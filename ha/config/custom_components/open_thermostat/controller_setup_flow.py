"""Ordinary E32 connection form over existing HA entry and native operations."""
from __future__ import annotations

import asyncio
import logging

import probatio as vol
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN
from .controller_link import (
    ControllerClient, ControllerLinkError, ControllerProvisioningError,
    controller_address, async_prepare_controller_link, async_provision_controller,
)
from .controller_connection import async_synchronise_controller_plan, async_wait_room_plan_link
from .e32_link import (async_prepare_room_plan_link, async_provision_room_plan, legacy_zones,
                       remove_legacy_room_devices, without_legacy_rooms)
from .native_plan import native_entry_state
from .native_provisioning import SOURCE_OPTION, source_selection
from .product import configuration_snapshot, commit_configuration, is_product
from .v1_model import CONF_ENABLED, MODE_SHADOW, integration_mode

CONTROLLER_ADDRESS = "controller_address"
CONTROLLER_PASSWORD = "controller_password"
CONTROLLER_ID = "controller_id"
_LOGGER = logging.getLogger(__name__)


def _private_guard(hass, entry, before):
    if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or native_entry_state(entry) != before):
        raise ControllerLinkError("setup_changed")


def _check_installation(hass, entry):
    """Checks shared by both connection routes, before any E32 contact."""
    from . import (_selected_graph_data_profile, _selected_graph_controller_source,
                   _selected_controller_policy_source_profile, _NATIVE_PLAN_SOURCE_PROFILES)
    from .product import ha_version_supported
    if not ha_version_supported(hass):
        raise ControllerLinkError("controller_ha_version_unsupported")
    if not is_product(entry) or integration_mode(entry) != MODE_SHADOW:
        raise ControllerLinkError("controller_room_configuration_invalid")
    if (any(p.policy.entry_unique_id == entry.unique_id for p in _NATIVE_PLAN_SOURCE_PROFILES)
            or _selected_graph_data_profile(entry) is not None
            or _selected_graph_controller_source(entry) is not None
            or _selected_controller_policy_source_profile(entry) is not None):
        raise ControllerLinkError("controller_source_conflict")


