from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.providers.registry import ProviderRegistryError, provider_registry


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
        "endpoint_configured": True,
        "username_configured": False,
        "credential_configured": False,
        "tls_verify": True,
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
    assert readiness["sp_readiness"]["status"] == "planned"
    assert readiness["cluster_management_readiness"]["status"] == "planned"
    assert readiness["node_management_readiness"]["status"] == "planned"
    assert readiness["svm_readiness"]["status"] == "planned"
    assert readiness["ontap_api_readiness"]["status"] == "blocked_until_configured"
    assert readiness["ontap_api_readiness"]["configured"] is False
    assert readiness["console_bootstrap_readiness"]["status"] == "manual_placeholder"
    assert readiness["upgrade_readiness_path"]["status"] == "preview_only"
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
        "endpoint_configured": True,
        "username_configured": False,
        "access_configured": False,
        "tls_verify": True,
    }
    readiness = payload["readiness_buckets"]
    assert readiness["sp_readiness"]["status"] == "planned"
    assert readiness["ontap_api_readiness"]["status"] == "blocked_until_configured"
    assert readiness["storage_iscsi_plan_preview"]["status"] == "preview_only"
    assert readiness["reports_artifacts"]["status"] == "placeholder"
    assert payload["cluster_intent_preview"]["management_ip"] == "10.10.8.45"
    assert payload["svm_intent_preview"]["management_ip"] == "10.10.8.48"
    assert len(payload["lif_intent_preview"]["iscsi_lifs"]) == 4
    assert payload["storage_iscsi_plan_preview"]["status"] == "placeholder"
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
