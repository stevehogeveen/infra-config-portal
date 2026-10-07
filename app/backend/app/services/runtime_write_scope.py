"""Durable permission reviews and serialized dispatch admission; never contacts hardware."""

import hashlib
import json
import os
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models import (
    AuditEvent,
    GuardedOperation,
    RuntimeDispatchLease,
    RuntimeScopeReview,
    RuntimeWriteScope,
    WorkflowRun,
)
from app.services.audit import record_audit_event

FIRMWARE_ACTION = "ilo.firmware-update"
PHRASE = "ONLY UPDATE ILO FIRMWARE"
# Firmware maintenance: the iLO update, other parts installed through the iLO, and the restart
# that applies them.
FIRMWARE_ACTIONS = frozenset({FIRMWARE_ACTION, "ilo.component-update", "ilo-redfish.firmware-restart"})
# RAID build: power off, stage the reviewed layout on the controller, then power on so it applies.
STORAGE_ACTIONS = frozenset({"ilo-redfish.hpe-raid-apply", "ilo-redfish.raid-shutdown", "ilo-redfish.raid-boot"})
STORAGE_PHRASE = "ONLY BUILD RAID"
# ESXi install: mount the reviewed installer ISO, set a one-time CD boot, power on or restart,
# then eject that same media once ESXi answers.
ESXI_INSTALL_ACTIONS = frozenset({"ilo-redfish.esxi-virtual-media", "ilo-redfish.esxi-boot-once", "ilo-redfish.esxi-power", "esxi.datastore-create"})
ESXI_INSTALL_PHRASE = "ONLY INSTALL ESXI"
# Windows: import the reviewed OVA/OVF onto the verified ESXi host and power that VM on.
VM_DEPLOY_ACTIONS = frozenset({"esxi.vm-deploy", "esxi.vm-power"})
VM_DEPLOY_PHRASE = "ONLY DEPLOY WINDOWS"
TARGETS = {"read_only", "firmware_only", "storage_only", "esxi_install_only", "vm_deploy_only"}
PHRASES = {"firmware_only": PHRASE, "storage_only": STORAGE_PHRASE, "esxi_install_only": ESXI_INSTALL_PHRASE,
           "vm_deploy_only": VM_DEPLOY_PHRASE}
EFFECTS = {
    "firmware_only": "Only firmware can be updated, through the iLO, including the restarts that apply it. Nothing else on the server can be changed.",
    "storage_only": "Only the server's disks and RAID can be changed (build, delete or wipe), including the restarts that apply it. Nothing else on the server can be changed.",
    "esxi_install_only": "Only the ESXi installer can be attached and booted, including the restart that starts it. Nothing else on the server can be changed.",
    "vm_deploy_only": "Only the reviewed Windows image can be imported onto ESXi and its VM powered on. Nothing else on the server can be changed.",
    "read_only": "Nothing on the server can be changed.",
}


class WriteScopeError(ValueError):
    pass


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def bootstrap():
    raw = os.getenv("LAB_ALLOWED_WRITE_ACTIONS")
    actions = None if raw is None else sorted({x.strip() for x in raw.split(",") if x.strip()})
    return {
        "actions": actions,
        "firmware": settings.lab_allow_firmware_updates,
        "power": settings.lab_allow_power_actions,
        "reset": settings.lab_allow_factory_reset,
        "mode": settings.provider_mode,
    }


def _bootstrap_hash():
    return _hash(json.dumps(bootstrap(), sort_keys=True))


def scope_name(row):
    if row and row.scope:
        return row.scope
    config = bootstrap()
    actions = config["actions"]
    if config["mode"] != "local-lab-readwrite" or actions == []:
        return "read_only"
    if actions == [FIRMWARE_ACTION] and config["firmware"]:
        return "firmware_only"
    return "mixed"


def _locked_row(session):
    # INSERT races are isolated from the caller transaction. UPDATE takes the same
    # exclusive row/write lock on PostgreSQL and SQLite before admission or change.
    if session.get(RuntimeWriteScope, 1) is None:
        try:
            with session.begin_nested():
                session.add(RuntimeWriteScope(id=1, generation=0))
                session.flush()
        except IntegrityError:
            pass
    session.execute(
        update(RuntimeWriteScope)
        .where(RuntimeWriteScope.id == 1)
        .values(generation=RuntimeWriteScope.generation)
    )
    return session.get(RuntimeWriteScope, 1, populate_existing=True)


