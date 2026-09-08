"""Cross-process serialization for stateful DaVinci Resolve operations."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Iterator

from ..errors import APICallFailed

try:  # pragma: no cover - platform-selected import
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:  # pragma: no cover - platform-selected import
    import msvcrt
except ImportError:  # pragma: no cover - POSIX
    msvcrt = None


_PROCESS_LOCK = threading.Lock()
_DEFAULT_TIMEOUT_SECONDS = 120.0
_POLL_SECONDS = 0.05


def _default_lock_path() -> Path:
    user_scope = str(os.getuid()) if hasattr(os, "getuid") else "user"
    return Path(tempfile.gettempdir()) / f"cutagent-davinci-resolve-state-{user_scope}.lock"


def _open_lock_file(path: Path) -> Any:
    flags = os.O_CREAT | os.O_RDWR
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise APICallFailed(
            "CutAgent CLI could not open the DaVinci Resolve operation lock.",
            details={"reason": "resolve_state_lock_open_failed", "error": str(exc)},
            recoverability="retryable",
        ) from exc
    return os.fdopen(descriptor, "r+")


def _try_lock(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    if msvcrt is None:  # pragma: no cover - supported release platforms provide one
        raise APICallFailed(
            "This platform cannot safely serialize DaVinci Resolve operations.",
            details={"reason": "resolve_state_lock_backend_unavailable"},
            recoverability="not_applicable",
        )
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write("\0")
        handle.flush()
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)


def _unlock(handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is not None:  # pragma: no branch - paired with _try_lock
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


@contextmanager
def exclusive_resolve_state_operation(
    *,
    operation: str,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    lock_path: Path | None = None,
) -> Iterator[None]:
    """Serialize stateful operations across threads and CutAgent CLI processes."""

    timeout = max(0.0, float(timeout_seconds))
    started = time.monotonic()
    if not _PROCESS_LOCK.acquire(timeout=timeout):
        raise APICallFailed(
            "Another CutAgent CLI operation is still controlling DaVinci Resolve.",
            details={"reason": "resolve_state_lock_timeout", "operation": operation},
            recoverability="retryable",
        )

    handle = None
    try:
        path = lock_path or _default_lock_path()
        handle = _open_lock_file(path)
        while True:
            try:
                _try_lock(handle)
                break
            except BlockingIOError:
                pass
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
            if time.monotonic() - started >= timeout:
                raise APICallFailed(
                    "Another CutAgent CLI operation is still controlling DaVinci Resolve.",
                    details={"reason": "resolve_state_lock_timeout", "operation": operation},
                    recoverability="retryable",
                )
            time.sleep(_POLL_SECONDS)
        try:
            yield
        finally:
            _unlock(handle)
    finally:
        if handle is not None:
            handle.close()
        _PROCESS_LOCK.release()
