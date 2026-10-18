"""The Battery Arsenal integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import BatteryArsenalCoordinator
from .services import async_setup_services, async_unload_services
from .storage import ReplacementHistory

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BatteryArsenalRuntime:
    """Objects shared between the entry, its platforms and its services."""

    coordinator: BatteryArsenalCoordinator
    history: ReplacementHistory


type BatteryArsenalConfigEntry = ConfigEntry[BatteryArsenalRuntime]


async def async_setup_entry(
    hass: HomeAssistant, entry: BatteryArsenalConfigEntry
) -> bool:
    """Set up Battery Arsenal from a config entry."""
    coordinator = BatteryArsenalCoordinator(hass, entry)
    history = ReplacementHistory(hass, entry)
    await history.async_start()

    entry.runtime_data = BatteryArsenalRuntime(coordinator=coordinator, history=history)
    # Kept for services / diagnostics that look it up by entry_id.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.runtime_data

    await coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async_setup_services(hass)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BatteryArsenalConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            async_unload_services(hass)
    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant, entry: BatteryArsenalConfigEntry
) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
