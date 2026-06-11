from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import LAB_CISCO_MANAGEMENT_IP, settings
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.cisco_console import (
    CiscoConsoleConfig,
    discover_cisco_console,
)
from app.providers.redaction import redact_sensitive
from app.services.hpe_raid import REPO_ROOT

REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-4h-lab-run-report.md"
FIX_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-privileged-exec-fix-report.md"
PRIVILEGE_HARDENING_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-privilege-hardening-report.md"
PRIVILEGE_DIAGNOSIS_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-privilege-diagnosis-report.md"
PASSWORD_RECOVERY_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-password-recovery-guidance-report.md"
BOOTSTRAP_APPLY_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-bootstrap-apply-report.md"
VLAN10_BOOTSTRAP_FIX_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-vlan10-bootstrap-fix-report.md"
LOGIN_BOOTSTRAP_FIX_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-login-bootstrap-fix-report.md"
COMMANDER_MODE_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-console-commander-mode-report.md"
DETAILS = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-4h-lab-run-details-redacted.json"
SAMPLES = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-console-samples-redacted.json"
COMMANDS = REPO_ROOT / "artifacts" / "codex-runs" / "cisco-bootstrap-commands-redacted.json"

BAUD_RATES = (9600, 19200, 38400, 57600, 115200)
WAKE_SEQUENCES = (
    {"name": "crlf", "bytes": b"\r\n"},
    {"name": "newline", "bytes": b"\n"},
    {"name": "enter", "bytes": b"\r"},
    {"name": "ctrl-c", "bytes": b"\x03"},
    {"name": "ctrl-z", "bytes": b"\x1a"},
    {"name": "break", "bytes": b""},
)
SHOW_COMMANDS = (
    "terminal length 0",
    "show privilege",
    "show version | include Cisco IOS|uptime|System image|processor|bytes of memory",
    "show inventory",
    "show interfaces status",
    "show ip interface brief",
    "show vlan brief",
    "show running-config | include ^hostname|^ip domain-name|^ip ssh|^ip scp|^ip http|^username|^interface Vlan|^ip default-gateway|^lldp run",
)
PROMPT_RE = re.compile(r"(?m)(?:^|\r|\n)([A-Za-z0-9_.:/()-]+(?:\(config[^\)]*\))?[#>])\s*$")
RECLAIMABLE_CONSOLE_COMMANDS = ("screen", "picocom", "minicom", "python")
CISCO_DEFAULT_DOMAIN_NAME = "lab.local"
CISCO_ALWAYS_ACCESS_PORTS = ("Gi1/0/1",)
CISCO_SSH_HOSTKEY_LABEL = "LAB-SSH-HOSTKEY"


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
            "privilege_diagnosis_report": str(PRIVILEGE_DIAGNOSIS_REPORT.relative_to(REPO_ROOT)),
            "password_recovery_guidance_report": str(PASSWORD_RECOVERY_REPORT.relative_to(REPO_ROOT)),
            "bootstrap_apply_report": str(BOOTSTRAP_APPLY_REPORT.relative_to(REPO_ROOT)),
            "vlan10_bootstrap_fix_report": str(VLAN10_BOOTSTRAP_FIX_REPORT.relative_to(REPO_ROOT)),
            "login_bootstrap_fix_report": str(LOGIN_BOOTSTRAP_FIX_REPORT.relative_to(REPO_ROOT)),
            "commander_mode_report": str(COMMANDER_MODE_REPORT.relative_to(REPO_ROOT)),
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
    claim = _claim_cisco_console(
        discovery,
        provider_mode=settings.provider_mode,
        reclaim_enabled=_env_flag("CISCO_CONSOLE_RECLAIM"),
    )
    if isinstance(claim.get("post_discovery"), dict):
        discovery = claim["post_discovery"]
    ownership = claim["post_ownership"]
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
    payload["stages"]["console_preflight_claim"] = claim
    payload["warnings"].extend(discovery.get("warnings") or [])
    payload["blockers"].extend(discovery.get("blockers") or [])
    payload["blockers"].extend(claim.get("blockers") or [])
    if claim.get("reclaimed"):
        payload["warnings"].append("Cisco console preflight reclaimed the selected serial port before opening it.")
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
    apply_result: dict[str, Any] = {
        "status": "not-attempted",
        "reason": "Privileged exec was not confirmed yet.",
    }
    ethernet: dict[str, Any] = {"status": "not-attempted", "reason": "Bootstrap apply did not run."}
    post_apply_validation_requested = False

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

        plan = _bootstrap_plan(identity)
        payload["stages"]["switch_identification"] = identity or {"status": "blocked"}
        payload["stages"]["bootstrap_plan"] = plan
        _write_json(COMMANDS, _sanitize({"commands": plan["redacted_commands"]}))

        if privilege_prompt.state != "privileged-exec":
            payload["blockers"].append("Privileged exec prompt is required for bootstrap apply.")

        should_apply = _bootstrap_apply_requested(args)
        if should_apply and not payload["blockers"]:
            apply_result = _apply_bootstrap(conn, plan)
            if apply_result["status"] == "completed":
                post_apply_validation_requested = True
            else:
                payload["blockers"].extend(apply_result.get("blockers") or [])
        elif not args.apply:
            switch_validation = _post_bootstrap_switch_validation(conn, plan)
            payload["stages"]["vlan10_switch_validation"] = switch_validation
            ethernet = _ethernet_readiness()
            apply_result = {
                "status": "not-attempted",
                "reason": "Bootstrap plan was built but not applied because --apply was not set.",
            }
            ethernet["failure_classification"] = _classify_vlan10_failure(apply_result, switch_validation, ethernet)
            payload["warnings"].append("Bootstrap plan was built but not applied because --apply was not set.")

    if post_apply_validation_requested:
        switch_validation = _post_apply_reconnect_switch_validation(serial, port, baud, plan)
        payload["stages"]["vlan10_switch_validation"] = switch_validation
        ethernet = _ethernet_readiness()
        ethernet["failure_classification"] = _classify_vlan10_failure(apply_result, switch_validation, ethernet)
        if ethernet.get("status") != "ready":
            payload["blockers"].extend(ethernet.get("blockers") or ["Cisco management validation failed."])

    payload["stages"]["apply"] = apply_result
    payload["stages"].setdefault("vlan10_switch_validation", _empty_switch_validation(apply_result))
    if "failure_classification" not in ethernet:
        ethernet["failure_classification"] = _classify_vlan10_failure(
            apply_result,
            payload["stages"]["vlan10_switch_validation"],
            ethernet,
        )
    payload["stages"]["ethernet_management_validation"] = ethernet
    return _finish(payload)


