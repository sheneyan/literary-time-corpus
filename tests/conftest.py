from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def run_ltc(project_root: Path):
    def run(*arguments: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "run", "ltc", *(str(argument) for argument in arguments)],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )

    return run
