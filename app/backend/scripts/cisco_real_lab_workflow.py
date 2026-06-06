from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.cisco_console import (
    CiscoConsoleAdapter,
    CiscoConsoleConfig,
    discover_cisco_console,
)
from app.providers.redaction import redact_sensitive
from app.services.hpe_raid import REPO_ROOT

REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-4h-lab-run-report.md"
FIX_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-privileged-exec-fix-report.md"
PRIVILEGE_HARDENING_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-privilege-hardening-report.md"
DETAILS = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-4h-lab-run-details-redacted.json"
SAMPLES = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-console-samples-redacted.json"
COMMANDS = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-bootstrap-commands-redacted.json"

BAUD_RATES = (9600, 19200, 38400, 57600, 115200)
WAKE_SEQUENCES = (
    {"name": "newline", "bytes": b"\n"},
    {"name": "enter", "bytes": b"\r"},
    {"name": "ctrl-c", "bytes": b"\x03"},
    {"name": "ctrl-z", "bytes": b"\x1a"},
)
SHOW_COMMANDS = (
    "terminal length 0",
    "show privilege",
    "show version",
    "show inventory",
    "show interfaces status",
    "show ip interface brief",
    "show vlan brief",
    "show running-config | include ^hostname|^ip domain-name|^ip ssh|^ip scp|^ip http|^username|^interface Vlan|^ip default-gateway|^lldp run",
)
PROMPT_RE = re.compile(r"(?m)(?:^|\r|\n)([A-Za-z0-9_.:/()-]+(?:\(config[^\)]*\))?[#>])\s*$")


@dataclass(frozen=True)
class Prompt:
    state: str
    text: str
    privileged: bool


