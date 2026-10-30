"""Every E32 room runs its own week program; an optional setting device adjusts it.

Owner, 30 Oct 2026: "per ruimte een weekplanner ... los daarvan kun je de
temperatuur instellen / overrulen met een thermostaatfunctie: een trv, een tado
thermostaat, alleen een virtuele thermostaat, of een losse sensor waarmee je de
temperatuur kunt instellen", and yes: push the program target to the knob.

- The week program lives on the E32 and runs without Home Assistant. A room
  without one gets "Workdays and weekend" (comfort 20 °C, away 18 °C, night
  16 °C, the week planner's defaults) when it is saved in the room editor or
  through the Repairs fix below.
- The room's **setting device** is its plan ``setpoint_entity``: a climate
  entity (a radiator valve such as a TV02, a tado, any thermostat) or a
  number / input_number with a target. Without one, our room thermostat and
  the E32 page are the virtual thermostat.
- Home Assistant writes the E32's current target (the program's, or an
  override or away) to the setting device whenever it differs from what the
  device shows: at each switch point, when the plan changes and when the E32 or
  Home Assistant comes back. Only the device the user chose for the room, only
  while the room is on and not paused for an open window, rounded to the
  device's step, at most once a minute per room.
- A target on the device that we did not write (somebody turned the knob or
  used the device's app) becomes an E32 override "until the next switch point"
  (or the configured time without a week program or clock). Our own write is
  recognised by value (within half the device's step) and for 10 s after it.
- Without Home Assistant the E32 keeps running the program; knob changes are
  not seen then. When it comes back the current target is written again.
- A device that keeps changing its own target at the same times on several
  days runs its own schedule: a Repairs issue asks to switch it to manual.

Nothing here writes to the boiler; the frost floor, flow limits and the guard
are the E32's and unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import logging
import math
import time

from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .heating_link import celsius, number

_LOGGER = logging.getLogger(__name__)

DEVICE_DOMAINS = ("climate", "number", "input_number")
MIN_INTERVAL = 60       # s between two writes to one device
ECHO_SECONDS = 10       # our own write settles
PENDING_SECONDS = 60    # a knob change waits this long for the E32 to report it as its target
SCHEDULE_DAYS = 3       # unasked changes at the same quarter on this many days: its own schedule
SCHEDULE_WINDOW_DAYS = 8
ROOM_PROGRAMS_ISSUE = "room_programs"
OWN_SCHEDULE_ISSUE = "device_own_schedule"

# The week planner's "Workdays and weekend" (week-editor.js TEMPLATES.work, levels comfort/away/night).
COMFORT, AWAY, NIGHT = 2000, 1800, 1600
WORKDAY = [(390, COMFORT), (510, AWAY), (1020, COMFORT), (1350, NIGHT)]
WEEKEND = [(480, COMFORT), (1380, NIGHT)]


def default_program(low=500, high=3000):
    """The template as a plan "schedule" (7 days of [minute, centi_c]) within the room's limits."""
    clamp = lambda v: max(low, min(high, v))  # noqa: E731
    return [[[m, clamp(c)] for m, c in (WORKDAY if day < 5 else WEEKEND)] for day in range(7)]


def has_program(room):
    schedule = (room or {}).get("schedule")
    return (type(schedule) is list and any(day for day in schedule)) or bool((room or {}).get("week"))


def setting_device(room):
    entity_id = (room or {}).get("setpoint_entity")
    return entity_id if type(entity_id) is str and entity_id.split(".")[0] in DEVICE_DOMAINS else None


def proposed_device(room):
    """A climate source of the room (its valve or thermostat) as the setting device, when it has none."""
    if setting_device(room):
        return None
    for source in (room or {}).get("sources") or []:
        if source.get("type") == "ha" and str(source.get("id", "")).startswith("climate."):
            return source["id"]
    return None


def setting_hint(device, language):
    """The room form's hint for a climate source that could be the setting device ("" without one).

    Only a hint: the form never pre-selects it, the user picks it (Home Assistant
    then writes the device's target at every switch point)."""
    if not device:
        return ""
    if str(language or "").startswith("nl"):
        return (f"\n\n**Instelapparaat?** {device} gebruiken als instelapparaat van deze ruimte? Home Assistant "
                "zet dan bij elk schakelpunt van het weekprogramma de gewenste temperatuur erop. "
                "Kies het daarvoor zelf bij Instelapparaat.")
    if str(language or "").startswith("pl"):
        return (f"\n\n**Urządzenie nastawcze?** Użyć {device} jako urządzenia nastawczego tego pomieszczenia? "
                "Home Assistant ustawi wtedy jego temperaturę zadaną w każdym punkcie przełączenia programu "
                "tygodniowego. Aby tak było, wybierz je w polu Urządzenie nastawcze.")
    return (f"\n\n**Setting device?** Use {device} as this room's setting device? Home Assistant will then set "
            "its target temperature at every switch point of the week program. To do so, choose it under "
            "Setting device.")


