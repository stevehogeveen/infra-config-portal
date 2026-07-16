from __future__ import annotations

import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import paramiko

from app.core.config import settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.guarded_action_context import GuardedActionContext, guarded_confirmation, guarded_flag
from app.services.esxi_vm_deploy import _govc_binary, _govc_env, _run_govc
from app.services.json_file_store import write_json_object, write_text_value
from app.services.json_utils import parse_json_object
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.path_utils import repo_relative_path

REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
PREVIEW_REPORT = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-preview-report.md"
PREVIEW_JSON = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-preview-redacted.json"
APPLY_REPORT = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-apply-report.md"
APPLY_JSON = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-apply-redacted.json"
VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-validation-report.md"
VALIDATION_JSON = CODEX_RUN_DIR / "esxi-netapp-nfs-datastore-validation-redacted.json"

DATASTORE_CONFIRM_PHRASE = "MOUNT NETAPP NFS DATASTORE"
DATASTORE_ACCESS_MODE = "readWrite"


def build_esxi_netapp_datastore_preview(*, write_report: bool = True) -> dict[str, Any]:
    plan = _mount_plan()
    target = _target_state()
    current = _datastore_info(plan) if target["can_query"] else _skipped_datastore_info()
    command_preview = _command_preview(plan, target)
    blockers = _preview_blockers(plan, target, current)
    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-netapp-datastore-preview",
        "checked_at": _now(),
        "status": "blocked" if blockers else "preview_ready",
        "message": "NetApp NFS datastore mount preview generated. No ESXi, NetApp, or vCenter write action was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if current.get("checked") else "live_cached",
        "freshness": "current",
        "current_state": current,
        "target_state": _target_payload(plan, target),
        "required_flags": _required_flags(),
        "command_preview": command_preview,
        "blockers": blockers,
        "warnings": _warnings(),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(PREVIEW_REPORT),
            "json": _rel(PREVIEW_JSON),
            "apply_report": _rel(APPLY_REPORT),
            "validation_report": _rel(VALIDATION_REPORT),
        },
        "next_safe_action": (
            "Resolve ESXi/govc blockers, then run guarded datastore apply."
            if blockers
            else "Run guarded datastore apply if this mount target is correct."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(PREVIEW_JSON, PREVIEW_REPORT, sanitized, _markdown)
    return sanitized


def apply_esxi_netapp_datastore(
    *, write_report: bool = True, guarded_context: GuardedActionContext | None = None
) -> dict[str, Any]:
    plan = _mount_plan()
    target = _target_state()
    current = _datastore_info(plan) if target["can_query"] else _skipped_datastore_info()
    gates = _apply_gates(plan, target, current, guarded_context=guarded_context)
    apply_result = {
        "govc_datastore_create_attempted": False,
        "govc_datastore_remove_attempted": False,
        "return_code": None,
        "result": "not_attempted",
    }
    blockers = list(gates["blockers"])
    status = "blocked" if blockers else "ready_to_apply"
    message = (
        "NetApp datastore apply was refused before any govc datastore.create command."
        if blockers
        else "NetApp datastore apply gates passed; running guarded govc datastore.create."
    )

    if not blockers:
        if current.get("exists") and current.get("accessible") and _is_read_write(current):
            status = "ready"
            message = "NetApp NFS datastore is already mounted and accessible on ESXi."
            apply_result["result"] = "already_mounted"
        else:
            if current.get("exists") and not _is_read_write(current):
                if target.get("access_method") == "ssh":
                    remove_result = _ssh_remove_datastore(plan)
                else:
                    remove_result = _run_govc(
                        _govc_remove_args(plan, target.get("host_target")),
                        env=_govc_env(),
                        timeout=120,
                    )
                apply_result["govc_datastore_remove_attempted"] = True
                apply_result["remove_return_code"] = remove_result["return_code"]
                if remove_result["return_code"] != 0:
                    status = "failed"
                    message = "govc datastore.remove failed while remounting the NetApp NFS datastore read-write."
                    apply_result["return_code"] = remove_result["return_code"]
                    apply_result["result"] = "failed"
                    apply_result["stderr"] = remove_result.get("stderr")
                    blockers.append("govc datastore.remove failed.")

            if blockers:
                result = None
            else:
                if target.get("access_method") == "ssh":
                    result = _ssh_create_datastore(plan)
                    apply_result["apply_mechanism"] = "ssh-esxcli"
                else:
                    result = _run_govc(_govc_create_args(plan, target.get("host_target")), env=_govc_env(), timeout=120)
                    apply_result["apply_mechanism"] = "govc"
            if result is None:
                pass
            else:
                apply_result["govc_datastore_create_attempted"] = True
                apply_result["return_code"] = result["return_code"]
                apply_result["result"] = "completed" if result["return_code"] == 0 else "failed"
                apply_result["stderr"] = result.get("stderr")
                if result["return_code"] == 0:
                    after = _datastore_info(plan)
                    current = after
                    status = "mounted" if after.get("exists") else "warning"
                    message = "NetApp NFS datastore mount command completed."
                    if not after.get("exists"):
                        blockers.append("govc datastore.create returned success, but datastore.info did not confirm the datastore.")
                    if after.get("exists") and not _is_read_write(after):
                        status = "failed"
                        message = "NetApp NFS datastore mounted, but ESXi still reports it is not read-write."
                        blockers.append("Datastore is not mounted read-write.")
                else:
                    status = "failed"
                    message = "govc datastore.create failed."
                    blockers.append("govc datastore.create failed.")

    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-netapp-datastore-apply",
        "checked_at": _now(),
        "status": status,
        "message": message,
        "mode": settings.provider_mode,
        "apply_enabled": not gates["blockers"],
        "source_type": "live_probe" if current.get("checked") else "live_cached",
        "freshness": "current",
        "current_state": current,
        "target_state": _target_payload(plan, target),
        "flag_state": gates["flag_state"],
        "required_flags": _required_flags(),
        "command_preview": _command_preview(plan, target),
        "apply": apply_result,
        "blockers": unique_preserving_order(blockers),
        "warnings": _warnings(),
        "not_attempted": _not_attempted(apply_result.get("govc_datastore_create_attempted") is True),
        "artifacts": {
            "report": _rel(APPLY_REPORT),
            "json": _rel(APPLY_JSON),
            "validation_report": _rel(VALIDATION_REPORT),
        },
        "next_safe_action": (
            "Run datastore validation and then VM deployment preview."
            if status in {"mounted", "ready"}
            else "Restore ESXi management/govc access, then rerun datastore apply."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(APPLY_JSON, APPLY_REPORT, sanitized, _markdown)
    return sanitized


def validate_esxi_netapp_datastore(*, write_report: bool = True) -> dict[str, Any]:
    plan = _mount_plan()
    target = _target_state()
    current = _datastore_info(plan) if target["can_query"] else _skipped_datastore_info()
    blockers = []
    if not target["can_query"]:
        blockers.append(_target_blocker(target))
    if target["can_query"] and not current.get("exists"):
        blockers.append(f"Datastore `{plan['datastore_name']}` is not visible to ESXi govc.")
    if current.get("exists") and current.get("accessible") is False:
        blockers.append(f"Datastore `{plan['datastore_name']}` is visible but not accessible.")
    if current.get("exists") and not _is_read_write(current):
        blockers.append(f"Datastore `{plan['datastore_name']}` is mounted but not read-write.")
    payload = {
        "provider_id": "esxi-readonly",
        "action": "esxi-netapp-datastore-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "NetApp NFS datastore validation completed with read-only ESXi checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if current.get("checked") else "live_cached",
        "freshness": "current",
        "current_state": current,
        "target_state": _target_payload(plan, target),
        "blockers": unique_preserving_order(blockers),
        "warnings": _warnings(),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(VALIDATION_REPORT),
            "json": _rel(VALIDATION_JSON),
            "apply_report": _rel(APPLY_REPORT),
        },
        "next_safe_action": (
            "Deploy the selected OVF/OVA to the NetApp datastore."
            if not blockers
            else "Mount the NetApp NFS datastore after ESXi management is reachable."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(VALIDATION_JSON, VALIDATION_REPORT, sanitized, _markdown)
    return sanitized


def _mount_plan() -> dict[str, Any]:
    nfs_lifs = list(settings.netapp_nfs_lifs)
    remote_host = os.getenv("ESXI_NETAPP_DATASTORE_REMOTE_HOST") or (nfs_lifs[0] if nfs_lifs else None)
    return {
        "datastore_name": os.getenv("ESXI_NETAPP_DATASTORE_NAME") or settings.netapp_nfs_datastore_name,
        "remote_host": remote_host,
        "remote_path": os.getenv("ESXI_NETAPP_DATASTORE_REMOTE_PATH") or settings.netapp_nfs_mount_path,
        "nfs_version": os.getenv("ESXI_NETAPP_DATASTORE_NFS_VERSION", "nfs"),
        "vmknic": os.getenv("ESXI_NETAPP_DATASTORE_VMKNIC", "vmk0"),
        "netapp_nfs_lifs": nfs_lifs,
    }


def _target_state() -> dict[str, Any]:
    env = _govc_env()
    missing = []
    host_target = os.getenv("ESXI_NETAPP_DATASTORE_HOST_TARGET")
    if not settings.esxi_configured:
        missing.append("ESXI_CONFIGURED=true")
    if not env.get("GOVC_URL"):
        missing.append("GOVC_URL or ESXI_TEST_HOST")
    if not env.get("GOVC_USERNAME"):
        missing.append("GOVC_USERNAME or ESXI_TEST_USERNAME")
    if not env.get("GOVC_PASSWORD"):
        missing.append("GOVC_PASSWORD or ESXI_TEST_PASSWORD")
    govc = _govc_binary()
    if not govc:
        missing.append("govc")
    about = {"return_code": None, "stderr": None}
    if govc and not missing:
        about = _run_govc(["about"], env=env, timeout=15)
        if about["return_code"] != 0:
            missing.append(_govc_about_missing_field(about))
        else:
            host_target = host_target or _discover_host_target()
            if not host_target:
                missing.append("ESXi govc host target")
    ssh_target = _ssh_target_state()
    if not govc and ssh_target["can_query"]:
        missing = []
    return {
        "provider_mode": settings.provider_mode,
        "esxi_configured": settings.esxi_configured,
        "govc_available": bool(govc),
        "ssh_available": bool(ssh_target["can_query"]),
        "access_method": "govc" if bool(govc and not missing) else "ssh" if ssh_target["can_query"] else "none",
        "govc_url_configured": bool(env.get("GOVC_URL")),
        "username_configured": bool(env.get("GOVC_USERNAME")),
        "credential_configured": bool(env.get("GOVC_PASSWORD")),
        "ssh_target": ssh_target,
        "govc_about": about,
        "host_target": host_target,
        "host_target_configured": bool(host_target),
        "missing_fields": missing,
        "can_query": bool((govc and not missing) or ssh_target["can_query"]),
    }


def _govc_about_missing_field(about: dict[str, Any]) -> str:
    stderr = str(about.get("stderr") or "").lower()
    if "incorrect user name or password" in stderr or "login" in stderr:
        return "valid ESXi govc credentials"
    if "certificate" in stderr:
        return "trusted ESXi govc TLS settings"
    return "reachable ESXi govc endpoint"


def _discover_host_target() -> str | None:
    result = _run_govc(["host.info", "-json"], env=_govc_env(), timeout=30)
    if result.get("return_code") != 0:
        return None
    payload = _json_stdout_object(result.get("stdout"))
    if not payload:
        return None
    host_systems = payload.get("hostSystems") or payload.get("HostSystems") or []
    if not isinstance(host_systems, list) or not host_systems:
        return None
    first = host_systems[0]
    if not isinstance(first, dict):
        return None
    name = first.get("name") or first.get("Name")
    return str(name) if name else None


def _target_payload(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    payload = dict(plan)
    payload["esxi_host_target"] = target.get("host_target")
    payload["esxi_host_target_configured"] = bool(target.get("host_target"))
    payload["access_method"] = target.get("access_method")
    payload["ssh_available"] = target.get("ssh_available")
    return payload


def _datastore_info(plan: dict[str, Any]) -> dict[str, Any]:
    target = _target_state()
    if target.get("access_method") == "ssh":
        return _ssh_datastore_info(plan, target)
    result = _run_govc(["datastore.info", "-json", plan["datastore_name"]], env=_govc_env(), timeout=30)
    summary = _datastore_summary(result.get("stdout"))
    return {
        "checked": True,
        "exists": result["return_code"] == 0,
        "accessible": summary.get("accessible") if summary else None,
        "return_code": result["return_code"],
        "stderr": result.get("stderr"),
        "summary": summary,
    }


def _datastore_summary(stdout: str | None) -> dict[str, Any] | None:
    payload = _json_stdout_object(stdout)
    if not payload:
        return None
    datastores = payload.get("Datastores") or payload.get("datastores")
    if not isinstance(datastores, list) or not datastores:
        return None
    datastore = datastores[0]
    summary = (datastore.get("Summary") or datastore.get("summary")) if isinstance(datastore, dict) else None
    if not isinstance(summary, dict):
        return None
    host_mounts = datastore.get("host") or datastore.get("Host") or []
    mount_info = None
    if isinstance(host_mounts, list) and host_mounts:
        first_mount = host_mounts[0]
        if isinstance(first_mount, dict):
            mount_info = first_mount.get("mountInfo") or first_mount.get("MountInfo")
    return {
        "name": summary.get("Name") or summary.get("name"),
        "type": summary.get("Type") or summary.get("type"),
        "accessible": summary.get("Accessible") if "Accessible" in summary else summary.get("accessible"),
        "capacity": summary.get("Capacity") or summary.get("capacity"),
        "free_space": summary.get("FreeSpace") or summary.get("freeSpace"),
        "access_mode": mount_info.get("accessMode") if isinstance(mount_info, dict) else None,
    }


def _json_stdout_object(stdout: str | None) -> dict[str, Any]:
    return parse_json_object(stdout)


def _skipped_datastore_info() -> dict[str, Any]:
    return {
        "checked": False,
        "exists": False,
        "accessible": None,
        "return_code": None,
        "stderr": None,
        "summary": None,
    }


def _preview_blockers(plan: dict[str, Any], target: dict[str, Any], current: dict[str, Any]) -> list[str]:
    blockers = []
    if not plan["datastore_name"]:
        blockers.append("NETAPP_NFS_DATASTORE_NAME or ESXI_NETAPP_DATASTORE_NAME is required.")
    if not plan["remote_host"]:
        blockers.append("NETAPP_NFS_LIFS or ESXI_NETAPP_DATASTORE_REMOTE_HOST is required.")
    if not plan["remote_path"]:
        blockers.append("NETAPP_NFS_MOUNT_PATH or ESXI_NETAPP_DATASTORE_REMOTE_PATH is required.")
    if not target["can_query"]:
        blockers.append(_target_blocker(target))
    if current.get("exists") and current.get("accessible") is False:
        blockers.append(f"Datastore `{plan['datastore_name']}` exists but is not accessible.")
    return unique_preserving_order(blockers)


def _is_read_write(current: dict[str, Any]) -> bool:
    summary = current.get("summary") if isinstance(current.get("summary"), dict) else {}
    return summary.get("access_mode") == DATASTORE_ACCESS_MODE


def _target_blocker(target: dict[str, Any]) -> str:
    missing = _string_list(target.get("missing_fields"))
    if missing:
        return f"ESXi govc target is not ready: {', '.join(missing)}."
    return "ESXi govc target is not ready."


def _apply_gates(
    plan: dict[str, Any],
    target: dict[str, Any],
    current: dict[str, Any],
    *,
    guarded_context: GuardedActionContext | None = None,
) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "datastore_apply": guarded_flag(
            "ESXI_NETAPP_DATASTORE_APPLY", action_id="esxi.netapp-datastore-apply", context=guarded_context
        ),
        "datastore_confirm": guarded_confirmation(
            "ESXI_NETAPP_DATASTORE_CONFIRM", action_id="esxi.netapp-datastore-apply", context=guarded_context
        )
        == DATASTORE_CONFIRM_PHRASE,
    }
    blockers = _string_list(policy.action_blockers("esxi.datastore-vswitch-vmkernel", ActionCategory.STORAGE_CONFIG))
    blockers.extend(_preview_blockers(plan, target, current))
    if not flag_state["datastore_apply"]:
        blockers.append("ESXI_NETAPP_DATASTORE_APPLY=true is required.")
    if not flag_state["datastore_confirm"]:
        blockers.append(f'ESXI_NETAPP_DATASTORE_CONFIRM="{DATASTORE_CONFIRM_PHRASE}" is required.')
    return {"flag_state": flag_state, "blockers": unique_preserving_order(blockers)}


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _govc_create_args(plan: dict[str, Any], host_target: Any) -> list[str]:
    datastore_type = "-type"
    datastore_kind = "nfs41" if str(plan.get("nfs_version")).lower() == "nfs41" else "nfs"
    args = [
        "datastore.create",
        datastore_type,
        datastore_kind,
        "-name",
        plan["datastore_name"],
        "-remote-host",
        plan["remote_host"],
        "-remote-path",
        plan["remote_path"],
        "-mode",
        DATASTORE_ACCESS_MODE,
    ]
    if host_target:
        args.append(str(host_target))
    return args


def _ssh_target_state() -> dict[str, Any]:
    missing = []
    if not settings.esxi_configured:
        missing.append("ESXI_CONFIGURED=true")
    if not settings.esxi_test_host:
        missing.append("ESXI_TEST_HOST")
    if not settings.esxi_test_username:
        missing.append("ESXI_TEST_USERNAME")
    if not settings.esxi_test_password:
        missing.append("ESXI_TEST_PASSWORD")
    reachable = False
    if not missing and settings.esxi_test_host:
        reachable = _tcp_reachable(settings.esxi_test_host, 22)
        if not reachable:
            missing.append("ESXi SSH port 22")
    return {
        "host": settings.esxi_test_host,
        "username_configured": bool(settings.esxi_test_username),
        "credential_configured": bool(settings.esxi_test_password),
        "ssh_22_reachable": reachable,
        "missing_fields": missing,
        "can_query": not missing,
    }


def _tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3.0):
            return True
    except OSError:
        return False


def _run_esxi_ssh(command: str, *, timeout: int = 60) -> dict[str, Any]:
    if not (settings.esxi_test_host and settings.esxi_test_username and settings.esxi_test_password):
        return {"return_code": 255, "stdout": "", "stderr": "ESXi SSH credentials are not configured."}
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=settings.esxi_test_host,
            username=settings.esxi_test_username,
            password=settings.esxi_test_password,
            look_for_keys=False,
            allow_agent=False,
            timeout=12,
            banner_timeout=12,
            auth_timeout=12,
        )
        _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return {"return_code": stdout.channel.recv_exit_status(), "stdout": out, "stderr": err}
    except (OSError, paramiko.SSHException) as exc:
        return {"return_code": 255, "stdout": "", "stderr": f"{exc.__class__.__name__}: {exc}"}
    finally:
        client.close()


def _ssh_datastore_info(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    nfs_result = _run_esxi_ssh("esxcli storage nfs list", timeout=30)
    fs_result = _run_esxi_ssh("esxcli storage filesystem list", timeout=30)
    summary = _ssh_datastore_summary(plan["datastore_name"], nfs_result.get("stdout"), fs_result.get("stdout"))
    exists = summary is not None
    return {
        "checked": True,
        "exists": exists,
        "accessible": summary.get("accessible") if summary else None,
        "return_code": 0 if nfs_result["return_code"] == 0 and fs_result["return_code"] == 0 else 1,
        "stderr": "\n".join(_string_list([nfs_result.get("stderr"), fs_result.get("stderr")])) or None,
        "summary": summary,
        "access_method": "ssh-esxcli",
        "ssh_target": target.get("ssh_target"),
    }


def _ssh_datastore_summary(datastore_name: str, nfs_stdout: str | None, fs_stdout: str | None) -> dict[str, Any] | None:
    nfs_line = _line_for_name(nfs_stdout, datastore_name)
    fs_line = _filesystem_line_for_name(fs_stdout, datastore_name)
    if not nfs_line and not fs_line:
        return None
    nfs_parts = nfs_line.split() if nfs_line else []
    fs_parts = fs_line.split() if fs_line else []
    accessible = _parse_bool(nfs_parts[4]) if len(nfs_parts) > 4 else None
    read_only = _parse_bool(nfs_parts[8]) if len(nfs_parts) > 8 else None
    return {
        "name": datastore_name,
        "type": fs_parts[4] if len(fs_parts) > 4 else "NFS",
        "accessible": accessible,
        "capacity": _parse_int(fs_parts[5]) if len(fs_parts) > 5 else None,
        "free_space": _parse_int(fs_parts[6]) if len(fs_parts) > 6 else None,
        "access_mode": DATASTORE_ACCESS_MODE if read_only is False and accessible is True else "readOnly" if read_only else None,
        "remote_host": nfs_parts[1] if len(nfs_parts) > 1 else None,
        "remote_path": nfs_parts[2] if len(nfs_parts) > 2 else None,
        "vmknic": nfs_parts[3] if len(nfs_parts) > 3 else None,
        "mounted": _parse_bool(nfs_parts[5]) if len(nfs_parts) > 5 else None,
    }


def _line_for_name(stdout: str | None, name: str) -> str:
    for line in (stdout or "").splitlines():
        if line.split() and line.split()[0] == name:
            return line.strip()
    return ""


def _filesystem_line_for_name(stdout: str | None, name: str) -> str:
    for line in (stdout or "").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[1] == name:
            return line.strip()
    return ""


def _parse_bool(value: Any) -> bool | None:
    normalized = str(value).strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def _parse_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _ssh_create_datastore(plan: dict[str, Any]) -> dict[str, Any]:
    remote_host = str(plan.get("remote_host") or "")
    vmknic = str(plan.get("vmknic") or "vmk0")
    nfs_version = str(plan.get("nfs_version") or "nfs").lower()
    if nfs_version == "nfs41":
        command = (
            f"esxcli storage nfs41 add -I {remote_host}:{vmknic} "
            f"-s {plan['remote_path']} -v {plan['datastore_name']}"
        )
    else:
        command = (
            f"esxcli storage nfs add -I {remote_host}:{vmknic} "
            f"-s {plan['remote_path']} -v {plan['datastore_name']}"
        )
    result = _run_esxi_ssh(command, timeout=120)
    return {
        "return_code": result["return_code"],
        "stderr": result.get("stderr"),
        "stdout": result.get("stdout"),
        "command": command,
    }


def _ssh_remove_datastore(plan: dict[str, Any]) -> dict[str, Any]:
    command = f"esxcli storage nfs remove -v {plan['datastore_name']}"
    if str(plan.get("nfs_version") or "").lower() == "nfs41":
        command = f"esxcli storage nfs41 remove -v {plan['datastore_name']}"
    result = _run_esxi_ssh(command, timeout=120)
    return {
        "return_code": result["return_code"],
        "stderr": result.get("stderr"),
        "stdout": result.get("stdout"),
        "command": command,
    }


def _govc_remove_args(plan: dict[str, Any], host_target: Any) -> list[str]:
    args = ["datastore.remove", "-ds", plan["datastore_name"]]
    if host_target:
        args.append(str(host_target))
    return args


def _command_preview(plan: dict[str, Any], target: dict[str, Any]) -> list[str]:
    if target.get("access_method") == "ssh":
        host_vmk = f"{plan['remote_host']}:{plan.get('vmknic') or 'vmk0'}"
        add_command = " ".join(
            [
                "ssh",
                "<esxi>",
                "esxcli storage nfs add",
                "-I",
                host_vmk,
                "-s",
                plan["remote_path"],
                "-v",
                plan["datastore_name"],
            ]
        )
        if str(plan.get("nfs_version")).lower() == "nfs41":
            add_command = add_command.replace("storage nfs add", "storage nfs41 add")
        return [
            "ssh <esxi> esxcli storage nfs list",
            f"ssh <esxi> esxcli storage nfs remove -v {plan['datastore_name']} # only if existing mount is read-only/inaccessible",
            add_command,
            "ssh <esxi> esxcli storage filesystem list",
        ]
    return [
        f"govc datastore.info -json {plan['datastore_name']}",
        " ".join(["govc", *_govc_remove_args(plan, target.get("host_target") or "<esxi-host-target>"), "# only if existing mount is read-only"]),
        " ".join(["govc", *_govc_create_args(plan, target.get("host_target") or "<esxi-host-target>")]),
        f"govc datastore.info -json {plan['datastore_name']}",
    ]


def _required_flags() -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "ESXI_NETAPP_DATASTORE_APPLY=true",
        f'ESXI_NETAPP_DATASTORE_CONFIRM="{DATASTORE_CONFIRM_PHRASE}"',
    ]


def _warnings() -> list[str]:
    return [
        "Datastore apply runs govc datastore.create and may remount an existing read-only ESXi NFS mount; it does not delete NFS contents.",
        "NFS v3 is the default mount type for this lab workflow; set ESXI_NETAPP_DATASTORE_NFS_VERSION=nfs41 only after validation.",
    ]


def _not_attempted(apply_attempted: bool = False) -> list[str]:
    skipped = [
        "ONTAP volume/export changes",
        "vCenter operation",
        "VM deploy/power operation",
        "ESXi host reboot",
        "ESXi networking changes",
    ]
    if not apply_attempted:
        skipped.insert(0, "govc datastore.create")
        skipped.insert(1, "govc datastore.remove")
    return skipped


def _markdown(payload: dict[str, Any]) -> str:
    target = payload.get("target_state") or {}
    current = payload.get("current_state") or {}
    lines = [
        "# ESXi NetApp NFS Datastore Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Action: `{payload.get('action')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        "",
        "## Current State",
        f"- Checked: `{current.get('checked')}`",
        f"- Exists: `{current.get('exists')}`",
        f"- Accessible: `{current.get('accessible')}`",
        "",
        "## Target State",
        f"- Datastore: `{target.get('datastore_name')}`",
        f"- Remote host: `{target.get('remote_host')}`",
        f"- Remote path: `{target.get('remote_path')}`",
        "",
        "## Command Preview",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("command_preview") or [])
    lines.extend(["", "## Required Flags"])
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- No datastore, ESXi, NetApp, vCenter, or VM write is run unless apply gates pass."])
    lines.extend(["", "## Next Action", f"- {payload.get('next_safe_action')}"])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(json_path, payload)
    write_text_value(report_path, markdown_builder(payload))


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for key, value in os.environ.items()
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie"))
    ]


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()
