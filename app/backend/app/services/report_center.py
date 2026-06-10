from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.redaction import redact_sensitive
from app.services.build_verification import get_lab_build_verification
from app.services.esxi_boot_workflow import esxi_boot_workflow_summary
from app.services.firmware_compliance import get_firmware_compliance
from app.services.hpe_raid import (
    REPO_ROOT,
    get_hpe_raid_plan_preview,
    get_hpe_storage_discovery,
)
from app.services.netapp_console_readiness import get_netapp_console_readiness
from app.services.netapp_readiness_comparison import get_netapp_readiness_comparison
from app.services.netapp_real_lab import (
    get_latest_netapp_console_discovery,
    get_latest_netapp_console_state,
    get_netapp_live_state,
    get_netapp_nfs_vcenter_readiness,
)
from app.services.netapp_upgrade_readiness import get_netapp_upgrade_readiness
from app.services.status_source import status_source_metadata


Severity = str
Classification = str

CRITICAL_CLASSIFICATIONS = {"hard_fail", "stale_config"}
WARNING_CLASSIFICATIONS = {"blocked_by_prior_stage", "warning"}
INFO_CLASSIFICATIONS = {"not_configured_yet"}
SUCCESS_CLASSIFICATIONS = {"passed"}
OPEN_STATUSES = {"open", "blocked"}
STATUS_TTL_SECONDS = 24 * 60 * 60

SOURCE_LABELS = {
    "build_verification": "Build Verification",
    "firmware": "Firmware",
    "cisco": "Cisco",
    "ilo": "HPE / iLO",
    "raid": "RAID",
    "esxi": "ESXi",
    "netapp": "NetApp",
    "serial": "Serial Console",
    "toolchain": "Toolchain",
    "lab_profile": "Lab Profile",
}

SOURCE_LINKS = {
    "build_verification": "/verification",
    "firmware": "/firmware",
    "cisco": "/control-center?section=cisco",
    "ilo": "/control-center?section=ilo",
    "raid": "/control-center?section=raid",
    "esxi": "/control-center?section=esxi",
    "netapp": "/run-center?section=netapp",
    "serial": "/control-center",
    "toolchain": "/settings?section=toolchain",
    "lab_profile": "/settings?section=ip-profile",
}

RECHECK_COMMANDS = {
    "build_verification": "make provider-lab-build-verification-live",
    "firmware": "make provider-lab-firmware-compliance",
    "cisco": "make provider-lab-cisco-console-ethernet-readiness",
    "ilo": "make provider-lab-ilo-reachability",
    "raid": "make provider-lab-hpe-raid-plan",
    "esxi": "make provider-lab-esxi-install-readiness",
    "netapp": "make provider-lab-refresh-live-state",
    "serial": "make provider-lab-serial-console-discovery",
    "toolchain": "make provider-lab-toolchain-check",
    "lab_profile": "make provider-lab-build-verification-live",
}

STATIC_ARTIFACTS = {
    "build_verification": [
        "artifacts/codex-runs/build-verification-report.md",
        "artifacts/codex-runs/build-verification-summary-redacted.json",
        "artifacts/codex-runs/build-verification-classification-report.md",
        "artifacts/codex-runs/failure-case-hardening-report.md",
    ],
    "firmware": [
        "artifacts/codex-runs/firmware-inventory-report.md",
        "artifacts/codex-runs/firmware-compliance-report.md",
        "artifacts/codex-runs/firmware-compliance-summary-redacted.json",
        "artifacts/codex-runs/firmware-waiver-report.md",
        "artifacts/codex-runs/firmware-compliance-gate-final-report.md",
    ],
    "cisco": [
        "artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json",
        "artifacts/codex-runs/cisco-4h-lab-run-report.md",
        "artifacts/codex-runs/cisco-console-discovery-report.md",
        "artifacts/codex-runs/cisco-console-ethernet-readiness-report.md",
        "artifacts/codex-runs/cisco-firmware-inventory-report.md",
    ],
    "ilo": [
        "artifacts/codex-runs/ilo-local-readonly-smoke-report.md",
        "artifacts/codex-runs/ilo-local-lab-test-report.md",
        "artifacts/codex-runs/ilo-real-run-report.md",
    ],
    "raid": [
        "artifacts/codex-runs/hpe-raid-discovery-report.md",
        "artifacts/codex-runs/hpe-raid-plan-report.md",
        "artifacts/codex-runs/hpe-raid-apply-report.md",
        "artifacts/codex-runs/hpe-raid-pending-report.md",
        "artifacts/codex-runs/hpe-raid-reset-report.md",
        "artifacts/codex-runs/hpe-raid-after-reset-validation-report.md",
    ],
    "esxi": [
        "artifacts/codex-runs/esxi-install-readiness-report.md",
        "artifacts/codex-runs/esxi-media-url-report.md",
        "artifacts/codex-runs/esxi-virtual-media-report.md",
        "artifacts/codex-runs/esxi-one-time-boot-report.md",
        "artifacts/codex-runs/esxi-installer-boot-report.md",
        "artifacts/codex-runs/esxi-full-rebuild-boot-report.md",
        "artifacts/codex-runs/esxi-management-readiness-report.md",
    ],
    "netapp": [
        "artifacts/codex-runs/netapp-bringup-baseline-report.md",
        "artifacts/codex-runs/netapp-console-current-report.md",
        "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
        "artifacts/codex-runs/netapp-console-autodiscovery-redacted.json",
        "artifacts/codex-runs/netapp-console-state-report.md",
        "artifacts/codex-runs/netapp-console-state-redacted.json",
        "artifacts/codex-runs/netapp-console-login-state-report.md",
        "artifacts/codex-runs/netapp-console-login-state-redacted.json",
        "artifacts/codex-runs/netapp-management-network-scan-report.md",
        "artifacts/codex-runs/netapp-setup-plan-report.md",
        "artifacts/codex-runs/netapp-live-state-report.md",
        "artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md",
        "artifacts/codex-runs/netapp-nfs-vcenter-readiness-redacted.json",
        "artifacts/codex-runs/netapp-bringup-build-verification-report.md",
        "artifacts/codex-runs/netapp-state-automanagement-report.md",
    ],
    "serial": [
        "artifacts/codex-runs/serial-console-discovery-report.md",
        "artifacts/codex-runs/serial-console-discovery-redacted.json",
        "artifacts/codex-runs/serial-console-autodiscovery-final-report.md",
    ],
    "toolchain": ["artifacts/codex-runs/toolchain-availability-report.md"],
    "lab_profile": [
        "artifacts/codex-runs/lab-ip-profile-update-report.md",
        "artifacts/codex-runs/lab-ip-profile-hardening-report.md",
        "artifacts/codex-runs/netapp-lab-profile-plan-report.md",
    ],
}

