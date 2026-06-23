# ReflexCase schema

`ReflexCase` is the canonical interchange object for CaeReflex case inspection output. This document is derived from `caereflex/core/models.py`; when the Python model and this document disagree, update this document to match the model.

## Purpose and lifecycle

A `ReflexCase` captures what CaeReflex can safely know about a computational engineering workspace after one or more adapters inspect it. It is intentionally descriptive rather than authoritative: it records detected files, inferred engineering assets, solver settings, result fields, literature metadata, review flags, provenance, exports, and agent-facing summaries.

Typical lifecycle:

1. **Create**: an adapter or orchestration layer creates a `ReflexCase` with a required `case_id`; defaults fill timestamps, schema version, workspace, inspection state, and empty collections.
2. **Inspect**: adapters populate `source_files`, `assets`, solver-related records, result fields, and review-oriented `inspection_flags`. Each extracted or inferred item should carry `trace` metadata when practical.
3. **Enrich**: optional enrichers can add external metadata such as CrossRef literature evidence and update `literature_context`.
4. **Summarize/export**: agents or exporters can populate `agent_summary`, `exports`, and `provenance` records.
5. **Consume**: downstream consumers should treat absent optional collections as normal, use provenance and trace confidence to decide how much to trust a record, and avoid treating review prompts as correctness evidence.

## `ReflexCase` field table

| Field | Type | Default | Meaning | Typical producer |
|---|---|---|---|---|
| `schema_version` | `str` | `"1.0"` | Version of the serialized `ReflexCase` schema. | Core model/orchestrator |
| `case_id` | `str` | Required | Stable identifier for the inspected case. | Orchestrator/adapter |
| `case_name` | `str` | `"untitled_case"` | Human-readable case name. | Orchestrator/adapter/user |
| `case_type` | `CaseType` | `"unknown"` | Broad format family for the case. | Format detector/adapter |
| `created_at` | `str` | `utc_now_iso()` | ISO-like UTC creation timestamp. | Core model |
| `updated_at` | `str` | `utc_now_iso()` | ISO-like UTC update timestamp. | Core model/orchestrator |
| `caereflex_version` | `str` | `"1.0.0"` | CaeReflex version associated with the output. | Core model/orchestrator |
| `workspace` | `WorkspaceInfo` | Empty `WorkspaceInfo` | Scan root display, depth, file count, and limits. | Scanner/orchestrator |
| `inspection` | `InspectionInfo` | Partial-success inspection with start time | Overall inspection status, timing, and messages. | Orchestrator/adapter |
| `detected_formats` | `list[str]` | `[]` | File formats or case formats detected in the workspace. | Format detector/adapter |
| `detected_tools` | `list[str]` | `[]` | Tools or solvers detected from files/logs. | Adapter |
| `physics_tags` | `list[str]` | `[]` | Coarse physics/domain tags, such as CFD or meshing. | Adapter/agent |
| `source_files` | `list[SourceFileRecord]` | `[]` | Files considered relevant to the case. | Scanner/adapter |
| `assets` | `list[EngineeringAsset]` | `[]` | Geometry, mesh, dictionary, result, field, literature, or unknown assets. | Adapter |
| `solver_records` | `list[SolverRecord]` | `[]` | Solver/application run metadata. | Adapter/log parser |
| `boundary_conditions` | `list[BoundaryConditionRecord]` | `[]` | Boundary-condition records extracted from case files. | Adapter/parser |
| `materials` | `list[MaterialPropertyRecord]` | `[]` | Material or physical-property records. | Adapter/parser |
| `numerical_settings` | `list[NumericalSettingsRecord]` | `[]` | Discretization, solver, timestep, or other numerical settings. | Adapter/parser |
| `result_fields` | `list[ResultFieldRecord]` | `[]` | Result arrays/fields and their associations/types. | Result adapter/parser |
| `literature_evidence` | `list[LiteratureEvidenceRecord]` | `[]` | External literature metadata used for contextualization. | Literature enricher, e.g. CrossRef |
| `literature_context` | `LiteratureContext` | Empty context with safety defaults | Queries, records used, summary, limitations, and claims to avoid. | Literature enricher/agent |
| `inspection_flags` | `list[InspectionFlag]` | `[]` | Review prompts and findings from inspection. | Adapter/agent |
| `provenance` | `list[ProvenanceRecord]` | `[]` | Case-level events showing what happened, when, and by whom. | Orchestrator/adapter/exporter |
| `agent_summary` | `AgentSummary` | Empty summary | Agent-facing case summary, safe-use policy, and next actions. | Agent/summarizer |
| `exports` | `list[ExportRecord]` | `[]` | Files exported from the case representation. | Exporter |
| `metadata` | `dict[str, Any]` | `{}` | Extensible case-level metadata. | Any producer |

