"""PPTX export — the DOMAIN logic for a native PowerPoint deck of any report (which slides, which
data); the slide→.pptx mechanics live in sonaloop/_pptx.py. Split out of services/_synthesis.py to
keep both modules under the LOC bar (spec/refactor-plan.md), behaviour-preserving.

Also home to export_synthesis_deliverable — the ONE binary-deliverable seam (pptx|pdf) the CLI and
MCP export route through: it writes via write_export_bytes (relative paths land under
DATA_DIR/exports/, never the caller's CWD) and records the file ON the owning project as a
`direction: out` asset (ticket project-assets-direction-deliverables-page-section).
"""
from __future__ import annotations

import re as _re_pptx
from pathlib import Path

from .. import artifacts as _A
from .. import config
from ..config import content_language
from ..storage import Store
from ._synthesis import _SYNTHESIS_EXPORT_LABELS, get_synthesis


def _strip_md(s: str) -> str:
    """Inline markdown → clean presenter text (bold/italic/code/links/figure-refs removed) so no raw
    `**`, `_`, `` ` `` or `![[fig]]` markers leak into a slide."""
    s = _re_pptx.sub(r"!\[\[.*?\]\]", "", s or "")
    s = _re_pptx.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = _re_pptx.sub(r"__(.+?)__", r"\1", s)
    s = _re_pptx.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", s)
    s = _re_pptx.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", s)
    s = _re_pptx.sub(r"`(.+?)`", r"\1", s)
    s = _re_pptx.sub(r"\[(.+?)\]\(.*?\)", r"\1", s)
    # bare artifact ids (council_…/protosession_…/…) are terminal output, not slide copy (§9 V11) —
    # drop them and heal the leftover punctuation/whitespace.
    s = _re_pptx.sub(r"\b[a-z]+_[0-9a-f]{12,16}\b", "", s)
    s = _re_pptx.sub(r"\(\s*[,;·]?\s*\)", "", s)
    s = _re_pptx.sub(r"\s+([,;.!?)])", r"\1", s)
    s = _re_pptx.sub(r"\(\s+", "(", s)
    s = _re_pptx.sub(r"\s{2,}", " ", s)
    return s.strip()


# callout directive kind → the colour role the slide paints it (mirrors the report's :::insight /
# :::recommendation / :::risk callout cards).
_CALLOUT_KIND = {"insight": "accent", "recommendation": "green", "rec": "green",
                 "risk": "amber", "key": "accent", "keytakeaway": "accent"}


def _md_blocks(md: str) -> list[dict]:
    """Markdown section body → a list of typed blocks the slide renderer styles like the report:
    {type: p|li|quote|callout|h, text, [kind,label]}. Callout fences (:::insight … :::) and
    blockquotes (>) are PRESERVED (not dropped) and inline markdown is stripped."""
    blocks: list[dict] = []
    lines = (md or "").split("\n")
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1; continue
        if s.startswith(":::"):
            tag = s[3:].strip().lower()
            body = []
            i += 1
            while i < n and lines[i].strip() != ":::":
                if lines[i].strip():
                    body.append(_strip_md(lines[i].strip()))
                i += 1
            i += 1  # closing fence
            if body:
                blocks.append({"type": "callout", "kind": _CALLOUT_KIND.get(tag, "accent"),
                               "label": (tag or "insight").replace("keytakeaway", "key").capitalize(),
                               "text": " ".join(body)})
            continue
        if s.startswith(">"):
            blocks.append({"type": "quote", "text": _strip_md(s.lstrip("> ").strip())})
        elif s[:2] in ("- ", "* "):
            blocks.append({"type": "li", "text": _strip_md(s[2:])})
        elif _re_pptx.match(r"^\d+\.\s", s):
            blocks.append({"type": "li", "text": _strip_md(_re_pptx.sub(r"^\d+\.\s", "", s))})
        elif s.startswith("#"):
            blocks.append({"type": "h", "text": _strip_md(s.lstrip("# ").strip())})
        else:
            blocks.append({"type": "p", "text": _strip_md(s)})
        i += 1
    return [b for b in blocks if b.get("text")]


def _li(texts: list[str]) -> list[dict]:
    return [{"type": "li", "text": _strip_md(t)} for t in texts if (t or "").strip()]


# ── prose discipline (ux-contract §9 V11): slides carry statements, cards and clamped leads —
# never the full authored prose. All splitting is renderer-side derivation from authored text;
# nothing new is written, the complete prose stays in the report/PDF. ─────────────────────────

# Sentence boundary only before an uppercase start ('Min.' / '+40 Min. wegen …' never splits) —
# the SAME heuristic the web report's verdict card uses (web/_synthesis._verdict_card).
_SENT_RE = _re_pptx.compile(r"(?<=[.!?])\s+(?=[«„\"'(]?[A-ZÄÖÜ])")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split((text or "").strip()) if s.strip()]


def _clause_cut(s: str, limit: int) -> str:
    """Hard cap for a single over-long sentence: cut at the last clause boundary before `limit`
    (comma / dash / semicolon; word boundary as a fallback) and mark the cut with an ellipsis."""
    if len(s) <= limit:
        return s
    cut = max(s.rfind(", ", 0, limit), s.rfind(" — ", 0, limit), s.rfind("; ", 0, limit))
    if cut < limit // 3:
        cut = s.rfind(" ", 0, limit)
    return s[:max(cut, 1)].rstrip(" ,;—") + " …"


def _clamp_prose(text: str, limit: int) -> tuple[str, bool]:
    """Sentence-greedy clamp: whole sentences while they fit; a lone over-long sentence
    clause-cuts. Returns (clamped_text, was_truncated)."""
    sents = _sentences(text)
    if not sents:
        return "", False
    out = _clause_cut(sents[0], limit)
    if out.endswith("…"):
        return out, True
    for s in sents[1:]:
        if len(out) + 1 + len(s) > limit:
            return out, True
        out = f"{out} {s}"
    return out, False


