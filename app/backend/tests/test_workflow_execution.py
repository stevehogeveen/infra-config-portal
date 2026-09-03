from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowRunStatus
from app.models import Approval, AuditEvent, Request, WorkflowRun
from app.schemas import ApprovalCreate, VMDeploymentCreate, VMDeploymentUpdate
from app.services.lifecycle import (
    ExecutionPreflightError,
    InvalidTransitionError,
    approve_request,
    cancel_request,
    create_vm_deployment_request,
    execute_request,
    get_request,
    plan_request,
    reject_request,
    submit_request,
    update_vm_deployment_request,
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


class BadPlanVsphereAdapter:
    def plan_vm_deployment(self, request: Request) -> dict:
        return {
            "dry_run": False,
            "mock_only": False,
            "provider": "vsphere.real",
            "workflow": "vm_deploy_from_template",
            "request_id": request.id,
            "review_before_execute": {"required": False},
            "steps": [],
            "stage_events": [],
            "admin_password": "should-never-persist",
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


def test_plan_stores_request_intent_and_hash(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request, run = _create_planned_request(db_session, vm_payload)

    intent = run.plan_json["request_intent"]
    assert run.plan_json["request_intent_hash"].startswith("sha256:")
    assert intent == {
        "version": 1,
        "request_type": "vm_deploy",
        "environment": vm_payload["environment"],
        "site": vm_payload["site"],
        "owner": vm_payload["owner"],
        "expiry_date": vm_payload["expiry_date"],
        "vm": {
            "cluster": vm_payload["cluster"],
            "vm_name": vm_payload["vm_name"],
            "template": vm_payload["template"],
            "cpu": vm_payload["cpu"],
            "memory_gb": vm_payload["memory_gb"],
            "disk_gb": vm_payload["disk_gb"],
            "network": vm_payload["network"],
            "datastore": None,
            "storage_tier": vm_payload["storage_tier"],
        },
    }
    assert run.plan_json["request_id"] == request.id


def test_plan_request_rejects_provider_plan_contract_failures(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = _create_approved_request(db_session, vm_payload)

    with pytest.raises(ExecutionPreflightError, match="Provider plan contract failed"):
        plan_request(
            db_session,
            request.id,
            actor="local-dev-user",
            vsphere=BadPlanVsphereAdapter(),
        )

    refreshed = get_request(db_session, request.id)
    assert refreshed.status == RequestStatus.APPROVED.value
    assert refreshed.workflow_runs == []


def test_draft_request_notes_can_be_edited(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )

    updated = update_vm_deployment_request(
        db_session,
        request.id,
        VMDeploymentUpdate(notes="Updated operator note."),
        actor="local-dev-user",
    )

    assert updated.status == RequestStatus.DRAFT.value
    assert updated.notes == "Updated operator note."

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "request.updated")
    ).scalar_one()
    assert audit_event.request_id == request.id
    assert audit_event.from_status == RequestStatus.DRAFT.value
    assert audit_event.to_status == RequestStatus.DRAFT.value
    assert audit_event.data_json["changed_fields"] == ["notes"]
    assert audit_event.data_json["execution_affecting_fields"] == []


def test_draft_execution_affecting_edit_remains_draft(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )

    updated = update_vm_deployment_request(
        db_session,
        request.id,
        VMDeploymentUpdate(cpu=4),
        actor="local-dev-user",
    )

    assert updated.status == RequestStatus.DRAFT.value
    assert updated.vm_deploy.cpu == 4

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "request.updated")
    ).scalar_one()
    assert audit_event.data_json["changed_fields"] == ["vm.cpu"]
    assert audit_event.data_json["execution_affecting_fields"] == ["vm.cpu"]
    assert audit_event.data_json["reset_to_draft"] is False