def _unit(hass, state):
    if state.domain == "climate":
        return hass.config.units.temperature_unit
    return state.attributes.get("unit_of_measurement") or UnitOfTemperature.CELSIUS


def device_target(hass, state):
    """The device's target in °C, or None."""
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    value = state.attributes.get("temperature") if state.domain == "climate" else state.state
    return celsius(value, _unit(hass, state), 5, 35)


def device_step(state):
    """The device's step in °C (close enough for °F devices too)."""
    key = "target_temp_step" if state.domain == "climate" else "step"
    step = number(state.attributes.get(key), 0.01, 5)
    return step if step is not None else 0.5


async def async_write(hass, state, value_c, context=None):
    """Set the device's target (its own service), rounded to its step and in its unit."""
    unit, step = _unit(hass, state), device_step(state)
    value = value_c
    if unit not in (UnitOfTemperature.CELSIUS, None, ""):
        from homeassistant.util.unit_conversion import TemperatureConverter
        value = TemperatureConverter.convert(value_c, UnitOfTemperature.CELSIUS, unit)
    value = round(round(value / step) * step, 2)
    low, high = number(state.attributes.get("min_temp" if state.domain == "climate" else "min"), -100, 1000), \
        number(state.attributes.get("max_temp" if state.domain == "climate" else "max"), -100, 1000)
    if low is not None:
        value = max(value, low)
    if high is not None:
        value = min(value, high)
    if state.domain == "climate":
        service, data = "set_temperature", {"entity_id": state.entity_id, "temperature": value}
    else:
        service, data = "set_value", {"entity_id": state.entity_id, "value": value}
    await hass.services.async_call(state.domain, service, data, blocking=True, context=context)
    return value


