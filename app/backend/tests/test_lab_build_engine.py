from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services import lab_build_engine
from app.schemas import LabBuildPlanRead, LabBuildRunRead
from app.services.lab_build_engine import (
    BuildStepDefinition,
    LabBuildRunStateError,
    LabBuildStepRetryError,
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

    resumed = resume_lab_build(reset["run_id"], action_runner=runner)
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
        "latest_workflow_action_run_trace",
        lambda action_id: {
            "run_id": f"external:{action_id}",
            "status": "completed",
            "summary": "guarded change completed",
            "blockers": [],
            "warnings": [],
            "started_at": run["steps"][1]["started_at"],
            "finished_at": run["updated_at"],
        },
    )

    resumed = resume_lab_build(run["run_id"], action_runner=runner)

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
        resume_lab_build(run["run_id"], action_runner=runner)


def test_action_runner_exception_becomes_a_redacted_failed_result() -> None:
    def runner(_action_id: str, _session: Any, _payload: Any) -> dict[str, Any]:
        raise RuntimeError("secret-bearing internal exception")

    run = start_lab_build(context=_context(), definitions=_definitions(), action_runner=runner)

    failed = run["steps"][0]
    assert failed["status"] == "blocked"
    assert failed["operator_message"] == "Prepare network could not start."
    assert "secret-bearing" not in failed["technical_details"]
    assert "RuntimeError" in failed["technical_details"]
