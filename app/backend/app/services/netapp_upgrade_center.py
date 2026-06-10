from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.base import ProviderAction
from app.providers.redaction import redact_sensitive
from app.schemas import MediaInventoryItemRead
from app.services.media_inventory import get_media_inventory
from app.services.netapp_disabled_actions import disabled_netapp_actions
from app.services.netapp_setup_intent import get_netapp_setup_intent
from app.services.netapp_state import get_netapp_runtime_state

PROVIDER_ID = "netapp-ontap"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

UPGRADE_INVENTORY_REPORT = CODEX_RUN_DIR / "netapp-upgrade-inventory-report.md"
UPGRADE_INVENTORY_JSON = CODEX_RUN_DIR / "netapp-upgrade-inventory-redacted.json"
UPGRADE_PLAN_REPORT = CODEX_RUN_DIR / "netapp-ontap-upgrade-plan-report.md"
UPGRADE_PLAN_JSON = CODEX_RUN_DIR / "netapp-ontap-upgrade-plan-redacted.json"
UPGRADE_VALIDATION_REPORT = CODEX_RUN_DIR / "netapp-ontap-upgrade-validation-report.md"
UPGRADE_VALIDATION_JSON = CODEX_RUN_DIR / "netapp-ontap-upgrade-validation-redacted.json"
UPGRADE_APPLY_REPORT = CODEX_RUN_DIR / "netapp-ontap-upgrade-apply-report.md"
UPGRADE_APPLY_JSON = CODEX_RUN_DIR / "netapp-ontap-upgrade-apply-redacted.json"

UPGRADE_CONFIRM_PHRASE = "UPGRADE ONTAP"
UPGRADE_WAIVER_CONFIRM_PHRASE = "WAIVE ONTAP VALIDATION"


