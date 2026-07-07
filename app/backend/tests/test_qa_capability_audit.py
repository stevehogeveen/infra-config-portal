from __future__ import annotations

import json

from scripts import qa_capability_audit


def test_qa_capability_audit_covers_goal_capabilities_without_running_actions() -> None:
    audit = qa_capability_audit.create_qa_capability_audit()

    assert audit["schema_version"] == "qa-capability-audit/v1"
    assert audit["valid"] is True
    capability_ids = {capability["id"] for capability in audit["capabilities"]}
    assert {
        "tiered-fast-verification",
        "hardware-smoke-lane",
        "frontend-component-lane",
        "generated-api-contract",
        "generated-property-tests",
        "visual-regression",
        "ci-ready-gates",
        "advisory-ai-triage",
        "aggregate-artifact-health",
        "guarded-execution-safety",
    }.issubset(capability_ids)
    assert audit["summary"]["satisfied"] == audit["summary"]["total"]
    assert "does not run tests" in " ".join(audit["safety_notes"])


def test_qa_capability_audit_validation_rejects_missing_capability(tmp_path) -> None:
    artifact = tmp_path / "qa-capability-audit.json"
    artifact.write_text(
        json.dumps(
            {
                "schema_version": "qa-capability-audit/v1",
                "valid": False,
                "capabilities": [
                    {
                        "id": "tiered-fast-verification",
                        "satisfied": False,
                        "evidence": [],
                    }
                ],
                "safety_notes": [],
                "errors": ["example failure"],
            }
        ),
        encoding="utf-8",
    )

    result = qa_capability_audit.validate_qa_capability_audit_path(artifact)

    assert result["valid"] is False
    assert "audit artifact records valid=false" in result["errors"]
    assert any("capabilities missing ids" in error for error in result["errors"])
    assert "capability tiered-fast-verification is not satisfied" in result["errors"]
    assert "safety_notes must be a non-empty list" in result["errors"]
    assert "example failure" in result["errors"]


def test_capability_result_reports_missing_marker(monkeypatch, tmp_path) -> None:
    repo_root = tmp_path
    marker_file = repo_root / "app" / "scripts" / "fast-verify.ps1"
    marker_file.parent.mkdir(parents=True)
    marker_file.write_text("fast-verify-plan.json", encoding="utf-8")
    monkeypatch.setattr(qa_capability_audit, "REPO_ROOT", repo_root)

    result = qa_capability_audit._capability_result(
        {
            "id": "sample",
            "requirement": "sample",
            "checks": (("app/scripts/fast-verify.ps1", ("fast-verify-plan.json", "step_details")),),
        }
    )

    assert result["satisfied"] is False
    assert result["evidence"][0]["missing_markers"] == ["step_details"]
