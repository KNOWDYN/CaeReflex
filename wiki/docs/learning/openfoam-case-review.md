# OpenFOAM Case Review

## Level

Beginner to expert.

## Audience

CFD engineers, CAE reviewers, and developers working with folder-based simulation artefacts.

## Learning objectives

By the end, you can:

1. inspect an OpenFOAM-like case folder;
2. identify solver dictionaries, boundary-condition files, material files, and numerical settings when detected;
3. interpret inspection flags as review prompts; and
4. state what a qualified engineer still needs to verify.

## Files used

- `examples/openfoam_cavity_minimal`
- [Architecture: Adapters](../architecture/adapters.md)
- [Safe Use Policy](../user-guide/safe-use-policy.md)

## Walkthrough

```bash
caereflex inspect-openfoam examples/openfoam_cavity_minimal --out openfoam_case.json
caereflex export agent-context openfoam_case.json --out openfoam_agent_context.json
caereflex export markdown openfoam_case.json --out openfoam_report.md
```

Review the outputs:

```bash
python -m json.tool openfoam_agent_context.json | head -80
sed -n '1,160p' openfoam_report.md
```

## What to observe

- CaeReflex reads OpenFOAM-like text files; it does not run OpenFOAM.
- Dictionary and boundary-condition evidence can help structure review.
- Missing or partial evidence should be carried into the final summary.

## Expected output and interpretation

A representative `openfoam_agent_context.json` from `examples/openfoam_cavity_minimal` should show the inspected dictionaries and initial fields:

```json
{
  "case_name": "openfoam_cavity_minimal",
  "case_type": "openfoam",
  "source_files": [
    {"relative_path": "system/controlDict", "hash_status": "complete"},
    {"relative_path": "system/fvSchemes", "hash_status": "complete"},
    {"relative_path": "constant/polyMesh/boundary", "hash_status": "complete"},
    {"relative_path": "0/U", "hash_status": "complete"}
  ],
  "result_fields": [
    {"name": "p", "association": "volume", "trace": {"source_files": ["0/p"]}},
    {"name": "U", "association": "volume", "trace": {"source_files": ["0/U"]}}
  ],
  "inspection_warnings": []
}
```

Interpret the output as follows:

- Extracted evidence: dictionary paths, boundary-file paths, initial field names, hashes, and trace source files are read from `examples/openfoam_cavity_minimal`.
- Inferred context: the OpenFOAM classification and summary are based on folder structure and recognized file names; CaeReflex has not run a solver.
- Warnings: preserve every `inspection_warnings` item if present. No warnings in this tiny fixture does not imply numerical readiness or case quality.
- Provenance: the full JSON includes `openfoam_inspection_started`; exported agent context may summarize provenance through `source_references`.
- Unsafe claims to avoid: do not claim solver execution, convergence, Courant-number acceptability, mesh adequacy, turbulence-model suitability, physical correctness, certification, or design safety.

## Beginner exercise

List three files from the case folder that CaeReflex inspected or referenced.

## Practitioner exercise

Write a review note with three sections: detected evidence, inspection limitations, and human follow-up checks.

## Expert extension

Inspect how the OpenFOAM adapter handles bounded scanning and safe text inspection. Propose one additional inspection flag that would improve review quality while staying read-only.

## Assessment checklist

- [ ] The learner distinguishes file inspection from solver execution.
- [ ] The learner explains at least one detected setting or source file.
- [ ] The learner lists follow-up checks without saying CaeReflex validated the simulation.

## Answer key

Use these examples to grade whether learners preserve file evidence, adapter limits, and safe-use boundaries.

### Beginner exercise answer key

**Sample acceptable answer**

- Three inspected or referenced files are `system/controlDict`, `system/fvSchemes`, and `0/U`.
- Other acceptable files for the bundled example include `system/fvSolution`, `constant/polyMesh/boundary`, `constant/transportProperties`, `constant/turbulenceProperties`, and `0/p` when present in the exported `source_files` list.
- These are files CaeReflex read or referenced during metadata extraction; they are not evidence that OpenFOAM was executed.

**Unsafe or incorrect answer**

- "The inspected files prove the solver ran and the cavity benchmark converged."

**Why the acceptable answer passes**

