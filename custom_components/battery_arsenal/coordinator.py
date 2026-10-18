"""Inventory coordinator for Battery Arsenal.

All inventory logic lives here. Sensors read from this coordinator and never
compute anything themselves. The coordinator rebuilds the inventory on demand
(debounced) in response to registry / state / config-entry changes.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_BATTERY_QUANTITY,
    ATTR_BATTERY_TYPE,
    ATTR_BATTERY_TYPE_AND_QUANTITY,
    BATTERY_NOTES_DOMAIN,
    CATEGORY_CONSUMABLE,
    CATEGORY_NON_CONSUMABLE,
    CATEGORY_UNMAPPED,
    CATEGORY_UNTRACKED,
    CONF_DEGRADED_MODE,
    CONF_EXCLUDED_DEVICES,
    CONF_NON_CONSUMABLE_KEYWORDS,
    DEBOUNCE_SECONDS,
    DEFAULT_DEGRADED_MODE,
    DEFAULT_NON_CONSUMABLE_KEYWORDS,
    DOMAIN,
    ISSUE_BATTERY_NOTES_MISSING,
    ISSUE_CONTRACT_CHANGED,
)
from .parsing import classify, resolve_battery

_LOGGER = logging.getLogger(__name__)

# Device classes we treat as "this device has a battery" when looking for
# untracked devices in degraded mode.
_BATTERY_DEVICE_CLASSES = {"battery"}

# Entity-id ranking for choosing which Battery Notes entity to read a device's
# type from. The _battery_type sensor exists for every battery device, so it is
# preferred; _battery_plus only exists when a % sensor is present.
def _type_source_rank(entity_id: str, domain: str) -> int:
    if entity_id.endswith("_battery_type"):
        return 0
    if "_battery_type" in entity_id:
        return 1
    if domain == "sensor" and entity_id.endswith("_battery_plus"):
        return 2
    if "_battery_plus" in entity_id:
        return 3
    return 4


@dataclass(slots=True)
class DeviceRecord:
    """One physical device's battery situation."""

    device_id: str
    name: str
    area: str | None
    manufacturer: str | None
    model: str | None
    battery_type: str | None
    quantity: int
    category: str
    source_entity_id: str | None

    def as_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "area": self.area,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "battery_type": self.battery_type,
            "quantity": self.quantity,
            "category": self.category,
            "source_entity_id": self.source_entity_id,
        }


@dataclass(slots=True)
class TypeAggregate:
    """Aggregated totals for one consumable battery type."""

    battery_type: str
    cells: int = 0
    devices: list[DeviceRecord] = field(default_factory=list)


@dataclass(slots=True)
class InventoryData:
    """The full computed inventory. Sensors read only from this."""

    bn_loaded: bool = True
    types: dict[str, TypeAggregate] = field(default_factory=dict)
    total_cells: int = 0
    records: list[DeviceRecord] = field(default_factory=list)
    unmapped: list[DeviceRecord] = field(default_factory=list)
    non_consumable: list[DeviceRecord] = field(default_factory=list)
    untracked: list[DeviceRecord] = field(default_factory=list)
    parse_failures: list[str] = field(default_factory=list)

    @property
    def most_common(self) -> TypeAggregate | None:
        if not self.types:
            return None
        return max(self.types.values(), key=lambda t: t.cells)


