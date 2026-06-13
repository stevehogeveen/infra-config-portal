from __future__ import annotations

import json
import socket
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
VCENTER_INSTALL_READINESS_JSON = CODEX_RUN_DIR / "vcenter-install-readiness-redacted.json"
VCENTER_INSTALL_PLAN_JSON = CODEX_RUN_DIR / "vcenter-install-plan-redacted.json"
CONSOLE_STATE_JSON = CODEX_RUN_DIR / "netapp-console-state-redacted.json"
CONSOLE_LOGIN_STATE_JSON = CODEX_RUN_DIR / "netapp-console-login-state-redacted.json"


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
    features = profile_context.get("enabled_features") or {}
    plan = profile_context.get("resolved_address_plan") or {}
    vcsa_iso = _find_vcsa_iso()
    esxi_host = settings.esxi_test_host or LAB_ESXI_MANAGEMENT_IP
    datastore_name = settings.netapp_nfs_datastore_name
    vcenter_host_configured = bool(settings.vcenter_host or settings.vcenter_configured)
    vcenter_credentials_configured = bool(settings.vcenter_username and settings.vcenter_password)
    govc_available = _tool_available("govc")
    vcsa_deploy_available = _tool_available("vcsa-deploy")
    vcenter_enabled = bool(features.get("vcenter_enabled", True))
    checks = {
        "vcenter_in_scope": _config_check(
            "vCenter in scope",
            vcenter_enabled,
            "vCenter is enabled by the active lab profile.",
            "vCenter is disabled by the active lab profile.",
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
        "govc_available": _config_check(
            "govc",
            govc_available,
            "govc is available.",
            "govc is not installed or not discoverable.",
        ),
        "vcsa_deploy_available": _config_check(
            "vcsa-deploy",
            vcsa_deploy_available,
            "vcsa-deploy is available.",
            "vcsa-deploy is not installed or not discoverable.",
        ),
        "vcenter_target_configured": _config_check(
            "vCenter target",
            vcenter_host_configured,
            "vCenter target is configured.",
            "VCENTER_HOST/GOVC_URL is not configured.",
        ),
        "vcenter_credentials_configured": _config_check(
            "vCenter credentials",
            vcenter_credentials_configured,
            "vCenter credential fields are configured.",
            "VCENTER_USERNAME/GOVC_USERNAME and VCENTER_PASSWORD/GOVC_PASSWORD are missing.",
        ),
    }
    blockers = []
    if not vcenter_enabled:
        blockers.append("vCenter is disabled by the active lab profile.")
    if not vcsa_iso:
        blockers.append("VCSA ISO media was not found under the configured media roots.")
    if checks["esxi_management_reachable"]["status"] != "ready":
        blockers.append("ESXi management must be reachable before vCenter install planning can proceed.")
    if checks["netapp_nfs_lif_reachable"]["status"] != "ready":
        blockers.append("NetApp NFS LIF must be reachable before vCenter install planning can proceed.")
    if not govc_available:
        blockers.append("govc is required for target datastore/ESXi validation.")
    if not vcsa_deploy_available:
        blockers.append("vcsa-deploy is required before guided VCSA install can run.")
    if not vcenter_host_configured:
        blockers.append("vCenter target values are missing.")
    if not vcenter_credentials_configured:
        blockers.append("vCenter credential values are missing.")
    payload = {
        "provider_id": "vcenter",
        "action": "vcenter-install-readiness",
        "checked_at": generated_at,
        "generated_at": generated_at,
        "status": "blocked" if blockers else "ready",
        "message": "vCenter install readiness evaluated. No vCenter deployment was started.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if check_ports else "live_cached",
        "freshness": "current" if check_ports else "not_checked",
        "current_state": {
            "vcenter_installed": vcenter_host_configured,
            "esxi_management": esxi_host,
            "netapp_datastore": datastore_name,
            "vcsa_iso": _safe_media_path(vcsa_iso),
        },
        "target_state": {
            "vcenter": _redacted_url(settings.vcenter_host),
            "deployment_target": esxi_host,
            "datastore": datastore_name,
            "lab_network": plan.get("subnet") if isinstance(plan, dict) else None,
        },
        "checks": checks,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": [
            "Install apply is intentionally disabled; this report only prepares the guided deployment lane.",
            "vCenter must wait until ESXi management and the NetApp datastore are ready.",
        ],
        "not_attempted": [
            "VCSA deploy install",
            "vCenter appliance power operation",
            "ESXi datastore mount",
            "vCenter configuration write",
        ],
        "artifacts": {
            "readiness_report": _rel(VCENTER_INSTALL_READINESS_REPORT),
            "plan_report": _rel(VCENTER_INSTALL_PLAN_REPORT),
            "readiness_json": _rel(VCENTER_INSTALL_READINESS_JSON),
        },
        "next_safe_action": (
            "Generate the vCenter install plan after readiness is ready."
            if not blockers
            else "Restore ESXi management, mount the NetApp datastore, and configure missing vCenter values."
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
    plan = {
        **readiness,
        "action": "vcenter-install-plan",
        "message": "vCenter install plan generated. Preview only; no install was started.",
        "install_plan": {
            "vcsa_iso": (readiness.get("current_state") or {}).get("vcsa_iso"),
            "deployment_target": (readiness.get("target_state") or {}).get("deployment_target"),
            "datastore": (readiness.get("target_state") or {}).get("datastore"),
            "command_preview": [
                "Mount VCSA ISO locally.",
                "Generate redacted VCSA deployment JSON from active lab profile.",
                "vcsa-deploy install --accept-eula --acknowledge-ceip <redacted-vcsa-plan.json>",
            ],
        },
        "artifacts": {
            **(readiness.get("artifacts") or {}),
            "plan_report": _rel(VCENTER_INSTALL_PLAN_REPORT),
            "plan_json": _rel(VCENTER_INSTALL_PLAN_JSON),
        },
    }
    sanitized = redact_sensitive(plan)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        VCENTER_INSTALL_PLAN_JSON.write_text(json.dumps(sanitized, indent=2) + "\n", encoding="utf-8")
        VCENTER_INSTALL_PLAN_REPORT.write_text(_vcenter_install_markdown(sanitized), encoding="utf-8")
    return sanitized


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
    if which(name) is not None:
        return True
    for directory in (Path(sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        candidate = directory / name
        if candidate.exists() and candidate.is_file():
            return True
    return False


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
        "source_type": "live_cached",
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
        }
    if not check_ports:
        return {
            "label": label,
            "host": host,
            "port": port,
            "status": "not_checked",
            "detail": "Reachability not checked in this read.",
            "source_type": "not_checked",
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
            "source_type": "live_probe",
        }
    return {
        "label": label,
        "host": host,
        "port": port,
        "status": "ready" if reachable else "blocked",
        "detail": f"TCP {port} reachable.",
        "source_type": "live_probe",
    }


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


def _vcenter_install_markdown(payload: dict[str, Any]) -> str:
    current = payload.get("current_state") or {}
    target = payload.get("target_state") or {}
    install_plan = payload.get("install_plan") or {}
    lines = [
        "# vCenter Install Readiness Report" if payload.get("action") == "vcenter-install-readiness" else "# vCenter Install Plan Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Action: `{payload.get('action')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Current State",
        f"- VCSA ISO: `{current.get('vcsa_iso') or 'not found'}`",
        f"- ESXi management: `{current.get('esxi_management')}`",
        f"- NetApp datastore: `{current.get('netapp_datastore')}`",
        f"- vCenter installed/configured: `{current.get('vcenter_installed')}`",
        "",
        "## Target State",
        f"- vCenter: `{target.get('vcenter') or 'not configured'}`",
        f"- Deployment target: `{target.get('deployment_target')}`",
        f"- Datastore: `{target.get('datastore')}`",
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
