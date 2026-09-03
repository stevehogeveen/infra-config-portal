from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.probe_cache import get_probe_result
from app.providers.redaction import redact_sensitive
from app.services.media_inventory import get_media_inventory
from app.services.netapp_real_lab import latest_console_ontap_version
from app.services.netapp_state import get_netapp_runtime_state
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.path_utils import path_exists, path_mtime, repo_relative_path, safe_read_text
from app.services.status_source import attach_status_source
from app.services.temp_file_utils import remove_file_best_effort

REPO_ROOT = Path(__file__).resolve().parents[4]
BASELINE_PATH = REPO_ROOT / "config" / "firmware-baselines" / "real-lab.yml"
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
INVENTORY_REPORT = CODEX_RUN_DIR / "firmware-inventory-report.md"
COMPLIANCE_REPORT = CODEX_RUN_DIR / "firmware-compliance-report.md"
COMPLIANCE_SUMMARY = CODEX_RUN_DIR / "firmware-compliance-summary-redacted.json"
WAIVER_REPORT = CODEX_RUN_DIR / "firmware-waiver-report.md"
LOCAL_WAIVER_PATH = CODEX_RUN_DIR / "firmware-waiver.json"
CISCO_FIRMWARE_INVENTORY_REPORT = CODEX_RUN_DIR / "cisco-firmware-inventory-report.md"
ESXI_MANAGEMENT_VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-management-validation-report.md"
VCENTER_NETAPP_READINESS_REPORT = CODEX_RUN_DIR / "vcenter-netapp-readiness-report.md"
ESXI_POST_RECOVERY_VALIDATION_JSON = CODEX_RUN_DIR / "esxi-post-recovery-validation-redacted.json"
NETAPP_ONTAP_UPGRADE_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-ontap-upgrade-validation-redacted.json"
NETAPP_ONTAP_UPGRADE_PLAN_JSON = CODEX_RUN_DIR / "netapp-ontap-upgrade-plan-redacted.json"
VCENTER_POST_INSTALL_VALIDATION_JSON = CODEX_RUN_DIR / "vcenter-post-install-validation-redacted.json"
VCENTER_POST_ATTACH_VALIDATION_JSON = CODEX_RUN_DIR / "vcenter-post-attach-validation-redacted.json"

BLOCKING_STATUSES = {"blocked", "unknown"}
VALID_STATUSES = {"passed", "blocked", "warning", "not_configured_yet", "unknown", "waived"}
VALID_SCOPES = {"hpe", "cisco", "netapp", "full"}
FIRMWARE_SUMMARY_STALE_AFTER_SECONDS = 24 * 60 * 60
SCOPE_COMPONENT_PREFIXES = {
    "hpe": ("hpe_",),
    "cisco": ("cisco_",),
    "netapp": ("netapp_",),
    "full": ("hpe_", "cisco_", "netapp_"),
}
SUMMARY_COMPONENTS = {
    "cisco": ("cisco_ios_xe_version", "cisco_bootloader_rommon"),
    "ilo": ("hpe_ilo_firmware", "hpe_bios_version"),
    "raid": ("hpe_smart_array_firmware",),
    "netapp": ("netapp_ontap_version", "netapp_disk_firmware", "netapp_shelf_firmware", "netapp_sp_bmc_firmware"),
}
SUMMARY_LABELS = {
    "cisco": "Cisco",
    "ilo": "iLO / HPE",
    "raid": "RAID / Smart Array",
    "esxi": "ESXi",
    "netapp": "NetApp",
    "vcenter": "vCenter",
}
SUMMARY_COMPONENT_TYPES = {
    "cisco": "network_os",
    "ilo": "management_firmware",
    "raid": "storage_controller_firmware",
    "esxi": "hypervisor",
    "netapp": "storage_os_and_component_firmware",
    "vcenter": "management_software",
}
SUMMARY_SCAN_ACTIONS = {
    "cisco": "cisco.firmware-inventory",
    "ilo": "ilo.firmware-inventory",
    "raid": "ilo.firmware-inventory",
    "esxi": "esxi.management-validation",
    "netapp": "netapp.ontap-upgrade-inventory",
    "vcenter": "vcenter-netapp.readiness",
}
SUMMARY_EVIDENCE_ARTIFACTS = {
    "cisco": (
        "artifacts/codex-runs/cisco-firmware-inventory-report.md",
        "artifacts/codex-runs/firmware-compliance-report.md",
    ),
    "ilo": (
        "artifacts/codex-runs/firmware-inventory-report.md",
        "artifacts/codex-runs/firmware-compliance-report.md",
    ),
    "raid": (
        "artifacts/codex-runs/firmware-inventory-report.md",
        "artifacts/codex-runs/firmware-compliance-report.md",
        "artifacts/codex-runs/hpe-raid-discovery-report.md",
    ),
    "esxi": (
        "artifacts/codex-runs/esxi-management-validation-report.md",
        "artifacts/codex-runs/firmware-compliance-report.md",
    ),
    "netapp": (
        "artifacts/codex-runs/netapp-upgrade-inventory-report.md",
        "artifacts/codex-runs/firmware-compliance-report.md",
    ),
    "vcenter": ("artifacts/codex-runs/vcenter-netapp-readiness-report.md",),
}
UPGRADE_PATH_STATUSES = {"current", "direct", "staged", "blocked", "unknown", "manual_review"}
UPGRADE_COMPONENT_ORDER = (
    "cisco_ios_xe_version",
    "cisco_bootloader_rommon",
    "hpe_ilo_firmware",
    "hpe_bios_version",
    "hpe_smart_array_firmware",
    "esxi_version",
    "netapp_ontap_version",
    "netapp_disk_firmware",
    "netapp_shelf_firmware",
    "netapp_sp_bmc_firmware",
    "vcenter_vcsa_version",
)
UPGRADE_COMPONENT_META = {
    "cisco_ios_xe_version": {
        "device_label": "Cisco",
        "component_label": "Cisco IOS XE",
        "equipment_type": "network_os",
        "scan_action_id": "cisco.firmware-inventory",
        "prechecks_required": ["Read-only show version inventory", "ROMMON/bootloader review before firmware apply"],
        "reboot_required": True,
        "estimated_impact": "Switch reload required for an IOS XE upgrade.",
    },
    "cisco_bootloader_rommon": {
        "device_label": "Cisco",
        "component_label": "Cisco ROMMON / bootloader",
        "equipment_type": "bootloader",
        "scan_action_id": "cisco.firmware-inventory",
        "prechecks_required": ["Read-only boot variable and ROMMON inventory"],
        "reboot_required": True,
        "estimated_impact": "Manual ROMMON review; reload impact depends on vendor procedure.",
    },
    "hpe_ilo_firmware": {
        "device_label": "iLO",
        "component_label": "iLO firmware",
        "equipment_type": "management_firmware",
        "scan_action_id": "ilo.firmware-inventory",
        "prechecks_required": ["Redfish manager inventory", "HPE package match"],
        "reboot_required": False,
        "estimated_impact": "iLO management controller restart may interrupt management sessions.",
    },
    "hpe_bios_version": {
        "device_label": "HPE Server",
        "component_label": "HPE BIOS",
        "equipment_type": "system_bios",
        "scan_action_id": "ilo.firmware-inventory",
        "prechecks_required": ["Redfish system inventory", "Approved HPE baseline or SPP evidence"],
        "reboot_required": True,
        "estimated_impact": "Host reboot required for BIOS changes.",
    },
    "hpe_smart_array_firmware": {
        "device_label": "HPE Smart Array",
        "component_label": "Smart Array firmware",
        "equipment_type": "storage_controller_firmware",
        "scan_action_id": "ilo.firmware-inventory",
        "prechecks_required": ["HPE storage discovery", "Approved HPE baseline or SPP evidence"],
        "reboot_required": True,
        "estimated_impact": "Controller firmware update may require host reboot and storage maintenance window.",
    },
    "esxi_version": {
        "device_label": "ESXi",
        "component_label": "ESXi image",
        "equipment_type": "hypervisor",
        "scan_action_id": "esxi.management-validation",
        "prechecks_required": ["ESXi management validation", "Approved ESXi ISO media"],
        "reboot_required": True,
        "estimated_impact": "ESXi image change requires host maintenance and reboot.",
    },
    "netapp_ontap_version": {
        "device_label": "NetApp",
        "component_label": "ONTAP",
        "equipment_type": "storage_os",
        "scan_action_id": "netapp.ontap-upgrade-inventory",
        "prechecks_required": ["ONTAP upgrade inventory", "Upgrade validation", "Upgrade Advisor or Health Checker review"],
        "reboot_required": True,
        "estimated_impact": "ONTAP upgrade may trigger takeover/giveback or controller reboot sequencing.",
    },
    "netapp_disk_firmware": {
        "device_label": "NetApp",
        "component_label": "NetApp disk firmware",
        "equipment_type": "disk_firmware",
        "scan_action_id": "netapp.component-firmware-inventory",
        "prechecks_required": ["ONTAP component firmware inventory"],
        "reboot_required": False,
        "estimated_impact": "Impact depends on NetApp component firmware procedure.",
    },
    "netapp_shelf_firmware": {
        "device_label": "NetApp",
        "component_label": "NetApp shelf firmware",
        "equipment_type": "shelf_firmware",
        "scan_action_id": "netapp.component-firmware-inventory",
        "prechecks_required": ["ONTAP shelf firmware inventory"],
        "reboot_required": False,
        "estimated_impact": "Impact depends on NetApp shelf firmware procedure.",
    },
    "netapp_sp_bmc_firmware": {
        "device_label": "NetApp",
        "component_label": "NetApp SP/BMC firmware",
        "equipment_type": "service_processor_firmware",
        "scan_action_id": "netapp.component-firmware-inventory",
        "prechecks_required": ["ONTAP service processor/BMC inventory"],
        "reboot_required": False,
        "estimated_impact": "Service processor restart may interrupt out-of-band management.",
    },
    "vcenter_vcsa_version": {
        "device_label": "vCenter",
        "component_label": "VCSA / vCenter",
        "equipment_type": "management_software",
        "scan_action_id": "vcenter-netapp.readiness",
        "prechecks_required": ["vCenter post-install or post-attach validation", "Approved VCSA ISO media"],
        "reboot_required": True,
        "estimated_impact": "VCSA upgrade affects vCenter management availability.",
    },
}


