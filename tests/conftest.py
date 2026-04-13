from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cad(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cad_cli", *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def examples_dir() -> Path:
    return REPO_ROOT / "examples" / "models"


@pytest.fixture
def blender_available() -> bool:
    return shutil.which("blender") is not None
