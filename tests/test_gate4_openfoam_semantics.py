from pathlib import Path

from caereflex.contracts import CONTRACT_VERSION
from caereflex.exporters import agent_context_dict
from caereflex.services import inspect_path


def _by_name(records):
    return {record.name: record for record in records}


def test_openfoam_fixture_has_exact_field_classes_and_dimensions():
    case = inspect_path("examples/openfoam_cavity_minimal", adapter="openfoam")
    fields = _by_name(case.result_fields)
    materials = _by_name(case.materials)

    assert case.contract_version == CONTRACT_VERSION
    assert fields["U"].field_type == "vector"
    assert fields["U"].components == 3
    assert fields["U"].metadata["field_class"] == "volVectorField"
    assert fields["U"].metadata["quantity_kind"] == "velocity"
    assert fields["U"].metadata["dimensions"] == [0, 1, -1, 0, 0, 0, 0]

    assert fields["p"].field_type == "scalar"
    assert fields["p"].components == 1
    assert fields["p"].metadata["field_class"] == "volScalarField"
    assert fields["p"].metadata["quantity_kind"] == "kinematic_pressure"
    assert fields["p"].metadata["dimensions"] == [0, 2, -2, 0, 0, 0, 0]

    assert materials["nu"].value == 0.01
    assert materials["nu"].metadata["quantity_kind"] == "kinematic_viscosity"
    assert materials["nu"].metadata["dimension_vector"] == [0, 2, -1, 0, 0, 0, 0]
    assert "m" in materials["nu"].units and "s" in materials["nu"].units


def test_openfoam_fixture_produces_non_blocking_dimensional_evidence():
    case = inspect_path("examples/openfoam_cavity_minimal", adapter="openfoam")
    checks = {check["subject_name"]: check for check in case.dimensional_checks}

    assert len(case.quantity_evidence) == 3
    assert checks["U"]["status"] == "consistent"
    assert checks["p"]["status"] == "consistent"
    assert checks["nu"]["status"] == "consistent"
    assert not any(check["blocks_automated_interpretation"] for check in case.dimensional_checks)
    assert not any(item.get("code") == "CRX-UNITS-DIMENSION-MISMATCH-001" for item in case.diagnostics)


def test_agent_context_exposes_units_summary_additively():
    case = inspect_path("examples/openfoam_cavity_minimal", adapter="openfoam")
    context = agent_context_dict(case)

    assert context["quantity_evidence"] == case.quantity_evidence
    assert context["dimensional_checks"] == case.dimensional_checks
    assert context["units_summary"]["quantity_evidence_count"] == 3
    assert context["units_summary"]["blocking_conflicts"] == 0
    assert "discovery_diagnostics" in context


def test_malformed_dimensions_fall_back_and_remain_visible(tmp_path: Path):
    case_root = tmp_path / "bad_case"
    (case_root / "system").mkdir(parents=True)
    (case_root / "constant" / "polyMesh").mkdir(parents=True)
    (case_root / "0").mkdir(parents=True)
    (case_root / "system" / "controlDict").write_text(
        "FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }\napplication simpleFoam;\n",
        encoding="utf-8",
    )
    (case_root / "constant" / "transportProperties").write_text(
        "FoamFile { version 2.0; format ascii; class dictionary; object transportProperties; }\n",
        encoding="utf-8",
    )
    (case_root / "constant" / "polyMesh" / "boundary").write_text("0\n(\n)\n", encoding="utf-8")
    (case_root / "0" / "U").write_text(
        "FoamFile { version 2.0; format ascii; class volVectorField; object U; }\n"
        "dimensions [0 1 broken 0 0 0 0];\n"
        "internalField uniform (0 0 0);\n",
        encoding="utf-8",
    )

    case = inspect_path(case_root, adapter="openfoam")
    field = next(record for record in case.result_fields if record.name == "U")

    assert field.field_type == "vector"
    assert field.metadata["units_status"] == "parse_failed"
    assert any(item.get("code") == "CRX-UNITS-PARSE-001" for item in case.diagnostics)
    assert any(flag.category == "units_parse_failure" for flag in case.inspection_flags)
