"""Repair flows for Battery Arsenal.

Both issues are informational (is_fixable=False) and clear automatically when
the underlying condition resolves, so this just satisfies the repairs platform
contract.
"""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict | None
) -> RepairsFlow:
    return ConfirmRepairFlow()
