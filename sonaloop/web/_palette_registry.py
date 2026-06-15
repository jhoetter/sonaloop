"""Cmd+K coverage registry — ONE source of truth for what the palette can reach
(ticket cmdk-registry-driven-coverage).

Two enumerations, consumed by BOTH /api/search and the palette's static commands, and
guarded by the canary (tests/test_palette_coverage.py — the "palette fell behind" gate,
the house pattern of the presence contract / i18n parity):

  - SEARCH_SOURCES: every searchable entity type — its localized group label, icon,
    palette dot color, the detail-route prefix its results link to, and a rows(store)
    reader yielding (title, subtitle, url). /api/search iterates THIS; the palette's
    group labels/icons/order are generated from it. Adding an entity type here is the
    whole job — search, grouping and styling follow.
  - nav_commands(): the palette's jump commands, derived from the NAV REGISTRY
    (web/_ext.nav_model — core seeds + extension items, so a downstream package's nav
    entry becomes a palette command automatically), plus the chrome surfaces that have
    no route of their own (the ? cheat sheet, the settings popover — '#'-href commands
    the chrome JS handles).

The explicit, reasoned opt-outs the canary honors — silence is never an excuse:

  - NON_SEARCHABLE_ROUTES: detail routes (/{prefix}/{id}) that are deliberately not
    entity search targets, each with the reason.
  - KIND_SEARCH: every presence-contract kind (web/_presence.REGISTRY) mapped to its
    search source — or to NotSearchable(reason) when it has no detail route to land on.

The entity kinds deliberately REUSE the presence contract's inventory rather than
inventing a second registry: _presence.REGISTRY stays the list of what exists,
KIND_SEARCH only declares how each kind reaches the palette."""
from __future__ import annotations

import difflib
import unicodedata
from typing import Any, Callable, Iterator

from ..storage import Store
from ._i18n import t

# (title, desc, url, date) — desc is the OWNING PROJECT title wherever the kind has one
# (the row's context line, ux-contract §9 V6), date is the compact '11 Jun' day for the
# right-aligned meta (ui.fmt_day — the ONE row date format, C5/C10).
Row = tuple[str, str, str, str]


def fold(s: Any) -> str:
    """Case- and diacritic-insensitive search form (the V1 `?q=` helper, shared here so the
    palette and the outline filter can never diverge): NFKD-decompose, drop combining marks,
    casefold — "über"/"UEBER"/"Uber…" all meet at "uber"."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(s))
                   if not unicodedata.combining(c)).casefold()


class SearchSource:
    """One searchable entity type. `label` is a lambda (resolves per request — i18n);
    `rows(store)` yields (title, subtitle, url); `url_prefix` is the detail-route
    prefix the canary maps routes onto."""

    def __init__(self, label: Callable[[], str], icon: str, color: str,
                 url_prefix: str, rows: Callable[[Store], Iterator[Row]]):
        self.label, self.icon, self.color = label, icon, color
        self.url_prefix, self.rows = url_prefix, rows


class NotSearchable:
    """Explicit 'this kind has no palette search target' declaration, with the reason
    (where its signal lives instead)."""

    def __init__(self, reason: str):
        self.reason = reason


# ------------------------------------------------------------------ the row readers

def _ptitles(store: Store) -> dict[str, str]:
    """{project_id: title} — every reader's context line resolves through this one map."""
    return {p["id"]: p.get("title", "") for p in store.list_research_projects()}


def _date(rec: dict, key: str = "created_at") -> str:
    from .ui import fmt_day
    return fmt_day(rec.get(key) or "")


def _project_rows(store: Store) -> Iterator[Row]:
    for p in store.list_research_projects():
        yield p.get("title", ""), (p.get("goal", "") or "")[:90], f'/projects/{p["id"]}', _date(p)


def _persona_rows(store: Store) -> Iterator[Row]:
    for p in store.list_personas():
        role = p.get("role")
        role_t = role.get("title", "") if isinstance(role, dict) else (role or "")
        yield p.get("display_name", ""), role_t, f'/personas/{p["id"]}', _date(p)


def _council_rows(store: Store) -> Iterator[Row]:
    titles = _ptitles(store)
    for c in store.list_council_sessions():
        yield (c.get("prompt", ""), titles.get(c.get("project_id") or "", ""),
               f'/councils/{c["id"]}', _date(c))


