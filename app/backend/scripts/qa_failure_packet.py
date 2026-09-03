from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPO_ROOT / "app"
OUTPUT_DIR = REPO_ROOT / "artifacts" / "codex-runs" / "qa-failure-packets"
MAX_TEXT_CHARS = 12000
MAX_ARTIFACTS = 12
PACKET_SCHEMA_VERSION = "qa-failure-packet/v1"
TRIAGE_SCHEMA_VERSION = "advisory-triage/v1"
ALLOWED_TRIAGE_AREAS = {"backend-pytest", "frontend-playwright", "hardware-smoke", "workflow-action", "unknown"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
UNSAFE_COMMAND_TOKENS = (
    " -allowwritemode",
    " apply",
    " reset",
    " power",
    " destructive",
    " local-lab-readwrite",
    "factory-reset",
)

from app.providers.redaction import redact_sensitive  # noqa: E402
from app.services.json_file_store import write_json_object, write_text_value  # noqa: E402
from app.services.path_utils import display_path, path_mtime, safe_read_text  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a redacted AI-ready packet from recent pytest/Playwright/workflow failure evidence."
    )
    parser.add_argument("--note", default="", help="Operator note to include in the packet.")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR), help="Directory for packet JSON/Markdown.")
    parser.add_argument("--max-artifacts", type=int, default=MAX_ARTIFACTS, help="Maximum evidence files to include.")
    parser.add_argument("--validate", default="", help="Validate an existing packet JSON file instead of creating one.")
    parser.add_argument("--validate-latest", action="store_true", help="Validate latest.json under the output directory.")
    args = parser.parse_args()

    if args.validate or args.validate_latest:
        packet_path = Path(args.validate) if args.validate else Path(args.output_dir) / "latest.json"
        result = validate_qa_failure_packet_path(packet_path)
        print(json.dumps(result, indent=2))
        return 0 if result["valid"] else 2

    packet = create_qa_failure_packet(
        note=args.note,
        output_dir=Path(args.output_dir),
        max_artifacts=max(1, args.max_artifacts),
    )
    print(json.dumps({"packet": packet["artifact"], "markdown": packet["markdown_artifact"]}, indent=2))
    return 0


def create_qa_failure_packet(*, note: str = "", output_dir: Path = OUTPUT_DIR, max_artifacts: int = MAX_ARTIFACTS) -> dict[str, Any]:
    created_at = datetime.now(UTC).isoformat()
    evidence = _collect_evidence(max_artifacts=max_artifacts)
    packet_id = created_at.replace(":", "").replace("-", "").split(".", 1)[0]
    packet = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": packet_id,
        "created_at": created_at,
        "advisory_only": True,
        "advisory_source": "local_redacted_evidence_packet",
        "operator_note": note[:1200],
        "summary": _summary(evidence),
        "advisory_triage": _advisory_triage(note, evidence),
        "evidence": evidence,
        "suggested_ai_prompt": _suggested_prompt(note, evidence),
        "safety_notes": [
            "This packet is advisory and does not execute tests, workflow actions, probes, or hardware commands.",
            "Payloads are redacted before writing. Review artifacts before sending them outside the lab machine.",
            "AI may diagnose and propose safe next checks only; existing guarded workflows remain the only execution path.",
        ],
        "not_attempted": [
            "test execution",
            "workflow action execution",
            "provider probe execution",
            "hardware access",
            "external AI/API call",
        ],
    }
    sanitized = redact_sensitive(packet, _env_secret_values())
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{packet_id}.json"
    markdown_path = output_dir / f"{packet_id}.md"
    latest_json = output_dir / "latest.json"
    latest_markdown = output_dir / "latest.md"
    sanitized["artifact"] = display_path(json_path, REPO_ROOT)
    sanitized["markdown_artifact"] = display_path(markdown_path, REPO_ROOT)
    write_json_object(json_path, sanitized)
    write_json_object(latest_json, sanitized)
    markdown = _markdown(sanitized)
    write_text_value(markdown_path, markdown)
    write_text_value(latest_markdown, markdown)
    return sanitized


