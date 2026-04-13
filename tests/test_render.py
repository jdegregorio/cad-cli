from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import run_cad
from PIL import Image

RENDER_VIEWS = ("front", "back", "left", "right", "top", "bottom", "iso", "sheet")


def non_background_bbox(path: Path) -> tuple[int, int, int, int] | None:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    background = image.getpixel((0, 0))
    xs: list[int] = []
    ys: list[int] = []
    for y in range(height):
        for x in range(width):
            pixel = image.getpixel((x, y))
            if any(abs(pixel[i] - background[i]) > 24 for i in range(3)):
                xs.append(x)
                ys.append(y)
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def background_outlier_ratio(path: Path, bbox: tuple[int, int, int, int]) -> float:
    image = Image.open(path).convert("RGB")
    width, height = image.size
    background = image.getpixel((0, 0))
    min_x, min_y, max_x, max_y = bbox
    total = 0
    outliers = 0
    for y in range(height):
        for x in range(width):
            if min_x <= x <= max_x and min_y <= y <= max_y:
                continue
            total += 1
            pixel = image.getpixel((x, y))
            if any(abs(pixel[i] - background[i]) > 18 for i in range(3)):
                outliers += 1
    return outliers / max(total, 1)


def center_pixel(path: Path) -> tuple[int, int, int]:
    image = Image.open(path).convert("RGB")
    return image.getpixel((image.width // 2, image.height // 2))


def build_and_render_fixture(
    tmp_path: Path, examples_dir: Path, model_name: str
) -> tuple[Path, dict]:
    build_dir = tmp_path / "build"
    render_dir = tmp_path / "render"
    build = run_cad(
        "build",
        str(examples_dir / model_name),
        "--output-dir",
        str(build_dir),
    )
    assert build.returncode == 0, build.stderr
    render = run_cad(
        "render",
        str(build_dir / "model.glb"),
        "--output-dir",
        str(render_dir),
        "--format",
        "json",
    )
    assert render.returncode == 0, render.stderr
    payload = json.loads(render.stdout)
    return render_dir, payload


def assert_render_views_fit(render_dir: Path, payload: dict) -> None:
    artifact_roles = {artifact["role"] for artifact in payload["artifacts"]}
    assert artifact_roles == {"front", "back", "left", "right", "top", "bottom", "iso", "sheet"}
    for name in RENDER_VIEWS:
        path = render_dir / f"{name}.png"
        assert path.exists()
        assert path.stat().st_size > 0
    for name in ("front", "back", "left", "right", "top", "bottom", "iso"):
        bbox = non_background_bbox(render_dir / f"{name}.png")
        assert bbox is not None
        min_x, min_y, max_x, max_y = bbox
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        assert min_x > 8
        assert min_y > 8
        assert max_x < 760
        assert max_y < 760
        assert width > 180
        assert height > 180
        assert background_outlier_ratio(render_dir / f"{name}.png", bbox) < 0.005
    assert Path(payload["metadata_path"]).exists()


@pytest.mark.skipif(not __import__("shutil").which("blender"), reason="Blender is not installed")
def test_render_end_to_end(tmp_path: Path, examples_dir: Path) -> None:
    render_dir, payload = build_and_render_fixture(tmp_path, examples_dir, "cube.py")
    assert_render_views_fit(render_dir, payload)


@pytest.mark.skipif(not __import__("shutil").which("blender"), reason="Blender is not installed")
def test_render_verification_block_front_back_fit(tmp_path: Path, examples_dir: Path) -> None:
    render_dir, payload = build_and_render_fixture(
        tmp_path, examples_dir, "verification_block.py"
    )
    assert_render_views_fit(render_dir, payload)
    for name in ("front", "back", "left", "right"):
        bbox = non_background_bbox(render_dir / f"{name}.png")
        assert bbox is not None
        min_x, min_y, max_x, max_y = bbox
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        assert height > width * 1.9
        assert min_y > 8
        assert max_y < 760

    top_center = center_pixel(render_dir / "top.png")
    bottom_center = center_pixel(render_dir / "bottom.png")
    front_center = center_pixel(render_dir / "front.png")
    # Regression for neutral verification shading: the bottom view should stay in the
    # same light neutral family rather than dropping into a strong blue cast, and the
    # matte material should avoid blowing out the part to pure white.
    for sample in (top_center, bottom_center, front_center):
        assert max(sample) <= 248
        assert min(sample) > 185
        assert max(sample) - min(sample) < 26
    assert bottom_center[2] - bottom_center[0] < 14
    assert abs(sum(bottom_center) - sum(top_center)) < 110
    assert abs(sum(bottom_center) - sum(front_center)) < 110