## Enum reference

| Enum | Values | Meaning |
|---|---|---|
| `InspectionStatus` | `success`, `partial_success`, `failed` | Overall inspection outcome. |
| `CaseType` | `unknown`, `gmsh`, `openfoam`, `vtk`, `mixed` | Broad case family. |
| `SourceKind` | `extracted`, `inferred`, `generated`, `user_supplied`, `external_metadata` | How a record or trace value was obtained. |
| `Severity` | `info`, `warning`, `error` | Review flag severity. |
| `AssetType` | `geometry`, `mesh`, `case_folder`, `result_file`, `dictionary`, `field`, `literature`, `unknown` | Asset category. |
| `EvidenceStatus` | `abstract_available`, `metadata_only`, `reference_only`, `unavailable` | Completeness of literature evidence. |
| `AdapterStatus` | `success`, `partial_success`, `failed`, `dependency_missing`, `unsupported` | Adapter execution outcome. |
| `FieldAssociation` | `point`, `cell`, `field`, `boundary`, `volume`, `unknown` | Where a result field is associated. |
| `FieldType` | `scalar`, `vector`, `tensor`, `unknown` | Shape/type of a result field. |
| `HashStatus` | `complete`, `skipped_large`, `failed`, `not_applicable` | File hashing outcome. |

## Status semantics

`InspectionStatus` and `AdapterStatus` deliberately distinguish complete failure from partial or unsupported operation:

- `success`: the inspection or adapter completed its intended work without known blocking errors.
- `partial_success`: useful output was produced, but some files, fields, metadata, dependencies, or optional enrichments were missing or incomplete.
- `failed`: the inspection or adapter could not produce reliable output for its target.
- `dependency_missing`: adapter-specific status meaning the adapter could not run because an optional dependency, executable, parser, or library was unavailable.
- `unsupported`: adapter-specific status meaning the input was recognized as outside the adapter's supported formats or capabilities.

## Provenance and trace confidence

Most record submodels include a `trace: TraceInfo` field. Use it to describe how a value entered the case:

- `source_kind` states whether a value was extracted directly, inferred, generated, user-supplied, or obtained from external metadata.
- `source_files` lists relative source paths that support the record.
- `adapter` names the adapter or enricher that produced the record.
- `confidence` is a numeric confidence score, defaulting to `1.0`; lower values should be used for uncertain inference.
- `notes` captures concise caveats, parsing limitations, or human-readable rationale.

Case-level `provenance` records complement trace data by recording events, timestamps, actors, and structured details for workflow steps such as inspection, enrichment, or export.

## Submodels

### `TraceInfo`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source_kind` | `SourceKind` | `"generated"` | How the record was produced. |
| `source_files` | `list[str]` | `[]` | Relative files supporting the record. |
| `adapter` | `str \| None` | `null` | Adapter/enricher name. |
| `confidence` | `float` | `1.0` | Confidence in the traced record. |
| `notes` | `list[str]` | `[]` | Caveats or additional context. |

### `InspectionInfo`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `status` | `InspectionStatus` | `"partial_success"` | Overall inspection status. |
| `started_at` | `str` | `utc_now_iso()` | Start timestamp. |
| `completed_at` | `str \| None` | `null` | Completion timestamp. |
| `messages` | `list[str]` | `[]` | Human-readable inspection messages. |

### `WorkspaceInfo`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `root_display` | `str` | `"."` | Display path for the scanned root. |
| `scan_depth` | `int` | `0` | Scan depth used. |
| `file_count_considered` | `int` | `0` | Number of files considered. |
| `limits` | `dict[str, Any]` | `{}` | Applied scan limits. |

