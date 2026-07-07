from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core.config import (
    settings,
)
from app.providers.redaction import redact_sensitive
from app.services.build_verification import get_lab_build_verification
from app.services.firmware_compliance import get_firmware_compliance
from app.services.json_file_store import read_json_object, write_json_object, write_text_value
from app.services.lab_profiles import active_lab_profile_context
from app.services.list_utils import unique_preserving_order
from app.services.netapp_state import get_netapp_runtime_state
from app.services.netapp_upgrade_center import build_netapp_upgrade_plan
from app.services.path_utils import path_exists, path_mtime, repo_relative_path
from app.services.vcenter_netapp_readiness import get_vcenter_netapp_readiness
from app.services.workflow_registry import list_workflow_actions

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
HANDOFF_REPORT = CODEX_RUN_DIR / "lab-validation-handoff-report.md"
SUMMARY_JSON = CODEX_RUN_DIR / "lab-validation-summary-redacted.json"

VALIDATION_STATUSES = (
    "ready",
    "partial",
    "blocked",
    "not_configured",
    "not_checked",
    "warning",
    "not_in_scope",
)


def get_lab_validation_summary(*, write_report: bool = False) -> dict[str, Any]:
    generated_at = _now()
    profile_context = active_lab_profile_context()
    actions = {str(action.get("action_id")): action for action in list_workflow_actions()}
    netapp_state = get_netapp_runtime_state()
    vcenter_netapp = get_vcenter_netapp_readiness(check_ports=False, write_report=False)
    build_verification = get_lab_build_verification()
    items = [
        _lab_profile_item(generated_at, actions, profile_context),
        _firmware_item(actions),
        build_cisco_validation_item(actions=actions, profile_context=profile_context),
        _ilo_item(actions),
        _raid_item(actions),
        _esxi_item(actions, profile_context=profile_context),
        _vcenter_item(actions, profile_context=profile_context),
        _netapp_console_item(netapp_state, actions, profile_context=profile_context),
        _netapp_ontap_item(netapp_state, actions, profile_context=profile_context),
        _netapp_upgrade_item(actions, profile_context=profile_context),
        _netapp_nfs_item(netapp_state, actions, profile_context=profile_context),
        _esxi_iscsi_datastore_item(actions, profile_context=profile_context),
        _vcenter_netapp_item(vcenter_netapp, actions, profile_context=profile_context),
        _build_verification_item(build_verification, actions),
    ]
    counts = _progress_counts(items)
    top_blocker = _top_blocker(items)
    remaining_items = _remaining_items(items)
    payload = {
        "overall_status": _overall_status(counts),
        "progress_counts": counts,
        "top_blocker": top_blocker,
        "validation_items": items,
        "proof_links": _proof_links(items),
        "generated_at": generated_at,
        "next_action": _summary_next_action(top_blocker, remaining_items),
        "source_type": "live_cached",
        "freshness": "current",
        "handoff_report": _rel(HANDOFF_REPORT),
        "warnings": [
            "Historical artifacts are evidence only; rerun the listed command to refresh current state.",
            "No secrets are included. Credential state is shown as configured or missing by field name only.",
        ],
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        write_json_object(SUMMARY_JSON, sanitized)
        write_text_value(HANDOFF_REPORT, _handoff_markdown(sanitized))
    return sanitized


def build_cisco_validation_item(
    *,
    actions: dict[str, dict[str, Any]] | None = None,
    management_ready: bool | None = None,
    target_ip: str | None = None,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actions = actions or {}
    profile_context = profile_context or active_lab_profile_context()
    plan = profile_context.get("resolved_address_plan") or {}
    target = target_ip or plan.get("cisco_management") or settings.cisco_target_ip
    ready = settings.cisco_mgmt_configured if management_ready is None else management_ready
    artifacts = _existing(
        [
            "artifacts/codex-runs/serial-console-discovery-report.md",
            "artifacts/codex-runs/cisco-console-ethernet-readiness-report.md",
            "artifacts/codex-runs/cisco-bootstrap-apply-report.md",
            "artifacts/codex-runs/cisco-current-intent-diff-report.md",
            "artifacts/codex-runs/cisco-current-intent-diff-redacted.json",
        ]
    )
    intent_diff = _json_artifact("artifacts/codex-runs/cisco-current-intent-diff-redacted.json")
    diff = intent_diff.get("diff") if isinstance(intent_diff.get("diff"), dict) else {}
    drift_count = int(diff.get("drift_count") or 0) if isinstance(diff.get("drift_count") or 0, int) else 0
    intent_status = str(intent_diff.get("status") or "")
    has_intent_evidence = bool(intent_diff)
    status = (
        "blocked"
        if ready and intent_status == "blocked"
        else "warning"
        if ready and (intent_status == "warning" or drift_count)
        else "ready"
        if ready
        else "partial"
        if artifacts
        else "not_checked"
    )
    blockers = [] if ready else [
        _blocker(
            problem="Cisco management SSH is not proven as configured yet.",
            source="Cisco validation summary",
            current_value="not configured" if not artifacts else "historical evidence only",
            expected_value=f"SSH reachable on {target}",
            where_to_fix="Run Center / Cisco",
            recommended_action="Run `make provider-lab-cisco-console-ethernet-readiness` after console/bootstrap work is in scope.",
            recheck_command="make provider-lab-cisco-console-ethernet-readiness",
            evidence_links=artifacts,
        )
    ]
    if ready and intent_status == "blocked":
        blockers = [
            _blocker(
                problem=str(item),
                source="Cisco current-to-intent diff",
                current_value="blocked",
                expected_value="live Cisco SSH show-command evidence",
                where_to_fix="Network / Cisco",
                recommended_action=str(intent_diff.get("next_safe_action") or "Refresh Cisco current-to-intent diff."),
                recheck_command="make provider-lab-cisco-current-intent-diff",
                evidence_links=artifacts,
            )
            for item in intent_diff.get("blockers") or ["Cisco current-to-intent diff is blocked."]
        ]
    drift_warnings = _cisco_drift_warnings(intent_diff)
    return _item(
        item_id="cisco-network",
        label="Cisco Network",
        category="Network",
        status=status,
        current_state=(
            f"Management SSH is reachable; current-to-intent drift count is {drift_count}."
            if ready and has_intent_evidence
            else "Management SSH is configured."
            if ready
            else "Console/ethernet readiness has not been freshly proven."
        ),
        desired_state=f"Cisco management reachable at {target} and aligned to the active lab VLAN, port, and guardrail intent.",
        setup_summary=(
            "Cisco management is reachable, but current-to-intent drift needs review."
            if ready and status == "warning"
            else "Cisco management is ready for SSH validation."
            if ready
            else "Console-first setup evidence exists, but SSH readiness needs refresh."
        ),
        next_action=(
            str(intent_diff.get("next_safe_action") or "Review VLAN/interface/guardrail drift before guarded config apply.")
            if ready and has_intent_evidence
            else "Validate SSH/SCP from Run Center."
            if ready
            else "Refresh Cisco ethernet readiness from Run Center."
        ),
        login_hint=f"ssh admin@{target}" if ready else f"Console-first; SSH target when ready: admin@{target}",
        management_url=None,
        ssh_target=f"admin@{target}",
        proof_points=[
            "Cisco login hint uses a username label only and does not expose credentials.",
            "Console-first evidence stays in the evidence drawer.",
            *(
                [
                    f"Current-to-intent drift count: {drift_count}",
                    f"Parsed VLAN rows: {len(((intent_diff.get('current') or {}).get('vlans') or []))}",
                    f"Parsed interface rows: {len(((intent_diff.get('current') or {}).get('ports') or []))}",
                ]
                if has_intent_evidence
                else []
            ),
        ],
        evidence_artifacts=artifacts,
        last_checked=str(intent_diff.get("checked_at") or _last_checked(artifacts)),
        source_type=str(intent_diff.get("source_type") or "live_cached" if ready else _source_for_artifacts(artifacts)),
        freshness=str(intent_diff.get("freshness") or "current" if ready else _freshness_for_artifacts(artifacts)),
        blockers=blockers,
        warnings=drift_warnings if ready and drift_warnings else [] if ready else ["Historical Cisco evidence must be refreshed before handoff."],
        recheck_command="make provider-lab-cisco-current-intent-diff" if has_intent_evidence else "make provider-lab-cisco-console-ethernet-readiness",
        linked_workflow_action=_action_link(actions, "cisco.current-intent-diff" if has_intent_evidence else "cisco.validate-ssh-scp"),
    )


def _cisco_drift_warnings(intent_diff: dict[str, Any]) -> list[str]:
    if not intent_diff:
        return []
    diff = intent_diff.get("diff") if isinstance(intent_diff.get("diff"), dict) else {}
    vlan = diff.get("vlan") if isinstance(diff.get("vlan"), dict) else {}
    guardrails = diff.get("guardrails") if isinstance(diff.get("guardrails"), dict) else {}
    warnings: list[str] = []
    missing_vlans = _cisco_strings(vlan.get("missing"))
    unexpected_vlans = _cisco_strings(vlan.get("unexpected"))
    port_drift = diff.get("ports") if isinstance(diff.get("ports"), list) else []
    if missing_vlans:
        warnings.append(f"Missing intended VLANs: {', '.join(missing_vlans)}.")
    if unexpected_vlans:
        warnings.append(f"Unexpected VLANs present: {', '.join(unexpected_vlans)}.")
    if port_drift:
        warnings.append(f"{len(port_drift)} Cisco port intent drift item(s) need review.")
    for label, key in (
        ("BPDU guard", "bpdu_guard"),
        ("ACL lanes", "acl_lanes"),
        ("Black-hole VLAN", "blackhole_vlan"),
    ):
        evidence = guardrails.get(key) if isinstance(guardrails.get(key), dict) else {}
        if evidence.get("status") == "warning":
            missing = _cisco_strings(evidence.get("missing"))
            warnings.append(f"{label} guardrail drift: {', '.join(missing) if missing else 'review evidence'}.")
        elif evidence.get("status") == "not_checked":
            warnings.append(f"{label} guardrail evidence was not checked.")
    return unique_preserving_order(warnings)


def _cisco_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return _clean_unique_strings(value)
    if value is None:
        return []
    return _clean_unique_strings([value])


def map_validation_status(
    *,
    ready: bool = False,
    configured: bool = False,
    blockers: list[Any] | None = None,
    warnings: list[Any] | None = None,
    checked: bool = True,
) -> str:
    if ready:
        return "ready"
    if blockers:
        return "blocked"
    if warnings:
        return "warning" if configured else "partial"
    if configured:
        return "partial"
    return "not_checked" if not checked else "not_configured"


def _lab_profile_item(
    generated_at: str,
    actions: dict[str, dict[str, Any]],
    profile_context: dict[str, Any],
) -> dict[str, Any]:
    runtime_address_plan = profile_context.get("resolved_address_plan") or {}
    warnings = [
        f"{item.get('env_field')}: expected {item.get('expected_value')}, current {item.get('current_value')}."
        for item in profile_context.get("mismatch_warnings") or []
    ]
    mismatch = bool(warnings)
    proof_points = [
        f"Topology: {profile_context.get('topology')}",
        f"Lab subnet: {runtime_address_plan['subnet']}",
        f"iLO: {runtime_address_plan['ilo']}",
        f"Server NIC: {runtime_address_plan.get('server_embedded_nic') or 'not_in_scope'}",
        f"ESXi: {runtime_address_plan['esxi_management']}",
        f"Cisco: {runtime_address_plan['cisco_management']}",
        f"Ansible/control host: {runtime_address_plan['ansible_control_host']}",
        f"NetApp cluster: {runtime_address_plan.get('netapp_cluster_mgmt') or 'not_in_scope'}",
        f"NetApp NFS LIFs: {', '.join(runtime_address_plan.get('netapp_nfs_lifs') or []) or 'not_in_scope'}",
        f"Disabled features: {', '.join(profile_context.get('disabled_features') or {}) or 'none'}",
    ]
    return _item(
        item_id="lab-profile",
        label="Lab Profile",
        category="Profile",
        status="warning" if mismatch else "ready",
        current_state=f"Active lab profile uses subnet {runtime_address_plan['subnet']}.",
        desired_state="Active lab profile drives default targets and feature scope.",
        setup_summary="Known runtime lab addressing is loaded.",
        next_action="Resolve profile/runtime mismatch warnings before live certification." if mismatch else "Use this profile for validation and keep live checks separate from historical proof.",
        login_hint="No login target; profile defines addresses only.",
        management_url=None,
        ssh_target=None,
        proof_points=proof_points,
        evidence_artifacts=_existing(["artifacts/codex-runs/lab-ip-profile-update-report.md", "artifacts/codex-runs/lab-ip-profile-hardening-report.md"]),
        last_checked=generated_at,
        source_type="live_cached",
        freshness="current",
        blockers=[],
        warnings=warnings,
        recheck_command="make provider-lab-validation",
        linked_workflow_action=_action_link(actions, "lab-profile.view-active"),
    )


def _firmware_item(actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    compliance = get_firmware_compliance(refresh_live=False, scope="full")
    profile_context = active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    paths = [
        path
        for path in compliance.get("upgrade_paths", [])
        if isinstance(path, dict) and _firmware_path_in_active_scope(path, features)
    ]
    review_paths = [path for path in paths if path.get("path_status") in {"manual_review", "unknown"}]
    blocked_paths = [path for path in paths if path.get("path_status") == "blocked"]
    upgrade_paths = [path for path in paths if path.get("path_status") in {"direct", "staged"}]
    current_paths = [path for path in paths if path.get("path_status") == "current"]
    artifacts = _existing(
        [
            "artifacts/codex-runs/firmware-compliance-report.md",
            "artifacts/codex-runs/firmware-compliance-summary-redacted.json",
            "artifacts/codex-runs/toolchain-availability-report.md",
        ]
    )
    status = (
        "blocked"
        if blocked_paths
        else "partial"
        if review_paths or upgrade_paths
        else "ready"
        if paths
        else "not_checked"
    )
    proof_points = [
        (
            f"{path.get('device_label')} {path.get('component_label')}: current "
            f"{path.get('current_version') or 'unknown'}, target "
            f"{path.get('target_version') or 'manual review'}, path "
            f"{path.get('path_status')}, package "
            f"{path.get('package_name') or 'not available'}."
        )
        for path in paths
    ]
    warnings = [
        (
            f"{path.get('device_label')} {path.get('component_label')}: "
            f"{path.get('disabled_reason') or path.get('next_action')}"
        )
        for path in [*blocked_paths, *review_paths, *upgrade_paths]
    ]
    return _item(
        item_id="firmware-compliance",
        label="Firmware Compliance",
        category="Preflight",
        status=status,
        current_state=(
            f"{len(current_paths)}/{len(paths)} firmware/software components current; "
            f"{len(review_paths)} manual review; {len(blocked_paths)} blocked."
            if paths
            else "Firmware compliance has not been checked."
        ),
        desired_state="Firmware/software components are current or explicitly accepted with package/path evidence.",
        setup_summary=(
            "Firmware/software path status is normalized by component."
            if paths
            else "No firmware proof is available yet."
        ),
        next_action=(
            "Open Firmware Upgrades and review the named firmware/software components."
            if review_paths or upgrade_paths
            else "Resolve firmware upgrade blockers."
            if blocked_paths
            else "No firmware handoff action remains."
            if paths
            else "Refresh firmware compliance when certification is in scope."
        ),
        login_hint="No direct login; use firmware workflow evidence.",
        management_url=None,
        ssh_target=None,
        proof_points=proof_points or ["Compliance evidence belongs in the evidence drawer."],
        evidence_artifacts=_existing(
            unique_preserving_order(
                [
                    *artifacts,
                    *[
                        artifact
                        for path in paths
                        for artifact in path.get("evidence_artifacts") or []
                    ],
                ]
            )
        ),
        last_checked=_last_checked(artifacts) or compliance.get("checked_at"),
        source_type=str(compliance.get("source_type") or _source_for_artifacts(artifacts)),
        freshness=str(compliance.get("freshness") or _freshness_for_artifacts(artifacts)),
        blockers=[
            _blocker(
                problem=str(path.get("disabled_reason") or path.get("next_action")),
                source="Firmware upgrade path model",
                current_value=str(path.get("current_version") or "unknown"),
                expected_value=str(path.get("target_version") or "manual review"),
                where_to_fix="Firmware Upgrades",
                recommended_action=str(path.get("next_action")),
                recheck_command="make provider-lab-firmware-compliance",
                evidence_links=[str(item) for item in path.get("evidence_artifacts") or []],
            )
            for path in blocked_paths
        ],
        warnings=warnings,
        recheck_command="make provider-lab-firmware-compliance",
        linked_workflow_action=_action_link(actions, "firmware.compliance-check"),
    )


def _firmware_path_in_active_scope(path: dict[str, Any], features: dict[str, Any]) -> bool:
    device = str(path.get("device") or path.get("device_id") or "").strip().lower()
    component_id = str(path.get("component_id") or "").strip().lower()
    if not features.get("vcenter_enabled") and (device == "vcenter" or component_id.startswith("vcenter_")):
        return False
    if features.get("netapp_enabled") is False and (device == "netapp" or component_id.startswith("netapp_")):
        return False
    return True


def _ilo_item(actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    profile_context = active_lab_profile_context()
    plan = profile_context.get("resolved_address_plan") or {}
    host = plan.get("ilo") or settings.ilo_test_host
    credentials_missing = _missing_credentials(
        [
            ("ILO_TEST_USERNAME", settings.ilo_test_username),
            ("ILO_TEST_PASSWORD", settings.ilo_test_password),
        ]
    )
    reachability = _json_artifact("artifacts/codex-runs/ilo-real-run-redacted.json")
    endpoint = reachability.get("endpoint_detection") if isinstance(reachability.get("endpoint_detection"), dict) else {}
    legacy = reachability.get("legacy_identity") if isinstance(reachability.get("legacy_identity"), dict) else {}
    artifacts = _existing(
        [
            "artifacts/codex-runs/ilo-real-run-report.md",
            "artifacts/codex-runs/ilo-real-run-redacted.json",
            "artifacts/codex-runs/ilo-local-readonly-smoke-report.md",
        ]
    )
    live_ready = str(reachability.get("status") or "") == "ok" and endpoint.get("redfish_status") == "available"
    status = "ready" if live_ready else "partial" if artifacts or host else "not_configured"
    warnings = [
        *([f"Credentials not configured: {', '.join(credentials_missing)}"] if credentials_missing else []),
        *[str(item) for item in reachability.get("warnings") or []],
    ]
    return _item(
        item_id="hpe-ilo",
        label="HPE / iLO",
        category="Management",
        status=status,
        current_state=(
            str(reachability.get("message") or "Read-only iLO Redfish probe completed.")
            if live_ready
            else "iLO target is known; live inventory evidence must be refreshed for handoff."
        ),
        desired_state=f"iLO reachable and authenticated at {host}.",
        setup_summary=(
            f"Redfish {endpoint.get('redfish_status')}; legacy {endpoint.get('legacy_status')}; model {legacy.get('model') or 'unknown'}."
            if reachability
            else "iLO management target is known; credentials are reported by field presence only."
        ),
        next_action=str(reachability.get("next_safe_action") or "Run iLO reachability before auth or inventory."),
        login_hint=_login_hint(f"https://{host}", credentials_missing),
        management_url=f"https://{host}",
        ssh_target=None,
        proof_points=[
            f"Endpoint classification: {endpoint.get('classification', 'not checked')}",
            f"Redfish status: {endpoint.get('redfish_status', 'not checked')}",
            f"Legacy status: {endpoint.get('legacy_status', 'not checked')}",
            f"Model: {legacy.get('model', 'unknown')}",
            "iLO validation is GET-only and does not change power, boot, firmware, users, licenses, or network settings.",
        ],
        evidence_artifacts=artifacts,
        last_checked=str(reachability.get("checked_at") or _last_checked(artifacts)),
        source_type=str(reachability.get("source_type") or _source_for_artifacts(artifacts) if artifacts else "live_cached"),
        freshness=str(reachability.get("freshness") or _freshness_for_artifacts(artifacts) if artifacts else "current"),
        blockers=[],
        warnings=warnings,
        recheck_command="make provider-lab-ilo-reachability",
        linked_workflow_action=_action_link(actions, "ilo.reachability"),
    )


def _raid_item(actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    artifacts = _existing(["artifacts/codex-runs/hpe-raid-plan-report.md", "artifacts/codex-runs/hpe-raid-pending-report.md"])
    plan_trace = _latest_action_trace(actions, "raid.plan")
    pending_trace = _latest_action_trace(actions, "raid.pending-check")
    current_trace = pending_trace if pending_trace.get("status") == "completed" else plan_trace
    current = current_trace.get("status") == "completed" and current_trace.get("source_type") == "live_probe"
    trace_warnings = unique_preserving_order(
        [
            *[str(item) for item in plan_trace.get("warnings") or []],
            *[str(item) for item in pending_trace.get("warnings") or []],
        ]
    )
    return _item(
        item_id="raid-storage",
        label="RAID / Storage",
        category="Server",
        status="partial" if artifacts else "not_checked",
        current_state=(
            "RAID read-only evidence is current."
            if current
            else "RAID evidence exists as supporting proof." if artifacts else "RAID/storage validation has not been checked."
        ),
        desired_state="Server storage layout planned and validated before ESXi handoff.",
        setup_summary="RAID/storage evidence is current supporting proof." if current else "RAID/storage evidence is supporting proof, not a primary blocker.",
        next_action="Review current RAID plan/pending warnings before ESXi install work." if current else "Refresh RAID plan/pending state before ESXi install work.",
        login_hint="No separate login; use iLO/Smart Array workflow.",
        management_url=None,
        ssh_target=None,
        proof_points=[
            "RAID discovery, plan, and pending checks are read-only.",
            "RAID apply remains destructive and gated outside this page.",
        ],
        evidence_artifacts=artifacts,
        last_checked=str(current_trace.get("finished_at") or _last_checked(artifacts)),
        source_type=str(current_trace.get("source_type") or _source_for_artifacts(artifacts)),
        freshness=str(current_trace.get("freshness") or _freshness_for_artifacts(artifacts)),
        blockers=[],
        warnings=trace_warnings if current else ["RAID evidence is historical until refreshed."] if artifacts else [],
        recheck_command="make provider-lab-hpe-raid-plan",
        linked_workflow_action=_action_link(actions, "raid.plan"),
    )


def _esxi_item(
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    plan = profile_context.get("resolved_address_plan") or {}
    host = plan.get("esxi_management") or settings.esxi_test_host
    credentials_missing = _missing_credentials(
        [
            ("ESXI_TEST_USERNAME", settings.esxi_test_username),
            ("ESXI_TEST_PASSWORD", settings.esxi_test_password),
        ]
    )
    validation = _json_artifact("artifacts/codex-runs/esxi-management-readiness-redacted.json")
    https = validation.get("https_reachability") if isinstance(validation.get("https_reachability"), dict) else {}
    ssh = validation.get("ssh_reachability") if isinstance(validation.get("ssh_reachability"), dict) else {}
    vim = validation.get("vim_service_versions") if isinstance(validation.get("vim_service_versions"), dict) else {}
    validation_status = str(validation.get("status") or "")
    artifacts = _existing(
        [
            "artifacts/codex-runs/esxi-management-readiness-report.md",
            "artifacts/codex-runs/esxi-management-readiness-redacted.json",
            "artifacts/codex-runs/esxi-install-readiness-report.md",
            "artifacts/codex-runs/esxi-installer-boot-report.md",
        ]
    )
    live_ready = validation_status in {"ok", "ready", "completed"} and https.get("reachable") is True
    status = "ready" if live_ready else "partial" if artifacts or settings.esxi_configured else "not_configured"
    blockers = [
        _blocker(
            problem=str(item),
            source="ESXi management validation",
            current_value=validation_status or "not_checked",
            expected_value=f"ESXi management reachable at {host}",
            where_to_fix="Server / ESXi",
            recommended_action=str(validation.get("next_safe_action") or "Refresh ESXi management validation."),
            recheck_command="make provider-lab-esxi-management-validation",
            evidence_links=artifacts,
        )
        for item in validation.get("blockers") or []
    ]
    warnings = [*([f"Credentials not configured: {', '.join(credentials_missing)}"] if credentials_missing else []), *[str(item) for item in validation.get("warnings") or []]]
    return _item(
        item_id="esxi-host",
        label="ESXi Host",
        category="Compute",
        status=status,
        current_state=(
            str(validation.get("message") or "ESXi management validation is current.")
            if live_ready
            else "ESXi management target is known; readiness proof needs refresh."
        ),
        desired_state=f"ESXi management reachable at {host}.",
        setup_summary=(
            f"HTTPS reachable: {https.get('reachable')}; SSH reachable: {ssh.get('reachable')}; VIM API versions: {vim.get('available')}."
            if validation
            else "ESXi management is planned/configured enough to show the validation target."
        ),
        next_action=str(validation.get("next_safe_action") or "Refresh ESXi install/management readiness."),
        login_hint=_login_hint(f"https://{host}", credentials_missing),
        management_url=f"https://{host}",
        ssh_target=f"root@{host}",
        proof_points=[
            f"HTTPS reachable: {https.get('reachable', 'not checked')}",
            f"SSH reachable: {ssh.get('reachable', 'not checked')}",
            f"VIM service versions available: {vim.get('available', 'not checked')}",
            "ESXi validation is read-only and does not reconfigure host, storage, network, or VMs.",
        ],
        evidence_artifacts=artifacts,
        last_checked=str(validation.get("checked_at") or _last_checked(artifacts)),
        source_type=str(validation.get("source_type") or _source_for_artifacts(artifacts) if artifacts else "live_cached"),
        freshness=str(validation.get("freshness") or _freshness_for_artifacts(artifacts) if artifacts else "current"),
        blockers=blockers,
        warnings=warnings,
        recheck_command="make provider-lab-esxi-management-validation",
        linked_workflow_action=_action_link(actions, "esxi.management-validation"),
    )


def _vcenter_item(
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("vcenter_enabled"):
        return _not_in_scope_item(
            item_id="vcenter",
            label="vCenter",
            category="Compute",
            reason="vCenter is disabled by the active lab profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "vcenter-netapp.readiness"),
        )
    validation = _json_artifact("artifacts/codex-runs/vcenter-post-install-validation-redacted.json")
    attach_validation = _json_artifact("artifacts/codex-runs/vcenter-post-attach-validation-redacted.json")
    validation_target = validation.get("target") if isinstance(validation.get("target"), dict) else {}
    attach_ready = _vcenter_post_attach_ready(attach_validation)
    validation_ready = validation.get("status") == "ready"
    target = _redacted_url(validation_target.get("host") or settings.vcenter_host)
    credential_missing = _missing_credentials(
        [
            ("VCENTER_HOST/GOVC_URL", validation_target.get("host") or settings.vcenter_host),
            ("VCENTER_USERNAME/GOVC_USERNAME", settings.vcenter_username or settings.vcenter_sso_admin_username),
            ("VCENTER_PASSWORD/GOVC_PASSWORD", settings.vcenter_password or settings.vcenter_sso_admin_password),
        ]
    )
    configured = attach_ready or validation_ready or bool(settings.vcenter_configured and settings.vcenter_host)
    artifacts = _existing(
        [
            "artifacts/codex-runs/vcenter-install-apply-report.md",
            "artifacts/codex-runs/vcenter-post-install-validation-report.md",
            "artifacts/codex-runs/vcenter-install-apply-unblock-final-report.md",
            "artifacts/codex-runs/vcenter-attach-esxi-preview-report.md",
            "artifacts/codex-runs/vcenter-attach-esxi-apply-report.md",
            "artifacts/codex-runs/vcenter-post-attach-validation-report.md",
        ]
    )
    warnings = [str(item) for item in attach_validation.get("warnings") or []] if attach_validation else [str(item) for item in validation.get("warnings") or []] if validation else []
    return _item(
        item_id="vcenter",
        label="vCenter",
        category="Compute",
        status="ready" if attach_ready else "partial" if configured else "not_configured",
        current_state="vCenter manages ESXi and sees the NetApp datastore." if attach_ready else "vCenter is deployed and authenticated; ESXi attach is pending." if validation_ready else "vCenter target is configured." if configured else "vCenter target is not configured yet.",
        desired_state="vCenter manages ESXi, sees the NetApp datastore, and exposes VM inventory.",
        setup_summary="vCenter post-attach validation is ready." if attach_ready else "vCenter post-install validation is ready; attach ESXi next." if validation_ready else "vCenter is ready for datastore validation." if configured else "vCenter/govc is not configured yet.",
        next_action="Refresh Golden State and continue managed validation." if attach_ready else "Run vCenter ESXi attach preview, guarded apply, and post-attach validation." if validation_ready else "Configure vCenter/govc fields, then rerun vCenter-NetApp readiness.",
        login_hint=_login_hint(target or "VCENTER_HOST / GOVC_URL not configured", credential_missing),
        management_url=target,
        ssh_target=None,
        proof_points=["vCenter credentials are shown by field presence only.", "Post-attach validation uses read-only govc inventory checks for datacenter, cluster, host, datastore, and VMs."],
        evidence_artifacts=artifacts,
        last_checked=attach_validation.get("checked_at") or validation.get("checked_at") or _last_checked(artifacts),
        source_type="live_probe" if attach_ready or validation_ready else "live_cached" if configured else "not_checked",
        freshness="current" if attach_ready or validation_ready or configured else "not_checked",
        blockers=[],
        warnings=warnings or ([f"Credentials not configured: {', '.join(credential_missing)}"] if credential_missing else []),
        recheck_command="make provider-lab-vcenter-post-attach-validation" if configured else "make provider-lab-vcenter-netapp-readiness",
        linked_workflow_action=_action_link(actions, "vcenter.post-attach-validation" if configured else "vcenter-netapp.readiness"),
    )


def _netapp_console_item(
    netapp_state: dict[str, Any],
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled"):
        return _not_in_scope_item(
            item_id="netapp-console",
            label="NetApp Console",
            category="Storage",
            reason="NetApp is disabled by the active lab profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "netapp.console-read-state"),
        )
    artifacts = _existing(
        [
            "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
            "artifacts/codex-runs/netapp-console-state-report.md",
            "artifacts/codex-runs/netapp-console-login-state-report.md",
        ]
    )
    console = netapp_state.get("console") if isinstance(netapp_state.get("console"), dict) else {}
    port = console.get("discovered_port") or _json_value("artifacts/codex-runs/netapp-console-state-redacted.json", "selected_port")
    baud = console.get("baud") or _json_value("artifacts/codex-runs/netapp-console-state-redacted.json", "selected_baud")
    state = _netapp_console_state(netapp_state)
    return _item(
        item_id="netapp-console",
        label="NetApp Console",
        category="Storage",
        status="ready" if state == "cluster_setup_wizard" or port else "not_checked",
        current_state=state,
        desired_state="Console autodiscovery and safe state read are available before setup.",
        setup_summary="Console autodiscovery works; NetApp setup has not been applied yet." if state == "cluster_setup_wizard" else "NetApp console proof needs refresh.",
        next_action="Review setup plan; do not enter setup commands without a guarded apply workflow.",
        login_hint=f"{port or 'console port not selected'} @ {baud or 115200}",
        management_url=None,
        ssh_target=None,
        proof_points=[
            "Console port is the MCP2221 USB serial adapter when discovered.",
            "No NetApp setup, storage, reboot, wipe, or upgrade command is part of validation.",
        ],
        evidence_artifacts=artifacts,
        last_checked=_last_checked(artifacts),
        source_type=_source_for_artifacts(artifacts),
        freshness=_freshness_for_artifacts(artifacts),
        blockers=[],
        warnings=["Console evidence is supporting proof; rerun read-state for fresh handoff."],
        recheck_command="make provider-lab-netapp-console-read-state",
        linked_workflow_action=_action_link(actions, "netapp.console-read-state"),
    )


def _netapp_ontap_item(
    netapp_state: dict[str, Any],
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled"):
        return _not_in_scope_item(
            item_id="netapp-ontap-cluster",
            label="NetApp ONTAP / Cluster",
            category="Storage",
            reason="NetApp is disabled by the active lab profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "netapp.validate-setup"),
        )
    state = _netapp_console_state(netapp_state)
    configured = bool(netapp_state.get("configured"))
    artifacts = _existing(
        [
            "artifacts/codex-runs/netapp-live-state-report.md",
            "artifacts/codex-runs/netapp-setup-plan-report.md",
            "artifacts/codex-runs/netapp-setup-preview-report.md",
        ]
    )
    blocked = state == "cluster_setup_wizard" or not configured
    blockers = [
        _blocker(
            problem="NetApp ONTAP cluster setup has not been applied yet.",
            source="NetApp console/runtime state",
            current_value=state,
            expected_value="ONTAP cluster configured with management access",
            where_to_fix="Run Center / NetApp",
            recommended_action="Complete guarded NetApp setup planning before any vCenter datastore work.",
            recheck_command="make provider-lab-netapp-validate-setup",
            evidence_links=artifacts,
        )
    ] if blocked else []
    return _item(
        item_id="netapp-ontap-cluster",
        label="NetApp ONTAP / Cluster",
        category="Storage",
        status="blocked" if blocked else "ready",
        current_state=state,
        desired_state=f"ONTAP cluster management reachable at {settings.netapp_cluster_mgmt_ip}.",
        setup_summary="ONTAP cluster is still in setup wizard." if blocked else "ONTAP cluster is configured.",
        next_action="Run NetApp setup preview and resolve missing intent before REST/SSH/NFS readiness." if blocked else "Refresh live NetApp validation.",
        login_hint=_login_hint(f"https://{settings.netapp_cluster_mgmt_ip}", _missing_credentials([("NETAPP_API_USERNAME", settings.netapp_api_username), ("NETAPP_API_PASSWORD", settings.netapp_api_password)])),
        management_url=f"https://{settings.netapp_cluster_mgmt_ip}",
        ssh_target=f"admin@{settings.netapp_cluster_mgmt_ip}",
        proof_points=[
            "NetApp REST/SSH are not configured until ONTAP setup completes.",
            f"After setup, log in at https://{settings.netapp_cluster_mgmt_ip} or SSH to admin@{settings.netapp_cluster_mgmt_ip}.",
        ],
        evidence_artifacts=artifacts,
        last_checked=_last_checked(artifacts),
        source_type=netapp_state.get("source_type") or _source_for_artifacts(artifacts),
        freshness=netapp_state.get("freshness") or _freshness_for_artifacts(artifacts),
        blockers=blockers,
        warnings=[],
        recheck_command="make provider-lab-netapp-validate-setup",
        linked_workflow_action=_action_link(actions, "netapp.validate-setup"),
    )


def _netapp_upgrade_item(
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled"):
        return _not_in_scope_item(
            item_id="netapp-ontap-upgrade",
            label="NetApp ONTAP Upgrade",
            category="Storage",
            reason="NetApp upgrade is disabled because NetApp is not in scope for the active profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "netapp.ontap-upgrade-validate"),
        )
    plan = build_netapp_upgrade_plan(write_report=False)
    artifacts = _existing(
        [
            "artifacts/codex-runs/netapp-upgrade-inventory-report.md",
            "artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md",
            "artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md",
            "artifacts/codex-runs/netapp-ontap-upgrade-apply-report.md",
        ]
    )
    blockers = [
        _blocker(
            problem=str(item),
            source="NetApp ONTAP Upgrade Center",
            current_value=str(plan.get("button_state") or plan.get("status")),
            expected_value="Upgrade button state Ready to upgrade",
            where_to_fix="Run Center / NetApp / Upgrade Center",
            recommended_action="Run ONTAP upgrade inventory, plan, and validation after NetApp setup completes.",
            recheck_command="make provider-lab-netapp-ontap-upgrade-validate",
            evidence_links=artifacts,
        )
        for item in plan.get("blockers") or []
    ]
    status = "ready" if plan.get("status") in {"ready", "current"} else "blocked" if blockers else "not_checked"
    return _item(
        item_id="netapp-ontap-upgrade",
        label="NetApp ONTAP Upgrade",
        category="Storage",
        status=status,
        current_state=str(plan.get("button_state") or plan.get("status") or "not_checked"),
        desired_state="ONTAP upgrade inventory, image/package, validation, and guarded apply gates are ready.",
        setup_summary=(
            f"Current ONTAP version `{plan.get('current_version') or 'unknown'}`; "
            f"target `{plan.get('target_version') or 'not selected'}`."
        ),
        next_action=str(plan.get("next_safe_action") or "Run ONTAP upgrade inventory."),
        login_hint=f"After setup: https://{settings.netapp_cluster_mgmt_ip} and admin@{settings.netapp_cluster_mgmt_ip}; values stay redacted.",
        management_url=f"https://{settings.netapp_cluster_mgmt_ip}",
        ssh_target=f"admin@{settings.netapp_cluster_mgmt_ip}",
        proof_points=[
            f"Current ONTAP version: {plan.get('current_version') or 'unknown'}",
            f"Upgrade target: {plan.get('target_version') or 'not selected'}",
            f"Upgrade button state: {plan.get('button_state') or 'not checked'}",
            "Upgrade apply requires explicit flags and pre-upgrade validation.",
        ],
        evidence_artifacts=artifacts,
        last_checked=_last_checked(artifacts),
        source_type=_source_for_artifacts(artifacts),
        freshness=_freshness_for_artifacts(artifacts),
        blockers=blockers,
        warnings=list(plan.get("warnings") or []),
        recheck_command="make provider-lab-netapp-ontap-upgrade-validate",
        linked_workflow_action=_action_link(actions, "netapp.ontap-upgrade-validate"),
    )


def _netapp_nfs_item(
    netapp_state: dict[str, Any],
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled"):
        return _not_in_scope_item(
            item_id="netapp-nfs",
            label="NetApp NFS",
            category="Storage",
            reason="NetApp NFS is disabled because NetApp is not in scope for the active profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "vcenter-netapp.readiness"),
        )
    state = _netapp_console_state(netapp_state)
    validation = _json_artifact("artifacts/codex-runs/netapp-nfs-setup-validation-redacted.json")
    readiness = validation.get("readiness") if isinstance(validation.get("readiness"), dict) else {}
    live_nfs = validation.get("live_nfs") if isinstance(validation.get("live_nfs"), dict) else {}
    validation_status = str(validation.get("status") or "")
    blocked = validation_status == "blocked" or (not validation_status and (state == "cluster_setup_wizard" or not netapp_state.get("configured")))
    artifacts = _existing(
        [
            "artifacts/codex-runs/netapp-nfs-setup-validation-report.md",
            "artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md",
        ]
    )
    validation_blockers = [str(item) for item in validation.get("blockers") or []]
    blockers = [
        _blocker(
            problem=str(problem),
            source="NetApp NFS validation",
            current_value=validation_status or "not created",
            expected_value=f"NFS volume/export for datastore {settings.netapp_nfs_datastore_name}",
            where_to_fix="Run Center / NetApp",
            recommended_action=str(validation.get("next_safe_action") or "Finish NetApp ONTAP setup and NFS planning first."),
            recheck_command="make provider-lab-netapp-nfs-setup-validate",
            evidence_links=artifacts,
        )
        for problem in (
            validation_blockers
            if validation_blockers
            else ["NetApp NFS datastore backing volume/export is not created yet."] if blocked else []
        )
    ]
    nfs_checks = live_nfs.get("checks") if isinstance(live_nfs.get("checks"), dict) else {}
    lif_checks = nfs_checks.get("planned_nfs_lifs_2049") if isinstance(nfs_checks.get("planned_nfs_lifs_2049"), list) else []
    reachable_lifs = [
        str(check.get("host"))
        for check in lif_checks
        if isinstance(check, dict) and check.get("reachable") is True and check.get("host")
    ]
    proof_points = [
        f"NFS validation status: {validation_status or ('blocked' if blocked else 'ready')}",
        f"NFS service records: {nfs_checks.get('nfs_service_records', 'not checked')}",
        f"NFS LIFs reachable on 2049: {', '.join(reachable_lifs) if reachable_lifs else 'not checked'}",
    ]
    return _item(
        item_id="netapp-nfs",
        label="NetApp NFS",
        category="Storage",
        status="blocked" if blocked else "ready",
        current_state=(
            "NFS volume/export not created yet."
            if blocked
            else str(validation.get("message") or readiness.get("message") or "NFS readiness is configured.")
        ),
        desired_state=f"NFS LIFs {', '.join(settings.netapp_nfs_lifs)} export {settings.netapp_nfs_mount_path}.",
        setup_summary=f"Planned datastore backing volume `{settings.netapp_nfs_volume}` is not live yet." if blocked else "NetApp NFS is ready.",
        next_action=str(validation.get("next_safe_action") or "Validate NFS after ONTAP setup completes."),
        login_hint=f"Datastore backing target: {settings.netapp_nfs_datastore_name} via {settings.netapp_nfs_lifs[0] if settings.netapp_nfs_lifs else 'NFS LIF not configured'}",
        management_url=None,
        ssh_target=None,
        proof_points=proof_points,
        evidence_artifacts=artifacts,
        last_checked=str(validation.get("checked_at") or readiness.get("checked_at") or _last_checked(artifacts)),
        source_type=str(validation.get("source_type") or readiness.get("source_type") or _source_for_artifacts(artifacts)),
        freshness=str(validation.get("freshness") or readiness.get("freshness") or _freshness_for_artifacts(artifacts)),
        blockers=blockers,
        warnings=[str(item) for item in validation.get("warnings") or []],
        recheck_command="make provider-lab-netapp-nfs-setup-validate",
        linked_workflow_action=_action_link(actions, "netapp.nfs-setup-validate"),
    )


def _vcenter_netapp_item(
    readiness: dict[str, Any],
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    if not features.get("netapp_enabled") or not features.get("vcenter_enabled"):
        return _not_in_scope_item(
            item_id="vcenter-netapp-datastore",
            label="vCenter-NetApp Datastore",
            category="Storage",
            reason="NetApp or vCenter is disabled by the active lab profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "vcenter-netapp.readiness"),
        )
    status_map = {
        "ready": "ready",
        "not_configured_yet": "not_configured",
        "blocked_by_prior_stage": "blocked",
    }
    artifacts = _existing(["artifacts/codex-runs/vcenter-netapp-readiness-report.md", "artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md"])
    blockers = [
        _blocker(
            problem=str(item),
            source="vCenter-NetApp readiness",
            current_value=str(readiness.get("netapp_stage") or readiness.get("status")),
            expected_value="vCenter, ESXi, ONTAP, and NFS datastore prerequisites ready",
            where_to_fix="Run Center / NetApp",
            recommended_action=str(readiness.get("next_safe_action")),
            recheck_command="make provider-lab-vcenter-netapp-readiness",
            evidence_links=artifacts,
        )
        for item in readiness.get("blockers") or []
    ]
    targets = readiness.get("targets") if isinstance(readiness.get("targets"), dict) else {}
    return _item(
        item_id="vcenter-netapp-datastore",
        label="vCenter-NetApp Datastore",
        category="Storage",
        status=status_map.get(str(readiness.get("status")), "warning"),
        current_state=str(readiness.get("status")),
        desired_state=f"Datastore `{targets.get('datastore_name') or settings.netapp_nfs_datastore_name}` mounted through vCenter/ESXi.",
        setup_summary=str(readiness.get("message")),
        next_action=str(readiness.get("next_safe_action")),
        login_hint=f"vCenter: {targets.get('vcenter') or 'VCENTER_HOST / GOVC_URL not configured'}; datastore: {targets.get('datastore_name') or settings.netapp_nfs_datastore_name}",
        management_url=targets.get("vcenter"),
        ssh_target=None,
        proof_points=[
            "Datastore add command preview is available in the detail panel.",
            "Future apply is write-capable and intentionally disabled.",
        ],
        evidence_artifacts=artifacts,
        last_checked=readiness.get("checked_at"),
        source_type=str(readiness.get("source_type") or "not_checked"),
        freshness=str(readiness.get("freshness") or "not_checked"),
        blockers=blockers,
        warnings=[str(item) for item in readiness.get("warnings") or []],
        recheck_command="make provider-lab-vcenter-netapp-readiness",
        linked_workflow_action=_action_link(actions, "vcenter-netapp.readiness"),
    )


def _esxi_iscsi_datastore_item(
    actions: dict[str, dict[str, Any]],
    *,
    profile_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_context = profile_context or active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    storage_protocol = str(features.get("storage_protocol") or settings.netapp_storage_protocol or "").strip().lower()
    in_scope_protocols = {"iscsi", "both", "nfs+iscsi", "nfs,iscsi", "shared_iscsi"}
    if not features.get("netapp_enabled"):
        return _not_in_scope_item(
            item_id="esxi-iscsi-datastore",
            label="ESXi iSCSI Datastore",
            category="Storage",
            reason="ESXi iSCSI datastore validation is disabled because NetApp shared storage is not in scope for the active profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "esxi.iscsi-datastore-validate"),
        )
    if storage_protocol not in in_scope_protocols:
        return _not_in_scope_item(
            item_id="esxi-iscsi-datastore",
            label="ESXi iSCSI Datastore",
            category="Storage",
            reason=f"Active storage protocol is `{storage_protocol or 'unset'}`; iSCSI is available as an option but not selected for this profile.",
            recheck_command="make provider-lab-validation",
            linked_workflow_action=_action_link(actions, "esxi.iscsi-datastore-validate"),
        )

    artifacts = _existing(
        [
            "artifacts/codex-runs/esxi-iscsi-datastore-validation-report.md",
            "artifacts/codex-runs/esxi-iscsi-datastore-validation-redacted.json",
            "artifacts/codex-runs/esxi-iscsi-datastore-preview-report.md",
            "artifacts/codex-runs/esxi-iscsi-datastore-preview-redacted.json",
        ]
    )
    payload = _json_artifact("artifacts/codex-runs/esxi-iscsi-datastore-validation-redacted.json")
    if not payload:
        payload = _json_artifact("artifacts/codex-runs/esxi-iscsi-datastore-preview-redacted.json")
    current = payload.get("current_state") if isinstance(payload.get("current_state"), dict) else {}
    plan = payload.get("iscsi_plan") if isinstance(payload.get("iscsi_plan"), dict) else {}
    netapp_validation = payload.get("netapp_validation") if isinstance(payload.get("netapp_validation"), dict) else {}
    netapp_status = str(netapp_validation.get("status") or "not_checked")
    raw_status = str(payload.get("status") or "not_checked")
    checked = bool(current.get("checked"))
    datastore_name = str(plan.get("datastore_name") or "netapp_iscsi_ds01")
    path_count = int(current.get("iscsi_path_count") or 0)
    datastore_visible = bool(current.get("datastore_visible"))
    blockers = [
        _blocker(
            problem=str(item),
            source="ESXi iSCSI datastore validation",
            current_value=(
                f"NetApp {netapp_status}; ESXi paths {path_count}; datastore visible {datastore_visible}"
                if checked
                else "not checked"
            ),
            expected_value=f"NetApp iSCSI objects ready, ESXi iSCSI path active, and VMFS datastore {datastore_name} visible",
            where_to_fix="Storage / ESXi iSCSI",
            recommended_action=str(payload.get("next_safe_action") or "Run ESXi iSCSI preview/validation and resolve the first reported blocker."),
            recheck_command="make provider-lab-esxi-iscsi-datastore-validate",
            evidence_links=artifacts,
        )
        for item in payload.get("blockers") or []
    ]
    if raw_status in {"ready", "completed"} and checked and datastore_visible and not blockers:
        status = "ready"
    elif blockers:
        status = "blocked"
    elif artifacts:
        status = "partial" if raw_status == "preview_ready" else "warning"
    else:
        status = "not_checked"
    return _item(
        item_id="esxi-iscsi-datastore",
        label="ESXi iSCSI Datastore",
        category="Storage",
        status=status,
        current_state=(
            f"NetApp {netapp_status}; ESXi adapters {current.get('adapter_count', 0)}; "
            f"iSCSI paths {path_count}; datastore visible {datastore_visible}."
            if artifacts
            else "No ESXi iSCSI datastore validation artifact exists yet."
        ),
        desired_state=f"VMFS datastore `{datastore_name}` visible on ESXi from NetApp iSCSI LUN.",
        setup_summary=str(payload.get("message") or "Run a read-only ESXi iSCSI validation before any guarded attach workflow."),
        next_action=str(payload.get("next_safe_action") or "Run ESXi iSCSI datastore validation."),
        login_hint=f"ESXi: {settings.esxi_test_host}; iSCSI target: {plan.get('preferred_iscsi_lif') or 'not selected'}",
        management_url=None,
        ssh_target=f"root@{settings.esxi_test_host}" if settings.esxi_test_host else None,
        proof_points=[
            f"NetApp iSCSI status: {netapp_status}",
            f"ESXi adapter count: {current.get('adapter_count', 0)}",
            f"ESXi iSCSI path count: {path_count}",
            f"Datastore visible: {datastore_visible}",
            "Validation is read-only and does not add targets, rescan adapters, format VMFS, or mount datastores.",
        ],
        evidence_artifacts=artifacts,
        last_checked=payload.get("checked_at") or _last_checked(artifacts),
        source_type=str(payload.get("source_type") or _source_for_artifacts(artifacts)),
        freshness=str(payload.get("freshness") or _freshness_for_artifacts(artifacts)),
        blockers=blockers,
        warnings=[str(item) for item in payload.get("warnings") or []],
        recheck_command="make provider-lab-esxi-iscsi-datastore-validate",
        linked_workflow_action=_action_link(actions, "esxi.iscsi-datastore-validate"),
    )


def _build_verification_item(build_verification: dict[str, Any], actions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    artifacts = _existing(
        [
            "artifacts/codex-runs/build-verification-report.md",
            "artifacts/codex-runs/build-verification-summary-redacted.json",
            "artifacts/codex-runs/build-verification-evidence-report.md",
        ]
    )
    raw_status = str(build_verification.get("status") or "not_run")
    status = "ready" if raw_status in {"completed", "ready"} else "warning" if raw_status == "warning" else "not_checked" if raw_status == "not_run" else "blocked"
    blockers = [
        _blocker(
            problem=str(item),
            source="Build Verification",
            current_value=raw_status,
            expected_value="completed or warning-only certification",
            where_to_fix="Build Verification",
            recommended_action=str(build_verification.get("next_safe_action") or "Run Build Verification."),
            recheck_command="make provider-lab-build-verification",
            evidence_links=artifacts,
        )
        for item in build_verification.get("blockers") or []
    ]
    return _item(
        item_id="build-verification",
        label="Build Verification",
        category="Certification",
        status=status,
        current_state=raw_status,
        desired_state="Build Verification has current redacted certification evidence.",
        setup_summary=str(build_verification.get("message") or "Build Verification has not run."),
        next_action=str(build_verification.get("next_safe_action") or "Run Build Verification."),
        login_hint="No login target; use proof/evidence reports.",
        management_url=None,
        ssh_target=None,
        proof_points=["Build Verification evidence is redacted and collapsed by default."],
        evidence_artifacts=artifacts,
        last_checked=build_verification.get("checked_at") or _last_checked(artifacts),
        source_type=str(build_verification.get("source_type") or _source_for_artifacts(artifacts)),
        freshness=str(build_verification.get("freshness") or _freshness_for_artifacts(artifacts)),
        blockers=blockers,
        warnings=[str(item) for item in build_verification.get("warnings") or []],
        recheck_command="make provider-lab-build-verification",
        linked_workflow_action=_action_link(actions, "build-verification.run-full"),
    )


def _item(
    *,
    item_id: str,
    label: str,
    category: str,
    status: str,
    current_state: str,
    desired_state: str,
    setup_summary: str,
    next_action: str,
    login_hint: str,
    management_url: str | None,
    ssh_target: str | None,
    proof_points: list[Any],
    evidence_artifacts: list[Any],
    last_checked: str | None,
    source_type: str,
    freshness: str,
    blockers: list[dict[str, Any]],
    warnings: list[Any],
    recheck_command: str,
    linked_workflow_action: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_status = status if status in VALIDATION_STATUSES else "warning"
    return {
        "id": item_id,
        "label": label,
        "category": category,
        "stage": category,
        "status": normalized_status,
        "current_state": current_state,
        "desired_state": desired_state,
        "setup_summary": setup_summary,
        "next_action": next_action,
        "login_hint": login_hint,
        "management_url": management_url,
        "ssh_target": ssh_target,
        "proof_points": _clean_unique_strings(proof_points),
        "evidence_artifacts": _clean_unique_strings(evidence_artifacts),
        "evidence_collapsed_by_default": True,
        "last_checked": last_checked,
        "source_type": source_type if source_type in {"live_probe", "live_cached", "historical_artifact", "not_checked"} else "not_checked",
        "freshness": freshness,
        "blockers": blockers,
        "warnings": _clean_unique_strings(warnings),
        "recheck_command": recheck_command,
        "linked_workflow_action": linked_workflow_action,
    }


def _not_in_scope_item(
    *,
    item_id: str,
    label: str,
    category: str,
    reason: str,
    recheck_command: str,
    linked_workflow_action: dict[str, Any] | None,
) -> dict[str, Any]:
    return _item(
        item_id=item_id,
        label=label,
        category=category,
        status="not_in_scope",
        current_state="not_in_scope",
        desired_state=reason,
        setup_summary=reason,
        next_action="Enable this feature in the active lab profile when it is intentionally in scope.",
        login_hint="Not in scope for the active lab profile.",
        management_url=None,
        ssh_target=None,
        proof_points=[reason],
        evidence_artifacts=[],
        last_checked=None,
        source_type="not_checked",
        freshness="not_checked",
        blockers=[],
        warnings=[],
        recheck_command=recheck_command,
        linked_workflow_action=linked_workflow_action,
    )


def _blocker(
    *,
    problem: str,
    source: str,
    current_value: str,
    expected_value: str,
    where_to_fix: str,
    recommended_action: str,
    recheck_command: str,
    evidence_links: list[str],
) -> dict[str, Any]:
    return {
        "problem": problem,
        "source": source,
        "current_value": current_value,
        "expected_value": expected_value,
        "where_to_fix": where_to_fix,
        "recommended_action": recommended_action,
        "copyable_command": recheck_command,
        "recheck_command": recheck_command,
        "evidence_links": evidence_links,
    }


def _clean_unique_strings(values: list[Any]) -> list[str]:
    return unique_preserving_order(
        text for text in (str(value).strip() for value in values if value is not None) if text
    )


def _progress_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {status: 0 for status in VALIDATION_STATUSES}
    for item in items:
        counts[str(item["status"])] += 1
    return counts


def _overall_status(counts: dict[str, int]) -> str:
    if counts["blocked"]:
        return "blocked"
    if counts["partial"] or counts["warning"]:
        return "partial"
    if counts["not_configured"]:
        return "not_configured"
    if counts["not_checked"]:
        return "not_checked"
    return "ready"


def _top_blocker(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if item["status"] == "blocked" and item.get("blockers"):
            blocker = dict(item["blockers"][0])
            blocker["component_id"] = item["id"]
            blocker["component_label"] = item["label"]
            return blocker
    return None


def _remaining_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actionable = [
        item
        for item in items
        if item.get("status") in {"blocked", "not_configured", "not_checked"} and item.get("status") != "not_in_scope"
    ]
    if actionable:
        return actionable
    partials = [item for item in items if item.get("status") in {"partial", "warning"}]
    firmware = [item for item in partials if item.get("id") == "firmware-compliance"]
    other_actionable_partials = [item for item in partials if item.get("id") != "firmware-compliance" and item.get("blockers")]
    if firmware and not other_actionable_partials:
        return firmware
    return partials


def _only_expected_firmware_partial(items: list[dict[str, Any]]) -> bool:
    return len(items) == 1 and items[0].get("id") == "firmware-compliance" and items[0].get("status") in {"partial", "warning"}


def _summary_next_action(top_blocker: dict[str, Any] | None, remaining_items: list[dict[str, Any]]) -> str:
    if top_blocker:
        return str(top_blocker.get("recommended_action") or top_blocker.get("recheck_command") or "")
    if _only_expected_firmware_partial(remaining_items):
        firmware = remaining_items[0]
        return (
            f"{firmware.get('next_action')} No vCenter-NetApp datastore action required."
        )
    if not remaining_items:
        return "No Lab Validation action required; current handoff rows are ready."
    return "Review Lab Validation rows and refresh the first not-checked stage."


def _proof_links(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        for path in item.get("evidence_artifacts") or []:
            if path in seen:
                continue
            seen.add(path)
            links.append({"component_id": str(item["id"]), "component_label": str(item["label"]), "path": path})
    return links


def _existing(paths: list[str]) -> list[str]:
    existing: list[str] = []
    for path in paths:
        if path_exists(REPO_ROOT / path):
            existing.append(path)
    return existing


def _last_checked(paths: list[str]) -> str | None:
    latest_mtime = None
    for path in paths:
        artifact = REPO_ROOT / path
        if not path_exists(artifact):
            continue
        mtime = path_mtime(artifact)
        if mtime is None:
            continue
        if latest_mtime is None or mtime > latest_mtime:
            latest_mtime = mtime
    if latest_mtime is None:
        return None
    return datetime.fromtimestamp(latest_mtime, UTC).isoformat()


def _source_for_artifacts(paths: list[str]) -> str:
    return "historical_artifact" if paths else "not_checked"


def _freshness_for_artifacts(paths: list[str]) -> str:
    return "historical" if paths else "not_checked"


def _missing_credentials(fields: list[tuple[str, Any]]) -> list[str]:
    return [name for name, value in fields if not value]


def _login_hint(target: str, missing_fields: list[str]) -> str:
    if not missing_fields:
        return target
    return f"{target}; credentials not configured: {', '.join(missing_fields)}"


def _action_link(actions: dict[str, dict[str, Any]], action_id: str) -> dict[str, Any] | None:
    action = actions.get(action_id)
    if not action:
        return None
    return {
        "action_id": action_id,
        "label": action.get("label"),
        "stage": action.get("stage"),
        "command": action.get("command"),
        "run_endpoint": action.get("run_endpoint"),
        "ui_run_supported": action.get("ui_run_supported"),
    }


def _latest_action_trace(actions: dict[str, dict[str, Any]], action_id: str) -> dict[str, Any]:
    action = actions.get(action_id)
    if not action:
        return {}
    trace = action.get("last_run_trace")
    return trace if isinstance(trace, dict) else {}


def _netapp_console_state(state: dict[str, Any]) -> str:
    console = state.get("console") if isinstance(state.get("console"), dict) else {}
    prompt = str(console.get("prompt_state") or _json_value("artifacts/codex-runs/netapp-console-state-redacted.json", "selected_prompt_state") or "")
    configured_state = str(state.get("configured_state") or "")
    if prompt == "cluster_setup_prompt" or configured_state == "setup_wizard":
        return "cluster_setup_wizard"
    if state.get("configured"):
        return "configured"
    if configured_state:
        return configured_state
    return "not_checked"


def _json_value(path: str, key: str) -> Any:
    payload = _json_artifact(path)
    return payload.get(key) if isinstance(payload, dict) else None


def _json_artifact(path: str) -> dict[str, Any]:
    artifact = REPO_ROOT / path
    return read_json_object(artifact)


def _vcenter_post_attach_ready(payload: dict[str, Any]) -> bool:
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    required = (
        "datacenter_visible",
        "cluster_visible",
        "esxi_visible",
        "netapp_datastore_visible",
        "vm_inventory_visible",
    )
    return payload.get("status") == "ready" and all(
        isinstance(checks.get(key), dict) and checks[key].get("visible") is True
        for key in required
    )


def _redacted_url(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "://" not in text:
        return text
    parts = urlsplit(text)
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _handoff_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Lab Validation / Handoff Report",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Overall status: `{payload.get('overall_status')}`",
        "- Secrets: not included; credential state is field-name only.",
        "- Hardware workflows: no destructive workflow was run by this report.",
        "",
        "## Lab Profile",
        "",
    ]
    profile = next((item for item in payload.get("validation_items", []) if item.get("id") == "lab-profile"), None)
    if profile:
        lines.extend(f"- {point}" for point in profile.get("proof_points") or [])
    lines.extend(["", "## Setup Status By Component", "", "| Component | Status | Setup Summary | Login / Proof | Next Action |", "| --- | --- | --- | --- | --- |"])
    for item in payload.get("validation_items") or []:
        lines.append(
            "| {label} | `{status}` | {summary} | {login} | {next_action} |".format(
                label=item.get("label"),
                status=item.get("status"),
                summary=_md_cell(item.get("setup_summary")),
                login=_md_cell(item.get("login_hint")),
                next_action=_md_cell(item.get("next_action")),
            )
        )
    lines.extend(["", "## Current Blockers", ""])
    blocker = payload.get("top_blocker")
    if blocker:
        lines.append(f"- {blocker.get('component_label')}: {blocker.get('problem')}")
        lines.append(f"  - Next action: `{blocker.get('recheck_command')}`")
    else:
        lines.append("- None")
    lines.extend(["", "## Evidence Links", ""])
    for link in payload.get("proof_links") or []:
        lines.append(f"- {link.get('component_label')}: `{link.get('path')}`")
    lines.extend(["", "## What Remains", ""])
    remaining_items = _remaining_items(payload.get("validation_items") or [])
    if _only_expected_firmware_partial(remaining_items):
        firmware = remaining_items[0]
        lines.append(f"- Firmware Compliance: {firmware.get('next_action')}")
        for point in firmware.get("proof_points") or []:
            if "path current" in str(point).lower() or "manual" in str(point).lower() or "blocked" in str(point).lower():
                lines.append(f"  - {point}")
    elif remaining_items:
        for item in remaining_items:
            lines.append(f"- {item.get('label')}: {item.get('next_action')}")
    else:
        lines.append("- None")
    lines.extend(["", "## Skill Improvement Review", "", "- Skills used: lab-builder-skill-steward, lab-builder-real-runtime, lab-builder-ux, lab-builder-product-craft, lab-builder-hardware-run, lab-builder-report-remediation, lab-builder-toolchain, lab-builder-dual-app-architecture", "- Skills created or updated: none", "- Skill gaps found: none requiring a new reusable skill in this pass", "- Candidate skills deferred: none", "- No additional skills were created because this work fits the existing Lab Builder skill set."])
    return "\n".join(lines) + "\n"


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()
