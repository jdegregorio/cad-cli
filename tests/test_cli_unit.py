from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cad_cli.cli import build_parser, main
from cad_cli.compare import _overlap_ratio, _safe_volume_exact, _safe_volume_mesh
from cad_cli.errors import InputError
from cad_cli.schemas import CompareMetrics, CompareResult, to_jsonable


def test_parser_requires_subcommand() -> None:
    parser = build_parser()
    try:
        parser.parse_args([])
    except Exception as exc:  # noqa: BLE001
        assert "required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected parser failure without a subcommand")


def test_main_returns_input_error_for_missing_model() -> None:
    exit_code = main(["build", "missing.py", "--output-dir", "out"])
    assert exit_code == 2


def test_main_json_output_for_helpful_command(tmp_path, capsys, examples_dir) -> None:
    output_dir = tmp_path / "build"
    exit_code = main(
        [
            "build",
            str(examples_dir / "box.py"),
            "--output-dir",
            str(output_dir),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["command"] == "build"
    assert payload["schema_version"] == 1


def test_build_python_flag_parses_into_path(examples_dir) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "build",
            str(examples_dir / "box.py"),
            "--output-dir",
            "out",
            "--python",
            "/usr/local/bin/python",
        ]
    )
    assert isinstance(args.python_path, Path)
    assert str(args.python_path) == "/usr/local/bin/python"


def test_build_python_flag_default_is_none(examples_dir) -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["build", str(examples_dir / "box.py"), "--output-dir", "out"]
    )
    assert args.python_path is None


def test_build_python_missing_interpreter_returns_input_error(
    tmp_path, examples_dir
) -> None:
    output_dir = tmp_path / "build"
    exit_code = main(
        [
            "build",
            str(examples_dir / "box.py"),
            "--output-dir",
            str(output_dir),
            "--python",
            str(tmp_path / "no-such-python"),
        ]
    )
    assert exit_code == 2


def test_build_python_subprocess_produces_artifacts(tmp_path, examples_dir) -> None:
    """End-to-end check: passing --python <current interpreter> still builds."""
    output_dir = tmp_path / "build"
    exit_code = main(
        [
            "build",
            str(examples_dir / "box.py"),
            "--output-dir",
            str(output_dir),
            "--python",
            sys.executable,
            "--emit-stl",
        ]
    )
    assert exit_code == 0
    assert (output_dir / "model.step").exists()
    assert (output_dir / "model.glb").exists()
    assert (output_dir / "model.stl").exists()
    metadata = json.loads((output_dir / "build-metadata.json").read_text())
    assert metadata["volume"] == 6000.0


# ---------------------------------------------------------------------------
# Error reporting: structured JSON error shape on stderr
# ---------------------------------------------------------------------------


def _write_raising_model(tmp_path: Path, body: str) -> Path:
    model = tmp_path / "broken.py"
    model.write_text(body)
    return model


