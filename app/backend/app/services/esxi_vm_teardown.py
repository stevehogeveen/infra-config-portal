from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.core.config import settings
from app.providers.action_policy import (
    ActionCategory,
    LOCAL_LAB_READWRITE_MODE,
    MOCK_MODE,
    current_lab_action_policy,
)
from app.providers.redaction import redact_sensitive
from app.services.guarded_action_context import (
    GuardedActionContext,
    guarded_confirmation,
    guarded_flag,
    guarded_value,
)
from app.services.json_file_store import write_json_object, write_text_value
from app.services.json_utils import parse_json_object
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.path_utils import is_file as _is_file
from app.services.path_utils import repo_relative_path

PROVIDER_ID = "esxi-readonly"
ACTION_ID = "esxi.vm-teardown-apply"
REPO_ROOT = Path(__file__).resolve().parents[4]
CODEX_RUN_DIR = REPO_ROOT / "artifacts" / "codex-runs"

VM_TEARDOWN_CONFIRM_PHRASE = "REMOVE ONE ESXI VM"
MAX_VM_NAME_LENGTH = 80
VM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")
NOT_FOUND_MARKERS = (
    "not found",
    "cannot find",
    "could not find",
    "no such virtual machine",
    "managed object not found",
)

PREVIEW_REPORT = CODEX_RUN_DIR / "esxi-vm-teardown-preview-report.md"
PREVIEW_JSON = CODEX_RUN_DIR / "esxi-vm-teardown-preview-redacted.json"
APPLY_REPORT = CODEX_RUN_DIR / "esxi-vm-teardown-apply-report.md"
APPLY_JSON = CODEX_RUN_DIR / "esxi-vm-teardown-apply-redacted.json"
VALIDATION_REPORT = CODEX_RUN_DIR / "esxi-vm-teardown-validation-report.md"
VALIDATION_JSON = CODEX_RUN_DIR / "esxi-vm-teardown-validation-redacted.json"

GovcExecutor = Callable[..., dict[str, Any]]