def _collect_evidence(*, max_artifacts: int) -> list[dict[str, Any]]:
    candidates: list[Path] = []
    candidates.extend(_paths("frontend/test-results/.last-run.json"))
    candidates.extend(_paths("frontend/test-results/**/error-context.md"))
    candidates.extend(_paths("frontend/test-results/**/*.txt"))
    candidates.extend(_paths("backend/.pytest_cache/v/cache/lastfailed"))
    candidates.extend(_paths("backend/.pytest_cache/v/cache/nodeids"))
    candidates.extend(_paths("artifacts/codex-runs/workflow-action-runs/*.json"))
    candidates.extend(_paths("artifacts/real-lab/*.json"))
    unique = {path.resolve(strict=False): path for path in candidates if path.is_file()}
    ordered = sorted(unique.values(), key=lambda path: path_mtime(path) or 0, reverse=True)
    return [_evidence_item(path) for path in ordered[:max_artifacts]]


def _paths(pattern: str) -> list[Path]:
    try:
        return list(APP_ROOT.glob(pattern))
    except OSError:
        return []


def _evidence_item(path: Path) -> dict[str, Any]:
    text = safe_read_text(path, default="")
    truncated = len(text) > MAX_TEXT_CHARS
    content = text[:MAX_TEXT_CHARS]
    parsed = _try_json(content) if path.suffix.lower() == ".json" or path.name in {"lastfailed", "nodeids"} else None
    item: dict[str, Any] = {
        "path": display_path(path, REPO_ROOT),
        "kind": _kind(path),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "modified_at": datetime.fromtimestamp(path_mtime(path) or 0, UTC).isoformat() if path_mtime(path) else None,
        "truncated": truncated,
    }
    if parsed is not None:
        item["json"] = parsed
    else:
        item["text"] = content
    if truncated:
        item["truncation_note"] = f"Content clipped to {MAX_TEXT_CHARS} characters."
    return redact_sensitive(item, _env_secret_values())


def _try_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _kind(path: Path) -> str:
    normalized = path.as_posix().lower()
    if "frontend/test-results" in normalized:
        return "playwright"
    if "pytest_cache" in normalized:
        return "pytest-cache"
    if "workflow-action-runs" in normalized:
        return "workflow-run"
    if "artifacts/real-lab" in normalized:
        return "hardware-smoke"
    return "local-artifact"


