"""Configure -> Advanced -> Restore settings to this E32: one stored backup back onto an E32.

Choose a backup by date (and, for a replacement E32, its address and
password), let the E32 check it and read what changes, what is skipped and
what must be entered again, then tick the confirmation: only then Home
Assistant backs up the E32 as it is and restores the chosen file. The rooms
keep the mode of the backup; a new or reset E32 controls the boiler only after
its owner confirms the takeover on the E32 page. A restore that changes the network or Bluetooth restarts the E32;
Home Assistant waits until it answers again.
"""
from __future__ import annotations

import asyncio

import probatio as vol
from homeassistant.core import callback
from homeassistant.helpers import selector

from .controller_link import BackupRejected, ControllerLinkError, controller_address
from .e32_backup import RestoreCheck, backups, created_text, credentials, reenter_text, record_label, summary_text

# The E32's refusals (ConfigBackupRoute.cpp) as this form's errors.
REFUSALS = {
    "boiler_owned": "e32_restore_boiler_owned",
    "busy": "e32_restore_busy",
    "settings_changed": "e32_restore_settings_changed",
    "wrong_passphrase": "e32_restore_wrong_passphrase",
    "invalid_passphrase": "e32_restore_wrong_passphrase",
    "newer_schema": "e32_restore_newer_backup",
    "save_failed_restored": "e32_restore_save_failed",
    "save_partial": "e32_restore_save_partial",
    "out_of_memory": "e32_restore_busy",
}
# The sign-in and connection codes this form names itself (controller_connection's texts).
CONNECTION_ERRORS = frozenset({
    "controller_address_invalid", "controller_password_required", "controller_auth_failed",
    "controller_unreachable", "controller_update_required", "controller_session_capacity",
    "controller_try_again_later", "controller_response_invalid",
})


def restore_error(err):
    if isinstance(err, BackupRejected):
        return REFUSALS.get(err.error, "e32_restore_invalid" if err.status in (400, 413) else "e32_restore_failed")
    code = str(err) if isinstance(err, ControllerLinkError) else ""
    return code if code in CONNECTION_ERRORS else "e32_restore_failed"


