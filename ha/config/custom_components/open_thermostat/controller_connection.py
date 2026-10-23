"""One explicit user operation joins the existing native MQTT owner and Store.

No second worker, MQTT publisher, readiness override or persistent approval is
introduced. The current saved installation must remain exact throughout.
"""
from __future__ import annotations

import asyncio

from .const import DOMAIN
from .controller_link import ControllerLinkError
from .product import configuration_snapshot

CONNECTION_TIMEOUT = 90


def _guard(hass, entry, source, expected, private_expected=None):
    from . import _selected_native_plan_source
    from .native_plan import native_entry_state
    if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or configuration_snapshot(entry) != expected
            or _selected_native_plan_source(entry) != source
            or private_expected is not None and native_entry_state(entry) != private_expected):
        raise ControllerLinkError("setup_changed")
    try:
        source.validate_native(hass, entry)
    except ValueError:
        raise ControllerLinkError("setup_changed") from None


def _connection(hass, entry, source):
    from .v1_mqtt import NativeShadowConnection
    from .v1_wire import ShadowClient
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    runtime, connection = state.get("v1_runtime"), state.get("v1_connection")
    if (runtime is None or not runtime.enabled or runtime.native_plan_source != source
            or not isinstance(connection, NativeShadowConnection) or connection.runtime is not runtime
            or connection.entry is not entry or connection.closed or connection.graph_profile is not None
            or connection.worker is None or connection.worker.done()
            or not isinstance(connection.client, ShadowClient)
            or connection.client.native_plan_source != source):
        return None
    return connection


async def async_wait_controller_connection(hass, entry, source, expected, *, private_expected=None,
                                           previous_connection=None):
    """Wait for the existing entry-update listener's reload, never start another."""
    from homeassistant.config_entries import ConfigEntryState
    changed = asyncio.Event()
    remove = entry.async_on_state_change(changed.set)
    try:
        async with asyncio.timeout(CONNECTION_TIMEOUT):
            while True:
                changed.clear()
                _guard(hass, entry, source, expected, private_expected)
                connection = _connection(hass, entry, source)
                if connection is not None and connection is not previous_connection:
                    return connection
                if entry.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.SETUP_RETRY,
                                    ConfigEntryState.MIGRATION_ERROR):
                    raise ControllerLinkError("controller_connection_failed")
                await changed.wait()
    except TimeoutError:
        raise ControllerLinkError("controller_connection_unconfirmed") from None
    finally:
        remove()


async def async_synchronise_controller_plan(hass, entry, source, expected, *, private_expected=None,
                                            previous_connection=None):
    """Prepare/apply this user's exact saved intent, using the SAME native worker.

    Called only by an authenticated explicit configure/apply action. Approval is
    the worker's volatile current-session review tuple, never an entry flag or
    a restored journal. ACK alone is not completion: actual verified readback
    and a validated current room state are required.
    """
    _guard(hass, entry, source, expected, private_expected)
    connection = await async_wait_controller_connection(hass, entry, source, expected,
        private_expected=private_expected, previous_connection=previous_connection)
    _guard(hass, entry, source, expected, private_expected)
    client, runtime = connection.client, connection.runtime
    changed = asyncio.Event()
    unsubscribe = runtime.add_listener(changed.set)
    remove_state = entry.async_on_state_change(changed.set)

    def guard():
        _guard(hass, entry, source, expected, private_expected)
        if _connection(hass, entry, source) is not connection or connection.client is not client:
            raise ControllerLinkError("controller_connection_changed")

    async def wait(predicate):
        while True:
            changed.clear()
            guard()
            if predicate():
                return
            await changed.wait()

    try:
        async with asyncio.timeout(CONNECTION_TIMEOUT):
            await wait(lambda: client.native_plan_readback_ready)
            guard()
            # A pending ambiguous operation must first be resolved by the
            # existing fresh readback path, never overwritten by this action.
            if client.journal["staged"] is not None:
                raise ControllerLinkError("controller_plan_pending")
            await connection.async_graph_command("prepare")
            guard()
            if client.journal["staged"] is not None:
                # Compiler and final Store awaits already fenced the exact
                # native desired plan. No raw incoming profile/data is adopted.
                reviewed = client.review_candidate()
                await connection.async_graph_command("apply", reviewed)
                guard()
            await wait(lambda: client.current_native_room_state_verified
                       and set(runtime.decisions) == set(runtime.rooms))
            guard()
            accepted = client.journal["accepted"]
            if (accepted is None or client.journal["staged"] is not None
                    or not client.native_desired_matches(accepted["config"])):
                raise ControllerLinkError("controller_plan_unconfirmed")
            return {"controller_id": source.policy.controller_id,
                    "profile_digest": source.policy.profile_digest,
                    "config_digest": accepted["config_digest"],
                    "revision": accepted["config"]["revision"],
                    "room_ids": sorted(runtime.rooms),
                    "mqtt_session_verified": True, "room_plan_applied": True,
                    "qualified_temperature_rooms": sorted(
                        key for key, value in runtime.observations.items() if value.quality == "qualified"),
                    "authorizes_physical_outputs": False}
    except TimeoutError:
        raise ControllerLinkError("controller_plan_unconfirmed") from None
    finally:
        unsubscribe()
        remove_state()
