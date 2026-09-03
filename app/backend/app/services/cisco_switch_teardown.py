from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.providers.action_policy import (
    ActionCategory,
    LOCAL_LAB_READWRITE_MODE,
    current_lab_action_policy,
)
from app.services.destructive_plan_claims import (
    DestructivePlanClaim,
    DestructivePlanClaimStore,
)
from app.services.list_utils import unique_preserving_order, unique_strings

PROVIDER_ID = "cisco-switch-teardown"
POLICY_ACTION_ID = "cisco-console.factory-reset"
PAYLOAD_CONTRACT_VERSION = "cisco-switch-teardown-v1"

ACTION_CONFIRMATION_PHRASE = "BLANK CISCO SWITCH"
SERIAL_EVIDENCE_MAX_AGE = timedelta(minutes=5)
BACKUP_EVIDENCE_MAX_AGE = timedelta(hours=1)
VALIDATION_EVIDENCE_MAX_AGE = timedelta(minutes=10)
MAX_FUTURE_CLOCK_SKEW = timedelta(seconds=30)

REQUIRED_BACKUP_ARTIFACTS = frozenset(
    {
        "running-config",
        "startup-config",
        "vlan-database",
        "boot-environment",
        "license-state",
    }
)


class CiscoSwitchPlatform(str, Enum):
    IOS = "cisco-ios"
    IOS_XE = "cisco-ios-xe"


class CiscoSwitchTeardownOperation(str, Enum):
    IOS_ERASE_STARTUP_CONFIGURATION = "cisco-ios.erase-startup-configuration"
    IOS_DELETE_VLAN_DATABASE = "cisco-ios.delete-vlan-database"
    IOS_RELOAD_WITHOUT_SAVE = "cisco-ios.reload-without-save"
    IOS_XE_ERASE_STARTUP_CONFIGURATION = "cisco-ios-xe.erase-startup-configuration"
    IOS_XE_DELETE_VLAN_DATABASE = "cisco-ios-xe.delete-vlan-database"
    IOS_XE_RELOAD_WITHOUT_SAVE = "cisco-ios-xe.reload-without-save"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class CiscoSwitchTarget(_StrictModel):
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    console_path: str = Field(min_length=1)
    platform: CiscoSwitchPlatform
    chassis_model: str = Field(min_length=1)
    chassis_serial: str = Field(min_length=1)
    hostname: str | None = None
    management_address: str | None = None


class CiscoPrivilegedSerialEvidence(_StrictModel):
    observed_at: datetime
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    console_path: str = Field(min_length=1)
    platform: CiscoSwitchPlatform
    chassis_model: str = Field(min_length=1)
    chassis_serial: str = Field(min_length=1)
    hostname: str | None = None
    observed_management_address: str | None = None
    transport: Literal["serial-console"]
    prompt_state: Literal[
        "privileged-exec",
        "user-exec",
        "login-required",
        "config-mode",
        "setup-wizard",
        "unknown",
    ]
    privileged: bool
    exclusive_access: bool
    identity_verified: bool
    firmware_version: str = Field(min_length=1)
    license_state_digest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class CiscoSwitchBackupEvidence(_StrictModel):
    backup_id: str = Field(min_length=1)
    captured_at: datetime
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    platform: CiscoSwitchPlatform
    chassis_model: str = Field(min_length=1)
    chassis_serial: str = Field(min_length=1)
    artifact_digest_sha256: str = Field(min_length=1)
    artifacts: tuple[str, ...]
    verified: bool
    restore_instructions_present: bool


class CiscoSwitchTeardownApplyRequest(_StrictModel):
    provider_mode: str
    policy_action_id: str
    target: CiscoSwitchTarget
    current_evidence: CiscoPrivilegedSerialEvidence
    backup_evidence: CiscoSwitchBackupEvidence
    reviewed_plan_digest: str
    action_confirmation_phrase: str
    target_confirmation_phrase: str
    allow_switch_teardown: bool = False
    allow_startup_config_erase: bool = False
    allow_vlan_database_erase: bool = False
    allow_reload: bool = False
    acknowledge_expected_ssh_loss: bool = False
    executor_enabled: bool = False


