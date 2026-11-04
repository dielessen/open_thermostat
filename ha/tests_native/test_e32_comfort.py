"""E32 room thermostats, temporary overrides, window/door pauses and away (beta.19 items 15-18)."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.open_thermostat import e32_comfort as module
from custom_components.open_thermostat.controller_link import HeatingPlanRejected
from custom_components.open_thermostat.e32_comfort import (
    CONF_COMFORT, ComfortError, ComfortForwarder, E32RoomClimate, away_command, comfort_options, comfort_payloads,
    contacts_open, house_presence, presence_home, validate_contacts, validate_presence, validate_settings)
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.room_plan import RoomPlanLink

WEEK = [[[390, 2050], [1350, 1800]], [], [], [], [], [], []]
LIVING = {"id": "living", "name": "Living", "state": "active", "inactive_until": 0, "emitter": "radiator",
          "sources": [{"type": "ble", "id": "a4c138000001"}], "setpoint_entity": "", "fallback_centi_c": 2000,
          "minimum_centi_c": 500, "maximum_centi_c": 2400, "schedule": WEEK}
STUDY = {**LIVING, "id": "study", "name": "Study", "schedule": [[], [], [], [], [], [], []]}
TADO = {**STUDY, "id": "tado", "name": "Tado room", "setpoint_entity": "climate.tado"}
PLAN = {"schema": 1, "revision": 2, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60,
        "rooms": [LIVING, STUDY, TADO]}


def room_state(room_id, **extra):
    return {"id": room_id, "name": room_id.title(), "state": "active", "status": "ok", "source": "a4c138000001",
            "temperature": 19.5, "setpoint": 20.5, "setpoint_source": "schedule", "demand": True, **extra}


def status(*rooms, away=None):
    return {"schema": 1, "revision": 2, "mode": "shadow", "request": {"heat": True, "flow_c": 45, "reason": "heating"},
            "ha_entities": [], "rooms": list(rooms),
            "away": away or {"on": False, "source": "none", "target_c": 15, "until": None, "presence": "unknown"}}


class FakeE32:
    """GET/POST /config/heating and POST /config/heating/comfort."""

    def __init__(self):
        self.plan = deepcopy(PLAN)
        self.commands, self.plan_posts = [], []
        self.refuse = {}  # override kind -> HeatingPlanRejected

    def client(self):
        e32 = self

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def async_login(self, password):
                assert password == "secret"

            async def async_read_heating_plan(self):
                return deepcopy(e32.plan)

            async def async_save_heating_plan(self, plan):
                e32.plan_posts.append(deepcopy(plan))
                e32.plan = {**deepcopy(plan), "revision": plan["revision"] + 1}
                return deepcopy(e32.plan)

            async def async_comfort_command(self, command):
                e32.commands.append(deepcopy(command))
                refusal = e32.refuse.get(command.get("override", "away"))
                if refusal:
                    raise refusal
                return {"schema": 1, "away": {}, "rooms": []}
        return Client()


def entry(settings=None):
    return SimpleNamespace(entry_id="e1", options={CONF_COMFORT: settings} if settings is not None else {})


async def climate(hass, e32, room, settings=None, away=None):
    hub = HeatingHub("fixture")
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    link._client = e32.client
    hub.plan = link
    await link.async_read()
    hub.update(status(room, away=away))
    await hass.async_block_till_done()
    return E32RoomClimate(hub, room, entry(settings)), hub, link


def test_presence_and_contacts_map_home_assistant_states():
    state = lambda entity_id, value: SimpleNamespace(entity_id=entity_id, state=value)
    assert presence_home(state("person.anna", "home")) is True
    assert presence_home(state("person.anna", "not_home")) is False
    assert presence_home(state("person.anna", "Work")) is False          # another zone: not home
    assert presence_home(state("group.family", "home")) is True
    assert presence_home(state("zone.home", "0")) is False
    assert presence_home(state("zone.home", "2")) is True
    assert presence_home(state("input_boolean.someone_home", "on")) is True
    assert presence_home(state("binary_sensor.occupied", "off")) is False
    for unknown in ("unknown", "unavailable"):
        assert presence_home(state("person.anna", unknown)) is None
    assert presence_home(None) is None
    on, off, gone = (SimpleNamespace(state=s) for s in ("on", "off", "unavailable"))
    assert contacts_open([off, on]) is True       # any open counts, also with one unknown
    assert contacts_open([on, gone]) is True
    assert contacts_open([off, off]) is False
    assert contacts_open([off, gone]) is None     # unknown: not sent, the E32 lets it expire
    assert contacts_open([]) is None


def test_options_have_safe_defaults_and_never_take_invalid_values():
    assert comfort_options(entry()) == module.DEFAULTS
    settings = comfort_options(entry({"presence_entity": "zone.home", "comfort_c": 21.5, "eco_c": 99,
                                      "contact_delay_s": 30, "override_minutes": 0,
                                      "contacts": {"living": ["binary_sensor.window", "light.x"], 5: []}}))
    assert settings["presence_entity"] == "zone.home" and settings["comfort_c"] == 21.5
    assert settings["presence_entities"] == ["zone.home"] and settings["away_delay_min"] == 15  # migrated: a list of one
    assert settings["eco_c"] == 16.0 and settings["override_minutes"] == 120 and settings["contact_delay_s"] == 30
    assert settings["contacts"] == {"living": ["binary_sensor.window"]}


@pytest.mark.asyncio
async def test_options_form_values_are_checked(hass):
    hass.states.async_set("zone.home", "1")
    hass.states.async_set("light.lamp", "on")
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    hass.states.async_set("binary_sensor.motion", "off", {"device_class": "motion"})
    current = comfort_options(entry())
    out = validate_settings(hass, {"comfort_temperature": 21.3, "eco_temperature": 16,
                                   "contact_delay": 90, "override_minutes": 60}, current)
    assert (out["comfort_c"], out["eco_c"], out["contact_delay_s"], out["override_minutes"]) == (21.5, 16.0, 90, 60)
    for bad, field in (({"comfort_temperature": 31}, "comfort_temperature"),
                       ({"contact_delay": 1801}, "contact_delay"), ({"override_minutes": 1.5}, "override_minutes")):
        with pytest.raises(ComfortError) as error:
            validate_settings(hass, bad, current)
        assert error.value.field == field
    assert validate_contacts(hass, ["binary_sensor.window"]) == ["binary_sensor.window"]
    for bad in (["binary_sensor.motion"], ["binary_sensor.window", "binary_sensor.window"], ["light.lamp"]):
        with pytest.raises(ComfortError):
            validate_contacts(hass, bad)


@pytest.mark.asyncio
async def test_contacts_and_presence_are_forwarded_per_room_with_the_delay(hass):
    hass.states.async_set("binary_sensor.window", "on", {"device_class": "window"})
    hass.states.async_set("binary_sensor.door", "off", {"device_class": "door"})
    hass.states.async_set("binary_sensor.attic", "on", {"device_class": "window"})
    hass.states.async_set("person.anna", "not_home")
    settings = comfort_options(entry({"presence_entity": "person.anna", "contact_delay_s": 60, "away_delay_min": 0,
                                      "contacts": {"living": ["binary_sensor.window", "binary_sensor.door"],
                                                   "attic": ["binary_sensor.attic"]}}))
    assert comfort_payloads(hass, settings, {"living", "study"}) == [
        {"kind": "contact", "room": "living", "open": True, "delay_s": 60},  # the attic is not in the plan
        {"kind": "presence", "home": False}]
    assert comfort_payloads(hass, settings, {"living"}, only="binary_sensor.door") == [
        {"kind": "contact", "room": "living", "open": True, "delay_s": 60}]
    assert comfort_payloads(hass, settings, {"living"}, only="person.anna") == [{"kind": "presence", "home": False}]

    sent, tracked = [], []
    hub = HeatingHub("fixture")
    forwarder = ComfortForwarder(hass, entry({"presence_entity": "person.anna", "away_delay_min": 0,
                                              "contacts": {"living": ["binary_sensor.window"]}}), hub,
                                 sent.append, lambda hass, ids, action: tracked.append((ids, action)) or (lambda: None))
    forwarder.reconfigure()
    assert tracked[0][0] == ["binary_sensor.window", "person.anna"]
    assert sent == []  # nothing while the E32 is silent
    hub.update(status(room_state("living")))
    forwarder.hub_changed()  # the E32 is (back) online: everything at once
    assert [json.loads(p) for p in sent] == [{"kind": "contact", "room": "living", "open": True, "delay_s": 120},
                                             {"kind": "presence", "home": False}]
    hass.states.async_set("binary_sensor.window", "off", {"device_class": "window"})
    tracked[0][1](SimpleNamespace(data={"entity_id": "binary_sensor.window"}))
    assert json.loads(sent[-1]) == {"kind": "contact", "room": "living", "open": False, "delay_s": 120}
    assert all(len(p.encode()) <= 192 for p in sent)  # the E32's input bound (RoomOverrides::inputBytes)


@pytest.mark.asyncio
async def test_the_thermostat_shows_the_room_and_its_override(hass):
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("living", comfort={
        "mode": "next", "target_c": 20.5, "until": 1793655000, "override": "next"}))
    assert entity.unique_id == "fixture_e32_room_living_thermostat" and entity.name is None
    assert (entity.current_temperature, entity.target_temperature, entity.min_temp, entity.max_temp) == (19.5, 20.5, 5.0, 24.0)
    assert entity.hvac_mode == HVACMode.HEAT and entity.hvac_action == HVACAction.HEATING
    assert entity.preset_mode == "comfort"  # the warmest level of the week program (20.5 °C)
    hub.update(status(room_state("living", comfort={"mode": "next", "target_c": 18, "override": "next"})))
    assert entity.preset_mode == "sleep"    # its coolest level: the planner's Night
    hub.update(status(room_state("living", comfort={"mode": "next", "target_c": 19.5, "override": "next"})))
    assert entity.preset_mode == "eco"      # the inferred middle level: the planner's Eco
    hub.update(status(room_state("living", comfort={"mode": "next", "target_c": 21, "until": 1793655000,
                                                        "override": "next"})))
    assert entity.preset_mode == "none"
    attributes = entity.extra_state_attributes
    assert attributes["comfort_mode"] == "next" and attributes["until"] == "2026-11-02T21:30:00+00:00"
    assert attributes["away"] is False and attributes["window"] is None
    # A window pause and away are visible with their reason.
    hub.update(status(room_state("living", setpoint=8, comfort={"mode": "window_open", "window": "open", "target_c": 8}),
                      away={"on": True, "source": "presence", "target_c": 15, "until": None, "presence": "away"}))
    # Away is the house mode, not a room preset (beta.23): the room shows no preset, the reason stays visible.
    assert entity.hvac_mode == HVACMode.AUTO and entity.preset_mode == "none" and "away" not in entity.preset_modes
    assert entity.extra_state_attributes["window"] == "open" and entity.extra_state_attributes["away_source"] == "presence"
    hub.update(status(room_state("living", state="inactive", demand=False)))
    assert entity.hvac_mode == HVACMode.OFF and entity.hvac_action == HVACAction.OFF and entity.preset_mode == "none"
    hub.update(None)
    assert not entity.available
    link.stop()


@pytest.mark.asyncio
async def test_a_new_target_holds_until_the_next_switch_point_else_for_the_set_time(hass):
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("living"), {"override_minutes": 90})
    await entity.async_set_temperature(temperature=21.5)
    assert e32.commands[-1] == {"room": "living", "override": "next", "temperature": 21.5}
    # The E32 has no clock yet: the same target for the configured time instead.
    e32.refuse["next"] = HeatingPlanRejected(409, "no_clock")
    await entity.async_set_temperature(temperature=21)
    assert e32.commands[-2:] == [{"room": "living", "override": "next", "temperature": 21.0},
                                 {"room": "living", "override": "timed", "temperature": 21.0, "minutes": 90}]
    assert e32.plan_posts == []  # the plan itself is never touched for an override
    link.stop()

    # A room following an HA thermostat (no own program): a timed override.
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("tado"))
    await entity.async_set_temperature(temperature=19)
    assert e32.commands == [{"room": "tado", "override": "timed", "temperature": 19.0, "minutes": 120}]
    link.stop()

    # A room with only a fixed target: the plan's fixed target changes (permanent).
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("study"))
    await entity.async_set_temperature(temperature=18.3)
    assert e32.commands == [] and e32.plan["rooms"][1]["fallback_centi_c"] == 1850
    link.stop()


@pytest.mark.asyncio
async def test_modes_and_presets_write_the_plan_or_a_command(hass):
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("living", comfort={
        "mode": "boost", "target_c": 24, "until": 1793620800, "override": "boost"}))
    assert entity.preset_mode == "boost"
    await entity.async_set_hvac_mode(HVACMode.OFF)
    assert e32.plan["rooms"][0]["state"] == "inactive"
    hub.update(status(room_state("living", state="inactive", comfort={"mode": "program", "override": "boost"})))
    await entity.async_set_hvac_mode(HVACMode.AUTO)  # on again, back to the week program
    assert e32.plan["rooms"][0]["state"] == "active"
    assert e32.commands[-1] == {"room": "living", "override": "none"}
    await entity.async_set_preset_mode("sleep")  # the Night level of the week program
    assert e32.commands[-1] == {"room": "living", "override": "next", "temperature": 18.0}
    await entity.async_set_preset_mode("eco")
    assert e32.commands[-1] == {"room": "living", "override": "next", "temperature": 19.5}
    await entity.async_set_preset_mode("comfort")
    assert e32.commands[-1] == {"room": "living", "override": "next", "temperature": 20.5}
    await entity.async_set_preset_mode("boost")
    assert e32.commands[-1] == {"room": "living", "override": "boost"}
    # Away is the house mode only: no room preset, and "none" on a room leaves a house away alone.
    with pytest.raises(ServiceValidationError):
        await entity.async_set_preset_mode("away")
    hub.update(status(room_state("living"), away={"on": True, "source": "manual", "target_c": 15, "until": None,
                                                  "presence": "unknown", "mode": "away"}))
    count = len(e32.commands)
    await entity.async_set_preset_mode("none")
    assert e32.commands[count:] == []
    link.stop()


@pytest.mark.asyncio
async def test_actions_and_refusals(hass):
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("living"))
    await entity.async_set_room_override("timed", 21, 120)
    assert e32.commands[-1] == {"room": "living", "override": "timed", "temperature": 21.0, "minutes": 120}
    await entity.async_set_room_override("until_next")  # the current target
    assert e32.commands[-1] == {"room": "living", "override": "next", "temperature": 20.5}
    await entity.async_set_room_override("boost", duration_minutes=30)
    assert e32.commands[-1] == {"room": "living", "override": "boost", "minutes": 30}
    with pytest.raises(ServiceValidationError) as error:
        await entity.async_set_room_override("timed", 29)  # above this room's 24 °C
    assert error.value.translation_key == "room_setpoint_outside_limits"
    await entity.async_clear_room_override()
    assert e32.commands[-1] == {"room": "living", "override": "none"}
    back = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=3)
    await entity.async_set_away(16, back)
    assert e32.commands[-1] == {"away": True, "temperature": 16.0, "until": int(back.timestamp())}
    await entity.async_clear_away()
    assert e32.commands[-1] == {"away": False}
    # E32 beta.23 (house.mode.v1): the same actions set the house mode, like the House mode select.
    hub.update(status(room_state("living"), away={"on": False, "source": "none", "target_c": 15, "until": None,
                                                  "presence": "unknown", "mode": "auto"}))
    await entity.async_set_away(16, back)
    assert e32.commands[-1] == {"house_mode": "holiday", "temperature": 16.0, "until": int(back.timestamp())}
    await entity.async_set_away()
    assert e32.commands[-1] == {"house_mode": "away"}
    await entity.async_clear_away()
    assert e32.commands[-1] == {"house_mode": "auto"}
    for code, key in (("no_clock", "comfort_no_clock"), ("room_inactive", "comfort_room_off"),
                      ("no_schedule", "comfort_no_schedule"), ("invalid_minutes", "comfort_rejected")):
        e32.refuse["timed"] = HeatingPlanRejected(400, code)
        with pytest.raises(ServiceValidationError) as error:
            await entity.async_set_room_override("timed", 21, 60)
        assert error.value.translation_key == key
    e32.refuse["timed"] = HeatingPlanRejected(503, "save_unconfirmed")
    with pytest.raises(HomeAssistantError) as error:
        await entity.async_set_room_override("timed", 21, 60)
    assert error.value.translation_key == "room_plan_unconfirmed"
    link.stop()


def test_comfort_eco_and_night_follow_the_week_planner_levels():
    settings = comfort_options(entry())
    # Older firmware: inferred exactly like week-editor.js infer() (see test/week-editor.test.cjs).
    assert module.program_levels(LIVING, settings) == (20.5, 19.5, 18.0)
    one = {**LIVING, "schedule": [[[420, 2100]], [], [], [], [], [], []]}
    assert module.program_levels(one, settings) == (21.0, 18.5, 16.0)       # one level: night at 16 °C
    low = {**LIVING, "minimum_centi_c": 1700, "schedule": [[[420, 1700]], [], [], [], [], [], []]}
    assert module.program_levels(low, settings) == (17.0, 18.0, 17.0)      # clamped to the room minimum, still distinct
    work = {**LIVING, "schedule": [[[390, 2050], [510, 1950], [1020, 2050], [1350, 1800]]] * 5 + [[[480, 2050], [1380, 1800]]] * 2}
    assert module.program_levels(work, settings) == (20.5, 19.5, 18.0)
    # No program: the former house settings (Comfort, and "eco_c" as Night) start the room's levels.
    assert module.program_levels(STUDY, settings) == (20.0, 18.0, 16.0)
    assert module.program_levels(None, comfort_options(entry({"comfort_c": 21.5, "eco_c": 17}))) == (21.5, 19.5, 17.0)
    # Stored levels (E32 beta.23) win, also equal ones or a Night warmer than Comfort.
    stored = {**LIVING, "levels": {"comfort": 2100, "eco": 1850, "night": 2200}}
    assert module.program_levels(stored, settings) == (21.0, 18.5, 22.0)
    outside = {**LIVING, "levels": {"comfort": 2600, "eco": 1850, "night": 1700}}  # above the room maximum: ignored
    assert module.program_levels(outside, settings) == (20.5, 19.5, 18.0)


def test_away_dates_are_checked_before_anything_is_sent():
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    assert away_command(True, 15.5, now + timedelta(days=2), now) == {
        "away": True, "temperature": 15.5, "until": int((now + timedelta(days=2)).timestamp())}
    assert away_command(False, 15, now) == {"away": False}
    for until in (now - timedelta(minutes=1), now + timedelta(days=367)):
        with pytest.raises(ServiceValidationError) as error:
            away_command(True, None, until, now)
        assert error.value.translation_key == "comfort_away_until"
    with pytest.raises(ServiceValidationError):
        away_command(True, 26)


@pytest.mark.asyncio
async def test_set_comfort_on_an_e32_room_is_handled(hass, monkeypatch):
    """R4-06: set_comfort belongs to the older Home Assistant rooms; an E32 room answers with a clear message."""
    import logging
    from unittest.mock import AsyncMock
    from homeassistant.core import ServiceCall
    from homeassistant.helpers import entity_platform
    from custom_components.open_thermostat import climate as climate_platform, v1_climate
    from test_v1_native import entry as v1_entry
    # An E32 installation without older rooms: the action is not offered at all.
    monkeypatch.setattr(module, "async_setup_e32_climates", AsyncMock())
    monkeypatch.setattr(v1_climate, "async_setup_entry", AsyncMock())
    item = v1_entry(hass)
    platform = entity_platform.EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="climate", platform_name="open_thermostat",
        platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = item
    token = entity_platform.current_platform.set(platform)
    try:
        await climate_platform.async_setup_entry(hass, item, lambda *args, **kwargs: None)
    finally:
        entity_platform.current_platform.reset(token)
    assert hass.services.has_service("open_thermostat", "set_room_override")
    assert not hass.services.has_service("open_thermostat", "set_comfort")
    # Registered by an installation that still has older rooms, it answers an E32 room clearly.
    e32 = FakeE32()
    entity, hub, link = await climate(hass, e32, room_state("living"))
    entity.entity_id = "climate.living"
    call = ServiceCall(hass, "open_thermostat", "set_comfort", {"entity_id": ["climate.living"], "mode": "boost"})
    with pytest.raises(ServiceValidationError) as caught:
        await climate_platform.set_comfort(entity, call)
    assert caught.value.translation_key == "set_comfort_unsupported"
    assert caught.value.translation_placeholders == {"entity": "climate.living"}
    assert e32.commands == [] and e32.plan_posts == []
    seen = []

    class OlderRoom:
        entity_id = "climate.older_room"

        async def async_set_comfort(self, **kwargs):
            seen.append(kwargs)
    await climate_platform.set_comfort(OlderRoom(), call)
    assert seen == [{"mode": "boost"}]
    link.stop()


def test_every_message_and_action_is_translated():
    from pathlib import Path
    import re
    component = Path(module.__file__).parent
    strings = json.loads((component / "strings.json").read_text(encoding="utf-8"))
    source = Path(module.__file__).read_text(encoding="utf-8")
    for key in set(re.findall(r'translation_key="([a-z_]+)"', source)) | set(module.E32_ERRORS.values()):
        assert key in strings["exceptions"], key
    services = set(re.findall(r"^([a-z_]+):", (component / "services.yaml").read_text(encoding="utf-8"), re.M))
    for name in ("set_room_override", "clear_room_override", "set_away", "clear_away"):
        assert name in services and name in strings["services"]
    # Eco and Night in the week planner's words; comfort, boost and none in Home Assistant's own.
    assert strings["entity"]["climate"]["room_thermostat"]["state_attributes"]["preset_mode"]["state"] == {
        "eco": "Eco", "sleep": "Night"}
    for step in ("comfort", "comfort_settings", "comfort_contacts", "comfort_contacts_room"):
        assert step in strings["options"]["step"]


@pytest.mark.asyncio
async def test_several_people_away_only_after_everyone_left_for_the_delay(hass, monkeypatch):
    """Home while anyone is home or unknown; away once the last person left the away delay ago (beta.23)."""
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "not_home")
    people = ["person.anna", "person.ben"]
    assert house_presence(hass, [], 15) == (None, None)
    assert house_presence(hass, people, 15, now) == (True, None)          # Anna is home
    hass.states.async_set("person.anna", "unavailable")
    assert house_presence(hass, people, 15, now) == (True, None)          # unknown: stay warm
    hass.states.async_set("person.anna", "Work")
    left = hass.states.get("person.anna").last_changed
    home, wait = house_presence(hass, people, 15, left + timedelta(minutes=5))
    assert home is True and wait == pytest.approx(600)                   # 10 more minutes
    assert house_presence(hass, people, 15, left + timedelta(minutes=15)) == (False, None)
    assert house_presence(hass, people, 0, left) == (False, None)         # no delay: away at once
    settings = comfort_options(entry({"presence_entities": people, "away_delay_min": 15}))
    assert comfort_payloads(hass, settings, set(), now=left + timedelta(minutes=5)) == [{"kind": "presence", "home": True}]
    assert comfort_payloads(hass, settings, set(), now=left + timedelta(minutes=16)) == [{"kind": "presence", "home": False}]
    assert comfort_payloads(hass, settings, set(), only="person.ben", now=left + timedelta(minutes=16)) == [
        {"kind": "presence", "home": False}]

    # The forwarder sends "home" now and "away" exactly when the delay has passed, not at the next refresh.
    timers = []
    monkeypatch.setattr(module, "async_call_later", lambda hass, delay, action: timers.append((delay, action)) or (lambda: None))
    sent = []
    hub = HeatingHub("fixture")
    hub.update(status(room_state("living")))
    forwarder = ComfortForwarder(hass, entry({"presence_entities": people, "away_delay_min": 15}), hub, sent.append,
                                 lambda hass, ids, action: lambda: None)
    forwarder.reconfigure()
    assert [json.loads(p) for p in sent] == [{"kind": "presence", "home": True}]
    assert len(timers) == 1 and 0 < timers[0][0] <= 15 * 60 + 1
    monkeypatch.setattr(module, "house_presence", lambda *a, **k: (False, None))  # the delay has passed
    timers[0][1](None)
    assert json.loads(sent[-1]) == {"kind": "presence", "home": False}
    forwarder.stop()


@pytest.mark.asyncio
async def test_the_away_delay_runs_from_when_the_last_person_left_home(hass, monkeypatch):
    """Another away zone, unavailable -> not_home and a Home Assistant restart do not restart the delay."""
    from test_daily_summary import FakeStore
    monkeypatch.setattr(module, "async_call_later", lambda hass, delay, action: lambda: None)
    t0 = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)
    people = ["person.anna", "person.ben"]
    store = FakeStore()
    hass.data[module.PRESENCE_MEMORY] = module.PresenceMemory(hass, store)
    hub = HeatingHub("fixture")
    hub.update(status(room_state("living")))
    sent = []
    forwarder = ComfortForwarder(hass, entry({"presence_entities": people, "away_delay_min": 15}), hub, sent.append,
                                 lambda hass, ids, action: lambda: None)

    def at(minutes, entity_id, value):
        hass.states.async_set(entity_id, value, timestamp=(t0 + timedelta(minutes=minutes)).timestamp())
        forwarder.publish(entity_id)  # what the state change event does
        return t0 + timedelta(minutes=minutes, seconds=30)

    at(0, "person.anna", "home")
    at(0, "person.ben", "home")
    at(5, "person.anna", "not_home")
    now = at(30, "person.ben", "Work")                                   # the last one leaves at 8:30
    home, wait = house_presence(hass, people, 15, now)
    assert home is True and wait == pytest.approx(14.5 * 60)
    assert house_presence(hass, people, 15, t0 + timedelta(hours=3)) == (False, None)
    now = at(180, "person.ben", "not_home")                               # leaves work: still away
    assert house_presence(hass, people, 15, now) == (False, None)
    assert house_presence(hass, people, 15, at(190, "person.anna", "unavailable")) == (True, None)  # unknown: warm
    assert house_presence(hass, people, 15, at(191, "person.anna", "not_home")) == (False, None)
    assert json.loads(sent[-1]) == {"kind": "presence", "home": False}

    # Home Assistant restarts: the people are restored with a new last_changed.
    data, _delay = store.pending
    restarted = module.PresenceMemory(hass, FakeStore(json.loads(json.dumps(data()))))
    await restarted.async_load()
    hass.data[module.PRESENCE_MEMORY] = restarted
    for entity_id in people:
        hass.states.async_remove(entity_id)
        at(240, entity_id, "not_home")
    assert house_presence(hass, people, 15, t0 + timedelta(minutes=241)) == (False, None)
    # Someone home and away again: the delay starts at that moment.
    at(300, "person.anna", "home")
    home, wait = house_presence(hass, people, 15, at(310, "person.anna", "not_home"))
    assert home is True and wait == pytest.approx(14.5 * 60)
    # Never seen home (a new person or a new install): its last change, as before.
    hass.states.async_set("person.carl", "not_home", timestamp=(t0 + timedelta(minutes=320)).timestamp())
    assert house_presence(hass, ["person.carl"], 15, t0 + timedelta(minutes=330))[0] is True
    forwarder.stop()


@pytest.mark.asyncio
async def test_the_presence_form_takes_several_people_and_the_away_delay(hass):
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "home")
    hass.states.async_set("light.lamp", "on")
    current = comfort_options(entry({"presence_entity": "person.anna"}))
    out = validate_presence(hass, {"presence_entities": ["person.anna", "person.ben"], "away_delay": 20}, current)
    assert out["presence_entities"] == ["person.anna", "person.ben"] and out["away_delay_min"] == 20
    assert out["presence_entity"] == "person.anna"  # HA 0.4.0b13 after a downgrade: the first person
    assert validate_presence(hass, {"presence_entities": [], "away_delay": 0}, current)["presence_entity"] is None
    # A person already chosen may be unavailable (a phone switched off); a new one must exist.
    hass.states.async_remove("person.ben")
    assert validate_presence(hass, {"presence_entities": ["person.anna", "person.ben"], "away_delay": 15},
                             out)["presence_entities"] == ["person.anna", "person.ben"]
    for bad, field in (({"presence_entities": ["light.lamp"]}, "presence_entities"),
                       ({"presence_entities": ["person.anna", "person.anna"]}, "presence_entities"),
                       ({"presence_entities": ["person.nobody"]}, "presence_entities"),
                       ({"presence_entities": [], "away_delay": 241}, "away_delay"),
                       ({"presence_entities": [], "away_delay": 1.5}, "away_delay")):
        with pytest.raises(ComfortError) as error:
            validate_presence(hass, bad, current)
        assert error.value.field == field


@pytest.mark.asyncio
async def test_the_room_says_what_smart_warm_up_does(hass):
    """E32 rc.3: the room's thermostat tells in plain words when heating starts for the next program step."""
    entity, hub, link = await climate(hass, FakeE32(), room_state("living"))
    entity.hass = hass
    assert entity.extra_state_attributes["smart_warm_up"] is None  # no plan without a trusted clock
    at = int(datetime(2026, 11, 4, 7, 0, tzinfo=timezone.utc).timestamp())
    hub.update_learned("living", ({"id": "living", "emitter": "floor", "readiness": "ready"},
                                  {"id": "living", "optimum_start": {"reason": "planned", "predicted_start_utc": at - 6000,
                                   "next_switch": {"utc": at, "target_c": 21}, "lead_minutes": 100, "confidence": "learned",
                                   "reachable": True, "start_now": False, "applies": True}}))
    text = entity.extra_state_attributes["smart_warm_up"]
    assert text.startswith("Smart warm-up: starts at ") and " so it is 21 °C at " in text
    hass.data.setdefault("open_thermostat", {})["e1"] = {"e32_flow": SimpleNamespace(settings={"apply_learned": False})}
    assert entity.extra_state_attributes["smart_warm_up"].startswith("Smart warm-up is off: heating starts at ")
    link.stop()


