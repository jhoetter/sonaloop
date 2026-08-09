"""Regression coverage for retry/model failures observed on the remote production MCP path."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from pathlib import Path
from threading import Barrier

import pytest

from sonaloop import methodology as M
from sonaloop import plan as P
from sonaloop import services
from sonaloop.mcp_server import build_server


def _hold_project_lifecycle_lock(
    database_path: str, project_id: str,
    attempting: multiprocessing.synchronize.Event,
    entered: multiprocessing.synchronize.Event,
    release: multiprocessing.synchronize.Event,
) -> None:
    """Spawn-safe helper proving that the SQLite guard crosses process boundaries."""
    from sonaloop._project_locks import project_lifecycle_locks
    from sonaloop.storage import Store

    with Store(Path(database_path)) as scoped:
        attempting.set()
        with project_lifecycle_locks(scoped, [project_id]):
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test lifecycle lock was not released")


def test_methodology_display_names_and_spelling_variants_resolve_to_stable_key(store):
    assert M.resolve_methodology_key("Reaction Test", store=store) == "reaction_test"
    assert M.resolve_methodology_key("reaction-test", store=store) == "reaction_test"
    assert M.resolve_methodology_key("  REACTION_test  ", store=store) == "reaction_test"

    project = services.start_project(
        "Website reaction", "Does the stimulus land?", methodology="Reaction Test", store=store)
    assert project["methodology"] == "reaction_test"
    assert services.get_plan(project["id"], store=store)["methodology"] == "reaction_test"


def test_start_project_mcp_schema_exposes_retry_key_and_contract():
    tool = next(t for t in asyncio.run(build_server().list_tools()) if t.name == "start_project")
    assert "operation_id" in tool.inputSchema["properties"]
    assert "Reaction Test" in tool.description and "transport retries" in tool.description
    run_tool = next(t for t in asyncio.run(build_server().list_tools()) if t.name == "start_run")
    assert "operation_id" in run_tool.inputSchema["properties"]
    assert "stable operation_id" in run_tool.description and "transport retries" in run_tool.description


def test_unknown_methodology_is_rejected_before_project_or_plan_write(store):
    assert store.list_research_projects() == []
    with pytest.raises(M.MethodologyError) as exc:
        services.start_project("No orphan", "g", methodology="Definitely Not A Method", store=store)
    assert exc.value.code == "UNKNOWN_METHODOLOGY"
    assert store.list_research_projects() == []
    assert store.conn.execute("SELECT COUNT(*) AS n FROM research_plans").fetchone()["n"] == 0


def test_start_project_operation_id_is_idempotent_and_conflicts_fail_closed(store):
    operation_id = "client-chat-17:create-study-1"
    first = services.start_project(
        "Retry-safe", "g", methodology="Reaction Test", operation_id=operation_id, store=store)
    replay = services.start_project(
        "Retry-safe", "g", methodology="reaction_test", operation_id=operation_id, store=store)

    assert replay["id"] == first["id"]
    assert replay["idempotent_replay"] is True
    assert len(store.list_research_projects()) == 1
    assert store.get_research_project(first["id"])["operation_id"] == operation_id

    with pytest.raises(P.PlanError) as exc:
        services.start_project(
            "Changed request", "different", methodology="reaction_test",
            operation_id=operation_id, store=store)
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"
    assert len(store.list_research_projects()) == 1

    with pytest.raises(ValueError, match="operation_id"):
        services.start_project("Blank key", "g", operation_id="   ", store=store)


def test_start_project_retry_repairs_a_partially_initialized_operation(store):
    operation_id = "client-chat-18:create-study-1"
    first = services.start_project(
        "Repair create", "g", methodology="Reaction Test", operation_id=operation_id, store=store)
    partial = store.get_research_project(first["id"])
    partial["operation_state"] = "creating"
    partial["methodology"] = ""
    store.upsert_research_project(partial)
    store.conn.execute("DELETE FROM research_plans WHERE project_id=?", (first["id"],))
    store.conn.commit()

    repaired = services.start_project(
        "Repair create", "g", methodology="reaction_test", operation_id=operation_id, store=store)
    assert repaired["id"] == first["id"] and repaired["idempotent_replay"] is True
    assert repaired["operation_state"] == "initialized"
    assert repaired["methodology"] == "reaction_test"
    assert services.get_plan(first["id"], store=store)["methodology"] == "reaction_test"
    assert len(store.list_research_projects()) == 1


def test_late_start_project_retry_never_rolls_back_a_later_methodology_change(store):
    operation_id = "client-chat-19:create-study-1"
    first = services.start_project(
        "Mutable after create", "g", methodology="Reaction Test",
        operation_id=operation_id, store=store)
    changed = services.set_project_methodology(first["id"], "Double Diamond", store=store)
    assert changed["methodology"] == "double_diamond"
    assert services.get_plan(first["id"], store=store)["methodology"] == "double_diamond"

    replay = services.start_project(
        "Mutable after create", "g", methodology="reaction_test",
        operation_id=operation_id, store=store)

    assert replay["idempotent_replay"] is True
    assert replay["methodology"] == "double_diamond"
    assert services.get_plan(first["id"], store=store)["methodology"] == "double_diamond"


def test_concurrent_start_project_replay_claims_one_project():
    from sonaloop.storage import Store
    with Store():
        pass  # initialize the shared SQLite schema before the racing connections open
    barrier = Barrier(2)

    def create():
        with Store() as thread_store:
            barrier.wait(timeout=10)
            return services.start_project(
                "Concurrent create", "g", methodology="Reaction Test",
                operation_id="concurrent:create:1", store=thread_store)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [pool.submit(create), pool.submit(create)]]

    assert results[0]["id"] == results[1]["id"]
    assert sum(bool(row.get("idempotent_replay")) for row in results) == 1
    with Store() as check:
        assert len(check.list_research_projects()) == 1
        assert check.get_research_plan(results[0]["id"])["methodology"] == "reaction_test"


def test_concurrent_operation_id_collision_rejects_different_payload():
    from sonaloop.storage import Store
    with Store():
        pass  # initialize the shared SQLite schema before the racing connections open
    barrier = Barrier(2)

    def create(title: str):
        with Store() as thread_store:
            barrier.wait(timeout=10)
            try:
                return services.start_project(
                    title, "g", operation_id="concurrent:collision:1", store=thread_store)
            except P.PlanError as exc:
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [
            pool.submit(create, "Payload A"), pool.submit(create, "Payload B")]]

    projects = [row for row in results if isinstance(row, dict)]
    errors = [row for row in results if isinstance(row, P.PlanError)]
    assert len(projects) == 1 and len(errors) == 1
    assert errors[0].code == "IDEMPOTENCY_CONFLICT"
    with Store() as check:
        assert len(check.list_research_projects()) == 1


def test_start_run_operation_id_is_retry_safe_and_conflict_checked(store):
    first_project = services.start_project("Run identity A", "g", store=store)
    second_project = services.start_project("Run identity B", "g", store=store)
    first = services.start_run(
        first_project["id"], budget=12, operation_id="connector:run-create:1", store=store)
    replay = services.start_run(
        first_project["id"], budget=12, operation_id="connector:run-create:1", store=store)
    assert replay["run_id"] == first["run_id"]
    assert replay["idempotent_replay"] is True
    assert len(store.list_runs(first_project["id"])) == 1

    with pytest.raises(P.PlanError) as conflict:
        services.start_run(
            second_project["id"], budget=12,
            operation_id="connector:run-create:1", store=store)
    assert conflict.value.code == "RUN_IDEMPOTENCY_CONFLICT"
    with pytest.raises(ValueError, match="either run_id"):
        services.start_run(
            first_project["id"], run_id=first["run_id"],
            operation_id="another-operation", store=store)


def test_concurrent_start_run_operation_claims_one_run():
    from sonaloop.storage import Store

    with Store() as setup:
        project = services.start_project("Concurrent run", "g", store=setup)
    barrier = Barrier(2)

    def create_run():
        with Store() as thread_store:
            barrier.wait(timeout=10)
            return services.start_run(
                project["id"], budget=20, operation_id="concurrent:run:1", store=thread_store)

    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = [future.result() for future in [pool.submit(create_run), pool.submit(create_run)]]

    assert runs[0]["run_id"] == runs[1]["run_id"]
    assert sum(bool(row.get("idempotent_replay")) for row in runs) == 1
    with Store() as check:
        assert len(check.list_runs(project["id"])) == 1


@pytest.mark.parametrize("operation_ids", [
    ("concurrent:run:left", "concurrent:run:right"),
    (None, None),
])
def test_concurrent_distinct_run_starts_fail_closed_on_one_active_owner(operation_ids):
    """Different intents (including legacy unkeyed calls) cannot race two active rows in."""
    from sonaloop.storage import Store

    with Store() as setup:
        project = services.start_project("One active owner", "g", store=setup)
    barrier = Barrier(2)

    def create_run(operation_id):
        with Store() as thread_store:
            barrier.wait(timeout=10)
            try:
                return services.start_run(
                    project["id"], operation_id=operation_id, store=thread_store)
            except P.PlanError as exc:
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [
            pool.submit(create_run, operation_ids[0]),
            pool.submit(create_run, operation_ids[1]),
        ]]

    runs = [row for row in results if isinstance(row, dict)]
    errors = [row for row in results if isinstance(row, P.PlanError)]
    assert len(runs) == 1 and len(errors) == 1
    assert errors[0].code == "ACTIVE_RUN_EXISTS"
    assert runs[0]["run_id"] in errors[0].message
    assert f"start_run(project_id={project['id']!r}, run_id={runs[0]['run_id']!r})" \
        in errors[0].message
    with Store() as check:
        persisted = check.list_runs(project["id"])
        assert len(persisted) == 1 and persisted[0]["status"] == "active"


def test_second_run_names_safe_resume_and_terminal_run_releases_owner(store):
    project = services.start_project("Resume the owner", "g", store=store)
    first = services.start_run(
        project["id"], budget=9, operation_id="one-active:first", store=store)

    with pytest.raises(P.PlanError) as blocked:
        services.start_run(
            project["id"], budget=9, operation_id="one-active:second", store=store)
    assert blocked.value.code == "ACTIVE_RUN_EXISTS"
    assert first["run_id"] in blocked.value.message
    assert "then continue with run_step" in blocked.value.message

    # Existing identity replay and explicit run-id resume remain valid through the guard.
    assert services.start_run(
        project["id"], budget=9, operation_id="one-active:first", store=store
    )["idempotent_replay"] is True
    assert services.start_run(
        project["id"], run_id=first["run_id"], store=store
    )["idempotent_replay"] is True

    services.finish_run(first["run_id"], "stopped", store=store)
    second = services.start_run(
        project["id"], operation_id="one-active:second", store=store)
    assert second["run_id"] != first["run_id"]
    assert [row["status"] for row in store.list_runs(project["id"])] == ["active", "stopped"]


def test_legacy_active_run_is_adopted_without_rewriting_history(store):
    project = services.start_project("Adopt legacy run", "g", store=store)
    legacy = {
        "run_id": "run_legacy_owner", "project_id": project["id"], "status": "active",
        "cursor": 0, "steps": [], "dispatches": [], "critic_rounds": [],
        "created_at": "2026-08-07T12:00:00+00:00",
        "updated_at": "2026-08-07T12:01:00+00:00",
    }
    store.upsert_run(legacy)  # pre-invariant storage shape: no active_run_claims row

    with pytest.raises(P.PlanError) as blocked:
        services.start_run(project["id"], operation_id="post-upgrade:new", store=store)
    assert blocked.value.code == "ACTIVE_RUN_EXISTS"
    assert legacy["run_id"] in blocked.value.message
    assert store.list_runs(project["id"]) == [legacy]


@pytest.mark.parametrize("close_kind", ["archive", "supersede"])
def test_closed_project_cannot_acquire_a_new_run(store, close_kind):
    project = services.start_project("Closed predecessor", "g", store=store)
    if close_kind == "archive":
        services.archive_project(
            project["id"], "close:archive", "Preserve it", store=store,
        )
    else:
        successor = services.start_project("Successor", "g", store=store)
        services.supersede_project(
            successor["id"], project["id"], "close:supersede", "Explicit lineage",
            store=store,
        )

    with pytest.raises(P.PlanError) as blocked:
        services.start_run(project["id"], operation_id="closed:new-run", store=store)

    assert blocked.value.code == "PROJECT_CLOSED"
    assert store.list_runs(project["id"]) == []


def test_archive_and_run_start_serialize_without_closed_active_state():
    from sonaloop.storage import Store

    with Store() as setup:
        project = services.start_project("Lifecycle race", "g", store=setup)
    barrier = Barrier(2)

    def start():
        with Store() as scoped:
            barrier.wait(timeout=10)
            try:
                return services.start_run(
                    project["id"], operation_id="lifecycle:race:run", store=scoped,
                )
            except Exception as exc:  # the archive-won outcome is expected
                return exc

    def archive():
        with Store() as scoped:
            barrier.wait(timeout=10)
            try:
                return services.archive_project(
                    project["id"], "lifecycle:race:archive", "Explicit race test",
                    store=scoped,
                )
            except Exception as exc:  # the run-won outcome is expected
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        start_result, archive_result = [future.result() for future in (
            pool.submit(start), pool.submit(archive),
        )]

    with Store() as check:
        persisted = check.get_research_project(project["id"])
        active = [row for row in check.list_runs(project["id"]) if row["status"] == "active"]
    lifecycle = str(persisted.get("status") or "active")
    assert not (lifecycle == "archived" and active)
    if lifecycle == "archived":
        assert isinstance(start_result, P.PlanError)
        assert start_result.code == "PROJECT_CLOSED"
        assert not active
    else:
        assert len(active) == 1
        assert isinstance(archive_result, ValueError)
        assert "ACTIVE_RUN_ARCHIVE_BLOCKED" in str(archive_result)


def test_sqlite_project_lifecycle_lock_serializes_separate_processes(store):
    project = services.start_project("Process lifecycle lock", "g", store=store)
    context = multiprocessing.get_context("spawn")
    attempting_one, attempting_two = context.Event(), context.Event()
    entered_one, release_one = context.Event(), context.Event()
    entered_two, release_two = context.Event(), context.Event()
    first = context.Process(
        target=_hold_project_lifecycle_lock,
        args=(str(store.path), project["id"], attempting_one, entered_one, release_one),
    )
    second = context.Process(
        target=_hold_project_lifecycle_lock,
        args=(str(store.path), project["id"], attempting_two, entered_two, release_two),
    )
    try:
        first.start()
        assert attempting_one.wait(timeout=5)
        assert entered_one.wait(timeout=5)
        second.start()
        assert attempting_two.wait(timeout=5)
        assert not entered_two.wait(timeout=0.3)
        release_one.set()
        assert entered_two.wait(timeout=5)
        release_two.set()
        first.join(timeout=5)
        second.join(timeout=5)
        assert first.exitcode == second.exitcode == 0
    finally:
        release_one.set()
        release_two.set()
        for process in (first, second):
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)


def test_delete_and_run_start_serialize_without_orphaned_run():
    from sonaloop.storage import Store

    with Store() as setup:
        project = services.start_project("Delete lifecycle race", "g", store=setup)
    barrier = Barrier(2)

    def start():
        with Store() as scoped:
            barrier.wait(timeout=10)
            try:
                return services.start_run(
                    project["id"], operation_id="lifecycle:delete-race:run", store=scoped,
                )
            except Exception as exc:
                return exc

    def delete():
        with Store() as scoped:
            barrier.wait(timeout=10)
            try:
                # The destructive API accepts legacy slugs, but must canonicalize the lock
                # to the same id used by start_run.
                return services.delete_research_project(project["slug"], store=scoped)
            except Exception as exc:
                return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        start_result, delete_result = [future.result() for future in (
            pool.submit(start), pool.submit(delete),
        )]

    with Store() as check:
        persisted = check.get_research_project(project["id"])
        runs = check.list_runs(project["id"])
        claims = check.conn.execute(
            "SELECT COUNT(*) AS n FROM active_run_claims WHERE project_id=?", (project["id"],),
        ).fetchone()["n"]
    if persisted is None:
        assert isinstance(delete_result, dict)
        assert delete_result["project_id"] == project["id"]
        assert isinstance(start_result, P.PlanError)
        assert start_result.code == "UNKNOWN_PROJECT"
        assert runs == [] and claims == 0
    else:
        assert isinstance(start_result, dict)
        assert len(runs) == 1 and runs[0]["status"] == "active" and claims == 1
        assert isinstance(delete_result, ValueError)
        assert "PROJECT_DELETE_RUN_HISTORY_BLOCKED" in str(delete_result)


def test_project_with_terminal_run_history_must_be_archived_not_deleted(store):
    project = services.start_project("Durable run history", "g", store=store)
    run = services.start_run(project["id"], operation_id="history:durable", store=store)
    services.finish_run(run["run_id"], "stopped", store=store)

    with pytest.raises(ValueError, match="PROJECT_DELETE_RUN_HISTORY_BLOCKED"):
        services.delete_research_project(project["id"], store=store)

    archived = services.archive_project(
        project["id"], "history:archive", "Preserve governed run history", store=store,
    )
    assert archived["status"] == "archived"
    assert store.get_research_project(project["id"])["status"] == "archived"
    assert store.list_runs(project["id"])[0]["run_id"] == run["run_id"]


def test_checkpoint_step_deduplicates_retried_deterministic_key(store):
    project = services.start_project("Journal", "g", store=store)
    run = services.start_run(project["id"], store=store)
    step = {"task_id": "frame__root", "bucket": "analyze",
            "key": services.run_key(run["run_id"], "frame__root"),
            "evidence": [{"kind": "frame", "id": "frame__root"}], "summary": "framed"}

    first = services.checkpoint_step(run["run_id"], step, store=store)
    services.checkpoint_step(run["run_id"], {
        "task_id": "followup", "bucket": "act", "key": services.run_key(run["run_id"], "followup"),
        "evidence": [], "summary": "later checkpoint"}, store=store)
    replay = services.checkpoint_step(run["run_id"], step, store=store)

    assert first == {"cursor": 1, "run_id": run["run_id"], "step_idx": 0,
                     "key": step["key"], "deduplicated": False}
    assert replay["cursor"] == 1 and replay["deduplicated"] is True
    assert replay["step_idx"] == first["step_idx"] and replay["key"] == first["key"]
    with pytest.raises(P.PlanError) as conflict:
        services.checkpoint_step(
            run["run_id"], {**step, "summary": "different payload"}, store=store)
    assert conflict.value.code == "CHECKPOINT_KEY_CONFLICT"
    journal = services.run_journal(run["run_id"], store=store)
    assert journal["cursor"] == 2 and len(journal["steps"]) == 2
    assert journal["steps"][0]["summary"] == "framed"


def test_concurrent_distinct_checkpoints_are_not_lost():
    from sonaloop.storage import Store

    with Store() as setup:
        project = services.start_project("Concurrent journal", "g", store=setup)
        run = services.start_run(project["id"], store=setup)
    barrier = Barrier(2)

    def checkpoint(suffix: str):
        with Store() as thread_store:
            barrier.wait(timeout=10)
            return services.checkpoint_step(run["run_id"], {
                "task_id": suffix,
                "bucket": "act",
                "key": services.run_key(run["run_id"], suffix),
                "summary": suffix,
            }, store=thread_store)

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = [future.result() for future in [
            pool.submit(checkpoint, "one"), pool.submit(checkpoint, "two")]]

    assert sorted(receipt["cursor"] for receipt in receipts) == [1, 2]
    with Store() as check:
        journal = services.run_journal(run["run_id"], store=check)
    assert journal["cursor"] == 2
    assert {row["key"] for row in journal["steps"]} == {
        services.run_key(run["run_id"], "one"),
        services.run_key(run["run_id"], "two"),
    }


def test_finish_run_rejects_open_plan_and_missing_critics_without_mutation(store):
    project = services.start_project("Cannot force", "g", store=store)
    run = services.start_run(project["id"], store=store)

    with pytest.raises(P.PlanError) as open_exc:
        services.finish_run(run["run_id"], "finished", store=store)
    assert open_exc.value.code == "RUN_NOT_FINISHABLE"
    assert services.run_journal(run["run_id"], store=store)["status"] == "active"

    services.record_frame(project["id"], "frame__root", ["q?"], memory_refs=["memory:1"], store=store)
    with pytest.raises(P.PlanError) as critic_exc:
        services.finish_run(run["run_id"], "finished", store=store)
    assert critic_exc.value.code == "RUN_NOT_FINISHABLE"
    assert "critic" in critic_exc.value.message
    assert services.run_journal(run["run_id"], store=store)["status"] == "active"

    with pytest.raises(P.PlanError) as mismatch:
        services.record_critic_round(
            run["run_id"], "missing_critic_report", "critic:test", store=store)
    assert mismatch.value.code == "CRITIC_REPORT_MISMATCH"
    assert services.run_journal(run["run_id"], store=store)["critic_rounds"] == []

    stopped = services.finish_run(run["run_id"], "stopped", store=store)
    assert stopped["status"] == "stopped"


def test_finish_run_rejects_arbitrary_terminal_status(store):
    project = services.start_project("Status enum", "g", store=store)
    run = services.start_run(project["id"], store=store)
    with pytest.raises(P.PlanError) as exc:
        services.finish_run(run["run_id"], "done", store=store)
    assert exc.value.code == "INVALID_RUN_STATUS"
    assert services.run_journal(run["run_id"], store=store)["status"] == "active"


def test_critic_retries_cannot_manufacture_two_independent_dry_rounds(store):
    project = services.start_project("Critic retry", "g", store=store)
    run = services.start_run(project["id"], store=store)
    services.record_frame(
        project["id"], "frame__root", ["q?"], memory_refs=["memory:1"], store=store)
    scores = {
        row["key"]: 5
        for row in services.brief_completeness_critic(project["id"], store=store)["frame"]["rubric"]
    }
    verdict = {"passed": True, "missing": [], "scores": scores, "rationale": "dry"}

    dispatch_one = services.run_step(run["run_id"], store=store)
    assert dispatch_one["kind"] == "critic"
    report_one = services.record_completeness_critic(
        project["id"], verdict, run["run_id"], dispatch_one["operation_id"], store=store)
    replay_report = services.record_completeness_critic(
        project["id"], verdict, run["run_id"], dispatch_one["operation_id"], store=store)
    assert replay_report["id"] == report_one["id"] and replay_report["deduplicated"] is True
    with pytest.raises(P.PlanError) as critic_conflict:
        services.record_completeness_critic(
            project["id"], {**verdict, "rationale": "different"}, run["run_id"],
            dispatch_one["operation_id"], store=store)
    assert critic_conflict.value.code == "CRITIC_OPERATION_CONFLICT"

    first_round = services.record_critic_round(
        run["run_id"], report_one["id"], dispatch_one["key"], store=store)
    replay_round = services.record_critic_round(
        run["run_id"], report_one["id"], dispatch_one["key"], store=store)
    assert first_round["round"] == replay_round["round"] == 0
    assert replay_round["deduplicated"] is True
    assert len(services.run_journal(run["run_id"], store=store)["critic_rounds"]) == 1

    with pytest.raises(P.PlanError) as not_two:
        services.finish_run(run["run_id"], "finished", store=store)
    assert not_two.value.code == "RUN_NOT_FINISHABLE"

    dispatch_two = services.run_step(run["run_id"], store=store)
    assert dispatch_two["kind"] == "critic" and dispatch_two["key"] != dispatch_one["key"]
    report_two = services.record_completeness_critic(
        project["id"], verdict, run["run_id"], dispatch_two["operation_id"], store=store)
    services.record_critic_round(
        run["run_id"], report_two["id"], dispatch_two["key"], store=store)
    finished = services.finish_run(run["run_id"], "finished", store=store)
    assert finished["status"] == "finished"
