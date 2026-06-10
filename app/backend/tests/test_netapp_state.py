from __future__ import annotations

import sys
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services import netapp_real_lab, netapp_state
from app.services.netapp_real_lab import run_netapp_console_discovery
from app.services.netapp_state import (
    get_netapp_runtime_state,
    read_netapp_live_state,
    update_netapp_runtime_state_from_console_probe,
)


def test_netapp_console_port_missing_autodiscovery_finds_console(
    monkeypatch,
    tmp_path,
    db_session: Session,
) -> None:
    _patch_reports(monkeypatch, tmp_path)
    _patch_console_probe(
        monkeypatch,
        settings_override=replace(
            settings,
            provider_mode="local-lab-readwrite",
            netapp_console_port=None,
            netapp_console_autodiscovery_disabled=False,
        ),
        candidates=[_candidate("/dev/ttyUSB0")],
        selected_path="/dev/ttyUSB0",
        prompt_state="cluster_setup_prompt",
    )

    result = run_netapp_console_discovery(session=db_session)
    state = get_netapp_runtime_state(session=db_session)

    assert result["selected_port"] == "/dev/ttyUSB0"
    assert result["selection_origin"] == "autodiscovery"
    assert result["manual_env_update_required"] is False
    assert state["console"]["discovered_port"] == "/dev/ttyUSB0"
    assert state["console"]["source"] == "autodiscovery"
    assert state["configured"] is False
    assert state["configured_state"] == "setup_wizard"


def test_netapp_console_port_stale_hint_falls_back_to_autodiscovery(
    monkeypatch,
    tmp_path,
    db_session: Session,
) -> None:
    _patch_reports(monkeypatch, tmp_path)
    _patch_console_probe(
        monkeypatch,
        settings_override=replace(
            settings,
            provider_mode="local-lab-readwrite",
            netapp_console_port="/dev/ttyS99",
            netapp_console_autodiscovery_disabled=False,
        ),
        candidates=[_candidate("/dev/ttyS99", exists=False), _candidate("/dev/ttyUSB1")],
        selected_path="/dev/ttyUSB1",
        prompt_state="existing_cluster_shell",
    )

    result = run_netapp_console_discovery(session=db_session)
    state = get_netapp_runtime_state(session=db_session)

    assert result["configured_port_hint"] == "/dev/ttyS99"
    assert result["selected_port"] == "/dev/ttyUSB1"
    assert result["selection_origin"] == "autodiscovery"
    assert state["console"]["discovered_port"] == "/dev/ttyUSB1"
    assert state["console"]["manual_env_update_required"] is False


def test_login_required_does_not_equal_configured(db_session: Session) -> None:
    state = update_netapp_runtime_state_from_console_probe(
        _console_payload(prompt_state="login_required"),
        session=db_session,
    )

    assert state["configured_state"] == "login_required"
    assert state["configured"] is False


def test_configured_is_only_true_after_live_validation(monkeypatch, db_session: Session) -> None:
    update_netapp_runtime_state_from_console_probe(
        _console_payload(prompt_state="existing_cluster_shell"),
        session=db_session,
    )
    before = get_netapp_runtime_state(session=db_session)

    assert before["configured"] is False
    assert before["configured_state"] == "ontap_detected"

    monkeypatch.setattr(
        netapp_state,
        "settings",
        replace(
            settings,
            netapp_api_username="admin",
            netapp_api_password="local-secret",
            netapp_storage_protocol="nfs",
            netapp_nfs_lifs=("192.168.1.230",),
        ),
    )
    result = read_netapp_live_state(
        check_ports=True,
        write_report=False,
        session=db_session,
        reachable=lambda _host, _port, _check_ports: True,
        api_getter=lambda: {"status": "ready", "authenticated": True, "reason": "ok"},
    )

    assert result["configured"] is True
    assert result["configured_state"] == "configured"
    after = get_netapp_runtime_state(session=db_session)
    assert after["configured"] is True
    assert after["source"] == "live_verification"
    assert after["detected_management_ips"]["cluster"] == "192.168.1.220"


def test_secrets_are_redacted_from_live_state(monkeypatch, db_session: Session) -> None:
    monkeypatch.setenv("NETAPP_API_PASSWORD", "super-secret-value")
    monkeypatch.setattr(
        netapp_state,
        "settings",
        replace(settings, netapp_api_username="admin", netapp_api_password="super-secret-value"),
    )

    result = read_netapp_live_state(
        check_ports=True,
        write_report=False,
        session=db_session,
        reachable=lambda _host, _port, _check_ports: True,
        api_getter=lambda: {
            "status": "blocked",
            "authenticated": False,
            "reason": "super-secret-value should not appear",
        },
    )

    assert "super-secret-value" not in str(result)
    assert "REDACTED" in str(result)


