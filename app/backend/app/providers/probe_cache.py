from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
CACHE_DIR = REPO_ROOT / "artifacts" / "codex-runs" / "provider-probe-cache"

_PROBE_RESULTS: dict[str, dict[str, Any]] = {}


def record_probe_result(provider_id: str, result: dict[str, Any]) -> dict[str, Any]:
    checked_at = datetime.now(UTC).isoformat()
    stored = {**result, "checked_at": checked_at}
    _PROBE_RESULTS[provider_id] = stored
    _write_probe_result(provider_id, stored)
    return stored


def get_probe_result(provider_id: str) -> tuple[dict[str, Any] | None, str | None]:
    result = _PROBE_RESULTS.get(provider_id) or _read_probe_result(provider_id)
    if result is None:
        return None, None
    _PROBE_RESULTS[provider_id] = result
    checked_at = result.get("checked_at")
    return result, checked_at if isinstance(checked_at, str) else None


def clear_probe_results() -> None:
    _PROBE_RESULTS.clear()
    if not CACHE_DIR.exists():
        return
    for path in CACHE_DIR.glob("*.json"):
        path.unlink()


def _write_probe_result(provider_id: str, result: dict[str, Any]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(provider_id).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return


def _read_probe_result(provider_id: str) -> dict[str, Any] | None:
    path = _cache_path(provider_id)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _cache_path(provider_id: str) -> Path:
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in provider_id)
    return CACHE_DIR / f"{safe}.json"
