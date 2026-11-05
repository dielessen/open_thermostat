"""The daily summary: what the heating did each day, kept for three weeks, for every installation.

Per calendar day (Home Assistant's time zone):

* burner time, burner starts and short runs (a run shorter than SUMMARY_SHORT_RUN_MINUTES),
  counted from the boiler's burner modulation every 10 s, so it works for any boiler the E32
  reads; the E32's own short-cycling flag stays a warning of its own (heating_problem.py);
* gas per post (heating and hot water, and any further posts such as tapping and keeping warm)
  from the day records of ``energy_use`` (gas meter or estimate), read back, never counted twice;
* per room: how long it asked for heat, every "time to target" after its target rose by at least
  SUMMARY_TARGET_STEP_C (minutes until it was within SUMMARY_TARGET_REACHED_C; late after
  SUMMARY_TARGET_ON_TIME_MINUTES, or not reached before the next change), and the missed comfort
  minutes: asking for heat, more than SUMMARY_MISSED_MARGIN_C below the target, for longer than
  SUMMARY_TARGET_ON_TIME_MINUTES;
* the outdoor temperature (lowest, highest, mean) when one is set in the energy options.

Only what was observed counts: without fresh E32 data (``hub.fresh``) the rooms are not followed
and a running measurement starts again afterwards. A day with less than
SUMMARY_COMPLETE_DAY_HOURS observed is marked ``complete: false``.

Entities on the product device: "Daily summary" (state: the last finished day; the days as
attributes) and three running totals with long-term statistics, whose change per day is the daily
figure: burner time (h), burner starts and missed comfort time (min). Nothing here writes a setting.
"""
from __future__ import annotations

import math
import statistics
import time
from datetime import date, datetime, timedelta, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store

from .const import (DOMAIN, SUMMARY_COMPLETE_DAY_HOURS, SUMMARY_DAYS_KEPT, SUMMARY_MISSED_MARGIN_C,
                    SUMMARY_SHORT_RUN_MINUTES, SUMMARY_TARGET_ON_TIME_MINUTES, SUMMARY_TARGET_REACHED_C,
                    SUMMARY_TARGET_STEP_C)

SAMPLE_SECONDS = 10
ROOM_SECONDS = 60
# Two samples further apart than this are not one observation: nothing is counted in between.
MAX_STEP_SECONDS = 60
SAVE_DELAY_SECONDS = 300
WRITE_SECONDS = 60
SHOWN_DAYS = 15
MAX_STEPS_PER_DAY = 24
STORE_VERSION = 1
ROOM_MEASURED = ("ok", "fallback")
# Gas posts read from the energy_use day records, in this order when present.
GAS_POSTS = ("heating", "hot_water", "tapping", "keep_warm")
TOTALS = ("burner_s", "starts", "missed_s")


def _round(value, digits):
    return None if value is None else round(value, digits)


def empty_day():
    return {"observed_s": 0.0, "burner_s": 0.0, "starts": 0, "short_runs": 0, "rooms": {},
            "outdoor": {"min": None, "max": None, "sum": 0.0, "n": 0}}


def empty_room(name):
    return {"name": name, "demand_s": 0.0, "missed_s": 0.0, "steps": [], "late": 0, "not_reached": 0}


def empty_data():
    return {"days": {}, "totals": {key: 0.0 for key in TOTALS}, "created": False}


def valid_data(value):
    """The stored data when it has the expected shape, else None (then counting starts afresh)."""
    if type(value) is not dict or type(value.get("days")) is not dict or type(value.get("totals")) is not dict:
        return None
    totals = value["totals"]
    if any(type(totals.get(key)) not in (int, float) or not math.isfinite(totals[key]) or totals[key] < 0
           for key in TOTALS):
        return None
    days = {}
    for key, day in value["days"].items():
        try:
            date.fromisoformat(key)
        except (TypeError, ValueError):
            continue
        if type(day) is dict and type(day.get("rooms")) is dict and type(day.get("outdoor")) is dict:
            days[key] = day
    return {"days": days, "totals": dict(totals), "created": value.get("created") is True}


