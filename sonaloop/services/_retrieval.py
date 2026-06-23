"""The host-agnostic retrieval facade: `retrieval_search` + `retrieval_fetch`.

ChatGPT's connector / Deep Research mode REQUIRES a server to expose two tools named
exactly `search` and `fetch` with a fixed shape (search -> {results:[{id,title,url}]};
fetch -> {id,title,text,url,metadata}) — without them ChatGPT rejects the server outside
Developer Mode and Deep Research can't run at all. The MCP wrappers (mcp_server) expose
those names; here we implement the cross-entity lookup over the workspace's own research
records (projects, councils, syntheses, hypotheses, personas) — read-only, deterministic,
no embeddings (a plain scored substring match, the same spirit as the catalog recommender).

These return the BARE OpenAI shape (not the _env envelope) so a ChatGPT client parses them
verbatim; the MCP wrappers return them unwrapped on purpose.
"""
from __future__ import annotations

from typing import Any

from ..config import partition_dir  # noqa: F401  (kept for parity; store resolves the partition)
from ..storage import Store

# web_url is bound into this module's globals by services/__init__ (cross-module registry).


def _tokens(s: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in (s or "")).split() if t]


def _score(haystack: str, query_tokens: list[str]) -> int:
    """How many distinct query tokens appear in the haystack — a transparent relevance count
    (no TF-IDF, no vectors): enough to rank the right entity to the top for a known term."""
    hay = haystack.lower()
    return sum(1 for t in set(query_tokens) if t in hay)


def _project_hit(p: dict, q: list[str]) -> tuple[int, dict] | None:
    score = _score(f"{p.get('title','')} {p.get('goal','')}", q)
    if not score:
        return None
    return score, {"id": p["id"], "title": p.get("title", p["id"]),
                   "url": web_url(f"/jobs/{p['id']}"),  # noqa: F821 (bound)
                   "text": (p.get("goal", "") or "")[:300]}


def retrieval_search(query: str, limit: int = 20, store: Store | None = None) -> dict[str, Any]:
    """OpenAI search-tool shape: {results:[{id,title,url,text}]} over the workspace's own
    research records. A keyword/substring scorer ranks projects, councils, syntheses,
    hypotheses and personas; the highest-scoring `limit` are returned with a link each."""
    store = store or Store()
    q = _tokens(query)
    scored: list[tuple[int, dict]] = []
    if not q:                                   # empty query: most-recent projects, still useful
        for p in store.list_research_projects()[:limit]:
            scored.append((0, {"id": p["id"], "title": p.get("title", p["id"]),
                               "url": web_url(f"/jobs/{p['id']}"),  # noqa: F821 (bound)
                               "text": (p.get("goal", "") or "")[:300]}))
        return {"results": [r for _, r in scored]}

    for p in store.list_research_projects():
        hit = _project_hit(p, q)
        if hit:
            scored.append(hit)
    for c in store.list_council_sessions():
        s = _score(c.get("prompt", ""), q)
        if s:
            scored.append((s, {"id": c["id"], "title": c.get("prompt", c["id"])[:120],
                               "url": web_url(f"/councils/{c['id']}"),  # noqa: F821 (bound)
                               "text": (c.get("exec_summary", "") or c.get("summary", ""))[:300]}))
    for syn in store.list_syntheses():
        s = _score(f"{syn.get('title','')} {syn.get('gesamtbild','')}", q)
        if s:
            scored.append((s, {"id": syn["id"], "title": syn.get("title", syn["id"]),
                               "url": web_url(f"/syntheses/{syn['id']}"),  # noqa: F821 (bound)
                               "text": (syn.get("gesamtbild", "") or "")[:300]}))
    for hyp in store.list_hypotheses():
        s = _score(hyp.get("text", ""), q)
        if s:
            scored.append((s, {"id": hyp["id"], "title": (hyp.get("text", "") or hyp["id"])[:120],
                               "url": web_url(f"/hypotheses/{hyp['id']}"),  # noqa: F821 (bound)
                               "text": (hyp.get("text", "") or "")[:300]}))
    for persona in store.list_personas():
        seg = persona.get("segment") or {}
        s = _score(f"{persona.get('display_name','')} {seg.get('customer_type','')} "
                   f"{(persona.get('role') or {}).get('title','')}", q)
        if s:
            scored.append((s, {"id": persona["id"], "title": persona.get("display_name", persona["id"]),
                               "url": web_url(f"/personas/{persona['id']}"),  # noqa: F821 (bound)
                               "text": (seg.get("customer_type", "") or "")[:300]}))
    scored.sort(key=lambda sr: (-sr[0], sr[1]["title"]))
    return {"results": [r for _, r in scored[:max(1, limit)]]}


