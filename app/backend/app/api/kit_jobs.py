"""What is running, what stopped, what just finished; and "find this exact box".

GET  /api/v1/jobs                    - running guarded jobs with elapsed time, ones that need
                                       attention, and ones that finished in the last two days.
                                       Database only; never contacts hardware.
POST /api/v1/devices/{id}/identify   - turn the server's blue ID light on (blinking) or off and
                                       read its serial number. The only change is the indicator
                                       LED; it is recorded in the run history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.database import get_session
from app.models import DeviceInventory, GuardedOperation
from app.services.audit import record_audit_event

router = APIRouter(prefix="/api/v1", tags=["jobs"])

LABELS = {
    "firmware-execution": ("Firmware update", "/setup/check-firmware"),
    "parts-update": ("Firmware update", "/setup/check-firmware"),
    "drive-return-to-service": ("Disk work", "/setup/disks"),
    "esxi-install": ("ESXi install", "/setup/prepare-esxi"),
    "windows-deploy": ("Windows deploy", "/setup/install-windows"),
    "switch-setup": ("Switch setup", "/setup/connect"),
    "acceptance-test": ("Acceptance test", "/setup/install-windows"),
    "switch-reset": ("Switch reset", "/reset"),
}
ATTENTION = ("uncertain", "failed", "needs", "timeout", "refused", "stopped")
RECENT = timedelta(days=2)
DONE = {"verified", "completed", "succeeded"}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _row(op: GuardedOperation, names: dict[str, str]) -> dict[str, Any]:
    label, path = LABELS.get(op.resource, (op.resource.replace("-", " ").capitalize(), "/setup/history"))
    started, updated = _aware(op.created_at), _aware(op.updated_at)
    status = (op.status or "").lower()
    if op.active_device:
        state = "needs_attention" if any(word in status for word in ATTENTION) else "running"
    else:
        state = "done" if status in DONE else "stopped"
    return {"id": op.id, "resource": op.resource, "label": label, "device_id": op.device_id,
            "device_name": names.get(op.device_id, "equipment"), "state": state, "status": op.status,
            "started_at": started.isoformat(), "updated_at": updated.isoformat(),
            "path": f"{path}?device={op.device_id}"}


@router.get("/jobs")
def jobs(session: Session = Depends(get_session)):
    names = {device.id: device.display_name for device in session.scalars(select(DeviceInventory))}
    since = datetime.now(UTC) - RECENT
    active = [_row(op, names) for op in session.scalars(select(GuardedOperation).where(GuardedOperation.active_device.is_not(None)))]
    finished = session.scalars(select(GuardedOperation).where(GuardedOperation.active_device.is_(None))
                               .order_by(GuardedOperation.updated_at.desc()).limit(50))
    recent = [_row(op, names) for op in finished if _aware(op.updated_at) >= since]
    return {"running": [job for job in active if job["state"] == "running"],
            "attention": [job for job in active if job["state"] == "needs_attention"],
            "recent": recent[:20], "now": datetime.now(UTC).isoformat()}


class IdentifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on: bool


@router.post("/devices/{device_id}/identify")
def identify(device_id: str, payload: IdentifyRequest, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    from app.core.config import settings
    from app.providers.action_policy import current_lab_action_policy
    from app.providers.ilo_redfish import _base_url
    from app.services.ilo_access_settings import IloAccessSettingsError, IloDeviceNotFoundError, ilo_config_for_device

    try:
        config = ilo_config_for_device(session, device_id)
    except IloDeviceNotFoundError:
        raise HTTPException(404, "Device not found") from None
    except IloAccessSettingsError as exc:
        raise HTTPException(409, str(exc)) from None
    if not config.host or not config.username or not config.password:
        raise HTTPException(409, "Save this server's iLO address and sign-in first (Connect equipment).")
    from app.providers.action_policy import LOCAL_LAB_READWRITE_MODE

    policy = current_lab_action_policy(settings.provider_mode)
    if settings.provider_mode != LOCAL_LAB_READWRITE_MODE or not policy.local_lab_acknowledged:
        raise HTTPException(409, "Changing anything on the server, even the ID light, needs the lab's read-write mode.")
    base = _base_url(config.host)
    wanted = "Blinking" if payload.on else "Off"
    record_audit_event(session, actor=actor, event_type="kit.identify.attempt",
                       message=f"ID light {'on' if payload.on else 'off'} requested.", data={"device_id": device_id})
    session.commit()
    sent = False
    try:
        with httpx.Client(auth=(config.username, config.password), timeout=httpx.Timeout(config.timeout_seconds),
                          trust_env=False, verify=config.verify_tls, follow_redirects=False) as client:
            system = client.get(base + "/redfish/v1/Systems/1/")
            system.raise_for_status()
            body = system.json()
            sent = True
            result = client.patch(base + "/redfish/v1/Systems/1/", json={"IndicatorLED": wanted},
                                  headers={"If-Match": system.headers.get("ETag", "*")})
            if result.status_code >= 400 and payload.on:
                # Older firmware lights it steadily instead of blinking.
                wanted = "Lit"
                result = client.patch(base + "/redfish/v1/Systems/1/", json={"IndicatorLED": wanted},
                                      headers={"If-Match": system.headers.get("ETag", "*")})
            if result.status_code >= 400:
                record_audit_event(session, actor=actor, event_type="kit.identify.failed",
                                   message=f"The iLO refused the ID light change (HTTP {result.status_code}).", data={"device_id": device_id})
                session.commit()
                raise HTTPException(409, f"The iLO refused the ID light change (HTTP {result.status_code}).")
            try:
                after = client.get(base + "/redfish/v1/Systems/1/").json()
                indicator = after.get("IndicatorLED")
            except (httpx.HTTPError, ValueError):
                indicator = None  # sent and accepted, but not read back
    except httpx.HTTPError as exc:
        if sent:
            record_audit_event(session, actor=actor, event_type="kit.identify.failed",
                               message=f"The ID light change was sent but its answer was lost ({exc.__class__.__name__}).", data={"device_id": device_id})
            session.commit()
        raise HTTPException(409, f"The iLO did not answer ({exc.__class__.__name__}).") from None
    record_audit_event(session, actor=actor, event_type="kit.identify.applied",
                       message=f"ID light turned {'on' if payload.on else 'off'} on {body.get('Model') or 'the server'}"
                               + ("." if indicator else " (accepted; not read back)."),
                       data={"device_id": device_id, "indicator": indicator})
    session.commit()
    return {"indicator": indicator, "serial": body.get("SerialNumber"), "model": body.get("Model")}


@router.get("/devices/{device_id}/identity")
def identity(device_id: str, session: Session = Depends(get_session)):
    """Read-only: the server's model, serial number and ID light state from its iLO."""
    from app.core.config import settings
    from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
    from app.providers.ilo_redfish import _base_url
    from app.services.ilo_access_settings import IloAccessSettingsError, IloDeviceNotFoundError, ilo_config_for_device

    try:
        config = ilo_config_for_device(session, device_id)
    except IloDeviceNotFoundError:
        raise HTTPException(404, "Device not found") from None
    except IloAccessSettingsError as exc:
        raise HTTPException(409, str(exc)) from None
    if not config.host or not config.username or not config.password:
        raise HTTPException(409, "Save this server's iLO address and sign-in first (Connect equipment).")
    if settings.provider_mode not in REAL_CONTACT_MODES or not current_lab_action_policy(settings.provider_mode).readonly_allowed:
        raise HTTPException(409, "The app is not allowed to contact real equipment in this mode.")
    try:
        with httpx.Client(auth=(config.username, config.password), timeout=httpx.Timeout(config.timeout_seconds),
                          trust_env=False, verify=config.verify_tls, follow_redirects=False) as client:
            response = client.get(_base_url(config.host) + "/redfish/v1/Systems/1/")
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(409, f"The iLO did not answer ({exc.__class__.__name__}).") from None
    return {"indicator": body.get("IndicatorLED"), "serial": body.get("SerialNumber"), "model": body.get("Model"), "ilo_host": config.host}


