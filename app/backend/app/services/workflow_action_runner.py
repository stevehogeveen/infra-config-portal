from __future__ import annotations

import json
import os
import subprocess
import uuid
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.providers.redaction import redact_sensitive
from app.services.lab_profiles import list_lab_profiles
from app.services.report_center import get_report_center, get_report_summary
from app.services.workflow_action_allowlist import (
    get_workflow_action_execution_spec,
    workflow_action_run_blockers,
)
from app.services.workflow_action_run_store import (
    latest_workflow_action_run_trace,
    list_workflow_action_run_traces,
    save_workflow_action_run_trace,
)
from app.services.workflow_registry import WorkflowRegistryNotFoundError, get_workflow_action
from app.services.control_actions import REPO_ROOT


class WorkflowActionRunNotFoundError(LookupError):
    pass


def run_workflow_action(action_id: str, session: Session | None = None) -> dict[str, Any]:
    action = get_workflow_action(action_id)
    blockers = workflow_action_run_blockers(action)
    started_at = _now()
    run_id = f"workflow-action:{action_id}:{uuid.uuid4().hex[:12]}"
    if blockers:
        result = _blocked_result(action, run_id, started_at, blockers)
        return save_workflow_action_run_trace(result)

    spec = get_workflow_action_execution_spec(action_id)
    if spec is None:
        result = _blocked_result(
            action,
            run_id,
            started_at,
            ["No read-only UI runner allowlist entry exists for this action yet."],
        )
        return save_workflow_action_run_trace(result)

    if spec.kind == "api":
        result = _run_api_action(action, run_id, started_at, session)
    else:
        result = _run_command_action(action, run_id, started_at, spec.command, spec.timeout_seconds)

    reports = _existing_report_artifacts([*list(action.get("reports") or []), *list(spec.reports)])
    result["report_artifacts"] = _unique(
        [
            *reports,
            *list(result.get("report_artifacts") or []),
        ]
    )
    return save_workflow_action_run_trace(result)


def list_workflow_action_runs(action_id: str) -> list[dict[str, Any]]:
    try:
        get_workflow_action(action_id)
    except WorkflowRegistryNotFoundError:
        raise
    return list_workflow_action_run_traces(action_id)


def latest_workflow_action_run(action_id: str) -> dict[str, Any] | None:
    return latest_workflow_action_run_trace(action_id)


def _run_command_action(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    command: tuple[str, ...],
    timeout_seconds: int,
) -> dict[str, Any]:
    completed: subprocess.CompletedProcess[str] | None = None
    stderr = ""
    stdout = ""
    try:
        completed = _run_subprocess(command, timeout_seconds)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        return_code = completed.returncode
        status = "completed" if return_code == 0 else "failed"
        blockers = [] if return_code == 0 else [f"Command exited with code {return_code}; review evidence before rerun."]
    except subprocess.TimeoutExpired as exc:
        stdout = _decode_output(exc.stdout)
        stderr = _decode_output(exc.stderr)
        return_code = None
        status = "failed"
        blockers = [f"Command exceeded the {timeout_seconds}s safe action runner timeout."]
    except OSError as exc:
        return_code = None
        status = "failed"
        blockers = [f"Command could not start: {exc.__class__.__name__}."]

    stdout_summary = _redacted_summary(stdout)
    stderr_summary = _redacted_summary(stderr)
    return _base_result(
        action,
        run_id,
        started_at,
        status=status,
        command=" ".join(command),
        executed=True,
        return_code=return_code,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        blockers=blockers,
        warnings=_output_warnings(stdout_summary, stderr_summary),
    )


def _run_api_action(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    session: Session | None,
) -> dict[str, Any]:
    try:
        payload = _api_action_payload(str(action["action_id"]), session)
        stdout_summary = _redacted_summary(json.dumps(_jsonable(payload), sort_keys=True))
        return _base_result(
            action,
            run_id,
            started_at,
            status="completed",
            command=f"{action.get('api_method') or 'GET'} {action.get('api_endpoint')}",
            executed=True,
            return_code=0,
            stdout_summary=stdout_summary,
            stderr_summary="",
            blockers=[],
            warnings=[],
        )
    except Exception as exc:
        return _base_result(
            action,
            run_id,
            started_at,
            status="failed",
            command=f"{action.get('api_method') or 'GET'} {action.get('api_endpoint')}",
            executed=True,
            return_code=None,
            stdout_summary="",
            stderr_summary=_redacted_summary(f"{exc.__class__.__name__}: {exc}"),
            blockers=[f"API action failed before completing safely: {exc.__class__.__name__}."],
            warnings=[],
        )


