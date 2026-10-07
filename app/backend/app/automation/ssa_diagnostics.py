"""Worker-only, read-only SSA execution; no caller-provided commands or variables."""
import hashlib
import ipaddress
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.automation.ansible_inventory import PROJECT, run_inventory
from app.automation.targets import AutomationBlocked, execution_blockers, profile_revision, resolve_target
from app.core.config import settings
from app.core.database import SessionLocal

ROOT = Path(__file__).resolve().parents[4] / '.local' / 'maintenance'


class MaintenanceTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(pattern=r'^[a-z_][a-z0-9_-]{0,31}$')

    @field_validator('host')
    @classmethod
    def literal_address(cls, value):
        return str(ipaddress.ip_address(value))


def load_target(device_id):
    try:
        directory = ROOT / str(UUID(device_id))
        raw = (directory / 'target.json').read_bytes()
        target = MaintenanceTarget.model_validate_json(raw)
        key = (directory / 'ssh_key').read_bytes()
        known = (directory / 'known_hosts').read_bytes()
        if not key.strip() or not known.strip():
            raise ValueError()
        revision = hashlib.sha256(raw + b'\0' + key + b'\0' + known).hexdigest()
        return target, key, known, revision
    except (OSError, ValueError, ValidationError):
        raise AutomationBlocked('Enroll this server\'s maintenance SSH address, private key and verified known_hosts file first. No server action was sent.') from None


def run_ssa(target, key, known, serial):
    import ansible_runner

    if not serial or not re.fullmatch(r'[A-Za-z0-9._ -]{1,100}', serial) or not serial.strip():
        raise AutomationBlocked('Fresh iLO inventory did not provide a server serial number.')
    exported = {}

    def event_handler(event):
        data = event.get('event_data', {})
        if event.get('event') == 'runner_on_ok' and data.get('task') == 'Export SSA diagnostics':
            exported.update(data.get('res', {}).get('ansible_stats', {}).get('data', {}))
        return False

    with TemporaryDirectory(prefix='ssa-read-') as directory:
        private = Path(directory)
        os.chmod(private, 0o700)
        for name, content in [('key', key), ('known_hosts', known)]:
            path = private / name
            path.write_bytes(content)
            os.chmod(path, 0o600)
        result = ansible_runner.run(
            private_data_dir=directory, project_dir=str(PROJECT),
            playbook='playbooks/ssa_diagnostics.yml', quiet=True,
            inventory={'all': {'hosts': {'maintenance': {
                'ansible_host': target.host, 'ansible_port': target.port,
                'ansible_user': target.username, 'ansible_connection': 'ssh',
                'ansible_python_interpreter': '/usr/bin/python3',
                'ansible_private_key_file': str(private / 'key'),
                'ansible_ssh_common_args': '-o StrictHostKeyChecking=yes -o BatchMode=yes -o IdentitiesOnly=yes -o UserKnownHostsFile=' + str(private / 'known_hosts'),
            }}}}, extravars={'expected_serial': serial.strip()},
            event_handler=event_handler,
            settings={'job_timeout': 120, 'suppress_ansible_output': True},
            envvars={'ANSIBLE_HOST_KEY_CHECKING': 'True', 'ANSIBLE_LOG_PATH': os.devnull,
                     'ANSIBLE_SSH_CONTROL_PATH_DIR': str(private / 'cp'),
                     'ANSIBLE_LOCAL_TEMP': str(private / 'local'), 'ANSIBLE_REMOTE_TEMP': '/tmp/lab-builder-ansible'},
        )
        if result.rc != 0 or result.status != 'successful':
            raise AutomationBlocked('Maintenance diagnostic failed. Check SSH host key, access, maintenance marker, matching server serial, and /usr/sbin/ssacli. No storage changes were requested.')
    reports = exported.get('reports')
    if exported.get('identity_verified') is not True or not isinstance(reports, list) or len(reports) != 2 or not all(isinstance(r, str) and r.strip() for r in reports):
        raise AutomationBlocked('SSA did not return complete, identity-verified diagnostics.')
    if any(len(r) > 65536 for r in reports):
        raise AutomationBlocked('SSA report exceeded the diagnostic size limit; no incomplete result will be treated as proof.')
    return reports


def execute_ssa(payload):
    from datetime import UTC, datetime
    result = {'status': 'blocked', 'reports': [], 'message': 'Maintenance diagnostics did not run.'}
    try:
        with SessionLocal() as session:
            config, _ = resolve_target(session, payload['device_id'])
            target, key, known, _ = load_target(payload['device_id'])
            def valid():
                return (resolve_target(session, payload['device_id'])[1] == payload['target_revision']
                        and profile_revision() == payload['profile_revision']
                        and load_target(payload['device_id'])[3] == payload['maintenance_revision']
                        and not execution_blockers(config, payload['provider_mode']))
            if settings.provider_mode == 'mock' or not valid():
                raise AutomationBlocked('Maintenance diagnostics require explicitly enabled read-only hardware access and unchanged target settings.')
            systems = run_inventory(config)
            if len(systems) != 1 or not systems[0].serial_number or not valid():
                raise AutomationBlocked('Fresh iLO identity is missing, ambiguous, or changed.')
            reports = run_ssa(target, key, known, systems[0].serial_number)
            if not valid():
                raise AutomationBlocked('Target settings changed during diagnostics; results were discarded.')
            result = {'status': 'completed', 'reports': reports,
                      'message': 'Read-only SSA diagnostics completed on the identity-matched maintenance host. This is not rebuild approval.'}
    except AutomationBlocked as exc:
        result['message'] = str(exc)
    except Exception:
        result['message'] = 'Maintenance diagnostics failed. Check worker configuration; no storage changes were requested.'
    result['checked_at'] = datetime.now(UTC).isoformat()
    from app.services.audit import record_audit_event
    from rq import get_current_job
    job = get_current_job()
    with SessionLocal() as session:
        record_audit_event(session, actor='automation-worker', event_type='automation.ssa.finished',
            message=result['message'], data={'device_id':payload['device_id'],
            'job_id':job.id if job else None, 'status':result['status']})
        session.commit()
    return result