def _synthesis_rows(store: Store) -> Iterator[Row]:
    # a synthesis is owned FROM the project side (study_ids) — older records may also
    # carry their own project_id; honor both.
    titles = _ptitles(store)
    owner = {sid: p.get("title", "") for p in store.list_research_projects()
             for sid in p.get("study_ids") or []}
    for sy in store.list_syntheses():
        proj = titles.get(sy.get("project_id") or "", "") or owner.get(sy.get("id"), "")
        yield sy.get("title", ""), proj, f'/syntheses/{sy["id"]}', _date(sy)


def _prototype_rows(store: Store) -> Iterator[Row]:
    titles = _ptitles(store)
    for pr in store.list_prototypes():
        yield (pr.get("name", ""), titles.get(pr.get("project_id") or "", "") or (pr.get("version") or ""),
               f'/prototypes/{pr["slug"]}', _date(pr))


def _section_rows(store: Store) -> Iterator[Row]:
    from .. import services
    for proj in store.list_research_projects():
        for sec in services.list_sections(proj["id"], store=store):
            yield sec.get("title", ""), proj.get("title", ""), f'/sections/{sec["id"]}', _date(sec)


def _note_rows(store: Store) -> Iterator[Row]:
    # ONE note entity — observations, concepts AND idea notes (kind discriminators on
    # the note primitive), so /notes/{id} ideas are searchable without a second source.
    from .. import services
    for proj in store.list_research_projects():
        for nt in services.list_notes(proj["id"], store=store):
            yield nt.get("title", ""), proj.get("title", ""), f'/notes/{nt["id"]}', _date(nt)


def _session_rows(store: Store) -> Iterator[Row]:
    titles = _ptitles(store)
    for s in store.list_usability_sessions():
        subj = s.get("subject") or {}
        yield ((subj.get("label") or s.get("id", "")), titles.get(s.get("project_id") or "", ""),
               f'/sessions/{s["id"]}', _date(s, "date"))


def _hypothesis_rows(store: Store) -> Iterator[Row]:
    titles = _ptitles(store)
    for hx in store.list_hypotheses():
        yield (hx.get("text", ""), titles.get(hx.get("project_id") or "", ""),
               f'/hypotheses/{hx["id"]}', _date(hx))


def _decision_rows(store: Store) -> Iterator[Row]:
    titles = _ptitles(store)
    for d in store.list_decisions():
        yield (d.get("title", ""), titles.get(d.get("project_id") or "", ""),
               f'/decisions/{d["id"]}', _date(d))


def _survey_rows(store: Store) -> Iterator[Row]:
    titles = _ptitles(store)
    for sv in store.list_surveys():
        yield (sv.get("title", ""), titles.get(sv.get("project_id") or "", ""),
               f'/surveys/{sv["id"]}', _date(sv))


def _asset_rows(store: Store) -> Iterator[Row]:
    # Assets ride the project record (no global list read) — the same scan the /assets/{id}
    # route resolves through (web/pages/assets.find_asset).
    for proj in store.list_research_projects():
        for a in proj.get("assets") or []:
            yield ((a.get("title") or a.get("filename", "")), proj.get("title", ""),
                   f'/assets/{a["id"]}', _date(a))


def _open_question_rows(store: Store) -> Iterator[Row]:
    for proj in store.list_research_projects():
        for o in store.list_open_questions(proj["id"]):
            yield o.get("text", ""), proj.get("title", ""), f'/open-questions/{o["id"]}', _date(o)


def _reference_rows(store: Store) -> Iterator[Row]:
    for proj in store.list_research_projects():
        for a in proj.get("artifacts") or []:
            yield (a.get("title") or a.get("url", ""), proj.get("title", ""),
                   f'/references/{a["id"]}', _date(a))


def _flow_rows(store: Store) -> Iterator[Row]:
    from .. import services
    for proj in store.list_research_projects():
        for fl in services.list_flows(proj["id"], store=store):
            yield fl.get("title", ""), proj.get("title", ""), f'/playbooks/{fl["id"]}', _date(fl, "updated_at")


# ------------------------------------------------- the searchable entity types (ordered)

