from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from app.services.workflow_registry import get_workflow_action


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "operator_readonly_sweep.py"
SPEC = importlib.util.spec_from_file_location("operator_readonly_sweep", SCRIPT_PATH)
assert SPEC and SPEC.loader
operator_readonly_sweep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator_readonly_sweep)


def test_action_group_contains_only_registered_read_only_or_report_actions() -> None:
    action_ids = [action_id for _stage, action_id, _label in operator_readonly_sweep.ACTION_GROUPS]

    assert len(action_ids) == len(set(action_ids))
    for action_id in action_ids:
        action = get_workflow_action(action_id)
        assert action["mode"] in {"read_only", "report_only"}, action_id
        assert not action.get("guarded_run_supported"), action_id


def test_quality_gate_fails_when_action_uses_non_live_evidence() -> None:
    report = {
        "results": [
            {
                "action_id": "cisco.ssh-readonly-probe",
                "status": "completed",
                "not_mock": True,
                "source_type": "live_probe",
                "warnings": [],
            },
            {
                "action_id": "netapp.live-state",
                "status": "completed",
                "not_mock": True,
                "source_type": "historical_artifact",
                "warnings": [],
            },
        ]
    }

    gate = operator_readonly_sweep._quality_gate(report)

    assert gate["status"] == "failed"
    assert gate["failed_actions"] == ["netapp.live-state"]
    assert "live real-lab evidence" in gate["message"]


def test_quality_gate_fails_when_inner_provider_payload_is_stale() -> None:
    report = {
        "results": [
            {
                "action_id": "netapp.live-state",
                "status": "blocked",
                "not_mock": True,
                "source_type": "live_probe",
                "evidence_source_type": "live_cached",
                "evidence_freshness": "stale",
                "evidence_is_current": False,
                "warnings": [],
            },
        ]
    }

    gate = operator_readonly_sweep._quality_gate(report)

    assert gate["status"] == "failed"
    assert gate["failed_actions"] == ["netapp.live-state"]


def test_quality_gate_keeps_optional_protocol_blockers_out_of_required_gate() -> None:
    report = {
        "results": [
            {
                "action_id": "netapp.nfs-setup-validate",
                "status": "completed",
                "not_mock": True,
                "source_type": "live_probe",
                "warnings": [],
            },
            {
                "action_id": "netapp.iscsi-setup-validate",
                "optional": True,
                "status": "blocked",
                "not_mock": True,
                "source_type": "live_probe",
                "warnings": [],
            },
            {
                "action_id": "esxi.iscsi-datastore-validate",
                "optional": True,
                "status": "blocked",
                "not_mock": True,
                "source_type": "live_probe",
                "warnings": [],
            },
        ]
    }

    gate = operator_readonly_sweep._quality_gate(report)

    assert gate["status"] == "completed"
    assert "required read-only operator actions completed" in gate["message"]
    assert "optional parity check" in gate["message"]
    assert gate["optional_blocked_actions"] == [
        "netapp.iscsi-setup-validate",
        "esxi.iscsi-datastore-validate",
    ]


def test_selected_actions_mark_inactive_shared_storage_protocol_optional() -> None:
    state = _profile_state(storage_protocol="nfs")
    actions = {
        item["action_id"]: item
        for item in operator_readonly_sweep._selected_actions(state)
    }

    assert actions["netapp.nfs-setup-validate"]["optional"] is False
    assert actions["netapp.iscsi-setup-validate"]["optional"] is True
    assert "active storage protocol is NFS" in actions["netapp.iscsi-setup-validate"]["optional_reason"]
    assert actions["esxi.iscsi-datastore-validate"]["optional"] is True


def test_selected_actions_mark_nfs_optional_when_iscsi_is_active() -> None:
    state = _profile_state(storage_protocol="iscsi")
    actions = {
        item["action_id"]: item
        for item in operator_readonly_sweep._selected_actions(state)
    }

    assert actions["netapp.nfs-setup-validate"]["optional"] is True
    assert actions["netapp.iscsi-setup-validate"]["optional"] is False
    assert actions["esxi.iscsi-datastore-validate"]["optional"] is False


def test_selected_actions_skip_netapp_when_profile_uses_local_storage() -> None:
    state = _profile_state(netapp_enabled=False, storage_protocol="local")
    actions = {
        item["action_id"]: item
        for item in operator_readonly_sweep._selected_actions(state)
    }

    assert actions["netapp.live-state"]["status"] == "skipped"
    assert actions["netapp.nfs-setup-validate"]["status"] == "skipped"
    assert actions["netapp.iscsi-setup-validate"]["status"] == "skipped"
    assert actions["esxi.iscsi-datastore-validate"]["status"] == "skipped"


