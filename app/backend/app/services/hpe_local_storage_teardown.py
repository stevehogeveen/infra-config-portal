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

PROVIDER_ID = "hpe-local-storage-teardown"
POLICY_ACTION_ID = "ilo-redfish.local-storage-teardown"

ACTION_CONFIRMATION_PHRASE = "DELETE ALL HPE LOCAL LOGICAL DRIVES"
PAYLOAD_CONTRACT_VERSION = "hpe-gen10-local-storage-teardown-v1"
INVENTORY_EVIDENCE_MAX_AGE = timedelta(minutes=5)
VALIDATION_EVIDENCE_MAX_AGE = timedelta(minutes=10)
DELETION_METHOD_PROOF_MAX_AGE = timedelta(days=30)
MAX_FUTURE_CLOCK_SKEW = timedelta(seconds=30)


class HpeLocalStorageTeardownOperation(str, Enum):
    DELETE_EXACT_REVIEWED_LOGICAL_DRIVES = (
        "hpe-gen10.local-storage.delete-exact-reviewed-logical-drives"
    )
    READ_ONLY_VALIDATE_ZERO_LOGICAL_DRIVES = "hpe-gen10.local-storage.validate-zero-logical-drives"


ALLOWED_APPLY_OPERATIONS = frozenset(
    {HpeLocalStorageTeardownOperation.DELETE_EXACT_REVIEWED_LOGICAL_DRIVES}
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class HpeLocalStorageTarget(_StrictModel):
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    ilo_host: str = Field(min_length=1)
    ilo_manager_id: str = Field(min_length=1)
    server_generation: Literal["Gen10"]
    server_model: str = Field(min_length=1)
    server_serial: str = Field(min_length=1)
    controller_id: str = Field(min_length=1)
    controller_model: str = Field(min_length=1)
    controller_serial: str = Field(min_length=1)


class HpeLocalLogicalDrive(_StrictModel):
    logical_drive_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    raid_level: str = Field(min_length=1)
    capacity_bytes: int = Field(ge=1)


class HpeLocalStorageInventoryEvidence(_StrictModel):
    observed_at: datetime
    source: Literal["live-ilo-redfish-inventory"]
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    ilo_host: str = Field(min_length=1)
    ilo_manager_id: str = Field(min_length=1)
    authenticated: bool
    read_only_collection: bool
    inventory_complete: bool
    identity_verified: bool
    server_generation: Literal["Gen10"]
    server_model: str = Field(min_length=1)
    server_serial: str = Field(min_length=1)
    controller_id: str = Field(min_length=1)
    controller_model: str = Field(min_length=1)
    controller_serial: str = Field(min_length=1)
    controller_firmware_version: str = Field(min_length=1)
    ilo_firmware_version: str = Field(min_length=1)
    ilo_configuration_digest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    server_firmware_inventory_digest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    logical_drives: tuple[HpeLocalLogicalDrive, ...]
    physical_drive_ids: tuple[str, ...]
    physical_drive_secure_erase_detected: bool | None = None


class HpeGen10DeletionMethodProof(_StrictModel):
    proof_id: str = Field(min_length=1)
    proved_at: datetime
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    ilo_host: str = Field(min_length=1)
    ilo_manager_id: str = Field(min_length=1)
    server_generation: Literal["Gen10"]
    server_model: str = Field(min_length=1)
    server_serial: str = Field(min_length=1)
    controller_id: str = Field(min_length=1)
    controller_model: str = Field(min_length=1)
    controller_serial: str = Field(min_length=1)
    controller_firmware_version: str = Field(min_length=1)
    ilo_firmware_version: str = Field(min_length=1)
    operation_id: HpeLocalStorageTeardownOperation
    payload_contract_version: Literal["hpe-gen10-local-storage-teardown-v1"]
    proof_artifact_digest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    attended_operator_present: bool
    exact_target_identity_verified: bool
    deletion_method_observed_on_target: bool
    zero_logical_drive_readback_verified: bool
    ilo_identity_and_configuration_retained_verified: bool
    firmware_retained_verified: bool
    physical_drive_secure_erase_not_used: bool


class HpeLocalStorageTeardownApplyRequest(_StrictModel):
    provider_mode: str
    policy_action_id: str
    target: HpeLocalStorageTarget
    current_evidence: HpeLocalStorageInventoryEvidence
    deletion_method_proof: HpeGen10DeletionMethodProof | None = None
    reviewed_plan_digest: str
    action_confirmation_phrase: str
    target_confirmation_phrase: str
    allow_local_storage_teardown: bool = False
    allow_all_logical_drive_deletion: bool = False
    acknowledge_permanent_local_data_loss: bool = False
    acknowledge_esxi_and_local_datastore_removal: bool = False
    acknowledge_attended_commit_if_required: bool = False
    deletion_method_proof_reviewed: bool = False
    retain_ilo_identity_and_configuration: bool = False
    retain_firmware: bool = False
    prohibit_physical_drive_secure_erase: bool = False
    attended_operator_present: bool = False
    executor_enabled: bool = False


class HpeLocalStorageTeardownOperationPayload(_StrictModel):
    contract_version: Literal["hpe-gen10-local-storage-teardown-v1"]
    operation_id: HpeLocalStorageTeardownOperation
    profile_id: str
    target_id: str
    ilo_host: str
    ilo_manager_id: str
    server_serial: str
    controller_id: str
    controller_serial: str
    reviewed_logical_drive_ids: tuple[str, ...]
    reviewed_logical_drive_count: int = Field(ge=1)
    desired_logical_drive_count: Literal[0]
    expected_physical_drive_ids: tuple[str, ...]
    expected_ilo_configuration_digest_sha256: str
    expected_server_firmware_inventory_digest_sha256: str
    deletion_method_proof_id: str
    deletion_method_proof_artifact_digest_sha256: str
    reviewed_plan_digest: str
    retain_ilo_identity_and_configuration: Literal[True]
    retain_firmware: Literal[True]
    physical_drive_secure_erase_permitted: Literal[False]
    require_live_logical_drive_ids_exact_match: Literal[True]
    abort_on_unreviewed_logical_drive: Literal[True]


class HpeLocalStorageOperationResult(_StrictModel):
    operation_id: HpeLocalStorageTeardownOperation
    reviewed_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_logical_drive_ids: tuple[str, ...]
    live_precondition_matched: bool
    succeeded: bool
    outcome_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class HpeLocalStorageTeardownApplyReceipt(_StrictModel):
    receipt_version: Literal["hpe-local-storage-teardown-receipt-v1"]
    provider_id: Literal["hpe-local-storage-teardown"]
    action: Literal["hpe-local-storage-teardown-apply"]
    completed_at: datetime
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    ilo_host: str = Field(min_length=1)
    ilo_manager_id: str = Field(min_length=1)
    server_serial: str = Field(min_length=1)
    controller_id: str = Field(min_length=1)
    controller_serial: str = Field(min_length=1)
    operation_id: HpeLocalStorageTeardownOperation
    reviewed_plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_evidence_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewed_logical_drive_ids: tuple[str, ...]
    outcome_code: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,63}$")


