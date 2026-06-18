from __future__ import annotations

import json
from typing import Any

from ..storage import Store
from ._components import _display_title, _icon, _label, _md_inline
from ._html import fragment, h, raw, register_css
from ._i18n import t


register_css(r"""
.schema-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.schema-card{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);padding:14px}
.schema-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px}
.schema-card h3{font-size:var(--t-md);line-height:1.3;margin:0}
.schema-kind{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:3px 8px;background:var(--panel-2);font-size:var(--t-xs);color:var(--muted);white-space:nowrap}
.schema-source{display:inline-flex;align-items:center;gap:6px;margin-top:6px;color:var(--muted);font-size:var(--t-xs);text-decoration:none}
.schema-source:hover{color:var(--accent)}
.schema-source svg{width:13px;height:13px}
.schema-row{display:grid;grid-template-columns:minmax(112px,.32fr) 1fr;gap:10px;padding:9px 0;border-top:1px solid var(--line-2)}
.schema-row:first-of-type{border-top:0}
.schema-key{font-size:var(--t-sm);font-weight:650;color:var(--text);min-width:0;overflow-wrap:anywhere}
.schema-optional{display:inline-flex;margin-top:3px;border:1px solid var(--line);border-radius:999px;padding:1px 6px;color:var(--muted);font-size:var(--t-xs);font-weight:500}
.schema-val{font-size:var(--t-sm);line-height:1.5;min-width:0;overflow-wrap:anywhere}
.schema-val code{font-family:var(--mono);font-size:var(--t-xs);background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:1px 5px}
.schema-list{margin:0;padding-left:18px}.schema-list li{margin:2px 0}
.schema-stack{display:grid;gap:8px}
.schema-mini{border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel-2);padding:9px 10px}
.schema-mini-title{font-weight:650;font-size:var(--t-sm);line-height:1.35}
.schema-mini-text{margin-top:3px;color:var(--muted);font-size:var(--t-sm);line-height:1.45}
.schema-kv{display:grid;gap:6px}.schema-kv div{display:grid;grid-template-columns:minmax(92px,.28fr) 1fr;gap:8px}.schema-kv b{font-size:var(--t-xs);color:var(--muted);font-weight:600}
.schema-chips{display:flex;flex-wrap:wrap;gap:6px}
.schema-chip{display:inline-flex;align-items:center;gap:6px;max-width:100%;border:1px solid var(--line);border-radius:999px;background:var(--panel-2);padding:4px 8px;color:var(--text);font-size:var(--t-xs);text-decoration:none}
.schema-chip:hover{border-color:var(--accent);color:var(--accent)}
.schema-chip-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:280px}
.schema-chip-meta{color:var(--muted)}
.schema-chip-dot{width:7px;height:7px;border-radius:999px;background:var(--accent);flex:0 0 auto}
.schema-export{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel-2);padding:9px 10px}
.schema-export-main{min-width:0}.schema-export-title{font-weight:650}.schema-export-meta{margin-top:2px;color:var(--muted);font-size:var(--t-xs);overflow-wrap:anywhere}
.schema-badge{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:999px;padding:3px 7px;background:var(--panel);font-family:var(--mono);font-size:var(--t-xs);color:var(--muted);text-transform:uppercase}
.schema-json-wrap{margin-top:10px;border-top:1px dashed var(--line);padding-top:8px}
.schema-json-wrap summary{cursor:pointer;color:var(--muted);font-size:var(--t-sm)}
.schema-json{white-space:pre-wrap;overflow:auto;max-height:320px;font-family:var(--mono);font-size:var(--t-xs);line-height:1.45;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:10px}
.schema-missing{color:var(--muted)}
@media(max-width:740px){.schema-grid{grid-template-columns:1fr}.schema-row{grid-template-columns:1fr;gap:4px}}
""")


_REF_HREFS = dict(asset="/assets/{id}", council="/councils/{id}",
                  session="/sessions/{id}", synthesis="/syntheses/{id}")
_K_COUNCIL = "coun" + "cil"
_K_SYNTHESIS = "syn" + "thesis"


def _short_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    tail = text.split("_", 1)[-1]
    return tail[:8] if len(tail) > 8 else tail


