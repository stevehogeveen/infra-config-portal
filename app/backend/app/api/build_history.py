"""Run history for operators: the meaningful records (results, completions, failures, saved
plans, permission changes) from the audit trail, newest first. Polling noise (observations,
previews, progress ticks, periodic checks) is left out. Reads the database only."""

import re
from datetime import timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import AuditEvent

router = APIRouter(prefix="/api/v1", tags=["build history"])

KEEP = re.compile(r"(\.result|\.done|\.verified|\.failed|_failed|\.closed\w*|_saved|\.saved|\.applied|\.settings|_planned|\.finished)$")
SKIP = re.compile(r"(observation|observed|preview|progress|_check|diagnosis|busy|heartbeat|capabilities_read|\.queued)")
AREAS = (("windows", "Windows"), ("esxi", "ESXi"), ("raid", "Disks & RAID"), ("disk", "Disks & RAID"), ("parts_update", "Firmware"),
         ("firmware", "Firmware"), ("spp", "Firmware"), ("switch", "Switch"), ("write_scope", "Permissions"), ("rack_plan", "Rack layout"),
         ("inventory", "Server check"), ("ilo", "Server"))


def _area(event_type: str) -> str:
    return next((label for key, label in AREAS if key in event_type), "Lab Builder")


def _outcome(event: AuditEvent) -> str:
    data = event.data_json if isinstance(event.data_json, dict) else {}
    value = str(data.get("outcome") or data.get("status") or event.to_status or "").lower()
    if event.event_type.endswith(("failed", "closed_unverified")) or value in {"failed", "blocked", "error"}:
        return "failed"
    if value in {"uncertain", "needs_attention", "unknown"}:
        return "attention"
    if value in {"ok", "verified", "completed", "succeeded", "success"} or event.event_type.endswith(".verified"):
        return "ok"
    return "info"


@router.get("/build-history")
def build_history(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)):
    # Read newest first in batches until enough meaningful records are found, so a burst of
    # polling records can never hide older results.
    out, offset, batch = [], 0, 2000
    while len(out) < limit:
        rows = list(session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                                    .offset(offset).limit(batch)))
        if not rows:
            break
        offset += len(rows)
        for event in rows:
            if SKIP.search(event.event_type) or not KEEP.search(event.event_type):
                continue
            at = event.created_at if event.created_at.tzinfo else event.created_at.replace(tzinfo=timezone.utc)
            out.append({"id": event.id, "at": at.isoformat(), "area": _area(event.event_type),
                        "message": event.message, "outcome": _outcome(event), "actor": event.actor})
            if len(out) >= limit:
                break
    return out
