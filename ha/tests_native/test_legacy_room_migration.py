"""Removing the older HA room keeps the E32 rooms that use it working.

Fixture mirroring the owner: the older HA room "Badkamer" (a zone subentry,
built on a temperature sensor and a radiator valve of another integration),
its own thermostat climate.thermostaat_badkamer, and an E32 plan with
woonkamer (active) and badkamer (inactive, radiator) whose only source is that
thermostat.
"""
import asyncio
from copy import deepcopy

import pytest
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import controller_setup_flow as setup, e32_link
from custom_components.open_thermostat import legacy_room_migration as migrate
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.controller_link import ControllerProvisioningError
from custom_components.open_thermostat.native_provisioning import local_device_descriptor
from test_e32_room_plan_link import PlanE32, badkamer, linked, owner_setup  # noqa: F401 (fixtures)

LEGACY = "climate.thermostaat_badkamer"
BLE = {"type": "ble", "id": "a4c138a3e8db"}


def e32_plan(badkamer_sources, *, woonkamer_sources=None, woonkamer_setpoint="climate.tado"):
    room = {"inactive_until": 0, "fallback_centi_c": 2000, "minimum_centi_c": 1000, "maximum_centi_c": 2400}
    return {"schema": 1, "revision": 7, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60, "rooms": [
        {**room, "id": "woonkamer", "name": "Woonkamer", "state": "active", "emitter": "floor",
         "sources": woonkamer_sources or [{"type": "ha", "id": "climate.tado"}, BLE],
         "setpoint_entity": woonkamer_setpoint},
        {**room, "id": "badkamer", "name": "Badkamer", "state": "inactive", "emitter": "radiator",
         "sources": badkamer_sources, "setpoint_entity": ""}]}