def active_operations(session):
    active = [
        {
            "operation_id": row.id,
            "resource": row.resource,
            "device_id": row.device_id,
            "status": row.status,
        }
        for row in session.scalars(
            select(GuardedOperation).where(GuardedOperation.active_device.is_not(None))
        )
    ]
    active.extend(
        {
            "operation_id": row.id,
            "resource": row.action_id,
            "status": "dispatch_in_flight_or_uncertain",
        }
        for row in session.scalars(select(RuntimeDispatchLease))
    )
    events = list(
        session.scalars(select(AuditEvent).where(AuditEvent.event_type.like("kit.raid_rebuild.%")))
    )
    attempts = {e.id: e for e in events if e.event_type == "kit.raid_rebuild.attempt"}

    def proven_rejection(event):
        attempt = attempts.get(event.data_json.get("attempt_id"))
        if not attempt or event.data_json.get("device_id") != attempt.data_json.get("device_id"):
            return False
        if event.data_json.get("reason") == "erase_method_rejected":
            return True
        codes = event.data_json.get("codes") or []
        return bool(
            event.data_json.get("identity")
            and event.data_json["identity"] == attempt.data_json.get("identity")
            and event.data_json.get("reported_at")
            and set(codes).intersection(
                {
                    "SmartStorageMessages.2.0.1.CanCreateEditableConfigControllerStatusNotOK",
                    "SmartStorageMessages.2.0.1.PropertyKeyMissing",
                }
            )
        )

    closed = {
        (e.data_json.get("device_id"), e.data_json.get("attempt_id"))
        for e in events
        if e.event_type == "kit.raid_rebuild.verified"
        or (e.event_type == "kit.raid_rebuild.failed" and proven_rejection(e))
    }
    verified = [e for e in events if e.event_type == "kit.raid_rebuild.verified"]
    for event in events:
        kind = event.event_type.removeprefix("kit.raid_rebuild.")
        if kind not in {"attempt", "shutdown_attempt", "boot_attempt"}:
            continue
        device = event.data_json.get("device_id")
        attempt = event.data_json.get("attempt_id") if kind == "boot_attempt" else event.id
        if (device, attempt) in closed:
            continue
        if kind == "shutdown_attempt" and any(
            e.data_json.get("device_id") == device
            and e.created_at > event.created_at
            and event.data_json.get("identity")
            and e.data_json.get("attempt_id") in attempts
            and attempts[e.data_json["attempt_id"]].data_json.get("identity")
            == event.data_json["identity"]
            and attempts[e.data_json["attempt_id"]].created_at > event.created_at
            for e in verified
        ):
            continue
        active.append(
            {
                "operation_id": event.id,
                "device_id": device,
                "resource": "legacy_raid_" + kind,
                "status": "unresolved",
            }
        )
    active.extend(
        {"operation_id": row.id, "resource": row.workflow_slug, "status": row.status}
        for row in session.scalars(
            select(WorkflowRun).where(
                WorkflowRun.status.in_(["executing", "uncertain"]),
                ~WorkflowRun.provider.like("%mock%"),
            )
        )
    )
    return active


def state(session):
    row = session.get(RuntimeWriteScope, 1, populate_existing=True)
    return {
        "scope": scope_name(row),
        "source": "operator" if row and row.scope else "server_configuration",
        "changed_at": row.changed_at if row else None,
        "changed_by": row.changed_by if row else None,
        "active_operations": active_operations(session),
        "blockers": [],
    }


def transition_blockers(session, target_scope):
    if target_scope == "read_only":
        return []
    from app.providers.action_policy import current_lab_action_policy

    policy = current_lab_action_policy()
    blockers = policy.readonly_blockers()
    if policy.provider_mode != "local-lab-readwrite":
        blockers.append("Firmware permission requires local-lab-readwrite mode.")
    blockers.extend(
        f"Resolve {item['resource']} operation {item['operation_id']} ({item['status']}) first."
        for item in active_operations(session)
    )
    return blockers


def preview(session, actor, target_scope):
    from app.services.blocker_guidance import describe_blockers

    if target_scope not in TARGETS:
        raise WriteScopeError("Only read_only, firmware_only, storage_only and esxi_install_only transitions are supported.")
    row = _locked_row(session)
    blockers = transition_blockers(session, target_scope)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    session.add(
        RuntimeScopeReview(
            token_hash=_hash(token),
            actor=actor,
            target_scope=target_scope,
            generation=row.generation,
            bootstrap_hash=_bootstrap_hash(),
            expires_at=expires,
        )
    )
    result = {
        "review_token": token,
        "expires_at": expires,
        "current_scope": scope_name(row),
        "target_scope": target_scope,
        "blockers": blockers,
        "blocker_details": describe_blockers(blockers),
        "confirmation_phrase": PHRASES.get(target_scope, ""),
        # One plain sentence: what the app may still change. Reads are never restricted.
        "effects": [EFFECTS[target_scope]],
    }
    record_audit_event(
        session,
        actor=actor,
        event_type="runtime.write_scope.preview",
        message="Reviewed runtime hardware write permissions.",
        data={"target_scope": target_scope, "generation": row.generation, "blockers": blockers},
    )
    session.commit()
    return result


