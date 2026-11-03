"""Configure → Home → Comfort and boiler care (rc.3): the E32's control knobs from Home Assistant.

The same settings as the E32 Home page (``GET/POST /config/heating/flow`` "tuning" and
"tuning_manual"): each automatic knob automatic or set by you, the fixed knobs a value,
back to automatic for all and back to start values. Every request is the exact partial
change the E32 page sends, values are checked against the E32's own ranges first, older
firmware is told to update, and every text exists in English, Dutch and Polish.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.open_thermostat import e32_care as module
from custom_components.open_thermostat.controller_link import ControllerLinkError, HeatingPlanRejected
from custom_components.open_thermostat.e32_flow import KEY as FLOW_KEY, decode_settings
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from nav_helpers import is_again  # noqa: E402
from test_room_plan import FakeE32 as PlanE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
BUILT_IN = {"min_on_s": 300, "min_off_s": 300, "heat_start_c": 0.2, "heat_stop_c": 0.2, "flow_per_degree_c": 10,
            "curve_correction_pct": 50, "floor_lead_min_per_c": 120, "radiator_lead_min_per_c": 45,
            "learned_accept_pct": 100, "night_saving_min_pct": 2}
AUTO = ("min_on_s", "min_off_s", "heat_start_c", "heat_stop_c", "flow_per_degree_c", "floor_lead_min_per_c",
        "radiator_lead_min_per_c")


class FakeE32(PlanE32):
    """The room plan plus /config/heating/flow as FlowSettings::parse handles it (control/FlowPolicy.h).

    The record holds the owner's values; GET reports the values in effect: an automatic
    knob the self-tuning's value (tuned), the others the record's.
    """

    def __init__(self, *, manual_supported=True, tuning_supported=True):
        super().__init__()
        self.record = dict(BUILT_IN)
        self.manual = []
        self.tuned = {"min_off_s": 420}  # what the self-tuning set
        self.flow_posts, self.flow_logins = [], []
        self.manual_supported, self.tuning_supported = manual_supported, tuning_supported
        self.fail = None

    def answer(self):
        value = {"weather_curve": False, "apply_learned": True, "curve_design_flow_c": 0}
        if self.tuning_supported:
            value["tuning"] = {k: (self.tuned.get(k, BUILT_IN[k]) if k in AUTO and k not in self.manual
                                   else self.record[k]) for k in BUILT_IN}
            if self.manual_supported:
                value["tuning_manual"] = [k for k in AUTO if k in self.manual]
        return value

    def apply(self, change):
        record, manual = dict(self.record), list(self.manual)
        exact = None
        for key, value in change.items():
            if key == "tuning":
                if value is None:
                    record, manual = dict(BUILT_IN), []
                    continue
                for knob, v in value.items():
                    if knob not in BUILT_IN:
                        raise HeatingPlanRejected(400, "invalid_key")
                    record[knob] = v
                    if knob in AUTO and v != BUILT_IN[knob] and knob not in manual:
                        manual.append(knob)
            elif key == "tuning_manual":
                exact = value
            else:
                raise HeatingPlanRejected(400, "invalid_key")
        if exact is not None:
            if any(k not in AUTO for k in exact):
                raise HeatingPlanRejected(400, "invalid_value")
            for knob in AUTO:
                if knob not in exact:
                    record[knob] = BUILT_IN[knob]
            manual = list(exact)
        self.record, self.manual = record, manual

    def client(self, address):
        client = super().client(address)
        e32 = self

        async def flow(change=None):
            if change is not None:
                e32.flow_posts.append(deepcopy(change))
                e32.flow_logins.append(e32.logins)
                if e32.fail:
                    raise e32.fail
                e32.apply(change)
            return e32.answer()
        client.async_flow_settings = flow
        return client


async def care_menu(manager, parent):
    await manager.hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "heating_boiler"})
    assert "comfort_care" in house["menu_options"]
    return await manager.async_configure(house["flow_id"], {"next_step_id": "comfort_care"})


async def knob_form(manager, parent, knob):
    menu = await care_menu(manager, parent)
    pick = await manager.async_configure(menu["flow_id"], {"next_step_id": "comfort_care_knob"})
    assert pick["step_id"] == "comfort_care_knob"
    return await manager.async_configure(pick["flow_id"], {"knob": knob})


def defaults(form):
    return {str(k): k.default() for k in form["data_schema"].schema}


def test_the_knobs_match_the_e32_and_are_checked_before_they_are_kept():
    assert set(module.KNOBS) == set(BUILT_IN) and module.AUTOMATIC == (
        "min_off_s", "min_on_s", "heat_start_c", "heat_stop_c", "flow_per_degree_c", "floor_lead_min_per_c",
        "radiator_lead_min_per_c")
    assert {k: module.KNOBS[k][1] for k in BUILT_IN} == BUILT_IN
    good = {"tuning": dict(BUILT_IN), "tuning_manual": ["min_on_s", "min_off_s", "min_on_s"]}
    assert module.decode_tuning(good) == {"tuning": BUILT_IN, "tuning_manual": ["min_off_s", "min_on_s"]}
    assert module.decode_tuning({"tuning": dict(BUILT_IN)}) == {"tuning": BUILT_IN}  # 1.0 before rc.2
    assert module.decode_tuning({}) == {}
    for bad in ({**BUILT_IN, "min_on_s": 119}, {**BUILT_IN, "heat_start_c": 0.125}, {**BUILT_IN, "night_saving_min_pct": 21},
                {k: v for k, v in BUILT_IN.items() if k != "heat_stop_c"}, {**BUILT_IN, "flow_per_degree_c": "10"}):
        assert module.decode_tuning({"tuning": bad, "tuning_manual": []}) == {}
    # A manual list with a fixed or unknown knob is not kept: the knobs then cannot be changed here.
    assert module.decode_tuning({"tuning": BUILT_IN, "tuning_manual": ["curve_correction_pct"]}) == {"tuning": BUILT_IN}
    # The flow options keep the knobs next to the switches, which never depend on them.
    base = {"weather_curve": True, "apply_learned": False, "curve_design_flow_c": 0}
    assert decode_settings({**base, **good})["tuning_manual"] == ["min_off_s", "min_on_s"]
    assert decode_settings({**base, "tuning": "x"}) == base


def test_values_are_entered_as_the_e32_page_shows_them():
    assert module.shown_value("min_off_s", 420) == 7 and module.stored_value("min_off_s", 7.5) == 450
    assert module.shown_value("heat_start_c", 0.15) == 0.15 and module.stored_value("heat_start_c", 0.15) == 0.15
    assert module.stored_value("floor_lead_min_per_c", 90) == 90 and type(module.stored_value("floor_lead_min_per_c", 90.0)) is int
    for key, value in (("min_on_s", 1.5), ("min_on_s", 31), ("heat_start_c", 0.04), ("heat_start_c", 0.123),
                       ("curve_correction_pct", 50.5), ("learned_accept_pct", 201), ("night_saving_min_pct", True),
                       ("flow_per_degree_c", float("nan")), ("radiator_lead_min_per_c", None)):
        with pytest.raises(ValueError):
            module.stored_value(key, value)


@pytest.mark.asyncio
async def test_the_overview_shows_every_knob_in_words_and_the_actions(hass, manager):
    hass.config.language = "en"
    e32 = FakeE32()
    e32.manual = ["min_on_s"]
    e32.record["min_on_s"] = 600
    parent, _ = product(hass, e32)
    menu = await care_menu(manager, parent)
    assert menu["type"] == FlowResultType.MENU and menu["step_id"] == "comfort_care"
    assert menu["menu_options"] == ["comfort_care_knob", "comfort_care_auto_all", "comfort_care_reset", "back"]
    lines = menu["description_placeholders"]["settings"].splitlines()
    assert "- Burner rest between starts: 7 min (automatic)" in lines  # the self-tuning's value
    assert "- Burner run time: at least 10 min (set by you)" in lines
    assert "- Room correction on weather compensation: 50 % (standard value)" in lines and len(lines) == 10
    assert e32.flow_posts == []  # reading changes nothing
    # Nothing set by you: no "back to automatic for all".
    e32.manual, e32.record["min_on_s"] = [], 300
    menu = await care_menu(manager, parent)
    assert menu["menu_options"] == ["comfort_care_knob", "comfort_care_reset", "back"]


@pytest.mark.asyncio
async def test_an_automatic_knob_is_set_by_you_and_back_to_automatic(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await knob_form(manager, parent, "min_off_s")
    assert form["step_id"] == "comfort_care_auto_value"
    assert defaults(form) == {"automatic": True, "value": 7}  # 420 s in minutes, as on the E32 page
    assert form["description_placeholders"]["range"] == "2–30 min"
    logins = e32.logins
    done = await manager.async_configure(form["flow_id"], {"automatic": False, "value": 10})
    assert is_again(done)
    assert e32.flow_posts == [{"tuning": {"min_off_s": 600}, "tuning_manual": ["min_off_s"]}]
    assert e32.flow_logins[-1] == logins + 1  # one sign-in for the change (and a logout)
    assert e32.answer()["tuning"]["min_off_s"] == 600 and e32.manual == ["min_off_s"]
    # Back to automatic: only the manual list changes, the E32 forgets your value.
    form = await knob_form(manager, parent, "min_off_s")
    assert defaults(form) == {"automatic": False, "value": 10}
    done = await manager.async_configure(form["flow_id"], {"automatic": True, "value": 10})
    assert is_again(done) and e32.flow_posts[-1] == {"tuning_manual": []}
    assert e32.answer()["tuning"]["min_off_s"] == 420
    # Automatic again while automatic: nothing is written.
    form = await knob_form(manager, parent, "min_off_s")
    done = await manager.async_configure(form["flow_id"], {"automatic": True, "value": 3})
    assert is_again(done, "unchanged") and len(e32.flow_posts) == 2


@pytest.mark.asyncio
async def test_other_knobs_set_by_you_stay_when_one_more_is_set(hass, manager):
    e32 = FakeE32()
    e32.manual, e32.record["heat_stop_c"] = ["heat_stop_c"], 0.35
    parent, _ = product(hass, e32)
    form = await knob_form(manager, parent, "heat_start_c")
    assert defaults(form) == {"automatic": True, "value": 0.2}
    await manager.async_configure(form["flow_id"], {"automatic": False, "value": 0.15})
    assert e32.flow_posts == [{"tuning": {"heat_start_c": 0.15}, "tuning_manual": ["heat_start_c", "heat_stop_c"]}]
    assert e32.answer()["tuning"]["heat_stop_c"] == 0.35


@pytest.mark.asyncio
async def test_a_fixed_knob_takes_a_value_and_impossible_values_never_leave_home_assistant(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await knob_form(manager, parent, "curve_correction_pct")
    assert form["step_id"] == "comfort_care_fixed_value" and defaults(form) == {"value": 50}
    for bad in (101, -1):  # the form's own range (the E32's)
        with pytest.raises(InvalidData):
            await manager.async_configure(form["flow_id"], {"value": bad})
    form = await manager.async_configure(form["flow_id"], {"value": 50.5})  # the E32 keeps whole percents
    assert form["errors"] == {"value": "care_value_invalid"} and form["description_placeholders"]["range"] == "0–100 %"
    assert e32.flow_posts == []
    done = await manager.async_configure(form["flow_id"], {"value": 50})
    assert is_again(done, "unchanged") and e32.flow_posts == []
    form = await knob_form(manager, parent, "curve_correction_pct")
    done = await manager.async_configure(form["flow_id"], {"value": 70})
    assert is_again(done) and e32.flow_posts == [{"tuning": {"curve_correction_pct": 70}}]


@pytest.mark.asyncio
async def test_back_to_automatic_for_all_and_back_to_start_values_need_a_confirmation(hass, manager):
    e32 = FakeE32()
    e32.manual, e32.record["min_on_s"], e32.record["night_saving_min_pct"] = ["min_on_s"], 600, 5
    parent, _ = product(hass, e32)
    menu = await care_menu(manager, parent)
    form = await manager.async_configure(menu["flow_id"], {"next_step_id": "comfort_care_auto_all"})
    form = await manager.async_configure(form["flow_id"], {"confirm": False})
    assert form["errors"] == {"base": "care_confirm"} and e32.flow_posts == []
    done = await manager.async_configure(form["flow_id"], {"confirm": True})
    assert is_again(done) and e32.flow_posts == [{"tuning_manual": []}]
    assert e32.record["night_saving_min_pct"] == 5  # fixed knobs keep their value
    menu = await care_menu(manager, parent)
    form = await manager.async_configure(menu["flow_id"], {"next_step_id": "comfort_care_reset"})
    done = await manager.async_configure(form["flow_id"], {"confirm": True})
    assert is_again(done) and e32.flow_posts[-1] == {"tuning": None}
    assert e32.record == BUILT_IN and e32.manual == []


@pytest.mark.asyncio
async def test_a_refusal_or_unreachable_e32_is_a_clear_message_and_nothing_is_retried(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await knob_form(manager, parent, "flow_per_degree_c")
    e32.fail = HeatingPlanRejected(400, "invalid_value")
    again = await manager.async_configure(form["flow_id"], {"automatic": False, "value": 12})
    assert again["errors"] == {"base": "care_rejected"} and again["description_placeholders"]["error"] == "invalid_value"
    e32.fail = ControllerLinkError("controller_unreachable")
    again = await manager.async_configure(form["flow_id"], {"automatic": False, "value": 12})
    assert again["errors"] == {"base": "care_unreachable"}
    assert len(e32.flow_posts) == 2  # each submit once, never retried


@pytest.mark.asyncio
async def test_older_firmware_is_told_to_update_and_then_not_offered(hass, manager):
    e32 = FakeE32(manual_supported=False)
    parent, _ = product(hass, e32)
    result = await care_menu(manager, parent)
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "care_update_required"
    assert e32.flow_posts == []
    # The flow options are now known to lack changeable knobs: Home no longer offers them.
    assert hass.data["open_thermostat"][parent.entry_id][FLOW_KEY].settings is not None
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "heating_boiler"})
    assert "comfort_care" not in house["menu_options"]
    assert module.care_offered(hass, parent) is False


def test_every_comfort_and_boiler_care_text_exists_in_every_language():
    files = {name: json.loads((COMPONENT / name).read_text(encoding="utf-8"))
             for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json")}
    assert files["strings.json"] == files["translations/en.json"]
    steps = ("comfort_care", "comfort_care_knob", "comfort_care_auto_value", "comfort_care_fixed_value",
             "comfort_care_auto_all", "comfort_care_reset")
    errors = ("care_value_invalid", "care_knob_invalid", "care_confirm", "care_rejected", "care_unconfirmed",
              "care_unreachable", "care_no_free_session")
    aborts = ("care_unreachable", "care_rejected", "care_unconfirmed", "care_update_required", "care_unchanged",
              "care_saved", "e32_rooms_unavailable", "e32_password_changed")
    for name, data in files.items():
        options = data["options"]
        assert options["step"]["heating_boiler"]["menu_options"]["comfort_care"], name
        for step in steps:
            assert options["step"][step]["title"], (name, step)
        assert set(options["step"]["comfort_care"]["menu_options"]) == {
            "comfort_care_knob", "comfort_care_auto_all", "comfort_care_reset", "back", "done"}
        assert set(options["step"]["comfort_care_auto_value"]["data"]) == {"automatic", "value"}
        assert set(options["step"]["comfort_care_fixed_value"]["data"]) == {"value"}
        assert "{settings}" in options["step"]["comfort_care"]["description"]
        assert all(options["error"][e] for e in errors) and all(options["abort"][a] for a in aborts)
        assert "{range}" in options["error"]["care_value_invalid"]
        assert set(data["selector"]["comfort_care_knob"]["options"]) == set(module.KNOBS)
    assert files["translations/nl.json"]["selector"]["comfort_care_knob"]["options"]["min_on_s"] == "Brandtijd"
