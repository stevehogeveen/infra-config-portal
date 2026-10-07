"""Internal durable SPP ledger. No routes, hardware adapters or scope grants.

Each mutation owns a transaction on a dedicated session. A committed step claim
precedes dispatch; a process restart never reclaims an in-flight step.
"""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime
from dataclasses import dataclass
from typing import ContextManager, Protocol

from sqlalchemy import select, update

from app.models import AuditEvent, FirmwareApproval, GuardedOperation, utcnow
from app.services.audit import record_audit_event
from app.services.guarded_operation_ledger import OperationConflict, reserve
from app.services.spp_update_contract import ApplyRequest, Step, UpdatePlan, UpdateStatus
from app.services.spp_update_plan import Assessment, assessment_digest, project_plan

EVENT = "spp.operation.progress"


@dataclass(frozen=True)
class Readback:
    target_identity_sha256: str
    version: str


@dataclass(frozen=True)
class ReconciledReadback(Readback):
    checked_at: datetime
    dispatch_ended: bool
    authority_released: bool


class StepAdapter(Protocol):
    def authority(self, assessment: Assessment, step: Step) -> ContextManager[None]:
        """Admit/revoke audited run-owned authority; never a global scope grant."""

    def preflight(self, assessment: Assessment, step: Step) -> str:
        """Revalidate reviewed facts and return their assessment digest, or raise."""

    def send(self, assessment: Assessment, step: Step) -> None:
        """Exactly one reviewed dispatch, including only disclosed restart effects."""

    def verify(self, assessment: Assessment, step: Step) -> Readback:
        """Independent exact-target readback, not the upload response."""


def _digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def issue_review(session, assessment: Assessment, *, actor: str) -> UpdatePlan:
    """Only a trusted server assessment may call this; not browser-supplied data."""
    plan = project_plan(assessment)
    if plan.blockers:
        return plan
    token = secrets.token_hex(32)
    phrase = f"UPDATE {assessment.device_id}"
    row = FirmwareApproval(
        token_hash=_digest(token),
        profile_id=plan.profile_id,
        device_id=plan.device_id,
        actor=actor,
        confirmation_phrase=phrase,
        expires_at=plan.expires_at,
        intent_json={
            "operation": "whole-spp-update",
            "assessment": assessment.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json", by_alias=True),
        },
    )
    session.add(row)
    session.flush()
    record_audit_event(
        session,
        actor=actor,
        event_type="spp.review.issued",
        message="Whole-SPP review recorded; no dispatch.",
        data={
            "review_id": row.id,
            "plan_id": plan.plan_id,
            "profile_id": plan.profile_id,
            "device_id": plan.device_id,
        },
    )
    session.commit()
    return UpdatePlan.model_validate(
        {
            **plan.model_dump(),
            "review_token": token,
            "confirmation_phrase": phrase,
            "can_apply": True,
        }
    )


def _review(session, *, profile_id, device_id, actor, token):
    row = session.scalar(
        select(FirmwareApproval).where(
            FirmwareApproval.token_hash == _digest(token),
            FirmwareApproval.actor == actor,
            FirmwareApproval.profile_id == profile_id,
            FirmwareApproval.device_id == device_id,
        )
    )
    if row is None or row.intent_json.get("operation") != "whole-spp-update":
        raise OperationConflict("No matching whole-SPP review exists.")
    return row


def approve(
    session,
    *,
    profile_id: str,
    device_id: str,
    actor: str,
    request: ApplyRequest,
    fresh_assessment: Assessment,
) -> UpdateStatus:
    row = _review(
        session, profile_id=profile_id, device_id=device_id, actor=actor, token=request.review_token
    )
    if not hmac.compare_digest(
        row.confirmation_phrase.encode(), request.confirmation_phrase.encode()
    ):
        raise OperationConflict("The exact confirmation phrase is required.")
    original = Assessment.model_validate_json(json.dumps(row.intent_json["assessment"]))
    # A regenerated report changes bytes/time even when normalized facts are identical.
    fresh = fresh_assessment.model_copy(
        update={
            "checked_at": original.checked_at,
            "report_sha256": original.report_sha256,
        }
    )
    if assessment_digest(fresh) != assessment_digest(original):
        raise OperationConflict("The target, package or reviewed update plan changed.")
    if project_plan(fresh_assessment).blockers:
        raise OperationConflict("Fresh assessment is not ready for installation.")
    operation = reserve(
        session,
        profile_id=profile_id,
        device_id=device_id,
        resource="firmware-execution",
        idempotency_key=request.idempotency_key,
        reviewed_intent={"review_token_sha256": row.token_hash, "intent": row.intent_json},
        actor=actor,
        firmware_review_id=row.id,
    )
    plan = UpdatePlan.model_validate_json(json.dumps(row.intent_json["plan"]))
    initial = UpdateStatus(
        profile_id=profile_id,
        device_id=device_id,
        operation_id=operation.id,
        idempotency_key=request.idempotency_key,
        status="running",
        steps=[Step(**u.model_dump(), state="waiting") for u in plan.updates],
        current_step=plan.updates[0].step_id,
        message="Approved; waiting for execution.",
        next_action=None,
        evidence_at=None,
        active=True,
    )
    _transition(session, operation.id, "accepted", "spp-ready-0", initial, actor)
    return status(session, operation.id)


