"""Compare command implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import trimesh
from build123d import export_step

from .artifacts import collect_file_artifact, ensure_directory, write_json
from .errors import CompareError, GeometryError, UnsupportedOperationError
from .geometry import align_exact_shapes, align_meshes, load_geometry_artifact
from .schemas import CompareMetrics, CompareResult


def _safe_volume_exact(shape: Any) -> float:
    return float(getattr(shape, "volume", 0.0) or 0.0)


def _safe_volume_mesh(mesh: trimesh.Trimesh) -> float | None:
    if not mesh.is_volume:
        return None
    return float(mesh.volume)


def _overlap_ratio(shared_volume: float | None, union_volume: float | None) -> float | None:
    if shared_volume is None or union_volume is None or union_volume <= 0:
        return None
    return float(shared_volume / union_volume)


def _compare_exact(
    left_shape: Any,
    right_shape: Any,
    left_path: Path,
    right_path: Path,
    output_dir: Path,
    alignment: str,
    emit_diff_solids: bool,
) -> CompareResult:
    aligned_right, alignment_payload = align_exact_shapes(left_shape, right_shape, alignment)
    try:
        shared = left_shape.intersect(aligned_right)
        left_only = left_shape.cut(aligned_right)
        right_only = aligned_right.cut(left_shape)
    except Exception as exc:  # pragma: no cover - covered via CLI integration tests
        raise CompareError(f"Exact solid comparison failed: {exc}") from exc

    left_volume = _safe_volume_exact(left_shape)
    right_volume = _safe_volume_exact(aligned_right)
    shared_volume = _safe_volume_exact(shared)
    left_only_volume = _safe_volume_exact(left_only)
    right_only_volume = _safe_volume_exact(right_only)
    union_volume = left_only_volume + shared_volume + right_only_volume
    metrics = CompareMetrics(
        mode="exact",
        alignment=alignment,
        left_volume=left_volume,
        right_volume=right_volume,
        shared_volume=shared_volume,
        left_only_volume=left_only_volume,
        right_only_volume=right_only_volume,
        union_volume=union_volume,
        overlap_ratio=_overlap_ratio(shared_volume, union_volume),
        notes=[f"alignment={alignment_payload}"],
    )
    artifacts = []
    if emit_diff_solids:
        for role, shape in (
            ("shared", shared),
            ("left_only", left_only),
            ("right_only", right_only),
        ):
            if _safe_volume_exact(shape) <= 0.0:
                continue
            path = output_dir / f"{role}.step"
            export_step(shape, path)
            artifacts.append(collect_file_artifact(path, role))

    metrics_path = output_dir / "compare-metrics.json"
    result = CompareResult(
        command="compare",
        summary=(
            f"Compared exact solids with overlap_ratio={metrics.overlap_ratio:.4f}"
            if metrics.overlap_ratio is not None
            else "Compared exact solids"
        ),
        left_path=str(left_path.resolve()),
        right_path=str(right_path.resolve()),
        output_dir=str(output_dir.resolve()),
        metrics_path=str(metrics_path.resolve()),
        metrics=metrics,
        artifacts=artifacts,
    )
    write_json(metrics_path, result)
    return result


def _run_boolean(
    operation: Literal["difference", "intersection", "union"],
    meshes: list[trimesh.Trimesh],
) -> trimesh.Trimesh | None:
    try:
        return cast(
            trimesh.Trimesh | None,
            trimesh.boolean.boolean_manifold(meshes, operation),
        )
    except BaseException as exc:  # pragma: no cover - dependency-backed fallback behavior
        raise UnsupportedOperationError(
            f"Mesh boolean '{operation}' is unavailable: {exc}"
        ) from exc


def _compare_mesh(
    left_mesh: trimesh.Trimesh,
    right_mesh: trimesh.Trimesh,
    left_path: Path,
    right_path: Path,
    output_dir: Path,
    alignment: str,
) -> CompareResult:
    aligned_right, alignment_payload = align_meshes(left_mesh, right_mesh, alignment)
    notes: list[str] = [f"alignment={alignment_payload}"]
    shared_volume: float | None = None
    left_only_volume: float | None = None
    right_only_volume: float | None = None
    union_volume: float | None = None
    try:
        shared_mesh = _run_boolean("intersection", [left_mesh, aligned_right])
        left_only_mesh = _run_boolean("difference", [left_mesh, aligned_right])
        right_only_mesh = _run_boolean("difference", [aligned_right, left_mesh])
        shared_volume = _safe_volume_mesh(shared_mesh) if shared_mesh is not None else None
        left_only_volume = _safe_volume_mesh(left_only_mesh) if left_only_mesh is not None else None
        right_only_volume = (
            _safe_volume_mesh(right_only_mesh) if right_only_mesh is not None else None
        )
        if (
            shared_volume is not None
            and left_only_volume is not None
            and right_only_volume is not None
        ):
            union_volume = shared_volume + left_only_volume + right_only_volume
    except UnsupportedOperationError as exc:
        notes.append(str(exc))

    metrics = CompareMetrics(
        mode="mesh_fallback",
        alignment=alignment,
        left_volume=_safe_volume_mesh(left_mesh),
        right_volume=_safe_volume_mesh(aligned_right),
        shared_volume=shared_volume,
        left_only_volume=left_only_volume,
        right_only_volume=right_only_volume,
        union_volume=union_volume,
        overlap_ratio=_overlap_ratio(shared_volume, union_volume),
        notes=notes,
    )
    metrics_path = output_dir / "compare-metrics.json"
    result = CompareResult(
        command="compare",
        summary=(
            "Compared mesh fallback artifacts"
            if metrics.overlap_ratio is None
            else f"Compared mesh fallback artifacts with overlap_ratio={metrics.overlap_ratio:.4f}"
        ),
        left_path=str(left_path.resolve()),
        right_path=str(right_path.resolve()),
        output_dir=str(output_dir.resolve()),
        metrics_path=str(metrics_path.resolve()),
        metrics=metrics,
        artifacts=[],
    )
    write_json(metrics_path, result)
    return result


def run_compare(
    *,
    left_path: Path,
    right_path: Path,
    output_dir: Path,
    alignment: str,
    emit_diff_solids: bool,
) -> CompareResult:
    # CAD-F-008 / CAD-F-010 / CAD-D-006 / CAD-D-007.
    ensure_directory(output_dir)
    left = load_geometry_artifact(left_path)
    right = load_geometry_artifact(right_path)
    if left.mode == "exact" and right.mode == "exact":
        return _compare_exact(
            left.exact_shape,
            right.exact_shape,
            left_path,
            right_path,
            output_dir,
            alignment,
            emit_diff_solids,
        )
    if left.mesh is None or right.mesh is None:
        raise GeometryError(
            "Comparison requires both artifacts to resolve to exact shapes or meshes"
        )
    return _compare_mesh(left.mesh, right.mesh, left_path, right_path, output_dir, alignment)
