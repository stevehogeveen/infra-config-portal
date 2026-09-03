from __future__ import annotations

import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.json_file_store import read_json_object, write_json_object
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[4]
STORE_ENV = "TOPOLOGY_DESIGN_DRAFT_STORE"
SCENARIOS = {
    "server_netapp_vcenter",
    "server_netapp_direct",
    "single_server_local_storage",
}
SLOTS = ("u1", "u2", "u3", "u4", "virtual")
LANES = ("management", "storage", "virtualization")
CONNECTIONS = ("switch-server", "switch-netapp", "server-netapp", "server-vm")
PARTS = {
    "switch",
    "ilo",
    "server-gen10",
    "server-gen10plus",
    "netapp",
    "vcenter",
    "windows",
}
VM_PARTS = {"vcenter", "windows"}
DEVICE_SETTING_KEYS = {
    "access_state",
    "datastore",
    "credential_state",
    "firmware",
    "gateway",
    "acl_lanes",
    "blackhole_vlan",
    "bpdu_guard",
    "controller_ports",
    "drive_bays",
    "iscsi_lifs",
    "management_ip",
    "mgmt_vlan",
    "name",
    "nfs_lifs",
    "notes",
    "power_state",
    "port_profiles",
    "ports",
    "protocol",
    "raid_boot",
    "raid_controller",
    "raid_data",
    "reachability",
    "role",
    "safe_checks",
    "san_ports",
    "storage_vlan",
    "vm_network",
}
LANE_SETTING_KEYS = {
    "mtu",
    "notes",
    "protocol",
    "purpose",
    "source",
    "target",
    "vlan",
}
CONNECTION_SETTING_KEYS = {
    "lane",
    "mtu",
    "notes",
    "protocol",
    "source",
    "status",
    "target",
    "vlan",
}


class TopologyDesignDraftError(Exception):
    pass


def get_topology_design_draft(profile_id: str, scenario: str, subnet: str | None = None) -> dict[str, Any]:
    scenario = _normalize_scenario(scenario)
    profile_id = _normalize_profile_id(profile_id)
    subnet = _normalize_subnet(subnet)
    store = _read_store()
    key = _draft_key(profile_id, scenario, subnet)
    existing = _drafts(store).get(key)
    if isinstance(existing, dict):
        return _draft_read(existing, source="saved")
    return _draft_read(
        {
            "profile_id": profile_id,
            "scenario": scenario,
            "subnet": subnet,
            "placements": _default_placements(scenario),
            "device_settings": _default_device_settings(scenario, subnet),
            "lane_settings": _default_lane_settings(scenario),
            "connection_settings": _default_connection_settings(scenario),
        },
        source="default",
    )


def save_topology_design_draft(payload: dict[str, Any]) -> dict[str, Any]:
    profile_id = _normalize_profile_id(payload.get("profile_id"))
    scenario = _normalize_scenario(payload.get("scenario"))
    subnet = _normalize_subnet(payload.get("subnet"))
    placements = _normalize_placements(payload.get("placements"), scenario)
    device_settings = _normalize_device_settings(payload.get("device_settings"), scenario, subnet)
    lane_settings = _normalize_lane_settings(payload.get("lane_settings"), scenario)
    connection_settings = _normalize_connection_settings(payload.get("connection_settings"), scenario)
    store = _read_store()
    key = _draft_key(profile_id, scenario, subnet)
    now = _now()
    draft = {
        "id": key,
        "profile_id": profile_id,
        "scenario": scenario,
        "subnet": subnet,
        "placements": placements,
        "device_settings": device_settings,
        "lane_settings": lane_settings,
        "connection_settings": connection_settings,
        "updated_at": now,
        "hardware_touched": False,
    }
    store.setdefault("drafts", {})[key] = draft
    _write_store(store)
    return _draft_read(draft, source="saved")


