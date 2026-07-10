# CLI reference

Current CLI command surface:

| Command | Purpose |
| --- | --- |
| `version` | Print the package version. |
| `doctor` | Report the Python environment, core dependencies, optional backends, contract version, and adapter capabilities. |
| `scan` | Build a bounded metadata-only case manifest without materialising large mesh or field arrays. |
| `inspect` | Discover, auto-select or explicitly select an adapter, inspect a simulation path, and emit ReflexCase outputs. |
| `inspect-gmsh` | Deprecated compatibility alias for Gmsh inspection. |
| `inspect-openfoam` | Deprecated compatibility alias for OpenFOAM inspection. |
| `inspect-vtk` | Deprecated compatibility alias for VTK inspection. |
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

## Bounded discovery

Use catalog mode before deep inspection:

```bash
caereflex doctor
caereflex scan examples/openfoam_cavity_minimal --out manifest.json
caereflex adapters probe examples/openfoam_cavity_minimal
```

`scan` accepts resource limits including `--max-files`, `--max-depth`, `--max-bytes-read`, and `--max-wall-time`. Reaching a limit produces an explicit diagnostic and a truncated manifest; it is never presented as a complete inspection.

## Inspection with manifest evidence

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter auto \
  --profile standard \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

The command producing an output successfully does not establish simulation validity, convergence, mesh adequacy, certification, or design safety. Review `inspection_flags`, discovery diagnostics, provenance, and raw source files before using the result for engineering decisions.

## Machine-readable output

Commands that expose `--json` emit JSON on standard output. Human-readable status text is suppressed in JSON mode so scripts can parse the result directly.

## Compatibility

The `inspect-gmsh`, `inspect-openfoam`, and `inspect-vtk` commands remain available during the migration to the unified `inspect --adapter ...` interface. New automation should use the unified command.
