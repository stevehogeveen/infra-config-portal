from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.env_utils import bool_value
from app.services.json_file_store import read_json_object, write_json_object
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[4]
LOCAL_LAB_ENVIRONMENT = "isolated-real-lab"
CONFIRMATION_PHRASE = "ACKNOWLEDGE REAL LAB RISK"
DEVICE_RECONFIGURATION_CONFIRMATION_PHRASE = "ACKNOWLEDGE DEVICE RECONFIGURATION"

SAFETY_FLAGS = [
    {
        "name": "lab_environment",
        "label": "Isolated real lab",
        "description": "Confirms this runtime is pointed at an isolated lab, not production.",
        "required": True,
    },
    {
        "name": "lab_acknowledge_real_hardware",
        "label": "Real hardware acknowledgement",
        "description": "Allows read-only probes to contact configured lab hardware.",
        "required": True,
    },
    {
        "name": "lab_acknowledge_device_reconfiguration",
        "label": "Device reconfiguration acknowledgement",
        "description": "Acknowledges guarded workflows may change lab device configuration.",
        "required": True,
    },
    {
        "name": "lab_acknowledge_data_loss_risk",
        "label": "Data loss risk acknowledgement",
        "description": "Acknowledges rebuild/reset workflows can destroy existing lab data.",
        "required": True,
    },
    {
        "name": "lab_acknowledge_lab_only",
        "label": "Lab-only acknowledgement",
        "description": "Confirms these permissions apply only to this local lab environment.",
        "required": True,
    },
]

BOOLEAN_FLAGS = {item["name"] for item in SAFETY_FLAGS if item["name"] != "lab_environment"}


class LabSafetySettingsError(ValueError):
    pass


def read_lab_safety_settings() -> dict[str, Any]:
    store = _read_store()
    runtime = _runtime_values(store)
    flags = [_flag_read(item, runtime, store) for item in SAFETY_FLAGS]
    missing = [item for item in flags if item["required"] and item["status"] != "enabled"]
    return {
        "flags": flags,
        "store_path": _path_label(_store_path()),
        "updated_at": store.get("updated_at"),
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "device_reconfiguration_confirmation_phrase": DEVICE_RECONFIGURATION_CONFIRMATION_PHRASE,
        "next_safe_action": (
            "Complete real lab prerequisites before relying on live provider probes."
            if missing
            else "Real lab prerequisites are satisfied for read-only probes."
        ),
    }


def update_lab_safety_settings(payload: dict[str, Any]) -> dict[str, Any]:
    requested = {key: payload[key] for key in ["lab_environment", *sorted(BOOLEAN_FLAGS)] if key in payload}
    if not requested:
      raise LabSafetySettingsError("No lab safety settings were provided.")
    if requested.get("lab_environment") not in {None, LOCAL_LAB_ENVIRONMENT}:
        raise LabSafetySettingsError("Unsupported lab environment.")
    if bool_value(requested.get("lab_acknowledge_device_reconfiguration")):
        phrase = str(payload.get("device_reconfiguration_confirmation_phrase") or "").strip()
        if phrase != DEVICE_RECONFIGURATION_CONFIRMATION_PHRASE:
            raise LabSafetySettingsError("Device reconfiguration acknowledgement requires the confirmation phrase.")
    if bool_value(requested.get("lab_acknowledge_data_loss_risk")):
        phrase = str(payload.get("confirmation_phrase") or "").strip()
        if phrase != CONFIRMATION_PHRASE:
            raise LabSafetySettingsError("Data loss acknowledgement requires the confirmation phrase.")

    store = _read_store()
    next_store = {key: value for key, value in store.items() if key in {"updated_at", *[item["name"] for item in SAFETY_FLAGS]}}
    for key, value in requested.items():
        next_store[key] = _clean_value(key, value)
    next_store["updated_at"] = datetime.now(UTC).isoformat()
    _write_store(next_store)
    return read_lab_safety_settings()


def read_lab_safety_overrides() -> dict[str, Any]:
    return _runtime_values(_read_store())


def _flag_read(definition: dict[str, Any], runtime: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    name = str(definition["name"])
    value = runtime.get(name)
    enabled = value == LOCAL_LAB_ENVIRONMENT if name == "lab_environment" else bool_value(value)
    return {
        "name": name,
        "label": definition["label"],
        "description": definition["description"],
        "required": bool(definition["required"]),
        "value": value,
        "enabled": enabled,
        "source": "runtime" if name in store else "environment",
        "status": "enabled" if enabled else "missing",
    }


def _runtime_values(store: dict[str, Any]) -> dict[str, Any]:
    return {
        "lab_environment": _clean_value("lab_environment", store.get("lab_environment", settings.lab_environment)),
        "lab_acknowledge_real_hardware": _clean_value(
            "lab_acknowledge_real_hardware",
            store.get("lab_acknowledge_real_hardware", settings.lab_acknowledge_real_hardware),
        ),
        "lab_acknowledge_device_reconfiguration": _clean_value(
            "lab_acknowledge_device_reconfiguration",
            store.get("lab_acknowledge_device_reconfiguration", settings.lab_acknowledge_device_reconfiguration),
        ),
        "lab_acknowledge_data_loss_risk": _clean_value(
            "lab_acknowledge_data_loss_risk",
            store.get("lab_acknowledge_data_loss_risk", settings.lab_acknowledge_data_loss_risk),
        ),
        "lab_acknowledge_lab_only": _clean_value(
            "lab_acknowledge_lab_only",
            store.get("lab_acknowledge_lab_only", settings.lab_acknowledge_lab_only),
        ),
    }


def _clean_value(key: str, value: Any) -> Any:
    if key == "lab_environment":
        return str(value or "").strip() or None
    return bool_value(value)


def _read_store() -> dict[str, Any]:
    return read_json_object(_store_path())


def _write_store(store: dict[str, Any]) -> None:
    write_json_object(_store_path(), store)


def _store_path() -> Path:
    configured = os.getenv("LAB_SAFETY_SETTINGS_STORE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "lab-safety-settings.json"


def _path_label(path: Path) -> str:
    return display_path(path, REPO_ROOT)
