from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import cisco_real_lab_workflow as workflow
from scripts import cisco_console_ethernet_readiness as ethernet_readiness


def test_cisco_workflow_write_json_uses_atomic_store(tmp_path: Path) -> None:
    json_path = tmp_path / "cisco-details.json"

    workflow._write_json(json_path, {"status": "ready", "nested": {"value": 1}})

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "ready"
    assert not list(tmp_path.glob("*.tmp"))


def test_cisco_workflow_write_json_value_uses_atomic_store(tmp_path: Path) -> None:
    json_path = tmp_path / "cisco-samples.json"

    workflow._write_json(json_path, [{"status": "ready"}, {"status": "blocked"}])

    assert json.loads(json_path.read_text(encoding="utf-8")) == [
        {"status": "ready"},
        {"status": "blocked"},
    ]
    assert not list(tmp_path.glob("*.tmp"))


def test_cisco_finish_writes_reports_atomically_and_dedupes(monkeypatch, tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True)
    paths = {
        "DETAILS": run_dir / "cisco-4h-lab-run-details-redacted.json",
        "REPORT": run_dir / "cisco-4h-lab-run-report.md",
        "FIX_REPORT": run_dir / "cisco-privileged-exec-fix-report.md",
        "PRIVILEGE_HARDENING_REPORT": run_dir / "cisco-privilege-hardening-report.md",
        "PRIVILEGE_DIAGNOSIS_REPORT": run_dir / "cisco-privilege-diagnosis-report.md",
        "PASSWORD_RECOVERY_REPORT": run_dir / "cisco-password-recovery-guidance-report.md",
        "BOOTSTRAP_APPLY_REPORT": run_dir / "cisco-bootstrap-apply-report.md",
        "VLAN10_BOOTSTRAP_FIX_REPORT": run_dir / "cisco-vlan10-bootstrap-fix-report.md",
        "LOGIN_BOOTSTRAP_FIX_REPORT": run_dir / "cisco-login-bootstrap-fix-report.md",
        "COMMANDER_MODE_REPORT": run_dir / "cisco-console-commander-mode-report.md",
    }
    for name, path in paths.items():
        monkeypatch.setattr(workflow, name, path)
    payload = {
        "checked_at": "2026-06-25T00:00:00+00:00",
        "provider_mode": "local-readonly",
        "stages": {"apply": {"status": "not-attempted"}},
        "blockers": ["duplicate", "duplicate", "unique"],
        "warnings": ["notice", "notice"],
    }

    assert workflow._finish(payload) == 0
    capsys.readouterr()

    saved = json.loads(paths["DETAILS"].read_text(encoding="utf-8"))
    assert saved["blockers"] == ["duplicate", "unique"]
    assert saved["warnings"] == ["notice"]
    assert paths["REPORT"].read_text(encoding="utf-8").strip()
    assert paths["VLAN10_BOOTSTRAP_FIX_REPORT"].read_text(encoding="utf-8").strip()
    assert not paths["BOOTSTRAP_APPLY_REPORT"].exists()
    assert not list(run_dir.glob("*.tmp"))


