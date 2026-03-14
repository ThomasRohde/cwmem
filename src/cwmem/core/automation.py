from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class AutoTagHook(Protocol):
    def __call__(self, *, title: str, body: str, metadata: dict[str, Any]) -> list[str]: ...


class EdgeExtractionHook(Protocol):
    def __call__(
        self, *, resource_id: str, text: str, metadata: dict[str, Any]
    ) -> list[dict[str, Any]]: ...


class PrLearningHook(Protocol):
    def __call__(
        self,
        *,
        pr_number: int | None,
        title: str,
        body: str,
        files: list[str],
        metadata: dict[str, Any],
    ) -> dict[str, Any] | None: ...


def noop_auto_tag(*, title: str, body: str, metadata: dict[str, Any]) -> list[str]:
    _ = (title, body, metadata)
    return []


def noop_extract_edges(
    *, resource_id: str, text: str, metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    _ = (resource_id, text, metadata)
    return []


def noop_learn_from_pr(
    *,
    pr_number: int | None,
    title: str,
    body: str,
    files: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    _ = (pr_number, title, body, files, metadata)
    return None


@dataclass(frozen=True)
class AutomationHooks:
    auto_tag: AutoTagHook = noop_auto_tag
    extract_edges: EdgeExtractionHook = noop_extract_edges
    learn_from_pr: PrLearningHook = noop_learn_from_pr


_DEFAULT_HOOKS = AutomationHooks()


def default_hooks() -> AutomationHooks:
    return _DEFAULT_HOOKS


def build_hooks(
    *,
    auto_tag: AutoTagHook = noop_auto_tag,
    extract_edges: EdgeExtractionHook = noop_extract_edges,
    learn_from_pr: PrLearningHook = noop_learn_from_pr,
) -> AutomationHooks:
    return AutomationHooks(
        auto_tag=auto_tag,
        extract_edges=extract_edges,
        learn_from_pr=learn_from_pr,
    )
