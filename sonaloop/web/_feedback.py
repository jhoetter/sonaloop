"""Feedback button (ticket feedback-button): user-menu trigger -> small modal ->
POST through the _forms CSRF kit -> 303 thank-you. Plus the read-only /feedback admin
list (linked from the settings popover only — deliberately NOT in the main nav).

Chrome-module shaped like web/_tour.py: CSS via register_css, the trigger via the
user menu, the modal + JS via the "body_end" slot.

The modal is transparent about context: the current page path (filled client-side on
open; the no-JS fallback form at GET /feedback/new shows the referer-less empty value)
and the app version are DISPLAYED to the user and sent along — nothing is collected
silently. A prefilled "open a GitHub issue" link covers public installs that prefer a
public channel. Validation re-renders the standalone form page (400); the naive per-DB
rate limit answers 429 (services._feedback)."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request

from .. import services
from ..storage import Store
from ._i18n import t
from ._html import h, raw, fragment, register_css
from ._ext import register_slot

GITHUB_ISSUES_URL = "https://github.com/jhoetter/sonaloop/issues/new"


def _github_issue_href(page: str = "") -> str:
    """Prefilled public-channel alternative (title/body query params)."""
    body = ("<!-- feel free to write in German or English -->\n\n\n---\n"
            + f"App version: {services.app_version()}\npage: {page or '-'}")
    return GITHUB_ISSUES_URL + "?" + urlencode({"title": "Feedback: ", "body": body})


def _form_fields(message: str = "", email: str = "", page: str = "",
                 error: str = "") -> str:
    from ._forms import field
    ver = services.app_version()
    ctx = h("p", {"class_": "fb-ctx muted small"},
            t("feedback_context_l"), " ",
            h("code", {}, t("feedback_page_l"), " ", h("span", {"id": "fb-page-show"}, page or "—")),
            " · ", h("code", {}, t("feedback_version_l"), " ", ver))
    return fragment(
        raw(field("message", t("feedback_msg_l"), message, required=True, textarea=True,
                  error=error)),
        raw(field("email", t("feedback_email_l"), email)),
        h("input", {"type": "hidden", "name": "page", "id": "fb-page", "value": page}),
        ctx,
        h("p", {"class_": "small"},
          h("a", {"href": _github_issue_href(page), "id": "fb-gh", "target": "_blank",
                  "rel": "noopener"}, t("feedback_github"), " ↗")))


def _modal_markup(store) -> str:
    """The per-request dialog (CSRF field included) injected on every page."""
    from ._forms import csrf_field
    dlg = h("dialog", {"class_": "fb-dialog", "id": "fb-dialog"},
            h("form", {"method": "post", "action": "/feedback"},
              raw(csrf_field()),
              h("h3", {}, t("feedback_h")),
              _form_fields(),
              h("div", {"class_": "wform-actions"},
                h("button", {"class_": "sl-btn sl-btn--primary", "type": "submit"}, t("feedback_send")),
                h("button", {"class_": "sl-btn", "type": "button", "data-fb-close": True}, t("cancel")))))
    return dlg + FEEDBACK_JS


def register_feedback(app) -> None:
    from fastapi.responses import HTMLResponse

    from ._components import _layout, _empty_state
    from ._forms import csrf_field, see_other, write_gate

    def _form_page(store, *, message="", email="", page="", error="", status=200):
        """The no-JS fallback + validation re-render: the same fields as the modal."""
        body = h("div", {"class_": "page"},
                 h("h1", {"class_": "h1"}, t("feedback_h")),
                 h("form", {"class_": "wform", "method": "post", "action": "/feedback"},
                   raw(csrf_field()),
                   _form_fields(message, email, page, error),
                   h("div", {"class_": "wform-actions"},
                     h("button", {"class_": "sl-btn sl-btn--primary", "type": "submit"},
                       t("feedback_send")))))
        return HTMLResponse(_layout(t("feedback_h"), body, store,
                                    crumbs=[(t("feedback_h"), None)]), status_code=status)

    @app.get("/feedback/new", response_class=HTMLResponse)
    def feedback_new():
        return _form_page(Store())

    @app.get("/feedback/thanks", response_class=HTMLResponse)
    def feedback_thanks():
        store = Store()
        return _layout(t("feedback_h"),
                       _empty_state(t("feedback_thanks_h"), t("feedback_thanks_d"),
                                    icon="chat", action=(t("projects"), "/", "back")),
                       store, crumbs=[(t("feedback_h"), None)])

    @app.post("/feedback")
    async def feedback_submit(request: Request):
        form = await request.form()
        if (gate := write_gate(form, "feedback", {})) is not None:
            return gate
        store = Store()
        message = str(form.get("message") or "")
        email = str(form.get("email") or "")
        page = str(form.get("page") or "")
        try:
            services.submit_feedback(message, email=email, page=page, store=store)
        except ValueError:
            return _form_page(store, message=message, email=email, page=page,
                              error=t("field_required"), status=400)
        except services.FeedbackRateLimited:
            return HTMLResponse(_layout(t("feedback_h"),
                                        _empty_state(t("feedback_h"), t("feedback_rate_limited"),
                                                     icon="clock"), store),
                                status_code=429)
        return see_other("/feedback/thanks")

    @app.get("/feedback", response_class=HTMLResponse)
    def feedback_admin():
        """Read-only submissions list. Reachable from the settings popover only —
        feedback is an operator surface, not a navigation destination. Rendering
        the list IS the read event (unread count -> 0; `sonaloop info` mirrors it)."""
        store = Store()
        rows = []
        for fb in services.list_feedback(limit=200, mark_read=True, store=store):
            meta = " · ".join(x for x in (
                fb.get("created_at", "")[:16].replace("T", " "), fb.get("email") or "",
                fb.get("page") or "", fb.get("app_version") or "") if x)
            rows.append(h("div", {"class_": "fb-row"},
                          h("p", {"class_": "fb-msg"}, fb.get("message", "")),
                          h("p", {"class_": "muted small"}, meta)))
        body = h("div", {"class_": "page"},
                 h("h1", {"class_": "h1"}, t("feedback_h"),
                   h("span", {"class_": "h1cnt"}, str(len(rows))) if rows else None),
                 h("p", {"class_": "lead"}, t("feedback_lead")),
                 (fragment(*rows) if rows else
                  h("div", {"class_": "sl-empty"},
                    h("p", {"class_": "sl-empty__body"}, t("no_feedback")))))
        return _layout(t("feedback_h"), body, store, crumbs=[(t("feedback_h"), None)])


register_css(r"""
/* ---- feedback modal + admin list (web/_feedback.py) ---- */
.fb-dialog{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);
  color:var(--ink);padding:18px;width:min(440px,92vw)}
