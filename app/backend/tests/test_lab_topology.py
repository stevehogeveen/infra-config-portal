from __future__ import annotations

from pathlib import Path

import pytest

from app.services.lab_topology import LabTopologyError, derive_lab_topology


def _derive(
    *,
    profile_topology: str | None = None,
    subnet_cidr: str | None = None,
    global_settings: dict | None = None,
    address_plan: dict | None = None,
    devices: dict | None = None,
    features: dict | None = None,
) -> dict:
    return derive_lab_topology(
        profile_topology=profile_topology,
        subnet_cidr=subnet_cidr,
        global_settings=global_settings,
        address_plan=address_plan,
        devices=devices,
        features=features,
        default_subnet="192.168.1.0/24",
    )


def test_24_high_address_topology_derives_lab_builder_defaults() -> None:
    profile = _derive(subnet_cidr="192.168.1.0/24")
    plan = profile["resolved_address_plan"]

    assert profile["profile_topology"] == "high_address_lab"
    assert plan["ilo"] == "192.168.1.201"
    assert plan["ilo_initial"] is None
    assert plan["server_embedded_nic"] == "192.168.1.202"
    assert plan["esxi_management"] == "192.168.1.203"
    assert plan["cisco_management"] == "192.168.1.204"
    assert plan["ansible_control_host"] == "192.168.1.205"
    assert plan["netapp_controller_a_sp"] == "192.168.1.210"
    assert plan["netapp_controller_b_sp"] == "192.168.1.211"
    assert plan["netapp_cluster_mgmt"] == "192.168.1.220"
    assert plan["netapp_node_a_mgmt"] == "192.168.1.221"
    assert plan["netapp_node_b_mgmt"] == "192.168.1.222"
    assert plan["netapp_svm_mgmt"] == "192.168.1.223"
    assert plan["netapp_nfs_lifs"] == ["192.168.1.230", "192.168.1.231"]
    assert plan["netapp_iscsi_lifs"] == [
        "192.168.1.240",
        "192.168.1.241",
        "192.168.1.242",
        "192.168.1.243",
    ]
    assert profile["features"]["deployment_mode"] == "server_netapp_direct"
    assert profile["features"]["deployment_supported"] is False


def test_26_compact_topology_derives_offset_layout_and_disables_storage_scope() -> None:
    profile = _derive(subnet_cidr="10.10.5.0/26")
    plan = profile["resolved_address_plan"]
    devices = profile["devices"]

    assert profile["profile_topology"] == "compact_edge_lab"
    assert profile["gateway"] == "10.10.5.1"
    assert devices["switch_primary"] == "10.10.5.2"
    assert devices["switch_secondary"] == "10.10.5.3"
    assert devices["reserved"] == ["10.10.5.4", "10.10.5.5", "10.10.5.6"]
    assert devices["ups"] == "10.10.5.7"
    assert devices["backup_storage"] == "10.10.5.8"
    assert devices["utility_vm"] == "10.10.5.9"
    assert plan["esxi_management"] == "10.10.5.10"
    assert plan["ilo"] == "10.10.5.11"
    assert profile["features"]["netapp_enabled"] is False
    assert profile["features"]["vcenter_enabled"] is False
    assert profile["devices"]["netapp"] is None
    assert profile["devices"]["vcenter"] is None
    assert "netapp" in profile["not_in_scope_stages"]
    assert "vcenter-netapp" in profile["not_in_scope_stages"]
    assert profile["features"]["deployment_mode"] == "single_server_local_storage"
    assert profile["features"]["deployment_supported"] is True
    assert profile["features"]["storage_location"] == "server_local"


def test_supported_world_scenario_server_netapp_vcenter_is_explicit() -> None:
    profile = _derive(
        subnet_cidr="192.168.1.0/24",
        devices={"vcenter": "192.168.1.224"},
        features={"netapp_enabled": True, "vcenter_enabled": True},
    )

    assert profile["features"]["deployment_mode"] == "server_netapp_vcenter"
    assert profile["features"]["deployment_label"] == "Server + NetApp + vCenter"
    assert profile["features"]["deployment_supported"] is True
    assert profile["features"]["storage_location"] == "netapp_shared"
    assert profile["devices"]["netapp"]["status"] == "in_scope"
    assert profile["devices"]["vcenter"] == "192.168.1.224"


def test_supported_world_scenario_single_server_local_storage_is_explicit() -> None:
    profile = _derive(
        subnet_cidr="192.168.1.0/24",
        features={"netapp_enabled": False, "vcenter_enabled": False},
    )

    assert profile["features"]["deployment_mode"] == "single_server_local_storage"
    assert profile["features"]["deployment_label"] == "Single server + local ESXi storage"
    assert profile["features"]["deployment_supported"] is True
    assert profile["features"]["storage_location"] == "server_local"
    assert profile["features"]["storage_protocol"] == "local"
    assert profile["devices"]["netapp"] is None
    assert profile["devices"]["vcenter"] is None


