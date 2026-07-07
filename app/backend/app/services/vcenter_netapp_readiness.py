from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from ipaddress import ip_network
from pathlib import Path
from shutil import which
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from app.core.config import LAB_ESXI_MANAGEMENT_IP, settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, LOCAL_READONLY_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.env_utils import env_flag as _env_flag
from app.services.json_file_store import read_json_object, write_json_object, write_json_value, write_text_value
from app.services.json_utils import parse_json_value
from app.services.lab_profiles import active_lab_profile_context
from app.services.list_utils import unique_csv_strings, unique_preserving_order, unique_strings
from app.services.netapp_state import get_netapp_runtime_state
from app.services.path_utils import display_path, is_directory, is_file, path_exists, repo_relative_path, rglob_paths
from app.services.temp_file_utils import remove_file_best_effort

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
READINESS_REPORT = CODEX_RUN_DIR / "vcenter-netapp-readiness-report.md"
PLAN_REPORT = CODEX_RUN_DIR / "vcenter-netapp-datastore-plan-report.md"
READINESS_JSON = CODEX_RUN_DIR / "vcenter-netapp-readiness-redacted.json"
VCENTER_INSTALL_READINESS_REPORT = CODEX_RUN_DIR / "vcenter-install-readiness-report.md"
VCENTER_INSTALL_PLAN_REPORT = CODEX_RUN_DIR / "vcenter-install-plan-report.md"
VCENTER_INSTALL_PREVIEW_REPORT = CODEX_RUN_DIR / "vcenter-install-preview-report.md"
VCENTER_INSTALL_APPLY_REPORT = CODEX_RUN_DIR / "vcenter-install-apply-report.md"
VCENTER_POST_INSTALL_VALIDATION_REPORT = CODEX_RUN_DIR / "vcenter-post-install-validation-report.md"
VCENTER_INSTALL_APPLY_FINAL_REPORT = CODEX_RUN_DIR / "vcenter-install-apply-unblock-final-report.md"
VCENTER_ATTACH_ESXI_PREVIEW_REPORT = CODEX_RUN_DIR / "vcenter-attach-esxi-preview-report.md"
VCENTER_ATTACH_ESXI_APPLY_REPORT = CODEX_RUN_DIR / "vcenter-attach-esxi-apply-report.md"
VCENTER_POST_ATTACH_VALIDATION_REPORT = CODEX_RUN_DIR / "vcenter-post-attach-validation-report.md"
VCENTER_ATTACH_ESXI_FINAL_REPORT = CODEX_RUN_DIR / "vcenter-attach-esxi-datastore-final-report.md"
VCENTER_INSTALL_READINESS_JSON = CODEX_RUN_DIR / "vcenter-install-readiness-redacted.json"
VCENTER_INSTALL_PLAN_JSON = CODEX_RUN_DIR / "vcenter-install-plan-redacted.json"
VCENTER_INSTALL_PREVIEW_JSON = CODEX_RUN_DIR / "vcenter-install-preview-redacted.json"
VCENTER_INSTALL_APPLY_JSON = CODEX_RUN_DIR / "vcenter-install-apply-redacted.json"
VCENTER_POST_INSTALL_VALIDATION_JSON = CODEX_RUN_DIR / "vcenter-post-install-validation-redacted.json"
VCENTER_ATTACH_ESXI_PREVIEW_JSON = CODEX_RUN_DIR / "vcenter-attach-esxi-preview-redacted.json"
VCENTER_ATTACH_ESXI_APPLY_JSON = CODEX_RUN_DIR / "vcenter-attach-esxi-apply-redacted.json"
VCENTER_POST_ATTACH_VALIDATION_JSON = CODEX_RUN_DIR / "vcenter-post-attach-validation-redacted.json"
VCENTER_INSTALL_SPEC_REDACTED_JSON = CODEX_RUN_DIR / "vcenter-install-spec-redacted.json"
CONSOLE_STATE_JSON = CODEX_RUN_DIR / "netapp-console-state-redacted.json"
CONSOLE_LOGIN_STATE_JSON = CODEX_RUN_DIR / "netapp-console-login-state-redacted.json"
VCENTER_INSTALL_CONFIRM_PHRASE = "DEPLOY VCENTER"
VCENTER_ATTACH_ESXI_CONFIRM_PHRASE = "ATTACH ESXI TO VCENTER"
VCENTER_INSTALL_POLICY_ACTION_ID = "vcenter.vcsa-deploy"
VCENTER_ATTACH_ESXI_POLICY_ACTION_ID = "vcenter.attach-esxi"
VCENTER_INSTALL_DEPLOY_TIMEOUT_SECONDS = 7200
VCENTER_INSTALL_VALIDATE_WAIT_SECONDS = 600
VCENTER_ATTACH_ESXI_TIMEOUT_SECONDS = 900


def _default_vcsa_mount_roots() -> tuple[Path, ...]:
    if os.name == "nt":
        return (Path(tempfile.gettempdir()) / "vcsa-iso",)
    return (
        Path("/tmp/vcsa-iso"),
        Path("/mnt/vcsa-iso"),
        Path("/media/vcsa-iso"),
        Path("/run/media/vcsa-iso"),
    )


VCSA_MOUNT_ROOTS = _default_vcsa_mount_roots()


