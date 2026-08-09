"""Cross-process serialization for project lifecycle and run-journal ownership changes."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Iterator

from .config import request_tenant_scope


_REGISTRY_GUARD = Lock()
_LOCAL_LOCKS: dict[str, RLock] = {}


def _lock_identity(store: Any, project_id: str) -> str:
    dialect = getattr(store.backend, "dialect", "sqlite")
    if dialect == "postgres" and getattr(store.backend, "tenant", False):
        scope = request_tenant_scope()
        workspace_id = str((scope or ((), ""))[1] or "")
        if not workspace_id:
            raise RuntimeError("project lifecycle ownership requires an active workspace")
    else:
        # SQLite and non-tenant Postgres share one physical keyspace; request context must
        # never split the lock protecting the same row into independent identities.
        workspace_id = "global"
    path = str(Path(store.path).resolve()) if getattr(store, "path", None) else "postgres"
    return f"sonaloop-project-lifecycle:{path}:{workspace_id}:{project_id}"


def _lock_number(identity: str) -> int:
    return int.from_bytes(
        hashlib.sha256(identity.encode("utf-8")).digest()[:8], "big", signed=True,
    )


def _sqlite_lock_path(store: Any, identity: str) -> Path:
    """Return a stable, non-user-controlled file used for cross-process locking."""
    database = Path(store.path).resolve()
    lock_dir = database.parent / f".{database.name}.project-locks"
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return lock_dir / (hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".lock")


def _acquire_file_lock(path: Path) -> Any:
    """Acquire one blocking OS file lock and return its open file handle."""
    handle = path.open("a+b")
    try:
        if os.name == "nt":  # pragma: no cover - production and CI are POSIX
            import msvcrt
            if path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle
    except BaseException:
        handle.close()
        raise


def _release_file_lock(handle: Any) -> None:
    try:
        if os.name == "nt":  # pragma: no cover - production and CI are POSIX
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _release_pg_locks(store: Any, lock_ids: list[int]) -> None:
    if not lock_ids:
        return

    def unlock() -> None:
        for lock_id in reversed(lock_ids):
            store.conn.execute("SELECT pg_advisory_unlock(?)", (lock_id,)).fetchone()

    try:
        unlock()
    except Exception:
        store.conn.rollback()
        unlock()
    store.conn.commit()


@contextmanager
def project_lifecycle_locks(store: Any, project_ids: list[str]) -> Iterator[None]:
    """Serialize run writes and start/delete/archive/supersede decisions for project ids.

    Postgres uses session advisory locks so service methods may commit their own
    replay-safe writes without releasing the lifecycle guard. SQLite combines re-entrant
    in-process locks with OS file locks so separate CLI/MCP processes share the contract.
    Identities are sorted before acquisition to prevent two-project lineage deadlocks.
    """
    identities = sorted({_lock_identity(store, str(pid)) for pid in project_ids if str(pid)})
    if getattr(store.backend, "dialect", "sqlite") == "postgres":
        acquired: list[int] = []
        try:
            for identity in identities:
                lock_id = _lock_number(identity)
                store.conn.execute("SELECT pg_advisory_lock(?)", (lock_id,)).fetchone()
                acquired.append(lock_id)
            yield
        except BaseException:
            # Do not let the unlock helper's final COMMIT publish a partially
            # written statement from the failed lifecycle operation.
            try:
                store.conn.rollback()
            finally:
                _release_pg_locks(store, acquired)
            raise
        else:
            _release_pg_locks(store, acquired)
        return

    locks: list[RLock] = []
    with _REGISTRY_GUARD:
        for identity in identities:
            locks.append(_LOCAL_LOCKS.setdefault(identity, RLock()))
    for lock in locks:
        lock.acquire()
    file_locks: list[Any] = []
    try:
        # SQLite serializes individual write transactions, while these service calls may
        # commit several times. A stable OS lock protects the full lifecycle decision across
        # separate CLI/MCP processes; the RLock above also covers threads in this process.
        for identity in identities:
            file_locks.append(_acquire_file_lock(_sqlite_lock_path(store, identity)))
        yield
    finally:
        for handle in reversed(file_locks):
            _release_file_lock(handle)
        for lock in reversed(locks):
            lock.release()
