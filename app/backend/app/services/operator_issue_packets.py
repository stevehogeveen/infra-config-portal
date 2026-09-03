from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.control_actions import REPO_ROOT
from app.services.json_file_store import write_json_object, write_text_value
from app.services.list_utils import unique_strings
from app.services.path_utils import display_path, glob_paths
from app.services.workflow_action_diagnosis import diagnose_workflow_action
from app.services import workflow_action_run_store
from app.services.workflow_action_run_store import run_trace_to_registry_trace

OPERATOR_ISSUE_PACKET_DIR = REPO_ROOT / "artifacts" / "codex-runs" / "operator-issue-packets"
MAX_OPERATOR_NOTE_CHARS = 1600
MAX_ROUTE_CHARS = 160
MAX_RECENT_RUNS = 8
PROBLEM_STATUSES = {"blocked", "failed", "error"}


def create_operator_issue_packet(payload: dict[str, Any]) -> dict[str, Any]:
    route = _clean_text(payload.get("route"), MAX_ROUTE_CHARS) or "/"
    page_title = _clean_text(payload.get("page_title"), 120) or _page_title_from_route(route)
    operator_note = _clean_text(payload.get("operator_note"), MAX_OPERATOR_NOTE_CHARS)
    ui_context = _clean_mapping(payload.get("ui_context"), max_items=12)
    recent_runs = _recent_problem_runs()
    diagnoses = [_diagnosis_for_trace(trace) for trace in recent_runs[:4]]
    packet_id = _packet_id(route)
    packet = redact_sensitive(
        {
            "packet_id": packet_id,
            "created_at": datetime.now(UTC).isoformat(),
            "route": route,
            "page_title": page_title,
            "operator_note": operator_note,
            "ui_context": ui_context,
            "ai_enabled": False,
            "advisory_source": "local_rules",
            "summary": _summary(operator_note, page_title, recent_runs),
            "recent_problem_runs": [run_trace_to_registry_trace(trace) for trace in recent_runs],
            "diagnoses": diagnoses,
            "suggested_next_steps": _suggested_next_steps(recent_runs, diagnoses),
            "safety_notes": [
                "Issue packets are advisory and do not execute workflow actions.",
                "Secrets are redacted before packet artifacts are written.",
                "Use read-only validation before rerunning guarded apply, reset, or upgrade actions.",
            ],
        }
    )
    json_path = OPERATOR_ISSUE_PACKET_DIR / f"{packet_id}.json"
    markdown_path = OPERATOR_ISSUE_PACKET_DIR / f"{packet_id}.md"
    write_json_object(json_path, packet)
    write_text_value(markdown_path, _packet_markdown(packet))
    return {
        **packet,
        "artifact": display_path(json_path, REPO_ROOT),
        "markdown_artifact": display_path(markdown_path, REPO_ROOT),
        "copy_prompt": _copy_prompt(packet),
    }


def _recent_problem_runs() -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for path in sorted(glob_paths(workflow_action_run_store.WORKFLOW_ACTION_RUN_TRACE_DIR, "*.json"), key=lambda item: item.name, reverse=True):
        payload = _read_trace(path)
        if not payload:
            continue
        status = str(payload.get("status") or "").lower()
        if status in PROBLEM_STATUSES or payload.get("blockers") or payload.get("warnings"):
            traces.append(payload)
        if len(traces) >= MAX_RECENT_RUNS:
            break
    return traces


def _read_trace(path: Path) -> dict[str, Any] | None:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _diagnosis_for_trace(trace: dict[str, Any]) -> dict[str, Any]:
    action_id = str(trace.get("action_id") or "")
    if not action_id:
        return {}
    try:
        diagnosis = diagnose_workflow_action(action_id, limit=3)
    except Exception:
        return {
            "action_id": action_id,
            "probable_cause": "Diagnosis unavailable for this action.",
            "suggested_next_action": "Review the saved workflow trace artifact.",
            "suggested_action_safe": False,
        }
    return {
        "action_id": diagnosis.get("action_id"),
        "status": diagnosis.get("status"),
        "confidence": diagnosis.get("confidence"),
        "probable_cause": diagnosis.get("probable_cause"),
        "suggested_next_action": diagnosis.get("suggested_next_action"),
        "suggested_action_id": diagnosis.get("suggested_action_id"),
        "suggested_action_safe": diagnosis.get("suggested_action_safe"),
    }