def test_error_json_shape_on_callable_exception(tmp_path, capsys) -> None:
    model = _write_raising_model(
        tmp_path,
        "def build_model(params, context):\n"
        "    raise ValueError('bad geometry input')\n",
    )
    exit_code = main(
        [
            "build",
            str(model),
            "--output-dir",
            str(tmp_path / "out"),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 5  # GeometryError
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert set(payload["error"].keys()) == {
        "type",
        "message",
        "traceback",
        "cause",
        "exit_code",
    }
    assert payload["error"]["type"] == "GeometryError"
    assert payload["error"]["exit_code"] == 5
    assert "ValueError" in payload["error"]["message"]
    assert "bad geometry input" in payload["error"]["message"]
    assert payload["error"]["cause"] == {
        "type": "ValueError",
        "message": "bad geometry input",
    }
    tb = payload["error"]["traceback"]
    assert tb is not None
    assert "ValueError: bad geometry input" in tb
    assert "build_model" in tb


def test_error_json_shape_on_import_failure(tmp_path, capsys) -> None:
    model = _write_raising_model(
        tmp_path,
        "import does_not_exist_xyz  # noqa: F401\n"
        "def build_model(params, context):\n"
        "    return None\n",
    )
    exit_code = main(
        [
            "build",
            str(model),
            "--output-dir",
            str(tmp_path / "out"),
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2  # InputError
    payload = json.loads(captured.err)
    assert payload["error"]["type"] == "InputError"
    assert payload["error"]["cause"]["type"] == "ModuleNotFoundError"
    assert "does_not_exist_xyz" in payload["error"]["traceback"]


def test_error_text_format_keeps_one_line_message(tmp_path, capsys) -> None:
    model = _write_raising_model(
        tmp_path,
        "def build_model(params, context):\n"
        "    raise RuntimeError('boom')\n",
    )
    exit_code = main(
        [
            "build",
            str(model),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 5
    # First line is the human-readable message; traceback follows for debugging.
    first_line = captured.err.splitlines()[0]
    assert "RuntimeError" in first_line
    assert "boom" in first_line
    # Stderr is not parseable as JSON in text mode.
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.err)


def test_error_json_shape_for_input_error_without_traceback(capsys) -> None:
    # Missing model triggers InputError raised directly (no chained exception).
    exit_code = main(
        [
            "build",
            "definitely_missing.py",
            "--output-dir",
            "out",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    payload = json.loads(captured.err)
    assert payload["error"]["type"] == "InputError"
    assert payload["error"]["traceback"] is None
    assert payload["error"]["cause"] is None
    assert "definitely_missing.py" in payload["error"]["message"]


# ---------------------------------------------------------------------------
# Unit tests for compare helper functions
# ---------------------------------------------------------------------------


class TestSafeVolumeExact:
    def test_normal_volume(self) -> None:
        shape = MagicMock()
        shape.volume = 42.5
        assert _safe_volume_exact(shape) == 42.5

    def test_zero_volume(self) -> None:
        shape = MagicMock()
        shape.volume = 0.0
        assert _safe_volume_exact(shape) == 0.0

    def test_none_volume_attribute(self) -> None:
        shape = MagicMock()
        shape.volume = None
        assert _safe_volume_exact(shape) == 0.0

    def test_missing_volume_attribute(self) -> None:
        shape = MagicMock(spec=[])
        assert _safe_volume_exact(shape) == 0.0


class TestSafeVolumeMesh:
    def test_valid_volume_mesh(self) -> None:
        mesh = MagicMock()
        mesh.is_volume = True
        mesh.volume = 100.0
        assert _safe_volume_mesh(mesh) == 100.0

    def test_non_volume_mesh_returns_none(self) -> None:
        mesh = MagicMock()
        mesh.is_volume = False
        assert _safe_volume_mesh(mesh) is None


class TestOverlapRatio:
    def test_normal_ratio(self) -> None:
        assert _overlap_ratio(50.0, 100.0) == 0.5

    def test_full_overlap(self) -> None:
        assert _overlap_ratio(100.0, 100.0) == 1.0

    def test_shared_none(self) -> None:
        assert _overlap_ratio(None, 100.0) is None

    def test_union_none(self) -> None:
        assert _overlap_ratio(50.0, None) is None

    def test_both_none(self) -> None:
        assert _overlap_ratio(None, None) is None

    def test_zero_union(self) -> None:
        assert _overlap_ratio(0.0, 0.0) is None

    def test_negative_union(self) -> None:
        assert _overlap_ratio(10.0, -1.0) is None


# ---------------------------------------------------------------------------
# Unit tests for compare CLI argument parsing
# ---------------------------------------------------------------------------


class TestCompareArgParsing:
    def test_compare_required_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["compare", "left.step", "right.step", "--output-dir", "out"]
        )
        assert args.command == "compare"
        assert str(args.left_path) == "left.step"
        assert str(args.right_path) == "right.step"
        assert str(args.output_dir) == "out"
        assert args.align == "none"
        assert args.emit_diff_solids is False
        assert args.render_diffs is False
        assert args.blender_bin is None
        assert args.render_spec is None
        assert args.format == "text"

    def test_compare_all_options(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "compare",
                "a.step",
                "b.step",
                "--output-dir",
                "cmp",
                "--align",
                "principal",
                "--emit-diff-solids",
                "--render-diffs",
                "--blender-bin",
                "/usr/bin/blender",
                "--render-spec",
                "spec.json",
                "--format",
                "json",
            ]
        )
        assert args.align == "principal"
        assert args.emit_diff_solids is True
        assert args.render_diffs is True
        assert str(args.blender_bin) == "/usr/bin/blender"
        assert str(args.render_spec) == "spec.json"
        assert args.format == "json"

    def test_compare_align_choices(self) -> None:
        parser = build_parser()
        for choice in ("none", "translate", "principal"):
            args = parser.parse_args(
                ["compare", "l.step", "r.step", "--output-dir", "o", "--align", choice]
            )
            assert args.align == choice

    def test_compare_invalid_align_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(InputError):
            parser.parse_args(
                ["compare", "l.step", "r.step", "--output-dir", "o", "--align", "invalid"]
            )

    def test_compare_missing_output_dir_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(InputError):
            parser.parse_args(["compare", "l.step", "r.step"])


# ---------------------------------------------------------------------------
# Unit tests for CompareMetrics / CompareResult schema serialization
# ---------------------------------------------------------------------------


class TestCompareSchemas:
    def test_compare_metrics_to_jsonable(self) -> None:
        metrics = CompareMetrics(
            mode="exact",
            alignment="none",
            left_volume=100.0,
            right_volume=100.0,
            shared_volume=100.0,
            left_only_volume=0.0,
            right_only_volume=0.0,
            union_volume=100.0,
            overlap_ratio=1.0,
            notes=["alignment=none"],
        )
        data = to_jsonable(metrics)
        assert data["mode"] == "exact"
        assert data["overlap_ratio"] == 1.0
        assert isinstance(data["notes"], list)

    def test_compare_result_to_jsonable(self) -> None:
        metrics = CompareMetrics(
            mode="mesh_fallback",
            alignment="translate",
            left_volume=50.0,
            right_volume=60.0,
            shared_volume=None,
            left_only_volume=None,
            right_only_volume=None,
            union_volume=None,
            overlap_ratio=None,
        )
        result = CompareResult(
            command="compare",
            summary="test",
            left_path="/a.glb",
            right_path="/b.glb",
            output_dir="/out",
            metrics_path="/out/compare-metrics.json",
            metrics=metrics,
            artifacts=[],
        )
        data = to_jsonable(result)
        assert data["schema_version"] == 1
        assert data["status"] == "ok"
        assert data["command"] == "compare"
        assert data["metrics"]["mode"] == "mesh_fallback"
        assert data["metrics"]["overlap_ratio"] is None

    def test_compare_result_json_serializable(self) -> None:
        metrics = CompareMetrics(
            mode="exact",
            alignment="principal",
            left_volume=10.0,
            right_volume=10.0,
            shared_volume=10.0,
            left_only_volume=0.0,
            right_only_volume=0.0,
            union_volume=10.0,
            overlap_ratio=1.0,
        )
        result = CompareResult(
            command="compare",
            summary="ok",
            left_path="/l",
            right_path="/r",
            output_dir="/o",
            metrics_path="/o/m.json",
            metrics=metrics,
            artifacts=[],
        )
        json_str = json.dumps(to_jsonable(result))
        roundtrip = json.loads(json_str)
        assert roundtrip["metrics"]["overlap_ratio"] == 1.0


# ---------------------------------------------------------------------------
# Unit tests for compare error paths via CLI main()
# ---------------------------------------------------------------------------


class TestCompareErrorPaths:
    def test_missing_left_file(self, tmp_path) -> None:
        exit_code = main(
            [
                "compare",
                str(tmp_path / "nonexistent.step"),
                str(tmp_path / "also_missing.step"),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        assert exit_code == 2

    def test_unsupported_file_extension(self, tmp_path) -> None:
        bad_file = tmp_path / "model.xyz"
        bad_file.write_text("not a model")
        exit_code = main(
            [
                "compare",
                str(bad_file),
                str(bad_file),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        assert exit_code == 2


# ---------------------------------------------------------------------------
# Unit tests for compose_compare_sheet (PIL compositing, no Blender)
# ---------------------------------------------------------------------------


class TestComposeCompareSheet:
    def test_compose_with_all_images(self, tmp_path) -> None:
        from PIL import Image as PILImage

        from cad_cli.render import compose_compare_sheet

        # Create small dummy images for each role.
        image_paths: dict[str, Path] = {}
        for role in ("left", "right", "shared", "left_only", "right_only"):
            img = PILImage.new("RGB", (64, 64), color=(128, 128, 128))
            path = tmp_path / f"{role}.png"
            img.save(path)
            image_paths[role] = path
        out = tmp_path / "sheet.png"
        result = compose_compare_sheet(image_paths, out, 64, 64)
        assert result == out
        assert out.exists()
        sheet = PILImage.open(out)
        # 3 columns × 2 rows, each cell is 64 wide, 64+36 (banner) tall
        assert sheet.size == (64 * 3, (64 + 36) * 2)

    def test_compose_with_missing_roles(self, tmp_path) -> None:
        from PIL import Image as PILImage

        from cad_cli.render import compose_compare_sheet

        # Only left and right, no diffs.
        image_paths: dict[str, Path] = {}
        for role in ("left", "right"):
            img = PILImage.new("RGB", (64, 64), color=(128, 128, 128))
            path = tmp_path / f"{role}.png"
            img.save(path)
            image_paths[role] = path
        out = tmp_path / "sheet.png"
        result = compose_compare_sheet(image_paths, out, 64, 64)
        assert result.exists()
        sheet = PILImage.open(out)
        assert sheet.size == (64 * 3, (64 + 36) * 2)
