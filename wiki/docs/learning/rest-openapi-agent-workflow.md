# REST/OpenAPI Agent Workflow

## Level

Intermediate to expert.

## Audience

Full-stack developers, AI-agent engineers, platform teams, and instructors teaching tool-calling workflows.

## Learning objectives

By the end, you can:

1. start the CaeReflex REST server in a bounded workspace;
2. inspect health and OpenAPI endpoints;
3. import a case through the API;
4. retrieve agent context and inspection flags; and
5. design safe tool instructions for Custom GPT, Claude-style, or internal agents.

## Files used

- [Architecture: REST API](../architecture/rest-api.md)
- [Reference: OpenAPI](../reference/openapi.md)
- `openapi/openapi.yaml`
- `examples/agent_workflow/`

## Walkthrough

Start the server from the repository root:

```bash
caereflex serve --host 127.0.0.1 --port 8765 --workspace .
```

In another terminal:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/openapi.yaml
curl -X POST "http://127.0.0.1:8765/cases/import" \
  -H "Content-Type: application/json" \
  -d '{"path":"examples/openfoam_cavity_minimal","adapter":"auto","attach_crossref":false,"return_agent_context":true}'
```

Use the returned `case_id`:

```bash
curl "http://127.0.0.1:8765/cases/CASE_ID/agent-context"
curl "http://127.0.0.1:8765/cases/CASE_ID/inspection-flags"
```

## What to observe

- The OpenAPI schema describes the tool surface for action-capable agents.
- Case paths should be workspace-relative.
- CrossRef should be requested explicitly, not silently.
- Agent answers must preserve inspection warnings and safe-use policy.

## Expected output and interpretation

A representative health response is intentionally small:

```json
{"status": "ok", "service": "caereflex"}
```

A representative import response for `examples/openfoam_cavity_minimal` should include the stored case identifier and optional agent context:

```json
{
  "status": "success",
  "case_id": "case_6c5707a83ec1",
  "summary": "OpenFOAM case inspected. 8 files were considered.",
  "warnings": [],
  "provenance_summary": ["openfoam_inspection_started"],
  "next_recommended_actions": ["get_agent_context", "export_case_report"],
  "data": {
    "agent_context": {
      "case_type": "openfoam",
      "source_files": [{"relative_path": "system/controlDict", "hash_status": "complete"}],
      "do_not_claim": ["Do not claim simulation convergence unless explicit evidence is present."]
    }
  }
}
```

A representative inspection-flags response is:

```json
{"inspection_flags": []}
```

Interpret the output as follows:

- Extracted evidence: `source_files`, `detected_formats`, field records, and hashes in `data.agent_context` come from the workspace-relative example path.
- Inferred context: `summary`, `next_recommended_actions`, and case classification help sequence agent behavior; they are not engineering conclusions.
- Warnings: top-level `warnings` and `/inspection-flags` must be fetched and echoed before summarization. An empty list is only an absence of emitted flags for that run.
- Provenance: `provenance_summary` identifies adapter events that produced the stored case.
- Unsafe claims to avoid: agents must not claim validation, convergence, mesh adequacy, certification, design safety, unrestricted filesystem access, or CrossRef attachment unless the corresponding endpoint was explicitly called.

## Beginner exercise

Identify the health endpoint, OpenAPI endpoint, import endpoint, and agent-context endpoint.

## Practitioner exercise

Draft safe agent instructions that require health check, case import, agent context retrieval, and inspection flag review before summarization.

## Expert extension

Review API exposure risks:

1. What changes when binding outside localhost?
2. Why is an API key required for external exposure?
3. How should workspace boundaries shape agent tool descriptions?
4. What should an agent do if a user provides an absolute path?

## Assessment checklist

- [ ] The learner understands the REST workflow sequence.
- [ ] The learner can write a safe agent prompt or tool policy.
- [ ] The learner explains workspace and authentication risks.

## Answer key

Use these examples to check that learners design safe REST/OpenAPI workflows rather than over-permissive agent tools.

### Beginner exercise answer key

**Sample acceptable answer**

- Health endpoint: `GET /health`, called with `curl http://127.0.0.1:8765/health`.
- OpenAPI endpoint: `GET /openapi.yaml`, called with `curl http://127.0.0.1:8765/openapi.yaml`.
- Import endpoint: `POST /cases/import`, called with a JSON body containing a workspace-relative `path`, `adapter`, `attach_crossref`, and `return_agent_context`.
- Agent-context endpoint: `GET /cases/{case_id}/agent-context`, called after replacing `{case_id}` with the returned case identifier.
- Inspection-flags endpoint: `GET /cases/{case_id}/inspection-flags`, used before summarization even when the import response includes warnings.