def build_esxi_vm_teardown_preview(
    vm_name: str,
    *,
    executor: GovcExecutor | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    """Build a read-only removal plan for one validated VM identifier."""

    checked_at = _now()
    request = _validated_request(vm_name)
    target = _target_state(executor_injected=executor is not None)
    blockers = _preview_static_blockers(request, target)
    evidence = _skipped_evidence("Static preview checks did not pass.")

    if not blockers:
        evidence = _discover_current_state(
            request["vm_name"],
            target=target,
            executor=executor,
        )
        blockers.extend(_evidence_blockers(evidence, require_vm=False))

    vm = evidence["vm"]
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "vm-teardown-preview",
        "checked_at": checked_at,
        "status": (
            "blocked"
            if blockers
            else "already_absent"
            if vm.get("absence_confirmed")
            else "preview_ready"
        ),
        "message": (
            "A read-only ESXi VM teardown preview was generated. No power, delete, "
            "datastore, or host operation was run."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if evidence["checked"] else "live_cached",
        "freshness": "current" if evidence["checked"] else "not_checked",
        "request": request,
        "target": target,
        "target_binding": evidence["target_binding"],
        "vm_evidence": vm,
        "teardown_plan": _teardown_plan(request, vm),
        "required_flags": _required_flags(target),
        "command_preview": _command_preview(request["vm_name"]),
        "blockers": _unique(blockers),
        "warnings": _preview_warnings(vm),
        "audit": _audit_payload(
            action="preview",
            checked_at=checked_at,
            request=request,
            target=target,
            evidence=evidence,
            gates=None,
            operations=[],
        ),
        "artifacts": {
            "report": _rel(PREVIEW_REPORT),
            "json": _rel(PREVIEW_JSON),
        },
        "next_safe_action": _preview_next_action(blockers, vm),
    }
    return _finish_payload(payload, PREVIEW_JSON, PREVIEW_REPORT, write_report)


def apply_esxi_vm_teardown(
    vm_name: str,
    *,
    executor: GovcExecutor | None = None,
    write_report: bool = True,
    guarded_context: GuardedActionContext | None = None,
) -> dict[str, Any]:
    """Power off, prove powered off, and remove one exact VM after all gates pass."""

    checked_at = _now()
    request = _validated_request(vm_name)
    target = _target_state(executor_injected=executor is not None)
    gates = _apply_gates(request, target, guarded_context=guarded_context)
    operations: list[dict[str, Any]] = []
    evidence = _skipped_evidence("Apply gates did not pass.")
    apply_state = {
        "target_probe_attempted": False,
        "vm_probe_attempted": False,
        "power_off_attempted": False,
        "powered_off_proven": False,
        "destroy_attempted": False,
        "absence_validation_attempted": False,
        "absence_confirmed": False,
    }
    blockers = list(gates["blockers"])
    warnings: list[str] = []
    status = "blocked"
    message = "ESXi VM teardown was refused before any govc command."

    if not blockers:
        evidence = _discover_current_state(
            request["vm_name"],
            target=target,
            executor=executor,
            operations=operations,
        )
        apply_state["target_probe_attempted"] = bool(evidence["target_binding"].get("checked"))
        apply_state["vm_probe_attempted"] = bool(evidence["vm"].get("checked"))
        blockers.extend(_evidence_blockers(evidence, require_vm=False))

        if not blockers and evidence["vm"].get("absence_confirmed"):
            status = "completed"
            message = (
                f"VM `{request['vm_name']}` is already absent from the bound ESXi "
                "target. No write operation was run."
            )
            apply_state["absence_confirmed"] = True
        elif not blockers:
            execution = _execute_teardown(
                request["vm_name"],
                target=target,
                initial_evidence=evidence,
                executor=executor,
                operations=operations,
            )
            status = execution["status"]
            message = execution["message"]
            blockers.extend(execution["blockers"])
            warnings.extend(execution["warnings"])
            apply_state.update(execution["apply"])
            evidence["vm"] = execution["final_vm_evidence"]

    payload = {
        "provider_id": PROVIDER_ID,
        "action": "vm-teardown-apply",
        "checked_at": checked_at,
        "status": status,
        "message": message,
        "mode": settings.provider_mode,
        "apply_enabled": not gates["blockers"],
        "source_type": "live_probe" if evidence["checked"] else "live_cached",
        "freshness": "current" if evidence["checked"] else "not_checked",
        "request": request,
        "target": target,
        "target_binding": evidence["target_binding"],
        "vm_evidence": evidence["vm"],
        "teardown_plan": _teardown_plan(request, evidence["vm"]),
        "required_flags": _required_flags(target),
        "command_preview": _command_preview(request["vm_name"]),
        "flag_state": gates["flag_state"],
        "apply": apply_state,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
        "audit": _audit_payload(
            action="apply",
            checked_at=checked_at,
            request=request,
            target=target,
            evidence=evidence,
            gates=gates,
            operations=operations,
        ),
        "artifacts": {
            "report": _rel(APPLY_REPORT),
            "json": _rel(APPLY_JSON),
        },
        "next_safe_action": _apply_next_action(status, blockers),
    }
    return _finish_payload(payload, APPLY_JSON, APPLY_REPORT, write_report)


def validate_esxi_vm_teardown(
    vm_name: str,
    *,
    executor: GovcExecutor | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    """Prove the exact VM is absent using fresh read-only ESXi evidence."""

    checked_at = _now()
    request = _validated_request(vm_name)
    target = _target_state(executor_injected=executor is not None)
    blockers = _preview_static_blockers(request, target)
    evidence = _skipped_evidence("Static validation checks did not pass.")

    if not blockers:
        evidence = _discover_current_state(
            request["vm_name"],
            target=target,
            executor=executor,
        )
        blockers.extend(_evidence_blockers(evidence, require_vm=False))
        if evidence["vm"].get("exists"):
            blockers.append(f"VM `{request['vm_name']}` is still present.")
        elif not evidence["vm"].get("absence_confirmed"):
            blockers.append(
                f"Absence of VM `{request['vm_name']}` was not proven by the fresh query."
            )

    absent = not blockers and evidence["vm"].get("absence_confirmed")
    payload = {
        "provider_id": PROVIDER_ID,
        "action": "vm-teardown-validation",
        "checked_at": checked_at,
        "status": "ready" if absent else "blocked",
        "message": (
            f"Fresh direct-ESXi evidence confirms VM `{request['vm_name']}` is absent."
            if absent
            else "ESXi VM teardown validation did not prove the requested VM is absent."
        ),
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "source_type": "live_probe" if evidence["checked"] else "live_cached",
        "freshness": "current" if evidence["checked"] else "not_checked",
        "request": request,
        "target": target,
        "target_binding": evidence["target_binding"],
        "vm_evidence": evidence["vm"],
        "blockers": _unique(blockers),
        "warnings": [],
        "audit": _audit_payload(
            action="validate",
            checked_at=checked_at,
            request=request,
            target=target,
            evidence=evidence,
            gates=None,
            operations=[],
        ),
        "artifacts": {
            "report": _rel(VALIDATION_REPORT),
            "json": _rel(VALIDATION_JSON),
        },
        "next_safe_action": (
            "The VM-removal postcondition is satisfied."
            if absent
            else "Resolve the blockers and rerun the read-only absence validation."
        ),
    }
    return _finish_payload(
        payload,
        VALIDATION_JSON,
        VALIDATION_REPORT,
        write_report,
    )


def _validated_request(vm_name: Any) -> dict[str, Any]:
    normalized = vm_name.strip() if isinstance(vm_name, str) else ""
    errors: list[str] = []
    if not normalized:
        errors.append("A non-empty VM name is required.")
    elif len(normalized) > MAX_VM_NAME_LENGTH:
        errors.append(f"VM name must be at most {MAX_VM_NAME_LENGTH} characters.")
    elif not VM_NAME_RE.fullmatch(normalized):
        errors.append(
            "VM name may contain only letters, numbers, spaces, dots, underscores, "
            "and hyphens, and must start with a letter or number."
        )
    if isinstance(vm_name, str) and vm_name != normalized:
        errors.append("VM name must not contain leading or trailing whitespace.")
    return {
        "vm_name": normalized,
        "valid": not errors,
        "validation_errors": errors,
        "scope": "one_exact_virtual_machine",
    }


def _target_state(*, executor_injected: bool) -> dict[str, Any]:
    configured_target = _normalize_host(settings.esxi_test_host)
    env = _govc_env()
    govc_target = _url_host(env.get("GOVC_URL"))
    missing_fields = []
    if not configured_target:
        missing_fields.append("ESXI_TEST_HOST")
    if not govc_target:
        missing_fields.append("GOVC_URL")
    if not env.get("GOVC_USERNAME"):
        missing_fields.append("GOVC_USERNAME or ESXI_TEST_USERNAME")
    if not env.get("GOVC_PASSWORD"):
        missing_fields.append("GOVC_PASSWORD or ESXI_TEST_PASSWORD")
    if not settings.esxi_configured:
        missing_fields.append("ESXI_CONFIGURED=true")

    targets_match = bool(
        configured_target and govc_target and configured_target.casefold() == govc_target.casefold()
    )
    executor_available = executor_injected or bool(_govc_binary())
    can_query = bool(not missing_fields and targets_match and executor_available)
    return {
        "provider_mode": settings.provider_mode,
        "esxi_configured": settings.esxi_configured,
        "configured_target": configured_target,
        "govc_target": govc_target,
        "targets_match": targets_match,
        "expected_confirmation": configured_target,
        "username_configured": bool(env.get("GOVC_USERNAME")),
        "credential_configured": bool(env.get("GOVC_PASSWORD")),
        "tls_verify": settings.esxi_test_verify_tls,
        "govc_available": executor_available,
        "executor_injected": executor_injected,
        "missing_fields": _unique(missing_fields),
        "can_query": can_query,
    }


def _preview_static_blockers(
    request: dict[str, Any],
    target: dict[str, Any],
) -> list[str]:
    blockers = list(request["validation_errors"])
    policy = current_lab_action_policy(settings.provider_mode)
    blockers.extend(_string_list(policy.readonly_blockers()))
    if settings.provider_mode == MOCK_MODE:
        blockers.append(
            "PROVIDER_MODE=local-readonly or local-lab-readwrite is required for "
            "fresh ESXi teardown evidence."
        )
    if target["missing_fields"]:
        blockers.append(f"ESXi target fields are missing: {', '.join(target['missing_fields'])}.")
    if target["configured_target"] and target["govc_target"] and not target["targets_match"]:
        blockers.append(
            "GOVC_URL does not resolve to the configured ESXI_TEST_HOST; refusing "
            "an unbound target."
        )
    if not target["govc_available"]:
        blockers.append("govc is not available.")
    return _unique(blockers)


def _apply_gates(
    request: dict[str, Any],
    target: dict[str, Any],
    *,
    guarded_context: GuardedActionContext | None,
) -> dict[str, Any]:
    expected_name = request["vm_name"]
    expected_target = target["expected_confirmation"]
    confirmed_name = guarded_value(
        "VM_TEARDOWN_CONFIRM_VM_NAME",
        action_id=ACTION_ID,
        context=guarded_context,
    )
    confirmed_target = guarded_value(
        "VM_TEARDOWN_CONFIRM_ESXI_TARGET",
        action_id=ACTION_ID,
        context=guarded_context,
    )
    flag_state = {
        "provider_mode": settings.provider_mode,
        "local_lab_readwrite": settings.provider_mode == LOCAL_LAB_READWRITE_MODE,
        "vm_teardown_apply": guarded_flag(
            "VM_TEARDOWN_APPLY",
            action_id=ACTION_ID,
            context=guarded_context,
        ),
        "vm_teardown_allow_delete": guarded_flag(
            "VM_TEARDOWN_ALLOW_DELETE",
            action_id=ACTION_ID,
            context=guarded_context,
        ),
        "vm_teardown_allow_power_off": guarded_flag(
            "VM_TEARDOWN_ALLOW_POWER_OFF",
            action_id=ACTION_ID,
            context=guarded_context,
        ),
        "lab_allow_power_actions": guarded_flag(
            "LAB_ALLOW_POWER_ACTIONS",
            action_id=ACTION_ID,
            context=guarded_context,
        ),
        "confirmation_phrase_matches": guarded_confirmation(
            "VM_TEARDOWN_CONFIRM",
            action_id=ACTION_ID,
            context=guarded_context,
        )
        == VM_TEARDOWN_CONFIRM_PHRASE,
        "vm_name_confirmation_matches": bool(expected_name and confirmed_name == expected_name),
        "esxi_target_confirmation_matches": bool(
            expected_target
            and _normalize_host(confirmed_target)
            and _normalize_host(confirmed_target).casefold() == expected_target.casefold()
        ),
    }
    blockers = list(request["validation_errors"])
    if not flag_state["local_lab_readwrite"]:
        blockers.append("PROVIDER_MODE=local-lab-readwrite is required.")
    else:
        blockers.extend(
            _string_list(
                current_lab_action_policy(settings.provider_mode).action_blockers(
                    "vm.teardown",
                    ActionCategory.VM_DEPLOY,
                )
            )
        )
    blockers.extend(_target_static_blockers(target))
    if not flag_state["vm_teardown_apply"]:
        blockers.append("VM_TEARDOWN_APPLY=true is required.")
    if not flag_state["vm_teardown_allow_delete"]:
        blockers.append("VM_TEARDOWN_ALLOW_DELETE=true is required.")
    if not flag_state["vm_teardown_allow_power_off"]:
        blockers.append("VM_TEARDOWN_ALLOW_POWER_OFF=true is required.")
    if not flag_state["lab_allow_power_actions"]:
        blockers.append("LAB_ALLOW_POWER_ACTIONS=true is required.")
    if not flag_state["confirmation_phrase_matches"]:
        blockers.append(f'VM_TEARDOWN_CONFIRM="{VM_TEARDOWN_CONFIRM_PHRASE}" is required.')
    if not flag_state["vm_name_confirmation_matches"]:
        blockers.append("VM_TEARDOWN_CONFIRM_VM_NAME must exactly match the requested VM name.")
    if not flag_state["esxi_target_confirmation_matches"]:
        blockers.append(
            "VM_TEARDOWN_CONFIRM_ESXI_TARGET must exactly match the configured ESXi target."
        )
    return {"flag_state": flag_state, "blockers": _unique(blockers)}


def _target_static_blockers(target: dict[str, Any]) -> list[str]:
    blockers = []
    if target["missing_fields"]:
        blockers.append(f"ESXi target fields are missing: {', '.join(target['missing_fields'])}.")
    if target["configured_target"] and target["govc_target"] and not target["targets_match"]:
        blockers.append(
            "GOVC_URL does not resolve to the configured ESXI_TEST_HOST; refusing "
            "an unbound target."
        )
    if not target["govc_available"]:
        blockers.append("govc is not available.")
    return blockers


def _discover_current_state(
    vm_name: str,
    *,
    target: dict[str, Any],
    executor: GovcExecutor | None,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    operation_log = operations if operations is not None else []
    binding = _target_binding(target=target, executor=executor, operations=operation_log)
    if not binding["bound"]:
        return {
            "checked": True,
            "target_binding": binding,
            "vm": _skipped_vm_evidence("Direct ESXi target identity was not proven."),
        }
    vm = _query_vm(vm_name, executor=executor, operations=operation_log)
    return {
        "checked": True,
        "target_binding": binding,
        "vm": vm,
    }


def _target_binding(
    *,
    target: dict[str, Any],
    executor: GovcExecutor | None,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    result = _execute_fixed(
        "about",
        vm_name=None,
        executor=executor,
        operations=operations,
    )
    about = _about_summary(result["stdout"])
    api_type = str(about.get("api_type") or "")
    instance_uuid = str(about.get("instance_uuid") or "")
    direct_esxi = api_type.casefold() == "hostagent"
    bound = bool(
        result["return_code"] == 0 and direct_esxi and instance_uuid and target["targets_match"]
    )
    fingerprint = None
    if bound:
        material = "|".join(
            (
                str(target["configured_target"]),
                instance_uuid,
                api_type,
            )
        )
        fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
    error = None
    if result["return_code"] != 0:
        error = "govc about failed; direct ESXi identity was not proven."
    elif not direct_esxi:
        error = (
            "The govc endpoint did not identify as a direct ESXi HostAgent; "
            "vCenter targets are refused."
        )
    elif not instance_uuid:
        error = "The direct ESXi instance UUID was missing from govc about evidence."
    elif not target["targets_match"]:
        error = "Configured ESXi and govc targets do not match."
    return {
        "checked": True,
        "checked_at": result["finished_at"],
        "freshness": "current",
        "bound": bound,
        "configured_target": target["configured_target"],
        "govc_target": target["govc_target"],
        "direct_esxi": direct_esxi,
        "api_type": api_type or None,
        "product_name": about.get("name"),
        "version": about.get("version"),
        "build": about.get("build"),
        "instance_fingerprint": fingerprint,
        "return_code": result["return_code"],
        "error": error,
        "stderr": result["stderr"] if result["return_code"] != 0 else "",
    }


def _query_vm(
    vm_name: str,
    *,
    executor: GovcExecutor | None,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    result = _execute_fixed(
        "vm_info",
        vm_name=vm_name,
        executor=executor,
        operations=operations,
    )
    return _vm_evidence(result, vm_name)


def _vm_evidence(result: dict[str, Any], vm_name: str) -> dict[str, Any]:
    base = {
        "checked": True,
        "checked_at": result["finished_at"],
        "freshness": "current",
        "requested_name": vm_name,
        "exists": False,
        "absence_confirmed": False,
        "exact_match": False,
        "ambiguous": False,
        "power_state": None,
        "inventory_path": None,
        "return_code": result["return_code"],
        "error": None,
        "stderr": result["stderr"] if result["return_code"] != 0 else "",
    }
    if result["return_code"] != 0:
        combined = f"{result['stdout']}\n{result['stderr']}".casefold()
        if any(marker in combined for marker in NOT_FOUND_MARKERS):
            base["absence_confirmed"] = True
        else:
            base["error"] = "govc vm.info failed without proving VM absence."
        return base

    payload = parse_json_object(result["stdout"])
    virtual_machines = payload.get("VirtualMachines")
    if not isinstance(virtual_machines, list):
        base["error"] = "govc vm.info returned an unexpected payload."
        return base
    if not virtual_machines:
        base["absence_confirmed"] = True
        return base

    matches = []
    for vm in virtual_machines:
        if not isinstance(vm, dict):
            continue
        summary = vm.get("Summary") if isinstance(vm.get("Summary"), dict) else {}
        config = summary.get("Config") if isinstance(summary.get("Config"), dict) else {}
        if config.get("Name") == vm_name:
            matches.append(vm)
    if len(matches) != 1:
        base["ambiguous"] = len(matches) > 1
        base["error"] = (
            "govc vm.info returned more than one exact VM match."
            if len(matches) > 1
            else "govc vm.info did not return the exact requested VM."
        )
        return base

    vm = matches[0]
    summary = vm.get("Summary") if isinstance(vm.get("Summary"), dict) else {}
    runtime = summary.get("Runtime") if isinstance(summary.get("Runtime"), dict) else {}
    base.update(
        {
            "exists": True,
            "exact_match": True,
            "power_state": runtime.get("PowerState"),
            "inventory_path": vm.get("InventoryPath"),
        }
    )
    if not base["power_state"]:
        base["error"] = "The exact VM power state was missing from fresh evidence."
    return base


def _evidence_blockers(
    evidence: dict[str, Any],
    *,
    require_vm: bool,
) -> list[str]:
    blockers = []
    binding = evidence["target_binding"]
    vm = evidence["vm"]
    if not binding.get("bound"):
        blockers.append(binding.get("error") or "Direct ESXi target identity was not proven.")
    if vm.get("error"):
        blockers.append(vm["error"])
    if vm.get("ambiguous"):
        blockers.append("VM identity is ambiguous; no write is allowed.")
    if require_vm and not vm.get("exists"):
        blockers.append("The exact requested VM was not proven present.")
    return _unique(blockers)


def _execute_teardown(
    vm_name: str,
    *,
    target: dict[str, Any],
    initial_evidence: dict[str, Any],
    executor: GovcExecutor | None,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    del target  # Binding is captured in initial_evidence and all calls use the same govc env.
    vm = initial_evidence["vm"]
    blockers = _evidence_blockers(initial_evidence, require_vm=True)
    warnings: list[str] = []
    apply_state = {
        "power_off_attempted": False,
        "powered_off_proven": False,
        "destroy_attempted": False,
        "absence_validation_attempted": False,
        "absence_confirmed": False,
    }
    if blockers:
        return _execution_result(
            "blocked",
            "Fresh evidence did not prove one exact VM target.",
            blockers,
            warnings,
            apply_state,
            vm,
        )

    if str(vm.get("power_state") or "").casefold() != "poweredoff":
        power_off = _execute_fixed(
            "power_off",
            vm_name=vm_name,
            executor=executor,
            operations=operations,
        )
        apply_state["power_off_attempted"] = True
        if power_off["return_code"] != 0:
            blockers.append("govc vm.power -off failed; VM destroy was not attempted.")
            return _execution_result(
                "failed",
                "VM teardown stopped because the exact VM could not be powered off.",
                blockers,
                warnings,
                apply_state,
                vm,
            )
        vm = _query_vm(vm_name, executor=executor, operations=operations)
        if (
            vm.get("error")
            or not vm.get("exists")
            or str(vm.get("power_state") or "").casefold() != "poweredoff"
        ):
            blockers.append(
                "Fresh vm.info evidence did not prove the exact VM powered off; "
                "VM destroy was not attempted."
            )
            return _execution_result(
                "failed",
                "VM teardown stopped before destroy because powered-off state was not proven.",
                blockers,
                warnings,
                apply_state,
                vm,
            )
    apply_state["powered_off_proven"] = True

    destroyed = _execute_fixed(
        "destroy",
        vm_name=vm_name,
        executor=executor,
        operations=operations,
    )
    apply_state["destroy_attempted"] = True
    if destroyed["return_code"] != 0:
        blockers.append("govc vm.destroy failed.")
        return _execution_result(
            "failed",
            "The exact VM destroy command failed.",
            blockers,
            warnings,
            apply_state,
            vm,
        )

    final_vm = _query_vm(vm_name, executor=executor, operations=operations)
    apply_state["absence_validation_attempted"] = True
    apply_state["absence_confirmed"] = bool(final_vm.get("absence_confirmed"))
    if final_vm.get("absence_confirmed"):
        return _execution_result(
            "completed",
            f"VM `{vm_name}` was powered off first and its absence is now proven.",
            blockers,
            warnings,
            apply_state,
            final_vm,
        )

    blockers.append(
        "govc vm.destroy returned success, but fresh vm.info evidence did not prove the VM absent."
    )
    return _execution_result(
        "failed",
        "The destroy command returned success, but the teardown postcondition was not proven.",
        blockers,
        warnings,
        apply_state,
        final_vm,
    )


def _execute_fixed(
    operation: str,
    *,
    vm_name: str | None,
    executor: GovcExecutor | None,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    args = _fixed_args(operation, vm_name)
    started_at = _now()
    runner = executor or _run_govc
    raw = runner(args, env=_govc_env(), timeout=_operation_timeout(operation))
    finished_at = _now()
    result = {
        "return_code": _return_code(raw.get("return_code")),
        "stdout": str(raw.get("stdout") or ""),
        "stderr": str(raw.get("stderr") or ""),
        "started_at": started_at,
        "finished_at": finished_at,
    }
    operations.append(
        {
            "operation": operation,
            "command": ["govc", *args],
            "started_at": started_at,
            "finished_at": finished_at,
            "return_code": result["return_code"],
        }
    )
    return result


def _fixed_args(operation: str, vm_name: str | None) -> list[str]:
    if operation == "about" and vm_name is None:
        return ["about", "-json"]
    if operation == "vm_info" and vm_name is not None:
        _require_valid_vm_name(vm_name)
        return ["vm.info", "-json", vm_name]
    if operation == "power_off" and vm_name is not None:
        _require_valid_vm_name(vm_name)
        return ["vm.power", "-off", vm_name]
    if operation == "destroy" and vm_name is not None:
        _require_valid_vm_name(vm_name)
        return ["vm.destroy", vm_name]
    raise ValueError(f"Unsupported fixed govc operation: {operation}")


def _require_valid_vm_name(vm_name: str) -> None:
    request = _validated_request(vm_name)
    if not request["valid"]:
        raise ValueError("Refusing to build a govc command for an invalid VM name.")


def _operation_timeout(operation: str) -> int:
    return 120 if operation in {"power_off", "destroy"} else 30


def _run_govc(
    args: list[str],
    *,
    env: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    govc = _govc_binary()
    if govc is None:
        return {
            "return_code": 127,
            "stdout": "",
            "stderr": "govc executable was not found.",
        }
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
        return {
            "return_code": 127,
            "stdout": "",
            "stderr": "govc executable was not found.",
        }
    except subprocess.TimeoutExpired:
        return {
            "return_code": 124,
            "stdout": "",
            "stderr": "govc command timed out.",
        }
    return {
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _govc_binary() -> str | None:
    from shutil import which

    found = which("govc")
    if found:
        return found
    for directory in (Path(os.sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        for executable in ("govc.exe", "govc"):
            candidate = directory / executable
            if _is_file(candidate):
                return str(candidate)
    return None


def _govc_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault(
        "GOVC_URL",
        f"https://{settings.esxi_test_host}/sdk" if settings.esxi_test_host else "",
    )
    env.setdefault("GOVC_USERNAME", settings.esxi_test_username or "")
    env.setdefault("GOVC_PASSWORD", settings.esxi_test_password or "")
    if "GOVC_INSECURE" not in env:
        env["GOVC_INSECURE"] = "false" if settings.esxi_test_verify_tls else "true"
    return env


def _about_summary(stdout: str) -> dict[str, Any]:
    payload = parse_json_object(stdout)
    about = payload.get("About")
    if not isinstance(about, dict):
        about = payload.get("about")
    if not isinstance(about, dict):
        return {}
    return {
        "name": about.get("Name") or about.get("name"),
        "version": about.get("Version") or about.get("version"),
        "build": about.get("Build") or about.get("build"),
        "api_type": about.get("ApiType") or about.get("apiType"),
        "instance_uuid": (
            about.get("InstanceUuid") or about.get("InstanceUUID") or about.get("instanceUuid")
        ),
    }


def _normalize_host(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    parsed = urlsplit(text if "://" in text else f"//{text}")
    host = parsed.hostname
    return host.strip().rstrip(".").lower() if host else None


def _url_host(value: Any) -> str | None:
    return _normalize_host(value)


def _teardown_plan(
    request: dict[str, Any],
    vm: dict[str, Any],
) -> dict[str, Any]:
    return {
        "vm_name": request["vm_name"],
        "scope": request["scope"],
        "current_power_state": vm.get("power_state"),
        "destructive_apply_needed": bool(vm.get("exists")),
        "ordered_operations": [
            "Bind to a direct ESXi HostAgent with fresh govc about evidence.",
            "Read the exact VM inventory and current power state.",
            "Power off the exact VM when it is not already powered off.",
            "Read the exact VM again and require poweredOff evidence.",
            "Destroy only the exact VM.",
            "Read the exact VM again and require confirmed absence.",
        ],
        "explicitly_excluded": [
            "datastore remove or wipe",
            "host maintenance, reset, reinstall, or reconfiguration",
            "disk, partition, RAID, or local-storage changes",
            "network or switch changes",
            "vCenter operations",
            "wildcard or folder-wide VM deletion",
        ],
    }


def _required_flags(target: dict[str, Any]) -> list[str]:
    return [
        "PROVIDER_MODE=local-lab-readwrite",
        "VM_TEARDOWN_APPLY=true",
        "VM_TEARDOWN_ALLOW_DELETE=true",
        "VM_TEARDOWN_ALLOW_POWER_OFF=true",
        "LAB_ALLOW_POWER_ACTIONS=true",
        f'VM_TEARDOWN_CONFIRM="{VM_TEARDOWN_CONFIRM_PHRASE}"',
        "VM_TEARDOWN_CONFIRM_VM_NAME=<exact requested VM name>",
        (
            "VM_TEARDOWN_CONFIRM_ESXI_TARGET="
            f"{target.get('expected_confirmation') or '<exact ESXi target>'}"
        ),
    ]


def _command_preview(vm_name: str) -> list[str]:
    display_name = vm_name or "<validated-vm-name>"
    return [
        "govc about -json",
        f'govc vm.info -json "{display_name}"',
        f'govc vm.power -off "{display_name}" (only when not already powered off)',
        f'govc vm.info -json "{display_name}" (must prove poweredOff)',
        f'govc vm.destroy "{display_name}"',
        f'govc vm.info -json "{display_name}" (must prove absence)',
    ]


def _preview_warnings(vm: dict[str, Any]) -> list[str]:
    if vm.get("exists"):
        return [
            "Removing a VM deletes its inventory object and virtual disks. This "
            "service does not remove or wipe the containing datastore."
        ]
    return []


def _preview_next_action(blockers: list[str], vm: dict[str, Any]) -> str:
    if blockers:
        return "Resolve blockers and regenerate the read-only preview."
    if vm.get("absence_confirmed"):
        return "No teardown apply is needed; run validation to record the postcondition."
    return (
        "Review the exact VM, ESXi target, power state, and exclusions before "
        "supplying all guarded apply confirmations."
    )


def _apply_next_action(status: str, blockers: list[str]) -> str:
    if status == "completed":
        return "Run the read-only VM teardown validation to preserve fresh evidence."
    if blockers:
        return "Resolve blockers and regenerate the read-only teardown preview."
    return "Review the audit operations before any retry."


def _audit_payload(
    *,
    action: str,
    checked_at: str,
    request: dict[str, Any],
    target: dict[str, Any],
    evidence: dict[str, Any],
    gates: dict[str, Any] | None,
    operations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "event_type": "esxi_vm_teardown",
        "action_id": ACTION_ID,
        "phase": action,
        "recorded_at": checked_at,
        "scope": {
            "vm_name": request["vm_name"],
            "scope": request["scope"],
            "configured_esxi_target": target["configured_target"],
        },
        "target_binding": {
            "bound": evidence["target_binding"].get("bound"),
            "checked_at": evidence["target_binding"].get("checked_at"),
            "instance_fingerprint": evidence["target_binding"].get("instance_fingerprint"),
            "direct_esxi": evidence["target_binding"].get("direct_esxi"),
        },
        "approval": dict(gates["flag_state"]) if gates else {},
        "operations": operations,
        "safety_exclusions": _teardown_plan(request, evidence["vm"])["explicitly_excluded"],
    }


def _skipped_evidence(reason: str) -> dict[str, Any]:
    return {
        "checked": False,
        "target_binding": {
            "checked": False,
            "checked_at": None,
            "freshness": "not_checked",
            "bound": False,
            "configured_target": None,
            "govc_target": None,
            "direct_esxi": False,
            "api_type": None,
            "product_name": None,
            "version": None,
            "build": None,
            "instance_fingerprint": None,
            "return_code": None,
            "error": reason,
            "stderr": "",
        },
        "vm": _skipped_vm_evidence(reason),
    }


def _skipped_vm_evidence(reason: str) -> dict[str, Any]:
    return {
        "checked": False,
        "checked_at": None,
        "freshness": "not_checked",
        "requested_name": None,
        "exists": False,
        "absence_confirmed": False,
        "exact_match": False,
        "ambiguous": False,
        "power_state": None,
        "inventory_path": None,
        "return_code": None,
        "error": reason,
        "stderr": "",
    }


def _execution_result(
    status: str,
    message: str,
    blockers: list[str],
    warnings: list[str],
    apply_state: dict[str, Any],
    final_vm_evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
        "apply": apply_state,
        "final_vm_evidence": final_vm_evidence,
    }


def _return_code(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 1


def _finish_payload(
    payload: dict[str, Any],
    json_path: Path,
    report_path: Path,
    write_report: bool,
) -> dict[str, Any]:
    sanitized = _sanitize(payload)
    if write_report:
        CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
        write_json_object(json_path, sanitized)
        write_text_value(report_path, _markdown(sanitized))
    return sanitized


def _markdown(payload: dict[str, Any]) -> str:
    request = payload.get("request") or {}
    binding = payload.get("target_binding") or {}
    vm = payload.get("vm_evidence") or {}
    lines = [
        "# ESXi VM Teardown Report",
        "",
        f"- Phase: `{payload.get('action')}`",
        f"- Checked at: `{payload.get('checked_at')}`",
        f"- Status: `{payload.get('status')}`",
        f"- Provider mode: `{payload.get('mode')}`",
        f"- VM name: `{request.get('vm_name')}`",
        f"- Direct ESXi target bound: `{binding.get('bound')}`",
        f"- Target evidence freshness: `{binding.get('freshness')}`",
        f"- VM exists: `{vm.get('exists')}`",
        f"- VM power state: `{vm.get('power_state')}`",
        f"- VM absence confirmed: `{vm.get('absence_confirmed')}`",
        "",
        "## Fixed Command Plan",
    ]
    lines.extend(f"- `{item}`" for item in payload.get("command_preview") or [])
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers") or ["None"])
    lines.extend(
        [
            "",
            "## Safety Boundary",
            "- The service can address only one validated VM name.",
            "- It powers that VM off and proves poweredOff before destroy.",
            "- It never removes or wipes a datastore, host, disk, RAID set, or network.",
        ]
    )
    return "\n".join(lines) + "\n"


def _sanitize(payload: Any) -> Any:
    return redact_sensitive(payload, _redaction_values())


def _redaction_values() -> list[str]:
    return [
        value
        for key, value in os.environ.items()
        if value
        and any(
            fragment in key.lower()
            for fragment in (
                "password",
                "token",
                "secret",
                "authorization",
                "cookie",
            )
        )
    ]


def _rel(path: Path) -> str:
    return repo_relative_path(path, REPO_ROOT)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)


def _unique(values: list[Any]) -> list[Any]:
    return unique_preserving_order(values, skip_falsey=True)
