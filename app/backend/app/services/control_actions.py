from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any, Literal

from app.core.config import LAB_CISCO_MANAGEMENT_IP, settings
from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.providers.base import ProviderStatus
from app.providers.registry import ProviderRegistryError, provider_registry
from app.services.build_verification import get_lab_build_verification
from app.services.control_access import control_access_configs
from app.services.firmware_compliance import get_firmware_compliance, get_firmware_summaries
from app.services.lab_profiles import active_lab_profile_context, active_lab_profile_runtime_env_command

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
    providers = _provider_statuses(lightweight=True)
    policy = current_lab_action_policy()
    firmware = get_firmware_compliance(refresh_live=False, scope="full")
    firmware_summaries = {summary["device_id"]: summary for summary in get_firmware_summaries(compliance=firmware)}
    verification = get_lab_build_verification()
    lab_profile = _control_lab_profile()
    access_configs = control_access_configs(lab_profile)
    actions = [_action_read(action, providers, policy, lab_profile) for action in ACTIONS]
    action_by_id = {action["id"]: action for action in actions}
    sections = [
        _section_read(
            section,
            action_by_id,
            providers,
            firmware,
            firmware_summaries,
            verification,
            lab_profile,
            access_configs,
        )
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


def _provider_statuses(*, lightweight: bool = False) -> dict[str, ProviderStatus]:
    try:
        statuses = provider_registry().statuses(lightweight=lightweight)
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
    diagnostics: list[str] = list(action.diagnostics)
    if action.section_id == "netapp":
        netapp_blocker = _lab_profile_netapp_blocker(lab_profile)
        if netapp_blocker:
            blockers.append(netapp_blocker)
    for provider_id in action.provider_ids:
        provider = providers.get(provider_id)
        if provider and provider.status in {"blocked", "failed", "unavailable"}:
            provider_blockers = provider.blockers or [provider.message]
            if _provider_blocker_is_nonblocking_for_action(action, provider_id):
                diagnostics.extend(str(item) for item in provider_blockers if item)
            else:
                blockers.extend(provider_blockers)
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
        "diagnostics": list(dict.fromkeys(diagnostics)),
    }


def _provider_blocker_is_nonblocking_for_action(action: ActionDefinition, provider_id: str) -> bool:
    return (
        provider_id == "netapp-ontap"
        and action.section_id == "netapp"
        and action.classification == "read-only"
    )


