from __future__ import annotations

import json
import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"
REPORT_DIR = REPO_ROOT / "artifacts" / "real-lab"
CONNECT_TIMEOUT_SECONDS = 3.0
HTTP_TIMEOUT_SECONDS = 5.0

if REAL_LAB_ENV.exists():
    for key, value in dotenv_values(REAL_LAB_ENV).items():
        if key == "PROVIDER_MODE" or value is None or key in os.environ:
            continue
        os.environ[key] = value

# Load local lab env before app imports; settings reads env at import time.
from app.core.config import settings  # noqa: E402
from app.providers.action_policy import LOCAL_LAB_MODE, current_lab_action_policy  # noqa: E402
from app.providers.ilo_redfish import (  # noqa: E402
    IloRedfishConfig,
    _base_url,
    ilo_redfish_redaction_values,
)
from app.providers.redaction import redact_sensitive  # noqa: E402


def main() -> int:
    config = IloRedfishConfig.from_settings()
    policy = current_lab_action_policy(settings.provider_mode)
    report: dict[str, Any] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_mode": settings.provider_mode,
        "env_file": {
            "path": ".env.local.real-lab",
            "exists": REAL_LAB_ENV.exists(),
            "mode": _file_mode(REAL_LAB_ENV),
        },
        "target": {
            "host_configured": bool(config.target_candidates),
            "host_source": config.host_source,
            "fallback_hosts_configured": len(config.fallback_hosts),
            "target_candidate_count": len(config.target_candidates),
            "target_candidate_sources": [
                candidate["source"] for candidate in config.target_candidates
            ],
            "username_configured": bool(config.username),
            "password_configured": bool(config.password),
            "tls_verify": config.verify_tls,
            "timeout_seconds": config.timeout_seconds,
            "redacted": True,
        },
        "policy": policy.status_summary(),
        "blockers": [],
        "warnings": [],
        "diagnostics": {},
        "classification": "not_checked",
        "next_action": "not_checked",
    }

    blockers = _gate_blockers(config, policy)
    if blockers:
        report.update(
            {
                "classification": "blocked_by_configuration",
                "blockers": blockers,
                "next_action": "Fix local-lab-readwrite acknowledgement or iLO target configuration.",
            }
        )
        _finish(report)
        return 0

    candidate_attempts: list[dict[str, Any]] = []
    selected_result: dict[str, Any] | None = None
    for index, candidate in enumerate(config.target_candidates, start=1):
        result = _candidate_reachability(config, candidate, index)
        candidate_attempts.append(_candidate_reachability_summary(result))
        selected_result = result
        if not _try_next_reachability_candidate(str(result["classification"])):
            break

    if selected_result is None:
        report.update(
            {
                "classification": "blocked_by_configuration",
                "blockers": ["Missing local iLO target configuration."],
                "next_action": "Configure an iLO target in the active lab profile or local first-access record.",
            }
        )
        _finish(report)
        return 0

    report.update(
        {
            "selected_target_source": selected_result.get("target_source"),
            "candidate_attempts": candidate_attempts,
            "diagnostics": selected_result["diagnostics"],
            "classification": selected_result["classification"],
            "next_action": selected_result["next_action"],
            "blockers": selected_result["blockers"],
        }
    )
    _finish(report)
    return 0


def _candidate_reachability(
    config: IloRedfishConfig,
    candidate: dict[str, str],
    candidate_index: int,
) -> dict[str, Any]:
    host_value = candidate["host"]
    base_url = _base_url(host_value)
    parsed = urlparse(base_url)
    host = parsed.hostname or host_value
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    dns_result = _dns_check(host)
    tcp_result = _tcp_check(host, port)
    http_result = _http_check(base_url, config.verify_tls) if tcp_result["reachable"] else _http_skipped(tcp_result)
    classification = _classify(dns_result, tcp_result, http_result)
    return {
        "candidate_index": candidate_index,
        "target_source": candidate.get("source", "unknown"),
        "diagnostics": {
            "dns": dns_result,
            "tcp": tcp_result,
            "http": http_result,
        },
        "classification": classification,
        "next_action": _next_action(classification),
        "blockers": _blockers(classification),
    }