class SettingDevicePusher:
    """One per entry: writes the E32 targets to the setting devices and turns knob changes into overrides."""

    def __init__(self, hass, entry, hub, clock=time.monotonic, now=dt_util.now):
        self.hass, self.entry, self.hub, self.clock, self.now = hass, entry, hub, clock, now
        self.pushed = {}       # room id -> (entity, °C, clock)
        self.pending = {}      # room id -> (°C, clock until)
        self.unasked = {}      # entity -> [(date, quarter)] of changes we did not write
        self._tracked, self._unsubscribe, self._retry = (), None, None
        self._busy = set()

    # -- the rooms -------------------------------------------------------------------
    def rooms(self):
        """(room id, plan room, status room, device entity) for each room with a program and a setting device."""
        link = self.hub.plan
        plan = link.plan if link is not None else None
        for room in (plan or {}).get("rooms", []):
            device = setting_device(room)
            if device and has_program(room):
                yield room["id"], room, self.hub.rooms.get(room["id"]), device

    @staticmethod
    def desired(status_room):
        """The E32's target to show on the device, or None (off, window pause, program not running)."""
        if not status_room or status_room.get("state") != "active":
            return None
        comfort = status_room.get("comfort") if type(status_room.get("comfort")) is dict else {}
        if comfort.get("mode") == "window_open" or status_room.get("setpoint_source") != "schedule":
            return None
        return number(status_room.get("setpoint"), 5, 35)

    # -- pushing ---------------------------------------------------------------------
    @callback
    def evaluate(self, _now=None):
        self._retry = None
        if not self.hub.fresh:
            return
        self._follow_devices()
        update_room_programs_issue(self.hass, self.entry, self.hub)
        self._clear_own_schedule_issues()
        wait = None
        for room_id, _room, status, device in self.rooms():
            want, state = self.desired(status), self.hass.states.get(device)
            if want is None or state is None or room_id in self._busy:
                continue
            pending = self.pending.get(room_id)
            if pending is not None:
                if abs(pending[0] - want) < 0.05 or self.clock() > pending[1]:
                    self.pending.pop(room_id, None)
                else:
                    continue  # the knob's value is on its way to the E32
            shown = device_target(self.hass, state)
            if shown is not None and abs(shown - want) <= device_step(state) / 2 + 0.01:
                continue
            last = self.pushed.get(room_id)
            if last is not None and self.clock() - last[2] < MIN_INTERVAL:
                wait = min(wait or MIN_INTERVAL, MIN_INTERVAL - (self.clock() - last[2]))
                continue
            self._busy.add(room_id)
            self.hass.async_create_task(self._push(room_id, state, want), f"OpenThermostat setting device {device}")
        if wait is not None and self._retry is None:
            self._retry = async_call_later(self.hass, wait + 1, self.evaluate)

    async def _push(self, room_id, state, want):
        try:
            value = await async_write(self.hass, state, want)
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Could not set %s to the program target of E32 room %s: %s", state.entity_id, room_id, err)
            value = None
        finally:
            self._busy.discard(room_id)
        # Rate-limited also after a failure: never a write storm.
        self.pushed[room_id] = (state.entity_id, want, self.clock())
        if value is not None:
            _LOGGER.debug("E32 room %s: set %s to %s", room_id, state.entity_id, value)

    # -- the knob --------------------------------------------------------------------
    @callback
    def _follow_devices(self):
        devices = tuple(sorted({device for *_rest, device in self.rooms()}))
        if devices == self._tracked:
            return
        self.stop_tracking()
        self._tracked = devices
        if devices:
            self._unsubscribe = async_track_state_change_event(self.hass, list(devices), self.device_changed)

    @callback
    def device_changed(self, event):
        if not self.hub.fresh:
            return
        entity_id, state = event.data["entity_id"], event.data.get("new_state")
        value = device_target(self.hass, state)
        old = device_target(self.hass, event.data.get("old_state"))
        if value is None or (old is not None and abs(old - value) < 0.01):
            return  # no new target (another attribute changed)
        for room_id, room, status, device in self.rooms():
            if device != entity_id or status is None or status.get("state") != "active":
                continue
            tolerance = device_step(state) / 2 + 0.01
            last = self.pushed.get(room_id)
            if last is not None and last[0] == entity_id and (abs(last[1] - value) <= tolerance
                                                              or self.clock() - last[2] < ECHO_SECONDS):
                return  # our own write
            current = number(status.get("setpoint"), 5, 35)
            if current is not None and abs(current - value) <= tolerance:
                return
            self.pending[room_id] = (value, self.clock() + PENDING_SECONDS)
            self._note_unasked(room_id, room, entity_id, state)
            self.hass.async_create_task(self._override(room_id, room, value), f"OpenThermostat knob {entity_id}")
            return

    async def _override(self, room_id, room, value):
        """The knob's target until the next switch point (else the configured time)."""
        from .e32_comfort import async_comfort_command, comfort_options, override_command
        from homeassistant.exceptions import ServiceValidationError
        value = round(value * 2) / 2
        try:
            try:
                await async_comfort_command(self.hub.plan, override_command(room_id, "next", value))
            except ServiceValidationError as err:
                if err.translation_key not in ("comfort_no_clock", "comfort_no_schedule"):
                    raise
                minutes = comfort_options(self.entry)["override_minutes"]
                await async_comfort_command(self.hub.plan, override_command(room_id, "timed", value, minutes))
        except HomeAssistantError as err:
            self.pending.pop(room_id, None)
            _LOGGER.warning("E32 room %s: could not take over %s °C from its setting device: %s", room_id, value, err)

    # -- the device's own schedule ------------------------------------------------------
    def _recent_unasked(self, entity_id):
        now = self.now()
        return [(d, q) for d, q in self.unasked.get(entity_id, []) if (now.date() - d).days < SCHEDULE_WINDOW_DAYS]

    def _own_schedule(self, entity_id):
        """Unasked changes at about the same quarter on SCHEDULE_DAYS days within the window."""
        seen = self._recent_unasked(entity_id)
        return any(len({d for d, other in seen if abs(other - q) <= 1}) >= SCHEDULE_DAYS for _, q in seen)

    @callback
    def _clear_own_schedule_issues(self):
        """The "own schedule" item goes once the condition is gone: the device stopped changing by
        itself for SCHEDULE_WINDOW_DAYS, it is no longer the room's setting device, or the room is gone."""
        head = f"{OWN_SCHEDULE_ISSUE}_{self.entry.entry_id}_"
        devices = {room_id: device for room_id, _room, _status, device in self.rooms()}
        for domain, issue in list(ir.async_get(self.hass).issues):
            if domain != DOMAIN or not issue.startswith(head):
                continue
            device = devices.get(issue.removeprefix(head))
            if device is None or not self._own_schedule(device):
                ir.async_delete_issue(self.hass, DOMAIN, issue)

    def _note_unasked(self, room_id, room, entity_id, state):
        now = self.now()
        quarter = (now.hour * 60 + now.minute) // 15
        seen = self._recent_unasked(entity_id)
        seen.append((now.date(), quarter))
        self.unasked[entity_id] = seen[-64:]
        days = {d for d, q in seen if abs(q - quarter) <= 1}
        if len(days) >= SCHEDULE_DAYS:
            name = state.name if state is not None else entity_id
            ir.async_create_issue(self.hass, DOMAIN, f"{OWN_SCHEDULE_ISSUE}_{self.entry.entry_id}_{room_id}",
                                  is_fixable=False, is_persistent=False, severity=ir.IssueSeverity.WARNING,
                                  translation_key=OWN_SCHEDULE_ISSUE,
                                  translation_placeholders={"device": name, "room": room.get("name") or room_id})

    # -- lifecycle -------------------------------------------------------------------------
    @callback
    def stop_tracking(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._tracked = ()

    @callback
    def start(self):
        remove = self.hub.add_listener(self.evaluate)
        self.evaluate()

        @callback
        def stop():
            remove()
            self.stop_tracking()
            if self._retry is not None:
                self._retry()
                self._retry = None
        return stop


# -- migration: a program (and the proposed setting device) for each room ------------------


def room_program_changes(plan):
    """[(room id, room name, adds program, proposed device or None)] for rooms that need one."""
    changes = []
    for room in (plan or {}).get("rooms", []):
        program, device = not has_program(room), proposed_device(room)
        if program or device:
            changes.append((room["id"], room.get("name") or room["id"], program, device))
    return changes


def issue_id(entry):
    return f"{ROOM_PROGRAMS_ISSUE}_{entry.entry_id}"


@callback
def update_room_programs_issue(hass, entry, hub):
    """A Repairs fix while a room has no week program, or a valve/thermostat source that is not its setting device."""
    link = hub.plan
    if link is None or link.plan is None:
        return
    changes = room_program_changes(link.plan)
    if not changes:
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry))
        return
    ir.async_create_issue(hass, DOMAIN, issue_id(entry), is_fixable=True, is_persistent=False,
                          severity=ir.IssueSeverity.WARNING, translation_key=ROOM_PROGRAMS_ISSUE,
                          translation_placeholders={"rooms": ", ".join(name for _, name, *_ in changes)},
                          data={"entry_id": entry.entry_id})


