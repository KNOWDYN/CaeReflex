# Gate 6B — Backend-to-Graph Mapping

Gate 6B translates the frozen Gate 5 native-reader outputs into the canonical spatial graph introduced in Gate 6A.

## Scope

The mapping layer accepts successful `InspectionExecutionResult` payloads from:

- `openfoam.native`;
- `gmsh.native`;
- `vtk.native`.

It emits a deterministic `SpatialGraphSnapshot` containing coordinate-frame declarations, canonical entities, explicit relations and `ArrayRef`-backed heavy-array links.

## Safety posture

The mapper is evidence preserving rather than inferential.

It does not:

- assert that two backend objects are geometrically equivalent;
- infer metres, global axes, zero origins or right-handed coordinates;
- compose coordinate transforms;
- derive mesh adjacency or non-manifold status;
- judge mesh quality, convergence, physics validity or design safety.

Every backend-derived frame remains unresolved unless the source supplies explicit origin, basis, unit and handedness evidence.

## OpenFOAM mapping

The OpenFOAM mapper creates:

- one canonical mesh region for `polyMesh`;
- patch entities from `boundary` declarations;
- containment relations from the mesh region to patches;
- one dataset block for time-indexed fields;
- `carries_field` evidence from the mesh to the field block;
- ArrayRef links for points, face offsets, connectivity, owner, neighbour and decoded fields.

Patch membership is represented from declared face ranges. No face adjacency is derived.

## Gmsh mapping

The Gmsh mapper creates:

- one dataset block per decoded source;
- geometry entities from declaration or native entity evidence;
- physical-group entities;
- containment relations from the source block to mapped entities and groups;
- ArrayRef links for coordinates, connectivity, offsets, element types, memberships and fields when present.

Geometry and mesh identity remain distinct. Physical-group membership is not converted into cross-format semantic equivalence.

## VTK mapping

The VTK mapper creates one dataset block for each decoded dataset and links:

- points;
- cell connectivity;
- offsets;
- cell types;
- coordinate axes;
- point, cell and field arrays.

Collection and parallel-file inventories remain inventories until their referenced datasets are explicitly selected and decoded.

## Determinism and limits

Identifiers are derived from stable content-independent mapping keys. `MappingPolicy` bounds entity and relation counts. The same frozen execution result and case identifier produce the same graph snapshot.

## Deferred to Gate 6C

- bounded spatial queries;
- coordinate-frame transformation and composition;
- equivalent-geometry acceptance fixtures;
- neighbourhood and adjacency queries;
- disconnected and non-manifold diagnostics;
- 2D, 3D and axisymmetric semantic acceptance;
- cross-format mapping proposals and human confirmation.
