from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import (
    LAB_ANSIBLE_CONTROL_HOST_IP,
    LAB_CISCO_MANAGEMENT_IP,
    LAB_ESXI_MANAGEMENT_IP,
    LAB_ILO_IP,
    LAB_NETAPP_CLUSTER_MGMT_IP,
    LAB_NETAPP_CONTROLLER_A_SP_IP,
    LAB_NETAPP_CONTROLLER_B_SP_IP,
    LAB_NETAPP_ISCSI_LIF_IPS,
    LAB_NETAPP_NODE_A_MGMT_IP,
    LAB_NETAPP_NODE_B_MGMT_IP,
    LAB_NETAPP_SVM_MGMT_IP,
    LAB_SERVER_EMBEDDED_NIC_IP,
    LAB_SUBNET_CIDR,
    settings,
)
from app.providers.redaction import redact_sensitive

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNTIME_PROFILE_ID = "runtime"


class LabProfileError(Exception):
    pass


class LabProfileNotFoundError(LabProfileError):
    pass


def list_lab_profiles() -> dict[str, Any]:
    store = _read_store()
    profiles = _profiles_with_active_flag(store)
    active_profile = _active_profile(store, profiles)
    return {
        "active_profile": active_profile,
        "runtime_profile": _runtime_profile(active=active_profile["id"] == RUNTIME_PROFILE_ID),
        "profiles": profiles,
        "store_path": _store_path_label(),
        "mock_only": True,
        "next_safe_action": (
            "Select a saved lab or create a new profile before running lab-specific planning."
        ),
    }


def create_lab_profile(payload: dict[str, Any]) -> dict[str, Any]:
    store = _read_store()
    now = _now()
    profile = {
        "id": f"lab-{uuid4().hex[:12]}",
        "name": payload["name"],
        "description": payload.get("description") or "",
        "address_plan": _normalize_address_plan(payload.get("address_plan") or {}),
        "source": "saved",
        "version": 1,
        "created_at": now,
        "updated_at": now,
        "last_selected_at": now,
        "history": [],
    }
    store["profiles"].append(profile)
    store["active_profile_id"] = profile["id"]
    _write_store(store)
    return _profile_read(profile, active=True)


