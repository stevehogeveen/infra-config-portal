from __future__ import annotations

import os
import time
from pathlib import Path

from app.services import serial_console_discovery
from app.services.serial_console_discovery import (
    SerialConsoleDiscoveryPaths,
    SerialConsoleProbeOptions,
    classify_serial_console_text,
    discover_serial_console_candidates,
    probe_serial_candidates,
)


def test_by_id_path_is_preferred(tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    tty = paths["dev"] / "ttyUSB0"
    tty.touch()
    stable = paths["by_id"] / "usb-NetApp_MCP2221-if00-port0"
    stable.symlink_to(tty)

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        collect_details=False,
        device_hint="netapp",
    )

    assert candidates[0]["display_path"] == str(stable)
    assert candidates[0]["path_type"] == "by-id"
    assert candidates[0]["recommendation"] == "preferred-stable-path"


def test_ttyusb_is_preferred_over_stale_ttys(tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    usb = paths["dev"] / "ttyUSB0"
    ttys = paths["dev"] / "ttyS4"
    usb.touch()
    ttys.touch()
    stale = time.time() - (8 * 24 * 60 * 60)
    os.utime(ttys, (stale, stale))

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        collect_details=False,
    )

    assert candidates[0]["display_path"] == str(usb)
    assert candidates[0]["path_type"] == "ttyUSB"
    assert candidates[1]["display_path"] == str(ttys)


def test_fresh_ttys4_is_ranked_as_candidate(tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    ttys4 = paths["dev"] / "ttyS4"
    ttys4.touch()

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        collect_details=False,
    )

    assert candidates[0]["display_path"] == str(ttys4)
    assert candidates[0]["path_type"] == "ttyS"
    assert candidates[0]["confidence"] == "medium"
    assert any("recent modified timestamp" in reason for reason in candidates[0]["selection_reasons"])


def test_in_use_port_is_deprioritized(tmp_path: Path, monkeypatch) -> None:
    paths = _serial_paths(tmp_path)
    in_use = paths["dev"] / "ttyUSB0"
    free = paths["dev"] / "ttyUSB1"
    in_use.touch()
    free.touch()

    def fake_in_use_state(path: str) -> dict:
        if path == str(in_use):
            return {"state": "in_use", "checked_with": ["fuser"], "unavailable_tools": [], "pids": [123]}
        return {"state": "not_in_use", "checked_with": ["fuser"], "unavailable_tools": [], "pids": []}

    monkeypatch.setattr(serial_console_discovery, "_in_use_state", fake_in_use_state)

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        collect_details=False,
    )

    assert candidates[0]["display_path"] == str(free)
    assert candidates[0]["in_use"] is False
    assert candidates[-1]["display_path"] == str(in_use)
    assert candidates[-1]["in_use"] is True


def test_netapp_loader_prompt_classification() -> None:
    classification = classify_serial_console_text("LOADER-A> ", device_hint="netapp")

    assert classification["device_type"] == "netapp"
    assert classification["classification"] == "bootloader"
    assert classification["prompt_state"] == "loader_prompt"


def test_ontap_login_classification() -> None:
    classification = classify_serial_console_text("ONTAP login: ", device_hint="netapp")

    assert classification["device_type"] == "netapp"
    assert classification["classification"] == "login_prompt"
    assert classification["prompt_state"] == "login_required"


def test_cisco_prompt_classification() -> None:
    classification = classify_serial_console_text("Switch# ", device_hint="cisco")

    assert classification["device_type"] == "cisco"
    assert classification["classification"] == "prompt_detected"
    assert classification["prompt_state"] == "privileged_exec"


def test_no_output_classification() -> None:
    classification = classify_serial_console_text("", device_hint="netapp")

    assert classification["device_type"] == "unknown"
    assert classification["classification"] == "no_bytes_read"
    assert classification["prompt_state"] == "no_output"


def test_wrong_baud_gibberish_classification() -> None:
    classification = classify_serial_console_text("\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd")

    assert classification["device_type"] == "unknown"
    assert classification["classification"] == "unreadable_gibberish"
    assert classification["prompt_state"] == "unreadable"


def test_probe_uses_provider_specific_wake_sequences() -> None:
    writes: list[bytes] = []

    class FakeSerialConnection:
        in_waiting = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def write(self, payload: bytes) -> int:
            writes.append(payload)
            return len(payload)

        def read(self, _size: int) -> bytes:
            return b""

        def reset_input_buffer(self) -> None:
            return None

    class FakeSerialModule:
        @staticmethod
        def Serial(**_kwargs):
            return FakeSerialConnection()

    result = probe_serial_candidates(
        FakeSerialModule,
        [
            {
                "display_path": "/dev/ttyUSB0",
                "exists": True,
                "readable": True,
                "writable": True,
                "in_use": False,
                "path_type": "ttyUSB",
            }
        ],
        options=SerialConsoleProbeOptions(
            configured_baud=115200,
            timeout_seconds=0.05,
            device_hint="netapp",
            wake_sequences=(("newline", b"\n"), ("carriage-return", b"\r")),
        ),
    )

    assert result["wake_sequences"] == ["newline", "carriage-return"]
    assert writes == [b"\n", b"\r"] * len(result["attempts"])
    assert b"\x03" not in writes


def _serial_paths(tmp_path: Path) -> dict[str, Path]:
    dev = tmp_path / "dev"
    by_id = dev / "serial" / "by-id"
    by_id.mkdir(parents=True)
    return {"dev": dev, "by_id": by_id}


def _discovery_paths(paths: dict[str, Path]) -> SerialConsoleDiscoveryPaths:
    dev = paths["dev"]
    by_id = paths["by_id"]
    return SerialConsoleDiscoveryPaths(
        by_id_glob=str(by_id / "*"),
        usb_glob=str(dev / "ttyUSB*"),
        acm_glob=str(dev / "ttyACM*"),
        ttys_glob=str(dev / "ttyS*"),
    )
