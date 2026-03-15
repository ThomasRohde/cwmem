from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal, cast

from cwmem.core.models import (
    SkillCustomization,
    SkillInstallResult,
    SkillInstallTarget,
    SkillMetadata,
    SkillRecommendation,
)
from cwmem.output.envelope import conflict_error, io_error, io_read_error, validation_error

SKILL_NAME = "cwmem"
SUPPORTED_TARGETS = {"auto", "copilot", "claude", "agents"}
SUPPORTED_STRATEGIES = {"copy", "link"}

_COPILOT_MARKERS: tuple[tuple[str, Path], ...] = (
    ("install_surface", Path(".github") / "skills"),
    ("install_surface", Path(".github") / "instructions"),
    ("instruction_file", Path(".github") / "copilot-instructions.md"),
    ("install_surface", Path(".copilot") / "skills"),
)
_CLAUDE_MARKERS: tuple[tuple[str, Path], ...] = (
    ("instruction_file", Path("CLAUDE.md")),
    ("install_surface", Path(".claude")),
    ("install_surface", Path(".claude") / "skills"),
)
_GENERIC_MARKERS: tuple[tuple[str, Path], ...] = (
    ("instruction_file", Path("AGENTS.md")),
    ("install_surface", Path(".agents")),
    ("install_surface", Path(".agents") / "skills"),
)


def bundled_skill_root(skill_name: str = SKILL_NAME) -> Path:
    package_root = Path(__file__).resolve().parents[1]
    bundled_root = package_root / "vendor" / "skills" / skill_name
    skill_file = bundled_root / "SKILL.md"
    if not skill_file.is_file():
        raise io_read_error(
            "The bundled skill payload is missing from the installed package.",
            details={"skill": skill_name, "expected_path": bundled_root.as_posix()},
        )
    return bundled_root


def authoring_skill_root(skill_name: str = SKILL_NAME) -> Path | None:
    repository_root = Path(__file__).resolve().parents[3]
    candidate = repository_root / "skills" / skill_name
    return candidate if (candidate / "SKILL.md").is_file() else None


def bundled_skill_files(skill_name: str = SKILL_NAME) -> list[Path]:
    root = bundled_skill_root(skill_name)
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file()
    )


def bundled_skill_metadata(skill_name: str = SKILL_NAME) -> SkillMetadata:
    skill_file = bundled_skill_root(skill_name) / "SKILL.md"
    name, description = _parse_skill_frontmatter(skill_file)
    return SkillMetadata(
        name=name or skill_name,
        description=description,
        bundle_path=f"package://cwmem/vendor/skills/{skill_name}",
    )


def detect_repo_customizations(root: Path) -> list[SkillCustomization]:
    detected: list[SkillCustomization] = []

    for ecosystem, markers in (
        ("copilot", _COPILOT_MARKERS),
        ("claude", _CLAUDE_MARKERS),
        ("agents", _GENERIC_MARKERS),
    ):
        for kind, relative in markers:
            absolute = root / relative
            if absolute.exists():
                detected.append(
                    SkillCustomization(
                        ecosystem=ecosystem,
                        path=relative.as_posix(),
                        kind=cast(Literal["install_surface", "instruction_file"], kind),
                    )
                )

    return detected


def resolve_install_targets(
    root: Path,
    *,
    requested_target: str = "auto",
) -> tuple[list[SkillInstallTarget], bool]:
    if requested_target not in SUPPORTED_TARGETS:
        raise validation_error(
            "Unsupported skill target.",
            details={
                "target": requested_target,
                "supported_targets": sorted(SUPPORTED_TARGETS),
            },
        )

    detections = detect_repo_customizations(root)
    has_copilot = any(item.ecosystem == "copilot" for item in detections)
    has_claude = any(item.ecosystem == "claude" for item in detections)

    target_map = {
        "copilot": SkillInstallTarget(
            ecosystem="copilot",
            path=".github/skills/cwmem",
            reason="Detected GitHub Copilot repo-level customization surfaces.",
        ),
        "claude": SkillInstallTarget(
            ecosystem="claude",
            path=".claude/skills/cwmem",
            reason="Detected Claude repo-level customization surfaces.",
        ),
        "agents": SkillInstallTarget(
            ecosystem="agents",
            path=".agents/skills/cwmem",
            reason="No packaged skill surface was detected, so the generic agent fallback is used.",
        ),
    }

    if requested_target == "copilot":
        return [target_map["copilot"]], False
    if requested_target == "claude":
        return [target_map["claude"]], False
    if requested_target == "agents":
        return [target_map["agents"]], True

    resolved: list[SkillInstallTarget] = []
    if has_copilot:
        resolved.append(target_map["copilot"])
    if has_claude:
        resolved.append(target_map["claude"])
    if resolved:
        return resolved, False
    return [target_map["agents"]], True