PAGE_SOURCE_MAP = {
    "dashboard": tuple(SOURCE_LABELS),
    "run-center": ("cisco", "ilo", "raid", "esxi", "netapp", "serial", "build_verification"),
    "control-center": ("cisco", "ilo", "raid", "esxi", "netapp", "serial", "lab_profile"),
    "firmware": ("firmware", "ilo", "cisco", "netapp"),
    "verification": ("build_verification", "lab_profile", "toolchain", "firmware"),
    "reports": tuple(SOURCE_LABELS),
    "settings": ("lab_profile", "toolchain", "build_verification"),
}


def get_report_center(
    session: Session | None = None,
    *,
    source_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    checked_at = _now()
    source_filter = set(source_ids or SOURCE_LABELS.keys())
    issues: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    collectors = {
        "build_verification": _collect_build_verification,
        "firmware": _collect_firmware,
        "cisco": _collect_cisco,
        "ilo": _collect_ilo,
        "raid": lambda: _collect_raid(session),
        "esxi": _collect_esxi,
        "netapp": _collect_netapp,
        "serial": _collect_serial,
    }
    for source_id, collector in collectors.items():
        if source_id not in source_filter:
            continue
        before_count = len(issues)
        try:
            collected = collector()
            issues.extend(collected)
        except Exception as exc:  # pragma: no cover - defensive API isolation
            issues.append(
                _issue(
                    source=source_id,
                    source_stage="report-center",
                    classification="warning",
                    title=f"{SOURCE_LABELS[source_id]} could not be summarized",
                    summary="The report center could not read this local source safely.",
                    problem=f"Local summarizer failed with {exc.__class__.__name__}.",
                    next_action="Open the source page and regenerate or inspect its redacted report.",
                    evidence_artifacts=_existing_artifacts(source_id),
                )
            )
        if len(issues) == before_count:
            issues.append(_source_passed_issue(source_id))

    if "lab_profile" in source_filter:
        _ensure_source_present("lab_profile", issues)
    if "toolchain" in source_filter:
        _ensure_source_present("toolchain", issues)

    issues = [_attach_workflow_link(_sanitize_issue(issue)) for issue in _dedupe_issues(issues)]
    issues.sort(key=_issue_sort_key)
    for source_id in SOURCE_LABELS:
        if source_id in source_filter:
            sources.append(_source_summary(source_id, issues))

    counts = Counter(issue["severity"] for issue in issues)
    classification_counts = Counter(issue["classification"] for issue in issues)
    top_issues = [
        issue
        for issue in issues
        if issue["status"] in OPEN_STATUSES and issue["severity"] in {"critical", "warning"}
    ][:3]
    evidence_artifacts = _unique(
        artifact
        for issue in issues
        for artifact in issue.get("evidence_artifacts", [])
        if artifact
    )
    last_reports = {
        source_id: _latest_existing_artifact(source_id)
        for source_id in SOURCE_LABELS
        if source_id in source_filter
    }

    return {
        "checked_at": checked_at,
        "overall_status": _overall_status(issues),
        "counts": {
            "critical": counts.get("critical", 0),
            "warning": counts.get("warning", 0),
            "info": counts.get("info", 0),
            "success": counts.get("success", 0),
        },
        "classification_counts": dict(classification_counts),
        "top_issues": top_issues,
        "issues": issues,
        "sources": sources,
        "evidence_artifacts": evidence_artifacts,
        "last_reports": last_reports,
        "page_badges": _page_badges(issues),
    }


def get_report_summary(session: Session | None = None) -> dict[str, Any]:
    report = get_report_center(session)
    return {
        "checked_at": report["checked_at"],
        "overall_status": report["overall_status"],
        "counts": report["counts"],
        "classification_counts": report["classification_counts"],
        "top_issues": report["top_issues"],
        "sources": report["sources"],
        "page_badges": report["page_badges"],
    }


def _collect_build_verification() -> list[dict[str, Any]]:
    payload = _dict(get_lab_build_verification())
    checked_at = _optional_str(payload.get("checked_at"))
    payload_source_type = _optional_str(payload.get("source_type")) or _default_source_type(checked_at)
    artifacts = _artifact_values(payload)
    issues: list[dict[str, Any]] = []
    if payload.get("status") == "not_run":
        return [
            _issue(
                source="build_verification",
                source_stage="certification",
                classification="not_configured_yet",
                title="Build Verification has not run",
                summary="The certification report has not been generated yet.",
                problem="No redacted Build Verification payload is available.",
                next_action="Run Build Verification when certification is in scope.",
                source_report=_first_artifact("build_verification"),
                evidence_artifacts=artifacts or _existing_artifacts("build_verification"),
                last_checked=checked_at,
                source_type="not_checked",
            )
        ]

    lab_profile = _dict(payload.get("lab_ip_profile"))
    issues.extend(_lab_profile_issues(lab_profile, checked_at, source_type=payload_source_type))
    issues.extend(_toolchain_issues(_dict(payload.get("toolchain")), checked_at, source_type=payload_source_type))

    for failure in _records(payload.get("failures")):
        category = _optional_str(failure.get("category")) or "verification"
        if category == "lab-ip-profile":
            continue
        classification = _normalize_classification(failure.get("classification"))
        issues.append(
            _issue(
                source="build_verification",
                source_stage=category,
                classification=classification,
                title=_optional_str(failure.get("ui_message"))
                or f"Build Verification {category} finding",
                summary=_optional_str(failure.get("report_detail"))
                or "Build Verification reported a finding.",
                problem=_optional_str(failure.get("report_detail"))
                or _optional_str(failure.get("ui_message"))
                or "The verification payload reported an issue.",
                next_action=_optional_str(failure.get("next_action"))
                or _optional_str(payload.get("next_safe_action"))
                or "Review the Build Verification report.",
                source_report=_optional_str(_dict(payload.get("artifacts")).get("report")),
                evidence_artifacts=artifacts,
                last_checked=checked_at,
                source_type=payload_source_type,
            )
        )

    if not issues and payload.get("status") in {"completed", "passed", "ready"}:
        issues.append(
            _issue(
                source="build_verification",
                source_stage="certification",
                classification="passed",
                title="Build Verification passed",
                summary="No current Build Verification blockers are reported.",
                problem="No active problem reported.",
                next_action="Continue monitoring certification evidence before execution.",
                source_report=_optional_str(_dict(payload.get("artifacts")).get("report")),
                evidence_artifacts=artifacts,
                last_checked=checked_at,
                source_type=payload_source_type,
            )
        )
    return issues


def _lab_profile_issues(
    lab_profile: dict[str, Any],
    checked_at: str | None,
    *,
    source_type: str | None,
) -> list[dict[str, Any]]:
    if not lab_profile:
        return []
    artifacts = _existing_artifacts("lab_profile")
    issues: list[dict[str, Any]] = []
    active_profile = _dict(lab_profile.get("active_lab_profile"))
    profile_name = _optional_str(active_profile.get("name")) or "active lab profile"
    for mismatch in _records(lab_profile.get("mismatches")):
        field = _optional_str(mismatch.get("field")) or "unknown_field"
        current = _optional_str(mismatch.get("configured"))
        expected = _optional_str(mismatch.get("expected"))
        reason = _optional_str(mismatch.get("reason"))
        details = {
            "field": field,
            "current_value": current,
            "expected_value": expected,
            "source": profile_name,
            "source_kind": active_profile.get("source"),
            "where_it_came_from": "Build Verification active lab profile comparison",
            "where_to_fix": _fix_location_for_field(field),
            "suggested_patch": f"Update {field} to match the active lab profile.",
            "suggested_copy_command": "make provider-lab-build-verification-live",
            "historical_only": False,
            "reason": reason,
        }
        issues.append(
            _issue(
                source="lab_profile",
                source_stage="active-profile",
                classification="stale_config",
                title=f"Stale lab profile value: {field}",
                summary=f"{field} does not match {profile_name}.",
                problem=reason or f"Configured {field} differs from the selected lab profile.",
                next_action=_optional_str(lab_profile.get("next_action"))
                or "Update the active lab profile or local provider environment inputs.",
                source_report="artifacts/codex-runs/lab-ip-profile-update-report.md",
                evidence_artifacts=artifacts,
                linked_page=SOURCE_LINKS["lab_profile"],
                last_checked=checked_at,
                source_type=source_type,
                details=details,
            )
        )
    for stale in _records(lab_profile.get("stale_10_10_8_values")):
        field = _optional_str(stale.get("field")) or "unknown_field"
        issues.append(
            _issue(
                source="lab_profile",
                source_stage="active-profile",
                classification="stale_config",
                title=f"Stale lab profile assumption: {field}",
                summary=f"{field} still carries an old lab-profile value.",
                problem="An active configuration value still references an old lab profile.",
                next_action=_optional_str(lab_profile.get("next_action"))
                or "Remove the stale active value and rerun Build Verification.",
                source_report="artifacts/codex-runs/lab-ip-profile-update-report.md",
                evidence_artifacts=artifacts,
                linked_page=SOURCE_LINKS["lab_profile"],
                last_checked=checked_at,
                source_type=source_type,
                details={
                    "field": field,
                    "current_value": _optional_str(stale.get("value")),
                    "expected_value": "active lab profile value",
                    "where_it_came_from": "Build Verification active value scan",
                    "where_to_fix": _fix_location_for_field(field),
                    "suggested_patch": f"Replace {field} with the active lab profile value.",
                    "suggested_copy_command": "make provider-lab-build-verification-live",
                    "historical_only": False,
                },
            )
        )
    for evidence in _records(lab_profile.get("stale_artifact_evidence")):
        artifact = _optional_str(evidence.get("artifact"))
        issues.append(
            _issue(
                source="lab_profile",
                source_stage="historical-artifact",
                classification="stale_config",
                severity="warning",
                status="stale",
                title="Historical artifact contains stale lab-profile evidence",
                summary="A past report still contains stale addressing evidence.",
                problem="This is historical evidence only unless active configuration still references it.",
                next_action=_optional_str(evidence.get("next_action"))
                or "Regenerate the historical report after active configuration is corrected.",
                source_report=artifact,
                evidence_artifacts=_unique([*artifacts, artifact]),
                linked_page=SOURCE_LINKS["lab_profile"],
                last_checked=checked_at,
                source_type="historical_artifact",
                details={
                    "field": "historical_artifact",
                    "current_value": artifact,
                    "expected_value": "fresh regenerated evidence",
                    "where_it_came_from": "historical artifact scan",
                    "where_to_fix": "Regenerate the source report",
                    "suggested_patch": "Regenerate historical evidence after active config is fixed.",
                    "suggested_copy_command": "make provider-lab-build-verification-live",
                    "historical_only": True,
                },
            )
        )
    if not issues and lab_profile.get("classification") == "passed":
        issues.append(
            _issue(
                source="lab_profile",
                source_stage="active-profile",
                classification="passed",
                title="Lab profile matches active configuration",
                summary="No stale lab-profile values are reported.",
                problem="No active problem reported.",
                next_action="Keep the active lab profile selected before validation.",
                source_report="artifacts/codex-runs/lab-ip-profile-update-report.md",
                evidence_artifacts=artifacts,
                last_checked=checked_at,
                source_type=source_type,
            )
        )
    return issues


def _toolchain_issues(
    toolchain: dict[str, Any],
    checked_at: str | None,
    *,
    source_type: str | None,
) -> list[dict[str, Any]]:
    if not toolchain:
        return []
    issues: list[dict[str, Any]] = []
    required_missing = _strings(toolchain.get("required_missing"))
    optional_missing = _strings(toolchain.get("optional_missing"))
    if required_missing:
        issues.append(
            _issue(
                source="toolchain",
                source_stage="required-tools",
                classification="hard_fail",
                title="Required local toolchain packages are missing",
                summary=", ".join(required_missing),
                problem="A required local tool is unavailable for readiness workflows.",
                next_action=_optional_str(toolchain.get("next_safe_action"))
                or "Install the missing required local packages.",
                source_report="artifacts/codex-runs/toolchain-availability-report.md",
                evidence_artifacts=_existing_artifacts("toolchain"),
                last_checked=checked_at,
                source_type=source_type,
            )
        )
    if optional_missing:
        issues.append(
            _issue(
                source="toolchain",
                source_stage="optional-tools",
                classification="warning",
                title="Optional toolchain packages need review",
                summary=", ".join(optional_missing[:6]),
                problem="Optional tooling is unavailable; related workflows may stay limited.",
                next_action="Install optional tools only for workflows that are in scope.",
                source_report="artifacts/codex-runs/toolchain-availability-report.md",
                evidence_artifacts=_existing_artifacts("toolchain"),
                last_checked=checked_at,
                source_type=source_type,
            )
        )
    if not issues and toolchain.get("status") in {"ready", "passed"}:
        issues.append(
            _issue(
                source="toolchain",
                source_stage="availability",
                classification="passed",
                title="Toolchain readiness passed",
                summary="Required local tools are available.",
                problem="No active problem reported.",
                next_action="Keep tool checks current before real-lab validation.",
                source_report="artifacts/codex-runs/toolchain-availability-report.md",
                evidence_artifacts=_existing_artifacts("toolchain"),
                last_checked=checked_at,
                source_type=source_type,
            )
        )
    return issues


def _collect_firmware() -> list[dict[str, Any]]:
    payload = _dict(get_firmware_compliance(refresh_live=False, scope="full"))
    checked_at = _optional_str(payload.get("checked_at"))
    source_type = _optional_str(payload.get("source_type")) or _default_source_type(checked_at)
    artifacts = _artifact_values(payload) or _existing_artifacts("firmware")
    issues: list[dict[str, Any]] = []
    for component in _records(payload.get("components")):
        if component.get("in_scope") is False:
            continue
        status = _optional_str(component.get("status")) or "unknown"
        if status in {"passed", "waived"}:
            continue
        classification = _firmware_component_classification(component, status)
        label = _optional_str(component.get("label")) or _optional_str(component.get("id")) or "component"
        device = _optional_str(component.get("device")) or "Firmware"
        issues.append(
            _issue(
                source="firmware",
                source_stage=_device_source_stage(device),
                classification=classification,
                title=f"Firmware {display_status(status)}: {label}",
                summary=_optional_str(component.get("reason")) or "Firmware compliance finding.",
                problem=(
                    f"{device} {label}: current "
                    f"{_optional_str(component.get('current_version')) or 'unknown'}, required "
                    f"{_optional_str(component.get('required_version')) or 'manual approval'}."
                ),
                next_action=_optional_str(component.get("next_action"))
                or _optional_str(payload.get("next_safe_action"))
                or "Review firmware compliance evidence.",
                source_report=_optional_str(_dict(payload.get("reports")).get("compliance")),
                evidence_artifacts=artifacts,
                last_checked=checked_at,
                source_type=source_type,
                details={
                    "component_id": component.get("id"),
                    "current_value": component.get("current_version"),
                    "expected_value": component.get("required_version")
                    or component.get("approved_versions"),
                    "where_it_came_from": "Firmware compliance baseline and cached inventory",
                    "where_to_fix": "Firmware / Upgrades",
                },
            )
        )
    if not issues and payload.get("status") in {"passed", "waived"}:
        issues.append(
            _issue(
                source="firmware",
                source_stage="compliance",
                classification="passed",
                title="Firmware compliance passed",
                summary=_optional_str(payload.get("message")) or "Firmware compliance is clear.",
                problem="No active problem reported.",
                next_action=_optional_str(payload.get("next_safe_action"))
                or "Review firmware evidence before major workflow execution.",
                source_report=_optional_str(_dict(payload.get("reports")).get("compliance")),
                evidence_artifacts=artifacts,
                last_checked=checked_at,
                source_type=source_type,
            )
        )
    return issues


def _firmware_component_classification(component: dict[str, Any], status: str) -> str:
    if status == "not_configured_yet":
        return "not_configured_yet"
    if (
        status in {"blocked", "unknown"}
        and not component.get("current_version")
        and "unknown" in (_optional_str(component.get("reason")) or "").lower()
    ):
        return "warning"
    if status in {"blocked", "unknown"}:
        return "hard_fail"
    return "warning"


def _collect_cisco() -> list[dict[str, Any]]:
    details_path = "artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json"
    payload = _read_json_artifact(details_path)
    artifacts = _existing_artifacts("cisco")
    if not payload:
        return [
            _issue(
                source="cisco",
                source_stage="console-readiness",
                classification="not_configured_yet",
                title="Cisco readiness evidence has not run",
                summary="No redacted Cisco run details are available.",
                problem="Cisco console/bootstrap evidence is missing or unreadable.",
                next_action="Run Cisco console discovery or readiness when that stage is in scope.",
                source_report="artifacts/codex-runs/cisco-console-discovery-report.md",
                evidence_artifacts=artifacts,
            )
        ]
    issues = _payload_stage_issues(
        source="cisco",
        source_report=details_path,
        payload=payload,
        default_stage="console-bootstrap",
        evidence_artifacts=artifacts,
    )
    if not issues:
        issues.append(
            _issue(
                source="cisco",
                source_stage="console-bootstrap",
                classification="passed",
                title="Cisco console readiness has usable evidence",
                summary="Cisco redacted run details do not report active blockers.",
                problem="No active problem reported.",
                next_action="Use Cisco controls for the next explicit read-only check.",
                source_report=details_path,
                evidence_artifacts=artifacts,
                last_checked=_optional_str(payload.get("checked_at")),
            )
        )
    return issues


def _collect_ilo() -> list[dict[str, Any]]:
    status = IloRedfishAdapter().health()
    artifacts = _existing_artifacts("ilo")
    issues = _provider_status_issues(
        source="ilo",
        source_stage="readiness",
        status=status.status,
        blockers=status.blockers,
        warnings=status.warnings,
        source_report=_latest_existing_artifact("ilo"),
        evidence_artifacts=artifacts,
        last_checked=status.last_probe_time,
        missing_is_not_configured=True,
    )
    if not issues:
        issues.append(
            _issue(
                source="ilo",
                source_stage="readiness",
                classification="passed",
                title="iLO readiness has no current blocker",
                summary=status.message,
                problem="No active problem reported.",
                next_action="Run the explicit GET-only iLO check before relying on live inventory.",
                source_report=_latest_existing_artifact("ilo"),
                evidence_artifacts=artifacts,
                last_checked=status.last_probe_time,
            )
        )
    return issues


def _collect_raid(session: Session | None) -> list[dict[str, Any]]:
    artifacts = _existing_artifacts("raid")
    discovery = get_hpe_storage_discovery()
    issues = _blocker_warning_issues(
        source="raid",
        source_stage="storage-discovery",
        blockers=discovery.blockers,
        warnings=discovery.warnings,
        source_report="artifacts/codex-runs/hpe-raid-discovery-report.md",
        evidence_artifacts=artifacts,
        next_action=discovery.next_safe_action,
        blocker_classification="blocked_by_prior_stage",
    )
    if session is not None:
        preview = get_hpe_raid_plan_preview(session)
        issues.extend(
            _blocker_warning_issues(
                source="raid",
                source_stage="plan-preview",
                blockers=preview.blockers,
                warnings=preview.warnings,
                source_report="artifacts/codex-runs/hpe-raid-plan-report.md",
                evidence_artifacts=artifacts,
                next_action=preview.next_safe_action,
                blocker_classification="hard_fail",
            )
        )
    if not issues:
        issues.append(
            _issue(
                source="raid",
                source_stage="plan-preview",
                classification="passed",
                title="RAID planning has no current blocker",
                summary="RAID discovery and plan preview did not report active blockers.",
                problem="No active problem reported.",
                next_action="Review RAID intent before any future guarded apply lane.",
                source_report="artifacts/codex-runs/hpe-raid-plan-report.md",
                evidence_artifacts=artifacts,
            )
        )
    return issues


def _collect_esxi() -> list[dict[str, Any]]:
    artifacts = _existing_artifacts("esxi")
    status = EsxiReadonlyAdapter().health()
    issues = _provider_status_issues(
        source="esxi",
        source_stage="management-readiness",
        status=status.status,
        blockers=status.blockers,
        warnings=status.warnings,
        source_report=_latest_existing_artifact("esxi"),
        evidence_artifacts=artifacts,
        last_checked=status.last_probe_time,
        missing_is_not_configured=True,
    )
    for stage, summary in _dict(esxi_boot_workflow_summary()).items():
        stage_status = _optional_str(_dict(summary).get("status")) or "not_run"
        if stage_status == "not_run":
            issues.append(
                _issue(
                    source="esxi",
                    source_stage=stage,
                    classification="not_configured_yet",
                    title=f"ESXi {display_status(stage)} has not run",
                    summary="Saved ESXi boot workflow evidence is not available yet.",
                    problem="No saved report exists for this ESXi stage.",
                    next_action="Run the ESXi readiness workflow when the prior gates are ready.",
                    source_report=_optional_str(_dict(summary).get("report")),
                    evidence_artifacts=artifacts,
                )
            )
        elif stage_status in {"blocked", "failed"}:
            issues.append(
                _issue(
                    source="esxi",
                    source_stage=stage,
                    classification="hard_fail",
                    title=f"ESXi {display_status(stage)} is blocked",
                    summary=_optional_str(_dict(summary).get("message")) or "ESXi stage is blocked.",
                    problem=_optional_str(_dict(summary).get("message")) or "ESXi evidence reports a blocker.",
                    next_action="Resolve the ESXi stage blocker, then rerun readiness.",
                    source_report=_optional_str(_dict(summary).get("report")),
                    evidence_artifacts=artifacts,
                )
            )
    if not issues:
        issues.append(
            _issue(
                source="esxi",
                source_stage="readiness",
                classification="passed",
                title="ESXi readiness has no current blocker",
                summary="ESXi cached readiness and boot workflow summaries are clear.",
                problem="No active problem reported.",
                next_action="Keep ESXi readiness current before install or rebuild planning.",
                source_report=_latest_existing_artifact("esxi"),
                evidence_artifacts=artifacts,
                last_checked=status.last_probe_time,
            )
        )
    return issues


def _collect_netapp() -> list[dict[str, Any]]:
    artifacts = _existing_artifacts("netapp")
    issues: list[dict[str, Any]] = []
    console_readiness = _dict(get_netapp_console_readiness())
    comparison = _dict(get_netapp_readiness_comparison())
    upgrade = _dict(get_netapp_upgrade_readiness())
    latest_discovery = _dict(get_latest_netapp_console_discovery())
    latest_state = _dict(get_latest_netapp_console_state())
    live_state = _dict(get_netapp_live_state())
    nfs_vcenter = _dict(get_netapp_nfs_vcenter_readiness(check_ports=False, write_report=False))

    if not console_readiness.get("netapp_configured"):
        issues.append(
            _issue(
                source="netapp",
                source_stage="setup-readiness",
                classification="not_configured_yet",
                title="NetApp setup is not configured yet",
                summary="NetApp live configured state has not been verified.",
                problem="Planned targets are visible, but live setup validation has not passed.",
                next_action=_optional_str(console_readiness.get("next_safe_action"))
                or "Run NetApp console discovery/read-state, then validate setup when ready.",
                source_report="artifacts/codex-runs/netapp-live-state-report.md",
                evidence_artifacts=artifacts,
                last_checked=_optional_str(_dict(console_readiness.get("runtime_state")).get("checked_at")),
            )
        )
    issues.extend(
        _blocker_warning_issues(
            source="netapp",
            source_stage="console-readiness",
            blockers=_nonfatal_netapp_blockers(console_readiness.get("blockers")),
            warnings=console_readiness.get("warnings"),
            source_report="artifacts/codex-runs/netapp-console-autodiscovery-report.md",
            evidence_artifacts=artifacts,
            next_action=_optional_str(console_readiness.get("next_safe_action")),
            blocker_classification="not_configured_yet",
        )
    )
    for item in _records(comparison.get("comparison_items")):
        item_status = _optional_str(item.get("status")) or "unknown"
        if item_status == "matched":
            continue
        classification = "warning" if item_status == "warning" else "not_configured_yet"
        if item_status == "blocker" and item.get("id") == "existing-data-risk":
            classification = "operator_action_required"
        issues.append(
            _issue(
                source="netapp",
                source_stage="planned-vs-observed",
                classification=classification,
                severity="warning" if classification == "operator_action_required" else None,
                title=f"NetApp review needed: {_optional_str(item.get('label')) or 'planned item'}",
                summary=_optional_str(item.get("observed")) or "Manual observation is missing.",
                problem=_optional_str(item.get("planned")) or "Planned value has not been verified.",
                next_action=_optional_str(item.get("next_action"))
                or _optional_str(comparison.get("next_safe_action"))
                or "Update NetApp manual observations.",
                source_report="artifacts/codex-runs/netapp-lab-profile-plan-report.md",
                evidence_artifacts=artifacts,
                details={
                    "field": item.get("id"),
                    "current_value": item.get("observed"),
                    "expected_value": item.get("planned"),
                    "where_it_came_from": item.get("source") or "NetApp planned-vs-observed comparison",
                    "where_to_fix": "Run Center / NetApp observations",
                },
            )
        )
    for payload, stage, report in [
        (latest_discovery, "console-discovery", "artifacts/codex-runs/netapp-console-autodiscovery-report.md"),
        (latest_state, "console-read-state", "artifacts/codex-runs/netapp-console-state-report.md"),
        (live_state, "live-state", "artifacts/codex-runs/netapp-live-state-report.md"),
        (nfs_vcenter, "nfs-vcenter", "artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md"),
        (upgrade, "upgrade-readiness", "artifacts/codex-runs/netapp-state-automanagement-report.md"),
    ]:
        issues.extend(
            _payload_status_issues(
                source="netapp",
                source_stage=stage,
                payload=payload,
                source_report=report,
                evidence_artifacts=artifacts,
                not_run_classification="not_configured_yet",
                blocker_classification="blocked_by_prior_stage",
            )
        )
    if not issues:
        issues.append(
            _issue(
                source="netapp",
                source_stage="readiness",
                classification="passed",
                title="NetApp readiness has no current blocker",
                summary="NetApp local readiness sources are clear.",
                problem="No active problem reported.",
                next_action="Continue using preview-only NetApp workflows until apply lanes are approved.",
                source_report=_latest_existing_artifact("netapp"),
                evidence_artifacts=artifacts,
            )
        )
    return issues


def _collect_serial() -> list[dict[str, Any]]:
    path = "artifacts/codex-runs/serial-console-discovery-redacted.json"
    payload = _read_json_artifact(path)
    artifacts = _existing_artifacts("serial")
    if not payload:
        return [
            _issue(
                source="serial",
                source_stage="console-discovery",
                classification="not_configured_yet",
                title="Serial console discovery has not run",
                summary="No shared serial console discovery payload is available.",
                problem="Serial evidence is missing or unreadable.",
                next_action="Run the relevant Cisco or NetApp console discovery workflow.",
                source_report="artifacts/codex-runs/serial-console-discovery-report.md",
                evidence_artifacts=artifacts,
            )
        ]
    return _payload_status_issues(
        source="serial",
        source_stage="console-discovery",
        payload=payload,
        source_report=path,
        evidence_artifacts=artifacts,
        not_run_classification="not_configured_yet",
        blocker_classification="warning",
    ) or [
        _issue(
            source="serial",
            source_stage="console-discovery",
            classification="passed",
            title="Serial console discovery has usable evidence",
            summary="Shared serial discovery payload has no current blockers.",
            problem="No active problem reported.",
            next_action="Use the provider-specific console page for follow-up checks.",
            source_report=path,
            evidence_artifacts=artifacts,
            last_checked=_optional_str(payload.get("checked_at")),
        )
    ]


def _payload_stage_issues(
    *,
    source: str,
    source_report: str,
    payload: dict[str, Any],
    default_stage: str,
    evidence_artifacts: list[str],
) -> list[dict[str, Any]]:
    issues = _payload_status_issues(
        source=source,
        source_stage=default_stage,
        payload=payload,
        source_report=source_report,
        evidence_artifacts=evidence_artifacts,
    )
    stages = _dict(payload.get("stages"))
    checked_at = _optional_str(payload.get("checked_at"))
    source_type = _optional_str(payload.get("source_type")) or _default_source_type(checked_at)
    for stage_name, stage_payload in stages.items():
        stage = _dict(stage_payload)
        status = _optional_str(stage.get("status")) or "unknown"
        blockers = _strings(stage.get("blockers"))
        warnings = _strings(stage.get("warnings"))
        if status in {"ready", "passed", "completed", "ok", "succeeded"} and not blockers and not warnings:
            continue
        if status in {"not-attempted", "not_attempted", "skipped"}:
            continue
        issues.extend(
            _blocker_warning_issues(
                source=source,
                source_stage=stage_name,
                blockers=blockers,
                warnings=warnings,
                source_report=source_report,
                evidence_artifacts=evidence_artifacts,
                next_action=_optional_str(stage.get("next_safe_action"))
                or _optional_str(stage.get("next_action"))
                or "Open the source page and review the stage.",
                blocker_classification="hard_fail",
                last_checked=checked_at,
                source_type=source_type,
            )
        )
        if not blockers and not warnings and status not in {"ready", "passed", "completed", "ok", "succeeded"}:
            issues.append(
                _issue(
                    source=source,
                    source_stage=stage_name,
                    classification="warning",
                    title=f"{SOURCE_LABELS[source]} {display_status(stage_name)} needs review",
                    summary=f"Stage status is {display_status(status)}.",
                    problem=_optional_str(stage.get("message")) or f"{stage_name} did not report ready.",
                    next_action=_optional_str(stage.get("next_safe_action"))
                    or "Open the source page and review the stage.",
                    source_report=source_report,
                    evidence_artifacts=evidence_artifacts,
                    last_checked=checked_at,
                    source_type=source_type,
                )
            )
    return issues


def _payload_status_issues(
    *,
    source: str,
    source_stage: str,
    payload: dict[str, Any],
    source_report: str | None,
    evidence_artifacts: list[str],
    not_run_classification: str = "not_configured_yet",
    blocker_classification: str = "hard_fail",
) -> list[dict[str, Any]]:
    status = _optional_str(payload.get("status")) or "unknown"
    blockers = _strings(payload.get("blockers"))
    warnings = _strings(payload.get("warnings"))
    checked_at = _optional_str(payload.get("checked_at"))
    source_type = _optional_str(payload.get("source_type")) or _default_source_type(checked_at)
    if status in {"ready", "passed", "completed", "ok", "succeeded", "waived"} and not blockers and not warnings:
        return []
    if status in {"not_run", "not-run", "not_checked", "not-checked"} and not blockers:
        return [
            _issue(
                source=source,
                source_stage=source_stage,
                classification=not_run_classification,
                title=f"{SOURCE_LABELS[source]} {display_status(source_stage)} has not run",
                summary=_optional_str(payload.get("message")) or "No current report is available.",
                problem="The source report is missing or has not been generated.",
                next_action=_optional_str(payload.get("next_safe_action"))
                or "Run this stage when it is in scope.",
                source_report=source_report,
                evidence_artifacts=evidence_artifacts,
                last_checked=checked_at,
                source_type="not_checked",
            )
        ]
    return _blocker_warning_issues(
        source=source,
        source_stage=source_stage,
        blockers=blockers,
        warnings=warnings,
        source_report=source_report,
        evidence_artifacts=evidence_artifacts,
        next_action=_optional_str(payload.get("next_safe_action"))
        or _optional_str(payload.get("message"))
        or "Open the source page for details.",
        blocker_classification=blocker_classification,
        last_checked=checked_at,
        source_type=source_type,
    )


def _provider_status_issues(
    *,
    source: str,
    source_stage: str,
    status: str,
    blockers: list[str],
    warnings: list[str],
    source_report: str | None,
    evidence_artifacts: list[str],
    last_checked: str | None = None,
    missing_is_not_configured: bool = False,
) -> list[dict[str, Any]]:
    blocker_classification = (
        "not_configured_yet"
        if missing_is_not_configured and status in {"missing-config", "not-configured", "planned-target"}
        else "hard_fail"
    )
    return _blocker_warning_issues(
        source=source,
        source_stage=source_stage,
        blockers=blockers,
        warnings=warnings,
        source_report=source_report,
        evidence_artifacts=evidence_artifacts,
        next_action=RECHECK_COMMANDS[source],
        blocker_classification=blocker_classification,
        last_checked=last_checked,
        source_type="live_cached" if last_checked else "not_checked",
    )


def _blocker_warning_issues(
    *,
    source: str,
    source_stage: str,
    blockers: Any,
    warnings: Any,
    source_report: str | None,
    evidence_artifacts: list[str],
    next_action: str | None,
    blocker_classification: str = "hard_fail",
    last_checked: str | None = None,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for index, blocker in enumerate(_strings(blockers), start=1):
        classification = _normalize_classification(blocker_classification)
        issues.append(
            _issue(
                source=source,
                source_stage=source_stage,
                classification=classification,
                title=f"{SOURCE_LABELS[source]} {display_status(source_stage)} blocked",
                summary=blocker,
                problem=blocker,
                next_action=next_action or RECHECK_COMMANDS[source],
                source_report=source_report,
                evidence_artifacts=evidence_artifacts,
                last_checked=last_checked,
                source_type=source_type,
                id_suffix=str(index),
            )
        )
    for index, warning in enumerate(_strings(warnings), start=1):
        issues.append(
            _issue(
                source=source,
                source_stage=source_stage,
                classification="warning",
                title=f"{SOURCE_LABELS[source]} {display_status(source_stage)} needs review",
                summary=warning,
                problem=warning,
                next_action=next_action or "Review the warning before continuing.",
                source_report=source_report,
                evidence_artifacts=evidence_artifacts,
                last_checked=last_checked,
                source_type=source_type,
                id_suffix=f"warning-{index}",
            )
        )
    return issues


def _issue(
    *,
    source: str,
    source_stage: str,
    classification: Classification,
    title: str,
    summary: str,
    problem: str,
    next_action: str,
    recheck_command: str | None = None,
    source_report: str | None = None,
    evidence_artifacts: list[str] | None = None,
    linked_page: str | None = None,
    last_checked: str | None = None,
    source_type: str | None = None,
    stale_after_seconds: int | None = STATUS_TTL_SECONDS,
    freshness: str | None = None,
    is_current: bool | None = None,
    is_operator_visible: bool | None = None,
    can_auto_fix: bool = False,
    auto_fix_action_id: str | None = None,
    severity: Severity | None = None,
    status: str | None = None,
    details: dict[str, Any] | None = None,
    id_suffix: str | None = None,
) -> dict[str, Any]:
    normalized_classification = _normalize_classification(classification)
    evidence = _unique(evidence_artifacts or [])
    recheck = recheck_command or RECHECK_COMMANDS.get(source, "make test")
    metadata = status_source_metadata(
        source_type=source_type or _default_source_type(last_checked),
        checked_at=last_checked,
        stale_after_seconds=stale_after_seconds,
        recheck_command=recheck,
        evidence_artifacts=evidence,
        is_operator_visible=is_operator_visible,
    )
    if freshness is not None:
        metadata["freshness"] = freshness
    if is_current is not None:
        metadata["is_current"] = is_current
    normalized_severity = severity or _severity_for(normalized_classification, metadata)
    normalized_status = status or _status_for(normalized_classification, metadata)
    return {
        "id": _issue_id(source, source_stage, title, id_suffix),
        "source": source,
        "source_stage": source_stage,
        "severity": normalized_severity,
        "classification": normalized_classification,
        "status": normalized_status,
        "source_type": metadata["source_type"],
        "freshness": metadata["freshness"],
        "ttl_seconds": metadata["ttl_seconds"],
        "stale_after_seconds": metadata["stale_after_seconds"],
        "is_current": metadata["is_current"],
        "is_operator_visible": metadata["is_operator_visible"],
        "title": title,
        "summary": summary,
        "problem": problem,
        "next_action": next_action,
        "recheck_command": metadata["recheck_command"] or recheck,
        "source_report": source_report,
        "evidence_artifacts": metadata["evidence_artifacts"],
        "linked_page": linked_page or SOURCE_LINKS.get(source, "/reports"),
        "last_checked": metadata["checked_at"],
        "can_auto_fix": can_auto_fix,
        "auto_fix_action_id": auto_fix_action_id,
        "details": details or {},
    }


def _source_passed_issue(source_id: str) -> dict[str, Any]:
    return _issue(
        source=source_id,
        source_stage="summary",
        classification="passed",
        title=f"{SOURCE_LABELS[source_id]} has no current issue",
        summary="No current blockers or warnings were normalized for this source.",
        problem="No active problem reported.",
        next_action="Keep report evidence current before continuing.",
        source_report=_latest_existing_artifact(source_id),
        evidence_artifacts=_existing_artifacts(source_id),
    )


def _ensure_source_present(source_id: str, issues: list[dict[str, Any]]) -> None:
    if any(issue["source"] == source_id for issue in issues):
        return
    issues.append(_source_passed_issue(source_id))


def _source_summary(source_id: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    source_issues = [issue for issue in issues if issue["source"] == source_id]
    counts = Counter(issue["severity"] for issue in source_issues)
    status = _overall_status(source_issues)
    representative = _representative_issue(source_issues)
    return {
        "id": source_id,
        "label": SOURCE_LABELS[source_id],
        "status": status,
        "critical": counts.get("critical", 0),
        "warning": counts.get("warning", 0),
        "info": counts.get("info", 0),
        "success": counts.get("success", 0),
        "issue_count": len(source_issues),
        "source_type": representative.get("source_type", "not_checked"),
        "freshness": representative.get("freshness", "unknown"),
        "checked_at": representative.get("last_checked"),
        "is_current": bool(representative.get("is_current")),
        "is_operator_visible": bool(representative.get("is_operator_visible", True)),
        "linked_page": SOURCE_LINKS.get(source_id, "/reports"),
        "recheck_command": RECHECK_COMMANDS.get(source_id),
        "last_report": _latest_existing_artifact(source_id),
    }


def _page_badges(issues: list[dict[str, Any]]) -> dict[str, Any]:
    badges: dict[str, Any] = {}
    for page_id, sources in PAGE_SOURCE_MAP.items():
        page_issues = [issue for issue in issues if issue["source"] in sources]
        critical = [issue for issue in page_issues if issue["severity"] == "critical"]
        warnings = [issue for issue in page_issues if issue["severity"] == "warning"]
        infos = [
            issue
            for issue in page_issues
            if issue["classification"] == "not_configured_yet" and issue["severity"] == "info"
        ]
        successes = [issue for issue in page_issues if issue["severity"] == "success"]
        if critical:
            status = "critical"
            label = "Blocked"
            count = len(critical)
            default_filter = "critical"
        elif warnings:
            status = "warning"
            label = "Needs review"
            count = len(warnings)
            default_filter = "warnings"
        elif infos and not successes:
            status = "not_configured_yet"
            label = "Not configured yet"
            count = len(infos)
            default_filter = "all"
        elif successes:
            status = "success"
            label = "Ready"
            count = len(successes)
            default_filter = "all"
        else:
            status = "neutral"
            label = "No report"
            count = 0
            default_filter = "all"
        badges[page_id] = {
            "page": page_id,
            "status": status,
            "label": label,
            "count": count,
            "critical": len(critical),
            "warning": len(warnings),
            "not_configured_yet": len(infos),
            "success": len(successes),
            "sources": list(sources),
            "default_filter": default_filter,
        }
    return badges


def _overall_status(issues: list[dict[str, Any]]) -> str:
    if any(issue["severity"] == "critical" for issue in issues):
        return "critical"
    if any(issue["severity"] == "warning" for issue in issues):
        return "warning"
    if any(issue["classification"] == "not_configured_yet" for issue in issues):
        return "not_configured_yet"
    if any(issue["severity"] == "success" for issue in issues):
        return "passed"
    return "not_run"


def _severity_for(classification: str, metadata: dict[str, Any]) -> str:
    source_type = metadata.get("source_type")
    is_current = bool(metadata.get("is_current"))
    freshness = metadata.get("freshness")
    if source_type == "not_checked":
        return "info"
    if classification in INFO_CLASSIFICATIONS:
        return "info"
    if source_type in {"historical_artifact", "test_fixture"} or freshness == "stale":
        return "success" if classification in SUCCESS_CLASSIFICATIONS and is_current else "warning"
    if classification in CRITICAL_CLASSIFICATIONS or classification == "operator_action_required":
        return "critical" if is_current else "warning"
    if classification in WARNING_CLASSIFICATIONS:
        return "warning"
    if classification in SUCCESS_CLASSIFICATIONS:
        return "success" if is_current else "info"
    return "warning"


def _status_for(classification: str, metadata: dict[str, Any]) -> str:
    if metadata.get("source_type") == "historical_artifact" or metadata.get("freshness") == "stale":
        return "stale"
    if metadata.get("source_type") == "not_checked":
        return "reviewed"
    if classification == "stale_config":
        return "open" if metadata.get("is_current") else "stale"
    if classification == "blocked_by_prior_stage":
        return "blocked"
    if classification in {"hard_fail", "operator_action_required", "warning"}:
        return "open"
    if classification == "not_configured_yet":
        return "reviewed"
    if classification == "passed":
        return "resolved"
    return "open"


def _normalize_classification(value: Any) -> str:
    text = _optional_str(value) or "warning"
    if text in {
        "hard_fail",
        "stale_config",
        "operator_action_required",
        "blocked_by_prior_stage",
        "not_configured_yet",
        "warning",
        "passed",
    }:
        return text
    if text in {"blocked", "failed", "critical"}:
        return "hard_fail"
    if text in {"ready", "ok", "completed", "succeeded"}:
        return "passed"
    if text in {"not_run", "not_configured", "missing-config", "not-configured"}:
        return "not_configured_yet"
    return "warning"


def _issue_sort_key(issue: dict[str, Any]) -> tuple[int, int, str, str]:
    severity_order = {"critical": 0, "warning": 1, "info": 2, "success": 3}
    classification_order = {
        "hard_fail": 0,
        "stale_config": 1,
        "operator_action_required": 2,
        "blocked_by_prior_stage": 3,
        "warning": 4,
        "not_configured_yet": 5,
        "passed": 6,
    }
    return (
        severity_order.get(issue["severity"], 9),
        classification_order.get(issue["classification"], 9),
        issue["source"],
        issue["title"],
    )


def _default_source_type(last_checked: str | None) -> str:
    return "live_cached" if last_checked else "not_checked"


def _representative_issue(issues: list[dict[str, Any]]) -> dict[str, Any]:
    if not issues:
        return {
            "source_type": "not_checked",
            "freshness": "unknown",
            "last_checked": None,
            "is_current": False,
            "is_operator_visible": True,
        }
    current = [issue for issue in issues if issue.get("is_current")]
    if current:
        return current[0]
    return issues[0]


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for issue in issues:
        deduped.setdefault(issue["id"], issue)
    return list(deduped.values())


def _sanitize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(issue)


def _attach_workflow_link(issue: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.services.workflow_registry import find_workflow_action_for_issue

        link = find_workflow_action_for_issue(issue)
    except Exception:
        link = {}
    return {
        **issue,
        "source_stage_id": link.get("source_stage_id"),
        "source_stage_label": link.get("source_stage_label"),
        "source_action_id": link.get("source_action_id"),
        "source_action_label": link.get("source_action_label"),
        "source_action_link": link.get("source_action_link"),
    }


def _artifact_values(payload: dict[str, Any]) -> list[str]:
    artifacts = []
    for key in ("artifacts", "reports"):
        value = payload.get(key)
        if isinstance(value, dict):
            artifacts.extend(_optional_str(item) for item in value.values())
    return _unique(item for item in artifacts if item)


def _existing_artifacts(source: str) -> list[str]:
    return [artifact for artifact in STATIC_ARTIFACTS.get(source, []) if _repo_path(artifact).exists()]


def _first_artifact(source: str) -> str | None:
    artifacts = STATIC_ARTIFACTS.get(source, [])
    return artifacts[0] if artifacts else None


def _latest_existing_artifact(source: str) -> str | None:
    existing = [artifact for artifact in STATIC_ARTIFACTS.get(source, []) if _repo_path(artifact).exists()]
    if not existing:
        return _first_artifact(source)
    return max(existing, key=lambda artifact: _repo_path(artifact).stat().st_mtime)


def _read_json_artifact(path: str) -> dict[str, Any] | None:
    artifact = _repo_path(path)
    if not artifact.exists():
        return None
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _repo_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _issue_id(source: str, stage: str, title: str, suffix: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{source}-{stage}-{title}".lower()).strip("-")
    if suffix:
        slug = f"{slug}-{suffix}"
    return slug[:180]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _device_source_stage(device: str) -> str:
    lower = device.lower()
    if "cisco" in lower:
        return "cisco"
    if "netapp" in lower:
        return "netapp"
    if "ilo" in lower or "hpe" in lower:
        return "ilo"
    return "compliance"


def _fix_location_for_field(field: str) -> str:
    if field.endswith("_env") or field in {
        "cisco_target_ip_env",
        "ansible_cisco_host_env",
        "netapp_iscsi_lifs_env",
    }:
        return ".env.local.real-lab"
    return "Lab Setup"


def _nonfatal_netapp_blockers(value: Any) -> list[str]:
    blockers = _strings(value)
    calm_fragments = (
        "not been verified",
        "planned",
        "credentials are missing",
        "readonly_ack",
        "bootstrap and configuration actions are disabled",
        "cluster management is planned",
        "node management is planned",
        "svm management",
    )
    return [
        blocker
        for blocker in blockers
        if not any(fragment in blocker.lower() for fragment in calm_fragments)
    ]


def display_status(value: str) -> str:
    return value.replace("_", " ").replace("-", " ")