def get_firmware_inventory(*, refresh_live: bool = False) -> dict[str, Any]:
    if refresh_live:
        _refresh_live_inventory()
    ilo_probe, ilo_checked_at = get_probe_result("ilo-redfish")
    cisco_probe, cisco_checked_at = get_probe_result("cisco-ansible")
    cisco_console_probe, cisco_console_checked_at = get_probe_result("cisco-console")
    netapp_probe, netapp_checked_at = get_probe_result("netapp-ontap")
    media = get_firmware_media_inventory()
    cisco_versions = _merged_cisco_versions(
        cisco_probe if isinstance(cisco_probe, dict) else {},
        cisco_console_probe if isinstance(cisco_console_probe, dict) else {},
        ansible_checked_at=cisco_checked_at,
        console_checked_at=cisco_console_checked_at,
    )
    inventory_checked_at = _latest_probe_time([ilo_checked_at, cisco_checked_at, cisco_console_checked_at, netapp_checked_at])
    generated_at = datetime.now(UTC).isoformat()
    inventory = {
        "provider_id": "firmware-compliance",
        "status": "completed",
        "message": "Firmware inventory collected from cached/live provider evidence and local media metadata.",
        "provider_mode": settings.provider_mode,
        "checked_at": inventory_checked_at,
        "generated_at": generated_at,
        "live_inventory": {
            "ilo": _ilo_versions(ilo_probe if isinstance(ilo_probe, dict) else {}),
            "cisco": cisco_versions,
            "netapp": _netapp_versions(netapp_probe if isinstance(netapp_probe, dict) else {}),
        },
        "last_probe_times": {
            "ilo": ilo_checked_at,
            "cisco": cisco_checked_at,
            "cisco_console": cisco_console_checked_at,
            "netapp": netapp_checked_at,
        },
        "provider_warnings": {
            "ilo": _string_list((ilo_probe or {}).get("warnings") if isinstance(ilo_probe, dict) else []),
            "cisco": _string_list((cisco_probe or {}).get("warnings") if isinstance(cisco_probe, dict) else []),
            "netapp": _string_list((netapp_probe or {}).get("warnings") if isinstance(netapp_probe, dict) else []),
        },
        "media_inventory": media,
        "warnings": [],
        "blockers": [],
    }
    if not isinstance(ilo_probe, dict):
        inventory["warnings"].append("No cached iLO firmware inventory is available.")
    if not cisco_versions.get("ios_xe_version") and not settings.cisco_mgmt_configured:
        inventory["warnings"].append("Cisco management is not configured yet; run Cisco firmware inventory from console.")
    netapp_runtime_state = get_netapp_runtime_state()
    if not netapp_runtime_state.get("configured"):
        inventory["warnings"].append("NetApp firmware inventory is waiting for live setup validation.")
    source_type = "live_cached" if inventory_checked_at else "not_checked"
    return _sanitize(
        attach_status_source(
            inventory,
            source_type=source_type,
            checked_at=inventory_checked_at if source_type == "live_cached" else None,
            recheck_command="make provider-lab-firmware-inventory",
            evidence_artifacts=[_rel(INVENTORY_REPORT)],
        )
    )


def _latest_probe_time(values: list[str | None]) -> str | None:
    parsed_values: list[tuple[datetime, str]] = []
    for value in values:
        parsed = _parse_datetime(value)
        if parsed and value:
            parsed_values.append((parsed, value))
    if not parsed_values:
        return None
    return max(parsed_values, key=lambda item: item[0])[1]


def get_firmware_media_inventory() -> dict[str, Any]:
    directories = _media_directories()
    media = get_media_inventory(directories=tuple(str(path) for path in directories))
    items = [item.model_dump() for item in media.items if _is_firmware_like(item.model_dump())]
    grouped = {
        "hpe": [item for item in items if _matches_product_hint(item, ("hpe", "hpe-ilo", "hpe-spp", "hpe-sum"))],
        "cisco": [item for item in items if _matches_product_hint(item, ("cisco", "cisco-ios-xe"))],
        "netapp": [item for item in items if _matches_product_hint(item, ("netapp", "netapp-ontap"))],
    }
    return {
        "mode": media.mode,
        "configured_directories": media.configured_directories,
        "candidate_count": len(items),
        "candidates": items,
        "grouped_counts": {key: len(value) for key, value in grouped.items()},
        "warnings": media.warnings,
    }


def get_firmware_compliance(*, refresh_live: bool = False, scope: str = "full") -> dict[str, Any]:
    normalized_scope = _normalize_scope(scope)
    baseline = load_firmware_baseline()
    inventory = get_firmware_inventory(refresh_live=refresh_live)
    waiver = load_firmware_waiver()
    checked_at = inventory.get("checked_at") or datetime.now(UTC).isoformat()
    components = [
        _classify_component(component, inventory, waiver)
        for component in baseline.get("components", [])
    ]
    for component in components:
        component["in_scope"] = _component_in_scope(component["id"], normalized_scope)
    upgrade_paths = _firmware_upgrade_paths(
        components=components,
        inventory=inventory,
        baseline=baseline,
        checked_at=checked_at,
    )
    scoped_components = [component for component in components if component["in_scope"]]
    blockers = [
        _blocker_text(component)
        for component in scoped_components
        if component["status"] == "blocked"
    ]
    warnings = [
        _blocker_text(component)
        for component in scoped_components
        if component["status"] in {"warning", "unknown", "not_configured_yet"}
    ]
    overall_status = "passed"
    if any(component["status"] == "blocked" for component in scoped_components):
        overall_status = "blocked"
    elif any(component["status"] == "waived" for component in scoped_components):
        overall_status = "waived"
    elif warnings:
        overall_status = "warning"
    result = {
        "provider_id": "firmware-compliance",
        "status": overall_status,
        "message": _overall_message(overall_status),
        "checked_at": checked_at,
        "provider_mode": settings.provider_mode,
        "scope": normalized_scope,
        "baseline": {
            "baseline_id": baseline.get("baseline_id", "real-lab"),
            "path": _rel(BASELINE_PATH),
        },
        "waiver": waiver,
        "inventory": inventory,
        "components": components,
        "upgrade_paths": upgrade_paths,
        "upgrade_path_summary": _upgrade_path_summary(upgrade_paths),
        "devices": _device_summary(components),
        "blockers": blockers,
        "warnings": warnings,
        "next_safe_action": _next_safe_action(overall_status, scoped_components),
        "apply_enabled": overall_status in {"passed", "waived", "warning"},
        "upgrade_apply_enabled": any(path.get("apply_enabled") for path in upgrade_paths),
        "reports": {
            "inventory": _rel(INVENTORY_REPORT),
            "compliance": _rel(COMPLIANCE_REPORT),
            "summary": _rel(COMPLIANCE_SUMMARY),
            "waiver": _rel(WAIVER_REPORT) if waiver.get("active") else None,
        },
    }
    source_type = "live_cached" if inventory.get("source_type") == "live_cached" else "not_checked"
    return _sanitize(
        attach_status_source(
            result,
            source_type=source_type,
            checked_at=inventory.get("checked_at") if source_type == "live_cached" else None,
            recheck_command="make provider-lab-firmware-compliance",
            evidence_artifacts=[
                _rel(INVENTORY_REPORT),
                _rel(COMPLIANCE_REPORT),
                _rel(COMPLIANCE_SUMMARY),
            ],
        )
    )


