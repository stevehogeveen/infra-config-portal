from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.ilo_redfish import IloRedfishConfig, ilo_target_fingerprint
from app.providers.probe_cache import get_probe_result
from app.services.env_utils import bool_value
from app.services.json_file_store import write_text_value
from app.services.path_utils import display_path, path_exists
from app.services.status_source import status_source_metadata

REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_KEYS = {
    "host": "ILO_TEST_HOST",
    "username": "ILO_TEST_USERNAME",
    "password": "ILO_TEST_PASSWORD",
    "verify_tls": "ILO_TEST_VERIFY_TLS",
}


class IloAccessSettingsError(ValueError):
    pass


def read_ilo_access_settings() -> dict[str, Any]:
    config = IloRedfishConfig.from_settings()
    host, host_source = _access_host(config)
    fallback_hosts = _fallback_hosts_for_access(config, host)
    return {
        "provider_id": "ilo-redfish",
        "host": host,
        "host_source": host_source,
        "fallback_hosts": fallback_hosts,
        "username": config.username,
        "username_configured": bool(config.username),
        "password_configured": bool(config.password),
        "verify_tls": bool(config.verify_tls),
        "env_path": display_path(_env_path(), REPO_ROOT),
        "updated_at": None,
        **_last_probe_summary(host, config),
        "next_safe_action": _next_safe_action(config),
    }


def update_ilo_access_settings(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, str] = {}
    if "host" in payload:
        host = _clean_optional(payload.get("host"))
        if host:
            updates[ENV_KEYS["host"]] = host
    if "username" in payload:
        username = _clean_optional(payload.get("username"))
        if username:
            updates[ENV_KEYS["username"]] = username
    if "password" in payload:
        password = _clean_optional(payload.get("password"))
        if password:
            updates[ENV_KEYS["password"]] = password
    if "verify_tls" in payload and payload.get("verify_tls") is not None:
        updates[ENV_KEYS["verify_tls"]] = "true" if bool_value(payload.get("verify_tls"), default=True) else "false"

    if not updates:
        raise IloAccessSettingsError("No iLO access settings were provided.")

    _write_env_updates(updates)
    _apply_runtime_updates(updates)
    readback = read_ilo_access_settings()
    return {
        **readback,
        "updated_at": datetime.now(UTC).isoformat(),
        "next_safe_action": "iLO access settings saved locally. Run iLO Inventory Read to prove reachability before trusting the map.",
    }


def _next_safe_action(config: IloRedfishConfig) -> str:
    if config.configured:
        return "Run iLO Inventory Read to refresh live iLO reachability and storage inventory."
    if not config.target_candidates:
        return "Enter the iLO IP or initial iLO IP, then save credentials locally."
    if not config.username or not config.password:
        return "Enter the iLO username/UID and password, then save credentials locally."
    return "Review iLO access settings, then run iLO Inventory Read."


def _access_host(config: IloRedfishConfig) -> tuple[str | None, str]:
    runtime_host = _clean_optional(os.getenv(ENV_KEYS["host"]) or settings.ilo_test_host)
    if runtime_host:
        return runtime_host, "runtime_env"
    return config.host, config.host_source


def _fallback_hosts_for_access(config: IloRedfishConfig, host: str | None) -> list[str]:
    seen = {host.casefold()} if host else set()
    fallbacks: list[str] = []
    for candidate in config.target_candidates:
        candidate_host = _clean_optional(candidate.get("host"))
        if not candidate_host or candidate_host.casefold() in seen:
            continue
        seen.add(candidate_host.casefold())
        fallbacks.append(candidate_host)
    return fallbacks


def _last_probe_summary(host: str | None, config: IloRedfishConfig) -> dict[str, Any]:
    result, checked_at = get_probe_result("ilo-redfish")
    if not isinstance(result, dict):
        return {
            "last_probe_status": "not_checked",
            "last_probe_time": None,
            "last_probe_freshness": "not_checked",
            "last_probe_is_current": False,
            "last_probe_message": None,
            "last_probe_target_source": None,
            "last_probe_target_matches_access_host": False,
            "last_probe_target_matches_configured_candidates": False,
            "last_probe_target_fingerprint_present": False,
        }
    source_metadata = status_source_metadata(
        source_type="live_cached",
        checked_at=checked_at,
    )
    target_fingerprint = _clean_optional(result.get("target_fingerprint"))
    candidate_fingerprints = {
        fingerprint
        for candidate in config.target_candidates
        if (fingerprint := ilo_target_fingerprint(candidate.get("host")))
    }
    return {
        "last_probe_status": _clean_optional(result.get("status")) or "unknown",
        "last_probe_time": checked_at,
        "last_probe_freshness": source_metadata["freshness"],
        "last_probe_is_current": bool(source_metadata["is_current"]),
        "last_probe_message": _clean_optional(result.get("message")),
        "last_probe_target_source": _clean_optional(result.get("target_source")),
        "last_probe_target_matches_access_host": bool(
            target_fingerprint
            and host
            and target_fingerprint == ilo_target_fingerprint(host)
        ),
        "last_probe_target_matches_configured_candidates": bool(
            target_fingerprint and target_fingerprint in candidate_fingerprints
        ),
        "last_probe_target_fingerprint_present": bool(target_fingerprint),
    }


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _write_env_updates(updates: dict[str, str]) -> None:
    path = _env_path()
    existing_lines: list[str] = []
    if path_exists(path):
        try:
            existing_lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise IloAccessSettingsError(f"Could not read {display_path(path, REPO_ROOT)}.") from exc

    seen: set[str] = set()
    next_lines: list[str] = []
    for line in existing_lines:
        key = _line_key(line)
        if key in updates:
            next_lines.append(f"{key}={_quote_env_value(updates[key])}")
            seen.add(key)
        else:
            next_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            next_lines.append(f"{key}={_quote_env_value(value)}")

    try:
        write_text_value(path, "\n".join(next_lines).rstrip() + "\n")
    except OSError as exc:
        raise IloAccessSettingsError(f"Could not write {display_path(path, REPO_ROOT)}.") from exc


def _line_key(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key = stripped.split("=", 1)[0].strip()
    return key if key in ENV_KEYS.values() else None


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "").replace("\n", "\\n")
    return f'"{escaped}"'


def _apply_runtime_updates(updates: dict[str, str]) -> None:
    for key, value in updates.items():
        os.environ[key] = value
    if ENV_KEYS["host"] in updates:
        object.__setattr__(settings, "ilo_test_host", updates[ENV_KEYS["host"]])
    if ENV_KEYS["username"] in updates:
        object.__setattr__(settings, "ilo_test_username", updates[ENV_KEYS["username"]])
    if ENV_KEYS["password"] in updates:
        object.__setattr__(settings, "ilo_test_password", updates[ENV_KEYS["password"]])
    if ENV_KEYS["verify_tls"] in updates:
        object.__setattr__(settings, "ilo_test_verify_tls", bool_value(updates[ENV_KEYS["verify_tls"]], default=True))


def _env_path() -> Path:
    configured = os.getenv("ILO_ACCESS_ENV_FILE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".env.local.real-lab"