async def async_connect_installation(hass, entry, address, password):
    """One explicit configure/apply operation; never a physical qualification.

    Without older Home Assistant rooms (zone subentries) this links the E32 room
    plan only (async_link_room_plan). Installations that still have such rooms
    keep the native room-profile route below, unchanged.
    """
    from homeassistant.config_entries import ConfigEntryState

    _check_installation(hass, entry)
    if not legacy_zones(entry):
        return await async_link_room_plan(hass, entry, address, password)
    address = controller_address(address)
    before_private = native_entry_state(entry)
    committed_private = None
    expected = None
    source = None
    device_changed = False
    try:
        async with ControllerClient(address) as client:
            # A bad password or old firmware must not pause a working runtime.
            await client.async_login(password)
            _private_guard(hass, entry, before_private)
            device, _ = await client.async_read("/config/device")
            _private_guard(hass, entry, before_private)
            if type(device.get("mqtt")) is not dict:
                raise ControllerLinkError("controller_response_invalid")
            identity = device["mqtt"].get("native_source_device_id")
            if entry.data.get(CONTROLLER_ID) not in (None, identity):
                raise ControllerLinkError("controller_source_conflict")
            state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
            runtime = state.get("v1_runtime")
            if runtime is not None and runtime.enabled:
                await runtime.async_stop()
                _private_guard(hass, entry, before_private)
            if entry.options.get(CONF_ENABLED, False):
                commit_configuration(hass, entry, configuration_snapshot(entry),
                    options={**entry.options, CONF_ENABLED: False})
                before_private = native_entry_state(entry)
            plan = await async_prepare_controller_link(hass, entry, client)
            _private_guard(hass, entry, before_private)
            await async_provision_controller(hass, entry, client, plan, password)
            device_changed = not plan.settings_unchanged or plan.needs_reboot
            _private_guard(hass, entry, plan.private_entry_state)
            source = plan.source
        # Credentials belong to the normal HA ConfigEntry, not a second store.
        # Cookies/CSRF/readback tags were closed above and are never persisted.
        _private_guard(hass, entry, plan.private_entry_state)
        needs_reload = entry.state is not ConfigEntryState.LOADED
        commit_configuration(hass, entry, plan.before,
            data={**entry.data, CONTROLLER_ADDRESS: address, CONTROLLER_PASSWORD: password,
                  CONTROLLER_ID: source.policy.controller_id},
            options={**entry.options, SOURCE_OPTION: source_selection(source), CONF_ENABLED: True})
        expected = configuration_snapshot(entry)
        committed_private = native_entry_state(entry)
        # The rooms are the E32 plan from now on: Home Assistant caches which
        # subentry buttons an entry has, so drop that cache and the older
        # "Add room" button goes at once, not only after a restart.
        if hasattr(entry, "_supported_subentry_types"):
            object.__setattr__(entry, "_supported_subentry_types", None)
        if needs_reload:
            # A previously failed/unloaded entry has no integration listener.
            # Loaded entries use their one existing update listener instead.
            await hass.config_entries.async_reload(entry.entry_id)
            _private_guard(hass, entry, committed_private)
        result = await async_synchronise_controller_plan(hass, entry, source, expected,
                                                        private_expected=committed_private)
        _private_guard(hass, entry, committed_private)
        result["admin_logout_confirmed"] = client.logout_confirmed
        return result
    except BaseException as error:
        # Cancellation/uncertain apply never restores an old ready state. Stop
        # only this operation's still-exact owner, preserving saved intent.
        if (committed_private is not None
                and hass.config_entries.async_get_entry(entry.entry_id) is entry
                and native_entry_state(entry) == committed_private):
            state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
            runtime = state.get("v1_runtime")
            if native_entry_state(entry) == committed_private:
                commit_configuration(hass, entry, expected,
                    options={**entry.options, CONF_ENABLED: False})
            if (runtime is not None and getattr(runtime, "native_plan_source", None) == source
                    and runtime.enabled):
                try:
                    async with asyncio.timeout(10):
                        await runtime.async_stop()
                except Exception:
                    # The saved owner is already disabled. Do not replace the
                    # original failure with a transport exception or its details.
                    _LOGGER.warning("E32 connection cleanup unconfirmed; saved connection disabled")
        if isinstance(error, asyncio.CancelledError):
            raise
        if isinstance(error, ControllerProvisioningError):
            raise
        code = str(error) if isinstance(error, ControllerLinkError) else "controller_connection_failed"
        raise ControllerProvisioningError(code, device_may_have_changed=device_changed) from None


