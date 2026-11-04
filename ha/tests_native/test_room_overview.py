"""Per room in plain words (1.1): why it heats or not, who is home, an open window and the valves."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import room_overview as module
from custom_components.open_thermostat.e32_comfort import CONF_COMFORT
from custom_components.open_thermostat.heating_link import HeatingHub, wanted_sensors
from custom_components.open_thermostat.room_overview import (
    LINES, PRESENCE, REASONS, OpenContact, RoomReason, RoomReasonSensor, open_contact, room_presence, room_reason)

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
CARD = (COMPONENT / "frontend/room-status-card.js").read_text(encoding="utf-8")
UNTIL = 1793561400  # 2026-11-02 21:30 UTC
SINCE = datetime(2026, 11, 1, 14, 5, tzinfo=timezone.utc)


def room(**extra):
    return {"id": "living", "name": "Living", "state": "active", "status": "ok", "source": "a4c138000001",
            "temperature": 20.6, "setpoint": 22.5, "setpoint_source": "schedule", "demand": True, **extra}


def house(mode="active", reason="heating", activity="idle", away=None):
    return {"schema": 1, "revision": 2, "mode": mode, "request": {"heat": True, "flow_c": 45, "reason": reason},
            "ha_entities": [], "burner": {"starts_last_hour": 1, "activity": activity},
            "away": away or {"on": False, "source": "none", "target_c": 18, "until": None, "presence": "home"}}


def why(r, status=None, contact=None):
    reason = room_reason(r, house() if status is None else status, contact)
    return reason.reason, reason.line, reason.values


def test_the_owners_examples_in_one_line_each():
    assert why(room()) == ("heating", "heating", {"temperature": 20.6, "target": 22.5})
    assert why(room(comfort={"mode": "window_open", "window": "open", "target_c": 8}), contact=OpenContact("Back door", SINCE)) == (
        "window_open", "window_open_contact", {"contact": "Back door", "since": SINCE})
    assert why(room(demand=False, comfort={"mode": "presence_away", "persons": "away", "target_c": 18})) == (
        "room_away", "room_away", {"target": 18.0})
    assert why(room(state="inactive", status="inactive", temperature=None, setpoint=None)) == ("off", "off", {})
    assert why(room(), house(activity="keep_warm")) == ("hot_water", "hot_water", {})


def test_the_reasons_win_in_order_and_use_only_reported_fields():
    # Off before an open window, an open window before a missing measurement or hot water.
    paused = {"mode": "window_open", "window": "open", "target_c": 8}
    assert why(room(state="inactive", comfort=paused))[0] == "off"
    assert why(room(temperature=None, comfort=paused), house(activity="tapping"))[:2] == ("window_open", "window_open")
    # Pending: the room still heats until its delay ends; the contact named when Home Assistant has it.
    pending = {"mode": "program", "window": "pending"}
    assert why(room(comfort=pending))[:2] == ("window_pending", "window_pending")
    assert why(room(comfort=pending), contact=OpenContact("Kitchen window")) == (
        "window_pending", "window_pending_contact", {"contact": "Kitchen window"})
    # A contact HA still sees open is never a reason by itself: the E32 decides the pause.
    assert why(room(), contact=OpenContact("Back door", SINCE))[0] == "heating"
    assert why(room(status="lost"))[0] == "no_measurement"
    assert why(room(temperature=None, status="stale"))[0] == "no_measurement"
    # Waiting for the boiler only while the room wants heat; the minimum pause only when the E32 controls it.
    for activity in ("tapping", "keep_warm", "charging", "hot_water"):
        assert why(room(), house(activity=activity))[0] == "hot_water"
    assert why(room(demand=False), house(activity="tapping"))[0] == "warm_enough"
    assert why(room(), house(reason="minimum_off"))[0] == "boiler_pause"
    assert why(room(), house(mode="shadow", reason="minimum_off"))[0] == "wants_heat"
    # Firmware without burner activity (before beta.23) never claims hot water.
    assert why(room(), {**house(), "burner": None})[0] == "heating"


def test_the_mode_that_sets_the_target_explains_it():
    until = datetime.fromtimestamp(UNTIL, timezone.utc)
    assert why(room(comfort={"mode": "away", "target_c": 16, "until": UNTIL})) == (
        "holiday", "holiday", {"until": until, "target": 16.0})
    assert why(room(comfort={"mode": "away", "target_c": 16})) == ("away", "away", {"target": 16.0})
    assert why(room(comfort={"mode": "away_return", "target_c": 21, "until": UNTIL}))[:2] == ("away_return", "away_return")
    # Everyone of the house away (no fresh report of the room's own persons); the house's away temperature
    # when the room's comfort leaves it out.
    assert why(room(demand=False, comfort={"mode": "presence_away"})) == ("house_away", "house_away", {"target": 18.0})
    assert why(room(comfort={"mode": "presence_away", "persons": "home", "target_c": 15}))[0] == "house_away"
    assert why(room(comfort={"mode": "boost", "override": "boost", "target_c": 24, "until": UNTIL})) == (
        "boost", "boost_until", {"until": until})
    assert why(room(comfort={"mode": "boost", "override": "boost", "remaining_s": 3000})) == ("boost", "boost", {})
    assert why(room(comfort={"mode": "next", "override": "next", "target_c": 21, "until": UNTIL})) == (
        "temporary", "temporary_until", {"target": 21.0, "until": until})
    assert why(room(comfort={"mode": "timed", "override": "timed", "remaining_s": 600})) == (
        "temporary", "temporary", {"target": 22.5})
    # "program" (only the persons or a pending window deviate) is the plan: what the room does.
    assert why(room(demand=False, comfort={"mode": "program", "persons": "home"})) == (
        "warm_enough", "warm_enough", {"temperature": 20.6, "target": 22.5})


def test_shadow_mode_wants_heat_instead_of_claiming_to_heat():
    assert why(room(), house(mode="shadow")) == ("wants_heat", "wants_heat", {"temperature": 20.6, "target": 22.5})
    assert why(room(demand=False, setpoint=None))[:2] == ("warm_enough", "no_heat_needed")


def test_odd_or_hostile_values_never_make_a_reason_up():
    assert room_reason(None) is None and room_reason("living") is None
    hostile = room(temperature="20", setpoint=True, demand="yes", comfort={"mode": "<img>", "window": ["open"], "target_c": "x"})
    assert why(hostile, {"mode": 1, "burner": "tapping", "request": [], "away": "x"})[:2] == ("warm_enough", "no_heat_needed")
    assert why(room(demand="yes", comfort="window_open"), {"burner": {"activity": "tapping"}})[0] == "warm_enough"
    assert why(room(comfort={"mode": "away", "until": -5, "target_c": 99}), {})[:3] == ("away", "away", {"target": None})
    assert isinstance(room_reason(room()), RoomReason)


def test_presence_is_the_rooms_own_persons_else_the_house():
    assert room_presence(room(comfort={"mode": "program", "persons": "home"}), house()) == "room_home"
    assert room_presence(room(comfort={"mode": "presence_away", "persons": "away"}), house()) == "room_away"
    assert room_presence(room(), house()) == "house_home"
    assert room_presence(room(), house(away={"on": True, "source": "presence", "presence": "away"})) == "house_away"
    assert room_presence(room(), house(away={"on": False, "presence": "unknown"})) is None
    assert room_presence(room(), None) is None and room_presence(None, {"away": "home"}) is None
    assert set(PRESENCE) == {"room_home", "room_away", "house_home", "house_away"}


@pytest.mark.asyncio
async def test_the_open_contact_is_the_one_open_longest(hass):
    hass.states.async_set("binary_sensor.back_door", "on", {"friendly_name": "Back door", "device_class": "door"})
    hass.states.async_set("binary_sensor.kitchen", "on", {"friendly_name": "Kitchen window", "device_class": "window"})
    hass.states.async_set("binary_sensor.hall", "on", {"friendly_name": "Hall window", "device_class": "window"})
    hass.states.async_set("binary_sensor.bath", "off", {"friendly_name": "Bath window", "device_class": "window"})
    first = hass.states.get("binary_sensor.back_door").last_changed
    assert open_contact(hass, ["binary_sensor.bath", "binary_sensor.back_door"]) == OpenContact("Back door", first)
    assert open_contact(hass, ["binary_sensor.kitchen", "binary_sensor.back_door"]).name == "Back door, Kitchen window"
    assert open_contact(hass, ["binary_sensor.hall", "binary_sensor.kitchen", "binary_sensor.back_door"]).name == (
        "Back door, Kitchen window +1")
    assert open_contact(hass, ["binary_sensor.bath", "binary_sensor.gone"]) is None
    assert open_contact(hass, []) is None


def sensor(hass, settings=None):
    hub = HeatingHub("fixture")
    entry = SimpleNamespace(entry_id="e1", options={CONF_COMFORT: settings} if settings is not None else {})
    hub.update({**house(), "rooms": [room(comfort={"mode": "window_open", "window": "open", "target_c": 8, "persons": "away"},
                                          setpoint=8.0)],
                "trv": {"output": False, "flow_offset_c": 0,
                        "rooms": [{"room": "living", "control": True, "degraded": False, "single_source": False,
                                   "valves": [{"name": "Valve 1", "model": "sonoff_trvzb", "health": "ok", "position_pct": 30},
                                              {"name": "Valve 2", "model": "sonoff_trvzb", "health": "low_battery",
                                               "position_pct": 51}]}]}})
    entity = RoomReasonSensor(hub, hub.rooms["living"])
    entity.hass, entity.platform = hass, SimpleNamespace(config_entry=entry)
    return entity, hub


@pytest.mark.asyncio
async def test_the_reason_sensor_names_the_contact_and_carries_the_card_values(hass):
    hass.states.async_set("binary_sensor.back_door", "on", {"friendly_name": "Back door", "device_class": "door"})
    since = hass.states.get("binary_sensor.back_door").last_changed
    entity, hub = sensor(hass, {"contacts": {"living": ["binary_sensor.back_door"]}})
    assert entity.unique_id == "fixture_e32_room_living_reason" and entity.translation_key == "room_reason"
    assert entity.options == REASONS and entity.native_value == "window_open"
    assert entity.extra_state_attributes == {
        "room_id": "living", "line": "window_open_contact", "values": {"contact": "Back door", "since": since.isoformat()},
        "temperature": 20.6, "setpoint": 8.0, "presence": "room_away", "window": "open",
        "valve_position": 40, "valve_problem": True}
    # The contact closed in HA while the E32 still pauses: the sentence without a name, never a wrong one.
    hass.states.async_set("binary_sensor.back_door", "off", {"friendly_name": "Back door", "device_class": "door"})
    assert entity.extra_state_attributes["line"] == "window_open" and entity.extra_state_attributes["values"] == {}
    # No contacts configured, no valves: plain values; an E32 gone silent makes the sensor unknown.
    plain, hub = sensor(hass)
    hub.valves = {}
    attributes = plain.extra_state_attributes
    assert attributes["line"] == "window_open" and attributes["valve_position"] is None and attributes["valve_problem"] is None
    hub.update(None)
    assert plain.native_value is None and plain.extra_state_attributes is None and not plain.available


def test_every_e32_room_gets_a_reason_sensor():
    hub = HeatingHub("fixture")
    hub.update({**house(), "rooms": [room(), room(id="study", name="Study")]})
    keys = [key for key, _factory in wanted_sensors(hub)]
    assert ("room", "living", "reason") in keys and ("room", "study", "reason") in keys
    made = dict(wanted_sensors(hub))[("room", "study", "reason")]()
    assert isinstance(made, RoomReasonSensor) and made.room_id == "study"


def placeholders(text):
    return sorted(re.findall(r"\{(\w+)\}", text))


@pytest.mark.parametrize("name", ["strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"])
def test_every_reason_and_sentence_has_its_words_with_the_same_values(name):
    words = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]["sensor"]["room_reason"]
    assert set(words["state"]) == set(REASONS), name
    attributes = words["state_attributes"]
    assert set(attributes["line"]["state"]) == set(LINES), name
    for line, values in LINES.items():
        assert placeholders(attributes["line"]["state"][line]) == sorted(values), (name, line)
    assert set(attributes["presence"]["state"]) == set(PRESENCE) and set(attributes["window"]["state"]) == {"open", "pending"}
    assert all(attributes[key]["name"] for key in ("temperature", "setpoint", "valve_position"))
    # rc.5 (the owner's sketch): each reason in one word for the card's chip, and the card's other chips.
    assert set(attributes["chip"]["state"]) == set(REASONS), name
    assert set(attributes["card"]["state"]) == {"smart_on", "home", "away", "holiday"}, name
    assert all(text.strip() and "{" not in text for part in ("chip", "card") for text in attributes[part]["state"].values())
    # The words the owner asked for, in each language.
    english = {"strings.json", "translations/en.json"}
    heating = attributes["line"]["state"]["heating"]
    assert heating == ("Heating: {temperature} → {target} °C" if name in english else
                       "Verwarmt: {temperature} → {target} °C" if "nl" in name else "Grzeje: {temperature} → {target} °C")
    chips = attributes["chip"]["state"]
    assert (chips["heating"], chips["warm_enough"], chips["off"], attributes["card"]["state"]["smart_on"]) == (
        ("Heating", "At temperature", "Off", "Smart warm-up on") if name in english else
        ("Verwarmt", "Op temperatuur", "Uit", "Slim opwarmen aan") if "nl" in name else
        ("Grzeje", "Temperatura osiągnięta", "Wyłączone", "Inteligentne nagrzewanie włączone"))


def js_table(name):
    """{key: text} of a ``const NAME = {key: 'text', ...};`` table in the card."""
    return dict(re.findall(r"(\w+): '([^']*)'", re.search(r"const " + name + r" = \{(.*?)\};", CARD, re.S)[1]))


def test_the_card_knows_every_reason_and_reads_the_integrations_words():
    assert set(js_table("TONE")) == set(REASONS)
    # Its English last resorts are the integration's English words, key for key.
    english = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))["entity"]["sensor"]["room_reason"]
    assert js_table("CHIP") == english["state_attributes"]["chip"]["state"]
    assert js_table("WORDS") == english["state_attributes"]["card"]["state"]
    assert "const KEY = 'component.open_thermostat.entity.sensor.room_reason.state_attributes.';" in CARD
    assert set(js_table("PRESENCE")) == set(PRESENCE) and set(js_table("PRESENCE").values()) == {"home", "away"}
    # The same registry guard as the week card, and no innerHTML: names and contacts are text.
    assert CARD.count("customElements.define(") == 1 and "ensureDefined('openthermostat-room-status', OpenThermostatRoomStatus);" in CARD
    assert "setInterval(check, 500);" in CARD and "innerHTML" not in CARD
    from custom_components.open_thermostat.dashboard import ROOM_STATUS_CARD_TYPE
    assert ROOM_STATUS_CARD_TYPE == "custom:openthermostat-room-status"
    assert module.CARD_URL.startswith("/open_thermostat/room-status-card-")


def test_rc3_names_who_is_away_and_smart_warm_up_is_a_reason():
    away = {"mode": "presence_away", "persons": "away", "target_c": 15}
    # rc.3 says whose absence it is: the room's own persons, or everyone.
    assert room_reason(room(demand=False, comfort={**away, "away_by": "house"})).reason == "house_away"
    assert room_reason(room(demand=False, comfort={**away, "away_by": "room"})).reason == "room_away"
    start = {"applies": True, "start_now": True, "reason": "planned",
             "next_switch": {"utc": 1_800_000_000, "target_c": 21}}
    got = room_reason(room(comfort={"mode": "program"}), None, None, start)
    assert got.reason == "warm_up" and got.values["target"] == 21
    # Only an applied, started warm-up counts; an estimate does not.
    assert room_reason(room(comfort={"mode": "program"}), None, None, {**start, "applies": False}).reason == "wants_heat"
