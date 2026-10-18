"""Pure parsing and classification helpers.

Everything here is side-effect free so it can be unit tested without a running
Home Assistant. The coordinator feeds it raw attribute values and gets back
normalized types, quantities and categories.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .const import (
    CATEGORY_CONSUMABLE,
    CATEGORY_NON_CONSUMABLE,
    CATEGORY_UNMAPPED,
)

# Values that mean "no known type" rather than an actual battery type.
_EMPTY_VALUES = {"", "-", "none", "unknown", "unavailable", "n/a", "null"}

# Matches an embedded count such as "2x AA", "2× AA", "3 x CR2032".
_EMBEDDED_COUNT = re.compile(
    r"^\s*(\d+)\s*(?:x|×|\*)\s*(.+?)\s*$",
    re.IGNORECASE,
)


def normalize_type(raw: object) -> str | None:
    """Normalize a battery type string.

    Returns an upper-cased code (``aa`` -> ``AA``), or ``None`` when the value
    is missing, empty, unknown or unavailable.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in _EMPTY_VALUES:
        return None
    return text.upper()


def parse_embedded_count(raw: object) -> tuple[str | None, int | None]:
    """Split a value like ``2× AA`` into ``("AA", 2)``.

    Returns ``(normalized_type, quantity)``. Quantity is ``None`` when no
    embedded count is present so the caller can decide the default.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None

    match = _EMBEDDED_COUNT.match(text)
    if match:
        qty = int(match.group(1))
        return normalize_type(match.group(2)), (qty if qty >= 1 else None)
    return normalize_type(text), None


def coerce_quantity(raw: object) -> int | None:
    """Coerce an explicit ``battery_quantity`` attribute to an int >= 1."""
    if raw is None:
        return None
    try:
        value = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None
    return value if value >= 1 else None


def resolve_battery(
    *,
    battery_type: object = None,
    battery_quantity: object = None,
    type_and_quantity: object = None,
    state_value: object = None,
) -> tuple[str | None, int]:
    """Resolve the battery type and quantity from the available sources.

    Precedence for the type:
      1. the ``battery_type`` attribute,
      2. the ``battery_type_and_quantity`` attribute,
      3. the entity state (the ``_battery_type`` sensor's state is the type).

    An explicit ``battery_quantity`` attribute always wins over a count
    embedded in a string. Quantity defaults to 1.
    """
    explicit_qty = coerce_quantity(battery_quantity)

    resolved_type = normalize_type(battery_type)
    embedded_qty: int | None = None

    if resolved_type is None:
        resolved_type, embedded_qty = parse_embedded_count(type_and_quantity)

    if resolved_type is None:
        resolved_type, embedded_qty = parse_embedded_count(state_value)

    quantity = explicit_qty or embedded_qty or 1
    return resolved_type, quantity


def _normalize_keywords(keywords: Iterable[str]) -> list[str]:
    return [k.strip().lower() for k in keywords if k and k.strip()]


def is_non_consumable(battery_type: str, keywords: Iterable[str]) -> bool:
    """True when the (already normalized) type matches a non-consumable keyword."""
    haystack = battery_type.lower()
    return any(keyword in haystack for keyword in _normalize_keywords(keywords))


def classify(battery_type: str | None, keywords: Iterable[str]) -> str:
    """Classify a device into consumable / non_consumable / unmapped."""
    if battery_type is None:
        return CATEGORY_UNMAPPED
    if is_non_consumable(battery_type, keywords):
        return CATEGORY_NON_CONSUMABLE
    return CATEGORY_CONSUMABLE


def slugify_type(battery_type: str) -> str:
    """Stable slug for a battery type, used in unique ids and object ids."""
    return re.sub(r"[^a-z0-9]+", "_", battery_type.lower()).strip("_") or "unknown"
