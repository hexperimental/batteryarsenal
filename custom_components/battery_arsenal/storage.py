"""Replacement history storage and rate estimation (phase 2).

Listens for the Battery Notes ``battery_notes_battery_replaced`` event and
records swaps to a versioned Store. On first run it seeds from each device's
``_battery_last_replaced`` sensor so there is something to work with.

Note: the replacement event carries no timestamp, so swaps are stamped at the
moment the event is received.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BATTERY_QUANTITY,
    ATTR_BATTERY_TYPE,
    BATTERY_NOTES_DOMAIN,
    CONF_RESTOCK_MONTHS,
    DEFAULT_RESTOCK_MONTHS,
    EVENT_BATTERY_REPLACED,
    MAX_HISTORY_PER_DEVICE,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .parsing import normalize_type

_LOGGER = logging.getLogger(__name__)


class ReplacementHistory:
    """Persistent per-device replacement log with simple rate maths."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # device_id -> list[{"ts": iso, "type": str, "quantity": int}]
        self._data: dict[str, list[dict]] = {}
        self._unsub = None

    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if stored:
            self._data = stored.get("devices", {})
        else:
            await self._async_seed()

        self._unsub = self.hass.bus.async_listen(
            EVENT_BATTERY_REPLACED, self._handle_replaced
        )
        self.entry.async_on_unload(self._unsub)

    async def _async_seed(self) -> None:
        """Seed one record per device from its last-replaced sensor."""
        ent_reg = er.async_get(self.hass)
        for entry in ent_reg.entities.values():
            if entry.platform != BATTERY_NOTES_DOMAIN:
                continue
            if not entry.entity_id.endswith("_battery_last_replaced"):
                continue
            if entry.device_id is None:
                continue
            state = self.hass.states.get(entry.entity_id)
            if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                continue
            ts = dt_util.parse_datetime(state.state)
            if ts is None:
                continue
            btype = normalize_type(state.attributes.get(ATTR_BATTERY_TYPE))
            qty = state.attributes.get(ATTR_BATTERY_QUANTITY) or 1
            self._append(entry.device_id, ts, btype, int(qty))
        await self._store.async_save({"devices": self._data})

    @callback
    def _handle_replaced(self, event: Event) -> None:
        device_id = event.data.get("device_id")
        if not device_id:
            return
        btype = normalize_type(event.data.get(ATTR_BATTERY_TYPE))
        qty = event.data.get(ATTR_BATTERY_QUANTITY) or 1
        self._append(device_id, dt_util.utcnow(), btype, int(qty))
        self.hass.async_create_task(
            self._store.async_save({"devices": self._data})
        )

    def _append(
        self, device_id: str, ts: datetime, btype: str | None, quantity: int
    ) -> None:
        records = self._data.setdefault(device_id, [])
        records.append(
            {
                "ts": ts.isoformat(),
                "type": btype,
                "quantity": max(1, quantity),
            }
        )
        # Keep storage small.
        if len(records) > MAX_HISTORY_PER_DEVICE:
            del records[: len(records) - MAX_HISTORY_PER_DEVICE]

    # -- analysis ----------------------------------------------------------
    @property
    def _restock_months(self) -> int:
        return self.entry.options.get(CONF_RESTOCK_MONTHS, DEFAULT_RESTOCK_MONTHS)

    def annual_rate_by_type(self) -> dict[str, float]:
        """Estimated cells-per-year per type from observed intervals.

        A device needs at least two recorded swaps to yield an interval; with
        only a seed record its rate is unknown and it is left out.
        """
        intervals_by_type: dict[str, list[tuple[float, int]]] = defaultdict(list)
        for records in self._data.values():
            parsed = sorted(
                (
                    (dt_util.parse_datetime(r["ts"]), r)
                    for r in records
                    if dt_util.parse_datetime(r["ts"]) is not None
                ),
                key=lambda pair: pair[0],
            )
            for (t0, _r0), (t1, r1) in zip(parsed, parsed[1:]):
                days = (t1 - t0).total_seconds() / 86400.0
                if days <= 0:
                    continue
                btype = r1.get("type")
                if btype:
                    intervals_by_type[btype].append((days, int(r1.get("quantity", 1))))

        rates: dict[str, float] = {}
        for btype, samples in intervals_by_type.items():
            # cells per year = sum(quantity) / sum(days) * 365
            total_days = sum(days for days, _ in samples)
            total_cells = sum(qty for _, qty in samples)
            if total_days > 0:
                rates[btype] = round(total_cells / total_days * 365.0, 1)
        return rates

    def suggested_stock(self, annual_rate: float) -> int:
        """Cells to keep on hand to cover the restock horizon."""
        from math import ceil

        return ceil(annual_rate * self._restock_months / 12.0)

    def as_dict(self) -> dict:
        return {
            "restock_months": self._restock_months,
            "devices_tracked": len(self._data),
            "annual_rate_by_type": self.annual_rate_by_type(),
        }
