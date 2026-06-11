from __future__ import annotations

import builtins
import importlib.util
import json
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

from app.providers import esxi_readonly
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.action_policy import ActionCategory, LabActionPolicy
from app.providers.cisco_console import (
    CiscoConsoleAdapter,
    CiscoConsoleConfig,
    ConsoleDiscoveryPaths,
    _prompt_blocker_message,
    _prompt_state,
    discover_cisco_console,
)
from app.providers.cisco_ansible import (
    CiscoAnsibleAdapter,
    CiscoAnsibleConfig,
    _run_command,
    _write_temp_inventory,
)
from app.providers.esxi_readonly import EsxiReadonlyAdapter, EsxiReadonlyConfig
from app.providers.ilo_redfish import IloRedfishAdapter, IloRedfishConfig
from app.providers.lab_safety import LabSafetyState
from app.providers.probe_cache import clear_probe_results, record_probe_result
from app.providers.redaction import redact_sensitive
from app.providers.registry import provider_registry
from app.services.cisco_bootstrap_requirements import build_cisco_bootstrap_requirements
from app.services.cisco_bootstrap_requirements import save_cisco_bootstrap_requirements
from app.services.cisco_console_bootstrap import (
    CONFIRMATION_PHRASE,
    apply_cisco_console_bootstrap,
    build_cisco_console_bootstrap_plan,
)
from app.services.cisco_setup_readiness import get_cisco_setup_readiness
from app.services.cisco_setup_wizard_plan import build_cisco_setup_wizard_plan
from app.services.ilo_readiness import save_ilo_setup_intent
from app.services.ilo_setup_apply import (
    CONFIRMATION_PHRASE as ILO_SETUP_CONFIRMATION_PHRASE,
    apply_ilo_setup,
)
from app.services.control_access import update_control_access_config
from app.services.lab_profiles import create_lab_profile
from app.schemas import IloNetworkIntent, IloSetupApplyCreate, IloSetupIntentWrite


def test_cisco_candidate_discovery_with_one_stable_candidate(tmp_path: Path) -> None:
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    stable = paths["by_id"] / "usb-Cisco_console-if00-port0"
    stable.symlink_to(tty)

    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "ready"
    assert discovery["recommended_path"] == str(stable)
    assert discovery["effective_path"] == str(stable)
    assert discovery["selection_source"] == "auto-stable-candidate"
    assert discovery["candidate_counts"]["stable_existing"] == 1
    assert discovery["operator_message"].startswith("Preferred console path:")
    assert "prompt readiness" in discovery["safe_next_action"]
    stable_candidates = [
        candidate for candidate in discovery["candidates"] if candidate["stable_path"]
    ]
    assert stable_candidates[0]["recommendation"] == "selected-auto"


def test_cisco_candidate_discovery_with_multiple_stable_candidates(tmp_path: Path) -> None:
    paths = _console_paths(tmp_path)
    tty0 = paths["dev"] / "ttyUSB0"
    tty1 = paths["dev"] / "ttyUSB1"
    tty0.touch()
    tty1.touch()
    (paths["by_id"] / "usb-Cisco_console-a").symlink_to(tty0)
    (paths["by_id"] / "usb-Cisco_console-b").symlink_to(tty1)

    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "ready"
    assert discovery["recommended_path"] is not None
    assert discovery["effective_path"] is not None
    assert discovery["selection_source"] == "auto-stable-candidate"
    assert discovery["candidate_counts"]["stable_existing"] == 2
    assert discovery["blockers"] == []


def test_cisco_candidate_discovery_with_no_candidates(tmp_path: Path) -> None:
    paths = _console_paths(tmp_path)

    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "missing-console"
    assert discovery["candidates"] == []
    assert discovery["effective_path"] is None
    assert discovery["selection_source"] == "missing"
    assert discovery["candidate_counts"]["total"] == 0
    assert "No Cisco serial console adapter was detected" in discovery["blockers"][0]
    assert discovery["operator_message"].startswith("No Cisco serial console adapter was detected")
    assert "USB serial cable is plugged into this machine" in discovery["operator_checklist"][0]
    assert "dialout/read-write access" in discovery["operator_checklist"][3]


def test_cisco_candidate_discovery_supports_tcp_console_transport() -> None:
    discovery = discover_cisco_console(
        CiscoConsoleConfig(
            port=None,
            baud=9600,
            timeout_seconds=1.0,
            transport="tcp_console",
            tcp_host="127.0.0.1",
            tcp_port=2001,
        )
    )

    assert discovery["status"] == "ready"
    assert discovery["transport"] == "tcp_console"
    assert discovery["effective_path"] == "tcp://127.0.0.1:2001"
    assert discovery["tcp_console"]["ser2net_compatible"] is True


def test_cisco_candidate_discovery_with_fallback_candidate_warns(tmp_path: Path) -> None:
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()

    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "ready"
    assert discovery["selection_source"] == "auto-fallback-candidate"
    assert discovery["effective_path"] == str(tty)
    assert discovery["candidate_counts"]["fallback_existing"] == 1
    assert any("Fallback serial adapter detected" in warning for warning in discovery["warnings"])
    assert "prompt readiness" in discovery["safe_next_action"]


def test_cisco_configured_port_missing_has_clear_blocker(tmp_path: Path) -> None:
    paths = _console_paths(tmp_path)
    missing_path = paths["dev"] / "ttyUSB9"

    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=str(missing_path), baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "missing-console"
    assert discovery["effective_path"] is None
    assert "Configured CISCO_CONSOLE_PORT does not exist" in discovery["blockers"][0]


def test_cisco_configured_port_permission_guidance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()

    def unreadable(path: str, mode: int) -> bool:
        if path == str(tty):
            return False
        return True

    monkeypatch.setattr("app.providers.cisco_console.os.access", unreadable)
    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "blocked"
    assert "not readable/writable" in discovery["blockers"][0]
    assert "dialout group membership" in discovery["blockers"][0]
    assert "restart the backend shell/session" in discovery["permission_guidance"]


def test_cisco_env_override_path(tmp_path: Path) -> None:
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()

    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=str(tty), baud=115200, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "ready"
    assert discovery["env_override"]["configured"] is True
    assert discovery["env_override"]["path"] == str(tty)
    assert discovery["effective_path"] == str(tty)
    assert discovery["selection_source"] == "configured-port-hint"
    matching = [candidate for candidate in discovery["candidates"] if candidate["path"] == str(tty)]
    assert matching[0]["recommendation"] == "selected-auto"


def test_cisco_discovery_does_not_open_serial_or_send_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()

    def blocked_open(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("discovery must not open files or serial ports")

    monkeypatch.setattr(builtins, "open", blocked_open)
    discovery = discover_cisco_console(
        CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        _discovery_paths(paths),
    )

    assert discovery["status"] == "ready"


def test_cisco_setup_wizard_prompt_is_blocked() -> None:
    prompt = "Would you like to enter the initial configuration dialog? [yes/no]:"

    assert _prompt_state(prompt) == "setup-wizard"
    assert "setup wizard" in _prompt_blocker_message("setup-wizard")


def test_cisco_console_probe_redacts_blocked_prompt_sample(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    _install_fake_serial(
        monkeypatch,
        ["Switch01\nWould you like to enter the initial configuration dialog? [yes/no]:"],
    )

    adapter = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
    )
    result = adapter.probe()
    encoded = json.dumps(result)

    assert result["status"] == "blocked"
    assert result["prompt_state"] == "setup-wizard"
    assert result["prompt_sample"]["raw_text_redacted"] is True
    assert "Switch01" not in encoded
    assert "initial configuration dialog" not in encoded


def test_cisco_console_probe_returns_command_summaries_not_raw_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    tty = tmp_path / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    _install_fake_serial(
        monkeypatch,
        [
            "Switch01#",
            "show version\nSwitch01 uptime is 1 day\nProcessor board ID SECRET123\nSwitch01#",
            "show inventory\nNAME: Chassis, SN: SECRET456\nSwitch01#",
            "show interfaces status\nGi1/0/1 connected\nSwitch01#",
            "show ip interface brief\nVlan1 192.0.2.10 up up\nSwitch01#",
            "show vlan brief\n1 default active\nSwitch01#",
        ],
    )

    adapter = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
    )
    result = adapter.probe()
    encoded = json.dumps(result)

    assert result["status"] == "ok"
    assert len(result["safe_show_commands"]) == 5
    assert all(item["raw_output_redacted"] for item in result["safe_show_commands"])
    assert "commands" not in result
    assert "SECRET123" not in encoded
    assert "192.0.2.10" not in encoded


def test_cisco_console_firmware_inventory_parses_ios_xe_from_user_exec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    tty = tmp_path / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    writes = _install_tracking_fake_serial(
        monkeypatch,
        [
            "Switch01>",
            "show version\nCisco IOS XE Software, Version 17.15.05\nSwitch01>",
        ],
    )

    adapter = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
    )
    result = adapter.firmware_inventory()
    encoded = json.dumps(result)

    assert result["status"] == "ok"
    assert result["prompt_state"] == "exec"
    assert result["ios_xe_version"] == "17.15.05"
    assert result["safe_show_commands"][0]["version_hint"] == "17.15.05"
    assert b"show version\n" in writes
    assert b"enable\n" not in writes
    assert "Cisco IOS XE Software" not in encoded


def test_cisco_prompt_readiness_is_blocked_in_mock_mode() -> None:
    clear_probe_results()
    adapter = CiscoConsoleAdapter(
        provider_mode="mock",
        config=CiscoConsoleConfig(port="/dev/ttyUSB0", baud=9600, timeout_seconds=1.0),
    )

    result = adapter.prompt_readiness()

    assert result["action"] == "prompt-readiness"
    assert result["status"] == "blocked"
    assert "local-readonly" in result["message"]
    assert result["prompt_ready"] is False
    assert "safe show commands" in result["not_attempted"]


def test_cisco_prompt_readiness_requires_lab_safety_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    tty = tmp_path / "ttyUSB0"
    tty.touch()
    monkeypatch.setattr(
        "app.providers.cisco_console.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=False,
            readonly_ack=False,
            destructive_ack=False,
        ),
    )

    result = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
    ).prompt_readiness()

    assert result["status"] == "blocked"
    assert "LAB_CLOSED_LOOP_ACK=YES" in result["message"]
    assert result["prompt_ready"] is False


def test_cisco_prompt_readiness_blocks_without_effective_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    paths = _console_paths(tmp_path)
    _allow_readonly_lab(monkeypatch)

    result = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        paths=_discovery_paths(paths),
    ).prompt_readiness()

    assert result["status"] == "blocked"
    assert "one selected readable and writable console path" in result["message"]
    assert result["prompt_ready"] is False
    assert result["discovery"]["status"] == "missing-console"


def test_cisco_prompt_readiness_exec_prompt_sends_newline_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(tmp_path, monkeypatch, "Switch01#")
    encoded = json.dumps(result)

    assert writes == [b"\n"]
    assert result["status"] == "ok"
    assert result["prompt_state"] == "privileged-exec"
    assert result["prompt_ready"] is True
    assert result["safe_show_commands_allowed"] is False
    assert result["future_show_command_check_eligible"] is True
    assert result["prompt_classification"]["label"] == "Privileged exec prompt"
    assert result["prompt_classification"]["safe_show_commands_allowed"] is False
    assert result["prompt_sample"]["last_line"] == "DEVICE#"
    assert "safe show commands" in result["not_attempted"]
    assert "safe_show_commands" not in result
    assert "Switch01" not in encoded


def test_cisco_prompt_readiness_blocks_setup_wizard_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(
        tmp_path,
        monkeypatch,
        "Switch01\nWould you like to enter the initial configuration dialog? [yes/no]:",
    )
    encoded = json.dumps(result)

    assert writes == [b"\n"]
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "setup-wizard"
    assert result["prompt_ready"] is False
    assert result["setup_wizard_detected"] is True
    assert result["safe_show_commands_allowed"] is False
    assert result["future_show_command_check_eligible"] is False
    assert result["prompt_classification"]["label"] == "Setup wizard prompt"
    assert "setup wizard" in result["blockers"][0]
    assert "initial configuration dialog" not in encoded


def test_cisco_prompt_readiness_blocks_login_required_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(tmp_path, monkeypatch, "Username:")

    assert writes == [b"\n"]
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "login-required"
    assert result["login_required"] is True
    assert result["prompt_ready"] is False
    assert result["safe_show_commands_allowed"] is False
    assert result["prompt_classification"]["label"] == "Login required"
    assert result["prompt_classification"]["classification"] == "login_prompt"


