from __future__ import annotations

import json
import os
import sys
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.providers.base import ProviderAction, ProviderStatus
from app.services.lab_profiles import create_lab_profile
from app.services import (
    operator_issue_packets,
    workflow_action_allowlist,
    workflow_action_diagnosis,
    workflow_action_run_store,
    workflow_action_runner,
    workflow_registry,
)
from app.services.workflow_action_runner import run_workflow_action


def test_read_only_action_can_run_and_save_trace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-toolchain-check")
        assert timeout_seconds == 180
        return subprocess.CompletedProcess(command, 0, stdout="toolchain passed", stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("build-verification.toolchain-check")

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["source_type"] == "live_probe"
    assert result["freshness"] == "current"
    assert result["not_mock"] is True
    assert result["lab_profile_id"]
    assert len(result["lab_profile_fingerprint"]) == 64
    assert result["trace_artifact"]
    assert list(tmp_path.glob("*.json"))
    assert workflow_action_run_store.workflow_action_run_trace(
        result["action_id"], result["run_id"]
    )["run_id"] == result["run_id"]


def test_cisco_discover_console_only_refreshes_passive_candidates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    calls: list[str] = []

    def passive_candidates() -> dict[str, object]:
        calls.append("listed")
        return {
            "provider_id": "cisco-console",
            "status": "ready",
            "message": "Choose one exact cable in Cisco setup.",
            "checked_at": "2026-07-23T18:00:00+00:00",
            "candidates": [{"port": "COM5", "candidate_fingerprint": "a" * 64}],
            "warnings": [],
            "blockers": [],
        }

    monkeypatch.setattr(
        workflow_action_runner,
        "list_cisco_console_identity_candidates",
        passive_candidates,
    )
    monkeypatch.setattr(
        workflow_action_runner,
        "_run_subprocess",
        lambda *_args, **_kwargs: pytest.fail("passive candidate refresh must not run a command"),
    )

    result = run_workflow_action("cisco.discover-console")

    assert calls == ["listed"]
    assert result["status"] == "completed"
    assert result["executed"] is True
    assert "COM5" in result["stdout_summary"]


def test_api_action_serializes_dataclass_provider_status(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "CODEX_RUN_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "ESXI_MANAGEMENT_VALIDATION_REPORT", tmp_path / "esxi-management-readiness-report.md")
    monkeypatch.setattr(workflow_action_runner, "ESXI_MANAGEMENT_VALIDATION_JSON", tmp_path / "esxi-management-readiness-redacted.json")

    class FakeEsxiReadonlyAdapter:
        def probe(self) -> ProviderStatus:
            return ProviderStatus(
                id="esxi-readonly",
                name="ESXi Read-Only",
                kind="virtualization",
                mode="local-lab-readwrite",
                status="ready",
                source_type="live_probe",
                freshness="current",
                is_current=True,
                capabilities=["https-api-reachability"],
                message="Read-only ESXi management probe completed.",
                safe_actions=[
                    ProviderAction(
                        id="probe-esxi-readonly",
                        label="Read-Only Probe",
                        enabled=True,
                        read_only=True,
                        reason="Safe read-only probe.",
                    )
                ],
            )

    monkeypatch.setattr(workflow_action_runner, "EsxiReadonlyAdapter", FakeEsxiReadonlyAdapter)

    result = run_workflow_action("esxi.management-validation")

    assert result["status"] == "completed"
    assert result["stderr_summary"] == ""
    assert result["not_mock"] is True
    assert "esxi-readonly" in result["stdout_summary"]
    assert "live_probe" in result["stdout_summary"]
    assert "current" in result["stdout_summary"]
    assert (tmp_path / "esxi-management-readiness-report.md").exists()
    assert (tmp_path / "esxi-management-readiness-redacted.json").exists()
    assert list(tmp_path.glob("*.json"))


def test_api_action_trace_preserves_underlying_readiness_status(monkeypatch) -> None:
    action = {
        "action_id": "cisco.current-intent-diff",
        "label": "Test Readiness",
        "stage": "test",
        "stage_label": "Test",
        "mode": "read_only",
        "api_method": "GET",
        "api_endpoint": "/test/readiness",
        "reports": [],
    }
    monkeypatch.setattr(
        workflow_action_runner,
        "_api_action_payload",
        lambda *_args, **_kwargs: {
            "status": "warning",
            "checked_at": "2026-07-23T12:00:00+00:00",
            "blockers": [],
            "warnings": ["Current state does not match intent."],
        },
    )

    result = workflow_action_runner._run_api_action(
        action,
        "workflow-action:cisco.current-intent-diff:test",
        "2026-07-23T12:00:00+00:00",
        None,
        {},
    )

    assert result["status"] == "completed"
    assert result["evidence_status"] == "warning"
    assert result["evidence_checked_at"] == "2026-07-23T12:00:00+00:00"


def test_ilo_reachability_action_writes_live_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "CODEX_RUN_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "ILO_REACHABILITY_REPORT", tmp_path / "ilo-real-run-report.md")
    monkeypatch.setattr(workflow_action_runner, "ILO_REACHABILITY_JSON", tmp_path / "ilo-real-run-redacted.json")
    configs: list[object] = []

    class FakeIloRedfishAdapter:
        def __init__(self, config=None) -> None:  # noqa: ANN001
            configs.append(config)

        def probe(self) -> dict[str, object]:
            return {
                "provider_id": "ilo-redfish",
                "status": "ok",
                "checked_at": "2026-07-01T01:10:00+00:00",
                "endpoint_detection": {
                    "classification": "redfish_available",
                    "redfish_status": "available",
                    "legacy_status": "available",
                },
                "legacy_identity": {"model": "ProLiant DL360 Gen10", "ilo_generation": "ilo5"},
                "blockers": [],
                "warnings": [],
            }

    monkeypatch.setattr(workflow_action_runner, "IloRedfishAdapter", FakeIloRedfishAdapter)

    result = run_workflow_action("ilo.reachability", payload={"ilo_host": "10.10.8.110"})

    assert result["status"] == "completed"
    assert result["evidence_status"] == "ok"
    assert result["evidence_checked_at"] == "2026-07-01T01:10:00+00:00"
    assert configs[-1].host == "10.10.8.110"
    assert configs[-1].host_source == "operator_first_contact"
    assert configs[-1].fallback_hosts == ()
    assert configs[-1].fallback_host_sources == ()
    assert (tmp_path / "ilo-real-run-report.md").exists()
    assert (tmp_path / "ilo-real-run-redacted.json").exists()
    assert any(str(path).endswith("ilo-real-run-redacted.json") for path in result["report_artifacts"])
    trace = workflow_action_run_store.workflow_action_run_trace(
        "ilo.reachability",
        result["run_id"],
    )
    assert trace is not None
    assert trace["evidence_status"] == "ok"


def test_ilo_reachability_route_preserves_exact_first_contact_target(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "CODEX_RUN_DIR", tmp_path)
    monkeypatch.setattr(
        workflow_action_runner,
        "ILO_REACHABILITY_REPORT",
        tmp_path / "ilo-real-run-report.md",
    )
    monkeypatch.setattr(
        workflow_action_runner,
        "ILO_REACHABILITY_JSON",
        tmp_path / "ilo-real-run-redacted.json",
    )
    configs: list[object] = []

    class FakeIloRedfishAdapter:
        def __init__(self, config=None) -> None:  # noqa: ANN001
            configs.append(config)

        def probe(self) -> dict[str, object]:
            return {
                "provider_id": "ilo-redfish",
                "status": "ok",
                "checked_at": "2026-07-23T12:00:00+00:00",
                "endpoint_detection": {"classification": "redfish_available"},
                "blockers": [],
                "warnings": [],
            }

    monkeypatch.setattr(workflow_action_runner, "IloRedfishAdapter", FakeIloRedfishAdapter)

    response = client.post(
        "/api/v1/workflows/actions/ilo.reachability/run",
        json={"ilo_host": "10.10.8.110"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["evidence_status"] == "ok"
    assert response.json()["evidence_checked_at"] == "2026-07-23T12:00:00+00:00"
    assert configs
    assert configs[-1].host == "10.10.8.110"
    assert configs[-1].host_source == "operator_first_contact"
    assert configs[-1].fallback_hosts == ()
    assert configs[-1].fallback_host_sources == ()


def test_raid_discovery_refuses_missing_exact_ilo_target_before_probe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    class FailIloRedfishAdapter:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("Missing exact iLO target must block before any probe.")

    monkeypatch.setattr(workflow_action_runner, "IloRedfishAdapter", FailIloRedfishAdapter)

    result = run_workflow_action("raid.discovery")

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert any("explicit current-access ilo_host" in item for item in result["blockers"])


def test_raid_discovery_uses_only_exact_first_contact_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "CODEX_RUN_DIR", tmp_path)
    monkeypatch.setattr(
        workflow_action_runner,
        "HPE_RAID_DISCOVERY_REPORT",
        tmp_path / "hpe-raid-discovery-report.md",
    )
    configs: list[object] = []
    discovery_inputs: list[tuple[object, object]] = []
    exact_probe = {
        "provider_id": "ilo-redfish",
        "status": "ok",
        "checked_at": "2026-07-23T15:00:00+00:00",
        "target_source": "operator_first_contact",
        "target_fingerprint": "exact-first-contact-fingerprint",
        "storage": {
            "controllers": [{"Id": "0", "Model": "HPE Smart Array"}],
            "physical_drives": [{"Id": "1I:1:1"}],
            "logical_drives": [],
        },
        "blockers": [],
        "warnings": [],
        "not_attempted": ["storage controller write"],
    }

    class FakeIloRedfishAdapter:
        def __init__(self, config=None) -> None:  # noqa: ANN001
            configs.append(config)

        def probe(self) -> dict[str, object]:
            return exact_probe

    def fake_storage_discovery(*, probe=None, probe_time=None):  # noqa: ANN001
        discovery_inputs.append((probe, probe_time))
        return SimpleNamespace(
            storage_inventory_available=True,
            blockers=[],
            warnings=[],
            next_safe_action="Review exact-target inventory.",
            model_dump=lambda: {
                "provider_id": "ilo-redfish",
                "source": "exact iLO Redfish probe",
                "last_probe_time": probe_time,
                "storage_inventory_available": True,
                "controllers": [{"Id": "0"}],
                "physical_drives": [{"Id": "1I:1:1"}],
                "logical_drives": [],
                "blockers": [],
                "warnings": [],
                "next_safe_action": "Review exact-target inventory.",
            },
        )

    monkeypatch.setattr(workflow_action_runner, "IloRedfishAdapter", FakeIloRedfishAdapter)
    monkeypatch.setattr(
        workflow_action_runner,
        "get_hpe_storage_discovery",
        fake_storage_discovery,
    )

    result = run_workflow_action(
        "raid.discovery",
        payload={"ilo_host": "192.168.1.11"},
    )

    assert result["status"] == "completed"
    assert configs
    assert configs[-1].host == "192.168.1.11"
    assert configs[-1].host_source == "operator_first_contact"
    assert configs[-1].fallback_hosts == ()
    assert configs[-1].fallback_host_sources == ()
    assert discovery_inputs == [(exact_probe, "2026-07-23T15:00:00+00:00")]
    assert (tmp_path / "hpe-raid-discovery-report.md").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"ilo_host": "https://10.10.8.110"},
        {"ilo_host": "not-an-ip"},
        {"host": "10.10.8.110"},
        {"unknown_target": "10.10.8.110"},
    ],
)
def test_workflow_action_route_rejects_invalid_or_unknown_target_payloads(
    client: TestClient,
    monkeypatch,
    payload: dict[str, str],
) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Invalid target payload must fail before the runner.")

    monkeypatch.setattr("app.api.routes.run_workflow_action", fail_if_called)

    response = client.post(
        "/api/v1/workflows/actions/ilo.reachability/run",
        json=payload,
    )

    assert response.status_code == 422