def get_firmware_summaries(*, compliance: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    compliance = compliance or get_firmware_compliance(refresh_live=False, scope="full")
    components = {
        component.get("id"): component
        for component in compliance.get("components", [])
        if isinstance(component, dict) and component.get("id")
    }
    inventory = compliance.get("inventory") if isinstance(compliance.get("inventory"), dict) else {}
    upgrade_paths = [
        path
        for path in compliance.get("upgrade_paths", [])
        if isinstance(path, dict)
    ]
    summaries = [
        _component_firmware_summary(device_id, components, inventory, upgrade_paths)
        for device_id in ("cisco", "ilo", "raid", "netapp")
    ]
    summaries.append(_esxi_firmware_summary(upgrade_paths))
    summaries.append(_vcenter_firmware_summary(upgrade_paths))
    return _sanitize({"summaries": summaries})["summaries"]


def firmware_gate_blockers(scope: str) -> list[str]:
    normalized_scope = _workflow_scope(scope)
    compliance = get_firmware_compliance(refresh_live=False, scope=normalized_scope)
    if compliance["status"] in {"passed", "waived", "warning"}:
        return []
    blockers = [
        f"Firmware compliance gate blocks {scope}: {message}"
        for message in compliance.get("blockers", [])
    ]
    return blockers or [f"Firmware compliance gate blocks {scope}; run provider-lab-firmware-compliance-scope-{normalized_scope}."]


def write_firmware_reports(*, refresh_live: bool = False, scope: str = "full") -> dict[str, Any]:
    inventory = get_firmware_inventory(refresh_live=refresh_live)
    compliance = get_firmware_compliance(refresh_live=False, scope=scope)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_text_value(INVENTORY_REPORT, _inventory_markdown(inventory))
    write_text_value(COMPLIANCE_REPORT, _compliance_markdown(compliance))
    write_json_object(COMPLIANCE_SUMMARY, _summary(compliance))
    if compliance.get("waiver", {}).get("active"):
        write_text_value(WAIVER_REPORT, _waiver_markdown(compliance["waiver"], compliance))
    elif path_exists(WAIVER_REPORT):
        remove_file_best_effort(WAIVER_REPORT)
    return compliance


def write_waiver_report() -> dict[str, Any]:
    compliance = get_firmware_compliance(refresh_live=False)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    if compliance.get("waiver", {}).get("configured"):
        write_text_value(WAIVER_REPORT, _waiver_markdown(compliance["waiver"], compliance))
    return compliance


def load_firmware_baseline() -> dict[str, Any]:
    text = _read_text(BASELINE_PATH)
    if not text.strip():
        return _missing_firmware_baseline()
    baseline = _parse_baseline(text)
    components = baseline.get("components")
    if not baseline.get("baseline_id") and not components:
        return _missing_firmware_baseline()
    baseline["components"] = _records(components)
    return baseline


def _missing_firmware_baseline() -> dict[str, Any]:
    return {"baseline_id": "missing", "components": []}


def load_firmware_waiver() -> dict[str, Any]:
    env_waiver = {
        "confirm": os.getenv("FIRMWARE_WAIVER_CONFIRM", "").strip(),
        "reason": os.getenv("FIRMWARE_WAIVER_REASON", "").strip(),
        "expires": os.getenv("FIRMWARE_WAIVER_EXPIRES", "").strip(),
        "scope": os.getenv("FIRMWARE_WAIVER_SCOPE", "").strip(),
        "source": "env",
    }
    file_waiver = _load_local_waiver()
    waiver = file_waiver or env_waiver
    configured = any(waiver.get(key) for key in ("confirm", "reason", "expires", "scope"))
    errors: list[str] = []
    if configured:
        if waiver.get("confirm") != "WAIVE FIRMWARE COMPLIANCE":
            errors.append("FIRMWARE_WAIVER_CONFIRM must equal WAIVE FIRMWARE COMPLIANCE.")
        if not waiver.get("reason"):
            errors.append("FIRMWARE_WAIVER_REASON is required.")
        expires = waiver.get("expires")
        if not expires:
            errors.append("FIRMWARE_WAIVER_EXPIRES is required.")
        elif _expired(expires):
            errors.append("Firmware waiver is expired.")
        if not waiver.get("scope"):
            errors.append("FIRMWARE_WAIVER_SCOPE is required.")
    return {
        "configured": configured,
        "active": configured and not errors,
        "source": waiver.get("source") or "none",
        "scope": waiver.get("scope") or None,
        "reason": waiver.get("reason") or None,
        "expires": waiver.get("expires") or None,
        "errors": errors,
        "report": _rel(WAIVER_REPORT) if configured else None,
    }


def _refresh_live_inventory() -> None:
    if settings.provider_mode != "local-lab-readwrite":
        return
    from app.providers.cisco_ansible import CiscoAnsibleAdapter
    from app.providers.ilo_redfish import IloRedfishAdapter

    IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
    if settings.cisco_mgmt_configured:
        CiscoAnsibleAdapter(provider_mode="local-lab-readwrite").probe()


def _classify_component(
    baseline_component: dict[str, Any],
    inventory: dict[str, Any],
    waiver: dict[str, Any],
) -> dict[str, Any]:
    current = _current_version_for(baseline_component["id"], inventory)
    minimum = baseline_component.get("minimum")
    approved = baseline_component.get("approved") or []
    status = "passed"
    reason = "Current version matches the firmware baseline."
    if baseline_component["id"].startswith("netapp_") and not get_netapp_runtime_state().get("configured") and not current:
        status = "not_configured_yet"
        reason = "NetApp firmware inventory is waiting for live setup validation."
    elif not current:
        status = baseline_component.get("unknown_policy") or "unknown"
        reason = "Current firmware or OS version is unknown."
        if baseline_component["id"] == "cisco_ios_xe_version":
            baseline_component = {
                **baseline_component,
                "next_action": "Run Cisco firmware inventory from console.",
            }
    elif approved and current in approved:
        status = "passed"
    elif minimum and _compare_versions(current, minimum) < 0:
        status = "blocked"
        reason = f"Current version {current} is below minimum {minimum}."
    elif minimum:
        status = "passed"
    elif not approved:
        status = "warning"
        reason = "Baseline requires manual approval because no minimum or approved version is set."

    if status == "unknown":
        status = "blocked"
    if status == "blocked" and _waiver_applies(waiver, baseline_component):
        status = "waived"
        reason = f"Blocked component was explicitly waived: {waiver.get('reason')}"

    return {
        "id": baseline_component["id"],
        "device": baseline_component.get("device", "Unknown"),
        "label": baseline_component.get("label", baseline_component["id"]),
        "status": status if status in VALID_STATUSES else "unknown",
        "current_version": current,
        "required_version": minimum,
        "approved_versions": approved,
        "reason": reason,
        "next_action": baseline_component.get("next_action") or "Review firmware baseline and live inventory.",
        "waiver_applied": status == "waived",
    }


def _current_version_for(component_id: str, inventory: dict[str, Any]) -> str | None:
    live = inventory.get("live_inventory", {})
    ilo = live.get("ilo", {})
    cisco = live.get("cisco", {})
    netapp = live.get("netapp", {})
    report_versions = _firmware_inventory_report_versions()
    mapping = {
        "hpe_ilo_firmware": ilo.get("ilo_firmware") or report_versions.get("ilo_firmware"),
        "hpe_bios_version": ilo.get("bios_version") or report_versions.get("bios_version"),
        "hpe_smart_array_firmware": ilo.get("smart_array_firmware") or report_versions.get("smart_array_firmware"),
        "cisco_ios_xe_version": cisco.get("ios_xe_version") or os.getenv("CISCO_CURRENT_IOS_XE_VERSION"),
        "cisco_bootloader_rommon": cisco.get("bootloader_rommon") or os.getenv("CISCO_CURRENT_BOOTLOADER_ROMMON"),
        "netapp_ontap_version": netapp.get("ontap_version") or report_versions.get("ontap_version"),
        "netapp_disk_firmware": netapp.get("disk_firmware"),
        "netapp_shelf_firmware": netapp.get("shelf_firmware"),
        "netapp_sp_bmc_firmware": netapp.get("sp_bmc_firmware"),
    }
    value = mapping.get(component_id)
    return _known_version_or_none(value)


def _ilo_versions(probe: dict[str, Any]) -> dict[str, Any]:
    managers = _records(probe.get("managers"))
    systems = _records(probe.get("systems"))
    storage = probe.get("storage") if isinstance(probe.get("storage"), dict) else {}
    controllers = _records(storage.get("controllers"))
    firmware = _records(probe.get("firmware"))
    legacy_identity = probe.get("legacy_identity") if isinstance(probe.get("legacy_identity"), dict) else {}
    return {
        "status": probe.get("status") or "not_checked",
        "ilo_firmware": _first(managers, ("FirmwareVersion", "firmware_version"))
        or _firmware_match(firmware, "ilo")
        or legacy_identity.get("current_firmware"),
        "bios_version": _first(systems, ("BiosVersion", "bios_version", "BIOSVersion")) or _firmware_match(firmware, "bios"),
        "smart_array_firmware": _first(controllers, ("FirmwareVersion", "firmware_version", "Version")) or _firmware_match(firmware, "smart"),
    }


def _cisco_versions(probe: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(probe)
    return {
        "status": probe.get("status") or ("not_configured_yet" if not settings.cisco_mgmt_configured else "not_checked"),
        "ios_xe_version": probe.get("ios_xe_version")
        or _show_command_hint(probe, "show version", "version_hint")
        or _regex_version(text, r"IOS XE Software[^0-9]*(\d+(?:\.\d+)+)")
        or _regex_version(text, r"Version\s+(\d+(?:\.\d+)+)"),
        "bootloader_rommon": probe.get("bootloader_rommon")
        or _show_command_hint(probe, "show version", "bootloader_rommon_hint")
        or _regex_version(text, r"(?:ROMMON|BOOTLDR|BOOT LOADER)[^0-9]*(\d+(?:\.\d+)+)"),
        "source": probe.get("source") or probe.get("provider_id") or "unknown",
    }


def _merged_cisco_versions(
    ansible_probe: dict[str, Any],
    console_probe: dict[str, Any],
    *,
    ansible_checked_at: str | None = None,
    console_checked_at: str | None = None,
) -> dict[str, Any]:
    ansible = _cisco_versions(ansible_probe)
    console = _cisco_versions(console_probe)
    report = _cisco_firmware_report_versions()
    historical: dict[str, Any] | None = None
    if ansible.get("ios_xe_version") or ansible.get("bootloader_rommon"):
        historical = {
            "source": ansible.get("source"),
            "checked_at": ansible_checked_at,
            "ios_xe_version": ansible.get("ios_xe_version"),
            "bootloader_rommon": ansible.get("bootloader_rommon"),
            "historical": True,
            "note": "Cached non-console evidence only; live console evidence remains preferred.",
        }
    if console_probe and (console.get("ios_xe_version") or console.get("bootloader_rommon")):
        return {
            "status": console.get("status"),
            "ios_xe_version": console.get("ios_xe_version"),
            "bootloader_rommon": console.get("bootloader_rommon"),
            "source": console.get("source"),
            "checked_at": console_checked_at,
            "historical_evidence": historical,
        }
    if (
        not ansible.get("ios_xe_version")
        and not console.get("ios_xe_version")
        and report.get("ios_xe_version")
        and not _console_inventory_failure_blocks_report(console_probe)
    ):
        return {
            "status": report.get("status") or "ok",
            "ios_xe_version": report.get("ios_xe_version"),
            "bootloader_rommon": report.get("bootloader_rommon"),
            "source": report.get("source") or "cisco-firmware-inventory-report",
            "checked_at": report.get("checked_at"),
            "historical_evidence": historical,
        }
    if console_probe and (ansible.get("ios_xe_version") or ansible.get("bootloader_rommon")) and (
        settings.cisco_mgmt_configured or not _console_inventory_failure_blocks_report(console_probe)
    ):
        return {
            "status": ansible.get("status"),
            "ios_xe_version": ansible.get("ios_xe_version"),
            "bootloader_rommon": ansible.get("bootloader_rommon"),
            "source": ansible.get("source"),
            "checked_at": ansible_checked_at,
            "historical_evidence": None,
        }
    if console_probe:
        return {
            "status": console.get("status"),
            "ios_xe_version": console.get("ios_xe_version"),
            "bootloader_rommon": console.get("bootloader_rommon"),
            "source": console.get("source"),
            "checked_at": console_checked_at,
            "historical_evidence": historical,
        }
    return {
        "status": ansible.get("status"),
        "ios_xe_version": ansible.get("ios_xe_version"),
        "bootloader_rommon": ansible.get("bootloader_rommon"),
        "source": ansible.get("source"),
        "checked_at": ansible_checked_at,
        "historical_evidence": None,
    }


def _console_inventory_failure_blocks_report(console_probe: dict[str, Any]) -> bool:
    if _optional_status(console_probe.get("status")) not in {"blocked", "failed"}:
        return False
    text = " ".join(_string_list(console_probe.get("blockers")) + _string_list(console_probe.get("warnings"))).lower()
    return any(token in text for token in ("no prompt", "wrong baud", "unreadable", "garbled"))


def _optional_status(value: Any) -> str | None:
    return str(value).strip().lower() if value else None


def _cisco_firmware_report_versions() -> dict[str, Any]:
    text = _read_text(CISCO_FIRMWARE_INVENTORY_REPORT)
    if not text:
        return {}
    return {
        "status": _report_field(text, "Status"),
        "source": _report_field(text, "Source") or "cisco-firmware-inventory-report",
        "ios_xe_version": _report_field(text, "IOS XE version"),
        "bootloader_rommon": _report_field(text, "Bootloader/ROMMON"),
        "checked_at": _path_mtime(CISCO_FIRMWARE_INVENTORY_REPORT),
    }


def _firmware_inventory_report_versions() -> dict[str, Any]:
    text = _read_text(INVENTORY_REPORT)
    if not text:
        return {}
    return {
        "checked_at": _report_scalar(text, "Checked") or _path_mtime(INVENTORY_REPORT),
        "ilo_firmware": _known_version_or_none(_report_field(text, "iLO firmware")),
        "bios_version": _known_version_or_none(_report_field(text, "HPE BIOS")),
        "smart_array_firmware": _known_version_or_none(_report_field(text, "HPE Smart Array")),
        "ontap_version": _known_version_or_none(_report_field(text, "ONTAP")),
        "netapp_disk_firmware": _known_version_or_none(_report_field(text, "NetApp disk firmware")),
        "netapp_shelf_firmware": _known_version_or_none(_report_field(text, "NetApp shelf firmware")),
        "netapp_sp_bmc_firmware": _known_version_or_none(_report_field(text, "NetApp SP/BMC firmware")),
    }


def _netapp_upgrade_versions() -> dict[str, Any]:
    validation = _read_json_artifact(NETAPP_ONTAP_UPGRADE_VALIDATION_JSON)
    plan = _read_json_artifact(NETAPP_ONTAP_UPGRADE_PLAN_JSON)
    source = "netapp-ontap-upgrade-validation"
    payload = validation if validation.get("current_version") or validation.get("target_version") else plan
    if payload is plan:
        source = "netapp-ontap-upgrade-plan"
    return {
        "source": source,
        "checked_at": _string_or_none(payload.get("checked_at")),
        "current_version": _known_version_or_none(payload.get("current_version")),
        "target_version": _known_version_or_none(payload.get("target_version")),
        "selected_package": payload.get("selected_package") if isinstance(payload.get("selected_package"), dict) else {},
        "status": _string_or_none(payload.get("status")),
        "validation_passed": bool(payload.get("validation_passed")),
    }


def _report_field(text: str, label: str) -> str | None:
    escaped = re.escape(label)
    match = re.search(rf"^\s*-\s*{escaped}:\s*(.+?)\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip(" `") if match else None


def _known_version_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() in {"unknown", "none", "null", "n/a", "not set", "not selected"}:
        return None
    return text


def _netapp_versions(probe: dict[str, Any]) -> dict[str, Any]:
    runtime_state = get_netapp_runtime_state()
    upgrade_versions = _netapp_upgrade_versions()
    console_version = (
        latest_console_ontap_version()
        if settings.provider_mode != "mock"
        else {"version": None, "source": "not_available", "checked_at": None}
    )
    ontap_version = (
        settings.netapp_current_ontap_version
        or upgrade_versions.get("current_version")
        or console_version.get("version")
    )
    configured = runtime_state.get("configured") or bool(upgrade_versions.get("current_version"))
    return {
        "status": "configured" if configured else "not_configured_yet",
        "ontap_version": ontap_version,
        "ontap_version_source": "configured_placeholder"
        if settings.netapp_current_ontap_version
        else upgrade_versions.get("source")
        if upgrade_versions.get("current_version")
        else console_version.get("source"),
        "disk_firmware": os.getenv("NETAPP_CURRENT_DISK_FIRMWARE"),
        "shelf_firmware": os.getenv("NETAPP_CURRENT_SHELF_FIRMWARE"),
        "sp_bmc_firmware": os.getenv("NETAPP_CURRENT_SP_BMC_FIRMWARE"),
    }


def _parse_baseline(text: str) -> dict[str, Any]:
    baseline: dict[str, Any] = {"components": []}
    current: dict[str, Any] | None = None
    in_components = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped == "components:":
            in_components = True
            continue
        if not in_components and ":" in stripped:
            key, value = stripped.split(":", 1)
            baseline[key.strip()] = _parse_scalar(value.strip())
            continue
        if in_components and stripped.startswith("- "):
            if current:
                baseline["components"].append(current)
            current = {}
            item = stripped[2:]
            if ":" in item:
                key, value = item.split(":", 1)
                current[key.strip()] = _parse_scalar(value.strip())
            continue
        if in_components and current is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current[key.strip()] = _parse_scalar(value.strip())
    if current:
        baseline["components"].append(current)
    return baseline


def _parse_scalar(value: str) -> Any:
    if value in {"", "null", "~"}:
        return None
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _first(records: list[dict[str, Any]], keys: tuple[str, ...]) -> str | None:
    for record in records:
        for key in keys:
            value = record.get(key)
            if value:
                return _version_value(value)
    return None


def _version_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("VersionString", "version", "Version", "FirmwareVersion"):
            nested = value.get(key)
            if nested:
                return _version_value(nested)
        current = value.get("Current")
        if current:
            return _version_value(current)
    return str(value)


def _firmware_match(records: list[dict[str, Any]], hint: str) -> str | None:
    for record in records:
        if hint in json.dumps(record).lower():
            value = _first([record], ("Version", "FirmwareVersion", "version", "firmware_version"))
            if value:
                return value
    return None


def _regex_version(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1) if match else None


def _show_command_hint(probe: dict[str, Any], command: str, key: str) -> str | None:
    candidates: list[dict[str, Any]] = []
    safe_show_commands = probe.get("safe_show_commands")
    if isinstance(safe_show_commands, list):
        candidates.extend(item for item in safe_show_commands if isinstance(item, dict))
    command_results = probe.get("command_results")
    if isinstance(command_results, dict):
        candidates.extend(
            {"command": command_name, **payload}
            for command_name, payload in command_results.items()
            if isinstance(payload, dict)
        )
    for item in candidates:
        if item.get("command") == command and item.get(key):
            return str(item[key])
    return None


def _compare_versions(current: str, minimum: str) -> int:
    left = _version_parts(current)
    right = _version_parts(minimum)
    width = max(len(left), len(right))
    left.extend([0] * (width - len(left)))
    right.extend([0] * (width - len(right)))
    return (left > right) - (left < right)


def _version_parts(value: str) -> list[int]:
    version_marker = re.search(r"\bv(\d+(?:\.\d+)+)", value, flags=re.IGNORECASE)
    if version_marker:
        return [int(part) for part in re.findall(r"\d+", version_marker.group(1))]
    parts = re.findall(r"\d+", value)
    return [int(part) for part in parts] or [0]


def _normalize_scope(scope: str) -> str:
    normalized = str(scope or "full").strip().lower()
    return normalized if normalized in VALID_SCOPES else "full"


def _component_in_scope(component_id: str, scope: str) -> bool:
    prefixes = SCOPE_COMPONENT_PREFIXES[_normalize_scope(scope)]
    return component_id.startswith(prefixes)


def _workflow_scope(scope: str) -> str:
    lower = str(scope or "").lower()
    if "netapp" in lower:
        return "netapp"
    if "cisco" in lower:
        return "cisco"
    if any(token in lower for token in ("hpe", "ilo", "raid", "esxi", "server")):
        return "hpe"
    return _normalize_scope(lower)


def _component_firmware_summary(
    device_id: str,
    components: dict[str, dict[str, Any]],
    inventory: dict[str, Any],
    upgrade_paths: list[dict[str, Any]],
) -> dict[str, Any]:
    component_ids = SUMMARY_COMPONENTS[device_id]
    selected = [components[component_id] for component_id in component_ids if component_id in components]
    source = _component_source_info(device_id, inventory)
    compliance_status = _summary_compliance_status(selected)
    blocker = _summary_blocker(compliance_status, selected, source)
    severity = _summary_severity(compliance_status, source["freshness"])
    path_rollup = _summary_path_rollup(_paths_for_device(device_id, upgrade_paths))
    return {
        "device_id": device_id,
        "label": SUMMARY_LABELS[device_id],
        "component_type": SUMMARY_COMPONENT_TYPES[device_id],
        "current_versions": _summary_current_versions(selected),
        "approved_versions": _summary_approved_versions(selected),
        "compliance_status": compliance_status,
        "severity": severity,
        "last_scanned": source["last_scanned"],
        "source_type": source["source_type"],
        "freshness": source["freshness"],
        "blocker": blocker,
        "next_action": _summary_next_action(compliance_status, selected, blocker),
        "scan_action_id": SUMMARY_SCAN_ACTIONS[device_id],
        "upgrade_center_link": f"/firmware?device={device_id}",
        "evidence_artifacts": _existing_summary_artifacts(device_id),
        **path_rollup,
    }


def _summary_current_versions(components: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for component in components:
        rows.append(
            {
                "label": _summary_component_label(component),
                "version": component.get("current_version"),
                "status": component.get("status"),
            }
        )
    return rows


def _summary_approved_versions(components: list[dict[str, Any]]) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for component in components:
        label = _summary_component_label(component)
        minimum = component.get("required_version")
        approved = [str(value) for value in component.get("approved_versions") or [] if value]
        if minimum:
            rows.append({"label": label, "version": f">= {minimum}", "status": "minimum"})
        for value in approved:
            rows.append({"label": label, "version": value, "status": "approved"})
        if not minimum and not approved:
            rows.append({"label": label, "version": None, "status": "manual_review"})
    return rows


def _summary_component_label(component: dict[str, Any]) -> str:
    label = str(component.get("label") or component.get("id") or "Version")
    id_replacements = {
        "hpe_ilo_firmware": "iLO firmware",
        "hpe_bios_version": "BIOS",
        "hpe_smart_array_firmware": "Smart Array",
        "cisco_ios_xe_version": "Cisco IOS XE",
        "cisco_bootloader_rommon": "ROMMON",
        "netapp_ontap_version": "ONTAP",
    }
    component_id = str(component.get("id") or "")
    if component_id in id_replacements:
        return id_replacements[component_id]
    replacements = {
        "HPE iLO firmware": "iLO firmware",
        "HPE BIOS version": "BIOS",
        "HPE Smart Array controller firmware": "Smart Array",
        "Cisco IOS XE version": "Cisco IOS XE",
        "Cisco bootloader/ROMMON": "ROMMON",
        "ONTAP version": "ONTAP",
    }
    return replacements.get(label, label)


def _summary_compliance_status(components: list[dict[str, Any]]) -> str:
    if not components:
        return "cannot_verify"
    statuses = [str(component.get("status") or "unknown") for component in components]
    if all(status == "not_configured_yet" for status in statuses):
        return "not_configured"
    if any(_component_is_below_baseline(component) for component in components):
        return "needs_upgrade"
    if any(status in {"blocked", "warning", "unknown", "not_configured_yet"} for status in statuses):
        return "cannot_verify"
    if not any(component.get("current_version") for component in components):
        return "cannot_verify"
    return "current"


def _component_is_below_baseline(component: dict[str, Any]) -> bool:
    return component.get("status") == "blocked" and "below minimum" in str(component.get("reason") or "").lower()


def _summary_severity(compliance_status: str, freshness: str) -> str:
    if compliance_status == "needs_upgrade":
        return "red"
    if compliance_status == "not_configured":
        return "gray"
    if compliance_status == "cannot_verify":
        return "yellow"
    if freshness in {"stale", "historical"}:
        return "yellow"
    return "green"


def _summary_blocker(
    compliance_status: str,
    components: list[dict[str, Any]],
    source: dict[str, str | None],
) -> str | None:
    if compliance_status == "not_configured":
        return "not configured yet"
    if compliance_status == "needs_upgrade":
        component = next((item for item in components if _component_is_below_baseline(item)), None)
        return str(component.get("reason") if component else "below baseline")
    if compliance_status == "current":
        if source["freshness"] in {"stale", "historical"}:
            return "stale evidence only"
        return None
    manual_review = _manual_review_message(components)
    if manual_review:
        return manual_review
    missing_versions = [component for component in components if not component.get("current_version")]
    if missing_versions:
        return _cannot_verify_reason(" ".join(str(item.get("reason") or "") for item in missing_versions), source)
    if source["freshness"] in {"stale", "historical"}:
        return "stale evidence only"
    return "live scan not run"


def _manual_review_message(components: list[dict[str, Any]]) -> str | None:
    labels = [
        _summary_component_label(component)
        for component in components
        if component.get("status") == "warning"
        and not component.get("required_version")
        and not component.get("approved_versions")
    ]
    if not labels:
        return None
    return f"{', '.join(labels)} baseline missing/manual review"


def _cannot_verify_reason(text: str, source: dict[str, str | None]) -> str:
    lower = text.lower()
    if source["freshness"] in {"stale", "historical"}:
        return "stale evidence only"
    if "credential" in lower or "auth" in lower or "password" in lower:
        return "credentials missing"
    if "unreachable" in lower or "timeout" in lower or "port is not reachable" in lower:
        return "device unreachable"
    if "unsupported" in lower or "not supported" in lower:
        return "unsupported endpoint"
    return "live scan not run"


def _summary_next_action(
    compliance_status: str,
    components: list[dict[str, Any]],
    blocker: str | None,
) -> str:
    if compliance_status == "current":
        return "Open Firmware Upgrades for full planning, or rescan before apply work."
    if compliance_status == "not_configured":
        return "Complete device setup and credentials before firmware inventory."
    if compliance_status == "needs_upgrade":
        component = next((item for item in components if _component_is_below_baseline(item)), None)
        return str(component.get("next_action") if component else "Open Firmware Upgrades to plan the upgrade.")
    if blocker and "baseline missing/manual review" in blocker:
        return "Open Firmware Upgrades and record the manual baseline decision."
    component = next((item for item in components if item.get("next_action")), None)
    return str(component.get("next_action") if component else "Run a safe firmware scan.")


def _component_source_info(device_id: str, inventory: dict[str, Any]) -> dict[str, str | None]:
    last_probe_times = inventory.get("last_probe_times") if isinstance(inventory.get("last_probe_times"), dict) else {}
    live_inventory = inventory.get("live_inventory") if isinstance(inventory.get("live_inventory"), dict) else {}
    source_type = "not_checked"
    checked_at: str | None = None
    if device_id == "cisco":
        cisco = live_inventory.get("cisco") if isinstance(live_inventory.get("cisco"), dict) else {}
        report = _cisco_firmware_report_versions()
        checked_at = _string_or_none(cisco.get("checked_at")) or _string_or_none(last_probe_times.get("cisco_console")) or _string_or_none(last_probe_times.get("cisco"))
        source_type = "cached_live" if checked_at else "not_checked"
        if (
            report.get("ios_xe_version")
            and cisco.get("ios_xe_version") == report.get("ios_xe_version")
            and cisco.get("checked_at") == report.get("checked_at")
        ):
            checked_at = _string_or_none(report.get("checked_at"))
            source_type = "historical_evidence"
    elif device_id in {"ilo", "raid"}:
        checked_at = _string_or_none(last_probe_times.get("ilo"))
        source_type = "cached_live" if checked_at else "not_checked"
    elif device_id == "netapp":
        checked_at = _string_or_none(last_probe_times.get("netapp"))
        source_type = "cached_live" if checked_at else "not_checked"
    freshness = _freshness(source_type, checked_at)
    return {"source_type": source_type, "last_scanned": checked_at, "freshness": freshness}


def _esxi_firmware_summary(upgrade_paths: list[dict[str, Any]]) -> dict[str, Any]:
    probe, checked_at = get_probe_result("esxi-readonly")
    probe_versions = _esxi_probe_versions(probe if isinstance(probe, dict) else {})
    report_versions = _esxi_report_versions()
    versions = probe_versions or report_versions
    source_type = "cached_live" if probe_versions else "historical_evidence" if report_versions else "not_checked"
    last_scanned = checked_at if probe_versions else _report_checked_at(ESXI_MANAGEMENT_VALIDATION_REPORT) if report_versions else checked_at
    freshness = _freshness(source_type, last_scanned)
    if versions:
        compliance_status = "current"
        blocker = "stale evidence only" if freshness in {"stale", "historical"} else None
    elif not settings.esxi_configured:
        compliance_status = "not_configured"
        blocker = "not configured yet"
    else:
        compliance_status = "cannot_verify"
        blocker = _cannot_verify_reason(json.dumps(probe or {}), {"source_type": source_type, "freshness": freshness})
    path_rollup = _summary_path_rollup(_paths_for_device("esxi", upgrade_paths))
    return {
        "device_id": "esxi",
        "label": SUMMARY_LABELS["esxi"],
        "component_type": SUMMARY_COMPONENT_TYPES["esxi"],
        "current_versions": versions,
        "approved_versions": [],
        "compliance_status": compliance_status,
        "severity": _summary_severity(compliance_status, freshness),
        "last_scanned": last_scanned,
        "source_type": source_type,
        "freshness": freshness,
        "blocker": blocker,
        "next_action": "Run ESXi management validation before install or datastore work.",
        "scan_action_id": SUMMARY_SCAN_ACTIONS["esxi"],
        "upgrade_center_link": "/firmware?device=esxi",
        "evidence_artifacts": _existing_summary_artifacts("esxi"),
        **path_rollup,
    }


def _vcenter_firmware_summary(upgrade_paths: list[dict[str, Any]]) -> dict[str, Any]:
    last_scanned = _report_checked_at(VCENTER_NETAPP_READINESS_REPORT)
    source_type = "cached_live" if last_scanned else "not_checked"
    freshness = _freshness(source_type, last_scanned)
    vcenter_version = _vcenter_current_version()
    configured = bool(settings.vcenter_configured or vcenter_version.get("version"))
    compliance_status = "current" if vcenter_version.get("version") else "cannot_verify" if configured else "not_configured"
    blocker = None if vcenter_version.get("version") else "live scan not run" if configured else "not configured yet"
    path_rollup = _summary_path_rollup(_paths_for_device("vcenter", upgrade_paths))
    return {
        "device_id": "vcenter",
        "label": SUMMARY_LABELS["vcenter"],
        "component_type": SUMMARY_COMPONENT_TYPES["vcenter"],
        "current_versions": [
            {"label": "VCSA / vCenter", "version": vcenter_version.get("version"), "status": "passed"}
        ] if vcenter_version.get("version") else [],
        "approved_versions": [
            {"label": "VCSA ISO", "version": path_rollup.get("target_version"), "status": "media"}
        ] if path_rollup.get("target_version") else [],
        "compliance_status": compliance_status,
        "severity": _summary_severity(compliance_status, freshness),
        "last_scanned": last_scanned,
        "source_type": source_type,
        "freshness": freshness,
        "blocker": blocker,
        "next_action": "Configure vCenter and rerun vCenter-NetApp readiness when that lane is in scope.",
        "scan_action_id": SUMMARY_SCAN_ACTIONS["vcenter"],
        "upgrade_center_link": "/firmware?device=vcenter",
        "evidence_artifacts": _existing_summary_artifacts("vcenter"),
        **path_rollup,
    }


def _firmware_upgrade_paths(
    *,
    components: list[dict[str, Any]],
    inventory: dict[str, Any],
    baseline: dict[str, Any],
    checked_at: str,
) -> list[dict[str, Any]]:
    component_by_id = {
        str(component.get("id")): component
        for component in components
        if isinstance(component, dict) and component.get("id")
    }
    baseline_by_id = {
        str(component.get("id")): component
        for component in baseline.get("components", [])
        if isinstance(component, dict) and component.get("id")
    }
    media_items = _all_media_items()
    return [
        _firmware_upgrade_path(
            component_id=component_id,
            component=component_by_id.get(component_id),
            baseline_component=baseline_by_id.get(component_id),
            inventory=inventory,
            media_items=media_items,
            checked_at=checked_at,
        )
        for component_id in UPGRADE_COMPONENT_ORDER
    ]


def _firmware_upgrade_path(
    *,
    component_id: str,
    component: dict[str, Any] | None,
    baseline_component: dict[str, Any] | None,
    inventory: dict[str, Any],
    media_items: list[dict[str, Any]],
    checked_at: str,
) -> dict[str, Any]:
    meta = UPGRADE_COMPONENT_META[component_id]
    current_version = _path_current_version(component_id, component)
    target = _path_target(component_id, baseline_component, media_items)
    package = _package_for_component(component_id, current_version, target.get("target_version"), media_items)
    candidate_files = _candidate_files_for_component(component_id, current_version, target.get("target_version"), media_items)
    source = _path_source_info(component_id, inventory, current_version, checked_at)
    evidence = _path_evidence_artifacts(component_id)
    required_intermediates = _string_list((baseline_component or {}).get("required_intermediate_versions"))
    missing_evidence = _missing_path_evidence(
        current_version=current_version,
        target_version=target.get("target_version"),
        baseline_component=baseline_component,
        component_id=component_id,
    )
    status = _path_status(
        component_id=component_id,
        current_version=current_version,
        target_version=target.get("target_version"),
        target_kind=target.get("target_kind"),
        package_available=bool(package),
        required_intermediate_versions=required_intermediates,
        missing_evidence=missing_evidence,
    )
    disabled_reason = _path_disabled_reason(
        path_status=status,
        component_id=component_id,
        current_version=current_version,
        target_version=target.get("target_version"),
        package_available=bool(package),
        freshness=source["freshness"],
        missing_evidence=missing_evidence,
    )
    next_action = _path_next_action(status, component_id, disabled_reason)
    return _sanitize_path(
        {
            "component_id": component_id,
            "component_label": meta["component_label"],
            "device_label": meta["device_label"],
            "equipment_label": meta["device_label"],
            "equipment_type": meta["equipment_type"],
            "current_version": current_version,
            "target_version": target.get("target_version"),
            "baseline_source": target.get("baseline_source"),
            "package_available": bool(package),
            "package_name": package.get("placeholder_name") if package else None,
            "package_version": package.get("version_hint") if package else None,
            "selected_file_name": _media_file_name(package) if package else None,
            "selected_file_path": _media_file_path(package) if package else None,
            "selection_source": "auto" if package else "none",
            "candidate_files": candidate_files,
            "path_status": status,
            "required_intermediate_versions": required_intermediates,
            "prechecks_required": list(meta["prechecks_required"]),
            "reboot_required": bool(meta["reboot_required"]),
            "estimated_impact": meta["estimated_impact"],
            "apply_enabled": False,
            "disabled_reason": disabled_reason,
            "next_action": next_action,
            "evidence_artifacts": evidence,
            "missing_evidence": missing_evidence,
            "scan_action_id": meta["scan_action_id"],
            "last_checked": source["last_checked"],
            "source_type": source["source_type"],
            "freshness": source["freshness"],
        }
    )


def _path_current_version(component_id: str, component: dict[str, Any] | None) -> str | None:
    if component_id == "esxi_version":
        versions = _esxi_probe_versions(get_probe_result("esxi-readonly")[0] or {})
        if versions:
            return _known_version_or_none(versions[0].get("version"))
        for version in _esxi_report_versions():
            if version.get("label") == "ESXi":
                return _known_version_or_none(version.get("version"))
        return None
    if component_id == "vcenter_vcsa_version":
        return _vcenter_current_version().get("version")
    value = (component or {}).get("current_version")
    if component_id == "netapp_ontap_version" and not value:
        value = _netapp_upgrade_versions().get("current_version")
    return _known_version_or_none(value)


def _path_target(
    component_id: str,
    baseline_component: dict[str, Any] | None,
    media_items: list[dict[str, Any]],
) -> dict[str, str | None]:
    if component_id == "netapp_ontap_version":
        upgrade = _netapp_upgrade_versions()
        if upgrade.get("target_version"):
            return {
                "target_version": upgrade["target_version"],
                "baseline_source": _rel(NETAPP_ONTAP_UPGRADE_VALIDATION_JSON)
                if path_exists(NETAPP_ONTAP_UPGRADE_VALIDATION_JSON)
                else _rel(NETAPP_ONTAP_UPGRADE_PLAN_JSON),
                "target_kind": "exact",
            }
    if component_id == "esxi_version":
        target = _media_target_version("esxi_version", media_items)
        return {
            "target_version": target.get("version"),
            "baseline_source": target.get("source"),
            "target_kind": "exact" if target.get("version") else None,
        }
    if component_id == "vcenter_vcsa_version":
        target = _media_target_version("vcenter_vcsa_version", media_items)
        return {
            "target_version": target.get("version"),
            "baseline_source": target.get("source"),
            "target_kind": "exact" if target.get("version") else None,
        }
    approved = [str(value) for value in (baseline_component or {}).get("approved") or [] if value]
    if approved:
        return {
            "target_version": approved[0],
            "baseline_source": f"{_rel(BASELINE_PATH)} approved",
            "target_kind": "exact",
        }
    minimum = _known_version_or_none((baseline_component or {}).get("minimum"))
    if minimum:
        return {
            "target_version": f">= {minimum}",
            "baseline_source": f"{_rel(BASELINE_PATH)} minimum",
            "target_kind": "minimum",
        }
    return {
        "target_version": None,
        "baseline_source": f"{_rel(BASELINE_PATH)} manual review" if baseline_component else "No baseline configured",
        "target_kind": None,
    }


def _path_status(
    *,
    component_id: str,
    current_version: str | None,
    target_version: str | None,
    target_kind: str | None,
    package_available: bool,
    required_intermediate_versions: list[str],
    missing_evidence: list[str],
) -> str:
    if not current_version:
        if component_id in {
            "cisco_bootloader_rommon",
            "netapp_disk_firmware",
            "netapp_shelf_firmware",
            "netapp_sp_bmc_firmware",
        }:
            return "manual_review"
        return "unknown"
    if not target_version:
        return "manual_review"
    if _version_satisfies_target(current_version, target_version, target_kind):
        return "current"
    if not package_available and _package_required_for_upgrade(component_id):
        return "blocked"
    if required_intermediate_versions:
        return "staged"
    if component_id in {"cisco_ios_xe_version", "hpe_ilo_firmware", "netapp_ontap_version", "esxi_version", "vcenter_vcsa_version"}:
        return "manual_review"
    return "manual_review" if missing_evidence else "unknown"


def _path_disabled_reason(
    *,
    path_status: str,
    component_id: str,
    current_version: str | None,
    target_version: str | None,
    package_available: bool,
    freshness: str,
    missing_evidence: list[str],
) -> str:
    if path_status == "current":
        return "No upgrade is needed; apply stays disabled."
    if path_status == "manual_review" and missing_evidence:
        return f"Manual review required: missing {', '.join(missing_evidence)}."
    if not current_version:
        return "Scan needed: current version evidence is missing."
    if not target_version:
        return "Manual review required: target baseline evidence is missing."
    if path_status == "blocked" and not package_available:
        return "Blocked: a matching local package/media item is required before planning apply."
    if freshness in {"stale", "historical", "not_checked", "unknown"}:
        return "Apply disabled: evidence is not fresh live inventory."
    if path_status in {"direct", "staged"}:
        return "Apply disabled: confirmation gates and vendor path validation are not implemented in this lane."
    if missing_evidence:
        return f"Manual review required: missing {', '.join(missing_evidence)}."
    return f"Manual review required before {UPGRADE_COMPONENT_META[component_id]['component_label']} can be actionable."


def _path_next_action(path_status: str, component_id: str, disabled_reason: str) -> str:
    label = UPGRADE_COMPONENT_META[component_id]["component_label"]
    if path_status == "current":
        return f"No {label} upgrade needed; rescan before any future apply work."
    if path_status == "unknown":
        return f"Scan needed: run {UPGRADE_COMPONENT_META[component_id]['scan_action_id']} to detect the current version."
    if path_status == "blocked":
        return disabled_reason
    if path_status == "staged":
        return f"Review staged {label} upgrade plan and required intermediate versions."
    if path_status == "direct":
        return f"Review direct {label} upgrade plan; apply remains disabled until all gates are present."
    return f"Manual review: record the approved {label} baseline and vendor upgrade-path evidence."


def _missing_path_evidence(
    *,
    current_version: str | None,
    target_version: str | None,
    baseline_component: dict[str, Any] | None,
    component_id: str,
) -> list[str]:
    missing: list[str] = []
    if not current_version:
        missing.append("current version")
    if not target_version:
        missing.append("target baseline")
    if component_id == "cisco_bootloader_rommon" and not current_version:
        missing.append("ROMMON/bootloader inventory")
    if component_id in {"hpe_bios_version", "hpe_smart_array_firmware"} and not (baseline_component or {}).get("minimum") and not (baseline_component or {}).get("approved"):
        missing.append("approved HPE baseline")
    if component_id.startswith("netapp_") and component_id != "netapp_ontap_version":
        if not current_version:
            missing.append("component firmware inventory")
        if not target_version:
            missing.append("component firmware baseline")
    return unique_preserving_order(missing)


def _version_satisfies_target(current_version: str, target_version: str, target_kind: str | None) -> bool:
    target = target_version.replace(">=", "").strip()
    comparison = _compare_versions(current_version, target)
    if target_kind == "minimum" or target_version.strip().startswith(">="):
        return comparison >= 0
    return comparison == 0


def _package_required_for_upgrade(component_id: str) -> bool:
    return component_id in {
        "cisco_ios_xe_version",
        "hpe_ilo_firmware",
        "hpe_bios_version",
        "hpe_smart_array_firmware",
        "esxi_version",
        "netapp_ontap_version",
        "vcenter_vcsa_version",
    }


def _all_media_items() -> list[dict[str, Any]]:
    media = get_media_inventory(directories=tuple(str(path) for path in _media_directories()))
    items = [item.model_dump() for item in media.items]
    return [
        item
        for item in items
        if item.get("category") in {"firmware", "iso"} or _is_firmware_like(item)
    ]


def _package_for_component(
    component_id: str,
    current_version: str | None,
    target_version: str | None,
    media_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    hints = _package_hints(component_id)
    scored = [
        (score, item)
        for item in media_items
        if (score := _package_score_for_component(item, hints, current_version, target_version, component_id)) > 0
    ]
    if not scored:
        return None
    scored.sort(key=lambda value: value[0], reverse=True)
    return scored[0][1]


def _candidate_files_for_component(
    component_id: str,
    current_version: str | None,
    target_version: str | None,
    media_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hints = _package_hints(component_id)
    scored = [
        (score, item)
        for item in media_items
        if (score := _package_score_for_component(item, hints, current_version, target_version, component_id)) > 0
    ]
    scored.sort(key=lambda value: value[0], reverse=True)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, item in scored:
        name = _media_file_name(item)
        key = f"{name}:{_media_file_path(item) or ''}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "file_name": name,
                "file_path": _media_file_path(item),
                "detected_vendor": item.get("detected_vendor"),
                "detected_product": item.get("detected_product")
                or ", ".join(str(value) for value in item.get("product_hints") or [] if value)
                or None,
                "detected_version": item.get("detected_version") or item.get("version_hint"),
                "confidence": item.get("confidence") or ("high" if score >= 10 else "medium"),
            }
        )
    return candidates


def _media_file_name(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    return str(item.get("file_name") or item.get("placeholder_name") or "media item")


def _media_file_path(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    value = item.get("file_path")
    return str(value) if value else None


def _media_target_version(component_id: str, media_items: list[dict[str, Any]]) -> dict[str, str | None]:
    package = _package_for_component(component_id, None, None, media_items)
    if not package:
        return {"version": None, "source": None}
    return {
        "version": _known_version_or_none(package.get("version_hint")),
        "source": f"artifacts/Media {package.get('placeholder_name')}",
    }


def _package_hints(component_id: str) -> tuple[str, ...]:
    return {
        "cisco_ios_xe_version": ("cisco-ios-xe", "cisco", "iosxe", "cat9k"),
        "hpe_ilo_firmware": ("hpe-ilo", "ilo", "hpe-spp", "hpe-sum"),
        "hpe_bios_version": ("hpe-spp", "hpe-sum", "bios"),
        "hpe_smart_array_firmware": ("hpe-spp", "hpe-sum", "smart-array", "raid"),
        "esxi_version": ("vmware-esxi", "esxi"),
        "netapp_ontap_version": ("netapp-ontap", "ontap"),
        "vcenter_vcsa_version": ("vmware-vcenter", "vcsa", "vcenter"),
    }.get(component_id, ())


def _package_score_for_component(
    item: dict[str, Any],
    hints: tuple[str, ...],
    current_version: str | None,
    target_version: str | None,
    component_id: str,
) -> int:
    product_hints = {str(value).lower() for value in item.get("product_hints") or []}
    generation_hints = {str(value).lower() for value in item.get("generation_hints") or []}
    text = " ".join(
        str(value)
        for value in [
            item.get("placeholder_name"),
            item.get("category"),
            item.get("extension"),
            item.get("version_hint"),
            *product_hints,
            *generation_hints,
        ]
        if value
    ).lower()
    score = 0
    for hint in hints:
        if hint.lower() in text or hint.lower() in product_hints:
            score += 4
    if score == 0:
        return 0
    if component_id.startswith("hpe_"):
        if "gen10" in generation_hints:
            score += 3
        if "gen11" in generation_hints:
            score -= 2
    if component_id == "hpe_ilo_firmware" and current_version and "ilo 5" in current_version.lower() and "ilo5" in generation_hints:
        score += 3
    version = _known_version_or_none(item.get("version_hint"))
    target = target_version.replace(">=", "").strip() if target_version else None
    if version and target and _compare_versions(version, target) == 0:
        score += 5
    elif version and current_version and _compare_versions(version, current_version) == 0:
        score += 4
    elif version and target_version and target_version.startswith(">=") and _compare_versions(version, target) >= 0:
        score += 2
    if component_id in {"esxi_version", "vcenter_vcsa_version"} and item.get("category") == "iso":
        score += 2
    if component_id not in {"hpe_bios_version", "hpe_smart_array_firmware"} and item.get("category") == "firmware":
        score += 1
    return score


def _path_source_info(
    component_id: str,
    inventory: dict[str, Any],
    current_version: str | None,
    checked_at: str,
) -> dict[str, str | None]:
    report_versions = _firmware_inventory_report_versions()
    if component_id in {"hpe_ilo_firmware", "hpe_bios_version", "hpe_smart_array_firmware"} and report_versions.get("checked_at"):
        device_id = "raid" if component_id == "hpe_smart_array_firmware" else "ilo"
        live = _component_source_info(device_id, inventory)
        if live["freshness"] == "live":
            return {"source_type": live["source_type"], "freshness": live["freshness"], "last_checked": live["last_scanned"]}
        return {
            "source_type": "historical_evidence",
            "freshness": _freshness("historical_evidence", report_versions.get("checked_at")),
            "last_checked": report_versions.get("checked_at"),
        }
    if component_id in {"hpe_ilo_firmware", "hpe_bios_version", "hpe_smart_array_firmware"}:
        device_id = "raid" if component_id == "hpe_smart_array_firmware" else "ilo"
        live = _component_source_info(device_id, inventory)
        return {"source_type": live["source_type"], "freshness": live["freshness"], "last_checked": live["last_scanned"]}
    if component_id == "cisco_ios_xe_version" or component_id == "cisco_bootloader_rommon":
        cisco = _component_source_info("cisco", inventory)
        return {"source_type": cisco["source_type"], "freshness": cisco["freshness"], "last_checked": cisco["last_scanned"]}
    if component_id.startswith("netapp_"):
        upgrade = _netapp_upgrade_versions()
        if upgrade.get("checked_at"):
            return {
                "source_type": "historical_evidence",
                "freshness": _freshness("historical_evidence", upgrade.get("checked_at")),
                "last_checked": upgrade.get("checked_at"),
            }
        netapp = _component_source_info("netapp", inventory)
        return {"source_type": netapp["source_type"], "freshness": netapp["freshness"], "last_checked": netapp["last_scanned"]}
    if component_id == "esxi_version":
        last_scanned = _report_checked_at(ESXI_MANAGEMENT_VALIDATION_REPORT) or _path_mtime(ESXI_POST_RECOVERY_VALIDATION_JSON)
        source_type = "historical_evidence" if last_scanned else "not_checked"
        return {"source_type": source_type, "freshness": _freshness(source_type, last_scanned), "last_checked": last_scanned}
    if component_id == "vcenter_vcsa_version":
        version = _vcenter_current_version()
        return {
            "source_type": version.get("source_type") or "not_checked",
            "freshness": version.get("freshness") or "not_checked",
            "last_checked": version.get("checked_at") or checked_at if current_version else None,
        }
    return {"source_type": "not_checked", "freshness": "not_checked", "last_checked": None}


def _path_evidence_artifacts(component_id: str) -> list[str]:
    mapping = {
        "cisco_ios_xe_version": SUMMARY_EVIDENCE_ARTIFACTS["cisco"],
        "cisco_bootloader_rommon": SUMMARY_EVIDENCE_ARTIFACTS["cisco"],
        "hpe_ilo_firmware": SUMMARY_EVIDENCE_ARTIFACTS["ilo"],
        "hpe_bios_version": SUMMARY_EVIDENCE_ARTIFACTS["ilo"],
        "hpe_smart_array_firmware": SUMMARY_EVIDENCE_ARTIFACTS["raid"],
        "esxi_version": SUMMARY_EVIDENCE_ARTIFACTS["esxi"],
        "netapp_ontap_version": SUMMARY_EVIDENCE_ARTIFACTS["netapp"],
        "netapp_disk_firmware": SUMMARY_EVIDENCE_ARTIFACTS["netapp"],
        "netapp_shelf_firmware": SUMMARY_EVIDENCE_ARTIFACTS["netapp"],
        "netapp_sp_bmc_firmware": SUMMARY_EVIDENCE_ARTIFACTS["netapp"],
        "vcenter_vcsa_version": SUMMARY_EVIDENCE_ARTIFACTS["vcenter"],
    }
    extra = {
        "netapp_ontap_version": (
            "artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md",
            "artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md",
        ),
        "vcenter_vcsa_version": (
            "artifacts/codex-runs/vcenter-post-install-validation-report.md",
            "artifacts/codex-runs/vcenter-post-attach-validation-report.md",
        ),
    }.get(component_id, ())
    return [
        path
        for path in (*mapping.get(component_id, ()), *extra)
        if path_exists(REPO_ROOT / path)
    ]


def _paths_for_device(device_id: str, upgrade_paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    component_ids = {
        "cisco": {"cisco_ios_xe_version", "cisco_bootloader_rommon"},
        "ilo": {"hpe_ilo_firmware", "hpe_bios_version"},
        "raid": {"hpe_smart_array_firmware"},
        "netapp": {"netapp_ontap_version", "netapp_disk_firmware", "netapp_shelf_firmware", "netapp_sp_bmc_firmware"},
        "esxi": {"esxi_version"},
        "vcenter": {"vcenter_vcsa_version"},
    }.get(device_id, set())
    return [path for path in upgrade_paths if path.get("component_id") in component_ids]


def _summary_path_rollup(paths: list[dict[str, Any]]) -> dict[str, Any]:
    if not paths:
        return {
            "upgrade_paths": [],
            "path_status": "unknown",
            "target_version": None,
            "package_available": False,
            "package_name": None,
            "required_intermediate_versions": [],
            "prechecks_required": [],
            "reboot_required": False,
            "estimated_impact": "Unknown until firmware/software path is classified.",
            "apply_enabled": False,
            "disabled_reason": "No upgrade path rows are available.",
        }
    statuses = [str(path.get("path_status") or "unknown") for path in paths]
    status = _rollup_path_status(statuses)
    package = next((path for path in paths if path.get("package_available")), None)
    disabled = next((path.get("disabled_reason") for path in paths if path.get("path_status") != "current"), None)
    return {
        "upgrade_paths": paths,
        "path_status": status,
        "target_version": "; ".join(
            f"{path.get('component_label')}: {path.get('target_version')}"
            for path in paths
            if path.get("target_version")
        ) or None,
        "package_available": any(path.get("package_available") for path in paths),
        "package_name": package.get("package_name") if package else None,
        "required_intermediate_versions": unique_preserving_order(
            version
            for path in paths
            for version in path.get("required_intermediate_versions") or []
        ),
        "prechecks_required": unique_preserving_order(
            check
            for path in paths
            for check in path.get("prechecks_required") or []
        ),
        "reboot_required": any(path.get("reboot_required") for path in paths),
        "estimated_impact": next((path.get("estimated_impact") for path in paths if path.get("path_status") != "current"), None)
        or "No upgrade impact expected while current.",
        "apply_enabled": any(path.get("apply_enabled") for path in paths),
        "disabled_reason": str(disabled or "No upgrade is needed; apply stays disabled."),
    }


def _rollup_path_status(statuses: list[str]) -> str:
    for status in ("blocked", "staged", "direct", "unknown", "manual_review"):
        if status in statuses:
            return status
    return "current"


def _upgrade_path_summary(paths: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in UPGRADE_PATH_STATUSES}
    for path in paths:
        status = str(path.get("path_status") or "unknown")
        counts[status if status in counts else "unknown"] += 1
    return {
        "counts": counts,
        "current": counts["current"],
        "manual_review": counts["manual_review"],
        "unknown": counts["unknown"],
        "blocked": counts["blocked"],
        "apply_enabled": any(path.get("apply_enabled") for path in paths),
        "components_needing_review": [
            path["component_label"]
            for path in paths
            if path.get("path_status") in {"manual_review", "unknown"}
        ],
        "blocked_components": [
            path["component_label"]
            for path in paths
            if path.get("path_status") == "blocked"
        ],
    }


def _vcenter_current_version() -> dict[str, str | None]:
    for path in (VCENTER_POST_ATTACH_VALIDATION_JSON, VCENTER_POST_INSTALL_VALIDATION_JSON):
        payload = _read_json_artifact(path)
        checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
        govc = checks.get("govc_authentication") if isinstance(checks.get("govc_authentication"), dict) else {}
        stdout = str(govc.get("stdout") or "")
        version = _regex_version(stdout, r"Version:\s*([0-9.]+)")
        if version:
            return {
                "version": version,
                "build": _regex_version(stdout, r"Build:\s*([0-9]+)"),
                "checked_at": _string_or_none(payload.get("checked_at")) or _path_mtime(path),
                "source_type": str(payload.get("source_type") or "live_probe"),
                "freshness": str(payload.get("freshness") or "current"),
            }
    return {"version": None, "build": None, "checked_at": None, "source_type": "not_checked", "freshness": "not_checked"}


def _sanitize_path(path: dict[str, Any]) -> dict[str, Any]:
    path["path_status"] = path["path_status"] if path["path_status"] in UPGRADE_PATH_STATUSES else "unknown"
    return path


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _esxi_probe_versions(probe: dict[str, Any]) -> list[dict[str, str | None]]:
    versions = (probe.get("vim_service_versions") or {}).get("versions") if isinstance(probe.get("vim_service_versions"), dict) else []
    if not versions:
        return []
    return [{"label": "VIM API", "version": str(max(versions)), "status": probe.get("status") or "ok"}]


def _esxi_report_versions() -> list[dict[str, str | None]]:
    text = _read_text(ESXI_MANAGEMENT_VALIDATION_REPORT)
    if not text:
        return []
    match = re.search(
        r"version/build/API:\s*`([^`]+)`\s*/\s*`([^`]+)`\s*/\s*`([^`]+)`",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return [
            {"label": "ESXi", "version": match.group(1), "status": "passed"},
            {"label": "Build", "version": match.group(2), "status": "passed"},
            {"label": "API", "version": match.group(3), "status": "passed"},
        ]
    match = re.search(r"VMware ESXi\s+([0-9.]+)\s+build-([0-9]+)", text, flags=re.IGNORECASE)
    if match:
        return [
            {"label": "ESXi", "version": match.group(1), "status": "passed"},
            {"label": "Build", "version": match.group(2), "status": "passed"},
        ]
    return []


def _existing_summary_artifacts(device_id: str) -> list[str]:
    existing: list[str] = []
    for path in SUMMARY_EVIDENCE_ARTIFACTS.get(device_id, ()):
        if path_exists(REPO_ROOT / path):
            existing.append(path)
    return existing


def _freshness(source_type: str, checked_at: str | None) -> str:
    if not checked_at or source_type == "not_checked":
        return "not_checked"
    parsed = _parse_datetime(checked_at)
    if parsed and (datetime.now(UTC) - parsed).total_seconds() > FIRMWARE_SUMMARY_STALE_AFTER_SECONDS:
        return "stale"
    if source_type == "historical_evidence":
        return "historical"
    return "live"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _report_checked_at(path: Path) -> str | None:
    text = _read_text(path)
    if not text:
        return _path_mtime(path)
    for label in ("Checked", "Checked at", "Generated", "Date"):
        value = _report_scalar(text, label)
        if value:
            return value.strip(" `")
    return _path_mtime(path)


def _report_scalar(text: str, label: str) -> str | None:
    escaped = re.escape(label)
    match = re.search(rf"^\s*(?:-\s*)?{escaped}:\s*`?(.+?)`?\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip(" `") if match else None


def _path_mtime(path: Path) -> str | None:
    modified_at = path_mtime(path) if path_exists(path) else None
    if modified_at is None:
        return None
    return datetime.fromtimestamp(modified_at, UTC).isoformat()


def _read_text(path: Path) -> str:
    if not path_exists(path):
        return ""
    return safe_read_text(path, errors="strict")


def _read_json_artifact(path: Path) -> dict[str, Any]:
    return read_json_object(path)


def _string_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _device_summary(components: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for component in components:
        key = _device_key(component["device"])
        entry = summary.setdefault(key, {"status": "passed", "components": []})
        entry["components"].append(component)
        statuses = [item["status"] for item in entry["components"]]
        entry["status"] = _rollup_status(statuses)
    return summary


def _rollup_status(statuses: list[str]) -> str:
    for status in ("blocked", "waived", "warning", "not_configured_yet", "unknown"):
        if status in statuses:
            return status
    return "passed"


def _device_key(device: str) -> str:
    lower = device.lower()
    if "cisco" in lower:
        return "cisco"
    if "netapp" in lower:
        return "netapp"
    return "ilo"


def _blocker_text(component: dict[str, Any]) -> str:
    return (
        f"{component['device']} {component['label']}: current "
        f"{component.get('current_version') or 'unknown'}, required "
        f"{component.get('required_version') or ', '.join(component.get('approved_versions') or []) or 'manual approval'}; "
        f"{component['reason']} Next action: {component['next_action']}"
    )


def _overall_message(status: str) -> str:
    if status == "passed":
        return "Firmware compliance gate passed."
    if status == "waived":
        return "Firmware compliance gate has active waiver coverage."
    if status == "warning":
        return "Firmware compliance gate has warnings; review before continuing."
    return "Firmware compliance gate is blocking major configuration workflows."


def _next_safe_action(status: str, components: list[dict[str, Any]]) -> str:
    if status == "blocked":
        blocked = next((component for component in components if component["status"] == "blocked"), None)
        if blocked and blocked["id"] == "cisco_ios_xe_version":
            return "Run Cisco firmware inventory from console."
        return blocked["next_action"] if blocked else "Resolve firmware blockers or create an explicit waiver."
    if status == "waived":
        return "Proceed only within the documented waiver scope and review the waiver report."
    return "Review firmware compliance evidence before running major configuration workflows."


def _waiver_applies(waiver: dict[str, Any], component: dict[str, Any]) -> bool:
    if not waiver.get("active"):
        return False
    scope = str(waiver.get("scope") or "").lower()
    if scope in {"all", "*", "firmware", "lab"}:
        return True
    return component["id"].lower() in scope or str(component.get("device", "")).lower() in scope


def _expired(value: str) -> bool:
    try:
        expires = date.fromisoformat(value[:10])
    except ValueError:
        return True
    return expires < datetime.now(UTC).date()


def _load_local_waiver() -> dict[str, Any] | None:
    if not path_exists(LOCAL_WAIVER_PATH):
        return None
    payload = read_json_object(LOCAL_WAIVER_PATH)
    return {
        "source": "artifact",
        "confirm": str(payload.get("confirm") or payload.get("FIRMWARE_WAIVER_CONFIRM") or ""),
        "reason": str(payload.get("reason") or payload.get("FIRMWARE_WAIVER_REASON") or ""),
        "expires": str(payload.get("expires") or payload.get("FIRMWARE_WAIVER_EXPIRES") or ""),
        "scope": str(payload.get("scope") or payload.get("FIRMWARE_WAIVER_SCOPE") or ""),
    }


def _media_directories() -> list[Path]:
    paths = [REPO_ROOT / "artifacts" / "Media"]
    for directory in settings.media_inventory_dirs:
        path = Path(directory).expanduser()
        if path not in paths:
            paths.append(path)
    return paths


def _is_firmware_like(item: dict[str, Any]) -> bool:
    if item.get("category") == "firmware":
        return True
    extension = str(item.get("extension") or "").lower()
    return extension in {".bin", ".rom", ".fw", ".fwpkg", ".scexe", ".firmware", ".tgz", ".zip", ".image"}


def _matches_product_hint(item: dict[str, Any], hints: tuple[str, ...]) -> bool:
    expected = {hint.lower() for hint in hints}
    product_hints = {str(hint).lower() for hint in item.get("product_hints") or []}
    generation_hints = {str(hint).lower() for hint in item.get("generation_hints") or []}
    return bool((product_hints | generation_hints) & expected)


def _inventory_markdown(inventory: dict[str, Any]) -> str:
    live = inventory["live_inventory"]
    media = inventory["media_inventory"]
    return "\n".join(
        [
            "# Firmware Inventory Report",
            "",
            f"Checked: {inventory['checked_at']}",
            f"Provider mode: {inventory['provider_mode']}",
            "",
            "## Live Inventory",
            "",
            f"- iLO firmware: {live['ilo'].get('ilo_firmware') or 'unknown'}",
            f"- HPE BIOS: {live['ilo'].get('bios_version') or 'unknown'}",
            f"- HPE Smart Array: {live['ilo'].get('smart_array_firmware') or 'unknown'}",
            f"- Cisco IOS XE: {live['cisco'].get('ios_xe_version') or 'unknown'}",
            f"- Cisco bootloader/ROMMON: {live['cisco'].get('bootloader_rommon') or 'unknown'}",
            f"- ONTAP: {live['netapp'].get('ontap_version') or 'unknown'}",
            f"- NetApp disk firmware: {live['netapp'].get('disk_firmware') or 'unknown'}",
            f"- NetApp shelf firmware: {live['netapp'].get('shelf_firmware') or 'unknown'}",
            f"- NetApp SP/BMC firmware: {live['netapp'].get('sp_bmc_firmware') or 'unknown'}",
            "",
            "## Local Media",
            "",
            f"- Firmware/package candidates: {media['candidate_count']}",
            f"- HPE candidates: {media['grouped_counts'].get('hpe', 0)}",
            f"- Cisco candidates: {media['grouped_counts'].get('cisco', 0)}",
            f"- NetApp candidates: {media['grouped_counts'].get('netapp', 0)}",
            "",
        ]
    )


def _compliance_markdown(compliance: dict[str, Any]) -> str:
    lines = [
        "# Firmware Compliance Report",
        "",
            f"Checked: {compliance['checked_at']}",
            f"Provider mode: {compliance['provider_mode']}",
            f"Scope: {compliance.get('scope', 'full')}",
            f"Status: {compliance['status']}",
        f"Message: {compliance['message']}",
        "",
        "## Components",
        "",
    ]
    for component in compliance["components"]:
        lines.extend(
            [
                f"### {component['device']} - {component['label']}",
                "",
                f"- Status: {component['status']}",
                f"- Current version: {component.get('current_version') or 'unknown'}",
                f"- Required/minimum: {component.get('required_version') or 'manual approval'}",
                f"- Approved: {', '.join(component.get('approved_versions') or []) or 'none listed'}",
                f"- Reason: {component['reason']}",
                f"- Next action: {component['next_action']}",
                "",
            ]
        )
    return "\n".join(lines)


def _waiver_markdown(waiver: dict[str, Any], compliance: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Firmware Waiver Report",
            "",
            f"Checked: {compliance['checked_at']}",
            f"Active: {waiver.get('active')}",
            f"Source: {waiver.get('source')}",
            f"Scope: {waiver.get('scope') or 'none'}",
            f"Expires: {waiver.get('expires') or 'none'}",
            f"Reason: {waiver.get('reason') or 'none'}",
            "",
            "Errors:",
            *[f"- {error}" for error in waiver.get("errors", [])],
            "",
        ]
    )


def _summary(compliance: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": compliance["provider_id"],
        "status": compliance["status"],
        "checked_at": compliance["checked_at"],
        "devices": {
            key: {"status": value["status"], "component_count": len(value["components"])}
            for key, value in compliance["devices"].items()
        },
        "blockers": compliance["blockers"],
        "warnings": compliance["warnings"],
        "waiver": compliance["waiver"],
        "reports": compliance["reports"],
        "upgrade_path_summary": compliance.get("upgrade_path_summary", {}),
    }


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(
        payload,
        [
            settings.ilo_test_host,
            settings.ilo_test_username,
            settings.ilo_test_password,
            settings.cisco_target_ip,
            settings.cisco_test_username,
            settings.cisco_test_password,
            settings.cisco_enable_password,
            settings.netapp_api_username,
            settings.netapp_api_password,
        ],
    )
