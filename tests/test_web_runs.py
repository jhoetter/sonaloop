"""/runs page + live topbar widget + extension seam (ticket agents-running-panel).

Fixtures mirror tests/test_autonomy.py: a planned project with no run is stalled,
a checkpointing run is active, a discharged freeform plan is finished."""
from __future__ import annotations

import base64

from starlette.testclient import TestClient

from sonaloop import services as S, web
from conftest import create_persona


def _client() -> TestClient:
    return TestClient(web.create_app())


def _planned(store, title: str) -> str:
    return S.start_project(title, "Wie können wir X erreichen?", methodology="double_diamond",
                           persona_ids=["p1"], store=store)["id"]


def test_runs_page_groups_active_stalled_finished(store):
    sid = _planned(store, "Stalled Proj")                      # open work, nobody driving
    aid = _planned(store, "Active Proj")
    S.start_run(aid, store=store)                              # an open, recently checkpointed run
    fid = S.start_project("Finished Proj", "frage?", store=store)["id"]
    S.record_frame(fid, "frame__root", ["q?"], memory_refs=["m"], store=store)
    html = _client().get("/runs?lang=en").text
    # all three projects show, each linking to its project page
    for pid, title in ((sid, "Stalled Proj"), (aid, "Active Proj"), (fid, "Finished Proj")):
        assert title in html and f'href="/jobs/{pid}"' in html
    # The primary row stays human-readable. Exact recovery instructions remain
    # available only behind an intentionally closed diagnostics disclosure.
    assert web.STRINGS["en"]["runs_stalled_h"] in html
    assert "start_run(" in html and f"data-copy=" in html and sid in html
    assert web.STRINGS["en"]["health_attention_not_started"] in html
    diag_tag = html[html.index("data-run-diagnostics") - 80:html.index("data-run-diagnostics") + 80]
    assert "<details" in diag_tag and " open" not in diag_tag
    assert html.index(web.STRINGS["en"]["health_attention_not_started"]) \
        < html.index("data-run-diagnostics") < html.index("start_run(")
    # Internal next-ready task keys remain support-visible, but only after the
    # intentionally closed diagnostics disclosure.
    assert html.index("data-run-diagnostics") < html.index("frame__discover")
    # finished plans collapse
    assert "<details" in html and web.STRINGS["en"]["runs_finished_h"] in html


def test_runs_page_stalled_detection_honors_quiet_open_run(store):
    """An open run gone quiet past the threshold is stalled — and the page's resume
    snippet names the run id (the project_run_state contract, honored end to end)."""
    pid = _planned(store, "Quiet Run Proj")
    run = S.start_run(pid, store=store)
    run["updated_at"] = "2020-01-01T00:00:00+00:00"            # age the checkpoint
    store.upsert_run(run)
    html = _client().get("/runs?lang=en").text
    assert web.STRINGS["en"]["runs_stalled_h"] in html
    assert run["run_id"] in html                                # resume call names the run
    assert web.STRINGS["en"]["health_attention_stalled"] in html
    assert web.STRINGS["en"]["health_attention_not_started"] not in html


def test_runs_page_empty_state(store):
    html = _client().get("/runs?lang=en").text
    assert web.STRINGS["en"]["no_runs"] in html
    # the page leads with the one-sentence definition of a run (§9 V8)
    assert web.STRINGS["en"]["runs_lead"] in html


def test_topbar_widget_present_on_every_page(store):
    aid = _planned(store, "Active Proj")
    S.start_run(aid, store=store)
    _planned(store, "Stalled Proj")
    html = _client().get("/personas?lang=en").text             # any page — the widget is chrome
    assert 'id="runsw"' in html and "has-active" in html and "has-stalled" in html
    # Attention remains loud even while another project is progressing.
    assert ">1 job needs attention</span>" in html.split('id="runsw-count"')[1][:80]
    assert "Active Proj" in html.split('id="runsw-fly"')[0] or "Active Proj" in html
    assert 'href="/runs"' in html                               # flyout links the full page
    assert "sl:live-event" in html                              # live update wiring (SSE re-dispatch)


