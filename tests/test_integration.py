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


def test_compare_identical_step_overlap_is_one(tmp_path: Path, examples_dir: Path) -> None:
    """I1: Identical STEP vs STEP should yield overlap_ratio == 1.0."""
    build_dir = tmp_path / "build"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(build_dir),
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(build_dir / "model.step"),
        str(build_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["metrics"]["mode"] == "exact"
    assert payload["metrics"]["overlap_ratio"] == 1.0
    assert payload["metrics"]["left_only_volume"] == 0.0
    assert payload["metrics"]["right_only_volume"] == 0.0


def test_compare_different_sizes_partial_overlap(tmp_path: Path, examples_dir: Path) -> None:
    """I4: Different-sized shapes should produce overlap_ratio < 1.0 with non-zero deltas."""
    small_dir = tmp_path / "small"
    big_dir = tmp_path / "big"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(small_dir),
        "--set",
        "width=10",
        "--set",
        "depth=10",
        "--set",
        "height=10",
    )
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(big_dir),
        "--set",
        "width=20",
        "--set",
        "depth=20",
        "--set",
        "height=20",
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(small_dir / "model.step"),
        str(big_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    metrics = payload["metrics"]
    assert metrics["overlap_ratio"] < 1.0
    assert metrics["overlap_ratio"] > 0.0
    assert metrics["left_only_volume"] == 0.0  # small is fully inside big
    assert metrics["right_only_volume"] > 0.0  # big has leftover volume
    assert metrics["shared_volume"] == metrics["left_volume"]


def test_compare_emit_diff_solids(tmp_path: Path, examples_dir: Path) -> None:
    """I5: --emit-diff-solids should produce shared.step and exclusive STEP files."""
    small_dir = tmp_path / "small"
    big_dir = tmp_path / "big"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(small_dir),
        "--set",
        "width=10",
        "--set",
        "depth=10",
        "--set",
        "height=10",
    )
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(big_dir),
        "--set",
        "width=20",
        "--set",
        "depth=20",
        "--set",
        "height=20",
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(small_dir / "model.step"),
        str(big_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
        "--emit-diff-solids",
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert (compare_dir / "shared.step").exists()
    assert (compare_dir / "right_only.step").exists()
    # left_only should be zero volume (small inside big), so file should NOT exist
    assert not (compare_dir / "left_only.step").exists()
    artifact_roles = {a["role"] for a in payload["artifacts"]}
    assert "shared" in artifact_roles
    assert "right_only" in artifact_roles


def test_compare_mesh_fallback_glb(tmp_path: Path, examples_dir: Path) -> None:
    """I6: GLB vs GLB should trigger mesh_fallback mode."""
    build_dir = tmp_path / "build"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(build_dir),
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(build_dir / "model.glb"),
        str(build_dir / "model.glb"),
        "--output-dir",
        str(compare_dir),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["metrics"]["mode"] == "mesh_fallback"


def test_compare_text_output_format(tmp_path: Path, examples_dir: Path) -> None:
    """I8: Default text format should output a human-readable summary."""
    build_dir = tmp_path / "build"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(build_dir),
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(build_dir / "model.step"),
        str(build_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
    )
    assert result.returncode == 0, result.stderr
    assert "overlap_ratio" in result.stdout
    # Should NOT be valid JSON (it's a summary string)
    try:
        json.loads(result.stdout)
        raise AssertionError("Text output should not be valid JSON")
    except json.JSONDecodeError:
        pass


def test_compare_json_has_all_required_fields(tmp_path: Path, examples_dir: Path) -> None:
    """I9: JSON output should contain all required schema fields."""
    build_dir = tmp_path / "build"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(build_dir),
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(build_dir / "model.step"),
        str(build_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # Top-level fields
    assert payload["schema_version"] == 1
    assert payload["status"] == "ok"
    assert payload["command"] == "compare"
    assert "summary" in payload
    assert "left_path" in payload
    assert "right_path" in payload
    assert "output_dir" in payload
    assert "metrics_path" in payload
    assert "metrics" in payload
    assert "artifacts" in payload
    # Metrics fields
    metrics = payload["metrics"]
    for field in (
        "mode",
        "alignment",
        "left_volume",
        "right_volume",
        "shared_volume",
        "left_only_volume",
        "right_only_volume",
        "union_volume",
        "overlap_ratio",
        "notes",
    ):
        assert field in metrics, f"Missing metrics field: {field}"


def test_compare_missing_input_file(tmp_path: Path) -> None:
    """I10: Missing input file should return exit code 2 (InputError)."""
    result = run_cad(
        "compare",
        str(tmp_path / "nonexistent.step"),
        str(tmp_path / "also_missing.step"),
        "--output-dir",
        str(tmp_path / "out"),
    )
    assert result.returncode == 2


def test_compare_metrics_json_on_disk_matches_stdout(
    tmp_path: Path, examples_dir: Path
) -> None:
    """I11: compare-metrics.json on disk should match the stdout JSON result."""
    build_dir = tmp_path / "build"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(build_dir),
    )
    compare_dir = tmp_path / "cmp"
    result = run_cad(
        "compare",
        str(build_dir / "model.step"),
        str(build_dir / "model.step"),
        "--output-dir",
        str(compare_dir),
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    stdout_payload = json.loads(result.stdout)
    disk_payload = json.loads((compare_dir / "compare-metrics.json").read_text())
    # The disk file IS the full result (written by write_json)
    assert disk_payload["metrics"]["overlap_ratio"] == stdout_payload["metrics"]["overlap_ratio"]
    assert disk_payload["metrics"]["mode"] == stdout_payload["metrics"]["mode"]
    assert disk_payload["schema_version"] == 1


def test_compare_rotated_partial_overlap_metrics_consistent(
    tmp_path: Path, examples_dir: Path
) -> None:
    """Regression: rotated boxes with partial overlap must report consistent volumes.

    build123d cut() on STEP-loaded shapes may return a ShapeList. This test
    catches the bug where left_only and right_only volumes were reported as 0
    because ShapeList lacks a .volume attribute.
    """
    base_dir = tmp_path / "base"
    rotated_dir = tmp_path / "rotated"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(base_dir),
        "--set",
        "width=10",
        "--set",
        "depth=20",
        "--set",
        "height=30",
    )
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(rotated_dir),
        "--set",
        "width=10",
        "--set",
        "depth=20",
        "--set",
        "height=30",
        "--set",
        'rotation_deg={"z":90}',
    )
    result = run_cad(
        "compare",
        str(base_dir / "model.step"),
        str(rotated_dir / "model.step"),
        "--output-dir",
        str(tmp_path / "cmp"),
        "--align",
        "none",
        "--format",
        "json",
    )
    assert result.returncode == 0, result.stderr
    m = json.loads(result.stdout)["metrics"]
    # 10x20x30 vs 20x10x30 centered at origin: intersection is 10x10x30 = 3000
    assert abs(m["shared_volume"] - 3000.0) < 1.0
    assert abs(m["left_only_volume"] - 3000.0) < 1.0
    assert abs(m["right_only_volume"] - 3000.0) < 1.0
    assert abs(m["union_volume"] - 9000.0) < 1.0
    # overlap_ratio = 3000 / 9000 ≈ 0.333
    assert abs(m["overlap_ratio"] - 1.0 / 3.0) < 0.01


