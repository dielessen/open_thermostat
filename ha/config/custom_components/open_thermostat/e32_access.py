"""The E32 sign-in as Home Assistant sees it: a changed password and the factory password.

* The E32 refuses the stored password (401 on /auth/login): the password was
  changed on the E32. Home Assistant asks for the new one (its re-authentication
  flow, ``async_step_reauth`` in v1_config_flow), and this entry stops trying the
  old one, so the E32's login limit is never hit by Home Assistant.
* The E32 reports ``default_password: true`` in /auth/session: a Repairs issue
  asks to change it on the E32 page. ``false`` removes the issue; firmware that
  does not report the field leaves it alone.
"""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

DEFAULT_PASSWORD_ISSUE = "e32_default_password"
# hass.data state key: the entry data a password-only save produced (the update
# listener then swaps the password in place, without a reload or plan review).
PASSWORD_ONLY_UPDATE = "password_only_data"


def default_password_issue_id(entry):
    return f"{DEFAULT_PASSWORD_ISSUE}_{entry.entry_id}"


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
    ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, is_persistent=False,
                          severity=ir.IssueSeverity.WARNING, translation_key=DEFAULT_PASSWORD_ISSUE,
                          translation_placeholders={"name": entry.title},
                          learn_more_url=password_page_url(entry))


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
    hub = state.get("heating_hub")
    link = getattr(hub, "plan", None)
    if link is not None:
        link.use_password(entry.data[CONTROLLER_PASSWORD])


@callback
def clear(hass, entry):
    ir.async_delete_issue(hass, DOMAIN, default_password_issue_id(entry))
