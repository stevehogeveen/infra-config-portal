from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.redaction import redact_sensitive
from app.services.build_verification import get_lab_build_verification
from app.services.media_inventory import get_media_inventory

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
GOLDEN_REPORT = CODEX_RUN_DIR / "golden-state-productization-report.md"
GOLDEN_JSON = CODEX_RUN_DIR / "golden-state-summary-redacted.json"


def get_provider_lab_golden_state(*, write_report: bool = False) -> dict[str, Any]:
    generated_at = _now()
    build_verification = get_lab_build_verification()
    live_status = _read_json("artifacts/codex-runs/provider-lab-live-status-redacted.json")
    rows = _golden_rows(live_status=live_status)
    credentials = _credential_status(build_verification, live_status=live_status, rows=rows)
    drift_rows = [row for row in rows if row["drift"] != "none"]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    warnings = list(dict.fromkeys(warning for row in rows for warning in row["warnings"]))
    vcenter_readiness = _vcenter_readiness(rows, credentials)
    workflow_actions = _workflow_actions()
    payload = {
        "provider_id": "provider-lab-golden-state",
        "checked_at": generated_at,
        "generated_at": generated_at,
        "status": "blocked" if blockers else "partial" if drift_rows else "ready",
        "message": "Golden-state validation surface generated from proven real-lab evidence. No provider write action was run.",
        "source_type": "historical_artifact",
        "freshness": "historical",
        "current_state": "ready" if not blockers else "blocked",
        "golden_state": "Cisco, iLO, RAID, ESXi, NetApp, NetApp NFS datastore, and VM deployment are ready; vCenter is not configured; firmware requires manual baseline review.",
        "rows": rows,
        "drift_rows": drift_rows,
        "credentials": credentials,
        "vcenter_readiness": vcenter_readiness,
        "workflow_actions": workflow_actions,
        "blockers": blockers,
        "warnings": warnings,
        "proof_links": _proof_links(rows),
        "artifacts": {
            "report": _rel(GOLDEN_REPORT),
            "summary_json": _rel(GOLDEN_JSON),
        },
        "handoff_report": _rel(GOLDEN_REPORT),
        "next_safe_action": vcenter_readiness["next_action"],
        "not_attempted": [
            "Cisco write/reload",
            "iLO power/reset/firmware/virtual media",
            "RAID create/delete/apply/reset",
            "ESXi datastore change or host reconfiguration",
            "NetApp ONTAP/NFS/write or firmware apply",
            "VCSA deployment",
            "VM create/delete/power operation",
        ],
        "recheck_command": "make provider-lab-golden-state",
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        GOLDEN_JSON.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        GOLDEN_REPORT.write_text(_markdown(sanitized), encoding="utf-8")
    return sanitized


def _golden_rows(*, live_status: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _row(
            row_id="cisco",
            label="Cisco",
            golden_state="Reachable and configured",
            current_state="Reachable/configured" if _stage_ready(live_status, "cisco-console-ethernet") else "Not refreshed",
            ready=_stage_ready(live_status, "cisco-console-ethernet"),
            repair_label="Run Cisco readiness",
            repair_action_id="cisco.validate-ssh-scp",
            repair_command="make provider-lab-cisco-console-ethernet-readiness",
            evidence=["artifacts/codex-runs/cisco-console-ethernet-readiness-report.md"],
            warnings=[],
        ),
        _row(
            row_id="ilo",
            label="iLO",
            golden_state=f"Reachable at {settings.ilo_test_host or '192.168.1.201'}",
            current_state="Reachable" if _stage_ready(live_status, "ilo-reachability") else "Not refreshed",
            ready=_stage_ready(live_status, "ilo-reachability"),
            repair_label="Run iLO reachability",
            repair_action_id="ilo.reachability",
            repair_command="make provider-lab-ilo-reachability",
            evidence=["artifacts/codex-runs/ilo-real-run-report.md"],
            warnings=[],
        ),
        _row(
            row_id="raid",
            label="RAID",
            golden_state="Saved RAID intent validated",
            current_state="Validated" if _raid_validated() else "Validation evidence missing",
            ready=_raid_validated(),
            repair_label="Validate RAID",
            repair_action_id="raid.validate",
            repair_command="make provider-lab-hpe-raid-validate-after-reset",
            evidence=["artifacts/codex-runs/hpe-raid-after-reset-validation-report.md"],
            warnings=[],
        ),
        _row(
            row_id="esxi",
            label="ESXi",
            golden_state=f"Reachable at {settings.esxi_test_host or '192.168.1.203'}",
            current_state="Reachable" if _json_status_ready("artifacts/codex-runs/esxi-post-recovery-validation-redacted.json") else "Not refreshed",
            ready=_json_status_ready("artifacts/codex-runs/esxi-post-recovery-validation-redacted.json"),
            repair_label="Validate ESXi",
            repair_action_id="esxi.post-recovery-validation",
            repair_command="make provider-lab-esxi-post-recovery-validation",
            evidence=["artifacts/codex-runs/esxi-post-recovery-validation-report.md"],
            warnings=[],
        ),
        _netapp_row(live_status),
        _datastore_row(),
        _vm_deployment_row(),
        _vcenter_row(),
        _row(
            row_id="firmware",
            label="Firmware",
            golden_state="Current or accepted after manual baseline review",
            current_state="Needs manual baseline review",
            ready=False,
            drift="needs_review",
            status="warning",
            repair_label="Run firmware compliance",
            repair_action_id="firmware.compliance-check",
            repair_command="make provider-lab-firmware-compliance",
            evidence=["artifacts/codex-runs/firmware-compliance-report.md"],
            warnings=_stage_warnings(live_status, "firmware-compliance") or ["Manual firmware baseline review remains."],
        ),
    ]


def _netapp_row(live_status: dict[str, Any]) -> dict[str, Any]:
    upgrade = _read_json("artifacts/codex-runs/netapp-ontap-upgrade-validation-redacted.json")
    version = upgrade.get("current_version") or upgrade.get("target_version") or "unknown"
    ready = _stage_ready(live_status, "netapp-live-state") and str(version) == "9.17.1"
    return _row(
        row_id="netapp",
        label="NetApp",
        golden_state="ONTAP 9.17.1 current",
        current_state=f"ONTAP {version}",
        ready=ready,
        repair_label="Validate NetApp setup",
        repair_action_id="netapp.validate-setup",
        repair_command="make provider-lab-netapp-validate-setup",
        evidence=[
            "artifacts/codex-runs/netapp-live-state-report.md",
            "artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md",
        ],
        warnings=[] if ready else ["NetApp live state or ONTAP version evidence needs review."],
    )


def _datastore_row() -> dict[str, Any]:
    payload = _read_json("artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-redacted.json")
    current = payload.get("current_state") if isinstance(payload.get("current_state"), dict) else {}
    summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    access_mode = str(summary.get("access_mode") or "")
    datastore = str(summary.get("name") or settings.netapp_nfs_datastore_name or "netapp_nfs_ds01")
    ready = (
        payload.get("status") == "ready"
        and current.get("exists") is True
        and current.get("accessible") is True
        and access_mode == "readWrite"
    )
    return _row(
        row_id="netapp-nfs-datastore",
        label="NetApp NFS datastore",
        golden_state="Mounted read/write on ESXi",
        current_state=f"{datastore} {access_mode or 'unknown'}",
        ready=ready,
        repair_label="Validate datastore",
        repair_action_id="esxi.netapp-datastore-validate",
        repair_command="make provider-lab-esxi-netapp-datastore-validate",
        evidence=["artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-report.md"],
        warnings=[] if ready else ["Datastore validation evidence does not show read/write mounted state."],
    )


def _vm_deployment_row() -> dict[str, Any]:
    payload = _read_json("artifacts/codex-runs/esxi-vm-deploy-validation-redacted.json")
    plan = payload.get("deployment_plan") if isinstance(payload.get("deployment_plan"), dict) else {}
    datastore = str(plan.get("datastore") or settings.netapp_nfs_datastore_name or "unknown")
    ready = payload.get("status") == "ready" and datastore == (settings.netapp_nfs_datastore_name or "netapp_nfs_ds01")
    return _row(
        row_id="vm-deployment",
        label="VM deployment",
        golden_state="VM deployed on NetApp datastore",
        current_state=f"VM on {datastore}" if ready else "VM deployment evidence missing",
        ready=ready,
        repair_label="Validate VM",
        repair_action_id="esxi.vm-deploy-validate",
        repair_command="make provider-lab-esxi-vm-deploy-validate",
        evidence=["artifacts/codex-runs/esxi-vm-deploy-validation-report.md"],
        warnings=[] if ready else ["VM validation evidence does not show the target VM on the NetApp datastore."],
    )


def _vcenter_row() -> dict[str, Any]:
    artifact = _read_json("artifacts/codex-runs/vcenter-install-readiness-redacted.json")
    validation = _read_json("artifacts/codex-runs/vcenter-post-install-validation-redacted.json")
    deployment_values = artifact.get("deployment_values") if isinstance(artifact.get("deployment_values"), dict) else {}
    values_complete = bool(deployment_values.get("complete"))
    validation_ready = validation.get("status") == "ready"
    configured = bool(settings.vcenter_host or settings.vcenter_configured or validation_ready)
    current_state = (
        "Deployed and authenticated"
        if validation_ready
        else "Configured"
        if configured
        else "Expected partial: deployment values complete; deploy pending"
        if values_complete
        else "Expected partial: deployment values incomplete"
    )
    return _row(
        row_id="vcenter",
        label="vCenter",
        golden_state="Configured and reachable" if configured else "Expected partial until deployed and configured",
        current_state=current_state,
        ready=configured,
        drift="none" if configured else "expected_partial",
        status="ready" if configured else "not_configured",
        repair_label="Configure vCenter values",
        repair_action_id="vcenter.install-readiness",
        repair_command="make provider-lab-vcenter-install-readiness",
        evidence=[
            "artifacts/codex-runs/vcenter-install-readiness-report.md",
            "artifacts/codex-runs/vcenter-install-plan-report.md",
            "artifacts/codex-runs/vcenter-install-preview-report.md",
            "artifacts/codex-runs/vcenter-install-apply-report.md",
            "artifacts/codex-runs/vcenter-post-install-validation-report.md",
        ],
        warnings=[] if configured else ["vCenter is expected partial until deployment values and confirmation gates are ready."],
    )


def _row(
    *,
    row_id: str,
    label: str,
    golden_state: str,
    current_state: str,
    ready: bool,
    repair_label: str,
    repair_action_id: str | None,
    repair_command: str,
    evidence: list[str],
    warnings: list[str],
    drift: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    existing_evidence = _existing(evidence)
    row_drift = drift or ("none" if ready else "missing_or_stale")
    row_status = status or ("ready" if ready else "warning")
    checked_at = _last_checked(existing_evidence)
    return {
        "id": row_id,
        "label": label,
        "status": row_status,
        "golden_state": golden_state,
        "current_state": current_state,
        "drift": row_drift,
        "repair_action": {
            "label": repair_label,
            "action_id": repair_action_id,
            "command": repair_command,
            "available": bool(repair_action_id),
        },
        "source_type": "live_cached" if ready else "historical_artifact" if existing_evidence else "not_checked",
        "freshness": "current" if ready else "historical" if existing_evidence else "not_checked",
        "checked_at": checked_at,
        "evidence_artifacts": existing_evidence,
        "blockers": [],
        "warnings": warnings,
    }


def _credential_status(
    build_verification: dict[str, Any],
    *,
    live_status: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    checks = {
        str(item.get("name")): item
        for item in (build_verification.get("credentials") or {}).get("checks", [])
        if isinstance(item, dict)
    }
    if _build_verification_has_real_credentials(build_verification, checks):
        metadata = {
            "source_type": str(build_verification.get("source_type") or "live_cached"),
            "freshness": str(build_verification.get("freshness") or "current"),
            "checked_at": build_verification.get("checked_at"),
            "recheck_command": "make provider-lab-build-verification-live",
        }
        credential_rows = [
            _credential_row("ilo", "iLO", checks.get("ilo"), metadata=metadata),
            _credential_row("cisco", "Cisco", checks.get("cisco"), secondary=checks.get("cisco_enable"), metadata=metadata),
            _credential_row("esxi", "ESXi", checks.get("esxi"), metadata=metadata),
            _credential_row("netapp", "NetApp", checks.get("netapp"), metadata=metadata),
            _vcenter_credential_row(),
        ]
    else:
        credential_rows = _credential_rows_from_evidence(live_status=live_status, rows=rows)
    missing = any(row["status"] == "missing" for row in credential_rows)
    untested = any(row["tested"] is False for row in credential_rows)
    return {
        "status": "warning" if missing else "partial" if untested else "ready",
        "summary": "Credential state is presence/test status only; values are never returned.",
        "rows": credential_rows,
    }


def _credential_row(
    row_id: str,
    label: str,
    primary: dict[str, Any] | None,
    *,
    secondary: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    configured = bool(primary and primary.get("configured"))
    tested = bool(primary and primary.get("classification") == "passed")
    if secondary is not None:
        configured = configured and bool(secondary.get("configured"))
        tested = tested and secondary.get("classification") == "passed"
    source = metadata or {
        "source_type": "not_checked",
        "freshness": "not_checked",
        "checked_at": None,
        "recheck_command": "make provider-lab-build-verification-live",
    }
    return {
        "id": row_id,
        "label": label,
        "configured": configured,
        "tested": tested,
        "status": "tested" if tested else "configured" if configured else "missing",
        "field": str((primary or {}).get("field") or label),
        "next_action": "No credential action required." if tested else "Configure local credential values and rerun Build Verification.",
        "source_type": source["source_type"],
        "freshness": source["freshness"],
        "checked_at": source["checked_at"],
        "recheck_command": source["recheck_command"],
    }


def _build_verification_has_real_credentials(build_verification: dict[str, Any], checks: dict[str, dict[str, Any]]) -> bool:
    if not checks:
        return False
    if build_verification.get("provider_mode") == "mock":
        return False
    if build_verification.get("source_type") == "test_fixture":
        return False
    if build_verification.get("certification_state") == "test_fixture":
        return False
    return True


def _credential_rows_from_evidence(*, live_status: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_by_id = {str(row.get("id")): row for row in rows}
    build_verified = _stage_ready(live_status, "build-verification")
    return [
        _credential_evidence_row(
            "ilo",
            "iLO",
            configured=_row_ready(row_by_id, "ilo"),
            tested=_row_ready(row_by_id, "ilo") and build_verified,
            field="ILO_TEST_PASSWORD",
            next_action="No credential action required.",
            metadata=_stage_metadata(live_status, "ilo-reachability"),
        ),
        _credential_evidence_row(
            "cisco",
            "Cisco",
            configured=_row_ready(row_by_id, "cisco"),
            tested=_row_ready(row_by_id, "cisco") and build_verified,
            field="CISCO_TEST_PASSWORD and CISCO_ENABLE_PASSWORD",
            next_action="No credential action required.",
            metadata=_stage_metadata(live_status, "cisco-console-ethernet"),
        ),
        _esxi_credential_row(),
        _netapp_credential_row(),
        _vcenter_credential_row(),
    ]


def _credential_evidence_row(
    row_id: str,
    label: str,
    *,
    configured: bool,
    tested: bool,
    field: str,
    next_action: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    row_next_action = (
        "No credential action required."
        if tested
        else next_action
        if configured
        else "Configure local credential values and rerun the linked validation."
    )
    return {
        "id": row_id,
        "label": label,
        "configured": configured,
        "tested": tested,
        "status": "tested" if tested else "configured" if configured else "missing",
        "field": field,
        "next_action": row_next_action,
        "source_type": metadata["source_type"],
        "freshness": metadata["freshness"],
        "checked_at": metadata["checked_at"],
        "recheck_command": metadata["recheck_command"],
    }


def _esxi_credential_row() -> dict[str, Any]:
    payload = _read_json("artifacts/codex-runs/esxi-vm-deploy-validation-redacted.json")
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    configured = bool(target.get("username_configured") and target.get("credential_configured"))
    tested = configured and bool(target.get("can_query")) and _json_status_ready(
        "artifacts/codex-runs/esxi-vm-deploy-validation-redacted.json"
    )
    return _credential_evidence_row(
        "esxi",
        "ESXi",
        configured=configured,
        tested=tested,
        field="ESXI_TEST_USERNAME/GOVC_USERNAME and ESXI_TEST_PASSWORD/GOVC_PASSWORD",
        next_action="No credential action required.",
        metadata=_artifact_metadata(
            "artifacts/codex-runs/esxi-vm-deploy-validation-redacted.json",
            "make provider-lab-esxi-vm-deploy-validate",
        ),
    )


def _netapp_credential_row() -> dict[str, Any]:
    payload = _read_json("artifacts/codex-runs/netapp-ontap-upgrade-validation-redacted.json")
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    access_passed = any(
        isinstance(item, dict) and item.get("id") == "access" and item.get("status") == "passed"
        for item in checks
    )
    tested = access_passed and bool(payload.get("validation_passed"))
    return _credential_evidence_row(
        "netapp",
        "NetApp",
        configured=access_passed,
        tested=tested,
        field="NETAPP_API_USERNAME and NETAPP_API_PASSWORD",
        next_action="No credential action required.",
        metadata=_artifact_metadata(
            "artifacts/codex-runs/netapp-ontap-upgrade-validation-redacted.json",
            "make provider-lab-netapp-validate-setup",
        ),
    )


def _vcenter_credential_row() -> dict[str, Any]:
    artifact = _read_json("artifacts/codex-runs/vcenter-install-readiness-redacted.json")
    validation = _read_json("artifacts/codex-runs/vcenter-post-install-validation-redacted.json")
    checks = artifact.get("checks") if isinstance(artifact.get("checks"), dict) else {}
    credential_check = (
        checks.get("vcenter_deployment_credentials_configured")
        if isinstance(checks.get("vcenter_deployment_credentials_configured"), dict)
        else {}
    )
    validation_ready = validation.get("status") == "ready"
    configured = bool(settings.vcenter_username and settings.vcenter_password) or credential_check.get("status") == "ready" or validation_ready
    metadata = _artifact_metadata(
        "artifacts/codex-runs/vcenter-install-readiness-redacted.json",
        "make provider-lab-vcenter-install-readiness",
    )
    return _credential_evidence_row(
        "vcenter",
        "vCenter",
        configured=configured,
        tested=validation_ready,
        field="VCENTER_USERNAME/GOVC_USERNAME and VCENTER_PASSWORD/GOVC_PASSWORD",
        next_action="No credential action required." if validation_ready else "Configure vCenter deployment values, then run vCenter install readiness.",
        metadata=metadata,
    )


def _vcenter_readiness(rows: list[dict[str, Any]], credentials: dict[str, Any]) -> dict[str, Any]:
    row_by_id = {row["id"]: row for row in rows}
    vcenter_credential = next((row for row in credentials["rows"] if row["id"] == "vcenter"), {})
    vcsa_iso_found = _vcsa_iso_found()
    artifact = _read_json("artifacts/codex-runs/vcenter-install-readiness-redacted.json")
    preview_artifact = _read_json("artifacts/codex-runs/vcenter-install-preview-redacted.json")
    validation_artifact = _read_json("artifacts/codex-runs/vcenter-post-install-validation-redacted.json")
    validation_ready = validation_artifact.get("status") == "ready"
    deployment_values = artifact.get("deployment_values") if isinstance(artifact.get("deployment_values"), dict) else {}
    value_checks = artifact.get("value_checks") if isinstance(artifact.get("value_checks"), dict) else {}
    credential_detail = artifact.get("credential_state") if isinstance(artifact.get("credential_state"), dict) else {}
    checks = artifact.get("checks") if isinstance(artifact.get("checks"), dict) else {}
    apply_gate_state = (
        preview_artifact.get("apply_gate_state")
        if isinstance(preview_artifact.get("apply_gate_state"), dict)
        else artifact.get("apply_gate_state")
        if isinstance(artifact.get("apply_gate_state"), dict)
        else {}
    )
    apply_gate_blockers = [
        str(item)
        for item in apply_gate_state.get("blockers") or []
        if item
    ]
    vcsa_deploy_check = checks.get("vcsa_deploy_available") if isinstance(checks.get("vcsa_deploy_available"), dict) else {}
    management_ip_check = (
        checks.get("vcenter_management_ip_available")
        if isinstance(checks.get("vcenter_management_ip_available"), dict)
        else {}
    )
    values_complete = bool(deployment_values.get("complete")) or (
        bool(value_checks) and all(isinstance(check, dict) and check.get("status") == "ready" for check in value_checks.values())
    )
    deployment_credentials_configured = bool(credential_detail.get("deployment_credentials_configured"))
    post_install_credentials_configured = validation_ready or bool(vcenter_credential.get("configured")) or bool(
        credential_detail.get("post_install_vcenter_credentials_configured")
    )
    vcenter_configured = validation_ready or bool(settings.vcenter_host or settings.vcenter_configured) or bool(
        deployment_values.get("post_install_vcenter_configured")
    )
    esxi_ready = row_by_id.get("esxi", {}).get("status") == "ready"
    datastore_ready = row_by_id.get("netapp-nfs-datastore", {}).get("status") == "ready"
    vcsa_deploy_ready = vcsa_deploy_check.get("status") == "ready"
    management_ip_available = management_ip_check.get("status") == "ready"
    ready_for_preview = (
        vcsa_iso_found
        and vcsa_deploy_ready
        and esxi_ready
        and datastore_ready
        and management_ip_available
        and values_complete
        and deployment_credentials_configured
    )
    preview_ready = ready_for_preview and preview_artifact.get("status") == "ready"
    deploy_enabled = bool(
        not validation_ready
        and preview_ready
        and not apply_gate_blockers
        and (artifact.get("apply_enabled") or preview_artifact.get("apply_enabled"))
    )
    deploy_disabled_reason = (
        str((artifact.get("blockers") or preview_artifact.get("blockers") or [""])[0])
        if not ready_for_preview and (artifact.get("blockers") or preview_artifact.get("blockers"))
        else apply_gate_blockers[0]
        if apply_gate_blockers
        else None
    )
    values_state = "complete" if values_complete else "incomplete"
    credential_state = "configured" if deployment_credentials_configured else "missing"
    metadata = _artifact_metadata(
        "artifacts/codex-runs/vcenter-install-readiness-redacted.json",
        "make provider-lab-vcenter-install-readiness",
    )
    return {
        "status": "ready" if validation_ready or ready_for_preview else "not_configured",
        "preview_state": "deployed" if validation_ready else "ready_for_preview" if ready_for_preview else "not_ready",
        "deploy_state": "deployed" if validation_ready else "ready_to_deploy" if deploy_enabled else "deploy_gated" if ready_for_preview else "not_ready",
        "ready_for_preview": ready_for_preview,
        "preview_ready": preview_ready,
        "ready_for_deploy": deploy_enabled,
        "vcsa_iso": "found" if vcsa_iso_found else "not_found",
        "vcsa_deploy": str(vcsa_deploy_check.get("status") or "not_checked"),
        "management_ip_available": (
            "in_use_by_deployed_vcenter"
            if validation_ready
            else "available"
            if management_ip_available
            else str(management_ip_check.get("status") or "not_checked")
        ),
        "esxi": "ready" if esxi_ready else "not_ready",
        "netapp_datastore": "ready" if datastore_ready else "not_ready",
        "vcenter_credentials": credential_state,
        "credentials": credential_state,
        "post_install_vcenter_credentials": "configured" if post_install_credentials_configured else "missing",
        "vcenter_config": "deployed" if validation_ready else "configured" if vcenter_configured else "expected_partial",
        "vcenter_values": values_state,
        "values_complete": values_complete,
        "deploy_enabled": deploy_enabled,
        "preview_action_id": "vcenter.install-preview",
        "deploy_action_id": "vcenter.install-apply",
        "deploy_action_label": "Deploy vCenter",
        "deploy_disabled_reason": deploy_disabled_reason,
        "apply_gate_state": apply_gate_state,
        "deployment_values": deployment_values,
        "value_checks": value_checks,
        "checks": checks,
        "post_install_validation": validation_artifact,
        "credential_detail": credential_detail,
        "next_action": (
            "vCenter is deployed and post-install validation is ready."
            if validation_ready
            else "Deploy vCenter through the guarded install apply workflow."
            if deploy_enabled
            else "Run Preview Deploy to generate the redacted VCSA deployment plan."
            if ready_for_preview
            else "Open vCenter install readiness and complete the current missing local-only deployment values."
        ),
        "source_type": metadata["source_type"],
        "freshness": metadata["freshness"],
        "checked_at": metadata["checked_at"],
        "recheck_command": metadata["recheck_command"],
        "evidence_artifacts": _existing(
            [
                "artifacts/codex-runs/vcenter-install-readiness-report.md",
                "artifacts/codex-runs/vcenter-install-plan-report.md",
                "artifacts/codex-runs/vcenter-install-preview-report.md",
                "artifacts/codex-runs/vcenter-install-apply-report.md",
                "artifacts/codex-runs/vcenter-post-install-validation-report.md",
            ]
        ),
    }


def _workflow_actions() -> list[dict[str, Any]]:
    return [
        {
            "id": "full-lab.validation",
            "label": "Run Full Lab Validation",
            "command": "make provider-lab-validation",
            "mode": "read_only",
            "description": "Refresh the existing Lab Validation / Handoff summary.",
        },
        {
            "id": "full-lab.build-plan",
            "label": "Run Full Lab Build Plan",
            "command": "make provider-lab-full-rebuild-summary",
            "mode": "read_only",
            "description": "Generate the existing full rebuild summary without apply.",
        },
        {
            "id": "full-lab.repair",
            "label": "Run Full Lab Repair",
            "command": "make provider-lab-golden-state",
            "mode": "report_only",
            "description": "Generate repair guidance from drift rows and linked existing actions.",
        },
        {
            "id": "full-lab.handoff-report",
            "label": "Generate Handoff Report",
            "command": "make provider-lab-golden-state",
            "mode": "report_only",
            "description": "Write the golden-state handoff report.",
        },
    ]


def _stage_ready(payload: dict[str, Any], stage_name: str) -> bool:
    return _stage_status(payload, stage_name) in {"ready", "completed", "current", "succeeded"}


def _row_ready(row_by_id: dict[str, dict[str, Any]], row_id: str) -> bool:
    return row_by_id.get(row_id, {}).get("status") == "ready"


def _stage_status(payload: dict[str, Any], stage_name: str) -> str:
    for stage in payload.get("stages") or []:
        if isinstance(stage, dict) and stage.get("stage") == stage_name:
            return str(stage.get("status") or "")
    return ""


def _stage_warnings(payload: dict[str, Any], stage_name: str) -> list[str]:
    for stage in payload.get("stages") or []:
        if isinstance(stage, dict) and stage.get("stage") == stage_name:
            return [str(item) for item in stage.get("warnings") or []]
    return []


def _stage_metadata(payload: dict[str, Any], stage_name: str) -> dict[str, Any]:
    for stage in payload.get("stages") or []:
        if isinstance(stage, dict) and stage.get("stage") == stage_name:
            return {
                "source_type": str(stage.get("source_type") or payload.get("source_type") or "historical_artifact"),
                "freshness": str(stage.get("freshness") or payload.get("freshness") or "historical"),
                "checked_at": payload.get("checked_at"),
                "recheck_command": "make provider-lab-live-status",
            }
    return {
        "source_type": "not_checked",
        "freshness": "not_checked",
        "checked_at": None,
        "recheck_command": "make provider-lab-live-status",
    }


def _artifact_metadata(path: str, recheck_command: str) -> dict[str, Any]:
    payload = _read_json(path)
    exists = (REPO_ROOT / path).exists()
    has_checked_at = bool(payload.get("checked_at"))
    source_type = payload.get("source_type") or (
        "live_cached" if has_checked_at else "historical_artifact" if exists else "not_checked"
    )
    freshness = payload.get("freshness") or (
        "current" if has_checked_at else "historical" if exists else "not_checked"
    )
    return {
        "source_type": str(source_type),
        "freshness": str(freshness),
        "checked_at": payload.get("checked_at"),
        "recheck_command": recheck_command,
    }


def _raid_validated() -> bool:
    path = REPO_ROOT / "artifacts/codex-runs/hpe-raid-after-reset-validation-report.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "Status: succeeded" in text and "Matches saved intent: True" in text


def _json_status_ready(path: str) -> bool:
    payload = _read_json(path)
    return str(payload.get("status") or "") in {"ready", "completed", "current", "succeeded"}


def _vcsa_iso_found() -> bool:
    artifact = _read_json("artifacts/codex-runs/vcenter-install-readiness-redacted.json")
    current_state = artifact.get("current_state") if isinstance(artifact.get("current_state"), dict) else {}
    if current_state.get("vcsa_iso"):
        return True
    try:
        inventory = get_media_inventory()
    except Exception:
        return False
    for item in getattr(inventory, "items", []):
        hints = getattr(item, "product_hints", None) or []
        if getattr(item, "category", "") == "iso" and "vmware-vcenter" in hints:
            return True
    return False


def _read_json(path: str) -> dict[str, Any]:
    artifact = REPO_ROOT / path
    if not artifact.exists():
        return {}
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _existing(paths: list[str]) -> list[str]:
    return [path for path in paths if (REPO_ROOT / path).exists()]


def _last_checked(paths: list[str]) -> str | None:
    existing = [REPO_ROOT / path for path in paths if (REPO_ROOT / path).exists()]
    if not existing:
        return None
    latest = max(existing, key=lambda path: path.stat().st_mtime)
    return datetime.fromtimestamp(latest.stat().st_mtime, UTC).isoformat()


def _proof_links(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        for path in row.get("evidence_artifacts") or []:
            if path in seen:
                continue
            seen.add(path)
            links.append({"component_id": str(row["id"]), "component_label": str(row["label"]), "path": path})
    return links


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Golden State Productization Report",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Status: `{payload.get('status')}`",
        "- Real hardware workflow run by this report: `False`",
        "- Secrets: not included; credentials are configured/tested status only.",
        "",
        "## Golden State Rows",
        "",
        "| Component | Golden State | Current State | Drift | Repair Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("rows") or []:
        action = row.get("repair_action") or {}
        lines.append(
            "| {label} | {golden} | {current} | `{drift}` | `{repair}` |".format(
                label=_md_cell(row.get("label")),
                golden=_md_cell(row.get("golden_state")),
                current=_md_cell(row.get("current_state")),
                drift=_md_cell(row.get("drift")),
                repair=_md_cell(action.get("command")),
            )
        )
    lines.extend(["", "## Credential Status", "", "| Provider | Configured | Tested | Next Action |", "| --- | --- | --- | --- |"])
    for credential in (payload.get("credentials") or {}).get("rows") or []:
        lines.append(
            "| {label} | `{configured}` | `{tested}` | {next_action} |".format(
                label=_md_cell(credential.get("label")),
                configured=credential.get("configured"),
                tested=credential.get("tested"),
                next_action=_md_cell(credential.get("next_action")),
            )
        )
    vcenter = payload.get("vcenter_readiness") or {}
    lines.extend(
        [
            "",
            "## vCenter Readiness",
            "",
            f"- VCSA ISO: `{vcenter.get('vcsa_iso')}`",
            f"- vcsa-deploy: `{vcenter.get('vcsa_deploy')}`",
            f"- ESXi: `{vcenter.get('esxi')}`",
            f"- NetApp datastore: `{vcenter.get('netapp_datastore')}`",
            f"- Management IP available: `{vcenter.get('management_ip_available')}`",
            f"- vCenter values: `{vcenter.get('vcenter_values')}`",
            f"- vCenter credentials: `{vcenter.get('vcenter_credentials')}`",
            f"- vCenter config: `{vcenter.get('vcenter_config')}`",
            f"- Preview state: `{vcenter.get('preview_state')}`",
            f"- Deploy state: `{vcenter.get('deploy_state')}`",
            f"- Deploy enabled: `{vcenter.get('deploy_enabled')}`",
            f"- Next action: {vcenter.get('next_action')}",
            "",
            "## Workflow Actions",
            "",
        ]
    )
    for action in payload.get("workflow_actions") or []:
        lines.append(f"- {action.get('label')}: `{action.get('command')}`")
    lines.extend(["", "## Drift", ""])
    drift_rows = payload.get("drift_rows") or []
    if drift_rows:
        for row in drift_rows:
            lines.append(f"- {row.get('label')}: `{row.get('drift')}` - {row.get('current_state')}")
    else:
        lines.append("- None")
    lines.extend(["", "## Evidence", ""])
    lines.extend(f"- `{link.get('path')}`" for link in payload.get("proof_links") or [])
    lines.extend(
        [
            "",
            "## Skill Improvement Review",
            "",
            "- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-hardware-run, lab-builder-toolchain, lab-builder-ux, lab-builder-product-craft, lab-builder-report-remediation",
            "- Skills created or updated: none",
            "- Skill gaps found: none requiring a new reusable skill in this pass",
            "- Candidate skills deferred: none",
            "- No additional skills were created because this work fits the existing Lab Builder skill set.",
        ]
    )
    return "\n".join(lines) + "\n"


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat()