class E32RestoreSteps:
    """The options-flow steps of a restore (mixed into ProductOptionsFlow)."""

    def _restore_language(self):
        return self.hass.config.language

    async def async_step_e32_restore(self, user_input=None):
        from .controller_setup_flow import CONTROLLER_ADDRESS
        entry = self.config_entry
        manager = backups(self.hass, entry)
        if manager is None:
            return self.async_abort(reason="e32_restore_unavailable")
        records = manager.records()
        if not records:
            return self.async_abort(reason="e32_restore_no_backups")
        errors = {}
        if (error := getattr(self, "_restore_error", None)) is not None:
            errors["base"] = error
            self._restore_error = None
        if user_input is not None:
            try:
                record = manager.record(user_input.get("backup"))
                if record is None:
                    raise ControllerLinkError("e32_restore_failed")
                address = controller_address(user_input.get("address", ""))
                password = user_input.get("password") or ""
                if type(password) is not str:
                    raise ControllerLinkError("controller_password_required")
                if not password:
                    # Never send the stored password to another address.
                    if address != entry.data.get(CONTROLLER_ADDRESS):
                        raise ControllerLinkError("controller_password_required")
                    password = credentials(entry)[1]
                if not 1 <= len(password) <= 128:
                    raise ControllerLinkError("controller_password_required")
            except ControllerLinkError as err:
                errors["base"] = restore_error(err)
            else:
                self._restore_choice = (record["id"], address)
                self._restore_task = self.hass.async_create_task(
                    manager.async_check(address, password, record["id"]), "OpenThermostat check E32 backup")
                return self._restore_wait("e32_restore_checking", "e32_restore_check")
        language = self._restore_language()
        chosen, address = getattr(self, "_restore_choice", (records[0]["id"], entry.data.get(CONTROLLER_ADDRESS, "")))
        if manager.record(chosen) is None:
            chosen = records[0]["id"]
        schema = vol.Schema({
            vol.Required("backup", default=chosen): selector.SelectSelector({"options": [
                {"value": r["id"], "label": record_label(r, language)} for r in records]}),
            vol.Required("address", default=address): str,
            # No stored password is ever sent back to a browser.
            vol.Optional("password"): selector.TextSelector({"type": "password"}),
        })
        return self.async_show_form(step_id="e32_restore", data_schema=schema, errors=errors,
                                    description_placeholders={"count": str(len(records))})

    def _restore_wait(self, step_id, action):
        # Always shown first, also for a task that already finished: the form's
        # input must never be handed on to the step after the progress.
        return self.async_show_progress(step_id=step_id, progress_action=action, progress_task=self._restore_task)

    async def _restore_progress(self, step_id, action, done_step):
        task = self._restore_task
        if task is None:
            return self.async_abort(reason="e32_restore_cancelled")
        if not task.done():
            return self._restore_wait(step_id, action)
        self._restore_task = None
        try:
            self._restore_result = task.result()
        except asyncio.CancelledError:
            return self.async_abort(reason="e32_restore_cancelled")
        except Exception as err:  # noqa: BLE001 - every failure becomes a named form error
            self._restore_error = restore_error(err)
            return self.async_show_progress_done(next_step_id="e32_restore")
        return self.async_show_progress_done(next_step_id=done_step)

    async def async_step_e32_restore_checking(self, user_input=None):
        return await self._restore_progress("e32_restore_checking", "e32_restore_check", "e32_restore_confirm")

    async def async_step_e32_restore_confirm(self, user_input=None):
        from .native_provisioning import SOURCE_OPTION
        from .controller_setup_flow import CONTROLLER_ID
        entry = self.config_entry
        manager = backups(self.hass, entry)
        check = getattr(self, "_restore_result", None)
        record = (manager.record(check.record_id) if manager is not None and isinstance(check, RestoreCheck)
                  else None)
        if record is None:
            return self.async_abort(reason="e32_restore_unavailable")
        if (check.identity is not None and entry.data.get(CONTROLLER_ID) not in (None, check.identity)
                and SOURCE_OPTION in entry.options):
            # Another E32 cannot take over the older Home Assistant room profile of this installation.
            self._restore_error = "e32_restore_other_e32"
            return await self.async_step_e32_restore()
        if not check.summary["changes"]:
            return self.async_abort(reason="e32_restore_nothing")
        errors = {}
        if user_input is not None:
            if user_input.get("confirm") is not True:
                errors["base"] = "e32_restore_confirm_required"
            else:
                self._restore_check = check
                self._restore_task = self.hass.async_create_task(
                    manager.async_restore(check), "OpenThermostat restore E32 backup")
                return self._restore_wait("e32_restore_applying", "e32_restore_apply")
        return self.async_show_form(step_id="e32_restore_confirm", errors=errors, data_schema=vol.Schema({
            vol.Required("confirm", default=False): selector.BooleanSelector()}),
            description_placeholders={"created": created_text(record),
                                      "summary": summary_text(check.summary, self._restore_language())})

    async def async_step_e32_restore_applying(self, user_input=None):
        return await self._restore_progress("e32_restore_applying", "e32_restore_apply", "e32_restore_done")

    async def async_step_e32_restore_done(self, user_input=None):
        result = self._restore_result
        reason = ("e32_restore_done_online" if result["online"] is True
                  else "e32_restore_done_waiting" if result["restart_scheduled"]
                  else "e32_restore_done_restart" if result["restart"] else "e32_restore_done")
        return self.async_abort(reason=reason, description_placeholders={
            "reenter": reenter_text(result["reenter"], self._restore_language())})

    @callback
    def async_remove(self):
        task = getattr(self, "_restore_task", None)
        # A check may stop; a restore that started is left to finish (the E32 applies it as one).
        if task is not None and not task.done() and getattr(self, "_restore_check", None) is None:
            task.cancel()
        self._restore_task = None
        super().async_remove()
