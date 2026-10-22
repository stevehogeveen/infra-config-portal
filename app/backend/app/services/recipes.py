"""Kit recipes: save a kit's design as a file and start a new kit from it ("build it again").

A recipe holds the shared network design, the rack layout and each server's and switch's
chosen settings (ESXi host settings, installer, Windows image and VM settings, switch first-setup
settings, firmware package). It never holds passwords, device identities, addresses read from
hardware, or evidence: a new kit starts unverified and asks for every password again.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

FORMAT = "lab-builder-recipe/1"
# Design-only allowlists: nothing that identifies a device (names, addresses) or could hold a secret.
NETWORK_KEYS = ("subnet_cidr", "gateway", "dns", "ntp", "vlan_id", "mtu")
GLOBAL_KEYS = ("dns_servers", "ntp_servers", "domain_name", "timezone", "gateway")
FEATURE_KEYS = ("enable_dns", "enable_ntp", "enable_snmp", "deployment_mode", "storage_location", "block_legacy_protocols", "disable_ipv6")
RACK_KEYS = ("kind", "name", "model", "position", "height", "mount", "ports", "uplink_ports", "bay_count", "occupied_bays")
ESXI_KEYS = ("addressing", "vlan_id", "datastore_name")
WINDOWS_KEYS = ("image", "vm_name", "datastore", "network")
SWITCH_KEYS = ("domain", "vlan", "mode", "prefix", "save", "uplink", "uplink_mode")
INSTALLER_KEYS = ("path", "name", "size_bytes")
PACKAGE_KEYS = ("path", "source_root", "file_name", "size_bytes", "modified_ns", "kind")
SECRET_WORDS = ("password", "secret", "token", "key", "community")


class RecipeError(ValueError):
    pass


def _plain(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return not (isinstance(value, str) and ("://" in value and "@" in value))
    if isinstance(value, list):
        return all(isinstance(item, (str, int, float, bool)) for item in value)
    return False


def _pick(source: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Only the listed keys, only plain values (no nested objects, no URLs with credentials)."""
    if not isinstance(source, dict):
        return {}
    return {key: deepcopy(source[key]) for key in keys if key in source and _plain(source[key])}


def _no_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _no_secrets(v) for k, v in value.items() if not any(word in k.lower() for word in SECRET_WORDS)}
    if isinstance(value, list):
        return [_no_secrets(v) for v in value]
    return value


def export(session: Session, profile_id: str) -> dict[str, Any]:
    from app.api.rack_plans import get_plan, kit_profile
    from app.services import esxi_install, switch_access, windows_deploy

    source = kit_profile(profile_id)
    plan = get_plan(profile_id, session)
    servers, switches = [], []
    for item in plan.equipment:
        if item.kind == "server" and item.device_id:
            esxi = esxi_install._latest(session, "kit.esxi_settings_saved", profile_id=profile_id, device_id=item.device_id)
            media = esxi_install._latest(session, "kit.esxi_media_selected", profile_id=profile_id, device_id=item.device_id)
            windows = windows_deploy._latest(session, "kit.windows.settings", profile_id=profile_id, device_id=item.device_id)
            servers.append({
                "esxi": _pick(esxi.data_json, ESXI_KEYS) if esxi else None,
                "esxi_installer": _pick(media.data_json, INSTALLER_KEYS) if media else None,
                "windows": _pick(windows.data_json, WINDOWS_KEYS) if windows else None,
            })
        elif item.kind == "switch" and item.device_id:
            saved = switch_access._saved(session.get(switch_access.SwitchDeviceCredential, item.device_id))
            setup = saved.get("setup") if isinstance(saved.get("setup"), dict) else None
            switches.append({"setup": _pick(setup, SWITCH_KEYS) if setup else None, "username": saved.get("username") if _plain(saved.get("username")) else None})
    package = esxi_install._latest(session, "kit.firmware_package_selected", profile_id=profile_id)
    layout = plan.model_dump()
    network = _pick(source, NETWORK_KEYS)
    network["global_settings"] = _pick(source.get("global_settings"), GLOBAL_KEYS)
    network["features"] = _pick(source.get("features"), FEATURE_KEYS)
    return {
        "format": FORMAT, "name": source.get("name"), "saved_at": datetime.now(UTC).isoformat(),
        "network": network,
        "rack": {"rack_units": layout.get("rack_units"), "equipment": [_pick(item, RACK_KEYS) for item in layout.get("equipment", [])]},
        "servers": servers, "switches": switches,
        "firmware_package": _pick((package.data_json or {}).get("package"), PACKAGE_KEYS) if package else None,
    }


