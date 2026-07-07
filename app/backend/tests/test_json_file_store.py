from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.services.json_file_store import _filesystem_path, read_json_object, write_json_object, write_json_value, write_text_value


def test_json_file_store_reads_missing_or_corrupt_as_empty(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    assert read_json_object(path) == {}

    path.write_text("{not-json", encoding="utf-8")

    assert read_json_object(path) == {}


def test_json_file_store_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    original_exists = os.path.exists

    def flaky_exists(candidate: str) -> bool:
        if candidate == _filesystem_path(path):
            raise OSError("path unavailable")
        return original_exists(candidate)

    monkeypatch.setattr(os.path, "exists", flaky_exists)

    assert read_json_object(path) == {}


def test_json_file_store_requires_object_payload(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    assert read_json_object(path) == {}


def test_json_file_store_reads_bom_prefixed_object(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_bytes(b'\xef\xbb\xbf{"status": "ready"}')

    assert read_json_object(path) == {"status": "ready"}


def test_json_file_store_recovers_object_after_noisy_prefix(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text('warning: partial previous output\n{"status": "ready"}', encoding="utf-8")

    assert read_json_object(path) == {"status": "ready"}


def test_json_file_store_writes_atomically_and_removes_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    write_json_object(path, {"status": "ready", "value": 1})

    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "ready", "value": 1}
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_writes_non_object_values_atomically(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    write_json_value(path, ["alpha", {"status": "ready"}])

    assert json.loads(path.read_text(encoding="utf-8")) == ["alpha", {"status": "ready"}]
    assert read_json_object(path) == {}
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_writes_text_atomically(tmp_path: Path) -> None:
    path = tmp_path / "app-mode.env"

    write_text_value(path, "PROVIDER_MODE=local-readonly\n")

    assert path.read_text(encoding="utf-8") == "PROVIDER_MODE=local-readonly\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_supports_default_serializer(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    write_json_object(path, {"path": tmp_path}, default=str)

    assert json.loads(path.read_text(encoding="utf-8")) == {"path": str(tmp_path)}
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_preserves_write_error_when_temp_cleanup_fails(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    original_unlink = Path.unlink

    def locked_unlink(candidate: Path, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        if candidate.parent == tmp_path and candidate.name.endswith(".tmp"):
            raise OSError("temp file locked")
        return original_unlink(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)

    with pytest.raises(TypeError):
        write_json_object(path, {"bad": object()})


def test_json_file_store_handles_long_target_filename(tmp_path: Path) -> None:
    path = tmp_path / f"{'x' * 220}.json"

    write_json_object(path, {"status": "ready"})

    assert read_json_object(path) == {"status": "ready"}
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_writes_text_to_long_target_filename(tmp_path: Path) -> None:
    path = tmp_path / f"{'x' * 220}.env"

    write_text_value(path, "ready\n")

    with open(_filesystem_path(path), encoding="utf-8") as handle:
        assert handle.read() == "ready\n"
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_uses_unique_temp_files_for_repeated_writes(tmp_path: Path) -> None:
    path = tmp_path / "state.json"

    for index in range(20):
        write_json_object(path, {"index": index})

    assert json.loads(path.read_text(encoding="utf-8")) == {"index": 19}
    assert list(tmp_path.glob("*.tmp")) == []


def test_json_file_store_allows_parallel_writes_from_same_process(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    payloads = [{"index": index} for index in range(20)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda payload: write_json_object(path, payload), payloads))

    assert json.loads(path.read_text(encoding="utf-8")) in payloads
    assert list(tmp_path.glob("*.tmp")) == []
