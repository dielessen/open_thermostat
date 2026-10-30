"""One integration-page group per E32 room, the E32 and boiler group for the rest.

The registry fixture mirrors the owner's beta.18 page: the hub "OpenThermostat"
with an older Home Assistant room "Badkamer" (zone subentry, its own
"Badkamer — thermostaat" device) and "Installatie en ketel" holding the E32
room devices Badkamer and Woonkamer, the Bluetooth thermometer Woonkamer uses
and the E32 controller device.
"""
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import room_groups as module
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.installation_group import ensure_installation_group
from custom_components.open_thermostat.native_plan import native_entry_state
from custom_components.open_thermostat.product import PRODUCT_CONFIG, configuration_snapshot
from test_v1_native import entry as make_entry, room as make_room

BLE = "a4c138a3e8db"
PLAN = {"schema": 1, "revision": 7, "rooms": [
    {"id": "woonkamer", "name": "Woonkamer", "sources": [{"type": "ble", "id": BLE}]},
    {"id": "badkamer", "name": "Badkamer", "sources": [{"type": "ha", "id": "climate.thermostaat_badkamer"}]}]}


async def owner(hass):
    """The owner's registry before beta.19 (5 devices), with a few of the user's own choices."""
    await ar.async_load(hass, load_empty=True)
    hass.config.language = "nl"
    parent = make_entry(hass, room=make_room(hass, room_id="badkamer", suffix="Badkamer"))
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1})
    zone = next(s for s in parent.subentries.values() if s.subentry_type == "zone")
    devices, entities, areas = dr.async_get(hass), er.async_get(hass), ar.async_get(hass)
    hub = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={(DOMAIN, "fixture")},
                                      name="OpenThermostat")
    devices.async_update_device(hub.id, name_by_user="E32-regelaar — ketel en diagnose")
    install = ensure_installation_group(hass, parent)
    hass.config_entries.async_update_subentry(parent, parent.subentries[install], title="Installatie en ketel")
    legacy = devices.async_get_or_create(config_entry_id=parent.entry_id, config_subentry_id=zone.subentry_id,
                                         identifiers={(DOMAIN, "fixture_room_badkamer")},
                                         name="Badkamer — thermostaat", via_device_id=hub.id)
    legacy_climate = entities.async_get_or_create(
        "climate", DOMAIN, "fixture_room_badkamer_climate", config_entry=parent,
        config_subentry_id=zone.subentry_id, device_id=legacy.id, suggested_object_id="thermostaat_badkamer")
    zitkamer, bathroom = areas.async_create("Zitkamer"), areas.async_create("badkamer")

    def device(identifier, name, **extra):
        return devices.async_get_or_create(config_entry_id=parent.entry_id, config_subentry_id=install,
                                           identifiers={(DOMAIN, identifier)}, name=name, via_device_id=hub.id,
                                           **extra)

    def record(domain, unique_id, on, **changes):
        item = entities.async_get_or_create(domain, DOMAIN, unique_id, config_entry=parent,
                                            config_subentry_id=install, device_id=on.id)
        if changes:
            item = entities.async_update_entity(item.entity_id, **changes)
        return item

    hub_records = [record("sensor", "fixture_hub_heat_request", hub),
                   record("binary_sensor", "fixture_hub_heating_problem", hub)]
    living = device("fixture_e32_room_woonkamer", "Woonkamer")
    devices.async_update_device(living.id, area_id=zitkamer.id)  # the user's own area
    bath = device("fixture_e32_room_badkamer", "Badkamer")
    ble = device(f"fixture_e32_ble_{BLE}", "BTE_A3E8DB")
    rooms = {
        "woonkamer": [record("climate", "fixture_e32_room_woonkamer_thermostat", living),
                      record("sensor", "fixture_e32_room_woonkamer_temperature", living, name="Woonkamer warmte"),
                      record("binary_sensor", "fixture_e32_room_woonkamer_demand", living),
                      record("select", "fixture_e32_room_woonkamer_state", living, disabled_by=er.RegistryEntryDisabler.USER)],
        "badkamer": [record("climate", "fixture_e32_room_badkamer_thermostat", bath),
                     record("sensor", "fixture_e32_room_badkamer_temperature", bath, new_entity_id="sensor.bad_temp"),
                     record("sensor", "fixture_e32_room_badkamer_learning", bath)],
    }
    ble_records = [record("sensor", f"fixture_e32_ble_{BLE}_{metric}", ble) for metric in ("temperature", "humidity", "battery")]
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    return SimpleNamespace(entry=parent, zone=zone, install=install, hub=hub, legacy=legacy,
                           legacy_climate=legacy_climate, living=living, bath=bath, ble=ble,
                           hub_records=hub_records, rooms=rooms, ble_records=ble_records,
                           zitkamer=zitkamer, bathroom=bathroom)


