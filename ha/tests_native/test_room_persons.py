"""Persons per room (beta.23, room.presence.v1): per-room aggregation in HA and forwarding to the E32."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import e32_comfort as module
from custom_components.open_thermostat.e32_comfort import (
    CONF_COMFORT, ComfortError, ComfortForwarder, away_waits, comfort_options, comfort_payloads, room_persons,
    supports_room_presence, validate_room_persons, with_room_persons)
from custom_components.open_thermostat.heating_link import HeatingHub


def entry(settings=None):
    return SimpleNamespace(entry_id="e1", options={CONF_COMFORT: settings} if settings is not None else {})


def status(*room_ids, room_presence=True):
    away = {"on": False, "source": "none", "target_c": 15, "until": None, "presence": "unknown", "mode": "auto"}
    if room_presence:
        away["room_presence"] = True
    return {"schema": 1, "revision": 2, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
            "ha_entities": [], "away": away,
            "rooms": [{"id": r, "name": r.title(), "state": "active", "status": "ok", "source": "a4c138000001",
                       "temperature": 19.5, "setpoint": 20.5, "setpoint_source": "schedule", "demand": False}
                      for r in room_ids]}


def test_room_persons_are_stored_per_room_and_checked():
    settings = comfort_options(entry({"room_persons": {"bedroom": ["person.anna", "person.ben"],
                                                       "attic": ["light.no", "zone.home"], "bad": "person.x"}}))
    # Only presence domains survive; zones are allowed by the house list but filtered nowhere else.
    assert settings["room_persons"] == {"bedroom": ["person.anna", "person.ben"], "attic": ["zone.home"]}
    assert room_persons(entry({"room_persons": {"bedroom": ["person.anna"]}}), "bedroom") == ["person.anna"]
    assert room_persons(entry(), "bedroom") == []
    updated = with_room_persons(settings, "study", ["person.anna"])
    assert updated["room_persons"]["study"] == ["person.anna"]
    assert "bedroom" not in with_room_persons(settings, "bedroom", [])["room_persons"]


@pytest.mark.asyncio
async def test_the_room_form_accepts_known_or_existing_persons_only(hass):
    hass.states.async_set("person.anna", "home")
    assert validate_room_persons(hass, ["person.anna"]) == ["person.anna"]
    assert validate_room_persons(hass, []) == []
    # A person already chosen may be unavailable now (a phone off); a new one must exist.
    assert validate_room_persons(hass, ["person.gone"], known=["person.gone"]) == ["person.gone"]
    for bad in (["person.gone"], ["light.kitchen"], ["person.anna", "person.anna"]):
        with pytest.raises(ComfortError) as err:
            validate_room_persons(hass, bad)
        assert (err.value.field, err.value.code) == ("persons", "presence_entity_invalid")


@pytest.mark.asyncio
async def test_a_room_is_home_while_one_of_its_persons_is_home_and_away_after_the_delay(hass):
    now = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "not_home")
    hass.states.async_set("person.carl", "home")
    settings = comfort_options(entry({"presence_entities": ["person.anna", "person.ben", "person.carl"],
                                      "away_delay_min": 15,
                                      "room_persons": {"bedroom": ["person.ben"], "living": ["person.anna", "person.carl"],
                                                       "attic": ["person.ben"]}}))
    rooms = {"bedroom", "living", "study"}
    # Without the E32's room.presence.v1 nothing per room is sent (an older E32).
    assert comfort_payloads(hass, settings, rooms, now=now) == [{"kind": "presence", "home": True}]
    ben_left = hass.states.get("person.ben").last_changed
    payloads = comfort_payloads(hass, settings, rooms, now=ben_left + timedelta(minutes=16), room_presence=True)
    # Ben's bedroom goes away although the house is home; the attic is not in the plan.
    assert payloads == [{"kind": "presence", "home": True},
                        {"kind": "room_presence", "room": "bedroom", "home": False},
                        {"kind": "room_presence", "room": "living", "home": True}]
    # Within the away delay the room still counts as home.
    assert {"kind": "room_presence", "room": "bedroom", "home": True} in comfort_payloads(
        hass, settings, rooms, now=ben_left + timedelta(minutes=5), room_presence=True)
    # Unknown never counts as away ("bij twijfel blijft het warm").
    hass.states.async_set("person.ben", "unavailable")
    assert {"kind": "room_presence", "room": "bedroom", "home": True} in comfort_payloads(
        hass, settings, rooms, now=now + timedelta(hours=1), room_presence=True)
    # Only the changed entity: only the rooms (and the house) that it belongs to.
    hass.states.async_set("person.carl", "not_home")
    only = comfort_payloads(hass, settings, rooms, only="person.carl", now=now, room_presence=True)
    assert only == [{"kind": "presence", "home": True}, {"kind": "room_presence", "room": "living", "home": True}]
    assert all(len(json.dumps(p, separators=(",", ":")).encode()) <= 192 for p in payloads)  # RoomOverrides::inputBytes


@pytest.mark.asyncio
async def test_a_room_stays_away_when_its_person_moves_to_another_away_zone(hass):
    t0 = datetime(2026, 11, 1, 8, 0, tzinfo=timezone.utc)
    memory = hass.data[module.PRESENCE_MEMORY] = module.PresenceMemory(hass)
    settings = comfort_options(entry({"presence_entities": ["person.anna"], "away_delay_min": 15,
                                      "room_persons": {"bedroom": ["person.ben"]}}))

    def at(minutes, value):
        hass.states.async_set("person.ben", value, timestamp=(t0 + timedelta(minutes=minutes)).timestamp())
        memory.observe("person.ben", hass.states.get("person.ben"))
        return t0 + timedelta(minutes=minutes, seconds=30)

    hass.states.async_set("person.anna", "home")
    at(0, "home")
    at(10, "Work")
    bedroom = {"kind": "room_presence", "room": "bedroom", "home": False}
    assert bedroom in comfort_payloads(hass, settings, {"bedroom"}, now=t0 + timedelta(hours=2), room_presence=True)
    for minutes, value in ((180, "not_home"), (181, "unavailable"), (182, "not_home")):
        now = at(minutes, value)
    assert bedroom in comfort_payloads(hass, settings, {"bedroom"}, now=now, room_presence=True)


@pytest.mark.asyncio
async def test_the_shortest_away_delay_over_the_house_and_the_rooms(hass):
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "not_home")
    settings = comfort_options(entry({"presence_entities": ["person.anna", "person.ben"], "away_delay_min": 15,
                                      "room_persons": {"bedroom": ["person.ben"]}}))
    wait = away_waits(hass, settings, {"bedroom"})
    assert wait is not None and 0 < wait <= 15 * 60       # Ben's room; the house has Anna home
    assert away_waits(hass, settings, set()) is None       # without rooms: only the house, which is home
    assert away_waits(hass, {**settings, "room_persons": {}}, {"bedroom"}) is None


def test_the_e32_announces_persons_per_room():
    hub = HeatingHub("fixture")
    assert supports_room_presence(hub) is False
    hub.update(status("living", room_presence=False))
    assert supports_room_presence(hub) is False
    hub.update(status("living"))
    assert supports_room_presence(hub) is True


@pytest.mark.asyncio
async def test_the_forwarder_sends_room_presence_only_to_an_e32_that_understands_it(hass, monkeypatch):
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "not_home")
    settings = {"presence_entities": ["person.anna", "person.ben"], "away_delay_min": 15,
                "room_persons": {"bedroom": ["person.ben"]}}
    timers = []
    monkeypatch.setattr(module, "async_call_later", lambda hass, delay, action: timers.append((delay, action)) or (lambda: None))
    sent, tracked = [], []

    # An older E32 (no away.room_presence): only the house, no room timer.
    hub = HeatingHub("fixture")
    hub.update(status("bedroom", room_presence=False))
    forwarder = ComfortForwarder(hass, entry(settings), hub, sent.append,
                                 lambda hass, ids, action: tracked.append((ids, action)) or (lambda: None))
    forwarder.reconfigure()
    assert tracked[0][0] == ["person.anna", "person.ben"]
    assert [json.loads(p) for p in sent] == [{"kind": "presence", "home": True}]
    assert timers == []
    forwarder.stop()

    # E32 beta.23: the bedroom too, and "away" exactly when Ben's delay has passed.
    sent.clear()
    hub.update(status("bedroom"))
    forwarder = ComfortForwarder(hass, entry(settings), hub, sent.append, lambda hass, ids, action: lambda: None)
    forwarder.reconfigure()
    assert [json.loads(p) for p in sent] == [{"kind": "presence", "home": True},
                                             {"kind": "room_presence", "room": "bedroom", "home": True}]
    assert len(timers) == 1 and 0 < timers[0][0] <= 15 * 60 + 1
    real = module.house_presence
    monkeypatch.setattr(module, "house_presence",
                        lambda hass, people, delay, now=None: (False, None) if people == ["person.ben"] else real(hass, people, delay, now))
    timers[0][1](None)
    assert {"kind": "room_presence", "room": "bedroom", "home": False} in [json.loads(p) for p in sent[-2:]]
    forwarder.stop()


# -- the room form (Configure -> Rooms -> the room -> Persons) -------------------------------------------

from homeassistant.data_entry_flow import section  # noqa: E402
from test_e32_room_flow import manager, product, room_form, rooms_menu, shown  # noqa: E402,F401
from test_room_plan import FakeE32  # noqa: E402


def persons_of(parent):
    return comfort_options(parent)["room_persons"]


@pytest.mark.asyncio
async def test_the_room_form_has_a_persons_section_and_saving_it_writes_no_plan(hass, manager):
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "not_home")
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    reconfigured = []
    hass.data["open_thermostat"][parent.entry_id]["comfort_forwarder"] = SimpleNamespace(
        reconfigure=lambda: reconfigured.append(True))
    form = await room_form(manager, parent, "woonkamer")
    persons = next(v for k, v in form["data_schema"].schema.items() if str(k) == "persons")
    assert isinstance(persons, section) and persons.options["collapsed"] is True  # none yet: folded
    picker = next(v for k, v in persons.schema.schema.items() if str(k) == "persons")
    assert picker.config["multiple"] is True
    assert {"domain": ["person"]} in picker.config["filter"] and {"domain": ["zone"]} not in picker.config["filter"]
    await manager.async_configure(form["flow_id"], shown(form))  # the fixture room gets its week program first
    form = await room_form(manager, parent, "woonkamer")
    posts = len(e32.posts)
    result = await manager.async_configure(form["flow_id"], {**shown(form), "persons": {"persons": ["person.anna", "person.ben"]}})
    assert result["step_id"] == "e32_rooms_saved", result
    assert len(e32.posts) == posts  # persons live in Home Assistant, not in the E32 plan
    assert persons_of(parent) == {"woonkamer": ["person.anna", "person.ben"]}
    assert reconfigured  # the forwarder follows the new persons at once
    # Shown again, unfolded, when the room is edited; unchanged is unchanged.
    form = await room_form(manager, parent, "woonkamer")
    assert shown(form)["persons"] == {"persons": ["person.anna", "person.ben"]}
    persons = next(v for k, v in form["data_schema"].schema.items() if str(k) == "persons")
    assert persons.options["collapsed"] is False
    result = await manager.async_configure(form["flow_id"], shown(form))
    assert result["reason"] == "e32_room_unchanged"
    # A person that does not exist is refused in the section.
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "persons": {"persons": ["person.nobody"]}})
    assert result["errors"] == {"persons": "presence_entity_invalid"}
    # Clearing the persons: the room follows the house again.
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "persons": {}})
    assert result["step_id"] == "e32_rooms_saved" and persons_of(parent) == {}


@pytest.mark.asyncio
async def test_removing_a_room_removes_its_persons(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    hass.config_entries.async_update_entry(parent, options={**parent.options, CONF_COMFORT: {"room_persons": {
        "badkamer": ["person.anna"], "woonkamer": ["person.ben"]}}})
    flow = await rooms_menu(manager, parent)
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_pick"})
    flow = await manager.async_configure(flow["flow_id"], {"room": "badkamer", "action": "remove"})
    result = await manager.async_configure(flow["flow_id"], {"confirm_remove": True})
    assert result["step_id"] == "e32_rooms_removed", result
    assert persons_of(parent) == {"woonkamer": ["person.ben"]}
