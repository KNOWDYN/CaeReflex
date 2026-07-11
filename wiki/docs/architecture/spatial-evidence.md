# Spatial evidence architecture

CaeReflex Gate 6A adds a backend-neutral spatial graph without collapsing geometry, mesh and dataset concepts into one object type.

## Why the graph is separate

ReflexCase remains the compact case-level evidence envelope. Spatial graphs may contain thousands or millions of entities and relations, so their metadata is stored in SQLite and their numerical arrays remain in the content-addressed artefact store.

ReflexCase therefore contains only compact graph references under `metadata.spatial_graph_refs`.

## Entity domains

Geometry entities are points, curves, surfaces, shells and volumes. Mesh entities are nodes, edges, faces and cells. Patches, physical groups and regions are grouping entities. Dataset blocks describe result-file structure.

These distinctions are contractual. A mesh entity can `discretises` a geometry entity, but the two records remain separate.

## Coordinate frames

Coordinate frames are evidence-bearing objects. CaeReflex records origin, basis, dimensionality, handedness, length-unit evidence, parent frame, affine parent transform, confidence and review status.

An unresolved frame has no assumed origin, axes, handedness or unit. This prevents a backend that merely supplies numbers from silently turning them into metres in a global right-handed Cartesian system.

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

Adjacency and connectivity are undirected. Other relations are directed.

## Array links

Coordinates, topology, membership and fields are referenced through registered `ArrayRef` objects. Spatial records contain only stable array IDs, content-addressed URIs, checksums, roles and component semantics.

The graph store does not contain BLOB columns and rejects oversized compact metadata.

## Persistence

`SpatialStore` uses the shared CaeReflex SQLite database. Foreign keys enforce graph scope, frame ownership, relation endpoints and array-link ownership. Transactional snapshot import prevents partially written graphs.

The store supports deterministic snapshot export and integrity checking, but Gate 6A does not yet perform backend mapping or spatial queries.

## Safety boundary

Spatial evidence does not establish geometric correctness, mesh adequacy, physical validity, coordinate-unit correctness or design safety. Unknown and conflicted frame information remains unknown or conflicted until explicit evidence or later human review resolves it.
