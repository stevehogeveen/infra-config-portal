from __future__ import annotations

import os


def test_device_inventory_seeds_existing_four_devices(client) -> None:
    response = client.get("/api/v1/device-inventory")

    assert response.status_code == 200
    devices = response.json()
    assert {item["device_type"] for item in devices} == {"ilo", "cisco_switch", "esxi_host", "netapp"}
    assert next(item for item in devices if item["device_type"] == "ilo")["host"] == os.environ["ILO_TEST_HOST"]


def test_device_inventory_crud_round_trip_does_not_change_provider_config(client) -> None:
    canonical_ilo_host = os.environ["ILO_TEST_HOST"]
    created = client.post("/api/v1/device-inventory", json={
        "device_type": "custom_appliance",
        "display_name": "Packet broker",
        "host": "lab-packet-broker.local",
        "notes": "Rack 2",
    })
    assert created.status_code == 201
    device_id = created.json()["id"]

    listed = client.get("/api/v1/device-inventory")
    assert any(item["id"] == device_id for item in listed.json())

    updated = client.patch(f"/api/v1/device-inventory/{device_id}", json={
        "display_name": "Packet broker A",
        "host": None,
    })
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Packet broker A"
    assert updated.json()["host"] is None

    deleted = client.delete(f"/api/v1/device-inventory/{device_id}")
    assert deleted.status_code == 200
    assert all(item["id"] != device_id for item in client.get("/api/v1/device-inventory").json())
    assert os.environ["ILO_TEST_HOST"] == canonical_ilo_host


def test_device_inventory_validates_required_fields(client) -> None:
    response = client.post("/api/v1/device-inventory", json={"device_type": "other", "display_name": "  "})
    assert response.status_code == 422


def test_device_inventory_missing_device_is_404(client) -> None:
    assert client.patch("/api/v1/device-inventory/missing", json={"display_name": "Nope"}).status_code == 404
    assert client.delete("/api/v1/device-inventory/missing").status_code == 404


def test_deleting_every_seeded_device_does_not_reseed(client) -> None:
    devices = client.get("/api/v1/device-inventory").json()
    for device in devices:
        assert client.delete(f"/api/v1/device-inventory/{device['id']}").status_code == 200
    assert client.get("/api/v1/device-inventory").json() == []


def test_seed_recovers_when_rows_exist_without_the_marker(client, db_session) -> None:
    """Seed rows without the marker (crashed/raced earlier request) must not
    500 the list endpoint forever via the seed_key UNIQUE constraint."""
    from app.models import DeviceInventory, DeviceInventoryState

    db_session.add(DeviceInventory(
        device_type="ilo",
        display_name="HPE iLO",
        host="192.168.1.201",
        seed_key="ilo-primary",
    ))
    db_session.commit()

    response = client.get("/api/v1/device-inventory")

    assert response.status_code == 200
    devices = response.json()
    seed_types = [item["device_type"] for item in devices]
    # The missing three seeds were backfilled, the surviving row was not
    # duplicated, and the marker now exists so the seed never runs again.
    assert sorted(seed_types) == sorted(["ilo", "cisco_switch", "esxi_host", "netapp"])
    assert db_session.get(DeviceInventoryState, "legacy-seed-v1") is not None
