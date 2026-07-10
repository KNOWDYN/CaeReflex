# CLI reference

Current CLI command surface:

| Command | Purpose |
| --- | --- |
| `version` | Print the package version. |
| `doctor` | Report the Python environment, units backend, execution backends, contract version and adapter capabilities. |
| `scan` | Build a bounded metadata-only case manifest without materialising large mesh or field arrays. |
| `inspect` | Discover and inspect a case; deep OpenFOAM inspection selects the native backend when a complete `polyMesh` is present. |
| `inspect-gmsh` | Deprecated compatibility alias for Gmsh inspection. |
| `inspect-openfoam` | Deprecated compatibility alias for OpenFOAM inspection. |
| `inspect-vtk` | Deprecated compatibility alias for VTK inspection. |
| `units parse` | Parse a quantity expression and normalise it to SI base units through Pint. |
| `units convert` | Convert a scalar value between dimensionally compatible units. |
| `units check` | Compare a unit's dimensions with a registered CaeReflex quantity kind. |
| `execution backends` | List installed isolated execution backends. |
| `execution run` | Execute a manifest and bounded inspection plan in a subprocess worker. |
| `jobs list` | List persistent local execution-job records. |
| `jobs show` | Show one execution-job record. |
| `arrays list` | List registered lazy arrays. |
| `arrays describe` | Show `ArrayRef` metadata and verified artefact size. |
| `arrays sample` | Return a deterministic bounded sample. |
| `arrays slice` | Return a bounded flat slice. |
| `arrays reduce` | Run a streaming min, max, mean, sum or count reduction. |
| `adapters list` | List installed adapter capabilities. |
| `adapters info` | Show the declared capabilities, dependencies, fallbacks and licence metadata for one adapter. |
| `adapters probe` | Build a manifest and report which installed adapters match it. |
| `schema show` | Print the generated ReflexCase JSON Schema. |
| `schema validate` | Validate a stored ReflexCase and report its schema and contract versions. |
| `diagnostics list` | List stable diagnostic codes. |
| `diagnostics explain` | Explain one diagnostic and the recommended human action. |
| `cache clean` | Remove cached case manifests from the SQLite catalogue. |
| `crossref search` | Search CrossRef metadata for a case. |
| `crossref attach` | Attach CrossRef metadata to a case. |
| `export agent-context` | Export agent-context JSON. |
| `export markdown` | Export a Markdown case report. |
| `export bibtex` | Export BibTeX references. |
| `serve` | Start the REST/OpenAPI server. |
| `examples list` | List bundled examples. |
| `examples run` | Run a bundled example workflow. |

## Dimensions and units

```bash
caereflex units parse "25 degC" --json
caereflex units convert 1 bar Pa --json
caereflex units check "m/s" velocity --name U --json
```

`units parse` and `units convert` use Pint for unit parsing, dimensionality and conversion. CaeReflex serialises only ordinary JSON values; Pint objects never appear in ReflexCase or agent payloads.

`units check` compares base dimensions, not names. A conflicting result exits with code `6`, emits `CRX-UNITS-DIMENSION-MISMATCH-001`, and blocks automated interpretation until a human reviews the source. A compatible result confirms dimensional compatibility only; it does not prove that the variable has the intended physical role.

OpenFOAM dimensions use `[mass length time temperature substance current luminosity]`. CaeReflex preserves the original vector and derives a canonical SI representation without erasing distinctions such as pressure versus incompressible kinematic pressure.

## Bounded discovery and execution

```bash
caereflex doctor
caereflex scan examples/openfoam_cavity_native --out manifest.json
caereflex adapters probe examples/openfoam_cavity_native
caereflex execution backends
```

`scan` accepts `--max-files`, `--max-depth`, `--max-bytes-read` and `--max-wall-time`. Reaching a limit produces an explicit diagnostic and a truncated manifest.

The worker uses parent-enforced wall time, bounded serialised output, selected-path containment, source snapshots and Python-level network/process guards. This is defence in depth, not a complete operating-system sandbox.

## Native OpenFOAM inspection

```bash
caereflex inspect examples/openfoam_cavity_native \
  --adapter openfoam \
  --profile deep \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

A complete ASCII `polyMesh` selects `openfoam.native`. The output adds:

- `metadata.openfoam_native.mesh`;
- `metadata.openfoam_native.times`;
- `metadata.openfoam_native.field_availability`;
- `metadata.openfoam_native.fields`;
- native `ArrayRef` records;
- quantity evidence and dimensional checks;
- native and fallback parser attempts.

Incomplete OpenFOAM cases continue to use `core.manifest-audit`. Binary payloads and executable or expandable constructs are not guessed or executed; they produce explicit diagnostics and fallbacks.

The native backend can also be selected for a direct execution command when the manifest includes all required files:

```bash
caereflex execution run manifest.json \
  --source-root examples/openfoam_cavity_native \
  --backend openfoam.native \
  --plugin-id openfoam \
  --json
```

## Jobs and arrays

```bash
caereflex jobs list
caereflex jobs show JOB_ID --json
caereflex arrays list
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays slice ARRAY_ID --start 0 --stop 100 --json
caereflex arrays reduce ARRAY_ID --operation mean --json
```

Array queries are allowed only when declared by the `ArrayRef` and are capped by a result-element limit. Coordinates, connectivity and internal fields remain outside ReflexCase JSON.

## Machine-readable output

Commands exposing `--json` emit JSON on standard output. Human-readable status text is suppressed so scripts can parse the result directly.

## Compatibility

The `inspect-gmsh`, `inspect-openfoam` and `inspect-vtk` commands remain available during migration to the unified interface. Existing schema-v1 ReflexCase payloads remain valid because Gate 5B uses additive metadata and existing contracts.

Successful native decoding does not establish simulation validity, convergence, mesh adequacy, physical-model suitability, certification or design safety.
