from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import ApprovalDecision, RequestStatus, WorkflowRunStatus
from app.models import Approval, Request, VMDeploymentRequest, Workflow, WorkflowRun
from app.providers.base import SourceOfTruthAdapter, VsphereAdapter, validate_vm_deployment_plan_contract
from app.providers.registry import provider_registry
from app.schemas import ApprovalCreate, VMDeploymentCreate, VMDeploymentUpdate
from app.services.audit import record_audit_event
from app.services.worker import InlineWorker

WORKFLOW_SLUG = "vm_deploy_from_template"
CANCELLABLE_REQUEST_STATUSES = {
    RequestStatus.DRAFT.value,
    RequestStatus.SUBMITTED.value,
    RequestStatus.VALIDATING.value,
    RequestStatus.NEEDS_APPROVAL.value,
    RequestStatus.APPROVED.value,
    RequestStatus.PLANNED.value,
}
EDITABLE_REQUEST_STATUSES = CANCELLABLE_REQUEST_STATUSES
LOCKED_REQUEST_STATUSES = {
    RequestStatus.EXECUTING.value,
    RequestStatus.COMPLETED.value,
    RequestStatus.FAILED.value,
    RequestStatus.CANCELLED.value,
    RequestStatus.REJECTED.value,
}
REQUEST_UPDATE_FIELDS = {
    "requester",
    "environment",
    "site",
    "owner",
    "expiry_date",
    "notes",
}
VM_DEPLOYMENT_UPDATE_FIELDS = {
    "cluster",
    "vm_name",
    "template",
    "cpu",
    "memory_gb",
    "disk_gb",
    "network",
    "datastore",
    "storage_tier",
}
EXECUTION_AFFECTING_UPDATE_FIELDS = {
    "requester",
    "environment",
    "site",
    "owner",
    "expiry_date",
    *VM_DEPLOYMENT_UPDATE_FIELDS,
}
REQUEST_INTENT_VERSION = 1
REQUEST_INTENT_HASH_PREFIX = "sha256:"


@dataclass(frozen=True)
class ExecutionPlanProblem:
    code: str
    message: str
    data: dict
    workflow_run: WorkflowRun | None = None


class RequestNotFoundError(Exception):
    pass


class WorkflowRunNotFoundError(Exception):
    pass


class ExecutionPreflightError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class ValidationFailureError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Request failed source-of-truth validation")
        self.errors = errors


class RequestUpdateValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Request update failed validation")
        self.errors = errors


def request_query() -> Select:
    return select(Request).options(
        selectinload(Request.vm_deploy),
        selectinload(Request.workflow_runs),
    )


def get_request(session: Session, request_id: str) -> Request:
    request = session.execute(
        request_query().where(Request.id == request_id)
    ).scalar_one_or_none()
    if request is None:
        raise RequestNotFoundError(request_id)
    return request


def list_requests(session: Session) -> list[Request]:
    return list(
        session.execute(
            request_query().order_by(Request.created_at.desc())
        ).scalars()
    )


def create_vm_deployment_request(
    session: Session,
    payload: VMDeploymentCreate,
    *,
    actor: str,
) -> Request:
    request = Request(
        request_type="vm_deploy",
        status=RequestStatus.DRAFT.value,
        requester=payload.requester,
        owner=payload.owner,
        environment=payload.environment.value,
        site=payload.site,
        expiry_date=payload.expiry_date,
        notes=payload.notes,
    )
    request.vm_deploy = VMDeploymentRequest(
        cluster=payload.cluster,
        vm_name=payload.vm_name,
        template=payload.template,
        cpu=payload.cpu,
        memory_gb=payload.memory_gb,
        disk_gb=payload.disk_gb,
        network=payload.network,
        datastore=payload.datastore,
        storage_tier=payload.storage_tier,
    )
    session.add(request)
    session.flush()
    record_audit_event(
        session,
        actor=actor,
        event_type="request.created",
        message="VM deployment request created as draft.",
        request=request,
        to_status=RequestStatus.DRAFT.value,
    )
    session.commit()
    return get_request(session, request.id)