def test_stable_microchip_console_artifact_clears_old_no_adapter_blocker(
    monkeypatch,
    tmp_path,
    db_session: Session,
) -> None:
    _patch_reports(monkeypatch, tmp_path)
    netapp_state.CONSOLE_STATE_JSON.write_text(
        json.dumps(
            {
                "checked_at": "2026-06-08T18:51:01+00:00",
                "selected_port": "/dev/serial/by-id/usb-Microchip_Technology_Inc._MCP2221_USB-I2C_UART_Combo-if00",
                "selected_baud": 115200,
                "selected_prompt_state": "login_required",
                "selected_prompt_label": "NetApp login prompt",
                "selection_source": "prompt-evidence",
                "selection_confidence": "medium",
            }
        ),
        encoding="utf-8",
    )

    update_netapp_runtime_state_from_console_probe(
        {
            **_console_payload(prompt_state="not_detected"),
            "checked_at": "2026-06-08T12:00:00+00:00",
            "status": "blocked",
            "selected_port": None,
            "selected_baud": None,
            "selected_prompt_state": None,
            "blockers": ["No NetApp USB serial adapters were discovered."],
        },
        session=db_session,
    )

    state = get_netapp_runtime_state(session=db_session)

    assert state["console"]["discovered_port"].endswith("MCP2221_USB-I2C_UART_Combo-if00")
    assert state["console"]["baud"] == 115200
    assert state["console"]["prompt_state"] == "login_required"


def _patch_reports(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(netapp_real_lab, "CONSOLE_DISCOVERY_JSON", tmp_path / "discovery.json")
    monkeypatch.setattr(netapp_real_lab, "CONSOLE_DISCOVERY_REPORT", tmp_path / "discovery.md")
    monkeypatch.setattr(netapp_state, "CONSOLE_LAST_KNOWN_GOOD_JSON", tmp_path / "last-known-good.json")
    monkeypatch.setattr(netapp_state, "CONSOLE_AUTODISCOVERY_JSON", tmp_path / "console-autodiscovery.json")
    monkeypatch.setattr(netapp_state, "CONSOLE_STATE_JSON", tmp_path / "console-state.json")
    monkeypatch.setattr(netapp_state, "AUTOMANAGEMENT_REPORT", tmp_path / "automanagement.md")
    monkeypatch.setattr(netapp_state, "LIVE_STATE_REPORT", tmp_path / "live-state.md")


def _patch_console_probe(
    monkeypatch,
    *,
    settings_override: Any,
    candidates: list[dict[str, Any]],
    selected_path: str,
    prompt_state: str,
) -> None:
    monkeypatch.setattr(netapp_real_lab, "settings", settings_override)
    monkeypatch.setattr(netapp_state, "settings", settings_override)
    monkeypatch.setattr(
        netapp_real_lab,
        "current_lab_action_policy",
        lambda _mode: SimpleNamespace(readonly_blockers=lambda: []),
    )
    monkeypatch.setitem(sys.modules, "serial", SimpleNamespace(Serial=object))
    monkeypatch.setattr(
        netapp_real_lab,
        "discover_serial_console_candidates",
        lambda **_kwargs: candidates,
    )
    monkeypatch.setattr(
        netapp_real_lab,
        "probe_serial_candidates",
        lambda *_args, **_kwargs: {
            "selected": _attempt(selected_path, prompt_state=prompt_state),
            "attempts": [_attempt(selected_path, prompt_state=prompt_state)],
            "probed_candidate_count": 1,
            "skipped_candidate_count": 0,
        },
    )


def _candidate(path: str, *, exists: bool = True) -> dict[str, Any]:
    return {
        "display_path": path,
        "path": path,
        "exists": exists,
        "readable": exists,
        "writable": exists,
        "in_use": False,
        "stable_path": False,
        "path_type": "ttyUSB" if "USB" in path else "ttyS",
        "confidence": "medium" if exists else "low",
        "selection_reasons": ["test candidate"],
        "recommendation": "usb-serial-candidate" if exists else "missing",
    }


def _attempt(path: str, *, prompt_state: str) -> dict[str, Any]:
    return {
        "path": path,
        "baud": 115200,
        "prompt_state": prompt_state,
        "prompt_label": "NetApp prompt",
        "classification": "prompt_detected",
        "device_type": "netapp",
        "classification_detail": {
            "confidence": "high",
            "signals": ["test prompt"],
        },
        "output_excerpt": "redacted prompt excerpt",
    }


def _console_payload(*, prompt_state: str) -> dict[str, Any]:
    return {
        "provider_id": "netapp-ontap",
        "action": "console-read-state",
        "checked_at": "2026-06-08T12:00:00+00:00",
        "status": "ready",
        "message": "NetApp console state read completed.",
        "selected_port": "/dev/ttyUSB0",
        "selected_baud": 115200,
        "selected_prompt_state": prompt_state,
        "selected_prompt_label": "NetApp prompt",
        "selection_source": "prompt-evidence",
        "selection_confidence": "high",
        "blockers": [],
        "artifacts": {"report": "artifacts/codex-runs/netapp-console-state-report.md"},
    }
