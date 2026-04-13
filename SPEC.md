# cad-cli Specification

`cad-cli` is the deterministic CAD tool layer for the Formloop ecosystem. It is intentionally separate from agent orchestration, UI concerns, and long-lived app state so it can be called reliably by humans, CI jobs, and downstream systems.

## Purpose

The project exists to provide one stable `cad` command surface for deterministic CAD operations:

- `build`: execute a Python-native `build123d` model and emit standard artifacts
- `render`: produce deterministic previews from GLB using Blender
- `compare`: compare two geometries with exact-solid math when possible
- `inspect`: expose deterministic measurements and feature summaries
- `package`: bundle authoritative, presentational, and review artifacts
- `validate`: reserved as a future extension point, not a v1 command

## Scope

### In scope

- `build123d`-based authoring workflows
- STEP as the authoritative CAD artifact
- GLB as the standard presentation artifact
- Blender-based preview rendering
- exact and fallback comparison flows
- deterministic inspection queries
- packaging for download, archival, and CI handoff
- stable machine-readable outputs with `schema_version: 1`

### Out of scope

- agent orchestration
- chat UX
- prompt/skill management
- dataset or eval orchestration at the app layer
- manufacturing validation in the v1 command surface

## Design Principles

- Determinism first: identical inputs should yield identical outputs when the environment is stable.
- Traceability by default: output metadata should preserve enough invocation context to debug artifacts without reading the source tree.
- STEP is truth: rendering never becomes the geometry authority.
- Comparison is first-class: alignment and overlap are explicit stages.
- Small, boring contracts win: explicit paths, explicit artifacts, explicit JSON.

## CLI Contract

### `cad build`

- Input: local Python file plus optional JSON params and `--set key=value` overrides
- Model contract: callable named `build_model(params, context)` by default
- Required outputs:
  - `model.step`
  - `model.glb`
  - `build-metadata.json`
- Optional outputs:
  - `model.stl`
  - `source-snapshot.py`

### `cad render`

- Input: GLB path, optional render spec JSON
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
- Render framing requirement: every preview image must fit the full geometry within frame with margin, without clipping.
- View requirement: datum-oriented orthographic views and at least one angled view are both first-class outputs.
- Verification requirement: edge and feature boundaries must remain readable enough for manual review of faces and holes, using clean renderer-native outlines rather than noisy image-space thresholding.
- Lighting requirement: previews should use a neutral verification material and balanced lighting so equivalent faces do not change to strongly different color families across datum views.

### `cad compare`

- Inputs: two geometry artifacts
- Alignment modes:
  - `none`
  - `translate`
  - `principal`
- Resolution order:
  - exact STEP/build123d comparison first
  - mesh fallback for GLB/STL when exact solids are unavailable
- Outputs:
  - `compare-metrics.json`
  - optional exact diff solids: `shared.step`, `left_only.step`, `right_only.step`

### `cad inspect`

- `cad inspect summary <artifact>`
- `cad inspect bbox <artifact>`
- `cad inspect volume <artifact>`
- `cad inspect holes <artifact>`
- `cad inspect center-distance <artifact> --feature-a <id> --feature-b <id>`
- `cad inspect thickness <artifact> --point x,y,z --direction x|y|z`

Exact STEP solids provide the richest inspection features. Mesh artifacts degrade gracefully and report unsupported operations clearly.

### `cad package`

- Collects selected build/render/compare directories and extra files into a zip bundle
- Emits `package-manifest.json` with source paths, archive paths, hashes, and input provenance

## Validation and Runtime Notes

- Exact compare is authoritative for STEP inputs.
- GLB/STL compare uses a mesh fallback and labels the mode explicitly in metrics JSON.
- Blender is a required external dependency for `cad render`.
- Build123d and Blender both carry non-trivial startup cost; targeted validation is preferred before full end-to-end render loops.

## Relationship to Formloop

Formloop is the primary application and orchestration layer. `cad-cli` is the deterministic subsystem it calls into, not a place for app-specific workflow logic.

- Formloop repo: <https://github.com/jdegregorio/formloop/tree/main>
- Rule of thumb:
  - if behavior should be portable, testable, and usable from a shell, it belongs here
  - if behavior depends on agents, UX, datasets, or run-state orchestration, it belongs in Formloop
