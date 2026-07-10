# Native OpenFOAM cavity fixture

This is a deliberately small, offline and legally clean OpenFOAM ASCII fixture for Gate 5B.

It contains one hexahedral cell, eight points, six faces, no internal faces, three boundary patches, two time directories, scalar/vector fields and a dimensioned kinematic-viscosity property.

The fixture is designed to test evidence extraction only. It is not a converged simulation, a mesh-quality benchmark or a validation case.

```bash
caereflex inspect examples/openfoam_cavity_native \
  --adapter openfoam \
  --profile deep \
  --out native_case.json \
  --agent-context native_agent_context.json
```

Expected native mesh counts:

- points: 8
- faces: 6
- cells: 1
- internal faces: 0
- patches: 3
- times: `0`, `1`
