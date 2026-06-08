from __future__ import annotations

import glob
import grp
import os
import pwd
import re
import signal
import stat
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any


COMMON_SERIAL_BAUDS = (9600, 115200, 19200, 38400, 57600)
SERIAL_WAKE_SEQUENCES = (
    ("newline", b"\n"),
    ("carriage-return", b"\r"),
    ("ctrl-c", b"\x03"),
)
RECENT_TTYS_SECONDS = 24 * 60 * 60
MAX_PREVIEW_CHARS = 1600
SAFE_UDEV_KEYS = {
    "DEVNAME",
    "DEVPATH",
    "DEVTYPE",
    "ID_BUS",
    "ID_MODEL",
    "ID_MODEL_ID",
    "ID_PATH",
    "ID_REVISION",
    "ID_TYPE",
    "ID_USB_DRIVER",
    "ID_VENDOR",
    "ID_VENDOR_ID",
    "SUBSYSTEM",
}
NETAPP_NAME_HINTS = ("netapp", "mcp2221", "microchip")
CISCO_NAME_HINTS = ("cisco",)
USB_SERIAL_NAME_HINTS = (
    "ftdi",
    "prolific",
    "silicon_labs",
    "silicon-labs",
    "cp210",
    "usb-serial",
    "usb_serial",
)


@dataclass(frozen=True)
class SerialConsoleDiscoveryPaths:
    by_id_glob: str = "/dev/serial/by-id/*"
    usb_glob: str = "/dev/ttyUSB*"
    acm_glob: str = "/dev/ttyACM*"
    ttys_glob: str = "/dev/ttyS*"


@dataclass(frozen=True)
class SerialConsoleProbeOptions:
    configured_baud: int | None = None
    timeout_seconds: float = 2.0
    max_bytes: int = 8192
    device_hint: str | None = None
    max_candidates: int | None = 3
    wake_sequences: tuple[tuple[str, bytes], ...] | None = None


def discover_serial_console_candidates(
    *,
    configured_hint: str | None = None,
    paths: SerialConsoleDiscoveryPaths | None = None,
    collect_details: bool = True,
    device_hint: str | None = None,
) -> list[dict[str, Any]]:
    paths = paths or SerialConsoleDiscoveryPaths()
    now = time.time()
    discovered: list[tuple[str, str]] = []
    for path in sorted(glob.glob(paths.by_id_glob)):
        discovered.append((path, "by-id"))
    for path in sorted(glob.glob(paths.usb_glob)):
        discovered.append((path, "ttyUSB"))
    for path in sorted(glob.glob(paths.acm_glob)):
        discovered.append((path, "ttyACM"))
    for path in sorted(glob.glob(paths.ttys_glob)):
        discovered.append((path, "ttyS"))
    if configured_hint:
        discovered.insert(0, (configured_hint, _path_type(configured_hint)))

    dmesg = _read_dmesg() if collect_details else _tool_unavailable("not-collected")
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for path, path_type in discovered:
        if path in seen:
            continue
        seen.add(path)
        candidates.append(
            inspect_serial_console_candidate(
                path,
                configured_hint=configured_hint,
                path_type=path_type,
                collect_details=collect_details,
                dmesg=dmesg,
                now=now,
                device_hint=device_hint,
            )
        )

    return rank_serial_console_candidates(
        candidates,
        configured_hint=configured_hint,
        now=now,
        device_hint=device_hint,
    )