def _detect_console(serial_module: Any, port: str, *, first_baud: int | None = None) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    baud_rates = _baud_order(first_baud)
    for baud in baud_rates:
        try:
            with serial_module.Serial(port=port, baudrate=baud, timeout=0.8, write_timeout=0.8) as conn:
                conn.reset_input_buffer()
                _toggle_dtr_rts(conn)
                for sequence in WAKE_SEQUENCES:
                    if sequence["name"] == "break":
                        _send_break(conn)
                    else:
                        conn.write(sequence["bytes"])
                    text = _read(conn, window=3.0)
                    prompt = _classify_prompt(text)
                    login_result = _complete_login_flow(conn, prompt, text)
                    prompt = login_result.prompt
                    debug = login_result.debug
                    sample = {
                        "baud": baud,
                        "sequence": sequence["name"],
                        "captured": bool(text),
                        "classification": _console_classification(prompt.state, text),
                        "bytes": len(text.encode("utf-8", errors="replace")),
                        "first_bytes_printable_preview": _printable_preview(text),
                        "prompt_regex_matched": debug["prompt_regex_matched"],
                        "login_state_transitions": debug["login_state_transitions"],
                        "user_access_verification_seen": debug["user_access_verification_seen"],
                        "username_prompt_seen": debug["username_prompt_seen"],
                        "password_prompt_seen": debug["password_prompt_seen"],
                        "final_prompt": prompt.text,
                        "line_count": len([line for line in text.splitlines() if line.strip()]),
                        "last_line": _redact_line(_last_line(text)),
                        "prompt": prompt.__dict__,
                    }
                    samples.append(sample)
                    if prompt.state in {
                        "exec",
                        "privileged-exec",
                        "setup-wizard",
                        "rommon-bootloader",
                        "password-recovery-ready",
                    }:
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
                                "first_bytes_printable_preview": sample["first_bytes_printable_preview"],
                                "prompt_regex_matched": sample["prompt_regex_matched"],
                                "login_state_transitions": sample["login_state_transitions"],
                                "user_access_verification_seen": sample["user_access_verification_seen"],
                                "username_prompt_seen": sample["username_prompt_seen"],
                                "password_prompt_seen": sample["password_prompt_seen"],
                                "final_prompt": sample["final_prompt"],
                                "bauds_tried": list(baud_rates),
                                "wake_sequences_tried": [item["name"] for item in WAKE_SEQUENCES],
                            },
                            "blockers": [],
                        }
                    if prompt.state in {"login-required", "password-required"}:
                        return {
                            "selected": None,
                            "samples": samples,
                            "summary": {
                                "status": "blocked",
                                "selected_port": port,
                                "selected_baud": baud,
                                "selected_sequence": sequence["name"],
                                "prompt_state": prompt.state,
                                "prompt_detected": True,
                                "first_bytes_printable_preview": sample["first_bytes_printable_preview"],
                                "prompt_regex_matched": sample["prompt_regex_matched"],
                                "login_state_transitions": sample["login_state_transitions"],
                                "user_access_verification_seen": sample["user_access_verification_seen"],
                                "username_prompt_seen": sample["username_prompt_seen"],
                                "password_prompt_seen": sample["password_prompt_seen"],
                                "final_prompt": sample["final_prompt"],
                                "bauds_tried": list(baud_rates),
                                "wake_sequences_tried": [item["name"] for item in WAKE_SEQUENCES],
                            },
                            "blockers": [
                                "Console login prompt was detected, but configured credentials did not reach exec."
                            ],
                        }
        except Exception as exc:  # pragma: no cover - hardware dependent
            state = _serial_open_prompt_state(exc)
            samples.append(
                {
                    "baud": baud,
                    "sequence": "open",
                    "captured": False,
                    "classification": _console_classification(state, ""),
                    "error": _serial_error_summary(exc),
                    "prompt": Prompt(state, "", False).__dict__,
                }
            )
    return {
        "selected": None,
        "samples": samples,
        "summary": {
            "status": "blocked",
            "selected_port": None,
            "selected_baud": None,
            "prompt_state": _final_console_prompt_state(samples),
            "classification": "no_bytes_read" if not any(sample.get("captured") for sample in samples) else "unreadable_gibberish",
            "prompt_detected": False,
            "first_bytes_printable_preview": _first_sample_preview(samples),
            "prompt_regex_matched": None,
            "login_state_transitions": [],
            "user_access_verification_seen": False,
            "username_prompt_seen": False,
            "password_prompt_seen": False,
            "final_prompt": None,
            "bauds_tried": list(baud_rates),
            "wake_sequences_tried": [item["name"] for item in WAKE_SEQUENCES],
            "recovery_attempts": ["newline", "carriage return", "Ctrl+C", "Ctrl+Z", "break", "DTR/RTS toggle when supported"],
        },
        "blockers": [
            "Console adapter opened across common baud rates, but no supported Cisco prompt was detected."
        ],
    }


def _bootstrap_apply_requested(args: argparse.Namespace) -> bool:
    return bool(args.apply)


def _baud_order(first_baud: int | None) -> tuple[int, ...]:
    values = [first_baud, *BAUD_RATES] if first_baud else list(BAUD_RATES)
    return tuple(dict.fromkeys(int(value) for value in values if value))


