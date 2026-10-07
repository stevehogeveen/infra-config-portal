from datetime import UTC, datetime
from rq import get_current_job

from app.automation.ansible_inventory import run_inventory
from app.automation.contracts import InventoryJob, InventoryResult
from app.automation.targets import (
    AutomationBlocked,
    execution_blockers,
    profile_revision,
    resolve_target,
)
from app.core.database import SessionLocal
from app.models import AuditEvent


def execute_inventory(payload: dict) -> dict:
    job = InventoryJob.model_validate(payload)
    running_job = get_current_job()
    result = InventoryResult(
        device_id=job.device_id,
        status="blocked",
        source="mock" if job.provider_mode == "mock" else "ansible",
        checked_at=datetime.now(UTC).isoformat(),
        summary="Inventory not executed.",
    )
    try:
        with SessionLocal() as session:
            config, revision = resolve_target(session, job.device_id)
            if revision != job.target_revision or profile_revision() != job.profile_revision:
                raise AutomationBlocked(
                    "Device access or lab profile changed. Request a new inventory job."
                )
            blockers = execution_blockers(config, job.provider_mode)
            if blockers:
                raise AutomationBlocked(" ".join(blockers))
            systems = [] if job.provider_mode == "mock" else run_inventory(config)
            _, revision = resolve_target(session, job.device_id)
            if revision != job.target_revision or profile_revision() != job.profile_revision:
                raise AutomationBlocked("Target changed during inventory; results were discarded.")
            if execution_blockers(config, job.provider_mode):
                raise AutomationBlocked("Execution policy changed; results were discarded.")
            result.status = "completed"
            result.systems = systems
            result.summary = (
                "Mock job completed. No hardware was contacted and no inventory is proven."
                if job.provider_mode == "mock"
                else "Read-only system inventory completed."
            )
    except AutomationBlocked as exc:
        result.summary = str(exc)
    except Exception:
        # Provider exceptions can contain secrets; only bounded, deliberate
        # messages cross the worker/result boundary.
        result.status = "failed"
        result.summary = "Inventory worker failed. Check worker configuration and device access."
    result.checked_at = datetime.now(UTC).isoformat()
    with SessionLocal() as session:
        session.add(
            AuditEvent(
                actor=job.actor,
                event_type="automation.inventory.finished",
                to_status=result.status,
                message=result.summary,
                data_json={
                    "device_id": job.device_id,
                    "source": result.source,
                    "job_id": running_job.id if running_job else None,
                },
            )
        )
        session.commit()
    return result.model_dump()
