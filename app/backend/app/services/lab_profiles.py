from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import (
    LAB_SUBNET_CIDR,
    settings,
)
from app.providers.redaction import redact_sensitive
from app.services.lab_topology import (
    HIGH_ADDRESS_LAB,
    LabTopologyError,
    configured_runtime_values,
    derive_lab_topology,
    runtime_configured_address_plan,
    topology_for_prefix,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNTIME_PROFILE_ID = "runtime"
SUBNET_PREFIX_OPTIONS = tuple(range(29, 22, -1))
NETAPP_MINIMUM_PREFIX = 24
NETAPP_DISABLED_REASON = (
    "NetApp high-address defaults require a /24 or larger lab subnet. "
    "Compact /26 lab profiles keep NetApp not_in_scope by default."
)
RUNTIME_ENV_FILE_ENV = "LAB_RUNTIME_ENV_FILE"
RUNTIME_ENV_SCALAR_FIELDS = (
    ("subnet", "LAB_SUBNET_CIDR"),
    ("ilo", "ILO_TEST_HOST"),
    ("server_embedded_nic", "SERVER_EMBEDDED_NIC_IP"),
    ("esxi_management", "ESXI_TEST_HOST"),
    ("cisco_management", "CISCO_TARGET_IP"),
    ("cisco_management", "ANSIBLE_CISCO_HOST"),
    ("ansible_control_host", "ANSIBLE_CONTROL_HOST"),
)
RUNTIME_ENV_NETAPP_FIELDS = (
    ("netapp_controller_a_sp", "NETAPP_CONTROLLER_A_SP"),
    ("netapp_controller_b_sp", "NETAPP_CONTROLLER_B_SP"),
    ("netapp_cluster_mgmt", "NETAPP_CLUSTER_MGMT_IP"),
    ("netapp_node_a_mgmt", "NETAPP_NODE_A_MGMT_IP"),
    ("netapp_node_b_mgmt", "NETAPP_NODE_B_MGMT_IP"),
    ("netapp_svm_mgmt", "NETAPP_SVM_MGMT_IP"),
    ("netapp_nfs_lifs", "NETAPP_NFS_LIFS"),
    ("netapp_iscsi_lifs", "NETAPP_ISCSI_LIFS"),
)
RUNTIME_ENV_PROFILE_KEYS = (
    "LAB_PROFILE_TOPOLOGY",
    "LAB_GATEWAY",
    "LAB_DNS_SERVERS",
    "LAB_NTP_SERVERS",
    "LAB_MTU",
    "LAB_PROFILE_NETAPP_ENABLED",
    "CISCO_MGMT_CONFIGURED",
    "ESXI_CONFIGURED",
)
RUNTIME_ENV_ALLOWED_KEYS = {
    *(env_key for _, env_key in RUNTIME_ENV_SCALAR_FIELDS),
    *(env_key for _, env_key in RUNTIME_ENV_NETAPP_FIELDS),
    *RUNTIME_ENV_PROFILE_KEYS,
}
ENV_ASSIGNMENT_RE = re.compile(r"^(?P<prefix>\s*(?:export\s+)?)(?P<key>[A-Z0-9_]+)\s*=.*$")


class LabProfileError(Exception):
    pass


class LabProfileNotFoundError(LabProfileError):
    pass


def list_lab_profiles() -> dict[str, Any]:
    store = _read_store()
    profiles = _profiles_with_active_flag(store)
    active_profile = _active_profile(store, profiles)
    active_context = active_lab_profile_context(active_profile)
    test_fixture_mode = _provider_mode() == "mock"
    return {
        "active_profile": active_context["active_profile"],
        "active_context": active_context,
        "runtime_profile": _runtime_profile(active=active_profile["id"] == RUNTIME_PROFILE_ID),
        "profiles": profiles,
        "subnet_options": lab_subnet_options(),
        "store_path": _store_path_label(),
        "mock_only": test_fixture_mode,
        "next_safe_action": (
            "Select a saved lab or create a new profile before running lab-specific planning."
            if test_fixture_mode
            else "Run `make provider-lab-live-status` to refresh the current real-lab profile."
        ),
    }


def create_lab_profile(payload: dict[str, Any]) -> dict[str, Any]:
    store = _read_store()
    now = _now()
    components = _normalize_profile_components(payload)
    profile = {
        "id": f"lab-{uuid4().hex[:12]}",
        "name": payload["name"],
        "description": payload.get("description") or "",
        **_profile_component_fields(components),
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
            "profile_topology": profile.get("profile_topology"),
            "subnet_cidr": profile.get("subnet_cidr"),
            "gateway": profile.get("gateway"),
            "dns": deepcopy(profile.get("dns") or []),
            "ntp": deepcopy(profile.get("ntp") or []),
            "vlan_id": profile.get("vlan_id"),
            "mtu": profile.get("mtu"),
            "devices": deepcopy(profile.get("devices") or {}),
            "features": deepcopy(profile.get("features") or {}),
            "global_settings": deepcopy(profile.get("global_settings") or {}),
            "address_plan": deepcopy(profile.get("address_plan") or {}),
        }
    )
    components = _normalize_profile_components(payload)
    profile["name"] = payload["name"]
    profile["description"] = payload.get("description") or ""
    profile.update(_profile_component_fields(components))
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