@dataclass(frozen=True)
class PrivilegeResult:
    prompt: Prompt
    debug: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cisco real-lab console workflow.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the guarded Cisco console bootstrap when prompt and policy gates pass.",
    )
    args = parser.parse_args()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_mode": settings.provider_mode,
        "stages": {},
        "blockers": [],
        "warnings": [],
        "artifacts": {
            "report": str(REPORT.relative_to(REPO_ROOT)),
            "privileged_exec_fix_report": str(FIX_REPORT.relative_to(REPO_ROOT)),
            "privilege_hardening_report": str(PRIVILEGE_HARDENING_REPORT.relative_to(REPO_ROOT)),
            "details": str(DETAILS.relative_to(REPO_ROOT)),
            "samples": str(SAMPLES.relative_to(REPO_ROOT)),
            "commands": str(COMMANDS.relative_to(REPO_ROOT)),
        },
    }

    policy_blockers = current_lab_action_policy(settings.provider_mode).action_blockers(
        "cisco-console.bootstrap",
        ActionCategory.NETWORK_CONFIG,
    )
    payload["stages"]["policy"] = {
        "status": "ready" if not policy_blockers else "blocked",
        "blockers": policy_blockers,
    }
    if policy_blockers:
        payload["blockers"].extend(policy_blockers)

    discovery = discover_cisco_console(CiscoConsoleConfig.from_settings())
    ownership = _serial_ownership(discovery)
    payload["stages"]["adapter_discovery"] = {
        "status": discovery["status"],
        "effective_path": discovery.get("effective_path"),
        "recommended_path": discovery.get("recommended_path"),
        "selection_source": discovery.get("selection_source"),
        "candidate_counts": discovery.get("candidate_counts"),
        "ownership": ownership,
        "blockers": discovery.get("blockers") or [],
        "warnings": discovery.get("warnings") or [],
    }
    payload["warnings"].extend(discovery.get("warnings") or [])
    payload["blockers"].extend(discovery.get("blockers") or [])
    if ownership["owned"]:
        payload["blockers"].append("Serial console is owned by another process.")

    port = discovery.get("effective_path")
    if discovery["status"] != "ready" or not isinstance(port, str) or policy_blockers or ownership["owned"]:
        return _finish(payload)

    try:
        import serial  # type: ignore[import-untyped]
    except ImportError:
        payload["blockers"].append("pyserial is not installed; real console workflow cannot open serial.")
        return _finish(payload)

    console_result = _detect_console(serial, port, first_baud=settings.cisco_console_baud)
    payload["stages"]["console_prompt_detection"] = console_result["summary"]
    _write_json(SAMPLES, _sanitize(console_result["samples"]))
    if console_result["blockers"]:
        payload["blockers"].extend(console_result["blockers"])
        return _finish(payload)

    selected = console_result["selected"]
    prompt = Prompt(**selected["prompt"])
    baud = int(selected["baud"])
    identity: dict[str, Any] = {}
    apply_result: dict[str, Any] = {"status": "not-attempted", "reason": "Run with --apply after prompt detection succeeds."}
    ethernet: dict[str, Any] = {"status": "not-attempted", "reason": "Bootstrap apply did not run."}

    with serial.Serial(port=port, baudrate=baud, timeout=1.0, write_timeout=1.0) as conn:
        privilege_result = _ensure_privileged(conn, prompt)
        privilege_prompt = privilege_result.prompt
        privilege_debug = privilege_result.debug
        if privilege_prompt.state in {"exec", "privileged-exec"}:
            privilege_debug["privilege_level"] = _read_privilege_level(conn)
        payload["stages"]["privilege_escalation"] = {
            "status": "ready" if privilege_prompt.state == "privileged-exec" else "blocked",
            "initial_prompt_state": privilege_debug["initial_prompt_state"],
            "enable_command_sent": privilege_debug["enable_command_sent"],
            "password_prompt_seen": privilege_debug["password_prompt_seen"],
            "prompt_state": privilege_prompt.state,
            "final_prompt_state": privilege_prompt.state,
            "privilege_level": privilege_debug["privilege_level"],
            "debug": privilege_debug,
            "blockers": []
            if privilege_prompt.state == "privileged-exec"
            else ["Configured console credentials did not reach a privileged exec prompt."],
        }
        capture_prompt = privilege_prompt
        if capture_prompt.state != "privileged-exec":
            capture_prompt = _recover_to_exec(conn)
        if capture_prompt.state in {"exec", "privileged-exec"}:
            identity = _capture_identity(conn)
            identity["privileged"] = capture_prompt.state == "privileged-exec"
        else:
            payload["blockers"].append(f"Exec prompt is required for identity capture; got {capture_prompt.state}.")

        plan = _bootstrap_plan()
        payload["stages"]["switch_identification"] = identity or {"status": "blocked"}
        payload["stages"]["bootstrap_plan"] = plan
        _write_json(COMMANDS, _sanitize({"commands": plan["redacted_commands"]}))

        if privilege_prompt.state != "privileged-exec":
            payload["blockers"].append("Privileged exec prompt is required for bootstrap apply.")

        if args.apply and not payload["blockers"]:
            apply_result = _apply_bootstrap(conn, plan)
            if apply_result["status"] == "completed":
                ethernet = _ethernet_readiness()
            else:
                payload["blockers"].extend(apply_result.get("blockers") or [])
        elif not args.apply:
            payload["warnings"].append("Bootstrap plan was built but not applied because --apply was not set.")

    payload["stages"]["apply"] = apply_result
    payload["stages"]["ethernet_management_validation"] = ethernet
    return _finish(payload)


