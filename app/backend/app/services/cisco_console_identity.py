from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.lab_safety import current_lab_safety
from app.services.serial_console_discovery import classify_serial_console_text

PROVIDER_ID = "cisco-console"
ALLOWED_EXPLICIT_IDENTITY_BAUDS = (9600, 115200)
MAX_IDENTITY_READ_BYTES = 16_384
MAX_IDENTITY_READ_SECONDS = 20.0
MIN_COMMAND_READ_SECONDS = 2.0
PASSIVE_READ_SECONDS = 0.5
PROMPT_READ_SECONDS = 2.0
TERMINAL_QUIET_SECONDS = 0.3
INITIAL_PROMPT_BYTES = b"\r\n"
SHOW_VERSION_BYTES = b"show version\r\n"
SHOW_INVENTORY_BYTES = b"show inventory\r\n"
IDENTITY_NOT_ATTEMPTED = [
    "other serial ports",
    "other baud rates",
    "credentials or enable secrets",
    "non-empty setup-wizard answers",
    "Ctrl-C, Ctrl-Z, break, DTR/RTS toggles after open, application-issued input-buffer resets, or pager keystrokes",
    "configuration, save, reload, erase, or other write commands",
]
CANDIDATE_WARNINGS = [
    "Baud and USB-adapter metadata are selection hints only; neither proves device identity."
]
VERIFY_WARNINGS = [
    "Opening a serial port through the operating-system driver may clear bytes that "
    "were buffered before this session; the application does not issue an additional "
    "input-buffer reset.",
    "Explicit Verify may send one blank CR/LF to request a fresh prompt. If a device is "
    "already waiting for blank or default input, that newline may advance it; verification "
    "stops when a wizard, login, configuration, boot, pager, or non-Cisco state is detected.",
    *CANDIDATE_WARNINGS,
]

_CISCO_SIGNATURE_PATTERNS = (
    re.compile(r"\bCisco IOS(?: XE)? Software\b", re.IGNORECASE),
    re.compile(r"\bCisco Internetwork Operating System Software\b", re.IGNORECASE),
    re.compile(r"\bCisco Systems,\s*Inc\.", re.IGNORECASE),
)
_SAFE_EXEC_PROMPT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}([>#])$")
_CONFIG_PROMPT_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_.-]{0,63}\(config[^)]*\)[#>]$",
    re.IGNORECASE,
)
_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|[@-_])")
_SERIAL_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{4,80}$")
_MODEL_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/+()-]{2,120}$")


@dataclass(frozen=True)
class _CandidateRecord:
    public: dict[str, Any]
    binding_ready: bool
    raw_port: str


@dataclass(frozen=True)
class _ConsoleClassification:
    detected_vendor: str
    prompt_state: str
    cisco_signature_present: bool
    safe_cisco_exec: bool


def list_cisco_console_identity_candidates(
    *,
    port_enumerator: Callable[[], Iterable[Any]] | None = None,
) -> dict[str, Any]:
    checked_at = _checked_at()
    records, enumeration_error = _enumerate_candidate_records(port_enumerator)
    if enumeration_error:
        return {
            "provider_id": PROVIDER_ID,
            "status": "blocked",
            "message": "Serial-port metadata could not be enumerated safely.",
            "checked_at": checked_at,
            "candidates": [],
            "allowed_bauds": list(ALLOWED_EXPLICIT_IDENTITY_BAUDS),
            "baud_is_identity_proof": False,
            "raw_identifiers_redacted": True,
            "blockers": [enumeration_error],
            "warnings": [],
        }

    candidates = [record.public for record in records]
    return {
        "provider_id": PROVIDER_ID,
        "status": "ready" if candidates else "blocked",
        "message": (
            "Select one exact serial port and one baud to verify its console identity."
            if candidates
            else "No present local serial ports were reported by the operating system."
        ),
        "checked_at": checked_at,
        "candidates": candidates,
        "allowed_bauds": list(ALLOWED_EXPLICIT_IDENTITY_BAUDS),
        "baud_is_identity_proof": False,
        "raw_identifiers_redacted": True,
        "blockers": [] if candidates else ["Connect the intended USB serial adapter, then refresh."],
        "warnings": list(CANDIDATE_WARNINGS),
    }