async def owner(hass, plan_for):
    """The owner's entry with the legacy thermostat at climate.thermostaat_badkamer and the E32 room thermostat."""
    parent, sub, source, climate, foreign, kept, binding = await owner_setup(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    entities.async_update_entity(climate, new_entity_id=LEGACY)
    hass.states.async_set("climate.tado", "heat", {"current_temperature": 20.5})
    device = devices.async_get_device_by_identifier((DOMAIN, "fixture_e32_room_badkamer"), parent.entry_id)
    room_climate = entities.async_get_or_create("climate", DOMAIN, "fixture_e32_room_badkamer_thermostat",
                                                config_entry=parent, device_id=device.id, has_entity_name=True)
    assert room_climate.entity_id == "climate.badkamer"  # generated from the room device name
    e32 = PlanE32(plan=plan_for(binding), source=local_device_descriptor(source), modern=True, adapter="ha1")
    e32.settings["mqtt"]["base"] = "fixture"
    return parent, sub, binding, foreign, e32


async def remove(hass, parent, **kwargs):
    return await setup.async_link_room_plan(hass, parent, parent.data[setup.CONTROLLER_ADDRESS],
                                            parent.data[setup.CONTROLLER_PASSWORD], remove_legacy_rooms=True,
                                            **kwargs)


def saved_plans(e32):
    return [c[1] for c in e32.calls if c[0] == "plan"]


def room_of(plan, room_id):
    return next(r for r in plan["rooms"] if r["id"] == room_id)


@pytest.mark.asyncio
async def test_the_source_moves_to_the_sensor_the_old_room_was_built_on(hass, linked, badkamer):
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    await ar.async_load(hass, load_empty=True)
    entities, areas = er.async_get(hass), ar.async_get(hass)
    area = areas.async_create("Badkamer")
    entities.async_update_entity(LEGACY, name="Bathroom thermostat", icon="mdi:radiator", area_id=area.id)
    zone_present = []
    e32.on_plan_save = lambda plan: zone_present.append(bool(e32_link.legacy_zones(parent)))
    linked["e32"] = e32
    await remove(hass, parent)
    # 1. The plan was written first, while the old room still existed.
    assert zone_present == [True]
    stored = e32.reads["/config/heating"]
    room = room_of(stored, "badkamer")
    assert room["sources"] == [{"type": "ha", "id": binding.temperature.entity_id}]
    assert room["state"] == "inactive" and room["name"] == "Badkamer"  # kept, state unchanged
    assert room_of(stored, "woonkamer") == room_of(e32_plan([]), "woonkamer")  # untouched
    # 2. The old room is gone; the radiator valve and sensor (another integration) are untouched.
    assert not e32_link.legacy_zones(parent)
    assert entities.async_get(binding.temperature.entity_id) is not None
    assert entities.async_get(binding.actuators[0].entity_id) is not None
    assert entities.async_get(foreign).device_id is None
    # 3. The E32 room thermostat took over the entity ID, name, icon and area.
    item = entities.async_get(LEGACY)
    assert item.unique_id == "fixture_e32_room_badkamer_thermostat" and item.platform == DOMAIN
    assert (item.name, item.icon, item.area_id) == ("Bathroom thermostat", "mdi:radiator", area.id)
    assert entities.async_get("climate.badkamer") is None
    assert not [i for i in ir.async_get(hass).issues if i[1].startswith(migrate.CHOOSE_SOURCE_ISSUE)]


@pytest.mark.asyncio
async def test_without_a_replacement_the_room_stays_and_asks_for_a_source(hass, linked, badkamer):
    def plan_for(binding):
        return e32_plan([{"type": "ha", "id": LEGACY}])
    parent, sub, binding, foreign, e32 = await owner(hass, plan_for)
    entities = er.async_get(hass)
    for entity_id in (binding.temperature.entity_id, binding.actuators[0].entity_id):
        entities.async_remove(entity_id)
        hass.states.async_remove(entity_id)
    linked["e32"] = e32
    await remove(hass, parent)
    # The E32 refuses a room without sources: the only one stays until the user chooses one.
    assert not saved_plans(e32)
    room = room_of(e32.reads["/config/heating"], "badkamer")
    assert room["sources"] == [{"type": "ha", "id": LEGACY}] and room["state"] == "inactive"
    assert not e32_link.legacy_zones(parent)
    # The ID stays free (a room thermostat there would be the room's own source).
    assert entities.async_get(LEGACY) is None and entities.async_get("climate.badkamer") is not None
    issue_id = migrate.choose_source_issue_id(parent, "badkamer")
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue.translation_key == "e32_room_choose_source" and issue.is_fixable
    assert issue.translation_placeholders["room"] == "Badkamer"
    # A plan read that still has the dead source keeps the note; a new source clears it.
    migrate.update_choose_source_issues(hass, parent, e32.reads["/config/heating"])
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None
    migrate.update_choose_source_issues(hass, parent, e32_plan([BLE]))
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


@pytest.mark.asyncio
async def test_other_sources_keep_their_order_and_a_lost_one_is_dropped(hass, linked, badkamer):
    def plan_for(binding):
        return e32_plan([BLE, {"type": "ha", "id": LEGACY}],
                        woonkamer_sources=[{"type": "ha", "id": "climate.tado"}, {"type": "ha", "id": LEGACY}, BLE])
    parent, sub, binding, foreign, e32 = await owner(hass, plan_for)
    linked["e32"] = e32
    await remove(hass, parent)
    stored = e32.reads["/config/heating"]
    sensor = {"type": "ha", "id": binding.temperature.entity_id}
    assert room_of(stored, "woonkamer")["sources"] == [{"type": "ha", "id": "climate.tado"}, sensor, BLE]
    assert room_of(stored, "badkamer")["sources"] == [BLE, sensor]


@pytest.mark.asyncio
async def test_without_a_replacement_a_lost_source_is_dropped_and_the_others_stay(hass, linked, badkamer):
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([BLE, {"type": "ha", "id": LEGACY}]))
    for entity_id in (binding.temperature.entity_id, binding.actuators[0].entity_id):
        er.async_get(hass).async_remove(entity_id)
        hass.states.async_remove(entity_id)
    linked["e32"] = e32
    await remove(hass, parent)
    room = room_of(e32.reads["/config/heating"], "badkamer")
    assert room["sources"] == [BLE] and room["state"] == "inactive"
    assert not ir.async_get(hass).async_get_issue(DOMAIN, migrate.choose_source_issue_id(parent, "badkamer"))
    # Nothing uses the old ID any more: the room thermostat takes it over.
    assert er.async_get(hass).async_get(LEGACY).unique_id == "fixture_e32_room_badkamer_thermostat"


@pytest.mark.asyncio
async def test_a_setpoint_entity_of_the_old_room_moves_or_is_cleared(hass, linked, badkamer):
    def plan_for(binding):
        return e32_plan([{"type": "ha", "id": "climate.tado"}], woonkamer_setpoint=LEGACY)
    parent, sub, binding, foreign, e32 = await owner(hass, plan_for)
    linked["e32"] = e32
    await remove(hass, parent)
    stored = e32.reads["/config/heating"]
    # The old room had no setpoint entity of its own: the room follows its week program.
    assert room_of(stored, "woonkamer")["setpoint_entity"] == ""
    assert room_of(stored, "woonkamer")["sources"] == room_of(e32_plan([]), "woonkamer")["sources"]


