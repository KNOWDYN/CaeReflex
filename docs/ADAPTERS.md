# Adapter Guide

CaeReflex adapters translate CAE-oriented inputs into a `ReflexCase` model. They are intentionally conservative: adapters inspect, fingerprint, and summarize evidence, but they do not run solvers or inspect engineering correctness.

## Adapter contract

Every adapter must follow the contract defined by `BaseAdapter`:

- Subclass `caereflex.adapters.base.BaseAdapter`.
- Implement `inspect(path: str | Path) -> AdapterResult`.
- Return an `AdapterResult` containing either:
  - a populated `ReflexCase` with `status` set to `success` or `partial_success`; or
  - an explicit `failed` / `unsupported` result with useful `errors` and inspection flags.
- Use `ReflexCase`, `SourceFileRecord`, `EngineeringAsset`, `InspectionFlag`, and trace/provenance records to describe what was inspected.
- Do **not** write reports, REST responses, case-store files, or UI output directly. Exporting and response formatting belong in services, exporters, CLI, or API layers.

## Auto-detection behavior

`caereflex.services.detect_adapter(path)` chooses an adapter from the path shape and suffixes:

1. If `path` is a directory and contains `system/controlDict`, `constant`, or `0`, it is detected as `openfoam`.
2. Otherwise, directory contents are scanned recursively for Gmsh-oriented suffixes: `.geo`, `.msh`, `.step`, `.stp`, `.iges`, `.igs`.
3. Otherwise, directory contents are scanned recursively for VTK-family suffixes: `.vtk`, `.vtu`, `.vtp`, `.vti`, `.vtr`, `.vts`.
4. If `path` is a file, suffix-based detection maps the Gmsh suffixes to `gmsh` and the VTK-family suffixes to `vtk`.
5. If no rule matches, `UnsupportedFormatError` is raised.

`inspect_path(..., adapter="auto")` uses this detector, then calls `inspect_with_adapter`. `inspect_with_adapter` registers the supported adapter names and aliases: `gmsh`, `openfoam`, `vtk`, plus `gmsh_adapter`, `openfoam_adapter`, and `vtk_adapter`.

## Gmsh adapter

`GmshAdapter` supports Gmsh-oriented geometry and mesh inputs with suffixes:

- `.geo`
- `.msh`
- `.step` / `.stp`
- `.iges` / `.igs`

### Core `.geo` inspection

For `.geo` files, the adapter performs text-based inspection and records:

- counts of declared `Point(...)`, `Line(...)`, and `Surface(...)` / `Plane Surface(...)` entries;
- the number of `Physical ...` groups;
- boundary-condition-like records for physical groups, using the group label, physical kind, and member list;
- source-file hashes and trace information.

This is structural extraction only. It does not evaluate CAD structure, mesh quality, geometric watertightness, or whether physical groups are complete.

### `.msh` fingerprinting and optional deeper inspection

For `.msh` files, the adapter always fingerprints the file and adds a mesh asset. If the optional mesh dependency stack is installed, it attempts to read the mesh with `meshio` and records basic metrics such as point count and cell-block count.

If `meshio` or compatible mesh support is unavailable, the adapter emits a warning that the `.msh` file was fingerprinted and that installing the `[mesh]` extra enables deeper inspection.

### CAD geometry fingerprinting

STEP and IGES-family files are treated as best-effort geometry inputs. The adapter fingerprints them and records geometry assets with a `best_effort_only` property. It does not parse the full CAD model.

### Safety limits and do-not-claim guidance

The adapter respects configured file-count and file-size limits while hashing and scanning. Its summaries include explicit do-not-claim guidance, including not claiming mesh adequacy, engineering correctness, or safety conclusions. Adapter output should be treated as evidence extracted from files, not as proof.

## OpenFOAM adapter

`OpenFOAMAdapter` inspects OpenFOAM case folders without requiring an OpenFOAM installation.

### Folder detection

Auto-detection treats a directory as OpenFOAM when any of the following exists under the directory:

- `system/controlDict`
- `constant`
- `0`

### Expected files and missing-file warnings

The adapter expects common case files:

- `system/controlDict`
- `system/fvSchemes`
- `system/fvSolution`
- `constant/transportProperties`
- `constant/turbulenceProperties`
- `constant/polyMesh/boundary`

Missing expected files are reported as warning-level `InspectionFlag` records. A case with useful extracted files can still be `partial_success` rather than failed.