def install_skill(
    root: Path,
    *,
    requested_target: str = "auto",
    strategy: str = "copy",
    force: bool = False,
    apply: bool,
) -> SkillInstallResult:
    if strategy not in SUPPORTED_STRATEGIES:
        raise validation_error(
            "Unsupported skill install strategy.",
            details={
                "strategy": strategy,
                "supported_strategies": sorted(SUPPORTED_STRATEGIES),
            },
        )

    root = root.resolve()
    source_root = bundled_skill_root()
    metadata = bundled_skill_metadata()
    detected = detect_repo_customizations(root)
    targets, defaulted_to_agents = resolve_install_targets(root, requested_target=requested_target)
    validated_strategy = cast(Literal["copy", "link"], strategy)

    written_files: list[str] = []
    existing_files: list[str] = []
    skipped_files: list[str] = []

    for target in targets:
        if strategy == "copy":
            target_written, target_existing = _install_copy(
                root=root,
                source_root=source_root,
                target_root=root / target.path,
                force=force,
                apply=apply,
            )
            written_files.extend(target_written)
            existing_files.extend(target_existing)
            continue

        target_written, target_existing, target_skipped = _install_link(
            root=root,
            source_root=source_root,
            target_root=root / target.path,
            force=force,
            apply=apply,
        )
        written_files.extend(target_written)
        existing_files.extend(target_existing)
        skipped_files.extend(target_skipped)

    recommendations = _build_recommendations(root, detected, targets, defaulted_to_agents)

    return SkillInstallResult(
        root=root.as_posix(),
        skill=metadata,
        detected_customizations=detected,
        resolved_targets=targets,
        install_strategy=validated_strategy,
        written_files=sorted(set(written_files)),
        existing_files=sorted(set(existing_files)),
        skipped_files=sorted(set(skipped_files)),
        recommendations=recommendations,
        defaulted_to_agents=defaulted_to_agents,
        applied=apply,
    )


def _install_copy(
    *,
    root: Path,
    source_root: Path,
    target_root: Path,
    force: bool,
    apply: bool,
) -> tuple[list[str], list[str]]:
    written_files: list[str] = []
    existing_files: list[str] = []

    if target_root.exists() and not target_root.is_dir():
        raise conflict_error(
            "The skill target exists but is not a directory.",
            details={"path": _relative_to_root(root, target_root)},
        )

    for relative in bundled_skill_files():
        source_path = source_root / relative
        destination_path = target_root / relative
        relative_destination = _relative_to_root(root, destination_path)

        if destination_path.exists():
            if not destination_path.is_file():
                raise conflict_error(
                    "A skill target path exists but is not a file.",
                    details={"path": relative_destination},
                )
            if _same_file_contents(source_path, destination_path):
                existing_files.append(relative_destination)
                continue
            if not force:
                raise conflict_error(
                    "A skill target file already exists with different content.",
                    details={
                        "path": relative_destination,
                        "suggested_flag": "--force",
                    },
                )

        written_files.append(relative_destination)
        if apply:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)

    return written_files, existing_files


def _install_link(
    *,
    root: Path,
    source_root: Path,
    target_root: Path,
    force: bool,
    apply: bool,
) -> tuple[list[str], list[str], list[str]]:
    relative_target = _relative_to_root(root, target_root)

    if target_root.exists() or target_root.is_symlink():
        if _is_same_symlink(target_root, source_root):
            return [], [relative_target], []
        if not force:
            raise conflict_error(
                "The skill target already exists with different content or link metadata.",
                details={"path": relative_target, "suggested_flag": "--force"},
            )
        if apply:
            _remove_existing_path(target_root)

    if apply:
        target_root.parent.mkdir(parents=True, exist_ok=True)
        try:
            target_root.symlink_to(source_root, target_is_directory=True)
        except OSError as exc:
            raise io_error(
                "Failed to create a symbolic link for the skill target.",
                details={
                    "path": relative_target,
                    "source": source_root.as_posix(),
                    "reason": str(exc),
                },
            ) from exc

    return [relative_target], [], []


