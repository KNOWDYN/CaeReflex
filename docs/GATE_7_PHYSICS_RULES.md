# Gate 7 — deterministic physics-consistency rules

Gate 7 adds a versioned deterministic rule protocol and the first built-in OpenFOAM CFD rule pack. Rules consume only evidence already present in ReflexCase and the Gate 5 ArrayRef registry. They do not run solvers, mutate engineering sources or infer missing physics.

## Protocol

The protocol version is `caereflex.physics-rule/1.0`.

Every rule declares stable rule, pack and version identities; applicability; required evidence paths; assumptions; severity; remediation; and limitations. Every rule returns exactly one status:

- `consistent`: required evidence is present and mutually consistent;
- `inconsistent`: explicit evidence conflicts;
- `unknown`: the rule applies, but evidence is incomplete or unresolved;
- `not_applicable`: the rule is outside the case domain;
- `not_evaluated`: the required profile or backend was not produced;
- `blocked`: referenced evidence cannot be trusted or accessed.

Results retain exact JSON-pointer evidence paths and source paths. Heavy values remain behind content-addressed `ArrayRef` handles. Reports are strictly serialisable, deterministically ordered and assigned canonical SHA-256 digests.

## OpenFOAM CFD core pack 1.0.0

Pack ID: `openfoam.cfd-core`.

| Rule | Check |
| --- | --- |
| `OF-CFD-MESH-001` | Mesh counts, topology-array shapes, bounded label ranges and connectivity offsets. |
| `OF-CFD-BOUNDARY-001` | Patch ranges form a unique contiguous partition of boundary faces. |
| `OF-CFD-FIELD-001` | Internal-field tuple counts and ArrayRef shapes match explicit OpenFOAM associations. |
| `OF-CFD-DIMENSIONS-001` | Gate 4 quantity names and declared dimensions contain no explicit conflicts. |
| `OF-CFD-BC-001` | Parsed boundary records reference native patch names without contradictory patch types. |
| `OF-CFD-TIME-001` | Declared start/end times and numeric interval controls are ordered and positive. |

## Safety boundary

A `consistent` result means only that the evidence checked by that exact rule version is mutually consistent. Gate 7 does not establish convergence, mesh independence, mesh adequacy, turbulence-model suitability, discretisation-scheme suitability, boundary-condition suitability, experimental validation, physical accuracy, certification or design safety.

## CLI

```bash
caereflex rules packs --json
caereflex rules describe openfoam.cfd-core --json
caereflex rules evaluate case.caereflex.json \
  --pack openfoam.cfd-core \
  --state-root ~/.caereflex \
  --out case.with-rules.json \
  --json
```

The state root must contain the same registered content-addressed arrays referenced by the case when rules require bounded heavy-array verification.
