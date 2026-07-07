from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
    stable.touch()

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        collect_details=False,
        device_hint="netapp",
    )

    assert candidates[0]["display_path"] == str(stable)
    assert candidates[0]["path_type"] == "by-id"
    assert candidates[0]["recommendation"] == "preferred-stable-path"


def test_ttyusb_is_preferred_over_stale_ttys(monkeypatch, tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    monkeypatch.setattr(serial_console_discovery, "_windows_serial_ports", lambda: [])
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


def test_fresh_ttys4_is_ranked_as_candidate(monkeypatch, tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    monkeypatch.setattr(serial_console_discovery, "_windows_serial_ports", lambda: [])
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


def test_windows_com_ports_are_discovered_as_selectable_candidates(monkeypatch, tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    monkeypatch.setattr(serial_console_discovery, "_windows_serial_ports", lambda: ["COM4", "COM10"])

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        collect_details=False,
        device_hint="netapp",
    )

    assert [candidate["display_path"] for candidate in candidates] == ["COM4", "COM10"]
    assert candidates[0]["path_type"] == "windows-com"
    assert candidates[0]["exists"] is True
    assert candidates[0]["readable"] is True
    assert candidates[0]["writable"] is True
    assert candidates[0]["recommendation"] == "windows-com-candidate"
    assert candidates[0]["confidence"] == "medium"


def test_configured_windows_com_hint_is_selectable_without_filesystem_path(tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        configured_hint="COM5",
        collect_details=False,
    )

    assert candidates[0]["display_path"] == "COM5"
    assert candidates[0]["path_type"] == "windows-com"
    assert candidates[0]["exists"] is True
    assert candidates[0]["target_path"] is None
    assert candidates[0]["recommendation"] == "windows-com-candidate"


def test_serial_discovery_self_heals_glob_errors(monkeypatch, tmp_path: Path) -> None:
    paths = _serial_paths(tmp_path)
    monkeypatch.setattr(serial_console_discovery, "_windows_serial_ports", lambda: [])
    original_glob = serial_console_discovery.glob.glob

    def flaky_glob(pattern: str):  # noqa: ANN202
        if pattern == str(paths["dev"] / "ttyUSB*"):
            raise OSError("serial glob unavailable")
        return original_glob(pattern)

    monkeypatch.setattr(serial_console_discovery.glob, "glob", flaky_glob)

    candidates = discover_serial_console_candidates(
        paths=_discovery_paths(paths),
        configured_hint=str(paths["dev"] / "ttyUSB9"),
        collect_details=False,
    )

    assert [candidate["display_path"] for candidate in candidates] == [str(paths["dev"] / "ttyUSB9")]
    assert candidates[0]["recommendation"] == "missing"


def test_serial_candidate_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    candidate_path = tmp_path / "ttyUSB9"
    original_exists = Path.exists

    def locked_exists(path: Path) -> bool:
        if path == candidate_path:
            raise OSError("serial path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", locked_exists)

    candidate = serial_console_discovery.inspect_serial_console_candidate(
        str(candidate_path),
        collect_details=False,
    )

    assert candidate["exists"] is False
    assert candidate["target_path"] is None
    assert candidate["readable"] is False
    assert candidate["writable"] is False
    assert candidate["recommendation"] == "missing"


def test_serial_candidate_self_heals_stat_probe_errors(monkeypatch, tmp_path: Path) -> None:
    candidate_path = tmp_path / "ttyUSB9"
    candidate_path.touch()
    original_stat = Path.stat

    def locked_stat(path: Path, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if path == candidate_path:
            raise OSError("serial metadata unavailable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(serial_console_discovery, "path_exists", lambda path: path == candidate_path)
    monkeypatch.setattr(Path, "stat", locked_stat)

    candidate = serial_console_discovery.inspect_serial_console_candidate(
        str(candidate_path),
        collect_details=False,
    )

    assert candidate["exists"] is True
    assert candidate["owner"] is None
    assert candidate["group"] is None
    assert candidate["mode"] is None
    assert candidate["modified_time"] is None
    assert candidate["modified_age_seconds"] is None


def test_in_use_state_dedupes_pids_preserving_probe_order(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        return name

    def fake_run(command: list[str], **_kwargs):  # noqa: ANN003
        calls.append(command)
        if command[0] == "fuser":
            return SimpleNamespace(returncode=0, stdout="456 123 456")
        return SimpleNamespace(returncode=0, stdout="123 789")

    monkeypatch.setattr(serial_console_discovery, "which", fake_which)
    monkeypatch.setattr(serial_console_discovery.subprocess, "run", fake_run)

    result = serial_console_discovery._in_use_state("/dev/ttyUSB0")

    assert result["state"] == "in_use"
    assert result["checked_with"] == ["fuser", "lsof"]
    assert result["pids"] == [456, 123, 789]
    assert calls == [["fuser", "/dev/ttyUSB0"], ["lsof", "-t", "/dev/ttyUSB0"]]


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


def test_serial_baud_order_dedupes_preserving_configured_first() -> None:
    assert serial_console_discovery.serial_baud_order(
        115200,
        common_bauds=(9600, 115200, 9600, 57600),
    ) == (115200, 9600, 57600)


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


def test_serial_probe_deadline_times_out_without_posix_signals() -> None:
    started = time.monotonic()

    try:
        serial_console_discovery._run_with_deadline(
            lambda: time.sleep(1) or {"status": "late"},
            timeout_seconds=0.05,
        )
    except TimeoutError as exc:
        assert "timed out" in str(exc)
    else:
        raise AssertionError("deadline should have raised TimeoutError")

    assert time.monotonic() - started < 0.5


def test_serial_timeout_classification_is_explicit() -> None:
    result = serial_console_discovery.probe_serial_candidate(
        _BlockingSerialModule(),
        [
            {
                "display_path": "/dev/ttyUSB0",
                "exists": True,
                "readable": True,
                "writable": True,
                "in_use": False,
                "path_type": "ttyUSB",
            }
        ][0],
        115200,
        options=SerialConsoleProbeOptions(timeout_seconds=0.01),
    )

    assert result["status"] == "blocked"
    assert result["classification"] == "serial_timeout"
    assert result["prompt_state"] == "serial_timeout"


def test_serial_console_discovery_script_artifact_labels_are_portable(tmp_path: Path) -> None:
    script = _load_serial_console_discovery_script()
    report = script.REPO_ROOT / "artifacts" / "codex-runs" / "serial-console-discovery-report.md"
    external = tmp_path / "serial-console-discovery-report.md"

    assert script._rel(report) == "artifacts/codex-runs/serial-console-discovery-report.md"
    assert script._rel(external) == str(external)


def test_serial_console_discovery_script_json_uses_atomic_store(monkeypatch, tmp_path: Path) -> None:
    script = _load_serial_console_discovery_script()
    run_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(script, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(script, "REPORT", run_dir / "serial-console-discovery-report.md")
    monkeypatch.setattr(script, "JSON_REPORT", run_dir / "serial-console-discovery-redacted.json")
    monkeypatch.setattr(
        script,
        "settings",
        SimpleNamespace(
            provider_mode="mock",
            netapp_console_port=None,
            cisco_console_port=None,
            netapp_console_baud=115200,
            cisco_console_baud=9600,
            netapp_console_timeout_seconds=1,
            cisco_console_timeout_seconds=1,
        ),
    )
    monkeypatch.setattr(script, "discover_serial_console_candidates", lambda **_kwargs: [])

    assert script.main() == 0

    saved = json.loads(script.JSON_REPORT.read_text(encoding="utf-8"))
    assert saved["action"] == "serial-console-discovery"
    assert saved["status"] == "blocked"
    assert script.REPORT.read_text(encoding="utf-8").strip()
    assert not list(run_dir.glob("*.tmp"))


class _BlockingSerialModule:
    @staticmethod
    def Serial(**_kwargs):
        time.sleep(3.2)
        return _NeverUsedSerialConnection()


class _NeverUsedSerialConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


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


def _load_serial_console_discovery_script() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "serial_console_discovery.py"
    spec = importlib.util.spec_from_file_location("serial_console_discovery_script_under_test", script_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
