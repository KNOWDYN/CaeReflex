# Changelog

## Unreleased — CaeReflex 2.x foundation

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