async def async_link_room_plan(hass, entry, address, password, *, remove_legacy_rooms=False,
                               confirmed_migration=None):
    """Connect the E32 room plan, without (or after removing) older Home Assistant rooms.

    Same order as the native route: log in, stop this entry's own link, read and
    check the E32, save and restart once, store the address and password, then
    wait for the E32's heating report over MQTT. With remove_legacy_rooms the
    older Home Assistant rooms (and only this entry's devices of them) are
    removed in one save after the E32 checks passed and before the E32 is
    changed; a later Connect E32 then finishes any interrupted link.

    Before that removal, E32 rooms that use an entity of an older room are moved
    to the entity it was built on (legacy_room_migration): the E32 plan is
    written first (revision checked); when that write fails nothing is removed.
    confirmed_migration is the outcome the user confirmed (Migration.signature());
    a different one stops with legacy_rooms_plan_changed. Afterwards the older
    room's thermostat is handed over to the E32 room's thermostat.
    """
    from homeassistant.config_entries import ConfigEntryState
    from .native_provisioning import SOURCE_OPTION
    _check_installation(hass, entry)
    if legacy_zones(entry) and not remove_legacy_rooms:
        raise ControllerLinkError("controller_room_configuration_invalid")
    address = controller_address(address)
    before_private = native_entry_state(entry)
    committed_private = expected = None
    device_changed = False
    try:
        async with ControllerClient(address) as client:
            await client.async_login(password)
            _private_guard(hass, entry, before_private)
            device, _ = await client.async_read("/config/device")
            _private_guard(hass, entry, before_private)
            if type(device.get("mqtt")) is not dict:
                raise ControllerLinkError("controller_response_invalid")
            identity = device["mqtt"].get("native_source_device_id")
            if entry.data.get(CONTROLLER_ID) not in (None, identity):
                raise ControllerLinkError("controller_source_conflict")
            migration = None
            if remove_legacy_rooms and legacy_zones(entry):
                # The E32 rooms first: when this write fails, everything (also the
                # running link) stays as it was and nothing is removed.
                from . import legacy_room_migration as migrate
                migration, _ = await migrate.async_write_migration(
                    hass, entry, client, legacy_zones(entry), confirmed_migration)
                _private_guard(hass, entry, before_private)
            state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
            runtime = state.get("v1_runtime")
            if runtime is not None and runtime.enabled:
                await runtime.async_stop()
                _private_guard(hass, entry, before_private)
            if entry.options.get(CONF_ENABLED, False):
                commit_configuration(hass, entry, configuration_snapshot(entry),
                    options={**entry.options, CONF_ENABLED: False})
                before_private = native_entry_state(entry)
            plan = await async_prepare_room_plan_link(hass, entry, client)
            _private_guard(hass, entry, before_private)
            if migration is not None and legacy_zones(entry):
                handover = migrate.capture_handover(hass, entry, migration)
                changes, removed = without_legacy_rooms(entry)
                commit_configuration(hass, entry, plan.before, **changes)
                remove_legacy_room_devices(hass, entry, removed)
                await migrate.async_apply_handover(hass, entry, handover)
                migrate.note_rooms_without_source(hass, entry, migration)
                plan = await async_prepare_room_plan_link(hass, entry, client)
                before_private = plan.private_entry_state
            await async_provision_room_plan(hass, entry, client, plan, password)
            device_changed = not plan.settings_unchanged or plan.needs_reboot
            _private_guard(hass, entry, plan.private_entry_state)
        needs_reload = entry.state is not ConfigEntryState.LOADED
        commit_configuration(hass, entry, plan.before,
            data={**entry.data, CONTROLLER_ADDRESS: address, CONTROLLER_PASSWORD: password,
                  CONTROLLER_ID: plan.controller_id},
            options={**{k: v for k, v in entry.options.items() if k != SOURCE_OPTION}, CONF_ENABLED: True})
        expected = configuration_snapshot(entry)
        committed_private = native_entry_state(entry)
        # The rooms are the E32 room plan: drop HA's cached subentry buttons.
        if hasattr(entry, "_supported_subentry_types"):
            object.__setattr__(entry, "_supported_subentry_types", None)
        if needs_reload:
            await hass.config_entries.async_reload(entry.entry_id)
            _private_guard(hass, entry, committed_private)
        result = await async_wait_room_plan_link(hass, entry, expected, private_expected=committed_private)
        _private_guard(hass, entry, committed_private)
        return {**result, "controller_id": plan.controller_id, "room_ids": list(plan.room_ids),
                "admin_logout_confirmed": client.logout_confirmed, "authorizes_physical_outputs": False}
    except BaseException as error:
        # Same rule as the native route: never restore an old state; stop only
        # this operation's own link and keep the saved intent (disabled).
        if (committed_private is not None
                and hass.config_entries.async_get_entry(entry.entry_id) is entry
                and native_entry_state(entry) == committed_private):
            state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
            runtime = state.get("v1_runtime")
            commit_configuration(hass, entry, expected, options={**entry.options, CONF_ENABLED: False})
            if (runtime is not None and getattr(runtime, "native_plan_source", None) is None
                    and runtime.enabled):
                try:
                    async with asyncio.timeout(10):
                        await runtime.async_stop()
                except Exception:
                    _LOGGER.warning("E32 connection cleanup unconfirmed; saved connection disabled")
        if isinstance(error, asyncio.CancelledError):
            raise
        if isinstance(error, ControllerProvisioningError):
            raise
        code = str(error) if isinstance(error, ControllerLinkError) else "controller_connection_failed"
        raise ControllerProvisioningError(code, device_may_have_changed=device_changed) from None


