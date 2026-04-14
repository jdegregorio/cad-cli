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
    vol_text = text_volume.stdout.strip()
    assert vol_text.startswith("Volume of model.glb:"), f"Unexpected text output: {vol_text!r}"
    assert any(c.isdigit() for c in vol_text) or "N/A" in vol_text, (
        f"Volume text must contain a numeric value or N/A explanation, got: {vol_text!r}"
    )


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


def test_inspect_text_format_shows_actual_data(tmp_path: Path, examples_dir: Path) -> None:
    """Regression: text format for inspect commands must output actual metric values.

    Previously, inspect summary/bbox/volume all emitted a generic "Computed X for file"
    message with no actual data, making the default text format useless.
    """
    build_dir = build_fixture(tmp_path, examples_dir, "box.py")

    # inspect volume (exact) – must include the actual volume number
    vol_exact = run_cad("inspect", "volume", str(build_dir / "model.step"))
    assert vol_exact.returncode == 0, vol_exact.stderr
    vol_text = vol_exact.stdout.strip()
    assert vol_text.startswith("Volume of model.step:"), f"Got: {vol_text!r}"
    assert "6000" in vol_text, f"Volume value missing from: {vol_text!r}"

    # inspect volume (mesh) – must include a numeric value or N/A, not a generic success message
    vol_mesh = run_cad("inspect", "volume", str(build_dir / "model.glb"))
    assert vol_mesh.returncode == 0, vol_mesh.stderr
    vol_mesh_text = vol_mesh.stdout.strip()
    assert vol_mesh_text.startswith("Volume of model.glb:"), f"Got: {vol_mesh_text!r}"
    assert any(c.isdigit() for c in vol_mesh_text) or "N/A" in vol_mesh_text, (
        f"Volume text must contain a numeric value or N/A explanation, got: {vol_mesh_text!r}"
    )

    # inspect bbox (exact) – must include actual dimensions
    bbox_exact = run_cad("inspect", "bbox", str(build_dir / "model.step"))
    assert bbox_exact.returncode == 0, bbox_exact.stderr
    bbox_text = bbox_exact.stdout.strip()
    assert bbox_text.startswith("Bounding box of model.step:"), f"Got: {bbox_text!r}"
    assert "10" in bbox_text and "20" in bbox_text and "30" in bbox_text, (
        f"Dimension values missing from: {bbox_text!r}"
    )

    # inspect bbox (mesh) – must include numeric dimensions
    bbox_mesh = run_cad("inspect", "bbox", str(build_dir / "model.glb"))
    assert bbox_mesh.returncode == 0, bbox_mesh.stderr
    bbox_mesh_text = bbox_mesh.stdout.strip()
    assert bbox_mesh_text.startswith("Bounding box of model.glb:"), f"Got: {bbox_mesh_text!r}"
    assert any(c.isdigit() for c in bbox_mesh_text), "BBox text must contain numeric values"

    # inspect summary (exact) – must include mode, dimensions, and volume
    summary_exact = run_cad("inspect", "summary", str(build_dir / "model.step"))
    assert summary_exact.returncode == 0, summary_exact.stderr
    summary_text = summary_exact.stdout.strip()
    assert "model.step" in summary_text, f"Got: {summary_text!r}"
    assert "exact" in summary_text, f"Mode missing from: {summary_text!r}"
    assert "6000" in summary_text, f"Volume missing from: {summary_text!r}"
    assert "10" in summary_text and "20" in summary_text and "30" in summary_text, (
        f"Dimensions missing from: {summary_text!r}"
    )

    # inspect summary (mesh) – must include mode and numeric values
    summary_mesh = run_cad("inspect", "summary", str(build_dir / "model.glb"))
    assert summary_mesh.returncode == 0, summary_mesh.stderr
    summary_mesh_text = summary_mesh.stdout.strip()
    assert "model.glb" in summary_mesh_text, f"Got: {summary_mesh_text!r}"
    assert "mesh" in summary_mesh_text, f"Mode missing from: {summary_mesh_text!r}"
    assert any(c.isdigit() for c in summary_mesh_text), "Summary text must contain numeric values"


def test_inspect_holes_text_format(tmp_path: Path, examples_dir: Path) -> None:
    """Text format for inspect holes must report the count of holes found."""
    build_dir = build_fixture(tmp_path, examples_dir, "hole_plate.py")

    text_holes = run_cad("inspect", "holes", str(build_dir / "model.step"))
    assert text_holes.returncode == 0, text_holes.stderr
    holes_text = text_holes.stdout.strip()
    assert any(c.isdigit() for c in holes_text), (
        f"Hole count missing from text output: {holes_text!r}"
    )
    assert "hole" in holes_text.lower(), f"Got: {holes_text!r}"


def test_inspect_center_distance_and_thickness_text_format(
    tmp_path: Path, examples_dir: Path
) -> None:
    """Text format for center-distance and thickness already embeds the key value; verify it still does."""
    build_dir = build_fixture(tmp_path, examples_dir, "hole_plate.py")

    cd = run_cad(
        "inspect",
        "center-distance",
        str(build_dir / "model.step"),
        "--feature-a",
        "hole-1",
        "--feature-b",
        "hole-2",
    )
    assert cd.returncode == 0, cd.stderr
    cd_text = cd.stdout.strip()
    assert "hole-1" in cd_text and "hole-2" in cd_text, f"Feature IDs missing from: {cd_text!r}"
    assert any(c.isdigit() for c in cd_text), f"Distance value missing from: {cd_text!r}"

    thickness = run_cad(
        "inspect",
        "thickness",
        str(build_dir / "model.step"),
        "--point",
        "0,0.009,0",
        "--direction",
        "y",
    )
    assert thickness.returncode == 0, thickness.stderr
    th_text = thickness.stdout.strip()
    assert "y" in th_text, f"Direction missing from: {th_text!r}"
    assert any(c.isdigit() for c in th_text), f"Thickness value missing from: {th_text!r}"