class DailySummary:
    """Follows the burner, the rooms and the outdoor temperature; owns the four sensors and their store."""

    def __init__(self, hass, entry, hub, connection, clock=time.time, local_date=None, store=None):
        self.hass, self.entry, self.hub, self.connection, self.clock = hass, entry, hub, connection, clock
        self._local_date = local_date
        self.store = store if store is not None else Store(hass, STORE_VERSION,
                                                           f"{DOMAIN}.daily_summary.{entry.entry_id}")
        self.data = empty_data()
        self.sensors = []
        self._add = None
        self._burner = None      # (time, burning) of the last usable burner sample
        self._run_start = None   # when the current burner run started (seen starting)
        self._observed = None    # time of the last fresh E32 observation
        self._rooms_at = None    # time of the last room pass
        self._room_state = {}    # room id -> {"setpoint", "step": (start, target) or None, "below": since or None}
        self._written = None
        self._dirty = False

    # -- time ----------------------------------------------------------------------------------

    def today(self, now=None):
        now = self.clock() if now is None else now
        if self._local_date is not None:
            return self._local_date(now)
        from homeassistant.util import dt as dt_util
        return dt_util.as_local(datetime.fromtimestamp(now, timezone.utc)).date()

    def day(self, now=None):
        days = self.data["days"]
        key = self.today(now).isoformat()
        if key not in days:
            days[key] = empty_day()
            for old in sorted(days)[:-SUMMARY_DAYS_KEPT]:
                del days[old]
        return days[key]

    # -- counting --------------------------------------------------------------------------------

    def _count_burner(self, now, sample):
        if sample is None:
            self._burner = None  # unknown: nothing counted, and the next run is not a seen start
            self._run_start = None
            return
        burning = sample[0] > 0
        previous = self._burner
        self._burner = (now, burning)
        if previous is None or not 0 < now - previous[0] <= MAX_STEP_SECONDS:
            self._run_start = None
            return
        day = self.day(now)
        if previous[1]:
            step = now - previous[0]
            day["burner_s"] += step
            self.data["totals"]["burner_s"] += step
            self._dirty = True
        if burning and not previous[1]:
            day["starts"] += 1
            self.data["totals"]["starts"] += 1
            self._run_start = now
            self._dirty = True
        elif previous[1] and not burning:
            if self._run_start is not None and now - self._run_start < SUMMARY_SHORT_RUN_MINUTES * 60:
                day["short_runs"] += 1
            self._run_start = None
            self._dirty = True

    def _count_observed(self, now):
        fresh = self.hub is not None and self.hub.fresh
        if fresh and self._observed is not None and 0 < now - self._observed <= MAX_STEP_SECONDS:
            self.day(now)["observed_s"] += now - self._observed
            self._dirty = True
        self._observed = now if fresh else None

    def _follow_rooms(self, now):
        if self._rooms_at is not None and now - self._rooms_at < ROOM_SECONDS:
            return
        previous, self._rooms_at = self._rooms_at, now
        if self.hub is None or not self.hub.fresh:
            self._room_state = {}  # a gap: running measurements start again afterwards
            return
        step = now - previous if previous is not None and 0 < now - previous <= 2 * ROOM_SECONDS else 0.0
        from .heating_link import label, number
        day = self.day(now)
        seen = set()
        for room_id, room in self.hub.rooms.items():
            comfort = room.get("comfort")
            if (room.get("status") not in ROOM_MEASURED
                    or (type(comfort) is dict and comfort.get("window") in ("open", "pending"))):
                self._room_state.pop(room_id, None)
                continue
            temperature, target = number(room.get("temperature"), -40, 85), number(room.get("setpoint"), 5, 30)
            if temperature is None or target is None:
                self._room_state.pop(room_id, None)
                continue
            seen.add(room_id)
            record = day["rooms"].setdefault(room_id, empty_room(label(room)))
            record["name"] = label(room)
            state = self._room_state.setdefault(room_id, {"setpoint": target, "step": None, "below": None})
            demand = room.get("demand") is True
            if demand and step:
                record["demand_s"] += step
                self._dirty = True
            # A new target: a rise starts a "time to target"; a fall ends one that was not reached.
            running = state["step"]
            if target >= state["setpoint"] + SUMMARY_TARGET_STEP_C:
                if running is not None:
                    self._close_step(record, None)
                state["step"] = running = (now, target)
            elif running is not None and target < running[1] - 0.05:
                self._close_step(record, None)
                state["step"] = running = None
            state["setpoint"] = target
            if running is not None and temperature >= running[1] - SUMMARY_TARGET_REACHED_C:
                self._close_step(record, (now - running[0]) / 60)
                state["step"] = None
            # Missed comfort: asking for heat, well below the target, for longer than a warm-up may take.
            if demand and temperature < target - SUMMARY_MISSED_MARGIN_C:
                state["below"] = state["below"] if state["below"] is not None else now
                if step and now - state["below"] > SUMMARY_TARGET_ON_TIME_MINUTES * 60:
                    record["missed_s"] += step
                    self.data["totals"]["missed_s"] += step
                    self._dirty = True
            else:
                state["below"] = None
        for room_id in set(self._room_state) - seen:
            del self._room_state[room_id]

    def _close_step(self, record, minutes):
        if minutes is None:
            record["not_reached"] += 1
        else:
            if len(record["steps"]) < MAX_STEPS_PER_DAY:
                record["steps"].append(round(minutes, 1))
            if minutes > SUMMARY_TARGET_ON_TIME_MINUTES:
                record["late"] += 1
        self._dirty = True

    def _follow_outdoor(self, now):
        from .energy_input import CONF_OUTDOOR, energy_options, outdoor_celsius
        entity_id = energy_options(self.entry).get(CONF_OUTDOOR)
        if not entity_id or self.hass is None:
            return
        value = outdoor_celsius(self.hass.states.get(entity_id))
        if value is None:
            return
        outdoor = self.day(now)["outdoor"]
        outdoor["min"] = value if outdoor["min"] is None else min(outdoor["min"], value)
        outdoor["max"] = value if outdoor["max"] is None else max(outdoor["max"], value)
        outdoor["sum"] += value
        outdoor["n"] += 1
        self._dirty = True

    @callback
    def tick(self, _now=None):
        now = self.clock()
        from .energy_use import boiler_sample
        sample = boiler_sample(getattr(self.connection, "client", None))
        self._count_burner(now, sample)
        self._count_observed(now)
        before = self._rooms_at
        self._follow_rooms(now)
        if self._rooms_at != before:
            self._follow_outdoor(now)
        if sample is not None and not self.data["created"]:
            self.data["created"] = True
            self._dirty = True
            self._create_sensors()
        if self._dirty:
            self._dirty = False
            if self.hass is not None:
                self.store.async_delay_save(lambda: self.data, SAVE_DELAY_SECONDS)
            if self._written is None or now - self._written >= WRITE_SECONDS:
                self._write(now)

    def _write(self, now):
        self._written = now
        for sensor in self.sensors:
            if sensor.added:
                sensor.async_write_ha_state()

    @callback
    def _create_sensors(self):
        if self._add is None or self.sensors:
            return
        self.sensors = [DailySummarySensor(self), *(SummaryTotalSensor(self, key) for key in TOTALS)]
        self._add(self.sensors)

    # -- reading back --------------------------------------------------------------------------

    def _gas(self, key):
        """{post: m³ or kWh} of one day from energy_use (its unit), or {} without it."""
        hass = self.hass
        use = hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {}).get("energy_use") if hass is not None else None
        day = use.data["days"].get(key) if use is not None else None
        if type(day) is not dict:
            return {}
        unit = getattr(use, "unit", "m³")
        suffix = "kwh" if unit == "kWh" else "m3"
        return {post: _round(day[f"{post}_{suffix}"], 3) for post in GAS_POSTS
                if type(day.get(f"{post}_{suffix}")) in (int, float)}

    def summary(self, key):
        """One day as plain figures (what the sensor shows and the dashboard reads)."""
        day = self.data["days"].get(key)
        if day is None:
            return None
        rooms = []
        for room_id, room in sorted(day["rooms"].items()):
            steps = room["steps"]
            rooms.append({"room": room_id, "name": room["name"],
                          "heat_hours": _round(room["demand_s"] / 3600, 1),
                          "missed_minutes": round(room["missed_s"] / 60),
                          "time_to_target_minutes": _round(statistics.median(steps), 0) if steps else None,
                          "targets_reached": len(steps), "late": room["late"], "not_reached": room["not_reached"]})
        outdoor = day["outdoor"]
        return {"date": key, "complete": day["observed_s"] >= SUMMARY_COMPLETE_DAY_HOURS * 3600,
                "observed_hours": _round(day["observed_s"] / 3600, 1),
                "burner_hours": _round(day["burner_s"] / 3600, 1), "burner_starts": day["starts"],
                "short_runs": day["short_runs"], "gas": self._gas(key),
                "missed_comfort_minutes": round(sum(room["missed_s"] for room in day["rooms"].values()) / 60),
                "rooms": rooms,
                "outdoor": ({"min": _round(outdoor["min"], 1), "max": _round(outdoor["max"], 1),
                             "mean": _round(outdoor["sum"] / outdoor["n"], 1)} if outdoor["n"] else None)}

    def finished_days(self, now=None):
        """The finished days, newest first (today is still running)."""
        today = self.today(now).isoformat()
        return [key for key in sorted(self.data["days"], reverse=True) if key < today]

    def diagnostics(self):
        return {"created": self.data["created"],
                "totals": {key: _round(value, 1) for key, value in self.data["totals"].items()},
                "days": {key: self.summary(key) for key in sorted(self.data["days"])}}

    # -- life cycle ----------------------------------------------------------------------------

    async def async_start(self, add_entities):
        self._add = add_entities
        stored = valid_data(await self.store.async_load())
        if stored is not None:
            self.data = stored
        if self.data["created"]:
            self._create_sensors()
        self.entry.async_on_unload(async_track_time_interval(self.hass, self.tick,
                                                             timedelta(seconds=SAMPLE_SECONDS)))
        self.entry.async_on_unload(self.stop)

    def stop(self):
        """Save now; Home Assistant awaits the returned save before the entry is set up again (a reload)."""
        return self.store.async_save(self.data)


