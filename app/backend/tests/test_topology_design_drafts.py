from __future__ import annotations

from ipaddress import ip_address, ip_network
from itertools import product
from pathlib import Path

import pytest

from app.services import topology_design_drafts


SCENARIOS = (
    "server_netapp_vcenter",
    "server_netapp_direct",
    "single_server_local_storage",
)
SUBNETS = (
    "192.168.1.0/24",
    "10.44.7.0/24",
    None,
)


@pytest.mark.parametrize(("scenario", "subnet"), list(product(SCENARIOS, SUBNETS)))
def test_generated_topology_draft_defaults_keep_scenario_invariants(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    subnet: str | None,
) -> None:
    monkeypatch.setenv("TOPOLOGY_DESIGN_DRAFT_STORE", str(tmp_path / "topology-design-drafts.json"))

    draft = topology_design_drafts.get_topology_design_draft("generated-lab", scenario, subnet)

    assert draft["source"] == "default"
    assert draft["hardware_touched"] is False
    assert _unique_non_empty(draft["placements"].values())
    assert set(draft["lane_settings"]) == {"management", "storage", "virtualization"}
    assert "switch-server" in draft["connection_settings"]
    assert "server-vm" in draft["connection_settings"]
    assert draft["device_settings"]["switch"]["bpdu_guard"] == "enabled on edge access ports"
    assert draft["device_settings"]["switch"]["blackhole_vlan"] == "999"
    assert "acl_lanes" in draft["device_settings"]["switch"]
    assert "drive_bays" in draft["device_settings"]["server-gen10"]
    assert "raid_controller" in draft["device_settings"]["server-gen10"]
    if scenario == "single_server_local_storage":
        assert "netapp" not in draft["placements"].values()
        assert "netapp" not in draft["device_settings"]
        assert "switch-netapp" not in draft["connection_settings"]
        assert "server-netapp" not in draft["connection_settings"]
        assert draft["lane_settings"]["storage"]["protocol"] == "local datastore"
        assert draft["lane_settings"]["storage"]["target"] == "server-local RAID datastore"
    else:
        assert draft["placements"]["u3"] == "netapp"
        assert "netapp" in draft["device_settings"]
        assert "server-netapp" in draft["connection_settings"]
        assert draft["lane_settings"]["storage"]["mtu"] == "9000"
    if scenario == "server_netapp_vcenter":
        assert draft["placements"]["virtual"] == "vcenter"
    else:
        assert draft["placements"]["virtual"] is None
    if subnet and subnet.endswith("/24"):
        network = ip_network(subnet)
        for address in _planned_ips(draft["device_settings"]):
            assert ip_address(address) in network


@pytest.mark.parametrize(("scenario", "subnet"), list(product(SCENARIOS, SUBNETS)))
def test_generated_topology_draft_save_normalizes_invalid_matrix_without_hardware_effect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scenario: str,
    subnet: str | None,
) -> None:
    monkeypatch.setenv("TOPOLOGY_DESIGN_DRAFT_STORE", str(tmp_path / "topology-design-drafts.json"))
    payload = {
        "profile_id": "generated-lab",
        "scenario": scenario,
        "subnet": subnet,
        "placements": {
            "u1": "switch",
            "u2": "vcenter",
            "u3": "netapp",
            "u4": "netapp",
            "virtual": "server-gen10plus",
            "unknown": "windows",
        },
        "device_settings": {
            "switch": {
                "acl_lanes": "MGMT-IN, STORAGE-NFS-IN, DROP-ALL, QUARANTINE",
                "blackhole_vlan": "998",
                "management_ip": "10.44.7.204",
                "storage_vlan": "230",
                "unknown": "ignored",
            },
            "netapp": {
                "controller_ports": "e0a/e0b/e0c/e0d",
                "management_ip": "10.44.7.220",
                "notes": "n" * 400,
            },
            "unknown": {"name": "ignored"},
        },
        "lane_settings": {
            "storage": {
                "mtu": "9100",
                "protocol": "operator-selected storage",
                "target": "operator-selected target",
                "unknown": "ignored",
            },
            "unknown": {"mtu": "ignored"},
        },
        "connection_settings": {
            "server-netapp": {
                "protocol": "operator-selected datastore path",
                "status": "planned",
                "unknown": "ignored",
            },
            "unknown": {"status": "ignored"},
        },
    }

    saved = topology_design_drafts.save_topology_design_draft(payload)

    assert saved["source"] == "saved"
    assert saved["hardware_touched"] is False
    assert _unique_non_empty(saved["placements"].values())
    assert saved["placements"]["u2"] != "vcenter"
    assert saved["placements"]["virtual"] != "server-gen10plus"
    assert "unknown" not in saved["placements"]
    assert "unknown" not in saved["device_settings"]
    assert "unknown" not in saved["lane_settings"]
    assert "unknown" not in saved["connection_settings"]
    assert saved["device_settings"]["switch"]["acl_lanes"] == "MGMT-IN, STORAGE-NFS-IN, DROP-ALL, QUARANTINE"
    assert saved["device_settings"]["switch"]["blackhole_vlan"] == "998"
    assert saved["device_settings"]["switch"]["storage_vlan"] == "230"
    if scenario == "single_server_local_storage":
        assert "netapp" not in saved["placements"].values()
        assert "netapp" not in saved["device_settings"]
        assert "server-netapp" not in saved["connection_settings"]
        assert saved["lane_settings"]["storage"]["protocol"] == "local datastore"
        assert saved["lane_settings"]["storage"]["target"] == "server-local RAID datastore"
    else:
        assert saved["placements"]["u3"] == "netapp"
        assert saved["device_settings"]["netapp"]["controller_ports"] == "e0a/e0b/e0c/e0d"
        assert len(saved["device_settings"]["netapp"]["notes"]) == 240
        assert saved["lane_settings"]["storage"]["mtu"] == "9100"
        assert saved["connection_settings"]["server-netapp"]["protocol"] == "operator-selected datastore path"

    reloaded = topology_design_drafts.get_topology_design_draft("generated-lab", scenario, subnet)
    assert reloaded["source"] == "saved"
    assert reloaded["placements"] == saved["placements"]
    assert reloaded["device_settings"] == saved["device_settings"]
    assert reloaded["lane_settings"] == saved["lane_settings"]
    assert reloaded["connection_settings"] == saved["connection_settings"]


def test_generated_topology_draft_rejects_bad_identity_values() -> None:
    assert (
        topology_design_drafts.get_topology_design_draft("", "server_netapp_direct", "192.168.1.0/24")["profile_id"]
        == "runtime"
    )

    bad_profile_ids = ["../escape", "lab with spaces", "x" * 121]
    for profile_id in bad_profile_ids:
        with pytest.raises(topology_design_drafts.TopologyDesignDraftError):
            topology_design_drafts.get_topology_design_draft(profile_id, "server_netapp_direct", "192.168.1.0/24")

    with pytest.raises(topology_design_drafts.TopologyDesignDraftError):
        topology_design_drafts.get_topology_design_draft("lab", "not-a-scenario", "192.168.1.0/24")

    with pytest.raises(topology_design_drafts.TopologyDesignDraftError):
        topology_design_drafts.get_topology_design_draft("lab", "server_netapp_direct", "x" * 81)


def _unique_non_empty(values: object) -> bool:
    parts = [value for value in values if value]
    return len(parts) == len(set(parts))


def _planned_ips(device_settings: dict[str, dict[str, str]]) -> list[str]:
    addresses: list[str] = []
    for settings in device_settings.values():
        value = settings.get("management_ip")
        if value:
            addresses.append(value)
    return addresses
