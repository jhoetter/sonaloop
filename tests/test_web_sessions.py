"""Session replay inspector (ticket session-replay-inspector) — web smoke tests.

The list page (empty + populated + the ≥2-sessions funnel), the replay view (per-step anchors,
friction rail, screenshots only when the file exists), the read-only screenshot route (serves a real
file, rejects traversal), session-ref deep links on council pages, and the persona/prototype/project
cross-link sections.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest
from starlette.testclient import TestClient

from conftest import create_persona
from sonaloop import artifacts, browser, config, prototypes, services, web


_PROTO = {"kind": "prototype", "id": "proto-signup", "label": "Signup prototype"}


def _step(i, *, friction="none", would_continue=True, reason="", monologue=None, **state):
    return {
        "index": i,
        "action": {"type": "click", "target": f"button-{i}", "detail": f"clicked button {i}"},
        "monologue": monologue if monologue is not None else f"thinking aloud at step {i}",
        "state": {"screen": f"screen-{i}", **state},
        "friction": {"level": friction, "note": "label was ambiguous" if friction != "none" else ""},
        "verdict": {"would_continue": would_continue, "reason": reason},
    }


def _record(store, *, steps=None, outcome=None, persona_id="pX", subject=None, **kw):
    return services.record_usability_session(
        persona_id, subject or _PROTO, "prototype", "2026-06-10",
        steps if steps is not None else [_step(0), _step(1)],
        outcome if outcome is not None else
        {"completed": True, "dropoff_step": None, "summary": "walked it", "predicted_behaviors": []},
        store=store, **kw)["usability_session"]


def _client():
    return TestClient(web.create_app())


# ----------------------------------------------------------------------------- ref deep links

def test_session_ref_href_maps_step_anchor_to_dom_id():
    assert artifacts.ref_href({"kind": "session", "id": "u1", "anchor": "step:3"}) == "/sessions/u1#step-3"
    # a whole-session ref (no anchor) links to the session page
    assert artifacts.ref_href({"kind": "session", "id": "u1"}) == "/sessions/u1"


# ----------------------------------------------------------------------------- list page

def test_sessions_list_renders_empty_and_populated(store):
    client = _client()
    html = client.get("/sessions?lang=en").text
    assert "no sessions" in html
    sess = _record(store)
    html = client.get("/sessions?lang=en").text
    # the URL stays canonical; the content is the LIBRARY with the Sessions tab active
    # (ux-contract §3.5): one sl-entity row per walk — subject desc and the slide-over armed
    # with the row's own canonical URL (§8.1). V2 row truth: the step count lives on the
    # detail/slide-over, never as a row chip.
    assert f'/sessions/{sess["id"]}' in html
    assert "Signup prototype" in html and "2 steps" not in html
    assert f'data-drawer="/sessions/{sess["id"]}"' in html
    # the project filter narrows honestly
    assert f'/sessions/{sess["id"]}' not in client.get("/sessions?project=nope&lang=en").text


def test_funnel_renders_only_with_two_or_more_sessions_of_one_subject(store):
    client = _client()
    _record(store, key="A", steps=[_step(0), _step(1), _step(2)])
    url = "/sessions?subject_kind=prototype&subject=proto-signup&lang=en"
    assert "Funnel" not in client.get(url).text                    # one walk is no funnel
    _record(store, key="B",
            steps=[_step(0), _step(1, friction="blocked", would_continue=False,
                                   reason="could not find the next button")],
            outcome={"completed": False, "dropoff_step": 1, "summary": "gave up",
                     "predicted_behaviors": []})
    html = client.get(url).text
    assert "Funnel" in html and "could not find the next button" in html
    assert "Step 1" in html and "entered" in html and "dropped" in html
    # without a subject filter the funnel stays off (it is a per-subject read)
    assert "Funnel" not in client.get("/sessions?lang=en").text


# ----------------------------------------------------------------------------- replay view

def test_replay_renders_step_anchors_friction_rail_and_verdicts(store):
    sess = _record(store, steps=[
        _step(0),
        _step(1, friction="confusion", url="https://example.test/x", title="Signup"),
        _step(2, friction="blocked", would_continue=False, reason="dead end"),
    ], outcome={"completed": False, "dropoff_step": 2, "summary": "bounced",
                "predicted_behaviors": []})
    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    # every step is addressable; the friction rail jumps to the friction steps only
    assert 'id="step-0"' in html and 'id="step-1"' in html and 'id="step-2"' in html
    assert "Friction points" in html and 'href="#step-1"' in html and 'href="#step-2"' in html
    # no screenshot file -> the screen TEXT excerpt, no <img> in the timeline
    assert "sess-screen-txt" in html and "screen-1" in html and "/sessions-files/" not in html
    # think-aloud, action chip + target, per-step verdict, outcome banner
    assert "thinking aloud at step 1" in html and "button-2" in html
    assert "would continue" in html and "would drop" in html and "dead end" in html
    assert "Dropped at step 2" in html
    # friction accents come from the data-driven scale colors (friction_levels.json)
    assert "--sfc:var(--amber)" in html and "--sfc:var(--red)" in html
    # an unknown id renders the honest empty state
    assert "Session not found" in _client().get("/sessions/usession_missing?lang=en").text


def test_replay_shows_screenshot_img_only_when_the_file_exists(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    sess_id = services.stable_id("usession", "shots")
    d = config.sessions_dir() / sess_id
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"\x89PNG fake")
    shot = _step(0)
    shot["state"]["screenshot"] = "step-0.png"
    sess = _record(store, steps=[shot, _step(1)], key="shots")
    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    assert f'<img class="sess-shot" src="/sessions-files/{sess_id}/step-0.png"' in html
    # step 1 has no screenshot -> text excerpt
    assert "sess-screen-txt" in html and "screen-1" in html


def test_reading_flow_renders_large_focused_screens_without_extra_controls(
        store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    sess_id = services.stable_id("usession", "reading-flow")
    d = config.sessions_dir() / sess_id
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"\x89PNG focused")
    step = _step(0, screenshot="step-0.png", focus={
        "x": 11, "y": 18.5, "width": 78, "height": 20,
        "label": "Hero · value proposition",
    }, monologue="The big promise tells me what this wants to be.")
    sess = _record(store, steps=[step], key="reading-flow")
    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    assert "Reading flow" in html and "not eye-tracking" in html
    assert 'class="sess-step sl-session-focus-step"' in html
    assert 'class="sl-session-lens"' in html and 'class="sl-session-focus"' in html
    assert "--fx:11%;--fy:18.5%;--fw:78%;--fh:20%" in html
    assert "Hero · value proposition" in html
    assert "The big promise tells me" in html
    # The reading path is linear; generic prototype transport and persona/task pickers do not leak in.
    assert "data-proto-expand" not in html and "Animation" not in html
    # A positive continue verdict is intentionally quiet; the session outcome follows the flow.
    assert "would continue" not in html
    assert html.index('id="sec-replay"') < html.index("walked it")


def test_artifact_reading_flow_reuses_project_asset_pixels(store, tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    proj = services.create_research_project("Screenshot reading flow", store=store)
    shot = tmp_path / "stimulus.png"
    Image.new("RGB", (600, 1933), "white").save(shot)
    asset = services.attach_asset(
        proj["id"], path=str(shot), kind="screenshot", title="Mobile banking overview",
        store=store,
    )
    step = _step(0, focus={
        "x": 8, "y": 12, "width": 62, "height": 18,
        "label": "Primary activation entry",
    })
    step["state"] = {
        "screen": asset["id"], "title": "Mobile banking overview",
        "focus": step["state"]["focus"],
    }
    sess = services.record_usability_session(
        "pX", {"kind": "flow", "id": "flow-mobile", "label": "Mobile flow"},
        "artifact", "2026-08-12", [step],
        {"completed": True, "dropoff_step": None, "summary": "read it",
         "predicted_behaviors": []},
        project_id=proj["id"], key="artifact-reading-flow", store=store,
    )["usability_session"]

    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    assert f'<img class="sess-shot" src="{asset["url"]}"' in html
    assert 'class="sl-session-lens sl-session-crop"' in html
    assert 'data-focus-source="full-screenshot"' in html
    assert "--shot-max:600px" in html and "--crop-y:-7%" in html
    assert "--fy:17.8571%" in html and "--fh:64.2857%" in html
    assert "Primary activation entry" in html
    assert 'class="sl-session-replay-mode"' in html
    assert ".sl-drawer:has(.sl-session-replay-mode) .sl-drawer__panel" in html
    assert '<div class="sess-screen-txt">' not in html

    slide = _client().get(f'/sessions/{sess["id"]}?slide=1&lang=en').text
    assert 'class="sl-session-replay-mode"' in slide


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_artifact_reading_flow_uses_compact_wide_drawer_in_real_browser(
        store, tmp_path, monkeypatch):
    """The actual inspection journey: the project opens a wide, evidence-first replay; every
    long screenshot is bounded to one reading moment, metadata follows, and mobile stacks."""
    from PIL import Image
    import uvicorn
    from playwright.sync_api import sync_playwright

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    proj = services.create_research_project("Compact reading flow", store=store)
    shot = tmp_path / "long-page.png"
    Image.new("RGB", (600, 1933), "white").save(shot)
    asset = services.attach_asset(
        proj["id"], path=str(shot), kind="screenshot", title="Long banking page", store=store,
    )
    steps = []
    for i, y in enumerate((7, 28, 51, 72)):
        step = _step(i, focus={
            "x": 6, "y": y, "width": 88, "height": 12, "label": f"Reading moment {i + 1}",
        }, monologue=f"I read moment {i + 1} before deciding what comes next.")
        step["state"] = {
            "screen": asset["id"], "title": "Long banking page",
            "focus": step["state"]["focus"],
        }
        steps.append(step)
    sess = services.record_usability_session(
        "pX", {"kind": "flow", "id": "flow-compact", "label": "Compact flow"},
        "artifact", "2026-08-12", steps,
        {"completed": True, "dropoff_step": None, "summary": "read it",
         "predicted_behaviors": []},
        project_id=proj["id"], key="compact-browser", store=store,
    )["usability_session"]

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        web.create_app(), host="127.0.0.1", port=port, log_level="error",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "app did not boot"
        time.sleep(0.05)

    try:
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            for width, height in ((1440, 900), (390, 844)):
                page = chromium.new_context(viewport={"width": width, "height": height}).new_page()
                page.goto(f"http://127.0.0.1:{port}/jobs/{proj['id']}?lang=en", wait_until="load")
                entry = page.locator(f'a[href="/sessions/{sess["id"]}"][data-drawer]').first
                assert entry.is_visible()
                entry.click()
                drawer = page.locator("#drawer.is-open")
                drawer.wait_for(state="visible")
                drawer.locator(".sl-session-crop").first.wait_for(state="visible")
                page.wait_for_timeout(300)

                panel = drawer.locator(".sl-drawer__panel").bounding_box()
                assert panel
                if width > 840:
                    assert panel["width"] >= 1100
                else:
                    assert panel["width"] >= width - 1

                replay = drawer.locator("#sec-replay").bounding_box()
                props = drawer.locator("#sec-properties").bounding_box()
                assert replay
                if width > 1040:
                    assert props and replay["y"] < props["y"]
                else:
                    # The existing compact breakpoint suppresses the generic metadata rail.
                    assert props is None
                for crop in drawer.locator(".sl-session-crop").all():
                    box = crop.bounding_box()
                    assert box and box["height"] <= 390
                    assert box["x"] >= 0 and box["x"] + box["width"] <= width + 1
                    if width > 840:
                        assert box["width"] <= 600.5  # never blur by upscaling the source
                    else:
                        assert box["width"] >= width - 70
                first_step = drawer.locator(".sl-session-focus-step").first.bounding_box()
                assert first_step and first_step["height"] <= (480 if width > 840 else 520)
                page.context.close()
            chromium.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_hosted_session_file_provider_replaces_local_runtime_path(store):
    web.register_session_file_url_provider(
        lambda session_dir, path: f"/signed-session/{session_dir}/{path}")
    try:
        shot = _step(0, screenshot="step-0.png")
        # The writer checks the actual file, so persist without a shot and stamp this fixture's
        # already-validated record to isolate the hosted render seam.
        sess = _record(store, steps=[_step(0)], key="hosted-shot")
        sess["steps"] = [shot]
        store.insert_usability_session(sess)
        html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
        assert f'/signed-session/{sess["id"]}/step-0.png' in html
        assert "/sessions-files/" not in html
    finally:
        web.register_session_file_url_provider(None)


def test_screenshot_route_serves_real_files_and_rejects_traversal(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = config.sessions_dir() / "u1"
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"png-bytes")
    secret = tmp_path / "secret.txt"
    secret.write_text("not yours")
    client = _client()
    ok = client.get("/sessions-files/u1/step-0.png")
    assert ok.status_code == 200 and ok.content == b"png-bytes"
    # traversal out of the sessions dir -> 404, never a file read
    for path in ("/sessions-files/..%2Fsecret.txt", "/sessions-files/u1/..%2F..%2Fsecret.txt",
                 "/sessions-files/%2e%2e/%2e%2e/etc/passwd"):
        assert client.get(path).status_code == 404
    assert client.get("/sessions-files/u1/missing.png").status_code == 404


# ----------------------------------------------------------------------------- evidence deep links

def test_council_session_refs_render_as_replay_deep_links(store):
    proj = services.create_research_project("P", store=store)
    pid = create_persona(store, "Greta Tester")
    sess = _record(store, persona_id=pid, project_id=proj["id"])
    council = services.record_council(
        proj["id"], "Did the prototype hold up?", [pid],
        statements=[{"persona_id": pid, "text": "The second screen lost me.",
                     "refs": [{"kind": "session", "id": sess["id"], "anchor": "step:1"},
                              {"kind": "session", "id": sess["id"]}]}],
        key="c1", store=store)
    html = _client().get(f'/councils/{council["id"]}?lang=en').text
    assert f'/sessions/{sess["id"]}#step-1' in html               # anchored -> the exact step
    assert f'href="/sessions/{sess["id"]}"' in html               # whole-session ref -> the session page


# ----------------------------------------------------------------------------- cross-link sections

def test_persona_page_lists_its_sessions(store):
    pid = create_persona(store, "Heinz Walker")
    sess = _record(store, persona_id=pid)
    html = _client().get(f"/personas/{pid}?lang=en").text
    assert f'/sessions/{sess["id"]}' in html and "Signup prototype" in html


def test_project_page_lists_its_sessions(store):
    proj = services.create_research_project("Q", store=store)
    sess = _record(store, project_id=proj["id"])
    html = _client().get(f'/jobs/{proj["id"]}?lang=en').text
    assert f'/sessions/{sess["id"]}' in html


# ----------------------------------------------------------------- sessions IN the project outline
# (tickets project-page-sessions-live-under-their-subject-in-the-outlin + outline-drops-study-nodes-
# on-plan-less-projects): sessions render as indented child rows under their SUBJECT row inside the
# outline; the appended flat section is gone from the project page (it stays on /sessions and the
# persona/prototype pages — covered by the cross-link tests above).


def _proto_project(store, title="Q"):
    proj = services.create_research_project(title, store=store)
    proto = prototypes.register_prototype("proto-signup", "Signup prototype", "prototypes/signup",
                                          project_id=proj["id"], store=store)
    return proj, proto


def test_project_outline_nests_sessions_under_their_subject(store):
    proj, proto = _proto_project(store)
    pid = create_persona(store, "Greta Tester")
    sess = _record(store, persona_id=pid, project_id=proj["id"],
                   subject={"kind": "prototype", "id": proto["id"], "label": "Signup prototype"})
    html = _client().get(f'/jobs/{proj["id"]}?lang=en').text
    # the appended flat section is gone — sessions live IN the outline now
    assert 'id="sec-sessions"' not in html
    # the subject (prototype) row precedes its session child row, which carries the tree-connector
    # indent classes (the note→prototype nesting mechanics)
    assert html.index(f'data-oid="{proto["id"]}"') < html.index(f'data-oid="{sess["id"]}"')
    assert f'class="olrow ol-tw ol-last" data-oid="{sess["id"]}"' in html
    # child row content: persona name, generic session icon/title metadata, replay href
    assert "Greta Tester" in html and 'title="Session"' in html
    assert f'href="/sessions/{sess["id"]}"' in html
    # sessions no longer render aggregate/count chips in the outline.
    assert 'class="ol-funnel"' not in html


def test_project_outline_parent_row_stays_tag_free_with_multiple_sessions(store):
    proj, proto = _proto_project(store)
    subj = {"kind": "prototype", "id": proto["id"], "label": "Signup prototype"}
    _record(store, key="A", project_id=proj["id"], subject=subj,
            steps=[_step(0), _step(1), _step(2)])
    _record(store, key="B", project_id=proj["id"], subject=subj,
            steps=[_step(0), _step(1, friction="blocked", would_continue=False, reason="lost")],
            outcome={"completed": False, "dropoff_step": 1, "summary": "gave up",
                     "predicted_behaviors": []})
    html = _client().get(f'/jobs/{proj["id"]}?lang=en').text
    # session rows still nest under the prototype, but counts/drop-off tags stay out of the outline.
    assert html.count('data-rkind="session"') == 2
    assert "2 sessions · 1× drop @ step 1" not in html
    assert 'class="ol-funnel"' not in html and 'class="ol-stretch"' not in html
    assert "Dropped at step 1" not in html and "1× friction" not in html


def test_project_outline_renders_live_url_use_as_a_session_row(store):
    proj = services.create_research_project("L", store=store)
    pid = create_persona(store, "Lena Live")
    subj = {"kind": "live_url", "url": "https://example.test/checkout", "label": "Checkout live"}
    sess = services.record_usability_session(
        pid, subj, "live", "2026-06-10",
        [_step(0, url="https://example.test/checkout", title="Checkout Example"), _step(1)],
        {"completed": True, "dropoff_step": None, "summary": "done", "predicted_behaviors": []},
        project_id=proj["id"], store=store)["usability_session"]
    html = _client().get(f'/jobs/{proj["id"]}?lang=en').text
    # No synthesized LIVE SURFACE parent: the replay itself is the visible primitive.
    assert 'data-rkind="live_url"' not in html
    assert "Live surface" not in html
    assert f'href="/sessions/{sess["id"]}"' in html and "Session" in html


def test_freeform_project_outline_shows_project_synthesis_nodes_and_compacts(store):
    # A project-bound synthesis must render as an outline row even when the project only has the
    # default freeform frame plan.
    proj = services.create_research_project("Freeform", store=store)
    services.record_synthesis("Pains", "What hurts?", project_id=proj["id"],
                              payload={"status": "done", "gesamtbild": "big picture"},
                              synthesis_id="syn0", store=store)
    html = _client().get(f'/jobs/{proj["id"]}?lang=en').text
    assert "Pains" in html and 'href="/syntheses/syn0"' in html
    # a near-empty outline sizes to content instead of pinning a viewport-high dead zone
    assert "ol-compact" in html


# --------------------------------------------------- prototype reaction sessions (UX U7, §8.2)
# A protosession_* record is the OTHER first-class session kind: it lists in the Library's
# Sessions tab through the SAME row vocabulary and serves a FULL detail page on /sessions/{id}
# (one route, the record decides; the slide-over renders its ?slide=1 variant) — persona +
# prototype header with the verified badge, verdict lead, liked/friction reads, the per-step
# timeline reusing the replay renderer (screenshots from the retained browser-session dir),
# predicted behaviors.


def _proto_reaction(**kw):
    base = {
        "summary": "tested the journey end to end",
        "verdict": "Two of three objections fixed; the delivery channel stays open.",
        "liked": ["the counter-proposal speaks my chosen block"],
        "friction": ["the trigger is still a calendar invite"],
        "steps": [
            {"index": 0, "action": {"type": "look", "target": "Screen 1", "detail": "first look"},
             "monologue": "thinking aloud at proto step 0", "state": {"screen": "proto-screen-0"},
             "friction": {"level": "none", "note": ""},
             "verdict": {"would_continue": True, "reason": "clear"}},
            {"index": 1, "action": {"type": "click", "target": "Button X", "detail": "clicked X"},
             "monologue": "thinking aloud at proto step 1", "state": {"screen": "proto-screen-1"},
             "friction": {"level": "hesitation", "note": "unusual pattern"},
             "verdict": {"would_continue": True, "reason": "works"}},
        ],
        "predicted_behaviors": [
            {"action": "sets the EN block as a status text", "step": 1, "likelihood": "likely",
             "trigger": "next week's daily huddles", "refs": []}],
        "observed_state_refs": ["proto-screen-0", "proto-screen-1"],
    }
    base.update(kw)
    return base


def _proto_session(store, **kw):
    proj = services.create_research_project("PS", store=store)
    proto = prototypes.register_prototype("proto-journey", "Journey prototype", "prototypes/j",
                                          project_id=proj["id"], store=store)
    pid = create_persona(store, "Greta Walker")
    sess = services.record_prototype_session(
        pid, proto["id"], "psession_test", "2026-06-11", _proto_reaction(**kw),
        key="ps1", store=store)["prototype_session"]
    return proj, proto, pid, sess


def test_prototype_session_full_detail_page(store):
    from sonaloop.web._i18n import STRINGS
    proj, proto, pid, sess = _proto_session(store)
    assert sess["id"].startswith("protosession_")
    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    # shared header anatomy (§8.2): kind eyebrow, prototype title, persona chip
    assert STRINGS["en"]["session_kind_prototype"] in html
    assert "Journey prototype" in html and "Greta Walker" in html
    # verdict lead + liked/friction reads + predicted behaviors
    assert "Two of three objections fixed" in html
    assert STRINGS["en"]["proto_liked_h"] in html and "counter-proposal" in html
    assert STRINGS["en"]["friction_rail_h"] in html and "calendar invite" in html
    assert STRINGS["en"]["predicted_behaviors_h"] in html and "status text" in html
    # V3: the likelihood renders as the vendored labeled %-with-mini-bar contract — a "likely"
    # level shows "70 %" (thin space, exactly like the DS <Likelihood>), the level name on
    # hover, the high tone — never a bare token/number
    assert "sl-likelihood" in html and "70 %" in html and "sl-likelihood--high" in html
    assert STRINGS["en"]["likelihood_likely"] in html        # the scale label, not the raw token
    # the per-step timeline reuses the replay renderer: anchors, monologue, friction accent
    assert 'id="step-0"' in html and 'id="step-1"' in html
    assert "thinking aloud at proto step 1" in html
    assert "--sfc:var(--accent)" in html                     # hesitation accent from the scale
    # no screenshot files for this session id -> text screens, no <img> rows
    assert "proto-screen-0" in html and 'class="sess-shot"' not in html
    # the properties rail: prototype + project links, the unverified grounding read
    assert f'/prototypes/{proto["slug"]}' in html and f'/jobs/{proj["id"]}' in html
    assert STRINGS["en"]["grounded_no"] in html              # no live session log -> unverified


def test_prototype_session_uses_top_level_durable_steps_in_vm_and_replay(store):
    """Recorder-derived browser snapshots remain visible/countable without authored reaction steps."""
    from sonaloop.web.pages.sessions import proto_session_vm

    _proj, _proto, _pid, sess = _proto_session(store, steps=[], timeline=[])
    sess["steps"] = [
        {"index": 0, "action": {"type": "open"},
         "state": {"url": "https://example.test/start", "title": "Start"}},
        {"index": 1, "action": {"type": "click", "target": "e1"},
         "state": {"url": "https://example.test/result", "title": "Result"}},
    ]
    store.insert_prototype_session(sess)

    vm = proto_session_vm(store.get_prototype_session(sess["id"]), store)
    assert len(vm["steps"]) == 2
    assert vm["steps"][1]["state"]["title"] == "Result"

    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    assert 'id="step-0"' in html and 'id="step-1"' in html
    assert "https://example.test/start · Start" in html
    assert "https://example.test/result · Result" in html


def test_prototype_sessions_list_in_library_tab_and_slideover(store):
    proj, proto, pid, sess = _proto_session(store)
    client = _client()
    html = client.get("/sessions?lang=en").text
    # one row vocabulary: persona title, subject desc, canonical href = drawer URL
    # (V2 row truth: no step-count chip — the count lives on the detail/slide-over)
    assert f'/sessions/{sess["id"]}' in html
    assert "Greta Walker" in html and "Journey prototype" in html and "2 steps" not in html
    assert f'data-drawer="/sessions/{sess["id"]}"' in html
    # the slide-over fragment serves the FULL detail content (no 500 on protosession ids):
    # the verdict lead and the step timeline, not an essence preview
    slide = client.get(f'/sessions/{sess["id"]}?slide=1&lang=en')
    assert slide.status_code == 200 and "Two of three objections fixed" in slide.text
    assert 'id="step-1"' in slide.text                       # the full timeline rides along
    assert slide.text.startswith('<div class="sl-slide">') and "sl-sidebar" not in slide.text
    # the prototype detail page rows its sessions through the same vocabulary
    proto_html = client.get(f'/prototypes/{proto["slug"]}?lang=en').text
    assert f'href="/sessions/{sess["id"]}"' in proto_html


def test_prototype_session_timeline_shows_screenshots_when_files_exist(store, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = config.sessions_dir() / "psession_test"
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"\x89PNG fake")
    proj, proto, pid, sess = _proto_session(store)
    client = _client()
    html = client.get(f'/sessions/{sess["id"]}?lang=en').text
    # the harness convention <browser session_id>/step-<n>.png resolves without a stored path
    assert '<img class="sess-shot" src="/sessions-files/psession_test/step-0.png"' in html
    # … and the emitted src actually serves (the V4 regression pin: src present AND 200)
    assert client.get("/sessions-files/psession_test/step-0.png").status_code == 200
    # the shot opens the lightbox (no-JS fallback: the file itself)
    assert 'class="sl-shotlink" href="/sessions-files/psession_test/step-0.png" data-lightbox' in html
    assert "__slLightbox" in html
    # round-3 H6: the lightbox builds a visible close × and a step/action caption, fed by the
    # anchor's data-caption (Esc/click-out unchanged)
    assert "sl-lb-close" in html and "sl-lb-cap" in html
    assert 'data-caption="Step 0' in html
    assert 'data-close-label="Close image"' in html
    # step 1 has no file -> the recorded screen text
    assert "proto-screen-1" in html


def test_lightbox_stacking_contract(store, tmp_path, monkeypatch):
    """W8 regression pin (the owner's screenshot: the prototype iframe bled over the dialog).
    The lightbox must (a) open through showModal() — the top layer — with the [open]-attribute
    fallback otherwise, (b) live as a direct child of <body> (re-appended if a fragment swap
    detached it), (c) carry a fixed, z-indexed, CONTAINED panel style + a styled ::backdrop +
    a body scroll-lock, and (d) the prototype iframe stays clipped inside its card."""
    from sonaloop.web.pages.sessions import LIGHTBOX_JS
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    proj, proto, pid, sess = _proto_session(store)
    # The preview is honest: only a registered prototype with real backing files
    # renders an iframe.  Point this fixture at a minimal app so this stacking test
    # continues to exercise the embedded-document case rather than the unavailable
    # fallback.
    app_dir = tmp_path / "prototype-app"
    app_dir.mkdir()
    (app_dir / "index.html").write_text("<button>Continue</button>", encoding="utf-8")
    proto["path"] = str(app_dir)
    store.upsert_prototype(proto)
    html = _client().get(f'/prototypes/{proto["slug"]}?lang=en').text
    # (a) top-layer first, honest fallback second
    assert "dlg.showModal()" in LIGHTBOX_JS
    assert "dlg.setAttribute('open','')" in LIGHTBOX_JS
    # (b) the dialog is (re)attached directly under <body> before every open
    assert "dlg.parentNode!==document.body" in LIGHTBOX_JS
    assert "document.body.appendChild(dlg)" in LIGHTBOX_JS
    # (c) contained panel + backdrop + scroll lock + non-top-layer z guard, shipped in the page CSS
    for rule in (".sl-lightbox{position:fixed", "z-index:200",
                 ".sl-lightbox::backdrop{background:rgba(0,0,0,.74)}",
                 "body:has(.sl-lightbox[open]){overflow:hidden}"):
        assert rule in html, f"lightbox CSS lost its stacking contract: {rule}"
    # (d) the iframe card clips and isolates its embedded document
    assert "isolation:isolate" in html and "contain:paint" in html
    assert '<div class="protoframe" data-proto-frame=' in html
    assert '<iframe src=' in html and 'sandbox="allow-scripts"' in html
    assert 'sandbox="allow-scripts"' in html
    assert ' credentialless' in html
    # The prototype can take over the product viewport without opening a second browser tab.
    # The host keeps the close affordance and Esc handling outside the untrusted iframe.
    assert 'data-proto-expand=' in html and 'data-proto-close' in html
    assert 'allow="fullscreen" allowfullscreen' in html
    assert "body.classList.add('sl-proto-expanded')" in html
    assert "event.key === 'Escape'" in html
    for rule in (".protoframe.is-expanded{position:fixed;inset:0;z-index:240",
                 "body.sl-proto-expanded{overflow:hidden}"):
        assert rule in html, f"prototype maximize CSS lost its viewport contract: {rule}"


def test_missing_prototype_entry_never_renders_dead_preview(store):
    _proj, proto, _pid, _sess = _proto_session(store)
    html = _client().get(f'/prototypes/{proto["slug"]}?lang=en').text
    assert "The prototype files are unavailable." in html
    assert '<div class="protoframe" data-proto-frame=' not in html
    assert "Open in new tab" not in html


def test_hosted_prototype_provider_can_fail_closed_without_local_fallback(
        store, tmp_path, monkeypatch):
    from sonaloop.web import register_prototype_url_provider

    _proj, proto, _pid, _sess = _proto_session(store)
    app_dir = tmp_path / "hosted-only-prototype"
    app_dir.mkdir()
    (app_dir / "index.html").write_text("<p>hosted only</p>", encoding="utf-8")
    proto["path"] = str(app_dir)
    store.upsert_prototype(proto)
    register_prototype_url_provider(lambda _prototype, _path: "")
    try:
        html = _client().get(f'/prototypes/{proto["slug"]}?lang=en').text
        assert "The prototype files are unavailable." in html
        assert 'href="/proto-files/' not in html
        assert 'src="/proto-files/' not in html
        assert "<iframe" not in html
    finally:
        register_prototype_url_provider(None)


def test_prototype_session_timeline_shape_renders_steps_and_screenshots(store, tmp_path, monkeypatch):
    """§9 V4 ROOT CAUSE pin: half the showcase's prototype reactions authored their walk
    under reaction.timeline (free-form keys, no reaction.steps) — the replay rendered
    NOTHING while the retained step-<n>.png files served 200. The timeline shape now
    adapts onto the step renderer: per-step rows, narration, and the on-disk shots."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = config.sessions_dir() / "psession_test"
    d.mkdir(parents=True)
    (d / "step-1.png").write_bytes(b"\x89PNG fake")
    timeline = [
        {"step": "1", "action": "Wählt das Zeitfenster", "monolog": "mein echtes Fenster",
         "beobachtung": "Select stand auf 12:00"},
        {"step": "2", "action": "Liest das Protokoll", "monologue": "die Frist frisst das Fenster",
         "observed": "Rutsch-Protokoll zeigt +60 Min."},
    ]
    proj, proto, pid, sess = _proto_session(store, steps=[], timeline=timeline,
                                            observed_state_refs=["Select stand auf 12:00"])
    client = _client()
    html = client.get(f'/sessions/{sess["id"]}?lang=en').text
    # both authored steps render as replay rows, with their narration aliases resolved
    assert 'id="step-1"' in html and 'id="step-2"' in html
    assert "mein echtes Fenster" in html and "die Frist frisst das Fenster" in html
    # step 1 has a retained file: <img> WITH a src that serves 200
    src = "/sessions-files/psession_test/step-1.png"
    assert f'<img class="sess-shot" src="{src}"' in html
    assert client.get(src).status_code == 200
    # step 2 has no file: the observed screen text, never a src-less <img>
    assert "Rutsch-Protokoll zeigt +60 Min." in html


def test_step_shim_repairs_explicitly_empty_screenshot_key(store, tmp_path, monkeypatch):
    """A recorder that stored `screenshot: None` (key present, value empty) used to dodge
    the setdefault enrichment — the shot stayed invisible despite the file existing."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = config.sessions_dir() / "psession_test"
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"\x89PNG fake")
    reaction = _proto_reaction()
    reaction["steps"][0]["state"]["screenshot"] = None
    proj, proto, pid, sess = _proto_session(store, **reaction)
    html = _client().get(f'/sessions/{sess["id"]}?lang=en').text
    assert '<img class="sess-shot" src="/sessions-files/psession_test/step-0.png"' in html


def test_prototype_page_session_rows_carry_shot_strips(store, tmp_path, monkeypatch):
    """§9 V4: the prototype detail page shows each session row with a small first/last
    step-shot strip — BOTH session kinds (prototype reactions and usability walks)."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = config.sessions_dir() / "psession_test"
    d.mkdir(parents=True)
    (d / "step-0.png").write_bytes(b"\x89PNG fake")
    (d / "step-1.png").write_bytes(b"\x89PNG fake too")
    proj, proto, pid, sess = _proto_session(store)
    # a usability walk of the SAME prototype, with its own stored shot
    u_id = services.stable_id("usession", "protowalk")
    ud = config.sessions_dir() / u_id
    ud.mkdir(parents=True)
    (ud / "step-0.png").write_bytes(b"\x89PNG walk")
    shot = _step(0)
    shot["state"]["screenshot"] = "step-0.png"
    _record(store, key="protowalk", steps=[shot],
            subject={"kind": "prototype", "id": proto["id"], "label": "Journey prototype"})
    html = _client().get(f'/prototypes/{proto["slug"]}?lang=en').text
    # the reaction row's strip: first AND last resolvable shots from the browser-session dir
    strip = html.split('class="sl-shotstrip"')
    assert len(strip) >= 3                                   # one strip per session kind
    assert 'src="/sessions-files/psession_test/step-0.png"' in html
    assert 'src="/sessions-files/psession_test/step-1.png"' in html
    # the usability walk's strip resolves its own session dir
    assert f'src="/sessions-files/{u_id}/step-0.png"' in html
    # The dominant thumbnail has the SAME destination as its row: the session. It must not
    # strand the reader in a competing lightbox before they have entered the replay.
    assert f'class="sl-session-shotlink" href="/sessions/{sess["id"]}"' in html
    assert f'data-drawer="/sessions/{sess["id"]}"' in html
    assert 'class="sl-shotlink"' not in html and "__slLightbox=1" not in html


@pytest.mark.skipif(not browser.available(), reason="chromium not installed")
def test_session_entry_and_image_exit_are_usable_in_real_browser(store, tmp_path, monkeypatch):
    """The user journey, not just emitted markup: a shot on the prototype opens its session;
    the in-session zoom always has a visible viewport-contained exit; button, Esc and backdrop
    close only the image and leave the session usable. Validate desktop and narrow mobile."""
    from PIL import Image
    import uvicorn

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    d = config.sessions_dir() / "psession_test"
    d.mkdir(parents=True)
    Image.new("RGB", (600, 1200), "white").save(d / "step-0.png")
    focus_step = _step(0, focus={
        "x": 8, "y": 10, "width": 84, "height": 24, "label": "Hero",
    })
    _proj, proto, _pid, sess = _proto_session(store, steps=[focus_step])

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        web.create_app(), host="127.0.0.1", port=port, log_level="error",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started:
        assert time.time() < deadline, "app did not boot"
        time.sleep(0.05)

    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as playwright:
            chromium = playwright.chromium.launch()
            for width, height in ((1440, 900), (390, 844)):
                page = chromium.new_context(viewport={"width": width, "height": height}).new_page()
                page.goto(
                    f"http://127.0.0.1:{port}/prototypes/{proto['slug']}?lang=de",
                    wait_until="load",
                )

                # The screenshot thumbnail is an entry into the session, not a zoom trap.
                entry = page.locator(
                    f'.sl-session-shotlink[href="/sessions/{sess["id"]}"]'
                ).first
                assert entry.is_visible()
                assert entry.get_attribute("data-lightbox") is None
                entry.click()
                drawer = page.locator("#drawer.is-open")
                drawer.wait_for(state="visible")
                drawer.locator("#sec-replay").wait_for(state="visible")
                page.wait_for_timeout(300)  # let the shared 240 ms drawer transition settle
                panel_box = drawer.locator(".sl-drawer__panel").bounding_box()
                assert panel_box and panel_box["x"] >= 0
                assert panel_box["x"] + panel_box["width"] <= width + 1

                # Zoom is available only inside the session. Its close control stays entirely
                # inside the viewport at both widths and receives focus when opened.
                zoom = drawer.locator(".sl-session-lens .sl-shotlink").first
                zoom.click()
                dialog = page.locator("dialog.sl-lightbox[open]")
                dialog.wait_for(state="visible")
                close = dialog.locator(".sl-lb-close")
                assert close.is_visible() and close.get_attribute("aria-label") == "Bild schließen"
                box = close.bounding_box()
                assert box and box["x"] >= 0 and box["y"] >= 0
                assert box["x"] + box["width"] <= width
                assert box["y"] + box["height"] <= height
                assert close.evaluate("el => document.activeElement === el")

                close.click()
                assert dialog.count() == 0 or not dialog.is_visible()
                assert drawer.is_visible()

                # Esc closes the image, not the surrounding session drawer.
                zoom.click()
                dialog.wait_for(state="visible")
                page.keyboard.press("Escape")
                assert dialog.count() == 0 or not dialog.is_visible()
                assert drawer.is_visible()

                # A click on the actual backdrop is the third reliable exit.
                zoom.click()
                dialog.wait_for(state="visible")
                page.mouse.click(2, 2)
                assert dialog.count() == 0 or not dialog.is_visible()
                assert drawer.is_visible()

                # The drawer's existing expand action still reaches the canonical full view.
                drawer.locator("[data-drawer-expand]").click()
                page.wait_for_url(f"**/sessions/{sess['id']}")
                assert page.locator("#sec-replay").is_visible()
                page.context.close()
            chromium.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
