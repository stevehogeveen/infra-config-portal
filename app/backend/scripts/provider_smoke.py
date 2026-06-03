from __future__ import annotations

import json
import os
import socket
import shutil
import time
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"
REPORT_DIR = REPO_ROOT / "artifacts" / "real-lab"
CONNECT_TIMEOUT_SECONDS = 3.0
REQUIRED_ENV_NAMES = (
    "LAB_CLOSED_LOOP_ACK",
    "LAB_READONLY_ACK",
    "LAB_DESTRUCTIVE_ACK",
    "ILO_TEST_HOST",
    "ILO_TEST_USERNAME",
    "ILO_TEST_PASSWORD",
    "ESXI_CONFIGURED",
    "ESXI_TEST_HOST",
    "ESXI_TEST_USERNAME",
    "ESXI_TEST_PASSWORD",
    "CISCO_MGMT_CONFIGURED",
    "CISCO_TARGET_IP",
    "CISCO_TEST_USERNAME",
    "CISCO_TEST_PASSWORD",
)

if REAL_LAB_ENV.exists():
    for key, value in dotenv_values(REAL_LAB_ENV).items():
        if key == "PROVIDER_MODE" or value is None or key in os.environ:
            continue
        os.environ[key] = value

from app.core.config import settings
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.lab_safety import current_lab_safety
from app.providers.redaction import redact_sensitive
from app.providers.registry import ProviderRegistryError, provider_registry


def main() -> int:
    print(f"provider_mode={settings.provider_mode}")
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_mode": settings.provider_mode,
        "preflight": _preflight_summary(),
        "guarded_rebuild_planning": _guarded_rebuild_planning(),
        "provider_status": [],
        "probes": [],
        "quality_gate_note": (
            "Hardware and manual probe failures are reported as lab blockers; "
            "provider-smoke exits successfully unless the status code path itself fails."
        ),
    }
    print(json.dumps(redact_sensitive(report["preflight"], _redaction_values()), indent=2))

    try:
        statuses = provider_registry().statuses()
    except ProviderRegistryError as exc:
        print(f"provider_status=blocked message={exc}")
        report["provider_status_error"] = str(exc)
        _write_report(report)
        return 0

    status_payload = [_status_summary(_to_dict(status)) for status in statuses]
    report["provider_status"] = status_payload
    print(json.dumps(redact_sensitive({"providers": status_payload}), indent=2))

    cisco_status = next((item for item in status_payload if item["id"] == "cisco-console"), None)
    if cisco_status:
        discovery = cisco_status.get("discovery") or {}
        print(
            json.dumps(
                {
                    "cisco_console_discovery": {
                        "status": discovery.get("status"),
                        "selection_source": discovery.get("selection_source"),
                        "effective_path": discovery.get("effective_path"),
                        "candidate_counts": discovery.get(
                            "candidate_counts",
                            {"total": len(discovery.get("candidates", []))},
                        ),
                        "candidates": discovery.get("candidates", []),
                    }
                },
                indent=2,
            )
        )

    if settings.provider_mode != "local-readonly":
        print("probes=skipped reason=PROVIDER_MODE is not local-readonly")
        _write_report(report)
        return 0

    for provider_id, adapter in (
        ("ilo-redfish", IloRedfishAdapter()),
        ("cisco-console", CiscoConsoleAdapter()),
        ("cisco-ansible", CiscoAnsibleAdapter()),
        ("esxi-readonly", EsxiReadonlyAdapter()),
    ):
        report["probes"].append(_run_optional_probe(provider_id, adapter))

    _write_report(report)
    return 0


