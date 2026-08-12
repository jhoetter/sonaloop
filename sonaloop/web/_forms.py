"""Shared write-path helpers for the inspector's CRUD forms (ticket web-crud-structure).

The inspector grew a WRITE path for structural/metadata operations (projects, notes,
sections, persona metadata, deletes). The boundary stays HOST-AUTHORS-ALL-TEXT:
generated/authored prose (council statements, synthesis prose, memories, SOUL
content) is never editable here — see docs/web-mutations.md for the full contract.

The ONE pattern every write route follows:
  GET  /thing/{id}/edit  -> plain HTML form (this module's components)
  POST same URL          -> write_gate (CSRF + access guard)
                            -> validate -> service call -> 303 See Other
Creation is NOT a UI affordance (UX U9, ux-contract §8.4 — the inspector inspects + edits;
creation belongs to the MCP/CLI host): the POST /thing/new routes stay as API surface, but
no GET form and no "New …" button renders anywhere.
Failure codes: 400 validation (form re-rendered with inline errors), 403 CSRF or
guard denial, 404 unknown id. All mutations go through sonaloop.services — never
the Store directly — so lifecycle events / hooks / cloud guards keep working.

CSRF: DOUBLE-SUBMIT COOKIE (stateless — the app has no session store, and a signed
token would need a key to manage; the cookie comparison needs neither). The
middleware issues a random token in an `sl_csrf` cookie (SameSite=Lax, HttpOnly,
and Secure whenever the public/request/proxy origin is HTTPS)
and every form embeds the same token in a hidden field (csrf_field()). A POST is
accepted only when cookie and field match (constant-time compare). A cross-site
attacker can make the browser SEND the cookie but can neither read it nor set a
cookie on this origin, so it cannot forge the matching field.
"""
from __future__ import annotations

import contextvars
import hmac
import json
import os
import secrets
import urllib.parse

from .. import services
from ..storage import Store
from ._i18n import t
from ._components import _icon, _layout, _empty_state
from ._html import h, raw, fragment, register_css

CSRF_COOKIE = "sl_csrf"
_CSRF: contextvars.ContextVar[str] = contextvars.ContextVar("csrf_token", default="")


def _secure_cookie(request) -> bool:
    """Preserve HTTPS cookie semantics when Cloud terminates TLS at a proxy."""
    public_url = (os.getenv("SONALOOP_CLOUD_PUBLIC_URL") or "").strip()
    public_scheme = urllib.parse.urlsplit(public_url).scheme.lower()
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
    return (public_scheme == "https" or request.url.scheme == "https"
            or forwarded.lower() == "https")


def install_forms(app) -> None:
    """Install the CSRF middleware: every response is guaranteed a double-submit
    cookie, and the per-request token is exposed to csrf_field() via a contextvar
    (the same pattern as the UI-language middleware)."""

    @app.middleware("http")
    async def _csrf_cookie_middleware(request, call_next):
        token = request.cookies.get(CSRF_COOKIE) or ""
        fresh = not token
        if fresh:
            token = secrets.token_urlsafe(32)
        ctx = _CSRF.set(token)
        try:
            response = await call_next(request)
        finally:
            _CSRF.reset(ctx)
        if fresh:
            response.set_cookie(CSRF_COOKIE, token, max_age=60 * 60 * 24 * 365,
                                samesite="lax", httponly=True,
                                secure=_secure_cookie(request))
        return response


def csrf_field() -> str:
    """The hidden token field — embed in EVERY mutating <form>."""
    return h("input", {"type": "hidden", "name": "csrf_token", "value": _CSRF.get()})


def current_csrf_token() -> str:
    """Return the request token for trusted in-process subrequests.

    The SSR drawer renders a detail route through the same ASGI app before the outer
    response has had a chance to set a freshly issued cookie. Propagating this value
    into that subrequest keeps every embedded form on the outer request's token.
    """
    return _CSRF.get()


def csrf_ok(form) -> bool:
    """Double-submit check: the posted hidden field must equal the request cookie."""
    cookie, field = _CSRF.get(), str(form.get("csrf_token") or "")
    return bool(cookie) and bool(field) and hmac.compare_digest(cookie, field)