def _section_read(
    section: SectionDefinition,
    action_by_id: dict[str, dict[str, Any]],
    providers: dict[str, ProviderStatus],
    firmware: dict[str, Any],
    firmware_summaries: dict[str, dict[str, Any]],
    verification: dict[str, Any],
    lab_profile: dict[str, Any],
    access_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    current, desired, diff, diagnostics = _section_state(section.id, providers, firmware, verification, lab_profile)
    actions = [action_by_id[action_id] for action_id in section.action_ids if action_id in action_by_id]
    blocked_actions = [action for action in actions if action["availability"] == "blocked"]
    not_in_scope = _section_not_in_scope(section.id, lab_profile)
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
        "status": "not_in_scope" if not_in_scope else "blocked" if blocked_actions else "ready",
        "firmware_summary": _firmware_summary_for_section(section.id, firmware_summaries),
        "current_state": current,
        "desired_state": desired,
        "plan_diff": diff,
        "access_config": access_configs.get(section.id),
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
    features = lab_profile.get("features") or {}
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
                _item("NETAPP_CONFIGURED_LEGACY", _bool_text(settings.netapp_configured)),
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
            _item("Management IP", known["cisco_management"]),
            _item("Console mode", "console-first discovery and bootstrap"),
            _item("SSH/SCP", "validate only after CISCO_MGMT_CONFIGURED=true"),
        ]
        diff = [_diff("Cisco management IP", _display(settings.cisco_target_ip), known["cisco_management"])]
        return current, desired, diff, _provider_diagnostics([console, ansible])

    if section_id == "ilo":
        provider = providers.get("ilo-redfish")
        discovery = provider.discovery if provider and provider.discovery else {}
        config = provider.configuration if provider else {}
        provider_status = provider.status if provider else "not_loaded"
        current = [
            _item("Status", provider_status),
            _item("Host configured", _presence(config.get("host_configured"))),
            _item("Username configured", _presence(config.get("username_configured"))),
            _item("Password configured", _presence(config.get("password_configured"))),
            _item("Model", _display(discovery.get("server_model") or discovery.get("model"))),
            _firmware_item("iLO firmware", firmware_components, "hpe_ilo_firmware"),
            _firmware_item("BIOS", firmware_components, "hpe_bios_version"),
        ]
        if provider and provider_status in {"blocked", "failed", "unavailable"}:
            current.extend(
                [
                    _item(
                        "Firmware live check",
                        provider.message or "iLO inventory did not complete.",
                        "blocked",
                    ),
                    _item(
                        "Firmware next action",
                        (provider.blockers or ["Refresh iLO reachability before firmware inventory."])[0],
                        "blocked",
                    ),
                ]
            )
        desired = [
            _item("iLO IP", known["ilo"]),
            _item("Inventory", "authenticated inventory available before apply paths"),
            _item("Virtual media", "gated and planned before ESXi install"),
        ]
        diff = [_diff("iLO IP", _display(profile.get("ilo")), known["ilo"])]
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
            _item("Target IP", _display(settings.esxi_test_host or known["esxi_management"])),
            _item("Install readiness", _report_status("artifacts/codex-runs/esxi-install-readiness-report.md")),
            _item("Virtual media", _report_status("artifacts/codex-runs/esxi-virtual-media-report.md")),
            _item("Installer boot", _report_status("artifacts/codex-runs/esxi-installer-boot-report.md")),
        ]
        desired = [
            _item("ESXi IP", known["esxi_management"]),
            _item("Media", "ESXi ISO selected and served through guarded workflow"),
            _item("Management", "HTTPS/SSH checks after ESXI_CONFIGURED=true"),
        ]
        diff = [_diff("ESXi IP", _display(profile.get("esxi_management")), known["esxi_management"])]
        return current, desired, diff, _provider_diagnostics([provider])

    if section_id == "netapp":
        if not features.get("netapp_enabled"):
            current = [
                _item("Profile scope", "not_in_scope"),
                _item("Reason", (features.get("netapp_disabled_reason") or "NetApp disabled by active profile")),
            ]
            desired = [_item("NetApp", "Enable in active profile only when this lab includes NetApp.")]
            diff = [_diff("NetApp scope", "not_in_scope", "disabled by active profile")]
            return current, desired, diff, {"not_in_scope": True, "features": features}
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
            _item(
                "Configured state",
                _display(config.get("netapp_configured_source") or "not verified by live check"),
            ),
            _item("Manual env flag", "not required"),
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
        ]
        if features.get("netapp_enabled"):
            current.extend(
                [
                    _firmware_item("ONTAP", firmware_components, "netapp_ontap_version"),
                    _firmware_item("NetApp disk firmware", firmware_components, "netapp_disk_firmware"),
                    _firmware_item("NetApp shelf firmware", firmware_components, "netapp_shelf_firmware"),
                    _firmware_item("NetApp SP/BMC firmware", firmware_components, "netapp_sp_bmc_firmware"),
                ]
            )
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
    context = active_lab_profile_context()
    active = context["active_profile"]
    address_plan = context["resolved_address_plan"]
    global_settings = active.get("global_settings") or {}
    known = dict(address_plan)
    return {
        "active_profile_name": active["name"],
        "source": active["source"],
        "version": active["version"],
        "topology": context["topology"],
        "features": context.get("enabled_features") or {},
        "not_in_scope_stages": context.get("not_in_scope_stages") or [],
        "mismatch_warnings": context.get("mismatch_warnings") or [],
        "fix_guidance": context.get("fix_guidance") or [],
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
            "NETAPP_CONFIGURED_LEGACY": settings.netapp_configured,
            "VCENTER_CONFIGURED": settings.vcenter_configured,
            "LAB_ALLOW_POWER_ACTIONS": settings.lab_allow_power_actions,
            "LAB_ALLOW_FIRMWARE_UPDATES": settings.lab_allow_firmware_updates,
            "LAB_ALLOW_FACTORY_RESET": settings.lab_allow_factory_reset,
        },
        "edit_profile_path": "/lab-setup",
        "env_update_command": active_lab_profile_runtime_env_command(),
        "stale_or_invalid_values": [
            str(item.get("recommended_action") or item)
            for item in context.get("mismatch_warnings") or []
        ] or _profile_issues(address_plan, known),
    }


def _section_not_in_scope(section_id: str, lab_profile: dict[str, Any]) -> bool:
    features = lab_profile.get("features") or {}
    if section_id == "netapp":
        return not bool(features.get("netapp_enabled"))
    return False


