"""Build command implementation."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import traceback
import types
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from build123d import export_gltf, export_step, export_stl

from . import __version__
from .artifacts import collect_file_artifact, copy_file, ensure_directory, write_json
from .errors import GeometryError, InputError
from .geometry import bounding_box_record_from_exact
from .schemas import BuildResult, TraceRecord


@dataclass(slots=True)
class BuildInvocationContext:
    source_path: str
    output_dir: str
    callable_name: str


def _load_python_module(model_path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(model_path.stem, model_path)
    if spec is None or spec.loader is None:
        raise InputError(f"Unable to import model source: {model_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise InputError(
            f"Failed to import model source '{model_path}': "
            f"{type(exc).__name__}: {exc}",
            traceback_str=traceback.format_exc(),
            cause_type=type(exc).__name__,
            cause_message=str(exc),
        ) from exc
    return module


def _load_build_callable(
    model_path: Path, callable_name: str
) -> Callable[[dict[str, Any], BuildInvocationContext], Any]:
    module = _load_python_module(model_path)
    build_callable = getattr(module, callable_name, None)
    if build_callable is None or not callable(build_callable):
        raise InputError(
            f"Model source must expose a callable named '{callable_name}(params, context)'"
        )
    return cast(Callable[[dict[str, Any], BuildInvocationContext], Any], build_callable)


def _coerce_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _assign_nested(target: dict[str, Any], key: str, value: Any) -> None:
    cursor = target
    parts = key.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
        if not isinstance(cursor, dict):
            raise InputError(f"Cannot assign nested param into non-object key '{part}'")
    cursor[parts[-1]] = value


def load_params(params_path: Path | None, overrides: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if params_path is not None:
        params = json.loads(params_path.read_text())
        if not isinstance(params, dict):
            raise InputError("Parameter files must contain a top-level JSON object")
    for override in overrides:
        if "=" not in override:
            raise InputError(f"Invalid --set override '{override}', expected key=value")
        key, raw_value = override.split("=", 1)
        _assign_nested(params, key, _coerce_value(raw_value))
    return params


def _tool_versions() -> dict[str, str]:
    return {
        "cad-cli": __version__,
        "build123d": importlib.metadata.version("build123d"),
        "trimesh": importlib.metadata.version("trimesh"),
    }


def _validate_shape(result: Any) -> Any:
    # CAD-F-003 / CAD-D-001: model callables must return a build123d-compatible shape object.
    required_attributes = ["bounding_box", "center", "faces", "solids", "volume"]
    if all(hasattr(result, attr) for attr in required_attributes):
        return result
    raise GeometryError("Model callable did not return a build123d shape/part/compound")


def run_build(
    *,
    model_path: Path,
    output_dir: Path,
    params_path: Path | None,
    overrides: list[str],
    callable_name: str,
    emit_stl: bool,
    snapshot_source: bool,
    raw_args: list[str],
) -> BuildResult:
    # CAD-F-003 / CAD-F-004 / CAD-F-017: deterministic build outputs with traceable metadata.
    if not model_path.exists():
        raise InputError(f"Model source does not exist: {model_path}")
    ensure_directory(output_dir)
    params = load_params(params_path, overrides)
    build_callable = _load_build_callable(model_path, callable_name)
    context = BuildInvocationContext(
        source_path=str(model_path.resolve()),
        output_dir=str(output_dir.resolve()),
        callable_name=callable_name,
    )
    try:
        raw_shape = build_callable(params, context)
    except Exception as exc:
        raise GeometryError(
            f"Model callable '{callable_name}' raised "
            f"{type(exc).__name__}: {exc}",
            traceback_str=traceback.format_exc(),
            cause_type=type(exc).__name__,
            cause_message=str(exc),
        ) from exc
    shape = _validate_shape(raw_shape)

    step_path = output_dir / "model.step"
    glb_path = output_dir / "model.glb"
    metadata_path = output_dir / "build-metadata.json"

    try:
        export_step(shape, step_path)
        export_gltf(shape, glb_path, binary=True)
        stl_path = output_dir / "model.stl" if emit_stl else None
        if stl_path is not None:
            export_stl(shape, stl_path)
    except Exception as exc:  # pragma: no cover - surfaced via integration tests
        raise GeometryError(
            f"Failed to export build artifacts: {type(exc).__name__}: {exc}",
            traceback_str=traceback.format_exc(),
            cause_type=type(exc).__name__,
            cause_message=str(exc),
        ) from exc

    snapshot_path: Path | None = None
    if snapshot_source:
        snapshot_path = output_dir / "source-snapshot.py"
        copy_file(model_path, snapshot_path)

    artifacts = [
        collect_file_artifact(step_path, "step"),
        collect_file_artifact(glb_path, "glb"),
    ]
    if emit_stl and stl_path is not None:
        artifacts.append(collect_file_artifact(stl_path, "stl"))
    if snapshot_path is not None:
        artifacts.append(collect_file_artifact(snapshot_path, "source_snapshot"))

    trace = TraceRecord(
        source_model=str(model_path.resolve()),
        cwd=str(Path.cwd()),
        args=raw_args,
        params=params,
        tool_versions=_tool_versions(),
    )
    result = BuildResult(
        command="build",
        summary=(
            f"Built {model_path.name} into {output_dir} with {len(artifacts)} artifacts; "
            f"volume={shape.volume:.4f}"
        ),
        output_dir=str(output_dir.resolve()),
        metadata_path=str(metadata_path.resolve()),
        artifacts=artifacts,
        bounding_box=bounding_box_record_from_exact(shape),
        volume=float(shape.volume),
        trace=trace,
    )
    write_json(metadata_path, result)
    return result
