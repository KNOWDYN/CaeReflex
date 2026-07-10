from pydantic import ValidationError
import pytest

from caereflex.contracts import (
    AdapterCapabilities,
    ArrayRef,
    CaseManifest,
    EvidenceState,
    EvidenceValue,
    InspectionBudget,
    ManifestEntry,
    QuantityEvidence,
)


def test_contracts_are_backend_neutral_and_serializable():
    quantity = QuantityEvidence(
        magnitude=0.01,
        unit="m^2/s",
        dimension_vector=(0, 2, -1, 0, 0, 0, 0),
        quantity_kind="kinematic_viscosity",
        evidence_state=EvidenceState.exactly_parsed,
        source_path="constant/transportProperties",
    )
    payload = quantity.model_dump(mode="json")
    assert payload["unit"] == "m^2/s"
    assert payload["dimension_vector"] == [0, 2, -1, 0, 0, 0, 0]
    assert payload["evidence_state"] == "exactly_parsed"


def test_evidence_confidence_is_bounded():
    with pytest.raises(ValidationError):
        EvidenceValue(confidence=1.1)


def test_array_reference_does_not_materialise_data():
    ref = ArrayRef(uri="artifact://mesh/points", format="zarr", shape=(10_000_000, 3), dtype="float64")
    assert ref.shape == (10_000_000, 3)
    assert "values" not in ref.model_dump()


def test_budget_rejects_negative_limits():
    with pytest.raises(ValidationError):
        InspectionBudget(max_files=-1)


def test_manifest_and_capabilities_contracts():
    manifest = CaseManifest(
        manifest_id="manifest_test",
        root_uri="/case",
        entries=[ManifestEntry(path="model.msh", format_hint="gmsh-msh")],
    )
    capability = AdapterCapabilities(plugin_id="demo", plugin_version="1.0", formats=["gmsh-msh"])
    assert manifest.contract_version.startswith("2.0")
    assert capability.read_only is True
