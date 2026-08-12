"""Composable lab shape: what the operator describes, and what it derives.

The kit says which rack servers form the cluster and what backs their shared
storage. Everything the rest of the app already branches on (netapp_enabled,
storage_protocol, deployment_mode) is derived from that, so these tests pin the
derivation as much as the new fields.
"""

from __future__ import annotations

import pytest

from app.services.lab_profiles import LabProfileError, validate_lab_shape
from app.services.lab_topology import derive_lab_topology


def _components(**features):
    return derive_lab_topology(
        profile_topology=None,
        subnet_cidr="10.238.207.0/24",
        global_settings={},
        address_plan={},
        devices={},
        features=features,
        default_subnet="10.238.207.0/24",
    )


@pytest.mark.parametrize(
    ("shared_storage", "netapp_enabled", "storage_location", "storage_protocol"),
    [
        ("netapp_nfs", True, "netapp_shared", "nfs"),
        ("netapp_iscsi", True, "netapp_shared", "iscsi"),
        ("vsan", False, "server_local", "local"),
        ("none", False, "server_local", "local"),
    ],
)
def test_shared_storage_derives_legacy_feature_fields(
    shared_storage, netapp_enabled, storage_location, storage_protocol
):
    features = _components(shared_storage=shared_storage)["features"]

    assert features["shared_storage"] == shared_storage
    assert features["netapp_enabled"] is netapp_enabled
    assert features["storage_location"] == storage_location
    assert features["storage_protocol"] == storage_protocol


def test_vsan_reports_local_storage_mode_so_the_installer_gate_still_matches():
    # esxi_installer_artifact compares deployment_mode by exact string. vSAN
    # consumes local disks, so the local-storage mode is the honest match.
    features = _components(shared_storage="vsan", cluster_member_device_ids=["a", "b", "c"])["features"]

    assert features["deployment_mode"] == "single_server_local_storage"
    assert features["storage_location"] == "server_local"


def test_vsan_with_vcenter_is_supported_despite_having_no_netapp():
    # The legacy truth table calls vCenter-without-NetApp unsupported. A vSAN
    # cluster is exactly that shape and is valid, so it must not be flagged.
    features = _components(
        shared_storage="vsan",
        vcenter_enabled=True,
        cluster_member_device_ids=["a", "b", "c"],
    )["features"]

    assert features["deployment_supported"] is True
    assert features["deployment_mode"] != "unsupported_vcenter_without_netapp"


def test_vcenter_without_any_shared_storage_stays_unsupported():
    features = _components(shared_storage="none", vcenter_enabled=True)["features"]

    assert features["deployment_supported"] is False


def test_label_describes_the_lab_rather_than_the_internal_mode():
    features = _components(
        shared_storage="vsan",
        vcenter_enabled=True,
        cluster_member_device_ids=["a", "b", "c"],
    )["features"]

    assert features["deployment_label"] == "3 hosts, vCenter, vSAN"


def test_single_host_label_stays_singular():
    features = _components(shared_storage="none", cluster_member_device_ids=["only"])["features"]

    assert features["deployment_label"] == "1 host, local storage"


def test_cluster_members_are_deduplicated_and_order_preserved():
    features = _components(cluster_member_device_ids=["b", "a", "b", "  ", "c"])["features"]

    assert features["cluster_member_device_ids"] == ["b", "a", "c"]


def test_kits_saved_before_this_field_keep_their_meaning():
    # An older NetApp iSCSI kit never wrote shared_storage; it must not be
    # silently downgraded to "none" and lose its NetApp.
    features = _components(netapp_enabled=True, storage_protocol="iscsi")["features"]

    assert features["shared_storage"] == "netapp_iscsi"
    assert features["netapp_enabled"] is True
    assert features["storage_protocol"] == "iscsi"


def test_deriving_twice_gives_the_same_answer():
    # A save runs the derivation twice, feeding the first result back in as
    # input. An inferred value must not come back looking like an explicit
    # choice, or the second pass reaches a different lab.
    first = _components()["features"]
    second = derive_lab_topology(
        profile_topology=None,
        subnet_cidr="10.238.207.0/24",
        global_settings={},
        address_plan={},
        devices={},
        features=first,
        default_subnet="10.238.207.0/24",
    )["features"]

    for field in ("shared_storage", "netapp_enabled", "storage_protocol", "storage_location"):
        assert second[field] == first[field], field


