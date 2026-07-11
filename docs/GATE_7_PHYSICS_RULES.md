# Gate 7 — deterministic physics-consistency rules

Gate 7 introduces `caereflex.physics-rule/1.0` and the first OpenFOAM CFD pack, `caereflex.openfoam-cfd/1.0.0`.

Each rule declares applicability, required evidence, assumptions, limitation, severity and remediation. Results use exactly six states: `consistent`, `inconsistent`, `unknown`, `not_applicable`, `not_evaluated` and `blocked`. Evidence is cited through absolute JSON pointers and source paths where available. Evaluation is deterministic, ordered and digestible.

The first pack checks:

- velocity dimensions for `U`;
- accepted thermodynamic or incompressible kinematic-pressure dimensions for `p`;
- kinematic-viscosity dimensions for `nu`;
- face/internal-face/boundary-face accounting;
- boundary patch coverage and overlap;
- field class versus spatial association.

Missing evidence never becomes a pass. Malformed required evidence blocks the rule. A rule implementation failure also becomes a deterministic `blocked` result rather than disappearing.

These checks are necessary evidence-consistency tests only. They do not establish convergence, mesh independence, turbulence-model suitability, numerical accuracy, experimental validation, certification or design safety.
