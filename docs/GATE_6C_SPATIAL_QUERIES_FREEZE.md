# Gate 6C — Spatial queries and acceptance freeze

Gate 6C closes the Gate 6 spatial-evidence line by adding a bounded read-only query service and a frozen acceptance contract over the spatial contracts introduced in Gate 6A and the native mappings introduced in Gate 6B.

## Version posture

- Package: `2.0.0b3`
- ReflexCase schema: `1.0`
- Inspection contract: `2.0-alpha.3`
- Spatial graph: `1.0`
- Spatial mapping: `caereflex.spatial-mapping/1.0`
- Spatial query: `caereflex.spatial-query/1.0`
- Gate 6 freeze: `caereflex.gate6.spatial/1.0`

## Query surface

`SpatialQueryService` provides deterministic bounded operations for:

- graph listing and graph description;
- coordinate-frame filtering;
- entity filtering by kind, domain, frame, topological dimension, name and source path;
- relation filtering and directional endpoint lookup;
- recorded-relation neighbourhood traversal;
- same-frame axis-aligned bounds matching;
- ArrayRef-link lookup by owner and semantic role.

Every response is strictly serialisable JSON, ordered by stable identifiers, subject to configured page, scan, traversal and serialised-size ceilings. Heavy arrays remain behind content-addressed handles.

## Coordinate and topology honesty

Bounds queries compare only entities already expressed in the requested named coordinate frame. Gate 6C does not compose transforms, convert units or compare unresolved frames. Neighbour traversal follows stored graph relations only; it does not infer adjacency from coordinates, connectivity or names.

## Acceptance freeze

`validate_spatial_snapshot` and `validate_spatial_store` freeze the following requirements:

- spatial graph, inspection-contract and mapping-version compatibility;
- deterministic ordering and strict JSON;
- no automated cross-format equivalence assertion;
- content-addressed ArrayRef links and shared registry presence;
- valid graph references and SQLite foreign keys;
- bounded deterministic query responses;
- preservation of the Gate 6 safety boundary.

The acceptance report includes a canonical SHA-256 digest of the snapshot. Acceptance means contract compatibility only. It does not establish geometry correctness, mesh quality, physics validity, convergence, certification or design safety.

## CLI

The `caereflex spatial` command group exposes:

- `graphs`
- `show`
- `frames`
- `entities`
- `relations`
- `neighbours`
- `bounds`
- `arrays`
- `validate`
- `version`

All data-bearing commands support `--json` and `--state-root`.

## Acceptance matrix

The dedicated Gate 6 workflow runs the complete Gate 6A, 6B and 6C deterministic suite on Python 3.10, 3.11 and 3.12. Existing Gate 5 and optional native-backend workflows remain required regressions.

## Explicit exclusions

Gate 6C does not add cross-format identity matching, coordinate-frame composition, tolerance-based geometric comparison, inferred adjacency, non-manifold analysis, axisymmetric interpretation, mesh-quality metrics, physics rule packs, engineering validation, REST spatial endpoints, remote graph databases or distributed query execution.
