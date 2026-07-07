from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, TypeVar

T = TypeVar("T")


def unique_preserving_order(
    values: Iterable[T],
    *,
    skip_falsey: bool = False,
    key: Callable[[T], Any] | None = None,
) -> list[T]:
    seen: set[Any] = set()
    result: list[T] = []
    for value in values:
        if skip_falsey and not value:
            continue
        marker = key(value) if key else value
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def unique_strings(values: Any) -> list[str]:
    if values is None:
        candidates: Iterable[Any] = []
    elif isinstance(values, str):
        candidates = [values]
    elif isinstance(values, dict):
        candidates = []
    elif isinstance(values, Iterable):
        candidates = values
    else:
        candidates = [values]
    return unique_preserving_order(
        (text for text in (str(value).strip() for value in candidates if value is not None) if text),
        skip_falsey=True,
    )


def unique_csv_strings(values: Any, *, include_scalars: bool = True) -> list[str]:
    if isinstance(values, str):
        return unique_strings(values.split(","))
    if values is None:
        return []
    if isinstance(values, dict):
        return []
    if isinstance(values, Iterable):
        return unique_strings(values)
    return unique_strings(values) if include_scalars else []
