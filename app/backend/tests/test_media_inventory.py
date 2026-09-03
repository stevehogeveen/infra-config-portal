from __future__ import annotations

from types import SimpleNamespace

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


def test_real_lab_media_inventory_without_configured_dirs_returns_no_sample_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setattr(mi, "settings", SimpleNamespace(provider_mode="local-lab-readwrite", media_inventory_dirs=()))

    inventory = mi.get_media_inventory()

    assert inventory.mode == "unavailable"
    assert inventory.items == []
    assert inventory.warnings == [
        "MEDIA_INVENTORY_DIRS is not configured; no real media inventory was returned."
    ]


def test_media_inventory_scans_configured_directory_metadata_only(tmp_path) -> None:
    (tmp_path / "customer-host-install.iso").write_bytes(b"iso")
    (tmp_path / "template-build.OVA").write_bytes(b"ova")
    (tmp_path / "firmware-secret.bin").write_bytes(b"firmware")

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "local"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert inventory.configured_directory_paths == [str(tmp_path)]
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


def test_media_inventory_redacts_strange_and_long_file_names(tmp_path) -> None:
    strange_name = "customer [secret]; $(whoami) ilo-5_v0319 snowman-\u2603.bin"
    long_name = f"{'private-product-name-' * 5}VMware-VCSA-all-8.0.3.iso"
    (tmp_path / strange_name).write_bytes(b"firmware")
    (tmp_path / long_name).write_bytes(b"vcsa")

    inventory = get_media_inventory((str(tmp_path),))

    assert [item.placeholder_name for item in inventory.items] == [
        "firmware-1.bin",
        "iso-2.iso",
    ]
    assert [item.product_hints for item in inventory.items] == [
        ["hpe-ilo"],
        ["vmware-vcenter"],
    ]
    assert [item.version_hint for item in inventory.items] == ["3.19", "8.0.3"]
    assert all(item.actual_name_redacted is True for item in inventory.items)
    rendered = repr(inventory)
    assert "customer [secret]" not in rendered
    assert "private-product-name" not in rendered
    assert "snowman" not in rendered


def test_media_inventory_dedupes_duplicate_configured_directories(tmp_path) -> None:
    (tmp_path / "installer.iso").write_bytes(b"iso")

    inventory = get_media_inventory((str(tmp_path), str(tmp_path)))

    assert inventory.mode == "local"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert [item.source for item in inventory.items] == ["configured-directory-1"]
    assert [item.placeholder_name for item in inventory.items] == [
        "iso-1.iso",
    ]
    assert inventory.warnings == ["1 duplicate configured media directory was ignored."]
    assert all(item.actual_name_redacted is True for item in inventory.items)


