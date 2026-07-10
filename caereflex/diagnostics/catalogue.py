"""Central diagnostic catalogue used by CLI, manifests, units, execution, and adapters."""
from __future__ import annotations

DIAGNOSTICS: dict[str, dict[str, str]] = {
    "CRX-SCAN-LIMIT-001": {
        "title": "File-count limit reached",
        "explanation": "The catalog stopped after the configured maximum number of entries.",
        "action": "Increase --max-files or inspect a narrower case root.",
    },
    "CRX-SCAN-LIMIT-002": {
        "title": "Depth limit reached",
        "explanation": "One or more directories were not traversed because the maximum scan depth was reached.",
        "action": "Increase --max-depth only when the additional filesystem scope is trusted.",
    },
    "CRX-SCAN-LIMIT-003": {
        "title": "Wall-time limit reached",
        "explanation": "Catalog generation stopped before all entries were visited.",
        "action": "Increase --max-wall-time or narrow the case root.",
    },
    "CRX-SCAN-SYMLINK-001": {
        "title": "Symbolic link not followed",
        "explanation": "CaeReflex catalogues symbolic links as metadata but does not follow them.",
        "action": "Place required artefacts directly under the configured case root.",
    },
    "CRX-PLUGIN-NONE-001": {
        "title": "No adapter matched",
        "explanation": "No installed adapter reported sufficient support for the case manifest.",
        "action": "Install an appropriate adapter plugin or select a more specific case root.",
    },
    "CRX-CACHE-READ-001": {
        "title": "Catalog cache could not be read",
        "explanation": "The SQLite catalog cache was unavailable or contained invalid data.",
        "action": "Run caereflex cache clean, then rescan the case.",
    },
    "CRX-UNITS-PARSE-001": {
        "title": "Dimension or unit expression could not be parsed",
        "explanation": "CaeReflex preserved the raw source value because it could not decode the dimensions or unit expression safely.",
        "action": "Review the raw source, correct the syntax or supply a human-reviewed unit mapping; do not infer a unit from the variable name alone.",
    },
    "CRX-UNITS-DIMENSION-MISMATCH-001": {
        "title": "Quantity name and dimensions conflict",
        "explanation": "The source name suggests one physical quantity while the explicit dimension vector supports another.",
        "action": "Inspect the source definition, solver convention and scaling; resolve the conflict before automated physical interpretation.",
    },
    "CRX-UNITS-AMBIGUOUS-001": {
        "title": "Dimensions support multiple quantity kinds",
        "explanation": "Dimensional analysis alone cannot distinguish among several physical quantities sharing the same base dimensions.",
        "action": "Use field class, solver model, source documentation or a qualified human annotation to resolve the semantic role.",
    },
    "CRX-UNITS-UNRESOLVED-001": {
        "title": "Quantity semantics unresolved",
        "explanation": "Neither the source name nor its dimensions matched the current CaeReflex quantity ontology.",
        "action": "Preserve the quantity as unknown and extend the ontology only with documented engineering evidence.",
    },
    "CRX-UNITS-MISSING-001": {
        "title": "Dimensions declaration missing",
        "explanation": "A field was found, but no parseable dimensions declaration was available.",
        "action": "Review the field source and supply dimensions explicitly; do not treat name-based inference as confirmed units.",
    },
    "CRX-EXEC-START-001": {
        "title": "Deep execution could not start",
        "explanation": "The execution request was rejected before an isolated worker could begin.",
        "action": "Review the source root, selected paths, execution policy, state directory, and filesystem permissions.",
    },
    "CRX-EXEC-BACKEND-001": {
        "title": "Execution backend failed",
        "explanation": "The selected isolated backend raised an exception and returned no complete deep-inspection result.",
        "action": "Inspect the parser-attempt ledger and worker log, then use a declared fallback or repair the input/backend installation.",
    },
    "CRX-EXEC-TIMEOUT-001": {
        "title": "Execution time budget exceeded",
        "explanation": "The isolated worker exceeded its wall-time budget and was terminated.",
        "action": "Narrow the inspection plan or increase the budget only for trusted inputs and backends.",
    },
    "CRX-EXEC-CRASH-001": {
        "title": "Execution worker crashed",
        "explanation": "The isolated worker exited without a valid result payload, including native-library crashes or forced termination.",
        "action": "Review the worker log and input fixture; do not retry untrusted malformed files without stronger isolation.",
    },
    "CRX-EXEC-RESULT-001": {
        "title": "Execution result invalid or oversized",
        "explanation": "The worker result could not be validated or exceeded the configured serialized-output limit.",
        "action": "Keep heavy data behind ArrayRef handles and reduce backend summary size.",
    },
    "CRX-EXEC-SOURCE-MUTATION-001": {
        "title": "Inspected source changed during execution",
        "explanation": "Before-and-after source snapshots differed while an isolated backend was running.",
        "action": "Treat the result as failed, investigate the backend, and restore the engineering source from a trusted copy if required.",
    },
    "CRX-EXEC-SNAPSHOT-PARTIAL-001": {
        "title": "Source snapshot only partially hashed",
        "explanation": "Some selected files exceeded the hashing budget, so immutability was checked using metadata rather than a complete byte hash.",
        "action": "Increase the source-hashing budget when byte-for-byte verification is required.",
    },
    "CRX-ARRAY-QUERY-001": {
        "title": "Lazy-array query rejected",
        "explanation": "An array query exceeded its result limit, requested an unsupported operation, or referenced invalid bounds or metadata.",
        "action": "Use describe first, request a smaller sample or slice, and select only operations declared by the ArrayRef.",
    },
    "CRX-ARTIFACT-INTEGRITY-001": {
        "title": "Artefact integrity check failed",
        "explanation": "A content-addressed artefact did not match its recorded SHA-256 digest or resolved outside the configured store.",
        "action": "Stop using the artefact, preserve logs, and recreate the local state directory from trusted sources.",
    },
}


def explain_diagnostic(code: str) -> dict[str, str] | None:
    return DIAGNOSTICS.get(code.upper())
