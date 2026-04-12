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
