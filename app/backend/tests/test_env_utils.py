from __future__ import annotations

import os
from pathlib import Path

from app.services import env_utils
from app.services.env_utils import (
    bool_value,
    env_float,
    env_flag,
    env_int,
    float_value,
    int_value,
    load_env_file,
    load_real_lab_env,
    read_env_file_values,
)


def test_bool_value_accepts_common_true_like_values() -> None:
    for value in ("1", "true", "TRUE", " yes ", "Y", "on", True):
        assert bool_value(value) is True


def test_bool_value_rejects_false_like_and_empty_values() -> None:
    for value in ("0", "false", "no", "N", "off", False):
        assert bool_value(value) is False


def test_bool_value_uses_default_for_missing_blank_and_unknown_values() -> None:
    for value in (None, "", " ", "sometimes", object()):
        assert bool_value(value, True) is True
        assert bool_value(value, False) is False


def test_env_flag_reads_environment_with_shared_parser(monkeypatch) -> None:
    monkeypatch.setenv("LAB_TEST_FLAG", " y ")

    assert env_flag("LAB_TEST_FLAG") is True
    assert env_flag("MISSING_LAB_TEST_FLAG") is False


def test_int_value_uses_default_for_blank_malformed_or_below_minimum() -> None:
    assert int_value("42", 10, minimum=1) == 42
    assert int_value("", 10, minimum=1) == 10
    assert int_value("not-a-number", 10, minimum=1) == 10
    assert int_value("0", 10, minimum=1) == 10


def test_float_value_uses_default_for_blank_malformed_or_below_minimum() -> None:
    assert float_value("2.5", 1.0, minimum=0.1) == 2.5
    assert float_value("", 1.0, minimum=0.1) == 1.0
    assert float_value("not-a-number", 1.0, minimum=0.1) == 1.0
    assert float_value("0", 1.0, minimum=0.1) == 1.0


def test_numeric_env_helpers_read_environment_with_shared_parser(monkeypatch) -> None:
    monkeypatch.setenv("LAB_TEST_INT", " 7 ")
    monkeypatch.setenv("LAB_TEST_FLOAT", " 1.5 ")
    monkeypatch.setenv("LAB_BAD_INT", "many")
    monkeypatch.setenv("LAB_BAD_FLOAT", "-1")

    assert env_int("LAB_TEST_INT", 3, minimum=1) == 7
    assert env_int("LAB_BAD_INT", 3, minimum=1) == 3
    assert env_int("MISSING_LAB_INT", 3, minimum=1) == 3
    assert env_float("LAB_TEST_FLOAT", 3.0, minimum=0.1) == 1.5
    assert env_float("LAB_BAD_FLOAT", 3.0, minimum=0.1) == 3.0
    assert env_float("MISSING_LAB_FLOAT", 3.0, minimum=0.1) == 3.0


def test_load_env_file_ignores_missing_file(tmp_path) -> None:
    assert load_env_file(tmp_path / ".env.local.real-lab") == {}


def test_load_env_file_ignores_unavailable_path(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    original_exists = Path.exists

    def fake_exists(self: Path) -> bool:
        if self == env_path:
            raise OSError("env path is unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fake_exists)

    assert load_env_file(env_path) == {}


def test_load_env_file_preserves_existing_process_environment(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text(
        "\n".join(
            [
                "EXISTING_VALUE=from-file",
                "NEW_VALUE=from-file",
                "QUOTED_VALUE=\"with spaces\"",
                "EMPTY_VALUE",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING_VALUE", "from-process")

    loaded = load_env_file(env_path)

    assert loaded == {"NEW_VALUE": "from-file", "QUOTED_VALUE": "with spaces"}
    assert env_flag("MISSING_REAL_LAB_FLAG") is False
    assert os.environ["EXISTING_VALUE"] == "from-process"
    assert os.environ["NEW_VALUE"] == "from-file"
    assert "EMPTY_VALUE" not in os.environ


def test_load_env_file_supports_skip_keys_and_overwrite(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text("PROVIDER_MODE=local-lab-readwrite\nVALUE=from-file\n", encoding="utf-8")
    monkeypatch.setenv("PROVIDER_MODE", "mock")
    monkeypatch.setenv("VALUE", "from-process")

    loaded = load_env_file(env_path, overwrite=True, skip_keys={"PROVIDER_MODE"})

    assert loaded == {"VALUE": "from-file"}
    assert os.environ["VALUE"] == "from-file"
    assert os.environ["PROVIDER_MODE"] == "mock"


def test_load_real_lab_env_uses_repo_root(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text("REAL_LAB_SENTINEL=yes\n", encoding="utf-8")
    monkeypatch.delenv("REAL_LAB_SENTINEL", raising=False)

    assert load_real_lab_env(tmp_path) == {"REAL_LAB_SENTINEL": "yes"}
    assert env_flag("REAL_LAB_SENTINEL") is True


def test_read_env_file_values_does_not_mutate_process_environment(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text("PROVIDER_MODE=local-lab-readwrite\nOTHER_VALUE=ready\n", encoding="utf-8")
    monkeypatch.delenv("OTHER_VALUE", raising=False)

    assert read_env_file_values(env_path, skip_keys={"PROVIDER_MODE"}) == {"OTHER_VALUE": "ready"}
    assert "OTHER_VALUE" not in os.environ


def test_read_env_file_values_ignores_dotenv_read_errors(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text("OTHER_VALUE=ready\n", encoding="utf-8")
    errors = [
        OSError("unreadable"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        ValueError("invalid dotenv value"),
    ]

    for error in errors:
        monkeypatch.setattr(env_utils, "dotenv_values", lambda _path, error=error: (_ for _ in ()).throw(error))

        assert read_env_file_values(env_path) == {}
