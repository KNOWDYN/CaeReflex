import sqlite3
import time

import pytest

from caereflex.lifecycle import (
    ASYNC_JOB_PROTOCOL_VERSION,
    HUMAN_REVIEW_PROTOCOL_VERSION,
    LIFECYCLE_PROTOCOL_VERSION,
    TEMPORAL_COMPARISON_PROTOCOL_VERSION,
    AsyncJobService,
    ImmutableRecordError,
    InvalidTransitionError,
    LifecycleStore,
    ReviewDecision,
    ReviewTargetType,
    compare_revisions,
)


def _case(case_id: str, value: int, created_at: str = "2026-01-01T00:00:00+00:00"):
    return {
        "schema_version": "1.0",
        "case_id": case_id,
        "created_at": created_at,
        "updated_at": created_at,
        "metadata": {"value": value},
        "items": [1, 2],
    }


def test_gate8_protocols_are_explicitly_versioned():
    assert LIFECYCLE_PROTOCOL_VERSION == "caereflex.lifecycle/1.0"
    assert TEMPORAL_COMPARISON_PROTOCOL_VERSION == "caereflex.temporal-comparison/1.0"
    assert HUMAN_REVIEW_PROTOCOL_VERSION == "caereflex.human-review/1.0"
    assert ASYNC_JOB_PROTOCOL_VERSION == "caereflex.async-job/1.0"


def test_project_revision_run_review_and_comparison_lifecycle(tmp_path):
    store = LifecycleStore(tmp_path / ".caereflex")
    project = store.create_project("Pump study")
    revision_a = store.create_revision(project.project_id, _case("case_a", 1))
    revision_b = store.create_revision(
        project.project_id,
        _case("case_b", 2, "2026-02-01T00:00:00+00:00"),
    )
    assert revision_b.sequence == 2
    assert revision_b.parent_revision_id == revision_a.revision_id

    comparison = compare_revisions(
        store,
        project.project_id,
        revision_a.revision_id,
        revision_b.revision_id,
    )
    assert comparison.counts["changed"] >= 2
    assert all(item.path not in {"/created_at", "/updated_at"} for item in comparison.changes)

    first_review = store.add_review(
        project.project_id,
        ReviewTargetType.comparison,
        comparison.comparison_id,
        reviewer_id="reviewer-1",
        decision=ReviewDecision.changes_requested,
        statement="Explain the changed evidence.",
    )
    second_review = store.add_review(
        project.project_id,
        "comparison",
        comparison.comparison_id,
        reviewer_id="reviewer-1",
        decision="approved",
        statement="The revision now resolves the concern.",
        supersedes_review_id=first_review.review_id,
    )
    assert second_review.previous_review_digest == first_review.record_digest
    assert store.get_review(first_review.review_id).record_digest == first_review.record_digest

    run = store.create_run(
        project.project_id,
        "inspection",
        input_revision_id=revision_b.revision_id,
    )
    store.transition_run(run.run_id, "running")
    completed = store.transition_run(
        run.run_id,
        "success",
        result_revision_id=revision_b.revision_id,
    )
    assert completed.status == "success"
    assert [event.status for event in store.list_run_events(run.run_id)] == [
        "queued",
        "running",
        "success",
    ]
    with pytest.raises(InvalidTransitionError):
        store.transition_run(run.run_id, "failed")


def test_revision_snapshot_and_review_tables_are_immutable(tmp_path):
    store = LifecycleStore(tmp_path / ".caereflex")
    project = store.create_project("Immutable study")
    revision = store.create_revision(project.project_id, _case("case_x", 1))
    snapshot = store.state_root / revision.snapshot_path
    snapshot.write_text("{}", encoding="utf-8")
    with pytest.raises(ImmutableRecordError):
        store.load_revision_payload(revision.revision_id)

    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(
                "UPDATE revisions SET record_json = ? WHERE revision_id = ?",
                ("{}", revision.revision_id),
            )


def test_temporal_comparison_is_deterministic_and_bounded(tmp_path):
    store = LifecycleStore(tmp_path / ".caereflex")
    project = store.create_project("Bounded comparison")
    baseline = {"case_id": "case_a", "values": {str(index): index for index in range(20)}}
    candidate = {"case_id": "case_b", "values": {str(index): index + 1 for index in range(20)}}
    revision_a = store.create_revision(project.project_id, baseline)
    revision_b = store.create_revision(project.project_id, candidate)
    first = compare_revisions(
        store,
        project.project_id,
        revision_a.revision_id,
        revision_b.revision_id,
        max_changes=5,
        persist=False,
    )
    second = compare_revisions(
        store,
        project.project_id,
        revision_a.revision_id,
        revision_b.revision_id,
        max_changes=5,
        persist=False,
    )
    assert first.counts == second.counts
    assert [item.path for item in first.changes] == [item.path for item in second.changes]
    assert first.truncated is True
    assert len(first.changes) == 5


def test_project_archive_rejects_active_runs(tmp_path):
    store = LifecycleStore(tmp_path / ".caereflex")
    project = store.create_project("Archive guard")
    run = store.create_run(project.project_id, "inspection")
    with pytest.raises(InvalidTransitionError):
        store.archive_project(project.project_id)
    store.transition_run(run.run_id, "cancelled")
    assert store.archive_project(project.project_id).status == "archived"


def test_asynchronous_comparison_persists_job_run_and_result(tmp_path):
    store = LifecycleStore(tmp_path / ".caereflex")
    project = store.create_project("Async comparison")
    revision_a = store.create_revision(project.project_id, _case("case_a", 1))
    revision_b = store.create_revision(project.project_id, _case("case_b", 2))
    service = AsyncJobService(
        tmp_path,
        lifecycle_store=store,
        max_workers=1,
        max_queue=1,
    )
    try:
        submitted = service.submit_comparison(
            project.project_id,
            revision_a.revision_id,
            revision_b.revision_id,
        )
        deadline = time.monotonic() + 5.0
        current = service.get(submitted.job_id)
        while current.status in {"pending", "running"} and time.monotonic() < deadline:
            time.sleep(0.02)
            current = service.get(submitted.job_id)
        assert current.status == "success"
        assert current.result_summary["comparison_id"].startswith("comparison_")
        run = store.get_run(current.request_summary["run_id"])
        assert run.status == "success"
    finally:
        service.shutdown(wait=True)


def test_bounded_rest_routes_and_openapi(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from caereflex.server.app import create_app

    app = create_app(
        tmp_path,
        max_workers=1,
        max_queue=0,
        max_request_body_bytes=2048,
    )
    with TestClient(app) as client:
        project_response = client.post("/projects", json={"name": "REST project"})
        assert project_response.status_code == 201
        project_id = project_response.json()["project_id"]
        assert client.get("/projects?limit=101").status_code == 422
        assert client.post(
            "/jobs/inspect",
            json={"project_id": project_id, "path": "../outside"},
        ).status_code == 400
        oversized = b'{"name":"' + (b"a" * 3000) + b'"}'
        assert client.post(
            "/projects",
            content=oversized,
            headers={"content-type": "application/json"},
        ).status_code == 413
        protocols = client.get("/lifecycle/version").json()
        assert protocols["lifecycle"] == LIFECYCLE_PROTOCOL_VERSION
        paths = app.openapi()["paths"]
        assert "/reviews" in paths
        assert "/jobs/compare" in paths
        assert "/projects/{project_id}/revisions" in paths
