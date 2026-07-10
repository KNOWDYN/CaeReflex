from __future__ import annotations
from pathlib import Path
import json, re
from typing import Any
from caereflex.core.models import ReflexCase, ExportRecord
from caereflex.core.validation import safe_display_path

SAFE_USE_POLICY = [
    "Use extracted facts as file-derived facts.",
    "Treat inferred facts as tentative.",
    "Treat CrossRef metadata as literature context, not validation.",
    "Do not claim metadata-only records were read as full papers.",
    "Do not claim simulation convergence unless explicit evidence is present.",
    "Do not claim mesh adequacy.",
    "Do not claim engineering certification.",
    "Do not claim design safety.",
    "Treat unresolved or conflicted dimensions as requiring human review.",
]
DO_NOT_CLAIM = [
    "Do not claim that CaeReflex validates this simulation.",
    "Do not claim convergence unless explicit residual/convergence evidence is present.",
    "Do not claim mesh adequacy.",
    "Do not claim engineering certification.",
    "Do not claim design safety.",
    "Do not claim metadata-only CrossRef records were read as full papers.",
    "Do not convert an unresolved dimension or ambiguous field name into a confirmed physical quantity.",
]

def case_to_dict(case: ReflexCase) -> dict[str, Any]:
    return case.model_dump(mode="json")

def export_reflexcase_json(case: ReflexCase, out: str | Path) -> Path:
    path = Path(out); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(case_to_dict(case), indent=2, ensure_ascii=False), encoding="utf-8")
    case.exports.append(ExportRecord(export_type="caereflex_json", relative_path=safe_display_path(path)))
    return path

def load_reflexcase(path: str | Path) -> ReflexCase:
    return ReflexCase.model_validate_json(Path(path).read_text(encoding="utf-8"))

def _units_summary(case: ReflexCase) -> dict[str, Any]:
    counts = {"consistent": 0, "conflicted": 0, "unresolved": 0, "not_applicable": 0}
    blocking = 0
    for check in case.dimensional_checks:
        status = str(check.get("status", "unresolved"))
        counts[status] = counts.get(status, 0) + 1
        if check.get("blocks_automated_interpretation"):
            blocking += 1
    return {
        "quantity_evidence_count": len(case.quantity_evidence),
        "dimensional_check_count": len(case.dimensional_checks),
        "status_counts": counts,
        "blocking_conflicts": blocking,
        "interpretation": (
            "No dimensional checks were produced."
            if not case.dimensional_checks
            else "Review blocking conflicts before automated physical interpretation."
            if blocking
            else "No blocking dimensional conflicts were emitted; this is not a full physics validation."
        ),
    }

def agent_context_dict(case: ReflexCase) -> dict[str, Any]:
    extracted = []
    inferred = []
    for asset in case.assets:
        record = {"name": asset.name, "asset_type": asset.asset_type, "metrics": asset.metrics, "properties": asset.properties, "trace": asset.trace.model_dump(mode="json")}
        if asset.trace.source_kind == "inferred": inferred.append(record)
        else: extracted.append(record)
    return {
        "schema_version": case.schema_version,
        "contract_version": case.contract_version,
        "inspection_profile": case.inspection_profile,
        "case_id": case.case_id,
        "case_name": case.case_name,
        "case_type": case.case_type,
        "inspection_status": case.inspection.status,
        "detected_formats": case.detected_formats,
        "detected_tools": case.detected_tools,
        "physics_tags": case.physics_tags,
        "safe_use_policy": SAFE_USE_POLICY,
        "extracted_facts": extracted,
        "inferred_facts": inferred,
        "source_files": [{"file_id": f.file_id, "relative_path": f.relative_path, "suffix": f.suffix, "size_bytes": f.size_bytes, "hash_status": f.hash_status} for f in case.source_files],
        "solver_records": [s.model_dump(mode="json") for s in case.solver_records],
        "boundary_conditions": [b.model_dump(mode="json") for b in case.boundary_conditions],
        "materials": [m.model_dump(mode="json") for m in case.materials],
        "numerical_settings": [n.model_dump(mode="json") for n in case.numerical_settings],
        "result_fields": [r.model_dump(mode="json") for r in case.result_fields],
        "quantity_evidence": case.quantity_evidence,
        "dimensional_checks": case.dimensional_checks,
        "units_summary": _units_summary(case),
        "literature_context": case.literature_context.model_dump(mode="json"),
        "inspection_warnings": [f.model_dump(mode="json") for f in case.inspection_flags],
        "discovery_diagnostics": case.diagnostics,
        "diagnostics": case.diagnostics,
        "case_manifest_summary": _manifest_summary(case.case_manifest),
        "available_actions": ["get_engineering_case", "get_agent_context", "get_units_report", "explain_dimensional_evidence", "search_related_research", "attach_related_research", "export_case_report", "export_bibliography"],
        "recommended_next_actions": case.agent_summary.recommended_next_actions or ["review_units_report", "export_case_report", "attach_related_research"],
        "do_not_claim": list(dict.fromkeys(DO_NOT_CLAIM + case.agent_summary.do_not_claim)),
        "source_references": [p.event for p in case.provenance],
    }

