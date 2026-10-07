"""Commit completion only from trusted post-dispatch, exact-review readback."""

from datetime import UTC

from sqlalchemy import select, update

from app.models import AuditEvent, FirmwareApproval, GuardedOperation, utcnow
from app.services.audit import record_audit_event
from app.services.firmware_readback import evaluate_ilo_readback
from app.services.guarded_operation_ledger import OperationConflict, recorded_result


def complete_from_readback(
    session, *, profile_id: str, device_id: str, operation_id: str, observation: dict, actor: str
) -> dict:
    """Observation must come from the provider collector, never an HTTP request body."""
    operation = session.scalar(
        select(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.profile_id == profile_id,
            GuardedOperation.device_id == device_id,
            GuardedOperation.resource == "firmware-execution",
        )
        .execution_options(populate_existing=True)
    )
    if operation is None:
        raise OperationConflict("No matching firmware operation exists")
    if operation.status == "verified":
        return recorded_result(operation, session=session)
    review = session.scalar(
        select(FirmwareApproval).where(FirmwareApproval.operation_id == operation.id)
    )
    dispatch = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "guarded.operation.dispatch_claimed",
            AuditEvent.data_json["operation_id"].as_string() == operation.id,
        )
        .order_by(AuditEvent.created_at.asc())
        .limit(1)
    )
    if review is None or dispatch is None or operation.status not in {"running", "uncertain"}:
        raise OperationConflict(
            "A consumed review and committed dispatch are required for completion"
        )
    submitted_at = dispatch.created_at
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=UTC)
    result = evaluate_ilo_readback(
        device_id=device_id,
        target_identity_sha256=review.intent_json["target_identity_sha256"],
        target_hardware_identity_sha256=review.intent_json.get("target_hardware_identity_sha256"),
        target_version=review.intent_json["target_version"],
        submitted_at=submitted_at,
        observation=observation,
    )
    if result["status"] != "verified":
        record_audit_event(
            session,
            actor=actor,
            event_type="firmware.readback.unproven",
            message="Firmware completion remains unproven; device lock retained.",
            data={
                "operation_id": operation.id,
                "blockers": result["blockers"],
                "observation": {
                    key: observation.get(key)
                    for key in (
                        "source",
                        "authenticated",
                        "exact_target_only",
                        "identity_verified",
                        "device_id",
                        "target_identity_sha256",
                        "target_hardware_identity_sha256",
                        "manager_firmware_version",
                        "checked_at",
                        "update_state",
                        "errors",
                    )
                },
            },
        )
        session.commit()
        return {**recorded_result(operation, session=session), "blockers": result["blockers"]}
    changed = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == operation.id,
            GuardedOperation.status.in_(["running", "uncertain"]),
            GuardedOperation.active_device == device_id,
        )
        .values(status="verified", active_device=None, updated_at=utcnow())
    )
    if changed.rowcount != 1:
        session.rollback()
        raise OperationConflict("Operation changed during completion; refresh its recorded status")
    record_audit_event(
        session,
        actor=actor,
        event_type="firmware.operation.verified",
        message=result["message"],
        data={
            "profile_id": profile_id,
            "device_id": device_id,
            "operation_id": operation.id,
            "review_id": review.id,
            "evidence_at": result["evidence_at"],
            "target_version": review.intent_json["target_version"],
        },
    )
    session.commit()
    session.refresh(operation)
    return recorded_result(operation, session=session)
