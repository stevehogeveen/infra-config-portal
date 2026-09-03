from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api import routes
from app.models import DeviceInventory, IloDeviceCredential
from app.providers.ilo_redfish import IloRedfishConfig, ilo_target_fingerprint
from app.providers.probe_cache import record_probe_result
from app.services import ilo_access_settings


def _config(host: str) -> IloRedfishConfig:
    return IloRedfishConfig(
        host=host,
        username="Administrator",
        password="configured-for-test",
        verify_tls=False,
        timeout_seconds=1,
    )


def test_last_probe_summary_marks_recent_exact_target_evidence_current(
    monkeypatch,
) -> None:
    host = "192.0.2.11"
    checked_at = datetime.now(UTC).isoformat()
    monkeypatch.setattr(
        ilo_access_settings,
        "get_probe_result",
        lambda _provider_id, **_kwargs: (
            {
                "status": "ok",
                "target_fingerprint": ilo_target_fingerprint(host),
                "target_source": "operator_first_contact",
            },
            checked_at,
        ),
    )

    summary = ilo_access_settings._last_probe_summary(host, _config(host))

    assert summary["last_probe_freshness"] == "current"
    assert summary["last_probe_is_current"] is True
    assert summary["last_probe_target_matches_access_host"] is True
    assert summary["last_probe_target_fingerprint_present"] is True


def test_last_probe_summary_marks_stale_exact_target_evidence_not_current(
    monkeypatch,
) -> None:
    host = "192.0.2.11"
    checked_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    monkeypatch.setattr(
        ilo_access_settings,
        "get_probe_result",
        lambda _provider_id, **_kwargs: (
            {
                "status": "ok",
                "target_fingerprint": ilo_target_fingerprint(host),
                "target_source": "operator_first_contact",
            },
            checked_at,
        ),
    )

    summary = ilo_access_settings._last_probe_summary(host, _config(host))

    assert summary["last_probe_status"] == "ok"
    assert summary["last_probe_freshness"] == "stale"
    assert summary["last_probe_is_current"] is False
    assert summary["last_probe_target_matches_access_host"] is True


def test_last_probe_summary_never_marks_another_device_current(monkeypatch) -> None:
    monkeypatch.setattr(
        ilo_access_settings,
        "get_probe_result",
        lambda _provider_id, **_kwargs: (
            {
                "status": "ok",
                "target_fingerprint": ilo_target_fingerprint("192.0.2.12"),
                "target_source": "device_credentials",
            },
            datetime.now(UTC).isoformat(),
        ),
    )

    summary = ilo_access_settings._last_probe_summary(
        "192.0.2.11",
        _config("192.0.2.11"),
    )

    assert summary["last_probe_status"] == "ok"
    assert summary["last_probe_is_current"] is False
    assert summary["last_probe_target_matches_access_host"] is False


def test_last_probe_summary_marks_missing_evidence_not_checked(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ilo_access_settings,
        "get_probe_result",
        lambda _provider_id, **_kwargs: (None, None),
    )

    summary = ilo_access_settings._last_probe_summary(
        "192.0.2.11",
        _config("192.0.2.11"),
    )

    assert summary["last_probe_status"] == "not_checked"
    assert summary["last_probe_freshness"] == "not_checked"
    assert summary["last_probe_is_current"] is False


def test_device_config_reports_inventory_host_fallback_truthfully(db_session) -> None:
    device = DeviceInventory(
        device_type="ilo",
        display_name="Mock inventory-only iLO",
        host="192.0.2.31",
    )
    db_session.add(device)
    db_session.commit()

    config = ilo_access_settings.ilo_config_for_device(db_session, device.id)

    assert config.host == "192.0.2.31"
    assert config.host_source == "device_inventory"


def test_access_settings_route_preserves_probe_freshness_fields(
    client,
    monkeypatch,
) -> None:
    inventory = client.get("/api/v1/device-inventory").json()
    device_id = next(device["id"] for device in inventory if device["device_type"] == "ilo")
    monkeypatch.setattr(
        routes,
        "read_ilo_access_settings",
        lambda _session, _device_id: {
            "provider_id": "ilo-redfish",
            "device_id": device_id,
            "host": "192.0.2.11",
            "host_source": "device_credentials",
            "fallback_hosts": ["192.0.2.201"],
            "username": "Administrator",
            "username_configured": True,
            "password_configured": True,
            "verify_tls": False,
            "updated_at": None,
            "last_probe_status": "ok",
            "last_probe_time": datetime.now(UTC).isoformat(),
            "last_probe_freshness": "current",
            "last_probe_is_current": True,
            "last_probe_message": "Read-only Redfish probe completed.",
            "last_probe_target_source": "operator_first_contact",
            "last_probe_target_matches_access_host": True,
            "last_probe_target_matches_configured_candidates": True,
            "last_probe_target_fingerprint_present": True,
            "next_safe_action": "Review current proof.",
        },
    )

    response = client.get(
        "/api/v1/providers/ilo-redfish/access-settings",
        params={"device_id": device_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_probe_freshness"] == "current"
    assert payload["last_probe_is_current"] is True


def test_upgrade_readiness_route_never_shows_another_ilo_probe(
    client,
    db_session,
) -> None:
    device_a = DeviceInventory(
        device_type="ilo",
        display_name="Mock iLO A",
        host="192.0.2.11",
    )
    device_b = DeviceInventory(
        device_type="ilo",
        display_name="Mock iLO B",
        host="192.0.2.12",
    )
    db_session.add_all([device_a, device_b])
    db_session.flush()
    for device, host in ((device_a, "192.0.2.11"), (device_b, "192.0.2.12")):
        db_session.add(
            IloDeviceCredential(
                device_id=device.id,
                credentials_json={
                    "host": host,
                    "username": "Mock-Administrator",
                    "password": "mock-password",
                    "verify_tls": False,
                },
            )
        )
    db_session.commit()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "target_fingerprint": ilo_target_fingerprint("192.0.2.12"),
            "managers": [{"FirmwareVersion": "2.82"}],
            "systems": [{"Model": "Mock ProLiant B"}],
        },
    )

    response_a = client.get(
        "/api/v1/providers/ilo-redfish/upgrade-readiness",
        params={"device_id": device_a.id},
    )
    response_b = client.get(
        "/api/v1/providers/ilo-redfish/upgrade-readiness",
        params={"device_id": device_b.id},
    )

    assert response_a.status_code == 200
    assert response_a.json()["subject"]["model"] is None
    assert response_a.json()["subject"]["current_version"] is None
    assert response_b.status_code == 200
    assert response_b.json()["subject"]["model"] == "Mock ProLiant B"
    assert response_b.json()["subject"]["current_version"] == "2.82"
