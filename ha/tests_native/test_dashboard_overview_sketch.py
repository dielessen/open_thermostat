"""The Overview as the owner's sketch (rc.5, P18): the house card across the top, under it Rooms, Today and House.

The sketches (out/rc5-design/project): Main.dc.html (phone, light), Overzicht-donker.dc.html (phone, dark) and
Overzicht-desktop.dc.html (1280 px). The house card stands alone on top, without a heading; under it "Ruimtes"
(one status card per room), "Vandaag" ("Morgen warmt de woonkamer vanaf 6:10 op om 7:00 op 20,5 °C te zijn.
Gisteren was hij 4 minuten te vroeg." and "Buiten 9 °C: weerafhankelijke regeling vraagt 30 °C water,
standaardlijn (de geleerde lijn volgt na 6 rustige periodes).") and "Huis" (home or away, the holiday planner,
outside), one column each: side by side on a wide screen, under each other on a phone.

Today is one markdown card whose text follows the sensors (rendered here with Home Assistant's own template engine
at a fixed moment); it and its section show exactly while one of its lines has a value. The room card is drawn in
test/ha-room-status-card-browser.cjs, the layout at phone and desktop width in test/dashboard-views-browser.cjs.
"""
from datetime import datetime
import json
import random
from zoneinfo import ZoneInfo

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat.dashboard import (ICONS, ROOM_STATUS_CARD_TYPE, TEXT, RoomDashboard,
                                                         _today_section, view_cards)
from custom_components.open_thermostat.room_overview import HOUSE_CARD_TYPE
from test_dashboard_heating import STATUS, installation, walk
from test_dashboard_redesign import UNKNOWN, known, shown

ZONE = ZoneInfo("Europe/Amsterdam")
NOW = datetime(2026, 11, 4, 14, 30, tzinfo=ZONE)  # a Wednesday afternoon in the owner's house
PLANNER = "/config/integrations/integration/open_thermostat"
HEADINGS = {"en": ["Rooms", "Today", "House"], "nl": ["Ruimtes", "Vandaag", "Huis"], "pl": ["Pomieszczenia", "Dziś", "Dom"]}


@pytest.fixture
def clock(monkeypatch):
    """Home Assistant's clock at NOW in the owner's time zone (templates call dt_util.now())."""
    monkeypatch.setattr(dt_util, "DEFAULT_TIME_ZONE", ZONE)
    monkeypatch.setattr(dt_util, "now", lambda time_zone=None: NOW.astimezone(time_zone or ZONE))
    return NOW


def sketch(hass, language="en", *, inactive=(), outdoor="sensor.buiten", with_curve=True, with_smart=True):
    """The fixture house with what the sketch shows: the house card's entities, the house mode, each room's Reason,
    "Heating starts" and "Warm on time", the weather compensation sensor, the Smart warm-up switch and an outdoor
    sensor set under Energy and outdoor temperature. inactive: rooms the E32 reports switched off."""
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)

    def add(domain, unique_id, device=product):
        return entities.async_get_or_create(domain, "open_thermostat", unique_id, config_entry=e, device_id=device.id,
                                            suggested_object_id=unique_id.removeprefix("fixture_")).entity_id
    for key in ("boiler_activity", "dhw_taps_today", "heating_gas", "daily_burner_starts"):
        hub[key] = add("sensor", f"fixture_hub_{key}")
    hub["house_mode"] = add("select", "fixture_house_mode")
    for room_id in rooms:
        device = devices.async_get_device_by_identifier(("open_thermostat", f"fixture_e32_room_{room_id}"), e.entry_id)
        for key in ("reason", "heating_start", "warm_on_time"):
            rooms[room_id][key] = add("sensor", f"fixture_e32_room_{room_id}_{key}", device)
    flow = {}
    if with_curve:
        flow["curve"] = add("sensor", "fixture_flow_curve")
    if with_smart:
        flow["apply_learned"] = add("switch", "fixture_flow_apply_learned")
    if outdoor:
        hass.config_entries.async_update_entry(e, options={**e.options, "energy_outdoor_entity": outdoor})
    status = json.loads(json.dumps(STATUS))
    for room in status["rooms"]:
        room["state"] = "inactive" if room["id"] in inactive else "active"
    hass.data["open_thermostat"][e.entry_id]["heating_hub"].update(status)
    board = RoomDashboard(hass, "fixture", e.entry_id)
    config = board._dashboard_config()
    assert None not in list(walk(config))
    return config, rooms, hub, fields, flow, board


