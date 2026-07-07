from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.control_actions import REPO_ROOT
from app.services.json_file_store import read_json_object, write_json_object
from app.services.list_utils import unique_strings
from app.services.path_utils import display_path, glob_paths

WORKFLOW_ACTION_RUN_TRACE_DIR = REPO_ROOT / "artifacts" / "codex-runs" / "workflow-action-runs"
MAX_TRACE_FILENAME_CHARS = 240
MAX_TRACE_SLUG_CHARS = 100
DEFAULT_TRACE_LIST_LIMIT = 20


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
    write_json_object(path, payload)
    return payload


def list_workflow_action_run_traces(action_id: str, *, limit: int = DEFAULT_TRACE_LIST_LIMIT) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    pattern = f"*__{_filename_slug(action_id)}__*.json"
    remaining = max(1, limit)
    for path in _trace_paths_newest_first(pattern):
        payload = _read_trace(path)
        if payload and payload.get("action_id") == action_id:
            traces.append(payload)
            remaining -= 1
            if remaining <= 0:
                break
    return traces


def latest_workflow_action_run_trace(action_id: str) -> dict[str, Any] | None:
    traces = list_workflow_action_run_traces(action_id, limit=1)
    return traces[0] if traces else None


def latest_workflow_action_run_traces_by_action() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for path in _trace_paths("*.json"):
        payload = _read_trace(path)
        if not payload:
            continue
        action_id = str(payload.get("action_id") or "")
        if not action_id:
            continue
        current = latest.get(action_id)
        if current is None or _trace_sort_key(payload) > _trace_sort_key(current):
            latest[action_id] = payload
    return latest


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
        "report_artifacts": _string_list(trace.get("report_artifacts")),
        "summary": str(trace.get("summary") or ""),
        "blockers": _string_list(trace.get("blockers")),
        "warnings": _string_list(trace.get("warnings")),
        "next_action": str(trace.get("next_action") or ""),
    }


def _read_trace(path: Path) -> dict[str, Any] | None:
    payload = read_json_object(path)
    if isinstance(payload, dict):
        return payload
    return None


def _trace_paths(pattern: str) -> list[Path]:
    return glob_paths(WORKFLOW_ACTION_RUN_TRACE_DIR, pattern)


def _trace_paths_newest_first(pattern: str) -> list[Path]:
    return sorted(_trace_paths(pattern), key=lambda path: path.name, reverse=True)


def _timestamp_for_filename() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _trace_sort_key(trace: dict[str, Any]) -> str:
    return str(trace.get("finished_at") or trace.get("started_at") or "")


def _filename_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")[:MAX_TRACE_SLUG_CHARS] or "run"


def _relative_to_repo(path: Path) -> str:
    return display_path(path, REPO_ROOT)


def _string_list(value: Any) -> list[str]:
    return unique_strings(value)
