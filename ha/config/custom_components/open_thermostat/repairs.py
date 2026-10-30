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
          "controller_ha_version_unsupported": "ha_version_unsupported",
          "controller_room_plan_update_required": "e32_update_required",
          "controller_session_capacity": "e32_session_capacity",
          "controller_try_again_later": "e32_try_again_later",
          "legacy_rooms_plan_changed": "legacy_rooms_plan_changed",
          "legacy_rooms_plan_failed": "legacy_rooms_plan_failed",
          "legacy_rooms_plan_unreadable": "legacy_rooms_plan_unreadable"}


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


class ChooseSourceRepairFlow(RepairsFlow):
    """"Choose a temperature source for <room>": pick one; the E32 room keeps everything else.

    Only choosing a source is offered here; the room itself is never removed
    from this message (that stays under Configure -> E32 rooms).
    """

    def __init__(self, issue_id, data):
        self._issue_id, self._data = issue_id, data

    async def async_step_init(self, user_input=None):
        return await self.async_step_choose_source()

    async def async_step_choose_source(self, user_input=None):
        import probatio as vol
        from homeassistant.exceptions import HomeAssistantError
        from homeassistant.helpers import issue_registry as ir, selector
        from .const import DOMAIN
        from .e32_room_flow import source_problem
        from .heating_link import heating_hub
        from .room_plan import has_room_plan, plan_room
        entry = self.hass.config_entries.async_get_entry(self._data.get("entry_id"))
        if entry is None or not has_room_plan(entry) or entry.entry_id not in self.hass.data.get(DOMAIN, {}):
            return self.async_abort(reason="e32_rooms_unavailable")
        link = heating_hub(self.hass, entry).plan
        room_id, dead = self._data.get("room_id"), set(self._data.get("entities") or ())
        try:
            plan = link.plan or await link.async_read()
        except HomeAssistantError:
            return self.async_abort(reason="e32_unreachable")
        room = plan_room(plan, room_id)
        if room is None:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            return self.async_abort(reason="room_missing")
        errors, placeholders = {}, {"room": room.get("name") or room_id, "source": ""}
        if user_input is not None:
            source = user_input.get("source") or ""
            if problem := source_problem(self.hass, source):
                errors["source"], placeholders["source"] = problem, source
            else:
                def change(room):
                    kept = [s for s in room["sources"] if not (s.get("type") == "ha" and s.get("id") in dead)
                            and s != {"type": "ha", "id": source}]
                    room["sources"] = [{"type": "ha", "id": source}, *kept]
                try:
                    await link.async_change_room(room_id, change)
                except HomeAssistantError:
                    errors["base"] = "save_failed"
                else:
                    ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
                    return self.async_create_entry(data={})
        return self.async_show_form(step_id="choose_source", data_schema=vol.Schema({
            vol.Required("source"): selector.EntitySelector({"filter": [
                {"domain": "climate"}, {"domain": "sensor", "device_class": "temperature"}]}),
        }), errors=errors, description_placeholders=placeholders)


async def async_create_fix_flow(hass, issue_id, data):
    from .legacy_room_migration import CHOOSE_SOURCE_ISSUE
    if not isinstance(data, dict):
        raise ValueError("unknown_issue")
    if issue_id.startswith(CHOOSE_SOURCE_ISSUE + "_"):
        return ChooseSourceRepairFlow(issue_id, data)
    from .e32_setting_device import ROOM_PROGRAMS_ISSUE, RoomProgramsRepairFlow
    if issue_id.startswith(ROOM_PROGRAMS_ISSUE + "_"):  # a week program and setting device per room
        return RoomProgramsRepairFlow(issue_id, data)
    if not issue_id.startswith(LEGACY_ROOMS_ISSUE + "_"):
        raise ValueError("unknown_issue")
    return LegacyRoomsRepairFlow(data.get("entry_id"))
