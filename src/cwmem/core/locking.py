from __future__ import annotations

import mmap
import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path

import orjson
from pydantic import ValidationError

try:
    import portalocker
except ModuleNotFoundError:  # pragma: no cover - fallback for unsynced environments
    portalocker = None

from cwmem.core.models import CommandError, LockInfo
from cwmem.core.store import _utc_now
from cwmem.output.envelope import AppError, current_request_id


def lock_path(root: Path) -> Path:
    return root / ".cwmem" / "memory.sqlite.lock"


def metadata_path(root: Path) -> Path:
    return root / ".cwmem" / "memory.sqlite.lock.json"


def read_lock_info(root: Path) -> LockInfo | None:
    for path in (metadata_path(root), lock_path(root)):
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            if path == lock_path(root):
                raw = _read_locked_file_text(path)
            else:
                continue
        info = _parse_lock_payload(raw)
        if info is not None:
            return info
    return None


@contextmanager
def acquire_lock(
    root: Path,
    *,
    command: str,
    wait_seconds: float = 0.0,
    request_id: str | None = None,
):
    if wait_seconds < 0:
        raise AppError.from_command_error(
            CommandError(
                code="ERR_VALIDATION_INPUT",
                message="`--wait-lock` must be zero or a positive number of seconds.",
                retryable=False,
                suggested_action="Retry with `--wait-lock 0` or a larger positive value.",
                details={"wait_lock": wait_seconds},
            )
        )

    path = lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + wait_seconds
    resolved_request_id = request_id or current_request_id() or "req_manual"

    while True:
        try:
            handle = path.open("a+", encoding="utf-8")
        except PermissionError:
            if time.monotonic() >= deadline:
                _raise_lock_held(root)
            time.sleep(0.1)
            continue
        try:
            _lock_handle(handle)
        except (_lock_exception_type(), OSError):
            owner = _read_lock_info_from_handle(handle)
            handle.close()
            if owner is None:
                owner = read_lock_info(root)
            if time.monotonic() >= deadline:
                _raise_lock_held(root, owner=owner)
            time.sleep(0.1)
            continue

        try:
            info = LockInfo(
                pid=os.getpid(),
                hostname=socket.gethostname(),
                acquired_at=_utc_now(),
                command=command,
                request_id=resolved_request_id,
            )
            _write_lock_info(handle, info)
            metadata_path(root).write_text(
                orjson.dumps(info.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS).decode(),
                encoding="utf-8",
            )
            yield info
        finally:
            try:
                handle.seek(0)
                handle.truncate(0)
                handle.flush()
                os.fsync(handle.fileno())
            except OSError:
                pass
            metadata_path(root).unlink(missing_ok=True)
            _unlock_handle(handle)
            handle.close()
        return


def _write_lock_info(handle, info: LockInfo) -> None:
    handle.seek(0)
    handle.truncate(0)
    handle.write(orjson.dumps(info.model_dump(mode="json"), option=orjson.OPT_SORT_KEYS).decode())
    handle.flush()
    os.fsync(handle.fileno())


def _read_lock_info_from_handle(handle) -> LockInfo | None:
    try:
        handle.seek(0)
        raw = handle.read().strip()
    except OSError:
        return None
    return _parse_lock_payload(raw)


def _raise_lock_held(root: Path, *, owner: LockInfo | None = None) -> None:
    resolved_owner = owner or _read_lock_info_with_retry(root)
    owner_details = resolved_owner.model_dump(mode="json") if resolved_owner is not None else {}
    raise AppError.from_command_error(
        CommandError(
            code="ERR_LOCK_HELD",
            message="A write lock is already held by another process.",
            retryable=True,
            suggested_action=(
                "Wait for the active writer to finish, or retry with a larger "
                "`--wait-lock` value."
            ),
            details={
                "lock_path": lock_path(root).as_posix(),
                **owner_details,
                "owner": owner_details,
            },
        )
    )


def _read_lock_info_with_retry(
    root: Path, *, attempts: int = 5, delay: float = 0.02
) -> LockInfo | None:
    for _ in range(attempts):
        info = read_lock_info(root)
        if info is not None:
            return info
        time.sleep(delay)
    return None


def _lock_handle(handle) -> None:
    if portalocker is not None:
        portalocker.lock(handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
        return
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_handle(handle) -> None:
    if portalocker is not None:
        portalocker.unlock(handle)
        return
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _lock_exception_type():
    if portalocker is not None:
        return portalocker.exceptions.LockException
    if os.name == "nt":
        return OSError
    return BlockingIOError


def _parse_lock_payload(raw: str) -> LockInfo | None:
    if not raw:
        return None
    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return LockInfo.model_validate(payload)
    except ValidationError:
        return None


def _read_locked_file_text(path: Path) -> str:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        try:
            with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as handle:
                return handle.read().decode("utf-8").strip()
        except ValueError:
            return ""
    finally:
        os.close(fd)