def apply_active_profile_to_runtime_env() -> dict[str, Any]:
    store = _read_store()
    profiles = _profiles_with_active_flag(store)
    active = _active_profile(store, profiles)
    if active.get("id") == RUNTIME_PROFILE_ID or active.get("source") != "saved":
        raise LabProfileError("Select a saved lab profile before applying runtime IPs.")

    context = active_lab_profile_context(active)
    updates, removals = _runtime_env_changes_for_context(context)
    env_path = _runtime_env_path()
    updated_keys, removed_keys = _write_runtime_env(env_path, updates, removals)

    for key in removed_keys:
        os.environ.pop(key, None)
    for key, value in updates.items():
        os.environ[key] = value

    changed = bool(updated_keys or removed_keys)
    return {
        "applied": changed,
        "env_path": _path_label(env_path),
        "updated_keys": updated_keys,
        "removed_keys": removed_keys,
        "restart_required": True,
        "message": (
            "Runtime IP env values were updated from the active lab profile."
            if changed
            else "Runtime IP env values already match the active lab profile."
        ),
        "next_action": "Restart the backend before running live provider checks that use startup-loaded settings.",
        "lab_profiles": list_lab_profiles(),
    }


def active_lab_profile_runtime_env_command() -> str:
    context = active_lab_profile_context()
    updates, removals = _runtime_env_changes_for_context(context)
    lines = ["cat <<'EOF' >> .env.local.real-lab"]
    lines.extend(f"{key}={updates[key]}" for key in sorted(updates))
    lines.append("EOF")
    if removals:
        lines.append("")
        lines.append("# Remove not-in-scope runtime IP keys if they exist:")
        lines.extend(f"# unset {key}" for key in sorted(removals))
    return "\n".join(lines)


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


def active_lab_profile_context(profile: dict[str, Any] | None = None) -> dict[str, Any]:
    active = deepcopy(profile or active_lab_profile_for_report())
    runtime = _runtime_profile(active=active.get("id") == RUNTIME_PROFILE_ID)
    warnings, guidance = _runtime_mismatch_guidance(active)
    active["mismatch_warnings"] = warnings
    active["fix_guidance"] = guidance
    features = active.get("features") if isinstance(active.get("features"), dict) else {}
    disabled = {
        "netapp": str(features.get("netapp_disabled_reason") or "NetApp disabled by active profile.")
        for enabled in [features.get("netapp_enabled")]
        if enabled is False
    }
    if features.get("vcenter_enabled") is False:
        disabled["vcenter"] = str(
            features.get("vcenter_disabled_reason") or "vCenter disabled by active profile."
        )
    return {
        "active_profile": active,
        "runtime_profile": runtime,
        "topology": str(active.get("profile_topology") or HIGH_ADDRESS_LAB),
        "resolved_address_plan": active.get("resolved_address_plan") or active.get("address_plan") or {},
        "enabled_features": features,
        "disabled_features": disabled,
        "not_in_scope_stages": list(active.get("not_in_scope_stages") or []),
        "mismatch_warnings": warnings,
        "fix_guidance": guidance,
    }


