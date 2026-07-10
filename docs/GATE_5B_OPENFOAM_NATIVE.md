# Gate 5B — OpenFOAM Native Reader

Gate 5B adds the first production backend on top of the Gate 5A execution substrate. It decodes native OpenFOAM ASCII mesh and field evidence inside the bounded subprocess worker.

## Release posture

- Package version: `2.0.0a2`.
- Contract version: `2.0-alpha.3`.
- ReflexCase schema version: `1.0`.
- OpenFOAM adapter plugin version: `1.2.0`.
- OpenFOAM execution backend version: `1.0.0`.

The contract and schema do not advance because Gate 5B uses the existing additive execution-result, diagnostic, quantity-evidence and `ArrayRef` contracts.

## Selection

A deep or forensic OpenFOAM inspection selects `openfoam.native` only when the manifest contains:

```text
constant/polyMesh/points
constant/polyMesh/faces
constant/polyMesh/owner
constant/polyMesh/neighbour
constant/polyMesh/boundary
```

Compressed `.gz` names satisfy the selection requirement. Incomplete OpenFOAM cases continue to use `core.manifest-audit`, preserving Gate 5A behaviour.

## Native mesh evidence

The backend decodes:

- point coordinates;
- face-to-point connectivity;
- owner labels;
- neighbour labels;
- boundary patch names, types, `startFace` and `nFaces`;
- point, face, internal-face, boundary-face, cell and patch counts;
- axis-aligned point bounds.

Heavy values are registered as immutable lazy arrays:

```text
points
face_offsets
face_points
owner
neighbour
```

Topology checks include:

- owner length equals face count;
- neighbour length does not exceed face count;
- face point labels are in range;
- owner/neighbour cell labels are non-negative;
- patch ranges lie within the face list;
- patch ranges do not overlap;
- patch coverage is compared with the boundary-face interval.

A topology warning does not become a validation claim. It marks the native result partial and preserves the decoded evidence with diagnostics.

## Native field evidence

The reader recognises scalar, vector, spherical-tensor, symmetric-tensor and tensor field classes. It records:

- field name and class;
- cell, face or point association;
- component count and component names;
- OpenFOAM dimension vector;
- quantity kind and canonical SI representation through Gate 4;
- uniform or nonuniform internal-field mode;
- boundary patch type and literal value summary;
- time directory and source path.

Uniform fields store one literal tuple with `logical_entity_count` metadata. Nonuniform fields store their declared tuples. Complete arrays remain outside ReflexCase and are accessed through `ArrayRef`.

## Time evidence

Numeric time directories are sorted numerically. The backend emits:

- available time directories;
- field names available at each time;
- one field record and optional lazy array per source field/time pair.

Gate 5B does not calculate temporal derivatives, run-to-run comparisons or long-series reductions. Those remain Gate 8 responsibilities.

## Dimensioned properties

Literal dimensioned entries in these dictionaries are inspected when present:

- `constant/transportProperties`;
- `constant/physicalProperties`;
- `constant/thermophysicalProperties`.

The reader reuses Gate 4 semantics and preserves ambiguous or conflicting quantities for human review.

## Non-execution boundary

The reader never expands or executes:

- `#include`, `#includeEtc` or `#includeIfPresent`;
- `$name` or `${name}` substitutions;
- `#calc`, `#eval` or `#codeStream`;
- coded boundary conditions;
- `dynamicCode`, code options or code libraries;
- dynamic-library declarations;
- OpenFOAM solvers, utilities or shell commands.

Detected constructs produce `CRX-OF-NATIVE-UNSAFE-001`, literal-source evidence and partial success.

## Binary files

Gate 5B detects `format binary` and NUL-bearing payloads but does not guess OpenFOAM architecture, label width, scalar width or compact face-list encoding. It returns `CRX-OF-NATIVE-BINARY-001` and a structured inventory fallback.

Binary native decoding may be introduced only with architecture-aware fixtures and cross-version tests. Renaming binary data as ASCII is not supported.

## Parser-attempt ledger

The backend records ordered stages:

```text
openfoam_native_mesh
openfoam_native_fields
openfoam_dimensioned_properties
```

When mesh decoding fails, the ledger records:

```text
openfoam_native_mesh [failed]
→ openfoam_structured_inventory [success]
```

Each failed or degraded route identifies information lost and the fallback used.

## Stable diagnostics

- `CRX-OF-NATIVE-MESH-001`
- `CRX-OF-NATIVE-TOPOLOGY-001`
- `CRX-OF-NATIVE-FIELD-001`
- `CRX-OF-NATIVE-DICTIONARY-001`
- `CRX-OF-NATIVE-BINARY-001`
- `CRX-OF-NATIVE-UNSAFE-001`

## Acceptance fixture

`examples/openfoam_cavity_native` contains:

- eight points;
- six faces;
- one cell;
- zero internal faces;
- three patches;
- times `0` and `1`;
- `U` and `p` fields at both times;
- uniform and nonuniform values;
- dimensioned kinematic viscosity `nu`.

## Gate lock

Gate 5B is complete only when:

1. the complete fixture selects `openfoam.native`;
2. incomplete legacy fixtures retain `core.manifest-audit`;
3. mesh counts, bounds, patches and topology arrays are exact;
4. field class, rank, dimensions, time and boundary metadata are exact;
5. uniform and nonuniform values are available through bounded arrays;
6. source files remain byte-for-byte unchanged;
7. unsafe constructs are detected without evaluation;
8. binary files return an explicit fallback rather than guessed values;
9. malformed mesh and field inputs cannot crash the parent process;
10. Python 3.10, 3.11 and 3.12 core CI passes.

## Explicitly deferred

- binary OpenFOAM mesh and field decoding;
- decomposed processor-domain reconstruction;
- mesh-quality metrics;
- cell-centre or face-normal derivation;
- spatial evidence graph construction;
- physics-consistency rules;
- convergence or validation assessment;
- solver execution or source mutation.
