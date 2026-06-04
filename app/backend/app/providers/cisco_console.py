from __future__ import annotations

import glob
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.lab_safety import current_lab_safety
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive

PROVIDER_ID = "cisco-console"
SAFE_SHOW_COMMANDS = (
    "show version",
    "show inventory",
    "show interfaces status",
    "show ip interface brief",
    "show vlan brief",
)
PROMPT_READINESS_NOT_ATTEMPTED = [
    "safe show commands",
    "configure terminal",
    "write memory",
    "reload",
    "copy or erase",
    "VLAN, interface, user, password, SSH, or SCP changes",
]
NO_PROMPT_TEXT_CAPTURED_MESSAGE = (
    "Console port opened but no prompt text was captured. Verify the console cable "
    "is connected to the Cisco console port, confirm the switch is powered on, "
    "confirm no other process owns the serial port, and verify the baud rate such "
    "as 9600 or 115200."
)
NO_PROMPT_TEXT_CAPTURED_CHECKLIST = [
    "Confirm the USB serial adapter is connected to this host.",
    "Confirm the RJ45/console cable is connected to the Cisco console port, not an Ethernet data port.",
    "Confirm the switch is powered on and booted far enough for console access.",
    "Press Enter a few times in a manual console session.",
    "Check no other process owns /dev/ttyUSB0 with lsof or fuser.",
    "Try baud 9600 first, then 115200 if needed.",
    "Prefer /dev/serial/by-id/... stable path for CISCO_CONSOLE_PORT.",
]
CONSOLE_DETECTION_CHECKLIST = [
    "Check that the USB serial cable is plugged into this machine.",
    "Check that the console cable is connected to the Cisco console port.",
    "Check that the selected port matches the adapter.",
    "Check that the backend user has dialout/read-write access.",
]
NO_CONSOLE_ADAPTER_MESSAGE = (
    "No Cisco serial console adapter was detected. Connect the USB serial adapter "
    "to this machine, connect the console cable to the Cisco console port, then "
    "refresh Provider Status."
)
FALLBACK_CONSOLE_MESSAGE = (
    "Fallback serial adapter detected. Prefer a stable /dev/serial/by-id path if available."
)
PERMISSION_GUIDANCE = (
    "Configured console path exists but is not readable/writable. Check dialout group "
    "membership and device permissions, then restart the backend shell/session."
)


@dataclass(frozen=True)
class ConsoleCandidate:
    path: str
    stable_path: bool
    exists: bool
    readable: bool | None
    writable: bool | None
    label: str | None
    target_path: str | None
    recommendation: str


@dataclass(frozen=True)
class ConsoleDiscoveryPaths:
    stable_glob: str = "/dev/serial/by-id/*"
    usb_glob: str = "/dev/ttyUSB*"
    acm_glob: str = "/dev/ttyACM*"


@dataclass(frozen=True)
class CiscoConsoleConfig:
    port: str | None
    baud: int
    timeout_seconds: float
    prompt_settle_seconds: float = 0.5
    prompt_read_window_seconds: float = 1.0
    prompt_max_bytes: int = 8192

    @classmethod
    def from_settings(cls) -> "CiscoConsoleConfig":
        return cls(
            port=settings.cisco_console_port,
            baud=settings.cisco_console_baud,
            timeout_seconds=settings.cisco_console_timeout_seconds,
            prompt_settle_seconds=settings.cisco_console_prompt_settle_seconds,
            prompt_read_window_seconds=settings.cisco_console_prompt_read_window_seconds,
            prompt_max_bytes=settings.cisco_console_prompt_max_bytes,
        )


