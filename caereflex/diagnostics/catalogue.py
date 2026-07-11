"""Central diagnostic catalogue used by CLI, manifests, units, execution, spatial mapping, and adapters."""
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
    "CRX-GATE5-COMPAT-001": {
        "title": "Gate 5 backend compatibility contract violated",
        "explanation": "A backend returned a payload that violated the frozen Gate 5 envelope, including unsafe paths, non-finite values, mismatched counts, invalid artefact references or materialised heavy arrays.",
        "action": "Treat the deep result as failed, inspect the worker log and update the backend to caereflex.gate5.backend-result/1.0 before retrying.",
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
    "CRX-SPATIAL-MAP-001": {
        "title": "Native evidence could not be mapped to a spatial graph",
        "explanation": "The Gate 6B mapper rejected or could not persist a native backend summary without inventing spatial evidence.",
        "action": "Keep the native execution result, inspect the mapping diagnostic, and correct the backend summary or ArrayRef registry before retrying.",
    },
    "CRX-SPATIAL-MAP-ARRAY-001": {
        "title": "Spatial array ownership unresolved",
        "explanation": "A valid ArrayRef could not be associated with a canonical entity because its native source asset or role did not match the backend summary.",
        "action": "Preserve the ArrayRef as unmapped and review its source_asset_id, association and native role; do not guess ownership.",
    },
    "CRX-OPENFOAM-NATIVE-FALLBACK-001": {
        "title": "OpenFOAM mesh decoding fell back",
        "explanation": "A native OpenFOAM mesh component was binary, malformed, directive-bearing, truncated or otherwise unsupported by the bounded ASCII reader.",
        "action": "Review the source file and parser attempt. Use a trusted optional backend for binary data or preserve the metadata-only result.",
    },
    "CRX-OPENFOAM-FIELD-FALLBACK-001": {
        "title": "OpenFOAM field values were not decoded",
        "explanation": "The field header could be inspected, but internal values were binary, directive-bearing, malformed or unsupported.",
        "action": "Do not treat the field as numerically available. Review the attempt ledger or use a trusted reader that explicitly supports the field encoding.",
    },
    "CRX-GMSH-READ-001": {
        "title": "Gmsh source could not be read",
        "explanation": "The selected Gmsh artefact could not be read within the path or byte limits of the execution plan.",
        "action": "Confirm the manifest path and increase the read budget only for a trusted source.",
    },
    "CRX-GMSH-MESHIO-FALLBACK-001": {
        "title": "meshio decoding fell back",
        "explanation": "The optional meshio reader was installed but could not decode the selected mesh, so CaeReflex tried its bounded core ASCII reader.",
        "action": "Review the meshio exception in the attempt ledger. Preserve the core-reader result if it decoded successfully.",
    },
    "CRX-GMSH-MSH-FALLBACK-001": {
        "title": "Gmsh mesh decoding fell back to fingerprint",
        "explanation": "Neither the optional meshio path nor the bounded MSH 2.x/4.x ASCII reader produced native mesh evidence.",
        "action": "Treat nodes, topology, physical groups and fields as unavailable. Review the encoding and use an explicitly supported trusted reader if needed.",
    },
    "CRX-GMSH-GEO-PARTIAL-001": {
        "title": "Gmsh geometry declarations only partially resolved",
        "explanation": "The .geo file contained procedural or unsupported declarations. CaeReflex did not execute the script and preserved unresolved statements explicitly.",
        "action": "Review the unresolved declarations or provide an exported .msh file. Do not infer the geometry produced by unexecuted script logic.",
    },
    "CRX-GMSH-CAD-FINGERPRINT-001": {
        "title": "Gmsh-oriented CAD file fingerprinted only",
        "explanation": "STEP, IGES or BREP geometry was identified and hashed but not decoded because the optional Gmsh API was not explicitly enabled.",
        "action": "Keep the fingerprint-only evidence or explicitly enable the isolated optional API for trusted files; mesh generation remains disabled.",
    },
    "CRX-GMSH-API-FALLBACK-001": {
        "title": "Optional Gmsh API inspection fell back",
        "explanation": "The explicitly enabled isolated Gmsh API path could not inspect the file and returned to fingerprint-only evidence.",
        "action": "Review the native-library failure and file format. Do not assume entity or topology evidence is available.",
    },
    "CRX-VTK-READ-001": {
        "title": "VTK source could not be read",
        "explanation": "The selected VTK artefact could not be read within the execution plan's path or byte limits.",
        "action": "Confirm the manifest path and increase the read budget only for a trusted source.",
    },
    "CRX-VTK-PYVISTA-FALLBACK-001": {
        "title": "PyVista/VTK decoding fell back",
        "explanation": "The optional PyVista/VTK reader was installed but did not decode the dataset, so CaeReflex tried meshio next.",
        "action": "Review the native-reader exception and continue only with the explicitly recorded fallback evidence.",
    },
    "CRX-VTK-MESHIO-FALLBACK-001": {
        "title": "VTK meshio decoding fell back",
        "explanation": "The optional meshio reader did not decode the VTK dataset, so CaeReflex tried the bounded dependency-free reader.",
        "action": "Review the attempt ledger and preserve the bounded core result only when its status is decoded.",
    },
    "CRX-VTK-CORE-FALLBACK-001": {
        "title": "VTK decoding fell back to fingerprint",
        "explanation": "Neither an available optional reader nor the bounded legacy/XML reader produced native dataset evidence.",
        "action": "Treat points, cells and fields as unavailable; inspect the encoding and reader diagnostics before selecting another trusted backend.",
    },
    "CRX-VTK-XML-ENCODING-001": {
        "title": "VTK XML encoding requires an optional reader",
        "explanation": "The dependency-free XML reader encountered appended, compressed or otherwise unsupported heavy-data encoding.",
        "action": "Install and use the optional VTK/PyVista backend for a trusted file, or retain fingerprint-only evidence.",
    },
    "CRX-VTK-COLLECTION-REFERENCE-001": {
        "title": "VTK collection reference not loaded",
        "explanation": "A collection or parallel metadata file referenced an unsafe path or a dataset absent from the selected manifest.",
        "action": "Review and normalise relative references inside the trusted case root; CaeReflex will not fetch or traverse external references automatically.",
    },
}


def explain_diagnostic(code: str) -> dict[str, str] | None:
    return DIAGNOSTICS.get(code.upper())
