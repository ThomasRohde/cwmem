from __future__ import annotations

# ruff: noqa: B008
from pathlib import Path

import typer
from pydantic import ValidationError

from cwmem.core.graph import graph_show
from cwmem.core.models import CommandError, RelatedQuery
from cwmem.output.envelope import AppError, run_cli_command


def graph_command(  # noqa: B008
    resource_id: str = typer.Argument(...),
    relation_type: str | None = typer.Option(None, "--relation", "--relation-type"),
    depth: int = typer.Option(1, "--depth"),
    limit: int = typer.Option(50, "--limit"),
    include_provenance: bool = typer.Option(False, "--include-provenance"),
    cwd: Path | None = typer.Option(None, "--cwd"),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, object]:
        try:
            query = RelatedQuery.model_validate(
                {
                    "resource_id": resource_id,
                    "relation_type": relation_type,
                    "depth": depth,
                    "limit": limit,
                    "include_provenance": include_provenance,
                }
            )
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
        neighborhood = graph_show(root, query)
        return {
            "resource_id": resource_id,
            "graph": neighborhood,
            "node_count": len(neighborhood.nodes),
            "edge_count": len(neighborhood.edges),
        }

    raise SystemExit(run_cli_command("memory.graph.show", "graph", handler))


def register(app: typer.Typer) -> None:
    app.command("graph")(graph_command)