class CiscoSwitchTeardownOperationPayload(_StrictModel):
    contract_version: Literal["cisco-switch-teardown-v1"]
    operation_id: CiscoSwitchTeardownOperation
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    console_path: str = Field(min_length=1)
    platform: CiscoSwitchPlatform
    chassis_model: str = Field(min_length=1)
    chassis_serial: str = Field(min_length=1)
    hostname: str | None = None
    management_address: str | None = None
    serial_evidence_observed_at: datetime
    backup_id: str = Field(min_length=1)
    backup_artifact_digest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    reviewed_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_binding_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    require_live_console_identity_exact_match: Literal[True]
    abort_on_console_identity_mismatch: Literal[True]


class CiscoSwitchOperationResult(_StrictModel):
    operation_id: CiscoSwitchTeardownOperation
    reviewed_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_binding_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    live_console_identity_matched: bool
    succeeded: bool
    outcome_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class CiscoSwitchTeardownExecutor(Protocol):
    def execute(
        self,
        operation_id: CiscoSwitchTeardownOperation,
        payload: CiscoSwitchTeardownOperationPayload,
    ) -> CiscoSwitchOperationResult: ...


class CiscoSwitchBlankStateEvidence(_StrictModel):
    observed_at: datetime
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    console_path: str = Field(min_length=1)
    platform: CiscoSwitchPlatform
    chassis_model: str = Field(min_length=1)
    chassis_serial: str = Field(min_length=1)
    transport: Literal["serial-console"]
    console_reconnected: bool
    prompt_state: Literal[
        "setup-wizard",
        "initial-dialog",
        "privileged-exec",
        "user-exec",
        "login-required",
        "unknown",
    ]
    startup_config_present: bool | None
    vlan_database_present: bool | None
    running_config_state: Literal["factory-default", "nondefault", "unknown"]
    firmware_version: str = Field(min_length=1)
    license_state_digest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    ssh_reachable: bool | None = None


class CiscoSwitchActionPolicy(Protocol):
    def action_blockers(
        self,
        action_id: str,
        category: ActionCategory | str,
    ) -> list[str]: ...


_PLATFORM_OPERATIONS: dict[
    CiscoSwitchPlatform,
    tuple[CiscoSwitchTeardownOperation, ...],
] = {
    CiscoSwitchPlatform.IOS: (
        CiscoSwitchTeardownOperation.IOS_ERASE_STARTUP_CONFIGURATION,
        CiscoSwitchTeardownOperation.IOS_DELETE_VLAN_DATABASE,
        CiscoSwitchTeardownOperation.IOS_RELOAD_WITHOUT_SAVE,
    ),
    CiscoSwitchPlatform.IOS_XE: (
        CiscoSwitchTeardownOperation.IOS_XE_ERASE_STARTUP_CONFIGURATION,
        CiscoSwitchTeardownOperation.IOS_XE_DELETE_VLAN_DATABASE,
        CiscoSwitchTeardownOperation.IOS_XE_RELOAD_WITHOUT_SAVE,
    ),
}

_OPERATION_INTENT = {
    CiscoSwitchTeardownOperation.IOS_ERASE_STARTUP_CONFIGURATION: (
        "Erase the saved IOS startup configuration through the privileged serial console."
    ),
    CiscoSwitchTeardownOperation.IOS_DELETE_VLAN_DATABASE: (
        "Delete the IOS VLAN database so locally-created VLAN state does not survive reload."
    ),
    CiscoSwitchTeardownOperation.IOS_RELOAD_WITHOUT_SAVE: (
        "Reload IOS and explicitly decline saving the current running configuration."
    ),
    CiscoSwitchTeardownOperation.IOS_XE_ERASE_STARTUP_CONFIGURATION: (
        "Erase the saved IOS XE startup configuration through the privileged serial console."
    ),
    CiscoSwitchTeardownOperation.IOS_XE_DELETE_VLAN_DATABASE: (
        "Delete the IOS XE VLAN database so locally-created VLAN state does not survive reload."
    ),
    CiscoSwitchTeardownOperation.IOS_XE_RELOAD_WITHOUT_SAVE: (
        "Reload IOS XE and explicitly decline saving the current running configuration."
    ),
}


def cisco_switch_target_confirmation_phrase(target: CiscoSwitchTarget) -> str:
    return (
        f"BLANK CISCO SWITCH {target.chassis_serial} "
        f"TARGET {target.target_id} PROFILE {target.profile_id}"
    )