def test_cisco_readonly_route_preserves_allowlisted_interface_commands(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    captured: list[list[str] | None] = []

    class FakeCiscoAnsibleAdapter:
        def probe(self, extra_show_commands=None) -> dict[str, object]:  # noqa: ANN001
            captured.append(extra_show_commands)
            return {
                "provider_id": "cisco-ansible",
                "status": "ok",
                "message": "Read-only Cisco SSH probe completed.",
                "command_results": {},
                "blockers": [],
                "warnings": [],
                "not_attempted": ["configure terminal", "write memory", "reload"],
            }

    monkeypatch.setattr(
        "app.providers.cisco_ansible.CiscoAnsibleAdapter",
        FakeCiscoAnsibleAdapter,
    )
    commands = [
        "show interface Gi1/0/1",
        "show running-config interface Gi1/0/1",
    ]

    response = client.post(
        "/api/v1/workflows/actions/cisco.ssh-readonly-probe/run",
        json={"cisco_commands": commands},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert captured == [commands]


@pytest.mark.parametrize(
    "command",
    [
        "configure terminal",
        "show running-config",
        "show interface Gi1/0/49",
        "show interface Gi1/0/1 | redirect flash:proof.txt",
    ],
)
def test_cisco_readonly_route_rejects_arbitrary_commands(
    client: TestClient,
    monkeypatch,
    command: str,
) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Unapproved Cisco commands must fail before the runner.")

    monkeypatch.setattr("app.api.routes.run_workflow_action", fail_if_called)

    response = client.post(
        "/api/v1/workflows/actions/cisco.ssh-readonly-probe/run",
        json={"cisco_commands": [command]},
    )

    assert response.status_code == 422


def test_cisco_ssh_readonly_probe_action_captures_show_command_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    class FakeCiscoAnsibleAdapter:
        def probe(self) -> dict[str, object]:
            return {
                "provider_id": "cisco-ansible",
                "status": "ok",
                "message": "Read-only Cisco SSH probe completed through Paramiko fallback.",
                "fallback": "paramiko",
                "command_results": {
                    "show version": {"captured": True, "version_hint": "17.15.05"},
                    "show interfaces status": {"captured": True, "line_count": 8},
                    "show vlan brief": {"captured": True, "line_count": 6},
                },
                "blockers": [],
                "warnings": [],
                "not_attempted": ["configure terminal", "write memory", "reload"],
            }

    monkeypatch.setattr("app.providers.cisco_ansible.CiscoAnsibleAdapter", FakeCiscoAnsibleAdapter)

    result = run_workflow_action("cisco.ssh-readonly-probe")

    assert result["status"] == "completed"
    assert result["not_mock"] is True
    assert result["stderr_summary"] == ""
    assert "show interfaces status" in result["stdout_summary"]
    assert "show vlan brief" in result["stdout_summary"]
    assert "17.15.05" in result["stdout_summary"]
    assert "write memory" in result["stdout_summary"]


def test_full_lab_validation_action_writes_report_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    calls: list[bool] = []

    def fake_lab_validation_summary(*, write_report: bool = False) -> dict[str, object]:
        calls.append(write_report)
        return {
            "overall_status": "ready",
            "source_type": "live_cached",
            "freshness": "current",
            "handoff_report": "artifacts/codex-runs/lab-validation-handoff-report.md",
            "blockers": [],
            "warnings": [],
        }

    monkeypatch.setattr(workflow_action_runner, "get_lab_validation_summary", fake_lab_validation_summary)

    result = run_workflow_action("full-lab.validation")

    assert result["status"] == "completed"
    assert result["not_mock"] is True
    assert calls == [True]
    assert "lab-validation-handoff-report.md" in result["stdout_summary"]


def test_netapp_api_action_stdout_is_compact_and_parseable() -> None:
    payload = {
        "provider_id": "netapp-ontap",
        "action": "read-live-state",
        "status": "ready",
        "source_type": "live_cached",
        "freshness": "current",
        "is_current": True,
        "checked_at": "2026-06-30T22:00:00+00:00",
        "management": {
            "cluster_mgmt_ip": "192.168.1.220",
            "rest_443_reachable": True,
            "ssh_22_reachable": True,
        },
        "api": {
            "access_values_present": True,
            "authenticated": True,
            "status": "ready",
            "reason": "Safe ONTAP API GET authenticated.",
        },
        "storage": {
            "protocol": "nfs",
            "ready": True,
            "nfs_lifs_detected": ["192.168.1.230"],
            "iscsi_lifs_detected": ["192.168.1.240"],
        },
        "protocol_options": {
            "iscsi": {
                "ready": True,
                "service_enabled": True,
                "reachable_lif_count": 4,
                "lifs": ["192.168.1.240", "192.168.1.241"],
            }
        },
        "very_large_unused_payload": "x" * 10_000,
    }

    compact = workflow_action_runner._api_stdout_payload("netapp.live-state", payload)

    assert compact["source_type"] == "live_cached"
    assert compact["freshness"] == "current"
    assert compact["api"]["authenticated"] is True
    assert compact["protocol_options"]["iscsi"]["reachable_lif_count"] == 4
    assert "very_large_unused_payload" not in compact


def test_netapp_live_state_action_runs_fresh_probe(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_live_state() -> dict[str, object]:
        return {
            "provider_id": "netapp-ontap",
            "action": "read-live-state",
            "status": "ready",
            "source_type": "live_probe",
            "freshness": "current",
            "is_current": True,
            "management": {"rest_443_reachable": True, "ssh_22_reachable": True},
            "api": {"access_values_present": True, "authenticated": True, "status": "ready"},
            "storage": {"protocol": "nfs", "ready": True},
            "blockers": [],
            "warnings": [],
        }

    monkeypatch.setattr(workflow_action_runner, "run_netapp_live_state", fake_live_state)

    result = run_workflow_action("netapp.live-state")

    assert result["status"] == "completed"
    assert result["not_mock"] is True
    assert "read-live-state" in result["stdout_summary"]
    assert "live_probe" in result["stdout_summary"]


def test_command_start_failure_reports_executable_without_args(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fail_start(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("missing executable")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fail_start)

    result = run_workflow_action("build-verification.toolchain-check")

    assert result["status"] == "failed"
    assert result["return_code"] is None
    assert result["blockers"] == ["Command `make` could not start: FileNotFoundError."]
    assert "provider-lab-toolchain-check" not in result["blockers"][0]
    assert list(tmp_path.glob("*.json"))


def test_workflow_trace_artifact_uses_posix_repo_relative_path(monkeypatch, tmp_path: Path) -> None:
    trace_dir = tmp_path / "artifacts" / "codex-runs" / "workflow-action-runs"
    monkeypatch.setattr(workflow_action_run_store, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", trace_dir)

    payload = workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "run-1",
            "action_id": "example.action",
            "stage_id": "verify",
            "status": "completed",
        }
    )

    assert payload["trace_artifact"].startswith("artifacts/codex-runs/workflow-action-runs/")
    assert "\\" not in payload["trace_artifact"]


def test_workflow_trace_store_ignores_corrupt_and_non_object_traces(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    action_id = "example.action"
    (tmp_path / "20260101T000000Z__example.action__bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "20260101T000001Z__example.action__list.json").write_text("[]", encoding="utf-8")

    saved = workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "run-1",
            "action_id": action_id,
            "stage_id": "verify",
            "status": "completed",
            "started_at": "2026-01-01T00:00:02Z",
        }
    )

    assert workflow_action_run_store.list_workflow_action_run_traces(action_id) == [saved]


def test_workflow_trace_store_self_heals_trace_listing_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    original_glob = Path.glob

    def flaky_glob(self: Path, pattern: str):  # noqa: ANN202
        if self == tmp_path:
            raise OSError("trace directory cannot be listed")
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", flaky_glob)

    assert workflow_action_run_store.list_workflow_action_run_traces("example.action") == []


def test_workflow_trace_store_writes_complete_json_without_temp_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    saved = workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "run-1",
            "action_id": "example.action",
            "stage_id": "verify",
            "status": "completed",
        }
    )
    trace_paths = list(tmp_path.glob("*.json"))

    assert len(trace_paths) == 1
    assert json.loads(trace_paths[0].read_text(encoding="utf-8")) == saved
    assert not list(tmp_path.glob("*.tmp"))


def test_workflow_trace_filenames_stay_within_windows_component_limit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    action_id = "action-" + ("x" * 300)
    run_id = "run-" + ("y" * 300)

    saved = workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": run_id,
            "action_id": action_id,
            "stage_id": "verify",
            "status": "completed",
        }
    )
    trace_paths = list(tmp_path.glob("*.json"))

    assert len(trace_paths) == 1
    assert len(trace_paths[0].name) <= workflow_action_run_store.MAX_TRACE_FILENAME_CHARS
    assert workflow_action_run_store.list_workflow_action_run_traces(action_id) == [saved]


