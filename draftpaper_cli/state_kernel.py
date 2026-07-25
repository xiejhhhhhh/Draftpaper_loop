"""Atomic, locked primitives for Draftpaper-loop authoritative state."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class StateKernelError(RuntimeError):
    """Raised when authoritative state cannot be read or committed safely."""


_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}


def _thread_lock_for(lock_path: Path) -> threading.RLock:
    key = str(lock_path)
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _lock_windows_byte(handle, *, timeout_seconds: float = 60.0) -> None:
    """Acquire a Windows byte lock without surfacing transient EDEADLOCK.

    ``msvcrt.LK_LOCK`` can raise ``EDEADLOCK`` when two threads in one
    process contend for the same byte.  The in-process lock serializes those
    threads, while the non-blocking retry loop continues to coordinate with
    other processes.
    """
    import errno
    import msvcrt

    locking = getattr(msvcrt, "locking")
    nonblocking_lock = int(getattr(msvcrt, "LK_NBLCK"))
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            locking(handle.fileno(), nonblocking_lock, 1)
            return
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EDEADLK} or time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


@contextmanager
def file_lock(target: str | Path) -> Iterator[None]:
    path = Path(target)
    lock_dir = Path(tempfile.gettempdir()) / "draftpaper-state-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / (hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24] + ".lock")
    with _thread_lock_for(lock_path):
        with lock_path.open("a+b") as handle:
            handle.seek(0)
            if handle.tell() == 0 and lock_path.stat().st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                _lock_windows_byte(handle)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(target):
        short_id = hashlib.sha256(target.name.encode("utf-8")).hexdigest()[:10]
        descriptor, temp_name = tempfile.mkstemp(prefix=f".dpl-{short_id}-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def atomic_write_bytes(path: str | Path, content: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(target):
        short_id = hashlib.sha256(target.name.encode("utf-8")).hexdigest()[:10]
        descriptor, temp_name = tempfile.mkstemp(prefix=f".dpl-{short_id}-", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """Atomically serialize any JSON value.

    Object-shape validation belongs to schema-aware readers such as
    ``read_json_object``.  The write primitive must also support legitimate
    top-level arrays such as ``references/literature_items.json``.
    """
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_jsonl_locked(path: str | Path, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise StateKernelError("JSONL event must be an object.")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with file_lock(target):
        with target.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())


def read_json_object(path: str | Path, *, required_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        raise StateKernelError(f"Cannot read JSON object {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StateKernelError(f"JSON artifact must contain an object: {target}")
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise StateKernelError(f"JSON artifact {target} is missing required keys: {', '.join(missing)}")
    return payload
