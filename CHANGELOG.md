# Changelog

## 2.0.0a2 — Gate 5B native OpenFOAM inspection

- Added the isolated `openfoam.native` execution backend.
- Added bounded ASCII decoding for `polyMesh/points`, `faces`, `owner`, `neighbour` and `boundary`.
- Added point bounds, face/cell counts, internal-face counts and patch ranges.
- Added time-directory inventory and field availability by time.
- Added lazy `ArrayRef` registration for mesh coordinates, topology, ownership and supported field values.
- Added scalar, vector and common tensor field handling for uniform and nonuniform ASCII internal fields.
- Preserved Gate 4 dimensions in native field summaries and array metadata.
- Added explicit binary/directive/unsupported-grammar fallbacks with ordered parser-attempt records.
- Routed `deep` and `forensic` OpenFOAM inspection through the native reader while retaining `core.manifest-audit` for other adapters.
- Kept the core install dependency-light; no OpenFOAM installation or solver execution is required.

## 2.0.0a1 — Gate 5A execution foundation

### Gate 5A — Safe execution, artefacts and lazy arrays

- Aligned the package release line with the 2.0 alpha contracts.
- Added a bounded subprocess executor for deep-inspection backends.
- Added execution policies, persistent job records and parser-attempt ledgers.
- Added timeout, crash, invalid-result and source-mutation diagnostics.
- Added an immutable SHA-256 content-addressed local artefact store.
- Extended `ArrayRef` additively with semantic, provenance, backend and lifecycle metadata.
- Added a dependency-light raw numeric array provider with bounded describe, sample, slice and reduction operations.
- Added `execution`, `arrays` and `jobs` CLI command groups.
- Added a safe `core.manifest-audit` backend for exercising the runtime before native readers are introduced.
- Integrated the execution foundation with `deep` and `forensic` inspection profiles without adding native OpenFOAM, Gmsh or VTK decoding.

### Gate 4 — Dimensions, units and physics semantics

- Added Pint as the core unit-parsing, dimensionality and conversion backend.
- Added backend-neutral seven-component dimension vectors, dimensional checks and quantity evidence.
- Added a conservative CAE quantity ontology with explicit ambiguity and conflict states.
- Corrected OpenFOAM `FoamFile` class parsing so scalar, vector and tensor field rank comes from the source header.
- Added OpenFOAM field and transport-property dimensional extraction with raw-text fallback and stable diagnostics.
- Distinguished thermodynamic pressure from incompressible kinematic pressure.
- Added `units parse`, `units convert` and `units check` CLI commands.
- Added units summaries to ReflexCase, agent context and Markdown reports without removing legacy payload keys.
- Added human-control diagnostics for missing, malformed, ambiguous and conflicting dimensions.
- Added Gate 4 user, CLI and architecture documentation and semantic regression tests.

### Gates 1–3 — Contracts, CLI and discovery

- Added backend-neutral evidence, quantity, array-reference, manifest, budget, diagnostic, and adapter contracts.
- Added Python entry-point adapter discovery and capability declarations.
- Added bounded local/fsspec case cataloging with explicit limit and symlink diagnostics.
- Added SQLite manifest caching and incremental path-level diffs.
- Added `doctor`, `scan`, `adapters`, `schema`, `diagnostics`, and `cache` CLI commands.
- Preserved existing inspection, export, CrossRef, example, and format-specific compatibility commands.
- Embedded discovery manifests and diagnostics into ReflexCase and agent-context exports.
- Added Gate 1–3 architecture, CLI, and plugin documentation.

## 1.0.0 — Initial public release

- Added ReflexCase schema v1.0.
- Added read-only Gmsh, OpenFOAM, and VTK adapters.
- Added CrossRef metadata evidence layer.
- Added CLI.
- Added REST/OpenAPI server.
- Added agent-context export.
- Added Markdown and BibTeX exporters.
- Added lightweight bundled examples.
- Added source-available academic/commercial licence files.
