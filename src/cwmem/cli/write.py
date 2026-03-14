from __future__ import annotations

# ruff: noqa: B008
import sys
import threading
from pathlib import Path
from typing import Any, TypeVar

import orjson
import typer
from pydantic import BaseModel, ValidationError

from cwmem.cli.setup import placeholder_command
from cwmem.core.export import render_entry_jsonl, render_entry_markdown, render_event_jsonl
from cwmem.core.graph import add_edge, add_entity
from cwmem.core.models import (
    CommandError,
    CreateEdgeInput,
    CreateEntityInput,
    CreateEntryInput,
    CreateEventInput,
    EntryRecord,
    EventRecord,
    TagMutationInput,
    UpdateEntryInput,
)
from cwmem.core.safety import execute_mutation
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


def _try_read_stdin(timeout: float = 1.0) -> str | None:
    """Read stdin with a timeout to avoid blocking on empty pipes."""
    result: list[str | None] = [None]
    exc_holder: list[BaseException | None] = [None]

    def _reader() -> None:
        try:
            result[0] = sys.stdin.read()
        except BaseException as exc:  # noqa: BLE001
            exc_holder[0] = exc

    thread = threading.Thread(target=_reader, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        return None
    if exc_holder[0] is not None:
        raise exc_holder[0]
    return result[0]


def _parse_stdin_json(*, enabled: bool) -> dict[str, Any]:
    if not enabled or sys.stdin.isatty():
        return {}
    try:
        raw = _try_read_stdin()
    except UnicodeDecodeError as exc:
        raise AppError.from_command_error(
            _validation_error(
                'Standard input must be valid UTF-8 text containing a JSON object.',
                details={'source': 'stdin'},
            )
        ) from exc
    if raw is None:
        return {}
    raw = raw.strip()
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


def _read_stdin_text(*, enabled: bool, option_name: str, field_name: str) -> str | None:
    if not enabled:
        return None
    if sys.stdin.isatty():
        raise AppError.from_command_error(
            _validation_error(
                f'Pipe or redirect standard input when using `--{option_name}`.',
                details={'source': 'stdin', 'option': option_name, 'field': field_name},
            )
        )
    try:
        return sys.stdin.read()
    except UnicodeDecodeError as exc:
        raise AppError.from_command_error(
            _validation_error(
                f'Standard input must be valid UTF-8 text when using `--{option_name}`.',
                details={'source': 'stdin', 'option': option_name, 'field': field_name},
            )
        ) from exc


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
                details={
                    'validation_errors': exc.errors(include_url=False, include_context=False)
                },
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
    body_from_stdin: bool = typer.Option(
        False,
        '--body-from-stdin',
        help='Read the entry body from standard input as plain text.',
    ),
    body: str | None = typer.Argument(None),
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        if body_from_stdin and body is not None:
            raise AppError.from_command_error(
                _validation_error(
                    'Provide `body` either as inline text or via `--body-from-stdin`, not both.',
                    details={'field': 'body', 'option': 'body-from-stdin'},
                )
            )

        stdin_payload = _parse_stdin_json(
            enabled=(not body_from_stdin)
            and _should_read_stdin(
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
        body_text = _read_stdin_text(
            enabled=body_from_stdin,
            option_name='body-from-stdin',
            field_name='body',
        )
        payload = _merge_payload(
            stdin_payload,
            title=title,
            body=(
                body_text
                if body_from_stdin
                else _resolve_text_input(body, root=root, field_name='body')
            ),
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
        return execute_mutation(
            root=root,
            command_id='memory.add',
            request_payload={
                'command': 'memory.add',
                'idempotency_key': idempotency_key,
                'input': entry_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _create_entry_result(apply_root, entry_input),
            summary_builder=lambda _result: {
                'entries_to_create': 1,
                'events_to_create': 1,
            },
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

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
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
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
        return execute_mutation(
            root=root,
            command_id='memory.update',
            request_payload={
                'command': 'memory.update',
                'idempotency_key': idempotency_key,
                'input': update_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _update_entry_result(apply_root, update_input),
            summary_builder=lambda result: {
                'entries_to_update': 1 if result.get('applied') else 0,
                'events_to_create': 1 if result.get('applied') else 0,
            },
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command('memory.update', 'entry', handler))


def tag_add_command(  # noqa: B008
    resource_id: str = typer.Argument(...),
    tags: list[str] = typer.Option(..., '--tag', '--tags'),
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        mutation_input = _build_model(
            TagMutationInput,
            {'resource_id': resource_id, 'tags': tags},
        )
        return execute_mutation(
            root=root,
            command_id='memory.tag.add',
            request_payload={
                'command': 'memory.tag.add',
                'idempotency_key': idempotency_key,
                'input': mutation_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _tag_result(apply_root, mutation_input, add=True),
            summary_builder=lambda result: {
                'entries_to_update': 1 if result.get('applied') else 0,
                'events_to_create': 1 if result.get('applied') else 0,
            },
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command('memory.tag.add', 'resource', handler))


def tag_remove_command(  # noqa: B008
    resource_id: str = typer.Argument(...),
    tags: list[str] = typer.Option(..., '--tag', '--tags'),
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        mutation_input = _build_model(
            TagMutationInput,
            {'resource_id': resource_id, 'tags': tags},
        )
        return execute_mutation(
            root=root,
            command_id='memory.tag.remove',
            request_payload={
                'command': 'memory.tag.remove',
                'idempotency_key': idempotency_key,
                'input': mutation_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _tag_result(apply_root, mutation_input, add=False),
            summary_builder=lambda result: {
                'entries_to_update': 1 if result.get('applied') else 0,
                'events_to_create': 1 if result.get('applied') else 0,
            },
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

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
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
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
        return execute_mutation(
            root=root,
            command_id='memory.event.add',
            request_payload={
                'command': 'memory.event.add',
                'idempotency_key': idempotency_key,
                'input': event_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _event_result(apply_root, event_input),
            summary_builder=lambda _result: {'events_to_create': 1},
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command('memory.event.add', 'event', handler))


def link_command(  # noqa: B008
    source_id: str = typer.Argument(...),
    target_id: str = typer.Argument(...),
    relation_type: str | None = typer.Option(None, '--relation', '--relation-type'),
    provenance: str = typer.Option('explicit_user', '--provenance'),
    confidence: float = typer.Option(1.0, '--confidence'),
    metadata_json: str | None = typer.Option(None, '--metadata', '--metadata-json'),
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        payload = _merge_payload(
            {},
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            provenance=provenance,
            confidence=confidence,
            metadata=_parse_json_option(metadata_json, field_name='metadata_json'),
        )
        edge_input = _build_model(CreateEdgeInput, payload)
        return execute_mutation(
            root=root,
            command_id='memory.link',
            request_payload={
                'command': 'memory.link',
                'idempotency_key': idempotency_key,
                'input': edge_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _edge_result(apply_root, edge_input),
            summary_builder=lambda _result: {'edges_to_create': 1},
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command('memory.link', 'edge', handler))


def entity_add_command(  # noqa: B008
    entity_type: str | None = typer.Option(None, '--entity-type', '--type'),
    name: str | None = typer.Option(None, '--name'),
    status: str | None = typer.Option(None, '--status'),
    aliases: list[str] | None = typer.Option(None, '--alias'),
    tags: list[str] | None = typer.Option(None, '--tag', '--tags'),
    provenance_json: str | None = typer.Option(None, '--provenance', '--provenance-json'),
    metadata_json: str | None = typer.Option(None, '--metadata', '--metadata-json'),
    description_option: str | None = typer.Option(None, '--description'),
    description: str | None = typer.Argument(None),
    dry_run: bool = typer.Option(False, '--dry-run'),
    idempotency_key: str | None = typer.Option(None, '--idempotency-key'),
    wait_lock: float = typer.Option(0.0, '--wait-lock', min=0.0),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    root = (cwd or Path.cwd()).resolve()

    def handler() -> dict[str, Any]:
        stdin_payload = _parse_stdin_json(
            enabled=_should_read_stdin(
                entity_type,
                name,
                status,
                aliases,
                tags,
                provenance_json,
                metadata_json,
                description_option,
                description,
            )
        )
        payload = _merge_payload(
            stdin_payload,
            entity_type=entity_type,
            name=name,
            description=_resolve_optional_text(
                option_value=description_option,
                argument_value=description,
                root=root,
                field_name='description',
            ),
            status=status,
            aliases=aliases,
            tags=tags,
            provenance=_parse_json_option(provenance_json, field_name='provenance_json'),
            metadata=_parse_json_option(metadata_json, field_name='metadata_json'),
        )
        entity_input = _build_model(CreateEntityInput, payload)
        return execute_mutation(
            root=root,
            command_id='memory.entity.add',
            request_payload={
                'command': 'memory.entity.add',
                'idempotency_key': idempotency_key,
                'input': entity_input.model_dump(mode='json'),
            },
            apply_handler=lambda apply_root: _entity_result(apply_root, entity_input),
            summary_builder=lambda _result: {'entities_to_create': 1},
            dry_run=dry_run,
            idempotency_key=idempotency_key,
            wait_lock=wait_lock,
        )

    raise SystemExit(run_cli_command('memory.entity.add', 'entity', handler))


def _create_entry_result(root: Path, entry_input: CreateEntryInput) -> dict[str, Any]:
    entry = create_entry(root, entry_input)
    return {
        'entry': entry,
        'artifacts': {
            'markdown': render_entry_markdown(entry),
            'jsonl': render_entry_jsonl(entry),
        },
    }


def _update_entry_result(root: Path, update_input: UpdateEntryInput) -> dict[str, Any]:
    entry, mutation = update_entry(root, update_input)
    return {
        'entry': entry,
        'applied': mutation.applied,
        'artifacts': {
            'markdown': render_entry_markdown(entry),
            'jsonl': render_entry_jsonl(entry),
        },
    }


def _tag_result(root: Path, mutation_input: TagMutationInput, *, add: bool) -> dict[str, Any]:
    resource, mutation = (
        add_tags(root, mutation_input) if add else remove_tags(root, mutation_input)
    )
    return _build_resource_payload(resource, applied=mutation.applied)


def _event_result(root: Path, event_input: CreateEventInput) -> dict[str, Any]:
    event = add_event(root, event_input)
    return {
        'event': event,
        'artifacts': {'jsonl': render_event_jsonl(event)},
    }


def _edge_result(root: Path, edge_input: CreateEdgeInput) -> dict[str, Any]:
    edge = add_edge(root, edge_input)
    return {'edge': edge}


def _entity_result(root: Path, entity_input: CreateEntityInput) -> dict[str, Any]:
    entity = add_entity(root, entity_input)
    return {'entity': entity}


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


def deprecate_command(  # noqa: B008
    resource_id: str | None = typer.Argument(None),
    cwd: Path | None = typer.Option(None, '--cwd'),
) -> None:
    _ = cwd  # accepted for consistency; command is not yet implemented
    details = {'resource_id': resource_id} if resource_id is not None else None
    target_resource = 'resource' if resource_id is not None else 'repository'
    raise SystemExit(
        run_cli_command(
            'memory.deprecate',
            target_resource,
            lambda: placeholder_command('memory.deprecate', 'deprecate', details=details),
        )
    )


def register(app: typer.Typer) -> None:
    app.command('add')(add_command)
    app.command('update')(update_command)
    app.command('deprecate')(deprecate_command)
    app.command('link')(link_command)
    app.command('tag-add')(tag_add_command)
    app.command('tag-remove')(tag_remove_command)
    app.command('event-add')(event_add_command)
    app.command('entity-add')(entity_add_command)