@pytest.mark.asyncio
async def test_the_room_says_how_the_last_morning_went(hass):
    """E32 rc.4: the thermostat's smart_warm_up attribute ends with the morning's check and what it changes."""
    entity, hub, link = await climate(hass, FakeE32(), room_state("living"))
    entity.hass = hass
    at = int(datetime(2026, 11, 4, 7, 0, tzinfo=timezone.utc).timestamp())
    arrival = {"factor": 1.1, "events": 3, "last_error_min": 12,
               "last_at_utc": int(datetime.now(timezone.utc).timestamp()) - 60}
    learned = {"id": "living", "emitter": "floor", "readiness": "ready"}
    hub.update_learned("living", (learned, {"id": "living", "arrival": arrival}))
    text = entity.extra_state_attributes["smart_warm_up"]
    assert text.startswith("Today warm at ") and text.endswith(" (12 min late); tomorrow 10 % earlier.")
    start = {"reason": "planned", "predicted_start_utc": at - 6000, "estimate": True,
             "next_switch": {"utc": at, "target_c": 21}, "lead_minutes": 100, "confidence": "default",
             "reachable": True, "start_now": False, "applies": True}
    hub.update_learned("living", (learned, {"id": "living", "arrival": arrival, "optimum_start": start}))
    text = entity.extra_state_attributes["smart_warm_up"]
    assert text.startswith("Smart warm-up: starts at ") and "(estimate; it learns from every morning)" in text
    assert text.endswith(" (12 min late); tomorrow 10 % earlier.") and ". Today warm at " in text
    hub.update_learned("living", (learned, None))
    assert entity.extra_state_attributes["smart_warm_up"] is None  # no plan (no trusted clock): nothing
    link.stop()
