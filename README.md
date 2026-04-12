# cad-cli

Deterministic CAD CLI for building, rendering, comparing, inspecting, and packaging 3D design artifacts.

`cad-cli` is the portable tool layer for the Formloop stack. It is intentionally separate from agent orchestration and UI concerns so it can be used by humans, CI pipelines, and other systems as a stable geometry toolchain.

## Purpose

This repo exists to provide a unified command-line interface for deterministic CAD operations:

- **build**: create geometry from Python-native CAD definitions, with `build123d` as the primary modeling backend
- **render**: produce consistent preview assets using Blender as the standard renderer
- **compare**: evaluate geometric similarity and deltas, with exact CAD-solid comparison where possible
- **inspect**: expose artifact metadata, dimensions, topology, and export details
- **package**: bundle authoritative and presentation artifacts for downstream use
- **validate** (future): run deterministic structural and artifact integrity checks

## Architectural role

`cad-cli` owns the deterministic core. It should be safe to call repeatedly, easy to script, and boring in the best possible way.

### In scope

- CAD build pipeline based on `build123d`
- STEP as the authoritative CAD artifact
- GLB as the standard presentation/render handoff artifact
- Blender-based rendering scripts and conventions
- Geometry comparison utilities
- Artifact inspection and packaging
- Stable CLI contracts for local use and CI

### Out of scope

- Multi-agent task orchestration
- Chat UX or application UI
- Prompting or skill management
- Dataset and eval orchestration at the app layer
- Long-lived design session state

## Design principles

- **Deterministic by default**: same inputs should produce the same outputs, or explicitly explain why not
- **Artifact traceability**: every command should make it easy to understand what was created, from what, and where it went
- **Geometry first**: rendering is downstream of geometry, not a substitute for it
- **Clean separation of concerns**: modeling, rendering, comparison, and packaging should stay composable
- **CI-friendly**: commands should be scriptable and machine-readable where practical

## Planned command surface

The repo should expose a unified deterministic `cad` command surface via the `cad-cli` package.

```bash
cad build ...
cad render ...
cad compare ...
cad inspect ...
cad package ...
# future
cad validate ...
```

## CLI specification

### `cad build`

Purpose: execute or parameterize a `build123d` model and emit standard artifacts.

Inputs may include:

- model source
- parameter file
- working directory
- output directory

Outputs should include:

- STEP
- GLB
- metadata
- optionally STL
- optionally normalized source snapshot

### `cad render`

Purpose: render a GLB model into deterministic preview assets using Blender.

Inputs may include:

- GLB path
- render spec
- output directory

Outputs should include:

- front view
- right view
- top view
- iso view
- composite contact sheet
- render metadata

### `cad compare`

Purpose: compare two geometries when two geometries are available.

Typical uses:

- candidate vs ground truth in evals
- candidate vs prior revision
- candidate vs imported reference geometry
- optional future derived geometry comparisons

Outputs should include:

- metrics JSON
- short summary
- overlap metrics
- optional diff solids or meshes
- optional visual review assets

### `cad inspect`

Purpose: provide lightweight deterministic inspection without requiring full comparison.

Typical uses:

- bounding box
- overall dimensions
- thickness checks
- hole diameters
- center distances
- volume
- face counts or feature-like summaries where practical
- export confirmation

This command is especially important for both the internal review loop and developer evals.

### `cad package`

Purpose: collect outputs into a clean bundle for download or archival.

Typical contents:

- STEP
- GLB
- render sheet
- model source
- metadata
- optional review summary
- optional compare or eval outputs

### `cad validate` (future)

Purpose: optional downstream manufacturability or printability validation.

This is intentionally outside the core design loop for the first version.

If added later, a sensible structure is:

- a geometry-aware pre-analysis layer
- a slicer-backed validation layer, with PrusaSlicer as the portable default and Bambu Studio as an optional target-specific second pass

Useful future signals may include:

- unsupported overhang area
- bridge risk
- mid-air islands
- support-contact pain proxy

## Relationship to Formloop

Formloop is the main application and agentic orchestration layer. It should treat `cad-cli` as a deterministic subsystem, not as a place to hide application logic.

A useful rule of thumb:

- if the behavior should be portable, testable, and usable without the app, it probably belongs in `cad-cli`
- if the behavior depends on agents, UX, datasets, or run-state orchestration, it probably belongs in Formloop

## Initial development priorities

1. Define the CLI contract and artifact conventions
2. Implement build flow with `build123d`
3. Implement GLB export and Blender render pipeline
4. Implement exact-or-best-available geometry comparison flow
5. Add inspection and packaging commands
6. Establish repeatable validation fixtures and golden artifacts

## Status

Early repo setup. The goal right now is to establish the contract and operating principles before adding full scaffolding.
