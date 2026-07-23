from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.services import lab_build_engine
from app.schemas import LabBuildPlanRead, LabBuildRunRead
from app.services.lab_build_engine import (
    BuildStepDefinition,
    LabBuildPlanError,
    LabBuildRunStateError,
    LabBuildStepRetryError,
    get_lab_build_run,
    get_latest_lab_build_run,
    get_lab_build_plan,
    resume_lab_build,
    retry_lab_build_step,
    start_lab_build,
)


def _context() -> dict[str, Any]:
    return {
        "active_profile": {
            "id": "kit-1",
            "name": "Toronto lab kit",
            "address_plan": {"subnet": "192.168.220.0/24"},
        },
        "enabled_features": {
            "netapp_enabled": False,
            "vcenter_enabled": False,
            "storage_protocol": "none",
        },
    }


def _definitions(*, middle_mode: str = "read_only") -> tuple[BuildStepDefinition, ...]:
    return (
        BuildStepDefinition(
            "first",
            "Prepare network",
            "Prepare the network.",
            "test.first",
            "read_only",
            (),
            ("network",),
            "/network",
            "Check the network and retry.",
        ),
        BuildStepDefinition(
            "second",
            "Prepare storage",
            "Prepare shared storage.",
            "test.second",
            middle_mode,
            ("network",),
            ("storage",),
            "/storage",
            "Complete storage setup, then resume.",
        ),
        BuildStepDefinition(
            "third",
            "Verify handoff",
            "Verify the completed kit.",
            "test.third",
            "read_only",
            ("storage",),
            ("handoff",),
            "/validation",
            "Correct the failed check and retry.",
        ),
    )


def _completed_runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
    return {
        "run_id": action_id,
        "status": "completed",
        "summary": "complete",
        "blockers": [],
        "warnings": [],
    }


@pytest.fixture(autouse=True)
def isolate_build_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAB_BUILD_RUN_DIR", str(tmp_path / "lab-build-runs"))


