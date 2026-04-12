# AGENTS.md

Instructions for coding agents working in `cad-cli`.

This repository is the deterministic CAD tool layer. Optimize for correctness, traceability, repeatability, and closed-loop validation. Do not optimize for speed by skipping proof.

## Mission

Build a stable CLI for deterministic CAD operations:

- build geometry with `build123d`
- render geometry through Blender
- compare geometry using exact CAD-solid math where possible
- inspect artifacts and metadata
- package outputs for downstream systems

This repo is not the agent orchestration layer. Keep it portable and boring.

## Core operating rules

1. **Closed-loop validation is mandatory**
   - Do not declare work complete until you have run the relevant validation steps.
   - Every functional change must include evidence that the behavior works as designed.
   - If validation is blocked, say exactly what is unverified and what remains to prove.

2. **Determinism over cleverness**
   - Prefer explicit inputs, explicit outputs, stable file names, and stable command contracts.
   - Avoid hidden state, ambient configuration, and behavior that depends on machine-specific quirks unless clearly documented.

3. **STEP is authoritative, GLB is presentational**
   - Preserve the separation between CAD truth and rendering assets.
   - Do not let rendering concerns distort the core geometry pipeline.

4. **Comparison is first-class**
   - Treat geometric comparison as a product feature, not an afterthought.
   - Alignment, overlap, and delta calculations should be explicit stages.

5. **Small diffs, clear contracts**
   - Prefer focused changes over repo-wide rewrites.
   - Update interfaces intentionally and document contract changes.

## Definition of done

A task is not done unless all relevant items below are satisfied:

- code is implemented
- tests covering the intended behavior are added or updated
- the changed functionality is exercised through the appropriate command path
- output artifacts are checked for expected existence and shape
- failure modes are validated where practical
- docs are updated when command behavior or artifacts change
- any billing, runtime cost, or external tool invocation implications are noted when relevant

If any item is skipped, explain why.

## Validation ladder

Use the lightest validation that can still prove the claim, then escalate when risk justifies it.

### Always do

- run targeted tests for changed modules
- run lint/format/type checks if configured
- execute the changed CLI command path locally when feasible
- verify expected files, metadata, and exit codes

### Do when behavior touches geometry generation

- validate that geometry is generated successfully
- verify exported STEP exists and is readable
- inspect dimensions / topology / key metadata relevant to the change
- use fixture-based or golden-artifact comparison where available

### Do when behavior touches rendering

- verify GLB export exists and is loadable
- run Blender render path end-to-end where feasible
- confirm rendered outputs are produced at expected paths with expected naming
- verify expected standard views are produced when applicable, including front, right, top, iso, and composite sheet
- sanity check camera, lighting, and output conventions against repository rules

### Do when behavior touches comparison

- test identical-shape equality path
- test known-different-shape delta path
- test alignment-sensitive scenarios separately from pure overlap/delta logic
- validate metrics JSON and short summary outputs
- prefer exact CAD-solid comparison when possible; document fallbacks clearly

### Do when behavior touches inspection

- validate reported measurements against known fixtures when possible
- verify volume, dimension, and feature-summary outputs are internally consistent
- confirm export confirmation and metadata reflect actual generated artifacts

### Do when behavior touches packaging or integration

- validate archive/bundle contents
- verify manifests, metadata, and references are complete
- confirm downstream consumer expectations remain satisfied

## Feedback loop expectations

When implementing non-trivial work, use this loop:

1. restate the exact claim being implemented
2. make the smallest viable change
3. run targeted validation
4. inspect outputs, not just return codes
5. adjust based on what failed or looked wrong
6. rerun validation until the evidence matches the claim

Do not stop at “command succeeded.” Success without artifact inspection is how bad systems become legends for the wrong reason.

## Testing guidance

- Prefer deterministic fixture-based tests
- Use golden artifacts when they are stable and meaningful
- Test CLI behavior at the contract level, not only helper functions
- Cover both success paths and failure/reporting paths
- Add regression tests for bugs before or alongside the fix
- If a geometry bug is found, capture the minimal reproducible case as a fixture

## Billing and external tool discipline

This repo may invoke heavyweight or licensed tools, especially Blender and future CAD/comparison components.

When changing code that affects tool execution:

- note when runtime cost or invocation frequency changes
- avoid unnecessary repeated heavyweight runs in tests
- cache or reuse intermediates only when it does not compromise determinism
- prefer targeted validation before full end-to-end runs
- if a command could materially increase compute cost, call it out explicitly

## Implementation preferences

- keep modules small and composable
- prefer pure functions around geometry transforms where possible
- isolate filesystem effects behind clear interfaces
- make artifact paths and naming conventions explicit
- use machine-readable output modes for CLI commands where useful
- surface actionable error messages with enough detail to debug failures

## Safety boundaries

Ask before:

- adding major dependencies
- changing artifact contracts in ways likely to break Formloop or CI
- deleting large fixture sets or golden artifacts
- introducing non-deterministic behavior by default
- adding network calls or telemetry

## Repo-specific architectural reminders

- `build123d` is the primary modeling backend
- Blender is the standard renderer
- STEP is the authoritative CAD artifact
- GLB is the standard presentation artifact
- geometry creation and rendering remain separate concerns
- exact CAD-solid comparison is preferred when possible
- alignment is a separate stage from overlap and delta computation
- `cad build` should emit standard build artifacts
- `cad render` should emit deterministic preview assets and render metadata
- `cad compare` should support evaluation, revision-to-revision, and imported-reference comparisons
- `cad inspect` should provide lightweight deterministic measurements without requiring full comparison
- `cad package` should collect authoritative, presentation, and optional review/eval artifacts into a clean bundle
- keep manufacturing or slicer validation outside the core path unless `cad validate` is intentionally being added as an optional downstream capability

## Good agent behavior

- be explicit about assumptions
- leave a short validation summary with evidence
- mention what is still unproven
- prefer one clean path over multiple half-working options
- keep the repo usable by humans, CI, and Formloop

## Bad agent behavior

- claiming success without running validation
- relying on screenshots or logs when artifact inspection is required
- changing CLI semantics without documentation
- hiding uncertainty behind vague language
- adding orchestration logic that belongs in Formloop
