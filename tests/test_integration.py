from __future__ import annotations

import json
import zipfile
from pathlib import Path

from conftest import run_cad


def test_build_compare_inspect_and_package_flow(tmp_path: Path, examples_dir: Path) -> None:
    build_dir = tmp_path / "build"
    compare_dir = tmp_path / "compare"
    package_path = tmp_path / "bundle.zip"

    build = run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(build_dir),
        "--emit-stl",
        "--snapshot-source",
    )
    assert build.returncode == 0, build.stderr
    assert (build_dir / "model.step").exists()
    assert (build_dir / "model.glb").exists()
    assert (build_dir / "model.stl").exists()
    metadata = json.loads((build_dir / "build-metadata.json").read_text())
    assert metadata["trace"]["source_model"].endswith("box.py")

    shifted_dir = tmp_path / "shifted"
    build_shifted = run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(shifted_dir),
        "--set",
        "translation=[5,0,0]",
    )
    assert build_shifted.returncode == 0, build_shifted.stderr

    compare = run_cad(
        "compare",
        str(build_dir / "model.step"),
        str(shifted_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
        "--align",
        "translate",
        "--emit-diff-solids",
        "--format",
        "json",
    )
    assert compare.returncode == 0, compare.stderr
    compare_payload = json.loads(compare.stdout)
    assert compare_payload["metrics"]["mode"] == "exact"
    assert (
        compare_payload["metrics"]["shared_volume"]
        == compare_payload["metrics"]["left_volume"]
    )
    assert (compare_dir / "compare-metrics.json").exists()

    inspect_summary = run_cad(
        "inspect",
        "summary",
        str(build_dir / "model.step"),
        "--format",
        "json",
    )
    assert inspect_summary.returncode == 0, inspect_summary.stderr
    inspect_payload = json.loads(inspect_summary.stdout)
    assert inspect_payload["data"]["volume"] == 6000.0

    package = run_cad(
        "package",
        "--output",
        str(package_path),
        "--build-dir",
        str(build_dir),
        "--compare-dir",
        str(compare_dir),
        "--format",
        "json",
    )
    assert package.returncode == 0, package.stderr
    package_payload = json.loads(package.stdout)
    assert Path(package_payload["bundle_path"]).exists()
    assert Path(package_payload["manifest_path"]).exists()
    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
    assert "package-manifest.json" in names
    assert "build/model.step" in names
    assert "compare/compare-metrics.json" in names


def test_compare_principal_alignment(tmp_path: Path, examples_dir: Path) -> None:
    left_dir = tmp_path / "left"
    right_dir = tmp_path / "right"
    build_left = run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(left_dir),
        "--set",
        "width=10",
        "--set",
        "depth=20",
        "--set",
        "height=30",
    )
    build_right = run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(right_dir),
        "--set",
        "width=10",
        "--set",
        "depth=20",
        "--set",
        "height=30",
        "--set",
        "rotation_deg={\"z\":90}",
    )
    assert build_left.returncode == 0, build_left.stderr
    assert build_right.returncode == 0, build_right.stderr

    compare_none = run_cad(
        "compare",
        str(left_dir / "model.step"),
        str(right_dir / "model.step"),
        "--output-dir",
        str(tmp_path / "cmp-none"),
        "--align",
        "none",
        "--format",
        "json",
    )
    compare_principal = run_cad(
        "compare",
        str(left_dir / "model.step"),
        str(right_dir / "model.step"),
        "--output-dir",
        str(tmp_path / "cmp-principal"),
        "--align",
        "principal",
        "--format",
        "json",
    )
    none_payload = json.loads(compare_none.stdout)
    principal_payload = json.loads(compare_principal.stdout)
    assert compare_none.returncode == 0, compare_none.stderr
    assert compare_principal.returncode == 0, compare_principal.stderr
    assert none_payload["metrics"]["shared_volume"] < principal_payload["metrics"]["shared_volume"]
    assert (
        principal_payload["metrics"]["shared_volume"]
        == principal_payload["metrics"]["left_volume"]
    )


def test_inspect_holes_center_distance_and_thickness(tmp_path: Path, examples_dir: Path) -> None:
    build_dir = tmp_path / "plate"
    build = run_cad(
        "build",
        str(examples_dir / "hole_plate.py"),
        "--output-dir",
        str(build_dir),
        "--format",
        "json",
    )
    assert build.returncode == 0, build.stderr

    holes = run_cad("inspect", "holes", str(build_dir / "model.step"), "--format", "json")
    assert holes.returncode == 0, holes.stderr
    holes_payload = json.loads(holes.stdout)
    assert len(holes_payload["data"]["holes"]) == 2
    assert holes_payload["data"]["holes"][0]["diameter"] == 6.0

    center_distance = run_cad(
        "inspect",
        "center-distance",
        str(build_dir / "model.step"),
        "--feature-a",
        "hole-1",
        "--feature-b",
        "hole-2",
        "--format",
        "json",
    )
    center_payload = json.loads(center_distance.stdout)
    assert center_distance.returncode == 0, center_distance.stderr
    assert center_payload["data"]["center_distance"] == 20.0

    thickness = run_cad(
        "inspect",
        "thickness",
        str(build_dir / "model.step"),
        "--point",
        "0,9,0",
        "--direction",
        "y",
        "--format",
        "json",
    )
    thickness_payload = json.loads(thickness.stdout)
    assert thickness.returncode == 0, thickness.stderr
    assert round(thickness_payload["data"]["thickness"], 4) == 24.0


def test_verification_block_fixture(tmp_path: Path, examples_dir: Path) -> None:
    build_dir = tmp_path / "verification-block"
    build = run_cad(
        "build",
        str(examples_dir / "verification_block.py"),
        "--output-dir",
        str(build_dir),
    )
    assert build.returncode == 0, build.stderr

    holes = run_cad("inspect", "holes", str(build_dir / "model.step"), "--format", "json")
    assert holes.returncode == 0, holes.stderr
    payload = json.loads(holes.stdout)
    diameters = sorted(round(item["diameter"], 4) for item in payload["data"]["holes"])
    assert diameters == [5.0, 5.0, 10.0]
