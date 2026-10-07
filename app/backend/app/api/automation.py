from fastapi import APIRouter, Depends, HTTPException
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.automation.contracts import InventoryRequest, InventoryRun
from app.automation.queue import enqueue_inventory, latest_inventory_run, read_inventory_run
from app.automation.targets import AutomationBlocked
from app.core.database import get_session
from app.services.ilo_access_settings import IloAccessSettingsError, IloDeviceNotFoundError

router = APIRouter(prefix="/api/v1/devices", tags=["automation"])


@router.post("/{device_id}/maintenance-diagnostics", status_code=202)
def create_maintenance_diagnostic(device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    from app.automation.ssa_diagnostics import load_target
    from app.automation.queue import inventory_queue
    from app.automation.targets import resolve_target, execution_blockers, profile_revision
    from app.core.config import settings
    from app.services.audit import record_audit_event
    try:
        config, revision = resolve_target(session, device_id)
        if settings.provider_mode == 'mock':
            raise AutomationBlocked('Maintenance diagnostics are disabled in mock mode. No hardware was contacted.')
        blockers = execution_blockers(config, settings.provider_mode)
        if blockers:
            raise AutomationBlocked(' '.join(blockers))
        _, _, _, maintenance_revision = load_target(device_id)
        payload = {'device_id': device_id, 'target_revision': revision,
                   'profile_revision': profile_revision(), 'provider_mode': settings.provider_mode,
                   'maintenance_revision': maintenance_revision}
        job = inventory_queue().enqueue('app.automation.ssa_diagnostics.execute_ssa', payload,
            job_timeout=300, ttl=300, result_ttl=3600, failure_ttl=3600,
            description='Read-only maintenance SSA diagnostic')
        record_audit_event(session, actor=actor, event_type='automation.ssa.queued',
                           message='Read-only maintenance diagnostics queued.',
                           data={'device_id': device_id, 'job_id': job.id})
        session.commit()
        return {'job_id': job.id, 'status': 'queued'}
    except (AutomationBlocked, IloAccessSettingsError, IloDeviceNotFoundError, RedisError) as exc:
        raise translate_error(exc) from None


@router.get("/{device_id}/maintenance-diagnostics/{job_id}")
def read_maintenance_diagnostic(device_id: str, job_id: str, session: Session = Depends(get_session)):
    from app.automation.queue import inventory_queue
    from app.automation.targets import resolve_target, profile_revision, execution_blockers
    from app.automation.ssa_diagnostics import load_target
    try:
        job = inventory_queue().fetch_job(job_id)
        if not job or job.func_name != 'app.automation.ssa_diagnostics.execute_ssa' or job.args[0].get('device_id') != device_id:
            raise LookupError()
        payload = job.args[0]
        config, revision = resolve_target(session, device_id)
        if (revision != payload['target_revision'] or profile_revision() != payload['profile_revision']
                or load_target(device_id)[3] != payload['maintenance_revision']
                or execution_blockers(config, payload['provider_mode'])):
            raise AutomationBlocked('Target or access policy changed. Request new maintenance diagnostics.')
        status = job.get_status(refresh=True).value
        return {'job_id': job.id, 'status': status, 'result': job.return_value() if status == 'finished' else None}
    except (AutomationBlocked, IloAccessSettingsError, LookupError, RedisError) as exc:
        raise translate_error(exc) from None


def translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (LookupError, IloDeviceNotFoundError)):
        return HTTPException(404, "Device or inventory job was not found.")
    if isinstance(exc, RedisError):
        return HTTPException(503, "Automation queue is unavailable.")
    return HTTPException(409, str(exc))


@router.post("/{device_id}/inventory-jobs", response_model=InventoryRun, status_code=202)
def create_inventory_job(
    device_id: str,
    payload: InventoryRequest,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    try:
        return enqueue_inventory(session, device_id, actor)
    except (AutomationBlocked, IloAccessSettingsError, IloDeviceNotFoundError, RedisError) as exc:
        raise translate_error(exc) from None


@router.get("/{device_id}/inventory-jobs/{job_id}", response_model=InventoryRun)
def get_inventory_job(device_id: str, job_id: str, session: Session = Depends(get_session)):
    try:
        return read_inventory_run(session, device_id, job_id)
    except (AutomationBlocked, IloAccessSettingsError, LookupError, RedisError) as exc:
        raise translate_error(exc) from None


@router.get("/{device_id}/inventory-jobs", response_model=InventoryRun | None)
def get_latest_inventory_job(device_id: str, session: Session = Depends(get_session)):
    try:
        return latest_inventory_run(session, device_id)
    except (AutomationBlocked, IloAccessSettingsError, LookupError, RedisError) as exc:
        raise translate_error(exc) from None
