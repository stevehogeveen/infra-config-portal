from __future__ import annotations

import os
from pathlib import Path

from app.core.config import _bool_env, _load_local_real_lab_env, _split_csv


def test_split_csv_trims_quotes_blanks_and_duplicates() -> None:
    assert _split_csv(" 'alpha' , beta, alpha, \"gamma\" , , beta ") == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_bool_env_accepts_common_true_like_values(monkeypatch) -> None:
    for value in ("1", "true", "TRUE", " yes ", "Y", "on"):
        monkeypatch.setenv("LAB_BOOL_TEST", value)
        assert _bool_env("LAB_BOOL_TEST", False) is True


def test_bool_env_defaults_and_rejects_false_like_values(monkeypatch) -> None:
    monkeypatch.delenv("LAB_BOOL_TEST", raising=False)
    assert _bool_env("LAB_BOOL_TEST", True) is True
    assert _bool_env("LAB_BOOL_TEST", False) is False

    for value in ("", "0", "false", "no", "off"):
        monkeypatch.setenv("LAB_BOOL_TEST", value)
        assert _bool_env("LAB_BOOL_TEST", True) is False


def test_load_local_real_lab_env_self_heals_path_probe_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INFRA_CONFIG_TEST_ISOLATE_REAL_LAB_ENV", "1")
    monkeypatch.delenv("REAL_LAB_SENTINEL", raising=False)
    target = tmp_path / ".env.local.real-lab"
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == target:
            raise OSError("path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    _load_local_real_lab_env()

    assert "REAL_LAB_SENTINEL" not in os.environ


def test_load_local_real_lab_env_self_heals_dotenv_read_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INFRA_CONFIG_TEST_ISOLATE_REAL_LAB_ENV", "1")
    monkeypatch.delenv("REAL_LAB_SENTINEL", raising=False)
    target = tmp_path / ".env.local.real-lab"
    target.write_text("REAL_LAB_SENTINEL=yes\n", encoding="utf-8")

    errors = [
        OSError("env file locked"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        ValueError("invalid dotenv value"),
    ]

    for error in errors:
        monkeypatch.setattr("app.core.config.dotenv_values", lambda _path, error=error: (_ for _ in ()).throw(error))

        _load_local_real_lab_env()

        assert "REAL_LAB_SENTINEL" not in os.environ
