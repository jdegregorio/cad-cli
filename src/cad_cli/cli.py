"""Command-line interface for cad-cli."""

from __future__ import annotations

import argparse
import json
import sys
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


def emit_result(result: Any, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(to_jsonable(result), indent=2, sort_keys=True))
        return
    print(result.summary)


def parse_point(value: str) -> list[float]:
    parts = value.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Points must be provided as x,y,z")
    try:
        return [float(part) for part in parts]
    except ValueError as exc:  # pragma: no cover - argparse path
        raise argparse.ArgumentTypeError("Point coordinates must be numeric") from exc


def build_parser() -> CadArgumentParser:
    parser = CadArgumentParser(prog="cad", description="Deterministic CAD CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser(
        "build", help="Build a model source into deterministic artifacts"
    )
    build_parser.add_argument("model_path", type=Path)
    build_parser.add_argument("--output-dir", type=Path, required=True)
    build_parser.add_argument("--params", type=Path)
    build_parser.add_argument("--set", dest="overrides", action="append", default=[])
    build_parser.add_argument("--callable", dest="callable_name", default="build_model")
    build_parser.add_argument("--emit-stl", action="store_true")
    build_parser.add_argument("--snapshot-source", action="store_true")
    build_parser.add_argument("--format", choices=["text", "json"], default="text")

    render_parser = subparsers.add_parser("render", help="Render a GLB artifact through Blender")
    render_parser.add_argument("glb_path", type=Path)
    render_parser.add_argument("--output-dir", type=Path, required=True)
    render_parser.add_argument("--spec", type=Path)
    render_parser.add_argument("--blender-bin", type=Path)
    render_parser.add_argument("--format", choices=["text", "json"], default="text")

    compare_parser = subparsers.add_parser("compare", help="Compare two geometry artifacts")
    compare_parser.add_argument("left_path", type=Path)
    compare_parser.add_argument("right_path", type=Path)
    compare_parser.add_argument("--output-dir", type=Path, required=True)
    compare_parser.add_argument(
        "--align", choices=["none", "translate", "principal"], default="none"
    )
    compare_parser.add_argument("--emit-diff-solids", action="store_true")
    compare_parser.add_argument("--format", choices=["text", "json"], default="text")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a single artifact")
    inspect_subparsers = inspect_parser.add_subparsers(dest="inspect_command", required=True)

    summary_parser = inspect_subparsers.add_parser(
        "summary", help="Show deterministic summary metrics"
    )
    summary_parser.add_argument("artifact_path", type=Path)
    summary_parser.add_argument("--format", choices=["text", "json"], default="text")

    bbox_parser = inspect_subparsers.add_parser("bbox", help="Show bounding box and dimensions")
    bbox_parser.add_argument("artifact_path", type=Path)
    bbox_parser.add_argument("--format", choices=["text", "json"], default="text")

    volume_parser = inspect_subparsers.add_parser("volume", help="Show artifact volume")
    volume_parser.add_argument("artifact_path", type=Path)
    volume_parser.add_argument("--format", choices=["text", "json"], default="text")

    holes_parser = inspect_subparsers.add_parser("holes", help="List cylindrical hole features")
    holes_parser.add_argument("artifact_path", type=Path)
    holes_parser.add_argument("--format", choices=["text", "json"], default="text")

    center_parser = inspect_subparsers.add_parser(
        "center-distance", help="Compute center distance between two cylindrical features"
    )
    center_parser.add_argument("artifact_path", type=Path)
    center_parser.add_argument("--feature-a", required=True)
    center_parser.add_argument("--feature-b", required=True)
    center_parser.add_argument("--format", choices=["text", "json"], default="text")

    thickness_parser = inspect_subparsers.add_parser(
        "thickness", help="Probe thickness along a principal axis"
    )
    thickness_parser.add_argument("artifact_path", type=Path)
    thickness_parser.add_argument("--point", required=True, type=parse_point)
    thickness_parser.add_argument("--direction", choices=["x", "y", "z"], required=True)
    thickness_parser.add_argument("--format", choices=["text", "json"], default="text")

    package_parser = subparsers.add_parser("package", help="Collect outputs into a zip bundle")
    package_parser.add_argument("--output", dest="output_path", type=Path, required=True)
    package_parser.add_argument("--build-dir", type=Path)
    package_parser.add_argument("--render-dir", type=Path)
    package_parser.add_argument("--compare-dir", type=Path)
    package_parser.add_argument(
        "--include", dest="includes", type=Path, action="append", default=[]
    )
    package_parser.add_argument("--format", choices=["text", "json"], default="text")

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