def _firmware_summary_for_section(
    section_id: str,
    firmware_summaries: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if section_id in {"cisco", "ilo", "raid", "esxi", "netapp"}:
        return firmware_summaries.get(section_id)
    if section_id == "firmware-upgrade":
        all_paths = [
            path
            for device_id in ("cisco", "ilo", "raid", "esxi", "netapp", "vcenter")
            for path in (firmware_summaries.get(device_id) or {}).get("upgrade_paths", [])
            if isinstance(path, dict)
        ]
        return {
            **(firmware_summaries.get("ilo") or {}),
            "device_id": "firmware-upgrade",
            "label": "Firmware / Software",
            "component_type": "global_firmware_compliance",
            "current_versions": [
                version
                for device_id in ("cisco", "ilo", "raid", "esxi", "netapp")
                for version in (firmware_summaries.get(device_id) or {}).get("current_versions", [])
            ],
            "approved_versions": [
                version
                for device_id in ("cisco", "ilo", "raid", "esxi", "netapp")
                for version in (firmware_summaries.get(device_id) or {}).get("approved_versions", [])
            ][:8],
            "compliance_status": _rollup_firmware_summary_status(firmware_summaries),
            "severity": _rollup_firmware_summary_severity(firmware_summaries),
            "last_scanned": _latest_firmware_summary_scan(firmware_summaries),
            "source_type": "cached_live",
            "freshness": _rollup_firmware_summary_freshness(firmware_summaries),
            "blocker": _rollup_firmware_summary_blocker(firmware_summaries),
            "next_action": "Open device details below or run the global firmware compliance check.",
            "scan_action_id": "firmware.compliance-check",
            "upgrade_center_link": "/firmware",
            "upgrade_paths": all_paths,
            "path_status": _rollup_firmware_summary_path_status(firmware_summaries),
            "target_version": "; ".join(
                str(summary.get("target_version"))
                for summary in firmware_summaries.values()
                if summary.get("target_version")
            ) or None,
            "package_available": any(summary.get("package_available") for summary in firmware_summaries.values()),
            "package_name": next(
                (str(summary.get("package_name")) for summary in firmware_summaries.values() if summary.get("package_name")),
                None,
            ),
            "required_intermediate_versions": list(
                dict.fromkeys(
                    version
                    for summary in firmware_summaries.values()
                    for version in summary.get("required_intermediate_versions", [])
                )
            ),
            "prechecks_required": list(
                dict.fromkeys(
                    check
                    for summary in firmware_summaries.values()
                    for check in summary.get("prechecks_required", [])
                )
            ),
            "reboot_required": any(summary.get("reboot_required") for summary in firmware_summaries.values()),
            "estimated_impact": _rollup_firmware_summary_impact(firmware_summaries),
            "apply_enabled": any(summary.get("apply_enabled") for summary in firmware_summaries.values()),
            "disabled_reason": _rollup_firmware_summary_disabled_reason(firmware_summaries),
            "evidence_artifacts": [
                "artifacts/codex-runs/firmware-inventory-report.md",
                "artifacts/codex-runs/firmware-compliance-report.md",
                "artifacts/codex-runs/firmware-compliance-summary-redacted.json",
            ],
        }
    return None


def _rollup_firmware_summary_status(firmware_summaries: dict[str, dict[str, Any]]) -> str:
    statuses = {str(summary.get("compliance_status")) for summary in firmware_summaries.values()}
    if "needs_upgrade" in statuses:
        return "needs_upgrade"
    if "cannot_verify" in statuses:
        return "cannot_verify"
    if statuses == {"not_configured"}:
        return "not_configured"
    return "current"


def _rollup_firmware_summary_severity(firmware_summaries: dict[str, dict[str, Any]]) -> str:
    severities = {str(summary.get("severity")) for summary in firmware_summaries.values()}
    if "red" in severities:
        return "red"
    if "yellow" in severities:
        return "yellow"
    if severities == {"gray"}:
        return "gray"
    return "green"


def _rollup_firmware_summary_freshness(firmware_summaries: dict[str, dict[str, Any]]) -> str:
    freshness = {str(summary.get("freshness")) for summary in firmware_summaries.values()}
    if "stale" in freshness:
        return "stale"
    if "historical" in freshness:
        return "historical"
    if "not_checked" in freshness and len(freshness) == 1:
        return "not_checked"
    return "live"


def _rollup_firmware_summary_blocker(firmware_summaries: dict[str, dict[str, Any]]) -> str | None:
    for severity in ("red", "yellow", "gray"):
        for summary in firmware_summaries.values():
            if summary.get("severity") == severity and summary.get("blocker"):
                return str(summary["blocker"])
    return None


def _rollup_firmware_summary_path_status(firmware_summaries: dict[str, dict[str, Any]]) -> str:
    statuses = {str(summary.get("path_status") or "unknown") for summary in firmware_summaries.values()}
    for status in ("blocked", "staged", "direct", "unknown", "manual_review"):
        if status in statuses:
            return status
    return "current"


def _rollup_firmware_summary_impact(firmware_summaries: dict[str, dict[str, Any]]) -> str:
    for summary in firmware_summaries.values():
        if summary.get("path_status") != "current" and summary.get("estimated_impact"):
            return str(summary["estimated_impact"])
    return "No upgrade impact expected while current."


def _rollup_firmware_summary_disabled_reason(firmware_summaries: dict[str, dict[str, Any]]) -> str:
    for summary in firmware_summaries.values():
        if summary.get("path_status") != "current" and summary.get("disabled_reason"):
            return str(summary["disabled_reason"])
    return "No upgrade is needed; apply stays disabled."


def _latest_firmware_summary_scan(firmware_summaries: dict[str, dict[str, Any]]) -> str | None:
    scans = [str(summary["last_scanned"]) for summary in firmware_summaries.values() if summary.get("last_scanned")]
    return sorted(scans, reverse=True)[0] if scans else None


def _lab_profile_netapp_blocker(lab_profile: dict[str, Any]) -> str | None:
    features = lab_profile.get("features") or {}
    if features.get("netapp_enabled", True):
        return None
    return features.get("netapp_disabled_reason") or "NetApp is disabled for the active lab profile."


def _profile_issues(address_plan: dict[str, Any], known: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for key, desired in known.items():
        current = address_plan.get(key)
        if key in {"netapp_iscsi_lifs", "netapp_nfs_lifs"}:
            continue
        if current is None or current == "":
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
        report="artifacts/codex-runs/cisco-privileged-exec-fix-report.md",
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
        required_flags=(
            "CISCO_CONSOLE_APPLY_ENABLED=true",
            "LAB_APPLY_ACK=YES",
            f"LAB_TARGET_ACK={LAB_CISCO_MANAGEMENT_IP}",
        ),
        required_confirmations=(f"APPLY CISCO CONSOLE BOOTSTRAP {LAB_CISCO_MANAGEMENT_IP}",),
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
        "ilo.baseline-preview",
        "Baseline Preview",
        "ilo",
        "HPE / iLO Control",
        "Preview the standard iLO baseline from the active kit profile without applying settings.",
        "read-only",
        method="GET",
        endpoint="/api/v1/providers/hpe-ilo/baseline-preview",
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
        command="make provider-lab-hpe-firmware-inventory",
        method="POST",
        endpoint="/api/v1/lab/firmware-inventory/refresh",
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
        "esxi.recover-management",
        "Recover Management",
        "esxi",
        "ESXi Control",
        "Diagnose ESXi reachability and run the guarded iLO power-on recovery path only when gates pass.",
        "destructive",
        command="make provider-lab-esxi-recover-management",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/recover-management",
        report="artifacts/codex-runs/esxi-reachability-remediation-report.md",
        provider_ids=("ilo-redfish", "esxi-readonly"),
        required_flags=("LAB_ALLOW_POWER_ACTIONS=true", "ESXI_RECOVERY_APPLY=true"),
        required_confirmations=("RECOVER ESXI MANAGEMENT",),
        policy_action_id="ilo.power-action",
        policy_category=ActionCategory.POWER_ACTION,
    ),
    _action(
        "esxi.post-recovery-validation",
        "Post-Recovery Validation",
        "esxi",
        "ESXi Control",
        "Validate ESXi management reachability after a recovery attempt.",
        "read-only",
        command="make provider-lab-esxi-post-recovery-validation",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/post-recovery-validation",
        report="artifacts/codex-runs/esxi-post-recovery-validation-report.md",
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
        "esxi.netapp-datastore-preview",
        "Mount NetApp Datastore Preview",
        "esxi",
        "ESXi Control",
        "Preview the direct ESXi NetApp NFS datastore mount target and govc command.",
        "read-only",
        command="make provider-lab-esxi-netapp-datastore-preview",
        method="GET",
        endpoint="/api/v1/providers/esxi-readonly/netapp-datastore-preview",
        report="artifacts/codex-runs/esxi-netapp-nfs-datastore-preview-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_CONFIGURED=true",),
    ),
    _action(
        "esxi.netapp-datastore-apply",
        "Mount NetApp Datastore",
        "esxi",
        "ESXi Control",
        "Guarded direct ESXi govc datastore.create path for the NetApp NFS datastore.",
        "write",
        command="make provider-lab-esxi-netapp-datastore-apply",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/netapp-datastore-apply",
        report="artifacts/codex-runs/esxi-netapp-nfs-datastore-apply-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_NETAPP_DATASTORE_APPLY=true",),
        required_confirmations=("MOUNT NETAPP NFS DATASTORE",),
        policy_action_id="esxi.datastore-vswitch-vmkernel",
        policy_category=ActionCategory.STORAGE_CONFIG,
    ),
    _action(
        "esxi.netapp-datastore-validate",
        "Validate NetApp Datastore",
        "esxi",
        "ESXi Control",
        "Validate the NetApp NFS datastore is visible and accessible to ESXi.",
        "read-only",
        command="make provider-lab-esxi-netapp-datastore-validate",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/netapp-datastore-validate",
        report="artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_CONFIGURED=true",),
    ),
    _action(
        "esxi.vm-deploy-preview",
        "VM Deploy Preview",
        "esxi",
        "ESXi Control",
        "Preview direct ESXi OVF deployment, datastore placement, and govc command shape without importing a VM.",
        "read-only",
        command="make provider-lab-esxi-vm-deploy-preview",
        method="GET",
        endpoint="/api/v1/providers/esxi-readonly/vm-deploy-preview",
        report="artifacts/codex-runs/esxi-vm-deploy-preview-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_CONFIGURED=true",),
    ),
    _action(
        "esxi.vm-deploy-apply",
        "VM Deploy to Selected Datastore",
        "esxi",
        "ESXi Control",
        "Guarded direct ESXi govc import.ovf lane with explicit datastore and power-on gates.",
        "write",
        command="make provider-lab-esxi-vm-deploy-apply",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/vm-deploy-apply",
        report="artifacts/codex-runs/esxi-vm-deploy-apply-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("VM_DEPLOY_APPLY=true", "VM_DEPLOY_ALLOW_CREATE=true"),
        required_confirmations=("DEPLOY ESXI OVF VM",),
        policy_action_id="vm.deploy-ovf",
        policy_category=ActionCategory.VM_DEPLOY,
    ),
    _action(
        "esxi.vm-deploy-validate",
        "VM Deploy Validate",
        "esxi",
        "ESXi Control",
        "Validate direct ESXi VM and datastore visibility with read-only govc checks.",
        "read-only",
        command="make provider-lab-esxi-vm-deploy-validate",
        method="POST",
        endpoint="/api/v1/providers/esxi-readonly/vm-deploy-validate",
        report="artifacts/codex-runs/esxi-vm-deploy-validation-report.md",
        provider_ids=("esxi-readonly",),
        required_flags=("ESXI_CONFIGURED=true",),
    ),
    _action(
        "netapp.console-autodiscovery",
        "Discover NetApp Console",
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
        "netapp.console-login-state",
        "Login / Read-Only State",
        "netapp",
        "NetApp Control",
        "Identify NetApp login or ONTAP shell state and run fixed read-only commands only after a shell is detected.",
        "read-only",
        command="make provider-lab-netapp-console-login-state",
        report="artifacts/codex-runs/netapp-console-login-state-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.live-state",
        "Read NetApp State",
        "netapp",
        "NetApp Control",
        "Read live NetApp state and persist the redacted result without applying changes.",
        "read-only",
        command="make provider-lab-netapp-live-state",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/live-state",
        report="artifacts/codex-runs/netapp-live-state-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.validate-setup",
        "Validate NetApp Setup",
        "netapp",
        "NetApp Control",
        "Mark NetApp configured only after live validation succeeds.",
        "read-only",
        command="make provider-lab-netapp-validate-setup",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/validate-setup",
        report="artifacts/codex-runs/netapp-live-state-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.address-plan",
        "Address Plan",
        "netapp",
        "NetApp Control",
        "Compare console-discovered ONTAP addresses with the active lab profile and show the safe readdress/profile-update path.",
        "read-only",
        command="make provider-lab-netapp-address-plan",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/address-plan",
        report="artifacts/codex-runs/netapp-address-remediation-plan-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.address-preview",
        "Readdress Preview",
        "netapp",
        "NetApp Control",
        "Preview exact console-mediated ONTAP address changes from the discovered 10.10.8.x state to the active 192.168.1.x lab plan.",
        "read-only",
        command="make provider-lab-netapp-address-preview",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/address-preview",
        report="artifacts/codex-runs/netapp-address-remediation-preview-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.address-apply",
        "Readdress Apply",
        "netapp",
        "NetApp Control",
        "Guarded console-mediated ONTAP network readdress; refused unless fresh target checks and exact confirmation gates pass.",
        "write",
        command="make provider-lab-netapp-address-apply",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/address-apply",
        report="artifacts/codex-runs/netapp-address-remediation-apply-report.md",
        provider_ids=("netapp-ontap",),
        required_flags=(
            "NETAPP_ADDRESS_APPLY=true",
            "NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES=true",
            "NETAPP_ADDRESS_ACCEPT_HA_WARNING=true",
        ),
        required_confirmations=("APPLY NETAPP ADDRESS REMEDIATION",),
        policy_action_id="netapp.address-remediation",
        policy_category=ActionCategory.NETWORK_CONFIG,
    ),
    _action(
        "netapp.address-validate",
        "Readdress Validate",
        "netapp",
        "NetApp Control",
        "Validate planned NetApp management and NFS addresses after a readdress attempt.",
        "read-only",
        command="make provider-lab-netapp-address-validate",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/address-validate",
        report="artifacts/codex-runs/netapp-address-remediation-validation-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.ha-node-diagnose",
        "HA / Node Diagnose",
        "netapp",
        "NetApp Control",
        "Collect read-only HA/node evidence and show the exact X20-01 blocker instead of a generic NetApp failure.",
        "read-only",
        command="make provider-lab-netapp-ha-node-diagnose",
        report="artifacts/codex-runs/netapp-ha-node-remediation-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.factory-reset-preview",
        "Factory Reset Preview",
        "netapp",
        "NetApp Control",
        "Preview the destructive NetApp reset/rebuild recovery path and show exactly what would be reset.",
        "read-only",
        command="make provider-lab-netapp-factory-reset-preview",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/factory-reset-preview",
        report="artifacts/codex-runs/netapp-factory-reset-plan-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.factory-reset-apply",
        "Factory Reset Apply",
        "netapp",
        "NetApp Control",
        "Destructive NetApp factory-reset lane; refused unless factory-reset gates and executor availability are explicit.",
        "destructive",
        command="make provider-lab-netapp-factory-reset-apply",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/factory-reset-apply",
        report="artifacts/codex-runs/netapp-factory-reset-apply-report.md",
        provider_ids=("netapp-ontap",),
        required_flags=("LAB_ALLOW_FACTORY_RESET=true", "NETAPP_FACTORY_RESET_APPLY=true"),
        required_confirmations=("FACTORY RESET NETAPP",),
        policy_action_id="netapp.factory-reset",
        policy_category=ActionCategory.FACTORY_RESET,
    ),
    _action(
        "netapp.factory-reset-validate",
        "Factory Reset Validate",
        "netapp",
        "NetApp Control",
        "Validate whether NetApp is back at setup wizard state after a reset.",
        "read-only",
        command="make provider-lab-netapp-factory-reset-validate",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/factory-reset-validate",
        report="artifacts/codex-runs/netapp-factory-reset-validation-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.setup-preview",
        "Setup Preview",
        "netapp",
        "NetApp Control",
        "Preview planned cluster, node, SVM, LIF, and storage setup intent.",
        "read-only",
        command="make provider-lab-netapp-setup-preview",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/setup-preview",
        report="artifacts/codex-runs/netapp-setup-preview-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.setup-apply",
        "Setup Apply",
        "netapp",
        "NetApp Control",
        "Guarded write-capable cluster setup path; refused unless explicit apply flags and intent gates pass.",
        "write",
        command="make provider-lab-netapp-setup-apply",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/setup-apply",
        report="artifacts/codex-runs/netapp-cluster-setup-apply-report.md",
        provider_ids=("netapp-ontap",),
        required_flags=("NETAPP_SETUP_APPLY=true", "NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true"),
        required_confirmations=("APPLY NETAPP CLUSTER SETUP",),
        policy_action_id="netapp.initial-setup",
        policy_category=ActionCategory.STORAGE_CONFIG,
    ),
    _action(
        "netapp.post-setup-validation",
        "Post-Setup Validation",
        "netapp",
        "NetApp Control",
        "Validate cluster management and storage readiness after a guarded setup run.",
        "read-only",
        command="make provider-lab-netapp-post-setup-validation",
        report="artifacts/codex-runs/netapp-post-setup-validation-report.md",
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
        "netapp.nfs-setup-preview",
        "NFS Setup Preview",
        "netapp",
        "NetApp Control",
        "Preview SVM, NFS service, LIF, volume, export policy, and datastore backing setup.",
        "read-only",
        command="make provider-lab-netapp-nfs-setup-preview",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/nfs-setup-preview",
        report="artifacts/codex-runs/netapp-nfs-setup-preview-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.nfs-setup-apply",
        "NFS Setup Apply",
        "netapp",
        "NetApp Control",
        "Guarded NFS setup apply path; refused unless ONTAP setup, access, and exact NFS setup gates pass.",
        "write",
        command="make provider-lab-netapp-nfs-setup-apply",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/nfs-setup-apply",
        report="artifacts/codex-runs/netapp-nfs-setup-apply-report.md",
        provider_ids=("netapp-ontap",),
        required_flags=("NETAPP_NFS_SETUP_APPLY=true", "NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true"),
        required_confirmations=("APPLY NETAPP NFS SETUP",),
        policy_action_id="netapp.nfs-setup",
        policy_category=ActionCategory.STORAGE_CONFIG,
    ),
    _action(
        "netapp.nfs-setup-validate",
        "Validate NFS Setup",
        "netapp",
        "NetApp Control",
        "Validate NFS setup readiness with read-only NetApp, NFS, ESXi, and vCenter checks.",
        "read-only",
        command="make provider-lab-netapp-nfs-setup-validate",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/nfs-setup-validate",
        report="artifacts/codex-runs/netapp-nfs-setup-validation-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.ontap-upgrade-inventory",
        "ONTAP Upgrade Inventory",
        "netapp",
        "NetApp Control",
        "Inventory current ONTAP state, local image packages, and component firmware readiness.",
        "read-only",
        command="make provider-lab-netapp-ontap-upgrade-inventory",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/inventory",
        report="artifacts/codex-runs/netapp-upgrade-inventory-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.ontap-upgrade-plan",
        "ONTAP Upgrade Plan",
        "netapp",
        "NetApp Control",
        "Plan target ONTAP version, selected package, validation, blockers, and progress commands.",
        "read-only",
        command="make provider-lab-netapp-ontap-upgrade-plan",
        method="GET",
        endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/plan",
        report="artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.ontap-upgrade-validate",
        "Validate ONTAP Upgrade",
        "netapp",
        "NetApp Control",
        "Run pre-upgrade validation gates before the ONTAP upgrade button can become ready.",
        "read-only",
        command="make provider-lab-netapp-ontap-upgrade-validate",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/validate",
        report="artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "netapp.ontap-upgrade-apply",
        "Upgrade ONTAP",
        "netapp",
        "NetApp Control",
        "Guarded ONTAP upgrade path; refused unless setup, image, validation, and exact confirmation gates pass.",
        "upgrade",
        command="make provider-lab-netapp-ontap-upgrade-apply",
        method="POST",
        endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/apply",
        report="artifacts/codex-runs/netapp-ontap-upgrade-apply-report.md",
        provider_ids=("netapp-ontap",),
        required_flags=("NETAPP_ONTAP_UPGRADE_APPLY=true",),
        required_confirmations=("UPGRADE ONTAP",),
        policy_action_id="netapp.ontap-upgrade",
        policy_category=ActionCategory.FIRMWARE_UPDATE,
    ),
    _action(
        "netapp.component-firmware-inventory",
        "Component Firmware Inventory",
        "netapp",
        "NetApp Control",
        "Report SP/BMC, disk, and shelf firmware inventory readiness when ONTAP access is available.",
        "read-only",
        command="make provider-lab-netapp-ontap-upgrade-inventory",
        report="artifacts/codex-runs/netapp-upgrade-inventory-report.md",
        provider_ids=("netapp-ontap",),
    ),
    _action(
        "vcenter.install-readiness",
        "Install Readiness",
        "vcenter",
        "vCenter Control",
        "Evaluate VCSA media, ESXi reachability, NetApp datastore prerequisites, and missing vCenter values.",
        "read-only",
        command="make provider-lab-vcenter-install-readiness",
        method="GET",
        endpoint="/api/v1/lab/vcenter/install-readiness",
        report="artifacts/codex-runs/vcenter-install-readiness-report.md",
        provider_ids=("esxi-readonly", "netapp-ontap"),
    ),
    _action(
        "vcenter.install-plan",
        "Install Plan",
        "vcenter",
        "vCenter Control",
        "Build the preview-only VCSA deployment plan after ESXi and NetApp datastore prerequisites are ready.",
        "read-only",
        command="make provider-lab-vcenter-install-plan",
        method="GET",
        endpoint="/api/v1/lab/vcenter/install-plan",
        report="artifacts/codex-runs/vcenter-install-plan-report.md",
        provider_ids=("esxi-readonly", "netapp-ontap"),
    ),
    _action(
        "vcenter.install-preview",
        "Preview Deploy",
        "vcenter",
        "vCenter Control",
        "Generate the redacted VCSA deploy preview without starting deployment.",
        "read-only",
        command="make provider-lab-vcenter-install-preview",
        method="GET",
        endpoint="/api/v1/lab/vcenter/install-preview",
        report="artifacts/codex-runs/vcenter-install-preview-report.md",
        provider_ids=("esxi-readonly", "netapp-ontap"),
    ),
    _action(
        "vcenter.install-apply",
        "Deploy vCenter",
        "vcenter",
        "vCenter Control",
        "Run the guarded vcsa-deploy install workflow after readiness and preview are ready.",
        "write",
        command="make provider-lab-vcenter-install-apply",
        method="POST",
        endpoint="/api/v1/lab/vcenter/install-apply",
        report="artifacts/codex-runs/vcenter-install-apply-report.md",
        provider_ids=("esxi-readonly", "netapp-ontap", "vcenter"),
        required_flags=("VCENTER_INSTALL_APPLY=true", "VCENTER_INSTALL_ALLOW_DEPLOY=true"),
        required_confirmations=("DEPLOY VCENTER",),
        policy_action_id="vcenter.vcsa-deploy",
        policy_category=ActionCategory.VM_DEPLOY,
    ),
    _action(
        "vcenter.attach-esxi-preview",
        "Attach ESXi Preview",
        "vcenter",
        "vCenter Control",
        "Preview datacenter, cluster, ESXi host attach, datastore visibility, and VM inventory validation without writing to vCenter.",
        "read-only",
        command="make provider-lab-vcenter-attach-esxi-preview",
        method="GET",
        endpoint="/api/v1/lab/vcenter/attach-esxi-preview",
        report="artifacts/codex-runs/vcenter-attach-esxi-preview-report.md",
        provider_ids=("esxi-readonly", "vcenter"),
    ),
    _action(
        "vcenter.attach-esxi-apply",
        "Attach ESXi to vCenter",
        "vcenter",
        "vCenter Control",
        "Run the guarded govc datacenter/cluster ensure and ESXi host attach workflow.",
        "write",
        command="make provider-lab-vcenter-attach-esxi-apply",
        method="POST",
        endpoint="/api/v1/lab/vcenter/attach-esxi-apply",
        report="artifacts/codex-runs/vcenter-attach-esxi-apply-report.md",
        provider_ids=("esxi-readonly", "vcenter"),
        required_flags=("VCENTER_ATTACH_ESXI_APPLY=true", "VCENTER_ATTACH_ESXI_ALLOW=true"),
        required_confirmations=("ATTACH ESXI TO VCENTER",),
        policy_action_id="vcenter.attach-esxi",
        policy_category=ActionCategory.VM_DEPLOY,
    ),
    _action(
        "vcenter.post-attach-validation",
        "Post-Attach Validation",
        "vcenter",
        "vCenter Control",
        "Validate vCenter datacenter, cluster, ESXi host, NetApp datastore, and VM inventory visibility.",
        "read-only",
        command="make provider-lab-vcenter-post-attach-validation",
        method="GET",
        endpoint="/api/v1/lab/vcenter/post-attach-validation",
        report="artifacts/codex-runs/vcenter-post-attach-validation-report.md",
        provider_ids=("vcenter",),
    ),
    _action(
        "vcenter.netapp-readiness",
        "NetApp Readiness",
        "vcenter",
        "vCenter Control",
        "Review vCenter, govc, ESXi management, and NetApp NFS readiness for datastore use.",
        "read-only",
        command="make provider-lab-vcenter-netapp-readiness",
        method="GET",
        endpoint="/api/v1/lab/vcenter-netapp/readiness",
        report="artifacts/codex-runs/vcenter-netapp-readiness-report.md",
        provider_ids=("esxi-readonly", "netapp-ontap"),
    ),
    _action(
        "vcenter.netapp-datastore-plan",
        "NetApp Datastore Plan",
        "vcenter",
        "vCenter Control",
        "Generate the preview-only NetApp NFS datastore add plan for vCenter/ESXi.",
        "read-only",
        command="make provider-lab-vcenter-netapp-datastore-plan",
        method="GET",
        endpoint="/api/v1/lab/vcenter-netapp/datastore-plan",
        report="artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md",
        provider_ids=("esxi-readonly", "netapp-ontap"),
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
        "read-only",
        command="make provider-lab-hpe-firmware-upgrade-plan",
        method="GET",
        endpoint="/api/v1/providers/ilo-redfish/upgrade-readiness",
        report="artifacts/codex-runs/hpe-firmware-upgrade-plan-report.md",
    ),
    _action(
        "firmware.hpe-upgrade-apply",
        "Run HPE Firmware Upgrade",
        "firmware-upgrade",
        "Firmware / Upgrade Center",
        "Run the guarded HPE firmware upgrade lane after live inventory, package selection, and explicit apply gates.",
        "upgrade",
        command="make provider-lab-hpe-firmware-upgrade-apply",
        report="artifacts/codex-runs/hpe-firmware-upgrade-apply-report.md",
        required_flags=("LAB_ALLOW_FIRMWARE_UPDATES=true", "HPE_FIRMWARE_APPLY=true"),
        required_confirmations=("run",),
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
        "Lab Setup",
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
            "ilo.baseline-preview",
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
            "esxi.recover-management",
            "esxi.post-recovery-validation",
            "esxi.ssh-api-check",
            "esxi.netapp-datastore-preview",
            "esxi.netapp-datastore-apply",
            "esxi.netapp-datastore-validate",
            "esxi.vm-deploy-preview",
            "esxi.vm-deploy-apply",
            "esxi.vm-deploy-validate",
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
            "netapp.live-state",
            "netapp.validate-setup",
            "netapp.address-plan",
            "netapp.address-preview",
            "netapp.address-apply",
            "netapp.address-validate",
            "netapp.ha-node-diagnose",
            "netapp.factory-reset-preview",
            "netapp.factory-reset-apply",
            "netapp.factory-reset-validate",
            "netapp.setup-preview",
            "netapp.setup-apply",
            "netapp.post-setup-validation",
            "netapp.nfs-vcenter-readiness",
            "netapp.nfs-setup-preview",
            "netapp.nfs-setup-apply",
            "netapp.nfs-setup-validate",
            "netapp.ontap-upgrade-inventory",
            "netapp.ontap-upgrade-plan",
            "netapp.ontap-upgrade-validate",
            "netapp.ontap-upgrade-apply",
            "netapp.component-firmware-inventory",
        ),
    ),
    SectionDefinition(
        "vcenter",
        "vCenter Control",
        "vCenter",
        "vCenter install readiness, VCSA media, NetApp datastore handoff, and deployment planning.",
        (
            "vcenter.install-readiness",
            "vcenter.install-plan",
            "vcenter.install-preview",
            "vcenter.install-apply",
            "vcenter.attach-esxi-preview",
            "vcenter.attach-esxi-apply",
            "vcenter.post-attach-validation",
            "vcenter.netapp-readiness",
            "vcenter.netapp-datastore-plan",
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
            "firmware.hpe-upgrade-apply",
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
