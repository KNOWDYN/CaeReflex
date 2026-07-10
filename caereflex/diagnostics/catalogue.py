"""Central diagnostic catalogue used by CLI, manifests, and future adapters."""
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
        "explanation": "No installed adapter reported sufficient support for the manifest.",
        "action": "Install an appropriate adapter plugin or select a more specific case root.",
    },
    "CRX-CACHE-READ-001": {
        "title": "Catalog cache could not be read",
        "explanation": "The SQLite catalog cache was unavailable or contained invalid data.",
        "action": "Run caereflex cache clean, then rescan the case.",
    },
}


def explain_diagnostic(code: str) -> dict[str, str] | None:
    return DIAGNOSTICS.get(code.upper())