_PRESENTATION_PHASE_LABELS = {
    "de": (
        (("product understanding", "product-understanding"), "Testgegenstand & Ausgangslage"),
        (("cohort integrity", "cohort-integrity"), "Testgruppe & Aussagekraft"),
        (("react", "reaction"), "Reaktionen & zentrale Erkenntnisse"),
        (("gate", "decide", "deliver"), "Entscheidung & Empfehlungen"),
        (("discover", "empathize", "explore"), "Ausgangslage & Bedürfnisse"),
        (("define", "frame"), "Fokus & Fragestellung"),
        (("ideate", "develop"), "Lösungsrichtungen"),
        (("prototype",), "Prototyp"),
        (("test", "validate"), "Validierung"),
    ),
    "en": (
        (("product understanding", "product-understanding"), "Test subject & context"),
        (("cohort integrity", "cohort-integrity"), "Participants & limitations"),
        (("react", "reaction"), "Reactions & key findings"),
        (("gate", "decide", "deliver"), "Decision & recommendations"),
        (("discover", "empathize", "explore"), "Context & user needs"),
        (("define", "frame"), "Focus & research question"),
        (("ideate", "develop"), "Solution directions"),
        (("prototype",), "Prototype"),
        (("test", "validate"), "Validation"),
    ),
}


def _presentation_section_heading(section: dict, index: int, total: int, de: bool) -> str:
    """Turn plan-phase labels into stakeholder chapter labels without altering the report."""
    explicit = _strip_md(section.get("presentation_heading", ""))
    if explicit:
        return explicit
    heading = _strip_md(section.get("heading", ""))
    intent = str(section.get("intent") or "")
    # Authored thematic headings are already customer copy.  Only translate scaffolder-shaped
    # phase labels ("Author the X phase (diverge|converge) …").
    if not _re_pptx.search(r"\bphase\s*\((?:diverge|converge)", intent, _re_pptx.I):
        return heading
    normalized = heading.casefold().replace("_", " ").strip()
    language = "de" if de else "en"
    for tokens, label in _PRESENTATION_PHASE_LABELS[language]:
        if any(token in normalized for token in tokens):
            return label
    if index == 1:
        return "Ausgangslage" if de else "Context"
    if index == total:
        return "Entscheidung & nächste Schritte" if de else "Decision & next steps"
    return f'{"Erkenntnisse" if de else "Findings"} {index - 1}'


def _report_cover_lead(synthesis: dict, sections: list[dict], de: bool) -> str:
    """Prefer an authored lead; replace report-scaffolder boilerplate with the conclusion."""
    lead = _strip_md(synthesis.get("lead", ""))
    generic = (
        "entlang der forschungsphasen" in lead.casefold()
        or "along the research phases" in lead.casefold()
    )
    if lead and not generic:
        return _clamp_prose(lead, 220)[0]
    for block in _md_blocks((sections[-1] if sections else {}).get("markdown", "")):
        if block.get("type") in {"p", "callout", "quote"} and block.get("text"):
            return _clamp_prose(block["text"], 220)[0]
    return "Ergebnisse und Empfehlungen" if de else "Findings and recommendations"


# Authored exec prose often segments itself with caps-lock labels ("DAS GEWINNERKONZEPT: …",
# "SURVEY-RÜCKHALT (5 Antworten): …") — those labels are the natural takeaway-card titles.
_LBL_WORD = r"(?:[0-9A-ZÄÖÜ][0-9A-ZÄÖÜ\-/&'\.]+|\([^()]{1,40}\))"
_LABEL_RE = _re_pptx.compile(rf"(?:^|(?<=[.!?:])\s)({_LBL_WORD}(?:\s+{_LBL_WORD}){{0,5}}):\s+")


def _label_segments(prose: str) -> list[tuple[str, str]]:
    """[(label, body), …] for caps-label-structured prose; [] when the prose has no such spine."""
    ms = list(_LABEL_RE.finditer(prose or ""))
    segs = []
    for m, nxt in zip(ms, list(ms[1:]) + [None]):
        body = prose[m.end():(nxt.start() if nxt else len(prose))].strip()
        if body:
            segs.append((m.group(1).strip(), body))
    return segs


def _split_card(text: str, head_max: int = 90) -> tuple[str, str]:
    """One authored finding → (card_title, card_body): split at the first ': ' or ' — ' inside the
    first `head_max` chars (': ' needs the space, so 'Arbeiter:innen' / '15:00' never split). A head
    that still carries an ' — ' subtitle re-splits, the subtitle leads the body. No head → body only."""
    t = _strip_md(text)
    i = t.find(": ")
    if 0 < i <= head_max:
        head, body = t[:i], t[i + 2:]
    else:
        j = t.find(" — ")
        if 0 < j <= head_max and t[j + 3:].strip():
            return t[:j].strip(), t[j + 3:].strip()
        return "", t
    k = head.find(" — ")
    if k > 0:
        head, body = head[:k], (f"{head[k + 3:]}: {body}" if body else head[k + 3:])
    return head.strip(), body.strip()