def test_workflow_trace_slug_handles_weird_characters(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    action_id = "netapp:setup/apply?confirm*name with spaces"
    run_id = "run id with [brackets]; $(whoami) and unicode snow"

    saved = workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": run_id,
            "action_id": action_id,
            "stage_id": "verify",
            "status": "completed",
        }
    )
    trace_path = next(tmp_path.glob("*.json"))

    assert not any(character in trace_path.name for character in '<>:"\\|?*[];$ ')
    assert workflow_action_run_store.list_workflow_action_run_traces(action_id) == [saved]


def test_workflow_trace_registry_projection_self_heals_malformed_lists() -> None:
    projected = workflow_action_run_store.run_trace_to_registry_trace(
        {
            "run_id": "run-1",
            "action_id": "action-1",
            "stage_id": "verify",
            "status": "completed",
            "report_artifacts": [" artifacts/report.md ", "artifacts/report.md", 404, "404"],
            "blockers": [" retry ", "retry", "", None, 404, "404"],
            "warnings": {"unexpected": "shape"},
        }
    )

    assert projected["report_artifacts"] == ["artifacts/report.md", "404"]
    assert projected["blockers"] == ["retry", "404"]
    assert projected["warnings"] == []


def test_existing_report_artifacts_skips_paths_that_error(monkeypatch, tmp_path: Path) -> None:
    ready = tmp_path / "artifacts" / "ready.md"
    unavailable = tmp_path / "artifacts" / "unavailable.md"
    ready.parent.mkdir(parents=True)
    ready.write_text("ready\n", encoding="utf-8")
    unavailable.write_text("unavailable\n", encoding="utf-8")
    monkeypatch.setattr(workflow_action_runner, "REPO_ROOT", tmp_path)
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == unavailable:
            raise OSError("report path is unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert workflow_action_runner._existing_report_artifacts(
        ["artifacts/ready.md", "artifacts/unavailable.md", "artifacts/ready.md"]
    ) == ["artifacts/ready.md"]


