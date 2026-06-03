from __future__ import annotations

import builtins
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.providers.cisco_console import (
    CiscoConsoleConfig,
    ConsoleDiscoveryPaths,
    _prompt_blocker_message,
    _prompt_state,
    discover_cisco_console,
)
from app.providers.cisco_ansible import CiscoAnsibleAdapter, CiscoAnsibleConfig
from app.providers.esxi_readonly import EsxiReadonlyAdapter, EsxiReadonlyConfig
from app.providers.ilo_redfish import IloRedfishAdapter, IloRedfishConfig
from app.providers.probe_cache import clear_probe_results
from app.providers.redaction import redact_sensitive
from app.providers.registry import provider_registry


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