def _run_optional_probe(provider_id: str, adapter: Any) -> dict[str, Any]:
    status = adapter.health()
    enabled_actions = [action for action in status.safe_actions if action.enabled]
    if not enabled_actions:
        status_dict = _status_summary(_to_dict(status))
        summary = {
            "provider_id": provider_id,
            "status": "skipped",
            "message": _disabled_probe_reason(status),
            "configuration": status_dict.get("configuration", {}),
            "blockers": status.blockers,
            "warnings": status.warnings,
        }
        not_attempted = _disabled_probe_not_attempted(provider_id)
        if not_attempted:
            summary["not_attempted"] = not_attempted
        print(json.dumps(redact_sensitive(summary, _redaction_values()), indent=2))
        return summary

    try:
        result = adapter.probe()
    except Exception as exc:
        summary = {
            "provider_id": provider_id,
            "status": "failed",
            "message": f"Probe raised an exception: {exc.__class__.__name__}",
            "blockers": ["Provider probe raised an exception."],
            "warnings": [],
        }
        print(json.dumps(redact_sensitive(summary, _redaction_values()), indent=2))
        return summary

    summary = _probe_summary(result)
    print(json.dumps(redact_sensitive(summary, _redaction_values()), indent=2))
    return summary


def _preflight_summary() -> dict[str, Any]:
    safety = current_lab_safety()
    return {
        "env_file": {
            "path": ".env.local.real-lab",
            "exists": REAL_LAB_ENV.exists(),
            "mode": _file_mode(REAL_LAB_ENV),
        },
        "required_env": _required_env_summary(),
        "safety": safety.as_flags(),
        "dangerous_mode": "enabled" if safety.destructive_allowed else "disabled",
        "tool_availability": {
            "ansible": shutil.which("ansible") is not None,
            "ansible-inventory": shutil.which("ansible-inventory") is not None,
            "python": shutil.which("python3") is not None,
        },
        "serial_candidates": _serial_candidate_summary(),
        "targets": {
            "ilo": {"configured": bool(settings.ilo_test_host)},
            "esxi": {
                "configured": settings.esxi_configured,
                "planned_target": bool(settings.esxi_test_host),
            },
            "cisco": {
                "management_configured": settings.cisco_mgmt_configured,
                "planned_target": bool(settings.cisco_target_ip),
                "console_discovery": "always",
            },
        },
        "tcp_preflight": _tcp_preflight(),
    }


def _required_env_summary() -> list[dict[str, str]]:
    return [{"name": name, "status": _present(name)} for name in REQUIRED_ENV_NAMES]


def _guarded_rebuild_planning() -> dict[str, Any]:
    safety = current_lab_safety()
    if not safety.destructive_allowed:
        return {
            "status": "disabled",
            "message": "LAB_DESTRUCTIVE_ACK is not REBUILD_LAB; no rebuild/bootstrap plans are prepared.",
            "apply_allowed": False,
            "plans": [],
        }

    stop_reason = (
        "The app does not yet have an explicit destructive confirmation UX, "
        "and live target identity has not been verified."
    )
    return {
        "status": "blocked",
        "message": "Guarded rebuild/bootstrap planning is blocked before apply.",
        "apply_allowed": False,
        "stop_reason": stop_reason,
        "plans": [
            _blocked_plan(
                "cisco-console-bootstrap",
                "Cisco console bootstrap to configured management IP",
                settings.cisco_target_ip,
            ),
            _blocked_plan(
                "cisco-enable-ssh-scp",
                "Cisco SSH/SCP enablement preview",
                settings.cisco_target_ip,
            ),
            _blocked_plan(
                "esxi-rebuild-config",
                "ESXi rebuild/config workflow preview",
                settings.esxi_test_host,
            ),
            _blocked_plan(
                "ilo-virtual-media-boot",
                "iLO virtual media and boot workflow preview",
                settings.ilo_test_host,
            ),
            _blocked_plan(
                "firmware-upgrade",
                "Firmware upgrade workflow preview",
                settings.ilo_test_host,
            ),
        ],
    }


