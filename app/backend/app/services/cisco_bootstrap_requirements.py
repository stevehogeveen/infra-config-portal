from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from app.core.config import settings

PROVIDER_ID = "cisco-bootstrap-requirements"
STATE_PATH = Path(__file__).resolve().parents[4] / ".local" / "cisco" / "bootstrap-requirements.json"
HOSTNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")
NEXT_SAFE_ACTION = (
    "Fill missing bootstrap requirements and review the preview before any future guarded workflow."
)
DISABLED_ACTIONS = [
    "answer setup wizard",
    "conf t",
    "write memory",
    "reload",
    "erase/copy",
    "VLAN/interface/user/password changes",
    "enable SSH/SCP",
    "running-config backup",
    "real config apply",
]
NOT_ATTEMPTED = [
    "answer setup wizard yes/no prompt",
    "configure terminal",
    "write memory",
    "reload",
    "copy or erase",
    "VLAN, interface, user, password, SSH, or SCP changes",
    "running-config backup",
    "real config apply",
]


class CiscoBootstrapRequirementsValidationError(ValueError):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("Cisco bootstrap requirements validation failed.")
        self.errors = errors


@dataclass(frozen=True)
class CiscoBootstrapRequirementsInput:
    planned_management_ip: str | None = None
    subnet_prefix: str | None = None
    gateway: str | None = None
    management_vlan: str | None = None
    management_interface: str | None = None
    management_strategy: str | None = None
    hostname: str | None = None
    domain_name: str | None = None
    dns_servers: list[str] | None = None
    local_admin_username_configured: bool = False
    local_admin_username_reference: str | None = None
    operator_notes: str | None = None


def get_cisco_bootstrap_requirements() -> dict[str, Any]:
    saved = _load_saved_requirements()
    return build_cisco_bootstrap_requirements(
        planned_management_ip=_coalesce(saved.get("planned_management_ip"), settings.cisco_target_ip),
        subnet_prefix=_coalesce(saved.get("subnet_prefix"), settings.cisco_management_prefix),
        gateway=_coalesce(saved.get("gateway"), settings.cisco_management_gateway),
        management_vlan=_coalesce(saved.get("management_vlan"), settings.cisco_management_vlan),
        management_interface=_coalesce(
            saved.get("management_interface"),
            settings.cisco_management_interface,
        ),
        management_strategy=_coalesce(
            saved.get("management_strategy"),
            settings.cisco_management_strategy,
        ),
        hostname=_coalesce(saved.get("hostname"), settings.cisco_hostname),
        domain_name=_coalesce(saved.get("domain_name"), settings.cisco_domain_name),
        dns_servers=_list_value(saved.get("dns_servers")) or list(settings.cisco_dns_servers),
        local_admin_username_configured=_bool_saved(
            saved.get("local_admin_username_configured"),
            bool(settings.cisco_test_username),
        ),
        local_admin_username_reference=_coalesce(
            saved.get("local_admin_username_reference"),
            "local environment username configured" if settings.cisco_test_username else None,
        ),
        operator_notes=_coalesce(saved.get("operator_notes"), None),
        management_configured=settings.cisco_mgmt_configured,
    )


def save_cisco_bootstrap_requirements(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = _validate_input(payload)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(parsed), handle, indent=2, sort_keys=True)
        handle.write("\n")
    temp_path.replace(STATE_PATH)
    return build_cisco_bootstrap_requirements(
        planned_management_ip=parsed.planned_management_ip,
        subnet_prefix=parsed.subnet_prefix,
        gateway=parsed.gateway,
        management_vlan=parsed.management_vlan,
        management_interface=parsed.management_interface,
        management_strategy=parsed.management_strategy,
        hostname=parsed.hostname,
        domain_name=parsed.domain_name,
        dns_servers=parsed.dns_servers,
        local_admin_username_configured=parsed.local_admin_username_configured,
        local_admin_username_reference=parsed.local_admin_username_reference,
        operator_notes=parsed.operator_notes,
        management_configured=settings.cisco_mgmt_configured,
    )


