from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api import routes
from app.providers.ilo_redfish import IloRedfishConfig, ilo_target_fingerprint
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
        lambda _provider_id: (
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
        lambda _provider_id: (
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


def test_last_probe_summary_marks_missing_evidence_not_checked(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        ilo_access_settings,
        "get_probe_result",
        lambda _provider_id: (None, None),
    )

    summary = ilo_access_settings._last_probe_summary(
        "192.0.2.11",
        _config("192.0.2.11"),
    )

    assert summary["last_probe_status"] == "not_checked"
    assert summary["last_probe_freshness"] == "not_checked"
    assert summary["last_probe_is_current"] is False


def test_access_settings_route_preserves_probe_freshness_fields(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "read_ilo_access_settings",
        lambda: {
            "provider_id": "ilo-redfish",
            "host": "192.0.2.11",
            "host_source": "runtime_env",
            "fallback_hosts": ["192.0.2.201"],
            "username": "Administrator",
            "username_configured": True,
            "password_configured": True,
            "verify_tls": False,
            "env_path": ".env.local.real-lab",
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

    response = client.get("/api/v1/providers/ilo-redfish/access-settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["last_probe_freshness"] == "current"
    assert payload["last_probe_is_current"] is True
