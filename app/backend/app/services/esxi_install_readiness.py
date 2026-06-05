from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.providers.ilo_redfish import PROVIDER_ID
from app.providers.redaction import redact_sensitive
from app.core.config import settings
from app.services.hpe_raid import (
    AFTER_RESET_VALIDATION_REPORT,
    REPO_ROOT,
    SYSTEM_PATH,
    _get_redfish_resource,
    _resource_body_or_error,
    _response_summary,
    validate_hpe_raid_after_reset,
)
from app.services.media_inventory import get_media_inventory
from app.services.esxi_boot_workflow import esxi_boot_workflow_summary

CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
ESXI_INSTALL_READINESS_REPORT = CODEX_RUN_DIR / "esxi-install-readiness-report.md"


def get_esxi_install_readiness(session: Session) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    requests: list[dict[str, Any]] = []
    root = _safe_get("/redfish/v1/", requests)
    system = _safe_get(SYSTEM_PATH, requests)
    manager = _first_manager(requests)
    virtual_media = _virtual_media_readiness(manager, requests)
    boot = _boot_readiness(system)
    bios = _bios_readiness(system, requests)
    media = get_media_inventory()
    iso = _iso_readiness(media.model_dump())
    raid_validation = validate_hpe_raid_after_reset(session)
    boot_workflow = esxi_boot_workflow_summary()

    blockers = []
    warnings = []
    if raid_validation.get("status") != "succeeded":
        blockers.append("RAID validation after reset must succeed before ESXi install readiness.")
    if not virtual_media["supported"]:
        blockers.append("iLO virtual media support was not discovered through Redfish.")
    if not boot["one_time_boot_supported"]:
        blockers.append("One-time boot override support was not discovered through Redfish.")
    if not iso["ready"]:
        blockers.append("No ESXi ISO candidate is ready in local media inventory.")
    if not bios["settings_available"]:
        warnings.append("BIOS settings discovery is unavailable or incomplete.")

    status = "ready" if not blockers else "blocked"
    report = {
        "provider_id": PROVIDER_ID,
        "status": status,
        "message": (
            "Server is ready to plan ESXi ISO virtual-media boot."
            if status == "ready"
            else "ESXi install readiness is blocked until required capabilities and media are present."
        ),
        "checked_at": checked_at,
        "provider_mode": settings.provider_mode,
        "inventory": {
            "redfish_root_status": root.get("status_code"),
            "system_status": system.get("status_code"),
            "manager_status": manager.get("status_code"),
            "model": (_body(system)).get("Model"),
            "power_state": (_body(system)).get("PowerState"),
            "health": ((_body(system)).get("Status") or {}).get("Health")
            if isinstance((_body(system)).get("Status"), dict)
            else None,
        },
        "virtual_media": virtual_media,
        "boot_control": boot,
        "bios": bios,
        "iso": iso,
        "raid_validation": {
            "status": raid_validation.get("status"),
            "message": raid_validation.get("message"),
            "report": str(AFTER_RESET_VALIDATION_REPORT.relative_to(REPO_ROOT)),
            "matches_saved_intent": (
                raid_validation.get("validation", {}).get("matches")
                if isinstance(raid_validation.get("validation"), dict)
                else None
            ),
        },
        "boot_workflow": boot_workflow,
        "milestones": _milestones(status, virtual_media, boot, iso, raid_validation, boot_workflow),
        "requests": requests,
        "blockers": blockers,
        "warnings": warnings,
        "report": str(ESXI_INSTALL_READINESS_REPORT.relative_to(REPO_ROOT)),
        "next_safe_action": _next_safe_action(status, boot_workflow),
    }
    sanitized = _sanitize(report)
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    ESXI_INSTALL_READINESS_REPORT.write_text(_readiness_markdown(sanitized), encoding="utf-8")
    return sanitized