def fake_hub(plan=PLAN, rooms=None, ble=None):
    return SimpleNamespace(plan=SimpleNamespace(plan=plan), rooms=rooms or {}, ble=ble or {},
                           add_listener=lambda listener: (lambda: None))


def layout(hass, entry):
    """Everything a group change could disturb: subentries, devices and entity records."""
    devices, entities = dr.async_get(hass), er.async_get(hass)
    return ({key: sub.as_dict() for key, sub in entry.subentries.items()},
            sorted((d.id, d.config_subentry_id, d.area_id, d.name, d.name_by_user)
                   for d in dr.async_entries_for_config_entry(devices, entry.entry_id)),
            sorted((e.id, e.entity_id, e.unique_id, e.name, e.device_id, e.config_subentry_id, e.disabled_by)
                   for e in er.async_entries_for_config_entry(entities, entry.entry_id)))


def groups_of(entry):
    return {room_id: entry.subentries[group_id] for room_id, group_id in module.room_group_ids(entry).items()}


def assert_kept(hass, records, group_id):
    entities = er.async_get(hass)
    for old in records:
        current = entities.async_get(old.entity_id)
        assert current is not None, old.entity_id
        assert (current.id, current.unique_id, current.name, current.device_id, current.disabled_by) == (
            old.id, old.unique_id, old.name, old.device_id, old.disabled_by)
        assert current.config_subentry_id == group_id


@pytest.mark.asyncio
async def test_the_owners_page_becomes_one_group_per_room(hass, caplog):
    o = await owner(hass)
    entry, devices = o.entry, dr.async_get(hass)
    groups = module.async_setup_room_groups(hass, entry, ensure_installation_group(hass, entry))
    await hass.async_block_till_done()  # Core's queued device-move events must keep every entity
    rooms = groups_of(entry)
    assert {room_id: (sub.title, sub.subentry_type, dict(sub.data), sub.unique_id) for room_id, sub in rooms.items()} == {
        "woonkamer": ("Woonkamer", "e32_room", {}, "e32_room_woonkamer"),
        "badkamer": ("Badkamer", "e32_room", {}, "e32_room_badkamer")}
    # The installation group keeps its identity and is called after what it holds now.
    assert entry.subentries[o.install].title == "E32 en ketel"
    for room_id, device in (("woonkamer", o.living), ("badkamer", o.bath)):
        current = devices.async_get(device.id)
        assert current.config_subentry_id == rooms[room_id].subentry_id and current.name == device.name
        assert_kept(hass, o.rooms[room_id], rooms[room_id].subentry_id)
    # The room's own thermostat lives in the room's group, under the IDs the user knows.
    assert er.async_get(hass).async_get("sensor.bad_temp").config_subentry_id == rooms["badkamer"].subentry_id
    # The user's area stays; a room without one gets the existing area of the same name (any case).
    assert devices.async_get(o.living.id).area_id == o.zitkamer.id
    assert devices.async_get(o.bath.id).area_id == o.bathroom.id
    assert len(ar.async_get(hass).async_list_areas()) == 2  # never a new area
    # Before the plan is read the sensor's room is unknown: it stays with the installation.
    assert devices.async_get(o.ble.id).config_subentry_id == o.install
    assert_kept(hass, o.ble_records, o.install)
    assert devices.async_get(o.hub.id).config_subentry_id == o.install
    assert_kept(hass, o.hub_records, o.install)
    # The older HA room is left to its own removal (legacy_rooms_flow): nothing of it moved.
    assert entry.subentries[o.zone.subentry_id].as_dict() == o.zone.as_dict()
    assert devices.async_get(o.legacy.id).config_subentry_id == o.zone.subentry_id
    assert er.async_get(hass).async_get(o.legacy_climate.entity_id) == o.legacy_climate
    # The plan says Woonkamer reads the Bluetooth thermometer: it joins Woonkamer.
    groups.attach(fake_hub())
    groups.reconcile()
    await hass.async_block_till_done()
    assert devices.async_get(o.ble.id).config_subentry_id == rooms["woonkamer"].subentry_id
    assert_kept(hass, o.ble_records, rooms["woonkamer"].subentry_id)
    assert "different config subentry" not in caplog.text
    # The next start changes nothing (idempotent), and Badkamer's area is not suggested again.
    devices.async_update_device(o.bath.id, area_id=None)
    before = layout(hass, entry)
    groups.stop()
    again = module.async_setup_room_groups(hass, entry, ensure_installation_group(hass, entry))
    again.attach(fake_hub())
    again.reconcile()
    await hass.async_block_till_done()
    assert layout(hass, entry) == before
    # Only the room plan adds rooms: nothing for the user to add on the integration page.
    assert "e32_room" not in OpenThermostatConfigFlow.async_get_supported_subentry_types(entry)


