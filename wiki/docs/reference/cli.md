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
| `spatial graphs` | List persisted canonical spatial graphs. |
| `spatial show` | Describe one graph with compact statistics and frames. |
| `spatial frames` | Filter coordinate frames by evidence and review state. |
| `spatial entities` | Filter entities by kind, domain, frame, dimension, name or source path. |
| `spatial relations` | Filter stored relations by endpoint, kind and direction. |
| `spatial neighbours` | Traverse recorded graph relations under depth and scan limits. |
| `spatial bounds` | Match entity bounds inside one exact named coordinate frame. |
| `spatial arrays` | List ArrayRef links by owner and spatial role. |
| `spatial validate` | Run the frozen Gate 6 compatibility checks. |
| `spatial version` | Print the spatial-query and Gate 6 freeze versions. |
| `adapters list` | List installed adapter capabilities. |
| `adapters info` | Show declared capabilities, dependencies, fallbacks, and licence metadata for one adapter. |
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

`units parse` and `units convert` use Pint. CaeReflex serialises ordinary JSON values only; Pint objects never appear in ReflexCase or agent payloads. Dimensional compatibility does not prove physical role.

OpenFOAM dimensions use `[mass length time temperature substance current luminosity]`. Gmsh and VTK coordinates and fields do not establish units by themselves, so native summaries preserve units as unresolved unless explicit evidence supplies them.

## Bounded discovery and safe execution

```bash
caereflex doctor
caereflex scan examples/openfoam_cavity_minimal --out openfoam-manifest.json
caereflex execution backends
```

`scan` accepts file, depth, byte and wall-time limits. The execution worker applies parent-enforced wall time, bounded serialised output, selected-path containment, source snapshots and Python-level network/process guards. This is defence in depth, not a complete operating-system sandbox.

## Native deep inspection

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter openfoam --profile deep \
  --out openfoam.caereflex.json
```

OpenFOAM uses `openfoam.native`, Gmsh uses `gmsh.native`, and VTK uses `vtk.native`. Deep and forensic inspection also persist a canonical spatial graph when mapping succeeds.

## Spatial queries

```bash
caereflex spatial graphs --state-root .caereflex
caereflex spatial show GRAPH_ID --state-root .caereflex --json
caereflex spatial entities GRAPH_ID --kinds mesh_cell,patch --state-root .caereflex
caereflex spatial relations GRAPH_ID --entity-id ENTITY_ID --direction both --state-root .caereflex
caereflex spatial neighbours GRAPH_ID ENTITY_ID --depth 2 --state-root .caereflex
caereflex spatial bounds GRAPH_ID --frame-id FRAME_ID \
  --minimum 0,0,0 --maximum 1,1,1 --state-root .caereflex
caereflex spatial arrays GRAPH_ID --owner-entity-id ENTITY_ID --state-root .caereflex
caereflex spatial validate GRAPH_ID --state-root .caereflex --json
```

Spatial responses are deterministic and bounded. Bounds are compared only in the exact requested frame; no transform or unit conversion is inferred. Neighbour traversal follows stored relations only. Array-link queries do not return numerical values.

## Jobs and arrays

```bash
caereflex jobs list
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays reduce ARRAY_ID --operation mean --json
```

Array queries are allowed only when declared by the `ArrayRef` and are capped by an element limit. Complete industrial arrays are never emitted into ReflexCase JSON or an LLM context.

## Machine-readable output

Commands exposing `--json` emit JSON on standard output. Human-readable status text is suppressed in JSON mode.

## Compatibility and limits of claims

The legacy format-specific aliases remain available. Schema-v1 ReflexCase payloads remain valid because all Gate 6 references are additive. Successful inspection, query or Gate 6 acceptance does not establish simulation validity, geometry validity, convergence, mesh adequacy, cross-format equivalence, certification or design safety.
