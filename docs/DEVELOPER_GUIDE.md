# CaeReflex Developer Guide

This guide maps the repository layout to the runtime entry points that inspect CAE artefacts, attach CrossRef metadata, and export agent-readable evidence. Keep implementation changes aligned with this document so new contributors can find the single owner for each behavior.

## Architecture map

| Path | Responsibility | Notes |
| --- | --- | --- |
| `caereflex/core/` | Shared domain models, configuration, errors, fingerprinting, provenance, and validation. | `models.py` defines `ReflexCase`, `AdapterResult`, evidence records, flags, and export/provenance records. `config.py` owns scan and request limits. `validation.py` owns path-safety helpers and display-path sanitization. |
| `caereflex/adapters/` | File/domain adapters for Gmsh, OpenFOAM, and VTK. | `base.py` defines the adapter interface. Concrete adapters inspect artefacts and return `AdapterResult` without owning CLI, REST, or output-format logic. |
| `caereflex/evidence/` | Literature and metadata enrichment. | `crossref.py` searches/parses CrossRef metadata, builds `LiteratureContext`, and attaches metadata-derived `LiteratureEvidenceRecord` values. |
| `caereflex/exporters.py` | Output formats. | Owns ReflexCase JSON, agent context JSON, agent context Markdown, human Markdown reports, and BibTeX. Exporters must preserve safe-use and do-not-claim guidance. |
| `caereflex/services.py` | Orchestration and business logic. | Central public workflow layer for inspection, adapter selection, CrossRef search/attach, case persistence, exports, and bundled examples. CLI and REST should call this layer instead of duplicating workflow logic. |
| `caereflex/cli/main.py` | Typer CLI entry point. | Defines `caereflex` commands, command-specific options, user-facing output, and exit codes. Business behavior should be delegated to `services.py`. |
| `caereflex/server/app.py` | FastAPI REST/OpenAPI entry point. | Defines REST request/response models, local/external API-key checks, workspace path resolution, OpenAPI generation, and REST routes. Workflow behavior should be delegated to `services.py`. |
| `examples/` | Runnable inspection examples and context/workflow examples. | `services.EXAMPLE_NAMES` lists bundled examples. Runnable examples should work through `caereflex examples run`. Context examples should document workflow expectations. |
| `tests/` | Feature-oriented test coverage. | Tests cover models, CLI, REST, adapters, CrossRef mock behavior, exporters, examples, security, documentation presence, and wiki/docs consistency. |

## Core design rules

1. **CLI and REST call `services.py`.**
   - Add orchestration in `caereflex/services.py` first.
   - `caereflex/cli/main.py` should translate command-line options into service calls and format output/exit codes.
   - `caereflex/server/app.py` should translate HTTP requests into service calls and format HTTP responses.
   - Avoid copying adapter detection, CrossRef attachment, persistence, or export dispatch into CLI/REST handlers.

2. **Adapters return `AdapterResult`.**
   - All adapters inherit or follow `BaseAdapter.inspect(path) -> AdapterResult`.
   - `AdapterResult.case` contains the populated `ReflexCase` when inspection succeeds or partially succeeds.
   - `AdapterResult.warnings`, `AdapterResult.errors`, `AdapterResult.status`, and `AdapterResult.provenance` communicate adapter-level outcomes without raising for ordinary unsupported/partial conditions.
   - Raise only for exceptional safety or programming errors that the service/entry point should surface.

3. **Exporters own output formats.**
   - Add or modify JSON, agent-context, Markdown, and BibTeX formatting in `caereflex/exporters.py`.
   - Services may dispatch export types, but should not assemble format-specific documents.
   - CLI and REST should not embed report templates or format-specific serialization beyond simple response envelopes.

4. **Path safety stays centralized in validation/server logic.**
   - Use `caereflex/core/validation.py` for reusable path checks and display-path sanitization.
   - Keep REST workspace resolution and external-host restrictions in `caereflex/server/app.py`.
   - Do not add ad-hoc `../` handling or absolute-path redaction in individual adapters unless it is adapter-specific metadata cleanup; prefer central helpers.

5. **CaeReflex extracts evidence; it does not inspect engineering correctness.**
   - No code path should imply solver execution, convergence, mesh adequacy, certification, safety conclusions, or full-paper review from metadata.

## Dependency extras

Base install dependencies are declared in `pyproject.toml` under `[project].dependencies`:

- `pydantic`: domain models and validation.
- `typer`: CLI framework.
- `rich`: CLI display.
- `httpx`: CrossRef HTTP client.
- `pyyaml`: OpenAPI YAML generation.
- `bibtexparser`: bibliography-related dependency.

