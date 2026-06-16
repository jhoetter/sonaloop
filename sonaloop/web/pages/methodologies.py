"""Methodology browser: the process layer a project can run through."""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from ._ctx import *  # noqa: F401,F403

from ... import job_taxonomy, methodology as _methodology
from ..._icons import figure as _figure
from .._html import register_css


register_css(
    ".meth-hero{display:grid;grid-template-columns:minmax(0,1fr) minmax(280px,420px);gap:24px;align-items:start;margin:6px 0 22px}"
    ".meth-lede{max-width:78ch}"
    ".meth-index{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}"
    ".meth-card{display:grid;grid-template-columns:104px minmax(0,1fr);gap:12px;align-items:start;text-decoration:none;color:inherit;padding:10px}"
    ".meth-card:hover{border-color:color-mix(in srgb,var(--accent) 42%,var(--line));background:var(--panel-2)}"
    ".meth-card-img{position:relative;display:block;aspect-ratio:4/3;border-radius:var(--radius-sm);overflow:hidden;background:var(--panel-2);border:1px solid var(--line)}"
    ".meth-card-img img{width:100%;height:100%;object-fit:cover;display:block}"
    ".meth-card-img .rico{position:absolute;left:8px;bottom:8px;width:28px;height:28px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;color:var(--accent);background:color-mix(in srgb,var(--panel) 84%,transparent);backdrop-filter:blur(10px);box-shadow:0 1px 8px color-mix(in srgb,var(--ink) 12%,transparent)}"
    ".meth-card h2{font-size:var(--t-md);line-height:1.25;margin:0 0 4px;font-weight:650}"
    ".meth-card p{margin:0;color:var(--muted);line-height:1.4}"
    ".meth-card .meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}"
    ".meth-cover{position:relative;overflow:hidden;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);min-height:250px;color:var(--accent)}"
    ".meth-cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}"
    ".meth-cover:after{content:\"\";position:absolute;inset:0;background:linear-gradient(180deg,color-mix(in srgb,var(--panel) 0%,transparent),color-mix(in srgb,var(--panel) 72%,transparent))}"
    ".meth-cover-fig{position:absolute;inset:auto 8px -28px 8px;z-index:1;opacity:.78}"
    ".meth-cover-fig svg{width:100%;height:auto;display:block}"
    ".meth-cover+.meth-viz{margin-top:10px}"
    ".meth-bands{display:grid;gap:8px;margin-top:18px}"
    ".meth-band{display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;padding:12px 0;border-top:1px solid var(--line)}"
    ".meth-band b{font-size:var(--t-sm)}"
    ".meth-band span{color:var(--muted);line-height:1.45}"
    ".meth-viz{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:14px}"
    ".meth-viz svg{width:100%;height:auto;display:block;overflow:visible}"
    ".meth-viz text{font-family:var(--sans);fill:var(--muted);font-size:11px}"
    ".meth-viz .node{fill:var(--panel-2);stroke:var(--accent);stroke-width:1.5}"
    ".meth-viz .edge{stroke:var(--line-strong);stroke-width:1.4;fill:none}"
    ".meth-viz .loop{stroke-dasharray:4 4}"
    ".meth-steps{display:grid;gap:10px}"
    ".meth-step{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel)}"
    ".meth-step-n{width:28px;height:28px;border-radius:999px;background:var(--panel-2);display:inline-flex;align-items:center;justify-content:center;font-size:var(--t-xs);font-family:var(--mono);color:var(--accent)}"
    ".meth-step h3{margin:0 0 4px;font-size:var(--t-md)}"
    ".meth-step p{margin:0;color:var(--muted);line-height:1.45}"
    ".meth-guide{display:grid;gap:6px;margin-top:10px}"
    ".meth-guide-row{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}"
    ".meth-guide-row b{min-width:62px;color:var(--muted);font-size:var(--t-xs);line-height:1.9;text-transform:uppercase;letter-spacing:.08em}"
    ".meth-guide-row .chips{display:flex;gap:6px;flex-wrap:wrap}"
    ".meth-jobs{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}"
    ".meth-job{padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel)}"
    ".meth-job b{display:block;margin-bottom:4px}"
    ".meth-job span{color:var(--muted);line-height:1.4}"
    "@media(max-width:980px){.meth-hero{grid-template-columns:1fr}.meth-band{grid-template-columns:1fr}}"
    "@media(max-width:560px){.meth-card{grid-template-columns:1fr}.meth-card-img{aspect-ratio:16/7}}"
)

_ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "methodologies"


