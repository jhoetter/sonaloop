"""Fail-closed Remote-MCP screenshot admission and immutable flow manifests.

This is deliberately *not* the generic local :func:`attach_asset` path.  A
remote principal can submit bounded bytes only; there is no URL or filesystem
parameter, so SSRF, redirect rebinding and host-path reads are absent from the
contract.  Admission is bound to the authenticated workspace, project, run,
operation id and Product Understanding dispatch before the bytes become
evidence.
"""
from __future__ import annotations

import base64
import binascii
import copy
from datetime import datetime
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import warnings

from PIL import Image, UnidentifiedImageError

from .. import config
from ..config import utc_now_iso
from ..research_integrity import IntegrityError, operation_fingerprint
from ..storage import Store

from ._common import *  # noqa: F401,F403  (stable_id, dispatch helpers, project guard)


REMOTE_SCREENSHOT_SCHEMA = "sonaloop.remote_screenshot_admission.v1"
FLOW_MANIFEST_SCHEMA = "sonaloop.flow_manifest.v1"
STIMULUS_BINDING_SCHEMA = "sonaloop.stimulus_manifest_binding.v1"
MAX_REMOTE_SCREENSHOT_BYTES = 10 * 1024 * 1024
MAX_REMOTE_SCREENSHOT_DIMENSION = 10_000
MAX_REMOTE_SCREENSHOT_PIXELS = 20_000_000
MAX_REMOTE_DECODED_BYTES = 80 * 1024 * 1024
_EICAR = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
_FORMAT_BY_EXT = {
    "png": ("PNG", "image/png", "png"),
    "jpg": ("JPEG", "image/jpeg", "jpg"),
    "jpeg": ("JPEG", "image/jpeg", "jpg"),
    "webp": ("WEBP", "image/webp", "webp"),
}


def _required_text(value: Any, name: str, *, maximum: int = 240) -> str:
    text = str(value or "").strip()
    if not text:
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", f"{name} is required")
    if len(text) > maximum or any(ord(char) < 32 for char in text):
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", f"{name} is invalid or too long")
    return text


def _optional_text(value: Any, name: str, *, maximum: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) > maximum or any(ord(char) < 32 for char in text):
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", f"{name} is invalid or too long")
    return text


