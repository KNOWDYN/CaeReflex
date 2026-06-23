# Agent integration

CaeReflex exposes CAE inspection results to LLM agents through bounded, evidence-oriented surfaces. Agents should treat CaeReflex as a read-only inspection and documentation aid: it extracts or infers metadata, records provenance, surfaces warnings, and optionally attaches CrossRef metadata, but it does not validate engineering correctness.

## Integration modes

### 1. REST/OpenAPI action mode

Use this mode when an agent platform can call HTTP actions from an OpenAPI schema, such as a Custom GPT Action or another tool-calling runtime.

Start the server from the workspace that should bound case imports:

```bash
caereflex serve --host 127.0.0.1 --port 8765 --workspace /path/to/workspace
```

Primary REST surfaces:

| Purpose | Method and path | Notes |
| --- | --- | --- |
| Health check | `GET /health` | First live call in an agent workflow. |
| Version | `GET /version` | Optional troubleshooting/version display. |
| OpenAPI schema | `GET /openapi.yaml` or `GET /openapi.json` | Import this schema into action-capable agents. |
| Import a case | `POST /cases/import` | Body includes `path`, `adapter`, `attach_crossref`, and `return_agent_context`. Prefer workspace-relative `path`. |
| List stored cases | `GET /cases` | Shows cases stored under the configured workspace. |
| Full case JSON | `GET /cases/{case_id}` | Returns the `ReflexCase` representation. |
| Summary | `GET /cases/{case_id}/summary` | Lightweight status, summary, formats, and tools. |
| Agent context | `GET /cases/{case_id}/agent-context` | Best default input for LLM summarization. |
| Inspection flags | `GET /cases/{case_id}/inspection-flags` | Warnings/errors/review prompts. |
| Literature metadata | `GET /cases/{case_id}/literature` | Existing attached CrossRef metadata only. |
| CrossRef search | `POST /cases/{case_id}/crossref/search` | Search only when the user requests related research/literature context. |
| CrossRef attach | `POST /cases/{case_id}/crossref/attach` | Mutates stored case by attaching CrossRef records; use only when requested. |
| Export JSON | `POST /cases/{case_id}/export/json` | Returns case JSON. |
| Export report | `POST /cases/{case_id}/export/markdown` | Writes a Markdown report in the server workspace. |
| Export bibliography | `POST /cases/{case_id}/export/bibtex` | Writes BibTeX in the server workspace. |

When the server is bound outside localhost, configure an `x-api-key` header and send it with protected routes. Do not expose a non-localhost server without an API key.

### 2. Developer-mediated tool mode

Use this mode when a developer or local automation mediates CaeReflex access for an agent. The agent requests narrow operations such as "import this workspace-relative case", "get agent context", or "list inspection flags"; a local tool wrapper then calls the CLI or REST API and returns only the resulting JSON or Markdown.

Recommended tool names can mirror the REST concepts:

- `import_engineering_case(path, adapter="auto", attach_crossref=false)` → `POST /cases/import` or `caereflex inspect`.
- `get_agent_context(case_id)` → `GET /cases/{case_id}/agent-context` or `caereflex export agent-context`.
- `get_inspection_flags(case_id)` → `GET /cases/{case_id}/inspection-flags` or the `inspection_flags` field from the case JSON.
- `search_related_research(...)` / `attach_related_research(...)` → CrossRef endpoints or CLI commands, only on explicit user request.
- `export_case_report(...)` / `export_bibliography(...)` → export endpoints or CLI commands.

This mode is useful for Claude-style, IDE, CI, or internal agents where the developer controls filesystem access and can enforce workspace boundaries.

### 3. Context-file mode

Use this mode when an agent cannot or should not call local tools. Generate bounded context files and upload or paste them into the agent:

```bash
caereflex inspect CASE --agent-context agent_context.json --report case_report.md
```

The agent should read `agent_context.json` first, then use `case_report.md` as a human-readable companion. `agent_context.json` is designed for LLM consumption and includes:

- case identifiers, case type, inspection status, detected formats, detected tools, and physics tags;
- `safe_use_policy` and merged `do_not_claim` instructions;
- separated `extracted_facts` and `inferred_facts`, with trace data;
- bounded source-file metadata such as relative path, suffix, size, and hash status;
- solver records, boundary conditions, materials, numerical settings, and result fields when detected;
- `literature_context` and any attached CrossRef records as metadata, not paper-reading evidence;
- `inspection_warnings` from inspection flags;
- available actions, recommended next actions, and provenance event names.

## Recommended agent workflow

For REST/OpenAPI or developer-mediated modes, agents should follow this sequence:

1. **Health check.** Call `GET /health` and stop or explain the issue if the service is unavailable.
2. **Import a workspace-relative path.** Call `POST /cases/import` with a workspace-relative `path`, `adapter: "auto"` unless a specific adapter is justified, `attach_crossref: false` by default, and `return_agent_context: true` when the agent can handle the returned context.
3. **Retrieve agent context.** Call `GET /cases/{case_id}/agent-context` even if import returned context, unless the current context is already complete and fresh.
4. **Retrieve inspection flags.** Call `GET /cases/{case_id}/inspection-flags` and surface warnings as review prompts or limitations.
5. **Optionally search or attach CrossRef only when requested.** Use `POST /cases/{case_id}/crossref/search` for non-mutating literature discovery or `POST /cases/{case_id}/crossref/attach` when the user wants the metadata stored with the case. Do not perform CrossRef calls silently.
6. **Summarize with safety limits.** Summaries should distinguish extracted facts from inferred facts, cite inspection warnings, preserve uncertainty, and include do-not-claim limitations.

A good default request body for import is:

```json
{
  "path": "workspace-relative/case",
  "adapter": "auto",
  "attach_crossref": false,
  "return_agent_context": true
}
```

## Custom GPT setup

1. Install server extras if needed:

   ```bash
   pip install -e ".[server]"
   ```

2. Start CaeReflex on localhost:

   ```bash
   caereflex serve --host 127.0.0.1 --port 8765 --workspace /path/to/workspace
   ```

3. If the Custom GPT cannot reach localhost directly, tunnel localhost to an HTTPS URL with your approved tunneling tool. Keep the tunnel and CaeReflex server running while using the GPT.

4. In the Custom GPT Action editor, import:

   ```text
   https://YOUR-TUNNEL-HOST/openapi.yaml
   ```

   For purely local clients, the schema is also available at:

   ```text
   http://127.0.0.1:8765/openapi.yaml
   ```

5. Configure `x-api-key` authentication when the server is not localhost or when the tunnel exposes the service beyond the local machine. Start the server with a matching API key when binding externally:

   ```bash
   caereflex serve --host 0.0.0.0 --port 8765 --workspace /path/to/workspace --api-key "$CAEREFLEX_API_KEY"
   ```

6. Suggested Custom GPT instructions:

   ```text
   You are using CaeReflex as a read-only CAE inspection and documentation service.

   Begin live workflows with the health endpoint. When the user provides a case path, call import_engineering_case with a workspace-relative path, adapter="auto", attach_crossref=false, and return_agent_context=true. Then retrieve get_agent_context and get_inspection_flags before drafting an answer.

   Use CrossRef search or attach actions only when the user explicitly asks for related research or literature context. Treat CrossRef as metadata only, not validation and not evidence that full papers were read.

   Summarize extracted facts separately from inferred facts. Surface inspection flags as warnings or review prompts. Never claim CaeReflex validates a simulation, proves convergence, proves mesh adequacy, certifies engineering results, establishes design safety, or confirms physical correctness.

   Never send arbitrary absolute host paths. Prefer paths relative to the configured CaeReflex workspace. If a path appears outside the workspace, ask the user to place or reference it inside the workspace.
   ```

The repository includes a shorter starter version in `examples/agent_workflow/custom_gpt_instructions.md`.

## Claude and generic agent notes

Claude-style and generic agents should use either REST endpoints or CLI-mediated files, depending on what their runtime can access.

