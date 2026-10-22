"""Pre-flight: one pass over saved data and this PC before the first hardware change.

Never contacts equipment. Each item says ok, warn or fail, why, and which page fixes it.
"""

from __future__ import annotations

import ipaddress
import shutil
import socket
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

FRESH = timedelta(hours=24)


def _item(group: str, name: str, state: str, detail: str, fix: str | None = None) -> dict[str, Any]:
    return {"group": group, "name": name, "state": state, "detail": detail, "fix": fix}


def _age_ok(stamp: str | None) -> bool:
    if not stamp:
        return False
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return False
    when = when if when.tzinfo else when.replace(tzinfo=UTC)
    return datetime.now(UTC) - when <= FRESH


def run(session: Session, profile_id: str, *, bridge_port: int = 7091) -> dict[str, Any]:
    from app.api.rack_plans import get_plan
    from app.services import esxi_install, switch_access, windows_deploy
    from app.services.firmware_packages import media_root, package_unchanged
    from app.services.ilo_access_settings import read_ilo_access_settings
    from app.services.lab_profiles import active_lab_profile_context
    from app.services.runtime_write_scope import state as scope_state

    items: list[dict[str, Any]] = []
    plan = get_plan(profile_id, session)
    servers = [item for item in plan.equipment if item.kind == "server" and item.device_id]
    switches = [item for item in plan.equipment if item.kind == "switch" and item.device_id]
    from app.api.rack_plans import kit_profile

    profile = kit_profile(profile_id)
    context = active_lab_profile_context()
    if (context.get("active_profile") or {}).get("id") == profile_id:
        kit = esxi_install._kit(context)
    else:
        # Not the open kit: read its own saved network, never the open kit's.
        settings = profile.get("global_settings") or {}
        kit = {"subnet": profile.get("subnet_cidr"), "gateway": settings.get("gateway") or profile.get("gateway")}
    addresses: dict[str, list[str]] = {}

    def note_address(value: str | None, owner: str) -> None:
        if value:
            addresses.setdefault(str(value).strip(), []).append(owner)

    # Plan
    items.append(_item("Plan", "Rack layout", "ok" if plan.equipment else "fail",
                       f"{len(plan.equipment)} piece{'s' if len(plan.equipment) != 1 else ''} of equipment" if plan.equipment else "No equipment yet",
                       None if plan.equipment else "/setup/guide"))
    subnet = None
    try:
        subnet = ipaddress.ip_network(str(kit["subnet"]), strict=False) if kit.get("subnet") else None
    except ValueError:
        subnet = None
    items.append(_item("Plan", "Network settings", "ok" if subnet and kit.get("gateway") else "fail",
                       f"{subnet} via {kit.get('gateway')}" if subnet else "Management network not saved", None if subnet else "/setup/defaults"))
    note_address(kit.get("gateway"), "gateway")

    # Servers
    for server in servers:
        try:
            access = read_ilo_access_settings(session, server.device_id)
        except Exception:  # noqa: BLE001 - a missing record is a failed item, not a crash
            access = {}
        signed = bool(access.get("host") and access.get("username_configured") and access.get("password_configured"))
        items.append(_item(server.name, "iLO sign-in", "ok" if signed else "fail",
                           f"iLO {access.get('host')}" if signed else "Address or sign-in not saved", None if signed else f"/setup/connect?device={server.device_id}"))
        note_address(access.get("host"), f"{server.name} iLO")
        fresh = access.get("last_probe_status") == "ok" and access.get("last_probe_is_current") and _age_ok(access.get("last_probe_time"))
        items.append(_item(server.name, "Connection check", "ok" if fresh else "warn",
                           "Answered within the last day" if fresh else "No check in the last day; use Check connections on My Rack", None if fresh else "/simple"))
        esxi = esxi_install.get_settings(session, profile_id, server.device_id)
        media = esxi_install.list_media(session, profile_id, server.device_id)
        selected = media.get("selected")
        items.append(_item(server.name, "ESXi installer", "ok" if selected and selected.get("present") else "warn",
                           selected["name"] if selected and selected.get("present") else ("Chosen installer is missing or changed" if selected else "No installer chosen"),
                           None if selected and selected.get("present") else f"/setup/prepare-esxi?device={server.device_id}"))
        saved = bool(esxi.get("saved_at") and esxi.get("password_set"))
        items.append(_item(server.name, "ESXi host settings", "ok" if saved else "warn",
                           f"{esxi.get('hostname')} · {esxi.get('addressing')}" if saved else "Host name, address or root password not saved",
                           None if saved else f"/setup/prepare-esxi?device={server.device_id}"))
        if esxi.get("addressing") == "static" and esxi.get("management_ip"):
            note_address(esxi["management_ip"], f"{server.name} ESXi")
            try:
                inside = subnet is not None and ipaddress.ip_address(esxi["management_ip"]) in subnet
            except ValueError:
                inside = False
            if not inside:
                items.append(_item(server.name, "ESXi address", "fail", f"{esxi['management_ip']} is outside {subnet}", f"/setup/prepare-esxi?device={server.device_id}"))
        windows = windows_deploy._latest(session, "kit.windows.settings", profile_id=profile_id, device_id=server.device_id)
        image = (windows.data_json or {}).get("image") if windows else None
        present = bool(image) and any(item["path"] == image for item in windows_deploy.list_images())
        items.append(_item(server.name, "Windows image", "ok" if present else "warn",
                           image if present else ("Chosen image is missing" if image else "No image chosen"),
                           None if present else f"/setup/install-windows?device={server.device_id}"))
        package = windows_deploy._latest(session, "kit.firmware_package_selected", profile_id=profile_id)
        if package and isinstance((package.data_json or {}).get("package"), dict) and (package.data_json["package"].get("path")):
            unchanged = package_unchanged(package.data_json["package"])
            items.append(_item(server.name, "Firmware package", "ok" if unchanged else "warn",
                               package.data_json["package"].get("file_name") or package.data_json["package"]["path"] if unchanged else "Chosen package is missing or changed",
                               None if unchanged else "/setup/check-firmware"))

    # Switches
    for switch in switches:
        access = switch_access.read_access(session, switch.device_id)
        console = access.get("console") or {}
        items.append(_item(switch.name, "Console port", "ok" if console.get("port") else "warn",
                           f"{console['port']} at {console.get('baud')}" if console.get("port") else "Not read on its console cable yet", None if console.get("port") else f"/setup/connect?device={switch.device_id}"))
        signed = bool(access.get("host") and access.get("password_configured"))
        items.append(_item(switch.name, "Switch sign-in", "ok" if signed else "warn",
                           f"Mgmt {access['host']}" if signed else "Not set up yet", None if signed else f"/setup/connect?device={switch.device_id}"))
        note_address(access.get("host"), f"{switch.name} mgmt")
        try:
            outside = bool(access.get("host")) and subnet is not None and ipaddress.ip_address(access["host"]) not in subnet
        except ValueError:
            outside = False
        if outside:
            items.append(_item(switch.name, "Switch address", "warn", f"{access['host']} is outside the kit network {subnet}; fine only if the switch is managed on another network",
                               f"/setup/connect?device={switch.device_id}"))

    # Addresses
    clashes = {address: owners for address, owners in addresses.items() if len(set(owners)) > 1}
    items.append(_item("Addresses", "No clashes", "fail" if clashes else "ok",
                       "; ".join(f"{address} is used by {', '.join(sorted(set(owners)))}" for address, owners in clashes.items()) if clashes
                       else f"{len(addresses)} address{'es' if len(addresses) != 1 else ''} checked", None))

    # This PC
    try:
        free = shutil.disk_usage(media_root()).free
        items.append(_item("This PC", "Free disk space", "ok" if free >= 20 * 1024**3 else "warn", f"{free / 1024**3:.0f} GB free for media"))
    except OSError:
        items.append(_item("This PC", "Media folder", "fail", "The media folder is missing"))
    items.append(_item("This PC", "govc (ESXi tool)", "ok" if shutil.which("govc") else "fail",
                       "Available" if shutil.which("govc") else "Not found; ESXi and Windows steps cannot run"))
    try:
        with socket.create_connection(("127.0.0.1", bridge_port), timeout=1):
            bridge = True
    except OSError:
        bridge = False
    if switches:
        items.append(_item("This PC", "Console helper", "ok" if bridge else "warn",
                           "Running" if bridge else "Not running; start-lab-builder.cmd starts it"))
    scope = scope_state(session)
    calm = scope.get("scope") == "read_only" and not scope.get("active_operations")
    items.append(_item("This PC", "Nothing half-done", "ok" if calm else "warn",
                       "Read-only mode, no job running" if calm else "A job is running or changes are still allowed; see the bell", None if calm else "/simple"))

    worst = "fail" if any(i["state"] == "fail" for i in items) else "warn" if any(i["state"] == "warn" for i in items) else "ok"
    return {"state": worst, "checked_at": datetime.now(UTC).isoformat(), "items": items}
