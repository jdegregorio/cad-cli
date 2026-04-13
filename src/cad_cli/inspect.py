"""Inspect command implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from .errors import UnsupportedOperationError
from .geometry import (
    axis_distance,
    bounding_box_record_from_exact,
    bounding_box_record_from_mesh,
    exact_hole_features,
    exact_thickness,
    find_hole,
    list_to_vector,
    load_geometry_artifact,
    mesh_thickness,
)
from .schemas import InspectResult


def _summary_exact(shape: Any) -> dict[str, object]:
    bbox = bounding_box_record_from_exact(shape)
    holes = exact_hole_features(shape)
    return {
        "bounding_box": bbox,
        "dimensions": bbox.size,
        "volume": float(shape.volume),
        "face_count": len(shape.faces()),
        "edge_count": len(shape.edges()),
        "solid_count": len(shape.solids()),
        "holes": holes,
    }


def _summary_mesh(mesh: trimesh.Trimesh) -> dict[str, object]:
    bbox = bounding_box_record_from_mesh(mesh)
    return {
        "bounding_box": bbox,
        "dimensions": bbox.size,
        "volume": float(mesh.volume) if mesh.is_volume else None,
        "face_count": int(len(mesh.faces)),
        "vertex_count": int(len(mesh.vertices)),
        "notes": ["Mesh fallback summary; feature extraction is limited."],
    }


def inspect_summary(artifact_path: Path) -> InspectResult:
    artifact = load_geometry_artifact(artifact_path)
    if artifact.mode == "exact":
        assert artifact.exact_shape is not None
        data = _summary_exact(artifact.exact_shape)
    else:
        assert artifact.mesh is not None
        data = _summary_mesh(artifact.mesh)
    return InspectResult(
        command="inspect summary",
        summary=f"Inspected summary for {artifact_path.name}",
        artifact_path=str(artifact_path.resolve()),
        mode=artifact.mode,
        data=data,
    )


def inspect_bbox(artifact_path: Path) -> InspectResult:
    artifact = load_geometry_artifact(artifact_path)
    if artifact.mode == "exact":
        assert artifact.exact_shape is not None
        bbox = bounding_box_record_from_exact(artifact.exact_shape)
    else:
        assert artifact.mesh is not None
        bbox = bounding_box_record_from_mesh(artifact.mesh)
    return InspectResult(
        command="inspect bbox",
        summary=f"Computed bounding box for {artifact_path.name}",
        artifact_path=str(artifact_path.resolve()),
        mode=artifact.mode,
        data={"bounding_box": bbox, "dimensions": bbox.size},
    )


def inspect_volume(artifact_path: Path) -> InspectResult:
    artifact = load_geometry_artifact(artifact_path)
    volume: float | None
    if artifact.mode == "exact":
        assert artifact.exact_shape is not None
        volume = float(artifact.exact_shape.volume)
    else:
        assert artifact.mesh is not None
        volume = float(artifact.mesh.volume) if artifact.mesh.is_volume else None
    return InspectResult(
        command="inspect volume",
        summary=f"Computed volume for {artifact_path.name}",
        artifact_path=str(artifact_path.resolve()),
        mode=artifact.mode,
        data={"volume": volume},
    )


def inspect_holes(artifact_path: Path) -> InspectResult:
    artifact = load_geometry_artifact(artifact_path)
    if artifact.mode != "exact":
        raise UnsupportedOperationError("Hole inspection requires a STEP/exact solid artifact")
    assert artifact.exact_shape is not None
    holes = exact_hole_features(artifact.exact_shape)
    return InspectResult(
        command="inspect holes",
        summary=f"Found {len(holes)} cylindrical hole features in {artifact_path.name}",
        artifact_path=str(artifact_path.resolve()),
        mode=artifact.mode,
        data={"holes": holes},
    )


def inspect_center_distance(artifact_path: Path, feature_a: str, feature_b: str) -> InspectResult:
    artifact = load_geometry_artifact(artifact_path)
    if artifact.mode != "exact":
        raise UnsupportedOperationError(
            "Center-distance queries require a STEP/exact solid artifact"
        )
    assert artifact.exact_shape is not None
    hole_a = find_hole(artifact.exact_shape, feature_a)
    hole_b = find_hole(artifact.exact_shape, feature_b)
    distance = axis_distance(hole_a, hole_b)
    return InspectResult(
        command="inspect center-distance",
        summary=f"Center distance between {feature_a} and {feature_b} is {distance:.4f}",
        artifact_path=str(artifact_path.resolve()),
        mode=artifact.mode,
        data={"feature_a": hole_a, "feature_b": hole_b, "center_distance": distance},
    )


def inspect_thickness(
    artifact_path: Path, point_values: list[float], direction: str
) -> InspectResult:
    artifact = load_geometry_artifact(artifact_path)
    direction_map = {
        "x": np.array([1.0, 0.0, 0.0], dtype=float),
        "y": np.array([0.0, 1.0, 0.0], dtype=float),
        "z": np.array([0.0, 0.0, 1.0], dtype=float),
    }
    direction_vector = direction_map[direction]
    if artifact.mode == "exact":
        assert artifact.exact_shape is not None
        thickness = exact_thickness(
            artifact.exact_shape,
            list_to_vector((point_values[0], point_values[1], point_values[2])),
            list_to_vector(
                (
                    float(direction_vector[0]),
                    float(direction_vector[1]),
                    float(direction_vector[2]),
                )
            ),
        )
    else:
        assert artifact.mesh is not None
        thickness = mesh_thickness(
            artifact.mesh,
            np.asarray(point_values, dtype=float),
            direction_vector,
        )
    return InspectResult(
        command="inspect thickness",
        summary=f"Thickness at point {point_values} along {direction} is {thickness:.4f}",
        artifact_path=str(artifact_path.resolve()),
        mode=artifact.mode,
        data={"point": point_values, "direction": direction, "thickness": thickness},
    )
