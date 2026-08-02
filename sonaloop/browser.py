"""Playwright harness (spec/methodology-engine-and-prototyping.md, Pillar B §7).

A persona-agent drives the REAL running app and reacts to REAL observed state. Each
session owns a dedicated worker thread that holds the sync Playwright objects (so it works
regardless of the caller's async context). Refs are valid only for the latest snapshot of a
session; acting on a stale ref raises STALE_REF. Degrades gracefully when Playwright/chromium
is unavailable.

Live walkthroughs (ticket live-saas-walkthrough) ride the SAME harness: an optional
WalkPolicy (walk_policy.py) is enforced in-session (origin allowlist, action denylist, hard
caps, credential redaction) — violations come back as structured refusals in the act() result
and land in the session log, never as host crashes. Every snapshot (any session kind) also
captures a per-step screenshot under data/sessions/<session_id>/step-<n>.png, fail-soft.
"""
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Any

from . import config
from . import walk_policy as _wp
from .config import max_browser_sessions, sessions_dir

ACTIONABLE = {"button", "link", "textbox", "checkbox", "combobox", "menuitem",
              "tab", "radio", "searchbox", "switch", "option", "slider", "spinbutton"}


class HarnessError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


class _Session(threading.Thread):
    """Owns one headless page in its own thread; commands arrive on a queue."""

    def __init__(self, session_id: str, url: str, prototype_id: str | None, persona_id: str | None,
                 policy: dict[str, Any] | None = None, credentials: dict[str, str] | None = None,
                 *, runtime_namespace: str = "", screenshots_root: Path | None = None):
        super().__init__(daemon=True)
        self.session_id = session_id
        self.url = url
        self.prototype_id = prototype_id
        self.persona_id = persona_id
        self.policy = policy
        # ContextVars do not flow into this dedicated worker thread. Capture both
        # the access namespace and file root while still inside the request.
        self.runtime_namespace = runtime_namespace
        self.screenshots_root = screenshots_root or sessions_dir()
        self.credentials = credentials or {}
        self._secrets = [v for v in self.credentials.values() if v]   # redacted from ALL retained output
        self.refmap: dict[str, dict[str, str]] = {}
        self.log: list[dict[str, Any]] = []
        self._cmd: queue.Queue = queue.Queue()
        self._ready: queue.Queue = queue.Queue()
        self._pw = None
        self._browser = None
        self._page = None
        self._shot_n = 0                       # monotonically increasing snapshot counter
        self._n_actions = 0
        self._opened_at = time.monotonic()
        self._last_ok_url = url                # last on-allowlist URL (origin-block recovery target)
        self._capped = False                   # a hard cap auto-closed the session

    # ----- thread body -----
    def run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
            self._page = self._browser.new_page()
            self._page.goto(self.url, wait_until="load", timeout=20000)
            self._page.wait_for_timeout(150)
            if self.policy and self._off_origin(self._page.url):
                # A redirect at open already left the allowlist: refuse the session outright —
                # there is no on-policy state to fall back to. The block itself is evidence,
                # so the one-entry log is retained even though the session never registers.
                self.log.append({"kind": "policy_block", "rule": "origin",
                                 "detail": f"open navigation landed off-origin: "
                                           f"{_wp.redact(self._page.url, self._secrets)}"})
                _retain_log(self.session_id, self.log, self.runtime_namespace)
                self._ready.put(("err", "POLICY_BLOCKED: the opening navigation redirected outside "
                                        "policy.allowed_origins — session refused"))
                self._teardown()
                return
            snap = self._snapshot()
            self._ready.put(("ok", snap))
        except Exception as e:  # launch/navigation failure
            self._ready.put(("err", f"{type(e).__name__}: {e}"))
            self._teardown()
            return
        while True:
            cmd, payload, reply = self._cmd.get()
            if cmd == "close":
                self._teardown()
                reply.put(("ok", {"closed": True}))
                return
            try:
                if self._capped:
                    # the cap auto-closed the browser; read/act after that is a clear, stable error
                    raise HarnessError("CAP_REACHED",
                                       "the WalkPolicy cap auto-closed this session — record what you "
                                       "observed; open a new walkthrough only if more steps are genuinely needed")
                if cmd == "read":
                    if self.policy and self._off_origin(self._current_url()):
                        # a delayed/JS redirect can land off-origin BETWEEN actions; the read-time
                        # guard keeps containment airtight no matter how the page got there
                        reply.put(("ok", self._block_origin()))
                    else:
                        reply.put(("ok", self._snapshot()))
                elif cmd == "act":
                    reply.put(("ok", self._act(payload)))
                else:
                    reply.put(("err", f"unknown command {cmd}"))
            except HarnessError as he:
                reply.put(("err", _wp.redact(f"{he.code}:{he.message}", self._secrets)))
            except Exception as e:
                reply.put(("err", _wp.redact(f"{type(e).__name__}: {e}", self._secrets)))

    def _teardown(self) -> None:
        for obj, meth in ((self._browser, "close"), (self._pw, "stop")):
            try:
                if obj:
                    getattr(obj, meth)()
            except Exception:
                pass

    # ----- in-thread operations -----
    _SNAP_JS = """() => {
      const out = [];
      const roleFor = (el) => {
        const explicit = el.getAttribute('role'); if (explicit) return explicit;
        const tag = el.tagName.toLowerCase();
        if (tag === 'a') return 'link';
        if (tag === 'button') return 'button';
        if (tag === 'select') return 'combobox';
        if (tag === 'textarea') return 'textbox';
        if (tag === 'input') {
          const t = (el.getAttribute('type') || 'text').toLowerCase();
          if (t === 'checkbox') return 'checkbox';
          if (t === 'radio') return 'radio';
          if (t === 'range') return 'slider';        // ARIA role Playwright's get_by_role resolves
          if (t === 'number') return 'spinbutton';   // — 'textbox' made range/number un-drivable
          return 'textbox';
        }
        return tag;
      };
      const sel = 'button, a[href], input, select, textarea, [role=button], [role=link]';
      document.querySelectorAll(sel).forEach(el => {
        if (el.offsetParent === null && el.tagName.toLowerCase() !== 'option') return; // hidden
        const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || '').trim();
        out.push({ role: roleFor(el), name, value: ('value' in el ? el.value : null) });
      });
      return { url: location.href, title: document.title,
               text: (document.body ? document.body.innerText : '').slice(0, 4000), nodes: out };
    }"""

    def _snapshot(self) -> dict[str, Any]:
        data = self._page.evaluate(self._SNAP_JS)
        self.refmap = {}
        tree: list[dict[str, Any]] = []
        for n in data.get("nodes", []):
            role, name = n.get("role", ""), (n.get("name") or "").strip()
            node = {"role": role, "name": name}
            if n.get("value") is not None:
                node["value"] = n["value"]
            if role in ACTIONABLE and name:
                ref = f"e{len(self.refmap) + 1}"
                node["ref"] = ref
                self.refmap[ref] = {"role": role, "name": name}  # RAW names (locator targets; never retained)
            tree.append(node)
        if not self._off_origin(data.get("url") or ""):
            self._last_ok_url = data.get("url") or self._last_ok_url
        snap = {"url": data.get("url"), "title": data.get("title"), "tree": tree,
                "text": data.get("text", "")}
        # The redaction layer: exact credential values are replaced BEFORE anything is retained or
        # returned — the page may echo a filled secret (input values, "signed in as …" banners).
        snap = _wp.redact(snap, self._secrets)
        shot = self._screenshot()
        if shot:
            snap["screenshot"] = shot
        entry = {"kind": "snapshot", "url": snap["url"], "title": snap["title"],
                 "refs": list(self.refmap.keys()), "text": snap["text"]}
        if shot:
            entry["screenshot"] = shot
        self.log.append(entry)
        return snap

    def _screenshot(self) -> str | None:
        """Per-step screenshot for the replayable trace: data/sessions/<session_id>/step-<n>.png
        (monotonic counter), taken on EVERY snapshot — open, act and read alike, walkthroughs and
        prototype sessions alike (one harness). Returns the path relative to the sessions dir (the
        recorder/replay convention); fail-soft: a screenshot error never breaks the snapshot."""
        try:
            name = f"step-{self._shot_n}.png"
            shot_dir = self.screenshots_root / self.session_id
            shot_dir.mkdir(parents=True, exist_ok=True)
            self._page.screenshot(path=str(shot_dir / name))
            self._shot_n += 1
            return f"{self.session_id}/{name}"
        except Exception:
            return None

    # ----- WalkPolicy enforcement (walk_policy.py; docs/live-walkthrough-safety.md) -----
    def _current_url(self) -> str:
        """The page's REAL current URL. `page.url` can be stale between calls (the sync API only
        pumps protocol events during an active round-trip), so a delayed JS redirect that fired
        while the session was idle would be invisible to it — evaluate forces a round-trip."""
        try:
            return str(self._page.evaluate("() => location.href"))
        except Exception:
            return self._page.url

    def _off_origin(self, url: str) -> bool:
        """True when a URL is outside policy.allowed_origins. An unparseable/non-http(s) URL is
        off-origin by definition — deny by default."""
        if not self.policy:
            return False
        try:
            return _wp.origin_of(url) not in (self.policy.get("allowed_origins") or [])
        except ValueError:
            return True

    def _enforce_policy(self, a: dict[str, Any]) -> dict[str, Any] | None:
        """Hard caps + the action denylist, BEFORE the action runs. Returns the structured refusal
        (which is also logged — the block itself is evidence) for a violation, None when the action
        may proceed. Violations are RESULTS, never raises: the host loop must not crash."""
        elapsed = time.monotonic() - self._opened_at
        cap = ("max_actions" if self._n_actions >= int(self.policy.get("max_actions")
                                                       or _wp.DEFAULT_MAX_ACTIONS)
               else "max_duration_s" if elapsed > int(self.policy.get("max_duration_s")
                                                      or _wp.DEFAULT_MAX_DURATION_S)
               else None)
        if cap:
            detail = f"{cap} reached after {self._n_actions} actions / {int(elapsed)}s — the session auto-closed"
            self.log.append({"kind": "cap_reached", "cap": cap, "detail": detail})
            self._capped = True
            self._teardown()
            return {"cap_reached": {"cap": cap, "detail": detail}, "closed": True}
        self._n_actions += 1                       # blocked attempts count too — no free retries
        target_text = ""
        if a.get("type") in ("click", "select"):
            target_text = (self.refmap.get(a.get("ref") or "") or {}).get("name", "")
        elif a.get("type") == "key" and (a.get("key") or "Enter") == "Enter":
            target_text = self._submit_context_text()
        hit = _wp.match_denylist(target_text, self.policy.get("denylist") or {})
        if hit:
            detail = (f"refused {a.get('type')} on {target_text!r}: matches blocked category "
                      f"'{hit['category']}' (term '{hit['term']}')")
            entry = _wp.redact({"kind": "policy_block", "rule": "blocked_action", **hit,
                                "detail": detail}, self._secrets)
            self.log.append(entry)
            snap = self._snapshot()
            snap["policy_block"] = {k: entry[k] for k in ("rule", "category", "term", "detail")}
            return snap
        return None

    _SUBMIT_JS = """() => {
      const el = document.activeElement;
      if (!el) return '';
      const name = (el.getAttribute && (el.getAttribute('aria-label') || '')) || '';
      let submit = '';
      const form = el.form || (el.closest && el.closest('form'));
      if (form) {
        const b = form.querySelector('button[type=submit], input[type=submit], button:not([type])');
        if (b) submit = (b.getAttribute('aria-label') || b.textContent || b.value || '');
      }
      return (name + ' ' + submit).trim();
    }"""

    def _submit_context_text(self) -> str:
        """What pressing Enter would trigger: the focused element's accessible name plus its form's
        submit control text — the denylist target for the submit-Enter path. Fail-soft to ''."""
        try:
            return str(self._page.evaluate(self._SUBMIT_JS))
        except Exception:
            return ""

    def _block_origin(self) -> dict[str, Any]:
        """An action's navigation left the allowlist: log the block, navigate back to the last
        on-policy URL and return the structured refusal with the recovered snapshot."""
        landed = _wp.redact(self._page.url, self._secrets)
        detail = (f"navigation landed off-origin: {landed} is not within allowed_origins "
                  f"{self.policy.get('allowed_origins')} — navigated back")
        self.log.append({"kind": "policy_block", "rule": "origin", "detail": detail})
        try:
            self._page.goto(self._last_ok_url, wait_until="load", timeout=20000)
            self._page.wait_for_timeout(150)
        except Exception:
            pass                                   # the snapshot shows whatever state recovery reached
        snap = self._snapshot()
        snap["policy_block"] = {"rule": "origin", "detail": detail}
        return snap

    def _locator(self, ref: str):
        spec = self.refmap.get(ref)
        if not spec:
            raise HarnessError("STALE_REF", f"ref '{ref}' is not in the latest snapshot; re-read")
        return self._page.get_by_role(spec["role"], name=spec["name"]).first

    def _act(self, a: dict[str, Any]) -> dict[str, Any]:
        typ = a.get("type")
        if self.policy:
            refusal = self._enforce_policy(a)
            if refusal is not None:
                return refusal
        self.log.append({"kind": "action", "action": _wp.redact(a, self._secrets)})
        if typ == "click":
            self._locator(a["ref"]).click(timeout=5000)
        elif typ == "type":
            self._locator(a["ref"]).fill(a.get("text", ""), timeout=5000)
        elif typ == "fill_credential":
            # The dedicated credential act: the secret is filled in-worker from the values supplied
            # at open — it never transits the host loop, and the redaction layer covers every echo.
            field = a.get("field")
            if field not in self.credentials:
                raise HarnessError("BAD_ACTION",
                                   f"no credential for field {field!r} — credentials are supplied "
                                   "once, at open (walk_open(credentials={username, password}))")
            self._locator(a["ref"]).fill(self.credentials[field], timeout=5000)
        elif typ == "select":
            self._locator(a["ref"]).select_option(a.get("value"), timeout=5000)
        elif typ == "key":
            self._page.keyboard.press(a.get("key", "Enter"))
        elif typ == "scroll":
            self._page.mouse.wheel(0, int(a.get("ms", 400) or 400))
        elif typ == "wait":
            self._page.wait_for_timeout(min(3000, int(a.get("ms", 400) or 400)))
        else:
            raise HarnessError("BAD_ACTION", f"unknown action type {typ}")
        self._page.wait_for_timeout(150)
        if self.policy and self._off_origin(self._current_url()):
            return self._block_origin()            # link-click results and redirects included
        return self._snapshot()

    # ----- public (called from other threads) -----
    def start_and_wait(self, timeout: float = 30.0) -> dict[str, Any]:
        self.start()
        status, payload = self._ready.get(timeout=timeout)
        if status != "ok":
            msg = str(payload)
            if "Executable doesn't exist" in msg or "playwright install" in msg:
                # The playwright PACKAGE is installed but the chromium BINARY was never fetched —
                # the normal cold-start state. Same stable code as a missing package, plus the fix.
                raise HarnessError(
                    "PLAYWRIGHT_UNAVAILABLE",
                    "the headless chromium is not fetched yet — run `sonaloop setup` (or "
                    "`playwright install chromium`) once. Artifact walkthroughs (define_flow + "
                    "brief_flow_walkthrough) work without it.")
            raise HarnessError("OPEN_FAILED", msg)
        return payload

    def send(self, cmd: str, payload: Any = None, timeout: float = 30.0) -> Any:
        reply: queue.Queue = queue.Queue()
        self._cmd.put((cmd, payload, reply))
        status, out = reply.get(timeout=timeout)
        if status != "ok":
            code, _, msg = str(out).partition(":")
            raise HarnessError(code if code in {"STALE_REF", "BAD_ACTION", "CAP_REACHED"} else "ACT_FAILED",
                               str(out))
        return out


