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
  control for more than 5 minutes;
* active control is chosen but the E32 waits for the owner to confirm that
  the old thermostat is disconnected (for example after a firmware update
  cleared the confirmation), for 10 minutes or more: it gives no heat until
  then (``active.awaiting_confirmation`` of the heating status);
* a room that asks for heat stays more than WARN_ROOM_SLOW_MARGIN_C below its
  target for WARN_ROOM_SLOW_HOURS (with a working measurement; a gap in the
  E32's data starts the wait again, so nothing fires on a day with gaps);
* the E32 is online but Home Assistant has had no working session with it for
  WARN_SESSION_LOST_MINUTES (the shadow link is switched on but not ready).

Each problem is also a Repairs issue (issue_sync.py), created when the
problem starts and removed when it clears; the water pressure keeps its own
issue (heating_advice.py).

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

from .const import DOMAIN, WARN_ROOM_SLOW_HOURS, WARN_ROOM_SLOW_MARGIN_C, WARN_SESSION_LOST_MINUTES
from .issue_sync import clear_issues, sync_issues

ROOM_LOST_SECONDS = 30 * 60
TELEMETRY_STALE_SECONDS = 10 * 60
SHORT_CYCLING_SECONDS = 2 * 3600
ACTIVE_WARNING_SECONDS = 5 * 60
AWAITING_CONFIRMATION_SECONDS = 10 * 60
ROOM_SLOW_SECONDS = WARN_ROOM_SLOW_HOURS * 3600
SESSION_LOST_SECONDS = WARN_SESSION_LOST_MINUTES * 60
# Rooms whose temperature counts for "does not get warm" (no window open, not switched off).
ROOM_MEASURED = ("ok", "fallback")
# The Repairs group of these issues (issue_sync.py); the pressure has its own issue already.
ISSUE_GROUP = "heating_problem"
NO_ISSUE = ("pressure_low", "pressure_high")
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
        "awaiting_confirmation": "The E32 is waiting for you to confirm that the old thermostat is disconnected; "
                                 "it is not heating until you do. Open the E32 Rooms page → Active control.",
        "pressure_low": "The water pressure is low ({pressure} bar). Top up the heating system.",
        "pressure_high": "The water pressure is high ({pressure} bar). Have the expansion vessel checked.",
        "short_cycling": "The boiler has been switching on and off too often for more than 2 hours.",
        "active_foreign_controller": "Another thermostat still sends heat requests to the boiler.",
        "active_measurement_lost": "The E32 lost the room measurements and stopped asking for heat.",
        "active_boiler_no_response": "The boiler does not respond to the E32's heat request.",
        "active_transmit_failed": "The E32 cannot send its heat request to the boiler.",
        "room_slow": "{room} asks for heat but has stayed more than {margin} °C below its target for "
                     "{hours} hours. Check that the radiators or floor heating get warm and that the boiler's "
                     "maximum flow temperature is high enough.",
        "session_lost": "The E32 is online, but Home Assistant has had no working connection with it for more "
                        "than {minutes} minutes, so rooms get no new targets from Home Assistant. Open the "
                        "integration and choose Connect E32 again if it does not recover.",
    },
    "nl": {
        "room_without_measurement": "{room}: al meer dan 30 minuten geen temperatuurmeting, dus deze ruimte "
                                    "vraagt geen warmte. Controleer de batterij en de afstand van de sensor.",
        "e32_offline": "De E32 meldt zich al meer dan 10 minuten niet. Controleer de stroom en de wifi.",
        "awaiting_confirmation": "De E32 wacht tot je bevestigt dat de oude thermostaat is losgekoppeld; tot "
                                 "dan verwarmt hij niet. Open op de E32 de pagina Ruimtes → Actieve regeling.",
        "pressure_low": "De waterdruk is laag ({pressure} bar). Vul de cv-installatie bij.",
        "pressure_high": "De waterdruk is hoog ({pressure} bar). Laat het expansievat controleren.",
        "short_cycling": "De ketel slaat al meer dan 2 uur te vaak aan en uit.",
        "active_foreign_controller": "Een andere thermostaat stuurt nog warmtevragen naar de ketel.",
        "active_measurement_lost": "De E32 heeft geen ruimtemetingen meer en vraagt geen warmte meer.",
        "active_boiler_no_response": "De ketel reageert niet op de warmtevraag van de E32.",
        "active_transmit_failed": "De E32 kan zijn warmtevraag niet naar de ketel sturen.",
        "room_slow": "{room} vraagt warmte, maar blijft al {hours} uur meer dan {margin} °C onder de gewenste "
                     "temperatuur. Kijk of de radiatoren of de vloerverwarming warm worden en of de maximale "
                     "aanvoertemperatuur van de ketel hoog genoeg is.",
        "session_lost": "De E32 is online, maar Home Assistant heeft al meer dan {minutes} minuten geen werkende "
                        "verbinding met hem, dus de ruimtes krijgen geen nieuwe doelen uit Home Assistant. Open de "
                        "integratie en kies opnieuw Connect E32 als het niet vanzelf herstelt.",
    },
}


def _active(status):
    active = status.get("active") if status else None
    return active if type(active) is dict else None


def awaiting_confirmation(hub):
    """Whether the E32's active control is chosen but waits for the owner's "thermostat disconnected".

    The E32 reports it in its heating status (``active.awaiting_confirmation``,
    or ``active.state`` ``awaiting_confirmation``); a hub that keeps the
    active-control block apart (``hub.active``) is read the same way.
    """
    active = getattr(hub, "active", None)
    active = active if type(active) is dict else _active(hub.status)
    return bool(active) and (active.get("awaiting_confirmation") is True
                             or active.get("state") == "awaiting_confirmation")


