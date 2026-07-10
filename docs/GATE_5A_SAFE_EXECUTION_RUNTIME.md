# Gate 5A — Safe Execution Runtime, Artefacts and Lazy Arrays

Gate 5A implements the reusable execution substrate required before native OpenFOAM, Gmsh, VTK or future CAE backends are allowed to deepen inspection.

It does not add native geometry, mesh or field decoding. The only bundled execution backend is `core.manifest-audit`, which exercises the runtime using metadata already selected by an inspection plan.

## Release posture

- Package version: `2.0.0a1`.
- Contract version: `2.0-alpha.3`.
- ReflexCase schema version remains `1.0` because the additions remain optional and backward-compatible.
- Gate 4 dimensional evidence remains unchanged.

## Execution flow

```text
CaseManifest
+ InspectionPlan
+ InspectionBudget
+ ExecutionPolicy
        |
        v
parent executor
        |
        v
sanitised subprocess worker
        |
        v
allow-listed execution backend
        |
        +--> compact result metadata
        +--> immutable artefacts
        +--> lazy ArrayRef handles
        +--> parser-attempt ledger
```

The parent process owns timeout enforcement, worker termination, source snapshots, result validation and job persistence. The worker owns backend loading, Python-level network and child-process guards, optional POSIX resource limits and backend execution.

## Security boundary

The runtime is defence in depth, not a complete operating-system sandbox.

It provides:

- a dedicated subprocess per execution;
- sanitised environment variables by default;
- Python socket guards when network access is disabled;
- Python child-process and shell guards when subprocess access is disabled;
- POSIX address-space and CPU limits where supported;
- parent-enforced wall-time limits;
- bounded result size;
- planned-path containment;
- before-and-after source snapshots;
- separate state and output directories;
- no solver execution or source-writing API.

Native libraries may bypass Python-level guards. Backends that require stronger isolation must later declare and use a container, operating-system sandbox or institutional execution provider. Capability documentation must not describe the default worker as a complete sandbox.

## Parser-attempt ledger

Every worker result contains a versioned attempt record with:

- backend identity and version;
- stage;
- outcome;
- start, completion and elapsed time;
- exception type and message where applicable;
- diagnostics;
- fallback target and information lost;
- enforcement metadata.

Later native adapters must append their own ordered attempts, for example:

```text
native VTK backend
→ meshio fallback
→ structured header parser
→ fingerprint-only
```

## Content-addressed artefacts

The default local state layout is:

```text
.caereflex/
  artifacts/sha256/
  catalog.sqlite3
  jobs/
  cases/
```

Artefacts are identified by SHA-256. A payload is written through a temporary file, verified after storage and treated as immutable. SQLite stores only metadata, references and job records.

The artefact URI format is:

```text
caereflex-artifact://sha256/<64-hex-digest>
```

Source simulation directories are never used as artefact destinations.

## ArrayRef v2 additions

The original required fields remain unchanged:

- URI;
- format;
- shape;
- dtype;
- optional chunks and checksum;
- selection capabilities.

Gate 5A adds optional fields for:

- stable array identity;
- source asset and source path;
- field association;
- component names;
- quantity-evidence and coordinate-frame references;
- time index;
- byte order;
- backend and backend version;
- storage lifetime;
- permitted operations;
- provider metadata.

Complete industrial arrays remain outside ReflexCase JSON.

## Core raw-array provider

Gate 5A includes a small standard-library provider for deterministic tests and small generated arrays. It supports:

- signed and unsigned integers;
- `float32` and `float64`;
- booleans;
- flat indexing;
- bounded slices;
- deterministic sampling;
- streaming `min`, `max`, `mean`, `sum` and `count` reductions.

This provider is not intended to replace NumPy, VTK, meshio or solver-native data access. Native adapters may register new formats and providers while returning the same `ArrayRef` contract.

## CLI

```bash
caereflex execution backends
caereflex execution run manifest.json --source-root CASE_ROOT
caereflex jobs list
caereflex jobs show JOB_ID
caereflex arrays list
caereflex arrays describe ARRAY_ID
caereflex arrays sample ARRAY_ID --count 100
caereflex arrays slice ARRAY_ID --start 0 --stop 100
caereflex arrays reduce ARRAY_ID --operation mean
```

`caereflex inspect CASE --profile deep` runs the safe manifest-audit backend and records the execution result in case metadata. Native decoding is intentionally unavailable until PRs 34B–34D.

## Stable diagnostics

- `CRX-EXEC-START-001`
- `CRX-EXEC-BACKEND-001`
- `CRX-EXEC-TIMEOUT-001`
- `CRX-EXEC-CRASH-001`
- `CRX-EXEC-RESULT-001`
- `CRX-EXEC-SOURCE-MUTATION-001`
- `CRX-EXEC-SNAPSHOT-PARTIAL-001`
- `CRX-ARRAY-QUERY-001`
- `CRX-ARTIFACT-INTEGRITY-001`

## Acceptance locks

Gate 5A is complete only when:

1. the core package installs without native CAE dependencies;
2. a backend success, exception, timeout and process crash all become deterministic results;
3. the parent process survives worker failures;
4. source files remain unchanged in compliant-backend tests;
5. source changes are detected and invalidate the result;
6. artefacts are content-addressed, immutable and integrity-checked;
7. heavy values remain behind `ArrayRef`;
8. array queries enforce explicit operation and result-size limits;
9. jobs persist locally and can be inspected through the CLI;
10. Python 3.10, 3.11 and 3.12 core CI passes.

## Explicitly deferred

- native OpenFOAM polyMesh and field reading;
- native Gmsh/meshio geometry and topology;
- native VTK/PyVista data reading;
- spatial evidence graphs and coordinate frames;
- physics-consistency rule packs;
- asynchronous background queues;
- distributed execution;
- complete operating-system sandboxing.
