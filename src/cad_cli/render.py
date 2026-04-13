"""Render command implementation."""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from . import __version__
from .artifacts import collect_file_artifact, ensure_directory, write_json
from .errors import InputError, MissingDependencyError, RenderError
from .schemas import RenderResult

RENDER_VIEW_NAMES = ("front", "back", "left", "right", "top", "bottom", "iso")

DEFAULT_RENDER_SPEC: dict[str, Any] = {
    "width": 768,
    "height": 768,
    "samples": 32,
    "engine": "BLENDER_EEVEE",
}


def blender_script_path() -> Path:
    return Path(__file__).with_name("blender").joinpath("render_glb.py")


def resolve_blender_binary(explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        if not explicit_path.exists():
            raise MissingDependencyError(
                f"Requested Blender binary does not exist: {explicit_path}"
            )
        return explicit_path
    env_value = os.environ.get("CAD_BLENDER_BIN")
    if env_value:
        candidate = Path(env_value)
        if candidate.exists():
            return candidate
    resolved = shutil.which("blender")
    if resolved is None:
        raise MissingDependencyError(
            "Blender not found. Install Blender and provide --blender-bin, "
            "CAD_BLENDER_BIN, or PATH."
        )
    return Path(resolved)


def load_render_spec(spec_path: Path | None) -> dict[str, Any]:
    spec = dict(DEFAULT_RENDER_SPEC)
    if spec_path is not None:
        loaded = json.loads(spec_path.read_text())
        if not isinstance(loaded, dict):
            raise InputError("Render spec files must contain a top-level JSON object")
        spec.update(loaded)
    return spec


def compose_sheet(output_dir: Path, width: int, height: int) -> Path:
    sheet_path = output_dir / "sheet.png"
    columns = 4
    rows = 2
    canvas = Image.new("RGB", (width * columns, height * rows), color=(248, 248, 248))
    draw = ImageDraw.Draw(canvas)
    for index, label in enumerate(RENDER_VIEW_NAMES):
        x = (index % columns) * width
        y = (index // columns) * height
        image = Image.open(output_dir / f"{label}.png").convert("RGB")
        canvas.paste(image, (x, y))
        draw.rectangle((x, y, x + width, y + 34), fill=(255, 255, 255))
        draw.text((x + 14, y + 9), label.upper(), fill=(32, 32, 32))
    canvas.save(sheet_path)
    return sheet_path


def run_render(
    *,
    glb_path: Path,
    output_dir: Path,
    spec_path: Path | None,
    blender_bin: Path | None,
    raw_args: list[str],
) -> RenderResult:
    # CAD-F-006 / CAD-F-007 / CAD-F-019 / CAD-F-020 / CAD-F-021 / CAD-D-004:
    # deterministic Blender-backed renders with full-fit datum and angled views.
    if not glb_path.exists():
        raise InputError(f"GLB input does not exist: {glb_path}")
    ensure_directory(output_dir)
    resolved_blender = resolve_blender_binary(blender_bin)
    render_spec = load_render_spec(spec_path)
    render_script = blender_script_path()
    if not render_script.exists():
        raise RenderError(f"Blender helper script is missing: {render_script}")

    command = [
        str(resolved_blender),
        "--background",
        "--factory-startup",
        "--python",
        str(render_script),
        "--",
        str(glb_path.resolve()),
        str(output_dir.resolve()),
        json.dumps(render_spec),
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RenderError(
            "Blender render failed:\n"
            f"STDOUT:\n{process.stdout}\n"
            f"STDERR:\n{process.stderr}"
        )

    required_paths = [output_dir / f"{name}.png" for name in RENDER_VIEW_NAMES]
    missing = [path for path in required_paths if not path.exists() or path.stat().st_size == 0]
    if missing:
        raise RenderError(f"Blender completed without producing expected views: {missing}")
    sheet_path = compose_sheet(output_dir, int(render_spec["width"]), int(render_spec["height"]))
    metadata_path = output_dir / "render-metadata.json"
    artifacts = [collect_file_artifact(path, path.stem) for path in [*required_paths, sheet_path]]
    result = RenderResult(
        command="render",
        summary=(
            f"Rendered {glb_path.name} into {output_dir} with {len(artifacts)} preview assets"
        ),
        input_glb=str(glb_path.resolve()),
        output_dir=str(output_dir.resolve()),
        metadata_path=str(metadata_path.resolve()),
        artifacts=artifacts,
        blender_bin=str(resolved_blender),
        render_spec={
            **render_spec,
            "argv": raw_args,
            "cad_cli_version": __version__,
            "build123d_version": importlib.metadata.version("build123d"),
        },
    )
    write_json(metadata_path, result)
    return result
