"""A password-only or energy-only save never leaves a marker that swallows a later change.

The update listener skips the reload for a save it was told about (a marker in
the entry state). A save that changed nothing runs no listener, so a marker
left behind used to turn the next real change (a name, the dashboard, the link
switched back on) into "password only": no reload, and that state remembered
as the baseline.
"""
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState

import custom_components.open_thermostat as integration
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_PASSWORD
from custom_components.open_thermostat.e32_access import PASSWORD_ONLY_UPDATE, save_password
from custom_components.open_thermostat.energy_input import ENERGY_ONLY_UPDATE, save_energy
from test_ux_review_ha import LoginFake
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)


@pytest.mark.asyncio
async def test_the_same_password_again_leaves_no_marker_and_a_later_change_reloads(hass, manager, monkeypatch):
    parent, hub = product(hass, LoginFake(password="secret"))
    parent._async_set_state(hass, ConfigEntryState.LOADED, None)
    reload = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    state = hass.data[DOMAIN][parent.entry_id]
    save_password(hass, parent, parent.data[CONTROLLER_PASSWORD])  # re-entered unchanged
    assert PASSWORD_ONLY_UPDATE not in state
    hass.config_entries.async_update_entry(parent, options={**parent.options, "shadow_enabled": True})
    await integration._async_options_updated(hass, parent)
    assert reload.await_count == 1  # a real change, not "password only"


@pytest.mark.asyncio
async def test_a_stale_password_marker_never_matches_an_options_change(hass, manager, monkeypatch):
    parent, hub = product(hass, LoginFake(password="secret"))
    parent._async_set_state(hass, ConfigEntryState.LOADED, None)
    reload = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    state = hass.data[DOMAIN][parent.entry_id]
    # A marker for exactly the current data (as an older release left it behind).
    state[PASSWORD_ONLY_UPDATE] = (dict(parent.data), dict(parent.options))
    hass.config_entries.async_update_entry(parent, options={**parent.options, "create_dashboard": True})
    await integration._async_options_updated(hass, parent)
    assert reload.await_count == 1 and PASSWORD_ONLY_UPDATE not in state


@pytest.mark.asyncio
async def test_an_energy_save_that_is_not_applied_leaves_no_marker(hass, manager, monkeypatch):
    parent, hub = product(hass, LoginFake(password="secret"))
    state = hass.data[DOMAIN][parent.entry_id]
    monkeypatch.setattr(hass.config_entries, "async_update_entry", lambda *a, **k: False)
    save_energy(hass, parent, {"boiler_kw": 24.0})
    assert ENERGY_ONLY_UPDATE not in state
