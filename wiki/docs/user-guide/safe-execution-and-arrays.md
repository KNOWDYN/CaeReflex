# Safe execution and lazy arrays

CaeReflex 2.0 alpha separates lightweight discovery from bounded deep inspection. Native or high-cost readers run through an execution plan in a subprocess rather than inside the CLI or REST process.

## Inspect with the deep profile

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --profile deep \
  --manifest-out manifest.json \
  --out case.json
```

In `2.0.0a1`, this uses `core.manifest-audit`. It verifies the execution path and records a job and parser attempt, but it does not yet decode native mesh or field arrays.

The case metadata contains:

- execution and job IDs;
- selected backend and version;
- status and elapsed time;
- relative paths accessed;
- bytes read;
- diagnostics;
- parser-attempt records;
- registered artefacts and arrays.

## Run an execution plan directly

First produce a manifest:

```bash
caereflex scan CASE_ROOT --out manifest.json
```

Then run the core audit backend:

```bash
caereflex execution run manifest.json \
  --source-root CASE_ROOT \
  --backend core.manifest-audit \
  --json
```

List available execution backends with:

```bash
caereflex execution backends
```

Execution backends are loaded only from built-in registrations or the `caereflex.execution_backends` Python entry-point group. A request cannot supply an arbitrary import path.

## Inspect jobs

```bash
caereflex jobs list
caereflex jobs show JOB_ID --json
```

Job records are stored in `.caereflex/catalog.sqlite3`. Worker request, result and log files are stored under `.caereflex/jobs/JOB_ID/`.

Jobs are synchronous in Gate 5A. Persistent queues, cancellation and resumable background execution belong to Gate 8.

## Artefact storage

Generated heavy data is written under:

```text
.caereflex/artifacts/sha256/
```

The source simulation directory is not used as an output directory. Payloads are addressed by SHA-256 and verified before use.

Do not manually edit files in the artefact store. An integrity mismatch invalidates the artefact.

## Query lazy arrays

Discover registered arrays:

```bash
caereflex arrays list
caereflex arrays describe ARRAY_ID --json
```

Request bounded data:

```bash
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays slice ARRAY_ID --start 0 --stop 100 --json
caereflex arrays reduce ARRAY_ID --operation mean --json
```

Every `ArrayRef` declares its permitted operations. CaeReflex rejects unsupported operations and requests that exceed the configured return limit.

The core raw-array provider is intended for deterministic tests and small generated data. Later native adapters will provide format-specific lazy access without embedding complete industrial arrays in ReflexCase JSON.

## Security boundary

The default worker provides:

- subprocess isolation;
- parent-enforced timeout;
- sanitised environment variables;
- Python-level network and child-process guards;
- POSIX memory and CPU limits where available;
- selected-path containment;
- before-and-after source snapshots;
- bounded serialized results.

This is not a complete operating-system sandbox. Native libraries may bypass Python-level guards. Use stronger external isolation for hostile inputs or institutional production environments.

CaeReflex remains read-only by product policy and does not run solvers, mutate simulation sources, validate results, prove convergence or assess design safety.