def topology_design_persistence_inventory() -> list[dict[str, str]]:
    return [
        {
            "choice": "scenario",
            "persists_to": "topology design draft store",
            "commit_state": "draft_only",
            "hardware_effect": "none",
        },
        {
            "choice": "rack placements",
            "persists_to": "topology design draft store",
            "commit_state": "draft_only",
            "hardware_effect": "none",
        },
        {
            "choice": "device editor intent",
            "persists_to": "topology design draft store",
            "commit_state": "draft_only",
            "hardware_effect": "none",
        },
        {
            "choice": "network and storage lane intent",
            "persists_to": "topology design draft store",
            "commit_state": "draft_only",
            "hardware_effect": "none",
        },
        {
            "choice": "visual connection intent",
            "persists_to": "topology design draft store",
            "commit_state": "draft_only",
            "hardware_effect": "none",
        },
        {
            "choice": "device addresses, subnet, VLAN, protocol",
            "persists_to": "lab profile",
            "commit_state": "committed_profile",
            "hardware_effect": "none until guarded workflow apply",
        },
        {
            "choice": "live port, LED, datastore, and VM state",
            "persists_to": "provider evidence artifacts",
            "commit_state": "observed_only",
            "hardware_effect": "read-only probes unless guarded apply is explicitly run",
        },
    ]


def _draft_read(draft: dict[str, Any], *, source: str) -> dict[str, Any]:
    scenario = _normalize_scenario(draft.get("scenario"))
    profile_id = _normalize_profile_id(draft.get("profile_id"))
    subnet = _normalize_subnet(draft.get("subnet"))
    return {
        "id": _draft_key(profile_id, scenario, subnet),
        "profile_id": profile_id,
        "scenario": scenario,
        "subnet": subnet,
        "placements": _normalize_placements(draft.get("placements"), scenario),
        "device_settings": _normalize_device_settings(draft.get("device_settings"), scenario, subnet),
        "lane_settings": _normalize_lane_settings(draft.get("lane_settings"), scenario),
        "connection_settings": _normalize_connection_settings(draft.get("connection_settings"), scenario),
        "source": source,
        "draft_saved": source == "saved",
        "hardware_touched": False,
        "updated_at": draft.get("updated_at"),
        "store_path": display_path(_store_path(), REPO_ROOT),
        "message": (
            "Topology design draft loaded from persistent store."
            if source == "saved"
            else "Topology design draft is using scenario defaults until saved."
        ),
        "persistence_inventory": topology_design_persistence_inventory(),
    }


def _normalize_device_settings(value: Any, scenario: str, subnet: str | None) -> dict[str, dict[str, str]]:
    defaults = _default_device_settings(scenario, subnet)
    if not isinstance(value, dict):
        return defaults
    normalized: dict[str, dict[str, str]] = deepcopy(defaults)
    for raw_part, raw_settings in value.items():
        part = str(raw_part).strip()
        if part not in PARTS or not _part_allowed_in_scenario(part, scenario) or not isinstance(raw_settings, dict):
            continue
        current = normalized.setdefault(part, {})
        for raw_key, raw_value in raw_settings.items():
            key = str(raw_key).strip()
            if key not in DEVICE_SETTING_KEYS or raw_value is None:
                continue
            text = str(raw_value).strip()
            if not text:
                continue
            current[key] = text[:240 if key == "notes" else 160]
    return normalized


def _normalize_lane_settings(value: Any, scenario: str) -> dict[str, dict[str, str]]:
    defaults = _default_lane_settings(scenario)
    if not isinstance(value, dict):
        return defaults
    normalized: dict[str, dict[str, str]] = deepcopy(defaults)
    for raw_lane, raw_settings in value.items():
        lane = str(raw_lane).strip()
        if lane not in LANES or not isinstance(raw_settings, dict):
            continue
        current = normalized.setdefault(lane, {})
        for raw_key, raw_value in raw_settings.items():
            key = str(raw_key).strip()
            if key not in LANE_SETTING_KEYS or raw_value is None:
                continue
            text = str(raw_value).strip()
            if text:
                current[key] = text[:240 if key == "notes" else 160]
    if scenario == "single_server_local_storage":
        normalized["storage"]["protocol"] = "local datastore"
        normalized["storage"]["target"] = "server-local RAID datastore"
    return normalized


def _normalize_connection_settings(value: Any, scenario: str) -> dict[str, dict[str, str]]:
    defaults = _default_connection_settings(scenario)
    if not isinstance(value, dict):
        return defaults
    normalized: dict[str, dict[str, str]] = deepcopy(defaults)
    for raw_connection, raw_settings in value.items():
        connection = str(raw_connection).strip()
        if connection not in CONNECTIONS or connection not in defaults or not isinstance(raw_settings, dict):
            continue
        current = normalized.setdefault(connection, {})
        for raw_key, raw_value in raw_settings.items():
            key = str(raw_key).strip()
            if key not in CONNECTION_SETTING_KEYS or raw_value is None:
                continue
            text = str(raw_value).strip()
            if text:
                current[key] = text[:240 if key == "notes" else 160]
    return normalized


