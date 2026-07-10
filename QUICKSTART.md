# Quickstart

Check the installation, units backend, execution runtime and case manifests:

```bash
caereflex doctor
caereflex units parse "25 degC" --json
caereflex units convert 1 bar Pa --json
caereflex units check "m/s" velocity --name U --json
caereflex execution backends

caereflex scan examples/openfoam_cavity_minimal --out openfoam-manifest.json
caereflex adapters probe examples/openfoam_cavity_minimal
caereflex scan examples/gmsh_minimal/t1.geo --out gmsh-manifest.json
caereflex adapters probe examples/gmsh_minimal/t1.geo
caereflex scan examples/vtk_minimal/sample.vtk --out vtk-manifest.json
caereflex adapters probe examples/vtk_minimal/sample.vtk
```

Run bounded execution backends directly:

```bash
caereflex execution run openfoam-manifest.json \
  --source-root examples/openfoam_cavity_minimal \
  --backend openfoam.native \
  --json

caereflex execution run gmsh-manifest.json \
  --source-root examples/gmsh_minimal/t1.geo \
  --backend gmsh.native \
  --json

caereflex execution run vtk-manifest.json \
  --source-root examples/vtk_minimal/sample.vtk \
  --backend vtk.native \
  --json

caereflex jobs list
```

Offline deep-inspection paths:

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter openfoam \
  --profile deep \
  --out openfoam.caereflex.json

caereflex inspect examples/gmsh_minimal/t1.geo \
  --adapter gmsh \
  --profile deep \
  --out gmsh.caereflex.json

caereflex inspect examples/vtk_minimal/sample.vtk \
  --adapter vtk \
  --profile deep \
  --out vtk.caereflex.json
```

For OpenFOAM, inspect `quantity_evidence`, `dimensional_checks`, `units_summary`, `metadata.native_openfoam` and `metadata.inspection_execution`.

For Gmsh, inspect `metadata.native_gmsh`. A `.geo` file is parsed as declarations and is never executed. A decoded `.msh` can expose physical groups, entities, topology and fields.

For VTK, inspect `metadata.native_vtk`. Supported datasets can expose points, bounds, topology and point/cell/field arrays. Collections and parallel metadata expose reference and time inventories without hidden reference loading.

Query a registered array without embedding it in ReflexCase JSON:

```bash
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays reduce ARRAY_ID --operation mean --json
```

Mock CrossRef path:

```bash
caereflex crossref attach examples/crossref_context/sample_case.json \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --out caereflex.with_literature.json
caereflex export bibtex caereflex.with_literature.json --out references.bib
```

OpenFOAM, Gmsh and VTK native readers are bounded and read-only. Successful decoding or dimensional consistency does not validate the model, prove convergence, assess mesh adequacy, certify the result or establish design safety.

See `docs/GATES_1_3_FOUNDATION.md`, `docs/GATE_4_DIMENSIONS_UNITS.md`, `docs/GATE_5A_SAFE_EXECUTION_RUNTIME.md`, `docs/CLI_FOUNDATION.md`, and `docs/ADAPTER_PLUGIN_CONTRACT.md`.
