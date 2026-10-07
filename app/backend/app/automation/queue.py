import os
from datetime import UTC, datetime

from redis import Redis
from rq import Queue
from rq.serializers import JSONSerializer
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.automation.contracts import InventoryJob, InventoryResult, InventoryRun
from app.automation.targets import (
    AutomationBlocked,
    execution_blockers,
    profile_revision,
    resolve_target,
)
from app.core.config import settings
from app.models import AuditEvent

QUEUE_NAME = "inventory"


def inventory_queue() -> Queue:
    url = os.getenv("AUTOMATION_REDIS_URL")
    if not url:
        raise AutomationBlocked(
            "Automation worker is not configured. Start the automation Compose services."
        )
    return Queue(
        QUEUE_NAME,
        connection=Redis.from_url(url, socket_connect_timeout=2, socket_timeout=3),
        serializer=JSONSerializer,
    )


def enqueue_inventory(session: Session, device_id: str, actor: str) -> InventoryRun:
    config, revision = resolve_target(session, device_id)
    blockers = execution_blockers(config, settings.provider_mode)
    if blockers:
        raise AutomationBlocked(" ".join(blockers))
    payload = InventoryJob(
        device_id=device_id,
        target_revision=revision,
        profile_revision=profile_revision(),
        provider_mode=settings.provider_mode,
        actor=actor,
    )
    queue = inventory_queue()
    job = queue.enqueue(
        "app.automation.tasks.execute_inventory",
        payload.model_dump(),
        job_timeout=150,
        ttl=300,
        result_ttl=86400,
        failure_ttl=86400,
        description="Read-only device system inventory",
    )
    session.add(
        AuditEvent(
            actor=actor,
            event_type="automation.inventory.queued",
            to_status="queued",
            message="Read-only inventory queued.",
            data_json={"job_id": job.id, "device_id": device_id},
        )
    )
    session.commit()
    return InventoryRun(job_id=job.id, device_id=device_id, status="queued")


def read_inventory_run(session: Session, device_id: str, job_id: str) -> InventoryRun:
    job = inventory_queue().fetch_job(job_id)
    if job is None:
        raise LookupError("Inventory job expired or was not found.")
    payload = InventoryJob.model_validate(job.args[0])
    if payload.device_id != device_id:
        raise LookupError("Inventory job does not belong to this device.")
    status = job.get_status(refresh=True).value
    result = InventoryResult.model_validate(job.return_value()) if status == "finished" else None
    current = False
    if result is not None:
        _, revision = resolve_target(session, device_id)
        age = (datetime.now(UTC) - datetime.fromisoformat(result.checked_at)).total_seconds()
        current = (
            result.status == "completed"
            and result.source == "ansible"
            and payload.provider_mode != "mock"
            and revision == payload.target_revision
            and profile_revision() == payload.profile_revision
            and settings.provider_mode == payload.provider_mode
            and 0 <= age <= 300
        )
    return InventoryRun(
        job_id=job.id,
        device_id=device_id,
        status=result.status if result else status,
        current=current,
        result=result,
    )


def latest_inventory_run(session: Session, device_id: str) -> InventoryRun | None:
    event = session.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.event_type == "automation.inventory.queued",
            AuditEvent.data_json["device_id"].as_string() == device_id,
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    if event is None:
        return None
    try:
        return read_inventory_run(session, device_id, event.data_json["job_id"])
    except LookupError:
        return InventoryRun(
            job_id=event.data_json["job_id"],
            device_id=device_id,
            status="expired",
        )
