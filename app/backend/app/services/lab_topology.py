from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
from typing import Any

HIGH_ADDRESS_LAB = "high_address_lab"
COMPACT_EDGE_LAB = "compact_edge_lab"
CUSTOM_LAB = "custom"
PROFILE_TOPOLOGIES = {HIGH_ADDRESS_LAB, COMPACT_EDGE_LAB, CUSTOM_LAB}

NETAPP_DISABLED_COMPACT_REASON = (
    "NetApp capabilities require a /24 or larger lab subnet for high-address defaults; compact lab profiles "
    "mark NetApp not in scope unless it is manually enabled with custom in-subnet addresses."
)
VCENTER_DISABLED_COMPACT_REASON = (
    "vCenter is not in scope for compact /26 lab profiles unless it is manually enabled."
)
NETAPP_DISABLED_PREFIX_REASON = (
    "NetApp high-address defaults require a /24 or larger lab subnet."
)

HIGH_ADDRESS_OFFSETS = {
    "gateway": 1,
    "ilo": 201,
    "server_embedded_nic": 202,
    "esxi_management": 203,
    "cisco_management": 204,
    "ansible_control_host": 205,
    "netapp_controller_a_sp": 210,
    "netapp_controller_b_sp": 211,
    "netapp_cluster_mgmt": 220,
    "netapp_node_a_mgmt": 221,
    "netapp_node_b_mgmt": 222,
    "netapp_svm_mgmt": 223,
}
HIGH_ADDRESS_NETAPP_NFS_OFFSETS = (230, 231)
HIGH_ADDRESS_NETAPP_ISCSI_OFFSETS = (240, 241, 242, 243)

COMPACT_EDGE_OFFSETS = {
    "gateway": 1,
    "switch_primary": 2,
    "switch_secondary": 3,
    "reserved_1": 4,
    "reserved_2": 5,
    "reserved_3": 6,
    "ups": 7,
    "backup_storage": 8,
    "utility_vm": 9,
    "esxi_management": 10,
    "ilo": 11,
}

ADDRESS_PLAN_SCALAR_FIELDS = (
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
)
ADDRESS_PLAN_LIST_FIELDS = ("netapp_nfs_lifs", "netapp_iscsi_lifs")

NETAPP_ADDRESS_FIELDS = {
    "netapp_controller_a_sp",
    "netapp_controller_b_sp",
    "netapp_cluster_mgmt",
    "netapp_node_a_mgmt",
    "netapp_node_b_mgmt",
    "netapp_svm_mgmt",
}

DEVICE_TO_ADDRESS_FIELD = {
    "ilo": "ilo",
    "esxi": "esxi_management",
    "cisco": "cisco_management",
    "switch_primary": "cisco_management",
    "utility_vm": "ansible_control_host",
}

NETAPP_DEVICE_TO_ADDRESS_FIELD = {
    "controller_a_sp": "netapp_controller_a_sp",
    "controller_b_sp": "netapp_controller_b_sp",
    "cluster_mgmt": "netapp_cluster_mgmt",
    "node_a_mgmt": "netapp_node_a_mgmt",
    "node_b_mgmt": "netapp_node_b_mgmt",
    "svm_mgmt": "netapp_svm_mgmt",
    "nfs_lifs": "netapp_nfs_lifs",
    "iscsi_lifs": "netapp_iscsi_lifs",
}


class LabTopologyError(ValueError):
    pass


