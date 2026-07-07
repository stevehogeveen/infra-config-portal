from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.json_file_store import read_json_object, write_json_object
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[4]
STORE_ENV = "FIRMWARE_FILE_SELECTION_STORE"


def read_firmware_file_selections() -> dict[str, Any]:
    store = _read_store()
    selections = _selected_files(store.get("selected_files"))
    updated_at = _clean_string(store.get("updated_at"))
    return {
        "provider_id": "firmware-file-selections",
        "status": "ready" if selections else "not_configured_yet",
        "message": (
            "Firmware file selections are saved in local runtime state."
            if selections
            else "No firmware file selections are saved yet."
        ),
        "source_type": "operator_config",
        "freshness": "live",
        "checked_at": updated_at,
        "updated_at": updated_at,
        "store_path": _path_label(_store_path()),
        "selected_files": selections,
        "apply_enabled": False,
        "blockers": [],
        "warnings": [],
        "next_safe_action": "Validate the upgrade path before any firmware apply workflow.",
    }


def save_firmware_file_selections(payload: dict[str, Any]) -> dict[str, Any]:
    store = {
        "selected_files": _selected_files(payload.get("selected_files")),
        "updated_at": datetime.now(UTC).isoformat(),
        "operator_runtime_only": True,
    }
    _write_store(store)
    return read_firmware_file_selections()


def _read_store() -> dict[str, Any]:
    return read_json_object(_store_path())


def _write_store(store: dict[str, Any]) -> None:
    write_json_object(_store_path(), redact_sensitive(store))


def _selected_files(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    selections: dict[str, str] = {}
    for component_id, file_name in value.items():
        component = _clean_string(component_id)
        if not component:
            continue
        selections[component] = _clean_string(file_name) or ""
    return dict(sorted(selections.items()))


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _store_path() -> Path:
    configured = os.getenv(STORE_ENV)
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "firmware-file-selections.json"


def _path_label(path: Path) -> str:
    return display_path(path, REPO_ROOT)
