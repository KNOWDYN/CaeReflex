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

Gate 5A stores the latest compact execution result under `metadata.inspection_execution`. Gate 5B also stores ordered native/fallback executions under `metadata.inspection_execution_history`.

## Native OpenFOAM metadata

When `openfoam.native` runs, `metadata.openfoam_native` contains:

- `backend_id` and `backend_version`;
- `representation`;
- `mesh`;
- `times`;
- `field_availability`;
- `fields`;
- `materials`;
- `unsafe_constructs`;
- `source_files_read`;
- `bytes_read`;
- `limitations`.

`mesh` contains counts, patch records, point bounds, warnings and array IDs. `fields` contains one record per field/time pair with class, association, rank, dimensions, quantity semantics, internal mode, optional array ID and boundary summaries.

Native mesh evidence is also represented as the `asset_openfoam_mesh` engineering asset. New time-specific fields are added to `result_fields`; existing time-zero records are enriched rather than removed.

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

OpenFOAM native arrays may represent point coordinates, face offsets, face-point labels, owner labels, neighbour labels or numeric internal fields. Uniform fields store one literal value or tuple with logical-entity metadata rather than materialising repeated industrial arrays.

An `ArrayRef` is a handle, not embedded array content. Agent-facing contexts must use bounded queries rather than serialising complete industrial arrays.
