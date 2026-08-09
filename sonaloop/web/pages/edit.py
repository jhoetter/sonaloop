"""Write routes: the inspector's structural CRUD (ticket web-crud-structure).

Every route follows the ONE write-path pattern from web/_forms.py — POST -> write_gate
(CSRF + cloud access guard) -> validate -> SERVICE call -> 303. The mutation boundary
(docs/web-mutations.md): the UI inspects + edits structural metadata; CREATION is not a
UI affordance (UX U9, §8.4 — it belongs to the MCP/CLI host), so the POST /new routes
stay as API surface while their GET forms are gone.

Since UX V10 (ux-contract §9) EDIT IS A DIALOG over the detail page: every detail header
carries the visible "…" overflow (Edit opens the native <dialog>, Delete the typed/plain
confirm modal) built by the per-kind *_actions() composers below. The GET /edit routes
keep answering for deep links (the same field builders — ONE source), and a POST
validation failure re-renders the DETAIL backdrop with the dialog re-opened and the
errors inline (the typed-confirm idiom)."""
from __future__ import annotations

from fastapi import Request

from ._ctx import *  # noqa: F401,F403  (shared render toolkit)
from ...prototypes import PrototypeError
from .._forms import (
    detail_overflow, field, form_page, not_found, overflow_delete, see_other, write_gate,
)


def _s(form, name: str) -> str:
    return str(form.get(name) or "").strip()


# ------------------------------------------------------- the per-kind field builders
# ONE source for the edit page (form_page) AND the V10 edit dialog (detail_overflow).

def project_fields(values: dict, errors: dict) -> list:
    current_icon = values.get("icon") or "random"
    def icon_choice(value: str, label: str, icon_name: str) -> str:
        checked = current_icon == value
        return h("label", {"class_": "sl-icon-option"},
                 h("input", {"type": "radio", "name": "icon", "value": value,
                             "checked": checked}),
                 h("span", {"class_": "sl-icon-tile"},
                   h("span", {"class_": "rico sl-project-rico"},
                     raw(services.project_icon_svg({"icon": {"kind": "regular", "name": icon_name}}))),
                   h("span", {"class_": "sl-icon-name"}, label)))
    icon_options = [icon_choice("random", t("project_icon_random"), "sparkles")]
    for name in services.available_project_icons()["icons"]:
        icon_options.append(icon_choice(name, name, name))
    return [raw(field("title", t("f_title"), values.get("title", ""),
                      error=errors.get("title", ""), required=True)),
            raw(field("goal", t("f_goal"), values.get("goal", ""))),
            h("fieldset", {"class_": "sl-field sl-icon-picker", "data-icon-picker": True,
                           "tabindex": "-1"},
              h("legend", {"class_": "sl-field__label"}, t("f_project_icon")),
              h("div", {"class_": "sl-icon-grid"}, fragment(*icon_options)),
              h("p", {"class_": "sl-field__hint"}, t("f_project_icon_hint")))]


def persona_fields(values: dict, errors: dict) -> list:
    return [raw(field("display_name", t("f_name"), values.get("display_name", ""),
                      error=errors.get("display_name", ""), required=True)),
            raw(field("role_title", t("f_role_title"), values.get("role_title", ""))),
            raw(field("customer_type", t("f_segment"), values.get("customer_type", ""))),
            raw(field("industry", t("f_industry"), values.get("industry", "")))]


def note_fields(values: dict, errors: dict) -> list:
    return [raw(field("title", t("f_title"), values.get("title", ""))),
            raw(field("text", t("f_text"), values.get("text", ""),
                      error=errors.get("text", ""), required=True, textarea=True))]


def section_fields(values: dict, errors: dict) -> list:
    return [raw(field("title", t("f_title"), values.get("title", ""),
                      error=errors.get("title", ""), required=True)),
            raw(field("kind", t("type_h"), values.get("kind", "theme"))),
            raw(field("note", t("f_note"), values.get("note", ""), textarea=True))]


def _project_values(proj: dict) -> dict:
    icon = proj.get("icon") or {}
    icon_value = icon.get("name") if icon.get("kind") == "regular" else "projects"
    return {"title": proj["title"], "goal": proj.get("goal", ""),
            "icon": icon_value or "projects"}


def _persona_values(p: dict) -> dict:
    return {"display_name": p["display_name"], "role_title": p.get("role", {}).get("title", ""),
            "customer_type": p.get("segment", {}).get("customer_type", ""),
            "industry": p.get("company_context", {}).get("industry", "")}