def _ensure_privileged(conn: Any, prompt: Prompt) -> PrivilegeResult:
    current = prompt
    debug: dict[str, Any] = {
        "initial_prompt_state": prompt.state,
        "setup_wizard_answered_no": False,
        "login_exchange_attempted": False,
        "login_state_transitions": [],
        "username_prompt_seen": False,
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
        if current.state in {"login-required", "password-required"}:
            debug["login_exchange_attempted"] = True
            credential_result = _credential_exchange(conn)
            current = credential_result.prompt
            debug["login_state_transitions"] = credential_result.debug["login_state_transitions"]
            debug["username_prompt_seen"] = credential_result.debug["username_prompt_seen"]
            debug["password_prompt_seen"] = credential_result.debug["password_prompt_seen"] or debug["password_prompt_seen"]
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
        if parsed.state in {"login-required", "password-required"}:
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
            username = _login_username()
            if not username:
                return EnableChallengeResult(Prompt("login-required", "username prompt", False), password_prompt_seen)
            _send(conn, username, secret=True)
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


@dataclass(frozen=True)
class CredentialExchangeResult:
    prompt: Prompt
    debug: dict[str, Any]


def _credential_exchange(conn: Any, initial_text: str = "") -> CredentialExchangeResult:
    text = initial_text or _read(conn, window=0.8)
    parsed = _classify_prompt(text)
    debug: dict[str, Any] = {
        "login_state_transitions": [],
        "user_access_verification_seen": "user access verification" in text.lower(),
        "username_prompt_seen": "username:" in text.lower() or "login:" in text.lower(),
        "password_prompt_seen": "password:" in text.lower(),
        "prompt_regex_matched": _prompt_match_label(text, parsed),
    }
    for _ in range(6):
        lower = text.lower()
        if parsed.state in {"exec", "privileged-exec", "setup-wizard", "rommon-bootloader", "password-recovery-ready"}:
            debug["prompt_regex_matched"] = _prompt_match_label(text, parsed)
            return CredentialExchangeResult(parsed, debug)
        if "username:" in lower or "login:" in lower:
            debug["username_prompt_seen"] = True
            debug["login_state_transitions"].append("username_prompt_seen")
            username = _login_username()
            if not username:
                return CredentialExchangeResult(Prompt("login-required", "username prompt", False), debug)
            _send(conn, username, secret=True)
            debug["login_state_transitions"].append("username_sent")
            text = _read(conn, window=2.0)
            parsed = _classify_prompt(text)
            continue
        if "password:" in lower:
            debug["password_prompt_seen"] = True
            debug["login_state_transitions"].append("password_prompt_seen")
            password = _login_password()
            if not password:
                return CredentialExchangeResult(Prompt("password-required", "password prompt", False), debug)
            _send(conn, password, secret=True)
            debug["login_state_transitions"].append("password_sent")
            text = _read(conn, window=2.5)
            parsed = _classify_prompt(text)
            if parsed.state == "unknown":
                _send(conn, "")
                debug["login_state_transitions"].append("prompt_refresh_sent")
                text = _read(conn, window=1.5)
                parsed = _classify_prompt(text)
            continue
        _send(conn, "")
        debug["login_state_transitions"].append("prompt_refresh_sent")
        text = _read(conn, window=1.5)
        parsed = _classify_prompt(text)
    debug["prompt_regex_matched"] = _prompt_match_label(text, parsed)
    return CredentialExchangeResult(parsed, debug)


@dataclass(frozen=True)
class LoginFlowResult:
    prompt: Prompt
    debug: dict[str, Any]


def _complete_login_flow(conn: Any, prompt: Prompt, text: str) -> LoginFlowResult:
    if prompt.state not in {"login-required", "password-required", "unknown"}:
        return LoginFlowResult(
            prompt,
            {
                "login_state_transitions": [],
                "user_access_verification_seen": "user access verification" in text.lower(),
                "username_prompt_seen": "username:" in text.lower() or "login:" in text.lower(),
                "password_prompt_seen": "password:" in text.lower(),
                "prompt_regex_matched": _prompt_match_label(text, prompt),
            },
        )
    result = _credential_exchange(conn, text)
    return LoginFlowResult(result.prompt, result.debug)


def _login_username() -> str | None:
    return os.getenv("CISCO_TEST_USERNAME") or os.getenv("ANSIBLE_CISCO_USERNAME") or settings.cisco_test_username


def _login_password() -> str | None:
    return os.getenv("CISCO_TEST_PASSWORD") or os.getenv("ANSIBLE_CISCO_PASSWORD") or settings.cisco_test_password


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
    detected_access_ports: list[str] = []
    for command in SHOW_COMMANDS:
        _send(conn, command)
        output = _read(conn, window=2.0)
        if command == "show interfaces status":
            detected_access_ports = _detect_access_ports_from_interfaces_status(output)
        outputs.append(
            {
                "command": command,
                "captured": bool(output),
                "bytes": len(output.encode("utf-8", errors="replace")),
                "summary": _summarize_show(command, output),
                "raw_output_redacted": True,
            }
        )
    return {
        "status": "captured",
        "commands": outputs,
        "detected_access_ports": detected_access_ports,
        "detected_access_port_count": len(detected_access_ports),
    }


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


def _bootstrap_plan(identity: dict[str, Any] | None = None) -> dict[str, Any]:
    hostname = settings.cisco_hostname or "lab-cisco-switch"
    target_ip = settings.cisco_target_ip or LAB_CISCO_MANAGEMENT_IP
    prefix = settings.cisco_management_prefix or "/24"
    netmask = _netmask(prefix)
    vlan = str(settings.cisco_management_vlan or "10")
    interface = settings.cisco_management_interface or f"Vlan{vlan}"
    domain_name = settings.cisco_domain_name or CISCO_DEFAULT_DOMAIN_NAME
    username = settings.cisco_test_username
    access_ports = _selected_or_detected_access_ports(identity or {})
    commands = [
        "terminal length 0",
        "configure terminal",
        f"hostname {hostname}",
        f"ip domain-name {domain_name}",
    ]
    for dns_server in settings.cisco_dns_servers:
        commands.append(f"ip name-server {dns_server}")
    commands.extend(["lldp run", "no ip http server", "no ip http secure-server"])
    commands.extend([f"vlan {vlan}", " name LAB-MGMT"])
    commands.append(f"interface {interface}")
    if target_ip and netmask:
        commands.append(f" ip address {target_ip} {netmask}")
    commands.extend([" no shutdown", " exit"])
    if access_ports:
        for port in access_ports:
            commands.extend(
                [
                    f"interface {port}",
                    " switchport mode access",
                    f" switchport access vlan {vlan}",
                    " no shutdown",
                    " exit",
                ]
            )
    if settings.cisco_management_gateway:
        commands.append(f"ip default-gateway {settings.cisco_management_gateway}")
    if username and settings.cisco_test_password:
        commands.append(f"username {username} privilege 15 secret <redacted>")
    commands.extend(
        [
            f"crypto key generate rsa general-keys label {CISCO_SSH_HOSTKEY_LABEL} modulus 2048",
            f"ip ssh rsa keypair-name {CISCO_SSH_HOSTKEY_LABEL}",
            "ip ssh version 2",
            "ip scp server enable",
            "line console 0",
            " login local",
            " exit",
            "line vty 0 31",
            " login local",
            " transport input ssh",
            " exit",
            "end",
            "write memory",
        ]
    )
    blockers = []
    if target_ip != LAB_CISCO_MANAGEMENT_IP:
        blockers.append(f"Cisco VLAN 10 bootstrap target must be {LAB_CISCO_MANAGEMENT_IP}.")
    if prefix not in {"/24", "255.255.255.0"}:
        blockers.append("Cisco VLAN 10 bootstrap requires a /24 management prefix.")
    if interface.lower() != "vlan10":
        blockers.append("Cisco VLAN 10 bootstrap requires interface Vlan10.")
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
        "management_ip": target_ip,
        "management_prefix": prefix,
        "management_netmask": netmask,
        "always_access_ports": list(CISCO_ALWAYS_ACCESS_PORTS),
        "selected_or_detected_access_ports": access_ports,
        "access_port_source": _access_port_source(identity or {}),
        "ansible_role": (
            "console first-contact/bootstrap first; Ansible starts after Cisco management SSH "
            "is configured for show commands, backup, validation, drift checks, and future repeatable config"
        ),
        "ansible_control_host": settings.ansible_control_host,
        "gateway_configured": bool(settings.cisco_management_gateway),
        "domain_configured": bool(domain_name),
        "domain_source": "env" if settings.cisco_domain_name else "default",
        "dns_server_count": len(settings.cisco_dns_servers),
        "ssh_key_generation": f"rsa general-keys label {CISCO_SSH_HOSTKEY_LABEL} modulus 2048",
        "ssh_keypair_name": CISCO_SSH_HOSTKEY_LABEL,
        "ssh_version": "2",
        "scp_enabled": True,
        "http_https_disabled": True,
        "save_startup_config": True,
        "reload_required": False,
        "redacted_commands": commands,
        "blockers": blockers,
    }


def _selected_or_detected_access_ports(identity: dict[str, Any]) -> list[str]:
    configured = _configured_access_ports()
    if configured:
        return _unique_ports([*CISCO_ALWAYS_ACCESS_PORTS, *configured])
    detected = identity.get("detected_access_ports")
    if isinstance(detected, list):
        return _unique_ports([*CISCO_ALWAYS_ACCESS_PORTS, *[str(item) for item in detected if str(item).strip()]])
    return list(CISCO_ALWAYS_ACCESS_PORTS)


def _unique_ports(ports: list[str]) -> list[str]:
    return list(dict.fromkeys(port.strip() for port in ports if port.strip()))


def _configured_access_ports() -> list[str]:
    raw = (
        os.getenv("CISCO_LAB_ACCESS_PORTS")
        or os.getenv("CISCO_ACCESS_PORTS")
        or os.getenv("CISCO_LAB_PORTS")
        or ""
    )
    return [item.strip() for item in raw.split(",") if item.strip()]