def _allow_default_build_start(
    monkeypatch: pytest.MonkeyPatch,
    context: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    now = datetime.now(UTC)
    profile = context["active_profile"]
    fingerprint = lab_build_engine.lab_profile_context_fingerprint(context)
    evidence_statuses = {
        "cisco.current-intent-diff": "ready",
        "ilo.reachability": "ok",
        "raid.validate": "succeeded",
    }
    checked_times = {
        "cisco.current-intent-diff": now.replace(microsecond=0),
        "ilo.reachability": now.replace(microsecond=0),
        "raid.validate": now,
    }
    traces = {
        action_id: {
            "run_id": f"workflow-action:{action_id}:test",
            "action_id": action_id,
            "status": "completed",
            "evidence_status": evidence_status,
            "evidence_checked_at": checked_times[action_id].isoformat(),
            "checked_at": checked_times[action_id].isoformat(),
            "finished_at": checked_times[action_id].isoformat(),
            "source_type": "live_probe",
            "freshness": "current",
            "not_mock": True,
            "executed": True,
            "blockers": [],
            "warnings": [],
            "lab_profile_id": str(profile["id"]),
            "lab_profile_fingerprint": fingerprint,
        }
        for action_id, evidence_status in evidence_statuses.items()
    }
    access = {
        "host": "192.168.1.11",
        "username_configured": True,
        "password_configured": True,
        "last_probe_status": "ok",
        "last_probe_time": checked_times["ilo.reachability"].isoformat(),
        "last_probe_target_matches_access_host": True,
    }
    monkeypatch.setattr(
        lab_build_engine,
        "latest_workflow_action_run_trace",
        lambda action_id: traces.get(action_id),
    )
    monkeypatch.setattr(lab_build_engine, "read_ilo_access_settings", lambda: access)
    return traces, access


def test_build_plan_topologically_orders_declared_capabilities() -> None:
    definitions = (_definitions()[2], _definitions()[0], _definitions()[1])

    plan = get_lab_build_plan(context=_context(), definitions=definitions)

    assert [step["step_id"] for step in plan["steps"]] == ["first", "second", "third"]
    assert plan["status"] == "ready"
    assert LabBuildPlanRead.model_validate(plan).kit_name == "Toronto lab kit"


def test_default_plan_starts_with_an_honest_installer_boundary() -> None:
    plan = get_lab_build_plan(context=_context())
    steps = plan["steps"]
    installer_boot = steps[0]
    management_validation = next(step for step in steps if step["step_id"] == "hypervisor")

    assert plan["status"] == "blocked"
    assert len(plan["blockers"]) == 3
    assert installer_boot["order"] == 1
    assert installer_boot["step_id"] == "esxi-installer-boot"
    assert installer_boot["label"] == "Boot the ESXi installer"
    assert installer_boot["action_id"] == "esxi.rebuild-install"
    assert installer_boot["action_mode"] == "destructive"
    assert installer_boot["depends_on"] == []
    assert "does not install or configure ESXi" in installer_boot["description"]
    assert installer_boot["provides"] == ["esxi-installer-boot-requested"]
    assert "hypervisor" not in installer_boot["provides"]
    assert management_validation["action_id"] == "esxi.management-validation"
    assert management_validation["action_mode"] == "read_only"
    assert management_validation["depends_on"] == ["esxi-installer-boot-requested"]
    assert management_validation["provides"] == ["hypervisor"]


def test_default_plan_accepts_current_profile_and_target_bound_setup_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    _allow_default_build_start(monkeypatch, context)

    plan = get_lab_build_plan(context=context)

    assert plan["status"] == "ready"
    assert plan["blockers"] == []
    assert plan["steps"][0]["step_id"] == "esxi-installer-boot"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lab_profile_fingerprint", "wrong-profile"),
        ("evidence_status", "warning"),
        ("evidence_checked_at", "2020-01-01T00:00:00+00:00"),
    ],
)
def test_default_plan_rejects_unbound_nonready_or_stale_network_evidence(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    context = _context()
    traces, _access = _allow_default_build_start(monkeypatch, context)
    traces["cisco.current-intent-diff"][field] = value

    plan = get_lab_build_plan(context=context)

    assert plan["status"] == "blocked"
    assert any("switch's initial setup" in blocker for blocker in plan["blockers"])


def test_default_plan_rejects_ilo_proof_for_a_different_access_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    _traces, access = _allow_default_build_start(monkeypatch, context)
    access["last_probe_target_matches_access_host"] = False

    plan = get_lab_build_plan(context=context)

    assert plan["status"] == "blocked"
    assert any("iLO first contact" in blocker for blocker in plan["blockers"])


def test_first_changing_step_remains_installer_boot_when_shared_storage_is_enabled() -> None:
    context = _context()
    context["enabled_features"] = {
        "netapp_enabled": True,
        "vcenter_enabled": False,
        "storage_protocol": "nfs",
    }

    plan = get_lab_build_plan(context=context)
    changing_steps = [
        step for step in plan["steps"] if step["action_mode"] not in {"read_only", "report_only"}
    ]
    storage_system = next(step for step in plan["steps"] if step["step_id"] == "storage-system")

    assert changing_steps[0]["step_id"] == "esxi-installer-boot"
    assert storage_system["depends_on"] == ["hypervisor"]


def test_build_starts_at_installer_boot_without_rerunning_setup_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    _allow_default_build_start(monkeypatch, context)
    calls: list[str] = []

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        calls.append(action_id)
        return {
            "run_id": f"run:{action_id}",
            "status": "completed",
            "summary": "complete",
            "blockers": [],
            "warnings": [],
        }

    run = start_lab_build(context=context, action_runner=runner)
    installer_boot = next(step for step in run["steps"] if step["step_id"] == "esxi-installer-boot")

    assert calls == []
    assert run["status"] == "waiting"
    assert run["current_step_id"] == "esxi-installer-boot"
    assert installer_boot["order"] == 1
    assert installer_boot["status"] == "waiting"
    assert installer_boot["summary"] == "operator_approval_required"
    assert "existing confirmation and safety gates" in installer_boot["technical_details"]


def test_start_rechecks_setup_evidence_after_plan_was_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    traces, _access = _allow_default_build_start(monkeypatch, context)
    assert get_lab_build_plan(context=context)["status"] == "ready"
    traces["raid.validate"]["evidence_status"] = "failed"

    with pytest.raises(LabBuildPlanError, match="local-storage initial setup"):
        start_lab_build(context=context, action_runner=_completed_runner)


def test_iscsi_datastore_plan_is_explicitly_manual_and_read_only() -> None:
    context = _context()
    context["enabled_features"] = {
        "netapp_enabled": True,
        "vcenter_enabled": False,
        "storage_protocol": "iscsi",
    }

    plan = get_lab_build_plan(context=context)
    datastore = next(step for step in plan["steps"] if step["step_id"] == "datastore")

    assert datastore["label"] == "Confirm the iSCSI datastore is attached"
    assert datastore["description"] == (
        "Check that the iSCSI datastore is attached to the compute host. "
        "Attaching it is a manual step in Virtualization Setup; this app "
        "validates the connection but does not apply it."
    )
    assert datastore["suggested_action"] == (
        "Attach the iSCSI datastore in Virtualization Setup yourself, then retry. "
        "This app validates the connection but does not apply it."
    )
    assert datastore["action_id"] == "esxi.iscsi-datastore-validate"
    assert datastore["action_mode"] == "read_only"
    assert "applied" not in datastore["description"].lower()
    assert "applied" not in datastore["suggested_action"].lower()


def test_nfs_datastore_plan_copy_and_write_action_are_unchanged() -> None:
    context = _context()
    context["enabled_features"] = {
        "netapp_enabled": True,
        "vcenter_enabled": False,
        "storage_protocol": "nfs",
    }

    plan = get_lab_build_plan(context=context)
    datastore = next(step for step in plan["steps"] if step["step_id"] == "datastore")

    assert datastore["label"] == "Connect shared storage to the compute host"
    assert datastore["description"] == "Make the selected shared storage available to the compute host."
    assert datastore["suggested_action"] == "Open Virtualization Setup, finish the storage connection, then retry."
    assert datastore["action_id"] == "esxi.netapp-datastore-apply"
    assert datastore["action_mode"] == "write"


def test_kit_moves_through_full_lifecycle_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []
    first_step_statuses: list[str] = []
    original_save = lab_build_engine._save_run

    def capture_save(run: dict[str, Any]) -> None:
        steps = run.get("steps")
        if isinstance(steps, list) and steps:
            first_step_statuses.append(str(steps[0].get("status")))
        original_save(run)

    monkeypatch.setattr(lab_build_engine, "_save_run", capture_save)

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        seen.append((action_id, "running"))
        return {
            "run_id": f"run:{action_id}",
            "status": "completed",
            "summary": f"{action_id} complete",
            "blockers": [],
            "warnings": [],
            "next_action": "internal detail is not operator copy",
        }

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)

    assert run["status"] == "completed"
    assert [step["status"] for step in run["steps"]] == ["succeeded", "succeeded", "succeeded"]
    assert run["progress"] == {"completed": 3, "total": 3, "percent": 100}
    assert run["report_artifact"].endswith(".md")
    assert [item[0] for item in seen] == ["test.first", "test.second", "test.third"]
    assert LabBuildRunRead.model_validate(run).counts.completed == 3
    assert [status for index, status in enumerate(first_step_statuses) if status not in first_step_statuses[:index]] == [
        "not_started",
        "preflight",
        "ready",
        "running",
        "succeeded",
    ]