def _safe_get(path: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        response = _get_redfish_resource(path)
    except Exception as exc:
        response = {
            "method": "GET",
            "path": path,
            "status_code": None,
            "error_class": type(exc).__name__,
            "error": str(exc),
        }
    requests.append(_response_summary(response) if response.get("status_code") else response)
    return response


def _first_manager(requests: list[dict[str, Any]]) -> dict[str, Any]:
    root = _safe_get("/redfish/v1/", requests)
    manager_path = _odata_id(_body(root).get("Managers")) or "/redfish/v1/Managers/"
    collection = _safe_get(manager_path, requests)
    members = _body(collection).get("Members")
    if isinstance(members, list) and members:
        member_path = _odata_id(members[0])
        if member_path:
            return _safe_get(member_path, requests)
    return _safe_get("/redfish/v1/Managers/1/", requests)


def _virtual_media_readiness(manager: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
    manager_body = _body(manager)
    virtual_media_path = _odata_id(manager_body.get("VirtualMedia"))
    candidate_paths = [path for path in [virtual_media_path, "/redfish/v1/Managers/1/VirtualMedia/"] if path]
    media_members: list[dict[str, Any]] = []
    collection_status = None
    for path in candidate_paths:
        collection = _safe_get(path, requests)
        collection_status = collection.get("status_code")
        members = _body(collection).get("Members")
        if isinstance(members, list):
            for member in members:
                member_path = _odata_id(member)
                if member_path:
                    media = _safe_get(member_path, requests)
                    body = _body(media)
                    media_members.append(
                        {
                            "path": member_path,
                            "status_code": media.get("status_code"),
                            "id": body.get("Id"),
                            "name": body.get("Name"),
                            "media_types": body.get("MediaTypes"),
                            "connected_via": body.get("ConnectedVia"),
                            "inserted": body.get("Inserted"),
                            "image_present": bool(body.get("Image")),
                            "actions": sorted((body.get("Actions") or {}).keys())
                            if isinstance(body.get("Actions"), dict)
                            else [],
                        }
                    )
            if media_members:
                break
    iso_capable = any(
        "CD" in [str(item) for item in (member.get("media_types") or [])]
        or "DVD" in [str(item) for item in (member.get("media_types") or [])]
        for member in media_members
    )
    return {
        "supported": bool(media_members),
        "iso_capable": iso_capable,
        "collection_status": collection_status,
        "devices": media_members,
    }


def _boot_readiness(system: dict[str, Any]) -> dict[str, Any]:
    boot = _body(system).get("Boot")
    boot = boot if isinstance(boot, dict) else {}
    target_values = boot.get("BootSourceOverrideTarget@Redfish.AllowableValues")
    enabled_values = boot.get("BootSourceOverrideEnabled@Redfish.AllowableValues")
    target_values = target_values if isinstance(target_values, list) else []
    enabled_values = enabled_values if isinstance(enabled_values, list) else []
    one_time_supported = "Once" in [str(value) for value in enabled_values]
    evidence = "allowable-values"
    if not enabled_values and "BootSourceOverrideEnabled" in boot and target_values:
        one_time_supported = True
        evidence = "inferred-from-boot-override-fields"
    return {
        "current_power_state": _body(system).get("PowerState"),
        "boot_source_override_target": boot.get("BootSourceOverrideTarget"),
        "boot_source_override_enabled": boot.get("BootSourceOverrideEnabled"),
        "target_allowable_values": target_values,
        "enabled_allowable_values": enabled_values,
        "one_time_boot_supported": one_time_supported,
        "one_time_boot_evidence": evidence,
        "cd_or_usb_boot_supported": any(
            str(value) in {"Cd", "Usb", "UefiTarget", "DVD"}
            for value in target_values
        ),
    }


def _bios_readiness(system: dict[str, Any], requests: list[dict[str, Any]]) -> dict[str, Any]:
    bios_path = _odata_id(_body(system).get("Bios")) or f"{SYSTEM_PATH.rstrip('/')}/Bios/"
    bios = _safe_get(bios_path, requests)
    settings_path = _odata_id(_body(bios).get("@Redfish.Settings"))
    settings_body: dict[str, Any] = {}
    settings_status = None
    if settings_path:
        settings = _safe_get(settings_path, requests)
        settings_body = _body(settings)
        settings_status = settings.get("status_code")
    attributes = _body(bios).get("Attributes")
    return {
        "bios_status": bios.get("status_code"),
        "settings_status": settings_status,
        "settings_available": bool(isinstance(attributes, dict) or settings_body),
        "bios_version": _body(system).get("BiosVersion") or _body(system).get("BIOSVersion"),
        "attribute_count": len(attributes) if isinstance(attributes, dict) else 0,
        "settings_path": settings_path,
    }


def _iso_readiness(media: dict[str, Any]) -> dict[str, Any]:
    items = media.get("items") if isinstance(media.get("items"), list) else []
    iso_items = [item for item in items if isinstance(item, dict) and item.get("category") == "iso"]
    esxi_candidates = [
        item
        for item in iso_items
        if "esxi" in " ".join(
            str(value).lower()
            for value in [
                item.get("placeholder_name"),
                item.get("version_hint"),
                *(item.get("product_hints") or []),
            ]
        )
    ]
    candidates = esxi_candidates
    return {
        "media_inventory_mode": media.get("mode"),
        "iso_count": len(iso_items),
        "esxi_candidate_count": len(esxi_candidates),
        "ready": media.get("mode") == "local" and bool(candidates),
        "selected_placeholder": candidates[0].get("placeholder_name") if candidates else None,
        "warnings": media.get("warnings") or [],
    }


def _milestones(
    status: str,
    virtual_media: dict[str, Any],
    boot: dict[str, Any],
    iso: dict[str, Any],
    raid_validation: dict[str, Any],
    boot_workflow: dict[str, Any],
) -> list[dict[str, Any]]:
    raid_ready = raid_validation.get("status") == "succeeded"
    one_time_boot_status = (boot_workflow.get("one_time_boot") or {}).get("status")
    installer_boot_status = (boot_workflow.get("reset_boot") or {}).get("status")
    return [
        {"id": "raid-reset-validate", "label": "RAID reset/validate works", "status": "complete" if raid_ready else "blocked"},
        {"id": "virtual-media-check", "label": "Virtual media check works", "status": "complete" if virtual_media.get("supported") else "blocked"},
        {"id": "one-time-boot", "label": "One-time boot works", "status": one_time_boot_status if one_time_boot_status != "not_run" else ("ready_to_run" if boot.get("one_time_boot_supported") else "blocked")},
        {"id": "esxi-iso-boots", "label": "ESXi ISO boots", "status": installer_boot_status if installer_boot_status != "not_run" else ("ready_to_run" if status == "ready" else "blocked")},
        {"id": "assisted-esxi-install", "label": "Automated/assisted ESXi install", "status": "future"},
    ]


def _next_safe_action(status: str, boot_workflow: dict[str, Any]) -> str:
    if status != "ready":
        return "Resolve blockers, then rerun provider-lab-esxi-install-readiness."
    reset_status = (boot_workflow.get("reset_boot") or {}).get("status")
    if reset_status == "boot_requested":
        return "Continue with Cisco console and Ethernet bootstrap readiness."
    virtual_media_status = (boot_workflow.get("virtual_media") or {}).get("status")
    if virtual_media_status == "inserted":
        return "Set one-time boot and run the controlled ESXi installer reset workflow."
    media_status = (boot_workflow.get("media_url") or {}).get("status")
    if media_status == "ready":
        return "Insert the selected ESXi ISO through iLO VirtualMedia."
    return "Run the gated media URL, virtual media attach, and one-time boot workflow."


def _body(response: dict[str, Any]) -> dict[str, Any]:
    body = response.get("body")
    return body if isinstance(body, dict) else {}


def _odata_id(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("@odata.id"), str):
        return value["@odata.id"]
    return None


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password])


