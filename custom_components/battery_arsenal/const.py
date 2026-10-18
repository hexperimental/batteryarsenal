"""Constants for the Battery Arsenal integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "battery_arsenal"
PLATFORMS: Final = [Platform.SENSOR]

# The integration we read from. We never import its code, only its public output.
BATTERY_NOTES_DOMAIN: Final = "battery_notes"

# Device that all Battery Arsenal entities attach to.
SERVICE_DEVICE_NAME: Final = "Battery Arsenal"

# Debounce window for rebuilds so a burst of startup discovery causes one
# recalculation, not hundreds.
DEBOUNCE_SECONDS: Final = 5.0

# --- Options keys ---------------------------------------------------------
CONF_REPORT_PATH: Final = "report_path"
CONF_NON_CONSUMABLE_KEYWORDS: Final = "non_consumable_keywords"
CONF_EXCLUDED_DEVICES: Final = "excluded_devices"
CONF_DEGRADED_MODE: Final = "degraded_mode"
CONF_RESTOCK_MONTHS: Final = "restock_months"

DEFAULT_REPORT_DIR: Final = "battery_arsenal"
DEFAULT_NON_CONSUMABLE_KEYWORDS: Final = [
    "rechargeable",
    "irreplaceable",
    "built in",
    "built-in",
    "li-ion",
    "li ion",
    "lipo",
    "lithium polymer",
]
DEFAULT_DEGRADED_MODE: Final = False
DEFAULT_RESTOCK_MONTHS: Final = 6

# --- Categories -----------------------------------------------------------
CATEGORY_CONSUMABLE: Final = "consumable"
CATEGORY_NON_CONSUMABLE: Final = "non_consumable"
CATEGORY_UNMAPPED: Final = "unmapped"
CATEGORY_UNTRACKED: Final = "untracked"

# --- Battery Notes attribute names (the contract we rely on) --------------
ATTR_BATTERY_TYPE: Final = "battery_type"
ATTR_BATTERY_QUANTITY: Final = "battery_quantity"
ATTR_BATTERY_TYPE_AND_QUANTITY: Final = "battery_type_and_quantity"
ATTR_BATTERY_LAST_REPLACED: Final = "battery_last_replaced"

# Battery Notes event fired on replacement (verified against current docs).
EVENT_BATTERY_REPLACED: Final = "battery_notes_battery_replaced"

# --- Repair issue ids -----------------------------------------------------
ISSUE_BATTERY_NOTES_MISSING: Final = "battery_notes_missing"
ISSUE_CONTRACT_CHANGED: Final = "battery_notes_contract_changed"

# --- Storage --------------------------------------------------------------
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "battery_arsenal_history"
# Cap replacement records kept per device so storage stays small.
MAX_HISTORY_PER_DEVICE: Final = 50
