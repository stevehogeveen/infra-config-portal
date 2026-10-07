"""Durable SPP API/worker orchestration; adapters are installed by the host, never HTTP.

The database is the work queue. Admission commits before returning; loss of a
browser response or worker wakeup does not lose the approved job.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models import FirmwareApproval, GuardedOperation
from app.services.guarded_operation_ledger import OperationConflict, find_attempt
from app.services.spp_update_contract import ApplyRequest, UpdateStatus
from app.services.spp_update_execution import (
    EVENT,
    StepAdapter,
    _digest,
    _review,
    _transition,
    approve,
    execute_next,
    issue_review,
    status,
)
from app.services.spp_update_plan import Assessment


class SppBackend(Protocol):
    def available(self, profile_id: str, device_id: str) -> bool:
        """Local configuration only; do not probe hardware during GET status."""

    def assess(self, profile_id: str, device_id: str) -> Assessment:
        """Authenticated vendor assessment for the exact saved target and baseline."""

    def adapter(self, operation_id: str) -> StepAdapter:
        """Create a run-bound adapter, using saved credentials only inside dispatch."""


def _whole(row):
    return row.intent_json.get("operation") == "whole-spp-update"


def _matching(session, profile_id, device_id, key=None):
    query = (
        select(GuardedOperation, FirmwareApproval)
        .join(FirmwareApproval, FirmwareApproval.operation_id == GuardedOperation.id)
        .where(GuardedOperation.profile_id == profile_id, GuardedOperation.device_id == device_id)
        .order_by(GuardedOperation.created_at.desc(), GuardedOperation.id.desc())
    )
    if key is not None:
        query = query.where(GuardedOperation.idempotency_key == key)
    return next((operation for operation, review in session.execute(query) if _whole(review)), None)


def recorded_status(session, profile_id, device_id, *, key=None):
    operation = _matching(session, profile_id, device_id, key)
    if operation:
        return status(session, operation.id)
    return UpdateStatus(
        profile_id=profile_id,
        device_id=device_id,
        operation_id=None,
        idempotency_key=None,
        status="not_started",
        current_step=None,
        message="No recorded whole-SPP operation.",
        next_action=None,
        evidence_at=None,
        active=False,
    )


def plan(session, backend, profile_id, device_id, actor):
    if getattr(backend, "mode", None) == "offline-spp-boot-v1":
        return backend.plan(session, profile_id, device_id, actor)
    assessment = backend.assess(profile_id, device_id)
    if assessment.profile_id != profile_id or assessment.device_id != device_id:
        raise OperationConflict("Assessment target does not match this server.")
    return issue_review(session, assessment, actor=actor)


def submit(session, backend, profile_id, device_id, actor, request: ApplyRequest):
    if getattr(backend, "mode", None) == "offline-spp-boot-v1":
        return backend.submit(session, profile_id, device_id, actor, request)
    # Duplicate responses must remain available after evidence/approval expiry,
    # and must not cause another assessment, dispatch, or permission change.
    review = _review(
        session, profile_id=profile_id, device_id=device_id, actor=actor, token=request.review_token
    )
    existing = find_attempt(
        session, profile_id, device_id, "firmware-execution", request.idempotency_key
    )
    if existing:
        if review.operation_id != existing.id:
            raise OperationConflict("Attempt key belongs to another reviewed operation.")
        return status(session, existing.id)
    assessment = backend.assess(profile_id, device_id)
    if assessment.profile_id != profile_id or assessment.device_id != device_id:
        raise OperationConflict("Assessment target does not match this server.")
    return approve(
        session,
        profile_id=profile_id,
        device_id=device_id,
        actor=actor,
        request=request,
        fresh_assessment=assessment,
    )


def reconcile(session, profile_id, device_id, actor, request: ApplyRequest):
    """Fence a lost, never-recorded approval. No adapter or target connection."""
    review = _review(
        session, profile_id=profile_id, device_id=device_id, actor=actor, token=request.review_token
    )
    existing = find_attempt(
        session, profile_id, device_id, "firmware-execution", request.idempotency_key
    )
    if existing:
        if review.operation_id != existing.id:
            raise OperationConflict("Attempt key belongs to another reviewed operation.")
        return status(session, existing.id)
    if review.operation_id:
        raise OperationConflict("This review belongs to a different attempt.")
    from app.services.audit import record_audit_event
    from app.services.spp_update_contract import Step, UpdatePlan

    saved = UpdatePlan.model_validate_json(json.dumps(review.intent_json["plan"]))
    intent = {"review_token_sha256": review.token_hash, "intent": review.intent_json}
    digest = _digest(json.dumps(intent, sort_keys=True, separators=(",", ":"), allow_nan=False))
    operation = GuardedOperation(
        profile_id=profile_id,
        device_id=device_id,
        resource="firmware-execution",
        idempotency_key=request.idempotency_key,
        intent_hash=digest,
        active_device=None,
        status="failed",
    )
    try:
        session.add(operation)
        session.flush()
        consumed = session.execute(
            update(FirmwareApproval)
            .where(FirmwareApproval.id == review.id, FirmwareApproval.operation_id.is_(None))
            .values(operation_id=operation.id)
        )
        if consumed.rowcount != 1:
            raise OperationConflict("This review was consumed by another request.")
        closed = UpdateStatus(
            execution_mode=saved.execution_mode,
            profile_id=profile_id,
            device_id=device_id,
            operation_id=operation.id,
            idempotency_key=request.idempotency_key,
            status="failed",
            steps=[Step(**item.model_dump(), state="not_started") for item in saved.updates],
            current_step=None,
            message="Unsent approval closed; nothing was dispatched.",
            next_action="Review the update again.",
            evidence_at=datetime.now(UTC),
            active=False,
            dispatch_prevented=True,
        )
        record_audit_event(
            session,
            actor=actor,
            event_type=EVENT,
            message=closed.message,
            data={
                "operation_id": operation.id,
                "ledger_state": "failed",
                "status": closed.model_dump(mode="json", by_alias=True),
            },
        )
        session.commit()
        return closed
    except (IntegrityError, OperationConflict):
        session.rollback()
        existing = find_attempt(
            session, profile_id, device_id, "firmware-execution", request.idempotency_key
        )
        if existing and existing.intent_hash == digest:
            return status(session, existing.id)
        raise OperationConflict(
            "Attempt changed during reconciliation; read recorded status."
        ) from None


def recover_reserved(session, operation_id, actor):
    """Recover the admission commit gap without recreating or resending a command."""
    from app.services.spp_update_contract import Step, UpdatePlan

    review = session.scalar(
        select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id)
    )
    operation = session.get(GuardedOperation, operation_id)
    if not review or not _whole(review) or not operation or operation.status != "accepted":
        return
    saved = UpdatePlan.model_validate_json(json.dumps(review.intent_json["plan"]))
    # A reserve commit alone cannot distinguish apply from an unsent fence crash.
    # Close it rather than turning an ambiguous admission into a hardware write.
    snapshot = UpdateStatus(
        execution_mode=saved.execution_mode,
        profile_id=operation.profile_id,
        device_id=operation.device_id,
        operation_id=operation.id,
        idempotency_key=operation.idempotency_key,
        status="failed",
        steps=[Step(**item.model_dump(), state="not_started") for item in saved.updates],
        current_step=None,
        message="Admission was interrupted before dispatch.",
        next_action="Review the update again.",
        evidence_at=datetime.now(UTC),
        active=False,
        dispatch_prevented=True,
    )
    _transition(session, operation.id, "accepted", "failed", snapshot, actor)


def work_once(session_factory, backend, *, limit=32):
    """One bounded queue sweep. Claimed/sent/uncertain work is never re-dispatched."""
    with session_factory() as session:
        rows = session.execute(
            select(GuardedOperation, FirmwareApproval)
            .join(FirmwareApproval, FirmwareApproval.operation_id == GuardedOperation.id)
            .where(GuardedOperation.active_device.is_not(None))
            .order_by(GuardedOperation.created_at)
            .limit(limit)
        ).all()
        pending = [
            (op.id, op.status, op.updated_at, review.intent_json.get("mode"))
            for op, review in rows
            if _whole(review)
        ]
    for operation_id, state, updated, mode in pending:
        with session_factory() as session:
            if state == "accepted":
                when = updated.replace(tzinfo=UTC) if updated.tzinfo is None else updated
                if datetime.now(UTC) - when > timedelta(minutes=2):
                    recover_reserved(session, operation_id, "spp-worker")
            elif mode == "offline-spp-boot-v1" and getattr(backend, "mode", None) == mode:
                backend.advance(session, operation_id)
            elif state.startswith("spp-ready-") and mode is None and hasattr(backend, "adapter"):
                execute_next(
                    session, operation_id, actor="spp-worker", adapter=backend.adapter(operation_id)
                )
    return len(pending)


class Worker:
    """Restartable database scanner. Shutdown never kills an in-flight vendor process."""

    def __init__(self, session_factory, backend, interval=5):
        from threading import Event, Thread

        self.stop_event = Event()
        self.session_factory = session_factory
        self.backend = backend
        self.interval = interval
        self.thread = Thread(target=self._run, name="spp-worker", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _run(self):
        import logging

        while not self.stop_event.is_set():
            try:
                work_once(self.session_factory, self.backend)
            except Exception:
                # Exception strings and vendor output may contain credentials.
                logging.getLogger(__name__).warning(
                    "SPP queue sweep failed; stored claims retained."
                )
            self.stop_event.wait(self.interval)