def lab_subnet_options() -> list[dict[str, Any]]:
    return [
        {
            "prefix": prefix,
            "cidr_suffix": f"/{prefix}",
            "label": f"/{prefix} ({_usable_hosts(prefix)} usable IPs)",
            "usable_hosts": _usable_hosts(prefix),
            "netapp_supported": _netapp_supported(prefix),
            "netapp_disabled_reason": None if _netapp_supported(prefix) else NETAPP_DISABLED_REASON,
            "default_topology": topology_for_prefix(prefix),
        }
        for prefix in SUBNET_PREFIX_OPTIONS
    ]


def _runtime_env_path() -> Path:
    configured = os.getenv(RUNTIME_ENV_FILE_ENV)
    if configured:
        return Path(configured)
    return REPO_ROOT / ".env.local.real-lab"


def _path_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _runtime_env_changes_for_context(context: dict[str, Any]) -> tuple[dict[str, str], set[str]]:
    active = context["active_profile"]
    address_plan = context["resolved_address_plan"]
    global_settings = active.get("global_settings") or {}
    features = context.get("enabled_features") or {}
    updates: dict[str, str] = {}
    removals: set[str] = set()

    for field, env_key in RUNTIME_ENV_SCALAR_FIELDS:
        value = _profile_value(address_plan.get(field))
        if value:
            updates[env_key] = value

    updates["LAB_PROFILE_TOPOLOGY"] = str(context.get("topology") or active.get("profile_topology") or HIGH_ADDRESS_LAB)
    for source_key, env_key in (
        ("gateway", "LAB_GATEWAY"),
        ("mtu", "LAB_MTU"),
    ):
        value = _profile_value(global_settings.get(source_key) or active.get(source_key))
        if value:
            updates[env_key] = value
        else:
            removals.add(env_key)
    for source_key, env_key in (
        ("dns_servers", "LAB_DNS_SERVERS"),
        ("ntp_servers", "LAB_NTP_SERVERS"),
    ):
        value = _profile_value(global_settings.get(source_key) or active.get(source_key))
        if value:
            updates[env_key] = value
        else:
            removals.add(env_key)

    netapp_enabled = bool(features.get("netapp_enabled"))
    updates["LAB_PROFILE_NETAPP_ENABLED"] = "true" if netapp_enabled else "false"
    updates["CISCO_MGMT_CONFIGURED"] = "false"
    updates["ESXI_CONFIGURED"] = "false"
    if netapp_enabled:
        for field, env_key in RUNTIME_ENV_NETAPP_FIELDS:
            value = _profile_value(address_plan.get(field))
            if value:
                updates[env_key] = value
            else:
                removals.add(env_key)
    else:
        removals.update(env_key for _, env_key in RUNTIME_ENV_NETAPP_FIELDS)

    return updates, removals - set(updates)


def _write_runtime_env(
    path: Path,
    updates: dict[str, str],
    removals: set[str],
) -> tuple[list[str], list[str]]:
    current = _read_env_file_values(path)
    updated_keys = sorted(
        key for key, value in updates.items() if key in RUNTIME_ENV_ALLOWED_KEYS and current.get(key) != value
    )
    removed_keys = sorted(
        key
        for key in removals
        if key in RUNTIME_ENV_ALLOWED_KEYS and (key in current or os.environ.get(key) is not None)
    )
    if not updated_keys and not removed_keys:
        return [], []

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        key = _env_line_key(line)
        if key is None or key not in RUNTIME_ENV_ALLOWED_KEYS:
            next_lines.append(line)
            continue
        if key in removals:
            seen.add(key)
            continue
        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
        next_lines.append(line)

    if next_lines and next_lines[-1].strip():
        next_lines.append("")
    for key in sorted(updates):
        if key in RUNTIME_ENV_ALLOWED_KEYS and key not in seen:
            next_lines.append(f"{key}={updates[key]}")
    path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    return updated_keys, removed_keys


