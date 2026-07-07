from __future__ import annotations

import re

from app.schemas import UiIntentOpRead, UiIntentRequest, UiIntentResponse


HIDE_WORDS = ("hide", "remove", "declutter", "clean", "simplify", "less", "clutter")
SHOW_WORDS = ("show", "restore", "bring back", "unhide")
COLLAPSE_WORDS = ("collapse", "fold", "minimize")
EXPAND_WORDS = ("expand", "open")
UP_WORDS = ("move up", "higher", "prioritize", "first")
DOWN_WORDS = ("move down", "lower", "last")
ADVANCED_WORDS = ("advanced", "proof", "details", "evidence")


def resolve_ui_intent(payload: UiIntentRequest) -> UiIntentResponse:
    """Resolve safe page-layout intent against the caller's region allowlist."""
    allowed = {region.id: region for region in payload.regions}
    request = _normalize(payload.request)
    ops: list[UiIntentOpRead] = []

    if not allowed:
        return UiIntentResponse(ops=[], summary="No page regions were available to change.")

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
