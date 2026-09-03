from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from app.services.json_utils import parse_json_object
from app.services.path_utils import filesystem_path

MAX_TEMP_PREFIX_NAME_CHARS = 48


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        filesystem_path = _filesystem_path(path)
        if not os.path.exists(filesystem_path):
            return {}
        with open(filesystem_path, "rb") as handle:
            return parse_json_object(handle.read())
    except OSError:
        return {}


def write_json_object(path: Path, payload: dict[str, Any], *, default: Any = None) -> None:
    write_json_value(path, payload, default=default)


def write_json_value(path: Path, payload: Any, *, default: Any = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
        prefix=f".{_temp_prefix_name(path.name)}.{os.getpid()}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            json.dump(payload, temp_file, indent=2, sort_keys=True, default=default)
            temp_file.write("\n")
        _replace_with_retry(temp_path, path)
    except BaseException:
        _unlink_temp_best_effort(temp_path)
        raise


def write_text_value(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=path.parent,
        encoding="utf-8",
        prefix=f".{_temp_prefix_name(path.name)}.{os.getpid()}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_file.name)
    try:
        with temp_file:
            temp_file.write(text)
        _replace_with_retry(temp_path, path)
    except BaseException:
        _unlink_temp_best_effort(temp_path)
        raise


def _replace_with_retry(source: Path, target: Path) -> None:
    for attempt in range(6):
        try:
            os.replace(_filesystem_path(source), _filesystem_path(target))
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def _temp_prefix_name(name: str) -> str:
    return name[:MAX_TEMP_PREFIX_NAME_CHARS] or "json"


def _unlink_temp_best_effort(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _filesystem_path(path: Path) -> str:
    return filesystem_path(path)
