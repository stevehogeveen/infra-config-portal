from __future__ import annotations

import json
from typing import Any


def parse_json_value(value: str | bytes | bytearray | None, *, default: Any = None) -> Any:
    if not value:
        return default
    text = _json_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, UnicodeDecodeError):
        payload = _parse_embedded_json_value(text, default=default)
    return payload


def parse_json_object(value: str | bytes | bytearray | None) -> dict[str, Any]:
    payload = parse_json_value(value, default={})
    return payload if isinstance(payload, dict) else {}


def _json_text(value: str | bytes | bytearray) -> str:
    if isinstance(value, str):
        return value.lstrip("\ufeff")
    try:
        return bytes(value).decode("utf-8-sig")
    except (TypeError, ValueError, UnicodeDecodeError):
        return ""


def _parse_embedded_json_object(text: str) -> dict[str, Any]:
    payload = _parse_embedded_json_value(text, default={})
    return payload if isinstance(payload, dict) else {}


def _parse_embedded_json_value(text: str, *, default: Any = None) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            payload, _end = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        return payload
    return default
