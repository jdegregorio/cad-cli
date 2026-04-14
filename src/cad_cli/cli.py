"""Command-line interface for cad-cli."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, NoReturn

from .build import run_build
from .compare import run_compare
from .errors import CadCliError, InputError
from .inspect import (
    inspect_bbox,
    inspect_center_distance,
    inspect_holes,
    inspect_summary,
    inspect_thickness,
    inspect_volume,
)
from .package import run_package
from .render import run_render
from .schemas import to_jsonable


class CadArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InputError(message)


# --------------------------------------------------------------------------- #
# Shared help text fragments
# --------------------------------------------------------------------------- #

FORMAT_HELP = (
    "Output format for the stdout summary. 'text' prints a human-readable "
    "one-liner; 'json' emits the full structured result (schema_version=1) "
    "suitable for scripting. The JSON payload written to disk "
    "(*-metadata.json, compare-metrics.json, package-manifest.json) is "
    "identical regardless of this flag. Default: text."
)

BLENDER_RESOLUTION_NOTE = (
    "Blender is resolved in this order: (1) --blender-bin, "
    "(2) CAD_BLENDER_BIN environment variable, (3) `blender` on PATH."
)

TOP_LEVEL_DESCRIPTION = textwrap.dedent(
    """\
    cad-cli — a deterministic CAD command-line toolchain.

    Takes a Python model source through a reproducible pipeline:
    build → render → compare → inspect → package.

    Artifact conventions:
      • STEP (model.step)  — authoritative, exact CAD geometry
      • GLB  (model.glb)   — presentation artifact used for rendering
      • STL  (model.stl)   — optional mesh export for printing / mesh tools
      • *-metadata.json    — schema-versioned trace (inputs, args, tool versions)

    Every command that produces artifacts writes a machine-readable manifest
    (schema_version=1) alongside them so results stay scriptable and traceable.
    """
)

TOP_LEVEL_EPILOG = textwrap.dedent(
    """\
    Common workflows
    ----------------

      1. Build a model, render previews, and package the result:

           cad build examples/models/cube.py --output-dir out/build --emit-stl
           cad render out/build/model.glb   --output-dir out/render
           cad package --output out/review.zip \\
                       --build-dir out/build --render-dir out/render

      2. Compare two revisions of a model with a visual diff sheet:

           cad build my_model.py --output-dir out/a --set size=20
           cad build my_model.py --output-dir out/b --set size=22
           cad compare out/a/model.step out/b/model.step \\
                       --output-dir out/compare --align principal \\
                       --emit-diff-solids --render-diffs

      3. Inspect features on an exact STEP artifact:

           cad inspect summary         out/build/model.step
           cad inspect holes           out/build/model.step --format json
           cad inspect center-distance out/build/model.step \\
                       --feature-a hole-1 --feature-b hole-2
           cad inspect thickness       out/build/model.step \\
                       --point 0,0,0 --direction y

    Environment variables
    ---------------------
      CAD_BLENDER_BIN   Fallback Blender binary used by `cad render` and
                        `cad compare --render-diffs` when --blender-bin is
                        not provided.

    Per-command help
    ----------------
      cad <command> --help             e.g. `cad build --help`
      cad inspect <subcommand> --help  e.g. `cad inspect holes --help`

    Exit codes
    ----------
      0  success
      2  invalid input / CLI usage error
      3  missing external dependency (e.g. Blender)
      4  unsupported operation for the given input type
      5  geometry load / export failure
      6  render pipeline failure
      7  compare pipeline failure
      1  any other error
    """
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def emit_result(result: Any, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(to_jsonable(result), indent=2, sort_keys=True))
        return
    print(result.summary)


def parse_point(value: str) -> list[float]:
    parts = value.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "Points must be provided as three comma-separated numbers: x,y,z"
        )
    try:
        return [float(part) for part in parts]
    except ValueError as exc:  # pragma: no cover - argparse path
        raise argparse.ArgumentTypeError(
            "Point coordinates must be numeric (got non-numeric component in "
            f"'{value}')"
        ) from exc


def _add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help=FORMAT_HELP,
    )


# --------------------------------------------------------------------------- #
# Subparser builders
# --------------------------------------------------------------------------- #


def _add_build_parser(subparsers: argparse._SubParsersAction) -> None:
    description = textwrap.dedent(
        """\
        Build a Python model source into deterministic CAD artifacts.

        The model source must expose a callable (default name: `build_model`) with
        the signature:

            def build_model(params: dict, context) -> build123d.Shape

        The returned object must be a build123d shape, part, or compound
        (anything exposing bounding_box / center / faces / solids / volume).

        Outputs written to --output-dir:
          model.step            authoritative CAD geometry
          model.glb             presentation artifact used by `cad render`
          build-metadata.json   trace: source path, resolved params, CLI args,
                                tool versions, bounding box, volume
          model.stl             optional — only with --emit-stl
          source-snapshot.py    optional — only with --snapshot-source;
                                a verbatim copy of the source for archival
        """
    )
    epilog = textwrap.dedent(
        """\
        Examples:

          # Simplest case: build from an example model
          cad build examples/models/cube.py --output-dir out/build

          # Override a single param from the command line
          cad build my_model.py --output-dir out --set size=25

          # Combine a params file with CLI overrides, and emit STL for printing
          cad build plate.py --output-dir out \\
              --params defaults.json \\
              --set hole.diameter=6 \\
              --emit-stl --snapshot-source

          # Use a non-default entry point
          cad build my_model.py --output-dir out --callable build_variant_a
        """
    )
    build_parser = subparsers.add_parser(
        "build",
        help="Build a model source file into deterministic CAD artifacts",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    build_parser.add_argument(
        "model_path",
        type=Path,
        metavar="MODEL_PATH",
        help=(
            "Path to a Python file defining the model callable "
            "(default name: build_model). Resolved relative to the current "
            "working directory."
        ),
    )
    build_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        metavar="DIR",
        help=(
            "Directory where model.step, model.glb, build-metadata.json, and "
            "optional extras are written. Created if it does not exist."
        ),
    )
    build_parser.add_argument(
        "--params",
        type=Path,
        metavar="PATH",
        help=(
            "Path to a JSON file whose top-level object is passed as the "
            "`params` dict to the model callable. Keys here can be overridden "
            "by --set."
        ),
    )
    build_parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Override or add a single parameter. Repeatable. VALUE is parsed "
            "as JSON first (so numbers, booleans, null, arrays, and objects "
            "work) and falls back to a plain string if that fails. Dotted "
            "keys set nested values, e.g. --set hole.diameter=6 or "
            "--set translation=[5,0,0]."
        ),
    )
    build_parser.add_argument(
        "--callable",
        dest="callable_name",
        default="build_model",
        metavar="NAME",
        help=(
            "Name of the function inside MODEL_PATH to invoke. Use this to "
            "keep multiple variants in a single file. Default: build_model."
        ),
    )
    build_parser.add_argument(
        "--emit-stl",
        action="store_true",
        help=(
            "Also write model.stl alongside the STEP and GLB outputs. Useful "
            "for 3D printing workflows and mesh-based downstream tools."
        ),
    )
    build_parser.add_argument(
        "--snapshot-source",
        action="store_true",
        help=(
            "Copy MODEL_PATH into --output-dir as source-snapshot.py so the "
            "build directory is self-contained for archival or packaging."
        ),
    )
    _add_format_arg(build_parser)


def _add_render_parser(subparsers: argparse._SubParsersAction) -> None:
    description = textwrap.dedent(
        f"""\
        Render a GLB artifact into a deterministic set of verification preview
        images using Blender in background mode.

        Outputs written to --output-dir:
          front.png, back.png, left.png, right.png, top.png, bottom.png
                                 datum-oriented orthographic views
          iso.png                angled isometric view
          sheet.png              2×4 composite of all views, labelled
          render-metadata.json   trace: GLB input, Blender binary, render spec,
                                 CLI args, tool versions

        All views are auto-framed so the part is never clipped. A neutral
        verification shader with balanced fill lighting keeps top/bottom datum
        views visually consistent with the sides.

        {BLENDER_RESOLUTION_NOTE}
        """
    )
    epilog = textwrap.dedent(
        """\
        Examples:

          # Render with defaults (768×768, EEVEE, 32 samples)
          cad render out/build/model.glb --output-dir out/render

          # Use a custom render spec (width/height/samples/engine)
          cad render out/build/model.glb --output-dir out/render \\
              --spec render-spec.json

          # Point at a specific Blender install
          cad render out/build/model.glb --output-dir out/render \\
              --blender-bin /Applications/Blender.app/Contents/MacOS/Blender

          # Via environment variable (handy in CI)
          CAD_BLENDER_BIN=/usr/local/bin/blender \\
              cad render out/build/model.glb --output-dir out/render
        """
    )
    render_parser = subparsers.add_parser(
        "render",
        help="Render a GLB artifact into verification preview images",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    render_parser.add_argument(
        "glb_path",
        type=Path,
        metavar="GLB_PATH",
        help="Path to the .glb file to render (typically produced by `cad build`).",
    )
    render_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        metavar="DIR",
        help=(
            "Directory where the PNG previews, sheet.png, and "
            "render-metadata.json are written. Created if it does not exist."
        ),
    )
    render_parser.add_argument(
        "--spec",
        type=Path,
        metavar="PATH",
        help=(
            "Optional JSON file overriding the render spec. Recognized keys: "
            "width, height, samples, engine. Any key omitted keeps its default "
            "(width=768, height=768, samples=32, engine=BLENDER_EEVEE)."
        ),
    )
    render_parser.add_argument(
        "--blender-bin",
        type=Path,
        metavar="PATH",
        help=(
            "Explicit path to the Blender binary. If omitted, falls back to "
            "the CAD_BLENDER_BIN environment variable and then to `blender` "
            "on PATH."
        ),
    )
    _add_format_arg(render_parser)


def _add_compare_parser(subparsers: argparse._SubParsersAction) -> None:
    description = textwrap.dedent(
        f"""\
        Compare two geometry artifacts and emit scriptable metrics plus
        optional diff artifacts.

        Comparison mode is selected automatically from the input file types:
          exact           both inputs are STEP — exact solid booleans
          mesh_fallback   at least one input is GLB/STL — mesh booleans via
                          trimesh (requires a watertight mesh for volumes)

        Metrics written to --output-dir/compare-metrics.json (schema_version=1):
          mode, alignment, left_volume, right_volume, shared_volume,
          left_only_volume, right_only_volume, union_volume, overlap_ratio,
          notes.

        Alignment is always recorded separately from overlap metrics, so a
        translation- or principal-axis alignment cannot silently inflate
        overlap numbers.

        When --render-diffs is used: {BLENDER_RESOLUTION_NOTE}
        """
    )
    epilog = textwrap.dedent(
        """\
        Examples:

          # Simplest comparison, no alignment
          cad compare a/model.step b/model.step --output-dir out/compare

          # Align by principal axes (useful when B is rotated relative to A)
          cad compare a/model.step b/model.step --output-dir out/compare \\
              --align principal

          # Export the diff solids so you can re-inspect them downstream
          cad compare a/model.step b/model.step --output-dir out/compare \\
              --emit-diff-solids

          # Render a full visual diff sheet (implies --emit-diff-solids)
          cad compare a/model.step b/model.step --output-dir out/compare \\
              --render-diffs

          # Mesh-fallback comparison (labelled mode=mesh_fallback)
          cad compare old.glb new.glb --output-dir out/compare
        """
    )
    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare two geometry artifacts (exact STEP or mesh fallback)",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compare_parser.add_argument(
        "left_path",
        type=Path,
        metavar="LEFT_PATH",
        help=(
            "'Left' geometry artifact (STEP, GLB, or STL). Treated as the "
            "reference side: left_only_volume is material present in LEFT "
            "but not RIGHT."
        ),
    )
    compare_parser.add_argument(
        "right_path",
        type=Path,
        metavar="RIGHT_PATH",
        help=(
            "'Right' geometry artifact (STEP, GLB, or STL). right_only_volume "
            "is material present in RIGHT but not LEFT."
        ),
    )
    compare_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        metavar="DIR",
        help=(
            "Directory where compare-metrics.json is written, plus any "
            "optional diff solids (*.step) and rendered sheets (*.png)."
        ),
    )
    compare_parser.add_argument(
        "--align",
        choices=["none", "translate", "principal"],
        default="none",
        help=(
            "Alignment applied to RIGHT before the boolean comparison. "
            "'none' assumes coordinate systems already match. 'translate' "
            "aligns centers by translation only. 'principal' translates *and* "
            "rotates RIGHT so its principal axes match LEFT — useful when "
            "inputs share geometry but differ in orientation. Default: none."
        ),
    )
    compare_parser.add_argument(
        "--emit-diff-solids",
        action="store_true",
        help=(
            "Exact mode only. Also export shared.step, left_only.step, and "
            "right_only.step into --output-dir. Pieces with zero volume are "
            "skipped."
        ),
    )
    compare_parser.add_argument(
        "--render-diffs",
        action="store_true",
        help=(
            "Exact mode only. Render each diff piece through Blender and "
            "compose a labelled compare-sheet.png (LEFT, RIGHT, SHARED, "
            "LEFT ONLY, RIGHT ONLY). Implies --emit-diff-solids."
        ),
    )
    compare_parser.add_argument(
        "--blender-bin",
        type=Path,
        metavar="PATH",
        help=(
            "Explicit Blender binary path, used only with --render-diffs. "
            "Falls back to CAD_BLENDER_BIN and then to `blender` on PATH."
        ),
    )
    compare_parser.add_argument(
        "--render-spec",
        type=Path,
        metavar="PATH",
        help=(
            "Optional JSON render spec used for diff renders. Same shape as "
            "`cad render --spec` (width, height, samples, engine). Only "
            "meaningful with --render-diffs."
        ),
    )
    _add_format_arg(compare_parser)


def _add_inspect_parser(subparsers: argparse._SubParsersAction) -> None:
    description = textwrap.dedent(
        """\
        Inspect a single geometry artifact.

        STEP inputs are analyzed as exact CAD solids (richest feature support).
        GLB/STL inputs fall back to mesh analysis — queries that require exact
        features (holes, center-distance) fail with a clear error rather than
        silently guessing.

        Subcommands:
          summary           key dimensions, volume, counts, and hole list
          bbox              bounding box (min, max, size)
          volume            signed volume (null for non-watertight meshes)
          holes             cylindrical through-hole features (STEP only)
          center-distance   center-to-center distance between two named holes
                            (STEP only)
          thickness         thickness at a point along one of the x/y/z axes

        Run `cad inspect <subcommand> --help` for the details of each one.
        """
    )
    epilog = textwrap.dedent(
        """\
        Examples:

          cad inspect summary         out/build/model.step
          cad inspect bbox            out/build/model.step --format json
          cad inspect volume          out/build/model.glb
          cad inspect holes           out/build/model.step --format json
          cad inspect center-distance out/build/model.step \\
              --feature-a hole-1 --feature-b hole-2
          cad inspect thickness       out/build/model.step \\
              --point 0,9,0 --direction y
        """
    )
    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a single artifact (summary, bbox, volume, holes, …)",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    inspect_subparsers = inspect_parser.add_subparsers(
        dest="inspect_command",
        required=True,
        metavar="SUBCOMMAND",
    )

    # --- summary ----------------------------------------------------------- #
    summary_parser = inspect_subparsers.add_parser(
        "summary",
        help="Show deterministic summary metrics (size, volume, counts, holes)",
        description=textwrap.dedent(
            """\
            Print a deterministic summary of an artifact.

            For STEP inputs: bounding box, dimensions, volume, face/edge/solid
            counts, and the list of cylindrical hole features.

            For GLB/STL inputs: bounding box, dimensions, volume (if the mesh
            is watertight), face/vertex counts, plus a note that feature
            extraction is limited.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    summary_parser.add_argument(
        "artifact_path",
        type=Path,
        metavar="ARTIFACT_PATH",
        help="Path to a STEP, GLB, or STL file to summarize.",
    )
    _add_format_arg(summary_parser)

    # --- bbox -------------------------------------------------------------- #
    bbox_parser = inspect_subparsers.add_parser(
        "bbox",
        help="Show bounding box (min, max, size)",
        description=(
            "Print the axis-aligned bounding box (min, max, size) of a STEP, "
            "GLB, or STL artifact."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    bbox_parser.add_argument(
        "artifact_path",
        type=Path,
        metavar="ARTIFACT_PATH",
        help="Path to a STEP, GLB, or STL file.",
    )
    _add_format_arg(bbox_parser)

    # --- volume ------------------------------------------------------------ #
    volume_parser = inspect_subparsers.add_parser(
        "volume",
        help="Show artifact volume",
        description=textwrap.dedent(
            """\
            Print the volume of an artifact.

            STEP inputs return the exact CAD volume. Mesh inputs return the
            signed volume only when the mesh is watertight; non-watertight
            meshes report null instead of a misleading number.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    volume_parser.add_argument(
        "artifact_path",
        type=Path,
        metavar="ARTIFACT_PATH",
        help="Path to a STEP, GLB, or STL file.",
    )
    _add_format_arg(volume_parser)

    # --- holes ------------------------------------------------------------- #
    holes_parser = inspect_subparsers.add_parser(
        "holes",
        help="List cylindrical hole features (STEP only)",
        description=textwrap.dedent(
            """\
            List cylindrical through-hole features of a STEP artifact. Each
            hole is reported with a stable id (`hole-1`, `hole-2`, …), axis,
            center point, and diameter. These ids are the values you pass to
            `cad inspect center-distance --feature-a / --feature-b`.

            Requires an exact STEP input. Mesh inputs (GLB/STL) are rejected
            with a clear error instead of guessing.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    holes_parser.add_argument(
        "artifact_path",
        type=Path,
        metavar="ARTIFACT_PATH",
        help="Path to a STEP file.",
    )
    _add_format_arg(holes_parser)

    # --- center-distance --------------------------------------------------- #
    center_parser = inspect_subparsers.add_parser(
        "center-distance",
        help="Compute center distance between two cylindrical features (STEP only)",
        description=textwrap.dedent(
            """\
            Compute the shortest distance between the axes of two cylindrical
            features (typically holes) in a STEP artifact.

            Feature ids come from `cad inspect holes`. Requires an exact STEP
            input.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    center_parser.add_argument(
        "artifact_path",
        type=Path,
        metavar="ARTIFACT_PATH",
        help="Path to a STEP file.",
    )
    center_parser.add_argument(
        "--feature-a",
        required=True,
        metavar="ID",
        help=(
            "Id of the first cylindrical feature (e.g. `hole-1`). Discover "
            "ids with `cad inspect holes`."
        ),
    )
    center_parser.add_argument(
        "--feature-b",
        required=True,
        metavar="ID",
        help="Id of the second cylindrical feature (e.g. `hole-2`).",
    )
    _add_format_arg(center_parser)

    # --- thickness --------------------------------------------------------- #
    thickness_parser = inspect_subparsers.add_parser(
        "thickness",
        help="Probe thickness at a point along the x/y/z axis",
        description=textwrap.dedent(
            """\
            Probe the material thickness of an artifact by casting a ray from
            a given point along one of the principal axes (x, y, or z) and
            measuring the enter/exit distance through solid material.

            STEP inputs use exact CAD ray casting. Mesh inputs use a trimesh
            ray cast and may require the optional `rtree` dependency for best
            accuracy; STEP remains the preferred authoritative input.
            """
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    thickness_parser.add_argument(
        "artifact_path",
        type=Path,
        metavar="ARTIFACT_PATH",
        help="Path to a STEP, GLB, or STL file.",
    )
    thickness_parser.add_argument(
        "--point",
        required=True,
        type=parse_point,
        metavar="X,Y,Z",
        help=(
            "Starting point of the probe as three comma-separated numbers in "
            "the artifact's coordinate system, e.g. `0,9,0`."
        ),
    )
    thickness_parser.add_argument(
        "--direction",
        choices=["x", "y", "z"],
        required=True,
        help=(
            "Principal axis along which to probe. The ray is cast in the "
            "positive direction of the chosen axis."
        ),
    )
    _add_format_arg(thickness_parser)


def _add_package_parser(subparsers: argparse._SubParsersAction) -> None:
    description = textwrap.dedent(
        """\
        Collect build, render, compare, and extra outputs into a single zip
        archive, plus a hashed JSON manifest.

        Inside the archive, files are grouped by role:
          build/      contents of --build-dir
          render/     contents of --render-dir
          compare/    contents of --compare-dir
          extra/      contents of each --include path

        package-manifest.json is written next to the output zip *and* embedded
        inside it. Each entry records: role, source path, archive path,
        sha256, and size_bytes — everything needed to audit the bundle.

        At least one of --build-dir, --render-dir, --compare-dir, or --include
        must be provided.
        """
    )
    epilog = textwrap.dedent(
        """\
        Examples:

          # Bundle a build + render pair
          cad package --output out/bundle.zip \\
              --build-dir out/build --render-dir out/render

          # Include compare outputs and extra files for a review package
          cad package --output out/review.zip \\
              --build-dir out/build \\
              --render-dir out/render \\
              --compare-dir out/compare \\
              --include NOTES.md \\
              --include screenshots/
        """
    )
    package_parser = subparsers.add_parser(
        "package",
        help="Collect outputs into a hashed zip bundle with a JSON manifest",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    package_parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        required=True,
        metavar="PATH",
        help=(
            "Path to the output .zip archive. Its parent directory is created "
            "if it does not exist. package-manifest.json is written alongside."
        ),
    )
    package_parser.add_argument(
        "--build-dir",
        type=Path,
        metavar="DIR",
        help=(
            "Directory of build artifacts to include under `build/` in the "
            "archive (typically the --output-dir from `cad build`)."
        ),
    )
    package_parser.add_argument(
        "--render-dir",
        type=Path,
        metavar="DIR",
        help=(
            "Directory of render artifacts to include under `render/` "
            "(typically the --output-dir from `cad render`)."
        ),
    )
    package_parser.add_argument(
        "--compare-dir",
        type=Path,
        metavar="DIR",
        help=(
            "Directory of compare artifacts to include under `compare/` "
            "(typically the --output-dir from `cad compare`)."
        ),
    )
    package_parser.add_argument(
        "--include",
        dest="includes",
        type=Path,
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "Additional file or directory to include under `extra/`. "
            "Repeatable. Directories are included recursively."
        ),
    )
    _add_format_arg(package_parser)


def build_parser() -> CadArgumentParser:
    parser = CadArgumentParser(
        prog="cad",
        description=TOP_LEVEL_DESCRIPTION,
        epilog=TOP_LEVEL_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar="COMMAND",
    )
    _add_build_parser(subparsers)
    _add_render_parser(subparsers)
    _add_compare_parser(subparsers)
    _add_inspect_parser(subparsers)
    _add_package_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(raw_args)
        result: Any
        if args.command == "build":
            result = run_build(
                model_path=args.model_path,
                output_dir=args.output_dir,
                params_path=args.params,
                overrides=args.overrides,
                callable_name=args.callable_name,
                emit_stl=args.emit_stl,
                snapshot_source=args.snapshot_source,
                raw_args=raw_args,
            )
            emit_result(result, args.format)
            return 0
        if args.command == "render":
            result = run_render(
                glb_path=args.glb_path,
                output_dir=args.output_dir,
                spec_path=args.spec,
                blender_bin=args.blender_bin,
                raw_args=raw_args,
            )
            emit_result(result, args.format)
            return 0
        if args.command == "compare":
            result = run_compare(
                left_path=args.left_path,
                right_path=args.right_path,
                output_dir=args.output_dir,
                alignment=args.align,
                emit_diff_solids=args.emit_diff_solids,
                render_diffs=args.render_diffs,
                blender_bin=args.blender_bin,
                render_spec_path=args.render_spec,
            )
            emit_result(result, args.format)
            return 0
        if args.command == "inspect":
            inspect_command = args.inspect_command
            if inspect_command == "summary":
                result = inspect_summary(args.artifact_path)
            elif inspect_command == "bbox":
                result = inspect_bbox(args.artifact_path)
            elif inspect_command == "volume":
                result = inspect_volume(args.artifact_path)
            elif inspect_command == "holes":
                result = inspect_holes(args.artifact_path)
            elif inspect_command == "center-distance":
                result = inspect_center_distance(
                    args.artifact_path, args.feature_a, args.feature_b
                )
            elif inspect_command == "thickness":
                result = inspect_thickness(args.artifact_path, args.point, args.direction)
            else:  # pragma: no cover - argparse enforces this
                raise InputError(f"Unknown inspect subcommand: {inspect_command}")
            emit_result(result, args.format)
            return 0
        if args.command == "package":
            result = run_package(
                output_path=args.output_path,
                build_dir=args.build_dir,
                render_dir=args.render_dir,
                compare_dir=args.compare_dir,
                includes=args.includes,
            )
            emit_result(result, args.format)
            return 0
        raise InputError(f"Unknown command: {args.command}")
    except CadCliError as exc:
        print(exc.message, file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
