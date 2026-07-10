import math
from pathlib import Path

import pytest

from caereflex.arrays import ArrayQueryError, ArrayService
from caereflex.artifacts import ArtifactStore
from caereflex.contracts import ArrayRef


def test_identical_payload_has_one_canonical_path_across_suffixes(tmp_path: Path):
    store = ArtifactStore(tmp_path / "state")
    first = store.put_bytes(b"same", suffix=".vtk")
    second = store.put_bytes(b"same", suffix=".msh")

    assert first.digest == second.digest
    assert first.relative_path == second.relative_path
    assert store.statistics()["artifact_count"] == 1


def test_component_names_must_match_final_axis(tmp_path: Path):
    arrays = ArrayService(tmp_path / "state")
    with pytest.raises(ArrayQueryError, match="component_names"):
        arrays.register_numeric(
            [1.0, 2.0, 3.0, 4.0],
            dtype="float64",
            shape=(2, 2),
            component_names=["x", "y", "z"],
        )


def test_registered_checksum_must_match_content_address(tmp_path: Path):
    arrays = ArrayService(tmp_path / "state")
    artifact = arrays.store.put_bytes(b"\x00" * 8, suffix=".crxarr")
    ref = ArrayRef(
        array_id="array_bad_checksum",
        uri=artifact.uri,
        format="caereflex.raw.v1",
        shape=(1,),
        dtype="float64",
        checksum="sha256:" + "0" * 64,
        permitted_operations=["describe"],
    )
    with pytest.raises(ArrayQueryError, match="checksum"):
        arrays.register_ref(ref)


def test_reductions_report_and_exclude_non_finite_values(tmp_path: Path):
    arrays = ArrayService(tmp_path / "state")
    ref = arrays.register_numeric(
        [1.0, math.nan, 3.0, math.inf],
        dtype="float64",
        shape=(4,),
    )
    summary = arrays.reduce(ref.array_id, "mean")

    assert summary["count"] == 4
    assert summary["finite_count"] == 2
    assert summary["non_finite_count"] == 2
    assert summary["value"] == 2.0
