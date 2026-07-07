from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.services.path_utils import path_exists as _path_exists

TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    if not normalized:
        return default
    return default


def env_flag(name: str) -> bool:
    return bool_value(os.getenv(name))


def int_value(value: Any, default: int, *, minimum: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def float_value(value: Any, default: float, *, minimum: float | None = None) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    return int_value(os.getenv(name), default, minimum=minimum)


def env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    return float_value(os.getenv(name), default, minimum=minimum)


def load_env_file(
    path: Path,
    *,
    overwrite: bool = False,
    skip_keys: set[str] | None = None,
) -> dict[str, str]:
    if not _path_exists(path):
        return {}

    loaded: dict[str, str] = {}
    for key, value in read_env_file_values(path, skip_keys=skip_keys).items():
        if not overwrite and key in os.environ:
            continue
        os.environ[key] = value
        loaded[key] = value
    return loaded


def read_env_file_values(path: Path, *, skip_keys: set[str] | None = None) -> dict[str, str]:
    if not _path_exists(path):
        return {}

    skipped = skip_keys or set()
    try:
        values = dotenv_values(path)
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return {key: value for key, value in values.items() if value is not None and key not in skipped}


def load_real_lab_env(
    repo_root: Path,
    *,
    overwrite: bool = False,
    skip_keys: set[str] | None = None,
) -> dict[str, str]:
    return load_env_file(
        repo_root / ".env.local.real-lab",
        overwrite=overwrite,
        skip_keys=skip_keys,
    )
