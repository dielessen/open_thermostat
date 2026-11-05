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
from types import SimpleNamespace
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


def curve(hass, entity, flow=30, outdoor=9.2, state="applied", source="design", windows=0, base=None, low=None, high=None):
    """"Water temperature by weather compensation": what it asks and the outdoor temperature it uses (°C), whether it
    is on (applied) or advice, where its line comes from and the steady periods seen so far; base: the line's own
    value (E32 rc.5), low and high: the water temperature limits."""
    hass.states.async_set(entity, str(flow) if flow is not None else "unknown", {
        "state": state, "slope": 0.67, "slope_source": source, "windows": windows, "outdoor_c": outdoor,
        "flow_c": flow, "base_c": base, "minimum_flow_c": low, "maximum_flow_c": high, "unit_of_measurement": "°C"})


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
    ("en", CLOCK + "Tomorrow Woonkamer warms up from **06:10** to be 20.5 °C at **07:00**. Yesterday it was warm 4 minutes "
           "early.\n\n" + WEATHER + "Outdoor 9.2 °C: weather compensation asks for 30 °C water, standard line (the learned "
           "line follows after 6 steady periods)."),
    ("nl", CLOCK + "Morgen begint Woonkamer om **06:10** met opwarmen, zodat het om **07:00** 20,5 °C is. Gisteren was het "
           "4 minuten te vroeg warm.\n\n" + WEATHER + "Buiten 9,2 °C: de weerafhankelijke regeling vraagt 30 °C water, "
           "standaardlijn (de geleerde lijn volgt na 6 rustige periodes)."),
    ("pl", CLOCK + "Woonkamer: jutro nagrzewanie od **06:10**, aby o **07:00** było 20,5 °C. Wczoraj ciepło 4 min za "
           "wcześnie.\n\n" + WEATHER + "Na zewnątrz 9,2 °C: kompensacja pogodowa żąda 30 °C wody, linia standardowa "
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
    hass.states.async_set(hub["heat_request"], "36", {"mode": "active"})  # a room asks for heat
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
    assert first() == "On 7 Nov Woonkamer warms up from **06:10** to be 19.5 °C at **07:00**."
    heating_start(hass, start, (4, 14, 5), (4, 15, 0), 21)
    assert first() == "Woonkamer is warming up now to be 21 °C at **15:00**."
    heating_start(hass, start, (4, 14, 40), (4, 15, 0), 21, start_now=True)
    assert first() == "Woonkamer is warming up now to be 21 °C at **15:00**."
    # Smart warm-up off: heating starts at the program time, and the line says why.
    hass.states.async_set(flow["apply_learned"], "off", {})
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    assert first() == "Tomorrow Woonkamer starts heating at **07:00** for 20.5 °C (Smart warm-up is off)."
    # The switch unavailable (the E32 not heard): on by default, as on the E32.
    hass.states.async_set(flow["apply_learned"], "unavailable", {})
    assert first() == "Tomorrow Woonkamer warms up from **06:10** to be 20.5 °C at **07:00**."
    # An older E32 without the program step: the start alone.
    hass.states.async_set(flow["apply_learned"], "on", {})
    heating_start(hass, start, (5, 6, 10))
    assert first() == "Tomorrow Woonkamer starts warming up at **06:10**."
    # Yesterday: late, a minute either way, on time; nothing while the scoreboard has no figure.
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    for minutes, said in (("12", " Yesterday it was warm 12 minutes late."), ("1", " Yesterday it was warm 1 minute late."),
                          ("-1", " Yesterday it was warm 1 minute early."), ("0.4", " Yesterday it was warm on time."),
                          ("unknown", "")):
        hass.states.async_set(warm, minutes, {})
        assert first() == "Tomorrow Woonkamer warms up from **06:10** to be 20.5 °C at **07:00**." + said, minutes
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
        "Morgen begint Woonkamer om **06:10** met opwarmen, zodat het om **07:00** 20,5 °C is. Gisteren was het 3 minuten "
        "te laat warm.")
    heating_start(hass, start, (7, 6, 10), (7, 7, 0), 21)
    assert "Op 7 nov begint Woonkamer om **06:10** met opwarmen, zodat het om **07:00** 21 °C is." in render(hass, dutch)
    hass.config.language = "pl"
    polish = today_card(board._dashboard_config(), "pl")
    hass.states.async_set(flow["apply_learned"], "off", {})
    assert ("Woonkamer: 7 lis grzanie od **07:00**, temperatura docelowa 21 °C (Inteligentne nagrzewanie wyłączone). "
            "Wczoraj ciepło 3 min za późno.") in render(hass, polish)