class ProblemTracker:
    """Since when each condition holds (monotonic seconds); pure, so it is easy to test."""

    def __init__(self, now, expect_telemetry=False):
        self.started = now
        self.expect_telemetry = expect_telemetry
        self.rooms = {}          # room id -> since without a measurement
        self.short_cycling = None
        self.active = {}         # warning -> since
        self.awaiting = None     # since active control waits for the owner's confirmation
        self.slow = {}           # room id -> since it asks for heat but stays well below its target
        self.session_lost = None  # since the E32 is online but the shadow link has no working session

    def observe(self, hub, now, session_ready=None):
        """Follow the hub's latest status (call on every hub change and periodically).

        ``session_ready``: True / False while the shadow link is switched on (its session works or
        not), None when it is off or unknown.
        """
        if not hub.fresh:
            # An outage is its own reason; keep the measurement timers as they were. The slow-room and
            # session waits start again after the gap: without data nothing is known about them.
            self.slow = {}
            self.session_lost = None
            return
        if session_ready is False:
            self.session_lost = self.session_lost if self.session_lost is not None else now
        else:
            self.session_lost = None
        slow = {}
        for room_id, room in hub.rooms.items():
            if room.get("status") not in ROOM_MEASURED or room.get("demand") is not True:
                continue
            comfort = room.get("comfort")
            if type(comfort) is dict and comfort.get("window") in ("open", "pending"):
                continue
            temperature, target = _number(room.get("temperature")), _number(room.get("setpoint"))
            if temperature is not None and target is not None and temperature < target - WARN_ROOM_SLOW_MARGIN_C:
                slow[room_id] = self.slow.get(room_id, now)
        self.slow = slow
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
        if not awaiting_confirmation(hub):
            self.awaiting = None
        elif self.awaiting is None:
            self.awaiting = now

    def problems(self, hub, now, advice_items=()):
        """[(id, placeholders)] of the current problems, most important first."""
        result = []
        last = getattr(hub, "last_seen", None)
        if last is not None or self.expect_telemetry:
            since = last if last is not None else self.started
            if not hub.fresh and now - since > TELEMETRY_STALE_SECONDS:
                result.append(("e32_offline", {}))
        if hub.fresh:
            if self.awaiting is not None and now - self.awaiting >= AWAITING_CONFIRMATION_SECONDS:
                result.append(("awaiting_confirmation", {}))
            for warning, since in self.active.items():
                if now - since > ACTIVE_WARNING_SECONDS:
                    result.append(("active_" + warning, {}))
            from .heating_link import label
            for room_id, since in self.rooms.items():
                if now - since > ROOM_LOST_SECONDS:
                    room = hub.rooms.get(room_id) or {"id": room_id}
                    result.append(("room_without_measurement", {"room": label(room), "room_id": room_id}))
            for room_id, since in self.slow.items():
                if now - since >= ROOM_SLOW_SECONDS:
                    room = hub.rooms.get(room_id) or {"id": room_id}
                    result.append(("room_slow", {"room": label(room), "room_id": room_id,
                                                 "hours": WARN_ROOM_SLOW_HOURS, "margin": WARN_ROOM_SLOW_MARGIN_C}))
            if self.session_lost is not None and now - self.session_lost >= SESSION_LOST_SECONDS:
                result.append(("session_lost", {"minutes": WARN_SESSION_LOST_MINUTES}))
        for item in advice_items or ():
            if item.get("id") in ("pressure_low", "pressure_high"):
                result.append((item["id"], {"pressure": item.get("values", {}).get("pressure")}))
        if self.short_cycling is not None and now - self.short_cycling > SHORT_CYCLING_SECONDS:
            result.append(("short_cycling", {}))
        return result


def _number(value):
    from .heating_link import number
    return number(value, -40, 85)


def render(problems, lang):
    """The plain-language reasons in a language (English for anything but Dutch)."""
    from .heating_advice import fmt
    texts = TEXT["nl" if lang == "nl" else "en"]
    return [texts[key].format(**{name: fmt(value, lang) if name in ("pressure", "margin") else value
                                 for name, value in values.items()}) for key, values in problems]


def issues(problems, lang):
    """{issue item: (translation key, placeholders)} for the Repairs issues of the current problems."""
    result = {}
    for (key, values), reason in zip(problems, render(problems, lang)):
        if key in NO_ISSUE:
            continue
        item = key + ("_" + values["room_id"] if "room_id" in values else "")
        result[item] = ("heating_problem", {"reason": reason})
    return result


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

    def _session_ready(self):
        """True / False while the shadow link is switched on; None when it is off or unknown."""
        hass = getattr(self, "hass", None)
        runtime = hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {}).get("v1_runtime") if hass else None
        if runtime is None or getattr(runtime, "enabled", False) is not True:
            return None
        ready = getattr(runtime, "transport_ready", None)
        return ready if type(ready) is bool else None

    def _advice_items(self):
        hass = getattr(self, "hass", None)
        advice = hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {}).get("heating_advice") if hass else None
        return getattr(advice, "items", ()) or ()

    @callback
    def evaluate(self, _now=None):
        now = self.hub.clock()
        self.tracker.observe(self.hub, now, self._session_ready())
        self.current = self.tracker.problems(self.hub, now, self._advice_items())
        if getattr(self, "hass", None) is not None and self.entity_id:
            written = (self.is_on, tuple(key for key, _ in self.current), self.extra_state_attributes["reasons"])
            if written != self._written:
                self._written = written
                self.async_write_ha_state()
                from .heating_advice import language
                sync_issues(self.hass, self.entry.entry_id, ISSUE_GROUP, issues(self.current, language(self.hass)))

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
        self.async_on_remove(lambda: clear_issues(self.hass, self.entry.entry_id, ISSUE_GROUP))
        self.evaluate()