def _transition(session, operation_id, expected, target, snapshot, actor):
    snapshot = UpdateStatus.model_validate(snapshot.model_dump())
    changed = session.execute(
        update(GuardedOperation)
        .where(
            GuardedOperation.id == operation_id,
            GuardedOperation.status == expected,
            GuardedOperation.active_device.is_not(None),
        )
        .values(
            status=target,
            active_device=snapshot.device_id if snapshot.active else None,
            updated_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(
        session,
        actor=actor,
        event_type=EVENT,
        message=snapshot.message,
        data={
            "operation_id": operation_id,
            "ledger_state": target,
            "status": snapshot.model_dump(mode="json", by_alias=True),
        },
    )
    session.commit()
    return True


def status(session, operation_id: str) -> UpdateStatus:
    """Stored evidence only. Never invokes a provider or infers an unsent result."""
    operation = session.get(GuardedOperation, operation_id, populate_existing=True)
    if operation is None:
        raise OperationConflict("Operation not found.")
    event = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == EVENT,
            AuditEvent.data_json["operation_id"].as_string() == operation_id,
            AuditEvent.data_json["ledger_state"].as_string() == operation.status,
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    if event is None:
        raise OperationConflict("Whole-SPP progress is not initialized; retain the device lock.")
    snapshot = dict(event.data_json["status"])
    if snapshot.get("execution_mode") == "offline" and operation.active_device:
        observed = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "spp.offline.observation",
                AuditEvent.data_json["operation_id"].as_string() == operation_id,
                AuditEvent.data_json["name"].as_string() == "observed",
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        if observed is not None:
            snapshot["observed"] = observed.data_json["value"]
    return UpdateStatus.model_validate_json(json.dumps(snapshot))


def claim_step(
    session, operation_id: str, *, actor: str, expected_step_id: str | None = None
) -> Step | None:
    """Internal worker only, after run authority and exact-target preflight.

    The returned step is the sole dispatch ticket. None must never cause a send.
    """
    current = status(session, operation_id)
    index = next((i for i, s in enumerate(current.steps) if s.state != "done"), None)
    if index is None or current.steps[index].state != "waiting":
        return None
    if expected_step_id is not None and current.steps[index].step_id != expected_step_id:
        return None
    steps = [s.model_copy(deep=True) for s in current.steps]
    steps[index] = steps[index].model_copy(
        update={"state": "installing", "started_at": datetime.now(UTC)}
    )
    snapshot = current.model_copy(
        update={
            "steps": steps,
            "current_step": steps[index].step_id,
            "message": "Dispatch claimed; completion is not proven.",
        }
    )
    if not _transition(
        session, operation_id, f"spp-ready-{index}", f"spp-sent-{index}", snapshot, actor
    ):
        return None
    return steps[index]


def record_step(
    session,
    operation_id: str,
    *,
    step_id: str,
    actor: str,
    outcome: str,
    target_identity_sha256: str,
    verified_version: str | None = None,
) -> bool:
    """Adapter evidence only, never browser assertions or vendor exit-code guesses.

    'failed' requires definite terminal failure; lost sends use 'uncertain'.
    A done outcome requires independent exact-target version readback.
    """
    if outcome not in {"done", "failed", "uncertain"}:
        raise ValueError("Unsupported step outcome.")
    current = status(session, operation_id)
    row = session.scalar(
        select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id)
    )
    if row is None or row.intent_json.get("operation") != "whole-spp-update":
        raise OperationConflict("No bound whole-SPP review.")
    if target_identity_sha256 != row.intent_json["assessment"]["target_identity_sha256"]:
        raise OperationConflict("Readback target does not match the approved server.")
    index = next((i for i, s in enumerate(current.steps) if s.step_id == step_id), None)
    if index is None or current.steps[index].state != "installing":
        return False
    now = datetime.now(UTC)
    steps = [s.model_copy(deep=True) for s in current.steps]
    steps[index] = Step.model_validate(
        {
            **steps[index].model_dump(),
            "state": outcome,
            "finished_at": None if outcome == "uncertain" else now,
            "verified_version": verified_version,
        }
    )
    complete = outcome == "done" and index == len(steps) - 1
    advance = outcome == "done" and not complete
    if not advance and not complete:
        for i in range(index + 1, len(steps)):
            steps[i] = steps[i].model_copy(update={"state": "not_started"})
    state = "verified" if complete else "running" if advance else outcome
    target = f"spp-ready-{index + 1}" if advance else state
    snapshot = current.model_copy(
        update={
            "steps": steps,
            "status": state,
            "active": advance or outcome == "uncertain",
            "current_step": steps[index + 1].step_id if advance else None,
            "evidence_at": now,
            "message": "Step independently verified."
            if outcome == "done"
            else "Update stopped; no automatic retry.",
            "next_action": "Reconcile this operation before another update."
            if outcome == "uncertain"
            else None,
        }
    )
    return _transition(session, operation_id, f"spp-sent-{index}", target, snapshot, actor)


def execute_next(session, operation_id: str, *, actor: str, adapter: StepAdapter) -> UpdateStatus:
    """Execute one pending step through an injected adapter. No real adapter registered.

    Authority must be revoked before recording completion/releasing the device.
    A crash between the durable claim and result retains the lock, without resend.
    """
    current = status(session, operation_id)
    index = next((i for i, s in enumerate(current.steps) if s.state != "done"), None)
    if index is None or current.steps[index].state != "waiting":
        return current
    row = session.scalar(
        select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id)
    )
    if row is None or row.intent_json.get("operation") != "whole-spp-update":
        raise OperationConflict("No bound whole-SPP review.")
    assessment = Assessment.model_validate_json(json.dumps(row.intent_json["assessment"]))
    step = current.steps[index]
    claimed = None
    authority_restored = False
    body_failed = False
    try:
        with adapter.authority(assessment, step):
            try:
                if adapter.preflight(assessment, step) != assessment_digest(assessment):
                    raise OperationConflict("Reviewed firmware facts changed.")
                claimed = claim_step(
                    session, operation_id, actor=actor, expected_step_id=step.step_id
                )
                if claimed is not None:
                    adapter.send(assessment, claimed)
                    proof = adapter.verify(assessment, claimed)
                    if (
                        proof.target_identity_sha256 != assessment.target_identity_sha256
                        or proof.version != claimed.to
                    ):
                        raise OperationConflict("Independent firmware verification did not match.")
            except Exception:
                body_failed = True
        authority_restored = True
        if body_failed:
            raise OperationConflict("Execution or verification failed.")
    except Exception:
        # Do not persist exception strings: vendor failures can contain credentials.
        if claimed is not None:
            record_step(
                session,
                operation_id,
                step_id=claimed.step_id,
                actor=actor,
                outcome="uncertain",
                target_identity_sha256=assessment.target_identity_sha256,
            )
        else:
            steps = [s.model_copy(deep=True) for s in current.steps]
            terminal = "failed" if authority_restored else "uncertain"
            steps[index] = steps[index].model_copy(update={"state": terminal})
            for i in range(index + 1, len(steps)):
                steps[i] = steps[i].model_copy(update={"state": "not_started"})
            failed = current.model_copy(
                update={
                    "steps": steps,
                    "status": terminal,
                    "active": not authority_restored,
                    "current_step": None,
                    "dispatch_prevented": index == 0 and authority_restored,
                    "message": "Execution prerequisites failed before dispatch."
                    if authority_restored
                    else "Execution authority cleanup is unresolved; device remains locked.",
                    "next_action": "Review the update again."
                    if authority_restored
                    else "Reconcile this operation before another update.",
                }
            )
            _transition(session, operation_id, f"spp-ready-{index}", terminal, failed, actor)
        return status(session, operation_id)
    if claimed is not None:
        record_step(
            session,
            operation_id,
            step_id=claimed.step_id,
            actor=actor,
            outcome="done",
            target_identity_sha256=proof.target_identity_sha256,
            verified_version=proof.version,
        )
    return status(session, operation_id)


