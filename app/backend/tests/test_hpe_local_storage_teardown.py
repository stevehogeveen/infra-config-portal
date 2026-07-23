from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.providers.action_policy import ActionCategory
from app.services import hpe_local_storage_teardown as teardown
from app.services.destructive_plan_claims import DestructivePlanClaim

NOW = datetime(2026, 7, 23, 18, 0, tzinfo=UTC)
VALIDATION_NOW = NOW + timedelta(minutes=2)


class AllowPolicy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ActionCategory | str]] = []

    def action_blockers(
        self,
        action_id: str,
        category: ActionCategory | str,
    ) -> list[str]:
        self.calls.append((action_id, category))
        return []


class BlockPolicy:
    def action_blockers(
        self,
        action_id: str,
        category: ActionCategory | str,
    ) -> list[str]:
        assert action_id == teardown.POLICY_ACTION_ID
        assert category == ActionCategory.FACTORY_RESET
        return ["Policy refused factory-reset category."]


class FakeExecutor:
    def __init__(
        self,
        *,
        fail: bool = False,
        raise_error: bool = False,
        mismatch_operation: bool = False,
        mismatch_digest: bool = False,
        mismatch_ids: bool = False,
        precondition_failed: bool = False,
        malformed_result: bool = False,
    ) -> None:
        self.calls: list[
            tuple[
                teardown.HpeLocalStorageTeardownOperation,
                teardown.HpeLocalStorageTeardownOperationPayload,
            ]
        ] = []
        self.fail = fail
        self.raise_error = raise_error
        self.mismatch_operation = mismatch_operation
        self.mismatch_digest = mismatch_digest
        self.mismatch_ids = mismatch_ids
        self.precondition_failed = precondition_failed
        self.malformed_result = malformed_result

    def execute(
        self,
        operation_id: teardown.HpeLocalStorageTeardownOperation,
        payload: teardown.HpeLocalStorageTeardownOperationPayload,
    ) -> teardown.HpeLocalStorageOperationResult | dict[str, Any]:
        self.calls.append((operation_id, payload))
        if self.raise_error:
            raise RuntimeError("sensitive adapter detail")
        if self.malformed_result:
            return {"operation_id": operation_id.value}
        returned_operation = (
            teardown.HpeLocalStorageTeardownOperation.READ_ONLY_VALIDATE_ZERO_LOGICAL_DRIVES
            if self.mismatch_operation
            else operation_id
        )
        return teardown.HpeLocalStorageOperationResult(
            operation_id=returned_operation,
            reviewed_plan_digest=(
                "0" * 64 if self.mismatch_digest else payload.reviewed_plan_digest
            ),
            reviewed_logical_drive_ids=(
                ("unreviewed-logical-drive",)
                if self.mismatch_ids
                else payload.reviewed_logical_drive_ids
            ),
            live_precondition_matched=not self.precondition_failed,
            succeeded=not self.fail,
            outcome_code="completed" if not self.fail else "device-refused",
        )


class FakeClaimStore:
    def __init__(self, *, raise_error: bool = False) -> None:
        self.claims: list[DestructivePlanClaim] = []
        self._claimed: set[str] = set()
        self.raise_error = raise_error

    def claim_once(self, claim: DestructivePlanClaim) -> bool:
        self.claims.append(claim)
        if self.raise_error:
            raise RuntimeError("claim backend detail")
        if claim.plan_digest in self._claimed:
            return False
        self._claimed.add(claim.plan_digest)
        return True


@pytest.fixture(autouse=True)
def authoritative_readwrite_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        teardown,
        "_authoritative_provider_mode",
        lambda: "local-lab-readwrite",
    )


def _target(**updates: Any) -> teardown.HpeLocalStorageTarget:
    values: dict[str, Any] = {
        "profile_id": "single-server-lab",
        "target_id": "server-1-local-storage",
        "ilo_host": "192.0.2.201",
        "ilo_manager_id": "manager-1",
        "server_generation": "Gen10",
        "server_model": "HPE DL360 Gen10 LAB",
        "server_serial": "TEST-SERVER-SERIAL",
        "controller_id": "slot-0",
        "controller_model": "HPE Smart Array LAB",
        "controller_serial": "TEST-CONTROLLER-SERIAL",
    }
    values.update(updates)
    return teardown.HpeLocalStorageTarget(**values)


