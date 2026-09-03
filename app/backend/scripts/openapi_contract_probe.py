from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_PATH = REPO_ROOT / "artifacts" / "codex-runs" / "openapi-contract-probe.json"
SCHEMA_VERSION = "openapi-contract-probe/v1"
GUARDED_MODES = {"write", "destructive", "upgrade"}
ALLOWED_NON_API_PATHS = {"/health"}

from app.main import app  # noqa: E402
from app.services.json_file_store import write_json_object  # noqa: E402
from app.services.path_utils import display_path  # noqa: E402
from app.services.workflow_registry import list_workflow_actions  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate and validate API contract checks from FastAPI OpenAPI plus the "
            "workflow registry."
        )
    )
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Probe artifact path.")
    parser.add_argument("--validate", default="", help="Validate an existing probe JSON artifact.")
    args = parser.parse_args()

    if args.validate:
        result = validate_openapi_contract_probe_path(Path(args.validate))
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 2

    result = probe_openapi_contract()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result["artifact"] = display_path(output_path, REPO_ROOT)
    write_json_object(output_path, result)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 2


def probe_openapi_contract() -> dict[str, Any]:
    schema = app.openapi()
    paths = schema.get("paths") if isinstance(schema.get("paths"), dict) else {}
    path_methods = _path_methods(paths)
    actions = list_workflow_actions()
    operation_errors = _operation_errors(paths)
    registry_errors, generated_cases = _registry_errors(actions, path_methods)
    errors = [*operation_errors, *registry_errors]

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "valid": not errors,
        "openapi": {
            "title": schema.get("info", {}).get("title"),
            "version": schema.get("openapi"),
            "path_count": len(paths),
            "operation_count": sum(len(methods) for methods in path_methods.values()),
        },
        "generated_cases": generated_cases,
        "errors": errors,
        "safety_notes": [
            "This probe reads FastAPI OpenAPI and workflow registry metadata only.",
            "It does not call API endpoints, run workflow actions, touch hardware, or call external AI.",
            "Guarded workflow actions must keep required gates or confirmations in registry metadata.",
        ],
    }


def validate_openapi_contract_probe_path(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"valid": False, "artifact": display_path(path, REPO_ROOT), "errors": ["probe artifact not found"]}
    except json.JSONDecodeError as exc:
        return {"valid": False, "artifact": display_path(path, REPO_ROOT), "errors": [f"probe JSON is invalid: {exc}"]}
    result = validate_openapi_contract_probe(payload)
    result["artifact"] = display_path(path, REPO_ROOT)
    return result


def validate_openapi_contract_probe(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if payload.get("valid") is not True:
        errors.append("probe artifact records valid=false")
    if not isinstance(payload.get("generated_cases"), list):
        errors.append("generated_cases must be a list")
    if not isinstance(payload.get("safety_notes"), list) or not payload.get("safety_notes"):
        errors.append("safety_notes must be a non-empty list")
    openapi = payload.get("openapi")
    if not isinstance(openapi, dict) or int(openapi.get("operation_count") or 0) < 1:
        errors.append("openapi.operation_count must be present and positive")
    if payload.get("errors"):
        errors.extend(str(error) for error in payload.get("errors", []))
    return {
        "valid": not errors,
        "schema_version": payload.get("schema_version"),
        "errors": errors,
    }


def _path_methods(paths: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        result[path] = {
            method.upper()
            for method in methods
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        }
    return result


def _operation_errors(paths: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    operation_ids: dict[str, str] = {}
    for path, methods in paths.items():
        if not path.startswith("/api/v1") and path not in ALLOWED_NON_API_PATHS:
            errors.append(f"OpenAPI path is outside /api/v1: {path}")
        if not isinstance(methods, dict):
            errors.append(f"OpenAPI path methods are malformed for {path}")
            continue
        for method, operation in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                errors.append(f"OpenAPI operation is malformed for {method.upper()} {path}")
                continue
            operation_id = str(operation.get("operationId") or "").strip()
            if not operation_id:
                errors.append(f"operationId is missing for {method.upper()} {path}")
                continue
            previous = operation_ids.get(operation_id)
            if previous:
                errors.append(f"operationId {operation_id} is duplicated by {previous} and {method.upper()} {path}")
            operation_ids[operation_id] = f"{method.upper()} {path}"
    return errors


def _registry_errors(
    actions: list[dict[str, Any]],
    path_methods: dict[str, set[str]],
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    generated_cases: list[dict[str, Any]] = []
    action_ids: set[str] = set()
    for action in actions:
        action_id = str(action.get("action_id") or "").strip()
        if not action_id:
            errors.append("workflow action is missing action_id")
            continue
        if action_id in action_ids:
            errors.append(f"workflow action_id is duplicated: {action_id}")
        action_ids.add(action_id)

        mode = str(action.get("mode") or "")
        endpoint = str(action.get("api_endpoint") or "").strip()
        method = str(action.get("api_method") or "GET").upper()
        if endpoint:
            generated_cases.append(
                {
                    "kind": "workflow-api-endpoint",
                    "action_id": action_id,
                    "mode": mode,
                    "method": method,
                    "path": endpoint,
                }
            )
            matched_methods = _methods_for_endpoint(endpoint, path_methods)
            if not matched_methods:
                errors.append(f"workflow action {action_id} points at missing OpenAPI path {endpoint}")
            elif method not in matched_methods:
                available = ", ".join(sorted(matched_methods))
                errors.append(
                    f"workflow action {action_id} expects {method} {endpoint}; OpenAPI has {available}"
                )

        if mode in GUARDED_MODES:
            gates = action.get("required_gates") if isinstance(action.get("required_gates"), list) else []
            confirmations = (
                action.get("required_confirmations")
                if isinstance(action.get("required_confirmations"), list)
                else []
            )
            if not gates and not confirmations:
                errors.append(f"guarded workflow action {action_id} has no required gates or confirmations")
            generated_cases.append(
                {
                    "kind": "guarded-workflow-action",
                    "action_id": action_id,
                    "mode": mode,
                    "required_gate_count": len(gates),
                    "required_confirmation_count": len(confirmations),
                }
            )
    return errors, generated_cases


def _methods_for_endpoint(endpoint: str, path_methods: dict[str, set[str]]) -> set[str]:
    direct = path_methods.get(endpoint)
    if direct is not None:
        return direct
    for template, methods in path_methods.items():
        if _path_template_matches(template, endpoint):
            return methods
    return set()


def _path_template_matches(template: str, endpoint: str) -> bool:
    pattern_parts = []
    for part in template.strip("/").split("/"):
        if part.startswith("{") and part.endswith("}"):
            pattern_parts.append(r"[^/]+")
        else:
            pattern_parts.append(re.escape(part))
    pattern = "^/" + "/".join(pattern_parts) + "$"
    return re.match(pattern, endpoint) is not None


if __name__ == "__main__":
    raise SystemExit(main())
