from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import workflow_action_run_store, workflow_action_runner
from app.services.workflow_action_runner import run_workflow_action


def test_read_only_action_can_run_and_save_trace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-build-verification")
        assert timeout_seconds == 300
        return subprocess.CompletedProcess(command, 0, stdout="verification passed", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("build-verification.run-full")

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["source_type"] == "live_probe"
    assert result["freshness"] == "current"
    assert result["not_mock"] is True
    assert result["trace_artifact"]
    assert list(tmp_path.glob("*.json"))


def test_report_only_action_can_run(
    monkeypatch,
    tmp_path: Path,
    db_session: Session,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    result = run_workflow_action("reports.summary", db_session)

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["source_type"] == "live_probe"
    assert result["freshness"] == "current"


def test_destructive_action_is_refused(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    result = run_workflow_action("raid.apply")

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert result["return_code"] is None
    assert any("guarded workflow" in blocker for blocker in result["blockers"])


def test_write_action_is_refused(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    result = run_workflow_action("ilo.virtual-media-insert")

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert any("guarded workflow" in blocker for blocker in result["blockers"])


def test_unknown_action_returns_clear_404(client: TestClient) -> None:
    response = client.post("/api/v1/workflows/actions/not-a-real-action/run")

    assert response.status_code == 404
    assert response.json()["detail"]["blocker"] == "Workflow action not found"


def test_secrets_are_redacted_from_stdout_stderr(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setenv("WORKFLOW_ACTION_TEST_PASSWORD", "super-secret-value")

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="password=super-secret-value",
            stderr="token=super-secret-value",
        )

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("build-verification.toolchain-check")

    assert result["status"] == "failed"
    assert "super-secret-value" not in result["stdout_summary"]
    assert "super-secret-value" not in result["stderr_summary"]
    assert "REDACTED" in result["stdout_summary"]
    assert "REDACTED" in result["stderr_summary"]


def test_run_trace_is_listed_from_api(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="toolchain ok", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    post = client.post("/api/v1/workflows/actions/build-verification.toolchain-check/run")
    get = client.get("/api/v1/workflows/actions/build-verification.toolchain-check/runs")

    assert post.status_code == 200
    assert get.status_code == 200
    runs = get.json()
    assert len(runs) == 1
    assert runs[0]["action_id"] == "build-verification.toolchain-check"
    assert runs[0]["trace_artifact"]
