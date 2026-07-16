from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import paramiko

from app.core.config import settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive
from app.services.env_utils import env_flag as _env_flag
from app.services.guarded_action_context import GuardedActionContext, guarded_confirmation, guarded_flag
from app.services.json_file_store import write_json_object, write_text_value
from app.services.json_utils import parse_json_object
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.path_utils import (
    display_path,
    is_directory as _is_directory,
    is_file as _is_file,
    path_exists as _path_exists,
    repo_relative_path,
    rglob_paths,
)
from app.services.temp_file_utils import remove_file_best_effort

PROVIDER_ID = "esxi-readonly"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"
DEFAULT_MEDIA_ROOT = REPO_ROOT / "artifacts" / "Media"

VM_DEPLOY_CONFIRM_PHRASE = "DEPLOY ESXI OVF VM"
VM_DEPLOY_POWER_ON_CONFIRM_PHRASE = "POWER ON DEPLOYED VM"

PREVIEW_REPORT = CODEX_RUN_DIR / "esxi-vm-deploy-preview-report.md"
PREVIEW_JSON = CODEX_RUN_DIR / "esxi-vm-deploy-preview-redacted.json"
APPLY_REPORT = CODEX_RUN_DIR / "esxi-vm-deploy-apply-report.md"
APPLY_JSON = CODEX_RUN_DIR / "esxi-vm-deploy-apply-redacted.json"
VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-vm-deploy-validation-report.md"
VALIDATION_JSON = CODEX_RUN_DIR / "esxi-vm-deploy-validation-redacted.json"
IMPORT_OPTIONS_JSON = CODEX_RUN_DIR / "esxi-vm-deploy-import-options-redacted.json"
VM_INFO_JSON = CODEX_RUN_DIR / "esxi-vm-deploy-vm-info-redacted.json"
DATASTORE_INFO_JSON = CODEX_RUN_DIR / "esxi-vm-deploy-datastore-info-redacted.json"
INFLIGHT_LOCK_STALE_AFTER = timedelta(minutes=40)


