from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.redaction import redact_sensitive

REPO_ROOT = Path(__file__).resolve().parents[4]
PROVIDER_MODE_OPTIONS = {
    "mock": {
        "label": "Simulation",
        "status": "safe_default",
        "description": "No real infrastructure contact. This remains the repository default.",
        "restart_command": "PROVIDER_MODE=mock make app-restart",
        "requirements": [],
    },
    "local-readonly": {
        "label": "Local Read-only Lab",
        "status": "read_only",
        "description": "Allows explicit read-only provider probes when local targets and acknowledgements are configured.",
        "restart_command": "PROVIDER_MODE=local-readonly LAB_READONLY_ACK=YES make app-restart",
        "requirements": [
            "Local lab targets are configured outside the repo defaults.",
            "LAB_READONLY_ACK=YES is set when running explicit read-only probes.",
            "No write/apply workflow is enabled by this setting.",
        ],
    },
    "local-lab-readwrite": {
        "label": "Local Lab Read/write",
        "status": "guarded_write",
        "description": "Enables only allowlisted lab write paths that still require workflow-specific flags and confirmations.",
        "restart_command": "PROVIDER_MODE=local-lab-readwrite make app-restart",
        "requirements": [
            "LAB_ENVIRONMENT=isolated-real-lab and required acknowledgement flags are configured locally.",
            "Real credentials stay outside versioned files.",
            "Apply paths remain gated by their own plans, confirmations, and blockers.",
        ],
    },
}


class ProviderModeSettingsError(ValueError):
    pass


def read_provider_mode_settings() -> dict[str, Any]:
    desired_mode = _read_desired_mode()
    current_mode = settings.provider_mode
    selected_mode = desired_mode or current_mode
    option = PROVIDER_MODE_OPTIONS.get(selected_mode, PROVIDER_MODE_OPTIONS["mock"])
    return {
        "current_mode": current_mode,
        "desired_mode": selected_mode,
        "pending_restart": selected_mode != current_mode,
        "options": _mode_options(),
        "restart_command": option["restart_command"],
        "mode_env_path": _path_label(_env_path()),
        "store_path": _path_label(_store_path()),
        "updated_at": _read_store().get("updated_at"),
        "next_safe_action": (
            "Restart the app with the shown command for the desired provider mode to take effect."
            if selected_mode != current_mode
            else "Provider mode is active. Use explicit section actions; page load does not run providers."
        ),
    }


def update_provider_mode_settings(payload: dict[str, Any]) -> dict[str, Any]:
    desired_mode = str(payload.get("desired_mode") or "").strip()
    if desired_mode not in PROVIDER_MODE_OPTIONS:
        raise ProviderModeSettingsError("Unsupported provider mode")
    now = datetime.now(UTC).isoformat()
    store = {
        "desired_mode": desired_mode,
        "updated_at": now,
        "mock_default_preserved": True,
    }
    _write_store(store)
    _write_env_file(desired_mode)
    return read_provider_mode_settings()


def _mode_options() -> list[dict[str, Any]]:
    return [
        {
            "mode": mode,
            "label": data["label"],
            "status": data["status"],
            "description": data["description"],
            "restart_command": data["restart_command"],
            "requirements": list(data["requirements"]),
        }
        for mode, data in PROVIDER_MODE_OPTIONS.items()
    ]


def _read_desired_mode() -> str | None:
    store_mode = _clean_mode(_read_store().get("desired_mode"))
    if store_mode:
        return store_mode
    return _clean_mode(_read_env_mode())


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


def _write_env_file(mode: str) -> None:
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"PROVIDER_MODE={mode}\n", encoding="utf-8")


def _read_env_mode() -> str | None:
    path = _env_path()
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "PROVIDER_MODE":
                return value.strip()
    except OSError:
        return None
    return None


def _clean_mode(value: Any) -> str | None:
    mode = str(value or "").strip()
    return mode if mode in PROVIDER_MODE_OPTIONS else None


def _store_path() -> Path:
    configured = os.getenv("PROVIDER_MODE_SETTINGS_STORE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "provider-mode-settings.json"


def _env_path() -> Path:
    configured = os.getenv("APP_MODE_ENV_FILE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "app-mode.env"


def _path_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