def test_failed_step_blocks_named_downstream_step_and_exposes_suggested_action() -> None:
    calls: list[str] = []

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        calls.append(action_id)
        return {
            "run_id": f"run:{action_id}",
            "status": "failed",
            "summary": "raw provider failure",
            "blockers": ["PROVIDER_MODE env missing"],
            "warnings": [],
            "next_action": "inspect raw provider payload",
        }

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)

    assert calls == ["test.first"]
    assert run["steps"][0]["status"] == "blocked"
    assert run["steps"][0]["suggested_action"] == "Check the network and retry."
    assert run["steps"][1]["status"] == "blocked"
    assert run["steps"][1]["operator_message"] == "Blocked by: Prepare network."
    assert json.loads(run["steps"][1]["technical_details"])["blocked_by"] == {
        "step_id": "first",
        "capability": "network",
    }
    assert "PROVIDER_MODE" not in run["steps"][0]["operator_message"]
    assert "PROVIDER_MODE" in run["steps"][0]["technical_details"]
    assert "blocked_by" not in json.loads(run["steps"][0]["technical_details"])


def test_dependency_block_names_earliest_unmet_step_in_plan_order() -> None:
    definitions = (
        BuildStepDefinition(
            "first-prerequisite",
            "First prerequisite",
            "Prepare the first prerequisite.",
            "test.first-prerequisite",
            "read_only",
            (),
            ("first-capability",),
            "/network",
            "Fix the first prerequisite and retry.",
        ),
        BuildStepDefinition(
            "second-prerequisite",
            "Second prerequisite",
            "Prepare the second prerequisite.",
            "test.second-prerequisite",
            "read_only",
            (),
            ("second-capability",),
            "/storage",
            "Fix the second prerequisite and retry.",
        ),
        BuildStepDefinition(
            "dependent",
            "Use both prerequisites",
            "Continue after both prerequisites are ready.",
            "test.dependent",
            "read_only",
            ("second-capability", "first-capability"),
            ("complete",),
            "/validation",
            "Fix the named prerequisite and retry.",
        ),
    )

    run = start_lab_build(
        context=_context(),
        definitions=definitions,
        action_runner=lambda action_id, _session, _payload: {
            "run_id": action_id,
            "status": "failed",
            "summary": "failed",
            "blockers": ["check failed"],
            "warnings": [],
        },
    )

    dependent = next(step for step in run["steps"] if step["step_id"] == "dependent")
    assert dependent["operator_message"] == "Blocked by: First prerequisite."
    assert "first-capability" not in dependent["operator_message"]
    assert json.loads(dependent["technical_details"])["blocked_by"] == {
        "step_id": "first-prerequisite",
        "capability": "first-capability",
    }