@pytest.mark.asyncio
async def test_groups_follow_the_room_plan_and_never_guard_configuration(hass):
    o = await owner(hass)
    entry, devices = o.entry, dr.async_get(hass)
    snapshot, private = configuration_snapshot(entry), native_entry_state(entry)
    groups = module.async_setup_room_groups(hass, entry, o.install)
    hub = fake_hub()
    groups.attach(hub)
    groups.reconcile()
    await hass.async_block_till_done()
    # Presentation only: an open editor or E32 link never sees "the setup changed".
    assert configuration_snapshot(entry) == snapshot and native_entry_state(entry) == private
    module.remember_configuration(hass, entry)
    rooms = groups_of(entry)
    # Renamed on the E32: the group follows; a title the user gave it stays.
    hub.plan.plan = {**PLAN, "revision": 8, "rooms": [{**PLAN["rooms"][0], "name": "Zitkamer"}, PLAN["rooms"][1]]}
    groups.reconcile()
    assert groups_of(entry)["woonkamer"].title == "Zitkamer"
    hass.config_entries.async_update_subentry(entry, entry.subentries[rooms["badkamer"].subentry_id], title="Bad")
    hub.plan.plan = {**hub.plan.plan, "revision": 9, "rooms": [hub.plan.plan["rooms"][0],
                                                               {**PLAN["rooms"][1], "name": "Badkamer boven"}]}
    groups.reconcile()
    assert groups_of(entry)["badkamer"].title == "Bad"
    assert module.presentation_only_update(hass, entry)  # the listener: no reload for any of this
    # Badkamer leaves the plan; its device goes first (native_entity_cleanup), then its group.
    from custom_components.open_thermostat.native_entity_cleanup import remove_room_devices
    hub.plan.plan = {**PLAN, "revision": 10, "rooms": [{**PLAN["rooms"][0], "sources": [{"type": "ha", "id": "sensor.x"}]}]}
    remove_room_devices(hass, entry, "fixture", ["badkamer"])
    groups.reconcile()
    await hass.async_block_till_done()
    assert set(groups_of(entry)) == {"woonkamer"} and devices.async_get(o.bath.id) is None
    # No room uses the thermometer any more: back to the installation, entities kept.
    assert devices.async_get(o.ble.id).config_subentry_id == o.install
    assert_kept(hass, o.ble_records, o.install)
    assert module.presentation_only_update(hass, entry)
    # A real configuration change still reloads as before.
    hass.config_entries.async_update_entry(entry, options={**entry.options, "something": True})
    assert not module.presentation_only_update(hass, entry)


@pytest.mark.asyncio
async def test_a_sensor_shared_by_two_rooms_stays_with_the_installation(hass):
    o = await owner(hass)
    groups = module.async_setup_room_groups(hass, o.entry, o.install)
    shared = {**PLAN, "rooms": [{**room, "sources": [{"type": "ble", "id": BLE}]} for room in PLAN["rooms"]]}
    groups.attach(fake_hub(shared))
    groups.reconcile()
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get(o.ble.id).config_subentry_id == o.install