def test_media_inventory_dedupes_equivalent_path_spellings(tmp_path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    (media_root / "installer.iso").write_bytes(b"iso")

    inventory = get_media_inventory((str(media_root), str(media_root / ".")))

    assert inventory.mode == "local"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert [item.placeholder_name for item in inventory.items] == ["iso-1.iso"]
    assert inventory.warnings == ["1 duplicate configured media directory was ignored."]


def test_media_inventory_skips_files_that_disappear_during_scan(monkeypatch, tmp_path) -> None:
    stable = tmp_path / "installer.iso"
    vanished = tmp_path / "vanished.ova"
    stable.write_bytes(b"iso")
    vanished.write_bytes(b"ova")
    original_inventory_item = mi._inventory_item

    def flaky_inventory_item(path, index, source_label):  # noqa: ANN001, ANN202
        if path.name == "vanished.ova":
            return None
        return original_inventory_item(path, index, source_label)

    monkeypatch.setattr(mi, "_inventory_item", flaky_inventory_item)

    inventory = get_media_inventory((str(tmp_path),))

    assert [item.placeholder_name for item in inventory.items] == ["iso-1.iso"]
    assert inventory.warnings == ["configured-directory-1 contained a file that could not be read."]
    assert "vanished" not in repr(inventory)


def test_media_inventory_skips_files_that_disappear_during_size_probe(monkeypatch, tmp_path) -> None:
    stable = tmp_path / "installer.iso"
    vanished = tmp_path / "vanished.ova"
    stable.write_bytes(b"iso")
    vanished.write_bytes(b"ova")
    original_file_size = mi.file_size

    def disappearing_file_size(path):  # noqa: ANN001, ANN202
        if path == vanished:
            return None
        return original_file_size(path)

    monkeypatch.setattr(mi, "file_size", disappearing_file_size)

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "local"
    assert [item.placeholder_name for item in inventory.items] == ["iso-1.iso"]
    assert inventory.warnings == ["configured-directory-1 contained a file that could not be read."]
    assert "vanished" not in repr(inventory)


def test_media_inventory_keeps_readable_files_when_one_file_probe_fails(monkeypatch, tmp_path) -> None:
    stable = tmp_path / "installer.iso"
    locked = tmp_path / "locked.ova"
    stable.write_bytes(b"iso")
    locked.write_bytes(b"ova")
    original_is_file = type(tmp_path).is_file

    def locked_is_file(path):  # noqa: ANN001, ANN202
        if path == locked:
            raise OSError("locked")
        return original_is_file(path)

    monkeypatch.setattr(type(tmp_path), "is_file", locked_is_file)

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "local"
    assert [item.placeholder_name for item in inventory.items] == ["iso-1.iso"]
    assert inventory.warnings == ["configured-directory-1 contained 1 file that could not be read."]
    assert "locked" not in repr(inventory)


def test_media_inventory_keeps_readable_files_when_symlink_probe_fails(monkeypatch, tmp_path) -> None:
    stable = tmp_path / "installer.iso"
    locked = tmp_path / "locked.ova"
    stable.write_bytes(b"iso")
    locked.write_bytes(b"ova")
    original_is_symlink = type(tmp_path).is_symlink

    def locked_is_symlink(path):  # noqa: ANN001, ANN202
        if path == locked:
            raise OSError("locked")
        return original_is_symlink(path)

    monkeypatch.setattr(type(tmp_path), "is_symlink", locked_is_symlink)

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "local"
    assert [item.placeholder_name for item in inventory.items] == ["iso-1.iso"]
    assert inventory.warnings == ["configured-directory-1 contained 1 file that could not be read."]
    assert "locked" not in repr(inventory)


def test_media_inventory_empty_directory_returns_local_mode_with_no_items(tmp_path) -> None:
    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "local"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert inventory.items == []
    assert inventory.warnings == []


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


def test_media_inventory_self_heals_directory_exists_errors(monkeypatch, tmp_path) -> None:
    original_exists = type(tmp_path).exists

    def locked_exists(path):  # noqa: ANN001, ANN202
        if path == tmp_path:
            raise OSError("locked")
        return original_exists(path)

    monkeypatch.setattr(type(tmp_path), "exists", locked_exists)

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "unavailable"
    assert inventory.items == []
    assert inventory.warnings == ["configured-directory-1 could not be read."]
    assert str(tmp_path) not in repr(inventory)


def test_media_inventory_self_heals_directory_type_errors(monkeypatch, tmp_path) -> None:
    original_is_dir = type(tmp_path).is_dir

    def locked_is_dir(path):  # noqa: ANN001, ANN202
        if path == tmp_path:
            raise OSError("locked")
        return original_is_dir(path)

    monkeypatch.setattr(type(tmp_path), "is_dir", locked_is_dir)

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "unavailable"
    assert inventory.items == []
    assert inventory.warnings == ["configured-directory-1 could not be read."]
    assert str(tmp_path) not in repr(inventory)


def test_media_inventory_self_heals_recursive_scan_errors(monkeypatch, tmp_path) -> None:
    original_rglob = type(tmp_path).rglob

    def locked_rglob(path, pattern):  # noqa: ANN001, ANN202
        if path == tmp_path:
            raise OSError("recursive scan failed")
        return original_rglob(path, pattern)

    monkeypatch.setattr(type(tmp_path), "rglob", locked_rglob)

    inventory = get_media_inventory((str(tmp_path),))

    assert inventory.mode == "unavailable"
    assert inventory.items == []
    assert inventory.warnings == ["configured-directory-1 could not be read."]
    assert str(tmp_path) not in repr(inventory)


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