def _access_port_source(identity: dict[str, Any]) -> str:
    if _configured_access_ports():
        return "always-access-plus-configured-env"
    if identity.get("detected_access_ports"):
        return "always-access-plus-detected-show-interfaces-status"
    return "always-access-default"


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
        if actual.startswith("crypto key generate rsa"):
            _send_crypto_keygen(conn, actual)
        else:
            _send(conn, actual, secret=" secret " in actual)
            _read(conn, window=_bootstrap_command_wait_seconds(command))
        sent.append(command)
    return {
        "status": "completed",
        "serial_writes_attempted": True,
        "commands_sent_redacted": sent,
        "save_status": "write memory command sent",
        "reload": {"attempted": False, "reason": "Bootstrap plan does not require reload."},
    }


def _bootstrap_command_wait_seconds(command: str) -> float:
    if command.startswith("crypto key generate") or command == "write memory":
        return 8.0
    return 2.0


def _send_crypto_keygen(conn: Any, command: str) -> None:
    _send(conn, command)
    output = _read(conn, window=8.0)
    lower = output.lower()
    if "[yes/no]" in lower or "replace" in lower:
        _send(conn, "yes")
        output = _read(conn, window=8.0)
        lower = output.lower()
    if "how many bits" in lower or "modulus" in lower and "2048" not in lower:
        _send(conn, "2048")
        _read(conn, window=8.0)


def _post_apply_reconnect_switch_validation(
    serial_module: Any,
    port: str,
    baud: int,
    plan: dict[str, Any],
) -> dict[str, Any]:
    time.sleep(2.0)
    try:
        with serial_module.Serial(port=port, baudrate=baud, timeout=1.0, write_timeout=1.0) as conn:
            _send(conn, "")
            _read(conn, window=1.0)
            validation = _post_bootstrap_switch_validation(conn, plan)
    except Exception as exc:
        validation = _empty_switch_validation({"status": "completed"})
        validation["status"] = "blocked"
        validation["reason"] = "Post-apply serial reconnect validation failed."
        validation["reconnect_error"] = str(exc)
    validation["connection_strategy"] = "serial-reconnect-after-apply"
    return validation


def _post_bootstrap_switch_validation(conn: Any, plan: dict[str, Any]) -> dict[str, Any]:
    commands = {
        "vlan10_interface": "show ip interface brief | include Vlan10",
        "vlan10_membership": "show vlan brief | include ^10",
        "interfaces_status": "show interfaces status",
    }
    outputs: dict[str, str] = {}
    summaries: dict[str, Any] = {}
    for key, command in commands.items():
        _send(conn, command)
        output = _read(conn, window=2.0)
        outputs[key] = output
        summaries[key] = {
            "command": command,
            "captured": bool(output),
            "bytes": len(output.encode("utf-8", errors="replace")),
            "raw_output_redacted": True,
        }
    vlan10_state = _parse_vlan10_interface_state(outputs["vlan10_interface"])
    vlan10_ports = _parse_vlan10_ports(outputs["vlan10_membership"], outputs["interfaces_status"])
    configured_ports = plan.get("selected_or_detected_access_ports") or []
    return {
        "status": "ready"
        if vlan10_state["configured"] and vlan10_state["line_status"] == "up" and vlan10_state["protocol_status"] == "up"
        else "blocked",
        "commands": summaries,
        "vlan10_state": vlan10_state,
        "ports_assigned_vlan10": vlan10_ports,
        "configured_or_detected_access_ports": configured_ports,
        "all_configured_ports_assigned_vlan10": all(port in vlan10_ports for port in configured_ports)
        if configured_ports
        else None,
    }


def _empty_switch_validation(apply_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "not-attempted",
        "reason": "Post-bootstrap switch validation requires completed bootstrap apply."
        if apply_result.get("status") != "completed"
        else "Post-bootstrap switch validation was not available.",
        "vlan10_state": {
            "configured": None,
            "line_status": None,
            "protocol_status": None,
            "ip": None,
        },
        "ports_assigned_vlan10": [],
    }


def _ethernet_readiness() -> dict[str, Any]:
    host = settings.cisco_target_ip
    if not host:
        return {"status": "blocked", "blockers": ["Cisco target IP is missing."]}
    host_route = _host_route_to(host)
    ping = subprocess.run(["ping", "-c", "2", "-W", "2", host], capture_output=True, text=True, check=False)
    ssh = _tcp_connect(host, 22, timeout=4.0)
    scp = _scp_validation(host)
    status = "ready" if ping.returncode == 0 and ssh["reachable"] and scp["reachable"] else "blocked"
    blockers = []
    if host_route["status"] != "ready":
        blockers.append("Ubuntu host route to Cisco management IP failed.")
    if ping.returncode != 0:
        blockers.append("Ping to Cisco management IP failed.")
    if not ssh["reachable"]:
        blockers.append("SSH TCP/22 to Cisco management IP failed.")
    if not scp["reachable"]:
        blockers.append("SCP readiness over TCP/22 to Cisco management IP failed.")
    return {
        "status": status,
        "host_route": host_route,
        "ping": {"status": "ok" if ping.returncode == 0 else "failed", "returncode": ping.returncode},
        "ssh": ssh,
        "scp": scp,
        "blockers": blockers,
    }


def _scp_validation(host: str) -> dict[str, Any]:
    ssh = _tcp_connect(host, 22, timeout=4.0)
    return {
        "status": "ready" if ssh["reachable"] else "blocked",
        "reachable": ssh["reachable"],
        "port": 22,
        "method": "TCP/22 readiness plus bootstrap command `ip scp server enable`.",
        "error": ssh.get("error"),
    }


def _claim_cisco_console(
    discovery: dict[str, Any],
    *,
    provider_mode: str,
    reclaim_enabled: bool,
    lock_dirs: tuple[Path, ...] = (Path("/var/lock"), Path("/run/lock")),
) -> dict[str, Any]:
    ownership = _serial_ownership(discovery)
    can_reclaim = provider_mode == "local-lab-readwrite" and reclaim_enabled
    result: dict[str, Any] = {
        "status": "ready",
        "provider_mode": provider_mode,
        "reclaim_requested": reclaim_enabled,
        "reclaim_allowed": can_reclaim,
        "selected_paths": ownership["checked_paths"],
        "initial_ownership": ownership,
        "terminated_processes": [],
        "skipped_processes": [],
        "lock_files_removed": [],
        "lock_file_errors": [],
        "reclaimed": False,
        "blockers": [],
        "post_ownership": ownership,
    }
    if ownership["owned"] and not can_reclaim:
        result["status"] = "blocked"
        result["blockers"].append(
            "Serial console is owned by another process; set CISCO_CONSOLE_RECLAIM=true in local-lab-readwrite mode to reclaim allowed console holders."
        )
        return result
    if can_reclaim:
        for owner in ownership["owners"]:
            if _is_reclaimable_console_owner(owner):
                termination = _terminate_process(int(owner["pid"]))
                result["terminated_processes"].append({**owner, **termination})
                result["reclaimed"] = True
            else:
                result["skipped_processes"].append({**owner, "reason": "process command is not an allowed console holder"})
        lock_cleanup = _clear_console_lock_files(ownership["checked_paths"], lock_dirs=lock_dirs)
        result["lock_files_removed"] = lock_cleanup["removed"]
        result["lock_file_errors"] = lock_cleanup["errors"]
        if lock_cleanup["removed"]:
            result["reclaimed"] = True
    if result["skipped_processes"]:
        result["status"] = "blocked"
        result["blockers"].append("Serial console owner is not an allowed reclaim target.")
    if result["lock_file_errors"]:
        result["status"] = "blocked"
        result["blockers"].append("One or more stale serial lock files could not be removed.")
    if can_reclaim:
        post_discovery = discover_cisco_console(CiscoConsoleConfig.from_settings())
        post_ownership = _serial_ownership(post_discovery)
        result["post_discovery"] = post_discovery
        result["post_ownership"] = post_ownership
        if post_ownership["owned"]:
            result["status"] = "blocked"
            result["blockers"].append("Serial console is still owned after reclaim.")
    return result


