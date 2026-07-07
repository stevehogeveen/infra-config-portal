from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.services.json_file_store import read_json_object, write_json_object
from app.services.path_utils import glob_paths, path_exists
from app.services.temp_file_utils import remove_file_best_effort

REPO_ROOT = Path(__file__).resolve().parents[4]
CACHE_DIR = REPO_ROOT / "artifacts" / "codex-runs" / "provider-probe-cache"
MAX_CACHE_FILENAME_CHARS = 120
MAX_CACHE_KEY_PREFIX_CHARS = 72

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
    if not _cache_dir_exists():
        return
    for path in _cache_files():
        remove_file_best_effort(path)


def _write_probe_result(provider_id: str, result: dict[str, Any]) -> None:
    try:
        write_json_object(_cache_path(provider_id), result)
    except OSError:
        return


def _read_probe_result(provider_id: str) -> dict[str, Any] | None:
    path = _cache_path(provider_id)
    value = read_json_object(path)
    return value or None


def _cache_path(provider_id: str) -> Path:
    return CACHE_DIR / f"{_cache_key(provider_id)}.json"


def _cache_dir_exists() -> bool:
    return path_exists(CACHE_DIR)


def _cache_files() -> list[Path]:
    return glob_paths(CACHE_DIR, "*.json")


def _cache_key(provider_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in provider_id)
    safe = "-".join(part for part in safe.strip(".-").split("-") if part)[:MAX_CACHE_KEY_PREFIX_CHARS]
    digest = hashlib.sha256(provider_id.encode("utf-8")).hexdigest()[:16]
    prefix = safe or "provider"
    key = f"{prefix}-{digest}"
    return key[: MAX_CACHE_FILENAME_CHARS - len(".json")]
