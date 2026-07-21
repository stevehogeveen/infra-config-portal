from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.ilo_redfish import IloRedfishConfig
from app.services.env_utils import bool_value
from app.services.json_file_store import write_text_value
from app.services.path_utils import display_path, path_exists

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
    return {
        "provider_id": "ilo-redfish",
        "host": config.host,
        "host_source": config.host_source,
        "fallback_hosts": list(config.fallback_hosts),
        "username": config.username,
        "username_configured": bool(config.username),
        "password_configured": bool(config.password),
        "verify_tls": bool(config.verify_tls),
        "env_path": display_path(_env_path(), REPO_ROOT),
        "updated_at": None,
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
