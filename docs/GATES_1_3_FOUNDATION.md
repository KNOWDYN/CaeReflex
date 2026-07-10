# Gates 1–3 foundation

This document describes the first CaeReflex 2.x foundation increment. It is deliberately limited to contracts, the CLI compatibility shell, and bounded case discovery. It does not claim that the existing Gmsh, OpenFOAM, or VTK parsers have already become physics-aware.

## Gate 1 — stable contracts and adapter protocol

CaeReflex now defines backend-neutral models for:

- evidence state and source location;
- scalar or structured evidence values;
- quantity evidence with seven-component dimension vectors;
- lazy references to large arrays;
- bounded inspection profiles and budgets;
- manifest entries and complete case manifests;
- stable diagnostic events;
- adapter capabilities, probes, and inspection plans;
- an entry-point-compatible adapter plugin protocol.

The contracts intentionally do not serialize objects from Pint, NumPy, VTK, Gmsh, OpenFOAM, Dask, or another native backend. Plugins translate backend-specific objects into these contracts.

The plugin entry-point group is:

```toml
[project.entry-points."caereflex.adapters"]
my_solver = "my_caereflex_plugin:plugin"
```

A plugin must remain read-only and declare its dependency, licence, format, geometry, topology, field, time-series, units, fallback, source-execution, and network capabilities.

## Gate 2 — CLI compatibility shell

The original commands remain available. The format-specific commands are compatibility aliases:

```bash
caereflex inspect-gmsh PATH
caereflex inspect-openfoam PATH
caereflex inspect-vtk PATH
```

New commands include:

```bash
caereflex doctor --json
caereflex scan PATH --json
caereflex adapters list
caereflex adapters info openfoam
caereflex adapters probe PATH
caereflex schema show
caereflex schema validate CASE.json
caereflex diagnostics list
caereflex diagnostics explain CRX-SCAN-LIMIT-001
caereflex cache clean
```

`caereflex inspect` now performs a bounded discovery pass first, records the manifest in the ReflexCase, and can emit it independently with `--manifest-out`.

The established `partial_success = 2` exit behaviour is retained in this PR to avoid breaking current automation. A later major-version migration may adopt a threshold-controlled exit contract after a formal deprecation period.

## Gate 3 — resolver and catalog mode

`caereflex scan` creates a metadata-only manifest. It does not load full meshes or result arrays.

The resolver currently identifies:

- Gmsh `.geo` and `.msh` artefacts;
- detected STEP and IGES geometry;
- OpenFOAM control files, dictionaries, initial fields, time fields, mesh folders, processor folders, and case roots;
- legacy, XML, parallel, collection, and multiblock VTK-family artefacts;
- common generic mesh, log, and literature files.

The scan is bounded by file count, directory depth, and wall time. Symbolic links are catalogued but never followed. Every limit and fallback produces a stable diagnostic event.

An optional SQLite catalog records the most recent manifest for each root and reports added, removed, changed, and unchanged paths. File content is not copied into the database.

## Scale boundary

A `CaseManifest` stores metadata only. Large coordinates, connectivity arrays, and field values must later be represented through `ArrayRef` and queried through adapter tools. They must not be embedded in ReflexCase JSON.

## Explicitly deferred

The following belong to subsequent gates:

- Pint-backed unit conversion and dimensional consistency;
- native Gmsh, VTK/PyVista, and OpenFOAM backends;
- parser-attempt and semantic-fallback logging inside each adapter;
- geometry and topology summaries derived from native backends;
- physics-model assertions and consistency rules;
- process-isolated deep inspection and distributed array reductions.
