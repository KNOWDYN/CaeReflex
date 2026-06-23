# CrossRef literature metadata

CaeReflex can attach DOI metadata and CrossRef-provided abstracts to a `ReflexCase` as lightweight literature context. The implementation lives in `caereflex/evidence/crossref.py`, the BibTeX exporter lives in `caereflex/exporters.py`, and the same workflow is exposed through explicit CLI commands and REST endpoints.

## Purpose

The CrossRef integration is intended to enrich a `ReflexCase` with related literature metadata:

- DOI, title, authors, publication year, venue, URL, and selected CrossRef metadata.
- Abstract text when the CrossRef work record includes an abstract.
- A `LiteratureContext` summary that records the queries used, records used, and limitations.

This context helps users see potentially related DOI records next to the engineering case. It is not an engineering-correctness checker, a proof workflow, or a literature-review engine.

## Explicit-only behavior

CrossRef is contacted only when a user explicitly chooses a CrossRef workflow:

- CLI CrossRef commands such as `caereflex crossref search` and `caereflex crossref attach`.
- Explicit inspection flags such as `--attach-crossref`.
- REST CrossRef endpoints such as `POST /cases/{case_id}/crossref/search` and `POST /cases/{case_id}/crossref/attach`.

CaeReflex does not silently call CrossRef during ordinary case loading or local inspection unless the explicit CrossRef flag or endpoint is used.

The integration queries CrossRef work metadata through `https://api.crossref.org/works`. It does not perform full-paper search, download PDFs, scrape publisher websites, bypass access controls, or infer that a metadata hit means a paper was read.

## Query generation

`generate_queries(case, user_query, include_case_tags)` builds one or more CrossRef query strings.

Behavior:

1. If `user_query` is provided, it is added first and used exactly as the user supplied it.
2. If `include_case_tags` is true, CaeReflex builds a case-derived query from:
   - `case.case_name`
   - `case.case_type`
   - up to the first five `case.physics_tags`
   - any `case.detected_tools`
3. Empty values and `unknown` are skipped.
4. Duplicate query strings are removed while preserving order.
5. If no query was otherwise generated, the case name is used as the fallback.

For example, the sample case named `openfoam_cavity_minimal` has physics tags such as `CFD`, `finite volume`, and `incompressible flow`, plus the detected tool `OpenFOAM`. With `include_case_tags=true`, a generated query can therefore include both the case identity and physics/tool context. These tags only influence text search terms; they are not treated as evidence that a CrossRef record shows case correctness.

## CLI workflows

### Search without mutating the case

Use `crossref search` to return records and a literature context without writing them back into the input case:

```bash
caereflex crossref search CASE_JSON --query "lid-driven cavity OpenFOAM metadata"
```

Useful options:

- `--mailto EMAIL`: sends a CrossRef `mailto` parameter and a CaeReflex user agent containing the mail address.
- `--limit N`: limits the number of unique records returned after DOI/title de-duplication.
- `--include-case-tags` / `--no-include-case-tags`: controls whether case name, case type, physics tags, and detected tools are appended as an additional generated query.
- `--mock-response PATH`: loads a local CrossRef-shaped JSON response instead of making a live network call.
- `--out PATH`: writes the search result JSON to a file.

### Attach records to a case

Use `crossref attach` to mutate the exported `ReflexCase` by adding `literature_evidence`, `literature_context`, and a `crossref_attached` provenance event:

```bash
caereflex crossref attach CASE_JSON \
  --query "lid-driven cavity OpenFOAM metadata" \
  --out caereflex.with_literature.json
```

The same `--mailto`, `--limit`, `--include-case-tags`, and `--mock-response` options are available for attach workflows.

## REST workflows

The REST API exposes the same explicit-only behavior for cases stored by the CaeReflex server.

### `POST /cases/{case_id}/crossref/search`

Searches CrossRef for a stored case and returns records plus `literature_context`. This endpoint does not save literature records onto the stored case.

Example request body:

