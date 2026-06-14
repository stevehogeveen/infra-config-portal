from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.lab_profiles import create_lab_profile
from app.services.workflow_registry import (
    get_workflow_action,
    list_workflow_actions,
    list_workflow_stages,
)


def test_registry_contains_expected_stage_ids_in_stable_order() -> None:
    stages = list_workflow_stages()

    assert [stage["stage_id"] for stage in stages] == [
        "lab-profile",
        "firmware",
        "cisco",
        "ilo",
        "raid",
        "esxi",
        "netapp",
        "vcenter",
        "build-verification",
        "reports",
    ]
    assert [stage["order"] for stage in stages] == sorted(stage["order"] for stage in stages)


def test_registry_contains_expected_provider_actions() -> None:
    action_ids = {action["action_id"] for action in list_workflow_actions()}

    assert {
        "lab-profile.view-active",
        "lab-profile.validate-ip-profile",
        "firmware.inventory",
        "firmware.compliance-check",
        "firmware.waiver-check",
        "cisco.discover-console",
        "cisco.reclaim-console",
        "cisco.privilege-check",
        "cisco.apply-bootstrap",
        "cisco.validate-ssh-scp",
        "cisco.firmware-inventory",
        "ilo.reachability",
        "ilo.auth",
        "ilo.inventory",
        "ilo.baseline-preview",
        "ilo.firmware-inventory",
        "ilo.virtual-media-insert",
        "ilo.one-time-boot",
        "ilo.reset-server",
        "raid.discovery",
        "raid.plan",
        "raid.debug",
        "raid.apply",
        "raid.pending-check",
        "raid.reset-commit",
        "raid.validate",
        "esxi.readiness",
        "esxi.iso-media-check",
        "esxi.virtual-media-insert",
        "esxi.one-time-boot",
        "esxi.installer-boot-detection",
        "esxi.management-readiness",
        "esxi.vm-deploy-preview",
        "esxi.vm-deploy-apply",
        "esxi.vm-deploy-validate",
        "netapp.serial-console-discovery",
        "netapp.console-autodiscovery",
        "netapp.console-read-state",
        "netapp.nfs-vcenter-readiness",
        "netapp.nfs-setup-preview",
        "netapp.nfs-setup-apply",
        "netapp.nfs-setup-validate",
        "netapp.setup-preview",
        "netapp.ontap-upgrade-inventory",
        "netapp.component-firmware-inventory",
        "vcenter-netapp.readiness",
        "vcenter-netapp.datastore-plan",
        "vcenter-netapp.datastore-apply-placeholder",
        "vcenter.install-apply",
        "build-verification.live-status",
        "build-verification.run-full",
        "lab-validation.summary",
        "full-lab.validation",
        "full-lab.build-plan",
        "full-lab.repair",
        "full-lab.handoff-report",
        "build-verification.toolchain-check",
        "reports.issue-center",
    }.issubset(action_ids)


def test_destructive_actions_are_marked_correctly() -> None:
    actions = {action["action_id"]: action for action in list_workflow_actions()}

    assert actions["raid.apply"]["mode"] == "destructive"
    assert actions["raid.reset-commit"]["mode"] == "destructive"
    assert actions["ilo.reset-server"]["mode"] == "destructive"
    assert actions["esxi.rebuild-install"]["mode"] == "destructive"
    assert "LAB_ALLOW_POWER_ACTIONS=true" in actions["raid.reset-commit"]["required_gates"]


def test_action_reports_are_linked_to_actions_and_traces() -> None:
    action = get_workflow_action("netapp.console-read-state")

    assert "artifacts/codex-runs/netapp-console-state-report.md" in action["reports"]
    assert action["last_run_trace"]["action_id"] == "netapp.console-read-state"
    assert set(action["last_run_trace"]["report_artifacts"]).issubset(set(action["reports"]))


def test_registry_does_not_treat_mock_or_test_state_as_real_current_state() -> None:
    actions = list_workflow_actions()

    assert actions
    for action in actions:
        trace = action["last_run_trace"]
        assert trace["source_type"] in {"historical_artifact", "not_checked", "live_probe"}
        assert trace["source_type"] not in {"mock", "test", "test_fixture"}
        assert trace["freshness"] in {"historical", "not_checked", "current"}
        if trace["source_type"] == "live_probe":
            assert trace["freshness"] == "current"


