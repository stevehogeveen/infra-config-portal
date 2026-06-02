from __future__ import annotations

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