def derive_lab_topology(
    *,
    profile_topology: str | None,
    subnet_cidr: str | None,
    global_settings: dict[str, Any] | None,
    address_plan: dict[str, Any] | None,
    devices: dict[str, Any] | None,
    features: dict[str, Any] | None,
    default_subnet: str,
) -> dict[str, Any]:
    global_settings = dict(global_settings or {})
    address_plan = dict(address_plan or {})
    devices = dict(devices or {})
    raw_features = dict(features or {})

    network = _network(subnet_cidr or address_plan.get("subnet") or default_subnet)
    topology = _topology_for(profile_topology, network.prefixlen)
    layout_topology = topology_for_prefix(network.prefixlen) if topology == CUSTOM_LAB else topology
    _validate_topology_fit(network, layout_topology)

    resolved_plan = _default_address_plan(network, layout_topology)
    _merge_address_overrides(resolved_plan, address_plan)
    _merge_device_overrides(resolved_plan, devices)

    feature_state = _feature_state(
        topology=layout_topology,
        prefix=network.prefixlen,
        raw_features=raw_features,
        global_settings=global_settings,
    )
    if not feature_state["netapp_enabled"]:
        _clear_netapp(resolved_plan)

    gateway = (
        _clean_string(global_settings.get("gateway"))
        or _clean_string(devices.get("gateway"))
        or resolved_plan.get("gateway")
        or _address_at_offset(network, 1)
    )
    resolved_plan["subnet"] = str(network)
    resolved_plan.pop("gateway", None)

    _validate_addresses(network, resolved_plan, gateway, feature_state)

    normalized_global = _global_settings(global_settings, gateway, network.prefixlen, feature_state)
    normalized_devices = _devices(network, layout_topology, resolved_plan, gateway, devices, feature_state)
    not_in_scope = _not_in_scope_stages(feature_state)

    return {
        "profile_topology": topology,
        "subnet_cidr": str(network),
        "gateway": gateway,
        "dns": _clean_string_list(global_settings.get("dns") or global_settings.get("dns_servers")),
        "ntp": _clean_string_list(global_settings.get("ntp") or global_settings.get("ntp_servers")),
        "vlan_id": _clean_string(global_settings.get("vlan_id")),
        "mtu": _int_or_none(global_settings.get("mtu")),
        "global_settings": normalized_global,
        "address_plan": _address_plan_response(resolved_plan),
        "devices": normalized_devices,
        "features": feature_state,
        "resolved_address_plan": _address_plan_response(resolved_plan),
        "not_in_scope_stages": not_in_scope,
        "mismatch_warnings": [],
        "fix_guidance": [],
    }


def runtime_configured_address_plan() -> dict[str, Any]:
    """Return only explicit runtime/env address overrides.

    Defaults are derived from topology so a /26 runtime does not inherit the
    committed 192.168.1.x high-address constants by accident.
    """

    import os

    return {
        "subnet": _clean_string(os.getenv("LAB_SUBNET_CIDR")),
        "ilo": _clean_string(os.getenv("ILO_TEST_HOST")),
        "server_embedded_nic": _clean_string(os.getenv("SERVER_EMBEDDED_NIC_IP")),
        "esxi_management": _clean_string(os.getenv("ESXI_TEST_HOST")),
        "cisco_management": _clean_string(
            os.getenv("CISCO_TARGET_IP") or os.getenv("ANSIBLE_CISCO_HOST")
        ),
        "ansible_control_host": _clean_string(os.getenv("ANSIBLE_CONTROL_HOST")),
        "netapp_controller_a_sp": _clean_string(os.getenv("NETAPP_CONTROLLER_A_SP")),
        "netapp_controller_b_sp": _clean_string(os.getenv("NETAPP_CONTROLLER_B_SP")),
        "netapp_cluster_mgmt": _clean_string(os.getenv("NETAPP_CLUSTER_MGMT_IP")),
        "netapp_node_a_mgmt": _clean_string(os.getenv("NETAPP_NODE_A_MGMT_IP")),
        "netapp_node_b_mgmt": _clean_string(os.getenv("NETAPP_NODE_B_MGMT_IP")),
        "netapp_svm_mgmt": _clean_string(os.getenv("NETAPP_SVM_MGMT_IP")),
        "netapp_nfs_lifs": _clean_string_list(os.getenv("NETAPP_NFS_LIFS")),
        "netapp_iscsi_lifs": _clean_string_list(os.getenv("NETAPP_ISCSI_LIFS")),
    }


def configured_runtime_values() -> dict[str, Any]:
    import os

    return {
        "subnet": _clean_string(os.getenv("LAB_SUBNET_CIDR")),
        "ilo": _clean_string(os.getenv("ILO_TEST_HOST")),
        "server_embedded_nic": _clean_string(os.getenv("SERVER_EMBEDDED_NIC_IP")),
        "esxi_management": _clean_string(os.getenv("ESXI_TEST_HOST")),
        "cisco_management": _clean_string(os.getenv("CISCO_TARGET_IP")),
        "ansible_cisco_inventory_target": _clean_string(os.getenv("ANSIBLE_CISCO_HOST")),
        "ansible_control_host": _clean_string(os.getenv("ANSIBLE_CONTROL_HOST")),
        "netapp_controller_a_sp": _clean_string(os.getenv("NETAPP_CONTROLLER_A_SP")),
        "netapp_controller_b_sp": _clean_string(os.getenv("NETAPP_CONTROLLER_B_SP")),
        "netapp_cluster_mgmt": _clean_string(os.getenv("NETAPP_CLUSTER_MGMT_IP")),
        "netapp_node_a_mgmt": _clean_string(os.getenv("NETAPP_NODE_A_MGMT_IP")),
        "netapp_node_b_mgmt": _clean_string(os.getenv("NETAPP_NODE_B_MGMT_IP")),
        "netapp_svm_mgmt": _clean_string(os.getenv("NETAPP_SVM_MGMT_IP")),
        "netapp_nfs_lifs": ",".join(_clean_string_list(os.getenv("NETAPP_NFS_LIFS"))) or None,
        "netapp_iscsi_lifs": ",".join(_clean_string_list(os.getenv("NETAPP_ISCSI_LIFS"))) or None,
    }