class BatteryArsenalCoordinator(DataUpdateCoordinator[InventoryData]):
    """Builds and maintains the household battery inventory."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=None,  # event driven, never polled
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=DEBOUNCE_SECONDS,
                immediate=False,
            ),
        )
        self.entry = entry
        self._tracked_state_unsub = None

    # -- lifecycle ---------------------------------------------------------
    async def async_start(self) -> None:
        """Wire up listeners and schedule the first build."""
        self._register_registry_listeners()

        if self.hass.state is CoreState.running:
            await self.async_refresh()
        else:
            self.entry.async_on_unload(
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._handle_started
                )
            )

    async def _handle_started(self, _event: Event) -> None:
        await self.async_refresh()

    @callback
    def _register_registry_listeners(self) -> None:
        """Listen for the registry / config-entry changes that affect us."""
        self.entry.async_on_unload(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._handle_registry_event
            )
        )
        self.entry.async_on_unload(
            self.hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED, self._handle_registry_event
            )
        )
        # Clean up the (re-subscribed) state tracker exactly once, on unload.
        self.entry.async_on_unload(self._clear_state_sub)

    @callback
    def _handle_registry_event(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _resubscribe_states(self, entity_ids: list[str]) -> None:
        """Track state changes only on the Battery Notes entities we read."""
        if self._tracked_state_unsub is not None:
            self._tracked_state_unsub()
            self._tracked_state_unsub = None
        if not entity_ids:
            return

        @callback
        def _state_changed(_event: Event) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self._tracked_state_unsub = async_track_state_change_event(
            self.hass, entity_ids, _state_changed
        )

    @callback
    def _clear_state_sub(self) -> None:
        if self._tracked_state_unsub is not None:
            self._tracked_state_unsub()
            self._tracked_state_unsub = None

    # -- options -----------------------------------------------------------
    @property
    def _keywords(self) -> list[str]:
        return self.entry.options.get(
            CONF_NON_CONSUMABLE_KEYWORDS, DEFAULT_NON_CONSUMABLE_KEYWORDS
        )

    @property
    def _excluded(self) -> set[str]:
        return set(self.entry.options.get(CONF_EXCLUDED_DEVICES, []))

    @property
    def _degraded_mode(self) -> bool:
        return self.entry.options.get(CONF_DEGRADED_MODE, DEFAULT_DEGRADED_MODE)

    # -- build -------------------------------------------------------------
    async def _async_update_data(self) -> InventoryData:
        """Rebuild the inventory from the registries and current states."""
        bn_loaded = BATTERY_NOTES_DOMAIN in self.hass.config.components
        self._update_missing_issue(bn_loaded)

        data = InventoryData(bn_loaded=bn_loaded)

        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        excluded = self._excluded

        # Group Battery Notes sensor/binary_sensor entities by device.
        bn_by_device: dict[str, list[er.RegistryEntry]] = defaultdict(list)
        tracked_entity_ids: list[str] = []
        for entry in ent_reg.entities.values():
            if entry.platform != BATTERY_NOTES_DOMAIN:
                continue
            if entry.domain not in ("sensor", "binary_sensor"):
                continue  # skip the _battery_replaced button etc.
            if entry.device_id is None or entry.disabled_by is not None:
                continue
            bn_by_device[entry.device_id].append(entry)

        saw_any_attribute = False

        for device_id, entries in bn_by_device.items():
            if device_id in excluded:
                continue

            record = self._build_record(
                device_id, entries, dev_reg, area_reg, tracked_entity_ids
            )
            if record is None:
                continue
            if record.battery_type is not None:
                saw_any_attribute = True

            data.records.append(record)

            if record.category == CATEGORY_CONSUMABLE:
                agg = data.types.setdefault(
                    record.battery_type, TypeAggregate(record.battery_type)
                )
                agg.cells += record.quantity
                agg.devices.append(record)
                data.total_cells += record.quantity
            elif record.category == CATEGORY_NON_CONSUMABLE:
                data.non_consumable.append(record)
            else:
                data.unmapped.append(record)

        # Degraded mode: surface battery devices Battery Notes does not track.
        if self._degraded_mode:
            data.untracked = self._find_untracked(
                ent_reg, dev_reg, area_reg, set(bn_by_device), excluded
            )

        # Sort type aggregates' device lists for stable output.
        for agg in data.types.values():
            agg.devices.sort(key=lambda r: (r.area or "", r.name))

        self._resubscribe_states(tracked_entity_ids)

        # Contract check: Battery Notes entities exist but none expose a type.
        self._update_contract_issue(
            bn_loaded and bool(bn_by_device) and not saw_any_attribute
        )

        return data

    def _build_record(
        self,
        device_id: str,
        entries: list[er.RegistryEntry],
        dev_reg: dr.DeviceRegistry,
        area_reg: ar.AreaRegistry,
        tracked_entity_ids: list[str],
    ) -> DeviceRecord | None:
        """Build one device record, picking the best type source."""
        device = dev_reg.async_get(device_id)
        if device is None:
            return None

        name = device.name_by_user or device.name or device_id
        area_name: str | None = None
        if device.area_id:
            area = area_reg.async_get_area(device.area_id)
            area_name = area.name if area else None

        # Prefer the _battery_type sensor, then _battery_plus, then anything.
        ordered = sorted(
            entries, key=lambda e: _type_source_rank(e.entity_id, e.domain)
        )

        battery_type: str | None = None
        quantity = 1
        source_entity_id: str | None = ordered[0].entity_id if ordered else None

        for entry in ordered:
            tracked_entity_ids.append(entry.entity_id)
            state = self.hass.states.get(entry.entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            attrs = state.attributes
            resolved_type, resolved_qty = resolve_battery(
                battery_type=attrs.get(ATTR_BATTERY_TYPE),
                battery_quantity=attrs.get(ATTR_BATTERY_QUANTITY),
                type_and_quantity=attrs.get(ATTR_BATTERY_TYPE_AND_QUANTITY),
                state_value=state.state,
            )
            if resolved_type is not None:
                battery_type = resolved_type
                quantity = resolved_qty
                source_entity_id = entry.entity_id
                break  # first entity with a valid type wins

        category = classify(battery_type, self._keywords)

        return DeviceRecord(
            device_id=device_id,
            name=name,
            area=area_name,
            manufacturer=device.manufacturer,
            model=device.model,
            battery_type=battery_type,
            quantity=quantity,
            category=category,
            source_entity_id=source_entity_id,
        )

    def _find_untracked(
        self,
        ent_reg: er.EntityRegistry,
        dev_reg: dr.DeviceRegistry,
        area_reg: ar.AreaRegistry,
        bn_device_ids: set[str],
        excluded: set[str],
    ) -> list[DeviceRecord]:
        """Devices with a battery device-class entity but no Battery Notes entry."""
        seen: set[str] = set()
        result: list[DeviceRecord] = []
        for entry in ent_reg.entities.values():
            if entry.platform in (BATTERY_NOTES_DOMAIN, DOMAIN):
                continue
            if entry.disabled_by is not None or entry.device_id is None:
                continue
            device_class = entry.device_class or entry.original_device_class
            if device_class not in _BATTERY_DEVICE_CLASSES:
                continue
            device_id = entry.device_id
            if (
                device_id in bn_device_ids
                or device_id in excluded
                or device_id in seen
            ):
                continue
            device = dev_reg.async_get(device_id)
            if device is None:
                continue
            seen.add(device_id)
            area_name = None
            if device.area_id:
                area = area_reg.async_get_area(device.area_id)
                area_name = area.name if area else None
            result.append(
                DeviceRecord(
                    device_id=device_id,
                    name=device.name_by_user or device.name or device_id,
                    area=area_name,
                    manufacturer=device.manufacturer,
                    model=device.model,
                    battery_type=None,
                    quantity=1,
                    category=CATEGORY_UNTRACKED,
                    source_entity_id=entry.entity_id,
                )
            )
        result.sort(key=lambda r: (r.area or "", r.name))
        return result

    # -- repair issues -----------------------------------------------------
    @callback
    def _update_missing_issue(self, bn_loaded: bool) -> None:
        if bn_loaded:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_BATTERY_NOTES_MISSING)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            ISSUE_BATTERY_NOTES_MISSING,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_BATTERY_NOTES_MISSING,
        )

    @callback
    def _update_contract_issue(self, broken: bool) -> None:
        if broken:
            _LOGGER.warning(
                "Battery Notes entities were found but none expose a battery "
                "type attribute; the upstream contract may have changed"
            )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_CONTRACT_CHANGED,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_CONTRACT_CHANGED,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_CONTRACT_CHANGED)