def _chunks(items: list, per: int) -> list[list]:
    """Balanced chunking: 6 items at 4/slide become 3+3, never 4+2 (no half-empty card grids)."""
    n = len(items)
    if not n:
        return []
    parts = -(-n // per)
    base = -(-n // parts)
    return [items[i:i + base] for i in range(0, n, base)]


# stance value → canonical term / palette role (mirrors suggestions/stance_scale.json colours).
_STANCE_TERM = {2: "support", 1: "conditional", 0: "neutral", -1: "skeptical", -2: "oppose"}
_STANCE_COLOR = {2: "green", 1: "accent", 0: "faint", -1: "amber", -2: "red"}


def _stance_chart(counter, L: dict, kind: str) -> dict | None:
    """A stance-value Counter → a deck chart with scale-ordered categories, semantic colours and
    NO zero categories (§9 V3: empty legend entries dropped)."""
    from .._deck import PALETTE
    cats, vals, cols = [], [], []
    for v in (2, 1, 0, -1, -2):
        n = counter.get(v, 0)
        if n:
            cats.append(L[f"st_{v}"]); vals.append(n); cols.append(PALETTE[_STANCE_COLOR[v]])
    if not vals:
        return None
    return {"type": kind, "categories": cats, "values": vals, "colors": cols}


# per-block clamp budgets for project-report sections (slide = headline + dosed lead, not a dump)
_BLOCK_LIMIT = {"p": 320, "li": 220, "quote": 240, "callout": 280, "h": 90}


def _budget_blocks(blocks: list[dict], max_blocks: int = 7, budget: int = 900) -> tuple[list[dict], bool]:
    """Apply the slide prose budget to typed blocks: each block clamps to its type budget and the
    slide stops at `max_blocks`/`budget` chars. Returns (blocks, clipped) — clipped slides carry a
    'details in the report' footnote instead of the overflow."""
    out: list[dict] = []
    used, clipped = 0, False
    for b in blocks:
        if len(out) >= max_blocks or used >= budget:
            clipped = True
            break
        txt, tr = _clamp_prose(b.get("text", ""), _BLOCK_LIMIT.get(b.get("type", "p"), 300))
        clipped = clipped or tr
        if txt:
            out.append({**b, "text": txt})
            used += len(txt)
    return out, clipped


def _figure_to_chart(fig: dict, store: Store) -> dict | None:
    """A report `chart` figure → the neutral _pptx chart model, or None (non-chart / unresolvable).

    Mirrors the design-system chart `of`-kinds (see charts_catalogue / web/_report) so a deck shows
    the SAME chart the report/PDF does — as native, editable PowerPoint shapes."""
    if (fig or {}).get("kind") != "chart":
        return None
    of = fig.get("of", "effort_impact")
    series = [s for s in (fig.get("series") or []) if isinstance(s, dict)]
    if of in ("bar", "pie"):
        rows = [s for s in series if s.get("value") not in (None, "")]
        if not rows:
            return None
        return {"type": of, "categories": [_strip_md(s.get("label", "")) for s in rows],
                "values": [s.get("value") for s in rows]}
    if of == "stacked_bar":
        rows = [{"label": _strip_md(s.get("label", "")),
                 "segments": [{"label": _strip_md(g.get("label", "")), "value": g.get("value")}
                              for g in (s.get("segments") or []) if isinstance(g, dict)]}
                for s in series if s.get("segments")]
        return {"type": "stacked_bar", "rows": rows} if rows else None
    if of == "diverging_bar":
        rows = [{"label": _strip_md(s.get("label", "")), "positive": s.get("positive"), "negative": s.get("negative")}
                for s in series if s.get("positive") is not None or s.get("negative") is not None]
        return {"type": "diverging_bar", "rows": rows} if rows else None
    if of == "gauge":
        items = [{"label": _strip_md(s.get("label", "")), "value": s.get("value"), "max": s.get("max")}
                 for s in series if s.get("value") not in (None, "")]
        return {"type": "gauge", "items": items} if items else None
    if of == "dot_plot":
        rows = [{"label": _strip_md(s.get("label", "")),
                 "values": [v for v in (s.get("values") or []) if isinstance(v, (int, float))]}
                for s in series if s.get("values")]
        rows = [r for r in rows if r["values"]]
        return {"type": "dot_plot", "rows": rows} if rows else None
    if of == "heatmap":
        cols = [_strip_md(str(c)) for c in (fig.get("columns") or [])]
        rows = [{"label": _strip_md(s.get("label", "")), "values": list(s.get("values") or [])}
                for s in series if s.get("values")]
        return {"type": "heatmap", "columns": cols, "rows": rows} if cols and rows else None
    if of == "line":
        lines = [{"label": _strip_md(s.get("label", "")),
                  "points": [p for p in (s.get("points") or []) if isinstance(p, (int, float))]}
                 for s in series if s.get("points")]
        lines = [ln for ln in lines if len(ln["points"]) > 1]
        labels = [_strip_md(str(x)) for x in (fig.get("labels") or [])]
        return {"type": "line", "series": lines, "labels": labels} if lines else None
    if of == "burnup":
        lines = [{"label": _strip_md(s.get("label", "")),
                  "points": [p for p in (s.get("points") or []) if isinstance(p, (int, float))]}
                 for s in series if s.get("points")]
        lines = [ln for ln in lines if len(ln["points"]) > 1]
        if not lines:
            return None
        labels = [_strip_md(str(x)) for x in (fig.get("labels") or [])]
        # The deck reuses the native line model; the dotted ideal renders as a dashed Target series.
        return {"type": "line", "series": lines, "labels": labels, "target": fig.get("target")}
    if of == "stacked_area":
        bands = [{"label": _strip_md(s.get("label", "")),
                  "points": [p for p in (s.get("points") or []) if isinstance(p, (int, float))]}
                 for s in series if s.get("points")]
        bands = [b for b in bands if len(b["points"]) > 1]
        labels = [_strip_md(str(x)) for x in (fig.get("labels") or [])]
        return {"type": "stacked_area", "series": bands, "labels": labels} if bands else None
    if of == "column":
        items = []
        for s in series:
            if s.get("segments"):
                items.append({"label": _strip_md(s.get("label", "")),
                              "segments": [{"label": _strip_md(g.get("label", "")), "value": g.get("value")}
                                           for g in s["segments"] if isinstance(g, dict)]})
            elif s.get("value") not in (None, ""):
                items.append({"label": _strip_md(s.get("label", "")), "value": s.get("value")})
        return {"type": "column", "items": items} if items else None
    if of == "strip":
        rows = [{"label": _strip_md(s.get("label", "")),
                 "values": [v for v in (s.get("values") or []) if isinstance(v, (int, float))]}
                for s in series if s.get("values")]
        rows = [r for r in rows if r["values"]]
        if not rows:
            return None
        allv = [v for r in rows for v in r["values"]]
        mn = fig.get("min") if isinstance(fig.get("min"), (int, float)) else min(allv)
        mx = fig.get("max") if isinstance(fig.get("max"), (int, float)) else max(allv)
        # The continuous strip reuses the dot_plot model with a data-derived scale + unit suffix.
        return {"type": "dot_plot", "rows": rows, "min": mn, "max": mx, "unit": str(fig.get("unit") or "")}
    if of == "progress_strip":
        items = [{"label": _strip_md(s.get("label", "")), "value": s.get("value")}
                 for s in series if isinstance(s.get("value"), (int, float)) and s.get("value") > 0]
        return {"type": "progress_strip", "items": items} if items else None
    if of == "stats":
        items = []
        for s in series:
            if not (s.get("label") or s.get("value") not in (None, "")):
                continue
            it = {"label": _strip_md(s.get("label", "")),
                  "value": _strip_md(s["value"]) if isinstance(s.get("value"), str) else s.get("value")}
            if s.get("sub"):
                it["sub"] = _strip_md(s["sub"])
            items.append(it)
        return {"type": "stats", "items": items} if items else None
    if of == "effort_impact":
        sid = fig.get("source_id") or fig.get("id")
        syn = store.get_synthesis(sid) if sid else None
        if not syn:
            return None
        return _effort_impact_chart(syn)
    return None


def _figure_image(fig: dict, store: Store) -> tuple[str, str] | None:
    """An image figure (asset | prototype screenshot | avatar) → (local_file_path, caption), or None
    if it can't be embedded. Mirrors web/_report._resolve_figure but resolves to a FILE on disk so the
    PPTX can embed the actual bytes (the web/PDF load it by URL; a deck must carry it)."""
    from ..config import partition_dir
    kind = (fig or {}).get("kind"); cap = fig.get("caption", "")
    aid = None
    if kind == "asset" and fig.get("id"):
        aid = fig["id"]
    elif kind == "prototype" and fig.get("id"):
        p = store.get_prototype(fig["id"]) or {}
        aid = p.get("shot"); cap = cap or p.get("name", "")
    elif kind == "avatar" and fig.get("id"):
        p = store.get_persona(fig["id"]) or {}
        ap = (p.get("avatar") or {}).get("path")
        if ap:
            from ._snapshots import _avatar_disk_path
            path = _avatar_disk_path(ap)
            return (str(path), cap or p.get("display_name", "")) if path.exists() else None
        return None
    if aid:
        path = partition_dir() / aid
        if path.exists():
            return (str(path), cap)
    return None


def _effort_impact_chart(syn: dict) -> dict | None:
    # legend labels are the recommendation HEADS, never the full prose (one legend line each)
    pts = []
    for (txt, e, v) in _A.synthesis_recommendations(syn):
        if e and v:
            head, _body = _split_card(txt)
            pts.append({"x": e, "y": v, "label": head or _clause_cut(_strip_md(txt), 64)})
    if not pts:
        return None
    L = _SYNTHESIS_EXPORT_LABELS[content_language()]
    return {"type": "scatter", "points": pts, "x_label": L["effort"], "y_label": L["value"],
            "quadrants": [L["q_quick"], L["q_big"], L["q_fill"], L["q_sink"]]}


def _presentation_asset_path(project_id: str, value, store: Store) -> str:
    """Resolve a plan asset reference to its active-workspace file without exposing paths."""
    if isinstance(value, dict):
        asset_id = str(value.get("asset_id") or value.get("id") or "")
    else:
        asset_id = str(value or "")
    if not asset_id:
        return ""
    try:
        record = get_asset(project_id, asset_id, store=store)  # noqa: F821 (bound)
    except (KeyError, ValueError):
        path = Path(asset_id)
        return str(path) if path.is_file() else ""
    path = config.partition_dir() / "assets" / Path(record.get("asset_path", "")).name
    return str(path) if path.is_file() else ""


def _presentation_persona_item(raw, store: Store) -> dict:
    item = dict(raw) if isinstance(raw, dict) else {"persona_id": str(raw or "")}
    persona_id = str(item.get("persona_id") or item.get("id") or "")
    persona = store.get_persona(persona_id) or {}
    role = persona.get("role") or {}
    segment = persona.get("segment") or {}
    lens = str(item.get("lens") or item.get("detail") or role.get("title") or "")
    if not lens and segment:
        lens = " · ".join(str(value) for value in list(segment.values())[:2] if value)
    avatar = ""
    avatar_path = (persona.get("avatar") or {}).get("path")
    if avatar_path:
        try:
            from ._snapshots import _avatar_disk_path
            candidate = _avatar_disk_path(avatar_path)
            avatar = str(candidate) if candidate.exists() else ""
        except Exception:
            avatar = ""
    return {
        **item,
        "persona_id": persona_id,
        "name": str(item.get("name") or persona.get("display_name") or persona_id),
        "lens": lens,
        "avatar": avatar,
    }


def _plan_support(slide: dict) -> list[str]:
    values = slide.get("support") or slide.get("items") or []
    out = []
    for value in values:
        if isinstance(value, dict):
            text = value.get("text") or value.get("title") or value.get("label")
        else:
            text = value
        if str(text or "").strip():
            out.append(_strip_md(str(text)))
    return out


def _presentation_plan_slides(report: dict, store: Store, title: str,
                              de: bool) -> list[dict]:
    """Compile a stored semantic plan into the neutral native-PPTX slide model."""
    plan = dict(report.get("presentation_plan") or {})
    project_id = str(report.get("project_id") or "")

    def compile_one(raw: dict) -> dict:
        slide = dict(raw)
        kind = str(slide.get("kind") or "content")
        headline = _strip_md(str(slide.get("headline") or slide.get("title") or ""))
        common = {
            "speaker_notes": dict(slide.get("speaker_notes") or {}),
            "evidence_refs": list(slide.get("evidence_refs") or []),
        }
        if kind == "cover":
            return {**common, "kind": "cover", "logo": True, "canvas": "dawn",
                    "eyebrow": str(slide.get("eyebrow") or "Research presentation"),
                    "title": headline,
                    "subtitle": _strip_md(str(slide.get("subheadline") or
                                              slide.get("subtitle") or plan.get("objective") or "")),
                    "meta": str(slide.get("meta") or
                                f"{plan.get('audience', '')} · {plan.get('duration_minutes', 10)} min"),
                    "date": str(slide.get("date") or report.get("created_at", "")[:10]),
                    "image": _presentation_asset_path(
                        project_id, slide.get("asset_id") or slide.get("image_ref"), store)}
        if kind in {"decision", "insight", "recommendation", "risk"}:
            tone = ("recommendation" if kind in {"decision", "recommendation"}
                    else "risk" if kind == "risk" else "insight")
            return {**common, "kind": tone, "tone": tone,
                    "eyebrow": str(slide.get("eyebrow") or (
                        ("Entscheidung" if de else "Decision") if kind == "decision" else kind)),
                    "statement": headline, "support": _plan_support(slide),
                    "meta": str(slide.get("meta") or "")}
        if kind in {"persona_grid", "persona_detail"}:
            rows = slide.get("items") or slide.get("personas") or slide.get("persona_ids") or []
            return {**common, "kind": kind, "heading": headline,
                    "items": [_presentation_persona_item(row, store) for row in rows],
                    "footnote": str(slide.get("footnote") or "")}
        if kind == "stimulus_comparison":
            panels = []
            for raw_panel in (slide.get("left") or {}, slide.get("right") or {}):
                panel = dict(raw_panel)
                panel["image"] = _presentation_asset_path(
                    project_id, panel.get("asset_id") or panel.get("image_ref") or panel.get("image"), store)
                panels.append(panel)
            return {**common, "kind": kind, "heading": headline,
                    "left": panels[0], "right": panels[1]}
        if kind == "preference_shift":
            return {**common, "kind": kind, "heading": headline,
                    "before": dict(slide.get("before") or {}),
                    "after": dict(slide.get("after") or {}),
                    "switchers": list(slide.get("switchers") or []),
                    "switch_label": str(slide.get("switch_label") or
                                        ("Gewechselt" if de else "Changed"))}
        if kind == "annotated_screen":
            return {**common, "kind": kind, "heading": headline,
                    "image": _presentation_asset_path(
                        project_id, slide.get("asset_id") or slide.get("image_ref") or slide.get("image"), store),
                    "annotations": list(slide.get("annotations") or [])}
        if kind in {"next_steps", "timeline"}:
            return {**common, "kind": "timeline", "heading": headline,
                    "steps": list(slide.get("steps") or slide.get("items") or [])}
        if kind == "source_index":
            return {**common, "kind": "table", "heading": headline,
                    "columns": list(slide.get("columns") or
                                    (["Quelle", "Beitrag"] if de else ["Source", "Contribution"])),
                    "rows": list(slide.get("rows") or [])}
        if kind == "image":
            return {**common, "kind": "image", "heading": headline,
                    "image": _presentation_asset_path(
                        project_id, slide.get("asset_id") or slide.get("image_ref") or slide.get("image"), store),
                    "caption": str(slide.get("caption") or "")}
        if kind == "quote":
            return {**common, "kind": "quote",
                    "text": str(slide.get("text") or headline),
                    "attribution": str(slide.get("attribution") or ""),
                    "role": str(slide.get("role") or "")}
        if kind in {"stats", "summary", "pillars", "voices", "comparison", "table",
                    "chart", "charts", "agenda", "section", "closing"}:
            compiled = {**slide, **common, "kind": kind}
            if kind in {"stats", "summary", "pillars", "voices", "comparison", "table",
                        "chart", "charts", "agenda"}:
                compiled["heading"] = headline
            elif kind in {"section", "closing"}:
                compiled["title"] = headline
            return compiled
        blocks = list(slide.get("blocks") or [])
        if not blocks:
            blocks = _li(_plan_support(slide))
        return {**common, "kind": "content", "heading": headline, "blocks": blocks}

    slides = [compile_one(slide) for slide in (plan.get("slides") or [])]
    appendix = list(plan.get("appendix") or [])
    if appendix:
        slides.append({
            "kind": "section", "num": "A", "title": "Anhang" if de else "Appendix",
            "subtitle": "Vertiefung, Persona-Details und Quellen" if de else
                        "Detail, persona profiles and sources",
            "speaker_notes": {"takeaway": "Appendix", "talk_track":
                              "Use the following slides for questions and evidence detail."},
        })
        slides.extend(compile_one(slide) for slide in appendix)
    return slides


def _analytic_slides(syn: dict, store: Store, L: dict, de: bool, title: str, kind_label: str) -> list[dict]:
    """The analytic-layer deck (convergence synthesis / sectionless project synthesis) built from
    the master template's layout vocabulary (ux-contract §9 V11): a statement verdict + takeaway
    cards instead of the prose wall, sentiment/stance as chart slides, voices as attributed
    quote/voices slides, recommendations as numbered cards plus the effort·value map. Slides carry
    leads, never the full prose — that stays in the report ('details' footnote)."""
    from collections import Counter

    councils = [c for c in (store.get_council_session(cid) for cid in syn.get("council_ids", [])) if c]
    cover = {"kind": "cover", "logo": True, "canvas": "dawn",
             "eyebrow": kind_label, "title": title,
             "subtitle": _strip_md(syn.get("goal", "")),
             "meta": f"{len(councils)} {L['councils_w']}" if councils else "",
             "date": syn.get("created_at", "")[:10]}

    chapters: list[str] = []

    def chap(label: str) -> str:
        chapters.append(label)
        return f"{len(chapters):02d}"

    body: list[dict] = []
    big = _strip_md(syn.get("gesamtbild") or "")
    segs = _label_segments(big)
    kps = _A.finding_texts(syn, "key_problem")

    # 01 · executive summary — the verdict as a STATEMENT slide + the takeaways as cards.
    if big or kps:
        num = chap(L["exec_summary"])
        src_sents = _sentences(segs[0][1] if segs else big)
        statement = _strip_md(kps[0]) if kps else (src_sents[0] if src_sents else "")
        support: list[str] = []
        if kps and big:                       # headline finding + the exec lead as support lines
            lead, _ = _clamp_prose(big, 300)
            support = _sentences(lead)[:2]
        body.append({"kind": "insight", "tone": "insight", "eyebrow": L["verdict"], "num": num,
                     "statement": _clause_cut(statement, 220), "support": support,
                     "footnote": L["details_in_report"]})
        items = []
        if len(segs) >= 2:                    # caps-label spine → labelled takeaway cards
            for i, (label, seg_body) in enumerate(segs[:4]):
                sents = _sentences(seg_body)
                if i == 0 and not kps and len(sents) > 1:   # the verdict consumed sentence one
                    seg_body = " ".join(sents[1:])
                items.append({"title": label, "text": _clamp_prose(seg_body, 230)[0]})
        else:                                 # unstructured prose → one sentence per card
            items = [{"title": "", "text": _clamp_prose(s, 230)[0]}
                     for s in _sentences(big)[1:4] if s]
            if len(items) < 2:
                items = []
        if items:
            body.append({"kind": "summary", "heading": L["exec_summary"], "num": num, "items": items})
        elif big and not kps:                 # no card spine → disciplined lead slide instead
            lead, trunc = _clamp_prose(big, 480)
            body.append({"kind": "content", "num": num, "heading": L["big_picture"],
                         "blocks": [{"type": "p", "text": s} for s in _sentences(lead)],
                         "footnote": L["details_in_report"] if trunc else ""})

    # 02 · sentiment & stance — chart slides over the cited council chain (data already exists).
    votes: Counter = Counter()
    stances: Counter = Counter()
    for c in councils:
        for v in c.get("votes", []):
            st = _A.vote_stance(v)
            if st is not None:
                votes[st["value"]] += 1
        for st in _A.council_statements(c):
            if st.get("stance"):
                stances[int((st["stance"] or {}).get("value") or 0)] += 1
    charts = [(t, ch) for t, ch in ((L["votes_w"].capitalize(), _stance_chart(votes, L, "pie")),
                                    (L["stance_dist"], _stance_chart(stances, L, "bar"))) if ch]
    if charts:
        num = chap(L["sentiment"])
        foot = " · ".join(p for p in (
            f"{sum(votes.values())} {L['votes_w']}" if votes else "",
            f"{sum(stances.values())} {L['contributions_w']}" if stances else "",
            f"{len(councils)} {L['councils_w']}") if p)
        if len(charts) == 2:
            body.append({"kind": "charts", "heading": L["sentiment"], "num": num,
                         "items": [{"title": t, "chart": ch} for t, ch in charts], "footnote": foot})
        else:
            body.append({"kind": "chart", "heading": L["sentiment"], "num": num,
                         "chart": charts[0][1], "footnote": foot})

    # 03 · voices — an anchor quote, then per-persona cards (2 per slide, name + stance + argument).
    stmts = _A.synthesis_statements(syn)
    if stmts:
        num = chap(L["voices_h"])
        quoted = [s for s in stmts
                  if any((r.get("quote") or "").strip() for r in (s.get("refs") or []))]
        if quoted:
            qs = max(quoted, key=lambda s: (abs((s.get("stance") or {}).get("value") or 0),
                                            (s.get("stance") or {}).get("value") or 0))
            qtext = next(r["quote"] for r in qs["refs"] if (r.get("quote") or "").strip())
            meta = qs.get("meta") or {}
            body.append({"kind": "quote", "text": _clause_cut(_strip_md(qtext), 220),
                         "attribution": meta.get("persona_name") or qs.get("persona_id", ""),
                         "role": _clause_cut(_strip_md(meta.get("segment", "")), 60)})
        vitems = []
        for s in stmts:
            meta = s.get("meta") or {}
            val = (s.get("stance") or {}).get("value")
            vitems.append({"name": meta.get("persona_name") or s.get("persona_id", ""),
                           "role": _clause_cut(_strip_md(meta.get("segment", "")), 60),
                           "sentiment": _STANCE_TERM.get(val if val is None else int(val), ""),
                           "sentiment_label": L.get(f"st_{val}", "") if val is not None else "",
                           "text": _clamp_prose(_strip_md(s.get("text", "")), 300)[0]})
        for chunk in _chunks(vitems, 2):
            body.append({"kind": "voices", "heading": L["voices_h"], "num": num, "items": chunk})

    def _cards(kind: str, heading: str, *, limit: int = 200, per: int = 4):
        texts = _A.finding_texts(syn, kind)
        if not texts:
            return
        num = chap(heading)
        cards = []
        for txt in texts:
            head, card_body = _split_card(txt)
            cards.append({"title": head, "text": _clamp_prose(card_body, limit)[0]})
        for chunk in _chunks(cards, per):
            body.append({"kind": "summary", "heading": heading, "num": num, "items": chunk})

    # 04+ · findings as card grids — never bullet walls.
    _cards("key_problem", L["key_problems"])
    _cards("pain_solver", L["pain_solvers"])

    # recommendations — numbered cards (effort·value as quiet card meta) + the effort·value map.
    recs = _A.synthesis_recommendations(syn)
    if recs:
        num = chap(L["recommendations"])
        cards = []
        for i, (txt, e, v) in enumerate(recs, 1):
            head, card_body = _split_card(txt)
            cards.append({"title": f"{i:02d} · {head}" if head else f"{i:02d}",
                          "text": _clamp_prose(card_body, 200)[0],
                          "meta": f"{L['effort']} {e}/5 · {L['value']} {v}/5" if e and v else ""})
        for chunk in _chunks(cards, 4):
            body.append({"kind": "summary", "heading": L["recommendations"], "num": num, "items": chunk})
        chart = _effort_impact_chart(syn)
        if chart:
            body.append({"kind": "chart", "num": num,
                         "heading": f"{L['recommendations']} — {L['effort']} · {L['value']}",
                         "chart": chart})

    # positioning — a disciplined lead (sentence rhythm, clamped), not the full paragraph.
    pos = _strip_md(syn.get("positionierung") or "")
    if pos:
        num = chap(L["positioning"])
        lead, trunc = _clamp_prose(pos, 480)
        body.append({"kind": "content", "num": num, "heading": L["positioning"],
                     "blocks": [{"type": "p", "text": s} for s in _sentences(lead)],
                     "footnote": L["details_in_report"] if trunc else ""})

    _cards("segment", L["segments"])
    _cards("open_question", L["open_questions"], limit=170, per=6)

    slides = [cover]
    if len(chapters) >= 4:                    # the reader's map — only when there is one to draw
        slides.append({"kind": "agenda", "heading": "Inhalt" if de else "Contents", "items": chapters})
    return slides + body


def export_template_deck(out: str = "master-template.pptx") -> dict:
    """Render the deck MASTER TEMPLATE — every layout with its placeholder content (vendored
    _deck.SAMPLE_SLIDES ← sonaloop-design/deck.data.mjs, previewed at #/deck in the design docs)
    — to a real .pptx. The harness demo deck: `sonaloop template-deck` / `make template-deck`."""
    from .. import _deck, _pptx
    if not _pptx.available():
        raise RuntimeError("PPTX export needs the python-pptx package (run `uv sync`).")
    from ._common import write_export_bytes
    data = _pptx.render(_deck.SAMPLE_SLIDES, title=_deck.DECK_TITLE)
    return {"path": write_export_bytes(data, out), "slides": len(_deck.SAMPLE_SLIDES),
            "title": _deck.DECK_TITLE}


def export_synthesis_deliverable(synthesis_id: str, fmt: str, out: str | None = None,
                                 store: Store | None = None,
                                 audience: str = "detailed") -> dict:
    """Render a synthesis as a presentation-grade deliverable file (`pptx`|`pdf`), write it via
    write_export_bytes (a relative/omitted `out` lands under DATA_DIR/exports/ — CWD-independent),
    and — when the synthesis belongs to a project (its own `project_id`, or the plan/graph parent)
    — record the file ON that project as a `direction: out` asset (`source: synthesis:<id>`), so
    what went OUT of the project shows on its page next to the evidence that came in."""
    store = store or Store()
    fmt = (fmt or "").lower()
    if fmt not in ("pptx", "pdf"):
        raise ValueError(f"Unsupported deliverable format {fmt!r} (pptx|pdf).")
    syn = get_synthesis(synthesis_id, store)
    if audience not in {"detailed", "stakeholder", "presentation"}:
        raise ValueError("audience must be detailed|stakeholder|presentation")
    if fmt == "pptx":
        data = export_synthesis_pptx(synthesis_id, store=store)
    elif audience == "stakeholder":
        data = export_synthesis_pdf(  # noqa: F821 (bound)
            synthesis_id, store=store, audience="stakeholder")
    else:
        # Preserve the original call shape for registered/legacy PDF providers.
        data = export_synthesis_pdf(synthesis_id, store=store)  # noqa: F821 (bound)
    path = write_export_bytes(data, out or f"{synthesis_id}.{fmt}")         # noqa: F821 (bound)
    # The hand-off contract: a server filesystem path means nothing to a remote (MCP)
    # user — `url` is the auth-gated download link ('' only for an out path outside
    # the served /data tree); the asset URL below supersedes it once attached.
    result = {"synthesis_id": syn["id"], "format": fmt, "path": path, "bytes": len(data),
              "url": export_download_url(path)}                             # noqa: F821 (bound)
    proj = (store.get_research_project(syn["project_id"]) if syn.get("project_id")
            else owning_project_of_synthesis(synthesis_id, store=store))    # noqa: F821 (bound)
    if proj:
        from ..correlation import stamp_workflow_trace
        stamp_workflow_trace(result, proj)
        rec = attach_asset(proj["id"], path=path, kind="document",          # noqa: F821 (bound)
                           title=f'{syn.get("title") or synthesis_id} ({fmt.upper()})',
                           source=f"synthesis:{synthesis_id}", direction="out", store=store)
        # A deliverable's identity is (synthesis, format), not its bytes: renders are not
        # byte-stable, so each re-export gets a fresh content hash and attach_asset's
        # bytes-keyed upsert can't see the previous record — supersede it here, and RECORD
        # the chain on the survivor (UX U8: the asset's provenance block shows which earlier
        # versions this export replaced; a stale record's own chain is inherited).
        replaced: list[dict] = []
        for stale in list_assets(proj["id"], store=store):                  # noqa: F821 (bound)
            if (stale["id"] != rec["id"] and stale.get("source") == f"synthesis:{synthesis_id}"
                    and stale.get("filename", "").lower().endswith(f".{fmt}")):
                replaced += (stale.get("supersedes") or []) + [
                    {"id": stale["id"], "filename": stale.get("filename", ""),
                     "created_at": stale.get("created_at", "")}]
                remove_asset(proj["id"], stale["id"], store=store)          # noqa: F821 (bound)
        if replaced:
            rec = record_asset_supersession(proj["id"], rec["id"], replaced, store=store)  # noqa: F821 (bound)
        result["project_id"], result["asset_id"] = proj["id"], rec["id"]
        result["url"] = web_url(rec["url"])                                 # noqa: F821 (bound)
        result["project_url"] = web_url(f'/jobs/{proj["id"]}')  # noqa: F821 (bound)
    from ..telemetry import capture_product_event
    from ..theming import active_runtime_design_system_context
    runtime = active_runtime_design_system_context()
    capture_product_event(
        "report_exported",
        project_id=str((proj or {}).get("id") or ""),
        subject_kind="report",
        subject_id=syn["id"],
        properties={
            "export_format": fmt,
            "audience": audience,
            "branding_source": "workspace" if (runtime or {}).get("workspace_id") else "default",
            "master_source": "uploaded" if (runtime or {}).get("deck_master_bytes") else "default",
        },
    )
    return result


def export_synthesis_pptx(synthesis_id: str, store: Store | None = None,
                          master_template: bytes | None = None) -> bytes:
    """Render ANY report (synthesis) as a native PowerPoint deck: a title slide + one slide per section
    (project scope) or per analytic layer (convergence scope), with native charts. Raises if the
    python-pptx package is unavailable (it degrades gracefully at the call sites)."""
    from .. import _pptx
    if not _pptx.available():
        raise RuntimeError("PPTX export needs the python-pptx package (run `uv sync`).")
    store = store or Store()
    syn = get_synthesis(synthesis_id, store)
    de = content_language() == "de"
    L = _SYNTHESIS_EXPORT_LABELS[content_language()]
    title = syn.get("title", "")
    for suffix in (" — Report", " — Meta-Report"):
        if title.endswith(suffix):
            title = title[:-len(suffix)]
            break
    kind_label = "Report"
    slides: list[dict] = []

    secs = syn.get("sections", [])
    if syn.get("presentation_plan"):
        slides = _presentation_plan_slides(syn, store, title, de)
    # A project synthesis without report sections (report flow never run) still has the
    # analytic layers — fall through to that deck instead of an empty cover+closing shell.
    elif syn.get("scope") == "project" and secs:
        meta = f"{len(secs)} {'Abschnitte' if de else 'sections'}"
        headings = [_presentation_section_heading(sec, idx, len(secs), de)
                    for idx, sec in enumerate(secs, 1)]
        slides.append({"kind": "cover", "logo": True, "canvas": "dawn",
                       "eyebrow": kind_label, "title": title,
                       "subtitle": _report_cover_lead(syn, secs, de), "meta": meta,
                       "date": syn.get("created_at", "")[:10]})
        if len(secs) >= 3:  # the reader's map — only when there are chapters to map
            slides.append({"kind": "agenda", "heading": "Inhalt" if de else "Contents",
                           "items": headings})
        for idx, sec in enumerate(secs, 1):
            figs = sec.get("figures") or []
            charts = [c for c in (_figure_to_chart(f, store) for f in figs) if c]
            images = [im for im in (_figure_image(f, store) for f in figs) if im]
            blocks, clipped = _budget_blocks(_md_blocks(sec.get("markdown", "")))
            count = len(set(sec.get("source_study_ids") or []))
            source_label = (
                f"{count} {'Quelle' if count == 1 else 'Quellen'}" if de else
                f"{count} {'source' if count == 1 else 'sources'}")
            if clipped and count:
                footnote = (f"Details und {source_label} im vollständigen Report" if de else
                            f"Details and {source_label} in the full report")
            elif clipped:
                footnote = L["details_in_report"]
            elif count:
                footnote = (f"{source_label} im vollständigen Report" if de else
                            f"{source_label} in the full report")
            else:
                footnote = ""
            slides.append({"kind": "content", "num": f"{idx:02d}", "heading": headings[idx - 1],
                           "blocks": blocks,
                           "chart": charts[0] if charts else None, "footnote": footnote})
            for c in charts[1:]:
                slides.append({"kind": "content", "num": f"{idx:02d}", "heading": headings[idx - 1],
                               "blocks": [], "chart": c})
            for path, cap in images:   # prototype screenshots / images / avatars — one slide each, fitted
                slides.append({"kind": "image", "num": f"{idx:02d}", "heading": headings[idx - 1],
                               "image": path, "caption": cap})
    else:
        slides.extend(_analytic_slides(syn, store, L, de, title, kind_label))

    if not syn.get("presentation_plan"):
        slides.append({"kind": "closing", "logo": True,
                       "title": "Vielen Dank" if de else "Thank you",
                       "text": "",
                       "meta": f"{kind_label} · {title} · {syn.get('created_at', '')[:10]}"})
    return _pptx.render(slides, title=title or kind_label,
                        master_template=master_template)