# ------------------------------------------- the V10 detail-header actions composers
# Every editable kind: the "…" overflow with Edit (dialog) + Delete (confirm). `values`/
# `errors`/`edit_open` re-render the dialog OPEN with inline errors after a 400;
# `confirm_error` re-opens the typed-confirm delete the same way.

def project_actions(proj: dict, *, values: dict | None = None, errors: dict | None = None,
                    edit_open: bool = False, confirm_error: str = "") -> str:
    return detail_overflow(
        edit={"action": f'/jobs/{proj["id"]}/edit', "title": f'{proj["title"]} — {t("edit")}',
              "fields": project_fields(values if values is not None else _project_values(proj),
                                       errors or {}),
              "lead": t("project_form_lead"), "open_now": edit_open,
              "dialog_attrs": {"data-project-edit": proj["id"]}},
        delete={"action": f'/jobs/{proj["id"]}/delete', "label": t("delete_project"),
                "expected": proj["title"], "error": confirm_error})


def persona_actions(p: dict, *, values: dict | None = None, errors: dict | None = None,
                    edit_open: bool = False, confirm_error: str = "") -> str:
    return detail_overflow(
        edit={"action": f'/personas/{p["id"]}/edit', "title": f'{p["display_name"]} — {t("edit")}',
              "fields": persona_fields(values if values is not None else _persona_values(p),
                                       errors or {}),
              "lead": t("persona_form_lead"), "open_now": edit_open},
        delete={"action": f'/personas/{p["id"]}/delete', "label": t("delete_persona"),
                "expected": p["display_name"], "error": confirm_error})


def note_actions(note: dict, *, values: dict | None = None, errors: dict | None = None,
                 edit_open: bool = False) -> str:
    vals = values if values is not None else {"title": note.get("title", ""),
                                              "text": note.get("text", "")}
    return detail_overflow(
        edit={"action": f'/notes/{note["id"]}/edit',
              "title": f'{note.get("title") or t("notes_h")} — {t("edit")}',
              "fields": note_fields(vals, errors or {}), "open_now": edit_open},
        delete={"action": f'/notes/{note["id"]}/delete', "label": t("delete_note")})


def section_actions(sec: dict, *, values: dict | None = None, errors: dict | None = None,
                    edit_open: bool = False) -> str:
    vals = values if values is not None else {"title": sec["title"],
                                              "kind": sec.get("kind", "theme"),
                                              "note": sec.get("note", "")}
    return detail_overflow(
        edit={"action": f'/sections/{sec["id"]}/edit', "title": f'{sec["title"]} — {t("edit")}',
              "fields": section_fields(vals, errors or {}), "lead": t("section_form_lead"),
              "open_now": edit_open},
        delete={"action": f'/sections/{sec["id"]}/delete', "label": t("delete_section")})


def _dialog_error_page(store, *, title: str, crumbs: list, active: str, actions: str) -> str:
    """The V10 400 re-render of a dialog-submitted form: the entity headline as a calm
    backdrop, the SAME dialog re-opened over it with the inline errors (one renderer,
    one source — never a second form page)."""
    body = h("div", {"class_": "page"}, h("h1", {"class_": "h1"}, title))
    return _layout(title, str(body), store, crumbs=crumbs, active=active, actions=actions)


# ------------------------------------------------------------------- projects

