"""Repairs: remove the older Home Assistant rooms that the E32 room plan replaced."""
from __future__ import annotations

from homeassistant.components.repairs import RepairsFlow

from .e32_link import LEGACY_ROOMS_ISSUE
from .legacy_rooms_flow import LegacyRoomsSteps

# Connection error codes -> the few messages of this Repairs flow. Every other
# code points to Configure -> Connect E32, which explains it in detail.
ERRORS = {"controller_auth_failed": "e32_password", "controller_unreachable": "e32_unreachable",
          "controller_broker_setup_required": "broker_login", "controller_mqtt_unconfirmed": "mqtt_unconfirmed",
          "controller_busy_or_conflict": "e32_busy", "controller_boot_unconfirmed": "e32_busy",
          "controller_ha_version_unsupported": "ha_version_unsupported"}


class LegacyRoomsRepairFlow(LegacyRoomsSteps, RepairsFlow):
    def __init__(self, entry_id):
        self._entry_id = entry_id

    def _legacy_entry(self):
        return self.hass.config_entries.async_get_entry(self._entry_id)

    def _legacy_error(self, code):
        return ERRORS.get(code, "connection_failed")

    async def async_step_init(self, user_input=None):
        return await self.async_step_legacy_rooms()

    async def async_step_legacy_rooms_done(self, user_input=None):
        return self.async_create_entry(data={})


async def async_create_fix_flow(hass, issue_id, data):
    if not issue_id.startswith(LEGACY_ROOMS_ISSUE + "_") or not isinstance(data, dict):
        raise ValueError("unknown_issue")
    return LegacyRoomsRepairFlow(data.get("entry_id"))
