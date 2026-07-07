from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import RequestStatus, WorkflowRunStatus
from app.models import AuditEvent, Request, WorkflowRun
from app.providers.action_policy import current_lab_action_policy
from app.providers.esxi_readonly import EsxiReadonlyConfig
from app.services import firmware_file_selections, lab_profiles, lab_safety_settings, provider_mode_settings


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_build_verification_endpoint_returns_status(client: TestClient) -> None:
    response = client.get("/api/v1/lab/build-verification")

    assert response.status_code == 200
    assert response.json()["provider_id"] == "build-verification"
    assert "status" in response.json()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/lab/vcenter-netapp/readiness"),
        ("get", "/api/v1/providers/netapp-ontap/setup-preview"),
        ("post", "/api/v1/providers/netapp-ontap/setup-apply"),
        ("get", "/api/v1/providers/netapp-ontap/nfs-vcenter-readiness"),
    ],
)
def test_single_server_profile_marks_netapp_vcenter_provider_endpoints_not_in_scope(
    client: TestClient,
    monkeypatch,
    tmp_path: Path,
    method: str,
    path: str,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    lab_profiles.create_lab_profile(
        {
            "name": "Single Server Lab",
            "features": {"netapp_enabled": False, "vcenter_enabled": False},
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )

    response = getattr(client, method)(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_in_scope"
    assert payload["blockers"] == []
    assert "active lab profile" in json.dumps(payload).lower()


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
        "esxi.vm-deploy-preview",
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


def test_ui_intent_resolves_only_allowlisted_layout_regions(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ui-intent",
        json={
            "page": "overview",
            "request": "hide advanced proof and run rebuild",
            "regions": [
                {"id": "topology", "label": "Living lab topology", "kind": "section"},
                {"id": "advanced-proof", "label": "Advanced proof", "kind": "drawer"},
            ],
            "current_layout": {
                "topology": {"visible": True, "collapsed": False, "order": 0},
                "advanced-proof": {"visible": True, "collapsed": False, "order": 1},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local_rules"
    assert payload["ops"] == [{"region_id": "advanced-proof", "op": "hide"}]
    assert "rebuild" not in json.dumps(payload).lower()


def test_ui_intent_drops_unknown_or_unmatched_requests(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ui-intent",
        json={
            "page": "storage",
            "request": "factory reset the netapp",
            "regions": [
                {"id": "reference", "label": "Storage reference", "kind": "section"},
            ],
            "current_layout": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ops"] == []
    assert payload["summary"] == "No safe layout change matched this page."


def test_ui_intent_applies_this_box_when_manifest_is_target_scoped(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ui-intent",
        json={
            "page": "overview",
            "request": "hide this box",
            "regions": [
                {"id": "topology", "label": "Living lab topology", "kind": "section"},
            ],
            "current_layout": {
                "topology": {"visible": True, "collapsed": False, "order": 0},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local_rules"
    assert payload["ops"] == [{"region_id": "topology", "op": "hide"}]


def test_ui_intent_uses_anthropic_when_key_is_present_and_validates_manifest(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeAnthropicResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "resolve_ui_intent",
                        "input": {
                            "ops": [
                                {"region_id": "advanced-proof", "op": "hide"},
                                {"region_id": "factory-reset", "op": "show"},
                                {"region_id": "advanced-proof", "op": "run"},
                            ],
                            "summary": "Hid advanced proof.",
                        },
                    }
                ]
            }

    class FakeAnthropicClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeAnthropicResponse()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_UI_INTENT_MODEL", "test-model")
    monkeypatch.setattr("app.services.ui_intent.httpx.Client", FakeAnthropicClient)

    response = client.post(
        "/api/v1/ui-intent",
        json={
            "page": "overview",
            "request": "password=supersecret please remove the proof clutter",
            "regions": [
                {"id": "topology", "label": "Living lab topology", "kind": "section"},
                {"id": "advanced-proof", "label": "Advanced proof", "kind": "drawer"},
            ],
            "current_layout": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "external_ai"
    assert payload["ops"] == [{"region_id": "advanced-proof", "op": "hide"}]
    encoded_request = json.dumps(captured["json"])
    assert "supersecret" not in encoded_request
    assert "password=[REDACTED]" in encoded_request


def test_ai_change_request_endpoint_queues_markdown_without_running_actions(client: TestClient) -> None:
    mailbox = Path(__file__).resolve().parents[2] / "docs" / "agent-chat.md"
    original_mailbox = mailbox.read_text(encoding="utf-8") if mailbox.exists() else ""
    response = client.post(
        "/api/v1/ai-change-requests",
        json={
            "page": "overview",
            "route": "/overview",
            "request": "make the topology map support drag and drop device creation",
            "target": "Living lab topology (topology)",
            "regions": [
                {"id": "topology", "label": "Living lab topology", "kind": "section"},
            ],
            "current_layout": {
                "topology": {"visible": True, "collapsed": False, "order": 0},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["artifact"].startswith("docs/change-requests/")
    artifact = Path(__file__).resolve().parents[2] / payload["artifact"]
    try:
        text = artifact.read_text(encoding="utf-8")
        assert "capture-only" in text
        assert "drag and drop device creation" in text
        assert "Living lab topology (topology)" in text
        assert "does not execute code" in text
        mailbox_text = mailbox.read_text(encoding="utf-8")
        assert "New AI change request queued" in mailbox_text
        assert payload["artifact"] in mailbox_text
        assert "make the topology map support drag and drop device creation" in mailbox_text
        assert "Living lab topology (topology)" in mailbox_text
        assert "sent to Claude+Codex mailbox" in mailbox_text
        assert payload["message"] == "Sent to the Claude+Codex mailbox and saved as a review artifact."
    finally:
        artifact.unlink(missing_ok=True)
        mailbox.write_text(original_mailbox, encoding="utf-8")


def test_control_action_catalog_keeps_netapp_readonly_actions_runnable_when_state_blocked(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/control/actions")

    assert response.status_code == 200
    payload = response.json()
    actions = {action["id"]: action for action in payload["actions"]}

    readonly_ids = {
        "netapp.console-autodiscovery",
        "netapp.console-read-state",
        "netapp.console-login-state",
        "netapp.ha-node-diagnose",
        "netapp.live-state",
        "netapp.setup-preview",
        "netapp.nfs-setup-preview",
        "netapp.ontap-upgrade-inventory",
        "netapp.ontap-upgrade-plan",
        "netapp.ontap-upgrade-validate",
    }
    for action_id in readonly_ids:
        assert actions[action_id]["classification"] == "read-only"
        assert actions[action_id]["availability"] == "manual_command_required"
        assert actions[action_id]["blocker"] is None

    assert actions["netapp.setup-apply"]["availability"] == "blocked"
    assert actions["netapp.nfs-setup-apply"]["availability"] == "blocked"
    assert actions["netapp.ontap-upgrade-apply"]["availability"] == "blocked"


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


def test_provider_mode_settings_exposes_real_lab_runtime_options(
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
    assert "mock" not in labels
    assert labels["local-readonly"] == "Read-only Live Checks"
    assert labels["local-lab-readwrite"] == "Real Lab Runtime"
    assert payload["desired_mode"] == "local-lab-readwrite"
    assert payload["expected_runtime_mode"] == "local-lab-readwrite"
    assert payload["pending_restart"] is (payload["current_mode"] != "local-lab-readwrite")
    if payload["current_mode"] == "mock":
        assert "test mode only" in payload["dev_test_banner"]
    assert payload["mode_env_path"].endswith("app-mode.env")


def test_provider_mode_default_paths_use_posix_separators(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("PROVIDER_MODE_SETTINGS_STORE", raising=False)
    monkeypatch.delenv("APP_MODE_ENV_FILE", raising=False)
    monkeypatch.setattr(provider_mode_settings, "REPO_ROOT", tmp_path)

    payload = provider_mode_settings.read_provider_mode_settings()

    assert payload["mode_env_path"] == ".local/app-mode.env"
    assert payload["store_path"] == ".local/provider-mode-settings.json"


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
    assert not list(tmp_path.glob("*.tmp"))

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert stored["desired_mode"] == desired
    assert stored["operator_runtime_only"] is True
    assert "password" not in stored


def test_provider_mode_settings_ignores_corrupt_store(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "provider-mode.json"
    store_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("PROVIDER_MODE_SETTINGS_STORE", str(store_path))
    monkeypatch.setenv("APP_MODE_ENV_FILE", str(tmp_path / "app-mode.env"))

    response = client.get("/api/v1/settings/provider-mode")

    assert response.status_code == 200
    assert response.json()["desired_mode"] == "local-lab-readwrite"


def test_provider_mode_settings_reads_quoted_env_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "missing-provider-mode.json"
    env_path = tmp_path / "app-mode.env"
    env_path.write_text(
        "# PROVIDER_MODE=local-lab-readwrite\n"
        "export PROVIDER_MODE=\"local-readonly\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROVIDER_MODE_SETTINGS_STORE", str(store_path))
    monkeypatch.setenv("APP_MODE_ENV_FILE", str(env_path))

    response = client.get("/api/v1/settings/provider-mode")

    assert response.status_code == 200
    assert response.json()["desired_mode"] == "local-readonly"


def test_lab_safety_settings_exposes_global_runtime_flags(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_SAFETY_SETTINGS_STORE", str(tmp_path / "lab-safety.json"))

    response = client.get("/api/v1/settings/lab-safety")

    assert response.status_code == 200
    payload = response.json()
    names = {flag["name"] for flag in payload["flags"]}
    assert {
        "lab_environment",
        "lab_acknowledge_real_hardware",
        "lab_acknowledge_device_reconfiguration",
        "lab_acknowledge_data_loss_risk",
        "lab_acknowledge_lab_only",
    }.issubset(names)
    assert payload["confirmation_phrase"] == lab_safety_settings.CONFIRMATION_PHRASE
    assert (
        payload["device_reconfiguration_confirmation_phrase"]
        == lab_safety_settings.DEVICE_RECONFIGURATION_CONFIRMATION_PHRASE
    )
    assert payload["store_path"].endswith("lab-safety.json")


def test_lab_safety_settings_write_overrides_action_policy_without_restart(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "lab-safety.json"
    monkeypatch.setenv("LAB_SAFETY_SETTINGS_STORE", str(store_path))

    response = client.put(
        "/api/v1/settings/lab-safety",
        json={
            "lab_environment": "isolated-real-lab",
            "lab_acknowledge_real_hardware": True,
            "lab_acknowledge_device_reconfiguration": True,
            "lab_acknowledge_data_loss_risk": True,
            "lab_acknowledge_lab_only": True,
            "confirmation_phrase": lab_safety_settings.CONFIRMATION_PHRASE,
            "device_reconfiguration_confirmation_phrase": (
                lab_safety_settings.DEVICE_RECONFIGURATION_CONFIRMATION_PHRASE
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert all(flag["enabled"] for flag in payload["flags"])
    assert not current_lab_action_policy("local-lab-readwrite").readonly_blockers()
    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert stored["lab_acknowledge_data_loss_risk"] is True
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == "settings.lab_safety.updated")
        .one()
    )
    assert event.actor == "local-operator"
    assert "confirmation_phrase" not in event.data_json
    assert "device_reconfiguration_confirmation_phrase" not in event.data_json
    assert "lab_acknowledge_data_loss_risk" in event.data_json["changed_fields"]


def test_local_user_header_sets_audit_actor(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "lab-safety.json"
    monkeypatch.setenv("LAB_SAFETY_SETTINGS_STORE", str(store_path))

    response = client.put(
        "/api/v1/settings/lab-safety",
        json={
            "lab_environment": "isolated-real-lab",
            "lab_acknowledge_real_hardware": True,
            "lab_acknowledge_device_reconfiguration": True,
            "lab_acknowledge_lab_only": True,
            "device_reconfiguration_confirmation_phrase": (
                lab_safety_settings.DEVICE_RECONFIGURATION_CONFIRMATION_PHRASE
            ),
        },
        headers={"X-Local-User": "real-lab-operator"},
    )

    assert response.status_code == 200
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == "settings.lab_safety.updated")
        .one()
    )
    assert event.actor == "real-lab-operator"


def test_lab_safety_settings_requires_confirmation_for_data_loss_ack(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_SAFETY_SETTINGS_STORE", str(tmp_path / "lab-safety.json"))

    response = client.put(
        "/api/v1/settings/lab-safety",
        json={"lab_acknowledge_data_loss_risk": True, "confirmation_phrase": "wrong"},
    )

    assert response.status_code == 422
    assert "confirmation phrase" in response.json()["detail"]


def test_lab_safety_settings_requires_confirmation_for_device_reconfiguration_ack(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_SAFETY_SETTINGS_STORE", str(tmp_path / "lab-safety.json"))

    response = client.put(
        "/api/v1/settings/lab-safety",
        json={
            "lab_acknowledge_device_reconfiguration": True,
            "device_reconfiguration_confirmation_phrase": "wrong",
        },
    )

    assert response.status_code == 422
    assert "Device reconfiguration" in response.json()["detail"]


def test_provider_mode_settings_reads_values_with_equals_from_env_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "missing-provider-mode.json"
    env_path = tmp_path / "app-mode.env"
    env_path.write_text(
        'APP_NOTE="operator=ready"\n'
        'PROVIDER_MODE="local-lab-readwrite"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PROVIDER_MODE_SETTINGS_STORE", str(store_path))
    monkeypatch.setenv("APP_MODE_ENV_FILE", str(env_path))

    response = client.get("/api/v1/settings/provider-mode")

    assert response.status_code == 200
    assert response.json()["desired_mode"] == "local-lab-readwrite"


def test_firmware_file_selections_persist_in_ignored_local_store(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "firmware-file-selections.json"
    monkeypatch.setenv("FIRMWARE_FILE_SELECTION_STORE", str(store_path))

    initial = client.get("/api/v1/firmware/file-selections")

    assert initial.status_code == 200
    assert initial.json()["selected_files"] == {}
    assert initial.json()["apply_enabled"] is False

    saved = client.put(
        "/api/v1/firmware/file-selections",
        json={
            "selected_files": {
                "cisco_ios_xe_version": "cat9k_iosxe.17.12.01.SPA.bin",
                "hpe_smart_array_firmware": "",
            }
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["selected_files"] == {
        "cisco_ios_xe_version": "cat9k_iosxe.17.12.01.SPA.bin",
        "hpe_smart_array_firmware": "",
    }
    assert payload["store_path"].endswith("firmware-file-selections.json")
    assert payload["source_type"] == "operator_config"
    assert payload["apply_enabled"] is False

    stored = json.loads(store_path.read_text(encoding="utf-8"))
    assert stored["selected_files"] == payload["selected_files"]
    assert stored["operator_runtime_only"] is True
    assert "password" not in json.dumps(stored).lower()

    reloaded = client.get("/api/v1/firmware/file-selections")
    assert reloaded.status_code == 200
    assert reloaded.json()["selected_files"] == payload["selected_files"]


def test_firmware_file_selections_ignores_corrupt_store(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "firmware-file-selections.json"
    store_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("FIRMWARE_FILE_SELECTION_STORE", str(store_path))

    response = client.get("/api/v1/firmware/file-selections")

    assert response.status_code == 200
    assert response.json()["selected_files"] == {}
    assert response.json()["status"] == "not_configured_yet"


def test_firmware_file_selection_repo_store_label_uses_posix_separators(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("FIRMWARE_FILE_SELECTION_STORE", raising=False)
    monkeypatch.setattr(firmware_file_selections, "REPO_ROOT", tmp_path)

    assert firmware_file_selections._path_label(tmp_path / ".local" / "firmware-file-selections.json") == ".local/firmware-file-selections.json"


def test_firmware_file_selections_reject_paths_and_secret_like_values(client: TestClient) -> None:
    with_path = client.put(
        "/api/v1/firmware/file-selections",
        json={"selected_files": {"cisco_ios_xe_version": "../cat9k.bin"}},
    )
    with_secret = client.put(
        "/api/v1/firmware/file-selections",
        json={"selected_files": {"cisco_ios_xe_version": "password=example.bin"}},
    )

    assert with_path.status_code == 422
    assert with_secret.status_code == 422


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
            "editable_fields": [
                {"label": "Management IP", "value": "192.0.2.56"},
                {"label": "Gateway", "value": "192.0.2.1"},
                {"label": "DNS", "value": "lab-dns.local"},
            ],
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["section_id"] == "ilo"
    assert payload["original_dhcp_ip"] == "192.0.2.55"
    assert payload["username_reference"] == "local-admin"
    assert payload["password_configured"] is True
    assert payload["password_reference_label"] is None
    assert payload["blockers"] == []
    fields = {item["label"]: item for item in payload["editable_fields"]}
    assert fields["Management IP"]["value"] == "192.0.2.56"
    assert fields["Management IP"]["source"] == "saved_override"
    assert fields["Gateway"]["value"] == "192.0.2.1"
    assert fields["DNS"]["value"] == "lab-dns.local"

    catalog = client.get("/api/v1/control/actions").json()
    ilo = next(section for section in catalog["sections"] if section["id"] == "ilo")
    assert ilo["access_config"]["original_dhcp_ip"] == "192.0.2.55"
    assert ilo["access_config"]["password_configured"] is True
    catalog_fields = {item["label"]: item for item in ilo["access_config"]["editable_fields"]}
    assert catalog_fields["Management IP"]["value"] == "192.0.2.56"
    assert catalog_fields["Management IP"]["source"] == "saved_override"


def test_control_access_config_ignores_corrupt_store_and_writes_atomically(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "control-access.json"
    store_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CONTROL_ACCESS_STORE", str(store_path))
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    catalog = client.get("/api/v1/control/actions")
    assert catalog.status_code == 200
    cisco = next(section for section in catalog.json()["sections"] if section["id"] == "cisco")
    assert cisco["access_config"]["first_time_configuring"] is True

    saved = client.put(
        "/api/v1/control/access/cisco",
        json={
            "first_time_configuring": True,
            "original_dhcp_ip": "192.0.2.10",
            "password_configured": False,
        },
    )

    assert saved.status_code == 200
    assert json.loads(store_path.read_text(encoding="utf-8"))["cisco"]["original_dhcp_ip"] == "192.0.2.10"
    assert not list(tmp_path.glob("*.tmp"))


def test_control_access_config_self_heals_string_booleans(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "control-access.json"
    store_path.write_text(
        json.dumps(
            {
                "cisco": {
                    "first_time_configuring": "false",
                    "password_configured": "false",
                    "editable_fields": {},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTROL_ACCESS_STORE", str(store_path))
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    catalog = client.get("/api/v1/control/actions")

    assert catalog.status_code == 200
    cisco = next(section for section in catalog.json()["sections"] if section["id"] == "cisco")
    access_config = cisco["access_config"]
    assert access_config["first_time_configuring"] is False
    assert access_config["password_configured"] is False
    assert access_config["blockers"] == []


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


def test_control_access_config_rejects_unknown_editable_fields(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("CONTROL_ACCESS_STORE", str(tmp_path / "control-access.json"))

    response = client.put(
        "/api/v1/control/access/netapp",
        json={
            "first_time_configuring": False,
            "password_configured": False,
            "editable_fields": [{"label": "Plaintext Password", "value": "not allowed"}],
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
            "devices": {
                "server_model": "gen10plus",
            },
            "address_plan": {
                "subnet": "192.0.2.0/24",
                "ilo": "192.0.2.10",
                "ilo_initial": "10.0.0.55",
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
    assert created.json()["devices"]["server_model"] == "gen10plus"
    assert created.json()["address_plan"]["ilo"] == "192.0.2.10"
    assert created.json()["address_plan"]["ilo_initial"] == "10.0.0.55"

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


def test_lab_profile_api_dedupes_repeated_lif_addresses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Repeated LIF Lab",
            "dns": "192.0.2.53, 192.0.2.53,192.0.2.54",
            "global_settings": {
                "dns_servers": "192.0.2.53, 192.0.2.53, 192.0.2.54",
                "ntp_servers": ["192.0.2.55", "192.0.2.55"],
            },
            "address_plan": {
                "subnet": "192.0.2.0/24",
                "netapp_iscsi_lifs": ",".join(["192.0.2.21"] * 20 + ["192.0.2.22"]),
                "netapp_nfs_lifs": ["192.0.2.23", "192.0.2.23", "192.0.2.24"],
            },
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["dns"] == ["192.0.2.53", "192.0.2.54"]
    assert payload["global_settings"]["dns_servers"] == ["192.0.2.53", "192.0.2.54"]
    assert payload["global_settings"]["ntp_servers"] == ["192.0.2.55"]
    assert payload["address_plan"]["netapp_iscsi_lifs"] == ["192.0.2.21", "192.0.2.22"]
    assert payload["address_plan"]["netapp_nfs_lifs"] == ["192.0.2.23", "192.0.2.24"]


def test_topology_design_draft_api_persists_without_hardware_effect(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TOPOLOGY_DESIGN_DRAFT_STORE", str(tmp_path / "topology-design-drafts.json"))

    default = client.get(
        "/api/v1/lab/topology-design-draft",
        params={
            "profile_id": "lab-demo",
            "scenario": "server_netapp_vcenter",
            "subnet": "192.168.1.0/24",
        },
    )
    assert default.status_code == 200
    assert default.json()["source"] == "default"
    assert default.json()["placements"]["virtual"] == "vcenter"
    assert default.json()["device_settings"]["switch"]["mgmt_vlan"] == "100"
    assert default.json()["lane_settings"]["storage"]["mtu"] == "9000"
    assert default.json()["connection_settings"]["server-netapp"]["protocol"] == "datastore path"
    assert default.json()["hardware_touched"] is False

    saved = client.put(
        "/api/v1/lab/topology-design-draft",
        json={
            "profile_id": "lab-demo",
            "scenario": "server_netapp_vcenter",
            "subnet": "192.168.1.0/24",
            "placements": {
                "u1": "switch",
                "u2": "server-gen10plus",
                "u3": "netapp",
                "u4": "server-gen10",
                "virtual": "vcenter",
            },
            "device_settings": {
                "switch": {
                    "mgmt_vlan": "200",
                    "storage_vlan": "230",
                    "ports": "Gi1/0/1 server, Gi1/0/2 NetApp A, Gi1/0/3 NetApp B",
                },
                "server-gen10plus": {
                    "raid_boot": "RAID1",
                    "raid_data": "RAID6 for local VM staging",
                },
            },
            "lane_settings": {
                "storage": {
                    "mtu": "9100",
                    "protocol": "NFS primary with iSCSI optional",
                    "vlan": "230",
                }
            },
            "connection_settings": {
                "server-netapp": {
                    "protocol": "NFS primary plus iSCSI standby",
                    "status": "planned - needs live session",
                    "vlan": "230",
                }
            },
        },
    )
    assert saved.status_code == 200
    payload = saved.json()
    assert payload["source"] == "saved"
    assert payload["draft_saved"] is True
    assert payload["hardware_touched"] is False
    assert payload["placements"]["u2"] == "server-gen10plus"
    assert payload["device_settings"]["switch"]["storage_vlan"] == "230"
    assert payload["device_settings"]["server-gen10plus"]["raid_data"] == "RAID6 for local VM staging"
    assert payload["lane_settings"]["storage"]["mtu"] == "9100"
    assert payload["lane_settings"]["storage"]["vlan"] == "230"
    assert payload["connection_settings"]["server-netapp"]["protocol"] == "NFS primary plus iSCSI standby"
    assert payload["connection_settings"]["server-netapp"]["status"] == "planned - needs live session"
    assert payload["persistence_inventory"][0]["hardware_effect"] == "none"

    reloaded = client.get(
        "/api/v1/lab/topology-design-draft",
        params={
            "profile_id": "lab-demo",
            "scenario": "server_netapp_vcenter",
            "subnet": "192.168.1.0/24",
        },
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["source"] == "saved"
    assert reloaded.json()["placements"]["u2"] == "server-gen10plus"
    assert reloaded.json()["device_settings"]["switch"]["mgmt_vlan"] == "200"
    assert reloaded.json()["lane_settings"]["storage"]["mtu"] == "9100"
    assert reloaded.json()["connection_settings"]["server-netapp"]["vlan"] == "230"


def test_topology_design_draft_api_normalizes_invalid_single_server_parts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TOPOLOGY_DESIGN_DRAFT_STORE", str(tmp_path / "topology-design-drafts.json"))

    saved = client.put(
        "/api/v1/lab/topology-design-draft",
        json={
            "profile_id": "lab-demo",
            "scenario": "single_server_local_storage",
            "subnet": "192.168.50.0/24",
            "placements": {
                "u1": "switch",
                "u2": "server-gen10",
                "u3": "netapp",
                "virtual": "server-gen10plus",
            },
        },
    )

    assert saved.status_code == 200
    placements = saved.json()["placements"]
    assert placements["u1"] == "switch"
    assert placements["u2"] == "server-gen10"
    assert placements["u3"] is None
    assert placements["virtual"] is None


def test_topology_design_draft_api_rejects_secret_shaped_payloads(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TOPOLOGY_DESIGN_DRAFT_STORE", str(tmp_path / "topology-design-drafts.json"))

    rejected = client.put(
        "/api/v1/lab/topology-design-draft",
        json={
            "profile_id": "lab-demo",
            "scenario": "server_netapp_direct",
            "subnet": "192.168.1.0/24",
            "placements": {
                "u1": "switch",
                "u2": "server-gen10",
                "password": "P@ssw0rd",
            },
        },
    )

    assert rejected.status_code == 422
    assert "unknown rack slot" in rejected.text.lower()

    rejected_device_setting = client.put(
        "/api/v1/lab/topology-design-draft",
        json={
            "profile_id": "lab-demo",
            "scenario": "server_netapp_direct",
            "subnet": "192.168.1.0/24",
            "placements": {
                "u1": "switch",
                "u2": "server-gen10",
            },
            "device_settings": {
                "switch": {
                    "notes": "token=do-not-store-this",
                },
            },
        },
    )

    assert rejected_device_setting.status_code == 422
    assert "secret-looking values are not allowed" in rejected_device_setting.text.lower()


def test_lab_profile_api_ignores_corrupt_store_and_writes_atomically(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    store_path = tmp_path / "lab-profiles.json"
    store_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("LAB_PROFILE_STORE", str(store_path))

    empty = client.get("/api/v1/lab/profiles")
    assert empty.status_code == 200
    assert empty.json()["active_profile"]["id"] == "runtime"
    assert empty.json()["profiles"] == []

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Recovered Lab",
            "address_plan": {"subnet": "192.0.2.0/24"},
        },
    )

    assert created.status_code == 201
    saved = json.loads(store_path.read_text(encoding="utf-8"))
    assert saved["profiles"][0]["name"] == "Recovered Lab"
    assert not list(tmp_path.glob("*.tmp"))


def test_lab_profile_api_keeps_saved_profile_active_and_reports_runtime_mismatch(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "local-lab-readwrite")
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setenv("CISCO_TARGET_IP", "192.168.1.204")

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Old Demo Lab",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.200",
                "server_embedded_nic": "10.10.8.201",
                "esxi_management": "10.10.8.202",
                "cisco_management": "10.10.8.2",
                "ansible_control_host": "10.10.8.5",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/lab/profiles")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_only"] is False
    assert payload["active_profile"]["id"] == created.json()["id"]
    assert payload["active_profile"]["address_plan"]["subnet"] == "10.10.8.0/24"
    assert payload["active_context"]["topology"] == "high_address_lab"
    assert payload["active_context"]["resolved_address_plan"]["cisco_management"] == "10.10.8.2"
    mismatches = {item["env_field"]: item for item in payload["active_context"]["mismatch_warnings"]}
    assert mismatches["CISCO_TARGET_IP"]["expected_value"] == "10.10.8.2"
    assert payload["runtime_profile"]["active"] is False
    assert payload["profiles"][0]["active"] is True
    assert "provider-lab-live-status" in payload["next_safe_action"]


def test_lab_profile_runtime_env_apply_updates_active_profile_ips(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    runtime_keys = [
        "LAB_SUBNET_CIDR",
        "ILO_TEST_HOST",
        "SERVER_EMBEDDED_NIC_IP",
        "ESXI_TEST_HOST",
        "CISCO_TARGET_IP",
        "ANSIBLE_CISCO_HOST",
        "ANSIBLE_CONTROL_HOST",
        "NETAPP_CONTROLLER_A_SP",
        "NETAPP_CONTROLLER_B_SP",
        "NETAPP_CLUSTER_MGMT_IP",
        "NETAPP_NODE_A_MGMT_IP",
        "NETAPP_NODE_B_MGMT_IP",
        "NETAPP_SVM_MGMT_IP",
        "NETAPP_NFS_LIFS",
        "NETAPP_ISCSI_LIFS",
        "LAB_PROFILE_TOPOLOGY",
        "LAB_GATEWAY",
        "LAB_DNS_SERVERS",
        "LAB_NTP_SERVERS",
        "LAB_MTU",
        "LAB_PROFILE_NETAPP_ENABLED",
    ]
    for key in runtime_keys:
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("PROVIDER_MODE", "local-lab-readwrite")
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setenv("LAB_RUNTIME_ENV_FILE", str(env_path))
    monkeypatch.setenv("LAB_SUBNET_CIDR", "192.168.1.0/24")
    monkeypatch.setenv("ILO_TEST_HOST", "192.168.1.201")
    monkeypatch.setenv("SERVER_EMBEDDED_NIC_IP", "192.168.1.202")
    monkeypatch.setenv("ESXI_TEST_HOST", "192.168.1.203")

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Old Demo Lab",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.200",
                "server_embedded_nic": "10.10.8.201",
                "esxi_management": "10.10.8.202",
                "cisco_management": "10.10.8.2",
                "ansible_control_host": "10.10.8.5",
            },
        },
    )
    assert created.status_code == 201

    mismatches = client.get("/api/v1/lab/profiles").json()["active_context"]["mismatch_warnings"]
    assert {item["env_field"] for item in mismatches} >= {
        "LAB_SUBNET_CIDR",
        "ILO_TEST_HOST",
        "SERVER_EMBEDDED_NIC_IP",
        "ESXI_TEST_HOST",
    }

    response = client.post("/api/v1/lab/profiles/active/apply-runtime-env")

    assert response.status_code == 200
    payload = response.json()
    assert payload["applied"] is True
    assert payload["env_path"] == str(env_path)
    assert set(payload["updated_keys"]) >= {
        "LAB_SUBNET_CIDR",
        "ILO_TEST_HOST",
        "SERVER_EMBEDDED_NIC_IP",
        "ESXI_TEST_HOST",
    }
    assert payload["restart_required"] is True
    assert payload["lab_profiles"]["active_context"]["mismatch_warnings"] == []
    contents = env_path.read_text(encoding="utf-8")
    assert "LAB_SUBNET_CIDR=10.10.8.0/24" in contents
    assert "ILO_TEST_HOST=10.10.8.200" in contents
    assert "SERVER_EMBEDDED_NIC_IP=10.10.8.201" in contents
    assert "ESXI_TEST_HOST=10.10.8.202" in contents
    assert "PASSWORD" not in contents
    assert "TOKEN" not in contents
    assert "SECRET" not in contents
    assert not list(tmp_path.glob("*.tmp"))


def test_lab_profile_runtime_env_export_removes_explicit_empty_dns_ntp() -> None:
    updates, removals = lab_profiles._runtime_env_changes_for_context(
        {
            "active_profile": {
                "_field_presence": {"global_settings": ["dns_servers", "ntp_servers"], "top_level": []},
                "dns": ["192.168.1.1"],
                "global_settings": {"dns_servers": [], "ntp_servers": []},
                "ntp": ["192.168.1.1"],
                "profile_topology": "high_address_lab",
            },
            "enabled_features": {"netapp_enabled": False},
            "resolved_address_plan": {},
            "topology": "high_address_lab",
        }
    )

    assert "LAB_DNS_SERVERS" not in updates
    assert "LAB_NTP_SERVERS" not in updates
    assert {"LAB_DNS_SERVERS", "LAB_NTP_SERVERS"} <= removals


def test_lab_profile_runtime_env_export_inherits_absent_dns_ntp() -> None:
    updates, removals = lab_profiles._runtime_env_changes_for_context(
        {
            "active_profile": {
                "_field_presence": {"global_settings": [], "top_level": []},
                "dns": [],
                "global_settings": {
                    "dns_servers": ["192.168.1.10", "192.168.1.11"],
                    "ntp_servers": ["192.168.1.12"],
                },
                "ntp": [],
                "profile_topology": "high_address_lab",
            },
            "enabled_features": {"netapp_enabled": False},
            "resolved_address_plan": {},
            "topology": "high_address_lab",
        }
    )

    assert updates["LAB_DNS_SERVERS"] == "192.168.1.10,192.168.1.11"
    assert updates["LAB_NTP_SERVERS"] == "192.168.1.12"
    assert "LAB_DNS_SERVERS" not in removals
    assert "LAB_NTP_SERVERS" not in removals


def test_lab_profile_runtime_env_write_self_heals_unreadable_env_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text("LAB_GATEWAY=192.168.1.1\n", encoding="utf-8")
    original_read_text = Path.read_text

    def flaky_read_text(path: Path, *args, **kwargs) -> str:
        if path == env_path:
            raise OSError("env file is temporarily unavailable")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)
    monkeypatch.setattr(lab_profiles, "read_dotenv_values", lambda _path: (_ for _ in ()).throw(OSError("unreadable")))

    updated, removed = lab_profiles._write_runtime_env(
        env_path,
        {"LAB_SUBNET_CIDR": "10.10.8.0/24"},
        set(),
    )

    assert updated == ["LAB_SUBNET_CIDR"]
    assert removed == []
    assert original_read_text(env_path, encoding="utf-8") == "LAB_SUBNET_CIDR=10.10.8.0/24\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_lab_profile_runtime_env_reader_handles_exports_and_comments(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text(
        "# LAB_SUBNET_CIDR=10.0.0.0/24\n"
        "export LAB_SUBNET_CIDR=10.10.8.0/24\n"
        "LAB_GATEWAY=10.10.8.1\n"
        'LAB_DNS_SERVERS="10.10.8.1,10.10.8.2"\n'
        "LAB_PROFILE_NETAPP_ENABLED=false\n"
        "IGNORED_UNRELATED=value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setenv("LAB_RUNTIME_ENV_FILE", str(env_path))
    monkeypatch.delenv("LAB_SUBNET_CIDR", raising=False)
    monkeypatch.delenv("LAB_GATEWAY", raising=False)
    monkeypatch.delenv("LAB_DNS_SERVERS", raising=False)
    monkeypatch.delenv("LAB_PROFILE_NETAPP_ENABLED", raising=False)

    response = client.get("/api/v1/lab/profiles")

    assert response.status_code == 200
    runtime_profile = response.json()["runtime_profile"]
    assert runtime_profile["address_plan"]["subnet"] == "10.10.8.0/24"
    assert runtime_profile["global_settings"]["gateway"] == "10.10.8.1"
    assert runtime_profile["global_settings"]["dns_servers"] == ["10.10.8.1", "10.10.8.2"]


def test_lab_profile_api_returns_compact_topology_context(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Compact Edge Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["profile_topology"] == "compact_edge_lab"
    assert payload["resolved_address_plan"]["esxi_management"] == "10.10.5.10"
    assert payload["resolved_address_plan"]["ilo"] == "10.10.5.11"
    assert payload["features"]["netapp_enabled"] is False
    assert payload["features"]["vcenter_enabled"] is False
    assert payload["devices"]["switch_primary"] == "10.10.5.2"
    assert payload["devices"]["switch_secondary"] == "10.10.5.3"
    assert "netapp" in payload["not_in_scope_stages"]

    listing = client.get("/api/v1/lab/profiles")
    assert listing.status_code == 200
    active_context = listing.json()["active_context"]
    assert active_context["topology"] == "compact_edge_lab"
    assert active_context["resolved_address_plan"]["ilo"] == "10.10.5.11"
    assert "netapp" in active_context["disabled_features"]


def test_lab_profile_api_rejects_invalid_topology_overrides(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    duplicate = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Duplicate Compact Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"ilo": "10.10.5.10"},
        },
    )
    out_of_subnet = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Invalid Compact Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"ilo": "10.10.6.11"},
        },
    )

    assert duplicate.status_code == 422
    assert "duplicates" in duplicate.json()["detail"]
    assert out_of_subnet.status_code == 422
    assert "outside active subnet" in out_of_subnet.json()["detail"]


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
    assert options[24]["default_topology"] == "high_address_lab"
    assert options[26]["default_topology"] == "compact_edge_lab"
    assert "NetApp" in options[25]["netapp_disabled_reason"]


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
    assert payload["address_plan"]["cisco_management"] == "192.0.2.204"
    assert payload["address_plan"]["ilo"] == "192.0.2.201"
    assert payload["address_plan"]["esxi_management"] == "192.0.2.203"
    assert payload["address_plan"]["netapp_controller_a_sp"] == "192.0.2.210"
    assert payload["address_plan"]["netapp_cluster_mgmt"] == "192.0.2.220"
    assert payload["address_plan"]["netapp_svm_mgmt"] == "192.0.2.223"
    assert payload["address_plan"]["netapp_iscsi_lifs"] == [
        "192.0.2.240",
        "192.0.2.241",
        "192.0.2.242",
        "192.0.2.243",
    ]


def test_hpe_ilo_baseline_preview_uses_active_profile_and_stays_preview_only(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Kit 42",
            "global_settings": {
                "gateway": "192.0.2.1",
                "support_unit": "Support Alpha",
                "dom_dc": "192.0.2.53",
                "dns_servers": ["192.0.2.53"],
                "timezone": "Eastern",
            },
            "address_plan": {"subnet": "192.0.2.0/24"},
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/hpe-ilo/baseline-preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "hpe-ilo"
    assert payload["source_provider_id"] == "ilo-redfish"

    assert payload["apply_enabled"] is False
    assert "Preview/readiness only" in payload["apply_reason"]
    assert payload["kit_profile"]["kit_id"] == "Kit_42"
    assert payload["kit_profile"]["support_unit"] == "Support Alpha"
    assert payload["kit_profile"]["subnet_mask"] == "255.255.255.0"
    assert payload["kit_profile"]["gateway"] == "192.0.2.1"
    assert payload["kit_profile"]["dom_dc"] == "192.0.2.53"
    assert payload["kit_profile"]["derived_subnet"] == "192.0.2.0/24"
    assert payload["discovery_range"]["addresses"] == [
        "192.0.2.21",
        "192.0.2.22",
        "192.0.2.23",
        "192.0.2.24",
        "192.0.2.25",
        "192.0.2.26",
        "192.0.2.27",
        "192.0.2.28",
        "192.0.2.29",
    ]
    assert payload["reset_required"] is False
    sections = {section["id"]: section for section in payload["expected_baseline_sections"]}
    assert {
        "users",
        "license",
        "snmp",
        "snmpv3",
        "alert_destinations",
        "ipv6_dedicated",
        "sntp_time",
        "reset_handling",
    } == set(sections)
    assert sections["users"]["items"]["admin_account"] == "Kit_42_Admin"
    assert sections["users"]["items"]["operator_account"] == "Kit_42_OA"
    assert sections["snmp"]["items"]["read_community"] == "secret-ref:ilo-snmp-read-community"
    assert sections["snmpv3"]["items"]["auth_protocol"] == "SHA"
    assert sections["snmpv3"]["items"]["privacy_protocol"] == "AES"
    assert sections["alert_destinations"]["items"]["desired_destinations"] == ["192.0.2.53"]
    assert sections["alert_destinations"]["items"]["alert_protocol"] == "SNMPv3Inform"
    assert sections["ipv6_dedicated"]["items"]["dhcpv6_stateful_mode"] == "disabled"
    assert sections["ipv6_dedicated"]["items"]["dhcpv6_stateless_mode"] == "disabled"
    assert sections["sntp_time"]["items"]["sntp_server"] == "192.0.2.1"
    assert sections["sntp_time"]["items"]["timezone"] == "Eastern"
    rows = {(row["section"], row["item"]): row for row in payload["comparison_rows"]}
    assert rows[("License Check", "License status")]["action"] == "check"
    assert rows[("License Check", "License status")]["severity"] == "warning"
    assert rows[("Reset Handling", "Reset after baseline")]["action"] == "requires_confirmation"
    assert rows[("SNMP Alert Destinations", "Alert destination reconcile")]["action"] == "update"
    encoded = response.text.lower()
    assert "csni" not in encoded
    assert "dwan" not in encoded
    assert "password=" not in encoded
    assert "secret-ref:" in encoded


def test_esxi_readonly_config_uses_active_lab_profile_target(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setenv("ESXI_TEST_HOST", "192.168.1.203")

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Server Configure Lab",
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "ilo": "10.10.8.88",
                "esxi_management": "10.10.8.89",
            },
        },
    )
    assert created.status_code == 201

    config = EsxiReadonlyConfig.from_settings()

    assert config.host == "10.10.8.89"


def test_hpe_ilo_baseline_readiness_is_read_only_and_redacted(client: TestClient) -> None:
    response = client.get("/api/v1/providers/hpe-ilo/readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "hpe-ilo"
    assert "expected_baseline_sections" not in payload
    assert payload["apply_enabled"] is False
    assert payload["current_state"]["login_status"] == "redacted"
    check_names = {check["name"] for check in payload["connection_readiness"]}
    assert {
        "Target configured",
        "Credential references",
        "Ping reachability",
        "HTTPS / 443",
        "Redfish root",
    } <= check_names


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
            "/api/v1/providers/hpe-ilo/baseline-preview",
            "hpe-ilo",
            ["apply_enabled", "kit_profile", "discovery_range", "comparison_rows"],
        ),
        (
            "/api/v1/providers/hpe-ilo/readiness",
            "hpe-ilo",
            ["apply_enabled", "connection_readiness", "current_state", "comparison_rows"],
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
    assert payload["backup_report"]["backup_enabled"] is True
    assert payload["backup_report"]["report_placeholder_enabled"] is False
    assert "Raw running-config is not persisted" in payload["backup_report"]["summary"]
    assert payload["next_safe_action"] in {
        "Select a console candidate and run prompt readiness check.",
        "Review setup wizard plan preview.",
    }
    assert "real config apply" in payload["disabled_actions"]

    encoded = response.text
    assert "/probe" not in encoded
    assert "Configure Terminal" not in encoded


def test_cisco_setup_readiness_uses_active_lab_profile_network_defaults(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Network Configure Lab",
            "global_settings": {
                "gateway": "10.10.8.1",
                "dns_servers": ["10.10.8.53"],
                "vlan_id": "8",
            },
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "cisco_management": "10.10.8.2",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/cisco/setup-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["planned_management_ip"] == "10.10.8.2"
    assert payload["state_boundaries"]["saved_kit_config_values"]["planned_management_ip"] == "10.10.8.2"
    assert payload["state_boundaries"]["saved_kit_config_values"]["planned_prefix"] == "/24"
    assert payload["ethernet_readiness"]["planned_management_ip"] == "10.10.8.2"
    assert payload["ethernet_readiness"]["planned_prefix"] == "/24"
    assert payload["ethernet_readiness"]["planned_gateway"] is True
    assert payload["ethernet_readiness"]["management_vlan"] == "8"
    assert payload["ethernet_readiness"]["dns_servers"] == ["10.10.8.53"]


def test_cisco_setup_readiness_honors_empty_active_profile_dns(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "No DNS Lab",
            "global_settings": {
                "gateway": "10.10.8.1",
                "dns_servers": [],
            },
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "cisco_management": "10.10.8.2",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/cisco/setup-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ethernet_readiness"]["dns_servers"] == []


def test_cisco_setup_readiness_inherits_env_dns_when_profile_dns_absent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    from app.services import cisco_setup_readiness

    monkeypatch.setattr(
        cisco_setup_readiness,
        "settings",
        replace(cisco_setup_readiness.settings, cisco_dns_servers=("192.0.2.53", "192.0.2.54")),
    )

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "DNS Inherit Lab",
            "global_settings": {
                "gateway": "10.10.8.1",
            },
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "cisco_management": "10.10.8.2",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/cisco/setup-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ethernet_readiness"]["dns_servers"] == ["192.0.2.53", "192.0.2.54"]


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


def test_cisco_bootstrap_requirements_use_active_lab_profile_defaults(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setattr(
        "app.services.cisco_bootstrap_requirements.STATE_PATH",
        tmp_path / "bootstrap-requirements.json",
    )

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Network Configure Lab",
            "global_settings": {
                "gateway": "10.10.8.1",
                "dns_servers": ["10.10.8.53"],
                "vlan_id": "8",
            },
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "cisco_management": "10.10.8.2",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/cisco/bootstrap-requirements")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requirements"]["planned_management_ip"]["value"] == "10.10.8.2"
    assert payload["requirements"]["subnet_prefix"]["value"] == "/24"
    assert payload["requirements"]["gateway"]["value"] == "10.10.8.1"
    assert payload["requirements"]["management_vlan_interface_strategy"]["vlan"] == "8"
    assert payload["requirements"]["domain_dns"]["dns_servers"] == ["10.10.8.53"]


def test_cisco_bootstrap_requirements_honor_empty_active_profile_dns(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setattr(
        "app.services.cisco_bootstrap_requirements.STATE_PATH",
        tmp_path / "bootstrap-requirements.json",
    )

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "No DNS Lab",
            "global_settings": {
                "gateway": "10.10.8.1",
                "dns_servers": [],
            },
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "cisco_management": "10.10.8.2",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/cisco/bootstrap-requirements")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requirements"]["domain_dns"]["dns_servers"] == []


def test_cisco_bootstrap_requirements_inherit_env_dns_when_profile_dns_absent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setattr(
        "app.services.cisco_bootstrap_requirements.STATE_PATH",
        tmp_path / "bootstrap-requirements.json",
    )
    from app.services import cisco_bootstrap_requirements

    monkeypatch.setattr(
        cisco_bootstrap_requirements,
        "settings",
        replace(cisco_bootstrap_requirements.settings, cisco_dns_servers=("192.0.2.53", "192.0.2.54")),
    )

    created = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "DNS Inherit Lab",
            "global_settings": {
                "gateway": "10.10.8.1",
            },
            "address_plan": {
                "subnet": "10.10.8.0/24",
                "cisco_management": "10.10.8.2",
            },
        },
    )
    assert created.status_code == 201

    response = client.get("/api/v1/providers/cisco/bootstrap-requirements")

    assert response.status_code == 200
    payload = response.json()
    assert payload["requirements"]["domain_dns"]["dns_servers"] == ["192.0.2.53", "192.0.2.54"]


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