@pytest.mark.asyncio
async def test_a_setpoint_entity_moves_to_the_old_rooms_own_setpoint(hass, linked, badkamer):
    def plan_for(binding):
        return e32_plan([{"type": "ha", "id": "climate.tado"}], woonkamer_setpoint=LEGACY)
    parent, sub, binding, foreign, e32 = await owner(hass, plan_for)
    hass.states.async_set("number.wall_setpoint", "21")
    zone = e32_link.legacy_zones(parent)[0]
    hass.config_entries.async_update_subentry(parent, zone, data={**zone.data, "setpoint": {
        "entity_id": "number.wall_setpoint", "platform": None, "unique_id": None}})
    linked["e32"] = e32
    await remove(hass, parent)
    assert room_of(e32.reads["/config/heating"], "woonkamer")["setpoint_entity"] == "number.wall_setpoint"


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", ["invalid_sources", "storage_full"])
async def test_a_failed_plan_write_removes_nothing(hass, linked, badkamer, fail):
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    e32.plan_fail = fail
    linked["e32"] = e32
    with pytest.raises(ControllerProvisioningError, match="legacy_rooms_plan_failed") as caught:
        await remove(hass, parent)
    assert caught.value.device_may_have_changed is False
    entities = er.async_get(hass)
    assert e32_link.legacy_zones(parent)[0].subentry_id == sub.subentry_id
    assert entities.async_get(LEGACY).unique_id.endswith("_climate")  # the old thermostat is still there
    assert entities.async_get(foreign).device_id is not None
    assert not any(c[0] in ("save", "reboot") for c in e32.calls)  # the E32 link is not changed either
    assert parent.options["shadow_enabled"] is True  # and the running link was not paused


@pytest.mark.asyncio
async def test_a_concurrent_plan_save_is_read_again_once(hass, linked, badkamer):
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    e32.conflicts = 1
    linked["e32"] = e32
    await remove(hass, parent)
    assert len(saved_plans(e32)) == 2 and e32.reads["/config/heating"]["revision"] == 9
    assert not e32_link.legacy_zones(parent)


@pytest.mark.asyncio
async def test_a_different_outcome_than_confirmed_stops_before_anything_changes(hass, linked, badkamer):
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    _, shown = migrate.plan_migration(hass, parent, e32_plan([{"type": "ha", "id": "climate.tado"}]),
                                      e32_link.legacy_zones(parent))
    linked["e32"] = e32
    with pytest.raises(ControllerProvisioningError, match="legacy_rooms_plan_changed"):
        await remove(hass, parent, confirmed_migration=shown.signature())
    assert not saved_plans(e32) and e32_link.legacy_zones(parent)


@pytest.mark.asyncio
async def test_a_room_thermostat_id_the_user_chose_is_kept(hass, linked, badkamer):
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    entities = er.async_get(hass)
    entities.async_update_entity("climate.badkamer", new_entity_id="climate.my_bathroom", name="Mine")
    entities.async_update_entity(LEGACY, name="Bathroom thermostat")
    linked["e32"] = e32
    await remove(hass, parent)
    item = entities.async_get("climate.my_bathroom")
    assert item.unique_id == "fixture_e32_room_badkamer_thermostat" and item.name == "Mine"
    assert entities.async_get(LEGACY) is None


@pytest.mark.asyncio
async def test_the_owners_real_case_a_valve_of_another_integration_is_never_touched(hass, linked, badkamer):
    """The real badkamer source is a Zigbee valve (another integration), not the old room's thermostat."""
    def plan_for(binding):
        return e32_plan([{"type": "ha", "id": binding.actuators[0].entity_id}])
    parent, sub, binding, foreign, e32 = await owner(hass, plan_for)
    linked["e32"] = e32
    await remove(hass, parent)
    assert not saved_plans(e32)  # nothing in the plan changes
    assert room_of(e32.reads["/config/heating"], "badkamer")["sources"] == [
        {"type": "ha", "id": binding.actuators[0].entity_id}]
    entities = er.async_get(hass)
    assert entities.async_get(binding.actuators[0].entity_id).platform == "fixture_driver"
    # The old room's own thermostat is replaced by the room thermostat under the same ID.
    assert entities.async_get(LEGACY).unique_id == "fixture_e32_room_badkamer_thermostat"


