"""Security and immutability contract for Remote-MCP screenshot evidence."""
from __future__ import annotations

import asyncio
import base64
from contextlib import contextmanager
from io import BytesIO
import struct
import zlib

import pytest
from PIL import Image

from sonaloop import config, services
from sonaloop.mcp_server import build_server
from sonaloop.research_integrity import IntegrityError, reaction_stimuli, resolve_project_ref


@contextmanager
def _workspace(workspace_id: str = "ws_remote_test"):
    token = config.set_request_tenant_scope([workspace_id], workspace_id)
    try:
        yield
    finally:
        config.reset_request_tenant_scope(token)


def _image(fmt: str = "PNG", *, size: tuple[int, int] = (24, 16)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, (26, 91, 151)).save(out, format=fmt)
    return out.getvalue()


def _png_dimension_bomb(width: int = 50_000, height: int = 50_000) -> bytes:
    """Tiny encoded PNG header claiming a huge decoded canvas (no allocation here)."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")


def _reaction(store, suffix: str = "remote"):
    # Issue the run dispatch in the same authenticated workspace that will
    # later admit the bytes; dispatch scope is part of the authorization proof.
    with _workspace():
        project = services.start_project(
            f"Remote reaction {suffix}", "Inspect exact screens",
            methodology="Reaction Test", persona_ids=[],
            operation_id=f"remote:{suffix}:project", store=store,
        )
        run = services.start_run(
            project["id"], operation_id=f"remote:{suffix}:run", store=store,
        )
        dispatch = services.run_step(run["run_id"], store=store)
    assert dispatch["next_action"]["capability"] == "product_understanding"
    return project, run, dispatch


def _admit(store, project, run, dispatch, *, operation_id="upload:1", data=None,
           filename="home.png", media_type="image/png", label="Home",
           revision="deploy:abc"):
    return services.admit_remote_screenshot(
        project["id"], run["run_id"], operation_id,
        base64.b64encode(data or _image()).decode("ascii"), filename, media_type,
        "2026-08-08T10:00:00Z", revision, label=label,
        dispatch_token=dispatch["dispatch_token"], store=store,
    )


def test_remote_admission_is_retry_safe_scanned_digest_bound_and_has_no_url_surface(store):
    project, run, dispatch = _reaction(store)
    with _workspace():
        admitted = _admit(store, project, run, dispatch)
        replay = _admit(store, project, run, dispatch)

    assert admitted["id"] == replay["id"]
    assert replay["idempotent_replay"] is True
    assert admitted["content_digest"].startswith("sha256:")
    assert len(admitted["content_sha256"]) == 64
    assert admitted["admission"]["workspace_id"] == "ws_remote_test"
    assert admitted["admission"]["project_id"] == project["id"]
    assert admitted["admission"]["run_id"] == run["run_id"]
    assert admitted["admission"]["scan"]["built_in"]["status"] == "clean"
    assert admitted["admission"]["scan"]["external"]["status"] == "not_configured"
    assert len(store.get_research_project(project["id"])["assets"]) == 1
    payload, record = services.get_asset_content(project["id"], admitted["id"], store=store)
    assert payload == _image() and record["id"] == admitted["id"]

    tools = {tool.name: tool for tool in asyncio.run(build_server().list_tools())}
    schema = tools["admit_remote_screenshot"].inputSchema["properties"]
    assert "content_base64" in schema
    assert not {"path", "url", "source_url", "content_url"} & schema.keys()


def test_remote_admission_rejects_identity_scope_and_operation_conflicts_before_mutation(store):
    project, run, dispatch = _reaction(store, "scope")
    other_project, other_run, other_dispatch = _reaction(store, "other")
    with _workspace():
        first = _admit(store, project, run, dispatch, operation_id="same-op")
        with pytest.raises(IntegrityError) as changed:
            _admit(store, project, run, dispatch, operation_id="same-op", label="Changed")
        assert changed.value.code == "REMOTE_ASSET_IDEMPOTENCY_CONFLICT"

        with pytest.raises(IntegrityError) as wrong_run:
            services.admit_remote_screenshot(
                project["id"], other_run["run_id"], "wrong-run",
                base64.b64encode(_image()).decode(), "home.png", "image/png",
                "2026-08-08T10:00:00Z", "deploy:abc",
                dispatch_token=dispatch["dispatch_token"], store=store,
            )
        assert wrong_run.value.code == "REMOTE_RUN_SCOPE_MISMATCH"

        with pytest.raises(Exception):
            services.admit_remote_screenshot(
                project["id"], run["run_id"], "wrong-token",
                base64.b64encode(_image()).decode(), "home.png", "image/png",
                "2026-08-08T10:00:00Z", "deploy:abc",
                dispatch_token=other_dispatch["dispatch_token"], store=store,
            )
        assert len(store.get_research_project(project["id"])["assets"]) == 1
        assert first["id"]

    with pytest.raises(IntegrityError) as unbound:
        _admit(store, project, run, dispatch, operation_id="unbound")
    assert unbound.value.code == "REMOTE_WORKSPACE_SCOPE_REQUIRED"


@pytest.mark.parametrize(
    ("operation_id", "data", "filename", "media_type", "code"),
    [
        ("mime", _image(), "wrong.jpg", "image/jpeg", "REMOTE_ASSET_POLYGLOT_REJECTED"),
        ("polyglot", _image() + b"<script>alert(1)</script>", "x.png", "image/png",
         "REMOTE_ASSET_POLYGLOT_REJECTED"),
        ("eicar", _image() + b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", "x.png", "image/png",
         "REMOTE_ASSET_MALWARE_SIGNATURE"),
        ("dimension", _image(size=(10_001, 1)), "wide.png", "image/png",
         "REMOTE_ASSET_DECOMPRESSION_LIMIT"),
        ("bomb", _png_dimension_bomb(), "bomb.png", "image/png",
         "REMOTE_ASSET_DECOMPRESSION_LIMIT"),
    ],
)
def test_remote_admission_rejects_mime_magic_polyglot_malware_and_bombs(
        store, operation_id, data, filename, media_type, code):
    project, run, dispatch = _reaction(store, operation_id)
    with _workspace():
        with pytest.raises(IntegrityError) as exc:
            _admit(store, project, run, dispatch, operation_id=operation_id,
                   data=data, filename=filename, media_type=media_type)
    assert exc.value.code == code
    assert not (store.get_research_project(project["id"]).get("assets") or [])


def test_shared_production_scanner_is_fail_closed_and_external_argv_has_no_shell(
        store, monkeypatch):
    project, run, dispatch = _reaction(store, "scanner")
    monkeypatch.setattr(config, "postgres_row_tenancy_enabled", lambda: True)
    monkeypatch.delenv("SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON", raising=False)
    monkeypatch.delenv("SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED", raising=False)
    with _workspace():
        with pytest.raises(IntegrityError) as missing:
            _admit(store, project, run, dispatch, operation_id="scanner-missing")
        assert missing.value.code == "REMOTE_ASSET_SCANNER_REQUIRED"

        calls = []

        class Result:
            returncode = 0

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return Result()

        import sonaloop.services._remote_assets as remote_assets
        monkeypatch.setattr(remote_assets.subprocess, "run", fake_run)
        monkeypatch.setenv("SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON", '["/bin/true", "{path}"]')
        admitted = _admit(store, project, run, dispatch, operation_id="scanner-clean")
        assert admitted["admission"]["scan"]["external"]["status"] == "clean"
        assert calls and calls[0][1]["shell"] is False
        assert calls[0][1]["stdout"] is remote_assets.subprocess.DEVNULL
        assert calls[0][1]["stderr"] is remote_assets.subprocess.DEVNULL
        assert calls[0][0][0] == "/bin/true"

        # An immutable clean receipt remains retryable if the scanner is briefly
        # unavailable; exact replay does not manufacture a second scan result.
        monkeypatch.delenv("SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON")
        replay = _admit(store, project, run, dispatch, operation_id="scanner-clean")
        assert replay["id"] == admitted["id"]
        assert replay["idempotent_replay"] is True


def test_production_replay_rejects_a_local_receipt_without_external_scan(store, monkeypatch):
    project, run, dispatch = _reaction(store, "scanner-migration")
    with _workspace():
        local = _admit(store, project, run, dispatch, operation_id="local-only")
        assert local["admission"]["scan"]["external"]["status"] == "not_configured"

        # Simulate restoring/migrating the project into shared production. The
        # old database row cannot bypass today's production scanner policy.
        monkeypatch.setattr(config, "postgres_row_tenancy_enabled", lambda: True)
        monkeypatch.delenv("SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED", raising=False)
        with pytest.raises(IntegrityError) as replay:
            _admit(store, project, run, dispatch, operation_id="local-only")
    assert replay.value.code == "REMOTE_ASSET_REPLAY_SCAN_INSUFFICIENT"


def test_manifest_and_product_understanding_freeze_exact_versions_revision_and_coverage(store):
    project, run, dispatch = _reaction(store, "manifest")
    with _workspace():
        first = _admit(store, project, run, dispatch, operation_id="screen:home", label="Home")
        second = _admit(store, project, run, dispatch, operation_id="screen:finance", label="Finance")
        first_ref = {"kind": "asset", "id": first["id"]}
        with pytest.raises(IntegrityError) as unmanifested:
            services.record_product_understanding(
                project["id"], {"name": "SHKB"}, "deploy:abc",
                routes=[{"path": "/", "evidence_refs": [first_ref]}],
                flows=[], states=[],
                capabilities=[{"claim": "Home is visible", "status": "observed_present",
                               "evidence_refs": [first_ref]}], evidence_refs=[first_ref],
                observed_at="2026-08-08T10:04:00Z",
                dispatch_token=dispatch["dispatch_token"], store=store,
            )
        assert unmanifested.value.code == "STIMULUS_MANIFEST_REQUIRED"

        services.record_reaction_test_capture_review(
            project["id"], True,
            [{"asset_version_id": first["id"], "role": "Home state"},
             {"asset_version_id": second["id"], "role": "Finance state"}],
            [], "The exact two-screen inventory covers the bounded home-to-finance task.",
            "capture-review:v1", dispatch["dispatch_token"], store=store,
        )

        manifest = services.record_flow_manifest(
            project["id"], run["run_id"], "flow:v1", "home-finance", "Home to finance",
            [{"asset_version_id": first["id"], "label": "Home"},
             {"asset_version_id": second["id"], "label": "Finance"}],
            "Find financing from the homepage", "deploy:abc", "2026-08-08T10:05:00Z",
            dispatch_token=dispatch["dispatch_token"], store=store,
        )
        replay = services.record_flow_manifest(
            project["id"], run["run_id"], "flow:v1", "home-finance", "Home to finance",
            [{"asset_version_id": first["id"], "label": "Home"},
             {"asset_version_id": second["id"], "label": "Finance"}],
            "Find financing from the homepage", "deploy:abc", "2026-08-08T10:05:00Z",
            dispatch_token=dispatch["dispatch_token"], store=store,
        )
        assert replay["id"] == manifest["id"] and replay["idempotent_replay"] is True
        assert manifest["version"] == 1 and manifest["manifest_digest"].startswith("sha256:")
        assert [step["asset_version_id"] for step in manifest["steps"]] == [first["id"], second["id"]]

        flow_ref = {"kind": "flow", "id": manifest["id"]}
        binding = {"id": manifest["id"], "version": 1,
                   "target_revision": "deploy:abc",
                   "manifest_digest": manifest["manifest_digest"]}
        coverage = [
            {"step_index": 0, "status": "inspected",
             "evidence_refs": [{"kind": "asset", "id": first["id"]}]},
            {"step_index": 1, "status": "inspected",
             "evidence_refs": [{"kind": "asset", "id": second["id"]}]},
        ]
        with pytest.raises(IntegrityError) as revision:
            services.record_product_understanding(
                project["id"], {"name": "SHKB"}, "deploy:different",
                routes=[{"path": "/", "evidence_refs": [flow_ref]}],
                flows=[{"name": "Home to finance", "evidence_refs": [flow_ref]}], states=[],
                capabilities=[{"claim": "Flow is visible", "status": "observed_present",
                               "evidence_refs": [flow_ref]}], evidence_refs=[flow_ref],
                stimulus_manifest=binding, coverage_checklist=coverage,
                observed_at="2026-08-08T10:06:00Z",
                dispatch_token=dispatch["dispatch_token"], store=store,
            )
        assert revision.value.code == "PRODUCT_REVISION_MISMATCH"

        pu = services.record_product_understanding(
            project["id"], {"name": "SHKB"}, "deploy:abc",
            routes=[{"path": "/", "evidence_refs": [flow_ref]}],
            flows=[{"name": "Home to finance", "evidence_refs": [flow_ref]}], states=[],
            capabilities=[{"claim": "Flow is visible", "status": "observed_present",
                           "evidence_refs": [flow_ref]}], evidence_refs=[flow_ref],
            stimulus_manifest=binding, coverage_checklist=coverage,
            observed_at="2026-08-08T10:06:00Z",
            dispatch_token=dispatch["dispatch_token"], store=store,
        )
        assert pu["stimulus_manifest"]["manifest_version"] == 1
        assert [c["asset_version_id"] for c in pu["coverage_checklist"]] == [first["id"], second["id"]]

        newer = services.record_flow_manifest(
            project["id"], run["run_id"], "flow:v2", "home-finance", "Home to finance",
            [{"asset_version_id": first["id"], "label": "Home revised label"},
             {"asset_version_id": second["id"], "label": "Finance"}],
            "Find financing from the homepage", "deploy:abc", "2026-08-08T10:07:00Z",
            dispatch_token=dispatch["dispatch_token"], store=store,
        )
        assert newer["version"] == 2 and newer["supersedes"] == manifest["id"]
        old = services.get_product_understanding(project["id"], pu["id"], store=store)
        assert old["stimulus_manifest"]["manifest_version"] == 1
        assert old["stimulus_manifest"]["manifest_digest"] == manifest["manifest_digest"]
        # The new manifest is a candidate for a new preflight, never an implicit
        # substitution in the already-bound Reaction Test.
        allowed = {(row["kind"], row["id"])
                   for row in reaction_stimuli(project["id"], store)}
        assert allowed == {
            ("flow", manifest["id"]),
            ("asset", first["id"]),
            ("asset", second["id"]),
        }
        assert ("flow", newer["id"]) not in allowed


def test_persona_memory_and_evidence_refs_resolve_only_inside_project_cohort(store):
    now = "2026-08-08T10:00:00Z"
    for pid in ("persona_in", "persona_out"):
        store.upsert_persona({"id": pid, "slug": pid, "display_name": pid,
                              "created_at": now, "updated_at": now})
    project = services.start_project(
        "Cohort refs", "No invented refs", persona_ids=["persona_in"], store=store,
    )
    inside = services.attach_evidence("persona_in", "interview", "inside", store=store)
    outside = services.attach_evidence("persona_out", "interview", "outside", store=store)
    store.insert_experience_event({"id": "event_in", "persona_id": "persona_in",
                                   "timestamp": now, "event_type": "work", "created_at": now})
    store.insert_experience_event({"id": "event_out", "persona_id": "persona_out",
                                   "timestamp": now, "event_type": "work", "created_at": now})

    assert resolve_project_ref(project["id"], {"kind": "persona", "id": "persona_in"}, store)["record"]
    assert resolve_project_ref(project["id"], {"kind": "evidence", "id": inside["id"]}, store)["record"]
    assert resolve_project_ref(project["id"], {"kind": "memory", "id": "event_in"}, store)["record"]
    for ref in (
        {"kind": "persona", "id": "persona_out"},
        {"kind": "persona", "id": "invented"},
        {"kind": "evidence", "id": outside["id"]},
        {"kind": "evidence", "id": "invented"},
        {"kind": "memory", "id": "event_out"},
        {"kind": "recall", "id": "invented"},
    ):
        with pytest.raises(IntegrityError):
            resolve_project_ref(project["id"], ref, store)
