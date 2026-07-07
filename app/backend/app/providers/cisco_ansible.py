from __future__ import annotations

import json
import importlib.util
import os
import re
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Any

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.lab_safety import current_lab_safety
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive
from app.services.temp_file_utils import remove_file_best_effort

PROVIDER_ID = "cisco-ansible"
MAX_ATTEMPTS = 3
SSH_PORT = 22
SAFE_SHOW_COMMANDS = (
    "show version",
    "show inventory",
    "show interfaces status",
    "show ip interface brief",
    "show vlan brief",
    "show running-config | include spanning-tree portfast",
    "show running-config | include spanning-tree bpduguard",
    "show running-config | include ip access-list|ip access-group",
)


@dataclass(frozen=True)
class CiscoAnsibleConfig:
    host: str | None
    username: str | None
    password: str | None
    enable_password: str | None
    network_os: str
    connection: str
    timeout_seconds: float
    management_configured: bool = False
    control_host: str | None = None

    @classmethod
    def from_settings(cls) -> "CiscoAnsibleConfig":
        return cls(
            host=settings.cisco_target_ip,
            control_host=settings.ansible_control_host,
            username=settings.cisco_test_username,
            password=settings.cisco_test_password,
            enable_password=settings.cisco_enable_password,
            network_os=_normalize_network_os(settings.ansible_cisco_network_os),
            connection=_normalize_connection(settings.ansible_cisco_connection),
            timeout_seconds=settings.ansible_cisco_timeout_seconds,
            management_configured=settings.cisco_mgmt_configured,
        )

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        if not self.host:
            missing.append("CISCO_TARGET_IP")
        if not self.username:
            missing.append("CISCO_TEST_USERNAME")
        if not self.password:
            missing.append("CISCO_TEST_PASSWORD")
        return missing