.fb-dialog::backdrop{background:rgba(0,0,0,.45)}
.fb-dialog h3{margin:0 0 12px}
.fb-dialog .sl-field{margin:0 0 12px}
.fb-ctx{margin:2px 0 10px}
.fb-ctx code{font-size:var(--t-xs)}
.fb-row{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);
  padding:11px 14px;margin:0 0 10px}
.fb-row .fb-msg{margin:0 0 6px;white-space:pre-wrap}
.fb-row p:last-child{margin:0}
""")


FEEDBACK_JS = r"""<script>(function(){
var dlg=document.getElementById('fb-dialog'); if(!dlg||!dlg.showModal) return;
function openDlg(){
  var p=location.pathname+location.search;
  var hid=document.getElementById('fb-page'); if(hid) hid.value=p;
  var show=document.getElementById('fb-page-show'); if(show) show.textContent=p;
  var gh=document.getElementById('fb-gh');
  if(gh){ gh.href=gh.href.replace(/page%3A\+[^&]*/,'page%3A+'+encodeURIComponent(p)); }
  var pop=document.querySelector('.sl-um-pop'); if(pop) pop.hidden=true;
  dlg.showModal();
  var ta=dlg.querySelector('textarea'); if(ta) ta.focus();
}
document.addEventListener('click',function(e){
  if(e.target.closest&&e.target.closest('[data-fb-open]')){ e.preventDefault(); openDlg(); return; }
  if(e.target.closest&&e.target.closest('[data-fb-close]')){ e.preventDefault(); dlg.close(); }
});
})();</script>"""


# Chrome wiring through the public seam: the per-request modal at body end. The trigger
# itself is rendered by the sidebar user menu, so Feedback has one visible home.
register_slot("body_end", _modal_markup)