class _SummaryEntity(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, summary, key):
        self.summary_owner = summary
        self.added = False
        prefix = summary.hub.prefix
        self._attr_unique_id = f"{prefix}_hub_daily_{key}"
        self._attr_translation_key = f"daily_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.added = True

    async def async_will_remove_from_hass(self):
        self.added = False
        await super().async_will_remove_from_hass()


class DailySummarySensor(_SummaryEntity):
    """The last finished day (its date); that day and the two weeks before it as attributes."""

    # The figures are read from the attributes, not kept in the history.
    _unrecorded_attributes = frozenset({"last_day", "days"})

    def __init__(self, summary):
        super().__init__(summary, "summary")

    @property
    def native_value(self):
        days = self.summary_owner.finished_days()
        return days[0] if days else None

    @property
    def extra_state_attributes(self):
        days = [self.summary_owner.summary(key) for key in self.summary_owner.finished_days()[:SHOWN_DAYS]]
        return {"last_day": days[0] if days else None, "days": days}


class SummaryTotalSensor(RestoreEntity, _SummaryEntity):
    """A running total (total_increasing): its change per day in the statistics is the day's figure.

    Diagnostic: the cards show the day's figure from the statistic; the total itself is a counter."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, summary, key):
        super().__init__(summary, {"burner_s": "burner_time", "starts": "burner_starts",
                                   "missed_s": "missed_comfort"}[key])
        self.key = key
        if key == "burner_s":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.HOURS
            self._attr_suggested_display_precision = 1
        elif key == "missed_s":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_suggested_display_precision = 0
        else:
            self._attr_suggested_display_precision = 0

    @property
    def native_value(self):
        value = self.summary_owner.data["totals"][self.key]
        return {"burner_s": round(value / 3600, 3), "missed_s": round(value / 60, 1)}.get(self.key, int(value))

    async def async_added_to_hass(self):
        """A total never goes down (Home Assistant would count a decrease as a new meter): at least the last state."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        try:
            value = float(last.state) if last is not None else None
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value) and value >= 0:
            stored = value * {"burner_s": 3600, "missed_s": 60}.get(self.key, 1)
            if stored > self.summary_owner.data["totals"][self.key]:
                self.summary_owner.data["totals"][self.key] = stored


async def async_setup_daily_summary(hass, entry, async_add_entities, options, hub, connection):
    """Product entries: the daily summary; its sensors appear once the boiler reports its modulation."""
    summary = DailySummary(hass, entry, hub, connection)
    hass.data[DOMAIN][entry.entry_id]["daily_summary"] = summary
    await summary.async_start(lambda entities: async_add_entities(entities, **options))
    return summary
