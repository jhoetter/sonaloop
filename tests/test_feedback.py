"""Feedback button (ticket feedback-button): submit happy path + validation + the naive
rate limit + the SONALOOP_FEEDBACK_WEBHOOK fan-out (mocked) + the /feedback admin page
and `sonaloop feedback` CLI listing + the unread count in `sonaloop info`."""
from __future__ import annotations

import json

import pytest

from sonaloop import services, web
from sonaloop.services import _feedback as fbmod
from sonaloop.web._i18n import STRINGS


def _client():
    from starlette.testclient import TestClient
    client = TestClient(web.create_app())
    client.get("/?lang=en")                    # primes the sl_csrf double-submit cookie
    return client


def _post(client, **data):
    payload = {"csrf_token": client.cookies.get("sl_csrf"), **data}
    return client.post("/feedback", data=payload, follow_redirects=False)


# ----------------------------------------------------------------------- service

def test_submit_happy_path_persists_with_transparent_context(store):
    fb = services.submit_feedback("The tour is great", email="x@y.z",
                                  page="/jobs?page=2", store=store)
    assert fb["message"] == "The tour is great" and fb["email"] == "x@y.z"
    assert fb["page"] == "/jobs?page=2" and fb["app_version"]
    rows = services.list_feedback(store=store)
    assert len(rows) == 1 and rows[0]["read_at"] is None
    assert services.unread_feedback_count(store=store) == 1


def test_submit_requires_a_message(store):
    with pytest.raises(ValueError):
        services.submit_feedback("   ", store=store)
    assert services.list_feedback(store=store) == []


def test_naive_rate_limit_caps_recent_submissions(store):
    for i in range(fbmod.RATE_LIMIT_MAX):
        services.submit_feedback(f"msg {i}", store=store)
    with pytest.raises(services.FeedbackRateLimited):
        services.submit_feedback("one too many", store=store)
    assert len(services.list_feedback(store=store)) == fbmod.RATE_LIMIT_MAX


def test_webhook_fired_best_effort(store, monkeypatch):
    """When SONALOOP_FEEDBACK_WEBHOOK is set the submission POSTs the JSON envelope
    through the ONE hook transport — and a dead webhook never fails the user path."""
    sent = []
    monkeypatch.setenv(fbmod.FEEDBACK_WEBHOOK_ENV, "https://hooks.example/fb")
    monkeypatch.setattr("sonaloop.services._hooks._deliver_webhook",
                        lambda target, envelope: (sent.append((target, envelope)) or (True, "HTTP 200")))
    fb = services.submit_feedback("hook me", page="/x", store=store)
    assert sent and sent[0][0] == "https://hooks.example/fb"
    env = sent[0][1]
    assert env["event"] == "feedback.submitted" and env["data"]["id"] == fb["id"]
    assert env["data"]["page"] == "/x" and env["data"]["app_version"]
    # dead webhook: logged, never raised, the row still lands
    monkeypatch.setattr("sonaloop.services._hooks._deliver_webhook",
                        lambda target, envelope: (_ for _ in ()).throw(OSError("down")))
    services.submit_feedback("still lands", store=store)
    assert len(services.list_feedback(store=store)) == 2


def test_no_webhook_env_means_no_delivery(store, monkeypatch):
    monkeypatch.delenv(fbmod.FEEDBACK_WEBHOOK_ENV, raising=False)
    called = []
    monkeypatch.setattr("sonaloop.services._hooks.deliver_notification",
                        lambda *a, **kw: called.append(a) or (True, ""))
    services.submit_feedback("quiet", store=store)
    assert not called


# ----------------------------------------------------------------------- web path

def test_web_submit_303_thanks_and_csrf_gate(store):
    client = _client()
    r = _post(client, message="From the modal", email="", page="/personas")
    assert r.status_code == 303 and r.headers["location"] == "/feedback/thanks"
    thanks = client.get("/feedback/thanks?lang=en").text
    assert STRINGS["en"]["feedback_thanks_h"] in thanks
    assert services.list_feedback(store=store)[0]["page"] == "/personas"
    # CSRF: a forged token never writes
    forged = client.post("/feedback", data={"csrf_token": "forged", "message": "nope"})
    assert forged.status_code == 403
    assert len(services.list_feedback(store=store)) == 1


def test_web_validation_rerenders_400_and_rate_limit_429(store):
    client = _client()
    bad = _post(client, message="   ")
    assert bad.status_code == 400
    assert STRINGS["en"]["field_required"] in bad.text
    for i in range(5):
        _post(client, message=f"w{i}")
    capped = _post(client, message="too much")
    assert capped.status_code == 429
    assert STRINGS["en"]["feedback_rate_limited"] in capped.text


def test_modal_chrome_trigger_context_and_github_link(store):
    html = _client().get("/?lang=en").text
    # user-menu trigger + the dialog with required message, optional email
    assert "data-fb-open" in html and 'id="fb-dialog"' in html
    assert STRINGS["en"]["feedback_msg_l"] in html and STRINGS["en"]["feedback_email_l"] in html
    # the transparent context line (page + app version, shown to the user)
    assert STRINGS["en"]["feedback_context_l"] in html
    assert services.app_version() in html
    # prefilled public-channel link
    assert "github.com/jhoetter/sonaloop/issues/new?title=" in html


def test_admin_page_lists_read_only_and_marks_read(store):
    services.submit_feedback("inbox item", email="a@b.c", page="/runs", store=store)
    client = _client()
    page = client.get("/feedback?lang=en").text
    assert "inbox item" in page and "a@b.c" in page and "/runs" in page
    assert STRINGS["en"]["feedback_lead"] in page
    assert services.unread_feedback_count(store=store) == 0      # viewing IS the read
    # The submit trigger lives in the user/settings popover only — never the nav/footer.
    home = client.get("/?lang=en").text
    pop = home.split('class="sl-um-pop"')[1].split("sl-um-trigger")[0]
    assert "data-fb-open" in pop
    nav = home.split('class="sl-sb-scroll"')[1].split("</div>")[0]
    assert 'href="/feedback"' not in nav and "data-fb-open" not in nav
    assert 'class="sl-nav sl-sb-foot"' not in home


# ----------------------------------------------------------------------- CLI / info

def test_cli_feedback_lists_recent_and_marks_read(store, capsys):
    from sonaloop import cli
    services.submit_feedback("cli reads me", page="/p", store=store)
    assert cli.main(["feedback", "--limit", "5"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["feedback"][0]["message"] == "cli reads me"
    assert out["unread_remaining"] == 0
    # --keep-unread peeks without consuming
    services.submit_feedback("still unread", store=store)
    assert cli.main(["feedback", "--keep-unread"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["unread_remaining"] == 1


def test_info_mentions_unread_feedback_count(store, capsys):
    from sonaloop import cli
    services.submit_feedback("count me", store=store)
    assert cli.main(["info"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["feedback_unread"] == 1
