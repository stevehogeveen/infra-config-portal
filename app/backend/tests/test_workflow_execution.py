from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowRunStatus
from app.models import AuditEvent, Request, WorkflowRun
from app.schemas import ApprovalCreate, VMDeploymentCreate
from app.services.lifecycle import (
    ExecutionPreflightError,
    InvalidTransitionError,
    approve_request,
    cancel_request,
    create_vm_deployment_request,
    execute_request,
    plan_request,
    submit_request,
)


class SpyVsphereAdapter:
    def __init__(self) -> None:
        self.execute_calls = 0

    def execute_vm_deployment(self, request: Request, plan: dict) -> dict:
        self.execute_calls += 1
        return {
            "dry_run": False,
            "mock": True,
            "provider": "vsphere.mock",
            "request_id": request.id,
            "vm_name": request.vm_deploy.vm_name,
            "executed_steps": [
                {**step, "status": "completed"}
                for step in plan.get("steps", [])
            ],
        }


def _create_approved_request(
    db_session: Session,
    vm_payload: dict,
    *,
    vm_name: str = "app-dev-001",
) -> Request:
    payload = {**vm_payload, "vm_name": vm_name}
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(payload),
        actor="local-dev-user",
    )
    request = submit_request(db_session, request.id, actor="local-dev-user")
    return approve_request(
        db_session,
        request.id,
        ApprovalCreate(approver="change.manager", notes="Approved for preflight test"),
    )


def _create_planned_request(
    db_session: Session,
    vm_payload: dict,
    *,
    vm_name: str = "app-dev-001",
) -> tuple[Request, WorkflowRun]:
    request = _create_approved_request(db_session, vm_payload, vm_name=vm_name)
    run = plan_request(db_session, request.id, actor="local-dev-user")
    return request, run


def test_mock_vm_deploy_lifecycle_records_audit_events(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )
    assert request.status == RequestStatus.DRAFT.value

    request = submit_request(db_session, request.id, actor="local-dev-user")
    assert request.status == RequestStatus.NEEDS_APPROVAL.value

    request = approve_request(
        db_session,
        request.id,
        ApprovalCreate(approver="change.manager", notes="Approved for MVP test"),
    )
    assert request.status == RequestStatus.APPROVED.value

    run = plan_request(db_session, request.id, actor="local-dev-user")
    assert run.status == WorkflowRunStatus.PLANNED.value
    assert run.plan_json["dry_run"] is True
    assert run.plan_json["provider"] == "vsphere.mock"

    run = execute_request(db_session, request.id, actor="local-dev-user")
    assert run.status == WorkflowRunStatus.COMPLETED.value
    assert run.result_json is not None
    assert run.result_json["mock"] is True
    assert run.result_json["provider"] == "vsphere.mock"

    audit_events = list(
        db_session.execute(
            select(AuditEvent).where(AuditEvent.request_id == request.id)
        ).scalars()
    )
    event_types = {event.event_type for event in audit_events}
    assert {
        "request.created",
        "request.submitted",
        "request.validation_started",
        "request.validation_passed",
        "request.approved",
        "request.planned",
        "request.execution_started",
        "request.completed",
    }.issubset(event_types)


def test_execute_succeeds_when_persisted_plan_belongs_to_request(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request, run = _create_planned_request(db_session, vm_payload)
    vsphere = SpyVsphereAdapter()

    completed_run = execute_request(
        db_session,
        request.id,
        actor="local-dev-user",
        vsphere=vsphere,
    )

    assert vsphere.execute_calls == 1
    assert completed_run.id == run.id
    assert completed_run.status == WorkflowRunStatus.COMPLETED.value
    assert completed_run.plan_json["request_id"] == request.id
    assert completed_run.result_json is not None
    assert completed_run.result_json["request_id"] == request.id


def test_execute_fails_when_no_persisted_plan_exists_and_records_audit(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = _create_approved_request(db_session, vm_payload)
    request.status = RequestStatus.PLANNED.value
    db_session.commit()
    request_id = request.id
    vsphere = SpyVsphereAdapter()

    with pytest.raises(ExecutionPreflightError, match="no persisted dry-run plan exists"):
        execute_request(
            db_session,
            request_id,
            actor="local-dev-user",
            vsphere=vsphere,
        )

    persisted_request = db_session.get(Request, request_id)
    assert persisted_request is not None
    assert persisted_request.status == RequestStatus.PLANNED.value
    assert vsphere.execute_calls == 0

    audit_event = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.request_id == request_id,
            AuditEvent.event_type == "request.execution_preflight_failed",
        )
    ).scalar_one()
    assert audit_event.workflow_run_id is None
    assert audit_event.from_status == RequestStatus.PLANNED.value
    assert audit_event.to_status == RequestStatus.PLANNED.value
    assert audit_event.data_json == {"reason": "missing_workflow_run"}


