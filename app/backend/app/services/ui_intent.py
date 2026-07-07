from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.schemas import UiIntentOpRead, UiIntentRequest, UiIntentResponse


HIDE_WORDS = ("hide", "remove", "declutter", "clean", "simplify", "less", "clutter")
SHOW_WORDS = ("show", "restore", "bring back", "unhide")
COLLAPSE_WORDS = ("collapse", "fold", "minimize")
EXPAND_WORDS = ("expand", "open")
UP_WORDS = ("move up", "higher", "prioritize", "first")
DOWN_WORDS = ("move down", "lower", "last")
ADVANCED_WORDS = ("advanced", "proof", "details", "evidence")
ALLOWED_OPS = {"hide", "show", "collapse", "expand", "moveUp", "moveDown"}
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
SECRET_RE = re.compile(
    r"((?:password|token|secret)\s*=\s*)\S+|(bearer\s+)\S+|-----begin|private[_ -]?key",
    re.IGNORECASE,
)


def resolve_ui_intent(payload: UiIntentRequest) -> UiIntentResponse:
    """Resolve safe page-layout intent against the caller's region allowlist."""
    allowed = {region.id: region for region in payload.regions}
    if not allowed:
        return UiIntentResponse(ops=[], summary="No page regions were available to change.")

    ai_response = _resolve_with_anthropic(payload, allowed)
    if ai_response is not None:
        return ai_response

    return resolve_ui_intent_locally(payload, allowed)


def resolve_ui_intent_locally(
    payload: UiIntentRequest,
    allowed: dict[str, object] | None = None,
) -> UiIntentResponse:
    allowed = allowed or {region.id: region for region in payload.regions}
    request = _normalize(payload.request)
    ops: list[UiIntentOpRead] = []

    selected = _matching_regions(request, payload)
    if not selected and any(word in request for word in ADVANCED_WORDS):
        selected = [
            region.id
            for region in payload.regions
            if any(word in _normalize(f"{region.id} {region.label}") for word in ADVANCED_WORDS)
        ]
    if not selected and any(word in request for word in ("clutter", "clean", "simplify", "less")):
        selected = [
            region.id
            for region in payload.regions
            if region.id != "primary" and any(word in _normalize(f"{region.id} {region.label}") for word in ADVANCED_WORDS)
        ]

    op = _requested_op(request)
    if op and selected:
        ops = [UiIntentOpRead(region_id=region_id, op=op) for region_id in selected if region_id in allowed]

    summary = _summary(ops, allowed)
    return UiIntentResponse(ops=ops, summary=summary, source="local_rules")


def _resolve_with_anthropic(payload: UiIntentRequest, allowed: dict[str, object]) -> UiIntentResponse | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("ANTHROPIC_UI_INTENT_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-opus-4-8")).strip()
    request_payload = _anthropic_request_payload(payload, model)
    try:
        with httpx.Client(timeout=12.0) as client:
            response = client.post(
                ANTHROPIC_MESSAGES_URL,
                headers={
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                    "x-api-key": api_key,
                },
                json=request_payload,
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    raw = _extract_anthropic_tool_input(data)
    if not isinstance(raw, dict):
        return None
    ops = _validated_ops(raw.get("ops"), allowed)
    summary = raw.get("summary") if isinstance(raw.get("summary"), str) else _summary(ops, allowed)
    return UiIntentResponse(ops=ops, summary=summary[:240], source="external_ai")


def _anthropic_request_payload(payload: UiIntentRequest, model: str) -> dict[str, Any]:
    regions = [{"id": region.id, "label": region.label, "kind": region.kind} for region in payload.regions]
    layout = {key: value.model_dump() for key, value in payload.current_layout.items()}
    operator_payload = {
        "page": payload.page,
        "request": _redact_for_ai(payload.request),
        "regions": regions,
        "current_layout": layout,
    }
    return {
        "model": model,
        "max_tokens": 500,
        "temperature": 0,
        "tools": [
            {
                "name": "resolve_ui_intent",
                "description": "Return only safe page layout operations against the provided region manifest.",
                "input_schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "ops": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "region_id": {"type": "string"},
                                    "op": {"type": "string", "enum": sorted(ALLOWED_OPS)},
                                },
                                "required": ["region_id", "op"],
                            },
                        },
                        "summary": {"type": "string"},
                    },
                    "required": ["ops", "summary"],
                },
            }
        ],
        "tool_choice": {"type": "tool", "name": "resolve_ui_intent"},
        "messages": [
            {
                "role": "user",
                "content": (
                    "Classify this operator request into reversible layout operations only. "
                    "Allowed operations are hide, show, collapse, expand, moveUp, moveDown. "
                    "Use only region IDs from the manifest. If the request asks for data changes, "
                    "workflow actions, settings, code edits, RAID, factory reset, rebuild, or anything "
                    "outside layout, return an empty ops array.\n\n"
                    f"{json.dumps(operator_payload, indent=2)}"
                ),
            }
        ],
    }


def _extract_anthropic_tool_input(data: dict[str, Any]) -> dict[str, Any] | None:
    content = data.get("content")
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "resolve_ui_intent":
            tool_input = block.get("input")
            return tool_input if isinstance(tool_input, dict) else None
    return None


def _validated_ops(value: object, allowed: dict[str, object]) -> list[UiIntentOpRead]:
    if not isinstance(value, list):
        return []
    ops: list[UiIntentOpRead] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        region_id = item.get("region_id")
        op = item.get("op")
        if isinstance(region_id, str) and region_id in allowed and isinstance(op, str) and op in ALLOWED_OPS:
            ops.append(UiIntentOpRead(region_id=region_id, op=op))
    return ops


def _redact_for_ai(value: str) -> str:
    if SECRET_RE.search(value):
        return SECRET_RE.sub(lambda match: f"{match.group(1) or match.group(2) or ''}[REDACTED]", value)
    return value


def _requested_op(request: str) -> str | None:
    if any(word in request for word in SHOW_WORDS):
        return "show"
    if any(word in request for word in EXPAND_WORDS):
        return "expand"
    if any(word in request for word in COLLAPSE_WORDS):
        return "collapse"
    if any(word in request for word in UP_WORDS):
        return "moveUp"
    if any(word in request for word in DOWN_WORDS):
        return "moveDown"
    if any(word in request for word in HIDE_WORDS):
        return "hide"
    return None


def _matching_regions(request: str, payload: UiIntentRequest) -> list[str]:
    matches: list[str] = []
    for region in payload.regions:
        haystack = _normalize(f"{region.id} {region.label}")
        if any(token and token in request for token in _significant_tokens(haystack)):
            matches.append(region.id)
    return matches


def _significant_tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value) if len(token) >= 4]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _summary(ops: list[UiIntentOpRead], allowed: dict[str, object]) -> str:
    if not ops:
        return "No safe layout change matched this page."
    labels = []
    for op in ops:
        region = allowed.get(op.region_id)
        labels.append(getattr(region, "label", op.region_id))
    action = {
        "hide": "Hid",
        "show": "Showed",
        "collapse": "Collapsed",
        "expand": "Expanded",
        "moveUp": "Moved up",
        "moveDown": "Moved down",
    }.get(ops[0].op, "Changed")
    return f"{action}: {', '.join(labels)}."