# rc7: the sentences review (R1). Each case is one the reviewer worked out from the firmware; the three languages say
# each of them.
TODAY_CASES = {
    # R1-5: the E32 heats now, but cannot reach the target in time.
    "late": ("Woonkamer is warming up now; 21 °C may come a little after **15:00**.",
             "Woonkamer warmt nu op; 21 °C wordt misschien pas iets na **15:00** gehaald.",
             "Woonkamer: nagrzewanie trwa; 21 °C może być dopiero nieco po **15:00**."),
    # rc7 (the E32 page's words): heating now on a start no morning has judged yet.
    "now_estimate": ("Woonkamer is warming up now (estimate) to be 21 °C at **15:00**.",
                     "Woonkamer warmt nu op (schatting), zodat het om **15:00** 21 °C is.",
                     "Woonkamer: nagrzewanie trwa (szacunek), aby o **15:00** było 21 °C."),
    # R1-3: the trial run: the E32 heats nothing early.
    "trial": ("Tomorrow Woonkamer would warm up from **06:10** to be 20.5 °C at **07:00** (trial run).",
              "Morgen zou Woonkamer om **06:10** met opwarmen beginnen, zodat het om **07:00** 20,5 °C is (proefperiode).",
              "Woonkamer: jutro nagrzewanie byłoby od **06:10**, aby o **07:00** było 20,5 °C (okres próbny)."),
    "trial_now": ("Woonkamer would be warming up now to be 21 °C at **15:00** (trial run).",
                  "Woonkamer zou nu opwarmen, zodat het om **15:00** 21 °C is (proefperiode).",
                  "Woonkamer: nagrzewanie trwałoby teraz, aby o **15:00** było 21 °C (okres próbny)."),
    # R1-10: the program step on the day after the start.
    "next_day": ("Today Woonkamer warms up from **23:30** to be 20 °C at **00:30 tomorrow**.",
                 "Vandaag begint Woonkamer om **23:30** met opwarmen, zodat het om **00:30 morgen** 20 °C is.",
                 "Woonkamer: dziś nagrzewanie od **23:30**, aby o **00:30 jutro** było 20 °C."),
    # R1-1: away, nobody home, an open window, a holiday: the E32 holds the program (no early start).
    "away": ("Woonkamer is set to away: no early warm-up.", "Woonkamer staat op afwezig: niet eerder opwarmen.",
             "Woonkamer: tryb nieobecności, bez wcześniejszego nagrzewania."),
    "house_away": ("Nobody is home for Woonkamer: no early warm-up.", "Niemand is thuis voor Woonkamer: niet eerder opwarmen.",
                   "Woonkamer: nikogo nie ma w domu, bez wcześniejszego nagrzewania."),
    "window_open": ("Woonkamer is paused: a window or door is open.",
                    "Woonkamer is gepauzeerd: er staat een raam of deur open.",
                    "Woonkamer: wstrzymane, otwarte okno lub drzwi."),
    "holiday": ("Woonkamer is on holiday until 9 Nov; it is warm again when you are back.",
                "Woonkamer is met vakantie tot 9 nov; bij thuiskomst is het weer warm.",
                "Woonkamer: urlop do 9 lis; po powrocie będzie ciepło."),
    "away_return": ("Woonkamer is warming up for your return.", "Woonkamer warmt op voor je thuiskomst.",
                    "Woonkamer: nagrzewanie na Twój powrót."),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
@pytest.mark.parametrize("case", list(TODAY_CASES))
async def test_today_says_the_reviewed_cases_in_every_language(hass, clock, language, case):
    config, rooms, hub, fields, flow, board = sketch(hass, language)
    card = today_card(config, language)
    living, start = rooms["woonkamer"], rooms["woonkamer"]["heating_start"]
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    hass.states.async_set(flow["apply_learned"], "on", {})
    hass.states.async_set(hub["heat_request"], "36", {"mode": "shadow" if case.startswith("trial") else "active"})
    hass.states.async_set(living["reason"], "warm_enough", {})
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    if case in ("late", "now_estimate", "trial_now"):
        heating_start(hass, start, (4, 14, 40), (4, 15, 0), 21, start_now=True)
        attributes = dict(hass.states.get(start).attributes)
        attributes.update({"late": {"reachable": False}, "now_estimate": {"estimate": True}}.get(case, {}))
        hass.states.async_set(start, hass.states.get(start).state, attributes)
    elif case == "next_day":
        heating_start(hass, start, (4, 23, 30), (5, 0, 30), 20)
    elif case == "holiday":
        hass.states.async_set(living["reason"], "holiday", {"values": {"until": local(9, 0, 0), "target": 15}})
    elif case in ("away", "house_away", "window_open", "away_return"):
        hass.states.async_set(living["reason"], case, {})
    said = render(hass, card).split("\n\n")[0].removeprefix(CLOCK)
    assert said == TODAY_CASES[case][("en", "nl", "pl").index(language)]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
async def test_a_free_heat_morning_is_on_time_on_today(hass, clock, language):
    """R4-2: with free heat the sensor's reachable is None (the E32's flag is for the earlier start without it), and
    None is not "not reachable": Today says the later start and then "warming up now", never "may come a little
    after"."""
    config, rooms, hub, fields, flow, board = sketch(hass, language)
    card = today_card(config, language)
    living, start = rooms["woonkamer"], rooms["woonkamer"]["heating_start"]
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    hass.states.async_set(flow["apply_learned"], "on", {})
    hass.states.async_set(hub["heat_request"], "36", {"mode": "active"})
    hass.states.async_set(living["reason"], "warm_enough", {})
    first = lambda: render(hass, card).split("\n\n")[0].removeprefix(CLOCK)  # noqa: E731
    for at, start_now in (((4, 16, 10), False), ((4, 14, 20), True)):
        heating_start(hass, start, at, (4, 17, 0) if not start_now else (4, 15, 0), 21, start_now=start_now)
        attributes = {**hass.states.get(start).attributes, "reachable": None, "free_heat_min": 20}
        hass.states.async_set(start, hass.states.get(start).state, attributes)
        said = first()
        assert said == {
            ("en", False): "Today Woonkamer warms up from **16:10** to be 21 °C at **17:00**.",
            ("en", True): "Woonkamer is warming up now to be 21 °C at **15:00**.",
            ("nl", False): "Vandaag begint Woonkamer om **16:10** met opwarmen, zodat het om **17:00** 21 °C is.",
            ("nl", True): "Woonkamer warmt nu op, zodat het om **15:00** 21 °C is.",
            ("pl", False): "Woonkamer: dziś nagrzewanie od **16:10**, aby o **17:00** było 21 °C.",
            ("pl", True): "Woonkamer: nagrzewanie trwa, aby o **15:00** było 21 °C.",
        }[language, start_now]
        assert said != TODAY_CASES["late"][("en", "nl", "pl").index(language)]


@pytest.mark.asyncio
async def test_today_says_would_before_the_takeover_and_held_behind_hot_water(hass, clock):
    """R4-13: before the takeover is confirmed (control awaiting_confirmation) the E32 heats nothing early, as in the
    trial run: "would". A Reason that ranks above away or a holiday (hot water, a boiler pause, no measurement) still
    holds the program: its comfort_mode says so, and Today says the away line, not a warm-up."""
    config, rooms, hub, fields, flow, board = sketch(hass)
    card = today_card(config)
    living, start = rooms["woonkamer"], rooms["woonkamer"]["heating_start"]
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    hass.states.async_set(flow["apply_learned"], "on", {})
    hass.states.async_set(living["reason"], "warm_enough", {})
    heating_start(hass, start, (5, 6, 10), (5, 7, 0))
    first = lambda: render(hass, card).split("\n\n")[0].removeprefix(CLOCK)  # noqa: E731
    hass.states.async_set(hub["heat_request"], "0", {"mode": "active", "control": "awaiting_confirmation"})
    assert first() == TODAY_CASES["trial"][0]
    hass.states.async_set(hub["heat_request"], "36", {"mode": "active", "control": "active"})
    assert first() == "Tomorrow Woonkamer warms up from **06:10** to be 20.5 °C at **07:00**."
    for comfort, until, said in (("away", local(9, 0, 0), TODAY_CASES["holiday"][0]), ("away", None, TODAY_CASES["away"][0]),
                                 ("presence_away", None, TODAY_CASES["house_away"][0]),
                                 ("window_open", None, TODAY_CASES["window_open"][0])):
        for why in ("hot_water", "boiler_pause", "no_measurement"):
            hass.states.async_set(living["reason"], why, {"values": {}, "comfort_mode": comfort, "comfort_until": until})
            assert first() == said, (comfort, why)
    hass.states.async_set(living["reason"], "hot_water", {"values": {}, "comfort_mode": "program", "comfort_until": None})
    assert first() == "Tomorrow Woonkamer warms up from **06:10** to be 20.5 °C at **07:00**."


LAST_WARM_UP = {
    # R1-6: 3 hours or more is the E32's "never warm" (it counts 3 hours).
    ("180", None, None): ("Yesterday it did not get warm within 3 hours.", "Gisteren werd het binnen 3 uur niet warm.",
                          "Wczoraj nie zrobiło się ciepło w ciągu 3 godzin."),
    # R1-24: an hour or more in hours and minutes.
    ("95", None, None): ("Yesterday it was warm 1 h 35 min late.", "Gisteren was het 1 u 35 min te laat warm.",
                         "Wczoraj ciepło 1 godz. 35 min za późno."),
    ("-60", None, None): ("Yesterday it was warm 1 h early.", "Gisteren was het 1 u te vroeg warm.",
                          "Wczoraj ciepło 1 godz. za wcześnie."),
    # R1-7: once today's warm-up is judged, today's figure.
    ("-4", 2, None): ("Today it was warm 2 minutes late.", "Vandaag was het 2 minuten te laat warm.",
                      "Dziś ciepło 2 min za późno."),
    # R1-27: the E32's last scored day is an older one (a day without a trusted clock).
    ("-4", None, "2026-11-01"): ("On 1 Nov it was warm 4 minutes early.", "Op 1 nov was het 4 minuten te vroeg warm.",
                                 "Dnia 1 lis ciepło 4 min za wcześnie."),
    ("-4", None, "2026-11-03"): ("Yesterday it was warm 4 minutes early.", "Gisteren was het 4 minuten te vroeg warm.",
                                 "Wczoraj ciepło 4 min za wcześnie."),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "nl", "pl"])