def overview(config):
    return config["views"][0]


def headed(config, heading):
    return next(s for s in overview(config)["sections"] if s["cards"][0].get("heading") == heading)


def today_card(config, language="en"):
    return headed(config, TEXT[language]["today"])["cards"][1]


def render(hass, card):
    """The card's text as Home Assistant's markdown card renders it: strictly (an undefined value is an error)."""
    return Template(card["content"], hass).async_render(parse_result=False, strict=True)


def local(day, hour, minute):
    """An ISO moment in the owner's time zone, as Home Assistant keeps a timestamp sensor's state (UTC)."""
    return datetime(2026, 11, day, hour, minute, tzinfo=ZONE).astimezone(ZoneInfo("UTC")).isoformat()


def heating_start(hass, entity, start, switch=None, target=20.5, start_now=False, lead=50, estimate=None):
    """The room's "Heating starts" sensor: the planned start, the program step it is for (rc.2), start_now, the lead
    (minutes before the step) and, when given, estimate (E32 rc.4: a start no morning has judged yet)."""
    attributes = {"reason": "planned", "lead_minutes": lead, "start_now": start_now}
    if estimate is not None:
        attributes["estimate"] = estimate
    if switch:
        attributes.update(switch_at=local(*switch), target_c=target)
    hass.states.async_set(entity, local(*start) if start else "unknown", attributes)


def curve(hass, entity, flow=30, outdoor=9.2, state="applied", source="design", windows=0):
    """"Water temperature by weather compensation": what it asks and the outdoor temperature it uses (°C), whether it
    is on (applied) or advice, where its line comes from and the steady periods seen so far."""
    hass.states.async_set(entity, str(flow) if flow is not None else "unknown", {
        "state": state, "slope": 0.67, "slope_source": source, "windows": windows, "outdoor_c": outdoor,
        "flow_c": flow, "unit_of_measurement": "°C"})


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_the_overview_is_the_house_card_then_rooms_today_and_house(hass, language):
    config, rooms, hub, fields, flow, board = sketch(hass, language)
    view = overview(config)
    # Three columns on a wide screen: the house card across all three, the other sections one column each.
    assert (view["max_columns"], view["dense_section_placement"]) == (3, True)
    top, *rest = view["sections"]
    assert top == {"type": "grid", "column_span": 3, "cards": [top["cards"][0]]}
    assert top["cards"][0]["type"] == HOUSE_CARD_TYPE and "heading" not in top["cards"][0]
    assert [s["cards"][0]["heading"] for s in rest] == HEADINGS[language]
    assert all(s["cards"][0]["type"] == "heading" and "column_span" not in s for s in rest)
    # Rooms two rows high: in two columns (1280 px with Home Assistant's sidebar) Today and House stack beside it.
    assert [s.get("row_span") for s in rest] == [2, None, None]
    # One icon per concept (dashboard-spec §1).
    assert [s["cards"][0]["icon"] for s in rest] == ["mdi:thermostat", ICONS["today"], ICONS["house"]]
    # Every other view keeps its two columns.
    assert all(v["max_columns"] == 2 for v in config["views"][1:] if v.get("type") == "sections")


