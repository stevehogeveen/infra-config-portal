from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services.lab_profiles import create_lab_profile
from app.services import workflow_registry
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
        "cisco.ssh-readonly-probe",
        "cisco.current-intent-diff",
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
        "raid.factory-reset-preview",
        "raid.factory-reset-apply",
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
        "esxi.vm-teardown-preview",
        "esxi.vm-teardown-apply",
        "esxi.vm-teardown-validate",
        "esxi.iscsi-datastore-preview",
        "esxi.iscsi-datastore-validate",
        "netapp.serial-console-discovery",
        "netapp.console-autodiscovery",
        "netapp.console-read-state",
        "netapp.nfs-vcenter-readiness",
        "netapp.nfs-setup-preview",
        "netapp.nfs-setup-apply",
        "netapp.nfs-setup-validate",
        "netapp.iscsi-setup-preview",
        "netapp.iscsi-setup-apply",
        "netapp.iscsi-setup-validate",
        "netapp.setup-preview",
        "netapp.ontap-upgrade-inventory",
        "netapp.component-firmware-inventory",
        "vcenter-netapp.readiness",
        "vcenter-netapp.datastore-plan",
        "vcenter-netapp.datastore-apply-placeholder",
        "vcenter.install-apply",
        "vcenter.attach-esxi-preview",
        "vcenter.attach-esxi-apply",
        "vcenter.post-attach-validation",
        "provider-smoke.real-lab",
        "operator-readonly-sweep.real-lab",
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
    assert actions["raid.factory-reset-apply"]["mode"] == "destructive"
    assert actions["raid.reset-commit"]["mode"] == "destructive"
    assert actions["ilo.reset-server"]["mode"] == "destructive"
    assert actions["esxi.rebuild-install"]["mode"] == "destructive"
    assert "HPE_RAID_ALLOW_FACTORY_RESET=true" in actions["raid.factory-reset-apply"]["required_gates"]
    assert "LAB_ALLOW_POWER_ACTIONS=true" in actions["raid.reset-commit"]["required_gates"]


