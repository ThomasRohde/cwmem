from __future__ import annotations

# ruff: noqa: B008
import sys
from pathlib import Path
from typing import Any, TypeVar

import orjson
import typer
from pydantic import BaseModel, ValidationError

from cwmem.cli.setup import placeholder_command
from cwmem.core.export import render_entry_jsonl, render_entry_markdown, render_event_jsonl
from cwmem.core.models import (
    CommandError,
    CreateEntryInput,
    CreateEventInput,
    EntryRecord,
    EventRecord,
    TagMutationInput,
    UpdateEntryInput,
)
from cwmem.core.store import add_event, add_tags, create_entry, remove_tags, update_entry
from cwmem.output.envelope import AppError, run_cli_command

ModelT = TypeVar("ModelT", bound=BaseModel)


def _is_unset(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return len(value) == 0
    return False


def _should_read_stdin(*values: object) -> bool:
    return all(_is_unset(value) for value in values)


def _parse_stdin_json(*, enabled: bool) -> dict[str, Any]:
    if not enabled or sys.stdin.isatty():
        return {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        payload = orjson.loads(raw)
    except orjson.JSONDecodeError as exc:
        raise AppError.from_command_error(
            _validation_error(
                'Standard input must contain a JSON object.',
                details={'source': 'stdin'},
            )
        ) from exc
    if not isinstance(payload, dict):
        raise AppError.from_command_error(
            _validation_error(
                'Standard input must contain a JSON object.',
                details={'received_type': type(payload).__name__},
            )
        )
    return payload


def _merge_payload(base: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    payload = dict(base)
    for key, value in overrides.items():
        if value is not None:
            payload[key] = value
    return payload


def _parse_json_option(raw: str | None, *, field_name: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        value = orjson.loads(raw)
    except orjson.JSONDecodeError as exc:
        raise AppError.from_command_error(
            _validation_error(
                f'`{field_name}` must be valid JSON.',
                details={'field': field_name},
            )
        ) from exc
    if not isinstance(value, dict):
        raise AppError.from_command_error(
            _validation_error(
                f'`{field_name}` must be a JSON object.',
                details={'field': field_name},
            )
        )
    return value


def _build_model(model_type: type[ModelT], payload: dict[str, Any]) -> ModelT:  # noqa: UP047
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise AppError.from_command_error(
            _validation_error(
                'Invalid command input.',
                details={'validation_errors': exc.errors(include_url=False)},
            )
        ) from exc


def _validation_error(message: str, *, details: dict[str, Any]) -> CommandError:
    return CommandError(
        code='ERR_VALIDATION_INPUT',
        message=message,
        retryable=False,
        suggested_action='Review the command arguments or stdin JSON, then retry.',
        details=details,
    )


def _resolve_text_input(raw: str | None, *, root: Path, field_name: str) -> str | None:
    if raw is None:
        return None

    candidate_text = raw.strip()
    if not candidate_text:
        return raw

    candidate_path = Path(candidate_text)
    if not candidate_path.is_absolute():
        candidate_path = root / candidate_path
    if not candidate_path.exists():
        return raw
    if not candidate_path.is_file():
        raise AppError.from_command_error(
            _validation_error(
                f'`{field_name}` must be inline text or a readable file path.',
                details={'field': field_name, 'path': str(candidate_path)},
            )
        )
    return candidate_path.read_text(encoding='utf-8')


def _resolve_optional_text(
    *,
    option_value: str | None,
    argument_value: str | None,
    root: Path,
    field_name: str,
) -> str | None:
    if option_value is not None and argument_value is not None:
        raise AppError.from_command_error(
            _validation_error(
                f'Provide `{field_name}` either as an option or as inline text, not both.',
                details={'field': field_name},
            )
        )
    return _resolve_text_input(option_value or argument_value, root=root, field_name=field_name)


def _build_resource_payload(
    resource: EntryRecord | EventRecord, *, applied: bool
) -> dict[str, Any]:
    if isinstance(resource, EntryRecord):
        return {
            'entry': resource,
            'applied': applied,
            'artifacts': {
                'markdown': render_entry_markdown(resource),
                'jsonl': render_entry_jsonl(resource),
            },
        }
    return {
        'event': resource,
        'applied': applied,
        'artifacts': {'jsonl': render_event_jsonl(resource)},
    }


def add_command(  # noqa: B008
    title: str | None = typer.Option(None, '--title'),
    entry_type: str | None = typer.Option(None, '--type'),
    status: str | None = typer.Option(None, '--status'),
    author: str | None = typer.Option(None, '--author'),
    tags: list[str] | None = typer.Option(None, '--tag', '--tags'),
    provenance_json: str | None = typer.Option(None, '--provenance', '--provenance-json'),
    related_ids: list[str] | None = typer.Option(None, '--related-id', '--relate'),
    entity_refs: list[str] | None = typer.Option(None, '--entity-ref', '--entity'),
    metadata_json: str | None = typer.Option(None, '--metadata', '--metadata-json'),
    body: str | None = typer.Argument(None),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        stdin_payload = _parse_stdin_json(
            enabled=_should_read_stdin(
                title,
                entry_type,
                status,
                author,
                tags,
                provenance_json,
                related_ids,
                entity_refs,
                metadata_json,
                body,
            )
        )
        payload = _merge_payload(
            stdin_payload,
            title=title,
            body=_resolve_text_input(body, root=root, field_name='body'),
            type=entry_type,
            status=status,
            author=author,
            tags=tags,
            provenance=_parse_json_option(provenance_json, field_name='provenance_json'),
            related_ids=related_ids,
            entity_refs=entity_refs,
            metadata=_parse_json_option(metadata_json, field_name='metadata_json'),
        )
        entry_input = _build_model(CreateEntryInput, payload)
        entry = create_entry(root, entry_input)
        return {
            'entry': entry,
            'artifacts': {
                'markdown': render_entry_markdown(entry),
                'jsonl': render_entry_jsonl(entry),
            },
        }

    raise SystemExit(run_cli_command('memory.add', 'entry', handler))


def update_command(  # noqa: B008
    public_id: str = typer.Argument(...),
    title: str | None = typer.Option(None, '--title'),
    entry_type: str | None = typer.Option(None, '--type'),
    status: str | None = typer.Option(None, '--status'),
    author: str | None = typer.Option(None, '--author'),
    expected_fingerprint: str | None = typer.Option(None, '--expected-fingerprint'),
    provenance_json: str | None = typer.Option(None, '--provenance', '--provenance-json'),
    related_ids: list[str] | None = typer.Option(None, '--related-id', '--relate'),
    entity_refs: list[str] | None = typer.Option(None, '--entity-ref', '--entity'),
    metadata_json: str | None = typer.Option(None, '--metadata', '--metadata-json'),
    body: str | None = typer.Option(None, '--body'),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        stdin_payload = _parse_stdin_json(
            enabled=_should_read_stdin(
                title,
                entry_type,
                status,
                author,
                expected_fingerprint,
                provenance_json,
                related_ids,
                entity_refs,
                metadata_json,
                body,
            )
        )
        payload = _merge_payload(
            stdin_payload,
            public_id=public_id,
            title=title,
            body=_resolve_text_input(body, root=root, field_name='body'),
            type=entry_type,
            status=status,
            author=author,
            expected_fingerprint=expected_fingerprint,
            provenance=_parse_json_option(provenance_json, field_name='provenance_json'),
            related_ids=related_ids,
            entity_refs=entity_refs,
            metadata=_parse_json_option(metadata_json, field_name='metadata_json'),
        )
        update_input = _build_model(UpdateEntryInput, payload)
        entry, mutation = update_entry(root, update_input)
        return {
            'entry': entry,
            'applied': mutation.applied,
            'artifacts': {
                'markdown': render_entry_markdown(entry),
                'jsonl': render_entry_jsonl(entry),
            },
        }

    raise SystemExit(run_cli_command('memory.update', 'entry', handler))


def tag_add_command(  # noqa: B008
    resource_id: str = typer.Argument(...),
    tags: list[str] = typer.Option(..., '--tag', '--tags'),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        mutation_input = _build_model(
            TagMutationInput,
            {'resource_id': resource_id, 'tags': tags},
        )
        resource, mutation = add_tags(root, mutation_input)
        return _build_resource_payload(resource, applied=mutation.applied)

    raise SystemExit(run_cli_command('memory.tag.add', 'resource', handler))


def tag_remove_command(  # noqa: B008
    resource_id: str = typer.Argument(...),
    tags: list[str] = typer.Option(..., '--tag', '--tags'),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        mutation_input = _build_model(
            TagMutationInput,
            {'resource_id': resource_id, 'tags': tags},
        )
        resource, mutation = remove_tags(root, mutation_input)
        return _build_resource_payload(resource, applied=mutation.applied)

    raise SystemExit(run_cli_command('memory.tag.remove', 'resource', handler))


def event_add_command(  # noqa: B008
    event_type: str | None = typer.Option(None, '--event-type'),
    summary: str | None = typer.Option(None, '--summary'),
    body_option: str | None = typer.Option(None, '--body'),
    actor: str | None = typer.Option(None, '--actor', '--author'),
    tags: list[str] | None = typer.Option(None, '--tag', '--tags'),
    resources: list[str] | None = typer.Option(None, '--resource'),
    related_ids: list[str] | None = typer.Option(None, '--related-id', '--relate'),
    entity_refs: list[str] | None = typer.Option(None, '--entity-ref', '--entity'),
    metadata_json: str | None = typer.Option(None, '--metadata', '--metadata-json'),
    occurred_at: str | None = typer.Option(None, '--occurred-at'),
    body: str | None = typer.Argument(None),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        stdin_payload = _parse_stdin_json(
            enabled=_should_read_stdin(
                event_type,
                summary,
                body_option,
                actor,
                tags,
                resources,
                related_ids,
                entity_refs,
                metadata_json,
                occurred_at,
                body,
            )
        )
        metadata = (
            dict(stdin_payload.get('metadata', {}))
            if isinstance(stdin_payload.get('metadata'), dict)
            else {}
        )
        metadata_override = _parse_json_option(metadata_json, field_name='metadata_json')
        if metadata_override:
            metadata.update(metadata_override)
        if summary is not None:
            metadata['summary'] = summary

        resolved_body = _resolve_optional_text(
            option_value=body_option,
            argument_value=body,
            root=root,
            field_name='body',
        )
        if resolved_body is None:
            resolved_body = summary
        payload = _merge_payload(
            stdin_payload,
            event_type=event_type,
            body=resolved_body,
            author=actor,
            tags=tags,
            resources=(
                [{'resource_id': resource_id, 'role': 'subject'} for resource_id in resources]
                if resources is not None
                else None
            ),
            related_ids=related_ids,
            entity_refs=entity_refs,
            metadata=(
                metadata
                if metadata or metadata_json is not None or summary is not None
                else None
            ),
            occurred_at=occurred_at,
        )
        event_input = _build_model(CreateEventInput, payload)
        event = add_event(root, event_input)
        return {
            'event': event,
            'artifacts': {'jsonl': render_event_jsonl(event)},
        }

    raise SystemExit(run_cli_command('memory.event.add', 'event', handler))


def _make_placeholder(command_id: str, human_name: str):
    def command() -> None:
        raise SystemExit(
            run_cli_command(
                command_id,
                'repository',
                lambda: placeholder_command(command_id, human_name),
            )
        )

    return command


def register(app: typer.Typer) -> None:
    app.command('add')(add_command)
    app.command('update')(update_command)
    app.command('deprecate')(_make_placeholder('memory.deprecate', 'deprecate'))
    app.command('link')(_make_placeholder('memory.link', 'link'))
    app.command('tag-add')(tag_add_command)
    app.command('tag-remove')(tag_remove_command)
    app.command('event-add')(event_add_command)
    app.command('entity-add')(_make_placeholder('memory.entity.add', 'entity-add'))