def build_cisco_bootstrap_requirements(
    *,
    planned_management_ip: str | None,
    subnet_prefix: str | None = None,
    gateway: str | None = None,
    management_vlan: str | None = None,
    management_interface: str | None = None,
    management_strategy: str | None = None,
    hostname: str | None = None,
    domain_name: str | None = None,
    dns_servers: list[str] | None = None,
    local_admin_username_configured: bool = False,
    local_admin_username_reference: str | None = None,
    operator_notes: str | None = None,
    management_configured: bool = False,
) -> dict[str, Any]:
    dns_servers = dns_servers or []
    requirements = {
        "planned_management_ip": _requirement(
            "planned_management_ip",
            planned_management_ip,
            "Cisco management IP after bootstrap.",
        ),
        "subnet_prefix": _requirement(
            "subnet_prefix",
            subnet_prefix,
            "Management subnet prefix such as /24 or 255.255.255.0.",
        ),
        "gateway": _requirement(
            "gateway",
            gateway,
            "Default gateway for management reachability.",
        ),
        "management_vlan_interface_strategy": {
            "configured": bool(management_vlan or management_interface or management_strategy),
            "vlan": _redacted_value(management_vlan),
            "interface": _redacted_value(management_interface),
            "strategy": _redacted_value(management_strategy),
            "summary": (
                "Management VLAN/interface strategy for the future guarded bootstrap."
            ),
        },
        "hostname": _requirement(
            "hostname",
            hostname,
            "Device hostname for the future guarded bootstrap.",
        ),
        "domain_dns": {
            "configured": bool(domain_name and dns_servers),
            "domain_name": _redacted_value(domain_name),
            "dns_servers": [_redacted_value(server) for server in dns_servers],
            "summary": "Domain name and DNS servers for management resolution.",
        },
        "local_admin_username": {
            "configured": local_admin_username_configured,
            "presence_only": True,
            "value": "configured" if local_admin_username_configured else None,
            "reference": _redacted_value(local_admin_username_reference),
            "summary": "Local admin username presence only. The username is not returned.",
        },
        "ssh_scp_policy": {
            "configured": True,
            "planned_only": True,
            "apply_enabled": False,
            "summary": (
                "SSH/SCP is enabled only by the guarded Cisco real-lab bootstrap, "
                "then used for IOS image transfer after TCP/22 validation."
            ),
            "guarded_enable_command": "ip scp server enable",
            "preferred_transfer_protocol": "SCP",
        },
        "save_behavior": {
            "configured": True,
            "enabled": False,
            "summary": (
                "The ordinary requirements page does not save config; the guarded "
                "real-lab bootstrap saves after the reviewed management commands."
            ),
            "guarded_save_command": "write memory",
        },
        "confirmation_requirements": {
            "configured": _confirmations_defined(
                planned_management_ip=planned_management_ip,
                subnet_prefix=subnet_prefix,
                gateway=gateway,
                management_strategy=management_strategy,
                hostname=hostname,
                domain_name=domain_name,
                dns_servers=dns_servers,
                local_admin_username_configured=local_admin_username_configured,
            ),
            "required": [
                "Confirm selected console path.",
                "Confirm planned management IP, subnet/prefix, gateway, and management strategy.",
                "Confirm hostname, domain, DNS, and local admin username presence.",
                "Review exact future wizard answers or commands before execution.",
                "Require explicit operator approval before sending any answer.",
                "Confirm save behavior remains disabled unless a future workflow explicitly changes it.",
            ],
        },
        "operator_notes": {
            "configured": bool(_redacted_value(operator_notes)),
            "value": _redacted_value(operator_notes),
            "summary": "Operator planning notes. Secrets must not be entered here.",
        },
    }
    blockers = _blockers(requirements)
    missing_blockers = [blocker for blocker in blockers if not blocker.startswith("Bootstrap requirements")]
    warnings = _warnings(management_configured)
    return {
        "provider_id": PROVIDER_ID,
        "status": "needs-input" if missing_blockers else "preview",
        "apply_enabled": False,
        "management_configured": management_configured,
        "requirements": requirements,
        "blockers": blockers,
        "warnings": warnings,
        "disabled_actions": DISABLED_ACTIONS,
        "not_attempted": NOT_ATTEMPTED,
        "next_safe_action": NEXT_SAFE_ACTION,
    }


def _requirement(key: str, value: str | None, summary: str) -> dict[str, Any]:
    return {
        "configured": bool(value),
        "value": _redacted_value(value),
        "key": key,
        "summary": summary,
    }


def _redacted_value(value: str | None) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _confirmations_defined(
    *,
    planned_management_ip: str | None,
    subnet_prefix: str | None,
    gateway: str | None,
    management_strategy: str | None,
    hostname: str | None,
    domain_name: str | None,
    dns_servers: list[str],
    local_admin_username_configured: bool,
) -> bool:
    return all(
        [
            _redacted_value(planned_management_ip),
            _redacted_value(subnet_prefix),
            _redacted_value(gateway),
            _redacted_value(management_strategy),
            _redacted_value(hostname),
            _redacted_value(domain_name),
            dns_servers,
            local_admin_username_configured,
        ]
    )