def test_cisco_prompt_readiness_classifies_password_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(tmp_path, monkeypatch, "Password:")

    assert writes == [b"\n"]
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "password-required"
    assert result["prompt_classification"]["classification"] == "password_prompt"


def test_cisco_prompt_readiness_blocks_config_mode_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(
        tmp_path,
        monkeypatch,
        "Switch01(config)#",
    )

    assert writes == [b"\n"]
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "config-mode"
    assert result["config_mode_detected"] is True
    assert result["prompt_ready"] is False
    assert result["safe_show_commands_allowed"] is False
    assert result["prompt_classification"]["label"] == "Configuration mode"


def test_cisco_prompt_readiness_blocks_unknown_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(
        tmp_path,
        monkeypatch,
        "unrecognized prompt text",
    )

    assert writes == [b"\n", b"\r", b"\x03", b"\x1a"] * 5
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "unknown"
    assert result["prompt_ready"] is False
    assert result["safe_show_commands_allowed"] is False
    assert result["prompt_classification"]["label"] == "Unknown prompt"
    assert result["prompt_classification"]["no_output_captured"] is False


def test_cisco_prompt_readiness_blocks_when_no_prompt_text_captured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(
        tmp_path,
        monkeypatch,
        "",
    )

    assert writes == [b"\n", b"\r", b"\x03", b"\x1a"] * 5
    assert result["status"] == "blocked"
    assert result["message"].startswith("Console port opened but no prompt text was captured")
    assert result["blockers"] == [result["message"]]
    assert result["prompt_state"] == "unknown"
    assert result["prompt_ready"] is False
    assert result["safe_show_commands_allowed"] is False
    assert result["future_show_command_check_eligible"] is False
    assert result["prompt_sample"]["captured"] is False
    assert result["prompt_classification"]["no_output_captured"] is True
    assert result["prompt_classification"]["classification"] == "no_bytes_read"
    assert result["troubleshooting_checklist"]
    assert any("Cisco console port" in item for item in result["troubleshooting_checklist"])
    assert "safe show commands" in result["not_attempted"]
    assert "configure terminal" in result["not_attempted"]
    assert "write memory" in result["not_attempted"]
    assert "reload" in result["not_attempted"]
    assert "copy or erase" in result["not_attempted"]
    assert "safe_show_commands" not in result


def test_cisco_prompt_readiness_reports_configured_read_timing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    writes = _install_tracking_fake_serial(monkeypatch, [""])

    result = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(
            port=str(tty),
            baud=9600,
            timeout_seconds=1.0,
            prompt_settle_seconds=0.1,
            prompt_read_window_seconds=0.2,
            prompt_max_bytes=123,
        ),
        paths=_discovery_paths(paths),
    ).prompt_readiness()

    assert writes == [b"\n", b"\r", b"\x03", b"\x1a"] * 5
    assert result["status"] == "blocked"
    assert result["read_timing"]["settle_seconds"] == 0.1
    assert result["read_timing"]["read_window_seconds"] == 0.2
    assert result["read_timing"]["read_windows"] == [0.2, 0.8, 1.5]
    assert result["read_timing"]["max_bytes"] == 123
    assert result["read_timing"]["dtr_rts_toggle"] == "attempted when supported"
    assert result["safe_show_commands_allowed"] is False


def test_cisco_prompt_readiness_classifies_wrong_baud_gibberish(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(
        tmp_path,
        monkeypatch,
        "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd",
    )

    assert writes == [b"\n", b"\r", b"\x03", b"\x1a"] * 5
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "unreadable"
    assert result["prompt_classification"]["classification"] == "unreadable_gibberish"


def test_cisco_prompt_readiness_classifies_port_in_use(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _run_prompt_readiness_with_serial_open_error(tmp_path, monkeypatch, OSError("Device or resource busy"))

    assert result["status"] == "blocked"
    assert result["prompt_state"] == "unknown"
    assert result["attempts"][0]["prompt_state"] == "port-in-use"
    assert result["attempts"][0]["classification"] == "port_in_use"


def test_cisco_prompt_readiness_classifies_permission_denied(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result = _run_prompt_readiness_with_serial_open_error(tmp_path, monkeypatch, PermissionError("Permission denied"))

    assert result["status"] == "blocked"
    assert result["attempts"][0]["prompt_state"] == "permission-denied"
    assert result["attempts"][0]["classification"] == "permission_denied"


def test_cisco_ansible_run_command_can_redact_output() -> None:
    result = _run_command(
        [sys.executable, "-c", "print('device output that should not be returned')"],
        timeout_seconds=3.0,
        include_output=False,
    )
    encoded = json.dumps(result)

    assert result["returncode"] == 0
    assert result["raw_output_redacted"] is True
    assert result["stdout_bytes"] > 0
    assert "stdout_tail" not in result
    assert "device output" not in encoded


def test_cisco_ansible_inventory_targets_switch_not_control_host() -> None:
    config = CiscoAnsibleConfig(
        host="192.168.1.204",
        username="switch-admin",
        password="super-secret-password",
        enable_password="enable-secret",
        network_os="cisco.ios.ios",
        connection="ansible.netcommon.network_cli",
        timeout_seconds=1.0,
        control_host="192.168.1.205",
    )

    inventory_path = _write_temp_inventory(config)
    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    finally:
        inventory_path.unlink(missing_ok=True)

    host_vars = inventory["all"]["hosts"]["cisco_target"]
    assert host_vars["ansible_host"] == "192.168.1.204"
    assert "192.168.1.205" not in json.dumps(inventory)


def test_cisco_setup_readiness_is_plan_only_until_management_bootstrap() -> None:
    clear_probe_results()
    readiness = get_cisco_setup_readiness(
        provider_mode="mock",
        planned_management_ip="192.168.1.204",
        management_configured=False,
    )
    encoded = json.dumps(readiness)

    assert readiness["provider_id"] == "cisco-setup"
    assert readiness["phase"] == "console-bootstrap-required"
    assert readiness["planned_management_ip"] == "192.168.1.204"
    assert readiness["management_configured"] is False
    assert readiness["state_boundaries"]["discovered_current_device_state"]["summary"]
    assert readiness["state_boundaries"]["saved_kit_config_values"]["planned_management_ip"] == "192.168.1.204"
    assert readiness["state_boundaries"]["saved_kit_config_values"]["management_configured"] is False
    assert readiness["state_boundaries"]["values_ready_to_apply"]["ready"] is False
    assert readiness["state_boundaries"]["last_action_logs_artifacts"]["raw_console_log_saved"] is False
    assert readiness["state_boundaries"]["last_action_logs_artifacts"]["last_action_present"] is False
    assert readiness["console"]["selected_path"] == readiness["console"]["effective_path"]
    assert readiness["console"]["baud"] == 9600
    assert readiness["console"]["last_prompt_readiness"]["available"] is False
    assert readiness["console"]["last_prompt_readiness"]["safe_show_commands_allowed"] is False
    assert readiness["console"]["last_prompt_readiness"]["prompt_classification"]["state"] == "unknown"
    assert readiness["bootstrap_preview"]["apply_enabled"] is False
    assert readiness["bootstrap_preview"]["commands_redacted"] is True
    assert readiness["bootstrap_preview"]["serial_writes_attempted"] is False
    assert "recent prompt-readiness evidence" in readiness["bootstrap_preview"]["missing_requirements"]
    assert readiness["bootstrap_preview"]["redacted_command_summary"]
    assert readiness["ssh_scp_readiness"]["planned_only"] is True
    assert readiness["ssh_scp_readiness"]["apply_enabled"] is False
    assert readiness["ansible"]["enabled"] is False
    assert readiness["ansible"]["status"] == "awaiting-bootstrap"
    assert "CISCO_MGMT_CONFIGURED is false" in readiness["ansible"]["reason"]
    assert readiness["backup_report"]["backup_enabled"] is False
    assert readiness["next_safe_action"] == (
        "Select a console candidate and run prompt readiness check."
    )
    assert "conf t" in readiness["disabled_actions"]
    assert "write memory" in readiness["disabled_actions"]
    assert "reload" in readiness["disabled_actions"]
    assert "running-config backup" in readiness["disabled_actions"]
    assert "Configure Terminal" not in encoded
    assert "/probe" not in encoded


def test_cisco_setup_readiness_surfaces_no_output_prompt_guidance() -> None:
    clear_probe_results()
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "action": "prompt-readiness",
            "status": "blocked",
            "message": "Console port opened but no prompt text was captured.",
            "prompt_state": "unknown",
            "safe_show_commands_allowed": False,
            "prompt_sample": {"captured": False, "line_count": 0, "last_line": "unrecognized prompt"},
            "prompt_classification": {
                "state": "unknown",
                "label": "Unknown prompt",
                "summary": "Console port opened, but no prompt text was captured.",
                "no_output_captured": True,
                "raw_text_redacted": True,
                "safe_show_commands_allowed": False,
                "next_safe_action": "Verify adapter ownership and baud.",
            },
            "read_timing": {
                "settle_seconds": 0.5,
                "read_window_seconds": 1.0,
                "max_bytes": 8192,
            },
            "troubleshooting_checklist": ["Try baud 9600 first, then 115200 if needed."],
            "warnings": [],
            "blockers": ["Console port opened but no prompt text was captured."],
        },
    )

    readiness = get_cisco_setup_readiness(
        provider_mode="mock",
        planned_management_ip="192.168.1.204",
        management_configured=False,
    )

    last_prompt = readiness["console"]["last_prompt_readiness"]
    discovered_state = readiness["state_boundaries"]["discovered_current_device_state"]

    assert last_prompt["available"] is True
    assert last_prompt["prompt_state"] == "unknown"
    assert last_prompt["captured"] is False
    assert last_prompt["safe_show_commands_allowed"] is False
    assert last_prompt["read_timing"]["read_window_seconds"] == 1.0
    assert last_prompt["prompt_classification"]["no_output_captured"] is True
    assert "115200" in last_prompt["troubleshooting_checklist"][0]
    assert discovered_state["prompt_captured"] is False


def test_cisco_setup_readiness_surfaces_password_recovery_summary(tmp_path: Path, monkeypatch) -> None:
    details_path = tmp_path / "cisco-details.json"
    details_path.write_text(
        json.dumps(
            {
                "status": "blocked",
                "checked_at": "2026-06-06T00:00:00Z",
                "stages": {
                    "adapter_discovery": {"effective_path": "/dev/ttyUSB0"},
                    "console_prompt_detection": {"prompt_detected": True, "prompt_state": "exec", "selected_baud": 9600},
                    "privilege_escalation": {
                        "initial_prompt_state": "exec",
                        "enable_command_sent": True,
                        "password_prompt_seen": True,
                        "final_prompt_state": "exec",
                        "debug": {"enable_command_sent": True, "password_prompt_seen": True},
                        "blockers": ["Configured console credentials did not reach a privileged exec prompt."],
                    },
                },
                "blockers": ["Privileged exec prompt is required for bootstrap apply."],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.services.cisco_setup_readiness.REAL_LAB_DETAILS", details_path)

    readiness = get_cisco_setup_readiness(provider_mode="mock", management_configured=False)

    assert readiness["password_recovery"]["needed"] is True
    assert readiness["password_recovery"]["enable_command_sent"] is True
    assert readiness["password_recovery"]["password_prompt_seen"] is True
    assert readiness["password_recovery"]["enable_rejected"] == "yes"
    assert readiness["password_recovery"]["final_prompt_state"] == "exec"
    assert "password recovery" in readiness["password_recovery"]["next_action"].lower()


def test_cisco_setup_wizard_plan_unknown_state_is_safe_preview() -> None:
    plan = build_cisco_setup_wizard_plan()

    assert plan["provider_id"] == "cisco-setup-wizard-plan"
    assert plan["status"] == "preview"
    assert plan["apply_enabled"] is False
    assert plan["detected_prompt_state"] == "unknown"
    assert plan["setup_wizard_detected"] is False
    assert "answer setup wizard" in plan["disabled_actions"]
    assert "conf t" in plan["disabled_actions"]
    assert "write memory" in plan["disabled_actions"]
    assert "reload" in plan["disabled_actions"]
    assert "erase/copy" in plan["disabled_actions"]
    assert "enable SSH/SCP" in plan["disabled_actions"]
    assert "real config apply" in plan["disabled_actions"]
    assert "answer setup wizard yes/no prompt" in plan["not_attempted"]


def test_cisco_setup_wizard_plan_detects_setup_wizard_prompt_result() -> None:
    plan = build_cisco_setup_wizard_plan(
        {
            "provider_id": "cisco-console",
            "action": "prompt-readiness",
            "prompt_state": "setup-wizard",
        }
    )

    assert plan["status"] == "preview"
    assert plan["apply_enabled"] is False
    assert plan["detected_prompt_state"] == "setup-wizard"
    assert plan["setup_wizard_detected"] is True
    assert "No answers or commands were sent" in plan["message"]
    assert plan["next_safe_action"] == (
        "Review the setup wizard plan preview and define the future guarded bootstrap requirements."
    )


def test_cisco_setup_readiness_surfaces_setup_wizard_plan_when_cached() -> None:
    clear_probe_results()
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "action": "prompt-readiness",
            "status": "blocked",
            "message": "Console is at an initial setup wizard prompt.",
            "prompt_state": "setup-wizard",
            "warnings": [],
            "blockers": [],
        },
    )

    readiness = get_cisco_setup_readiness(
        provider_mode="mock",
        planned_management_ip="192.168.1.204",
        management_configured=False,
    )

    assert readiness["setup_wizard_plan"]["available"] is True
    assert readiness["setup_wizard_plan"]["detected"] is True
    assert readiness["setup_wizard_plan"]["detected_prompt_state"] == "setup-wizard"
    assert readiness["setup_wizard_plan"]["apply_enabled"] is False
    assert readiness["next_safe_action"] == "Review setup wizard plan preview."


def test_cisco_bootstrap_requirements_reports_missing_inputs_preview_only() -> None:
    requirements = build_cisco_bootstrap_requirements(
        planned_management_ip="192.168.1.204",
        local_admin_username_configured=False,
        management_configured=False,
    )

    assert requirements["provider_id"] == "cisco-bootstrap-requirements"
    assert requirements["status"] == "needs-input"
    assert requirements["apply_enabled"] is False
    assert requirements["requirements"]["planned_management_ip"]["value"] == "192.168.1.204"
    assert requirements["requirements"]["subnet_prefix"]["configured"] is False
    assert requirements["requirements"]["gateway"]["configured"] is False
    assert requirements["requirements"]["management_vlan_interface_strategy"]["configured"] is False
    assert requirements["requirements"]["local_admin_username"]["presence_only"] is True
    assert "Management subnet/prefix is required." in requirements["blockers"]
    assert "Management gateway is required." in requirements["blockers"]
    assert "Management VLAN/interface strategy is required." in requirements["blockers"]
    assert "Local admin username presence must be confirmed." in requirements["blockers"]
    assert "answer setup wizard" in requirements["disabled_actions"]
    assert "conf t" in requirements["disabled_actions"]
    assert "write memory" in requirements["disabled_actions"]
    assert "reload" in requirements["disabled_actions"]
    assert "erase/copy" in requirements["disabled_actions"]
    assert "enable SSH/SCP" in requirements["disabled_actions"]
    assert "real config apply" in requirements["disabled_actions"]
    assert "CISCO_MGMT_CONFIGURED is false" in requirements["warnings"][0]


def test_cisco_bootstrap_requirements_keep_username_presence_only() -> None:
    requirements = build_cisco_bootstrap_requirements(
        planned_management_ip="192.168.1.204",
        subnet_prefix="/24",
        gateway="192.168.1.1",
        management_vlan="8",
        management_interface="Vlan8",
        management_strategy="SVI",
        hostname="switch-preview",
        domain_name="example.test",
        dns_servers=["192.0.2.53"],
        local_admin_username_configured=True,
        management_configured=False,
    )
    encoded = json.dumps(requirements)

    assert requirements["requirements"]["local_admin_username"]["configured"] is True
    assert requirements["requirements"]["local_admin_username"]["value"] == "configured"
    assert "switch-admin" not in encoded
    assert requirements["requirements"]["ssh_scp_policy"]["planned_only"] is True
    assert requirements["requirements"]["ssh_scp_policy"]["apply_enabled"] is False
    assert requirements["requirements"]["save_behavior"]["enabled"] is False
    assert requirements["requirements"]["confirmation_requirements"]["configured"] is True
    assert requirements["blockers"] == [
        "Bootstrap requirements are preview-only; no answers or commands will be sent."
    ]


def test_cisco_bootstrap_requirements_save_non_secret_planning_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)

    requirements = save_cisco_bootstrap_requirements(_valid_bootstrap_payload())
    encoded = json.dumps(requirements)

    assert state_path.exists()
    assert requirements["status"] == "preview"
    assert requirements["apply_enabled"] is False
    assert requirements["requirements"]["planned_management_ip"]["value"] == "192.168.1.204"
    assert requirements["requirements"]["subnet_prefix"]["configured"] is True
    assert requirements["requirements"]["gateway"]["configured"] is True
    assert requirements["requirements"]["management_vlan_interface_strategy"]["configured"] is True
    assert requirements["requirements"]["hostname"]["configured"] is True
    assert requirements["requirements"]["domain_dns"]["configured"] is True
    assert requirements["requirements"]["local_admin_username"]["value"] == "configured"
    assert requirements["requirements"]["local_admin_username"]["reference"] == "local-env:CISCO_TEST_USERNAME"
    assert requirements["requirements"]["ssh_scp_policy"]["apply_enabled"] is False
    assert requirements["requirements"]["save_behavior"]["enabled"] is False
    assert requirements["blockers"] == [
        "Bootstrap requirements are preview-only; no answers or commands will be sent."
    ]
    assert "super-secret" not in encoded


def test_cisco_console_bootstrap_plan_uses_real_lab_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "action": "prompt-readiness",
            "status": "ok",
            "message": "ready",
            "prompt_state": "exec",
            "warnings": [],
            "blockers": [],
        },
    )
    monkeypatch.setattr(
        "app.services.cisco_console_bootstrap.CiscoConsoleAdapter.health",
        lambda _self: ProviderStatus(
            id="cisco-console",
            name="Cisco Console",
            kind="network-console",
            mode="local-readonly",
            status="ready",
            capabilities=[],
            message="ready",
            discovery={"effective_path": "/dev/serial/by-id/mock-cisco-console"},
            blockers=[],
            warnings=[],
        ),
    )

    plan = build_cisco_console_bootstrap_plan()
    encoded = json.dumps(plan)

    assert plan["status"] == "preview"
    assert plan["target"]["ip"] == "192.168.1.204"
    assert plan["target"]["prefix"] == "/24"
    assert plan["target"]["netmask"] == "255.255.255.0"
    assert plan["flow"] == "direct-exec-config-mode-flow"
    assert plan["confirmation_phrase"] == CONFIRMATION_PHRASE
    assert plan["apply_enabled"] is False
    assert plan["serial_writes_attempted"] is False
    assert "write erase" in plan["destructive_actions_disabled"]
    assert "erase startup-config" in plan["destructive_actions_disabled"]
    assert "reload" in plan["destructive_actions_disabled"]
    assert plan["redacted_command_summary"]
    assert plan["artifact_preview"]["raw_console_log_saved"] is False
    assert plan["blocker_summary"]["count"] == len(plan["blockers"])
    assert "copy running-config" not in encoded