@lru_cache(maxsize=16)
def _asset_uri(name: str) -> str:
    if not name or Path(name).name != name:
        return ""
    path = _ASSET_DIR / name
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _slug(key: str) -> str:
    return key.replace("_", "-")


def _spec_for(slug: str, store: Store) -> dict | None:
    key = slug.replace("-", "_")
    reg = _methodology.registry(store)
    return reg.get(key) or reg.get(slug)


def _meta(spec: dict) -> dict:
    own = spec.get("presentation") or {}
    return {"icon": "target", "summary": spec.get("description", ""), "jobs": spec.get("when_to_use", ""),
            "image": "", "figure": ""} | own


def _image(spec: dict) -> str:
    return _asset_uri(str(_meta(spec).get("image") or ""))


def _cover(spec: dict) -> str:
    meta = _meta(spec)
    src = _asset_uri(str(meta.get("image") or ""))
    if not src:
        return ""
    fig = _figure(str(meta.get("figure") or ""), width=420, cls="meth-figure", animate=True)
    return h("div", {"class_": "meth-cover"},
             h("img", {"src": src, "alt": ""}),
             h("div", {"class_": "meth-cover-fig"}, raw(fig)) if fig else None)


def _guide_row(label: str, items: list[str], color: str) -> str:
    if not items:
        return ""
    return h("div", {"class_": "meth-guide-row"},
             h("b", {}, label),
             h("span", {"class_": "chips"},
               fragment(*(raw(_label(item, color)) for item in items))))


def _stage_guide(st: dict) -> str:
    pres = st.get("presentation") or {}
    formats = [str(x) for x in pres.get("formats") or [] if str(x).strip()]
    library = [str(x) for x in (pres.get("library") or pres.get("artifacts") or []) if str(x).strip()]
    if not (formats or library):
        return ""
    de = _lang() == "de"
    return h("div", {"class_": "meth-guide"},
             raw(_guide_row("Formate" if de else "Formats", formats, "var(--accent)")),
             raw(_guide_row("Library", library, "var(--blue)")))


def _jobs_for(key: str) -> list[dict]:
    ids = []
    for fw in job_taxonomy.frameworks():
        if fw.get("methodology_key") == key:
            ids.append(fw.get("id"))
    return [j for j in job_taxonomy.jobs() if any(fw in ids for fw in j.get("frameworks", []))]