def update_lab_profile(profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    store = _read_store()
    profile = _find_profile(store, profile_id)
    now = _now()
    profile.setdefault("history", []).append(
        {
            "version": profile.get("version", 1),
            "saved_at": profile.get("updated_at") or now,
            "name": profile.get("name", ""),
            "description": profile.get("description", ""),
            "address_plan": deepcopy(profile.get("address_plan") or {}),
        }
    )
    profile["name"] = payload["name"]
    profile["description"] = payload.get("description") or ""
    profile["address_plan"] = _normalize_address_plan(payload.get("address_plan") or {})
    profile["version"] = int(profile.get("version", 1)) + 1
    profile["updated_at"] = now
    _write_store(store)
    return _profile_read(profile, active=store.get("active_profile_id") == profile_id)


def activate_lab_profile(profile_id: str) -> dict[str, Any]:
    store = _read_store()
    if profile_id == RUNTIME_PROFILE_ID:
        store["active_profile_id"] = None
        _write_store(store)
        return list_lab_profiles()
    profile = _find_profile(store, profile_id)
    profile["last_selected_at"] = _now()
    store["active_profile_id"] = profile_id
    _write_store(store)
    return list_lab_profiles()


def get_active_saved_lab_profile() -> dict[str, Any] | None:
    store = _read_store()
    profile_id = store.get("active_profile_id")
    if not profile_id:
        return None
    try:
        return _profile_read(_find_profile(store, str(profile_id)), active=True)
    except LabProfileNotFoundError:
        return None


def active_lab_profile_for_report() -> dict[str, Any]:
    active = get_active_saved_lab_profile()
    if active:
        return active
    return _runtime_profile(active=True)


def _store_path() -> Path:
    configured = os.getenv("LAB_PROFILE_STORE")
    if configured:
        return Path(configured)
    return REPO_ROOT / ".local" / "lab-profiles.json"


def _store_path_label() -> str:
    path = _store_path()
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _read_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"active_profile_id": None, "profiles": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active_profile_id": None, "profiles": []}
    profiles = payload.get("profiles") if isinstance(payload, dict) else []
    active_profile_id = payload.get("active_profile_id") if isinstance(payload, dict) else None
    return {
        "active_profile_id": active_profile_id,
        "profiles": profiles if isinstance(profiles, list) else [],
    }


def _write_store(store: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = redact_sensitive(store)
    path.write_text(json.dumps(sanitized, indent=2, sort_keys=True), encoding="utf-8")


def _find_profile(store: dict[str, Any], profile_id: str) -> dict[str, Any]:
    for profile in store.get("profiles", []):
        if isinstance(profile, dict) and profile.get("id") == profile_id:
            return profile
    raise LabProfileNotFoundError("Lab profile not found")


def _profiles_with_active_flag(store: dict[str, Any]) -> list[dict[str, Any]]:
    active_id = store.get("active_profile_id")
    profiles = [
        _profile_read(profile, active=profile.get("id") == active_id)
        for profile in store.get("profiles", [])
        if isinstance(profile, dict)
    ]
    return sorted(
        profiles,
        key=lambda profile: profile.get("last_selected_at") or profile.get("updated_at") or "",
        reverse=True,
    )


def _active_profile(store: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    active_id = store.get("active_profile_id")
    if active_id:
        for profile in profiles:
            if profile["id"] == active_id:
                return profile
    return _runtime_profile(active=True)


def _profile_read(profile: dict[str, Any], *, active: bool) -> dict[str, Any]:
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or "Unnamed lab"),
        "description": str(profile.get("description") or ""),
        "address_plan": _normalize_address_plan(profile.get("address_plan") or {}),
        "source": str(profile.get("source") or "saved"),
        "version": int(profile.get("version") or 1),
        "active": active,
        "created_at": profile.get("created_at") or _now(),
        "updated_at": profile.get("updated_at") or _now(),
        "last_selected_at": profile.get("last_selected_at"),
        "history": [
            {
                "version": int(item.get("version") or 1),
                "saved_at": item.get("saved_at") or _now(),
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "address_plan": _normalize_address_plan(item.get("address_plan") or {}),
            }
            for item in profile.get("history", [])
            if isinstance(item, dict)
        ],
    }


def _runtime_profile(*, active: bool) -> dict[str, Any]:
    now = _now()
    return {
        "id": RUNTIME_PROFILE_ID,
        "name": "Runtime environment",
        "description": (
            "Unsaved targets currently loaded from environment and safe defaults. "
            "Use a saved lab profile for repeatable lab selection."
        ),
        "address_plan": _runtime_address_plan(),
        "source": "runtime_env",
        "version": 1,
        "active": active,
        "created_at": now,
        "updated_at": now,
        "last_selected_at": None,
        "history": [],
    }


def _runtime_address_plan() -> dict[str, Any]:
    return _normalize_address_plan(
        {
            "subnet": settings.lab_subnet_cidr or LAB_SUBNET_CIDR,
            "ilo": settings.ilo_test_host or LAB_ILO_IP,
            "server_embedded_nic": settings.server_embedded_nic_ip or LAB_SERVER_EMBEDDED_NIC_IP,
            "esxi_management": settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP,
            "cisco_management": settings.cisco_target_ip or LAB_CISCO_MANAGEMENT_IP,
            "ansible_control_host": settings.ansible_control_host or LAB_ANSIBLE_CONTROL_HOST_IP,
            "netapp_controller_a_sp": settings.netapp_controller_a_sp
            or LAB_NETAPP_CONTROLLER_A_SP_IP,
            "netapp_controller_b_sp": settings.netapp_controller_b_sp
            or LAB_NETAPP_CONTROLLER_B_SP_IP,
            "netapp_cluster_mgmt": settings.netapp_cluster_mgmt_ip or LAB_NETAPP_CLUSTER_MGMT_IP,
            "netapp_node_a_mgmt": settings.netapp_node_a_mgmt_ip or LAB_NETAPP_NODE_A_MGMT_IP,
            "netapp_node_b_mgmt": settings.netapp_node_b_mgmt_ip or LAB_NETAPP_NODE_B_MGMT_IP,
            "netapp_svm_mgmt": settings.netapp_svm_mgmt_ip or LAB_NETAPP_SVM_MGMT_IP,
            "netapp_iscsi_lifs": list(settings.netapp_iscsi_lifs or LAB_NETAPP_ISCSI_LIF_IPS),
        }
    )


def _normalize_address_plan(value: dict[str, Any]) -> dict[str, Any]:
    string_fields = [
        "subnet",
        "ilo",
        "server_embedded_nic",
        "esxi_management",
        "cisco_management",
        "ansible_control_host",
        "netapp_controller_a_sp",
        "netapp_controller_b_sp",
        "netapp_cluster_mgmt",
        "netapp_node_a_mgmt",
        "netapp_node_b_mgmt",
        "netapp_svm_mgmt",
    ]
    normalized = {field: _clean_string(value.get(field)) for field in string_fields}
    raw_lifs = value.get("netapp_iscsi_lifs") or []
    if isinstance(raw_lifs, str):
        raw_lifs = [item.strip() for item in raw_lifs.split(",")]
    normalized["netapp_iscsi_lifs"] = [
        item for item in (_clean_string(item) for item in raw_lifs) if item
    ]
    return normalized


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _now() -> str:
    return datetime.now(UTC).isoformat()
