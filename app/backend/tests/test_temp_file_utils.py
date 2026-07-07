from __future__ import annotations

from pathlib import Path

from app.services import temp_file_utils
from app.services.path_utils import filesystem_path
from app.services.temp_file_utils import remove_file_best_effort


def test_remove_file_best_effort_deletes_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "scratch.json"
    path.write_text('{"status": "temporary"}\n', encoding="utf-8")

    assert remove_file_best_effort(path) is True

    assert not path.exists()


def test_remove_file_best_effort_treats_missing_file_as_clean(tmp_path: Path) -> None:
    assert remove_file_best_effort(tmp_path / "missing.json") is True


def test_remove_file_best_effort_scrubs_sensitive_file_when_unlink_fails(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "vcsa-spec.json"
    path.write_text('{"password": "super-secret"}\n', encoding="utf-8")
    original_unlink = temp_file_utils.os.unlink
    locked_path = filesystem_path(path)

    def locked_unlink(candidate: str) -> None:
        if candidate == locked_path:
            raise PermissionError("locked")
        original_unlink(candidate)

    with monkeypatch.context() as scoped:
        scoped.setattr(temp_file_utils.os, "unlink", locked_unlink)

        assert remove_file_best_effort(path, scrub=True) is False

    assert path.exists()
    assert path.read_text(encoding="utf-8") == ""


def test_remove_file_best_effort_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "vcsa-spec.json"
    path.write_text('{"password": "super-secret"}\n', encoding="utf-8")
    original_exists = temp_file_utils.os.path.exists
    checked_path = filesystem_path(path)

    def flaky_exists(candidate: str) -> bool:
        if candidate == checked_path:
            raise OSError("path unavailable")
        return original_exists(candidate)

    monkeypatch.setattr(temp_file_utils.os.path, "exists", flaky_exists)

    assert remove_file_best_effort(path, scrub=True) is True
    assert not path.exists()


def test_remove_file_best_effort_uses_filesystem_path_for_cleanup(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "scratch.json"
    path.write_text("temporary\n", encoding="utf-8")
    calls: list[str] = []
    original_unlink = temp_file_utils.os.unlink

    def recording_unlink(candidate: str) -> None:
        calls.append(candidate)
        original_unlink(candidate)

    monkeypatch.setattr(temp_file_utils.os, "unlink", recording_unlink)

    assert remove_file_best_effort(path) is True

    assert calls == [filesystem_path(path)]
