"""Per room in plain words (1.1): why it heats or not, who is home, an open window and the valves."""
from datetime import datetime, timezone
import json
from zoneinfo import ZoneInfo
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import room_overview as module
from custom_components.open_thermostat.e32_comfort import CONF_COMFORT
from custom_components.open_thermostat.heating_link import HeatingHub, wanted_sensors
from custom_components.open_thermostat.room_overview import (
    LINES, PRESENCE, PROGRAM_LEVELS, REASONS, OpenContact, RoomReason, RoomReasonSensor, e32_zone, open_contact,
    program_step, room_presence, room_reason)

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
        "valve_position": 40, "valve_problem": True, "program": None}
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


english_files = {"strings.json", "translations/en.json"}


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
    # HA 1.0.0rc7: the week program's step ("Comfort until 22:30, then Night 18.0 °C"), its levels and its parts.
    program = attributes["program"]["state"]
    assert set(program) == {*PROGRAM_LEVELS, "step"}, name
    assert placeholders(program["step"]) == ["level", "next", "time"], name
    assert (program["step"], program["night"]) == (
        ("{level} until {time}, then {next}", "Night") if name in english_files else
        ("{level} tot {time}, daarna {next}", "Nacht") if "nl" in name else ("{level} do {time}, potem {next}", "Noc"))
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
    assert js_table("PROGRAM") == english["state_attributes"]["program"]["state"]
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


# -- HA 1.0.0rc7: the week program now and its next step (program_step) ------------------------------------------------
AMSTERDAM = ZoneInfo("Europe/Amsterdam")
# Every day 6:30 Comfort 21 °C, 22:30 Night 18 °C, as the planner stores it (E32 beta.23: levels and their marks).
DAY = [[390, 2100], [1350, 1800]]
LEVELS = {"comfort": 2100, "eco": 1900, "night": 1800}


def plan(schedule=None, levels=LEVELS, marks=None):
    week = [[list(point) for point in day] for day in (schedule or [DAY] * 7)]
    out = {"id": "living", "schedule": week, "minimum_centi_c": 500, "maximum_centi_c": 3000}
    if levels is not None:
        out["levels"] = levels
        out["schedule_levels"] = marks if marks is not None else ".".join("13" for _ in range(7))
    return out


def local(*args):
    """A wall-clock moment in Amsterdam, as an aware datetime."""
    return datetime(*args, tzinfo=AMSTERDAM)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc).isoformat()


def step(plan_room, now, room_=None, away=None, zone=AMSTERDAM):
    return program_step(plan_room, now, zone, room_ if room_ is not None else room(comfort={"mode": "program"}), away)


def test_the_program_now_and_its_next_step_as_the_sketch():
    # Wednesday 4 November 2026, 20:00 in Amsterdam (UTC+1): "Comfort until 22:30, then Night 18.0 °C".
    assert step(plan(), local(2026, 11, 4, 20, 0)) == {
        "level": "comfort", "target": 21.0, "next_at": utc(2026, 11, 4, 21, 30), "next_level": "night", "next_target": 18.0}
    # At the switch minute itself the new point holds (the E32's RoomSchedule::at: at or before now).
    assert step(plan(), local(2026, 11, 4, 22, 30))["level"] == "night"
    assert step(plan(), local(2026, 11, 4, 22, 29, 59))["next_at"] == utc(2026, 11, 4, 21, 30)


def test_the_night_runs_over_midnight_and_the_week_wraps():
    # After 22:30 the next step is tomorrow's 6:30; before 6:30 the night holds from yesterday's last point.
    late = step(plan(), local(2026, 11, 4, 23, 30))
    assert (late["level"], late["next_at"], late["next_level"], late["next_target"]) == (
        "night", utc(2026, 11, 5, 5, 30), "comfort", 21.0)
    early = step(plan(), local(2026, 11, 5, 5, 0))
    assert (early["level"], early["target"], early["next_at"]) == ("night", 18.0, utc(2026, 11, 5, 5, 30))
    # Sunday night to Monday morning: the end of the week wraps to its start.
    sunday = step(plan(), local(2026, 11, 8, 23, 0))
    assert (sunday["level"], sunday["next_at"]) == ("night", utc(2026, 11, 9, 5, 30))
    # Points on Monday only: from Friday the Monday night holds until next Monday 7:00 (empty days in between).
    monday = plan([[[420, 2000], [1320, 1600]], [], [], [], [], [], []], levels=None)
    friday = step(monday, local(2026, 11, 6, 12, 0))
    assert friday == {"level": "night", "target": 16.0, "next_at": utc(2026, 11, 9, 6, 0), "next_level": "comfort",
                      "next_target": 20.0}
    # Monday before 7:00: the night of the Monday a week earlier (a week back at most).
    assert step(monday, local(2026, 11, 9, 6, 0))["level"] == "night"


