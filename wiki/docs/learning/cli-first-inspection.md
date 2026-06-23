# CLI-first Inspection

## Level

Beginner to intermediate, with expert tracing prompts.

## Audience

CAE engineers, Python developers, AI-agent builders, and instructors beginning the CaeReflex curriculum.

## Learning objectives

By the end, you can:

1. run a complete CaeReflex inspection from the command line;
2. identify the purpose of full case JSON, agent context JSON, and Markdown reports;
3. find inspection warnings and limitations; and
4. write a safe summary without claiming validation or certification.

## Files used

- `examples/openfoam_cavity_minimal`
- [Quickstart](../user-guide/quickstart.md)
- [CLI Reference](../reference/cli.md)

## Walkthrough

From the repository root:

```bash
caereflex examples list
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

Inspect the outputs:

```bash
python -m json.tool caereflex.json | head
python -m json.tool agent_context.json | head
sed -n '1,120p' case_report.md
```

## What to observe

- `caereflex.json` is the full structured record.
- `agent_context.json` is the compact LLM-oriented context.
- `case_report.md` is a human-readable report.
- Warnings and safe-use statements are part of the learning output, not noise to ignore.

## Expected output and interpretation

A representative `agent_context.json` from `examples/openfoam_cavity_minimal` should contain stable, file-derived evidence like this:

```json
{
  "case_name": "openfoam_cavity_minimal",
  "case_type": "openfoam",
  "detected_formats": ["OpenFOAM case folder"],
  "detected_tools": ["OpenFOAM"],
  "source_files": [
    {"relative_path": "system/controlDict", "hash_status": "complete"},
    {"relative_path": "0/U", "hash_status": "complete"}
  ],
  "result_fields": [
    {"name": "p", "association": "volume", "trace": {"source_kind": "extracted", "source_files": ["0/p"]}},
    {"name": "U", "association": "volume", "trace": {"source_kind": "extracted", "source_files": ["0/U"]}}
  ]
}
```

A representative Markdown report should start with safe-use framing:

```markdown
# CaeReflex Report — openfoam_cavity_minimal
This report was generated from metadata extracted or inferred by CaeReflex.
It is not an engineering validation report, certification, safety approval, or convergence proof.
```

Interpret the output as follows:

- Extracted evidence: `source_files`, `detected_formats`, `detected_tools`, and `result_fields[*].trace.source_files` are direct observations from files under `examples/openfoam_cavity_minimal`.
- Inferred context: `case_type: "openfoam"` and the human-readable summary classify the folder from its layout and known dictionary names; treat them as adapter interpretation, not solver execution.
- Warnings: `inspection_warnings` or `inspection_flags` must be preserved verbatim when present. An empty list only means this inspection did not emit a warning; it is not proof that the case is complete.
- Provenance: `source_references` or full-case `provenance` events identify which adapter actions produced the context.
- Unsafe claims to avoid: do not say the simulation converged, the mesh is adequate, the boundary conditions are correct, the result is certified, or the design is safe.

## Beginner exercise

Find the case identifier, detected formats, detected tools, and at least one warning or limitation.

## Practitioner exercise

Write a five-sentence case summary that separates detected evidence from what a qualified engineer still needs to review.

## Expert extension

Trace the workflow through the architecture:

1. CLI command in `caereflex/cli/main.py`.
2. Service orchestration in `caereflex/services.py`.
3. OpenFOAM adapter behavior in `caereflex/adapters/openfoam.py`.
4. Export behavior in `caereflex/exporters.py`.
5. Domain records in `caereflex/core/models.py`.

## Assessment checklist

- [ ] Commands ran successfully.
- [ ] The learner can explain each generated file.
- [ ] The learner surfaced at least one limitation.
- [ ] The summary avoids claims of correctness, convergence, mesh adequacy, certification, or safety.

## Answer key

Use these examples to calibrate answers. Equivalent wording is acceptable when it preserves evidence, limitations, and safe-use constraints.

### Beginner exercise answer key

**Sample acceptable answer**

- Case identifier: read `case_id` from `agent_context.json` or the CLI's `Case ID` line; it is a generated identifier for this inspection run, not proof of uniqueness outside the CaeReflex case store.
- Case name/type: `openfoam_cavity_minimal` / `openfoam`.
- Detected format/tool: `OpenFOAM case folder` and `OpenFOAM`.
- Warning or limitation: the report states it is not an engineering validation report, certification, safety approval, or convergence proof; if `inspection_warnings` is empty, say that no warning was emitted for this run but that this is not proof of case completeness.

**Unsafe or incorrect answer**

- "The case is a validated OpenFOAM simulation, CaeReflex proved it converged, and there are no limitations because `inspection_warnings` is empty."

**Why the acceptable answer passes**

- It names fields that are available in the agent-context output and keeps the limitation attached to the report output.
- It treats an empty warning list as absence of emitted flags, not as positive engineering evidence.
- It aligns with the safe-use policy exported into agent context: extracted facts are file-derived facts, inferred facts are tentative, and convergence, mesh adequacy, certification, and design safety must not be claimed without explicit evidence.

**Why the unsafe answer fails**

- It converts metadata inspection into validation and convergence claims.
- It ignores the Markdown report's explicit safe-use framing and the exporter `do_not_claim` rules.

**References**

- Command output to cite: `python -m json.tool agent_context.json | head` for `case_id`, `case_name`, `case_type`, `detected_formats`, and `detected_tools`; `sed -n '1,120p' case_report.md` for the safe-use report preamble.
- Adapter behavior: `caereflex/services.py` auto-detects OpenFOAM from `system/controlDict`, `constant`, or `0` directories, then dispatches to the OpenFOAM adapter.
- Safety rule: `caereflex/exporters.py` adds `safe_use_policy` and `do_not_claim` items to agent context and the Markdown report.

### Practitioner exercise answer key

**Sample acceptable answer**

1. CaeReflex inspected `examples/openfoam_cavity_minimal` as an OpenFOAM-like case folder and exported a full JSON record, an agent-context JSON file, and a Markdown report.
2. The detected evidence includes source files such as `system/controlDict` and initial fields such as `0/U` or `0/p`, with trace information pointing back to the files that supplied those records.
3. The OpenFOAM classification, summary, and recommended next actions are inspection context, not solver output.
4. A qualified engineer still needs to review boundary conditions, numerical settings, mesh quality, physical assumptions, solver logs, and convergence evidence using appropriate CAE procedures.
5. This summary does not claim validation, certification, mesh adequacy, design safety, or that the simulation converged.

**Unsafe or incorrect answer**

- "The command confirms the cavity case ran correctly, the mesh and boundary conditions are adequate, and the result is safe to use because CaeReflex found OpenFOAM files and no warnings."

**Why the acceptable answer passes**

- It separates file-derived evidence from inferred context and human follow-up work.
- It explicitly preserves limitations and avoids unsupported engineering conclusions.
- It references command outputs that learners can reproduce instead of inventing solver behavior.

**Why the unsafe answer fails**

- It treats adapter detection as solver execution.
- It claims mesh adequacy, boundary-condition correctness, and design safety without command output or explicit validation evidence.

**References**

- Command output to cite: `python -m json.tool caereflex.json | head`, `python -m json.tool agent_context.json | head`, and `sed -n '1,120p' case_report.md`.
- Adapter behavior: `caereflex/adapters/openfoam.py` records source files, parses known dictionaries and `0/` field files, and sets do-not-claim notes for convergence, mesh adequacy, validation, and certification.
- Safety rule: `wiki/docs/user-guide/safe-use-policy.md` defines CaeReflex output as structured evidence, not engineering validation.

### Expert extension answer key

**Sample acceptable answer**

- CLI: `caereflex/cli/main.py` implements `inspect`, builds a `CaeReflexConfig`, calls `inspect_path`, saves the full JSON, and optionally exports agent context and Markdown.
- Service layer: `caereflex/services.py` handles adapter auto-detection, adapter dispatch, optional CrossRef attachment, loading, saving, and export routing.
- OpenFOAM adapter: `caereflex/adapters/openfoam.py` creates a `ReflexCase`, records provenance, scans expected OpenFOAM files plus `0/` fields, hashes bounded files, parses dictionaries and boundary fields, emits flags for missing expected files or residual-like log lines, and marks success or partial success based on flags.
- Exporters: `caereflex/exporters.py` serializes the full case, builds a compact agent context with safe-use and do-not-claim lists, and writes the Markdown report with limitations.
- Domain model: `caereflex/core/models.py` defines `ReflexCase`, `SourceFileRecord`, `TraceInfo`, `InspectionFlag`, `ResultFieldRecord`, provenance records, and export records used by all layers.

**Unsafe or incorrect answer**

- "The CLI directly reads every file recursively, runs OpenFOAM, validates residuals, and then the exporter certifies the case."

**Why the acceptable answer passes**

- It follows the actual control flow and identifies which layer performs inspection, export, and record modeling.
- It correctly describes residual-like log detection as an inspection flag, not a convergence decision.

**Why the unsafe answer fails**

- It invents solver execution and certification behavior.
- It misattributes adapter work to the CLI and ignores service orchestration and model/export boundaries.

**References**

- Command output to cite: the three walkthrough commands plus the generated `caereflex.json`, `agent_context.json`, and `case_report.md` outputs.
- Adapter behavior: `caereflex/adapters/openfoam.py` expected-file scanning and `_parse_file` logic.
- Safety rule: `caereflex/exporters.py` `SAFE_USE_POLICY` and `DO_NOT_CLAIM` entries.
