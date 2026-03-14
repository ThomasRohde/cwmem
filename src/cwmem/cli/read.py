from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path
from typing import Any, TypeVar

import typer
from pydantic import BaseModel, ValidationError

from cwmem.core.export import render_entry_jsonl, render_entry_markdown, render_event_jsonl
from cwmem.core.models import CommandError, ListEntriesQuery, LogQuery, SearchQuery
from cwmem.core.store import get_entry, list_entries, list_events, search_entries
from cwmem.output.envelope import AppError, run_cli_command

ModelT = TypeVar("ModelT", bound=BaseModel)


def _build_query(model_type: type[ModelT], payload: dict[str, object]) -> ModelT:  # noqa: UP047
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise AppError.from_command_error(
            CommandError(
                code="ERR_VALIDATION_INPUT",
                message="Invalid command input.",
                retryable=False,
                suggested_action="Review the command arguments and retry.",
                details={"validation_errors": exc.errors(include_url=False)},
            )
        ) from exc


def get_command(  # noqa: B008
    public_id: str = typer.Argument(...),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, object]:
        entry = get_entry(root, public_id)
        return {
            "entry": entry,
            "artifacts": {
                "markdown": render_entry_markdown(entry),
                "jsonl": render_entry_jsonl(entry),
            },
        }

    raise SystemExit(run_cli_command("memory.get", "entry", handler))


def list_command(  # noqa: B008
    tag: str | None = typer.Option(None, "--tag", "--tags"),
    entry_type: str | None = typer.Option(None, "--type"),
    status: str | None = typer.Option(None, "--status"),
    author: str | None = typer.Option(None, "--author"),
    limit: int = typer.Option(50, "--limit"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, object]:
        query = _build_query(
            ListEntriesQuery,
            {
                "tag": tag,
                "type": entry_type,
                "status": status,
                "author": author,
                "limit": limit,
            },
        )
        entries = list_entries(root, query)
        return {"entries": entries, "count": len(entries)}

    raise SystemExit(run_cli_command("memory.list", "entry", handler))


def log_command(  # noqa: B008
    resource: str | None = typer.Option(None, "--resource"),
    event_type: str | None = typer.Option(None, "--event-type"),
    tag: str | None = typer.Option(None, "--tag", "--tags"),
    limit: int = typer.Option(50, "--limit"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        query = _build_query(
            LogQuery,
            {
                "resource": resource,
                "event_type": event_type,
                "tag": tag,
                "limit": limit,
            },
        )
        events = list_events(root, query)
        return {
            "events": events,
            "count": len(events),
            "artifacts": {"jsonl": "".join(render_event_jsonl(event) for event in events)},
        }

    raise SystemExit(run_cli_command("memory.log", "event", handler))


def search_command(  # noqa: B008
    q: str = typer.Argument(...),
    tag: str | None = typer.Option(None, "--tag"),
    search_type: str | None = typer.Option(None, "--type"),
    author: str | None = typer.Option(None, "--author"),
    date_from: str | None = typer.Option(None, "--from"),
    date_to: str | None = typer.Option(None, "--to"),
    lexical_only: bool = typer.Option(False, "--lexical-only"),
    semantic_only: bool = typer.Option(False, "--semantic-only"),
    limit: int = typer.Option(20, "--limit"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        query = _build_query(
            SearchQuery,
            {
                "q": q,
                "tag": tag,
                "type": search_type,
                "author": author,
                "date_from": date_from,
                "date_to": date_to,
                "lexical_only": lexical_only,
                "semantic_only": semantic_only,
                "limit": limit,
            },
        )
        try:
            hits = search_entries(root, query)
        except FileNotFoundError as exc:
            if semantic_only or (not lexical_only):
                raise AppError.from_command_error(
                    CommandError(
                        code="ERR_VALIDATION_SEMANTIC_UNAVAILABLE",
                        message=(
                            f"Semantic search is unavailable: {exc}. "
                            "Run `cwmem build` to rebuild the semantic index, "
                            "or use --lexical-only for FTS-only search."
                        ),
                        retryable=False,
                        suggested_action=(
                            "Ensure models/model2vec/manifest.json and the vendored model "
                            "are present, then run `cwmem build`."
                        ),
                        details={"missing_path": str(exc), "flag": "--semantic-only"},
                    )
                ) from exc
            raise
        return {"hits": hits, "count": len(hits), "query": q}

    raise SystemExit(run_cli_command("memory.search", "entry", handler))


def _make_placeholder(command_id: str, human_name: str):
    from cwmem.cli.setup import placeholder_command

    def command(ctx: typer.Context) -> None:
        _ = ctx.args
        raise SystemExit(
            run_cli_command(
                command_id,
                "repository",
                lambda: placeholder_command(command_id, human_name),
            )
        )

    return command


PLACEHOLDER_CONTEXT = {"allow_extra_args": True, "ignore_unknown_options": True}


def register(app: typer.Typer) -> None:
    app.command("get")(get_command)
    app.command("list")(list_command)
    app.command("search")(search_command)
    app.command("related", context_settings=PLACEHOLDER_CONTEXT)(
        _make_placeholder("memory.related", "related")
    )
    app.command("log")(log_command)
