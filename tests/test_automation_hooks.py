from __future__ import annotations

from cwmem.core.automation import build_hooks, default_hooks


def test_default_automation_hooks_are_inert() -> None:
    hooks = default_hooks()

    assert hooks.auto_tag(title="Decision", body="Body", metadata={}) == []
    assert hooks.extract_edges(resource_id="mem-000001", text="Body", metadata={}) == []
    assert hooks.learn_from_pr(
        pr_number=1,
        title="PR title",
        body="PR body",
        files=["README.md"],
        metadata={},
    ) is None


def test_build_hooks_accepts_explicit_overrides() -> None:
    hooks = build_hooks(
        auto_tag=lambda **_: ["architecture"],
        extract_edges=lambda **_: [{"source_id": "mem-000001", "target_id": "ent-000001"}],
        learn_from_pr=lambda **_: {"learned": True},
    )

    assert hooks.auto_tag(title="Decision", body="Body", metadata={}) == ["architecture"]
    assert hooks.extract_edges(resource_id="mem-000001", text="Body", metadata={}) == [
        {"source_id": "mem-000001", "target_id": "ent-000001"}
    ]
    assert hooks.learn_from_pr(
        pr_number=1,
        title="PR title",
        body="PR body",
        files=["README.md"],
        metadata={},
    ) == {"learned": True}
