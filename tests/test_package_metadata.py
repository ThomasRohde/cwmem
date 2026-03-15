from __future__ import annotations

import tomllib
from pathlib import Path


def test_project_metadata_is_complete_enough_for_release_builds() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]

    assert project["name"] == "cwmem"
    assert project["readme"] == "README.md"
    assert project["requires-python"] == ">=3.12"
    assert project["scripts"]["cwmem"] == "cwmem.__main__:main"

    dependencies = project["dependencies"]
    for package_name in ("model2vec", "orjson", "pydantic", "portalocker", "typer"):
        assert any(package_name in dependency for dependency in dependencies), package_name

    urls = project["urls"]
    assert urls["Homepage"].endswith("/cwmem")
    assert urls["Repository"].endswith("/cwmem")
    assert urls["Issues"].endswith("/cwmem/issues")


def test_bundled_skill_payload_exists_in_package_tree() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bundled_root = repo_root / "src" / "cwmem" / "vendor" / "skills" / "cwmem"

    assert (bundled_root / "SKILL.md").is_file()
    assert (bundled_root / "references" / "commands.md").is_file()