_SESSIONS: dict[str, _Session] = {}
# Logs retained PAST close() so a proband session still verifies its observed states after the browser
# is torn down (spec/exploration-depth-and-prototype-variety GAP-5). Without this, the clean
# drive→close→record order destroyed the groundedness evidence and every session recorded unverified.
_RETAINED_LOGS: dict[str, list[dict[str, Any]]] = {}
_MAX_RETAINED = 128


def _runtime_namespace() -> str:
    """Opaque in-process namespace for browser state.

    SQLite keeps the historical flat dictionary keys. Shared Postgres keys by
    the active workspace file partition; the unbound startup quarantine is a
    namespace too, never an alias for a real tenant.
    """
    return str(config.partition_dir().resolve()) if config.postgres_row_tenancy_enabled() else ""


def _session_key(session_id: str, namespace: str | None = None) -> str:
    ns = _runtime_namespace() if namespace is None else namespace
    return f"{ns}\0{session_id}" if ns else session_id


def _key_namespace(key: str) -> str:
    return key.partition("\0")[0] if "\0" in key else ""


def _retain_log(session_id: str, log: list[dict[str, Any]], namespace: str | None = None) -> None:
    ns = _runtime_namespace() if namespace is None else namespace
    key = _session_key(session_id, ns)
    _RETAINED_LOGS[key] = list(log)[-400:]
    same_namespace = [k for k in _RETAINED_LOGS if _key_namespace(k) == ns]
    while len(same_namespace) > _MAX_RETAINED:
        oldest = same_namespace.pop(0)
        _RETAINED_LOGS.pop(oldest, None)