def _api_action_payload(action_id: str, session: Session | None) -> Any:
    if action_id == "reports.issue-center":
        if session is None:
            raise WorkflowActionRunNotFoundError("Report Center requires a database session.")
        return get_report_center(session)
    if action_id == "reports.summary":
        if session is None:
            raise WorkflowActionRunNotFoundError("Report summary requires a database session.")
        return get_report_summary(session)
    if action_id == "lab-profile.view-active":
        return list_lab_profiles()
    raise WorkflowActionRunNotFoundError(action_id)


def _blocked_result(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    blockers: list[str],
) -> dict[str, Any]:
    return _base_result(
        action,
        run_id,
        started_at,
        status="blocked",
        command=_action_command(action),
        executed=False,
        return_code=None,
        stdout_summary="",
        stderr_summary="",
        blockers=blockers,
        warnings=[],
    )


def _base_result(
    action: dict[str, Any],
    run_id: str,
    started_at: str,
    *,
    status: str,
    command: str | None,
    executed: bool,
    return_code: int | None,
    stdout_summary: str,
    stderr_summary: str,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    finished_at = _now()
    report_artifacts = _existing_report_artifacts(action.get("reports") or [])
    if status == "completed":
        summary = "Safe read-only/report-only action completed. Review evidence before using results as current state."
        next_action = "Review evidence artifacts, then continue with the next safe stage."
    elif status == "blocked":
        summary = "Action was not run by the safe read-only action runner."
        next_action = blockers[0] if blockers else str(action.get("next_action") or "Review the blocked action.")
    else:
        summary = "Safe read-only/report-only action failed before completing cleanly."
        next_action = "Review the run trace and evidence, fix the blocker, then run the check again."
    return {
        "run_id": run_id,
        "action_id": action["action_id"],
        "action_label": action["label"],
        "stage_id": action["stage"],
        "stage_label": action["stage_label"],
        "mode": action["mode"],
        "started_at": started_at,
        "finished_at": finished_at,
        "checked_at": finished_at,
        "status": status,
        "source_type": "live_probe",
        "freshness": "current",
        "not_mock": True,
        "command": command,
        "executed": executed,
        "return_code": return_code,
        "stdout_summary": stdout_summary,
        "stderr_summary": stderr_summary,
        "report_artifacts": report_artifacts,
        "trace_artifact": None,
        "summary": summary,
        "blockers": blockers,
        "warnings": warnings,
        "next_action": next_action,
    }


def _run_subprocess(command: tuple[str, ...], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
    }
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )


def _action_command(action: dict[str, Any]) -> str | None:
    command = action.get("command")
    if command:
        return str(command)
    endpoint = action.get("api_endpoint")
    if endpoint:
        return f"{action.get('api_method') or 'GET'} {endpoint}"
    return None


def _existing_report_artifacts(paths: list[str] | tuple[str, ...]) -> list[str]:
    return _unique(str(path) for path in paths if path and (REPO_ROOT / str(path)).exists())


def _redacted_summary(text: str, *, max_chars: int = 4000) -> str:
    if not text:
        return ""
    redacted = redact_sensitive(text, _redaction_values())
    lines = str(redacted).splitlines()
    if len(lines) > 80:
        lines = [*lines[:40], "... output truncated ...", *lines[-40:]]
    summary = "\n".join(lines)
    if len(summary) > max_chars:
        return f"{summary[:max_chars]}\n... output truncated ..."
    return summary


def _redaction_values() -> list[str]:
    values: list[str] = []
    if hasattr(settings, "model_dump"):
        settings_data = settings.model_dump()
    elif hasattr(settings, "dict"):
        settings_data = settings.dict()
    elif is_dataclass(settings):
        settings_data = asdict(settings)
    else:
        settings_data = vars(settings)
    for key, value in settings_data.items():
        if _looks_sensitive_key(str(key)) and value:
            if isinstance(value, list | tuple):
                values.extend(str(item) for item in value if item)
            else:
                values.append(str(value))
    for key, value in os.environ.items():
        if _looks_sensitive_key(key) and value and len(value) >= 3:
            values.append(value)
    return _unique(values)


def _looks_sensitive_key(key: str) -> bool:
    lower = key.lower()
    return any(fragment in lower for fragment in ("password", "token", "secret", "credential", "authorization", "cookie"))


def _output_warnings(stdout_summary: str, stderr_summary: str) -> list[str]:
    warnings = ["Output was redacted and truncated for operator display."]
    if stderr_summary:
        warnings.append("stderr summary is available in the run trace.")
    if "REDACTED" in stdout_summary or "REDACTED" in stderr_summary:
        warnings.append("Sensitive-looking values were redacted.")
    return warnings


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _decode_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _unique(values: Any) -> list[Any]:
    seen: set[Any] = set()
    result: list[Any] = []
    for value in values:
        if value in {None, ""} or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
