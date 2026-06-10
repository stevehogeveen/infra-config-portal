from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SourceType = str
Freshness = str

LIVE_SOURCE_TYPES = {"live_probe", "live_cached"}
VALID_SOURCE_TYPES = LIVE_SOURCE_TYPES | {"historical_artifact", "test_fixture", "not_checked"}
DEFAULT_STALE_AFTER_SECONDS = 24 * 60 * 60


def status_source_metadata(
    *,
    source_type: SourceType,
    checked_at: Any = None,
    stale_after_seconds: int | None = DEFAULT_STALE_AFTER_SECONDS,
    recheck_command: str | None = None,
    evidence_artifacts: list[str] | tuple[str, ...] | None = None,
    is_operator_visible: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_source = _normalize_source_type(source_type)
    normalized_checked_at = _datetime_iso(_parse_datetime(checked_at))
    freshness = _freshness_for(
        normalized_source,
        checked_at=normalized_checked_at,
        stale_after_seconds=stale_after_seconds,
        now=now or datetime.now(UTC),
    )
    return {
        "source_type": normalized_source,
        "checked_at": normalized_checked_at,
        "freshness": freshness,
        "ttl_seconds": stale_after_seconds,
        "stale_after_seconds": stale_after_seconds,
        "is_current": _is_current(normalized_source, freshness),
        "is_operator_visible": (
            normalized_source != "test_fixture"
            if is_operator_visible is None
            else bool(is_operator_visible)
        ),
        "recheck_command": recheck_command,
        "evidence_artifacts": _unique(evidence_artifacts or []),
    }


def attach_status_source(
    payload: dict[str, Any],
    *,
    source_type: SourceType,
    checked_at: Any = None,
    stale_after_seconds: int | None = DEFAULT_STALE_AFTER_SECONDS,
    recheck_command: str | None = None,
    evidence_artifacts: list[str] | tuple[str, ...] | None = None,
    is_operator_visible: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    metadata = status_source_metadata(
        source_type=source_type,
        checked_at=checked_at if checked_at is not None else payload.get("checked_at"),
        stale_after_seconds=stale_after_seconds,
        recheck_command=recheck_command,
        evidence_artifacts=evidence_artifacts,
        is_operator_visible=is_operator_visible,
        now=now,
    )
    return {**payload, **metadata}


def source_type_for_provider_mode(provider_mode: str) -> SourceType:
    return "test_fixture" if provider_mode == "mock" else "live_cached"


def can_source_block(source_type: SourceType, freshness: Freshness, *, is_current: bool) -> bool:
    normalized_source = _normalize_source_type(source_type)
    if normalized_source == "live_probe":
        return True
    if normalized_source == "live_cached":
        return bool(is_current) and freshness == "current"
    return False


def _freshness_for(
    source_type: SourceType,
    *,
    checked_at: str | None,
    stale_after_seconds: int | None,
    now: datetime,
) -> Freshness:
    if source_type == "live_probe":
        return "current"
    if source_type == "live_cached":
        checked = _parse_datetime(checked_at)
        if checked is None or stale_after_seconds is None:
            return "unknown"
        return "current" if (now - checked).total_seconds() <= stale_after_seconds else "stale"
    if source_type == "historical_artifact":
        return "stale" if checked_at else "unknown"
    return "unknown"


def _is_current(source_type: SourceType, freshness: Freshness) -> bool:
    return source_type == "live_probe" or (
        source_type == "live_cached" and freshness == "current"
    )


def _normalize_source_type(value: Any) -> SourceType:
    text = str(value or "").strip()
    return text if text in VALID_SOURCE_TYPES else "not_checked"


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _datetime_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _unique(values: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
