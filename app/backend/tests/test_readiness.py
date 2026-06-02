from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus
from app.models import Request


READINESS_KEYS = {
    "request_id",
    "current_status",
    "ready_for_submit",
    "ready_for_approval",
    "ready_for_plan",
    "ready_for_execute",
    "next_action",
    "blockers",
    "warnings",
    "summary",
}
ISSUE_KEYS = {"code", "message", "severity", "action"}


def _create_request(client: TestClient, vm_payload: dict) -> str:
    response = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert response.status_code == 201
    return str(response.json()["id"])


def _submit_request(client: TestClient, request_id: str) -> None:
    response = client.post(f"/api/v1/requests/{request_id}/submit")
    assert response.status_code == 200
    assert response.json()["status"] == "needs_approval"


def _approve_request(client: TestClient, request_id: str) -> None:
    response = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Approved for readiness test"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def _plan_request(client: TestClient, request_id: str) -> str:
    response = client.post(f"/api/v1/requests/{request_id}/plan")
    assert response.status_code == 200
    assert response.json()["status"] == "planned"
    return str(response.json()["id"])


def _readiness(client: TestClient, request_id: str) -> dict:
    response = client.get(f"/api/v1/requests/{request_id}/readiness")
    assert response.status_code == 200
    payload = response.json()
    _assert_readiness_shape(payload)
    return payload


def _assert_readiness_shape(payload: dict) -> None:
    assert set(payload) == READINESS_KEYS
    assert isinstance(payload["blockers"], list)
    assert isinstance(payload["warnings"], list)
    for issue in [*payload["blockers"], *payload["warnings"]]:
        assert set(issue) == ISSUE_KEYS
        assert all(isinstance(issue[field], str) for field in ISSUE_KEYS)


def _audit_events_for_request(client: TestClient, request_id: str) -> list[dict]:
    response = client.get("/api/v1/audit-events")
    assert response.status_code == 200
    return [
        event
        for event in response.json()
        if event["request_id"] == request_id
    ]


def _assert_all_ready_flags_false(payload: dict) -> None:
    assert payload["ready_for_submit"] is False
    assert payload["ready_for_approval"] is False
    assert payload["ready_for_plan"] is False
    assert payload["ready_for_execute"] is False


def test_draft_request_readiness(client: TestClient, vm_payload: dict) -> None:
    request_id = _create_request(client, vm_payload)

    payload = _readiness(client, request_id)

    assert payload["request_id"] == request_id
    assert payload["current_status"] == "draft"
    assert payload["ready_for_submit"] is True
    assert payload["ready_for_approval"] is False
    assert payload["ready_for_plan"] is False
    assert payload["ready_for_execute"] is False
    assert payload["next_action"] == "submit"
    assert payload["blockers"] == []
    assert payload["warnings"] == []


def test_needs_approval_request_readiness(client: TestClient, vm_payload: dict) -> None:
    request_id = _create_request(client, vm_payload)
    _submit_request(client, request_id)

    payload = _readiness(client, request_id)

    assert payload["current_status"] == "needs_approval"
    assert payload["ready_for_approval"] is True
    assert payload["next_action"] == "approve_or_reject"
    assert payload["blockers"] == []


def test_approved_request_readiness(client: TestClient, vm_payload: dict) -> None:
    request_id = _create_request(client, vm_payload)
    _submit_request(client, request_id)
    _approve_request(client, request_id)

    payload = _readiness(client, request_id)

    assert payload["current_status"] == "approved"
    assert payload["ready_for_plan"] is True
    assert payload["next_action"] == "plan"
    assert payload["blockers"] == []


def test_planned_request_with_valid_plan_readiness(
    client: TestClient,
    vm_payload: dict,
) -> None:
    request_id = _create_request(client, vm_payload)
    _submit_request(client, request_id)
    _approve_request(client, request_id)
    _plan_request(client, request_id)

    payload = _readiness(client, request_id)

    assert payload["current_status"] == "planned"
    assert payload["ready_for_execute"] is True
    assert payload["next_action"] == "execute"
    assert payload["blockers"] == []


def test_planned_request_with_missing_plan_readiness(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    request_id = _create_request(client, vm_payload)
    request = db_session.get(Request, request_id)
    assert request is not None
    request.status = RequestStatus.PLANNED.value
    db_session.commit()

    payload = _readiness(client, request_id)

    _assert_all_ready_flags_false(payload)
    assert payload["current_status"] == "planned"
    assert payload["next_action"] == "replan"
    assert payload["blockers"][0]["code"] == "plan_missing"
    assert "no persisted dry-run plan exists" in payload["blockers"][0]["message"]


def test_planned_request_with_intent_drift_readiness_is_read_only(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    request_id = _create_request(client, vm_payload)
    _submit_request(client, request_id)
    _approve_request(client, request_id)
    _plan_request(client, request_id)

    request = db_session.get(Request, request_id)
    assert request is not None
    request.vm_deploy.memory_gb = vm_payload["memory_gb"] + 4
    db_session.commit()
    audit_events_before = _audit_events_for_request(client, request_id)

    payload = _readiness(client, request_id)

    _assert_all_ready_flags_false(payload)
    assert payload["current_status"] == "planned"
    assert payload["next_action"] == "edit_resubmit"
    assert payload["blockers"][0]["code"] == "request_plan_intent_drift"
    assert "current intent no longer matches" in payload["blockers"][0]["message"]
    assert _audit_events_for_request(client, request_id) == audit_events_before


def test_completed_request_readiness(client: TestClient, vm_payload: dict) -> None:
    request_id = _create_request(client, vm_payload)
    _submit_request(client, request_id)
    _approve_request(client, request_id)
    _plan_request(client, request_id)

    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"

    payload = _readiness(client, request_id)

    _assert_all_ready_flags_false(payload)
    assert payload["current_status"] == "completed"
    assert payload["next_action"] == "none"
    assert payload["blockers"][0]["code"] == "already_completed"
    assert "complete" in payload["summary"].lower()


@pytest.mark.parametrize(
    ("status_value", "blocker_code"),
    [
        (RequestStatus.CANCELLED.value, "cancelled_request"),
        (RequestStatus.REJECTED.value, "rejected_request"),
        (RequestStatus.FAILED.value, "failed_request"),
    ],
)
def test_terminal_request_readiness(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
    status_value: str,
    blocker_code: str,
) -> None:
    request_id = _create_request(client, vm_payload)
    request = db_session.get(Request, request_id)
    assert request is not None
    request.status = status_value
    db_session.commit()

    payload = _readiness(client, request_id)

    _assert_all_ready_flags_false(payload)
    assert payload["current_status"] == status_value
    assert payload["next_action"] == "none"
    assert payload["blockers"][0]["code"] == blocker_code


def test_readiness_api_response_shape_includes_structured_issues(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    request_id = _create_request(client, vm_payload)
    request = db_session.get(Request, request_id)
    assert request is not None
    request.status = RequestStatus.PLANNED.value
    db_session.commit()

    payload = _readiness(client, request_id)

    assert set(payload) == READINESS_KEYS
    assert payload["blockers"]
    assert set(payload["blockers"][0]) == ISSUE_KEYS
    assert payload["warnings"] == []