def build_esxi_vm_deploy_preview(*, write_report: bool = True) -> dict[str, Any]:
    plan = _deployment_plan()
    target = _target_state()
    datastore = _datastore_info(plan, target) if target["can_query"] and plan["datastore"] else _skipped_datastore_info()
    blockers = _preview_blockers(plan, target, datastore)
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "vm-deploy-preview",
        "checked_at": _now(),
        "status": "blocked" if blockers else "preview_ready",
        "message": "Direct ESXi OVF deployment preview generated. No VM, datastore, network, or power action was run.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if datastore.get("checked") else "live_cached",
        "freshness": "current",
        "target": target,
        "deployment_plan": plan,
        "datastore_check": datastore,
        "required_flags": _required_flags(plan),
        "command_preview": _command_preview(plan),
        "blockers": blockers,
        "warnings": _warnings(plan),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(PREVIEW_REPORT),
            "json": _rel(PREVIEW_JSON),
        },
        "next_safe_action": (
            "Resolve blockers, rerun the preview, then apply only from an attended local-lab session."
            if blockers
            else "Review the command preview and set the explicit deploy flags only when ready."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(PREVIEW_JSON, PREVIEW_REPORT, sanitized, _markdown)
    return sanitized


def apply_esxi_vm_deploy(
    *, write_report: bool = True, guarded_context: GuardedActionContext | None = None
) -> dict[str, Any]:
    plan = _deployment_plan()
    target = _target_state()
    datastore = _datastore_info(plan, target) if target["can_query"] and plan["datastore"] else _skipped_datastore_info()
    gates = _apply_gates(plan, target, datastore, guarded_context=guarded_context)
    blocked = bool(gates["blockers"])
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "vm-deploy-apply",
        "checked_at": _now(),
        "status": "blocked" if blocked else "ready_to_apply",
        "message": (
            "Direct ESXi OVF deploy apply was refused before any govc import command."
            if blocked
            else "Direct ESXi OVF deploy gates passed; starting guarded govc import."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": not blocked,
        "source_type": "live_probe" if datastore.get("checked") else "live_cached",
        "freshness": "current",
        "target": target,
        "deployment_plan": plan,
        "datastore_check": datastore,
        "flag_state": gates["flag_state"],
        "required_flags": _required_flags(plan),
        "command_preview": _command_preview(plan),
        "apply": {
            "govc_import_spec_attempted": False,
            "govc_import_ovf_attempted": False,
            "vm_power_on_attempted": False,
            "vm_power_on_requested": plan["power_on"],
        },
        "blockers": gates["blockers"],
        "warnings": _warnings(plan),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(APPLY_REPORT),
            "json": _rel(APPLY_JSON),
            "import_options": _rel(IMPORT_OPTIONS_JSON),
            "vm_info": _rel(VM_INFO_JSON),
            "datastore_info": _rel(DATASTORE_INFO_JSON),
        },
        "next_safe_action": (
            "Resolve blockers and rerun `make provider-lab-esxi-vm-deploy-preview`."
            if blocked
            else "Validate the VM inventory and datastore placement after import."
        ),
    }

    if not blocked:
        lock_path = _inflight_lock_path(plan)
        lock_handle, stale_lock_warning = _try_acquire_inflight_lock(lock_path, plan)
        if lock_handle is None:
            blocker = (
                f"VM deploy is already in flight for `{plan['vm_name']}` on datastore `{plan['datastore']}`; "
                "wait for the current import to finish before retrying."
            )
            payload["status"] = "blocked"
            payload["message"] = "Direct ESXi OVF deploy apply was refused because an import is already in flight for this VM target."
            payload["apply_enabled"] = False
            payload["apply"]["in_flight_refused"] = True
            payload["blockers"] = _unique([*payload["blockers"], blocker])
            if stale_lock_warning:
                payload["warnings"].append(stale_lock_warning)
            payload["next_safe_action"] = "Wait for the current VM deploy run to finish, then validate VM inventory before retrying."
        else:
            try:
                result = _run_guarded_import(plan, target)
            finally:
                _release_inflight_lock(lock_handle, lock_path)
            payload["apply"] = result["apply"]
            payload["status"] = result["status"]
            payload["message"] = result["message"]
            payload["blockers"] = result["blockers"]
            payload["warnings"] = [*payload["warnings"], *result["warnings"]]
            if stale_lock_warning:
                payload["warnings"].append(stale_lock_warning)
            payload["not_attempted"] = _not_attempted(payload["apply"])

    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(APPLY_JSON, APPLY_REPORT, sanitized, _markdown)
    return sanitized


def validate_esxi_vm_deploy(*, write_report: bool = True) -> dict[str, Any]:
    plan = _deployment_plan()
    target = _target_state()
    datastore = _datastore_info(plan, target) if target["can_query"] and plan["datastore"] else _skipped_datastore_info()
    vm_info = _vm_info(plan, target) if target["can_query"] and plan["vm_name"] else _skipped_vm_info()
    blockers: list[str] = []
    if not datastore.get("exists"):
        blockers.append(f"Target datastore `{plan['datastore']}` is not visible to direct ESXi govc.")
    if not vm_info.get("exists"):
        blockers.append(f"VM `{plan['vm_name']}` is not visible to direct ESXi govc.")
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "vm-deploy-validation",
        "checked_at": _now(),
        "status": "blocked" if blockers else "ready",
        "message": "Direct ESXi VM deployment validation completed with read-only govc checks.",
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if target["can_query"] else "live_cached",
        "freshness": "current",
        "target": target,
        "deployment_plan": plan,
        "datastore_check": datastore,
        "vm_check": vm_info,
        "blockers": _unique(blockers),
        "warnings": _warnings(plan),
        "not_attempted": _not_attempted(),
        "artifacts": {
            "report": _rel(VALIDATION_REPORT),
            "json": _rel(VALIDATION_JSON),
            "vm_info": _rel(VM_INFO_JSON),
            "datastore_info": _rel(DATASTORE_INFO_JSON),
        },
        "next_safe_action": (
            "Deploy only after the target datastore is visible and guarded apply flags are present."
            if blockers
            else "Keep the VM powered off unless an operator explicitly enables power-on."
        ),
    }
    sanitized = _sanitize(payload)
    if write_report:
        _write_payload(VALIDATION_JSON, VALIDATION_REPORT, sanitized, _markdown)
    return sanitized