SEARCH_SOURCES: dict[str, SearchSource] = {
    "project": SearchSource(lambda: t("projects"), "projects", "#7a5ed1", "/projects", _project_rows),
    "persona": SearchSource(lambda: t("personas"), "personas", "#3d7fc4", "/personas", _persona_rows),
    "council": SearchSource(lambda: t("councils"), "councils", "var(--accent)", "/councils", _council_rows),
    "synthesis": SearchSource(lambda: t("syntheses"), "syntheses", "#9a8cff", "/syntheses", _synthesis_rows),
    "prototype": SearchSource(lambda: t("prototypes_h"), "prototype", "#00897b", "/prototypes", _prototype_rows),
    "flow": SearchSource(lambda: t("flows_h"), "compass", "#0f9d8f", "/playbooks", _flow_rows),
    "session": SearchSource(lambda: t("sessions"), "activity", "#4a7d7d", "/sessions", _session_rows),
    "survey": SearchSource(lambda: t("surveys_h"), "clipboard", "#00798c", "/surveys", _survey_rows),
    "hypothesis": SearchSource(lambda: t("hypotheses_h"), "target", "#c0760a", "/hypotheses", _hypothesis_rows),
    "decision": SearchSource(lambda: t("decisions_h"), "flag", "#d81b60", "/decisions", _decision_rows),
    "section": SearchSource(lambda: t("sections"), "squareGrid", "#3d9b6b", "/sections", _section_rows),
    "note": SearchSource(lambda: t("notes_h"), "panel", "#b87a25", "/notes", _note_rows),
    "asset": SearchSource(lambda: t("assets_h"), "file", "#8a6d3b", "/assets", _asset_rows),
    "reference": SearchSource(lambda: t("references_h"), "link", "#3a7bd5", "/references", _reference_rows),
    "open_question": SearchSource(lambda: t("open_questions_h"), "help", "#9aa0a6", "/open-questions",
                                  _open_question_rows),
}


def search_rows(q: str, store: Store | None = None, per_kind: int = 6) -> list[dict[str, Any]]:
    """The /api/search read (UX V6): diacritic-/case-insensitive title match across every
    SEARCH_SOURCES type, ranked title-prefix > word-prefix > substring (shorter titles first
    within a rank), capped at `per_kind` rows per type so the response stays palette-sized
    and fast no matter how big the store grows. Rows stay grouped in SEARCH_SOURCES order —
    the palette renders the groups as-is. A broken source is skipped (fail-soft) — the
    canary, not the request, polices gaps."""
    qf = fold((q or "").strip())
    if not qf:
        return []
    store = store or Store()
    out: list[dict[str, Any]] = []
    for typ, src in SEARCH_SOURCES.items():
        try:
            rows = list(src.rows(store))
        except Exception:  # noqa: BLE001
            continue
        hits: list[tuple[int, int, dict[str, Any]]] = []
        for title, desc, url, date in rows:
            tf = fold(title)
            if not title or qf not in tf:
                continue
            rank = (0 if tf.startswith(qf)
                    else 1 if any(w.startswith(qf) for w in tf.split()) else 2)
            hits.append((rank, len(title),
                         {"type": typ, "title": title,
                          "subtitle": desc if isinstance(desc, str) else "",
                          "url": url, "date": date or ""}))
        hits.sort(key=lambda x: (x[0], x[1]))
        out.extend(hit for _r, _l, hit in hits[:per_kind])
    return out


def closest_rows(q: str, store: Store | None = None, limit: int = 4) -> list[dict[str, Any]]:
    """Nearest hits for a query that matched NOTHING (the DS site's ⌘K "Closest matches"
    rail, ticket ds-cmdk-synonym-search): normalized similarity (difflib ratio — Levenshtein
    family) of the folded query against every entity title AND its words, threshold ≥ .55.
    Only called on the empty-result path, so the extra scan never taxes live typing."""
    qf = fold((q or "").strip())
    if not qf:
        return []
    store = store or Store()
    scored: list[tuple[float, dict[str, Any]]] = []
    for typ, src in SEARCH_SOURCES.items():
        try:
            rows = list(src.rows(store))
        except Exception:  # noqa: BLE001
            continue
        for title, desc, url, date in rows:
            tf = fold(title)
            if not tf:
                continue
            score = max(difflib.SequenceMatcher(None, qf, cand).ratio()
                        for cand in [tf, *tf.split()])
            if score >= 0.55:
                scored.append((score, {"type": typ, "title": title,
                                       "subtitle": desc if isinstance(desc, str) else "",
                                       "url": url, "date": date or ""}))
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for _score, row in scored:
        if row["url"] in seen:
            continue
        seen.add(row["url"])
        out.append(row)
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------- the jump commands