def topology_for_prefix(prefix: int) -> str:
    if prefix <= 24:
        return HIGH_ADDRESS_LAB
    return COMPACT_EDGE_LAB


def _topology_for(raw: str | None, prefix: int) -> str:
    value = _clean_string(raw)
    if not value:
        return topology_for_prefix(prefix)
    if value not in PROFILE_TOPOLOGIES:
        raise LabTopologyError(f"profile_topology must be one of {', '.join(sorted(PROFILE_TOPOLOGIES))}.")
    return value


def _default_address_plan(network: IPv4Network, topology: str) -> dict[str, Any]:
    plan: dict[str, Any] = {field: None for field in ADDRESS_PLAN_SCALAR_FIELDS}
    plan["netapp_nfs_lifs"] = []
    plan["netapp_iscsi_lifs"] = []
    plan["subnet"] = str(network)
    if topology == HIGH_ADDRESS_LAB:
        for field, offset in HIGH_ADDRESS_OFFSETS.items():
            plan[field] = _address_at_offset(network, offset)
        plan["netapp_nfs_lifs"] = [
            _address_at_offset(network, offset) for offset in HIGH_ADDRESS_NETAPP_NFS_OFFSETS
        ]
        plan["netapp_iscsi_lifs"] = [
            _address_at_offset(network, offset) for offset in HIGH_ADDRESS_NETAPP_ISCSI_OFFSETS
        ]
        return plan

    plan["gateway"] = _address_at_offset(network, COMPACT_EDGE_OFFSETS["gateway"])
    plan["cisco_management"] = _address_at_offset(network, COMPACT_EDGE_OFFSETS["switch_primary"])
    plan["ansible_control_host"] = _address_at_offset(network, COMPACT_EDGE_OFFSETS["utility_vm"])
    plan["esxi_management"] = _address_at_offset(network, COMPACT_EDGE_OFFSETS["esxi_management"])
    plan["ilo"] = _address_at_offset(network, COMPACT_EDGE_OFFSETS["ilo"])
    return plan


def _merge_address_overrides(plan: dict[str, Any], overrides: dict[str, Any]) -> None:
    for field in ADDRESS_PLAN_SCALAR_FIELDS:
        value = _clean_string(overrides.get(field))
        if value:
            plan[field] = value
    for field in ADDRESS_PLAN_LIST_FIELDS:
        values = _clean_string_list(overrides.get(field))
        if values:
            plan[field] = values


def _merge_device_overrides(plan: dict[str, Any], devices: dict[str, Any]) -> None:
    for device, field in DEVICE_TO_ADDRESS_FIELD.items():
        value = _clean_string(devices.get(device))
        if value:
            plan[field] = value
    netapp = devices.get("netapp")
    if isinstance(netapp, dict):
        for device, field in NETAPP_DEVICE_TO_ADDRESS_FIELD.items():
            value = _clean_string_list(netapp.get(device)) if field in ADDRESS_PLAN_LIST_FIELDS else _clean_string(netapp.get(device))
            if value:
                plan[field] = value


