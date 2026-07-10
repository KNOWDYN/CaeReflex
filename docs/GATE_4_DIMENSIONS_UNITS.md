# Gate 4 — Dimensions, Units and Physics Semantics

Gate 4 adds dimensional meaning without turning CaeReflex into a solver, validation service or opaque inference engine.

## Architectural decision

Pint owns unit parsing, dimensionality and conversion. CaeReflex owns:

- the backend-neutral evidence schema;
- seven-component CAE dimension vectors;
- OpenFOAM dimension-vector extraction;
- quantity-name and dimension reconciliation;
- physics-semantic diagnostics;
- fallback and human-review behavior;
- agent-context compilation.

Pint objects are not serialized. `QuantityEvidence` contains only ordinary JSON-compatible values.

## Evidence priority

1. Explicit source dimension vectors.
2. Explicit source unit metadata.
3. Native field or property class.
4. Solver-specific documented convention.
5. Name-based disambiguation.
6. Unknown.

A lower-priority signal never overrides explicit dimensional evidence.

## OpenFOAM scope

The Gate 4 adapter reads:

- inline `FoamFile` class and object records;
- field `dimensions` vectors;
- dimensioned scalar entries in `transportProperties`;
- scalar, vector and common tensor rank from the field class;
- exact source path and line when available.

It does not execute includes, substitutions, macros, coded boundary conditions or solver commands. Unsupported syntax falls back to raw evidence plus diagnostics.

## Semantic states

- `consistent`: explicit dimensions support the resolved quantity meaning.
- `conflicted`: the name and dimensions disagree; automated interpretation is blocked.
- `unresolved`: evidence is insufficient or dimensionally ambiguous.
- `not_applicable`: dimensional checking does not apply.

A consistent result is not a physical-validation certificate.

## Diagnostic contract

- `CRX-UNITS-PARSE-001`
- `CRX-UNITS-DIMENSION-MISMATCH-001`
- `CRX-UNITS-AMBIGUOUS-001`
- `CRX-UNITS-UNRESOLVED-001`
- `CRX-UNITS-MISSING-001`

Diagnostics remain present in ReflexCase, reports and agent context. Raw source text is retained whenever parsing fails.

## Backward compatibility

- ReflexCase schema version remains `1.0`.
- Contract version advances additively to `2.0-alpha.2`.
- Existing fields and CLI commands remain available.
- Existing `discovery_diagnostics` agent-context data remains available alongside the unified `diagnostics` key.
- Gmsh and VTK behavior is unchanged by Gate 4.

## Acceptance demonstration

The bundled OpenFOAM cavity case must produce:

| Source | Field/property class | Quantity | Dimensions |
| --- | --- | --- | --- |
| `0/U` | `volVectorField` | velocity | `[0 1 -1 0 0 0 0]` |
| `0/p` | `volScalarField` | kinematic pressure | `[0 2 -2 0 0 0 0]` |
| `constant/transportProperties: nu` | dimensioned scalar | kinematic viscosity | `[0 2 -1 0 0 0 0]` |

No mismatch diagnostic should be emitted for those records. A deliberately malformed vector must produce `CRX-UNITS-PARSE-001`, preserve the field class and raw dimensions, and keep the human reviewer in control.

## Deferred

Gate 4 does not yet include:

- full OpenFOAM grammar and include resolution;
- native mesh topology;
- numerical plausibility ranges;
- coordinate-frame transformations;
- boundary-condition compatibility rules;
- derived dimensionless groups;
- temporal field statistics;
- human override persistence.
