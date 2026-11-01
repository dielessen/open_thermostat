"""Window and door contacts per E32 room: in the room form, under Comfort, and the room's window state.

Any Home Assistant binary sensor of the class window, door, opening or garage
door works (Zigbee, Z-Wave, Shelly, Bluetooth, a template ...). The contacts
live in the entry's comfort settings; the forwarder sends the room's combined
state to the E32, which pauses the room at frost protection after the delay
(RoomOverrides.h) and reports "window" in the room's comfort.
"""
from types import SimpleNamespace

import pytest
from homeassistant.data_entry_flow import section

from custom_components.open_thermostat.e32_comfort import (
    CONF_COMFORT, comfort_options, contact_delay_text, room_contacts, with_room_contacts)
from custom_components.open_thermostat.heating_link import ROOM_STATUSES, HeatingHub, RoomStatusSensor, room_status
from test_e32_room_flow import NEW_ROOM, manager, product, room_form, rooms_menu, shown  # noqa: F401
from test_room_plan import STATUS, FakeE32

BOTH_ROOMS = {**STATUS, "rooms": [*STATUS["rooms"], {**STATUS["rooms"][0], "id": "badkamer", "name": "Badkamer"}]}


def contacts_of(parent):
    return comfort_options(parent)["contacts"]


def sensors(hass):
    hass.states.async_set("binary_sensor.raam_zigbee", "off", {"device_class": "window", "friendly_name": "Raam"})
    hass.states.async_set("binary_sensor.deur_zwave", "off", {"device_class": "door", "friendly_name": "Deur"})
    hass.states.async_set("binary_sensor.shelly_opening", "on", {"device_class": "opening"})
    hass.states.async_set("binary_sensor.beweging", "off", {"device_class": "motion"})


def window_field(form):
    marker, value = next((k, v) for k, v in form["data_schema"].schema.items() if str(k) == "window")
    assert isinstance(value, section)
    return marker, value


@pytest.mark.asyncio
async def test_the_room_form_has_an_open_window_section_for_any_brand(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    _, window = window_field(form)
    assert window.options["collapsed"] is False  # findable: open in the room itself
    picker = next(v for k, v in window.schema.schema.items() if str(k) == "contacts")
    assert picker.config["multiple"] is True
    assert picker.config["filter"] == [{"domain": ["binary_sensor"],
                                        "device_class": ["window", "door", "opening", "garage_door"]}]
    assert form["description_placeholders"]["delay"] == "2 min"  # the default 120 s, in the explanation


def test_the_delay_reads_as_minutes_or_seconds():
    settings = comfort_options(SimpleNamespace(options={}))
    assert contact_delay_text(settings) == "2 min"
    assert contact_delay_text({**settings, "contact_delay_s": 45}) == "45 s"
    assert contact_delay_text({**settings, "contact_delay_s": 90}) == "90 s"
    assert contact_delay_text({**settings, "contact_delay_s": 0}) == "0 s"
    assert with_room_contacts({**settings, "contacts": {"a": ["binary_sensor.x"]}}, "a", [])["contacts"] == {}


@pytest.mark.asyncio
async def test_a_new_room_keeps_its_contacts_under_its_new_id(hass, manager):
    sensors(hass)
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    result = await manager.async_configure(form["flow_id"], {
        **NEW_ROOM, "window": {"contacts": ["binary_sensor.raam_zigbee", "binary_sensor.shelly_opening"]}})
    assert result["step_id"] == "e32_rooms_saved", result
    room = e32.plan["rooms"][-1]
    assert room["id"] == "slaapkamer_zoe" and "window" not in room and "contacts" not in room  # not in the E32 plan
    assert contacts_of(parent) == {"slaapkamer_zoe": ["binary_sensor.raam_zigbee", "binary_sensor.shelly_opening"]}
    assert "- Slaapkamer Zoë: " in result["description_placeholders"]["rooms"]
    assert "window/door contacts: 2" in result["description_placeholders"]["rooms"]
    # Shown again when the room is edited.
    form = await room_form(manager, parent, "slaapkamer_zoe")
    assert shown(form)["window"] == {"contacts": ["binary_sensor.raam_zigbee", "binary_sensor.shelly_opening"], "contact_delay": 2.0}


@pytest.mark.asyncio
async def test_changing_only_the_contacts_writes_no_plan(hass, manager):
    sensors(hass)
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    reconfigured = []
    hass.data["open_thermostat"][parent.entry_id]["comfort_forwarder"] = SimpleNamespace(
        reconfigure=lambda: reconfigured.append(True))
    form = await room_form(manager, parent, "woonkamer")
    await manager.async_configure(form["flow_id"], shown(form))  # the fixture room gets its week program first
    form = await room_form(manager, parent, "woonkamer")
    posts = len(e32.posts)
    result = await manager.async_configure(form["flow_id"], {
        **shown(form), "window": {"contacts": ["binary_sensor.deur_zwave"]}})
    assert result["step_id"] == "e32_rooms_saved", result
    assert len(e32.posts) == posts  # the E32 plan is unchanged
    assert contacts_of(parent) == {"woonkamer": ["binary_sensor.deur_zwave"]}
    assert reconfigured  # the forwarder follows the new sensors at once
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], shown(form))
    assert result["reason"] == "e32_room_unchanged"
    # Removing all contacts switches the pause off for the room.
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "window": {}})
    assert result["step_id"] == "e32_rooms_saved" and contacts_of(parent) == {}
    assert len(e32.posts) == posts