def test_a_point_that_changes_nothing_is_not_a_step():
    noon = plan([[[390, 2100], [720, 2100], [1350, 1800]]] * 7, marks=".".join("113" for _ in range(7)))
    assert step(noon, local(2026, 11, 4, 9, 0))["next_at"] == utc(2026, 11, 4, 21, 30)
    # The same temperature as another level is a step (the planner names it): Eco and Night both 18 °C.
    same = plan([[[390, 2100], [1200, 1800], [1350, 1800]]] * 7, levels={"comfort": 2100, "eco": 1800, "night": 1800},
                marks=".".join("123" for _ in range(7)))
    evening = step(same, local(2026, 11, 4, 20, 30))
    assert (evening["level"], evening["next_at"], evening["next_level"], evening["next_target"]) == (
        "eco", utc(2026, 11, 4, 21, 30), "night", 18.0)
    # Nothing changes all week: the level now, no next step (the card then shows nothing).
    flat = step(plan([[[0, 2000]]] + [[]] * 6, levels=None), local(2026, 11, 4, 20, 0))
    assert flat == {"level": "comfort", "target": 20.0, "next_at": None, "next_level": None, "next_target": None}


def test_the_levels_are_the_planners_stored_marks_else_inferred_as_it_shows_them():
    # A point marked 0 has its own temperature: no level name.
    own = plan([[[390, 2150], [1350, 1800]]] * 7, marks=".".join("03" for _ in range(7)))
    assert step(own, local(2026, 11, 4, 20, 0))["level"] is None
    # Marks that no longer fit the program (changed elsewhere): each point's first level with its temperature.
    stale = plan(marks=".".join("31" for _ in range(7)))
    assert step(stale, local(2026, 11, 4, 20, 0))["level"] == "comfort"
    # Older firmware (no stored levels): warmest Comfort, coolest Night, the most used in between Eco.
    three = plan([[[390, 2100], [540, 1900], [1020, 2100], [1350, 1700]]] * 7, levels=None)
    assert [step(three, local(2026, 11, 4, h, 0))["level"] for h in (7, 12, 20, 23)] == [
        "comfort", "eco", "comfort", "night"]


def test_a_planned_holiday_before_the_next_step_is_the_next_step():
    start = int(datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc).timestamp())  # 21:00 in Amsterdam
    away = {"on": False, "mode": "auto", "target_c": 15, "holiday_temperature_c": 12, "presence": "home",
            "holidays": [{"from": start, "until": start + 7 * 86400}]}
    assert step(plan(), local(2026, 11, 4, 20, 0), away=away) == {
        "level": "comfort", "target": 21.0, "next_at": utc(2026, 11, 4, 20, 0), "next_level": "holiday", "next_target": 12.0}
    # At most the holiday temperature: a cooler program then stays cooler (Night 18 °C under a holiday of 20 °C).
    night = {**away, "holiday_temperature_c": 20, "holidays": [{"from": start + 3 * 3600, "until": start + 86400}]}
    assert step(plan(), local(2026, 11, 4, 23, 0), away=night)["next_target"] == 18.0
    # A holiday after the next step changes nothing here; a running one holds the room (its sentence says so): None.
    later = {**away, "holidays": [{"from": start + 86400, "until": start + 2 * 86400}]}
    assert step(plan(), local(2026, 11, 4, 20, 0), away=later)["next_level"] == "night"
    running = room(comfort={"mode": "away", "target_c": 12, "until": start + 86400})
    assert step(plan(), local(2026, 11, 4, 22, 0), running, away) is None
    # Firmware without planned holidays (before rc.4): no list, no holiday step.
    assert step(plan(), local(2026, 11, 4, 20, 0), away={"on": False, "target_c": 15})["next_level"] == "night"


