from __future__ import annotations

import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive

REPO_ROOT = Path(__file__).resolve().parents[4]
STORE_ENV = "CONTROL_CENTER_STATE_STORE"

SECRET_VALUE_RE = re.compile(
    r"(password\s*=|token\s*=|secret\s*=|bearer\s+|-----begin|private[_ -]?key)",
    re.IGNORECASE,
)

IP_MODES = {"ipv4", "ipv6", "both"}
SNMP_VERSIONS = {"v2", "v3"}
LOGGING_VERBOSITY = {"errors", "normal", "debug"}
MAX_LOG_ENTRIES = 80


class ControlCenterStateValidationError(ValueError):
    pass


def read_control_center_config() -> dict[str, Any]:
    store = _read_store()
    config = _normalize_config(store.get("config") if isinstance(store.get("config"), dict) else {})
    return {
        **config,
        "source_type": "operator_config",
        "freshness": "live",
        "store_path": _path_label(_store_path()),
        "credential_storage": "presence_only",
        "warnings": [],
        "blockers": [],
    }


def save_control_center_config(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secret_values(payload)
    store = _read_store()
    config = _normalize_config(payload)
    saved_at = datetime.now(UTC).isoformat()
    config["updated_at"] = saved_at
    store["config"] = config
    store["operator_runtime_only"] = True
    _append_log(
        store,
        detail=_config_log_detail(config),
        message="Config saved",
        status="saved",
        timestamp=saved_at,
        type_="config",
    )
    _write_store(store)
    return read_control_center_config()


def read_control_center_settings() -> dict[str, Any]:
    store = _read_store()
    settings = _normalize_settings(store.get("settings") if isinstance(store.get("settings"), dict) else {})
    return {
        **settings,
        "source_type": "operator_config",
        "freshness": "live",
        "store_path": _path_label(_store_path()),
        "warnings": [],
        "blockers": [],
    }


def save_control_center_settings(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secret_values(payload)
    store = _read_store()
    settings = _normalize_settings(payload)
    saved_at = datetime.now(UTC).isoformat()
    settings["updated_at"] = saved_at
    store["settings"] = settings
    store["operator_runtime_only"] = True
    _append_log(
        store,
        detail=_settings_log_detail(settings),
        message="Settings changed",
        status="saved",
        timestamp=saved_at,
        type_="settings",
    )
    _write_store(store)
    return read_control_center_settings()


def read_control_center_state_logs(*, limit: int = MAX_LOG_ENTRIES) -> list[dict[str, Any]]:
    store = _read_store()
    logs = store.get("logs")
    if not isinstance(logs, list):
        return []
    normalized = [_normalize_log_entry(entry) for entry in logs]
    return [entry for entry in normalized if entry is not None][:limit]


def append_control_center_log(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_secret_values(payload)
    message = _clean_string(payload.get("message"))
    if not message:
        raise ControlCenterStateValidationError("Control Center log message is required.")
    store = _read_store()
    timestamp = datetime.now(UTC).isoformat()
    _append_log(
        store,
        detail=_clean_string(payload.get("detail")) or "",
        message=message,
        status=_clean_string(payload.get("status")) or "recorded",
        timestamp=timestamp,
        type_=_clean_string(payload.get("type")) or "system",
    )
    store["operator_runtime_only"] = True
    _write_store(store)
    logs = read_control_center_state_logs(limit=1)
    if not logs:
        raise ControlCenterStateValidationError("Control Center log could not be recorded.")
    return logs[0]


def _normalize_config(payload: dict[str, Any]) -> dict[str, Any]:
    target = _clean_string(payload.get("target")) or ""
    ip_mode = _enum_value(payload.get("ip_mode"), IP_MODES, "ipv4")
    snmp_version = _enum_value(payload.get("snmp_version"), SNMP_VERSIONS, "v2")
    credential_status = _enum_value(
        payload.get("snmp_credential_status"),
        {"missing", "configured"},
        "missing",
    )
    credential_version = _clean_string(payload.get("snmp_credential_version"))
    if credential_version not in SNMP_VERSIONS or credential_status != "configured":
        credential_version = None
    timeout_seconds = _bounded_int(payload.get("timeout_seconds"), default=8, minimum=1, maximum=120)
    retry_count = _bounded_int(payload.get("retry_count"), default=1, minimum=0, maximum=5)
    updated_at = _clean_string(payload.get("updated_at"))
    return {
        "target": target,
        "ip_mode": ip_mode,
        "snmp_version": snmp_version,
        "snmp_credential_status": credential_status,
        "snmp_credential_version": credential_version,
        "timeout_seconds": timeout_seconds,
        "retry_count": retry_count,
        "updated_at": updated_at,
    }


def _normalize_settings(payload: dict[str, Any]) -> dict[str, Any]:
    firmware_repository = (
        _clean_string(payload.get("firmware_repository"))
        or "Backend firmware repository integration pending"
    )
    return {
        "default_ip_mode": _enum_value(payload.get("default_ip_mode"), IP_MODES, "ipv4"),
        "default_snmp_version": _enum_value(payload.get("default_snmp_version"), SNMP_VERSIONS, "v2"),
        "default_timeout_seconds": _bounded_int(
            payload.get("default_timeout_seconds"),
            default=8,
            minimum=1,
            maximum=120,
        ),
        "default_retry_count": _bounded_int(
            payload.get("default_retry_count"),
            default=1,
            minimum=0,
            maximum=5,
        ),
        "api_base_url": _clean_string(payload.get("api_base_url")) or "same-origin",
        "firmware_repository": firmware_repository,
        "logging_verbosity": _enum_value(payload.get("logging_verbosity"), LOGGING_VERBOSITY, "normal"),
        "updated_at": _clean_string(payload.get("updated_at")),
    }


def _read_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_store(store: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact_sensitive(store), indent=2, sort_keys=True), encoding="utf-8")


def _append_log(
    store: dict[str, Any],
    *,
    detail: str,
    message: str,
    status: str,
    timestamp: str,
    type_: str,
) -> None:
    existing = store.get("logs")
    normalized_existing = (
        [entry for entry in (_normalize_log_entry(item) for item in existing) if entry is not None]
        if isinstance(existing, list)
        else []
    )
    store["logs"] = [
        {
            "id": f"control:{uuid.uuid4().hex[:12]}",
            "timestamp": timestamp,
            "type": _log_type(type_),
            "message": message,
            "status": status,
            "detail": _clean_string(redact_sensitive(detail)) or "",
            "source_type": "operator_config",
            "freshness": "live",
        },
        *normalized_existing,
    ][:MAX_LOG_ENTRIES]


def _normalize_log_entry(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    message = _clean_string(value.get("message"))
    timestamp = _clean_string(value.get("timestamp"))
    if not message or not timestamp:
        return None
    return {
        "id": _clean_string(value.get("id")) or f"control:{uuid.uuid4().hex[:12]}",
        "timestamp": timestamp,
        "type": _log_type(_clean_string(value.get("type")) or "system"),
        "message": message,
        "status": _clean_string(value.get("status")),
        "detail": _clean_string(redact_sensitive(value.get("detail"))),
        "source_type": _clean_string(value.get("source_type")) or "operator_config",
        "freshness": _clean_string(value.get("freshness")) or "historical",
    }


def _store_path() -> Path:
    configured = os.getenv(STORE_ENV)
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "control-center-state.json"


def _path_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _config_log_detail(config: dict[str, Any]) -> str:
    return (
        f"Target {_clean_string(config.get('target')) or 'not configured'}; "
        f"{config['ip_mode']}; {config['snmp_version']}; "
        f"SNMP credentials {config['snmp_credential_status']}; "
        f"timeout {config['timeout_seconds']}s; retry {config['retry_count']}."
    )


def _settings_log_detail(settings: dict[str, Any]) -> str:
    return (
        f"Defaults {settings['default_ip_mode']}; {settings['default_snmp_version']}; "
        f"timeout {settings['default_timeout_seconds']}s; retry {settings['default_retry_count']}; "
        f"logging {settings['logging_verbosity']}; firmware source updated."
    )


def _log_type(value: str) -> str:
    return value if value in {"system", "config", "run", "firmware", "settings"} else "system"


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_value(value: Any, allowed: set[str], default: str) -> str:
    text = _clean_string(value)
    if not text:
        return default
    normalized = text.lower()
    return normalized if normalized in allowed else default


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, number))


def _reject_secret_values(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _reject_secret_values(item)
        return
    if isinstance(value, list):
        for item in value:
            _reject_secret_values(item)
        return
    if value is None:
        return
    if SECRET_VALUE_RE.search(str(value)):
        raise ControlCenterStateValidationError("Control Center state must not contain secrets.")
