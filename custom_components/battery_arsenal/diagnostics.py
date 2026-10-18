"""Diagnostics for Battery Arsenal."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import BatteryArsenalConfigEntry
from .const import BATTERY_NOTES_DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BatteryArsenalConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    data = runtime.coordinator.data

    bn_present = bool(hass.config_entries.async_entries(BATTERY_NOTES_DOMAIN))

    inventory: dict[str, Any] = {}
    if data is not None:
        inventory = {
            "bn_loaded": data.bn_loaded,
            "total_cells": data.total_cells,
            "types": {
                t: {"cells": a.cells, "devices": len(a.devices)}
                for t, a in data.types.items()
            },
            "unmapped": len(data.unmapped),
            "non_consumable": len(data.non_consumable),
            "untracked": len(data.untracked),
            "records": [r.as_dict() for r in data.records],
            "parse_failures": data.parse_failures,
        }

    return {
        "options": dict(entry.options),
        "battery_notes_loaded": BATTERY_NOTES_DOMAIN in hass.config.components,
        "battery_notes_present": bn_present,
        "inventory": inventory,
        "history": runtime.history.as_dict(),
    }