def test_console_ownership_paths_include_selected_by_id_and_resolved_tty(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    by_id = dev / "serial" / "by-id"
    by_id.mkdir(parents=True)
    tty = dev / "ttyUSB0"
    tty.touch()
    stable = by_id / "usb-Cisco_console-if00-port0"
    _symlink_or_skip(stable, tty)

    paths = workflow._console_ownership_paths({"effective_path": str(stable), "candidates": []})

    assert paths == [str(stable), str(tty)]


def test_cisco_workflow_helper_dedupe_preserves_first_seen_order(tmp_path: Path, monkeypatch) -> None:
    assert workflow._baud_order(115200) == (115200, 9600, 19200, 38400, 57600)
    assert workflow._unique_ports([" Gi1/0/1 ", "Gi1/0/1", "", "Gi1/0/2"]) == ["Gi1/0/1", "Gi1/0/2"]
    assert workflow._detect_access_ports_from_interfaces_status(
        "\n".join(
            [
                "Gi1/0/1 connected 10 a-full a-1000 10/100/1000BaseTX",
                "Gi1/0/1 connected 10 a-full a-1000 10/100/1000BaseTX",
                "Gi1/0/2 connected 20 a-full a-1000 10/100/1000BaseTX",
            ]
        )
    ) == ["Gi1/0/1", "Gi1/0/2"]
    assert workflow._parse_vlan10_ports(
        "10 VLAN0010 active Gi1/0/1, Gi1/0/1, Gi1/0/3",
        "",
    ) == ["Gi1/0/1", "Gi1/0/3"]

    monkeypatch.setattr(workflow.shutil, "which", lambda _name: "/usr/bin/fuser")
    monkeypatch.setattr(
        workflow.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout="123 123 456", stderr=""),
    )
    assert workflow._pids_using_path("/dev/ttyUSB0") == [123, 456]

    lock_dir = tmp_path / "lock"
    assert workflow._console_lock_paths(
        ["/dev/ttyUSB0", "/dev/ttyUSB0", "/dev/ttyACM1"],
        lock_dirs=(lock_dir,),
    ) == [lock_dir / "LCK..ttyUSB0", lock_dir / "LCK..ttyACM1"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("YES", True),
        (" on ", True),
        ("0", False),
        ("false", False),
        ("unexpected", False),
    ],
)
def test_cisco_workflow_uses_shared_env_flag_parser(monkeypatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("CISCO_CONSOLE_RECLAIM", value)

    assert workflow._env_flag("CISCO_CONSOLE_RECLAIM") is expected


def test_claim_reclaims_allowed_console_owner_and_stale_lock(tmp_path: Path, monkeypatch) -> None:
    dev = tmp_path / "dev"
    by_id = dev / "serial" / "by-id"
    by_id.mkdir(parents=True)
    tty = dev / "ttyUSB0"
    tty.touch()
    stable = by_id / "usb-Cisco_console-if00-port0"
    _symlink_or_skip(stable, tty)
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    lock_file = lock_dir / "LCK..ttyUSB0"
    lock_file.write_text("123\n", encoding="utf-8")
    discovery = {"status": "ready", "effective_path": str(stable), "candidates": []}
    ownership_results = [
        {
            "checked_paths": [str(stable), str(tty)],
            "owned": True,
            "owners": [
                {
                    "pid": 123,
                    "command": "screen",
                    "args": "screen <redacted>",
                    "paths": [str(stable), str(tty)],
                    "summary": "pid=123 command=screen",
                }
            ],
        },
        {"checked_paths": [str(stable), str(tty)], "owned": False, "owners": []},
    ]
    terminated: list[int] = []

    def fake_serial_ownership(_discovery: dict[str, Any]) -> dict[str, Any]:
        return ownership_results.pop(0)

    def fake_terminate(pid: int) -> dict[str, Any]:
        terminated.append(pid)
        return {"termination": "terminated", "signal": "SIGTERM"}

    monkeypatch.setattr(workflow, "_serial_ownership", fake_serial_ownership)
    monkeypatch.setattr(workflow, "_terminate_process", fake_terminate)
    monkeypatch.setattr(workflow, "discover_cisco_console", lambda _config: discovery)

    result = workflow._claim_cisco_console(
        discovery,
        provider_mode="local-lab-readwrite",
        reclaim_enabled=True,
        lock_dirs=(lock_dir,),
    )

    assert result["status"] == "ready"
    assert result["reclaimed"] is True
    assert terminated == [123]
    assert result["terminated_processes"][0]["command"] == "screen"
    assert result["lock_files_removed"] == [str(lock_file)]
    assert result["post_ownership"]["owned"] is False
    assert not lock_file.exists()


def test_clear_console_lock_files_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    locked = lock_dir / "LCK..ttyUSB0"
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == locked:
            raise OSError("lock path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = workflow._clear_console_lock_files(["/dev/ttyUSB0"], lock_dirs=(lock_dir,))

    assert result == {"removed": [], "errors": []}


def test_claim_blocks_owner_without_reclaim_lane(tmp_path: Path, monkeypatch) -> None:
    discovery = {"status": "ready", "effective_path": "/dev/ttyUSB0", "candidates": []}
    ownership = {
        "checked_paths": ["/dev/ttyUSB0"],
        "owned": True,
        "owners": [{"pid": 123, "command": "screen", "paths": ["/dev/ttyUSB0"], "summary": "screen"}],
    }
    monkeypatch.setattr(workflow, "_serial_ownership", lambda _discovery: ownership)

    result = workflow._claim_cisco_console(discovery, provider_mode="local-readonly", reclaim_enabled=True)

    assert result["status"] == "blocked"
    assert result["reclaim_allowed"] is False
    assert result["terminated_processes"] == []
    assert "CISCO_CONSOLE_RECLAIM=true" in result["blockers"][0]


def test_serial_ownership_reports_unsupported_fuser(monkeypatch) -> None:
    monkeypatch.setattr(workflow.shutil, "which", lambda _name: None)

    result = workflow._serial_ownership(
        {"status": "ready", "effective_path": "/dev/ttyUSB0", "candidates": []}
    )

    assert result["checked_paths"][0] == "/dev/ttyUSB0"
    assert result["ownership_check_supported"] is False
    assert result["unavailable_tools"] == ["fuser"]
    assert result["owned"] is False
    assert result["owners"] == []


def test_pids_using_path_self_heals_when_fuser_fails(monkeypatch) -> None:
    monkeypatch.setattr(workflow.shutil, "which", lambda _name: "/usr/bin/fuser")

    def fake_run(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise PermissionError("fuser unavailable")

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    assert workflow._pids_using_path("/dev/ttyUSB0") == []


def test_ping_host_uses_windows_ping_flags(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="reply", stderr="")

    monkeypatch.setattr(workflow.os, "name", "nt")
    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    result = workflow._ping_host("192.0.2.10")

    assert result["status"] == "ok"
    assert calls == [["ping", "-n", "2", "-w", "2000", "192.0.2.10"]]


def test_ping_host_uses_posix_ping_flags(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="timeout")

    monkeypatch.setattr(workflow.os, "name", "posix")
    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    result = workflow._ping_host("192.0.2.10")

    assert result["status"] == "failed"
    assert result["error"] == "timeout"
    assert calls == [["ping", "-c", "2", "-W", "2", "192.0.2.10"]]


def test_host_route_reports_unsupported_tool_without_raising(monkeypatch) -> None:
    def fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("route tool missing")

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)

    result = workflow._host_route_to("192.0.2.10")

    assert result["status"] == "unsupported"
    assert result["supported"] is False
    assert "route tool missing" in result["error"]


def test_bootstrap_apply_requested_is_args_apply_only() -> None:
    assert workflow._bootstrap_apply_requested(argparse.Namespace(apply=False)) is False
    assert workflow._bootstrap_apply_requested(argparse.Namespace(apply=True)) is True


def test_ethernet_readiness_accepts_privileged_exec_prompt() -> None:
    readiness = {
        "console": {"status": "ready"},
        "ethernet_readiness": {"ready": True, "management_configured": True},
        "blockers": [],
    }
    prompt = {
        "prompt_state": "privileged-exec",
        "blockers": ["Privileged exec prompt was detected; no configuration commands were sent."],
    }

    assert ethernet_readiness._overall_status(readiness, prompt) == "ready"
    assert ethernet_readiness._blockers(readiness, prompt) == []


def test_ethernet_readiness_treats_configured_login_prompt_as_recoverable() -> None:
    readiness = {
        "console": {"status": "ready"},
        "ethernet_readiness": {"ready": True, "management_configured": True},
        "blockers": [],
        "warnings": [],
    }
    prompt = {
        "prompt_state": "login-required",
        "credentials_configured": True,
        "blockers": ["Console is at a login prompt; use the guarded Cisco privilege/bootstrap workflow."],
    }

    assert ethernet_readiness._overall_status(readiness, prompt) == "ready"
    assert ethernet_readiness._blockers(readiness, prompt) == []
    assert "guarded privilege check" in ethernet_readiness._warnings(readiness, prompt)[0]


def test_ethernet_readiness_keeps_scalar_blockers_and_warnings_whole() -> None:
    readiness = {
        "console": {"status": "ready"},
        "ethernet_readiness": {"ready": False, "management_configured": False},
        "blockers": "console blocker",
        "warnings": "console warning",
    }
    prompt = {
        "prompt_state": "setup-wizard",
        "blockers": "prompt blocker",
    }

    assert ethernet_readiness._blockers(readiness, prompt) == [
        "console blocker",
        "prompt blocker",
        "Cisco Ethernet management is not configured; SSH/SCP readiness requires console bootstrap.",
    ]
    assert ethernet_readiness._warnings(readiness, prompt) == ["console warning"]


def test_ethernet_readiness_artifact_labels_are_portable(tmp_path: Path) -> None:
    report = (
        ethernet_readiness.REPO_ROOT
        / "artifacts"
        / "codex-runs"
        / "cisco-console-ethernet-readiness-report.md"
    )
    external = tmp_path / "cisco-console-ethernet-readiness-report.md"

    assert ethernet_readiness._rel(report) == (
        "artifacts/codex-runs/cisco-console-ethernet-readiness-report.md"
    )
    assert ethernet_readiness._rel(external) == str(external)


def test_ethernet_readiness_main_writes_artifacts_atomically(monkeypatch, tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True)
    monkeypatch.setattr(ethernet_readiness, "REPORT", run_dir / "cisco-console-ethernet-readiness-report.md")
    monkeypatch.setattr(ethernet_readiness, "DETAILS", run_dir / "cisco-console-ethernet-readiness-redacted.json")
    monkeypatch.setattr(
        ethernet_readiness,
        "settings",
        SimpleNamespace(
            provider_mode="local-readonly",
            cisco_console_port="COM3",
            cisco_target_ip="192.0.2.204",
            cisco_test_username="operator",
            cisco_test_password="secret",
            cisco_enable_password="enable-secret",
        ),
    )

    class FakeConsoleAdapter:
        def __init__(self, _provider_mode: str) -> None:
            pass

        def health(self) -> SimpleNamespace:
            return SimpleNamespace(status="ready")

        def prompt_readiness(self) -> dict[str, Any]:
            return {"prompt_state": "privileged-exec", "prompt_sample": {"captured": True}, "blockers": []}

    class FakeAnsibleAdapter:
        def __init__(self, _provider_mode: str) -> None:
            pass

        def health(self) -> SimpleNamespace:
            return SimpleNamespace(status="awaiting-bootstrap")

    readiness = {
        "console": {"status": "ready", "selected_path": "COM3"},
        "ethernet_readiness": {"ready": True, "management_configured": True},
        "blockers": [],
        "warnings": ["notice", "notice"],
    }
    monkeypatch.setattr(ethernet_readiness, "CiscoConsoleAdapter", FakeConsoleAdapter)
    monkeypatch.setattr(ethernet_readiness, "CiscoAnsibleAdapter", FakeAnsibleAdapter)
    monkeypatch.setattr(ethernet_readiness, "get_cisco_setup_readiness", lambda **_kwargs: readiness)
    monkeypatch.setattr(ethernet_readiness, "build_cisco_console_bootstrap_plan", lambda: {"status": "ready"})

    assert ethernet_readiness.main() == 0
    capsys.readouterr()

    saved = json.loads(ethernet_readiness.DETAILS.read_text(encoding="utf-8"))
    assert saved["status"] == "ready"
    assert saved["blockers"] == []
    assert saved["warnings"] == ["notice"]
    assert ethernet_readiness.REPORT.read_text(encoding="utf-8").strip()
    assert not list(run_dir.glob("*.tmp"))


def test_vlan10_bootstrap_plan_configures_required_lab_network(monkeypatch) -> None:
    monkeypatch.setenv("CISCO_LAB_ACCESS_PORTS", "Gi1/0/1, Gi1/0/2")
    monkeypatch.setattr(
        workflow,
        "settings",
        workflow.settings.__class__(
            provider_mode="local-lab-readwrite",
            cisco_target_ip="192.168.1.204",
            cisco_management_prefix="/24",
            cisco_management_vlan=None,
            cisco_management_interface=None,
            cisco_test_username="admin",
            cisco_test_password="secret",
        ),
    )

    plan = workflow._bootstrap_plan({"detected_access_ports": ["Gi1/0/3"]})
    commands = plan["redacted_commands"]

    assert plan["status"] == "ready"
    assert plan["management_vlan"] == "10"
    assert plan["management_interface"] == "Vlan10"
    assert "vlan 10" in commands
    assert "interface Vlan10" in commands
    assert " ip address 192.168.1.204 255.255.255.0" in commands
    assert " no shutdown" in commands
    assert "interface Gi1/0/1" in commands
    assert "interface Gi1/0/2" in commands
    assert "interface range Gi1/0/1,Gi1/0/2" not in commands
    assert " switchport access vlan 10" in commands
    assert " switchport mode trunk" not in commands
    assert "ip domain-name lab.local" in commands
    assert "crypto key generate rsa general-keys label LAB-SSH-HOSTKEY modulus 2048" in commands
    assert "ip ssh rsa keypair-name LAB-SSH-HOSTKEY" in commands
    assert "ip ssh version 2" in commands
    assert "ip scp server enable" in commands
    assert "line vty 0 31" in commands
    assert " login local" in commands
    assert plan["domain_source"] == "default"
    assert plan["ssh_key_generation"] == "rsa general-keys label LAB-SSH-HOSTKEY modulus 2048"
    assert plan["ssh_keypair_name"] == "LAB-SSH-HOSTKEY"
    assert commands[-1] == "write memory"


def test_vlan10_bootstrap_plan_uses_detected_access_ports(monkeypatch) -> None:
    monkeypatch.delenv("CISCO_LAB_ACCESS_PORTS", raising=False)
    monkeypatch.delenv("CISCO_ACCESS_PORTS", raising=False)
    monkeypatch.delenv("CISCO_LAB_PORTS", raising=False)
    monkeypatch.setattr(
        workflow,
        "settings",
        workflow.settings.__class__(
            provider_mode="local-lab-readwrite",
            cisco_target_ip="192.168.1.204",
            cisco_management_prefix="/24",
            cisco_test_username="admin",
            cisco_test_password="secret",
        ),
    )

    plan = workflow._bootstrap_plan({"detected_access_ports": ["Gi1/0/7"]})

    assert plan["access_port_source"] == "always-access-plus-detected-show-interfaces-status"
    assert plan["always_access_ports"] == ["Gi1/0/1"]
    assert "interface Gi1/0/1" in plan["redacted_commands"]
    assert "interface Gi1/0/7" in plan["redacted_commands"]
    assert "interface range Gi1/0/1,Gi1/0/7" not in plan["redacted_commands"]


def test_vlan10_bootstrap_plan_keeps_first_port_access_even_when_detection_skips_it(monkeypatch) -> None:
    monkeypatch.delenv("CISCO_LAB_ACCESS_PORTS", raising=False)
    monkeypatch.delenv("CISCO_ACCESS_PORTS", raising=False)
    monkeypatch.delenv("CISCO_LAB_PORTS", raising=False)
    monkeypatch.setattr(
        workflow,
        "settings",
        workflow.settings.__class__(
            provider_mode="local-lab-readwrite",
            cisco_target_ip="192.168.1.204",
            cisco_management_prefix="/24",
            cisco_test_username="admin",
            cisco_test_password="secret",
        ),
    )

    plan = workflow._bootstrap_plan({"detected_access_ports": ["Gi1/0/2", "Gi1/0/3"]})

    assert "interface Gi1/0/1" in plan["redacted_commands"]
    assert "interface Gi1/0/2" in plan["redacted_commands"]
    assert "interface Gi1/0/3" in plan["redacted_commands"]
    assert "interface range Gi1/0/1,Gi1/0/2,Gi1/0/3" not in plan["redacted_commands"]
    assert " switchport mode access" in plan["redacted_commands"]
    assert " switchport mode trunk" not in plan["redacted_commands"]


def test_bootstrap_apply_waits_longer_for_keygen_and_save() -> None:
    assert (
        workflow._bootstrap_command_wait_seconds(
            "crypto key generate rsa general-keys label LAB-SSH-HOSTKEY modulus 2048"
        )
        == 8.0
    )
    assert workflow._bootstrap_command_wait_seconds("write memory") == 8.0
    assert workflow._bootstrap_command_wait_seconds("ip ssh version 2") == 2.0


def test_crypto_keygen_answers_existing_key_prompt(monkeypatch) -> None:
    sent: list[str] = []
    reads = iter(["Do you really want to replace them? [yes/no]:", "keys generated"])

    def fake_send(_conn: Any, command: str, *, secret: bool = False) -> None:
        del secret
        sent.append(command)

    def fake_read(_conn: Any, *, window: float) -> str:
        assert window == 8.0
        return next(reads)

    monkeypatch.setattr(workflow, "_send", fake_send)
    monkeypatch.setattr(workflow, "_read", fake_read)

    workflow._send_crypto_keygen(
        object(),
        "crypto key generate rsa general-keys label LAB-SSH-HOSTKEY modulus 2048",
    )

    assert sent == ["crypto key generate rsa general-keys label LAB-SSH-HOSTKEY modulus 2048", "yes"]


def test_read_only_validation_does_not_overwrite_apply_report() -> None:
    assert workflow._should_write_bootstrap_apply_report({"stages": {"apply": {"status": "completed"}}}) is True
    assert workflow._should_write_bootstrap_apply_report({"stages": {"apply": {"status": "blocked"}}}) is True
    assert workflow._should_write_bootstrap_apply_report({"stages": {"apply": {"status": "not-attempted"}}}) is False


def test_post_apply_validation_reconnects_before_show_commands(monkeypatch) -> None:
    sent: list[str] = []
    reads = iter(
        [
            "DEVICE#",
            "Vlan10 192.168.1.204 YES manual up up\n",
            "10 LAB-MGMT active Gi1/0/2\n",
            "Gi1/0/2                    connected    10         a-full a-100 10/100/1000BaseTX\n",
        ]
    )

    def fake_send(_conn: Any, command: str, *, secret: bool = False) -> None:
        del secret
        sent.append(command)

    def fake_read(_conn: Any, *, window: float) -> str:
        del window
        return next(reads, "")

    class FakeSerialModule:
        class Serial:
            def __init__(self, **_kwargs: Any) -> None:
                pass

            def __enter__(self) -> "FakeSerialModule.Serial":
                return self

            def __exit__(self, *_args: Any) -> None:
                return None

    monkeypatch.setattr(workflow.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(workflow, "_send", fake_send)
    monkeypatch.setattr(workflow, "_read", fake_read)

    validation = workflow._post_apply_reconnect_switch_validation(
        FakeSerialModule,
        "/dev/ttyUSB0",
        9600,
        {"selected_or_detected_access_ports": ["Gi1/0/2"]},
    )

    assert validation["connection_strategy"] == "serial-reconnect-after-apply"
    assert validation["status"] == "ready"
    assert validation["vlan10_state"]["ip"] == "192.168.1.204"
    assert validation["ports_assigned_vlan10"] == ["Gi1/0/2"]
    assert sent[:2] == ["", "show ip interface brief | include Vlan10"]


def test_detect_access_ports_from_interfaces_status() -> None:
    output = """
Port      Name               Status       Vlan       Duplex  Speed Type
Gi1/0/1                      connected    1          a-full  a-100 10/100/1000BaseTX
Gi1/0/2                      notconnect   10         auto    auto  10/100/1000BaseTX
Gi1/0/3                      connected    trunk      a-full  a-100 10/100/1000BaseTX
Te1/1/1                      connected    routed     a-full  a-10G SFP
"""

    assert workflow._detect_access_ports_from_interfaces_status(output) == ["Gi1/0/1", "Gi1/0/2"]


def test_vlan10_failure_classifier_distinguishes_svi_and_host_route() -> None:
    apply = {"status": "completed"}
    switch = {
        "vlan10_state": {"configured": True, "ip": "192.168.1.204", "line_status": "down", "protocol_status": "down"},
        "ports_assigned_vlan10": ["Gi1/0/1"],
    }
    ethernet = {"status": "blocked", "host_route": {"status": "ready"}, "ping": {"status": "ok"}}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "svi_down"

    switch["vlan10_state"] = {"configured": True, "ip": "192.168.1.204", "line_status": "up", "protocol_status": "up"}
    ethernet["host_route"] = {"status": "blocked"}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "host_routing"

    ethernet["host_route"] = {"status": "ready"}
    ethernet["ping"] = {"status": "ok"}
    ethernet["ssh"] = {"reachable": False, "error": "[Errno 111] Connection refused"}
    ethernet["scp"] = {"reachable": False, "error": "[Errno 111] Connection refused"}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "ssh_service"

    ethernet["ssh"] = {"reachable": True}
    ethernet["scp"] = {"reachable": True}
    ethernet["ping"] = {"status": "failed"}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "host_reachability"

    switch["vlan10_state"] = {"configured": True, "ip": "192.168.1.203", "line_status": "up", "protocol_status": "up"}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "config"


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        if os.name == "nt":
            pytest.skip(f"Windows symlink privileges are not available: {exc}")
        raise
