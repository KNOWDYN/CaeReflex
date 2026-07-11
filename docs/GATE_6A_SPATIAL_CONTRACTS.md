# Gate 6A — Spatial Contracts and Coordinate Frames

Gate 6A introduces the backend-neutral spatial evidence layer required before OpenFOAM, Gmsh and VTK evidence can be mapped into one graph.

It does **not** perform backend mapping, coordinate transformation, geometric inference, adjacency inference, physics consistency checks or engineering validation.

## Version posture

- Package version: `2.0.0b1`.
- ReflexCase schema: `1.0`.
- Backend-neutral inspection contract: `2.0-alpha.3`.
- Spatial graph format: `1.0`.

The spatial graph is independently versioned because it is persisted outside ReflexCase. ReflexCase stores only compact graph references under `metadata.spatial_graph_refs`.

## Canonical entity families

Geometry and mesh entities remain distinct:

| Domain | Canonical entity kinds |
| --- | --- |
| Geometry | point, curve, surface, shell, volume |
| Mesh | node, edge, face, cell |
| Grouping | patch, physical group, region |
| Dataset | dataset block |

A mesh face may discretise a geometric surface, but it is never silently converted into that surface. A Gmsh physical group, OpenFOAM patch and VTK block may later map to a common region, but Gate 6A does not assert that equivalence.

## Canonical relation kinds

- `contains`
- `bounded_by`
- `adjacent_to`
- `connected_to`
- `discretises`
- `belongs_to`
- `carries_field`
- `maps_to`
- `derived_from`

`adjacent_to` and `connected_to` are undirected. Other relation kinds are directed. Self-relations are rejected.

## Coordinate-frame contract

A coordinate frame records:

- frame identity and name;
- active dimension;
- origin;
- basis vectors;
- handedness;
- length unit and its evidence state;
- optional parent frame;
- optional affine transform to the parent;
- evidence status and confidence;
- source backend and source asset;
- review status;
- evidence records.

Frame evidence states are:

- `explicit`
- `derived`
- `user_supplied`
- `conflicted`
- `unresolved`

Unresolved frames keep origin, basis and length unit absent. CaeReflex does not silently assume a zero origin, Cartesian global axes, right-handed orientation or metres.

Resolved frames require an origin and a linearly independent basis. A resolved child frame also requires an explicit affine transform to its parent. Three-dimensional handedness is checked against the basis determinant. Lower-dimensional frames do not claim handedness.

## Compact bounds

Axis-aligned bounds are permitted as compact metadata only when they name their coordinate frame. Bounds do not establish units or orientation independently of that frame.

## Heavy-array boundary

Coordinates, connectivity, offsets, cell types, memberships, fields and transforms are represented by `SpatialArrayLink` records that point to registered `ArrayRef` objects.

Spatial metadata rejects:

- binary values;
- non-finite numbers;
- deeply nested objects;
- sequences larger than the compact-metadata threshold;
- non-content-addressed artefact URIs.

This prevents full industrial arrays from entering SQLite graph payloads, ReflexCase JSON or LLM context.

## SQLite repository

The default repository uses a local CaeReflex state database:

```text
.caereflex/catalog.sqlite3
```

Callers may supply another state root explicitly, including the shared configured CaeReflex state directory.

Tables are graph-scoped and enforce foreign keys between:

- graphs and coordinate frames;
- entities and frames;
- relations and entity endpoints;
- array links and their entity or frame owners.

The repository supports:

- graph creation;
- frame, entity, relation and array-link upserts;
- default-frame assignment;
- transactional snapshot import;
- deterministic snapshot export;
- compact counts and graph references;
- coordinate-frame parent-cycle checks;
- SQLite foreign-key integrity checks;
- graph deletion with cascading compact metadata removal.

Array payloads remain in the content-addressed artefact store. The spatial repository stores only array identifiers and compact reference metadata.

## ReflexCase integration

A graph is attached additively as a compact reference:

```json
{
  "metadata": {
    "spatial_graph_refs": [
      {
        "graph_id": "graph_case_1",
        "store_uri": "caereflex-spatial://sqlite/graph_case_1",
        "graph_version": "1.0",
        "frame_count": 1,
        "entity_count": 12,
        "relation_count": 18,
        "array_link_count": 4
      }
    ]
  }
}
```

The complete graph and arrays are never embedded in ReflexCase.

## Acceptance locks

Gate 6A is complete only when:

1. unresolved frames do not acquire implicit axes, origin, handedness or units;
2. resolved frames require finite, independent bases;
3. parent-frame cycles are rejected;
4. geometry and mesh domains remain distinct;
5. relation directionality is canonical;
6. all graph references are graph-scoped and foreign-key checked;
7. heavy arrays are linked through registered `ArrayRef` objects;
8. snapshot import is transactional;
9. snapshot export is deterministic;
10. existing Gate 5 inspection and native-reader tests remain unchanged and passing.

## Explicitly deferred

- OpenFOAM-to-graph mapping;
- Gmsh-to-graph mapping;
- VTK-to-graph mapping;
- cross-format entity equivalence;
- coordinate transformations and frame composition;
- spatial neighbourhood queries;
- adjacency and non-manifold inference;
- axisymmetric semantics;
- physics-consistency rules;
- human review history and overrides.