@pytest.mark.parametrize("figures", list(LAST_WARM_UP))
async def test_today_says_how_the_last_warm_up_went(hass, clock, language, figures):
    config, rooms, hub, fields, flow, board = sketch(hass, language)
    card = today_card(config, language)
    living = rooms["woonkamer"]
    hass.states.async_set(living["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    hass.states.async_set(flow["apply_learned"], "on", {})
    heating_start(hass, living["heating_start"], (5, 6, 10), (5, 7, 0))
    state, today, day = figures
    hass.states.async_set(living["warm_on_time"], state, {"today": today, **({"day": day} if day else {})})
    said = render(hass, card).split("\n\n")[0]
    assert said.endswith(". " + LAST_WARM_UP[figures][("en", "nl", "pl").index(language)]), said


def with_learning(hass, board, rooms, hub):
    """The fixture house with what the Rooms view's learning area needs: each room's learning sensor and the learned
    overview; the dashboard rebuilt."""
    entry = hass.config_entries.async_get_entry(board.entry_id)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    for room_id in rooms:
        device = devices.async_get_device_by_identifier(("open_thermostat", f"fixture_e32_room_{room_id}"), entry.entry_id)
        rooms[room_id]["learning"] = entities.async_get_or_create(
            "sensor", "open_thermostat", f"fixture_e32_room_{room_id}_learning", config_entry=entry, device_id=device.id,
            suggested_object_id=f"{room_id}_learning").entity_id
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), entry.entry_id)
    hub["learned_overview"] = entities.async_get_or_create(
        "sensor", "open_thermostat", "fixture_hub_learned_overview", config_entry=entry, device_id=product.id,
        suggested_object_id="learned_overview").entity_id
    return board._dashboard_config()


