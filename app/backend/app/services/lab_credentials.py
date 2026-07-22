from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.core.config import settings

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
# This must be the repo-root file, not a backend-local one. config.py's
# _load_local_real_lab_env() searches cwd (= app/backend when uvicorn is
# launched from there) *before* repo root, and stops at the first file
# whose LAB_ENVIRONMENT=isolated-real-lab. Since every file this service
# writes sets that same marker, a backend-local file would have been found
# first and permanently shadowed the real ~60-key authoritative file at
# repo root instead of merging into it.
REAL_LAB_ENV_FILE = REPO_ROOT / ".env.local.real-lab"
RELOAD_TRIGGER_FILE = BACKEND_ROOT / "app" / "main.py"

# Each entry: (field name accepted from the API) -> (env var name, is_secret, "configured" check)
CREDENTIAL_FIELDS: dict[str, str] = {
    "ilo_host": "ILO_TEST_HOST",
    "ilo_username": "ILO_TEST_USERNAME",
    "ilo_password": "ILO_TEST_PASSWORD",
    "esxi_host": "ESXI_TEST_HOST",
    "esxi_username": "ESXI_TEST_USERNAME",
    "esxi_password": "ESXI_TEST_PASSWORD",
    "cisco_username": "CISCO_TEST_USERNAME",
    "cisco_password": "CISCO_TEST_PASSWORD",
    "cisco_enable_password": "CISCO_ENABLE_PASSWORD",
    "netapp_username": "NETAPP_API_USERNAME",
    "netapp_password": "NETAPP_API_PASSWORD",
    "vcenter_username": "VCENTER_USERNAME",
    "vcenter_password": "VCENTER_PASSWORD",
    "snmp_community": "SNMP_COMMUNITY",
    "snmp_v3_username": "SNMP_V3_USERNAME",
    "snmp_v3_auth_protocol": "SNMP_V3_AUTH_PROTOCOL",
    "snmp_v3_auth_password": "SNMP_V3_AUTH_PASSWORD",
    "snmp_v3_priv_protocol": "SNMP_V3_PRIV_PROTOCOL",
    "snmp_v3_priv_password": "SNMP_V3_PRIV_PASSWORD",
}

SECRET_FIELDS = {
    "ilo_password",
    "esxi_password",
    "cisco_password",
    "cisco_enable_password",
    "netapp_password",
    "vcenter_password",
    "snmp_community",
    "snmp_v3_auth_password",
    "snmp_v3_priv_password",
}

# Groups shown together in the UI, in device order.
CREDENTIAL_GROUPS: list[dict[str, Any]] = [
    {
        "id": "ilo",
        "label": "HPE iLO",
        "hint": "iLO 5 / iLO 6 out-of-band management sign-in. Host overrides the address used for real probes if it differs from the saved lab profile.",
        "fields": ["ilo_host", "ilo_username", "ilo_password"],
    },
    {
        "id": "esxi",
        "label": "ESXi",
        "hint": "ESXi 7 / ESXi 8 host sign-in. Host overrides the address used for real probes if it differs from the saved lab profile.",
        "fields": ["esxi_host", "esxi_username", "esxi_password"],
    },
    {
        "id": "cisco",
        "label": "Cisco switch",
        "hint": "SSH sign-in plus the enable secret for privileged commands.",
        "fields": ["cisco_username", "cisco_password", "cisco_enable_password"],
    },
    {
        "id": "netapp",
        "label": "NetApp ONTAP",
        "hint": "Cluster/SVM management API sign-in.",
        "fields": ["netapp_username", "netapp_password"],
    },
    {
        "id": "vcenter",
        "label": "vCenter",
        "hint": "vCenter/ESXi VM-management API sign-in.",
        "fields": ["vcenter_username", "vcenter_password"],
    },
    {
        "id": "snmp",
        "label": "SNMP",
        "hint": "Read-only monitoring credentials for the SNMP managers configured in Lab Defaults.",
        "fields": [
            "snmp_community",
            "snmp_v3_username",
            "snmp_v3_auth_protocol",
            "snmp_v3_auth_password",
            "snmp_v3_priv_protocol",
            "snmp_v3_priv_password",
        ],
    },
]

