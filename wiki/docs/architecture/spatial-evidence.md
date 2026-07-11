# Spatial evidence architecture

CaeReflex Gates 6A–6B provide a backend-neutral spatial graph and deterministic native-backend mappings without collapsing geometry, mesh and dataset concepts into one object type.

## Why the graph is separate

ReflexCase remains the compact case-level evidence envelope. Spatial graphs may contain thousands or millions of entities and relations, so their metadata is stored in SQLite and their numerical arrays remain in the content-addressed artefact store.

ReflexCase therefore contains only compact graph references under `metadata.spatial_graph_refs` and compact mapping reports under `metadata.spatial_mapping`.

## Entity domains

Geometry entities are points, curves, surfaces, shells and volumes. Mesh entities are nodes, edges, faces and cells. Patches, physical groups and regions are grouping entities. Dataset blocks describe case, result-file and collection structure.

These distinctions are contractual. A mesh entity can later `discretises` a geometry entity, but the two records remain separate. Gate 6B does not invent that relationship from similar names or dimensions.

## Coordinate frames

Coordinate frames are evidence-bearing objects. CaeReflex records origin, basis, dimensionality, handedness, length-unit evidence, parent frame, affine parent transform, confidence and review status.

An unresolved frame has no assumed origin, axes, handedness or unit. OpenFOAM and Gmsh native coordinates therefore remain unresolved by default. VTK origin and direction can establish an explicit frame when both are finite and linearly independent, while the length unit still remains unresolved.

## Backend mappings

Gate 6B maps validated native summaries through `caereflex.spatial-mapping/1.0`:

- OpenFOAM: case block, aggregate nodes, faces and cells, explicit patches and lazy topology/field links;
- Gmsh: per-file block, geometry entities, mesh aggregates, physical groups and explicit tag-backed memberships;
- VTK: dataset blocks, point and cell aggregates, fields, structured metadata and collection-reference inventories.

Identifiers are deterministic for the same case, manifest and native evidence. Every graph records that cross-format equivalence was not asserted.

## Relations

The canonical relation vocabulary is:

- contains;
- bounded by;
- adjacent to;
- connected to;
- discretises;
- belongs to;
- carries field;
- maps to;
- derived from.

Adjacency and connectivity are undirected. Other relations are directed. Gate 6B emits only relations supported directly by the native summary; neighbourhood and equivalence inference remain deferred.

## Array links

Coordinates, topology, membership and fields are referenced through registered `ArrayRef` objects. Spatial records contain only stable array IDs, content-addressed URIs, checksums, roles and component semantics.

The graph store does not contain BLOB columns and rejects oversized compact metadata. Unmatched arrays remain valid in the array registry and are reported as unmapped rather than assigned speculatively.

## Persistence

`SpatialStore` uses the shared CaeReflex SQLite database. Foreign keys enforce graph scope, frame ownership, relation endpoints and array-link ownership. Transactional snapshot import prevents partially written graphs.

Deep and forensic native inspection automatically persists the mapped snapshot and attaches its compact reference to ReflexCase. Mapping failures preserve the native execution result and emit `CRX-SPATIAL-MAP-001`.

## Safety boundary

Spatial evidence does not establish geometric correctness, cross-format equivalence, mesh adequacy, physical validity, coordinate-unit correctness or design safety. Unknown and conflicted frame information remains unknown or conflicted until explicit evidence or later human review resolves it.
