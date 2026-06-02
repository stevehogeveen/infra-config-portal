from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import VMDeploymentCreate


def test_vm_request_accepts_required_mvp_fields(vm_payload: dict) -> None:
    payload = VMDeploymentCreate.model_validate(vm_payload)

    assert payload.vm_name == "app-dev-001"
    assert payload.memory_gb == 8
    assert payload.storage_tier == "silver"


def test_vm_request_accepts_memory_alias(vm_payload: dict) -> None:
    vm_payload.pop("memory_gb")
    vm_payload["memory"] = 16

    payload = VMDeploymentCreate.model_validate(vm_payload)

    assert payload.memory_gb == 16


def test_vm_request_requires_storage_target(vm_payload: dict) -> None:
    vm_payload.pop("storage_tier")
    vm_payload["datastore"] = None

    with pytest.raises(ValidationError) as exc:
        VMDeploymentCreate.model_validate(vm_payload)

    assert "datastore or storage_tier is required" in str(exc.value)


def test_vm_request_rejects_unsafe_vm_name(vm_payload: dict) -> None:
    vm_payload["vm_name"] = "bad name; rm -rf"

    with pytest.raises(ValidationError) as exc:
        VMDeploymentCreate.model_validate(vm_payload)

    assert "vm_name" in str(exc.value)


def test_vm_request_requires_future_expiry(vm_payload: dict) -> None:
    vm_payload["expiry_date"] = (date.today() - timedelta(days=1)).isoformat()

    with pytest.raises(ValidationError) as exc:
        VMDeploymentCreate.model_validate(vm_payload)

    assert "expiry_date must be in the future" in str(exc.value)
