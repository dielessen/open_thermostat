"""Remove the older Home Assistant rooms once the E32 room plan has replaced them.

Before beta.19, Connect E32 needed one room in Home Assistant (a zone subentry,
"Add room"). The rooms now live in the E32 room plan, so that starter room is no
longer used. These steps remove it, with this integration's own devices and
entities of it, and keep the E32 connected (e32_link / async_link_room_plan).
They are offered under Repairs and under Configure -> Advanced.
"""
from __future__ import annotations

import asyncio

import probatio as vol
from homeassistant.core import callback

from .controller_link import ControllerLinkError, ControllerProvisioningError
from .e32_link import legacy_rooms_pending, legacy_zones, issue_id

PROGRESS = "legacy_rooms_remove"


class LegacyRoomsSteps:
    """legacy_rooms -> legacy_rooms_removing (progress) -> legacy_rooms_done."""

    def _legacy_entry(self):
        return self.config_entry

    def _legacy_error(self, code):
        """The flow's error key for a connection error code."""
        return code

    async def async_step_legacy_rooms(self, user_input=None):
        from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
        entry = self._legacy_entry()
        if entry is None or not legacy_rooms_pending(entry):
            return self.async_abort(reason="legacy_rooms_none")
        errors = {}
        if (error := getattr(self, "_legacy_failure", None)) is not None:
            errors["base"] = error
            self._legacy_failure = None
        zones = legacy_zones(entry)
        if user_input is None and not errors:
            # Firmware before beta.19 cannot confirm the change: say so before the user confirms.
            from .e32_link import async_room_plan_firmware_problem
            if (problem := await async_room_plan_firmware_problem(self.hass, entry)) is not None:
                errors["base"] = self._legacy_error(problem)
        shown = getattr(self, "_legacy_shown", None)
        if user_input is not None and (shown is not None or not zones):
            from .controller_setup_flow import async_link_room_plan
            self._legacy_task = self.hass.async_create_task(async_link_room_plan(
                self.hass, entry, entry.data[CONTROLLER_ADDRESS], entry.data[CONTROLLER_PASSWORD],
                remove_legacy_rooms=True, confirmed_migration=shown), "OpenThermostat remove old rooms")
            self._legacy_shown = None  # a new form after a failure reads the plan again
            return await self.async_step_legacy_rooms_removing()
        # What happens to the E32 rooms: read the plan now, write it only after the user confirmed.
        migration = self._legacy_shown = None
        if zones:
            from .legacy_room_migration import async_read_plan, plan_migration
            plan = await async_read_plan(self.hass, entry)
            if plan is not None:
                _, migration = plan_migration(self.hass, entry, plan, zones)
                self._legacy_shown = migration.signature()
            elif user_input is not None:
                errors["base"] = self._legacy_error("legacy_rooms_plan_unreadable")
        from .legacy_room_migration import describe
        names = sorted(s.title for s in zones)
        return self.async_show_form(step_id="legacy_rooms" if names else "legacy_rooms_finish",
            data_schema=vol.Schema({}), errors=errors,
            description_placeholders={"rooms": ", ".join(names), "count": str(len(names)),
                                      "changes": describe(self.hass, migration) if names else ""})

    async def async_step_legacy_rooms_finish(self, user_input=None):
        """Same action when the rooms are already gone but the E32 link is not finished."""
        return await self.async_step_legacy_rooms(user_input)

    async def async_step_legacy_rooms_removing(self, user_input=None):
        task = self._legacy_task
        if not task.done():
            return self.async_show_progress(step_id="legacy_rooms_removing",
                progress_action=PROGRESS, progress_task=task)
        try:
            self._legacy_result = task.result()
        except asyncio.CancelledError:
            return self.async_abort(reason="legacy_rooms_cancelled")
        except ControllerProvisioningError as err:
            self._legacy_failure = self._legacy_error(
                "controller_partial_connection" if err.device_may_have_changed and str(err) in (
                    "controller_unreachable", "controller_connection_failed") else str(err))
            return self.async_show_progress_done(next_step_id="legacy_rooms")
        except ControllerLinkError as err:
            self._legacy_failure = self._legacy_error(str(err))
            return self.async_show_progress_done(next_step_id="legacy_rooms")
        except Exception:
            self._legacy_failure = self._legacy_error("controller_connection_failed")
            return self.async_show_progress_done(next_step_id="legacy_rooms")
        from homeassistant.helpers import issue_registry as ir
        from .const import DOMAIN
        ir.async_delete_issue(self.hass, DOMAIN, issue_id(self._legacy_entry()))
        return self.async_show_progress_done(next_step_id="legacy_rooms_done")

    async def async_step_legacy_rooms_done(self, user_input=None):
        return self.async_abort(reason="legacy_rooms_removed",
            description_placeholders={"rooms": str(len(self._legacy_result.get("room_ids", [])))})

    @callback
    def async_remove(self):
        task = getattr(self, "_legacy_task", None)
        if task is not None and not task.done() and not task.cancelling():
            task.cancel()
        self._legacy_task = None
        super().async_remove()
