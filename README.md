# cad-cli

Deterministic CAD command-line tooling for building, rendering, comparing, inspecting, and packaging 3D design artifacts.

`cad-cli` is the portable geometry toolchain used by [Formloop](https://github.com/jdegregorio/formloop/tree/main). It keeps CAD generation, preview rendering, and artifact comparison in a stable CLI that can be used locally, in CI, or from another application without bringing along orchestration logic.

## Why it exists

- STEP is the authoritative artifact for CAD truth.
- GLB is the standard presentation artifact for preview and rendering.
- Comparison and inspection need deterministic, scriptable outputs.
- Downstream systems need clean bundles and machine-readable metadata.

Project background and deeper architecture notes live in [SPEC.md](/Users/jdegregorio/Repos/cad-cli/SPEC.md).

## Install

Python 3.12+ and [`uv`](https://docs.astral.sh/uv/) are the supported defaults.

```bash
uv sync --extra dev
```

Install Blender for the render pipeline:

```bash
brew install --cask blender
```

`cad render` discovers Blender through:

1. `--blender-bin`
2. `CAD_BLENDER_BIN`
3. `PATH`

## Quickstart

Build a sample model:

```bash
uv run cad build examples/models/cube.py --output-dir out/build --emit-stl --snapshot-source
```

Render the generated GLB:

```bash
uv run cad render out/build/model.glb --output-dir out/render
```

Compare two revisions:

```bash
uv run cad compare out/a/model.step out/b/model.step --output-dir out/compare --align principal --emit-diff-solids
```

Inspect exact geometry:

```bash
uv run cad inspect holes out/build/model.step --format json
uv run cad inspect center-distance out/build/model.step --feature-a hole-1 --feature-b hole-2
uv run cad inspect thickness out/build/model.step --point 0,9,0 --direction y
```

Package outputs:

```bash
uv run cad package --output out/review.zip --build-dir out/build --render-dir out/render --compare-dir out/compare
```

## Command Overview

### `cad build`

- Input: local Python model file
- Contract: `build_model(params, context)` returns a `build123d` shape
- Outputs:
  - `model.step`
  - `model.glb`
  - `build-metadata.json`
  - optional `model.stl`
  - optional `source-snapshot.py`

### `cad render`

- Input: GLB
- Backend: Blender in background mode
- Outputs:
  - `front.png`
  - `back.png`
  - `left.png`
  - `right.png`
  - `top.png`
  - `bottom.png`
  - `iso.png`
- `sheet.png`
- `render-metadata.json`
- All preview images are framed to show the full part without clipping.
- The default view set includes datum-oriented orthographic views plus an angled isometric view.
- Blender-native outline rendering emphasizes visible edges and feature transitions for verification-oriented review without adding image noise.
- The default verification shader uses a neutral light material with balanced fill lighting so top and bottom datum views stay visually consistent.

### `cad compare`

- Exact-solid comparison for STEP when available
- Mesh fallback for GLB/STL
- Outputs `compare-metrics.json` with `schema_version: 1`
- Optional exact diff exports: `shared.step`, `left_only.step`, `right_only.step`

### `cad inspect`

- Summary, bounding box, volume, holes, center distance, and thickness queries
- Richest feature support is available on exact STEP solids
- Unsupported mesh-only operations fail clearly instead of silently guessing
- Mesh thickness probing may require the optional `rtree` dependency; STEP remains the preferred authoritative inspect input

### `cad package`

- Bundles build, render, compare, and extra files into a zip archive
- Emits `package-manifest.json` with hashes and source references

## Artifact and Metadata Conventions

- All machine-readable results use `schema_version: 1`.
- Build metadata preserves source model path, params, command args, and tool versions.
- Render metadata records the input GLB, Blender binary, and render spec.
- Compare metadata records both input paths, alignment mode, and comparison mode.
- Package manifests record archive layout, source paths, hashes, and packaging inputs.

## Exact vs Fallback Compare

- STEP inputs use exact CAD-solid comparison.
- GLB/STL inputs use a mesh fallback and label the comparison mode as `mesh_fallback`.
- Alignment is always recorded separately from overlap metrics.

## Validation

Development validation is managed with `uv`:

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

The render test uses a real local Blender install. If Blender is unavailable, only the render-specific pytest case is skipped.