def _logical_drive(
    logical_drive_id: str = "logical-1",
    **updates: Any,
) -> teardown.HpeLocalLogicalDrive:
    values: dict[str, Any] = {
        "logical_drive_id": logical_drive_id,
        "name": f"Test {logical_drive_id}",
        "raid_level": "RAID1",
        "capacity_bytes": 1000,
    }
    values.update(updates)
    return teardown.HpeLocalLogicalDrive(**values)


def _evidence(
    target: teardown.HpeLocalStorageTarget,
    **updates: Any,
) -> teardown.HpeLocalStorageInventoryEvidence:
    values: dict[str, Any] = {
        "observed_at": NOW - timedelta(minutes=1),
        "source": "live-ilo-redfish-inventory",
        "profile_id": target.profile_id,
        "target_id": target.target_id,
        "ilo_host": target.ilo_host,
        "ilo_manager_id": target.ilo_manager_id,
        "authenticated": True,
        "read_only_collection": True,
        "inventory_complete": True,
        "identity_verified": True,
        "server_generation": target.server_generation,
        "server_model": target.server_model,
        "server_serial": target.server_serial,
        "controller_id": target.controller_id,
        "controller_model": target.controller_model,
        "controller_serial": target.controller_serial,
        "controller_firmware_version": "test-controller-fw",
        "ilo_firmware_version": "test-ilo-fw",
        "ilo_configuration_digest_sha256": "a" * 64,
        "server_firmware_inventory_digest_sha256": "b" * 64,
        "logical_drives": (
            _logical_drive("logical-1"),
            _logical_drive(
                "logical-2",
                name="Test datastore",
                raid_level="RAID5",
                capacity_bytes=2000,
            ),
        ),
        "physical_drive_ids": ("bay-1", "bay-2", "bay-3", "bay-4"),
        "physical_drive_secure_erase_detected": None,
    }
    values.update(updates)
    return teardown.HpeLocalStorageInventoryEvidence(**values)


def _proof(
    target: teardown.HpeLocalStorageTarget,
    evidence: teardown.HpeLocalStorageInventoryEvidence,
    **updates: Any,
) -> teardown.HpeGen10DeletionMethodProof:
    values: dict[str, Any] = {
        "proof_id": "attended-proof-test-001",
        "proved_at": NOW - timedelta(days=1),
        "profile_id": target.profile_id,
        "target_id": target.target_id,
        "ilo_host": target.ilo_host,
        "ilo_manager_id": target.ilo_manager_id,
        "server_generation": target.server_generation,
        "server_model": target.server_model,
        "server_serial": target.server_serial,
        "controller_id": target.controller_id,
        "controller_model": target.controller_model,
        "controller_serial": target.controller_serial,
        "controller_firmware_version": evidence.controller_firmware_version,
        "ilo_firmware_version": evidence.ilo_firmware_version,
        "operation_id": (
            teardown.HpeLocalStorageTeardownOperation.DELETE_EXACT_REVIEWED_LOGICAL_DRIVES
        ),
        "payload_contract_version": teardown.PAYLOAD_CONTRACT_VERSION,
        "proof_artifact_digest_sha256": "c" * 64,
        "attended_operator_present": True,
        "exact_target_identity_verified": True,
        "deletion_method_observed_on_target": True,
        "zero_logical_drive_readback_verified": True,
        "ilo_identity_and_configuration_retained_verified": True,
        "firmware_retained_verified": True,
        "physical_drive_secure_erase_not_used": True,
    }
    values.update(updates)
    return teardown.HpeGen10DeletionMethodProof(**values)