def update_vm_deployment_request(
    session: Session,
    request_id: str,
    payload: VMDeploymentUpdate,
    *,
    actor: str,
) -> Request:
    request = get_request(session, request_id)
    _ensure_editable_status(request)
    _ensure_vm_deployment_request(request)

    updates = payload.model_dump(exclude_unset=True)
    _validate_update_storage_target(request, updates)

    changed_fields = _apply_update_fields(request, updates)
    execution_affecting_changed_fields = [
        field for field in changed_fields if _is_execution_affecting_update_field(field)
    ]

    from_status = request.status
    invalidated_runs: list[WorkflowRun] = []
    invalidated_approval_ids: list[str] = []
    reset_to_draft = bool(
        execution_affecting_changed_fields
        and request.status != RequestStatus.DRAFT.value
    )
    if reset_to_draft:
        invalidated_runs = _cancel_planned_workflow_runs_for_request(session, request.id)
        invalidated_approval_ids = _invalidate_approvals_for_request(session, request.id)
        request.status = RequestStatus.DRAFT.value

    message = _update_audit_message(
        changed_fields=changed_fields,
        reset_to_draft=reset_to_draft,
    )
    record_audit_event(
        session,
        actor=actor,
        event_type="request.updated",
        message=message,
        request=request,
        from_status=from_status,
        to_status=request.status,
        data={
            "changed_fields": changed_fields,
            "execution_affecting_fields": execution_affecting_changed_fields,
            "reset_to_draft": reset_to_draft,
            "invalidated_approval_ids": invalidated_approval_ids,
            "invalidated_workflow_run_ids": [run.id for run in invalidated_runs],
        },
    )
    session.flush()
    session.commit()
    return get_request(session, request.id)


def submit_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
    source_of_truth: SourceOfTruthAdapter | None = None,
) -> Request:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.DRAFT)
    source_of_truth = source_of_truth or provider_registry().source_of_truth()

    _transition(
        session,
        request,
        RequestStatus.SUBMITTED,
        actor=actor,
        event_type="request.submitted",
        message="Request submitted.",
    )
    _transition(
        session,
        request,
        RequestStatus.VALIDATING,
        actor=actor,
        event_type="request.validation_started",
        message="Source-of-truth validation started.",
    )

    errors = source_of_truth.validate_vm_deployment(request)
    if errors:
        _transition(
            session,
            request,
            RequestStatus.FAILED,
            actor=actor,
            event_type="request.validation_failed",
            message="Request failed source-of-truth validation.",
            data={"errors": errors},
        )
        session.commit()
        raise ValidationFailureError(errors)

    _transition(
        session,
        request,
        RequestStatus.NEEDS_APPROVAL,
        actor=actor,
        event_type="request.validation_passed",
        message="Request validated and needs approval.",
    )
    session.commit()
    return get_request(session, request.id)


def approve_request(
    session: Session,
    request_id: str,
    payload: ApprovalCreate,
) -> Request:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.NEEDS_APPROVAL)

    approval = Approval(
        request_id=request.id,
        approver=payload.approver,
        decision=ApprovalDecision.APPROVED.value,
        notes=payload.notes,
    )
    session.add(approval)
    session.flush()
    _transition(
        session,
        request,
        RequestStatus.APPROVED,
        actor=payload.approver,
        event_type="request.approved",
        message="Request approved.",
        data={"approval_id": approval.id},
    )
    session.commit()
    return get_request(session, request.id)


def reject_request(
    session: Session,
    request_id: str,
    payload: ApprovalCreate,
) -> Request:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.NEEDS_APPROVAL)

    approval = Approval(
        request_id=request.id,
        approver=payload.approver,
        decision=ApprovalDecision.REJECTED.value,
        notes=payload.notes,
    )
    session.add(approval)
    session.flush()
    _transition(
        session,
        request,
        RequestStatus.REJECTED,
        actor=payload.approver,
        event_type="request.rejected",
        message="Request rejected.",
        data={"approval_id": approval.id},
    )
    session.commit()
    return get_request(session, request.id)