def open_session(url: str, prototype_id: str | None = None, persona_id: str | None = None,
                 policy: dict[str, Any] | None = None,
                 credentials: dict[str, str] | None = None) -> dict[str, Any]:
    """Open one headless session. `policy` is an enforced WalkPolicy as produced by
    walk_policy.normalize_policy (walk_open is the public path); `credentials` values stay inside
    the worker (filled via {type:'fill_credential'}) and are redacted from all retained output —
    they are never logged, at open or later."""
    if not available():
        raise HarnessError("PLAYWRIGHT_UNAVAILABLE",
                           "Playwright is not installed. Run `make playwright` (pip install playwright && playwright install chromium).")
    namespace = _runtime_namespace()
    if len(_SESSIONS) >= max_browser_sessions():
        raise HarnessError("SESSION_CAP", f"too many live sessions (max {max_browser_sessions()}); close one first")
    from .services import stable_id
    sid = stable_id("psession", url, str(time.time()))
    sess = _Session(sid, url, prototype_id, persona_id, policy=policy, credentials=credentials,
                    runtime_namespace=namespace, screenshots_root=sessions_dir())
    snap = sess.start_and_wait()
    _SESSIONS[_session_key(sid, namespace)] = sess
    return {"session_id": sid, "snapshot": snap}