def _project_form(store, proj: dict | None, values: dict, errors: dict,
                  confirm_error: str = "") -> str:
    """New + edit share one form (new renders only on the POST validation re-render —
    no GET form, U9); edit adds the header overflow with the typed-confirm delete."""
    new = proj is None
    title = t("new_project") if new else f'{proj["title"]} — {t("edit")}'
    action = "/jobs/new" if new else f'/jobs/{proj["id"]}/edit'
    cancel = "/jobs" if new else f'/jobs/{proj["id"]}'
    crumbs = ([(t("projects"), "/jobs"), (t("new_project"), None)] if new else
              [(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}'), (t("edit"), None)])
    actions = "" if new else overflow_delete(
        f'/jobs/{proj["id"]}/delete', t("delete_project"), expected=proj["title"],
        error=confirm_error)
    return form_page(
        store, title=title, crumbs=crumbs, active="projects", action=action,
        lead=t("project_form_lead"), fields=project_fields(values, errors),
        submit_label=t("create") if new else t("save"), cancel_href=cancel, actions=actions)


def _persona_form(store, p: dict, values: dict, errors: dict, confirm_error: str = "") -> str:
    """Persona METADATA only (name/role/segment/industry) — the profile prose and the
    generated SOUL stay host-authored (docs/web-mutations.md)."""
    actions = overflow_delete(
        f'/personas/{p["id"]}/delete', t("delete_persona"), expected=p["display_name"],
        error=confirm_error)
    return form_page(
        store, title=f'{p["display_name"]} — {t("edit")}', active="personas",
        crumbs=[(t("personas"), "/personas"), (p["display_name"], f'/personas/{p["id"]}'), (t("edit"), None)],
        action=f'/personas/{p["id"]}/edit', lead=t("persona_form_lead"),
        fields=persona_fields(values, errors),
        submit_label=t("save"), cancel_href=f'/personas/{p["id"]}', actions=actions)


def _note_form(store, proj: dict, note: dict | None, values: dict, errors: dict) -> str:
    new = note is None
    title = t("new_note") if new else f'{note.get("title") or t("notes_h")} — {t("edit")}'
    action = f'/jobs/{proj["id"]}/notes/new' if new else f'/notes/{note["id"]}/edit'
    cancel = f'/jobs/{proj["id"]}' if new else f'/notes/{note["id"]}'
    actions = "" if new else overflow_delete(f'/notes/{note["id"]}/delete', t("delete_note"))
    return form_page(
        store, title=title, active="library",
        crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}'), (title, None)],
        action=action, fields=note_fields(values, errors),
        submit_label=t("create") if new else t("save"), cancel_href=cancel, actions=actions)


def _section_form(store, proj: dict, sec: dict | None, values: dict, errors: dict) -> str:
    new = sec is None
    title = t("new_section") if new else f'{sec["title"]} — {t("edit")}'
    action = f'/jobs/{proj["id"]}/sections/new' if new else f'/sections/{sec["id"]}/edit'
    cancel = f'/jobs/{proj["id"]}' if new else f'/sections/{sec["id"]}'
    actions = "" if new else overflow_delete(f'/sections/{sec["id"]}/delete', t("delete_section"))
    return form_page(
        store, title=title, active="projects",
        crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}'), (title, None)],
        action=action, lead=t("section_form_lead"), fields=section_fields(values, errors),
        submit_label=t("create") if new else t("save"), cancel_href=cancel, actions=actions)


