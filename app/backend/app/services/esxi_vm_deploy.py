from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.providers.action_policy import ActionCategory, LOCAL_LAB_READWRITE_MODE, current_lab_action_policy
from app.providers.redaction import redact_sensitive

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


def apply_esxi_vm_deploy(*, write_report: bool = True) -> dict[str, Any]:
    plan = _deployment_plan()
    target = _target_state()
    datastore = _datastore_info(plan, target) if target["can_query"] and plan["datastore"] else _skipped_datastore_info()
    gates = _apply_gates(plan, target, datastore)
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
        result = _run_guarded_import(plan, target)
        payload["apply"] = result["apply"]
        payload["status"] = result["status"]
        payload["message"] = result["message"]
        payload["blockers"] = result["blockers"]
        payload["warnings"] = [*payload["warnings"], *result["warnings"]]

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
    power_on = os.getenv("VM_DEPLOY_POWER_ON", "").strip().lower() in {"1", "true", "yes", "on"}
    return {
        "vm_name": vm_name,
        "ovf_path": _safe_path(ovf_path),
        "ovf_present": bool(ovf_path and ovf_path.exists()),
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
    can_query = bool(govc and not missing and settings.esxi_configured)
    return {
        "provider_mode": settings.provider_mode,
        "esxi_configured": settings.esxi_configured,
        "esxi_host_configured": bool(settings.esxi_test_host),
        "govc_available": bool(govc),
        "govc_url_configured": bool(env.get("GOVC_URL")),
        "username_configured": bool(env.get("GOVC_USERNAME")),
        "credential_configured": bool(env.get("GOVC_PASSWORD")),
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
    if not target["govc_available"]:
        blockers.append("govc is not installed or not on PATH.")
    if target["missing_fields"]:
        blockers.append(f"Direct ESXi govc target fields are missing: {', '.join(target['missing_fields'])}.")
    if datastore.get("checked") and not datastore.get("exists"):
        blockers.append(f"Target datastore `{plan['datastore']}` is not visible to direct ESXi govc.")
    if plan["target_is_netapp_nfs"] and not datastore.get("exists"):
        blockers.append("NetApp NFS datastore is selected but is not mounted on ESXi yet.")
    return _unique(blockers)


def _apply_gates(plan: dict[str, Any], target: dict[str, Any], datastore: dict[str, Any]) -> dict[str, Any]:
    policy = current_lab_action_policy(settings.provider_mode)
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "vm_deploy_apply": os.getenv("VM_DEPLOY_APPLY") == "true",
        "vm_deploy_confirm": os.getenv("VM_DEPLOY_CONFIRM") == VM_DEPLOY_CONFIRM_PHRASE,
        "vm_deploy_allow_create": os.getenv("VM_DEPLOY_ALLOW_CREATE") == "true",
        "vm_deploy_power_on": plan["power_on"],
        "vm_deploy_power_on_confirm": os.getenv("VM_DEPLOY_POWER_ON_CONFIRM") == VM_DEPLOY_POWER_ON_CONFIRM_PHRASE,
    }
    blockers = []
    blockers.extend(policy.action_blockers("vm.deploy-ovf", ActionCategory.VM_DEPLOY))
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
    if ovf_path is None or not ovf_path.exists():
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
    IMPORT_OPTIONS_JSON.write_text(json.dumps(_sanitize(options), indent=2) + "\n", encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(options, handle, indent=2)
        options_path = Path(handle.name)
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
        try:
            options_path.unlink()
        except OSError:
            pass

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


def _import_options(stdout: str | None, plan: dict[str, Any]) -> dict[str, Any]:
    try:
        options = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        options = {}
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
    result = _run_govc(["datastore.info", "-json", plan["datastore"]], env=_govc_env(), timeout=30)
    info = {
        "checked": True,
        "exists": result["return_code"] == 0,
        "return_code": result["return_code"],
        "stderr": result["stderr"],
        "summary": _datastore_summary(result["stdout"]),
    }
    DATASTORE_INFO_JSON.write_text(json.dumps(_sanitize(info), indent=2) + "\n", encoding="utf-8")
    return info


def _vm_info(plan: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    result = _run_govc(["vm.info", "-json", plan["vm_name"]], env=_govc_env(), timeout=30)
    info = {
        "checked": True,
        "exists": result["return_code"] == 0,
        "return_code": result["return_code"],
        "stderr": result["stderr"],
        "summary": _vm_summary(result["stdout"]),
    }
    VM_INFO_JSON.write_text(json.dumps(_sanitize(info), indent=2) + "\n", encoding="utf-8")
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
        candidate = directory / "govc"
        if candidate.exists() and candidate.is_file():
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
        return path if path.exists() else path
    roots = [Path(item).expanduser() for item in settings.media_inventory_dirs]
    roots.append(DEFAULT_MEDIA_ROOT)
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        matches = sorted(root.rglob("*.ovf"), key=lambda item: str(item).lower())
        if matches:
            return matches[0]
    return None


def _datastore_summary(stdout: str | None) -> dict[str, Any] | None:
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    datastores = payload.get("Datastores") if isinstance(payload, dict) else None
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
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    virtual_machines = payload.get("VirtualMachines") if isinstance(payload, dict) else None
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


def _skipped_datastore_info() -> dict[str, Any]:
    return {"checked": False, "exists": False, "return_code": None, "stderr": None, "summary": None}


def _skipped_vm_info() -> dict[str, Any]:
    return {"checked": False, "exists": False, "return_code": None, "stderr": None, "summary": None}


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


def _not_attempted() -> list[str]:
    return [
        "VM import/create",
        "VM power on",
        "VM delete",
        "datastore add/remove",
        "network reconfiguration",
        "ESXi host reconfiguration",
        "vCenter operation",
    ]


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
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(markdown_builder(payload), encoding="utf-8")


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
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