def _read_env_file_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key = _env_line_key(line)
        if key is None:
            continue
        values[key] = line.split("=", maxsplit=1)[1].strip().strip("\"'")
    return values


def _env_line_key(line: str) -> str | None:
    match = ENV_ASSIGNMENT_RE.match(line)
    if not match:
        return None
    return match.group("key")


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
        _profile_read(
            profile,
            active=profile.get("id") == active_id,
        )
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
    components = _normalize_profile_components(profile)
    history = []
    for item in profile.get("history", []):
        if not isinstance(item, dict):
            continue
        revision_components = _normalize_profile_components(item)
        history.append(
            {
                "version": int(item.get("version") or 1),
                "saved_at": item.get("saved_at") or _now(),
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                **_profile_component_fields(revision_components),
            }
        )
    return {
        "id": str(profile.get("id") or ""),
        "name": str(profile.get("name") or "Unnamed lab"),
        "description": str(profile.get("description") or ""),
        **_profile_component_fields(components),
        "resolved_address_plan": components["resolved_address_plan"],
        "not_in_scope_stages": components["not_in_scope_stages"],
        "mismatch_warnings": list(profile.get("mismatch_warnings") or []),
        "fix_guidance": list(profile.get("fix_guidance") or []),
        "source": str(profile.get("source") or "saved"),
        "version": int(profile.get("version") or 1),
        "active": active,
        "created_at": profile.get("created_at") or _now(),
        "updated_at": profile.get("updated_at") or _now(),
        "last_selected_at": profile.get("last_selected_at"),
        "history": history,
    }


def _runtime_profile(*, active: bool) -> dict[str, Any]:
    now = _now()
    components = _runtime_profile_components()
    return {
        "id": RUNTIME_PROFILE_ID,
        "name": "Runtime environment",
        "description": (
            "Unsaved targets currently loaded from environment and safe defaults. "
            "Use a saved lab profile for repeatable lab selection."
        ),
        **_profile_component_fields(components),
        "resolved_address_plan": components["resolved_address_plan"],
        "not_in_scope_stages": components["not_in_scope_stages"],
        "mismatch_warnings": [],
        "fix_guidance": [],
        "source": "runtime_env",
        "version": 1,
        "active": active,
        "created_at": now,
        "updated_at": now,
        "last_selected_at": None,
        "history": [],
    }


def _provider_mode() -> str:
    return os.getenv("PROVIDER_MODE", settings.provider_mode)


def _saved_profile_is_stale_for_operator_runtime(profile: dict[str, Any]) -> bool:
    if _provider_mode() == "mock":
        return False
    if profile.get("source") != "saved":
        return False
    components = _normalize_profile_components(profile)
    return _contains_stale_lab_value(
        components.get("address_plan"),
        components.get("global_settings"),
    ) or _differs_from_runtime_profile(
        components.get("address_plan") or {}
    )


def _contains_stale_lab_value(*values: Any) -> bool:
    stack = list(values)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
            continue
        if isinstance(value, (list, tuple)):
            stack.extend(value)
            continue
        if isinstance(value, str) and "10.10.8." in value:
            return True
    return False


def _differs_from_runtime_profile(address_plan: dict[str, Any]) -> bool:
    runtime_address_plan = _runtime_address_plan()
    for key, runtime_value in runtime_address_plan.items():
        value = address_plan.get(key)
        if isinstance(runtime_value, list):
            if list(value or []) != runtime_value:
                return True
            continue
        if value != runtime_value:
            return True
    return False


