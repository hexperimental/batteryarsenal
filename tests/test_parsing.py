"""Unit tests for parsing and classification (no Home Assistant needed)."""

import pytest

from custom_components.battery_arsenal.const import (
    CATEGORY_CONSUMABLE,
    CATEGORY_NON_CONSUMABLE,
    CATEGORY_UNMAPPED,
    DEFAULT_NON_CONSUMABLE_KEYWORDS,
)
from custom_components.battery_arsenal.parsing import (
    classify,
    coerce_quantity,
    normalize_type,
    parse_embedded_count,
    resolve_battery,
    slugify_type,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aa", "AA"),
        (" cr2032 ", "CR2032"),
        ("9V", "9V"),
        ("", None),
        ("unknown", None),
        ("unavailable", None),
        ("-", None),
        (None, None),
    ],
)
def test_normalize_type(raw, expected):
    assert normalize_type(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2x AA", ("AA", 2)),
        ("2× AA", ("AA", 2)),
        ("3 x CR2032", ("CR2032", 3)),
        ("AA", ("AA", None)),
        ("", (None, None)),
    ],
)
def test_parse_embedded_count(raw, expected):
    assert parse_embedded_count(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1, 1), ("2", 2), ("3.0", 3), (0, None), (-1, None), ("x", None), (None, None)],
)
def test_coerce_quantity(raw, expected):
    assert coerce_quantity(raw) == expected


def test_resolve_explicit_quantity_wins():
    # Explicit battery_quantity beats the count embedded in the string.
    t, q = resolve_battery(
        battery_type="AA", battery_quantity=4, type_and_quantity="2× AA"
    )
    assert (t, q) == ("AA", 4)


def test_resolve_from_type_and_quantity():
    t, q = resolve_battery(type_and_quantity="2× AAA")
    assert (t, q) == ("AAA", 2)


def test_resolve_from_state_fallback():
    t, q = resolve_battery(state_value="CR2032")
    assert (t, q) == ("CR2032", 1)


def test_resolve_missing_is_none():
    t, q = resolve_battery()
    assert t is None
    assert q == 1


@pytest.mark.parametrize(
    ("battery_type", "expected"),
    [
        ("AA", CATEGORY_CONSUMABLE),
        ("CR2032", CATEGORY_CONSUMABLE),
        ("RECHARGEABLE", CATEGORY_NON_CONSUMABLE),
        ("LI-ION", CATEGORY_NON_CONSUMABLE),
        (None, CATEGORY_UNMAPPED),
    ],
)
def test_classify(battery_type, expected):
    assert classify(battery_type, DEFAULT_NON_CONSUMABLE_KEYWORDS) == expected


def test_slugify_type():
    assert slugify_type("CR2032") == "cr2032"
    assert slugify_type("2× AA") == "2_aa"