def test_safe_read_only_registry_actions_are_ui_runnable() -> None:
    actions = {action["action_id"]: action for action in list_workflow_actions()}

    assert actions["build-verification.run-full"]["ui_run_supported"] is True
    assert actions["build-verification.run-full"]["current_availability"] == "available"
    assert actions["build-verification.run-full"]["run_endpoint"].endswith(
        "/workflows/actions/build-verification.run-full/run"
    )
    assert actions["full-lab.validation"]["ui_run_supported"] is True
    assert actions["full-lab.build-plan"]["ui_run_supported"] is True
    assert actions["full-lab.repair"]["ui_run_supported"] is True
    assert actions["full-lab.handoff-report"]["ui_run_supported"] is True
    assert actions["reports.summary"]["ui_run_supported"] is True
    assert actions["ilo.baseline-preview"]["ui_run_supported"] is True
    assert actions["ilo.baseline-preview"]["api_endpoint"] == "/api/v1/providers/hpe-ilo/baseline-preview"
    assert actions["netapp.component-firmware-inventory"]["ui_run_supported"] is True
    assert actions["netapp.component-firmware-inventory"]["current_availability"] == "available"


def test_compact_profile_marks_netapp_registry_actions_not_in_scope(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "Compact Edge Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )

    actions = {action["action_id"]: action for action in list_workflow_actions()}
    stages = {stage["stage_id"]: stage for stage in list_workflow_stages()}

    assert actions["netapp.setup-preview"]["current_availability"] == "not_in_scope"
    assert "active lab profile" in actions["netapp.setup-preview"]["not_in_scope_reason"]
    assert actions["vcenter-netapp.readiness"]["current_availability"] == "not_in_scope"
    assert stages["netapp"]["current_state"] == "not_in_scope"


def test_write_destructive_and_unallowlisted_actions_are_not_ui_runnable() -> None:
    actions = {action["action_id"]: action for action in list_workflow_actions()}

    assert actions["raid.apply"]["ui_run_supported"] is False
    assert any("guarded workflow" in blocker for blocker in actions["raid.apply"]["ui_run_blockers"])
    assert actions["ilo.firmware-inventory"]["ui_run_supported"] is True
    assert actions["ilo.virtual-media-insert"]["ui_run_supported"] is False
    assert actions["build-verification.run-scoped"]["ui_run_supported"] is False
    assert actions["vcenter-netapp.datastore-apply-placeholder"]["mode"] == "write"
    assert actions["vcenter-netapp.datastore-apply-placeholder"]["ui_run_supported"] is False
    assert actions["vcenter.install-apply"]["mode"] == "write"
    assert actions["vcenter.install-apply"]["ui_run_supported"] is False


def test_workflow_registry_api_endpoints(client: TestClient) -> None:
    stages_response = client.get("/api/v1/workflows/stages")
    actions_response = client.get("/api/v1/workflows/actions")
    action_response = client.get("/api/v1/workflows/actions/raid.apply")
    stage_response = client.get("/api/v1/workflows/stages/raid")

    assert stages_response.status_code == 200
    assert actions_response.status_code == 200
    assert action_response.status_code == 200
    assert stage_response.status_code == 200
    assert action_response.json()["mode"] == "destructive"
    assert any(action["action_id"] == "raid.apply" for action in stage_response.json()["actions"])


def test_unknown_workflow_registry_items_return_404(client: TestClient) -> None:
    assert client.get("/api/v1/workflows/actions/not-real").status_code == 404
    assert client.get("/api/v1/workflows/stages/not-real").status_code == 404


def test_report_center_issues_include_workflow_link_fields(client: TestClient) -> None:
    response = client.get("/api/v1/reports/issues")

    assert response.status_code == 200
    payload = response.json()
    assert payload["issues"]
    issue = payload["issues"][0]
    assert "source_stage_id" in issue
    assert "source_stage_label" in issue
    assert "source_action_id" in issue
    assert "source_action_label" in issue
    assert "source_action_link" in issue
