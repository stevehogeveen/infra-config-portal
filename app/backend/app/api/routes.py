from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.config import settings
from app.core.database import get_session
from app.models import AuditEvent
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.mock import MockSourceOfTruthAdapter
from app.providers.registry import (
    ProviderRegistryError,
    provider_registry,
    provider_registry_error_status,
)
from app.schemas import (
    ApprovalCreate,
    ArtifactRead,
    AuditEventRead,
    CatalogRead,
    IloReadinessSummaryRead,
    IloUpgradeReadinessRead,
    MediaInventoryRead,
    ProviderProbeResultRead,
    ProviderStatusRead,
    RequestReadinessRead,
    RequestRead,
    VMDeploymentCreate,
    VMDeploymentUpdate,
    WorkflowRunRead,
)
from app.services.artifacts import (
    list_request_artifacts,
    list_workflow_run_artifacts,
)
from app.services.lifecycle import (
    ExecutionPreflightError,
    InvalidTransitionError,
    RequestNotFoundError,
    RequestUpdateValidationError,
    ValidationFailureError,
    WorkflowRunNotFoundError,
    approve_request,
    cancel_request,
    create_vm_deployment_request,
    execute_request,
    get_request,
    get_workflow_run,
    list_workflow_runs,
    list_requests,
    plan_request,
    submit_request,
    update_vm_deployment_request,
)
from app.services.media_inventory import get_media_inventory
from app.services.ilo_readiness import get_ilo_readiness_summary
from app.services.readiness import get_request_readiness
from app.services.upgrade_decision import get_ilo_upgrade_readiness

router = APIRouter(prefix="/api/v1")


@router.post(
    "/requests/vm-deploy",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vm_deploy(
    payload: VMDeploymentCreate,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    return create_vm_deployment_request(session, payload, actor=actor)


@router.get("/requests", response_model=list[RequestRead])
def read_requests(session: Session = Depends(get_session)) -> list[RequestRead]:
    return list_requests(session)


@router.get("/requests/{request_id}", response_model=RequestRead)
def read_request(request_id: str, session: Session = Depends(get_session)) -> RequestRead:
    try:
        return get_request(session, request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.get("/requests/{request_id}/readiness", response_model=RequestReadinessRead)
def read_request_readiness(
    request_id: str,
    session: Session = Depends(get_session),
) -> RequestReadinessRead:
    try:
        return get_request_readiness(session, request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.get("/requests/{request_id}/artifacts", response_model=list[ArtifactRead])
def read_request_artifacts(
    request_id: str,
    session: Session = Depends(get_session),
) -> list[ArtifactRead]:
    try:
        return list_request_artifacts(session, request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.patch("/requests/{request_id}", response_model=RequestRead)
def update_request(
    request_id: str,
    payload: VMDeploymentUpdate,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    try:
        return update_vm_deployment_request(session, request_id, payload, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except RequestUpdateValidationError as exc:
        raise HTTPException(status_code=422, detail={"validation_errors": exc.errors}) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/submit", response_model=RequestRead)
def submit(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    try:
        return submit_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except ProviderRegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValidationFailureError as exc:
        raise HTTPException(status_code=422, detail={"validation_errors": exc.errors}) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/approve", response_model=RequestRead)
def approve(
    request_id: str,
    payload: ApprovalCreate,
    session: Session = Depends(get_session),
) -> RequestRead:
    try:
        return approve_request(session, request_id, payload)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except ProviderRegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/plan", response_model=WorkflowRunRead)
def plan(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> WorkflowRunRead:
    actor = get_current_actor(fastapi_request)
    try:
        return plan_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/cancel", response_model=RequestRead)
def cancel(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    try:
        return cancel_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/execute", response_model=WorkflowRunRead)
def execute(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> WorkflowRunRead:
    actor = get_current_actor(fastapi_request)
    try:
        return execute_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except ProviderRegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExecutionPreflightError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/workflow-runs/{workflow_run_id}", response_model=WorkflowRunRead)
def read_workflow_run(
    workflow_run_id: str,
    session: Session = Depends(get_session),
) -> WorkflowRunRead:
    try:
        return get_workflow_run(session, workflow_run_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc


@router.get("/workflow-runs/{workflow_run_id}/artifacts", response_model=list[ArtifactRead])
def read_workflow_run_artifacts(
    workflow_run_id: str,
    session: Session = Depends(get_session),
) -> list[ArtifactRead]:
    try:
        return list_workflow_run_artifacts(session, workflow_run_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.get("/audit-events", response_model=list[AuditEventRead])
def read_audit_events(session: Session = Depends(get_session)) -> list[AuditEventRead]:
    return list(
        session.execute(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)
        ).scalars()
    )


@router.get("/workflow-runs", response_model=list[WorkflowRunRead])
def read_workflow_runs(session: Session = Depends(get_session)) -> list[WorkflowRunRead]:
    return list_workflow_runs(session)


@router.get("/providers/status", response_model=list[ProviderStatusRead])
def read_provider_status() -> list[ProviderStatusRead]:
    try:
        return provider_registry().statuses()
    except ProviderRegistryError as exc:
        return [provider_registry_error_status(settings.provider_mode, str(exc))]


@router.post("/providers/{provider_id}/probe", response_model=ProviderProbeResultRead)
def probe_provider(provider_id: str) -> ProviderProbeResultRead:
    if provider_id == "ilo-redfish":
        return _run_provider_probe(provider_id, IloRedfishAdapter().probe)
    if provider_id == "cisco-console":
        return _run_provider_probe(provider_id, CiscoConsoleAdapter().probe)
    if provider_id == "cisco-ansible":
        return _run_provider_probe(provider_id, CiscoAnsibleAdapter().probe)
    if provider_id == "esxi-readonly":
        return _run_provider_probe(provider_id, EsxiReadonlyAdapter().probe)
    raise HTTPException(status_code=404, detail="Provider probe not found")


@router.get(
    "/providers/ilo-redfish/upgrade-readiness",
    response_model=IloUpgradeReadinessRead,
)
def read_ilo_upgrade_readiness() -> IloUpgradeReadinessRead:
    return get_ilo_upgrade_readiness()


@router.get(
    "/providers/ilo-redfish/readiness-summary",
    response_model=IloReadinessSummaryRead,
)
def read_ilo_readiness_summary() -> IloReadinessSummaryRead:
    return get_ilo_readiness_summary()


def _run_provider_probe(provider_id: str, probe: Callable[[], dict]) -> dict:
    try:
        return probe()
    except Exception as exc:
        return {
            "provider_id": provider_id,
            "status": "blocked",
            "message": "Provider probe failed before completing safely.",
            "warnings": [],
            "blockers": [f"Provider probe failed: {exc.__class__.__name__}."],
        }


@router.get("/catalog", response_model=CatalogRead)
def read_catalog() -> CatalogRead:
    return MockSourceOfTruthAdapter().catalog()


@router.get("/media-inventory", response_model=MediaInventoryRead)
def read_media_inventory() -> MediaInventoryRead:
    return get_media_inventory()