def _deployment_plan() -> dict[str, Any]:
    ovf_path = _resolve_ovf_path()
    datastore = os.getenv("VM_DEPLOY_DATASTORE") or settings.netapp_nfs_datastore_name
    network = os.getenv("VM_DEPLOY_NETWORK", "VM Network")
    vm_name = os.getenv("VM_DEPLOY_VM_NAME", "netapp-nfs-ovf-preview-vm")
    power_on = _env_flag("VM_DEPLOY_POWER_ON")
    return {
        "vm_name": vm_name,
        "ovf_path": _safe_path(ovf_path),
        "ovf_present": bool(ovf_path and _path_exists(ovf_path)),
        "datastore": datastore,
        "network": network,
        "disk_provisioning": os.getenv("VM_DEPLOY_DISK_PROVISIONING", "thin"),
        "power_on": power_on,
        "target_is_netapp_nfs": datastore == settings.netapp_nfs_datastore_name,
        "netapp_nfs_datastore": settings.netapp_nfs_datastore_name,
        "netapp_nfs_lif": settings.netapp_nfs_lifs[0] if settings.netapp_nfs_lifs else None,
        "netapp_nfs_mount_path": settings.netapp_nfs_mount_path,
    }


def _target_state() -> dict[str, Any]:
    govc = _govc_binary()
    env = _govc_env()
    missing = []
    if not env.get("GOVC_URL"):
        missing.append("GOVC_URL or ESXI_TEST_HOST")
    if not env.get("GOVC_USERNAME"):
        missing.append("GOVC_USERNAME or ESXI_TEST_USERNAME")
    if not env.get("GOVC_PASSWORD"):
        missing.append("GOVC_PASSWORD or ESXI_TEST_PASSWORD")
    govc_ready = bool(govc and not missing and settings.esxi_configured)
    ssh_target = _ssh_target_state()
    can_query = bool(govc_ready or ssh_target["can_query"])
    return {
        "provider_mode": settings.provider_mode,
        "esxi_configured": settings.esxi_configured,
        "esxi_host_configured": bool(settings.esxi_test_host),
        "govc_available": bool(govc),
        "ssh_available": bool(ssh_target["can_query"]),
        "access_method": "govc" if govc_ready else "ssh" if ssh_target["can_query"] else "none",
        "govc_url_configured": bool(env.get("GOVC_URL")),
        "username_configured": bool(env.get("GOVC_USERNAME")),
        "credential_configured": bool(env.get("GOVC_PASSWORD")),
        "ssh_target": ssh_target,
        "tls_verify": settings.esxi_test_verify_tls,
        "missing_fields": missing,
        "can_query": can_query,
    }


def _preview_blockers(plan: dict[str, Any], target: dict[str, Any], datastore: dict[str, Any]) -> list[str]:
    blockers = []
    if not plan["ovf_present"]:
        blockers.append("No OVF template was found under VM_DEPLOY_OVF_PATH, MEDIA_INVENTORY_DIRS, or artifacts/Media.")
    if not plan["datastore"]:
        blockers.append("VM_DEPLOY_DATASTORE or NETAPP_NFS_DATASTORE_NAME is required.")
    if not settings.esxi_configured:
        blockers.append("ESXI_CONFIGURED=true is required before direct ESXi VM deployment.")
    if not target["govc_available"] and target.get("access_method") != "ssh":
        blockers.append("govc is not installed or not on PATH.")
    missing_fields = _string_list(target.get("missing_fields"))
    if missing_fields:
        blockers.append(f"Direct ESXi govc target fields are missing: {', '.join(missing_fields)}.")
    if datastore.get("checked") and not datastore.get("exists"):
        blockers.append(f"Target datastore `{plan['datastore']}` is not visible to direct ESXi govc.")
    if plan["target_is_netapp_nfs"] and not datastore.get("exists"):
        blockers.append("NetApp NFS datastore is selected but is not mounted on ESXi yet.")
    return _unique(blockers)


