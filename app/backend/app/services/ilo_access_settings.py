from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DeviceInventory, IloDeviceCredential
from app.providers.ilo_redfish import IloRedfishConfig, ilo_target_fingerprint
from app.providers.probe_cache import get_probe_result
from app.services.env_utils import bool_value
from app.services.status_source import status_source_metadata

PROVIDER_ID = "ilo-redfish"


class IloAccessSettingsError(ValueError):
    pass


class IloDeviceNotFoundError(LookupError):
    pass


def is_ilo_device_type(device_type: str | None) -> bool:
    """Match the operator-facing device-type rule used by the rack UI.

    Inventory device types are free text, so an operator adding a board can
    save "HPE ILO", "ilo", or "bmc". The rack normalizes any of those to an
    iLO; an exact "ilo" comparison here would show the iLO panel and then
    reject every request it makes.
    """
    normalized = re.sub(r"[^a-z0-9]+", "_", (device_type or "").casefold())
    return "ilo" in normalized.split("_") or "bmc" in normalized.split("_")


def ilo_device_ids(session: Session) -> list[str]:
    return [
        device.id
        for device in session.scalars(
            select(DeviceInventory).order_by(DeviceInventory.id)
        )
        if is_ilo_device_type(device.device_type)
    ]


def require_ilo_device(session: Session, device_id: str) -> DeviceInventory:
    device = session.get(DeviceInventory, device_id)
    if device is None:
        raise IloDeviceNotFoundError(device_id)
    if not is_ilo_device_type(device.device_type):
        raise IloAccessSettingsError("The selected inventory device is not an iLO device.")
    return device


def resolve_ilo_device_id(session: Session, device_id: str | None) -> str:
    if device_id:
        return require_ilo_device(session, device_id).id
    device_ids = ilo_device_ids(session)
    if not device_ids:
        # Production startup seeds before this path. Test clients and older
        # direct ASGI integrations may skip lifespan, so retain the historical
        # single-iLO behavior without inventing a global credential record.
        from app.services.device_inventory import seed_legacy_devices

        seed_legacy_devices(session)
        device_ids = ilo_device_ids(session)
    if not device_ids:
        raise IloAccessSettingsError("No iLO inventory device is configured.")
    if len(device_ids) > 1:
        raise IloAccessSettingsError("device_id is required when more than one iLO device exists.")
    return device_ids[0]


def read_ilo_access_settings(session: Session, device_id: str) -> dict[str, Any]:
    device = require_ilo_device(session, device_id)
    record = session.get(IloDeviceCredential, device_id)
    credentials = _credentials(record)
    credential_host = _clean_optional(credentials.get("host"))
    host = credential_host or _clean_optional(device.host)
    host_source = "device_credentials" if credential_host else "device_inventory"
    username = _clean_optional(credentials.get("username"))
    password = _clean_optional(credentials.get("password"))
    verify_tls = bool_value(credentials.get("verify_tls"), default=True)
    config = _config(
        host=host,
        username=username,
        password=password,
        verify_tls=verify_tls,
        host_source=host_source,
    )
    return {
        "device_id": device_id,
        "provider_id": PROVIDER_ID,
        "host": host,
        "host_source": host_source,
        "fallback_hosts": [],
        "username": username,
        "username_configured": bool(username),
        "password_configured": bool(password),
        "verify_tls": verify_tls,
        "updated_at": record.updated_at.isoformat() if record is not None else None,
        **_last_probe_summary(host, config),
        "next_safe_action": _next_safe_action(config),
    }


def read_unique_ilo_access_settings(session: Session) -> dict[str, Any]:
    device_ids = list(session.scalars(select(IloDeviceCredential.device_id).order_by(IloDeviceCredential.device_id)))
    if not device_ids:
        raise IloAccessSettingsError("No saved iLO device credentials are configured.")
    if len(device_ids) > 1:
        raise IloAccessSettingsError("Select an iLO device before reading its access settings.")
    return read_ilo_access_settings(session, device_ids[0])


