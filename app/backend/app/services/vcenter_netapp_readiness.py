from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import which
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.core.config import LAB_ESXI_MANAGEMENT_IP, settings
from app.providers.redaction import redact_sensitive
from app.services.lab_profiles import active_lab_profile_context
from app.services.netapp_state import get_netapp_runtime_state

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
READINESS_REPORT = CODEX_RUN_DIR / "vcenter-netapp-readiness-report.md"
PLAN_REPORT = CODEX_RUN_DIR / "vcenter-netapp-datastore-plan-report.md"
READINESS_JSON = CODEX_RUN_DIR / "vcenter-netapp-readiness-redacted.json"
VCENTER_INSTALL_READINESS_REPORT = CODEX_RUN_DIR / "vcenter-install-readiness-report.md"
VCENTER_INSTALL_PLAN_REPORT = CODEX_RUN_DIR / "vcenter-install-plan-report.md"
VCENTER_INSTALL_PREVIEW_REPORT = CODEX_RUN_DIR / "vcenter-install-preview-report.md"
VCENTER_INSTALL_READINESS_JSON = CODEX_RUN_DIR / "vcenter-install-readiness-redacted.json"
VCENTER_INSTALL_PLAN_JSON = CODEX_RUN_DIR / "vcenter-install-plan-redacted.json"
VCENTER_INSTALL_PREVIEW_JSON = CODEX_RUN_DIR / "vcenter-install-preview-redacted.json"
CONSOLE_STATE_JSON = CODEX_RUN_DIR / "netapp-console-state-redacted.json"
CONSOLE_LOGIN_STATE_JSON = CODEX_RUN_DIR / "netapp-console-login-state-redacted.json"
VCSA_MOUNT_ROOTS = (
    Path("/tmp/vcsa-iso"),
    Path("/mnt/vcsa-iso"),
    Path("/media/vcsa-iso"),
    Path("/run/media/vcsa-iso"),
)


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
            READINESS_JSON.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
            READINESS_REPORT.write_text(_readiness_markdown(sanitized), encoding="utf-8")
            PLAN_REPORT.write_text(_plan_markdown(sanitized), encoding="utf-8")
        return sanitized
    netapp_state = get_netapp_runtime_state()
    netapp_stage = _netapp_stage(netapp_state)
    vcenter_target = _redacted_url(settings.vcenter_host)
    first_lif = (list(settings.netapp_nfs_lifs) or [settings.netapp_svm_mgmt_ip])[0]
    govc_available = _tool_available("govc")
    vcenter_host_configured = bool(settings.vcenter_host or settings.vcenter_configured)
    vcenter_credentials_configured = bool(settings.vcenter_username and settings.vcenter_password)
    netapp_credentials_configured = bool(settings.netapp_api_username and settings.netapp_api_password)
    planned_nfs = _planned_nfs()

    checks = {
        "vcenter_configured": _config_check(
            "vCenter target",
            vcenter_host_configured,
            "VCENTER_HOST or GOVC_URL is configured.",
            "VCENTER_HOST / GOVC_URL is not configured.",
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
        "datastore_mounted": {
            "label": "Datastore mounted",
            "status": "not_checked",
            "detail": "vCenter/ESXi datastore inventory is not checked until vCenter/govc and NetApp NFS are ready.",
            "source_type": "not_checked",
        },
    }

    classification, blockers = _classify(
        netapp_stage=netapp_stage,
        vcenter_host_configured=vcenter_host_configured,
        vcenter_credentials_configured=vcenter_credentials_configured,
        govc_available=govc_available,
        planned_nfs=planned_nfs,
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
        "message": _message(classification),
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if check_ports else "live_cached",
        "freshness": "current" if check_ports else "not_checked",
        "netapp_stage": netapp_stage,
        "targets": {
            "vcenter": vcenter_target,
            "esxi_management": settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP,
            "netapp_cluster_management": settings.netapp_cluster_mgmt_ip,
            "netapp_nfs_lif": first_lif,
            "datastore_name": settings.netapp_nfs_datastore_name,
        },
        "credential_state": {
            "vcenter_host_configured": vcenter_host_configured,
            "vcenter_credentials_configured": vcenter_credentials_configured,
            "netapp_credentials_configured": netapp_credentials_configured,
            "missing_fields": _missing_fields(vcenter_host_configured, vcenter_credentials_configured, netapp_credentials_configured),
        },
        "tooling": {
            "govc_available": govc_available,
            "govc_path": "configured" if govc_available else "not_found",
        },
        "planned_nfs": planned_nfs,
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
        "next_safe_action": _next_action(classification),
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        READINESS_JSON.write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        READINESS_REPORT.write_text(_readiness_markdown(sanitized), encoding="utf-8")
        PLAN_REPORT.write_text(_plan_markdown(sanitized), encoding="utf-8")
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
    vcenter_host_configured = bool(settings.vcenter_host or settings.vcenter_configured)
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
    warnings = [
        "Install apply is intentionally disabled; this report only prepares the guided deployment lane.",
        "vCenter deploy must wait until ESXi management and the NetApp datastore are ready.",
    ]
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
        "apply_enabled": False,
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
        "blockers": list(dict.fromkeys(blockers)),
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
            "readiness_json": _rel(VCENTER_INSTALL_READINESS_JSON),
        },
        "next_safe_action": (
            "Run Preview Deploy to generate the redacted VCSA deployment plan."
            if not blockers
            else "Complete missing vCenter deployment values and local-only credentials, then rerun vCenter install readiness."
        ),
    }
    sanitized = redact_sensitive(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        VCENTER_INSTALL_READINESS_JSON.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        VCENTER_INSTALL_READINESS_REPORT.write_text(_vcenter_install_markdown(sanitized), encoding="utf-8")
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
        VCENTER_INSTALL_PLAN_JSON.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        VCENTER_INSTALL_PLAN_REPORT.write_text(_vcenter_install_markdown(sanitized), encoding="utf-8")
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
        VCENTER_INSTALL_PREVIEW_JSON.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        VCENTER_INSTALL_PREVIEW_REPORT.write_text(_vcenter_install_markdown(sanitized), encoding="utf-8")
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
            "deploy_confirmations_present": False,
            "deploy_apply_enabled": False,
        },
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
        "post_install_vcenter_configured": bool(settings.vcenter_host or settings.vcenter_configured),
        "post_install_vcenter": _redacted_url(settings.vcenter_host),
    }


