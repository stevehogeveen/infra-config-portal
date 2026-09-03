from __future__ import annotations

import sys
import json
from dataclasses import replace
from pathlib import Path
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
    assert netapp_real_lab.CONSOLE_DISCOVERY_REPORT.read_text(encoding="utf-8").strip()
    assert netapp_state.AUTOMANAGEMENT_REPORT.read_text(encoding="utf-8").strip()
    assert list(tmp_path.glob("*.tmp")) == []


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
    assert netapp_real_lab.CONSOLE_DISCOVERY_REPORT.read_text(encoding="utf-8").strip()
    assert list(tmp_path.glob("*.tmp")) == []


def test_login_required_does_not_equal_configured(db_session: Session) -> None:
    state = update_netapp_runtime_state_from_console_probe(
        _console_payload(prompt_state="login_required"),
        session=db_session,
    )

    assert state["configured_state"] == "login_required"
    assert state["configured"] is False


def test_console_login_state_upgrades_to_ontap_shell_after_commands() -> None:
    assert (
        netapp_real_lab._identified_state_after_commands(
            "login_required",
            [
                {
                    "status": "captured",
                    "prompt_state": "existing_cluster_shell",
                }
            ],
        )
        == "ontap_shell"
    )


def test_latest_console_ontap_version_parser_uses_read_only_command_output() -> None:
    payload = {
        "checked_at": "2026-06-13T00:00:00+00:00",
        "command_results": [
            {
                "id": "ontap_version",
                "status": "captured",
                "output_excerpt": "NetApp Release 9.17.1: Fri May 02 01:22:03 UTC 2026",
            }
        ],
    }

    assert netapp_real_lab._ontap_version_from_console_payload(payload) == "9.17.1"


