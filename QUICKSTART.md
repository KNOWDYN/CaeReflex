# Quickstart

Check the installation, units backend, execution runtime and native backend inventory:

```bash
caereflex doctor
caereflex units parse "25 degC" --json
caereflex units convert 1 bar Pa --json
caereflex units check "m/s" velocity --name U --json
caereflex execution backends
caereflex scan examples/openfoam_cavity_native --out manifest.json
caereflex adapters probe examples/openfoam_cavity_native
```

Run the complete offline OpenFOAM native example:

```bash
caereflex examples list
caereflex examples run openfoam_cavity_native
caereflex inspect examples/openfoam_cavity_native \
  --adapter openfoam \
  --profile deep \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

The deep result uses `openfoam.native` when all five required `polyMesh` files are present. Inspect:

- `metadata.openfoam_native.mesh` for counts, bounds, patches and topology-array IDs;
- `metadata.openfoam_native.times` and `field_availability`;
- `metadata.openfoam_native.fields` for field/time records;
- `quantity_evidence` and `dimensional_checks` for `U`, `p` and `nu`;
- `metadata.inspection_execution.attempts` for native and fallback stages.

Query lazy values without embedding complete arrays in JSON:

```bash
caereflex arrays list
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays slice ARRAY_ID --start 0 --stop 100 --json
caereflex arrays reduce ARRAY_ID --operation mean --json
```

Incomplete legacy cases remain supported through the metadata-only fallback:

```bash
caereflex scan examples/openfoam_cavity_minimal --out minimal_manifest.json
caereflex execution run minimal_manifest.json \
  --source-root examples/openfoam_cavity_minimal \
  --backend core.manifest-audit \
  --json
```

Gate 5B decodes native OpenFOAM ASCII. Binary payloads are detected but not guessed. Includes, substitutions, code streams, coded boundary conditions and dynamic libraries are preserved literally and never expanded or executed.

Mock CrossRef path:

```bash
caereflex crossref attach examples/crossref_context/sample_case.json \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --out caereflex.with_literature.json
caereflex export bibtex caereflex.with_literature.json --out references.bib
```

A successful native read or dimensional check does not validate the model, prove convergence, assess mesh adequacy, certify the result or establish design safety.

See `docs/GATES_1_3_FOUNDATION.md`, `docs/GATE_4_DIMENSIONS_UNITS.md`, `docs/GATE_5A_SAFE_EXECUTION_RUNTIME.md`, `docs/GATE_5B_OPENFOAM_NATIVE.md`, `docs/CLI_FOUNDATION.md`, and `docs/ADAPTER_PLUGIN_CONTRACT.md`.