def _feature_state(
    *,
    topology: str,
    prefix: int,
    raw_features: dict[str, Any],
    global_settings: dict[str, Any],
) -> dict[str, Any]:
    compact = topology == COMPACT_EDGE_LAB
    netapp_enabled = (
        _bool_value(raw_features.get("netapp_enabled"), False)
        if compact
        else _bool_value(raw_features.get("netapp_enabled"), _bool_value(global_settings.get("netapp_enabled"), True))
    )
    if prefix > 24 and "netapp_enabled" not in raw_features:
        netapp_enabled = False
    vcenter_enabled = _bool_value(raw_features.get("vcenter_enabled"), False)
    return {
        "netapp_enabled": netapp_enabled,
        "vcenter_enabled": vcenter_enabled,
        "firmware_gate_enabled": _bool_value(raw_features.get("firmware_gate_enabled"), True),
        "build_verification_enabled": _bool_value(raw_features.get("build_verification_enabled"), True),
        "storage_protocol": _clean_string(raw_features.get("storage_protocol"))
        or ("nfs" if netapp_enabled else "none"),
        "disable_ipv6": _bool_value(raw_features.get("disable_ipv6"), True),
        "enable_snmp": _bool_value(raw_features.get("enable_snmp"), False),
        "enable_ntp": _bool_value(raw_features.get("enable_ntp"), True),
        "enable_dns": _bool_value(raw_features.get("enable_dns"), True),
        "netapp_disabled_reason": None
        if netapp_enabled
        else NETAPP_DISABLED_COMPACT_REASON
        if compact
        else NETAPP_DISABLED_PREFIX_REASON,
        "vcenter_disabled_reason": None if vcenter_enabled else VCENTER_DISABLED_COMPACT_REASON if compact else "vCenter is disabled by the active lab profile.",
    }


def _global_settings(
    source: dict[str, Any],
    gateway: str | None,
    prefix: int,
    features: dict[str, Any],
) -> dict[str, Any]:
    return {
        "subnet_prefix": prefix,
        "gateway": gateway,
        "support_unit": _clean_string(source.get("support_unit")),
        "domain_name": _clean_string(source.get("domain_name")),
        "dom_dc": _clean_string(source.get("dom_dc")),
        "dns_servers": _clean_string_list(source.get("dns_servers") or source.get("dns")),
        "ntp_servers": _clean_string_list(source.get("ntp_servers") or source.get("ntp")),
        "timezone": _clean_string(source.get("timezone")),
        "netapp_enabled": bool(features["netapp_enabled"]),
        "netapp_disabled_reason": features.get("netapp_disabled_reason"),
        "vcenter_enabled": bool(features["vcenter_enabled"]),
        "vlan_id": _clean_string(source.get("vlan_id")),
        "mtu": _int_or_none(source.get("mtu")),
    }


def _devices(
    network: IPv4Network,
    topology: str,
    plan: dict[str, Any],
    gateway: str | None,
    overrides: dict[str, Any],
    features: dict[str, Any],
) -> dict[str, Any]:
    compact = topology == COMPACT_EDGE_LAB
    switch_secondary = _clean_string(overrides.get("switch_secondary"))
    ups = _clean_string(overrides.get("ups"))
    backup_storage = _clean_string(overrides.get("backup_storage"))
    utility_vm = _clean_string(overrides.get("utility_vm"))
    if compact:
        switch_secondary = switch_secondary or _address_at_offset(network, COMPACT_EDGE_OFFSETS["switch_secondary"])
        ups = ups or _address_at_offset(network, COMPACT_EDGE_OFFSETS["ups"])
        backup_storage = backup_storage or _address_at_offset(network, COMPACT_EDGE_OFFSETS["backup_storage"])
        utility_vm = utility_vm or _address_at_offset(network, COMPACT_EDGE_OFFSETS["utility_vm"])
    netapp = None
    if features["netapp_enabled"]:
        netapp = {
            "controller_a_sp": plan.get("netapp_controller_a_sp"),
            "controller_b_sp": plan.get("netapp_controller_b_sp"),
            "cluster_mgmt": plan.get("netapp_cluster_mgmt"),
            "node_a_mgmt": plan.get("netapp_node_a_mgmt"),
            "node_b_mgmt": plan.get("netapp_node_b_mgmt"),
            "svm_mgmt": plan.get("netapp_svm_mgmt"),
            "nfs_lifs": list(plan.get("netapp_nfs_lifs") or []),
            "iscsi_lifs": list(plan.get("netapp_iscsi_lifs") or []),
            "status": "in_scope",
        }
    return {
        "gateway": gateway,
        "switch_primary": plan.get("cisco_management"),
        "switch_secondary": switch_secondary,
        "reserved": _reserved_compact_addresses(network) if compact else [],
        "ups": ups,
        "backup_storage": backup_storage,
        "utility_vm": utility_vm,
        "esxi": plan.get("esxi_management"),
        "ilo": plan.get("ilo"),
        "cisco": plan.get("cisco_management"),
        "netapp": netapp,
        "vcenter": _clean_string(overrides.get("vcenter")) if features["vcenter_enabled"] else None,
    }