def test_retry_resets_downstream_readiness_before_resume() -> None:
    calls: list[str] = []

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        calls.append(action_id)
        return {
            "run_id": f"run:{action_id}:{len(calls)}",
            "status": "completed",
            "summary": "complete",
            "blockers": [],
            "warnings": [],
        }

    completed = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)
    reset = retry_lab_build_step(completed["run_id"], "first", action_runner=runner)

    assert reset["status"] == "waiting"
    assert [step["status"] for step in reset["steps"]] == ["not_started", "not_started", "not_started"]
    assert calls == ["test.first", "test.second", "test.third"]

    resumed = resume_lab_build(
        reset["run_id"],
        run_revision=reset["revision"],
        context=_context(),
        action_runner=runner,
    )
    assert resumed["status"] == "completed"
    assert calls == [
        "test.first",
        "test.second",
        "test.third",
        "test.first",
        "test.second",
        "test.third",
    ]


def test_successful_step_retries_only_when_can_retry_is_true() -> None:
    definitions = list(_definitions())
    definitions[0] = BuildStepDefinition(
        **{
            **definitions[0].__dict__,
            "can_retry": False,
        }
    )

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        return {"run_id": action_id, "status": "completed", "summary": "ok", "blockers": [], "warnings": []}

    run = start_lab_build(context=_context(), definitions=tuple(definitions), action_runner=runner)

    with pytest.raises(LabBuildStepRetryError):
        retry_lab_build_step(run["run_id"], "first", action_runner=runner)


