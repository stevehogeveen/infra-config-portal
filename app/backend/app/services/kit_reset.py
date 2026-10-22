"""Reset for the next person: what each reset step erases, and forgetting the kit's saved sign-ins.

The page lists the kit's equipment from stored records only (no equipment contact). Erasing is
done by the existing guarded flows: the disk wipe (delete RAID + secure erase, Disks & RAID) and
the switch reset (services/switch_reset.py). Forgetting sign-ins only deletes this PC's saved
ESXi, Windows and switch passwords for this kit; the iLO sign-in stays (the server keeps its iLO).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GuardedOperation, SwitchDeviceCredential
from app.services.audit import record_audit_event

FORGET_PHRASE = "FORGET SIGN-INS"


class KitResetError(RuntimeError):
    pass


def _kit(session: Session, profile_id: str):
    from app.api.rack_plans import get_plan

    plan = get_plan(profile_id, session)
    servers = [item for item in plan.equipment if item.kind == "server" and item.device_id]
    switches = [item for item in plan.equipment if item.kind == "switch" and item.device_id]
    return servers, switches


def _server_secrets(device_id: str) -> list[tuple[str, Any]]:
    from app.services import acceptance, esxi_install

    return [("ESXi root password", esxi_install._root_password_path(device_id)),
            ("ESXi root password (installer copy)", esxi_install._secret_path(device_id)),
            ("Windows administrator sign-in", acceptance._signin_path(device_id))]


def summary(session: Session, profile_id: str) -> dict[str, Any]:
    from app.services import esxi_install, switch_reset, windows_deploy

    servers, switches = _kit(session, profile_id)
    out_servers = []
    for item in servers:
        settings = esxi_install.get_settings(session, profile_id, item.device_id)
        esxi = esxi_install.install_status(session, profile_id, item.device_id)
        windows = windows_deploy.status(session, profile_id, item.device_id)
        erases = []
        if settings.get("boot_volume") or settings.get("data_volume"):
            erases.append("Every RAID volume on its disks")
        if esxi.get("state") == "verified":
            erases.append(f"ESXi ({esxi.get('management_ip') or 'installed'}) and its datastore")
        if windows.get("vm_name"):
            erases.append(f"The Windows VM {windows['vm_name']}")
        erases.append("Then each disk is securely erased (can take hours)")
        out_servers.append({"device_id": item.device_id, "name": item.name, "model": item.model, "erases": erases,
                            "signins": [label for label, path in _server_secrets(item.device_id) if path.is_file()]})
    out_switches = []
    for item in switches:
        saved = _switch_saved(session, item.device_id)
        out_switches.append({"device_id": item.device_id, "name": item.name, "model": item.model,
                             "console_port": saved.get("console_port"), "erases": switch_reset.ERASES,
                             "reset": switch_reset.status(session, profile_id, item.device_id),
                             "signins": [label for key, label in (("password", "Switch admin password"), ("enable_password", "Switch enable password")) if saved.get(key)]})
    return {"enabled": switch_reset.enabled(), "forget_phrase": FORGET_PHRASE, "servers": out_servers, "switches": out_switches}


def _switch_saved(session: Session, device_id: str) -> dict[str, Any]:
    from app.services import switch_access

    return switch_access._saved(session.get(SwitchDeviceCredential, device_id))


def forget(session: Session, profile_id: str, actor: str, confirmation: str) -> dict[str, Any]:
    from app.services import switch_reset

    if not switch_reset.enabled():
        raise KitResetError("Reset is turned off for this lab (LAB_ALLOW_FACTORY_RESET is not true).")
    if confirmation != FORGET_PHRASE:
        raise KitResetError(f"Type {FORGET_PHRASE} exactly.")
    servers, switches = _kit(session, profile_id)
    devices = [item.device_id for item in servers + switches]
    busy = session.scalar(select(GuardedOperation).where(GuardedOperation.active_device.in_(devices)).limit(1))
    if busy:
        raise KitResetError(f"Finish or close the running {busy.resource} first.")
    removed: list[str] = []
    for item in servers:
        for label, path in _server_secrets(item.device_id):
            if path.is_file():
                path.unlink()
                removed.append(f"{item.name}: {label}")
    for item in switches:
        record = session.get(SwitchDeviceCredential, item.device_id)
        if record is None or not isinstance(record.credentials_json, dict):
            continue
        kept = {key: value for key, value in record.credentials_json.items() if key not in {"password", "enable_password"}}
        gone = [key for key in ("password", "enable_password") if record.credentials_json.get(key)]
        if gone:
            record.credentials_json = kept
            removed += [f"{item.name}: {'switch admin password' if key == 'password' else 'switch enable password'}" for key in gone]
    record_audit_event(session, actor=actor, event_type="kit.reset.forget", message=f"Forgot {len(removed)} saved sign-ins for this kit.",
                       data={"profile_id": profile_id, "removed": removed})
    session.commit()
    return {"removed": removed, **summary(session, profile_id)}
