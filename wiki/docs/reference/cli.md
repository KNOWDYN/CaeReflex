# CLI reference

Current CLI command surface:

| Command | Purpose |
| --- | --- |
| `version` | Print the package version. |
| `doctor` | Report the Python environment, core dependencies, units backend, optional backends, contract version, and adapter capabilities. |
| `scan` | Build a bounded metadata-only case manifest without materialising large mesh or field arrays. |
| `inspect` | Discover, auto-select or explicitly select an adapter, inspect a simulation path, and emit ReflexCase outputs. |
| `inspect-gmsh` | Deprecated compatibility alias for Gmsh inspection. |
| `inspect-openfoam` | Deprecated compatibility alias for OpenFOAM inspection. |
| `inspect-vtk` | Deprecated compatibility alias for VTK inspection. |
| `units parse` | Parse a quantity expression and normalise it to SI base units through Pint. |
| `units convert` | Convert a scalar value between dimensionally compatible units. |
| `units check` | Compare a unit's dimensions with a registered CaeReflex quantity kind. |
| `adapters list` | List installed adapter capabilities. |
| `adapters info` | Show the declared capabilities, dependencies, fallbacks, and licence metadata for one adapter. |
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

OpenFOAM dimensions are represented in the order `[mass length time temperature substance current luminosity]`. CaeReflex preserves the original vector and derives a canonical SI unit representation. That representation does not erase the distinction between pressure and incompressible kinematic pressure.

## Bounded discovery

Use catalog mode before deep inspection:

```bash
caereflex doctor
caereflex scan examples/openfoam_cavity_minimal --out manifest.json
caereflex adapters probe examples/openfoam_cavity_minimal
```

`scan` accepts resource limits including `--max-files`, `--max-depth`, `--max-bytes-read`, and `--max-wall-time`. Reaching a limit produces an explicit diagnostic and a truncated manifest; it is never presented as a complete inspection.

## Inspection with manifest and dimensional evidence

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter auto \
  --profile standard \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

The output includes `quantity_evidence`, `dimensional_checks`, and diagnostics. The command producing output successfully does not establish simulation validity, convergence, mesh adequacy, certification, or design safety. Review conflicts, unresolved dimensions, inspection flags, provenance, and raw source files before using the result for engineering decisions.

## Machine-readable output

Commands that expose `--json` emit JSON on standard output. Human-readable status text is suppressed in JSON mode so scripts can parse the result directly.

## Compatibility

The `inspect-gmsh`, `inspect-openfoam`, and `inspect-vtk` commands remain available during the migration to the unified `inspect --adapter ...` interface. New automation should use the unified command.
