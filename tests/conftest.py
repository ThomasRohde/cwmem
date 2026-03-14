from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
PACKAGE_MAIN = SRC_ROOT / "cwmem" / "__main__.py"
CLI_TIMEOUT_SECONDS = 30


def pytest_report_header(config: pytest.Config) -> list[str]:
    _ = config
    return [
        "cwmem bootstrap tests assume `src/cwmem` is created by the scaffold work.",
        (
            "If the scaffold is not present yet, these tests skip and should be "
            "re-run in todo e1-reconcile-verify."
        ),
    ]


@pytest.fixture
def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath_parts = [str(SRC_ROOT)]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath_parts.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.fixture
def run_cli(cli_env: dict[str, str]):
    if not PACKAGE_MAIN.exists():
        pytest.skip(
            "cwmem scaffold is not present yet; run these integration tests during "
            "todo e1-reconcile-verify."
        )

    def _run(
        tmp_repo: Path, *args: str, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [sys.executable, "-m", "cwmem", *args],
                cwd=tmp_repo,
                env=cli_env,
                capture_output=True,
                input=input_text,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover
            pytest.fail(
                f"cwmem {' '.join(args)} timed out after {CLI_TIMEOUT_SECONDS}s.\n"
                f"STDOUT:\n{exc.stdout or ''}\n"
                f"STDERR:\n{exc.stderr or ''}"
            )

    return _run