def _serial_ownership(discovery: dict[str, Any]) -> dict[str, Any]:
    paths = _console_ownership_paths(discovery)
    owners_by_pid: dict[int, dict[str, Any]] = {}
    for path in paths:
        for pid in _pids_using_path(path):
            owner = owners_by_pid.setdefault(pid, _process_info(pid))
            owner.setdefault("paths", [])
            owner["paths"].append(path)
    owners = []
    for owner in owners_by_pid.values():
        owner["paths"] = list(dict.fromkeys(owner.get("paths") or []))
        owner["summary"] = _owner_summary(owner)
        owners.append(owner)
    return {"checked_paths": paths, "owned": bool(owners), "owners": owners}


def _console_ownership_paths(discovery: dict[str, Any]) -> list[str]:
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
    return list(dict.fromkeys(paths))


def _pids_using_path(path: str) -> list[int]:
    result = subprocess.run(["fuser", path], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return []
    pids = []
    for token in result.stdout.split():
        if token.isdigit():
            pids.append(int(token))
    return list(dict.fromkeys(pids))


def _process_info(pid: int) -> dict[str, Any]:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "pid=", "-o", "comm=", "-o", "args="],
        capture_output=True,
        text=True,
        check=False,
    )
    line = result.stdout.strip()
    if result.returncode != 0 or not line:
        return {"pid": pid, "command": "unknown", "args": ""}
    parts = line.split(maxsplit=2)
    command = parts[1] if len(parts) > 1 else "unknown"
    args = parts[2] if len(parts) > 2 else ""
    return {"pid": pid, "command": command, "args": _redact_process_text(args)}


def _owner_summary(owner: dict[str, Any]) -> str:
    paths = ", ".join(owner.get("paths") or [])
    return f"pid={owner.get('pid')} command={owner.get('command')} paths={paths}"


def _is_reclaimable_console_owner(owner: dict[str, Any]) -> bool:
    command = Path(str(owner.get("command") or "")).name.lower()
    return any(
        command == allowed or command.startswith(f"{allowed}.") or (allowed == "python" and command.startswith("python"))
        for allowed in RECLAIMABLE_CONSOLE_COMMANDS
    )


def _terminate_process(pid: int) -> dict[str, Any]:
    if pid == os.getpid():
        return {"termination": "skipped", "reason": "refusing to terminate current process"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"termination": "already-exited", "signal": "SIGTERM"}
    except PermissionError:
        return {"termination": "failed", "signal": "SIGTERM", "error": "permission denied"}
    time.sleep(0.5)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {"termination": "terminated", "signal": "SIGTERM"}
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return {"termination": "terminated", "signal": "SIGTERM"}
    except PermissionError:
        return {"termination": "failed", "signal": "SIGKILL", "error": "permission denied"}
    return {"termination": "terminated", "signal": "SIGKILL"}


def _clear_console_lock_files(paths: list[str], *, lock_dirs: tuple[Path, ...]) -> dict[str, Any]:
    removed = []
    errors = []
    for lock_path in _console_lock_paths(paths, lock_dirs=lock_dirs):
        if not lock_path.exists():
            continue
        try:
            lock_path.unlink()
            removed.append(str(lock_path))
        except OSError as exc:
            errors.append({"path": str(lock_path), "error": str(exc)})
    return {"removed": removed, "errors": errors}


def _console_lock_paths(paths: list[str], *, lock_dirs: tuple[Path, ...]) -> list[Path]:
    names = []
    for path in paths:
        basename = Path(path).name
        if basename.startswith("tty"):
            names.append(f"LCK..{basename}")
    return list(dict.fromkeys(lock_dir / name for lock_dir in lock_dirs for name in names))


def _env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _send(conn: Any, command: str, *, secret: bool = False) -> None:
    del secret
    conn.write(command.encode("utf-8", errors="replace") + b"\r\n")


def _read(conn: Any, *, window: float) -> str:
    chunks: list[bytes] = []
    for read_window in (window, max(window, 2.0), max(window, 3.0)):
        deadline = time.monotonic() + read_window
        while time.monotonic() < deadline:
            waiting = getattr(conn, "in_waiting", 0)
            data = conn.read(waiting or 256)
            if data:
                chunks.append(data)
            else:
                time.sleep(0.1)
        if chunks:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def _toggle_dtr_rts(conn: Any) -> None:
    for attr in ("dtr", "rts"):
        if not hasattr(conn, attr):
            continue
        try:
            setattr(conn, attr, False)
            time.sleep(0.05)
            setattr(conn, attr, True)
        except Exception:
            continue


def _send_break(conn: Any) -> None:
    try:
        if hasattr(conn, "send_break"):
            conn.send_break(duration=0.25)
    except TypeError:
        conn.send_break()
    except Exception:
        return


def _classify_prompt(text: str) -> Prompt:
    lower = text.lower()
    if not text:
        return Prompt("unknown", "", False)
    if "initial configuration dialog" in lower or "system configuration dialog" in lower or "[yes/no]" in lower:
        return Prompt("setup-wizard", "setup wizard prompt", False)
    if re.search(r"(?im)(?:^|\r|\n)\s*rommon(?:\s+\d+)?\s*>\s*$", text):
        return Prompt("rommon-bootloader", "ROMMON/bootloader prompt", False)
    if re.search(r"(?im)(?:^|\r|\n)\s*switch:\s*$", text):
        return Prompt("password-recovery-ready", "password recovery bootloader prompt", False)
    match = PROMPT_RE.search(text)
    if match:
        prompt = match.group(1)
        if "(config" in prompt.lower():
            return Prompt("config-mode", "configuration prompt", False)
        if prompt.endswith("#"):
            return Prompt("privileged-exec", "DEVICE#", True)
        return Prompt("exec", "DEVICE>", False)
    if "password:" in lower:
        return Prompt("password-required", "password prompt", False)
    if "username:" in lower or "login:" in lower:
        return Prompt("login-required", "login/password prompt", False)
    if _looks_unreadable(text):
        return Prompt("unreadable", "unreadable console text", False)
    return Prompt("unknown", _redact_line(_last_line(text)), False)


def _prompt_match_label(text: str, prompt: Prompt) -> str | None:
    if prompt.state == "login-required":
        return "username_or_login_prompt"
    if prompt.state == "password-required":
        return "password_prompt"
    if "user access verification" in text.lower():
        return "user_access_verification"
    if PROMPT_RE.search(text):
        return "hostname_exec_prompt"
    if prompt.state in {"setup-wizard", "rommon-bootloader", "password-recovery-ready", "unreadable"}:
        return prompt.state
    return None


