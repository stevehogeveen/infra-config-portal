from __future__ import annotations

import builtins
import importlib.util
import json
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient

from app.providers.base import ProviderAction, ProviderStatus
from app.providers.cisco_console import (
    CiscoConsoleAdapter,
    CiscoConsoleConfig,
    ConsoleDiscoveryPaths,
    _prompt_blocker_message,
    _prompt_state,
    discover_cisco_console,
)
from app.providers.cisco_ansible import CiscoAnsibleAdapter, CiscoAnsibleConfig, _run_command
from app.providers.esxi_readonly import EsxiReadonlyAdapter, EsxiReadonlyConfig
from app.providers.ilo_redfish import IloRedfishAdapter, IloRedfishConfig
from app.providers.lab_safety import LabSafetyState
from app.providers.probe_cache import clear_probe_results
from app.providers.redaction import redact_sensitive
from app.providers.registry import provider_registry
from app.services.cisco_setup_readiness import get_cisco_setup_readiness


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
    assert discovery["selection_source"] == "single-stable-candidate"
    assert discovery["candidate_counts"]["stable_existing"] == 1
    stable_candidates = [
        candidate for candidate in discovery["candidates"] if candidate["stable_path"]
    ]
    assert stable_candidates[0]["recommendation"] == "recommended-default"


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

    assert discovery["status"] == "needs-selection"
    assert discovery["recommended_path"] is None
    assert discovery["effective_path"] is None
    assert discovery["selection_source"] == "multiple-stable-candidates"
    assert discovery["candidate_counts"]["stable_existing"] == 2
    assert "Multiple stable serial console candidates" in discovery["blockers"][0]


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
    assert "No Cisco serial console candidates" in discovery["blockers"][0]


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
    assert discovery["selection_source"] == "env-override"
    matching = [candidate for candidate in discovery["candidates"] if candidate["path"] == str(tty)]
    assert matching[0]["recommendation"] == "env-override"


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

    assert discovery["status"] == "needs-selection"


def test_cisco_setup_wizard_prompt_is_blocked() -> None:
    prompt = "Would you like to enter the initial configuration dialog? [yes/no]:"

    assert _prompt_state(prompt) == "setup-wizard"
    assert "setup wizard" in _prompt_blocker_message("setup-wizard")


def test_cisco_console_probe_redacts_blocked_prompt_sample(
    tmp_path: Path,
    monkeypatch,
) -> None:
    clear_probe_results()
    tty = tmp_path / "ttyUSB0"
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
    assert result["prompt_state"] == "exec"
    assert result["prompt_ready"] is True
    assert result["safe_show_commands_allowed"] is True
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


def test_cisco_prompt_readiness_blocks_unknown_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    result, writes = _run_prompt_readiness_with_fake_serial(
        tmp_path,
        monkeypatch,
        "unrecognized prompt text",
    )

    assert writes == [b"\n"]
    assert result["status"] == "blocked"
    assert result["prompt_state"] == "unknown"
    assert result["prompt_ready"] is False
    assert result["safe_show_commands_allowed"] is False


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


def test_cisco_setup_readiness_is_plan_only_until_management_bootstrap() -> None:
    readiness = get_cisco_setup_readiness(
        provider_mode="mock",
        planned_management_ip="10.10.8.112",
        management_configured=False,
    )
    encoded = json.dumps(readiness)

    assert readiness["provider_id"] == "cisco-setup"
    assert readiness["phase"] == "console-bootstrap-required"
    assert readiness["planned_management_ip"] == "10.10.8.112"
    assert readiness["management_configured"] is False
    assert readiness["bootstrap_preview"]["apply_enabled"] is False
    assert readiness["bootstrap_preview"]["commands_redacted"] is True
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
        esxi_test_host="192.0.2.50",
        esxi_configured=False,
        cisco_target_ip="192.0.2.60",
        cisco_mgmt_configured=False,
    )

    def fake_tcp(host: str, port: int) -> dict[str, object]:
        calls.append((host, port))
        return {"configured": True, "reachable": True, "port": port, "attempts": []}

    monkeypatch.setattr(smoke, "settings", fake_settings)
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


def test_ilo_readonly_status_is_unchanged_by_management_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.providers.ilo_redfish.current_lab_safety",
        lambda: LabSafetyState(
            closed_loop_ack=True,
            readonly_ack=True,
            destructive_ack=False,
        ),
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

    status = adapter.health()

    assert status.status == "ready"
    assert status.safe_actions[0].enabled is True
    assert status.safe_actions[0].reason == "Run GET-only Redfish inventory checks."


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
    tty = tmp_path / "ttyUSB0"
    tty.touch()
    _allow_readonly_lab(monkeypatch)
    writes = _install_tracking_fake_serial(monkeypatch, [prompt_output])

    result = CiscoConsoleAdapter(
        provider_mode="local-readonly",
        config=CiscoConsoleConfig(port=str(tty), baud=9600, timeout_seconds=1.0),
    ).prompt_readiness()
    return result, writes


def _load_provider_smoke_module() -> types.ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "provider_smoke.py"
    spec = importlib.util.spec_from_file_location("provider_smoke_under_test", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
