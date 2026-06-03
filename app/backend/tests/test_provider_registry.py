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
    assert {"ilo-redfish", "cisco-console", "mock-vsphere"}.issubset(ids)
    assert all(provider["mode"] == "mock" for provider in payload)
    assert all("disabled_actions" in provider for provider in payload)


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