def test_cisco_console_bootstrap_plan_blocks_no_output_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())
    _record_prompt_readiness("unknown", prompt_sample={"captured": False})
    _mock_ready_console(monkeypatch)

    plan = build_cisco_console_bootstrap_plan()

    assert plan["status"] == "blocked"
    assert plan["prompt_detail"] == "unknown-no-output"
    assert plan["flow"] == "unknown-no-output-blocked-flow"
    assert plan["serial_writes_attempted"] is False
    assert plan["artifact_preview"]["raw_console_log_saved"] is False
    assert plan["blocker_summary"]["has_prompt_blocker"] is True
    assert any("no prompt text was captured" in blocker for blocker in plan["blockers"])
    assert any("no prompt text was captured" in step for step in plan["intended_steps"])


def test_cisco_console_bootstrap_plan_blocks_login_required_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())
    _record_prompt_readiness("login-required")
    _mock_ready_console(monkeypatch)

    plan = build_cisco_console_bootstrap_plan()

    assert plan["status"] == "blocked"
    assert plan["flow"] == "login-required-blocked-flow"
    assert any("Login-required prompt is not supported" in blocker for blocker in plan["blockers"])


def test_cisco_console_bootstrap_plan_blocks_config_mode_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())
    _record_prompt_readiness("config-mode")
    _mock_ready_console(monkeypatch)

    plan = build_cisco_console_bootstrap_plan()

    assert plan["status"] == "blocked"
    assert plan["flow"] == "config-mode-blocked-flow"
    assert any("Configuration-mode prompt is not supported" in blocker for blocker in plan["blockers"])


def test_cisco_console_bootstrap_apply_blocked_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())

    result = apply_cisco_console_bootstrap({"confirmation_phrase": CONFIRMATION_PHRASE})

    assert result["status"] == "blocked"
    assert result["serial_writes_attempted"] is False
    assert result["commands_sent"] == []
    assert any("PROVIDER_MODE=local-readonly" in blocker for blocker in result["blockers"])


def test_cisco_console_bootstrap_apply_rejects_destructive_requested_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())

    result = apply_cisco_console_bootstrap(
        {
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "requested_actions": ["reload"],
        }
    )

    assert result["status"] == "blocked"
    assert result["serial_writes_attempted"] is False
    assert result["commands_sent"] == []
    assert any("Destructive reset/wipe/copy/reload" in blocker for blocker in result["blockers"])