def palette_nav() -> list[dict[str, Any]]:
    """The palette's STRUCTURED Navigate model (ux-contract §9 V6 + C10): every registered
    nav item (core seeds AND extension registrations — the nav registry stays the source of
    truth) with its icon, then the chrome/footer surfaces (Settings popover on '#settings',
    Documentation, the ? cheat sheet on '#shortcuts') and the /runs journal. The Library's
    kind lists are NOT flat top-level commands anymore — they ride the /library item as
    `children` (rendered as one expandable "Library" entry; each child stays individually
    matchable when typing). `quiet` items skip the empty-state listing but stay searchable
    (Runs was deliberately retired from the IA — it must not look like nav again)."""
    from ._ext import nav_model, resolve_label
    from .pages.library import LIBRARY_TABS   # late: pages import web modules, not vice versa
    items: list[dict[str, Any]] = []
    for _sec, navitems in nav_model():
        for it in navitems:
            entry: dict[str, Any] = {"title": resolve_label(it["label"]), "url": it["href"],
                                     "icon": it.get("icon") or "arrowRight"}
            if it["href"] == "/library":
                entry["children"] = [{"title": label(), "url": route, "icon": icon}
                                     for _k, route, icon, label, *_rest in LIBRARY_TABS]
            items.append(entry)
    items += [
        {"title": t("settings"), "url": "#settings", "icon": "settings"},
        {"title": t("documentation"), "url": "/documentation", "icon": "overview"},
        {"title": t("kbd_cheatsheet_h"), "url": "#shortcuts", "icon": "command"},
        {"title": t("runs_h"), "url": "/runs", "icon": "play", "quiet": True},
    ]
    return items


def nav_commands() -> list[dict[str, str]]:
    """The FLAT jump-command list — the coverage canary's truth, derived from palette_nav()
    (one structure feeds both the rendered palette and the canary, so they cannot drift):
    every nav item, every Library kind list, /runs, /documentation, '#shortcuts', '#settings'."""
    cmds: list[dict[str, str]] = []
    for it in palette_nav():
        cmds.append({"title": it["title"], "url": it["url"], "type": "go"})
        cmds += [{"title": c["title"], "url": c["url"], "type": "go"}
                 for c in it.get("children", ())]
    return cmds


# ------------------------------------------------------- the canary's reasoned opt-outs

# Detail routes (GET /{prefix}/{param}) that are deliberately NOT entity-search targets.
NON_SEARCHABLE_ROUTES: dict[str, str] = {
    "/activities": "one simulated calendar activity of one persona — reached from the persona's "
                   "calendar; far too granular for a global jump target",
    "/documentation": "the curated docs hub — the nav-derived 'Documentation' jump command covers "
                      "it; full-text doc search is not entity search",
    "/flows": "legacy alias for playbook detail routes — entity search targets /playbooks",
    "/sessions-files": "static passthrough for recorded session assets (screenshots), not an entity",
}

# Every presence-contract kind (web/_presence.REGISTRY — the existing entity-kind
# inventory, reused instead of duplicated) → its search source, or why it has none.
KIND_SEARCH: dict[str, str | NotSearchable] = {
    "council": "council",
    "synthesis": "synthesis",
    "report": "synthesis",       # a report IS a project-scope synthesis; list_syntheses carries it
    "note": "note",              # observations/concepts/ideas — kind discriminators on one primitive
    "prototype": "prototype",
    "session": "session",
    "section": "section",
    "hypothesis": "hypothesis",
    "decision": "decision",
    "survey": "survey",
    "flow": "flow",
    "url_artifact": "reference",
    "open_question": "open_question",
    "asset": "asset",            # the U8 detail surface: /assets/{id}, global id resolution
}
