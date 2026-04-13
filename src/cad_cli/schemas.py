"""Typed result schemas for machine-readable CLI output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, cast


def to_jsonable(value: Any) -> Any:
    """Convert result dataclasses to JSON-safe values."""
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(cast(Any, value)))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


@dataclass(slots=True)
class ArtifactRecord:
    role: str
    path: str
    sha256: str
    size_bytes: int


@dataclass(slots=True)
class BoundingBoxRecord:
    min_corner: list[float]
    max_corner: list[float]
    size: list[float]


@dataclass(slots=True)
class TraceRecord:
    source_model: str | None
    cwd: str
    args: list[str]
    params: dict[str, Any]
    tool_versions: dict[str, str]


@dataclass(slots=True)
class BuildResult:
    command: str
    summary: str
    output_dir: str
    metadata_path: str
    artifacts: list[ArtifactRecord]
    bounding_box: BoundingBoxRecord
    volume: float
    trace: TraceRecord
    schema_version: int = 1
    status: str = "ok"


@dataclass(slots=True)
class RenderResult:
    command: str
    summary: str
    input_glb: str
    output_dir: str
    metadata_path: str
    artifacts: list[ArtifactRecord]
    blender_bin: str
    render_spec: dict[str, Any]
    schema_version: int = 1
    status: str = "ok"


@dataclass(slots=True)
class CompareMetrics:
    mode: str
    alignment: str
    left_volume: float | None
    right_volume: float | None
    shared_volume: float | None
    left_only_volume: float | None
    right_only_volume: float | None
    union_volume: float | None
    overlap_ratio: float | None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompareResult:
    command: str
    summary: str
    left_path: str
    right_path: str
    output_dir: str
    metrics_path: str
    metrics: CompareMetrics
    artifacts: list[ArtifactRecord]
    schema_version: int = 1
    status: str = "ok"


@dataclass(slots=True)
class HoleFeature:
    feature_id: str
    diameter: float
    radius: float
    axis_point: list[float]
    axis_direction: list[float]


@dataclass(slots=True)
class InspectResult:
    command: str
    summary: str
    artifact_path: str
    mode: str
    data: dict[str, Any]
    schema_version: int = 1
    status: str = "ok"


@dataclass(slots=True)
class PackageEntry:
    role: str
    source_path: str
    archive_path: str
    sha256: str
    size_bytes: int


@dataclass(slots=True)
class PackageResult:
    command: str
    summary: str
    bundle_path: str
    manifest_path: str
    inputs: dict[str, Any]
    entries: list[PackageEntry]
    schema_version: int = 1
    status: str = "ok"