def test_cisco_console_bootstrap_apply_requires_exact_phrase(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(_valid_bootstrap_payload())

    result = apply_cisco_console_bootstrap({"confirmation_phrase": "APPLY"})

    assert result["status"] == "blocked"
    assert result["serial_writes_attempted"] is False
    assert any("Exact confirmation phrase" in blocker for blocker in result["blockers"])


def test_cisco_console_bootstrap_plan_rejects_wrong_target_or_prefix(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    save_cisco_bootstrap_requirements(
        {
            **_valid_bootstrap_payload(),
            "planned_management_ip": "192.168.1.221",
            "subnet_prefix": "/25",
        }
    )

    plan = build_cisco_console_bootstrap_plan()

    assert plan["status"] == "blocked"
    assert "Planned target IP must be 192.168.1.204." in plan["blockers"]
    assert "Planned target prefix must be /24." in plan["blockers"]


def test_cisco_bootstrap_requirements_reject_invalid_values(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state_path = tmp_path / "bootstrap-requirements.json"
    monkeypatch.setattr("app.services.cisco_bootstrap_requirements.STATE_PATH", state_path)
    payload = {
        **_valid_bootstrap_payload(),
        "planned_management_ip": "not-an-ip",
        "gateway": "bad-gateway",
        "hostname": "bad host name",
    }

    try:
        save_cisco_bootstrap_requirements(payload)
    except Exception as exc:
        errors = getattr(exc, "errors", [])
    else:  # pragma: no cover - defensive
        raise AssertionError("invalid bootstrap requirements should fail validation")

    fields = {error["field"] for error in errors}
    assert {"planned_management_ip", "gateway", "hostname"}.issubset(fields)
    assert not state_path.exists()


def test_esxi_configured_false_returns_planned_status_and_skips_probe(monkeypatch) -> None:
    def fail_tcp(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("ESXI_CONFIGURED=false must skip network probes")

    monkeypatch.setattr("app.providers.esxi_readonly._tcp_connect", fail_tcp)
    adapter = EsxiReadonlyAdapter(
        provider_mode="local-readonly",
        config=EsxiReadonlyConfig(
            host="192.0.2.50",
            username=None,
            password=None,
            verify_tls=False,
            timeout_seconds=1.0,
            ssh_timeout_seconds=1.0,
            management_configured=False,
        ),
    )

    status = adapter.health()
    probe = adapter.probe()

    assert status.status == "planned-target"
    assert status.blockers == []
    assert status.configuration["management_configured"] is False
    assert status.configuration["planned_target"] is True
    assert status.safe_actions[0].enabled is False
    assert "Install/configure ESXi management network" in status.safe_actions[0].reason
    assert probe["status"] == "skipped"
    assert probe["blockers"] == []
    assert "HTTPS reachability check" in probe["not_attempted"]


def test_esxi_configured_true_runs_readonly_reachability(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.providers.esxi_readonly.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )

    def fake_tcp(host: str, port: int, _timeout_seconds: float) -> dict[str, object]:
        calls.append((host, port))
        return {"reachable": False, "port": port, "attempts": []}

    monkeypatch.setattr("app.providers.esxi_readonly._tcp_connect", fake_tcp)
    adapter = EsxiReadonlyAdapter(
        provider_mode="local-readonly",
        config=EsxiReadonlyConfig(
            host="192.0.2.50",
            username=None,
            password=None,
            verify_tls=False,
            timeout_seconds=1.0,
            ssh_timeout_seconds=1.0,
            management_configured=True,
        ),
    )

    result = adapter.probe()

    assert calls == [("192.0.2.50", 443), ("192.0.2.50", 22)]
    assert result["status"] == "failed"
    assert "ESXi HTTPS port is not reachable." in result["blockers"]


def test_esxi_tool_availability_checks_repo_local_bin(monkeypatch, tmp_path: Path) -> None:
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    tool = local_bin / "govc"
    tool.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(esxi_readonly, "REPO_ROOT", tmp_path)

    assert esxi_readonly._which("govc") is True


def test_cisco_management_configured_false_returns_bootstrap_status_and_skips_probe(
    monkeypatch,
) -> None:
    def fail_tcp(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("CISCO_MGMT_CONFIGURED=false must skip SSH probes")

    monkeypatch.setattr("app.providers.cisco_ansible._tcp_connect", fail_tcp)
    adapter = CiscoAnsibleAdapter(
        provider_mode="local-readonly",
        config=CiscoAnsibleConfig(
            host="192.0.2.60",
            username=None,
            password=None,
            enable_password=None,
            network_os="cisco.ios.ios",
            connection="ansible.netcommon.network_cli",
            timeout_seconds=1.0,
            management_configured=False,
        ),
    )

    status = adapter.health()
    probe = adapter.probe()

    assert status.status == "awaiting-bootstrap"
    assert status.blockers == []
    assert status.configuration["management_configured"] is False
    assert status.configuration["planned_target"] is True
    assert status.safe_actions[0].enabled is False
    assert "Use console bootstrap before Ansible SSH" in status.safe_actions[0].reason
    assert all("Ansible CLI" not in warning for warning in status.warnings)
    assert probe["status"] == "skipped"
    assert probe["blockers"] == []
    assert "Cisco SSH reachability check" in probe["not_attempted"]


def test_cisco_management_configured_false_without_target_returns_not_configured() -> None:
    status = CiscoAnsibleAdapter(
        provider_mode="local-readonly",
        config=CiscoAnsibleConfig(
            host=None,
            username=None,
            password=None,
            enable_password=None,
            network_os="cisco.ios.ios",
            connection="ansible.netcommon.network_cli",
            timeout_seconds=1.0,
            management_configured=False,
        ),
    ).health()

    assert status.status == "not-configured"
    assert status.blockers == []
    assert status.configuration["planned_target"] is False
    assert status.configuration["safe_next_action"] == "Use console bootstrap before Ansible SSH."


def test_cisco_management_configured_true_runs_ssh_reachability(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.providers.cisco_ansible.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )

    def fake_tcp(host: str, port: int, _timeout_seconds: float) -> dict[str, object]:
        calls.append((host, port))
        return {"reachable": False, "port": port, "attempts": []}

    monkeypatch.setattr("app.providers.cisco_ansible._tcp_connect", fake_tcp)
    adapter = CiscoAnsibleAdapter(
        provider_mode="local-readonly",
        config=CiscoAnsibleConfig(
            host="192.0.2.60",
            username="switch-admin",
            password="super-secret-password",
            enable_password=None,
            network_os="cisco.ios.ios",
            connection="ansible.netcommon.network_cli",
            timeout_seconds=1.0,
            management_configured=True,
        ),
    )

    result = adapter.probe()

    assert calls == [("192.0.2.60", 22)]
    assert result["status"] == "blocked"
    assert result["blockers"] == ["Cisco SSH is not reachable."]


def test_cisco_console_discovery_runs_when_management_is_not_configured(
    tmp_path: Path,
) -> None:
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    stable = paths["by_id"] / "usb-Cisco_console-if00-port0"
    stable.symlink_to(tty)

    ansible_status = CiscoAnsibleAdapter(
        provider_mode="mock",
        config=CiscoAnsibleConfig(
            host="192.0.2.60",
            username=None,
            password=None,
            enable_password=None,
            network_os="cisco.ios.ios",
            connection="ansible.netcommon.network_cli",
            timeout_seconds=1.0,
            management_configured=False,
        ),
    ).health()
    console_status = CiscoConsoleAdapter(
        provider_mode="mock",
        config=CiscoConsoleConfig(port=None, baud=9600, timeout_seconds=1.0),
        paths=_discovery_paths(paths),
    ).health()

    assert ansible_status.status == "awaiting-bootstrap"
    assert console_status.status == "ready"
    assert console_status.discovery is not None
    assert console_status.discovery["effective_path"] == str(stable)


def test_provider_smoke_skips_unconfigured_management_tcp_preflight(monkeypatch) -> None:
    smoke = _load_provider_smoke_module()
    calls: list[tuple[str, int]] = []
    fake_settings = types.SimpleNamespace(
        provider_mode="local-readonly",
        ilo_test_host="192.0.2.202",
        ilo_test_username="local-admin",
        ilo_test_password="local-password",
        ilo_test_verify_tls=False,
        ilo_test_timeout_seconds=1.0,
        esxi_test_host="192.0.2.50",
        esxi_configured=False,
        cisco_target_ip="192.0.2.60",
        cisco_mgmt_configured=False,
    )

    def fake_tcp(host: str, port: int) -> dict[str, object]:
        calls.append((host, port))
        return {"configured": True, "reachable": True, "port": port, "attempts": []}

    monkeypatch.setattr(smoke, "settings", fake_settings)
    monkeypatch.setattr("app.providers.ilo_redfish.settings", fake_settings)
    monkeypatch.setattr(
        smoke,
        "current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )
    monkeypatch.setattr(smoke, "_tcp_connect", fake_tcp)

    result = smoke._tcp_preflight()

    assert calls == [("192.0.2.202", 443)]
    assert result["ilo_https"]["reachable"] is True
    assert result["esxi_https"]["skipped"] is True
    assert result["esxi_https"]["configured"] is False
    assert result["esxi_https"]["planned_target"] is True
    assert "ESXI_CONFIGURED=false" in result["esxi_https"]["reason"]
    assert result["cisco_ssh"]["skipped"] is True
    assert result["cisco_ssh"]["configured"] is False
    assert result["cisco_ssh"]["planned_target"] is True
    assert "CISCO_MGMT_CONFIGURED=false" in result["cisco_ssh"]["reason"]


def test_provider_smoke_provider_filter_limits_tcp_preflight(monkeypatch) -> None:
    smoke = _load_provider_smoke_module()
    calls: list[tuple[str, int]] = []
    fake_settings = types.SimpleNamespace(
        provider_mode="local-readonly",
        ilo_test_host="192.0.2.202",
        ilo_test_username="local-admin",
        ilo_test_password="local-password",
        ilo_test_verify_tls=False,
        ilo_test_timeout_seconds=1.0,
        esxi_test_host="192.0.2.50",
        esxi_configured=True,
        cisco_target_ip="192.0.2.60",
        cisco_mgmt_configured=True,
    )

    def fake_tcp(host: str, port: int) -> dict[str, object]:
        calls.append((host, port))
        return {"configured": True, "reachable": True, "port": port, "attempts": []}

    monkeypatch.setattr(smoke, "settings", fake_settings)
    monkeypatch.setattr("app.providers.ilo_redfish.settings", fake_settings)
    monkeypatch.setattr(
        smoke,
        "current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )
    monkeypatch.setattr(smoke, "_tcp_connect", fake_tcp)

    result = smoke._tcp_preflight(["ilo-redfish"])

    assert calls == [("192.0.2.202", 443)]
    assert set(result) == {"ilo_https"}
    assert result["ilo_https"]["reachable"] is True


def test_provider_smoke_ilo_preflight_uses_active_lab_profile(monkeypatch) -> None:
    smoke = _load_provider_smoke_module()
    calls: list[tuple[str, int]] = []
    monkeypatch.setenv("ILO_TEST_HOST", "192.168.1.201")
    monkeypatch.setattr(
        smoke,
        "settings",
        types.SimpleNamespace(
            provider_mode="local-readonly",
            esxi_test_host="192.0.2.50",
            esxi_configured=False,
            cisco_target_ip="192.0.2.60",
            cisco_mgmt_configured=False,
        ),
    )
    monkeypatch.setattr(
        smoke,
        "current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )
    create_lab_profile(
        {
            "name": "TDC-LAB",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.200",
                "server_embedded_nic": "10.10.8.201",
                "esxi_management": "10.10.8.202",
                "cisco_management": "10.10.8.203",
                "ansible_control_host": "10.10.8.5",
            },
        }
    )

    def fake_tcp(host: str, port: int) -> dict[str, object]:
        calls.append((host, port))
        return {"configured": True, "reachable": True, "port": port, "attempts": []}

    monkeypatch.setattr(smoke, "_tcp_connect", fake_tcp)

    result = smoke._tcp_preflight(["ilo-redfish"])

    assert calls == [("10.10.8.200", 443)]
    assert result["ilo_https"]["reachable"] is True


def test_provider_smoke_ilo_preflight_tries_first_access_candidate(monkeypatch) -> None:
    smoke = _load_provider_smoke_module()
    calls: list[tuple[str, int]] = []
    monkeypatch.setenv("ILO_TEST_HOST", "192.168.1.201")
    monkeypatch.setattr(
        smoke,
        "settings",
        types.SimpleNamespace(
            provider_mode="local-readonly",
            esxi_test_host="192.0.2.50",
            esxi_configured=False,
            cisco_target_ip="192.0.2.60",
            cisco_mgmt_configured=False,
        ),
    )
    monkeypatch.setattr(
        smoke,
        "current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )
    create_lab_profile(
        {
            "name": "TDC-LAB",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.200",
                "server_embedded_nic": "10.10.8.201",
                "esxi_management": "10.10.8.202",
                "cisco_management": "10.10.8.203",
                "ansible_control_host": "10.10.8.5",
            },
        }
    )
    update_control_access_config(
        "ilo",
        {
            "first_time_configuring": True,
            "original_dhcp_ip": "10.10.8.110",
            "username_reference": "local-admin",
            "password_configured": True,
            "password_reference_label": "local secret ref",
        },
    )

    def fake_tcp(host: str, port: int) -> dict[str, object]:
        calls.append((host, port))
        return {
            "configured": True,
            "reachable": host == "10.10.8.110",
            "port": port,
            "attempts": [],
        }

    monkeypatch.setattr(smoke, "_tcp_connect", fake_tcp)

    result = smoke._tcp_preflight(["ilo-redfish"])

    assert calls == [("10.10.8.200", 443), ("10.10.8.110", 443)]
    assert result["ilo_https"]["reachable"] is True
    assert result["ilo_https"]["candidate_count"] == 2
    assert result["ilo_https"]["selected_source"] == "control_access_original_dhcp_ip"


def test_provider_smoke_provider_filter_reads_env(monkeypatch) -> None:
    smoke = _load_provider_smoke_module()

    monkeypatch.setenv("PROVIDER_SMOKE_PROVIDERS", "ilo-redfish, esxi-readonly")

    assert smoke._selected_provider_ids() == ["ilo-redfish", "esxi-readonly"]


def test_provider_smoke_provider_filter_skips_serial_preflight(monkeypatch) -> None:
    smoke = _load_provider_smoke_module()
    fake_settings = types.SimpleNamespace(
        provider_mode="mock",
        ilo_test_host="192.0.2.202",
        esxi_test_host=None,
        esxi_configured=False,
        cisco_target_ip=None,
        cisco_mgmt_configured=False,
    )

    monkeypatch.setattr(smoke, "settings", fake_settings)

    result = smoke._preflight_summary(["ilo-redfish"])

    assert "serial_candidates" not in result
    assert set(result["targets"]) == {"ilo"}
    assert set(result["tcp_preflight"]) == {"ilo_https"}
    assert [item["name"] for item in result["required_env"]] == [
        "LAB_CLOSED_LOOP_ACK",
        "LAB_READONLY_ACK",
        "LAB_DESTRUCTIVE_ACK",
        "ILO_TEST_HOST",
        "ILO_TEST_USERNAME",
        "ILO_TEST_PASSWORD",
    ]


def test_provider_smoke_disabled_management_probe_keeps_planned_context() -> None:
    smoke = _load_provider_smoke_module()
    status = ProviderStatus(
        id="esxi-readonly",
        name="ESXi Read-Only",
        kind="virtualization",
        mode="local-readonly",
        status="planned-target",
        capabilities=["explicit-read-only-probe"],
        message="status only",
        configuration={
            "management_configured": False,
            "planned_target": True,
            "host_configured": True,
            "missing_fields": [],
            "safe_next_action": (
                "Install/configure ESXi management network before read-only probe."
            ),
        },
        warnings=["ESXI_CONFIGURED is false; ESXi management network probes are skipped."],
        safe_actions=[
            ProviderAction(
                id="probe-esxi-readonly",
                label="Read-Only Probe",
                enabled=False,
                read_only=True,
                reason="Install/configure ESXi management network before read-only probe.",
            )
        ],
    )
    adapter = types.SimpleNamespace(health=lambda: status)

    summary = smoke._run_optional_probe("esxi-readonly", adapter)
    details = smoke._probe_detail_lines(summary)

    assert summary["status"] == "skipped"
    assert summary["configuration"]["planned_target"] is True
    assert summary["configuration"]["management_configured"] is False
    assert "HTTPS reachability check" in summary["not_attempted"]
    assert any("skipped_reason" in line for line in details)
    assert not any("https_reachable: False" in line for line in details)


def test_hpe_raid_plan_preserves_existing_esxi_layout() -> None:
    raid = _load_hpe_raid_plan_module()

    plan = raid._raid_plan(
        {"server_model": "ProLiant DL360 Gen10"},
        {
            "controllers": [{"Model": "HPE Smart Array P408i-a SR Gen10"}],
            "physical_drives": [{"Id": str(index)} for index in range(8)],
            "logical_drives": [
                {
                    "LogicalDriveName": "OS RAID 1 logical drive",
                    "LogicalDriveNumber": 1,
                    "RAIDType": "RAID1",
                    "CapacityMiB": 512000,
                    "Status": {"Health": "OK"},
                },
                {
                    "LogicalDriveName": "Data RAID 6 logical drive",
                    "LogicalDriveNumber": 2,
                    "RAIDType": "RAID6",
                    "CapacityMiB": 3433827,
                    "Status": {"Health": "OK"},
                },
            ],
        },
    )

    assert plan["status"] == "preview_only"
    assert plan["apply_allowed"] is False
    assert plan["planned_layout"]["recommendation"] == (
        "preserve existing OS and data logical drives for ESXi preview"
    )
    assert plan["planned_layout"]["boot_volume"]["source"] == "existing-logical-drive"
    assert plan["planned_layout"]["boot_volume"]["raid"] == "RAID1"
    assert plan["planned_layout"]["datastore_volume"]["source"] == "existing-logical-drive"
    assert plan["planned_layout"]["datastore_volume"]["raid"] == "RAID6"
    assert "RAID create/delete/update" in plan["not_attempted"]


def test_ilo_readonly_status_is_unchanged_by_management_flags(monkeypatch) -> None:
    _allow_readonly_ilo_lab(monkeypatch)
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    status = adapter.health()

    assert status.status == "ready"
    assert status.safe_actions[0].enabled is True
    assert status.safe_actions[0].reason == "Run GET-only endpoint detection and Redfish inventory checks."


def test_ilo_config_prefers_active_lab_profile_host(monkeypatch) -> None:
    monkeypatch.setenv("ILO_TEST_HOST", "192.168.1.201")
    create_lab_profile(
        {
            "name": "TDC-LAB",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.200",
                "server_embedded_nic": "10.10.8.201",
                "esxi_management": "10.10.8.202",
                "cisco_management": "10.10.8.203",
                "ansible_control_host": "10.10.8.5",
            },
        }
    )

    config = IloRedfishConfig.from_settings()

    assert config.host == "10.10.8.200"
    assert config.host_source == "active_lab_profile"


def test_ilo_config_includes_saved_first_access_candidate(monkeypatch) -> None:
    monkeypatch.setenv("ILO_TEST_HOST", "192.168.1.201")
    create_lab_profile(
        {
            "name": "TDC-LAB",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.200",
                "server_embedded_nic": "10.10.8.201",
                "esxi_management": "10.10.8.202",
                "cisco_management": "10.10.8.203",
                "ansible_control_host": "10.10.8.5",
            },
        }
    )
    update_control_access_config(
        "ilo",
        {
            "first_time_configuring": True,
            "original_dhcp_ip": "10.10.8.110",
            "username_reference": "local-admin",
            "password_configured": True,
            "password_reference_label": "local secret ref",
        },
    )

    config = IloRedfishConfig.from_settings()

    assert config.host == "10.10.8.200"
    assert config.host_source == "active_lab_profile"
    assert config.fallback_hosts == ("10.10.8.110",)
    assert config.fallback_host_sources == ("control_access_original_dhcp_ip",)
    assert config.target_candidates == [
        {"host": "10.10.8.200", "source": "active_lab_profile"},
        {"host": "10.10.8.110", "source": "control_access_original_dhcp_ip"},
    ]


def test_ilo_setup_apply_blocks_hostname_patch_in_local_readonly(
    db_session,
    monkeypatch,
) -> None:
    fake_settings = types.SimpleNamespace(
        provider_mode="local-readonly",
        ilo_setup_apply_enabled=True,
        lab_apply_ack="YES",
        lab_target_ack="ilo.lab.local",
        ilo_test_host="ilo.lab.local",
        ilo_test_username="local-admin",
        ilo_test_password="local-password",
        ilo_test_verify_tls=False,
        ilo_test_timeout_seconds=3.0,
    )
    monkeypatch.setattr("app.services.ilo_setup_apply.settings", fake_settings)
    monkeypatch.setattr("app.providers.ilo_redfish.settings", fake_settings)
    monkeypatch.setattr(
        "app.services.ilo_setup_apply.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )
    patch_bodies: list[dict[str, object]] = []
    _install_fake_ilo_setup_apply_httpx_client(
        monkeypatch,
        before_hostname="old-ilo-name",
        after_hostname="lab-ilo-host",
        patch_bodies=patch_bodies,
    )
    save_ilo_setup_intent(
        db_session,
        IloSetupIntentWrite(network=IloNetworkIntent(hostname="lab-ilo-host")),
    )

    result = apply_ilo_setup(
        db_session,
        IloSetupApplyCreate(confirmation_phrase=ILO_SETUP_CONFIRMATION_PHRASE),
    )

    assert result["status"] == "blocked"
    assert result["patch_attempted"] is False
    assert result["patch_count"] == 0
    assert patch_bodies == []
    assert any("local-readonly is read-only" in blocker for blocker in result["blockers"])
    assert "lab-ilo-host" not in str(result)


def test_ilo_setup_apply_blocks_ip_changes_and_does_not_patch(
    db_session,
    monkeypatch,
) -> None:
    fake_settings = types.SimpleNamespace(
        provider_mode="local-readonly",
        ilo_setup_apply_enabled=True,
        lab_apply_ack="YES",
        lab_target_ack="ilo.lab.local",
        ilo_test_host="ilo.lab.local",
        ilo_test_username="local-admin",
        ilo_test_password="local-password",
        ilo_test_verify_tls=False,
        ilo_test_timeout_seconds=3.0,
    )
    monkeypatch.setattr("app.services.ilo_setup_apply.settings", fake_settings)
    monkeypatch.setattr("app.providers.ilo_redfish.settings", fake_settings)
    monkeypatch.setattr(
        "app.services.ilo_setup_apply.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )
    patch_bodies: list[dict[str, object]] = []
    _install_fake_ilo_setup_apply_httpx_client(
        monkeypatch,
        before_hostname="old-ilo-name",
        after_hostname="lab-ilo-host",
        patch_bodies=patch_bodies,
    )
    save_ilo_setup_intent(
        db_session,
        IloSetupIntentWrite(
            network=IloNetworkIntent(
                hostname="lab-ilo-host",
                management_ip="192.0.2.25",
            )
        ),
    )

    result = apply_ilo_setup(
        db_session,
        IloSetupApplyCreate(confirmation_phrase=ILO_SETUP_CONFIRMATION_PHRASE),
    )

    assert result["status"] == "blocked"
    assert result["patch_attempted"] is False
    assert patch_bodies == []
    assert any("IP" in blocker for blocker in result["blockers"])


def test_ilo_missing_config_returns_missing_config_blocker() -> None:
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host=None,
            username=None,
            password=None,
            verify_tls=True,
            timeout_seconds=1.0,
        ),
    )

    status = adapter.health()
    probe = adapter.probe()

    assert status.status == "missing-config"
    assert "ILO_TEST_HOST" in status.blockers[0]
    assert probe["status"] == "blocked"
    assert "missing_fields" in probe


def test_ilo_status_exposes_only_configuration_presence() -> None:
    adapter = IloRedfishAdapter(
        provider_mode="mock",
        config=IloRedfishConfig(
            host="ilo-lab-private.example.test",
            username="local-admin",
            password="super-secret-password",
            verify_tls=True,
            timeout_seconds=1.0,
        ),
    )

    status = adapter.health()
    encoded_configuration = json.dumps(status.configuration)

    assert status.configuration["host_configured"] is True
    assert status.configuration["username_configured"] is True
    assert status.configuration["password_configured"] is True
    assert "ilo-lab-private" not in encoded_configuration
    assert "local-admin" not in encoded_configuration
    assert "super-secret-password" not in encoded_configuration


def test_ilo_probe_in_mock_mode_does_not_create_http_client(monkeypatch) -> None:
    def fail_client(**_kwargs):  # noqa: ANN003
        raise AssertionError("mock mode must not create an HTTP client")

    monkeypatch.setattr("app.providers.ilo_redfish.httpx.Client", fail_client)
    adapter = IloRedfishAdapter(
        provider_mode="mock",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()

    assert result["status"] == "blocked"
    assert "local-readonly or PROVIDER_MODE=local-lab-readwrite" in result["message"]


def test_ilo_local_lab_requires_acknowledgement_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.providers.ilo_redfish.current_lab_action_policy",
        lambda provider_mode=None: _lab_action_policy(
            provider_mode or "local-lab-readwrite",
            lab_environment=None,
            acknowledge_real_hardware=False,
            acknowledge_device_reconfiguration=False,
            acknowledge_data_loss_risk=False,
            acknowledge_lab_only=False,
        ),
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-lab-readwrite",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    status = adapter.health()
    result = adapter.probe()

    assert status.status == "blocked"
    assert status.safe_actions[0].enabled is False
    assert result["status"] == "blocked"
    assert any("LAB_ENVIRONMENT=isolated-real-lab" in item for item in result["blockers"])
    assert any("LAB_ACKNOWLEDGE_REAL_HARDWARE=true" in item for item in result["blockers"])
    assert any("LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true" in item for item in result["blockers"])
    assert any("LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true" in item for item in result["blockers"])
    assert any("LAB_ACKNOWLEDGE_LAB_ONLY=true" in item for item in result["blockers"])
    assert "super-secret-password" not in json.dumps(result)


def test_ilo_local_lab_allows_get_only_inventory_and_local_recording(monkeypatch) -> None:
    clear_probe_results()
    requested_urls: list[str] = []
    _allow_local_lab_ilo(monkeypatch)
    _install_fake_httpx_client(
        monkeypatch,
        {
            "/redfish/v1/": (
                200,
                "application/json",
                {
                    "@odata.id": "/redfish/v1/",
                    "Managers": {"@odata.id": "/redfish/v1/Managers/"},
                    "Systems": {"@odata.id": "/redfish/v1/Systems/"},
                    "Chassis": {"@odata.id": "/redfish/v1/Chassis/"},
                },
            ),
            "/redfish/v1": (200, "application/json", {"@odata.id": "/redfish/v1/"}),
            "/": (200, "text/html"),
            "/xmldata?item=All": (404, "text/plain"),
            "/redfish/v1/Managers/": (
                200,
                "application/json",
                {"Members": [{"@odata.id": "/redfish/v1/Managers/1"}]},
            ),
            "/redfish/v1/Managers/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Manager",
                    "Model": "iLO 5",
                    "FirmwareVersion": "3.19",
                },
            ),
            "/redfish/v1/Systems/": (
                200,
                "application/json",
                {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
            ),
            "/redfish/v1/Systems/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Server",
                    "Model": "ProLiant DL360 Gen10",
                    "SerialNumber": "SECRET-SERIAL-123",
                    "BiosVersion": "U32 v2.78",
                    "PowerState": "On",
                    "Status": {"Health": "OK"},
                    "NetworkAdapters": {"@odata.id": "/redfish/v1/Systems/1/NetworkAdapters/"},
                    "Storage": {"@odata.id": "/redfish/v1/Systems/1/Storage/"},
                    "SmartStorage": {"@odata.id": "/redfish/v1/Systems/1/SmartStorage/"},
                },
            ),
            "/redfish/v1/Systems/1/NetworkAdapters/": (
                200,
                "application/json",
                {"Members": [{"@odata.id": "/redfish/v1/Systems/1/NetworkAdapters/1"}]},
            ),
            "/redfish/v1/Systems/1/NetworkAdapters/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Embedded LOM",
                    "Model": "HPE Ethernet 1Gb 4-port 331i Adapter",
                    "Status": {"Health": "OK"},
                },
            ),
            "/redfish/v1/Systems/1/Storage/": (
                200,
                "application/json",
                {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/1"}]},
            ),
            "/redfish/v1/Systems/1/Storage/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Smart Array P408i-a SR Gen10",
                    "Model": "Smart Array P408i-a SR Gen10",
                    "Drives": [
                        {"@odata.id": "/redfish/v1/Systems/1/Storage/1/Drives/1"},
                        {"@odata.id": "/redfish/v1/Systems/1/Storage/1/Drives/2"},
                    ],
                    "Volumes": {"@odata.id": "/redfish/v1/Systems/1/Storage/1/Volumes/"},
                },
            ),
            "/redfish/v1/Systems/1/Storage/1/Drives/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Drive Bay 1",
                    "Bay": 1,
                    "CapacityBytes": 480103981056,
                    "MediaType": "SSD",
                    "Status": {"Health": "OK"},
                },
            ),
            "/redfish/v1/Systems/1/Storage/1/Drives/2": (
                200,
                "application/json",
                {
                    "Id": "2",
                    "Name": "Drive Bay 2",
                    "Bay": 2,
                    "CapacityBytes": 480103981056,
                    "MediaType": "SSD",
                    "Status": {"Health": "OK"},
                },
            ),
            "/redfish/v1/Systems/1/Storage/1/Volumes/": (
                200,
                "application/json",
                {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/1/Volumes/1"}]},
            ),
            "/redfish/v1/Systems/1/Storage/1/Volumes/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Logical Drive 1",
                    "RAIDType": "RAID1",
                    "CapacityBytes": 480103981056,
                    "Status": {"Health": "OK"},
                },
            ),
            "/redfish/v1/Systems/1/SmartStorage/": (
                200,
                "application/json",
                {"Members": []},
            ),
            "/redfish/v1/Chassis/": (
                200,
                "application/json",
                {"Members": [{"@odata.id": "/redfish/v1/Chassis/1"}]},
            ),
            "/redfish/v1/Chassis/1": (
                200,
                "application/json",
                {"Id": "1", "Name": "Chassis"},
            ),
        },
        requested_urls=requested_urls,
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-lab-readwrite",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()
    encoded = json.dumps(result)

    assert result["status"] == "ok"
    assert result["action_policy"]["provider_mode"] == "local-lab-readwrite"
    assert result["action_policy"]["local_state_write"] == "allowed"
    assert result["action_policy"]["device_writes"] == "policy-gated"
    assert result["endpoint_detection"]["classification"] == "redfish_available"
    assert result["systems"][0]["Model"] == "ProLiant DL360 Gen10"
    assert result["systems"][0]["serial_number_present"] is True
    assert result["systems"][0]["BiosVersion"] == "U32 v2.78"
    assert result["managers"][0]["Model"] == "iLO 5"
    assert result["managers"][0]["FirmwareVersion"] == "3.19"
    assert result["network_adapters"][0]["Model"] == "HPE Ethernet 1Gb 4-port 331i Adapter"
    assert result["network_adapters"][0]["mac_address_present"] is False
    assert result["storage"]["status"] == "available"
    assert result["storage"]["controllers"][0]["Model"] == "Smart Array P408i-a SR Gen10"
    assert result["storage"]["physical_drives"][0]["Bay"] == 1
    assert result["storage"]["physical_drives"][0]["MediaType"] == "SSD"
    assert result["storage"]["logical_drives"][0]["RAIDType"] == "RAID1"
    assert requested_urls
    assert all(url.startswith("https://192.0.2.202/") for url in requested_urls)
    assert all("/redfish/" in url or url.endswith("/") or "xmldata" in url for url in requested_urls)
    assert "192.0.2.202" not in encoded
    assert "local-admin" not in encoded
    assert "super-secret-password" not in encoded
    assert "SECRET-SERIAL-123" not in encoded


