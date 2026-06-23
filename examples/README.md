# CaeReflex examples

This directory contains small, offline examples for learning the CaeReflex CLI, adapters, evidence export, and safe agent-integration patterns. The fixture files are intentionally tiny so the examples can run without solvers, CAD kernels, OpenFOAM, Gmsh, ParaView, or other heavy optional dependencies.

## Available examples

| Folder | Purpose | Start here |
| --- | --- | --- |
| [`gmsh_minimal/`](gmsh_minimal/) | Text-based inspection of a tiny Gmsh `.geo` geometry file. | [`gmsh_minimal/README.md`](gmsh_minimal/README.md) |
| [`openfoam_cavity_minimal/`](openfoam_cavity_minimal/) | Read-only inspection of a minimal OpenFOAM-like case folder. | [`openfoam_cavity_minimal/README.md`](openfoam_cavity_minimal/README.md) |
| [`vtk_minimal/`](vtk_minimal/) | Lightweight inspection of a legacy ASCII VTK result file. | [`vtk_minimal/README.md`](vtk_minimal/README.md) |
| [`crossref_context/`](crossref_context/) | Deterministic mocked CrossRef metadata attachment and BibTeX export. | [`crossref_context/README.md`](crossref_context/README.md) |
| [`agent_workflow/`](agent_workflow/) | Safe context-file and REST/OpenAPI notes for LLM agent workflows. | [`agent_workflow/README.md`](agent_workflow/README.md) |

## List bundled examples

```bash
caereflex examples list
```

Expected output:

```text
gmsh_minimal
openfoam_cavity_minimal
vtk_minimal
crossref_context
agent_workflow
```

## Run a bundled example

```bash
caereflex examples run gmsh_minimal --out-dir build
```

Expected output includes a successful status, a case ID, and an output JSON path under `build/`. The exact case ID may vary with file contents and hashing.

```text
Status: success
Case ID: case_...
Outputs:
- case: build/gmsh_minimal.caereflex.json
- agent_context: build/gmsh_minimal.agent_context.json
- report: build/gmsh_minimal.case_report.md
```

## Manual CLI equivalents

The example runner is a convenience wrapper. These commands show the equivalent manual workflows:

```bash
mkdir -p build

caereflex inspect-gmsh examples/gmsh_minimal/t1.geo \
  --out build/gmsh_case.json

caereflex inspect-openfoam examples/openfoam_cavity_minimal \
  --out build/openfoam_case.json

caereflex inspect-vtk examples/vtk_minimal/sample.vtk \
  --out build/vtk_case.json

caereflex crossref attach examples/crossref_context/sample_case.json \
  --query "lid-driven cavity OpenFOAM metadata" \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --limit 5 \
  --out build/case_with_literature.json

caereflex export bibtex build/case_with_literature.json \
  --out build/references.bib
```

## Expected outputs at a glance

- Gmsh example: `case_type` is `gmsh`; one source file and one geometry/mesh asset are recorded.
- OpenFOAM example: `case_type` is `openfoam`; the standard `0/`, `constant/`, and `system/` folders are inspected read-only.
- VTK example: `case_type` is `vtk`; scalar `pressure` and vector `velocity` fields are extracted from the legacy file.
- CrossRef example: two deterministic mock metadata records are attached; one record includes a mock abstract.
- Agent workflow example: no solver is run; the files are prompts and notes for safely consuming CaeReflex context.

## Related documentation

- [CLI reference](../docs/CLI.md)
- [REST API](../docs/REST_API.md)
- [Agent integration](../docs/AGENT_INTEGRATION.md)
- [Adapter guide](../docs/ADAPTERS.md)
- [CrossRef literature metadata](../docs/CROSSREF.md)