def reconcile_step(session, operation_id, *, actor, proof: ReconciledReadback):
    """Record fresh post-crash evidence; never dispatch or infer success from exit code."""
    operation = session.get(GuardedOperation, operation_id, populate_existing=True)
    current = status(session, operation_id)
    index = next((i for i, step in enumerate(current.steps) if step.state != "done"), None)
    if index is None or current.steps[index].state not in {"installing", "uncertain"}:
        return current
    step = current.steps[index]
    if operation.status not in {f"spp-sent-{index}", "uncertain"}:
        return current
    review = session.scalar(
        select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id)
    )
    if (
        not review
        or review.intent_json.get("operation") != "whole-spp-update"
        or proof.target_identity_sha256
        != review.intent_json["assessment"]["target_identity_sha256"]
        or proof.version != step.to
        or not proof.dispatch_ended
        or not proof.authority_released
        or step.started_at is None
        or proof.checked_at.tzinfo is None
        or not step.started_at <= proof.checked_at <= datetime.now(UTC)
    ):
        raise OperationConflict("Fresh exact-target completion evidence is not established.")
    steps = [item.model_copy(deep=True) for item in current.steps]
    steps[index] = Step.model_validate(
        {
            **step.model_dump(),
            "state": "done",
            "finished_at": proof.checked_at,
            "verified_version": proof.version,
        }
    )
    for i in range(index + 1, len(steps)):
        steps[i] = steps[i].model_copy(update={"state": "waiting"})
    complete = index == len(steps) - 1
    snapshot = current.model_copy(
        update={
            "steps": steps,
            "status": "verified" if complete else "running",
            "active": not complete,
            "current_step": None if complete else steps[index + 1].step_id,
            "message": "Firmware independently verified after reconciliation.",
            "next_action": None,
            "evidence_at": proof.checked_at,
        }
    )
    _transition(
        session,
        operation_id,
        operation.status,
        "verified" if complete else f"spp-ready-{index + 1}",
        snapshot,
        actor,
    )
    return status(session, operation_id)
