# Native OpenFOAM inspection

CaeReflex `2.0.0a2` adds an isolated, read-only OpenFOAM reader for deep and forensic profiles.

```bash
caereflex inspect CASE_ROOT \
  --adapter openfoam \
  --profile deep \
  --out case.json \
  --agent-context agent_context.json
```

The resulting case records `metadata.inspection_execution`, `metadata.native_openfoam`, parser attempts, diagnostics and lazy array references.

## Supported native evidence

For bounded ASCII cases, the reader can decode:

- `constant/polyMesh/points`;
- `constant/polyMesh/faces`;
- `constant/polyMesh/owner`;
- `constant/polyMesh/neighbour`;
- `constant/polyMesh/boundary`;
- scalar, vector, spherical-tensor, symmetric-tensor and tensor internal fields;
- uniform and nonuniform `internalField` values;
- available numerical time directories;
- field dimensions and class metadata.

Mesh coordinates, connectivity, ownership and field values are stored as content-addressed artefacts and exposed through `ArrayRef` handles.

```bash
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays reduce ARRAY_ID --operation min --json
```

## Fallback behaviour

Binary files, malformed counted lists, includes, code streams and unsupported grammar are not executed or guessed. CaeReflex records an ordered failed parser attempt, identifies the fallback and states what information was lost.

Relevant diagnostics include:

- `CRX-OPENFOAM-NATIVE-FALLBACK-001`;
- `CRX-OPENFOAM-FIELD-FALLBACK-001`.

A successful worker status can still contain field-level fallback diagnostics. Review the attempt ledger before treating a case as fully decoded.

## Important limits

The native reader does not:

- run OpenFOAM solvers or utilities;
- expand `#include` or `#codeStream` directives;
- load OpenFOAM shared libraries;
- infer missing coordinate units;
- prove topology validity;
- validate boundary-condition suitability;
- prove convergence, mesh independence or physical accuracy.

The current core reader targets bounded ASCII evidence. Binary and decomposed parallel cases remain future work unless an optional backend is added later.
