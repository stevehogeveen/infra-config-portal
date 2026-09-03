from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def repo_relative_path(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return repo_relative_path(path, repo_root)
    except ValueError:
        return str(path)


def path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def path_state(path: Path) -> str:
    try:
        return "present" if path.exists() else "missing"
    except OSError:
        return "unreadable"


def directory_state(path: Path) -> str:
    try:
        if not path.exists():
            return "missing"
        if path.is_dir():
            return "directory"
    except OSError:
        return "unreadable"
    return "not_directory"


def glob_paths(path: Path, pattern: str) -> list[Path]:
    try:
        return list(path.glob(pattern))
    except OSError:
        return []


def rglob_paths(path: Path, pattern: str) -> list[Path]:
    return rglob_paths_or_none(path, pattern) or []


def rglob_paths_or_none(path: Path, pattern: str) -> list[Path] | None:
    try:
        return list(path.rglob(pattern))
    except OSError:
        return None


def is_directory(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir()
    except OSError:
        return False


def is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def file_state(path: Path) -> str:
    try:
        return "file" if path.is_file() else "not_file"
    except OSError:
        return "unreadable"


def file_size(path: Path) -> int | None:
    stat_result = path_stat(path)
    return int(stat_result.st_size) if stat_result is not None else None


def file_mode(path: Path) -> str | None:
    if not path_exists(path):
        return None
    stat_result = path_stat(path)
    return oct(stat_result.st_mode & 0o777) if stat_result is not None else None


def path_mtime(path: Path) -> float | None:
    stat_result = path_stat(path)
    return float(stat_result.st_mtime) if stat_result is not None else None


def path_stat(path: Path) -> Any | None:
    try:
        return path.stat()
    except OSError:
        return None


def safe_read_text(path: Path, *, default: str = "", errors: str = "replace") -> str:
    try:
        return path.read_text(encoding="utf-8", errors=errors)
    except (OSError, UnicodeDecodeError, ValueError):
        return default


def filesystem_path(path: Path) -> str:
    text = str(path)
    if os.name != "nt":
        return text
    resolved = str(path.resolve(strict=False))
    if resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved.lstrip("\\")
    return "\\\\?\\" + resolved