def update_ilo_access_settings(
    session: Session,
    device_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    device = require_ilo_device(session, device_id)
    record = session.get(IloDeviceCredential, device_id)
    credentials = _credentials(record)
    updates: dict[str, Any] = {}

    for field in ("host", "username", "password"):
        if field not in payload:
            continue
        value = _clean_optional(payload.get(field))
        if value:
            updates[field] = value
    if "verify_tls" in payload and payload.get("verify_tls") is not None:
        updates["verify_tls"] = bool_value(payload.get("verify_tls"), default=True)

    if not updates:
        raise IloAccessSettingsError("No iLO access settings were provided.")

    next_credentials = {
        "host": _clean_optional(credentials.get("host")) or _clean_optional(device.host),
        "username": _clean_optional(credentials.get("username")),
        "password": _clean_optional(credentials.get("password")),
        "verify_tls": bool_value(credentials.get("verify_tls"), default=True),
        **updates,
    }
    if record is None:
        record = IloDeviceCredential(
            device_id=device_id,
            credentials_json=next_credentials,
        )
        session.add(record)
    else:
        record.credentials_json = next_credentials

    if "host" in updates:
        device.host = updates["host"]

    try:
        session.commit()
        session.refresh(record)
    except SQLAlchemyError:
        session.rollback()
        # SQLAlchemy exception representations can contain bound parameters.
        # Convert failures at this boundary so a password is never echoed by
        # the API or normal application logs.
        raise IloAccessSettingsError("Could not save iLO access settings locally.") from None

    readback = read_ilo_access_settings(session, device_id)
    return {
        **readback,
        "next_safe_action": (
            "iLO access settings saved locally. Run iLO Inventory Read to prove "
            "reachability before trusting the map."
        ),
    }


def ilo_config_for_device(session: Session, device_id: str) -> IloRedfishConfig:
    device = require_ilo_device(session, device_id)
    record = session.get(IloDeviceCredential, device_id)
    credentials = _credentials(record)
    credential_host = _clean_optional(credentials.get("host"))
    return _config(
        host=credential_host or _clean_optional(device.host),
        username=_clean_optional(credentials.get("username")),
        password=_clean_optional(credentials.get("password")),
        verify_tls=bool_value(credentials.get("verify_tls"), default=True),
        host_source="device_credentials" if credential_host else "device_inventory",
    )


def ilo_config_for_target(
    session: Session,
    host: str,
    *,
    device_id: str | None = None,
) -> IloRedfishConfig:
    requested_fingerprint = ilo_target_fingerprint(host)
    if requested_fingerprint is None:
        raise IloAccessSettingsError("An explicit current-access ilo_host IP is required.")

    if device_id:
        config = ilo_config_for_device(session, device_id)
        if ilo_target_fingerprint(config.host) != requested_fingerprint:
            raise IloAccessSettingsError(
                "The requested ilo_host does not match the selected device's saved credential host."
            )
        return config

    matches: list[IloDeviceCredential] = []
    for record in session.scalars(select(IloDeviceCredential)):
        saved_host = _clean_optional(_credentials(record).get("host"))
        if saved_host and ilo_target_fingerprint(saved_host) == requested_fingerprint:
            matches.append(record)
    if not matches:
        raise IloAccessSettingsError("No saved iLO device credentials match the requested ilo_host.")
    if len(matches) > 1:
        raise IloAccessSettingsError(
            "More than one iLO device credential matches the requested ilo_host; provide device_id."
        )
    return ilo_config_for_device(session, matches[0].device_id)


def _credentials(record: IloDeviceCredential | None) -> dict[str, Any]:
    if record is None or not isinstance(record.credentials_json, dict):
        return {}
    return dict(record.credentials_json)


def _config(
    *,
    host: str | None,
    username: str | None,
    password: str | None,
    verify_tls: bool,
    host_source: str,
) -> IloRedfishConfig:
    return IloRedfishConfig(
        host=host,
        username=username,
        password=password,
        verify_tls=verify_tls,
        timeout_seconds=settings.ilo_test_timeout_seconds,
        host_source=host_source,
        fallback_hosts=(),
        fallback_host_sources=(),
    )


def _next_safe_action(config: IloRedfishConfig) -> str:
    if config.configured:
        return "Run iLO Inventory Read to refresh live iLO reachability and storage inventory."
    if not config.target_candidates:
        return "Enter the iLO IP or initial iLO IP, then save credentials locally."
    if not config.username or not config.password:
        return "Enter the iLO username/UID and password, then save credentials locally."
    return "Review iLO access settings, then run iLO Inventory Read."


def _last_probe_summary(host: str | None, config: IloRedfishConfig) -> dict[str, Any]:
    result, checked_at = get_probe_result(PROVIDER_ID)
    if not isinstance(result, dict):
        return {
            "last_probe_status": "not_checked",
            "last_probe_time": None,
            "last_probe_freshness": "not_checked",
            "last_probe_is_current": False,
            "last_probe_message": None,
            "last_probe_target_source": None,
            "last_probe_target_matches_access_host": False,
            "last_probe_target_matches_configured_candidates": False,
            "last_probe_target_fingerprint_present": False,
        }
    source_metadata = status_source_metadata(
        source_type="live_cached",
        checked_at=checked_at,
    )
    target_fingerprint = _clean_optional(result.get("target_fingerprint"))
    candidate_fingerprints = {
        fingerprint
        for candidate in config.target_candidates
        if (fingerprint := ilo_target_fingerprint(candidate.get("host")))
    }
    target_matches_access_host = bool(
        target_fingerprint
        and host
        and target_fingerprint == ilo_target_fingerprint(host)
    )
    return {
        "last_probe_status": _clean_optional(result.get("status")) or "unknown",
        "last_probe_time": checked_at,
        "last_probe_freshness": source_metadata["freshness"],
        "last_probe_is_current": bool(
            source_metadata["is_current"] and target_matches_access_host
        ),
        "last_probe_message": _clean_optional(result.get("message")),
        "last_probe_target_source": _clean_optional(result.get("target_source")),
        "last_probe_target_matches_access_host": target_matches_access_host,
        "last_probe_target_matches_configured_candidates": bool(
            target_fingerprint and target_fingerprint in candidate_fingerprints
        ),
        "last_probe_target_fingerprint_present": bool(target_fingerprint),
    }


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