class HpeLocalStorageTeardownExecutor(Protocol):
    def execute(
        self,
        operation_id: HpeLocalStorageTeardownOperation,
        payload: HpeLocalStorageTeardownOperationPayload,
    ) -> HpeLocalStorageOperationResult: ...


class HpeLocalStorageActionPolicy(Protocol):
    def action_blockers(
        self,
        action_id: str,
        category: ActionCategory | str,
    ) -> list[str]: ...


def hpe_local_storage_target_confirmation_phrase(
    target: HpeLocalStorageTarget,
) -> str:
    return (
        f"DELETE LOCAL STORAGE ON {target.server_serial} "
        f"CONTROLLER {target.controller_id}/{target.controller_serial} "
        f"ILO {target.ilo_host} PROFILE {target.profile_id} TARGET {target.target_id}"
    )


def build_hpe_local_storage_teardown_preview(
    target: HpeLocalStorageTarget,
    current_evidence: HpeLocalStorageInventoryEvidence,
    deletion_method_proof: HpeGen10DeletionMethodProof | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _normalized_now(now)
    evidence_blockers = _inventory_evidence_blockers(
        target,
        current_evidence,
        now=checked_at,
        maximum_age=INVENTORY_EVIDENCE_MAX_AGE,
        label="Live iLO storage inventory evidence",
    )
    logical_drives = sorted(
        current_evidence.logical_drives,
        key=lambda item: item.logical_drive_id,
    )
    apply_required = bool(logical_drives)
    method_blockers = (
        _deletion_method_proof_blockers(
            target,
            current_evidence,
            deletion_method_proof,
            now=checked_at,
        )
        if apply_required
        else []
    )
    blockers = unique_preserving_order([*evidence_blockers, *method_blockers])
    plan_digest = _plan_digest(
        target,
        current_evidence,
        deletion_method_proof,
    )
    operation = _operation_preview(current_evidence)

    if blockers:
        status = "blocked"
    elif not apply_required:
        status = "already_down"
    else:
        status = "ready_for_guarded_apply"

    return {
        "provider_id": PROVIDER_ID,
        "action": "hpe-local-storage-teardown-preview",
        "status": status,
        "checked_at": checked_at.isoformat(),
        "destructive": apply_required,
        "apply_required": apply_required,
        "apply_enabled": False,
        "plan_digest": plan_digest,
        "target_binding": {
            "profile_id": target.profile_id,
            "target_id": target.target_id,
            "ilo_host": target.ilo_host,
        },
        "intended_identity": _target_identity(target),
        "observed_identity": _evidence_identity(current_evidence),
        "identity_matches": not _identity_blockers(target, current_evidence),
        "current_local_storage": {
            "logical_drive_count": len(logical_drives),
            "logical_drives": [drive.model_dump(mode="json") for drive in logical_drives],
            "physical_drive_ids": sorted(current_evidence.physical_drive_ids),
        },
        "desired_down_state": {
            "logical_drive_count": 0,
            "logical_drives": [],
            "physical_drives_retained": True,
            "physical_drive_secure_erase": False,
        },
        "operations": [operation] if apply_required else [],
        "removed_state": [
            "all local logical-drive definitions",
            "all data stored on those local logical drives",
            "local ESXi boot and local datastore state, if present",
        ],
        "retained_state": {
            "ilo_manager_identity": current_evidence.ilo_manager_id,
            "ilo_configuration_digest_sha256": (current_evidence.ilo_configuration_digest_sha256),
            "ilo_firmware_version": current_evidence.ilo_firmware_version,
            "server_firmware_inventory_digest_sha256": (
                current_evidence.server_firmware_inventory_digest_sha256
            ),
            "controller_firmware_version": (current_evidence.controller_firmware_version),
            "physical_drive_ids": sorted(current_evidence.physical_drive_ids),
            "physical_drive_secure_erase_permitted": False,
        },
        "retention_boundary": (
            "The teardown intent deletes logical-drive definitions only. It does not "
            "reset iLO, change iLO configuration or identity, update or remove firmware, "
            "initialize the controller, or securely erase physical drives."
        ),
        "deletion_method_proof": {
            "required": apply_required,
            "present": deletion_method_proof is not None,
            "proof_id": (
                deletion_method_proof.proof_id if deletion_method_proof is not None else None
            ),
            "maximum_age_days": DELETION_METHOD_PROOF_MAX_AGE.days,
            "contract_version": PAYLOAD_CONTRACT_VERSION,
            "first_attended_gen10_proof_required": True,
            "vendor_primitive_assumed_by_service": False,
            "blockers": method_blockers,
        },
        "confirmation_requirements": {
            "action_confirmation_phrase": ACTION_CONFIRMATION_PHRASE,
            "target_confirmation_phrase": (hpe_local_storage_target_confirmation_phrase(target)),
            "policy_action_id": POLICY_ACTION_ID,
        },
        "executor_contract": {
            "supplied_by_integration": True,
            "accepts_typed_operation_and_payload_only": True,
            "accepted_apply_operation_ids": sorted(
                operation.value for operation in ALLOWED_APPLY_OPERATIONS
            ),
            "payload_contract_version": PAYLOAD_CONTRACT_VERSION,
            "raw_commands_accepted": False,
            "redfish_uri_or_vendor_payload_defined_here": False,
            "live_logical_drive_ids_must_exactly_match_reviewed_ids": True,
            "single_use_claim_store_required": True,
            "default_executor_available": False,
            "default_claim_store_available": False,
        },
        "blockers": blockers,
        "warnings": [
            "Preview only. No iLO, Redfish, controller, disk, power, or firmware request was attempted.",
            "Deleting every logical drive permanently removes local ESXi and datastore content.",
            "An attended, exact-target Gen10 method proof must exist before an executor may be supplied.",
        ],
        "next_safe_action": _preview_next_action(
            blockers=blockers,
            apply_required=apply_required,
        ),
    }


def apply_hpe_local_storage_teardown(
    request: HpeLocalStorageTeardownApplyRequest,
    *,
    executor: HpeLocalStorageTeardownExecutor | None = None,
    claim_store: DestructivePlanClaimStore | None = None,
    policy: HpeLocalStorageActionPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _normalized_now(now)
    runtime_provider_mode = _authoritative_provider_mode()
    preview = build_hpe_local_storage_teardown_preview(
        request.target,
        request.current_evidence,
        request.deletion_method_proof,
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
    if not preview["apply_required"]:
        blockers.append(
            "Fresh inventory already reports zero local logical drives; destructive apply is not required."
        )
    if executor is None:
        blockers.append(
            "A separately implemented, attended-proof-backed HPE local-storage executor "
            "must be injected; this service has no default hardware executor."
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
            "action": "hpe-local-storage-teardown-apply",
            "status": "blocked",
            "checked_at": checked_at.isoformat(),
            "apply_attempted": False,
            "hardware_writes_attempted": False,
            "operations_attempted": [],
            "plan_digest": preview["plan_digest"],
            "blockers": blockers,
            "warnings": preview["warnings"],
            "next_safe_action": (
                "Resolve every blocker and generate a fresh, exact-target preview before retrying."
            ),
        }

    claim = _destructive_plan_claim(request.target, preview["plan_digest"], checked_at)
    try:
        claimed = claim_store.claim_once(claim)
    except Exception as exc:  # noqa: BLE001 - claim persistence must fail closed
        return {
            "provider_id": PROVIDER_ID,
            "action": "hpe-local-storage-teardown-apply",
            "status": "blocked",
            "checked_at": checked_at.isoformat(),
            "apply_attempted": False,
            "hardware_writes_attempted": False,
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
            "action": "hpe-local-storage-teardown-apply",
            "status": "blocked",
            "checked_at": checked_at.isoformat(),
            "apply_attempted": False,
            "hardware_writes_attempted": False,
            "operations_attempted": [],
            "plan_digest": preview["plan_digest"],
            "blockers": ["This exact destructive plan was already claimed; replay is refused."],
            "warnings": preview["warnings"],
            "next_safe_action": "Collect fresh target evidence and generate a new reviewed plan.",
        }

    proof = request.deletion_method_proof
    if proof is None:  # pragma: no cover - preview blocker is defense in depth
        raise RuntimeError("Deletion method proof unexpectedly missing after guard checks.")
    operation_id = proof.operation_id
    if operation_id not in ALLOWED_APPLY_OPERATIONS:
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code="operation-not-allowlisted",
            blocker=(
                "The proved operation identifier is not in the fixed local-storage "
                "teardown apply allowlist."
            ),
            write_attempted=False,
        )

    payload = _operation_payload(request, preview["plan_digest"], proof)
    try:
        raw_result = executor.execute(operation_id, payload)
        result = HpeLocalStorageOperationResult.model_validate(raw_result)
    except ValidationError:
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code="executor-invalid-result",
            blocker=(
                "The injected executor returned a malformed result for the fixed "
                "operation; no retry or alternate operation was attempted."
            ),
            write_attempted=True,
        )
    except Exception as exc:  # noqa: BLE001 - hardware adapters must fail closed
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code=f"executor-exception-{exc.__class__.__name__.lower()}",
            blocker=(
                "The injected executor raised an exception while handling the fixed "
                "operation; no retry or alternate operation was attempted."
            ),
            write_attempted=True,
        )

    if result.operation_id != operation_id:
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code="executor-operation-id-mismatch",
            blocker=(
                "The executor returned an operation identifier that did not match the "
                "fixed requested operation."
            ),
            write_attempted=True,
        )
    if result.reviewed_plan_digest != preview["plan_digest"]:
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code="executor-plan-digest-mismatch",
            blocker=(
                "The executor did not echo the exact reviewed plan digest; validation "
                "of the attempted target contract failed."
            ),
            write_attempted=True,
        )
    reviewed_ids = tuple(sorted(payload.reviewed_logical_drive_ids))
    echoed_ids = tuple(sorted(result.reviewed_logical_drive_ids))
    if not result.live_precondition_matched or echoed_ids != reviewed_ids:
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code="executor-live-precondition-mismatch",
            blocker=(
                "The executor did not prove that the live logical-drive identity set "
                "exactly matched the reviewed set before deletion."
            ),
            write_attempted=True,
        )
    if not result.succeeded:
        return _failed_apply_result(
            checked_at=checked_at,
            preview=preview,
            operation_id=operation_id,
            outcome_code=result.outcome_code,
            blocker=(
                "The fixed logical-drive teardown operation did not complete. No "
                "fallback, physical-drive erase, or additional operation was attempted."
            ),
            write_attempted=True,
        )

    receipt = _apply_receipt(
        request,
        payload,
        result,
        completed_at=checked_at,
    )
    return {
        "provider_id": PROVIDER_ID,
        "action": "hpe-local-storage-teardown-apply",
        "status": "completed_pending_validation",
        "checked_at": checked_at.isoformat(),
        "apply_attempted": True,
        "hardware_writes_attempted": True,
        "single_use_plan_claimed": True,
        "operations_attempted": [
            {
                "operation_id": operation_id.value,
                "payload_contract_version": payload.contract_version,
                "reviewed_plan_digest": payload.reviewed_plan_digest,
                "status": "completed",
                "outcome_code": result.outcome_code,
            }
        ],
        "plan_digest": preview["plan_digest"],
        "validation_receipt": receipt.model_dump(mode="json"),
        "retention_boundary": preview["retention_boundary"],
        "blockers": [],
        "warnings": [
            "The result remains unverified until fresh read-only iLO inventory proves zero logical drives.",
            "Do not start a new build until iLO configuration, firmware, controller, and physical-drive retention are validated.",
        ],
        "next_safe_action": (
            "Collect fresh read-only iLO inventory and run local-storage teardown validation."
        ),
    }