def _detect_console(serial_module: Any, port: str, *, first_baud: int | None = None) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    baud_rates = _baud_order(first_baud)
    for baud in baud_rates:
        try:
            with serial_module.Serial(port=port, baudrate=baud, timeout=0.8, write_timeout=0.8) as conn:
                conn.reset_input_buffer()
                for sequence in WAKE_SEQUENCES:
                    conn.write(sequence["bytes"])
                    text = _read(conn, window=1.6)
                    prompt = _classify_prompt(text)
                    sample = {
                        "baud": baud,
                        "sequence": sequence["name"],
                        "captured": bool(text),
                        "bytes": len(text.encode("utf-8", errors="replace")),
                        "line_count": len([line for line in text.splitlines() if line.strip()]),
                        "last_line": _redact_line(_last_line(text)),
                        "prompt": prompt.__dict__,
                    }
                    samples.append(sample)
                    if prompt.state in {"exec", "privileged-exec", "setup-wizard", "login-required"}:
                        return {
                            "selected": {"baud": baud, "sequence": sequence["name"], "prompt": prompt.__dict__},
                            "samples": samples,
                            "summary": {
                                "status": "ready",
                                "selected_port": port,
                                "selected_baud": baud,
                                "selected_sequence": sequence["name"],
                                "prompt_state": prompt.state,
                                "prompt_detected": True,
                                "bauds_tried": list(baud_rates),
                                "wake_sequences_tried": [item["name"] for item in WAKE_SEQUENCES],
                            },
                            "blockers": [],
                        }
        except Exception as exc:  # pragma: no cover - hardware dependent
            samples.append(
                {
                    "baud": baud,
                    "sequence": "open",
                    "captured": False,
                    "error": f"serial open/read failed: {exc}",
                    "prompt": Prompt("failed", "", False).__dict__,
                }
            )
    return {
        "selected": None,
        "samples": samples,
        "summary": {
            "status": "blocked",
            "selected_port": None,
            "selected_baud": None,
            "prompt_state": "unknown-no-output"
            if not any(sample.get("captured") for sample in samples)
            else "unknown",
            "prompt_detected": False,
            "bauds_tried": list(baud_rates),
            "wake_sequences_tried": [item["name"] for item in WAKE_SEQUENCES],
        },
        "blockers": [
            "Console adapter opened across common baud rates, but no supported Cisco prompt was detected."
        ],
    }


def _baud_order(first_baud: int | None) -> tuple[int, ...]:
    values = [first_baud, *BAUD_RATES] if first_baud else list(BAUD_RATES)
    return tuple(dict.fromkeys(int(value) for value in values if value))


def _ensure_privileged(conn: Any, prompt: Prompt) -> PrivilegeResult:
    current = prompt
    debug: dict[str, Any] = {
        "initial_prompt_state": prompt.state,
        "setup_wizard_answered_no": False,
        "login_exchange_attempted": False,
        "enable_command_sent": False,
        "enable_commands_attempted": [],
        "password_prompt_seen": False,
        "enable_password_sources_configured": _enable_password_sources_configured(),
        "enable_password_sources_tried": [],
        "final_prompt_state": prompt.state,
        "privilege_level": None,
    }
    if current.state == "setup-wizard":
        _send(conn, "no")
        debug["setup_wizard_answered_no"] = True
        current = _classify_prompt(_read(conn, window=2.0))

    for _ in range(4):
        if current.state == "privileged-exec":
            debug["final_prompt_state"] = current.state
            return PrivilegeResult(current, debug)
        if current.state == "exec":
            result = _enter_enable(conn)
            debug.update(
                {
                    "enable_command_sent": result.debug["enable_command_sent"],
                    "enable_commands_attempted": result.debug["enable_commands_attempted"],
                    "password_prompt_seen": result.debug["password_prompt_seen"],
                    "enable_password_sources_tried": result.debug["enable_password_sources_tried"],
                    "final_prompt_state": result.prompt.state,
                }
            )
            return PrivilegeResult(result.prompt, debug)
        if current.state == "login-required":
            debug["login_exchange_attempted"] = True
            current = _credential_exchange(conn)
            continue
        if current.state == "unknown":
            _send(conn, "")
            current = _classify_prompt(_read(conn, window=1.0))
            if current.state != "unknown":
                continue
        break
    debug["final_prompt_state"] = current.state
    return PrivilegeResult(current, debug)


def _enter_enable(conn: Any) -> PrivilegeResult:
    password_candidates = _enable_password_candidates()
    debug: dict[str, Any] = {
        "enable_command_sent": False,
        "enable_commands_attempted": [],
        "password_prompt_seen": False,
        "enable_password_sources_tried": [],
    }
    parsed = Prompt("unknown", "", False)
    for enable_command in ("enable", "enable 15"):
        _send(conn, enable_command)
        debug["enable_command_sent"] = True
        debug["enable_commands_attempted"].append(enable_command)
        text = _read(conn, window=1.5)
        parsed = _classify_prompt(text)
        if parsed.state == "privileged-exec":
            return PrivilegeResult(parsed, debug)
        if parsed.state == "login-required":
            debug["password_prompt_seen"] = debug["password_prompt_seen"] or _contains_password_prompt(text)
            for candidate in password_candidates:
                debug["enable_password_sources_tried"].append(candidate["sources"])
                challenge = _answer_enable_challenge(conn, text, candidate["value"])
                parsed = challenge.prompt
                debug["password_prompt_seen"] = debug["password_prompt_seen"] or challenge.password_prompt_seen
                if parsed.state == "privileged-exec":
                    return PrivilegeResult(parsed, debug)
                if parsed.state == "exec":
                    break
                text = _read(conn, window=0.5)
        if parsed.state == "exec":
            continue
    _send(conn, "")
    parsed = _classify_prompt(_read(conn, window=1.0))
    return PrivilegeResult(parsed, debug)


