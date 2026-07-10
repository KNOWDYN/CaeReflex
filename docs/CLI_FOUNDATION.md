# CLI foundation reference

## Diagnose the installation

```bash
caereflex doctor
caereflex doctor --json
```

The report includes CaeReflex and contract versions, Python and platform information, installed optional backends, and adapter capabilities.

## Catalog a case

```bash
caereflex scan CASE_PATH \
  --profile catalog \
  --max-files 500 \
  --max-depth 3 \
  --max-wall-time 30 \
  --out manifest.json
```

Use `--cache .caereflex/catalog.sqlite3` for incremental path-level comparisons. The cache contains manifest metadata, not CAE payloads.

## Probe adapters

```bash
caereflex adapters list
caereflex adapters info vtk
caereflex adapters probe CASE_PATH
```

Probe scores are routing evidence, not a claim that the case is physically correct or fully supported.

## Inspect with discovery context

```bash
caereflex inspect CASE_PATH \
  --adapter auto \
  --profile standard \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

The resulting ReflexCase contains `contract_version`, `inspection_profile`, a case manifest, and discovery diagnostics.

## Stable diagnostics

```bash
caereflex diagnostics list
caereflex diagnostics explain CRX-SCAN-LIMIT-001
```

Diagnostics are designed for both human users and machine automation. Empty diagnostics never imply engineering validation.

## Compatibility commands

The original format-specific commands remain operational during the migration:

```bash
caereflex inspect-gmsh PATH
caereflex inspect-openfoam PATH
caereflex inspect-vtk PATH
```
