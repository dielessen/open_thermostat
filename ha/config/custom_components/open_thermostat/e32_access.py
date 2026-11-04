"""The E32 sign-in as Home Assistant sees it: a changed password and the factory password.

* The E32 refuses the stored password (401 on /auth/login): the password was
  changed on the E32. Home Assistant asks for the new one (its re-authentication
  flow, ``async_step_reauth`` in v1_config_flow), and this entry stops trying the
  old one, so the E32's login limit is never hit by Home Assistant.
* The E32 reports ``default_password: true`` in /auth/session: a fixable Repairs
  issue, "Choose a new E32 password", changes it in one step (POST /auth/password
  with the stored password) and stores the new one in the entry. Since rc.2 the
  E32 refuses every change while it has the factory password (403
  password_change_required); reads keep working and the heating keeps running on
  its stored plan and MQTT inputs. ``false`` removes the issue; firmware that does
  not report the field leaves it alone.
"""
from __future__ import annotations

import logging

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

DEFAULT_PASSWORD_ISSUE = "e32_default_password"
# hass.data state key: the entry data a password-only save produced (the update
# listener then swaps the password in place, without a reload or plan review).
PASSWORD_ONLY_UPDATE = "password_only_data"
_LOGGER = logging.getLogger(__name__)
# The E32's refusals of POST /auth/password -> this flow's errors.
PASSWORD_REFUSALS = {"password_too_short": "password_too_short", "password_too_long": "password_too_long",
                     "password_wrong": "e32_password_stored_wrong", "password_change_busy": "e32_busy",
                     "password_storage_failed": "e32_password_not_saved"}
SIGN_IN_REFUSALS = {"controller_auth_failed": "e32_password_stored_wrong",
                    "controller_try_again_later": "e32_try_again_later",
                    "controller_session_capacity": "e32_session_capacity",
                    "controller_password_change_required": "e32_unreachable"}


def default_password_issue_id(entry):
    return f"{DEFAULT_PASSWORD_ISSUE}_{entry.entry_id}"


# hass.data key: {entry id: the stored E32 password the E32 refused}. Every part of an entry that
# signs in with the stored password (the room plan and every write through it, the backups, the
# firmware check, Configure forms) checks it first, so a password changed on the E32 costs one
# failed sign-in in total, not one per part (R4-05): the E32 limits failed sign-ins and would lock
# the owner's browser out as well. Kept over a reload of the entry; a saved password clears it.
REJECTED_PASSWORDS = DOMAIN + "_rejected_password"


def _rejected(hass, entry):
    data = getattr(hass, "data", None)
    if entry is None or not isinstance(data, dict):
        return None
    return data.setdefault(REJECTED_PASSWORDS, {})


def _key(entry):
    return getattr(entry, "entry_id", None) or id(entry)


def password_rejected(hass, entry, password):
    """True when the E32 already refused this password of the entry: do not sign in with it again."""
    rejected = _rejected(hass, entry)
    return rejected is not None and password is not None and rejected.get(_key(entry)) == password


@callback
def remember_rejected(hass, entry, password):
    """Note the refused password for every part of the entry; True when it was not noted yet."""
    rejected = _rejected(hass, entry)
    if rejected is None:
        return True
    if rejected.get(_key(entry)) == password:
        return False
    rejected[_key(entry)] = password
    return True


@callback
def mark_rejected(hass, entry, password):
    """The E32 refused the stored password: no part of the entry tries it again; ask for the new one (once)."""
    if remember_rejected(hass, entry, password):
        login_rejected(hass, entry)


@callback
def clear_rejected(hass, entry):
    """A new (or re-entered) password: every part may sign in again."""
    rejected = _rejected(hass, entry)
    if rejected is not None:
        rejected.pop(_key(entry), None)


@callback
def login_rejected(hass, entry):
    """The stored E32 password no longer works: ask the user for the new one (once)."""
    if entry is not None and hass.config_entries.async_get_entry(entry.entry_id) is entry:
        entry.async_start_reauth(hass)


@callback
def report_password(hass, entry, default):
    """The /auth/session answer after a login: show or clear the factory-password issue."""
    if entry is None or type(default) is not bool:
        return
    issue_id = default_password_issue_id(entry)
    if not default:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=True, is_persistent=False,
                          severity=ir.IssueSeverity.WARNING, translation_key=DEFAULT_PASSWORD_ISSUE,
                          translation_placeholders={"name": entry.title},
                          learn_more_url=password_page_url(entry), data={"entry_id": entry.entry_id})


def password_page_url(entry):
    """The E32's own password form (About page), or None without a valid stored address.

    Only the address is used: the password itself never leaves the entry.
    """
    from .controller_link import ControllerLinkError, controller_address
    from .controller_setup_flow import CONTROLLER_ADDRESS
    try:
        return controller_address(entry.data.get(CONTROLLER_ADDRESS)) + "/#about"
    except ControllerLinkError:
        return None