def get_vcenter_netapp_readiness(
    *,
    check_ports: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    generated_at = _now()
    profile_context = active_lab_profile_context()
    features = profile_context.get("enabled_features") or {}
    plan = profile_context.get("resolved_address_plan") or {}
    if not features.get("netapp_enabled") or not features.get("vcenter_enabled"):
        payload = {
            "provider_id": "vcenter-netapp",
            "action": "vcenter-netapp-readiness",
            "checked_at": generated_at,
            "generated_at": generated_at,
            "status": "not_in_scope",
            "message": "vCenter-NetApp readiness is not in scope for the active lab profile.",
            "mode": settings.provider_mode,
            "apply_enabled": False,
            "source_type": "not_checked",
            "freshness": "not_checked",
            "netapp_stage": "not_in_scope",
            "targets": {
                "vcenter": None,
                "esxi_management": plan.get("esxi_management"),
                "netapp_cluster_management": None,
                "netapp_nfs_lif": None,
                "datastore_name": settings.netapp_nfs_datastore_name,
            },
            "credential_state": {
                "vcenter_host_configured": False,
                "vcenter_credentials_configured": False,
                "netapp_credentials_configured": False,
                "missing_fields": [],
            },
            "tooling": {
                "govc_available": False,
                "govc_path": "not_in_scope",
            },
            "planned_nfs": {
                "planned": False,
                "missing_fields": [],
                "nfs_lifs": [],
            },
            "checks": {},
            "datastore_add_preview": {},
            "blockers": [],
            "warnings": [
                "NetApp or vCenter is disabled by the active lab profile; this is not a validation blocker.",
            ],
            "not_attempted": [
                "ONTAP volume/export creation",
                "vCenter datastore mount",
                "ESXi datastore mount",
                "govc datastore.create execution",
                "ONTAP API write",
            ],
            "artifacts": {
                "readiness_report": _rel(READINESS_REPORT),
                "datastore_plan_report": _rel(PLAN_REPORT),
                "readiness_json": _rel(READINESS_JSON),
            },
            "next_safe_action": "Enable NetApp and vCenter in the active lab profile when this datastore workflow is intentionally in scope.",
        }
        sanitized = redact_sensitive(payload)
        if write_report:
            CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
            _write_json(READINESS_JSON, sanitized)
            write_text_value(READINESS_REPORT, _readiness_markdown(sanitized))
            write_text_value(PLAN_REPORT, _plan_markdown(sanitized))
        return sanitized
    netapp_state = get_netapp_runtime_state()
    netapp_stage = _netapp_stage(netapp_state)
    datastore_name = settings.netapp_nfs_datastore_name
    post_attach_state = _post_attach_vcenter_netapp_state(datastore_name=datastore_name)
    vcenter_management_ip = _clean_value(getattr(settings, "vcenter_management_ip", None))
    vcenter_target = (
        _redacted_url(settings.vcenter_host)
        or _redacted_url(_vcenter_govc_url(vcenter_management_ip))
        or post_attach_state.get("url")
        or post_attach_state.get("host")
    )
    first_lif = (list(settings.netapp_nfs_lifs) or [settings.netapp_svm_mgmt_ip])[0]
    govc_available = _tool_available("govc") or bool(post_attach_state.get("govc_available"))
    vcenter_host_configured = bool(
        settings.vcenter_host
        or vcenter_management_ip
        or settings.vcenter_configured
        or post_attach_state.get("ready")
    )
    vcenter_credentials_configured = bool(settings.vcenter_username and settings.vcenter_password) or bool(
        post_attach_state.get("credential_configured")
    )
    netapp_credentials_configured = bool(settings.netapp_api_username and settings.netapp_api_password)
    planned_nfs = _planned_nfs()

    checks = {
        "vcenter_configured": _config_check(
            "vCenter target",
            vcenter_host_configured,
            "vCenter target is configured or derived from deployed vCenter state.",
            "VCENTER_HOST / GOVC_URL / VCENTER_MANAGEMENT_IP is not configured and no ready post-attach validation target was found.",
        ),
        "govc_available": _config_check(
            "govc",
            govc_available,
            "govc is available on PATH or repo-local .local/bin.",
            "govc is not installed or not discoverable.",
        ),
        "vcenter_credentials_configured": _config_check(
            "vCenter credentials",
            vcenter_credentials_configured,
            "vCenter credential fields are configured.",
            "vCenter credential fields are missing: VCENTER_USERNAME/GOVC_USERNAME, VCENTER_PASSWORD/GOVC_PASSWORD.",
        ),
        "esxi_management_reachable": _tcp_check(
            "ESXi management",
            settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP,
            443,
            check_ports=check_ports,
        ),
        "netapp_cluster_management_reachable": _tcp_check(
            "NetApp cluster management",
            settings.netapp_cluster_mgmt_ip,
            443,
            check_ports=check_ports and netapp_stage not in {"cluster_setup_wizard", "not_configured"},
        ),
        "netapp_nfs_lif_reachable": _tcp_check(
            "NetApp NFS LIF",
            first_lif,
            2049,
            check_ports=check_ports and netapp_stage == "configured",
        ),
        "netapp_nfs_planned": _config_check(
            "NetApp NFS plan",
            planned_nfs["planned"],
            "NetApp NFS volume, export policy, mount path, and datastore name are planned.",
            "NetApp NFS volume/export/datastore plan is incomplete.",
        ),
        "netapp_nfs_exists": {
            "label": "NetApp NFS exists",
            "status": "not_checked",
            "detail": "ONTAP API existence checks are not attempted until ONTAP is configured and credentials are present.",
            "source_type": "not_checked",
        },
        "vcenter_post_attach_validation": _post_attach_validation_check(post_attach_state),
        "datastore_mounted": _post_attach_datastore_check(post_attach_state, datastore_name),
    }

    classification, blockers = _classify(
        netapp_stage=netapp_stage,
        vcenter_host_configured=vcenter_host_configured,
        vcenter_credentials_configured=vcenter_credentials_configured,
        govc_available=govc_available,
        planned_nfs=planned_nfs,
        post_attach_ready=bool(post_attach_state.get("ready")),
    )
    warnings = [
        "Preview only. No ONTAP, vCenter, ESXi, NFS, datastore, or storage write action is run.",
    ]
    if not netapp_credentials_configured:
        warnings.append("NetApp API credential fields are missing: NETAPP_API_USERNAME, NETAPP_API_PASSWORD.")
    if not check_ports:
        warnings.append("Reachability checks were not run for this API/readiness read; use the make target to refresh port checks.")

    payload = {
        "provider_id": "vcenter-netapp",
        "action": "vcenter-netapp-readiness",
        "checked_at": generated_at,
        "generated_at": generated_at,
        "status": classification,
        "message": _message(
            classification,
            post_attach_ready=bool(post_attach_state.get("ready")),
            datastore_name=datastore_name,
        ),
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if check_ports else "live_cached",
        "freshness": "current" if check_ports else "not_checked",
        "netapp_stage": netapp_stage,
        "targets": {
            "vcenter": vcenter_target,
            "vcenter_management_ip": vcenter_management_ip or post_attach_state.get("host"),
            "esxi_management": settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP,
            "netapp_cluster_management": settings.netapp_cluster_mgmt_ip,
            "netapp_nfs_lif": first_lif,
            "datastore_name": datastore_name,
        },
        "current_state": {
            "vcenter_version": post_attach_state.get("vcenter_version"),
            "vcenter_host": post_attach_state.get("host"),
            "vcenter_url": post_attach_state.get("url"),
        },
        "credential_state": {
            "vcenter_host_configured": vcenter_host_configured,
            "vcenter_credentials_configured": vcenter_credentials_configured,
            "netapp_credentials_configured": netapp_credentials_configured,
            "vcenter_target_derived": bool(post_attach_state.get("ready") and not settings.vcenter_host),
            "missing_fields": _missing_fields(vcenter_host_configured, vcenter_credentials_configured, netapp_credentials_configured),
        },
        "tooling": {
            "govc_available": govc_available,
            "govc_path": "configured" if govc_available else "not_found",
        },
        "planned_nfs": planned_nfs,
        "post_attach_validation": post_attach_state,
        "checks": checks,
        "datastore_add_preview": _datastore_preview(first_lif),
        "blockers": blockers,
        "warnings": warnings,
        "not_attempted": [
            "ONTAP volume/export creation",
            "vCenter datastore mount",
            "ESXi datastore mount",
            "govc datastore.create execution",
            "ONTAP API write",
        ],
        "artifacts": {
            "readiness_report": _rel(READINESS_REPORT),
            "datastore_plan_report": _rel(PLAN_REPORT),
            "readiness_json": _rel(READINESS_JSON),
        },
        "next_safe_action": _next_action(
            classification,
            post_attach_ready=bool(post_attach_state.get("ready")),
            datastore_name=datastore_name,
        ),
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(READINESS_JSON, sanitized)
        write_text_value(READINESS_REPORT, _readiness_markdown(sanitized))
        write_text_value(PLAN_REPORT, _plan_markdown(sanitized))
    return sanitized


def get_vcenter_netapp_datastore_plan(*, write_report: bool = True) -> dict[str, Any]:
    readiness = get_vcenter_netapp_readiness(check_ports=False, write_report=write_report)
    return {
        **readiness,
        "action": "vcenter-netapp-datastore-plan",
        "message": "vCenter-NetApp datastore plan generated. Preview only; no changes were made.",
    }


def get_vcenter_install_readiness(
    *,
    check_ports: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    generated_at = _now()
    profile_context = active_lab_profile_context()
    active_profile = profile_context.get("active_profile") if isinstance(profile_context.get("active_profile"), dict) else {}
    features = profile_context.get("enabled_features") or {}
    plan = profile_context.get("resolved_address_plan") or {}
    vcsa_iso = _find_vcsa_iso()
    deployment_values = _vcenter_deployment_values(plan=plan, active_profile=active_profile, vcsa_iso=vcsa_iso)
    value_checks = _vcenter_deployment_value_checks(deployment_values)
    credential_state = _vcenter_deployment_credential_state()
    deployment_values_complete = all(item.get("status") == "ready" for item in value_checks.values())
    deployment_values["complete"] = deployment_values_complete
    deployment_values["missing_fields"] = _missing_value_labels(value_checks)
    datastore_name = str(deployment_values.get("datastore_target") or settings.netapp_nfs_datastore_name)
    esxi_host = str(deployment_values.get("esxi_target") or settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP)
    vcenter_host_configured = bool(
        settings.vcenter_host or settings.vcenter_management_ip or settings.vcenter_configured
    )
    govc_available = _tool_available("govc")
    vcsa_deploy_status = _vcsa_deploy_status()
    vcenter_profile_enabled = _boolish(features.get("vcenter_enabled"), default=False)
    datastore_ready = _datastore_ready_check(datastore_name)
    management_ip_available = _ip_available_check(
        "vCenter management IP",
        deployment_values.get("management_ip"),
        check_ports=check_ports,
    )
    checks = {
        "vcenter_profile_scope": _config_check(
            "vCenter profile scope",
            vcenter_profile_enabled,
            "vCenter is marked configured by the active lab profile.",
            "vCenter is not configured yet by the active lab profile; this is expected partial until deployment completes.",
        ),
        "vcsa_iso_present": _config_check(
            "VCSA ISO",
            bool(vcsa_iso),
            "VCSA ISO media is present under the configured media roots.",
            "No VCSA ISO was found under MEDIA_INVENTORY_DIRS/artifacts/Media.",
        ),
        "esxi_management_reachable": _tcp_check("ESXi management", esxi_host, 443, check_ports=check_ports),
        "netapp_nfs_lif_reachable": _tcp_check(
            "NetApp NFS LIF",
            (settings.netapp_nfs_lifs or [None])[0],
            2049,
            check_ports=check_ports,
        ),
        "netapp_datastore_ready": datastore_ready,
        "vcenter_management_ip_available": management_ip_available,
        "govc_available": _config_check(
            "govc",
            govc_available,
            "govc is available.",
            "govc is not installed or not discoverable.",
        ),
        "vcsa_deploy_available": vcsa_deploy_status,
        "vcenter_values_complete": _config_check(
            "vCenter deployment values",
            deployment_values_complete,
            "All required vCenter deployment values are configured.",
            "One or more required vCenter deployment values are missing.",
        ),
        "vcenter_deployment_credentials_configured": _config_check(
            "vCenter deployment credentials",
            bool(credential_state["deployment_credentials_configured"]),
            "Local-only deployment credential fields are configured.",
            "Local-only deployment credential fields are missing.",
        ),
    }
    blockers = []
    if not vcsa_iso:
        blockers.append("VCSA ISO media was not found under the configured media roots.")
    if checks["esxi_management_reachable"]["status"] != "ready":
        blockers.append("ESXi management must be reachable before vCenter install planning can proceed.")
    if checks["netapp_nfs_lif_reachable"]["status"] != "ready":
        blockers.append("NetApp NFS LIF must be reachable before vCenter install planning can proceed.")
    if datastore_ready["status"] != "ready":
        blockers.append("NetApp datastore must be validated read/write before vCenter install planning can proceed.")
    if management_ip_available["status"] != "ready":
        blockers.append("vCenter management IP must be available before vCenter install planning can proceed.")
    if not govc_available:
        blockers.append("govc is required for target datastore/ESXi validation.")
    if vcsa_deploy_status["status"] != "ready":
        blockers.append("vcsa-deploy must be found and executable before guided VCSA install can run.")
    if not deployment_values_complete:
        blockers.append(
            "vCenter deployment values are incomplete: "
            + ", ".join(_missing_value_labels(value_checks))
            + "."
        )
    if not credential_state["deployment_credentials_configured"]:
        blockers.append(
            "vCenter deployment credentials are missing: "
            + ", ".join(credential_state["missing_fields"])
            + "."
        )
    readiness_ready = not blockers
    apply_gate_state = _vcenter_install_apply_gate_state(readiness_ready=readiness_ready)
    apply_enabled = readiness_ready and not apply_gate_state["blockers"]
    warnings = _vcenter_install_warnings(
        readiness_ready=readiness_ready,
        apply_gate_blockers=apply_gate_state["blockers"],
    )
    if not vcenter_profile_enabled:
        warnings.append("Golden State treats vCenter as expected partial until the appliance is deployed and configured.")
    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-install-readiness",
        "checked_at": generated_at,
        "generated_at": generated_at,
        "status": "blocked" if blockers else "ready",
        "message": "vCenter install readiness evaluated. No vCenter deployment was started.",
        "mode": settings.provider_mode,
        "apply_enabled": apply_enabled,
        "deploy_enabled": apply_enabled,
        "ready_for_deploy": apply_enabled,
        "apply_disabled_reason": _first_blocker([*blockers, *apply_gate_state["blockers"]]),
        "apply_gate_state": apply_gate_state,
        "source_type": "live_provider" if check_ports else "operator_config",
        "freshness": "live" if check_ports else "not_checked",
        "current_state": {
            "vcenter_installed": vcenter_host_configured,
            "esxi_management": esxi_host,
            "netapp_datastore": datastore_name,
            "netapp_datastore_access": datastore_ready.get("detail"),
            "vcsa_iso": _safe_media_path(vcsa_iso),
            "vcsa_deploy": vcsa_deploy_status.get("path"),
            "post_install_vcenter": _redacted_url(settings.vcenter_host),
        },
        "target_state": {
            "vcenter": deployment_values.get("management_ip"),
            "appliance_name": deployment_values.get("appliance_name"),
            "deployment_target": esxi_host,
            "datastore": datastore_name,
            "deployment_size": deployment_values.get("deployment_size"),
            "network": deployment_values.get("network"),
            "portgroup": deployment_values.get("portgroup"),
            "lab_network": deployment_values.get("subnet_cidr"),
            "management_ip_available": management_ip_available.get("available"),
        },
        "deployment_values": deployment_values,
        "value_checks": value_checks,
        "credential_state": credential_state,
        "checks": checks,
        "blockers": unique_preserving_order(blockers),
        "warnings": warnings,
        "not_attempted": [
            "VCSA deploy install",
            "vCenter appliance power operation",
            "ESXi datastore mount",
            "vCenter configuration write",
        ],
        "artifacts": {
            "readiness_report": _rel(VCENTER_INSTALL_READINESS_REPORT),
            "plan_report": _rel(VCENTER_INSTALL_PLAN_REPORT),
            "preview_report": _rel(VCENTER_INSTALL_PREVIEW_REPORT),
            "apply_report": _rel(VCENTER_INSTALL_APPLY_REPORT),
            "post_install_validation_report": _rel(VCENTER_POST_INSTALL_VALIDATION_REPORT),
            "final_report": _rel(VCENTER_INSTALL_APPLY_FINAL_REPORT),
            "readiness_json": _rel(VCENTER_INSTALL_READINESS_JSON),
        },
        "deploy_action_id": "vcenter.install-apply",
        "deploy_action_label": "Deploy vCenter",
        "recheck_command": "make provider-lab-vcenter-install-readiness",
        "next_safe_action": (
            "Run Preview Deploy, then run the guarded vCenter install apply target."
            if not blockers
            else "Resolve the current vCenter install blockers, then rerun vCenter install readiness."
        ),
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(VCENTER_INSTALL_READINESS_JSON, sanitized)
        write_text_value(VCENTER_INSTALL_READINESS_REPORT, _vcenter_install_markdown(sanitized))
    return sanitized


def get_vcenter_install_plan(*, write_report: bool = True) -> dict[str, Any]:
    readiness = get_vcenter_install_readiness(check_ports=True, write_report=write_report)
    plan = _vcenter_install_plan_payload(
        readiness,
        action="vcenter-install-plan",
        message="vCenter install plan generated. Preview only; no install was started.",
        report=VCENTER_INSTALL_PLAN_REPORT,
        json_report=VCENTER_INSTALL_PLAN_JSON,
        artifact_key="plan",
    )
    sanitized = redact_sensitive(plan)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(VCENTER_INSTALL_PLAN_JSON, sanitized)
        write_text_value(VCENTER_INSTALL_PLAN_REPORT, _vcenter_install_markdown(sanitized))
    return sanitized


def get_vcenter_install_preview(*, write_report: bool = True) -> dict[str, Any]:
    readiness = get_vcenter_install_readiness(check_ports=True, write_report=write_report)
    preview = _vcenter_install_plan_payload(
        readiness,
        action="vcenter-install-preview",
        message="vCenter deploy preview generated. No VCSA deployment was started.",
        report=VCENTER_INSTALL_PREVIEW_REPORT,
        json_report=VCENTER_INSTALL_PREVIEW_JSON,
        artifact_key="preview",
    )
    sanitized = redact_sensitive(preview)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        _write_json(VCENTER_INSTALL_PREVIEW_JSON, sanitized)
        write_text_value(VCENTER_INSTALL_PREVIEW_REPORT, _vcenter_install_markdown(sanitized))
    return sanitized


def get_vcenter_install_apply(*, write_report: bool = True) -> dict[str, Any]:
    generated_at = _now()
    readiness = get_vcenter_install_readiness(check_ports=True, write_report=write_report)
    plan = get_vcenter_install_plan(write_report=write_report)
    preview = get_vcenter_install_preview(write_report=write_report)
    readiness_ready = readiness.get("status") == "ready" and not readiness.get("blockers")
    preview_ready = preview.get("status") == "ready" and not preview.get("blockers")
    gate_state = _vcenter_install_apply_gate_state(
        readiness_ready=readiness_ready,
        preview_ready=preview_ready,
    )
    deployment_values = (
        readiness.get("deployment_values") if isinstance(readiness.get("deployment_values"), dict) else {}
    )
    spec = _vcenter_deployment_spec(deployment_values)
    spec_blockers = _vcenter_deployment_spec_blockers(spec)
    blockers = _unique(
        [
            *_coerce_string_list(readiness.get("blockers")),
            *([] if preview_ready else _coerce_string_list(preview.get("blockers"))),
            *gate_state["blockers"],
            *spec_blockers,
        ]
    )
    apply_result = {
        "vcsa_deploy_attempted": False,
        "return_code": None,
        "result": "not_attempted",
        "stdout_summary": "",
        "stderr_summary": "",
        "command": _vcsa_deploy_command_preview(readiness),
    }
    validation: dict[str, Any] | None = None
    refresh_result: dict[str, Any] | None = None

    if write_report and spec:
        _write_json(VCENTER_INSTALL_SPEC_REDACTED_JSON, _sanitize(spec))

    status = "blocked" if blockers else "ready_to_apply"
    message = (
        "vCenter install apply was refused before vcsa-deploy because required gates or readiness checks are incomplete."
        if blockers
        else "vCenter install apply gates passed; running vcsa-deploy against the local lab ESXi target."
    )
    if not blockers:
        deploy_path = (readiness.get("current_state") or {}).get("vcsa_deploy")
        apply_result = _run_vcsa_deploy(spec, deploy_path)
        if apply_result["return_code"] == 0:
            status = "completed"
            message = "vcsa-deploy completed. Running post-install vCenter validation."
            validation = validate_vcenter_post_install(wait_for_ready=True, write_report=write_report)
            refresh_result = _refresh_post_install_reports()
        else:
            status = "failed"
            message = "vcsa-deploy failed. Review the redacted apply report before rerunning."
            blockers.append("vcsa-deploy returned a non-zero exit code.")

    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-install-apply",
        "checked_at": generated_at,
        "generated_at": generated_at,
        "status": status,
        "message": message,
        "mode": settings.provider_mode,
        "apply_enabled": not blockers,
        "deploy_enabled": not blockers,
        "source_type": "live_provider",
        "freshness": "live",
        "current_state": readiness.get("current_state") or {},
        "target_state": readiness.get("target_state") or {},
        "deployment_values": deployment_values,
        "install_plan": preview.get("install_plan") or plan.get("install_plan") or {},
        "apply_gate_state": gate_state,
        "apply": apply_result,
        "post_install_validation": validation,
        "post_install_refresh": refresh_result,
        "blockers": _unique(blockers),
        "warnings": _vcenter_apply_warnings(validation=validation, refresh_result=refresh_result),
        "not_attempted": _vcenter_apply_not_attempted(apply_result),
        "artifacts": {
            "readiness_report": _rel(VCENTER_INSTALL_READINESS_REPORT),
            "plan_report": _rel(VCENTER_INSTALL_PLAN_REPORT),
            "preview_report": _rel(VCENTER_INSTALL_PREVIEW_REPORT),
            "apply_report": _rel(VCENTER_INSTALL_APPLY_REPORT),
            "post_install_validation_report": _rel(VCENTER_POST_INSTALL_VALIDATION_REPORT),
            "final_report": _rel(VCENTER_INSTALL_APPLY_FINAL_REPORT),
            "apply_json": _rel(VCENTER_INSTALL_APPLY_JSON),
            "redacted_spec_json": _rel(VCENTER_INSTALL_SPEC_REDACTED_JSON),
        },
        "next_safe_action": (
            "Review post-install validation, then refresh Golden State and Lab Validation."
            if status == "completed"
            else "Resolve the listed blocker, rerun readiness, plan, preview, then rerun vCenter install apply."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(VCENTER_INSTALL_APPLY_JSON, sanitized)
        write_text_value(VCENTER_INSTALL_APPLY_REPORT, _vcenter_apply_markdown(sanitized))
        write_text_value(VCENTER_INSTALL_APPLY_FINAL_REPORT, _vcenter_apply_final_markdown(sanitized))
    return sanitized


def validate_vcenter_post_install(
    *,
    wait_for_ready: bool = False,
    write_report: bool = True,
) -> dict[str, Any]:
    checked_at = _now()
    target = _vcenter_validation_target()
    host = target["host"]
    wait_seconds = _int_env("VCENTER_INSTALL_VALIDATE_WAIT_SECONDS", VCENTER_INSTALL_VALIDATE_WAIT_SECONDS)
    if wait_for_ready and host:
        _wait_for_tcp(host, 443, timeout_seconds=wait_seconds, poll_seconds=15)
    ping_ready = _ping(host) if host else False
    tcp_443 = _tcp_open(host, 443) if host else False
    api_probe = _vcenter_api_probe(host) if host and tcp_443 else _skipped_probe("vCenter HTTPS/API readiness was not reachable.")
    govc_about = _run_vcenter_govc(["about"], timeout=45) if target["govc_configured"] else _skipped_govc(target)
    govc_ready = govc_about.get("return_code") == 0
    esxi_visible = _vcenter_esxi_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    datastore_visible = _vcenter_datastore_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    blockers = []
    warnings = []
    if not host:
        blockers.append("VCENTER_HOST/GOVC_URL or VCENTER_MANAGEMENT_IP is required for post-install validation.")
    if host and not tcp_443:
        blockers.append("vCenter TCP/443 is not reachable after deployment.")
    if not target["govc_configured"]:
        blockers.append("vCenter govc credentials are not configured for post-install validation.")
    elif not govc_ready:
        blockers.append("govc authentication to vCenter failed.")
    if host and not ping_ready:
        warnings.append("ICMP ping did not reply; TCP/API checks are authoritative for this validation.")
    if govc_ready and not esxi_visible.get("visible"):
        warnings.append("ESXi is not visible in vCenter inventory yet; host add/attach is not implemented in this apply workflow.")
    if govc_ready and not datastore_visible.get("visible"):
        warnings.append("NetApp datastore is not visible through vCenter yet; validate again after ESXi inventory is attached.")
    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-post-install-validation",
        "checked_at": checked_at,
        "generated_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "message": "Post-install vCenter validation completed with ping, TCP/443, HTTPS/API, and govc checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_provider",
        "freshness": "live",
        "target": target,
        "checks": {
            "ping": {"status": "ready" if ping_ready else "warning", "host": host, "reply": ping_ready},
            "tcp_443": {"status": "ready" if tcp_443 else "blocked", "host": host, "port": 443},
            "api_readiness": api_probe,
            "govc_authentication": govc_about,
            "esxi_visible": esxi_visible,
            "netapp_datastore_visible": datastore_visible,
        },
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
        "not_attempted": _post_install_not_attempted(govc_ready),
        "artifacts": {
            "report": _rel(VCENTER_POST_INSTALL_VALIDATION_REPORT),
            "json": _rel(VCENTER_POST_INSTALL_VALIDATION_JSON),
        },
        "next_safe_action": (
            "Refresh Golden State and Lab Validation."
            if not blockers
            else "Fix the current validation blocker, then rerun post-install validation."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(VCENTER_POST_INSTALL_VALIDATION_JSON, sanitized)
        write_text_value(VCENTER_POST_INSTALL_VALIDATION_REPORT, _vcenter_post_install_markdown(sanitized))
    return sanitized


def get_vcenter_attach_esxi_preview(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    target = _vcenter_attach_target(include_thumbprint=True)
    govc_about = _run_vcenter_govc(["about"], timeout=45) if target["govc_configured"] else _skipped_govc(target)
    govc_ready = govc_about.get("return_code") == 0
    datacenter_visible = _vcenter_datacenter_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    cluster_visible = _vcenter_cluster_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    esxi_visible = _vcenter_esxi_visibility(target) if govc_ready and datacenter_visible.get("visible") else _skipped_probe(
        "Datacenter is not visible yet; attach apply will ensure it before host validation."
    )
    datastore_visible = _vcenter_datastore_visibility(target) if govc_ready and datacenter_visible.get("visible") else _skipped_probe(
        "Datacenter is not visible yet; attach apply will validate datastore visibility after host attach."
    )
    vm_inventory_visible = _vcenter_vm_inventory_visibility(target) if govc_ready and datacenter_visible.get("visible") else _skipped_probe(
        "Datacenter is not visible yet; VM inventory validation will run after host attach."
    )
    esxi_reachable = _tcp_check("ESXi management", target.get("esxi_target"), 443, check_ports=True)
    thumbprint_check = _vcenter_esxi_thumbprint_check(target)
    blockers = _vcenter_attach_preview_blockers(
        target=target,
        govc_about=govc_about,
        esxi_reachable=esxi_reachable,
    )
    warnings = [
        "Preview only. No vCenter datacenter, cluster, host attach, datastore, ESXi, or NetApp write action was run.",
    ]
    if thumbprint_check.get("status") != "ready":
        warnings.append("ESXi certificate thumbprint could not be read; guarded apply will use govc -noverify for this local lab attach.")
    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-attach-esxi-preview",
        "checked_at": checked_at,
        "generated_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "message": "vCenter ESXi attach preview generated. No vCenter inventory write was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "ready_for_apply": not blockers,
        "source_type": "live_provider",
        "freshness": "live",
        "target": target,
        "attach_plan": _vcenter_attach_plan(
            target=target,
            datacenter_visible=datacenter_visible,
            cluster_visible=cluster_visible,
            esxi_visible=esxi_visible,
            datastore_visible=datastore_visible,
            vm_inventory_visible=vm_inventory_visible,
        ),
        "apply_gate_state": _vcenter_attach_apply_gate_state(preview_ready=not blockers),
        "checks": {
            "govc_authentication": govc_about,
            "esxi_management_reachable": esxi_reachable,
            "esxi_certificate_thumbprint": thumbprint_check,
            "datacenter_visible": datacenter_visible,
            "cluster_visible": cluster_visible,
            "esxi_visible": esxi_visible,
            "netapp_datastore_visible": datastore_visible,
            "vm_inventory_visible": vm_inventory_visible,
        },
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
        "not_attempted": [
            "vCenter datacenter create",
            "vCenter cluster create",
            "vCenter ESXi host add",
            "vCenter datastore mount/create",
            "ESXi host reconfiguration outside vCenter attach",
            "NetApp ONTAP write",
        ],
        "artifacts": {
            "preview_report": _rel(VCENTER_ATTACH_ESXI_PREVIEW_REPORT),
            "preview_json": _rel(VCENTER_ATTACH_ESXI_PREVIEW_JSON),
            "apply_report": _rel(VCENTER_ATTACH_ESXI_APPLY_REPORT),
            "post_attach_validation_report": _rel(VCENTER_POST_ATTACH_VALIDATION_REPORT),
            "final_report": _rel(VCENTER_ATTACH_ESXI_FINAL_REPORT),
        },
        "recheck_command": "make provider-lab-vcenter-attach-esxi-preview",
        "next_safe_action": (
            "Run the guarded vCenter ESXi attach apply target with explicit confirmation gates."
            if not blockers
            else "Resolve the current attach preview blockers, then rerun preview."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(VCENTER_ATTACH_ESXI_PREVIEW_JSON, sanitized)
        write_text_value(VCENTER_ATTACH_ESXI_PREVIEW_REPORT, _vcenter_attach_preview_markdown(sanitized))
    return sanitized


def get_vcenter_attach_esxi_apply(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    preview = get_vcenter_attach_esxi_preview(write_report=write_report)
    target = _vcenter_attach_target(include_thumbprint=True)
    preview_ready = preview.get("status") == "ready" and not preview.get("blockers")
    gate_state = _vcenter_attach_apply_gate_state(preview_ready=preview_ready)
    blockers = _unique([*_coerce_string_list(preview.get("blockers")), *gate_state["blockers"]])
    operations: list[dict[str, Any]] = []
    validation: dict[str, Any] | None = None
    status = "blocked" if blockers else "ready_to_apply"
    message = (
        "vCenter ESXi attach apply was refused because required gates or readiness checks are incomplete."
        if blockers
        else "vCenter ESXi attach apply gates passed; running idempotent datacenter, cluster, and host attach steps."
    )

    if not blockers:
        for operation in (
            _ensure_vcenter_datacenter,
            _ensure_vcenter_cluster,
            _attach_esxi_host_to_vcenter,
        ):
            result = operation(target)
            operations.append(result)
            if result.get("status") != "ready":
                blockers.append(str(result.get("detail") or f"{result.get('operation')} failed."))
                break
        validation = validate_vcenter_post_attach(write_report=write_report)
        if blockers:
            status = "failed"
            message = "vCenter ESXi attach failed before all idempotent steps completed."
        elif validation.get("status") == "ready":
            status = "completed"
            message = "vCenter ESXi attach completed and post-attach validation passed."
            _refresh_post_install_reports()
        else:
            status = "failed"
            message = "vCenter ESXi attach ran, but post-attach validation is not ready."
            blockers.extend(_coerce_string_list(validation.get("blockers")))

    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-attach-esxi-apply",
        "checked_at": checked_at,
        "generated_at": checked_at,
        "status": status,
        "message": message,
        "mode": settings.provider_mode,
        "apply_enabled": not blockers,
        "source_type": "live_provider",
        "freshness": "live",
        "target": target,
        "attach_plan": preview.get("attach_plan") or {},
        "apply_gate_state": gate_state,
        "operations": operations,
        "post_attach_validation": validation,
        "blockers": _unique(blockers),
        "warnings": _vcenter_attach_apply_warnings(operations=operations, validation=validation),
        "not_attempted": _vcenter_attach_not_attempted(status=status, operations=operations),
        "artifacts": {
            "preview_report": _rel(VCENTER_ATTACH_ESXI_PREVIEW_REPORT),
            "apply_report": _rel(VCENTER_ATTACH_ESXI_APPLY_REPORT),
            "post_attach_validation_report": _rel(VCENTER_POST_ATTACH_VALIDATION_REPORT),
            "final_report": _rel(VCENTER_ATTACH_ESXI_FINAL_REPORT),
            "apply_json": _rel(VCENTER_ATTACH_ESXI_APPLY_JSON),
        },
        "next_safe_action": (
            "Refresh Golden State and Lab Validation."
            if status == "completed"
            else "Resolve the listed blocker, rerun preview, then rerun guarded vCenter ESXi attach apply."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(VCENTER_ATTACH_ESXI_APPLY_JSON, sanitized)
        write_text_value(VCENTER_ATTACH_ESXI_APPLY_REPORT, _vcenter_attach_apply_markdown(sanitized))
        write_text_value(VCENTER_ATTACH_ESXI_FINAL_REPORT, _vcenter_attach_final_markdown(sanitized))
    return sanitized


def validate_vcenter_post_attach(*, write_report: bool = True) -> dict[str, Any]:
    checked_at = _now()
    target = _vcenter_attach_target(include_thumbprint=False)
    govc_about = _run_vcenter_govc(["about"], timeout=45) if target["govc_configured"] else _skipped_govc(target)
    govc_ready = govc_about.get("return_code") == 0
    datacenter_visible = _vcenter_datacenter_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    cluster_visible = _vcenter_cluster_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    esxi_visible = _vcenter_esxi_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    datastore_visible = _vcenter_datastore_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    vm_inventory_visible = _vcenter_vm_inventory_visibility(target) if govc_ready else _skipped_probe("govc authentication did not pass.")
    blockers = []
    if not target["govc_configured"]:
        blockers.append("vCenter govc credentials are not configured for post-attach validation.")
    elif not govc_ready:
        blockers.append("govc authentication to vCenter failed.")
    if govc_ready and not datacenter_visible.get("visible"):
        blockers.append(f"vCenter datacenter {target.get('datacenter')} is not visible.")
    if govc_ready and target.get("cluster") and not cluster_visible.get("visible"):
        blockers.append(f"vCenter cluster {target.get('cluster')} is not visible.")
    if govc_ready and not esxi_visible.get("visible"):
        blockers.append(f"ESXi host {target.get('esxi_target')} is not visible in vCenter.")
    if govc_ready and not datastore_visible.get("visible"):
        blockers.append(f"Datastore {target.get('datastore')} is not visible in vCenter.")
    if govc_ready and not vm_inventory_visible.get("visible"):
        blockers.append("No VM inventory is visible through vCenter after host attach.")
    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-post-attach-validation",
        "checked_at": checked_at,
        "generated_at": checked_at,
        "status": "blocked" if blockers else "ready",
        "message": "Post-attach vCenter validation completed with govc datacenter, cluster, host, datastore, and VM inventory checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_provider",
        "freshness": "live",
        "target": target,
        "checks": {
            "govc_authentication": govc_about,
            "datacenter_visible": datacenter_visible,
            "cluster_visible": cluster_visible,
            "esxi_visible": esxi_visible,
            "netapp_datastore_visible": datastore_visible,
            "vm_inventory_visible": vm_inventory_visible,
        },
        "blockers": _unique(blockers),
        "warnings": [],
        "not_attempted": [
            "vCenter datacenter create",
            "vCenter cluster create",
            "vCenter ESXi host add",
            "vCenter datastore mount/create",
            "ESXi host reconfiguration",
            "NetApp ONTAP write",
        ],
        "artifacts": {
            "report": _rel(VCENTER_POST_ATTACH_VALIDATION_REPORT),
            "json": _rel(VCENTER_POST_ATTACH_VALIDATION_JSON),
        },
        "recheck_command": "make provider-lab-vcenter-post-attach-validation",
        "next_safe_action": (
            "Refresh Golden State and Lab Validation."
            if not blockers
            else "Fix the current post-attach validation blocker, then rerun post-attach validation."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_json(VCENTER_POST_ATTACH_VALIDATION_JSON, sanitized)
        write_text_value(VCENTER_POST_ATTACH_VALIDATION_REPORT, _vcenter_post_attach_markdown(sanitized))
    return sanitized


def _vcenter_install_plan_payload(
    readiness: dict[str, Any],
    *,
    action: str,
    message: str,
    report: Path,
    json_report: Path,
    artifact_key: str,
) -> dict[str, Any]:
    deployment_values = readiness.get("deployment_values") if isinstance(readiness.get("deployment_values"), dict) else {}
    apply_gate_state = (
        readiness.get("apply_gate_state") if isinstance(readiness.get("apply_gate_state"), dict) else {}
    )
    deploy_apply_enabled = bool(readiness.get("apply_enabled")) and not apply_gate_state.get("blockers")
    return {
        **readiness,
        "action": action,
        "message": message,
        "install_plan": {
            "vcsa_iso": deployment_values.get("vcsa_iso_path") or (readiness.get("current_state") or {}).get("vcsa_iso"),
            "appliance_name": deployment_values.get("appliance_name"),
            "management_ip": deployment_values.get("management_ip"),
            "sso_domain": deployment_values.get("sso_domain"),
            "sso_admin_username_status": deployment_values.get("sso_admin_username_status"),
            "deployment_size": deployment_values.get("deployment_size"),
            "network": deployment_values.get("network"),
            "portgroup": deployment_values.get("portgroup"),
            "deployment_target": (readiness.get("target_state") or {}).get("deployment_target"),
            "datastore": (readiness.get("target_state") or {}).get("datastore"),
            "vcsa_deploy": (readiness.get("current_state") or {}).get("vcsa_deploy"),
            "command_preview": [
                "Mount VCSA ISO locally.",
                "Generate redacted VCSA deployment JSON from active lab profile and local-only credential status.",
                (
                    f"{(readiness.get('current_state') or {}).get('vcsa_deploy') or 'vcsa-deploy'} "
                    "install --accept-eula --acknowledge-ceip <redacted-vcsa-plan.json>"
                ),
            ],
            "deploy_confirmations_present": not bool(apply_gate_state.get("blockers")),
            "deploy_apply_enabled": deploy_apply_enabled,
            "apply_disabled_reason": readiness.get("apply_disabled_reason"),
        },
        "apply_enabled": deploy_apply_enabled,
        "deploy_enabled": deploy_apply_enabled,
        "ready_for_deploy": deploy_apply_enabled,
        "artifacts": {
            **(readiness.get("artifacts") or {}),
            f"{artifact_key}_report": _rel(report),
            f"{artifact_key}_json": _rel(json_report),
        },
    }


def _vcenter_deployment_values(
    *,
    plan: dict[str, Any],
    active_profile: dict[str, Any],
    vcsa_iso: Path | None,
) -> dict[str, Any]:
    global_settings = active_profile.get("global_settings") if isinstance(active_profile.get("global_settings"), dict) else {}
    vcsa_iso_path = _safe_media_path(vcsa_iso) or _safe_media_path(_configured_vcsa_iso_path())
    sso_admin_username = settings.vcenter_sso_admin_username
    return {
        "appliance_name": settings.vcenter_appliance_name,
        "management_ip": settings.vcenter_management_ip,
        "subnet_cidr": settings.vcenter_subnet_cidr or _clean_value(plan.get("subnet")) or settings.lab_subnet_cidr,
        "gateway": settings.vcenter_gateway or _clean_value(global_settings.get("gateway")) or _clean_value(active_profile.get("gateway")),
        "dns_servers": _first_non_empty_list(settings.vcenter_dns_servers, global_settings.get("dns_servers"), active_profile.get("dns")),
        "ntp_servers": _first_non_empty_list(settings.vcenter_ntp_servers, global_settings.get("ntp_servers"), active_profile.get("ntp")),
        "time_sync_mode": _vcenter_time_sync_mode(),
        "sso_domain": settings.vcenter_sso_domain,
        "sso_admin_username": sso_admin_username,
        "sso_admin_username_status": "configured" if bool(sso_admin_username) else "missing",
        "esxi_target": settings.vcenter_esxi_target
        or settings.esxi_test_host
        or _clean_value(plan.get("esxi_management"))
        or LAB_ESXI_MANAGEMENT_IP,
        "datastore_target": settings.vcenter_datastore_target or settings.netapp_nfs_datastore_name or "netapp_nfs_ds01",
        "vcsa_iso_path": vcsa_iso_path,
        "deployment_size": settings.vcenter_deployment_size,
        "network": settings.vcenter_network or settings.vcenter_portgroup,
        "portgroup": settings.vcenter_portgroup or settings.vcenter_network,
        "post_install_vcenter_configured": bool(
            settings.vcenter_host or settings.vcenter_management_ip or settings.vcenter_configured
        ),
        "post_install_vcenter": _redacted_url(settings.vcenter_host),
    }


def _vcenter_deployment_value_checks(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "appliance_name": _value_check("vCenter appliance name", "VCENTER_APPLIANCE_NAME", values.get("appliance_name")),
        "management_ip": _value_check("vCenter management IP", "VCENTER_MANAGEMENT_IP", values.get("management_ip")),
        "subnet_cidr": _value_check("Subnet", "VCENTER_SUBNET_CIDR or active lab subnet", values.get("subnet_cidr")),
        "gateway": _value_check("Gateway", "VCENTER_GATEWAY or active lab gateway", values.get("gateway")),
        "dns_servers": _value_check("DNS servers", "VCENTER_DNS_SERVERS or active lab DNS", values.get("dns_servers")),
        "time_sync": _value_check(
            "Time synchronization",
            "VCENTER_TIME_SYNC_MODE=tools or VCENTER_NTP_SERVERS/active lab NTP",
            values.get("time_sync_mode") == "tools" or values.get("ntp_servers"),
        ),
        "sso_domain": _value_check("SSO domain", "VCENTER_SSO_DOMAIN", values.get("sso_domain")),
        "sso_admin_username": _value_check(
            "SSO admin username",
            "VCENTER_SSO_ADMIN_USERNAME",
            values.get("sso_admin_username"),
        ),
        "esxi_target": _value_check("ESXi target", "VCENTER_ESXI_TARGET or ESXI_TEST_HOST", values.get("esxi_target")),
        "datastore_target": _value_check(
            "Datastore target",
            "VCENTER_DATASTORE_TARGET or NETAPP_NFS_DATASTORE_NAME",
            values.get("datastore_target"),
        ),
        "vcsa_iso_path": _value_check("VCSA ISO path", "VCENTER_VCSA_ISO_PATH or VCSA_ISO_PATH", values.get("vcsa_iso_path")),
        "deployment_size": _value_check("Deployment size", "VCENTER_DEPLOYMENT_SIZE", values.get("deployment_size")),
        "network_portgroup": _value_check(
            "Network / portgroup",
            "VCENTER_NETWORK or VCENTER_PORTGROUP",
            values.get("network") or values.get("portgroup"),
        ),
    }


def _vcenter_deployment_credential_state() -> dict[str, Any]:
    sso_password_configured = bool(settings.vcenter_sso_admin_password)
    root_password_configured = bool(settings.vcenter_appliance_root_password)
    esxi_credentials_configured = bool(settings.esxi_test_username and settings.esxi_test_password)
    post_install_vcenter_credentials_configured = bool(settings.vcenter_username and settings.vcenter_password)
    missing_fields = []
    if not root_password_configured:
        missing_fields.append("VCENTER_APPLIANCE_ROOT_PASSWORD")
    if not sso_password_configured:
        missing_fields.append("VCENTER_SSO_ADMIN_PASSWORD")
    if not esxi_credentials_configured:
        missing_fields.append("ESXI_TEST_USERNAME/ESXI_TEST_PASSWORD")
    return {
        "sso_admin_username_configured": bool(settings.vcenter_sso_admin_username),
        "sso_admin_password_configured": sso_password_configured,
        "appliance_root_password_configured": root_password_configured,
        "esxi_credentials_configured": esxi_credentials_configured,
        "post_install_vcenter_credentials_configured": post_install_vcenter_credentials_configured,
        "deployment_credentials_configured": not missing_fields,
        "missing_fields": missing_fields,
        "source_type": "operator_config",
        "freshness": "live",
    }


def _vcenter_install_apply_gate_state(
    *,
    readiness_ready: bool,
    preview_ready: bool | None = None,
) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "readiness_ready": readiness_ready,
        "preview_ready": preview_ready,
        "install_apply": _env_flag("VCENTER_INSTALL_APPLY"),
        "install_confirm": os.getenv("VCENTER_INSTALL_CONFIRM") == VCENTER_INSTALL_CONFIRM_PHRASE,
        "install_allow_deploy": _env_flag("VCENTER_INSTALL_ALLOW_DEPLOY"),
    }
    blockers = unique_strings(policy.action_blockers(VCENTER_INSTALL_POLICY_ACTION_ID, ActionCategory.VM_DEPLOY))
    if not readiness_ready:
        blockers.append("vCenter install readiness must be ready before apply.")
    if preview_ready is False:
        blockers.append("vCenter install preview must be ready before apply.")
    if not flag_state["install_apply"]:
        blockers.append("VCENTER_INSTALL_APPLY=true is required.")
    if not flag_state["install_confirm"]:
        blockers.append(f'VCENTER_INSTALL_CONFIRM="{VCENTER_INSTALL_CONFIRM_PHRASE}" is required.')
    if not flag_state["install_allow_deploy"]:
        blockers.append("VCENTER_INSTALL_ALLOW_DEPLOY=true is required.")
    return {
        "required_flags": _vcenter_install_required_flags(),
        "flag_state": flag_state,
        "blockers": _unique(blockers),
    }


def _vcenter_install_required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "VCENTER_INSTALL_APPLY=true",
        f'VCENTER_INSTALL_CONFIRM="{VCENTER_INSTALL_CONFIRM_PHRASE}"',
        "VCENTER_INSTALL_ALLOW_DEPLOY=true",
    ]


def _vcenter_install_warnings(*, readiness_ready: bool, apply_gate_blockers: list[str]) -> list[str]:
    if not readiness_ready:
        return ["vCenter install is blocked by the current readiness findings."]
    if apply_gate_blockers:
        return ["Ready to preview; deploy remains gated by explicit local-lab apply confirmations."]
    return ["Ready to deploy through the guarded vCenter install apply lane."]


def _vcenter_deployment_spec(values: dict[str, Any]) -> dict[str, Any]:
    prefix = _prefix_from_cidr(values.get("subnet_cidr"))
    network_name = values.get("network") or values.get("portgroup")
    ntp_servers = ",".join(_coerce_string_list(values.get("ntp_servers")))
    os_spec: dict[str, Any] = {
        "password": settings.vcenter_appliance_root_password,
        "ssh_enable": False,
    }
    if values.get("time_sync_mode") == "ntp":
        os_spec["ntp_servers"] = ntp_servers
    else:
        os_spec["time_tools_sync"] = True
    esxi_spec = {
        "hostname": values.get("esxi_target"),
        "username": settings.esxi_test_username,
        "password": settings.esxi_test_password,
        "deployment_network": network_name,
        "datastore": values.get("datastore_target"),
    }
    if not _vcsa_deploy_verify_tls():
        thumbprint = _server_certificate_sha1_thumbprint(values.get("esxi_target"))
        esxi_spec["ssl_certificate_verification"] = (
            {"thumbprint": thumbprint} if thumbprint else {"verification_mode": "NONE"}
        )
    return {
        "__version": "2.13.0",
        "new_vcsa": {
            "esxi": esxi_spec,
            "appliance": {
                "thin_disk_mode": True,
                "deployment_option": values.get("deployment_size") or "tiny",
                "name": values.get("appliance_name"),
            },
            "network": {
                "ip_family": "ipv4",
                "mode": "static",
                "system_name": _vcenter_system_name(values),
                "ip": values.get("management_ip"),
                "prefix": prefix,
                "gateway": values.get("gateway"),
                "dns_servers": _coerce_string_list(values.get("dns_servers")),
            },
            "os": os_spec,
            "sso": {
                "password": settings.vcenter_sso_admin_password,
                "domain_name": values.get("sso_domain"),
            },
        },
        "ceip": {"settings": {"ceip_enabled": False}},
    }


def _vcenter_deployment_spec_blockers(spec: dict[str, Any]) -> list[str]:
    blockers = []
    vcsa = spec.get("new_vcsa") if isinstance(spec.get("new_vcsa"), dict) else {}
    required = {
        "new_vcsa.esxi.hostname": (vcsa.get("esxi") or {}).get("hostname"),
        "new_vcsa.esxi.username": (vcsa.get("esxi") or {}).get("username"),
        "new_vcsa.esxi.password": (vcsa.get("esxi") or {}).get("password"),
        "new_vcsa.esxi.deployment_network": (vcsa.get("esxi") or {}).get("deployment_network"),
        "new_vcsa.esxi.datastore": (vcsa.get("esxi") or {}).get("datastore"),
        "new_vcsa.appliance.name": (vcsa.get("appliance") or {}).get("name"),
        "new_vcsa.network.ip": (vcsa.get("network") or {}).get("ip"),
        "new_vcsa.network.prefix": (vcsa.get("network") or {}).get("prefix"),
        "new_vcsa.network.gateway": (vcsa.get("network") or {}).get("gateway"),
        "new_vcsa.network.dns_servers": (vcsa.get("network") or {}).get("dns_servers"),
        "new_vcsa.os.password": (vcsa.get("os") or {}).get("password"),
        "new_vcsa.sso.password": (vcsa.get("sso") or {}).get("password"),
        "new_vcsa.sso.domain_name": (vcsa.get("sso") or {}).get("domain_name"),
    }
    for key, value in required.items():
        if not value:
            blockers.append(f"Generated VCSA spec is missing {key}.")
    return blockers


def _vcenter_system_name(values: dict[str, Any]) -> str | None:
    host = _host_from_endpoint(settings.vcenter_host)
    return host or _clean_value(values.get("management_ip"))


def _prefix_from_cidr(value: Any) -> str | None:
    text = _clean_value(value)
    if not text:
        return None
    try:
        return str(ip_network(text, strict=False).prefixlen)
    except ValueError:
        if text.startswith("/") and text[1:].isdigit():
            return text[1:]
        if text.isdigit():
            return text
        return None


def _run_vcsa_deploy(spec: dict[str, Any], deploy_path_value: Any) -> dict[str, Any]:
    deploy_path = Path(str(deploy_path_value)).expanduser() if deploy_path_value else _find_vcsa_deploy()
    if not deploy_path or not path_exists(deploy_path):
        return {
            "vcsa_deploy_attempted": False,
            "return_code": 127,
            "result": "not_found",
            "stdout_summary": "",
            "stderr_summary": "vcsa-deploy executable was not found.",
            "command": _vcsa_deploy_command_preview({"current_state": {"vcsa_deploy": str(deploy_path_value or "vcsa-deploy")}}),
        }
    timeout = _int_env("VCENTER_INSTALL_DEPLOY_TIMEOUT_SECONDS", VCENTER_INSTALL_DEPLOY_TIMEOUT_SECONDS)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="vcsa-deploy-", suffix=".json", delete=False) as handle:
            temp_path = handle.name
            json.dump(spec, handle, indent=2)
            handle.write("\n")
        _chmod_private(temp_path)
        completed = subprocess.run(
            _vcsa_deploy_install_command(str(deploy_path), temp_path),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
        result = {
            "vcsa_deploy_attempted": True,
            "return_code": completed.returncode,
            "result": "completed" if completed.returncode == 0 else "failed",
            "stdout_summary": _tail(completed.stdout),
            "stderr_summary": _tail(completed.stderr),
            "command": _vcsa_deploy_command_preview({"current_state": {"vcsa_deploy": str(deploy_path)}}),
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "vcsa_deploy_attempted": True,
            "return_code": 124,
            "result": "timeout",
            "stdout_summary": _tail(_decode_bytes(exc.stdout)),
            "stderr_summary": "vcsa-deploy command timed out.",
            "command": _vcsa_deploy_command_preview({"current_state": {"vcsa_deploy": str(deploy_path)}}),
        }
    except OSError as exc:
        result = {
            "vcsa_deploy_attempted": True,
            "return_code": 127,
            "result": "failed_to_start",
            "stdout_summary": "",
            "stderr_summary": f"vcsa-deploy failed to start: {exc.__class__.__name__}.",
            "command": _vcsa_deploy_command_preview({"current_state": {"vcsa_deploy": str(deploy_path)}}),
        }
    finally:
        if temp_path:
            remove_file_best_effort(temp_path, scrub=True)
    return _sanitize(result)


def _vcenter_validation_target() -> dict[str, Any]:
    host = _host_from_endpoint(settings.vcenter_host) or settings.vcenter_management_ip
    username = _vcenter_validation_username()
    password = _vcenter_validation_password()
    verify_tls = _vcenter_validation_verify_tls()
    return {
        "host": host,
        "url": _vcenter_govc_url(host),
        "username_configured": bool(username),
        "credential_configured": bool(password),
        "govc_available": _tool_available("govc"),
        "govc_configured": bool(host and username and password and _tool_available("govc")),
        "esxi_target": settings.vcenter_esxi_target or settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP,
        "datastore": settings.vcenter_datastore_target or settings.netapp_nfs_datastore_name,
        "datacenter": _vcenter_datacenter_name(),
        "cluster": _vcenter_cluster_name(),
        "verify_tls": verify_tls,
    }


def _vcenter_attach_target(*, include_thumbprint: bool) -> dict[str, Any]:
    target = _vcenter_validation_target()
    esxi_username = _clean_value(settings.esxi_test_username)
    esxi_password = _clean_value(settings.esxi_test_password)
    thumbprint = _server_certificate_sha1_thumbprint(target.get("esxi_target")) if include_thumbprint else None
    return {
        **target,
        "esxi_username_configured": bool(esxi_username),
        "esxi_credential_configured": bool(esxi_password),
        "esxi_thumbprint_configured": bool(thumbprint),
        "esxi_thumbprint": thumbprint,
        "host_attach_tls_mode": "thumbprint" if thumbprint else "noverify",
    }


def _vcenter_datacenter_name() -> str:
    return _clean_value(getattr(settings, "vcenter_datacenter_name", None)) or "Lab-DC"


def _vcenter_cluster_name() -> str:
    return _clean_value(getattr(settings, "vcenter_cluster_name", None)) or "Lab-Cluster"


def _run_vcenter_govc(args: list[str], *, timeout: int) -> dict[str, Any]:
    govc = _tool_path("govc")
    if govc is None:
        return {"status": "blocked", "return_code": 127, "stdout": "", "stderr": "govc executable was not found."}
    env = os.environ.copy()
    target = _vcenter_validation_target()
    env["GOVC_URL"] = target["url"] or ""
    env["GOVC_USERNAME"] = _vcenter_validation_username() or ""
    env["GOVC_PASSWORD"] = _vcenter_validation_password() or ""
    env["GOVC_INSECURE"] = "false" if target["verify_tls"] else "true"
    try:
        completed = subprocess.run(
            [str(govc), *args],
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"status": "blocked", "return_code": 124, "stdout": "", "stderr": "govc command timed out."}
    except OSError as exc:
        return {"status": "blocked", "return_code": 127, "stdout": "", "stderr": f"govc failed to start: {exc.__class__.__name__}."}
    return _sanitize(
        {
            "status": "ready" if completed.returncode == 0 else "blocked",
            "return_code": completed.returncode,
            "stdout": _tail(completed.stdout),
            "stderr": _tail(completed.stderr),
        }
    )


def _vcenter_attach_preview_blockers(
    *,
    target: dict[str, Any],
    govc_about: dict[str, Any],
    esxi_reachable: dict[str, Any],
) -> list[str]:
    blockers = []
    if not target.get("host"):
        blockers.append("VCENTER_HOST/GOVC_URL or VCENTER_MANAGEMENT_IP is required for ESXi attach.")
    if not target.get("username_configured") or not target.get("credential_configured"):
        blockers.append("vCenter govc credentials are required for ESXi attach.")
    if not target.get("govc_available"):
        blockers.append("govc is required for ESXi attach.")
    elif target.get("govc_configured") and govc_about.get("return_code") != 0:
        blockers.append("govc authentication to vCenter must pass before ESXi attach.")
    if esxi_reachable.get("status") != "ready":
        blockers.append("ESXi management TCP/443 must be reachable before vCenter host attach.")
    if not target.get("esxi_username_configured") or not target.get("esxi_credential_configured"):
        blockers.append("ESXi local credentials are required for govc host attach.")
    if not target.get("datacenter"):
        blockers.append("VCENTER_DATACENTER_NAME is required.")
    if not target.get("cluster"):
        blockers.append("VCENTER_CLUSTER_NAME is required.")
    if not target.get("datastore"):
        blockers.append("VCENTER_DATASTORE_TARGET or NETAPP_NFS_DATASTORE_NAME is required.")
    return blockers


def _vcenter_attach_apply_gate_state(*, preview_ready: bool) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "preview_ready": preview_ready,
        "attach_apply": _env_flag("VCENTER_ATTACH_ESXI_APPLY"),
        "attach_confirm": os.getenv("VCENTER_ATTACH_ESXI_CONFIRM") == VCENTER_ATTACH_ESXI_CONFIRM_PHRASE,
        "attach_allow": _env_flag("VCENTER_ATTACH_ESXI_ALLOW"),
    }
    blockers = unique_strings(policy.action_blockers(VCENTER_ATTACH_ESXI_POLICY_ACTION_ID, ActionCategory.VM_DEPLOY))
    if not preview_ready:
        blockers.append("vCenter ESXi attach preview must be ready before apply.")
    if not flag_state["attach_apply"]:
        blockers.append("VCENTER_ATTACH_ESXI_APPLY=true is required.")
    if not flag_state["attach_confirm"]:
        blockers.append(f'VCENTER_ATTACH_ESXI_CONFIRM="{VCENTER_ATTACH_ESXI_CONFIRM_PHRASE}" is required.')
    if not flag_state["attach_allow"]:
        blockers.append("VCENTER_ATTACH_ESXI_ALLOW=true is required.")
    return {
        "required_flags": _vcenter_attach_required_flags(),
        "flag_state": flag_state,
        "blockers": _unique(blockers),
    }


def _vcenter_attach_required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "VCENTER_ATTACH_ESXI_APPLY=true",
        f'VCENTER_ATTACH_ESXI_CONFIRM="{VCENTER_ATTACH_ESXI_CONFIRM_PHRASE}"',
        "VCENTER_ATTACH_ESXI_ALLOW=true",
    ]


def _vcenter_attach_plan(
    *,
    target: dict[str, Any],
    datacenter_visible: dict[str, Any],
    cluster_visible: dict[str, Any],
    esxi_visible: dict[str, Any],
    datastore_visible: dict[str, Any],
    vm_inventory_visible: dict[str, Any],
) -> dict[str, Any]:
    return {
        "datacenter": target.get("datacenter"),
        "cluster": target.get("cluster"),
        "esxi_target": target.get("esxi_target"),
        "datastore": target.get("datastore"),
        "steps": [
            {
                "operation": "datacenter.ensure",
                "status": "already_visible" if datacenter_visible.get("visible") else "will_create",
                "command_preview": f"govc datacenter.create {target.get('datacenter')}",
            },
            {
                "operation": "cluster.ensure",
                "status": "already_visible" if cluster_visible.get("visible") else "will_create",
                "command_preview": f"govc cluster.create -dc {target.get('datacenter')} {target.get('cluster')}",
            },
            {
                "operation": "esxi.attach",
                "status": "already_visible" if esxi_visible.get("visible") else "will_attach",
                "command_preview": _vcenter_attach_host_command_preview(target),
                "tls_mode": target.get("host_attach_tls_mode"),
            },
            {
                "operation": "post_attach.validate",
                "status": "ready" if datastore_visible.get("visible") and vm_inventory_visible.get("visible") else "will_validate",
                "command_preview": "make provider-lab-vcenter-post-attach-validation",
            },
        ],
    }


def _ensure_vcenter_datacenter(target: dict[str, Any]) -> dict[str, Any]:
    existing = _vcenter_datacenter_visibility(target)
    if existing.get("visible"):
        return _vcenter_operation_result(
            "datacenter.ensure",
            command_preview=f"govc datacenter.create {target.get('datacenter')}",
            attempted=False,
            changed=False,
            result=existing,
            detail=f"Datacenter {target.get('datacenter')} already exists.",
        )
    result = _run_vcenter_govc(["datacenter.create", str(target.get("datacenter"))], timeout=120)
    return _vcenter_operation_result(
        "datacenter.ensure",
        command_preview=f"govc datacenter.create {target.get('datacenter')}",
        attempted=True,
        changed=result.get("return_code") == 0,
        result=result,
        detail=(
            f"Datacenter {target.get('datacenter')} created."
            if result.get("return_code") == 0
            else f"Datacenter {target.get('datacenter')} could not be created."
        ),
    )


def _ensure_vcenter_cluster(target: dict[str, Any]) -> dict[str, Any]:
    existing = _vcenter_cluster_visibility(target)
    if existing.get("visible"):
        return _vcenter_operation_result(
            "cluster.ensure",
            command_preview=f"govc cluster.create -dc {target.get('datacenter')} {target.get('cluster')}",
            attempted=False,
            changed=False,
            result=existing,
            detail=f"Cluster {target.get('cluster')} already exists.",
        )
    result = _run_vcenter_govc(
        ["cluster.create", "-dc", str(target.get("datacenter")), str(target.get("cluster"))],
        timeout=120,
    )
    return _vcenter_operation_result(
        "cluster.ensure",
        command_preview=f"govc cluster.create -dc {target.get('datacenter')} {target.get('cluster')}",
        attempted=True,
        changed=result.get("return_code") == 0,
        result=result,
        detail=(
            f"Cluster {target.get('cluster')} created."
            if result.get("return_code") == 0
            else f"Cluster {target.get('cluster')} could not be created."
        ),
    )


def _attach_esxi_host_to_vcenter(target: dict[str, Any]) -> dict[str, Any]:
    existing = _vcenter_esxi_visibility(target)
    if existing.get("visible"):
        return _vcenter_operation_result(
            "esxi.attach",
            command_preview=_vcenter_attach_host_command_preview(target),
            attempted=False,
            changed=False,
            result=existing,
            detail=f"ESXi host {target.get('esxi_target')} is already visible in vCenter.",
        )
    command = [
        "cluster.add",
        "-dc",
        str(target.get("datacenter")),
        "-cluster",
        str(target.get("cluster")),
        "-hostname",
        str(target.get("esxi_target")),
        "-username",
        str(settings.esxi_test_username),
        "-password",
        str(settings.esxi_test_password),
    ]
    if target.get("esxi_thumbprint"):
        command.extend(["-thumbprint", str(target.get("esxi_thumbprint"))])
    else:
        command.append("-noverify")
    result = _run_vcenter_govc(command, timeout=VCENTER_ATTACH_ESXI_TIMEOUT_SECONDS)
    return _vcenter_operation_result(
        "esxi.attach",
        command_preview=_vcenter_attach_host_command_preview(target),
        attempted=True,
        changed=result.get("return_code") == 0,
        result=result,
        detail=(
            f"ESXi host {target.get('esxi_target')} attached to vCenter."
            if result.get("return_code") == 0
            else f"ESXi host {target.get('esxi_target')} could not be attached to vCenter."
        ),
    )


def _vcenter_operation_result(
    operation: str,
    *,
    command_preview: str,
    attempted: bool,
    changed: bool,
    result: dict[str, Any],
    detail: str,
) -> dict[str, Any]:
    return _sanitize(
        {
            "operation": operation,
            "status": "ready" if result.get("return_code") in {0, None} and result.get("status") != "blocked" else "blocked",
            "attempted": attempted,
            "changed": changed,
            "detail": detail,
            "command_preview": command_preview,
            "return_code": result.get("return_code"),
            "stdout_summary": result.get("stdout") or "",
            "stderr_summary": result.get("stderr") or "",
        }
    )


def _vcenter_attach_host_command_preview(target: dict[str, Any]) -> str:
    tls_flag = (
        f"-thumbprint {target.get('esxi_thumbprint')}"
        if target.get("esxi_thumbprint")
        else "-noverify"
    )
    return (
        "govc cluster.add "
        f"-dc {target.get('datacenter')} "
        f"-cluster {target.get('cluster')} "
        f"-hostname {target.get('esxi_target')} "
        "-username <configured> -password <redacted> "
        f"{tls_flag}"
    )


def _vcenter_datacenter_visibility(target: dict[str, Any]) -> dict[str, Any]:
    datacenter = str(target.get("datacenter") or "")
    if not datacenter:
        return _skipped_probe("vCenter datacenter target is not configured.")
    result = _run_vcenter_govc(["find", "/", "-type", "d", "-name", datacenter], timeout=45)
    paths = _stdout_lines(result.get("stdout"))
    visible = result.get("return_code") == 0 and _path_list_contains(paths, datacenter)
    return _visibility_result(result, visible=visible, name=datacenter, paths=paths, missing_status="not_found")


def _vcenter_cluster_visibility(target: dict[str, Any]) -> dict[str, Any]:
    cluster = str(target.get("cluster") or "")
    datacenter = str(target.get("datacenter") or "")
    if not cluster:
        return _skipped_probe("vCenter cluster target is not configured.")
    if not datacenter:
        return _skipped_probe("vCenter datacenter target is not configured.")
    result = _run_vcenter_govc(["find", f"/{datacenter}/host", "-type", "c", "-name", cluster], timeout=45)
    paths = _stdout_lines(result.get("stdout"))
    visible = result.get("return_code") == 0 and _path_list_contains(paths, cluster)
    return _visibility_result(result, visible=visible, name=cluster, paths=paths, missing_status="not_found")


def _vcenter_esxi_visibility(target: dict[str, Any]) -> dict[str, Any]:
    datacenter = str(target.get("datacenter") or "")
    esxi_target = str(target.get("esxi_target") or "")
    if not datacenter:
        return _skipped_probe("vCenter datacenter target is not configured.")
    if not esxi_target:
        return _skipped_probe("ESXi target is not configured.")
    result = _run_vcenter_govc(["find", f"/{datacenter}", "-type", "h"], timeout=45)
    paths = _stdout_lines(result.get("stdout"))
    visible = result.get("return_code") == 0 and _path_list_contains(paths, esxi_target)
    return _visibility_result(result, visible=visible, name=esxi_target, paths=paths, missing_status="not_found")


def _vcenter_datastore_visibility(target: dict[str, Any]) -> dict[str, Any]:
    datacenter = str(target.get("datacenter") or "")
    datastore = str(target.get("datastore") or "")
    if not datacenter:
        return _skipped_probe("vCenter datacenter target is not configured.")
    if not datastore:
        return _skipped_probe("Datastore target is not configured.")
    result = _run_vcenter_govc(["find", f"/{datacenter}", "-type", "s", "-name", datastore], timeout=45)
    paths = _stdout_lines(result.get("stdout"))
    visible = result.get("return_code") == 0 and _path_list_contains(paths, datastore)
    return _visibility_result(result, visible=visible, name=datastore, paths=paths, missing_status="not_found")


def _vcenter_vm_inventory_visibility(target: dict[str, Any]) -> dict[str, Any]:
    datacenter = str(target.get("datacenter") or "")
    if not datacenter:
        return _skipped_probe("vCenter datacenter target is not configured.")
    result = _run_vcenter_govc(["find", f"/{datacenter}/vm", "-type", "m"], timeout=45)
    paths = _stdout_lines(result.get("stdout"))
    visible = result.get("return_code") == 0 and bool(paths)
    payload = _visibility_result(result, visible=visible, name="vm inventory", paths=paths, missing_status="not_found")
    payload["count"] = len(paths)
    return payload


def _vcenter_esxi_thumbprint_check(target: dict[str, Any]) -> dict[str, Any]:
    thumbprint = target.get("esxi_thumbprint")
    if thumbprint:
        return {
            "status": "ready",
            "configured": True,
            "detail": "ESXi certificate SHA-1 thumbprint was read for govc host attach.",
            "thumbprint": thumbprint,
            "source_type": "live_provider",
            "freshness": "live",
        }
    return {
        "status": "warning",
        "configured": False,
        "detail": "ESXi certificate SHA-1 thumbprint could not be read; local-lab attach can fall back to govc -noverify.",
        "thumbprint": None,
        "source_type": "live_provider",
        "freshness": "live",
    }


def _visibility_result(
    result: dict[str, Any],
    *,
    visible: bool,
    name: str,
    paths: list[str],
    missing_status: str,
) -> dict[str, Any]:
    status = "ready" if visible else missing_status if result.get("return_code") == 0 else "blocked"
    return {
        **result,
        "status": status,
        "visible": bool(visible),
        "name": name,
        "paths": paths,
    }


def _vcenter_api_probe(host: str) -> dict[str, Any]:
    url = f"https://{host}/ui/"
    context = None if _vcenter_validation_verify_tls() else ssl._create_unverified_context()
    request = Request(url, method="GET", headers={"User-Agent": "infra-config-portal-vcenter-validation"})
    try:
        with urlopen(request, timeout=10, context=context) as response:
            status_code = int(response.status)
    except HTTPError as exc:
        status_code = int(exc.code)
    except (OSError, URLError, ValueError) as exc:
        return {
            "status": "blocked",
            "url": _redacted_url(url),
            "reachable": False,
            "status_code": None,
            "detail": f"HTTPS probe failed with {exc.__class__.__name__}.",
        }
    return {
        "status": "ready" if 200 <= status_code < 500 else "blocked",
        "url": _redacted_url(url),
        "reachable": 200 <= status_code < 500,
        "status_code": status_code,
        "detail": "vCenter HTTPS endpoint responded.",
    }


def _skipped_probe(reason: str) -> dict[str, Any]:
    return {"status": "not_checked", "checked": False, "visible": False, "detail": reason}


def _skipped_govc(target: dict[str, Any]) -> dict[str, Any]:
    missing = []
    if not target.get("host"):
        missing.append("VCENTER_HOST/GOVC_URL or VCENTER_MANAGEMENT_IP")
    if not target.get("username_configured"):
        missing.append("VCENTER_USERNAME/GOVC_USERNAME or VCENTER_SSO_ADMIN_USERNAME")
    if not target.get("credential_configured"):
        missing.append("VCENTER_PASSWORD/GOVC_PASSWORD or VCENTER_SSO_ADMIN_PASSWORD")
    if not target.get("govc_available"):
        missing.append("govc")
    return {
        "status": "not_configured",
        "return_code": None,
        "stdout": "",
        "stderr": "",
        "missing_fields": missing,
    }


def _refresh_post_install_reports() -> dict[str, Any]:
    refreshed: dict[str, Any] = {}
    errors: list[str] = []
    try:
        from app.services.golden_state import get_provider_lab_golden_state

        golden = get_provider_lab_golden_state(write_report=True)
        refreshed["golden_state_status"] = golden.get("status")
        refreshed["golden_state_report"] = (golden.get("artifacts") or {}).get("report")
    except Exception as exc:
        errors.append(f"Golden State refresh failed: {exc.__class__.__name__}.")
    try:
        from app.services.lab_validation import get_lab_validation_summary

        validation = get_lab_validation_summary(write_report=True)
        refreshed["lab_validation_status"] = validation.get("overall_status") or validation.get("status")
        refreshed["lab_validation_report"] = validation.get("handoff_report")
    except Exception as exc:
        errors.append(f"Lab Validation refresh failed: {exc.__class__.__name__}.")
    return {"refreshed": refreshed, "errors": errors}


def _value_check(label: str, field: str, value: Any) -> dict[str, Any]:
    configured = bool(value) if not isinstance(value, (list, tuple)) else bool(list(value))
    return {
        "label": label,
        "field": field,
        "status": "ready" if configured else "not_configured",
        "detail": f"{label} is configured." if configured else f"{label} is missing.",
        "source_type": "operator_config",
        "freshness": "live",
    }


def _missing_value_labels(value_checks: dict[str, dict[str, Any]]) -> list[str]:
    return [
        str(check.get("field") or check.get("label") or key)
        for key, check in value_checks.items()
        if check.get("status") != "ready"
    ]


def _datastore_ready_check(datastore_name: str | None) -> dict[str, Any]:
    path = REPO_ROOT / "artifacts" / "codex-runs" / "esxi-netapp-nfs-datastore-validation-redacted.json"
    payload = _read_json_artifact(path)
    if not payload:
        return {
            "label": "NetApp datastore",
            "datastore": datastore_name,
            "status": "not_checked",
            "detail": "No NetApp datastore validation artifact was found.",
            "source_type": "not_checked",
            "freshness": "not_checked",
            "checked_at": None,
            "recheck_command": "make provider-lab-esxi-netapp-datastore-validate",
        }
    current = payload.get("current_state") if isinstance(payload.get("current_state"), dict) else {}
    summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    artifact_datastore = str(summary.get("name") or "")
    access_mode = str(summary.get("access_mode") or "")
    ready = (
        payload.get("status") == "ready"
        and current.get("exists") is True
        and current.get("accessible") is True
        and access_mode == "readWrite"
        and (not datastore_name or artifact_datastore == datastore_name)
    )
    return {
        "label": "NetApp datastore",
        "datastore": artifact_datastore or datastore_name,
        "status": "ready" if ready else "blocked",
        "detail": (
            f"{artifact_datastore or datastore_name} is mounted read/write."
            if ready
            else "NetApp datastore validation evidence does not show the requested datastore mounted read/write."
        ),
        "source_type": "historical_artifact",
        "freshness": "historical",
        "checked_at": payload.get("checked_at"),
        "recheck_command": "make provider-lab-esxi-netapp-datastore-validate",
        "evidence_artifacts": [_rel(path)] if path_exists(path) else [],
    }


def _configured_vcsa_iso_path() -> Path | None:
    value = settings.vcenter_vcsa_iso_path
    return Path(value).expanduser() if value else None


def _configured_vcsa_deploy_path() -> Path | None:
    value = getattr(settings, "vcenter_vcsa_deploy_path", None)
    return Path(value).expanduser() if value else None


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _boolish(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _first_non_empty_list(*values: Any) -> list[str]:
    for value in values:
        items = _coerce_string_list(value)
        if items:
            return items
    return []


def _coerce_string_list(value: Any) -> list[str]:
    return unique_csv_strings(value, include_scalars=False)


def _read_json_artifact(path: Path) -> dict[str, Any]:
    return read_json_object(path)


def _post_attach_vcenter_netapp_state(*, datastore_name: str | None) -> dict[str, Any]:
    payload = _read_json_artifact(VCENTER_POST_ATTACH_VALIDATION_JSON)
    target = payload.get("target") if isinstance(payload.get("target"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    govc_authentication = checks.get("govc_authentication") if isinstance(checks.get("govc_authentication"), dict) else {}
    datastore_check = checks.get("netapp_datastore_visible") if isinstance(checks.get("netapp_datastore_visible"), dict) else {}
    host = _clean_value(target.get("host")) or _host_from_endpoint(str(target.get("url") or ""))
    url = _redacted_url(str(target.get("url") or "")) or _redacted_url(_vcenter_govc_url(host))
    vcenter_version = _vcenter_version_from_govc_about(str(govc_authentication.get("stdout") or ""))
    required_visible = {
        "datacenter_visible": _check_visible(checks, "datacenter_visible"),
        "cluster_visible": _check_visible(checks, "cluster_visible"),
        "esxi_visible": _check_visible(checks, "esxi_visible"),
        "netapp_datastore_visible": _check_visible(checks, "netapp_datastore_visible"),
        "vm_inventory_visible": _check_visible(checks, "vm_inventory_visible"),
    }
    datastore_matches = _datastore_check_matches(datastore_check, datastore_name)
    ready = payload.get("status") == "ready" and all(required_visible.values()) and datastore_matches
    return {
        "artifact": _rel(VCENTER_POST_ATTACH_VALIDATION_JSON),
        "artifact_exists": bool(payload),
        "checked_at": payload.get("checked_at"),
        "status": payload.get("status") or "not_checked",
        "ready": ready,
        "host": host,
        "url": url,
        "datacenter": target.get("datacenter"),
        "cluster": target.get("cluster"),
        "esxi_target": target.get("esxi_target"),
        "datastore": target.get("datastore") or datastore_check.get("name") or datastore_name,
        "vcenter_version": vcenter_version,
        "datastore_matches": datastore_matches,
        "govc_available": bool(target.get("govc_available") or target.get("govc_configured")),
        "credential_configured": bool(target.get("username_configured") and target.get("credential_configured")),
        "visible": required_visible,
        "source_type": payload.get("source_type") or "historical_artifact",
        "freshness": payload.get("freshness") or "historical",
        "recheck_command": payload.get("recheck_command") or "make provider-lab-vcenter-post-attach-validation",
    }


def _check_visible(checks: dict[str, Any], key: str) -> bool:
    check = checks.get(key)
    return isinstance(check, dict) and check.get("visible") is True


def _datastore_check_matches(check: dict[str, Any], datastore_name: str | None) -> bool:
    expected = _clean_value(datastore_name)
    if not expected:
        return bool(check.get("visible"))
    candidates = [check.get("name"), *(check.get("paths") if isinstance(check.get("paths"), list) else [])]
    return any(expected == str(candidate).strip().split("/")[-1] or expected in str(candidate) for candidate in candidates if candidate)


def _post_attach_validation_check(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("artifact_exists"):
        return {
            "label": "vCenter post-attach validation",
            "status": "not_checked",
            "detail": "No post-attach validation artifact was found.",
            "source_type": "not_checked",
            "freshness": "not_checked",
            "recheck_command": "make provider-lab-vcenter-post-attach-validation",
        }
    ready = bool(state.get("ready"))
    return {
        "label": "vCenter post-attach validation",
        "status": "ready" if ready else "blocked",
        "detail": (
            "Post-attach validation shows vCenter deployed, ESXi attached, datastore visible, and VM inventory visible."
            if ready
            else "Post-attach validation evidence does not yet show all required vCenter inventory checks ready."
        ),
        "source_type": "live_cached",
        "freshness": "current" if ready else "historical",
        "checked_at": state.get("checked_at"),
        "recheck_command": state.get("recheck_command") or "make provider-lab-vcenter-post-attach-validation",
        "evidence_artifacts": [state.get("artifact")] if state.get("artifact") else [],
    }


def _post_attach_datastore_check(state: dict[str, Any], datastore_name: str | None) -> dict[str, Any]:
    datastore = state.get("datastore") or datastore_name
    if state.get("ready"):
        return {
            "label": "Datastore visible through vCenter",
            "status": "ready",
            "detail": f"{datastore} is visible through vCenter post-attach validation.",
            "source_type": "live_cached",
            "freshness": "current",
            "checked_at": state.get("checked_at"),
            "recheck_command": state.get("recheck_command") or "make provider-lab-vcenter-post-attach-validation",
            "evidence_artifacts": [state.get("artifact")] if state.get("artifact") else [],
        }
    if state.get("artifact_exists"):
        return {
            "label": "Datastore visible through vCenter",
            "status": "blocked",
            "detail": f"Post-attach validation does not show {datastore} visible through vCenter.",
            "source_type": "historical_artifact",
            "freshness": "historical",
            "checked_at": state.get("checked_at"),
            "recheck_command": state.get("recheck_command") or "make provider-lab-vcenter-post-attach-validation",
            "evidence_artifacts": [state.get("artifact")] if state.get("artifact") else [],
        }
    return {
        "label": "Datastore visible through vCenter",
        "status": "not_checked",
        "detail": "vCenter/ESXi datastore inventory is not checked until vCenter/govc and NetApp NFS are ready.",
        "source_type": "not_checked",
        "freshness": "not_checked",
        "recheck_command": "make provider-lab-vcenter-post-attach-validation",
    }


def _classify(
    *,
    netapp_stage: str,
    vcenter_host_configured: bool,
    vcenter_credentials_configured: bool,
    govc_available: bool,
    planned_nfs: dict[str, Any],
    post_attach_ready: bool = False,
) -> tuple[str, list[str]]:
    if netapp_stage == "cluster_setup_wizard":
        return (
            "blocked_by_prior_stage",
            ["NetApp is still at cluster_setup_wizard; ONTAP, NFS, and datastore readiness are blocked by prior setup."],
        )
    if netapp_stage != "configured":
        return (
            "blocked_by_prior_stage",
            ["NetApp ONTAP/NFS is not configured yet; datastore readiness is blocked by prior NetApp setup."],
        )
    if not planned_nfs["planned"]:
        return ("blocked_by_prior_stage", ["NetApp NFS volume/export/datastore plan is incomplete."])
    if post_attach_ready:
        return ("ready", [])
    missing_vcenter = []
    if not vcenter_host_configured:
        missing_vcenter.append("VCENTER_HOST/GOVC_URL/VCENTER_MANAGEMENT_IP")
    if not vcenter_credentials_configured:
        missing_vcenter.append("VCENTER_USERNAME/GOVC_USERNAME and VCENTER_PASSWORD/GOVC_PASSWORD")
    if not govc_available:
        missing_vcenter.append("govc")
    if missing_vcenter:
        return ("not_configured_yet", [f"vCenter/govc is not configured yet: {', '.join(missing_vcenter)}."])
    return ("ready", [])


def _tool_available(name: str) -> bool:
    return _tool_path(name) is not None


def _tool_path(name: str) -> Path | None:
    found = which(name)
    if found:
        return Path(found)
    for directory in (Path(sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        candidate = directory / name
        if is_file(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _vcsa_deploy_status() -> dict[str, Any]:
    path = _find_vcsa_deploy()
    if path is None:
        return {
            "label": "vcsa-deploy",
            "status": "not_configured",
            "detail": (
                "vcsa-deploy is not installed, configured with VCSA_DEPLOY/VCSA_DEPLOY_PATH/"
                "VCENTER_VCSA_DEPLOY, or found under a mounted VCSA ISO."
            ),
            "path": None,
            "executable": False,
            "source_type": "tool_probe",
            "freshness": "live",
            "recheck_command": "make provider-lab-vcenter-install-readiness",
        }
    executable = os.access(path, os.X_OK)
    return {
        "label": "vcsa-deploy",
        "status": "ready" if executable else "blocked",
        "detail": "vcsa-deploy is found and executable." if executable else "vcsa-deploy was found but is not executable.",
        "path": _safe_external_path(path),
        "executable": executable,
        "source_type": "tool_probe",
        "freshness": "live",
        "recheck_command": "make provider-lab-vcenter-install-readiness",
    }


def _find_vcsa_deploy() -> Path | None:
    explicit = _configured_vcsa_deploy_path()
    if explicit and is_file(explicit):
        return explicit
    path_tool = _tool_path("vcsa-deploy")
    if path_tool is not None:
        return path_tool
    for root in VCSA_MOUNT_ROOTS:
        for candidate in _vcsa_deploy_candidates(root):
            if is_file(candidate):
                return candidate
    return None


def _vcsa_deploy_candidates(root: Path) -> tuple[Path, ...]:
    installer_root = root / "vcsa-cli-installer"
    if os.name == "nt":
        preferred = (
            installer_root / "win32" / "vcsa-deploy.exe",
            installer_root / "win32" / "vcsa-deploy",
        )
    else:
        preferred = (
            installer_root / "lin64" / "vcsa-deploy",
            installer_root / "win32" / "vcsa-deploy.exe",
        )
    return tuple(unique_preserving_order([*preferred, installer_root / "lin64" / "vcsa-deploy"]))


def _chmod_private(path: str) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        return


def _netapp_stage(state: dict[str, Any]) -> str:
    configured_state = str(state.get("configured_state") or "")
    console = state.get("console") if isinstance(state.get("console"), dict) else {}
    prompt_state = str(console.get("prompt_state") or "")
    artifact_prompt_state = str(_artifact_value(CONSOLE_STATE_JSON, "selected_prompt_state") or "")
    artifact_identified_state = str(_artifact_value(CONSOLE_LOGIN_STATE_JSON, "identified_state") or "")
    if state.get("configured") is True or configured_state == "configured":
        return "configured"
    if configured_state in {"api_authenticated", "management_reachable", "ontap_detected"}:
        return "ontap_partial"
    if (
        prompt_state == "cluster_setup_prompt"
        or artifact_prompt_state == "cluster_setup_prompt"
        or artifact_identified_state == "cluster_setup_wizard"
        or configured_state == "setup_wizard"
    ):
        return "cluster_setup_wizard"
    return "not_configured"


def _artifact_value(path: Path, key: str) -> Any:
    return read_json_object(path).get(key)


def _planned_nfs() -> dict[str, Any]:
    missing = []
    if not settings.netapp_nfs_volume:
        missing.append("NETAPP_NFS_VOLUME")
    if not settings.netapp_nfs_export_policy:
        missing.append("NETAPP_NFS_EXPORT_POLICY")
    if not settings.netapp_nfs_mount_path:
        missing.append("NETAPP_NFS_MOUNT_PATH")
    if not settings.netapp_nfs_datastore_name:
        missing.append("NETAPP_NFS_DATASTORE_NAME")
    if not settings.netapp_nfs_lifs:
        missing.append("NETAPP_NFS_LIFS")
    return {
        "planned": not missing,
        "missing_fields": missing,
        "volume": settings.netapp_nfs_volume,
        "export_policy": settings.netapp_nfs_export_policy,
        "mount_path": settings.netapp_nfs_mount_path,
        "datastore_name": settings.netapp_nfs_datastore_name,
        "nfs_lifs": list(settings.netapp_nfs_lifs),
        "client_match": settings.netapp_nfs_client_match,
    }


def _datastore_preview(first_lif: str) -> dict[str, str]:
    return {
        "govc": (
            "govc datastore.create -type nfs "
            f"-name {settings.netapp_nfs_datastore_name} "
            f"-remote-host {first_lif} "
            f"-remote-path {settings.netapp_nfs_mount_path}"
        ),
        "esxi_fallback": (
            "esxcli storage nfs add "
            f"-H {first_lif} "
            f"-s {settings.netapp_nfs_mount_path} "
            f"-v {settings.netapp_nfs_datastore_name}"
        ),
    }


def _config_check(label: str, ok: bool, ready_detail: str, missing_detail: str) -> dict[str, Any]:
    return {
        "label": label,
        "status": "ready" if ok else "not_configured",
        "detail": ready_detail if ok else missing_detail,
        "source_type": "operator_config",
        "freshness": "live",
    }


def _tcp_check(label: str, host: str | None, port: int, *, check_ports: bool) -> dict[str, Any]:
    if not host:
        return {
            "label": label,
            "host": None,
            "port": port,
            "status": "not_configured",
            "detail": f"{label} host is not configured.",
            "source_type": "not_checked",
            "freshness": "not_checked",
        }
    if not check_ports:
        return {
            "label": label,
            "host": host,
            "port": port,
            "status": "not_checked",
            "detail": "Reachability not checked in this read.",
            "source_type": "not_checked",
            "freshness": "not_checked",
        }
    try:
        with socket.create_connection((host, port), timeout=2.5):
            reachable = True
    except OSError as exc:
        return {
            "label": label,
            "host": host,
            "port": port,
            "status": "blocked",
            "detail": f"TCP {port} check failed with {exc.__class__.__name__}.",
            "source_type": "live_provider",
            "freshness": "live",
        }
    return {
        "label": label,
        "host": host,
        "port": port,
        "status": "ready" if reachable else "blocked",
        "detail": f"TCP {port} reachable.",
        "source_type": "live_provider",
        "freshness": "live",
    }


def _ip_available_check(label: str, host: Any, *, check_ports: bool) -> dict[str, Any]:
    address = _clean_value(host)
    if not address:
        return {
            "label": label,
            "host": None,
            "status": "not_configured",
            "detail": f"{label} is not configured.",
            "available": False,
            "source_type": "not_checked",
            "freshness": "not_checked",
        }
    if not check_ports:
        return {
            "label": label,
            "host": address,
            "status": "not_checked",
            "detail": "Management IP availability was not checked in this read.",
            "available": None,
            "source_type": "not_checked",
            "freshness": "not_checked",
            "recheck_command": "make provider-lab-vcenter-install-readiness",
        }
    ping_reply = _ping(address)
    tcp_443 = _tcp_open(address, 443)
    tcp_5480 = _tcp_open(address, 5480)
    neighbor = _neighbor_state(address)
    neighbor_in_use = neighbor in {"REACHABLE", "DELAY", "PROBE"}
    in_use = ping_reply or tcp_443 or tcp_5480 or neighbor_in_use
    return {
        "label": label,
        "host": address,
        "status": "ready" if not in_use else "blocked",
        "detail": (
            "Management IP appears available for VCSA deployment."
            if not in_use
            else "Management IP appears to be in use or visible on the local network."
        ),
        "available": not in_use,
        "ping": "reply" if ping_reply else "no_reply",
        "tcp_443": "open" if tcp_443 else "closed",
        "tcp_5480": "open" if tcp_5480 else "closed",
        "neighbor_state": neighbor or "not_present",
        "source_type": "live_provider",
        "freshness": "live",
        "recheck_command": "make provider-lab-vcenter-install-readiness",
    }


def _ping(address: str) -> bool:
    if which("ping") is None:
        return False
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _tcp_open(address: str, port: int) -> bool:
    try:
        with socket.create_connection((address, port), timeout=1.0):
            return True
    except OSError:
        return False


def _neighbor_state(address: str) -> str | None:
    if which("ip") is None:
        return None
    try:
        result = subprocess.run(
            ["ip", "neigh", "show", address],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = result.stdout.strip()
    for state in ("REACHABLE", "STALE", "DELAY", "PROBE", "FAILED", "INCOMPLETE"):
        if state in text:
            return state
    return None


def _wait_for_tcp(host: str, port: int, *, timeout_seconds: int, poll_seconds: int) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    while True:
        if _tcp_open(host, port):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(max(poll_seconds, 1))


def _host_from_endpoint(value: str | None) -> str | None:
    text = _clean_value(value)
    if not text:
        return None
    if "://" not in text:
        return text.split("/", maxsplit=1)[0]
    parts = urlsplit(text)
    return parts.hostname


def _vcenter_version_from_govc_about(stdout: str) -> str | None:
    version = None
    build = None
    for line in stdout.splitlines():
        key, _, value = line.partition(":")
        normalized = key.strip().lower()
        if normalized == "version":
            version = value.strip() or None
        elif normalized == "build":
            build = value.strip() or None
    if version and build:
        return f"{version} build-{build}"
    return version


def _vcenter_govc_url(host: str | None) -> str | None:
    if not host:
        return None
    configured = _clean_value(settings.vcenter_host)
    if configured and "://" in configured:
        parts = urlsplit(configured)
        if parts.path and parts.path != "/":
            return configured
        return urlunsplit((parts.scheme, parts.netloc, "/sdk", "", ""))
    return f"https://{host}/sdk"


def _vcenter_time_sync_mode() -> str:
    configured = _clean_value(os.getenv("VCENTER_TIME_SYNC_MODE"))
    return "ntp" if configured and configured.lower() == "ntp" else "tools"


def _vcenter_validation_verify_tls() -> bool:
    if os.getenv("VCENTER_VERIFY_TLS") is None and os.getenv("GOVC_TLS_VERIFY") is None:
        if settings.provider_mode in {LOCAL_READONLY_MODE, LOCAL_LAB_READWRITE_MODE}:
            return False
    return bool(settings.vcenter_verify_tls)


def _vcenter_validation_username() -> str | None:
    return (
        _canonical_vcenter_sso_admin_username()
        or _canonical_vcenter_sso_username(_clean_value(os.getenv("VCENTER_USERNAME")))
        or _clean_value(os.getenv("GOVC_USERNAME"))
    )


def _vcenter_validation_password() -> str | None:
    return (
        _clean_value(settings.vcenter_sso_admin_password)
        or _clean_value(os.getenv("VCENTER_PASSWORD"))
        or _clean_value(os.getenv("GOVC_PASSWORD"))
    )


def _canonical_vcenter_sso_admin_username() -> str | None:
    return _canonical_vcenter_sso_username(_clean_value(settings.vcenter_sso_admin_username))


def _canonical_vcenter_sso_username(username: str | None) -> str | None:
    if not username:
        return None
    if "@" not in username:
        return username
    name, domain = username.split("@", 1)
    if name.lower() == "administrator":
        return f"Administrator@{domain}"
    return username


def _time_sync_label(values: dict[str, Any]) -> str:
    if values.get("time_sync_mode") == "ntp":
        return f"NTP ({', '.join(values.get('ntp_servers') or []) or 'missing'})"
    return "VMware Tools"


def _vcsa_deploy_command_preview(readiness: dict[str, Any]) -> str:
    deploy = (readiness.get("current_state") or {}).get("vcsa_deploy") or "vcsa-deploy"
    return " ".join(_vcsa_deploy_install_command(str(deploy), "<generated-vcsa-spec.json>"))


def _vcsa_deploy_install_command(deploy: str, spec_path: str) -> list[str]:
    command = [deploy, "install", "--accept-eula", "--acknowledge-ceip"]
    if not _vcsa_deploy_verify_tls():
        command.append("--no-ssl-certificate-verification")
    command.append(spec_path)
    return command


def _vcsa_deploy_verify_tls() -> bool:
    return bool(getattr(settings, "esxi_test_verify_tls", settings.vcenter_verify_tls))


def _server_certificate_sha1_thumbprint(host: Any, port: int = 443) -> str | None:
    text = _clean_value(host)
    if not text:
        return None
    try:
        pem = ssl.get_server_certificate((text, port), timeout=10)
        der = ssl.PEM_cert_to_DER_cert(pem)
    except (OSError, ValueError, ssl.SSLError):
        return None
    digest = hashlib.sha1(der).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


def _first_blocker(values: list[Any]) -> str | None:
    for value in values:
        if value:
            return str(value)
    return None


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _tail(value: str | None, *, max_chars: int = 4000) -> str:
    text = value or ""
    return text[-max_chars:] if len(text) > max_chars else text


def _decode_bytes(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _json_contains(stdout: Any, needle: str) -> bool:
    text = _decode_bytes(stdout)
    if not needle:
        return False
    if needle in text:
        return True
    payload = parse_json_value(stdout)
    if payload is None:
        return False
    return needle in json.dumps(payload)


def _stdout_lines(stdout: Any) -> list[str]:
    return [line.strip() for line in str(stdout or "").splitlines() if line.strip()]


def _path_list_contains(paths: list[str], needle: str) -> bool:
    if not needle:
        return False
    lowered = needle.lower()
    for path in paths:
        if lowered == path.rstrip("/").split("/")[-1].lower():
            return True
        if lowered in path.lower():
            return True
    return False


def _vcenter_apply_warnings(
    *,
    validation: dict[str, Any] | None,
    refresh_result: dict[str, Any] | None,
) -> list[str]:
    warnings = [
        "vcsa-deploy is the only deployment executor for this workflow; secrets are passed through a temporary local spec and not written to artifacts.",
    ]
    if validation:
        warnings.extend(_coerce_string_list(validation.get("warnings")))
    if refresh_result:
        warnings.extend(_coerce_string_list(refresh_result.get("errors")))
    return _unique(warnings)


def _vcenter_apply_not_attempted(apply_result: dict[str, Any]) -> list[str]:
    skipped = [
        "vCenter delete",
        "vCenter inventory host add",
        "NetApp datastore create/delete",
        "ESXi host reconfiguration outside vcsa-deploy",
    ]
    if not apply_result.get("vcsa_deploy_attempted"):
        skipped.insert(0, "vcsa-deploy install")
    return skipped


def _post_install_not_attempted(govc_ready: bool) -> list[str]:
    skipped = [
        "vCenter inventory host add",
        "vCenter datastore mount/create",
        "ESXi host reconfiguration",
        "NetApp ONTAP write",
    ]
    if not govc_ready:
        skipped.insert(0, "vCenter inventory validation through govc")
    return skipped


def _vcenter_attach_apply_warnings(
    *,
    operations: list[dict[str, Any]],
    validation: dict[str, Any] | None,
) -> list[str]:
    warnings = [
        "vCenter host attach uses govc with local-only ESXi credential values; credentials are never written to reports.",
    ]
    if any(operation.get("operation") == "esxi.attach" and "-noverify" in str(operation.get("command_preview")) for operation in operations):
        warnings.append("ESXi certificate thumbprint was unavailable; govc host attach used -noverify for this local lab.")
    if validation:
        warnings.extend(_coerce_string_list(validation.get("warnings")))
    return _unique(warnings)


def _vcenter_attach_not_attempted(*, status: str, operations: list[dict[str, Any]]) -> list[str]:
    attempted = {str(operation.get("operation")) for operation in operations if operation.get("attempted")}
    skipped = [
        "vCenter datastore mount/create",
        "ESXi host power/reset/reboot",
        "ESXi datastore create/delete",
        "NetApp ONTAP write",
        "VM create/delete/power operation",
    ]
    if status == "blocked":
        skipped.extend(["vCenter datacenter create", "vCenter cluster create", "vCenter ESXi host add"])
    else:
        if "datacenter.ensure" not in attempted:
            skipped.append("vCenter datacenter create")
        if "cluster.ensure" not in attempted:
            skipped.append("vCenter cluster create")
        if "esxi.attach" not in attempted:
            skipped.append("vCenter ESXi host add")
    return _unique(skipped)


def _write_json(path: Path, payload: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, dict):
        write_json_object(path, payload)
        return
    write_json_value(path, payload)


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    configured = [
        settings.vcenter_password,
        settings.vcenter_sso_admin_password,
        settings.vcenter_appliance_root_password,
        settings.esxi_test_password,
    ]
    env_values = [
        value
        for key, value in os.environ.items()
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie"))
    ]
    return [str(value) for value in [*configured, *env_values] if value]


def _unique(values: list[Any]) -> list[Any]:
    return unique_preserving_order(values, skip_falsey=True, key=str)


def _missing_fields(vcenter_host: bool, vcenter_credentials: bool, netapp_credentials: bool) -> list[str]:
    missing = []
    if not vcenter_host:
        missing.extend(["VCENTER_HOST", "GOVC_URL"])
    if not vcenter_credentials:
        missing.extend(["VCENTER_USERNAME/GOVC_USERNAME", "VCENTER_PASSWORD/GOVC_PASSWORD"])
    if not netapp_credentials:
        missing.extend(["NETAPP_API_USERNAME", "NETAPP_API_PASSWORD"])
    return missing


def _message(status: str, *, post_attach_ready: bool = False, datastore_name: str | None = None) -> str:
    if status == "ready" and post_attach_ready:
        datastore = datastore_name or "the NetApp datastore"
        return f"vCenter is deployed, ESXi is attached, and {datastore} is visible through vCenter."
    if status == "ready":
        return "vCenter-NetApp readiness is ready for a future guarded datastore apply lane."
    if status == "not_configured_yet":
        return "vCenter/govc is not configured yet."
    return "vCenter-NetApp readiness is blocked by prior NetApp/ONTAP/NFS setup."


def _next_action(status: str, *, post_attach_ready: bool = False, datastore_name: str | None = None) -> str:
    if status == "ready" and post_attach_ready:
        datastore = datastore_name or "the NetApp datastore"
        return f"No vCenter-NetApp datastore action required; post-attach validation is ready and {datastore} is visible through vCenter."
    if status == "ready":
        return "Review the datastore command preview; keep apply disabled until a guarded apply workflow is implemented."
    if status == "not_configured_yet":
        return "Configure VCENTER_HOST/GOVC_URL or VCENTER_MANAGEMENT_IP, vCenter credentials, and govc, then rerun `make provider-lab-vcenter-netapp-readiness`."
    return "Complete NetApp ONTAP setup and NFS readiness before vCenter datastore work."


def _readiness_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# vCenter-NetApp Readiness Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Source type: `{payload.get('source_type')}`",
        f"- NetApp stage: `{payload.get('netapp_stage')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Targets",
    ]
    for key, value in (payload.get("targets") or {}).items():
        lines.append(f"- {key}: `{value or 'not configured'}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Checks"])
    for key, check in (payload.get("checks") or {}).items():
        lines.append(f"- {key}: `{check.get('status')}` - {check.get('detail')}")
    post_attach = payload.get("post_attach_validation") if isinstance(payload.get("post_attach_validation"), dict) else {}
    if post_attach:
        lines.extend(
            [
                "",
                "## Post-Attach Evidence",
                f"- Status: `{post_attach.get('status')}`",
                f"- Ready: `{post_attach.get('ready')}`",
                f"- vCenter: `{post_attach.get('url') or post_attach.get('host') or 'not configured'}`",
                f"- ESXi attached: `{(post_attach.get('visible') or {}).get('esxi_visible')}`",
                f"- Datastore visible: `{(post_attach.get('visible') or {}).get('netapp_datastore_visible')}`",
                f"- VM inventory visible: `{(post_attach.get('visible') or {}).get('vm_inventory_visible')}`",
                f"- Checked at: `{post_attach.get('checked_at')}`",
            ]
        )
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    lines.extend(["", "## Safety", "- No datastore, ONTAP, vCenter, ESXi, NFS, or storage write action was run."])
    return "\n".join(lines) + "\n"


def _plan_markdown(payload: dict[str, Any]) -> str:
    preview = payload.get("datastore_add_preview") or {}
    planned = payload.get("planned_nfs") or {}
    return "\n".join(
        [
            "# vCenter-NetApp Datastore Plan Report",
            "",
            f"- Generated at: `{payload.get('generated_at')}`",
            "- Apply enabled: `False`",
            "- Plan type: `preview_only`",
            "",
            "## Planned NFS",
            f"- Volume: `{planned.get('volume')}`",
            f"- Export policy: `{planned.get('export_policy')}`",
            f"- Mount path: `{planned.get('mount_path')}`",
            f"- Datastore: `{planned.get('datastore_name')}`",
            f"- NFS LIFs: `{', '.join(planned.get('nfs_lifs') or [])}`",
            "",
            "## Current State",
            f"- Status: `{payload.get('status')}`",
            f"- Next action: {payload.get('next_safe_action')}",
            "",
            "## Command Preview",
            f"- govc: `{preview.get('govc')}`",
            f"- ESXi fallback: `{preview.get('esxi_fallback')}`",
            "",
            "## Safety",
            "- This is not runnable apply logic.",
            "- Future apply must require fresh discovery, approval, audit logging, and explicit write gates.",
        ]
    ) + "\n"


def _find_vcsa_iso() -> Path | None:
    explicit = _configured_vcsa_iso_path()
    if explicit and is_file(explicit):
        return explicit
    roots = [Path(item).expanduser() for item in settings.media_inventory_dirs]
    roots.append(REPO_ROOT / "artifacts" / "Media")
    candidates: list[Path] = []
    for root in roots:
        if not is_directory(root):
            continue
        for path in rglob_paths(root, "*.iso"):
            lowered = path.name.lower()
            if is_file(path) and any(marker in lowered for marker in ("vcsa", "vcenter", "vmware-vc")):
                candidates.append(path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: str(item).lower())[0]


def _safe_media_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return display_path(path.resolve(), REPO_ROOT)


def _safe_external_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _vcenter_install_markdown(payload: dict[str, Any]) -> str:
    current = payload.get("current_state") or {}
    target = payload.get("target_state") or {}
    values = payload.get("deployment_values") or {}
    credential_state = payload.get("credential_state") or {}
    install_plan = payload.get("install_plan") or {}
    title = {
        "vcenter-install-readiness": "# vCenter Install Readiness Report",
        "vcenter-install-preview": "# vCenter Install Preview Report",
    }.get(str(payload.get("action")), "# vCenter Install Plan Report")
    lines = [
        title,
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Action: `{payload.get('action')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Current State",
        f"- VCSA ISO: `{current.get('vcsa_iso') or 'not found'}`",
        f"- vcsa-deploy: `{current.get('vcsa_deploy') or 'not found'}`",
        f"- ESXi management: `{current.get('esxi_management')}`",
        f"- NetApp datastore: `{current.get('netapp_datastore')}`",
        f"- vCenter installed/configured: `{current.get('vcenter_installed')}`",
        "",
        "## Target State",
        f"- vCenter: `{target.get('vcenter') or 'not configured'}`",
        f"- Deployment target: `{target.get('deployment_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
        f"- Deployment size: `{target.get('deployment_size') or 'not configured'}`",
        f"- Network / portgroup: `{target.get('network') or target.get('portgroup') or 'not configured'}`",
        f"- Management IP available: `{target.get('management_ip_available')}`",
        "",
        "## Deployment Values",
        f"- Appliance name: `{values.get('appliance_name') or 'missing'}`",
        f"- Management IP: `{values.get('management_ip') or 'missing'}`",
        f"- Subnet: `{values.get('subnet_cidr') or 'missing'}`",
        f"- Gateway: `{values.get('gateway') or 'missing'}`",
        f"- DNS: `{', '.join(values.get('dns_servers') or []) or 'missing'}`",
        f"- Time sync: `{_time_sync_label(values)}`",
        f"- SSO domain: `{values.get('sso_domain') or 'missing'}`",
        f"- SSO admin username: `{values.get('sso_admin_username_status') or 'missing'}`",
        f"- Values complete: `{values.get('complete')}`",
        "",
        "## Credential Status",
        f"- SSO admin password: `{'configured' if credential_state.get('sso_admin_password_configured') else 'missing'}`",
        f"- Appliance root password: `{'configured' if credential_state.get('appliance_root_password_configured') else 'missing'}`",
        f"- ESXi credentials: `{'configured' if credential_state.get('esxi_credentials_configured') else 'missing'}`",
        f"- Post-install vCenter credentials: `{'configured' if credential_state.get('post_install_vcenter_credentials_configured') else 'missing'}`",
        "",
        "## Checks",
    ]
    for key, check in (payload.get("checks") or {}).items():
        lines.append(f"- {key}: `{check.get('status')}` - {check.get('detail')}")
    command_preview = install_plan.get("command_preview") if isinstance(install_plan, dict) else None
    if command_preview:
        lines.extend(["", "## Command Preview"])
        lines.extend(f"- `{item}`" for item in command_preview)
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Safety", "- No vCenter install, vCenter write, ESXi write, datastore mount, or appliance power action was run."])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    return "\n".join(lines) + "\n"


def _vcenter_apply_markdown(payload: dict[str, Any]) -> str:
    current = payload.get("current_state") or {}
    target = payload.get("target_state") or {}
    apply_result = payload.get("apply") or {}
    gate_state = payload.get("apply_gate_state") or {}
    flag_state = gate_state.get("flag_state") if isinstance(gate_state.get("flag_state"), dict) else {}
    lines = [
        "# vCenter Install Apply Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Provider mode: `{payload.get('mode')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- vcsa-deploy attempted: `{apply_result.get('vcsa_deploy_attempted')}`",
        f"- vcsa-deploy result: `{apply_result.get('result')}`",
        f"- vcsa-deploy return code: `{apply_result.get('return_code')}`",
        "",
        "## Current State",
        f"- VCSA ISO: `{current.get('vcsa_iso') or 'not found'}`",
        f"- vcsa-deploy: `{current.get('vcsa_deploy') or 'not found'}`",
        f"- ESXi management: `{current.get('esxi_management')}`",
        f"- NetApp datastore: `{current.get('netapp_datastore')}`",
        "",
        "## Target State",
        f"- vCenter: `{target.get('vcenter') or 'not configured'}`",
        f"- Deployment target: `{target.get('deployment_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
        f"- Network / portgroup: `{target.get('network') or target.get('portgroup') or 'not configured'}`",
        "",
        "## Apply Gates",
    ]
    for flag in gate_state.get("required_flags") or []:
        lines.append(f"- `{flag}`")
    lines.extend(["", "## Gate State"])
    for key, value in flag_state.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Command"])
    lines.append(f"- `{apply_result.get('command') or _vcsa_deploy_command_preview(payload)}`")
    if apply_result.get("stdout_summary"):
        lines.extend(["", "## vcsa-deploy stdout summary", "```text", str(apply_result.get("stdout_summary")), "```"])
    if apply_result.get("stderr_summary"):
        lines.extend(["", "## vcsa-deploy stderr summary", "```text", str(apply_result.get("stderr_summary")), "```"])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(
        [
            "",
            "## Safety",
            "- Secrets are redacted in this report.",
            "- The unredacted VCSA spec is written only to a temporary 0600 file for vcsa-deploy and is removed after the command exits.",
        ]
    )
    return "\n".join(lines) + "\n"


def _vcenter_post_install_markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target") or {}
    checks = payload.get("checks") or {}
    lines = [
        "# vCenter Post-Install Validation Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- vCenter host: `{target.get('host') or 'not configured'}`",
        f"- govc configured: `{target.get('govc_configured')}`",
        f"- ESXi target: `{target.get('esxi_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
        "",
        "## Checks",
    ]
    for key, check in checks.items():
        status = check.get("status") if isinstance(check, dict) else "unknown"
        detail = check.get("detail") if isinstance(check, dict) else ""
        lines.append(f"- {key}: `{status}` {detail or ''}".rstrip())
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Safety", "- Validation uses ping, TCP/443, HTTPS/API, and read-only govc inventory checks."])
    return "\n".join(lines) + "\n"


def _vcenter_apply_final_markdown(payload: dict[str, Any]) -> str:
    validation = payload.get("post_install_validation") or {}
    refresh = payload.get("post_install_refresh") or {}
    refreshed = refresh.get("refreshed") if isinstance(refresh.get("refreshed"), dict) else {}
    artifacts = payload.get("artifacts") or {}
    lines = [
        "# vCenter Install Apply Unblock Final Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Apply status: `{payload.get('status')}`",
        f"- Validation status: `{validation.get('status') or 'not_run'}`",
        f"- Golden State refresh: `{refreshed.get('golden_state_status') or 'not_run'}`",
        f"- Lab Validation refresh: `{refreshed.get('lab_validation_status') or 'not_run'}`",
        "",
        "## Reports",
    ]
    for label, path in artifacts.items():
        lines.append(f"- {label}: `{path}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    if validation.get("blockers"):
        lines.extend(["", "## Validation Blockers"])
        lines.extend(f"- {item}" for item in validation.get("blockers") or [])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
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


def _vcenter_attach_preview_markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target") or {}
    plan = payload.get("attach_plan") or {}
    checks = payload.get("checks") or {}
    lines = [
        "# vCenter ESXi Attach Preview Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Target",
        f"- vCenter host: `{target.get('host') or 'not configured'}`",
        f"- Datacenter: `{target.get('datacenter')}`",
        f"- Cluster: `{target.get('cluster')}`",
        f"- ESXi host: `{target.get('esxi_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
        f"- Host attach TLS mode: `{target.get('host_attach_tls_mode')}`",
        "",
        "## Plan",
    ]
    for step in plan.get("steps") or []:
        lines.append(f"- {step.get('operation')}: `{step.get('status')}` - `{step.get('command_preview')}`")
    lines.extend(["", "## Checks"])
    for key, check in checks.items():
        if not isinstance(check, dict):
            continue
        lines.append(f"- {key}: `{check.get('status')}` visible=`{check.get('visible')}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Safety", "- Preview only. No vCenter inventory write, ESXi write, datastore mount, or NetApp action was run."])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    return "\n".join(lines) + "\n"


def _vcenter_attach_apply_markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target") or {}
    gate_state = payload.get("apply_gate_state") or {}
    flag_state = gate_state.get("flag_state") if isinstance(gate_state.get("flag_state"), dict) else {}
    lines = [
        "# vCenter ESXi Attach Apply Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Provider mode: `{payload.get('mode')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Target",
        f"- vCenter host: `{target.get('host') or 'not configured'}`",
        f"- Datacenter: `{target.get('datacenter')}`",
        f"- Cluster: `{target.get('cluster')}`",
        f"- ESXi host: `{target.get('esxi_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
        "",
        "## Apply Gates",
    ]
    for flag in gate_state.get("required_flags") or []:
        lines.append(f"- `{flag}`")
    lines.extend(["", "## Gate State"])
    for key, value in flag_state.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Operations"])
    for operation in payload.get("operations") or []:
        lines.append(
            f"- {operation.get('operation')}: `{operation.get('status')}` "
            f"attempted=`{operation.get('attempted')}` changed=`{operation.get('changed')}` - {operation.get('detail')}"
        )
        if operation.get("stderr_summary"):
            lines.append(f"  - stderr summary: `{operation.get('stderr_summary')}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(
        [
            "",
            "## Safety",
            "- ESXi credential values are passed only to govc for host attach and are redacted from artifacts.",
            "- No datastore create/delete, NetApp write, VM power action, or ESXi power/reset action was run.",
        ]
    )
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    return "\n".join(lines) + "\n"


def _vcenter_post_attach_markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target") or {}
    checks = payload.get("checks") or {}
    lines = [
        "# vCenter Post-Attach Validation Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- vCenter host: `{target.get('host') or 'not configured'}`",
        f"- Datacenter: `{target.get('datacenter')}`",
        f"- Cluster: `{target.get('cluster')}`",
        f"- ESXi host: `{target.get('esxi_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
        "",
        "## Checks",
    ]
    for key, check in checks.items():
        if not isinstance(check, dict):
            continue
        suffix = ""
        if key == "vm_inventory_visible":
            suffix = f" count=`{check.get('count')}`"
        lines.append(f"- {key}: `{check.get('status')}` visible=`{check.get('visible')}`{suffix}")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Safety", "- Validation uses read-only govc inventory checks."])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    return "\n".join(lines) + "\n"


def _vcenter_attach_final_markdown(payload: dict[str, Any]) -> str:
    validation = payload.get("post_attach_validation") or {}
    artifacts = payload.get("artifacts") or {}
    lines = [
        "# vCenter Attach ESXi Datastore Final Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Apply status: `{payload.get('status')}`",
        f"- Post-attach validation status: `{validation.get('status') or 'not_run'}`",
        "",
        "## Reports",
    ]
    for label, path in artifacts.items():
        lines.append(f"- {label}: `{path}`")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    if validation.get("blockers"):
        lines.extend(["", "## Validation Blockers"])
        lines.extend(f"- {item}" for item in validation.get("blockers") or [])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
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


def _redacted_url(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "://" not in text:
        return text
    parts = urlsplit(text)
    hostname = parts.hostname or ""
    netloc = hostname
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()