def _printable_preview(text: str, *, limit: int = 160) -> str:
    preview = "".join(char if char.isprintable() or char in "\r\n\t" else "." for char in text[:limit])
    preview = preview.replace("\r", "\\r").replace("\n", "\\n")
    return _redact_preview(preview)


def _redact_preview(text: str) -> str:
    redacted = text
    for value in (
        settings.cisco_console_port,
        settings.cisco_target_ip,
        _login_username(),
        _login_password(),
        settings.cisco_enable_password,
        os.getenv("CISCO_ENABLE_PASSWORD"),
        os.getenv("ANSIBLE_CISCO_ENABLE_PASSWORD"),
    ):
        if value:
            redacted = redacted.replace(value, "<redacted>")
    redacted = re.sub(r"(?i)(username:\s*)\S+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(?i)(password:\s*)\S+", r"\1<redacted>", redacted)
    return redacted


def _first_sample_preview(samples: list[dict[str, Any]]) -> str:
    for sample in samples:
        preview = sample.get("first_bytes_printable_preview")
        if isinstance(preview, str) and preview:
            return preview
    return ""


def _looks_unreadable(text: str) -> bool:
    if not text:
        return False
    replacement_count = text.count("\ufffd")
    control_count = sum(1 for char in text if ord(char) < 32 and char not in "\r\n\t")
    visible_count = sum(1 for char in text if char.isprintable() and not char.isspace())
    total = max(len(text), 1)
    return (replacement_count + control_count) / total > 0.2 or (total >= 8 and visible_count == 0)


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
    return "serial open or read failed"


def _console_classification(prompt_state: str, text: str) -> str:
    if prompt_state == "unknown" and not text:
        return "no_bytes_read"
    return {
        "unknown": "no_bytes_read",
        "unreadable": "unreadable_gibberish",
        "login-required": "login_prompt",
        "password-required": "password_prompt",
        "exec": "user_exec",
        "privileged-exec": "privileged_exec",
        "config-mode": "config_mode",
        "setup-wizard": "setup_wizard",
        "rommon-bootloader": "rommon_or_bootloader",
        "password-recovery-ready": "rommon_or_bootloader",
        "port-in-use": "port_in_use",
        "permission-denied": "permission_denied",
    }.get(prompt_state, "no_bytes_read")


def _final_console_prompt_state(samples: list[dict[str, Any]]) -> str:
    if not any(sample.get("captured") for sample in samples):
        return "unknown-no-output"
    if any(sample.get("classification") == "unreadable_gibberish" for sample in samples):
        return "unreadable"
    for sample in samples:
        prompt = sample.get("prompt") if isinstance(sample.get("prompt"), dict) else {}
        state = prompt.get("state")
        if state in {"permission-denied", "port-in-use"}:
            return str(state)
    return "unknown"


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
    if command.startswith("show version"):
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
    if command.startswith("show running-config"):
        return {
            "hostname_present": bool(re.search(r"(?im)^hostname\s+", output)),
            "ssh_present": bool(re.search(r"(?im)^ip ssh\s+", output)),
            "scp_present": bool(re.search(r"(?im)^ip scp\s+", output)),
            "username_lines_redacted": len(re.findall(r"(?im)^username\s+", output)),
            "vlan_interface_lines": len(re.findall(r"(?im)^interface Vlan", output)),
            "raw_running_config_redacted": True,
        }
    return {"captured": bool(output)}


def _detect_access_ports_from_interfaces_status(output: str) -> list[str]:
    ports = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        port = parts[0]
        vlan = parts[-4] if len(parts) >= 6 else parts[2]
        if not _looks_like_switchport(port):
            continue
        if vlan.lower() in {"trunk", "routed", "disabled", "unassigned"}:
            continue
        if vlan.isdigit():
            ports.append(port)
    return list(dict.fromkeys(ports))


def _looks_like_switchport(value: str) -> bool:
    return bool(re.match(r"(?i)^(?:gi|gig|gigabitethernet|te|tengigabitethernet|fa|fastethernet|eth|ethernet)\S+", value))


def _parse_vlan10_interface_state(output: str) -> dict[str, Any]:
    for line in output.splitlines():
        if not re.search(r"(?i)^vlan10\s+", line.strip()):
            continue
        parts = line.split()
        if len(parts) >= 6:
            return {
                "configured": True,
                "interface": parts[0],
                "ip": parts[1],
                "line_status": parts[-2].lower(),
                "protocol_status": parts[-1].lower(),
            }
        return {"configured": True, "interface": parts[0], "ip": None, "line_status": "unknown", "protocol_status": "unknown"}
    return {"configured": False, "interface": "Vlan10", "ip": None, "line_status": None, "protocol_status": None}


def _parse_vlan10_ports(vlan_output: str, interfaces_output: str) -> list[str]:
    ports: list[str] = []
    for line in vlan_output.splitlines():
        if not re.match(r"^\s*10\s+", line):
            continue
        tokens = re.split(r"[\s,]+", line.strip())
        for token in tokens[2:]:
            if _looks_like_switchport(token):
                ports.append(token)
    if ports:
        return list(dict.fromkeys(ports))
    for line in interfaces_output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        port = parts[0]
        vlan = parts[-4] if len(parts) >= 6 else parts[2]
        if _looks_like_switchport(port) and vlan == "10":
            ports.append(port)
    return list(dict.fromkeys(ports))


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


def _host_route_to(host: str) -> dict[str, Any]:
    result = subprocess.run(["ip", "route", "get", host], capture_output=True, text=True, check=False)
    route = " ".join((result.stdout or result.stderr or "").split())
    return {
        "status": "ready" if result.returncode == 0 else "blocked",
        "returncode": result.returncode,
        "route": route,
        "dev": _route_token(route, "dev"),
        "src": _route_token(route, "src"),
        "error": None if result.returncode == 0 else route,
    }


def _route_token(route: str, token: str) -> str | None:
    parts = route.split()
    try:
        index = parts.index(token)
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def _classify_vlan10_failure(
    apply_result: dict[str, Any],
    switch_validation: dict[str, Any],
    ethernet: dict[str, Any],
) -> str:
    if apply_result.get("status") not in {"completed", None, "not-attempted"}:
        return "config"
    if apply_result.get("status") == "not-attempted" and switch_validation.get("status") == "not-attempted":
        return "not-applied"
    vlan10_state = switch_validation.get("vlan10_state") if isinstance(switch_validation, dict) else {}
    if not vlan10_state or vlan10_state.get("configured") is False:
        return "config"
    if vlan10_state.get("ip") != LAB_CISCO_MANAGEMENT_IP:
        return "config"
    if vlan10_state.get("line_status") != "up" or vlan10_state.get("protocol_status") != "up":
        return "svi_down"
    ports = switch_validation.get("ports_assigned_vlan10") or []
    if not ports:
        return "port_down"
    route = ethernet.get("host_route") if isinstance(ethernet, dict) else {}
    if not route or route.get("status") != "ready":
        return "host_routing"
    ping = ethernet.get("ping") if isinstance(ethernet, dict) else {}
    if ping.get("status") != "ok":
        return "host_reachability"
    ssh = ethernet.get("ssh") if isinstance(ethernet, dict) else {}
    scp = ethernet.get("scp") if isinstance(ethernet, dict) else {}
    if ssh.get("reachable") is False or scp.get("reachable") is False:
        return "ssh_service"
    if ethernet.get("status") != "ready":
        return "host_reachability"
    return "passed"


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
    LOGIN_BOOTSTRAP_FIX_REPORT.write_text(
        _markdown(sanitized, title="Cisco Login Bootstrap Fix Report"),
        encoding="utf-8",
    )
    COMMANDER_MODE_REPORT.write_text(
        _markdown(sanitized, title="Cisco Console Commander Mode Report"),
        encoding="utf-8",
    )
    PRIVILEGE_HARDENING_REPORT.write_text(
        _markdown(sanitized, title="Cisco Privilege Hardening Report"),
        encoding="utf-8",
    )
    PRIVILEGE_DIAGNOSIS_REPORT.write_text(
        _markdown(sanitized, title="Cisco Privilege Diagnosis Report"),
        encoding="utf-8",
    )
    PASSWORD_RECOVERY_REPORT.write_text(_password_recovery_markdown(sanitized), encoding="utf-8")
    if _should_write_bootstrap_apply_report(sanitized):
        BOOTSTRAP_APPLY_REPORT.write_text(_bootstrap_apply_markdown(sanitized), encoding="utf-8")
    VLAN10_BOOTSTRAP_FIX_REPORT.write_text(_vlan10_bootstrap_fix_markdown(sanitized), encoding="utf-8")
    print(json.dumps(_summary(sanitized), indent=2))
    return 0 if payload["status"] in {"completed", "blocked"} else 1