def test_waiting_step_resumes_without_rerunning_completed_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        calls.append(action_id)
        return {
            "run_id": f"run:{action_id}",
            "status": "completed",
            "summary": "complete",
            "blockers": [],
            "warnings": [],
        }

    run = start_lab_build(
        context=_context(),
        definitions=_definitions(middle_mode="write"),
        action_runner=runner,
    )

    assert run["status"] == "waiting"
    assert calls == ["test.first"]
    assert run["steps"][1]["status"] == "waiting"
    assert run["steps"][2]["operator_message"] == "Blocked by: Prepare storage."

    monkeypatch.setattr(
        lab_build_engine,
        "workflow_action_run_trace",
        lambda action_id, action_run_id: {
            "run_id": action_run_id,
            "action_id": action_id,
            "status": "completed",
            "summary": "guarded change completed",
            "blockers": [],
            "warnings": [],
            "lab_profile_id": run["kit_id"],
            "lab_profile_fingerprint": run["profile_fingerprint"],
            "started_at": run["steps"][1]["started_at"],
            "finished_at": run["updated_at"],
        },
    )

    resumed = resume_lab_build(
        run["run_id"],
        action_run_id="external:test.second",
        run_revision=run["revision"],
        waiting_nonce=run["steps"][1]["waiting_nonce"],
        context=_context(),
        action_runner=runner,
    )

    assert resumed["status"] == "completed"
    assert calls == ["test.first", "test.third"]
    assert [step["status"] for step in resumed["steps"]] == ["succeeded", "succeeded", "succeeded"]


def test_failed_build_cannot_resume_without_an_explicit_retry() -> None:
    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        return {
            "run_id": action_id,
            "status": "failed",
            "summary": "failed",
            "blockers": ["check failed"],
            "warnings": [],
        }

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)

    with pytest.raises(LabBuildRunStateError):
        resume_lab_build(
            run["run_id"],
            run_revision=run["revision"],
            context=_context(),
            action_runner=runner,
        )


def test_action_runner_exception_becomes_a_redacted_failed_result() -> None:
    def runner(_action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        raise RuntimeError("secret-bearing internal exception")

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)

    failed = run["steps"][0]
    assert failed["status"] == "blocked"
    assert failed["operator_message"] == "Prepare network could not start."
    assert "secret-bearing" not in failed["technical_details"]
    assert "RuntimeError" in failed["technical_details"]


def test_required_skipped_step_blocks_the_build() -> None:
    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        return {
            "run_id": action_id,
            "status": "skipped",
            "summary": "provider skipped the check",
            "blockers": [],
            "warnings": [],
        }

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)

    assert run["status"] == "failed"
    assert run["steps"][0]["status"] == "blocked"
    assert run["steps"][0]["operator_message"] == "Prepare network did not produce the required result."
    assert run["progress"]["completed"] == 0


def test_optional_skipped_step_can_complete() -> None:
    optional = BuildStepDefinition(
        "optional",
        "Check optional accessory",
        "Check an accessory that is not required by this kit.",
        "test.optional",
        "read_only",
        (),
        (),
        "/server",
        "No action required.",
        optional=True,
    )

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        return {
            "run_id": action_id,
            "status": "skipped",
            "summary": "not installed",
            "blockers": [],
            "warnings": [],
        }

    run = start_lab_build(context=_context(), definitions=(optional,), action_runner=runner)

    assert run["status"] == "completed"
    assert run["steps"][0]["status"] == "skipped"
    assert run["progress"]["completed"] == 1