def apply(session, actor, review_token, confirmation_phrase):
    row = _locked_row(session)
    review = session.get(RuntimeScopeReview, _hash(review_token), populate_existing=True)
    if (
        review is None
        or review.actor != actor
        or review.consumed
        or review.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC)
        or review.generation != row.generation
        or review.bootstrap_hash != _bootstrap_hash()
    ):
        raise WriteScopeError("Scope review is missing, expired, used or stale. Preview again.")
    expected = PHRASES.get(review.target_scope, "")
    if confirmation_phrase != expected:
        raise WriteScopeError("Enter the exact scope confirmation phrase.")
    blockers = transition_blockers(session, review.target_scope)
    if blockers:
        raise WriteScopeError(" ".join(blockers))
    previous = scope_name(row)
    row.scope = review.target_scope
    row.generation += 1
    row.changed_at = datetime.now(UTC)
    row.changed_by = actor
    review.consumed = True
    record_audit_event(
        session,
        actor=actor,
        event_type="runtime.write_scope.applied",
        message="Changed runtime hardware write permissions; no hardware action sent.",
        from_status=previous,
        to_status=row.scope,
        data={"generation": row.generation, "review_hash": review.token_hash},
    )
    session.commit()
    return state(session)


def admit_dispatch(session, action_id, *, activity_only=False):
    row = _locked_row(session)
    if not activity_only and (
        row.scope == "read_only"
        or (row.scope == "firmware_only" and action_id not in FIRMWARE_ACTIONS)
        or (row.scope == "storage_only" and action_id not in STORAGE_ACTIONS)
        or (row.scope == "esxi_install_only" and action_id not in ESXI_INSTALL_ACTIONS)
        or (row.scope == "vm_deploy_only" and action_id not in VM_DEPLOY_ACTIONS)
    ):
        raise WriteScopeError("This hardware action is outside the operator-selected write scope.")
    lease = RuntimeDispatchLease(action_id=action_id)
    session.add(lease)
    session.commit()
    return lease.id


def finish_dispatch(session, lease_id):
    lease = session.get(RuntimeDispatchLease, lease_id)
    if lease:
        session.delete(lease)
        session.commit()


def runtime_override():
    from app.core.database import SessionLocal, init_database

    # CLI providers do not run FastAPI lifespan. This is the existing additive,
    # once-per-engine bootstrap, never a reset or a permission grant.
    init_database()
    with SessionLocal() as session:
        row = session.get(RuntimeWriteScope, 1)
        return row.scope if row else None


def firmware_only():
    override = runtime_override()
    if override is not None:
        return override == "firmware_only"
    return {x.strip() for x in os.getenv("LAB_ALLOWED_WRITE_ACTIONS", "").split(",")} == {
        FIRMWARE_ACTION
    }


@contextmanager
def dispatch_lease(action_id):
    ticket = {"retain": False}
    if settings.provider_mode == "mock":
        yield ticket
        return
    from app.core.database import SessionLocal, init_database

    init_database()
    with SessionLocal() as session:
        lease_id = admit_dispatch(session, action_id)
    # Callers durably record attempts before sending. Graceful exits leave their
    # unresolved operation evidence; process death additionally retains this lease.
    try:
        yield ticket
    finally:
        if not ticket["retain"]:
            with SessionLocal() as session:
                finish_dispatch(session, lease_id)


class WriteScopeActivityMiddleware:
    """Hold admission evidence across legacy mutating API requests, on every worker."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        from app.core.database import SessionLocal
        from sqlalchemy.exc import SQLAlchemyError
        from starlette.concurrency import run_in_threadpool
        from starlette.responses import JSONResponse

        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or settings.provider_mode == "mock"
            or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}
            or path.startswith("/api/v1/runtime/write-scope")
        ):
            await self.app(scope, receive, send)
            return

        def begin():
            with SessionLocal() as session:
                return admit_dispatch(
                    session, (scope["method"] + " " + path)[:128], activity_only=True
                )

        def finish(lease):
            with SessionLocal() as session:
                finish_dispatch(session, lease)

        try:
            lease = await run_in_threadpool(begin)
        except SQLAlchemyError:
            await JSONResponse(
                {"detail": "Runtime permission storage unavailable; request not started."},
                status_code=503,
            )(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            await run_in_threadpool(finish, lease)
