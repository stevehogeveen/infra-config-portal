from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowRunStatus
from app.models import Request, WorkflowRun


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_vm_deploy_api_flow(client: TestClient, vm_payload: dict) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "needs_approval"

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]
    assert planned.json()["status"] == "planned"
    assert planned.json()["plan_json"]["dry_run"] is True
    assert planned.json()["plan_json"]["mock_only"] is True
    assert planned.json()["plan_json"]["review_before_execute"]["required"] is True
    assert [
        event["stage"]
        for event in planned.json()["plan_json"]["stage_events"]
    ] == [
        "DISCOVER",
        "VALIDATE",
        "PLAN",
        "REVIEW",
        "EXECUTE",
        "COMPLETE",
        "BLOCKED",
    ]

    workflow_runs = client.get("/api/v1/workflow-runs")
    assert workflow_runs.status_code == 200
    assert workflow_runs.json()[0]["id"] == workflow_run_id

    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
    assert executed.json()["result_json"]["mock"] is True
    assert executed.json()["result_json"]["stage_events"][0]["stage"] == "DISCOVER"
    assert executed.json()["result_json"]["stage_events"][0]["status"] == "completed"

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "completed"

    run_detail = client.get(f"/api/v1/workflow-runs/{workflow_run_id}")
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "completed"

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.completed" in event_types


def test_cancel_draft_request_api_flow(client: TestClient, vm_payload: dict) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    cancelled = client.post(f"/api/v1/requests/{request_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 409

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.cancelled" in event_types


def test_update_request_api_allows_draft_patch_and_records_audit(
    client: TestClient,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"notes": "Updated through PATCH", "cpu": 4},
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["notes"] == "Updated through PATCH"
    assert updated.json()["vm_deploy"]["cpu"] == 4

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    matching_events = [
        event
        for event in audit_events.json()
        if event["event_type"] == "request.updated"
    ]
    assert matching_events[0]["data_json"]["changed_fields"] == ["notes", "vm.cpu"]
    assert matching_events[0]["data_json"]["reset_to_draft"] is False


def test_update_request_api_resets_planned_execution_edit_and_cancels_plan(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]

    updated = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"memory_gb": vm_payload["memory_gb"] + 4},
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["vm_deploy"]["memory_gb"] == vm_payload["memory_gb"] + 4

    workflow_run = db_session.get(WorkflowRun, workflow_run_id)
    assert workflow_run is not None
    assert workflow_run.status == WorkflowRunStatus.CANCELLED.value
    assert workflow_run.plan_json["invalidated_by_request_edit"] is True

    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 409
    assert "expected planned" in executed.json()["detail"]

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    matching_events = [
        event
        for event in audit_events.json()
        if event["event_type"] == "request.updated"
    ]
    assert matching_events[0]["data_json"]["reset_to_draft"] is True
    assert matching_events[0]["data_json"]["invalidated_workflow_run_ids"] == [
        workflow_run_id
    ]


def test_update_request_api_rejects_locked_request(
    client: TestClient,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    cancelled = client.post(f"/api/v1/requests/{request_id}/cancel")
    assert cancelled.status_code == 200

    updated = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"notes": "Rejected because cancelled is locked."},
    )

    assert updated.status_code == 409
    assert "locked" in updated.json()["detail"]

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "cancelled"
    assert request_detail.json()["notes"] == vm_payload["notes"]


def test_execute_api_rejects_planned_request_without_persisted_plan(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200

    request = db_session.get(Request, request_id)
    assert request is not None
    request.status = RequestStatus.PLANNED.value
    db_session.commit()

    executed = client.post(f"/api/v1/requests/{request_id}/execute")

    assert executed.status_code == 409
    assert "no persisted dry-run plan exists" in executed.json()["detail"]

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "planned"

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.execution_preflight_failed" in event_types


def test_execute_api_rejects_request_intent_drift(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    assert planned.json()["plan_json"]["request_intent_hash"].startswith("sha256:")

    request = db_session.get(Request, request_id)
    assert request is not None
    request.vm_deploy.memory_gb = vm_payload["memory_gb"] + 4
    db_session.commit()

    executed = client.post(f"/api/v1/requests/{request_id}/execute")

    assert executed.status_code == 409
    assert "current intent no longer matches" in executed.json()["detail"]

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "planned"

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    matching_events = [
        event
        for event in audit_events.json()
        if event["event_type"] == "request.execution_preflight_failed"
    ]
    assert matching_events[0]["data_json"]["reason"] == "request_intent_mismatch"
    assert matching_events[0]["data_json"]["changed_fields"] == ["vm.memory_gb"]


def test_provider_status_reports_mock_and_preview_providers(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    statuses = response.json()
    ids = {item["id"] for item in statuses}
    assert {"mock-vsphere", "ilo-redfish", "cisco-console"}.issubset(ids)
    assert any(item["name"] == "Mock vSphere" and item["mode"] == "mock" for item in statuses)
    assert all(item["mode"] == "mock" for item in statuses)
    assert all("safe_actions" in item and "disabled_actions" in item for item in statuses)
