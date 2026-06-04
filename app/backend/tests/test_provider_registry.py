from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.providers.registry import ProviderRegistryError, provider_registry
from app.services.netapp_observations import (
    reset_netapp_observations,
    save_netapp_observations,
)


def test_provider_status_endpoint_reports_mock_registry(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    names = {provider["name"] for provider in payload}
    ids = {provider["id"] for provider in payload}
    assert "Mock vSphere" in names
    assert "Mock NetBox/Nautobot" in names
    assert "HPE iLO / Redfish" in names
    assert "Cisco Console" in names
    assert "NetApp ONTAP" in names
    assert {"ilo-redfish", "cisco-console", "mock-vsphere", "netapp-ontap"}.issubset(ids)
    assert all(provider["mode"] == "mock" for provider in payload)
    assert all("disabled_actions" in provider for provider in payload)


def test_netapp_ontap_status_preview_is_plan_only_and_redacted(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    netapp = next(provider for provider in payload if provider["id"] == "netapp-ontap")
    assert netapp["kind"] == "storage"
    assert netapp["status"] == "blocked"
    assert netapp["capabilities"] == [
        "health",
        "plan-preview",
        "readiness-preview",
        "readiness-comparison-preview",
        "upgrade-readiness-preview",
    ]
    assert netapp["configuration"]["netapp_configured"] is False
    assert netapp["configuration"]["planned_sp_ips"] == {
        "controller_a": "10.10.8.13",
        "controller_b": "10.10.8.14",
    }
    assert netapp["configuration"]["planned_management_ips"] == {
        "cluster": "10.10.8.45",
        "node_a": "10.10.8.46",
        "node_b": "10.10.8.47",
        "svm": "10.10.8.48",
    }
    assert netapp["configuration"]["planned_iscsi_lif_range"] == {
        "start": "10.10.8.51",
        "end": "10.10.8.54",
        "addresses": ["10.10.8.51", "10.10.8.52", "10.10.8.53", "10.10.8.54"],
    }
    assert netapp["configuration"]["api_configured_flags"] == {
        "endpoint_configured": False,
        "endpoint_planned": True,
        "endpoint_reachable": False,
        "username_configured": False,
        "credential_configured": False,
        "tls_verify": True,
    }
    assert netapp["configuration"]["current_discovered_targets"]["discovery_enabled"] is False
    assert netapp["configuration"]["current_discovered_targets"]["management_ips"] == {
        "cluster": None,
        "node_a": None,
        "node_b": None,
        "svm": None,
    }
    assert netapp["configuration"]["target_addressing"] == [
        {"label": "Controller A SP", "address": "10.10.8.13"},
        {"label": "Controller B SP", "address": "10.10.8.14"},
        {"label": "Cluster management", "address": "10.10.8.45"},
        {"label": "Node A management / e0M", "address": "10.10.8.46"},
        {"label": "Node B management / e0M", "address": "10.10.8.47"},
        {"label": "SVM management", "address": "10.10.8.48"},
        {"label": "iSCSI LIFs", "address": "10.10.8.51, 10.10.8.52, 10.10.8.53, 10.10.8.54"},
    ]
    readiness = netapp["discovery"]["readiness"]
    assert readiness["sp_readiness"]["status"] == "planned_not_live"
    assert readiness["cluster_management_readiness"]["status"] == "not_configured"
    assert readiness["cluster_management_readiness"]["reachable"] is False
    assert readiness["node_management_readiness"]["status"] == "not_configured"
    assert readiness["svm_readiness"]["status"] == "planned_not_live"
    assert readiness["iscsi_lif_readiness"]["status"] == "planned_not_live"
    assert readiness["ontap_api_readiness"]["status"] == "blocked_until_configured"
    assert readiness["ontap_api_readiness"]["configured"] is False
    assert readiness["ontap_api_readiness"]["api_access_present"] is False
    assert isinstance(readiness["ontap_api_readiness"]["local_readonly_ack"], bool)
    assert readiness["console_bootstrap_readiness"]["status"] == "manual_placeholder"
    assert readiness["upgrade_readiness_path"]["status"] == "blocked_until_setup_ready"
    assert readiness["storage_iscsi_plan_preview"]["status"] == "preview_only"
    assert readiness["reports_artifacts"]["status"] == "placeholder"
    assert netapp["safe_actions"] == []
    disabled_actions = {action["label"]: action for action in netapp["disabled_actions"]}
    assert set(disabled_actions) >= {
        "Create Cluster",
        "Change IPs",
        "Create SVM",
        "Create LIFs",
        "Create Volumes",
        "Upgrade ONTAP",
        "Reboot Controllers",
        "Wipe Disks",
        "Apply Configuration",
    }
    for label in ("Apply Configuration", "Change IPs", "Upgrade ONTAP", "Reboot Controllers", "Wipe Disks"):
        assert disabled_actions[label]["enabled"] is False
    assert not _contains_sensitive_key(netapp)


def test_netapp_ontap_plan_preview_endpoint_is_plan_only_and_redacted(
    client: TestClient,
) -> None:
    reset_netapp_observations()
    response = client.get("/api/v1/providers/netapp-ontap/plan-preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "netapp-ontap"
    assert payload["mode"] == "mock"
    assert payload["apply_enabled"] is False
    assert payload["netapp_configured"] is False
    assert payload["planned_targets"]["sp_ips"] == {
        "controller_a": "10.10.8.13",
        "controller_b": "10.10.8.14",
    }
    assert payload["planned_targets"]["management_ips"] == {
        "cluster": "10.10.8.45",
        "node_a": "10.10.8.46",
        "node_b": "10.10.8.47",
        "svm": "10.10.8.48",
    }
    assert payload["planned_targets"]["iscsi_lif_range"]["addresses"] == [
        "10.10.8.51",
        "10.10.8.52",
        "10.10.8.53",
        "10.10.8.54",
    ]
    assert payload["planned_targets"]["api_access_flags"] == {
        "endpoint_configured": False,
        "endpoint_planned": True,
        "endpoint_reachable": False,
        "username_configured": False,
        "access_configured": False,
        "tls_verify": True,
    }
    assert payload["current_discovered_targets"]["discovery_enabled"] is False
    assert payload["current_discovered_targets"]["management_ips"]["cluster"] is None
    assert payload["setup_readiness"]["ready"] is False
    assert payload["upgrade_readiness"]["ready"] is False
    readiness = payload["readiness_buckets"]
    assert readiness["sp_readiness"]["status"] == "planned_not_live"
    assert readiness["cluster_management_readiness"]["status"] == "not_configured"
    assert readiness["cluster_management_readiness"]["reachable"] is False
    assert readiness["ontap_api_readiness"]["status"] == "blocked_until_configured"
    assert readiness["ontap_api_readiness"]["api_access_present"] is False
    assert isinstance(readiness["ontap_api_readiness"]["local_readonly_ack"], bool)
    assert readiness["iscsi_lif_readiness"]["status"] == "planned_not_live"
    assert readiness["storage_iscsi_plan_preview"]["status"] == "preview_only"
    assert readiness["reports_artifacts"]["status"] == "placeholder"
    assert payload["cluster_intent_preview"]["management_ip"] == "10.10.8.45"
    assert payload["svm_intent_preview"]["management_ip"] == "10.10.8.48"
    assert len(payload["lif_intent_preview"]["iscsi_lifs"]) == 4
    assert payload["storage_iscsi_plan_preview"]["status"] == "placeholder"
    assert payload["readiness_comparison_preview"]["endpoint"] == (
        "/api/v1/providers/netapp-ontap/readiness-comparison"
    )
    assert payload["readiness_comparison_preview"]["apply_enabled"] is False
    assert payload["readiness_comparison_preview"]["discovery_enabled"] is False
    assert payload["readiness_comparison_preview"]["warning_count"] == 1
    assert payload["readiness_comparison_preview"]["blocker_count"] == 5
    assert payload["upgrade_readiness_preview"]["status"] == "preview_only"
    assert {
        "setup-plan.json",
        "readiness-report.md",
        "upgrade-path-preview.md",
        "storage-iscsi-plan-preview.json",
        "cluster-svm-lif-intent.json",
        "post-run-report.md",
    }.issubset(set(payload["artifact_placeholders"]))
    disabled_actions = {action["label"]: action for action in payload["disabled_actions"]}
    assert set(disabled_actions) >= {
        "Create Cluster",
        "Change IPs",
        "Create SVM",
        "Create LIFs",
        "Create Volumes",
        "Upgrade ONTAP",
        "Reboot Controllers",
        "Wipe Disks",
        "Apply Configuration",
    }
    for label, action in disabled_actions.items():
        if label in {
            "Create Cluster",
            "Change IPs",
            "Create SVM",
            "Create LIFs",
            "Create Volumes",
            "Upgrade ONTAP",
            "Reboot Controllers",
            "Wipe Disks",
            "Apply Configuration",
        }:
            assert action["enabled"] is False
    assert not _contains_forbidden_plan_preview_key(payload)


def test_netapp_ontap_upgrade_readiness_is_offline_disabled_and_redacted(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/netapp-ontap/upgrade-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "netapp-ontap"
    assert payload["mode"] == "mock"
    assert payload["apply_enabled"] is False
    assert payload["upgrade_enabled"] is False
    assert payload["setup_ready"] is False
    assert payload["readiness_scope"] == "upgrade"
    assert payload["current_version_source"] == "unknown"
    assert payload["current_version"] is None
    assert payload["current_version_confidence"] == "unknown"
    assert payload["media_inventory_mode"] == "sample"
    assert payload["candidates"] == []
    assert payload["recommended_target"] is None
    assert payload["required_intermediate_versions"] == []
    assert payload["upgrade_chain"] == []
    assert any("Current ONTAP version is not discovered" in blocker for blocker in payload["blockers"])
    assert any("cluster management is planned but not reachable" in blocker for blocker in payload["blockers"])
    assert any("LAB_READONLY_ACK=YES" in blocker for blocker in payload["blockers"])
    assert any("No ONTAP API" in warning for warning in payload["warnings"])
    assert any("Add ONTAP image media" in warning for warning in payload["removable_warnings"])
    disabled_actions = {action["label"]: action for action in payload["disabled_actions"]}
    assert set(disabled_actions) >= {
        "Upload ONTAP Image",
        "Stage Upgrade",
        "Start Upgrade",
        "Reboot Controller",
        "Apply Upgrade",
    }
    assert all(action["enabled"] is False for action in disabled_actions.values())
    assert not _contains_forbidden_plan_preview_key(payload)


def test_netapp_ontap_console_readiness_is_manual_offline_and_redacted(
    client: TestClient,
) -> None:
    reset_netapp_observations()
    response = client.get("/api/v1/providers/netapp-ontap/console-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "netapp-ontap"
    assert payload["mode"] == "mock"
    assert payload["bootstrap_enabled"] is False
    assert payload["console_probe_enabled"] is False
    assert payload["apply_enabled"] is False
    assert payload["netapp_configured"] is False
    assert payload["planned_targets"]["controller_sp"] == {
        "controller_a": "10.10.8.13",
        "controller_b": "10.10.8.14",
    }
    assert payload["planned_targets"]["management_ips"] == {
        "cluster": "10.10.8.45",
        "node_a": "10.10.8.46",
        "node_b": "10.10.8.47",
        "svm": "10.10.8.48",
    }
    assert payload["planned_targets"]["iscsi_lif_range"]["addresses"] == [
        "10.10.8.51",
        "10.10.8.52",
        "10.10.8.53",
        "10.10.8.54",
    ]
    assert payload["current_discovered_targets"]["management_ips"]["cluster"] is None
    assert payload["current_discovered_targets"]["iscsi_lif_range"]["addresses"] == []
    assert payload["prerequisites"]
    assert payload["manual_steps"]
    assert {state["id"] for state in payload["expected_prompts_or_states"]} >= {
        "loader",
        "boot-menu",
        "cluster-setup",
        "existing-login",
        "unknown",
    }
    assert {
        "physical_access_readiness",
        "console_access_readiness",
        "sp_network_readiness",
        "management_ip_plan_readiness",
        "api_access_readiness",
        "local_readonly_ack_readiness",
        "bootstrap_intent_readiness",
        "future_discovery_readiness",
    }.issubset(payload["readiness_buckets"])
    assert payload["readiness_buckets"]["api_access_readiness"]["status"] == "missing"
    assert payload["readiness_buckets"]["local_readonly_ack_readiness"]["status"] in {
        "acknowledged",
        "missing",
    }
    assert payload["observations"]["observed_console_state"] == "unknown"
    assert payload["observations"]["mock_only"] is True
    assert payload["observations"]["sent_to_netapp"] is False
    assert payload["observation_summary"]["status"] == "not_recorded"
    assert payload["observation_summary"]["required_check_count"] == 6
    assert payload["observation_summary"]["optional_check_count"] == 1
    assert payload["observation_blockers"]
    assert not any("Controller B console" in blocker for blocker in payload["observation_blockers"])
    disabled_actions = {action["label"]: action for action in payload["disabled_actions"]}
    assert set(disabled_actions) >= {
        "Open Console",
        "Send Console Commands",
        "Interrupt Boot",
        "Configure SP IP",
        "Create Cluster",
        "Join Controller",
        "Configure Cluster Management",
        "Configure Node Management",
        "Configure SVM",
        "Configure LIFs",
        "Reboot Controller",
        "Wipe Disks",
    }
    assert all(action["enabled"] is False for action in disabled_actions.values())
    assert not _contains_forbidden_plan_preview_key(payload)


def test_netapp_observations_default_state_is_mock_only_and_redacted(
    client: TestClient,
) -> None:
    reset_netapp_observations()

    response = client.get("/api/v1/providers/netapp-ontap/observations")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "netapp-ontap"
    assert payload["observed_console_state"] == "unknown"
    assert payload["controller_a_console_seen"] is False
    assert payload["controller_b_console_seen"] is False
    assert payload["controller_a_sp_cabled"] is False
    assert payload["controller_b_sp_cabled"] is False
    assert payload["management_network_reviewed"] is False
    assert payload["planned_targets_reviewed"] is False
    assert payload["existing_data_risk_acknowledged"] is False
    assert payload["operator_notes"] == ""
    assert payload["updated_at"]
    assert payload["updated_by"] == "system"
    assert payload["mock_only"] is True
    assert payload["sent_to_netapp"] is False
    assert not _contains_forbidden_plan_preview_key(payload)


def test_netapp_observations_save_and_console_readiness_reflect_saved_values(
    client: TestClient,
) -> None:
    reset_netapp_observations()
    payload = {
        "observed_console_state": "cluster_setup_prompt",
        "controller_a_console_seen": True,
        "controller_b_console_seen": False,
        "controller_a_sp_cabled": True,
        "controller_b_sp_cabled": True,
        "management_network_reviewed": True,
        "planned_targets_reviewed": True,
        "existing_data_risk_acknowledged": True,
        "operator_notes": "Controller A showed cluster setup prompt. Controller B not yet viewed.",
    }

    response = client.put(
        "/api/v1/providers/netapp-ontap/observations",
        json=payload,
        headers={"X-Mock-User": "netapp-operator"},
    )

    assert response.status_code == 200
    saved = response.json()
    assert saved["observed_console_state"] == "cluster_setup_prompt"
    assert saved["operator_notes"] == payload["operator_notes"]
    assert saved["updated_by"] == "netapp-operator"
    assert saved["mock_only"] is True
    assert saved["sent_to_netapp"] is False
    assert not _contains_forbidden_plan_preview_key(saved)

    readback = client.get("/api/v1/providers/netapp-ontap/observations").json()
    assert readback["observed_console_state"] == "cluster_setup_prompt"
    assert readback["operator_notes"] == payload["operator_notes"]

    readiness = client.get("/api/v1/providers/netapp-ontap/console-readiness").json()
    assert readiness["observations"]["observed_console_state"] == "cluster_setup_prompt"
    assert readiness["observation_summary"]["completed_check_count"] == 6
    assert readiness["observation_summary"]["completed_optional_check_count"] == 0
    assert readiness["observation_summary"]["missing_optional_checks"] == [
        "controller_b_console_seen"
    ]
    assert readiness["observation_blockers"] == []
    assert not _contains_forbidden_plan_preview_key(readiness)


def test_netapp_observations_reject_long_notes_and_secret_shaped_keys(
    client: TestClient,
) -> None:
    reset_netapp_observations()
    valid_payload = {
        "observed_console_state": "unknown",
        "controller_a_console_seen": False,
        "controller_b_console_seen": False,
        "controller_a_sp_cabled": False,
        "controller_b_sp_cabled": False,
        "management_network_reviewed": False,
        "planned_targets_reviewed": False,
        "existing_data_risk_acknowledged": False,
        "operator_notes": "",
    }

    long_notes = {**valid_payload, "operator_notes": "x" * 1201}
    long_response = client.put("/api/v1/providers/netapp-ontap/observations", json=long_notes)
    assert long_response.status_code == 422

    secret_key_payload = {**valid_payload, "password": "do-not-store"}
    secret_response = client.put(
        "/api/v1/providers/netapp-ontap/observations",
        json=secret_key_payload,
    )
    assert secret_response.status_code == 422

    secret_notes_payload = {
        **valid_payload,
        "operator_notes": "Observed prompt but password was pasted by mistake.",
    }
    secret_notes_response = client.put(
        "/api/v1/providers/netapp-ontap/observations",
        json=secret_notes_payload,
    )
    assert secret_notes_response.status_code == 422

    readback = client.get("/api/v1/providers/netapp-ontap/observations").json()
    assert readback["operator_notes"] == ""
    assert not _contains_forbidden_plan_preview_key(readback)


def test_netapp_observation_service_rejects_secret_shaped_notes() -> None:
    reset_netapp_observations()

    with pytest.raises(ValueError, match="operator_notes must not include"):
        save_netapp_observations(
            {"operator_notes": "token pasted accidentally"},
            updated_by="unit-test",
        )

    assert save_netapp_observations(
        {"operator_notes": "Manual prompt reviewed."},
        updated_by="unit-test",
    )["operator_notes"] == "Manual prompt reviewed."


def test_netapp_readiness_comparison_defaults_to_manual_unknowns_and_redacts(
    client: TestClient,
) -> None:
    reset_netapp_observations()

    response = client.get("/api/v1/providers/netapp-ontap/readiness-comparison")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "netapp-ontap"
    assert payload["mode"] == "mock"
    assert payload["comparison_enabled"] is True
    assert payload["apply_enabled"] is False
    assert payload["discovery_enabled"] is False
    assert payload["planned_targets"]["sp_ips"] == {
        "controller_a": "10.10.8.13",
        "controller_b": "10.10.8.14",
    }
    assert payload["planned_targets"]["management_ips"] == {
        "cluster": "10.10.8.45",
        "node_a": "10.10.8.46",
        "node_b": "10.10.8.47",
        "svm": "10.10.8.48",
    }
    assert payload["planned_targets"]["iscsi_lif_range"]["addresses"] == [
        "10.10.8.51",
        "10.10.8.52",
        "10.10.8.53",
        "10.10.8.54",
    ]
    assert payload["current_discovered_targets"]["discovery_enabled"] is False
    assert payload["current_discovered_targets"]["management_ips"]["cluster"] is None
    assert payload["observations"]["observed_console_state"] == "unknown"
    assert payload["observations"]["mock_only"] is True
    assert payload["observations"]["sent_to_netapp"] is False
    assert payload["comparison_items"]
    statuses = {item["id"]: item["status"] for item in payload["comparison_items"]}
    assert statuses["cluster-management-not-configured"] == "blocker"
    assert statuses["node-management-not-configured"] == "blocker"
    assert statuses["svm-management-planned-not-live"] == "blocker"
    assert statuses["iscsi-lif-range-planned-not-live"] == "blocker"
    assert statuses["controller-a-sp-cabling"] == "unknown"
    assert statuses["controller-b-sp-cabling"] == "unknown"
    assert statuses["controller-a-console"] == "unknown"
    assert statuses["controller-b-console"] == "warning"
    assert statuses["management-network-review"] == "unknown"
    assert statuses["existing-data-risk"] == "blocker"
    assert statuses["console-state"] == "unknown"
    assert payload["matched_items"] == []
    assert payload["unknown_items"]
    assert [item["id"] for item in payload["warning_items"]] == ["controller-b-console"]
    assert [item["id"] for item in payload["blocker_items"]] == [
        "cluster-management-not-configured",
        "node-management-not-configured",
        "svm-management-planned-not-live",
        "iscsi-lif-range-planned-not-live",
        "existing-data-risk",
    ]
    assert any("Controller A SP cabling" in warning for warning in payload["removable_warnings"])
    assert any("Controller B console state" in warning for warning in payload["warnings"])
    assert any("system is new/factory" in blocker for blocker in payload["blockers"])
    assert any("Live NetApp discovery is disabled" in blocker for blocker in payload["blockers"])
    disabled_actions = {action["label"]: action for action in payload["disabled_actions"]}
    assert set(disabled_actions) >= {
        "Discover Live State",
        "Open Console",
        "Send Console Commands",
        "Probe Service Processor",
        "Probe ONTAP API",
        "Create Cluster",
        "Change IPs",
        "Create SVM",
        "Create LIFs",
        "Create Volumes",
        "Upgrade ONTAP",
        "Reboot Controller",
        "Wipe Disks",
        "Apply Configuration",
    }
    assert all(action["enabled"] is False for action in disabled_actions.values())
    assert not _contains_forbidden_plan_preview_key(payload)


def test_netapp_readiness_comparison_reflects_saved_observations(
    client: TestClient,
) -> None:
    reset_netapp_observations()
    client.put(
        "/api/v1/providers/netapp-ontap/observations",
        json={
            "observed_console_state": "cluster_setup_prompt",
            "controller_a_console_seen": True,
            "controller_b_console_seen": True,
            "controller_a_sp_cabled": True,
            "controller_b_sp_cabled": True,
            "management_network_reviewed": True,
            "planned_targets_reviewed": True,
            "existing_data_risk_acknowledged": True,
            "operator_notes": "Manual checks reviewed.",
        },
    )

    response = client.get("/api/v1/providers/netapp-ontap/readiness-comparison")

    assert response.status_code == 200
    payload = response.json()
    statuses = {item["id"]: item["status"] for item in payload["comparison_items"]}
    assert statuses == {
        "cluster-management-not-configured": "blocker",
        "node-management-not-configured": "blocker",
        "svm-management-planned-not-live": "blocker",
        "iscsi-lif-range-planned-not-live": "blocker",
        "controller-a-sp-cabling": "matched",
        "controller-b-sp-cabling": "matched",
        "controller-a-console": "matched",
        "controller-b-console": "matched",
        "management-network-review": "matched",
        "planned-target-review": "matched",
        "existing-data-risk": "matched",
        "console-state": "matched",
    }
    assert len(payload["matched_items"]) == len(payload["comparison_items"]) - 4
    assert payload["unknown_items"] == []
    assert payload["warning_items"] == []
    assert [item["id"] for item in payload["blocker_items"]] == [
        "cluster-management-not-configured",
        "node-management-not-configured",
        "svm-management-planned-not-live",
        "iscsi-lif-range-planned-not-live",
    ]
    assert payload["removable_warnings"] == []
    assert payload["observations"]["observed_console_state"] == "cluster_setup_prompt"
    assert not _contains_forbidden_plan_preview_key(payload)


def test_netapp_ontap_artifacts_endpoint_returns_mock_placeholder_and_redacts(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/netapp-ontap/artifacts")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    artifact = payload[0]
    assert artifact["provider_id"] == "netapp-ontap"
    assert artifact["kind"] == "netapp_plan_preview"
    assert artifact["title"] == "NetApp ONTAP Plan Preview"
    assert artifact["status"] == "available_preview"
    assert artifact["mock_only"] is True
    assert artifact["redacted"] is True
    assert artifact["downloadable"] is False
    assert artifact["download_url"] is None
    assert artifact["generated_at"]
    assert artifact["metadata"] == {
        "source_endpoint": "/api/v1/providers/netapp-ontap/plan-preview",
        "apply_enabled": False,
        "includes_planned_targets": True,
        "includes_readiness": True,
        "includes_intent_preview": True,
        "includes_disabled_actions": True,
        "no_ontap_calls": True,
    }
    assert not _contains_forbidden_plan_preview_key(payload)


def test_provider_artifacts_endpoint_aggregates_netapp_placeholder_and_redacts(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/providers/artifacts")

    assert response.status_code == 200
    payload = response.json()
    artifact = next(
        item
        for item in payload
        if item["provider_id"] == "netapp-ontap" and item["kind"] == "netapp_plan_preview"
    )
    assert artifact["title"] == "NetApp ONTAP Plan Preview"
    assert artifact["mock_only"] is True
    assert artifact["redacted"] is True
    assert artifact["downloadable"] is False
    assert artifact["download_url"] is None
    assert artifact["metadata"]["source_endpoint"] == "/api/v1/providers/netapp-ontap/plan-preview"
    assert artifact["metadata"]["no_ontap_calls"] is True
    assert not _contains_forbidden_plan_preview_key(payload)


def _contains_sensitive_key(value: object) -> bool:
    sensitive_fragments = ("password", "token", "secret")
    if isinstance(value, dict):
        return any(
            any(fragment in str(key).lower() for fragment in sensitive_fragments)
            or _contains_sensitive_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _contains_forbidden_plan_preview_key(value: object) -> bool:
    forbidden_fragments = (
        "password",
        "secret",
        "token",
        "credential",
        "authorization",
        "cookie",
    )
    if isinstance(value, dict):
        return any(
            any(fragment in str(key).lower() for fragment in forbidden_fragments)
            or _contains_forbidden_plan_preview_key(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_plan_preview_key(item) for item in value)
    return False


def test_provider_registry_rejects_non_mock_mode() -> None:
    registry = provider_registry("real")

    with pytest.raises(ProviderRegistryError, match="Provider status supports only"):
        registry.statuses()


def test_local_real_lab_file_does_not_set_provider_mode(tmp_path: Path) -> None:
    (tmp_path / ".env.local.real-lab").write_text(
        "PROVIDER_MODE=local-readonly\nILO_TEST_HOST=example.invalid\n",
        encoding="utf-8",
    )
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for key in ("PROVIDER_MODE", "ILO_TEST_HOST"):
        env.pop(key, None)
    env["PYTHONPATH"] = str(backend_dir)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.config import settings; "
                "print(settings.provider_mode); "
                "print(bool(settings.ilo_test_host))"
            ),
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert completed.stdout.splitlines() == ["mock", "True"]


def test_explicit_provider_mode_env_wins_over_mock_default(tmp_path: Path) -> None:
    (tmp_path / ".env.local.real-lab").write_text(
        "PROVIDER_MODE=mock\n",
        encoding="utf-8",
    )
    backend_dir = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir)
    env["PROVIDER_MODE"] = "local-readonly"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.core.config import settings; print(settings.provider_mode)",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert completed.stdout.strip() == "local-readonly"


def test_local_readonly_registry_keeps_vm_lifecycle_mock_backed() -> None:
    registry = provider_registry("local-readonly")

    assert registry.vsphere().health().id == "mock-vsphere"
    assert registry.source_of_truth().catalog()["environments"]


def test_provider_status_endpoint_normalizes_registry_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_registry() -> None:
        raise ProviderRegistryError("Provider mode 'real' is not available.")

    monkeypatch.setattr("app.api.routes.provider_registry", fail_registry)

    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "provider-registry"
    assert payload[0]["status"] == "blocked"
    assert "Provider mode 'real'" in payload[0]["blockers"][0]


def test_provider_probe_endpoint_normalizes_adapter_errors(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_probe(self) -> dict:  # noqa: ARG001
        raise RuntimeError("secret endpoint detail")

    monkeypatch.setattr("app.api.routes.IloRedfishAdapter.probe", fail_probe)

    response = client.post("/api/v1/providers/ilo-redfish/probe")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "ilo-redfish"
    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["Provider probe failed: RuntimeError."]
    assert "secret endpoint detail" not in str(payload)