def test_run_action_surfaces_payload_blockers_from_failed_api_result(monkeypatch) -> None:
    def fake_run_workflow_action(_action_id, _session, payload=None):
        return {
            "action_id": "ilo.reachability",
            "blockers": [],
            "executed": True,
            "not_mock": True,
            "return_code": None,
            "source_type": "live_probe",
            "status": "failed",
            "stderr_summary": "",
            "stdout_summary": json.dumps({
                "blockers": ["For lab/self-signed iLO, set ILO_TEST_VERIFY_TLS=false locally and retry."],
                "freshness": "current",
                "source_type": "live_probe",
                "warnings": ["TLS verification failed during endpoint detection."]
            }),
            "summary": "failed",
            "trace_artifact": "trace.json",
            "warnings": [],
        }

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(operator_readonly_sweep, "run_workflow_action", fake_run_workflow_action)
    monkeypatch.setattr(operator_readonly_sweep, "SessionLocal", FakeSession)

    result = operator_readonly_sweep._run_action("ilo.reachability", "iLO reachability", "server")

    assert result["status"] == "failed"
    assert result["evidence_source_type"] == "live_probe"
    assert result["evidence_freshness"] == "current"
    assert result["blockers"] == ["For lab/self-signed iLO, set ILO_TEST_VERIFY_TLS=false locally and retry."]
    assert result["warnings"] == ["TLS verification failed during endpoint detection."]


def test_main_writes_current_progress_report_before_and_after_each_action(monkeypatch) -> None:
    writes: list[dict] = []

    def fake_write_report(report):
        writes.append(json.loads(json.dumps(report)))

    def fake_run_action(action_id, label, stage, *, optional=False):
        return {
            "action_id": action_id,
            "label": label,
            "optional": optional,
            "stage": stage,
            "status": "completed",
            "not_mock": True,
            "source_type": "live_probe",
            "blockers": [],
            "warnings": [],
        }

    monkeypatch.setattr(
        operator_readonly_sweep,
        "settings",
        SimpleNamespace(provider_mode=operator_readonly_sweep.LOCAL_READONLY_MODE),
    )
    monkeypatch.setattr(operator_readonly_sweep, "_profile_state", lambda: _profile_state())
    monkeypatch.setattr(
        operator_readonly_sweep,
        "_selected_actions",
        lambda _state: [
            {
                "action_id": "cisco.ssh-readonly-probe",
                "label": "Cisco SSH read-only show commands",
                "optional": False,
                "optional_reason": "",
                "stage": "network",
                "status": "selected",
                "skip_reason": "",
            },
            {
                "action_id": "netapp.live-state",
                "label": "NetApp live state",
                "optional": False,
                "optional_reason": "",
                "stage": "storage",
                "status": "selected",
                "skip_reason": "",
            },
            {
                "action_id": "vcenter-netapp.readiness",
                "label": "vCenter NetApp readiness",
                "optional": False,
                "optional_reason": "",
                "stage": "virtualization",
                "status": "skipped",
                "skip_reason": "vCenter is out of scope for the active lab profile.",
            },
        ],
    )
    monkeypatch.setattr(operator_readonly_sweep, "_run_action", fake_run_action)
    monkeypatch.setattr(operator_readonly_sweep, "_write_report", fake_write_report)
    monkeypatch.setattr(operator_readonly_sweep, "_redaction_values", lambda: [])

    exit_code = operator_readonly_sweep.main()

    assert exit_code == 0
    assert [item["quality_gate"]["status"] for item in writes] == ["running", "running", "running", "completed"]
    assert writes[0]["quality_gate"]["remaining_count"] == 2
    assert writes[0]["quality_gate"]["completed_actions"] == []
    assert writes[1]["quality_gate"]["completed_actions"] == ["cisco.ssh-readonly-probe"]
    assert writes[2]["quality_gate"]["completed_actions"] == ["cisco.ssh-readonly-probe", "netapp.live-state"]
    assert "partial report is current" in writes[1]["quality_gate"]["message"]
    assert writes[-1]["finished_at"]


def _profile_state(*, netapp_enabled: bool = True, storage_protocol: str = "nfs") -> dict:
    return {
        "active_profile": {
            "features": {
                "netapp_enabled": netapp_enabled,
                "storage_protocol": storage_protocol,
                "vcenter_enabled": False,
            }
        }
    }
