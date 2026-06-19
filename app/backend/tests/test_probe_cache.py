from __future__ import annotations

import json
from pathlib import Path

from app.providers import probe_cache


def test_probe_cache_persists_across_memory_clear(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    probe_cache.clear_probe_results()

    stored = probe_cache.record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok"})
    probe_cache._PROBE_RESULTS.clear()

    result, checked_at = probe_cache.get_probe_result("ilo-redfish")

    assert result == stored
    assert checked_at == stored["checked_at"]


def test_probe_cache_prefers_newer_disk_result_over_stale_memory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    probe_cache.clear_probe_results()

    probe_cache._PROBE_RESULTS["ilo-redfish"] = {
        "provider_id": "ilo-redfish",
        "status": "ok",
        "checked_at": "2026-06-18T18:54:00+00:00",
        "systems": [],
    }
    disk_result = {
        "provider_id": "ilo-redfish",
        "status": "ok",
        "checked_at": "2026-06-18T18:56:00+00:00",
        "systems": [{"BiosVersion": "U46 v1.80 (07/05/2023)"}],
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "ilo-redfish.json").write_text(json.dumps(disk_result), encoding="utf-8")

    result, checked_at = probe_cache.get_probe_result("ilo-redfish")

    assert result == disk_result
    assert checked_at == "2026-06-18T18:56:00+00:00"
