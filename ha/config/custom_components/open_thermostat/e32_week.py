"""The visual week planner for E32 rooms (dashboard card openthermostat-e32-week).

Reads the E32 room plan and writes one room's week program through the same
RoomPlanLink as the "E32 rooms" options flow: the whole plan with the revision
it was read at, one re-read on 409. The program is the plan's own semantic
form (7 days Mon..Sun of [minute, centi °C], a point holds until the next
one); the E32 packs it for storage itself. A save only replaces the room's
"schedule" when it still equals the program the planner loaded, so a change
made meanwhile on the E32 page or in the options flow is never overwritten.
"""
from __future__ import annotations

from copy import deepcopy

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .heating_link import heating_hub
from .room_plan import has_room_plan, plan_room

MAX_POINTS = 6
CARD_URL = "/open_thermostat/e32-week-card-0.4.0b13.js"
EDITOR_URL = "/open_thermostat/week-editor-0.4.0b13.js"
# RoomPlanLink failures -> the short codes the card explains in plain words.
FAILURES = {"room_plan_changed": "plan_changed", "room_plan_too_large": "plan_too_large",
            "room_plan_storage_full": "storage_full", "room_plan_unconfirmed": "save_unconfirmed",
            "room_plan_room_missing": "room_missing", "room_plan_password": "password_changed",
            "room_plan_rejected": "rejected", "room_plan_invalid": "unreachable", "room_plan_unreachable": "unreachable",
            # The E32's web sign-ins (room_plan.SIGN_IN_ERRORS): busy for a while, the card retries.
            "e32_session_capacity": "session_capacity", "e32_try_again_later": "try_again_later"}


class WeekError(Exception):
    """A planner error code (sent to the card as the websocket error code)."""


def valid_schedule(schedule, low, high):
    """The 7-day program as the E32 accepts it (RoomSchedule::parse), or None for no program."""
    if schedule is None:
        return None
    if type(schedule) is not list or len(schedule) != 7:
        raise WeekError("invalid_schedule")
    week = []
    for day in schedule:
        if type(day) is not list or len(day) > MAX_POINTS:
            raise WeekError("invalid_schedule")
        points = []
        for point in day:
            if (type(point) is not list or len(point) != 2 or any(type(v) is not int for v in point)
                    or not 0 <= point[0] <= 1439 or (points and point[0] <= points[-1][0])):
                raise WeekError("invalid_schedule")
            if not low <= point[1] <= high:
                raise WeekError("invalid_schedule_limits")
            points.append([point[0], point[1]])
        week.append(points)
    return week if any(week) else None


def _program(room):
    schedule = room.get("schedule")
    return deepcopy(schedule) if type(schedule) is list and any(schedule) else None


def _link(hass, entry_id):
    """The entry's RoomPlanLink, or WeekError: unavailable (no such E32 installation),
    disabled (turned off by the user), setup_error (the installation could not start: a clear
    message, no retry) or not_ready (still starting: the card waits and retries)."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not has_room_plan(entry):
        raise WeekError("unavailable")
    if entry.disabled_by is not None:
        raise WeekError("disabled")
    if entry.state in (ConfigEntryState.SETUP_ERROR, ConfigEntryState.MIGRATION_ERROR):
        raise WeekError("setup_error")
    if entry_id not in hass.data.get(DOMAIN, {}):
        raise WeekError("not_ready")
    link = heating_hub(hass, entry).plan
    if link is None:
        raise WeekError("not_ready")
    return link


def _code(err):
    return FAILURES.get(getattr(err, "translation_key", None), "rejected")


def week_rooms(plan):
    """What the card shows: per room its name, limits, fallback and program."""
    return {"revision": plan["revision"], "rooms": [{
        "id": room["id"], "name": room.get("name") or room["id"],
        "minimum_centi_c": room.get("minimum_centi_c", 500), "maximum_centi_c": room.get("maximum_centi_c", 3000),
        "fallback_centi_c": room.get("fallback_centi_c", 2000), "setpoint_entity": room.get("setpoint_entity") or "",
        "schedule": _program(room)} for room in plan["rooms"]]}


def _current(link):
    """The plan HA already read, while the E32 reports exactly its revision and is heard (so it is current):
    no sign-in on the E32 for every opened card. None: read it from the E32."""
    plan, hub = link.plan, link.hub
    if plan is None or link.revision is None or link.revision != hub.revision or not hub.alive:
        return None
    return plan


async def read_week(hass, entry_id, fresh=False):
    """The week programs; the plan HA holds while it is current, else (and with ``fresh``) read from the E32.

    A save always reads the E32's plan again and only replaces a program that still equals the one shown."""
    link = _link(hass, entry_id)
    if not fresh and (plan := _current(link)) is not None:
        return week_rooms(plan)
    try:
        return week_rooms(await link.async_read())
    except HomeAssistantError as err:
        raise WeekError(_code(err)) from None


async def save_week(hass, entry_id, room_id, schedule, expected):
    """Replace one room's program; WeekError("week_changed") when it changed since it was loaded."""
    link = _link(hass, entry_id)
    wanted = []

    def change(plan):
        candidate = deepcopy(plan)
        room = plan_room(candidate, room_id)
        if room is None:
            raise WeekError("room_missing")
        if _program(room) != expected:
            raise WeekError("week_changed")
        week = valid_schedule(schedule, room.get("minimum_centi_c", 500), room.get("maximum_centi_c", 3000))
        if week is None:
            room.pop("schedule", None)  # no program: the room keeps its fallback temperature
        else:
            room["schedule"] = week
        wanted[:] = [week]
        return candidate

    def confirm(stored):
        room = plan_room(stored, room_id)
        return room is not None and _program(room) == wanted[0]
    try:
        stored = await link.async_change_plan(change, confirm)
    except HomeAssistantError as err:
        raise WeekError(_code(err)) from None
    return week_rooms(stored)


@websocket_api.websocket_command({vol.Required("type"): "open_thermostat/e32_week/get",
                                  vol.Required("entry_id"): str, vol.Optional("fresh", default=False): bool})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_week_get(hass, connection, msg):
    try:
        result = await read_week(hass, msg["entry_id"], msg.get("fresh", False))
    except WeekError as err:
        connection.send_error(msg["id"], str(err), "The week programs could not be read")
    else:
        # The module this backend serves: a page still running an older card asks for a reload.
        connection.send_result(msg["id"], {**result, "card_url": CARD_URL})


@websocket_api.websocket_command({vol.Required("type"): "open_thermostat/e32_week/save",
                                  vol.Required("entry_id"): str, vol.Required("room_id"): str,
                                  vol.Required("schedule"): vol.Any(None, list),
                                  vol.Required("expected"): vol.Any(None, list)})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_week_save(hass, connection, msg):
    try:
        result = await save_week(hass, msg["entry_id"], msg["room_id"], msg["schedule"], msg["expected"])
    except WeekError as err:
        connection.send_error(msg["id"], str(err), "The week program was not saved")
    else:
        connection.send_result(msg["id"], result)