Optional extras in `pyproject.toml`:

| Extra | Contents | Use |
| --- | --- | --- |
| `[server]` | `fastapi`, `uvicorn` | REST/OpenAPI server via `caereflex serve` and `caereflex.server.app`. |
| `[mesh]` | `numpy`, `meshio` | Mesh-oriented optional inspection support. |
| `[vtk]` | `pyvista`, `vtk` | Rich VTK/PyVista inspection support. |
| `[gmsh]` | `gmsh` | Optional Gmsh SDK support. |
| `[dev]` | `pytest` | Test runner for repository development. |
| `[all]` | Server, mesh, VTK, and Gmsh runtime extras | Broad local development/runtime install. |

When adding an optional integration, keep the base package importable without that dependency. If an optional dependency is missing, the feature should report a controlled dependency-missing/partial result where possible.

## How to add a feature

Use this sequence for any new public behavior:

1. **Model change**
   - Add or extend Pydantic models/enums in `caereflex/core/models.py` only when the data needs to persist in a `ReflexCase` or API/export payload.
   - Add traceability (`TraceInfo`), provenance, confidence, or limitations for inferred/generated/external facts.
   - Consider schema/backward compatibility for existing `ReflexCase` JSON files.

2. **Service change**
   - Add business orchestration to `caereflex/services.py`.
   - Keep service functions usable from both CLI and REST.
   - If the feature persists cases, use the existing store helpers (`save_case_to_store`, `load_case_from_store`, `list_case_store`) or add adjacent helpers.

3. **CLI/REST exposure**
   - Add Typer commands/options in `caereflex/cli/main.py` only after the service function exists.
   - Add FastAPI request/response models and routes in `caereflex/server/app.py` only after the service function exists.
   - Preserve existing safety checks: localhost vs external API key handling, workspace path checks, scan/file limits, and clear errors.

4. **Export update**
   - Update `caereflex/exporters.py` if the feature changes what agent contexts, reports, JSON, Markdown, or BibTeX should contain.
   - Include limitations and do-not-claim text for any inferred or external metadata.

5. **Tests**
   - Add model tests for schema changes.
   - Add CLI and REST tests for public entry points.
   - Add exporter tests for output changes.
   - Add security tests for path, size, scan, or claim-boundary behavior.
   - Add adapter-specific tests if a feature depends on adapter output.

6. **Docs/examples update**
   - Update the relevant user docs, developer docs, OpenAPI/wiki docs, and bundled examples.
   - If the feature adds a new public command, endpoint, model field, or bundled example behavior, update documentation in the same change.

## How to add an adapter

1. Create `caereflex/adapters/<name>.py`.
2. Implement an adapter class that follows `BaseAdapter.inspect(path) -> AdapterResult`.
3. Populate a `ReflexCase` with:
   - `case_id`, `case_name`, `case_type`, `detected_formats`, and `detected_tools`.
   - `source_files` with relative/display-safe paths, suffixes, sizes, hash status, and trace data.
   - Domain records (`assets`, `solver_records`, `boundary_conditions`, `materials`, `numerical_settings`, `result_fields`) as appropriate.
   - `inspection_flags` for skipped files, missing optional dependencies, unsupported files, or partial extraction.
   - `provenance` records for major extraction steps.
   - `agent_summary` with conservative next actions and do-not-claim notes.
4. Respect `CaeReflexConfig` limits (`max_file_size_mb`, `max_scan_depth`, `max_scan_files`) and do not traverse unbounded directories.
5. Never execute solvers, mesh generators, post-processors, shell scripts, or case commands. Inspect files only.
6. Register the adapter in `caereflex/services.py`:
   - Add it to `inspect_with_adapter`.
   - Add auto-detection in `detect_adapter` only if reliable and safe.
7. Expose it through CLI/REST only if it is intended to be public.
8. Add tests such as `tests/test_<name>_adapter.py`, plus CLI/REST/export tests if public behavior changes.
9. Add documentation and examples if the adapter is user-facing.

## How to add an exporter

1. Add a formatting function to `caereflex/exporters.py`.
2. Accept a `ReflexCase` and output path, create parent directories, write UTF-8 text/JSON as appropriate, and return `Path`.
3. Append an `ExportRecord` to `case.exports` when the export should be tracked.
4. Use `safe_display_path` or equivalent central sanitization; do not leak absolute local paths into agent-facing output.
5. Preserve safe-use policy and do-not-claim constraints for agent-facing or human-readable formats.
6. Add the export type dispatch in `services.export_case`.
7. Add CLI and/or REST routes if the exporter is public.
8. Add tests in `tests/test_exporters.py` and update docs.