def test_workflow_action_runner_keeps_scalar_report_artifacts_whole(monkeypatch, tmp_path: Path) -> None:
    report = tmp_path / "artifacts" / "codex-runs" / "scalar-report.md"
    report.parent.mkdir(parents=True)
    report.write_text("ready\n", encoding="utf-8")
    monkeypatch.setattr(workflow_action_runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path / "traces")

    action = {
        "action_id": "example.scalar-artifact",
        "label": "Scalar Artifact",
        "stage": "reports",
        "stage_label": "Reports",
        "mode": "report_only",
        "reports": "artifacts/codex-runs/scalar-report.md",
    }

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", lambda _action_id: action)
    monkeypatch.setattr(workflow_action_runner, "workflow_action_run_blockers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        workflow_action_runner,
        "get_workflow_action_execution_spec",
        lambda _action_id: SimpleNamespace(
            kind="command",
            command=("echo", "ok"),
            timeout_seconds=1,
            reports="artifacts/codex-runs/scalar-report.md",
        ),
    )
    def fake_command_result(action_arg: dict, run_id: str, started_at: str, *_args) -> dict:
        result = workflow_action_runner._base_result(
            action_arg,
            run_id,
            started_at,
            status="completed",
            command="echo ok",
            executed=True,
            return_code=0,
            stdout_summary="ok",
            stderr_summary="",
            blockers=[],
            warnings=[],
        )
        result["report_artifacts"] = "artifacts/codex-runs/scalar-report.md"
        return result

    monkeypatch.setattr(workflow_action_runner, "_run_command_action", fake_command_result)

    result = run_workflow_action("example.scalar-artifact")

    assert result["report_artifacts"] == ["artifacts/codex-runs/scalar-report.md"]


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


def test_timeout_cleanup_uses_taskkill_on_windows(monkeypatch) -> None:
    calls: list[list[str]] = []
    killed: list[bool] = []

    class FakeProcess:
        pid = 12345

        def wait(self, timeout: int) -> None:
            return None

        def kill(self) -> None:
            killed.append(True)

    def fake_run(command, **_kwargs):  # noqa: ANN001, ANN003
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(workflow_action_runner.os, "name", "nt")
    monkeypatch.setattr(workflow_action_runner.subprocess, "run", fake_run)

    workflow_action_runner._terminate_process_group(FakeProcess())

    assert calls == [["taskkill", "/PID", "12345", "/T", "/F"]]
    assert killed == []


def test_inline_env_command_is_normalized_for_cross_platform_spawn() -> None:
    command, env_overrides = workflow_action_runner._normalize_inline_env_command(
        ("env", "ONE=1", "TWO=value with spaces", "make", "target")
    )

    assert command == ("make", "target")
    assert env_overrides == {"ONE": "1", "TWO": "value with spaces"}


def test_bare_inline_env_command_is_normalized_for_windows_spawn() -> None:
    command, env_overrides = workflow_action_runner._normalize_inline_env_command(
        ("ONE=1", "TWO=value with spaces", "make", "target")
    )

    assert command == ("make", "target")
    assert env_overrides == {"ONE": "1", "TWO": "value with spaces"}


def test_inline_env_command_without_program_is_left_unchanged() -> None:
    command, env_overrides = workflow_action_runner._normalize_inline_env_command(("env", "ONE=1"))

    assert command == ("env", "ONE=1")
    assert env_overrides == {}