def test_compare_translate_alignment_shifted_box(tmp_path: Path, examples_dir: Path) -> None:
    """I2: Shifted box with translate alignment should recover full overlap."""
    base_dir = tmp_path / "base"
    shifted_dir = tmp_path / "shifted"
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(base_dir),
    )
    run_cad(
        "build",
        str(examples_dir / "box.py"),
        "--output-dir",
        str(shifted_dir),
        "--set",
        "translation=[100,200,300]",
    )

    # Without alignment, overlap should be near 0
    cmp_none = run_cad(
        "compare",
        str(base_dir / "model.step"),
        str(shifted_dir / "model.step"),
        "--output-dir",
        str(tmp_path / "cmp-none"),
        "--align",
        "none",
        "--format",
        "json",
    )
    assert cmp_none.returncode == 0, cmp_none.stderr
    none_metrics = json.loads(cmp_none.stdout)["metrics"]
    assert none_metrics["overlap_ratio"] == 0.0

    # With translate, overlap should be 1.0
    cmp_translate = run_cad(
        "compare",
        str(base_dir / "model.step"),
        str(shifted_dir / "model.step"),
        "--output-dir",
        str(tmp_path / "cmp-translate"),
        "--align",
        "translate",
        "--format",
        "json",
    )
    assert cmp_translate.returncode == 0, cmp_translate.stderr
    translate_metrics = json.loads(cmp_translate.stdout)["metrics"]
    assert translate_metrics["overlap_ratio"] == 1.0


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
