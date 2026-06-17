from __future__ import annotations

import os
import re
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.lab_safety import current_lab_safety
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive
from app.services.serial_console_discovery import (
    SerialConsoleDiscoveryPaths as SharedSerialConsoleDiscoveryPaths,
    discover_serial_console_candidates,
    inspect_serial_console_candidate,
    rank_serial_console_candidates,
)

PROVIDER_ID = "cisco-console"
REPO_ROOT = Path(__file__).resolve().parents[4]
CISCO_CONSOLE_DISCOVERY_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-console-discovery-report.md"
CISCO_FIRMWARE_INVENTORY_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-firmware-inventory-report.md"
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
PROMPT_CLASSIFICATION_GUIDANCE = {
    "exec": {
        "label": "User exec prompt",
        "summary": "Console appears to be at a user exec prompt.",
        "next_safe_action": (
            "Keep this as readiness evidence only; run any future show-command check "
            "through a separate explicit read-only action."
        ),
    },
    "privileged-exec": {
        "label": "Privileged exec prompt",
        "summary": "Console appears to be at a privileged exec prompt.",
        "next_safe_action": "Privileged exec is confirmed; keep configuration apply behind explicit guarded workflows.",
    },
    "setup-wizard": {
        "label": "Setup wizard prompt",
        "summary": "Console appears to be waiting at the initial setup wizard.",
        "next_safe_action": "Do not answer the wizard; review the setup wizard plan preview.",
    },
    "login-required": {
        "label": "Login required",
        "summary": "Console is requesting a username, login, or password.",
        "next_safe_action": "Do not send credentials; confirm credential handling in a future guarded task.",
    },
    "password-required": {
        "label": "Password required",
        "summary": "Console is requesting a password.",
        "next_safe_action": "Do not print or store the password; confirm credentials out of band.",
    },
    "config-mode": {
        "label": "Configuration mode",
        "summary": "Console appears to already be in configuration mode.",
        "next_safe_action": "Stop and get human review before any further console interaction.",
    },
    "unknown": {
        "label": "Unknown prompt",
        "summary": "Console output was not enough to classify the prompt.",
        "next_safe_action": "Use manual console observation and adapter checks before trying again.",
    },
    "unreadable": {
        "label": "Unreadable console text",
        "summary": "Console returned bytes that look like wrong-baud or unreadable text.",
        "next_safe_action": "Retry with common Cisco baud rates, starting with the configured baud then 9600 and 115200.",
    },
    "rommon-bootloader": {
        "label": "ROMMON or bootloader",
        "summary": "Console appears to be at a ROMMON or bootloader prompt.",
        "next_safe_action": "Use a manual Cisco recovery runbook before normal bootstrap.",
    },
    "port-in-use": {
        "label": "Port in use",
        "summary": "The serial port appears to be owned by another process.",
        "next_safe_action": "Close the other console session or service, then retry.",
    },
    "permission-denied": {
        "label": "Permission denied",
        "summary": "The backend user cannot open the serial port.",
        "next_safe_action": "Fix dialout/device permissions and restart the shell or backend session.",
    },
}
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
USB_SERIAL_NAME_HINTS = ("Cisco", "FTDI", "Prolific", "Silicon_Labs", "CP210", "USB-Serial")
COMMON_CISCO_CONSOLE_BAUDS = (9600, 115200, 19200, 38400, 57600)
MAX_PROMPT_SCAN_CANDIDATES = 2
MAX_PROMPT_SCAN_BAUDS = 2
MAX_SERIAL_READ_TIMEOUT_SECONDS = 0.35
CONSOLE_WAKE_SEQUENCES = (
    ("newline", b"\n"),
    ("enter", b"\r"),
    ("ctrl-c", b"\x03"),
    ("ctrl-z", b"\x1a"),
    ("break", b""),
)
VALID_PROMPT_STATES = {"exec", "privileged-exec", "setup-wizard", "login-required", "password-required", "rommon-bootloader"}
PROMPT_STATE_CLASSIFICATIONS = {
    "unknown": "no_bytes_read",
    "unreadable": "unreadable_gibberish",
    "login-required": "login_prompt",
    "password-required": "password_prompt",
    "exec": "user_exec",
    "privileged-exec": "privileged_exec",
    "config-mode": "config_mode",
    "setup-wizard": "setup_wizard",
    "rommon-bootloader": "rommon_or_bootloader",
    "port-in-use": "port_in_use",
    "permission-denied": "permission_denied",
}
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
    in_use: bool
    rank: int
    recommendation: str


@dataclass(frozen=True)
class ConsoleDiscoveryPaths:
    stable_glob: str = "/dev/serial/by-id/*"
    usb_glob: str = "/dev/ttyUSB*"
    acm_glob: str = "/dev/ttyACM*"
    ttys_glob: str = "/dev/ttyS*"