def build_cisco_switch_teardown_preview(
    target: CiscoSwitchTarget,
    current_evidence: CiscoPrivilegedSerialEvidence,
    backup_evidence: CiscoSwitchBackupEvidence | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _normalized_now(now)
    operations = _platform_operation_plan(target.platform)
    blockers = _serial_evidence_blockers(target, current_evidence, now=checked_at)
    blockers.extend(_backup_evidence_blockers(target, backup_evidence, now=checked_at))
    blockers = unique_preserving_order(blockers)
    plan_digest = _plan_digest(target, current_evidence, backup_evidence, operations)

    return {
        "provider_id": PROVIDER_ID,
        "action": "switch-teardown-preview",
        "status": "ready_for_guarded_apply" if not blockers else "blocked",
        "checked_at": checked_at.isoformat(),
        "apply_enabled": False,
        "destructive": True,
        "target_binding": {
            "profile_id": target.profile_id,
            "target_id": target.target_id,
            "console_path": target.console_path,
            "management_address": target.management_address,
        },
        "intended_chassis_identity": _target_identity(target),
        "current_console_identity": _serial_identity(current_evidence),
        "identity_matches": not _identity_blockers(target, current_evidence),
        "platform": target.platform.value,
        "plan_digest": plan_digest,
        "operations": operations,
        "backup_prerequisite": {
            "required": True,
            "maximum_age_minutes": int(BACKUP_EVIDENCE_MAX_AGE.total_seconds() // 60),
            "required_artifacts": sorted(REQUIRED_BACKUP_ARTIFACTS),
            "evidence_id": backup_evidence.backup_id if backup_evidence else None,
            "verified": bool(backup_evidence and backup_evidence.verified),
            "restore_instructions_present": bool(
                backup_evidence and backup_evidence.restore_instructions_present
            ),
        },
        "expected_connectivity_change": {
            "ssh_expected_to_be_lost": True,
            "management_address_expected_to_be_removed": True,
            "loss_point": "reload-without-save",
            "required_recovery_path": "physical serial console",
            "automatic_ssh_reconnect_attempted": False,
        },
        "removed_state": [
            "saved startup configuration",
            "locally-created VLAN database",
            "volatile running configuration at reload",
            "configured management IP, SSH, users, and port/VLAN intent",
        ],
        "retained_state": [
            "installed IOS or IOS XE firmware image",
            "boot loader or ROMMON",
            "license entitlement and license state",
            "chassis model and serial identity",
        ],
        "retained_state_boundary": (
            "This plan contains no firmware image deletion, boot-loader mutation, "
            "license reset, hardware secure erase, or arbitrary command operation."
        ),
        "confirmation_requirements": {
            "action_confirmation_phrase": ACTION_CONFIRMATION_PHRASE,
            "target_confirmation_phrase": cisco_switch_target_confirmation_phrase(target),
            "policy_action_id": POLICY_ACTION_ID,
        },
        "executor_contract": {
            "supplied_by_integration": True,
            "accepts_typed_target_bound_payload": True,
            "accepted_operation_ids": [item["operation_id"] for item in operations],
            "raw_user_commands_accepted": False,
            "result_must_echo_plan_and_target_binding": True,
            "single_use_claim_store_required": True,
            "default_executor_available": False,
            "default_claim_store_available": False,
        },
        "blockers": blockers,
        "warnings": [
            "Preview only. No console write, erase, delete, reload, or network request was attempted.",
            "The switch will intentionally lose its configured management and SSH path after reload.",
            "A serial-console reconnect is required to prove setup-wizard or blank state.",
        ],
        "next_safe_action": (
            "Resolve every evidence blocker, review the exact chassis-bound plan, "
            "and provide all guarded apply confirmations in a separate request."
        ),
    }


def apply_cisco_switch_teardown(
    request: CiscoSwitchTeardownApplyRequest,
    *,
    executor: CiscoSwitchTeardownExecutor | None = None,
    claim_store: DestructivePlanClaimStore | None = None,
    policy: CiscoSwitchActionPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _normalized_now(now)
    runtime_provider_mode = _authoritative_provider_mode()
    preview = build_cisco_switch_teardown_preview(
        request.target,
        request.current_evidence,
        request.backup_evidence,
        now=checked_at,
    )
    action_policy = policy or current_lab_action_policy(runtime_provider_mode)
    blockers = list(preview["blockers"])
    blockers.extend(
        _apply_gate_blockers(
            request,
            action_policy,
            preview,
            runtime_provider_mode=runtime_provider_mode,
        )
    )
    if executor is None:
        blockers.append(
            "A dedicated Cisco switch teardown executor must be supplied; "
            "the service has no default hardware executor."
        )
    if claim_store is None:
        blockers.append(
            "An atomic single-use destructive-plan claim store must be supplied; "
            "the service has no default claim store and cannot dispatch a replayable plan."
        )
    blockers = unique_preserving_order(blockers)
    if blockers:
        return {
            "provider_id": PROVIDER_ID,
            "action": "switch-teardown-apply",
            "status": "blocked",
            "checked_at": checked_at.isoformat(),
            "apply_attempted": False,
            "console_writes_attempted": False,
            "operations_attempted": [],
            "plan_digest": preview["plan_digest"],
            "blockers": blockers,
            "warnings": preview["warnings"],
            "next_safe_action": "Resolve every blocker and generate a fresh preview before retrying.",
        }

    claim = _destructive_plan_claim(request.target, preview["plan_digest"], checked_at)
    try:
        claimed = claim_store.claim_once(claim)
    except Exception as exc:  # noqa: BLE001 - claim persistence must fail closed
        return {
            "provider_id": PROVIDER_ID,
            "action": "switch-teardown-apply",
            "status": "blocked",
            "checked_at": checked_at.isoformat(),
            "apply_attempted": False,
            "console_writes_attempted": False,
            "operations_attempted": [],
            "plan_digest": preview["plan_digest"],
            "blockers": [
                "The destructive-plan claim store failed closed before executor dispatch "
                f"({exc.__class__.__name__})."
            ],
            "warnings": preview["warnings"],
            "next_safe_action": "Repair the claim store and generate a fresh preview.",
        }
    if claimed is not True:
        return {
            "provider_id": PROVIDER_ID,
            "action": "switch-teardown-apply",
            "status": "blocked",
            "checked_at": checked_at.isoformat(),
            "apply_attempted": False,
            "console_writes_attempted": False,
            "operations_attempted": [],
            "plan_digest": preview["plan_digest"],
            "blockers": ["This exact destructive plan was already claimed; replay is refused."],
            "warnings": preview["warnings"],
            "next_safe_action": "Collect fresh target evidence and generate a new reviewed plan.",
        }

    operations = _PLATFORM_OPERATIONS[request.target.platform]
    attempted: list[dict[str, Any]] = []
    for operation_id in operations:
        payload = _operation_payload(request, operation_id, preview["plan_digest"])
        try:
            raw_result = executor.execute(operation_id, payload)
            result = CiscoSwitchOperationResult.model_validate(raw_result)
        except ValidationError:
            attempted.append(
                {
                    "operation_id": operation_id.value,
                    "status": "failed",
                    "outcome_code": "executor-invalid-result",
                }
            )
            return _failed_apply_result(
                checked_at=checked_at,
                preview=preview,
                attempted=attempted,
                blocker=(
                    f"Fixed operation {operation_id.value} returned a malformed result; "
                    "no later operation was attempted."
                ),
            )
        except Exception as exc:  # noqa: BLE001 - hardware adapters must fail closed
            attempted.append(
                {
                    "operation_id": operation_id.value,
                    "status": "failed",
                    "outcome_code": f"executor-exception-{exc.__class__.__name__.lower()}",
                }
            )
            return _failed_apply_result(
                checked_at=checked_at,
                preview=preview,
                attempted=attempted,
                blocker=(
                    f"Fixed operation {operation_id.value} failed inside the supplied executor; "
                    "no later operation was attempted."
                ),
            )

        if (
            result.operation_id != operation_id
            or result.reviewed_plan_digest != payload.reviewed_plan_digest
            or result.target_binding_digest_sha256 != payload.target_binding_digest_sha256
            or not result.live_console_identity_matched
        ):
            attempted.append(
                {
                    "operation_id": operation_id.value,
                    "status": "failed",
                    "outcome_code": "executor-binding-echo-mismatch",
                }
            )
            return _failed_apply_result(
                checked_at=checked_at,
                preview=preview,
                attempted=attempted,
                blocker=(
                    "The executor did not echo the exact operation, reviewed plan, and "
                    "target binding or did not prove a live console identity match; "
                    "execution stopped."
                ),
            )

        attempted.append(
            {
                "operation_id": operation_id.value,
                "payload_contract_version": payload.contract_version,
                "reviewed_plan_digest": payload.reviewed_plan_digest,
                "target_binding_digest_sha256": payload.target_binding_digest_sha256,
                "status": "completed" if result.succeeded else "failed",
                "outcome_code": result.outcome_code,
            }
        )
        if not result.succeeded:
            return _failed_apply_result(
                checked_at=checked_at,
                preview=preview,
                attempted=attempted,
                blocker=(
                    f"Fixed operation {operation_id.value} did not complete; "
                    "no later operation was attempted."
                ),
            )

    return {
        "provider_id": PROVIDER_ID,
        "action": "switch-teardown-apply",
        "status": "completed_pending_validation",
        "checked_at": checked_at.isoformat(),
        "apply_attempted": True,
        "console_writes_attempted": True,
        "single_use_plan_claimed": True,
        "operations_attempted": attempted,
        "plan_digest": preview["plan_digest"],
        "expected_connectivity_change": preview["expected_connectivity_change"],
        "blockers": [],
        "warnings": [
            "The management and SSH path is expected to be unavailable.",
            "Do not configure the switch until blank-state validation finishes over serial console.",
        ],
        "next_safe_action": (
            "Reconnect through the same serial console and run switch teardown validation."
        ),
    }


def validate_cisco_switch_teardown(
    target: CiscoSwitchTarget,
    baseline_evidence: CiscoPrivilegedSerialEvidence,
    current_evidence: CiscoSwitchBlankStateEvidence,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _normalized_now(now)
    blockers = _baseline_serial_evidence_blockers(
        target,
        baseline_evidence,
        current_evidence=current_evidence,
    )
    blockers.extend(_blank_state_identity_blockers(target, current_evidence))
    blockers.extend(
        _freshness_blockers(
            current_evidence.observed_at,
            now=checked_at,
            maximum_age=VALIDATION_EVIDENCE_MAX_AGE,
            label="Post-reload serial-console evidence",
        )
    )
    if not current_evidence.console_reconnected:
        blockers.append("The physical serial console must reconnect after reload.")
    if current_evidence.startup_config_present is not False:
        blockers.append("Read-only console evidence must prove startup configuration is absent.")
    if current_evidence.vlan_database_present is not False:
        blockers.append("Read-only console evidence must prove the VLAN database is absent.")
    if current_evidence.running_config_state != "factory-default":
        blockers.append("Read-only console evidence must identify a factory-default running state.")
    if current_evidence.firmware_version != baseline_evidence.firmware_version:
        blockers.append("Installed IOS/IOS XE firmware changed from the reviewed baseline.")
    if (
        current_evidence.license_state_digest_sha256
        != baseline_evidence.license_state_digest_sha256
    ):
        blockers.append("License state changed from the reviewed baseline.")

    blank_prompt = current_evidence.prompt_state in {
        "setup-wizard",
        "initial-dialog",
        "privileged-exec",
    }
    if not blank_prompt:
        blockers.append(
            "Console prompt must show the setup wizard, initial dialog, or factory-default "
            "privileged exec state."
        )
    blockers = unique_preserving_order(blockers)
    identified_state = _identified_blank_state(current_evidence, blockers)
    return {
        "provider_id": PROVIDER_ID,
        "action": "switch-teardown-validation",
        "status": "ready" if not blockers else "blocked",
        "checked_at": checked_at.isoformat(),
        "validation_read_only": True,
        "console_writes_attempted": False,
        "target_binding": {
            "profile_id": target.profile_id,
            "target_id": target.target_id,
            "console_path": target.console_path,
        },
        "chassis_identity": {
            "platform": current_evidence.platform.value,
            "model": current_evidence.chassis_model,
            "serial": current_evidence.chassis_serial,
        },
        "identified_state": identified_state,
        "blank_state": {
            "console_reconnected": current_evidence.console_reconnected,
            "prompt_state": current_evidence.prompt_state,
            "startup_config_present": current_evidence.startup_config_present,
            "vlan_database_present": current_evidence.vlan_database_present,
            "running_config_state": current_evidence.running_config_state,
        },
        "expected_connectivity": {
            "ssh_reachable": current_evidence.ssh_reachable,
            "ssh_required_for_validation": False,
            "serial_console_required": True,
        },
        "retained_state_observed": {
            "firmware_version": current_evidence.firmware_version,
            "firmware_unchanged": (
                current_evidence.firmware_version == baseline_evidence.firmware_version
            ),
            "license_state_digest_sha256": (current_evidence.license_state_digest_sha256),
            "license_state_unchanged": (
                current_evidence.license_state_digest_sha256
                == baseline_evidence.license_state_digest_sha256
            ),
            "firmware_or_license_changed_by_plan": False,
        },
        "blockers": blockers,
        "warnings": [
            "Validation performs no configuration command and does not require SSH reachability."
        ],
        "next_safe_action": (
            "The switch is blank and ready for a new build preview."
            if not blockers
            else "Keep the switch on serial console and resolve the blank-state evidence blockers."
        ),
    }


def _platform_operation_plan(platform: CiscoSwitchPlatform) -> list[dict[str, Any]]:
    return [
        {
            "order": index,
            "platform": platform.value,
            "operation_id": operation.value,
            "intent": _OPERATION_INTENT[operation],
            "executor_input": "fixed-operation-id-only",
            "expected_disconnect": operation
            in {
                CiscoSwitchTeardownOperation.IOS_RELOAD_WITHOUT_SAVE,
                CiscoSwitchTeardownOperation.IOS_XE_RELOAD_WITHOUT_SAVE,
            },
        }
        for index, operation in enumerate(_PLATFORM_OPERATIONS[platform], start=1)
    ]


def _apply_gate_blockers(
    request: CiscoSwitchTeardownApplyRequest,
    policy: CiscoSwitchActionPolicy,
    preview: dict[str, Any],
    *,
    runtime_provider_mode: str,
) -> list[str]:
    blockers: list[str] = []
    if runtime_provider_mode != LOCAL_LAB_READWRITE_MODE:
        blockers.append(
            "The authoritative runtime PROVIDER_MODE must be local-lab-readwrite "
            "for switch teardown."
        )
    if request.provider_mode != runtime_provider_mode:
        blockers.append(
            "Request provider_mode does not match the authoritative runtime provider mode."
        )
    if request.policy_action_id != POLICY_ACTION_ID:
        blockers.append(f"policy_action_id must be exactly {POLICY_ACTION_ID}.")
    blockers.extend(
        unique_strings(
            policy.action_blockers(
                POLICY_ACTION_ID,
                ActionCategory.FACTORY_RESET,
            )
        )
    )
    required_boolean_gates = (
        (
            request.allow_switch_teardown,
            "allow_switch_teardown=true is required.",
        ),
        (
            request.allow_startup_config_erase,
            "allow_startup_config_erase=true is required.",
        ),
        (
            request.allow_vlan_database_erase,
            "allow_vlan_database_erase=true is required.",
        ),
        (
            request.allow_reload,
            "allow_reload=true is required.",
        ),
        (
            request.acknowledge_expected_ssh_loss,
            "acknowledge_expected_ssh_loss=true is required.",
        ),
        (
            request.executor_enabled,
            "executor_enabled=true is required.",
        ),
    )
    blockers.extend(message for enabled, message in required_boolean_gates if not enabled)
    if request.action_confirmation_phrase != ACTION_CONFIRMATION_PHRASE:
        blockers.append(
            f"Exact action confirmation phrase is required: {ACTION_CONFIRMATION_PHRASE}"
        )
    expected_target_phrase = cisco_switch_target_confirmation_phrase(request.target)
    if request.target_confirmation_phrase != expected_target_phrase:
        blockers.append(
            f"Exact chassis-bound target confirmation phrase is required: {expected_target_phrase}"
        )
    if request.reviewed_plan_digest != preview["plan_digest"]:
        blockers.append(
            "reviewed_plan_digest must exactly match the fresh target-bound teardown preview."
        )
    return blockers


def _serial_evidence_blockers(
    target: CiscoSwitchTarget,
    evidence: CiscoPrivilegedSerialEvidence,
    *,
    now: datetime,
) -> list[str]:
    blockers = _identity_blockers(target, evidence)
    blockers.extend(
        _freshness_blockers(
            evidence.observed_at,
            now=now,
            maximum_age=SERIAL_EVIDENCE_MAX_AGE,
            label="Privileged serial-console evidence",
        )
    )
    if evidence.transport != "serial-console":
        blockers.append("Fresh evidence must come from the physical serial console.")
    if evidence.prompt_state != "privileged-exec" or not evidence.privileged:
        blockers.append("Fresh serial-console evidence must prove a privileged exec prompt.")
    if not evidence.exclusive_access:
        blockers.append("Fresh serial-console evidence must prove exclusive console ownership.")
    if not evidence.identity_verified:
        blockers.append("Fresh serial-console evidence must explicitly verify chassis identity.")
    return blockers


def _baseline_serial_evidence_blockers(
    target: CiscoSwitchTarget,
    evidence: CiscoPrivilegedSerialEvidence,
    *,
    current_evidence: CiscoSwitchBlankStateEvidence,
) -> list[str]:
    blockers = _identity_blockers(target, evidence)
    if evidence.transport != "serial-console":
        blockers.append("Reviewed baseline evidence must come from the physical serial console.")
    if evidence.prompt_state != "privileged-exec" or not evidence.privileged:
        blockers.append("Reviewed baseline evidence must prove a privileged exec prompt.")
    if not evidence.exclusive_access:
        blockers.append("Reviewed baseline evidence must prove exclusive console ownership.")
    if not evidence.identity_verified:
        blockers.append("Reviewed baseline evidence must explicitly verify chassis identity.")
    if evidence.observed_at.tzinfo is None or evidence.observed_at.utcoffset() is None:
        blockers.append("Reviewed baseline evidence timestamp must include a timezone.")
    elif current_evidence.observed_at.tzinfo is not None and (
        evidence.observed_at.astimezone(UTC) >= current_evidence.observed_at.astimezone(UTC)
    ):
        blockers.append(
            "Post-reload evidence must be newer than the reviewed pre-teardown baseline."
        )
    return blockers


def _identity_blockers(
    target: CiscoSwitchTarget,
    evidence: CiscoPrivilegedSerialEvidence,
) -> list[str]:
    comparisons = (
        ("profile ID", target.profile_id, evidence.profile_id),
        ("target ID", target.target_id, evidence.target_id),
        ("console path", target.console_path, evidence.console_path),
        ("platform", target.platform, evidence.platform),
        ("chassis model", target.chassis_model, evidence.chassis_model),
        ("chassis serial", target.chassis_serial, evidence.chassis_serial),
    )
    blockers = [
        f"Current console {label} does not match the intended target."
        for label, intended, observed in comparisons
        if intended != observed
    ]
    if target.hostname is not None and target.hostname != evidence.hostname:
        blockers.append("Current console hostname does not match the intended target.")
    if (
        target.management_address is not None
        and target.management_address != evidence.observed_management_address
    ):
        blockers.append("Current console management address does not match the intended target.")
    return blockers


def _backup_evidence_blockers(
    target: CiscoSwitchTarget,
    evidence: CiscoSwitchBackupEvidence | None,
    *,
    now: datetime,
) -> list[str]:
    if evidence is None:
        return [
            "A verified, target-bound switch backup is required before teardown.",
        ]
    comparisons = (
        ("profile ID", target.profile_id, evidence.profile_id),
        ("target ID", target.target_id, evidence.target_id),
        ("platform", target.platform, evidence.platform),
        ("chassis model", target.chassis_model, evidence.chassis_model),
        ("chassis serial", target.chassis_serial, evidence.chassis_serial),
    )
    blockers = [
        f"Backup {label} does not match the intended target."
        for label, intended, observed in comparisons
        if intended != observed
    ]
    blockers.extend(
        _freshness_blockers(
            evidence.captured_at,
            now=now,
            maximum_age=BACKUP_EVIDENCE_MAX_AGE,
            label="Switch backup evidence",
        )
    )
    if not evidence.verified:
        blockers.append("Switch backup evidence must be verified.")
    if not evidence.restore_instructions_present:
        blockers.append("Switch backup evidence must include restore instructions.")
    missing_artifacts = sorted(REQUIRED_BACKUP_ARTIFACTS - set(evidence.artifacts))
    if missing_artifacts:
        blockers.append(
            f"Switch backup evidence is missing required artifacts: {', '.join(missing_artifacts)}."
        )
    if not re.fullmatch(r"[0-9a-fA-F]{64}", evidence.artifact_digest_sha256):
        blockers.append("Switch backup artifact digest must be a full SHA-256 value.")
    return blockers


def _blank_state_identity_blockers(
    target: CiscoSwitchTarget,
    evidence: CiscoSwitchBlankStateEvidence,
) -> list[str]:
    comparisons = (
        ("profile ID", target.profile_id, evidence.profile_id),
        ("target ID", target.target_id, evidence.target_id),
        ("console path", target.console_path, evidence.console_path),
        ("platform", target.platform, evidence.platform),
        ("chassis model", target.chassis_model, evidence.chassis_model),
        ("chassis serial", target.chassis_serial, evidence.chassis_serial),
    )
    return [
        f"Post-reload console {label} does not match the intended target."
        for label, intended, observed in comparisons
        if intended != observed
    ]


def _freshness_blockers(
    observed_at: datetime,
    *,
    now: datetime,
    maximum_age: timedelta,
    label: str,
) -> list[str]:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        return [f"{label} timestamp must include a timezone."]
    observed = observed_at.astimezone(UTC)
    if observed - now > MAX_FUTURE_CLOCK_SKEW:
        return [f"{label} timestamp is too far in the future."]
    if now - observed > maximum_age:
        return [
            f"{label} is stale; it must be no older than "
            f"{int(maximum_age.total_seconds() // 60)} minutes."
        ]
    return []


def _plan_digest(
    target: CiscoSwitchTarget,
    current_evidence: CiscoPrivilegedSerialEvidence,
    backup_evidence: CiscoSwitchBackupEvidence | None,
    operations: list[dict[str, Any]],
) -> str:
    digest_input = {
        "provider_id": PROVIDER_ID,
        "target": target.model_dump(mode="json"),
        "current_evidence": current_evidence.model_dump(mode="json"),
        "backup_evidence": (
            backup_evidence.model_dump(mode="json") if backup_evidence is not None else None
        ),
        "operation_ids": [operation["operation_id"] for operation in operations],
    }
    canonical = json.dumps(
        digest_input,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _operation_payload(
    request: CiscoSwitchTeardownApplyRequest,
    operation_id: CiscoSwitchTeardownOperation,
    plan_digest: str,
) -> CiscoSwitchTeardownOperationPayload:
    target = request.target
    return CiscoSwitchTeardownOperationPayload(
        contract_version=PAYLOAD_CONTRACT_VERSION,
        operation_id=operation_id,
        profile_id=target.profile_id,
        target_id=target.target_id,
        console_path=target.console_path,
        platform=target.platform,
        chassis_model=target.chassis_model,
        chassis_serial=target.chassis_serial,
        hostname=target.hostname,
        management_address=target.management_address,
        serial_evidence_observed_at=request.current_evidence.observed_at,
        backup_id=request.backup_evidence.backup_id,
        backup_artifact_digest_sha256=(request.backup_evidence.artifact_digest_sha256),
        reviewed_plan_digest=plan_digest,
        target_binding_digest_sha256=_target_binding_digest(target),
        require_live_console_identity_exact_match=True,
        abort_on_console_identity_mismatch=True,
    )


def _destructive_plan_claim(
    target: CiscoSwitchTarget,
    plan_digest: str,
    claimed_at: datetime,
) -> DestructivePlanClaim:
    return DestructivePlanClaim(
        provider_id=PROVIDER_ID,
        action_id=POLICY_ACTION_ID,
        plan_digest=plan_digest,
        profile_id=target.profile_id,
        target_id=target.target_id,
        target_binding_digest_sha256=_target_binding_digest(target),
        claimed_at=claimed_at,
    )


def _target_binding_digest(target: CiscoSwitchTarget) -> str:
    canonical = json.dumps(
        target.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _failed_apply_result(
    *,
    checked_at: datetime,
    preview: dict[str, Any],
    attempted: list[dict[str, Any]],
    blocker: str,
) -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "action": "switch-teardown-apply",
        "status": "failed",
        "checked_at": checked_at.isoformat(),
        "apply_attempted": True,
        "console_writes_attempted": True,
        "operations_attempted": attempted,
        "plan_digest": preview["plan_digest"],
        "blockers": [blocker],
        "warnings": [
            "Execution stopped at the first incomplete fixed operation.",
            "Keep the physical serial console connected and inspect state before any retry.",
        ],
        "next_safe_action": (
            "Generate fresh serial-console and backup evidence before deciding whether to retry."
        ),
    }


def _identified_blank_state(
    evidence: CiscoSwitchBlankStateEvidence,
    blockers: list[str],
) -> str:
    if blockers:
        return "not-proven-blank"
    if evidence.prompt_state in {"setup-wizard", "initial-dialog"}:
        return "setup-wizard-blank"
    return "factory-default-exec-blank"


def _target_identity(target: CiscoSwitchTarget) -> dict[str, str | None]:
    return {
        "platform": target.platform.value,
        "model": target.chassis_model,
        "serial": target.chassis_serial,
        "hostname": target.hostname,
    }


def _serial_identity(
    evidence: CiscoPrivilegedSerialEvidence,
) -> dict[str, str | None]:
    return {
        "platform": evidence.platform.value,
        "model": evidence.chassis_model,
        "serial": evidence.chassis_serial,
        "hostname": evidence.hostname,
    }


def _normalized_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return value.astimezone(UTC)


def _authoritative_provider_mode() -> str:
    return settings.provider_mode
