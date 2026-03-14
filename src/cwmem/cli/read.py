from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path
from typing import Any, TypeVar

import typer
from pydantic import BaseModel, ValidationError

from cwmem.core.export import render_entry_jsonl, render_entry_markdown, render_event_jsonl
from cwmem.core.graph import related as related_resources
from cwmem.core.models import (
    CommandError,
    ListEntriesQuery,
    LogQuery,
    RelatedQuery,
    SearchQuery,
)
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
                details={"validation_errors": exc.errors(include_url=False, include_context=False)},
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
    expand_graph: bool = typer.Option(False, "--expand-graph"),
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
                "expand_graph": expand_graph,
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

    raise SystemExit(run_cli_command("memory.search", "resource", handler))


def related_command(  # noqa: B008
    resource_id: str = typer.Argument(...),
    relation_type: str | None = typer.Option(None, "--relation", "--relation-type"),
    depth: int = typer.Option(1, "--depth"),
    limit: int = typer.Option(50, "--limit"),
    include_provenance: bool = typer.Option(False, "--include-provenance"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        query = _build_query(
            RelatedQuery,
            {
                "resource_id": resource_id,
                "relation_type": relation_type,
                "depth": depth,
                "limit": limit,
                "include_provenance": include_provenance,
            },
        )
        hits = related_resources(root, query)
        return {"resource_id": resource_id, "hits": hits, "count": len(hits)}

    raise SystemExit(run_cli_command("memory.related", "resource", handler))


def register(app: typer.Typer) -> None:
    app.command("get")(get_command)
    app.command("list")(list_command)
    app.command("search")(search_command)
    app.command("related")(related_command)
    app.command("log")(log_command)
