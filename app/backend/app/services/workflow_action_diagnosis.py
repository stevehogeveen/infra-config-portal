from __future__ import annotations

from typing import Any

from app.providers.redaction import redact_sensitive
from app.services.list_utils import unique_strings
from app.services.workflow_action_run_store import list_workflow_action_run_traces
from app.services.workflow_registry import (
    WorkflowRegistryNotFoundError,
    get_workflow_action,
    list_workflow_actions_for_stage,
    workflow_action_exists,
)

SAFE_SUGGESTION_MODES = {"read_only", "report_only"}
PROBLEM_STATUSES = {"blocked", "failed", "error"}


def diagnose_workflow_action(action_id: str, *, limit: int = 5) -> dict[str, Any]:
    if not workflow_action_exists(action_id):
        raise WorkflowRegistryNotFoundError(action_id)
    action = get_workflow_action(action_id)
    traces = list_workflow_action_run_traces(action_id, limit=max(1, min(limit, 10)))
    latest = traces[0] if traces else None
    recent_runs = [_compact_recent_run(trace) for trace in traces]
    if latest is None:
        suggested = _safe_action_suggestion(action)
        return {
            "action_id": action_id,
            "action_label": str(action.get("label") or action_id),
            "status": "not_checked",
            "ai_enabled": False,
            "advisory_source": "local_rules",
            "confidence": "low",
            "probable_cause": "No workflow run evidence has been captured for this action yet.",
            "explanation": "Run evidence is required before the app can diagnose a failure or blocker.",
            "suggested_next_action": suggested["label"],
            "suggested_action_id": suggested["action_id"],
            "suggested_action_safe": suggested["safe"],
            "evidence": [],
            "recent_runs": recent_runs,
            "safety_notes": _safety_notes(),
        }

    status = str(latest.get("status") or "not_checked").lower()
    blockers = unique_strings(latest.get("blockers"))
    warnings = unique_strings(latest.get("warnings"))
    stderr = str(latest.get("stderr_summary") or "")
    stdout = str(latest.get("stdout_summary") or "")
    suggested = _safe_action_suggestion(action, latest)
    cause, explanation, confidence = _diagnose_trace(status, blockers, warnings, stderr, stdout, action)
    evidence = _diagnosis_evidence(latest, blockers, warnings, stderr, stdout)
    return {
        "action_id": action_id,
        "action_label": str(latest.get("action_label") or action.get("label") or action_id),
        "run_id": latest.get("run_id"),
        "status": status,
        "ai_enabled": False,
        "advisory_source": "local_rules",
        "confidence": confidence,
        "probable_cause": cause,
        "explanation": explanation,
        "suggested_next_action": suggested["label"],
        "suggested_action_id": suggested["action_id"],
        "suggested_action_safe": suggested["safe"],
        "evidence": evidence,
        "recent_runs": recent_runs,
        "safety_notes": _safety_notes(),
    }


def _diagnose_trace(
    status: str,
    blockers: list[str],
    warnings: list[str],
    stderr: str,
    stdout: str,
    action: dict[str, Any],
) -> tuple[str, str, str]:
    combined = "\n".join([*blockers, *warnings, stderr, stdout]).lower()
    if status not in PROBLEM_STATUSES:
        return (
            "The latest run did not report a blocking failure.",
            "The diagnosis card is advisory. Continue using the latest evidence and rerun validation if the page looks stale.",
            "medium",
        )
    if "confirmation" in combined or "required gate" in combined or "required gates" in combined:
        return (
            "A guarded action was blocked by missing confirmation or safety gates.",
            "The app refused to proceed before making changes. Review the preview or validation action first, then provide the exact guarded confirmation only when ready.",
            "high",
        )
    if status == "blocked" and str(action.get("mode") or "") in {"write", "destructive", "upgrade"}:
        return (
            "A guarded action was blocked before it could make changes.",
            "The app refused to proceed because a profile, runtime, safety, or confirmation gate was not satisfied. Use a read-only preview or validation action before attempting the guarded path again.",
            "high",
        )
    if "timeout" in combined or "exceeded" in combined:
        return (
            "The workflow runner timed out before collecting complete evidence.",
            "This usually means the target device, API, console, or command did not respond inside the safe timeout window. Run a read-only reachability check before retrying.",
            "high",
        )
    if "network error" in combined or "connection" in combined or "unreachable" in combined or "refused" in combined:
        return (
            "The app could not reach one of the expected device endpoints.",
            "Check the saved subnet, gateway, management IP, cable path, and current operator network before rerunning the action.",
            "medium",
        )
    if "subnet" in combined:
        return (
            "The active lab subnet does not match the current operator network evidence.",
            "Update the saved network profile or move the operator machine back onto the intended lab subnet before treating live status as trustworthy.",
            "medium",
        )
    if stderr:
        return (
            "The underlying command or API returned an error.",
            "The stderr summary has been redacted and attached as evidence. Use the suggested read-only check to narrow whether this is connectivity, credentials, media, or device state.",
            "medium",
        )
    if blockers:
        return (
            "The workflow reported blockers before it could finish.",
            "The blockers are preserved as evidence. Address the first blocker, then rerun the safest validation action for this stage.",
            "medium",
        )
    return (
        "The run status is problematic, but the trace has limited diagnostic detail.",
        "Collect a fresh read-only run for this stage so the app has enough evidence to classify the failure.",
        "low",
    )


def _safe_action_suggestion(action: dict[str, Any], trace: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = str(action.get("mode") or "")
    if mode in SAFE_SUGGESTION_MODES:
        return {
            "action_id": str(action.get("action_id") or ""),
            "label": str(action.get("next_action") or action.get("label") or "Rerun the read-only action."),
            "safe": True,
        }
    stage = str(action.get("stage") or (trace.get("stage_id") if trace else "") or "")
    for candidate in list_workflow_actions_for_stage(stage):
        if str(candidate.get("mode") or "") in SAFE_SUGGESTION_MODES:
            return {
                "action_id": str(candidate.get("action_id") or ""),
                "label": str(candidate.get("label") or candidate.get("next_action") or "Run the stage read-only check."),
                "safe": True,
            }
    return {
        "action_id": None,
        "label": "Review the trace and run the safest read-only validation available for this stage.",
        "safe": False,
    }


def _diagnosis_evidence(
    trace: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
    stderr: str,
    stdout: str,
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for blocker in blockers[:4]:
        evidence.append({"label": "Blocker", "detail": blocker})
    for warning in warnings[:3]:
        evidence.append({"label": "Warning", "detail": warning})
    if stderr:
        evidence.append({"label": "stderr", "detail": stderr[:500]})
    elif stdout and str(trace.get("status") or "").lower() in PROBLEM_STATUSES:
        evidence.append({"label": "stdout", "detail": stdout[:500]})
    for artifact in unique_strings(trace.get("report_artifacts"))[:3]:
        evidence.append({"label": "Artifact", "detail": artifact})
    return redact_sensitive(evidence)


def _compact_recent_run(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(trace.get("run_id") or ""),
        "status": str(trace.get("status") or "not_checked"),
        "finished_at": trace.get("finished_at"),
        "summary": str(trace.get("summary") or "")[:240],
        "blocker_count": len(unique_strings(trace.get("blockers"))),
        "warning_count": len(unique_strings(trace.get("warnings"))),
        "trace_artifact": trace.get("trace_artifact"),
    }


def _safety_notes() -> list[str]:
    return [
        "Diagnosis is advisory and does not execute workflow actions.",
        "Suggested action ids are limited to read-only or report-only actions when available.",
        "Trace evidence is redacted before being returned for display.",
    ]
