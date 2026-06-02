from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_PROBE_RESULTS: dict[str, dict[str, Any]] = {}


def record_probe_result(provider_id: str, result: dict[str, Any]) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    stored = {**result, "checked_at": checked_at}
    _PROBE_RESULTS[provider_id] = stored
    return stored


def get_probe_result(provider_id: str) -> tuple[dict[str, Any] | None, str | None]:
    result = _PROBE_RESULTS.get(provider_id)
    if result is None:
        return None, None
    checked_at = result.get("checked_at")
    return result, checked_at if isinstance(checked_at, str) else None


def clear_probe_results() -> None:
    _PROBE_RESULTS.clear()
