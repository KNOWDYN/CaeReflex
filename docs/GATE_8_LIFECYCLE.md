# Gate 8 — Lifecycle, temporal comparison, review and bounded services

Gate 8 adds an operational record layer around the existing immutable engineering evidence. It does not change ReflexCase schema `1.0` or inspection contract `2.0-alpha.3`.

## Versioned protocols

- `caereflex.lifecycle/1.0`
- `caereflex.temporal-comparison/1.0`
- `caereflex.human-review/1.0`
- `caereflex.async-job/1.0`

## Project, revision and run lifecycle

A project is a long-lived container for related engineering evidence. Each revision is an immutable canonical JSON snapshot of one ReflexCase, stored under the lifecycle state root with a SHA-256 digest. Revisions are ordered per project and may point to a parent revision.

Runs record operations such as inspection and temporal comparison. A run moves through a restricted state machine and emits append-only events. Terminal runs cannot be reopened or rewritten.

## Temporal comparisons

Comparisons operate on verified revision snapshots. They produce deterministic, JSON-pointer-addressed `added`, `removed` and `changed` records. Volatile timestamps are ignored by default. Results are sorted, bounded by `max_changes`, explicitly marked when truncated and protected by a comparison digest.

A temporal comparison reports structural evidence differences. It does not infer causality, physical significance, numerical correctness or design safety.

## Immutable human review

A human review is append-only. Existing review rows cannot be updated or deleted. A reviewer may supersede an earlier review only by creating a new record that points to it.

Each review contains a controlled decision, statement, evidence references, optional external-signature metadata, the previous review digest for the same target and its own canonical record digest.

CaeReflex preserves the review statement and chain. It does not verify the real-world identity, authority, competence or cryptographic signature of the reviewer unless a separately trusted identity and signature-verification layer is supplied.

## Asynchronous jobs

The local service supports bounded in-process jobs for inspection and temporal comparison. Worker and queue capacity are fixed when the service starts. Jobs use the existing persistent job store and create lifecycle runs.

This is a local executor, not a distributed queue. Work that was pending or running when a previous service process stopped is failed closed during recovery; jobs are not silently resumed.

## Bounded REST service

The REST surface now applies the following controls:

- all filesystem paths must remain within the configured workspace;
- non-localhost binding still requires an API key;
- request bodies are bounded, with a 1 MiB default;
- list responses are capped at 100 records;
- comparison details are capped at 500 changes;
- metadata, option maps, text fields and evidence-reference lists are bounded;
- worker counts are limited to 1–8 and queued jobs to 0–128;
- a full queue returns a conflict response rather than accepting unbounded work.

The existing synchronous case endpoints remain available. Gate 8 adds project, revision, run, comparison, review and asynchronous job endpoints without adding solver execution or source mutation.

## CLI examples

```bash
caereflex lifecycle version
caereflex lifecycle project-create "Pump optimisation"
caereflex lifecycle revision-create PROJECT_ID --case caereflex.json
caereflex lifecycle compare PROJECT_ID BASELINE_REVISION CANDIDATE_REVISION
caereflex lifecycle review-add PROJECT_ID comparison COMPARISON_ID reviewer-1 approved "Reviewed against the recorded evidence."
```

## Safety boundary

Gate 8 provides provenance-preserving workflow records. It does not validate simulations, prove convergence, establish mesh independence, authenticate reviewers, approve a design, certify compliance or replace qualified engineering judgement.
