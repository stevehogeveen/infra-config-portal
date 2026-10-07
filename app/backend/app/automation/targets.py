import hashlib
import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import IloDeviceCredential
from app.providers.action_policy import current_lab_action_policy
from app.services.ilo_access_settings import ilo_config_for_device
from app.services.lab_profiles import active_lab_profile_context, lab_profile_context_fingerprint


class AutomationBlocked(ValueError):
    pass


def profile_revision() -> str:
    context = active_lab_profile_context()
    profile = dict(context["active_profile"])
    if profile.get("source") == "runtime_env":
        # Runtime profiles are synthesized on every read; these timestamps
        # describe that read rather than a change in configuration.
        for key in ("created_at", "updated_at", "last_selected_at"):
            profile.pop(key, None)
    return lab_profile_context_fingerprint({**context, "active_profile": profile})


def resolve_target(session: Session, device_id: str):
    session.expire_all()
    config = ilo_config_for_device(session, device_id)
    credential = session.get(IloDeviceCredential, device_id)
    # Addresses are mutable. Bind queued work to the reviewed access revision,
    # then resolve credentials again in the worker; never serialize them to RQ.
    revision = hashlib.sha256(
        json.dumps(
            [
                device_id,
                config.host,
                config.username,
                config.verify_tls,
                str(credential.updated_at) if credential else None,
            ]
        ).encode()
    ).hexdigest()
    return config, revision


def execution_blockers(config, expected_mode: str) -> list[str]:
    if settings.provider_mode != expected_mode:
        return ["Provider mode changed after this job was requested."]
    if expected_mode == "mock":
        return []
    blockers = current_lab_action_policy(expected_mode).readonly_blockers()
    if not config.host:
        blockers.append("Save this device's current access address first.")
    if not config.username or not config.password:
        blockers.append("Save this device's access credentials first.")
    return blockers
