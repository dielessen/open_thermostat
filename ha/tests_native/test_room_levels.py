"""The week planner's levels in the E32 room plan (E32 beta.23, "plan.levels.v1"): stored per room, only
sent to firmware that stores them, and never a reason for the E32 to refuse a plan."""
from copy import deepcopy

import pytest

from custom_components.open_thermostat import room_levels
from custom_components.open_thermostat.e32_week import read_week, save_week
from test_e32_room_flow import product
from test_room_plan import FakeE32, PLAN

LEVELS = {"comfort": 2100, "eco": 1850, "night": 1850}
WEEK = [[[390, 2100], [510, 1850], [1020, 2100], [1350, 1850]], [[390, 2100], [1350, 1850]], [], [], [], [[480, 2050]], []]
# The same fixture as test/test_native/test_room_plan_levels.cpp and test/week-editor.test.cjs.
MARKS = "1213.13....0."


def plan(features=True, **room):
    out = deepcopy(PLAN)
    out["rooms"][0].update(room)
    if features:
        out["features"] = [room_levels.FEATURE]
    return out


def test_marks_follow_the_planner_rules():
    assert room_levels.mark_text(WEEK, LEVELS, MARKS) == MARKS
    # Stale or broken digits are redone from the temperatures, like week-editor.js marked().
    for bad in ("1213.13....1.", "12.13....0.", "1213.13....0", "1214.13....0.", None, 42):
        assert room_levels.mark_text(WEEK, LEVELS, bad) == "1212.12....0.", bad
    assert room_levels.valid_levels({"comfort": 1900, "eco": 1700, "night": 2300}) == {"comfort": 1900, "eco": 1700, "night": 2300}
    assert room_levels.valid_levels({"comfort": 1900, "eco": 1700}) is None
    assert room_levels.valid_levels({"comfort": 1900, "eco": 17.5, "night": 1700}) is None
    assert room_levels.valid_levels({"comfort": 2600, "eco": 1700, "night": 1700}, 500, 2500) is None


def test_normalize_sends_levels_only_to_firmware_that_stores_them():
    # beta.21 and older: no "features", so no levels and no marks are posted.
    old = room_levels.normalize(plan(False, schedule=WEEK, levels=LEVELS, schedule_levels=MARKS))
    assert "levels" not in old["rooms"][0] and "schedule_levels" not in old["rooms"][0]
    # beta.23: kept, the read-only "features" is not posted.
    new = room_levels.normalize(plan(schedule=WEEK, levels=LEVELS, schedule_levels=MARKS))
    assert "features" not in new and new["rooms"][0]["levels"] == LEVELS and new["rooms"][0]["schedule_levels"] == MARKS
    # A program changed elsewhere (options flow, setting device) gets marks that fit it again.
    changed = room_levels.normalize(plan(schedule=[[[420, 2100], [1320, 1850]], [], [], [], [], [], []], levels=LEVELS,
                                         schedule_levels=MARKS))
    assert changed["rooms"][0]["schedule_levels"] == "12......"
    # No program: levels stay (thermostat presets), marks go; levels outside the room's limits go.
    bare = room_levels.normalize(plan(levels=LEVELS, schedule_levels=MARKS))
    assert bare["rooms"][0]["levels"] == LEVELS and "schedule_levels" not in bare["rooms"][0]
    outside = room_levels.normalize(plan(schedule=WEEK, levels={"comfort": 2600, "eco": 1850, "night": 1700}))
    assert "levels" not in outside["rooms"][0] and "schedule_levels" not in outside["rooms"][0]


class LevelsE32(FakeE32):
    """An E32 with beta.23: its plan names "plan.levels.v1" (the fake stores what HA posts)."""

    def __init__(self, plan_=None):
        super().__init__(plan_ or PLAN)
        self.plan["features"] = [room_levels.FEATURE]

    def client(self, address):
        inner, e32 = super().client(address), self

        class Client:
            async def __aenter__(self):
                await inner.__aenter__()
                return self

            async def __aexit__(self, *exc):
                return await inner.__aexit__(*exc)

            async def async_login(self, password):
                return await inner.async_login(password)

            async def async_read_heating_plan(self):
                return {**await inner.async_read_heating_plan(), "features": [room_levels.FEATURE]}

            async def async_save_heating_plan(self, plan_):
                stored = await inner.async_save_heating_plan(plan_)
                e32.plan["features"] = [room_levels.FEATURE]
                return {**stored, "features": [room_levels.FEATURE]}
        return Client()


@pytest.mark.asyncio
async def test_the_week_card_stores_the_levels_with_beta23(hass):
    e32 = LevelsE32()
    parent, _ = product(hass, e32)
    loaded = await read_week(hass, parent.entry_id, fresh=True)
    assert loaded["levels_supported"] is True
    week = [[[390, 2000], [1350, 1600]]] * 7
    result = await save_week(hass, parent.entry_id, "woonkamer", week, None,
                             {"comfort": 2000, "eco": 1600, "night": 1600}, ".".join(["13"] * 7))
    room = next(r for r in e32.posts[-1]["rooms"] if r["id"] == "woonkamer")
    assert room["levels"] == {"comfort": 2000, "eco": 1600, "night": 1600}       # equal Eco and Night are fine
    assert room["schedule_levels"] == ".".join(["13"] * 7) and "features" not in e32.posts[-1]
    assert result["rooms"][0]["levels"] == {"comfort": 2000, "eco": 1600, "night": 1600}
    assert result["rooms"][0]["schedule_levels"] == ".".join(["13"] * 7)
    # A program saved without marks (an older card) keeps the levels; marks that no longer fit are redone
    # from the temperatures (the first level with the temperature: 16 °C is Eco).
    second = [[[420, 1600], [1320, 2000]]] * 7
    await save_week(hass, parent.entry_id, "woonkamer", second, week)
    room = next(r for r in e32.posts[-1]["rooms"] if r["id"] == "woonkamer")
    assert room["levels"] == {"comfort": 2000, "eco": 1600, "night": 1600} and room["schedule_levels"] == ".".join(["21"] * 7)


@pytest.mark.asyncio
async def test_older_firmware_gets_plain_programs(hass):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    assert (await read_week(hass, parent.entry_id, fresh=True))["levels_supported"] is False
    week = [[[390, 2000], [1350, 1600]]] * 7
    await save_week(hass, parent.entry_id, "woonkamer", week, None, {"comfort": 2000, "eco": 1800, "night": 1600}, ".".join(["13"] * 7))
    room = next(r for r in e32.posts[-1]["rooms"] if r["id"] == "woonkamer")
    assert room["schedule"] == week and "levels" not in room and "schedule_levels" not in room
