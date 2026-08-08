"""Methodology browser: the process layer a project can run through."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from ._ctx import *  # noqa: F401,F403

from ... import job_taxonomy, methodology as _methodology, result_schemas as _result_schemas
from ...theming import active_runtime_design_system_context
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
    ".sl-meth-img{display:block;width:100%;height:100%}"
    ".sl-meth-img--dark{display:none}"
    "[data-theme='dark'] .sl-meth-img--light{display:none}"
    "[data-theme='dark'] .sl-meth-img--dark{display:block}"
    "@media(prefers-color-scheme:dark){:root:not([data-theme]) .sl-meth-img--light{display:none}:root:not([data-theme]) .sl-meth-img--dark{display:block}}"
    ".sl-meth-card-cover img{width:100%;height:100%;object-fit:cover;display:block}"
    ".sl-meth-card-ico{position:relative;z-index:1;display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;margin:14px 0 0 14px;border-radius:var(--radius-lg);background:var(--panel);border:1px solid var(--line);color:var(--accent)}"
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
    ".sl-meth-ico{display:inline-flex;align-items:center;justify-content:center;width:60px;height:60px;border-radius:var(--radius-lg);background:var(--panel);border:1px solid var(--line);color:var(--accent)}"
    ".sl-meth-ico svg{width:32px;height:32px}"
    ".sl-meth-ico--float{position:relative;z-index:1;margin:-30px 0 0 20px;box-shadow:0 4px 16px color-mix(in srgb,var(--ink) 12%,transparent)}"
    ".sl-meth-doc-head .sl-page-header{margin:10px 0 0}"
    ".sl-meth-bands{display:grid;gap:8px;margin-top:18px}"
    ".sl-meth-band{display:grid;grid-template-columns:96px minmax(0,1fr);gap:12px;padding:12px 0;border-top:1px solid var(--line)}"
    ".sl-meth-band b{font-size:var(--t-sm)}"
    ".sl-meth-band span{color:var(--muted);line-height:1.45}"
    ".sl-meth-steps{display:grid;gap:10px}"
    ".sl-meth-step{display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel)}"
    ".sl-meth-step-n{width:28px;height:28px;border-radius:var(--radius-full);background:var(--panel-2);display:inline-flex;align-items:center;justify-content:center;font-size:var(--t-xs);font-family:var(--mono);color:var(--accent)}"
    ".sl-meth-step h3{margin:0 0 4px;font-size:var(--t-md)}"
    ".sl-meth-step p{margin:0;color:var(--muted);line-height:1.45}"
    ".sl-meth-guide{display:grid;gap:6px;margin-top:10px}"
    ".sl-meth-guide-row{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}"
    ".sl-meth-guide-row b{min-width:62px;color:var(--muted);font-size:var(--t-xs);line-height:1.9;text-transform:uppercase;letter-spacing:.08em}"
    ".sl-meth-chips{display:flex;gap:6px;flex-wrap:wrap}"
    ".sl-meth-jobprops{display:grid;gap:12px}"
    ".sl-meth-jobprop b{display:block;font-weight:600;line-height:1.3;margin-bottom:2px}"
    ".sl-meth-jobprop span{color:var(--muted);line-height:1.45;font-size:var(--t-sm)}"
    ".sl-meth-schema-rail{display:grid;gap:8px}"
    ".sl-meth-schema-intro{margin:0 0 10px;color:var(--muted);font-size:var(--t-sm);line-height:1.45}"
    ".sl-meth-schema-dlgbtn{display:block;width:100%;text-align:left;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel);color:var(--ink);padding:12px;cursor:pointer}"
    ".sl-meth-schema-dlgbtn:hover{border-color:color-mix(in srgb,var(--accent) 38%,var(--line));background:var(--panel-2)}"
    ".sl-meth-schema-title{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}"
    ".sl-meth-schema-title b{font-size:var(--t-sm);line-height:1.25}"
    ".sl-meth-schema-title code{display:block;margin-top:2px;font-family:var(--mono);font-size:var(--t-xs);color:var(--muted);white-space:normal;overflow-wrap:anywhere}"
    ".sl-meth-schema-meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}"
    ".sl-meth-schema-desc{display:block;margin-top:8px;color:var(--muted);font-size:var(--t-sm);line-height:1.45}"
    ".sl-meth-schema-dialog{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);color:var(--ink);padding:20px;width:min(820px,92vw);max-height:90vh;overflow:auto}"
    ".sl-meth-schema-dialog::backdrop{background:rgba(0,0,0,.45)}"
    ".sl-meth-schema-dialog h3{margin:0 0 4px;font-size:var(--t-lg)}"
    ".sl-meth-schema-dialog p{margin:0;color:var(--muted);line-height:1.45}"
    ".sl-meth-schema-dialog-actions{display:flex;justify-content:flex-end;margin-top:14px}"
    ".sl-meth-schema-mini{display:grid;gap:0;margin-top:14px}"
    ".sl-meth-schema-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-top:12px}"
    ".sl-meth-schema{border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel);padding:12px}"
    ".sl-meth-schema h3{margin:2px 0 6px;font-size:var(--t-md)}"
    ".sl-meth-schema p{margin:0;color:var(--muted);line-height:1.45}"
    ".sl-meth-schema-code{font-family:var(--mono);font-size:var(--t-xs);color:var(--muted)}"
    ".sl-meth-schema-block{padding:14px 0;border-top:1px solid var(--line-2)}"
    ".sl-meth-schema-block:first-child{border-top:0;padding-top:0}"
    ".sl-meth-schema-block b{display:block;margin-bottom:6px;color:var(--muted);font-size:var(--t-xs);text-transform:uppercase;letter-spacing:.08em}"
    ".sl-meth-fields{display:grid;gap:6px}"
    ".sl-meth-field{display:grid;grid-template-columns:minmax(96px,.35fr) 1fr;gap:8px;font-size:var(--t-sm)}"
    ".sl-meth-field code{font-family:var(--mono);font-size:var(--t-xs)}"
    ".sl-meth-field span{color:var(--muted)}"
    ".sl-meth-field-row{display:grid;grid-template-columns:minmax(190px,1.05fr) minmax(120px,.42fr) minmax(180px,.8fr);gap:12px;align-items:start;padding:9px 0;border-top:1px solid var(--line-2)}"
    ".sl-meth-field-row:first-child{border-top:0}"
    ".sl-meth-field-main code{display:block;font-family:var(--mono);font-size:var(--t-xs);margin-bottom:3px}"
    ".sl-meth-field-main span{display:block;color:var(--muted);font-size:var(--t-sm);line-height:1.35}"
    ".sl-meth-field-type{color:var(--muted);font-size:var(--t-sm);line-height:1.35}"
    ".sl-meth-field-example{font-family:var(--mono);font-size:var(--t-xs);line-height:1.45;background:var(--panel-2);border:1px solid var(--line-2);border-radius:var(--radius-sm);padding:3px 7px;white-space:pre-wrap;overflow-wrap:anywhere}"
    ".sl-meth-metrics{display:flex;gap:6px;flex-wrap:wrap}"
    ".sl-meth-metrics code{font-family:var(--mono);font-size:var(--t-xs);background:var(--panel-2);border:1px solid var(--line-2);border-radius:var(--radius-sm);padding:2px 7px;color:var(--muted)}"
    ".sl-meth-checklist{display:grid;gap:8px;margin:0;padding:0;list-style:none}"
    ".sl-meth-checkitem{display:grid;grid-template-columns:18px minmax(0,1fr);gap:10px;align-items:start;color:var(--muted);line-height:1.45}"
    ".sl-meth-checkmark{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;margin-top:2px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel-2);color:var(--accent)}"
    ".sl-meth-checkmark svg{width:12px;height:12px;stroke-width:2.2}"
    ".sl-meth-schema-list{margin:0;padding-left:18px;color:var(--muted);line-height:1.45}"
    "@media(max-width:980px){.sl-meth-hero{grid-template-columns:1fr}.sl-meth-band{grid-template-columns:1fr}}"
    "@media(max-width:700px){.sl-meth-field-row{grid-template-columns:1fr}.sl-meth-schema-dialog{padding:16px}}"
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
    if c == "light":
        return t("complexity_light")
    if c == "medium":
        return t("complexity_medium")
    if c == "deep":
        return t("complexity_deep")
    return ""


def _image(spec: dict) -> str:
    return _asset_src(str(_meta(spec).get("image") or ""))


def _image_dark(spec: dict) -> str:
    """The dark-theme twin of the cover (`<stem>-dark<ext>`), or "" if none is vendored."""
    name = str(_meta(spec).get("image") or "")
    if not name:
        return ""
    p = Path(name)
    return _asset_src(f"{p.stem}-dark{p.suffix}")


def _runtime_methodology_cover_base() -> str:
    ctx = active_runtime_design_system_context()
    ds = (ctx or {}).get("design_system") or {}
    meta = ds.get("meta") or {}
    base = str(meta.get("methodology_cover_asset_base") or "").strip()
    if not base.startswith("/cloud-assets/design-presets/methodologies/"):
        return ""
    return base if base.endswith("/") else f"{base}/"


def _cover_sources(spec: dict) -> tuple[str, str]:
    name = Path(str(_meta(spec).get("image") or "")).name
    if not name:
        return "", ""
    base = _runtime_methodology_cover_base()
    if base:
        p = Path(name)
        return (
            f"{base}{quote(name)}",
            f"{base}{quote(f'{p.stem}-dark{p.suffix}')}",
        )
    return _asset_src(name), _image_dark(spec)


def _cover_inner(spec: dict):
    """The cover media, including explicit sidebar light/dark theme choices."""
    light, dark = _cover_sources(spec)
    if not light:
        return None
    attrs = {"loading": "lazy", "decoding": "async", "alt": ""}
    light_img = h("span", {"class_": "sl-meth-img sl-meth-img--light"},
                  h("img", {"src": light, **attrs}))
    if not dark:
        return light_img
    return fragment(
        light_img,
        h("span", {"class_": "sl-meth-img sl-meth-img--dark"},
          h("img", {"src": dark, **attrs})),
    )


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
    for p in store.list_research_projects():
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
    for p in store.list_research_projects():
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


def _schema_card(schema: dict, role: str = "") -> str:
    fields = schema.get("fields") or []
    field_rows = [
        h("div", {"class_": "sl-meth-field"},
          h("code", {}, f.get("id", "")),
          h("span", {}, f'{f.get("type", "")} · {t("required_h") if f.get("required") else t("optional_h")}'))
        for f in fields
    ]
    metrics = [str(x) for x in schema.get("derived_metrics") or []]
    done = [str(x) for x in schema.get("done_when") or []]
    return h("div", {"class_": "sl-meth-schema"},
             h("div", {"class_": "sl-meth-schema-code"}, schema.get("id", "")),
             h("h3", {}, schema.get("name", schema.get("id", ""))),
             h("p", {}, schema.get("summary", "")),
             raw(_label(role, "var(--violet)")) if role else None,
             h("div", {"class_": "sl-meth-schema-block"},
               h("b", {}, t("expected_fields_h")),
               h("div", {"class_": "sl-meth-fields"}, fragment(*field_rows))),
             h("div", {"class_": "sl-meth-schema-block"},
               h("b", {}, t("derived_metrics_h")),
               h("ul", {"class_": "sl-meth-schema-list"},
                 fragment(*(h("li", {}, m) for m in metrics))) if metrics else h("p", {}, "—")),
             h("div", {"class_": "sl-meth-schema-block"},
               h("b", {}, t("done_criteria_h")),
               h("ul", {"class_": "sl-meth-schema-list"},
                 fragment(*(h("li", {}, d) for d in done))) if done else h("p", {}, "—")))


def _humanize_token(value: str) -> str:
    return " ".join(part for part in str(value or "").replace("-", "_").split("_") if part).capitalize()


def _schema_dialog_id(schema_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in str(schema_id or "schema")).strip("-")
    return f"meth-schema-{safe}"


def _schema_example(schema: dict, field: dict) -> str:
    examples = schema.get("example") or {}
    value = field.get("example", examples.get(field.get("id", "")))
    if value is None or value == "":
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ": "))
    return str(value)


_SCHEMA_DIALOG_JS = """<script>(function(){if(window.__slMethSchemaDialog)return;window.__slMethSchemaDialog=1;
document.addEventListener('click',function(e){
  var btn=e.target&&e.target.closest&&e.target.closest('[data-meth-schema-dialog]');
  if(btn){
    e.preventDefault();
    var dlg=document.getElementById(btn.getAttribute('data-meth-schema-dialog'));
    if(!dlg)return;
    if(dlg.showModal){if(!dlg.open)dlg.showModal();}else{dlg.setAttribute('open','');}
    return;
  }
  var d=e.target&&e.target.closest&&e.target.closest('dialog.sl-meth-schema-dialog');
  if(d&&e.target===d&&d.open)d.close();
});
})();</script>"""


def _schema_dialog_parts(schema: dict, role: str = "") -> tuple[str, str]:
    fields = schema.get("fields") or []
    field_rows = [
        h("div", {"class_": "sl-meth-field-row"},
          h("span", {"class_": "sl-meth-field-main"},
            h("code", {}, f.get("id", "")),
            h("span", {}, f.get("description", ""))),
          h("span", {"class_": "sl-meth-field-type"},
            f'{f.get("type", "")} · {t("required_h") if f.get("required") else t("optional_h")}'),
          h("code", {"class_": "sl-meth-field-example"}, _schema_example(schema, f)))
        for f in fields
    ]
    metrics = [str(x) for x in schema.get("derived_metrics") or []]
    done = [str(x) for x in schema.get("done_when") or []]
    required_count = sum(1 for f in fields if f.get("required"))
    meta = [
        raw(_label(_humanize_token(role), "var(--violet)")) if role else "",
        raw(_label(_humanize_token(schema.get("result_kind", "")), "var(--blue)")) if schema.get("result_kind") else "",
        raw(_label(f"{required_count} {t('required_h')}", "var(--muted)")) if required_count else "",
    ]
    did = _schema_dialog_id(schema.get("id", ""))
    trigger = h("button", {"class_": "sl-meth-schema-dlgbtn", "type": "button",
                           "data_meth_schema_dialog": did},
                h("span", {"class_": "sl-meth-schema-title"},
                  h("span", {},
                    h("b", {}, schema.get("name", schema.get("id", ""))),
                    h("code", {}, schema.get("id", "")))),
                h("span", {"class_": "sl-meth-schema-meta"}, fragment(*meta)),
                h("span", {"class_": "sl-meth-schema-desc"}, schema.get("summary", "")))
    dialog = h("dialog", {"class_": "sl-meth-schema-dialog", "id": did},
               h("h3", {}, schema.get("name", schema.get("id", ""))),
               h("div", {"class_": "sl-meth-schema-code"}, schema.get("id", "")),
               h("p", {}, schema.get("summary", "")),
               h("span", {"class_": "sl-meth-schema-meta"}, fragment(*meta)),
               h("div", {"class_": "sl-meth-schema-mini"},
                 h("div", {"class_": "sl-meth-schema-block"},
                   h("b", {}, t("expected_fields_h")),
                   h("div", {"class_": "sl-meth-fields"}, fragment(*field_rows))),
                 h("div", {"class_": "sl-meth-schema-block"},
                   h("b", {}, t("derived_metrics_h")),
                   h("div", {"class_": "sl-meth-metrics"},
                     fragment(*(h("code", {}, m) for m in metrics))) if metrics else h("p", {}, "—")),
                 h("div", {"class_": "sl-meth-schema-block"},
                   h("b", {}, t("done_criteria_h")),
                   h("ul", {"class_": "sl-meth-checklist"},
                     fragment(*(h("li", {"class_": "sl-meth-checkitem"},
                                  h("span", {"class_": "sl-meth-checkmark", "aria_hidden": "true"},
                                    raw(_icon("check"))),
                                  h("span", {}, d))
                                for d in done))) if done else h("p", {}, "—"))),
               h("form", {"method": "dialog", "class_": "sl-meth-schema-dialog-actions"},
                 h("button", {"class_": "sl-btn", "value": "close"}, t("cancel"))))
    return trigger, dialog


def _schema_aside_for_methodology(key: str) -> str:
    try:
        refs = _result_schemas.contract_for_methodology(key).get("result_schemas") or []
    except KeyError:
        refs = []
    if not refs:
        return ""
    parts = [_schema_dialog_parts(_result_schemas.get_schema(ref["id"]), ref.get("role", ""))
             for ref in refs]
    triggers = [trigger for trigger, _dialog in parts]
    dialogs = [_dialog for _trigger, _dialog in parts]
    return fragment(h("h4", {"id": "sec-target-schemas"}, t("target_schemas_h")),
                    h("p", {"class_": "sl-meth-schema-intro"}, t("target_schemas_lead")),
                    h("div", {"class_": "sl-meth-schema-rail"}, fragment(*triggers)),
                    fragment(*dialogs),
                    raw(_SCHEMA_DIALOG_JS))


def _schema_docs_for_methodology(key: str) -> str:
    try:
        refs = _result_schemas.contract_for_methodology(key).get("result_schemas") or []
    except KeyError:
        refs = []
    if not refs:
        return ""
    cards = []
    for ref in refs:
        schema = _result_schemas.get_schema(ref["id"])
        cards.append(_schema_card(schema, ref.get("role", "")))
    return h("section", {},
             h("h2", {"class_": "sl-doc-sub-h", "id": "result-schemas"},
               t("result_schemas_h")),
             h("div", {"class_": "sl-meth-schema-grid"}, fragment(*cards)))


def _schema_index(result_schema: str | None = None) -> str:
    schemas = _result_schemas.schemas()
    if result_schema:
        schemas = [s for s in schemas if s.get("id") == result_schema]
    if not schemas:
        return ""
    cards = [_schema_card(schema) for schema in schemas]
    return h("section", {},
             h("h2", {"class_": "sl-doc-sub-h", "id": "result-schemas"},
               t("result_schemas_h")),
             h("div", {"class_": "sl-meth-schema-grid"}, fragment(*cards)))


def _methodologies_page(q: str = "", job_type: str = "", complexity: str = "",
                        result_schema: str | None = None) -> str:
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
    schema_section = raw(_schema_index(result_schema)) if result_schema else ""
    body = h("div", {"class_": "page"}, hero, bar, index, schema_section)
    return _layout(t("methodologies_h"), body, store,
                   crumbs=[(t("methodologies_h"), None)], active="methodologies")


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
    schema_aside = _schema_aside_for_methodology(spec.get("key", ""))
    projs = _projects_using(spec.get("key", ""), store)
    proj_aside = fragment(h("h4", {"id": "sec-meth-projects"}, t("meth_projects_h")),
                          *(h("a", {"class_": "sl-relrow", "href": f"/jobs/{p['id']}"},
                              h("span", {"class_": "sl-rel-dot sl-rel-dot--accent"}),
                              h("span", {"class_": "sl-relt"}, p.get("title", "")))
                            for p in projs)) if projs else ""
    return detail_page(store, title=title, active="methodologies",
                       crumbs=[(t("methodologies_h"), "/methodologies"), (title, None)],
                       hero=raw(_doc_head(spec, meta, title)), body=body,
                       prop_rows=prop_rows, aside_extra=fragment(jobs_aside, schema_aside, proj_aside))


def register_methodologies(app) -> None:
    @app.get("/methodologies", response_class=HTMLResponse)
    def methodologies(q: str = "", job_type: str = "", complexity: str = "",
                      result_schema: str | None = None) -> str:
        return _methodologies_page(q=q, job_type=job_type, complexity=complexity,
                                  result_schema=result_schema)

    @app.get("/methodologies/{slug}", response_class=HTMLResponse)
    def methodology_detail(slug: str) -> str:
        return _methodology_detail(slug)
