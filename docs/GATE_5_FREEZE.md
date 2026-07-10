# Gate 5 — Compatibility Freeze and Malformed-Input Acceptance

Gate 5 is complete only when the reusable execution runtime and every built-in native reader satisfy one shared result envelope and a deterministic malformed-input harness.

## Release posture

- Package: `2.0.0a5`
- ReflexCase schema: `1.0`
- Backend-neutral contract: `2.0-alpha.3`
- Gate 5 backend envelope: `caereflex.gate5.backend-result/1.0`

The Gate 5 envelope is additive. Backend-specific evidence remains under `metadata.backend_result.summary`; the common report appears at `summary.gate5_compatibility`.

## Frozen built-in backends

The following backends must expose the same compatibility field set:

- `core.manifest-audit`
- `openfoam.native`
- `gmsh.native`
- `vtk.native`

The report records backend and plugin identity, profile, read-only posture, source-execution posture, evidence status, relative-path posture and the counts of arrays, artefacts, diagnostics and parser attempts.

## Worker enforcement

Before persistence, the isolated worker validates the backend payload. It rejects:

1. non-object payloads or payloads without a summary object;
2. non-JSON values and non-finite floating-point values;
3. absolute, Windows-absolute or traversal-bearing source paths;
4. array and diagnostic counts that disagree with the execution context;
5. ArrayRef or artefact URIs outside the SHA-256 content-addressed store;
6. ArrayRef backend identities that disagree with the executing backend;
7. large raw numerical sequences under heavy-data keys;
8. excessive nesting or sequence size.

A violation produces `CRX-GATE5-COMPAT-001`, a failed execution result and worker exit code `1`. The parent process must remain operational and the inspected source must remain unchanged.

## Evidence-status vocabulary

| State | Meaning |
| --- | --- |
| `metadata_only` | The backend reported metadata without decoded heavy arrays. |
| `decoded` | Native evidence and one or more lazy arrays were registered without failed parser attempts. |
| `partially_decoded` | Lazy arrays were registered, but one or more parser attempts failed or fell back. |
| `fallback_only` | Native decoding failed and only bounded fallback or fingerprint evidence remains. |

These states describe inspection evidence, not engineering validity.

## Cross-backend acceptance harness

The common harness verifies that every frozen backend:

- emits the identical compatibility field set;
- preserves its backend-specific summary;
- uses relative source paths;
- externalises heavy arrays behind `ArrayRef`;
- uses content-addressed artefact URIs;
- reports array, artefact, diagnostic and attempt counts consistently;
- serialises as strict JSON without NaN or infinity;
- leaves source bytes unchanged.

## Malformed-input matrix

### OpenFOAM

- declared-count mismatches;
- binary mesh payloads;
- negative connectivity labels;
- unclosed face lists.

### Gmsh

- binary mesh headers;
- truncated node sections;
- duplicate node identifiers;
- unclosed sections.

### VTK

- binary legacy payloads without an optional reader;
- truncated point sections;
- invalid cell connectivity counts;
- malformed XML;
- appended XML without an optional reader.

### Backend payloads

- non-object payload;
- missing summary object;
- NaN/Infinity values;
- absolute and traversal-bearing paths;
- materialised heavy arrays;
- mismatched array and diagnostic counts.

Reader-level malformed inputs must degrade to explicit fallback evidence rather than crashing the parent. Contract-level payload violations must fail before persistence.

## Safety boundary

The compatibility freeze does not:

- execute OpenFOAM, Gmsh, ParaView or shell commands;
- fetch VTK collection references;
- repair malformed files;
- infer units or coordinate frames;
- assess mesh quality, convergence or physical validity;
- provide a complete operating-system sandbox.

Native libraries remain a separate trust boundary. Hostile or safety-critical files require stronger external isolation.

## Gate 5 completion lock

Gate 5 is locked only when all of the following pass:

1. Core CI on Python 3.10, 3.11 and 3.12.
2. Gate 5 freeze CI on Python 3.10, 3.11 and 3.12.
3. Optional meshio and PyVista/VTK reader jobs.
4. Optional meshio and Gmsh API reader jobs.
5. Source immutability checks for valid and malformed fixtures.
6. Strict JSON serialisation and compatibility-count checks.
7. No regression to the Gate 5A execution, artefact and lazy-array contracts.

Gates 6–8 may rely on this frozen envelope but must not reinterpret it as spatial truth, physics validation or project-level approval.
