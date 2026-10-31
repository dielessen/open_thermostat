"""The visual week planner of E32 rooms: planner week -> schedule -> E32 room plan, and back as program text."""
from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import Unauthorized

from custom_components.open_thermostat import e32_week
from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.e32_room_flow import E32RoomFlow, format_program, parse_program
from custom_components.open_thermostat.e32_week import WeekError, read_week, save_week, valid_schedule
from test_e32_room_flow import product
from test_room_plan import FakeE32, other_side
from test_v1_native import room

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "ha/config/custom_components/open_thermostat/frontend"
COMFORT, AWAY, NIGHT = 2050, 1800, 1650
# The planner's "Workdays and weekend" template (week-editor.js TEMPLATES.work) with these levels.
WORK = [[390, COMFORT], [510, AWAY], [1020, COMFORT], [1350, NIGHT]]
FREE = [[480, COMFORT], [1380, NIGHT]]
WEEK = [WORK] * 5 + [FREE] * 2
TEXT_EN = ("mon-fri: 06:30 20.5; 08:30 18; 17:00 20.5; 22:30 16.5\n"
           "sat-sun: 08:00 20.5; 23:00 16.5")


def woonkamer(e32):
    return next(r for r in e32.plan["rooms"] if r["id"] == "woonkamer")


@pytest.mark.asyncio
async def test_a_planner_week_is_stored_in_the_room_plan_and_reads_back_as_the_same_program_text(hass):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    loaded = await read_week(hass, parent.entry_id)
    assert loaded["revision"] == 4
    assert loaded["rooms"][0] == {"id": "woonkamer", "name": "Woonkamer", "minimum_centi_c": 1000, "maximum_centi_c": 2400,
                                  "fallback_centi_c": 2000, "setpoint_entity": "climate.woonkamer", "schedule": None}
    before = deepcopy(e32.plan)
    result = await save_week(hass, parent.entry_id, "woonkamer", deepcopy(WEEK), None)
    # Only the one room's schedule changed; the E32 confirmed the new revision.
    assert woonkamer(e32)["schedule"] == WEEK and e32.plan["revision"] == 5
    stored = deepcopy(e32.plan)
    del next(r for r in stored["rooms"] if r["id"] == "woonkamer")["schedule"]
    assert {**stored, "revision": 4} == before
    assert result["rooms"][0]["schedule"] == WEEK
    # The options flow's advanced text view shows exactly this program and keeps it on an unchanged save.
    assert format_program(WEEK) == TEXT_EN
    assert format_program(WEEK, "nl") == TEXT_EN.replace("mon-fri", "ma-vr").replace("sat-sun", "za-zo").replace(".5", ",5")
    assert parse_program(TEXT_EN, 1000, 2400) == WEEK
    flow = E32RoomFlow()
    flow.hass = hass
    flow.config_entry = parent  # the form also lists the room's window/door contacts
    assert flow._e32_defaults(woonkamer(e32))["program"] == TEXT_EN  # the e32_room form's program field
    # And a program typed in the text view comes back to the planner unchanged.
    assert (await read_week(hass, parent.entry_id))["rooms"][0]["schedule"] == WEEK


@pytest.mark.asyncio
async def test_a_program_changed_elsewhere_since_loading_is_never_overwritten(hass):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    woonkamer(e32)["schedule"] = [[[420, 2000]]] + [[]] * 6
    posts = len(e32.posts)
    with pytest.raises(WeekError, match="week_changed"):
        await save_week(hass, parent.entry_id, "woonkamer", deepcopy(WEEK), None)
    assert len(e32.posts) == posts and woonkamer(e32)["schedule"] == [[[420, 2000]]] + [[]] * 6
    # A change to another room between the read and the write is kept (one re-read on 409).
    e32.before_save.append(other_side("name", "Bad"))
    await save_week(hass, parent.entry_id, "woonkamer", deepcopy(WEEK), [[[420, 2000]]] + [[]] * 6)
    assert woonkamer(e32)["schedule"] == WEEK
    assert next(r for r in e32.plan["rooms"] if r["id"] == "badkamer")["name"] == "Bad"
    # The program edited at the same time on the E32 page: the planner's save is refused after the re-read.
    e32.before_save.append(other_side("schedule", [[[360, 1900]]] * 7, room="woonkamer"))
    with pytest.raises(WeekError, match="week_changed"):
        await save_week(hass, parent.entry_id, "woonkamer", [[[420, 2100]]] * 7, WEEK)
    assert woonkamer(e32)["schedule"] == [[[360, 1900]]] * 7


@pytest.mark.asyncio
async def test_removing_the_program_leaves_the_fallback_and_invalid_programs_are_refused_before_sending(hass):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    await save_week(hass, parent.entry_id, "woonkamer", deepcopy(WEEK), None)
    result = await save_week(hass, parent.entry_id, "woonkamer", [[]] * 7, WEEK)
    assert "schedule" not in woonkamer(e32) and result["rooms"][0]["schedule"] is None
    posts = len(e32.posts)
    for schedule, code in (([[[m * 60, 2000] for m in range(7)]] + [[]] * 6, "invalid_schedule"),
                           ([[[480, 2000], [480, 1800]]] + [[]] * 6, "invalid_schedule"),
                           ([[[1440, 2000]]] + [[]] * 6, "invalid_schedule"),
                           ([[[480, 2000.0]]] + [[]] * 6, "invalid_schedule"),
                           ([[[480, 2000]]] * 6, "invalid_schedule"),
                           ([[[480, 2500]]] + [[]] * 6, "invalid_schedule_limits")):
        with pytest.raises(WeekError, match=code):
            await save_week(hass, parent.entry_id, "woonkamer", schedule, None)
    assert len(e32.posts) == posts
    with pytest.raises(WeekError, match="room_missing"):
        await save_week(hass, parent.entry_id, "zolder", deepcopy(WEEK), None)
    with pytest.raises(WeekError, match="unavailable"):
        await read_week(hass, "no-such-entry")
    assert valid_schedule(None, 500, 3000) is None and valid_schedule([[]] * 7, 500, 3000) is None