### `SourceFileRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `file_id` | `str` | Required | Stable file identifier. |
| `relative_path` | `str` | Required | Path relative to workspace root. |
| `suffix` | `str \| None` | `null` | File suffix or extension. |
| `size_bytes` | `int \| None` | `null` | File size in bytes. |
| `sha256` | `str \| None` | `null` | SHA-256 hash when available. |
| `hash_status` | `HashStatus` | `"not_applicable"` | Hashing outcome. |
| `metadata_subset` | `dict[str, Any]` | `{}` | Selected file metadata. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `EngineeringAsset`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `asset_id` | `str` | Required | Stable asset identifier. |
| `asset_type` | `AssetType` | `"unknown"` | Asset category. |
| `name` | `str` | Required | Human-readable asset name. |
| `metrics` | `dict[str, Any]` | `{}` | Quantitative metrics. |
| `properties` | `dict[str, Any]` | `{}` | Descriptive properties. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `SolverRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str \| None` | `null` | Solver name. |
| `application` | `str \| None` | `null` | Application/executable name. |
| `start_time` | `str \| None` | `null` | Solver start time. |
| `end_time` | `str \| None` | `null` | Solver end time. |
| `metadata` | `dict[str, Any]` | `{}` | Extensible solver metadata. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `BoundaryConditionRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `patch` | `str` | Required | Boundary patch name. |
| `field` | `str \| None` | `null` | Field the condition applies to. |
| `type` | `str \| None` | `null` | Boundary condition type. |
| `value` | `str \| None` | `null` | Boundary value representation. |
| `metadata` | `dict[str, Any]` | `{}` | Extensible boundary metadata. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `MaterialPropertyRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | Required | Property/material name. |
| `value` | `str \| float \| int \| None` | `null` | Property value. |
| `units` | `str \| None` | `null` | Units for the value. |
| `metadata` | `dict[str, Any]` | `{}` | Extensible material metadata. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `NumericalSettingsRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `category` | `str` | Required | Settings category. |
| `name` | `str` | Required | Setting name. |
| `value` | `Any` | `null` | Setting value. |
| `metadata` | `dict[str, Any]` | `{}` | Extensible setting metadata. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `ResultFieldRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | Required | Field/array name. |
| `association` | `FieldAssociation` | `"unknown"` | Field association. |
| `field_type` | `FieldType` | `"unknown"` | Scalar/vector/tensor classification. |
| `components` | `int \| None` | `null` | Number of components. |
| `statistics` | `dict[str, Any]` | `{}` | Extracted field statistics. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `LiteratureEvidenceRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `doi` | `str \| None` | `null` | DOI. |
| `title` | `str \| None` | `null` | Publication title. |
| `authors` | `list[str]` | `[]` | Author names. |
| `year` | `int \| None` | `null` | Publication year. |
| `container_title` | `str \| None` | `null` | Journal/proceedings/container. |
| `url` | `str \| None` | `null` | Record URL. |
| `abstract` | `str \| None` | `null` | Abstract text when available. |
| `evidence_status` | `EvidenceStatus` | `"metadata_only"` | Evidence completeness. |
| `relevance_score` | `float \| None` | `null` | Relevance score assigned by an enricher. |
| `query` | `str \| None` | `null` | Query that found the record. |
| `metadata_subset` | `dict[str, Any]` | `{}` | Selected external metadata. |
| `trace` | `TraceInfo` | External CrossRef trace | Defaults to `source_kind="external_metadata"`, `adapter="crossref"`. |

### `LiteratureContext`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `queries` | `list[str]` | `[]` | Literature search queries. |
| `records_used` | `list[str]` | `[]` | IDs/DOIs/titles used for context. |
| `summary` | `str` | `""` | Literature context summary. |
| `limitations` | `list[str]` | `[]` | Context limitations. |
| `do_not_claim` | `list[str]` | Safety defaults | Claims consumers must avoid. |

Default `do_not_claim` values are:

- Do not claim that metadata-only records were read as full papers.
- Do not claim that CrossRef evidence shows simulation correctness.

### `InspectionFlag`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `severity` | `Severity` | `"info"` | Flag severity. |
| `category` | `str` | Required | Flag category. |
| `message` | `str` | Required | Review prompt or finding. |
| `trace` | `TraceInfo` | Empty `TraceInfo` | Record provenance. |

### `ProvenanceRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `event` | `str` | Required | Event name. |
| `timestamp` | `str` | `utc_now_iso()` | Event timestamp. |
| `actor` | `str` | `"caereflex"` | Actor responsible for the event. |
| `details` | `dict[str, Any]` | `{}` | Structured event details. |

### `AgentSummary`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `summary` | `str` | `""` | Human/agent-readable summary. |
| `safe_use_policy` | `list[str]` | `[]` | Safe use constraints. |
| `recommended_next_actions` | `list[str]` | `[]` | Recommended follow-up steps. |
| `do_not_claim` | `list[str]` | `[]` | Claims agents should avoid. |

### `ExportRecord`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `export_type` | `str` | Required | Export format/type. |
| `relative_path` | `str \| None` | `null` | Export path relative to workspace/output root. |
| `created_at` | `str` | `utc_now_iso()` | Export creation timestamp. |

### `AdapterResult`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `adapter_name` | `str` | Required | Adapter identifier. |
| `status` | `AdapterStatus` | Required | Adapter status. |
| `case` | `ReflexCase \| None` | `null` | Case produced by the adapter, if any. |
| `warnings` | `list[str]` | `[]` | Non-fatal adapter warnings. |
| `errors` | `list[str]` | `[]` | Adapter errors. |
| `provenance` | `list[ProvenanceRecord]` | `[]` | Adapter-level provenance events. |