def _apply_request(
    *,
    target: teardown.HpeLocalStorageTarget | None = None,
    current_evidence: teardown.HpeLocalStorageInventoryEvidence | None = None,
    deletion_method_proof: teardown.HpeGen10DeletionMethodProof | None = None,
    include_default_proof: bool = True,
    **updates: Any,
) -> teardown.HpeLocalStorageTeardownApplyRequest:
    selected_target = target or _target()
    selected_evidence = current_evidence or _evidence(selected_target)
    selected_proof = deletion_method_proof
    if selected_proof is None and include_default_proof:
        selected_proof = _proof(selected_target, selected_evidence)
    preview = teardown.build_hpe_local_storage_teardown_preview(
        selected_target,
        selected_evidence,
        selected_proof,
        now=NOW,
    )
    values: dict[str, Any] = {
        "provider_mode": "local-lab-readwrite",
        "policy_action_id": teardown.POLICY_ACTION_ID,
        "target": selected_target,
        "current_evidence": selected_evidence,
        "deletion_method_proof": selected_proof,
        "reviewed_plan_digest": preview["plan_digest"],
        "action_confirmation_phrase": teardown.ACTION_CONFIRMATION_PHRASE,
        "target_confirmation_phrase": (
            teardown.hpe_local_storage_target_confirmation_phrase(selected_target)
        ),
        "allow_local_storage_teardown": True,
        "allow_all_logical_drive_deletion": True,
        "acknowledge_permanent_local_data_loss": True,
        "acknowledge_esxi_and_local_datastore_removal": True,
        "acknowledge_attended_commit_if_required": True,
        "deletion_method_proof_reviewed": True,
        "retain_ilo_identity_and_configuration": True,
        "retain_firmware": True,
        "prohibit_physical_drive_secure_erase": True,
        "attended_operator_present": True,
        "executor_enabled": True,
    }
    values.update(updates)
    return teardown.HpeLocalStorageTeardownApplyRequest(**values)


