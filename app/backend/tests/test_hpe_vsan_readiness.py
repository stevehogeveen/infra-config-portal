from app.schemas import HpeStorageDiscoveryRead
from app.services import hpe_raid, hpe_vsan_readiness


FP_BOOT = "a" * 64
FP_FREE = "b" * 64


def _probe() -> dict:
    return {
        "systems": [{"Model": "ProLiant DL380 Gen10"}],
        "storage": {
            "controllers": [{"Model": "HPE Smart Array P408i-a SR Gen10", "FirmwareVersion": "1.66", "CurrentOperatingMode": "Mixed"}],
            "physical_drives": [
                {"@odata.id": "/Systems/1/Storage/A/Drives/1", "SerialNumber": "boot", "hardware_identity_fingerprint_sha256": FP_BOOT},
                {"@odata.id": "/Systems/1/Storage/A/Drives/2", "SerialNumber": "free", "hardware_identity_fingerprint_sha256": FP_FREE},
                {"@odata.id": "/Systems/1/SmartStorage/A/DiskDrives/1", "Bay": "1I:1:1", "CapacityBytes": 1_000, "MediaType": "SSD", "Status": {"Health": "OK"}, "hardware_identity_fingerprint_sha256": FP_BOOT},
                {"@odata.id": "/Systems/1/SmartStorage/A/DiskDrives/2", "Bay": "1I:1:2", "CapacityBytes": 2_000, "MediaType": "SSD", "Status": {"Health": "OK"}, "hardware_identity_fingerprint_sha256": FP_FREE},
            ],
            "logical_drives": [{"Name": "ESXi boot", "Links": {"Drives": [{"@odata.id": "/Systems/1/Storage/A/Drives/1"}]}}],
        },
    }


def test_discovery_pairs_cross_view_volume_members_by_hardware_fingerprint() -> None:
    discovery = hpe_raid.get_hpe_storage_discovery(probe=_probe())
    member = discovery.logical_drives[0]["Links"]["Drives"][0]
    assert member["hardware_identity_fingerprint_sha256"] == FP_BOOT
    assert {drive["bay_id"] for drive in discovery.physical_drives} == {"1I:1:1", "1I:1:2"}


def test_vsan_readiness_marks_boot_volume_and_unconfigured_drive(monkeypatch) -> None:
    discovery = hpe_raid.get_hpe_storage_discovery(probe=_probe())
    monkeypatch.setattr(hpe_vsan_readiness, "get_hpe_storage_discovery", lambda: discovery)
    result = hpe_vsan_readiness.get_hpe_vsan_readiness()
    assert [drive["vsan_status"] for drive in result.drives] == ["in_raid_volume", "passthrough_ready"]
    assert result.drives[0]["volume_name"] == "ESXi boot"
    assert result.summary["passthrough_ready_count"] == 1
    assert result.summary["passthrough_ready_capacity_bytes"] == 2_000
    assert result.controller["current_operating_mode"] == "Mixed"
    assert result.apply_enabled is False


def test_vsan_readiness_never_guesses_without_fingerprint(monkeypatch) -> None:
    discovery = hpe_raid.get_hpe_storage_discovery(probe=_probe())
    discovery.physical_drives[1].pop("hardware_identity_fingerprint_sha256")
    monkeypatch.setattr(hpe_vsan_readiness, "get_hpe_storage_discovery", lambda: discovery)
    result = hpe_vsan_readiness.get_hpe_vsan_readiness()
    assert result.drives[1]["vsan_status"] == "unknown"


def test_vsan_readiness_unpaired_volume_member_makes_nonmembers_unknown(monkeypatch) -> None:
    discovery = hpe_raid.get_hpe_storage_discovery(probe=_probe())
    discovery.logical_drives[0]["Links"]["Drives"][0].pop("hardware_identity_fingerprint_sha256")
    monkeypatch.setattr(hpe_vsan_readiness, "get_hpe_storage_discovery", lambda: discovery)
    result = hpe_vsan_readiness.get_hpe_vsan_readiness()
    assert {drive["vsan_status"] for drive in result.drives} == {"unknown"}


def test_vsan_readiness_memberless_volume_never_clears_other_drives(monkeypatch) -> None:
    """The Uplands DL380 regression: the probe held only SmartStorage views,
    whose volumes carry a DataDrives collection reference and no inline
    members. With memberships unprovable, every drive must be unknown - the
    pre-fix behavior marked all 16 drives passthrough_ready, including the
    RAID members."""
    probe = _probe()
    probe["storage"]["physical_drives"] = [
        {"@odata.id": "/Systems/1/SmartStorage/A/DiskDrives/1", "Bay": "1I:1:1", "CapacityBytes": 1_000, "MediaType": "SSD", "Status": {"Health": "OK"}, "hardware_identity_fingerprint_sha256": FP_BOOT},
        {"@odata.id": "/Systems/1/SmartStorage/A/DiskDrives/2", "Bay": "1I:1:2", "CapacityBytes": 2_000, "MediaType": "SSD", "Status": {"Health": "OK"}, "hardware_identity_fingerprint_sha256": FP_FREE},
    ]
    probe["storage"]["logical_drives"] = [
        {"Name": "HpeSmartStorageLogicalDrive", "Links": {"DataDrives": {"@odata.id": "/Systems/1/SmartStorage/A/LogicalDrives/1/DataDrives/"}}}
    ]
    discovery = hpe_raid.get_hpe_storage_discovery(probe=probe)
    monkeypatch.setattr(hpe_vsan_readiness, "get_hpe_storage_discovery", lambda: discovery)
    result = hpe_vsan_readiness.get_hpe_vsan_readiness()
    assert {drive["vsan_status"] for drive in result.drives} == {"unknown"}
    assert result.summary["passthrough_ready_count"] == 0


def test_vsan_readiness_no_inventory_requests_discovery_first(monkeypatch) -> None:
    empty = HpeStorageDiscoveryRead(
        provider_id="ilo-redfish",
        source="cached iLO Redfish probe",
        next_safe_action="Run discovery.",
    )
    monkeypatch.setattr(hpe_vsan_readiness, "get_hpe_storage_discovery", lambda: empty)
    result = hpe_vsan_readiness.get_hpe_vsan_readiness()
    assert result.storage_inventory_available is False
    assert result.drives == []
    assert result.next_safe_action == "Run iLO Inventory Read first."