@pytest.mark.asyncio
async def test_each_room_card_gets_smart_warm_up_and_the_house_mode(hass):
    config, rooms, hub, fields, flow, board = sketch(hass)
    cards = headed(config, "Rooms")["cards"][1:]
    assert cards == [{"type": ROOM_STATUS_CARD_TYPE, "entity": rooms[key]["reason"], "name": name,
                      "smart": flow["apply_learned"], "mode": hub["house_mode"]}
                     for key, name in (("woonkamer", "Woonkamer"), ("badkamer", "Badkamer"))]
    # Without the switch and the select (older firmware) the card has only its room.
    registry = er.async_get(hass)
    registry.async_remove(flow["apply_learned"])
    registry.async_remove(hub["house_mode"])
    cards = headed(board._dashboard_config(), "Rooms")["cards"][1:]
    assert cards[0] == {"type": ROOM_STATUS_CARD_TYPE, "entity": rooms["woonkamer"]["reason"], "name": "Woonkamer"}


@pytest.mark.asyncio
async def test_the_room_that_is_on_is_in_the_house_card_and_first_under_rooms(hass):
    """The owner's house as the sketch shows it: the living room on (inside the house card, its summary, and first
    under "Ruimtes" with its line, chips and tap), the bathroom off after it. No "Other rooms" heading."""
    config, rooms, hub, fields, flow, board = sketch(hass, "nl", inactive=("badkamer",))
    top = overview(config)["sections"][0]["cards"][0]
    assert top["rooms"] == [{"entity": rooms["woonkamer"]["reason"], "name": "Woonkamer"}]
    cards = overview(config)["sections"][1]["cards"]
    assert cards[0]["heading"] == "Ruimtes"
    assert [c["entity"] for c in cards[1:]] == [rooms["woonkamer"]["reason"], rooms["badkamer"]["reason"]]
    assert [s["cards"][0].get("heading") for s in overview(config)["sections"]] == [None, "Ruimtes", "Vandaag", "Huis"]


# Today's two icons, blue as in the sketch (a markdown card keeps <font color> only, dashboard._icon).
CLOCK = '<font color="#039be5"><ha-icon icon="mdi:clock-outline"></ha-icon></font> '
WEATHER = '<font color="#039be5"><ha-icon icon="mdi:sun-thermometer"></ha-icon></font> '


@pytest.mark.asyncio
@pytest.mark.parametrize("language, words", [
    ("en", CLOCK + "Tomorrow Woonkamer warms up from **6:10** to be 20.5 °C at **7:00**. Yesterday it was warm 4 minutes "
           "early.\n\n" + WEATHER + "Outside 9 °C: weather compensation asks for 30 °C water, standard line (the learned "
           "line follows after 6 steady periods)."),
    ("nl", CLOCK + "Morgen warmt Woonkamer vanaf **6:10** op om **7:00** op 20,5 °C te zijn. Gisteren was het 4 minuten "
           "te vroeg warm.\n\n" + WEATHER + "Buiten 9 °C: weerafhankelijke regeling vraagt 30 °C water, standaardlijn (de "
           "geleerde lijn volgt na 6 rustige periodes)."),
    ("pl", CLOCK + "Woonkamer: jutro nagrzewanie od **6:10**, aby o **7:00** było 20,5 °C. Wczoraj ciepło 4 min za "
           "wcześnie.\n\n" + WEATHER + "Na zewnątrz 9 °C: kompensacja pogodowa zadaje 30 °C wody, linia standardowa "
           "(wyuczona linia po 6 stabilnych okresach)."),
])
async def test_today_says_the_sketchs_two_lines(hass, clock, language, words):
    config, rooms, hub, fields, flow, board = sketch(hass, language, inactive=("badkamer",))
    card = today_card(config, language)
    living = rooms["woonkamer"]
    heating_start(hass, living["heating_start"], (5, 6, 10), (5, 7, 0))
    hass.states.async_set(living["warm_on_time"], "-4", {"unit_of_measurement": "min"})
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})  # off: no line, whatever it plans
    heating_start(hass, rooms["badkamer"]["heating_start"], (5, 5, 0), (5, 6, 0))
    hass.states.async_set(flow["apply_learned"], "on", {})
    curve(hass, flow["curve"])
    assert render(hass, card) == words
    # The heading names it as the sketch does; the text follows the sensors, so a new day needs no rebuild.
    assert headed(config, TEXT[language]["today"])["cards"][0]["heading"] == HEADINGS[language][1]