def _blockers(requirements: dict[str, Any]) -> list[str]:
    labels = {
        "planned_management_ip": "Planned management IP is required.",
        "subnet_prefix": "Management subnet/prefix is required.",
        "gateway": "Management gateway is required.",
        "management_vlan_interface_strategy": (
            "Management VLAN/interface strategy is required."
        ),
        "hostname": "Hostname is required.",
        "domain_dns": "Domain and DNS server requirements are required.",
        "local_admin_username": "Local admin username presence must be confirmed.",
        "confirmation_requirements": (
            "Explicit confirmation requirements must be defined before execution."
        ),
    }
    blockers = [
        labels[key]
        for key in labels
        if not bool(requirements[key]["configured"])
    ]
    blockers.append("Bootstrap requirements are preview-only; no answers or commands will be sent.")
    return blockers


def _warnings(management_configured: bool) -> list[str]:
    if management_configured:
        return [
            "CISCO_MGMT_CONFIGURED is true; verify this before using console bootstrap planning."
        ]
    return ["CISCO_MGMT_CONFIGURED is false; console/bootstrap planning comes first."]


def _load_saved_requirements() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _validate_input(payload: dict[str, Any]) -> CiscoBootstrapRequirementsInput:
    cleaned = {
        "planned_management_ip": _string(payload.get("planned_management_ip")),
        "subnet_prefix": _string(payload.get("subnet_prefix")),
        "gateway": _string(payload.get("gateway")),
        "management_vlan": _string(payload.get("management_vlan")),
        "management_interface": _string(payload.get("management_interface")),
        "management_strategy": _string(payload.get("management_strategy")),
        "hostname": _string(payload.get("hostname")),
        "domain_name": _string(payload.get("domain_name")),
        "dns_servers": _list_value(payload.get("dns_servers")),
        "local_admin_username_configured": bool(payload.get("local_admin_username_configured")),
        "local_admin_username_reference": _string(payload.get("local_admin_username_reference")),
        "operator_notes": _string(payload.get("operator_notes")),
    }
    errors: list[dict[str, str]] = []
    _require_ip(cleaned["planned_management_ip"], "planned_management_ip", errors)
    _require_subnet_prefix(cleaned["subnet_prefix"], errors)
    _require_ip(cleaned["gateway"], "gateway", errors)
    _require_text(cleaned["management_strategy"], "management_strategy", errors)
    _require_hostname(cleaned["hostname"], errors)
    _require_text(cleaned["domain_name"], "domain_name", errors)
    if not cleaned["dns_servers"]:
        errors.append({"field": "dns_servers", "message": "At least one DNS server is required."})
    for dns_server in cleaned["dns_servers"]:
        _require_ip(dns_server, "dns_servers", errors)
    if not cleaned["local_admin_username_configured"]:
        errors.append(
            {
                "field": "local_admin_username_configured",
                "message": "Local admin username presence must be confirmed.",
            }
        )
    if errors:
        raise CiscoBootstrapRequirementsValidationError(errors)
    return CiscoBootstrapRequirementsInput(**cleaned)


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _coalesce(left: object, right: str | None) -> str | None:
    return left if isinstance(left, str) and left.strip() else right


def _list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _bool_saved(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _require_ip(value: str | None, field: str, errors: list[dict[str, str]]) -> None:
    if not value:
        errors.append({"field": field, "message": f"{field} is required."})
        return
    try:
        ip_address(value)
    except ValueError:
        errors.append({"field": field, "message": f"{field} must be a valid IP address."})


def _require_subnet_prefix(value: str | None, errors: list[dict[str, str]]) -> None:
    if not value:
        errors.append({"field": "subnet_prefix", "message": "subnet_prefix is required."})
        return
    if value.startswith("/"):
        try:
            prefix = int(value[1:])
        except ValueError:
            errors.append({"field": "subnet_prefix", "message": "subnet_prefix must be valid."})
            return
        if 0 <= prefix <= 32:
            return
    try:
        ip_address(value)
        return
    except ValueError:
        errors.append({"field": "subnet_prefix", "message": "subnet_prefix must be valid."})


def _require_text(value: str | None, field: str, errors: list[dict[str, str]]) -> None:
    if not value:
        errors.append({"field": field, "message": f"{field} is required."})


def _require_hostname(value: str | None, errors: list[dict[str, str]]) -> None:
    if not value:
        errors.append({"field": "hostname", "message": "hostname is required."})
        return
    if not HOSTNAME_RE.match(value) or "--" in value:
        errors.append({"field": "hostname", "message": "hostname must be safe-looking."})