def test_relative_subprocess_executable_is_resolved_from_repo_root(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "app" / "backend" / ".venv" / "Scripts" / "python.exe"
    executable.parent.mkdir(parents=True)
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(workflow_action_runner, "REPO_ROOT", tmp_path)

    command = workflow_action_runner._resolve_subprocess_executable(
        ("app\\backend\\.venv\\Scripts\\python.exe", "app\\backend\\scripts\\provider_smoke.py")
    )

    assert command == (str(executable), "app\\backend\\scripts\\provider_smoke.py")


def test_run_subprocess_applies_env_overrides_without_env_binary() -> None:
    completed = workflow_action_runner._run_subprocess(
        (
            sys.executable,
            "-c",
            "import os; print(os.environ.get('INFRA_CONFIG_PORTAL_TEST_ENV'))",
        ),
        10,
        env_overrides={"INFRA_CONFIG_PORTAL_TEST_ENV": "ready"},
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "ready"


def test_operator_readonly_sweep_surfaces_report_quality_gate(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "artifacts" / "real-lab"
    report_dir.mkdir(parents=True)
    (report_dir / "operator-readonly-sweep-latest.json").write_text(
        json.dumps(
            {
                "quality_gate": {
                    "status": "blocked",
                    "blocked_actions": ["netapp.iscsi-setup-validate", "esxi.vm-deploy-validate"],
                    "warning_actions": ["firmware.compliance-check"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(workflow_action_runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path / "traces")

    def fake_run(command: tuple[str, ...], timeout_seconds: int, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout='{"quality_gate":{"status":"blocked"}}', stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("operator-readonly-sweep.real-lab")

    assert result["status"] == "blocked"
    assert result["return_code"] == 0
    assert result["blockers"] == [
        "Read-only sweep reported lab blockers: netapp.iscsi-setup-validate, esxi.vm-deploy-validate."
    ]
    assert "firmware.compliance-check" in result["warnings"]


def test_operator_readonly_sweep_warns_on_optional_parity_blockers(monkeypatch, tmp_path: Path) -> None:
    report_dir = tmp_path / "artifacts" / "real-lab"
    report_dir.mkdir(parents=True)
    (report_dir / "operator-readonly-sweep-latest.json").write_text(
        json.dumps(
            {
                "quality_gate": {
                    "status": "completed",
                    "optional_blocked_actions": ["esxi.iscsi-datastore-validate"],
                    "warning_actions": ["netapp.nfs-setup-validate"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(workflow_action_runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path / "traces")

    def fake_run(command: tuple[str, ...], timeout_seconds: int, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, stdout='{"quality_gate":{"status":"completed"}}', stderr="")

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    result = run_workflow_action("operator-readonly-sweep.real-lab")

    assert result["status"] == "completed"
    assert result["return_code"] == 0
    assert result["blockers"] == []
    assert (
        "Read-only sweep passed the required path, but optional parity checks reported blockers: "
        "esxi.iscsi-datastore-validate."
    ) in result["warnings"]
    assert "netapp.nfs-setup-validate" in result["warnings"]


def test_latest_workflow_action_run_traces_by_action_uses_newest_trace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "old",
            "action_id": "example.action",
            "stage_id": "reports",
            "finished_at": "2026-06-30T00:00:00+00:00",
        }
    )
    workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "new",
            "action_id": "example.action",
            "stage_id": "reports",
            "finished_at": "2026-06-30T01:00:00+00:00",
        }
    )
    workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "other",
            "action_id": "other.action",
            "stage_id": "reports",
            "finished_at": "2026-06-30T00:30:00+00:00",
        }
    )

    latest = workflow_action_run_store.latest_workflow_action_run_traces_by_action()

    assert latest["example.action"]["run_id"] == "new"
    assert latest["other.action"]["run_id"] == "other"


def test_list_workflow_action_run_traces_is_newest_first_and_limited(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    for index in range(5):
        workflow_action_run_store.save_workflow_action_run_trace(
            {
                "run_id": f"run-{index}",
                "action_id": "example.action",
                "stage_id": "reports",
                "finished_at": f"2026-06-30T00:0{index}:00+00:00",
            }
        )

    traces = workflow_action_run_store.list_workflow_action_run_traces("example.action", limit=2)

    assert [trace["run_id"] for trace in traces] == ["run-4", "run-3"]


def test_list_workflow_action_runs_returns_compact_history(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setattr(workflow_action_runner, "workflow_action_exists", lambda _action_id: True)
    monkeypatch.setattr(
        workflow_action_runner,
        "get_workflow_action",
        lambda _action_id: (_ for _ in ()).throw(AssertionError("History listing should not build the workflow catalog.")),
    )
    workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "run-1",
            "action_id": "example.action",
            "action_label": "Example",
            "stage_id": "reports",
            "stage_label": "Reports",
            "mode": "read_only",
            "started_at": "2026-06-30T00:00:00+00:00",
            "finished_at": "2026-06-30T00:00:01+00:00",
            "checked_at": "2026-06-30T00:00:01+00:00",
            "status": "completed",
            "source_type": "live_probe",
            "freshness": "current",
            "not_mock": True,
            "executed": True,
            "return_code": 0,
            "stdout_summary": "x" * 2000,
            "stderr_summary": "y" * 2000,
            "report_artifacts": [f"artifact-{index}.json" for index in range(15)],
            "summary": "done",
            "blockers": [],
            "warnings": [],
            "next_action": "continue",
        }
    )

    runs = workflow_action_runner.list_workflow_action_runs("example.action", limit=1)

    assert len(runs) == 1
    assert len(runs[0]["stdout_summary"]) < 700
    assert len(runs[0]["stderr_summary"]) < 700
    assert len(runs[0]["report_artifacts"]) == 10
    assert runs[0]["trace_artifact"].endswith(".json")


def test_live_status_action_uses_live_lab_timeout(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def fake_run(
        command: tuple[str, ...],
        timeout_seconds: int,
        *,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-live-status")
        assert timeout_seconds == 180
        assert env_overrides == {"PROVIDER_LAB_LIVE_STAGE_TIMEOUT_SECONDS": "20"}
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


def test_guarded_action_runs_with_exact_confirmation_and_gates(
    monkeypatch,
    tmp_path: Path,
    db_session: Session,
) -> None:
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

    def fail_subprocess(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("RAID apply should run through the in-process API runner on Windows.")

    captured_context: dict[str, object] = {}

    def fake_apply_raid_plan(session: Session, request: object, *, guarded_context: object) -> dict:
        assert session is db_session
        assert request.confirmation_phrase == "APPLY HPE RAID PLAN"
        captured_context["context"] = guarded_context
        return {"status": "completed", "provider_id": "hpe-raid-apply"}

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fail_subprocess)
    monkeypatch.setattr(workflow_action_runner, "apply_hpe_raid_plan", fake_apply_raid_plan)

    result = run_workflow_action(
        "raid.apply",
        db_session,
        payload={
            "ilo_host": "192.168.1.11",
            "confirmation_phrase": "  APPLY HPE RAID PLAN  ",
            "confirmed_gates": [
                " HPE_RAID_ALLOW_DESTRUCTIVE=true ",
                "HPE_RAID_ALLOW_DESTRUCTIVE=true",
                "",
                None,
            ],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["command"] == "POST /api/v1/providers/ilo-redfish/hpe-raid-apply"
    context = captured_context["context"]
    assert context.action_id == "raid.apply"
    assert context.gate_value("HPE_RAID_ALLOW_DESTRUCTIVE") == "true"
    assert context.confirmation_phrase == "APPLY HPE RAID PLAN"
    assert "Guarded workflow action completed" in result["summary"]


def test_cisco_guarded_command_is_profile_bound_and_receives_request_local_gates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setattr(
        workflow_registry,
        "active_cisco_network_defaults",
        lambda: {"planned_management_ip": "10.10.8.204"},
    )

    class AllowPolicy:
        def action_blockers(self, action_id: str, category: object) -> list[str]:
            return []

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: AllowPolicy())

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    captured: dict[str, object] = {}

    def fake_run(
        command: tuple[str, ...],
        timeout_seconds: int,
        *,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["timeout_seconds"] = timeout_seconds
        captured["env_overrides"] = env_overrides
        return subprocess.CompletedProcess(command, 0, stdout="bootstrap complete", stderr="")

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fake_run)

    action = get_unblocked_action("cisco.apply-bootstrap")
    assert action["required_confirmations"] == [
        "APPLY CISCO CONSOLE BOOTSTRAP 10.10.8.204"
    ]
    assert "LAB_TARGET_ACK=10.10.8.204" in action["required_gates"]

    result = run_workflow_action(
        "cisco.apply-bootstrap",
        payload={
            "confirmation_phrase": "APPLY CISCO CONSOLE BOOTSTRAP 10.10.8.204",
            "confirmed_gates": action["required_gates"],
        },
    )

    assert result["status"] == "completed"
    assert captured["command"] == ("make", "provider-lab-cisco-vlan10-bootstrap-apply")
    assert captured["env_overrides"] == {
        "CISCO_CONSOLE_APPLY_ENABLED": "true",
        "LAB_APPLY_ACK": "YES",
        "LAB_TARGET_ACK": "10.10.8.204",
        "CISCO_BOOTSTRAP_CONFIRM": "APPLY CISCO CONSOLE BOOTSTRAP 10.10.8.204",
    }


def test_vm_teardown_guarded_runner_uses_configured_name_and_request_local_gates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setenv("VM_TEARDOWN_VM_NAME", "single-server-smoke-vm")
    monkeypatch.setattr(
        workflow_registry,
        "settings",
        SimpleNamespace(esxi_test_host="10.10.8.203"),
    )

    class AllowPolicy:
        def action_blockers(self, action_id: str, category: object) -> list[str]:
            return []

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: AllowPolicy())

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    captured: dict[str, object] = {}

    def fake_apply(vm_name: str, *, guarded_context: object) -> dict:
        captured["vm_name"] = vm_name
        captured["context"] = guarded_context
        return {
            "provider_id": "esxi-readonly",
            "action": "vm-teardown-apply",
            "status": "completed",
            "request": {"vm_name": vm_name, "valid": True},
            "target": {"configured_target": "10.10.8.203"},
            "target_binding": {"bound": True, "direct_esxi": True},
            "vm_evidence": {"absence_confirmed": True},
            "apply": {"destroy_attempted": True, "absence_confirmed": True},
        }

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "apply_esxi_vm_teardown", fake_apply)

    action = get_unblocked_action("esxi.vm-teardown-apply")
    result = run_workflow_action(
        "esxi.vm-teardown-apply",
        payload={
            "vm_name": "payload-must-not-change-scope",
            "confirmation_phrase": "REMOVE ONE ESXI VM",
            "confirmed_gates": action["required_gates"],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert captured["vm_name"] == "single-server-smoke-vm"
    context = captured["context"]
    assert context.action_id == "esxi.vm-teardown-apply"
    assert context.gate_value("VM_TEARDOWN_CONFIRM_VM_NAME") == "single-server-smoke-vm"
    assert context.gate_value("VM_TEARDOWN_CONFIRM_ESXI_TARGET") == "10.10.8.203"
    assert context.confirmation_phrase == "REMOVE ONE ESXI VM"


@pytest.mark.parametrize(
    ("action_id", "service_name", "service_action"),
    [
        (
            "esxi.vm-teardown-preview",
            "build_esxi_vm_teardown_preview",
            "vm-teardown-preview",
        ),
        (
            "esxi.vm-teardown-validate",
            "validate_esxi_vm_teardown",
            "vm-teardown-validation",
        ),
    ],
)
def test_vm_teardown_readonly_runners_use_only_the_configured_name(
    monkeypatch,
    tmp_path: Path,
    action_id: str,
    service_name: str,
    service_action: str,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setenv("VM_TEARDOWN_VM_NAME", "single-server-smoke-vm")

    def get_unblocked_action(requested_action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(requested_action_id)
        action["blockers"] = []
        action["current_availability"] = "available"
        return action

    captured: dict[str, object] = {}

    def fake_readonly(vm_name: str) -> dict:
        captured["vm_name"] = vm_name
        return {
            "provider_id": "esxi-readonly",
            "action": service_action,
            "status": "ready" if action_id.endswith("validate") else "preview_ready",
            "request": {"vm_name": vm_name, "valid": True},
            "target": {"configured_target": "10.10.8.203"},
            "target_binding": {"bound": True, "direct_esxi": True},
            "vm_evidence": {
                "exists": not action_id.endswith("validate"),
                "absence_confirmed": action_id.endswith("validate"),
            },
        }

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, service_name, fake_readonly)

    result = run_workflow_action(
        action_id,
        payload={"vm_name": "payload-must-not-change-scope"},
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert captured["vm_name"] == "single-server-smoke-vm"


def test_vm_teardown_runner_refuses_mismatched_name_before_service_call(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    monkeypatch.setenv("VM_TEARDOWN_VM_NAME", "single-server-smoke-vm")
    monkeypatch.setattr(
        workflow_registry,
        "settings",
        SimpleNamespace(esxi_test_host="10.10.8.203"),
    )

    class AllowPolicy:
        def action_blockers(self, action_id: str, category: object) -> list[str]:
            return []

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: AllowPolicy())

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    def fail_apply(*_args, **_kwargs):
        raise AssertionError("Mismatched VM confirmation must not reach the service.")

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "apply_esxi_vm_teardown", fail_apply)

    result = run_workflow_action(
        "esxi.vm-teardown-apply",
        payload={
            "confirmation_phrase": "REMOVE ONE ESXI VM",
            "confirmed_gates": [
                "VM_TEARDOWN_APPLY=true",
                "VM_TEARDOWN_ALLOW_DELETE=true",
                "VM_TEARDOWN_ALLOW_POWER_OFF=true",
                "LAB_ALLOW_POWER_ACTIONS=true",
                "VM_TEARDOWN_CONFIRM_VM_NAME=some-other-vm",
                "VM_TEARDOWN_CONFIRM_ESXI_TARGET=10.10.8.203",
            ],
        },
    )

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert any(
        "VM_TEARDOWN_CONFIRM_VM_NAME=single-server-smoke-vm" in blocker
        for blocker in result["blockers"]
    )


def test_guarded_action_ignores_unregistered_env_gates(
    monkeypatch,
    tmp_path: Path,
    db_session: Session,
) -> None:
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

    captured_context: dict[str, object] = {}

    def fake_apply_raid_plan(session: Session, request: object, *, guarded_context: object) -> dict:
        assert session is db_session
        assert request.confirmation_phrase == "APPLY HPE RAID PLAN"
        captured_context["context"] = guarded_context
        return {"status": "completed", "provider_id": "hpe-raid-apply"}

    monkeypatch.delenv("PYTHONPATH", raising=False)
    monkeypatch.delenv("LAB_ALLOW_FACTORY_RESET", raising=False)
    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "apply_hpe_raid_plan", fake_apply_raid_plan)

    result = run_workflow_action(
        "raid.apply",
        db_session,
        payload={
            "ilo_host": "192.168.1.11",
            "confirmation_phrase": "APPLY HPE RAID PLAN",
            "confirmed_gates": [
                "HPE_RAID_ALLOW_DESTRUCTIVE=true",
                "PYTHONPATH=C:\\malicious",
                "LAB_ALLOW_FACTORY_RESET=true",
            ],
        },
    )

    assert result["status"] == "completed"
    context = captured_context["context"]
    assert context.gate_value("HPE_RAID_ALLOW_DESTRUCTIVE") == "true"
    assert context.gate_value("PYTHONPATH") is None
    assert context.gate_value("LAB_ALLOW_FACTORY_RESET") is None
    assert os.environ.get("PYTHONPATH") is None
    assert os.environ.get("LAB_ALLOW_FACTORY_RESET") is None


def test_factory_reset_rebuild_actions_are_in_process_api_runners() -> None:
    action_ids = [
        "netapp.factory-reset-preview",
        "netapp.factory-reset-apply",
        "netapp.factory-reset-validate",
        "raid.apply",
        "raid.factory-reset-preview",
        "raid.factory-reset-apply",
        "raid.reset-commit",
        "netapp.setup-apply",
        "netapp.nfs-setup-apply",
        "netapp.iscsi-setup-preview",
        "netapp.iscsi-setup-apply",
        "netapp.iscsi-setup-validate",
    ]

    for action_id in action_ids:
        spec = workflow_action_allowlist.get_workflow_action_execution_spec(action_id)
        action = workflow_registry.get_workflow_action(action_id)

        assert spec is not None
        assert spec.kind == "api"
        assert spec.api_endpoint
        assert not spec.command
        assert action["source_type"] == "api_endpoint"


def test_netapp_iscsi_apply_uses_request_local_confirmation_context(monkeypatch, db_session) -> None:
    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)

    def fail_subprocess(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("NetApp iSCSI apply should run through the in-process API runner on Windows.")

    captured_context: dict[str, object] = {}

    def fake_apply_iscsi_setup(*, guarded_context: object) -> dict:
        captured_context["context"] = guarded_context
        return {"status": "completed", "provider_id": "netapp-ontap", "action": "iscsi-setup-apply"}

    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fail_subprocess)
    monkeypatch.setattr(workflow_action_runner, "apply_netapp_iscsi_setup", fake_apply_iscsi_setup)

    result = run_workflow_action(
        "netapp.iscsi-setup-apply",
        db_session,
        payload={
            "confirmation_phrase": "  APPLY NETAPP ISCSI SETUP  ",
            "confirmed_gates": [
                "PROVIDER_MODE=local-lab-readwrite",
                "NETAPP_ISCSI_SETUP_APPLY=true",
                'NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP"',
                "NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true",
            ],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["command"] == "POST /api/v1/providers/netapp-ontap/iscsi-setup-apply"
    context = captured_context["context"]
    assert context.action_id == "netapp.iscsi-setup-apply"
    assert context.confirmation_phrase == "APPLY NETAPP ISCSI SETUP"
    assert context.gate_value("PROVIDER_MODE") == "local-lab-readwrite"
    assert context.gate_value("NETAPP_ISCSI_SETUP_APPLY") == "true"
    assert context.gate_value("NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE") == "true"


def test_concurrent_workflow_requests_do_not_share_confirmations() -> None:
    actions = {
        "netapp.iscsi-setup-apply": workflow_registry.get_workflow_action("netapp.iscsi-setup-apply"),
        "netapp.nfs-setup-apply": workflow_registry.get_workflow_action("netapp.nfs-setup-apply"),
    }

    payloads = {
        "netapp.iscsi-setup-apply": {
            "confirmation_phrase": "APPLY NETAPP ISCSI SETUP",
            "confirmed_gates": actions["netapp.iscsi-setup-apply"]["required_gates"],
        },
        "netapp.nfs-setup-apply": {
            "confirmation_phrase": "APPLY NETAPP NFS SETUP",
            "confirmed_gates": actions["netapp.nfs-setup-apply"]["required_gates"],
        },
    }

    def run(action_id: str):  # noqa: ANN202
        return workflow_action_runner._guarded_action_context(action_id, payloads[action_id])

    with ThreadPoolExecutor(max_workers=2) as pool:
        contexts = {action_id: context for action_id, context in zip(actions, pool.map(run, actions))}

    for action_id, expected_phrase in (
        ("netapp.iscsi-setup-apply", "APPLY NETAPP ISCSI SETUP"),
        ("netapp.nfs-setup-apply", "APPLY NETAPP NFS SETUP"),
    ):
        context = contexts[action_id]
        assert context.confirmation_phrase == expected_phrase
        assert context.action_id == action_id
        assert context.confirmed_gates
    assert os.environ.get("NETAPP_ISCSI_SETUP_CONFIRM") is None
    assert os.environ.get("NETAPP_NFS_SETUP_CONFIRM") is None


def test_raid_factory_reset_apply_reaches_safe_refusing_endpoint(monkeypatch, db_session) -> None:
    def fake_action(_action_id: str) -> dict:
        return {
            "action_id": "raid.factory-reset-apply",
            "label": "Apply RAID Factory Reset",
            "stage": "raid",
            "stage_label": "RAID",
            "mode": "destructive",
            "source_type": "api_endpoint",
            "api_endpoint": "/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-apply",
            "api_method": "POST",
            "current_availability": "manual_command_required",
            "blockers": [],
            "required_confirmations": ["FACTORY RESET HPE RAID"],
            "required_gates": ["LAB_ALLOW_FACTORY_RESET=true", "HPE_RAID_ALLOW_FACTORY_RESET=true"],
            "reports": [],
            "next_action": "Review blocked factory-reset apply report.",
        }

    def fake_apply(_session, request, *, guarded_context) -> dict:  # noqa: ANN001
        assert request.confirmation_phrase == "FACTORY RESET HPE RAID"
        assert guarded_context.confirmation_phrase == "FACTORY RESET HPE RAID"
        return {
            "status": "blocked",
            "blockers": ["No implemented HPE SmartStorage logical-drive delete/factory-reset executor exists yet."],
            "warnings": ["No destructive command was sent."],
        }

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", fake_action)
    monkeypatch.setattr(workflow_action_runner, "apply_hpe_raid_factory_reset", fake_apply)

    result = run_workflow_action(
        "raid.factory-reset-apply",
        db_session,
        payload={
            "confirmation_phrase": "FACTORY RESET HPE RAID",
            "confirmed_gates": ["LAB_ALLOW_FACTORY_RESET=true", "HPE_RAID_ALLOW_FACTORY_RESET=true"],
        },
    )

    assert result["status"] == "blocked"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert "endpoint ran and reported blockers" in result["summary"]
    assert result["blockers"] == [
        "No implemented HPE SmartStorage logical-drive delete/factory-reset executor exists yet."
    ]


def test_netapp_setup_apply_injects_gates_without_subprocess(monkeypatch, tmp_path: Path) -> None:
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

    def fail_subprocess(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("NetApp setup apply should run through the in-process API runner on Windows.")

    captured_context: dict[str, object] = {}

    def fake_apply_netapp_setup(*, guarded_context) -> dict:  # noqa: ANN001
        captured_context["context"] = guarded_context
        return {"status": "completed", "provider_id": "netapp-setup-apply"}

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fail_subprocess)
    monkeypatch.setattr(workflow_action_runner, "apply_netapp_setup", fake_apply_netapp_setup)

    result = run_workflow_action(
        "netapp.setup-apply",
        payload={
            "confirmation_phrase": "APPLY NETAPP CLUSTER SETUP",
            "confirmed_gates": ["NETAPP_SETUP_APPLY=true", "NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true"],
        },
    )

    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["command"] == "POST /api/v1/providers/netapp-ontap/setup-apply"
    context = captured_context["context"]
    assert context.confirmation_phrase == "APPLY NETAPP CLUSTER SETUP"
    assert context.gate_value("NETAPP_SETUP_APPLY") == "true"
    assert context.gate_value("NETAPP_SETUP_ALLOW_CLUSTER_CREATE") == "true"


def test_netapp_console_login_state_runs_in_process_api(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    def fail_subprocess(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("NetApp console login-state should run through the in-process API runner on Windows.")

    def fake_login_state() -> dict:
        return {
            "provider_id": "netapp-ontap",
            "status": "blocked",
            "message": "NetApp console login/read-only state identification completed.",
            "blockers": ["NetApp console/API credentials are missing; guarded login was skipped."],
        }

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fail_subprocess)
    monkeypatch.setattr(workflow_action_runner, "run_netapp_console_login_state", fake_login_state)

    result = run_workflow_action("netapp.console-login-state")

    assert result["status"] == "blocked"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["command"] == "POST /api/v1/providers/netapp-ontap/console-login-state"
    assert result["blockers"] == ["NetApp console/API credentials are missing; guarded login was skipped."]


def test_netapp_ha_node_diagnose_runs_in_process_api(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    def get_unblocked_action(action_id: str) -> dict:
        action = workflow_registry.get_workflow_action(action_id)
        action["blockers"] = []
        action["current_availability"] = "manual_command_required"
        return action

    def fail_subprocess(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("NetApp HA/node diagnose should run through the in-process API runner on Windows.")

    def fake_ha_diagnose() -> dict:
        return {
            "provider_id": "netapp-ontap",
            "status": "blocked",
            "message": "NetApp HA/node diagnostic completed with read-only console commands.",
            "blockers": ["NetApp node health is not clean: X20-01."],
        }

    monkeypatch.setattr(workflow_action_runner, "get_workflow_action", get_unblocked_action)
    monkeypatch.setattr(workflow_action_runner, "_run_subprocess", fail_subprocess)
    monkeypatch.setattr(workflow_action_runner, "diagnose_netapp_ha_node_warning", fake_ha_diagnose)

    result = run_workflow_action("netapp.ha-node-diagnose")

    assert result["status"] == "blocked"
    assert result["executed"] is True
    assert result["return_code"] == 0
    assert result["command"] == "POST /api/v1/providers/netapp-ontap/ha-node-diagnose"
    assert result["blockers"] == ["NetApp node health is not clean: X20-01."]


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

    def fake_run(
        command: tuple[str, ...],
        timeout_seconds: int,
        *,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-vcenter-install-apply")
        assert timeout_seconds == 7200
        assert env_overrides == {
            "VCENTER_INSTALL_APPLY": "true",
            "VCENTER_INSTALL_CONFIRM": "DEPLOY VCENTER",
            "VCENTER_INSTALL_ALLOW_DEPLOY": "true",
        }
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

    def fake_run(
        command: tuple[str, ...],
        timeout_seconds: int,
        *,
        env_overrides: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        assert command == ("make", "provider-lab-vcenter-attach-esxi-apply")
        assert timeout_seconds == 1200
        assert env_overrides == {
            "VCENTER_ATTACH_ESXI_APPLY": "true",
            "VCENTER_ATTACH_ESXI_CONFIRM": "ATTACH ESXI TO VCENTER",
            "VCENTER_ATTACH_ESXI_ALLOW": "true",
        }
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


@pytest.mark.parametrize(
    ("action_id", "expected_blocker"),
    [
        ("vcenter-netapp.readiness", "NetApp is disabled by the active lab profile."),
        ("netapp.setup-preview", "NetApp is disabled by the active lab profile."),
        ("netapp.setup-apply", "NetApp is disabled by the active lab profile."),
        ("netapp.nfs-setup-apply", "NetApp is disabled by the active lab profile."),
    ],
)
def test_out_of_scope_action_run_is_blocked_without_execution(
    action_id: str,
    expected_blocker: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path / "runs")
    create_lab_profile(
        {
            "name": "Single Server Lab",
            "features": {"netapp_enabled": False, "vcenter_enabled": False},
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )

    result = run_workflow_action(action_id)

    assert result["status"] == "blocked"
    assert result["executed"] is False
    assert result["return_code"] is None
    assert result["blockers"] == [expected_blocker]


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


def test_workflow_action_diagnosis_explains_blocked_guard_without_suggesting_apply(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)

    post = client.post("/api/v1/workflows/actions/netapp.setup-apply/run")
    diagnosis = client.get("/api/v1/workflows/actions/netapp.setup-apply/diagnosis")

    assert post.status_code == 200
    assert post.json()["status"] == "blocked"
    assert diagnosis.status_code == 200
    payload = diagnosis.json()
    assert payload["status"] == "blocked"
    assert payload["advisory_source"] == "local_rules"
    assert payload["ai_enabled"] is False
    assert "confirmation" in payload["probable_cause"].lower() or "guarded" in payload["probable_cause"].lower()
    assert payload["suggested_action_safe"] is True
    assert payload["suggested_action_id"] != "netapp.setup-apply"
    assert payload["suggested_action_id"]
    suggested_action = workflow_registry.get_workflow_action(payload["suggested_action_id"])
    assert suggested_action["mode"] in {"read_only", "report_only"}
    assert any("does not execute" in note for note in payload["safety_notes"])
    assert payload["recent_runs"][0]["status"] == "blocked"


def test_workflow_action_diagnosis_uses_failed_trace_evidence_without_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", tmp_path)
    workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "run-failed",
            "action_id": "build-verification.toolchain-check",
            "action_label": "Toolchain Check",
            "stage_id": "build-verification",
            "stage_label": "Build Verification",
            "mode": "read_only",
            "started_at": "2026-07-06T00:00:00+00:00",
            "finished_at": "2026-07-06T00:00:01+00:00",
            "checked_at": "2026-07-06T00:00:01+00:00",
            "status": "failed",
            "source_type": "live_probe",
            "freshness": "current",
            "not_mock": True,
            "command": "make provider-lab-toolchain-check",
            "executed": True,
            "return_code": 1,
            "stdout_summary": "toolchain output",
            "stderr_summary": "token=super-secret-value connection refused",
            "report_artifacts": [],
            "summary": "Safe read-only/report-only action failed before completing cleanly.",
            "blockers": ["Command exited with code 1; review evidence before rerun."],
            "warnings": [],
            "next_action": "Review the run trace.",
        }
    )

    payload = workflow_action_diagnosis.diagnose_workflow_action("build-verification.toolchain-check")

    assert payload["status"] == "failed"
    assert payload["suggested_action_id"] == "build-verification.toolchain-check"
    assert payload["suggested_action_safe"] is True
    assert "connection" in payload["probable_cause"].lower() or "reach" in payload["probable_cause"].lower()
    assert "super-secret-value" not in json.dumps(payload)
    assert payload["evidence"]


def test_operator_issue_packet_captures_route_and_redacted_recent_runs(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "traces"
    packet_dir = tmp_path / "packets"
    monkeypatch.setattr(workflow_action_run_store, "WORKFLOW_ACTION_RUN_TRACE_DIR", trace_dir)
    monkeypatch.setattr(operator_issue_packets, "OPERATOR_ISSUE_PACKET_DIR", packet_dir)
    workflow_action_run_store.save_workflow_action_run_trace(
        {
            "run_id": "run-feedback",
            "action_id": "build-verification.toolchain-check",
            "action_label": "Toolchain Check",
            "stage_id": "build-verification",
            "stage_label": "Build Verification",
            "mode": "read_only",
            "started_at": "2026-07-06T00:00:00+00:00",
            "finished_at": "2026-07-06T00:00:01+00:00",
            "checked_at": "2026-07-06T00:00:01+00:00",
            "status": "failed",
            "source_type": "live_probe",
            "freshness": "current",
            "not_mock": True,
            "command": "make provider-lab-toolchain-check",
            "executed": True,
            "return_code": 1,
            "stdout_summary": "",
            "stderr_summary": "password=super-secret-value connection refused",
            "report_artifacts": [],
            "summary": "Toolchain failed with connection refused.",
            "blockers": ["Connection refused while reading target."],
            "warnings": [],
            "next_action": "Review the run trace.",
        }
    )

    response = client.post(
        "/api/v1/operator-issue-packets",
        json={
            "route": "/validation",
            "page_title": "Validation",
            "operator_note": "The validation button looked done but the run failed. token=super-secret-value",
            "ui_context": {"visible_tab": "handoff", "last_button": "Run Validation"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    encoded = json.dumps(payload)
    assert payload["route"] == "/validation"
    assert payload["recent_problem_runs"][0]["action_id"] == "build-verification.toolchain-check"
    assert payload["diagnoses"][0]["suggested_action_safe"] is True
    assert "fast-verify.ps1" in " ".join(payload["suggested_next_steps"])
    assert "super-secret-value" not in encoded
    assert (packet_dir / f"{payload['packet_id']}.json").exists()
    assert (packet_dir / f"{payload['packet_id']}.md").exists()


def _process_args() -> str:
    if sys.platform == "win32":
        return subprocess.run(
            (
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | Select-Object -ExpandProperty CommandLine",
            ),
            check=False,
            capture_output=True,
            text=True,
        ).stdout
    return subprocess.run(
        ("ps", "-eo", "args"),
        check=False,
        capture_output=True,
        text=True,
    ).stdout