@pytest.mark.asyncio
async def test_today_says_every_case_of_a_warm_up_in_plain_words(hass, clock):
    config, rooms, hub, fields, flow, board = sketch(hass)
    card = today_card(config)
    living, start, warm = rooms["woonkamer"], rooms["woonkamer"]["heating_start"], rooms["woonkamer"]["warm_on_time"]
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    hass.states.async_set(flow["apply_learned"], "on", {})
    first = lambda: render(hass, card).split("\n\n")[0].removeprefix(CLOCK)  # noqa: E731
    # Later today; on another day; already warming up (the start passed, or the E32 says so); a whole target.
    heating_start(hass, start, (4, 16, 10), (4, 17, 0), 21)
    assert first() == "Today Woonkamer warms up from **16:10** to be 21 °C at **17:00**."
    heating_start(hass, start, (7, 6, 10), (7, 7, 0), 19.5)
    assert first() == "On 7 Nov Woonkamer warms up from **6:10** to be 19.5 °C at **7:00**."
    heating_start(hass, start, (4, 14, 5), (4, 15, 0), 21)
    assert first() == "Woonkamer is warming up now to be 21 °C at **15:00**."
    heating_start(hass, start, (4, 14, 40), (4, 15, 0), 21, start_now=True)
    assert first() == "Woonkamer is warming up now to be 21 °C at **15:00**."
    # Smart warm-up off: heating starts at the program time, and the line says why.
    hass.states.async_set(flow["apply_learned"], "off", {})
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    assert first() == "Tomorrow Woonkamer starts heating at **7:00** for 20.5 °C (Smart warm-up is off)."
    # An older E32 without the program step: the start alone.
    hass.states.async_set(flow["apply_learned"], "on", {})
    heating_start(hass, start, (5, 6, 10))
    assert first() == "Tomorrow Woonkamer starts warming up at **6:10**."
    # Yesterday: late, a minute either way, on time; nothing while the scoreboard has no figure.
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    for minutes, said in (("12", " Yesterday it was warm 12 minutes late."), ("1", " Yesterday it was warm 1 minute late."),
                          ("-1", " Yesterday it was warm 1 minute early."), ("0.4", " Yesterday it was warm on time."),
                          ("unknown", "")):
        hass.states.async_set(warm, minutes, {})
        assert first() == "Tomorrow Woonkamer warms up from **6:10** to be 20.5 °C at **7:00**." + said, minutes
    # No step up within 24 hours (the start is unknown) or the room switched off: no line for it.
    heating_start(hass, start, None)
    assert "Woonkamer" not in render(hass, card)
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    hass.states.async_set(living["state"], "inactive", {})
    assert "Woonkamer" not in render(hass, card)
    # Dutch and Polish say the other cases too.
    hass.states.async_set(living["state"], "active", {})
    hass.config.language = "nl"
    dutch = today_card(board._dashboard_config(), "nl")
    hass.states.async_set(warm, "3", {})
    assert render(hass, dutch).split("\n\n")[0].endswith(
        "Morgen warmt Woonkamer vanaf **6:10** op om **7:00** op 20,5 °C te zijn. Gisteren was het 3 minuten te laat warm.")
    heating_start(hass, start, (7, 6, 10), (7, 7, 0), 21)
    assert "Op 7 nov warmt Woonkamer vanaf **6:10** op om **7:00** op 21 °C te zijn." in render(hass, dutch)
    hass.config.language = "pl"
    polish = today_card(board._dashboard_config(), "pl")
    hass.states.async_set(flow["apply_learned"], "off", {})
    assert ("Woonkamer: 7 lis grzanie od **7:00** do 21 °C (Inteligentne nagrzewanie wyłączone). Wczoraj ciepło 3 min za "
            "późno.") in render(hass, polish)