def _manifest_summary(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not manifest:
        return None
    root_uri = str(manifest.get("root_uri") or "")
    root_display = root_uri.rstrip("/").rsplit("/", 1)[-1] if root_uri else None
    return {
        "manifest_id": manifest.get("manifest_id"),
        "root_display": root_display,
        "entry_count": len(manifest.get("entries", [])),
        "detected_formats": manifest.get("detected_formats", []),
        "case_hints": manifest.get("case_hints", []),
        "truncated": manifest.get("truncated", False),
        "limits_reached": manifest.get("limits_reached", []),
    }

def export_agent_context_json(case: ReflexCase, out: str | Path) -> Path:
    path = Path(out); path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(agent_context_dict(case), indent=2, ensure_ascii=False)
    text = re.sub(r'([A-Za-z]:\\[^"\n]+|/home/[^"\n]+|/mnt/data/[^"\n]+)', '[absolute_path_removed]', text)
    path.write_text(text, encoding="utf-8")
    case.exports.append(ExportRecord(export_type="agent_context_json", relative_path=safe_display_path(path)))
    return path

def export_agent_context_md(case: ReflexCase, out: str | Path) -> Path:
    ctx = agent_context_dict(case)
    lines = [f"# Agent Context — {case.case_name}", "", f"Case ID: `{case.case_id}`", f"Status: `{case.inspection.status}`", "", "## Safe Use Policy"]
    lines += [f"- {item}" for item in SAFE_USE_POLICY]
    lines += ["", "## Units Summary", "", f"- Quantity evidence: {ctx['units_summary']['quantity_evidence_count']}", f"- Dimensional checks: {ctx['units_summary']['dimensional_check_count']}", f"- Blocking conflicts: {ctx['units_summary']['blocking_conflicts']}"]
    lines += ["", "## Do Not Claim"] + [f"- {item}" for item in ctx["do_not_claim"]]
    path = Path(out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return path

def export_markdown_report(case: ReflexCase, out: str | Path) -> Path:
    lines = [
        f"# CaeReflex Case Report — {case.case_name}", "",
        "This report was generated from metadata extracted or inferred by CaeReflex. It is not an engineering validation report, certification, safety approval, or convergence proof. All engineering conclusions must be reviewed by qualified human experts using appropriate simulation, verification, validation, and experimental evidence.", "",
        f"- Case ID: `{case.case_id}`", f"- Case type: `{case.case_type}`", f"- Inspection status: `{case.inspection.status}`", "",
        "## Detected Artefacts", "",
    ]
    lines += [f"- Formats: {', '.join(case.detected_formats) or 'none'}", f"- Tools: {', '.join(case.detected_tools) or 'none'}", f"- Source files: {len(case.source_files)}"]
    lines += ["", "## Extracted Facts", ""]
    if case.assets:
        for asset in case.assets: lines.append(f"- {asset.name} ({asset.asset_type}); metrics: `{asset.metrics}`")
    else: lines.append("- No engineering assets extracted.")
    lines += ["", "## Boundary Conditions", ""]
    lines += [f"- {condition.patch}: field={condition.field}, type={condition.type}, value={condition.value}" for condition in case.boundary_conditions] or ["- None extracted."]
    lines += ["", "## Numerical Settings", ""]
    lines += [f"- {setting.category}/{setting.name}: `{setting.value}`" for setting in case.numerical_settings[:50]] or ["- None extracted."]
    lines += ["", "## Result Fields", ""]
    lines += [f"- {field.name}: {field.field_type}, association={field.association}, components={field.components}, quantity={field.metadata.get('quantity_kind')}, unit={field.metadata.get('canonical_unit')}" for field in case.result_fields] or ["- None extracted."]
    lines += ["", "## Dimensions and Units", ""]
    units_summary = _units_summary(case)
    lines += [f"- Quantity evidence records: {units_summary['quantity_evidence_count']}", f"- Dimensional checks: {units_summary['dimensional_check_count']}", f"- Blocking conflicts: {units_summary['blocking_conflicts']}", f"- Interpretation: {units_summary['interpretation']}"]
    for check in case.dimensional_checks:
        lines.append(f"- **{check.get('status', 'unresolved')}** `{check.get('subject_name', 'unknown')}`: {check.get('message', '')}")
    lines += ["", "## CrossRef Metadata", ""]
    if case.literature_evidence:
        for record in case.literature_evidence: lines.append(f"- {record.title or 'Untitled'} ({record.year or 'n.d.'}), DOI: {record.doi or 'none'}, status: {record.evidence_status}")
    else: lines.append("- No CrossRef metadata attached.")
    lines += ["", "## Inspection Flags", ""]
    lines += [f"- **{flag.severity}** `{flag.category}`: {flag.message}" for flag in case.inspection_flags] or ["- None emitted."]
    if case.diagnostics:
        lines += ["", "## Diagnostics", ""]
        lines += [f"- **{diagnostic.get('severity', 'info')}** `{diagnostic.get('code', 'unknown')}`: {diagnostic.get('message', '')}" for diagnostic in case.diagnostics]
    lines += ["", "## Limitations and Do-Not-Claim Notes", ""]
    lines += [f"- {item}" for item in DO_NOT_CLAIM]
    path = Path(out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n".join(lines)+"\n", encoding="utf-8")
    case.exports.append(ExportRecord(export_type="markdown_report", relative_path=safe_display_path(path)))
    return path

def export_bibtex(case: ReflexCase, out: str | Path) -> Path:
    entries = []
    for index, record in enumerate(case.literature_evidence, start=1):
        key = bib_key(record, index)
        fields = {"title": record.title or "Untitled", "year": str(record.year or ""), "doi": record.doi or "", "url": record.url or "", "journal": record.container_title or ""}
        if record.authors: fields["author"] = " and ".join(record.authors)
        body = ",\n".join([f"  {key_name} = {{{value}}}" for key_name, value in fields.items() if value])
        entries.append(f"@article{{{key},\n{body}\n}}")
    if not entries: entries.append("% No literature evidence records were attached to this ReflexCase.")
    path = Path(out); path.parent.mkdir(parents=True, exist_ok=True); path.write_text("\n\n".join(entries)+"\n", encoding="utf-8")
    case.exports.append(ExportRecord(export_type="bibtex", relative_path=safe_display_path(path)))
    return path

def bib_key(record: Any, index: int) -> str:
    name = (record.authors[0].split()[-1] if record.authors else "caereflex").lower()
    year = record.year or "nd"
    return re.sub(r"[^A-Za-z0-9_]", "", f"{name}{year}_{index}")
