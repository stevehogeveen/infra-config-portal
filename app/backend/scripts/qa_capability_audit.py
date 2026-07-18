from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "app"
OUTPUT_PATH = REPO_ROOT / "artifacts" / "codex-runs" / "qa-capability-audit.json"
SCHEMA_VERSION = "qa-capability-audit/v1"

from app.services.json_file_store import write_json_object  # noqa: E402
from app.services.path_utils import display_path, safe_read_text  # noqa: E402


CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "tiered-fast-verification",
        "requirement": "Diff-aware fast verification with inspectable plan and failure packet handoff.",
        "checks": (
            ("app/scripts/fast-verify.ps1", ("fast-verify-plan.json", "step_details", "New-FailurePacket")),
            ("app/docs/testing-acceleration.md", ("fast-verify.ps1", "WhatIfOnly")),
        ),
    },
    {
        "id": "hardware-smoke-lane",
        "requirement": "Real-lab smoke verification is explicit, previewable, and separated from destructive actions.",
        "checks": (
            ("app/scripts/hardware-smoke.ps1", ("hardware-smoke-plan/v1", "WhatIfOnly", "AllowWriteMode")),
            ("app/docs/testing-acceleration.md", ("hardware-smoke.ps1", "local-lab-readwrite")),
        ),
    },
    {
        "id": "frontend-component-lane",
        "requirement": "Fast component/server-render checks absorb UI assertions that do not need a browser.",
        "checks": (
            ("app/frontend/package.json", ("test:component", "component-test.mjs")),
            ("app/frontend/scripts/component-test.mjs", ("component.test.tsx", "esbuild")),
            ("app/frontend/src/components/ui/ui-components.component.test.tsx", ("StatusBadge", "RemediationLadder")),
            ("app/scripts/fast-verify.ps1", ("frontend-component-tests", "npm run test:component")),
        ),
    },
    {
        "id": "generated-api-contract",
        "requirement": "Generated API/registry contract checks catch stale workflow endpoint wiring.",
        "checks": (
            ("app/backend/scripts/openapi_contract_probe.py", ("openapi-contract-probe/v1", "workflow-api-endpoint")),
            ("app/backend/tests/test_openapi_contract_probe.py", ("missing OpenAPI path", "matches_openapi_path_templates")),
            ("app/scripts/fast-verify.ps1", ("backend-openapi-contract", "openapi_contract_probe.py")),
        ),
    },
    {
        "id": "generated-property-tests",
        "requirement": "Generated or matrix-style tests cover combinatorial topology and scenario invariants.",
        "checks": (
            ("app/backend/tests/test_topology_design_drafts.py", ("generated", "scenario", "hardware")),
            ("app/docs/testing-acceleration.md", ("generated scenario/subnet matrices", "Property examples")),
        ),
    },
    {
        "id": "visual-regression",
        "requirement": "Stable visual product surfaces have screenshot regression coverage.",
        "checks": (
            ("app/frontend/tests/safe-action-runner.spec.ts", ("overview design mode map surface stays stable and scalable", "toHaveScreenshot")),
            (
                "app/frontend/tests/safe-action-runner.spec.ts-snapshots/overview-design-map-chromium-win32.png",
                (),
            ),
        ),
    },
    {
        "id": "ci-ready-gates",
        "requirement": "CI runs Linux, Windows, and fast-verify gates and uploads QA artifacts.",
        "checks": (
            (".github/workflows/ci.yml", ("Linux Make Gate", "Windows PowerShell Gate", "Windows Fast Verify Gate")),
            (".github/workflows/ci.yml", ("fast-verify-plan.json", "qa-failure-packets", "openapi-contract-probe.json")),
        ),
    },
    {
        "id": "advisory-ai-triage",
        "requirement": "AI-ready failure diagnosis is advisory-only, redacted, and safe-command constrained.",
        "checks": (
            ("app/backend/scripts/qa_failure_packet.py", ("qa-failure-packet/v1", "advisory-triage/v1", "redact_sensitive")),
            ("app/backend/tests/test_qa_failure_packet.py", ("unsafe token", "external AI/API calls")),
            (
                "app/frontend/tests/safe-action-runner.spec.ts",
                ("Advisory diagnosis", "Diagnosis is advisory and does not execute workflow actions."),
            ),
        ),
    },
    {
        "id": "aggregate-artifact-health",
        "requirement": "Local QA artifacts have one aggregate contract validator.",
        "checks": (
            ("app/scripts/qa-artifact-health.ps1", ("qa-artifact-health/v1", "fast-verify-plan", "openapi-contract-probe")),
            ("app/backend/tests/test_windows_scripts.py", ("qa-artifact-health", "openapi-contract-probe.json")),
        ),
    },
    {
        "id": "guarded-execution-safety",
        "requirement": "Verification helpers avoid write/destructive/hardware execution unless explicitly operator-triggered.",
        "checks": (
            ("app/scripts/fast-verify.ps1", ("step detail command contains unsafe token", "Hardware smoke is intentionally separate")),
            ("app/scripts/qa-artifact-health.ps1", ("does not run tests", "provider probes", "external AI calls")),
            ("app/backend/scripts/openapi_contract_probe.py", ("does not call API endpoints", "Guarded workflow actions")),
        ),
    },
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Lab Builder QA acceleration capabilities.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Audit artifact path.")
    parser.add_argument("--validate", default="", help="Validate an existing audit artifact instead of creating one.")
    args = parser.parse_args()

    if args.validate:
        result = validate_qa_capability_audit_path(Path(args.validate))
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 2

    audit = create_qa_capability_audit()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit["artifact"] = display_path(output_path, REPO_ROOT)
    write_json_object(output_path, audit)
    print(json.dumps(audit, indent=2))
    return 0 if audit["valid"] else 2


