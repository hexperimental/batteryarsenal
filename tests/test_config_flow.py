"""Config flow tests."""

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.battery_arsenal.const import BATTERY_NOTES_DOMAIN, DOMAIN


async def test_abort_without_battery_notes(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "battery_notes_not_found"


async def test_create_entry_with_battery_notes(hass: HomeAssistant) -> None:
    hass.config.components.add(BATTERY_NOTES_DOMAIN)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result2["type"] is FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Battery Arsenal"


async def test_single_instance(hass: HomeAssistant) -> None:
    hass.config.components.add(BATTERY_NOTES_DOMAIN)
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(first["flow_id"], {})
    await hass.async_block_till_done()

    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert second["type"] is FlowResultType.ABORT
    assert second["reason"] == "already_configured"