def _blocked_plan(plan_id: str, title: str, configured_target: str | None) -> dict[str, Any]:
    return {
        "id": plan_id,
        "title": title,
        "status": "blocked",
        "intended_target_configured": bool(configured_target),
        "apply_allowed": False,
        "log_tags": ["DISCOVER", "COMPARE", "PLAN", "DECISION", "BLOCKED"],
        "stop_reason": (
            "Discovered target identity was not verified and no explicit destructive "
            "confirmation step exists in the app."
        ),
        "not_attempted": [
            "wipe",
            "reset",
            "reinstall",
            "configure terminal",
            "write memory",
            "reload",
            "virtual media mount",
            "power cycle",
            "firmware upgrade",
        ],
    }


def _present(name: str) -> str:
    if name == "ESXI_CONFIGURED":
        return "enabled" if settings.esxi_configured else "disabled"
    if name == "CISCO_MGMT_CONFIGURED":
        return "enabled" if settings.cisco_mgmt_configured else "disabled"
    if name.startswith("ESXI_") and not settings.esxi_configured:
        if name == "ESXI_TEST_HOST" and settings.esxi_test_host:
            return "planned"
        return "not-required"
    if name.startswith("CISCO_") and name != "CISCO_MGMT_CONFIGURED":
        if not settings.cisco_mgmt_configured:
            if name == "CISCO_TARGET_IP" and settings.cisco_target_ip:
                return "planned"
            return "not-required"
    value = getattr(settings, _setting_name(name), None)
    if name == "LAB_DESTRUCTIVE_ACK":
        return "enabled" if value == "REBUILD_LAB" else "disabled"
    return "present" if value else "missing"


def _setting_name(env_name: str) -> str:
    return {
        "LAB_CLOSED_LOOP_ACK": "lab_closed_loop_ack",
        "LAB_READONLY_ACK": "lab_readonly_ack",
        "LAB_DESTRUCTIVE_ACK": "lab_destructive_ack",
        "ILO_TEST_HOST": "ilo_test_host",
        "ILO_TEST_USERNAME": "ilo_test_username",
        "ILO_TEST_PASSWORD": "ilo_test_password",
        "ESXI_CONFIGURED": "esxi_configured",
        "ESXI_TEST_HOST": "esxi_test_host",
        "ESXI_TEST_USERNAME": "esxi_test_username",
        "ESXI_TEST_PASSWORD": "esxi_test_password",
        "CISCO_MGMT_CONFIGURED": "cisco_mgmt_configured",
        "CISCO_TARGET_IP": "cisco_target_ip",
        "CISCO_TEST_USERNAME": "cisco_test_username",
        "CISCO_TEST_PASSWORD": "cisco_test_password",
    }[env_name]


def _file_mode(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)


def _serial_candidate_summary() -> dict[str, Any]:
    stable = (
        sorted(Path("/dev/serial/by-id").glob("*"))
        if Path("/dev/serial/by-id").exists()
        else []
    )
    usb = sorted(Path("/dev").glob("ttyUSB*"))
    acm = sorted(Path("/dev").glob("ttyACM*"))
    return {
        "stable_by_id_count": len(stable),
        "ttyUSB_count": len(usb),
        "ttyACM_count": len(acm),
        "stable_by_id_paths": [str(path) for path in stable],
        "fallback_paths": [str(path) for path in [*usb, *acm]],
    }


