from __future__ import annotations

from app.models import DeviceInventory, HpeRaidIntent, IloDeviceCredential, IloSetupIntent


ACCESS_PATH = "/api/v1/providers/ilo-redfish/access-settings"
SETUP_INTENT_PATH = "/api/v1/providers/ilo-redfish/setup-intent"
RAID_INTENT_PATH = "/api/v1/providers/ilo-redfish/hpe-raid-intent"
PROVIDER_ID = "ilo-redfish"


def _create_ilo(client, *, display_name: str, host: str) -> str:
    response = client.post(
        "/api/v1/device-inventory",
        json={
            "device_type": "ilo",
            "display_name": display_name,
            "host": host,
            "dhcp_enabled": False,
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def test_access_credentials_are_isolated_redacted_and_preserved_per_device(
    client,
    db_session,
) -> None:
    device_a = _create_ilo(client, display_name="Mock iLO A", host="192.0.2.11")
    device_b = _create_ilo(client, display_name="Mock iLO B", host="192.0.2.12")
    password_a = "mock-device-a-password"
    password_b = "mock-device-b-password"

    saved_a = client.put(
        ACCESS_PATH,
        params={"device_id": device_a},
        json={
            "host": "192.0.2.21",
            "username": "Administrator-A",
            "password": password_a,
            "verify_tls": False,
        },
    )
    assert saved_a.status_code == 200
    saved_a_payload = saved_a.json()
    assert saved_a_payload["device_id"] == device_a
    assert saved_a_payload["host"] == "192.0.2.21"
    assert saved_a_payload["username"] == "Administrator-A"
    assert saved_a_payload["username_configured"] is True
    assert saved_a_payload["password_configured"] is True
    assert saved_a_payload["verify_tls"] is False
    assert "password" not in saved_a_payload
    assert password_a not in saved_a.text

    untouched_b = client.get(ACCESS_PATH, params={"device_id": device_b})
    assert untouched_b.status_code == 200
    assert untouched_b.json()["device_id"] == device_b
    assert untouched_b.json()["host"] == "192.0.2.12"
    assert untouched_b.json()["username"] is None
    assert untouched_b.json()["username_configured"] is False
    assert untouched_b.json()["password_configured"] is False

    saved_b = client.put(
        ACCESS_PATH,
        params={"device_id": device_b},
        json={
            "host": "192.0.2.22",
            "username": "Administrator-B",
            "password": password_b,
            "verify_tls": True,
        },
    )
    assert saved_b.status_code == 200
    assert saved_b.json()["device_id"] == device_b
    assert saved_b.json()["host"] == "192.0.2.22"
    assert saved_b.json()["username"] == "Administrator-B"
    assert saved_b.json()["password_configured"] is True
    assert "password" not in saved_b.json()
    assert password_b not in saved_b.text

    # The frontend deliberately sends null after the password field is cleared.
    # That means "preserve the saved password", not "erase the credential".
    updated_a = client.put(
        ACCESS_PATH,
        params={"device_id": device_a},
        json={"username": "Administrator-A2", "password": None},
    )
    assert updated_a.status_code == 200
    assert updated_a.json()["username"] == "Administrator-A2"
    assert updated_a.json()["password_configured"] is True
    assert "password" not in updated_a.json()
    assert password_a not in updated_a.text

    reread_a = client.get(ACCESS_PATH, params={"device_id": device_a})
    reread_b = client.get(ACCESS_PATH, params={"device_id": device_b})
    assert reread_a.status_code == reread_b.status_code == 200
    assert reread_a.json()["host"] == "192.0.2.21"
    assert reread_a.json()["username"] == "Administrator-A2"
    assert reread_b.json()["host"] == "192.0.2.22"
    assert reread_b.json()["username"] == "Administrator-B"
    assert password_a not in reread_a.text
    assert password_b not in reread_b.text

    db_session.expire_all()
    credential_a = db_session.get(IloDeviceCredential, device_a)
    credential_b = db_session.get(IloDeviceCredential, device_b)
    assert credential_a is not None
    assert credential_b is not None
    assert credential_a.credentials_json["password"] == password_a
    assert credential_b.credentials_json["password"] == password_b
    assert credential_a.credentials_json["username"] == "Administrator-A2"
    assert credential_b.credentials_json["username"] == "Administrator-B"
    inventory_a = db_session.get(DeviceInventory, device_a)
    inventory_b = db_session.get(DeviceInventory, device_b)
    assert inventory_a is not None
    assert inventory_b is not None
    assert inventory_a.host == "192.0.2.21"
    assert inventory_b.host == "192.0.2.22"


def test_setup_intents_are_isolated_per_device(client, db_session) -> None:
    device_a = _create_ilo(client, display_name="Mock setup iLO A", host="198.51.100.11")
    device_b = _create_ilo(client, display_name="Mock setup iLO B", host="198.51.100.12")

    saved_a = client.put(
        SETUP_INTENT_PATH,
        params={"device_id": device_a},
        json={
            "network": {"hostname": "mock-ilo-a"},
            "notes": "Device A setup intent",
        },
    )
    assert saved_a.status_code == 200
    assert saved_a.json()["device_id"] == device_a
    assert saved_a.json()["network"]["hostname"] == "mock-ilo-a"

    untouched_b = client.get(SETUP_INTENT_PATH, params={"device_id": device_b})
    assert untouched_b.status_code == 200
    assert untouched_b.json()["device_id"] == device_b
    assert untouched_b.json()["network"]["hostname"] is None
    assert untouched_b.json()["notes"] is None

    saved_b = client.put(
        SETUP_INTENT_PATH,
        params={"device_id": device_b},
        json={
            "network": {"hostname": "mock-ilo-b"},
            "notes": "Device B setup intent",
        },
    )
    assert saved_b.status_code == 200

    reread_a = client.get(SETUP_INTENT_PATH, params={"device_id": device_a})
    reread_b = client.get(SETUP_INTENT_PATH, params={"device_id": device_b})
    assert reread_a.status_code == reread_b.status_code == 200
    assert reread_a.json()["network"]["hostname"] == "mock-ilo-a"
    assert reread_a.json()["notes"] == "Device A setup intent"
    assert reread_b.json()["network"]["hostname"] == "mock-ilo-b"
    assert reread_b.json()["notes"] == "Device B setup intent"

    db_session.expire_all()
    intent_a = db_session.get(IloSetupIntent, (device_a, PROVIDER_ID))
    intent_b = db_session.get(IloSetupIntent, (device_b, PROVIDER_ID))
    assert intent_a is not None
    assert intent_b is not None
    assert intent_a.intent_json["network"]["hostname"] == "mock-ilo-a"
    assert intent_b.intent_json["network"]["hostname"] == "mock-ilo-b"


def test_raid_intents_are_isolated_per_device(client, db_session) -> None:
    device_a = _create_ilo(client, display_name="Mock RAID iLO A", host="203.0.113.11")
    device_b = _create_ilo(client, display_name="Mock RAID iLO B", host="203.0.113.12")

    saved_a = client.put(
        RAID_INTENT_PATH,
        params={"device_id": device_a},
        json={
            "controller_ref": "mock-controller-a",
            "volumes": [
                {
                    "name": "Mock-A-OS",
                    "purpose": "ESXi install",
                    "raid_level": "RAID1",
                    "drive_bays": ["1", "2"],
                    "bootable": True,
                }
            ],
            "notes": "Device A RAID intent",
        },
    )
    assert saved_a.status_code == 200
    assert saved_a.json()["device_id"] == device_a
    assert saved_a.json()["volumes"][0]["name"] == "Mock-A-OS"

    untouched_b = client.get(RAID_INTENT_PATH, params={"device_id": device_b})
    assert untouched_b.status_code == 200
    assert untouched_b.json()["device_id"] == device_b
    assert untouched_b.json()["controller_ref"] is None
    assert untouched_b.json()["volumes"] == []

    saved_b = client.put(
        RAID_INTENT_PATH,
        params={"device_id": device_b},
        json={
            "controller_ref": "mock-controller-b",
            "volumes": [
                {
                    "name": "Mock-B-Data",
                    "purpose": "VM datastore",
                    "raid_level": "RAID6",
                    "drive_bays": ["3", "4", "5", "6"],
                }
            ],
            "notes": "Device B RAID intent",
        },
    )
    assert saved_b.status_code == 200

    reread_a = client.get(RAID_INTENT_PATH, params={"device_id": device_a})
    reread_b = client.get(RAID_INTENT_PATH, params={"device_id": device_b})
    assert reread_a.status_code == reread_b.status_code == 200
    assert reread_a.json()["controller_ref"] == "mock-controller-a"
    assert reread_a.json()["volumes"][0]["drive_bays"] == ["1", "2"]
    assert reread_b.json()["controller_ref"] == "mock-controller-b"
    assert reread_b.json()["volumes"][0]["drive_bays"] == ["3", "4", "5", "6"]

    db_session.expire_all()
    intent_a = db_session.get(HpeRaidIntent, (device_a, PROVIDER_ID))
    intent_b = db_session.get(HpeRaidIntent, (device_b, PROVIDER_ID))
    assert intent_a is not None
    assert intent_b is not None
    assert intent_a.intent_json["volumes"][0]["name"] == "Mock-A-OS"
    assert intent_b.intent_json["volumes"][0]["name"] == "Mock-B-Data"