def test_topbar_widget_hidden_at_zero_runs(store):
    """§9 V7: the zero state ("• 0") taught nothing — with no active or stalled run the
    chip is hidden entirely (the markup still ships so a live event can unhide it)."""
    def _runsw_tag(html: str) -> str:
        start = html.index('id="runsw"')
        return html[html.rindex("<div", 0, start):html.index(">", start)]

    assert " hidden" in _runsw_tag(_client().get("/personas?lang=en").text)
    # a stalled project alone keeps the loud lane loud — visible, amber, stalled read
    _planned(store, "Stalled Proj")
    html = _client().get("/personas?lang=en").text
    tag = _runsw_tag(html)
    assert " hidden" not in tag and "has-stalled" in tag
    assert ">1 job needs attention</span>" in html.split('id="runsw-count"')[1][:80]


def test_project_head_run_chip_with_progressive_diagnostics(store):
    """Runs left the nav. The global runs widget owns the topbar; a project with a
    plan carries its run-state chip in the project head, with state, last activity,
    a human-readable hint and the /runs journal link. Raw invariants, recovery
    calls and trace ids are available only inside the closed diagnostics detail."""
    sid = _planned(store, "Stalled Proj")                      # open work, nobody driving
    html = _client().get(f"/jobs/{sid}?lang=en").text
    assert 'class="sl-toolbtn runchip runchip--stalled"' in html          # the rendered chip, not the chrome CSS/JS
    assert f'{web.STRINGS["en"]["run_chip"]} · {web.STRINGS["en"]["runs_stalled_h"]}' in html
    toggle_at = html.index("data-runchip-toggle")
    toggle_tag = html[html.rindex("<button", 0, toggle_at):html.index(">", toggle_at) + 1]
    assert 'aria-haspopup="dialog"' in toggle_tag
    assert 'aria-controls="runchip-fly"' in toggle_tag
    assert 'aria-expanded="false"' in toggle_tag
    topbar_actions = html.split('<span class="sl-tb-actions">', 1)[1].split('</span></header>', 1)[0]
    assert 'id="runchip"' not in topbar_actions
    assert 'class="sl-toolbtn sl-tour-plan-chip"' in topbar_actions
    project_head = html.split('class="proj-head"', 1)[1].split('class="outlinecard', 1)[0]
    assert 'id="runchip"' in project_head
    pop = html.split('id="runchip-fly"')[1][:6000]
    fly_tag = html[html.rindex("<div", 0, html.index('id="runchip-fly"')):
                   html.index(">", html.index('id="runchip-fly"')) + 1]
    assert 'role="dialog"' in fly_tag
    assert 'aria-labelledby="runchip-fly-title"' in fly_tag
    # the popover LEADS with the concept (§9 V8): what a run is, before this run's state
    assert web.STRINGS["en"]["runs_lead"] in pop
    assert pop.index(web.STRINGS["en"]["runs_lead"]) < pop.index(web.STRINGS["en"]["run_last_activity"])
    assert web.STRINGS["en"]["run_last_activity"] in pop
    assert web.STRINGS["en"]["health_attention_not_started"] in pop
    assert "data-run-diagnostics" in pop
    details_tag = pop[pop.index("<details"):pop.index(">", pop.index("<details")) + 1]
    assert " open" not in details_tag
    invariant = S.project_health(sid, store=store)["unmet_invariant"]["message"]
    assert pop.index(web.STRINGS["en"]["health_attention_not_started"]) \
        < pop.index("data-run-diagnostics") < pop.index(invariant) < pop.index("start_run(")
    assert pop.index("data-run-diagnostics") < pop.index("frame__discover")
    assert 'data-copy=' in html and 'href="/runs"' in html            # journal link
    # The old full-width engineering card no longer interrupts the project canvas.
    assert 'class="sl-job-health' not in html and 'id="job-health"' not in html
    # an active run flips the chip state
    aid = _planned(store, "Active Proj")
    S.start_run(aid, store=store)
    active_html = _client().get(f"/jobs/{aid}?lang=en").text
    assert 'class="sl-toolbtn runchip runchip--active"' in active_html
    assert f'{web.STRINGS["en"]["run_chip"]} · {web.STRINGS["en"]["runs_active_h"]}' in active_html
    # New projects now get a minimal frame plan immediately, so there is always
    # a driver to resume from the project header.
    bare = S.create_research_project("No plan", goal="g", store=store)
    bare_html = _client().get(f'/jobs/{bare["id"]}?lang=en').text
    assert 'class="sl-toolbtn runchip runchip--stalled"' in bare_html


