from __future__ import annotations

import contextvars
import socket
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from cwmem.core.models import CommandError, CommandWarning, Envelope, Metrics, Target
from cwmem.output.json import write_json

EXIT_CODES = {
    "success": 0,
    "validation": 10,
    "auth": 20,
    "conflict": 40,
    "io": 50,
    "internal": 90,
}

_CURRENT_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cwmem_current_request_id", default=None
)
_CURRENT_COMMAND_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cwmem_current_command_id", default=None
)


class AppError(Exception):
    def __init__(self, error: CommandError, exit_code: int) -> None:
        super().__init__(error.message)
        self.error = error
        self.exit_code = exit_code

    @classmethod
    def from_command_error(cls, error: CommandError) -> AppError:
        return cls(error=error, exit_code=exit_code_for_error(error.code))


def request_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"req_{timestamp}_{uuid4().hex[:8]}"


def current_request_id() -> str | None:
    return _CURRENT_REQUEST_ID.get()


def current_command_id() -> str | None:
    return _CURRENT_COMMAND_ID.get()


def exit_code_for_error(code: str) -> int:
    if code.startswith("ERR_VALIDATION_") or code == "ERR_NOT_IMPLEMENTED":
        return EXIT_CODES["validation"]
    if code.startswith("ERR_AUTH_"):
        return EXIT_CODES["auth"]
    if code.startswith("ERR_CONFLICT_") or code == "ERR_LOCK_HELD":
        return EXIT_CODES["conflict"]
    if code.startswith("ERR_IO_"):
        return EXIT_CODES["io"]
    return EXIT_CODES["internal"]


def build_envelope(
    *,
    command: str,
    target_resource: str,
    request_token: str,
    ok: bool,
    result: Any = None,
    warnings: list[CommandWarning] | None = None,
    errors: list[CommandError] | None = None,
    duration_ms: int = 0,
) -> Envelope:
    return Envelope(
        schema_version="1.0",
        request_id=request_token,
        ok=ok,
        command=command,
        target=Target(resource=target_resource),
        result=result,
        warnings=warnings or [],
        errors=errors or [],
        metrics=Metrics(duration_ms=duration_ms),
    )


def not_implemented_error(command_id: str, human_name: str) -> CommandError:
    return CommandError(
        code="ERR_NOT_IMPLEMENTED",
        message=f"The `{human_name}` command is planned but not implemented yet.",
        retryable=False,
        suggested_action="Use `cwmem guide` to inspect the available implemented command surface.",
        details={"command": command_id},
    )


def validation_error(message: str, *, details: dict[str, Any] | None = None) -> AppError:
    error = CommandError(
        code="ERR_VALIDATION_INPUT",
        message=message,
        retryable=False,
        suggested_action="Review the command usage and try again, or inspect `cwmem guide`.",
        details=details or {},
    )
    return AppError.from_command_error(error)


def conflict_error(message: str, *, details: dict[str, Any] | None = None) -> AppError:
    error = CommandError(
        code="ERR_CONFLICT_STATE",
        message=message,
        retryable=False,
        suggested_action="Resolve the conflicting path or state, then retry the command.",
        details=details or {},
    )
    return AppError.from_command_error(error)


def io_error(message: str, *, details: dict[str, Any] | None = None) -> AppError:
    error = CommandError(
        code="ERR_IO_WRITE_FAILED",
        message=message,
        retryable=True,
        suggested_action="Check filesystem permissions and retry the command.",
        details=details or {},
    )
    return AppError.from_command_error(error)


def internal_error(exc: Exception, *, command: str) -> CommandError:
    return CommandError(
        code="ERR_INTERNAL_UNHANDLED",
        message="An unexpected internal error occurred.",
        retryable=False,
        suggested_action="Review stderr or logs, then retry once the underlying issue is fixed.",
        details={
            "command": command,
            "exception_type": type(exc).__name__,
            "hostname": socket.gethostname(),
        },
    )


def run_cli_command(command: str, target_resource: str, handler: Callable[[], Any]) -> int:
    started = time.perf_counter()
    token = request_id()
    request_context = _CURRENT_REQUEST_ID.set(token)
    command_context = _CURRENT_COMMAND_ID.set(command)

    try:
        result = handler()
        envelope = build_envelope(
            command=command,
            target_resource=target_resource,
            request_token=token,
            ok=True,
            result=result,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        write_json(envelope)
        return EXIT_CODES["success"]
    except AppError as exc:
        envelope = build_envelope(
            command=command,
            target_resource=target_resource,
            request_token=token,
            ok=False,
            result=None,
            errors=[exc.error],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        write_json(envelope)
        return exc.exit_code
    except OSError as exc:
        app_error = io_error(str(exc), details={"command": command})
        envelope = build_envelope(
            command=command,
            target_resource=target_resource,
            request_token=token,
            ok=False,
            result=None,
            errors=[app_error.error],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        write_json(envelope)
        return app_error.exit_code
    except Exception as exc:
        error = internal_error(exc, command=command)
        envelope = build_envelope(
            command=command,
            target_resource=target_resource,
            request_token=token,
            ok=False,
            result=None,
            errors=[error],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        write_json(envelope)
        return EXIT_CODES["internal"]
    finally:
        _CURRENT_COMMAND_ID.reset(command_context)
        _CURRENT_REQUEST_ID.reset(request_context)


def emit_internal_failure(exc: Exception, *, command: str) -> None:
    envelope = build_envelope(
        command=command,
        target_resource="repository",
        request_token=request_id(),
        ok=False,
        result=None,
        errors=[internal_error(exc, command=command)],
        duration_ms=0,
    )
    write_json(envelope)

