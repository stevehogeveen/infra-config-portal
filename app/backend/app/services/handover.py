"""Hand-over pack: everything a kit's next owner needs, from stored data only.

Never contacts equipment; never includes passwords. Every value says where it came from
(saved plan, last check with its time, or verified run with its time).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session


def switch_config(session: Session, device_id: str) -> dict | None:
    """The switch's running configuration as recorded by the app's last successful first setup (secrets were masked at read time)."""
    import difflib

    from sqlalchemy import select

    from app.models import AuditEvent

    runs = {row.data_json.get("run_id"): row for row in session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch.run").order_by(AuditEvent.created_at.desc()).limit(50))
            if row.data_json.get("device_id") == device_id}
    for row in session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch.result").order_by(AuditEvent.created_at.desc()).limit(200)):
        data = row.data_json or {}
        if data.get("phase") != "configure" or data.get("run_id") not in runs or not (data.get("config_after") or data.get("config_before")):
            continue
        from app.providers.cisco_console_setup import sanitize_config

        before, after = sanitize_config(data.get("config_before") or ""), sanitize_config(data.get("config_after") or "")  # masked again on the way out
        diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), "before setup", "after setup", lineterm="", n=1))
        at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
        return {"before": before or None, "after": after or None, "diff": diff, "at": at.isoformat(), "outcome": data.get("outcome")}
    return None


def _verified_at(session: Session, event_type: str, device_id: str) -> str | None:
    from sqlalchemy import select

    from app.models import AuditEvent

    for row in session.scalars(select(AuditEvent).where(AuditEvent.event_type == event_type).order_by(AuditEvent.created_at.desc()).limit(200)):
        data = row.data_json or {}
        if data.get("outcome") == "verified" and (data.get("device_id") in (None, device_id)):
            at = row.created_at if row.created_at.tzinfo else row.created_at.replace(tzinfo=UTC)
            return at.isoformat()
    return None


def build(session: Session, profile_id: str) -> dict[str, Any]:
    from app.api.kit_jobs import health_summary
    from app.api.rack_plans import get_plan, kit_profile
    from app.providers.probe_cache import get_probe_result
    from app.services import acceptance, cable_map, esxi_install, switch_access, windows_deploy
    from app.services.ilo_access_settings import read_ilo_access_settings
    from app.services.lab_profiles import active_lab_profile_context

    profile = kit_profile(profile_id)
    plan = get_plan(profile_id, session)
    kit = esxi_install._kit(active_lab_profile_context()) if (active_lab_profile_context().get("active_profile") or {}).get("id") == profile_id else {}
    servers, switches = [], []
    for item in plan.equipment:
        if item.kind == "server" and item.device_id:
            try:
                access = read_ilo_access_settings(session, item.device_id)
            except Exception:  # noqa: BLE001
                access = {}
            probe, probe_at = get_probe_result("ilo-redfish", scope=item.device_id)
            system = ((probe or {}).get("systems") or [{}])[0] if isinstance(probe, dict) else {}
            esxi = esxi_install.install_status(session, profile_id, item.device_id)
            esxi_settings = esxi_install.get_settings(session, profile_id, item.device_id)
            windows = windows_deploy.status(session, profile_id, item.device_id)
            test = acceptance.status(session, profile_id, item.device_id)
            servers.append({
                "name": item.name,
                "model": system.get("Model") or item.model,
                "observed_at": probe_at if system.get("Model") else None,
                "ilo": {"address": access.get("host"), "firmware": access.get("observed_ilo_firmware"),
                        "bios": access.get("observed_bios_version"), "checked_at": access.get("last_probe_time")},
                "health": health_summary(probe if isinstance(probe, dict) else None),
                "boot_disks": esxi_settings.get("boot_volume"), "data_disks": esxi_settings.get("data_volume"),
                "esxi": {"state": esxi.get("state"), "host_name": esxi_settings.get("hostname"), "address": esxi.get("management_ip"),
                         "datastore": esxi.get("datastore"), "verified_at": esxi.get("verified_at")},
                "windows": {"state": windows.get("state"), "vm": windows.get("vm_name"), "address": windows.get("address"),
                            "computer": windows.get("hostname"), "os": windows.get("guest_os"),
                            "verified_at": _verified_at(session, "kit.windows.done", item.device_id)},
                "acceptance": {"state": test["state"], "finished_at": test.get("finished_at"), "lookup": test.get("lookup")},
            })
        elif item.kind == "switch" and item.device_id:
            access = switch_access.read_access(session, item.device_id)
            check = access.get("last_check") or {}
            switches.append({"name": item.name, "address": access.get("host"), "username": access.get("username"),
                             "model": check.get("model") or item.model, "software": check.get("version"), "serial": check.get("serial"),
                             "checked_at": check.get("checked_at"), "check_status": check.get("status"), "console": (access.get("console") or {}).get("port"),
                             "config": switch_config(session, item.device_id)})
    history = []
    from app.api.build_history import build_history

    for row in build_history(limit=400, session=session):
        if row["outcome"] == "ok" and row["area"] in {"Firmware", "Disks & RAID", "ESXi", "Windows", "Switch"}:
            history.append(row)
    latest: dict[str, dict[str, Any]] = {}
    for row in history:
        latest.setdefault(row["area"], row)
    return {
        "kit": profile.get("name"), "generated_at": datetime.now(UTC).isoformat(),
        "network": {"subnet": kit.get("subnet") or profile.get("subnet_cidr"), "gateway": kit.get("gateway") or profile.get("gateway"),
                    "dns": kit.get("dns") or profile.get("dns"), "domain": kit.get("domain_name")},
        "servers": servers, "switches": switches, "cables": cable_map.last(profile_id),
        "verified": list(latest.values()),
    }
