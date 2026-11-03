"""Away temperature per room (E32 "plan.room_away.v1"): the room form, capability gating, the room
thermostat's reason, the plan writer, translations and a restore. The rules themselves run on the E32
(test/test_native/test_room_away.cpp); Home Assistant edits the value and reports the room's persons."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import InvalidData, section

from custom_components.open_thermostat import e32_backup as backup_module
from custom_components.open_thermostat import room_away, room_levels
from custom_components.open_thermostat.e32_comfort import comfort_options, comfort_payloads, CONF_COMFORT
from custom_components.open_thermostat.controller_link import HeatingPlanRejected
from custom_components.open_thermostat.room_plan import plan_room
from test_e32_backup import FakeBackupE32, backups, finish, open_restore
from test_e32_comfort import FakeE32 as ComfortE32, PLAN as COMFORT_PLAN, climate, room_state
from test_e32_room_flow import manager, product, room_form, shown  # noqa: F401  (the manager fixture)
from test_room_plan import PLAN, STATUS, FakeE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


class AwayE32(FakeE32):
    """An E32 after rc.2: its plan names plan.room_away.v1 (and levels); the fake stores what HA posts."""

    FEATURES = [room_levels.FEATURE, room_away.FEATURE]

    def __init__(self, plan=PLAN):
        super().__init__(plan)
        self.plan["features"] = list(self.FEATURES)

    def client(self, address):
        inner, features = super().client(address), self.FEATURES

        class Client:
            async def __aenter__(self):
                await inner.__aenter__()
                return self

            async def __aexit__(self, *exc):
                return await inner.__aexit__(*exc)

            async def async_login(self, password):
                return await inner.async_login(password)

            async def async_read_heating_plan(self):
                return {**await inner.async_read_heating_plan(), "features": list(features)}

            async def async_save_heating_plan(self, plan):
                return {**await inner.async_save_heating_plan(plan), "features": list(features)}

            async def async_valves(self, document=None):
                return None  # firmware without valve records: the room form has no valves section
        return Client()


def persons_section(form):
    marker, value = next((k, v) for k, v in form["data_schema"].schema.items() if str(k) == "persons")
    assert isinstance(value, section)
    return value


# -- the plan writer ---------------------------------------------------------------------------------


def test_the_value_is_sent_only_to_an_e32_that_names_the_feature_and_only_when_valid():
    plan = deepcopy(PLAN)
    plan["features"] = [room_away.FEATURE]
    plan["rooms"][0]["away_centi_c"] = 1600
    plan["rooms"][1]["away_centi_c"] = 2600          # outside 5–25 °C: never sent
    sent = room_levels.normalize(deepcopy(plan))
    assert "features" not in sent
    assert sent["rooms"][0]["away_centi_c"] == 1600 and "away_centi_c" not in sent["rooms"][1]
    old = deepcopy(plan)
    old["features"] = [room_levels.FEATURE]           # rc.2: levels only
    assert all("away_centi_c" not in r for r in room_levels.normalize(old)["rooms"])
    assert room_away.room_away({"away_centi_c": 1600}) == 1600
    for bad in (None, {}, {"away_centi_c": 499}, {"away_centi_c": 16.0}, {"away_centi_c": True}, {"away_centi_c": "1600"}):
        assert room_away.room_away(bad) is None


def test_the_reason_a_room_is_cooler():
    reason = room_away.away_reason
    assert reason({"mode": "presence_away", "away_by": "room", "persons": "away"}, {"presence": "home"}) == "room_persons"
    assert reason({"mode": "presence_away", "away_by": "house", "persons": "away"}, {"presence": "away"}) == "everyone"
    assert reason({"mode": "presence_away"}, {"presence": "away"}) == "everyone"
    # rc.2 has no away_by: its own persons away while the house is not is the room.
    assert reason({"mode": "presence_away", "persons": "away"}, {"presence": "home"}) == "room_persons"
    assert reason({"mode": "presence_away", "persons": "away"}, {"presence": "away"}) == "everyone"
    assert reason({"mode": "away"}, {}) == reason({"mode": "away_return"}, {}) == "house_mode"
    assert reason({"mode": "window_open"}, {}) is None and reason({}, {}) is None and reason(None, None) is None


# -- the room form -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_persons_section_sets_and_clears_the_rooms_own_away_temperature(hass, manager):
    e32 = AwayE32()
    parent, hub = product(hass, e32)
    hub.update({**STATUS, "away": {"on": False, "source": "none", "target_c": 17, "until": None, "presence": "home",
                                   "mode": "auto", "room_presence": True}})
    form = await room_form(manager, parent, "woonkamer")
    persons = persons_section(form)
    assert [str(k) for k in persons.schema.schema] == ["persons", "away_temperature"]
    assert persons.options["collapsed"] is True       # nothing set yet
    field = next(v for k, v in persons.schema.schema.items() if str(k) == "away_temperature")
    assert (field.config["min"], field.config["max"], field.config["step"]) == (5.0, 25.0, 0.5)
    assert form["description_placeholders"]["house_away"] == "17 °C"
    assert form["description_placeholders"]["away_range"] == "5–25 °C"
    values = shown(form)
    assert "away_temperature" not in values.get("persons", {})   # empty: the house value
    values["persons"] = {**values.get("persons", {}), "away_temperature": 16}
    result = await manager.async_configure(form["flow_id"], values)
    assert result["step_id"] == "e32_rooms_saved", result
    sent = e32.posts[-1]
    assert plan_room(sent, "woonkamer")["away_centi_c"] == 1600 and "features" not in sent
    assert "away_centi_c" not in plan_room(sent, "badkamer")       # the other room is untouched
    # Shown again: the section is open with the value; saving it unchanged writes nothing.
    form = await room_form(manager, parent, "woonkamer")
    assert persons_section(form).options["collapsed"] is False
    values = shown(form)
    assert values["persons"]["away_temperature"] == 16.0
    posts = len(e32.posts)
    unchanged = await manager.async_configure(form["flow_id"], values)
    assert unchanged["type"] == "abort" and unchanged["reason"] == "e32_room_unchanged"
    assert len(e32.posts) == posts
    # Cleared: the room uses the house value again (the field leaves the plan).
    form = await room_form(manager, parent, "woonkamer")
    values = shown(form)
    values["persons"].pop("away_temperature")
    result = await manager.async_configure(form["flow_id"], values)
    assert result["step_id"] == "e32_rooms_saved", result
    assert "away_centi_c" not in plan_room(e32.posts[-1], "woonkamer")


@pytest.mark.asyncio
async def test_a_new_room_can_start_with_its_own_value_and_bad_values_are_refused(hass, manager):
    e32 = AwayE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    values = {"name": "Werkkamer Jolien", "state": "active", "emitter": "radiator", "ha_sources": ["sensor.hal"],
              "fallback_temperature": 20, "persons": {"away_temperature": 15.5}}
    result = await manager.async_configure(form["flow_id"], values)
    assert result["step_id"] == "e32_rooms_saved", result
    assert plan_room(e32.posts[-1], "werkkamer_jolien")["away_centi_c"] == 1550
    # Outside 5–25 °C the form itself refuses it.
    form = await room_form(manager, parent, "woonkamer")
    for bad in (4.5, 25.5):
        with pytest.raises(InvalidData):
            await manager.async_configure(form["flow_id"], {**shown(form), "persons": {"away_temperature": bad}})
    # The E32's own refusal is a clear message, not its code.
    e32.fail = HeatingPlanRejected(400, "invalid_room_away")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "persons": {"away_temperature": 16}})
    assert result["errors"] == {"base": "e32_away_invalid"} and result["description_placeholders"]["away_range"] == "5–25 °C"


@pytest.mark.asyncio
async def test_an_e32_without_the_feature_gets_no_field_and_no_value(hass, manager):
    e32 = FakeE32()                                     # rc.2 and older: no plan.room_away.v1
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    assert [str(k) for k in persons_section(form).schema.schema] == ["persons"]
    values = shown(form)
    values["name"] = "Woonkamer beneden"
    result = await manager.async_configure(form["flow_id"], values)
    assert result["step_id"] == "e32_rooms_saved", result
    assert all("away_centi_c" not in r for r in e32.posts[-1]["rooms"])
    with pytest.raises(InvalidData):                    # the field does not exist for this E32
        await manager.async_configure((await room_form(manager, parent, "woonkamer"))["flow_id"],
                                      {**values, "persons": {"away_temperature": 16}})


# -- the room thermostat -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_thermostat_names_why_the_room_is_cooler_and_its_own_value(hass):
    e32 = ComfortE32()
    e32.plan["features"] = [room_away.FEATURE]
    next(r for r in e32.plan["rooms"] if r["id"] == "study")["away_centi_c"] = 1600
    house_home = {"on": False, "source": "none", "target_c": 17, "until": None, "presence": "home", "mode": "auto"}
    entity, hub, link = await climate(hass, e32, room_state("study", setpoint=16, comfort={
        "mode": "presence_away", "persons": "away", "away_by": "room", "target_c": 16}), away=house_home)
    attributes = entity.extra_state_attributes
    assert attributes["away_reason"] == "room_persons" and attributes["room_persons"] == "away"
    assert attributes["own_away_temperature"] == 16.0 and entity.target_temperature == 16
    # Everyone out: the house value for every room, also the study.
    hub.update({**hub.status, "away": {**house_home, "on": True, "source": "presence", "presence": "away"},
                "rooms": [room_state("study", setpoint=17, comfort={"mode": "presence_away", "persons": "away",
                                                                     "away_by": "house", "target_c": 17}),
                          room_state("living", setpoint=17, comfort={"mode": "presence_away", "away_by": "house",
                                                                      "target_c": 17})]})
    assert entity.extra_state_attributes["away_reason"] == "everyone" and entity.target_temperature == 17
    # The living room has no value of its own: None (the house value).
    living = type(entity)(hub, room_state("living"), entity.entry)
    assert living.extra_state_attributes["own_away_temperature"] is None
    assert living.extra_state_attributes["away_reason"] == "everyone"
    assert living.extra_state_attributes["room_persons"] is None    # no persons of its own
    link.stop()


@pytest.mark.asyncio
async def test_a_room_for_two_reports_home_until_both_are_out(hass):
    """Rule 2 needs all of the room's persons away: HA aggregates them before it tells the E32."""
    from homeassistant.util import dt as dt_util
    hass.states.async_set("person.jolien", "not_home")
    hass.states.async_set("person.mark", "home")
    settings = comfort_options(type("E", (), {"options": {CONF_COMFORT: {
        "presence_entities": ["person.jolien", "person.mark"], "away_delay_min": 15,
        "room_persons": {"bedroom": ["person.jolien", "person.mark"], "study": ["person.jolien"]}}}})())
    later = dt_util.utcnow() + timedelta(minutes=16)
    payloads = comfort_payloads(hass, settings, {"bedroom", "study", "living"}, now=later, room_presence=True)
    assert {"kind": "room_presence", "room": "study", "home": False} in payloads    # Jolien's study: away
    assert {"kind": "room_presence", "room": "bedroom", "home": True} in payloads   # Mark is still home
    assert {"kind": "presence", "home": True} in payloads                           # the house stays warm
    hass.states.async_set("person.mark", "not_home")
    later = dt_util.utcnow() + timedelta(minutes=16)
    payloads = comfort_payloads(hass, settings, {"bedroom", "study", "living"}, now=later, room_presence=True)
    assert {"kind": "room_presence", "room": "bedroom", "home": False} in payloads
    assert {"kind": "presence", "home": False} in payloads                          # everyone: the house value


