from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.lab_profiles import active_lab_profile_for_report

REPO_ROOT = Path(__file__).resolve().parents[4]


class ControlAccessConfigNotFoundError(LookupError):
    pass


ACCESS_SECTION_METADATA: dict[str, dict[str, Any]] = {
    "cisco": {
        "title": "Cisco first-time access",
        "desired_key": "cisco_management",
        "desired_label": "Cisco management IP",
        "access_method": "Console or SSH",
        "editable_fields": ("Management IP", "Gateway", "DNS", "VLAN", "SSH/SCP"),
    },
    "ilo": {
        "title": "iLO first-time access",
        "desired_key": "ilo",
        "desired_label": "iLO management IP",
        "access_method": "HTTPS / Redfish",
        "editable_fields": ("Management IP", "Gateway", "DNS", "NTP", "Local users"),
    },
    "raid": {
        "title": "Server first-time access",
        "desired_key": "server_embedded_nic",
        "desired_label": "Server embedded NIC",
        "access_method": "iLO / local server path",
        "editable_fields": ("Server NIC IP", "iLO path", "RAID intent", "Post-reset validation"),
    },
    "esxi": {
        "title": "ESXi first-time access",
        "desired_key": "esxi_management",
        "desired_label": "ESXi management IP",
        "access_method": "Installer DCUI / HTTPS / SSH",
        "editable_fields": ("Management IP", "Gateway", "DNS", "Hostname", "NTP"),
    },
    "netapp": {
        "title": "NetApp first-time access",
        "desired_key": "netapp_cluster_mgmt",
        "desired_label": "Cluster management IP",
        "access_method": "Console / SP / ONTAP REST",
        "editable_fields": ("SP IPs", "Cluster IP", "Node IPs", "SVM IP", "LIFs"),
    },
}


def control_access_configs(lab_profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    store = _read_store()
    return {
        section_id: _read_config(section_id, lab_profile, store.get(section_id))
        for section_id in ACCESS_SECTION_METADATA
    }


def update_control_access_config(section_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if section_id not in ACCESS_SECTION_METADATA:
        raise ControlAccessConfigNotFoundError(section_id)
    _validate_ip(payload.get("original_dhcp_ip"))
    store = _read_store()
    store[section_id] = {
        "first_time_configuring": bool(payload.get("first_time_configuring", True)),
        "original_dhcp_ip": _clean_string(payload.get("original_dhcp_ip")),
        "username_reference": _clean_string(payload.get("username_reference")),
        "password_configured": bool(payload.get("password_configured", False)),
        "password_reference_label": _clean_string(payload.get("password_reference_label")),
        "updated_at": _now(),
    }
    _write_store(store)
    return _read_config(section_id, active_lab_profile_for_report(), store[section_id])


def _read_config(
    section_id: str,
    lab_profile: dict[str, Any],
    saved: Any,
) -> dict[str, Any]:
    metadata = ACCESS_SECTION_METADATA[section_id]
    saved = saved if isinstance(saved, dict) else {}
    address_plan = lab_profile.get("address_plan") or {}
    original_dhcp_ip = _clean_string(saved.get("original_dhcp_ip"))
    username_reference = _clean_string(saved.get("username_reference"))
    password_configured = bool(saved.get("password_configured", False))
    first_time_configuring = bool(saved.get("first_time_configuring", True))
    blockers = []
    if first_time_configuring and not original_dhcp_ip:
        blockers.append("Original DHCP/current-access IP is required before first-time config edits.")
    if first_time_configuring and not username_reference:
        blockers.append("Username reference is required before first-time config edits.")
    if first_time_configuring and not password_configured:
        blockers.append("Password must be available from the local credential path before edits.")

    return {
        "section_id": section_id,
        "title": metadata["title"],
        "access_method": metadata["access_method"],
        "first_time_configuring": first_time_configuring,
        "first_time_note": "First-time configuration only: capture original DHCP/current access before changing final IP config.",
        "original_dhcp_ip": original_dhcp_ip,
        "desired_management_ip": _clean_string(address_plan.get(metadata["desired_key"])),
        "desired_address_label": metadata["desired_label"],
        "username_reference": username_reference,
        "password_configured": password_configured,
        "password_reference_label": _clean_string(saved.get("password_reference_label")),
        "editable_fields": [
            {
                "label": label,
                "value": _field_value(label, lab_profile, section_id),
                "source": "active_lab_profile",
            }
            for label in metadata["editable_fields"]
        ],
        "blockers": blockers,
        "updated_at": saved.get("updated_at"),
    }


def _field_value(label: str, lab_profile: dict[str, Any], section_id: str) -> str:
    address_plan = lab_profile.get("address_plan") or {}
    global_settings = lab_profile.get("global_settings") or {}
    if label in {"Management IP", "Cisco management IP"}:
        return str(address_plan.get(ACCESS_SECTION_METADATA[section_id]["desired_key"]) or "Not set")
    if label == "Gateway":
        return str(global_settings.get("gateway") or "Not set")
    if label == "DNS":
        dns_servers = global_settings.get("dns_servers") or []
        return ", ".join(dns_servers) if dns_servers else "Not set"
    if label == "NTP":
        ntp_servers = global_settings.get("ntp_servers") or []
        return ", ".join(ntp_servers) if ntp_servers else "Not set"
    if label == "SP IPs":
        return ", ".join(
            value
            for value in [
                address_plan.get("netapp_controller_a_sp"),
                address_plan.get("netapp_controller_b_sp"),
            ]
            if value
        ) or "Not set"
    if label == "Cluster IP":
        return str(address_plan.get("netapp_cluster_mgmt") or "Not set")
    if label == "Node IPs":
        return ", ".join(
            value
            for value in [
                address_plan.get("netapp_node_a_mgmt"),
                address_plan.get("netapp_node_b_mgmt"),
            ]
            if value
        ) or "Not set"
    if label == "SVM IP":
        return str(address_plan.get("netapp_svm_mgmt") or "Not set")
    if label == "LIFs":
        lifs = address_plan.get("netapp_iscsi_lifs") or []
        return ", ".join(lifs) if lifs else "Not set"
    if label == "Server NIC IP":
        return str(address_plan.get("server_embedded_nic") or "Not set")
    return "Configured in section workflow"


def _store_path() -> Path:
    configured = os.getenv("CONTROL_ACCESS_STORE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "control-access.json"


def _read_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_store(store: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_sensitive(store), indent=2, sort_keys=True), encoding="utf-8")


def _validate_ip(value: Any) -> None:
    text = _clean_string(value)
    if not text:
        return
    ip_address(text)


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now() -> str:
    return datetime.now(UTC).isoformat()
