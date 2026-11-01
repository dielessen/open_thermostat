"""Takeover readiness: is the E32 ready to take over the boiler from the old thermostat?

The E32 judges the shadow exit criteria itself (``fw/telemetry/readiness``,
src/control/TakeoverReadiness.h; the thresholds of
tools/switchover/shadow_exit.py): stable 72 h, 10 heating periods, timing, the
hard flow limit, cycling and the room sources; in a home without a thermostat
on the bus the stability, the sources, the boiler's reception and its limit.
It keeps its counters over restarts, so only one thing is left for Home
Assistant: what the E32 cannot see of itself. An outage of five minutes or
more in which Home Assistant did not hear the E32 (a hang without a restart, a
lost network) restarts the 72 hours from the moment it was heard again, as
shadow_exit.py counts an offline stretch. The sensor then says "waiting".

One sensor, no repair issue: ready / waiting / not_ready / not_applicable
(the E32 already controls the boiler), with the criteria as attributes.
"""
import time
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity

from .heating_link import HubEntity

READINESS_STATES = ["ready", "waiting", "not_ready", "not_applicable"]
RESULTS = ("pass", "wait", "fail")
STABLE_HOURS = 72
PERIODS_NEEDED = 10
EVENTS_NEEDED = 2 * PERIODS_NEEDED
OUTAGE_SECONDS = 5 * 60  # shadow_exit.py OFFLINE_MINUTES
# Criterion -> {attribute: key in the E32's criterion}.
FIGURES = {
    "stable": {"last_restart": "restart"},
    "periods": {"periods_compared": "thermostat", "night_setbacks": "night_setbacks",
                "morning_warmups": "morning_warmups", "no_demand_periods": "no_demand"},
    "timing": {"timing_events": "events", "timing_matched": "matched", "timing_within_5min": "within_5min",
               "timing_within_15min": "within_15min"},
    "flow": {"flow_max_c": "max_c", "flow_limit_c": "limit_c", "flow_over_limit": "over"},
    "cycling": {"heating_periods_e32": "e32", "heating_periods_thermostat": "thermostat"},
    "sources": {"rooms": "rooms", "rooms_working": "working", "rooms_with_fallback_source": "backup",
                "fallback_seen": "fallback_seen"},
    "boiler": {"boiler_heard_age_s": "age_s"},
    "boiler_limit": {"boiler_limit_c": "limit_c"},
}
NEEDED = {"stable": ("stable_hours_needed", STABLE_HOURS), "periods": ("periods_needed", PERIODS_NEEDED),
          "timing": ("timing_events_needed", EVENTS_NEEDED)}
# The attribute of each criterion's result (the flow criterion is the hard limit).
RESULT_ATTRIBUTE = {"flow": "flow_limit"}


def readiness_status(status):
    """The E32's readiness (``readiness``), or None on firmware without the check."""
    readiness = status.get("readiness") if status else None
    if type(readiness) is not dict or readiness.get("state") not in READINESS_STATES:
        return None
    return readiness


def _value(value):
    return value if type(value) in (int, float, bool, str) or value is None else None


def evaluate(readiness, outage_end=None, now=None):
    """(state, attributes) of the E32's readiness, Home Assistant's outage applied.

    outage_end: unix time Home Assistant heard the E32 again after its last
    outage of OUTAGE_SECONDS or more (None: none seen). The E32's stable time
    is cut to the time since then; the overall state follows all criteria.
    """
    if readiness is None:
        return None, None
    if readiness["state"] == "not_applicable":
        return "not_applicable", None
    now = time.time() if now is None else now
    attributes = {"comparison": readiness.get("comparison") is True}
    results = []
    for key, figures in FIGURES.items():
        item = readiness.get(key)
        if type(item) is not dict or item.get("result") not in RESULTS:
            continue
        result = item["result"]
        if key == "stable":
            seconds = item.get("s") if type(item.get("s")) in (int, float) and item.get("s") >= 0 else 0
            if outage_end is not None:
                seconds = min(seconds, max(0.0, now - outage_end))
            result = "pass" if seconds >= STABLE_HOURS * 3600 else "wait"
            attributes["stable_hours"] = round(seconds / 3600, 1)
            attributes["last_outage_end"] = (datetime.fromtimestamp(outage_end, timezone.utc).isoformat(timespec="minutes")
                                             if outage_end is not None else None)
        attributes[RESULT_ATTRIBUTE.get(key, key)] = result
        if key in NEEDED:
            attributes[NEEDED[key][0]] = NEEDED[key][1]
        for name, field in figures.items():
            attributes[name] = _value(item.get(field))
        results.append(result)
    if not results:
        return None, None
    state = "not_ready" if "fail" in results else "waiting" if "wait" in results else "ready"
    return state, attributes


class TakeoverReadinessSensor(HubEntity, RestoreEntity, SensorEntity):
    """Ready to take over? The E32's shadow exit check, with Home Assistant's own outages.

    Created by heating_link.wanted_sensors once the E32 reports the check
    (firmware 1.0); available while the hub is fresh. The last outage end
    survives a Home Assistant restart as its attribute.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = READINESS_STATES
    _attr_translation_key = "takeover_readiness"

    def __init__(self, hub, wall=time.time):
        self._attach(hub, "hub_takeover_readiness")
        self._wall = wall
        self._outage_end = None
        self._lost_at = None  # wall time of the last sign before the hub went quiet
        self._was_fresh = hub.fresh

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        end = last.attributes.get("last_outage_end") if last is not None else None
        if type(end) is str and self._outage_end is None:
            try:
                self._outage_end = datetime.fromisoformat(end).timestamp()
            except ValueError:
                pass

    @callback
    def track(self):
        """After every hub change: an outage of OUTAGE_SECONDS or more ends when the E32 is heard again."""
        fresh, now = self.hub.fresh, self._wall()
        if not fresh and self._was_fresh and self._lost_at is None:
            seen = self.hub.last_seen
            self._lost_at = now - max(0.0, self.hub.clock() - seen) if seen is not None else now
        elif fresh and self._lost_at is not None:
            if now - self._lost_at >= OUTAGE_SECONDS:
                self._outage_end = now
            self._lost_at = None
        self._was_fresh = fresh

    @callback
    def _hub_changed(self):
        self.track()
        super()._hub_changed()

    @property
    def readiness(self):
        return readiness_status(self.hub.status) if self.hub.fresh else None

    @property
    def available(self):
        return self.readiness is not None

    @property
    def native_value(self):
        return evaluate(self.readiness, self._outage_end, self._wall())[0]

    @property
    def extra_state_attributes(self):
        return evaluate(self.readiness, self._outage_end, self._wall())[1]
