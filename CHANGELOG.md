# Changelog

## 2.0.0b2 — Gate 6B backend-to-graph mapping

- Added deterministic `caereflex.spatial-mapping/1.0` translation from validated `openfoam.native`, `gmsh.native` and `vtk.native` execution results into Gate 6A spatial graphs.
- Added OpenFOAM dataset, aggregate node/face/cell and explicit patch entities with lazy coordinate, topology, ownership and field links.
- Added Gmsh geometry, mesh, entity and physical-group mappings while keeping geometry and mesh identities distinct.
- Added VTK dataset, point, cell-type, field and collection-reference inventory mappings.
- Preserved unresolved coordinate frames for OpenFOAM and Gmsh; accepted VTK origin/direction frames only when explicit and linearly independent.
- Added deterministic graph, frame, entity, relation and array-link identifiers.
- Added automatic graph persistence and compact ReflexCase references after deep or forensic native inspection.
- Added stable mapping diagnostics for graph failures and unresolved array ownership.
- Added no cross-format equivalence, coordinate composition, adjacency inference, spatial query service, physics validation or design certification.

## 2.0.0b1 — Gate 6A spatial contracts and coordinate frames

- Added canonical backend-neutral spatial entity families for geometry, mesh, grouping and dataset evidence.
- Added versioned relations for containment, boundaries, adjacency, connectivity, discretisation, membership, field carriage, mapping and derivation.
- Added coordinate-frame contracts with explicit origin, basis, dimensionality, handedness, length-unit evidence, parent transforms, confidence and review states.
- Kept unresolved frames genuinely unresolved: CaeReflex does not assume metres, global axes, zero origins or right-handed orientation.
- Added compact axis-aligned bounds with explicit frame references.
- Added ArrayRef-only links for coordinates, connectivity, offsets, cell types, memberships, fields and transforms.
- Added compact-metadata limits that reject binary payloads, non-finite numbers and materialised heavy arrays.
- Added a SQLite spatial repository with graph-scoped foreign keys, parent-cycle checks, transactional snapshot import, deterministic export and integrity checks.
- Added compact spatial graph references to ReflexCase metadata without embedding graph or array payloads.
- Kept ReflexCase schema `1.0` and backend-neutral contract `2.0-alpha.3`; the Gate 6A spatial graph format is versioned independently as `1.0`.
- Added no backend mappings, spatial inference, coordinate transformation, physics rules or engineering validation in this foundation release.

## 2.0.0a5 — Gate 5 compatibility freeze and malformed-input hardening

- Froze the built-in execution-backend envelope as `caereflex.gate5.backend-result/1.0`.
- Added one common compatibility report to `core.manifest-audit`, `openfoam.native`, `gmsh.native` and `vtk.native` results.
- Added worker-side rejection of non-object payloads, missing summaries, non-finite values, unsafe paths, mismatched counts, invalid artefact references and materialised heavy arrays.
- Added stable diagnostic `CRX-GATE5-COMPAT-001` for deterministic backend-contract failures.
- Added cross-backend tests for common fields, relative paths, content-addressed arrays, parser-attempt accounting, deterministic JSON and source immutability.
- Added malformed Gmsh, OpenFOAM and VTK fixtures covering binary encodings, truncated sections, duplicate identifiers, count mismatches, negative labels, invalid connectivity and malformed XML.
- Added deterministic fault-injection tests proving that invalid backend payloads fail without crashing the parent process or mutating engineering sources.
- Kept ReflexCase schema `1.0` and backend-neutral contract `2.0-alpha.3`; the new Gate 5 envelope is additive inside execution summaries.
- Completed Gate 5 acceptance across the reusable runtime and all three native-reader families.

## 2.0.0a4 — Gate 5D native VTK inspection

- Added the isolated `vtk.native` execution backend.
- Added optional PyVista/VTK-first and meshio-second decoding for supported VTK datasets.
- Added dependency-free bounded readers for legacy ASCII VTK and single-piece XML VTK with inline ASCII or uncompressed inline base64 arrays.
- Added points, bounds, structured extents, rectilinear coordinate axes, cell connectivity, offsets and VTK cell-type evidence.
- Added point, cell and field data behind content-addressed lazy `ArrayRef` handles.
- Added `.pvd`, multiblock and parallel-file reference inventories with time values and no automatic external-reference loading.
- Added explicit fallbacks for malformed, binary, appended, compressed, unsafe-reference and dependency-limited inputs.
- Routed `deep` and `forensic` VTK inspection through the native backend.
- Kept coordinate and field units unresolved unless supplied by explicit evidence.
- Completed the Gate 5 native-reader line for OpenFOAM, Gmsh and VTK without adding spatial inference or physics validation.

## 2.0.0a3 — Gate 5C native Gmsh inspection

- Added the isolated `gmsh.native` execution backend.
- Added optional meshio-first decoding for supported `.msh` files.
- Added a dependency-free bounded ASCII parser for Gmsh MSH 2.x and 4.x.
- Added node, element, entity, physical-group and mesh-bound summaries.
- Added lazy arrays for node tags, coordinates, element tags/types, entity membership, physical membership and ragged connectivity.
- Added `NodeData` and `ElementData` fields and meshio point/cell data as bounded lazy arrays.
- Added safe declaration-only `.geo` inspection with restricted numeric evaluation and explicit non-execution of includes, loops, system calls, booleans and extrusions.
- Added fingerprint-only STEP/IGES/BREP handling by default and an explicit opt-in isolated Gmsh API path that never requests mesh generation.
- Added ordered meshio → core ASCII → fingerprint fallback records and stable Gmsh diagnostics.
- Routed `deep` and `forensic` Gmsh inspection through the native backend.
- Kept coordinate and field units unresolved unless supplied by evidence.

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
