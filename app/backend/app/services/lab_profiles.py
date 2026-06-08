from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from ipaddress import IPv4Network, ip_network
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import (
    LAB_ANSIBLE_CONTROL_HOST_IP,
    LAB_CISCO_MANAGEMENT_IP,
    LAB_ESXI_MANAGEMENT_IP,
    LAB_ILO_IP,
    LAB_NETAPP_CLUSTER_MGMT_IP,
    LAB_NETAPP_CONTROLLER_A_SP_IP,
    LAB_NETAPP_CONTROLLER_B_SP_IP,
    LAB_NETAPP_ISCSI_LIF_IPS,
    LAB_NETAPP_NODE_A_MGMT_IP,
    LAB_NETAPP_NODE_B_MGMT_IP,
    LAB_NETAPP_SVM_MGMT_IP,
    LAB_SERVER_EMBEDDED_NIC_IP,
    LAB_SUBNET_CIDR,
    settings,
)
from app.providers.redaction import redact_sensitive

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNTIME_PROFILE_ID = "runtime"
SUBNET_PREFIX_OPTIONS = tuple(range(29, 22, -1))
NETAPP_MINIMUM_PREFIX = 24
NETAPP_DISABLED_REASON = (
    "NetApp capabilities require a /24 or larger lab subnet. "
    "They are disabled for /25 through /29 lab profiles."
)
LAB_BUILDER_CORE_OFFSETS = {
    "gateway": 1,
    "cisco_management": 2,
    "ansible_control_host": 5,
    "ilo": 200,
    "server_embedded_nic": 201,
    "esxi_management": 202,
}
COMPACT_CORE_OFFSETS = {
    "gateway": 1,
    "cisco_management": 2,
    "ilo": 3,
    "server_embedded_nic": 4,
    "esxi_management": 5,
    "ansible_control_host": 6,
}
LAB_BUILDER_NETAPP_OFFSETS = {
    "netapp_controller_a_sp": 13,
    "netapp_controller_b_sp": 14,
    "netapp_cluster_mgmt": 45,
    "netapp_node_a_mgmt": 46,
    "netapp_node_b_mgmt": 47,
    "netapp_svm_mgmt": 48,
}
LAB_BUILDER_NETAPP_ISCSI_OFFSETS = (49, 50, 51, 52)


class LabProfileError(Exception):
    pass


class LabProfileNotFoundError(LabProfileError):
    pass


def list_lab_profiles() -> dict[str, Any]:
    store = _read_store()
    profiles = _profiles_with_active_flag(store)
    active_profile = _active_profile(store, profiles)
    return {
        "active_profile": active_profile,
        "runtime_profile": _runtime_profile(active=active_profile["id"] == RUNTIME_PROFILE_ID),
        "profiles": profiles,
        "subnet_options": lab_subnet_options(),
        "store_path": _store_path_label(),
        "mock_only": True,
        "next_safe_action": (
            "Select a saved lab or create a new profile before running lab-specific planning."
        ),
    }


def create_lab_profile(payload: dict[str, Any]) -> dict[str, Any]:
    store = _read_store()
    now = _now()
    global_settings, address_plan = _normalize_profile_components(payload)
    profile = {
        "id": f"lab-{uuid4().hex[:12]}",
        "name": payload["name"],
        "description": payload.get("description") or "",
        "global_settings": global_settings,
        "address_plan": address_plan,
        "source": "saved",
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "last_selected_at": now,
        "history": [],
    }
    store["profiles"].append(profile)
    store["active_profile_id"] = profile["id"]
    _write_store(store)
    return _profile_read(profile, active=True)