@pytest.mark.asyncio
async def test_a_room_group_deleted_in_home_assistant_comes_back_with_its_ids(hass, monkeypatch):
    o = await owner(hass)
    entry, devices, entities = o.entry, dr.async_get(hass), er.async_get(hass)
    groups = module.async_setup_room_groups(hass, entry, o.install)
    groups.attach(fake_hub())
    groups.reconcile()
    await hass.async_block_till_done()
    module.remember_configuration(hass, entry)
    reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reload)
    living = groups_of(entry)["woonkamer"].subentry_id
    hass.config_entries.async_remove_subentry(entry, living)  # the integration page's delete
    await hass.async_block_till_done()
    assert devices.async_get(o.living.id) is None  # Core removed the device and its entities
    # The update listener: no configuration change, the room is still on the E32.
    assert module.presentation_only_update(hass, entry)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, module.restored_issue_id(entry, "woonkamer"))
    assert issue is not None and issue.translation_key == "room_group_restored" and not issue.is_fixable
    assert issue.translation_placeholders == {"room": "Woonkamer", "installation": entry.title}
    reload.assert_called_once_with(entry.entry_id)
    assert module.presentation_only_update(hass, entry) and reload.call_count == 1  # once
    # The reload: the platforms add the room's entities again into a new group with the same IDs.
    groups.stop()
    restarted = module.async_setup_room_groups(hass, entry, o.install)
    climate = SimpleNamespace(_attr_device_info={"identifiers": {(DOMAIN, "fixture_e32_room_woonkamer")},
                                                 "name": "Woonkamer"})
    group = restarted.subentry_for(climate, o.install)
    assert groups_of(entry)["woonkamer"].subentry_id == group != living
    device = devices.async_get_or_create(config_entry_id=entry.entry_id, config_subentry_id=group,
                                         identifiers={(DOMAIN, "fixture_e32_room_woonkamer")}, name="Woonkamer")
    assert device.id == o.living.id and device.area_id == o.zitkamer.id
    for old in o.rooms["woonkamer"]:
        back = entities.async_get_or_create(old.domain, DOMAIN, old.unique_id, config_entry=entry,
                                            config_subentry_id=group, device_id=device.id)
        assert (back.id, back.entity_id, back.name, back.disabled_by) == (old.id, old.entity_id, old.name, old.disabled_by)
    # Removing the room the intended way (Configure -> Rooms) clears the message with the group.
    restarted.attach(fake_hub({**PLAN, "rooms": PLAN["rooms"][1:]}))
    from custom_components.open_thermostat.native_entity_cleanup import remove_room_devices
    remove_room_devices(hass, entry, "fixture", ["woonkamer"])
    restarted.reconcile()
    assert "woonkamer" not in groups_of(entry)
    assert ir.async_get(hass).async_get_issue(DOMAIN, module.restored_issue_id(entry, "woonkamer")) is None


@pytest.mark.asyncio
async def test_the_group_restored_note_goes_by_itself_a_day_after_the_group_is_back(hass, monkeypatch):
    from datetime import timedelta
    from homeassistant.util import dt as dt_util
    o = await owner(hass)
    groups = module.async_setup_room_groups(hass, o.entry, o.install)
    groups.attach(fake_hub())
    groups.reconcile()
    await hass.async_block_till_done()
    assert "woonkamer" in groups_of(o.entry)  # the group is back
    issue_id = module.restored_issue_id(o.entry, "woonkamer")
    ir.async_create_issue(hass, DOMAIN, issue_id, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                          translation_key="room_group_restored")
    groups.reconcile()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None  # shown first
    later = dt_util.utcnow() + module.RESTORED_NOTICE + timedelta(minutes=1)
    monkeypatch.setattr(module.dt_util, "utcnow", lambda: later)
    groups.reconcile()  # the next telemetry message
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    groups.stop()


@pytest.mark.asyncio
async def test_a_group_deleted_for_a_room_no_longer_on_the_e32_stays_deleted(hass, monkeypatch):
    o = await owner(hass)
    groups = module.async_setup_room_groups(hass, o.entry, o.install)
    hub = fake_hub()
    groups.attach(hub)
    groups.reconcile()
    reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reload)
    hub.plan.plan = {**PLAN, "revision": 8, "rooms": PLAN["rooms"][:1]}
    hass.config_entries.async_remove_subentry(o.entry, groups_of(o.entry)["badkamer"].subentry_id)
    await hass.async_block_till_done()
    groups.reconcile(force=True)
    assert "badkamer" not in groups_of(o.entry) and not reload.called
    assert ir.async_get(hass).async_get_issue(DOMAIN, module.restored_issue_id(o.entry, "badkamer")) is None


