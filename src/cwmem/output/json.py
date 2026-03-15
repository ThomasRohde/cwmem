from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import orjson
from pydantic import BaseModel


def _default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def to_json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    opts = orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE
    if pretty:
        opts |= orjson.OPT_INDENT_2
    return orjson.dumps(value, default=_default, option=opts)


def write_json(value: Any) -> None:
    pretty = sys.stdout.isatty()
    sys.stdout.buffer.write(to_json_bytes(value, pretty=pretty))
    sys.stdout.flush()

