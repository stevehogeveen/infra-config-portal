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
