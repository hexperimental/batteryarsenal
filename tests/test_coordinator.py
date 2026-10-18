"""Coordinator / inventory build tests with a mocked registry."""

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.battery_arsenal.const import BATTERY_NOTES_DOMAIN, DOMAIN


def _make_bn_device(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    *,
    key: str,
    name: str,
    object_id: str,
    state: str,
    attributes: dict,
    suffix: str = "battery_type",
    domain: str = "sensor",
) -> str:
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("demo", key)},
        name=name,
        manufacturer="Acme",
        model="M1",
    )
    reg_entry = ent_reg.async_get_or_create(
        domain=domain,
        platform=BATTERY_NOTES_DOMAIN,
        unique_id=f"{key}_{suffix}",
        device_id=device.id,
        suggested_object_id=f"{object_id}_{suffix}",
    )
    hass.states.async_set(reg_entry.entity_id, state, attributes)
    return device.id


@pytest.fixture
async def setup_entry(hass: HomeAssistant):
    hass.config.components.add(BATTERY_NOTES_DOMAIN)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, options={})
    entry.add_to_hass(hass)
    return entry


async def test_inventory_counts(hass: HomeAssistant, setup_entry) -> None:
    entry = setup_entry
    _make_bn_device(
        hass, entry, key="d1", name="Hallway", object_id="hallway",
        state="AA", attributes={"battery_type": "AA", "battery_quantity": 2},
    )
    _make_bn_device(
        hass, entry, key="d2", name="Remote", object_id="remote",
        state="AA", attributes={"battery_type": "AA", "battery_quantity": 2},
    )
    _make_bn_device(
        hass, entry, key="d3", name="Door", object_id="door",
        state="CR2032", attributes={"battery_type": "CR2032"},
    )
    _make_bn_device(
        hass, entry, key="d4", name="Thermostat", object_id="thermostat",
        state="Rechargeable", attributes={"battery_type": "Rechargeable"},
    )
    _make_bn_device(
        hass, entry, key="d5", name="Mystery", object_id="mystery",
        state="unknown", attributes={},
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    data = coordinator.data

    assert data.total_cells == 5  # AA 2+2 + CR2032 1
    assert data.types["AA"].cells == 4
    assert data.types["CR2032"].cells == 1
    assert data.most_common.battery_type == "AA"
    assert len(data.non_consumable) == 1
    assert len(data.unmapped) == 1

    # Summary sensor should reflect the total.
    state = hass.states.get("sensor.battery_arsenal_total_cells_in_rotation")
    assert state is not None
    assert state.state == "5"


async def test_embedded_count_from_state(hass: HomeAssistant, setup_entry) -> None:
    entry = setup_entry
    _make_bn_device(
        hass, entry, key="d1", name="Scale", object_id="scale",
        state="2× AAA", attributes={},
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    assert coordinator.data.types["AAA"].cells == 2


async def test_excluded_device(hass: HomeAssistant, setup_entry) -> None:
    entry = setup_entry
    device_id = _make_bn_device(
        hass, entry, key="d1", name="Hallway", object_id="hallway",
        state="AA", attributes={"battery_type": "AA", "battery_quantity": 2},
    )
    hass.config_entries.async_update_entry(
        entry, options={"excluded_devices": [device_id]}
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    assert coordinator.data.total_cells == 0
    assert "AA" not in coordinator.data.types
