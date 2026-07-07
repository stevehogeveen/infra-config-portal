from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.schemas import AiChangeRequestCreate, AiChangeRequestRead


def create_ai_change_request(payload: AiChangeRequestCreate) -> AiChangeRequestRead:
    created_at = datetime.now(UTC)
    request_id = created_at.strftime("%Y%m%dT%H%M%SZ")
    safe_page = _slug(payload.page) or "page"
    root = Path(__file__).resolve().parents[3]
    request_dir = root / "docs" / "change-requests"
    request_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = request_dir / f"{request_id}-{safe_page}.md"
    relative_artifact = artifact_path.relative_to(root).as_posix()

    artifact_path.write_text(_markdown(payload, request_id, created_at), encoding="utf-8")
    return AiChangeRequestRead(
        request_id=request_id,
        status="queued",
        artifact=relative_artifact,
        message="Change request queued for the Claude+Codex build loop.",
        next_action="Review the markdown artifact, branch, implement, fast-verify, and request review before applying.",
    )


def _markdown(payload: AiChangeRequestCreate, request_id: str, created_at: datetime) -> str:
    regions = [{"id": region.id, "label": region.label, "kind": region.kind} for region in payload.regions]
    layout = {key: value.model_dump() for key, value in payload.current_layout.items()}
    return "\n".join(
        [
            f"# AI change request {request_id}",
            "",
            f"- status: queued",
            f"- created_at: {created_at.isoformat()}",
            f"- page: {payload.page}",
            f"- route: {payload.route}",
            f"- target: {payload.target or 'not specified'}",
            f"- screenshot: {payload.screenshot_path or 'not captured by the in-app queue'}",
            "",
            "## Operator Request",
            "",
            payload.request,
            "",
            "## Safety Boundary",
            "",
            "This artifact is capture-only. It does not execute code, change settings, run workflow actions, or touch hardware. Any implementation must happen on a branch and pass fast-verify plus review before apply.",
            "",
            "## Region Manifest",
            "",
            "```json",
            json.dumps(regions, indent=2),
            "```",
            "",
            "## Current Layout",
            "",
            "```json",
            json.dumps(layout, indent=2),
            "```",
            "",
        ]
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