def test_deriving_twice_keeps_netapp_addresses():
    # The concrete regression: a kit with no features saved its NetApp LIFs,
    # and the second derivation pass cleared them.
    plan = {"subnet": "192.0.2.0/24", "netapp_iscsi_lifs": ["192.0.2.21", "192.0.2.22"]}
    first = derive_lab_topology(
        profile_topology=None, subnet_cidr=None, global_settings={},
        address_plan=plan, devices={}, features={}, default_subnet="192.0.2.0/24",
    )
    second = derive_lab_topology(
        profile_topology=None, subnet_cidr=None, global_settings=first["global_settings"],
        address_plan=first["address_plan"], devices={}, features=first["features"],
        default_subnet="192.0.2.0/24",
    )

    assert second["address_plan"]["netapp_iscsi_lifs"] == ["192.0.2.21", "192.0.2.22"]


def _payload(**features):
    return {"name": "Shape kit", "subnet_cidr": "10.238.207.0/24", "features": features}


@pytest.fixture()
def rack(monkeypatch):
    """Pin the rack contents so these rules do not depend on the local database."""

    def _install(device_ids=("a", "b", "c"), has_netapp=True):
        monkeypatch.setattr(
            "app.services.lab_profiles._inventory_server_device_ids",
            lambda: set(device_ids),
        )
        monkeypatch.setattr(
            "app.services.lab_profiles._inventory_has_netapp",
            lambda: has_netapp,
        )

    return _install


def test_vsan_below_three_hosts_is_refused_with_the_count():
    with pytest.raises(LabProfileError) as excinfo:
        validate_lab_shape(_payload(shared_storage="vsan", cluster_member_device_ids=["a", "b"]))

    assert "at least 3 hosts" in str(excinfo.value)
    assert "2" in str(excinfo.value)


def test_vcenter_needs_more_than_one_host(rack):
    rack(device_ids=("only",))

    with pytest.raises(LabProfileError) as excinfo:
        validate_lab_shape(_payload(vcenter_enabled=True, cluster_member_device_ids=["only"]))

    assert "at least 2 hosts" in str(excinfo.value)


def test_a_kit_saved_before_cluster_members_existed_still_saves():
    # Older vCenter kits never listed members, so no host count can be inferred
    # for them. The new rule must not refuse a lab the app always supported.
    validate_lab_shape(_payload(vcenter_enabled=True, netapp_enabled=True, storage_protocol="nfs"))


def test_three_host_vsan_cluster_is_accepted(rack):
    rack(device_ids=("a", "b", "c"))

    validate_lab_shape(
        _payload(shared_storage="vsan", vcenter_enabled=True, cluster_member_device_ids=["a", "b", "c"])
    )


def test_single_server_local_storage_is_accepted(rack):
    rack(device_ids=("only",))

    validate_lab_shape(_payload(shared_storage="none", cluster_member_device_ids=["only"]))


def test_netapp_storage_without_a_netapp_in_the_rack_is_refused(rack):
    rack(device_ids=("a", "b"), has_netapp=False)

    with pytest.raises(LabProfileError) as excinfo:
        validate_lab_shape(_payload(shared_storage="netapp_nfs", cluster_member_device_ids=["a", "b"]))

    assert "no NetApp appears in the rack" in str(excinfo.value)


def test_cluster_host_removed_from_the_rack_is_refused(rack):
    rack(device_ids=("a", "b"))

    with pytest.raises(LabProfileError) as excinfo:
        validate_lab_shape(_payload(shared_storage="none", cluster_member_device_ids=["a", "gone"]))

    assert "no longer in the rack" in str(excinfo.value)


def test_unreadable_inventory_never_blocks_saving(monkeypatch):
    monkeypatch.setattr("app.services.lab_profiles._inventory_devices", lambda: None)

    validate_lab_shape(_payload(shared_storage="netapp_nfs", cluster_member_device_ids=["a", "b"]))