def test_execute_fails_when_persisted_plan_belongs_to_another_request(
    db_session: Session,
    vm_payload: dict,
) -> None:
    other_request, _ = _create_planned_request(
        db_session,
        vm_payload,
        vm_name="app-dev-002",
    )
    request, run = _create_planned_request(
        db_session,
        vm_payload,
        vm_name="app-dev-003",
    )
    run.plan_json = {**run.plan_json, "request_id": other_request.id}
    db_session.commit()
    request_id = request.id
    run_id = run.id
    vsphere = SpyVsphereAdapter()

    with pytest.raises(ExecutionPreflightError, match="dry-run plan for request"):
        execute_request(
            db_session,
            request_id,
            actor="local-dev-user",
            vsphere=vsphere,
        )

    persisted_request = db_session.get(Request, request_id)
    persisted_run = db_session.get(WorkflowRun, run_id)
    assert persisted_request is not None
    assert persisted_run is not None
    assert persisted_request.status == RequestStatus.PLANNED.value
    assert persisted_run.status == WorkflowRunStatus.PLANNED.value
    assert vsphere.execute_calls == 0

    audit_event = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.request_id == request_id,
            AuditEvent.event_type == "request.execution_preflight_failed",
        )
    ).scalar_one()
    assert audit_event.workflow_run_id == run_id
    assert audit_event.from_status == RequestStatus.PLANNED.value
    assert audit_event.to_status == RequestStatus.PLANNED.value
    assert audit_event.data_json == {
        "reason": "plan_request_mismatch",
        "workflow_run_id": run_id,
        "plan_request_id": other_request.id,
        "expected_request_id": request_id,
    }


def test_cancel_planned_request_cancels_workflow_run_and_records_audit(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )
    request = submit_request(db_session, request.id, actor="local-dev-user")
    request = approve_request(
        db_session,
        request.id,
        ApprovalCreate(approver="change.manager", notes="Approved for cancellation test"),
    )
    run = plan_request(db_session, request.id, actor="local-dev-user")

    request = cancel_request(db_session, request.id, actor="local-dev-user")

    assert request.status == RequestStatus.CANCELLED.value

    cancelled_run = db_session.get(WorkflowRun, run.id)
    assert cancelled_run is not None
    assert cancelled_run.status == WorkflowRunStatus.CANCELLED.value

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "request.cancelled")
    ).scalar_one()
    assert audit_event.request_id == request.id
    assert audit_event.workflow_run_id == run.id
    assert audit_event.from_status == RequestStatus.PLANNED.value
    assert audit_event.to_status == RequestStatus.CANCELLED.value
    assert audit_event.data_json == {"workflow_run_id": run.id}


def test_completed_request_cannot_be_cancelled(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )
    request = submit_request(db_session, request.id, actor="local-dev-user")
    request = approve_request(
        db_session,
        request.id,
        ApprovalCreate(approver="change.manager", notes="Approved for terminal state test"),
    )
    plan_request(db_session, request.id, actor="local-dev-user")
    execute_request(db_session, request.id, actor="local-dev-user")

    with pytest.raises(InvalidTransitionError):
        cancel_request(db_session, request.id, actor="local-dev-user")