def test_preview_blocks_until_first_attended_gen10_deletion_method_is_proven() -> None:
    target = _target()
    result = teardown.build_hpe_local_storage_teardown_preview(
        target,
        _evidence(target),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["apply_enabled"] is False
    assert result["deletion_method_proof"]["first_attended_gen10_proof_required"] is True
    assert result["deletion_method_proof"]["vendor_primitive_assumed_by_service"] is False
    assert any("first attended HPE Gen10" in blocker for blocker in result["blockers"])
    assert result["operations"][0]["vendor_primitive"] == ("not-defined-until-attended-gen10-proof")
    assert result["executor_contract"]["raw_commands_accepted"] is False
    assert result["executor_contract"]["redfish_uri_or_vendor_payload_defined_here"] is False
    assert (
        result["executor_contract"]["live_logical_drive_ids_must_exactly_match_reviewed_ids"]
        is True
    )
    assert result["executor_contract"]["single_use_claim_store_required"] is True


def test_preview_is_exact_target_bound_and_preserves_nonstorage_state() -> None:
    target = _target()
    evidence = _evidence(target)
    proof = _proof(target, evidence)

    result = teardown.build_hpe_local_storage_teardown_preview(
        target,
        evidence,
        proof,
        now=NOW,
    )

    assert result["status"] == "ready_for_guarded_apply"
    assert result["apply_required"] is True
    assert result["identity_matches"] is True
    assert result["intended_identity"] == result["observed_identity"]
    assert result["target_binding"] == {
        "profile_id": "single-server-lab",
        "target_id": "server-1-local-storage",
        "ilo_host": "192.0.2.201",
    }
    assert result["desired_down_state"] == {
        "logical_drive_count": 0,
        "logical_drives": [],
        "physical_drives_retained": True,
        "physical_drive_secure_erase": False,
    }
    assert result["retained_state"]["ilo_manager_identity"] == "manager-1"
    assert result["retained_state"]["ilo_firmware_version"] == "test-ilo-fw"
    assert result["retained_state"]["controller_firmware_version"] == ("test-controller-fw")
    assert result["retained_state"]["physical_drive_secure_erase_permitted"] is False
    assert result["operations"] == [
        {
            "order": 1,
            "operation_id": ("hpe-gen10.local-storage.delete-exact-reviewed-logical-drives"),
            "effect": "delete-exact-reviewed-local-logical-drive-definitions",
            "reviewed_logical_drive_ids": ["logical-1", "logical-2"],
            "abort_if_live_logical_drive_ids_differ": True,
            "desired_logical_drive_count": 0,
            "physical_drive_secure_erase": False,
            "ilo_configuration_change": False,
            "firmware_change": False,
            "executor_input": "fixed-typed-operation-and-payload-only",
            "vendor_primitive": "not-defined-until-attended-gen10-proof",
        }
    ]
    assert result["blockers"] == []


@pytest.mark.parametrize(
    ("evidence_update", "expected"),
    [
        ({"profile_id": "other-profile"}, "profile ID"),
        ({"target_id": "other-target"}, "target ID"),
        ({"ilo_host": "192.0.2.99"}, "iLO host"),
        ({"ilo_manager_id": "other-manager"}, "iLO manager ID"),
        ({"server_model": "OTHER MODEL"}, "server model"),
        ({"server_serial": "OTHER-SERIAL"}, "server serial"),
        ({"controller_id": "slot-9"}, "controller ID"),
        ({"controller_model": "OTHER CONTROLLER"}, "controller model"),
        ({"controller_serial": "OTHER-CONTROLLER"}, "controller serial"),
    ],
)
def test_preview_refuses_every_identity_mismatch(
    evidence_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    evidence = _evidence(target, **evidence_update)

    result = teardown.build_hpe_local_storage_teardown_preview(
        target,
        evidence,
        _proof(target, evidence),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])


@pytest.mark.parametrize(
    ("evidence_update", "expected"),
    [
        ({"observed_at": NOW - timedelta(minutes=6)}, "stale"),
        ({"observed_at": NOW + timedelta(minutes=1)}, "future"),
        ({"authenticated": False}, "authenticated iLO access"),
        ({"read_only_collection": False}, "read-only collection"),
        ({"inventory_complete": False}, "complete local-storage inventory"),
        ({"identity_verified": False}, "verify target identity"),
        ({"physical_drive_ids": ()}, "identify the installed physical drives"),
        (
            {"logical_drives": (_logical_drive(), _logical_drive())},
            "duplicate logical-drive IDs",
        ),
        (
            {"physical_drive_ids": ("bay-1", "bay-1")},
            "duplicate physical-drive IDs",
        ),
    ],
)
def test_preview_requires_fresh_complete_live_readonly_inventory(
    evidence_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    evidence = _evidence(target, **evidence_update)

    result = teardown.build_hpe_local_storage_teardown_preview(
        target,
        evidence,
        _proof(target, evidence),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])


@pytest.mark.parametrize(
    ("proof_update", "expected"),
    [
        ({"profile_id": "other-profile"}, "profile ID"),
        ({"target_id": "other-target"}, "target ID"),
        ({"ilo_host": "192.0.2.99"}, "iLO host"),
        ({"ilo_manager_id": "other-manager"}, "iLO manager ID"),
        ({"server_model": "OTHER MODEL"}, "server model"),
        ({"server_serial": "OTHER-SERIAL"}, "server serial"),
        ({"controller_id": "slot-9"}, "controller ID"),
        ({"controller_model": "OTHER CONTROLLER"}, "controller model"),
        ({"controller_serial": "OTHER-CONTROLLER"}, "controller serial"),
        ({"controller_firmware_version": "other-fw"}, "controller firmware"),
        ({"ilo_firmware_version": "other-fw"}, "iLO firmware"),
        ({"proved_at": NOW - timedelta(days=31)}, "stale"),
        (
            {
                "operation_id": teardown.HpeLocalStorageTeardownOperation.READ_ONLY_VALIDATE_ZERO_LOGICAL_DRIVES
            },
            "fixed apply allowlist",
        ),
        ({"attended_operator_present": False}, "attended operator"),
        ({"exact_target_identity_verified": False}, "exact target identity"),
        ({"deletion_method_observed_on_target": False}, "exact Gen10 target"),
        ({"zero_logical_drive_readback_verified": False}, "zero logical drives"),
        (
            {"ilo_identity_and_configuration_retained_verified": False},
            "retained iLO identity",
        ),
        ({"firmware_retained_verified": False}, "retained iLO, server"),
        (
            {"physical_drive_secure_erase_not_used": False},
            "secure erase was not used",
        ),
    ],
)
def test_preview_refuses_untrusted_or_wrong_target_deletion_method_proof(
    proof_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    evidence = _evidence(target)
    proof = _proof(target, evidence, **proof_update)

    result = teardown.build_hpe_local_storage_teardown_preview(
        target,
        evidence,
        proof,
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])


def test_preview_recognizes_zero_logical_drives_as_desired_down_state() -> None:
    target = _target()
    evidence = _evidence(
        target,
        logical_drives=(),
        physical_drive_secure_erase_detected=False,
    )

    result = teardown.build_hpe_local_storage_teardown_preview(
        target,
        evidence,
        now=NOW,
    )

    assert result["status"] == "already_down"
    assert result["apply_required"] is False
    assert result["destructive"] is False
    assert result["operations"] == []
    assert result["blockers"] == []


def test_plan_digest_is_stable_for_inventory_order_and_changes_for_content() -> None:
    target = _target()
    first_evidence = _evidence(target)
    first_proof = _proof(target, first_evidence)
    first = teardown.build_hpe_local_storage_teardown_preview(
        target,
        first_evidence,
        first_proof,
        now=NOW,
    )
    reordered_evidence = _evidence(
        target,
        logical_drives=tuple(reversed(first_evidence.logical_drives)),
        physical_drive_ids=tuple(reversed(first_evidence.physical_drive_ids)),
    )
    reordered = teardown.build_hpe_local_storage_teardown_preview(
        target,
        reordered_evidence,
        _proof(target, reordered_evidence),
        now=NOW,
    )
    changed_evidence = _evidence(
        target,
        logical_drives=(_logical_drive("different-logical-drive"),),
    )
    changed = teardown.build_hpe_local_storage_teardown_preview(
        target,
        changed_evidence,
        _proof(target, changed_evidence),
        now=NOW,
    )

    assert first["plan_digest"] == reordered["plan_digest"]
    assert first["plan_digest"] != changed["plan_digest"]


def test_apply_defaults_to_refuse_without_injected_executor() -> None:
    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["apply_attempted"] is False
    assert result["hardware_writes_attempted"] is False
    assert result["operations_attempted"] == []
    assert any("no default hardware executor" in item for item in result["blockers"])
    assert any("no default claim store" in item for item in result["blockers"])


@pytest.mark.parametrize(
    ("request_update", "expected"),
    [
        ({"provider_mode": "local-readonly"}, "does not match the authoritative runtime"),
        ({"policy_action_id": "lab.factory-reset"}, "policy_action_id"),
        ({"allow_local_storage_teardown": False}, "allow_local_storage_teardown"),
        (
            {"allow_all_logical_drive_deletion": False},
            "allow_all_logical_drive_deletion",
        ),
        (
            {"acknowledge_permanent_local_data_loss": False},
            "acknowledge_permanent_local_data_loss",
        ),
        (
            {"acknowledge_esxi_and_local_datastore_removal": False},
            "acknowledge_esxi_and_local_datastore_removal",
        ),
        (
            {"acknowledge_attended_commit_if_required": False},
            "acknowledge_attended_commit_if_required",
        ),
        (
            {"deletion_method_proof_reviewed": False},
            "deletion_method_proof_reviewed",
        ),
        (
            {"retain_ilo_identity_and_configuration": False},
            "retain_ilo_identity_and_configuration",
        ),
        ({"retain_firmware": False}, "retain_firmware"),
        (
            {"prohibit_physical_drive_secure_erase": False},
            "prohibit_physical_drive_secure_erase",
        ),
        ({"attended_operator_present": False}, "attended_operator_present"),
        ({"executor_enabled": False}, "executor_enabled"),
        ({"action_confirmation_phrase": "DELETE STORAGE"}, "action confirmation"),
        ({"target_confirmation_phrase": "WRONG TARGET"}, "target-bound"),
        ({"reviewed_plan_digest": "wrong-digest"}, "reviewed_plan_digest"),
    ],
)
def test_apply_refuses_every_missing_or_inexact_gate(
    request_update: dict[str, Any],
    expected: str,
) -> None:
    executor = FakeExecutor()

    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(**request_update),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["apply_attempted"] is False
    assert executor.calls == []
    assert any(expected in blocker for blocker in result["blockers"])


def test_apply_requires_factory_reset_policy_approval() -> None:
    executor = FakeExecutor()

    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=BlockPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["Policy refused factory-reset category."]
    assert executor.calls == []


def test_apply_refuses_already_down_state_without_dispatching_executor() -> None:
    target = _target()
    evidence = _evidence(
        target,
        logical_drives=(),
        physical_drive_secure_erase_detected=False,
    )
    executor = FakeExecutor()

    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(
            target=target,
            current_evidence=evidence,
            include_default_proof=False,
        ),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any("already reports zero" in blocker for blocker in result["blockers"])
    assert executor.calls == []


def test_apply_dispatches_only_fixed_typed_operation_and_payload() -> None:
    policy = AllowPolicy()
    executor = FakeExecutor()

    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=policy,
        now=NOW,
    )

    assert result["status"] == "completed_pending_validation"
    assert result["blockers"] == []
    assert len(executor.calls) == 1
    operation_id, payload = executor.calls[0]
    assert operation_id is (
        teardown.HpeLocalStorageTeardownOperation.DELETE_EXACT_REVIEWED_LOGICAL_DRIVES
    )
    assert isinstance(
        payload,
        teardown.HpeLocalStorageTeardownOperationPayload,
    )
    assert payload.operation_id is operation_id
    assert payload.reviewed_logical_drive_ids == ("logical-1", "logical-2")
    assert payload.desired_logical_drive_count == 0
    assert payload.retain_ilo_identity_and_configuration is True
    assert payload.retain_firmware is True
    assert payload.physical_drive_secure_erase_permitted is False
    assert payload.require_live_logical_drive_ids_exact_match is True
    assert payload.abort_on_unreviewed_logical_drive is True
    assert "command" not in payload.model_dump()
    assert "redfish_uri" not in payload.model_dump()
    receipt = teardown.HpeLocalStorageTeardownApplyReceipt.model_validate(
        result["validation_receipt"]
    )
    assert receipt.reviewed_plan_digest == result["plan_digest"]
    assert receipt.reviewed_logical_drive_ids == ("logical-1", "logical-2")
    assert policy.calls == [
        (teardown.POLICY_ACTION_ID, ActionCategory.FACTORY_RESET),
    ]