def _methodology_svg(spec: dict) -> str:
    steps = spec.get("steps") or []
    if not steps:
        return ""
    width = max(420, 118 * len(steps))
    y = 62
    parts = [f'<svg viewBox="0 0 {width} 128" role="img" aria-label="{_esc(spec.get("name", ""))}">']
    xs = [48 + i * ((width - 96) / max(1, len(steps) - 1)) for i in range(len(steps))]
    for i in range(len(xs) - 1):
        parts.append(f'<path class="edge" d="M {xs[i] + 28:.1f} {y} C {xs[i] + 58:.1f} {y}, {xs[i + 1] - 58:.1f} {y}, {xs[i + 1] - 28:.1f} {y}"/>')
    by_id = {st.get("id"): i for i, st in enumerate(steps)}
    for i, st in enumerate(steps):
        lb = st.get("loop_back")
        if lb in by_id:
            j = by_id[lb]
            parts.append(f'<path class="edge loop" d="M {xs[i]:.1f} 94 C {xs[i]:.1f} 122, {xs[j]:.1f} 122, {xs[j]:.1f} 94"/>')
    for i, (x, st) in enumerate(zip(xs, steps, strict=False), start=1):
        req = st.get("requires") or {}
        r = 24 if req.get("min_inputs") else 19
        parts.append(f'<circle class="node" cx="{x:.1f}" cy="{y}" r="{r}"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + 4}" text-anchor="middle">{i}</text>')
        label = _esc(st.get("name", ""))
        parts.append(f'<text x="{x:.1f}" y="112" text-anchor="middle">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _methodologies_page() -> str:
    store = Store()
    specs = sorted(_methodology.registry(store).values(), key=lambda s: s.get("name", ""))
    de = _lang() == "de"
    rows = []
    for spec in specs:
        meta = _meta(spec)
        jobs = _jobs_for(spec.get("key", ""))
        src = _image(spec)
        rows.append(h("a", {"class_": "sl-card meth-card", "href": f"/methodologies/{_slug(spec.get('key', ''))}"},
                      h("span", {"class_": "meth-card-img"},
                        h("img", {"src": src, "alt": ""}) if src else None,
                        h("span", {"class_": "rico"}, raw(_icon(meta["icon"])))),
                      h("span", {},
                        h("h2", {}, spec.get("name", "")),
                        h("p", {}, meta["summary"]),
                        h("span", {"class_": "meta"},
                          raw(_label(t("n_tasks", n=len(spec.get("steps") or [])), "var(--accent)")),
                          raw(_label(f"{len(jobs)} Jobs", "var(--blue)"))))))
    bands = h("div", {"class_": "meth-bands"},
              h("div", {"class_": "meth-band"}, h("b", {}, "Job"), h("span", {}, "Was du herausfinden willst: Positioning, Pricing, Demand, Churn.")),
              h("div", {"class_": "meth-band"}, h("b", {}, t("methodology_h")), h("span", {}, "Der Prozess, der die Studie von offenem Problem zu belastbarer Antwort führt.")),
              h("div", {"class_": "meth-band"}, h("b", {}, "Format"), h("span", {}, "Ein einzelner Move im Prozess: Council, Head-to-Head, Red-Team oder Prototype Test.")))
    hero = h("div", {"class_": "meth-hero"},
             h("div", {"class_": "meth-lede"},
               h("h1", {"class_": "h1"}, t("methodologies_h"), h("span", {"class_": "h1cnt"}, str(len(specs)))),
               h("p", {"class_": "lead"}, "Methodologies sind die Prozesse, die ein Projekt strukturiert durchläuft." if de else "Methodologies are the processes a project runs through."),
               h("div", {"class_": "sl-prose"}, raw(_md(
                 "Ein Projekt startet mit einer Forschungsfrage. Die Methodology entscheidet, in welcher Reihenfolge Sonaloop öffnet, verdichtet, baut, testet und am Ende übergibt. Formate sind die einzelnen Moves innerhalb dieses Ablaufs." if de else
                 "A project starts with a research question. The methodology decides the order in which Sonaloop diverges, converges, builds, tests and hands off. Formats are the individual moves inside that process.")))),
             bands)
    body = h("div", {"class_": "page"}, hero, h("div", {"class_": "meth-index"}, fragment(*rows)))
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
        step_rows.append(h("div", {"class_": "meth-step"},
                           h("span", {"class_": "meth-step-n"}, f"{i:02d}"),
                           h("div", {},
                             h("h3", {}, st.get("name", "")),
                             h("p", {}, st.get("intent", "")),
                             raw(_stage_guide(st)))))
    job_cards = [h("div", {"class_": "meth-job"},
                   h("b", {}, j.get("name", "")),
                   h("span", {}, j.get("user_question", "")))
                 for j in jobs]
    title = spec.get("name", spec.get("key", ""))
    body = h("div", {"class_": "page"},
             _hero(title, sub=spec.get("description", ""), icon=meta["icon"],
                   top=raw(_label(t("methodology_h"), "var(--accent)"))),
             h("div", {"class_": "meth-hero"},
               h("div", {},
                 h("div", {"class_": "sl-prose"}, raw(_md(spec.get("when_to_use", "")))),
                 h("h2", {"class_": "doc-sub-h", "id": "steps"}, "Phasen" if _lang() == "de" else "Stages"),
                 h("div", {"class_": "meth-steps"}, fragment(*step_rows))),
               h("aside", {},
                 raw(_cover(spec)),
                 h("div", {"class_": "meth-viz"}, raw(_methodology_svg(spec))),
                 h("div", {"class_": "meth-bands"},
                   h("div", {"class_": "meth-band"}, h("b", {}, "Geeignet für" if _lang() == "de" else "Good for"), h("span", {}, meta["jobs"])),
                   h("div", {"class_": "meth-band"}, h("b", {}, "Engine"), h("span", {}, "Analyze -> Act -> Verify; convergence needs evidence-backed gates."))))),
             h("h2", {"class_": "doc-sub-h", "id": "jobs"}, "Passende Jobs" if _lang() == "de" else "Matching jobs"),
             h("div", {"class_": "meth-jobs"}, fragment(*job_cards)) if job_cards else h("p", {"class_": "muted"}, "—"))
    return _layout(title, body, store, crumbs=[(t("projects"), "/projects"), (t("methodologies_h"), "/methodologies"), (title, None)], active="methodologies")


def register_methodologies(app) -> None:
    @app.get("/methodologies", response_class=HTMLResponse)
    def methodologies() -> str:
        return _methodologies_page()

    @app.get("/methodologies/{slug}", response_class=HTMLResponse)
    def methodology_detail(slug: str) -> str:
        return _methodology_detail(slug)
