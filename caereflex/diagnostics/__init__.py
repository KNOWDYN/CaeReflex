from .catalogue import DIAGNOSTICS, explain_diagnostic

DIAGNOSTICS.update({
    "CRX-SPATIAL-QUERY-001": {
        "title": "Spatial query rejected",
        "explanation": "A spatial graph query used an unknown graph, frame or entity, invalid filter, or unsupported operation.",
        "action": "Describe the graph first, use canonical identifiers, and retry only with filters supported by caereflex.spatial-query/1.0.",
    },
    "CRX-SPATIAL-QUERY-LIMIT-001": {
        "title": "Spatial query limit reached",
        "explanation": "A page, metadata scan, relation traversal or serialized response reached its configured bound.",
        "action": "Use a narrower filter, a smaller page, or the returned continuation offset; increase limits only for trusted local state.",
    },
    "CRX-SPATIAL-QUERY-FRAME-001": {
        "title": "Spatial frame comparison unavailable",
        "explanation": "The query would require an unrecorded coordinate transform, unit conversion or cross-frame comparison.",
        "action": "Query entities in one explicit frame or add reviewed transform evidence in a later supported workflow; do not assume equivalence.",
    },
    "CRX-GATE6-COMPAT-001": {
        "title": "Gate 6 spatial compatibility contract violated",
        "explanation": "A spatial snapshot, store or query response violated the frozen Gate 6 graph, mapping, ArrayRef or bounded-query requirements.",
        "action": "Treat Gate 6 acceptance as failed, preserve the source and native evidence, and repair the graph or registry without inventing spatial semantics.",
    },
})

__all__ = ["DIAGNOSTICS", "explain_diagnostic"]
