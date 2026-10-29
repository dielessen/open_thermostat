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
                          translation_placeholders={"name": entry.title})


@callback
def clear(hass, entry):
    ir.async_delete_issue(hass, DOMAIN, default_password_issue_id(entry))
