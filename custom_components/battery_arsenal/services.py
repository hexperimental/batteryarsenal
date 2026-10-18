"""Services for Battery Arsenal: generate_report and refresh."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DEFAULT_REPORT_DIR, DOMAIN
from .report import render_csv, render_markdown

_LOGGER = logging.getLogger(__name__)

SERVICE_GENERATE_REPORT = "generate_report"
SERVICE_REFRESH = "refresh"

ATTR_FORMAT = "format"
ATTR_PATH = "path"

_FORMATS = ("markdown", "csv", "both")

_GENERATE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_FORMAT, default="both"): vol.In(_FORMATS),
        vol.Optional(ATTR_PATH): cv.string,
    }
)


def _runtimes(hass: HomeAssistant) -> list:
    return list(hass.data.get(DOMAIN, {}).values())


def _resolve_dir(hass: HomeAssistant, path: str | None) -> Path:
    """Resolve and validate the output directory against the allowlist."""
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path(hass.config.path(path))
    else:
        candidate = Path(hass.config.path(DEFAULT_REPORT_DIR))

    resolved = str(candidate)
    if not hass.config.is_allowed_path(resolved):
        raise ServiceValidationError(
            f"Path '{resolved}' is not allowed. Add it to allowlist_external_dirs "
            "or use a folder inside the Home Assistant config directory."
        )
    return candidate


def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_GENERATE_REPORT):
        return

    async def _async_generate_report(call: ServiceCall) -> ServiceResponse:
        runtimes = _runtimes(hass)
        if not runtimes:
            raise HomeAssistantError("Battery Arsenal is not set up")
        runtime = runtimes[0]
        coordinator = runtime.coordinator
        history = runtime.history

        await coordinator.async_refresh()
        data = coordinator.data
        if data is None:
            raise HomeAssistantError("Inventory is not ready yet")

        fmt = call.data[ATTR_FORMAT]
        target_dir = _resolve_dir(hass, call.data.get(ATTR_PATH))

        markdown = render_markdown(data, history) if fmt in ("markdown", "both") else None
        csv_text = render_csv(data) if fmt in ("csv", "both") else None

        stamp = dt_util.now().strftime("%Y%m%d_%H%M%S")
        written: list[str] = []

        def _write() -> None:
            os.makedirs(target_dir, exist_ok=True)
            if markdown is not None:
                p = target_dir / f"battery_arsenal_{stamp}.md"
                p.write_text(markdown, encoding="utf-8")
                written.append(str(p))
            if csv_text is not None:
                p = target_dir / f"battery_arsenal_{stamp}.csv"
                p.write_text(csv_text, encoding="utf-8")
                written.append(str(p))

        await hass.async_add_executor_job(_write)

        return {
            "files": written,
            "markdown": markdown,
            "csv": csv_text,
            "total_cells": data.total_cells,
            "types": len(data.types),
        }

    async def _async_refresh(call: ServiceCall) -> None:
        for runtime in _runtimes(hass):
            await runtime.coordinator.async_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_REPORT,
        _async_generate_report,
        schema=_GENERATE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _async_refresh)


def async_unload_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_GENERATE_REPORT, SERVICE_REFRESH):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
