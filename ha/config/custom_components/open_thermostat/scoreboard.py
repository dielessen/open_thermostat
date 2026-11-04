"""Yesterday's scoreboard (E32 rc.4): is the thermostat getting better at its job?

The E32 keeps score per local day and sends it in ``fw/telemetry/summary`` as ``scoreboard``:
``{"yesterday": {...} | null, "today": {...} | null}``, each day with ``day`` (YYYY-MM-DD),
``heating_h``, ``heating_starts_per_h``, ``short_cycle_h``, ``heating_kwh``, ``degree_days`` and
``rooms``: ``[{"id", "on_time_min", "overshoot_c"}]``. Every number may be null (not measured);
firmware before rc.4 sends no scoreboard at all.

Per room, on the room's device: "Warm on time" (minutes after the program's switch time that the
room was warm; negative: early) and "Overshoot" (how far it got above its target, °C). Per house,
on the product device: burner starts per heating hour, hours of short cycling, gas for heating and
gas per degree-day. Each shows yesterday's figure; state class measurement, so the Recorder keeps
the history of every day. Today's figure so far is an attribute (not recorded: it changes all day).
An entity appears only once the E32 reported a value for it (yesterday or today), so firmware or a
house without a figure never gets an "unknown" entity for good.
"""
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfTime

from .heating_link import HubEntity, RoomEntity, number

DAYS = ("yesterday", "today")
# Room figure: (scoreboard key, lowest and highest plausible value).
ROOM_FIGURES = {"warm_on_time": ("on_time_min", -1440, 1440), "overshoot": ("overshoot_c", -10, 10)}
# House figure: (scoreboard key, lowest and highest plausible value); gas per degree-day is worked out.
HOUSE_FIGURES = {"burner_starts_per_heating_hour": ("heating_starts_per_h", 0, 60),
                 "short_cycling_hours": ("short_cycle_h", 0, 24),
                 "heating_gas_yesterday": ("heating_kwh", 0, 1000),
                 "gas_per_degree_day": None}
# Below one degree-day (a mild day) gas per degree-day says little and jumps: not shown.
MIN_DEGREE_DAYS = 1.0


def scoreboard(summary):
    """The summary's scoreboard, or None on firmware without it."""
    board = summary.get("scoreboard") if type(summary) is dict else None
    return board if type(board) is dict else None


def scoreboard_day(board, which):
    """One day of the scoreboard ("yesterday" or "today"), or None."""
    day = board.get(which) if type(board) is dict else None
    return day if type(day) is dict else None


def day_name(day):
    """The local day a scoreboard day is about (YYYY-MM-DD), or None."""
    value = day.get("day") if type(day) is dict else None
    return value if type(value) is str and len(value) == 10 else None


def room_figure(day, room_id, key):
    """One room's figure of a scoreboard day, or None (not measured, or no such room)."""
    rooms = day.get("rooms") if type(day) is dict else None
    room = next((r for r in rooms if type(r) is dict and r.get("id") == room_id), None) if type(rooms) is list else None
    field, low, high = ROOM_FIGURES[key]
    return number(room.get(field), low, high) if room is not None else None


def house_figure(day, key):
    """One house figure of a scoreboard day, or None (not measured)."""
    if type(day) is not dict:
        return None
    if key == "gas_per_degree_day":
        kwh, degree_days = number(day.get("heating_kwh"), 0, 1000), number(day.get("degree_days"), 0, 100)
        return round(kwh / degree_days, 2) if kwh is not None and degree_days and degree_days >= MIN_DEGREE_DAYS else None
    field, low, high = HOUSE_FIGURES[key]
    return number(day.get(field), low, high)


class _Scoreboard:
    """Mixin: the hub's scoreboard while the E32 reports."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    # Today's figure changes all day: shown, not kept in the history (yesterday's figure is the state).
    _unrecorded_attributes = frozenset({"today"})

    @property
    def board(self):
        return scoreboard(self.hub.summary) if self.hub.fresh else None


class ScoreboardRoomSensor(_Scoreboard, RoomEntity, SensorEntity):
    """Yesterday's "warm on time" or "overshoot" of one room."""

    def __init__(self, hub, room, key):
        self.key = key
        self._attach_room(hub, room, key)
        if key == "overshoot":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE_DELTA
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_suggested_display_precision = 1
        else:  # minutes late; negative: early (plain minutes: a duration cannot be negative)
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_suggested_display_precision = 0

    @property
    def available(self):
        return self.hub.fresh and self.room is not None and self.board is not None

    @property
    def native_value(self):
        return room_figure(scoreboard_day(self.board, "yesterday"), self.room_id, self.key)

    @property
    def extra_state_attributes(self):
        board = self.board
        if board is None:
            return None
        return {"room_id": self.room_id, "day": day_name(scoreboard_day(board, "yesterday")),
                "today": room_figure(scoreboard_day(board, "today"), self.room_id, self.key)}


class ScoreboardHouseSensor(_Scoreboard, HubEntity, SensorEntity):
    """Yesterday's burner starts per heating hour, short cycling, gas for heating or gas per degree-day."""

    def __init__(self, hub, key):
        self.key = key
        self._attach(hub, f"hub_{key}")
        self._attr_translation_key = key
        if key == "short_cycling_hours":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.HOURS
            self._attr_suggested_display_precision = 1
        elif key in ("heating_gas_yesterday", "gas_per_degree_day"):
            # A day's figure, not a meter: no energy device class (the Energy dashboard has the gas meter).
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_suggested_display_precision = 1 if key == "heating_gas_yesterday" else 2
        else:
            self._attr_suggested_display_precision = 1

    @property
    def available(self):
        return self.board is not None

    @property
    def native_value(self):
        return house_figure(scoreboard_day(self.board, "yesterday"), self.key)

    @property
    def extra_state_attributes(self):
        board = self.board
        if board is None:
            return None
        yesterday = scoreboard_day(board, "yesterday")
        result = {"day": day_name(yesterday), "today": house_figure(scoreboard_day(board, "today"), self.key)}
        if self.key == "burner_starts_per_heating_hour":
            result["heating_hours"] = number((yesterday or {}).get("heating_h"), 0, 24)
        elif self.key == "gas_per_degree_day":
            result["heating_kwh"] = house_figure(yesterday, "heating_gas_yesterday")
            result["degree_days"] = number((yesterday or {}).get("degree_days"), 0, 100)
        return result


def wanted_scoreboard(hub):
    """(key, factory) of every scoreboard figure the E32 reported a value for (yesterday or today)."""
    board = scoreboard(hub.summary) if hub.fresh else None
    if board is None:
        return
    days = [scoreboard_day(board, which) for which in DAYS]
    for key in HOUSE_FIGURES:
        if any(house_figure(day, key) is not None for day in days):
            yield ("scoreboard", key), lambda key=key: ScoreboardHouseSensor(hub, key)
    for room_id, room in hub.rooms.items():
        for key in ROOM_FIGURES:
            if any(room_figure(day, room_id, key) is not None for day in days):
                yield ("room", room_id, key), lambda room=room, key=key: ScoreboardRoomSensor(hub, room, key)
