from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services.lab_validation import (
    build_cisco_validation_item,
    get_lab_validation_summary,
    map_validation_status,
)
from app.services import vcenter_netapp_readiness


def test_validation_item_status_mapping() -> None:
    assert map_validation_status(ready=True) == "ready"
    assert map_validation_status(blockers=["blocked"]) == "blocked"
    assert map_validation_status(configured=True, warnings=["warn"]) == "warning"
    assert map_validation_status(checked=False) == "not_checked"
    assert map_validation_status() == "not_configured"


def test_login_hints_do_not_include_secret_values() -> None:
    payload = get_lab_validation_summary(write_report=False)
    serialized = json.dumps(payload).lower()

    assert "password=" not in serialized
    assert "token=" not in serialized
    assert "bearer " not in serialized
    assert "private_key" not in serialized
    assert "credentials not configured" in serialized


def test_ready_cisco_shows_ssh_login_hint() -> None:
    item = build_cisco_validation_item(management_ready=True, target_ip="192.168.1.204")

    assert item["status"] == "ready"
    assert item["login_hint"] == "ssh admin@192.168.1.204"
    assert item["ssh_target"] == "admin@192.168.1.204"


def test_netapp_cluster_setup_wizard_blocks_vcenter_netapp_readiness(
    monkeypatch,
) -> None:
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _vcenter_netapp_settings())
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: "/usr/bin/govc")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {
            "configured": False,
            "configured_state": "setup_wizard",
            "console": {"prompt_state": "cluster_setup_prompt"},
        },
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness()

    assert result["status"] == "blocked_by_prior_stage"
    assert result["netapp_stage"] == "cluster_setup_wizard"
    assert any("cluster_setup_wizard" in blocker for blocker in result["blockers"])


def test_vcenter_not_configured_is_not_configured_yet(monkeypatch) -> None:
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _vcenter_netapp_settings(vcenter_host=None, vcenter_configured=False),
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: "/usr/bin/govc")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {"configured": True, "configured_state": "configured", "console": {}},
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness()

    assert result["status"] == "not_configured_yet"
    assert any("VCENTER_HOST" in blocker or "GOVC_URL" in blocker for blocker in result["blockers"])


def test_evidence_artifacts_are_collapsed_supporting_metadata() -> None:
    payload = get_lab_validation_summary(write_report=False)

    assert payload["validation_items"]
    assert all(item["evidence_collapsed_by_default"] is True for item in payload["validation_items"])
    assert "proof_links" in payload


def test_lab_validation_api_payload_shape(client: TestClient) -> None:
    response = client.get("/api/v1/lab/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"]
    assert "progress_counts" in payload
    assert "validation_items" in payload
    assert "proof_links" in payload
    assert "generated_at" in payload
    assert "next_action" in payload
    assert any(item["id"] == "vcenter-netapp-datastore" for item in payload["validation_items"])


def _vcenter_netapp_settings(**overrides):
    values = {
        "provider_mode": "mock",
        "vcenter_host": "https://vcenter.example/sdk",
        "vcenter_configured": True,
        "vcenter_username": "configured-user",
        "vcenter_password": "configured-password",
        "netapp_api_username": "configured-user",
        "netapp_api_password": "configured-password",
        "netapp_cluster_mgmt_ip": "192.168.1.220",
        "netapp_svm_mgmt_ip": "192.168.1.223",
        "netapp_nfs_lifs": ("192.168.1.230", "192.168.1.231"),
        "netapp_nfs_volume": "esxi_datastore_01",
        "netapp_nfs_export_policy": "esxi_nfs_policy",
        "netapp_nfs_mount_path": "/esxi_datastore_01",
        "netapp_nfs_datastore_name": "netapp_nfs_ds01",
        "netapp_nfs_client_match": "192.168.1.0/24",
        "esxi_test_host": "192.168.1.203",
    }
    values.update(overrides)
    return SimpleNamespace(**values)
