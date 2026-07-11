# Backend-to-Graph Mapping

Gate 6B converts frozen Gate 5 native-reader evidence into Gate 6 spatial graph snapshots.

## Entry point

```python
from caereflex.spatial import map_execution_result

snapshot = map_execution_result(
    execution_result,
    case_id="case-123",
    source_manifest_id="manifest-123",
)
```

The accepted backends are `openfoam.native`, `gmsh.native` and `vtk.native`.

## Mapping rules

The mapper uses only explicit reader summaries and `ArrayRef` records. Stable identifiers are derived from the case, execution, backend, source path and native identifiers.

OpenFOAM patches become grouping entities beneath one mesh region. Gmsh declaration/native entities and physical groups remain separate. VTK decoded datasets become dataset blocks. Heavy coordinates, topology and fields remain content-addressed array links.

## Coordinate frames

Each decoded source receives an unresolved coordinate frame unless explicit frame evidence is available. File-local coordinates are not silently promoted to a shared global Cartesian system.

## Non-claims

The mapping layer does not assert cross-format equivalence, infer adjacency, compose transforms, assess mesh quality, validate physics or certify a design.
