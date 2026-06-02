from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import ApprovalDecision, RequestStatus, WorkflowRunStatus
from app.models import Approval, Request, VMDeploymentRequest, Workflow, WorkflowRun
from app.providers.mock import MockSourceOfTruthAdapter, MockVsphereAdapter
from app.schemas import ApprovalCreate, VMDeploymentCreate
from app.services.audit import record_audit_event
from app.services.worker import InlineWorker

WORKFLOW_SLUG = "vm_deploy_from_template"


class RequestNotFoundError(Exception):
    pass


class WorkflowRunNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


class ValidationFailureError(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("Request failed source-of-truth validation")
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


def submit_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
    source_of_truth: MockSourceOfTruthAdapter | None = None,
) -> Request:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.DRAFT)
    source_of_truth = source_of_truth or MockSourceOfTruthAdapter()

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


def plan_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
    vsphere: MockVsphereAdapter | None = None,
) -> WorkflowRun:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.APPROVED)
    vsphere = vsphere or MockVsphereAdapter()

    workflow = _get_or_create_workflow(session)
    plan = vsphere.plan_vm_deployment(request)
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
        data={"workflow_run_id": run.id, "dry_run": True},
    )
    session.commit()
    return get_workflow_run(session, run.id)


def execute_request(
    session: Session,
    request_id: str,
    *,
    actor: str,
    vsphere: MockVsphereAdapter | None = None,
    worker: InlineWorker | None = None,
) -> WorkflowRun:
    request = get_request(session, request_id)
    _ensure_status(request, RequestStatus.PLANNED)
    vsphere = vsphere or MockVsphereAdapter()
    worker = worker or InlineWorker()

    run = _latest_run_for_request(session, request.id)
    if run is None or run.status != WorkflowRunStatus.PLANNED.value:
        raise WorkflowRunNotFoundError(f"No planned workflow run for request {request.id}")

    run.status = WorkflowRunStatus.EXECUTING.value
    _transition(
        session,
        request,
        RequestStatus.EXECUTING,
        actor=actor,
        event_type="request.execution_started",
        message="Mock workflow execution started.",
        workflow_run=run,
        data={"workflow_run_id": run.id},
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
        data={"workflow_run_id": run.id, "mock": True},
    )
    session.commit()
    return get_workflow_run(session, run.id)


def get_workflow_run(session: Session, workflow_run_id: str) -> WorkflowRun:
    run = session.get(WorkflowRun, workflow_run_id)
    if run is None:
        raise WorkflowRunNotFoundError(workflow_run_id)
    return run


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


def _ensure_status(request: Request, expected: RequestStatus) -> None:
    if request.status != expected.value:
        raise InvalidTransitionError(
            f"Request {request.id} is {request.status}; expected {expected.value}"
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