# rc7: the owner's card said "Tomorrow Woonkamer warms up from 9:00 to be 20.5 °C at 9:00.": the room was at the
# step's target already, so the lead was 0. The E32 has no cooling model yet and plans from the temperature now, so
# that start moves earlier as the room cools; the line says so. A start no morning has judged yet says "(estimate)",
# as the Learning tab does (learned_overview.py warmup_ready and warmup_estimate).
@pytest.mark.asyncio
@pytest.mark.parametrize("language, ready, estimate, plain", [
    ("en", "Tomorrow Woonkamer is warm enough for 20.5 °C at **9:00**; if it cools down before then, the warm-up starts "
           "earlier.",
     "Tomorrow Woonkamer warms up from **6:10** (estimate) to be 20.5 °C at **7:00**.",
     "Tomorrow Woonkamer warms up from **6:10** to be 20.5 °C at **7:00**."),
    ("nl", "Morgen is Woonkamer warm genoeg voor 20,5 °C om **9:00**; koelt de ruimte voor die tijd af, dan begint het "
           "opwarmen eerder.",
     "Morgen warmt Woonkamer vanaf **6:10** (schatting) op om **7:00** op 20,5 °C te zijn.",
     "Morgen warmt Woonkamer vanaf **6:10** op om **7:00** op 20,5 °C te zijn."),
    ("pl", "Woonkamer: jutro jest dość ciepło na 20,5 °C o **9:00**; jeśli pomieszczenie wcześniej się wychłodzi, "
           "nagrzewanie zacznie się wcześniej.",
     "Woonkamer: jutro nagrzewanie od **6:10** (szacunek), aby o **7:00** było 20,5 °C.",
     "Woonkamer: jutro nagrzewanie od **6:10**, aby o **7:00** było 20,5 °C."),
])
async def test_today_says_warm_enough_and_estimate_in_plain_words(hass, clock, language, ready, estimate, plain):
    config, rooms, hub, fields, flow, board = sketch(hass, language)
    card = today_card(config, language)
    living, start = rooms["woonkamer"], rooms["woonkamer"]["heating_start"]
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    hass.states.async_set(flow["apply_learned"], "on", {})
    first = lambda: render(hass, card).split("\n\n")[0].removeprefix(CLOCK)  # noqa: E731
    # No lead: the start is the step's own time; never "from 9:00 to be ... at 9:00".
    heating_start(hass, start, (5, 9, 0), (5, 9, 0), lead=0)
    assert first() == ready
    heating_start(hass, start, (5, 9, 0), (5, 9, 0), lead=0, estimate=True)
    assert first() == ready
    heating_start(hass, start, (5, 9, 0), (5, 9, 0), lead=None)  # the start alone says it as well
    assert first() == ready
    # No lead but the E32 heats now anyway: warming up now, as before.
    heating_start(hass, start, (4, 14, 40), (4, 15, 0), 21, start_now=True, lead=0)
    assert first() == TEXT[language]["warm_up_now"].replace("{room}", "Woonkamer").replace(
        "{target}", "21").replace("{time}", "15:00")
    # A start no morning has judged yet; one that has (or firmware without "estimate"): the plain line.
    heating_start(hass, start, (5, 6, 10), (5, 7, 0), estimate=True)
    assert first() == estimate
    for judged in (False, None):
        heating_start(hass, start, (5, 6, 10), (5, 7, 0), estimate=judged)
        assert first() == plain, judged
    # Smart warm-up off says so whatever the lead.
    hass.states.async_set(flow["apply_learned"], "off", {})
    heating_start(hass, start, (5, 9, 0), (5, 9, 0), lead=0)
    off = {"en": "(Smart warm-up is off)", "nl": "(Slim opwarmen staat uit)", "pl": "(Inteligentne nagrzewanie wyłączone)"}
    assert first().endswith(off[language] + ".") and "**9:00**" in first()


