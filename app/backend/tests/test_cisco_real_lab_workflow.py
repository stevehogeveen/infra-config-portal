from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts import cisco_real_lab_workflow as workflow


def test_console_ownership_paths_include_selected_by_id_and_resolved_tty(tmp_path: Path) -> None:
    dev = tmp_path / "dev"
    by_id = dev / "serial" / "by-id"
    by_id.mkdir(parents=True)
    tty = dev / "ttyUSB0"
    tty.touch()
    stable = by_id / "usb-Cisco_console-if00-port0"
    stable.symlink_to(tty)

    paths = workflow._console_ownership_paths({"effective_path": str(stable), "candidates": []})

    assert paths == [str(stable), str(tty)]


def test_claim_reclaims_allowed_console_owner_and_stale_lock(tmp_path: Path, monkeypatch) -> None:
    dev = tmp_path / "dev"
    by_id = dev / "serial" / "by-id"
    by_id.mkdir(parents=True)
    tty = dev / "ttyUSB0"
    tty.touch()
    stable = by_id / "usb-Cisco_console-if00-port0"
    stable.symlink_to(tty)
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


def test_bootstrap_apply_requested_is_args_apply_only() -> None:
    assert workflow._bootstrap_apply_requested(argparse.Namespace(apply=False)) is False
    assert workflow._bootstrap_apply_requested(argparse.Namespace(apply=True)) is True


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
    assert "interface range Gi1/0/1,Gi1/0/2" in commands
    assert " switchport access vlan 10" in commands
    assert "ip domain-name lab.local" in commands
    assert "crypto key generate rsa modulus 2048" in commands
    assert "ip ssh version 2" in commands
    assert "ip scp server enable" in commands
    assert "line vty 0 31" in commands
    assert " login local" in commands
    assert plan["domain_source"] == "default"
    assert plan["ssh_key_generation"] == "rsa modulus 2048"
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

    assert plan["access_port_source"] == "detected-show-interfaces-status"
    assert "interface range Gi1/0/7" in plan["redacted_commands"]


def test_bootstrap_apply_waits_longer_for_keygen_and_save() -> None:
    assert workflow._bootstrap_command_wait_seconds("crypto key generate rsa modulus 2048") == 8.0
    assert workflow._bootstrap_command_wait_seconds("write memory") == 8.0
    assert workflow._bootstrap_command_wait_seconds("ip ssh version 2") == 2.0


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
    ethernet = {"status": "blocked", "host_route": {"status": "ready"}}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "svi_down"

    switch["vlan10_state"] = {"configured": True, "ip": "192.168.1.204", "line_status": "up", "protocol_status": "up"}
    ethernet["host_route"] = {"status": "blocked"}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "host_routing"

    switch["vlan10_state"] = {"configured": True, "ip": "192.168.1.203", "line_status": "up", "protocol_status": "up"}

    assert workflow._classify_vlan10_failure(apply, switch, ethernet) == "config"
