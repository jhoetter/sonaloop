"""Memory layer: entity/temporal graph, embeddings, hybrid retrieval, projection.

Implements spec/memory-and-simulation-architecture.md §3, §5.2, §6, §7, §12.1, §12.6.
This module is pure infrastructure (deterministic): it stores/retrieves what the
host LLM authored. It never generates persona text. The one external call is
OpenAI *embeddings* (retrieval only, not text generation), and it is fail-soft:
without a key, recall degrades to keyword/entity + recency + importance.
"""
from __future__ import annotations

import hashlib
import math
import re
from array import array
from typing import Any

from .config import (
    embedding_model,
    embeddings_enabled,
    recency_halflife_days,
    retrieval_weights,
    utc_now_iso,
)
from .storage import Store

_WORD = re.compile(r"[0-9a-zäöüß]+", re.IGNORECASE)
_STOP = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einen", "mit", "für", "auf",
    "den", "dem", "des", "im", "in", "am", "an", "zu", "zur", "zum", "von", "vom",
    "ist", "war", "wird", "hat", "the", "and", "for", "with", "of", "to", "a", "an",
}


def mem_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall((text or "").lower()) if t not in _STOP and len(t) > 2}


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


# --------------------------------------------------------------------------- #
# Embeddings (OpenAI, fail-soft)                                              #
# --------------------------------------------------------------------------- #