def _vcenter_deployment_value_checks(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        "appliance_name": _value_check("vCenter appliance name", "VCENTER_APPLIANCE_NAME", values.get("appliance_name")),
        "management_ip": _value_check("vCenter management IP", "VCENTER_MANAGEMENT_IP", values.get("management_ip")),
        "subnet_cidr": _value_check("Subnet", "VCENTER_SUBNET_CIDR or active lab subnet", values.get("subnet_cidr")),
        "gateway": _value_check("Gateway", "VCENTER_GATEWAY or active lab gateway", values.get("gateway")),
        "dns_servers": _value_check("DNS servers", "VCENTER_DNS_SERVERS or active lab DNS", values.get("dns_servers")),
        "ntp_servers": _value_check("NTP servers", "VCENTER_NTP_SERVERS or active lab NTP", values.get("ntp_servers")),
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
        "evidence_artifacts": [_rel(path)] if path.exists() else [],
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
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (tuple, list)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _read_json_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _classify(
    *,
    netapp_stage: str,
    vcenter_host_configured: bool,
    vcenter_credentials_configured: bool,
    govc_available: bool,
    planned_nfs: dict[str, Any],
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
    missing_vcenter = []
    if not vcenter_host_configured:
        missing_vcenter.append("VCENTER_HOST/GOVC_URL")
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
        if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
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
    if explicit and explicit.exists() and explicit.is_file():
        return explicit
    path_tool = _tool_path("vcsa-deploy")
    if path_tool is not None:
        return path_tool
    for root in VCSA_MOUNT_ROOTS:
        candidate = root / "vcsa-cli-installer" / "lin64" / "vcsa-deploy"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


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
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload.get(key) if isinstance(payload, dict) else None


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
    neighbor_in_use = neighbor in {"REACHABLE", "STALE", "DELAY", "PROBE"}
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


def _missing_fields(vcenter_host: bool, vcenter_credentials: bool, netapp_credentials: bool) -> list[str]:
    missing = []
    if not vcenter_host:
        missing.extend(["VCENTER_HOST", "GOVC_URL"])
    if not vcenter_credentials:
        missing.extend(["VCENTER_USERNAME/GOVC_USERNAME", "VCENTER_PASSWORD/GOVC_PASSWORD"])
    if not netapp_credentials:
        missing.extend(["NETAPP_API_USERNAME", "NETAPP_API_PASSWORD"])
    return missing


def _message(status: str) -> str:
    if status == "ready":
        return "vCenter-NetApp readiness is ready for a future guarded datastore apply lane."
    if status == "not_configured_yet":
        return "vCenter/govc is not configured yet."
    return "vCenter-NetApp readiness is blocked by prior NetApp/ONTAP/NFS setup."


def _next_action(status: str) -> str:
    if status == "ready":
        return "Review the datastore command preview; keep apply disabled until a guarded apply workflow is implemented."
    if status == "not_configured_yet":
        return "Configure VCENTER_HOST/GOVC_URL, vCenter credentials, and govc, then rerun `make provider-lab-vcenter-netapp-readiness`."
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
    if explicit and explicit.exists() and explicit.is_file():
        return explicit
    roots = [Path(item).expanduser() for item in settings.media_inventory_dirs]
    roots.append(REPO_ROOT / "artifacts" / "Media")
    candidates: list[Path] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*.iso"):
            lowered = path.name.lower()
            if any(marker in lowered for marker in ("vcsa", "vcenter", "vmware-vc")):
                candidates.append(path)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: str(item).lower())[0]


def _safe_media_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


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
        f"- NTP: `{', '.join(values.get('ntp_servers') or []) or 'missing'}`",
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
    return str(path.relative_to(REPO_ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat()
