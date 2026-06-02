from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import WorkflowRunStatus
from app.models import AuditEvent, Request, WorkflowRun
from app.services.lifecycle import (
    RequestNotFoundError,
    get_request,
    get_workflow_run,
)


def list_request_artifacts(session: Session, request_id: str) -> list[dict[str, Any]]:
    request = get_request(session, request_id)
    runs = list(
        session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.request_id == request.id)
            .order_by(WorkflowRun.created_at.desc())
        ).scalars()
    )

    artifacts = [_request_history_artifact(session, request)]
    for run in runs:
        artifacts.extend(_workflow_run_artifacts(session, run))

    artifacts.extend(
        [
            _debug_bundle_placeholder(request_id=request.id, updated_at=request.updated_at),
            _export_placeholder(request_id=request.id, updated_at=request.updated_at),
        ]
    )
    return artifacts


def list_workflow_run_artifacts(
    session: Session,
    workflow_run_id: str,
) -> list[dict[str, Any]]:
    run = get_workflow_run(session, workflow_run_id)
    request = session.execute(
        select(Request)
        .options(selectinload(Request.vm_deploy))
        .where(Request.id == run.request_id)
    ).scalar_one_or_none()
    if request is None:
        raise RequestNotFoundError(run.request_id)

    return [
        *_workflow_run_artifacts(session, run),
        _debug_bundle_placeholder(
            request_id=request.id,
            workflow_run_id=run.id,
            updated_at=run.updated_at,
        ),
        _export_placeholder(
            request_id=request.id,
            workflow_run_id=run.id,
            updated_at=run.updated_at,
        ),
    ]


def _workflow_run_artifacts(session: Session, run: WorkflowRun) -> list[dict[str, Any]]:
    return [
        _plan_artifact(run),
        _report_artifact(run),
        _workflow_history_artifact(session, run),
    ]


def _plan_artifact(run: WorkflowRun) -> dict[str, Any]:
    plan = run.plan_json if isinstance(run.plan_json, dict) else {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    return _artifact(
        id_=f"{run.id}:dry-run-plan",
        request_id=run.request_id,
        workflow_run_id=run.id,
        kind="dry_run_plan",
        title="Dry-Run Plan",
        description="Mock plan metadata stored with the workflow run; no provider plan file is generated.",
        status="available" if plan else "pending",
        created_at=run.created_at,
        updated_at=run.updated_at,
        metadata={
            "workflow_slug": run.workflow_slug,
            "provider": run.provider,
            "vm_name": _string(plan.get("vm_name")),
            "step_count": len(steps),
            "review_before_execute_required": bool(
                _dict(plan.get("review_before_execute")).get("required")
            ),
        },
    )


def _report_artifact(run: WorkflowRun) -> dict[str, Any]:
    result = run.result_json if isinstance(run.result_json, dict) else {}
    completed = run.status == WorkflowRunStatus.COMPLETED.value
    failed = run.status == WorkflowRunStatus.FAILED.value
    return _artifact(
        id_=f"{run.id}:completion-report",
        request_id=run.request_id,
        workflow_run_id=run.id,
        kind="completion_report",
        title="Completed-Run Report",
        description=(
            "Mock completion metadata is available for review."
            if completed
            else "Completion report metadata will be available after mock execution."
        ),
        status="available" if completed else "blocked" if failed else "pending",
        created_at=run.created_at,
        updated_at=run.updated_at,
        metadata={
            "workflow_slug": run.workflow_slug,
            "provider": _string(result.get("provider")) or run.provider,
            "run_status": run.status,
            "mock_task_id": _string(result.get("mock_task_id")),
            "mock_vm_id": _string(result.get("mock_vm_id")),
            "message": _string(result.get("message")) or run.error_message or "",
        },
    )


def _request_history_artifact(session: Session, request: Request) -> dict[str, Any]:
    audit = _audit_summary(session, request_id=request.id)
    return _artifact(
        id_=f"{request.id}:request-history",
        request_id=request.id,
        workflow_run_id=None,
        kind="audit_history",
        title="Request History",
        description="Request-scoped audit history is available through the audit event API and UI.",
        status="available" if audit["event_count"] else "pending",
        created_at=request.created_at,
        updated_at=request.updated_at,
        metadata=audit,
    )


def _workflow_history_artifact(session: Session, run: WorkflowRun) -> dict[str, Any]:
    audit = _audit_summary(session, request_id=run.request_id, workflow_run_id=run.id)
    return _artifact(
        id_=f"{run.id}:run-history",
        request_id=run.request_id,
        workflow_run_id=run.id,
        kind="run_history",
        title="Run History",
        description="Request and run audit events are linked for operator handoff.",
        status="available" if audit["event_count"] else "pending",
        created_at=run.created_at,
        updated_at=run.updated_at,
        metadata=audit,
    )


def _debug_bundle_placeholder(
    *,
    request_id: str,
    updated_at: datetime,
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    return _artifact(
        id_=f"{workflow_run_id or request_id}:debug-bundle-placeholder",
        request_id=request_id,
        workflow_run_id=workflow_run_id,
        kind="debug_bundle",
        title="Redacted Debug Bundle",
        description=(
            "Placeholder only. No local files are collected; future bundles must redact secrets "
            "before packaging."
        ),
        status="placeholder",
        created_at=updated_at,
        updated_at=updated_at,
        metadata={
            "generated": False,
            "redaction_required": True,
            "contains_local_data": False,
        },
    )


def _export_placeholder(
    *,
    request_id: str,
    updated_at: datetime,
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    return _artifact(
        id_=f"{workflow_run_id or request_id}:export-placeholder",
        request_id=request_id,
        workflow_run_id=workflow_run_id,
        kind="export",
        title="Export Package",
        description="Placeholder only. No report archive, debug bundle, or provider artifact is generated.",
        status="placeholder",
        created_at=updated_at,
        updated_at=updated_at,
        metadata={
            "generated": False,
            "download_available": False,
            "mock_only": True,
        },
    )


def _audit_summary(
    session: Session,
    *,
    request_id: str,
    workflow_run_id: str | None = None,
) -> dict[str, Any]:
    clauses = [AuditEvent.request_id == request_id]
    if workflow_run_id:
        clauses.append(AuditEvent.workflow_run_id == workflow_run_id)

    events = list(
        session.execute(
            select(AuditEvent).where(or_(*clauses)).order_by(AuditEvent.created_at.desc())
        ).scalars()
    )
    event_types = sorted({event.event_type for event in events})
    latest = events[0].created_at.isoformat() if events else None
    return {
        "event_count": len(events),
        "event_types": event_types,
        "latest_event_time": latest,
    }


def _artifact(
    *,
    id_: str,
    request_id: str,
    workflow_run_id: str | None,
    kind: str,
    title: str,
    description: str,
    status: str,
    created_at: datetime,
    updated_at: datetime,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": id_,
        "request_id": request_id,
        "workflow_run_id": workflow_run_id,
        "kind": kind,
        "title": title,
        "description": description,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "mock_only": True,
        "redacted": True,
        "downloadable": False,
        "download_url": None,
        "metadata": metadata,
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""
