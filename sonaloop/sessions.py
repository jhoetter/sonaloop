"""Signed-session contract shared by sonaloop-cloud and sonaloop-research.

The ``sonaloop_session`` cookie is minted by sonaloop-cloud on app.sonaloop.com and
verified across ``*.sonaloop.com`` (the cookie domain). Both products depend on this
core package, so the HMAC-SHA256 scheme lives here exactly once instead of being copied
between them (it used to be duplicated byte-for-byte into sonaloop-research/auth.py,
with a "if the cloud scheme ever changes, this copy must change with it" caveat — the
caveat is gone now that there is a single implementation)::

    b64url(json({**payload, "exp": ...})) + "." + b64url(hmac_sha256(body, SECRET))

``SECRET`` is the ``SONALOOP_CLOUD_SECRET`` env var. Stdlib only — research can import
this without taking a dependency on the cloud package. Auth is OFF when the secret is
unset (local single-user mode); a malformed/expired/forged token verifies to ``None``,
which callers treat as an anonymous request, never an error.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

#: Default cookie lifetime cloud mints sessions with (12h). Callers may override.
DEFAULT_SESSION_TTL_S = 12 * 3600


def _secret() -> bytes:
    return (os.getenv("SONALOOP_CLOUD_SECRET") or "").encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_session(payload: dict[str, Any], ttl_s: int = DEFAULT_SESSION_TTL_S) -> str:
    """Sign ``payload`` (plus an ``exp`` ttl_s seconds out) into a session token."""
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl_s}).encode("utf-8"))
    sig = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_session(token: str) -> dict[str, Any] | None:
    """The payload if the signature holds and it hasn't expired — else ``None``.

    Constant-time HMAC comparison, then the ``exp`` check; any malformed token is just
    an anonymous request, never an error.
    """
    try:
        body, sig = (token or "").split(".", 1)
        expect = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except Exception:  # noqa: BLE001 — a malformed cookie is just an anonymous request
        return None


__all__ = ["DEFAULT_SESSION_TTL_S", "sign_session", "verify_session"]
