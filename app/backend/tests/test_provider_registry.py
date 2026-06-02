from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.providers.registry import ProviderRegistryError, provider_registry


def test_provider_status_endpoint_reports_mock_registry(client: TestClient) -> None:
    response = client.get("/api/v1/providers/status")

    assert response.status_code == 200
    payload = response.json()
    names = {provider["name"] for provider in payload}
    assert "Mock vSphere" in names
    assert "Mock NetBox/Nautobot" in names
    assert all(
        provider["mode"] in {"mock", "placeholder"}
        for provider in payload
    )


def test_provider_registry_rejects_non_mock_mode() -> None:
    registry = provider_registry("real")

    with pytest.raises(ProviderRegistryError, match="Only mock providers are registered"):
        registry.statuses()