def _default_lane_settings(scenario: str) -> dict[str, dict[str, str]]:
    storage_protocol = "local datastore" if scenario == "single_server_local_storage" else "NFS primary / iSCSI optional"
    storage_target = "server-local RAID datastore" if scenario == "single_server_local_storage" else "NetApp SVM datastore LIFs"
    return {
        "management": {
            "purpose": "Device access and control plane",
            "source": "Operator workstation / Cisco",
            "target": "iLO, ESXi, NetApp, vCenter",
            "vlan": "100",
            "mtu": "1500",
            "protocol": "HTTPS, SSH, Redfish, ONTAP REST",
        },
        "storage": {
            "purpose": "VM datastore traffic",
            "source": "ESXi vmkernel",
            "target": storage_target,
            "vlan": "220",
            "mtu": "9000",
            "protocol": storage_protocol,
        },
        "virtualization": {
            "purpose": "Inventory, templates, and VM handoff",
            "source": "ESXi / vCenter",
            "target": "VM networks and datastore inventory",
            "vlan": "100",
            "mtu": "1500",
            "protocol": "vSphere API, VM networks",
        },
    }


def _default_connection_settings(scenario: str) -> dict[str, dict[str, str]]:
    connections: dict[str, dict[str, str]] = {
        "switch-server": {
            "source": "Cisco C9300",
            "target": "ESXi host vmnic/iLO",
            "lane": "management",
            "vlan": "100",
            "mtu": "1500",
            "protocol": "management + vmkernel",
            "status": "planned",
        },
        "server-vm": {
            "source": "ESXi host",
            "target": "VM inventory",
            "lane": "virtualization",
            "vlan": "100",
            "mtu": "1500",
            "protocol": "vSphere API / VM network",
            "status": "planned",
        },
    }
    if scenario != "single_server_local_storage":
        connections["switch-netapp"] = {
            "source": "Cisco C9300",
            "target": "NetApp e0a/e0b",
            "lane": "storage",
            "vlan": "220",
            "mtu": "9000",
            "protocol": "NFS / iSCSI VLANs",
            "status": "planned",
        }
        connections["server-netapp"] = {
            "source": "ESXi vmkernel",
            "target": "NetApp datastore LIFs",
            "lane": "storage",
            "vlan": "220",
            "mtu": "9000",
            "protocol": "datastore path",
            "status": "planned",
        }
    return connections


def _default_device_settings(scenario: str, subnet: str | None) -> dict[str, dict[str, str]]:
    base = subnet.split("/", 1)[0].rsplit(".", 1)[0] if subnet and "." in subnet else "192.168.1"
    settings: dict[str, dict[str, str]] = {
        "switch": {
            "name": "Cisco C9300",
            "management_ip": f"{base}.204",
            "mgmt_vlan": "100",
            "storage_vlan": "220",
            "ports": "uplinks, server mgmt, NetApp e0a/e0b",
            "bpdu_guard": "enabled on edge access ports",
            "blackhole_vlan": "999",
            "acl_lanes": "MGMT-IN, STORAGE-NFS-IN, DROP-ALL",
            "port_profiles": "trunk uplinks, access mgmt, storage VLAN tagged",
            "san_ports": "storage ports tagged for NFS/iSCSI",
        },
        "ilo": {
            "name": "HPE iLO",
            "management_ip": f"{base}.201",
            "credential_state": "unknown until iLO Auth Live Check runs",
            "reachability": "unknown until iLO Live Check runs",
            "firmware": "read by iLO Inventory",
            "power_state": "read-only inventory only",
            "notes": "No power, firmware flash, virtual media, RAID, or reset action is exposed here.",
        },
        "server-gen10": {
            "name": "HPE DL360 Gen10",
            "management_ip": f"{base}.203",
            "drive_bays": "discover with iLO / Smart Array",
            "raid_controller": "Smart Array discovered",
            "raid_boot": "RAID1",
            "raid_data": "RAID6 or local datastore by scenario",
            "ports": "iLO, ESXi management, storage vmkernel",
        },
        "server-gen10plus": {
            "name": "HPE DL360 Gen10+",
            "management_ip": f"{base}.203",
            "drive_bays": "discover with iLO / Smart Array",
            "raid_controller": "Smart Array discovered",
            "raid_boot": "RAID1",
            "raid_data": "RAID6 or local datastore by scenario",
            "ports": "iLO, ESXi management, storage vmkernel",
        },
        "vcenter": {
            "name": "vCenter VCSA",
            "management_ip": f"{base}.205",
            "datastore": "validated datastore",
            "role": "inventory, portability, templates",
        },
        "windows": {
            "name": "Windows Server",
            "vm_network": "management or workload VLAN",
            "role": "guest workload",
        },
    }
    if scenario != "single_server_local_storage":
        settings["netapp"] = {
            "name": "NetApp ONTAP",
            "management_ip": f"{base}.220",
            "protocol": "NFS primary, iSCSI optional",
            "nfs_lifs": f"{base}.230, {base}.231",
            "iscsi_lifs": f"{base}.232, {base}.233",
            "controller_ports": "e0a/e0b on both controllers",
            "ports": "e0a/e0b per controller to Cisco storage VLAN",
        }
    return settings


