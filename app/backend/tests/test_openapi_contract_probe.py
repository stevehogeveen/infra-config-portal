from __future__ import annotations

import json

from scripts import openapi_contract_probe


def test_openapi_contract_probe_generates_registry_cases_without_running_actions() -> None:
    result = openapi_contract_probe.probe_openapi_contract()

    assert result["schema_version"] == "openapi-contract-probe/v1"
    assert result["valid"] is True
    assert result["openapi"]["operation_count"] > 20
    assert any(
        case["kind"] == "workflow-api-endpoint" and case["action_id"] == "netapp.setup-apply"
        for case in result["generated_cases"]
    )
    assert any(
        case["kind"] == "guarded-workflow-action"
        and case["action_id"] == "raid.apply"
        and case["required_confirmation_count"] >= 1
        for case in result["generated_cases"]
    )
    assert "does not call API endpoints" in " ".join(result["safety_notes"])


def test_openapi_contract_probe_validation_rejects_failed_or_malformed_artifact(tmp_path) -> None:
    artifact = tmp_path / "openapi-contract-probe.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "openapi-contract-probe/v1",
                "valid": False,
                "openapi": {"operation_count": 0},
                "generated_cases": [],
                "errors": ["workflow action test points at missing OpenAPI path /api/v1/missing"],
                "safety_notes": [],
            }
        ),
        encoding="utf-8",
    )

    result = openapi_contract_probe.validate_openapi_contract_probe_path(artifact)

    assert result["valid"] is False
    assert "probe artifact records valid=false" in result["errors"]
    assert "openapi.operation_count must be present and positive" in result["errors"]
    assert "safety_notes must be a non-empty list" in result["errors"]
    assert any("missing OpenAPI path" in error for error in result["errors"])


def test_registry_contract_generation_flags_missing_endpoint_and_missing_guard() -> None:
    errors, cases = openapi_contract_probe._registry_errors(
        [
            {
                "action_id": "danger.apply",
                "mode": "write",
                "api_endpoint": "/api/v1/missing",
                "api_method": "POST",
                "required_gates": [],
                "required_confirmations": [],
            }
        ],
        {"/api/v1/known": {"GET"}},
    )

    assert any("missing OpenAPI path /api/v1/missing" in error for error in errors)
    assert any("has no required gates or confirmations" in error for error in errors)
    assert {case["kind"] for case in cases} == {"workflow-api-endpoint", "guarded-workflow-action"}


def test_registry_contract_generation_matches_openapi_path_templates() -> None:
    errors, cases = openapi_contract_probe._registry_errors(
        [
            {
                "action_id": "cisco.ssh-readonly-probe",
                "mode": "read_only",
                "api_endpoint": "/api/v1/providers/cisco-ansible/probe",
                "api_method": "POST",
            }
        ],
        {"/api/v1/providers/{provider_id}/probe": {"POST"}},
    )

    assert errors == []
    assert cases[0]["path"] == "/api/v1/providers/cisco-ansible/probe"