def test_reaction_preflights_project_one_truthful_waiting_state_in_de_and_en(store):
    """An active journal waiting at a mandatory gate is amber, not a green
    background worker. Setup guidance belongs to the run-chip popover; the job
    canvas never grows a second, full-width missing-state card.
    """
    project = S.start_project(
        "Reaction waiting", "Do people understand the captured screen?",
        methodology="Reaction Test", operation_id="reaction-waiting:create", store=store,
    )
    run = S.start_run(
        project["id"], operation_id="reaction-waiting:run", store=store,
    )

    health = S.project_health(project["id"], store=store)
    assert health["state"] == "waiting"
    assert health["driver_state"] == "waiting_on_preflight"
    assert health["preflight"]["state"] == "waiting"
    assert health["preflight"]["gate"] == "product_understanding"
    assert health["preflight"]["kind"] == "stimulus_required"
    assert health["preflight"]["code"] == "REACTION_STIMULUS_REQUIRED"
    assert health["preflight"]["action"]["next_call"] == health["preflight"]["next_call"]
    grouped = _client().get("/api/runs").json()
    assert grouped["active"] == []
    assert grouped["waiting"][0]["state"] == "waiting"
    assert grouped["stalled"] == []

    for language, waiting, recovery, global_label in (
        ("de", "Run · Wartet auf Eingabe",
         "Echte Screens oder Assets erfassen und dann denselben Run fortsetzen.",
         "1 Job wartet auf Eingabe"),
        ("en", "Run · Waiting for input",
         "Capture real screens or assets, then continue the same run.",
         "1 job awaits input"),
    ):
        list_html = _client().get(f"/jobs?lang={language}").text
        detail_html = _client().get(f"/jobs/{project['id']}?lang={language}").text
        assert waiting in list_html and waiting in detail_html
        assert global_label in detail_html
        assert 'runchip runchip--waiting' in detail_html
        assert recovery in detail_html
        assert 'id="product-understanding"' not in detail_html
        assert 'id="cohort-selection"' not in detail_html
        assert 'id="cohort-integrity"' not in detail_html
        assert 'id="research-setup-details"' not in detail_html
        assert "Cohort Integrity" not in detail_html
        assert 'runchip runchip--active' not in detail_html

    # Complete Product Understanding through the governed dispatch. While the
    # frame is being authored, Cohort Integrity is still a future task and must
    # not render as a simultaneous missing error.
    dispatch = S.run_step(run["run_id"], store=store)
    asset = S.attach_asset(
        project["id"], content_base64=base64.b64encode(b"screen-state").decode(),
        filename="screen.png", kind="screenshot", title="Captured screen",
        dispatch_token=dispatch["dispatch_token"], store=store,
    )
    ref = {"kind": "asset", "id": asset["id"]}
    inventory_health = S.project_health(project["id"], store=store)
    assert inventory_health["preflight"]["kind"] == "product_understanding_required"
    inventory_html = _client().get(f"/jobs/{project['id']}?lang=en").text
    assert 'runchip runchip--waiting' in inventory_html
    assert 'id="product-understanding"' not in inventory_html
    assert 'id="research-setup-details"' not in inventory_html
    S.record_product_understanding(
        project["id"], target={"name": "Captured product"}, revision="screen:1",
        routes=[{"path": "/", "evidence_refs": [ref]}],
        flows=[{"name": "Landing", "evidence_refs": [ref]}],
        states=[{"state": "landing", "evidence_refs": [ref]}],
        capabilities=[{
            "key": "headline", "claim": "The headline is visible",
            "status": "observed_present", "evidence_refs": [ref],
        }],
        evidence_refs=[ref], observed_at="2026-08-09T18:00:00Z",
        dispatch_token=dispatch["dispatch_token"], store=store,
    )
    personas = [create_persona(store, "Independent A"), create_persona(store, "Independent B")]
    frame_dispatch = S.run_step(run["run_id"], store=store)
    assert frame_dispatch["step_id"] == "frame__react"
    assert frame_dispatch["blocking_action"]["kind"] == "cohort_selection_required"
    selection_health = S.project_health(project["id"], store=store)
    assert selection_health["state"] == "waiting"
    assert selection_health["preflight"]["gate"] == "cohort_selection"
    selection_html = _client().get(f"/jobs/{project['id']}?lang=en").text
    assert 'id="cohort-selection"' not in selection_html
    assert "Cohort Integrity" not in selection_html
    assert 'runchip runchip--waiting' in selection_html
    assert 'runchip runchip--active' not in selection_html

    S.select_reaction_test_cohort(
        project["id"], personas,
        "Independent roles provide a useful contrast",
        operation_id="reaction-waiting:cohort-selection",
        dispatch_token=frame_dispatch["dispatch_token"], store=store,
    )
    frame_html = _client().get(f"/jobs/{project['id']}?lang=en").text
    assert 'id="cohort-selection"' not in frame_html
    assert "Cohort Integrity" not in frame_html
    assert 'id="research-setup-details"' in frame_html
    assert 'runchip runchip--active' in frame_html

    S.record_frame(
        project["id"], frame_dispatch["step_id"],
        ["What would make the captured headline unclear?"],
        hypotheses=["Some readers may miss the intended next action."],
        memory_refs=["memory:independent-context"],
        dispatch_token=frame_dispatch["dispatch_token"], store=store,
    )
    cohort_health = S.project_health(project["id"], store=store)
    assert cohort_health["state"] == "waiting"
    assert cohort_health["preflight"]["gate"] == "cohort_integrity"
    cohort_html = _client().get(f"/jobs/{project['id']}?lang=en").text
    assert 'id="cohort-integrity"' not in cohort_html
    assert 'id="research-setup-details"' in cohort_html
    assert web.STRINGS["en"]["health_attention_preflight_cohort"] in cohort_html


