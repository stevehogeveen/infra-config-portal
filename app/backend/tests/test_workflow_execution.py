from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowRunStatus
from app.models import AuditEvent, WorkflowRun
from app.schemas import ApprovalCreate, VMDeploymentCreate
from app.services.lifecycle import (
    InvalidTransitionError,
    approve_request,
    cancel_request,
    create_vm_deployment_request,
    execute_request,
    plan_request,
    submit_request,
)


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