@pytest.mark.parametrize(
    ("executor", "expected_code"),
    [
        (FakeExecutor(fail=True), "device-refused"),
        (
            FakeExecutor(mismatch_operation=True),
            "executor-operation-id-mismatch",
        ),
        (
            FakeExecutor(mismatch_digest=True),
            "executor-plan-digest-mismatch",
        ),
        (
            FakeExecutor(raise_error=True),
            "executor-exception-runtimeerror",
        ),
        (
            FakeExecutor(mismatch_ids=True),
            "executor-live-precondition-mismatch",
        ),
        (
            FakeExecutor(precondition_failed=True),
            "executor-live-precondition-mismatch",
        ),
        (
            FakeExecutor(malformed_result=True),
            "executor-invalid-result",
        ),
    ],
)
def test_apply_fails_closed_on_executor_contract_failure(
    executor: FakeExecutor,
    expected_code: str,
) -> None:
    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "failed"
    assert len(executor.calls) == 1
    assert result["operations_attempted"][0]["outcome_code"] == expected_code
    assert "sensitive adapter detail" not in str(result)
    assert "secure erase" in result["warnings"][1]


def test_apply_refuses_request_mode_that_disagrees_with_authoritative_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        teardown,
        "_authoritative_provider_mode",
        lambda: "local-readonly",
    )
    executor = FakeExecutor()

    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(provider_mode="local-lab-readwrite"),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["apply_attempted"] is False
    assert executor.calls == []
    assert any("authoritative runtime PROVIDER_MODE" in item for item in result["blockers"])
    assert any("does not match" in item for item in result["blockers"])