def _tcp_preflight() -> dict[str, Any]:
    checks = {
        "ilo_https": {
            "host": settings.ilo_test_host,
            "port": 443,
            "configured": bool(settings.ilo_test_host),
            "planned": False,
            "skip_reason": None,
        },
        "esxi_https": {
            "host": settings.esxi_test_host,
            "port": 443,
            "configured": settings.esxi_configured,
            "planned": bool(settings.esxi_test_host),
            "skip_reason": (
                None
                if settings.esxi_configured
                else "ESXI_CONFIGURED=false; ESXi management network is a planned target."
            ),
        },
        "cisco_ssh": {
            "host": settings.cisco_target_ip,
            "port": 22,
            "configured": settings.cisco_mgmt_configured,
            "planned": bool(settings.cisco_target_ip),
            "skip_reason": (
                None
                if settings.cisco_mgmt_configured
                else "CISCO_MGMT_CONFIGURED=false; use console bootstrap before SSH."
            ),
        },
    }
    if settings.provider_mode != "local-readonly":
        return {
            label: _skipped_tcp_check(
                check["host"],
                "PROVIDER_MODE is not local-readonly.",
                configured=bool(check["configured"]),
                planned=bool(check["planned"]),
            )
            for label, check in checks.items()
        }

    safety = current_lab_safety()
    if not safety.readonly_allowed:
        return {
            label: _skipped_tcp_check(
                check["host"],
                "LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES are required.",
                configured=bool(check["configured"]),
                planned=bool(check["planned"]),
            )
            for label, check in checks.items()
        }

    results: dict[str, Any] = {}
    for label, check in checks.items():
        host = check["host"]
        if check["skip_reason"]:
            results[label] = _skipped_tcp_check(
                host,
                str(check["skip_reason"]),
                configured=False,
                planned=bool(check["planned"]),
            )
        elif host:
            results[label] = _tcp_connect(str(host), int(check["port"]))
        else:
            results[label] = {"configured": False, "reachable": False}
    return results


def _skipped_tcp_check(
    host: str | None,
    reason: str,
    configured: bool | None = None,
    planned: bool = False,
) -> dict[str, Any]:
    return {
        "configured": bool(host) if configured is None else configured,
        "planned_target": planned,
        "reachable": False,
        "skipped": True,
        "reason": reason,
    }


def _tcp_connect(host: str, port: int) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, 4):
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_SECONDS):
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "ok",
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                return {"configured": True, "reachable": True, "port": port, "attempts": attempts}
        except OSError as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error": exc.__class__.__name__,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            )
    return {"configured": True, "reachable": False, "port": port, "attempts": attempts}


def _probe_summary(result: dict[str, Any]) -> dict[str, Any]:
    safe_keys = {
        "provider_id",
        "status",
        "message",
        "warnings",
        "blockers",
        "checked_at",
        "phases",
        "not_attempted",
        "base_url",
        "tls_verify",
        "timeout_seconds",
        "max_attempts",
        "requests",
        "service_root",
        "managers",
        "systems",
        "chassis",
        "power",
        "thermal",
        "firmware",
        "discovery",
        "prompt_state",
        "prompt_sample",
        "safe_show_commands",
        "ssh_reachability",
        "tool_availability",
        "https_reachability",
        "https_requests",
        "vim_service_versions",
    }
    return {
        key: value
        for key, value in result.items()
        if key in safe_keys
    }


def _status_summary(status: dict[str, Any]) -> dict[str, Any]:
    configuration = status.get("configuration") or {}
    if status.get("id") == "ilo-redfish":
        configuration = {
            "host_configured": bool(configuration.get("host_configured")),
            "username_configured": bool(configuration.get("username_configured")),
            "password_configured": bool(configuration.get("password_configured")),
            "tls_verify": configuration.get("tls_verify"),
            "missing_fields": configuration.get("missing_fields", []),
        }
    if status.get("id") in {"cisco-ansible", "esxi-readonly"}:
        configuration = {
            key: value
            for key, value in configuration.items()
            if key.endswith("_configured")
            or key.endswith("_available")
            or key
            in {
                "tls_verify",
                "missing_fields",
                "planned_target",
                "safe_next_action",
                "closed_loop_ack",
                "readonly_ack",
                "destructive_ack",
                "readonly_allowed",
                "destructive_allowed",
            }
        }

    return {
        "id": status.get("id"),
        "name": status.get("name"),
        "mode": status.get("mode"),
        "status": status.get("status"),
        "configuration": configuration,
        "discovery": status.get("discovery"),
        "blockers": status.get("blockers", []),
        "warnings": status.get("warnings", []),
        "safe_actions": status.get("safe_actions", []),
        "disabled_actions": status.get("disabled_actions", []),
    }


def _to_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return dict(value)


