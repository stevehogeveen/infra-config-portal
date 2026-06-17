from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import workflow_action_run_store, workflow_action_runner, workflow_registry
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


def test_action_trace_keeps_sanitized_control_center_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout="verification passed", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action(
        "build-verification.run-full",
        payload={
            "control_config": {
                "target": "token=secret-target",
                "ip_mode": "both",
                "snmp_version": "v3",
                "snmp_credentials": "configured",
                "snmp_v3_auth_password": "do-not-store",
                "timeout_seconds": 20,
                "retry_count": 2,
            }
        },
    )

    assert result["control_center_config"] == {
        "target": "token=REDACTED",
        "ip_mode": "both",
        "snmp_version": "v3",
        "snmp_credentials": "configured",
        "timeout_seconds": 20,
        "retry_count": 2,
    }
    assert "do-not-store" not in json.dumps(result)
    assert "secret-target" not in json.dumps(result)


def test_blocked_firmware_upgrade_trace_keeps_control_center_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    result = run_workflow_action(
        "netapp.ontap-upgrade-apply",
        payload={
            "control_config": {
                "target": "192.0.2.203",
                "ip_mode": "ipv4",
                "snmp_version": "v2",
                "snmp_credentials": "configured",
                "timeout_seconds": 8,
                "retry_count": 1,
            }
        },
    )

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert result["control_center_config"]["target"] == "192.0.2.203"


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


def test_ilo_baseline_preview_action_can_run(
    monkeypatch,
    tmp_path: Path,
    db_session: Session,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    result = run_workflow_action("ilo.baseline-preview", db_session)

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert "Preview/readiness only" in result["stdout_summary"]
    assert "WorkflowActionRunNotFoundError" not in result["stderr_summary"]


def test_cisco_firmware_inventory_allows_console_inventory_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-firmware-cisco-inventory")
        assert timeout_seconds == 60
        return subprocess.CompletedProcess(command, 0, stdout="version checked", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("cisco.firmware-inventory")

    assert result["status"] == "completed"
    assert result["executed"] is True


def test_subprocess_timeout_terminates_child_process_group(tmp_path: Path) -> None:
    marker = f"workflow-timeout-child-{uuid.uuid4().hex}"
    script = tmp_path / "spawn_child.py"
    script.write_text(
        "\n".join(
            [
                "import subprocess",
                "import sys",
                "import time",
                f"marker = {marker!r}",
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', marker])",
                "time.sleep(30)",
            ]
        )
    )

    with pytest.raises(subprocess.TimeoutExpired):
        workflow_action_runner._run_subprocess((sys.executable, str(script)), 1)

    deadline = time.time() + 5
    while time.time() < deadline:
        if marker not in _process_args():
            break
        time.sleep(0.1)

    assert marker not in _process_args()


def test_live_status_action_uses_live_lab_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == ("env", "PROVIDER_LAB_LIVE_STAGE_TIMEOUT_SECONDS=20", "make", "provider-lab-live-status")
        assert timeout_seconds == 180
        return subprocess.CompletedProcess(command, 0, stdout="live status checked", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("build-verification.live-status")

    assert result["status"] == "completed"
    assert result["executed"] is True


def test_full_lab_handoff_action_runs_golden_state_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-golden-state")
        assert timeout_seconds == 90
        return subprocess.CompletedProcess(command, 0, stdout="golden state generated", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("full-lab.handoff-report")

    assert result["status"] == "completed"
    assert result["executed"] is True


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


def test_guarded_action_runs_with_exact_confirmation_and_gates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    class AllowPolicy:
        def action_blockers(self, action_id: str, category: object) -> list[str]:
            return []

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: AllowPolicy())

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == (
            "env",
            "HPE_RAID_ALLOW_DESTRUCTIVE=true",
            "HPE_RAID_APPLY_CONFIRM=APPLY HPE RAID PLAN",
            "make",
            "provider-lab-hpe-raid-apply",
        )
        assert timeout_seconds == 900
        return subprocess.CompletedProcess(command, 0, stdout="raid apply complete", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action(
        "raid.apply",
        payload={
            "confirmation_phrase": "APPLY HPE RAID PLAN",
            "confirmed_gates": ["HPE_RAID_ALLOW_DESTRUCTIVE=true"],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert "Guarded workflow action completed" in result["summary"]


def test_vcenter_install_apply_runner_injects_explicit_gates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    class AllowPolicy:
        def action_blockers(self, action_id: str, category: object) -> list[str]:
            return []

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: AllowPolicy())

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == (
            "env",
            "VCENTER_INSTALL_APPLY=true",
            "VCENTER_INSTALL_CONFIRM=DEPLOY VCENTER",
            "VCENTER_INSTALL_ALLOW_DEPLOY=true",
            "make",
            "provider-lab-vcenter-install-apply",
        )
        assert timeout_seconds == 7200
        return subprocess.CompletedProcess(command, 0, stdout="vcenter deploy complete", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action(
        "vcenter.install-apply",
        payload={
            "confirmation_phrase": "DEPLOY VCENTER",
            "confirmed_gates": ["VCENTER_INSTALL_APPLY=true", "VCENTER_INSTALL_ALLOW_DEPLOY=true"],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0


def test_vcenter_attach_esxi_apply_runner_injects_explicit_gates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    class AllowPolicy:
        def action_blockers(self, action_id: str, category: object) -> list[str]:
            return []

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: AllowPolicy())

    def get_unblocked_attach_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_attach_action)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == (
            "env",
            "VCENTER_ATTACH_ESXI_APPLY=true",
            "VCENTER_ATTACH_ESXI_CONFIRM=ATTACH ESXI TO VCENTER",
            "VCENTER_ATTACH_ESXI_ALLOW=true",
            "make",
            "provider-lab-vcenter-attach-esxi-apply",
        )
        assert timeout_seconds == 1200
        return subprocess.CompletedProcess(command, 0, stdout="attach complete", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action(
        "vcenter.attach-esxi-apply",
        payload={
            "confirmation_phrase": "ATTACH ESXI TO VCENTER",
            "confirmed_gates": ["VCENTER_ATTACH_ESXI_APPLY=true", "VCENTER_ATTACH_ESXI_ALLOW=true"],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0


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


def _process_args() -> str:
    return subprocess.run(
        ("ps", "-eo", "args"),
        check=False,
        capture_output=True,
        text=True,
    ).stdout