@pytest.mark.asyncio
async def test_websocket_commands_are_admin_only_and_answer_with_plain_codes(hass):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    sent = []
    connection = SimpleNamespace(user=SimpleNamespace(is_admin=True),
                                 send_result=lambda i, r: sent.append(("result", i, r)),
                                 send_error=lambda i, c, m: sent.append(("error", i, c)))
    e32_week.ws_week_get(hass, connection, {"id": 1, "type": "open_thermostat/e32_week/get", "entry_id": parent.entry_id})
    await hass.async_block_till_done()
    assert sent[-1][:2] == ("result", 1) and sent[-1][2]["rooms"][0]["id"] == "woonkamer"
    e32_week.ws_week_save(hass, connection, {"id": 2, "type": "open_thermostat/e32_week/save", "entry_id": parent.entry_id,
                                             "room_id": "woonkamer", "schedule": deepcopy(WEEK), "expected": [[]] * 7})
    await hass.async_block_till_done()
    assert sent[-1] == ("error", 2, "week_changed")
    e32_week.ws_week_save(hass, connection, {"id": 3, "type": "open_thermostat/e32_week/save", "entry_id": parent.entry_id,
                                             "room_id": "woonkamer", "schedule": deepcopy(WEEK), "expected": None})
    await hass.async_block_till_done()
    assert sent[-1][:2] == ("result", 3) and woonkamer(e32)["schedule"] == WEEK
    connection.user.is_admin = False
    with pytest.raises(Unauthorized):
        e32_week.ws_week_get(hass, connection, {"id": 4, "type": "open_thermostat/e32_week/get", "entry_id": parent.entry_id})
    # Every code the backend sends has a plain sentence in the card, in English and Dutch.
    card = (FRONTEND / "e32-week-card.js").read_text(encoding="utf-8")
    codes = set(e32_week.FAILURES.values()) | {"week_changed", "room_missing", "invalid_schedule",
                                                "invalid_schedule_limits", "unavailable"}
    for language in ("en", "nl"):
        block = re.search(language + r": \{title:.*?errors: \{(.*?)\}\}", card, re.S)[1]
        assert codes <= set(re.findall(r"(\w+): '", block)), language


@pytest.mark.asyncio
@pytest.mark.parametrize("credentials", [True, False])
async def test_the_dashboard_has_a_week_program_view_for_the_e32_rooms(hass, credentials):
    parent, _ = product(hass, FakeE32(), credentials=credentials, binding=room(hass))
    dashboard = RoomDashboard(hass, "fixture", parent.entry_id)
    config = dashboard._dashboard_config()
    views = {view["path"]: view for view in config["views"]}
    links = [card for card in view_cards(config["views"][0]) if card["type"] == "heading" and card.get("tap_action")]
    if credentials:
        assert views["week-program"]["cards"] == [{"type": "custom:openthermostat-e32-week", "entry_id": parent.entry_id}]
        assert links[-1]["heading"] == "Week program"
        assert links[-1]["tap_action"]["navigation_path"] == "/" + dashboard.path + "/week-program"
    else:
        assert "week-program" not in views and all(b.get("heading") != "Week program" for b in links)


def test_the_planner_is_one_file_shared_by_the_e32_page_and_home_assistant():
    shared = (ROOT / "data/html/week-editor.js").read_bytes()
    assert (FRONTEND / "week-editor.js").read_bytes() == shared, "copy data/html/week-editor.js to the HA frontend"
    assert b"\r" not in shared and len(shared) < 34000
    card = (FRONTEND / "e32-week-card.js").read_text(encoding="utf-8")
    assert f"const EDITOR = '{e32_week.EDITOR_URL}';" in card
    # Defined through ensureDefined, which defines it again when another card replaces the registry,
    # and the planner itself comes only from the one shared file (no other module import).
    assert "ensureDefined('openthermostat-e32-week', OpenThermostatE32Week);" in card
    assert re.findall(r"\bimport\b\W*\w*", card) == ["import.meta", "import(EDITOR"]


def test_the_planner_fahrenheit_text_matches_the_options_flow():
    """week-editor.js shows °F like e32_room_flow (test/week-editor.test.cjs has the same strings)."""
    from custom_components.open_thermostat.e32_room_flow import FAHRENHEIT
    week = [[[420, 2000], [1350, 1700]]] + [[]] * 6
    assert format_program(week, "en", FAHRENHEIT) == "mon: 07:00 68; 22:30 62.6"
    assert format_program(week, "nl", FAHRENHEIT) == "ma: 07:00 68; 22:30 62,6"
    # The planner stores a whole °F to 0.01 °C; the options flow shows it as the same whole °F.
    assert format_program([[[420, 2056], [1350, 1611]]] + [[]] * 6, "en", FAHRENHEIT) == "mon: 07:00 69; 22:30 61"