def _gate_blockers(config: IloRedfishConfig, policy: Any) -> list[str]:
    blockers: list[str] = []
    if settings.provider_mode != LOCAL_LAB_MODE:
        blockers.append("PROVIDER_MODE=local-lab-readwrite is required for real iLO reachability.")
    blockers.extend(policy.readonly_blockers())
    if config.missing_fields:
        blockers.append(f"Missing local iLO configuration: {', '.join(config.missing_fields)}.")
    return list(dict.fromkeys(blockers))


def _candidate_reachability_summary(result: dict[str, Any]) -> dict[str, Any]:
    diagnostics = result.get("diagnostics") if isinstance(result.get("diagnostics"), dict) else {}
    tcp = diagnostics.get("tcp") if isinstance(diagnostics.get("tcp"), dict) else {}
    http = diagnostics.get("http") if isinstance(diagnostics.get("http"), dict) else {}
    return {
        "candidate_index": result.get("candidate_index"),
        "target_source": result.get("target_source"),
        "classification": result.get("classification"),
        "tcp_reachable": tcp.get("reachable", False),
        "tcp_failure_kind": tcp.get("failure_kind"),
        "http_status": http.get("status", "not_checked"),
        "http_failure_kind": http.get("failure_kind"),
    }


def _try_next_reachability_candidate(classification: str) -> bool:
    return classification in {
        "dns_resolution_failed",
        "execution_environment_socket_permission_denied",
        "tcp_timeout_or_filtered",
        "tcp_connection_refused",
        "network_route_unreachable",
        "tcp_connect_failed",
        "https_or_redfish_connect_failed",
        "https_reachable_redfish_unconfirmed",
    }


def _dns_check(host: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {
            "status": "failed",
            "error_class": exc.__class__.__name__,
            "elapsed_ms": _elapsed_ms(started),
            "addresses_found": 0,
        }
    return {
        "status": "ok",
        "elapsed_ms": _elapsed_ms(started),
        "addresses_found": len(results),
    }


def _tcp_check(host: str, port: int) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, 4):
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_SECONDS):
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "ok",
                        "elapsed_ms": _elapsed_ms(started),
                    }
                )
                return {
                    "status": "ok",
                    "reachable": True,
                    "port": port,
                    "attempts": attempts,
                }
        except PermissionError as exc:
            attempts.append(_tcp_error_attempt(attempt, started, exc))
            return {
                "status": "failed",
                "reachable": False,
                "port": port,
                "failure_kind": "socket_permission_denied",
                "attempts": attempts,
            }
        except socket.timeout as exc:
            attempts.append(_tcp_error_attempt(attempt, started, exc, failure_kind="timeout"))
        except OSError as exc:
            attempts.append(_tcp_error_attempt(attempt, started, exc))
    return {
        "status": "failed",
        "reachable": False,
        "port": port,
        "failure_kind": _tcp_failure_kind(attempts),
        "attempts": attempts,
    }


def _tcp_error_attempt(
    attempt: int,
    started: float,
    exc: OSError,
    *,
    failure_kind: str | None = None,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "status": "failed",
        "error_class": exc.__class__.__name__,
        "failure_kind": failure_kind or _os_error_kind(exc),
        "elapsed_ms": _elapsed_ms(started),
    }


def _tcp_failure_kind(attempts: list[dict[str, Any]]) -> str:
    kinds = {attempt.get("failure_kind") for attempt in attempts}
    if "socket_permission_denied" in kinds:
        return "socket_permission_denied"
    if "timeout" in kinds:
        return "timeout"
    if "connection_refused" in kinds:
        return "connection_refused"
    if "network_unreachable" in kinds:
        return "network_unreachable"
    return "connect_error"


