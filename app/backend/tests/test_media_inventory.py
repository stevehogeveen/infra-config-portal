from __future__ import annotations

from fastapi.testclient import TestClient

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


def test_media_inventory_missing_directory_warning_is_redacted(tmp_path) -> None:
    missing_directory = tmp_path / "customer-media-private"

    inventory = get_media_inventory((str(missing_directory),))

    assert inventory.mode == "unavailable"
    assert inventory.configured_directories == ["configured-directory-1"]
    assert inventory.items == []
    assert inventory.warnings == ["configured-directory-1 does not exist."]
    assert "customer-media-private" not in repr(inventory)