def health_summary(probe: dict[str, Any] | None) -> dict[str, Any] | None:
    """Temperatures, fans and power supplies from a stored iLO read, for the rack view."""
    if not isinstance(probe, dict) or probe.get("status") != "ok":
        return None
    temps = [t for block in probe.get("thermal") or [] for t in block.get("Temperatures") or []
             if isinstance(t.get("ReadingCelsius"), (int, float)) and t.get("ReadingCelsius") > 0]
    fans = [f for block in probe.get("thermal") or [] for f in block.get("Fans") or []]
    supplies = [p for block in probe.get("power") or [] for p in block.get("PowerSupplies") or []]

    def ok(item: dict[str, Any]) -> bool:
        status = item.get("Status") or {}
        return status.get("State") in (None, "Enabled") and status.get("Health") in (None, "OK")

    present = [f for f in fans if (f.get("Status") or {}).get("State") != "Absent"]
    psus = [p for p in supplies if (p.get("Status") or {}).get("State") != "Absent"]
    inlet = next((t for t in temps if "inlet" in str(t.get("Name", "")).lower() or t.get("PhysicalContext") == "Intake"), None)
    hottest = max(temps, key=lambda t: t["ReadingCelsius"], default=None)
    hot = [t for t in temps if isinstance(t.get("UpperThresholdCritical"), (int, float)) and t["ReadingCelsius"] >= t["UpperThresholdCritical"] - 5]
    system = (probe.get("systems") or [{}])[0] if probe.get("systems") else {}
    rollup = ((system.get("Status") or {}).get("HealthRollup") or (system.get("Status") or {}).get("Health"))
    problems = [f"{f.get('Name') or 'A fan'} is not OK" for f in present if not ok(f)]
    problems += [f"Power supply {p.get('Location') or p.get('MemberId') or ''} is not OK".replace("  ", " ") for p in psus if not ok(p)]
    problems += [f"{t.get('Name')} is {t['ReadingCelsius']}°C, near its limit" for t in hot]
    return {"checked_at": probe.get("checked_at"), "overall": rollup or ("Warning" if problems else "OK"),
            "inlet_c": inlet["ReadingCelsius"] if inlet else None,
            "hottest": {"name": hottest.get("Name"), "c": hottest["ReadingCelsius"]} if hottest else None,
            "fans_ok": sum(1 for f in present if ok(f)), "fans": len(present),
            "psu_ok": sum(1 for p in psus if ok(p)), "psus": len(psus), "problems": problems}


