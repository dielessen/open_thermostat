"""E32 rooms: the Home Assistant editor of the E32 room plan.

The rooms live in the E32 room plan (GET/POST /config/heating) and keep
running on the E32 without Home Assistant. This options flow step lists them
and adds, edits or removes one room at a time through RoomPlanLink: the whole
plan with the revision it was read at; on 409 the plan is read again and the
same edit applied once. An edit changes only the fields the form changed, so a
concurrent change on the E32's own page to another field or room survives.

Each source records who reads it: "ha" (a Home Assistant climate or °C
temperature sensor that HA forwards to the E32) or "ble" (a Bluetooth sensor
paired on the E32, read by the E32 itself).
"""
from __future__ import annotations

from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
import re

import probatio as vol
from homeassistant.const import UnitOfTemperature
from homeassistant.data_entry_flow import section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import CONF_TOPIC_PREFIX, DOMAIN
from .heating_link import TEMPERATURE_UNITS, celsius, heating_hub, label, number
from .native_form import retained_input_schema
from .room_plan import has_room_plan, plan_room

MAX_ROOMS = 8
MAX_SOURCES = 4
MAX_POINTS = 6
NAME_BYTES = 40
ROOM_ID_LENGTH = 32
LIMITS_CENTI_C = (500, 3000)
ENTITY_ID = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")
SOURCE_DOMAINS = ("climate", "sensor")
SETPOINT_DOMAINS = ("climate", "input_number", "number")
CELSIUS = UnitOfTemperature.CELSIUS
# The plan's flow limits as the E32 accepts them (RoomPlan.h): whole °C, minimum below maximum.
# Up to 80 °C for radiator homes; firmware before that refuses more than 60 °C
# (invalid_flow_limits, shown as e32_rejected_flow_limits).
FLOW_MINIMUM_C = (20, 59)
FLOW_MAXIMUM_C = (21, 80)
# Floor heating without a mixing valve: a higher maximum earns a warning first.
FLOOR_FLOW_WARNING_C = 50
FAHRENHEIT = UnitOfTemperature.FAHRENHEIT
# Plan error names of the E32 (RoomPlan.h) -> a clear message instead of the code.
REJECTIONS = {"invalid_sources": "e32_rejected_sources", "invalid_room_name": "e32_name_invalid",
              "duplicate_room": "e32_rejected_duplicate_room", "duplicate_source": "e32_rejected_duplicate_source",
              "invalid_setpoint_entity": "e32_rejected_setpoint", "invalid_room_limits": "e32_limits_invalid",
              "invalid_flow_limits": "e32_rejected_flow_limits", "invalid_schedule": "e32_rejected_schedule",
              "invalid_schedule_limits": "e32_rejected_schedule"}
# The one sentence about the boiler's own maximum in the flow-limits form.
BOILER_MAXIMUM_TEXT = {
    "en": "Your boiler allows at most {maximum}; the E32 never asks for more. A lower limit here is useful "
          "for floor heating.",
    "nl": "Je ketel staat hoogstens {maximum} toe; de E32 vraagt nooit meer. Een lagere grens hier is nuttig "
          "bij vloerverwarming."}
FLOW_LIMIT_FIELDS = {"minimum_flow_temperature": "minimum_flow_c", "maximum_flow_temperature": "maximum_flow_c"}

DAYS = {"en": ("mon", "tue", "wed", "thu", "fri", "sat", "sun"),
        "nl": ("ma", "di", "wo", "do", "vr", "za", "zo")}
DAY_NAMES = {name: index for names in (
    *DAYS.values(),
    ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"),
    ("maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"),
) for index, name in enumerate(names)}
POINT = re.compile(r"(\d{1,2})[:.](\d{2})\s+(\d{1,2}(?:[.,]\d{1,2})?)")
DAY_PREFIX = re.compile(r"([a-z][a-z ,\-]*?)\s*:\s*(.*)")

# HA error translation keys of RoomPlanLink -> this flow's error/abort keys.
FAILURES = {"room_plan_changed": "e32_plan_changed", "room_plan_too_large": "e32_plan_too_large",
            "room_plan_rejected": "e32_rejected", "room_plan_unconfirmed": "e32_unconfirmed",
            "room_plan_unreachable": "e32_unreachable", "room_plan_invalid": "e32_plan_invalid",
            "room_plan_room_missing": "e32_room_missing", "room_plan_password": "e32_password_changed"}