@pytest.mark.asyncio
async def test_only_window_door_and_opening_sensors_are_accepted(hass, manager):
    sensors(hass)
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    posts = len(e32.posts)
    for contacts, error in ((["binary_sensor.beweging"], "not_contact_sensor"),
                            (["binary_sensor.missing"], "not_contact_sensor"),
                            ([f"binary_sensor.raam_{i}" for i in range(9)], "contacts_invalid")):
        form = await manager.async_configure(form["flow_id"], {**shown(form), "window": {"contacts": contacts}})
        assert form["type"] == "form" and form["errors"] == {"base": error}, form
        assert shown(form)["window"] == {"contacts": contacts, "contact_delay": 2.0}  # what was entered stays
    assert len(e32.posts) == posts and contacts_of(parent) == {}


@pytest.mark.asyncio
async def test_a_configured_contact_that_is_unavailable_never_blocks_saving(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    hass.config_entries.async_update_entry(parent, options={
        **parent.options, CONF_COMFORT: {"contacts": {"woonkamer": ["binary_sensor.lege_batterij"]}}})
    form = await room_form(manager, parent, "woonkamer")
    assert shown(form)["window"] == {"contacts": ["binary_sensor.lege_batterij"], "contact_delay": 2.0}
    result = await manager.async_configure(form["flow_id"], {**shown(form), "name": "Huiskamer"})
    assert result["step_id"] == "e32_rooms_saved", result
    assert contacts_of(parent) == {"woonkamer": ["binary_sensor.lege_batterij"]}


@pytest.mark.asyncio
async def test_removing_a_room_removes_its_contacts(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    hass.config_entries.async_update_entry(parent, options={**parent.options, CONF_COMFORT: {"contacts": {
        "badkamer": ["binary_sensor.badkamer_raam"], "woonkamer": ["binary_sensor.raam_zigbee"]}}})
    flow = await rooms_menu(manager, parent)
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_pick"})
    flow = await manager.async_configure(flow["flow_id"], {"room": "badkamer", "action": "remove"})
    result = await manager.async_configure(flow["flow_id"], {"confirm_remove": True})
    assert result["step_id"] == "e32_rooms_removed", result
    assert contacts_of(parent) == {"woonkamer": ["binary_sensor.raam_zigbee"]}


@pytest.mark.asyncio
async def test_comfort_asks_the_room_first_and_shows_that_rooms_own_contacts(hass, manager):
    """Before: one form with a room list and a sensor list prefilled for the first room only."""
    sensors(hass)
    e32 = FakeE32()
    parent, hub = product(hass, e32)
    hub.update(BOTH_ROOMS)
    hass.config_entries.async_update_entry(parent, options={**parent.options, CONF_COMFORT: {"contacts": {
        "badkamer": ["binary_sensor.raam_zigbee"], "woonkamer": ["binary_sensor.deur_zwave"]}}})
    await hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "comfort"})
    assert flow["menu_options"] == ["comfort_settings", "comfort_contacts"]
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "comfort_contacts"})
    assert flow["step_id"] == "comfort_contacts"
    assert [str(k) for k in flow["data_schema"].schema] == ["room"]
    assert flow["description_placeholders"]["rooms"] == "- Badkamer: Raam\n- Woonkamer: Deur"
    flow = await manager.async_configure(flow["flow_id"], {"room": "badkamer"})
    assert flow["step_id"] == "comfort_contacts_room"
    assert flow["description_placeholders"] == {"room": "Badkamer", "delay": "2 min"}
    picker = next(k for k in flow["data_schema"].schema if str(k) == "contacts")
    assert picker.description["suggested_value"] == ["binary_sensor.raam_zigbee"]  # the bathroom's, not the first room's
    flow = await manager.async_configure(flow["flow_id"], {"contacts": ["binary_sensor.beweging"]})
    assert flow["errors"] == {"contacts": "not_contact_sensor"}
    result = await manager.async_configure(flow["flow_id"], {
        "contacts": ["binary_sensor.raam_zigbee", "binary_sensor.shelly_opening"]})
    assert result["reason"] == "comfort_saved"
    assert contacts_of(parent) == {"badkamer": ["binary_sensor.raam_zigbee", "binary_sensor.shelly_opening"],
                                   "woonkamer": ["binary_sensor.deur_zwave"]}  # the other room is untouched
    assert room_contacts(parent, "woonkamer") == ["binary_sensor.deur_zwave"]