class CiscoAnsibleAdapter:
    def __init__(
        self,
        provider_mode: str | None = None,
        config: CiscoAnsibleConfig | None = None,
    ) -> None:
        self.provider_mode = provider_mode or settings.provider_mode
        self.config = config or CiscoAnsibleConfig.from_settings()

    def health(self) -> ProviderStatus:
        last_result, last_time = get_probe_result(PROVIDER_ID)
        missing_fields = self.config.missing_fields
        safety = current_lab_safety()
        policy = current_lab_action_policy(self.provider_mode)
        tool_availability = _tool_availability()
        planned_target = bool(self.config.host)
        blockers: list[str] = []
        if self.config.management_configured and missing_fields:
            blockers.append(
                f"Missing local Cisco Ansible configuration: {', '.join(missing_fields)}."
            )
        if self.config.management_configured and self.provider_mode in REAL_CONTACT_MODES:
            blockers.extend(policy.readonly_blockers())

        warnings: list[str] = []
        if self.provider_mode not in REAL_CONTACT_MODES:
            warnings.append(
                "Provider mode is not local-readonly or local-lab-readwrite; Cisco Ansible probes are disabled."
            )
        if not self.config.management_configured:
            warnings.append(
                "CISCO_MGMT_CONFIGURED is false; Cisco SSH and Ansible probes are skipped. "
                "Use console first contact/bootstrap before Ansible."
            )
        if self.config.management_configured and (
            not tool_availability["ansible_available"]
            or not tool_availability["ansible_inventory_available"]
        ):
            if tool_availability["paramiko_available"]:
                warnings.append(
                    "Ansible CLI is not available; using Paramiko fallback for fixed read-only Cisco show commands."
                )
            else:
                warnings.append(
                    "Ansible CLI is not available and Paramiko fallback is unavailable; SSH reachability can be checked, "
                    "but inventory parsing and show commands will be blocked."
                )

        status = "awaiting-bootstrap" if planned_target else "not-configured"
        if self.config.management_configured:
            status = "missing-config" if missing_fields else "ready"
        if (
            self.config.management_configured
            and not missing_fields
            and self.provider_mode not in REAL_CONTACT_MODES
        ):
            status = "configured"
        if (
            self.config.management_configured
            and not missing_fields
            and self.provider_mode in REAL_CONTACT_MODES
            and not policy.readonly_allowed
        ):
            status = "blocked"

        probe_enabled = (
            self.provider_mode in REAL_CONTACT_MODES
            and self.config.management_configured
            and not missing_fields
            and policy.readonly_allowed
        )
        disabled_reason = "Use console bootstrap before Ansible SSH."

        return ProviderStatus(
            id=PROVIDER_ID,
            name="Cisco Ansible SSH",
            kind="network-automation",
            mode=self.provider_mode,
            status=status,
            capabilities=[
                "explicit-read-only-probe",
                "ssh-reachability-check",
                "ansible-inventory-parse",
                "safe-show-commands",
            ],
            message=(
                "Cisco management-IP automation is separated from console discovery; "
                "the probe action is available only after CISCO_MGMT_CONFIGURED=true and "
                "checks SSH plus fixed read-only show commands only."
            ),
            configuration={
                "management_configured": self.config.management_configured,
                "planned_target": planned_target,
                "host_configured": bool(self.config.host),
                "control_host_configured": bool(self.config.control_host),
                "ansible_control_host": self.config.control_host,
                "ansible_role": (
                    "post-console-bootstrap show commands, backup, validation, drift checks, "
                    "and future repeatable config"
                ),
                "first_contact_path": "Cisco console bootstrap; Ansible starts after management SSH is configured.",
                "username_configured": bool(self.config.username),
                "password_configured": bool(self.config.password),
                "enable_password_configured": bool(self.config.enable_password),
                "network_os": self.config.network_os,
                "connection": self.config.connection,
                "timeout_seconds": self.config.timeout_seconds,
                "missing_fields": missing_fields,
                "safe_next_action": (
                    "Check SSH, parse inventory, and run fixed safe show commands."
                    if probe_enabled
                    else disabled_reason
                ),
                **tool_availability,
                **safety.as_flags(),
            },
            blockers=blockers,
            warnings=warnings,
            safe_actions=[
                ProviderAction(
                    id="probe-cisco-ansible",
                    label="Read-Only Probe",
                    enabled=probe_enabled,
                    read_only=True,
                    reason=(
                        "Check SSH, parse inventory, and run fixed safe show commands."
                        if probe_enabled
                        else disabled_reason
                        if not self.config.management_configured
                        else (
                            "Requires Cisco target, credentials, LAB_CLOSED_LOOP_ACK=YES, "
                            "LAB_READONLY_ACK=YES, and PROVIDER_MODE=local-readonly; or "
                            "complete local-lab-readwrite acknowledgements."
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

    def probe(self, extra_show_commands: list[str] | None = None) -> dict[str, Any]:
        if self.provider_mode not in REAL_CONTACT_MODES:
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running Cisco Ansible probes."
            )

        if not self.config.management_configured:
            return self._record_skipped(
                "CISCO_MGMT_CONFIGURED is false; use console bootstrap before Ansible SSH.",
                planned_target=bool(self.config.host),
            )

        policy = current_lab_action_policy(self.provider_mode)
        if not policy.readonly_allowed:
            return self._record_blocked(
                "Required lab acknowledgement flags are missing before real lab probes.",
                action_policy=policy.as_flags(),
            )

        if self.config.missing_fields:
            return self._record_blocked(
                f"Missing local Cisco Ansible configuration: {', '.join(self.config.missing_fields)}.",
                missing_fields=self.config.missing_fields,
            )

        assert self.config.host is not None
        phases = [
            {
                "tag": "DISCOVER",
                "message": "Checking Cisco management SSH reachability before Ansible commands.",
            }
        ]
        blockers: list[str] = []
        warnings: list[str] = []
        ssh_reachability = _tcp_connect(self.config.host, SSH_PORT, self.config.timeout_seconds)
        if not ssh_reachability["reachable"]:
            return self._record_result(
                {
                    "provider_id": PROVIDER_ID,
                    "status": "blocked",
                    "message": "Cisco SSH is not reachable; Ansible show commands were not attempted.",
                    "phases": phases
                    + [
                        {
                            "tag": "BLOCKED",
                            "message": "SSH reachability failed.",
                        }
                    ],
                    "ssh_reachability": ssh_reachability,
                    "warnings": warnings,
                    "blockers": ["Cisco SSH is not reachable."],
                    "not_attempted": ["Ansible inventory parse", "safe show commands"],
                }
            )

        ansible_bin = which("ansible")
        inventory_bin = which("ansible-inventory")
        if not ansible_bin or not inventory_bin:
            paramiko_result = _paramiko_show_commands(self.config, ssh_reachability, extra_show_commands)
            if paramiko_result["status"] == "ok":
                phases.append(
                    {
                        "tag": "PLAN",
                        "message": "Ansible CLI unavailable; running fixed read-only Cisco show commands through Paramiko.",
                    }
                )
                phases.append(
                    {
                        "tag": "VERIFY",
                        "message": "Cisco Paramiko read-only probe completed.",
                    }
                )
                return self._record_result(
                    {
                        "provider_id": PROVIDER_ID,
                        "status": "ok",
                        "message": "Read-only Cisco SSH probe completed through Paramiko fallback.",
                        "phases": phases,
                        "ssh_reachability": ssh_reachability,
                        "inventory_target": self.config.host,
                        "ansible_control_host": self.config.control_host,
                        "tool_availability": _tool_availability(),
                        "fallback": "paramiko",
                        "safe_show_commands": list(SAFE_SHOW_COMMANDS),
                        "command_results": paramiko_result["command_results"],
                        "not_attempted": _not_attempted_config_actions(),
                        "warnings": ["Ansible CLI is not available; used Paramiko read-only fallback."],
                        "blockers": [],
                    }
                )
            return self._record_result(
                {
                    "provider_id": PROVIDER_ID,
                    "status": "blocked",
                    "message": "Ansible CLI is not available; Cisco SSH commands were not attempted.",
                    "phases": phases
                    + [
                        {
                            "tag": "BLOCKED",
                            "message": "ansible and ansible-inventory must be installed.",
                        }
                    ],
                    "ssh_reachability": ssh_reachability,
                    "tool_availability": _tool_availability(),
                    "fallback": "paramiko",
                    "fallback_result": paramiko_result,
                    "warnings": warnings,
                    "blockers": ["Ansible CLI is not available.", *(paramiko_result.get("blockers") or [])],
                    "not_attempted": ["Ansible inventory parse", "safe show commands"],
                }
            )

        inventory_path = _write_temp_inventory(self.config)
        try:
            ansible_version = _run_command(
                [ansible_bin, "--version"],
                timeout_seconds=self.config.timeout_seconds,
            )
            inventory_parse = _run_command(
                [inventory_bin, "-i", str(inventory_path), "--graph"],
                timeout_seconds=self.config.timeout_seconds,
            )
            if inventory_parse["returncode"] != 0:
                blockers.append("Ansible inventory parse failed.")

            command_results: dict[str, Any] = {}
            if not blockers:
                phases.append(
                    {
                        "tag": "PLAN",
                        "message": "Running fixed read-only Cisco show commands through Ansible.",
                    }
                )
                for command in (*SAFE_SHOW_COMMANDS, *(extra_show_commands or [])):
                    command_results[command] = _run_command(
                        [
                            ansible_bin,
                            "-i",
                            str(inventory_path),
                            "cisco_target",
                            "-m",
                            "cisco.ios.ios_command",
                            "-a",
                            json.dumps({"commands": [command]}),
                        ],
                        timeout_seconds=self.config.timeout_seconds,
                        include_output=False,
                    )
                    if command_results[command]["returncode"] != 0:
                        blockers.append(f"Ansible command failed: {command}.")
                        break
            else:
                command_results = {}
        finally:
            remove_file_best_effort(inventory_path, scrub=True)

        status = "ok" if not blockers else "failed"
        phases.append(
            {
                "tag": "VERIFY" if status == "ok" else "BLOCKED",
                "message": (
                    "Cisco Ansible read-only probe completed."
                    if status == "ok"
                    else "Cisco Ansible read-only probe stopped with blockers."
                ),
            }
        )

        return self._record_result(
            {
                "provider_id": PROVIDER_ID,
                "status": status,
                "message": (
                    "Read-only Cisco Ansible probe completed."
                    if status == "ok"
                    else "Read-only Cisco Ansible probe could not complete."
                ),
                "phases": phases,
                "ssh_reachability": ssh_reachability,
                "inventory_target": self.config.host,
                "ansible_control_host": self.config.control_host,
                "tool_availability": _tool_availability(),
                "ansible_version": ansible_version,
                "inventory_parse": inventory_parse,
                "safe_show_commands": list(SAFE_SHOW_COMMANDS),
                "command_results": command_results,
                "not_attempted": _not_attempted_config_actions(),
                "warnings": warnings,
                "blockers": blockers,
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

    def _record_skipped(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._record_result(
            {
                "provider_id": PROVIDER_ID,
                "status": "skipped",
                "message": message,
                "warnings": [message],
                "blockers": [],
                "not_attempted": [
                    "Cisco SSH reachability check",
                    "Ansible inventory parse",
                    "safe show commands",
                ],
                **extra,
            }
        )

    def _record_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return record_probe_result(PROVIDER_ID, redact_sensitive(result, self._redaction_values()))

    def _redaction_values(self) -> list[str | None]:
        return [
            self.config.host,
            self.config.username,
            self.config.password,
            self.config.enable_password,
        ]


def _tcp_connect(host: str, port: int, timeout_seconds: float) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds):
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "ok",
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                return {"reachable": True, "port": port, "attempts": attempts}
        except OSError as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error": exc.__class__.__name__,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            )
    return {"reachable": False, "port": port, "attempts": attempts}


def _validated_extra_show_commands(raw_commands: Any) -> list[str]:
    commands: list[str] = []
    if not isinstance(raw_commands, list):
        return commands
    for raw in raw_commands[:4]:
        command = str(raw or "").strip()
        interface_match = re.fullmatch(r"show interface\s+(Gi1/0/(?:[1-9]|[1-3][0-9]|4[0-8]))", command, re.IGNORECASE)
        run_match = re.fullmatch(r"show running-config interface\s+(Gi1/0/(?:[1-9]|[1-3][0-9]|4[0-8]))", command, re.IGNORECASE)
        if command.lower() == "show interfaces status" or interface_match or run_match:
            commands.append(command)
    return commands


def _paramiko_show_commands(config: CiscoAnsibleConfig, ssh_reachability: dict[str, Any], extra_show_commands: list[str] | None = None) -> dict[str, Any]:
    if not ssh_reachability.get("reachable"):
        return {"status": "blocked", "blockers": ["Cisco SSH is not reachable."]}
    try:
        import paramiko  # type: ignore[import-untyped]
    except ImportError:
        return {"status": "blocked", "blockers": ["Paramiko is not available for SSH fallback."]}
    if not config.host or not config.username or not config.password:
        return {"status": "blocked", "blockers": ["Cisco SSH fallback is missing host, username, or password."]}

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=config.host,
            port=SSH_PORT,
            username=config.username,
            password=config.password,
            look_for_keys=False,
            allow_agent=False,
            timeout=config.timeout_seconds,
            auth_timeout=config.timeout_seconds,
            banner_timeout=config.timeout_seconds,
        )
        channel = client.invoke_shell(width=160, height=80)
        _read_paramiko_channel(channel, seconds=1.5)
        command_results: dict[str, Any] = {}
        for command in ("terminal length 0", *SAFE_SHOW_COMMANDS, *(extra_show_commands or [])):
            channel.send(command + "\n")
            output = _read_paramiko_channel(channel, seconds=max(config.timeout_seconds, 3.0))
            command_results[command] = _paramiko_command_summary(command, output)
            if command in SAFE_SHOW_COMMANDS and not command_results[command]["captured"]:
                return {
                    "status": "blocked",
                    "command_results": command_results,
                    "blockers": [f"Paramiko command returned no output: {command}."],
                }
        return {"status": "ok", "command_results": command_results, "blockers": []}
    except Exception as exc:
        return {"status": "blocked", "blockers": [f"Paramiko SSH fallback failed: {exc.__class__.__name__}."]}
    finally:
        client.close()


def _read_paramiko_channel(channel: Any, *, seconds: float) -> str:
    chunks: list[bytes] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if channel.recv_ready():
            chunks.append(channel.recv(65535))
            deadline = time.monotonic() + 0.4
        else:
            time.sleep(0.1)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _paramiko_command_summary(command: str, output: str) -> dict[str, Any]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    summary: dict[str, Any] = {
        "returncode": 0 if output.strip() else 1,
        "captured": bool(output.strip()),
        "bytes": len(output.encode("utf-8", errors="replace")),
        "line_count": len(lines),
        "raw_output_redacted": True,
        "has_vlan_table_header": bool(re.search(r"(?is)\bVLAN\s+Name\s+Status\s+Ports\b", output)),
        "has_vlan_1": bool(re.search(r"(?m)^\s*1\s+", output)),
        "looks_ontap": "::>" in output or "cluster " in output.lower(),
        "stdout_summary": lines[:12],
        "stderr_summary": "",
        "command": command,
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


def _not_attempted_config_actions() -> list[str]:
    return [
        "configure terminal",
        "write memory",
        "reload",
        "copy or erase",
        "VLAN, interface, user, or firmware changes",
        "running-config backup",
    ]


def _write_temp_inventory(config: CiscoAnsibleConfig) -> Path:
    host_vars: dict[str, Any] = {
        "ansible_host": config.host,
        "ansible_user": config.username,
        "ansible_password": config.password,
        "ansible_connection": config.connection,
        "ansible_network_os": config.network_os,
        "ansible_command_timeout": int(config.timeout_seconds),
        "ansible_connect_timeout": int(config.timeout_seconds),
    }
    if config.enable_password:
        host_vars.update(
            {
                "ansible_become": True,
                "ansible_become_method": "enable",
                "ansible_become_password": config.enable_password,
            }
        )

    inventory = {
        "all": {
            "hosts": {
                "cisco_target": host_vars
            }
        }
    }
    fd, name = tempfile.mkstemp(prefix="infra-config-cisco-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(inventory, handle)
        os.chmod(name, 0o600)
    except Exception:
        remove_file_best_effort(name, scrub=True)
        raise
    return Path(name)


def _run_command(
    args: list[str],
    timeout_seconds: float,
    include_output: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            env=_ansible_env(),
            text=True,
            timeout=timeout_seconds,
        )
        result = {
            "returncode": completed.returncode,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        if include_output:
            result.update(
                {
                    "stdout_tail": _tail(completed.stdout),
                    "stderr_tail": _tail(completed.stderr),
                }
            )
        else:
            result.update(_redacted_output_summary(completed.stdout, completed.stderr))
        return result
    except subprocess.TimeoutExpired as exc:
        result = {
            "returncode": 124,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        if include_output:
            result.update(
                {
                    "stdout_tail": _tail(_stream_text(exc.stdout)),
                    "stderr_tail": "timeout",
                }
            )
        else:
            result.update(_redacted_output_summary(exc.stdout, exc.stderr))
            result["stderr_summary"] = "timeout"
        return result


def _tail(value: str | bytes | None) -> str:
    return _stream_text(value)[-12000:]


def _stream_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _stream_length(value: str | bytes | None) -> int:
    if value is None:
        return 0
    if isinstance(value, bytes):
        return len(value)
    return len(value.encode("utf-8", errors="replace"))


def _redacted_output_summary(
    stdout: str | bytes | None,
    stderr: str | bytes | None,
) -> dict[str, Any]:
    return {
        "stdout_bytes": _stream_length(stdout),
        "stderr_bytes": _stream_length(stderr),
        "raw_output_redacted": True,
    }


def _ansible_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_LOAD_CALLBACK_PLUGINS": "False",
        }
    )
    for key in (
        "LAB_PASSWORD",
        "ILO_TEST_PASSWORD",
        "ESXI_TEST_PASSWORD",
        "CISCO_TEST_PASSWORD",
        "CISCO_ENABLE_PASSWORD",
        "ANSIBLE_CISCO_PASSWORD",
        "ANSIBLE_CISCO_ENABLE_PASSWORD",
    ):
        env.pop(key, None)
    return env


def _tool_availability() -> dict[str, bool]:
    return {
        "ansible_available": which("ansible") is not None,
        "ansible_inventory_available": which("ansible-inventory") is not None,
        "paramiko_available": importlib.util.find_spec("paramiko") is not None,
    }


def _normalize_network_os(value: str) -> str:
    return "cisco.ios.ios" if value == "ios" else value


def _normalize_connection(value: str) -> str:
    return "ansible.netcommon.network_cli" if value == "network_cli" else value


def _dangerous_actions() -> list[ProviderAction]:
    return [
        ProviderAction(
            id="cisco-configure-terminal",
            label="Configure Terminal",
            enabled=False,
            read_only=False,
            reason="Cisco configuration mode is blocked.",
        ),
        ProviderAction(
            id="cisco-write-memory",
            label="Write Memory",
            enabled=False,
            read_only=False,
            reason="Saving switch configuration is disabled.",
        ),
        ProviderAction(
            id="cisco-reload",
            label="Reload",
            enabled=False,
            read_only=False,
            reason="Reload and restart operations are blocked.",
        ),
        ProviderAction(
            id="cisco-copy-erase",
            label="Copy / Erase",
            enabled=False,
            read_only=False,
            reason="Copy, erase, and firmware operations are blocked.",
        ),
    ]
