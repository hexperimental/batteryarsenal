"""Sensors for Battery Arsenal.

A single service device carries a set of summary sensors plus one dynamically
created sensor per consumable battery type. Sensors only read from the
coordinator; when a type disappears its sensor goes unavailable rather than
being removed, so history and dashboards do not break.
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BatteryArsenalConfigEntry
from .const import DOMAIN, SERVICE_DEVICE_NAME
from .coordinator import BatteryArsenalCoordinator, InventoryData
from .parsing import slugify_type

UNIT_CELLS = "cells"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BatteryArsenalConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up summary sensors and dynamic per-type sensors."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    history = runtime.history

    async_add_entities(
        [
            TotalCellsSensor(coordinator, entry),
            MostCommonBatterySensor(coordinator, entry),
            UnmappedDevicesSensor(coordinator, entry),
            NonConsumableDevicesSensor(coordinator, entry),
        ]
    )

    known: set[str] = set()

    @callback
    def _sync_type_sensors() -> None:
        data = coordinator.data
        if data is None:
            return
        new = [
            BatteryTypeSensor(coordinator, entry, history, battery_type)
            for battery_type in data.types
            if battery_type not in known
        ]
        for sensor in new:
            known.add(sensor.battery_type)
        if new:
            async_add_entities(new)

    _sync_type_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_sync_type_sensors))


class _BaseSensor(CoordinatorEntity[BatteryArsenalCoordinator], SensorEntity):
    """Common wiring: attach every entity to the one service device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: BatteryArsenalCoordinator, entry: BatteryArsenalConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=SERVICE_DEVICE_NAME,
            manufacturer="Battery Arsenal",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _data(self) -> InventoryData | None:
        return self.coordinator.data

    @property
    def available(self) -> bool:
        data = self._data
        return (
            super().available and data is not None and data.bn_loaded
        )


class TotalCellsSensor(_BaseSensor):
    """Sum of all consumable cells in rotation."""

    _attr_translation_key = "total_cells"
    _attr_native_unit_of_measurement = UNIT_CELLS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_total_cells"

    @property
    def native_value(self) -> int | None:
        return self._data.total_cells if self._data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        if not data:
            return {}
        return {
            "types": len(data.types),
            "devices": sum(len(a.devices) for a in data.types.values()),
        }


class MostCommonBatterySensor(_BaseSensor):
    """The battery type with the most cells in use."""

    _attr_translation_key = "most_common"
    _attr_icon = "mdi:podium-gold"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_most_common"

    @property
    def native_value(self) -> str | None:
        data = self._data
        if not data:
            return None
        top = data.most_common
        return top.battery_type if top else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        if not data:
            return {}
        top = data.most_common
        if top is None:
            return {}
        share = round(100 * top.cells / data.total_cells, 1) if data.total_cells else 0
        return {"cells": top.cells, "share_percent": share}


class UnmappedDevicesSensor(_BaseSensor):
    """Count of Battery Notes devices with no known battery type."""

    _attr_translation_key = "unmapped"
    _attr_native_unit_of_measurement = "devices"
    _attr_icon = "mdi:help-circle-outline"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_unmapped"

    @property
    def native_value(self) -> int | None:
        return len(self._data.unmapped) if self._data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        if not data:
            return {}
        attrs: dict = {
            "incomplete_devices": [
                {
                    "name": r.name,
                    "area": r.area,
                    "manufacturer": r.manufacturer,
                    "model": r.model,
                }
                for r in data.unmapped
            ]
        }
        if data.untracked:
            attrs["untracked_count"] = len(data.untracked)
            attrs["untracked_devices"] = [
                {"name": r.name, "area": r.area} for r in data.untracked
            ]
        return attrs


class NonConsumableDevicesSensor(_BaseSensor):
    """Count of devices with rechargeable / built-in batteries."""

    _attr_translation_key = "non_consumable"
    _attr_native_unit_of_measurement = "devices"
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_non_consumable"

    @property
    def native_value(self) -> int | None:
        return len(self._data.non_consumable) if self._data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        if not data:
            return {}
        return {
            "devices": [
                {"name": r.name, "area": r.area, "battery_type": r.battery_type}
                for r in data.non_consumable
            ]
        }


class BatteryTypeSensor(_BaseSensor):
    """One sensor per consumable battery type: total cells of that type."""

    _attr_native_unit_of_measurement = UNIT_CELLS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery"

    def __init__(self, coordinator, entry, history, battery_type: str) -> None:
        super().__init__(coordinator, entry)
        self.battery_type = battery_type
        self._history = history
        self._attr_unique_id = f"{entry.entry_id}_type_{slugify_type(battery_type)}"
        self._attr_name = battery_type

    @property
    def available(self) -> bool:
        data = self._data
        return (
            super().available
            and data is not None
            and self.battery_type in data.types
        )

    @property
    def native_value(self) -> int | None:
        data = self._data
        if not data or self.battery_type not in data.types:
            return None
        return data.types[self.battery_type].cells

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        if not data or self.battery_type not in data.types:
            return {}
        agg = data.types[self.battery_type]
        share = (
            round(100 * agg.cells / data.total_cells, 1) if data.total_cells else 0
        )
        attrs: dict = {
            "device_count": len(agg.devices),
            "share_percent": share,
            "devices": [
                {"name": r.name, "area": r.area, "quantity": r.quantity}
                for r in agg.devices
            ],
        }
        # Phase 2: restock figures when history has enough data.
        rate = self._history.annual_rate_by_type().get(self.battery_type)
        if rate is not None:
            attrs["estimated_cells_per_year"] = rate
            attrs["suggested_stock"] = self._history.suggested_stock(rate)
        return attrs