def retrieval_fetch(id: str, store: Store | None = None) -> dict[str, Any]:
    """OpenAI fetch-tool shape: {id,title,text,url,metadata} for ONE record, resolved by id
    prefix across the workspace's research records. `text` is a plain-text rendering the host
    can read/quote; `metadata` carries the kind + structured counts."""
    store = store or Store()
    rid = (id or "").strip()

    def doc(title: str, text: str, url_path: str, **meta) -> dict[str, Any]:
        return {"id": rid, "title": title, "text": text,
                "url": web_url(url_path), "metadata": {**meta}}  # noqa: F821 (bound)

    if rid.startswith("rproject_"):
        p = store.get_research_project(rid)
        if not p:
            raise KeyError(f"Unknown record: {rid}")
        cs = [c for c in store.list_council_sessions() if c.get("project_id") == rid]
        lines = [f"# {p.get('title','')}", "", f"Goal: {p.get('goal','')}",
                 f"Status: {p.get('status','active')}", "",
                 f"Councils: {len(cs)}", "Council prompts:"]
        lines += [f"- {c.get('prompt','')}" for c in cs[:25]]
        return doc(p.get("title", rid), "\n".join(lines), f"/jobs/{rid}",
                   kind="project", councils=len(cs), status=p.get("status", "active"))
    if rid.startswith("council_"):
        c = store.get_council_session(rid)
        if not c:
            raise KeyError(f"Unknown record: {rid}")
        sts = c.get("statements") or []
        lines = [f"# {c.get('prompt','')}", ""]
        for st in sts[:60]:
            lines.append(f"- {st.get('persona_id','')}: {st.get('text','')}")
        return doc(c.get("prompt", rid)[:120], "\n".join(lines), f"/councils/{rid}",
                   kind="council", project_id=c.get("project_id", ""), statements=len(sts))
    if rid.startswith("synthesis_") or rid.startswith("report_"):
        syn = store.get_synthesis(rid)
        if not syn:
            raise KeyError(f"Unknown record: {rid}")
        findings = syn.get("findings") or []
        lines = [f"# {syn.get('title','')}", "", syn.get("gesamtbild", ""), "",
                 syn.get("positionierung", "")]
        if findings:
            lines += ["", "Findings:"] + [f"- {f.get('text','')}" for f in findings[:40]]
        return doc(syn.get("title", rid), "\n".join(l for l in lines if l is not None),
                   f"/syntheses/{rid}", kind="synthesis", project_id=syn.get("project_id", ""),
                   findings=len(findings))
    if rid.startswith("hyp_"):
        h = store.get_hypothesis(rid)
        if not h:
            raise KeyError(f"Unknown record: {rid}")
        pred = h.get("prediction") or {}
        text = (f"{h.get('text','')}\n\nPrediction: {pred}\n"
                f"Status: {h.get('status','open')}\nResult: {h.get('result')}")
        return doc((h.get("text", "") or rid)[:120], text, f"/hypotheses/{rid}",
                   kind="hypothesis", project_id=h.get("project_id", ""), status=h.get("status", "open"))
    # personas have free-form ids (slug/uuid) — try a persona lookup last
    persona = store.get_persona(rid)
    if persona:
        seg = persona.get("segment") or {}
        role = persona.get("role") or {}
        lines = [f"# {persona.get('display_name','')}",
                 f"{role.get('title','')} — {seg.get('customer_type','')}", "",
                 "Goals: " + "; ".join(persona.get("goals") or []),
                 "Pain points: " + "; ".join(persona.get("pain_points") or [])]
        return doc(persona.get("display_name", rid), "\n".join(lines), f"/personas/{rid}",
                   kind="persona", segment=seg.get("customer_type", ""))
    raise KeyError(f"Unknown record: {rid}")