def test_failed_guarded_evidence_remains_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    run = start_lab_build(
        context=_context(),
        definitions=_definitions(middle_mode="write"),
        action_runner=lambda action_id, _session, _payload: {
            "run_id": action_id,
            "status": "completed",
            "summary": "complete",
            "blockers": [],
            "warnings": [],
        },
    )
    waiting = run["steps"][1]
    monkeypatch.setattr(
        lab_build_engine,
        "workflow_action_run_trace",
        lambda action_id, action_run_id: {
            "run_id": action_run_id,
            "action_id": action_id,
            "status": "failed",
            "summary": "guarded action failed",
            "blockers": [],
            "warnings": [],
            "lab_profile_id": run["kit_id"],
            "lab_profile_fingerprint": run["profile_fingerprint"],
            "finished_at": datetime.now(UTC).isoformat(),
        },
    )

    failed = resume_lab_build(
        run["run_id"],
        action_run_id="guarded:failed",
        run_revision=run["revision"],
        waiting_nonce=waiting["waiting_nonce"],
        context=_context(),
    )

    assert failed["status"] == "failed"
    assert failed["steps"][1]["status"] == "failed"
    assert failed["steps"][1]["summary"] == "guarded action failed"


def test_action_result_secrets_are_redacted_before_persistence() -> None:
    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        return {
            "run_id": action_id,
            "status": "failed",
            "summary": "password=NeverPersistThis",
            "blockers": ["token=NeverPersistThis"],
            "warnings": [],
            "password": "NeverPersistThis",
        }

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)
    stored = get_lab_build_run(run["run_id"])
    serialized = str(stored)

    assert "NeverPersistThis" not in serialized
    assert "REDACTED" in stored["steps"][0]["technical_details"]


def test_guarded_evidence_cannot_be_reused_across_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    definitions = _definitions(middle_mode="write")
    runner = _completed_runner
    first = start_lab_build(context=_context(), definitions=definitions, action_runner=runner)
    second = start_lab_build(context=_context(), definitions=definitions, action_runner=runner)
    trace = {
        "run_id": "guarded:shared",
        "action_id": "test.second",
        "status": "completed",
        "summary": "complete",
        "blockers": [],
        "warnings": [],
        "lab_profile_id": first["kit_id"],
        "lab_profile_fingerprint": first["profile_fingerprint"],
        "finished_at": datetime.now(UTC).isoformat(),
    }
    monkeypatch.setattr(lab_build_engine, "workflow_action_run_trace", lambda _action, _run: trace)

    resume_lab_build(
        first["run_id"],
        action_run_id=trace["run_id"],
        run_revision=first["revision"],
        waiting_nonce=first["steps"][1]["waiting_nonce"],
        context=_context(),
        action_runner=runner,
    )

    with pytest.raises(LabBuildRunStateError, match="already attached"):
        resume_lab_build(
            second["run_id"],
            action_run_id=trace["run_id"],
            run_revision=second["revision"],
            waiting_nonce=second["steps"][1]["waiting_nonce"],
            context=_context(),
            action_runner=runner,
        )


def test_stale_revision_and_profile_change_are_rejected() -> None:
    definitions = _definitions(middle_mode="write")
    runner = _completed_runner
    run = start_lab_build(context=_context(), definitions=definitions, action_runner=runner)

    with pytest.raises(LabBuildRunStateError, match="changed after the page"):
        resume_lab_build(
            run["run_id"],
            run_revision=run["revision"] - 1,
            context=_context(),
        )

    changed_context = _context()
    changed_context["active_profile"]["address_plan"]["subnet"] = "192.168.221.0/24"
    with pytest.raises(LabBuildRunStateError, match="selected kit changed"):
        resume_lab_build(
            run["run_id"],
            run_revision=run["revision"],
            context=changed_context,
        )


def test_profile_fingerprint_ignores_transient_runtime_guidance() -> None:
    first = _context()
    second = _context()
    first["active_profile"]["mismatch_warnings"] = ["old runtime address"]
    second["active_profile"]["mismatch_warnings"] = []
    second["active_profile"]["fix_guidance"] = ["refresh runtime inputs"]

    assert lab_build_engine._profile_fingerprint(first) == lab_build_engine._profile_fingerprint(second)