def build_netapp_upgrade_inventory(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    runtime_state = get_netapp_runtime_state()
    configured = bool(runtime_state.get("configured"))
    access_configured = bool(settings.netapp_api_username and settings.netapp_api_password)
    media_inventory = get_media_inventory()
    local_packages = [_candidate_from_media(item) for item in media_inventory.items if _is_ontap_media(item)]
    current_version = settings.netapp_current_ontap_version if configured else None
    current_source = "configured_placeholder" if current_version else "unknown"
    blockers = []
    if not configured:
        blockers.append("NetApp cluster management is not configured/reachable yet.")
    if not access_configured:
        blockers.append("NetApp API access values are missing; keep values in .env.local.real-lab.")
    if not current_version:
        blockers.append("Current ONTAP version is unknown until ONTAP/API/CLI discovery can run.")
    if not local_packages:
        blockers.append("No local ONTAP image package is available from MEDIA_INVENTORY_DIRS or artifacts/Media.")
    supported_path_state = _supported_path_state(current_version, _recommended_target(current_version, local_packages), blockers)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "ontap-upgrade-inventory",
        "checked_at": checked_at,
        "status": "not_configured_yet" if not configured else "blocked" if blockers else "ready",
        "message": "NetApp ONTAP upgrade inventory generated. No upgrade command was run.",
        "mode": settings.provider_mode,
        "cluster_management_configured": configured,
        "access_configured": access_configured,
        "current_ontap_version": current_version,
        "current_version_source": current_source,
        "node_image_versions": _node_versions(current_version),
        "cluster_image_repository": {
            "available": False,
            "source_type": "not_checked" if not configured else "live_probe_not_implemented",
            "packages": [],
            "note": "Cluster image repository is not queried until cluster management and access are configured.",
        },
        "local_image_packages": local_packages,
        "media_inventory_mode": media_inventory.mode,
        "media_warnings": list(media_inventory.warnings),
        "sp_bmc_firmware": {
            "status": "not_checked" if not configured else "manual_review",
            "source_type": "not_checked",
            "reboot_recommended_before_upgrade": None,
            "note": "SP/BMC firmware status is reported when ONTAP management access is available.",
        },
        "disk_shelf_firmware": {
            "status": "not_checked" if not configured else "manual_review",
            "source_type": "not_checked",
            "note": "Disk and shelf firmware status is reported when ONTAP management access is available.",
        },
        "upgrade_readiness_state": "blocked" if blockers else "ready_for_plan",
        "supported_path_state": supported_path_state,
        "blockers": blockers,
        "warnings": _inventory_warnings(media_inventory.mode, local_packages),
        "not_attempted": _upgrade_not_attempted(),
        "artifacts": {"report": _rel(UPGRADE_INVENTORY_REPORT), "json": _rel(UPGRADE_INVENTORY_JSON)},
        "next_safe_action": (
            "Complete NetApp setup and add a local ONTAP image package before planning an upgrade."
            if blockers
            else "Generate the ONTAP upgrade plan and run pre-upgrade validation."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(UPGRADE_INVENTORY_JSON, sanitized)
        UPGRADE_INVENTORY_REPORT.write_text(_inventory_markdown(sanitized), encoding="utf-8")
    return sanitized


def build_netapp_upgrade_plan(*, write_report: bool = True) -> dict[str, Any]:
    inventory = build_netapp_upgrade_inventory(write_report=False)
    target_version = settings.netapp_target_ontap_version or _recommended_target(
        inventory.get("current_ontap_version"),
        list(inventory.get("local_image_packages") or []),
    )
    selected_package = _selected_package(list(inventory.get("local_image_packages") or []), target_version)
    validation = _latest_validation()
    blockers = list(inventory.get("blockers") or [])
    if not target_version:
        blockers.append("No target ONTAP version is selected.")
    if selected_package is None:
        blockers.append("No local ONTAP image/package is selected.")
    if validation.get("validation_passed") is not True:
        blockers.append("Pre-upgrade validation has not passed.")
    manual_plan_attached = bool(settings.netapp_upgrade_advisor_plan)
    if not manual_plan_attached:
        blockers.append("Manual Upgrade Advisor/Health Checker plan is not attached.")
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "ontap-upgrade-plan",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp ONTAP upgrade plan generated. No upgrade command was run.",
        "mode": settings.provider_mode,
        "current_version": inventory.get("current_ontap_version"),
        "current_version_source": inventory.get("current_version_source"),
        "target_version": target_version,
        "selected_package": selected_package,
        "package_loaded": False,
        "pre_upgrade_validation": validation,
        "manual_upgrade_advisor_plan": {
            "attached": manual_plan_attached,
            "source": "redacted local path reference" if manual_plan_attached else None,
            "required": True,
        },
        "supported_path_state": inventory.get("supported_path_state"),
        "blockers": _unique(blockers),
        "warnings": [
            "Expected ONTAP commands/API calls are shown for review only.",
            "Use NetApp Upgrade Advisor/Health Checker output before applying a real upgrade.",
        ],
        "expected_commands_or_api_calls": _expected_upgrade_actions(target_version, selected_package),
        "progress_command": "cluster image show-update-progress",
        "post_upgrade_validation_command": "make provider-lab-netapp-ontap-upgrade-validate",
        "sp_bmc_reboot_recommended_before_upgrade": None,
        "apply_command": _upgrade_apply_command(),
        "button_state": _upgrade_button_state(inventory, selected_package, validation, blockers),
        "not_attempted": _upgrade_not_attempted(),
        "artifacts": {"report": _rel(UPGRADE_PLAN_REPORT), "json": _rel(UPGRADE_PLAN_JSON)},
        "next_safe_action": "Resolve blockers, run validation, and keep upgrade apply disabled until all gates pass.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(UPGRADE_PLAN_JSON, sanitized)
        UPGRADE_PLAN_REPORT.write_text(_plan_markdown(sanitized), encoding="utf-8")
    return sanitized


def validate_netapp_upgrade(*, write_report: bool = True) -> dict[str, Any]:
    inventory = build_netapp_upgrade_inventory(write_report=False)
    target_version = settings.netapp_target_ontap_version or _recommended_target(
        inventory.get("current_ontap_version"),
        list(inventory.get("local_image_packages") or []),
    )
    selected_package = _selected_package(list(inventory.get("local_image_packages") or []), target_version)
    setup_intent = get_netapp_setup_intent()
    blockers = list(inventory.get("blockers") or [])
    if setup_intent["missing_fields"]:
        blockers.append("NetApp setup intent is incomplete.")
    if not target_version:
        blockers.append("No target ONTAP version is selected.")
    if selected_package is None:
        blockers.append("No ONTAP image/package is selected.")
    if inventory.get("supported_path_state") in {"blocked", "unknown"}:
        blockers.append("Supported ONTAP upgrade path is not confirmed.")
    warnings = [
        "Pre-upgrade validation is blocked until the cluster is configured and a local image/package is selected.",
        "No package upload, image validation, or upgrade command was run.",
    ]
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "ontap-upgrade-validate",
        "checked_at": _now(),
        "status": "blocked" if blockers else "passed",
        "message": "NetApp ONTAP pre-upgrade validation completed without running upgrade commands.",
        "mode": settings.provider_mode,
        "validation_passed": not blockers,
        "validation_waiver": _upgrade_validation_waiver(),
        "current_version": inventory.get("current_ontap_version"),
        "target_version": target_version,
        "selected_package": selected_package,
        "checks": [
            _check("cluster_management", bool(inventory.get("cluster_management_configured")), "Cluster management configured and reachable."),
            _check("access", bool(inventory.get("access_configured")), "NetApp API access values configured."),
            _check("current_version", bool(inventory.get("current_ontap_version")), "Current ONTAP version discovered."),
            _check("target_package", selected_package is not None, "Local ONTAP image/package selected."),
            _check("supported_path", inventory.get("supported_path_state") not in {"blocked", "unknown"}, "Upgrade path is confirmed."),
            _check("setup_intent", not setup_intent["missing_fields"], "Setup intent complete."),
        ],
        "blockers": _unique(blockers),
        "warnings": warnings,
        "not_attempted": _upgrade_not_attempted(),
        "artifacts": {"report": _rel(UPGRADE_VALIDATION_REPORT), "json": _rel(UPGRADE_VALIDATION_JSON)},
        "next_safe_action": (
            "Resolve validation blockers before the Upgrade button can become ready."
            if blockers
            else "Review the plan and use the exact apply flags only from an attended real-lab session."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(UPGRADE_VALIDATION_JSON, sanitized)
        UPGRADE_VALIDATION_REPORT.write_text(_validation_markdown(sanitized), encoding="utf-8")
    return sanitized


def apply_netapp_upgrade(*, write_report: bool = True) -> dict[str, Any]:
    plan = build_netapp_upgrade_plan(write_report=False)
    validation = _latest_validation()
    waiver = _upgrade_validation_waiver()
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "netapp_ontap_upgrade_apply": os.getenv("NETAPP_ONTAP_UPGRADE_APPLY") == "true",
        "netapp_ontap_upgrade_confirm": os.getenv("NETAPP_ONTAP_UPGRADE_CONFIRM") == UPGRADE_CONFIRM_PHRASE,
        "validation_passed": validation.get("validation_passed") is True,
        "validation_waiver": waiver["active"],
    }
    blockers = _upgrade_apply_blockers(plan, validation, waiver, flag_state)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "ontap-upgrade-apply",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready_to_apply",
        "message": (
            "NetApp ONTAP upgrade apply was refused before any upgrade command."
            if blockers
            else "NetApp ONTAP upgrade gates passed. The operator must launch the guarded ONTAP upgrade executor from an attended session."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": not blockers,
        "flag_state": flag_state,
        "required_flags": _upgrade_required_flags(),
        "current_version": plan.get("current_version"),
        "target_version": plan.get("target_version"),
        "selected_package": plan.get("selected_package"),
        "pre_upgrade_validation": validation,
        "validation_waiver": waiver,
        "expected_commands_or_api_calls": plan.get("expected_commands_or_api_calls") or [],
        "progress_command": plan.get("progress_command"),
        "post_upgrade_validation_command": plan.get("post_upgrade_validation_command"),
        "upgrade_writes_attempted": False,
        "blockers": blockers,
        "warnings": [
            "No secrets are printed or written to the apply report.",
            "No package upload, image update, reboot, takeover/giveback, or upgrade command was run by this blocked apply.",
        ],
        "not_attempted": _upgrade_not_attempted(),
        "artifacts": {"report": _rel(UPGRADE_APPLY_REPORT), "json": _rel(UPGRADE_APPLY_JSON)},
        "next_safe_action": "Resolve apply blockers, rerun validation, and keep the Upgrade button disabled until the state is ready.",
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(UPGRADE_APPLY_JSON, sanitized)
        UPGRADE_APPLY_REPORT.write_text(_apply_markdown(sanitized), encoding="utf-8")
    return sanitized


def get_legacy_upgrade_readiness() -> dict[str, Any]:
    inventory = build_netapp_upgrade_inventory(write_report=False)
    plan = build_netapp_upgrade_plan(write_report=False)
    current_version = inventory.get("current_ontap_version")
    candidates = [_legacy_candidate(candidate, current_version) for candidate in inventory.get("local_image_packages") or []]
    recommended = _recommended_target(current_version, candidates)
    upgrade_chain = [candidate for candidate in candidates if candidate.get("version") == recommended]
    readonly_ack = settings.lab_readonly_ack == "YES"
    blockers = [
        "Upgrade readiness is separate from setup readiness; setup is not ready.",
        "Live NetApp configured state has not verified cluster management reachability.",
        "Node management is planned but not configured.",
        "SVM management and iSCSI LIFs are planned but not live.",
        "Current ONTAP version is not discovered; live controller queries are disabled."
        if not current_version
        else "Current ONTAP version is configured as a local placeholder, not discovered from a controller.",
        "NetApp API credentials are missing." if not inventory.get("access_configured") else "NetApp API credentials are present but not returned.",
        "LAB_READONLY_ACK=YES is missing for future safe probes."
        if not readonly_ack
        else "LAB_READONLY_ACK=YES is present.",
        "ONTAP upgrade actions are disabled; preview only.",
    ]
    removable_warnings = list(inventory.get("media_warnings") or [])
    if not candidates:
        removable_warnings.append("Add ONTAP image media to the configured media inventory directory.")
    if inventory.get("media_inventory_mode") == "sample":
        removable_warnings.append("MEDIA_INVENTORY_DIRS is not configured; ONTAP media matching uses sample metadata only.")
    return {
        "provider_id": PROVIDER_ID,
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "upgrade_enabled": False,
        "setup_ready": False,
        "readiness_scope": "upgrade",
        "current_version_source": "configured" if current_version else "unknown",
        "current_version": current_version,
        "current_version_confidence": "placeholder" if current_version else "unknown",
        "media_inventory_mode": inventory.get("media_inventory_mode"),
        "candidates": candidates,
        "recommended_target": recommended,
        "required_intermediate_versions": [],
        "upgrade_chain": upgrade_chain,
        "blockers": _unique(blockers),
        "warnings": [
            "Offline media preview only. No ONTAP API, SSH, Service Processor, upload, upgrade, or reboot call is made.",
            f"Upgrade button state: {plan.get('button_state')}.",
        ],
        "removable_warnings": _unique(removable_warnings),
        "next_safe_action": "Add sanitized ONTAP image media metadata and keep upgrade disabled until read-only ONTAP discovery confirms the running version.",
        "disabled_actions": _disabled_upgrade_actions(),
    }


def _is_ontap_media(item: MediaInventoryItemRead) -> bool:
    hints = {hint.lower() for hint in item.product_hints}
    if "netapp-ontap" in hints:
        return True
    return item.category in {"firmware", "other"} and item.version_hint is not None and (
        item.extension in {".tgz", ".zip", ".tar", ".gz", ".iso"}
    )


def _candidate_from_media(item: MediaInventoryItemRead) -> dict[str, Any]:
    return {
        "id": item.placeholder_name,
        "category": item.category,
        "product_hint": "netapp-ontap" if "netapp-ontap" in item.product_hints else None,
        "version": item.version_hint,
        "source": item.source,
        "redacted_label": item.placeholder_name,
        "match_confidence": "likely" if "netapp-ontap" in item.product_hints else "weak",
        "loaded": False,
        "warnings": [] if item.version_hint else ["Candidate version could not be parsed from sanitized media metadata."],
    }


def _legacy_candidate(candidate: dict[str, Any], current_version: str | None) -> dict[str, Any]:
    warnings = list(candidate.get("warnings") or [])
    if current_version is None:
        warnings.append("Current ONTAP version is unknown; target comparison is not available.")
    return {
        "id": candidate.get("id"),
        "category": candidate.get("category"),
        "product_hint": candidate.get("product_hint"),
        "version": candidate.get("version"),
        "source": candidate.get("source"),
        "redacted_label": candidate.get("redacted_label"),
        "match_confidence": candidate.get("match_confidence"),
        "warnings": _unique(warnings),
    }


def _recommended_target(current_version: Any, candidates: list[dict[str, Any]]) -> str | None:
    versioned = [candidate for candidate in candidates if _version_key(candidate.get("version")) is not None]
    if not versioned:
        return None
    sorted_candidates = sorted(versioned, key=lambda item: _version_key(item.get("version")) or (), reverse=True)
    current_key = _version_key(str(current_version)) if current_version else None
    if current_key is None:
        return sorted_candidates[0].get("version")
    newer = [item for item in sorted_candidates if (_version_key(item.get("version")) or ()) > current_key]
    return (newer[0] if newer else sorted_candidates[0]).get("version")


def _version_key(version: Any) -> tuple[int, ...] | None:
    if not version:
        return None
    parts: list[int] = []
    for raw in str(version).split("."):
        if not raw.isdigit():
            return None
        parts.append(int(raw))
    return tuple(parts) if parts else None


def _supported_path_state(current_version: Any, target_version: Any, blockers: list[str]) -> str:
    if blockers and not current_version:
        return "unknown"
    if not current_version or not target_version:
        return "unknown"
    current_key = _version_key(current_version)
    target_key = _version_key(target_version)
    if current_key is None or target_key is None:
        return "manual-review"
    if target_key <= current_key:
        return "blocked"
    if len(current_key) >= 2 and len(target_key) >= 2 and target_key[0] == current_key[0] and target_key[1] - current_key[1] <= 1:
        return "direct"
    return "manual-review"


def _selected_package(candidates: list[dict[str, Any]], target_version: str | None) -> dict[str, Any] | None:
    if not candidates:
        return None
    configured_id = settings.netapp_ontap_image_id
    if configured_id:
        for candidate in candidates:
            if candidate.get("id") == configured_id:
                return candidate
    if target_version:
        for candidate in candidates:
            if candidate.get("version") == target_version:
                return candidate
    return candidates[0]


def _node_versions(current_version: str | None) -> list[dict[str, Any]]:
    if not current_version:
        return []
    return [
        {"node": settings.netapp_node_a_name or "node-a", "version": current_version, "source_type": "configured_placeholder"},
        {"node": settings.netapp_node_b_name or "node-b", "version": current_version, "source_type": "configured_placeholder"},
    ]


def _inventory_warnings(mode: str, local_packages: list[dict[str, Any]]) -> list[str]:
    warnings = [
        "Inventory is read/report only. No ONTAP package upload, validation, reboot, or upgrade command is run.",
    ]
    if mode == "sample":
        warnings.append("MEDIA_INVENTORY_DIRS is not configured for this provider mode; sample media metadata is ignored for apply.")
    if not local_packages:
        warnings.append("No local ONTAP image package was found.")
    return warnings


def _expected_upgrade_actions(target_version: str | None, selected_package: dict[str, Any] | None) -> list[dict[str, Any]]:
    package_label = selected_package.get("redacted_label") if selected_package else "no-package-selected"
    return [
        {"phase": "inventory", "command": "cluster image package show", "type": "ONTAP CLI/REST read"},
        {"phase": "load", "command": f"cluster image package get -url <redacted-local-or-upload-source:{package_label}>", "type": "ONTAP package load"},
        {"phase": "validate", "command": f"cluster image validate -version {target_version or '<target-version>'}", "type": "pre-upgrade validation"},
        {"phase": "apply", "command": f"cluster image update -version {target_version or '<target-version>'}", "type": "guarded upgrade"},
    ]


def _check(check_id: str, passed: bool, description: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "passed" if passed else "blocked",
        "description": description,
    }


def _latest_validation() -> dict[str, Any]:
    if not UPGRADE_VALIDATION_JSON.exists():
        return {
            "status": "not_run",
            "validation_passed": False,
            "checked_at": None,
            "source_type": "not_checked",
            "recheck_command": "make provider-lab-netapp-ontap-upgrade-validate",
        }
    try:
        data = json.loads(UPGRADE_VALIDATION_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "unreadable",
            "validation_passed": False,
            "checked_at": None,
            "source_type": "historical_artifact",
            "recheck_command": "make provider-lab-netapp-ontap-upgrade-validate",
        }
    return {
        "status": data.get("status"),
        "validation_passed": data.get("validation_passed") is True,
        "checked_at": data.get("checked_at"),
        "source_type": "historical_artifact",
        "recheck_command": "make provider-lab-netapp-ontap-upgrade-validate",
    }


def _upgrade_validation_waiver() -> dict[str, Any]:
    active = (
        os.getenv("NETAPP_ONTAP_UPGRADE_VALIDATION_WAIVER") == "true"
        and os.getenv("NETAPP_ONTAP_UPGRADE_WAIVER_CONFIRM") == UPGRADE_WAIVER_CONFIRM_PHRASE
    )
    return {
        "active": active,
        "required_flags": [
            "NETAPP_ONTAP_UPGRADE_VALIDATION_WAIVER=true",
            f'NETAPP_ONTAP_UPGRADE_WAIVER_CONFIRM="{UPGRADE_WAIVER_CONFIRM_PHRASE}"',
        ],
        "reason": "explicit waiver present" if active else "no waiver",
    }


def _upgrade_apply_blockers(
    plan: dict[str, Any],
    validation: dict[str, Any],
    waiver: dict[str, Any],
    flag_state: dict[str, Any],
) -> list[str]:
    policy = current_lab_action_policy(settings.provider_mode)
    blockers = [
        blocker
        for blocker in list(plan.get("blockers") or [])
        if not (waiver["active"] and "Pre-upgrade validation has not passed" in str(blocker))
    ]
    blockers.extend(policy.action_blockers("netapp.ontap-upgrade", "firmware_update"))
    if not flag_state["netapp_ontap_upgrade_apply"]:
        blockers.append("NETAPP_ONTAP_UPGRADE_APPLY=true is required.")
    if not flag_state["netapp_ontap_upgrade_confirm"]:
        blockers.append(f'NETAPP_ONTAP_UPGRADE_CONFIRM="{UPGRADE_CONFIRM_PHRASE}" is required.')
    if validation.get("validation_passed") is not True and not waiver["active"]:
        blockers.append("Pre-upgrade validation has not passed and no explicit waiver is present.")
    if not plan.get("current_version"):
        blockers.append("Current ONTAP version is unknown.")
    if not plan.get("target_version"):
        blockers.append("Target ONTAP version is not selected.")
    if plan.get("selected_package") is None:
        blockers.append("Target ONTAP image/package is not selected.")
    return _unique(blockers)


def _upgrade_button_state(
    inventory: dict[str, Any],
    selected_package: dict[str, Any] | None,
    validation: dict[str, Any],
    blockers: list[str],
) -> str:
    if not inventory.get("cluster_management_configured"):
        return "Disabled: NetApp not configured"
    if selected_package is None:
        return "Disabled: no ONTAP image/package"
    if validation.get("status") == "not_run":
        return "Disabled: validation not run"
    if validation.get("validation_passed") is not True:
        return "Disabled: validation failed"
    if blockers:
        return "Disabled: validation failed"
    return "Ready to upgrade"


def _upgrade_apply_command() -> str:
    return (
        'NETAPP_ONTAP_UPGRADE_APPLY=true NETAPP_ONTAP_UPGRADE_CONFIRM="UPGRADE ONTAP" '
        "PROVIDER_MODE=local-lab-readwrite make provider-lab-netapp-ontap-upgrade-apply"
    )


def _upgrade_required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "NETAPP_ONTAP_UPGRADE_APPLY=true",
        f'NETAPP_ONTAP_UPGRADE_CONFIRM="{UPGRADE_CONFIRM_PHRASE}"',
    ]


def _upgrade_not_attempted() -> list[str]:
    return [
        "ONTAP image package upload/load",
        "ONTAP image validate",
        "ONTAP image update",
        "SP/BMC reboot",
        "takeover/giveback",
        "controller reboot",
        "disk or shelf firmware update",
    ]


def _disabled_upgrade_actions() -> list[ProviderAction]:
    return disabled_netapp_actions(
        "upload-ontap-image",
        "stage-upgrade",
        "start-upgrade",
        "reboot-controller",
        "apply-upgrade",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _inventory_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp Upgrade Inventory Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Current ONTAP version: `{payload.get('current_ontap_version') or 'unknown'}`",
        f"- Supported path state: `{payload.get('supported_path_state')}`",
        f"- Local image packages: `{len(payload.get('local_image_packages') or [])}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- No ONTAP upload, validation, upgrade, reboot, or firmware command was run."])
    return "\n".join(lines) + "\n"


def _plan_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp ONTAP Upgrade Plan Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Current version: `{payload.get('current_version') or 'unknown'}`",
        f"- Target version: `{payload.get('target_version') or 'none'}`",
        f"- Package loaded: `{payload.get('package_loaded')}`",
        f"- Button state: `{payload.get('button_state')}`",
        f"- Apply command: `{payload.get('apply_command')}`",
        "",
        "## Expected Commands / API Calls",
    ]
    lines.extend(f"- {item.get('phase')}: `{item.get('command')}`" for item in payload.get("expected_commands_or_api_calls") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- Plan only; no ONTAP upgrade command was run."])
    return "\n".join(lines) + "\n"


def _validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp ONTAP Upgrade Validation Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Validation passed: `{payload.get('validation_passed')}`",
        "",
        "## Checks",
    ]
    lines.extend(f"- {item.get('id')}: `{item.get('status')}`" for item in payload.get("checks") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- Validation only; no upgrade apply command was run."])
    return "\n".join(lines) + "\n"


def _apply_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NetApp ONTAP Upgrade Apply Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Upgrade writes attempted: `{payload.get('upgrade_writes_attempted')}`",
        "",
        "## Required Flags",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- No secrets are written to this report."])
    return "\n".join(lines) + "\n"


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for key, value in os.environ.items()
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie"))
    ]


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
