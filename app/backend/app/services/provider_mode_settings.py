from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.redaction import redact_sensitive
from app.services.env_utils import read_env_file_values
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[4]
PROVIDER_MODE_OPTIONS = {
    "local-readonly": {
        "label": "Read-only Live Checks",
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
        "label": "Real Lab Runtime",
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
    selected_mode = desired_mode or (
        current_mode if current_mode in PROVIDER_MODE_OPTIONS else "local-lab-readwrite"
    )
    option = PROVIDER_MODE_OPTIONS.get(selected_mode, PROVIDER_MODE_OPTIONS["local-lab-readwrite"])
    dev_test_banner = (
        "The app is currently served with PROVIDER_MODE=mock. This is test mode only and cannot certify real lab results."
        if current_mode == "mock"
        else None
    )
    return {
        "current_mode": current_mode,
        "desired_mode": selected_mode,
        "pending_restart": selected_mode != current_mode,
        "options": _mode_options(),
        "restart_command": option["restart_command"],
        "expected_runtime_mode": "local-lab-readwrite",
        "dev_test_banner": dev_test_banner,
        "mode_env_path": _path_label(_env_path()),
        "store_path": _path_label(_store_path()),
        "updated_at": _read_store().get("updated_at"),
        "next_safe_action": (
            "Restart in Real Lab Runtime before relying on operator status, reports, or certification."
            if dev_test_banner
            else
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
        "operator_runtime_only": True,
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
    return read_json_object(_store_path())


def _write_store(store: dict[str, Any]) -> None:
    write_json_object(_store_path(), redact_sensitive(store))


def _write_env_file(mode: str) -> None:
    path = _env_path()
    write_text_value(path, f"PROVIDER_MODE={mode}\n")


def _read_env_mode() -> str | None:
    path = _env_path()
    try:
        return read_env_file_values(path).get("PROVIDER_MODE")
    except OSError:
        return None


def _clean_mode(value: Any) -> str | None:
    mode = str(value or "").strip().strip("\"'")
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
    return display_path(path, REPO_ROOT)