def write_gate(form, operation: str, resource: dict | None = None):
    """The shared front door of every POST route: CSRF first, then the cloud
    access-guard seam (services.check_access -> register_access_guard). Returns an
    error response to send back, or None to proceed. Operations are namespaced
    `web.<action>` so a tenancy guard can hold one editor+ rule for all web writes."""
    if not csrf_ok(form):
        return forbidden(t("csrf_invalid"))
    try:
        services.check_access("web." + operation, resource or {})
    except PermissionError:
        return forbidden(t("write_forbidden"))
    return None


def forbidden(message: str):
    from fastapi.responses import HTMLResponse
    store = Store()
    return HTMLResponse(_layout(t("not_allowed"), _empty_state(t("not_allowed"), message,
                                                               icon="warning"), store),
                        status_code=403)


def not_found(icon: str = "projects", active: str = "projects"):
    """The write-path 404 — same calm empty-state as read routes, but with a real
    404 status (forms post to ids that can vanish under them)."""
    from fastapi.responses import HTMLResponse
    store = Store()
    return HTMLResponse(_layout(t("not_found"), _empty_state(t("not_found"), t("runtime_maybe_cleared"),
                                                             icon=icon), store, active=active),
                        status_code=404)


def see_other(url: str):
    """POST-redirect-GET: every successful mutation answers 303 to the entity page."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url, status_code=303)


# --------------------------------------------------------------------- components

def field(name: str, label: str, value: str = "", *, error: str = "", required: bool = False,
          textarea: bool = False, hint: str = "") -> str:
    """One labeled form control (design-system .sl-field), with the inline error
    rendered under the control when server-side validation re-renders the form."""
    ctrl = (h("textarea", {"class_": "sl-textarea", "id": f"f-{name}", "name": name, "rows": "5"}, value)
            if textarea else
            h("input", {"class_": "sl-input", "id": f"f-{name}", "name": name, "type": "text",
                        "value": value}))
    return h("div", {"class_": "sl-field" + (" sl-field--invalid" if error else "")},
             h("label", {"class_": "sl-field__label", "for": f"f-{name}"}, label,
               h("span", {"class_": "sl-field__req"}, " *") if required else None),
             ctrl,
             h("p", {"class_": "sl-field__error"}, error) if error else None,
             h("p", {"class_": "sl-field__hint"}, hint) if hint else None)


def form_page(store, *, title: str, crumbs: list, active: str, action: str,
              fields: list, submit_label: str, cancel_href: str, lead: str = "",
              actions: str = "") -> str:
    """The shared form-page shell: heading, the POST form (CSRF field included),
    submit/cancel. `actions` is topbar HTML — the overflow delete on edit pages."""
    body = h("div", {"class_": "page"},
             h("h1", {"class_": "h1"}, title),
             h("p", {"class_": "lead"}, lead) if lead else None,
             h("form", {"class_": "wform", "method": "post", "action": action},
               raw(csrf_field()), fragment(*fields),
               h("div", {"class_": "wform-actions"},
                 h("button", {"class_": "sl-btn sl-btn--primary", "type": "submit"}, submit_label),
                 h("a", {"class_": "sl-btn", "href": cancel_href}, t("cancel")))))
    return _layout(title, body, store, crumbs=crumbs, active=active, actions=actions)


def menu_item(label: str, icon: str, dialog_id: str, *, danger: bool = False) -> str:
    """One overflow menu entry that opens a <dialog> by id (closing the popover first)."""
    return h("button", {"class_": "sl-menu-item" + (" sl-menu-item--danger" if danger else ""),
                        "type": "button",
                        "onclick": "this.closest('details').removeAttribute('open');"
                                   f"document.getElementById({json.dumps(dialog_id)}).showModal()"},
             raw(_icon(icon)), " ", label)


def overflow_menu(items, dialogs="") -> str:
    """The "…" header overflow (UX V10 — VISIBLE and CONSISTENT on every detail header): a
    native <details> popover (keyboard-toggleable without JS; _OVERFLOW_JS only adds
    Esc/outside-click dismiss) holding the entity's actions; the dialogs the items open ride
    along as siblings (showModal works from anywhere — the top layer)."""
    menu = h("details", {"class_": "sl-overflow"},
             h("summary", {"class_": "sl-iconbtn sl-iconbtn--ghost", "role": "button",
                           "aria-label": t("more_actions"), "title": t("more_actions")},
               raw(_icon("more"))),
             h("div", {"class_": "sl-popover sl-popover--bottom-end"}, fragment(*items)))
    return fragment(menu, dialogs, raw(_OVERFLOW_JS))


def edit_dialog(*, action: str, title: str, fields: list, lead: str = "",
                open_now: bool = False, dialog_id: str = "edit-dialog",
                dialog_attrs: dict | None = None) -> str:
    """The EDIT modal (UX V10, ux-contract §9: "edit pages sollten eher modale/dialoge
    sein"): a native <dialog> over the detail page carrying the SAME form fields the edit
    page renders (one source — the pages/edit.py field builders), posting to the SAME
    route. `open_now=True` re-opens it on the server's 400 re-render, so validation errors
    appear IN the dialog (the typed-confirm idiom)."""
    attrs = {"class_": "wdialog", "id": dialog_id}
    attrs.update(dialog_attrs or {})
    dlg = h("dialog", attrs,
            h("form", {"class_": "wform", "method": "post", "action": action},
              raw(csrf_field()),
              h("h3", {}, title),
              h("p", {"class_": "sl-field__hint"}, lead) if lead else None,
              fragment(*fields),
              h("div", {"class_": "wform-actions"},
                h("button", {"class_": "sl-btn sl-btn--primary", "type": "submit"}, t("save")),
                h("button", {"class_": "sl-btn", "type": "button",
                             "onclick": "this.closest('dialog').close()"}, t("cancel")))))
    reopen = (raw("<script>document.getElementById(" + json.dumps(dialog_id)
                  + ").showModal()</script>") if open_now else "")
    return fragment(dlg, reopen)


def confirm_delete_dialog(action: str, label: str, *, expected: str | None = None,
                          error: str = "", hint: str = "",
                          dialog_id: str = "del-dialog") -> str:
    """The confirm <dialog> behind every delete: with `expected` set (projects/personas)
    the user must TYPE the entity name and the SERVER re-checks `confirm == name` (the JS
    is convenience, never the protection — on mismatch the page re-renders with the inline
    `error` and the dialog re-opened); without it (notes/sections/councils/syntheses/
    prototypes) the same modal simply asks for confirmation."""
    confirm_row = (raw(field("confirm", t("confirm_type_name", name=expected),
                             error=error, required=True)) if expected is not None
                   else h("p", {}, t("delete_confirm_q")))
    dlg = h("dialog", {"class_": "danger-dialog", "id": dialog_id},
            h("form", {"method": "post", "action": action},
              raw(csrf_field()),
              h("h3", {}, label),
              confirm_row,
              h("p", {"class_": "sl-field__hint"}, hint or t("delete_hint")),
              h("div", {"class_": "wform-actions"},
                h("button", {"class_": "sl-btn btn-danger", "type": "submit"}, label),
                h("button", {"class_": "sl-btn", "type": "button",
                             "onclick": f"document.getElementById('{dialog_id}').close()"},
                  t("cancel")))))
    reopen = (raw("<script>document.getElementById(" + json.dumps(dialog_id)
                  + ").showModal()</script>") if error else "")
    return fragment(dlg, reopen)


def _dialog_id(prefix: str, action: str) -> str:
    """A document-UNIQUE dialog id derived from the POST action: the `?d=` SSR context view
    renders the background page AND the panel fragment in ONE document — fixed ids would
    make the panel's hoisted menu items showModal() the background page's dialog."""
    import re
    return prefix + "-" + re.sub(r"[^a-z0-9]+", "-", action.lower()).strip("-")


def detail_overflow(*, edit: dict | None = None, delete: dict | None = None) -> str:
    """THE detail-header actions (UX V10): ONE visible "…" overflow holding Edit (opens the
    edit <dialog> — kinds with editable structure) and/or Delete (opens the confirm dialog —
    kinds with a delete route), composed per kind:

        edit   = {action, title, fields[, lead, open_now]}   (edit_dialog kwargs)
        delete = {action, label[, expected, error]}          (confirm_delete_dialog args)

    Kinds without either render no overflow (pass nothing). Used by every detail page AND
    carried into the slide-over header (web/_drawer hoists [data-slide-actions])."""
    items, dialogs = [], []
    if edit:
        eid = _dialog_id("edit", edit["action"])
        edit_config = dict(edit)
        edit_label = str(edit_config.pop("label", "") or t("edit"))
        edit_icon = str(edit_config.pop("icon", "") or "pencil")
        items.append(menu_item(edit_label, edit_icon, eid))
        dialogs.append(raw(edit_dialog(**edit_config, dialog_id=eid)))
    if delete:
        did = _dialog_id("del", delete["action"])
        items.append(menu_item(delete["label"], "trash", did, danger=True))
        dialogs.append(raw(confirm_delete_dialog(
            delete["action"], delete["label"], expected=delete.get("expected"),
            error=delete.get("error", ""), hint=delete.get("hint", ""), dialog_id=did)))
    if not items:
        return ""
    return overflow_menu(items, fragment(*dialogs))


def overflow_delete(action: str, label: str, *, expected: str | None = None,
                    error: str = "") -> str:
    """The delete-only overflow (UX U9, ux-contract §8.4: subtle, never a danger zone) —
    councils/syntheses/prototypes (recorded artifacts: no content editing) and the
    deep-link edit pages keep this thin wrapper over the V10 builders."""
    return detail_overflow(delete={"action": action, "label": label,
                                   "expected": expected, "error": error})


# Light-dismiss for the overflow <details> (Esc + outside click) — enhancement only; the
# summary itself toggles natively. Idempotent across multiple renders on one page.
_OVERFLOW_JS = """
<script>(function(){if(window.__slov)return;window.__slov=1;
document.addEventListener('click',function(e){
  document.querySelectorAll('details.sl-overflow[open]').forEach(function(d){
    if(!d.contains(e.target))d.removeAttribute('open');});});
document.addEventListener('keydown',function(e){if(e.key==='Escape')
  document.querySelectorAll('details.sl-overflow[open]').forEach(function(d){d.removeAttribute('open');});});
if(!window.__slDialogDismiss){window.__slDialogDismiss=1;
document.addEventListener('click',function(e){
  var d=e.target&&e.target.closest&&e.target.closest('dialog.wdialog,dialog.danger-dialog');
  if(!d||e.target!==d||!d.open)return;
  var r=d.getBoundingClientRect();
  if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();
});}
})();</script>
"""


# Co-located CSS (spec/roadmap.md R3): the write-form shell, the overflow menu + the modals.
register_css(r"""
/* ---- write forms (web CRUD) ---- */
.wform{max-width:560px;display:flex;flex-direction:column;gap:14px;margin-top:10px}
.wform-actions{display:flex;gap:10px;margin-top:6px}
.btn-danger{border-color:var(--red,#ea4335);color:var(--red,#ea4335)}
.btn-danger:hover{background:var(--red,#ea4335);border-color:var(--red,#ea4335);color:#fff}
/* ---- the overflow ("…") menu (U9/V10): a quiet header affordance, not a red block ---- */
.sl-overflow{position:relative;display:inline-flex}
.sl-overflow>summary{list-style:none;cursor:pointer}
.sl-overflow>summary::-webkit-details-marker{display:none}
.sl-overflow .sl-popover{min-width:170px}
.sl-menu-item--danger{color:var(--red,#ea4335)}
.sl-menu-item--danger svg{width:15px;height:15px;color:var(--red,#ea4335)}
.sl-menu-item--danger:hover{background:color-mix(in srgb,var(--red,#ea4335) 10%,transparent)}
/* ---- the modals: the typed-confirm delete + the V10 edit dialog (one visual idiom) ---- */
.danger-dialog,.wdialog{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);color:var(--ink);padding:18px}
.danger-dialog{max-width:420px}
.wdialog{width:min(560px,92vw);max-height:90vh;overflow:auto}
.danger-dialog h3,.wdialog h3{margin:0 0 12px}
.danger-dialog p{margin:0 0 6px;color:var(--muted)}
.wdialog .wform{max-width:none;margin-top:0}
.danger-dialog::backdrop,.wdialog::backdrop{background:rgba(0,0,0,.45)}
""")
