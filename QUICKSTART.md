# Quickstart

Check the installation, units backend and case manifest before deep inspection:

```bash
caereflex doctor
caereflex units parse "25 degC" --json
caereflex units convert 1 bar Pa --json
caereflex units check "m/s" velocity --name U --json
caereflex scan examples/openfoam_cavity_minimal --out manifest.json
caereflex adapters probe examples/openfoam_cavity_minimal
```

Offline inspection path:

```bash
caereflex examples list
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

For the bundled OpenFOAM case, inspect `quantity_evidence`, `dimensional_checks`, and `units_summary`. The expected semantic reads include velocity `U`, incompressible kinematic pressure `p`, and kinematic viscosity `nu`. A successful dimensional check establishes compatibility only; it does not validate the model or result.

Mock CrossRef path:

```bash
caereflex crossref attach examples/crossref_context/sample_case.json \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --out caereflex.with_literature.json
caereflex export bibtex caereflex.with_literature.json --out references.bib
```

See `docs/GATES_1_3_FOUNDATION.md`, `docs/GATE_4_DIMENSIONS_UNITS.md`, `docs/CLI_FOUNDATION.md`, and `docs/ADAPTER_PLUGIN_CONTRACT.md` for the architecture and safety boundaries.
