"""SPP iLO route orchestration. Preview uses recorded evidence and local media only."""

from fastapi import HTTPException
from sqlalchemy import select

from app.models import AuditEvent, GuardedOperation
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.hpe_firmware_adapter import HpeFirmwareAdapter, bridge_intent
from app.providers.hpe_firmware_inventory import collect_firmware_capabilities
from app.services.firmware_completion import complete_from_readback
from app.services.firmware_packages import FirmwarePackageError
from app.services.firmware_catalog import ilo_component, next_ilo_version
from app.services.firmware_reviews import issue_review, load_review
from app.services.firmware_trust import inspect_spp_bridge, verify_bridge_from_spp
from app.services.firmware_worker import FirmwareReviewError, run_reviewed_firmware
from app.services.guarded_operation_ledger import OperationConflict, find_attempt, recorded_result
from app.services.runtime_write_scope import firmware_only


def _latest(session, event_type, profile_id, device_id=None):
    query = select(AuditEvent).where(
        AuditEvent.event_type == event_type,
        AuditEvent.data_json["profile_id"].as_string() == profile_id,
    )
    if device_id is not None:
        query = query.where(AuditEvent.data_json["device_id"].as_string() == device_id)
    return session.scalar(
        query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1)
    )


def preview_firmware(session, profile_id, device_id, actor, default):
    blockers = current_lab_action_policy().action_blockers(
        "ilo.firmware-update", ActionCategory.FIRMWARE_UPDATE
    )
    if not firmware_only():
        blockers.append(
            "Exclusive firmware maintenance scope is required; competing hardware writes must be disabled."
        )
    if session.scalar(
        select(GuardedOperation.id).where(GuardedOperation.active_device == device_id)
    ):
        blockers.append(
            "An unresolved operation already holds this device. Verify it before another change."
        )
    selected = _latest(session, "kit.firmware_package_selected", profile_id)
    capabilities = _latest(session, "kit.firmware_capabilities_read", profile_id, device_id)
    if selected is None:
        blockers.append("Select the SPP containing the signed iLO firmware.")
    if capabilities is None:
        blockers.append("Run the explicitly confirmed read-only firmware capability check.")
    else:
        # Keep individual recorded health reasons separate for actionable guidance.
        blockers.extend(
            (capabilities.data_json.get("ilo_update_health") or {}).get("blockers") or []
        )
    if blockers:
        return {**default, "blockers": blockers}
    try:
        target = next_ilo_version(capabilities.data_json.get("manager_firmware_version"))
        bridge = (
            inspect_spp_bridge(selected.data_json["package"])
            if target == "1.48"
            else inspect_spp_bridge(selected.data_json["package"], target)
        )
        authentication = verify_bridge_from_spp(selected.data_json["package"], bridge)
        intent = bridge_intent(
            profile_id, device_id, selected.id, bridge, authentication, capabilities.data_json
        )
        phrase = f"INSTALL ILO {target}"
        review = issue_review(
            session,
            profile_id=profile_id,
            device_id=device_id,
            actor=actor,
            intent=intent,
            confirmation_phrase=phrase,
        )
    except (FirmwareReviewError, FirmwarePackageError) as exc:
        return {**default, "blockers": [str(exc)]}
    except (KeyError, TypeError, ValueError):
        return {
            **default,
            "blockers": ["Recorded preparation evidence is incomplete; prepare and check again."],
        }
    return {
        **default,
        "review_token": review.review_token,
        "expires_at": review.expires_at.isoformat(),
        "target_provenance": "live-ilo-firmware-capabilities",
        "evidence_at": capabilities.data_json["checked_at"],
        "component_hash": intent["component_sha256"],
        "blockers": [],
        "can_apply": True,
        "warnings": intent["ilo_update_health"]["warnings"],
        "confirmation_phrase": phrase,
        "operations": [
            {
                "order": 1,
                "component": "iLO 5",
                "current_version": intent["installed_version"],
                "package_version": target,
                "file": ilo_component(target).filename,
                "action": "POST /cgi-bin/uploadFile; automatic iLO reset; no host reboot",
            }
        ],
        "message": f"Install only the authenticated iLO {target} firmware. iLO will reset and temporarily disconnect. Keep power connected. Listed storage and redundancy warnings remain unresolved; this does not clear them for RAID. No host reboot or storage change is authorized.",
    }


def apply_firmware(session, profile_id, device_id, actor, payload):
    try:
        review = load_review(
            session,
            profile_id=profile_id,
            device_id=device_id,
            actor=actor,
            token=payload.review_token,
        )
        # A matching duplicate reads the durable result without another hardware preflight.
        existing = find_attempt(
            session, profile_id, device_id, "firmware-execution", payload.idempotency_key
        )
        if existing:
            from app.models import FirmwareApproval

            approval = session.get(FirmwareApproval, review.review_id)
            if (
                approval.operation_id != existing.id
                or payload.confirmation_phrase != review.confirmation_phrase
            ):
                raise FirmwareReviewError(
                    "Attempt key or typed confirmation does not match the consumed review."
                )
            return recorded_result(existing, session=session)
        return run_reviewed_firmware(
            session,
            review=review,
            review_token=payload.review_token,
            confirmation_phrase=payload.confirmation_phrase,
            idempotency_key=payload.idempotency_key,
            actor=actor,
            adapter=HpeFirmwareAdapter(session),
        )
    except (FirmwareReviewError, FirmwarePackageError, OperationConflict) as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None
    except Exception:
        session.rollback()
        raise HTTPException(
            409, "Firmware preparation failed safely. Reconcile this attempt before retrying."
        ) from None


def verify_firmware(session, profile_id, device_id, operation_id, actor):
    operation = session.scalar(
        select(GuardedOperation).where(
            GuardedOperation.id == operation_id,
            GuardedOperation.profile_id == profile_id,
            GuardedOperation.device_id == device_id,
            GuardedOperation.resource == "firmware-execution",
        )
    )
    if operation is None:
        raise HTTPException(404, "No matching firmware operation exists.")
    if operation.status == "verified":
        return recorded_result(operation, session=session)
    if operation.status not in {"running", "uncertain"}:
        raise HTTPException(409, "No dispatched firmware operation is available for readback.")
    try:
        capabilities = collect_firmware_capabilities(session, device_id)
        observation = {
            **capabilities,
            "source": "live-ilo-firmware-readback",
            "update_state": capabilities["state"],
        }
        return complete_from_readback(
            session,
            profile_id=profile_id,
            device_id=device_id,
            operation_id=operation_id,
            observation=observation,
            actor=actor,
        )
    except Exception:
        session.rollback()
        raise HTTPException(
            409, "Firmware readback is not proven. The operation remains blocked; do not resend."
        ) from None
