from __future__ import annotations

from app.services.list_utils import unique_csv_strings, unique_preserving_order, unique_strings


def test_unique_preserving_order_keeps_first_occurrence() -> None:
    assert unique_preserving_order(["alpha", "beta", "alpha", "gamma", "beta"]) == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_unique_preserving_order_can_keep_falsey_values() -> None:
    assert unique_preserving_order(["", "alpha", "", None, None]) == ["", "alpha", None]


def test_unique_preserving_order_can_skip_falsey_values() -> None:
    assert unique_preserving_order(["", "alpha", "", None, "alpha", "beta"], skip_falsey=True) == [
        "alpha",
        "beta",
    ]


def test_unique_preserving_order_can_dedupe_by_key() -> None:
    assert unique_preserving_order([1, "1", 2, "2", 1], key=str) == [1, 2]


def test_unique_strings_strips_skips_and_dedupes() -> None:
    assert unique_strings([" alpha ", "alpha", None, "", 2, "2"]) == ["alpha", "2"]


def test_unique_strings_keeps_scalar_string_whole() -> None:
    assert unique_strings(" policy blocker ") == ["policy blocker"]


def test_unique_strings_handles_scalar_and_container_edges() -> None:
    assert unique_strings(None) == []
    assert unique_strings({"blocker": "ignored"}) == []
    assert unique_strings((" alpha ", "beta", "alpha", 3)) == ["alpha", "beta", "3"]


def test_unique_csv_strings_splits_csv_and_dedupes_values() -> None:
    assert unique_csv_strings(" alpha, beta ,, alpha ") == ["alpha", "beta"]
    assert unique_csv_strings([" alpha ", "alpha", 3, "3"]) == ["alpha", "3"]
    assert unique_csv_strings({"alpha": "ignored"}) == []


def test_unique_csv_strings_can_ignore_scalar_non_strings() -> None:
    assert unique_csv_strings(123) == ["123"]
    assert unique_csv_strings(123, include_scalars=False) == []
