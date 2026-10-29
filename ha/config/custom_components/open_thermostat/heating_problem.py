"""The "Heating problem" sensor: one calm yes/no for "is my heating OK?", on the product device.

A binary sensor (device class problem) that is on only for real problems,
each held long enough that a short hiccup never raises it:

* a room has had no usable temperature measurement for more than 30 minutes
  (the E32 reports it as ``stale`` and then ``lost``; an inactive room never counts);
* the E32 has not reported for more than 10 minutes (only once Home Assistant
  has heard from it, or when the E32 connection is stored);
* the heating advice reports a low or high water pressure (that advice already
  waits 30 / 60 minutes);
* the E32 has seen the burner short cycling for more than 2 hours without a break;
* in active mode (the E32 controls the boiler): a warning of the E32's active
  control for more than 5 minutes.

Attributes: ``problems`` (stable ids, for automations) and ``reasons`` (the
same in plain English or Dutch, following the Home Assistant language), so a
user's own notification automation can say what is wrong.
"""
from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN

ROOM_LOST_SECONDS = 30 * 60
TELEMETRY_STALE_SECONDS = 10 * 60
SHORT_CYCLING_SECONDS = 2 * 3600
ACTIVE_WARNING_SECONDS = 5 * 60
CHECK_INTERVAL = timedelta(seconds=60)
ROOM_WITHOUT_MEASUREMENT = ("stale", "lost")
# Active-control warnings that mean the heating does not work as it should.
# (boiler_limit_unknown only says the E32 still waits for the boiler's maximum.)
ACTIVE_WARNINGS = ("foreign_controller", "measurement_lost", "boiler_no_response", "transmit_failed")

TEXT = {
    "en": {
        "room_without_measurement": "{room}: no temperature measurement for more than 30 minutes, so this room "
                                    "does not ask for heat. Check the sensor's battery and distance.",
        "e32_offline": "The E32 has not reported for more than 10 minutes. Check its power and Wi-Fi.",
        "pressure_low": "The water pressure is low ({pressure} bar). Top up the heating system.",
        "pressure_high": "The water pressure is high ({pressure} bar). Have the expansion vessel checked.",
        "short_cycling": "The boiler has been switching on and off too often for more than 2 hours.",
        "active_foreign_controller": "Another thermostat still sends heat requests to the boiler.",
        "active_measurement_lost": "The E32 lost the room measurements and stopped asking for heat.",
        "active_boiler_no_response": "The boiler does not respond to the E32's heat request.",
        "active_transmit_failed": "The E32 cannot send its heat request to the boiler.",
    },
    "nl": {
        "room_without_measurement": "{room}: al meer dan 30 minuten geen temperatuurmeting, dus deze ruimte "
                                    "vraagt geen warmte. Controleer de batterij en de afstand van de sensor.",
        "e32_offline": "De E32 meldt zich al meer dan 10 minuten niet. Controleer de stroom en de wifi.",
        "pressure_low": "De waterdruk is laag ({pressure} bar). Vul de cv-installatie bij.",
        "pressure_high": "De waterdruk is hoog ({pressure} bar). Laat het expansievat controleren.",
        "short_cycling": "De ketel slaat al meer dan 2 uur te vaak aan en uit.",
        "active_foreign_controller": "Een andere thermostaat stuurt nog warmtevragen naar de ketel.",
        "active_measurement_lost": "De E32 heeft geen ruimtemetingen meer en vraagt geen warmte meer.",
        "active_boiler_no_response": "De ketel reageert niet op de warmtevraag van de E32.",
        "active_transmit_failed": "De E32 kan zijn warmtevraag niet naar de ketel sturen.",
    },
}


def _active(status):
    active = status.get("active") if status else None
    return active if type(active) is dict else None