def test_flow_manifest_setup_stays_in_run_chip_without_a_canvas_card(store):
    project = S.start_project(
        "Flow setup", "React to https://example.test",
        methodology="Reaction Test", operation_id="flow-setup:create", store=store,
    )
    run = S.start_run(project["id"], operation_id="flow-setup:run", store=store)
    dispatch = S.run_step(run["run_id"], store=store)
    asset = S.attach_asset(
        project["id"], content_base64=base64.b64encode(b"remote-screen").decode(),
        filename="remote.png", kind="screenshot", title="Remote screen",
        dispatch_token=dispatch["dispatch_token"], store=store,
    )
    # This is a presentation fixture: mark the already persisted asset as an
    # admitted remote version so the canonical projector selects its manifest
    # action. Admission validation itself is covered by test_remote_stimulus_admission.
    row = store.get_research_project(project["id"])
    persisted_asset = next(item for item in row["assets"] if item["id"] == asset["id"])
    persisted_asset["admission"] = {
        "schema": "sonaloop.remote_screenshot_admission.v1",
        "target_revision": "deploy:1",
    }
    store.upsert_research_project(row)
    S.record_reaction_test_capture_review(
        project["id"], True,
        [{"asset_version_id": asset["id"], "role": "The deliberately bounded target screen"}],
        [], "This presentation fixture intentionally covers one bounded target screen only.",
        "flow-setup:capture-review", dispatch["dispatch_token"], store=store,
    )

    health = S.project_health(project["id"], store=store)
    assert health["preflight"]["kind"] == "flow_manifest_required"
    for language in ("de", "en"):
        html = _client().get(f"/jobs/{project['id']}?lang={language}").text
        assert 'runchip runchip--waiting' in html
        assert 'data-setup-kind="flow_manifest_required"' not in html
        assert 'id="product-understanding"' not in html
        assert 'id="research-setup-details"' not in html
        assert "Cohort Integrity" not in html


def test_setup_and_stalled_runs_keep_separate_lanes_and_neutral_mixed_count(store):
    setup = S.start_project(
        "Needs setup", "React to https://example.test",
        methodology="Reaction Test", operation_id="lanes:setup", store=store,
    )
    S.start_run(setup["id"], operation_id="lanes:setup-run", store=store)
    stalled = _planned(store, "Actually stalled")

    grouped = _client().get("/api/runs").json()
    assert [row["project_id"] for row in grouped["waiting"]] == [setup["id"]]
    assert [row["project_id"] for row in grouped["stalled"]] == [stalled]

    chrome = _client().get("/personas?lang=en").text
    assert ">2 jobs need attention</span>" in chrome.split('id="runsw-count"')[1][:100]
    assert 'data-run-lane="waiting"' in chrome
    assert 'data-run-lane="stalled"' in chrome
    assert "1 job awaits input" not in chrome.split('id="runsw-count"')[1][:100]

    runs = _client().get("/runs?lang=en").text
    main = runs.split("<section>", 1)[1]
    setup_at = main.index(web.STRINGS["en"]["runs_setup_h"])
    stalled_at = main.index(web.STRINGS["en"]["runs_stalled_h"], setup_at + 1)
    assert setup_at < main.index(f'href="/jobs/{setup["id"]}"', setup_at) < stalled_at
    assert stalled_at < main.index(f'href="/jobs/{stalled}"', stalled_at)