@pytest.mark.asyncio
async def test_today_says_what_weather_compensation_asks_and_which_line(hass, clock):
    config, rooms, hub, fields, flow, board = sketch(hass)
    card = today_card(config)
    for room in rooms.values():
        hass.states.async_set(room["heating_start"], "unknown", {})
    last = lambda: render(hass, card).removeprefix(WEATHER)  # noqa: E731
    curve(hass, flow["curve"], windows=2)
    assert last() == ("Outside 9 °C: weather compensation asks for 30 °C water, standard line (the learned line follows "
                      "after 6 steady periods, 2 of 6 so far).")
    curve(hass, flow["curve"], flow=41, outdoor=-3.6, source="house", windows=9)
    assert last() == ("Outside -4 °C: weather compensation asks for 41 °C water, line estimated from your house (the "
                      "learned line follows after 6 steady periods, 6 of 6 so far).")
    curve(hass, flow["curve"], source="learned", windows=7)
    assert last() == "Outside 9 °C: weather compensation asks for 30 °C water, line learned for your house."
    # Switched off, it only says what it would ask; no outdoor temperature known: what it asks, from a capital.
    curve(hass, flow["curve"], state="advice")
    assert last() == "Outside 9 °C: weather compensation is off; it would ask for 30 °C water."
    curve(hass, flow["curve"], outdoor=None, windows=None)
    assert last() == ("Weather compensation asks for 30 °C water, standard line (the learned line follows after 6 steady "
                      "periods).")
    curve(hass, flow["curve"], flow=None)
    assert render(hass, card) == ""
    hass.config.language = "nl"
    dutch = today_card(board._dashboard_config(), "nl")
    curve(hass, flow["curve"], source="house", windows=2)
    assert render(hass, dutch).endswith("Buiten 9 °C: weerafhankelijke regeling vraagt 30 °C water, lijn geschat uit je "
                                        "huis (de geleerde lijn volgt na 6 rustige periodes, nu 2 van 6).")
    curve(hass, flow["curve"], state="advice")
    assert render(hass, dutch).endswith("Buiten 9 °C: weerafhankelijke regeling staat uit; die zou 30 °C water vragen.")


@pytest.mark.asyncio
async def test_today_shows_exactly_while_one_of_its_lines_has_a_value(hass, clock):
    """The card and its section share one visibility: a start known for a room that is on, or the curve known. In
    every mix of those states the card shows text when visible and nothing is said while it is hidden."""
    config, rooms, hub, fields, flow, board = sketch(hass)
    section = headed(config, "Today")
    card = section["cards"][1]
    assert section["visibility"] == card["visibility"] and "show_empty" not in card
    assert card["visibility"] == [{"condition": "or", "conditions": [
        *({"condition": "and", "conditions": [known(rooms[key]["heating_start"]),
                                              {"condition": "state", "entity": rooms[key]["state"], "state_not": "inactive"}]}
          for key in ("woonkamer", "badkamer")),
        {"condition": "and", "conditions": [known(flow["curve"])]}]}]
    rng = random.Random(4112026)
    hass.states.async_set(flow["apply_learned"], "on", {})
    for _ in range(60):
        states = {}
        for room in rooms.values():
            states[room["state"]] = rng.choice(["active", "inactive", "unavailable"])
            states[room["heating_start"]] = rng.choice(["planned", "unknown", "unavailable"])
            hass.states.async_set(room["state"], states[room["state"]], {})
            heating_start(hass, room["heating_start"], (5, 6, 10) if states[room["heating_start"]] == "planned" else None,
                          (5, 7, 0) if rng.random() < .8 else None)
            if states[room["heating_start"]] == "unavailable":
                hass.states.async_set(room["heating_start"], "unavailable", {})
            hass.states.async_set(room["warm_on_time"], rng.choice(["-4", "0", "unknown"]), {})
        states[flow["curve"]] = rng.choice(["30", "unknown", "unavailable"])
        curve(hass, flow["curve"], flow=30 if states[flow["curve"]] == "30" else None,
              outdoor=rng.choice([9.2, None]), state=rng.choice(["applied", "advice"]),
              source=rng.choice(["design", "house", "learned", None]), windows=rng.choice([0, 3, None]))
        if states[flow["curve"]] == "unavailable":
            hass.states.async_set(flow["curve"], "unavailable", {})
        text = render(hass, card)
        assert bool(text) == shown(card["visibility"], states), (states, text)
        assert "None" not in text and "{" not in text


