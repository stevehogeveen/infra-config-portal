from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowRunStatus
from app.models import Request, WorkflowRun


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_build_verification_endpoint_returns_status(client: TestClient) -> None:
    response = client.get("/api/v1/lab/build-verification")

    assert response.status_code == 200
    assert response.json()["provider_id"] == "build-verification"
    assert "status" in response.json()


def test_control_action_catalog_exposes_device_actions_without_direct_runs(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/control/actions")

    assert response.status_code == 200
    payload = response.json()
    action_ids = {action["id"] for action in payload["actions"]}
    section_ids = {section["id"] for section in payload["sections"]}

    assert {
        "lab-profile",
        "cisco",
        "ilo",
        "raid",
        "esxi",
        "netapp",
        "firmware-upgrade",
        "verification",
        "reports",
    }.issubset(section_ids)
    assert {
        "cisco.discover-console",
        "cisco.reclaim-console",
        "ilo.inventory",
        "raid.apply",
        "esxi.rebuild-install",
        "netapp.setup-preview",
        "firmware.upgrade-apply-placeholder",
        "build-verification.run-full",
    }.issubset(action_ids)

    cisco = next(action for action in payload["actions"] if action["id"] == "cisco.discover-console")
    assert cisco["classification"] == "read-only"
    assert cisco["plan_endpoint"] == "/api/v1/control/actions/cisco.discover-console/plan"
    assert cisco["run_endpoint"] == "/api/v1/control/actions/cisco.discover-console/run"
    assert cisco["direct_run_supported"] is False

    upgrade = next(
        action
        for action in payload["actions"]
        if action["id"] == "firmware.upgrade-apply-placeholder"
    )
    assert upgrade["classification"] == "upgrade"
    assert "LAB_ALLOW_FIRMWARE_UPDATES=true" in upgrade["required_flags"]
    assert upgrade["availability"] == "blocked"
    assert "executed" not in upgrade

    lab_profile = payload["lab_profile"]
    assert lab_profile["known_lab_profile"]["ilo"] == "192.168.1.201"
    assert lab_profile["known_lab_profile"]["server_embedded_nic"] == "192.168.1.202"
    assert lab_profile["known_lab_profile"]["esxi_management"] == "192.168.1.203"
    assert lab_profile["known_lab_profile"]["cisco_management"] == "192.168.1.204"
    assert lab_profile["known_lab_profile"]["ansible_control_host"] == "192.168.1.205"
    assert "ILO_TEST_HOST=192.168.1.201" in lab_profile["env_update_command"]
    assert "PASSWORD" not in lab_profile["env_update_command"].upper()


def test_control_action_plan_and_run_are_safe_placeholders(client: TestClient) -> None:
    planned = client.post("/api/v1/control/actions/ilo.inventory/plan")

    assert planned.status_code == 200
    plan_payload = planned.json()
    assert plan_payload["action"]["id"] == "ilo.inventory"
    assert plan_payload["direct_run_enabled"] is False
    assert plan_payload["plan_steps"][-1]["status"] == "manual_command_required"

    run = client.post("/api/v1/control/actions/ilo.inventory/run")

    assert run.status_code == 200
    run_payload = run.json()
    assert run_payload["action"]["id"] == "ilo.inventory"
    assert run_payload["executed"] is False
    assert "No provider call" in run_payload["message"]
    assert any("Direct Control Center run is not implemented" in item for item in run_payload["blockers"])


def test_control_action_unknown_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/control/actions/not-a-real-action/plan")

    assert response.status_code == 404


def test_provider_mode_settings_exposes_simulation_and_lab_options(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("PROVIDER_MODE_SETTINGS_STORE", str(tmp_path / "provider-mode.json"))
    monkeypatch.setenv("APP_MODE_ENV_FILE", str(tmp_path / "app-mode.env"))

    response = client.get("/api/v1/settings/provider-mode")

    assert response.status_code == 200
    payload = response.json()
    labels = {option["mode"]: option["label"] for option in payload["options"]}
    assert labels["mock"] == "Simulation"
    assert labels["local-readonly"] == "Local Read-only Lab"
    assert labels["local-lab-readwrite"] == "Local Lab Read/write"
    assert payload["desired_mode"] == payload["current_mode"]
    assert payload["pending_restart"] is False
    assert payload["mode_env_path"].endswith("app-mode.env")


def test_provider_mode_settings_save_writes_ignored_local_restart_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "provider-mode.json"
    env_path = tmp_path / "app-mode.env"
    monkeypatch.setenv("PROVIDER_MODE_SETTINGS_STORE", str(store_path))
    monkeypatch.setenv("APP_MODE_ENV_FILE", str(env_path))

    current = client.get("/api/v1/settings/provider-mode").json()["current_mode"]
    desired = "local-readonly" if current != "local-readonly" else "local-lab-readwrite"
    response = client.put(
        "/api/v1/settings/provider-mode",
        json={"desired_mode": desired},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["desired_mode"] == desired
    assert payload["current_mode"] == current
    assert payload["pending_restart"] is (desired != current)
    assert payload["restart_command"]
    assert env_path.read_text(encoding="utf-8") == f"PROVIDER_MODE={desired}\n"

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert stored["desired_mode"] == desired
    assert stored["mock_default_preserved"] is True
    assert "password" not in stored


def test_control_action_catalog_includes_first_time_access_config(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONTROL_ACCESS_STORE", str(tmp_path / "control-access.json"))
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    response = client.get("/api/v1/control/actions")

    assert response.status_code == 200
    payload = response.json()
    cisco = next(section for section in payload["sections"] if section["id"] == "cisco")
    access_config = cisco["access_config"]
    assert access_config["title"] == "Cisco first-time access"
    assert access_config["desired_address_label"] == "Cisco management IP"
    assert access_config["desired_management_ip"] == "192.168.1.204"
    assert access_config["first_time_configuring"] is True
    assert any("Original DHCP/current-access IP" in item for item in access_config["blockers"])
    assert any(item["label"] == "Management IP" for item in access_config["editable_fields"])


def test_control_access_config_saves_original_dhcp_and_presence_only_credentials(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONTROL_ACCESS_STORE", str(tmp_path / "control-access.json"))
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    saved = client.put(
        "/api/v1/control/access/ilo",
        json={
            "first_time_configuring": True,
            "original_dhcp_ip": "192.0.2.55",
            "username_reference": "local-admin",
            "password_configured": True,
            "password_reference_label": "local env reference",
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["section_id"] == "ilo"
    assert payload["original_dhcp_ip"] == "192.0.2.55"
    assert payload["username_reference"] == "local-admin"
    assert payload["password_configured"] is True
    assert payload["password_reference_label"] == "local env reference"
    assert payload["blockers"] == []

    catalog = client.get("/api/v1/control/actions").json()
    ilo = next(section for section in catalog["sections"] if section["id"] == "ilo")
    assert ilo["access_config"]["original_dhcp_ip"] == "192.0.2.55"
    assert ilo["access_config"]["password_configured"] is True


def test_control_access_config_rejects_secret_shaped_values(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONTROL_ACCESS_STORE", str(tmp_path / "control-access.json"))

    response = client.put(
        "/api/v1/control/access/cisco",
        json={
            "first_time_configuring": True,
            "original_dhcp_ip": "192.0.2.10",
            "username_reference": "password=bad",
            "password_configured": True,
        },
    )

    assert response.status_code == 422


def test_control_action_catalog_blocks_netapp_when_lab_profile_disables_it(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Small Subnet Lab",
            "global_settings": {"subnet_prefix": 25},
            "address_plan": {"subnet": "198.51.100.0/25"},
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/control/actions")

    assert response.status_code == 200
    payload = response.json()
    setup_preview = next(
        action for action in payload["actions"] if action["id"] == "netapp.setup-preview"
    )
    assert setup_preview["availability"] == "blocked"
    assert "NetApp capabilities require a /24" in setup_preview["blocker"]
    assert payload["lab_profile"]["global_settings"]["netapp_enabled"] is False


def test_lab_profile_api_saves_selects_and_versions_profiles(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    empty = client.get("/api/v1/lab/profiles")
    assert empty.status_code == 200
    assert empty.json()["active_profile"]["id"] == "runtime"
    assert empty.json()["profiles"] == []

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Bench Lab A",
            "description": "Primary saved lab address plan.",
            "address_plan": {
                "subnet": "192.0.2.0/24",
                "ilo": "192.0.2.10",
                "server_embedded_nic": "192.0.2.11",
                "esxi_management": "192.0.2.12",
                "cisco_management": "192.0.2.13",
                "ansible_control_host": "192.0.2.14",
                "netapp_controller_a_sp": "192.0.2.15",
                "netapp_controller_b_sp": "192.0.2.16",
                "netapp_cluster_mgmt": "192.0.2.17",
                "netapp_node_a_mgmt": "192.0.2.18",
                "netapp_node_b_mgmt": "192.0.2.19",
                "netapp_svm_mgmt": "192.0.2.20",
                "netapp_iscsi_lifs": ["192.0.2.21", "192.0.2.22"],
            },
        },
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]
    assert created.json()["active"] is True
    assert created.json()["version"] == 1

    updated = client.put(
        f"/api/v1/lab/profiles/{profile_id}",
        json={
            "name": "Bench Lab A",
            "description": "Updated saved lab address plan.",
            "address_plan": {
                "subnet": "198.51.100.0/24",
                "ilo": "198.51.100.10",
                "server_embedded_nic": "198.51.100.11",
                "esxi_management": "198.51.100.12",
                "cisco_management": "198.51.100.13",
                "ansible_control_host": "198.51.100.14",
                "netapp_iscsi_lifs": "198.51.100.21,198.51.100.22",
            },
        },
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["history"][0]["version"] == 1
    assert updated.json()["address_plan"]["netapp_iscsi_lifs"] == [
        "198.51.100.21",
        "198.51.100.22",
    ]

    runtime = client.post("/api/v1/lab/profiles/runtime/activate")
    assert runtime.status_code == 200
    assert runtime.json()["active_profile"]["id"] == "runtime"

    activated = client.post(f"/api/v1/lab/profiles/{profile_id}/activate")
    assert activated.status_code == 200
    assert activated.json()["active_profile"]["id"] == profile_id


def test_lab_profile_subnet_options_include_netapp_capability_boundary(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    response = client.get("/api/v1/lab/profiles")

    assert response.status_code == 200
    options = {item["prefix"]: item for item in response.json()["subnet_options"]}
    assert set(options) == {23, 24, 25, 26, 27, 28, 29}
    assert options[24]["netapp_supported"] is True
    assert options[25]["netapp_supported"] is False
    assert "NetApp capabilities require a /24" in options[25]["netapp_disabled_reason"]


def test_lab_profile_uses_lab_builder_schema_for_24_when_addresses_are_blank(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    response = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Schema Lab",
            "global_settings": {"subnet_prefix": 24},
            "address_plan": {"subnet": "192.0.2.0/24"},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["global_settings"]["gateway"] == "192.0.2.1"
    assert payload["global_settings"]["netapp_enabled"] is True
    assert payload["address_plan"]["subnet"] == "192.0.2.0/24"
    assert payload["address_plan"]["cisco_management"] == "192.0.2.2"
    assert payload["address_plan"]["ilo"] == "192.0.2.200"
    assert payload["address_plan"]["esxi_management"] == "192.0.2.202"
    assert payload["address_plan"]["netapp_controller_a_sp"] == "192.0.2.13"
    assert payload["address_plan"]["netapp_cluster_mgmt"] == "192.0.2.45"
    assert payload["address_plan"]["netapp_svm_mgmt"] == "192.0.2.48"
    assert payload["address_plan"]["netapp_iscsi_lifs"] == [
        "192.0.2.49",
        "192.0.2.50",
        "192.0.2.51",
        "192.0.2.52",
    ]


def test_lab_profile_25_and_smaller_subnets_clear_netapp_capabilities(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    response = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Small Subnet Lab",
            "global_settings": {
                "subnet_prefix": 25,
                "gateway": "198.51.100.1",
                "dns_servers": ["198.51.100.2"],
            },
            "address_plan": {
                "subnet": "198.51.100.0/24",
                "netapp_controller_a_sp": "198.51.100.13",
                "netapp_cluster_mgmt": "198.51.100.45",
                "netapp_iscsi_lifs": ["198.51.100.49"],
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["address_plan"]["subnet"] == "198.51.100.0/25"
    assert payload["global_settings"]["subnet_prefix"] == 25
    assert payload["global_settings"]["gateway"] == "198.51.100.1"
    assert payload["global_settings"]["dns_servers"] == ["198.51.100.2"]
    assert payload["global_settings"]["netapp_enabled"] is False
    assert "NetApp capabilities require a /24" in payload["global_settings"]["netapp_disabled_reason"]
    assert payload["address_plan"]["netapp_controller_a_sp"] is None
    assert payload["address_plan"]["netapp_cluster_mgmt"] is None
    assert payload["address_plan"]["netapp_iscsi_lifs"] == []


def test_lab_profile_api_rejects_secret_shaped_values(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    response = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Lab with password=bad",
            "address_plan": {"subnet": "192.0.2.0/24"},
        },
    )

    assert response.status_code == 422


def test_vm_deploy_api_flow(client: TestClient, vm_payload: dict) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "needs_approval"

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]
    assert planned.json()["status"] == "planned"
    assert planned.json()["plan_json"]["dry_run"] is True
    assert planned.json()["plan_json"]["mock_only"] is True
    assert planned.json()["plan_json"]["review_before_execute"]["required"] is True
    assert [
        event["stage"]
        for event in planned.json()["plan_json"]["stage_events"]
    ] == [
        "DISCOVER",
        "VALIDATE",
        "PLAN",
        "REVIEW",
        "EXECUTE",
        "COMPLETE",
        "BLOCKED",
    ]

    workflow_runs = client.get("/api/v1/workflow-runs")
    assert workflow_runs.status_code == 200
    assert workflow_runs.json()[0]["id"] == workflow_run_id

    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 200
    assert executed.json()["status"] == "completed"
    assert executed.json()["result_json"]["mock"] is True
    assert executed.json()["result_json"]["stage_events"][0]["stage"] == "DISCOVER"
    assert executed.json()["result_json"]["stage_events"][0]["status"] == "completed"

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "completed"

    run_detail = client.get(f"/api/v1/workflow-runs/{workflow_run_id}")
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "completed"

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.completed" in event_types


def test_artifact_listing_returns_mock_report_and_placeholders(
    client: TestClient,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    assert client.post(f"/api/v1/requests/{request_id}/submit").status_code == 200
    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200
    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]
    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 200

    request_artifacts = client.get(f"/api/v1/requests/{request_id}/artifacts")
    assert request_artifacts.status_code == 200
    request_payload = request_artifacts.json()
    request_kinds = {artifact["kind"] for artifact in request_payload}
    assert {
        "audit_history",
        "dry_run_plan",
        "completion_report",
        "run_history",
        "debug_bundle",
        "export",
    }.issubset(request_kinds)
    assert all(artifact["mock_only"] is True for artifact in request_payload)
    assert all(artifact["downloadable"] is False for artifact in request_payload)
    assert all(artifact["download_url"] is None for artifact in request_payload)

    run_artifacts = client.get(f"/api/v1/workflow-runs/{workflow_run_id}/artifacts")
    assert run_artifacts.status_code == 200
    run_payload = run_artifacts.json()
    report = next(artifact for artifact in run_payload if artifact["kind"] == "completion_report")
    debug_bundle = next(artifact for artifact in run_payload if artifact["kind"] == "debug_bundle")

    assert report["status"] == "available"
    assert report["metadata"]["mock_task_id"].startswith("mock-task-")
    assert report["metadata"]["mock_vm_id"].startswith("vm-")
    assert debug_bundle["status"] == "placeholder"
    assert debug_bundle["metadata"]["generated"] is False


def test_cancel_draft_request_api_flow(client: TestClient, vm_payload: dict) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    cancelled = client.post(f"/api/v1/requests/{request_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 409

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.cancelled" in event_types


def test_reject_request_api_flow(client: TestClient, vm_payload: dict) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "needs_approval"

    rejected = client.post(
        f"/api/v1/requests/{request_id}/reject",
        json={"approver": "change.manager", "notes": "Rejected in API test"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Too late"},
    )
    assert approved.status_code == 409

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.rejected" in event_types


def test_update_request_api_allows_draft_patch_and_records_audit(
    client: TestClient,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"notes": "Updated through PATCH", "cpu": 4},
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["notes"] == "Updated through PATCH"
    assert updated.json()["vm_deploy"]["cpu"] == 4

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    matching_events = [
        event
        for event in audit_events.json()
        if event["event_type"] == "request.updated"
    ]
    assert matching_events[0]["data_json"]["changed_fields"] == ["notes", "vm.cpu"]
    assert matching_events[0]["data_json"]["reset_to_draft"] is False


def test_update_request_api_resets_planned_execution_edit_and_cancels_plan(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    workflow_run_id = planned.json()["id"]

    updated = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"memory_gb": vm_payload["memory_gb"] + 4},
    )

    assert updated.status_code == 200
    assert updated.json()["status"] == "draft"
    assert updated.json()["vm_deploy"]["memory_gb"] == vm_payload["memory_gb"] + 4

    workflow_run = db_session.get(WorkflowRun, workflow_run_id)
    assert workflow_run is not None
    assert workflow_run.status == WorkflowRunStatus.CANCELLED.value
    assert workflow_run.plan_json["invalidated_by_request_edit"] is True

    executed = client.post(f"/api/v1/requests/{request_id}/execute")
    assert executed.status_code == 409
    assert "expected planned" in executed.json()["detail"]

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    matching_events = [
        event
        for event in audit_events.json()
        if event["event_type"] == "request.updated"
    ]
    assert matching_events[0]["data_json"]["reset_to_draft"] is True
    assert matching_events[0]["data_json"]["invalidated_workflow_run_ids"] == [
        workflow_run_id
    ]


def test_update_request_api_rejects_locked_request(
    client: TestClient,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    cancelled = client.post(f"/api/v1/requests/{request_id}/cancel")
    assert cancelled.status_code == 200

    updated = client.patch(
        f"/api/v1/requests/{request_id}",
        json={"notes": "Rejected because cancelled is locked."},
    )

    assert updated.status_code == 409
    assert "locked" in updated.json()["detail"]

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "cancelled"
    assert request_detail.json()["notes"] == vm_payload["notes"]


def test_execute_api_rejects_planned_request_without_persisted_plan(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200

    request = db_session.get(Request, request_id)
    assert request is not None
    request.status = RequestStatus.PLANNED.value
    db_session.commit()

    executed = client.post(f"/api/v1/requests/{request_id}/execute")

    assert executed.status_code == 409
    assert "no persisted dry-run plan exists" in executed.json()["detail"]

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "planned"

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    event_types = {event["event_type"] for event in audit_events.json()}
    assert "request.execution_preflight_failed" in event_types


def test_execute_api_rejects_request_intent_drift(
    client: TestClient,
    db_session: Session,
    vm_payload: dict,
) -> None:
    created = client.post("/api/v1/requests/vm-deploy", json=vm_payload)
    assert created.status_code == 201
    request_id = created.json()["id"]

    submitted = client.post(f"/api/v1/requests/{request_id}/submit")
    assert submitted.status_code == 200

    approved = client.post(
        f"/api/v1/requests/{request_id}/approve",
        json={"approver": "change.manager", "notes": "Looks safe"},
    )
    assert approved.status_code == 200

    planned = client.post(f"/api/v1/requests/{request_id}/plan")
    assert planned.status_code == 200
    assert planned.json()["plan_json"]["request_intent_hash"].startswith("sha256:")

    request = db_session.get(Request, request_id)
    assert request is not None
    request.vm_deploy.memory_gb = vm_payload["memory_gb"] + 4
    db_session.commit()

    executed = client.post(f"/api/v1/requests/{request_id}/execute")

    assert executed.status_code == 409
    assert "current intent no longer matches" in executed.json()["detail"]

    request_detail = client.get(f"/api/v1/requests/{request_id}")
    assert request_detail.status_code == 200
    assert request_detail.json()["status"] == "planned"

    audit_events = client.get("/api/v1/audit-events")
    assert audit_events.status_code == 200
    matching_events = [
        event
        for event in audit_events.json()
        if event["event_type"] == "request.execution_preflight_failed"
    ]
    assert matching_events[0]["data_json"]["reason"] == "request_intent_mismatch"
    assert matching_events[0]["data_json"]["changed_fields"] == ["vm.memory_gb"]


def test_provider_status_reports_mock_and_preview_providers(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    statuses = response.json()
    ids = {item["id"] for item in statuses}
    assert {"mock-vsphere", "ilo-redfish", "cisco-console", "netapp-ontap"}.issubset(ids)
    assert any(item["name"] == "Mock vSphere" and item["mode"] == "mock" for item in statuses)
    assert all(item["mode"] == "mock" for item in statuses)
    assert all("safe_actions" in item and "disabled_actions" in item for item in statuses)


def test_merged_provider_preview_endpoints_smoke_in_mock_mode(client: TestClient) -> None:
    endpoint_expectations = [
        (
            "/api/v1/providers/ilo-redfish/upgrade-readiness",
            "ilo-redfish",
            ["apply_enabled", "blockers", "warnings"],
        ),
        (
            "/api/v1/providers/ilo-redfish/readiness-summary",
            "ilo-redfish",
            ["desired_setup_sections", "blockers", "warnings", "disabled_dangerous_actions"],
        ),
        (
            "/api/v1/providers/ilo-redfish/setup-plan-preview",
            "ilo-redfish",
            ["apply_enabled", "sections", "blockers", "warnings", "disabled_dangerous_actions"],
        ),
        (
            "/api/v1/providers/ilo-redfish/report-preview",
            "ilo-redfish",
            ["apply_enabled", "setup_compare_report", "blockers", "warnings"],
        ),
        (
            "/api/v1/providers/ilo-redfish/setup-apply-plan",
            "ilo-redfish-setup-apply",
            ["apply_enabled", "operations", "blockers", "confirmation_phrase"],
        ),
        (
            "/api/v1/providers/cisco/setup-readiness",
            "cisco-setup",
            ["blockers", "warnings", "disabled_actions", "next_safe_action"],
        ),
        (
            "/api/v1/providers/cisco/setup-wizard-plan",
            "cisco-setup-wizard-plan",
            ["apply_enabled", "blockers", "warnings", "disabled_actions"],
        ),
        (
            "/api/v1/providers/cisco/bootstrap-requirements",
            "cisco-bootstrap-requirements",
            ["apply_enabled", "blockers", "warnings", "disabled_actions"],
        ),
        (
            "/api/v1/providers/cisco/console-bootstrap/plan",
            "cisco-console-bootstrap",
            ["apply_enabled", "blockers", "warnings", "destructive_actions_disabled"],
        ),
        (
            "/api/v1/providers/netapp-ontap/plan-preview",
            "netapp-ontap",
            ["apply_enabled", "blockers", "warnings", "disabled_actions"],
        ),
        (
            "/api/v1/providers/netapp-ontap/console-readiness",
            "netapp-ontap",
            ["apply_enabled", "blockers", "warnings", "disabled_actions"],
        ),
        (
            "/api/v1/providers/netapp-ontap/readiness-comparison",
            "netapp-ontap",
            ["apply_enabled", "blockers", "warnings", "disabled_actions"],
        ),
        (
            "/api/v1/providers/netapp-ontap/upgrade-readiness",
            "netapp-ontap",
            ["apply_enabled", "blockers", "warnings", "disabled_actions"],
        ),
    ]

    for path, provider_id, required_keys in endpoint_expectations:
        response = client.get(path)

        assert response.status_code == 200, path
        payload = response.json()
        assert payload["provider_id"] == provider_id
        for key in required_keys:
            assert key in payload, f"{path} missing {key}"


def test_ilo_setup_apply_endpoint_blocked_by_default(client: TestClient) -> None:
    response = client.post(
        "/api/v1/providers/ilo-redfish/setup-apply",
        json={"confirmation_phrase": "APPLY ILO HOSTNAME SETUP"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "ilo-redfish-setup-apply"
    assert payload["status"] == "blocked"
    assert payload["patch_attempted"] is False
    assert payload["patch_count"] == 0
    assert any("PROVIDER_MODE=local-lab-readwrite" in blocker for blocker in payload["blockers"])


def test_cisco_setup_readiness_endpoint_is_read_only_preview(client: TestClient) -> None:
    response = client.get("/api/v1/providers/cisco/setup-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "cisco-setup"
    assert payload["phase"] in {"console-bootstrap-required", "ssh-management-ready"}
    assert payload["bootstrap_preview"]["apply_enabled"] is False
    assert payload["bootstrap_preview"]["commands_redacted"] is True
    assert payload["ssh_scp_readiness"]["planned_only"] is True
    assert payload["ssh_scp_readiness"]["apply_enabled"] is False
    assert payload["ansible"]["enabled"] is False
    assert payload["backup_report"]["backup_enabled"] is False
    assert payload["next_safe_action"] == (
        "Select a console candidate and run prompt readiness check."
    )
    assert "real config apply" in payload["disabled_actions"]

    encoded = response.text
    assert "/probe" not in encoded
    assert "Configure Terminal" not in encoded


def test_cisco_prompt_readiness_endpoint_blocks_in_mock_mode(client: TestClient) -> None:
    response = client.post("/api/v1/providers/cisco-console/prompt-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "cisco-console"
    assert payload["action"] == "prompt-readiness"
    assert payload["status"] == "blocked"
    assert "local-readonly" in payload["message"]
    assert "safe show commands" in payload["not_attempted"]
    assert payload["prompt_ready"] is False


def test_cisco_setup_wizard_plan_endpoint_returns_safe_unknown_preview(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/cisco/setup-wizard-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "cisco-setup-wizard-plan"
    assert payload["status"] == "preview"
    assert payload["apply_enabled"] is False
    assert payload["detected_prompt_state"] in {"unknown", "setup-wizard"}
    assert "answer setup wizard" in payload["disabled_actions"]
    assert "conf t" in payload["disabled_actions"]
    assert "write memory" in payload["disabled_actions"]
    assert "reload" in payload["disabled_actions"]
    assert "erase/copy" in payload["disabled_actions"]
    assert "enable SSH/SCP" in payload["disabled_actions"]
    assert "real config apply" in payload["disabled_actions"]
    assert "answer setup wizard yes/no prompt" in payload["not_attempted"]


def test_cisco_bootstrap_requirements_endpoint_returns_preview_only(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/cisco/bootstrap-requirements")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "cisco-bootstrap-requirements"
    assert payload["apply_enabled"] is False
    assert payload["requirements"]["planned_management_ip"]["value"] == "192.168.1.204"
    assert payload["requirements"]["local_admin_username"]["presence_only"] is True
    assert payload["requirements"]["ssh_scp_policy"]["planned_only"] is True
    assert payload["requirements"]["ssh_scp_policy"]["apply_enabled"] is False
    assert payload["requirements"]["save_behavior"]["enabled"] is False
    assert "answer setup wizard" in payload["disabled_actions"]
    assert "conf t" in payload["disabled_actions"]
    assert "write memory" in payload["disabled_actions"]
    assert "reload" in payload["disabled_actions"]
    assert "erase/copy" in payload["disabled_actions"]
    assert "enable SSH/SCP" in payload["disabled_actions"]
    assert "real config apply" in payload["disabled_actions"]


def test_cisco_bootstrap_requirements_update_saves_preview_only(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.cisco_bootstrap_requirements.STATE_PATH",
        tmp_path / "bootstrap-requirements.json",
    )

    response = client.put(
        "/api/v1/providers/cisco/bootstrap-requirements",
        json={
            "planned_management_ip": "192.168.1.204",
            "subnet_prefix": "/24",
            "gateway": "192.168.1.1",
            "management_vlan": "8",
            "management_interface": "Vlan8",
            "management_strategy": "SVI management interface",
            "hostname": "cisco-lab-01",
            "domain_name": "lab.example.test",
            "dns_servers": ["192.168.1.1"],
            "local_admin_username_configured": True,
            "local_admin_username_reference": "local-env:CISCO_TEST_USERNAME",
            "operator_notes": "Preview only. No secrets.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    encoded = response.text
    assert payload["provider_id"] == "cisco-bootstrap-requirements"
    assert payload["status"] == "preview"
    assert payload["apply_enabled"] is False
    assert payload["requirements"]["planned_management_ip"]["value"] == "192.168.1.204"
    assert payload["requirements"]["local_admin_username"]["value"] == "configured"
    assert payload["requirements"]["ssh_scp_policy"]["planned_only"] is True
    assert payload["requirements"]["ssh_scp_policy"]["apply_enabled"] is False
    assert payload["requirements"]["save_behavior"]["enabled"] is False
    assert "write memory" in payload["disabled_actions"]
    assert "enable SSH/SCP" in payload["disabled_actions"]
    assert "super-secret" not in encoded.lower()


def test_cisco_bootstrap_requirements_update_rejects_invalid_ip(
    client: TestClient,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.cisco_bootstrap_requirements.STATE_PATH",
        tmp_path / "bootstrap-requirements.json",
    )

    response = client.put(
        "/api/v1/providers/cisco/bootstrap-requirements",
        json={
            "planned_management_ip": "invalid",
            "subnet_prefix": "/24",
            "gateway": "also-invalid",
            "management_strategy": "SVI management interface",
            "hostname": "cisco-lab-01",
            "domain_name": "lab.example.test",
            "dns_servers": ["192.168.1.1"],
            "local_admin_username_configured": True,
        },
    )

    assert response.status_code == 422
    fields = {error["field"] for error in response.json()["detail"]["validation_errors"]}
    assert {"planned_management_ip", "gateway"}.issubset(fields)


def test_cisco_console_bootstrap_plan_endpoint_is_preview_only(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/cisco/console-bootstrap/plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "cisco-console-bootstrap"
    assert payload["target"]["required_ip"] == "192.168.1.204"
    assert payload["target"]["required_prefix"] == "/24"
    assert payload["target"]["netmask"] == "255.255.255.0"
    assert payload["apply_enabled"] is False
    assert payload["execution_supported"] is False
    assert payload["confirmation_phrase"] == "APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.204"
    assert "write erase" in payload["destructive_actions_disabled"]
    assert "erase startup-config" in payload["destructive_actions_disabled"]
    assert "reload" in payload["destructive_actions_disabled"]


def test_cisco_console_bootstrap_apply_endpoint_blocked_by_default(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/providers/cisco/console-bootstrap/apply",
        json={"confirmation_phrase": "APPLY CISCO CONSOLE BOOTSTRAP 192.168.1.204"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "cisco-console-bootstrap"
    assert payload["status"] == "blocked"
    assert payload["serial_writes_attempted"] is False
    assert payload["commands_sent"] == []
    assert any("PROVIDER_MODE=local-readonly" in blocker for blocker in payload["blockers"])


def test_cisco_console_bootstrap_apply_endpoint_requires_exact_phrase(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/providers/cisco/console-bootstrap/apply",
        json={"confirmation_phrase": "APPLY"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["serial_writes_attempted"] is False
    assert any("Exact confirmation phrase" in blocker for blocker in payload["blockers"])