- It quotes source-file evidence from the exported agent context and keeps the claim at the level of read-only inspection.
- It does not infer numerical correctness from the presence of OpenFOAM dictionaries or initial field files.

**Why the unsafe answer fails**

- File discovery and dictionary parsing do not run the solver.
- Convergence requires explicit solver-log or residual evidence and qualified interpretation, not just source-file paths.

**References**

- Command output to cite: `python -m json.tool openfoam_agent_context.json | head -80` for `source_files`, `result_fields`, and `inspection_warnings`; `sed -n '1,160p' openfoam_report.md` for the report limitation text.
- Adapter behavior: `caereflex/adapters/openfoam.py` scans the expected OpenFOAM dictionary paths and files in the `0/` directory, then records file hashes and trace source files.
- Safety rule: `caereflex/exporters.py` and `wiki/docs/user-guide/safe-use-policy.md` prohibit validation, convergence, mesh adequacy, certification, and design-safety claims.

### Practitioner exercise answer key

**Sample acceptable answer**

#### Detected evidence

CaeReflex identified the folder as an OpenFOAM case and recorded file-derived evidence from dictionaries and initial field files, including source-file paths and hashes in `openfoam_agent_context.json`. It extracted field records such as `U` and `p` when the corresponding files are present, and it may extract boundary-condition, material-property, and numerical-setting records from recognized OpenFOAM dictionaries.

#### Inspection limitations

The inspection is read-only metadata extraction. It does not execute OpenFOAM, does not check mesh quality, does not prove that boundary conditions are physically correct, and does not establish convergence or validation. Empty `inspection_warnings` only means the adapter emitted no flag for this fixture.

#### Human follow-up checks

A qualified reviewer should inspect mesh quality, patch semantics, dimensions and units, solver choice, discretization schemes, tolerances, physical assumptions, residual histories, conservation checks, benchmark comparisons, and acceptance criteria before making engineering decisions.

**Unsafe or incorrect answer**

- "Detected evidence: the solver settings are correct. Limitations: none. Human checks: no follow-up needed because the exported report is a certification."

**Why the acceptable answer passes**

- It distinguishes detected metadata from engineering acceptance.
- It gives concrete follow-up checks without claiming CaeReflex performed them.

**Why the unsafe answer fails**

- It declares correctness and certification unsupported by the adapter or report.
- It removes required human review.

**References**

- Command output to cite: `python -m json.tool openfoam_agent_context.json | head -80` and `sed -n '1,160p' openfoam_report.md`.
- Adapter behavior: `_parse_file` in `caereflex/adapters/openfoam.py` maps recognized files to solver records, numerical settings, material properties, boundary conditions, and result fields.
- Safety rule: `caereflex/exporters.py` Markdown report preamble says the report is not validation, certification, safety approval, or convergence proof.

### Expert extension answer key

**Sample acceptable answer**

The OpenFOAM adapter performs bounded, read-only text inspection. It starts from a case folder, records an `openfoam_inspection_started` provenance event, checks a fixed list of expected OpenFOAM paths, adds warnings for missing expected files, scans the `0/` directory for initial field files, and limits post-processing/log collection to a small slice. For each considered file, it hashes up to the configured maximum file size and parses simple dictionary entries with regular expressions. An additional useful read-only flag would be `missing_initial_field_boundaryField`: warn when a `0/` field file lacks a `boundaryField` block or when a boundary patch appears in `constant/polyMesh/boundary` but is not represented in a field file.

**Unsafe or incorrect answer**

- "Improve the adapter by automatically running OpenFOAM, modifying bad boundary files, and suppressing warnings so agents can state the case is validated."

**Why the acceptable answer passes**

- The proposed flag improves review quality without changing source files or claiming solver results.
- It stays within CaeReflex's role as evidence extraction and review support.

**Why the unsafe answer fails**

- It changes the system from read-only inspection into solver execution and file mutation.
- It suppresses safety evidence and encourages unsupported validation claims.

**References**

- Command output to cite: `python -m json.tool openfoam_agent_context.json | head -80` for extracted records and warning shape.
- Adapter behavior: `caereflex/adapters/openfoam.py` expected paths, `0/` scan, limited log/post-processing scan, hashing, simple dictionary parsing, and residual-like-line flagging.
- Safety rule: `wiki/docs/user-guide/safe-use-policy.md` requires treating output as structured evidence rather than engineering validation.