def discover_cisco_console(
    config: CiscoConsoleConfig | None = None,
    paths: ConsoleDiscoveryPaths | None = None,
) -> dict[str, Any]:
    config = config or CiscoConsoleConfig.from_settings()
    paths = paths or ConsoleDiscoveryPaths()
    candidates = _discover_candidates(paths)
    env_override = _env_override(config.port, candidates)

    existing_stable = [candidate for candidate in candidates if candidate.stable_path and candidate.exists]
    existing_candidates = [candidate for candidate in candidates if candidate.exists]
    blockers: list[str] = []
    warnings: list[str] = []
    recommended_path: str | None = None
    effective_path: str | None = None
    status = "missing-console"
    selection_source = "missing"
    safe_next_action = (
        "Connect a USB serial console cable and refresh provider status. "
        "Stable /dev/serial/by-id paths are preferred."
    )

    if env_override["configured"]:
        effective_path = str(env_override["path"])
        status = "ready"
        selection_source = "env-override"
        safe_next_action = "Run an explicit read-only probe after confirming the console target."
        _mark_recommendation(candidates, effective_path, "env-override")
        if not env_override["exists"]:
            status = "blocked"
            blockers.append(
                "Configured CISCO_CONSOLE_PORT does not exist. Reconnect the adapter "
                "or update CISCO_CONSOLE_PORT to the detected stable path."
            )
            safe_next_action = "Reconnect the adapter or update CISCO_CONSOLE_PORT."
        elif not _is_accessible(env_override):
            status = "blocked"
            blockers.append(PERMISSION_GUIDANCE)
            safe_next_action = (
                "Check dialout group membership and device permissions, then restart the backend shell/session."
            )
    elif len(existing_stable) == 1:
        recommended_path = existing_stable[0].path
        effective_path = recommended_path
        status = "ready"
        selection_source = "single-stable-candidate"
        _mark_recommendation(candidates, recommended_path, "recommended-default")
        safe_next_action = (
            f"Preferred console path: {recommended_path}. Use this stable path for "
            "CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible."
        )
        if not _candidate_accessible(existing_stable[0]):
            status = "blocked"
            blockers.append(
                "Preferred stable console path exists but is not readable/writable. "
                "Check dialout group membership and device permissions, then restart the backend shell/session."
            )
            safe_next_action = (
                "Check dialout group membership and device permissions, then restart the backend shell/session."
            )
    elif len(existing_stable) > 1:
        status = "needs-selection"
        selection_source = "multiple-stable-candidates"
        blockers.append(
            "Multiple stable serial console candidates were discovered; set "
            "CISCO_CONSOLE_PORT to the intended /dev/serial/by-id path."
        )
        safe_next_action = "Select the intended stable /dev/serial/by-id path in .env.local.real-lab."
    elif existing_candidates:
        status = "needs-selection"
        selection_source = "fallback-candidates"
        blockers.append(
            "Only fallback /dev/ttyUSB or /dev/ttyACM candidates were discovered; set "
            "CISCO_CONSOLE_PORT to the intended path before probing."
        )
        warnings.append(FALLBACK_CONSOLE_MESSAGE)
        safe_next_action = FALLBACK_CONSOLE_MESSAGE
    else:
        blockers.append(NO_CONSOLE_ADAPTER_MESSAGE)

    if existing_candidates and not existing_stable:
        warnings.append("No stable /dev/serial/by-id console path was found.")
    if recommended_path:
        warnings.append(
            f"Preferred console path: {recommended_path}. Use this stable path for "
            "CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible."
        )

    return {
        "status": status,
        "candidates": [asdict(candidate) for candidate in candidates],
        "recommended_path": recommended_path,
        "effective_path": effective_path,
        "selection_source": selection_source,
        "candidate_counts": {
            "total": len(candidates),
            "existing": len(existing_candidates),
            "stable_existing": len(existing_stable),
            "fallback_existing": len(existing_candidates) - len(existing_stable),
        },
        "env_override": env_override,
        "blockers": blockers,
        "warnings": warnings,
        "operator_message": _operator_message(status, recommended_path),
        "operator_checklist": CONSOLE_DETECTION_CHECKLIST,
        "permission_guidance": PERMISSION_GUIDANCE,
        "safe_next_action": safe_next_action,
        "safe_show_commands": list(SAFE_SHOW_COMMANDS),
    }


