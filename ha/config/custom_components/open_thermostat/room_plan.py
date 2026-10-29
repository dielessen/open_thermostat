"""Operate the E32 room plan from Home Assistant.

The one room plan lives and runs on the E32 (GET/POST /config/heating over the
stored controller connection). Home Assistant changes one field of one room at
a time: read the plan, change that field, write the whole plan back with the
revision it was read at. When the E32 answers 409 plan_changed (its own page
or another HA call saved in between), the plan is read again once and the same
single change is applied to the new revision; nothing else is overwritten.

Entities (product entries with a stored controller connection, one per room
the E32 telemetry reports): a select (active / inactive), a datetime
(inactive until) and a number (fallback setpoint). Whole rooms are added,
edited and removed by the "E32 rooms" options flow (e32_room_flow.py) through
the same writer.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import logging
import time

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .controller_link import ControllerClient, ControllerLinkError, ControllerLoginRejected, HeatingPlanRejected
from .heating_link import ROOM_ID, RoomEntity, add_options, heating_hub, track_entities

_LOGGER = logging.getLogger(__name__)

ROOM_STATES = ["active", "inactive"]
RETRY_SECONDS = 60
SETPOINT_LIMITS = (5.0, 30.0)
SETPOINT_STEP = 0.5
LATEST_UNTIL = 4102444800  # The E32's own upper bound for inactive_until.


def decode_plan(value):
    """The plan when it is a schema 1 document with a revision and room ids, else None."""
    if (type(value) is not dict or value.get("schema") != 1
            or type(value.get("revision")) is not int or value["revision"] < 0
            or type(value.get("rooms")) is not list):
        return None
    ids = []
    for room in value["rooms"]:
        if type(room) is not dict or type(room.get("id")) is not str or not ROOM_ID.fullmatch(room["id"]):
            return None
        ids.append(room["id"])
    return value if len(ids) == len(set(ids)) else None


def plan_room(plan, room_id):
    for room in plan["rooms"] if plan else []:
        if room["id"] == room_id:
            return room
    return None


def changed_plan(plan, room_id, change):
    """A copy of the plan with change(room) applied to that one room."""
    candidate = deepcopy(plan)
    room = plan_room(candidate, room_id)
    if room is None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_room_missing",
                                 translation_placeholders={"room": room_id})
    change(room)
    return candidate


def set_state(state):
    def change(room):
        room["state"] = state
        room["inactive_until"] = 0
    return change


def set_inactive_until(until):
    def change(room):
        room["state"] = "inactive"
        room["inactive_until"] = until
    return change


def set_fallback(centi_c):
    def change(room):
        low, high = room.get("minimum_centi_c"), room.get("maximum_centi_c")
        if type(low) is int and type(high) is int and not low <= centi_c <= high:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="room_setpoint_outside_limits",
                translation_placeholders={"minimum": f"{low / 100:g}", "maximum": f"{high / 100:g}"})
        room["fallback_centi_c"] = centi_c
    return change


def has_room_plan(entry):
    """A product entry whose E32 room plan HA edits (a stored controller connection).

    Such an entry is set up through the E32 rooms editor; the older HA room
    settings views stay out of its menu and dashboard.
    """
    from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
    from .product import is_product
    return bool(is_product(entry) and entry.data.get(CONTROLLER_ADDRESS) and entry.data.get(CONTROLLER_PASSWORD))


def plan_error(err):
    """A clear Home Assistant error for a refused or failed plan read or write."""
    if isinstance(err, ControllerLoginRejected):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_password")
    if isinstance(err, HeatingPlanRejected):
        if err.error == "plan_changed":
            return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_changed")
        if err.error == "plan_too_large":
            return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_too_large")
        if err.error == "save_unconfirmed":
            return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unconfirmed")
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_rejected",
                                  translation_placeholders={"error": err.error})
    return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unreachable",
                              translation_placeholders={"error": str(err)})


class RoomPlanLink:
    """The last plan read from the E32 and the only path that writes it."""

    def __init__(self, hass, address, password, hub, clock=time.monotonic, entry=None):
        self.hass, self._address, self._password, self.hub, self.clock = hass, address, password, hub, clock
        self.entry = entry
        # The E32 refused this password once: never try it again (its login limit
        # would lock the owner out of the web page); the re-authentication brings a new one.
        self.login_rejected = False
        self.plan = None
        self._lock = asyncio.Lock()
        self._task = None
        self._seen_revision = None
        self._failed_at = None
        self._remove = hub.add_listener(self._status_changed)

    @classmethod
    def for_entry(cls, hass, entry, hub):
        """Only with a stored controller connection (address and admin password)."""
        from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
        address, password = entry.data.get(CONTROLLER_ADDRESS), entry.data.get(CONTROLLER_PASSWORD)
        if not address or not password:
            return None
        return cls(hass, address, password, hub, entry=entry)

    @property
    def revision(self):
        return self.plan["revision"] if self.plan else None

    def room(self, room_id):
        return plan_room(self.plan, room_id)

    def operation(self, room_id):
        """The room's state and inactive_until: the E32's live status, unless our write is newer."""
        status_room = self.hub.rooms.get(room_id)
        room = self.room(room_id)
        status_revision = self.hub.revision
        if room is not None and (status_room is None or (status_revision is not None
                                                        and self.revision > status_revision)):
            return room
        if status_room is not None and room is not None and "inactive_until" not in status_room:
            # Newer firmware leaves inactive_until out of the MQTT rooms: the plan has it.
            return {**status_room, "inactive_until": room.get("inactive_until")}
        return status_room

    @callback
    def _status_changed(self):
        """Read the plan again when the telemetry reports a revision we have not read.

        Each telemetry revision triggers at most one read (an E32 that restored
        an older plan is read once too, not in a loop).
        """
        if self.hub.status is None or (self._task is not None and not self._task.done()):
            return
        revision = self.hub.revision
        if self.plan is not None and (revision is None or revision in (self.revision, self._seen_revision)):
            return
        if self.login_rejected or (self._failed_at is not None and self.clock() - self._failed_at < RETRY_SECONDS):
            return
        self._seen_revision = revision
        self._task = self.hass.async_create_task(self.async_refresh(), "OpenThermostat E32 room plan read")

    def _client(self):
        return ControllerClient(self._address)

    async def _login(self, client):
        from .e32_access import login_rejected, report_password
        if self.login_rejected:
            raise ControllerLoginRejected()
        try:
            await client.async_login(self._password)
        except ControllerLoginRejected:
            self.login_rejected = True
            login_rejected(self.hass, self.entry)
            raise
        report_password(self.hass, self.entry, getattr(client, "default_password", None))

    async def _async_fetch(self):
        async with self._lock:
            async with self._client() as client:
                await self._login(client)
                plan = decode_plan(await client.async_read_heating_plan())
        if plan is None:
            raise ControllerLinkError("controller_response_invalid")
        return plan

    async def async_refresh(self):
        try:
            plan = await self._async_fetch()
        except ControllerLinkError as err:
            _LOGGER.debug("E32 room plan read failed: %s", err)
            self._failed_at, self._seen_revision = self.clock(), None
            return
        self._failed_at = None
        self._set(plan)

    async def async_read(self):
        """The plan as the E32 holds it now; a clear error when it cannot be read."""
        try:
            plan = await self._async_fetch()
        except ControllerLinkError as err:
            if err.args and err.args[0] == "controller_response_invalid":
                raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_invalid") from None
            raise plan_error(err) from None
        self._failed_at = None
        self._set(plan)
        return plan

    @callback
    def _set(self, plan):
        self.plan = plan
        self.hub.notify()

    async def async_change_room(self, room_id, change):
        """GET, change one room field, POST with the read revision; one re-read on 409."""
        return await self.async_change_plan(
            lambda plan: changed_plan(plan, room_id, change),
            lambda stored: plan_room(stored, room_id) is not None)

    async def async_change_plan(self, change, confirm=lambda stored: True):
        """GET, change(plan) returns the new plan, POST with the read revision; one re-read on 409.

        change runs again on the re-read plan, so a concurrent save elsewhere is
        kept and only this edit is applied on top. confirm(stored) checks the
        E32's answer; a stored plan it does not accept is reported unconfirmed.
        """
        async with self._lock:
            try:
                async with self._client() as client:
                    await self._login(client)
                    for attempt in (1, 2):
                        plan = decode_plan(await client.async_read_heating_plan())
                        if plan is None:
                            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_invalid")
                        candidate = change(plan)
                        try:
                            stored = await client.async_save_heating_plan(candidate)
                        except HeatingPlanRejected as err:
                            if err.error == "plan_changed" and attempt == 1:
                                _LOGGER.info("E32 room plan changed since revision %s; applying the change again",
                                             plan["revision"])
                                continue
                            raise
                        break
            except ControllerLinkError as err:
                if isinstance(err, HeatingPlanRejected) and err.error == "save_unconfirmed":
                    self._seen_revision = None  # Read back what the E32 really stored.
                raise plan_error(err) from None
        stored = decode_plan(stored)
        if stored is None or not confirm(stored):
            self._seen_revision = None
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unconfirmed")
        # Telemetry still carries the old revision for a moment; that is not a reason to read.
        self._seen_revision = self.hub.revision
        self._set(stored)
        return stored

    @callback
    def stop(self):
        self._remove()
        if self._task is not None and not self._task.done():
            self._task.cancel()


class PlanRoomEntity(RoomEntity):
    """A room operation entity: needs fresh telemetry and the plan writer."""

    @property
    def plan(self):
        return self.hub.plan

    @property
    def operation(self):
        return self.plan.operation(self.room_id)

    @property
    def available(self):
        return self.hub.fresh and self.operation is not None

    async def _change(self, change):
        await self.plan.async_change_room(self.room_id, change)


class RoomStateSelect(PlanRoomEntity, SelectEntity):
    _attr_options = ROOM_STATES

    def __init__(self, hub, room):
        self._attach_room(hub, room, "state")

    @property
    def current_option(self):
        room = self.operation if self.hub.fresh else None
        state = room.get("state") if room else None
        return state if state in ROOM_STATES else None

    @property
    def extra_state_attributes(self):
        room = self.operation if self.hub.fresh else None
        if not room:
            return None
        until = until_datetime(room)
        return {"room_id": self.room_id, "inactive_until": until.isoformat() if until else None,
                "revision": self.plan.revision}

    async def async_select_option(self, option):
        if option not in ROOM_STATES:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_state_invalid")
        await self._change(set_state(option))


def until_datetime(room):
    until = room.get("inactive_until")
    if room.get("state") != "inactive" or type(until) is not int or not 0 < until <= LATEST_UNTIL:
        return None
    return datetime.fromtimestamp(until, timezone.utc)


class RoomInactiveUntil(PlanRoomEntity, DateTimeEntity):
    """When an inactive room becomes active again (unknown: inactive without end, or active)."""

    def __init__(self, hub, room):
        self._attach_room(hub, room, "inactive_until")

    @property
    def native_value(self):
        room = self.operation if self.hub.fresh else None
        return until_datetime(room) if room else None

    async def async_set_value(self, value):
        until = int(value.timestamp())
        if until <= dt_util.utcnow().timestamp() or until > LATEST_UNTIL:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_inactive_until_past")
        await self._change(set_inactive_until(until))


def setpoint_range(room):
    low, high = SETPOINT_LIMITS
    lo, hi = (room or {}).get("minimum_centi_c"), (room or {}).get("maximum_centi_c")
    if type(lo) is int and type(hi) is int and lo <= hi:
        low, high = max(low, lo / 100), min(high, hi / 100)
    return low, max(low, high)


class RoomFallbackSetpoint(PlanRoomEntity, NumberEntity):
    """The room setpoint the E32 uses without (or when it loses) its setpoint entity."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = SETPOINT_STEP
    _attr_mode = NumberMode.BOX

    def __init__(self, hub, room):
        self._attach_room(hub, room, "fallback_setpoint")

    @property
    def plan_room(self):
        return self.plan.room(self.room_id)

    @property
    def available(self):
        return self.hub.fresh and self.plan_room is not None

    @property
    def native_min_value(self):
        return setpoint_range(self.plan_room)[0]

    @property
    def native_max_value(self):
        return setpoint_range(self.plan_room)[1]

    @property
    def native_value(self):
        room = self.plan_room
        value = room.get("fallback_centi_c") if room else None
        return value / 100 if type(value) is int else None

    @property
    def extra_state_attributes(self):
        room = self.plan_room
        if not room:
            return None
        return {"room_id": self.room_id, "setpoint_entity": room.get("setpoint_entity") or None,
                "revision": self.plan.revision}

    async def async_set_native_value(self, value):
        centi_c = int(round(value / SETPOINT_STEP)) * int(SETPOINT_STEP * 100)
        low, high = setpoint_range(self.plan_room)
        if not low * 100 <= centi_c <= high * 100:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="room_setpoint_outside_limits",
                translation_placeholders={"minimum": f"{low:g}", "maximum": f"{high:g}"})
        await self._change(set_fallback(centi_c))


def _wanted(factory):
    def wanted(hub):
        for room_id, room in hub.rooms.items():
            yield room_id, lambda room=room: factory(hub, room)
    return wanted


async def _async_setup(hass, entry, async_add_entities, factory):
    from .product import is_product
    if not is_product(entry):
        return
    hub = heating_hub(hass, entry)
    if hub.plan is None:
        return  # No stored controller connection: the plan cannot be written.
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), _wanted(factory)))


async def async_setup_selects(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, RoomStateSelect)


async def async_setup_datetimes(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, RoomInactiveUntil)


async def async_setup_numbers(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, RoomFallbackSetpoint)
