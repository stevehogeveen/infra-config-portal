from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Literal

from app.core.config import (
    LAB_ANSIBLE_CONTROL_HOST_IP,
    LAB_CISCO_MANAGEMENT_IP,
    LAB_ESXI_MANAGEMENT_IP,
    LAB_ILO_IP,
    LAB_SERVER_EMBEDDED_NIC_IP,
    LAB_SUBNET_CIDR,
    settings,
)
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.base import ProviderStatus
from app.providers.registry import ProviderRegistryError, provider_registry
from app.services.build_verification import get_lab_build_verification
from app.services.firmware_compliance import get_firmware_compliance
from app.services.lab_profiles import active_lab_profile_for_report

REPO_ROOT = Path(__file__).resolve().parents[4]

Classification = Literal["read-only", "write", "destructive", "upgrade"]


class ControlActionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class ActionInput:
    name: str
    label: str
    required: bool = False
    secret: bool = False
    description: str = ""


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    label: str
    section_id: str
    device_stage: str
    description: str
    classification: Classification
    command: str | None = None
    method: str | None = None
    endpoint: str | None = None
    report: str | None = None
    provider_ids: tuple[str, ...] = ()
    required_inputs: tuple[ActionInput, ...] = ()
    required_flags: tuple[str, ...] = ()
    required_confirmations: tuple[str, ...] = ()
    policy_action_id: str | None = None
    policy_category: ActionCategory | None = None
    direct_run_supported: bool = False
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionDefinition:
    id: str
    title: str
    stage: str
    description: str
    action_ids: tuple[str, ...]
    report_paths: tuple[tuple[str, str], ...] = ()


def get_control_action_catalog() -> dict[str, Any]:
    providers = _provider_statuses()
    policy = current_lab_action_policy()
    firmware = get_firmware_compliance(refresh_live=False, scope="full")
    verification = get_lab_build_verification()
    lab_profile = _control_lab_profile()
    actions = [_action_read(action, providers, policy, lab_profile) for action in ACTIONS]
    action_by_id = {action["id"]: action for action in actions}
    sections = [
        _section_read(section, action_by_id, providers, firmware, verification, lab_profile)
        for section in SECTIONS
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider_mode": settings.provider_mode,
        "summary": {
            "sections": len(sections),
            "actions": len(actions),
            "blocked_actions": len([action for action in actions if action["availability"] == "blocked"]),
            "upgrade_actions": len(
                [action for action in actions if action["classification"] == "upgrade"]
            ),
            "direct_run_enabled": False,
            "safety": (
                "Control Center direct runs are disabled in this pass. Use Plan or copy the "
                "suggested command/API endpoint."
            ),
        },
        "lab_profile": lab_profile,
        "sections": sections,
        "actions": actions,
    }


def plan_control_action(action_id: str) -> dict[str, Any]:
    catalog = get_control_action_catalog()
    action = _find_action(catalog, action_id)
    blockers = _string_list(action.get("blocker"))
    steps = [
        {
            "label": "Review current state",
            "status": "ready",
            "detail": "Use the Control Center current-state block for this device/stage.",
        },
        {
            "label": "Review desired state",
            "status": "ready",
            "detail": "Confirm the target profile and desired configuration before apply paths.",
        },
        {
            "label": "Review blockers and flags",
            "status": "blocked" if blockers else "ready",
            "detail": action.get("blocker") or "No catalog blocker is reported.",
        },
        {
            "label": "Execute through guarded operator path",
            "status": "manual_command_required",
            "detail": "Direct Control Center run is disabled; use the suggested command/API endpoint.",
        },
    ]
    return {
        "action": action,
        "status": "blocked" if blockers else "planned",
        "message": (
            "Action is blocked by current catalog gates."
            if blockers
            else "Action plan is ready for manual guarded execution."
        ),
        "plan_steps": steps,
        "suggested_command": action.get("suggested_command"),
        "api_endpoint": action.get("api_endpoint"),
        "method": action.get("method"),
        "direct_run_enabled": False,
        "warnings": [
            "Direct execution is intentionally disabled in this Control Center pass.",
        ],
        "blockers": blockers,
    }


def run_control_action(action_id: str) -> dict[str, Any]:
    plan = plan_control_action(action_id)
    action = plan["action"]
    blockers = list(plan["blockers"])
    blockers.append(
        "Direct Control Center run is not implemented yet; use the suggested command after "
        "reviewing required flags and confirmations."
    )
    return {
        "action": action,
        "status": "manual_command_required" if len(blockers) == 1 else "blocked",
        "message": "No provider call, command, firmware update, power action, or write was executed.",
        "executed": False,
        "suggested_command": action.get("suggested_command"),
        "api_endpoint": action.get("api_endpoint"),
        "method": action.get("method"),
        "warnings": plan["warnings"],
        "blockers": blockers,
    }


def _find_action(catalog: dict[str, Any], action_id: str) -> dict[str, Any]:
    for action in catalog["actions"]:
        if action["id"] == action_id:
            return action
    raise ControlActionNotFoundError(action_id)


def _provider_statuses() -> dict[str, ProviderStatus]:
    try:
        statuses = provider_registry().statuses()
    except ProviderRegistryError:
        return {}
    return {status.id: status for status in statuses}