@dataclass(frozen=True)
class EnableChallengeResult:
    prompt: Prompt
    password_prompt_seen: bool


def _answer_enable_challenge(conn: Any, text: str, password: str) -> EnableChallengeResult:
    current = text
    password_prompt_seen = False
    for _ in range(3):
        lower = current.lower()
        if "username:" in lower or "login:" in lower:
            if not settings.cisco_test_username:
                return EnableChallengeResult(Prompt("login-required", "username prompt", False), password_prompt_seen)
            _send(conn, settings.cisco_test_username, secret=True)
            current = _read(conn, window=1.0)
            continue
        if "password:" in lower:
            password_prompt_seen = True
            _send(conn, password, secret=True)
            parsed = _classify_prompt(_read(conn, window=1.8))
            if parsed.state == "unknown":
                _send(conn, "")
                parsed = _classify_prompt(_read(conn, window=1.0))
            return EnableChallengeResult(parsed, password_prompt_seen)
        parsed = _classify_prompt(current)
        if parsed.state != "unknown":
            return EnableChallengeResult(parsed, password_prompt_seen)
        _send(conn, "")
        current = _read(conn, window=1.0)
    return EnableChallengeResult(_classify_prompt(current), password_prompt_seen)


def _contains_password_prompt(text: str) -> bool:
    return "password:" in text.lower()


def _enable_password_sources_configured() -> dict[str, bool]:
    return {
        "CISCO_ENABLE_PASSWORD": bool(os.getenv("CISCO_ENABLE_PASSWORD")),
        "ANSIBLE_CISCO_ENABLE_PASSWORD": bool(os.getenv("ANSIBLE_CISCO_ENABLE_PASSWORD")),
        "settings.cisco_enable_password": bool(settings.cisco_enable_password),
        "settings.cisco_test_password": bool(settings.cisco_test_password),
    }


def _enable_password_candidates() -> list[dict[str, Any]]:
    raw_candidates = (
        ("CISCO_ENABLE_PASSWORD", os.getenv("CISCO_ENABLE_PASSWORD")),
        ("ANSIBLE_CISCO_ENABLE_PASSWORD", os.getenv("ANSIBLE_CISCO_ENABLE_PASSWORD")),
        ("settings.cisco_enable_password", settings.cisco_enable_password),
        ("settings.cisco_test_password", settings.cisco_test_password),
    )
    candidates_by_value: dict[str, list[str]] = {}
    for source, value in raw_candidates:
        if value:
            candidates_by_value.setdefault(value, []).append(source)
    return [
        {"value": value, "sources": sources}
        for value, sources in candidates_by_value.items()
    ]


def _credential_exchange(conn: Any) -> Prompt:
    text = _read(conn, window=0.3)
    lower = text.lower()
    if "username:" in lower or "login:" in lower:
        if not settings.cisco_test_username:
            return Prompt("login-required", "username prompt", False)
        _send(conn, settings.cisco_test_username, secret=True)
        text = _read(conn, window=0.8)
        lower = text.lower()
    if "password:" in lower:
        password = settings.cisco_test_password
        if not password:
            return Prompt("login-required", "password prompt", False)
        _send(conn, password, secret=True)
        text = _read(conn, window=1.2)
        parsed = _classify_prompt(text)
        if parsed.state == "unknown":
            _send(conn, "")
            parsed = _classify_prompt(_read(conn, window=1.0))
        if parsed.state != "login-required":
            return parsed
        return parsed
    return _classify_prompt(text)


