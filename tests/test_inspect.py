from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from conftest import run_cad


def build_fixture(tmp_path: Path, examples_dir: Path, model_name: str) -> Path:
    build_dir = tmp_path / Path(model_name).stem
    build = run_cad(
        "build",
        str(examples_dir / model_name),
        "--output-dir",
        str(build_dir),
        "--emit-stl",
        "--format",
        "json",
    )
    assert build.returncode == 0, build.stderr
    return build_dir


def test_inspect_exact_summary_bbox_volume_contract(
    tmp_path: Path, examples_dir: Path
) -> None:
    build_dir = build_fixture(tmp_path, examples_dir, "box.py")

    summary = run_cad("inspect", "summary", str(build_dir / "model.step"), "--format", "json")
    bbox = run_cad("inspect", "bbox", str(build_dir / "model.step"), "--format", "json")
    volume = run_cad("inspect", "volume", str(build_dir / "model.step"), "--format", "json")

    assert summary.returncode == 0, summary.stderr
    assert bbox.returncode == 0, bbox.stderr
    assert volume.returncode == 0, volume.stderr

    summary_payload = json.loads(summary.stdout)
    bbox_payload = json.loads(bbox.stdout)
    volume_payload = json.loads(volume.stdout)

    assert summary_payload["command"] == "inspect summary"
    assert summary_payload["mode"] == "exact"
    assert summary_payload["schema_version"] == 1
    assert summary_payload["data"]["dimensions"] == [10.0, 20.0, 30.0]
    assert summary_payload["data"]["bounding_box"]["size"] == [10.0, 20.0, 30.0]
    assert summary_payload["data"]["volume"] == 6000.0
    assert summary_payload["data"]["solid_count"] == 1
    assert summary_payload["data"]["holes"] == []

    assert bbox_payload["data"]["dimensions"] == [10.0, 20.0, 30.0]
    assert bbox_payload["data"]["bounding_box"]["min_corner"] == [-5.0, -10.0, -15.0]
    assert bbox_payload["data"]["bounding_box"]["max_corner"] == [5.0, 10.0, 15.0]

    assert volume_payload["data"]["volume"] == 6000.0


def test_inspect_mesh_summary_and_volume_contract(
    tmp_path: Path, examples_dir: Path
) -> None:
    build_dir = build_fixture(tmp_path, examples_dir, "box.py")

    summary = run_cad("inspect", "summary", str(build_dir / "model.glb"), "--format", "json")
    bbox = run_cad("inspect", "bbox", str(build_dir / "model.glb"), "--format", "json")
    volume = run_cad("inspect", "volume", str(build_dir / "model.glb"), "--format", "json")
    text_volume = run_cad("inspect", "volume", str(build_dir / "model.glb"))

    assert summary.returncode == 0, summary.stderr
    assert bbox.returncode == 0, bbox.stderr
    assert volume.returncode == 0, volume.stderr
    assert text_volume.returncode == 0, text_volume.stderr

    summary_payload = json.loads(summary.stdout)
    bbox_payload = json.loads(bbox.stdout)
    volume_payload = json.loads(volume.stdout)

    assert summary_payload["mode"] == "mesh"
    assert summary_payload["schema_version"] == 1
    assert (
        "Mesh fallback summary; feature extraction is limited."
        in summary_payload["data"]["notes"]
    )
    assert summary_payload["data"]["face_count"] > 0
    assert summary_payload["data"]["vertex_count"] > 0
    assert len(summary_payload["data"]["dimensions"]) == 3
    assert all(value > 0 for value in summary_payload["data"]["dimensions"])

    assert bbox_payload["mode"] == "mesh"
    assert len(bbox_payload["data"]["bounding_box"]["size"]) == 3
    assert all(value > 0 for value in bbox_payload["data"]["bounding_box"]["size"])

    assert "volume" in volume_payload["data"]
    assert text_volume.stdout.strip() == "Computed volume for model.glb"


def test_inspect_exact_failure_paths(tmp_path: Path, examples_dir: Path) -> None:
    build_dir = build_fixture(tmp_path, examples_dir, "hole_plate.py")

    missing_feature = run_cad(
        "inspect",
        "center-distance",
        str(build_dir / "model.step"),
        "--feature-a",
        "hole-1",
        "--feature-b",
        "hole-99",
        "--format",
        "json",
    )
    outside_thickness = run_cad(
        "inspect",
        "thickness",
        str(build_dir / "model.step"),
        "--point",
        "0,30,0",
        "--direction",
        "y",
        "--format",
        "json",
    )

    assert missing_feature.returncode == 2
    assert "Unknown hole feature id: hole-99" in missing_feature.stderr
    assert outside_thickness.returncode == 2
    assert "Thickness queries require a point inside the solid material" in outside_thickness.stderr


def test_inspect_mesh_unsupported_operations_are_clear(
    tmp_path: Path, examples_dir: Path
) -> None:
    build_dir = build_fixture(tmp_path, examples_dir, "hole_plate.py")

    holes = run_cad("inspect", "holes", str(build_dir / "model.glb"), "--format", "json")
    center_distance = run_cad(
        "inspect",
        "center-distance",
        str(build_dir / "model.glb"),
        "--feature-a",
        "hole-1",
        "--feature-b",
        "hole-2",
        "--format",
        "json",
    )

    assert holes.returncode == 4
    assert "Hole inspection requires a STEP/exact solid artifact" in holes.stderr
    assert center_distance.returncode == 4
    assert "Center-distance queries require a STEP/exact solid artifact" in center_distance.stderr


def test_inspect_mesh_thickness_reports_optional_dependency_or_value(
    tmp_path: Path, examples_dir: Path
) -> None:
    build_dir = build_fixture(tmp_path, examples_dir, "hole_plate.py")
    thickness = run_cad(
        "inspect",
        "thickness",
        str(build_dir / "model.glb"),
        "--point",
        "0,0.009,0",
        "--direction",
        "y",
        "--format",
        "json",
    )

    if importlib.util.find_spec("rtree") is None:
        assert thickness.returncode == 4
        assert "optional 'rtree' dependency" in thickness.stderr
    else:
        assert thickness.returncode == 0, thickness.stderr
        payload = json.loads(thickness.stdout)
        assert payload["mode"] == "mesh"
        assert payload["data"]["thickness"] > 0