def _apply_gates(
    plan: dict[str, Any],
    target: dict[str, Any],
    datastore: dict[str, Any],
    *,
    guarded_context: GuardedActionContext | None = None,
) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "vm_deploy_apply": guarded_flag(
            "VM_DEPLOY_APPLY", action_id="esxi.vm-deploy-apply", context=guarded_context
        ),
        "vm_deploy_confirm": guarded_confirmation(
            "VM_DEPLOY_CONFIRM", action_id="esxi.vm-deploy-apply", context=guarded_context
        )
        == VM_DEPLOY_CONFIRM_PHRASE,
        "vm_deploy_allow_create": guarded_flag(
            "VM_DEPLOY_ALLOW_CREATE", action_id="esxi.vm-deploy-apply", context=guarded_context
        ),
        "vm_deploy_power_on": plan["power_on"],
        "vm_deploy_power_on_confirm": os.getenv("VM_DEPLOY_POWER_ON_CONFIRM") == VM_DEPLOY_POWER_ON_CONFIRM_PHRASE,
    }
    blockers = []
    blockers.extend(_string_list(policy.action_blockers("vm.deploy-ovf", ActionCategory.VM_DEPLOY)))
    blockers.extend(_preview_blockers(plan, target, datastore))
    if not flag_state["vm_deploy_apply"]:
        blockers.append("VM_DEPLOY_APPLY=true is required.")
    if not flag_state["vm_deploy_confirm"]:
        blockers.append(f'VM_DEPLOY_CONFIRM="{VM_DEPLOY_CONFIRM_PHRASE}" is required.')
    if not flag_state["vm_deploy_allow_create"]:
        blockers.append("VM_DEPLOY_ALLOW_CREATE=true is required.")
    if plan["power_on"] and not flag_state["vm_deploy_power_on_confirm"]:
        blockers.append(f'VM_DEPLOY_POWER_ON_CONFIRM="{VM_DEPLOY_POWER_ON_CONFIRM_PHRASE}" is required when VM_DEPLOY_POWER_ON=true.')
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _run_guarded_import(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    ovf_path = _resolve_ovf_path()
    if ovf_path is None or not _path_exists(ovf_path):
        return {
            "status": "failed",
            "message": "Direct ESXi OVF deploy failed because the OVF template disappeared before apply.",
            "apply": {
                "govc_import_spec_attempted": False,
                "govc_import_ovf_attempted": False,
                "vm_power_on_attempted": False,
                "vm_power_on_requested": plan["power_on"],
            },
            "blockers": ["OVF template is not available at apply time."],
            "warnings": [],
        }
    env = _govc_env()
    import_spec = _run_govc(["import.spec", str(ovf_path)], env=env, timeout=120)
    apply_state = {
        "govc_import_spec_attempted": True,
        "govc_import_ovf_attempted": False,
        "vm_power_on_attempted": False,
        "vm_power_on_requested": plan["power_on"],
        "import_spec_return_code": import_spec["return_code"],
        "import_ovf_return_code": None,
    }
    warnings = []
    blockers = []
    if import_spec["return_code"] != 0:
        blockers.append("govc import.spec failed; OVF import was not attempted.")
        return {
            "status": "failed",
            "message": "Direct ESXi OVF deploy failed while generating import options.",
            "apply": apply_state,
            "blockers": blockers,
            "warnings": warnings,
        }

    options = _import_options(import_spec.get("stdout"), plan)
    write_json_object(IMPORT_OPTIONS_JSON, _sanitize(options))
    options_path = _write_temp_json(options, prefix="esxi-vm-deploy-options-")
    try:
        import_ovf = _run_govc(
            [
                "import.ovf",
                "-ds",
                plan["datastore"],
                "-name",
                plan["vm_name"],
                "-options",
                str(options_path),
                str(ovf_path),
            ],
            env=env,
            timeout=1800,
        )
    finally:
        remove_file_best_effort(options_path)

    apply_state["govc_import_ovf_attempted"] = True
    apply_state["import_ovf_return_code"] = import_ovf["return_code"]
    if import_ovf["return_code"] != 0:
        blockers.append("govc import.ovf failed.")
        return {
            "status": "failed",
            "message": "Direct ESXi OVF deploy failed during govc import.ovf.",
            "apply": apply_state,
            "blockers": blockers,
            "warnings": warnings,
        }

    vm_info = _vm_info(plan, target)
    if not vm_info.get("exists"):
        warnings.append("govc import.ovf returned success, but vm.info did not confirm the VM yet.")
    return {
        "status": "completed" if vm_info.get("exists") else "warning",
        "message": "Direct ESXi OVF deploy completed. The VM was left powered off unless explicitly requested.",
        "apply": apply_state,
        "blockers": blockers,
        "warnings": warnings,
    }


def _inflight_lock_path(plan: dict[str, Any]) -> Path:
    key = f"{plan.get('vm_name') or 'vm'}-{plan.get('datastore') or 'datastore'}"
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", key).strip("-")[:96] or "vm-deploy"
    return CODEX_RUN_DIR / f"esxi-vm-deploy-inflight-{slug}.lock"


def _try_acquire_inflight_lock(lock_path: Path, plan: dict[str, Any]) -> tuple[Any | None, str | None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stale_warning = None
    for attempt in range(2):
        try:
            handle = lock_path.open("x", encoding="utf-8")
            break
        except FileExistsError:
            if attempt == 0:
                cleared, warning = _clear_stale_inflight_lock(lock_path)
                stale_warning = warning
                if cleared:
                    continue
            return None, stale_warning
    try:
        json.dump(
            _sanitize(
                {
                    "started_at": _now(),
                    "pid": os.getpid(),
                    "vm_name": plan.get("vm_name"),
                    "datastore": plan.get("datastore"),
                    "ovf_path": plan.get("ovf_path"),
                }
            ),
            handle,
        )
        handle.flush()
        return handle, stale_warning
    except Exception:
        handle.close()
        remove_file_best_effort(lock_path)
        raise


def _clear_stale_inflight_lock(lock_path: Path) -> tuple[bool, str | None]:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    if not isinstance(payload, dict):
        return False, None
    started_at = _parse_timestamp(str(payload.get("started_at") or ""))
    if started_at is None:
        return False, None
    if datetime.now(UTC) - started_at <= INFLIGHT_LOCK_STALE_AFTER:
        return False, None
    pid = _int_or_none(payload.get("pid"))
    if pid is None or _process_is_running(pid):
        return (
            False,
            "A VM deploy in-flight lock is older than 40 minutes, but the owning backend process could not be proven stopped; refusing a concurrent import.",
        )
    remove_file_best_effort(lock_path)
    return True, "A stale VM deploy in-flight lock older than 40 minutes was cleared because its backend process is no longer running."


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return True
        if completed.returncode != 0:
            return True
        return f'"{pid}"' in completed.stdout or f",{pid}," in completed.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _release_inflight_lock(lock_handle: Any, lock_path: Path) -> None:
    try:
        lock_handle.close()
    finally:
        remove_file_best_effort(lock_path)


def _import_options(stdout: str | None, plan: dict[str, Any]) -> dict[str, Any]:
    options = _json_stdout_object(stdout)
    options["Name"] = plan["vm_name"]
    options["DiskProvisioning"] = plan["disk_provisioning"]
    options["PowerOn"] = plan["power_on"]
    network_mappings = options.get("NetworkMapping")
    if isinstance(network_mappings, list) and network_mappings:
        options["NetworkMapping"] = [
            {**mapping, "Network": plan["network"]}
            if isinstance(mapping, dict)
            else mapping
            for mapping in network_mappings
        ]
    else:
        options["NetworkMapping"] = [{"Name": plan["network"], "Network": plan["network"]}]
    return options


def _datastore_info(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    if target.get("access_method") == "ssh":
        return _ssh_datastore_info(plan, target)
    result = _run_govc(["datastore.info", "-json", plan["datastore"]], env=_govc_env(), timeout=30)
    info = {
        "checked": True,
        "exists": result["return_code"] == 0,
        "return_code": result["return_code"],
        "stderr": result["stderr"],
        "summary": _datastore_summary(result["stdout"]),
    }
    write_json_object(DATASTORE_INFO_JSON, _sanitize(info))
    return info


def _vm_info(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    if target.get("access_method") == "ssh":
        return _ssh_vm_info(plan, target)
    result = _run_govc(["vm.info", "-json", plan["vm_name"]], env=_govc_env(), timeout=30)
    info = {
        "checked": True,
        "exists": result["return_code"] == 0,
        "return_code": result["return_code"],
        "stderr": result["stderr"],
        "summary": _vm_summary(result["stdout"]),
    }
    write_json_object(VM_INFO_JSON, _sanitize(info))
    return info


def _run_govc(args: list[str], *, env: dict[str, str], timeout: int) -> dict[str, Any]:
    govc = _govc_binary()
    if govc is None:
        return {"return_code": 127, "stdout": "", "stderr": "govc executable was not found."}
    try:
        completed = subprocess.run(
            [govc, *args],
            capture_output=True,
            check=False,
            env=env,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return {"return_code": 127, "stdout": "", "stderr": "govc executable was not found."}
    except subprocess.TimeoutExpired:
        return {"return_code": 124, "stdout": "", "stderr": "govc command timed out."}
    return _sanitize(
        {
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    )


def _govc_binary() -> str | None:
    from shutil import which

    found = which("govc")
    if found:
        return found
    for directory in (Path(sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        for executable in ("govc.exe", "govc"):
            candidate = directory / executable
            if _is_file(candidate):
                return str(candidate)
    return None


def _govc_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GOVC_URL", f"https://{settings.esxi_test_host}/sdk" if settings.esxi_test_host else "")
    env.setdefault("GOVC_USERNAME", settings.esxi_test_username or "")
    env.setdefault("GOVC_PASSWORD", settings.esxi_test_password or "")
    if "GOVC_INSECURE" not in env:
        env["GOVC_INSECURE"] = "false" if settings.esxi_test_verify_tls else "true"
    return env


def _resolve_ovf_path() -> Path | None:
    configured = os.getenv("VM_DEPLOY_OVF_PATH")
    if configured:
        path = Path(configured).expanduser()
        return path if _path_exists(path) else path
    roots = [Path(item).expanduser() for item in settings.media_inventory_dirs]
    roots.append(DEFAULT_MEDIA_ROOT)
    for root in roots:
        if not _is_directory(root):
            continue
        matches = sorted(rglob_paths(root, "*.ovf"), key=lambda item: str(item).lower())
        if matches:
            return matches[0]
    return None


def _datastore_summary(stdout: str | None) -> dict[str, Any] | None:
    payload = _json_stdout_object(stdout)
    if not payload:
        return None
    datastores = payload.get("Datastores")
    if not isinstance(datastores, list) or not datastores:
        return None
    summary = datastores[0].get("Summary") if isinstance(datastores[0], dict) else None
    if not isinstance(summary, dict):
        return None
    return {
        "name": summary.get("Name"),
        "type": summary.get("Type"),
        "accessible": summary.get("Accessible"),
        "capacity": summary.get("Capacity"),
        "free_space": summary.get("FreeSpace"),
    }


def _vm_summary(stdout: str | None) -> dict[str, Any] | None:
    payload = _json_stdout_object(stdout)
    if not payload:
        return None
    virtual_machines = payload.get("VirtualMachines")
    if not isinstance(virtual_machines, list) or not virtual_machines:
        return None
    vm = virtual_machines[0]
    if not isinstance(vm, dict):
        return None
    summary = vm.get("Summary") if isinstance(vm.get("Summary"), dict) else {}
    runtime = summary.get("Runtime") if isinstance(summary.get("Runtime"), dict) else {}
    config = summary.get("Config") if isinstance(summary.get("Config"), dict) else {}
    return {
        "name": config.get("Name"),
        "path": vm.get("InventoryPath"),
        "power_state": runtime.get("PowerState"),
        "guest": config.get("GuestFullName"),
    }


def _json_stdout_object(stdout: str | None) -> dict[str, Any]:
    return parse_json_object(stdout)


def _skipped_datastore_info() -> dict[str, Any]:
    return {"checked": False, "exists": False, "return_code": None, "stderr": None, "summary": None}


def _skipped_vm_info() -> dict[str, Any]:
    return {"checked": False, "exists": False, "return_code": None, "stderr": None, "summary": None}


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


def _run_esxi_ssh(command: str, *, timeout: int = 30) -> dict[str, Any]:
    if not (settings.esxi_test_host and settings.esxi_test_username and settings.esxi_test_password):
        return {"return_code": 255, "stdout": "", "stderr": "ESXi SSH credentials are not configured."}
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=settings.esxi_test_host,
            username=settings.esxi_test_username,
            password=settings.esxi_test_password,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        stdout_text = stdout.read().decode(errors="replace")
        stderr_text = stderr.read().decode(errors="replace")
        return_code = stdout.channel.recv_exit_status()
        return {"return_code": return_code, "stdout": stdout_text, "stderr": stderr_text}
    except Exception as exc:
        return {"return_code": 255, "stdout": "", "stderr": f"{exc.__class__.__name__}: {exc}"}
    finally:
        client.close()


def _ssh_datastore_info(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    result = _run_esxi_ssh("esxcli storage nfs list", timeout=30)
    summary = _ssh_datastore_summary(result.get("stdout"), plan["datastore"])
    info = {
        "checked": result["return_code"] == 0,
        "exists": bool(summary),
        "return_code": result["return_code"],
        "stderr": result.get("stderr"),
        "summary": summary,
        "access_method": "ssh-esxcli",
        "ssh_target": target.get("ssh_target"),
    }
    write_json_object(DATASTORE_INFO_JSON, _sanitize(info))
    return info


def _ssh_datastore_summary(stdout: Any, datastore_name: str) -> dict[str, Any] | None:
    for line in str(stdout or "").splitlines():
        if not line.strip() or line.lower().startswith("volume name"):
            continue
        columns = line.split()
        if columns and columns[0] == datastore_name:
            return {
                "name": columns[0],
                "remote_host": columns[1] if len(columns) > 1 else None,
                "remote_path": columns[2] if len(columns) > 2 else None,
                "accessible": True,
                "mounted": True,
                "type": "NFS",
            }
    return None


def _ssh_vm_info(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    result = _run_esxi_ssh("vim-cmd vmsvc/getallvms", timeout=30)
    exists = _ssh_vm_exists(result.get("stdout"), plan["vm_name"])
    info = {
        "checked": result["return_code"] == 0,
        "exists": exists,
        "return_code": result["return_code"],
        "stderr": result.get("stderr"),
        "summary": {"name": plan["vm_name"], "access_method": "ssh-vim-cmd"} if exists else None,
        "access_method": "ssh-vim-cmd",
        "ssh_target": target.get("ssh_target"),
    }
    write_json_object(VM_INFO_JSON, _sanitize(info))
    return info


def _ssh_vm_exists(stdout: Any, vm_name: str) -> bool:
    return any(vm_name in line.split() for line in str(stdout or "").splitlines())


def _required_flags(plan: dict[str, Any]) -> list[str]:
    flags = [
        "PROVIDER_MODE=local-lab-readwrite",
        "VM_DEPLOY_APPLY=true",
        f'VM_DEPLOY_CONFIRM="{VM_DEPLOY_CONFIRM_PHRASE}"',
        "VM_DEPLOY_ALLOW_CREATE=true",
    ]
    if plan["power_on"]:
        flags.append(f'VM_DEPLOY_POWER_ON_CONFIRM="{VM_DEPLOY_POWER_ON_CONFIRM_PHRASE}"')
    return flags


def _command_preview(plan: dict[str, Any]) -> list[str]:
    ovf_path = plan["ovf_path"] or "<ovf-path>"
    return [
        f"govc datastore.info -json {plan['datastore']}",
        f"govc import.spec {ovf_path}",
        f"govc import.ovf -ds {plan['datastore']} -name {plan['vm_name']} -options <generated-options.json> {ovf_path}",
        f"govc vm.info -json {plan['vm_name']}",
    ]


def _warnings(plan: dict[str, Any]) -> list[str]:
    warnings = [
        "Preview and validation use read-only govc checks; apply requires explicit deploy flags.",
        "The VM is left powered off unless VM_DEPLOY_POWER_ON=true and its separate confirmation are provided.",
    ]
    if plan["target_is_netapp_nfs"]:
        warnings.append("Selected datastore is the NetApp NFS datastore; deployment waits until ESXi can see it.")
    return warnings


def _not_attempted(apply_state: dict[str, Any] | None = None) -> list[str]:
    apply_state = apply_state or {}
    not_attempted = [
        "VM import/create",
        "VM power on",
        "VM delete",
        "datastore add/remove",
        "network reconfiguration",
        "ESXi host reconfiguration",
        "vCenter operation",
    ]
    if apply_state.get("govc_import_ovf_attempted"):
        not_attempted.remove("VM import/create")
    if apply_state.get("vm_power_on_attempted"):
        not_attempted.remove("VM power on")
    return not_attempted


def _markdown(payload: dict[str, Any]) -> str:
    plan = payload.get("deployment_plan") or {}
    target = payload.get("target") or {}
    datastore = payload.get("datastore_check") or {}
    lines = [
        f"# ESXi VM Deploy {str(payload.get('action', '')).title().replace('-', ' ')} Report",
        "",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Apply enabled: `{payload.get('apply_enabled')}`",
        f"- Provider mode: `{payload.get('mode')}`",
        f"- ESXi configured: `{target.get('esxi_configured')}`",
        f"- govc available: `{target.get('govc_available')}`",
        f"- Target datastore visible: `{datastore.get('exists')}`",
        "",
        "## Deployment Plan",
        f"- VM name: `{plan.get('vm_name')}`",
        f"- OVF path: `{plan.get('ovf_path')}`",
        f"- Datastore: `{plan.get('datastore')}`",
        f"- Network: `{plan.get('network')}`",
        f"- Disk provisioning: `{plan.get('disk_provisioning')}`",
        f"- Power on: `{plan.get('power_on')}`",
        "",
        "## Command Preview",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("command_preview") or [])
    lines.extend(["", "## Required Flags"])
    lines.extend(f"- `{item}`" for item in payload.get("required_flags") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(["", "## Safety", "- No VM, datastore, network, host, vCenter, or power write action is run unless apply gates pass."])
    return "\n".join(lines) + "\n"


def _write_payload(json_path: Path, report_path: Path, payload: dict[str, Any], markdown_builder: Any) -> None:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    write_json_object(json_path, payload)
    write_text_value(report_path, markdown_builder(payload))


def _write_temp_json(payload: Any, *, prefix: str) -> Path:
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=CODEX_RUN_DIR,
        encoding="utf-8",
        prefix=prefix[:48],
        suffix=".json",
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        return Path(handle.name)


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for key, value in os.environ.items()
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie"))
    ]


def _safe_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return display_path(path.resolve(), REPO_ROOT)


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _unique(values: list[Any]) -> list[Any]:
    return unique_preserving_order(values, skip_falsey=True)