def apply_room_program_changes(plan, room_ids=None):
    """The plan with the template program and the proposed setting device for these rooms."""
    candidate = deepcopy(plan)
    for room in candidate["rooms"]:
        if room_ids is not None and room["id"] not in room_ids:
            continue
        if not has_program(room):
            room["schedule"] = default_program(room.get("minimum_centi_c", 500), room.get("maximum_centi_c", 3000))
        if device := proposed_device(room):
            room["setpoint_entity"] = device
    return candidate


def describe_changes(changes, language):
    nl = str(language or "").startswith("nl")
    lines = []
    for _, name, program, device in changes:
        parts = []
        if program:
            parts.append("weekprogramma Werkdagen en weekend (20 °C)" if nl else "week program Workdays and weekend (20 °C)")
        if device:
            parts.append(("instelapparaat " if nl else "setting device ") + device)
        lines.append(f"- {name}: " + ", ".join(parts))
    return "\n".join(lines)


try:
    from homeassistant.components.repairs import RepairsFlow
except ImportError:  # pragma: no cover
    RepairsFlow = object


class RoomProgramsRepairFlow(RepairsFlow):
    """One confirmation: the template program and the proposed setting device for the listed rooms."""

    def __init__(self, issue, data):
        self._issue, self._data = issue, data

    async def async_step_init(self, user_input=None):
        return await self.async_step_room_programs(user_input)

    async def async_step_room_programs(self, user_input=None):
        entry = self.hass.config_entries.async_get_entry(self._data.get("entry_id"))
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub") if entry else None
        if hub is None or hub.plan is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        if user_input is None:
            plan = await hub.plan.async_read()
            changes = room_program_changes(plan)
            if not changes:
                ir.async_delete_issue(self.hass, DOMAIN, self._issue)
                return self.async_abort(reason="room_programs_done")
            self._ids = {room_id for room_id, *_ in changes}
            return self.async_show_form(step_id="room_programs", description_placeholders={
                "changes": describe_changes(changes, self.hass.config.language)})
        await hub.plan.async_change_plan(lambda plan: apply_room_program_changes(plan, self._ids))
        ir.async_delete_issue(self.hass, DOMAIN, self._issue)
        return self.async_create_entry(data={})
