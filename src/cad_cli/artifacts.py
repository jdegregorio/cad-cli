"""Filesystem and artifact helpers."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .schemas import ArtifactRecord, to_jsonable


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> Path:
    ensure_directory(path.parent)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, sort_keys=True) + "\n")
    return path


def copy_file(source: Path, destination: Path) -> Path:
    ensure_directory(destination.parent)
    shutil.copy2(source, destination)
    return destination


def collect_file_artifact(path: Path, role: str) -> ArtifactRecord:
    return ArtifactRecord(
        role=role,
        path=str(path),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for child in sorted(path.rglob("*")):
        if child.is_file():
            yield child