@pytest.mark.asyncio
async def test_a_room_renamed_in_home_assistant_keeps_its_learned_lines(hass, clock):
    """R1-13: the learned lines are found by the room's ID, and every text names the room as Home Assistant does."""
    from custom_components.open_thermostat import learned_overview as lo
    config, rooms, hub, fields, flow, board = sketch(hass)
    devices = dr.async_get(hass)
    entry_id = board.entry_id
    device = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), entry_id)
    devices.async_update_device(device.id, name_by_user="Living room with a rather long name")
    config = with_learning(hass, board, rooms, hub)
    lines = [card for section in config["views"][1]["sections"] for card in section["cards"]
             if card.get("type") == "markdown" and "'rooms'" in card.get("content", "")]
    assert lines and all("selectattr('room_id', 'eq', " in card["content"] for card in lines)
    assert any("\"woonkamer\"" in card["content"] for card in lines) and not any("names" in card["content"] for card in lines)
    hass.states.async_set(rooms["woonkamer"]["state"], "active", {})
    hass.states.async_set(rooms["badkamer"]["state"], "inactive", {})
    heating_start(hass, rooms["woonkamer"]["heating_start"], (5, 6, 10), (5, 7, 0))
    assert render(hass, today_card(config)).startswith(CLOCK + "Tomorrow Living room with a rather long name warms up ")
    # The learned overview names the room the same way and gives its ID.
    heating_hub = hass.data["open_thermostat"][entry_id]["heating_hub"]
    heating_hub.update_learned("woonkamer", ({"id": "woonkamer", "readiness": "learning", "segments": 2}, None))
    sensor = lo.LearnedOverviewSensor(SimpleNamespace(entry_id=entry_id), heating_hub, clock=str)
    sensor.hass = hass
    room = next(room for room in sensor.extra_state_attributes["rooms"] if room["room_id"] == "woonkamer")
    assert room["name"] == "Living room with a rather long name"


