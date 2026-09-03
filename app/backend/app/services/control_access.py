from __future__ import annotations

import os
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.env_utils import bool_value
from app.services.json_file_store import read_json_object, write_json_object
from app.services.lab_profiles import active_lab_profile_for_report

REPO_ROOT = Path(__file__).resolve().parents[4]


class ControlAccessConfigNotFoundError(LookupError):
    pass


class ControlAccessConfigValidationError(ValueError):
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
    previous = store.get(section_id)
    previous = previous if isinstance(previous, dict) else {}
    editable_fields = (
        _editable_field_overrides(section_id, payload.get("editable_fields"))
        if payload.get("editable_fields") is not None
        else _saved_editable_fields(previous.get("editable_fields"))
    )
    store[section_id] = {
        "first_time_configuring": bool_value(payload.get("first_time_configuring", True), True),
        "original_dhcp_ip": _clean_string(payload.get("original_dhcp_ip")),
        "username_reference": _clean_string(payload.get("username_reference")),
        "password_configured": bool_value(payload.get("password_configured", False), False),
        "password_reference_label": None,
        "editable_fields": editable_fields,
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
    password_configured = bool_value(saved.get("password_configured", False), False)
    first_time_configuring = bool_value(saved.get("first_time_configuring", True), True)
    saved_fields = _saved_editable_fields(saved.get("editable_fields"))
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
        "password_reference_label": None,
        "editable_fields": [
            {
                "label": label,
                "value": saved_fields.get(label) or _field_value(label, lab_profile, section_id),
                "source": "saved_override" if label in saved_fields else "active_lab_profile",
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
    if label == "VLAN":
        vlan = global_settings.get("vlan_id")
        return str(vlan) if vlan else "Not set"
    if label == "SSH/SCP":
        return "Enable after validation"
    if label == "Local users":
        return "Secret references only"
    return "Configured in section workflow"


def _editable_field_overrides(section_id: str, fields: Any) -> dict[str, str]:
    if fields is None:
        return {}
    if not isinstance(fields, list):
        raise ControlAccessConfigValidationError("editable_fields must be a list of label/value entries.")
    allowed = set(ACCESS_SECTION_METADATA[section_id]["editable_fields"])
    overrides: dict[str, str] = {}
    for field in fields:
        if not isinstance(field, dict):
            raise ControlAccessConfigValidationError("editable_fields entries must be objects.")
        label = _clean_string(field.get("label"))
        value = _clean_string(field.get("value"))
        if not label:
            raise ControlAccessConfigValidationError("editable_fields entries require a label.")
        if label not in allowed:
            raise ControlAccessConfigValidationError(f"{label} is not an editable field for {section_id}.")
        if not value or value == "Not set":
            continue
        _validate_editable_field(section_id, label, value)
        overrides[label] = value
    return overrides


def _saved_editable_fields(fields: Any) -> dict[str, str]:
    if not isinstance(fields, dict):
        return {}
    normalized: dict[str, str] = {}
    for label, value in fields.items():
        clean_label = _clean_string(label)
        clean_value = _clean_string(value)
        if clean_label and clean_value:
            normalized[clean_label] = clean_value
    return normalized


def _validate_editable_field(section_id: str, label: str, value: str) -> None:
    ip_fields = {"Management IP", "Gateway", "Cluster IP", "SVM IP", "Server NIC IP"}
    ip_list_fields = {"SP IPs", "Node IPs", "LIFs"}
    if label in ip_fields:
        _validate_ip(value)
    if label in ip_list_fields:
        _validate_ip_list(value)
    if section_id == "cisco" and label == "VLAN":
        text = value.strip()
        if text.isdigit():
            vlan_id = int(text)
            if vlan_id < 1 or vlan_id > 4094:
                raise ControlAccessConfigValidationError("VLAN must be between 1 and 4094.")


def _validate_ip_list(value: str) -> None:
    parts = [item.strip() for item in value.split(",") if item.strip()]
    if not parts:
        return
    for item in parts:
        _validate_ip(item)


def _store_path() -> Path:
    configured = os.getenv("CONTROL_ACCESS_STORE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "control-access.json"


def _read_store() -> dict[str, Any]:
    return read_json_object(_store_path())


def _write_store(store: dict[str, Any]) -> None:
    write_json_object(_store_path(), redact_sensitive(store))


def _validate_ip(value: Any) -> None:
    text = _clean_string(value)
    if not text:
        return
    try:
        ip_address(text)
    except ValueError as exc:
        raise ControlAccessConfigValidationError(f"{text} must be an IPv4 or IPv6 address.") from exc


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now() -> str:
    return datetime.now(UTC).isoformat()