def verify_cisco_console_identity(
    *,
    port: str,
    baud: int,
    candidate_fingerprint: str,
    port_enumerator: Callable[[], Iterable[Any]] | None = None,
    connection_opener: Callable[[str, int], Any] | None = None,
    provider_mode: str | None = None,
    read_window_seconds: float | None = None,
) -> dict[str, Any]:
    result = _base_verification_result(
        port=port,
        baud=baud,
        candidate_fingerprint=candidate_fingerprint,
    )
    if baud not in ALLOWED_EXPLICIT_IDENTITY_BAUDS:
        return _blocked_result(
            result,
            f"Baud must be one of: {', '.join(str(item) for item in ALLOWED_EXPLICIT_IDENTITY_BAUDS)}.",
        )

    records, enumeration_error = _enumerate_candidate_records(port_enumerator)
    if enumeration_error:
        return _blocked_result(result, enumeration_error)
    matching_port = [record for record in records if record.public["port"] == port]
    selected = next(
        (
            record
            for record in matching_port
            if record.public["candidate_fingerprint"] == candidate_fingerprint
        ),
        None,
    )
    if not matching_port:
        return _blocked_result(
            result,
            "The exact selected serial port is no longer present; no port was opened.",
        )
    if selected is None:
        return _blocked_result(
            result,
            "The selected serial port fingerprint changed; no port was opened.",
        )
    if not selected.binding_ready:
        return _blocked_result(
            result,
            "The selected serial adapter lacks a stable serial, USB location, or by-id binding; "
            "identity verification is blocked before opening it.",
        )

    contact_blockers = _readonly_contact_blockers(provider_mode or settings.provider_mode)
    if contact_blockers:
        return _blocked_result(result, *contact_blockers)

    opener = connection_opener or _open_explicit_serial_connection
    connection: Any | None = None
    try:
        connection = opener(selected.raw_port, baud)
    except Exception as exc:  # noqa: BLE001 - hardware adapters fail closed
        return _blocked_result(result, _serial_open_blocker(exc))

    commands_attempted: list[str] = []
    try:
        passive_text = _read_serial_text(
            connection,
            baud=baud,
            hard_deadline_seconds=(
                read_window_seconds
                if read_window_seconds is not None
                else PASSIVE_READ_SECONDS
            ),
        )
        classification = _classify_console_identity(passive_text)
        prompted_text: str | None = None

        if _may_request_fresh_prompt(passive_text, classification):
            connection.write(INITIAL_PROMPT_BYTES)
            prompted_text = _read_serial_text(
                connection,
                baud=baud,
                hard_deadline_seconds=(
                    read_window_seconds
                    if read_window_seconds is not None
                    else PROMPT_READ_SECONDS
                ),
            )
            classification = _classify_console_identity(prompted_text)

        result["detected_vendor"] = classification.detected_vendor
        result["prompt_state"] = classification.prompt_state
        if classification.detected_vendor == "netapp":
            return _blocked_result(
                result,
                "The selected console was positively classified as NetApp; Cisco show commands "
                "were not sent.",
            )
        if classification.cisco_signature_present and not classification.safe_cisco_exec:
            return _blocked_result(
                result,
                "Cisco was detected, but the console is not at a safe user or privileged exec "
                "prompt; no show command was sent.",
            )
        if classification.safe_cisco_exec:
            result["verification_method"] = "signed-exec"
        elif prompted_text is not None and _is_safe_show_version_discriminator(
            prompted_text
        ):
            result["verification_method"] = "show-version-discriminator"
        else:
            return _blocked_result(
                result,
                "The fresh console observation did not provide a Cisco signature or meet "
                "the narrow safe-exec guard for one fixed show version discriminator.",
            )

        connection.write(SHOW_VERSION_BYTES)
        commands_attempted.append("show version")
        version_output = _read_serial_text(
            connection,
            baud=baud,
            hard_deadline_seconds=read_window_seconds,
        )
        result["commands_attempted"] = commands_attempted
        if _contains_pager_prompt(version_output):
            return _blocked_result(
                result,
                "The fixed show version response entered a pager; no pager keystroke or "
                "additional command was sent.",
            )
        if not _contains_high_confidence_cisco_signature(version_output):
            return _blocked_result(
                result,
                "The fixed show version response did not confirm Cisco IOS/IOS XE; "
                "identity remains unverified.",
            )
        if _safe_exec_prompt_state(version_output) not in {
            "exec",
            "privileged-exec",
        }:
            return _blocked_result(
                result,
                "The fixed show version response did not return to a current safe exec "
                "prompt; the output may be incomplete and was not accepted.",
            )

        version_models, software_version, version_serials = _parse_show_version(
            version_output
        )
        model_values = list(version_models)
        serial_values = list(version_serials)
        if (
            (not model_values or not serial_values)
            or _contains_stack_indicator(version_output)
        ):
            connection.write(SHOW_INVENTORY_BYTES)
            commands_attempted.append("show inventory")
            inventory_output = _read_serial_text(
                connection,
                baud=baud,
                hard_deadline_seconds=read_window_seconds,
            )
            if _contains_pager_prompt(inventory_output):
                result["commands_attempted"] = commands_attempted
                return _blocked_result(
                    result,
                    "The fixed show inventory response entered a pager; no pager keystroke "
                    "or additional command was sent.",
                )
            if _safe_exec_prompt_state(inventory_output) not in {
                "exec",
                "privileged-exec",
            }:
                result["commands_attempted"] = commands_attempted
                return _blocked_result(
                    result,
                    "The fixed show inventory response did not return to a current safe exec "
                    "prompt; the output may be incomplete and was not accepted.",
                )
            inventory_models, inventory_serials = _parse_show_inventory(inventory_output)
            model_values = _unique_tokens([*model_values, *inventory_models])
            serial_values = _unique_tokens([*serial_values, *inventory_serials])

        result["commands_attempted"] = commands_attempted
        if len(model_values) > 1 or len(serial_values) > 1:
            return _blocked_result(
                result,
                "Multiple Cisco chassis or stack identities were observed; an operator must "
                "select and bind the intended physical switch before verification can pass.",
            )
        model = model_values[0] if model_values else None
        chassis_serial = serial_values[0] if serial_values else None
        result["model"] = model
        result["software_version"] = software_version
        result["serial_fingerprint"] = (
            _chassis_serial_fingerprint(chassis_serial) if chassis_serial else None
        )
        blockers: list[str] = []
        if not model:
            blockers.append("Cisco chassis model could not be parsed from the fixed read-only output.")
        if not chassis_serial:
            blockers.append(
                "Cisco chassis serial could not be fingerprinted from the fixed read-only output."
            )
        if blockers:
            return _blocked_result(result, *blockers)

        result.update(
            {
                "status": "ready",
                "message": (
                    "Cisco console identity was verified on the exact selected port and baud."
                ),
                "detected_vendor": "cisco",
                "identity_verified": True,
                "blockers": [],
            }
        )
        return result
    except Exception as exc:  # noqa: BLE001 - serial I/O must fail closed
        return _blocked_result(result, _serial_io_blocker(exc))
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _enumerate_candidate_records(
    port_enumerator: Callable[[], Iterable[Any]] | None,
) -> tuple[list[_CandidateRecord], str | None]:
    enumerator = port_enumerator or _default_port_enumerator
    try:
        port_infos = list(enumerator())
    except Exception as exc:  # noqa: BLE001 - discovery must fail closed
        return [], (
            "Operating-system serial metadata enumeration failed "
            f"({exc.__class__.__name__}); no port was opened."
        )

    records: list[_CandidateRecord] = []
    seen: set[str] = set()
    for port_info in port_infos:
        record = _candidate_record(port_info)
        if record is None:
            continue
        port = str(record.public["port"])
        if port in seen:
            continue
        seen.add(port)
        records.append(record)
    records.sort(key=lambda record: _port_sort_key(str(record.public["port"])))
    return records, None


