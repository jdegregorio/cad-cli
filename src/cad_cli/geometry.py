"""Geometry loading, alignment, and shared measurement helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import trimesh
from build123d import Axis, GeomType, Matrix, Vector, import_step
from scipy.spatial.transform import Rotation  # type: ignore[import-untyped]

from .errors import GeometryError, InputError, UnsupportedOperationError
from .schemas import BoundingBoxRecord, HoleFeature

STEP_SUFFIXES = {".step", ".stp"}
MESH_SUFFIXES = {".glb", ".gltf", ".stl"}


@dataclass(slots=True)
class GeometryArtifact:
    path: Path
    mode: str
    source_format: str
    exact_shape: Any | None = None
    mesh: trimesh.Trimesh | None = None


def vector_to_list(vector: Vector) -> list[float]:
    return [float(vector.X), float(vector.Y), float(vector.Z)]


def list_to_vector(values: list[float] | tuple[float, float, float]) -> Vector:
    return Vector(*values)


def bounding_box_record_from_exact(shape: Any) -> BoundingBoxRecord:
    bbox = shape.bounding_box()
    return BoundingBoxRecord(
        min_corner=vector_to_list(bbox.min),
        max_corner=vector_to_list(bbox.max),
        size=vector_to_list(bbox.size),
    )


def bounding_box_record_from_mesh(mesh: trimesh.Trimesh) -> BoundingBoxRecord:
    bounds = mesh.bounds
    size = bounds[1] - bounds[0]
    return BoundingBoxRecord(
        min_corner=[float(v) for v in bounds[0]],
        max_corner=[float(v) for v in bounds[1]],
        size=[float(v) for v in size],
    )


def normalize_mesh(loaded: Any) -> trimesh.Trimesh:
    if isinstance(loaded, trimesh.Trimesh):
        return loaded
    if isinstance(loaded, trimesh.Scene):
        meshes = [geom for geom in loaded.geometry.values()]
        if not meshes:
            raise GeometryError("Mesh scene contains no geometry")
        return cast(trimesh.Trimesh, trimesh.util.concatenate(meshes))
    raise GeometryError(f"Unsupported trimesh load result: {type(loaded)!r}")


def load_geometry_artifact(path: Path) -> GeometryArtifact:
    if not path.exists():
        raise InputError(f"Artifact does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in STEP_SUFFIXES:
        return GeometryArtifact(
            path=path,
            mode="exact",
            source_format=suffix.lstrip("."),
            exact_shape=import_step(path),
        )
    if suffix in MESH_SUFFIXES:
        mesh = normalize_mesh(trimesh.load(path, force="mesh"))
        return GeometryArtifact(
            path=path,
            mode="mesh",
            source_format=suffix.lstrip("."),
            mesh=mesh,
        )
    raise InputError(
        f"Unsupported artifact type '{suffix}'. Supported: STEP/STP, GLB/GLTF, STL."
    )


def _normalized_basis(vectors: list[np.ndarray]) -> np.ndarray:
    basis = np.column_stack([vec / np.linalg.norm(vec) for vec in vectors])
    if np.linalg.det(basis) < 0:
        basis[:, 2] *= -1.0
    return basis


def _exact_principal_basis(shape: Any) -> np.ndarray:
    props = sorted(shape.principal_properties, key=lambda item: item[1])
    vectors = [
        np.array([float(vec.X), float(vec.Y), float(vec.Z)], dtype=float) for vec, _ in props
    ]
    return _normalized_basis(vectors)


def _mesh_principal_basis(mesh: trimesh.Trimesh) -> np.ndarray:
    vectors = [np.asarray(vec, dtype=float) for vec in mesh.principal_inertia_vectors]
    return _normalized_basis(vectors)


def _transform_matrix(rotation: np.ndarray, translation: np.ndarray) -> Matrix:
    matrix_rows = [
        [
            float(rotation[0, 0]),
            float(rotation[0, 1]),
            float(rotation[0, 2]),
            float(translation[0]),
        ],
        [
            float(rotation[1, 0]),
            float(rotation[1, 1]),
            float(rotation[1, 2]),
            float(translation[1]),
        ],
        [
            float(rotation[2, 0]),
            float(rotation[2, 1]),
            float(rotation[2, 2]),
            float(translation[2]),
        ],
    ]
    return Matrix(matrix_rows)


def align_exact_shapes(left: Any, right: Any, mode: str) -> tuple[Any, dict[str, Any]]:
    left_center = np.array(vector_to_list(left.center()), dtype=float)
    right_center = np.array(vector_to_list(right.center()), dtype=float)
    if mode == "none":
        return right, {"translation": [0.0, 0.0, 0.0], "rotation_matrix": np.eye(3).tolist()}
    if mode == "translate":
        translation = left_center - right_center
        aligned = right.translate(tuple(float(value) for value in translation))
        return aligned, {"translation": translation.tolist(), "rotation_matrix": np.eye(3).tolist()}
    if mode == "principal":
        left_basis = _exact_principal_basis(left)
        right_basis = _exact_principal_basis(right)
        rotation = left_basis @ right_basis.T
        euler_angles = Rotation.from_matrix(rotation).as_euler("xyz", degrees=True)
        aligned = right.translate(tuple(float(value) for value in (-right_center)))
        for axis, angle in zip((Axis.X, Axis.Y, Axis.Z), euler_angles, strict=True):
            if not math.isclose(float(angle), 0.0, abs_tol=1e-6):
                aligned = aligned.rotate(axis, float(angle))
        aligned = aligned.translate(tuple(float(value) for value in left_center))
        translation = left_center - rotation @ right_center
        return aligned, {"translation": translation.tolist(), "rotation_matrix": rotation.tolist()}
    raise InputError(f"Unsupported alignment mode: {mode}")


def align_meshes(
    left: trimesh.Trimesh, right: trimesh.Trimesh, mode: str
) -> tuple[trimesh.Trimesh, dict[str, Any]]:
    left_center = np.asarray(left.center_mass if left.is_volume else left.centroid, dtype=float)
    right_center = np.asarray(right.center_mass if right.is_volume else right.centroid, dtype=float)
    aligned = right.copy()
    if mode == "none":
        return aligned, {"translation": [0.0, 0.0, 0.0], "rotation_matrix": np.eye(3).tolist()}
    if mode == "translate":
        translation = left_center - right_center
        matrix = np.eye(4)
        matrix[:3, 3] = translation
        aligned.apply_transform(matrix)
        return aligned, {"translation": translation.tolist(), "rotation_matrix": np.eye(3).tolist()}
    if mode == "principal":
        left_basis = _mesh_principal_basis(left)
        right_basis = _mesh_principal_basis(right)
        rotation = left_basis @ right_basis.T
        translation = left_center - rotation @ right_center
        matrix = np.eye(4)
        matrix[:3, :3] = rotation
        matrix[:3, 3] = translation
        aligned.apply_transform(matrix)
        return aligned, {"translation": translation.tolist(), "rotation_matrix": rotation.tolist()}
    raise InputError(f"Unsupported alignment mode: {mode}")


def exact_hole_features(shape: Any) -> list[HoleFeature]:
    features: list[HoleFeature] = []
    for face in shape.faces():
        if face.geom_type != GeomType.CYLINDER:
            continue
        axis = face.axis_of_rotation
        features.append(
            HoleFeature(
                feature_id="",
                diameter=float(face.radius * 2.0),
                radius=float(face.radius),
                axis_point=vector_to_list(axis.position),
                axis_direction=vector_to_list(axis.direction),
            )
        )
    features.sort(
        key=lambda item: (round(item.diameter, 6), item.axis_point, item.axis_direction)
    )
    for index, feature in enumerate(features, start=1):
        feature.feature_id = f"hole-{index}"
    return features


def find_hole(shape: Any, feature_id: str) -> HoleFeature:
    for feature in exact_hole_features(shape):
        if feature.feature_id == feature_id:
            return feature
    raise InputError(f"Unknown hole feature id: {feature_id}")


def axis_distance(feature_a: HoleFeature, feature_b: HoleFeature) -> float:
    point_a = np.asarray(feature_a.axis_point, dtype=float)
    point_b = np.asarray(feature_b.axis_point, dtype=float)
    direction_a = np.asarray(feature_a.axis_direction, dtype=float)
    direction_b = np.asarray(feature_b.axis_direction, dtype=float)
    direction_a = direction_a / np.linalg.norm(direction_a)
    direction_b = direction_b / np.linalg.norm(direction_b)
    cross = np.cross(direction_a, direction_b)
    norm = np.linalg.norm(cross)
    delta = point_b - point_a
    if norm < 1e-9:
        return float(np.linalg.norm(np.cross(delta, direction_a)))
    return float(abs(np.dot(delta, cross)) / norm)


def exact_thickness(shape: Any, point: Vector, direction: Vector) -> float:
    if not shape.is_inside(point):
        raise InputError("Thickness queries require a point inside the solid material")
    axis = Axis(point, direction)
    intersections = shape.find_intersection_points(axis)
    if not intersections:
        raise GeometryError("No intersections found for the requested thickness probe")
    direction_np = np.asarray(vector_to_list(direction), dtype=float)
    direction_np = direction_np / np.linalg.norm(direction_np)
    origin_np = np.asarray(vector_to_list(point), dtype=float)
    t_values: list[float] = []
    for intersection_point, _normal in intersections:
        t = float(np.dot(np.asarray(vector_to_list(intersection_point)) - origin_np, direction_np))
        if not any(math.isclose(t, existing, abs_tol=1e-6) for existing in t_values):
            t_values.append(t)
    t_values.sort()
    boundaries = [-1e6, *t_values, 1e6]
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        midpoint = (start + end) / 2.0
        midpoint_vector = point + Vector(*(direction_np * midpoint))
        if shape.is_inside(midpoint_vector):
            if start <= 0.0 <= end:
                return float(end - start)
    raise GeometryError("Unable to resolve a solid segment for thickness at the requested point")


def mesh_thickness(mesh: trimesh.Trimesh, point: np.ndarray, direction: np.ndarray) -> float:
    origins = np.vstack([point - direction * 1e3, point + direction * 1e3])
    directions = np.vstack([direction, -direction])
    locations, _index_ray, _index_tri = mesh.ray.intersects_location(  # type: ignore[no-untyped-call]
        origins,
        directions,
    )
    if len(locations) < 2:
        raise UnsupportedOperationError(
            "Mesh thickness probing needs at least two ray intersections"
        )
    projected = [float(np.dot(location - point, direction)) for location in locations]
    projected.sort()
    for start, end in zip(projected, projected[1:], strict=False):
        midpoint = point + direction * ((start + end) / 2.0)
        if mesh.contains([midpoint])[0]:
            if start <= 0.0 <= end:
                return float(end - start)
    raise UnsupportedOperationError(
        "Unable to resolve a mesh thickness segment for the requested point"
    )
