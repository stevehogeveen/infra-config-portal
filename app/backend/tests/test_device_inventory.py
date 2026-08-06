from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from app.core.database import ensure_device_inventory_dhcp_column


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
        "dhcp_enabled": False,
        "notes": "Rack 2",
    })
    assert created.status_code == 201
    device_id = created.json()["id"]
    assert created.json()["dhcp_enabled"] is False

    listed = client.get("/api/v1/device-inventory")
    assert any(item["id"] == device_id for item in listed.json())

    updated = client.patch(f"/api/v1/device-inventory/{device_id}", json={
        "display_name": "Packet broker A",
        "host": None,
    })
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Packet broker A"
    assert updated.json()["host"] is None
    assert updated.json()["dhcp_enabled"] is False

    deleted = client.delete(f"/api/v1/device-inventory/{device_id}")
    assert deleted.status_code == 200
    assert all(item["id"] != device_id for item in client.get("/api/v1/device-inventory").json())
    assert os.environ["ILO_TEST_HOST"] == canonical_ilo_host


def test_device_inventory_validates_required_fields(client) -> None:
    response = client.post("/api/v1/device-inventory", json={"device_type": "other", "display_name": "  "})
    assert response.status_code == 422


def test_device_inventory_dhcp_round_trip_enforces_observed_host(client) -> None:
    created = client.post("/api/v1/device-inventory", json={
        "device_type": "custom_appliance",
        "display_name": "DHCP appliance",
        "host": "192.0.2.44",
        "dhcp_enabled": True,
    })
    assert created.status_code == 201
    device = created.json()
    assert device["dhcp_enabled"] is True
    assert device["host"] == "192.0.2.44"
    assert any(
        item["id"] == device["id"] and item["dhcp_enabled"] is True
        for item in client.get("/api/v1/device-inventory").json()
    )

    rejected = client.patch(
        f"/api/v1/device-inventory/{device['id']}",
        json={"host": "192.0.2.45"},
    )
    assert rejected.status_code == 422
    assert "last observed address" in rejected.json()["detail"]

    static = client.patch(
        f"/api/v1/device-inventory/{device['id']}",
        json={"dhcp_enabled": False},
    )
    assert static.status_code == 200
    assert static.json()["dhcp_enabled"] is False
    assert static.json()["host"] == "192.0.2.44"

    changed = client.patch(
        f"/api/v1/device-inventory/{device['id']}",
        json={"host": "192.0.2.46"},
    )
    assert changed.status_code == 200
    assert changed.json()["host"] == "192.0.2.46"

    dhcp_again = client.patch(
        f"/api/v1/device-inventory/{device['id']}",
        json={"dhcp_enabled": True},
    )
    assert dhcp_again.status_code == 200
    assert dhcp_again.json()["host"] == "192.0.2.46"

    static_again = client.patch(
        f"/api/v1/device-inventory/{device['id']}",
        json={"dhcp_enabled": False},
    )
    assert static_again.status_code == 200
    assert static_again.json()["host"] == "192.0.2.46"


def test_device_inventory_dhcp_column_guard_is_idempotent_with_existing_data(tmp_path) -> None:
    target = tmp_path / "inventory.db"
    target_engine = create_engine(f"sqlite:///{target}")
    with target_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE device_inventory ("
            "id VARCHAR(36) PRIMARY KEY, host VARCHAR(300) NULL)"
        ))
        connection.execute(text(
            "INSERT INTO device_inventory (id, host) VALUES ('existing', '192.0.2.80')"
        ))

    ensure_device_inventory_dhcp_column(target_engine)
    ensure_device_inventory_dhcp_column(target_engine)

    with target_engine.connect() as connection:
        row = connection.execute(text(
            "SELECT host, dhcp_enabled FROM device_inventory WHERE id = 'existing'"
        )).one()
    assert row == ("192.0.2.80", 0)


def test_dhcp_seeded_device_syncs_observed_host_from_provider_config(
    client, monkeypatch
) -> None:
    monkeypatch.setenv("CISCO_TARGET_IP", "192.0.2.60")
    devices = client.get("/api/v1/device-inventory").json()
    cisco = next(item for item in devices if item["device_type"] == "cisco_switch")

    flipped = client.patch(
        f"/api/v1/device-inventory/{cisco['id']}",
        json={"dhcp_enabled": True},
    )
    assert flipped.status_code == 200

    # The provider config moves (a new lease was configured); the DHCP
    # device's observed address follows on the next list.
    monkeypatch.setenv("CISCO_TARGET_IP", "192.0.2.61")
    refreshed = client.get("/api/v1/device-inventory").json()
    cisco_after = next(item for item in refreshed if item["id"] == cisco["id"])
    assert cisco_after["host"] == "192.0.2.61"


def test_static_seeded_device_host_is_never_overwritten_by_provider_config(
    client, monkeypatch
) -> None:
    monkeypatch.setenv("CISCO_TARGET_IP", "192.0.2.70")
    devices = client.get("/api/v1/device-inventory").json()
    cisco = next(item for item in devices if item["device_type"] == "cisco_switch")
    assert cisco["dhcp_enabled"] is False

    edited = client.patch(
        f"/api/v1/device-inventory/{cisco['id']}",
        json={"host": "10.99.0.4"},
    )
    assert edited.status_code == 200

    monkeypatch.setenv("CISCO_TARGET_IP", "192.0.2.71")
    refreshed = client.get("/api/v1/device-inventory").json()
    cisco_after = next(item for item in refreshed if item["id"] == cisco["id"])
    assert cisco_after["host"] == "10.99.0.4"


def test_custom_dhcp_device_keeps_last_known_host_without_a_source(client) -> None:
    created = client.post("/api/v1/device-inventory", json={
        "device_type": "packet_broker",
        "display_name": "Broker",
        "host": "192.0.2.90",
        "dhcp_enabled": True,
    })
    assert created.status_code == 201

    listed = client.get("/api/v1/device-inventory").json()
    broker = next(item for item in listed if item["id"] == created.json()["id"])
    assert broker["host"] == "192.0.2.90"


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
