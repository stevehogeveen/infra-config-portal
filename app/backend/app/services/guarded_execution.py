"""Guarded contracts; status is read-only and dispatch requires an injected handler."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.models import AuditEvent, GuardedOperation
from app.services.audit import record_audit_event
from app.services.blocker_guidance import with_blocker_details
from app.services.guarded_operation_ledger import find_attempt, recorded_result


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(min_length=1, max_length=128)
    confirmation_phrase: str = Field(min_length=1, max_length=256)
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


def build_router(
    resource: str, blockers: tuple[str, ...], *, preview_handler=None, apply_handler=None
) -> APIRouter:
    router = APIRouter(prefix=f"/api/v1/rack-plans/{{profile_id}}/{resource}", tags=[resource])
    event_type = f"kit.{resource}.preview"

    def recorded_preview(session, profile_id, device_id):
        events = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type == event_type)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        )
        return next(
            (
                event.data_json
                for event in events
                if event.data_json.get("profile_id") == profile_id
                and event.data_json.get("device_id") == device_id
            ),
            None,
        )

    @router.get("/status")
    def status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
        server_in_kit(profile_id, device_id, session)
        operation = session.scalar(
            select(GuardedOperation)
            .where(
                GuardedOperation.profile_id == profile_id,
                GuardedOperation.device_id == device_id,
                GuardedOperation.resource == resource,
            )
            .order_by(GuardedOperation.created_at.desc(), GuardedOperation.id.desc())
        )
        if operation:
            return with_blocker_details(recorded_result(operation, session=session))
        previous = recorded_preview(session, profile_id, device_id)
        available = bool(
            previous
            and previous["preview"].get("can_apply")
            and datetime.fromisoformat(previous["preview"]["expires_at"]) > datetime.now(UTC)
        )
        status_blockers = list(previous["preview"]["blockers"] if previous else blockers)
        if previous and previous["preview"].get("can_apply") and not available:
            status_blockers.append("Firmware review expired. Open a new review.")
        return with_blocker_details(
            {
                "profile_id": profile_id,
                "device_id": device_id,
                "resource": resource,
                "status": "blocked" if previous and not available else "not_started",
                "operation_id": None,
                "idempotency_key": None,
                "evidence_at": None,
                "reviewed_at": previous["reviewed_at"] if previous else None,
                "stages": [],
                "blockers": status_blockers,
                "execution_available": available,
                "message": "Stored workflow state only. This status performs no fresh hardware check.",
                "next_action": "Review and explicitly confirm the prepared operation."
                if available
                else "Review the capability blockers before any installation or recovery approval.",
            }
        )

    @router.post("/preview")
    def preview(
        profile_id: str,
        device_id: str,
        payload: PreviewRequest,
        session: Session = Depends(get_session),
        actor: str = Depends(get_current_actor),
    ):
        server = server_in_kit(profile_id, device_id, session)
        now = datetime.now(UTC)
        result = {
            "review_token": uuid4().hex + uuid4().hex,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "target": {"device_id": device_id, "name": server.name},
            "target_provenance": "saved_plan",
            "evidence_at": None,
            "component_hash": None,
            "drive_identities": [],
            "operations": [],
            "blockers": list(blockers),
            "can_apply": False,
            "confirmation_phrase": "",
            "message": "Capability review only. No fresh hardware read or write was sent; target identity is not verified.",
        }
        if preview_handler is not None:
            result = preview_handler(session, profile_id, device_id, actor, result)
        result = with_blocker_details(result)
        record_audit_event(
            session,
            actor=actor,
            event_type=event_type,
            message="Firmware or recovery review recorded; no hardware calls.",
            data={
                "profile_id": profile_id,
                "device_id": device_id,
                "reviewed_at": now.isoformat(),
                "preview": result,
            },
        )
        session.commit()
        return result

    @router.post("/apply")
    def apply(
        profile_id: str,
        device_id: str,
        payload: ApplyRequest,
        session: Session = Depends(get_session),
        actor: str = Depends(get_current_actor),
    ):
        server_in_kit(profile_id, device_id, session)
        if apply_handler is not None:
            return apply_handler(session, profile_id, device_id, actor, payload)
        # Do not create an operation record: a rejected request cannot reconcile an older send.
        raise HTTPException(
            409,
            "Execution is unavailable. No hardware action was dispatched. " + " ".join(blockers),
        )

    @router.get("/reconcile")
    def reconcile(
        profile_id: str,
        device_id: str,
        idempotency_key: str = Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
        session: Session = Depends(get_session),
    ):
        server_in_kit(profile_id, device_id, session)
        operation = find_attempt(session, profile_id, device_id, resource, idempotency_key)
        if operation:
            return {
                **recorded_result(operation, session=session),
                "requested_idempotency_key": idempotency_key,
            }
        # A missing row is not proof of no send, including pre-ledger attempts.
        return {
            "profile_id": profile_id,
            "device_id": device_id,
            "resource": resource,
            "requested_idempotency_key": idempotency_key,
            "idempotency_key": None,
            "operation_id": None,
            "status": "uncertain",
            "record_found": False,
            "safe_to_retry": False,
            "evidence_at": None,
            "stages": [],
            "message": "No correlated execution record is available. This does not prove the request was never sent or applied.",
            "next_action": "Keep this attempt blocked pending supported, target-bound reconciliation.",
        }

    return router
