from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from caereflex.core.models import ReflexCase
from caereflex.rules import (
    RULE_PROTOCOL_VERSION,
    PhysicsRuleEvaluation,
    RuleEvaluationStatus,
    RuleEvidenceRef,
    RuleSeverity,
    evaluate_rule_pack,
    list_rule_packs,
)


def test_protocol_exposes_all_required_outcome_states():
    assert {item.value for item in RuleEvaluationStatus} == {
        "consistent", "inconsistent", "unknown", "not_applicable", "not_evaluated", "blocked"
    }
    manifests = list_rule_packs()
    assert manifests[0].protocol_version == RULE_PROTOCOL_VERSION
    assert manifests[0].pack_id == "openfoam.cfd-core"
    assert manifests[0].pack_version == "1.0.0"
    assert manifests[0].rule_ids == sorted(manifests[0].rule_ids)


def test_rule_evidence_requires_exact_pointer_and_compact_values():
    with pytest.raises(ValidationError, match="absolute JSON pointers"):
        RuleEvidenceRef(path="metadata/native_openfoam", value=1)
    with pytest.raises(ValidationError, match="ArrayRef"):
        RuleEvidenceRef(path="/bad", value=list(range(100)))


def test_non_openfoam_case_is_deterministically_not_applicable(tmp_path):
    case = ReflexCase(case_id="case_vtk", case_type="vtk", physics_tags=["post-processing"])
    first = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=tmp_path)
    second = evaluate_rule_pack(case, pack_id="openfoam.cfd-core", state_root=tmp_path)
    assert first.run_id == second.run_id
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.status == "not_applicable"
    assert all(item.status == "not_applicable" for item in first.results)


def test_evaluation_contract_keeps_remediation_and_limitations():
    evaluation = PhysicsRuleEvaluation(
        rule_id="TEST-001",
        rule_version="1.0.0",
        pack_id="test",
        pack_version="1.0.0",
        status=RuleEvaluationStatus.unknown,
        severity=RuleSeverity.warning,
        message="Evidence missing.",
        missing_evidence=["/metadata/example"],
        remediation="Supply evidence.",
        limitations=["No validation claim."],
    )
    assert evaluation.missing_evidence == ["/metadata/example"]
    assert evaluation.limitations == ["No validation claim."]


def test_release_metadata_is_aligned():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    from caereflex.version import __version__

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert __version__ == "2.0.0b4"
    assert project["project"]["version"] == __version__
    assert json.loads((root / "openapi" / "openapi.json").read_text(encoding="utf-8"))["info"]["version"] == __version__
    assert f"version: {__version__}" in (root / "CITATION.cff").read_text(encoding="utf-8")
