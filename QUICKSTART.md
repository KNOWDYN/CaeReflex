# Quickstart

Check the installation, units backend, execution runtime and case manifest:

```bash
caereflex doctor
caereflex units parse "25 degC" --json
caereflex units convert 1 bar Pa --json
caereflex units check "m/s" velocity --name U --json
caereflex execution backends
caereflex scan examples/openfoam_cavity_minimal --out manifest.json
caereflex adapters probe examples/openfoam_cavity_minimal
```

Run the safe manifest-audit worker directly:

```bash
caereflex execution run manifest.json \
  --source-root examples/openfoam_cavity_minimal \
  --backend core.manifest-audit \
  --json
caereflex jobs list
```

Offline inspection path:

```bash
caereflex examples list
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal \
  --profile deep \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

For the bundled OpenFOAM case, inspect `quantity_evidence`, `dimensional_checks`, `units_summary`, and `metadata.inspection_execution`. The expected semantic reads include velocity `U`, incompressible kinematic pressure `p`, and kinematic viscosity `nu`.

Gate 5A uses `core.manifest-audit`; it does not yet decode native OpenFOAM, Gmsh or VTK arrays. Later readers will register heavy values behind `ArrayRef` handles. When an array is available:

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

A successful execution or dimensional check does not validate the model, prove convergence, assess mesh adequacy, certify the result or establish design safety.

See `docs/GATES_1_3_FOUNDATION.md`, `docs/GATE_4_DIMENSIONS_UNITS.md`, `docs/GATE_5A_SAFE_EXECUTION_RUNTIME.md`, `docs/CLI_FOUNDATION.md`, and `docs/ADAPTER_PLUGIN_CONTRACT.md`.