def validate_hpe_local_storage_teardown(
    target: HpeLocalStorageTarget,
    baseline_evidence: HpeLocalStorageInventoryEvidence,
    current_evidence: HpeLocalStorageInventoryEvidence,
    *,
    apply_receipt: HpeLocalStorageTeardownApplyReceipt,
    reviewed_plan_digest: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _normalized_now(now)
    receipt_time = _aware_datetime_or_fallback(
        apply_receipt.completed_at,
        fallback=checked_at,
    )
    blockers = _apply_receipt_blockers(
        target,
        baseline_evidence,
        apply_receipt,
        reviewed_plan_digest=reviewed_plan_digest,
    )
    blockers.extend(
        _inventory_evidence_blockers(
            target,
            baseline_evidence,
            now=receipt_time,
            maximum_age=INVENTORY_EVIDENCE_MAX_AGE,
            label="Reviewed pre-teardown live iLO storage inventory evidence",
            identity_prefix="Baseline",
        )
    )
    blockers.extend(
        _inventory_evidence_blockers(
            target,
            current_evidence,
            now=checked_at,
            maximum_age=VALIDATION_EVIDENCE_MAX_AGE,
            label="Post-teardown live iLO storage inventory evidence",
        )
    )
    if _aware_datetime(baseline_evidence.observed_at) is not None and (
        _aware_datetime(baseline_evidence.observed_at) >= receipt_time
    ):
        blockers.append(
            "Reviewed baseline evidence must be older than the completed apply receipt."
        )
    if _aware_datetime(current_evidence.observed_at) is not None and (
        _aware_datetime(current_evidence.observed_at) <= receipt_time
    ):
        blockers.append("Post-teardown evidence must be newer than the completed apply receipt.")
    if (
        _aware_datetime(baseline_evidence.observed_at) is not None
        and _aware_datetime(current_evidence.observed_at) is not None
        and _aware_datetime(current_evidence.observed_at)
        <= _aware_datetime(baseline_evidence.observed_at)
    ):
        blockers.append("Post-teardown evidence must be newer than the reviewed baseline.")
    if current_evidence.logical_drives:
        blockers.append("Post-teardown inventory must prove zero local logical drives.")
    if current_evidence.ilo_manager_id != baseline_evidence.ilo_manager_id:
        blockers.append("iLO manager identity changed from the reviewed baseline.")
    if (
        current_evidence.ilo_configuration_digest_sha256
        != baseline_evidence.ilo_configuration_digest_sha256
    ):
        blockers.append("iLO configuration changed from the reviewed baseline.")
    if current_evidence.ilo_firmware_version != baseline_evidence.ilo_firmware_version:
        blockers.append("iLO firmware changed from the reviewed baseline.")
    if (
        current_evidence.server_firmware_inventory_digest_sha256
        != baseline_evidence.server_firmware_inventory_digest_sha256
    ):
        blockers.append("Server firmware inventory changed from the reviewed baseline.")
    if (
        current_evidence.controller_firmware_version
        != baseline_evidence.controller_firmware_version
    ):
        blockers.append("Storage-controller firmware changed from the reviewed baseline.")
    if set(current_evidence.physical_drive_ids) != set(baseline_evidence.physical_drive_ids):
        blockers.append("Physical-drive identity set changed from the reviewed baseline.")
    if current_evidence.physical_drive_secure_erase_detected is not False:
        blockers.append(
            "Post-teardown evidence must explicitly report that no physical-drive secure erase was detected."
        )
    blockers = unique_preserving_order(blockers)
    down_state_proven = not blockers

    return {
        "provider_id": PROVIDER_ID,
        "action": "hpe-local-storage-teardown-validation",
        "status": "ready" if down_state_proven else "blocked",
        "checked_at": checked_at.isoformat(),
        "validation_read_only": True,
        "hardware_writes_attempted": False,
        "target_binding": {
            "profile_id": target.profile_id,
            "target_id": target.target_id,
            "ilo_host": target.ilo_host,
        },
        "apply_binding": {
            "receipt_version": apply_receipt.receipt_version,
            "completed_at": apply_receipt.completed_at.isoformat(),
            "reviewed_plan_digest": apply_receipt.reviewed_plan_digest,
            "baseline_evidence_digest_sha256": (apply_receipt.baseline_evidence_digest_sha256),
            "reviewed_logical_drive_ids": list(apply_receipt.reviewed_logical_drive_ids),
        },
        "desired_down_state": {
            "logical_drive_count": 0,
            "observed_logical_drive_count": len(current_evidence.logical_drives),
            "proven": down_state_proven,
        },
        "retained_state_observed": {
            "ilo_manager_identity_unchanged": (
                current_evidence.ilo_manager_id == baseline_evidence.ilo_manager_id
            ),
            "ilo_configuration_unchanged": (
                current_evidence.ilo_configuration_digest_sha256
                == baseline_evidence.ilo_configuration_digest_sha256
            ),
            "ilo_firmware_unchanged": (
                current_evidence.ilo_firmware_version == baseline_evidence.ilo_firmware_version
            ),
            "server_firmware_inventory_unchanged": (
                current_evidence.server_firmware_inventory_digest_sha256
                == baseline_evidence.server_firmware_inventory_digest_sha256
            ),
            "controller_firmware_unchanged": (
                current_evidence.controller_firmware_version
                == baseline_evidence.controller_firmware_version
            ),
            "physical_drive_identity_set_unchanged": (
                set(current_evidence.physical_drive_ids)
                == set(baseline_evidence.physical_drive_ids)
            ),
            "physical_drive_secure_erase_detected": (
                current_evidence.physical_drive_secure_erase_detected
            ),
        },
        "blockers": blockers,
        "warnings": [
            "Validation uses read-only inventory evidence and performs no iLO, controller, disk, power, or firmware write."
        ],
        "next_safe_action": (
            "Local storage is down and the retained iLO, firmware, controller, and physical-drive boundary is proven."
            if down_state_proven
            else "Resolve the read-only evidence blockers before treating local storage as down."
        ),
    }


def _operation_preview(
    evidence: HpeLocalStorageInventoryEvidence,
) -> dict[str, Any]:
    return {
        "order": 1,
        "operation_id": (
            HpeLocalStorageTeardownOperation.DELETE_EXACT_REVIEWED_LOGICAL_DRIVES.value
        ),
        "effect": "delete-exact-reviewed-local-logical-drive-definitions",
        "reviewed_logical_drive_ids": sorted(
            drive.logical_drive_id for drive in evidence.logical_drives
        ),
        "abort_if_live_logical_drive_ids_differ": True,
        "desired_logical_drive_count": 0,
        "physical_drive_secure_erase": False,
        "ilo_configuration_change": False,
        "firmware_change": False,
        "executor_input": "fixed-typed-operation-and-payload-only",
        "vendor_primitive": "not-defined-until-attended-gen10-proof",
    }


def _operation_payload(
    request: HpeLocalStorageTeardownApplyRequest,
    plan_digest: str,
    proof: HpeGen10DeletionMethodProof,
) -> HpeLocalStorageTeardownOperationPayload:
    evidence = request.current_evidence
    logical_drive_ids = tuple(sorted(drive.logical_drive_id for drive in evidence.logical_drives))
    return HpeLocalStorageTeardownOperationPayload(
        contract_version=PAYLOAD_CONTRACT_VERSION,
        operation_id=proof.operation_id,
        profile_id=request.target.profile_id,
        target_id=request.target.target_id,
        ilo_host=request.target.ilo_host,
        ilo_manager_id=request.target.ilo_manager_id,
        server_serial=request.target.server_serial,
        controller_id=request.target.controller_id,
        controller_serial=request.target.controller_serial,
        reviewed_logical_drive_ids=logical_drive_ids,
        reviewed_logical_drive_count=len(logical_drive_ids),
        desired_logical_drive_count=0,
        expected_physical_drive_ids=tuple(sorted(evidence.physical_drive_ids)),
        expected_ilo_configuration_digest_sha256=(evidence.ilo_configuration_digest_sha256),
        expected_server_firmware_inventory_digest_sha256=(
            evidence.server_firmware_inventory_digest_sha256
        ),
        deletion_method_proof_id=proof.proof_id,
        deletion_method_proof_artifact_digest_sha256=(proof.proof_artifact_digest_sha256),
        reviewed_plan_digest=plan_digest,
        retain_ilo_identity_and_configuration=True,
        retain_firmware=True,
        physical_drive_secure_erase_permitted=False,
        require_live_logical_drive_ids_exact_match=True,
        abort_on_unreviewed_logical_drive=True,
    )


def _apply_gate_blockers(
    request: HpeLocalStorageTeardownApplyRequest,
    policy: HpeLocalStorageActionPolicy,
    preview: dict[str, Any],
    *,
    runtime_provider_mode: str,
) -> list[str]:
    blockers: list[str] = []
    if runtime_provider_mode != LOCAL_LAB_READWRITE_MODE:
        blockers.append(
            "The authoritative runtime PROVIDER_MODE must be local-lab-readwrite "
            "for HPE local-storage teardown."
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
            request.allow_local_storage_teardown,
            "allow_local_storage_teardown=true is required.",
        ),
        (
            request.allow_all_logical_drive_deletion,
            "allow_all_logical_drive_deletion=true is required.",
        ),
        (
            request.acknowledge_permanent_local_data_loss,
            "acknowledge_permanent_local_data_loss=true is required.",
        ),
        (
            request.acknowledge_esxi_and_local_datastore_removal,
            "acknowledge_esxi_and_local_datastore_removal=true is required.",
        ),
        (
            request.acknowledge_attended_commit_if_required,
            "acknowledge_attended_commit_if_required=true is required.",
        ),
        (
            request.deletion_method_proof_reviewed,
            "deletion_method_proof_reviewed=true is required.",
        ),
        (
            request.retain_ilo_identity_and_configuration,
            "retain_ilo_identity_and_configuration=true is required.",
        ),
        (
            request.retain_firmware,
            "retain_firmware=true is required.",
        ),
        (
            request.prohibit_physical_drive_secure_erase,
            "prohibit_physical_drive_secure_erase=true is required.",
        ),
        (
            request.attended_operator_present,
            "attended_operator_present=true is required.",
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
    expected_target_phrase = hpe_local_storage_target_confirmation_phrase(request.target)
    if request.target_confirmation_phrase != expected_target_phrase:
        blockers.append(
            f"Exact target-bound confirmation phrase is required: {expected_target_phrase}"
        )
    if request.reviewed_plan_digest != preview["plan_digest"]:
        blockers.append(
            "reviewed_plan_digest must exactly match the fresh, target-bound teardown preview."
        )
    return blockers


def _inventory_evidence_blockers(
    target: HpeLocalStorageTarget,
    evidence: HpeLocalStorageInventoryEvidence,
    *,
    now: datetime,
    maximum_age: timedelta,
    label: str,
    identity_prefix: str = "Current inventory",
) -> list[str]:
    blockers = _identity_blockers(target, evidence, prefix=identity_prefix)
    blockers.extend(
        _freshness_blockers(
            evidence.observed_at,
            now=now,
            maximum_age=maximum_age,
            label=label,
        )
    )
    if not evidence.authenticated:
        blockers.append(f"{label} must prove authenticated iLO access.")
    if not evidence.read_only_collection:
        blockers.append(f"{label} must come from a read-only collection.")
    if not evidence.inventory_complete:
        blockers.append(f"{label} must report complete local-storage inventory.")
    if not evidence.identity_verified:
        blockers.append(f"{label} must explicitly verify target identity.")
    if not evidence.physical_drive_ids:
        blockers.append(f"{label} must identify the installed physical drives.")
    duplicate_logical_ids = _duplicates(drive.logical_drive_id for drive in evidence.logical_drives)
    if duplicate_logical_ids:
        blockers.append(
            f"{label} contains duplicate logical-drive IDs: {', '.join(duplicate_logical_ids)}."
        )
    duplicate_physical_ids = _duplicates(evidence.physical_drive_ids)
    if duplicate_physical_ids:
        blockers.append(
            f"{label} contains duplicate physical-drive IDs: {', '.join(duplicate_physical_ids)}."
        )
    return blockers


def _identity_blockers(
    target: HpeLocalStorageTarget,
    evidence: HpeLocalStorageInventoryEvidence,
    *,
    prefix: str = "Current inventory",
) -> list[str]:
    comparisons = (
        ("profile ID", target.profile_id, evidence.profile_id),
        ("target ID", target.target_id, evidence.target_id),
        ("iLO host", target.ilo_host, evidence.ilo_host),
        ("iLO manager ID", target.ilo_manager_id, evidence.ilo_manager_id),
        ("server generation", target.server_generation, evidence.server_generation),
        ("server model", target.server_model, evidence.server_model),
        ("server serial", target.server_serial, evidence.server_serial),
        ("controller ID", target.controller_id, evidence.controller_id),
        ("controller model", target.controller_model, evidence.controller_model),
        ("controller serial", target.controller_serial, evidence.controller_serial),
    )
    return [
        f"{prefix} {label} does not match the intended target."
        for label, intended, observed in comparisons
        if intended != observed
    ]


def _deletion_method_proof_blockers(
    target: HpeLocalStorageTarget,
    evidence: HpeLocalStorageInventoryEvidence,
    proof: HpeGen10DeletionMethodProof | None,
    *,
    now: datetime,
) -> list[str]:
    if proof is None:
        return [
            "The first attended HPE Gen10 logical-drive deletion-method proof is required "
            "for this exact iLO, server, controller, and firmware tuple. This service "
            "does not assume or implement a Redfish deletion primitive."
        ]
    comparisons = (
        ("profile ID", target.profile_id, proof.profile_id),
        ("target ID", target.target_id, proof.target_id),
        ("iLO host", target.ilo_host, proof.ilo_host),
        ("iLO manager ID", target.ilo_manager_id, proof.ilo_manager_id),
        ("server generation", target.server_generation, proof.server_generation),
        ("server model", target.server_model, proof.server_model),
        ("server serial", target.server_serial, proof.server_serial),
        ("controller ID", target.controller_id, proof.controller_id),
        ("controller model", target.controller_model, proof.controller_model),
        ("controller serial", target.controller_serial, proof.controller_serial),
        (
            "controller firmware",
            evidence.controller_firmware_version,
            proof.controller_firmware_version,
        ),
        (
            "iLO firmware",
            evidence.ilo_firmware_version,
            proof.ilo_firmware_version,
        ),
    )
    blockers = [
        f"Deletion-method proof {label} does not match current target evidence."
        for label, intended, observed in comparisons
        if intended != observed
    ]
    blockers.extend(
        _freshness_blockers(
            proof.proved_at,
            now=now,
            maximum_age=DELETION_METHOD_PROOF_MAX_AGE,
            label="Attended Gen10 deletion-method proof",
        )
    )
    if proof.operation_id not in ALLOWED_APPLY_OPERATIONS:
        blockers.append("Deletion-method proof operation ID is not in the fixed apply allowlist.")
    proof_requirements = (
        (
            proof.attended_operator_present,
            "Deletion-method proof must record an attended operator.",
        ),
        (
            proof.exact_target_identity_verified,
            "Deletion-method proof must verify the exact target identity.",
        ),
        (
            proof.deletion_method_observed_on_target,
            "Deletion-method proof must observe the method on the exact Gen10 target.",
        ),
        (
            proof.zero_logical_drive_readback_verified,
            "Deletion-method proof must verify zero logical drives by readback.",
        ),
        (
            proof.ilo_identity_and_configuration_retained_verified,
            "Deletion-method proof must verify retained iLO identity and configuration.",
        ),
        (
            proof.firmware_retained_verified,
            "Deletion-method proof must verify retained iLO, server, and controller firmware.",
        ),
        (
            proof.physical_drive_secure_erase_not_used,
            "Deletion-method proof must verify that physical-drive secure erase was not used.",
        ),
    )
    blockers.extend(message for verified, message in proof_requirements if not verified)
    if not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        proof.proof_artifact_digest_sha256,
    ):
        blockers.append("Deletion-method proof artifact digest must be a full SHA-256 value.")
    return blockers


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
        minutes = int(maximum_age.total_seconds() // 60)
        return [f"{label} is stale; it must be no older than {minutes} minutes."]
    return []


def _plan_digest(
    target: HpeLocalStorageTarget,
    evidence: HpeLocalStorageInventoryEvidence,
    proof: HpeGen10DeletionMethodProof | None,
) -> str:
    evidence_payload = evidence.model_dump(mode="json")
    evidence_payload["logical_drives"] = sorted(
        evidence_payload["logical_drives"],
        key=lambda item: item["logical_drive_id"],
    )
    evidence_payload["physical_drive_ids"] = sorted(evidence_payload["physical_drive_ids"])
    digest_input = {
        "provider_id": PROVIDER_ID,
        "payload_contract_version": PAYLOAD_CONTRACT_VERSION,
        "operation_id": (
            HpeLocalStorageTeardownOperation.DELETE_EXACT_REVIEWED_LOGICAL_DRIVES.value
        ),
        "target": target.model_dump(mode="json"),
        "current_evidence": evidence_payload,
        "deletion_method_proof": (proof.model_dump(mode="json") if proof is not None else None),
        "desired_logical_drive_count": 0,
        "retention": {
            "ilo_identity_and_configuration": True,
            "firmware": True,
            "physical_drives": True,
            "physical_drive_secure_erase": False,
        },
    }
    canonical = json.dumps(
        digest_input,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _apply_receipt(
    request: HpeLocalStorageTeardownApplyRequest,
    payload: HpeLocalStorageTeardownOperationPayload,
    result: HpeLocalStorageOperationResult,
    *,
    completed_at: datetime,
) -> HpeLocalStorageTeardownApplyReceipt:
    target = request.target
    return HpeLocalStorageTeardownApplyReceipt(
        receipt_version="hpe-local-storage-teardown-receipt-v1",
        provider_id=PROVIDER_ID,
        action="hpe-local-storage-teardown-apply",
        completed_at=completed_at,
        profile_id=target.profile_id,
        target_id=target.target_id,
        ilo_host=target.ilo_host,
        ilo_manager_id=target.ilo_manager_id,
        server_serial=target.server_serial,
        controller_id=target.controller_id,
        controller_serial=target.controller_serial,
        operation_id=payload.operation_id,
        reviewed_plan_digest=payload.reviewed_plan_digest,
        baseline_evidence_digest_sha256=_inventory_evidence_digest(request.current_evidence),
        reviewed_logical_drive_ids=payload.reviewed_logical_drive_ids,
        outcome_code=result.outcome_code,
    )


def _apply_receipt_blockers(
    target: HpeLocalStorageTarget,
    baseline_evidence: HpeLocalStorageInventoryEvidence,
    receipt: HpeLocalStorageTeardownApplyReceipt,
    *,
    reviewed_plan_digest: str,
) -> list[str]:
    comparisons = (
        ("profile ID", target.profile_id, receipt.profile_id),
        ("target ID", target.target_id, receipt.target_id),
        ("iLO host", target.ilo_host, receipt.ilo_host),
        ("iLO manager ID", target.ilo_manager_id, receipt.ilo_manager_id),
        ("server serial", target.server_serial, receipt.server_serial),
        ("controller ID", target.controller_id, receipt.controller_id),
        ("controller serial", target.controller_serial, receipt.controller_serial),
    )
    blockers = [
        f"Apply receipt {label} does not match the intended target."
        for label, intended, observed in comparisons
        if intended != observed
    ]
    if receipt.completed_at.tzinfo is None or receipt.completed_at.utcoffset() is None:
        blockers.append("Apply receipt timestamp must include a timezone.")
    if receipt.operation_id not in ALLOWED_APPLY_OPERATIONS:
        blockers.append("Apply receipt operation ID is not in the fixed teardown allowlist.")
    if receipt.reviewed_plan_digest != reviewed_plan_digest:
        blockers.append("Apply receipt does not match the reviewed teardown plan digest.")
    if receipt.baseline_evidence_digest_sha256 != _inventory_evidence_digest(baseline_evidence):
        blockers.append("Apply receipt is not bound to the supplied baseline evidence.")
    reviewed_ids = tuple(sorted(receipt.reviewed_logical_drive_ids))
    baseline_ids = tuple(
        sorted(drive.logical_drive_id for drive in baseline_evidence.logical_drives)
    )
    if not reviewed_ids:
        blockers.append("Apply receipt must identify the deleted logical drives.")
    if reviewed_ids != baseline_ids:
        blockers.append("Apply receipt logical-drive IDs do not match the reviewed baseline.")
    return blockers


def _inventory_evidence_digest(
    evidence: HpeLocalStorageInventoryEvidence,
) -> str:
    payload = evidence.model_dump(mode="json")
    payload["logical_drives"] = sorted(
        payload["logical_drives"],
        key=lambda item: item["logical_drive_id"],
    )
    payload["physical_drive_ids"] = sorted(payload["physical_drive_ids"])
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _destructive_plan_claim(
    target: HpeLocalStorageTarget,
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


def _target_binding_digest(target: HpeLocalStorageTarget) -> str:
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
    operation_id: HpeLocalStorageTeardownOperation,
    outcome_code: str,
    blocker: str,
    write_attempted: bool,
) -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "action": "hpe-local-storage-teardown-apply",
        "status": "failed",
        "checked_at": checked_at.isoformat(),
        "apply_attempted": write_attempted,
        "hardware_writes_attempted": write_attempted,
        "operations_attempted": [
            {
                "operation_id": operation_id.value,
                "status": "failed",
                "outcome_code": outcome_code,
            }
        ],
        "plan_digest": preview["plan_digest"],
        "blockers": [blocker],
        "warnings": [
            "Execution stopped at the first fixed operation.",
            "No fallback, raw command, physical-drive secure erase, iLO reset, or firmware operation was attempted.",
        ],
        "next_safe_action": (
            "Collect fresh read-only inventory and inspect the exact target before deciding whether to retry."
        ),
    }


def _target_identity(target: HpeLocalStorageTarget) -> dict[str, str]:
    return {
        "ilo_manager_id": target.ilo_manager_id,
        "server_generation": target.server_generation,
        "server_model": target.server_model,
        "server_serial": target.server_serial,
        "controller_id": target.controller_id,
        "controller_model": target.controller_model,
        "controller_serial": target.controller_serial,
    }


def _evidence_identity(
    evidence: HpeLocalStorageInventoryEvidence,
) -> dict[str, str]:
    return {
        "ilo_manager_id": evidence.ilo_manager_id,
        "server_generation": evidence.server_generation,
        "server_model": evidence.server_model,
        "server_serial": evidence.server_serial,
        "controller_id": evidence.controller_id,
        "controller_model": evidence.controller_model,
        "controller_serial": evidence.controller_serial,
    }


def _duplicates(values: Any) -> list[str]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        normalized = str(value)
        if normalized in seen:
            duplicate.add(normalized)
        seen.add(normalized)
    return sorted(duplicate)


def _preview_next_action(*, blockers: list[str], apply_required: bool) -> str:
    if not apply_required and not blockers:
        return "Local storage already has zero logical drives; run read-only validation."
    if blockers:
        return (
            "Resolve fresh identity/inventory blockers and complete the first attended "
            "Gen10 deletion-method proof before any executor integration."
        )
    return (
        "Review the digest-bound plan and provide every destructive confirmation "
        "through a separately guarded apply request."
    )


def _normalized_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include a timezone")
    return value.astimezone(UTC)


def _aware_datetime(value: datetime) -> datetime | None:
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(UTC)


def _aware_datetime_or_fallback(
    value: datetime,
    *,
    fallback: datetime,
) -> datetime:
    return _aware_datetime(value) or fallback


def _authoritative_provider_mode() -> str:
    return settings.provider_mode