def _timestamp(value: Any, name: str) -> str:
    text = _required_text(value, name, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", f"{name} must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None:
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", f"{name} must include a timezone")
    return text


def _remote_workspace() -> str:
    scope = config.request_tenant_scope()
    if not scope or not str(scope[1] or "").strip():
        raise IntegrityError(
            "REMOTE_WORKSPACE_SCOPE_REQUIRED",
            "remote screenshot admission requires an authenticated active workspace",
        )
    accessible, active = scope
    if active not in accessible:
        raise IntegrityError("REMOTE_WORKSPACE_SCOPE_REQUIRED", "active workspace is outside read scope")
    return str(active)


def _bound_dispatch(project_id: str, run_id: str, dispatch_token: str,
                    output_kind: str, store: Store) -> tuple[dict[str, Any], dict[str, Any]]:
    token = _required_text(dispatch_token, "dispatch_token")
    run = store.get_run(run_id)
    if not run or str(run.get("project_id") or "") != project_id:
        raise IntegrityError(
            "REMOTE_RUN_SCOPE_MISMATCH",
            f"run {run_id!r} is not an authorized run of project {project_id}",
        )
    ctx = prepare_dispatch_write(  # noqa: F821 (bound by services package)
        project_id, token, None, output_kind, store,
        allowed_buckets={"analyze"}, required_capability="product_understanding",
    )
    if str(ctx.get("run_id") or "") != run_id:
        raise IntegrityError(
            "REMOTE_RUN_SCOPE_MISMATCH",
            "dispatch_token and explicit run_id do not identify the same governed run",
        )
    return run, ctx


def _decode_base64(content_base64: str) -> bytes:
    if not isinstance(content_base64, str) or not content_base64:
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", "content_base64 is required")
    # Reject before allocating a decoded object much larger than the byte cap.
    if len(content_base64) > ((MAX_REMOTE_SCREENSHOT_BYTES + 2) // 3) * 4 + 4:
        raise IntegrityError("REMOTE_ASSET_TOO_LARGE", "encoded screenshot exceeds the 10MB cap")
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise IntegrityError("REMOTE_ASSET_BAD_BASE64", "content_base64 is not canonical base64") from None
    if not data:
        raise IntegrityError("REMOTE_ASSET_BAD_INPUT", "screenshot is empty")
    if base64.b64encode(data).decode("ascii") != content_base64:
        raise IntegrityError("REMOTE_ASSET_BAD_BASE64", "content_base64 is not canonical base64")
    if len(data) > MAX_REMOTE_SCREENSHOT_BYTES:
        raise IntegrityError("REMOTE_ASSET_TOO_LARGE", "screenshot exceeds the 10MB cap")
    return data


def _png_has_exact_eof(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    while offset + 12 <= len(data):
        length = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            return False
        if kind == b"IEND":
            return length == 0 and end == len(data)
        offset = end
    return False


def _container_is_exact(data: bytes, expected_format: str) -> bool:
    if expected_format == "PNG":
        return _png_has_exact_eof(data)
    if expected_format == "JPEG":
        return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if expected_format == "WEBP":
        return (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
                and int.from_bytes(data[4:8], "little") + 8 == len(data))
    return False


def _validate_remote_image(data: bytes, filename: str, media_type: str) -> dict[str, Any]:
    name = _required_text(filename, "filename")
    if Path(name).name != name or "\\" in name or name in {".", ".."}:
        raise IntegrityError("REMOTE_ASSET_BAD_FILENAME", "filename must be one safe basename")
    ext = Path(name).suffix.lower().lstrip(".")
    expected = _FORMAT_BY_EXT.get(ext)
    if not expected:
        raise IntegrityError(
            "REMOTE_ASSET_TYPE_UNSUPPORTED",
            "remote screenshots support only .png, .jpg/.jpeg and .webp",
        )
    expected_format, expected_mime, canonical_ext = expected
    declared = _required_text(media_type, "media_type", maximum=80).lower()
    if declared != expected_mime:
        raise IntegrityError(
            "REMOTE_ASSET_MIME_MISMATCH",
            f"filename extension {ext!r} requires {expected_mime}, got {declared}",
        )
    if _EICAR in data.upper():
        raise IntegrityError("REMOTE_ASSET_MALWARE_SIGNATURE", "built-in EICAR content scan rejected upload")
    if not _container_is_exact(data, expected_format):
        raise IntegrityError(
            "REMOTE_ASSET_POLYGLOT_REJECTED",
            "image container/magic is invalid or has a trailing payload",
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as probe:
                if probe.format != expected_format:
                    raise IntegrityError(
                        "REMOTE_ASSET_MAGIC_MISMATCH",
                        f"decoded format {probe.format!r} does not match {expected_format}",
                    )
                width, height = probe.size
                frames = int(getattr(probe, "n_frames", 1) or 1)
                probe.verify()
            if width <= 0 or height <= 0:
                raise IntegrityError("REMOTE_ASSET_DECODE_FAILED", "image has invalid dimensions")
            pixels = width * height
            if (width > MAX_REMOTE_SCREENSHOT_DIMENSION
                    or height > MAX_REMOTE_SCREENSHOT_DIMENSION
                    or pixels > MAX_REMOTE_SCREENSHOT_PIXELS):
                raise IntegrityError(
                    "REMOTE_ASSET_DECOMPRESSION_LIMIT",
                    "decoded screenshot exceeds dimension/pixel limits",
                )
            if frames != 1:
                raise IntegrityError("REMOTE_ASSET_ANIMATION_REJECTED", "animated images are not screenshots")
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()
                bands = max(1, len(decoded.getbands()))
                if width * height * bands > MAX_REMOTE_DECODED_BYTES:
                    raise IntegrityError(
                        "REMOTE_ASSET_DECOMPRESSION_LIMIT",
                        "decoded screenshot exceeds the 80MB pixel budget",
                    )
                mode = str(decoded.mode)
    except IntegrityError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise IntegrityError(
            "REMOTE_ASSET_DECOMPRESSION_LIMIT", "Pillow rejected a decompression bomb"
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise IntegrityError("REMOTE_ASSET_DECODE_FAILED", "Pillow could not verify and load the image") from None
    return {
        "format": expected_format,
        "media_type": expected_mime,
        "canonical_ext": canonical_ext,
        "width": width,
        "height": height,
        "pixels": pixels,
        "mode": mode,
        "frames": frames,
    }


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise IntegrityError("REMOTE_ASSET_SCANNER_CONFIG", f"{name} must be a boolean")


def _scanner_timeout() -> float:
    raw = os.getenv("SONALOOP_REMOTE_ASSET_SCANNER_TIMEOUT_SECONDS", "30")
    try:
        return min(120.0, max(1.0, float(raw)))
    except ValueError:
        raise IntegrityError(
            "REMOTE_ASSET_SCANNER_CONFIG",
            "SONALOOP_REMOTE_ASSET_SCANNER_TIMEOUT_SECONDS must be numeric",
        ) from None


def _scanner_argv(path: Path) -> tuple[list[str], str] | None:
    raw = (os.getenv("SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON") or "").strip()
    required = _bool_env(
        "SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED",
        config.postgres_row_tenancy_enabled(),
    )
    if not raw:
        if required:
            raise IntegrityError(
                "REMOTE_ASSET_SCANNER_REQUIRED",
                "shared production admission requires SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON",
            )
        return None
    try:
        configured = json.loads(raw)
    except json.JSONDecodeError:
        raise IntegrityError(
            "REMOTE_ASSET_SCANNER_CONFIG",
            "SONALOOP_REMOTE_ASSET_SCANNER_ARGV_JSON must be a JSON string array",
        ) from None
    if (not isinstance(configured, list) or not configured or len(configured) > 32
            or any(not isinstance(arg, str) or not arg or len(arg) > 512 for arg in configured)):
        raise IntegrityError("REMOTE_ASSET_SCANNER_CONFIG", "scanner argv must be 1..32 bounded strings")
    executable = Path(configured[0])
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        raise IntegrityError(
            "REMOTE_ASSET_SCANNER_CONFIG", "scanner executable must be an absolute executable file",
        )
    argv: list[str] = []
    inserted = False
    for arg in configured:
        if "{" in arg or "}" in arg:
            if arg != "{path}":
                raise IntegrityError(
                    "REMOTE_ASSET_SCANNER_CONFIG", "only an exact {path} scanner placeholder is allowed",
                )
            argv.append(str(path))
            inserted = True
        else:
            argv.append(arg)
    if not inserted:
        argv.append(str(path))
    policy_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return argv, policy_digest


def _scan_remote_image(data: bytes, suffix: str) -> dict[str, Any]:
    """Run the built-in signature check plus an optional real external scanner.

    The built-in scan is intentionally described narrowly; it is not a general
    antivirus claim.  Shared PostgreSQL production requires an external scanner
    by default.  The command is a JSON argv vector and is never interpreted by a
    shell.
    """
    quarantine = config.partition_dir() / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="remote-asset-", dir=quarantine) as temp_dir:
        candidate = Path(temp_dir) / f"candidate.{suffix}"
        candidate.write_bytes(data)
        candidate.chmod(0o600)
        external = _scanner_argv(candidate)
        if external is None:
            return {
                "built_in": {"engine": "eicar-signature-v1", "status": "clean"},
                "external": {"status": "not_configured", "required": False},
                "scanned_at": utc_now_iso(),
            }
        argv, policy_digest = external
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                # Exit status is the contract. Scanner prose may contain file
                # material and is neither needed nor allowed to grow process
                # memory, logs or telemetry, so discard it at the OS boundary.
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=_scanner_timeout(),
                check=False,
                cwd=temp_dir,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            )
        except subprocess.TimeoutExpired:
            raise IntegrityError("REMOTE_ASSET_SCAN_TIMEOUT", "external content scanner timed out") from None
        except OSError:
            raise IntegrityError("REMOTE_ASSET_SCANNER_FAILED", "external content scanner could not run") from None
        if completed.returncode != 0:
            raise IntegrityError(
                "REMOTE_ASSET_SCAN_REJECTED",
                f"external content scanner rejected the screenshot (exit {completed.returncode})",
            )
        return {
            "built_in": {"engine": "eicar-signature-v1", "status": "clean"},
            "external": {
                "engine": Path(argv[0]).name,
                "status": "clean",
                "required": _bool_env("SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED",
                                      config.postgres_row_tenancy_enabled()),
                "policy_sha256": policy_digest,
            },
            "scanned_at": utc_now_iso(),
        }


def _ensure_content_blob(data: bytes, digest: str, ext: str) -> tuple[Path, bool]:
    from ._project_assets import _assets_dir

    directory = _assets_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = (directory / f"{digest}.{ext}").resolve()
    if not target.is_relative_to(directory.resolve()):
        raise IntegrityError("REMOTE_ASSET_STORAGE_ERROR", "content-addressed target escaped asset store")
    if target.exists():
        if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise IntegrityError("REMOTE_ASSET_STORAGE_ERROR", "existing content blob failed digest verification")
        return target, True
    fd, temporary = tempfile.mkstemp(prefix=".remote-admission-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target)
            deduplicated = False
        except FileExistsError:
            deduplicated = True
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise IntegrityError("REMOTE_ASSET_STORAGE_ERROR", "stored content blob failed digest verification")
        return target, deduplicated
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _admission_operation(project: dict[str, Any], operation_id: str) -> dict[str, Any] | None:
    return next((a for a in (project.get("assets") or [])
                 if str((a.get("admission") or {}).get("operation_id") or "") == operation_id), None)


def _require_valid_replay_scan(record: dict[str, Any]) -> None:
    """Do not let a locally admitted receipt become production evidence by migration.

    Exact retries intentionally reuse the immutable scan receipt instead of invoking
    a non-deterministic scanner again.  When the *current* environment requires an
    external scanner, however, that receipt must prove a prior clean external scan.
    This closes the local-SQLite -> shared-Postgres migration/replay gap while keeping
    a genuinely scanned retry stable when the scanner is temporarily unavailable.
    """
    required = _bool_env(
        "SONALOOP_REMOTE_ASSET_EXTERNAL_SCAN_REQUIRED",
        config.postgres_row_tenancy_enabled(),
    )
    external = (((record.get("admission") or {}).get("scan") or {}).get("external") or {})
    if required and (str(external.get("status") or "") != "clean"
                     or not str(external.get("policy_sha256") or "")):
        raise IntegrityError(
            "REMOTE_ASSET_REPLAY_SCAN_INSUFFICIENT",
            "the existing admission has no clean external-scan receipt required by this environment",
        )


def admit_remote_screenshot(
    project_id: str,
    run_id: str,
    operation_id: str,
    content_base64: str,
    filename: str,
    media_type: str,
    captured_at: str,
    target_revision: str,
    title: str = "",
    label: str = "",
    dispatch_token: str = "",
    store: Store | None = None,
) -> dict[str, Any]:
    """Admit one scanned screenshot from a Remote-MCP caller.

    There is intentionally no ``path`` or URL argument.  Exact retries reuse
    ``operation_id``; changing any content or provenance under that id fails
    before project mutation.  The active workspace comes only from the request
    authorization context and is never caller-selected.
    """
    store = store or Store()
    workspace_id = _remote_workspace()
    project = _require_research_project(store, project_id)  # noqa: F821
    run_id = _required_text(run_id, "run_id")
    operation_id = _required_text(operation_id, "operation_id")
    _run, dispatch_ctx = _bound_dispatch(project["id"], run_id, dispatch_token, "asset", store)
    data = _decode_base64(content_base64)
    image = _validate_remote_image(data, filename, media_type)
    captured_at = _timestamp(captured_at, "captured_at")
    target_revision = _required_text(target_revision, "target_revision")
    title = _optional_text(title, "title")
    label = _optional_text(label, "label")
    digest = hashlib.sha256(data).hexdigest()
    intent = {
        "schema": REMOTE_SCREENSHOT_SCHEMA,
        "workspace_id": workspace_id,
        "project_id": project["id"],
        "run_id": run_id,
        "operation_id": operation_id,
        "content_sha256": digest,
        "filename": filename,
        "media_type": image["media_type"],
        "captured_at": captured_at,
        "target_revision": target_revision,
        "title": title,
        "label": label,
    }
    fingerprint = operation_fingerprint(intent)

    existing = _admission_operation(project, operation_id)
    if existing:
        if str((existing.get("admission") or {}).get("operation_fingerprint") or "") != fingerprint:
            raise IntegrityError(
                "REMOTE_ASSET_IDEMPOTENCY_CONFLICT",
                "operation_id was already admitted with different bytes or provenance",
            )
        _require_valid_replay_scan(existing)
        # A crash or restore may have retained the immutable DB receipt but not
        # its content-addressed blob.  The caller supplied the exact verified
        # bytes again, so repair that blob under the same digest before exposing
        # the replay as readable evidence.
        _ensure_content_blob(data, digest, image["canonical_ext"])
        dispatch = bind_dispatch_output(  # noqa: F821
            dispatch_ctx, {"kind": "asset", "id": existing["id"]},
            "admitted scanned remote screenshot", store, complete=False,
        )
        return {**existing, "idempotent_replay": True, "dispatch": dispatch}

    scan = _scan_remote_image(data, image["canonical_ext"])
    _target, deduplicated = _ensure_content_blob(data, digest, image["canonical_ext"])
    asset_id = stable_id("asset", workspace_id, project["id"], run_id, operation_id)  # noqa: F821
    record: dict[str, Any] | None = None
    replay = False
    for _attempt in range(16):
        current = store.get_research_project(project["id"])
        if not current:
            raise IntegrityError("UNKNOWN_PROJECT", f"unknown research project: {project_id}")
        existing = _admission_operation(current, operation_id)
        if existing:
            if str((existing.get("admission") or {}).get("operation_fingerprint") or "") != fingerprint:
                raise IntegrityError(
                    "REMOTE_ASSET_IDEMPOTENCY_CONFLICT",
                    "operation_id was concurrently admitted with different bytes or provenance",
                )
            _require_valid_replay_scan(existing)
            record, replay = existing, True
            break
        if any(str(a.get("id") or "") == asset_id for a in (current.get("assets") or [])):
            raise IntegrityError("REMOTE_ASSET_ID_COLLISION", "asset authorization identity collision")
        now = utc_now_iso()
        from ._project_assets import _assets_url_base
        record = {
            "id": asset_id,
            "kind": "screenshot",
            "filename": filename,
            "title": title or label or filename,
            "label": label or title or filename,
            "notes": "",
            "source": "remote_mcp:direct_upload",
            "direction": "in",
            "media_type": image["media_type"],
            "bytes": len(data),
            "content_digest": f"sha256:{digest}",
            "content_sha256": digest,
            "asset_path": f"data/assets/{digest}.{image['canonical_ext']}",
            "url": f"{_assets_url_base()}/{digest}.{image['canonical_ext']}",
            "preview_url": "",
            "text_excerpt": "",
            "image": {k: image[k] for k in ("format", "width", "height", "pixels", "mode", "frames")},
            "created_at": now,
            "updated_at": now,
            "dispatch_provenance": {
                "state": "governed", "dispatch_token": dispatch_ctx["dispatch_token"],
                "run_id": run_id, "task_id": dispatch_ctx["task_id"],
            },
            "admission": {
                **intent,
                "operation_fingerprint": fingerprint,
                "scan": scan,
                "storage_deduplicated": deduplicated,
                "admitted_at": now,
            },
        }
        updated = copy.deepcopy(current)
        updated.setdefault("assets", []).append(record)
        updated["updated_at"] = now
        if store.compare_and_swap_research_project(current, updated):
            break
        record = None
    if record is None:
        raise IntegrityError(
            "REMOTE_ASSET_CONTENTION", "project changed repeatedly; retry the same operation_id",
        )
    emit_lifecycle_event(  # noqa: F821
        "asset.attached",
        {"project_id": project["id"], "asset_id": record["id"],
         "kind": "screenshot", "filename": filename, "admission": REMOTE_SCREENSHOT_SCHEMA},
        store,
    )
    dispatch = bind_dispatch_output(  # noqa: F821
        dispatch_ctx, {"kind": "asset", "id": record["id"]},
        "admitted scanned remote screenshot", store, complete=False,
    )
    return {**record, "idempotent_replay": replay, "dispatch": dispatch}
