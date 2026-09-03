from __future__ import annotations

from ipaddress import ip_network
from typing import Any

from app.services.lab_profiles import active_lab_profile_context


def active_cisco_network_defaults() -> dict[str, Any]:
    context = active_lab_profile_context()
    plan, active, global_settings = _active_profile_parts(context)
    field_presence = _dict(active.get("_field_presence"))
    subnet = _string(plan.get("subnet") or active.get("subnet_cidr"))
    prefix = _string(global_settings.get("subnet_prefix")) or _prefix_from_subnet(subnet)
    return {
        "planned_management_ip": _string(plan.get("cisco_management")),
        "subnet_prefix": _prefix_value(prefix),
        "planned_prefix": _prefix_value(prefix),
        "gateway": _string(global_settings.get("gateway") or active.get("gateway")),
        "planned_gateway": _string(global_settings.get("gateway") or active.get("gateway")),
        "management_vlan": _string(global_settings.get("vlan_id") or active.get("vlan_id")),
        "dns_servers": _profile_list_value(
            field_presence,
            global_settings,
            "dns_servers",
            active,
            "dns",
        ),
        "ntp_servers": _profile_list_value(
            field_presence,
            global_settings,
            "ntp_servers",
            active,
            "ntp",
        ),
        "mtu": _string(global_settings.get("mtu") or active.get("mtu")),
    }


def active_server_network_defaults() -> dict[str, Any]:
    context = active_lab_profile_context()
    plan, active, global_settings = _active_profile_parts(context)
    field_presence = _dict(active.get("_field_presence"))
    subnet = _string(plan.get("subnet") or active.get("subnet_cidr"))
    prefix = _string(global_settings.get("subnet_prefix")) or _prefix_from_subnet(subnet)
    return {
        "ilo": _string(plan.get("ilo")),
        "ilo_initial": _string(plan.get("ilo_initial")),
        "server_embedded_nic": _string(plan.get("server_embedded_nic")),
        "esxi_management": _string(plan.get("esxi_management")),
        "subnet_prefix": _prefix_value(prefix),
        "gateway": _string(global_settings.get("gateway") or active.get("gateway")),
        "dns_servers": _profile_list_value(
            field_presence,
            global_settings,
            "dns_servers",
            active,
            "dns",
        ),
        "ntp_servers": _profile_list_value(
            field_presence,
            global_settings,
            "ntp_servers",
            active,
            "ntp",
        ),
        "mtu": _string(global_settings.get("mtu") or active.get("mtu")),
    }


def first_configured(*values: object) -> str | None:
    for value in values:
        text = _string(value)
        if text:
            return text
    return None


def first_configured_list(*values: object) -> list[str]:
    for value in values:
        if isinstance(value, (list, tuple, set)):
            return _string_list(value)
        items = _string_list(value)
        if items:
            return items
    return []


def _active_profile_parts(context: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = _dict(context.get("resolved_address_plan"))
    active = _dict(context.get("active_profile"))
    global_settings = _dict(active.get("global_settings"))
    return plan, active, global_settings


def _dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _profile_list_value(
    field_presence: dict[str, Any],
    primary: dict[str, Any],
    primary_key: str,
    fallback: dict[str, Any],
    fallback_key: str,
) -> list[str] | None:
    global_keys = set(_string_list(field_presence.get("global_settings")))
    top_level_keys = set(_string_list(field_presence.get("top_level")))
    if primary_key in global_keys:
        return _string_list(primary.get(primary_key))
    if fallback_key in top_level_keys:
        return _string_list(fallback.get(fallback_key))
    if not field_presence:
        primary_items = _string_list(primary.get(primary_key))
        fallback_items = _string_list(fallback.get(fallback_key))
        if primary_items or fallback_items:
            return primary_items or fallback_items
    return None


def _string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _string(item))]
    if isinstance(value, str):
        return [text for item in value.split(",") if (text := item.strip())]
    return []


def _prefix_from_subnet(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ip_network(value, strict=False).prefixlen)
    except ValueError:
        return None


def _prefix_value(value: str | None) -> str | None:
    if not value:
        return None
    return value if value.startswith("/") else f"/{value}"