def test_latest_console_ontap_version_self_heals_corrupt_state(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "netapp-console-login-state-redacted.json"
    state_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(netapp_real_lab, "CONSOLE_LOGIN_STATE_JSON", state_path)

    payload = netapp_real_lab.latest_console_ontap_version()

    assert payload == {"version": None, "source": "not_available", "checked_at": None}


def test_latest_console_ontap_version_ignores_non_object_state(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "netapp-console-login-state-redacted.json"
    state_path.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(netapp_real_lab, "CONSOLE_LOGIN_STATE_JSON", state_path)

    payload = netapp_real_lab.latest_console_ontap_version()

    assert payload == {"version": None, "source": "not_available", "checked_at": None}


def test_netapp_aggregate_read_command_uses_supported_field_name() -> None:
    commands = dict(netapp_real_lab.READ_ONLY_ONTAP_COMMANDS)

    assert "availsize" in commands["storage_aggregate_summary"]
    assert "available" not in commands["storage_aggregate_summary"]


def test_console_login_runtime_payload_uses_existing_cluster_shell_after_login() -> None:
    payload = netapp_real_lab._login_runtime_probe_payload(
        {
            "action": "console-login-state",
            "selected_port": "/dev/ttyACM0",
            "selected_baud": 115200,
            "prompt_state": "login_required",
            "identified_state": "ontap_shell",
        }
    )

    assert payload["selected_prompt_state"] == "existing_cluster_shell"
    assert payload["selected_prompt_label"] == "Existing ONTAP cluster shell"
    assert payload["selection_source"] == "console-login-state"


def test_netapp_state_artifact_paths_use_posix_separators(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(netapp_state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_real_lab, "REPO_ROOT", tmp_path)

    path = tmp_path / "artifacts" / "codex-runs" / "netapp-live-state-report.md"

    assert netapp_state._rel(path) == "artifacts/codex-runs/netapp-live-state-report.md"
    assert netapp_real_lab._rel(path) == "artifacts/codex-runs/netapp-live-state-report.md"


def test_netapp_tool_path_skips_unavailable_local_candidate(monkeypatch, tmp_path) -> None:
    candidate = tmp_path / "venv" / "Scripts" / "sshpass"
    monkeypatch.setattr(netapp_real_lab, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_real_lab.sys, "executable", str(tmp_path / "venv" / "Scripts" / "python.exe"))
    monkeypatch.setattr(netapp_real_lab, "which", lambda _name: None)
    original_is_file = Path.is_file

    def unavailable_is_file(path: Path) -> bool:
        if path == candidate:
            raise OSError("candidate path unavailable")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", unavailable_is_file)

    assert netapp_real_lab._tool_path("sshpass") is None


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


def test_iscsi_service_license_gap_blocks_configured_state(monkeypatch, db_session: Session) -> None:
    monkeypatch.setattr(
        netapp_state,
        "settings",
        replace(
            settings,
            netapp_api_username="admin",
            netapp_api_password="local-secret",
            netapp_storage_protocol="iscsi",
            netapp_iscsi_lifs=("192.168.1.240", "192.168.1.241"),
            netapp_svm_name="esxi_svm",
        ),
    )

    def reachable(_host: str | None, port: int, _check_ports: bool) -> bool:
        return port != 3260

    result = read_netapp_live_state(
        check_ports=True,
        write_report=False,
        session=db_session,
        reachable=reachable,
        api_getter=lambda: {"status": "ready", "authenticated": True, "reason": "ok"},
        storage_probe_getter=lambda _protocol: {
            "status": "blocked",
            "enabled": False,
            "record_count": 0,
            "svm_name": "esxi_svm",
            "reason": "No enabled NetApp iSCSI service record was found for SVM `esxi_svm`.",
        },
    )

    assert result["configured"] is False
    assert result["configured_state"] == "api_authenticated"
    assert result["storage"]["protocol"] == "iscsi"
    assert result["storage"]["service_enabled"] is False
    assert "NetApp iSCSI service is not enabled for SVM `esxi_svm`." in result["blockers"]
    assert "iSCSI LIF `192.168.1.240` is not accepting TCP/3260." in result["blockers"]


def test_protocol_service_and_data_ports_can_mark_storage_ready(monkeypatch, db_session: Session) -> None:
    monkeypatch.setattr(
        netapp_state,
        "settings",
        replace(
            settings,
            netapp_api_username="admin",
            netapp_api_password="local-secret",
            netapp_storage_protocol="nfs",
            netapp_nfs_lifs=("192.168.1.230", "192.168.1.231"),
            netapp_nfs_mount_path="/esxi_datastore_01",
            netapp_nfs_datastore_name="netapp_nfs_ds01",
            netapp_svm_name="esxi_svm",
        ),
    )

    result = read_netapp_live_state(
        check_ports=True,
        write_report=False,
        session=db_session,
        reachable=lambda _host, _port, _check_ports: True,
        api_getter=lambda: {"status": "ready", "authenticated": True, "reason": "ok"},
        storage_probe_getter=lambda _protocol: {
            "status": "ready",
            "enabled": True,
            "record_count": 1,
            "svm_name": "esxi_svm",
        },
    )

    assert result["configured"] is True
    assert result["configured_state"] == "configured"
    assert result["storage"]["ready"] is True
    assert result["storage"]["service_status"] == "ready"


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


def test_live_state_writes_reports_atomically(monkeypatch, tmp_path, db_session: Session) -> None:
    _patch_reports(monkeypatch, tmp_path)
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
        write_report=True,
        session=db_session,
        reachable=lambda _host, _port, _check_ports: True,
        api_getter=lambda: {"status": "ready", "authenticated": True, "reason": "ok"},
    )

    assert result["configured"] is True
    assert netapp_state.LIVE_STATE_REPORT.read_text(encoding="utf-8").strip()
    assert netapp_state.AUTOMANAGEMENT_REPORT.read_text(encoding="utf-8").strip()
    assert netapp_state.CONSOLE_LAST_KNOWN_GOOD_JSON.exists()
    assert list(tmp_path.glob("*.tmp")) == []


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


def test_netapp_state_ignores_corrupt_console_artifacts_and_writes_last_known_good(
    monkeypatch,
    tmp_path,
) -> None:
    _patch_reports(monkeypatch, tmp_path)
    netapp_state.CONSOLE_STATE_JSON.write_text("{not json", encoding="utf-8")
    netapp_state.CONSOLE_AUTODISCOVERY_JSON.write_text("[]", encoding="utf-8")

    assert netapp_state._stable_netapp_console_from_artifacts() is None

    netapp_state._write_console_last_known_good(
        {
            "checked_at": "2026-06-25T00:00:00+00:00",
            "confidence": "medium",
            "console": {
                "discovered_port": "/dev/ttyUSB9",
                "baud": 115200,
                "last_seen": "2026-06-25T00:00:00+00:00",
                "source": "test",
            },
        }
    )

    saved = netapp_state._read_json(netapp_state.CONSOLE_LAST_KNOWN_GOOD_JSON)
    assert saved is not None
    assert saved["discovered_console_port"] == "/dev/ttyUSB9"
    assert list(tmp_path.glob("*.tmp")) == []


def test_netapp_console_discovery_dedupes_configured_and_globbed_paths(monkeypatch, tmp_path) -> None:
    configured = tmp_path / "ttyUSB0"
    configured.touch()
    alternate = tmp_path / "ttyUSB1"
    alternate.touch()
    monkeypatch.setattr(
        netapp_real_lab,
        "settings",
        SimpleNamespace(netapp_console_port=str(configured)),
    )
    monkeypatch.setattr(
        netapp_real_lab.glob,
        "glob",
        lambda _pattern: [str(configured), str(alternate), str(configured)],
    )

    candidates = netapp_real_lab._discover_console_candidates()

    assert [candidate.path for candidate in candidates] == [str(configured), str(alternate)]
    assert candidates[0].recommendation == "configured-port-hint"


def test_netapp_console_discovery_self_heals_glob_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        netapp_real_lab,
        "settings",
        SimpleNamespace(netapp_console_port=None),
    )

    def failing_glob(_pattern: str) -> list[str]:
        raise OSError("console glob unavailable")

    monkeypatch.setattr(netapp_real_lab.glob, "glob", failing_glob)

    assert netapp_real_lab._discover_console_candidates() == []


def test_netapp_console_candidate_self_heals_exists_probe_errors(monkeypatch, tmp_path) -> None:
    candidate_path = tmp_path / "ttyUSB9"
    original_exists = Path.exists

    def locked_exists(path: Path) -> bool:
        if path == candidate_path:
            raise OSError("console path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", locked_exists)
    monkeypatch.setattr(
        netapp_real_lab,
        "settings",
        SimpleNamespace(netapp_console_port=str(candidate_path)),
    )

    candidate = netapp_real_lab._candidate(str(candidate_path))

    assert candidate.exists is False
    assert candidate.readable is False
    assert candidate.writable is False
    assert candidate.target_path is None
    assert candidate.recommendation == "configured-port-hint"


def test_netapp_baud_order_dedupes_configured_first() -> None:
    original = netapp_real_lab.COMMON_NETAPP_CONSOLE_BAUDS
    try:
        netapp_real_lab.COMMON_NETAPP_CONSOLE_BAUDS = (115200, 9600, 115200, 57600)
        assert netapp_real_lab._baud_order(9600) == (9600, 115200, 57600)
    finally:
        netapp_real_lab.COMMON_NETAPP_CONSOLE_BAUDS = original


def _patch_reports(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(netapp_state, "CODEX_RUN_DIR", tmp_path)
    monkeypatch.setattr(netapp_real_lab, "CODEX_RUN_DIR", tmp_path)
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
