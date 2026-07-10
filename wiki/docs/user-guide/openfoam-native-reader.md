# OpenFOAM native reader

CaeReflex `2.0.0a2` can decode native OpenFOAM ASCII mesh and field evidence without an OpenFOAM installation.

## Run the bundled case

```bash
caereflex inspect examples/openfoam_cavity_native \
  --adapter openfoam \
  --profile deep \
  --manifest-out manifest.json \
  --out case.json \
  --agent-context agent_context.json
```

A complete `polyMesh` selects the `openfoam.native` execution backend. Cases without all five required files retain the `core.manifest-audit` fallback.

Required paths:

```text
constant/polyMesh/points
constant/polyMesh/faces
constant/polyMesh/owner
constant/polyMesh/neighbour
constant/polyMesh/boundary
```

The corresponding `.gz` paths are recognised.

## Mesh evidence

Inspect `metadata.openfoam_native.mesh` for:

- point, face, internal-face, boundary-face, cell and patch counts;
- boundary patch names, types, `startFace` and `nFaces`;
- minimum and maximum point coordinates;
- lazy-array IDs for points, face offsets, face-point labels, owner and neighbour.

Query an array with:

```bash
caereflex arrays describe ARRAY_ID --json
caereflex arrays slice ARRAY_ID --start 0 --stop 24 --json
```

## Fields and time directories

`metadata.openfoam_native.fields` contains one record per field and time directory. Records include:

- field name and class;
- association and component count;
- dimensions, quantity kind and canonical SI representation;
- uniform or nonuniform internal mode;
- optional lazy-array ID;
- boundary patch summaries;
- source path and time index.

Time inventory and availability appear under:

```text
metadata.openfoam_native.times
metadata.openfoam_native.field_availability
```

## Units and properties

The native reader reuses Gate 4 semantics. It inspects dimensioned values in common property dictionaries and distinguishes incompressible kinematic pressure from thermodynamic pressure.

Ambiguous or conflicting dimensions remain explicit and require human review.

## Executable constructs

CaeReflex does not expand or execute OpenFOAM includes, substitutions, code streams, coded boundary conditions or dynamic libraries. These produce `CRX-OF-NATIVE-UNSAFE-001` and a partial result.

Binary files produce `CRX-OF-NATIVE-BINARY-001`. Gate 5B does not infer architecture, label width, scalar width, endian order or compact-list layout.

## Interpretation limits

Native decoding establishes what is represented in the source. It does not establish:

- convergence;
- mesh adequacy;
- numerical accuracy;
- physical-model suitability;
- experimental validation;
- engineering certification or safety.