The adapter also considers field files directly under `0/`, plus selected log or post-processing files (`log`, `log.simpleFoam`, and up to a bounded subset under `postProcessing`).

### Dictionary and field extraction

The adapter uses text parsing for OpenFOAM dictionaries and fields:

- `system/controlDict` creates a `SolverRecord` with application, start time, end time, and parsed metadata.
- `system/fvSchemes` and `system/fvSolution` create numerical-setting records.
- `constant/transportProperties` creates material-property records.
- `constant/turbulenceProperties` creates turbulence/numerical-setting records.
- `constant/polyMesh/boundary` extracts patch names and patch types as boundary-condition records.
- Files under `0/` create result-field records and boundary-condition records from `boundaryField` patch blocks.
- Solver-log-like lines such as residual text are flagged as informational evidence only.

### No solver execution

The OpenFOAM adapter never invokes OpenFOAM solvers or utilities. It does not run `blockMesh`, `simpleFoam`, `pimpleFoam`, `foamToVTK`, or any other executable. It only reads and fingerprints files.

## VTK adapter

`VTKAdapter` supports VTK-family result files with suffixes:

- `.vtk`
- `.vtu`
- `.vtp`
- `.vti`
- `.vtr`
- `.vts`

### Legacy `.vtk` core inspection

Legacy `.vtk` files receive lightweight text inspection. The adapter reads a bounded prefix and extracts:

- `DATASET` type;
- `POINTS` count;
- `CELLS` count;
- `SCALARS` field names as scalar point-associated result fields;
- `VECTORS` field names as vector point-associated result fields.

### Optional VTK/PyVista expectations

XML VTK-family files (`.vtu`, `.vtp`, `.vti`, `.vtr`, `.vts`) are fingerprinted in the core implementation. Deeper inspection is expected to require optional VTK/PyVista-style dependencies, and the adapter emits an informational flag indicating that installing the `[vtk]` extra enables deeper inspection.

### Result-field limitations

Field extraction is conservative. Legacy `.vtk` field association is recorded as point-associated for extracted scalar/vector declarations, and no derived physics, units, interpolation quality, or correctness claims are made. XML-family files are not deeply parsed by the core adapter.

## Hashing and path limits

Adapters use `CaeReflexConfig` safety limits:

- `max_file_size_mb`: maximum file size to hash/read fully through hashing helpers. Files above the byte limit can be recorded without a complete hash.
- `max_scan_depth`: intended maximum recursive scan depth for adapters and services that perform directory scans.
- `max_scan_files`: maximum number of relevant files to consider during adapter scans.

`HashStatus` meanings:

- `complete`: a SHA-256 hash was successfully computed.
- `skipped_large`: hashing was skipped because the file exceeded the configured size limit.
- `failed`: hashing was attempted but failed.
- `not_applicable`: no hash was expected or applicable for that record.

All recorded paths should be safe display paths rather than unbounded or unsafe filesystem disclosures.

## How to add an adapter

1. Create a new module, for example `caereflex/adapters/my_adapter.py`.
2. Implement a class that subclasses `BaseAdapter` and returns `AdapterResult` from `inspect(path)`.
3. Add auto-detection rules in `caereflex/services.py::detect_adapter`.
4. Register the adapter name and any aliases in `caereflex/services.py::inspect_with_adapter`.
5. Add a CLI command only if users need explicit CLI access beyond `adapter="auto"` or existing generic inspection commands.
6. Add tests for:
   - model structure: returned cases serialize as `ReflexCase` / `AdapterResult`;
   - partial-success inspection flags: missing optional dependencies or incomplete inputs produce inspection flags rather than false success;
   - path safety: unsafe, missing, oversized, or out-of-workspace paths are handled explicitly;
   - unsupported inputs: unsupported formats return or raise clear unsupported/failed results at the correct layer.

## Anti-patterns

Do not implement adapters that:

- execute solvers, preprocessors, mesh generators, converters, or external solver/checking tools as part of inspection;
- write reports, REST responses, case-store records, or arbitrary external files directly;
- bypass services/exporters for persistence or presentation;
- claim convergence, mesh adequacy, CAD structure, simulation correctness, certification, safety conclusions, or regulatory compliance;
- hide missing files or optional dependencies as successful deep inspection;
- return loosely structured dictionaries when a typed `AdapterResult` / `ReflexCase` record is required.
