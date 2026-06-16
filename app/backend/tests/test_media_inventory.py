from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import media_inventory as mi
from app.services.media_inventory import get_media_inventory


def test_media_inventory_api_returns_sample_metadata_when_not_configured(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/media-inventory")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "sample"
    assert payload["configured_directories"] == []
    assert payload["warnings"]
    assert {item["category"] for item in payload["items"]} == {"firmware", "iso", "ova"}
    assert all(item["actual_name_redacted"] is True for item in payload["items"])


def test_media_inventory_scans_configured_directory_metadata_only(tmp_path) -> None:
    (tmp_path / "customer-host-install.iso").write_bytes(b"iso")
    (tmp_path / "template-build.OVA").write_bytes(b"ova")
    (tmp_path / "firmware-secret.bin").write_bytes(b"firmware")

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "local"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert [item.extension for item in inventory.items] == [".iso", ".bin", ".ova"]
    assert [item.category for item in inventory.items] == ["iso", "firmware", "ova"]
    assert [item.size_bytes for item in inventory.items] == [3, 8, 3]
    assert {item.source for item in inventory.items} == {"configured-directory-1"}
    assert [item.placeholder_name for item in inventory.items] == [
        "iso-1.iso",
        "firmware-2.bin",
        "ova-3.ova",
    ]
    assert all(item.actual_name_redacted is True for item in inventory.items)
    assert "customer-host-install" not in repr(inventory)


def test_media_inventory_exposes_exact_names_only_for_repo_media_root(monkeypatch, tmp_path) -> None:
    media_root = tmp_path / "artifacts" / "Media"
    media_root.mkdir(parents=True)
    firmware = media_root / "cat9k_iosxe.17.15.05.SPA.bin"
    firmware.write_bytes(b"firmware")
    monkeypatch.setattr(mi, "DEFAULT_MEDIA_ROOT", media_root)

    inventory = mi.get_media_inventory((str(media_root),))

    assert inventory.mode == "local"
    assert len(inventory.items) == 1
    item = inventory.items[0]
    assert item.actual_name_redacted is False
    assert item.file_name == "cat9k_iosxe.17.15.05.SPA.bin"
    assert item.file_path == str(firmware.resolve())
    assert item.detected_vendor == "Cisco"
    assert item.detected_product == "cisco-ios-xe"
    assert item.detected_version == "17.15.5"
    assert item.confidence == "high"


def test_media_inventory_scans_nested_vm_template_metadata_only(tmp_path) -> None:
    template_dir = tmp_path / "private-template"
    template_dir.mkdir()
    (template_dir / "customer-template.ovf").write_bytes(b"ovf")
    (template_dir / "customer-template.vmdk").write_bytes(b"vmdk")

    inventory = get_media_inventory((str(tmp_path),))

    assert [item.extension for item in inventory.items] == [".ovf", ".vmdk"]
    assert [item.category for item in inventory.items] == ["ovf", "vmdk"]
    assert [item.placeholder_name for item in inventory.items] == [
        "ovf-1.ovf",
        "vmdk-2.vmdk",
    ]
    assert all(item.source == "configured-directory-1" for item in inventory.items)
    assert "private-template" not in repr(inventory)
    assert "customer-template" not in repr(inventory)


def test_media_inventory_missing_directory_warning_is_redacted(tmp_path) -> None:
    missing_directory = tmp_path / "customer-media-private"

    inventory = get_media_inventory((str(missing_directory),))

    assert inventory.mode == "unavailable"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert inventory.items == []
    assert inventory.warnings == ["configured-directory-1 does not exist."]
    assert "customer-media-private" not in repr(inventory)


def test_media_inventory_exposes_redacted_firmware_hints_only(tmp_path) -> None:
    (tmp_path / "customer-private-ilo5_319.fwpkg").write_bytes(b"firmware")

    inventory = get_media_inventory((str(tmp_path),))

    assert len(inventory.items) == 1
    item = inventory.items[0]
    assert item.placeholder_name == "firmware-1.fwpkg"
    assert item.product_hints == ["hpe-ilo"]
    assert item.generation_hints == ["ilo5"]
    assert item.version_hint == "3.19"
    assert "customer-private" not in repr(inventory)


def test_media_inventory_exposes_redacted_ontap_hints_only(tmp_path) -> None:
    (tmp_path / "customer-private-netapp-ontap-9.14.1.tgz").write_bytes(b"ontap")

    inventory = get_media_inventory((str(tmp_path),))

    assert len(inventory.items) == 1
    item = inventory.items[0]
    assert item.placeholder_name == "firmware-1.tgz"
    assert item.category == "firmware"
    assert item.product_hints == ["netapp-ontap"]
    assert item.version_hint == "9.14.1"
    assert "customer-private" not in repr(inventory)


def test_media_inventory_exposes_redacted_ontap_q_image_hints_only(tmp_path) -> None:
    (tmp_path / "9131P17_q_image.tgz").write_bytes(b"ontap")

    inventory = get_media_inventory((str(tmp_path),))

    assert len(inventory.items) == 1
    item = inventory.items[0]
    assert item.placeholder_name == "firmware-1.tgz"
    assert item.category == "firmware"
    assert item.product_hints == ["netapp-ontap"]
    assert item.version_hint == "9.13.1P17"
    assert "9131P17" not in repr(inventory)


def test_media_inventory_exposes_redacted_cisco_and_vcenter_hints_only(tmp_path) -> None:
    (tmp_path / "cat9k_iosxe.17.15.05.SPA.bin").write_bytes(b"cisco")
    (tmp_path / "VMware-VCSA-all-8.0.3.iso").write_bytes(b"vcsa")

    inventory = get_media_inventory((str(tmp_path),))

    assert len(inventory.items) == 2
    cisco, vcenter = inventory.items
    assert cisco.placeholder_name == "firmware-1.bin"
    assert cisco.product_hints == ["cisco-ios-xe"]
    assert cisco.version_hint == "17.15.5"
    assert vcenter.placeholder_name == "iso-2.iso"
    assert vcenter.product_hints == ["vmware-vcenter"]
    assert vcenter.version_hint == "8.0.3"
    assert "cat9k" not in repr(inventory)
    assert "VCSA" not in repr(inventory)


def test_media_inventory_detects_service_pack_for_proliant_as_hpe_spp(tmp_path) -> None:
    (tmp_path / "Service Pack for ProLiant 2024.03.iso").write_bytes(b"spp")

    inventory = get_media_inventory((str(tmp_path),))

    assert len(inventory.items) == 1
    item = inventory.items[0]
    assert item.category == "iso"
    assert item.product_hints == ["hpe-spp"]
    assert item.version_hint == "2024.3"
    assert item.actual_name_redacted is True
    assert "Service Pack" not in repr(inventory)


def test_media_inventory_detects_current_gen10_spp_iso_name(tmp_path) -> None:
    (
        tmp_path
        / "P95170_001_gen10spp-2026.05.00.00-SPP2026050000.2026_0527.9.iso"
    ).write_bytes(b"spp")

    inventory = get_media_inventory((str(tmp_path),))

    assert len(inventory.items) == 1
    item = inventory.items[0]
    assert item.category == "iso"
    assert item.product_hints == ["hpe-spp"]
    assert item.generation_hints == ["gen10"]
    assert item.version_hint == "2026.5.0"
    assert item.actual_name_redacted is True
    assert "P95170" not in repr(inventory)