def test_ilo_probe_tries_first_access_candidate_after_primary_network_failure(monkeypatch) -> None:
    import httpx

    _allow_readonly_ilo_lab(monkeypatch)
    requested_urls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            pass

        def get(self, url: str) -> httpx.Response:
            requested_urls.append(url)
            request = httpx.Request("GET", url)
            if "10.10.8.200" in url:
                raise httpx.ConnectError("network unreachable", request=request)
            path = "/" + url.split("/", 3)[3] if "/" in url.split("://", 1)[-1] else "/"
            payload = {"@odata.id": "/redfish/v1/"} if path in {"/redfish/v1/", "/redfish/v1"} else {}
            status_code = 200 if path in {"/redfish/v1/", "/redfish/v1"} else 404
            return httpx.Response(
                status_code,
                headers={"content-type": "application/json"},
                content=json.dumps(payload).encode("utf-8"),
                request=request,
            )

    monkeypatch.setattr("app.providers.ilo_redfish.httpx.Client", FakeClient)
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="10.10.8.200",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
            host_source="active_lab_profile",
            fallback_hosts=("10.10.8.110",),
            fallback_host_sources=("control_access_original_dhcp_ip",),
        ),
    )

    result = adapter.probe()
    encoded = json.dumps(result)

    assert result["status"] == "ok"
    assert result["target_source"] == "control_access_original_dhcp_ip"
    assert result["candidate_attempts"][0]["target_source"] == "active_lab_profile"
    assert result["candidate_attempts"][0]["classification"] == "network_unreachable"
    assert result["candidate_attempts"][1]["target_source"] == "control_access_original_dhcp_ip"
    assert any("10.10.8.200" in url for url in requested_urls)
    assert any("10.10.8.110" in url for url in requested_urls)
    assert "10.10.8.200" not in encoded
    assert "10.10.8.110" not in encoded
    assert "super-secret-password" not in encoded


