from __future__ import annotations

import glob
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.probe_cache import get_probe_result, record_probe_result

PROVIDER_ID = "cisco-console"
SAFE_SHOW_COMMANDS = (
    "show version",
    "show inventory",
    "show interfaces status",
    "show ip interface brief",
    "show vlan brief",
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

    @classmethod
    def from_settings(cls) -> "CiscoConsoleConfig":
        return cls(
            port=settings.cisco_console_port,
            baud=settings.cisco_console_baud,
            timeout_seconds=settings.cisco_console_timeout_seconds,
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
    safe_next_action = (
        "Connect a USB serial console cable and refresh provider status. "
        "Stable /dev/serial/by-id paths are preferred."
    )

    if env_override["configured"]:
        effective_path = str(env_override["path"])
        status = "ready"
        safe_next_action = "Run an explicit read-only probe after confirming the console target."
        _mark_recommendation(candidates, effective_path, "env-override")
        if not env_override["exists"]:
            status = "blocked"
            blockers.append("Configured CISCO_CONSOLE_PORT does not exist on this host.")
            safe_next_action = "Update CISCO_CONSOLE_PORT or unplug/reconnect the console cable."
        elif not _is_accessible(env_override):
            status = "blocked"
            blockers.append("Configured CISCO_CONSOLE_PORT is not readable and writable.")
            safe_next_action = "Check device permissions for the backend user."
    elif len(existing_stable) == 1:
        recommended_path = existing_stable[0].path
        effective_path = recommended_path
        status = "ready"
        _mark_recommendation(candidates, recommended_path, "recommended-default")
        safe_next_action = "Run an explicit read-only probe against the recommended stable path."
        if not _candidate_accessible(existing_stable[0]):
            status = "blocked"
            blockers.append("The recommended stable console path is not readable and writable.")
            safe_next_action = "Check device permissions for the backend user."
    elif len(existing_stable) > 1:
        status = "needs-selection"
        blockers.append(
            "Multiple stable serial console candidates were discovered; set "
            "CISCO_CONSOLE_PORT to the intended /dev/serial/by-id path."
        )
        safe_next_action = "Select the intended stable path in .env.local.providers."
    elif existing_candidates:
        status = "needs-selection"
        blockers.append(
            "Only fallback /dev/ttyUSB or /dev/ttyACM candidates were discovered; set "
            "CISCO_CONSOLE_PORT to the intended path before probing."
        )
        safe_next_action = "Prefer a stable /dev/serial/by-id path when the lab cable exposes one."
    else:
        blockers.append(
            "No Cisco serial console candidates were found under /dev/serial/by-id, "
            "/dev/ttyUSB*, or /dev/ttyACM*."
        )

    if existing_candidates and not existing_stable:
        warnings.append("No stable /dev/serial/by-id console path was found.")

    return {
        "status": status,
        "candidates": [asdict(candidate) for candidate in candidates],
        "recommended_path": recommended_path,
        "effective_path": effective_path,
        "env_override": env_override,
        "blockers": blockers,
        "warnings": warnings,
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
        probe_enabled = (
            self.provider_mode == "local-readonly"
            and discovery["status"] == "ready"
            and bool(discovery["effective_path"])
        )
        warnings = list(discovery["warnings"])
        if self.provider_mode != "local-readonly":
            warnings.append(
                "Provider mode is not local-readonly; Cisco probe actions are disabled."
            )

        return ProviderStatus(
            id=PROVIDER_ID,
            name="Cisco Console",
            kind="network-console",
            mode=self.provider_mode,
            status=discovery["status"],
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
            },
            discovery=discovery,
            blockers=list(discovery["blockers"]),
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
                        else "Requires PROVIDER_MODE=local-readonly and one effective console path."
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
                prompt_text = _read_console(connection)
                prompt_state = _prompt_state(prompt_text)
                if prompt_state != "exec":
                    return self._record_blocked(
                        _prompt_blocker_message(prompt_state),
                        discovery=discovery,
                        prompt_state=prompt_state,
                        prompt_sample=_trim_console(prompt_text),
                    )

                command_outputs: dict[str, str] = {}
                for command in SAFE_SHOW_COMMANDS:
                    connection.write(f"{command}\n".encode("ascii"))
                    command_outputs[command] = _trim_console(_read_console(connection))

                return self._record_result(
                    {
                        "provider_id": PROVIDER_ID,
                        "status": "ok",
                        "message": "Read-only Cisco console probe completed.",
                        "port": port,
                        "baud": self.config.baud,
                        "prompt_state": prompt_state,
                        "commands": command_outputs,
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
        return record_probe_result(PROVIDER_ID, result)


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


def _read_console(connection: Any) -> str:
    time.sleep(0.2)
    chunks = [connection.read(4096)]
    while getattr(connection, "in_waiting", 0):
        chunks.append(connection.read(4096))
    return b"".join(chunks).decode("utf-8", errors="replace")


def _prompt_state(prompt_text: str) -> str:
    lower_text = prompt_text.lower()
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


def _prompt_blocker_message(prompt_state: str) -> str:
    if prompt_state == "login-required":
        return "Console requires login or password; credentials are not configured for this probe."
    if prompt_state == "config-mode":
        return "Console appears to be in configuration mode; no commands were sent."
    return "Console prompt could not be identified; no show commands were sent."


def _trim_console(value: str) -> str:
    return value[-12000:]