def test_vm_teardown_action_is_bound_to_configured_name_and_esxi_target(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VM_TEARDOWN_VM_NAME", "single-server-smoke-vm")
    monkeypatch.setattr(
        workflow_registry,
        "settings",
        SimpleNamespace(esxi_test_host="10.10.8.203"),
    )

    actions = {
        action["action_id"]: action
        for action in workflow_registry.list_workflow_actions()
    }
    preview = actions["esxi.vm-teardown-preview"]
    apply = actions["esxi.vm-teardown-apply"]
    validate = actions["esxi.vm-teardown-validate"]

    assert preview["mode"] == "read_only"
    assert apply["mode"] == "destructive"
    assert validate["mode"] == "read_only"
    assert apply["required_confirmations"] == ["REMOVE ONE ESXI VM"]
    assert "VM_TEARDOWN_CONFIRM_VM_NAME=single-server-smoke-vm" in apply[
        "required_gates"
    ]
    assert "VM_TEARDOWN_CONFIRM_ESXI_TARGET=10.10.8.203" in apply[
        "required_gates"
    ]
    assert preview["ui_run_supported"] is True
    assert apply["guarded_run_supported"] is True
    assert validate["ui_run_supported"] is True


def test_action_reports_are_linked_to_actions_and_traces() -> None:
    action = get_workflow_action("netapp.console-read-state")

    assert "artifacts/codex-runs/netapp-console-state-report.md" in action["reports"]
    assert action["last_run_trace"]["action_id"] == "netapp.console-read-state"
    assert set(action["last_run_trace"]["report_artifacts"]).issubset(set(action["reports"]))


def test_workflow_registry_report_artifacts_exclude_run_traces() -> None:
    reports = workflow_registry._workflow_report_artifacts(
        {
            "report_artifacts": [
                "artifacts/codex-runs/esxi-management-readiness-report.md",
                "artifacts/codex-runs/workflow-action-runs/trace.json",
                "artifacts/codex-runs/esxi-management-readiness-redacted.json",
            ]
        }
    )

    assert reports == [
        "artifacts/codex-runs/esxi-management-readiness-report.md",
        "artifacts/codex-runs/esxi-management-readiness-redacted.json",
    ]


def test_workflow_registry_dedupes_seeds_by_action_id_preserving_first() -> None:
    first = workflow_registry.WorkflowActionSeed(
        action_id="example.action",
        label="First",
        stage="reports",
        provider="reports",
        category="report",
        mode="report_only",
        description="First action",
        source_type="manual_guidance",
    )
    duplicate = workflow_registry.WorkflowActionSeed(
        action_id="example.action",
        label="Duplicate",
        stage="reports",
        provider="reports",
        category="report",
        mode="report_only",
        description="Duplicate action",
        source_type="manual_guidance",
    )
    second = workflow_registry.WorkflowActionSeed(
        action_id="example.second",
        label="Second",
        stage="reports",
        provider="reports",
        category="report",
        mode="report_only",
        description="Second action",
        source_type="manual_guidance",
    )

    assert workflow_registry._dedupe_seeds([first, duplicate, second, first]) == [first, second]


def test_workflow_registry_existing_reports_skips_paths_that_error(monkeypatch) -> None:
    class ReportPath:
        def __init__(self, *, exists: bool = True, exists_error: Exception | None = None) -> None:
            self._exists = exists
            self._exists_error = exists_error

        def exists(self) -> bool:
            if self._exists_error:
                raise self._exists_error
            return self._exists

    class RepoRoot:
        def __truediv__(self, report: str) -> ReportPath:
            return reports[report]

    reports = {
        "artifacts/ready.md": ReportPath(),
        "artifacts/locked.md": ReportPath(exists_error=OSError("locked")),
        "artifacts/missing.md": ReportPath(exists=False),
    }
    monkeypatch.setattr(workflow_registry, "REPO_ROOT", RepoRoot())

    assert workflow_registry._existing_reports(list(reports)) == ["artifacts/ready.md"]


def test_workflow_registry_latest_report_skips_files_that_disappear(monkeypatch) -> None:
    class ReportPath:
        def __init__(self, *, mtime: float, stat_error: Exception | None = None) -> None:
            self._mtime = mtime
            self._stat_error = stat_error

        def stat(self) -> SimpleNamespace:
            if self._stat_error:
                raise self._stat_error
            return SimpleNamespace(st_mtime=self._mtime)

    class RepoRoot:
        def __truediv__(self, report: str) -> ReportPath:
            return reports[report]

    reports = {
        "artifacts/older.md": ReportPath(mtime=1),
        "artifacts/disappeared.md": ReportPath(mtime=999, stat_error=FileNotFoundError("gone")),
        "artifacts/newer.md": ReportPath(mtime=2),
    }
    monkeypatch.setattr(workflow_registry, "REPO_ROOT", RepoRoot())

    assert workflow_registry._latest_report(list(reports)) == "artifacts/newer.md"


def test_workflow_registry_run_trace_self_heals_disappearing_last_report(monkeypatch) -> None:
    class ReportPath:
        def stat(self) -> SimpleNamespace:
            raise FileNotFoundError("gone")

    class RepoRoot:
        def __truediv__(self, report: str) -> ReportPath:
            return ReportPath()

    monkeypatch.setattr(workflow_registry, "REPO_ROOT", RepoRoot())
    seed = workflow_registry.WorkflowActionSeed(
        action_id="example.action",
        label="Example",
        stage="reports",
        provider="reports",
        category="report",
        mode="report_only",
        description="Example action",
        source_type="manual_guidance",
    )

    trace = workflow_registry._run_trace(
        seed,
        "artifacts/disappeared.md",
        blockers=[],
        availability="available",
    )

    assert trace["status"] == "not_checked"
    assert trace["source_type"] == "not_checked"
    assert trace["finished_at"] is None
    assert trace["report_artifacts"] == []


def test_workflow_registry_issue_link_keeps_scalar_evidence_artifact_whole() -> None:
    issue = {
        "source_report": None,
        "evidence_artifacts": "artifacts/codex-runs/netapp-console-state-report.md",
    }

    link = workflow_registry.find_workflow_action_for_issue(issue)

    assert link["source_action_id"] == "netapp.console-read-state"
    assert link["source_stage_id"] == "netapp"


def test_workflow_registry_stage_report_count_skips_unreadable_reports(monkeypatch) -> None:
    class ReportPath:
        def __init__(self, *, exists: bool = True, exists_error: Exception | None = None) -> None:
            self._exists = exists
            self._exists_error = exists_error

        def exists(self) -> bool:
            if self._exists_error:
                raise self._exists_error
            return self._exists

    class RepoRoot:
        def __truediv__(self, report: str) -> ReportPath:
            return reports[report]

    reports = {
        "artifacts/ready.md": ReportPath(),
        "artifacts/locked.md": ReportPath(exists_error=OSError("locked")),
    }
    monkeypatch.setattr(workflow_registry, "REPO_ROOT", RepoRoot())
    stage = workflow_registry.WorkflowStageSeed(
        stage_id="reports",
        label="Reports",
        order=1,
        current_state="Reports available.",
        desired_state="Reports available.",
        reports=tuple(reports),
    )

    payload = workflow_registry._stage_read(stage, actions=[])

    assert payload["report_count"] == 1


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
    assert actions["netapp.setup-preview"]["ui_run_supported"] is False
    assert any("active lab profile" in blocker for blocker in actions["netapp.setup-preview"]["ui_run_blockers"])
    assert actions["vcenter-netapp.readiness"]["current_availability"] == "not_in_scope"
    assert actions["vcenter-netapp.readiness"]["ui_run_supported"] is False
    assert any("active lab profile" in blocker for blocker in actions["vcenter-netapp.readiness"]["ui_run_blockers"])
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
    assert actions["vcenter.attach-esxi-preview"]["ui_run_supported"] is False
    assert actions["vcenter.attach-esxi-apply"]["mode"] == "write"
    assert actions["vcenter.attach-esxi-apply"]["ui_run_supported"] is False
    assert actions["vcenter.post-attach-validation"]["ui_run_supported"] is False


def test_vcenter_read_actions_are_ui_runnable_when_profile_enables_vcenter(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "Shared vCenter Lab",
            "features": {"netapp_enabled": True, "vcenter_enabled": True},
            "subnet_cidr": "192.168.1.0/24",
            "address_plan": {"subnet": "192.168.1.0/24"},
        }
    )

    actions = {action["action_id"]: action for action in list_workflow_actions()}

    assert actions["vcenter.attach-esxi-preview"]["current_availability"] == "available"
    assert actions["vcenter.attach-esxi-preview"]["ui_run_supported"] is True
    assert actions["vcenter.post-attach-validation"]["current_availability"] == "available"
    assert actions["vcenter.post-attach-validation"]["ui_run_supported"] is True


def test_workflow_registry_keeps_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id, _category):
            return " policy blocker "

    monkeypatch.setattr(workflow_registry, "current_lab_action_policy", lambda: ScalarPolicy())
    seed = workflow_registry.WorkflowActionSeed(
        action_id="example.apply",
        label="Example Apply",
        stage="raid",
        provider="hpe-ilo",
        category="apply",
        mode="write",
        description="Example write action",
        source_type="live",
        policy_action_id="example.apply",
        policy_category=workflow_registry.ActionCategory.STORAGE_CONFIG,
    )

    blockers = workflow_registry._blockers_for_seed(seed)

    assert blockers == ["policy blocker"]
    assert "p" not in blockers


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