def _os_error_kind(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "socket_permission_denied"
    if isinstance(exc, ConnectionRefusedError):
        return "connection_refused"
    if getattr(exc, "errno", None) in {101, 113}:
        return "network_unreachable"
    return "connect_error"


def _http_check(base_url: str, verify_tls: bool) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/redfish/v1/"
    started = time.monotonic()
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
            trust_env=False,
            verify=verify_tls,
        ) as client:
            response = client.get(url)
    except httpx.ConnectError as exc:
        return _http_error(started, exc, "connect_error")
    except httpx.ConnectTimeout as exc:
        return _http_error(started, exc, "timeout")
    except httpx.TimeoutException as exc:
        return _http_error(started, exc, "timeout")
    except httpx.HTTPError as exc:
        text = str(exc).lower()
        failure_kind = "tls_error" if any(token in text for token in ("certificate", "tls", "ssl")) else "http_error"
        return _http_error(started, exc, failure_kind)

    return {
        "status": "ok",
        "elapsed_ms": _elapsed_ms(started),
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "-"),
        "redfish_root_available": response.status_code == 200,
        "auth_required": response.status_code in {401, 403},
    }


def _http_error(started: float, exc: httpx.HTTPError, failure_kind: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "failure_kind": failure_kind,
        "error_class": exc.__class__.__name__,
        "elapsed_ms": _elapsed_ms(started),
    }


def _http_skipped(tcp_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "skipped",
        "reason": "TCP reachability failed before HTTPS/Redfish check.",
        "tcp_failure_kind": tcp_result.get("failure_kind"),
    }


def _classify(
    dns_result: dict[str, Any],
    tcp_result: dict[str, Any],
    http_result: dict[str, Any],
) -> str:
    if dns_result["status"] != "ok":
        return "dns_resolution_failed"
    if not tcp_result["reachable"]:
        failure_kind = tcp_result.get("failure_kind")
        if failure_kind == "socket_permission_denied":
            return "execution_environment_socket_permission_denied"
        if failure_kind == "timeout":
            return "tcp_timeout_or_filtered"
        if failure_kind == "connection_refused":
            return "tcp_connection_refused"
        if failure_kind == "network_unreachable":
            return "network_route_unreachable"
        return "tcp_connect_failed"
    if http_result["status"] != "ok":
        if http_result.get("failure_kind") == "tls_error":
            return "tls_or_certificate_failed"
        return "https_or_redfish_connect_failed"
    if http_result.get("redfish_root_available"):
        return "redfish_root_available"
    if http_result.get("auth_required"):
        return "redfish_auth_required_or_credentials_needed"
    return "https_reachable_redfish_unconfirmed"


def _blockers(classification: str) -> list[str]:
    blocker_map = {
        "dns_resolution_failed": "Configured iLO host could not be resolved.",
        "execution_environment_socket_permission_denied": (
            "The execution environment denied outbound socket connection attempts."
        ),
        "tcp_timeout_or_filtered": "TCP 443 timed out or is filtered before HTTPS.",
        "tcp_connection_refused": "TCP 443 was refused by the configured target.",
        "network_route_unreachable": "No network route to the configured iLO target.",
        "tcp_connect_failed": "TCP 443 connection failed.",
        "tls_or_certificate_failed": "HTTPS reached the target but TLS/certificate validation failed.",
        "https_or_redfish_connect_failed": "TCP succeeded but HTTPS/Redfish connection failed.",
    }
    blocker = blocker_map.get(classification)
    return [blocker] if blocker else []