def test_only_while_the_program_sets_the_target():
    now = local(2026, 11, 4, 20, 0)
    for comfort in ({"mode": "timed", "target_c": 22, "until": 1}, {"mode": "next", "target_c": 22}, {"mode": "boost"},
                    {"mode": "away", "target_c": 15}, {"mode": "presence_away"}, {"mode": "window_open", "window": "open"},
                    {"mode": "away_return"}):
        assert step(plan(), now, room(comfort=comfort)) is None, comfort
    assert step(plan(), now, room(state="inactive")) is None
    assert step(plan(), now, room(setpoint_source="fallback")) is None  # no clock yet
    assert step(plan(), now, room(setpoint_source="ha")) is None
    # A room without a comfort report, or a pending window (it still heats): the program.
    assert step(plan(), now, room())["level"] == "comfort"
    assert step(plan(), now, room(comfort={"mode": "program", "window": "pending"}))["level"] == "comfort"
    for odd in (None, {}, {"schedule": None}, {"schedule": [[]] * 7}, {"schedule": [[[390, 2100]]] * 6},
                {"schedule": [[[390, "x"]]] * 7}, {"schedule": [[[600, 2000], [500, 1800]]] * 7}):
        assert step(odd, now) is None, odd
    assert program_step(plan(), datetime(2026, 11, 4, 20, 0), AMSTERDAM) is None  # a naive time: never a guess


def test_the_times_are_the_e32s_wall_clock_also_over_a_clock_change():
    # Sunday 25 October 2026 the clocks go back at 3:00: Saturday 23:00 is 21:00 UTC, Sunday 6:30 is 5:30 UTC.
    assert step(plan(), local(2026, 10, 24, 23, 0))["next_at"] == utc(2026, 10, 25, 5, 30)
    # The same program in London: the E32's own zone decides, not Home Assistant's.
    london = step(plan(), datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc), zone=ZoneInfo("Europe/London"))
    assert (london["level"], london["next_at"]) == ("comfort", utc(2026, 11, 4, 22, 30))


@pytest.mark.asyncio
async def test_the_e32s_time_zone_is_its_own_when_known_else_home_assistants(hass):
    from custom_components.open_thermostat.e32_system import TIME_ZONE_STATE
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    entry = SimpleNamespace(entry_id="e1")
    assert str(e32_zone(hass, entry)) == "Europe/Amsterdam" and str(e32_zone(hass, None)) == "Europe/Amsterdam"
    hass.data.setdefault("open_thermostat", {})["e1"] = {TIME_ZONE_STATE: "GMT0BST,M3.5.0/1,M10.5.0"}
    assert str(e32_zone(hass, entry)) == "Europe/London"
    # The rules of Home Assistant's own zone: that name; rules Home Assistant does not know: its own zone.
    hass.data["open_thermostat"]["e1"] = {TIME_ZONE_STATE: "CET-1CEST,M3.5.0,M10.5.0/3"}
    assert str(e32_zone(hass, entry)) == "Europe/Amsterdam"
    hass.data["open_thermostat"]["e1"] = {TIME_ZONE_STATE: "XYZ-5"}
    assert str(e32_zone(hass, entry)) == "Europe/Amsterdam"


@pytest.mark.asyncio
async def test_the_reason_sensor_carries_the_program_and_writes_again_at_its_next_step(hass):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    entity, hub = sensor(hass)
    # No plan read yet (or no E32 credentials): no program.
    assert entity.extra_state_attributes["program"] is None
    hub.update({**house(), "rooms": [room(comfort={"mode": "program"})]})
    hub.plan = SimpleNamespace(room=lambda room_id: plan() if room_id == "living" else None)
    assert entity._program(local(2026, 11, 4, 20, 0))["next_at"] == utc(2026, 11, 4, 21, 30)
    assert entity.extra_state_attributes["program"]["level"] in ("comfort", "night")
    assert "program" in entity._unrecorded_attributes  # live only, as the sentence's values
    # The state is written again just after the next step, also when the E32 reports nothing new then.
    entity.entity_id = "sensor.living_reason"
    entity._plan_tick()
    assert entity._tick is not None
    first = entity._tick
    entity._plan_tick()  # a new write replaces the timer, never a second one
    assert entity._tick is not first
    await entity.async_will_remove_from_hass()
    assert entity._tick is None
    hub.update(None)
    entity._plan_tick()
    assert entity._tick is None and entity.extra_state_attributes is None


def test_the_room_and_house_cards_share_one_clock():
    """R3 finding 11: one clock for both cards (the house's time zone, the viewer's 12/24 hours, a date beyond tomorrow)."""
    house = (COMPONENT / "frontend/house-card.js").read_text(encoding="utf-8")

    def block(text):
        return text[text.index("/* clock: begin"):text.index("/* clock: end */")]
    assert block(CARD) == block(house)
    assert "weekday: 'short', day: 'numeric', month: 'short'" in block(CARD) and "RelativeTimeFormat" in block(CARD)
    assert "hour: hour12 ? 'numeric' : '2-digit'" in block(CARD)
    assert "const moment = (hass, iso) => clockMoment(hass, iso);" in CARD and "const at = iso => clockMoment(hass, iso);" in house
