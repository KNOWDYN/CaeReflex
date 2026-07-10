from pathlib import Path

import pytest

from caereflex.arrays import ArrayQueryError, ArrayService
from caereflex.artifacts import ArtifactStore, ArtifactStoreError
from caereflex.contracts import ArrayRef


def test_artifact_store_is_content_addressed_and_deduplicated(tmp_path: Path):
    store = ArtifactStore(tmp_path / "state")
    first = store.put_bytes(b"engineering-evidence", suffix=".bin")
    second = store.put_bytes(b"engineering-evidence", suffix=".bin")

    assert first.digest == second.digest
    assert first.artifact_id == second.artifact_id
    path = store.resolve(first.uri)
    assert path.read_bytes() == b"engineering-evidence"
    assert store.statistics()["artifact_count"] == 1


def test_artifact_integrity_failure_is_detected(tmp_path: Path):
    store = ArtifactStore(tmp_path / "state")
    record = store.put_bytes(b"trusted", suffix=".bin")
    path = store.resolve(record.uri)
    path.chmod(0o644)
    path.write_bytes(b"changed")
    with pytest.raises(ArtifactStoreError):
        store.resolve(record.uri)


def test_arrayref_v1_payload_remains_valid():
    ref = ArrayRef(uri="caereflex-artifact://sha256/" + "0" * 64, format="legacy", shape=(3,), dtype="float64")
    assert ref.array_id is None
    assert ref.permitted_operations == []


def test_numeric_array_registration_and_queries(tmp_path: Path):
    arrays = ArrayService(tmp_path / "state", max_elements_returned=8)
    ref = arrays.register_numeric(
        [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
        dtype="float64",
        shape=(3, 2),
        source_asset_id="asset_mesh",
        association="point",
        component_names=["x", "y"],
        coordinate_frame_ref="frame_global",
    )

    assert ref.array_id
    assert arrays.describe(ref.array_id)["element_count"] == 6
    assert arrays.slice(ref.array_id, 1, 5)["values"] == [1.0, 2.0, 3.0, 4.0]
    assert arrays.sample(ref.array_id, 3)["indices"] == [0, 2, 5]
    assert arrays.reduce(ref.array_id, "min")["value"] == 0.0
    assert arrays.reduce(ref.array_id, "max")["value"] == 5.0
    assert arrays.reduce(ref.array_id, "mean")["value"] == 2.5
    assert arrays.reduce(ref.array_id, "mean", component=1)["value"] == 3.0


def test_array_queries_enforce_declared_operations_and_output_limits(tmp_path: Path):
    arrays = ArrayService(tmp_path / "state", max_elements_returned=2)
    ref = arrays.register_numeric([1, 2, 3, 4], dtype="int32", shape=(4,))

    with pytest.raises(ArrayQueryError):
        arrays.slice(ref.array_id, 0, 4)
    with pytest.raises(ArrayQueryError):
        arrays.reduce(ref.array_id, "median")


def test_array_shape_and_dtype_are_validated(tmp_path: Path):
    arrays = ArrayService(tmp_path / "state")
    with pytest.raises(ArrayQueryError):
        arrays.register_numeric([1, 2], dtype="int32", shape=(3,))
    with pytest.raises(ArrayQueryError):
        arrays.register_numeric([1, 2], dtype="complex128", shape=(2,))