@callback
def save_password(hass, entry, password):
    """Store a new E32 password (re-authentication): no reload, no new plan review.

    A loaded entry swaps the password in place through its update listener
    (password_only_update); an entry that did not load is reloaded.
    """
    from homeassistant.config_entries import ConfigEntryState
    from .controller_setup_flow import CONTROLLER_PASSWORD
    clear_rejected(hass, entry)  # the E32 accepted it just now (also the same password entered again)
    data = {**entry.data, CONTROLLER_PASSWORD: password}
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if entry.state is ConfigEntryState.LOADED and state is not None:
        if data == dict(entry.data):
            # Unchanged (the same password entered again): no update, so no marker
            # that a later, real change would be mistaken for.
            apply_password(hass, entry, state)
            return
        # The marker names the whole entry it expects (data and options): a stale
        # one never matches a later options change.
        state[PASSWORD_ONLY_UPDATE] = (data, dict(entry.options))
        if not hass.config_entries.async_update_entry(entry, data=data):
            state.pop(PASSWORD_ONLY_UPDATE, None)
        return
    hass.config_entries.async_update_entry(entry, data=data)
    hass.config_entries.async_schedule_reload(entry.entry_id)


def password_only_update(state, entry):
    """True (once) when the last entry change was a password-only save (save_password)."""
    pending = state.pop(PASSWORD_ONLY_UPDATE, None) if state is not None else None
    return pending is not None and pending == (dict(entry.data), dict(entry.options))


@callback
def apply_password(hass, entry, state):
    """The running entry uses the new password from now on (and may log in again)."""
    from .controller_setup_flow import CONTROLLER_PASSWORD
    clear_rejected(hass, entry)
    hub = state.get("heating_hub")
    link = getattr(hub, "plan", None)
    if link is not None:
        link.use_password(entry.data[CONTROLLER_PASSWORD])


@callback
def clear(hass, entry):
    ir.async_delete_issue(hass, DOMAIN, default_password_issue_id(entry))


class ChooseE32PasswordRepairFlow(RepairsFlow):
    """"Choose a new E32 password": one form, the E32 changes it and the entry stores it.

    Signs in with the stored (factory) password, POSTs /auth/password and saves the
    new password in the entry (save_password: no reload, no plan review). Holds the
    room-plan link's lock, so no write signs in with the old password meanwhile.
    """

    def __init__(self, issue_id, data):
        self._issue_id, self._data = issue_id, data if isinstance(data, dict) else {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_choose_password(user_input)

    async def async_step_choose_password(self, user_input=None):
        import asyncio
        import probatio as vol
        from homeassistant.helpers import selector
        from .controller_link import (ControllerClient, ControllerLinkError, ControllerLoginRejected,
                                      PasswordChangeRejected)
        from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
        entry = self.hass.config_entries.async_get_entry(self._data.get("entry_id"))
        address = entry.data.get(CONTROLLER_ADDRESS) if entry is not None else None
        stored = entry.data.get(CONTROLLER_PASSWORD) if entry is not None else None
        if not address or not stored:
            return self.async_abort(reason="e32_password_no_connection")
        secret = selector.TextSelector({"type": "password", "autocomplete": "new-password"})
        schema = vol.Schema({vol.Required("new_password"): secret, vol.Required("repeat_password"): secret})
        placeholders = {"name": entry.title}
        if user_input is None:
            return self.async_show_form(step_id="choose_password", data_schema=schema,
                                        description_placeholders=placeholders)
        new, again = user_input.get("new_password"), user_input.get("repeat_password")
        errors = {}
        # Characters as the E32 counts them (code points, WebPassword::checkNew): 8 to 64.
        if type(new) is not str or len(new) < 8:
            errors["new_password"] = "password_too_short"
        elif len(new) > 64:
            errors["new_password"] = "password_too_long"
        elif new != again:
            errors["repeat_password"] = "password_mismatch"
        if errors:
            return self.async_show_form(step_id="choose_password", data_schema=schema, errors=errors,
                                        description_placeholders=placeholders)
        state = self.hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
        link = getattr(state.get("heating_hub"), "plan", None)
        lock = getattr(link, "_lock", None) or asyncio.Lock()
        try:
            # The owner asks for this: one sign-in per submit, also with a password refused before.
            async with lock:
                async with ControllerClient(address) as client:
                    await client.async_login(stored)
                    clear_rejected(self.hass, entry)  # it works (again): every part may sign in
                    if client.default_password is False:
                        clear(self.hass, entry)
                        return self.async_abort(reason="e32_password_already_changed")
                    await client.async_change_password(stored, new)
                    # Still under the lock: the next write already signs in with the new password.
                    save_password(self.hass, entry, new)
                    if link is not None:
                        link.use_password(new)
        except ControllerLoginRejected:
            mark_rejected(self.hass, entry, stored)  # Home Assistant asks for the current password (reauth)
            errors["base"] = "e32_password_stored_wrong"
        except PasswordChangeRejected as err:
            key = PASSWORD_REFUSALS.get(err.error, "e32_unreachable")
            errors["new_password" if key.startswith("password_") else "base"] = key
        except ControllerLinkError as err:
            errors["base"] = SIGN_IN_REFUSALS.get(str(err), "e32_unreachable")
        if errors:
            return self.async_show_form(step_id="choose_password", data_schema=schema, errors=errors,
                                        description_placeholders=placeholders)
        _LOGGER.info("The E32 password of %s was changed through Repairs", entry.title)
        clear(self.hass, entry)
        return self.async_create_entry(data={})