@pytest.mark.asyncio
async def test_without_its_sensors_there_is_no_today(hass):
    config, rooms, hub, fields, flow, board = sketch(hass, with_curve=False, with_smart=False)
    for key in ("heating_start", "warm_on_time"):
        for room in rooms.values():
            er.async_get(hass).async_remove(room[key])
    config = board._dashboard_config()
    assert [s["cards"][0].get("heading") for s in overview(config)["sections"]] == [None, "Rooms", "House"]
    assert "row_span" not in overview(config)["sections"][1]  # nothing to stack beside the rooms
    assert _today_section(TEXT["en"], []) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_house_is_home_or_away_the_holiday_planner_and_outside(hass, language):
    config, rooms, hub, fields, flow, board = sketch(hass, language)
    t = TEXT[language]
    section = headed(config, t["house"])
    heading, rows, holiday = section["cards"]
    assert heading == {"type": "heading", "heading": t["house"], "heading_style": "title", "icon": ICONS["house"]}
    select = hub["house_mode"]
    assert rows == {"type": "entities", "visibility": [{"condition": "or", "conditions": [known(select), known("sensor.buiten")]}],
                    "entities": [
        {"type": "conditional", "conditions": [known(select)], "row": {
            "type": "simple-entity", "entity": select, "name": t["home_or_away"], "icon": "mdi:home-account"}},
        {"type": "conditional", "conditions": [known(select)], "row": {
            "type": "button", "name": t["holiday"], "icon": "mdi:calendar-month-outline", "action_name": t["plan"],
            "tap_action": {"action": "navigate", "navigation_path": PLANNER}}},
        {"type": "conditional", "conditions": [known("sensor.buiten")], "row": {"entity": "sensor.buiten", "name": t["outdoor"]}}]}
    # The next holiday under it while one is planned (rc.4), as before.
    assert holiday["type"] == "markdown" and holiday["show_empty"] is False and select in holiday["content"]
    # The section shows while one of its rows does; the old house mode tile is gone (the rows and the house card
    # chip carry the mode).
    assert section["visibility"] == [{"condition": "or", "conditions": [{"condition": "and", "conditions": rows["visibility"]}]}]
    assert not any(card.get("features") for card in view_cards(overview(config)))
    words = {"en": ("Home or away", "Holiday", "Plan", "Outdoor"), "nl": ("Thuis of weg", "Vakantie", "Plannen", "Buiten"),
             "pl": ("W domu czy poza domem", "Urlop", "Zaplanuj", "Na zewnątrz")}[language]
    assert (t["home_or_away"], t["holiday"], t["plan"], t["outdoor"]) == words


@pytest.mark.asyncio
@pytest.mark.parametrize("option, field, metric, expected", [
    ("weather.forecast_home", False, False, "weather.forecast_home"),  # a weather entity has its own row
    (None, True, True, "sensor.boiler_outdoor"),                     # no option: the boiler's own sensor
    (None, False, True, "sensor.hub_outdoor_temperature"),           # an older E32: its hub sensor
    ("light.kitchen", False, False, None),                           # not a temperature: no row
    (None, False, False, None),
])
async def test_outside_is_the_outdoor_temperature_set_else_the_boilers(hass, option, field, metric, expected):
    e, rooms, sensors, hub, fields = installation(hass)
    entities = er.async_get(hass)
    product = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    if field:
        entities.async_get_or_create("sensor", "open_thermostat", "fixture_boiler_fields_v1_outdoor_temperature",
                                     config_entry=e, device_id=product.id, suggested_object_id="boiler_outdoor")
    if metric:
        entities.async_get_or_create("sensor", "open_thermostat", "fixture_hub_outdoor_temperature", config_entry=e,
                                     device_id=product.id, suggested_object_id="hub_outdoor_temperature")
    if option:
        hass.config_entries.async_update_entry(e, options={**e.options, "energy_outdoor_entity": option})
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    house = [s for s in overview(config)["sections"] if s["cards"][0].get("heading") == "House"]
    if expected is None:  # no house mode and no outdoor temperature: no House section at all
        assert house == []
        return
    rows = house[0]["cards"][1]["entities"]
    assert rows == [{"type": "conditional", "conditions": [known(expected)], "row": {"entity": expected, "name": "Outdoor"}}]