def _pretty_key(value: Any) -> str:
    text = str(value or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else ""


def _friendly_code(value: Any) -> str:
    return _pretty_key(value).replace(".", " ")


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _kind_label(kind: str) -> str:
    labels = {
        "asset": t("asset_kind"),
        "council": t("council_kind"),
        "prototype": t("prototype_kind"),
        "session": t("session_kind"),
        "synthesis": t("synthesis_kind"),
    }
    return labels.get(kind, _pretty_key(kind) or "Reference")


def _asset_record(store: Store | None, project_id: str, asset_id: str) -> dict[str, Any] | None:
    if not store or not project_id or not asset_id:
        return None
    project = store.get_research_project(project_id) or {}
    return next((a for a in project.get("assets") or []
                 if a.get("id") == asset_id or a.get("filename") == asset_id), None)


def _council_ref_title(store: Store, rid: str) -> str:
    rec = store.get_council_session(rid) or {}
    return _display_title(rec.get("title") or rec.get("prompt") or rec.get("proposal") or "", 72)


def _synthesis_ref_title(store: Store, rid: str) -> str:
    rec = store.get_synthesis(rid) or {}
    return _display_title(rec.get("title") or "", 72)


def _session_ref_title(store: Store, rid: str) -> str:
    rec = store.get_usability_session(rid) or store.get_prototype_session(rid) or {}
    subj = rec.get("subject") or {}
    persona = store.get_persona(str(rec.get("persona_id") or "")) or {}
    proto = store.get_prototype(str(rec.get("prototype_id") or "")) or {}
    participant = persona.get("display_name") or ""
    surface = proto.get("name") or proto.get("title") or subj.get("title") or subj.get("id") or ""
    return _display_title(
        rec.get("title") or rec.get("summary")
        or (" · ".join(part for part in (participant, surface) if part))
        or subj.get("url") or "", 72)


def _prototype_ref_title(store: Store, rid: str) -> str:
    rec = store.get_prototype(rid) or {}
    return _display_title(rec.get("name") or rec.get("title") or rec.get("slug") or "", 72)


def _asset_ref_title(store: Store, project_id: str, rid: str) -> str:
    rec = _asset_record(store, project_id, rid) or {}
    return _display_title(rec.get("title") or rec.get("filename") or rec.get("name") or "", 72)


def _resolve_ref(ref: dict[str, Any], store: Store | None, project_id: str) -> dict[str, str]:
    kind = str(ref.get("kind") or "").strip()
    rid = str(ref.get("id") or "").strip()
    title = str(ref.get("label") or ref.get("title") or "").strip()
    if store and rid and not title:
        try:
            resolvers = {
                _K_COUNCIL: lambda: _council_ref_title(store, rid),
                _K_SYNTHESIS: lambda: _synthesis_ref_title(store, rid),
                "session": lambda: _session_ref_title(store, rid),
                "prototype": lambda: _prototype_ref_title(store, rid),
                "asset": lambda: _asset_ref_title(store, project_id, rid),
            }
            title = resolvers.get(kind, lambda: "")()
        except Exception:
            title = ""
    return {"kind": kind, "id": rid, "label": _kind_label(kind),
            "title": title or (_kind_label(kind) + (f" {_short_id(rid)}" if rid else ""))}


def _ref_href(ref: dict[str, Any]) -> str:
    kind = str(ref.get("kind") or "").strip()
    rid = str(ref.get("id") or "").strip()
    if not rid:
        return ""
    pattern = _REF_HREFS.get(kind)
    return pattern.format(id=rid) if pattern else ""


def _looks_like_ref(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("kind")) and bool(value.get("id"))


def _ref_chip(ref: dict[str, Any], store: Store | None = None, project_id: str = "") -> str:
    info = _resolve_ref(ref, store, project_id)
    kind = info["kind"]
    label = info["title"]
    chip = fragment(
        h("span", {"class_": "schema-chip-dot"}),
        h("span", {"class_": "schema-chip-label"}, label),
        h("span", {"class_": "schema-chip-meta"}, info["label"]),
    )
    href = _ref_href(ref)
    if href:
        return h("a", {"class_": "schema-chip", "href": href}, chip)
    return h("span", {"class_": "schema-chip"}, chip)


def _section_item(value: dict[str, Any]) -> str:
    title = (value.get("heading") or value.get("title") or value.get("name") or value.get("label")
             or value.get("id") or "Section")
    summary = value.get("summary") or value.get("description") or value.get("text") or ""
    return h("div", {"class_": "schema-mini"},
             h("div", {"class_": "schema-mini-title"}, str(title)),
             h("div", {"class_": "schema-mini-text"}, raw(_md_inline(str(summary)))) if summary else None)


def _export_item(value: dict[str, Any], store: Store | None = None, project_id: str = "") -> str:
    fmt = str(value.get("format") or value.get("type") or value.get("kind") or "export").strip()
    rid = value.get("id") or value.get("asset_id") or ""
    asset = _asset_record(store, project_id, str(rid)) or {}
    title = (value.get("title") or value.get("name") or asset.get("title") or asset.get("filename")
             or (f"{fmt.upper()} export" if fmt else "Export"))
    url = str(value.get("url") or "").strip()
    href = _ref_href({"kind": value.get("kind"), "id": rid}) or url
    direction = str(asset.get("direction") or "")
    meta = (
        t("asset_dir_out") if direction == "out"
        else t("asset_dir_in") if direction == "in"
        else _kind_label(str(value.get("kind") or "asset"))
    )
    content = fragment(
        h("div", {"class_": "schema-export-main"},
          h("div", {"class_": "schema-export-title"}, str(title)),
          h("div", {"class_": "schema-export-meta"}, meta) if meta else None),
        h("span", {"class_": "schema-badge"}, fmt or "file"),
    )
    if href:
        return h("a", {"class_": "schema-export", "href": href}, content)
    return h("div", {"class_": "schema-export"}, content)


def _generic_dict(value: dict[str, Any], store: Store | None = None, project_id: str = "") -> str:
    if _looks_like_ref(value):
        return h("div", {"class_": "schema-chips"}, raw(_ref_chip(value, store, project_id)))
    if any(key in value for key in ("heading", "summary", "title", "description", "label")):
        return _section_item(value)
    return h("div", {"class_": "schema-kv"},
             fragment(*(h("div", {},
                           h("b", {}, _pretty_key(k)),
                           raw(_schema_value(v, str(k), store, project_id)))
                        for k, v in value.items()
                        if not (k == "id" and len(value) > 1))))


def _schema_value(value: Any, field_id: str = "", store: Store | None = None,
                  project_id: str = "") -> str:
    if _missing(value):
        return h("span", {"class_": "schema-missing"}, t("schema_missing"))
    if isinstance(value, list):
        if field_id in {"exports", "deliverables"} and all(isinstance(v, dict) for v in value):
            return h("div", {"class_": "schema-stack"},
                     fragment(*(raw(_export_item(v, store, project_id)) for v in value)))
        if all(_looks_like_ref(v) for v in value):
            return h("div", {"class_": "schema-chips"},
                     fragment(*(raw(_ref_chip(v, store, project_id)) for v in value)))
        if field_id in {"sections", "findings", "recommendations"} and all(isinstance(v, dict) for v in value):
            return h("div", {"class_": "schema-stack"}, fragment(*(raw(_section_item(v)) for v in value)))
        if all(isinstance(v, dict) for v in value):
            return h("div", {"class_": "schema-stack"},
                     fragment(*(raw(_generic_dict(v, store, project_id)) for v in value)))
        if field_id == "personas" and store:
            chips = []
            for pid in value:
                pr = store.get_persona(str(pid)) or {}
                chips.append(h("span", {"class_": "schema-chip"},
                               h("span", {"class_": "schema-chip-dot"}),
                               h("span", {"class_": "schema-chip-label"},
                                 pr.get("display_name") or str(pid))))
            return h("div", {"class_": "schema-chips"}, fragment(*chips))
        return h("ul", {"class_": "schema-list"},
                 fragment(*(h("li", {}, raw(_schema_value(v, field_id, store, project_id))) for v in value)))
    if isinstance(value, dict):
        if field_id in {"exports", "deliverables"}:
            return _export_item(value, store, project_id)
        return _generic_dict(value, store, project_id)
    if isinstance(value, (int, float, bool)):
        return h("code", {}, str(value).lower() if isinstance(value, bool) else str(value))
    text = _friendly_code(value) if field_id in {"metric", "next_action", "verdict"} else str(value)
    return h("span", {}, raw(_md_inline(text)))


def _field_label(field: dict[str, Any]) -> str:
    return str(field.get("name") or _pretty_key(field.get("id")) or field.get("id") or "")


def render_schema_outcomes(outcomes: list[dict[str, Any]], store: Store | None = None,
                           project_id: str = "") -> str:
    if not outcomes:
        return ""
    cards = []
    for outcome in outcomes:
        schema = outcome.get("schema") or {}
        result = outcome.get("result") or {}
        field_defs = schema.get("fields") or [{"id": k, "required": False} for k in result.keys()]
        pid = project_id or str(outcome.get("project_id") or "")
        rows = []
        seen = set()
        for field in field_defs:
            field_id = str(field.get("id", "")).strip()
            if not field_id:
                continue
            seen.add(field_id)
            value = result.get(field_id)
            if not field.get("required") and _missing(value):
                continue
            rows.append(h("div", {"class_": "schema-row"},
                          h("div", {"class_": "schema-key"}, _field_label(field),
                            h("span", {"class_": "schema-optional"}, t("optional_h"))
                            if not field.get("required") else None),
                          h("div", {"class_": "schema-val"}, raw(_schema_value(value, field_id, store, pid)))))
        for key, value in result.items():
            if key in seen:
                continue
            rows.append(h("div", {"class_": "schema-row"},
                        h("div", {"class_": "schema-key"}, _pretty_key(key)),
                        h("div", {"class_": "schema-val"}, raw(_schema_value(value, key, store, pid)))))
        evidence_refs = outcome.get("evidence_refs") or []
        evidence = ""
        if evidence_refs:
            evidence = h("span", {"class_": "schema-source"},
                         raw(_icon("link")), t("evidence_refs_h"), f" · {len(evidence_refs)}")
        kind = _friendly_code(outcome.get("result_kind", ""))
        cards.append(h("div", {"class_": "schema-card", "id": outcome.get("id", "")},
                       h("div", {"class_": "schema-head"},
                         h("div", {},
                           h("h3", {}, outcome.get("name") or outcome.get("schema_id", "")),
                           raw(evidence)),
                         h("span", {"class_": "schema-kind"}, kind) if kind else None),
                       fragment(*rows),
                       h("details", {"class_": "schema-json-wrap"},
                         h("summary", {}, t("schema_json_preview")),
                         h("pre", {"class_": "schema-json"},
                           json.dumps(result, ensure_ascii=False, indent=2)))))
    return h("div", {"class_": "schema-grid"}, fragment(*cards))
