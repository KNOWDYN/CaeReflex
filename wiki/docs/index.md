# CaeReflex Wiki

CaeReflex is deterministic engineering-evidence infrastructure for Physics-AI. It converts OpenFOAM, Gmsh and VTK-family artefacts into provenance-preserving `ReflexCase` evidence, lazy heavy-data references, backend-neutral spatial graphs, deterministic physics-rule reports and governed lifecycle records for humans and AI systems.

!!! warning "Boundary of use"
    CaeReflex is an inspection, evidence and workflow-control system. It does not run solvers, validate simulations, prove convergence, certify engineering results, assess mesh adequacy, establish regulatory compliance or determine design safety.

## Platform spine

```text
engineering artefacts
  -> bounded discovery and native read-only inspection
  -> ReflexCase + provenance + dimensions + ArrayRef
  -> spatial graph + bounded spatial queries
  -> deterministic versioned physics-rule reports
  -> projects + immutable revisions + temporal comparison + human review
  -> Python | CLI | bounded REST/OpenAPI | reports | agent context
```

## Current release facts

| Fact | Value |
| --- | --- |
| Package version | `2.0.0b6` |
| ReflexCase schema version | `1.0` |
| Backend-neutral inspection contract | `2.0-alpha.3` |
| Native reader families | OpenFOAM, Gmsh, VTK |
| Governed platform layers | Inspect, Structure, Reason, Govern |
| CLI command | `caereflex` |
| Primary model | `caereflex.core.models.ReflexCase` |
| Service spine | `caereflex.services` |
| REST app factory | `caereflex.server.app.create_app` |

## Supported evidence paths

- OpenFOAM case dictionaries, mesh topology, fields, dimensions and time inventories through bounded read-only inspection.
- Gmsh `.geo` declarations, supported `.msh` topology and fields, and safe CAD-like geometry fingerprinting.
- VTK legacy and supported XML-family datasets, collections, topology and fields with explicit fallbacks.
- Content-addressed lazy arrays for heavy coordinates, connectivity and field values.
- Backend-neutral spatial entities, coordinate frames, relations, bounds and bounded queries.
- Versioned deterministic physics-consistency rules with evidence pointers, limitations and remediation.
- Projects, immutable revisions, run histories, temporal comparisons, append-only human review and bounded local jobs.
- CrossRef metadata and available abstracts only when explicitly requested.

## Start here

- [Quickstart](user-guide/quickstart.md)
- [Spatial queries](user-guide/spatial-queries.md)
- [Architecture](architecture/index.md)
- [Services layer](architecture/services-layer.md)
- [Release controls](developer-guide/release-controls.md)
- [Release 2.0.0b6](releases/2.0.0b6.md)
