# openfoam_cavity_minimal

This is a minimal OpenFOAM-like case-folder fixture for read-only parser tests. It keeps the familiar OpenFOAM layout while avoiding large meshes, solver logs, or generated outputs.

## Folder structure

```text
openfoam_cavity_minimal/
├── 0/
│   ├── U
│   └── p
├── constant/
│   ├── polyMesh/boundary
│   ├── transportProperties
│   └── turbulenceProperties
└── system/
    ├── controlDict
    ├── fvSchemes
    └── fvSolution
```

- `0/` contains initial field files such as velocity `U` and pressure `p`.
- `constant/` contains material/turbulence dictionaries and the minimal `polyMesh/boundary` patch listing.
- `system/` contains run-control and numerical-setting dictionaries.

## Inspect the example

```bash
mkdir -p build
caereflex inspect-openfoam examples/openfoam_cavity_minimal --out build/openfoam_case.json
```

Expected output snippet:

```text
Status: success
Case ID: case_...
OpenFOAM case inspected. 8 files were considered.
Outputs:
- caereflex_json: build/openfoam_case.json
```

Expected JSON highlights:

```json
{
  "case_type": "openfoam",
  "detected_formats": ["OpenFOAM case folder"],
  "detected_tools": ["OpenFOAM"],
  "result_fields": ["p", "U"]
}
```

## Missing or partial data warnings

This fixture includes the common files expected by the adapter, so the normal example should produce no missing-file warnings. If you remove files such as `system/controlDict`, `system/fvSchemes`, `system/fvSolution`, `constant/transportProperties`, `constant/turbulenceProperties`, or `constant/polyMesh/boundary`, CaeReflex should report warning-level inspection flags and may return `partial_success` rather than pretending the case is complete.

## CaeReflex does not run OpenFOAM

CaeReflex only reads and fingerprints files. It does **not** run `blockMesh`, `simpleFoam`, `pimpleFoam`, `foamToVTK`, or any OpenFOAM utility, and it does not confirm convergence, mesh adequacy, turbulence-model suitability, or engineering safety.

## Related documentation

- [CLI reference](../../docs/CLI.md)
- [REST API](../../docs/REST_API.md)
- [Agent integration](../../docs/AGENT_INTEGRATION.md)
- [Adapter guide](../../docs/ADAPTERS.md)
- [CrossRef literature metadata](../../docs/CROSSREF.md)
