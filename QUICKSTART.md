# Quickstart

Check the installation and catalog a case before deep inspection:

```bash
caereflex doctor
caereflex scan examples/openfoam_cavity_minimal --out manifest.json
caereflex adapters probe examples/openfoam_cavity_minimal
```

Offline inspection path:

```bash
caereflex examples list
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal \
  --manifest-out manifest.json \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

Mock CrossRef path:

```bash
caereflex crossref attach examples/crossref_context/sample_case.json \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --out caereflex.with_literature.json
caereflex export bibtex caereflex.with_literature.json --out references.bib
```

See `docs/GATES_1_3_FOUNDATION.md`, `docs/CLI_FOUNDATION.md`, and `docs/ADAPTER_PLUGIN_CONTRACT.md` for the new contracts, catalog mode, and plugin boundary.