def _build_recommendations(
    root: Path,
    detected: list[SkillCustomization],
    targets: list[SkillInstallTarget],
    defaulted_to_agents: bool,
) -> list[SkillRecommendation]:
    recommendations: list[SkillRecommendation] = []
    target_paths_by_ecosystem = {target.ecosystem: target.path for target in targets}
    installed_paths = [target.path for target in targets]

    if (root / "AGENTS.md").is_file():
        recommendations.append(
            SkillRecommendation(
                path="AGENTS.md",
                reason="Existing generic repo instructions can advertise the installed skill.",
                paragraph=_agents_paragraph(installed_paths),
            )
        )

    copilot_path = root / ".github" / "copilot-instructions.md"
    if copilot_path.is_file():
        recommendations.append(
            SkillRecommendation(
                path=".github/copilot-instructions.md",
                reason=(
                    "Existing GitHub Copilot instructions can point Copilot at "
                    "the installed skill."
                ),
                paragraph=_copilot_paragraph(
                    target_paths_by_ecosystem.get("copilot", installed_paths[0])
                ),
            )
        )

    if (root / "CLAUDE.md").is_file():
        recommendations.append(
            SkillRecommendation(
                path="CLAUDE.md",
                reason="Existing Claude instructions can point Claude at the installed skill.",
                paragraph=_claude_paragraph(
                    target_paths_by_ecosystem.get("claude", installed_paths[0])
                ),
            )
        )

    has_instruction_file = any(item.kind == "instruction_file" for item in detected)
    if not recommendations and defaulted_to_agents and not has_instruction_file:
        recommendations.append(
            SkillRecommendation(
                path="AGENTS.md",
                reason=(
                    "No repo instruction file was detected, so AGENTS.md is the "
                    "default generic instruction surface."
                ),
                paragraph=_agents_paragraph(installed_paths),
            )
        )

    return recommendations


def _agents_paragraph(installed_paths: list[str]) -> str:
    return (
        f"This repository ships the `cwmem` skill at {_format_paths(installed_paths)}. Use it "
        "whenever work uncovers an architecture decision, dependency policy, workflow change, "
        "or debugging lesson worth preserving in repo memory. Prefer `--dry-run` before "
        "unfamiliar writes, reuse `--idempotency-key` for retried mutations, never hand-edit "
        "`memory/`, and run `cwmem sync export` after successful `cwmem` writes."
    )


def _copilot_paragraph(installed_path: str) -> str:
    return (
        f"This repo includes the packaged `cwmem` skill at `{installed_path}`. Use that skill "
        "when the task is about recording, updating, linking, searching, or verifying "
        "repository memory, or when a meaningful architecture/process change should be saved. "
        "Prefer `--dry-run` for cautious writes, reuse `--idempotency-key` on retries, never "
        "hand-edit `memory/`, and run `cwmem sync export` after successful mutations."
    )


def _claude_paragraph(installed_path: str) -> str:
    return (
        f"This repo includes the packaged `cwmem` skill at `{installed_path}`. Use that skill "
        "when the task is about recording, updating, linking, searching, or verifying "
        "repository memory, or when a meaningful architecture/process change should be saved. "
        "Prefer `--dry-run` for cautious writes, reuse `--idempotency-key` on retries, never "
        "hand-edit `memory/`, and run `cwmem sync export` after successful mutations."
    )


def _parse_skill_frontmatter(skill_file: Path) -> tuple[str, str]:
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise io_read_error(
            "Failed to read the bundled skill markdown file.",
            details={"path": skill_file.as_posix(), "reason": str(exc)},
        ) from exc

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise io_read_error(
            "The bundled skill markdown file is missing YAML frontmatter.",
            details={"path": skill_file.as_posix()},
        )

    try:
        closing_index = next(
            index for index in range(1, len(lines)) if lines[index].strip() == "---"
        )
    except StopIteration as exc:
        raise io_read_error(
            "The bundled skill markdown file has malformed YAML frontmatter.",
            details={"path": skill_file.as_posix()},
        ) from exc

    frontmatter_lines = lines[1:closing_index]
    name = ""
    description = ""
    index = 0

    while index < len(frontmatter_lines):
        line = frontmatter_lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if ":" not in line:
            index += 1
            continue

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()

        if key == "name":
            name = _strip_yaml_scalar(value)
            index += 1
            continue

        if key == "description" and value == ">":
            folded_lines: list[str] = []
            index += 1
            while index < len(frontmatter_lines):
                continuation = frontmatter_lines[index]
                if continuation.startswith((" ", "\t")) or not continuation.strip():
                    if continuation.strip():
                        folded_lines.append(continuation.strip())
                    index += 1
                    continue
                break
            description = " ".join(folded_lines).strip()
            continue

        if key == "description":
            description = _strip_yaml_scalar(value)

        index += 1

    return name, description


def _strip_yaml_scalar(value: str) -> str:
    return value.strip().strip("'").strip('"')


def _same_file_contents(source_path: Path, destination_path: Path) -> bool:
    return source_path.read_bytes() == destination_path.read_bytes()


def _is_same_symlink(target_path: Path, source_root: Path) -> bool:
    if not target_path.is_symlink():
        return False
    try:
        return target_path.resolve() == source_root.resolve()
    except OSError:
        return False


def _remove_existing_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink(missing_ok=True)


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _format_paths(paths: list[str]) -> str:
    quoted = [f"`{path}`" for path in paths]
    if len(quoted) == 1:
        return quoted[0]
    if len(quoted) == 2:
        return f"{quoted[0]} and {quoted[1]}"
    return f"{', '.join(quoted[:-1])}, and {quoted[-1]}"