class ControllerSetupFlow:
    """One form and native progress lifecycle, no room wizard or raw profiles."""

    async def async_step_controller_connection(self, user_input=None):
        entry = self.config_entry
        errors = {}
        error = getattr(self, "_controller_error", None)
        if error is not None:
            errors["base"] = error
            self._controller_error = None
        if user_input is not None:
            try:
                address = controller_address(user_input["address"])
                self._controller_form_address = address
                password = user_input.get("password", "")
                if type(password) is not str:
                    raise ControllerLinkError("controller_password_required")
                if not password:
                    # Never send a previously stored password to a changed host.
                    if address != entry.data.get(CONTROLLER_ADDRESS):
                        raise ControllerLinkError("controller_password_required")
                    password = entry.data.get(CONTROLLER_PASSWORD)
                if type(password) is not str or not 1 <= len(password) <= 128:
                    raise ControllerLinkError("controller_password_required")
            except (KeyError, ControllerLinkError) as err:
                errors["base"] = str(err) if isinstance(err, ControllerLinkError) else "controller_address_invalid"
            else:
                self._controller_task = self.hass.async_create_task(
                    async_connect_installation(self.hass, entry, address, password),
                    "OpenThermostat connect controller")
                return await self.async_step_controller_connecting()
        schema = vol.Schema({
            vol.Required("address", default=getattr(self, "_controller_form_address",
                entry.data.get(CONTROLLER_ADDRESS, ""))): str,
            # No retained/suggested/default password is ever returned to a client.
            vol.Optional("password"): selector.TextSelector({"type": "password"}),
        })
        return self.async_show_form(step_id="controller_connection", data_schema=schema,
            errors=errors)

    async def async_step_controller_connecting(self, user_input=None):
        task = self._controller_task
        if not task.done():
            return self.async_show_progress(step_id="controller_connecting",
                progress_action="controller_connect", progress_task=task)
        try:
            self._controller_result = task.result()
        except asyncio.CancelledError:
            return self.async_abort(reason="controller_connection_cancelled")
        except ControllerProvisioningError as err:
            self._controller_error = ("controller_partial_connection" if err.device_may_have_changed
                                      else str(err))
            return self.async_show_progress_done(next_step_id="controller_connection")
        except ControllerLinkError as err:
            self._controller_error = str(err)
            return self.async_show_progress_done(next_step_id="controller_connection")
        except Exception:
            self._controller_error = "controller_connection_failed"
            return self.async_show_progress_done(next_step_id="controller_connection")
        return self.async_show_progress_done(next_step_id="controller_connected")

    async def async_step_controller_connected(self, user_input=None):
        if user_input is not None:
            return self.async_abort(reason="controller_connection_complete")
        rooms = len(self._controller_result["room_ids"])
        if rooms == 0 and hasattr(self, "async_step_e32_room_add"):
            # A new installation: the next step is its first room (the same dialog goes on).
            return self.async_show_form(step_id="controller_connected_first_room", data_schema=vol.Schema({}))
        return self.async_show_form(step_id="controller_connected", data_schema=vol.Schema({}),
            description_placeholders={"rooms": str(rooms)})

    async def async_step_controller_connected_first_room(self, user_input=None):
        """E32 connected without rooms: submit opens the room form (e32_room_flow.py)."""
        from homeassistant.exceptions import HomeAssistantError
        link = self._e32_link()
        if link is None:
            return self.async_abort(reason="controller_connection_complete")
        try:
            self._e32_plan = await link.async_read()
        except HomeAssistantError as err:
            return self._e32_abort_failure(err)
        return await self.async_step_e32_room_add()

    @callback
    def async_remove(self):
        task = getattr(self, "_controller_task", None)
        if task is not None and not task.done() and not task.cancelling():
            task.cancel()
        self._controller_task = None
        super().async_remove()