def _runtime_mismatch_guidance(
    active: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expected_plan = active.get("resolved_address_plan") or active.get("address_plan") or {}
    features = active.get("features") if isinstance(active.get("features"), dict) else {}
    configured = configured_runtime_values()
    env_fields = {
        "subnet": "LAB_SUBNET_CIDR",
        "ilo": "ILO_TEST_HOST",
        "server_embedded_nic": "SERVER_EMBEDDED_NIC_IP",
        "esxi_management": "ESXI_TEST_HOST",
        "cisco_management": "CISCO_TARGET_IP",
        "ansible_cisco_inventory_target": "ANSIBLE_CISCO_HOST",
        "ansible_control_host": "ANSIBLE_CONTROL_HOST",
        "netapp_controller_a_sp": "NETAPP_CONTROLLER_A_SP",
        "netapp_controller_b_sp": "NETAPP_CONTROLLER_B_SP",
        "netapp_cluster_mgmt": "NETAPP_CLUSTER_MGMT_IP",
        "netapp_node_a_mgmt": "NETAPP_NODE_A_MGMT_IP",
        "netapp_node_b_mgmt": "NETAPP_NODE_B_MGMT_IP",
        "netapp_svm_mgmt": "NETAPP_SVM_MGMT_IP",
        "netapp_nfs_lifs": "NETAPP_NFS_LIFS",
        "netapp_iscsi_lifs": "NETAPP_ISCSI_LIFS",
    }
    warnings: list[dict[str, Any]] = []
    guidance: list[dict[str, Any]] = []
    netapp_enabled = bool(features.get("netapp_enabled"))

    for field, current_value in configured.items():
        if current_value in {None, ""}:
            continue
        expected_field = "cisco_management" if field == "ansible_cisco_inventory_target" else field
        expected_value = _profile_value(expected_plan.get(expected_field))
        env_field = env_fields.get(field, field.upper())
        if field.startswith("netapp_") and not netapp_enabled:
            expected_value = "not_in_scope"
        if expected_value in {None, "", "Not set"} and "10.10.8." not in str(current_value):
            continue
        if str(current_value) == str(expected_value):
            continue
        classification = (
            "stale_config" if "10.10.8." in str(current_value) else "profile_mismatch"
        )
        action = (
            f"Unset {env_field}; {field} is not in scope for active profile `{active.get('name')}`."
            if expected_value == "not_in_scope"
            else f"Set {env_field} to {expected_value} or update the active lab profile."
        )
        warning = {
            "field": field,
            "env_field": env_field,
            "classification": classification,
            "current_value": current_value,
            "expected_value": expected_value,
            "active_profile": active.get("name"),
            "where_to_fix": ".env.local.real-lab or Settings / Lab Profile",
            "recommended_action": action,
            "recheck_command": "make provider-lab-build-verification-live",
        }
        warnings.append(warning)
        guidance.append(
            {
                **warning,
                "copyable_command": (
                    f"unset {env_field}"
                    if expected_value == "not_in_scope"
                    else f"{env_field}={expected_value}"
                ),
            }
        )
    return warnings, guidance


def _profile_value(value: Any) -> str | None:
    if isinstance(value, list):
        return ",".join(str(item) for item in value if item)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _runtime_address_plan() -> dict[str, Any]:
    return _runtime_profile_components()["address_plan"]


def _runtime_profile_components() -> dict[str, Any]:
    netapp_enabled_override = _env_bool_or_none("LAB_PROFILE_NETAPP_ENABLED")
    global_settings = {
        "gateway": _clean_string(os.getenv("LAB_GATEWAY")) or settings.cisco_management_gateway,
        "dns_servers": _clean_string_list(os.getenv("LAB_DNS_SERVERS")) or list(settings.cisco_dns_servers),
        "ntp_servers": _clean_string_list(os.getenv("LAB_NTP_SERVERS")),
        "vlan_id": settings.cisco_management_vlan,
        "mtu": os.getenv("LAB_MTU"),
    }
    features = {
        "vcenter_enabled": settings.vcenter_configured,
        "storage_protocol": settings.netapp_storage_protocol,
    }
    if netapp_enabled_override is not None:
        features["netapp_enabled"] = netapp_enabled_override
    elif settings.netapp_configured:
        features["netapp_enabled"] = True
    address_plan = runtime_configured_address_plan()
    if not address_plan.get("subnet"):
        address_plan["subnet"] = settings.lab_subnet_cidr or LAB_SUBNET_CIDR
    payload = {
        "profile_topology": _clean_string(os.getenv("LAB_PROFILE_TOPOLOGY")),
        "subnet_cidr": address_plan.get("subnet"),
        "global_settings": global_settings,
        "address_plan": address_plan,
        "devices": {},
        "features": features,
    }
    try:
        return _derive_components(payload)
    except LabProfileError:
        safe_address_plan = {"subnet": address_plan.get("subnet")}
        return _derive_components({**payload, "address_plan": safe_address_plan})


def _normalize_profile_components(payload: dict[str, Any]) -> dict[str, Any]:
    return _derive_components(payload)


def _derive_components(payload: dict[str, Any]) -> dict[str, Any]:
    address_plan = _normalize_address_plan(payload.get("address_plan") or {})
    global_settings = dict(payload.get("global_settings") or {})
    if payload.get("gateway") is not None:
        global_settings["gateway"] = payload.get("gateway")
    if payload.get("dns"):
        global_settings["dns"] = payload.get("dns")
    if payload.get("ntp"):
        global_settings["ntp"] = payload.get("ntp")
    if payload.get("vlan_id") is not None:
        global_settings["vlan_id"] = payload.get("vlan_id")
    if payload.get("mtu") is not None:
        global_settings["mtu"] = payload.get("mtu")
    subnet_cidr = payload.get("subnet_cidr") or address_plan.get("subnet")
    if subnet_cidr and global_settings.get("subnet_prefix") is not None and not payload.get("subnet_cidr"):
        subnet_cidr = f"{str(subnet_cidr).split('/', maxsplit=1)[0]}/{global_settings['subnet_prefix']}"
    try:
        return derive_lab_topology(
            profile_topology=payload.get("profile_topology"),
            subnet_cidr=subnet_cidr,
            global_settings=global_settings,
            address_plan=address_plan,
            devices=payload.get("devices") if isinstance(payload.get("devices"), dict) else {},
            features=payload.get("features") if isinstance(payload.get("features"), dict) else {},
            default_subnet=LAB_SUBNET_CIDR,
        )
    except LabTopologyError as exc:
        raise LabProfileError(str(exc)) from exc


def _profile_component_fields(components: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_topology": components["profile_topology"],
        "subnet_cidr": components["subnet_cidr"],
        "gateway": components["gateway"],
        "dns": components["dns"],
        "ntp": components["ntp"],
        "vlan_id": components["vlan_id"],
        "mtu": components["mtu"],
        "devices": components["devices"],
        "features": components["features"],
        "global_settings": components["global_settings"],
        "address_plan": components["address_plan"],
    }


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
    for list_field in ("netapp_nfs_lifs", "netapp_iscsi_lifs"):
        raw_lifs = value.get(list_field) or []
        if isinstance(raw_lifs, str):
            raw_lifs = [item.strip() for item in raw_lifs.split(",")]
        normalized[list_field] = [
            item for item in (_clean_string(item) for item in raw_lifs) if item
        ]
    return normalized


def _usable_hosts(prefix: int) -> int:
    return max((2 ** (32 - prefix)) - 2, 0)


def _netapp_supported(prefix: int) -> bool:
    return prefix <= NETAPP_MINIMUM_PREFIX


def _clean_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = [value]
    return [item for item in (_clean_string(candidate) for candidate in candidates) if item]


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _env_bool_or_none(name: str) -> bool | None:
    value = _clean_string(os.getenv(name))
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def _now() -> str:
    return datetime.now(UTC).isoformat()
