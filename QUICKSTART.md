# Quickstart

Check the installation, units backend, execution runtime and case manifest:

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
```

Run a bounded execution backend directly:

```bash
caereflex execution run openfoam-manifest.json \
  --source-root examples/openfoam_cavity_minimal \
  --backend openfoam.native \
  --json

caereflex execution run gmsh-manifest.json \
  --source-root examples/gmsh_minimal/t1.geo \
  --backend gmsh.native \
  --json

caereflex jobs list
```

Offline deep-inspection paths:

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter openfoam \
  --profile deep \
  --manifest-out openfoam-manifest.json \
  --out openfoam.caereflex.json

caereflex inspect examples/gmsh_minimal/t1.geo \
  --adapter gmsh \
  --profile deep \
  --manifest-out gmsh-manifest.json \
  --out gmsh.caereflex.json
```

For the bundled OpenFOAM case, inspect `quantity_evidence`, `dimensional_checks`, `units_summary`, `metadata.native_openfoam` and `metadata.inspection_execution`. Expected semantic reads include velocity `U`, incompressible kinematic pressure `p`, and kinematic viscosity `nu`.

For the bundled Gmsh file, inspect `metadata.native_gmsh`. The `.geo` file is parsed as declarations and is never executed. A decoded `.msh` can expose physical groups, entities, topology and fields through lazy array handles.

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

OpenFOAM and Gmsh native readers are bounded and read-only. VTK native decoding remains deferred. A successful execution or dimensional check does not validate the model, prove convergence, assess mesh adequacy, certify the result or establish design safety.

See `docs/GATES_1_3_FOUNDATION.md`, `docs/GATE_4_DIMENSIONS_UNITS.md`, `docs/GATE_5A_SAFE_EXECUTION_RUNTIME.md`, `docs/CLI_FOUNDATION.md`, and `docs/ADAPTER_PLUGIN_CONTRACT.md`.