@pytest.mark.asyncio
async def test_the_confirmation_lists_what_happens(hass, linked, badkamer):
    from custom_components.open_thermostat import repairs
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    hass.states.async_set(LEGACY, "heat", {"friendly_name": "Badkamer — thermostaat"})
    linked["e32"] = e32
    e32_link.update_legacy_rooms_issue(hass, parent)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent))
    flow = await repairs.async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass; flow.handler = DOMAIN; flow.flow_id = "fix"
    form = await flow.async_step_init()
    text = form["description_placeholders"]["changes"]
    assert (f"Badkamer on the E32 used 'Badkamer — thermostaat' ({LEGACY}) as its temperature source; "
            f"it will use '{binding.temperature.entity_id}' instead.") in text
    assert ("Your thermostat 'Badkamer — thermostaat' (climate.thermostaat_badkamer) is replaced by the "
            "Badkamer room thermostat; it keeps the entity ID climate.thermostaat_badkamer, so dashboards, "
            "automations and voice assistants keep working.") in text
    assert "The rooms on the E32 themselves stay, with their settings and week programs: Woonkamer, Badkamer." in text
    hass.config.language = "nl"
    form = await flow.async_step_init()
    assert "Badkamer op de E32 gebruikte 'Badkamer — thermostaat'" in form["description_placeholders"]["changes"]
    assert "De ruimtes op de E32 zelf blijven" in form["description_placeholders"]["changes"]
    hass.config.language = "en"
    # The E32 room plan changes after the list was shown: nothing is removed, a new list follows.
    e32.reads["/config/heating"] = e32_plan([BLE, {"type": "ha", "id": LEGACY}], woonkamer_setpoint=LEGACY)
    hass.states.async_remove(LEGACY)  # the old entity's state leaves with it
    await flow.async_step_legacy_rooms({})
    await asyncio.wait([flow._legacy_task])
    back = await flow.async_step_legacy_rooms_removing()
    assert back["step_id"] == "legacy_rooms"
    form = await flow.async_step_legacy_rooms()
    assert form["errors"] == {"base": "legacy_rooms_plan_changed"} and e32_link.legacy_zones(parent)
    assert "Woonkamer on the E32 took its desired temperature from" in form["description_placeholders"]["changes"]
    # Confirming the new list removes the old room.
    await flow.async_step_legacy_rooms({})
    await asyncio.wait([flow._legacy_task])
    await flow.async_step_legacy_rooms_removing()
    assert (await flow.async_step_legacy_rooms_done())["type"] == "create_entry"
    stored = e32.reads["/config/heating"]
    assert room_of(stored, "badkamer")["sources"] == [BLE, {"type": "ha", "id": binding.temperature.entity_id}]
    assert room_of(stored, "woonkamer")["setpoint_entity"] == ""


@pytest.mark.asyncio
async def test_an_unreadable_plan_is_said_and_nothing_starts(hass, linked, badkamer):
    from custom_components.open_thermostat import repairs
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    e32.reads["/config/heating"] = {"unexpected": True}
    linked["e32"] = e32
    e32_link.update_legacy_rooms_issue(hass, parent)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent))
    flow = await repairs.async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass; flow.handler = DOMAIN; flow.flow_id = "fix"
    form = await flow.async_step_init()
    assert "could not be read just now" in form["description_placeholders"]["changes"]
    form = await flow.async_step_legacy_rooms({})
    assert form["type"] == "form" and form["errors"] == {"base": "legacy_rooms_plan_unreadable"}
    assert getattr(flow, "_legacy_task", None) is None and e32_link.legacy_zones(parent)


class FakeLink:
    def __init__(self, plan):
        self.plan, self.changes = deepcopy(plan), []

    async def async_read(self):
        return self.plan

    def room(self, room_id):
        return next((r for r in self.plan["rooms"] if r["id"] == room_id), None)

    async def async_change_room(self, room_id, change):
        change(self.room(room_id))
        self.changes.append(room_id)
        return self.plan


@pytest.mark.asyncio
async def test_the_choose_source_fix_only_chooses_a_source(hass, linked, badkamer):
    from types import SimpleNamespace
    from custom_components.open_thermostat import repairs
    parent, sub, binding, foreign, e32 = await owner(hass, lambda b: e32_plan([{"type": "ha", "id": LEGACY}]))
    link = FakeLink(e32_plan([{"type": "ha", "id": LEGACY}]))
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"heating_hub": SimpleNamespace(plan=link)}
    migration = migrate.Migration((migrate.Change("badkamer", "Badkamer", "source", LEGACY, None, kept=True),), (), ())
    migrate.note_rooms_without_source(hass, parent, migration)
    issue_id = migrate.choose_source_issue_id(parent, "badkamer")
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    flow = await repairs.async_create_fix_flow(hass, issue_id, issue.data)
    flow.hass = hass; flow.handler = DOMAIN; flow.flow_id = "fix2"
    form = await flow.async_step_init()
    assert form["step_id"] == "choose_source" and list(form["data_schema"].schema) == ["source"]
    form = await flow.async_step_choose_source({"source": "sensor.nowhere"})
    assert form["errors"] == {"source": "e32_source_not_found"}
    done = await flow.async_step_choose_source({"source": binding.temperature.entity_id})
    assert done["type"] == "create_entry"
    room = link.room("badkamer")
    assert room["sources"] == [{"type": "ha", "id": binding.temperature.entity_id}] and room["state"] == "inactive"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