def _recover_to_exec(conn: Any) -> Prompt:
    conn.write(b"\x03")
    time.sleep(0.2)
    _send(conn, "")
    prompt = _classify_prompt(_read(conn, window=1.0))
    if prompt.state in {"exec", "privileged-exec"}:
        return prompt
    conn.write(b"\x1a")
    time.sleep(0.2)
    _send(conn, "")
    return _classify_prompt(_read(conn, window=1.0))


def _capture_identity(conn: Any) -> dict[str, Any]:
    outputs = []
    for command in SHOW_COMMANDS:
        _send(conn, command)
        output = _read(conn, window=2.0)
        outputs.append(
            {
                "command": command,
                "captured": bool(output),
                "bytes": len(output.encode("utf-8", errors="replace")),
                "summary": _summarize_show(command, output),
                "raw_output_redacted": True,
            }
        )
    return {"status": "captured", "commands": outputs}


def _read_privilege_level(conn: Any) -> int | None:
    _send(conn, "show privilege")
    output = _read(conn, window=1.5)
    match = re.search(r"(?im)\bCurrent privilege level is\s+(\d+)\b", output)
    if not match:
        match = re.search(r"(?im)\bprivilege level is\s+(\d+)\b", output)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _bootstrap_plan() -> dict[str, Any]:
    hostname = settings.cisco_hostname or "lab-cisco-switch"
    target_ip = settings.cisco_target_ip
    prefix = settings.cisco_management_prefix or "/24"
    netmask = _netmask(prefix)
    vlan = settings.cisco_management_vlan
    interface = settings.cisco_management_interface or (f"Vlan{vlan}" if vlan else "Vlan1")
    username = settings.cisco_test_username
    commands = [
        "terminal length 0",
        "configure terminal",
        f"hostname {hostname}",
    ]
    if settings.cisco_domain_name:
        commands.append(f"ip domain-name {settings.cisco_domain_name}")
    for dns_server in settings.cisco_dns_servers:
        commands.append(f"ip name-server {dns_server}")
    commands.extend(["lldp run", "no ip http server", "no ip http secure-server"])
    if vlan and interface.lower() != f"vlan{vlan}".lower():
        commands.extend([f"vlan {vlan}", f" name LAB-MGMT"])
    commands.append(f"interface {interface}")
    if target_ip and netmask:
        commands.append(f" ip address {target_ip} {netmask}")
    commands.extend([" no shutdown", " exit"])
    if settings.cisco_management_gateway:
        commands.append(f"ip default-gateway {settings.cisco_management_gateway}")
    if username and settings.cisco_test_password:
        commands.append(f"username {username} privilege 15 secret <redacted>")
    commands.extend(
        [
            "ip ssh version 2",
            "ip scp server enable",
            "line console 0",
            " login local",
            " exit",
            "line vty 0 15",
            " login local",
            " transport input ssh",
            " exit",
            "end",
            "write memory",
        ]
    )
    blockers = []
    if not target_ip:
        blockers.append("CISCO_TARGET_IP or ANSIBLE_CISCO_HOST is required for Cisco management IP.")
    if not netmask:
        blockers.append("CISCO_MANAGEMENT_PREFIX must be a valid prefix or netmask.")
    if not username or not settings.cisco_test_password:
        blockers.append("Cisco local admin username/password are required for SSH/SCP bootstrap.")
    return {
        "status": "ready" if not blockers else "blocked",
        "hostname": hostname,
        "management_interface": interface,
        "management_vlan": vlan,
        "management_ip_configured": bool(target_ip),
        "ansible_role": (
            "console first-contact/bootstrap first; Ansible starts after Cisco management SSH "
            "is configured for show commands, backup, validation, drift checks, and future repeatable config"
        ),
        "ansible_control_host": settings.ansible_control_host,
        "gateway_configured": bool(settings.cisco_management_gateway),
        "domain_configured": bool(settings.cisco_domain_name),
        "dns_server_count": len(settings.cisco_dns_servers),
        "ssh_version": "2",
        "scp_enabled": True,
        "http_https_disabled": True,
        "save_startup_config": True,
        "reload_required": False,
        "redacted_commands": commands,
        "blockers": blockers,
    }