def test_apply_claims_plan_once_and_refuses_replay_before_executor_dispatch() -> None:
    request = _apply_request()
    claim_store = FakeClaimStore()
    first_executor = FakeExecutor()
    second_executor = FakeExecutor()

    first = teardown.apply_hpe_local_storage_teardown(
        request,
        executor=first_executor,
        claim_store=claim_store,
        policy=AllowPolicy(),
        now=NOW,
    )
    replay = teardown.apply_hpe_local_storage_teardown(
        request,
        executor=second_executor,
        claim_store=claim_store,
        policy=AllowPolicy(),
        now=NOW,
    )

    assert first["status"] == "completed_pending_validation"
    assert replay["status"] == "blocked"
    assert replay["apply_attempted"] is False
    assert second_executor.calls == []
    assert any("replay is refused" in item for item in replay["blockers"])


def test_contract_models_reject_raw_commands_and_unknown_operations() -> None:
    request_values = _apply_request().model_dump(mode="python")
    request_values["commands"] = ["arbitrary destructive command"]
    target = _target()
    evidence = _evidence(target)
    proof_values = _proof(target, evidence).model_dump(mode="python")
    proof_values["operation_id"] = "arbitrary-operation"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        teardown.HpeLocalStorageTeardownApplyRequest(**request_values)
    with pytest.raises(ValidationError):
        teardown.HpeGen10DeletionMethodProof(**proof_values)