def test_ilo_local_lab_dangerous_actions_remain_blocked(monkeypatch) -> None:
    _allow_local_lab_ilo(monkeypatch)
    adapter = IloRedfishAdapter(
        provider_mode="local-lab-readwrite",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    status = adapter.health()
    disabled_actions = {action.id: action for action in status.disabled_actions}

    assert status.status == "ready"
    assert status.safe_actions[0].enabled is True
    assert {
        "ilo-power-action",
        "ilo-firmware-update",
        "ilo-virtual-media",
        "ilo-boot-order-change",
        "ilo-bios-change",
        "ilo-user-change",
        "ilo-network-change",
        "ilo-factory-reset",
    }.issubset(disabled_actions)
    assert all(not action.enabled for action in disabled_actions.values())
    assert "LAB_ALLOW_POWER_ACTIONS=true" in disabled_actions["ilo-power-action"].reason
    assert "LAB_ALLOW_FIRMWARE_UPDATES=true" in disabled_actions["ilo-firmware-update"].reason
    assert "LAB_ALLOW_FACTORY_RESET=true" in disabled_actions["ilo-factory-reset"].reason


def test_ilo_setup_apply_allows_hostname_patch_in_local_lab_readwrite(
    db_session,
    monkeypatch,
) -> None:
    fake_settings = types.SimpleNamespace(
        provider_mode="local-lab-readwrite",
        ilo_setup_apply_enabled=True,
        lab_apply_ack="YES",
        lab_target_ack="ilo.lab.local",
        ilo_test_host="ilo.lab.local",
        ilo_test_username="local-admin",
        ilo_test_password="local-password",
        ilo_test_verify_tls=False,
        ilo_test_timeout_seconds=3.0,
    )
    monkeypatch.setattr("app.services.ilo_setup_apply.settings", fake_settings)
    monkeypatch.setattr("app.providers.ilo_redfish.settings", fake_settings)
    monkeypatch.setattr(
        "app.services.ilo_setup_apply.current_lab_action_policy",
        lambda provider_mode=None: _lab_action_policy(provider_mode or "local-lab-readwrite"),
    )
    patch_bodies: list[dict[str, object]] = []
    _install_fake_ilo_setup_apply_httpx_client(
        monkeypatch,
        before_hostname="old-ilo-name",
        after_hostname="lab-ilo-host",
        patch_bodies=patch_bodies,
    )
    save_ilo_setup_intent(
        db_session,
        IloSetupIntentWrite(network=IloNetworkIntent(hostname="lab-ilo-host")),
    )

    result = apply_ilo_setup(
        db_session,
        IloSetupApplyCreate(confirmation_phrase=ILO_SETUP_CONFIRMATION_PHRASE),
    )

    assert result["status"] == "ok"
    assert result["patch_attempted"] is True
    assert patch_bodies == [{"HostName": "lab-ilo-host"}]
    assert result["blockers"] == []
    assert "lab-ilo-host" not in str(result)


def test_local_lab_readwrite_allows_allowlisted_lab_action_categories() -> None:
    policy = _lab_action_policy("local-lab-readwrite")

    assert policy.action_allowed("ilo-redfish.record-readonly-inventory", ActionCategory.APP_STATE_WRITE)
    assert policy.action_allowed(
        "ilo-redfish.manager-network-protocol-hostname",
        ActionCategory.NETWORK_CONFIG,
    )
    assert policy.action_allowed("netapp.svm-lif-iscsi", ActionCategory.STORAGE_CONFIG)
    assert policy.action_allowed("ilo.bios-settings", ActionCategory.BIOS_CONFIG)
    assert policy.action_allowed("ilo.boot-settings", ActionCategory.BOOT_CONFIG)
    assert policy.action_allowed("ilo.virtual-media", ActionCategory.VIRTUAL_MEDIA)
    assert policy.action_allowed("esxi.install-config", ActionCategory.OS_INSTALL)
    assert policy.action_allowed("vm.deploy-ovf", ActionCategory.VM_DEPLOY)


def test_local_lab_readwrite_blocks_unrepresented_actions() -> None:
    policy = _lab_action_policy("local-lab-readwrite")

    blockers = policy.action_blockers("shell.freeform-command", ActionCategory.NETWORK_CONFIG)

    assert any("explicit allowlisted workflow step" in blocker for blocker in blockers)


def test_firmware_and_factory_reset_require_explicit_flags() -> None:
    policy = _lab_action_policy("local-lab-readwrite")

    assert any(
        "LAB_ALLOW_FIRMWARE_UPDATES=true" in blocker
        for blocker in policy.action_blockers("ilo.firmware-update", ActionCategory.FIRMWARE_UPDATE)
    )
    assert any(
        "LAB_ALLOW_FACTORY_RESET=true" in blocker
        for blocker in policy.action_blockers("lab.factory-reset", ActionCategory.FACTORY_RESET)
    )

    enabled_policy = _lab_action_policy(
        "local-lab-readwrite",
        allow_firmware_updates=True,
        allow_factory_reset=True,
    )
    assert enabled_policy.action_allowed("ilo.firmware-update", ActionCategory.FIRMWARE_UPDATE)
    assert enabled_policy.action_allowed("lab.factory-reset", ActionCategory.FACTORY_RESET)


def test_ilo_probe_classifies_web_available_redfish_not_found(monkeypatch) -> None:
    _allow_readonly_ilo_lab(monkeypatch)
    _install_fake_httpx_client(
        monkeypatch,
        {
            "/redfish/v1/": (404, "text/plain; charset=utf-8"),
            "/redfish/v1": (404, "text/plain; charset=utf-8"),
            "/": (200, "text/html"),
            "/xmldata?item=All": (404, "text/plain; charset=utf-8"),
        },
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()

    assert result["status"] == "failed"
    detection = result["endpoint_detection"]
    assert detection["classification"] == "web_available_redfish_not_found"
    assert detection["redfish_status"] == "not_found"
    assert detection["web_status"] == "available"
    assert detection["legacy_status"] == "not_found"
    assert "The web root responded, but Redfish root was not found." in result["message"]
    assert "HTTP web reachability alone does not prove" in result["message"]
    assert "legacy iLO generation" in result["message"]
    assert "unrelated web server" in result["message"]
    assert "No settings were changed." in detection["next_safe_action"]
    assert all(token not in detection["next_safe_action"].lower() for token in ("apply", "write"))
    assert detection["diagnostic_hints"] == [
        "Wrong IP: the responding web server may be a server OS, proxy, or another device.",
        "Legacy iLO: older generations may not expose Redfish at /redfish/v1.",
        "Redfish unavailable: the management UI may be reachable while the API is disabled or unsupported.",
        "Non-iLO web server: the root page responds, but iLO-specific probes did not.",
        "Keep using GET-only endpoint detection until target identity and Redfish support are confirmed.",
    ]
    matrix = {check["path"]: check for check in detection["checks"]}
    assert matrix["/redfish/v1/"]["status_code"] == 404
    assert matrix["/redfish/v1"]["status_code"] == 404
    assert matrix["/"]["status_code"] == 200
    assert matrix["/"]["content_type"] == "text/html"
    assert matrix["/xmldata?item=All"]["status_code"] == 404
    assert all("super-secret-password" not in json.dumps(check) for check in detection["checks"])


def test_ilo_probe_classifies_legacy_available_redfish_not_found(monkeypatch) -> None:
    _allow_readonly_ilo_lab(monkeypatch)
    _install_fake_httpx_client(
        monkeypatch,
        {
            "/redfish/v1/": (404, "text/plain"),
            "/redfish/v1": (404, "text/plain"),
            "/": (404, "text/plain"),
            "/xmldata?item=All": (
                200,
                "text/xml",
                (
                    b"<RIMP><HSI><SPN>ProLiant DL360 Gen10</SPN>"
                    b"<SBSN>SECRET-SERIAL-123</SBSN></HSI>"
                    b"<MP><PN>Integrated Lights-Out 5</PN><FWRI>2.80</FWRI></MP></RIMP>"
                ),
            ),
        },
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()

    assert result["status"] == "failed"
    assert result["endpoint_detection"]["classification"] == "legacy_available_redfish_not_found"
    assert result["endpoint_detection"]["legacy_status"] == "available"
    assert result["message"] == "Legacy iLO endpoint is available, but Redfish root was not found."


def test_ilo_probe_classifies_redfish_auth_failed(monkeypatch) -> None:
    _allow_readonly_ilo_lab(monkeypatch)
    _install_fake_httpx_client(
        monkeypatch,
        {
            "/redfish/v1/": (401, "application/json"),
            "/redfish/v1": (401, "application/json"),
            "/": (200, "text/html"),
            "/xmldata?item=All": (401, "text/plain"),
        },
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()

    assert result["status"] == "failed"
    assert result["endpoint_detection"]["classification"] == "auth_failed"
    assert "credentials" in result["message"].lower()
    assert "super-secret-password" not in json.dumps(result)


def test_ilo_probe_classifies_inventory_auth_after_root_available(monkeypatch) -> None:
    _allow_readonly_ilo_lab(monkeypatch)
    _install_fake_httpx_client(
        monkeypatch,
        {
            "/redfish/v1/": (
                200,
                "application/json",
                {
                    "@odata.id": "/redfish/v1/",
                    "Managers": {"@odata.id": "/redfish/v1/Managers/"},
                    "Systems": {"@odata.id": "/redfish/v1/Systems/"},
                    "Chassis": {"@odata.id": "/redfish/v1/Chassis/"},
                    "UpdateService": {"@odata.id": "/redfish/v1/UpdateService/"},
                },
            ),
            "/redfish/v1": (200, "application/json", {"@odata.id": "/redfish/v1/"}),
            "/": (200, "text/html"),
            "/xmldata?item=All": (
                200,
                "text/xml",
                (
                    b"<RIMP><HSI><SPN>ProLiant DL360 Gen10</SPN>"
                    b"<SBSN>SECRET-SERIAL-123</SBSN></HSI>"
                    b"<MP><PN>Integrated Lights-Out 5</PN><FWRI>2.80</FWRI></MP></RIMP>"
                ),
            ),
            "/redfish/v1/Managers/": (401, "application/json"),
            "/redfish/v1/Systems/": (401, "application/json"),
            "/redfish/v1/Chassis/": (401, "application/json"),
            "/redfish/v1/UpdateService/": (401, "application/json"),
        },
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="192.0.2.202",
            username="local-admin",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()

    assert result["status"] == "failed"
    detection = result["endpoint_detection"]
    assert detection["classification"] == "redfish_inventory_auth_failed"
    assert detection["redfish_status"] == "available"
    assert detection["legacy_status"] == "available"
    assert detection["web_status"] == "available"
    assert result["legacy_identity"] == {
        "source": "/xmldata?item=All",
        "serial_present": True,
        "model": "ProLiant DL360 Gen10",
        "current_firmware": "2.80",
        "ilo_generation": "ilo5",
        "management_product": "Integrated Lights-Out 5",
    }
    assert detection["checks"][0]["classification"] == "redfish_root_available"
    assert detection["inventory_collection_status"] == "unauthorized"
    assert detection["inventory_collection_classification"] == "redfish_collection_unauthorized"
    assert {
        check["name"]: (check["path"], check["status_code"], check["classification"])
        for check in detection["inventory_collection_checks"]
    } == {
        "Managers": (
            "/redfish/v1/Managers/",
            401,
            "redfish_collection_unauthorized",
        ),
        "Systems": (
            "/redfish/v1/Systems/",
            401,
            "redfish_collection_unauthorized",
        ),
        "Chassis": (
            "/redfish/v1/Chassis/",
            401,
            "redfish_collection_unauthorized",
        ),
        "UpdateService": (
            "/redfish/v1/UpdateService/",
            401,
            "redfish_collection_unauthorized",
        ),
    }
    assert detection["auth_failure_classification"] == "basic_auth_rejected_or_insufficient_privilege"
    assert detection["auth_recovery_hint"] == "session_auth_may_be_required"
    assert detection["next_safe_action"] == (
        "Review iLO account permissions or Redfish authentication method. No settings were changed."
    )
    assert "inventory discovery cannot continue" in result["message"].lower()
    assert "Inventory discovery can continue" not in result["message"]
    assert all("super-secret-password" not in json.dumps(check) for check in detection["checks"])
    assert "SECRET-SERIAL-123" not in json.dumps(result)


def test_ilo_probe_for_lab_target_192_168_1_202_is_get_only_and_redacted(monkeypatch) -> None:
    clear_probe_results()
    requested_urls: list[str] = []
    _allow_readonly_ilo_lab(monkeypatch)
    _install_fake_httpx_client(
        monkeypatch,
        {
            "/redfish/v1/": (
                200,
                "application/json",
                {
                    "@odata.id": "/redfish/v1/",
                    "Managers": {"@odata.id": "/redfish/v1/Managers/"},
                    "Systems": {"@odata.id": "/redfish/v1/Systems/"},
                    "Chassis": {"@odata.id": "/redfish/v1/Chassis/"},
                },
            ),
            "/redfish/v1": (200, "application/json", {"@odata.id": "/redfish/v1/"}),
            "/": (200, "text/html"),
            "/xmldata?item=All": (404, "text/plain"),
            "/redfish/v1/Managers/": (
                200,
                "application/json",
                {
                    "Members": [
                        {"@odata.id": "/redfish/v1/Managers/1"},
                    ]
                },
            ),
            "/redfish/v1/Managers/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Manager",
                    "ManagerType": "BMC",
                    "FirmwareVersion": "2.80",
                    "Model": "iLO 5",
                },
            ),
            "/redfish/v1/Systems/": (
                200,
                "application/json",
                {
                    "Members": [
                        {"@odata.id": "/redfish/v1/Systems/1"},
                    ]
                },
            ),
            "/redfish/v1/Systems/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Server",
                    "Model": "ProLiant DL360 Gen10",
                    "PowerState": "On",
                },
            ),
            "/redfish/v1/Chassis/": (
                200,
                "application/json",
                {
                    "Members": [
                        {"@odata.id": "/redfish/v1/Chassis/1"},
                    ]
                },
            ),
            "/redfish/v1/Chassis/1": (
                200,
                "application/json",
                {
                    "Id": "1",
                    "Name": "Chassis",
                    "ChassisType": "RackMount",
                    "Power": {"@odata.id": "/redfish/v1/Chassis/1/Power"},
                    "Thermal": {"@odata.id": "/redfish/v1/Chassis/1/Thermal"},
                },
            ),
            "/redfish/v1/Chassis/1/Power": (200, "application/json", {"Id": "Power"}),
            "/redfish/v1/Chassis/1/Thermal": (200, "application/json", {"Id": "Thermal"}),
        },
        requested_urls=requested_urls,
    )
    adapter = IloRedfishAdapter(
        provider_mode="local-readonly",
        config=IloRedfishConfig(
            host="192.168.1.201",
            username="Administrator",
            password="super-secret-password",
            verify_tls=False,
            timeout_seconds=1.0,
        ),
    )

    result = adapter.probe()
    encoded = json.dumps(result)

    assert result["status"] == "ok"
    assert result["base_url"] == "https://REDACTED"
    assert result["tls_verify"] is False
    assert result["endpoint_detection"]["classification"] == "redfish_available"
    assert requested_urls
    assert all(url.startswith("https://192.168.1.201/") for url in requested_urls)
    assert {request["path"] for request in result["requests"]}.issuperset(
        {"/redfish/v1/", "/redfish/v1", "/", "/xmldata?item=All"}
    )
    assert "192.168.1.201" not in encoded
    assert "Administrator" not in encoded
    assert "super-secret-password" not in encoded


def test_ilo_redacts_secrets() -> None:
    secret = "super-secret-password"
    host = "ilo-lab-private.example.test"
    username = "local-admin"
    redacted = redact_sensitive(
        {
            "password": secret,
            "message": f"request failed for {username}@{host} with password={secret}",
            "nested": {"token": "abc123"},
        },
        [secret, host, username],
    )

    encoded = json.dumps(redacted)
    assert secret not in encoded
    assert host not in encoded
    assert username not in encoded
    assert "abc123" not in encoded
    assert encoded.count("REDACTED") >= 3


def test_redaction_masks_hardware_identity_fields() -> None:
    redacted = redact_sensitive(
        {
            "Oem": {
                "Hpe": {
                    "FQDN": "private-ilo.example.test",
                    "HostName": "private-ilo",
                }
            },
            "UUID": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "SerialNumber": "SERIAL123",
            "MACAddress": "00:11:22:33:44:55",
            "serial_number_present": True,
            "mac_address_present": True,
        }
    )

    encoded = json.dumps(redacted)
    assert "private-ilo" not in encoded
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" not in encoded
    assert "SERIAL123" not in encoded
    assert "00:11:22:33:44:55" not in encoded
    assert redacted["serial_number_present"] is True
    assert redacted["mac_address_present"] is True


def test_redaction_does_not_corrupt_classification_when_username_is_short() -> None:
    redacted = redact_sensitive(
        {
            "classification": "redfish_root_available",
            "message": "root login failed for root@example.test",
        },
        ["root"],
    )

    assert redacted["classification"] == "redfish_root_available"
    assert redacted["message"] == "REDACTED login failed for REDACTED@example.test"


def test_redaction_keeps_cisco_privilege_evidence_without_secret_values() -> None:
    secret = "super-secret-password"
    redacted = redact_sensitive(
        {
            "password": secret,
            "password_prompt_seen": True,
            "enable_password_sources_configured": {
                "CISCO_ENABLE_PASSWORD": True,
                "ANSIBLE_CISCO_ENABLE_PASSWORD": False,
            },
            "enable_password_sources_tried": [["CISCO_ENABLE_PASSWORD"]],
            "message": f"enable password={secret} rejected",
        },
        [secret],
    )

    encoded = json.dumps(redacted)
    assert redacted["password"] == "REDACTED"
    assert redacted["password_prompt_seen"] is True
    assert redacted["enable_password_sources_configured"]["CISCO_ENABLE_PASSWORD"] is True
    assert redacted["enable_password_sources_tried"] == [["CISCO_ENABLE_PASSWORD"]]
    assert "CISCO_ENABLE_PASSWORD" in encoded
    assert secret not in encoded


def test_esxi_status_exposes_only_configuration_presence() -> None:
    adapter = EsxiReadonlyAdapter(
        provider_mode="mock",
        config=EsxiReadonlyConfig(
            host="esxi-lab-private.example.test",
            username="root",
            password="super-secret-password",
            verify_tls=True,
            timeout_seconds=1.0,
            ssh_timeout_seconds=1.0,
        ),
    )

    status = adapter.health()
    encoded_configuration = json.dumps(status.configuration)

    assert status.configuration["host_configured"] is True
    assert status.configuration["username_configured"] is True
    assert status.configuration["password_configured"] is True
    assert "esxi-lab-private" not in encoded_configuration
    assert "root" not in encoded_configuration
    assert "super-secret-password" not in encoded_configuration


def test_cisco_ansible_status_exposes_only_configuration_presence() -> None:
    adapter = CiscoAnsibleAdapter(
        provider_mode="mock",
        config=CiscoAnsibleConfig(
            host="192.0.2.10",
            username="switch-admin",
            password="super-secret-password",
            enable_password="enable-secret",
            network_os="cisco.ios.ios",
            connection="ansible.netcommon.network_cli",
            timeout_seconds=1.0,
        ),
    )

    status = adapter.health()
    encoded_configuration = json.dumps(status.configuration)

    assert status.configuration["host_configured"] is True
    assert status.configuration["username_configured"] is True
    assert status.configuration["password_configured"] is True
    assert "192.0.2.10" not in encoded_configuration
    assert "switch-admin" not in encoded_configuration
    assert "super-secret-password" not in encoded_configuration
    assert "enable-secret" not in encoded_configuration


def test_dangerous_actions_are_not_exposed_as_runnable() -> None:
    statuses = provider_registry("mock").statuses()

    assert statuses
    for status in statuses:
        assert all(action.read_only for action in status.safe_actions)
        assert all(not action.enabled for action in status.disabled_actions)
        assert all(not action.read_only for action in status.disabled_actions)


def test_local_readonly_status_does_not_run_probes(monkeypatch) -> None:
    clear_probe_results()

    def fail_probe(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("provider status must not run probes")

    monkeypatch.setattr(IloRedfishAdapter, "probe", fail_probe)
    statuses = provider_registry("local-readonly").statuses()

    assert {status.mode for status in statuses} == {"local-readonly"}
    assert all(status.last_probe_result is None for status in statuses)


def test_provider_status_response_shape(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    provider_ids = {provider["id"] for provider in payload}
    assert {
        "ilo-redfish",
        "cisco-console",
        "cisco-ansible",
        "esxi-readonly",
        "netapp-ontap",
        "mock-vsphere",
    }.issubset(provider_ids)
    for provider in payload:
        assert isinstance(provider["configuration"], dict)
        assert isinstance(provider["blockers"], list)
        assert isinstance(provider["warnings"], list)
        assert isinstance(provider["safe_actions"], list)
        assert isinstance(provider["disabled_actions"], list)
        assert all(not action["enabled"] for action in provider["disabled_actions"])


def test_new_provider_probe_endpoints_are_explicit_and_blocked_in_mock_mode(
    client: TestClient,
) -> None:
    for provider_id in ("cisco-ansible", "esxi-readonly"):
        response = client.post(f"/api/v1/providers/{provider_id}/probe")

        assert response.status_code == 200
        payload = response.json()
        assert payload["provider_id"] == provider_id
        assert payload["status"] == "blocked"
        assert "local-readonly" in payload["message"]


def _console_paths(tmp_path: Path) -> dict[str, Path]:
    dev = tmp_path / "dev"
    by_id = dev / "serial" / "by-id"
    by_id.mkdir(parents=True)
    return {"dev": dev, "by_id": by_id}


def _discovery_paths(paths: dict[str, Path]) -> ConsoleDiscoveryPaths:
    dev = paths["dev"]
    by_id = paths["by_id"]
    return ConsoleDiscoveryPaths(
        stable_glob=str(by_id / "*"),
        usb_glob=str(dev / "ttyUSB*"),
        acm_glob=str(dev / "ttyACM*"),
        ttys_glob=str(dev / "ttyS*"),
    )


def _allow_readonly_lab(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.providers.cisco_console.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
    )


def _allow_readonly_ilo_lab(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.providers.ilo_redfish.current_lab_action_policy",
        lambda provider_mode=None: _lab_action_policy(provider_mode or "local-readonly"),
    )


def _allow_local_lab_ilo(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.providers.ilo_redfish.current_lab_action_policy",
        lambda provider_mode=None: _lab_action_policy(provider_mode or "local-lab-readwrite"),
    )


def _lab_action_policy(
    provider_mode: str,
    *,
    lab_environment: str | None = "isolated-real-lab",
    acknowledge_real_hardware: bool = True,
    acknowledge_device_reconfiguration: bool = True,
    acknowledge_data_loss_risk: bool = True,
    acknowledge_lab_only: bool = True,
    allow_power_actions: bool = False,
    allow_firmware_updates: bool = False,
    allow_factory_reset: bool = False,
    legacy_closed_loop_ack: bool = True,
    legacy_readonly_ack: bool = True,
    legacy_destructive_ack: bool = False,
) -> LabActionPolicy:
    return LabActionPolicy(
        provider_mode=provider_mode,
        lab_environment=lab_environment,
        acknowledge_real_hardware=acknowledge_real_hardware,
        acknowledge_device_reconfiguration=acknowledge_device_reconfiguration,
        acknowledge_data_loss_risk=acknowledge_data_loss_risk,
        acknowledge_lab_only=acknowledge_lab_only,
        allow_power_actions=allow_power_actions,
        allow_firmware_updates=allow_firmware_updates,
        allow_factory_reset=allow_factory_reset,
        legacy_closed_loop_ack=legacy_closed_loop_ack,
        legacy_readonly_ack=legacy_readonly_ack,
        legacy_destructive_ack=legacy_destructive_ack,
    )


def _install_fake_httpx_client(
    monkeypatch,
    responses: dict[
        str,
        tuple[int, str] | tuple[int, str, dict[str, object] | bytes],
    ],
    *,
    requested_urls: list[str] | None = None,
) -> None:
    import httpx
    import json as json_module

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            pass

        def get(self, url: str) -> httpx.Response:
            if requested_urls is not None:
                requested_urls.append(url)
            path = "/" + url.split("/", 3)[3] if "/" in url.split("://", 1)[-1] else "/"
            response_spec = responses.get(path, (404, "text/plain"))
            status_code, content_type = response_spec[:2]
            if len(response_spec) == 3:
                payload = response_spec[2]
                content = (
                    payload
                    if isinstance(payload, bytes)
                    else json_module.dumps(payload).encode("utf-8")
                )
            else:
                content = b'{"@odata.id": "/redfish/v1/"}' if content_type == "application/json" else b""
            request = httpx.Request("GET", url)
            return httpx.Response(
                status_code,
                headers={"content-type": content_type},
                content=content,
                request=request,
            )

    monkeypatch.setattr("app.providers.ilo_redfish.httpx.Client", FakeClient)


def _install_fake_ilo_setup_apply_httpx_client(
    monkeypatch,
    *,
    before_hostname: str,
    after_hostname: str,
    patch_bodies: list[dict[str, object]],
) -> None:
    import httpx
    import json as json_module

    state = {"hostname": before_hostname}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_args) -> None:
            pass

        def get(self, url: str) -> httpx.Response:
            path = "/" + url.split("/", 3)[3] if "/" in url.split("://", 1)[-1] else "/"
            payloads = {
                "/redfish/v1/": {"Managers": {"@odata.id": "/redfish/v1/Managers/"}},
                "/redfish/v1/Managers/": {
                    "Members": [{"@odata.id": "/redfish/v1/Managers/1"}]
                },
                "/redfish/v1/Managers/1": {
                    "NetworkProtocol": {
                        "@odata.id": "/redfish/v1/Managers/1/NetworkProtocol"
                    }
                },
                "/redfish/v1/Managers/1/NetworkProtocol": {
                    "HostName": state["hostname"]
                },
            }
            request = httpx.Request("GET", url)
            return httpx.Response(
                200 if path in payloads else 404,
                headers={"content-type": "application/json"},
                content=json_module.dumps(payloads.get(path, {})).encode("utf-8"),
                request=request,
            )

        def patch(self, url: str, json: dict[str, object]) -> httpx.Response:
            patch_bodies.append(json)
            state["hostname"] = after_hostname
            request = httpx.Request("PATCH", url)
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=b"{}",
                request=request,
            )

    monkeypatch.setattr("app.services.ilo_setup_apply.httpx.Client", FakeClient)


def _install_fake_serial(monkeypatch, outputs: list[str]) -> None:
    monkeypatch.setattr("app.providers.cisco_console.time.sleep", lambda _seconds: None)

    class FakeSerialConnection:
        def __init__(self) -> None:
            self.outputs = [output.encode("utf-8") for output in outputs]
            self.writes: list[bytes] = []

        def __enter__(self) -> "FakeSerialConnection":
            return self

        def __exit__(self, *_args) -> None:  # noqa: ANN002
            return None

        @property
        def in_waiting(self) -> int:
            return 0

        def write(self, value: bytes) -> int:
            self.writes.append(value)
            return len(value)

        def read(self, _size: int) -> bytes:
            return self.outputs.pop(0) if self.outputs else b""

    fake_serial = types.SimpleNamespace(Serial=lambda **_kwargs: FakeSerialConnection())
    monkeypatch.setitem(sys.modules, "serial", fake_serial)


def _install_tracking_fake_serial(monkeypatch, outputs: list[str]) -> list[bytes]:
    monkeypatch.setattr("app.providers.cisco_console.time.sleep", lambda _seconds: None)
    writes: list[bytes] = []

    class FakeSerialConnection:
        def __init__(self) -> None:
            self.outputs = [output.encode("utf-8") for output in outputs]

        def __enter__(self) -> "FakeSerialConnection":
            return self

        def __exit__(self, *_args) -> None:  # noqa: ANN002
            return None

        @property
        def in_waiting(self) -> int:
            return 0

        def write(self, value: bytes) -> int:
            writes.append(value)
            return len(value)

        def read(self, _size: int) -> bytes:
            return self.outputs.pop(0) if self.outputs else b""

    fake_serial = types.SimpleNamespace(Serial=lambda **_kwargs: FakeSerialConnection())
    monkeypatch.setitem(sys.modules, "serial", fake_serial)
    return writes


def _run_prompt_readiness_with_fake_serial(
    tmp_path: Path,
    monkeypatch,
    prompt_output: str,
) -> tuple[dict, list[bytes]]:
    clear_probe_results()
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    writes = _install_tracking_fake_serial(monkeypatch, [prompt_output])

    result = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
        paths=_discovery_paths(paths),
    ).prompt_readiness()
    return result, writes