def _default_port_enumerator() -> Iterable[Any]:
    from serial.tools import list_ports  # type: ignore[import-untyped]

    return list_ports.comports()


def _candidate_record(port_info: Any) -> _CandidateRecord | None:
    raw_port = _clean_text(getattr(port_info, "device", None), max_length=260)
    if not raw_port:
        return None
    raw_hwid = str(getattr(port_info, "hwid", "") or "").strip()
    raw_serial = _port_serial(port_info, raw_hwid)
    raw_location = _port_location(port_info, raw_hwid)
    vid, pid = _port_vid_pid(port_info, raw_hwid)
    raw_description = str(getattr(port_info, "description", "") or "").strip()
    raw_manufacturer = str(getattr(port_info, "manufacturer", "") or "").strip()
    raw_product = str(getattr(port_info, "product", "") or "").strip()
    raw_interface = str(getattr(port_info, "interface", "") or "").strip()
    redaction_values = [raw_serial] if raw_serial else []

    description = _safe_metadata_text(
        raw_description or raw_product or "Serial port",
        redaction_values,
        max_length=160,
    )
    manufacturer = _safe_metadata_text(
        raw_manufacturer,
        redaction_values,
        max_length=120,
    )
    location = _safe_metadata_text(
        raw_location,
        redaction_values,
        max_length=160,
    )
    port = _safe_port_label(raw_port, raw_serial)
    vid_pid = (
        f"{vid:04X}:{pid:04X}"
        if isinstance(vid, int) and isinstance(pid, int)
        else None
    )
    fingerprint_material = {
        "port": _normalized_port_for_fingerprint(raw_port),
        "description": raw_description,
        "manufacturer": raw_manufacturer,
        "product": raw_product,
        "interface": raw_interface,
        "hwid": raw_hwid,
        "vid": vid,
        "pid": pid,
        "serial_number": raw_serial,
        "location": raw_location,
    }
    fingerprint = _sha256_json("cisco-console-candidate-v1", fingerprint_material)
    hint_text = " ".join(
        item
        for item in (
            raw_description,
            raw_manufacturer,
            raw_product,
            raw_interface,
        )
        if item
    ).lower()
    transport = (
        "usb-serial"
        if vid_pid or "usb" in hint_text or raw_location
        else "serial"
    )
    recommended_bauds = (
        [115200, 9600]
        if "netapp" in hint_text or "mcp2221" in hint_text
        else [9600, 115200]
    )
    configured_port = str(settings.cisco_console_port or "")
    recommended = bool(
        (configured_port and configured_port == raw_port)
        or "cisco" in hint_text
    )
    binding_ready = bool(
        raw_serial
        or raw_location
        or raw_port.startswith("/dev/serial/by-id/")
    )
    return _CandidateRecord(
        public={
            "port": port,
            "candidate_fingerprint": fingerprint,
            "description": description,
            "manufacturer": manufacturer,
            "transport": transport,
            "vid_pid": vid_pid,
            "usb_location": location,
            "serial_present": bool(raw_serial),
            "recommended_bauds": recommended_bauds,
            "recommended": recommended,
        },
        binding_ready=binding_ready,
        raw_port=raw_port,
    )