def _should_write_bootstrap_apply_report(payload: dict[str, Any]) -> bool:
    apply = dict(dict(payload.get("stages") or {}).get("apply") or {})
    return apply.get("status") != "not-attempted"


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
        "vlan10_bootstrap_fix_report": str(VLAN10_BOOTSTRAP_FIX_REPORT.relative_to(REPO_ROOT)),
        "login_bootstrap_fix_report": str(LOGIN_BOOTSTRAP_FIX_REPORT.relative_to(REPO_ROOT)),
        "commander_mode_report": str(COMMANDER_MODE_REPORT.relative_to(REPO_ROOT)),
        "details": str(DETAILS.relative_to(REPO_ROOT)),
    }


def _markdown(payload: dict[str, Any], *, title: str = "Cisco 4h Lab Run Report") -> str:
    stages = payload.get("stages", {})
    adapter = stages.get("adapter_discovery", {})
    claim = stages.get("console_preflight_claim", {})
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
            "- Configuration apply: `not run unless --apply is passed`.",
            "",
            "## Stage Evidence",
            "",
            f"- Adapter discovery: `{adapter.get('status')}`; source `{adapter.get('selection_source')}`.",
            f"- Port ownership: `{adapter.get('ownership', {}).get('owned')}`.",
            f"- Console claim requested: `{claim.get('reclaim_requested')}`.",
            f"- Console claim allowed: `{claim.get('reclaim_allowed')}`.",
            f"- Console claim reclaimed: `{claim.get('reclaimed')}`.",
            f"- Console claim terminated processes: `{len(claim.get('terminated_processes') or [])}`.",
            f"- Console claim skipped processes: `{len(claim.get('skipped_processes') or [])}`.",
            f"- Console stale lock files removed: `{claim.get('lock_files_removed') or []}`.",
            f"- Console prompt detection: tried `{prompt.get('bauds_tried')}` and wake sequences `{prompt.get('wake_sequences_tried')}`.",
            f"- First bytes printable preview: `{prompt.get('first_bytes_printable_preview')}`.",
            f"- Prompt regex matched: `{prompt.get('prompt_regex_matched')}`.",
            f"- Login state transitions: `{prompt.get('login_state_transitions')}`.",
            f"- User Access Verification seen: `{prompt.get('user_access_verification_seen')}`.",
            f"- Username prompt seen: `{prompt.get('username_prompt_seen')}`.",
            f"- Password prompt seen: `{prompt.get('password_prompt_seen')}`.",
            f"- Final prompt: `{prompt.get('final_prompt')}`.",
            f"- Privilege initial prompt state: `{privilege.get('initial_prompt_state')}`.",
            f"- Enable command sent: `{privilege.get('enable_command_sent')}`.",
            f"- Enable password prompt seen: `{privilege.get('password_prompt_seen')}`.",
            f"- Privilege final prompt state: `{privilege.get('final_prompt_state')}`.",
            f"- Readable privilege level: `{privilege.get('privilege_level')}`.",
            f"- Enable password rejected: `{_enable_password_rejected_label(privilege)}`.",
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


def _enable_password_rejected_label(privilege: dict[str, Any]) -> str:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return "no"
    debug = privilege.get("debug") if isinstance(privilege.get("debug"), dict) else {}
    if debug.get("enable_command_sent") and debug.get("password_prompt_seen"):
        return "yes"
    if debug.get("enable_command_sent"):
        return "unknown"
    return "unknown"


def _password_recovery_required(privilege: dict[str, Any]) -> str:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return "false"
    if privilege.get("final_prompt_state") in {"rommon-bootloader", "password-recovery-ready"}:
        return "operator-physical-console-recovery"
    if _enable_password_rejected(privilege):
        return "operator-confirm-password-recovery-or-factory-reset"
    if privilege.get("initial_prompt_state") == "exec" and not privilege.get("enable_command_sent"):
        return "unknown-enable-not-sent"
    return "unknown"


def _privilege_next_action(privilege: dict[str, Any]) -> str:
    if privilege.get("final_prompt_state") == "privileged-exec":
        return "Privilege is confirmed; continue Cisco management network validation."
    if privilege.get("final_prompt_state") == "password-recovery-ready":
        return "Recover Cisco password from console, then rerun Cisco bootstrap."
    if privilege.get("final_prompt_state") == "rommon-bootloader":
        return "Use the documented ROMMON/bootloader recovery path before rerunning Cisco bootstrap."
    if _enable_password_rejected(privilege):
        return (
            "Confirm the enable credential out of band. If no valid enable credential exists, "
            "perform the documented password recovery or factory reset procedure, then rerun Cisco bootstrap."
        )
    if privilege.get("initial_prompt_state") == "exec":
        return "Rerun the Cisco privilege workflow and verify whether enable sends a Password: challenge."
    if privilege.get("initial_prompt_state") == "login-required":
        return "Recover Cisco password from console or provide valid console login credentials, then rerun Cisco bootstrap."
    return "Restore a user exec or privileged exec prompt before retrying Cisco bootstrap."