@pytest.mark.asyncio
async def test_new_room_entities_are_added_to_their_room_group(hass, caplog):
    """Real entity platform: a new install gets each room's device straight in its own group."""
    from homeassistant.helpers.entity_platform import EntityPlatform
    from custom_components.open_thermostat import heating_link
    hass.config.language = "en"
    parent = make_entry(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1})
    devices = dr.async_get(hass)
    devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={(DOMAIN, "fixture")}, name="OpenThermostat")
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    install = ensure_installation_group(hass, parent)
    assert parent.subentries[install].title == "E32 and boiler"
    await ar.async_load(hass, load_empty=True)
    living_area = ar.async_get(hass).async_create("Living room")
    # Pre-registered without device or group (legacy_rooms_flow keeps a freed entity_id this way).
    early = er.async_get(hass).async_get_or_create("sensor", DOMAIN, "fixture_e32_room_woonkamer_temperature",
                                                   config_entry=parent, suggested_object_id="temperatuur_woonkamer")
    groups = module.async_setup_room_groups(hass, parent, install)
    hub = heating_link.HeatingHub("fixture")
    hub.plan = SimpleNamespace(plan={**PLAN, "rooms": [{"id": "woonkamer", "name": "Living room",
                                                         "sources": [{"type": "ble", "id": BLE}]}]})
    groups.attach(hub)
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="sensor",
                              platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30),
                              entity_namespace=None)
    platform.config_entry = parent

    def add(new, **options):
        hass.async_create_task(platform.async_add_entities(new, **options))
    stop = heating_link.track_entities(hub, add, {"config_subentry_id": install}, heating_link.wanted_sensors)
    try:
        hub.update({"schema": 1, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
                    "ha_entities": [], "rooms": [{"id": "woonkamer", "name": "Living room", "status": "ok",
                                                  "source": BLE, "temperature": 20.5, "setpoint": 21.0,
                                                  "demand": False}],
                    "ble_sensors": [{"id": BLE, "name": "BTE_A3E8DB", "temperature": 20.4, "humidity": 51,
                                     "battery": 90, "age_s": 3}]})
        await hass.async_block_till_done()
        group = groups_of(parent)["woonkamer"]
        assert group.title == "Living room"
        room = devices.async_get_device_by_identifier((DOMAIN, "fixture_e32_room_woonkamer"), parent.entry_id)
        sensor = devices.async_get_device_by_identifier((DOMAIN, f"fixture_e32_ble_{BLE}"), parent.entry_id)
        assert room.config_subentry_id == sensor.config_subentry_id == group.subentry_id
        assert room.area_id == living_area.id  # suggested once, when the device was created
        records = er.async_entries_for_config_entry(er.async_get(hass), parent.entry_id)
        assert {r.unique_id for r in records if r.config_subentry_id == group.subentry_id} == {
            "fixture_e32_room_woonkamer_temperature", "fixture_e32_room_woonkamer_setpoint",
            "fixture_e32_room_woonkamer_status", f"fixture_e32_ble_{BLE}_temperature",
            f"fixture_e32_ble_{BLE}_humidity", f"fixture_e32_ble_{BLE}_battery"}
        moved = er.async_get(hass).async_get(early.entity_id)
        assert (moved.id, moved.device_id, moved.config_subentry_id) == (early.id, room.id, group.subentry_id)
        assert "different config subentry" not in caplog.text
    finally:
        stop()
        await platform.async_reset()


def test_add_grouped_without_groups_adds_as_before():
    calls = []
    entity = SimpleNamespace(_attr_device_info={"identifiers": {(DOMAIN, "fixture_e32_room_woonkamer")}})
    module.add_grouped(SimpleNamespace(), lambda new, **options: calls.append((new, options)), [entity], {})
    assert calls == [([entity], {})]


def test_translations_name_the_room_type_and_the_restore_message():
    import json
    from pathlib import Path
    component = Path(module.__file__).parent
    for name, room in (("strings.json", "Room"), ("translations/en.json", "Room"),
                       ("translations/nl.json", "Ruimte"), ("translations/pl.json", "Pomieszczenie")):
        strings = json.loads((component / name).read_text(encoding="utf-8"))
        assert strings["config_subentries"]["e32_room"]["entry_type"] == room
        issue = strings["issues"]["room_group_restored"]
        assert "{room}" in issue["title"] and "{installation}" in issue["description"]