def _pack(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def _unpack(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return list(a)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Return one vector per input text, or None if embeddings are unavailable.

    Provider-agnostic since ticket provider-agnostic-embeddings: the active
    provider (openai | ollama | none) is a config choice — see sonaloop/embeddings.py.
    Fail-soft: any error degrades recall to keyword/entity + recency + importance."""
    from . import embeddings as _emb

    if not embeddings_enabled() or not texts:
        return None
    return _emb.embed_texts(texts)


def embedding_space() -> str:
    """The provider-qualified model id persisted with every vector — rows from a
    different space are never scored against the active one."""
    from . import embeddings as _emb

    return _emb.provider_model()


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def upsert_object_embedding(store: Store, obj_type: str, obj_id: str, persona_id: str, text: str) -> bool:
    """Embed and store one object's text. Returns True if an embedding was stored."""
    vecs = embed_texts([text])
    if not vecs:
        return False
    vec = vecs[0]
    store.upsert_embedding(obj_type, obj_id, persona_id, embedding_space(), _pack(vec), len(vec), text, utc_now_iso())
    return True


def backfill_persona_embeddings(store: Store, persona_id: str) -> dict[str, int]:
    """Embed all not-yet-embedded events/facts/digests/threads for a persona."""
    items: list[tuple[str, str, str]] = []  # (obj_type, obj_id, text)
    for e in store.list_experience_events(persona_id):
        items.append(("event", e["id"], f"{e.get('task','')}. {e.get('what_happened','')} {e.get('persona_thought','')}"))
    ent_name = {ent["id"]: ent["name"] for ent in store.list_entities(persona_id)}
    for ent in store.list_entities(persona_id):
        items.append(("entity", ent["id"], f"{ent['name']} ({ent['kind']})"))
    for f in store.list_persona_facts(persona_id):
        items.append(("fact", f["id"], f"{ent_name.get(f['entity_id'],'')}: {f['fact']}"))
    for d in store.list_digests(persona_id):
        items.append(("digest", d["id"], d.get("text", "")))
    for t in store.list_threads(persona_id):
        items.append(("thread", t["id"], t.get("text", "")))

    space = embedding_space()                      # re-embed per vector space: a provider/model
    todo = [(ot, oid, txt) for (ot, oid, txt) in items   # switch makes old rows invisible, not poison
            if txt.strip() and not store.has_embedding(ot, oid, model=space)]
    counts = {"embedded": 0, "skipped_existing": len(items) - len(todo), "disabled": 0}
    if not todo:
        return counts
    # batch in chunks
    for i in range(0, len(todo), 128):
        chunk = todo[i:i + 128]
        vecs = embed_texts([t[2] for t in chunk])
        if not vecs:
            counts["disabled"] = len(todo)
            return counts
        for (ot, oid, txt), vec in zip(chunk, vecs):
            # Persist the provider-qualified vector-space id.  ``embedding_model`` is
            # the legacy OpenAI-only value and would make Ollama rows invisible to the
            # read side immediately after a successful backfill.
            store.upsert_embedding(ot, oid, persona_id, space, _pack(vec), len(vec), txt, utc_now_iso())
            counts["embedded"] += 1
    store.commit()
    return counts


# --------------------------------------------------------------------------- #
# Entity resolution (§12.1)                                                    #
# --------------------------------------------------------------------------- #

def resolve_entity(store: Store, persona_id: str, mention: str, kind: str | None = None,
                   sim_threshold: float = 0.86, token_threshold: float = 0.6) -> dict[str, Any] | None:
    """Find an existing entity matching a mention, or None (caller creates new)."""
    norm = normalize_name(mention)
    if not norm:
        return None
    candidates = store.list_entities(persona_id, kind)
    if not candidates and kind:
        candidates = store.list_entities(persona_id)
    # 1) exact normalized name / alias match
    for ent in candidates:
        names = [ent["name"]] + ent.get("aliases", [])
        if norm in {normalize_name(n) for n in names}:
            return ent
    # 2) token-overlap (cheap, no key)
    mt = _tokens(mention)
    best, best_score = None, 0.0
    for ent in candidates:
        et = _tokens(ent["name"])
        if not mt or not et:
            continue
        overlap = len(mt & et) / len(mt | et)
        if overlap > best_score:
            best, best_score = ent, overlap
    if best and best_score >= token_threshold:
        return best
    # 3) semantic similarity (if embeddings available)
    vecs = embed_texts([mention])
    if vecs and candidates:
        q = vecs[0]
        for ent in candidates:
            emb = store.get_embedding("entity", ent["id"])
            score = cosine(q, _unpack(emb["vector"])) if emb else 0.0
            if score >= sim_threshold and score > best_score:
                best, best_score = ent, score
        if best and best_score >= sim_threshold:
            return best
    return None


# --------------------------------------------------------------------------- #
# Hybrid recall (§5.2)                                                         #
# --------------------------------------------------------------------------- #

def _age_days(ts: str | None, ref: str | None) -> float:
    from datetime import date

    def _d(x: str | None) -> date | None:
        if not x:
            return None
        try:
            return date.fromisoformat(x[:10])
        except ValueError:
            return None

    a, b = _d(ts), _d(ref) or _d(utc_now_iso())
    if not a or not b:
        return 0.0
    return max(0.0, (b - a).days)


def recall(store: Store, persona_id: str, query: str, as_of: str | None = None, k: int = 8) -> dict[str, Any]:
    """Hybrid scored retrieval over episodes, facts, digests, threads."""
    w = retrieval_weights()
    half = recency_halflife_days()
    qt = _tokens(query)
    qvec = embed_texts([query]) if query.strip() else None
    qvec = qvec[0] if qvec else None
    ent_name = {ent["id"]: ent["name"] for ent in store.list_entities(persona_id)}

    pool: list[dict[str, Any]] = []
    for e in store.list_experience_events(persona_id):
        if as_of and e["timestamp"][:10] > as_of:
            continue
        if e.get("memory_state") == "archived":
            continue
        pool.append({"obj_type": "event", "obj_id": e["id"], "when": e["timestamp"],
                     "text": f"{e.get('task','')}. {e.get('what_happened','')} {e.get('persona_thought','')}",
                     "importance": 3 + len(e.get("open_loops", [])), "ref": e})
    # Current recall sees only currently-valid facts.  Time-travel recall sees
    # exactly the interval valid at ``as_of``.  The old implementation admitted
    # every superseded fact and merely filtered future starts, which let a persona
    # remember mutually exclusive old and new states at once.
    facts = store.list_persona_facts(persona_id)
    if as_of:
        facts = [f for f in facts if f["t_valid"][:10] <= as_of
                 and (not f.get("t_invalid") or f["t_invalid"][:10] > as_of)]
    else:
        facts = [f for f in facts if not f.get("t_invalid")]
    for f in facts:
        pool.append({"obj_type": "fact", "obj_id": f["id"], "when": f["t_valid"],
                     "text": f"{ent_name.get(f['entity_id'],'')}: {f['fact']}",
                     "importance": int(f.get("importance", 3)), "ref": f})
    for d in store.list_digests(persona_id):
        if as_of and d["period_end"][:10] > as_of:
            continue
        pool.append({"obj_type": "digest", "obj_id": d["id"], "when": d["period_end"],
                     "text": d.get("text", ""), "importance": 4, "ref": d})
    for t in store.list_threads(persona_id):
        if as_of and t.get("opened_on") and t["opened_on"][:10] > as_of:
            continue
        effective_status = t["status"]
        if as_of:
            effective_status = ("resolved" if t.get("closed_on")
                                and t["closed_on"][:10] <= as_of else "open")
        pool.append({"obj_type": "thread", "obj_id": t["id"], "when": t.get("opened_on"),
                     "text": t.get("text", ""), "importance": 4 if effective_status == "open" else 2,
                     "ref": {**t, "status_at_recall": effective_status}})

    # precompute semantic scores via stored embeddings
    emb_index = {}
    other_space = 0
    if qvec is not None:
        space = embedding_space()
        for row in store.list_embeddings(persona_id):
            if row.get("model") != space:              # never mix vector spaces (provider/model switch)
                other_space += 1
                continue
            emb_index[(row["obj_type"], row["obj_id"])] = _unpack(row["vector"])

    scored = []
    for item in pool:
        it = _tokens(item["text"])
        kw = (len(qt & it) / len(qt)) if qt else 0.0
        sem = 0.0
        if qvec is not None:
            v = emb_index.get((item["obj_type"], item["obj_id"]))
            if v:
                sem = max(0.0, cosine(qvec, v))
        rec = 0.5 ** (_age_days(item["when"], as_of) / half) if half else 0.0
        imp = min(1.0, item["importance"] / 5.0)
        score = w["semantic"] * sem + w["keyword"] * kw + w["recency"] * rec + w["importance"] * imp
        scored.append((score, sem, kw, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    hits = []
    for score, sem, kw, item in scored[:k]:
        recency = 0.5 ** (_age_days(item["when"], as_of) / half) if half else 0.0
        importance = min(1.0, item["importance"] / 5.0)
        source = item["ref"]
        hits.append({
            "obj_type": item["obj_type"], "obj_id": item["obj_id"], "when": item["when"],
            "score": round(score, 4), "semantic": round(sem, 4), "keyword": round(kw, 4),
            "recency": round(recency, 4), "importance": round(importance, 4),
            "source_kind": source.get("source_kind") or (
                "simulated_episode" if item["obj_type"] == "event" else "derived_memory"),
            "source_refs": source.get("source_refs") or (
                ([{"kind": "event", "id": source["source_event_id"]}]
                 if source.get("source_event_id") else [])),
            "confidence": source.get("confidence"),
            "review_status": source.get("review_status"),
            "text": item["text"][:280],
        })
    out = {
        "persona_id": persona_id, "query": query, "as_of": as_of,
        "semantic_enabled": qvec is not None, "k": k, "hits": hits,
    }
    if other_space:
        out["embedding_space_mismatch"] = {
            "skipped": other_space,
            "note": "stored vectors from a different provider/model were ignored — re-run "
                    "backfill-embeddings to re-embed them in the active space"}
    return out


# --------------------------------------------------------------------------- #
# Projections & time-travel                                                    #
# --------------------------------------------------------------------------- #

def get_project_timeline(store: Store, persona_id: str, entity_id: str, as_of: str | None = None) -> dict[str, Any]:
    ent = store.get_entity(entity_id)
    if not ent or ent["persona_id"] != persona_id:
        raise KeyError(f"Unknown entity for persona: {entity_id}")
    facts = store.list_entity_facts(entity_id)
    if as_of:
        facts = [f for f in facts if f["t_valid"][:10] <= as_of]
    threads = [t for t in store.list_threads(persona_id) if t.get("entity_id") == entity_id]
    return {
        "entity": ent,
        "status_now": ent.get("status"),
        "facts": [{"t_valid": f["t_valid"], "t_invalid": f.get("t_invalid"), "status": f.get("status"),
                   "fact": f["fact"], "valid": not f.get("t_invalid")} for f in facts],
        "open_threads": [t for t in threads if t["status"] == "open"],
        "event_ids": store.list_entity_events(entity_id),
    }


def list_active_projects(store: Store, persona_id: str) -> list[dict[str, Any]]:
    out = []
    for ent in store.list_entities(persona_id, "project"):
        threads = [t for t in store.list_threads(persona_id) if t.get("entity_id") == ent["id"] and t["status"] == "open"]
        facts = store.list_entity_facts(ent["id"], valid_only=True)
        _closed = ("abgeschlossen", "abgenommen", "fertig", "verloren", "abgelehnt", "abgesagt",
                   "abgebrochen", "gescheitert", "nicht weiterverfolgt", "fallengelassen", "verkauft",
                   "closed", "lost", "done", "won", "übergeben")
        st = (ent.get("status") or "").lower()
        if any(c in st for c in _closed):
            continue
        out.append({
            "entity_id": ent["id"], "name": ent["name"], "status": ent.get("status"),
            "last_seen": ent.get("last_seen"), "open_loops": len(threads), "valid_facts": len(facts),
        })
    return out


def get_state_at(store: Store, persona_id: str, as_of: str) -> dict[str, Any]:
    """Time-travel snapshot: entities + facts valid at a given simulation date."""
    entities = []
    for ent in store.list_entities(persona_id):
        facts = store.list_entity_facts(ent["id"], as_of=as_of)
        if not facts and (ent.get("first_seen") or "9999")[:10] > as_of:
            continue
        # status AT as_of = the most recent status-bearing fact valid then.
        # Never fall back to the entity's *current* status (that breaks time-travel).
        status_facts = [f for f in facts if f.get("status")]
        status_at = status_facts[-1]["status"] if status_facts else None
        entities.append({
            "entity_id": ent["id"], "kind": ent["kind"], "name": ent["name"],
            "status_at": status_at,
            "facts": [{"t_valid": f["t_valid"], "fact": f["fact"], "status": f.get("status")} for f in facts],
        })
    threads = [t for t in store.list_threads(persona_id)
               if (t.get("opened_on") or "0000")[:10] <= as_of
               and (t["status"] != "resolved" or (t.get("closed_on") or "9999")[:10] > as_of)]
    world = store.list_world_context(as_of=as_of)
    return {"persona_id": persona_id, "as_of": as_of, "entities": entities,
            "open_threads": threads, "world_context": world}


def render_memory_md(store: Store, persona: dict[str, Any]) -> str:
    """Compact, human/LLM-readable projection of memory layer 2/3 (the MEMORY.md)."""
    pid = persona["id"]
    active = list_active_projects(store, pid)
    people = store.list_entities(pid, "person")
    digests = store.list_digests(pid)
    open_threads = store.list_threads(pid, "open")

    def proj_block(p: dict[str, Any]) -> str:
        tl = store.list_entity_facts(p["entity_id"])
        lines = [f"### {p['name']}  —  Status: {p.get('status') or 'unbekannt'}"]
        for f in tl[-6:]:
            mark = "" if not f.get("t_invalid") else "  (überholt)"
            lines.append(f"- {f['t_valid'][:10]}: {f['fact']}{mark}")
        return "\n".join(lines)

    parts = [f"# {persona['display_name']} — MEMORY", "",
             "> Gerendert aus dem Gedächtnis (Schicht 2/3). Hintergrundwissen — bei Bedarf abrufbar, nicht ständig erzählen.",
             "", "## Aktive Projekte"]
    parts.append("\n\n".join(proj_block(p) for p in active) or "- keine aktiven Projekte erfasst.")
    parts += ["", "## Offene Fäden"]
    parts.append("\n".join(f"- {t['text']} (seit {(t.get('opened_on') or '?')[:10]})" for t in open_threads) or "- keine.")
    parts += ["", "## Schlüsselpersonen / Stellen"]
    parts.append("\n".join(f"- {p['name']} ({p['kind']})" for p in people[:12]) or "- keine erfasst.")
    parts += ["", "## Verdichtete Rückblicke"]
    parts.append("\n".join(f"- [{d['scope']} {d['period_start'][:10]}…{d['period_end'][:10]}] {d.get('text','')[:240]}"
                           for d in digests[-6:]) or "- noch keine Digests.")
    return "\n".join(parts) + "\n"