def inspect_serial_console_candidate(
    path: str,
    *,
    configured_hint: str | None = None,
    path_type: str | None = None,
    collect_details: bool = True,
    dmesg: dict[str, Any] | None = None,
    now: float | None = None,
    device_hint: str | None = None,
) -> dict[str, Any]:
    now = now or time.time()
    path_obj = Path(path)
    exists = path_obj.exists()
    path_type = path_type or _path_type(path)
    resolved_path = str(path_obj.resolve(strict=False)) if exists else None
    stat_result = _stat_path(path_obj) if exists else None
    readable = os.access(path, os.R_OK) if exists else False
    writable = os.access(path, os.W_OK) if exists else False
    modified_time = _iso_from_timestamp(stat_result.st_mtime) if stat_result else None
    modified_age_seconds = int(max(now - stat_result.st_mtime, 0)) if stat_result else None
    in_use_state = _in_use_state(path) if exists else _not_in_use_state("missing")
    udevadm = _udevadm_info(path) if collect_details and exists else _tool_unavailable("not-collected")
    setserial = _setserial_info(path) if collect_details and exists else _tool_unavailable("not-collected")
    dmesg_info = (
        _dmesg_clues(path, resolved_path, dmesg or _tool_unavailable("not-collected"))
        if collect_details
        else _tool_unavailable("not-collected")
    )
    candidate = {
        "display_path": path,
        "path": path,
        "resolved_path": resolved_path,
        "target_path": resolved_path,
        "exists": exists,
        "readable": readable,
        "writable": writable,
        "owner": _owner_name(stat_result) if stat_result else None,
        "group": _group_name(stat_result) if stat_result else None,
        "mode": _mode_string(stat_result) if stat_result else None,
        "modified_time": modified_time,
        "modified_age_seconds": modified_age_seconds,
        "stable_path": path_type == "by-id",
        "path_type": path_type,
        "label": _candidate_label(path, resolved_path),
        "in_use": in_use_state["state"] == "in_use",
        "in_use_state": in_use_state,
        "udevadm": udevadm,
        "setserial": setserial,
        "dmesg": dmesg_info,
        "rank": 0,
        "recommendation": "unranked",
        "confidence": "low",
        "selection_reasons": [],
    }
    ranked = rank_serial_console_candidates(
        [candidate],
        configured_hint=configured_hint,
        now=now,
        device_hint=device_hint,
    )
    return ranked[0]


def rank_serial_console_candidates(
    candidates: list[dict[str, Any]],
    *,
    configured_hint: str | None = None,
    now: float | None = None,
    device_hint: str | None = None,
) -> list[dict[str, Any]]:
    now = now or time.time()
    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        candidate_copy = dict(candidate)
        rank, reasons = _rank_candidate(
            candidate_copy,
            configured_hint=configured_hint,
            now=now,
            device_hint=device_hint,
        )
        candidate_copy["rank"] = rank
        candidate_copy["selection_reasons"] = reasons
        candidate_copy["recommendation"] = _candidate_recommendation(candidate_copy)
        candidate_copy["confidence"] = _candidate_confidence(candidate_copy)
        ranked.append(candidate_copy)
    return sorted(ranked, key=lambda item: (int(item["rank"]), str(item["display_path"])))


def selectable_serial_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in candidates
        if serial_candidate_selectable(candidate)
    ]


def serial_candidate_selectable(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("exists")
        and candidate.get("readable")
        and candidate.get("writable")
        and not candidate.get("in_use")
        and isinstance(candidate.get("display_path"), str)
    )


def serial_baud_order(configured_baud: int | None, common_bauds: tuple[int, ...] = COMMON_SERIAL_BAUDS) -> tuple[int, ...]:
    values = [configured_baud, *common_bauds] if configured_baud else list(common_bauds)
    return tuple(dict.fromkeys(int(value) for value in values if value))


def _bounded_probe_candidates(
    candidates: list[dict[str, Any]],
    max_candidates: int | None,
) -> list[dict[str, Any]]:
    if max_candidates is None or max_candidates <= 0 or len(candidates) <= max_candidates:
        return candidates
    limited = candidates[:max_candidates]
    if any(candidate.get("path_type") == "ttyS" for candidate in limited):
        return limited
    first_ttys = next((candidate for candidate in candidates if candidate.get("path_type") == "ttyS"), None)
    if first_ttys is not None:
        return [*limited[:-1], first_ttys]
    return limited