def _summary(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "No recent pytest, Playwright, workflow, or hardware-smoke evidence artifacts were found."
    kinds: dict[str, int] = {}
    for item in evidence:
        kind = str(item.get("kind") or "unknown")
        kinds[kind] = kinds.get(kind, 0) + 1
    return "Collected redacted evidence: " + ", ".join(f"{kind}={count}" for kind, count in sorted(kinds.items())) + "."


def _advisory_triage(note: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = sorted({str(item.get("kind") or "unknown") for item in evidence})
    combined = "\n".join([note, *[_evidence_search_text(item) for item in evidence]]).lower()
    probable_area = "unknown"
    safe_command = ".\\scripts\\fast-verify.ps1 -WhatIfOnly"
    focus = "Review the collected evidence and choose the narrowest safe verification lane before rerunning a full gate."
    confidence = "low"

    if "hardware-smoke" in kinds:
        probable_area = "hardware-smoke"
        safe_command = ".\\scripts\\hardware-smoke.ps1 -WhatIfOnly"
        focus = "Preview the read-only hardware lane first; do not run write or destructive checks from a packet."
        confidence = "medium"
    elif "workflow-run" in kinds:
        probable_area = "workflow-action"
        safe_command = ".\\scripts\\fast-verify.ps1 -WhatIfOnly"
        focus = "Inspect the latest workflow run trace, blockers, warnings, and report artifacts before suggesting a guarded retry."
        confidence = "medium"
    elif "pytest-cache" in kinds:
        probable_area = "backend-pytest"
        safe_command = "cd backend && .\\.venv\\Scripts\\python.exe -m pytest <failing test path> -q"
        focus = "Start with the failing pytest node id and nearby service or schema invariant."
        confidence = "medium"
    elif "playwright" in kinds:
        probable_area = "frontend-playwright"
        safe_command = "cd frontend && npm run test:e2e -- -g \"<failing test name>\""
        focus = "Start with the failing Playwright test, screenshot diff, route, and visible operator flow."
        confidence = "medium"
    elif "pytest" in combined:
        probable_area = "backend-pytest"
        safe_command = "cd backend && .\\.venv\\Scripts\\python.exe -m pytest <failing test path> -q"
        focus = "Start with the failing pytest node id and nearby service or schema invariant."
        confidence = "medium"
    elif any(term in combined for term in ("workflow", "blocker", "required gate", "confirmation")):
        probable_area = "workflow-action"
        safe_command = ".\\scripts\\fast-verify.ps1 -WhatIfOnly"
        focus = "Inspect the latest workflow run trace, blockers, warnings, and report artifacts before suggesting a guarded retry."
        confidence = "medium"
    elif any(term in combined for term in ("real-lab", "unreachable", "timeout", "connection refused")):
        probable_area = "hardware-smoke"
        safe_command = ".\\scripts\\hardware-smoke.ps1 -WhatIfOnly"
        focus = "Preview the read-only hardware lane first; do not run write or destructive checks from a packet."
        confidence = "medium"
    if not evidence:
        focus = "No evidence files were found. Reproduce with fast-verify or the narrow failing command, then regenerate the packet."

    return {
        "schema_version": TRIAGE_SCHEMA_VERSION,
        "probable_area": probable_area,
        "confidence": confidence,
        "evidence_kinds": kinds,
        "safe_verification_command": safe_command,
        "suggested_focus": focus,
        "unsafe_actions_excluded": [
            "write workflow actions",
            "destructive workflow actions",
            "hardware reset/power actions",
            "external AI/API calls",
            "credential or secret disclosure",
        ],
    }


def validate_qa_failure_packet_path(path: Path) -> dict[str, Any]:
    try:
        packet = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"valid": False, "packet": display_path(path, REPO_ROOT), "errors": ["packet file not found"]}
    except json.JSONDecodeError as exc:
        return {"valid": False, "packet": display_path(path, REPO_ROOT), "errors": [f"packet JSON is invalid: {exc}"]}
    result = validate_qa_failure_packet(packet)
    result["packet"] = display_path(path, REPO_ROOT)
    return result


def validate_qa_failure_packet(packet: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if packet.get("schema_version") != PACKET_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PACKET_SCHEMA_VERSION}")
    if packet.get("advisory_only") is not True:
        errors.append("advisory_only must be true")
    if packet.get("advisory_source") != "local_redacted_evidence_packet":
        errors.append("advisory_source must be local_redacted_evidence_packet")
    if not isinstance(packet.get("evidence"), list):
        errors.append("evidence must be a list")
    if not isinstance(packet.get("safety_notes"), list) or not packet.get("safety_notes"):
        errors.append("safety_notes must be a non-empty list")
    not_attempted = packet.get("not_attempted")
    if not isinstance(not_attempted, list) or "external AI/API call" not in not_attempted or "hardware access" not in not_attempted:
        errors.append("not_attempted must include external AI/API call and hardware access")

    triage = packet.get("advisory_triage")
    if not isinstance(triage, dict):
        errors.append("advisory_triage must be an object")
    else:
        errors.extend(_validate_triage(triage))

    serialized = json.dumps(packet, sort_keys=True).lower()
    for secret_marker in ("password=", "authorization:", "bearer "):
        if secret_marker in serialized and "redacted" not in serialized:
            errors.append(f"packet appears to contain unredacted secret marker: {secret_marker.strip()}")
    return {
        "valid": not errors,
        "schema_version": packet.get("schema_version"),
        "triage_schema_version": triage.get("schema_version") if isinstance(triage, dict) else None,
        "errors": errors,
    }


def _validate_triage(triage: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if triage.get("schema_version") != TRIAGE_SCHEMA_VERSION:
        errors.append(f"advisory_triage.schema_version must be {TRIAGE_SCHEMA_VERSION}")
    if triage.get("probable_area") not in ALLOWED_TRIAGE_AREAS:
        errors.append("advisory_triage.probable_area is not recognized")
    if triage.get("confidence") not in ALLOWED_CONFIDENCE:
        errors.append("advisory_triage.confidence is not recognized")
    if not isinstance(triage.get("evidence_kinds"), list):
        errors.append("advisory_triage.evidence_kinds must be a list")
    command = str(triage.get("safe_verification_command") or "").strip()
    if not command:
        errors.append("advisory_triage.safe_verification_command is required")
    lowered = f" {command.lower()} "
    for token in UNSAFE_COMMAND_TOKENS:
        if token in lowered:
            errors.append(f"advisory_triage.safe_verification_command contains unsafe token: {token.strip()}")
    excluded = triage.get("unsafe_actions_excluded")
    if not isinstance(excluded, list):
        errors.append("advisory_triage.unsafe_actions_excluded must be a list")
    else:
        for required in ("write workflow actions", "destructive workflow actions", "external AI/API calls"):
            if required not in excluded:
                errors.append(f"advisory_triage.unsafe_actions_excluded must include {required}")
    return errors


def _evidence_search_text(item: dict[str, Any]) -> str:
    values = [
        str(item.get("path") or ""),
        str(item.get("kind") or ""),
        str(item.get("text") or ""),
    ]
    parsed = item.get("json")
    if parsed is not None:
        try:
            values.append(json.dumps(parsed, sort_keys=True))
        except TypeError:
            values.append(str(parsed))
    return "\n".join(values)


def _suggested_prompt(note: str, evidence: list[dict[str, Any]]) -> str:
    paths = "\n".join(f"- {item.get('path')}" for item in evidence[:8]) or "- No evidence files found"
    note_line = note.strip() or "No operator note supplied."
    return (
        "You are diagnosing a Lab Builder test or workflow failure from redacted local evidence.\n"
        "Stay advisory only. Do not suggest destructive actions or hardware writes. Prefer safe read-only checks and targeted tests.\n\n"
        f"Operator note: {note_line}\n\n"
        f"Evidence files:\n{paths}\n\n"
        "Return: probable cause, affected module/page, safest next verification command, and one minimal fix direction. "
        "Do not suggest write, destructive, reset, power, or hardware-changing actions."
    )


def _markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# QA Failure Packet",
        "",
        f"- Packet: `{packet.get('packet_id')}`",
        f"- Created: `{packet.get('created_at')}`",
        f"- Advisory only: `{packet.get('advisory_only')}`",
        f"- Summary: {packet.get('summary')}",
        "",
        "## Advisory Triage",
        "",
    ]
    triage = packet.get("advisory_triage") if isinstance(packet.get("advisory_triage"), dict) else {}
    lines.extend(
        [
            f"- Probable area: `{triage.get('probable_area') or 'unknown'}`",
            f"- Confidence: `{triage.get('confidence') or 'low'}`",
            f"- Safe verification: `{triage.get('safe_verification_command') or '.\\scripts\\fast-verify.ps1 -WhatIfOnly'}`",
            f"- Focus: {triage.get('suggested_focus') or 'Review redacted evidence before rerunning checks.'}",
            "",
            "## Evidence",
            "",
        ]
    )
    for item in packet.get("evidence", []):
        if not isinstance(item, dict):
            continue
        lines.append(f"- `{item.get('path')}` ({item.get('kind')}, truncated={item.get('truncated')})")
    lines.extend(
        [
            "",
            "## Suggested AI Prompt",
            "",
            "```text",
            str(packet.get("suggested_ai_prompt") or ""),
            "```",
            "",
            "## Safety",
            "",
        ]
    )
    for note in packet.get("safety_notes", []):
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _env_secret_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if value and any(fragment in key.lower() for fragment in ("password", "token", "secret", "authorization", "cookie")):
            values.append(value)
    return values


if __name__ == "__main__":
    raise SystemExit(main())