class CiscoConsoleAdapter:
    def __init__(
        self,
        provider_mode: str | None = None,
        config: CiscoConsoleConfig | None = None,
        paths: ConsoleDiscoveryPaths | None = None,
    ) -> None:
        self.provider_mode = provider_mode or settings.provider_mode
        self.config = config or CiscoConsoleConfig.from_settings()
        self.paths = paths or ConsoleDiscoveryPaths()

    def health(self) -> ProviderStatus:
        discovery = discover_cisco_console(self.config, self.paths)
        last_result, last_time = get_probe_result(PROVIDER_ID)
        safety = current_lab_safety()
        probe_enabled = (
            self.provider_mode == "local-readonly"
            and discovery["status"] == "ready"
            and bool(discovery["effective_path"])
            and safety.readonly_allowed
        )
        warnings = list(discovery["warnings"])
        blockers = list(discovery["blockers"])
        if self.provider_mode == "local-readonly":
            blockers.extend(safety.blockers)
        if self.provider_mode != "local-readonly":
            warnings.append(
                "Provider mode is not local-readonly; Cisco probe actions are disabled."
            )

        status = discovery["status"]
        if status == "ready" and self.provider_mode == "local-readonly" and not safety.readonly_allowed:
            status = "blocked"

        return ProviderStatus(
            id=PROVIDER_ID,
            name="Cisco Console",
            kind="network-console",
            mode=self.provider_mode,
            status=status,
            capabilities=[
                "dynamic-console-discovery",
                "explicit-read-only-probe",
                "safe-show-commands",
            ],
            message="Serial console discovery is read-only; probes require explicit operator action.",
            configuration={
                "port_configured": bool(self.config.port),
                "configured_port": self.config.port,
                "baud": self.config.baud,
                "timeout_seconds": self.config.timeout_seconds,
                **safety.as_flags(),
            },
            discovery=discovery,
            blockers=blockers,
            warnings=warnings,
            safe_actions=[
                ProviderAction(
                    id="probe-cisco-console",
                    label="Read-Only Probe",
                    enabled=probe_enabled,
                    read_only=True,
                    reason=(
                        "Open the selected serial port, send newline, then run safe show commands."
                        if probe_enabled
                        else (
                            "Requires PROVIDER_MODE=local-readonly, LAB_CLOSED_LOOP_ACK=YES, "
                            "LAB_READONLY_ACK=YES, and one effective console path."
                        )
                    ),
                    method="POST",
                    endpoint=f"/api/v1/providers/{PROVIDER_ID}/probe",
                )
            ],
            disabled_actions=_dangerous_actions(),
            last_probe_result=last_result,
            last_probe_time=last_time,
        )

    def probe(self) -> dict[str, Any]:
        if self.provider_mode != "local-readonly":
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly before running console probes."
            )

        safety = current_lab_safety()
        if not safety.readonly_allowed:
            return self._record_blocked(
                "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab probes.",
                safety=safety.as_flags(),
            )

        discovery = discover_cisco_console(self.config, self.paths)
        port = discovery.get("effective_path")
        if discovery["status"] != "ready" or not isinstance(port, str):
            return self._record_blocked(
                "Console probe requires one selected readable and writable console path.",
                discovery=discovery,
            )

        try:
            import serial  # type: ignore[import-untyped]
        except ImportError:
            return self._record_blocked(
                "pyserial is not installed; install backend requirements before probing.",
                discovery=discovery,
            )

        try:
            connection = serial.Serial(
                port=port,
                baudrate=self.config.baud,
                timeout=self.config.timeout_seconds,
                write_timeout=self.config.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            return self._record_result(
                {
                    "provider_id": PROVIDER_ID,
                    "status": "failed",
                    "message": f"Could not open selected console path: {exc}",
                    "discovery": discovery,
                    "warnings": [],
                    "blockers": ["Serial console open failed."],
                }
            )

        try:
            with connection:
                connection.write(b"\n")
                prompt_text = _read_console(
                    connection,
                    settle_seconds=self.config.prompt_settle_seconds,
                    read_window_seconds=self.config.prompt_read_window_seconds,
                    max_bytes=self.config.prompt_max_bytes,
                )
                prompt_state = _prompt_state(prompt_text)
                if prompt_state != "exec":
                    return self._record_blocked(
                        _prompt_blocker_message(prompt_state),
                        discovery=discovery,
                        prompt_state=prompt_state,
                        prompt_sample=_prompt_sample_summary(prompt_text),
                    )

                command_summaries: list[dict[str, Any]] = []
                for command in SAFE_SHOW_COMMANDS:
                    connection.write(f"{command}\n".encode("ascii"))
                    command_summaries.append(_command_summary(command, _read_console(connection)))

                return self._record_result(
                    {
                        "provider_id": PROVIDER_ID,
                        "status": "ok",
                        "message": "Read-only Cisco console probe completed.",
                        "port": port,
                        "baud": self.config.baud,
                        "prompt_state": prompt_state,
                        "safe_show_commands": command_summaries,
                        "warnings": [],
                        "blockers": [],
                    }
                )
        except Exception as exc:  # pragma: no cover - hardware dependent
            return self._record_result(
                {
                    "provider_id": PROVIDER_ID,
                    "status": "failed",
                    "message": f"Read-only Cisco console probe failed: {exc}",
                    "warnings": [],
                    "blockers": ["Serial console read-only probe failed."],
                }
            )

    def prompt_readiness(self) -> dict[str, Any]:
        if self.provider_mode != "local-readonly":
            return self._record_prompt_readiness(
                "blocked",
                "Set PROVIDER_MODE=local-readonly before running console prompt readiness checks.",
                blockers=[
                    "Set PROVIDER_MODE=local-readonly before running console prompt readiness checks."
                ],
            )

        safety = current_lab_safety()
        if not safety.readonly_allowed:
            return self._record_prompt_readiness(
                "blocked",
                "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab prompt checks.",
                blockers=[
                    "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab prompt checks."
                ],
                safety=safety.as_flags(),
            )

        discovery = discover_cisco_console(self.config, self.paths)
        port = discovery.get("effective_path")
        if discovery["status"] != "ready" or not isinstance(port, str):
            return self._record_prompt_readiness(
                "blocked",
                "Console prompt readiness requires one selected readable and writable console path.",
                blockers=[
                    "Console prompt readiness requires one selected readable and writable console path."
                ],
                discovery=discovery,
            )

        try:
            import serial  # type: ignore[import-untyped]
        except ImportError:
            return self._record_prompt_readiness(
                "blocked",
                "pyserial is not installed; install backend requirements before prompt readiness.",
                blockers=[
                    "pyserial is not installed; install backend requirements before prompt readiness."
                ],
                discovery=discovery,
            )

        try:
            connection = serial.Serial(
                port=port,
                baudrate=self.config.baud,
                timeout=self.config.timeout_seconds,
                write_timeout=self.config.timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - hardware dependent
            return self._record_prompt_readiness(
                "failed",
                f"Could not open selected console path: {exc}",
                blockers=["Serial console open failed."],
                discovery=discovery,
            )

        try:
            with connection:
                connection.write(b"\n")
                prompt_text = _read_console(
                    connection,
                    settle_seconds=self.config.prompt_settle_seconds,
                    read_window_seconds=self.config.prompt_read_window_seconds,
                    max_bytes=self.config.prompt_max_bytes,
                )
                prompt_state = _prompt_state(prompt_text)
                prompt_sample = _prompt_sample_summary(prompt_text)
                no_prompt_text = prompt_state == "unknown" and not prompt_sample["captured"]
                return self._record_prompt_readiness(
                    _prompt_readiness_status(prompt_state),
                    _prompt_readiness_message(prompt_state, prompt_sample),
                    port=port,
                    baud=self.config.baud,
                    read_timing={
                        "settle_seconds": self.config.prompt_settle_seconds,
                        "read_window_seconds": self.config.prompt_read_window_seconds,
                        "max_bytes": self.config.prompt_max_bytes,
                    },
                    prompt_state=prompt_state,
                    prompt_sample=prompt_sample,
                    blockers=(
                        []
                        if prompt_state == "exec"
                        else [_prompt_blocker_message(prompt_state, prompt_sample)]
                    ),
                    troubleshooting_checklist=(
                        NO_PROMPT_TEXT_CAPTURED_CHECKLIST if no_prompt_text else []
                    ),
                )
        except Exception as exc:  # pragma: no cover - hardware dependent
            return self._record_prompt_readiness(
                "failed",
                f"Cisco console prompt readiness check failed: {exc}",
                blockers=["Serial console prompt readiness check failed."],
            )

    def _record_blocked(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._record_result(
            {
                "provider_id": PROVIDER_ID,
                "status": "blocked",
                "message": message,
                "warnings": [],
                "blockers": [message],
                **extra,
            }
        )

    def _record_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return record_probe_result(PROVIDER_ID, redact_sensitive(result, [self.config.port]))

    def _record_prompt_readiness(
        self,
        status: str,
        message: str,
        *,
        blockers: list[str],
        warnings: list[str] | None = None,
        prompt_state: str = "unknown",
        **extra: Any,
    ) -> dict[str, Any]:
        result = {
            "provider_id": PROVIDER_ID,
            "action": "prompt-readiness",
            "status": status,
            "message": message,
            "prompt_state": prompt_state,
            "prompt_ready": prompt_state == "exec",
            "safe_show_commands_allowed": prompt_state == "exec",
            "setup_wizard_detected": prompt_state == "setup-wizard",
            "config_mode_detected": prompt_state == "config-mode",
            "login_required": prompt_state == "login-required",
            "not_attempted": PROMPT_READINESS_NOT_ATTEMPTED,
            "warnings": warnings or [],
            "blockers": blockers,
            **extra,
        }
        return self._record_result(result)


def _discover_candidates(paths: ConsoleDiscoveryPaths) -> list[ConsoleCandidate]:
    stable_paths = sorted(glob.glob(paths.stable_glob))
    fallback_paths = sorted(glob.glob(paths.usb_glob)) + sorted(glob.glob(paths.acm_glob))
    candidates = [_candidate(path, stable_path=True) for path in stable_paths]
    seen_paths = {candidate.path for candidate in candidates}

    for path in fallback_paths:
        if path not in seen_paths:
            candidates.append(_candidate(path, stable_path=False))
            seen_paths.add(path)

    return candidates


def _candidate(path: str, stable_path: bool) -> ConsoleCandidate:
    exists = os.path.exists(path)
    readable = os.access(path, os.R_OK) if exists else None
    writable = os.access(path, os.W_OK) if exists else None
    target_path = os.path.realpath(path) if stable_path and os.path.islink(path) else None
    return ConsoleCandidate(
        path=path,
        stable_path=stable_path,
        exists=exists,
        readable=readable,
        writable=writable,
        label=_candidate_label(path, target_path),
        target_path=target_path,
        recommendation="stable-candidate" if stable_path else "fallback-candidate",
    )


def _candidate_label(path: str, target_path: str | None) -> str:
    label = Path(path).name.replace("_", " ")
    if target_path:
        return f"{label} -> {target_path}"
    return label


def _env_override(
    configured_path: str | None,
    candidates: list[ConsoleCandidate],
) -> dict[str, Any]:
    if not configured_path:
        return {
            "configured": False,
            "path": None,
            "exists": False,
            "readable": None,
            "writable": None,
            "stable_path": False,
            "matches_discovered_candidate": False,
        }

    matching_candidate = next(
        (candidate for candidate in candidates if candidate.path == configured_path),
        None,
    )
    exists = os.path.exists(configured_path)
    readable = os.access(configured_path, os.R_OK) if exists else None
    writable = os.access(configured_path, os.W_OK) if exists else None
    return {
        "configured": True,
        "path": configured_path,
        "exists": exists,
        "readable": readable,
        "writable": writable,
        "stable_path": (
            matching_candidate.stable_path
            if matching_candidate
            else configured_path.startswith("/dev/serial/by-id/")
        ),
        "matches_discovered_candidate": matching_candidate is not None,
    }


def _mark_recommendation(
    candidates: list[ConsoleCandidate],
    path: str,
    recommendation: str,
) -> None:
    for index, candidate in enumerate(candidates):
        if candidate.path == path:
            candidates[index] = ConsoleCandidate(
                **{**asdict(candidate), "recommendation": recommendation}
            )


def _is_accessible(candidate: dict[str, Any]) -> bool:
    return bool(candidate.get("readable")) and bool(candidate.get("writable"))


def _candidate_accessible(candidate: ConsoleCandidate) -> bool:
    return bool(candidate.readable) and bool(candidate.writable)


def _dangerous_actions() -> list[ProviderAction]:
    return [
        ProviderAction(
            id="configure-terminal",
            label="Configure Terminal",
            enabled=False,
            read_only=False,
            reason="Persistent Cisco configuration changes are disabled in this preview.",
        ),
        ProviderAction(
            id="write-memory",
            label="Write Memory",
            enabled=False,
            read_only=False,
            reason="Saving switch configuration is not exposed by this portal preview.",
        ),
        ProviderAction(
            id="reload-switch",
            label="Reload",
            enabled=False,
            read_only=False,
            reason="Reload and erase operations are blocked.",
        ),
        ProviderAction(
            id="copy-or-erase",
            label="Copy / Erase",
            enabled=False,
            read_only=False,
            reason="Copy, erase, and startup-config changes are blocked.",
        ),
    ]


def _read_console(
    connection: Any,
    *,
    settle_seconds: float = 0.2,
    read_window_seconds: float = 0.0,
    max_bytes: int = 4096,
) -> str:
    time.sleep(max(settle_seconds, 0.0))
    byte_limit = max(max_bytes, 1)
    chunk_size = min(4096, byte_limit)
    chunks = [connection.read(chunk_size)]
    captured = sum(len(chunk) for chunk in chunks)
    deadline = time.monotonic() + max(read_window_seconds, 0.0)
    while getattr(connection, "in_waiting", 0) and captured < byte_limit and time.monotonic() <= deadline:
        chunk = connection.read(min(4096, byte_limit - captured))
        if not chunk:
            break
        chunks.append(chunk)
        captured += len(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _prompt_state(prompt_text: str) -> str:
    lower_text = prompt_text.lower()
    if (
        "initial configuration dialog" in lower_text
        or "would you like to enter the initial configuration dialog" in lower_text
        or "system configuration dialog" in lower_text
        or "[yes/no]" in lower_text
    ):
        return "setup-wizard"
    if "username:" in lower_text or "login:" in lower_text or "password:" in lower_text:
        return "login-required"
    if "(config" in lower_text:
        return "config-mode"

    lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
    if not lines:
        return "unknown"
    last_line = lines[-1]
    if last_line.endswith("#") or last_line.endswith(">"):
        return "exec"
    return "unknown"


def _prompt_blocker_message(
    prompt_state: str,
    prompt_sample: dict[str, Any] | None = None,
) -> str:
    if (
        prompt_state == "unknown"
        and isinstance(prompt_sample, dict)
        and not bool(prompt_sample.get("captured"))
    ):
        return NO_PROMPT_TEXT_CAPTURED_MESSAGE
    if prompt_state == "setup-wizard":
        return "Console is at an initial setup wizard prompt; no answers or commands were sent."
    if prompt_state == "login-required":
        return "Console requires login or password; credentials are not configured for this probe."
    if prompt_state == "config-mode":
        return "Console appears to be in configuration mode; no commands were sent."
    return "Console prompt could not be identified; no show commands were sent."


def _prompt_readiness_status(prompt_state: str) -> str:
    return "ok" if prompt_state == "exec" else "blocked"


def _prompt_readiness_message(prompt_state: str, prompt_sample: dict[str, Any]) -> str:
    if prompt_state == "exec":
        return "Prompt is ready for future safe show-command checks."
    return _prompt_blocker_message(prompt_state, prompt_sample)


def _prompt_sample_summary(prompt_text: str) -> dict[str, Any]:
    lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
    last_line = lines[-1] if lines else ""
    return {
        "captured": bool(prompt_text),
        "line_count": len(lines),
        "last_line": _redacted_prompt_line(last_line),
        "raw_text_redacted": True,
    }


def _redacted_prompt_line(line: str) -> str:
    lower_line = line.lower()
    if "initial configuration dialog" in lower_line or "system configuration dialog" in lower_line:
        return "setup wizard prompt"
    if "[yes/no]" in lower_line:
        return "[yes/no] prompt"
    if "username:" in lower_line:
        return "username prompt"
    if "login:" in lower_line:
        return "login prompt"
    if "password:" in lower_line:
        return "password prompt"
    if line.endswith("#"):
        return "DEVICE#"
    if line.endswith(">"):
        return "DEVICE>"
    if "(config" in lower_line:
        return "configuration prompt"
    return "unrecognized prompt"


def _command_summary(command: str, output: str) -> dict[str, Any]:
    return {
        "command": command,
        "captured": bool(output),
        "output_bytes": len(output.encode("utf-8", errors="replace")),
        "raw_output_redacted": True,
    }


def _operator_message(status: str, recommended_path: str | None) -> str:
    if status == "missing-console":
        return NO_CONSOLE_ADAPTER_MESSAGE
    if recommended_path:
        return (
            f"Preferred console path: {recommended_path}. Use this stable path for "
            "CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible."
        )
    return "Review Cisco serial console discovery before running prompt readiness."
