"""Least-privilege projections of immutable server-side creation attribution.

Creator identity and connector origin are separate claims.  The former comes from
the authenticated request actor; the latter is an optional, server-observed MCP
client snapshot captured by Cloud at the first front-door call.  In particular,
``provider_declared`` is model-authored trace metadata and is never promoted to a
public origin claim here.
"""
from __future__ import annotations

from typing import Any


_CLIENT_FAMILY_LABELS = {
    # The telemetry family deliberately groups generic Mistral MCP clients and
    # Le Chat.  Keep the public label at that truthful family level instead of
    # overclaiming the specific Le Chat product from a broad name match.
    "mistral": "Mistral",
    "claude": "Claude",
    "anthropic": "Anthropic",
    "chatgpt": "ChatGPT",
    "codex": "Codex",
    "openai": "OpenAI",
    "cursor": "Cursor",
    "windsurf": "Windsurf",
    "vscode": "Visual Studio Code",
    "continue": "Continue",
}
_CLIENT_EVIDENCE_SOURCES = frozenset({"initialize_client_info_binding"})


def public_creator_projection(value: Any) -> dict[str, str] | None:
    """Expose only a revalidated display label on public project surfaces."""
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    if not isinstance(label, str):
        return None
    label = label.strip()
    if not label or len(label) > 160 or not label.isprintable():
        return None
    return {"label": label}


def public_client_origin_projection(value: Any) -> dict[str, str] | None:
    """Project one verified, closed connector snapshot for member-facing UI.

    The label always comes from this closed server vocabulary, never from stored
    text. Unknown/ambiguous clients, malformed snapshots and caller-declared
    provider/model fields therefore fail closed to no attribution.
    """
    if not isinstance(value, dict):
        return None
    if value.get("schema") != "sonaloop.ingress_client_snapshot.v1":
        return None
    family = str(value.get("family") or "")
    evidence_source = str(value.get("evidence_source") or "")
    label = _CLIENT_FAMILY_LABELS.get(family)
    if not label or evidence_source not in _CLIENT_EVIDENCE_SOURCES:
        return None
    return {"family": family, "label": label}


def public_project_client_origin(project: Any) -> dict[str, str] | None:
    """Read the immutable first-ingress connector snapshot from a project.

    Keeping the private snapshot under ``research_job_ingress`` prevents ordinary
    structural project edits from presenting a client family.  Public callers get
    only the closed family and product label.
    """
    if not isinstance(project, dict):
        return None
    ingress = project.get("research_job_ingress")
    if not isinstance(ingress, dict):
        return None
    return public_client_origin_projection(ingress.get("client_at_creation"))