def apply(session: Session, recipe: dict[str, Any], name: str, actor: str) -> dict[str, Any]:
    """Create a new kit from a recipe. Returns the new kit and what still needs doing."""
    from app.api.rack_plans import RackPlan, save_plan
    from app.schemas import LabProfileWrite
    from app.services.audit import record_audit_event
    from app.services.lab_profiles import create_lab_profile
    from app.services.switch_access import SwitchDeviceCredential

    if not isinstance(recipe, dict) or recipe.get("format") != FORMAT:
        raise RecipeError("This file is not a Lab Builder recipe.")
    source_network = recipe.get("network") if isinstance(recipe.get("network"), dict) else {}
    network = _pick(source_network, NETWORK_KEYS)
    network["global_settings"] = _pick(source_network.get("global_settings"), GLOBAL_KEYS)
    network["features"] = _pick(source_network.get("features"), FEATURE_KEYS)
    try:
        profile = LabProfileWrite(name=name, profile_topology="custom", **network)
    except Exception:
        raise RecipeError("The recipe's network settings are not valid.") from None
    kit = create_lab_profile(profile.model_dump(), activate=False)
    rack = recipe.get("rack") or {}
    equipment = []
    for item in rack.get("equipment") or []:
        equipment.append({**_pick(item, RACK_KEYS), "id": str(uuid4()), "device_id": None})
    plan = RackPlan(revision=0, rack_units=rack.get("rack_units") or 12, equipment=equipment)
    saved = save_plan(plan, kit["id"], session, actor)
    saved_equipment = saved.equipment if hasattr(saved, "equipment") else saved["equipment"]

    def device_of(item) -> str | None:
        return item.device_id if hasattr(item, "device_id") else item.get("device_id")

    def kind_of(item) -> str:
        return item.kind if hasattr(item, "kind") else item.get("kind")

    servers = [item for item in saved_equipment if kind_of(item) == "server"]
    switches = [item for item in saved_equipment if kind_of(item) == "switch"]
    todo: list[str] = []
    for item, settings in zip(servers, recipe.get("servers") or []):
        device_id = device_of(item)
        if not isinstance(settings, dict):
            continue
        installer = _pick(settings.get("esxi_installer"), INSTALLER_KEYS)
        if installer.get("path"):
            record_audit_event(session, actor=actor, event_type="kit.esxi_media_selected", message="ESXi installer chosen from a recipe.",
                               data={**installer, "profile_id": kit["id"], "device_id": device_id})
        esxi = _pick(settings.get("esxi"), ESXI_KEYS)
        if esxi:
            # Host name and fixed address identify a host: never copied; entered for this kit.
            record_audit_event(session, actor=actor, event_type="kit.esxi_settings_saved",
                               message="ESXi host settings from a recipe; host name, address and root password still needed.",
                               data={**esxi, "hostname": None, "management_ip": None, "management_nic": "vmnic0",
                                     "password_changed": False, "from_recipe": True, "profile_id": kit["id"], "device_id": device_id})
        windows = _pick(settings.get("windows"), WINDOWS_KEYS)
        if windows:
            record_audit_event(session, actor=actor, event_type="kit.windows.settings", message="Windows VM settings from a recipe.",
                               data={**windows, "profile_id": kit["id"], "device_id": device_id})
    for item, settings in zip(switches, recipe.get("switches") or []):
        if not isinstance(settings, dict):
            continue
        setup = _pick(settings.get("setup"), SWITCH_KEYS)
        if setup:
            setup.update(hostname=None, address=None, gateway=None if setup.get("mode") == "static" else setup.get("gateway"))
            username = settings.get("username") if isinstance(settings.get("username"), str) else None
            session.add(SwitchDeviceCredential(device_id=device_of(item), credentials_json={"setup": setup, "username": username}))
    package = _pick(recipe.get("firmware_package"), PACKAGE_KEYS)
    if package.get("path"):
        record_audit_event(session, actor=actor, event_type="kit.firmware_package_selected", message="Firmware package chosen from a recipe.",
                           data={"package": package, "profile_id": kit["id"]})
    session.commit()
    todo.append("Connect each server and the switch (addresses and sign-ins are never copied).")
    todo.append("Enter each ESXi host name (and fixed address, if used) and root password.")
    todo.append("Name the switch and enter its passwords.")
    return {"kit": kit, "todo": todo}