def _part_allowed_in_scenario(part: str, scenario: str) -> bool:
    return not (part == "netapp" and scenario == "single_server_local_storage")


def _normalize_placements(value: Any, scenario: str) -> dict[str, str | None]:
    if not isinstance(value, dict):
        value = {}
    next_placements: dict[str, str | None] = {slot: None for slot in SLOTS}
    seen: set[str] = set()
    for slot in SLOTS:
        raw = value.get(slot)
        part = str(raw).strip() if raw is not None else None
        if part and part in PARTS and _can_place(part, slot, scenario) and part not in seen:
            next_placements[slot] = part
            seen.add(part)
        elif raw is None:
            next_placements[slot] = None
    for slot, fallback in _default_placements(scenario).items():
        if not next_placements[slot] and fallback and fallback not in seen:
            next_placements[slot] = fallback
            seen.add(fallback)
    return next_placements


def _default_placements(scenario: str) -> dict[str, str | None]:
    return {
        "u1": "switch",
        "u2": "server-gen10",
        "u3": None if scenario == "single_server_local_storage" else "netapp",
        "u4": None,
        "virtual": "vcenter" if scenario == "server_netapp_vcenter" else None,
    }


def _can_place(part: str, slot: str, scenario: str) -> bool:
    if part in VM_PARTS:
        return slot == "virtual"
    if slot == "virtual":
        return False
    if part == "ilo":
        return slot == "u1"
    if part == "netapp":
        return scenario != "single_server_local_storage" and slot == "u3"
    return True


def _normalize_scenario(value: Any) -> str:
    scenario = str(value or "").strip().lower()
    if scenario not in SCENARIOS:
        raise TopologyDesignDraftError("scenario must be a supported topology design scenario")
    return scenario


def _normalize_profile_id(value: Any) -> str:
    profile_id = str(value or "runtime").strip()
    if not profile_id or len(profile_id) > 120 or not re.match(r"^[A-Za-z0-9_.:-]+$", profile_id):
        raise TopologyDesignDraftError("profile_id must be a simple profile identifier")
    return profile_id


def _normalize_subnet(value: Any) -> str | None:
    if value is None:
        return None
    subnet = str(value).strip()
    if not subnet:
        return None
    if len(subnet) > 80:
        raise TopologyDesignDraftError("subnet is too long")
    return subnet


def _draft_key(profile_id: str, scenario: str, subnet: str | None) -> str:
    raw = f"{profile_id}:{scenario}:{subnet or 'no-subnet'}"
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw)


def _read_store() -> dict[str, Any]:
    payload = read_json_object(_store_path())
    drafts = payload.get("drafts") if isinstance(payload, dict) else {}
    return {"drafts": drafts if isinstance(drafts, dict) else {}}


def _write_store(store: dict[str, Any]) -> None:
    write_json_object(_store_path(), redact_sensitive(store))


def _drafts(store: dict[str, Any]) -> dict[str, Any]:
    drafts = store.get("drafts")
    return deepcopy(drafts) if isinstance(drafts, dict) else {}


def _store_path() -> Path:
    configured = os.getenv(STORE_ENV)
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "topology-design-drafts.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()
