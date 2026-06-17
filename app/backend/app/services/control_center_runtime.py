from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import AuditEvent
from app.services.workflow_action_run_store import list_all_workflow_action_run_traces
from app.services.workflow_registry import list_workflow_actions


def get_control_center_firmware_status() -> dict[str, Any]:
    actions = list_workflow_actions()
    firmware_action_ids = _firmware_action_ids(actions)
    traces = [
        _historical_trace(trace)
        for trace in list_all_workflow_action_run_traces(limit=120)
        if str(trace.get("action_id") or "") in firmware_action_ids
    ][:20]

    if not firmware_action_ids:
        return _empty_firmware_status(
            message="No backend firmware action catalog entries are available yet.",
            source_type="todo_placeholder",
        )

    if not traces:
        return {
            **_empty_firmware_status(
                message=(
                    "No backend firmware checks, validations, or upgrade attempts "
                    "have been recorded yet."
                ),
                source_type="backend_action_runs",
            ),
            "action_ids": firmware_action_ids,
        }

    latest = traces[0]
    latest_upgrade = next(
        (trace for trace in traces if _firmware_operation_type(trace) == "firmware-upgrade"),
        None,
    )
    active = latest_upgrade or latest
    message_source = latest_upgrade or latest
    return {
        "action_ids": firmware_action_ids,
        "checked_at": (
            active.get("checked_at")
            or active.get("finished_at")
            or active.get("started_at")
        ),
        "freshness": "historical",
        "history": traces,
        "latest_upgrade": latest_upgrade,
        "message": str(
            message_source.get("summary")
            or message_source.get("next_action")
            or "Firmware action history is available."
        ),
        "source_type": "historical_artifact",
        "status": _upgrade_status_from_trace(active),
        "warnings": list(active.get("warnings") or []),
        "blockers": list(active.get("blockers") or []),
        "next_safe_action": str(
            active.get("next_action") or "Review firmware action history before continuing."
        ),
    }


def get_control_center_logs(session: Session, *, limit: int = 80) -> list[dict[str, Any]]:
    traces = [_log_from_trace(trace) for trace in list_all_workflow_action_run_traces(limit=limit)]
    audit_rows = session.execute(
        select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(limit)
    ).scalars()
    audit_logs = [_log_from_audit_event(event) for event in audit_rows]
    return sorted(
        [*traces, *audit_logs],
        key=lambda log: str(log.get("timestamp") or ""),
        reverse=True,
    )[:limit]


def _empty_firmware_status(*, message: str, source_type: str) -> dict[str, Any]:
    return {
        "action_ids": [],
        "checked_at": None,
        "freshness": "not_checked",
        "history": [],
        "latest_upgrade": None,
        "message": message,
        "source_type": source_type,
        "status": "idle",
        "warnings": [],
        "blockers": [],
        "next_safe_action": (
            "Use Check Firmware or Validate Firmware when backend integration is available."
        ),
    }


def _historical_trace(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        **trace,
        "source_type": "historical_artifact",
        "freshness": "historical",
    }


def _firmware_action_ids(actions: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for action in actions:
        action_id = str(action.get("action_id") or "")
        normalized = action_id.lower()
        if (
            action.get("stage") == "firmware"
            or action.get("category") == "upgrade"
            or "firmware" in normalized
            or "ontap-upgrade" in normalized
        ):
            ids.append(action_id)
    return sorted(set(ids))


def _firmware_operation_type(trace: dict[str, Any]) -> str:
    action_id = str(trace.get("action_id") or "").lower()
    if "apply" in action_id or "upgrade-apply" in action_id:
        return "firmware-upgrade"
    if "validate" in action_id or "compliance" in action_id or "waiver" in action_id:
        return "firmware-validation"
    return "firmware-check"


def _upgrade_status_from_trace(trace: dict[str, Any]) -> str:
    status = str(trace.get("status") or "").lower()
    if status in {"completed", "success", "ok", "passed", "ready"}:
        return "success"
    if status == "running":
        return "upgrading"
    if status == "blocked":
        return "blocked"
    if status in {"failed", "error", "unavailable"}:
        return "failed"
    if status in {"pending", "not_checked", "unknown"}:
        return "pending"
    return "idle"


def _log_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    operation = _firmware_operation_type(trace) if _is_firmware_trace(trace) else "run"
    label = _event_label(operation, str(trace.get("status") or "recorded"))
    return {
        "id": f"workflow:{trace.get('run_id')}",
        "timestamp": (
            trace.get("checked_at")
            or trace.get("finished_at")
            or trace.get("started_at")
            or _now()
        ),
        "type": "firmware" if operation.startswith("firmware") else "run",
        "message": label,
        "status": str(trace.get("status") or "recorded"),
        "detail": str(trace.get("summary") or trace.get("next_action") or ""),
        "source_type": "historical_artifact",
        "freshness": "historical",
    }


def _log_from_audit_event(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": f"audit:{event.id}",
        "timestamp": event.created_at.isoformat(),
        "type": _audit_log_type(event.event_type),
        "message": _humanize(event.event_type),
        "status": event.to_status or event.from_status or "recorded",
        "detail": event.message,
        "source_type": "backend_audit",
        "freshness": "historical",
    }


def _is_firmware_trace(trace: dict[str, Any]) -> bool:
    action_id = str(trace.get("action_id") or "").lower()
    return (
        str(trace.get("stage_id") or "") == "firmware"
        or "firmware" in action_id
        or "ontap-upgrade" in action_id
    )


def _event_label(operation: str, status: str) -> str:
    prefix = {
        "firmware-check": "Firmware check",
        "firmware-validation": "Firmware validation",
        "firmware-upgrade": "Firmware upgrade",
    }.get(operation, "Run")
    normalized = status.lower()
    if normalized in {"completed", "success", "ok", "passed", "ready"}:
        return f"{prefix} succeeded"
    if normalized == "blocked":
        return f"{prefix} blocked"
    if normalized in {"failed", "error"}:
        return f"{prefix} failed"
    if normalized == "running":
        return f"{prefix} started"
    return f"{prefix} recorded"


def _audit_log_type(event_type: str) -> str:
    normalized = event_type.lower()
    if "firmware" in normalized:
        return "firmware"
    if "setting" in normalized:
        return "settings"
    if "config" in normalized:
        return "config"
    return "system"


def _humanize(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("-", "_").split("_") if part)


def _now() -> str:
    return datetime.now(UTC).isoformat()
