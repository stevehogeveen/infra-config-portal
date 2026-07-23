from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.providers.action_policy import ActionCategory
from app.services import cisco_switch_teardown as teardown
from app.services.destructive_plan_claims import DestructivePlanClaim

NOW = datetime(2026, 7, 23, 16, 0, tzinfo=UTC)


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
        fail_at: teardown.CiscoSwitchTeardownOperation | None = None,
        raise_at: teardown.CiscoSwitchTeardownOperation | None = None,
        mismatch_at: teardown.CiscoSwitchTeardownOperation | None = None,
        mismatch_digest_at: teardown.CiscoSwitchTeardownOperation | None = None,
        identity_mismatch_at: teardown.CiscoSwitchTeardownOperation | None = None,
        malformed_at: teardown.CiscoSwitchTeardownOperation | None = None,
    ) -> None:
        self.calls: list[teardown.CiscoSwitchTeardownOperation] = []
        self.payloads: list[teardown.CiscoSwitchTeardownOperationPayload] = []
        self.fail_at = fail_at
        self.raise_at = raise_at
        self.mismatch_at = mismatch_at
        self.mismatch_digest_at = mismatch_digest_at
        self.identity_mismatch_at = identity_mismatch_at
        self.malformed_at = malformed_at

    def execute(
        self,
        operation_id: teardown.CiscoSwitchTeardownOperation,
        payload: teardown.CiscoSwitchTeardownOperationPayload,
    ) -> teardown.CiscoSwitchOperationResult | dict[str, Any]:
        self.calls.append(operation_id)
        self.payloads.append(payload)
        if operation_id == self.raise_at:
            raise RuntimeError("sensitive raw console failure")
        if operation_id == self.malformed_at:
            return {"operation_id": operation_id.value}
        if operation_id == self.mismatch_at:
            return teardown.CiscoSwitchOperationResult(
                operation_id=teardown.CiscoSwitchTeardownOperation.IOS_DELETE_VLAN_DATABASE,
                reviewed_plan_digest=payload.reviewed_plan_digest,
                target_binding_digest_sha256=payload.target_binding_digest_sha256,
                live_console_identity_matched=True,
                succeeded=True,
                outcome_code="wrong-operation",
            )
        return teardown.CiscoSwitchOperationResult(
            operation_id=operation_id,
            reviewed_plan_digest=(
                "0" * 64
                if operation_id == self.mismatch_digest_at
                else payload.reviewed_plan_digest
            ),
            target_binding_digest_sha256=payload.target_binding_digest_sha256,
            live_console_identity_matched=operation_id != self.identity_mismatch_at,
            succeeded=operation_id != self.fail_at,
            outcome_code="completed" if operation_id != self.fail_at else "device-refused",
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


def _target(
    *,
    platform: teardown.CiscoSwitchPlatform = teardown.CiscoSwitchPlatform.IOS_XE,
) -> teardown.CiscoSwitchTarget:
    return teardown.CiscoSwitchTarget(
        profile_id="single-server-lab",
        target_id="switch-1",
        console_path="serial://switch-console-a",
        platform=platform,
        chassis_model="C9300-24T-LAB",
        chassis_serial="TESTSERIAL0001",
        hostname="lab-switch-before-reset",
        management_address="192.0.2.204",
    )


def _serial_evidence(
    target: teardown.CiscoSwitchTarget,
    **updates: Any,
) -> teardown.CiscoPrivilegedSerialEvidence:
    values: dict[str, Any] = {
        "observed_at": NOW - timedelta(minutes=1),
        "profile_id": target.profile_id,
        "target_id": target.target_id,
        "console_path": target.console_path,
        "platform": target.platform,
        "chassis_model": target.chassis_model,
        "chassis_serial": target.chassis_serial,
        "hostname": target.hostname,
        "observed_management_address": target.management_address,
        "transport": "serial-console",
        "prompt_state": "privileged-exec",
        "privileged": True,
        "exclusive_access": True,
        "identity_verified": True,
        "firmware_version": "test-ios-xe-version",
        "license_state_digest_sha256": "d" * 64,
    }
    values.update(updates)
    return teardown.CiscoPrivilegedSerialEvidence(**values)


def _backup_evidence(
    target: teardown.CiscoSwitchTarget,
    **updates: Any,
) -> teardown.CiscoSwitchBackupEvidence:
    values: dict[str, Any] = {
        "backup_id": "backup-test-001",
        "captured_at": NOW - timedelta(minutes=2),
        "profile_id": target.profile_id,
        "target_id": target.target_id,
        "platform": target.platform,
        "chassis_model": target.chassis_model,
        "chassis_serial": target.chassis_serial,
        "artifact_digest_sha256": "a" * 64,
        "artifacts": tuple(sorted(teardown.REQUIRED_BACKUP_ARTIFACTS)),
        "verified": True,
        "restore_instructions_present": True,
    }
    values.update(updates)
    return teardown.CiscoSwitchBackupEvidence(**values)


def _apply_request(
    *,
    target: teardown.CiscoSwitchTarget | None = None,
    current_evidence: teardown.CiscoPrivilegedSerialEvidence | None = None,
    backup_evidence: teardown.CiscoSwitchBackupEvidence | None = None,
    **updates: Any,
) -> teardown.CiscoSwitchTeardownApplyRequest:
    selected_target = target or _target()
    selected_current = current_evidence or _serial_evidence(selected_target)
    selected_backup = backup_evidence or _backup_evidence(selected_target)
    preview = teardown.build_cisco_switch_teardown_preview(
        selected_target,
        selected_current,
        selected_backup,
        now=NOW,
    )
    values: dict[str, Any] = {
        "provider_mode": "local-lab-readwrite",
        "policy_action_id": teardown.POLICY_ACTION_ID,
        "target": selected_target,
        "current_evidence": selected_current,
        "backup_evidence": selected_backup,
        "reviewed_plan_digest": preview["plan_digest"],
        "action_confirmation_phrase": teardown.ACTION_CONFIRMATION_PHRASE,
        "target_confirmation_phrase": teardown.cisco_switch_target_confirmation_phrase(
            selected_target
        ),
        "allow_switch_teardown": True,
        "allow_startup_config_erase": True,
        "allow_vlan_database_erase": True,
        "allow_reload": True,
        "acknowledge_expected_ssh_loss": True,
        "executor_enabled": True,
    }
    values.update(updates)
    return teardown.CiscoSwitchTeardownApplyRequest(**values)


@pytest.mark.parametrize(
    ("platform", "expected_operations"),
    [
        (
            teardown.CiscoSwitchPlatform.IOS,
            [
                "cisco-ios.erase-startup-configuration",
                "cisco-ios.delete-vlan-database",
                "cisco-ios.reload-without-save",
            ],
        ),
        (
            teardown.CiscoSwitchPlatform.IOS_XE,
            [
                "cisco-ios-xe.erase-startup-configuration",
                "cisco-ios-xe.delete-vlan-database",
                "cisco-ios-xe.reload-without-save",
            ],
        ),
    ],
)
def test_preview_is_platform_and_exact_chassis_bound(
    platform: teardown.CiscoSwitchPlatform,
    expected_operations: list[str],
) -> None:
    target = _target(platform=platform)
    current = _serial_evidence(target)
    backup = _backup_evidence(target)

    result = teardown.build_cisco_switch_teardown_preview(
        target,
        current,
        backup,
        now=NOW,
    )

    assert result["status"] == "ready_for_guarded_apply"
    assert result["apply_enabled"] is False
    assert result["target_binding"] == {
        "profile_id": "single-server-lab",
        "target_id": "switch-1",
        "console_path": "serial://switch-console-a",
        "management_address": "192.0.2.204",
    }
    assert result["intended_chassis_identity"]["model"] == "C9300-24T-LAB"
    assert result["intended_chassis_identity"]["serial"] == "TESTSERIAL0001"
    assert result["current_console_identity"] == result["intended_chassis_identity"]
    assert [item["operation_id"] for item in result["operations"]] == expected_operations
    assert [item["order"] for item in result["operations"]] == [1, 2, 3]
    assert result["operations"][-1]["expected_disconnect"] is True
    assert result["expected_connectivity_change"]["ssh_expected_to_be_lost"] is True
    assert result["expected_connectivity_change"]["required_recovery_path"] == (
        "physical serial console"
    )
    assert "license entitlement and license state" in result["retained_state"]
    assert "installed IOS or IOS XE firmware image" in result["retained_state"]
    assert result["executor_contract"]["raw_user_commands_accepted"] is False
    assert result["executor_contract"]["accepts_typed_target_bound_payload"] is True
    assert result["executor_contract"]["single_use_claim_store_required"] is True
    assert result["backup_prerequisite"]["required_artifacts"] == sorted(
        teardown.REQUIRED_BACKUP_ARTIFACTS
    )
    assert result["blockers"] == []


def test_preview_blocks_missing_backup_without_hiding_plan() -> None:
    target = _target()
    result = teardown.build_cisco_switch_teardown_preview(
        target,
        _serial_evidence(target),
        None,
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert len(result["operations"]) == 3
    assert "verified, target-bound switch backup" in result["blockers"][0]
    assert result["backup_prerequisite"]["required"] is True


@pytest.mark.parametrize(
    ("evidence_update", "expected"),
    [
        ({"profile_id": "other-profile"}, "profile ID"),
        ({"target_id": "other-switch"}, "target ID"),
        ({"console_path": "serial://wrong"}, "console path"),
        ({"chassis_model": "OTHER-MODEL"}, "chassis model"),
        ({"chassis_serial": "OTHER-SERIAL"}, "chassis serial"),
        ({"hostname": "other-host"}, "hostname"),
        ({"observed_management_address": "192.0.2.99"}, "management address"),
        ({"observed_at": NOW - timedelta(minutes=6)}, "stale"),
        ({"observed_at": NOW + timedelta(minutes=1)}, "future"),
        ({"prompt_state": "user-exec"}, "privileged exec"),
        ({"privileged": False}, "privileged exec"),
        ({"exclusive_access": False}, "exclusive console ownership"),
        ({"identity_verified": False}, "verify chassis identity"),
    ],
)
def test_preview_refuses_untrusted_serial_evidence(
    evidence_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    current = _serial_evidence(target, **evidence_update)

    result = teardown.build_cisco_switch_teardown_preview(
        target,
        current,
        _backup_evidence(target),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])


@pytest.mark.parametrize(
    ("backup_update", "expected"),
    [
        ({"profile_id": "other-profile"}, "Backup profile ID"),
        ({"target_id": "other-switch"}, "Backup target ID"),
        ({"chassis_model": "OTHER-MODEL"}, "Backup chassis model"),
        ({"chassis_serial": "OTHER-SERIAL"}, "Backup chassis serial"),
        ({"captured_at": NOW - timedelta(hours=2)}, "stale"),
        ({"verified": False}, "must be verified"),
        ({"restore_instructions_present": False}, "restore instructions"),
        ({"artifacts": ("running-config",)}, "missing required artifacts"),
        ({"artifact_digest_sha256": "short"}, "full SHA-256"),
    ],
)
def test_preview_refuses_invalid_backup_evidence(
    backup_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    backup = _backup_evidence(target, **backup_update)

    result = teardown.build_cisco_switch_teardown_preview(
        target,
        _serial_evidence(target),
        backup,
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])


def test_plan_digest_changes_when_chassis_bound_backup_changes() -> None:
    target = _target()
    current = _serial_evidence(target)
    first = teardown.build_cisco_switch_teardown_preview(
        target,
        current,
        _backup_evidence(target, backup_id="backup-a"),
        now=NOW,
    )
    second = teardown.build_cisco_switch_teardown_preview(
        target,
        current,
        _backup_evidence(target, backup_id="backup-b"),
        now=NOW,
    )

    assert first["plan_digest"] != second["plan_digest"]


def test_apply_default_refuses_without_executor_even_when_every_gate_passes() -> None:
    result = teardown.apply_cisco_switch_teardown(
        _apply_request(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["apply_attempted"] is False
    assert result["console_writes_attempted"] is False
    assert result["operations_attempted"] == []
    assert any("no default hardware executor" in item for item in result["blockers"])
    assert any("no default claim store" in item for item in result["blockers"])


@pytest.mark.parametrize(
    ("request_update", "expected"),
    [
        ({"provider_mode": "local-readonly"}, "does not match the authoritative runtime"),
        ({"policy_action_id": "lab.factory-reset"}, "policy_action_id"),
        ({"allow_switch_teardown": False}, "allow_switch_teardown"),
        ({"allow_startup_config_erase": False}, "allow_startup_config_erase"),
        ({"allow_vlan_database_erase": False}, "allow_vlan_database_erase"),
        ({"allow_reload": False}, "allow_reload"),
        ({"acknowledge_expected_ssh_loss": False}, "acknowledge_expected_ssh_loss"),
        ({"executor_enabled": False}, "executor_enabled"),
        ({"action_confirmation_phrase": "BLANK IT"}, "action confirmation"),
        ({"target_confirmation_phrase": "WRONG TARGET"}, "chassis-bound target"),
        ({"reviewed_plan_digest": "wrong-digest"}, "reviewed_plan_digest"),
    ],
)
def test_apply_refuses_each_missing_or_inexact_gate(
    request_update: dict[str, Any],
    expected: str,
) -> None:
    executor = FakeExecutor()
    result = teardown.apply_cisco_switch_teardown(
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


def test_apply_requires_factory_reset_policy_action_approval() -> None:
    executor = FakeExecutor()
    result = teardown.apply_cisco_switch_teardown(
        _apply_request(),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=BlockPolicy(),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["operations_attempted"] == []
    assert result["blockers"] == ["Policy refused factory-reset category."]
    assert executor.calls == []


def test_apply_success_dispatches_only_fixed_allowlisted_operation_ids() -> None:
    request = _apply_request()
    policy = AllowPolicy()
    executor = FakeExecutor()

    result = teardown.apply_cisco_switch_teardown(
        request,
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=policy,
        now=NOW,
    )

    expected = list(teardown._PLATFORM_OPERATIONS[request.target.platform])
    assert result["status"] == "completed_pending_validation"
    assert result["blockers"] == []
    assert executor.calls == expected
    assert all(isinstance(item, teardown.CiscoSwitchTeardownOperation) for item in executor.calls)
    assert all(
        payload.reviewed_plan_digest == request.reviewed_plan_digest
        and payload.profile_id == request.target.profile_id
        and payload.target_id == request.target.target_id
        and payload.console_path == request.target.console_path
        and payload.chassis_serial == request.target.chassis_serial
        and payload.require_live_console_identity_exact_match is True
        and payload.abort_on_console_identity_mismatch is True
        for payload in executor.payloads
    )
    assert [item["operation_id"] for item in result["operations_attempted"]] == [
        operation.value for operation in expected
    ]
    assert policy.calls == [
        (teardown.POLICY_ACTION_ID, ActionCategory.FACTORY_RESET),
    ]


def test_apply_stops_before_reload_when_vlan_erase_fails() -> None:
    request = _apply_request()
    operations = teardown._PLATFORM_OPERATIONS[request.target.platform]
    executor = FakeExecutor(fail_at=operations[1])

    result = teardown.apply_cisco_switch_teardown(
        request,
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "failed"
    assert executor.calls == list(operations[:2])
    assert operations[2] not in executor.calls
    assert result["operations_attempted"][-1]["status"] == "failed"


def test_apply_stops_on_executor_operation_id_mismatch() -> None:
    request = _apply_request()
    first = teardown._PLATFORM_OPERATIONS[request.target.platform][0]
    executor = FakeExecutor(mismatch_at=first)

    result = teardown.apply_cisco_switch_teardown(
        request,
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "failed"
    assert executor.calls == [first]
    assert "did not echo" in result["blockers"][0]


def test_apply_executor_exception_fails_closed_without_exposing_raw_message() -> None:
    request = _apply_request()
    first = teardown._PLATFORM_OPERATIONS[request.target.platform][0]
    executor = FakeExecutor(raise_at=first)

    result = teardown.apply_cisco_switch_teardown(
        request,
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "failed"
    assert executor.calls == [first]
    assert "sensitive raw console failure" not in str(result)
    assert result["operations_attempted"][0]["outcome_code"] == ("executor-exception-runtimeerror")


def test_apply_refuses_request_mode_that_disagrees_with_authoritative_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        teardown,
        "_authoritative_provider_mode",
        lambda: "local-readonly",
    )
    executor = FakeExecutor()

    result = teardown.apply_cisco_switch_teardown(
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

    first = teardown.apply_cisco_switch_teardown(
        request,
        executor=first_executor,
        claim_store=claim_store,
        policy=AllowPolicy(),
        now=NOW,
    )
    replay = teardown.apply_cisco_switch_teardown(
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


@pytest.mark.parametrize(
    ("executor", "expected_code"),
    [
        (
            FakeExecutor(
                malformed_at=teardown.CiscoSwitchTeardownOperation.IOS_XE_ERASE_STARTUP_CONFIGURATION
            ),
            "executor-invalid-result",
        ),
        (
            FakeExecutor(
                mismatch_digest_at=teardown.CiscoSwitchTeardownOperation.IOS_XE_ERASE_STARTUP_CONFIGURATION
            ),
            "executor-binding-echo-mismatch",
        ),
        (
            FakeExecutor(
                identity_mismatch_at=teardown.CiscoSwitchTeardownOperation.IOS_XE_ERASE_STARTUP_CONFIGURATION
            ),
            "executor-binding-echo-mismatch",
        ),
    ],
)
def test_apply_fails_closed_on_malformed_or_unbound_executor_result(
    executor: FakeExecutor,
    expected_code: str,
) -> None:
    result = teardown.apply_cisco_switch_teardown(
        _apply_request(),
        executor=executor,
        claim_store=FakeClaimStore(),
        policy=AllowPolicy(),
        now=NOW,
    )

    assert result["status"] == "failed"
    assert len(executor.calls) == 1
    assert result["operations_attempted"][0]["outcome_code"] == expected_code


def test_apply_request_rejects_arbitrary_commands() -> None:
    values = _apply_request().model_dump(mode="python")
    values["commands"] = ["write erase", "reload"]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        teardown.CiscoSwitchTeardownApplyRequest(**values)


def test_evidence_rejects_non_serial_transport_and_unknown_platform() -> None:
    target = _target()
    serial_values = _serial_evidence(target).model_dump(mode="python")
    serial_values["transport"] = "ssh"
    target_values = target.model_dump(mode="python")
    target_values["platform"] = "arbitrary-platform"

    with pytest.raises(ValidationError):
        teardown.CiscoPrivilegedSerialEvidence(**serial_values)
    with pytest.raises(ValidationError):
        teardown.CiscoSwitchTarget(**target_values)


def _blank_evidence(
    target: teardown.CiscoSwitchTarget,
    **updates: Any,
) -> teardown.CiscoSwitchBlankStateEvidence:
    values: dict[str, Any] = {
        "observed_at": NOW,
        "profile_id": target.profile_id,
        "target_id": target.target_id,
        "console_path": target.console_path,
        "platform": target.platform,
        "chassis_model": target.chassis_model,
        "chassis_serial": target.chassis_serial,
        "transport": "serial-console",
        "console_reconnected": True,
        "prompt_state": "setup-wizard",
        "startup_config_present": False,
        "vlan_database_present": False,
        "running_config_state": "factory-default",
        "firmware_version": "test-ios-xe-version",
        "license_state_digest_sha256": "d" * 64,
        "ssh_reachable": False,
    }
    values.update(updates)
    return teardown.CiscoSwitchBlankStateEvidence(**values)


@pytest.mark.parametrize(
    ("prompt_state", "identified_state"),
    [
        ("setup-wizard", "setup-wizard-blank"),
        ("initial-dialog", "setup-wizard-blank"),
        ("privileged-exec", "factory-default-exec-blank"),
    ],
)
def test_validate_accepts_proven_blank_state_after_console_reconnect(
    prompt_state: str,
    identified_state: str,
) -> None:
    target = _target()
    result = teardown.validate_cisco_switch_teardown(
        target,
        _serial_evidence(target),
        _blank_evidence(target, prompt_state=prompt_state),
        now=NOW,
    )

    assert result["status"] == "ready"
    assert result["identified_state"] == identified_state
    assert result["validation_read_only"] is True
    assert result["console_writes_attempted"] is False
    assert result["expected_connectivity"]["ssh_required_for_validation"] is False
    assert result["retained_state_observed"]["firmware_or_license_changed_by_plan"] is False
    assert result["retained_state_observed"]["firmware_unchanged"] is True
    assert result["retained_state_observed"]["license_state_unchanged"] is True
    assert result["blockers"] == []


@pytest.mark.parametrize(
    ("evidence_update", "expected"),
    [
        ({"profile_id": "other-profile"}, "profile ID"),
        ({"target_id": "other-switch"}, "target ID"),
        ({"console_path": "serial://wrong"}, "console path"),
        ({"chassis_model": "OTHER-MODEL"}, "chassis model"),
        ({"chassis_serial": "OTHER-SERIAL"}, "chassis serial"),
        ({"observed_at": NOW - timedelta(minutes=11)}, "stale"),
        ({"console_reconnected": False}, "must reconnect"),
        ({"startup_config_present": True}, "startup configuration is absent"),
        ({"startup_config_present": None}, "startup configuration is absent"),
        ({"vlan_database_present": True}, "VLAN database is absent"),
        ({"vlan_database_present": None}, "VLAN database is absent"),
        ({"running_config_state": "nondefault"}, "factory-default running state"),
        ({"prompt_state": "user-exec"}, "Console prompt must show"),
        ({"firmware_version": "changed-version"}, "firmware changed"),
        ({"license_state_digest_sha256": "e" * 64}, "License state changed"),
    ],
)
def test_validate_refuses_unproven_blank_state(
    evidence_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()
    result = teardown.validate_cisco_switch_teardown(
        target,
        _serial_evidence(target),
        _blank_evidence(target, **evidence_update),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert result["identified_state"] == "not-proven-blank"
    assert result["console_writes_attempted"] is False
    assert any(expected in blocker for blocker in result["blockers"])


@pytest.mark.parametrize(
    ("baseline_update", "expected"),
    [
        ({"identity_verified": False}, "verify chassis identity"),
        ({"exclusive_access": False}, "exclusive console ownership"),
        ({"observed_at": NOW}, "newer than the reviewed pre-teardown baseline"),
    ],
)
def test_validate_refuses_untrusted_or_nonchronological_baseline(
    baseline_update: dict[str, Any],
    expected: str,
) -> None:
    target = _target()

    result = teardown.validate_cisco_switch_teardown(
        target,
        _serial_evidence(target, **baseline_update),
        _blank_evidence(target),
        now=NOW,
    )

    assert result["status"] == "blocked"
    assert any(expected in blocker for blocker in result["blockers"])
