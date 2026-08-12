"""Provider-neutral, privacy-minimal product telemetry seam.

Core knows neither PostHog nor a hosted deployment. Product code emits small semantic
events here; installed extensions register a sink that may persist/export them. Without
an authenticated request actor and exact workspace scope, capture is a deliberate no-op.

Raw research content never belongs in telemetry properties. Entity identifiers have
dedicated fields so a hosting sink can pseudonymize them before durable persistence.
"""
from __future__ import annotations

import copy
import logging
import math
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from . import config

log = logging.getLogger("sonaloop.telemetry")

EVENT_SCHEMA = "sonaloop.product_event.v1"
_EVENT_RE = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_PROPERTY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_ENUM_VALUE_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,79}$")
_FORBIDDEN_PROPERTY_PARTS = frozenset({
    "content", "description", "email", "goal", "label", "name", "path",
    "prompt", "query", "text", "title", "url",
})
_MAX_PROPERTIES = 32
_MAX_STRING_CHARS = 120
_MAX_LIST_ITEMS = 20


@runtime_checkable
class ProductTelemetrySink(Protocol):
    """One replaceable destination for normalized internal product events."""

    def capture(self, event: Mapping[str, Any]) -> Any: ...


_SINKS: dict[str, ProductTelemetrySink | Callable[[Mapping[str, Any]], Any]] = {}
_SINK_LOCK = threading.RLock()


def register_product_telemetry_sink(
    name: str,
    sink: ProductTelemetrySink | Callable[[Mapping[str, Any]], Any],
) -> None:
    """Install or replace one named sink; repeated extension setup is idempotent."""
    key = str(name or "").strip().casefold()
    if not _EVENT_RE.fullmatch(key):
        raise ValueError("telemetry sink name must be lowercase snake_case")
    if not callable(sink) and not isinstance(sink, ProductTelemetrySink):
        raise TypeError("telemetry sink must be callable or implement capture(event)")
    with _SINK_LOCK:
        _SINKS[key] = sink


def unregister_product_telemetry_sink(name: str) -> None:
    """Remove one sink, primarily for extension shutdown and isolated tests."""
    with _SINK_LOCK:
        _SINKS.pop(str(name or "").strip().casefold(), None)


def product_telemetry_sink_names() -> list[str]:
    with _SINK_LOCK:
        return sorted(_SINKS)


def _scalar_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_STRING_CHARS:
            raise ValueError(f"telemetry string values are limited to {_MAX_STRING_CHARS} characters")
        normalized = value.strip().casefold()
        # Product properties are enums, counts and booleans — never prose. Open taxonomy
        # values degrade to ``unknown`` rather than leaking authored text or breaking a flow.
        return normalized if _ENUM_VALUE_RE.fullmatch(normalized) else "unknown"
    raise TypeError("telemetry values must be bounded scalar enums/counts/booleans")


def _properties(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise TypeError("telemetry properties must be a mapping")
    if len(values) > _MAX_PROPERTIES:
        raise ValueError(f"telemetry properties are limited to {_MAX_PROPERTIES} fields")
    out: dict[str, Any] = {}
    for raw_key, value in values.items():
        key = str(raw_key or "").strip().casefold()
        if not _PROPERTY_RE.fullmatch(key):
            raise ValueError("telemetry property keys must be lowercase snake_case")
        if set(key.split("_")) & _FORBIDDEN_PROPERTY_PARTS:
            raise ValueError(f"telemetry property {key!r} could carry authored/private content")
        if not isinstance(value, (list, tuple)):
            out[key] = _scalar_value(value)
            continue
        if len(value) <= _MAX_LIST_ITEMS:
            out[key] = [_scalar_value(item) for item in value]
            continue
        raise TypeError(f"telemetry property {key!r} must be a bounded scalar/list")
    return out


def _identifier(value: Any, field: str, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if not text and not required:
        return ""
    if not text or len(text) > 240 or not text.isprintable():
        raise ValueError(f"telemetry {field} must be a bounded printable identifier")
    return text


def capture_product_event(
    name: str,
    *,
    project_id: str = "",
    subject_kind: str = "",
    subject_id: str = "",
    properties: Mapping[str, Any] | None = None,
    idempotency_key: str = "",
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    """Emit one semantic event to every registered sink, fail-soft.

    Callers provide only event semantics and bounded structural metadata. The request
    actor/workspace are server-owned context, never caller arguments. A stable
    ``idempotency_key`` lets a durable sink collapse transport retries.
    """
    event_name = str(name or "").strip().casefold()
    if not _EVENT_RE.fullmatch(event_name):
        raise ValueError("telemetry event name must be lowercase snake_case")
    kind = str(subject_kind or "").strip().casefold()
    if bool(kind) != bool(subject_id):
        raise ValueError("telemetry subject_kind and subject_id must be supplied together")
    if kind and not _KIND_RE.fullmatch(kind):
        raise ValueError("telemetry subject kind must be lowercase snake_case")
    project = _identifier(project_id, "project_id")
    subject = _identifier(subject_id, "subject_id")
    operation = _identifier(idempotency_key, "idempotency_key")
    now = occurred_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("telemetry occurred_at must include a timezone")
    actor = config.current_request_actor()
    scope = config.request_tenant_scope()
    workspace_id = str(scope[1] if scope else "")
    if not actor or not workspace_id:
        return {"accepted": 0, "ignored": "unbound_request"}

    event = {
        "schema": EVENT_SCHEMA,
        "id": str(uuid.uuid4()),
        "name": event_name,
        "occurred_at": now.astimezone(timezone.utc).isoformat(),
        "workspace_id": workspace_id,
        "actor": {
            key: str(actor.get(key) or "")
            for key in ("kind", "id", "role", "channel") if actor.get(key)
        },
        "project_id": project,
        "subject": ({"kind": kind, "id": subject} if kind else None),
        "properties": _properties(properties),
        "idempotency_key": operation,
    }
    with _SINK_LOCK:
        sinks = list(_SINKS.items())
    failures: list[str] = []
    accepted = 0
    receipts: dict[str, Any] = {}
    for sink_name, sink in sinks:
        try:
            payload = copy.deepcopy(event)
            receipt = sink(payload) if callable(sink) else sink.capture(payload)
            if receipt is not None:
                receipts[sink_name] = receipt
            accepted += 1
        except Exception:
            failures.append(sink_name)
            log.exception("product telemetry sink %s failed; product flow continues", sink_name)
    return {
        "accepted": accepted,
        "failed_sinks": failures,
        "event_id": event["id"],
        "receipts": receipts,
    }
