# Dimensions and units

CaeReflex treats dimensions and units as evidence, not as decorations attached after parsing. Explicit source dimensions take precedence over variable names, solver conventions, and semantic inference.

## Dimension-vector convention

OpenFOAM and the CaeReflex schema use seven SI base dimensions in this order:

```text
[mass length time temperature amount-of-substance electric-current luminous-intensity]
```

Examples:

| Quantity | Dimension vector |
| --- | --- |
| Velocity | `[0 1 -1 0 0 0 0]` |
| Thermodynamic pressure | `[1 -1 -2 0 0 0 0]` |
| Incompressible kinematic pressure | `[0 2 -2 0 0 0 0]` |
| Kinematic viscosity | `[0 2 -1 0 0 0 0]` |
| Temperature | `[0 0 0 1 0 0 0]` |

CaeReflex deliberately distinguishes thermodynamic pressure from the pressure divided by density used by common incompressible OpenFOAM solvers.

## Pint backend

Pint performs unit parsing, dimensionality calculations and conversion. CaeReflex converts Pint results into backend-neutral JSON containing magnitudes, unit strings and dimension vectors. Pint objects are never serialized into `ReflexCase`.

```bash
caereflex units parse "1 bar" --json
caereflex units convert 25 degC K --json
caereflex units check "m/s" velocity --name U --json
```

Offset temperatures are treated as absolute quantities when entered as a scalar and unit, so `25 degC` normalizes to `298.15 K`. Temperature differences require an explicit delta unit such as `delta_degC`.

## Evidence states

A dimensioned quantity records:

- the raw source text;
- the parsed magnitude where it is a scalar literal;
- the original dimension vector;
- a canonical SI unit representation;
- the semantic resolution method;
- source path and line when available;
- warnings and diagnostics;
- whether automated interpretation is blocked.

Canonical SI units derived from a dimension vector do not imply that the original source declared that exact unit symbol. The raw dimension vector remains authoritative.

## Semantic resolution

CaeReflex resolves a physical quantity conservatively:

1. Read explicit source dimensions.
2. Compare those dimensions with the registered quantity ontology.
3. Use the source name only to disambiguate dimensionally compatible meanings.
4. Emit `conflicted` when name and dimensions disagree.
5. Emit `unresolved` when the evidence is insufficient.
6. Never replace missing dimensions with a name-based default.

Several quantities share the same dimensions. For example, kinematic pressure, specific energy and turbulence kinetic energy all use `[0 2 -2 0 0 0 0]`. The name, field class and solver context are needed to distinguish them.

## Diagnostics and human control

Important diagnostics include:

| Code | Meaning |
| --- | --- |
| `CRX-UNITS-PARSE-001` | The expression could not be parsed; raw text was preserved. |
| `CRX-UNITS-DIMENSION-MISMATCH-001` | The name and explicit dimensions conflict. |
| `CRX-UNITS-AMBIGUOUS-001` | Multiple quantity meanings share the dimensions. |
| `CRX-UNITS-UNRESOLVED-001` | No registered semantic meaning could be established. |
| `CRX-UNITS-MISSING-001` | A field had no parseable dimensions declaration. |

A dimension mismatch blocks automated physical interpretation. The user should inspect the source, solver convention, scaling and any human annotations before accepting a meaning.

## OpenFOAM extraction

For supported OpenFOAM field files, CaeReflex now reads the `FoamFile` class and `dimensions` declaration independently. This prevents a scalar field from being classified as a vector merely because it has dimensions.

For `transportProperties`, dimensioned scalar entries such as:

```text
nu [0 2 -1 0 0 0 0] 0.01;
```

become structured evidence for kinematic viscosity while preserving the complete raw record.

The parser remains read-only and does not execute includes, macros, code blocks or solver commands.

## Limits

Dimensional consistency is necessary but not sufficient for physical correctness. A dimensionally valid value may still be numerically implausible, applied to the wrong region, expressed in the wrong reference frame, or inconsistent with the governing model. Gate 4 does not claim full physics validation.
