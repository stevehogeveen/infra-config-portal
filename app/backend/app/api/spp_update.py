"""Whole-SPP API. A missing production provider leaves the legacy iLO UI available."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.services.guarded_operation_ledger import OperationConflict
from app.services.firmware_packages import FirmwarePackageError
from app.services.spp_update_contract import ApplyRequest, PlanRequest, UpdatePlan, UpdateStatus
from app.services import spp_update_runtime as runtime

router = APIRouter(prefix="/api/v1/rack-plans/{profile_id}/firmware-update", tags=["whole-spp"])


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=128)


def backend(request: Request):
    provider = getattr(request.app.state, "spp_backend", None)
    if provider is None:
        raise HTTPException(501, "Whole-SPP vendor adapter is not configured.")
    return provider


@router.post("/verify", response_model=UpdateStatus)
def verify(
    profile_id: str,
    device_id: str,
    payload: VerifyRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
    provider=Depends(backend),
):
    server_in_kit(profile_id, device_id, session)
    if getattr(provider, "mode", None) != "offline-spp-boot-v1":
        raise HTTPException(
            501, "Readback reconciliation is not configured for this execution method."
        )
    try:
        return provider.verify(session, profile_id, device_id, payload.operation_id)
    except (OperationConflict, FirmwarePackageError) as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None


def check_target(session, provider, profile_id, device_id):
    server_in_kit(profile_id, device_id, session)
    if not provider.available(profile_id, device_id):
        raise HTTPException(501, "Whole-SPP updates are not available for this target and package.")


@router.get("/status", response_model=UpdateStatus)
def status(
    profile_id: str,
    device_id: str,
    request: Request,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
    idempotency_key: str | None = Query(default=None, min_length=1, max_length=128),
):
    server_in_kit(profile_id, device_id, session)
    try:
        result = runtime.recorded_status(session, profile_id, device_id, key=idempotency_key)
        # Existing records stay readable if the provider is removed or disabled.
        if result.operation_id is None:
            provider = backend(request)
            if not provider.available(profile_id, device_id):
                raise HTTPException(501, "Whole-SPP updates are not available for this server.")
        return result
    except (OperationConflict, FirmwarePackageError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/plan", response_model=UpdatePlan)
def plan(
    profile_id: str,
    device_id: str,
    payload: PlanRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
    provider=Depends(backend),
):
    if payload.device_id != device_id:
        raise HTTPException(409, "Plan target does not match the selected server.")
    check_target(session, provider, profile_id, device_id)
    try:
        return runtime.plan(session, provider, profile_id, device_id, actor)
    except (OperationConflict, FirmwarePackageError) as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/apply", response_model=UpdateStatus)
def apply(
    profile_id: str,
    device_id: str,
    payload: ApplyRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
    provider=Depends(backend),
):
    check_target(session, provider, profile_id, device_id)
    try:
        return runtime.submit(session, provider, profile_id, device_id, actor, payload)
    except (OperationConflict, FirmwarePackageError) as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/reconcile", response_model=UpdateStatus)
def reconcile(
    profile_id: str,
    device_id: str,
    payload: ApplyRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    try:
        return runtime.reconcile(session, profile_id, device_id, actor, payload)
    except OperationConflict as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None