def update_lab_profile(profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    store = _read_store()
    profile = _find_profile(store, profile_id)
    now = _now()
    profile.setdefault("history", []).append(
        {
            "version": profile.get("version", 1),
            "saved_at": profile.get("updated_at") or now,
            "name": profile.get("name", ""),
            "description": profile.get("description", ""),
            "global_settings": deepcopy(profile.get("global_settings") or {}),
            "address_plan": deepcopy(profile.get("address_plan") or {}),
        }
    )
    global_settings, address_plan = _normalize_profile_components(payload)
    profile["name"] = payload["name"]
    profile["description"] = payload.get("description") or ""
    profile["global_settings"] = global_settings
    profile["address_plan"] = address_plan
    profile["version"] = int(profile.get("version", 1)) + 1
    profile["updated_at"] = now
    _write_store(store)
    return _profile_read(profile, active=store.get("active_profile_id") == profile_id)


def activate_lab_profile(profile_id: str) -> dict[str, Any]:
    store = _read_store()
    if profile_id == RUNTIME_PROFILE_ID:
        store["active_profile_id"] = None
        _write_store(store)
        return list_lab_profiles()
    profile = _find_profile(store, profile_id)
    profile["last_selected_at"] = _now()
    store["active_profile_id"] = profile_id
    _write_store(store)
    return list_lab_profiles()


def get_active_saved_lab_profile() -> dict[str, Any] | None:
    store = _read_store()
    profile_id = store.get("active_profile_id")
    if not profile_id:
        return None
    try:
        return _profile_read(_find_profile(store, str(profile_id)), active=True)
    except LabProfileNotFoundError:
        return None


def active_lab_profile_for_report() -> dict[str, Any]:
    active = get_active_saved_lab_profile()
    if active:
        return active
    return _runtime_profile(active=True)


def lab_subnet_options() -> list[dict[str, Any]]:
    return [
        {
            "prefix": prefix,
            "cidr_suffix": f"/{prefix}",
            "label": f"/{prefix} ({_usable_hosts(prefix)} usable IPs)",
            "usable_hosts": _usable_hosts(prefix),
            "netapp_supported": _netapp_supported(prefix),
            "netapp_disabled_reason": None if _netapp_supported(prefix) else NETAPP_DISABLED_REASON,
        }
        for prefix in SUBNET_PREFIX_OPTIONS
    ]


def _store_path() -> Path:
    configured = os.getenv("LAB_PROFILE_STORE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "lab-profiles.json"


def _store_path_label() -> str:
    path = _store_path()
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _read_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"active_profile_id": None, "profiles": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active_profile_id": None, "profiles": []}
    profiles = payload.get("profiles") if isinstance(payload, dict) else []
    active_profile_id = payload.get("active_profile_id") if isinstance(payload, dict) else None
    return {
        "active_profile_id": active_profile_id,
        "profiles": profiles if isinstance(profiles, list) else [],
    }


def _write_store(store: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = redact_sensitive(store)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")


def _find_profile(store: dict[str, Any], profile_id: str) -> dict[str, Any]:
    for profile in store.get("profiles", []):
        if isinstance(profile, dict) and profile.get("id") == profile_id:
            return profile
    raise LabProfileNotFoundError("Lab profile not found")


def _profiles_with_active_flag(store: dict[str, Any]) -> list[dict[str, Any]]:
    active_id = store.get("active_profile_id")
    profiles = [
        _profile_read(profile, active=profile.get("id") == active_id)
        for profile in store.get("profiles", [])
        if isinstance(profile, dict)
    ]
    return sorted(
        profiles,
        key=lambda profile: profile.get("last_selected_at") or profile.get("updated_at") or "",
        reverse=True,
    )


def _active_profile(store: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    active_id = store.get("active_profile_id")
    if active_id:
        for profile in profiles:
            if profile["id"] == active_id:
                return profile
    return _runtime_profile(active=True)


def _profile_read(profile: dict[str, Any], *, active: bool) -> dict[str, Any]:
    global_settings, address_plan = _normalize_profile_components(profile)
    history = []
    for item in profile.get("history", []):
        if not isinstance(item, dict):
            continue
        revision_global_settings, revision_address_plan = _normalize_profile_components(item)
        history.append(
            {
                "version": int(item.get("version") or 1),
                "saved_at": item.get("saved_at") or _now(),
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "global_settings": revision_global_settings,
                "address_plan": revision_address_plan,
            }
        )
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or "Unnamed lab"),
        "description": str(profile.get("description") or ""),
        "global_settings": global_settings,
        "address_plan": address_plan,
        "source": str(profile.get("source") or "saved"),
        "version": int(profile.get("version") or 1),
        "active": active,
        "created_at": profile.get("created_at") or _now(),
        "updated_at": profile.get("updated_at") or _now(),
        "last_selected_at": profile.get("last_selected_at"),
        "history": history,
    }


def _runtime_profile(*, active: bool) -> dict[str, Any]:
    now = _now()
    address_plan = _runtime_address_plan()
    global_settings = _normalize_global_settings({}, address_plan)
    return {
        "id": RUNTIME_PROFILE_ID,
        "name": "Runtime environment",
        "description": (
            "Unsaved targets currently loaded from environment and safe defaults. "
            "Use a saved lab profile for repeatable lab selection."
        ),
        "global_settings": global_settings,
        "address_plan": address_plan,
        "source": "runtime_env",
        "version": 1,
        "active": active,
        "created_at": now,
        "updated_at": now,
        "last_selected_at": None,
        "history": [],
    }


def _runtime_address_plan() -> dict[str, Any]:
    return _normalize_address_plan(
        {
            "subnet": settings.lab_subnet_cidr or LAB_SUBNET_CIDR,
            "ilo": settings.ilo_test_host or LAB_ILO_IP,
            "server_embedded_nic": settings.server_embedded_nic_ip or LAB_SERVER_EMBEDDED_NIC_IP,
            "esxi_management": settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP,
            "cisco_management": settings.cisco_target_ip or LAB_CISCO_MANAGEMENT_IP,
            "ansible_control_host": settings.ansible_control_host or LAB_ANSIBLE_CONTROL_HOST_IP,
            "netapp_controller_a_sp": settings.netapp_controller_a_sp
            or LAB_NETAPP_CONTROLLER_A_SP_IP,
            "netapp_controller_b_sp": settings.netapp_controller_b_sp
            or LAB_NETAPP_CONTROLLER_B_SP_IP,
            "netapp_cluster_mgmt": settings.netapp_cluster_mgmt_ip or LAB_NETAPP_CLUSTER_MGMT_IP,
            "netapp_node_a_mgmt": settings.netapp_node_a_mgmt_ip or LAB_NETAPP_NODE_A_MGMT_IP,
            "netapp_node_b_mgmt": settings.netapp_node_b_mgmt_ip or LAB_NETAPP_NODE_B_MGMT_IP,
            "netapp_svm_mgmt": settings.netapp_svm_mgmt_ip or LAB_NETAPP_SVM_MGMT_IP,
            "netapp_iscsi_lifs": list(settings.netapp_iscsi_lifs or LAB_NETAPP_ISCSI_LIF_IPS),
        }
    )


def _normalize_profile_components(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    address_plan = _normalize_address_plan(payload.get("address_plan") or {})
    global_settings = _normalize_global_settings(payload.get("global_settings") or {}, address_plan)
    address_plan = _apply_subnet_schema(address_plan, global_settings)
    global_settings = _normalize_global_settings(global_settings, address_plan)
    return global_settings, address_plan


def _normalize_global_settings(
    value: dict[str, Any], address_plan: dict[str, Any]
) -> dict[str, Any]:
    prefix = _subnet_prefix(value.get("subnet_prefix"), address_plan.get("subnet"))
    network = _network_for_subnet(address_plan.get("subnet"), prefix)
    gateway = _clean_string(value.get("gateway")) or _host_address(network, 1)
    netapp_supported = _netapp_supported(prefix)
    return {
        "subnet_prefix": prefix,
        "gateway": gateway,
        "domain_name": _clean_string(value.get("domain_name")),
        "dns_servers": _clean_string_list(value.get("dns_servers")),
        "ntp_servers": _clean_string_list(value.get("ntp_servers")),
        "timezone": _clean_string(value.get("timezone")),
        "netapp_enabled": netapp_supported and bool(value.get("netapp_enabled", True)),
        "netapp_disabled_reason": None if netapp_supported else NETAPP_DISABLED_REASON,
    }


def _normalize_address_plan(value: dict[str, Any]) -> dict[str, Any]:
    string_fields = [
        "subnet",
        "ilo",
        "server_embedded_nic",
        "esxi_management",
        "cisco_management",
        "ansible_control_host",
        "netapp_controller_a_sp",
        "netapp_controller_b_sp",
        "netapp_cluster_mgmt",
        "netapp_node_a_mgmt",
        "netapp_node_b_mgmt",
        "netapp_svm_mgmt",
    ]
    normalized = {field: _clean_string(value.get(field)) for field in string_fields}
    raw_lifs = value.get("netapp_iscsi_lifs") or []
    if isinstance(raw_lifs, str):
        raw_lifs = [item.strip() for item in raw_lifs.split(",")]
    normalized["netapp_iscsi_lifs"] = [
        item for item in (_clean_string(item) for item in raw_lifs) if item
    ]
    return normalized


def _apply_subnet_schema(
    address_plan: dict[str, Any], global_settings: dict[str, Any]
) -> dict[str, Any]:
    prefix = int(global_settings["subnet_prefix"])
    network = _network_for_subnet(address_plan.get("subnet"), prefix)
    normalized = dict(address_plan)
    normalized["subnet"] = str(network)

    core_offsets = LAB_BUILDER_CORE_OFFSETS if prefix <= NETAPP_MINIMUM_PREFIX else COMPACT_CORE_OFFSETS
    for key, offset in core_offsets.items():
        if key == "gateway":
            continue
        if not normalized.get(key):
            normalized[key] = _host_address(network, offset)

    if not _netapp_supported(prefix):
        for key in LAB_BUILDER_NETAPP_OFFSETS:
            normalized[key] = None
        normalized["netapp_iscsi_lifs"] = []
        return normalized

    for key, offset in LAB_BUILDER_NETAPP_OFFSETS.items():
        if not normalized.get(key):
            normalized[key] = _host_address(network, offset)
    if not normalized.get("netapp_iscsi_lifs"):
        normalized["netapp_iscsi_lifs"] = [
            address
            for address in (_host_address(network, offset) for offset in LAB_BUILDER_NETAPP_ISCSI_OFFSETS)
            if address
        ]
    return normalized


def _network_for_subnet(value: str | None, prefix: int) -> IPv4Network:
    source = value or LAB_SUBNET_CIDR
    address = str(source).split("/", maxsplit=1)[0]
    try:
        return ip_network(f"{address}/{prefix}", strict=False)
    except ValueError:
        return ip_network(LAB_SUBNET_CIDR, strict=False)


def _subnet_prefix(raw_prefix: Any, subnet: str | None) -> int:
    try:
        prefix = int(str(raw_prefix).strip().lstrip("/")) if raw_prefix is not None else None
    except (TypeError, ValueError):
        prefix = None
    if prefix in SUBNET_PREFIX_OPTIONS:
        return int(prefix)
    if subnet:
        try:
            network = ip_network(str(subnet), strict=False)
        except ValueError:
            network = None
        if isinstance(network, IPv4Network) and network.prefixlen in SUBNET_PREFIX_OPTIONS:
            return int(network.prefixlen)
    return 24


def _host_address(network: IPv4Network, host_offset: int) -> str | None:
    usable_hosts = max(network.num_addresses - 2, 0)
    if host_offset < 1 or host_offset > usable_hosts:
        return None
    return str(network.network_address + host_offset)


def _usable_hosts(prefix: int) -> int:
    return max((2 ** (32 - prefix)) - 2, 0)


def _netapp_supported(prefix: int) -> bool:
    return prefix <= NETAPP_MINIMUM_PREFIX


def _clean_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = [value]
    return [item for item in (_clean_string(candidate) for candidate in candidates) if item]


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now() -> str:
    return datetime.now(UTC).isoformat()
