from __future__ import annotations

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