def test_runs_page_support_trace_is_only_inside_closed_diagnostics(store):
    pid = _planned(store, "Support trace disclosure")
    run = S.start_run(pid, store=store)
    run["updated_at"] = "2020-01-01T00:00:00+00:00"
    store.upsert_run(run)
    health = S.project_health(pid, store=store)
    support_ref = health["trace"]["support_ref"]
    invariant = health["unmet_invariant"]["message"]

    html = _client().get("/runs?lang=en").text
    details_at = html.index("data-run-diagnostics")
    details_tag = html[html.rindex("<details", 0, details_at):html.index(">", details_at) + 1]
    assert " open" not in details_tag
    summary_at = html.index("<summary", details_at)
    summary_tag = html[summary_at:html.index(">", summary_at) + 1]
    assert f'aria-label="Technical diagnostics for Support trace disclosure"' in summary_tag
    assert html.index(web.STRINGS["en"]["health_attention_stalled"]) < details_at
    assert details_at < html.index(invariant) < html.index(support_ref)


def test_run_popovers_keep_aria_state_and_focus_in_sync():
    from sonaloop.web._runs_widget import RUNS_WIDGET_JS

    assert "function closePopover(btn,fly,restore)" in RUNS_WIDGET_JS
    assert "btn.setAttribute('aria-expanded','false')" in RUNS_WIDGET_JS
    assert "var ownedFocus=fly.contains(document.activeElement)" in RUNS_WIDGET_JS
    assert "if((restore||ownedFocus)&&btn) btn.focus()" in RUNS_WIDGET_JS
    assert "closePopover(document.querySelector('[data-runchip-toggle]'),cfly,false)" in RUNS_WIDGET_JS
    assert "closePopover(document.querySelector('[data-runchip-toggle]'),cfly,true)" in RUNS_WIDGET_JS


def test_api_runs_returns_grouped_states(store):
    aid = _planned(store, "Active Proj")
    S.start_run(aid, store=store)
    data = _client().get("/api/runs").json()
    assert [r["project_id"] for r in data["active"]] == [aid]
    assert data["active"][0]["url"] == f"/jobs/{aid}"
    assert data["stalled"] == [] and data["finished"] == []


def test_archived_projects_are_absent_from_all_run_surfaces(store):
    """Archiving removes a job from ordinary discovery everywhere, including
    the run journal and its global status projection.  A current run remains
    visible, so an accidentally empty projector cannot satisfy this contract.
    """
    visible = _planned(store, "VISIBLE ACTIVE RUN")
    S.start_run(visible, operation_id="runs:visible-active", store=store)
    archived = _planned(store, "HIDDEN ARCHIVED RUN")
    S.archive_project(
        archived, "runs:archive-hidden", "Preserve historical evidence", store=store,
    )

    runs_html = _client().get("/runs?lang=en").text
    assert f'href="/jobs/{visible}"' in runs_html
    assert "VISIBLE ACTIVE RUN" in runs_html
    assert f'href="/jobs/{archived}"' not in runs_html
    assert "HIDDEN ARCHIVED RUN" not in runs_html

    grouped = _client().get("/api/runs").json()
    projected = [row for rows in grouped.values() for row in rows]
    assert any(row["project_id"] == visible for row in projected)
    assert all(row["project_id"] != archived for row in projected)

    chrome = _client().get("/personas?lang=en").text
    assert 'id="runsw"' in chrome
    assert f'href="/jobs/{visible}"' in chrome
    assert "VISIBLE ACTIVE RUN" in chrome
    assert f'href="/jobs/{archived}"' not in chrome
    assert "HIDDEN ARCHIVED RUN" not in chrome


def test_runs_section_extension_seam(store):
    """register_runs_section: a downstream package (sonaloop-cloud) contributes an
    extra section to /runs without the core importing it. Idempotent by id."""
    from sonaloop.web.pages import runs as runs_mod

    web.register_runs_section("assignments", lambda store: '<div id="cloud-assignments">EXT</div>')
    web.register_runs_section("assignments", lambda store: '<div id="cloud-assignments">EXT2</div>')
    try:
        assert sum(1 for s in runs_mod._RUNS_SECTIONS if s["id"] == "assignments") == 1
        html = _client().get("/runs").text
        assert 'id="cloud-assignments"' in html and "EXT2" in html
    finally:
        runs_mod._RUNS_SECTIONS[:] = [s for s in runs_mod._RUNS_SECTIONS
                                      if s["id"] != "assignments"]