## How to extend CrossRef/literature behavior without overclaiming

CrossRef support lives in `caereflex/evidence/crossref.py` and is intentionally metadata-scoped.

When extending it:

- Keep query construction in `generate_queries` conservative and explainable.
- Keep parsing in `parse_crossref_items`; store only metadata that came from CrossRef payloads.
- Use `LiteratureEvidenceRecord.evidence_status` accurately:
  - `abstract_available` only when CrossRef supplied an abstract.
  - `metadata_only` when no abstract/full text was retrieved.
  - Do not infer full-paper access from DOI, title, URL, or citation counts.
- Keep `TraceInfo(source_kind=external_metadata, adapter="crossref")` or an equivalent trace for literature records.
- Keep `LiteratureContext.limitations` and `do_not_claim` explicit.
- Do not write summaries that state or imply the simulation correctness was established, peer reviewed, benchmarked, certified, or shown correct by CrossRef results.
- Prefer mock-response tests for deterministic coverage; mark live API tests separately if added.

## Safety and security checklist

Before merging, verify the change respects these constraints:

- **No solver execution:** CaeReflex inspects files only. It must not run OpenFOAM solvers, Gmsh generation, VTK pipelines requiring arbitrary user code, shell scripts, Makefiles, or post-processing commands.
- **No path traversal:** External REST mode must keep paths inside the configured workspace. Reuse `assert_safe_workspace_path` and `safe_display_path`; do not introduce unreviewed path resolution logic.
- **No certification claims:** Outputs must not claim convergence, mesh adequacy, safety conclusions, engineering certification, or simulation correctness unless explicit future evidence models are designed for that purpose and still clearly scoped.
- **No full-paper claims from CrossRef metadata:** CrossRef records are metadata/abstract context only. Do not state that papers were read, reviewed, or used as full-text evidence unless a separate full-text feature exists and clearly records that provenance.
- **Respect file-size and scan limits:** Honor `CaeReflexConfig.max_file_size_mb`, `max_scan_depth`, `max_scan_files`, and server request limits. Large or skipped files should produce flags/status rather than unbounded reads.
- **Keep base imports safe:** Optional extras must not make `import caereflex` fail when not installed.
- **Avoid absolute path leakage:** Agent-facing exports and reports should use relative or sanitized display paths.
- **Prefer deterministic tests:** Use fixtures and mock CrossRef responses for CI-stable tests.

## Testing map

Current tests are organized by feature and public surface:

| Test file | Coverage intent |
| --- | --- |
| `tests/test_models.py` | Pydantic model defaults, enum/model serialization, and `ReflexCase` shape. |
| `tests/test_cli.py` | Typer CLI commands, output behavior, exit codes, and service-backed workflows. |
| `tests/test_server.py` | FastAPI routes, case import/store/access, exports, CrossRef endpoints, and API safety behavior. |
| `tests/test_*_adapter.py` | Adapter-specific extraction for Gmsh, OpenFOAM, VTK, including partial/dependency behavior. Current concrete files include `test_gmsh_adapter.py`, `test_openfoam_adapter.py`, and `test_vtk_adapter.py`. |
| `tests/test_crossref_mock.py` | Deterministic CrossRef query/parse/attach behavior using mock payloads rather than live network dependence. |
| `tests/test_exporters.py` | ReflexCase JSON, agent context, Markdown report, BibTeX, safe-use text, and path redaction expectations. |
| `tests/test_examples.py` | Bundled example discovery and runnable example workflows. |
| `tests/test_security.py` | Path traversal, path redaction, scan/file limits, and security-sensitive behavior. |
| `tests/test_docs_presence.py` | Required documentation file presence and baseline documentation coverage. |
| `tests/test_wiki.py` | Wiki/docs consistency expectations. |

Recommended local checks:

```bash
pytest
pytest tests/test_security.py tests/test_exporters.py
pytest tests/test_cli.py tests/test_server.py
```

Use targeted tests while developing, then run the full suite before opening a pull request when optional dependencies are available.

## Documentation-maintenance rule

Every public change must update documentation in the same pull request:

- Public CLI command or option changes must update the corresponding CLI/user documentation.
- REST endpoint, request, response, or authentication behavior changes must update REST/OpenAPI documentation and generated/static OpenAPI artefacts if maintained in the repo.
- ReflexCase field additions, removals, or semantic changes must update schema/model documentation and exporter expectations.
- Bundled example additions or behavior changes must update `examples/` docs and any example index/listing.
- Export format changes must update exporter docs and agent-facing guidance.
- Safety, security, or claim-boundary changes must update the safety documentation and tests.

If a change is public enough for users, agents, or integrators to call it, it is public enough to document.
