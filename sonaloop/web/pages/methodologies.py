"""Methodology browser: the process layer a project can run through."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from ._ctx import *  # noqa: F401,F403

from ... import job_taxonomy, methodology as _methodology
from .._html import register_css


register_css(
    ".sl-meth-hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,420px);gap:24px;align-items:start;margin:6px 0 22px}"
    ".sl-meth-lede{max-width:78ch}"
    ".sl-meth-index{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}"
    # The index card mirrors the detail head (Notion anatomy): a full-bleed cover on top, the
    # icon floating over its bottom-left edge, then name -> description -> badges below.
    ".sl-meth-card{display:block;text-decoration:none;color:inherit;padding:0;overflow:hidden}"
    ".sl-meth-card:hover{border-color:color-mix(in srgb,var(--accent) 42%,var(--line))}"
    ".sl-meth-card-cover{display:block;height:132px;overflow:hidden;background:var(--panel-2);border-bottom:1px solid var(--line)}"
    ".sl-meth-card-cover img{width:100%;height:100%;object-fit:cover;display:block}"
    ".sl-meth-card-ico{position:relative;z-index:1;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;margin:14px 0 0 14px;border-radius:12px;background:var(--panel);border:1px solid var(--line);color:var(--accent)}"
    ".sl-meth-card-ico svg{width:24px;height:24px}"
    ".sl-meth-card-ico--float{margin-top:-22px;box-shadow:0 3px 12px color-mix(in srgb,var(--ink) 12%,transparent)}"
    ".sl-meth-card-body{display:block;padding:6px 14px 14px}"
    ".sl-meth-card h2{font-size:var(--t-md);line-height:1.25;margin:0 0 4px;font-weight:650}"
    ".sl-meth-card p{margin:0;color:var(--muted);line-height:1.4}"
    ".sl-meth-card-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}"
    # Notion-style document head: a full-width brand cover banner, then the methodology icon
    # overlapping its bottom-left edge (sl-meth-ico--float), then the standard hero (eyebrow,
    # title, description). The cover replaces the old aside cover/figure/step-viz.
    ".sl-meth-doc-head{margin:0 0 4px}"
    ".sl-meth-banner{height:180px;border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);background:var(--panel-2)}"
    ".sl-meth-banner img{width:100%;height:100%;object-fit:cover;display:block}"
    # Theme-aware cover: light variant by default; the dark twin only under system-dark
    # (no explicit data-theme) or an explicit dark theme. Mirrors the token theme rules.
    ".sl-meth-banner .b-dark,.sl-meth-card-cover .b-dark{display:none}"
    "@media(prefers-color-scheme:dark){"
    ":root:not([data-theme]) .sl-meth-banner .b-light,:root:not([data-theme]) .sl-meth-card-cover .b-light{display:none}"
    ":root:not([data-theme]) .sl-meth-banner .b-dark,:root:not([data-theme]) .sl-meth-card-cover .b-dark{display:block}}"
    ":root[data-theme=dark] .sl-meth-banner .b-light,:root[data-theme=dark] .sl-meth-card-cover .b-light{display:none}"
    ":root[data-theme=dark] .sl-meth-banner .b-dark,:root[data-theme=dark] .sl-meth-card-cover .b-dark{display:block}"
    ".sl-meth-ico{display:inline-flex;align-items:center;justify-content:center;width:60px;height:60px;border-radius:16px;background:var(--panel);border:1px solid var(--line);color:var(--accent)}"
    ".sl-meth-ico svg{width:32px;height:32px}"
    ".sl-meth-ico--float{position:relative;z-index:1;margin:-30px 0 0 20px;box-shadow:0 4px 16px color-mix(in srgb,var(--ink) 12%,transparent)}"
    ".sl-meth-doc-head .sl-page-header{margin:10px 0 0}"
    ".sl-meth-bands{display:grid;gap:8px;margin-top:18px}"
    ".sl-meth-band{display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;padding:12px 0;border-top:1px solid var(--line)}"
    ".sl-meth-band b{font-size:var(--t-sm)}"
    ".sl-meth-band span{color:var(--muted);line-height:1.45}"
    ".sl-meth-steps{display:grid;gap:10px}"
    ".sl-meth-step{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel)}"
    ".sl-meth-step-n{width:28px;height:28px;border-radius:999px;background:var(--panel-2);display:inline-flex;align-items:center;justify-content:center;font-size:var(--t-xs);font-family:var(--mono);color:var(--accent)}"
    ".sl-meth-step h3{margin:0 0 4px;font-size:var(--t-md)}"
    ".sl-meth-step p{margin:0;color:var(--muted);line-height:1.45}"
    ".sl-meth-guide{display:grid;gap:6px;margin-top:10px}"
    ".sl-meth-guide-row{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}"
    ".sl-meth-guide-row b{min-width:62px;color:var(--muted);font-size:var(--t-xs);line-height:1.9;text-transform:uppercase;letter-spacing:.08em}"
    ".sl-meth-chips{display:flex;gap:6px;flex-wrap:wrap}"
    ".sl-meth-jobprops{display:grid;gap:12px}"
    ".sl-meth-jobprop b{display:block;font-weight:600;line-height:1.3;margin-bottom:2px}"
    ".sl-meth-jobprop span{color:var(--muted);line-height:1.45;font-size:var(--t-sm)}"
    "@media(max-width:980px){.sl-meth-hero{grid-template-columns:1fr}.sl-meth-band{grid-template-columns:1fr}}"
)

_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "methodologies"


@lru_cache(maxsize=32)
def _asset_src(name: str) -> str:
    if not name or Path(name).name != name:
        return ""
    path = _ASSET_DIR / name
    if not path.is_file():
        return ""
    return f"/web-assets/methodologies/{quote(name)}"


def _slug(key: str) -> str:
    return key.replace("_", "-")


def _spec_for(slug: str, store: Store) -> dict | None:
    key = slug.replace("-", "_")
    reg = _methodology.registry(store)
    return reg.get(key) or reg.get(slug)


def _meta(spec: dict) -> dict:
    own = spec.get("presentation") or {}
    return {"icon": "target", "summary": spec.get("description", ""), "jobs": spec.get("when_to_use", ""),
            "image": "", "figure": "", "complexity": ""} | own


# How heavy a methodology is — the spectrum from a quick reaction read to a deep study. Drives
# the card badge, an aside property and a filter facet, and orders the index light -> deep.
_COMPLEXITY_ORDER = {"light": 0, "medium": 1, "deep": 2}
_COMPLEXITY_COLOR = {"light": "var(--green)", "medium": "var(--amber)", "deep": "var(--violet)"}


def _complexity_label(c: str) -> str:
    return t(f"complexity_{c}") if c in _COMPLEXITY_ORDER else ""


def _image(spec: dict) -> str:
    return _asset_src(str(_meta(spec).get("image") or ""))


def _image_dark(spec: dict) -> str:
    """The dark-theme twin of the cover (`<stem>-dark<ext>`), or "" if none is vendored."""
    name = str(_meta(spec).get("image") or "")
    if not name:
        return ""
    p = Path(name)
    return _asset_src(f"{p.stem}-dark{p.suffix}")


def _cover_inner(spec: dict):
    """The cover's <img>(s): always the light variant, plus the dark twin when present. CSS
    (`.b-light`/`.b-dark` + the theme rules) shows the right one per active theme. None when the
    methodology has no cover image."""
    light = _image(spec)
    if not light:
        return None
    dark = _image_dark(spec)
    attrs = {"loading": "lazy", "decoding": "async", "alt": ""}
    return fragment(h("img", {"class_": "b-light", "src": light, **attrs}),
                    h("img", {"class_": "b-dark", "src": dark, **attrs}) if dark else None)


def _doc_head(spec: dict, meta: dict, title: str) -> str:
    """Notion-style document head: brand cover banner -> floating icon -> hero (eyebrow,
    title, description). When the methodology has no cover image the icon renders inline
    (no overlap), so the head still reads as a normal hero."""
    cover = _cover_inner(spec)
    banner = h("div", {"class_": "sl-meth-banner"}, cover) if cover else None
    ico = h("span", {"class_": "sl-meth-ico" + (" sl-meth-ico--float" if cover else "")},
            raw(_icon(meta["icon"])))
    desc = spec.get("description", "")
    # No kind eyebrow here: the breadcrumb already states "Methodologies", so a "Methodology"
    # chip over the title is redundant (round-2 feedback).
    header = h("div", {"class_": "sl-page-header"},
               h("div", {"class_": "sl-page-header__main"},
                 h("h1", {"class_": "sl-page-header__title", "title": title}, title),
                 h("p", {"class_": "sl-page-header__sub"}, desc) if desc else None))
    return h("div", {"class_": "sl-meth-doc-head"}, banner, ico, header)


def _guide_row(label: str, items: list[str], color: str) -> str:
    if not items:
        return ""
    return h("div", {"class_": "sl-meth-guide-row"},
             h("b", {}, label),
             h("span", {"class_": "sl-meth-chips"},
               fragment(*(raw(_label(item, color)) for item in items))))


def _stage_guide(st: dict) -> str:
    # One unified row (round-2 feedback): name only the library artifacts a stage produces,
    # under a single "Formats" label — the separate, redundant Formats/Council row is dropped.
    pres = st.get("presentation") or {}
    library = [str(x) for x in (pres.get("library") or pres.get("artifacts") or []) if str(x).strip()]
    if not library:
        return ""
    de = _lang() == "de"
    return h("div", {"class_": "sl-meth-guide"},
             raw(_guide_row("Formate" if de else "Formats", library, "var(--accent)")))


def _projects_using(key: str, store: Store) -> list[dict]:
    """Research projects whose methodology resolves to this spec — by the project's own
    methodology key or via a job framework that maps to it. The methodology lives on the plan
    (the list dict omits it), so we read plan.methodology first, like the projects page does.
    Returns [] when none use it."""
    if not key:
        return []
    from ... import plan as _plan
    fw_ids = {fw.get("id") for fw in job_taxonomy.frameworks() if fw.get("methodology_key") == key}
    out = []
    for p in services.list_research_projects(store=store):
        pk = (p.get("methodology") or "").strip()
        if not pk:
            try:
                pk = ((_plan.get_plan(p["id"], store=store) or {}).get("methodology") or "").strip()
            except Exception:
                pk = ""
        if pk and (pk == key or pk in fw_ids):
            out.append(p)
    return out


def _usage_counts(store: Store) -> dict[str, int]:
    """How many research projects (jobs) actually RUN each methodology, keyed by methodology key.
    Resolves a project's methodology from plan.methodology (the list dict omits it), normalising a
    job-framework id to its methodology key. One pass over all projects — used by the index cards."""
    from ... import plan as _plan
    fw_key = {fw.get("id"): fw.get("methodology_key") for fw in job_taxonomy.frameworks()}
    counts: dict[str, int] = {}
    for p in services.list_research_projects(store=store):
        pk = (p.get("methodology") or "").strip()
        if not pk:
            try:
                pk = ((_plan.get_plan(p["id"], store=store) or {}).get("methodology") or "").strip()
            except Exception:
                pk = ""
        if not pk:
            continue
        key = fw_key.get(pk, pk)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _jobs_for(key: str) -> list[dict]:
    ids = []
    for fw in job_taxonomy.frameworks():
        if fw.get("methodology_key") == key:
            ids.append(fw.get("id"))
    return [j for j in job_taxonomy.jobs() if any(fw in ids for fw in j.get("frameworks", []))]


def _used_in_label(n: int) -> str:
    """Compact, grammatical badge for real usage (singular vs plural)."""
    return t("used_in_one_job") if n == 1 else t("n_used_in_jobs", n=n)


def _job_types_label(n: int) -> str:
    return t("one_job_type") if n == 1 else t("n_job_types", n=n)


def _meth_card(spec: dict, jobs: list[dict], used: int) -> str:
    """One index card — Notion anatomy: cover on top, floating icon over its edge, then
    name -> description -> three badges (formats · job types · real usage)."""
    meta = _meta(spec)
    cover = _cover_inner(spec)
    cx = meta["complexity"]
    badges = []
    if cx in _COMPLEXITY_ORDER:
        badges.append(raw(_label(_complexity_label(cx), _COMPLEXITY_COLOR[cx])))
    # The same four badges on EVERY card (consistency over hiding zeros): complexity · formats ·
    # job types · real usage.
    badges += [raw(_label(t("n_formats", n=len(spec.get("steps") or [])), "var(--accent)")),
               raw(_label(_job_types_label(len(jobs)), "var(--blue)")),
               raw(_label(_used_in_label(used), "var(--muted)"))]
    return h("a", {"class_": "sl-card sl-meth-card", "href": f"/methodologies/{_slug(spec.get('key', ''))}"},
             h("span", {"class_": "sl-meth-card-cover"}, cover) if cover else None,
             h("span", {"class_": "sl-meth-card-ico" + (" sl-meth-card-ico--float" if cover else "")},
               raw(_icon(meta["icon"]))),
             h("span", {"class_": "sl-meth-card-body"},
               h("h2", {}, spec.get("name", "")),
               h("p", {}, meta["summary"]),
               h("span", {"class_": "sl-meth-card-meta"}, fragment(*badges))))


def _methodologies_page(q: str = "", job_type: str = "", complexity: str = "") -> str:
    from urllib.parse import quote
    from collections import Counter
    from .._filterbar import filter_bar, parse_multi, empty_filter_state
    store = Store()
    # Order light -> deep, then by name — so the index reads as a spectrum from a quick
    # reaction read down to a deep study.
    specs = sorted(_methodology.registry(store).values(),
                   key=lambda s: (_COMPLEXITY_ORDER.get(_meta(s)["complexity"], 1), s.get("name", "")))
    usage = _usage_counts(store)
    spec_jobs = {s.get("key", ""): _jobs_for(s.get("key", "")) for s in specs}

    # Facets — only values that actually occur, counted over the FULL set (unfiltered), so the
    # menu shows honest live counts (the FilterBar model contract).
    selected = {"complexity": parse_multi(complexity), "job_type": parse_multi(job_type)}
    cx_count: Counter = Counter()
    jt_count: Counter = Counter()
    jt_label: dict[str, str] = {}
    for s in specs:
        cx = _meta(s)["complexity"]
        if cx in _COMPLEXITY_ORDER:
            cx_count[cx] += 1
        for j in spec_jobs[s.get("key", "")]:
            jid = j.get("id") or j.get("name", "")
            jt_count[jid] += 1
            jt_label[jid] = j.get("name", jid)
    cx_options = [{"value": c, "label": _complexity_label(c), "count": cx_count[c], "dot": _COMPLEXITY_COLOR[c]}
                  for c in ("light", "medium", "deep") if cx_count[c]]
    jt_options = [{"value": jid, "label": jt_label[jid], "count": jt_count[jid]}
                  for jid in sorted(jt_count, key=lambda x: jt_label[x].lower())]
    facets = [{"key": "complexity", "label": t("complexity_h"), "icon": "activity", "options": cx_options},
              {"key": "job_type", "label": t("job_type_h"), "icon": "jtbd", "options": jt_options}]

    # Apply search + facets server-side.
    qn = q.strip().lower()
    want_cx = set(selected["complexity"])
    want_jt = set(selected["job_type"])
    visible = []
    for s in specs:
        if qn and qn not in f"{s.get('name', '')} {_meta(s)['summary']}".lower():
            continue
        if want_cx and _meta(s)["complexity"] not in want_cx:
            continue
        if want_jt and not (want_jt & {j.get("id") or j.get("name", "") for j in spec_jobs[s.get("key", "")]}):
            continue
        visible.append(s)

    base = "/methodologies" + (f"?q={quote(q)}" if q else "")
    bar = filter_bar(base, facets, selected, search={"value": q, "placeholder": t("search")})
    rows = [_meth_card(s, spec_jobs[s.get("key", "")], usage.get(s.get("key", ""), 0)) for s in visible]
    index = (h("div", {"class_": "sl-meth-index"}, fragment(*rows)) if rows
             else empty_filter_state(base))
    hero = h("div", {"class_": "sl-meth-hero"},
             h("div", {"class_": "sl-meth-lede"},
               h("h1", {"class_": "h1"}, t("methodologies_h"), h("span", {"class_": "h1cnt"}, str(len(specs)))),
               h("p", {"class_": "lead"}, t("methodologies_lead"))))
    body = h("div", {"class_": "page"}, hero, bar, index)
    return _layout(t("methodologies_h"), body, store, crumbs=[(t("projects"), "/projects"), (t("methodologies_h"), None)], active="methodologies")


def _methodology_detail(slug: str) -> str:
    store = Store()
    spec = _spec_for(slug, store)
    if not spec:
        return _layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"), icon="target"), store, active="methodologies")
    meta = _meta(spec)
    jobs = _jobs_for(spec.get("key", ""))
    steps = spec.get("steps") or []
    step_rows = []
    for i, st in enumerate(steps, start=1):
        step_rows.append(h("div", {"class_": "sl-meth-step"},
                           h("span", {"class_": "sl-meth-step-n"}, f"{i:02d}"),
                           h("div", {},
                             h("h3", {}, st.get("name", "")),
                             h("p", {}, st.get("intent", "")),
                             raw(_stage_guide(st)))))
    title = spec.get("name", spec.get("key", ""))
    when = (spec.get("when_to_use") or "").strip()
    body = h("div", {},
             h("div", {"class_": "sl-prose"}, raw(_md(when))) if when else None,
             h("h2", {"class_": "sl-doc-sub-h", "id": "steps"}, t("stages_h")),
             h("div", {"class_": "sl-meth-steps"}, fragment(*step_rows)))
    # Aside (artifact-detail parity, ux-contract §9): "Good for" as a quiet property, then a
    # full-rail-width "Matching jobs" block that WRITES OUT each job's question (a tooltip hid
    # them before), then — when any exist — the projects that run this methodology. No "Engine".
    prop_rows = [("target", t("good_for_h"), meta["jobs"])]
    if meta["complexity"] in _COMPLEXITY_ORDER:
        prop_rows.append(("activity", t("complexity_h"), _complexity_label(meta["complexity"])))
    job_blocks = [h("div", {"class_": "sl-meth-jobprop"},
                    h("b", {}, j.get("name", "")),
                    h("span", {}, j.get("user_question", "")))
                  for j in jobs]
    # Each aside section is a FLAT fragment (h4 + body), not a wrapping <div>: the rail's
    # between-section hairline + rhythm comes from `.rail h4:not(:first-child)`, which only
    # fires when the h4 is a direct child of .rail (a wrapper would make every h4 first-child).
    jobs_aside = fragment(h("h4", {"id": "sec-jobs"}, t("matching_jobs_h")),
                          h("div", {"class_": "sl-meth-jobprops"}, fragment(*job_blocks))) if job_blocks else ""
    projs = _projects_using(spec.get("key", ""), store)
    proj_aside = fragment(h("h4", {"id": "sec-meth-projects"}, t("meth_projects_h")),
                          *(h("a", {"class_": "relrow", "href": f"/projects/{p['id']}"},
                              h("span", {"class_": "ol-dot", "style": "background:#5e6ad2"}),
                              h("span", {"class_": "relt"}, p.get("title", "")))
                            for p in projs)) if projs else ""
    return detail_page(store, title=title, active="methodologies",
                       crumbs=[(t("projects"), "/projects"),
                               (t("methodologies_h"), "/methodologies"), (title, None)],
                       hero=raw(_doc_head(spec, meta, title)), body=body,
                       prop_rows=prop_rows, aside_extra=fragment(jobs_aside, proj_aside))


def register_methodologies(app) -> None:
    @app.get("/methodologies", response_class=HTMLResponse)
    def methodologies(q: str = "", job_type: str = "", complexity: str = "") -> str:
        return _methodologies_page(q=q, job_type=job_type, complexity=complexity)

    @app.get("/methodologies/{slug}", response_class=HTMLResponse)
    def methodology_detail(slug: str) -> str:
        return _methodology_detail(slug)
