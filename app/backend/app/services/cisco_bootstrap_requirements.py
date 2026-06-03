from __future__ import annotations

from typing import Any

from app.core.config import settings

PROVIDER_ID = "cisco-bootstrap-requirements"
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


def get_cisco_bootstrap_requirements() -> dict[str, Any]:
    return build_cisco_bootstrap_requirements(
        planned_management_ip=settings.cisco_target_ip,
        subnet_prefix=settings.cisco_management_prefix,
        gateway=settings.cisco_management_gateway,
        management_vlan=settings.cisco_management_vlan,
        management_interface=settings.cisco_management_interface,
        management_strategy=settings.cisco_management_strategy,
        hostname=settings.cisco_hostname,
        domain_name=settings.cisco_domain_name,
        dns_servers=list(settings.cisco_dns_servers),
        local_admin_username_configured=bool(settings.cisco_test_username),
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
            "summary": "Local admin username presence only. The username is not returned.",
        },
        "ssh_scp_policy": {
            "configured": True,
            "planned_only": True,
            "apply_enabled": False,
            "summary": "SSH/SCP policy is planned only and will not be enabled by this workflow.",
        },
        "save_behavior": {
            "configured": True,
            "enabled": False,
            "summary": "Save behavior is disabled for now; write memory is not allowed.",
        },
        "confirmation_requirements": {
            "configured": False,
            "required": [
                "Confirm selected console path.",
                "Confirm planned management IP, subnet/prefix, gateway, and management strategy.",
                "Confirm hostname, domain, DNS, and local admin username presence.",
                "Review exact future wizard answers or commands before execution.",
                "Require explicit operator approval before sending any answer.",
                "Confirm save behavior remains disabled unless a future workflow explicitly changes it.",
            ],
        },
    }
    blockers = _blockers(requirements)
    warnings = _warnings(management_configured)
    return {
        "provider_id": PROVIDER_ID,
        "status": "needs-input" if blockers else "preview",
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
