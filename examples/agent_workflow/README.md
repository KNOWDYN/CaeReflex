# agent_workflow

This directory contains short, safe starter materials for connecting CaeReflex outputs to LLM agents. The files are intentionally small and are not solver inputs.

## Integration modes

### Context-file mode

Use context-file mode when an agent cannot call local tools or should only receive bounded exported files.

```bash
mkdir -p build
caereflex inspect examples/openfoam_cavity_minimal \
  --out build/openfoam_case.json \
  --agent-context build/agent_context.json \
  --report build/case_report.md
```

Expected behavior:

```text
Status: success
Case ID: case_...
Outputs:
- caereflex_json: build/openfoam_case.json
- agent_context: build/agent_context.json
- report: build/case_report.md
```

Give the agent `agent_context.json` first, then `case_report.md` as a readable companion. The agent should separate extracted facts from inferred facts and preserve safety limitations.

### REST/OpenAPI mode

Use REST/OpenAPI mode when an agent platform can call HTTP actions from a schema.

```bash
caereflex serve --host 127.0.0.1 --port 8765 --workspace .
curl http://127.0.0.1:8765/openapi.json
```

Agents should call `GET /health` first, then import workspace-relative paths with `POST /cases/import`, and then prefer `GET /cases/{case_id}/agent-context` for summarization. Use an `x-api-key` header when the server is bound outside localhost.

## Included notes

- [`custom_gpt_instructions.md`](custom_gpt_instructions.md) — short Custom GPT instruction seed.
- [`claude_tool_notes.md`](claude_tool_notes.md) — Claude/tool-wrapper notes emphasizing structured case data and bounded filesystem access.
- [`generic_rest_agent_notes.md`](generic_rest_agent_notes.md) — concise REST-agent reminders, including `x-api-key` outside localhost.
- [`gemini_context_mode.md`](gemini_context_mode.md) — upload-oriented context-file notes for agents that consume files directly.
- [`agent_context_example.json`](agent_context_example.json) — tiny example of safety fields in an agent context file.
- [`case_report_example.md`](case_report_example.md) — tiny report reminder that generated reports are not correctness evidence.

## Safe agent prompt

```text
You are reviewing CaeReflex output for engineering context. Read agent_context.json first. Summarize only extracted facts and clearly label inferred facts. Preserve all inspection flags, safe_use_policy, and do_not_claim items. Do not claim solver execution, correctness, convergence, mesh adequacy, certification, or safety conclusions unless independent evidence outside CaeReflex explicitly supports it. If information is missing or partial, say so and recommend a qualified engineering review.
```

Expected agent behavior:

- Reports the detected case type, source files, assets, fields, inspection flags, and provenance available in the context.
- Uses REST tools or local wrappers only for narrow requested operations.
- Does not request unrestricted filesystem access.
- Does not run solvers or imply that CaeReflex ran them.
- Treats CrossRef records as bibliographic metadata, not engineering evidence.

## Related documentation

- [CLI reference](../../docs/CLI.md)
- [REST API](../../docs/REST_API.md)
- [Agent integration](../../docs/AGENT_INTEGRATION.md)
- [Adapter guide](../../docs/ADAPTERS.md)
- [CrossRef literature metadata](../../docs/CROSSREF.md)