def _next_action(classification: str) -> str:
    actions = {
        "dns_resolution_failed": "Fix the configured iLO host value or local name resolution.",
        "execution_environment_socket_permission_denied": (
            "Run the reachability check from a shell/session allowed to open outbound lab network sockets."
        ),
        "tcp_timeout_or_filtered": "Check VLAN/routing/firewall and confirm iLO is powered and cabled.",
        "tcp_connection_refused": "Confirm HTTPS is enabled on iLO and the target is the management controller.",
        "network_route_unreachable": "Fix route/VLAN path from this host to the iLO management network.",
        "tcp_connect_failed": "Check network path, target address, and target power/network state.",
        "tls_or_certificate_failed": "Set ILO_TEST_VERIFY_TLS=false for lab/self-signed iLO or install trusted CA.",
        "https_or_redfish_connect_failed": "Inspect HTTPS service state and retry Redfish root detection.",
        "redfish_root_available": "Proceed to iLO authentication and inventory.",
        "redfish_auth_required_or_credentials_needed": "Proceed to authenticated iLO Redfish inventory.",
        "https_reachable_redfish_unconfirmed": "Review HTTP status/content and verify Redfish support.",
    }
    return actions.get(classification, "Review sanitized diagnostics and retry.")


def _finish(report: dict[str, Any]) -> None:
    sanitized = redact_sensitive(report, _redaction_values())
    print(json.dumps(sanitized, indent=2))
    _write_report(sanitized)


def _write_report(report: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"ilo-reachability-{stamp}.json"
    markdown_path = REPORT_DIR / f"ilo-reachability-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(report), encoding="utf-8")
    print(f"report_json={json_path.relative_to(REPO_ROOT)}")
    print(f"report_markdown={markdown_path.relative_to(REPO_ROOT)}")


def _markdown_report(report: dict[str, Any]) -> str:
    diagnostics = report.get("diagnostics") or {}
    tcp = diagnostics.get("tcp") or {}
    http = diagnostics.get("http") or {}
    lines = [
        "# iLO Real Reachability",
        "",
        f"Checked at: {report.get('checked_at', 'unknown')}",
        f"Provider mode: {report.get('provider_mode', 'unknown')}",
        f"Classification: {report.get('classification', 'unknown')}",
        f"Next action: {report.get('next_action', 'unknown')}",
        "",
        "## Target",
        f"- host_configured: {(report.get('target') or {}).get('host_configured', False)}",
        f"- host_source: {(report.get('target') or {}).get('host_source', 'unknown')}",
        f"- fallback_hosts_configured: {(report.get('target') or {}).get('fallback_hosts_configured', 0)}",
        f"- target_candidate_count: {(report.get('target') or {}).get('target_candidate_count', 0)}",
        f"- selected_target_source: {report.get('selected_target_source', 'none')}",
        f"- username_configured: {(report.get('target') or {}).get('username_configured', False)}",
        f"- password_configured: {(report.get('target') or {}).get('password_configured', False)}",
        f"- tls_verify: {(report.get('target') or {}).get('tls_verify', 'unknown')}",
        "",
        "## Diagnostics",
        f"- dns_status: {(diagnostics.get('dns') or {}).get('status', 'not_checked')}",
        f"- tcp_status: {tcp.get('status', 'not_checked')}",
        f"- tcp_reachable: {tcp.get('reachable', False)}",
        f"- tcp_failure_kind: {tcp.get('failure_kind', 'none')}",
        f"- http_status: {http.get('status', 'not_checked')}",
        f"- http_failure_kind: {http.get('failure_kind', 'none')}",
    ]
    for candidate in report.get("candidate_attempts", []):
        lines.append(
            "- candidate: "
            f"index={candidate.get('candidate_index')}, "
            f"source={candidate.get('target_source')}, "
            f"classification={candidate.get('classification')}, "
            f"tcp_reachable={candidate.get('tcp_reachable', False)}"
        )
    for blocker in report.get("blockers", []):
        lines.append(f"- blocker: {blocker}")
    lines.append("")
    return "\n".join(lines)


def _file_mode(path: Path) -> str | None:
    if not path.exists():
        return None
    return oct(path.stat().st_mode & 0o777)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _redaction_values() -> list[str | None]:
    config = IloRedfishConfig.from_settings()
    values = ilo_redfish_redaction_values(config)
    if config.host:
        base_url = _base_url(config.host)
        parsed = urlparse(base_url)
        values.extend([base_url, parsed.netloc, parsed.hostname])
    return values


if __name__ == "__main__":
    raise SystemExit(main())