def _validation_binding(
    target: teardown.HpeLocalStorageTarget,
    baseline: teardown.HpeLocalStorageInventoryEvidence,
) -> tuple[teardown.HpeLocalStorageTeardownApplyReceipt, str]:
    result = teardown.apply_hpe_local_storage_teardown(
        _apply_request(target=target, current_evidence=baseline),
        executor=FakeExecutor(),
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )
    assert result["status"] == "completed_pending_validation"
    return (
        teardown.HpeLocalStorageTeardownApplyReceipt.model_validate(result["validation_receipt"]),
        str(result["plan_digest"]),
    )


def test_validation_proves_zero_logical_drives_and_retained_boundary() -> None:
    target = _target()
    baseline = _evidence(target)
    receipt, plan_digest = _validation_binding(target, baseline)
    current = _evidence(
        target,
        observed_at=NOW + timedelta(minutes=1),
        logical_drives=(),
        physical_drive_secure_erase_detected=False,
    )

    result = teardown.validate_hpe_local_storage_teardown(
        target,
        baseline,
        current,
        apply_receipt=receipt,
        reviewed_plan_digest=plan_digest,
        now=VALIDATION_NOW,
    )

    assert result["status"] == "ready"
    assert result["validation_read_only"] is True
    assert result["hardware_writes_attempted"] is False
    assert result["desired_down_state"] == {
        "logical_drive_count": 0,
        "observed_logical_drive_count": 0,
        "proven": True,
    }
    assert all(
        value is True
        for key, value in result["retained_state_observed"].items()
        if key.endswith("_unchanged")
    )
    assert result["retained_state_observed"]["physical_drive_secure_erase_detected"] is False
    assert result["blockers"] == []


