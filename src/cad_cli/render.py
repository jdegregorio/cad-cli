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

# Color palette for compare diff rendering (linear sRGB for Blender Principled BSDF).
COMPARE_COLORS: dict[str, list[float]] = {
    "left": [0.22, 0.50, 0.82, 1.0],
    "right": [0.90, 0.55, 0.08, 1.0],
    "shared": [0.20, 0.70, 0.32, 1.0],
    "left_only": [0.22, 0.50, 0.82, 1.0],
    "right_only": [0.90, 0.55, 0.08, 1.0],
}

# Label-friendly display names and banner colors (PIL RGB) for the compare sheet.
COMPARE_LABELS: dict[str, str] = {
    "left": "LEFT",
    "right": "RIGHT",
    "shared": "SHARED",
    "left_only": "LEFT ONLY",
    "right_only": "RIGHT ONLY",
}
COMPARE_BANNER_COLORS: dict[str, tuple[int, int, int]] = {
    "left": (80, 130, 175),
    "right": (200, 155, 40),
    "shared": (80, 165, 90),
    "left_only": (60, 110, 175),
    "right_only": (200, 155, 40),
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


def render_single_view(
    *,
    glb_path: Path,
    output_path: Path,
    blender_bin: Path | None,
    view: str = "iso",
    base_color: list[float] | None = None,
    spec_overrides: dict[str, Any] | None = None,
) -> Path:
    """Render one view of a GLB file with an optional material colour.

    The image is written to *output_path*.  Intermediate Blender output is
    placed in a temporary sibling directory to avoid collisions.
    """
    resolved_blender = resolve_blender_binary(blender_bin)
    render_script = blender_script_path()
    if not render_script.exists():
        raise RenderError(f"Blender helper script is missing: {render_script}")

    spec: dict[str, Any] = dict(DEFAULT_RENDER_SPEC)
    if spec_overrides:
        spec.update(spec_overrides)
    spec["views"] = [view]
    if base_color is not None:
        spec["base_color"] = base_color

    # Render into a dedicated temp directory so parallel calls don't collide.
    temp_dir = output_path.parent / f".render-tmp-{output_path.stem}"
    ensure_directory(temp_dir)
    command = [
        str(resolved_blender),
        "--background",
        "--factory-startup",
        "--python",
        str(render_script),
        "--",
        str(glb_path.resolve()),
        str(temp_dir.resolve()),
        json.dumps(spec),
    ]
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        raise RenderError(
            f"Single-view render failed for {glb_path.name}:\n"
            f"STDERR:\n{process.stderr}"
        )
    rendered = temp_dir / f"{view}.png"
    if not rendered.exists():
        raise RenderError(f"Blender did not produce expected view: {rendered}")
    import shutil as _shutil

    _shutil.move(str(rendered), str(output_path))
    _shutil.rmtree(temp_dir, ignore_errors=True)
    return output_path


def compose_compare_sheet(
    image_paths: dict[str, Path],
    output_path: Path,
    cell_width: int,
    cell_height: int,
) -> Path:
    """Compose individual diff renders into a labelled comparison sheet.

    Layout: up to 3 columns × 2 rows.  Row 1 = LEFT, RIGHT, SHARED.
    Row 2 = LEFT ONLY, RIGHT ONLY.  Cells for zero-volume pieces are
    rendered as light grey placeholders.
    """
    ordered = ["left", "right", "shared", "left_only", "right_only"]
    columns = 3
    rows = 2
    banner_h = 36
    canvas_w = cell_width * columns
    canvas_h = (cell_height + banner_h) * rows
    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(235, 235, 235))
    draw = ImageDraw.Draw(canvas)

    for index, role in enumerate(ordered):
        col = index % columns
        row = index // columns
        x = col * cell_width
        y = row * (cell_height + banner_h)

        # Banner
        banner_color = COMPARE_BANNER_COLORS.get(role, (100, 100, 100))
        draw.rectangle((x, y, x + cell_width, y + banner_h), fill=banner_color)
        label = COMPARE_LABELS.get(role, role.upper())
        draw.text((x + 14, y + 9), label, fill=(255, 255, 255))

        # Image or placeholder
        img_y = y + banner_h
        if role in image_paths and image_paths[role].exists():
            img = Image.open(image_paths[role]).convert("RGB")
            img = img.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
            canvas.paste(img, (x, img_y))
        else:
            draw.rectangle((x, img_y, x + cell_width, img_y + cell_height), fill=(215, 215, 215))
            draw.text(
                (x + cell_width // 2 - 30, img_y + cell_height // 2 - 8),
                "empty",
                fill=(160, 160, 160),
            )

    canvas.save(output_path)
    return output_path


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