def _summary(operator_note: str, page_title: str, recent_runs: list[dict[str, Any]]) -> str:
    if operator_note:
        return f"Operator reported an issue on {page_title}: {operator_note[:180]}"
    if recent_runs:
        trace = recent_runs[0]
        return f"Operator requested an issue packet on {page_title}; latest run {trace.get('action_id')} is {trace.get('status')}."
    return f"Operator requested an issue packet on {page_title}; no recent failed or blocked workflow traces were found."


def _suggested_next_steps(recent_runs: list[dict[str, Any]], diagnoses: list[dict[str, Any]]) -> list[str]:
    steps = [
        "Attach this packet to the AI/code review prompt before changing behavior.",
        "Reproduce from the route and active UI context listed in the packet.",
    ]
    safe_actions = unique_strings(
        diagnosis.get("suggested_action_id")
        for diagnosis in diagnoses
        if diagnosis.get("suggested_action_safe") and diagnosis.get("suggested_action_id")
    )
    if safe_actions:
        steps.append(f"Use read-only/report-only follow-up action(s): {', '.join(safe_actions[:3])}.")
    elif recent_runs:
        steps.append("Run the safest read-only validation for the affected page before retrying a guarded action.")
    else:
        steps.append("Run the page validation or operator read-only sweep to collect first evidence.")
    steps.append("After any fix, run .\\scripts\\fast-verify.ps1 from the app directory.")
    return steps


def _packet_markdown(packet: dict[str, Any]) -> str:
    lines = [
        f"# Operator Issue Packet: {packet.get('page_title')}",
        "",
        f"- Packet: `{packet.get('packet_id')}`",
        f"- Created: {packet.get('created_at')}",
        f"- Route: `{packet.get('route')}`",
        f"- Advisory source: {packet.get('advisory_source')}",
        "",
        "## Operator Note",
        packet.get("operator_note") or "No operator note provided.",
        "",
        "## Summary",
        packet.get("summary") or "",
        "",
        "## Recent Problem Runs",
    ]
    for run in packet.get("recent_problem_runs") or []:
        lines.append(f"- `{run.get('action_id')}`: {run.get('status')} - {run.get('summary')}")
    if not packet.get("recent_problem_runs"):
        lines.append("- None captured.")
    lines.extend(["", "## Suggested Next Steps"])
    for step in packet.get("suggested_next_steps") or []:
        lines.append(f"- {step}")
    lines.extend(["", "## Safety Notes"])
    for note in packet.get("safety_notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _copy_prompt(packet: dict[str, Any]) -> str:
    run_lines = [
        f"- {run.get('action_id')}: {run.get('status')} ({run.get('summary')})"
        for run in (packet.get("recent_problem_runs") or [])[:4]
    ]
    return "\n".join(
        [
            "Please fix this Lab Builder issue using the attached current worktree context.",
            f"Route: {packet.get('route')}",
            f"Operator note: {packet.get('operator_note') or 'No note provided.'}",
            f"Summary: {packet.get('summary')}",
            "Recent runs:",
            *(run_lines or ["- No recent problem runs captured."]),
            "Safety: do not execute destructive/write actions from this packet; use read-only validation first.",
        ]
    )


def _packet_id(route: str) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", route.strip("/").replace("/", "-")).strip("-") or "overview"
    return f"{timestamp}__{slug[:80]}"


def _clean_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "").strip()
    return text[:limit]


def _clean_mapping(value: Any, *, max_items: int) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, item in value.items():
        if len(cleaned) >= max_items:
            break
        cleaned[_clean_text(key, 80)] = _clean_text(item, 240)
    return cleaned


def _page_title_from_route(route: str) -> str:
    label = route.strip("/").split("/")[0] or "overview"
    return label.replace("-", " ").title()