ABORTS = {"e32_unconfirmed", "e32_plan_invalid", "e32_room_missing", "e32_password_changed"}


class FlowError(Exception):
    """A form error key (and the field it belongs to)."""

    def __init__(self, key, field="base", **placeholders):
        super().__init__(key)
        self.key, self.field, self.placeholders = key, field, placeholders


def unique_room_id(name, taken):
    """A room id from the name ([a-z0-9_], at most 32), unique in the plan."""
    base = re.sub(r"[^a-z0-9_]", "", slugify(name, separator="_"))[:ROOM_ID_LENGTH].strip("_")
    if not base or base == "unknown" and "unknown" not in name.lower():  # slugify's empty result
        base = "room"
    candidate, count = base, 1
    while candidate in taken:
        count += 1
        suffix = f"_{count}"
        candidate = base[:ROOM_ID_LENGTH - len(suffix)] + suffix
    return candidate


def valid_name(value):
    name = (value or "").strip()
    if not name or len(name.encode()) > NAME_BYTES or any(ord(c) < 32 for c in name):
        raise FlowError("e32_name_invalid", "name")
    return name


def centi(value, unit=CELSIUS):
    """A temperature in the user's unit (°C or °F) as the plan's centi-°C (°F: to 0.1 °C)."""
    try:
        number = Decimal(str(value).replace(",", "."))
        if not number.is_finite():
            raise InvalidOperation
        if unit == FAHRENHEIT:
            return int(((number - 32) * 50 / 9).to_integral_value(ROUND_HALF_UP)) * 10
        return int((number * 100).to_integral_value(ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        raise FlowError("e32_program_invalid", "program") from None


def shown(centi_c, unit=CELSIUS):
    """The plan's centi-°C in the user's unit (°F with one decimal)."""
    if unit == FAHRENHEIT:
        return float((Decimal(centi_c) * 9 / 500 + 32).quantize(Decimal("0.1"), ROUND_HALF_UP))
    return centi_c / 100


def flow_shown(celsius_value, unit=CELSIUS):
    """A whole-°C flow temperature in the user's unit (whole °F)."""
    return round(celsius_value * 9 / 5 + 32) if unit == FAHRENHEIT else celsius_value


def flow_celsius(value, unit=CELSIUS):
    """A whole flow temperature in the user's unit as whole °C (None when not whole)."""
    if not float(value).is_integer():
        return None
    return round((value - 32) * 5 / 9) if unit == FAHRENHEIT else int(value)


def _days(text):
    days = []
    for token in (t.strip() for t in text.split(",")):
        ends = [part.strip() for part in token.split("-")]
        if len(ends) > 2 or any(end not in DAY_NAMES for end in ends):
            raise FlowError("e32_program_invalid", "program")
        first, last = DAY_NAMES[ends[0]], DAY_NAMES[ends[-1]]
        days += [(first + step) % 7 for step in range((last - first) % 7 + 1)]
    return days


def parse_program(text, minimum, maximum, unit=CELSIUS):
    """The 7-day schedule from the program text, or None for no program.

    One line per group of days: "mon-fri: 06:30 20.5; 22:30 18" (Dutch
    "ma-vr: 06:30 20,5; 22:30 18"; a comma between points works too); a line
    without days applies to every day. Days not named have no switch point
    (the previous point holds, as on the E32). Temperatures are in the user's
    unit (°C or °F). An error names the line it could not read.
    """
    week = [None] * 7
    for number, original in enumerate((text or "").splitlines(), 1):
        try:
            _parse_line(original, week, minimum, maximum, unit)
        except FlowError as err:
            err.placeholders.setdefault("line", str(number))
            err.placeholders.setdefault("text", original.strip()[:60])
            raise
    if all(day is None for day in week):
        return None
    return [day or [] for day in week]


def _parse_line(original, week, minimum, maximum, unit):
    """One program line into week (days -> points); raises FlowError."""
    line = original.lower().replace("–", "-").strip()
    if not line:
        return
    prefix = DAY_PREFIX.fullmatch(line)
    days, body = (_days(prefix[1]), prefix[2]) if prefix else (range(7), line)
    points, position = {}, 0
    for match in POINT.finditer(body):
        if body[position:match.start()].strip(" ,;\t"):
            raise FlowError("e32_program_invalid", "program")
        position = match.end()
        hour, minute = int(match[1]), int(match[2])
        if hour > 23 or minute > 59 or hour * 60 + minute in points:
            raise FlowError("e32_program_invalid", "program")
        value = centi(match[3], unit)
        if not minimum <= value <= maximum:
            raise FlowError("e32_program_outside_limits", "program")
        points[hour * 60 + minute] = value
    if not points or body[position:].strip(" ,;\t"):
        raise FlowError("e32_program_invalid", "program")
    if len(points) > MAX_POINTS:
        raise FlowError("e32_program_too_many", "program")
    for day in days:
        if week[day] is not None:
            raise FlowError("e32_program_invalid", "program")
        week[day] = [[minute, points[minute]] for minute in sorted(points)]


def _day_ranges(days, names):
    runs = []
    for day in days:
        if runs and runs[-1][1] == day - 1:
            runs[-1][1] = day
        else:
            runs.append([day, day])
    return ",".join(names[a] if a == b else f"{names[a]}-{names[b]}" for a, b in runs)


def format_program(schedule, language="en", unit=CELSIUS):
    """The program text for a stored schedule (identical days grouped; Dutch with decimal commas)."""
    if type(schedule) is not list or len(schedule) != 7 or not any(schedule):
        return ""
    dutch = language == "nl"
    names = DAYS["nl" if dutch else "en"]
    groups = {}

    def degrees(c):
        text = f"{shown(c, unit):g}"
        return text.replace(".", ",") if dutch else text
    for day, points in enumerate(schedule):
        if points:
            key = "; ".join(f"{m // 60:02d}:{m % 60:02d} {degrees(c)}" for m, c in points)
            groups.setdefault(key, []).append(day)
    return "\n".join(key if len(days) == 7 else f"{_day_ranges(days, names)}: {key}"
                     for key, days in groups.items())


def source_problem(hass, entity_id, setpoint=False):
    """An error key when the E32 cannot use this HA entity as a source (or setpoint), else None."""
    if len(entity_id) > 80 or not ENTITY_ID.fullmatch(entity_id):
        return "e32_source_invalid_id"
    domain = entity_id.split(".", 1)[0]
    if domain not in (SETPOINT_DOMAINS if setpoint else SOURCE_DOMAINS):
        return "e32_source_wrong_domain"
    state = hass.states.get(entity_id)
    if state is None:
        return "e32_source_not_found"
    if domain == "climate":
        # Climate attributes are in the HA unit system (°C or °F); they are
        # converted to °C before they are forwarded to the E32.
        if not setpoint and celsius(state.attributes.get("current_temperature"),
                                    hass.config.units.temperature_unit, -40, 85) is None:
            return "e32_source_no_temperature"
        return None
    unit = state.attributes.get("unit_of_measurement")
    # °F and K sources are converted to °C on the way to the E32; other units are refused.
    if domain == "sensor" and unit not in TEMPERATURE_UNITS or domain != "sensor" and unit not in (None, "", *TEMPERATURE_UNITS):
        return "e32_source_not_celsius"
    return None


class E32RoomFlow:
    """Options flow steps for the E32 room plan (mixed into ProductOptionsFlow)."""

    def _e32_link(self):
        entry = self.config_entry
        if not has_room_plan(entry) or entry.entry_id not in self.hass.data.get(DOMAIN, {}):
            return None
        return heating_hub(self.hass, entry).plan

    def _e32_failure(self, err):
        key = FAILURES.get(getattr(err, "translation_key", None), "e32_rejected")
        placeholders = dict(getattr(err, "translation_placeholders", None) or {})
        placeholders.setdefault("error", getattr(err, "translation_key", None) or "unknown")
        if key == "e32_rejected":
            key = REJECTIONS.get(placeholders["error"], key)
        return key, placeholders

    def _unit(self):
        """The Home Assistant temperature unit (°C or °F); the E32 plan itself is always °C."""
        unit = getattr(getattr(getattr(self.hass, "config", None), "units", None), "temperature_unit", CELSIUS)
        return FAHRENHEIT if unit == FAHRENHEIT else CELSIUS

    def _e32_abort_failure(self, err):
        key, placeholders = self._e32_failure(err)
        if key not in ABORTS | {"e32_unreachable"}:
            key = "e32_unreachable"
        return self.async_abort(reason=key, description_placeholders=placeholders)

    async def async_step_e32_rooms(self, user_input=None, done=None, name=None):
        """The room list and what to do next; done ("saved"/"removed") says what just happened."""
        link = self._e32_link()
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        if done is not None and link.plan is not None:
            plan = link.plan  # just stored and confirmed by the E32
        else:
            try:
                plan = await link.async_read()
            except HomeAssistantError as err:
                return self._e32_abort_failure(err)
        self._e32_plan = plan
        options = (["e32_room_add"] if len(plan["rooms"]) < MAX_ROOMS else []) + (
            ["e32_room_pick"] if plan["rooms"] else []) + ["e32_flow_limits"]
        placeholders = {"rooms": self._e32_room_list(plan), "revision": str(plan["revision"])}
        if done is not None:
            placeholders["name"] = name or ""
        return self.async_show_menu(step_id="e32_rooms" if done is None else f"e32_rooms_{done}",
                                    menu_options=options, description_placeholders=placeholders)

    def _e32_source_label(self, source):
        if source.get("type") == "ble":
            sensor = heating_hub(self.hass, self.config_entry).ble.get(source.get("id"))
            name = label(sensor) if sensor else source.get("id")
            return f"Bluetooth {name}" if name == source.get("id") else f"Bluetooth {name} ({source.get('id')})"
        return str(source.get("id"))

    def _e32_room_list(self, plan):
        dutch = self.hass.config.language == "nl"
        lines = []
        for room in plan["rooms"]:
            inactive = "" if room.get("state") == "active" else (" (inactief)" if dutch else " (inactive)")
            sources = ", ".join(self._e32_source_label(s) for s in room.get("sources", []))
            lines.append(f"- {room.get('name', room['id'])}{inactive}: {sources}")
        return "\n".join(lines) or ("Nog geen ruimtes." if dutch else "No rooms yet.")

    async def async_step_e32_room_add(self, user_input=None):
        self._e32_room_id = None
        return await self.async_step_e32_room()

    async def async_step_e32_room_pick(self, user_input=None):
        rooms = self._e32_plan["rooms"]
        if user_input is not None:
            if user_input.get("room") not in {r["id"] for r in rooms}:
                return self.async_abort(reason="e32_room_missing", description_placeholders={
                    "room": str(user_input.get("room"))})
            self._e32_room_id = user_input["room"]
            if user_input.get("action") == "remove":
                return await self.async_step_e32_room_remove()
            return await self.async_step_e32_room()
        return self.async_show_form(step_id="e32_room_pick", data_schema=vol.Schema({
            vol.Required("room", default=rooms[0]["id"]): selector.SelectSelector({"options": [
                {"value": r["id"], "label": r.get("name", r["id"])} for r in rooms]}),
            vol.Required("action", default="edit"): selector.SelectSelector({
                "options": ["edit", "remove"], "translation_key": "e32_room_action"}),
        }))

    def _boiler_maximum(self):
        """The boiler's own maximum heating temperature (°C) when it reports one, else None.

        On some boilers a knob (read-only, the boiler reports its position), on
        others a menu setting; it is the real ceiling either way.
        """
        state = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {})
        client = getattr(state.get("v1_connection"), "client", None)
        if client is None:
            return None
        from .heating_advice import boiler_maximum
        return boiler_maximum(client)

    async def async_step_e32_flow_limits(self, user_input=None):
        """The plan's minimum/maximum flow temperature (whole °C, 20–59 / 21–80, minimum below maximum).

        Shown and entered in the Home Assistant unit. A maximum above 50 °C with
        floor heating, or above the boiler's own maximum, is saved only after a
        second confirming save (a warning, not a block: the boiler caps anyway).
        """
        plan = self._e32_plan
        unit = self._unit()
        current = {key: plan.get(key) for key in FLOW_LIMIT_FIELDS.values()}
        boiler = self._boiler_maximum()
        errors, placeholders = {}, {"error": "", "boiler": "", **self._flow_ranges(unit)}
        if boiler is not None:
            from .heating_advice import language
            placeholders["boiler"] = BOILER_MAXIMUM_TEXT[language(self.hass)].format(
                maximum=f"{flow_shown(boiler, unit):g} {unit}")
        if user_input is not None:
            try:
                values = [float(user_input[field]) for field in FLOW_LIMIT_FIELDS]
                low, high = (flow_celsius(v, unit) for v in values)
            except (KeyError, TypeError, ValueError):
                low = high = None
            if low is None or high is None or not (FLOW_MINIMUM_C[0] <= low <= FLOW_MINIMUM_C[1]
                                                   and FLOW_MAXIMUM_C[0] <= high <= FLOW_MAXIMUM_C[1]):
                errors["base"] = "e32_flow_limits_invalid"
            elif low >= high:
                errors["base"] = "e32_flow_limits_order"
            elif current == {"minimum_flow_c": low, "maximum_flow_c": high}:
                return self.async_abort(reason="e32_room_unchanged")
            else:
                warnings = {}
                if high > FLOOR_FLOW_WARNING_C and any(
                        room.get("emitter") == "floor" for room in plan.get("rooms", [])):
                    warnings["maximum_flow_temperature"] = "e32_flow_limits_floor_warning"
                if boiler is not None and high > boiler:
                    warnings["base"] = "e32_flow_limits_above_boiler"
                if warnings and getattr(self, "_e32_flow_warned", None) != (low, high):
                    self._e32_flow_warned = (low, high)  # the same values once more: save
                    errors.update(warnings)
                else:
                    return await self._e32_save_flow_limits(low, high, errors, placeholders)
        return self._e32_flow_form(current, unit, user_input, errors, placeholders)

    @staticmethod
    def _flow_ranges(unit):
        def span(bounds):
            return f"{flow_shown(bounds[0], unit)}–{flow_shown(bounds[1], unit)} {unit}"
        return {"minimum_range": span(FLOW_MINIMUM_C), "maximum_range": span(FLOW_MAXIMUM_C),
                "floor_maximum": f"{flow_shown(FLOOR_FLOW_WARNING_C, unit)} {unit}"}

    async def _e32_save_flow_limits(self, low, high, errors, placeholders):
        def change(stored):
            candidate = deepcopy(stored)
            candidate["minimum_flow_c"], candidate["maximum_flow_c"] = low, high
            return candidate
        link = self._e32_link()
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        try:
            await link.async_change_plan(change, lambda stored: (
                stored.get("minimum_flow_c"), stored.get("maximum_flow_c")) == (low, high))
        except HomeAssistantError as err:
            key, extra = self._e32_failure(err)
            if key in ABORTS:
                return self.async_abort(reason=key, description_placeholders={"room": "", **extra})
            errors["base"] = key
            placeholders.update(extra)
            return self._e32_flow_form({"minimum_flow_c": low, "maximum_flow_c": high}, self._unit(),
                                       None, errors, placeholders)
        unit = self._unit()
        return self.async_abort(reason="e32_flow_limits_saved", description_placeholders={
            "minimum": f"{flow_shown(low, unit)}", "maximum": f"{flow_shown(high, unit)}", "unit": unit})

    def _e32_flow_form(self, current, unit, user_input, errors, placeholders):
        default = {"minimum_flow_temperature": current["minimum_flow_c"], "maximum_flow_temperature":
                   current["maximum_flow_c"]}
        for field, fallback in (("minimum_flow_temperature", 30), ("maximum_flow_temperature", 60)):
            if type(default[field]) not in (int, float) or type(default[field]) is bool:
                default[field] = fallback
        fields = {}
        for field, (low, high) in (("minimum_flow_temperature", FLOW_MINIMUM_C),
                                   ("maximum_flow_temperature", FLOW_MAXIMUM_C)):
            fields[vol.Required(field, default=flow_shown(default[field], unit))] = selector.NumberSelector({
                "min": flow_shown(low, unit), "max": flow_shown(high, unit), "step": 1, "mode": "box",
                "unit_of_measurement": unit})
        return self.async_show_form(step_id="e32_flow_limits", data_schema=retained_input_schema(
            self, vol.Schema(fields), user_input), errors=errors, description_placeholders=placeholders)

    async def async_step_e32_room_remove(self, user_input=None):
        room_id = self._e32_room_id
        room = plan_room(self._e32_plan, room_id)
        if room is None:
            return self.async_abort(reason="e32_room_missing", description_placeholders={"room": room_id})
        errors, placeholders = {}, {"name": room.get("name", room_id), "error": ""}
        if user_input is not None:
            if not user_input.get("confirm_remove", False):
                return self.async_abort(reason="cancelled")

            def change(plan):
                if plan_room(plan, room_id) is None:
                    raise FlowError("e32_room_missing")
                candidate = deepcopy(plan)
                candidate["rooms"] = [r for r in candidate["rooms"] if r["id"] != room_id]
                return candidate
            link = self._e32_link()
            if link is None:
                return self.async_abort(reason="e32_rooms_unavailable")
            try:
                await link.async_change_plan(change, lambda stored: plan_room(stored, room_id) is None)
            except FlowError:
                return await self.async_step_e32_rooms(done="removed", name=placeholders["name"])
            except HomeAssistantError as err:
                key, extra = self._e32_failure(err)
                if key in ABORTS:
                    return self.async_abort(reason=key, description_placeholders={**placeholders, **extra})
                errors["base"] = key
                placeholders.update(extra)
            else:
                return await self.async_step_e32_rooms(done="removed", name=placeholders["name"])
        return self.async_show_form(step_id="e32_room_remove", data_schema=vol.Schema({
            vol.Required("confirm_remove", default=False): bool}),
            errors=errors, description_placeholders=placeholders)

    def _e32_own_entities(self):
        """This entry's E32 entities (room and Bluetooth values): never an HA source.

        The E32 already has them; its Bluetooth sensors are chosen as such.
        """
        prefix = self.config_entry.data.get(CONF_TOPIC_PREFIX, "") + "_e32_"
        return [item.entity_id for item in er.async_entries_for_config_entry(
            er.async_get(self.hass), self.config_entry.entry_id) if item.unique_id.startswith(prefix)]

    def _e32_ble_options(self, room):
        sensors = heating_hub(self.hass, self.config_entry).ble
        options = []
        for sensor_id, sensor in sensors.items():
            text = label(sensor)
            text = sensor_id if text == sensor_id else f"{text} ({sensor_id})"
            temperature = number(sensor.get("temperature"), -40, 85)
            options.append({"value": sensor_id, "label": text if temperature is None else f"{text} {temperature:g} °C"})
        for source in (room or {}).get("sources", []):
            if source.get("type") == "ble" and source.get("id") not in sensors:
                options.append({"value": source["id"], "label": source["id"]})
        return options

    def _e32_defaults(self, room):
        room = room or {}
        sources = room.get("sources", [])
        unit = self._unit()
        return {
            "name": room.get("name", ""), "state": room.get("state", "active"),
            "emitter": room.get("emitter", "radiator"),
            "ha_sources": [s["id"] for s in sources if s.get("type") == "ha"],
            "ble_sources": [s["id"] for s in sources if s.get("type") == "ble"],
            "bluetooth_first": bool(sources) and sources[0].get("type") == "ble",
            "setpoint_entity": room.get("setpoint_entity") or None,
            "fallback_temperature": shown(room.get("fallback_centi_c", 2000), unit),
            "minimum_temperature": shown(room.get("minimum_centi_c", 500), unit),
            "maximum_temperature": shown(room.get("maximum_centi_c", 2500), unit),
            "program": format_program(room.get("schedule"), self.hass.config.language, unit),
        }

    def _e32_centi(self, value, field, defaults, room):
        """A submitted temperature as centi-°C; the value as shown keeps the stored one exactly."""
        stored = room.get({"fallback_temperature": "fallback_centi_c", "minimum_temperature": "minimum_centi_c",
                           "maximum_temperature": "maximum_centi_c"}[field])
        try:
            same = type(stored) is int and float(value) == float(defaults[field])
        except (TypeError, ValueError):
            same = False
        return stored if same else centi(value, self._unit())

    def _e32_room_values(self, user_input, room, ble_options):
        """The submitted room as plan fields; raises FlowError for the first problem."""
        room = room or {}
        defaults = self._e32_defaults(room)
        name = valid_name(user_input.get("name"))
        state, emitter = user_input.get("state"), user_input.get("emitter")
        if state not in ("active", "inactive") or emitter not in ("floor", "radiator"):
            raise FlowError("e32_rejected", error="invalid_room")
        known = {(s.get("type"), s.get("id")) for s in room.get("sources", [])}
        ha, ble = [], []
        for entity_id in user_input.get("ha_sources") or []:
            if entity_id not in ha:
                if ("ha", entity_id) not in known and (problem := source_problem(self.hass, entity_id)):
                    raise FlowError(problem, "ha_sources", source=entity_id)
                ha.append(entity_id)
        offered = {option["value"] for option in ble_options}
        for sensor_id in user_input.get("ble_sources") or []:
            if sensor_id not in offered and sensor_id not in ble:
                raise FlowError("e32_rejected", "ble_sources", error="invalid_sources")
            if sensor_id not in ble:
                ble.append(sensor_id)
        if not 1 <= len(ha) + len(ble) <= MAX_SOURCES:
            raise FlowError("e32_sources_count")
        first = user_input.get("bluetooth_first", defaults["bluetooth_first"])
        if (ha, ble, first) == (defaults["ha_sources"], defaults["ble_sources"], defaults["bluetooth_first"]):
            sources = deepcopy(room.get("sources", []))  # untouched: keep the stored order exactly
        else:
            ha_sources = [{"type": "ha", "id": e} for e in ha]
            ble_sources = [{"type": "ble", "id": b} for b in ble]
            sources = ble_sources + ha_sources if first else ha_sources + ble_sources
        setpoint = user_input.get("setpoint_entity") or ""
        if setpoint and setpoint != room.get("setpoint_entity") and (
                problem := source_problem(self.hass, setpoint, setpoint=True)):
            raise FlowError(problem, "setpoint_entity", source=setpoint)
        limits = user_input.get("limits") or {}
        try:
            low = self._e32_centi(limits.get("minimum_temperature", defaults["minimum_temperature"]),
                                  "minimum_temperature", defaults, room)
            high = self._e32_centi(limits.get("maximum_temperature", defaults["maximum_temperature"]),
                                   "maximum_temperature", defaults, room)
            fallback = self._e32_centi(user_input.get("fallback_temperature", defaults["fallback_temperature"]),
                                       "fallback_temperature", defaults, room)
        except FlowError:
            raise FlowError("e32_limits_invalid", "fallback_temperature", **self._limit_range()) from None
        if not LIMITS_CENTI_C[0] <= low <= high <= LIMITS_CENTI_C[1] or not low <= fallback <= high:
            raise FlowError("e32_limits_invalid", "fallback_temperature", **self._limit_range())
        text = user_input.get("program") or ""
        stored = room.get("schedule")
        if stored and text.strip() == defaults["program"].strip() and all(
                low <= point[1] <= high for day in stored for point in day):
            schedule = deepcopy(stored)  # the program as shown: kept exactly (no °F rounding)
        else:
            schedule = parse_program(text, low, high, self._unit())
        return {"name": name, "state": state, "emitter": emitter, "sources": sources,
                "setpoint_entity": setpoint, "fallback_centi_c": fallback,
                "minimum_centi_c": low, "maximum_centi_c": high, "schedule": schedule}

    def _limit_range(self):
        unit = self._unit()
        low, high = LIMITS_CENTI_C
        return {"range": f"{shown(low, unit):g}–{shown(high, unit):g} {unit}"}

    async def async_step_e32_room(self, user_input=None):
        room_id = getattr(self, "_e32_room_id", None)
        room = plan_room(self._e32_plan, room_id) if room_id else None
        if room_id and room is None:
            return self.async_abort(reason="e32_room_missing", description_placeholders={"room": room_id})
        ble_options = self._e32_ble_options(room)
        errors = {}
        placeholders = {"source": "", "error": "", "line": "", "text": "", **self._limit_range()}
        link = self._e32_link()
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        if user_input is not None:
            try:
                values = self._e32_room_values(user_input, room, ble_options)
                if room is not None:
                    edits = {k: v for k, v in values.items() if room.get(k) != v}
                    if not edits:
                        return self.async_abort(reason="e32_room_unchanged")
                    change, confirm = self._e32_edit(room_id, edits)
                else:
                    change, confirm = self._e32_add(values)
                await link.async_change_plan(change, confirm)
            except FlowError as err:
                if err.key in ABORTS:
                    return self.async_abort(reason=err.key, description_placeholders={"room": room_id or ""})
                errors[err.field] = err.key
                placeholders.update(err.placeholders)
            except HomeAssistantError as err:
                key, extra = self._e32_failure(err)
                if key in ABORTS:
                    return self.async_abort(reason=key, description_placeholders={"room": room_id or "", **extra})
                errors["base"] = key
                placeholders.update(extra)
            else:
                return await self.async_step_e32_rooms(done="saved", name=values["name"])
        return self.async_show_form(step_id="e32_room", data_schema=retained_input_schema(
            self, self._e32_room_schema(room, ble_options), user_input),
            errors=errors, description_placeholders=placeholders)

    def _e32_room_schema(self, room, ble_options):
        d = self._e32_defaults(room)
        own = self._e32_own_entities()
        unit = self._unit()
        low, high = (shown(limit, unit) for limit in LIMITS_CENTI_C)
        temperature = selector.NumberSelector({"min": low, "max": high, "step": 0.5 if unit == CELSIUS else 0.1,
                                               "mode": "box", "unit_of_measurement": unit})
        sources = {"filter": [{"domain": "climate"}, {"domain": "sensor", "device_class": "temperature"}],
                   "multiple": True, "reorder": True}
        if own:
            sources["exclude_entities"] = own
        fields = {
            vol.Required("name", default=d["name"]): str,
            vol.Required("state", default=d["state"]): selector.SelectSelector({
                "options": ["active", "inactive"], "translation_key": "e32_room_state"}),
            vol.Required("emitter", default=d["emitter"]): selector.SelectSelector({
                "options": ["radiator", "floor"], "translation_key": "e32_room_emitter"}),
            vol.Optional("ha_sources", description={"suggested_value": d["ha_sources"]}):
                selector.EntitySelector(sources),
        }
        if ble_options:
            fields[vol.Optional("ble_sources", description={"suggested_value": d["ble_sources"]})] = \
                selector.SelectSelector({"options": ble_options, "multiple": True})
            fields[vol.Optional("bluetooth_first", default=d["bluetooth_first"])] = bool
        fields.update({
            vol.Optional("setpoint_entity", description={"suggested_value": d["setpoint_entity"]}):
                selector.EntitySelector({"filter": [{"domain": domain} for domain in SETPOINT_DOMAINS]}),
            vol.Required("fallback_temperature", default=d["fallback_temperature"]): temperature,
            vol.Optional("program", description={"suggested_value": d["program"] or None}):
                selector.TextSelector({"multiline": True}),
            vol.Optional("limits"): section(vol.Schema({
                vol.Required("minimum_temperature", default=d["minimum_temperature"]): temperature,
                vol.Required("maximum_temperature", default=d["maximum_temperature"]): temperature,
            }), {"collapsed": True}),
        })
        return vol.Schema(fields)

    @staticmethod
    def _e32_edit(room_id, edits):
        def change(plan):
            candidate = deepcopy(plan)
            room = plan_room(candidate, room_id)
            if room is None:
                raise FlowError("e32_room_missing")
            for key, value in edits.items():
                if value is None:
                    room.pop(key, None)  # schedule cleared: fallback only
                else:
                    room[key] = deepcopy(value)
            if "state" in edits:
                room["inactive_until"] = 0
            return candidate
        return change, lambda stored: plan_room(stored, room_id) is not None

    @staticmethod
    def _e32_add(values):
        created = []

        def change(plan):
            candidate = deepcopy(plan)
            if len(candidate["rooms"]) >= MAX_ROOMS:
                raise FlowError("e32_room_limit")
            room_id = unique_room_id(values["name"], {r["id"] for r in candidate["rooms"]})
            room = {"id": room_id, "name": values["name"], "state": values["state"], "inactive_until": 0,
                    **{k: deepcopy(v) for k, v in values.items()
                       if k not in ("name", "state") and v is not None}}
            candidate["rooms"].append(room)
            created[:] = [room_id]
            return candidate
        return change, lambda stored: bool(created) and plan_room(stored, created[0]) is not None