def _run_prompt_readiness_with_serial_open_error(
    tmp_path: Path,
    monkeypatch,
    error: BaseException,
) -> dict:
    clear_probe_results()
    paths = _console_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    monkeypatch.setattr("app.providers.cisco_console.time.sleep", lambda _seconds: None)

    def fail_serial(**_kwargs):
        raise error

    monkeypatch.setitem(sys.modules, "serial", types.SimpleNamespace(Serial=fail_serial))
    return CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
        paths=_discovery_paths(paths),
    ).prompt_readiness()


def _record_prompt_readiness(
    prompt_state: str,
    *,
    prompt_sample: dict[str, object] | None = None,
) -> None:
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "action": "prompt-readiness",
            "status": "ok" if prompt_state == "exec" else "blocked",
            "message": "prompt readiness test fixture",
            "prompt_state": prompt_state,
            "prompt_sample": prompt_sample or {"captured": True},
            "safe_show_commands_allowed": False,
            "future_show_command_check_eligible": prompt_state == "exec",
            "prompt_classification": {
                "state": prompt_state,
                "label": prompt_state,
                "summary": "test fixture",
                "no_output_captured": (
                    prompt_state == "unknown"
                    and bool(prompt_sample)
                    and prompt_sample.get("captured") is False
                ),
                "raw_text_redacted": True,
                "safe_show_commands_allowed": False,
                "next_safe_action": "test fixture",
            },
            "warnings": [],
            "blockers": [],
        },
    )