def _write_report(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sanitized = redact_sensitive(report, _redaction_values())
    json_path = REPORT_DIR / f"provider-smoke-{stamp}.json"
    markdown_path = REPORT_DIR / f"provider-smoke-{stamp}.md"
    json_path.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(sanitized), encoding="utf-8")
    print(f"report_json={json_path.relative_to(REPO_ROOT)}")
    print(f"report_markdown={markdown_path.relative_to(REPO_ROOT)}")


def _markdown_report(report: dict[str, Any]) -> str:
    preflight = report.get("preflight") or {}
    lines = [
        "# Real Lab Provider Smoke",
        "",
        f"Checked at: {report.get('checked_at', 'unknown')}",
        f"Provider mode: {report.get('provider_mode', 'unknown')}",
        "",
        "## Preflight",
        f"- env_file_exists: {((preflight.get('env_file') or {}).get('exists', False))}",
        f"- env_file_mode: {((preflight.get('env_file') or {}).get('mode') or 'unknown')}",
        f"- dangerous_mode: {preflight.get('dangerous_mode', 'unknown')}",
    ]
    for item in preflight.get("required_env", []):
        lines.append(f"- {item.get('name', 'unknown')}: {item.get('status', 'unknown')}")
    tools = preflight.get("tool_availability") or {}
    if tools:
        lines.append(
            "- tools: "
            + ", ".join(f"{key}={value}" for key, value in sorted(tools.items()))
        )
    serial = preflight.get("serial_candidates") or {}
    if serial:
        lines.append(
            "- serial_candidates: "
            f"stable_by_id={serial.get('stable_by_id_count', 0)}, "
            f"ttyUSB={serial.get('ttyUSB_count', 0)}, "
            f"ttyACM={serial.get('ttyACM_count', 0)}"
        )
    tcp = preflight.get("tcp_preflight") or {}
    for label, value in sorted(tcp.items()):
        if isinstance(value, dict):
            if value.get("skipped"):
                lines.append(
                    f"- {label}: skipped=true, reason={value.get('reason', 'unknown')}"
                )
            else:
                lines.append(f"- {label}: reachable={value.get('reachable', False)}")

    lines.extend(
        [
            "",
            "## Safety",
        ]
    )
    safety = ((report.get("preflight") or {}).get("safety") or {})
    for key, value in safety.items():
        lines.append(f"- {key}: {value}")
    guarded = report.get("guarded_rebuild_planning") or {}
    lines.extend(
        [
            "",
            "## Guarded Rebuild Planning",
            f"- status: {guarded.get('status', 'unknown')}",
            f"- apply_allowed: {guarded.get('apply_allowed', False)}",
            f"- stop_reason: {guarded.get('stop_reason') or guarded.get('message') or 'not set'}",
        ]
    )
    for plan in guarded.get("plans", []):
        lines.append(f"- {plan.get('id')}: {plan.get('status')} - {plan.get('stop_reason')}")
    lines.extend(["", "## Provider Status"])
    for provider in report.get("provider_status", []):
        lines.append(
            f"- {provider.get('id')}: {provider.get('status')} - "
            f"{provider.get('blockers') or provider.get('warnings') or 'no blockers'}; "
            f"next={_provider_next_action(provider)}"
        )
    lines.extend(["", "## Probes"])
    for probe in report.get("probes", []):
        lines.append(
            f"- {probe.get('provider_id')}: {probe.get('status')} - {probe.get('message')}"
        )
        lines.extend(_probe_detail_lines(probe))
        for blocker in probe.get("blockers", []):
            lines.append(f"  - blocker: {blocker}")
        for warning in probe.get("warnings", []):
            lines.append(f"  - warning: {warning}")
    lines.extend(
        [
            "",
            "## Not Attempted",
            "- No destructive, rebuild, power, reload, write-memory, virtual-media, "
            "firmware, ESXi VM, datastore, or network configuration action is run by this smoke.",
            "",
        ]
    )
    return "\n".join(lines)