_SETTINGS_ATTR_BY_FIELD: dict[str, str] = {
    "ilo_host": "ilo_test_host",
    "ilo_username": "ilo_test_username",
    "ilo_password": "ilo_test_password",
    "esxi_host": "esxi_test_host",
    "esxi_username": "esxi_test_username",
    "esxi_password": "esxi_test_password",
    "cisco_username": "cisco_test_username",
    "cisco_password": "cisco_test_password",
    "cisco_enable_password": "cisco_enable_password",
    "netapp_username": "netapp_api_username",
    "netapp_password": "netapp_api_password",
    "vcenter_username": "vcenter_username",
    "vcenter_password": "vcenter_password",
}


class LabCredentialsError(ValueError):
    pass


def read_lab_credentials_status() -> dict[str, Any]:
    groups = []
    for group in CREDENTIAL_GROUPS:
        fields = [_field_status(name) for name in group["fields"]]
        groups.append({
            "id": group["id"],
            "label": group["label"],
            "hint": group["hint"],
            "fields": fields,
            "configured": any(f["configured"] for f in fields),
        })
    return {
        "groups": groups,
        "store_path": _display_path(REAL_LAB_ENV_FILE),
        "restart_required": True,
        "next_safe_action": (
            "Saving credentials restarts the backend automatically (a few seconds) so the new "
            "sign-in takes effect immediately."
        ),
    }


def update_lab_credentials(payload: dict[str, Any]) -> dict[str, Any]:
    provided = {
        key: str(value).strip()
        for key, value in payload.items()
        if key in CREDENTIAL_FIELDS and value is not None and str(value).strip() != ""
    }
    if not provided:
        raise LabCredentialsError("No credential values were provided.")

    existing = dict(dotenv_values(REAL_LAB_ENV_FILE)) if REAL_LAB_ENV_FILE.exists() else {}
    for field, value in provided.items():
        existing[CREDENTIAL_FIELDS[field]] = value

    _write_env_file(existing)

    # Apply immediately to this process too, so a same-request status read
    # already reflects the change even before the reload finishes.
    for field, value in provided.items():
        os.environ[CREDENTIAL_FIELDS[field]] = value

    _trigger_reload()

    return read_lab_credentials_status()


def _field_status(field: str) -> dict[str, Any]:
    env_name = CREDENTIAL_FIELDS[field]
    settings_attr = _SETTINGS_ATTR_BY_FIELD.get(field)
    # Prefer the live environment over the frozen Settings snapshot: a save
    # earlier in this same process already updated os.environ, but Settings
    # is a frozen dataclass computed once at import time and won't reflect
    # it until the process actually restarts. Reading os.environ first means
    # a save shows its own new value immediately instead of only after the
    # reload finishes.
    value = os.getenv(env_name)
    if value is None and settings_attr:
        value = getattr(settings, settings_attr, None)
    is_secret = field in SECRET_FIELDS
    return {
        "field": field,
        "env_var": env_name,
        "is_secret": is_secret,
        "configured": bool(value),
        # Non-secret fields (usernames, SNMP protocol names) are safe to echo
        # back so the operator doesn't have to retype them on every visit.
        # Secret fields (passwords, community strings) are never returned.
        "value": None if is_secret else value,
    }


def _write_env_file(values: dict[str, str]) -> None:
    REAL_LAB_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ["LAB_ENVIRONMENT=isolated-real-lab"]
    for key, value in sorted(values.items()):
        if key == "LAB_ENVIRONMENT" or value is None:
            # dotenv_values() can hand back a None value for a stray/blank
            # line, or a bogus "key" for a leading UTF-8 BOM byte on a file
            # some other tool/editor saved with one. Neither is a real
            # setting; carrying it forward would either crash (None has no
            # .replace) or write junk back into the authoritative file.
            continue
        if not key.isidentifier():
            continue
        safe_value = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{safe_value}"')
    REAL_LAB_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _trigger_reload() -> None:
    try:
        os.utime(RELOAD_TRIGGER_FILE, (time.time(), time.time()))
    except OSError:
        pass


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
