# Physics-consistency rules

CaeReflex 2.0.0b4 adds deterministic evidence checks through `caereflex.physics-rule/1.0`.

## Inspect, then evaluate

```bash
caereflex inspect examples/openfoam_cavity_minimal \
  --adapter openfoam \
  --profile deep \
  --out cavity.caereflex.json

caereflex rules evaluate cavity.caereflex.json \
  --pack openfoam.cfd-core \
  --state-root ~/.caereflex \
  --out cavity.rules.json \
  --json
```

By default the report is attached under `metadata.physics_consistency.runs`. Use `--no-attach` to emit a standalone report.

## Reading statuses

`consistent` means the explicit evidence used by that rule agrees. `inconsistent` means explicit evidence conflicts. `unknown` means the rule applies but evidence is incomplete. `not_evaluated` means a required native profile or backend was not run. `blocked` means referenced evidence could not be verified. `not_applicable` means the rule is outside the case domain.

Do not collapse `unknown`, `not_evaluated` or `blocked` into success.

## OpenFOAM CFD core pack

Version 1.0.0 checks mesh topology cardinality, boundary-face partitioning, field cardinality, declared dimensional semantics, parsed patch references and time-control ordering.

It does not evaluate convergence, mesh quality or independence, turbulence-model suitability, boundary-condition suitability, experimental validation, physical accuracy, certification or design safety.