def _action_read(
    action: ActionDefinition,
    providers: dict[str, ProviderStatus],
    policy: Any,
    lab_profile: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    if action.section_id == "netapp":
        netapp_blocker = _lab_profile_netapp_blocker(lab_profile)
        if netapp_blocker:
            blockers.append(netapp_blocker)
    for provider_id in action.provider_ids:
        provider = providers.get(provider_id)
        if provider and provider.status in {"blocked", "failed", "unavailable"}:
            blockers.extend(provider.blockers or [provider.message])
    if action.policy_action_id and action.policy_category:
        blockers.extend(policy.action_blockers(action.policy_action_id, action.policy_category))

    if blockers:
        availability = "blocked"
    elif action.direct_run_supported:
        availability = "available"
    else:
        availability = "manual_command_required"

    last_report = action.report
    report_path = REPO_ROOT / last_report if last_report else None
    last_run_status = "report_available" if report_path and report_path.exists() else "not_run"
    last_run_at = (
        datetime.fromtimestamp(report_path.stat().st_mtime, UTC).isoformat()
        if report_path and report_path.exists()
        else None
    )
    return {
        "id": action.id,
        "label": action.label,
        "section_id": action.section_id,
        "device_stage": action.device_stage,
        "description": action.description,
        "classification": action.classification,
        "required_inputs": [
            {
                "name": item.name,
                "label": item.label,
                "required": item.required,
                "secret": item.secret,
                "description": item.description,
            }
            for item in action.required_inputs
        ],
        "required_flags": list(action.required_flags),
        "required_confirmations": list(action.required_confirmations),
        "availability": availability,
        "blocker": "; ".join(dict.fromkeys(blockers)) if blockers else None,
        "last_run_status": last_run_status,
        "last_run_at": last_run_at,
        "last_report": last_report,
        "suggested_command": action.command,
        "method": action.method,
        "api_endpoint": action.endpoint,
        "plan_endpoint": f"/api/v1/control/actions/{action.id}/plan",
        "run_endpoint": f"/api/v1/control/actions/{action.id}/run",
        "direct_run_supported": action.direct_run_supported,
        "diagnostics": list(action.diagnostics),
    }


def _section_read(
    section: SectionDefinition,
    action_by_id: dict[str, dict[str, Any]],
    providers: dict[str, ProviderStatus],
    firmware: dict[str, Any],
    verification: dict[str, Any],
    lab_profile: dict[str, Any],
) -> dict[str, Any]:
    current, desired, diff, diagnostics = _section_state(section.id, providers, firmware, verification, lab_profile)
    actions = [action_by_id[action_id] for action_id in section.action_ids if action_id in action_by_id]
    blocked_actions = [action for action in actions if action["availability"] == "blocked"]
    upgrade_actions = [action for action in actions if action["classification"] == "upgrade"]
    destructive_actions = [action for action in actions if action["classification"] == "destructive"]
    report_links = [
        {
            "label": label,
            "path": path,
            "status": "available" if (REPO_ROOT / path).exists() else "not_run",
        }
        for label, path in section.report_paths
    ]
    report_links.extend(_action_report_links(actions))
    return {
        "id": section.id,
        "title": section.title,
        "stage": section.stage,
        "description": section.description,
        "status": "blocked" if blocked_actions else "ready",
        "current_state": current,
        "desired_state": desired,
        "plan_diff": diff,
        "actions": actions,
        "primary_actions": [action for action in actions if action["classification"] == "read-only"][:4],
        "destructive_actions": destructive_actions,
        "upgrade_actions": upgrade_actions,
        "last_result": _last_result_for_actions(actions),
        "report_links": report_links,
        "advanced_diagnostics": diagnostics,
    }


def _section_state(
    section_id: str,
    providers: dict[str, ProviderStatus],
    firmware: dict[str, Any],
    verification: dict[str, Any],
    lab_profile: dict[str, Any],
) -> tuple[list[dict[str, str | None]], list[dict[str, str | None]], list[dict[str, str | None]], dict[str, Any]]:
    profile = lab_profile["address_plan"]
    known = lab_profile["known_lab_profile"]
    firmware_components = {
        component.get("id"): component
        for component in firmware.get("components", [])
        if isinstance(component, dict)
    }
    if section_id == "lab-profile":
        labels = [
            ("subnet", "Subnet"),
            ("ilo", "iLO"),
            ("server_embedded_nic", "Server NIC"),
            ("esxi_management", "ESXi"),
            ("cisco_management", "Cisco"),
            ("ansible_control_host", "Control Host"),
        ]
        current = [_item(label, _display(profile.get(key))) for key, label in labels]
        desired = [_item(label, known[key]) for key, label in labels]
        diff = [_diff(label, _display(profile.get(key)), known[key]) for key, label in labels]
        current.extend(
            [
                _item("CISCO_MGMT_CONFIGURED", _bool_text(settings.cisco_mgmt_configured)),
                _item("ESXI_CONFIGURED", _bool_text(settings.esxi_configured)),
                _item("NETAPP_CONFIGURED", _bool_text(settings.netapp_configured)),
            ]
        )
        return current, desired, diff, lab_profile

    if section_id == "cisco":
        console = providers.get("cisco-console")
        ansible = providers.get("cisco-ansible")
        discovery = console.discovery if console and console.discovery else {}
        current = [
            _item("Console", console.status if console else "not_loaded"),
            _item("Selected path", _display(discovery.get("effective_path"))),
            _item("Management IP", _display(settings.cisco_target_ip)),
            _item("Management configured", _bool_text(settings.cisco_mgmt_configured)),
            _item("SSH provider", ansible.status if ansible else "not_loaded"),
            _firmware_item("Cisco IOS XE", firmware_components, "cisco_ios_xe_version"),
            _firmware_item("Cisco ROMMON", firmware_components, "cisco_bootloader_rommon"),
        ]
        desired = [
            _item("Management IP", LAB_CISCO_MANAGEMENT_IP),
            _item("Console mode", "console-first discovery and bootstrap"),
            _item("SSH/SCP", "validate only after CISCO_MGMT_CONFIGURED=true"),
        ]
        diff = [_diff("Cisco management IP", _display(settings.cisco_target_ip), LAB_CISCO_MANAGEMENT_IP)]
        return current, desired, diff, _provider_diagnostics([console, ansible])

    if section_id == "ilo":
        provider = providers.get("ilo-redfish")
        discovery = provider.discovery if provider and provider.discovery else {}
        config = provider.configuration if provider else {}
        current = [
            _item("Status", provider.status if provider else "not_loaded"),
            _item("Host configured", _presence(config.get("host_configured"))),
            _item("Username configured", _presence(config.get("username_configured"))),
            _item("Password configured", _presence(config.get("password_configured"))),
            _item("Model", _display(discovery.get("server_model") or discovery.get("model"))),
            _firmware_item("iLO firmware", firmware_components, "hpe_ilo_firmware"),
            _firmware_item("BIOS", firmware_components, "hpe_bios_version"),
        ]
        desired = [
            _item("iLO IP", LAB_ILO_IP),
            _item("Inventory", "authenticated inventory available before apply paths"),
            _item("Virtual media", "gated and planned before ESXi install"),
        ]
        diff = [_diff("iLO IP", _display(profile.get("ilo")), LAB_ILO_IP)]
        return current, desired, diff, _provider_diagnostics([provider])

    if section_id == "raid":
        current = [
            _item("Discovery report", _report_status("artifacts/codex-runs/hpe-raid-discovery-report.md")),
            _item("Plan report", _report_status("artifacts/codex-runs/hpe-raid-plan-report.md")),
            _item("Apply report", _report_status("artifacts/codex-runs/hpe-raid-apply-report.md")),
            _item("Pending report", _report_status("artifacts/codex-runs/hpe-raid-pending-report.md")),
            _item("After reset validation", _report_status("artifacts/codex-runs/hpe-raid-after-reset-validation-report.md")),
        ]
        desired = [
            _item("RAID intent", "saved OS/data layout before apply"),
            _item("Destructive gate", "explicit flags and confirmation before wipe/apply"),
            _item("Validation", "post-reset layout matches saved intent"),
        ]
        diff = [_diff("RAID apply", current[2]["value"], "explicit gated apply")]
        return current, desired, diff, {"reports": current}

    if section_id == "esxi":
        provider = providers.get("esxi-readonly")
        current = [
            _item("Provider status", provider.status if provider else "not_loaded"),
            _item("ESXI_CONFIGURED", _bool_text(settings.esxi_configured)),
            _item("Target IP", _display(settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP)),
            _item("Install readiness", _report_status("artifacts/codex-runs/esxi-install-readiness-report.md")),
            _item("Virtual media", _report_status("artifacts/codex-runs/esxi-virtual-media-report.md")),
            _item("Installer boot", _report_status("artifacts/codex-runs/esxi-installer-boot-report.md")),
        ]
        desired = [
            _item("ESXi IP", LAB_ESXI_MANAGEMENT_IP),
            _item("Media", "ESXi ISO selected and served through guarded workflow"),
            _item("Management", "HTTPS/SSH checks after ESXI_CONFIGURED=true"),
        ]
        diff = [_diff("ESXi IP", _display(profile.get("esxi_management")), LAB_ESXI_MANAGEMENT_IP)]
        return current, desired, diff, _provider_diagnostics([provider])

    if section_id == "netapp":
        provider = providers.get("netapp-ontap")
        config = provider.configuration if provider else {}
        current_targets = config.get("current_discovered_targets")
        current_targets = current_targets if isinstance(current_targets, dict) else {}
        discovery_enabled = current_targets.get("discovery_enabled")
        management_ips = current_targets.get("management_ips")
        management_ips = management_ips if isinstance(management_ips, dict) else {}
        discovered_count = len([value for value in management_ips.values() if value])
        current = [
            _item("Provider status", provider.status if provider else "not_loaded"),
            _item("NETAPP_CONFIGURED", _bool_text(settings.netapp_configured)),
            _item("Cluster management", _display(settings.netapp_cluster_mgmt_ip)),
            _item("Controller A SP", _display(settings.netapp_controller_a_sp)),
            _item("Controller B SP", _display(settings.netapp_controller_b_sp)),
            _item(
                "Current discovery",
                (
                    f"{discovered_count} management targets discovered"
                    if discovery_enabled and discovered_count
                    else "No live NetApp discovery has run"
                ),
            ),
        ]
        desired = [
            _item("Setup readiness", "planned targets remain separate from current discovery"),
            _item("Cluster management", settings.netapp_cluster_mgmt_ip),
            _item("NFS/vCenter", "validate readiness before storage export handoff"),
        ]
        diff = [
            _diff("Cluster management", _display(profile.get("netapp_cluster_mgmt")), settings.netapp_cluster_mgmt_ip)
        ]
        return current, desired, diff, _provider_diagnostics([provider])

    if section_id == "firmware-upgrade":
        current = [
            _firmware_item("iLO firmware", firmware_components, "hpe_ilo_firmware"),
            _firmware_item("BIOS", firmware_components, "hpe_bios_version"),
            _firmware_item("Smart Array", firmware_components, "hpe_smart_array_firmware"),
            _firmware_item("Cisco IOS XE", firmware_components, "cisco_ios_xe_version"),
            _firmware_item("Cisco ROMMON", firmware_components, "cisco_bootloader_rommon"),
            _item("ESXi ISO/version", "Review media inventory"),
            _firmware_item("ONTAP", firmware_components, "netapp_ontap_version"),
            _firmware_item("NetApp disk firmware", firmware_components, "netapp_disk_firmware"),
            _firmware_item("NetApp shelf firmware", firmware_components, "netapp_shelf_firmware"),
            _firmware_item("NetApp SP/BMC firmware", firmware_components, "netapp_sp_bmc_firmware"),
        ]
        desired = [
            _item("Compliance", firmware.get("status", "unknown")),
            _item("Baseline", _display((firmware.get("baseline") or {}).get("path"))),
            _item("Upgrade apply", "placeholder only; no firmware update in this pass"),
        ]
        diff = [
            _diff(
                "Firmware compliance",
                _display(firmware.get("status")),
                "passed, waived, or reviewed warning",
            )
        ]
        return current, desired, diff, firmware

    if section_id == "verification":
        current = [
            _item("Status", _display(verification.get("status"))),
            _item("Certification", _display(verification.get("certification_state"))),
            _item("Checked", _display(verification.get("checked_at"))),
            _item("Top blocker", _display((verification.get("blockers") or [""])[0])),
        ]
        desired = [
            _item("Certification", "all required stages verified"),
            _item("Report", "redacted certification report exported"),
        ]
        diff = [_diff("Certification", _display(verification.get("certification_state")), "passed")]
        return current, desired, diff, verification

    current = [
        _item("Reports available", str(len([action for action in ACTIONS if action.report]))),
        _item("Action catalog", "visible"),
        _item("Direct run", "disabled"),
    ]
    desired = [
        _item("Reports", "linked next to each action"),
        _item("History", "latest report and command handoff visible"),
    ]
    diff = [_diff("Direct run", "disabled", "guarded execution lane in future pass")]
    return current, desired, diff, {"reports": [action.report for action in ACTIONS if action.report]}


def _control_lab_profile() -> dict[str, Any]:
    active = active_lab_profile_for_report()
    address_plan = active["address_plan"]
    global_settings = active.get("global_settings") or {}
    known = {
        "subnet": LAB_SUBNET_CIDR,
        "ilo": LAB_ILO_IP,
        "server_embedded_nic": LAB_SERVER_EMBEDDED_NIC_IP,
        "esxi_management": LAB_ESXI_MANAGEMENT_IP,
        "cisco_management": LAB_CISCO_MANAGEMENT_IP,
        "ansible_control_host": LAB_ANSIBLE_CONTROL_HOST_IP,
        "netapp_controller_a_sp": settings.netapp_controller_a_sp,
        "netapp_controller_b_sp": settings.netapp_controller_b_sp,
        "netapp_cluster_mgmt": settings.netapp_cluster_mgmt_ip,
        "netapp_node_a_mgmt": settings.netapp_node_a_mgmt_ip,
        "netapp_node_b_mgmt": settings.netapp_node_b_mgmt_ip,
        "netapp_svm_mgmt": settings.netapp_svm_mgmt_ip,
        "netapp_iscsi_lifs": list(settings.netapp_iscsi_lifs),
    }
    return {
        "active_profile_name": active["name"],
        "source": active["source"],
        "version": active["version"],
        "global_settings": global_settings,
        "address_plan": address_plan,
        "known_lab_profile": known,
        "network": {
            "vlan_ids": {
                "cisco_management": settings.cisco_management_vlan or "Not set",
            },
            "mtu": os.getenv("LAB_MTU", "Not set"),
            "dns": os.getenv("LAB_DNS_SERVERS")
            or ", ".join(global_settings.get("dns_servers") or [])
            or ", ".join(settings.cisco_dns_servers)
            or "Not set",
            "gateway": global_settings.get("gateway")
            or os.getenv("LAB_GATEWAY")
            or settings.cisco_management_gateway
            or "Not set",
            "ntp": ", ".join(global_settings.get("ntp_servers") or [])
            or os.getenv("LAB_NTP_SERVERS", "Not set"),
        },
        "configured_flags": {
            "CISCO_MGMT_CONFIGURED": settings.cisco_mgmt_configured,
            "ESXI_CONFIGURED": settings.esxi_configured,
            "NETAPP_CONFIGURED": settings.netapp_configured,
            "VCENTER_CONFIGURED": settings.vcenter_configured,
            "LAB_ALLOW_POWER_ACTIONS": settings.lab_allow_power_actions,
            "LAB_ALLOW_FIRMWARE_UPDATES": settings.lab_allow_firmware_updates,
            "LAB_ALLOW_FACTORY_RESET": settings.lab_allow_factory_reset,
        },
        "edit_profile_path": "/lab-profiles",
        "env_update_command": _env_update_command(known),
        "stale_or_invalid_values": _profile_issues(address_plan, known),
    }


def _lab_profile_netapp_blocker(lab_profile: dict[str, Any]) -> str | None:
    global_settings = lab_profile.get("global_settings") or {}
    if global_settings.get("netapp_enabled", True):
        return None
    return global_settings.get("netapp_disabled_reason") or "NetApp is disabled for the active lab profile."


def _env_update_command(known: dict[str, Any]) -> str:
    lines = [
        "cat <<'EOF' >> app/.env.local.real-lab",
        f"LAB_SUBNET_CIDR={known['subnet']}",
        f"ILO_TEST_HOST={known['ilo']}",
        f"SERVER_EMBEDDED_NIC_IP={known['server_embedded_nic']}",
        f"ESXI_TEST_HOST={known['esxi_management']}",
        f"CISCO_TARGET_IP={known['cisco_management']}",
        f"ANSIBLE_CONTROL_HOST={known['ansible_control_host']}",
        f"NETAPP_CONTROLLER_A_SP={known['netapp_controller_a_sp']}",
        f"NETAPP_CONTROLLER_B_SP={known['netapp_controller_b_sp']}",
        f"NETAPP_CLUSTER_MGMT_IP={known['netapp_cluster_mgmt']}",
        f"NETAPP_NODE_A_MGMT_IP={known['netapp_node_a_mgmt']}",
        f"NETAPP_NODE_B_MGMT_IP={known['netapp_node_b_mgmt']}",
        f"NETAPP_SVM_MGMT_IP={known['netapp_svm_mgmt']}",
        f"NETAPP_ISCSI_LIFS={','.join(known['netapp_iscsi_lifs'])}",
        "CISCO_MGMT_CONFIGURED=false",
        "ESXI_CONFIGURED=false",
        "NETAPP_CONFIGURED=false",
        "EOF",
    ]
    return "\n".join(lines)


def _profile_issues(address_plan: dict[str, Any], known: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key, desired in known.items():
        current = address_plan.get(key)
        if key == "netapp_iscsi_lifs":
            continue
        if current in {None, ""}:
            issues.append(f"{key} is not set.")
            continue
        if str(current).startswith("10.10.8."):
            issues.append(f"{key} uses stale 10.10.8.x lab addressing.")
        if key == "subnet":
            try:
                ip_network(str(current), strict=False)
            except ValueError:
                issues.append(f"{key} is not a valid subnet.")
        else:
            try:
                ip_address(str(current))
            except ValueError:
                issues.append(f"{key} is not a valid IP address.")
        if key in {
            "subnet",
            "ilo",
            "server_embedded_nic",
            "esxi_management",
            "cisco_management",
            "ansible_control_host",
        } and str(current) != str(desired):
            issues.append(f"{key} is {current}; expected {desired} for the known lab.")
    return issues


def _action_report_links(actions: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    links = []
    seen: set[str] = set()
    for action in actions:
        path = action.get("last_report")
        if not path or path in seen:
            continue
        seen.add(str(path))
        links.append(
            {
                "label": action["label"],
                "path": str(path),
                "status": action["last_run_status"],
            }
        )
    return links


def _last_result_for_actions(actions: list[dict[str, Any]]) -> dict[str, str | None]:
    available = [action for action in actions if action.get("last_run_status") == "report_available"]
    if available:
        latest = sorted(
            available,
            key=lambda action: str(action.get("last_run_at") or ""),
            reverse=True,
        )[0]
        return {
            "status": "report_available",
            "label": latest["label"],
            "report": latest["last_report"],
            "checked_at": latest["last_run_at"],
        }
    return {
        "status": "not_run",
        "label": None,
        "report": None,
        "checked_at": None,
    }


def _item(label: str, value: Any, status: str | None = None) -> dict[str, str | None]:
    return {
        "label": label,
        "value": _display(value),
        "status": status,
        "detail": None,
    }


def _diff(label: str, current: Any, desired: Any) -> dict[str, str | None]:
    current_text = _display(current)
    desired_text = _display(desired)
    if current_text == desired_text:
        status = "matched"
        note = "Current matches desired."
    elif current_text in {"Not set", "Missing", "None", "not_run"}:
        status = "missing"
        note = "Current value is missing."
    else:
        status = "different"
        note = "Review before apply."
    return {
        "label": label,
        "current": current_text,
        "desired": desired_text,
        "status": status,
        "note": note,
    }


def _firmware_item(
    label: str,
    components: dict[str, dict[str, Any]],
    component_id: str,
) -> dict[str, str | None]:
    component = components.get(component_id, {})
    value = component.get("current_version") or "Unknown"
    return _item(label, value, _display(component.get("status")))


def _provider_diagnostics(providers: list[ProviderStatus | None]) -> dict[str, Any]:
    return {
        provider.id: {
            "status": provider.status,
            "message": provider.message,
            "blockers": provider.blockers,
            "warnings": provider.warnings,
            "configuration": provider.configuration,
            "discovery": provider.discovery,
        }
        for provider in providers
        if provider is not None
    }


def _report_status(path: str) -> str:
    return "report_available" if (REPO_ROOT / path).exists() else "not_run"


def _presence(value: Any) -> str:
    return "Present" if bool(value) else "Missing"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _display(value: Any) -> str:
    if value is None or value == "":
        return "Not set"
    if isinstance(value, bool):
        return _bool_text(value)
    if isinstance(value, dict):
        if not value:
            return "Not set"
        return ", ".join(f"{key}={_display(nested)}" for key, nested in sorted(value.items()))
    if isinstance(value, list | tuple):
        return ", ".join(_display(item) for item in value) or "Not set"
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    text = str(value).strip()
    return [text] if text else []


def _action(
    id: str,
    label: str,
    section_id: str,
    device_stage: str,
    description: str,
    classification: Classification,
    *,
    command: str | None = None,
    method: str | None = None,
    endpoint: str | None = None,
    report: str | None = None,
    provider_ids: tuple[str, ...] = (),
    required_inputs: tuple[ActionInput, ...] = (),
    required_flags: tuple[str, ...] = (),
    required_confirmations: tuple[str, ...] = (),
    policy_action_id: str | None = None,
    policy_category: ActionCategory | None = None,
    diagnostics: tuple[str, ...] = (),
) -> ActionDefinition:
    return ActionDefinition(
        id=id,
        label=label,
        section_id=section_id,
        device_stage=device_stage,
        description=description,
        classification=classification,
        command=command,
        method=method,
        endpoint=endpoint,
        report=report,
        provider_ids=provider_ids,
        required_inputs=required_inputs,
        required_flags=required_flags,
        required_confirmations=required_confirmations,
        policy_action_id=policy_action_id,
        policy_category=policy_category,
        diagnostics=diagnostics,
    )


ACTIONS: tuple[ActionDefinition, ...] = (
    _action(
        "cisco.discover-console",
        "Discover Console",
        "cisco",
        "Cisco Control",
        "Find usable local/TCP console candidates and classify access without sending config.",
        "read-only",
        command="make provider-lab-serial-console-discovery",
        method="POST",
        endpoint="/api/v1/providers/cisco-console/prompt-readiness",
        report="artifacts/codex-runs/serial-console-discovery-report.md",
        provider_ids=("cisco-console",),
        required_flags=("LAB_READONLY_ACK=YES for live probes",),
    ),
    _action(
        "cisco.reclaim-console",
        "Reclaim Cisco Console",
        "cisco",
        "Cisco Control",
        "Operator-controlled console reclaim path for a busy or stale Cisco console.",
        "write",
        command="CISCO_CONSOLE_RECLAIM=true make provider-lab-cisco-console-recovery",
        report="artifacts/codex-runs/cisco-console-recovery-final-report.md",
        provider_ids=("cisco-console",),
        required_flags=("CISCO_CONSOLE_RECLAIM=true",),
        required_confirmations=("RECLAIM CISCO CONSOLE",),
        policy_action_id="cisco-console.bootstrap",
        policy_category=ActionCategory.NETWORK_CONFIG,
    ),
    _action(
        "commander.reclaim-serial-port",
        "Reclaim Serial Port",
        "cisco",
        "Cisco Control",
        "Commander mode control to force serial-port ownership review before console actions.",
        "write",
        command="CISCO_CONSOLE_RECLAIM=true make provider-lab-serial-console-discovery",
        report="artifacts/codex-runs/serial-console-discovery-report.md",
        provider_ids=("cisco-console",),
        required_flags=("CISCO_CONSOLE_RECLAIM=true",),
        required_confirmations=("RECLAIM SERIAL PORT",),
        policy_action_id="cisco-console.bootstrap",
        policy_category=ActionCategory.NETWORK_CONFIG,
    ),
    _action(
        "cisco.privilege-check",
        "Privilege Check",
        "cisco",
        "Cisco Control",
        "Check privileged exec readiness and classify prompt state.",
        "read-only",
        command="make provider-lab-cisco-privilege-check",
        report="artifacts/codex-runs/cisco-privilege-check-report.md",
        provider_ids=("cisco-console", "cisco-ansible"),
    ),
    _action(
        "cisco.firmware-inventory",
        "Cisco Firmware Inventory",
        "cisco",
        "Cisco Control",
        "Collect Cisco IOS XE and ROMMON/bootloader inventory evidence.",
        "read-only",
        command="make provider-lab-firmware-cisco-inventory",
        report="artifacts/codex-runs/cisco-firmware-inventory-report.md",
        provider_ids=("cisco-console", "cisco-ansible"),
    ),
    _action(
        "cisco.apply-bootstrap",
        "Apply Bootstrap",
        "cisco",
        "Cisco Control",
        "Apply guarded console bootstrap once prerequisites and confirmation are present.",
        "write",
        command="make provider-lab-cisco-vlan10-bootstrap-apply",
        method="POST",
        endpoint="/api/v1/providers/cisco/console-bootstrap/apply",
        report="artifacts/codex-runs/cisco-bootstrap-apply-report.md",
        provider_ids=("cisco-console",),
        required_inputs=(
            ActionInput("confirmation_phrase", "Confirmation phrase", True),
        ),
        required_flags=("CISCO_CONSOLE_APPLY_ENABLED=true",),
        required_confirmations=("APPLY CISCO BOOTSTRAP",),
        policy_action_id="cisco-console.bootstrap",
        policy_category=ActionCategory.NETWORK_CONFIG,
    ),
    _action(
        "cisco.validate-ssh-scp",
        "Validate SSH/SCP",
        "cisco",
        "Cisco Control",
        "Validate Cisco management SSH/SCP readiness after console bootstrap.",
        "read-only",
        command="make provider-lab-cisco-console-ethernet-readiness",
        report="artifacts/codex-runs/cisco-console-ethernet-readiness-report.md",
        provider_ids=("cisco-ansible",),
        required_flags=("CISCO_MGMT_CONFIGURED=true",),
    ),
    _action(
        "cisco.save-config",
        "Save Config",
        "cisco",
        "Cisco Control",
        "Future guarded write-memory step after validated bootstrap.",
        "write",
        command="CISCO_SAVE_CONFIG_CONFIRM='SAVE CISCO CONFIG' make provider-lab-cisco-vlan10-bootstrap-apply",
        provider_ids=("cisco-console", "cisco-ansible"),
        required_confirmations=("SAVE CISCO CONFIG",),
        policy_action_id="cisco-console.vlan-management-ssh-scp",
        policy_category=ActionCategory.NETWORK_CONFIG,
    ),
    _action(
        "cisco.reload-if-needed",
        "Reload If Needed",
        "cisco",
        "Cisco Control",
        "Future guarded reload after a plan proves reload is required.",
        "destructive",
        command="CISCO_RELOAD_CONFIRM='RELOAD CISCO IF NEEDED' make provider-lab-cisco-console-recovery",
        provider_ids=("cisco-console",),
        required_flags=("LAB_ALLOW_POWER_ACTIONS=true",),
        required_confirmations=("RELOAD CISCO IF NEEDED",),
        policy_action_id="ilo.power-action",
        policy_category=ActionCategory.POWER_ACTION,
    ),
    _action(
        "ilo.reachability",
        "Reachability",
        "ilo",
        "HPE / iLO Control",
        "Run iLO reachability diagnostics before auth or inventory.",
        "read-only",
        command="make provider-lab-ilo-reachability",
        report="artifacts/codex-runs/ilo-local-lab-test-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "ilo.auth",
        "Auth",
        "ilo",
        "HPE / iLO Control",
        "Validate iLO authentication readiness with redacted credential handling.",
        "read-only",
        command="make provider-lab-ilo-authentication",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "ilo.inventory",
        "Inventory",
        "ilo",
        "HPE / iLO Control",
        "Collect server, manager, firmware, and storage inventory through iLO.",
        "read-only",
        command="make provider-lab-ilo-inventory",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/readiness-summary",
        report="artifacts/codex-runs/ilo-real-run-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "ilo.virtual-media-insert",
        "Virtual Media Insert",
        "ilo",
        "HPE / iLO Control",
        "Insert ESXi ISO virtual media through guarded iLO workflow.",
        "write",
        command="make provider-lab-esxi-insert-virtual-media",
        report="artifacts/codex-runs/esxi-virtual-media-report.md",
        provider_ids=("ilo-redfish",),
        required_confirmations=("INSERT ESXI VIRTUAL MEDIA",),
        policy_action_id="ilo.virtual-media",
        policy_category=ActionCategory.VIRTUAL_MEDIA,
    ),
    _action(
        "ilo.one-time-boot",
        "One-Time Boot",
        "ilo",
        "HPE / iLO Control",
        "Set a one-time boot target for installer media after validation.",
        "write",
        command="make provider-lab-esxi-one-time-boot",
        report="artifacts/codex-runs/esxi-one-time-boot-report.md",
        provider_ids=("ilo-redfish",),
        required_confirmations=("SET ONE TIME ESXI BOOT",),
        policy_action_id="ilo.boot-settings",
        policy_category=ActionCategory.BOOT_CONFIG,
    ),
    _action(
        "ilo.reset-server",
        "Reset Server",
        "ilo",
        "HPE / iLO Control",
        "Guarded server reset for installer boot or RAID commit.",
        "destructive",
        command=(
            "LAB_ALLOW_POWER_ACTIONS=true HPE_RAID_RESET_CONFIRM='RESET SERVER FOR HPE RAID "
            "APPLY' make provider-lab-esxi-reset-installer-boot"
        ),
        report="artifacts/codex-runs/esxi-installer-boot-report.md",
        provider_ids=("ilo-redfish",),
        required_flags=("LAB_ALLOW_POWER_ACTIONS=true",),
        required_confirmations=("RESET SERVER FOR HPE RAID APPLY",),
        policy_action_id="ilo.power-action",
        policy_category=ActionCategory.POWER_ACTION,
    ),
    _action(
        "ilo.firmware-inventory",
        "iLO Firmware Inventory",
        "ilo",
        "HPE / iLO Control",
        "Collect HPE firmware inventory evidence.",
        "read-only",
        command="make provider-lab-firmware-inventory",
        method="GET",
        endpoint="/api/v1/lab/firmware-inventory",
        report="artifacts/codex-runs/firmware-inventory-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "raid.discovery",
        "Discovery",
        "raid",
        "RAID / Storage Control",
        "Collect Smart Array controller and drive inventory.",
        "read-only",
        command="make provider-lab-hpe-storage-discovery",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/hpe-storage-discovery",
        report="artifacts/codex-runs/hpe-raid-discovery-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "raid.plan",
        "Plan",
        "raid",
        "RAID / Storage Control",
        "Build a RAID layout plan from saved desired intent.",
        "read-only",
        command="make provider-lab-hpe-raid-plan",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/hpe-raid-plan-preview",
        report="artifacts/codex-runs/hpe-raid-plan-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "raid.apply",
        "Apply",
        "raid",
        "RAID / Storage Control",
        "Apply a saved RAID plan only after destructive gates are satisfied.",
        "destructive",
        command="HPE_RAID_ALLOW_DESTRUCTIVE=true make provider-lab-hpe-raid-apply",
        method="POST",
        endpoint="/api/v1/providers/ilo-redfish/hpe-raid-apply",
        report="artifacts/codex-runs/hpe-raid-apply-report.md",
        provider_ids=("ilo-redfish",),
        required_flags=("HPE_RAID_ALLOW_DESTRUCTIVE=true",),
        required_confirmations=("APPLY HPE RAID PLAN",),
        policy_action_id="ilo-redfish.hpe-raid-apply",
        policy_category=ActionCategory.STORAGE_CONFIG,
    ),
    _action(
        "raid.pending-check",
        "Pending Check",
        "raid",
        "RAID / Storage Control",
        "Check pending RAID apply/reset state.",
        "read-only",
        command="make -C app provider-lab-hpe-raid-pending",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/hpe-raid-pending",
        report="artifacts/codex-runs/hpe-raid-pending-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "raid.reset-commit",
        "Reset / Commit",
        "raid",
        "RAID / Storage Control",
        "Reset server only when required to commit RAID changes.",
        "destructive",
        command="LAB_ALLOW_POWER_ACTIONS=true HPE_RAID_ALLOW_RESET=true make -C app provider-lab-server-reset-for-raid",
        method="POST",
        endpoint="/api/v1/providers/ilo-redfish/hpe-raid-reset",
        report="artifacts/codex-runs/hpe-raid-reset-report.md",
        provider_ids=("ilo-redfish",),
        required_flags=("LAB_ALLOW_POWER_ACTIONS=true", "HPE_RAID_ALLOW_RESET=true"),
        required_confirmations=("RESET SERVER FOR HPE RAID APPLY",),
        policy_action_id="ilo-redfish.hpe-raid-reset",
        policy_category=ActionCategory.POWER_ACTION,
    ),
    _action(
        "raid.validate",
        "Validate",
        "raid",
        "RAID / Storage Control",
        "Validate post-reset storage layout against saved intent.",
        "read-only",
        command="make provider-lab-hpe-raid-validate-after-reset",
        method="POST",
        endpoint="/api/v1/providers/ilo-redfish/hpe-raid-validate-after-reset",
        report="artifacts/codex-runs/hpe-raid-after-reset-validation-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "esxi.readiness",
        "Readiness",
        "esxi",
        "ESXi Control",
        "Review ESXi install readiness, ISO, virtual media, BIOS, and RAID gates.",
        "read-only",
        command="make provider-lab-esxi-install-readiness",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/esxi-install-readiness",
        report="artifacts/codex-runs/esxi-install-readiness-report.md",
        provider_ids=("ilo-redfish", "esxi-readonly"),
    ),
    _action(
        "esxi.iso-media-check",
        "ISO / Media Check",
        "esxi",
        "ESXi Control",
        "Validate ESXi media URL and local ISO placeholder readiness.",
        "read-only",
        command="make provider-lab-esxi-media-url",
        method="GET",
        endpoint="/api/v1/media-inventory",
        report="artifacts/codex-runs/esxi-media-url-report.md",
        provider_ids=("ilo-redfish",),
    ),
    _action(
        "esxi.kickstart-generation",
        "Kickstart Generation",
        "esxi",
        "ESXi Control",
        "Future generation step for ESXi kickstart content after profile review.",
        "write",
        command="make provider-lab-esxi-install-readiness",
        report="artifacts/codex-runs/esxi-install-readiness-report.md",
        required_confirmations=("GENERATE ESXI KICKSTART",),
        policy_action_id="esxi.install-config",
        policy_category=ActionCategory.APP_STATE_WRITE,
    ),
    _action(
        "esxi.rebuild-install",
        "Rebuild / Install",
        "esxi",
        "ESXi Control",
        "Guarded install workflow after RAID, ISO, virtual media, and boot plan pass.",
        "destructive",
        command="make provider-lab-esxi-reset-installer-boot",
        report="artifacts/codex-runs/esxi-full-rebuild-boot-report.md",
        provider_ids=("ilo-redfish",),
        required_flags=("LAB_ALLOW_POWER_ACTIONS=true",),
        required_confirmations=("REBUILD ESXI HOST",),
        policy_action_id="esxi.install-config",
        policy_category=ActionCategory.OS_INSTALL,
    ),
    _action(
        "esxi.management-validation",
        "Management Validation",
        "esxi",
        "ESXi Control",
        "Validate ESXi management endpoint after install/configuration.",
        "read-only",
        command="make provider-lab-esxi-detect-installer",
        report="artifacts/codex-runs/esxi-management-readiness-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_CONFIGURED=true",),
    ),
    _action(
        "esxi.ssh-api-check",
        "SSH / API Check",
        "esxi",
        "ESXi Control",
        "Run read-only ESXi SSH/API readiness checks after management is configured.",
        "read-only",
        command="make provider-smoke PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=esxi-readonly",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/probe",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_CONFIGURED=true", "LAB_READONLY_ACK=YES"),
    ),
    _action(
        "netapp.console-autodiscovery",
        "Console Autodiscovery",
        "netapp",
        "NetApp Control",
        "Discover NetApp serial console candidates without modifying ONTAP.",
        "read-only",
        command="make provider-lab-netapp-console-autodiscovery",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/console-discovery",
        report="artifacts/codex-runs/netapp-console-autodiscovery-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.console-read-state",
        "Console Watch / Read State",
        "netapp",
        "NetApp Control",
        "Read NetApp console state and classify prompts without writing commands.",
        "read-only",
        command="make provider-lab-netapp-console-read-state",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/console-read-state",
        report="artifacts/codex-runs/netapp-console-state-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.rest-ssh-readiness",
        "REST / SSH Readiness",
        "netapp",
        "NetApp Control",
        "Review ONTAP REST/SSH readiness without treating planned IPs as live.",
        "read-only",
        command="make netapp-real-readiness",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/upgrade-readiness",
        report="artifacts/codex-runs/netapp-real-readiness-report.md",
        provider_ids=("netapp-ontap",),
        required_flags=("NETAPP_CONFIGURED=true for live REST/SSH readiness",),
    ),
    _action(
        "netapp.setup-preview",
        "Setup Preview",
        "netapp",
        "NetApp Control",
        "Preview planned cluster, node, SVM, LIF, and storage setup intent.",
        "read-only",
        command="make netapp-real-readiness",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/plan-preview",
        report="artifacts/codex-runs/netapp-lab-profile-plan-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.nfs-vcenter-readiness",
        "NFS / vCenter Readiness",
        "netapp",
        "NetApp Control",
        "Review NFS datastore and vCenter handoff readiness.",
        "read-only",
        command="make provider-lab-netapp-nfs-vcenter-readiness",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/nfs-vcenter-readiness",
        report="artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "firmware.inventory",
        "Run Inventory",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Collect firmware and package inventory evidence.",
        "read-only",
        command="make provider-lab-firmware-inventory",
        method="GET",
        endpoint="/api/v1/lab/firmware-inventory",
        report="artifacts/codex-runs/firmware-inventory-report.md",
    ),
    _action(
        "firmware.compliance-check",
        "Check Compliance",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Evaluate firmware/software versions against the local real-lab baseline.",
        "read-only",
        command="make provider-lab-firmware-compliance",
        method="GET",
        endpoint="/api/v1/lab/firmware-compliance",
        report="artifacts/codex-runs/firmware-compliance-report.md",
    ),
    _action(
        "firmware.waiver-check",
        "Waiver Check",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Review firmware waiver state and generated waiver report if configured.",
        "read-only",
        command="make provider-lab-firmware-waiver-check",
        method="GET",
        endpoint="/api/v1/lab/firmware-waiver-check",
        report="artifacts/codex-runs/firmware-waiver-report.md",
    ),
    _action(
        "firmware.package-inventory",
        "View Packages",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Review local media/package metadata without exposing filenames or mounting media.",
        "read-only",
        method="GET",
        endpoint="/api/v1/media-inventory",
    ),
    _action(
        "firmware.create-waiver",
        "Create Waiver",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Future local waiver creation path for reviewed firmware exceptions.",
        "write",
        command="make provider-lab-firmware-waiver-check",
        report="artifacts/codex-runs/firmware-waiver-report.md",
        required_inputs=(
            ActionInput("reason", "Waiver reason", True),
            ActionInput("expires", "Waiver expiry", True),
        ),
        required_confirmations=("WAIVE FIRMWARE COMPLIANCE",),
        policy_action_id="ilo-redfish.record-readonly-inventory",
        policy_category=ActionCategory.APP_STATE_WRITE,
    ),
    _action(
        "firmware.upgrade-plan",
        "Plan Upgrade",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Build a staged upgrade plan from inventory, packages, baseline, and waivers.",
        "upgrade",
        command="make provider-lab-firmware-compliance",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/upgrade-readiness",
        report="artifacts/codex-runs/firmware-compliance-gate-final-report.md",
        required_confirmations=("PLAN FIRMWARE UPGRADE",),
    ),
    _action(
        "firmware.upgrade-apply-placeholder",
        "Run Upgrade Placeholder",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Visible disabled placeholder for future firmware/software upgrade execution.",
        "upgrade",
        required_flags=("LAB_ALLOW_FIRMWARE_UPDATES=true",),
        required_confirmations=("RUN FIRMWARE UPGRADE",),
        policy_action_id="ilo.firmware-update",
        policy_category=ActionCategory.FIRMWARE_UPDATE,
    ),
    _action(
        "commander.force-live-discovery",
        "Force Live Discovery",
        "verification",
        "Build Verification",
        "Commander mode control to require fresh provider discovery instead of cached evidence.",
        "read-only",
        command="FORCE_LIVE_DISCOVERY=true make provider-lab-build-verification",
        report="artifacts/codex-runs/build-verification-report.md",
        required_flags=("LAB_READONLY_ACK=YES for real live checks",),
    ),
    _action(
        "commander.ignore-cached-artifact",
        "Ignore Cached Artifact",
        "verification",
        "Build Verification",
        "Commander mode control to ignore stale cached artifacts during verification.",
        "write",
        command="IGNORE_CACHED_ARTIFACT=true make provider-lab-build-verification",
        report="artifacts/codex-runs/build-verification-report.md",
        required_confirmations=("IGNORE CACHED ARTIFACT",),
        policy_action_id="ilo-redfish.record-readonly-inventory",
        policy_category=ActionCategory.APP_STATE_WRITE,
    ),
    _action(
        "commander.run-live-check",
        "Run Live Check",
        "verification",
        "Build Verification",
        "Commander mode control for scoped live readiness checks.",
        "read-only",
        command="RUN_LIVE_CHECK=true make provider-lab-build-verification",
        report="artifacts/codex-runs/build-verification-report.md",
        required_flags=("LAB_READONLY_ACK=YES for real live checks",),
    ),
    _action(
        "build-verification.run-full",
        "Run Full Verification",
        "verification",
        "Build Verification",
        "Run the full product certification and build verification report.",
        "read-only",
        command="make provider-lab-build-verification",
        method="GET",
        endpoint="/api/v1/lab/build-verification",
        report="artifacts/codex-runs/build-verification-report.md",
    ),
    _action(
        "build-verification.run-scoped",
        "Run Scoped Verification",
        "verification",
        "Build Verification",
        "Run a scoped verification pass for a selected device/stage.",
        "read-only",
        command="VERIFY_SCOPE=<stage> make provider-lab-build-verification",
        report="artifacts/codex-runs/build-verification-report.md",
        required_inputs=(ActionInput("scope", "Verification scope", True),),
    ),
    _action(
        "build-verification.export-certification-report",
        "Export Certification Report",
        "verification",
        "Build Verification",
        "Export the redacted certification report and summary artifacts.",
        "read-only",
        command="make provider-lab-build-verification",
        report="artifacts/codex-runs/build-verification-summary-redacted.json",
    ),
)


SECTIONS: tuple[SectionDefinition, ...] = (
    SectionDefinition(
        "lab-profile",
        "Lab Profile",
        "Profile",
        "Active and known lab addressing, configured flags, and non-secret env update handoff.",
        (),
        (("Lab IP profile", "artifacts/codex-runs/lab-ip-profile-update-report.md"),),
    ),
    SectionDefinition(
        "cisco",
        "Cisco Control",
        "Network",
        "Console-first Cisco discovery, bootstrap, SSH/SCP validation, firmware, and recovery.",
        (
            "cisco.discover-console",
            "cisco.reclaim-console",
            "commander.reclaim-serial-port",
            "cisco.privilege-check",
            "cisco.firmware-inventory",
            "cisco.apply-bootstrap",
            "cisco.validate-ssh-scp",
            "cisco.save-config",
            "cisco.reload-if-needed",
        ),
    ),
    SectionDefinition(
        "ilo",
        "HPE / iLO Control",
        "Server Management",
        "iLO reachability, auth, inventory, virtual media, boot, reset, and firmware inventory.",
        (
            "ilo.reachability",
            "ilo.auth",
            "ilo.inventory",
            "ilo.virtual-media-insert",
            "ilo.one-time-boot",
            "ilo.reset-server",
            "ilo.firmware-inventory",
        ),
    ),
    SectionDefinition(
        "raid",
        "RAID / Storage Control",
        "Storage",
        "Smart Array discovery, RAID planning, gated apply, pending state, reset, and validation.",
        (
            "raid.discovery",
            "raid.plan",
            "raid.apply",
            "raid.pending-check",
            "raid.reset-commit",
            "raid.validate",
        ),
    ),
    SectionDefinition(
        "esxi",
        "ESXi Control",
        "Install",
        "ESXi readiness, media, kickstart, rebuild/install, management validation, and SSH/API.",
        (
            "esxi.readiness",
            "esxi.iso-media-check",
            "esxi.kickstart-generation",
            "esxi.rebuild-install",
            "esxi.management-validation",
            "esxi.ssh-api-check",
        ),
    ),
    SectionDefinition(
        "netapp",
        "NetApp Control",
        "ONTAP",
        "NetApp console, REST/SSH readiness, setup preview, and NFS/vCenter readiness.",
        (
            "netapp.console-autodiscovery",
            "netapp.console-read-state",
            "netapp.rest-ssh-readiness",
            "netapp.setup-preview",
            "netapp.nfs-vcenter-readiness",
        ),
    ),
    SectionDefinition(
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Upgrade",
        "Firmware/software inventory, compliance, packages, waivers, and upgrade planning.",
        (
            "firmware.inventory",
            "firmware.compliance-check",
            "firmware.waiver-check",
            "firmware.package-inventory",
            "firmware.create-waiver",
            "firmware.upgrade-plan",
            "firmware.upgrade-apply-placeholder",
        ),
    ),
    SectionDefinition(
        "verification",
        "Build Verification",
        "Verification",
        "Full and scoped verification, commander mode live checks, and certification export.",
        (
            "commander.force-live-discovery",
            "commander.ignore-cached-artifact",
            "commander.run-live-check",
            "build-verification.run-full",
            "build-verification.run-scoped",
            "build-verification.export-certification-report",
        ),
    ),
    SectionDefinition(
        "reports",
        "Action History / Reports",
        "Reports",
        "Latest known action reports, generated artifacts, and command/API handoff.",
        (),
    ),
)