**Unsafe or incorrect answer**

- "Skip health and flags, call any URL exposed by OpenAPI, use absolute paths such as `/etc/passwd`, and summarize the case as validated if the import succeeds."

**Why the acceptable answer passes**

- It preserves the documented sequence and uses the `case_id` returned by import.
- It treats inspection flags as a required safety check before agent summarization.
- It keeps paths workspace-relative for safe tool descriptions.

**Why the unsafe answer fails**

- It bypasses readiness and warning checks.
- It encourages unsafe filesystem access and unsupported validation claims.

**References**

- Command output to cite: `curl http://127.0.0.1:8765/health`, `curl http://127.0.0.1:8765/openapi.yaml`, the `POST /cases/import` response, `curl .../agent-context`, and `curl .../inspection-flags`.
- Adapter/API behavior: `caereflex/server/app.py` implements `/health`, `/openapi.yaml`, `/cases/import`, `/cases/{case_id}/agent-context`, and `/cases/{case_id}/inspection-flags`.
- Safety rule: agent answers must preserve inspection warnings and the safe-use/do-not-claim lists returned in agent context.

### Practitioner exercise answer key

**Sample acceptable answer**

> Before answering engineering questions, call `GET /health` and stop if the service is unavailable. Import only user-approved, workspace-relative case paths with `POST /cases/import`; set `attach_crossref` to `false` unless the user explicitly requests literature metadata. After import, store the returned `case_id`, call `GET /cases/{case_id}/agent-context`, and call `GET /cases/{case_id}/inspection-flags`. In the answer, cite file-derived evidence from `source_files`, `result_fields`, and other extracted records, echo all warnings or flags, and state that empty flags do not prove correctness. Never claim validation, convergence, mesh adequacy, certification, design safety, unrestricted filesystem access, or CrossRef attachment unless the corresponding endpoint output explicitly supports that limited statement.

**Unsafe or incorrect answer**

- "The agent may import any path the user types, attach CrossRef automatically, skip flag retrieval, and present the API result as a certified engineering review."

**Why the acceptable answer passes**

- It defines an auditable, least-privilege workflow.
- It separates endpoint outputs from engineering conclusions and requires warning preservation.
- It avoids silent CrossRef attachment.

**Why the unsafe answer fails**

- It is over-permissive with filesystem paths and external metadata.
- It skips explicit warning retrieval and misrepresents inspection as certification.

**References**

- Command output to cite: health response, import response with `case_id`, agent-context response, and inspection-flags response.
- API behavior: `caereflex/server/app.py` returns import `warnings`, full `inspection_flags`, `provenance_summary`, and optional `data.agent_context`; the agent-context endpoint returns `safe_use_policy`, `inspection_warnings`, `do_not_claim`, and `source_references` from `caereflex/exporters.py`.
- Safety rule: `wiki/docs/user-guide/safe-use-policy.md` states that CaeReflex output is structured evidence, not engineering validation.

### Expert extension answer key

**Sample acceptable answer**

1. Binding outside localhost changes the threat model: the API can be reached by other machines, so unauthenticated access could expose inspection, export, and case-store operations.
2. An API key is required for external exposure because `caereflex serve` rejects non-localhost binding without one, and the server checks `x-api-key` for external mode.
3. Workspace boundaries should be reflected in tool descriptions: tools should accept workspace-relative paths, should not advertise arbitrary filesystem access, and should tell agents to reject or ask the user to relocate paths that are outside the configured workspace.
4. If a user provides an absolute path, an agent should not pass it blindly. Prefer asking for or constructing a workspace-relative path; for external deployments, paths outside the workspace are rejected by path-safety checks.

**Unsafe or incorrect answer**

- "Bind to `0.0.0.0` without a key for convenience, describe the tool as able to read any path on the host, and pass absolute paths directly because the API will validate the engineering content."

**Why the acceptable answer passes**

- It recognizes that network exposure, authentication, and workspace scoping are part of safe agent operation.
- It ties path handling to the server's safety behavior instead of inventing broad capabilities.

**Why the unsafe answer fails**

- It creates an avoidable remote-access risk.
- It misstates the tool's filesystem and engineering-validation capabilities.

**References**

- Command output to cite: `caereflex serve --host 127.0.0.1 --port 8765 --workspace .`, `curl .../health`, and the OpenAPI output from `curl .../openapi.yaml`.
- API behavior: `caereflex/cli/main.py` requires an API key when serving outside localhost; `caereflex/server/app.py` enforces `x-api-key` in external mode and resolves request paths against the workspace; `caereflex/core/validation.py` provides workspace path checks.
- Safety rule: agent tool descriptions must not claim unrestricted filesystem access or engineering validation beyond endpoint evidence.
