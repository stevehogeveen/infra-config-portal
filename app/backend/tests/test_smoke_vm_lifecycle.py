from __future__ import annotations

from fastapi.testclient import TestClient


def _audit_events_for_request(client: TestClient, request_id: str) -> list[dict]:
    response = client.get("/api/v1/audit-events")
    assert response.status_code == 200
    return [
        event
        for event in response.json()
        if event["request_id"] == request_id
    ]


def _audit_event_types(client: TestClient, request_id: str) -> set[str]:
    return {
        event["event_type"]
        for event in _audit_events_for_request(client, request_id)
    }


def test_mock_vm_lifecycle_smoke_happy_path_and_blocked_transitions(
    client: TestClient,
    vm_payload: dict,
) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["provider_mode"] == "mock"

    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    patched = client.patch(
        f"/api/v1/requests/{request_id}",
        json={
            "cpu": vm_payload["cpu"] + 1,
            "notes": "Smoke test draft edit.",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "draft"
    assert patched.json()["notes"] == "Smoke test draft edit."
    assert patched.json()["vm_deploy"]["cpu"] == vm_payload["cpu"] + 1

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "needs_approval"

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Approved for mock smoke test"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    execute_before_plan = client.post(f"/api/v1/requests/{request_id}/execute")
    assert execute_before_plan.status_code == 409
    assert "expected planned" in execute_before_plan.json()["detail"]

    still_approved = client.get(f"/api/v1/requests/{request_id}")
    assert still_approved.status_code == 200
    assert still_approved.json()["status"] == "approved"

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]
    assert planned.json()["status"] == "planned"
    assert planned.json()["provider"] == "vsphere.mock"
    assert planned.json()["plan_json"]["dry_run"] is True
    assert planned.json()["plan_json"]["request_id"] == request_id
    assert planned.json()["plan_json"]["request_intent_hash"].startswith("sha256:")

    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 200
    assert executed.json()["id"] == workflow_run_id
    assert executed.json()["status"] == "completed"
    assert executed.json()["result_json"]["mock"] is True
    assert executed.json()["result_json"]["provider"] == "vsphere.mock"

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "completed"

    run_detail = client.get(f"/api/v1/workflow-runs/{workflow_run_id}")
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "completed"

    cancel_completed = client.post(f"/api/v1/requests/{request_id}/cancel")
    assert cancel_completed.status_code == 409
    assert "completed" in cancel_completed.json()["detail"]

    assert {
        "request.created",
        "request.updated",
        "request.submitted",
        "request.validation_started",
        "request.validation_passed",
        "request.approved",
        "request.execution_preflight_failed",
        "request.planned",
        "request.execution_started",
        "request.completed",
    }.issubset(_audit_event_types(client, request_id))


def test_mock_vm_lifecycle_smoke_stale_plan_edit_blocks_execution(
    client: TestClient,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "needs_approval"

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Approved for stale-plan smoke test"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]
    assert planned.json()["status"] == "planned"

    edited = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"memory_gb": vm_payload["memory_gb"] + 4},
    )
    assert edited.status_code == 200
    assert edited.json()["status"] == "draft"
    assert edited.json()["vm_deploy"]["memory_gb"] == vm_payload["memory_gb"] + 4

    invalidated_run = client.get(f"/api/v1/workflow-runs/{workflow_run_id}")
    assert invalidated_run.status_code == 200
    assert invalidated_run.json()["status"] == "cancelled"
    assert invalidated_run.json()["plan_json"]["invalidated_by_request_edit"] is True

    stale_execute = client.post(f"/api/v1/requests/{request_id}/execute")
    assert stale_execute.status_code == 409
    assert "expected planned" in stale_execute.json()["detail"]

    update_events = [
        event
        for event in _audit_events_for_request(client, request_id)
        if event["event_type"] == "request.updated"
    ]
    assert len(update_events) == 1
    assert update_events[0]["from_status"] == "planned"
    assert update_events[0]["to_status"] == "draft"
    assert update_events[0]["data_json"]["changed_fields"] == ["vm.memory_gb"]
    assert update_events[0]["data_json"]["execution_affecting_fields"] == [
        "vm.memory_gb"
    ]
    assert update_events[0]["data_json"]["reset_to_draft"] is True
    assert update_events[0]["data_json"]["invalidated_workflow_run_ids"] == [
        workflow_run_id
    ]

    assert "request.completed" not in _audit_event_types(client, request_id)
