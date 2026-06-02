from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent, Request, WorkflowRun


def record_audit_event(
    session: Session,
    *,
    actor: str,
    event_type: str,
    message: str,
    request: Request | None = None,
    workflow_run: WorkflowRun | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    data: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        request_id=request.id if request else None,
        workflow_run_id=workflow_run.id if workflow_run else None,
        actor=actor,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        message=message,
        data_json=data or {},
    )
    session.add(event)
    session.flush()
    return event