def test_the_room_status_shows_an_open_window_unless_a_measurement_problem_comes_first():
    room = {"id": "woonkamer", "status": "ok"}
    assert room_status(room) == "ok"
    assert room_status({**room, "comfort": {"mode": "window_open", "window": "open"}}) == "window_open"
    assert room_status({**room, "comfort": {"mode": "program", "window": "pending"}}) == "window_pending"
    assert room_status({**room, "status": "fallback", "comfort": {"window": "open"}}) == "window_open"
    for problem in ("stale", "lost", "inactive"):  # a problem to fix (or off) stays visible
        assert room_status({**room, "status": problem, "comfort": {"window": "open"}}) == problem
    assert room_status({**room, "comfort": {"window": "ajar"}}) == "ok"
    assert room_status({**room, "comfort": "open"}) == "ok"
    assert room_status({**room, "status": "window_open"}) is None  # only the E32's own statuses come in
    assert set(ROOM_STATUSES) == {"ok", "fallback", "stale", "lost", "inactive", "window_open", "window_pending"}


def test_the_control_status_entity_reads_the_window_from_the_room_comfort():
    hub = HeatingHub("fixture")
    rooms = [{**STATUS["rooms"][0], "comfort": {"mode": "window_open", "window": "open", "target_c": 8}}]
    hub.update({**STATUS, "rooms": rooms})
    sensor = RoomStatusSensor(hub, hub.rooms["woonkamer"])
    assert sensor.native_value == "window_open"
    assert sensor.extra_state_attributes["window"] == "open"
    hub.update({**STATUS})
    assert sensor.native_value == "ok" and sensor.extra_state_attributes["window"] is None


@pytest.mark.asyncio
async def test_each_room_has_its_own_pause_delay(hass, manager):
    """beta.23: the delay is set per room in its "Windows and doors" block (default 2 min)."""
    from custom_components.open_thermostat.e32_comfort import comfort_payloads, room_contact_delay
    sensors(hass)
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    posts = len(e32.posts)
    form = await room_form(manager, parent, "woonkamer")
    assert shown(form)["window"] == {"contact_delay": 2.0}
    result = await manager.async_configure(form["flow_id"], {
        **shown(form), "window": {"contacts": ["binary_sensor.raam_zigbee"], "contact_delay": 5}})
    assert result["step_id"] == "e32_rooms_saved", result
    settings = comfort_options(parent)
    assert settings["contact_delays"] == {"woonkamer": 300} and room_contact_delay(settings, "woonkamer") == 300
    assert room_contact_delay(settings, "badkamer") == 120  # another room keeps the default
    assert comfort_payloads(hass, settings, {"woonkamer"}) == [
        {"kind": "contact", "room": "woonkamer", "open": False, "delay_s": 300}]
    posts = len(e32.posts)
    form = await room_form(manager, parent, "woonkamer")
    assert form["description_placeholders"]["delay"] == "5 min" and shown(form)["window"]["contact_delay"] == 5.0
    # Only the delay changed: saved; out of range: refused in the form.
    result = await manager.async_configure(form["flow_id"], {**shown(form), "window": {**shown(form)["window"], "contact_delay": 1}})
    assert result["step_id"] == "e32_rooms_saved" and comfort_options(parent)["contact_delays"] == {"woonkamer": 60}
    form = await room_form(manager, parent, "woonkamer")
    from homeassistant.data_entry_flow import InvalidData
    with pytest.raises(InvalidData):  # the number field itself allows 0..30 minutes
        await manager.async_configure(form["flow_id"], {**shown(form), "window": {**shown(form)["window"], "contact_delay": 31}})
    # Without contacts the room has no delay of its own.
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "window": {"contact_delay": 1}})
    assert comfort_options(parent)["contact_delays"] == {} and contacts_of(parent) == {}