def _require(session_id: str) -> _Session:
    s = _SESSIONS.get(_session_key(session_id))
    if not s:
        raise HarnessError("SESSION_NOT_FOUND",
                           f"no live session '{session_id}' — browser sessions live inside ONE process; "
                           f"from the CLI use `proto-drive` (open→actions→read→close in a single run), "
                           f"or drive via the long-lived MCP server")
    return s


def act(session_id: str, action: dict[str, Any]) -> dict[str, Any]:
    return {"snapshot": _require(session_id).send("act", action)}


def read(session_id: str) -> dict[str, Any]:
    return {"snapshot": _require(session_id).send("read")}


def close(session_id: str) -> dict[str, Any]:
    s = _SESSIONS.pop(_session_key(session_id), None)
    if not s:
        return {"closed": False}
    _retain_log(session_id, s.log, s.runtime_namespace)  # keep observed states past close
    try:
        s.send("close", timeout=10)
    except Exception:
        pass
    return {"closed": True, "session_id": session_id}


def list_sessions() -> list[dict[str, Any]]:
    namespace = _runtime_namespace()
    return [{"session_id": s.session_id, "url": s.url, "prototype_id": s.prototype_id,
             "persona_id": s.persona_id, "steps": len(s.log)} for s in _SESSIONS.values()
            if s.runtime_namespace == namespace]


def session_log(session_id: str) -> list[dict[str, Any]] | None:
    key = _session_key(session_id)
    s = _SESSIONS.get(key)
    if s:
        return list(s.log)
    return list(_RETAINED_LOGS[key]) if key in _RETAINED_LOGS else None
