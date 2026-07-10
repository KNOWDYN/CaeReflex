import json

from caereflex.contracts import InspectionProfile
from caereflex.exporters import agent_context_dict
from caereflex.services import inspect_path


def test_inspection_carries_manifest_diagnostics_and_contract_version():
    case = inspect_path("examples/openfoam_cavity_minimal", profile=InspectionProfile.standard)
    assert case.contract_version.startswith("2.0")
    assert case.inspection_profile == "standard"
    assert case.case_manifest is not None
    assert case.case_manifest["case_hints"] == ["openfoam"]
    context = agent_context_dict(case)
    assert context["case_manifest_summary"]["entry_count"] > 0
    json.dumps(context)
