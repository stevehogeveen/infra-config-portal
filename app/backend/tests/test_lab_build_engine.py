from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.services import lab_build_engine
from app.schemas import LabBuildPlanRead, LabBuildRunRead
from app.services.lab_build_engine import (
    BuildStepDefinition,
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


def test_build_plan_topologically_orders_declared_capabilities() -> None:
    definitions = (_definitions()[2], _definitions()[0], _definitions()[1])

    plan = get_lab_build_plan(context=_context(), definitions=definitions)

    assert [step["step_id"] for step in plan["steps"]] == ["first", "second", "third"]
    assert plan["status"] == "ready"
    assert LabBuildPlanRead.model_validate(plan).kit_name == "Toronto lab kit"


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
    assert "PROVIDER_MODE" not in run["steps"][0]["operator_message"]
    assert "PROVIDER_MODE" in run["steps"][0]["technical_details"]


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