def create_qa_capability_audit() -> dict[str, Any]:
    capabilities = [_capability_result(spec) for spec in CAPABILITIES]
    missing = [capability for capability in capabilities if not capability["satisfied"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "valid": not missing,
        "capabilities": capabilities,
        "summary": {
            "satisfied": len(capabilities) - len(missing),
            "total": len(capabilities),
            "missing": [capability["id"] for capability in missing],
        },
        "safety_notes": [
            "This audit inspects local files and artifact contracts only.",
            "It does not run tests, API endpoints, workflow actions, provider probes, hardware commands, or external AI.",
            "A satisfied capability means its declared evidence markers are present; full goal completion still requires full gate evidence.",
        ],
    }


def validate_qa_capability_audit_path(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"valid": False, "artifact": display_path(path, REPO_ROOT), "errors": ["audit artifact not found"]}
    except json.JSONDecodeError as exc:
        return {"valid": False, "artifact": display_path(path, REPO_ROOT), "errors": [f"audit JSON is invalid: {exc}"]}
    result = validate_qa_capability_audit(payload)
    result["artifact"] = display_path(path, REPO_ROOT)
    return result


def validate_qa_capability_audit(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("valid") is not True:
        errors.append("audit artifact records valid=false")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        errors.append("capabilities must be a non-empty list")
    else:
        expected_ids = {spec["id"] for spec in CAPABILITIES}
        actual_ids = {str(item.get("id") or "") for item in capabilities if isinstance(item, dict)}
        missing_ids = sorted(expected_ids - actual_ids)
        if missing_ids:
            errors.append(f"capabilities missing ids: {', '.join(missing_ids)}")
        for item in capabilities:
            if not isinstance(item, dict):
                errors.append("capability entries must be objects")
                continue
            if item.get("satisfied") is not True:
                errors.append(f"capability {item.get('id') or '<unknown>'} is not satisfied")
            evidence = item.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"capability {item.get('id') or '<unknown>'} has no evidence")
    if not isinstance(payload.get("safety_notes"), list) or not payload.get("safety_notes"):
        errors.append("safety_notes must be a non-empty list")
    if payload.get("errors"):
        errors.extend(str(error) for error in payload.get("errors", []))
    return {
        "valid": not errors,
        "schema_version": payload.get("schema_version"),
        "errors": errors,
    }


def _capability_result(spec: dict[str, Any]) -> dict[str, Any]:
    evidence = [_evidence_result(path, markers) for path, markers in spec["checks"]]
    missing = [
        item
        for item in evidence
        if not item["exists"] or item["missing_markers"]
    ]
    return {
        "id": spec["id"],
        "requirement": spec["requirement"],
        "satisfied": not missing,
        "evidence": evidence,
    }


def _evidence_result(relative_path: str, markers: Iterable[str]) -> dict[str, Any]:
    path = REPO_ROOT / relative_path
    text = safe_read_text(path, default="")
    marker_list = list(markers)
    missing_markers = [marker for marker in marker_list if marker not in text]
    return {
        "path": relative_path,
        "exists": path.is_file(),
        "markers": marker_list,
        "missing_markers": missing_markers if path.is_file() else marker_list,
    }


if __name__ == "__main__":
    raise SystemExit(main())
