# ReflexCase fields

ReflexCase schema version remains `1.0`. The root fields include:

- `schema_version`
- `case_id`
- `case_name`
- `case_type`
- `created_at`
- `updated_at`
- `caereflex_version`
- `workspace`
- `inspection`
- `detected_formats`
- `detected_tools`
- `physics_tags`
- `source_files`
- `assets`
- `solver_records`
- `boundary_conditions`
- `materials`
- `numerical_settings`
- `result_fields`
- `literature_evidence`
- `literature_context`
- `inspection_flags`
- `provenance`
- `agent_summary`
- `exports`
- `contract_version`
- `inspection_profile`
- `case_manifest`
- `diagnostics`
- `quantity_evidence`
- `dimensional_checks`
- `array_references`
- `metadata`

Gate 5A stores compact execution results under `metadata.inspection_execution`. The result includes job and execution IDs, backend identity, status, parser attempts, diagnostics, relative paths accessed, bytes read, artefact metadata and lazy array references.

Gate 6A stores compact spatial graph references under `metadata.spatial_graph_refs`. Each reference contains a graph ID, SQLite store URI, graph and contract versions, default-frame ID, compact counts and update time. Complete entities, relations, frames and arrays remain outside ReflexCase.

## ArrayRef

Required compatibility fields:

- `uri`
- `format`
- `shape`
- `dtype`

Optional fields include:

- `chunks`
- `checksum`
- `selection_capabilities`
- `array_id`
- `source_asset_id`
- `source_path`
- `association`
- `component_names`
- `quantity_evidence_ref`
- `coordinate_frame_ref`
- `time_index`
- `byte_order`
- `backend`
- `backend_version`
- `storage_lifetime`
- `permitted_operations`
- `metadata`

An `ArrayRef` is a handle, not embedded array content. Agent-facing contexts must use bounded queries rather than serialising complete industrial arrays.

## SpatialGraphRef

A compact spatial graph reference contains:

- `graph_id`
- `store_uri`
- `graph_version`
- `contract_version`
- `default_coordinate_frame_id`
- `frame_count`
- `entity_count`
- `relation_count`
- `array_link_count`
- `updated_at`

The reference does not contain coordinates, connectivity, full graph payloads or inferred coordinate assumptions.
