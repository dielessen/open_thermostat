"""Graphical editor adapter over the existing room program; no scheduler or I/O."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from types import MappingProxyType
import logging

import probatio as vol
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .product import is_product, configuration_snapshot, commit_configuration
from .schedule_compiler import WEEKDAYS, compile_week
from .v1_config_flow import reference
from .v1_heating_graph import actual_runtime_active, validate_room_ownership
from .v1_model import CONF_ENABLED, RoomBinding
from .v1_program import normalize_program, native_week
from .v1_wire import digest

_LOGGER = logging.getLogger(__name__)
_KEY = DOMAIN + "_week_frontend"
URL = "/open_thermostat/week-planner-0.4.0.dev28.js"
ROOM_CARD_TYPE = "custom:openthermostat-room-editor-v28"


def _target(hass, entry_id, room_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if (entry is None or not is_product(entry)
            or entry_id not in hass.data.get(DOMAIN, {})):
        raise ValueError("installation_unavailable")
    rooms = [s for s in entry.subentries.values()
             if s.subentry_type == "zone" and s.data.get("room_id") == room_id]
    if len(rooms) != 1:
        raise ValueError("room_changed")
    return entry, rooms[0], RoomBinding.from_dict(dict(rooms[0].data))


def read_program(hass, entry_id, room_id):
    entry, sub, room = _target(hass, entry_id, room_id)
    return {"entry_id": entry_id, "room_id": room_id, "name": sub.title,
            "token": digest(configuration_snapshot(entry)),
            "week": normalize_program(room.week_program or {}),
            "base_centi_c": room.base_centi_c,
            "minimum_centi_c": room.minimum_target_centi_c,
            "maximum_centi_c": room.maximum_target_centi_c,
            "time_zone": hass.config.time_zone,
            "external_schedule": room.schedule is not None,
            "editable": not (entry.options.get(CONF_ENABLED, False)
                             or actual_runtime_active(hass, entry) or room.schedule),
            "maximum_blocks": 28}


def _save_guard(hass, entry, sub, room, token):
    current, current_sub, _ = _target(hass, entry.entry_id, room.room_id)
    if (current is not entry or current_sub is not sub
            or digest(configuration_snapshot(entry)) != token):
        raise ValueError("setup_changed")
    if entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry):
        raise ValueError("runtime_active")
    if room.schedule is not None:
        raise ValueError("program_source_conflict")
    for ref in (room.temperature, *room.actuators, room.setpoint, room.window, room.presence):
        if ref is not None and reference(hass, ref.entity_id) != ref:
            raise ValueError("binding_missing")
    state = hass.states.get(room.temperature.entity_id)
    if state and state.state not in ("unknown", "unavailable"):
        if state.attributes.get("device_class") != "temperature":
            raise ValueError("not_temperature")
        if state.attributes.get("unit_of_measurement") not in ("°C", "°F"):
            raise ValueError("unsupported_unit")
    validate_room_ownership(hass, entry, room)


async def save_program(hass, entry_id, room_id, token, week):
    entry, sub, room = _target(hass, entry_id, room_id)
    _save_guard(hass, entry, sub, room, token)
    before = configuration_snapshot(entry)
    normalized = normalize_program(week, room.minimum_target_centi_c, room.maximum_target_centi_c)
    start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    await hass.async_add_executor_job(compile_week, native_week(normalized), room.base_centi_c,
        hass.config.time_zone, int(start.timestamp()), int((start + timedelta(days=15)).timestamp()))
    # Compile yields: fence owner, all configuration and current registry again.
    _save_guard(hass, entry, sub, room, token)
    updated = {**deepcopy(dict(sub.data)), "week_program": normalized}
    replacement = type(sub)(data=MappingProxyType(updated), subentry_type=sub.subentry_type,
        title=sub.title, unique_id=sub.unique_id, subentry_id=sub.subentry_id)
    commit_configuration(hass, entry, before,
        subentries={**entry.subentries, sub.subentry_id: replacement})
    return read_program(hass, entry_id, room_id)


@websocket_api.websocket_command({vol.Required("type"): "open_thermostat/week/get",
    vol.Required("entry_id"): str, vol.Required("room_id"): str})
@websocket_api.require_admin
@callback
def ws_get(hass, connection, msg):
    try:
        result = read_program(hass, msg["entry_id"], msg["room_id"])
    except (KeyError, ValueError) as err:
        connection.send_error(msg["id"], str(err), "Week program is unavailable")
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "open_thermostat/week/save",
    vol.Required("entry_id"): str, vol.Required("room_id"): str,
    vol.Required("token"): vol.Match(r"^[a-f0-9]{64}$"), vol.Required("week"): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_save(hass, connection, msg):
    try:
        result = await save_program(hass, msg["entry_id"], msg["room_id"], msg["token"], msg["week"])
    except (KeyError, ValueError) as err:
        connection.send_error(msg["id"], str(err), "Week program was not saved")
    except Exception:
        _LOGGER.exception("Week program save could not be confirmed")
        connection.send_error(msg["id"], "save_uncertain", "Reload the saved program before retrying")
    else:
        connection.send_result(msg["id"], result)


async def async_setup_planner(hass):
    """One static module and authenticated native WS, shared by managed dashboards."""
    if task := hass.data.get(_KEY):
        await task
        return
    # No await before claiming setup; parallel entries await the same owned task.
    async def setup():
        await hass.http.async_register_static_paths([
            StaticPathConfig(URL, str(Path(__file__).parent / "frontend/week-planner.js"), False)])
        from .room_editor import ws_room_get, ws_room_save, ws_room_device_metadata
        websocket_api.async_register_command(hass, ws_room_get)
        websocket_api.async_register_command(hass, ws_room_save)
        websocket_api.async_register_command(hass, ws_room_device_metadata)
        websocket_api.async_register_command(hass, ws_get)
        websocket_api.async_register_command(hass, ws_save)
        frontend.add_extra_js_url(hass, URL)
    task = hass.data[_KEY] = hass.async_create_task(setup(), "OpenThermostat week editor frontend")
    try:
        await task
    except BaseException:
        hass.data.pop(_KEY, None)
        raise
