"""Config and options flow for Battery Arsenal."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BATTERY_NOTES_DOMAIN,
    CONF_DEGRADED_MODE,
    CONF_EXCLUDED_DEVICES,
    CONF_NON_CONSUMABLE_KEYWORDS,
    CONF_REPORT_PATH,
    CONF_RESTOCK_MONTHS,
    DEFAULT_DEGRADED_MODE,
    DEFAULT_NON_CONSUMABLE_KEYWORDS,
    DEFAULT_REPORT_DIR,
    DEFAULT_RESTOCK_MONTHS,
    DOMAIN,
)


class BatteryArsenalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow that requires Battery Notes to be loaded."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if BATTERY_NOTES_DOMAIN not in self.hass.config.components:
            return self.async_abort(reason="battery_notes_not_found")

        if user_input is not None:
            return self.async_create_entry(title="Battery Arsenal", data={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BatteryArsenalOptionsFlow()


class BatteryArsenalOptionsFlow(OptionsFlow):
    """Options: report folder, keywords, exclusions, degraded mode, restock."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            keywords_raw: str = user_input[CONF_NON_CONSUMABLE_KEYWORDS]
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            return self.async_create_entry(
                data={
                    CONF_REPORT_PATH: user_input[CONF_REPORT_PATH],
                    CONF_NON_CONSUMABLE_KEYWORDS: keywords,
                    CONF_EXCLUDED_DEVICES: user_input.get(CONF_EXCLUDED_DEVICES, []),
                    CONF_DEGRADED_MODE: user_input[CONF_DEGRADED_MODE],
                    CONF_RESTOCK_MONTHS: user_input[CONF_RESTOCK_MONTHS],
                }
            )

        options = self.config_entry.options
        current_keywords = options.get(
            CONF_NON_CONSUMABLE_KEYWORDS, DEFAULT_NON_CONSUMABLE_KEYWORDS
        )

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_REPORT_PATH,
                    default=options.get(CONF_REPORT_PATH, DEFAULT_REPORT_DIR),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_NON_CONSUMABLE_KEYWORDS,
                    default=", ".join(current_keywords),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_EXCLUDED_DEVICES,
                    default=options.get(CONF_EXCLUDED_DEVICES, []),
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(multiple=True)
                ),
                vol.Optional(
                    CONF_DEGRADED_MODE,
                    default=options.get(CONF_DEGRADED_MODE, DEFAULT_DEGRADED_MODE),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_RESTOCK_MONTHS,
                    default=options.get(CONF_RESTOCK_MONTHS, DEFAULT_RESTOCK_MONTHS),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1, max=36, step=1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