def _password_recovery_markdown(payload: dict[str, Any]) -> str:
    stages = payload.get("stages", {})
    prompt = stages.get("console_prompt_detection", {})
    privilege = stages.get("privilege_escalation", {})
    lines = [
        "# Cisco Password Recovery Guidance Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Provider mode: `{payload.get('provider_mode')}`",
        f"- Initial prompt state: `{privilege.get('initial_prompt_state') or prompt.get('prompt_state')}`",
        f"- Enable command sent: `{privilege.get('enable_command_sent')}`",
        f"- Password prompt seen: `{privilege.get('password_prompt_seen')}`",
        f"- Enable rejected: `{_enable_password_rejected_label(privilege)}`",
        f"- Final prompt state: `{privilege.get('final_prompt_state')}`",
        f"- Privilege level: `{privilege.get('privilege_level')}`",
        f"- Password recovery status: `{_password_recovery_required(privilege)}`",
        f"- Next action: {_privilege_next_action(privilege)}",
        "",
        "## Detection Text",
        "",
        "- `user exec only`: enable is required before bootstrap apply; no configuration is sent from `DEVICE>`.",
        "- `enable password rejected`: enable was sent, a password prompt was seen, and the final prompt did not become `DEVICE#`.",
        "- `setup wizard`: stop at the initial configuration dialog; do not answer wizard prompts from automation.",
        "- `ROMMON/bootloader prompt`: use the physical-console recovery path before normal bootstrap.",
        "- `password recovery ready`: bootloader recovery prompt is present; recover credentials from console, then rerun bootstrap.",
        "",
        "## Manual Password Recovery Runbook",
        "",
        "1. Connect the console cable to the Cisco console port and confirm the selected serial port and baud.",
        "2. Power cycle or reload only under local operator control, then interrupt boot if the platform recovery procedure requires it.",
        "3. At ROMMON or bootloader, use the platform-supported method to ignore startup configuration.",
        "4. Boot the switch and reach user or privileged exec without printing credentials in this app.",
        "5. Set new local admin and enable credentials manually on the console.",
        "6. Save the configuration manually after verifying the intended target.",
        "7. Update `.env.local.real-lab` locally with the new credential values, then rerun the Cisco privilege check.",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in payload.get("blockers") or []] or ["- none"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- No secrets, raw console transcript, or raw running-config are stored here.",
            "- No bootstrap configuration is applied unless privileged exec is confirmed.",
            "- Password recovery requires local operator control of the physical console.",
            "",
        ]
    )
    return "\n".join(lines)


def _bootstrap_apply_markdown(payload: dict[str, Any]) -> str:
    stages = payload.get("stages", {})
    privilege = stages.get("privilege_escalation", {})
    apply = stages.get("apply", {})
    ethernet = stages.get("ethernet_management_validation", {})
    lines = [
        "# Cisco Bootstrap Apply Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Provider mode: `{payload.get('provider_mode')}`",
        "- Management IP requested: `192.168.1.204`",
        f"- Privileged exec reached: `{privilege.get('final_prompt_state') == 'privileged-exec'}`",
        f"- Privilege level readback: `{privilege.get('privilege_level')}`",
        f"- Bootstrap apply status: `{apply.get('status') or 'not-attempted'}`",
        f"- Serial writes attempted: `{bool(apply.get('serial_writes_attempted'))}`",
        f"- Ethernet management validation: `{ethernet.get('status') or 'not-attempted'}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend([f"- {item}" for item in payload.get("blockers") or []] or ["- none"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- No secrets were printed in this report.",
            "- No reload was performed unless explicitly listed above.",
            "- Mock results were not used as substitutes for live-lab evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _vlan10_bootstrap_fix_markdown(payload: dict[str, Any]) -> str:
    stages = payload.get("stages", {})
    plan = stages.get("bootstrap_plan", {})
    apply = stages.get("apply", {})
    switch = stages.get("vlan10_switch_validation", {})
    ethernet = stages.get("ethernet_management_validation", {})
    route = ethernet.get("host_route") if isinstance(ethernet.get("host_route"), dict) else {}
    vlan10 = switch.get("vlan10_state") if isinstance(switch.get("vlan10_state"), dict) else {}
    commands_sent = apply.get("commands_sent_redacted") or []
    planned_commands = plan.get("redacted_commands") or []
    ports = switch.get("ports_assigned_vlan10") or []
    configured_ports = plan.get("selected_or_detected_access_ports") or []
    lines = [
        "# Cisco VLAN 10 Bootstrap Fix Report",
        "",
        "## Summary",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Provider mode: `{payload.get('provider_mode')}`",
        f"- Overall status: `{payload.get('status')}`",
        f"- Management VLAN: `{plan.get('management_vlan') or '10'}`",
        f"- Management interface: `{plan.get('management_interface') or 'Vlan10'}`",
        f"- Management IP: `{plan.get('management_ip') or LAB_CISCO_MANAGEMENT_IP}`",
        f"- Management prefix: `{plan.get('management_prefix') or '/24'}`",
        f"- Bootstrap apply status: `{apply.get('status') or 'not-attempted'}`",
        f"- Serial writes attempted: `{bool(apply.get('serial_writes_attempted'))}`",
        f"- Failure classification: `{ethernet.get('failure_classification') or 'unknown'}`",
        "",
        "## Commands Sent",
        "",
    ]
    if commands_sent:
        lines.extend(f"- `{command}`" for command in commands_sent)
    else:
        lines.append("- none")
        lines.append("")
        lines.append("## Planned Commands")
        lines.append("")
        lines.extend(f"- `{command}`" for command in planned_commands)
    lines.extend(
        [
            "",
            "## Switch Validation",
            "",
            f"- Vlan10 configured: `{vlan10.get('configured')}`",
            f"- Vlan10 IP: `{vlan10.get('ip')}`",
            f"- Vlan10 line state: `{vlan10.get('line_status')}`",
            f"- Vlan10 protocol state: `{vlan10.get('protocol_status')}`",
            f"- Always-access lab ports: `{plan.get('always_access_ports') or []}`",
            f"- Access port source: `{plan.get('access_port_source')}`",
            f"- Configured/detected lab ports: `{configured_ports}`",
            f"- Ports assigned to VLAN 10: `{ports}`",
            f"- All configured/detected ports assigned to VLAN 10: `{switch.get('all_configured_ports_assigned_vlan10')}`",
            "",
            "## Ubuntu Route To Cisco",
            "",
            f"- Route status: `{route.get('status')}`",
            f"- Route: `{route.get('route')}`",
            f"- Interface: `{route.get('dev')}`",
            f"- Source IP: `{route.get('src')}`",
            "",
            "## Network Reachability",
            "",
            f"- Ping: `{(ethernet.get('ping') or {}).get('status')}`",
            f"- SSH TCP/22 reachable: `{(ethernet.get('ssh') or {}).get('reachable')}`",
            f"- SCP TCP/22 readiness: `{(ethernet.get('scp') or {}).get('reachable')}`",
            "",
            "## Failure Classification Guide",
            "",
            "- `config`: expected VLAN 10, SVI, local admin, SSH/SCP, or line login config was not confirmed.",
            "- `config` also includes `interface Vlan10` using an IP other than `192.168.1.204`.",
            "- `svi_down`: `interface Vlan10` exists but line/protocol is not up/up.",
            "- `port_down`: no selected/detected access port is confirmed in VLAN 10.",
            "- `host_routing`: switch-side validation looks usable, but Ubuntu cannot route/reach `192.168.1.204`.",
            "- `host_reachability`: Ubuntu can route to `192.168.1.204`, but ping or another host reachability check failed.",
            "- `ssh_service`: VLAN 10 and ping are usable, but SSH/SCP TCP readiness failed.",
            "- `passed`: switch-side validation and Ubuntu reachability passed.",
            "",
            "## Blockers",
            "",
        ]
    )
    lines.extend([f"- {item}" for item in payload.get("blockers") or []] or ["- none"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Local admin secret values are redacted.",
            "- Raw console output and raw running-config are not saved.",
            "- `write memory` is only sent by the guarded apply path.",
            "",
        ]
    )
    return "\n".join(lines)


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(
        payload,
        [
            settings.cisco_console_port,
            None if settings.cisco_target_ip == LAB_CISCO_MANAGEMENT_IP else settings.cisco_target_ip,
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
