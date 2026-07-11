# Gate 6B — Backend-to-Graph Mapping

Gate 6B translates native OpenFOAM, Gmsh and VTK execution evidence into the canonical Gate 6A spatial graph. The mapping layer is versioned as `caereflex.spatial-mapping/1.0`.

## Scope

The mapper consumes a validated `InspectionExecutionResult`, its backend summary and its registered `ArrayRef` handles. It emits a deterministic `SpatialGraphSnapshot` and can persist it through `SpatialStore`.

Supported native backends are:

- `openfoam.native`;
- `gmsh.native`;
- `vtk.native`.

`core.manifest-audit` is intentionally not a spatial mapping source.

## OpenFOAM mapping

The mapper creates a case dataset block, aggregate mesh-node, mesh-face and mesh-cell entities, and one patch entity for each explicit boundary entry. Coordinates, face connectivity, offsets, owner/neighbour membership and internal fields remain behind `ArrayRef` links.

OpenFOAM coordinates retain an unresolved frame because the native case does not establish origin, global basis, handedness or length unit.

## Gmsh mapping

Each decoded file receives its own dataset block and unresolved model frame. Mesh nodes and element-type aggregates remain distinct from geometry entities. Explicit Gmsh entities and physical groups become canonical geometry and grouping records. Membership relations are emitted only when native tags or `.geo` declaration members provide evidence.

The mapper does not claim that a Gmsh mesh entity discretises a geometry entity unless a later gate establishes that relation from explicit evidence.

## VTK mapping

Each dataset or collection receives its own dataset block. Point and cell-type aggregates are mapped separately. Collection references are inventory entities; referenced files are not loaded by the mapper.

A VTK frame becomes explicit only when both a finite origin and a linearly independent direction basis are present. Coordinate units remain unresolved unless separately evidenced.

## Persistence and ReflexCase integration

Deep and forensic native inspection automatically builds and persists a spatial snapshot in the shared CaeReflex state database. ReflexCase stores only compact graph references under `metadata.spatial_graph_refs` and compact mapping reports under `metadata.spatial_mapping`.

Mapping failures do not erase a successful native inspection. They emit `CRX-SPATIAL-MAP-001`, preserve the execution result and leave the case in partial-success posture where appropriate. Array ownership that cannot be supported emits `CRX-SPATIAL-MAP-ARRAY-001` and remains unmapped.

## Determinism and safety

Graph, frame, entity, relation and array-link identifiers are deterministic for the same case, manifest and native evidence. The mapper does not materialise arrays, mutate engineering sources, fetch references, execute solvers or infer missing units.

## Explicit exclusions

Gate 6B does not perform:

- cross-format equivalence;
- coordinate transformation or frame composition;
- adjacency, connectivity or non-manifold inference;
- geometric tolerance matching;
- axisymmetric interpretation;
- physics consistency checks;
- engineering validation, certification or design-safety assessment.