def _apply_bootstrap(conn: Any, plan: dict[str, Any]) -> dict[str, Any]:
    policy_blockers = current_lab_action_policy(settings.provider_mode).action_blockers(
        "cisco-console.bootstrap",
        ActionCategory.NETWORK_CONFIG,
    )
    blockers = [*policy_blockers, *(plan.get("blockers") or [])]
    if blockers:
        return {"status": "blocked", "serial_writes_attempted": False, "blockers": blockers}
    sent = []
    for command in plan["redacted_commands"]:
        actual = command
        if command.startswith("username ") and settings.cisco_test_username and settings.cisco_test_password:
            actual = f"username {settings.cisco_test_username} privilege 15 secret {settings.cisco_test_password}"
        _send(conn, actual, secret=" secret " in actual)
        sent.append(command)
        _read(conn, window=0.5)
    return {
        "status": "completed",
        "serial_writes_attempted": True,
        "commands_sent_redacted": sent,
        "save_status": "write memory command sent",
        "reload": {"attempted": False, "reason": "Bootstrap plan does not require reload."},
    }


def _ethernet_readiness() -> dict[str, Any]:
    host = settings.cisco_target_ip
    if not host:
        return {"status": "blocked", "blockers": ["Cisco target IP is missing."]}
    ping = subprocess.run(["ping", "-c", "2", "-W", "2", host], capture_output=True, text=True, check=False)
    ssh = _tcp_connect(host, 22, timeout=4.0)
    return {
        "status": "ready" if ping.returncode == 0 and ssh["reachable"] else "blocked",
        "ping": {"status": "ok" if ping.returncode == 0 else "failed", "returncode": ping.returncode},
        "ssh": ssh,
        "scp": {
            "status": "ready" if ssh["reachable"] else "blocked",
            "method": "TCP/22 readiness plus bootstrap command `ip scp server enable`.",
        },
    }


def _serial_ownership(discovery: dict[str, Any]) -> dict[str, Any]:
    paths = []
    effective = discovery.get("effective_path")
    if isinstance(effective, str):
        paths.append(effective)
        resolved = os.path.realpath(effective)
        if resolved != effective:
            paths.append(resolved)
    if not paths:
        for candidate in discovery.get("candidates") or []:
            path = candidate.get("path") if isinstance(candidate, dict) else None
            if isinstance(path, str):
                paths.append(path)
                resolved = os.path.realpath(path)
                if resolved != path:
                    paths.append(resolved)
    paths = list(dict.fromkeys(paths))
    owners = []
    for path in paths:
        result = subprocess.run(["fuser", "-v", path], capture_output=True, text=True, check=False)
        text = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and text:
            owners.append({"path": path, "summary": _redact_process_text(text)})
    return {"checked_paths": paths, "owned": bool(owners), "owners": owners}


def _send(conn: Any, command: str, *, secret: bool = False) -> None:
    del secret
    conn.write(command.encode("utf-8", errors="replace") + b"\r\n")


def _read(conn: Any, *, window: float) -> str:
    deadline = time.monotonic() + window
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        waiting = getattr(conn, "in_waiting", 0)
        data = conn.read(waiting or 256)
        if data:
            chunks.append(data)
        else:
            time.sleep(0.1)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _classify_prompt(text: str) -> Prompt:
    lower = text.lower()
    if "initial configuration dialog" in lower or "system configuration dialog" in lower or "[yes/no]" in lower:
        return Prompt("setup-wizard", "setup wizard prompt", False)
    match = PROMPT_RE.search(text)
    if match:
        prompt = match.group(1)
        if "(config" in prompt.lower():
            return Prompt("config-mode", "configuration prompt", False)
        if prompt.endswith("#"):
            return Prompt("privileged-exec", "DEVICE#", True)
        return Prompt("exec", "DEVICE>", False)
    if "username:" in lower or "login:" in lower or "password:" in lower:
        return Prompt("login-required", "login/password prompt", False)
    return Prompt("unknown", _redact_line(_last_line(text)), False)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _redact_line(line: str) -> str:
    if not line:
        return ""
    lower = line.lower()
    if "username" in lower:
        return "username prompt"
    if "password" in lower:
        return "password prompt"
    if line.endswith("#"):
        return "DEVICE#"
    if line.endswith(">"):
        return "DEVICE>"
    if "[yes/no]" in lower:
        return "[yes/no] prompt"
    return "unrecognized console text"


