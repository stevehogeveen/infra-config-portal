from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.control_actions import REPO_ROOT

WORKFLOW_ACTION_RUN_TRACE_DIR = REPO_ROOT / "artifacts" / "codex-runs" / "workflow-action-runs"


def save_workflow_action_run_trace(trace: dict[str, Any]) -> dict[str, Any]:
    WORKFLOW_ACTION_RUN_TRACE_DIR.mkdir(parents=True, exist_ok=True)
    run_id = str(trace["run_id"])
    action_id = str(trace["action_id"])
    filename = f"{_timestamp_for_filename()}__{_filename_slug(action_id)}__{_filename_slug(run_id)}.json"
    path = WORKFLOW_ACTION_RUN_TRACE_DIR / filename
    relative_path = _relative_to_repo(path)
    payload = {
        **trace,
        "trace_artifact": relative_path,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def list_workflow_action_run_traces(action_id: str) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    pattern = f"*__{_filename_slug(action_id)}__*.json"
    for path in WORKFLOW_ACTION_RUN_TRACE_DIR.glob(pattern):
        payload = _read_trace(path)
        if payload and payload.get("action_id") == action_id:
            traces.append(payload)
    return sorted(
        traces,
        key=lambda trace: str(trace.get("finished_at") or trace.get("started_at") or ""),
        reverse=True,
    )


def list_all_workflow_action_run_traces(limit: int = 80) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for path in WORKFLOW_ACTION_RUN_TRACE_DIR.glob("*.json"):
        payload = _read_trace(path)
        if payload:
            traces.append(payload)
    return sorted(
        traces,
        key=lambda trace: str(trace.get("finished_at") or trace.get("started_at") or ""),
        reverse=True,
    )[:limit]


def latest_workflow_action_run_trace(action_id: str) -> dict[str, Any] | None:
    traces = list_workflow_action_run_traces(action_id)
    return traces[0] if traces else None


def run_trace_to_registry_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(trace.get("run_id") or ""),
        "action_id": str(trace.get("action_id") or ""),
        "stage_id": str(trace.get("stage_id") or ""),
        "started_at": trace.get("started_at"),
        "finished_at": trace.get("finished_at"),
        "status": str(trace.get("status") or "not_checked"),
        "source_type": str(trace.get("source_type") or "live_probe"),
        "freshness": str(trace.get("freshness") or "current"),
        "command": trace.get("command"),
        "report_artifacts": list(trace.get("report_artifacts") or []),
        "summary": str(trace.get("summary") or ""),
        "blockers": list(trace.get("blockers") or []),
        "warnings": list(trace.get("warnings") or []),
        "next_action": str(trace.get("next_action") or ""),
    }


def _read_trace(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _timestamp_for_filename() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _filename_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:120] or "run"


def _relative_to_repo(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
