# crossref_context

This directory demonstrates a deterministic, mock-first CrossRef workflow. It is designed for tests and documentation, so no live CrossRef network call is required when `--mock-response` is supplied.

## Files

- [`sample_case.json`](sample_case.json) — a minimal `ReflexCase` for an OpenFOAM-style cavity example with CFD-related tags and no attached literature yet.
- [`mock_crossref_response.json`](mock_crossref_response.json) — a CrossRef-shaped response fixture with two DOI metadata records.
- [`expected_literature_context.json`](expected_literature_context.json) — high-level deterministic expectations used by tests: the generated summary should mention CrossRef literature context and two records are expected.

## Attach mocked CrossRef metadata

```bash
mkdir -p build
caereflex crossref attach examples/crossref_context/sample_case.json \
  --query "lid-driven cavity OpenFOAM" \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --limit 5 \
  --out build/case_with_literature.json
```

Expected output snippet:

```text
Status: success
Case ID: case_sample_crossref
CrossRef literature context generated from 2 metadata record(s); 1 record(s) included available abstracts.
Outputs:
- caereflex_json: build/case_with_literature.json
```

Expected JSON highlights:

```json
{
  "case_id": "case_sample_crossref",
  "case_type": "openfoam",
  "literature_evidence_count": 2
}
```

Because `--mock-response` is present, the command reads the local fixture instead of contacting the live CrossRef API.

## Export BibTeX

```bash
caereflex export bibtex build/case_with_literature.json --out build/references.bib
```

Expected output snippet:

```text
Status: success
Outputs:
- bibtex: build/references.bib
```

The resulting file contains entries for the two mock DOIs, such as `10.0000/example.cavity.1` and `10.0000/example.openfoam.2`.

## Interpretation limits

CrossRef output is metadata context only. Metadata records and mock abstracts do not prove that papers were read in full, do not validate the simulation, and do not establish convergence, mesh adequacy, or design safety.

## Related documentation

- [CLI reference](../../docs/CLI.md)
- [REST API](../../docs/REST_API.md)
- [Agent integration](../../docs/AGENT_INTEGRATION.md)
- [Adapter guide](../../docs/ADAPTERS.md)
- [CrossRef literature metadata](../../docs/CROSSREF.md)