def _summarize_show(command: str, output: str) -> dict[str, Any]:
    if command == "show version":
        model = re.search(r"(?im)^cisco\s+(\S+).+processor", output)
        version = re.search(r"(?im)^Cisco IOS(?: XE)? Software.+Version\s+([^,\s]+)", output)
        uptime = re.search(r"(?im)^(.+ uptime is .+)$", output)
        return {
            "model_hint": model.group(1) if model else None,
            "version_hint": version.group(1) if version else None,
            "uptime_present": bool(uptime),
        }
    if command == "show ip interface brief":
        return {"vlan_lines": len(re.findall(r"(?im)^vlan\d+\s+", output))}
    if command == "show vlan brief":
        return {"vlan_count_hint": len(re.findall(r"(?im)^\d+\s+\S+", output))}
    return {"captured": bool(output)}


def _netmask(prefix: str) -> str | None:
    value = prefix.strip()
    if value.startswith("/"):
        try:
            return str(ipaddress.IPv4Network(f"0.0.0.0{value}").netmask)
        except ValueError:
            return None
    try:
        ipaddress.IPv4Address(value)
        return value
    except ValueError:
        return None


def _tcp_connect(host: str, port: int, *, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"reachable": True, "port": port, "elapsed_seconds": round(time.monotonic() - started, 3)}
    except OSError as exc:
        return {
            "reachable": False,
            "port": port,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": str(exc),
        }


def _redact_process_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        lines.append(re.sub(r"\s+", " ", line).strip())
    return "\n".join(lines)


def _finish(payload: dict[str, Any]) -> int:
    payload["blockers"] = list(dict.fromkeys(payload["blockers"]))
    payload["warnings"] = list(dict.fromkeys(payload["warnings"]))
    payload["status"] = "blocked" if payload["blockers"] else "completed"
    sanitized = _sanitize(payload)
    _write_json(DETAILS, sanitized)
    REPORT.write_text(_markdown(sanitized), encoding="utf-8")
    FIX_REPORT.write_text(_markdown(sanitized, title="Cisco Privileged Exec Fix Report"), encoding="utf-8")
    PRIVILEGE_HARDENING_REPORT.write_text(
        _markdown(sanitized, title="Cisco Privilege Hardening Report"),
        encoding="utf-8",
    )
    print(json.dumps(_summary(sanitized), indent=2))
    return 0 if payload["status"] in {"completed", "blocked"} else 1


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload.get("stages", {}).get("console_prompt_detection", {})
    adapter = payload.get("stages", {}).get("adapter_discovery", {})
    return {
        "checked_at": payload.get("checked_at"),
        "status": payload.get("status"),
        "console_adapter": adapter.get("effective_path"),
        "prompt_state": prompt.get("prompt_state"),
        "prompt_detected": prompt.get("prompt_detected"),
        "selected_baud": prompt.get("selected_baud"),
        "blockers": payload.get("blockers") or [],
        "report": str(FIX_REPORT.relative_to(REPO_ROOT)),
        "details": str(DETAILS.relative_to(REPO_ROOT)),
    }