def test_custom_override_inside_subnet_passes_validation() -> None:
    profile = _derive(
        profile_topology="custom",
        subnet_cidr="10.10.5.0/26",
        address_plan={"ilo": "10.10.5.12", "esxi_management": "10.10.5.13"},
    )

    assert profile["profile_topology"] == "custom"
    assert profile["resolved_address_plan"]["ilo"] == "10.10.5.12"
    assert profile["resolved_address_plan"]["esxi_management"] == "10.10.5.13"


def test_initial_ilo_login_ip_can_differ_from_permanent_subnet() -> None:
    profile = _derive(
        subnet_cidr="192.0.2.0/24",
        address_plan={"ilo": "192.0.2.10", "ilo_initial": "10.0.0.55"},
    )

    assert profile["resolved_address_plan"]["ilo"] == "192.0.2.10"
    assert profile["resolved_address_plan"]["ilo_initial"] == "10.0.0.55"


def test_out_of_subnet_override_fails_validation() -> None:
    with pytest.raises(LabTopologyError, match="outside active subnet"):
        _derive(subnet_cidr="10.10.5.0/26", address_plan={"ilo": "10.10.6.11"})


def test_duplicate_ip_override_fails_validation() -> None:
    with pytest.raises(LabTopologyError, match="duplicates"):
        _derive(subnet_cidr="10.10.5.0/26", address_plan={"ilo": "10.10.5.10"})


def test_repeated_list_ip_override_self_heals_to_unique_values() -> None:
    profile = _derive(
        subnet_cidr="192.168.1.0/24",
        address_plan={
            "netapp_nfs_lifs": [
                "192.168.1.230",
                " 192.168.1.230 ",
                "192.168.1.231",
            ],
        },
    )

    assert profile["resolved_address_plan"]["netapp_nfs_lifs"] == [
        "192.168.1.230",
        "192.168.1.231",
    ]


def test_numeric_and_string_list_overrides_collapse_to_same_text_value() -> None:
    profile = _derive(
        subnet_cidr="10.10.5.0/24",
        global_settings={
            "dns_servers": [123, " 123 ", "8.8.8.8"],
            "ntp_servers": ["time.example.test", " time.example.test "],
        },
    )

    assert profile["dns"] == ["123", "8.8.8.8"]
    assert profile["ntp"] == ["time.example.test"]


def test_blank_and_missing_fields_self_heal_to_defaults() -> None:
    profile = _derive(
        subnet_cidr=" 10.10.5.0/26 ",
        global_settings={
            "gateway": "   ",
            "dns_servers": " 1.1.1.1, ,8.8.8.8, ",
            "ntp_servers": [" ", "time.example.test", None],
            "mtu": "not-a-number",
            "vlan_id": "\t",
        },
        address_plan={
            "ilo": "",
            "esxi_management": None,
            "netapp_nfs_lifs": " , ",
        },
        devices={"switch_secondary": ""},
    )

    assert profile["gateway"] == "10.10.5.1"
    assert profile["resolved_address_plan"]["ilo"] == "10.10.5.11"
    assert profile["resolved_address_plan"]["esxi_management"] == "10.10.5.10"
    assert profile["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert profile["ntp"] == ["time.example.test"]
    assert profile["mtu"] is None
    assert profile["vlan_id"] is None
    assert profile["devices"]["switch_secondary"] == "10.10.5.3"


def test_long_and_strange_metadata_strings_are_trimmed_without_validation_failure() -> None:
    long_support_unit = f"  {'ops/team;drop-table?' * 40}  "
    profile = _derive(
        subnet_cidr="10.10.5.0/24",
        global_settings={
            "support_unit": long_support_unit,
            "domain_name": " lab.example.test;$(whoami) ",
            "timezone": " America/Toronto\n",
        },
        features={
            "firmware_gate_enabled": " YES ",
            "build_verification_enabled": " definitely ",
            "storage_protocol": " iScSi ",
        },
    )

    assert profile["global_settings"]["support_unit"] == long_support_unit.strip()
    assert profile["global_settings"]["domain_name"] == "lab.example.test;$(whoami)"
    assert profile["global_settings"]["timezone"] == "America/Toronto"
    assert profile["features"]["firmware_gate_enabled"] is True
    assert profile["features"]["build_verification_enabled"] is False
    assert profile["features"]["storage_protocol"] == "iscsi"


def test_invalid_storage_protocol_falls_back_to_real_scenario_default() -> None:
    netapp_profile = _derive(features={"netapp_enabled": True, "storage_protocol": " iscsi;rm -rf "})
    local_profile = _derive(features={"netapp_enabled": False, "storage_protocol": " nfs;rm -rf "})

    assert netapp_profile["features"]["storage_protocol"] == "nfs"
    assert local_profile["features"]["storage_protocol"] == "local"


def test_compact_offset_rules_must_fit_subnet() -> None:
    with pytest.raises(LabTopologyError, match="does not fit"):
        _derive(subnet_cidr="10.10.5.0/29")


def test_local_lab_profile_files_remain_gitignored() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

    assert ".local/" in gitignore
    assert ".env.local.real-lab" in gitignore
