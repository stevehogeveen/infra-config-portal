"""Guarded firmware-execution API."""

from app.services.guarded_execution import build_router
from app.services.firmware_execution import BLOCKERS
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.models import AuditEvent
from app.services.audit import record_audit_event
from app.services.firmware_component import inspect_component
from app.services.firmware_packages import FirmwarePackageError
from app.services.firmware_catalog import next_ilo_version
from app.services.firmware_standalone import browse_standalone, inspect_standalone
from app.services.firmware_trust import inspect_spp_bridge, verify_bridge_from_spp
from app.providers.hpe_firmware_inventory import (
    FirmwareInventoryError,
    collect_firmware_capabilities,
)

from app.services.firmware_flow import preview_firmware, apply_firmware, verify_firmware, _latest
from app.services.firmware_reconcile import fence_unsent_attempt
from app.services.firmware_worker import FirmwareReviewError
from app.services.guarded_operation_ledger import OperationConflict

router = build_router(
    "firmware-execution", BLOCKERS, preview_handler=preview_firmware, apply_handler=apply_firmware
)


class RecoveryPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=36)


class RecoveryClosure(RecoveryPreview):
    review_token: str = Field(min_length=1, max_length=128)
    confirmation_phrase: str = Field(max_length=128)


@router.post("/recovery-preview")
def preview_recovery(
    profile_id: str,
    device_id: str,
    payload: RecoveryPreview,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    from app.services.firmware_recovery import preview_closure

    server_in_kit(profile_id, device_id, session)
    try:
        return preview_closure(
            session,
            profile_id=profile_id,
            device_id=device_id,
            operation_id=payload.operation_id,
            actor=actor,
        )
    except OperationConflict as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/close-unverified")
def close_recovery(
    profile_id: str,
    device_id: str,
    payload: RecoveryClosure,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    from app.services.firmware_recovery import close_unverified

    server_in_kit(profile_id, device_id, session)
    try:
        return close_unverified(
            session, profile_id=profile_id, device_id=device_id, actor=actor, **payload.model_dump()
        )
    except OperationConflict as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None


class FirmwareVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(min_length=1, max_length=36)
    confirm_read_only: bool = Field(strict=True)


class UnsentReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    prevent_late_dispatch: bool = Field(strict=True)


@router.post("/reconcile-unsent")
def reconcile_unsent(
    profile_id: str,
    device_id: str,
    payload: UnsentReconciliation,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    if payload.prevent_late_dispatch is not True:
        raise HTTPException(409, "Confirm closing this attempt against delayed dispatch.")
    try:
        return fence_unsent_attempt(
            session,
            profile_id=profile_id,
            device_id=device_id,
            actor=actor,
            review_token=payload.review_token,
            idempotency_key=payload.idempotency_key,
        )
    except (FirmwareReviewError, OperationConflict) as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None


@router.post("/verify")
def verify_operation(
    profile_id: str,
    device_id: str,
    payload: FirmwareVerification,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    if payload.confirm_read_only is not True:
        raise HTTPException(409, "Confirm exact-target read-only firmware verification.")
    return verify_firmware(session, profile_id, device_id, payload.operation_id, actor)


class ComponentInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_id: str = Field(min_length=1, max_length=128)


class CapabilityRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_read_only: bool = Field(strict=True)


class StandaloneSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)


class BridgePreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/prepare-spp-bridge")
def prepare_spp_bridge(
    profile_id: str,
    device_id: str,
    payload: BridgePreparation,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    selected = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "kit.firmware_package_selected",
            AuditEvent.data_json["profile_id"].as_string() == profile_id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    if selected is None:
        raise HTTPException(409, "Select the SPP containing the signed iLO firmware.")
    capabilities = _latest(session, "kit.firmware_capabilities_read", profile_id, device_id)
    try:
        # Legacy preparation without hardware evidence remains offline-only 1.48 inspection.
        target = (
            next_ilo_version(capabilities.data_json.get("manager_firmware_version"))
            if capabilities
            else "1.48"
        )
        bridge = (
            inspect_spp_bridge(selected.data_json["package"])
            if target == "1.48"
            else inspect_spp_bridge(selected.data_json["package"], target)
        )
        authentication = verify_bridge_from_spp(selected.data_json["package"], bridge)
    except FirmwarePackageError as exc:
        raise HTTPException(409, str(exc)) from None
    result = {
        "profile_id": profile_id,
        "device_id": device_id,
        "package_selection_id": selected.id,
        "target_version": target,
        "bridge": bridge,
        "authentication": authentication,
        "can_apply": False,
        "blockers": [
            "Fresh target applicability and prerequisites require review.",
            "Preparation does not authorize installation. Create a separate exact-target firmware install review.",
        ],
    }
    event = record_audit_event(
        session,
        actor=actor,
        event_type="kit.firmware_bridge_authenticated",
        message="SPP bridge binary authenticated offline; no installation approval.",
        data=result,
    )
    session.commit()
    return {**result, "preparation_id": event.id}


@router.get("/standalone-packages")
def standalone_packages(
    profile_id: str,
    device_id: str,
    folder: str = "",
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    try:
        return browse_standalone(folder)
    except FirmwarePackageError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/select-standalone")
def select_standalone(
    profile_id: str,
    device_id: str,
    payload: StandaloneSelection,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    try:
        result = inspect_standalone(payload.path)
    except FirmwarePackageError as exc:
        raise HTTPException(409, str(exc)) from None
    result = {**result, "profile_id": profile_id, "device_id": device_id}
    event = record_audit_event(
        session,
        actor=actor,
        event_type="kit.firmware_standalone_selected",
        message="Standalone package inspected and selected; no hardware approval.",
        data=result,
    )
    session.commit()
    return {**result, "selection_id": event.id}


@router.get("/selected-standalone")
def selected_standalone(
    profile_id: str,
    device_id: str,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    event = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "kit.firmware_standalone_selected",
            AuditEvent.data_json["profile_id"].as_string() == profile_id,
            AuditEvent.data_json["device_id"].as_string() == device_id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    return {"selection": {**event.data_json, "selection_id": event.id} if event else None}


@router.post("/capabilities")
def read_capabilities(
    profile_id: str,
    device_id: str,
    payload: CapabilityRead,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    if payload.confirm_read_only is not True:
        raise HTTPException(409, "Confirm the exact-target read-only capability check.")
    try:
        result = collect_firmware_capabilities(session, device_id)
    except FirmwareInventoryError as exc:
        raise HTTPException(409, str(exc)) from None
    result = {**result, "profile_id": profile_id}
    record_audit_event(
        session,
        actor=actor,
        event_type="kit.firmware_capabilities_read",
        message="Explicit read-only firmware discovery; no installation.",
        data=result,
    )
    session.commit()
    return result


@router.post("/inspect-component")
def inspect_selected_component(
    profile_id: str,
    device_id: str,
    payload: ComponentInspection,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    server_in_kit(profile_id, device_id, session)
    selection = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "kit.firmware_package_selected",
            AuditEvent.data_json["profile_id"].as_string() == profile_id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(1)
    )
    if selection is None:
        raise HTTPException(409, "Select an SPP package before inspecting a component.")
    try:
        result = inspect_component(selection.data_json["package"], payload.component_id)
    except (FirmwarePackageError, OSError) as exc:
        raise HTTPException(
            409,
            str(exc)
            if isinstance(exc, FirmwarePackageError)
            else "Selected component could not be read.",
        ) from None
    result = {
        **result,
        "profile_id": profile_id,
        "device_id": device_id,
        "package_selection_id": selection.id,
    }
    record_audit_event(
        session,
        actor=actor,
        event_type="kit.firmware_component_inspected",
        message="Local component content hashed; no hardware approval or dispatch.",
        data=result,
    )
    session.commit()
    return result