- Prefer REST calls when the agent has a safe HTTP tool configured against the CaeReflex server.
- Prefer CLI-mediated files when the developer controls command execution and can upload `agent_context.json` plus `case_report.md` to the agent.
- Never request unrestricted filesystem access just to inspect a case.
- Never send arbitrary absolute host paths such as `/home/user/...`, `/mnt/...`, or `C:\...` unless the CaeReflex server workspace explicitly permits that location and the developer has approved it.
- Ask for workspace-relative paths, for example `examples/openfoam_cavity_minimal` or `project_cases/bracket_mesh/model.geo`.
- Treat partial-success and warning flags as important context rather than as failures to hide.

See also `examples/agent_workflow/generic_rest_agent_notes.md`, `examples/agent_workflow/claude_tool_notes.md`, and `examples/agent_workflow/gemini_context_mode.md`.

## Safety policies agents must preserve

`agent_context.json` and Markdown exports are built from the exporter policies and adapter-generated `agent_summary.do_not_claim` lists. Agents must carry these policies forward into their answers.

Safe-use policy:

- Use extracted facts as file-derived facts.
- Treat inferred facts as tentative.
- Treat CrossRef metadata as literature context, not validation.
- Do not claim metadata-only records were read as full papers.
- Do not claim simulation convergence unless explicit evidence is present.
- Do not claim mesh adequacy.
- Do not claim engineering certification.
- Do not claim design safety.

Base do-not-claim policy:

- Do not claim that CaeReflex validates this simulation.
- Do not claim convergence unless explicit residual/convergence evidence is present.
- Do not claim mesh adequacy.
- Do not claim engineering certification.
- Do not claim design safety.
- Do not claim metadata-only CrossRef records were read as full papers.

Adapters may add more case-specific `agent_summary.do_not_claim` items. The exported agent context merges the base list with adapter-provided items; agents should obey the merged `do_not_claim` field, not only the base list above.

## Prompt snippets for downstream agents

Use or adapt these snippets in system prompts, tool descriptions, or developer wrappers.

### General safety snippet

```text
CaeReflex provides inspection metadata, provenance, warnings, and optional literature metadata. It is not a solver, validator, certification authority, safety reviewer, or substitute for qualified engineering judgment. Do not claim validation, convergence, mesh adequacy, certification, design safety, or physical correctness unless independent explicit evidence is provided outside CaeReflex metadata.
```

### CrossRef snippet

```text
CrossRef results are bibliographic metadata and related-literature context only. Do not describe metadata-only records as papers you have read. Do not use CrossRef records to validate the simulation, prove correctness, confirm mesh adequacy, certify design safety, or establish convergence.
```

### Context-file snippet

```text
Read agent_context.json first. Separate extracted_facts from inferred_facts. Use inspection_warnings as limitations or review prompts. Follow every safe_use_policy and do_not_claim item. Use case_report.md only as a readable companion, not as validation evidence.
```

### Path-safety snippet

```text
Only submit workspace-relative paths to CaeReflex unless the developer explicitly confirms that an absolute path is inside the configured server workspace. If unsure, ask the user to move or reference the case under the CaeReflex workspace.
```

## Example materials

The `examples/agent_workflow/` directory contains starter materials for common integrations:

- `examples/agent_workflow/custom_gpt_instructions.md` — minimal Custom GPT instruction seed.
- `examples/agent_workflow/generic_rest_agent_notes.md` — concise REST-agent reminders, including `x-api-key` outside localhost.
- `examples/agent_workflow/claude_tool_notes.md` — Claude/tool-wrapper notes emphasizing structured data and bounded filesystem access.
- `examples/agent_workflow/gemini_context_mode.md` — context-file workflow note for agents that consume uploaded files.
- `examples/agent_workflow/agent_context_example.json` — tiny example of safety fields in an agent context file.
- `examples/agent_workflow/case_report_example.md` — tiny example report emphasizing that reports are not validation.

These examples are intentionally small. For production workflows, use the live `/openapi.yaml` schema, the current `agent_context.json`, and the actual inspection flags produced for the case being reviewed.
