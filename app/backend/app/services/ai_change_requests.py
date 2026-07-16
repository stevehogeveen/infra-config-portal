from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.providers.redaction import redact_sensitive
from app.schemas import AiChangeRequestCreate, AiChangeRequestRead


MAILBOX_IDENTITY_VALUE_RE = re.compile(
    r"(?i)\b(hostname|fqdn|customer|client|account|serial(?:_?number)?|ip(?:_?address)?)"
    r"(\s*[=:]\s*)([^,\s;]+)"
)
MAILBOX_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
MAILBOX_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


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
    _append_agent_chat_notice(root, payload, request_id, created_at, relative_artifact)
    return AiChangeRequestRead(
        request_id=request_id,
        status="queued",
        artifact=relative_artifact,
        message="Sent to the Claude+Codex mailbox and saved as a review artifact.",
        next_action="Claude and Codex read docs/agent-chat.md; implement on a branch, fast-verify, and request review before applying.",
    )


def _append_agent_chat_notice(
    root: Path,
    payload: AiChangeRequestCreate,
    request_id: str,
    created_at: datetime,
    relative_artifact: str,
) -> None:
    mailbox = root / "docs" / "agent-chat.md"
    mailbox.parent.mkdir(parents=True, exist_ok=True)
    safe_page = _mailbox_safe_text(payload.page)
    safe_route = _mailbox_safe_text(payload.route)
    safe_target = _mailbox_safe_text(payload.target or "not specified")
    safe_request = _mailbox_safe_text(payload.request)
    mailbox_entry = "\n".join(
        [
            "",
            "---",
            "",
            f"## {created_at.strftime('%Y-%m-%d %H:%M UTC')} - APP QUEUE",
            "",
            f"New AI change request queued: `{relative_artifact}`",
            "",
            f"- request_id: `{request_id}`",
            f"- page: `{safe_page}`",
            f"- route: `{safe_route}`",
            f"- target: `{safe_target}`",
            "- status: sent to Claude+Codex mailbox; capture-only, no workflow ran.",
            "",
            "Operator request:",
            "",
            f"> {safe_request}",
            "",
        ]
    )
    with mailbox.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(mailbox_entry)


def _mailbox_safe_text(value: str) -> str:
    redacted = str(redact_sensitive(value))
    redacted = MAILBOX_IDENTITY_VALUE_RE.sub(r"\1\2REDACTED", redacted)
    redacted = MAILBOX_EMAIL_RE.sub("REDACTED_EMAIL", redacted)
    return MAILBOX_IPV4_RE.sub("REDACTED_IP", redacted)


def _markdown(payload: AiChangeRequestCreate, request_id: str, created_at: datetime) -> str:
    regions = [{"id": region.id, "label": region.label, "kind": region.kind} for region in payload.regions]
    layout = {key: value.model_dump() for key, value in payload.current_layout.items()}
    return "\n".join(
        [
            f"# AI change request {request_id}",
            "",
            "- status: queued",
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