def _provider_next_action(provider: dict[str, Any]) -> str:
    discovery = provider.get("discovery") or {}
    if isinstance(discovery, dict) and discovery.get("safe_next_action"):
        return str(discovery["safe_next_action"])
    configuration = provider.get("configuration") or {}
    if isinstance(configuration, dict) and configuration.get("safe_next_action"):
        return str(configuration["safe_next_action"])
    for action in provider.get("safe_actions", []):
        if action.get("enabled"):
            return str(action.get("reason") or "read-only action enabled")
    blockers = provider.get("blockers") or []
    if blockers:
        return str(blockers[0])
    safe_actions = provider.get("safe_actions") or []
    if safe_actions:
        return str(safe_actions[0].get("reason") or "review read-only action")
    return "status-only"


def _disabled_probe_reason(status: Any) -> str:
    if getattr(status, "safe_actions", None):
        return str(status.safe_actions[0].reason)
    return "No enabled read-only action."


def _disabled_probe_not_attempted(provider_id: str) -> list[str]:
    if provider_id == "esxi-readonly":
        return [
            "HTTPS reachability check",
            "SSH reachability check",
            "ESXi API GET requests",
        ]
    if provider_id == "cisco-ansible":
        return [
            "Cisco SSH reachability check",
            "Ansible inventory parse",
            "safe show commands",
        ]
    return []


def _probe_detail_lines(probe: dict[str, Any]) -> list[str]:
    provider_id = probe.get("provider_id")
    if probe.get("status") == "skipped":
        lines = [f"  - skipped_reason: {probe.get('message', 'not attempted')}"]
        configuration = probe.get("configuration") or {}
        if isinstance(configuration, dict):
            if "management_configured" in configuration:
                lines.append(
                    f"  - management_configured: {configuration.get('management_configured')}"
                )
            if "planned_target" in configuration:
                lines.append(f"  - planned_target: {configuration.get('planned_target')}")
        not_attempted = probe.get("not_attempted") or []
        for item in not_attempted:
            lines.append(f"  - not_attempted: {item}")
        return lines

    if provider_id == "ilo-redfish":
        return [
            f"  - redfish_requests: {len(probe.get('requests', []))}",
            (
                "  - inventory_counts: "
                f"managers={len(probe.get('managers', []))}, "
                f"systems={len(probe.get('systems', []))}, "
                f"chassis={len(probe.get('chassis', []))}, "
                f"firmware={len(probe.get('firmware', []))}"
            ),
        ]
    if provider_id == "cisco-console":
        discovery = probe.get("discovery") or {}
        if not isinstance(discovery, dict):
            discovery = {}
        return [
            f"  - prompt_state: {probe.get('prompt_state', 'not-attempted')}",
            f"  - console_selection: {discovery.get('selection_source', 'unknown')}",
        ]
    if provider_id == "cisco-ansible":
        reachability = probe.get("ssh_reachability") or {}
        tools = probe.get("tool_availability") or {}
        return [
            f"  - ssh_reachable: {reachability.get('reachable', False)}",
            (
                "  - ansible_tools: "
                f"ansible={tools.get('ansible_available', False)}, "
                f"ansible_inventory={tools.get('ansible_inventory_available', False)}"
            ),
        ]
    if provider_id == "esxi-readonly":
        https = probe.get("https_reachability") or {}
        ssh = probe.get("ssh_reachability") or {}
        vim = probe.get("vim_service_versions") or {}
        return [
            f"  - https_reachable: {https.get('reachable', False)}",
            f"  - ssh_reachable: {ssh.get('reachable', False)}",
            f"  - vim_versions_available: {vim.get('available', False)}",
        ]
    return []


def _redaction_values() -> list[str | None]:
    return [
        settings.ilo_test_host,
        settings.ilo_test_username,
        settings.ilo_test_password,
        settings.esxi_test_host,
        settings.esxi_test_username,
        settings.esxi_test_password,
        settings.cisco_target_ip,
        settings.cisco_test_username,
        settings.cisco_test_password,
        settings.cisco_enable_password,
    ]


if __name__ == "__main__":
    raise SystemExit(main())