class ProblemTracker:
    """Since when each condition holds (monotonic seconds); pure, so it is easy to test."""

    def __init__(self, now, expect_telemetry=False):
        self.started = now
        self.expect_telemetry = expect_telemetry
        self.rooms = {}          # room id -> since without a measurement
        self.short_cycling = None
        self.active = {}         # warning -> since

    def observe(self, hub, now):
        """Follow the hub's latest status (call on every hub change and periodically)."""
        if not hub.fresh:
            return  # an outage is its own reason; keep the room timers as they were
        status = hub.status
        rooms = {}
        for room_id, room in hub.rooms.items():
            if room.get("status") in ROOM_WITHOUT_MEASUREMENT:
                rooms[room_id] = self.rooms.get(room_id, now)
        self.rooms = rooms
        burner = status.get("burner") if type(status.get("burner")) is dict else {}
        flag = burner.get("short_cycling")
        if flag is True:
            self.short_cycling = self.short_cycling if self.short_cycling is not None else now
        elif flag is False:
            self.short_cycling = None
        active = _active(status)
        warnings = active.get("warnings") if active and status.get("mode") == "active" else None
        current = [w for w in warnings if w in ACTIVE_WARNINGS] if type(warnings) is list else []
        self.active = {w: self.active.get(w, now) for w in current}

    def problems(self, hub, now, advice_items=()):
        """[(id, placeholders)] of the current problems, most important first."""
        result = []
        last = getattr(hub, "last_seen", None)
        if last is not None or self.expect_telemetry:
            since = last if last is not None else self.started
            if not hub.fresh and now - since > TELEMETRY_STALE_SECONDS:
                result.append(("e32_offline", {}))
        if hub.fresh:
            for warning, since in self.active.items():
                if now - since > ACTIVE_WARNING_SECONDS:
                    result.append(("active_" + warning, {}))
            for room_id, since in self.rooms.items():
                if now - since > ROOM_LOST_SECONDS:
                    room = hub.rooms.get(room_id) or {"id": room_id}
                    from .heating_link import label
                    result.append(("room_without_measurement", {"room": label(room), "room_id": room_id}))
        for item in advice_items or ():
            if item.get("id") in ("pressure_low", "pressure_high"):
                result.append((item["id"], {"pressure": item.get("values", {}).get("pressure")}))
        if self.short_cycling is not None and now - self.short_cycling > SHORT_CYCLING_SECONDS:
            result.append(("short_cycling", {}))
        return result


def render(problems, lang):
    """The plain-language reasons in a language (English for anything but Dutch)."""
    from .heating_advice import fmt
    texts = TEXT["nl" if lang == "nl" else "en"]
    return [texts[key].format(**{name: fmt(value, lang) if name == "pressure" else value
                                 for name, value in values.items()}) for key, values in problems]


class HeatingProblemSensor(BinarySensorEntity):
    """On while the heating has a real problem; ``reasons`` says what (EN/NL)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "heating_problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    # The texts are shown and sent, not kept in the history.
    _unrecorded_attributes = frozenset({"reasons"})

    def __init__(self, entry, hub):
        from .room_plan import has_room_plan
        self.entry, self.hub = entry, hub
        self._attr_unique_id = f"{hub.prefix}_hub_heating_problem"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.prefix)})
        self.tracker = ProblemTracker(hub.clock(), expect_telemetry=has_room_plan(entry))
        self.current = []
        self._written = None

    def _advice_items(self):
        hass = getattr(self, "hass", None)
        advice = hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {}).get("heating_advice") if hass else None
        return getattr(advice, "items", ()) or ()

    @callback
    def evaluate(self, _now=None):
        now = self.hub.clock()
        self.tracker.observe(self.hub, now)
        self.current = self.tracker.problems(self.hub, now, self._advice_items())
        if getattr(self, "hass", None) is not None and self.entity_id:
            written = (self.is_on, tuple(key for key, _ in self.current), self.extra_state_attributes["reasons"])
            if written != self._written:
                self._written = written
                self.async_write_ha_state()

    @property
    def is_on(self):
        return bool(self.current)

    @property
    def extra_state_attributes(self):
        from .heating_advice import language
        lang = language(self.hass) if getattr(self, "hass", None) is not None else "en"
        return {"problems": [key for key, _ in self.current], "reasons": render(self.current, lang),
                "rooms": [values["room_id"] for key, values in self.current if "room_id" in values]}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.hub.add_listener(self.evaluate))
        self.async_on_remove(async_track_time_interval(self.hass, self.evaluate, CHECK_INTERVAL))
        self.evaluate()