def test_dependency_blocked_step_cannot_be_retried_directly() -> None:
    run = start_lab_build(
        context=_context(),
        definitions=_definitions(),
        action_runner=lambda action_id, _session, _payload: {
            "run_id": action_id,
            "status": "failed",
            "summary": "failed",
            "blockers": ["check failed"],
            "warnings": [],
        },
    )

    with pytest.raises(LabBuildStepRetryError, match="owning step"):
        retry_lab_build_step(run["run_id"], "second")


def test_stale_running_lease_recovers_as_retryable_failure() -> None:
    runner = _completed_runner
    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)
    stored = lab_build_engine._load_run(run["run_id"])
    stored.update({"status": "running", "current_step_id": "first", "finished_at": None})
    stored["steps"][0].update(
        {
            "status": "running",
            "summary": "running",
            "finished_at": None,
            "lease_expires_at": "2000-01-01T00:00:00+00:00",
        }
    )
    lab_build_engine._save_run(stored)

    recovered = get_lab_build_run(run["run_id"])

    assert recovered["status"] == "failed"
    assert recovered["steps"][0]["summary"] == "execution_interrupted"
    assert recovered["steps"][0]["can_retry"] is True


def test_latest_run_is_scoped_to_the_selected_kit() -> None:
    runner = _completed_runner
    first_context = _context()
    second_context = _context()
    second_context["active_profile"]["id"] = "kit-2"
    second_context["active_profile"]["name"] = "Ottawa lab kit"
    first = start_lab_build(context=first_context, definitions=_definitions(), action_runner=runner)
    second = start_lab_build(context=second_context, definitions=_definitions(), action_runner=runner)

    assert get_latest_lab_build_run("kit-1")["run_id"] == first["run_id"]
    assert get_latest_lab_build_run("kit-2")["run_id"] == second["run_id"]


def test_concurrent_resume_executes_downstream_step_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def runner(action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        calls.append(action_id)
        return {
            "run_id": f"run:{action_id}:{len(calls)}",
            "status": "completed",
            "summary": "complete",
            "blockers": [],
            "warnings": [],
        }

    run = start_lab_build(
        context=_context(),
        definitions=_definitions(middle_mode="write"),
        action_runner=runner,
    )
    trace = {
        "run_id": "guarded:once",
        "action_id": "test.second",
        "status": "completed",
        "summary": "complete",
        "blockers": [],
        "warnings": [],
        "lab_profile_id": run["kit_id"],
        "lab_profile_fingerprint": run["profile_fingerprint"],
        "finished_at": datetime.now(UTC).isoformat(),
    }
    monkeypatch.setattr(lab_build_engine, "workflow_action_run_trace", lambda _action, _run: trace)

    def resume_once() -> dict[str, Any]:
        return resume_lab_build(
            run["run_id"],
            action_run_id=trace["run_id"],
            run_revision=run["revision"],
            waiting_nonce=run["steps"][1]["waiting_nonce"],
            context=_context(),
            action_runner=runner,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(resume_once) for _ in range(2)]
        outcomes = []
        errors = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except LabBuildRunStateError as exc:
                errors.append(str(exc))

    assert len(outcomes) == 1
    assert len(errors) == 1
    assert calls.count("test.third") == 1


def test_legacy_active_run_fails_closed_during_recovery() -> None:
    runner = _completed_runner
    run = start_lab_build(
        context=_context(),
        definitions=_definitions(middle_mode="write"),
        action_runner=runner,
    )
    legacy = lab_build_engine._load_run(run["run_id"])
    legacy.pop("revision")
    legacy.pop("profile_fingerprint")
    legacy["steps"][1].pop("waiting_nonce")
    lab_build_engine.write_json_object(lab_build_engine._run_path(run["run_id"]), legacy)

    recovered = get_lab_build_run(run["run_id"])

    assert recovered["revision"] == 1
    assert recovered["status"] == "failed"
    assert recovered["steps"][1]["summary"] == "resume_contract_upgrade_required"
    assert recovered["steps"][1]["can_retry"] is False