def _port_serial(port_info: Any, hwid: str) -> str | None:
    serial_value = _clean_text(getattr(port_info, "serial_number", None), max_length=160)
    if serial_value:
        return serial_value
    match = re.search(r"(?:^|\s)SER=([^\s]+)", hwid, re.IGNORECASE)
    return _clean_text(match.group(1), max_length=160) if match else None


def _port_location(port_info: Any, hwid: str) -> str | None:
    location = _clean_text(getattr(port_info, "location", None), max_length=160)
    if location:
        return location
    match = re.search(r"(?:^|\s)LOCATION=([^\s]+)", hwid, re.IGNORECASE)
    return _clean_text(match.group(1), max_length=160) if match else None


def _port_vid_pid(port_info: Any, hwid: str) -> tuple[int | None, int | None]:
    vid = getattr(port_info, "vid", None)
    pid = getattr(port_info, "pid", None)
    if isinstance(vid, int) and isinstance(pid, int):
        return vid, pid
    match = re.search(
        r"VID:PID=([0-9A-F]{4}):([0-9A-F]{4})",
        hwid,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    return int(match.group(1), 16), int(match.group(2), 16)


def _readonly_contact_blockers(provider_mode: str) -> list[str]:
    if provider_mode not in REAL_CONTACT_MODES:
        return [
            "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite "
            "before opening the explicitly selected console."
        ]
    safety = current_lab_safety()
    policy = current_lab_action_policy(provider_mode)
    readonly_allowed = (
        safety.readonly_allowed
        if provider_mode == "local-readonly"
        else policy.readonly_allowed
    )
    if readonly_allowed:
        return []
    return (
        list(safety.blockers)
        if provider_mode == "local-readonly"
        else list(policy.readonly_blockers())
    )


def _open_explicit_serial_connection(port: str, baud: int) -> Any:
    import serial  # type: ignore[import-untyped]

    connection = serial.Serial(
        port=None,
        baudrate=baud,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=0.5,
        xonxoff=False,
        rtscts=False,
        dsrdtr=False,
    )
    connection.dtr = False
    connection.rts = False
    connection.port = port
    try:
        connection.open()
    except Exception:
        try:
            connection.close()
        except Exception:
            pass
        raise
    return connection


def _read_serial_text(
    connection: Any,
    *,
    baud: int,
    hard_deadline_seconds: float | None,
    max_bytes: int = MAX_IDENTITY_READ_BYTES,
    quiet_seconds: float = TERMINAL_QUIET_SECONDS,
) -> str:
    hard_window = (
        _identity_hard_deadline_seconds(baud, max_bytes=max_bytes)
        if hard_deadline_seconds is None
        else max(hard_deadline_seconds, 0.0)
    )
    deadline = time.monotonic() + hard_window
    chunks: list[bytes] = []
    captured = 0
    last_data_at: float | None = None
    first_read = True
    while first_read or time.monotonic() <= deadline:
        first_read = False
        waiting = int(getattr(connection, "in_waiting", 0) or 0)
        size = min(max(waiting, 1), max_bytes - captured)
        if size <= 0:
            break
        chunk = connection.read(size)
        if chunk:
            chunks.append(bytes(chunk))
            captured += len(chunk)
            last_data_at = time.monotonic()
            if captured >= max_bytes:
                break
            continue
        now = time.monotonic()
        observed = b"".join(chunks).decode("utf-8", errors="replace")
        if (
            last_data_at is not None
            and _has_current_terminal_state(observed)
            and now - last_data_at >= max(quiet_seconds, 0.0)
        ):
            break
        if now >= deadline:
            break
        time.sleep(0.01)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _identity_hard_deadline_seconds(
    baud: int,
    *,
    max_bytes: int = MAX_IDENTITY_READ_BYTES,
) -> float:
    wire_seconds = (max(max_bytes, 1) * 10) / max(baud, 1)
    return min(
        MAX_IDENTITY_READ_SECONDS,
        max(MIN_COMMAND_READ_SECONDS, wire_seconds + 1.0),
    )


def _has_current_terminal_state(text: str) -> bool:
    if _contains_pager_prompt(text):
        return True
    state = _safe_exec_prompt_state(text)
    return state in {
        "exec",
        "privileged-exec",
        "config-mode",
        "setup-wizard",
        "login-required",
        "rommon-bootloader",
    }


def _classify_console_identity(text: str) -> _ConsoleClassification:
    shared = classify_serial_console_text(text)
    shared_vendor = str(shared.get("device_type") or "unknown")
    current_prompt_state = _safe_exec_prompt_state(text)
    prompt_state = current_prompt_state or "unknown"
    if shared_vendor == "netapp" or _contains_netapp_signature(text):
        return _ConsoleClassification(
            detected_vendor="netapp",
            prompt_state=prompt_state,
            cisco_signature_present=False,
            safe_cisco_exec=False,
        )
    cisco_signature = _contains_high_confidence_cisco_signature(text)
    safe_exec = cisco_signature and current_prompt_state in {
        "exec",
        "privileged-exec",
    }
    return _ConsoleClassification(
        detected_vendor="cisco" if cisco_signature else "unknown",
        prompt_state=prompt_state,
        cisco_signature_present=cisco_signature,
        safe_cisco_exec=safe_exec,
    )


def _may_request_fresh_prompt(
    observation: str,
    classification: _ConsoleClassification,
) -> bool:
    if classification.detected_vendor == "netapp":
        return False
    if classification.cisco_signature_present:
        return False
    if _observation_forbids_show_discriminator(observation):
        return False
    return classification.prompt_state in {"unknown", "exec", "privileged-exec"}


def _is_safe_show_version_discriminator(observation: str) -> bool:
    if _observation_forbids_show_discriminator(observation):
        return False
    lines = _meaningful_lines(observation)
    if len(lines) != 1:
        return False
    if not _SAFE_EXEC_PROMPT_RE.fullmatch(lines[0]):
        return False
    hostname = lines[0][:-1].lower()
    return hostname not in {
        "root",
        "bash",
        "sh",
        "shell",
        "linux",
        "ubuntu",
        "esxi",
        "node",
        "ontap",
        "loader",
        "sp",
        "bmc",
    }


def _observation_forbids_show_discriminator(observation: str) -> bool:
    lower = observation.lower()
    if _contains_netapp_signature(observation) or _contains_pager_prompt(observation):
        return True
    forbidden_patterns = (
        r"\buser access verification\b",
        r"(?:username|login|password)\s*:",
        r"\binitial configuration dialog\b",
        r"\bsystem configuration dialog\b",
        r"\[yes/no\]",
        r"\(config[^)]*\)",
        r"\brommon\b",
        r"(?m)^\s*switch\s*:\s*$",
        r"\bloader\b",
        r"\bboot(?:ing|loader)?\b",
        r"\buefi\b",
        r"\bshell\b",
    )
    return any(re.search(pattern, lower) for pattern in forbidden_patterns)


def _contains_high_confidence_cisco_signature(text: str) -> bool:
    return any(pattern.search(text) for pattern in _CISCO_SIGNATURE_PATTERNS)


def _contains_netapp_signature(text: str) -> bool:
    lower = text.lower()
    return bool(
        "netapp" in lower
        or "ontap" in lower
        or "cluster setup" in lower
        or "service processor" in lower
        or re.search(r"\b(?:aff|fas)[-_ ]?[a-z0-9]{2,}\b", text, re.IGNORECASE)
        or re.search(r"\b(?:sp|bmc)\s+login\s*:", text, re.IGNORECASE)
        or re.search(r"(?im)(?:^|\r|\n)\s*loader[-_a-z0-9]*>\s*$", text)
        or re.search(r"(?m)(?:^|\r|\n)\s*[A-Za-z0-9_.:-]+::\*?>\s*$", text)
    )


def _safe_exec_prompt_state(text: str) -> str | None:
    last_line = _last_meaningful_line(text)
    if not last_line:
        return None
    lower = last_line.lower()
    if _CONFIG_PROMPT_RE.fullmatch(last_line):
        return "config-mode"
    if (
        "initial configuration dialog" in lower
        or "system configuration dialog" in lower
        or "[yes/no]" in lower
    ):
        return "setup-wizard"
    if re.search(r"(?:username|login|password)\s*:\s*$", lower):
        return "login-required"
    if re.fullmatch(r"(?i)rommon(?:\s+\d+)?\s*>", last_line) or re.fullmatch(
        r"(?i)switch\s*:",
        last_line,
    ):
        return "rommon-bootloader"
    prompt = _SAFE_EXEC_PROMPT_RE.fullmatch(last_line)
    if not prompt:
        return None
    return "privileged-exec" if prompt.group(1) == "#" else "exec"


def _last_meaningful_line(text: str) -> str:
    lines = _meaningful_lines(text)
    return lines[-1] if lines else ""


def _meaningful_lines(text: str) -> list[str]:
    cleaned = _ANSI_ESCAPE_RE.sub("", text)
    return [
        line.strip()
        for line in cleaned.replace("\r", "\n").splitlines()
        if line.strip()
    ]


def _contains_pager_prompt(text: str) -> bool:
    lower = text.lower()
    return "--more--" in lower or bool(
        re.search(r"(?im)(?:^|\r|\n)\s*more\s*:\s*$", text)
    )


def _contains_stack_indicator(text: str) -> bool:
    return bool(
        re.search(r"(?im)^\s*Switch\s+Ports\s+Model\b", text)
        or re.search(r"\bStackWise\b", text, re.IGNORECASE)
        or re.search(r"\b(?:stack member|number of members)\b", text, re.IGNORECASE)
    )


def _parse_show_version(
    output: str,
) -> tuple[list[str], str | None, list[str]]:
    models = _all_safe_tokens(
        output,
        (
            r"(?im)^Model Number\s*:\s*(\S+)",
            r"(?im)^cisco\s+(\S+)\s+\(.+\)\s+processor",
            r"(?im)^cisco\s+(\S+)\s+processor",
        ),
        _MODEL_TOKEN_RE,
    )
    version = _first_safe_token(
        output,
        (
            r"(?im)^Cisco IOS XE Software[^,\n]*,\s*Version\s+([^,\s]+)",
            r"(?im)^Cisco IOS Software[^,\n]*,\s*Version\s+([^,\s]+)",
            r"(?im)^Cisco Internetwork Operating System Software.+Version\s+([^,\s]+)",
        ),
        _MODEL_TOKEN_RE,
    )
    serials = _all_safe_tokens(
        output,
        (
            r"(?im)^System Serial Number\s*:\s*(\S+)",
            r"(?im)^Processor board ID\s+(\S+)",
        ),
        _SERIAL_TOKEN_RE,
    )
    return models, version, serials


def _parse_show_inventory(output: str) -> tuple[list[str], list[str]]:
    chassis_blocks = list(
        re.finditer(
            r'(?is)NAME:\s*"[^"]*(?:chassis|switch)[^"]*".{0,800}?'
            r"PID:\s*([^,\s]+)\s*,\s*VID:[^,\r\n]*,\s*SN:\s*(\S+)",
            output,
        )
    )
    matches = chassis_blocks or list(
        re.finditer(
            r"(?im)^PID:\s*([^,\s]+)\s*,\s*VID:[^,\r\n]*,\s*SN:\s*(\S+)",
            output,
        )
    )
    models = [
        token
        for match in matches
        if (token := _validated_token(match.group(1), _MODEL_TOKEN_RE))
    ]
    serials = [
        token
        for match in matches
        if (token := _validated_token(match.group(2), _SERIAL_TOKEN_RE))
    ]
    return _unique_tokens(models), _unique_tokens(serials)


def _first_safe_token(
    text: str,
    patterns: tuple[str, ...],
    allowed: re.Pattern[str],
) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            token = _validated_token(match.group(1), allowed)
            if token:
                return token
    return None


def _all_safe_tokens(
    text: str,
    patterns: tuple[str, ...],
    allowed: re.Pattern[str],
) -> list[str]:
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            token = _validated_token(match.group(1), allowed)
            if token:
                values.append(token)
    return _unique_tokens(values)


def _unique_tokens(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.upper()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _validated_token(value: str, allowed: re.Pattern[str]) -> str | None:
    token = value.strip().strip(",;")
    return token if allowed.fullmatch(token) else None


def _chassis_serial_fingerprint(chassis_serial: str) -> str:
    normalized = chassis_serial.strip().upper()
    return hashlib.sha256(
        f"cisco-chassis-serial-v1\0{normalized}".encode("utf-8")
    ).hexdigest()


def _base_verification_result(
    *,
    port: str,
    baud: int,
    candidate_fingerprint: str,
) -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "status": "blocked",
        "message": "Cisco console identity has not been verified.",
        "checked_at": _checked_at(),
        "port": port,
        "baud": baud,
        "candidate_fingerprint": candidate_fingerprint,
        "detected_vendor": "unknown",
        "identity_verified": False,
        "prompt_state": "unknown",
        "model": None,
        "software_version": None,
        "serial_fingerprint": None,
        "read_only": True,
        "verification_method": "none",
        "baud_is_identity_proof": False,
        "raw_output_redacted": True,
        "raw_identifiers_redacted": True,
        "commands_attempted": [],
        "not_attempted": list(IDENTITY_NOT_ATTEMPTED),
        "blockers": [],
        "warnings": list(VERIFY_WARNINGS),
    }


def _blocked_result(result: dict[str, Any], *blockers: str) -> dict[str, Any]:
    result["status"] = "blocked"
    result["message"] = blockers[0] if blockers else "Cisco console identity is blocked."
    result["identity_verified"] = False
    result["blockers"] = [item for item in blockers if item]
    return result


def _serial_open_blocker(exc: BaseException) -> str:
    detail = str(exc).lower()
    if "access denied" in detail or "permission" in detail:
        return "Permission was denied opening the exact selected serial port."
    if "busy" in detail or "in use" in detail:
        return "The exact selected serial port is already in use."
    return (
        "The exact selected serial port could not be opened "
        f"({exc.__class__.__name__}); no other port or baud was tried."
    )


def _serial_io_blocker(exc: BaseException) -> str:
    return (
        "The exact selected serial session failed closed "
        f"({exc.__class__.__name__}); no alternate port, baud, or recovery sequence was tried."
    )


def _safe_metadata_text(
    value: str | None,
    redaction_values: list[str],
    *,
    max_length: int,
) -> str | None:
    if not value:
        return None
    text = "".join(character if ord(character) >= 32 else " " for character in value)
    for secret in redaction_values:
        if secret:
            text = re.sub(re.escape(secret), "[redacted]", text, flags=re.IGNORECASE)
    text = " ".join(text.split()).strip()
    return text[:max_length] or None


def _clean_text(value: Any, *, max_length: int) -> str | None:
    if value is None:
        return None
    text = "".join(
        character if ord(character) >= 32 else " "
        for character in str(value)
    )
    text = " ".join(text.split()).strip()
    return text[:max_length] or None


def _normalized_port_for_fingerprint(port: str) -> str:
    return port.upper() if re.fullmatch(r"(?i)COM[1-9][0-9]{0,3}", port) else port


def _safe_port_label(raw_port: str, raw_serial: str | None) -> str:
    if re.fullmatch(r"(?i)(?:COM[1-9][0-9]{0,3}|\\\\\.\\COM[1-9][0-9]{0,3})", raw_port):
        return raw_port
    if re.fullmatch(r"/dev/(?:ttyUSB|ttyACM|ttyS)\d+", raw_port):
        return raw_port
    if raw_port.startswith("/dev/serial/by-id/"):
        digest = hashlib.sha256(
            f"serial-port-label-v1\0{raw_port}".encode("utf-8")
        ).hexdigest()[:12]
        return f"/dev/serial/by-id/[redacted-{digest}]"
    if raw_serial and raw_serial.lower() in raw_port.lower():
        digest = hashlib.sha256(
            f"serial-port-label-v1\0{raw_port}".encode("utf-8")
        ).hexdigest()[:12]
        return f"/dev/[redacted-{digest}]"
    if raw_port.startswith("/dev/"):
        digest = hashlib.sha256(
            f"serial-port-label-v1\0{raw_port}".encode("utf-8")
        ).hexdigest()[:12]
        return f"/dev/[redacted-{digest}]"
    digest = hashlib.sha256(
        f"serial-port-label-v1\0{raw_port}".encode("utf-8")
    ).hexdigest()[:12]
    return f"/dev/[redacted-{digest}]"


def _sha256_json(domain: str, value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(f"{domain}\0{payload}".encode("utf-8")).hexdigest()


def _port_sort_key(port: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"(?i)COM(\d+)", port)
    if match:
        return ("com", int(match.group(1)), port)
    return ("path", 0, port)


def _checked_at() -> str:
    return datetime.now(UTC).isoformat()
