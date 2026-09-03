from __future__ import annotations

from pathlib import Path

from app.services import path_utils
from app.services.path_utils import (
    display_path,
    directory_state,
    filesystem_path,
    file_mode,
    file_size,
    file_state,
    glob_paths,
    is_directory,
    is_file,
    path_mtime,
    path_exists,
    path_stat,
    path_state,
    rglob_paths,
    rglob_paths_or_none,
    repo_relative_path,
    safe_read_text,
)


def test_repo_relative_path_uses_posix_separators(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "codex-runs" / "report.md"

    assert repo_relative_path(path, tmp_path) == "artifacts/codex-runs/report.md"


def test_display_path_handles_paths_outside_repo(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-report.md"

    assert display_path(outside, tmp_path).endswith("outside-report.md")


def test_safe_path_helpers_return_false_on_probe_errors(monkeypatch, tmp_path: Path) -> None:
    file_path = tmp_path / "locked.txt"
    file_path.write_text("locked", encoding="utf-8")
    original_exists = Path.exists
    original_is_dir = Path.is_dir
    original_is_file = Path.is_file
    original_stat = Path.stat

    def flaky_exists(path: Path) -> bool:
        if path == file_path:
            raise OSError("exists unavailable")
        return original_exists(path)

    def flaky_is_dir(path: Path) -> bool:
        if path == file_path:
            raise OSError("is_dir unavailable")
        return original_is_dir(path)

    def flaky_is_file(path: Path) -> bool:
        if path == file_path:
            raise OSError("is_file unavailable")
        return original_is_file(path)

    def flaky_stat(path: Path, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if path == file_path:
            raise OSError("stat unavailable")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", flaky_exists)
    assert path_exists(file_path) is False
    assert path_state(file_path) == "unreadable"
    assert directory_state(file_path) == "unreadable"
    assert is_directory(file_path) is False

    monkeypatch.setattr(Path, "exists", original_exists)
    monkeypatch.setattr(Path, "is_dir", flaky_is_dir)
    assert is_directory(file_path) is False

    monkeypatch.setattr(Path, "is_file", flaky_is_file)
    assert is_file(file_path) is False
    assert file_state(file_path) == "unreadable"

    monkeypatch.setattr(Path, "stat", flaky_stat)
    assert path_stat(file_path) is None
    assert file_mode(file_path) is None
    assert file_size(file_path) is None


def test_safe_path_helpers_report_normal_file_and_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "media.iso"
    file_path.write_bytes(b"iso")
    (tmp_path / "template.ovf").write_bytes(b"ovf")

    assert path_exists(file_path) is True
    assert path_state(file_path) == "present"
    assert path_state(tmp_path / "missing.iso") == "missing"
    assert directory_state(tmp_path) == "directory"
    assert directory_state(file_path) == "not_directory"
    assert directory_state(tmp_path / "missing") == "missing"
    assert is_file(file_path) is True
    assert file_state(file_path) == "file"
    assert path_stat(file_path) is not None
    assert file_mode(file_path) is not None
    assert file_size(file_path) == 3
    assert file_state(tmp_path) == "not_file"
    assert is_directory(tmp_path) is True
    assert glob_paths(tmp_path, "*.iso") == [file_path]
    assert rglob_paths(tmp_path, "*.iso") == [file_path]
    assert rglob_paths_or_none(tmp_path, "*.iso") == [file_path]


def test_glob_paths_returns_empty_list_on_probe_errors(monkeypatch, tmp_path: Path) -> None:
    original_glob = Path.glob

    def flaky_glob(path: Path, pattern: str):  # noqa: ANN202
        if path == tmp_path:
            raise OSError("glob unavailable")
        return original_glob(path, pattern)

    monkeypatch.setattr(Path, "glob", flaky_glob)

    assert glob_paths(tmp_path, "*.iso") == []


def test_rglob_paths_returns_empty_list_on_probe_errors(monkeypatch, tmp_path: Path) -> None:
    original_rglob = Path.rglob

    def flaky_rglob(path: Path, pattern: str):  # noqa: ANN202
        if path == tmp_path:
            raise OSError("recursive glob unavailable")
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", flaky_rglob)

    assert rglob_paths(tmp_path, "*.iso") == []
    assert rglob_paths_or_none(tmp_path, "*.iso") is None


def test_safe_read_text_returns_default_on_read_errors(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text("ready\n", encoding="utf-8")
    original_read_text = Path.read_text

    def locked_read_text(candidate: Path, *args, **kwargs) -> str:  # noqa: ANN002, ANN003
        if candidate == path:
            raise OSError("locked")
        return original_read_text(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", locked_read_text)

    assert safe_read_text(path, default="fallback") == "fallback"


def test_safe_read_text_replaces_invalid_utf8_by_default(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_bytes(b"Status: ready\n\xff")

    assert safe_read_text(path).startswith("Status: ready")
    assert safe_read_text(path, errors="strict", default="fallback") == "fallback"


def test_path_mtime_returns_none_on_stat_errors(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text("ready\n", encoding="utf-8")
    original_stat = Path.stat

    def disappearing_stat(candidate: Path, *args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        if candidate == path:
            raise FileNotFoundError("gone")
        return original_stat(candidate, *args, **kwargs)

    assert path_mtime(path) == original_stat(path).st_mtime

    monkeypatch.setattr(Path, "stat", disappearing_stat)

    assert path_mtime(path) is None


def test_filesystem_path_returns_plain_path_on_non_windows(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    monkeypatch.setattr(path_utils.os, "name", "posix")

    assert filesystem_path(path) == str(path)


def test_filesystem_path_adds_windows_long_path_prefix(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    monkeypatch.setattr(path_utils.os, "name", "nt")

    assert filesystem_path(path).startswith("\\\\?\\")