def build_request_intent(request: Request) -> dict:
    vm = request.vm_deploy
    return {
        "version": REQUEST_INTENT_VERSION,
        "request_type": request.request_type,
        "environment": request.environment,
        "site": request.site,
        "owner": request.owner,
        "expiry_date": request.expiry_date.isoformat(),
        "vm": {
            "cluster": vm.cluster,
            "vm_name": vm.vm_name,
            "template": vm.template,
            "cpu": vm.cpu,
            "memory_gb": vm.memory_gb,
            "disk_gb": vm.disk_gb,
            "network": vm.network,
            "datastore": vm.datastore,
            "storage_tier": vm.storage_tier,
        },
    }


def build_request_intent_hash(intent: dict) -> str:
    normalized = json.dumps(
        intent,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return f"{REQUEST_INTENT_HASH_PREFIX}{hashlib.sha256(normalized.encode()).hexdigest()}"


def plan_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
    vsphere: VsphereAdapter | None = None,
) -> WorkflowRun:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.APPROVED)
    vsphere = vsphere or provider_registry().vsphere()

    workflow = _get_or_create_workflow(session)
    plan = vsphere.plan_vm_deployment(request)
    contract_errors = validate_vm_deployment_plan_contract(plan, request)
    if contract_errors:
        raise ExecutionPreflightError(
            "Provider plan contract failed: " + "; ".join(contract_errors)
        )
    request_intent = build_request_intent(request)
    plan = {
        **plan,
        "request_intent": request_intent,
        "request_intent_hash": build_request_intent_hash(request_intent),
    }
    run = WorkflowRun(
        request_id=request.id,
        workflow_id=workflow.id,
        workflow_slug=WORKFLOW_SLUG,
        status=WorkflowRunStatus.PLANNED.value,
        provider="vsphere.mock",
        plan_json=plan,
    )
    session.add(run)
    session.flush()
    _transition(
        session,
        request,
        RequestStatus.PLANNED,
        actor=actor,
        event_type="request.planned",
        message="Dry-run deployment plan created.",
        workflow_run=run,
        data={
            "workflow_run_id": run.id,
            "dry_run": True,
            "stage": "PLAN",
            "review_before_execute_required": True,
        },
    )
    session.commit()
    return get_workflow_run(session, run.id)


def execute_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
    vsphere: VsphereAdapter | None = None,
    worker: InlineWorker | None = None,
) -> WorkflowRun:
    request = get_request(session, request_id)
    run = _preflight_execution_plan(session, request, actor=actor)

    vsphere = vsphere or provider_registry().vsphere()
    worker = worker or InlineWorker()

    run.status = WorkflowRunStatus.EXECUTING.value
    _transition(
        session,
        request,
        RequestStatus.EXECUTING,
        actor=actor,
        event_type="request.execution_started",
        message="Mock workflow execution started.",
        workflow_run=run,
        data={"workflow_run_id": run.id, "stage": "EXECUTE"},
    )

    try:
        result = worker.run(vsphere.execute_vm_deployment, request, run.plan_json)
    except Exception as exc:
        run.status = WorkflowRunStatus.FAILED.value
        run.error_message = str(exc)
        _transition(
            session,
            request,
            RequestStatus.FAILED,
            actor=actor,
            event_type="request.execution_failed",
            message="Mock workflow execution failed.",
            workflow_run=run,
            data={"error": str(exc)},
        )
        session.commit()
        raise

    run.result_json = result
    run.status = WorkflowRunStatus.COMPLETED.value
    _transition(
        session,
        request,
        RequestStatus.COMPLETED,
        actor=actor,
        event_type="request.completed",
        message="Mock VM deployment completed.",
        workflow_run=run,
        data={"workflow_run_id": run.id, "mock": True, "stage": "COMPLETE"},
    )
    session.commit()
    return get_workflow_run(session, run.id)


def cancel_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
) -> Request:
    request = get_request(session, request_id)
    _ensure_cancellable_status(request)

    run = None
    if request.status == RequestStatus.PLANNED.value:
        latest_run = _latest_run_for_request(session, request.id)
        if latest_run is not None and latest_run.status == WorkflowRunStatus.PLANNED.value:
            run = latest_run
            run.status = WorkflowRunStatus.CANCELLED.value

    data = {"workflow_run_id": run.id} if run is not None else None
    _transition(
        session,
        request,
        RequestStatus.CANCELLED,
        actor=actor,
        event_type="request.cancelled",
        message="Request cancelled before execution.",
        workflow_run=run,
        data=data,
    )
    session.commit()
    return get_request(session, request.id)