## Minimal valid JSON examples

These examples include explicit fields for readability. In actual model construction, defaulted fields may be omitted except required fields.

### Gmsh case

```json
{
  "schema_version": "1.0",
  "case_id": "gmsh-demo",
  "case_name": "gmsh-demo",
  "case_type": "gmsh",
  "caereflex_version": "1.0.0",
  "detected_formats": ["gmsh"],
  "source_files": [
    {
      "file_id": "file-geo",
      "relative_path": "model.geo",
      "suffix": ".geo",
      "hash_status": "not_applicable",
      "trace": {"source_kind": "extracted", "source_files": ["model.geo"], "adapter": "gmsh", "confidence": 1.0, "notes": []}
    }
  ],
  "assets": [
    {"asset_id": "mesh-1", "asset_type": "mesh", "name": "Gmsh mesh", "trace": {"source_kind": "extracted", "source_files": ["model.geo"], "adapter": "gmsh", "confidence": 0.9, "notes": []}}
  ]
}
```

### OpenFOAM case

```json
{
  "case_id": "openfoam-cavity",
  "case_name": "cavity",
  "case_type": "openfoam",
  "detected_tools": ["OpenFOAM"],
  "source_files": [
    {"file_id": "controlDict", "relative_path": "system/controlDict", "suffix": null, "hash_status": "not_applicable"}
  ],
  "solver_records": [
    {"application": "icoFoam", "trace": {"source_kind": "extracted", "source_files": ["log.icoFoam"], "adapter": "openfoam", "confidence": 1.0, "notes": []}}
  ],
  "boundary_conditions": [
    {"patch": "movingWall", "field": "U", "type": "fixedValue", "value": "uniform (1 0 0)"}
  ],
  "numerical_settings": [
    {"category": "time", "name": "deltaT", "value": 0.005}
  ]
}
```

### VTK case

```json
{
  "case_id": "vtk-results",
  "case_name": "vtk-results",
  "case_type": "vtk",
  "detected_formats": ["vtk"],
  "source_files": [
    {"file_id": "result-vtu", "relative_path": "results/part.vtu", "suffix": ".vtu", "hash_status": "not_applicable"}
  ],
  "assets": [
    {"asset_id": "result-1", "asset_type": "result_file", "name": "part.vtu"}
  ],
  "result_fields": [
    {"name": "U", "association": "point", "field_type": "vector", "components": 3, "statistics": {}}
  ]
}
```

### CrossRef-enriched case

```json
{
  "case_id": "case-with-literature",
  "case_name": "case-with-literature",
  "case_type": "mixed",
  "literature_evidence": [
    {
      "doi": "10.0000/example",
      "title": "Example CFD benchmark metadata study",
      "authors": ["A. Researcher"],
      "year": 2024,
      "container_title": "Example Journal",
      "url": "https://doi.org/10.0000/example",
      "evidence_status": "metadata_only",
      "relevance_score": 0.72,
      "query": "CFD benchmark metadata",
      "trace": {"source_kind": "external_metadata", "source_files": [], "adapter": "crossref", "confidence": 0.8, "notes": ["Metadata only; full paper not read."]}
    }
  ],
  "literature_context": {
    "queries": ["CFD benchmark metadata"],
    "records_used": ["10.0000/example"],
    "summary": "External metadata was found for contextual comparison only.",
    "limitations": ["No full-text review was performed."],
    "do_not_claim": [
      "Do not claim that metadata-only records were read as full papers.",
      "Do not claim that CrossRef evidence shows simulation correctness."
    ]
  }
}
```

## Compatibility guidance for consumers

- Ignore unknown keys inside any `metadata`, `metadata_subset`, `limits`, `details`, `metrics`, `properties`, or `statistics` dictionaries unless your consumer explicitly owns those keys.
- Do not assume optional lists are populated. Empty `source_files`, `assets`, `result_fields`, `literature_evidence`, or other collections can mean the information was absent, unsupported, skipped, or not inspected.
- Treat `inspection_flags` as review prompts, not solver output or correctness evidence. They can highlight missing inputs, suspicious metadata, parser caveats, or next steps, but they do not show a simulation is correct or incorrect.
- Use enum strings exactly as documented, and preserve unknown top-level or nested metadata for forward compatibility when round-tripping JSON.
- Use `trace` and `provenance` together: trace explains where a record came from, while provenance explains workflow events that occurred while building or exporting the case.