@router.get("/devices/{device_id}/health")
def health(device_id: str):
    """From the last stored server check only; never contacts the iLO."""
    from app.providers.probe_cache import get_probe_result

    probe, checked_at = get_probe_result("ilo-redfish", scope=device_id)
    summary = health_summary(probe)
    if summary is not None and not summary.get("checked_at"):
        summary["checked_at"] = checked_at
    return summary or {"overall": None, "problems": [], "checked_at": checked_at}


@router.get("/rack-plans/{profile_id}/preflight")
def preflight(profile_id: str, session: Session = Depends(get_session)):
    """One pass over saved data and this PC; never contacts equipment."""
    from app.api.rack_plans import kit_profile
    from app.services import preflight as service

    kit_profile(profile_id)
    return service.run(session, profile_id)


@router.get("/rack-plans/{profile_id}/cable-map")
def cable_map_last(profile_id: str):
    """The last cable map read (stored); never contacts equipment."""
    from app.services import cable_map

    return cable_map.last(profile_id) or {"state": "not_read", "cables": [], "unmatched_server_ports": [], "other_switch_ports": [], "problems": []}


@router.post("/rack-plans/{profile_id}/cable-map/read")
def cable_map_read(profile_id: str, session: Session = Depends(get_session)):
    """Read-only on click: server ports from the iLO, switch address table over SSH (show commands)."""
    from app.api.rack_plans import kit_profile
    from app.services import cable_map

    kit_profile(profile_id)
    return cable_map.read(session, profile_id)


@router.get("/rack-plans/{profile_id}/recipe")
def recipe_export(profile_id: str, session: Session = Depends(get_session)):
    """The kit's design as a recipe file (no passwords, no device identities, no evidence)."""
    from app.services import recipes

    return recipes.export(session, profile_id)


class RecipeApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    recipe: dict


@router.post("/recipes/apply")
def recipe_apply(payload: RecipeApply, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    """Start a new kit from a recipe; it opens unverified and asks for every password again."""
    from app.services import recipes

    try:
        return recipes.apply(session, payload.recipe, payload.name.strip() or "Kit from recipe", actor)
    except recipes.RecipeError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/rack-plans/{profile_id}/handover")
def handover(profile_id: str, session: Session = Depends(get_session)):
    """Everything the kit's next owner needs, from stored data only; no passwords."""
    from app.services import handover as service

    return service.build(session, profile_id)
