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
from app.services.status_source import attach_status_source

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
    inventory = {
        "provider_id": "firmware-compliance",
        "status": "completed",
        "message": "Firmware inventory collected from cached/live provider evidence and local media metadata.",
        "provider_mode": settings.provider_mode,
        "checked_at": datetime.now(UTC).isoformat(),
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
    source_type = "live_cached" if any(inventory["last_probe_times"].values()) else "not_checked"
    return _sanitize(
        attach_status_source(
            inventory,
            source_type=source_type,
            checked_at=inventory["checked_at"] if source_type == "live_cached" else None,
            recheck_command="make provider-lab-firmware-inventory",
            evidence_artifacts=[str(INVENTORY_REPORT.relative_to(REPO_ROOT))],
        )
    )


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
    components = [
        _classify_component(component, inventory, waiver)
        for component in baseline.get("components", [])
    ]
    for component in components:
        component["in_scope"] = _component_in_scope(component["id"], normalized_scope)
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
        "checked_at": datetime.now(UTC).isoformat(),
        "provider_mode": settings.provider_mode,
        "scope": normalized_scope,
        "baseline": {
            "baseline_id": baseline.get("baseline_id", "real-lab"),
            "path": str(BASELINE_PATH.relative_to(REPO_ROOT)),
        },
        "waiver": waiver,
        "inventory": inventory,
        "components": components,
        "devices": _device_summary(components),
        "blockers": blockers,
        "warnings": warnings,
        "next_safe_action": _next_safe_action(overall_status, scoped_components),
        "apply_enabled": overall_status in {"passed", "waived", "warning"},
        "reports": {
            "inventory": str(INVENTORY_REPORT.relative_to(REPO_ROOT)),
            "compliance": str(COMPLIANCE_REPORT.relative_to(REPO_ROOT)),
            "summary": str(COMPLIANCE_SUMMARY.relative_to(REPO_ROOT)),
            "waiver": str(WAIVER_REPORT.relative_to(REPO_ROOT)) if waiver.get("active") else None,
        },
    }
    source_type = "live_cached" if inventory.get("source_type") == "live_cached" else "not_checked"
    return _sanitize(
        attach_status_source(
            result,
            source_type=source_type,
            checked_at=result["checked_at"] if source_type == "live_cached" else None,
            recheck_command="make provider-lab-firmware-compliance",
            evidence_artifacts=[
                str(INVENTORY_REPORT.relative_to(REPO_ROOT)),
                str(COMPLIANCE_REPORT.relative_to(REPO_ROOT)),
                str(COMPLIANCE_SUMMARY.relative_to(REPO_ROOT)),
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
    summaries = [
        _component_firmware_summary(device_id, components, inventory)
        for device_id in ("cisco", "ilo", "raid", "netapp")
    ]
    summaries.append(_esxi_firmware_summary())
    summaries.append(_vcenter_firmware_summary())
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
    INVENTORY_REPORT.write_text(_inventory_markdown(inventory), encoding="utf-8")
    COMPLIANCE_REPORT.write_text(_compliance_markdown(compliance), encoding="utf-8")
    COMPLIANCE_SUMMARY.write_text(json.dumps(_summary(compliance), indent=2) + "\n", encoding="utf-8")
    if compliance.get("waiver", {}).get("active"):
        WAIVER_REPORT.write_text(_waiver_markdown(compliance["waiver"], compliance), encoding="utf-8")
    elif WAIVER_REPORT.exists():
        WAIVER_REPORT.unlink()
    return compliance


def write_waiver_report() -> dict[str, Any]:
    compliance = get_firmware_compliance(refresh_live=False)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    if compliance.get("waiver", {}).get("configured"):
        WAIVER_REPORT.write_text(_waiver_markdown(compliance["waiver"], compliance), encoding="utf-8")
    return compliance


def load_firmware_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        return {"baseline_id": "missing", "components": []}
    return _parse_baseline(BASELINE_PATH.read_text(encoding="utf-8"))


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
        "report": str(WAIVER_REPORT.relative_to(REPO_ROOT)) if configured else None,
    }


def _refresh_live_inventory() -> None:
    if settings.provider_mode != "local-lab-readwrite":
        return
    from app.providers.cisco_ansible import CiscoAnsibleAdapter
    from app.providers.cisco_console import CiscoConsoleAdapter
    from app.providers.ilo_redfish import IloRedfishAdapter

    IloRedfishAdapter(provider_mode="local-lab-readwrite").probe()
    if settings.cisco_mgmt_configured:
        CiscoAnsibleAdapter(provider_mode="local-lab-readwrite").probe()
    else:
        CiscoConsoleAdapter(provider_mode="local-lab-readwrite").firmware_inventory()


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
    mapping = {
        "hpe_ilo_firmware": ilo.get("ilo_firmware"),
        "hpe_bios_version": ilo.get("bios_version"),
        "hpe_smart_array_firmware": ilo.get("smart_array_firmware"),
        "cisco_ios_xe_version": cisco.get("ios_xe_version") or os.getenv("CISCO_CURRENT_IOS_XE_VERSION"),
        "cisco_bootloader_rommon": cisco.get("bootloader_rommon") or os.getenv("CISCO_CURRENT_BOOTLOADER_ROMMON"),
        "netapp_ontap_version": netapp.get("ontap_version"),
        "netapp_disk_firmware": netapp.get("disk_firmware"),
        "netapp_shelf_firmware": netapp.get("shelf_firmware"),
        "netapp_sp_bmc_firmware": netapp.get("sp_bmc_firmware"),
    }
    value = mapping.get(component_id)
    return str(value).strip() if value else None


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
    if not CISCO_FIRMWARE_INVENTORY_REPORT.exists():
        return {}
    try:
        text = CISCO_FIRMWARE_INVENTORY_REPORT.read_text(encoding="utf-8")
    except OSError:
        return {}
    checked_at = datetime.fromtimestamp(CISCO_FIRMWARE_INVENTORY_REPORT.stat().st_mtime, UTC).isoformat()
    return {
        "status": _report_field(text, "Status"),
        "source": _report_field(text, "Source") or "cisco-firmware-inventory-report",
        "ios_xe_version": _report_field(text, "IOS XE version"),
        "bootloader_rommon": _report_field(text, "Bootloader/ROMMON"),
        "checked_at": checked_at,
    }


def _report_field(text: str, label: str) -> str | None:
    escaped = re.escape(label)
    match = re.search(rf"^\s*-\s*{escaped}:\s*(.+?)\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip(" `") if match else None


def _netapp_versions(probe: dict[str, Any]) -> dict[str, Any]:
    runtime_state = get_netapp_runtime_state()
    console_version = (
        latest_console_ontap_version()
        if settings.provider_mode != "mock"
        else {"version": None, "source": "not_available", "checked_at": None}
    )
    ontap_version = settings.netapp_current_ontap_version or console_version.get("version")
    return {
        "status": "configured" if runtime_state.get("configured") else "not_configured_yet",
        "ontap_version": ontap_version,
        "ontap_version_source": "configured_placeholder"
        if settings.netapp_current_ontap_version
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
    return [str(item) for item in value if item] if isinstance(value, list) else []


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
    commands = probe.get("safe_show_commands")
    if not isinstance(commands, list):
        commands = probe.get("command_results")
        if isinstance(commands, dict):
            commands = [
                {"command": command_name, **payload}
                for command_name, payload in commands.items()
                if isinstance(payload, dict)
            ]
    if not isinstance(commands, list):
        return None
    for item in commands:
        if not isinstance(item, dict) or item.get("command") != command:
            continue
        value = item.get(key)
        if value:
            return str(value)
    return None


def _compare_versions(current: str, minimum: str) -> int:
    left = _version_parts(current)
    right = _version_parts(minimum)
    width = max(len(left), len(right))
    left.extend([0] * (width - len(left)))
    right.extend([0] * (width - len(right)))
    return (left > right) - (left < right)


def _version_parts(value: str) -> list[int]:
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
) -> dict[str, Any]:
    component_ids = SUMMARY_COMPONENTS[device_id]
    selected = [components[component_id] for component_id in component_ids if component_id in components]
    source = _component_source_info(device_id, inventory)
    compliance_status = _summary_compliance_status(selected)
    blocker = _summary_blocker(compliance_status, selected, source)
    severity = _summary_severity(compliance_status, source["freshness"])
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


def _esxi_firmware_summary() -> dict[str, Any]:
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
    }


def _vcenter_firmware_summary() -> dict[str, Any]:
    last_scanned = _report_checked_at(VCENTER_NETAPP_READINESS_REPORT)
    source_type = "cached_live" if last_scanned else "not_checked"
    freshness = _freshness(source_type, last_scanned)
    configured = bool(settings.vcenter_configured)
    compliance_status = "cannot_verify" if configured else "not_configured"
    blocker = "live scan not run" if configured else "not configured yet"
    return {
        "device_id": "vcenter",
        "label": SUMMARY_LABELS["vcenter"],
        "component_type": SUMMARY_COMPONENT_TYPES["vcenter"],
        "current_versions": [],
        "approved_versions": [],
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
    }


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
    return [
        path
        for path in SUMMARY_EVIDENCE_ARTIFACTS.get(device_id, ())
        if (REPO_ROOT / path).exists()
    ]


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
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


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
    if not LOCAL_WAIVER_PATH.exists():
        return None
    try:
        payload = json.loads(LOCAL_WAIVER_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"source": "artifact", "confirm": "", "reason": "", "expires": "", "scope": ""}
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