def _readiness_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ESXi Install Readiness Report",
        "",
        f"Date: {report.get('checked_at')}",
        f"Mode: `{report.get('provider_mode')}`",
        f"Status: {report.get('status')}",
        f"Message: {report.get('message')}",
        "",
        "## Inventory",
        "",
    ]
    inventory = report.get("inventory") or {}
    for key in ("model", "power_state", "health", "redfish_root_status", "system_status", "manager_status"):
        lines.append(f"- {key}: {inventory.get(key)}")
    vm = report.get("virtual_media") or {}
    boot = report.get("boot_control") or {}
    bios = report.get("bios") or {}
    iso = report.get("iso") or {}
    boot_workflow = report.get("boot_workflow") or {}
    lines.extend(
        [
            "",
            "## Capabilities",
            "",
            f"- Virtual media supported: {vm.get('supported')}",
            f"- ISO capable virtual media: {vm.get('iso_capable')}",
            f"- One-time boot supported: {boot.get('one_time_boot_supported')}",
            f"- Boot targets: {', '.join(str(item) for item in boot.get('target_allowable_values') or []) or 'unknown'}",
            f"- BIOS settings available: {bios.get('settings_available')}",
            f"- BIOS version: {bios.get('bios_version')}",
            "",
            "## ISO Readiness",
            "",
            f"- Media inventory mode: {iso.get('media_inventory_mode')}",
            f"- ISO count: {iso.get('iso_count')}",
            f"- ESXi candidate count: {iso.get('esxi_candidate_count')}",
            f"- Selected placeholder: {iso.get('selected_placeholder') or 'none'}",
            "",
            "## Milestones",
            "",
        ]
    )
    for milestone in report.get("milestones") or []:
        lines.append(f"- {milestone.get('label')}: {milestone.get('status')}")
    lines.extend(["", "## Boot Workflow", ""])
    for key, label in (
        ("media_url", "Media URL"),
        ("virtual_media", "Virtual media"),
        ("one_time_boot", "One-time boot"),
        ("reset_boot", "Reset/installer boot"),
    ):
        item = boot_workflow.get(key) or {}
        lines.append(f"- {label}: {item.get('status', 'not_run')} ({item.get('report', 'no report')})")
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- {item}" for item in report.get("blockers") or []] or ["- none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in report.get("warnings") or []] or ["- none"])
    lines.extend(["", "## Next Safe Action", "", f"- {report.get('next_safe_action')}", ""])
    return "\n".join(lines)