def _ensure_vm_deployment_request(request: Request) -> None:
    if request.request_type != "vm_deploy" or request.vm_deploy is None:
        raise RequestUpdateValidationError(
            ["Only VM deployment requests can be updated through this endpoint"]
        )


def _validate_update_storage_target(request: Request, updates: dict) -> None:
    datastore = updates.get("datastore", request.vm_deploy.datastore)
    storage_tier = updates.get("storage_tier", request.vm_deploy.storage_tier)
    if not datastore and not storage_tier:
        raise RequestUpdateValidationError(["datastore or storage_tier is required"])


def _apply_update_fields(request: Request, updates: dict) -> list[str]:
    changed_fields: list[str] = []
    for field in sorted(REQUEST_UPDATE_FIELDS):
        if field not in updates:
            continue
        new_value = _normalize_update_value(field, updates[field])
        if getattr(request, field) != new_value:
            setattr(request, field, new_value)
            changed_fields.append(field)

    for field in sorted(VM_DEPLOYMENT_UPDATE_FIELDS):
        if field not in updates:
            continue
        new_value = _normalize_update_value(field, updates[field])
        if getattr(request.vm_deploy, field) != new_value:
            setattr(request.vm_deploy, field, new_value)
            changed_fields.append(f"vm.{field}")

    return changed_fields


def _normalize_update_value(field: str, value: object) -> object:
    if field == "environment" and value is not None:
        return getattr(value, "value", value)
    return value


def _is_execution_affecting_update_field(field: str) -> bool:
    if field.startswith("vm."):
        return field.removeprefix("vm.") in EXECUTION_AFFECTING_UPDATE_FIELDS
    return field in EXECUTION_AFFECTING_UPDATE_FIELDS


def _cancel_planned_workflow_runs_for_request(
    session: Session,
    request_id: str,
) -> list[WorkflowRun]:
    runs = list(
        session.execute(
            select(WorkflowRun).where(
                WorkflowRun.request_id == request_id,
                WorkflowRun.status == WorkflowRunStatus.PLANNED.value,
            )
        ).scalars()
    )
    for run in runs:
        run.status = WorkflowRunStatus.CANCELLED.value
        plan_json = run.plan_json if isinstance(run.plan_json, dict) else {}
        run.plan_json = {
            **plan_json,
            "invalidated_by_request_edit": True,
            "invalidated_reason": "execution_affecting_request_edit",
        }
    return runs


def _invalidate_approvals_for_request(session: Session, request_id: str) -> list[str]:
    approvals = list(
        session.execute(
            select(Approval)
            .where(Approval.request_id == request_id)
            .order_by(Approval.created_at.desc())
        ).scalars()
    )
    for approval in approvals:
        approval.decision = ApprovalDecision.INVALIDATED.value
    return [approval.id for approval in approvals]


def _update_audit_message(
    *,
    changed_fields: list[str],
    reset_to_draft: bool,
) -> str:
    if not changed_fields:
        return "Request update received; no persisted fields changed."
    if reset_to_draft:
        return (
            "Request execution intent updated; approval and dry-run plan "
            "were invalidated and the request was reset to draft."
        )
    return "Request updated."


def get_workflow_run(session: Session, workflow_run_id: str) -> WorkflowRun:
    run = session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise WorkflowRunNotFoundError(workflow_run_id)
    return run


def list_workflow_runs(session: Session) -> list[WorkflowRun]:
    return list(
        session.execute(
            select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(200)
        ).scalars()
    )


def _get_or_create_workflow(session: Session) -> Workflow:
    workflow = session.execute(
        select(Workflow).where(Workflow.slug == WORKFLOW_SLUG)
    ).scalar_one_or_none()
    if workflow is not None:
        return workflow

    workflow = Workflow(
        slug=WORKFLOW_SLUG,
        name="Deploy VM from vSphere Template",
        version="1.0.0",
        is_active=True,
    )
    session.add(workflow)
    session.flush()
    return workflow