def _markdown(payload: dict[str, Any], *, title: str = "Cisco 4h Lab Run Report") -> str:
    stages = payload.get("stages", {})
    adapter = stages.get("adapter_discovery", {})
    prompt = stages.get("console_prompt_detection", {})
    privilege = stages.get("privilege_escalation", {})
    identity = stages.get("switch_identification", {})
    plan = stages.get("bootstrap_plan", {})
    apply = stages.get("apply", {})
    ethernet = stages.get("ethernet_management_validation", {})
    lines = [
        f"# {title}",
        "",
        "## Summary",
        "",
        f"- Checked at: {payload.get('checked_at')}",
        f"- Provider mode: `{payload.get('provider_mode')}`",
        f"- Overall status: `{payload.get('status')}`",
        f"- Console adapter detected: `{adapter.get('effective_path')}`",
        f"- Prompt detected: `{prompt.get('prompt_detected')}`",
        f"- Prompt state: `{prompt.get('prompt_state')}`",
        f"- Selected baud: `{prompt.get('selected_baud')}`",
        f"- Switch identity status: `{identity.get('status')}`",
        f"- Bootstrap plan status: `{plan.get('status')}`",
        f"- Apply status: `{apply.get('status')}`",
        f"- Ethernet management status: `{ethernet.get('status')}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in payload.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in payload.get("warnings") or []] or ["- none"])
    lines.extend(
        [
            "",
            "## Code Inspection",
            "",
            "- Enable from exec prompt: `yes`; `_ensure_privileged` calls `_enter_enable` when prompt state is `exec`.",
            "- Enable commands attempted: `enable`, then `enable 15`.",
            "- Password prompt after enable handled: `yes`; `_answer_enable_challenge` responds to `Password:` without logging the value.",
            "- Enable password aliases tried: `CISCO_ENABLE_PASSWORD`, `ANSIBLE_CISCO_ENABLE_PASSWORD`, `settings.cisco_enable_password`, then login-password fallback.",
            "- Configuration apply: `not run` unless `--apply` is passed.",
            "",
            "## Stage Evidence",
            "",
            f"- Adapter discovery: `{adapter.get('status')}`; source `{adapter.get('selection_source')}`.",
            f"- Port ownership: `{adapter.get('ownership', {}).get('owned')}`.",
            f"- Console prompt detection: tried `{prompt.get('bauds_tried')}` and wake sequences `{prompt.get('wake_sequences_tried')}`.",
            f"- Privilege initial prompt state: `{privilege.get('initial_prompt_state')}`.",
            f"- Enable command sent: `{privilege.get('enable_command_sent')}`.",
            f"- Enable password prompt seen: `{privilege.get('password_prompt_seen')}`.",
            f"- Privilege final prompt state: `{privilege.get('final_prompt_state')}`.",
            f"- Readable privilege level: `{privilege.get('privilege_level')}`.",
            f"- Enable password rejected: `{_enable_password_rejected(privilege)}`.",
            f"- Password recovery/factory reset required: `{_password_recovery_required(privilege)}`.",
            f"- Operator next action: {_privilege_next_action(privilege)}",
            f"- Bootstrap commands redacted artifact: `{COMMANDS.relative_to(REPO_ROOT)}`.",
            f"- Console samples redacted artifact: `{SAMPLES.relative_to(REPO_ROOT)}`.",
            f"- Details artifact: `{DETAILS.relative_to(REPO_ROOT)}`.",
            "",
            "## Safety",
            "",
            "- Raw console logs and secrets were not saved.",
            "- Reboot/reload was not attempted unless explicitly reported in apply status.",
            "- Mock results were not used as substitutes for real lab evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _enable_password_rejected(privilege: dict[str, Any]) -> bool:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return False
    debug = privilege.get("debug") if isinstance(privilege.get("debug"), dict) else {}
    return bool(debug.get("enable_command_sent") and debug.get("password_prompt_seen"))


def _password_recovery_required(privilege: dict[str, Any]) -> str:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return "false"
    if _enable_password_rejected(privilege):
        return "operator-confirm-password-recovery-or-factory-reset"
    if privilege.get("initial_prompt_state") == "exec" and not privilege.get("enable_command_sent"):
        return "unknown-enable-not-sent"
    return "unknown"


def _privilege_next_action(privilege: dict[str, Any]) -> str:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return "Privilege is confirmed; continue Cisco management network validation."
    if _enable_password_rejected(privilege):
        return (
            "Confirm the enable credential out of band. If no valid enable credential exists, "
            "perform the documented password recovery or factory reset procedure, then rerun Cisco bootstrap."
        )
    if privilege.get("initial_prompt_state") == "exec":
        return "Rerun the Cisco privilege workflow and verify whether enable sends a Password: challenge."
    return "Restore a user exec or privileged exec prompt before retrying Cisco bootstrap."


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(
        payload,
        [
            settings.cisco_console_port,
            settings.cisco_target_ip,
            settings.cisco_test_username,
            settings.cisco_test_password,
            settings.cisco_enable_password,
            os.getenv("CISCO_ENABLE_PASSWORD"),
            os.getenv("ANSIBLE_CISCO_ENABLE_PASSWORD"),
            settings.cisco_management_gateway,
            settings.cisco_domain_name,
            *settings.cisco_dns_servers,
        ],
    )


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
