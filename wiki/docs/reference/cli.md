# CLI reference

Current CLI command surface:

| Command | Purpose |
| --- | --- |
| `version` | Print the package version. |
| `doctor` | Report the Python environment, core dependencies, units backend, execution runtime, contract version, and adapter capabilities. |
| `scan` | Build a bounded metadata-only case manifest without materialising large mesh or field arrays. |
| `inspect` | Discover, inspect and export a case; `deep` and `forensic` profiles invoke the bounded native backend for OpenFOAM, Gmsh or VTK. |
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
| `arrays describe` | Show ArrayRef metadata and verified artefact size. |
| `arrays sample` | Return a deterministic bounded sample. |
| `arrays slice` | Return a bounded flat slice. |
| `arrays reduce` | Run a streaming min, max, mean, sum or count reduction. |
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

`units parse` and `units convert` use Pint. CaeReflex serialises ordinary JSON values only; Pint objects never appear in ReflexCase or agent payloads.

`units check` compares base dimensions, not names. A conflict emits `CRX-UNITS-DIMENSION-MISMATCH-001` and blocks automated interpretation until reviewed. Dimensional compatibility does not prove physical role.

OpenFOAM dimensions use `[mass length time temperature substance current luminosity]`. Gmsh and VTK coordinates and fields do not establish units by themselves, so native summaries preserve units as unresolved unless explicit evidence supplies them.

## Bounded discovery and safe execution

```bash
caereflex doctor
caereflex scan examples/openfoam_cavity_minimal --out openfoam-manifest.json
caereflex scan examples/gmsh_minimal/t1.geo --out gmsh-manifest.json
caereflex scan examples/vtk_minimal/sample.vtk --out vtk-manifest.json
caereflex execution backends
```

`scan` accepts `--max-files`, `--max-depth`, `--max-bytes-read`, and `--max-wall-time`. Reaching a limit produces an explicit truncated manifest.

Run completed native backends directly:

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
```

The worker applies parent-enforced wall time, bounded serialised output, selected-path containment, source snapshots and Python-level network/process guards. This is defence in depth, not a complete operating-system sandbox.

## Native deep inspection

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter openfoam --profile deep \
  --out openfoam.caereflex.json

caereflex inspect examples/gmsh_minimal/t1.geo \
  --adapter gmsh --profile deep \
  --out gmsh.caereflex.json

caereflex inspect examples/vtk_minimal/sample.vtk \
  --adapter vtk --profile deep \
  --out vtk.caereflex.json
```

OpenFOAM uses `openfoam.native`, Gmsh uses `gmsh.native`, and VTK uses `vtk.native`. Outputs include execution metadata, ordered parser attempts, diagnostics and bounded lazy-array references.

The Gmsh `.geo` path is declaration-only. VTK collection and parallel metadata are reference/time inventories only; they do not cause hidden external-reference loading.

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

Array queries are allowed only when declared by the `ArrayRef` and are capped by an element limit. Complete industrial arrays are never emitted into ReflexCase JSON or an LLM context.

## Machine-readable output

Commands exposing `--json` emit JSON on standard output. Human-readable status text is suppressed in JSON mode.

## Compatibility

The `inspect-gmsh`, `inspect-openfoam`, and `inspect-vtk` aliases remain available during migration to `inspect --adapter ...`. Schema-v1 ReflexCase payloads remain valid because Gate 5 contract extensions are additive.

Successful command execution does not establish simulation validity, geometry validity, convergence, mesh adequacy, certification or design safety.