@pytest.mark.parametrize(
    ("current_update", "expected"),
    [
        ({"profile_id": "other-profile"}, "profile ID"),
        ({"target_id": "other-target"}, "target ID"),
        ({"ilo_host": "192.0.2.99"}, "iLO host"),
        ({"server_serial": "OTHER-SERIAL"}, "server serial"),
        ({"controller_id": "slot-9"}, "controller ID"),
        ({"controller_model": "OTHER CONTROLLER"}, "controller model"),
        ({"controller_serial": "OTHER-CONTROLLER"}, "controller serial"),
        ({"observed_at": NOW - timedelta(minutes=11)}, "stale"),
        ({"logical_drives": (_logical_drive(),)}, "zero local logical drives"),
        ({"ilo_manager_id": "other-manager"}, "iLO manager identity"),
        ({"ilo_configuration_digest_sha256": "d" * 64}, "iLO configuration"),
        ({"ilo_firmware_version": "other-ilo-fw"}, "iLO firmware"),
        (
            {"server_firmware_inventory_digest_sha256": "e" * 64},
            "Server firmware inventory",
        ),
        (
            {"controller_firmware_version": "other-controller-fw"},
            "Storage-controller firmware",
        ),
        ({"physical_drive_ids": ("bay-1",)}, "Physical-drive identity set"),
        ({"physical_drive_secure_erase_detected": None}, "no physical-drive secure erase"),
        ({"physical_drive_secure_erase_detected": True}, "no physical-drive secure erase"),
    ],
)
def test_validation_refuses_unproven_or_changed_down_state(
    current_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    baseline = _evidence(target)
    receipt, plan_digest = _validation_binding(target, baseline)
    default_current: dict[str, Any] = {
        "observed_at": NOW + timedelta(minutes=1),
        "logical_drives": (),
        "physical_drive_secure_erase_detected": False,
    }
    default_current.update(current_update)
    current = _evidence(target, **default_current)

    result = teardown.validate_hpe_local_storage_teardown(
        target,
        baseline,
        current,
        apply_receipt=receipt,
        reviewed_plan_digest=plan_digest,
        now=VALIDATION_NOW,
    )

    assert result["status"] == "blocked"
    assert result["desired_down_state"]["proven"] is False
    assert any(expected in blocker for blocker in result["blockers"])


def test_validation_refuses_baseline_target_mismatch() -> None:
    target = _target()
    reviewed_baseline = _evidence(target)
    receipt, plan_digest = _validation_binding(target, reviewed_baseline)
    baseline = _evidence(target, profile_id="other-profile")
    current = _evidence(
        target,
        observed_at=NOW + timedelta(minutes=1),
        logical_drives=(),
        physical_drive_secure_erase_detected=False,
    )

    result = teardown.validate_hpe_local_storage_teardown(
        target,
        baseline,
        current,
        apply_receipt=receipt,
        reviewed_plan_digest=plan_digest,
        now=VALIDATION_NOW,
    )

    assert result["status"] == "blocked"
    assert any("Baseline profile ID" in blocker for blocker in result["blockers"])


@pytest.mark.parametrize(
    ("baseline_update", "expected"),
    [
        ({"authenticated": False}, "authenticated iLO access"),
        ({"read_only_collection": False}, "read-only collection"),
        ({"inventory_complete": False}, "complete local-storage inventory"),
        ({"identity_verified": False}, "verify target identity"),
        ({"physical_drive_ids": ()}, "identify the installed physical drives"),
    ],
)
def test_validation_fully_validates_reviewed_baseline_evidence(
    baseline_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    reviewed_baseline = _evidence(target)
    receipt, plan_digest = _validation_binding(target, reviewed_baseline)
    supplied_baseline = _evidence(target, **baseline_update)
    current = _evidence(
        target,
        observed_at=NOW + timedelta(minutes=1),
        logical_drives=(),
        physical_drive_secure_erase_detected=False,
    )

    result = teardown.validate_hpe_local_storage_teardown(
        target,
        supplied_baseline,
        current,
        apply_receipt=receipt,
        reviewed_plan_digest=plan_digest,
        now=VALIDATION_NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])
    assert any("not bound to the supplied baseline" in blocker for blocker in result["blockers"])


def test_validation_refuses_wrong_plan_receipt_and_nonchronological_current_evidence() -> None:
    target = _target()
    baseline = _evidence(target)
    receipt, _plan_digest = _validation_binding(target, baseline)
    current = _evidence(
        target,
        observed_at=NOW,
        logical_drives=(),
        physical_drive_secure_erase_detected=False,
    )

    result = teardown.validate_hpe_local_storage_teardown(
        target,
        baseline,
        current,
        apply_receipt=receipt,
        reviewed_plan_digest="f" * 64,
        now=VALIDATION_NOW,
    )

    assert result["status"] == "blocked"
    assert any("reviewed teardown plan digest" in blocker for blocker in result["blockers"])
    assert any(
        "newer than the completed apply receipt" in blocker for blocker in result["blockers"]
    )