# -- restore and translations ------------------------------------------------------------------------


class RoomAwayBackupE32(FakeBackupE32):
    """Its backup file holds a room with its own away temperature (the plan's away_centi_c)."""

    def client(self, address):
        inner = super().client(address)
        export = inner.async_config_backup

        async def async_config_backup(request):
            value, status = await export(request)
            if request["action"] == "export":
                value["heating"] = {"schema": 1, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60,
                                    "rooms": [{**PLAN["rooms"][0], "away_centi_c": 1600}]}
            return value, status
        inner.async_config_backup = async_config_backup
        return inner


@pytest.mark.asyncio
async def test_a_restore_sends_the_rooms_own_away_temperature_back_unchanged(hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = RoomAwayBackupE32(hostname="kelder")
    monkeypatch.setattr(backup_module, "RESTART_POLL", 0)
    store = await backups(hass, parent, e32)
    await store.async_backup("daily")
    chosen = store.records()[0]["id"]
    assert store.record(chosen)["document"]["heating"]["rooms"][0]["away_centi_c"] == 1600
    e32.hostname = "zolder"
    form = await open_restore(manager, parent)
    confirm = await finish(hass, manager, await manager.async_configure(form["flow_id"], {"backup": chosen, "address": e32.address}))
    assert confirm["step_id"] == "e32_restore_confirm", confirm
    await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    apply = e32.calls[-1]
    assert apply["action"] == "apply" and apply["backup"]["heating"]["rooms"][0]["away_centi_c"] == 1600


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"])
def test_the_new_texts_exist_in_every_language_with_their_placeholders(filename):
    document = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))
    persons = document["options"]["step"]["e32_room"]["sections"]["persons"]
    assert set(persons["data"]) == {"persons", "away_temperature"}
    assert set(persons["data_description"]) == {"persons", "away_temperature"}
    assert "{house_away}" in persons["data_description"]["away_temperature"]
    assert "{away_range}" in document["options"]["error"]["e32_away_invalid"]
    if filename.endswith("nl.json"):
        assert persons["data"]["away_temperature"] == "Temperatuur als de mensen van deze ruimte weg zijn"
    if filename.endswith("en.json") or filename == "strings.json":
        assert persons["data"]["away_temperature"] == "Temperature when this room's people are away"
    assert (COMPONENT / "strings.json").read_text(encoding="utf-8") == (COMPONENT / "translations/en.json").read_text(encoding="utf-8")