def probe_serial_candidates(
    serial_module: Any,
    candidates: list[dict[str, Any]],
    *,
    options: SerialConsoleProbeOptions,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    baud_rates = serial_baud_order(options.configured_baud)
    wake_sequences = options.wake_sequences or SERIAL_WAKE_SEQUENCES
    candidates_to_probe = _bounded_probe_candidates(selectable_serial_candidates(candidates), options.max_candidates)
    for candidate in candidates_to_probe:
        for baud in baud_rates:
            attempt = probe_serial_candidate(serial_module, candidate, baud, options=options)
            attempts.append(attempt)
            classification = attempt.get("classification_detail", {})
            if _classification_is_selectable(classification, options.device_hint):
                selected = attempt
                return {
                    "selected": selected,
                    "attempts": attempts,
                    "bauds_tried": list(baud_rates),
                    "wake_sequences": [name for name, _payload in wake_sequences],
                    "probed_candidate_count": len(candidates_to_probe),
                    "skipped_candidate_count": max(len(selectable_serial_candidates(candidates)) - len(candidates_to_probe), 0),
                }
    return {
        "selected": selected,
        "attempts": attempts,
        "bauds_tried": list(baud_rates),
        "wake_sequences": [name for name, _payload in wake_sequences],
        "probed_candidate_count": len(candidates_to_probe),
        "skipped_candidate_count": max(len(selectable_serial_candidates(candidates)) - len(candidates_to_probe), 0),
    }


def probe_serial_candidate(
    serial_module: Any,
    candidate: dict[str, Any],
    baud: int,
    *,
    options: SerialConsoleProbeOptions,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    path = str(candidate["display_path"])
    wake_sequences = options.wake_sequences or SERIAL_WAKE_SEQUENCES
    try:
        with _serial_attempt_deadline(max(options.timeout_seconds * 2, 3.0)):
            with serial_module.Serial(
                port=path,
                baudrate=baud,
                timeout=max(min(options.timeout_seconds / 20, 0.08), 0.03),
                write_timeout=max(min(options.timeout_seconds, 1.0), 0.1),
            ) as conn:
                _safe_reset_input(conn)
                chunks: list[bytes] = []
                sequence_reads: list[dict[str, Any]] = []
                for sequence_name, payload in wake_sequences:
                    conn.write(payload)
                    read_bytes = _read_serial_bytes(
                        conn,
                        window=max(min(options.timeout_seconds / 8, 0.2), 0.08),
                        max_bytes=options.max_bytes - sum(len(chunk) for chunk in chunks),
                    )
                    chunks.append(read_bytes)
                    sequence_reads.append(
                        {
                            "sequence": sequence_name,
                            "wake_bytes_sent": len(payload),
                            "bytes_read": len(read_bytes),
                        }
                    )
                for index, window in enumerate(_read_windows(options.timeout_seconds), start=1):
                    read_bytes = _read_serial_bytes(
                        conn,
                        window=window,
                        max_bytes=options.max_bytes - sum(len(chunk) for chunk in chunks),
                    )
                    chunks.append(read_bytes)
                    sequence_reads.append(
                        {
                            "sequence": f"read-window-{index}",
                            "wake_bytes_sent": 0,
                            "bytes_read": len(read_bytes),
                        }
                    )
                    if sum(len(chunk) for chunk in chunks) >= options.max_bytes:
                        break

                raw = b"".join(chunks)
                text = raw.decode("utf-8", errors="replace")
                classification = classify_serial_console_text(text, device_hint=options.device_hint)
                return {
                    "path": path,
                    "baud": baud,
                    "started_at": started_at,
                    "status": "checked",
                    "bytes": len(raw),
                    "captured": bool(raw),
                    "classification": classification["classification"],
                    "classification_detail": classification,
                    "device_type": classification["device_type"],
                    "prompt_state": classification["prompt_state"],
                    "prompt_label": classification["prompt_label"],
                    "confidence": classification["confidence"],
                    "signals": classification["signals"],
                    "output_excerpt": redacted_printable_preview(text),
                    "raw_output_redacted": True,
                    "sequence_reads": sequence_reads,
                    "blocker": None
                    if _classification_is_selectable(classification, options.device_hint)
                    else _classification_blocker(classification),
                }
    except Exception as exc:  # pragma: no cover - hardware dependent
        classification = _serial_error_classification(exc)
        return {
            "path": path,
            "baud": baud,
            "started_at": started_at,
            "status": "blocked",
            "bytes": 0,
            "captured": False,
            "classification": classification["classification"],
            "classification_detail": classification,
            "device_type": "unknown",
            "prompt_state": classification["prompt_state"],
            "prompt_label": classification["prompt_label"],
            "confidence": "low",
            "signals": classification["signals"],
            "output_excerpt": "",
            "raw_output_redacted": True,
            "sequence_reads": [],
            "blocker": _serial_error_summary(exc),
        }


def classify_serial_console_text(text: str, *, device_hint: str | None = None) -> dict[str, Any]:
    if not text:
        return _classification(
            "no_bytes_read",
            "unknown",
            "no_output",
            "No console output",
            "low",
            [],
        )
    if _looks_unreadable(text):
        return _classification(
            "unreadable_gibberish",
            "unknown",
            "unreadable",
            "Unreadable console text",
            "low",
            ["replacement/control character ratio indicates wrong baud or line settings"],
        )

    lower = text.lower()
    hint = (device_hint or "").lower()

    if re.search(r"(?im)(?:^|\r|\n)\s*loader[-_a-z0-9]*>\s*$", text):
        return _classification("bootloader", "netapp", "loader_prompt", "NetApp LOADER prompt", "high", ["loader prompt"])
    if "boot menu" in lower or ("wipeconfig" in lower and "selection" in lower):
        return _classification("bootloader", "netapp", "boot_menu", "NetApp boot menu", "high", ["boot menu"])
    if "cluster setup wizard" in lower or "cluster setup" in lower:
        return _classification(
            "prompt_detected",
            "netapp",
            "cluster_setup_prompt",
            "NetApp cluster setup wizard",
            "high",
            ["cluster setup"],
        )
    if "ontap" in lower and ("login:" in lower or "username:" in lower):
        return _classification("login_prompt", "netapp", "login_required", "ONTAP login prompt", "high", ["ontap login"])
    if "sp login" in lower or "bmc login" in lower:
        return _classification("login_prompt", "netapp", "sp_bmc_login", "NetApp SP/BMC login", "medium", ["sp/bmc login"])
    if hint == "netapp" and ("login:" in lower or "username:" in lower):
        return _classification("login_prompt", "netapp", "login_required", "NetApp login prompt", "medium", ["login prompt"])
    if re.search(r"(?m)(?:^|\r|\n)\s*[A-Za-z0-9_.:-]+::\*?>\s*$", text):
        return _classification(
            "prompt_detected",
            "netapp",
            "existing_cluster_shell",
            "ONTAP cluster shell",
            "high",
            ["ontap shell prompt"],
        )
    if "starting ontap" in lower or "booting ontap" in lower or "press ctrl-c" in lower:
        return _classification("prompt_detected", "netapp", "booting", "ONTAP booting", "medium", ["ontap boot text"])

    if "user access verification" in lower:
        return _classification(
            "login_prompt",
            "cisco",
            "login_required",
            "Cisco user access verification",
            "high",
            ["user access verification"],
        )
    if "initial configuration dialog" in lower or "system configuration dialog" in lower:
        return _classification(
            "prompt_detected",
            "cisco",
            "setup_wizard",
            "Cisco initial configuration dialog",
            "high",
            ["initial configuration dialog"],
        )
    if re.search(r"(?im)(?:^|\r|\n)\s*rommon(?:\s+\d+)?\s*>\s*$", text) or re.search(
        r"(?im)(?:^|\r|\n)\s*switch:\s*$",
        text,
    ):
        return _classification("bootloader", "cisco", "rommon_bootloader", "Cisco bootloader", "high", ["rommon/switch bootloader"])
    if hint == "cisco" and ("username:" in lower or "login:" in lower or "password:" in lower):
        return _classification("login_prompt", "cisco", "login_required", "Cisco login prompt", "medium", ["login prompt"])
    if "username:" in lower or "password:" in lower:
        return _classification("login_prompt", "cisco", "login_required", "Console login prompt", "medium", ["login prompt"])

    prompt_match = re.search(r"(?m)(?:^|\r|\n)\s*([A-Za-z][A-Za-z0-9_.-]{0,63})([>#])\s*$", text)
    if prompt_match:
        suffix = prompt_match.group(2)
        return _classification(
            "prompt_detected",
            "cisco",
            "privileged_exec" if suffix == "#" else "exec",
            "Cisco privileged prompt" if suffix == "#" else "Cisco user prompt",
            "medium",
            ["hostname prompt"],
        )

    return _classification(
        "unknown",
        "unknown",
        "unknown_output",
        "Unclassified console output",
        "low",
        ["printable output did not match known Cisco or NetApp prompts"],
    )


def redacted_printable_preview(text: str, *, max_chars: int = MAX_PREVIEW_CHARS) -> str:
    if not text:
        return ""
    printable = "".join(ch if ch in "\n\r\t" or 32 <= ord(ch) <= 126 else "." for ch in text)
    lines = [line.strip() for line in printable.replace("\r", "\n").splitlines() if line.strip()]
    redacted = [_redact_console_line(line) for line in lines]
    return "\n".join(redacted)[:max_chars]


def _rank_candidate(
    candidate: dict[str, Any],
    *,
    configured_hint: str | None,
    now: float,
    device_hint: str | None,
) -> tuple[int, list[str]]:
    path = str(candidate.get("display_path") or candidate.get("path") or "")
    path_type = str(candidate.get("path_type") or _path_type(path))
    hinted = bool(configured_hint and path == configured_hint)
    recent_ttys = _fresh_ttys(candidate, now)
    reasons: list[str] = []

    if path_type == "by-id":
        rank = 0
        reasons.append("stable /dev/serial/by-id path")
    elif path_type in {"ttyUSB", "ttyACM"}:
        rank = 100
        reasons.append(f"{path_type} USB serial fallback")
    elif path_type == "ttyS":
        if recent_ttys:
            rank = 240 - min(_ttys_number(path), 20)
            reasons.append("ttyS device has a recent modified timestamp")
        elif hinted:
            rank = 260
            reasons.append("ttyS device matches configured hint")
        else:
            rank = 650
            reasons.append("older ttyS serial candidate")
    else:
        rank = 800
        reasons.append("non-standard configured serial candidate")

    if hinted:
        rank -= 40
        reasons.append("matches configured port hint")

    hint_delta, hint_reason = _device_hint_delta(candidate, device_hint)
    rank += hint_delta
    if hint_reason:
        reasons.append(hint_reason)

    if not candidate.get("exists"):
        rank += 2000
        reasons.append("path does not exist")
    if not candidate.get("readable") or not candidate.get("writable"):
        rank += 1000
        reasons.append("path is not readable/writable")
    if candidate.get("in_use"):
        rank += 600
        reasons.append("path appears to be in use")
    return rank, reasons


def _candidate_recommendation(candidate: dict[str, Any]) -> str:
    if not candidate.get("exists"):
        return "missing"
    if not candidate.get("readable") or not candidate.get("writable"):
        return "permission-blocked"
    if candidate.get("in_use"):
        return "in-use-deprioritized"
    path_type = candidate.get("path_type")
    if path_type == "by-id":
        return "preferred-stable-path"
    if path_type in {"ttyUSB", "ttyACM"}:
        return "usb-serial-candidate"
    if path_type == "ttyS":
        return "local-ttyS-candidate"
    return "serial-candidate"


def _candidate_confidence(candidate: dict[str, Any]) -> str:
    if not serial_candidate_selectable(candidate):
        return "low"
    path_type = candidate.get("path_type")
    if path_type == "by-id":
        return "high"
    if path_type in {"ttyUSB", "ttyACM"}:
        return "medium"
    if path_type == "ttyS" and _fresh_ttys(candidate, time.time()):
        return "medium"
    return "low"


def _device_hint_delta(candidate: dict[str, Any], device_hint: str | None) -> tuple[int, str | None]:
    if not device_hint:
        return 0, None
    haystack = _candidate_haystack(candidate)
    hint = device_hint.lower()
    if hint == "netapp":
        if any(item in haystack for item in NETAPP_NAME_HINTS):
            return -35, "candidate name matches NetApp serial hint"
        if any(item in haystack for item in CISCO_NAME_HINTS):
            return 60, "candidate name suggests Cisco, not NetApp"
    if hint == "cisco":
        if any(item in haystack for item in CISCO_NAME_HINTS):
            return -35, "candidate name matches Cisco serial hint"
        if any(item in haystack for item in NETAPP_NAME_HINTS):
            return 60, "candidate name suggests NetApp, not Cisco"
    if any(item in haystack for item in USB_SERIAL_NAME_HINTS):
        return -10, "candidate name matches common USB serial adapter"
    return 0, None


def _candidate_haystack(candidate: dict[str, Any]) -> str:
    parts = [
        str(candidate.get("display_path") or ""),
        str(candidate.get("resolved_path") or ""),
        str(candidate.get("label") or ""),
    ]
    udev = candidate.get("udevadm")
    if isinstance(udev, dict):
        props = udev.get("properties")
        if isinstance(props, dict):
            parts.extend(str(value) for value in props.values())
    return " ".join(parts).lower().replace("-", "_")


def _fresh_ttys(candidate: dict[str, Any], now: float) -> bool:
    if candidate.get("path_type") != "ttyS":
        return False
    age = candidate.get("modified_age_seconds")
    if isinstance(age, (int, float)):
        return age <= RECENT_TTYS_SECONDS
    modified = candidate.get("modified_time")
    if not isinstance(modified, str):
        return False
    try:
        parsed = datetime.fromisoformat(modified)
    except ValueError:
        return False
    return now - parsed.timestamp() <= RECENT_TTYS_SECONDS


def _path_type(path: str) -> str:
    name = Path(path).name
    if path.startswith("/dev/serial/by-id/") or "/serial/by-id/" in path:
        return "by-id"
    if name.startswith("ttyUSB"):
        return "ttyUSB"
    if name.startswith("ttyACM"):
        return "ttyACM"
    if name.startswith("ttyS"):
        return "ttyS"
    return "other"


def _ttys_number(path: str) -> int:
    match = re.match(r"ttyS(\d+)$", Path(path).name)
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0


def _stat_path(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def _owner_name(stat_result: os.stat_result) -> str:
    try:
        return pwd.getpwuid(stat_result.st_uid).pw_name
    except KeyError:
        return str(stat_result.st_uid)


def _group_name(stat_result: os.stat_result) -> str:
    try:
        return grp.getgrgid(stat_result.st_gid).gr_name
    except KeyError:
        return str(stat_result.st_gid)


def _mode_string(stat_result: os.stat_result) -> str:
    return stat.filemode(stat_result.st_mode)


def _iso_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


def _candidate_label(path: str, resolved_path: str | None) -> str:
    label = Path(path).name.replace("_", " ")
    if resolved_path and resolved_path != path:
        return f"{label} -> {resolved_path}"
    return label


def _in_use_state(path: str) -> dict[str, Any]:
    checked: list[str] = []
    unavailable: list[str] = []
    pids: list[int] = []
    for tool, args in (("fuser", [path]), ("lsof", ["-t", path])):
        executable = which(tool)
        if executable is None:
            unavailable.append(tool)
            continue
        checked.append(tool)
        try:
            result = subprocess.run(
                [executable, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
                timeout=0.2,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            pids.extend(_parse_pids(result.stdout))
    if pids:
        return {"state": "in_use", "checked_with": checked, "unavailable_tools": unavailable, "pids": sorted(set(pids))}
    if checked:
        return {"state": "not_in_use", "checked_with": checked, "unavailable_tools": unavailable, "pids": []}
    return {"state": "unavailable", "checked_with": [], "unavailable_tools": unavailable, "pids": []}


def _not_in_use_state(reason: str) -> dict[str, Any]:
    return {"state": "not_in_use", "checked_with": [], "unavailable_tools": [], "pids": [], "reason": reason}


def _parse_pids(value: str) -> list[int]:
    pids: list[int] = []
    for item in re.findall(r"\b\d+\b", value):
        try:
            pids.append(int(item))
        except ValueError:
            continue
    return pids


def _udevadm_info(path: str) -> dict[str, Any]:
    executable = which("udevadm")
    if executable is None:
        return _tool_unavailable("udevadm-not-found")
    try:
        result = subprocess.run(
            [executable, "info", "--query=property", "--name", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=0.5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "status": "error", "reason": _short_text(str(exc)), "properties": {}, "raw_redacted": True}
    if result.returncode != 0:
        return {
            "available": True,
            "status": "error",
            "reason": _short_text(result.stderr or result.stdout),
            "properties": {},
            "raw_redacted": True,
        }
    properties = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in SAFE_UDEV_KEYS:
            properties[key] = _short_text(value, max_chars=240)
    return {"available": True, "status": "ok", "properties": properties, "raw_redacted": True}


def _setserial_info(path: str) -> dict[str, Any]:
    executable = which("setserial")
    if executable is None:
        return _tool_unavailable("setserial-not-found")
    try:
        result = subprocess.run(
            [executable, "-g", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=0.5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "status": "error", "summary": _short_text(str(exc))}
    output = result.stdout.strip() or result.stderr.strip()
    status_text = "ok" if result.returncode == 0 else "not_supported"
    return {"available": True, "status": status_text, "summary": _short_text(output)}


def _read_dmesg() -> dict[str, Any]:
    executable = which("dmesg")
    if executable is None:
        return _tool_unavailable("dmesg-not-found")
    commands = (
        [executable, "--ctime", "--color=never"],
        [executable],
    )
    last_result: subprocess.CompletedProcess[str] | None = None
    for command in commands:
        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": True, "status": "error", "reason": _short_text(str(exc)), "lines": []}
        last_result = result
        if result.returncode == 0:
            return {"available": True, "status": "ok", "lines": result.stdout.splitlines()[-400:]}
    reason = _short_text((last_result.stderr or last_result.stdout) if last_result else "dmesg unavailable")
    return {"available": True, "status": "unavailable", "reason": reason, "lines": []}


def _dmesg_clues(path: str, resolved_path: str | None, dmesg: dict[str, Any]) -> dict[str, Any]:
    if dmesg.get("status") != "ok":
        return {key: value for key, value in dmesg.items() if key != "lines"}
    identifiers = {Path(path).name.lower()}
    if resolved_path:
        identifiers.add(Path(resolved_path).name.lower())
    lines = []
    for line in dmesg.get("lines", []):
        lowered = str(line).lower()
        if any(identifier and identifier in lowered for identifier in identifiers):
            lines.append(_short_text(str(line), max_chars=300))
    return {"available": True, "status": "ok", "clues": lines[-20:]}


def _tool_unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "status": "unavailable", "reason": reason}


def _read_windows(timeout_seconds: float) -> tuple[float, float, float]:
    base = max(min(timeout_seconds / 8, 0.2), 0.08)
    return (base, max(base, min(timeout_seconds / 4, 0.35)), max(base, min(timeout_seconds / 2, 0.6)))


def _read_serial_bytes(conn: Any, *, window: float, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        return b""
    deadline = time.monotonic() + max(window, 0.05)
    chunks: list[bytes] = []
    captured = 0
    while time.monotonic() < deadline and captured < max_bytes:
        try:
            waiting = int(getattr(conn, "in_waiting", 0) or 0)
            read_size = min(waiting or 1, max_bytes - captured)
            chunk = conn.read(read_size)
        except Exception:
            break
        if chunk:
            chunks.append(chunk)
            captured += len(chunk)
            continue
        time.sleep(0.03)
    return b"".join(chunks)


def _safe_reset_input(conn: Any) -> None:
    try:
        if hasattr(conn, "reset_input_buffer"):
            conn.reset_input_buffer()
    except Exception:
        return


def _safe_flush(conn: Any) -> None:
    try:
        if hasattr(conn, "flush"):
            conn.flush()
    except Exception:
        return


def _classification_is_selectable(classification: object, device_hint: str | None) -> bool:
    if not isinstance(classification, dict):
        return False
    if classification.get("classification") not in {"prompt_detected", "login_prompt", "bootloader"}:
        return False
    if device_hint and classification.get("device_type") not in {device_hint, "unknown"}:
        return False
    return True


def _classification_blocker(classification: dict[str, Any]) -> str:
    value = classification.get("classification")
    if value == "no_bytes_read":
        return "No bytes were read from this serial candidate and baud."
    if value == "unreadable_gibberish":
        return "Bytes were read but look like wrong-baud or unreadable console text."
    if value == "unknown":
        return "Console output was captured but did not match known Cisco or NetApp prompts."
    return "Console output did not match the requested device type."


def _serial_error_classification(exc: Exception) -> dict[str, Any]:
    text = str(exc).lower()
    if "permission" in text or "access denied" in text:
        return _classification("permission_denied", "unknown", "permission_denied", "Permission denied", "low", ["serial open denied"])
    if "busy" in text or "in use" in text or "resource temporarily unavailable" in text:
        return _classification("port_in_use", "unknown", "port_in_use", "Port in use", "low", ["serial open busy"])
    if "no such file" in text or "could not open port" in text:
        return _classification("missing_port", "unknown", "missing_port", "Missing serial port", "low", ["serial path missing"])
    return _classification("serial_open_failed", "unknown", "serial_open_failed", "Serial open failed", "low", ["serial open failed"])


def _serial_error_summary(exc: Exception) -> str:
    detail = str(exc).strip()
    if not detail:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}: {_short_text(detail)}"


@contextmanager
def _serial_attempt_deadline(seconds: float):
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _timeout(_signum, _frame) -> None:  # noqa: ANN001
        raise TimeoutError("serial probe attempt timed out")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, max(seconds, 0.5))
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous_handler)


def _classification(
    classification: str,
    device_type: str,
    prompt_state: str,
    prompt_label: str,
    confidence: str,
    signals: list[str],
) -> dict[str, Any]:
    return {
        "classification": classification,
        "device_type": device_type,
        "prompt_state": prompt_state,
        "prompt_label": prompt_label,
        "confidence": confidence,
        "signals": signals,
    }


def _looks_unreadable(text: str) -> bool:
    replacement_count = text.count("\ufffd")
    control_count = sum(1 for char in text if ord(char) < 32 and char not in "\r\n\t")
    visible_count = sum(1 for char in text if char.isprintable() and not char.isspace())
    total = max(len(text), 1)
    return (replacement_count + control_count) / total > 0.2 or (total >= 8 and visible_count == 0)


def _redact_console_line(line: str) -> str:
    lowered = line.lower()
    if "password:" in lowered:
        return "password prompt"
    if "username:" in lowered:
        return "username prompt"
    if re.search(r"\blogin:\s*$", lowered):
        return "login prompt"
    if "initial configuration dialog" in lowered or "system configuration dialog" in lowered:
        return "initial configuration dialog"
    if "cluster setup" in lowered:
        return "cluster setup prompt"
    if re.match(r"^\s*loader[-_a-z0-9]*>\s*$", line, re.IGNORECASE):
        return "LOADER>"
    if re.match(r"^\s*[A-Za-z0-9_.:-]+::\*?>\s*$", line):
        return "ONTAP::>"
    if re.match(r"^\s*[A-Za-z][A-Za-z0-9_.-]{0,63}[>#]\s*$", line):
        return f"DEVICE{line.rstrip()[-1]}"
    return re.sub(
        r"(?i)\b(password|token|secret|authorization|cookie)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        line,
    )


def _short_text(value: str, *, max_chars: int = 180) -> str:
    cleaned = " ".join(value.split())
    return cleaned[:max_chars]