def _latest_run_for_request(session: Session, request_id: str) -> WorkflowRun | None:
    return session.execute(
        select(WorkflowRun)
        .where(WorkflowRun.request_id == request_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _preflight_execution_plan(
    session: Session,
    request: Request,
    *,
    actor: str,
) -> WorkflowRun:
    run, problem = inspect_execution_plan(session, request)
    if problem is None and run is not None:
        return run

    if problem is None:
        message = f"Request {request.id} cannot execute because no plan inspection result exists."
        problem = ExecutionPlanProblem(
            code="plan_missing",
            message=message,
            data={"reason": "missing_workflow_run"},
        )

    _record_execution_preflight_failure(
        session,
        request,
        actor=actor,
        workflow_run=problem.workflow_run,
        message=problem.message,
        data=problem.data,
    )
    if problem.data.get("reason") == "invalid_request_status":
        raise InvalidTransitionError(problem.message)
    raise ExecutionPreflightError(problem.message)


def inspect_execution_plan(
    session: Session,
    request: Request,
) -> tuple[WorkflowRun | None, ExecutionPlanProblem | None]:
    if request.status != RequestStatus.PLANNED.value:
        message = (
            f"Request {request.id} is {request.status}; "
            f"expected {RequestStatus.PLANNED.value}"
        )
        return None, ExecutionPlanProblem(
            code="request_not_planned",
            message=message,
            data={
                "reason": "invalid_request_status",
                "expected_status": RequestStatus.PLANNED.value,
                "actual_status": request.status,
            },
        )

    run = _latest_run_for_request(session, request.id)
    if run is None:
        message = (
            f"Request {request.id} cannot execute because no persisted dry-run plan exists."
        )
        return None, ExecutionPlanProblem(
            code="plan_missing",
            message=message,
            data={"reason": "missing_workflow_run"},
        )

    if run.status != WorkflowRunStatus.PLANNED.value:
        message = (
            f"Request {request.id} cannot execute because workflow run {run.id} "
            f"is {run.status}; expected {WorkflowRunStatus.PLANNED.value}."
        )
        return None, ExecutionPlanProblem(
            code="plan_not_executable",
            message=message,
            workflow_run=run,
            data={
                "reason": "workflow_run_not_planned",
                "workflow_run_id": run.id,
                "actual_run_status": run.status,
                "expected_run_status": WorkflowRunStatus.PLANNED.value,
            },
        )

    if run.request_id != request.id:
        message = (
            f"Request {request.id} cannot execute because workflow run {run.id} "
            f"belongs to request {run.request_id}."
        )
        return None, ExecutionPlanProblem(
            code="plan_belongs_to_different_request",
            message=message,
            workflow_run=run,
            data={
                "reason": "workflow_run_request_mismatch",
                "workflow_run_id": run.id,
                "workflow_run_request_id": run.request_id,
                "expected_request_id": request.id,
            },
        )

    plan = run.plan_json
    if not isinstance(plan, dict) or not plan:
        message = (
            f"Request {request.id} cannot execute because workflow run {run.id} "
            "does not contain a persisted dry-run plan."
        )
        return None, ExecutionPlanProblem(
            code="plan_missing",
            message=message,
            workflow_run=run,
            data={"reason": "missing_plan", "workflow_run_id": run.id},
        )

    plan_request_id = plan.get("request_id")
    if plan_request_id != request.id:
        message = (
            f"Request {request.id} cannot execute because workflow run {run.id} "
            f"contains a dry-run plan for request {plan_request_id!r}."
        )
        return None, ExecutionPlanProblem(
            code="plan_belongs_to_different_request",
            message=message,
            workflow_run=run,
            data={
                "reason": "plan_request_mismatch",
                "workflow_run_id": run.id,
                "plan_request_id": plan_request_id,
                "expected_request_id": request.id,
            },
        )

    intent_problem = _inspect_plan_intent_matches_request(request, run)
    if intent_problem is not None:
        return None, intent_problem

    return run, None


def _inspect_plan_intent_matches_request(
    request: Request,
    run: WorkflowRun,
) -> ExecutionPlanProblem | None:
    plan = run.plan_json
    stored_intent = plan.get("request_intent")
    stored_hash = plan.get("request_intent_hash")
    if not isinstance(stored_intent, dict) or not isinstance(stored_hash, str):
        message = (
            f"Request {request.id} cannot execute because workflow run {run.id} "
            "does not include request intent metadata."
        )
        return ExecutionPlanProblem(
            code="request_plan_intent_drift",
            message=message,
            workflow_run=run,
            data={
                "reason": "missing_request_intent",
                "workflow_run_id": run.id,
            },
        )

    expected_stored_hash = build_request_intent_hash(stored_intent)
    if stored_hash != expected_stored_hash:
        message = (
            f"Request {request.id} cannot execute because workflow run {run.id} "
            "contains inconsistent request intent metadata."
        )
        return ExecutionPlanProblem(
            code="request_plan_intent_drift",
            message=message,
            workflow_run=run,
            data={
                "reason": "request_intent_metadata_mismatch",
                "workflow_run_id": run.id,
                "stored_request_intent_hash": stored_hash,
                "expected_request_intent_hash": expected_stored_hash,
            },
        )

    current_intent = build_request_intent(request)
    current_hash = build_request_intent_hash(current_intent)
    if current_hash == stored_hash:
        return None

    changed_fields = _changed_intent_fields(stored_intent, current_intent)
    message = (
        f"Request {request.id} cannot execute because its current intent no longer "
        f"matches workflow run {run.id}'s dry-run plan. Create a new plan before executing."
    )
    return ExecutionPlanProblem(
        code="request_plan_intent_drift",
        message=message,
        workflow_run=run,
        data={
            "reason": "request_intent_mismatch",
            "workflow_run_id": run.id,
            "stored_request_intent_hash": stored_hash,
            "current_request_intent_hash": current_hash,
            "changed_fields": changed_fields,
        },
    )


def _changed_intent_fields(stored: dict, current: dict, prefix: str = "") -> list[str]:
    changed: list[str] = []
    for key in sorted(stored.keys() | current.keys()):
        path = f"{prefix}.{key}" if prefix else str(key)
        stored_value = stored.get(key)
        current_value = current.get(key)
        if isinstance(stored_value, dict) and isinstance(current_value, dict):
            changed.extend(_changed_intent_fields(stored_value, current_value, path))
        elif stored_value != current_value:
            changed.append(path)
    return changed


def _record_execution_preflight_failure(
    session: Session,
    request: Request,
    *,
    actor: str,
    message: str,
    workflow_run: WorkflowRun | None = None,
    data: dict | None = None,
) -> None:
    record_audit_event(
        session,
        actor=actor,
        event_type="request.execution_preflight_failed",
        message=message,
        request=request,
        workflow_run=workflow_run,
        from_status=request.status,
        to_status=request.status,
        data=data,
    )
    session.commit()


def _ensure_status(request: Request, expected: RequestStatus) -> None:
    if request.status != expected.value:
        raise InvalidTransitionError(
            f"Request {request.id} is {request.status}; expected {expected.value}"
        )


def _ensure_cancellable_status(request: Request) -> None:
    if request.status not in CANCELLABLE_REQUEST_STATUSES:
        expected = ", ".join(sorted(CANCELLABLE_REQUEST_STATUSES))
        raise InvalidTransitionError(
            f"Request {request.id} is {request.status}; expected one of: {expected}"
        )


def _ensure_editable_status(request: Request) -> None:
    if request.status in LOCKED_REQUEST_STATUSES:
        locked = ", ".join(sorted(LOCKED_REQUEST_STATUSES))
        raise InvalidTransitionError(
            f"Request {request.id} is {request.status} and is locked; "
            f"edits are not allowed in locked states: {locked}"
        )
    if request.status not in EDITABLE_REQUEST_STATUSES:
        expected = ", ".join(sorted(EDITABLE_REQUEST_STATUSES))
        raise InvalidTransitionError(
            f"Request {request.id} is {request.status}; expected one of: {expected}"
        )


def _transition(
    session: Session,
    request: Request,
    to_status: RequestStatus,
    *,
    actor: str,
    event_type: str,
    message: str,
    workflow_run: WorkflowRun | None = None,
    data: dict | None = None,
) -> None:
    from_status = request.status
    request.status = to_status.value
    record_audit_event(
        session,
        actor=actor,
        event_type=event_type,
        message=message,
        request=request,
        workflow_run=workflow_run,
        from_status=from_status,
        to_status=to_status.value,
        data=data,
    )
    session.flush()