@pytest.mark.asyncio
async def test_the_smart_warm_up_start_tile_shows_only_while_smart_warm_up_uses_it(hass):
    """R1-4: named after the sensor, hidden while Smart warm-up is off and while the room is away or paused."""
    config, rooms, hub, fields, flow, board = sketch(hass)
    config = with_learning(hass, board, rooms, hub)
    tiles = [card for section in config["views"][1]["sections"] for card in section["cards"]
             if card.get("type") == "tile" and card.get("entity") == rooms["woonkamer"]["heating_start"]]
    assert len(tiles) == 1 and tiles[0]["name"] == "Smart warm-up start"
    conditions = tiles[0]["visibility"]
    assert {"condition": "state", "entity": flow["apply_learned"], "state_not": "off"} in conditions
    assert {"condition": "state", "entity": rooms["woonkamer"]["reason"],
            "state_not": ["holiday", "away", "room_away", "house_away", "away_return", "window_open"]} in conditions
    assert (TEXT["nl"]["heating_start"], TEXT["pl"]["heating_start"]) == ("Start slim opwarmen",
                                                                          "Start inteligentnego nagrzewania")


# rc7: the owner's card said "Tomorrow Woonkamer warms up from 9:00 to be 20.5 °C at 9:00.": the room was at the
# step's target already, so the lead was 0. The E32 has no cooling model yet and plans from the temperature now, so
# that start moves earlier as the room cools; the line says so. A start no morning has judged yet says "(estimate)",
# as the Learning tab does (learned_overview.py warmup_ready and warmup_estimate).
@pytest.mark.asyncio
@pytest.mark.parametrize("language, ready, estimate, plain", [
    ("en", "Tomorrow Woonkamer is warm enough for 20.5 °C at **09:00**; if it cools down before then, the warm-up "
           "starts earlier.",
     "Tomorrow Woonkamer warms up from **06:10** (estimate) to be 20.5 °C at **07:00**.",
     "Tomorrow Woonkamer warms up from **06:10** to be 20.5 °C at **07:00**."),
    ("nl", "Morgen is Woonkamer warm genoeg voor 20,5 °C om **09:00**; koelt de ruimte voor die tijd af, dan begint het "
           "opwarmen eerder.",
     "Morgen begint Woonkamer om **06:10** (schatting) met opwarmen, zodat het om **07:00** 20,5 °C is.",
     "Morgen begint Woonkamer om **06:10** met opwarmen, zodat het om **07:00** 20,5 °C is."),
    ("pl", "Woonkamer: jutro jest dość ciepło na 20,5 °C o **09:00**; jeśli pomieszczenie wcześniej się wychłodzi, "
           "nagrzewanie zacznie się wcześniej.",
     "Woonkamer: jutro nagrzewanie od **06:10** (szacunek), aby o **07:00** było 20,5 °C.",
     "Woonkamer: jutro nagrzewanie od **06:10**, aby o **07:00** było 20,5 °C."),
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
    assert first().endswith(off[language] + ".") and "**09:00**" in first()


@pytest.mark.asyncio
async def test_today_says_what_weather_compensation_asks_and_which_line(hass, clock):
    config, rooms, hub, fields, flow, board = sketch(hass)
    card = today_card(config)
    for room in rooms.values():
        hass.states.async_set(room["heating_start"], "unknown", {})
    hass.states.async_set(hub["heat_request"], "36", {"mode": "active"})
    last = lambda: render(hass, card).removeprefix(WEATHER)  # noqa: E731
    curve(hass, flow["curve"], windows=2)
    assert last() == ("Outdoor 9.2 °C: weather compensation asks for 30 °C water, standard line (the learned line follows "
                      "after 6 steady periods, 2 of 6 so far).")
    # A line worked out from the house until 6 steady periods (the E32 uses the learned one from then on); a true minus.
    curve(hass, flow["curve"], flow=41, outdoor=-3.64, source="house", windows=5)
    assert last() == ("Outdoor −3.6 °C: weather compensation asks for 41 °C water, line estimated from your house (the "
                      "learned line follows after 6 steady periods, 5 of 6 so far).")
    curve(hass, flow["curve"], source="learned", windows=7)
    assert last() == "Outdoor 9.2 °C: weather compensation asks for 30 °C water, line learned for your house."
    # Six or more without the learned line (a moment's race in one summary): never "6 of 6 so far".
    curve(hass, flow["curve"], windows=6)
    assert last() == ("Outdoor 9.2 °C: weather compensation asks for 30 °C water, standard line (the learned line follows "
                      "after 6 steady periods).")
    # Switched off, it only says what it would ask; no outdoor temperature known: what it asks, from a capital.
    curve(hass, flow["curve"], state="advice")
    assert last() == "Outdoor 9.2 °C: weather compensation is off; it would ask for 30 °C water."
    curve(hass, flow["curve"], outdoor=None, windows=None)
    assert last() == ("Weather compensation asks for 30 °C water, standard line (the learned line follows after 6 steady "
                      "periods).")
    curve(hass, flow["curve"], flow=None)
    assert render(hass, card) == ""
    # Integrator's finding 1: the line gives 37 °C and the room correction adds the rest; never 42 °C "from the line".
    curve(hass, flow["curve"], flow=42, outdoor=1.8, source="learned", windows=9, base=36.4, low=25, high=60)
    assert last() == ("Outdoor 1.8 °C: weather compensation asks for 42 °C water, line learned for your house (the line "
                      "gives 37 °C, the room correction adds 5 °C).")
    # Held at the lowest water temperature: what the line gives, nothing ascribed to the room correction.
    curve(hass, flow["curve"], flow=25, outdoor=14, source="learned", windows=9, base=22.3, low=25, high=60)
    assert last() == ("Outdoor 14.0 °C: weather compensation asks for 25 °C water, line learned for your house (the line "
                      "gives 23 °C).")
    # R1-9: no room asks for heat: nothing is sent now.
    hass.states.async_set(hub["heat_request"], "0", {"mode": "active"})
    curve(hass, flow["curve"], flow=25, outdoor=14, source="learned", windows=9, base=24.6)
    assert last() == ("Outdoor 14.0 °C: when a room asks for heat, weather compensation sends 25 °C water, line learned for "
                      "your house.")
    hass.config.language = "nl"
    dutch = today_card(board._dashboard_config(), "nl")
    curve(hass, flow["curve"], source="house", windows=2)
    assert render(hass, dutch).endswith("Buiten 9,2 °C: als een ruimte warmte vraagt, stuurt de weerafhankelijke regeling "
                                        "water van 30 °C, lijn geschat uit je huis (de geleerde lijn volgt na 6 rustige "
                                        "periodes, nu 2 van 6).")
    hass.states.async_set(hub["heat_request"], "36", {"mode": "active"})
    curve(hass, flow["curve"], flow=42, outdoor=1.8, source="learned", windows=9, base=36.4, low=25, high=60)
    assert render(hass, dutch).endswith("Buiten 1,8 °C: de weerafhankelijke regeling vraagt 42 °C water, lijn geleerd voor "
                                        "je huis (de lijn geeft 37 °C, de ruimtecorrectie doet er 5 °C bij).")
    curve(hass, flow["curve"], state="advice")
    assert render(hass, dutch).endswith("Buiten 9,2 °C: de weerafhankelijke regeling staat uit; die zou 30 °C water vragen.")
    hass.config.language = "pl"
    polish = today_card(board._dashboard_config(), "pl")
    curve(hass, flow["curve"], flow=42, outdoor=-1.8, source="learned", windows=9, base=36.4, low=25, high=60)
    assert render(hass, polish).endswith("Na zewnątrz −1,8 °C: kompensacja pogodowa żąda 42 °C wody, linia wyuczona dla "
                                         "Twojego domu (linia daje 37 °C, korekta pomieszczenia dodaje 5 °C).")


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
    heading, rows, holiday, hint = section["cards"]
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
    # Where to plan one (the Holiday row's "Plan" opens the integration's page, not the planner itself): R1-28.
    assert hint == {"type": "markdown", "content": t["holiday_hint"], "visibility": [known(select)]}
    assert t["holiday_hint"] == {"en": "To plan a holiday: Configure → House → House mode and holiday.",
                                 "nl": "Vakantie plannen: Configureren → Huis → Huismodus en vakantie.",
                                 "pl": "Aby zaplanować urlop: Konfiguruj → Dom → Tryb domu i urlop."}[language]
    # The section shows while one of its rows does; the old house mode tile is gone (the rows and the house card
    # chip carry the mode).
    assert section["visibility"] == [{"condition": "or", "conditions": [
        {"condition": "and", "conditions": rows["visibility"]}, {"condition": "and", "conditions": [known(select)]}]}]
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
@pytest.mark.parametrize("used, expected", [("boiler", "sensor.boiler_outdoor"), ("ha", "sensor.buiten"),
                                            (None, "sensor.buiten")])
async def test_outside_is_the_outdoor_temperature_the_e32_uses(hass, used, expected):
    """R1-8: the House row shows the outdoor temperature the E32 uses (its learner's input, as Today and the curve),
    not the Home Assistant sensor beside the boiler's while the E32 takes the boiler's."""
    e, rooms, sensors, hub, fields = installation(hass)
    entities = er.async_get(hass)
    product = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    entities.async_get_or_create("sensor", "open_thermostat", "fixture_boiler_fields_v1_outdoor_temperature",
                                 config_entry=e, device_id=product.id, suggested_object_id="boiler_outdoor")
    hass.config_entries.async_update_entry(e, options={**e.options, "energy_outdoor_entity": "sensor.buiten"})
    heating = hass.data["open_thermostat"][e.entry_id]["heating_hub"]
    heating.summary = {"schema": 1, "learned": {"schema": 1, "inputs": {"outdoor": used}}} if used else None
    board = RoomDashboard(hass, "fixture", e.entry_id)
    config = board._dashboard_config()
    house = next(s for s in overview(config)["sections"] if s["cards"][0].get("heading") == "House")
    assert house["cards"][1]["entities"][-1]["row"] == {"entity": expected, "name": "Outdoor"}
    # A change of source rebuilds the dashboard (it is part of its signature).
    signature = board._signature(heating)
    heating.summary = {"schema": 1, "learned": {"schema": 1, "inputs": {"outdoor": "ha" if used == "boiler" else "boiler"}}}
    assert board._signature(heating) != signature


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


@pytest.mark.asyncio
async def test_the_latest_change_is_one_it_made_and_dates_read_as_on_the_rest_of_the_dashboard(hass, clock):
    """R1-16 and the integrator's 3: "Latest change" is a change the thermostat made (with a time), never a trial-run
    proposal, and nothing while it changed nothing (the section below says that once). R1-25: "5 Nov: ...", not
    "05-11". The integrator's 5: a learned room says in a few words how fast it warms."""
    from custom_components.open_thermostat.dashboard import _learned_sections
    entity = "sensor.what_the_thermostat_learned"
    summary, house, changes = (s["cards"][1] for s in _learned_sections(TEXT["en"], entity))
    proposal = {"time": None, "text": "Would set “Burner rest between starts” to 10 min, because the burner started 25 "
                                      "times yesterday."}
    made = {"time": "2026-11-05T00:00:00+00:00", "text": "Woonkamer got 0.6 °C warmer than its target; ..."}
    rooms = [{"name": "Woonkamer", "room_id": "woonkamer", "progress": "Learned",
              "summary": "warms about 1 °C in 1 h 15 min with water of 40 °C", "lines": []},
             {"name": "Badkamer", "room_id": "badkamer", "progress": "Learning: 3 of 6 warm-ups seen", "summary": None,
              "lines": []}]
    hass.states.async_set(entity, "x", {"explanation": "One. Two.", "rooms": rooms, "changes": [proposal, made]})
    text = render(hass, summary)
    assert ("- **Woonkamer** · Learned · warms about 1 °C in 1 h 15 min with water of 40 °C\n"
            "- **Badkamer** · Learning: 3 of 6 warm-ups seen\n") in text
    assert text.endswith("*Latest change:* Woonkamer got 0.6 °C warmer than its target; ...")
    assert render(hass, changes) == "- " + proposal["text"] + "\n- 5 Nov: " + made["text"]
    nothing = {"time": None, "text": "Nothing changed yet: the start values still fit, or there is not enough to go on."}
    hass.states.async_set(entity, "x", {"explanation": "One.", "rooms": [], "changes": [nothing]})
    assert "Latest change" not in render(hass, summary) and render(hass, changes) == "- " + nothing["text"]
    hass.config.language = "nl"
    dutch = _learned_sections(TEXT["nl"], entity)[2]["cards"][1]
    hass.states.async_set(entity, "x", {"explanation": "Een.", "rooms": [], "changes": [made]})
    assert render(hass, dutch) == "- 5 nov: " + made["text"]


@pytest.mark.asyncio
async def test_short_cycling_in_the_trial_run_is_the_thermostat_in_charge(hass):
    """R1-17: in the trial run the E32 sends nothing, so it does not lengthen anything yet."""
    config, rooms, hub, fields, flow, board = sketch(hass)
    card = board._cycling_card(TEXT["en"], hub["burner_short_cycling"], hub["heat_request"])
    hass.states.async_set(hub["burner_short_cycling"], "on", {})
    hass.states.async_set(hub["heat_request"], "0", {"mode": "shadow"})
    assert render(hass, card).endswith("Your current thermostat lets the burner switch on and off often; the E32 will "
                                       "lengthen the rest once it controls the boiler.")
    hass.states.async_set(hub["heat_request"], "40", {"mode": "active"})
    assert render(hass, card).endswith("The E32 lengthens the burner rest step by step.")
    assert TEXT["nl"]["cycling_info_shadow"].startswith("Je huidige thermostaat") and TEXT["pl"]["cycling_info_shadow"]