@dataclass(frozen=True)
class CiscoConsoleConfig:
    port: str | None
    baud: int
    timeout_seconds: float
    transport: str = "local_serial"
    tcp_host: str | None = None
    tcp_port: int = 2001
    prompt_settle_seconds: float = 0.5
    prompt_read_window_seconds: float = 1.0
    prompt_max_bytes: int = 8192

    @classmethod
    def from_settings(cls) -> "CiscoConsoleConfig":
        return cls(
            port=settings.cisco_console_port,
            baud=settings.cisco_console_baud,
            timeout_seconds=settings.cisco_console_timeout_seconds,
            transport=_normalize_console_transport(settings.cisco_console_transport),
            tcp_host=settings.cisco_console_tcp_host,
            tcp_port=settings.cisco_console_tcp_port,
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
    if config.transport == "tcp_console":
        configured = bool(config.tcp_host and config.tcp_port)
        return {
            "status": "ready" if configured else "missing-config",
            "transport": config.transport,
            "tcp_console": {
                "host_configured": bool(config.tcp_host),
                "port_configured": bool(config.tcp_port),
                "host": config.tcp_host,
                "port": config.tcp_port,
                "ser2net_compatible": True,
            },
            "configured_port_hint": config.port,
            "candidates": [],
            "recommended_path": None,
            "effective_path": f"tcp://{config.tcp_host}:{config.tcp_port}" if configured else None,
            "selected_path": f"tcp://{config.tcp_host}:{config.tcp_port}" if configured else None,
            "selection_source": "configured-tcp-console" if configured else "missing-tcp-console-config",
            "candidate_counts": {
                "total": 1 if configured else 0,
                "existing": 1 if configured else 0,
                "stable_existing": 0,
                "fallback_existing": 0,
            },
            "env_override": {
                "configured": configured,
                "path": f"tcp://{config.tcp_host}:{config.tcp_port}" if configured else None,
                "exists": configured,
                "readable": None,
                "writable": None,
                "stable_path": False,
                "matches_discovered_candidate": False,
            },
            "blockers": [] if configured else ["Set CISCO_CONSOLE_TCP_HOST and CISCO_CONSOLE_TCP_PORT for TCP console mode."],
            "last_console_blocker": None if configured else "Set CISCO_CONSOLE_TCP_HOST and CISCO_CONSOLE_TCP_PORT for TCP console mode.",
            "warnings": [
                "TCP console mode assumes a trusted local ser2net or console-server endpoint; no credentials are sent by discovery."
            ],
            "operator_message": (
                "TCP console endpoint is configured for ser2net-compatible console access."
                if configured
                else "TCP console mode needs host and port configuration before prompt readiness."
            ),
            "operator_checklist": [
                "Confirm ser2net or the console server maps this TCP endpoint to the Cisco console port.",
                "Confirm only the intended operator session owns the console.",
                "Keep bootstrap/apply behind explicit guarded workflows.",
            ],
            "permission_guidance": "",
            "safe_next_action": (
                "Run prompt readiness against the TCP console endpoint."
                if configured
                else "Set CISCO_CONSOLE_TCP_HOST and CISCO_CONSOLE_TCP_PORT, then refresh Provider Status."
            ),
            "safe_show_commands": list(SAFE_SHOW_COMMANDS),
        }
    candidates = _discover_candidates(paths)
    if config.port and not any(candidate.path == config.port for candidate in candidates):
        candidates.append(
            _candidate(
                config.port,
                stable_path=config.port.startswith("/dev/serial/by-id/"),
            )
        )
    env_override = _env_override(config.port, candidates)
    ranked_candidates = _rank_candidates(candidates, configured_port=config.port)

    existing_stable = [candidate for candidate in ranked_candidates if candidate.stable_path and candidate.exists]
    existing_candidates = [candidate for candidate in ranked_candidates if candidate.exists]
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

    selected_candidate = _first_selectable_candidate(ranked_candidates)
    if selected_candidate:
        recommended_path = next(
            (candidate.path for candidate in ranked_candidates if candidate.stable_path and _candidate_accessible(candidate)),
            None,
        )
        if config.port and selected_candidate.path == config.port:
            effective_path = selected_candidate.path
            status = "ready"
            selection_source = "configured-port-hint"
            _mark_recommendation(candidates, effective_path, "selected-auto")
            safe_next_action = "Run prompt readiness against the configured console path."
        elif selected_candidate.stable_path:
            effective_path = selected_candidate.path
            status = "ready"
            selection_source = "auto-stable-candidate"
            _mark_recommendation(candidates, effective_path, "selected-auto")
            safe_next_action = "Run prompt readiness; auto-discovery will confirm prompt and baud."
        else:
            status = "needs-selection"
            selection_source = "fallback-needs-selection"
            blockers.append(
                "Only fallback serial candidates were found; set CISCO_CONSOLE_PORT to the intended adapter or connect a stable /dev/serial/by-id path before treating Cisco console as reachable."
            )
            warnings.append(FALLBACK_CONSOLE_MESSAGE)
            safe_next_action = (
                "Select the intended Cisco console adapter with CISCO_CONSOLE_PORT or connect a stable "
                "/dev/serial/by-id path, then refresh Provider Status."
            )
        if config.port and selected_candidate.path != config.port:
            warnings.append(
                "Configured CISCO_CONSOLE_PORT was treated as a hint; auto-discovery selected another usable adapter."
            )
    elif env_override["configured"] and not env_override["exists"]:
        blockers.append(
            "Configured CISCO_CONSOLE_PORT does not exist; auto-discovery did not find another selectable adapter."
        )
        safe_next_action = "Reconnect the adapter or leave CISCO_CONSOLE_PORT unset and retry auto-discovery."
    elif existing_candidates:
        status = "blocked"
        selection_source = "no-accessible-candidates"
        if any(candidate.readable is False or candidate.writable is False for candidate in existing_candidates):
            blockers.append(
                "Serial console candidates were discovered but at least one is not readable/writable. "
                "Check dialout group membership and device permissions, then restart the backend shell/session."
            )
        else:
            blockers.append("Serial console candidates were discovered but none are selectable.")
        safe_next_action = "Check port ownership and permissions, then retry prompt readiness."
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
        "configured_port_hint": config.port,
        "candidates": [asdict(candidate) for candidate in _rank_candidates(candidates, configured_port=config.port)],
        "recommended_path": recommended_path,
        "effective_path": effective_path,
        "selected_path": effective_path,
        "selection_source": selection_source,
        "candidate_counts": {
            "total": len(candidates),
            "existing": len(existing_candidates),
            "stable_existing": len(existing_stable),
            "fallback_existing": len(existing_candidates) - len(existing_stable),
        },
        "env_override": env_override,
        "blockers": blockers,
        "last_console_blocker": blockers[-1] if blockers else None,
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
        policy = current_lab_action_policy(self.provider_mode)
        readonly_allowed = (
            safety.readonly_allowed if self.provider_mode == "local-readonly" else policy.readonly_allowed
        )
        probe_enabled = (
            self.provider_mode in REAL_CONTACT_MODES
            and discovery["status"] == "ready"
            and bool(discovery["effective_path"])
            and readonly_allowed
        )
        warnings = list(discovery["warnings"])
        blockers = list(discovery["blockers"])
        if self.provider_mode in REAL_CONTACT_MODES:
            blockers.extend(policy.readonly_blockers())
        if self.provider_mode not in REAL_CONTACT_MODES:
            warnings.append(
                "Provider mode is not local-readonly or local-lab-readwrite; Cisco probe actions are disabled."
            )

        status = discovery["status"]
        if status == "ready" and self.provider_mode in REAL_CONTACT_MODES and not readonly_allowed:
            status = "blocked"

        return ProviderStatus(
            id=PROVIDER_ID,
            name="Cisco Console",
            kind="network-console",
            mode=self.provider_mode,
            status=status,
            capabilities=[
                "dynamic-console-discovery",
                "local-serial-console",
                "tcp-console-ser2net",
                "explicit-read-only-probe",
                "safe-show-commands",
            ],
            message="Serial console discovery is read-only; probes require explicit operator action.",
            configuration={
                "port_configured": bool(self.config.port),
                "transport": self.config.transport,
                "configured_port": self.config.port,
                "tcp_host_configured": bool(self.config.tcp_host),
                "tcp_port_configured": bool(self.config.tcp_port),
                "tcp_host": self.config.tcp_host,
                "tcp_port": self.config.tcp_port,
                "baud": self.config.baud,
                "timeout_seconds": self.config.timeout_seconds,
                "prompt_settle_seconds": self.config.prompt_settle_seconds,
                "prompt_read_window_seconds": self.config.prompt_read_window_seconds,
                "prompt_max_bytes": self.config.prompt_max_bytes,
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
                            "LAB_READONLY_ACK=YES, and one effective console path; or complete "
                            "local-lab-readwrite acknowledgements."
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

    def cached_health(self) -> ProviderStatus:
        last_result, last_time = get_probe_result(PROVIDER_ID)
        safety = current_lab_safety()
        policy = current_lab_action_policy(self.provider_mode)
        readonly_allowed = (
            safety.readonly_allowed if self.provider_mode == "local-readonly" else policy.readonly_allowed
        )
        configured_path = self.config.port if self.config.transport == "local_serial" else None
        if self.config.transport == "tcp" and self.config.tcp_host and self.config.tcp_port:
            configured_path = f"{self.config.tcp_host}:{self.config.tcp_port}"
        status = "configured" if configured_path else "not_checked"
        blockers: list[str] = []
        warnings = [
            "Control Center uses cached Cisco console status; run Discover Console for a fresh serial scan."
        ]
        if self.provider_mode in REAL_CONTACT_MODES and not readonly_allowed:
            blockers.extend(policy.readonly_blockers())
            if blockers:
                status = "blocked"
        elif self.provider_mode not in REAL_CONTACT_MODES:
            warnings.append(
                "Provider mode is not local-readonly or local-lab-readwrite; Cisco probe actions are disabled."
            )

        return ProviderStatus(
            id=PROVIDER_ID,
            name="Cisco Console",
            kind="network-console",
            mode=self.provider_mode,
            status=status,
            capabilities=[
                "dynamic-console-discovery",
                "local-serial-console",
                "tcp-console-ser2net",
                "explicit-read-only-probe",
                "safe-show-commands",
            ],
            message="Cached Cisco console status is shown for fast UI rendering; explicit discovery is available.",
            configuration={
                "port_configured": bool(self.config.port),
                "transport": self.config.transport,
                "configured_port": self.config.port,
                "tcp_host_configured": bool(self.config.tcp_host),
                "tcp_port_configured": bool(self.config.tcp_port),
                "tcp_host": self.config.tcp_host,
                "tcp_port": self.config.tcp_port,
                "baud": self.config.baud,
                "timeout_seconds": self.config.timeout_seconds,
                "prompt_settle_seconds": self.config.prompt_settle_seconds,
                "prompt_read_window_seconds": self.config.prompt_read_window_seconds,
                "prompt_max_bytes": self.config.prompt_max_bytes,
                **safety.as_flags(),
            },
            discovery={
                "status": status,
                "effective_path": configured_path,
                "source": "cached_config",
                "cached_probe_status": last_result.get("status") if last_result else None,
                "operator_message": "Use Discover Console to refresh serial candidates and prompt readiness.",
            },
            blockers=blockers,
            warnings=warnings,
            safe_actions=[
                ProviderAction(
                    id="probe-cisco-console",
                    label="Read-Only Probe",
                    enabled=bool(configured_path) and readonly_allowed and self.provider_mode in REAL_CONTACT_MODES,
                    read_only=True,
                    reason=(
                        "Open the configured console path only after the operator starts a discovery/probe action."
                        if configured_path
                        else "Configure or discover a Cisco console path before probing."
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
        if self.provider_mode not in REAL_CONTACT_MODES:
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running console probes."
            )

        safety = current_lab_safety()
        policy = current_lab_action_policy(self.provider_mode)
        readonly_allowed = (
            safety.readonly_allowed if self.provider_mode == "local-readonly" else policy.readonly_allowed
        )
        if not readonly_allowed:
            message = (
                "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab probes."
                if self.provider_mode == "local-readonly"
                else "Required lab acknowledgement flags are missing before real lab probes."
            )
            return self._record_blocked(
                message,
                safety=safety.as_flags() if self.provider_mode == "local-readonly" else None,
                action_policy=policy.as_flags() if self.provider_mode != "local-readonly" else None,
            )

        discovery = discover_cisco_console(self.config, self.paths)
        port = discovery.get("effective_path")
        if discovery["status"] != "ready" or not isinstance(port, str):
            return self._record_blocked(
                "Console probe requires one selected readable and writable console path.",
                discovery=discovery,
            )

        if self.config.transport == "local_serial" and not _serial_available():
            return self._record_blocked(
                "pyserial is not installed; install backend requirements before probing.",
                discovery=discovery,
            )

        try:
            connection = _open_console_connection(self.config, port)
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
                if prompt_state not in {"exec", "privileged-exec"}:
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

    def firmware_inventory(self) -> dict[str, Any]:
        if self.provider_mode not in REAL_CONTACT_MODES:
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running Cisco firmware inventory."
            )

        safety = current_lab_safety()
        policy = current_lab_action_policy(self.provider_mode)
        readonly_allowed = (
            safety.readonly_allowed if self.provider_mode == "local-readonly" else policy.readonly_allowed
        )
        if not readonly_allowed:
            message = (
                "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab Cisco firmware inventory."
                if self.provider_mode == "local-readonly"
                else "Required lab acknowledgement flags are missing before real lab Cisco firmware inventory."
            )
            return self._record_cisco_firmware_result(
                {
                    "provider_id": PROVIDER_ID,
                    "action": "firmware-inventory",
                    "status": "blocked",
                    "message": message,
                    "warnings": [],
                    "blockers": [message],
                    "safety": safety.as_flags() if self.provider_mode == "local-readonly" else None,
                    "action_policy": policy.as_flags() if self.provider_mode != "local-readonly" else None,
                }
            )

        discovery = discover_cisco_console(self.config, self.paths)
        if settings.cisco_mgmt_configured:
            ssh_result = _ssh_cisco_firmware_inventory(discovery)
            if ssh_result["status"] == "ok":
                return self._record_cisco_firmware_result(ssh_result)

        scan_candidates = _scan_candidates(discovery, max_candidates=MAX_PROMPT_SCAN_CANDIDATES)
        if not scan_candidates:
            return self._record_cisco_firmware_result(
                {
                    "provider_id": PROVIDER_ID,
                    "action": "firmware-inventory",
                    "status": "blocked",
                    "message": "Cisco firmware inventory requires one selected readable and writable console path.",
                    "discovery": discovery,
                    "warnings": [],
                    "blockers": ["Cisco firmware inventory requires one selected readable and writable console path."],
                }
            )

        if self.config.transport == "local_serial" and not _serial_available():
            return self._record_cisco_firmware_result(
                {
                    "provider_id": PROVIDER_ID,
                    "action": "firmware-inventory",
                    "status": "blocked",
                    "message": "pyserial is not installed; install backend requirements before Cisco firmware inventory.",
                    "discovery": discovery,
                    "warnings": [],
                    "blockers": ["pyserial is not installed; install backend requirements before Cisco firmware inventory."],
                }
            )

        attempts: list[dict[str, Any]] = []
        last_blocker = "No Cisco exec prompt was detected on discovered console candidates."
        baud_rates = _baud_scan_order(self.config.baud, max_bauds=MAX_PROMPT_SCAN_BAUDS)
        for candidate in scan_candidates:
            port = str(candidate["path"])
            for baud in baud_rates:
                try:
                    connection = _open_console_connection(self.config, port, baud=baud)
                except Exception as exc:  # pragma: no cover - hardware dependent
                    prompt_state = _serial_open_prompt_state(exc)
                    last_blocker = _prompt_blocker_message(prompt_state)
                    attempts.append(
                        {
                            "port": port,
                            "baud": baud,
                            "sequence": "open",
                            "status": "failed",
                            "error": _serial_error_summary(exc),
                            "prompt_state": prompt_state,
                            "classification": _classification_for_state(prompt_state, {"captured": False}),
                        }
                    )
                    continue

                try:
                    with connection:
                        if hasattr(connection, "reset_input_buffer"):
                            connection.reset_input_buffer()
                        _toggle_dtr_rts(connection)
                        for sequence_name, sequence_bytes in CONSOLE_WAKE_SEQUENCES:
                            if sequence_name == "break":
                                _send_break(connection)
                            else:
                                connection.write(sequence_bytes)
                            prompt_text = _read_console(
                                connection,
                                settle_seconds=self.config.prompt_settle_seconds,
                                read_window_seconds=self.config.prompt_read_window_seconds,
                                max_bytes=self.config.prompt_max_bytes,
                            )
                            prompt_state = _prompt_state(prompt_text)
                            prompt_sample = _prompt_sample_summary(prompt_text)
                            attempts.append(
                                {
                                    "port": port,
                                    "baud": baud,
                                    "sequence": sequence_name,
                                    "status": "checked",
                                    "prompt_state": prompt_state,
                                    "classification": _classification_for_state(prompt_state, prompt_sample),
                                    "captured": bool(prompt_text),
                                }
                            )
                            if prompt_state not in {"exec", "privileged-exec"}:
                                last_blocker = _prompt_blocker_message(prompt_state, prompt_sample)
                                continue

                            connection.write(b"show version\n")
                            output = _read_console(
                                connection,
                                settle_seconds=self.config.prompt_settle_seconds,
                                read_window_seconds=max(self.config.prompt_read_window_seconds, 1.0),
                                max_bytes=self.config.prompt_max_bytes,
                            )
                            command_summary = _command_summary("show version", output)
                            ios_xe_version = _ios_xe_version(output)
                            status = "ok" if ios_xe_version else "blocked"
                            result = {
                                "provider_id": PROVIDER_ID,
                                "action": "firmware-inventory",
                                "status": status,
                                "message": (
                                    "Cisco IOS XE firmware inventory completed from console user exec."
                                    if ios_xe_version
                                    else "Cisco show version ran from console user exec, but IOS XE version was not parsed."
                                ),
                                "source": "console-user-exec-show-version",
                                "prompt_state": prompt_state,
                                "selected_path": port,
                                "selected_baud": baud,
                                "selected_sequence": sequence_name,
                                "discovery": discovery,
                                "attempts": attempts,
                                "safe_show_commands": [command_summary],
                                "ios_xe_version": ios_xe_version,
                                "bootloader_rommon": _bootloader_rommon_version(output),
                                "warnings": [],
                                "blockers": [] if ios_xe_version else ["Cisco IOS XE version was not parsed from show version output."],
                            }
                            return self._record_cisco_firmware_result(result)
                except Exception as exc:  # pragma: no cover - hardware dependent
                    prompt_state = _serial_open_prompt_state(exc)
                    last_blocker = _prompt_blocker_message(prompt_state)
                    attempts.append(
                        {
                            "port": port,
                            "baud": baud,
                            "status": "failed",
                            "error": _serial_error_summary(exc),
                            "prompt_state": prompt_state,
                            "classification": _classification_for_state(prompt_state, {"captured": False}),
                        }
                    )

        return self._record_cisco_firmware_result(
            {
                "provider_id": PROVIDER_ID,
                "action": "firmware-inventory",
                "status": "blocked",
                "message": last_blocker,
                "discovery": discovery,
                "attempts": attempts,
                "warnings": [],
                "blockers": [last_blocker],
                "next_safe_action": "Run Cisco firmware inventory from console.",
            }
        )

    def prompt_readiness(self) -> dict[str, Any]:
        if self.provider_mode not in REAL_CONTACT_MODES:
            return self._record_prompt_readiness(
                "blocked",
                "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running console prompt readiness checks.",
                blockers=[
                    "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running console prompt readiness checks."
                ],
            )

        safety = current_lab_safety()
        policy = current_lab_action_policy(self.provider_mode)
        readonly_allowed = (
            safety.readonly_allowed if self.provider_mode == "local-readonly" else policy.readonly_allowed
        )
        if not readonly_allowed:
            message = (
                "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab prompt checks."
                if self.provider_mode == "local-readonly"
                else "Required lab acknowledgement flags are missing before real lab prompt checks."
            )
            return self._record_prompt_readiness(
                "blocked",
                message,
                blockers=[message],
                safety=safety.as_flags() if self.provider_mode == "local-readonly" else None,
                action_policy=policy.as_flags() if self.provider_mode != "local-readonly" else None,
            )

        discovery = discover_cisco_console(self.config, self.paths)
        scan_candidates = _scan_candidates(discovery)
        if not scan_candidates:
            return self._record_prompt_readiness(
                "blocked",
                "Console prompt readiness requires one selected readable and writable console path.",
                blockers=[
                    "Console prompt readiness requires one selected readable and writable console path."
                ],
                discovery=discovery,
                candidate_count=_candidate_count(discovery),
            )

        if self.config.transport == "local_serial" and not _serial_available():
            return self._record_prompt_readiness(
                "blocked",
                "pyserial is not installed; install backend requirements before prompt readiness.",
                blockers=[
                    "pyserial is not installed; install backend requirements before prompt readiness."
                ],
                discovery=discovery,
            )

        attempts: list[dict[str, Any]] = []
        last_blocker = "No Cisco prompt or login flow was detected on discovered console candidates."
        best_prompt_sample: dict[str, Any] | None = None
        scan_candidates = _scan_candidates(discovery, max_candidates=MAX_PROMPT_SCAN_CANDIDATES)
        baud_rates = _baud_scan_order(self.config.baud, max_bauds=MAX_PROMPT_SCAN_BAUDS)
        read_timing = {
            "settle_seconds": self.config.prompt_settle_seconds,
            "read_window_seconds": self.config.prompt_read_window_seconds,
            "read_windows": _read_windows(self.config.prompt_read_window_seconds),
            "max_bytes": self.config.prompt_max_bytes,
            "dtr_rts_toggle": "attempted when supported",
        }
        for candidate in scan_candidates:
            port = str(candidate["path"])
            for baud in baud_rates:
                try:
                    connection = _open_console_connection(self.config, port, baud=baud)
                except Exception as exc:  # pragma: no cover - hardware dependent
                    open_state = _serial_open_prompt_state(exc)
                    last_blocker = _prompt_blocker_message(open_state)
                    attempts.append(
                        {
                            "port": port,
                            "baud": baud,
                            "sequence": "open",
                            "status": "failed",
                            "error": _serial_error_summary(exc),
                            "prompt_state": open_state,
                            "classification": _classification_for_state(open_state, {"captured": False}),
                        }
                    )
                    continue

                try:
                    with connection:
                        if hasattr(connection, "reset_input_buffer"):
                            connection.reset_input_buffer()
                        _toggle_dtr_rts(connection)
                        for sequence_name, sequence_bytes in CONSOLE_WAKE_SEQUENCES:
                            if sequence_name == "break":
                                _send_break(connection)
                            else:
                                connection.write(sequence_bytes)
                            prompt_text = _read_console(
                                connection,
                                settle_seconds=self.config.prompt_settle_seconds,
                                read_window_seconds=self.config.prompt_read_window_seconds,
                                max_bytes=self.config.prompt_max_bytes,
                            )
                            prompt_state = _prompt_state(prompt_text)
                            prompt_sample = _prompt_sample_summary(prompt_text)
                            if prompt_sample["captured"]:
                                best_prompt_sample = prompt_sample
                            attempts.append(
                                {
                                    "port": port,
                                    "baud": baud,
                                    "sequence": sequence_name,
                                    "status": "checked",
                                    "prompt_state": prompt_state,
                                    "classification": _classification_for_state(prompt_state, prompt_sample),
                                    "captured": prompt_sample["captured"],
                                    "last_line": prompt_sample["last_line"],
                                }
                            )
                            if prompt_state in VALID_PROMPT_STATES or prompt_state == "config-mode":
                                no_prompt_text = prompt_state == "unknown" and not prompt_sample["captured"]
                                return self._record_prompt_readiness(
                                    _prompt_readiness_status(prompt_state),
                                    _prompt_readiness_message(prompt_state, prompt_sample),
                                    port=port,
                                    baud=baud,
                                    selected_path=port,
                                    selected_baud=baud,
                                    selected_sequence=sequence_name,
                                    candidate_count=_candidate_count(discovery),
                                    configured_port_hint=self.config.port,
                                    discovery=discovery,
                                    attempts=attempts,
                                    read_timing=read_timing,
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
                            last_blocker = _prompt_blocker_message(prompt_state, prompt_sample)
                except Exception as exc:  # pragma: no cover - hardware dependent
                    read_state = _serial_open_prompt_state(exc)
                    last_blocker = _prompt_blocker_message(read_state)
                    attempts.append(
                        {
                            "port": port,
                            "baud": baud,
                            "sequence": "read",
                            "status": "failed",
                            "error": _serial_error_summary(exc),
                            "prompt_state": read_state,
                            "classification": _classification_for_state(read_state, {"captured": False}),
                        }
                    )

        final_prompt_sample = best_prompt_sample or {
            "captured": False,
            "line_count": 0,
            "last_line": "",
            "raw_text_redacted": True,
        }
        return self._record_prompt_readiness(
            "blocked",
            last_blocker,
            blockers=[last_blocker],
            discovery=discovery,
            attempts=attempts,
            configured_port_hint=self.config.port,
            selected_path=None,
            selected_baud=None,
            candidate_count=_candidate_count(discovery),
            read_timing=read_timing,
            prompt_state=_final_prompt_state(final_prompt_sample),
            prompt_sample=final_prompt_sample,
            troubleshooting_checklist=(
                [] if final_prompt_sample["captured"] else NO_PROMPT_TEXT_CAPTURED_CHECKLIST
            ),
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
        return record_probe_result(
            PROVIDER_ID,
            redact_sensitive(
                result,
                [
                    self.config.port,
                    settings.cisco_test_username,
                    settings.cisco_test_password,
                    settings.cisco_enable_password,
                ],
            ),
        )

    def _record_cisco_firmware_result(self, result: dict[str, Any]) -> dict[str, Any]:
        recorded = self._record_result(result)
        _write_cisco_firmware_inventory_report(recorded)
        return recorded

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
            "prompt_ready": prompt_state in {"exec", "privileged-exec"},
            "safe_show_commands_allowed": False,
            "future_show_command_check_eligible": prompt_state in {"exec", "privileged-exec"},
            "prompt_classification": _prompt_classification(
                prompt_state,
                extra.get("prompt_sample"),
            ),
            "setup_wizard_detected": prompt_state == "setup-wizard",
            "config_mode_detected": prompt_state == "config-mode",
            "login_required": prompt_state == "login-required",
            "credentials_configured": _cisco_console_credentials_configured(),
            "not_attempted": PROMPT_READINESS_NOT_ATTEMPTED,
            "next_safe_action": _prompt_next_safe_action(prompt_state, extra.get("prompt_sample")),
            "warnings": warnings or [],
            "blockers": blockers,
            **extra,
        }
        recorded = self._record_result(result)
        _write_console_discovery_report(recorded)
        return recorded


def _discover_candidates(paths: ConsoleDiscoveryPaths) -> list[ConsoleCandidate]:
    shared_paths = SharedSerialConsoleDiscoveryPaths(
        by_id_glob=paths.stable_glob,
        usb_glob=paths.usb_glob,
        acm_glob=paths.acm_glob,
        ttys_glob=paths.ttys_glob,
    )
    return [
        _console_candidate_from_shared(candidate)
        for candidate in discover_serial_console_candidates(
            paths=shared_paths,
            collect_details=False,
            device_hint="cisco",
        )
    ]


def _candidate(path: str, stable_path: bool) -> ConsoleCandidate:
    return _console_candidate_from_shared(
        inspect_serial_console_candidate(
            path,
            path_type="by-id" if stable_path else None,
            collect_details=False,
            device_hint="cisco",
        )
    )


def _rank_candidates(
    candidates: list[ConsoleCandidate],
    *,
    configured_port: str | None,
) -> list[ConsoleCandidate]:
    selected_auto_paths = {
        candidate.path for candidate in candidates if candidate.recommendation == "selected-auto"
    }
    shared_candidates = [
        {
            **asdict(candidate),
            "display_path": candidate.path,
            "resolved_path": candidate.target_path,
            "path_type": _path_type_for_candidate(candidate),
        }
        for candidate in candidates
    ]
    return [
        _console_candidate_from_shared(candidate)
        for candidate in _with_selected_auto_recommendations(
            rank_serial_console_candidates(
                shared_candidates,
                configured_hint=configured_port,
                device_hint="cisco",
            ),
            selected_auto_paths,
        )
    ]


def _with_selected_auto_recommendations(
    candidates: list[dict[str, Any]],
    selected_auto_paths: set[str],
) -> list[dict[str, Any]]:
    return [
        {
            **candidate,
            "recommendation": "selected-auto"
            if str(candidate.get("display_path") or candidate.get("path") or "") in selected_auto_paths
            else candidate.get("recommendation"),
        }
        for candidate in candidates
    ]


def _console_candidate_from_shared(candidate: dict[str, Any]) -> ConsoleCandidate:
    return ConsoleCandidate(
        path=str(candidate.get("display_path") or candidate.get("path") or ""),
        stable_path=bool(candidate.get("stable_path")),
        exists=bool(candidate.get("exists")),
        readable=bool(candidate.get("readable")) if candidate.get("exists") else None,
        writable=bool(candidate.get("writable")) if candidate.get("exists") else None,
        label=str(candidate.get("label") or candidate.get("display_path") or ""),
        target_path=str(candidate.get("resolved_path") or candidate.get("target_path") or "")
        if candidate.get("resolved_path") or candidate.get("target_path")
        else None,
        in_use=bool(candidate.get("in_use")),
        rank=int(candidate.get("rank") or 0),
        recommendation=str(candidate.get("recommendation") or "serial-candidate"),
    )


def _path_type_for_candidate(candidate: ConsoleCandidate) -> str:
    if candidate.stable_path:
        return "by-id"
    name = Path(candidate.path).name
    if name.startswith("ttyUSB"):
        return "ttyUSB"
    if name.startswith("ttyACM"):
        return "ttyACM"
    if name.startswith("ttyS"):
        return "ttyS"
    return "other"


def _candidate_rank(
    *,
    path: str,
    label: str | None,
    stable_path: bool,
    exists: bool,
    readable: bool | None,
    writable: bool | None,
    in_use: bool,
    configured_port: str | None,
) -> int:
    rank = 0 if stable_path else 100
    if configured_port and path == configured_port:
        rank -= 200
    if _preferred_usb_name(path, label):
        rank -= 25
    if not exists:
        rank += 2000
    if not readable or not writable:
        rank += 1000
    if in_use:
        rank += 500
    return rank


def _ranked_recommendation(candidate: ConsoleCandidate, configured_port: str | None) -> str:
    if candidate.recommendation == "selected-auto":
        return "selected-auto"
    if configured_port and candidate.path == configured_port:
        return "configured-port-hint"
    if not candidate.exists:
        return "unavailable"
    if not _candidate_accessible(candidate):
        return "permission-blocked"
    if candidate.in_use:
        return "in-use-deprioritized"
    if candidate.stable_path:
        return "stable-auto-candidate"
    return "fallback-auto-candidate"


def _preferred_usb_name(path: str, label: str | None) -> bool:
    haystack = f"{path} {label or ''}".lower().replace("-", "_")
    return any(hint.lower().replace("-", "_") in haystack for hint in USB_SERIAL_NAME_HINTS)


def _path_in_use(path: str) -> bool:
    try:
        result = subprocess.run(
            ["fuser", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=0.5,
            check=False,
        )
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _first_selectable_candidate(candidates: list[ConsoleCandidate]) -> ConsoleCandidate | None:
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.exists and _candidate_accessible(candidate) and not candidate.in_use
        ),
        None,
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


def _scan_candidates(discovery: dict[str, Any], *, max_candidates: int | None = None) -> list[dict[str, Any]]:
    if discovery.get("transport") == "tcp_console" and isinstance(discovery.get("effective_path"), str):
        tcp_console = discovery.get("tcp_console") if isinstance(discovery.get("tcp_console"), dict) else {}
        return [
            {
                "path": discovery["effective_path"],
                "stable_path": False,
                "exists": True,
                "readable": True,
                "writable": True,
                "in_use": False,
                "rank": 0,
                "recommendation": "configured-tcp-console",
                "host": tcp_console.get("host"),
                "port": tcp_console.get("port"),
            }
        ]
    candidates = [
        candidate
        for candidate in discovery.get("candidates", [])
        if isinstance(candidate, dict)
        and candidate.get("exists") is True
        and candidate.get("readable") is True
        and candidate.get("writable") is True
        and candidate.get("in_use") is not True
        and isinstance(candidate.get("path"), str)
    ]
    effective_path = discovery.get("effective_path")
    if isinstance(effective_path, str):
        candidates = sorted(
            candidates,
            key=lambda candidate: (
                0 if candidate.get("path") == effective_path else 1,
                int(candidate.get("rank") or 0),
                str(candidate.get("path")),
            ),
        )
    if max_candidates is not None:
        return candidates[: max(max_candidates, 0)]
    return candidates


def _candidate_count(discovery: dict[str, Any]) -> int:
    counts = discovery.get("candidate_counts")
    if isinstance(counts, dict) and isinstance(counts.get("total"), int):
        return int(counts["total"])
    candidates = discovery.get("candidates")
    return len(candidates) if isinstance(candidates, list) else 0


def _baud_scan_order(configured_baud: int, *, max_bauds: int | None = None) -> list[int]:
    bauds = list(dict.fromkeys([configured_baud, *COMMON_CISCO_CONSOLE_BAUDS]))
    if max_bauds is not None:
        return bauds[: max(max_bauds, 0)]
    return bauds


def _normalize_console_transport(value: str | None) -> str:
    normalized = (value or "local_serial").strip().lower().replace("-", "_")
    if normalized in {"tcp", "tcp_console", "ser2net"}:
        return "tcp_console"
    return "local_serial"


def _serial_available() -> bool:
    try:
        import serial  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        return False
    return True


class TcpConsoleConnection:
    def __init__(self, host: str, port: int, timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self._socket: socket.socket | None = None

    def __enter__(self) -> "TcpConsoleConnection":
        self._socket = socket.create_connection((self.host, self.port), timeout=self.timeout_seconds)
        self._socket.settimeout(0.05)
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    @property
    def in_waiting(self) -> int:
        return 0

    def write(self, payload: bytes) -> int:
        if self._socket is None:
            raise RuntimeError("TCP console connection is not open.")
        self._socket.sendall(payload)
        return len(payload)

    def read(self, size: int) -> bytes:
        if self._socket is None:
            raise RuntimeError("TCP console connection is not open.")
        try:
            return self._socket.recv(size)
        except TimeoutError:
            return b""
        except socket.timeout:
            return b""


def _open_console_connection(
    config: CiscoConsoleConfig,
    port: str,
    *,
    baud: int | None = None,
) -> Any:
    if config.transport == "tcp_console":
        if not config.tcp_host or not config.tcp_port:
            raise RuntimeError("TCP console host and port are required.")
        return TcpConsoleConnection(config.tcp_host, config.tcp_port, config.timeout_seconds)
    import serial  # type: ignore[import-untyped]

    return serial.Serial(
        port=port,
        baudrate=baud or config.baud,
        timeout=min(max(config.timeout_seconds, 0.05), MAX_SERIAL_READ_TIMEOUT_SECONDS),
        write_timeout=config.timeout_seconds,
    )


def _ssh_cisco_firmware_inventory(discovery: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if not settings.cisco_target_ip:
        missing.append("CISCO_TARGET_IP")
    if not settings.cisco_test_username:
        missing.append("CISCO_TEST_USERNAME")
    if not settings.cisco_test_password:
        missing.append("CISCO_TEST_PASSWORD")
    if missing:
        return {
            "provider_id": PROVIDER_ID,
            "action": "firmware-inventory",
            "status": "blocked",
            "message": "Cisco SSH firmware inventory is missing local connection fields.",
            "source": "ssh-netmiko-show-version",
            "discovery": discovery,
            "warnings": [],
            "blockers": [f"Cisco SSH firmware inventory missing fields: {', '.join(missing)}."],
        }
    try:
        from netmiko import ConnectHandler  # type: ignore[import-untyped]
    except ImportError:
        return {
            "provider_id": PROVIDER_ID,
            "action": "firmware-inventory",
            "status": "blocked",
            "message": "Netmiko is not installed; Cisco SSH firmware inventory cannot run.",
            "source": "ssh-netmiko-show-version",
            "discovery": discovery,
            "warnings": [],
            "blockers": ["Netmiko is not installed; use the console firmware inventory path."],
        }

    connection = None
    try:
        connection = ConnectHandler(
            device_type="cisco_ios",
            host=settings.cisco_target_ip,
            username=settings.cisco_test_username,
            password=settings.cisco_test_password,
            secret=settings.cisco_enable_password or "",
            conn_timeout=settings.ansible_cisco_timeout_seconds,
            auth_timeout=settings.ansible_cisco_timeout_seconds,
            banner_timeout=settings.ansible_cisco_timeout_seconds,
            fast_cli=False,
        )
        output = str(
            connection.send_command(
                "show version",
                read_timeout=max(settings.ansible_cisco_timeout_seconds, 8.0),
            )
        )
    except Exception as exc:  # pragma: no cover - network and device dependent
        return {
            "provider_id": PROVIDER_ID,
            "action": "firmware-inventory",
            "status": "blocked",
            "message": "Cisco SSH firmware inventory did not complete.",
            "source": "ssh-netmiko-show-version",
            "discovery": discovery,
            "warnings": [],
            "blockers": [f"Cisco SSH firmware inventory failed before parsing show version: {exc.__class__.__name__}."],
        }
    finally:
        if connection is not None:
            try:
                connection.disconnect()
            except Exception:
                pass

    command_summary = _command_summary("show version", output)
    ios_xe_version = _ios_xe_version(output)
    return {
        "provider_id": PROVIDER_ID,
        "action": "firmware-inventory",
        "status": "ok" if ios_xe_version else "blocked",
        "message": (
            "Cisco IOS XE firmware inventory completed from management SSH."
            if ios_xe_version
            else "Cisco SSH show version ran, but IOS XE version was not parsed."
        ),
        "source": "ssh-netmiko-show-version",
        "prompt_state": "ssh-management",
        "selected_path": settings.cisco_target_ip,
        "selected_baud": None,
        "selected_sequence": "ssh",
        "discovery": discovery,
        "attempts": [
            {
                "transport": "ssh",
                "status": "checked",
                "classification": "management_ssh",
                "captured": bool(output),
            }
        ],
        "safe_show_commands": [command_summary],
        "ios_xe_version": ios_xe_version,
        "bootloader_rommon": _bootloader_rommon_version(output),
        "warnings": [],
        "blockers": [] if ios_xe_version else ["Cisco IOS XE version was not parsed from SSH show version output."],
    }


def _write_console_discovery_report(result: dict[str, Any]) -> None:
    CISCO_CONSOLE_DISCOVERY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    discovery = result.get("discovery") if isinstance(result.get("discovery"), dict) else {}
    candidate_count = result.get("candidate_count")
    if candidate_count is None and discovery:
        candidate_count = _candidate_count(discovery)
    blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
    last_blocker = blockers[-1] if blockers else discovery.get("last_console_blocker") if discovery else None
    attempts = result.get("attempts") if isinstance(result.get("attempts"), list) else []
    lines = [
        "# Cisco Console Discovery",
        "",
        f"- Status: {result.get('status', 'unknown')}",
        f"- Prompt state: {result.get('prompt_state', 'unknown')}",
        f"- Configured port hint: {result.get('configured_port_hint') or discovery.get('configured_port_hint') or 'not set'}",
        f"- Auto-discovered selected port: {result.get('selected_path') or discovery.get('effective_path') or 'not selected'}",
        f"- Selected baud: {result.get('selected_baud') or result.get('baud') or 'not selected'}",
        f"- Candidate count: {candidate_count if candidate_count is not None else 0}",
        f"- Last console blocker: {last_blocker or 'none'}",
        "",
        "## Candidate Summary",
    ]
    for candidate in discovery.get("candidates", []) if discovery else []:
        if not isinstance(candidate, dict):
            continue
        lines.append(
            "- "
            f"{candidate.get('path')} | stable={candidate.get('stable_path')} | "
            f"exists={candidate.get('exists')} | readable={candidate.get('readable')} | "
            f"writable={candidate.get('writable')} | in_use={candidate.get('in_use')} | "
            f"rank={candidate.get('rank')} | recommendation={candidate.get('recommendation')}"
        )
    lines.extend(["", "## Attempts"])
    for attempt in attempts[-40:]:
        if not isinstance(attempt, dict):
            continue
        lines.append(
            "- "
            f"{attempt.get('port')} @ {attempt.get('baud')} via {attempt.get('sequence')}: "
            f"{attempt.get('status')} prompt={attempt.get('prompt_state')} "
            f"captured={attempt.get('captured')}"
        )
    if not attempts:
        lines.append("- No serial prompt attempts were run.")
    lines.append("")
    CISCO_CONSOLE_DISCOVERY_REPORT.write_text("\n".join(lines), encoding="utf-8")


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
    chunks: list[bytes] = []
    captured = 0
    for window in _read_windows(read_window_seconds):
        deadline = time.monotonic() + window
        while captured < byte_limit and time.monotonic() <= deadline:
            waiting = int(getattr(connection, "in_waiting", 0) or 0)
            chunk = connection.read(min(chunk_size if waiting <= 0 else waiting, byte_limit - captured))
            if not chunk:
                time.sleep(0.05)
                if not waiting:
                    break
                continue
            chunks.append(chunk)
            captured += len(chunk)
            if not waiting:
                break
        if captured:
            if not int(getattr(connection, "in_waiting", 0) or 0):
                break
            time.sleep(0.1)
            continue
    return b"".join(chunks).decode("utf-8", errors="replace")


def _read_windows(read_window_seconds: float) -> list[float]:
    base = max(read_window_seconds, 0.2)
    return [base, max(base, 0.8), max(base, 1.5)]


def _toggle_dtr_rts(connection: Any) -> None:
    for attr in ("dtr", "rts"):
        if not hasattr(connection, attr):
            continue
        try:
            setattr(connection, attr, False)
            time.sleep(0.05)
            setattr(connection, attr, True)
        except Exception:
            continue


def _send_break(connection: Any) -> None:
    try:
        if hasattr(connection, "send_break"):
            connection.send_break(duration=0.25)
    except TypeError:
        connection.send_break()
    except Exception:
        return


def _serial_open_prompt_state(exc: BaseException) -> str:
    text = str(exc).lower()
    if "permission" in text or "access denied" in text:
        return "permission-denied"
    if "busy" in text or "in use" in text or "resource temporarily unavailable" in text:
        return "port-in-use"
    return "unknown"


def _serial_error_summary(exc: BaseException) -> str:
    state = _serial_open_prompt_state(exc)
    if state == "permission-denied":
        return "permission denied opening serial port"
    if state == "port-in-use":
        return "serial port appears to be in use"
    detail = str(exc).strip()
    if detail:
        return f"{exc.__class__.__name__}: {detail}"
    return exc.__class__.__name__


def _final_prompt_state(prompt_sample: dict[str, Any]) -> str:
    if not bool(prompt_sample.get("captured")):
        return "unknown"
    if prompt_sample.get("last_line") == "unreadable console text":
        return "unreadable"
    return "unknown"


def _classification_for_state(prompt_state: str, prompt_sample: object) -> str:
    if (
        prompt_state == "unknown"
        and isinstance(prompt_sample, dict)
        and not bool(prompt_sample.get("captured"))
    ):
        return "no_bytes_read"
    return PROMPT_STATE_CLASSIFICATIONS.get(prompt_state, "no_bytes_read")


def _prompt_state(prompt_text: str) -> str:
    lower_text = prompt_text.lower()
    if not prompt_text:
        return "unknown"
    if (
        "initial configuration dialog" in lower_text
        or "would you like to enter the initial configuration dialog" in lower_text
        or "system configuration dialog" in lower_text
        or "[yes/no]" in lower_text
    ):
        return "setup-wizard"
    if re.search(r"(?im)(?:^|\r|\n)\s*rommon(?:\s+\d+)?\s*>\s*$", prompt_text) or re.search(
        r"(?im)(?:^|\r|\n)\s*switch:\s*$",
        prompt_text,
    ):
        return "rommon-bootloader"
    if "password:" in lower_text:
        return "password-required"
    if "username:" in lower_text or "login:" in lower_text:
        return "login-required"
    if "(config" in lower_text:
        return "config-mode"
    if _looks_unreadable(prompt_text):
        return "unreadable"

    lines = [line.strip() for line in prompt_text.splitlines() if line.strip()]
    if not lines:
        return "unknown"
    last_line = lines[-1]
    if last_line.endswith("#"):
        return "privileged-exec"
    if last_line.endswith(">"):
        return "exec"
    return "unknown"


def _looks_unreadable(prompt_text: str) -> bool:
    if not prompt_text:
        return False
    replacement_count = prompt_text.count("\ufffd")
    control_count = sum(1 for char in prompt_text if ord(char) < 32 and char not in "\r\n\t")
    visible_count = sum(1 for char in prompt_text if char.isprintable() and not char.isspace())
    total = max(len(prompt_text), 1)
    return (replacement_count + control_count) / total > 0.2 or (total >= 8 and visible_count == 0)


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
        if _cisco_console_credentials_configured():
            return "Console is at a login prompt; use the guarded Cisco privilege/bootstrap workflow to authenticate before readiness."
        return "Console is at a login prompt; configure Cisco console credentials in local ignored real-lab config before guarded authentication."
    if prompt_state == "password-required":
        if _cisco_console_credentials_configured():
            return "Console is requesting a password; prompt readiness did not send credentials, use the guarded Cisco privilege/bootstrap workflow."
        return "Console is requesting a password; configure Cisco console credentials in local ignored real-lab config before guarded authentication."
    if prompt_state == "privileged-exec":
        return "Privileged exec prompt was detected; no configuration commands were sent."
    if prompt_state == "config-mode":
        return "Console appears to be in configuration mode; no commands were sent."
    if prompt_state == "unreadable":
        return "Console returned unreadable text; this usually indicates the wrong baud rate or line settings."
    if prompt_state == "rommon-bootloader":
        return "Console appears to be at ROMMON or a bootloader prompt; use manual recovery guidance."
    if prompt_state == "port-in-use":
        return "Serial console port is already in use by another process."
    if prompt_state == "permission-denied":
        return "Serial console port permission was denied for the backend user."
    return "Console prompt could not be identified; no show commands were sent."


def _prompt_readiness_status(prompt_state: str) -> str:
    return "ok" if prompt_state in {"exec", "privileged-exec"} else "blocked"


def _prompt_readiness_message(prompt_state: str, prompt_sample: dict[str, Any]) -> str:
    if prompt_state in {"exec", "privileged-exec"}:
        return "Prompt is ready for future safe show-command checks."
    return _prompt_blocker_message(prompt_state, prompt_sample)


def _prompt_classification(
    prompt_state: str,
    prompt_sample: object,
) -> dict[str, Any]:
    guidance = PROMPT_CLASSIFICATION_GUIDANCE.get(
        prompt_state,
        PROMPT_CLASSIFICATION_GUIDANCE["unknown"],
    )
    no_output = (
        prompt_state == "unknown"
        and isinstance(prompt_sample, dict)
        and not bool(prompt_sample.get("captured"))
    )
    summary = (
        "Console port opened, but no prompt text was captured."
        if no_output
        else guidance["summary"]
    )
    return {
        "state": prompt_state,
        "classification": _classification_for_state(prompt_state, prompt_sample),
        "label": guidance["label"],
        "summary": summary,
        "no_output_captured": no_output,
        "raw_text_redacted": True,
        "safe_show_commands_allowed": False,
        "next_safe_action": _prompt_next_safe_action(prompt_state, prompt_sample),
    }


def _prompt_next_safe_action(prompt_state: str, prompt_sample: object) -> str:
    if (
        prompt_state == "unknown"
        and isinstance(prompt_sample, dict)
        and not bool(prompt_sample.get("captured"))
    ):
        return (
            "Verify adapter ownership, cable placement, power state, and baud 9600/115200 "
            "before running another newline-only readiness check."
        )
    if prompt_state in {"login-required", "password-required"}:
        if _cisco_console_credentials_configured():
            return "Run the guarded Cisco privilege/bootstrap workflow from local-lab-readwrite mode; prompt readiness will not send credentials."
        return "Add Cisco console credentials to the ignored real-lab environment, then rerun the guarded Cisco privilege/bootstrap workflow."
    guidance = PROMPT_CLASSIFICATION_GUIDANCE.get(
        prompt_state,
        PROMPT_CLASSIFICATION_GUIDANCE["unknown"],
    )
    return str(guidance["next_safe_action"])


def _cisco_console_credentials_configured() -> bool:
    return bool(settings.cisco_test_username and settings.cisco_test_password)


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
    if _looks_unreadable(line):
        return "unreadable console text"
    if line.endswith("#"):
        return "DEVICE#"
    if line.endswith(">"):
        return "DEVICE>"
    if "(config" in lower_line:
        return "configuration prompt"
    return "unrecognized prompt"


def _command_summary(command: str, output: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "command": command,
        "captured": bool(output),
        "output_bytes": len(output.encode("utf-8", errors="replace")),
        "raw_output_redacted": True,
    }
    if command == "show version":
        summary["version_hint"] = _ios_xe_version(output)
        summary["bootloader_rommon_hint"] = _bootloader_rommon_version(output)
    return summary


def _ios_xe_version(output: str) -> str | None:
    patterns = (
        r"Cisco IOS XE Software[^,\n]*,\s*Version\s+([^,\s]+)",
        r"Cisco IOS Software[^,\n]*,\s*Version\s+([^,\s]+)",
        r"\bVersion\s+(\d+(?:\.\d+)+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, output, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _bootloader_rommon_version(output: str) -> str | None:
    match = re.search(r"(?:ROMMON|BOOTLDR|BOOT LOADER)[^0-9]*(\d+(?:\.\d+)+)", output, re.IGNORECASE)
    return match.group(1) if match else None


def _write_cisco_firmware_inventory_report(result: dict[str, Any]) -> None:
    CISCO_FIRMWARE_INVENTORY_REPORT.parent.mkdir(parents=True, exist_ok=True)
    commands = result.get("safe_show_commands") if isinstance(result.get("safe_show_commands"), list) else []
    lines = [
        "# Cisco Firmware Inventory Report",
        "",
        f"- Status: {result.get('status', 'unknown')}",
        f"- Source: {result.get('source') or 'console'}",
        f"- Prompt state: {result.get('prompt_state', 'unknown')}",
        f"- Console classification: {_classification_for_state(str(result.get('prompt_state') or 'unknown'), result.get('prompt_sample') or {'captured': False})}",
        f"- Selected baud: {result.get('selected_baud') or 'not selected'}",
        f"- IOS XE version: {result.get('ios_xe_version') or 'unknown'}",
        f"- Bootloader/ROMMON: {result.get('bootloader_rommon') or 'unknown'}",
        f"- Next physical/operator action: {result.get('next_safe_action') or _prompt_next_safe_action(str(result.get('prompt_state') or 'unknown'), result.get('prompt_sample') or {'captured': False})}",
        "",
        "## Command Evidence",
    ]
    if commands:
        for command in commands:
            if not isinstance(command, dict):
                continue
            lines.append(
                "- "
                f"{command.get('command')}: captured={command.get('captured')} "
                f"version_hint={command.get('version_hint') or 'unknown'} "
                f"raw_output_redacted={command.get('raw_output_redacted')}"
            )
    else:
        lines.append("- No show-command evidence was captured.")
    historical = result.get("historical_evidence") if isinstance(result.get("historical_evidence"), dict) else None
    lines.extend(["", "## Historical Evidence"])
    if historical:
        lines.extend(
            [
                f"- Source: {historical.get('source') or 'unknown'}",
                f"- Checked at: {historical.get('checked_at') or 'unknown'}",
                f"- IOS XE version: {historical.get('ios_xe_version') or 'unknown'}",
                f"- Bootloader/ROMMON: {historical.get('bootloader_rommon') or 'unknown'}",
                "- Marked historical: true",
            ]
        )
    else:
        lines.append("- none")
    blockers = result.get("blockers") if isinstance(result.get("blockers"), list) else []
    warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
    lines.extend(["", "## Blockers", *(f"- {item}" for item in blockers), ""])
    if not blockers:
        lines.insert(-1, "- none")
    lines.extend(["## Warnings", *(f"- {item}" for item in warnings), ""])
    if not warnings:
        lines.insert(-1, "- none")
    lines.extend(
        [
            "## Safety",
            "- Read-only console path only.",
            "- No privileged exec requirement was used for show version.",
            "- No firmware update commands were run.",
            "- Raw console output was not saved.",
            "",
        ]
    )
    CISCO_FIRMWARE_INVENTORY_REPORT.write_text("\n".join(lines), encoding="utf-8")


def _operator_message(status: str, recommended_path: str | None) -> str:
    if status == "missing-console":
        return NO_CONSOLE_ADAPTER_MESSAGE
    if recommended_path:
        return (
            f"Preferred console path: {recommended_path}. Use this stable path for "
            "CISCO_CONSOLE_PORT instead of /dev/ttyUSB0 when possible."
        )
    return "Review Cisco serial console discovery before running prompt readiness."
