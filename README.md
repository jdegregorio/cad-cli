# cad-cli

**A deterministic CAD toolchain in a single command.** Take a Python model from
source → STEP / GLB → previews → diffs → a hashed review bundle, all from a
stable, scriptable CLI. 

`cad-cli` is the portable geometry toolchain used by
[Formloop](https://github.com/jdegregorio/formloop/tree/main). It keeps CAD
generation, preview rendering, and artifact comparison in one place so you can
drop it into local dev, CI, or another application without bringing
orchestration logic along.

> 📖 Architecture background and design rationale live in [SPEC.md](./SPEC.md).
> ✨ Every command has rich `--help` — if you installed the CLI you don't need
> to come back here: `cad --help`, `cad <command> --help`, and
> `cad inspect <subcommand> --help` cover everything below.

---

## Why it exists

- **STEP** is the authoritative truth for CAD geometry.
- **GLB** is the standard presentation artifact for preview and rendering.
- **Comparison and inspection** need deterministic, scriptable outputs.
- **Downstream systems** need clean bundles and machine-readable metadata.

Every command that produces artifacts also writes a schema-versioned JSON
manifest (`schema_version: 1`) alongside them so results stay scriptable and
traceable.

---

## Install

`cad-cli` is a standard Python 3.12+ package with a `cad` entry point. Pick the
installation path that fits how you'll use it.

### 1. Global install with `uv tool` (recommended for daily use)

[`uv`](https://docs.astral.sh/uv/) can install the CLI into its own isolated
virtual environment and drop the `cad` binary onto your PATH — the same way
`pipx` does, but faster.

From a local checkout:

```bash
uv tool install .
```

Or directly from a Git reference (no clone needed):

```bash
uv tool install git+https://github.com/jdegregorio/cad-cli
```

Upgrade later with `uv tool upgrade cad-cli`, uninstall with
`uv tool uninstall cad-cli`.

### 2. Run without installing (one-shot)

Handy for CI or a quick try:

```bash
uvx --from git+https://github.com/jdegregorio/cad-cli cad --help
```

### 3. Project-local dev environment

When you're working **on** `cad-cli` itself, sync the project and its dev
dependencies into a local `.venv`:

```bash
uv sync --extra dev
uv run cad --help
```

This is what the examples in the rest of this README assume.

### 4. Other installers

The project is a plain PEP 621 package, so `pipx`, `pip install .`, and
`pip install git+…` all work identically.

### Blender (required for `cad render` and `cad compare --render-diffs`)

```bash
brew install --cask blender       # macOS
# or install Blender from https://www.blender.org/ for your platform
```

`cad render` discovers Blender in this order:

1. `--blender-bin /path/to/blender`
2. `CAD_BLENDER_BIN` environment variable
3. `blender` on your `PATH`

---

## 60-second quickstart

```bash
# 1. Build a sample model into out/build
uv run cad build examples/models/cube.py --output-dir out/build --emit-stl

# 2. Render verification previews (7 views + a labelled sheet)
uv run cad render out/build/model.glb --output-dir out/render

# 3. Bundle everything into a hashed review zip
uv run cad package --output out/review.zip \
    --build-dir out/build --render-dir out/render
```

Open `out/render/sheet.png` to see your part from every angle. Open
`out/review.zip` to see the full bundle with `package-manifest.json`.

---

## Commands at a glance

| Command | Purpose |
| --- | --- |
| [`cad build`](#cad-build) | Run a Python model file to produce STEP / GLB / metadata (and optional STL) |
| [`cad render`](#cad-render) | Render a GLB into deterministic Blender previews (7 views + sheet) |
| [`cad compare`](#cad-compare) | Diff two geometry artifacts with exact or mesh-fallback metrics |
| [`cad inspect`](#cad-inspect) | Query a single artifact — summary, bbox, volume, holes, distances, thickness |
| [`cad package`](#cad-package) | Zip build + render + compare + extras into a hashed review bundle |

Every command supports `--format json` for structured stdout and writes a
matching JSON manifest to disk.

---

## `cad build`

Turn a Python model file into deterministic CAD artifacts.

**Contract.** The source file exposes a callable (default: `build_model`) with
the signature:

```python
def build_model(params: dict, context) -> build123d.Shape: ...
```

**Outputs in `--output-dir`:**

- `model.step` — authoritative CAD geometry
- `model.glb` — presentation artifact used by `cad render`
- `build-metadata.json` — source path, resolved params, CLI args, tool versions
- `model.stl` — optional, via `--emit-stl`
- `source-snapshot.py` — optional, via `--snapshot-source`

```bash
# Params from a file plus command-line overrides, with an STL for printing
uv run cad build plate.py --output-dir out/build \
    --params defaults.json \
    --set hole.diameter=6 \
    --set translation=[5,0,0] \
    --emit-stl --snapshot-source
```

`--set` values are parsed as JSON first, so numbers, booleans, arrays, and
objects all work. Dotted keys set nested values.

---

## `cad render`

Render a GLB through Blender into a deterministic set of verification previews.

**Outputs in `--output-dir`:** `front.png`, `back.png`, `left.png`, `right.png`,
`top.png`, `bottom.png`, `iso.png`, `sheet.png`, `render-metadata.json`.

- All views are auto-framed — parts never clip the frame.
- A neutral verification shader with balanced fill lighting keeps the top and
  bottom datum views visually consistent with the sides.
- Default spec: `768×768`, `BLENDER_EEVEE`, `32 samples`. Override any of these
  via `--spec render-spec.json`.

```bash
uv run cad render out/build/model.glb --output-dir out/render
```

---

## `cad compare`

Diff two geometry artifacts and emit scriptable metrics plus optional visual
diffs.

The comparison mode is selected automatically from the inputs:

- **`exact`** — both inputs are STEP → exact solid boolean comparison.
- **`mesh_fallback`** — at least one input is GLB/STL → mesh boolean via
  `trimesh`.

Alignment (`none` / `translate` / `principal`) is applied to the right input
*before* comparing and is always recorded separately from overlap metrics, so
alignment never silently inflates overlap numbers.

```bash
# Exact compare with a full visual diff sheet
uv run cad compare out/a/model.step out/b/model.step \
    --output-dir out/compare \
    --align principal \
    --render-diffs          # implies --emit-diff-solids
```

`compare-metrics.json` always includes:
`mode, alignment, left_volume, right_volume, shared_volume, left_only_volume,
right_only_volume, union_volume, overlap_ratio, notes`.

With `--emit-diff-solids` you also get `shared.step`, `left_only.step`, and
`right_only.step`. With `--render-diffs` you additionally get one labelled
`compare-sheet.png` (LEFT / RIGHT / SHARED / LEFT ONLY / RIGHT ONLY).

---

## `cad inspect`

Query a single artifact. STEP inputs get the richest feature analysis; mesh
inputs fall back cleanly and only fail for operations that genuinely need
exact features.

| Subcommand | What it reports | STEP only? |
| --- | --- | --- |
| `summary` | dimensions, volume, face/edge/solid counts, holes | No |
| `bbox` | axis-aligned bounding box (min / max / size) | No |
| `volume` | signed volume (null for non-watertight meshes) | No |
| `holes` | cylindrical through-holes, each with a stable `hole-N` id | **Yes** |
| `center-distance` | axis-to-axis distance between two named features | **Yes** |
| `thickness` | ray-cast thickness at a point along x / y / z | No* |

<sub>\* Mesh-based thickness probing may require the optional `rtree`
dependency. STEP remains the preferred authoritative input.</sub>

```bash
uv run cad inspect summary         out/build/model.step
uv run cad inspect holes           out/build/model.step --format json
uv run cad inspect center-distance out/build/model.step \
    --feature-a hole-1 --feature-b hole-2
uv run cad inspect thickness       out/build/model.step \
    --point 0,9,0 --direction y
```

---

## `cad package`

Collect build, render, compare, and any extra outputs into a single zip archive
with a hashed manifest.

Inside the archive, files are grouped by role (`build/`, `render/`, `compare/`,
`extra/`). `package-manifest.json` is written next to the zip **and** embedded
in it. Each entry records role, source path, archive path, `sha256`, and
`size_bytes`.

```bash
uv run cad package --output out/review.zip \
    --build-dir out/build \
    --render-dir out/render \
    --compare-dir out/compare \
    --include NOTES.md --include screenshots/
```

---

## Artifact and metadata conventions

- All machine-readable results use `schema_version: 1`.
- **Build metadata** preserves source model path, params, command args, and
  tool versions.
- **Render metadata** records the input GLB, Blender binary, and render spec.
- **Compare metadata** records both input paths, alignment mode, and comparison
  mode.
- **Package manifests** record archive layout, source paths, hashes, and
  packaging inputs.

### Exact vs fallback compare

- STEP inputs → exact CAD-solid comparison.
- GLB / STL inputs → mesh fallback, mode is labelled `mesh_fallback`.
- Alignment is always recorded separately from overlap metrics.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | success |
| `1` | other / unexpected error |
| `2` | invalid input or CLI usage error |
| `3` | missing external dependency (e.g. Blender) |
| `4` | unsupported operation for the given input type |
| `5` | geometry load / export failure |
| `6` | render pipeline failure |
| `7` | compare pipeline failure |

---

## Development

```bash
uv sync --extra dev

uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

The render test uses a real local Blender install. If Blender is unavailable,
only that test is skipped — the rest of the suite still runs.

---

## Releases

Versioning is automated via
[release-please](https://github.com/googleapis/release-please) and
[Conventional Commits](https://www.conventionalcommits.org/):

- PRs should use conventional commit titles — `feat:`, `fix:`, `docs:`,
  `refactor:`, `perf:`, `chore:`, `test:`, `ci:`, etc. Breaking changes use
  `feat!:` or a `BREAKING CHANGE:` footer.
- On every merge to `main`, the `release-please` workflow maintains an open
  **release PR** that bumps the version in `pyproject.toml` and updates
  `CHANGELOG.md`. Merging that PR cuts a `vX.Y.Z` tag and a GitHub Release.
- The release workflow then runs `uv build`, validates the artifacts with
  `twine check`, and attaches the built wheel and sdist to the GitHub
  Release. Install a specific release with:

  ```bash
  uv tool install git+https://github.com/jdegregorio/cad-cli@v0.1.0
  ```

  Or grab the `.whl` / `.tar.gz` directly from the release page.

See [`.github/workflows/release-please.yml`](./.github/workflows/release-please.yml)
for the full pipeline.

---

## Further reading

- [SPEC.md](./SPEC.md) — design rationale and architecture notes.
- [REQUIREMENTS.md](./REQUIREMENTS.md) — requirement IDs referenced in source.
- [examples/models/](./examples/models/) — runnable model sources used by the
  quickstart and the test suite.
