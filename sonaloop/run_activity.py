"""Time-based projections for resumable governed-run activity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def is_inactive_for(timestamp: str, hours: int) -> bool:
    """Return whether an ISO timestamp is older than the requested activity window."""
    try:
        value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - value > timedelta(hours=hours)
    except (TypeError, ValueError):
        return False


def activity_deadline(timestamp: str, hours: int) -> str:
    """Return the UTC ISO deadline for one activity timestamp, or empty if invalid."""
    try:
        value = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (value + timedelta(hours=hours)).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return ""
