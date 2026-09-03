from __future__ import annotations

from app.services.json_utils import parse_json_object, parse_json_value


def test_parse_json_object_accepts_text_and_bytes() -> None:
    assert parse_json_object('{"status": "ready"}') == {"status": "ready"}
    assert parse_json_object(b'{"return_code": 0}') == {"return_code": 0}


def test_parse_json_object_accepts_utf8_bom_output() -> None:
    assert parse_json_object('\ufeff{"status": "ready"}') == {"status": "ready"}
    assert parse_json_object(b'\xef\xbb\xbf{"return_code": 0}') == {"return_code": 0}


def test_parse_json_object_rejects_empty_invalid_and_non_object_values() -> None:
    for value in (None, "", b"", "not-json", b"\xff", "[]", '"text"', "123"):
        assert parse_json_object(value) == {}


def test_parse_json_object_allows_surrounding_json_whitespace() -> None:
    assert parse_json_object('\r\n  {"Datastores": []}\n') == {"Datastores": []}


def test_parse_json_object_recovers_object_after_noisy_prefix() -> None:
    assert parse_json_object('warning: using cached govc session\n{"status": "ready"}\n') == {"status": "ready"}
    assert parse_json_object(b'log line\n{"stage": "complete"}') == {"stage": "complete"}
    assert parse_json_object('\ufeffwarning\n{"stage": "complete"}') == {"stage": "complete"}


def test_parse_json_value_accepts_arrays_and_embedded_payloads() -> None:
    assert parse_json_value('["alpha", {"name": "beta"}]') == ["alpha", {"name": "beta"}]
    assert parse_json_value(b'\xef\xbb\xbflog line\n["first", "second"]') == ["first", "second"]
    assert parse_json_value("not-json", default=[]) == []
