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


def test_probe_cache_ignores_corrupt_persisted_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    probe_cache.clear_probe_results()
    probe_cache._cache_path("ilo-redfish").write_text("{not-json", encoding="utf-8")

    result, checked_at = probe_cache.get_probe_result("ilo-redfish")

    assert result is None
    assert checked_at is None


def test_probe_cache_clear_ignores_locked_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    locked = tmp_path / "locked.json"
    locked.write_text("{}", encoding="utf-8")

    def fake_unlink(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if self == locked:
            raise PermissionError("file is locked")
        return None

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    probe_cache.clear_probe_results()

    assert probe_cache._PROBE_RESULTS == {}


def test_probe_cache_clear_uses_best_effort_cleanup(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    removed: list[Path] = []

    def fake_remove(path: Path) -> bool:
        removed.append(path)
        return path != second

    monkeypatch.setattr(probe_cache, "remove_file_best_effort", fake_remove)

    probe_cache.clear_probe_results()

    assert removed == [first, second]
    assert probe_cache._PROBE_RESULTS == {}


def test_probe_cache_clear_ignores_unavailable_cache_directory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    probe_cache._PROBE_RESULTS["ilo-redfish"] = {"status": "ok"}
    original_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self == tmp_path:
            raise OSError("cache directory is unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    probe_cache.clear_probe_results()

    assert probe_cache._PROBE_RESULTS == {}


def test_probe_cache_clear_ignores_cache_glob_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    tmp_path.mkdir(exist_ok=True)
    probe_cache._PROBE_RESULTS["ilo-redfish"] = {"status": "ok"}
    original_glob = Path.glob

    def fake_glob(self: Path, pattern: str):  # noqa: ANN202
        if self == tmp_path and pattern == "*.json":
            raise OSError("cache directory cannot be listed")
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "glob", fake_glob)

    probe_cache.clear_probe_results()

    assert probe_cache._PROBE_RESULTS == {}


def test_probe_cache_uses_collision_resistant_safe_filenames(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    probe_cache.clear_probe_results()

    first = probe_cache.record_probe_result("provider:one", {"provider_id": "provider:one", "status": "ok"})
    second = probe_cache.record_probe_result("provider/one", {"provider_id": "provider/one", "status": "blocked"})
    probe_cache._PROBE_RESULTS.clear()

    paths = sorted(tmp_path.glob("*.json"))
    assert len(paths) == 2
    assert paths[0].name != paths[1].name
    assert not any(character in path.name for path in paths for character in '<>:"\\|?* ')
    assert probe_cache.get_probe_result("provider:one")[0] == first
    assert probe_cache.get_probe_result("provider/one")[0] == second


def test_probe_cache_bounds_long_provider_id_filename(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(probe_cache, "CACHE_DIR", tmp_path)
    probe_cache.clear_probe_results()
    provider_id = "provider-" + ("x" * 400)

    stored = probe_cache.record_probe_result(provider_id, {"provider_id": provider_id, "status": "ok"})
    probe_cache._PROBE_RESULTS.clear()
    path = next(tmp_path.glob("*.json"))

    assert len(path.name) <= probe_cache.MAX_CACHE_FILENAME_CHARS
    assert probe_cache.get_probe_result(provider_id)[0] == stored
