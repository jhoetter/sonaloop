"""Ground personas & sessions in real source material
(ticket ground-personas-from-real-material — the #1 capability gap).

Real corpora — interview transcripts, support tickets, reviews, survey
verbatims — become first-class, citable grounding: `ingest_corpus` chunks and
dedupes the messy raw material into addressable units (stable chunk ids);
`brief_grounding` gathers the chunks for the HOST to author a persona profile
or patch from (the same gather → author → write-back contract as everything
else — the server never generates text); `record_grounding` persists the
PROVENANCE — which chunks shaped which trait or claim — onto the persona.

Downstream, the grounding rides every session: `prepare_persona_agent_context`
appends the task-relevant chunks with their ids and instructs citations as
refs `{kind: 'evidence', id: <chunk_id>, quote: …}` on statements/findings, so
a synthesis claim traces back to the exact source line via `trace_evidence`.

Grounding works ALONGSIDE source prompts, never instead of them: the authored
profile keeps its source_description; the corpus adds the real signal."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from ..config import utc_now_iso
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, …)


CHUNK_TARGET_CHARS = 1200
CHUNK_MERGE_BELOW_CHARS = 200
CHUNK_MIN_CHARS = 20
BRIEF_CHUNK_CAP = 40
MAX_CORPUS_BYTES = 10 * 1024 * 1024


# --- Chunking: messy, large input → deduped, addressable units --------------------

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _split_units(text: str) -> list[str]:
    """Natural units: blank-line paragraphs, with speaker-turn lines ("Name: …")
    kept as their own unit so transcripts chunk along turns."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        lines = para.splitlines()
        speakerish = sum(1 for ln in lines if re.match(r"^[\w .\-]{1,40}:\s", ln))
        if len(lines) > 1 and speakerish >= max(2, len(lines) // 2):
            units.extend(ln.strip() for ln in lines if ln.strip())
        else:
            units.append(re.sub(r"[ \t]+", " ", para))
    return units


def chunk_corpus_text(text: str) -> tuple[list[str], int]:
    """Split into natural units → dedup near-identical units (the messy-input
    reality: repeated paragraphs, copy-paste echoes) → merge only SMALL fragments
    forward (a lone question joins its answer) so each chunk stays one coherent,
    citable statement. Returns (chunks, deduped_units). Deterministic, no LLM."""
    seen: set[str] = set()
    units: list[str] = []
    deduped = 0
    for unit in _split_units(text):
        key = _normalize(unit)
        if not key:
            continue
        if key in seen:
            deduped += 1
            continue
        seen.add(key)
        units.append(unit)
    merged: list[str] = []
    buf = ""
    for unit in units:
        if buf and len(buf) < CHUNK_MERGE_BELOW_CHARS:
            buf = f"{buf}\n{unit}"
        else:
            if buf:
                merged.append(buf)
            buf = unit
        while len(buf) > CHUNK_TARGET_CHARS:           # a single oversized unit: hard-wrap
            merged.append(buf[:CHUNK_TARGET_CHARS])
            buf = buf[CHUNK_TARGET_CHARS:]
    if buf:
        merged.append(buf)
    return [m for m in merged if len(m) >= CHUNK_MIN_CHARS], deduped


def ingest_corpus(content_or_path: str, source_type: str, title: str | None = None,
                  notes: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Ingest one real document (a transcript, ticket export, review dump, survey
    verbatims) as a corpus of citable chunks. `content_or_path` is a file path or
    the raw text itself (the evidence-attach convention). Idempotent: identical
    content yields the same corpus id; near-duplicate chunks are dropped."""
    store = store or Store()
    src = None
    if "\n" not in content_or_path and len(content_or_path) < 512:
        try:
            candidate = Path(content_or_path).expanduser()
            src = candidate if candidate.is_file() else None
        except OSError:
            src = None
    if src:
        from .. import config
        if config.postgres_row_tenancy_enabled() and not src.resolve().is_relative_to(
                config.partition_dir().resolve()):
            raise ValueError("corpus file path must stay inside the active workspace partition; "
                             "send external material as inline content")
        if src.stat().st_size > MAX_CORPUS_BYTES:
            raise ValueError(f"Corpus exceeds the {MAX_CORPUS_BYTES // (1024 * 1024)}MB cap.")
        text, source = src.read_text(encoding="utf-8", errors="ignore"), str(src)
    else:
        text, source = content_or_path, "inline"
    if not text.strip():
        raise ValueError("Corpus is empty.")
    content_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    corpus_id = f"corpus_{content_hash}"
    chunks_raw, deduped = chunk_corpus_text(text)
    chunks = [{"id": stable_id("chunk", corpus_id, str(idx), raw_chunk[:80]),  # noqa: F821 (bound)
               "corpus_id": corpus_id, "idx": idx, "text": raw_chunk}
              for idx, raw_chunk in enumerate(chunks_raw)]
    if not chunks:
        raise ValueError("Corpus chunked to nothing usable (only noise/empty fragments).")
    corpus = {"id": corpus_id, "title": (title or (src.name if src else
              text.strip().splitlines()[0][:80])).strip(),
              "source_type": source_type, "source": source, "notes": notes or "",
              "bytes": len(text.encode("utf-8")), "chunks": len(chunks), "deduped": deduped,
              "created_at": utc_now_iso()}
    store.upsert_corpus(corpus)
    store.insert_corpus_chunks(chunks)
    return corpus


def list_corpora(store: Store | None = None) -> list[dict[str, Any]]:
    store = store or Store()
    return sorted(store.list_corpora(), key=lambda c: c.get("created_at", ""))


def get_corpus(corpus_id: str, include_chunks: bool = False,
               limit: int | None = None, cursor: str | None = None,
               store: Store | None = None) -> dict[str, Any]:
    """One corpus record. `include_chunks=True` adds `chunk_list` — PAGED per the
    shared convention (docs/pagination.md): `limit` (default 25) + opaque `cursor`
    over the stable chunk order, with `chunk_total`/`has_more`/`next_cursor`
    alongside. A corpus can be megabytes; the page keeps the result context-sized
    and the in-band note names the params that return the rest."""
    store = store or Store()
    corpus = store.get_corpus(corpus_id)
    if not corpus:
        raise KeyError(f"Unknown corpus: {corpus_id}")
    if include_chunks:
        from ._pagination import paginate
        page = paginate(store.list_corpus_chunks(corpus_id), lambda c: f"{c['idx']:08d}",
                        limit=limit, cursor=cursor, filters={"corpus_id": corpus_id})
        corpus = {**corpus, "chunk_list": page["items"], "chunk_total": page["total"],
                  "has_more": page["has_more"]}
        if page["has_more"]:
            corpus["next_cursor"] = page["next_cursor"]
            corpus["note"] = (
                f"chunk_list shows {len(page['items'])} of {page['total']} chunks — pass "
                f"cursor=next_cursor (and limit, max 200) to get_corpus for the rest, or "
                f"search_corpus(query, corpus_ids=[{corpus_id!r}]) for targeted retrieval.")
    return corpus


def search_corpus(query: str, corpus_ids: list[str] | None = None, limit: int = 12,
                  store: Store | None = None) -> list[dict[str, Any]]:
    """Keyword search over chunks (token-hit scoring) — how a session pulls the real
    signal relevant to its task. Deterministic, no embeddings required."""
    store = store or Store()
    tokens = [t for t in re.findall(r"\w{3,}", (query or "").lower())]
    if not tokens:
        return []
    scored = []
    for c in store.all_corpus_chunks(corpus_ids):
        low = c["text"].lower()
        score = sum(low.count(t) for t in tokens)
        if score:
            scored.append((score, c))
    scored.sort(key=lambda sc: (-sc[0], sc[1]["id"]))
    return [{**c, "score": s} for s, c in scored[:max(1, min(50, limit))]]


# --- Gather → author → write-back: grounded persona create/update ------------------

def brief_grounding(corpus_ids: list[str], persona_id: str | None = None,
                    focus: str | None = None, store: Store | None = None) -> dict[str, Any]:
    """Gather everything the host needs to author a persona FROM real material
    (create: no persona_id) or to refresh one against new material (update).
    Returns the corpus chunks (capped; use search_corpus for more) + the authoring
    contract: every trait/claim that the material supports lists its chunk ids in
    `provenance` — that provenance is what record_grounding persists."""
    store = store or Store()
    corpora = [get_corpus(cid, store=store) for cid in corpus_ids]
    chunks: list[dict[str, Any]] = []
    if focus:
        chunks = search_corpus(focus, corpus_ids, limit=BRIEF_CHUNK_CAP, store=store)
    if not chunks:
        for cid in corpus_ids:
            chunks.extend(store.list_corpus_chunks(cid))
    total = len(chunks)
    chunks = chunks[:BRIEF_CHUNK_CAP]
    persona = None
    if persona_id:
        persona = store.get_persona(persona_id)
        if not persona:
            raise KeyError(f"Unknown persona: {persona_id}")
    mode = "update" if persona else "create"
    create_steps = (
        "1) Author `description` (the source prompt — grounding works ALONGSIDE it, not instead) "
        "and the profile JSON FROM these chunks: real pains, tools, constraints, vocabulary. "
        "2) record_persona(description, profile). "
        "3) record_grounding(<new persona_id>, corpus_ids, provenance).")
    update_steps = (
        "1) Compare the current profile against the chunks; author a `patch` for what the real "
        "material corrects or deepens (do NOT overwrite traits the material is silent on). "
        "2) record_grounding(persona_id, corpus_ids, provenance, patch=<the patch>, reason=…).")
    return {
        "schema": "grounding", "mode": mode, "corpus_ids": corpus_ids,
        "corpora": [{"id": c["id"], "title": c["title"], "source_type": c["source_type"],
                     "chunks": c["chunks"]} for c in corpora],
        "persona": ({"persona_id": persona["id"], "display_name": persona["display_name"],
                     "profile_summary": {k: persona.get(k) for k in
                                         ("goals", "constraints", "pain_points", "tools")},
                     "grounding": persona.get("grounding")} if persona else None),
        "chunks": [{"id": c["id"], "corpus_id": c["corpus_id"], "text": c["text"]} for c in chunks],
        "chunks_total": total, "chunks_shown": len(chunks),
        "instructions": (
            f"Ground this persona in REAL material ({mode} mode). Work ONLY from the chunks — "
            "do not invent signal the material doesn't carry; traits the material contradicts "
            "must follow the material. Build `provenance`: a list of "
            "{claim: <the trait/claim you authored>, chunk_ids: [<the chunks that support it>]} — "
            "every load-bearing claim should trace to at least one chunk. Then: "
            + (create_steps if mode == "create" else update_steps)
            + (" More material exists than shown — search_corpus(query, corpus_ids) to pull "
               "specific signal." if total > len(chunks) else "")
        ),
    }


def record_grounding(persona_id: str, corpus_ids: list[str],
                     provenance: list[dict[str, Any]],
                     patch: dict[str, Any] | None = None,
                     reason: str = "grounded from real material",
                     store: Store | None = None) -> dict[str, Any]:
    """Persist the grounding the host authored: optional profile patch + the
    provenance map (claim → chunk ids). The corpora are linked as persona evidence
    (so the evidence-check flow sees them) and the claims land on
    `persona['grounding']`. Emits `persona.grounded`."""
    store = store or Store()
    if not store.get_persona(persona_id):
        raise KeyError(f"Unknown persona: {persona_id}")
    corpora = [get_corpus(cid, store=store) for cid in corpus_ids]  # validates ids
    if not provenance:
        raise ValueError("provenance is required: [{claim, chunk_ids}] — grounding without "
                         "traceability is the failure mode this ticket removes.")
    valid_chunk_ids = {c["id"] for cid in corpus_ids for c in store.list_corpus_chunks(cid)}
    claims = []
    now = utc_now_iso()
    for entry in provenance:
        claim = str(entry.get("claim", "")).strip()
        chunk_ids = [str(x) for x in (entry.get("chunk_ids") or [])]
        if not claim or not chunk_ids:
            raise ValueError(f"Bad provenance entry (need claim + chunk_ids): {entry!r}")
        unknown = [x for x in chunk_ids if x not in valid_chunk_ids]
        if unknown:
            raise ValueError(f"Unknown chunk ids in provenance: {unknown}")
        claims.append({"claim": claim, "chunk_ids": chunk_ids, "grounded_at": now})
    if patch:
        update_persona(persona_id, patch, reason, store=store)  # noqa: F821 (bound)
    persona = store.get_persona(persona_id)
    grounding = persona.get("grounding") or {"corpus_ids": [], "claims": []}
    grounding["corpus_ids"] = sorted(set(grounding["corpus_ids"]) | set(corpus_ids))
    grounding["claims"] = (grounding.get("claims") or []) + claims
    grounding["updated_at"] = now
    persona["grounding"] = grounding
    persona["updated_at"] = now
    store.upsert_persona(persona, reason=reason)
    for corpus in corpora:
        attach_evidence(persona_id, corpus["source_type"], f"corpus:{corpus['id']}",  # noqa: F821 (bound)
                        notes=f"grounding corpus: {corpus['title']}", store=store)
    emit_lifecycle_event("persona.grounded", {"persona_id": persona_id,  # noqa: F821 (bound)
                                              "corpus_ids": corpus_ids,
                                              "claims": len(claims)}, store)
    return {"persona_id": persona_id, "corpus_ids": grounding["corpus_ids"],
            "claims": len(grounding["claims"]), "patched": bool(patch)}


def trace_evidence(chunk_id: str, store: Store | None = None) -> dict[str, Any]:
    """From a cited chunk id back to the source: the chunk text, its corpus, and
    every persona claim grounded on it — how a synthesis ref
    {kind:'evidence', id:<chunk_id>} resolves to real signal."""
    store = store or Store()
    chunk = store.get_corpus_chunk(chunk_id)
    if not chunk:
        raise KeyError(f"Unknown evidence chunk: {chunk_id}")
    corpus = store.get_corpus(chunk["corpus_id"]) or {}
    grounded = []
    for p in store.list_personas():
        for claim in ((p.get("grounding") or {}).get("claims") or []):
            if chunk_id in claim.get("chunk_ids", []):
                grounded.append({"persona_id": p["id"], "display_name": p.get("display_name", ""),
                                 "claim": claim["claim"], "grounded_at": claim.get("grounded_at")})
    return {"chunk": chunk,
            "corpus": {"id": corpus.get("id"), "title": corpus.get("title"),
                       "source_type": corpus.get("source_type"), "source": corpus.get("source")},
            "grounded_claims": grounded}


def grounding_context_block(persona: dict[str, Any], task: str | None,
                            store: Store, k: int = 6) -> str:
    """The session-side feed: the persona's grounded source chunks most relevant to
    the task (keyword recall over its grounding corpora), rendered with ids so the
    host cites them as refs {kind:'evidence', id: <chunk_id>, quote: …}."""
    grounding = persona.get("grounding") or {}
    corpus_ids = grounding.get("corpus_ids") or []
    if not corpus_ids:
        return ""
    hits = search_corpus(task or "", corpus_ids, limit=k, store=store) if task else []
    if not hits:                                        # no task signal: lead with the first chunks
        hits = store.all_corpus_chunks(corpus_ids)[:k]
    lines = [f"- [{h['id']}] {h['text'][:400]}" for h in hits]
    return ("\n".join(lines)
            + "\n(Cite this material in statements/findings as refs "
              "{kind: 'evidence', id: <chunk id>, quote: <the words used>}.)")