```json
{
  "query": "lid-driven cavity OpenFOAM metadata",
  "include_case_tags": true,
  "limit": 5,
  "mailto": "user@example.com",
  "mock_response": "examples/crossref_context/mock_crossref_response.json"
}
```

### `POST /cases/{case_id}/crossref/attach`

Searches CrossRef for a stored case, attaches the resulting records and context, persists the updated case, and returns the updated `ReflexCase` JSON.

Example request body:

```json
{
  "query": "lid-driven cavity OpenFOAM metadata",
  "include_case_tags": true,
  "limit": 5,
  "mailto": "user@example.com",
  "mock_response": "examples/crossref_context/mock_crossref_response.json"
}
```

## Data model

CrossRef results are stored as `LiteratureEvidenceRecord` objects. Important fields include:

- `doi`, `title`, `authors`, `year`, `container_title`, `url`, and `abstract`.
- `evidence_status`, which indicates how much literature content was available to CaeReflex.
- `relevance_score`, a simple text-match score.
- `query`, the query string that produced the record.
- `metadata_subset`, currently including CrossRef fields such as type, publisher, and reference count.
- `trace`, with `source_kind="external_metadata"` and `adapter="crossref"`.

`LiteratureContext` records the surrounding context:

- `queries`: query strings generated or supplied for the search.
- `records_used`: DOI or title identifiers for records included in the context.
- `summary`: a short count-based summary.
- `limitations`: safety limitations for interpreting CrossRef metadata.
- `do_not_claim`: model-level guardrails for downstream agent usage.

`EvidenceStatus` values are:

- `abstract_available`: CrossRef metadata included an abstract, and CaeReflex cleaned the abstract markup into text.
- `metadata_only`: CrossRef returned metadata but no abstract.
- `reference_only`: reserved for records represented only as a reference/citation.
- `unavailable`: reserved for cases where the literature item is known but usable metadata is unavailable.

Current CrossRef parsing marks records as `abstract_available` when an abstract exists; otherwise it marks them as `metadata_only`.

## Relevance score

`relevance_score` is lightweight text matching, not scientific evidence.

CaeReflex tokenizes the query into alphanumeric terms longer than two characters, then checks how many of those terms appear in the combined title and abstract text. The score is the fraction of query terms found, rounded to three decimals.

A high score means the query words overlap the title or abstract. It does not mean:

- the paper supports the simulation setup,
- the simulation is converged or accurate,
- the paper was read in full,
- the record is the best or most authoritative source, or
- the returned set is a complete literature review.

## Mocked deterministic example

The `examples/crossref_context` directory provides an offline, deterministic CrossRef workflow:

- `sample_case.json`: a minimal `ReflexCase` with OpenFOAM and CFD-related tags.
- `mock_crossref_response.json`: a CrossRef-shaped response used instead of a live network call.
- `expected_literature_context.json`: expected high-level assertions for deterministic tests, including that the generated summary contains `CrossRef literature context generated` and that two records are expected.

Run the mock attach workflow:

```bash
caereflex crossref attach examples/crossref_context/sample_case.json \
  --query "lid-driven cavity OpenFOAM metadata" \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --limit 5 \
  --out caereflex.with_literature.json
```

Because `--mock-response` is supplied, this example does not call the live CrossRef API. It parses the local mock response, produces deterministic `LiteratureEvidenceRecord` values, and writes the attached case to `caereflex.with_literature.json`.

## BibTeX export

After attaching literature records, export a bibliography with:

```bash
caereflex export bibtex CASE_JSON --out references.bib
```

`export_bibtex` emits one `@article` entry per attached `LiteratureEvidenceRecord`, using the title, year, DOI, URL, journal/container title, and authors when present. If no literature evidence records are attached, the output file contains a comment indicating that no records were available.

## Required safety language

Always preserve these interpretation limits when presenting CrossRef results:

- CrossRef metadata does not show simulation setup correctness.
- Metadata-only records were not read as full papers.
- Abstract availability does not imply complete literature review.