def _validate_topology_fit(network: IPv4Network, topology: str) -> None:
    offsets = COMPACT_EDGE_OFFSETS if topology == COMPACT_EDGE_LAB else HIGH_ADDRESS_OFFSETS
    maximum = max(offsets.values())
    if topology == HIGH_ADDRESS_LAB:
        maximum = max(maximum, *HIGH_ADDRESS_NETAPP_ISCSI_OFFSETS)
    if maximum > _usable_hosts(network):
        raise LabTopologyError(
            f"{topology} requires host offset +{maximum}, which does not fit inside {network}."
        )


def _validate_addresses(
    network: IPv4Network,
    plan: dict[str, Any],
    gateway: str | None,
    features: dict[str, Any],
) -> None:
    values: list[tuple[str, str]] = []
    if gateway:
        values.append(("gateway", gateway))
    for field in ADDRESS_PLAN_SCALAR_FIELDS:
        if field == "subnet":
            continue
        if field in NETAPP_ADDRESS_FIELDS and not features["netapp_enabled"]:
            continue
        value = _clean_string(plan.get(field))
        if value:
            values.append((field, value))
    if features["netapp_enabled"]:
        for field in ADDRESS_PLAN_LIST_FIELDS:
            for index, value in enumerate(_clean_string_list(plan.get(field))):
                values.append((f"{field}[{index}]", value))

    seen: dict[str, str] = {}
    for field, value in values:
        try:
            parsed = ip_address(value)
        except ValueError as exc:
            raise LabTopologyError(f"{field} must be a valid IPv4 address.") from exc
        if not isinstance(parsed, IPv4Address):
            raise LabTopologyError(f"{field} must be an IPv4 address.")
        if parsed not in network:
            raise LabTopologyError(f"{field}={value} is outside active subnet {network}.")
        if parsed == network.network_address or parsed == network.broadcast_address:
            raise LabTopologyError(f"{field}={value} cannot use the network or broadcast address.")
        duplicate_field = seen.get(value)
        if duplicate_field:
            raise LabTopologyError(f"{field} duplicates {duplicate_field} at {value}.")
        seen[value] = field


def _clear_netapp(plan: dict[str, Any]) -> None:
    for field in NETAPP_ADDRESS_FIELDS:
        plan[field] = None
    plan["netapp_nfs_lifs"] = []
    plan["netapp_iscsi_lifs"] = []


def _not_in_scope_stages(features: dict[str, Any]) -> list[str]:
    stages: list[str] = []
    if not features["netapp_enabled"]:
        stages.extend(["netapp", "netapp-console", "netapp-ontap", "netapp-upgrade", "netapp-nfs"])
    if not features["vcenter_enabled"]:
        stages.extend(["vcenter", "vcenter-netapp"])
    return stages


def _network(value: str) -> IPv4Network:
    try:
        network = ip_network(str(value), strict=False)
    except ValueError as exc:
        raise LabTopologyError(f"subnet_cidr must be a valid IPv4 CIDR: {value}") from exc
    if not isinstance(network, IPv4Network):
        raise LabTopologyError("subnet_cidr must be an IPv4 CIDR.")
    return network


def _address_at_offset(network: IPv4Network, offset: int) -> str | None:
    if offset < 1 or offset > _usable_hosts(network):
        return None
    return str(network.network_address + offset)


def _usable_hosts(network: IPv4Network) -> int:
    return max(network.num_addresses - 2, 0)


def _reserved_compact_addresses(network: IPv4Network) -> list[str]:
    return [
        address
        for offset in (
            COMPACT_EDGE_OFFSETS["reserved_1"],
            COMPACT_EDGE_OFFSETS["reserved_2"],
            COMPACT_EDGE_OFFSETS["reserved_3"],
        )
        for address in [_address_at_offset(network, offset)]
        if address
    ]


def _address_plan_response(plan: dict[str, Any]) -> dict[str, Any]:
    response = {field: _clean_string(plan.get(field)) for field in ADDRESS_PLAN_SCALAR_FIELDS}
    response["netapp_nfs_lifs"] = _clean_string_list(plan.get("netapp_nfs_lifs"))
    response["netapp_iscsi_lifs"] = _clean_string_list(plan.get("netapp_iscsi_lifs"))
    return response


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