@pytest.mark.asyncio
async def test_without_a_house_card_what_it_replaces_heads_the_overview(hass):
    """No heat request and no boiler activity: the rooms that want heat (nothing without its request) and the problem
    with its reasons stand on top, without a heading, only while there is a problem."""
    e, rooms, sensors, hub, fields = installation(hass)
    entities = er.async_get(hass)
    product = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    problem = entities.async_get_or_create("binary_sensor", "open_thermostat", "fixture_hub_heating_problem",
                                           config_entry=e, device_id=product.id,
                                           suggested_object_id="heating_problem").entity_id
    entities.async_remove(hub["heat_request"])
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert HOUSE_CARD_TYPE not in json.dumps(config)
    top = overview(config)["sections"][0]
    on = [{"condition": "state", "entity": problem, "state": "on"}]
    assert [card["type"] for card in top["cards"]] == ["tile", "markdown"] and top["column_span"] == 3
    assert top["visibility"] == [{"condition": "or", "conditions": [{"condition": "and", "conditions": on}] * 2}]
    assert [s["cards"][0].get("heading") for s in overview(config)["sections"][1:]] == ["Rooms"]


def test_every_new_word_is_in_english_dutch_and_polish():
    keys = ("today", "home_or_away", "holiday", "plan", "when_today", "when_tomorrow", "when_date", "warm_up_at",
            "warm_up_estimate", "warm_up_ready", "warm_up_now", "warm_up_from", "warm_up_off", "arrived_late", "arrived_late_one", "arrived_early",
            "arrived_early_one", "arrived_on_time", "weather_outside", "weather_asks", "weather_off", "line_standard",
            "line_house", "line_learned", "line_follows", "line_follows_n")
    for language in ("en", "nl", "pl"):
        assert all(TEXT[language][key].strip() for key in keys), language
    # The glossary's words (docs/UX-GLOSSARY.md): Smart warm-up and Weather compensation by their names.
    assert "Smart warm-up" in TEXT["en"]["warm_up_off"] and "Slim opwarmen" in TEXT["nl"]["warm_up_off"]
    assert "Inteligentne nagrzewanie" in TEXT["pl"]["warm_up_off"]
    assert "weather compensation" in TEXT["en"]["weather_asks"] and "weerafhankelijke regeling" in TEXT["nl"]["weather_asks"]
    assert "kompensacja pogodowa" in TEXT["pl"]["weather_asks"]
    # Polish puts the room's name before a colon, so the sentence fits any name.
    assert all(TEXT["pl"][key].startswith("{room}: ") for key in ("warm_up_at", "warm_up_estimate", "warm_up_ready",
                                                                   "warm_up_now", "warm_up_from", "warm_up_off"))
    # "estimate" in the glossary's words, as the Learning tab says it.
    assert [TEXT[lang]["warm_up_estimate"].count(word) for lang, word in
            (("en", "(estimate)"), ("nl", "(schatting)"), ("pl", "(szacunek)"))] == [1, 1, 1]
    for words in (TEXT["en"], TEXT["nl"], TEXT["pl"]):
        assert not any(term in words[key].lower() for key in keys for term in ("shadow", "setpoint", "flow temperature"))
    assert UNKNOWN == ("unavailable", "unknown")
