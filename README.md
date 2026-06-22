# CaeReflex

CaeReflex is a source-available Python package that turns Gmsh, OpenFOAM, and ParaView/VTK-compatible simulation artefacts into structured, agent-readable, provenance-aware, CrossRef-grounded engineering cases.

CaeReflex is an inspection and documentation aid. It allows you to connect any LLM agent to a CAE simulation case, and identify any related research from CrossRef. CaeReflex makes your LLM agent capable of understanding CAE simulation cases and include their information in its reasoning. CaeReflex does not run solvers, validate simulations, certify engineering results, prove convergence, assess mesh adequacy, or replace qualified engineering judgement.

## Install

```bash
pip install -e .
pip install -e ".[server]"
pip install -e ".[mesh]"
pip install -e ".[vtk]"
pip install -e ".[gmsh]"
pip install -e ".[all,dev]"
```

## Quickstart

```bash
caereflex examples list
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal --out caereflex.json
caereflex export agent-context caereflex.json --out agent_context.json
caereflex export markdown caereflex.json --out case_report.md
```

## Supported files

- Gmsh `.geo` in core mode; `.msh` with optional mesh extras.
- OpenFOAM-like case folders through read-only text inspection.
- VTK/ParaView-compatible result files with safe fallback behaviour.
- CrossRef DOI metadata and available abstracts when explicitly requested.

## Licence summary

CaeReflex is source-available. Academic research, teaching, and non-commercial evaluation are free. Commercial use requires a paid commercial licence. CaeReflex is not released under an OSI-approved open-source licence.

See `LICENSE.md`, `ACADEMIC_USE.md`, and `COMMERCIAL_LICENSE.md`.