def test_notes_edit_on_planned_request_does_not_invalidate_plan(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request, run = _create_planned_request(db_session, vm_payload)
    request_id = request.id
    run_id = run.id
    plan_hash = run.plan_json["request_intent_hash"]

    updated = update_vm_deployment_request(
        db_session,
        request_id,
        VMDeploymentUpdate(notes="Notes changed through formal edit path."),
        actor="local-dev-user",
    )

    persisted_run = db_session.get(WorkflowRun, run_id)
    assert persisted_run is not None
    assert updated.status == RequestStatus.PLANNED.value
    assert updated.notes == "Notes changed through formal edit path."
    assert persisted_run.status == WorkflowRunStatus.PLANNED.value
    assert persisted_run.plan_json["request_intent_hash"] == plan_hash
    assert "invalidated_by_request_edit" not in persisted_run.plan_json

    vsphere = SpyVsphereAdapter()
    completed_run = execute_request(
        db_session,
        request_id,
        actor="local-dev-user",
        vsphere=vsphere,
    )
    assert completed_run.status == WorkflowRunStatus.COMPLETED.value
    assert vsphere.execute_calls == 1


@pytest.mark.parametrize(
    "target_status",
    [
        RequestStatus.NEEDS_APPROVAL,
        RequestStatus.APPROVED,
        RequestStatus.PLANNED,
    ],
)
def test_execution_affecting_edit_resets_pre_execution_request_to_draft(
    db_session: Session,
    vm_payload: dict,
    target_status: RequestStatus,
) -> None:
    if target_status == RequestStatus.NEEDS_APPROVAL:
        request = create_vm_deployment_request(
            db_session,
            VMDeploymentCreate.model_validate(vm_payload),
            actor="local-dev-user",
        )
        request = submit_request(db_session, request.id, actor="local-dev-user")
        run_id = None
    elif target_status == RequestStatus.APPROVED:
        request = _create_approved_request(db_session, vm_payload)
        run_id = None
    else:
        request, run = _create_planned_request(db_session, vm_payload)
        run_id = run.id

    updated = update_vm_deployment_request(
        db_session,
        request.id,
        VMDeploymentUpdate(cpu=vm_payload["cpu"] + 1),
        actor="local-dev-user",
    )

    assert updated.status == RequestStatus.DRAFT.value
    assert updated.vm_deploy.cpu == vm_payload["cpu"] + 1

    audit_event = db_session.execute(
        select(AuditEvent)
        .where(
            AuditEvent.request_id == request.id,
            AuditEvent.event_type == "request.updated",
        )
        .order_by(AuditEvent.created_at.desc())
    ).scalar_one()
    assert audit_event.from_status == target_status.value
    assert audit_event.to_status == RequestStatus.DRAFT.value
    assert audit_event.data_json["changed_fields"] == ["vm.cpu"]
    assert audit_event.data_json["execution_affecting_fields"] == ["vm.cpu"]
    assert audit_event.data_json["reset_to_draft"] is True

    if run_id is not None:
        persisted_run = db_session.get(WorkflowRun, run_id)
        assert persisted_run is not None
        assert persisted_run.status == WorkflowRunStatus.CANCELLED.value
        assert persisted_run.plan_json["invalidated_by_request_edit"] is True
        assert audit_event.data_json["invalidated_workflow_run_ids"] == [run_id]


def test_planned_execution_affecting_edit_leaves_no_executable_stale_plan(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request, run = _create_planned_request(db_session, vm_payload)
    request_id = request.id
    run_id = run.id

    update_vm_deployment_request(
        db_session,
        request_id,
        VMDeploymentUpdate(memory_gb=vm_payload["memory_gb"] + 4),
        actor="local-dev-user",
    )

    persisted_run = db_session.get(WorkflowRun, run_id)
    assert persisted_run is not None
    assert persisted_run.status == WorkflowRunStatus.CANCELLED.value

    vsphere = SpyVsphereAdapter()
    with pytest.raises(InvalidTransitionError, match="expected planned"):
        execute_request(
            db_session,
            request_id,
            actor="local-dev-user",
            vsphere=vsphere,
        )
    assert vsphere.execute_calls == 0


def test_execution_affecting_edit_invalidates_existing_approval(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = _create_approved_request(db_session, vm_payload)
    approval = db_session.execute(
        select(Approval).where(Approval.request_id == request.id)
    ).scalar_one()
    assert approval.decision == "approved"

    updated = update_vm_deployment_request(
        db_session,
        request.id,
        VMDeploymentUpdate(template="ubuntu-24.04-template"),
        actor="local-dev-user",
    )

    persisted_approval = db_session.get(Approval, approval.id)
    assert persisted_approval is not None
    assert updated.status == RequestStatus.DRAFT.value
    assert persisted_approval.decision == "invalidated"

    audit_event = db_session.execute(
        select(AuditEvent).where(
            AuditEvent.request_id == request.id,
            AuditEvent.event_type == "request.updated",
        )
    ).scalar_one()
    assert audit_event.data_json["invalidated_approval_ids"] == [approval.id]


def test_reject_request_records_decision_and_locks_request(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )
    request = submit_request(db_session, request.id, actor="local-dev-user")

    rejected = reject_request(
        db_session,
        request.id,
        ApprovalCreate(approver="change.manager", notes="Rejected for lifecycle test"),
    )

    assert rejected.status == RequestStatus.REJECTED.value

    approval = db_session.execute(
        select(Approval).where(Approval.request_id == request.id)
    ).scalar_one()
    assert approval.decision == "rejected"
    assert approval.notes == "Rejected for lifecycle test"

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "request.rejected")
    ).scalar_one()
    assert audit_event.request_id == request.id
    assert audit_event.from_status == RequestStatus.NEEDS_APPROVAL.value
    assert audit_event.to_status == RequestStatus.REJECTED.value
    assert audit_event.data_json == {"approval_id": approval.id}

    with pytest.raises(InvalidTransitionError, match="locked"):
        update_vm_deployment_request(
            db_session,
            request.id,
            VMDeploymentUpdate(notes="Rejected requests are locked."),
            actor="local-dev-user",
        )


@pytest.mark.parametrize(
    "locked_status",
    [
        RequestStatus.EXECUTING.value,
        RequestStatus.COMPLETED.value,
        RequestStatus.FAILED.value,
        RequestStatus.CANCELLED.value,
        RequestStatus.REJECTED.value,
    ],
)
def test_locked_request_states_cannot_be_edited(
    db_session: Session,
    vm_payload: dict,
    locked_status: str,
) -> None:
    request = create_vm_deployment_request(
        db_session,
        VMDeploymentCreate.model_validate(vm_payload),
        actor="local-dev-user",
    )
    request.status = locked_status
    db_session.commit()

    with pytest.raises(InvalidTransitionError, match="locked"):
        update_vm_deployment_request(
            db_session,
            request.id,
            VMDeploymentUpdate(notes="Should not be accepted."),
            actor="local-dev-user",
        )

    persisted_request = db_session.get(Request, request.id)
    assert persisted_request is not None
    assert persisted_request.status == locked_status
    assert persisted_request.notes == vm_payload["notes"]


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


def test_execute_fails_when_request_intent_changes_after_planning(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request, run = _create_planned_request(db_session, vm_payload)
    request_id = request.id
    run_id = run.id

    persisted_request = db_session.get(Request, request_id)
    assert persisted_request is not None
    persisted_request.vm_deploy.cpu = vm_payload["cpu"] + 2
    db_session.commit()

    vsphere = SpyVsphereAdapter()
    with pytest.raises(ExecutionPreflightError, match="current intent no longer matches"):
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
    assert audit_event.data_json["reason"] == "request_intent_mismatch"
    assert audit_event.data_json["workflow_run_id"] == run_id
    assert audit_event.data_json["changed_fields"] == ["vm.cpu"]


def test_execute_ignores_notes_changed_after_planning(
    db_session: Session,
    vm_payload: dict,
) -> None:
    request, run = _create_planned_request(db_session, vm_payload)
    request_id = request.id
    vsphere = SpyVsphereAdapter()

    persisted_request = db_session.get(Request, request_id)
    assert persisted_request is not None
    persisted_request.notes = "Operator-only note changed after planning."
    db_session.commit()

    completed_run = execute_request(
        db_session,
        request_id,
        actor="local-dev-user",
        vsphere=vsphere,
    )

    assert vsphere.execute_calls == 1
    assert completed_run.id == run.id
    assert completed_run.status == WorkflowRunStatus.COMPLETED.value


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