def _mock_ready_console(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.cisco_console_bootstrap.CiscoConsoleAdapter.health",
        lambda _self: ProviderStatus(
            id="cisco-console",
            name="Cisco Console",
            kind="network-console",
            mode="local-readonly",
            status="ready",
            capabilities=[],
            message="ready",
            discovery={"effective_path": "/dev/serial/by-id/mock-cisco-console"},
            blockers=[],
            warnings=[],
        ),
    )


def _load_provider_smoke_module() -> types.ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "provider_smoke.py"
    spec = importlib.util.spec_from_file_location("provider_smoke_under_test", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_hpe_raid_plan_module() -> types.ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "hpe_raid_plan.py"
    spec = importlib.util.spec_from_file_location("hpe_raid_plan_under_test", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _valid_bootstrap_payload() -> dict[str, object]:
    return {
        "planned_management_ip": "192.168.1.204",
        "subnet_prefix": "/24",
        "gateway": "192.168.1.1",
        "management_vlan": "8",
        "management_interface": "Vlan8",
        "management_strategy": "SVI management interface",
        "hostname": "cisco-lab-01",
        "domain_name": "lab.example.test",
        "dns_servers": ["192.168.1.1"],
        "local_admin_username_configured": True,
        "local_admin_username_reference": "local-env:CISCO_TEST_USERNAME",
        "operator_notes": "Preview only. No secrets.",
    }