def register_edit(app) -> None:  # noqa: C901  (route table — one block per entity)
    from fastapi.responses import HTMLResponse

    # ---------------------------------------------------------------- projects
    # POST-only (U9): creation is API surface for hosts/automations — the UI renders no
    # create form; the 400 validation re-render below is the only place the form appears.
    @app.post("/jobs/new")
    async def project_create(request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "create_project")) is not None:
            return gate
        values = {k: _s(form, k) for k in ("title", "goal", "icon")}
        if "description" in form:  # API/back-compat surface; the browser form no longer shows it.
            values["description"] = _s(form, "description")
        if not values["title"]:
            return HTMLResponse(_project_form(store, None, values, {"title": t("field_required")}),
                                status_code=400)
        p = services.create_research_project(values["title"], goal=values["goal"],
                                             description=values["description"], store=store,
                                             icon=values["icon"] or "random")
        return see_other(f'/jobs/{p["id"]}')

    @app.get("/jobs/{project_id}/edit", response_class=HTMLResponse)
    def project_edit_form(project_id: str):
        store = Store()
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return not_found()
        return _project_form(store, proj, {"title": proj["title"], "goal": proj.get("goal", ""),
                                           "icon": _project_values(proj)["icon"]}, {})

    @app.post("/jobs/{project_id}/edit")
    async def project_update(project_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "update_project", {"project_id": project_id})) is not None:
            return gate
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return not_found()
        values = {k: _s(form, k) for k in ("title", "goal", "icon")}
        if "description" in form:  # Preserve existing descriptions unless an API caller sends one.
            values["description"] = _s(form, "description")
        if not values["title"]:
            return HTMLResponse(_dialog_error_page(
                store, title=proj["title"], active="projects",
                crumbs=[(t("projects"), "/jobs"), (proj["title"], f"/jobs/{project_id}"),
                        (t("edit"), None)],
                actions=project_actions(proj, values=values, errors={"title": t("field_required")},
                                        edit_open=True)), status_code=400)
        services.update_research_project(project_id, values, store=store)
        return see_other(f"/jobs/{project_id}")

    @app.post("/jobs/{project_id}/delete")
    async def project_delete(project_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_project", {"project_id": project_id})) is not None:
            return gate
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return not_found()
        if _s(form, "confirm") != proj["title"]:
            return HTMLResponse(_dialog_error_page(
                store, title=proj["title"], active="projects",
                crumbs=[(t("projects"), "/jobs"), (proj["title"], f"/jobs/{project_id}"),
                        (t("delete_project"), None)],
                actions=project_actions(proj, confirm_error=t("confirm_mismatch"))),
                status_code=400)
        try:
            services.delete_research_project(project_id, store=store)
        except ValueError as exc:
            if "PROJECT_DELETE_RUN_HISTORY_BLOCKED" not in str(exc):
                raise
            return HTMLResponse(_dialog_error_page(
                store, title=proj["title"], active="projects",
                crumbs=[(t("projects"), "/jobs"), (proj["title"], f"/jobs/{project_id}"),
                        (t("delete_project"), None)],
                actions=project_actions(proj, confirm_error=t("delete_run_history_blocked"))),
                status_code=409)
        return see_other("/jobs")

    # ---------------------------------------------------------------- personas
    @app.get("/personas/{persona_id}/edit", response_class=HTMLResponse)
    def persona_edit_form(persona_id: str):
        store = Store()
        p = store.get_persona(persona_id)
        if not p:
            return not_found(icon="personas", active="personas")
        return _persona_form(store, p, {
            "display_name": p["display_name"], "role_title": p.get("role", {}).get("title", ""),
            "customer_type": p.get("segment", {}).get("customer_type", ""),
            "industry": p.get("company_context", {}).get("industry", "")}, {})

    @app.post("/personas/{persona_id}/edit")
    async def persona_update(persona_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "update_persona", {"persona_id": persona_id})) is not None:
            return gate
        p = store.get_persona(persona_id)
        if not p:
            return not_found(icon="personas", active="personas")
        values = {k: _s(form, k) for k in ("display_name", "role_title", "customer_type", "industry")}
        if not values["display_name"]:
            return HTMLResponse(_dialog_error_page(
                store, title=p["display_name"], active="personas",
                crumbs=[(t("personas"), "/personas"), (p["display_name"], f"/personas/{persona_id}"),
                        (t("edit"), None)],
                actions=persona_actions(p, values=values,
                                        errors={"display_name": t("field_required")},
                                        edit_open=True)), status_code=400)
        services.update_persona(persona_id, {
            "display_name": values["display_name"],
            "role": {"title": values["role_title"]},
            "segment": {"customer_type": values["customer_type"]},
            "company_context": {"industry": values["industry"]},
        }, reason="web metadata edit", store=store)
        return see_other(f"/personas/{persona_id}")

    @app.post("/personas/{persona_id}/delete")
    async def persona_delete(persona_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_persona", {"persona_id": persona_id})) is not None:
            return gate
        p = store.get_persona(persona_id)
        if not p:
            return not_found(icon="personas", active="personas")
        if _s(form, "confirm") != p["display_name"]:
            return HTMLResponse(_dialog_error_page(
                store, title=p["display_name"], active="personas",
                crumbs=[(t("personas"), "/personas"), (p["display_name"], f"/personas/{persona_id}"),
                        (t("delete_persona"), None)],
                actions=persona_actions(p, confirm_error=t("confirm_mismatch"))),
                status_code=400)
        services.delete_persona(persona_id, store=store)
        return see_other("/personas")

    # ------------------------------------------------------------------- notes
    @app.post("/jobs/{project_id}/notes/new")
    async def note_create(project_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "create_note", {"project_id": project_id})) is not None:
            return gate
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return not_found()
        values = {k: _s(form, k) for k in ("title", "text")}
        if not values["text"]:
            return HTMLResponse(_note_form(store, proj, None, values, {"text": t("field_required")}),
                                status_code=400)
        note = services.create_note(project_id, values["text"], title=values["title"], store=store)
        return see_other(f'/notes/{note["id"]}')

    @app.get("/notes/{note_id}/edit", response_class=HTMLResponse)
    def note_edit_form(note_id: str):
        store = Store()
        try:
            data = services.get_note(note_id, store=store)
        except KeyError:
            return not_found(icon="panel", active="library")
        return _note_form(store, data["project"], data["note"],
                          {"title": data["note"].get("title", ""), "text": data["note"].get("text", "")}, {})

    @app.post("/notes/{note_id}/edit")
    async def note_update(note_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "update_note", {"note_id": note_id})) is not None:
            return gate
        try:
            data = services.get_note(note_id, store=store)
        except KeyError:
            return not_found(icon="panel", active="library")
        values = {k: _s(form, k) for k in ("title", "text")}
        if not values["text"]:
            note, proj = data["note"], data["project"]
            ntitle = note.get("title") or t("notes_h")
            return HTMLResponse(_dialog_error_page(
                store, title=ntitle, active="library",
                crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}'),
                        (ntitle, None)],
                actions=note_actions(note, values=values, errors={"text": t("field_required")},
                                     edit_open=True)), status_code=400)
        services.update_note(note_id, values, store=store)
        return see_other(f"/notes/{note_id}")

    @app.post("/notes/{note_id}/delete")
    async def note_delete(note_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_note", {"note_id": note_id})) is not None:
            return gate
        try:
            data = services.get_note(note_id, store=store)
        except KeyError:
            return not_found(icon="panel", active="library")
        services.delete_note(data["project"]["id"], note_id, store=store)
        return see_other(f'/jobs/{data["project"]["id"]}')

    # ---------------------------------------------------------------- sections
    @app.post("/jobs/{project_id}/sections/new")
    async def section_create(project_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "create_section", {"project_id": project_id})) is not None:
            return gate
        try:
            proj = services.get_research_project(project_id, store=store)
        except KeyError:
            return not_found()
        values = {k: _s(form, k) for k in ("title", "kind", "note")}
        if not values["title"]:
            return HTMLResponse(_section_form(store, proj, None, values,
                                              {"title": t("field_required")}), status_code=400)
        sec = services.create_section(project_id, values["title"], kind=values["kind"] or "theme",
                                      note=values["note"], store=store)
        return see_other(f'/sections/{sec["id"]}')

    @app.get("/sections/{section_id}/edit", response_class=HTMLResponse)
    def section_edit_form(section_id: str):
        store = Store()
        try:
            data = services.section_members(section_id, store=store)
        except KeyError:
            return not_found(icon="squareGrid")
        sec = data["section"]
        return _section_form(store, data["project"], sec,
                             {"title": sec["title"], "kind": sec.get("kind", "theme"),
                              "note": sec.get("note", "")}, {})

    @app.post("/sections/{section_id}/edit")
    async def section_update(section_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "update_section", {"section_id": section_id})) is not None:
            return gate
        try:
            data = services.section_members(section_id, store=store)
        except KeyError:
            return not_found(icon="squareGrid")
        values = {k: _s(form, k) for k in ("title", "kind", "note")}
        if not values["title"]:
            sec, proj = data["section"], data["project"]
            return HTMLResponse(_dialog_error_page(
                store, title=sec["title"], active="projects",
                crumbs=[(t("projects"), "/jobs"), (proj["title"], f'/jobs/{proj["id"]}'),
                        (sec["title"], None)],
                actions=section_actions(sec, values=values, errors={"title": t("field_required")},
                                        edit_open=True)), status_code=400)
        services.update_section(section_id, values, store=store)
        return see_other(f"/sections/{section_id}")

    @app.post("/sections/{section_id}/delete")
    async def section_delete(section_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_section", {"section_id": section_id})) is not None:
            return gate
        try:
            sec = services.get_section(section_id, store=store)
        except KeyError:
            return not_found(icon="squareGrid")
        services.delete_section(section_id, store=store)
        return see_other(f'/jobs/{sec["project_id"]}')

    # ------------------------------- studies/artifacts: DELETE only (no content editing)
    @app.post("/councils/{session_id}/delete")
    async def council_delete(session_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_council", {"council_id": session_id})) is not None:
            return gate
        if not store.get_council_session(session_id):
            return not_found(icon="councils", active="library")
        services.delete_council(session_id, store=store)
        return see_other("/councils")

    @app.post("/syntheses/{synthesis_id}/delete")
    async def synthesis_delete(synthesis_id: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_synthesis", {"synthesis_id": synthesis_id})) is not None:
            return gate
        if not store.get_synthesis(synthesis_id):
            return not_found(icon="syntheses", active="library")
        services.delete_synthesis(synthesis_id, store=store)
        return see_other("/syntheses")

    @app.post("/prototypes/{slug}/delete")
    async def prototype_delete(slug: str, request: Request):
        store = Store()
        form = await request.form()
        if (gate := write_gate(form, "delete_prototype", {"prototype": slug})) is not None:
            return gate
        try:
            p = services.get_prototype_artifact(slug, store=store)
        except PrototypeError:  # UNKNOWN_PROTOTYPE — the lookup's only input-triggered raise
            return not_found(icon="prototype", active="library")
        services.delete_prototype_artifact(p["id"], store=store)
        return see_other("/prototypes")
