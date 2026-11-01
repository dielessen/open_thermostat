"""Optional entity-ID tidy (1.0): Home Assistant's own IDs, a preview with where each entity is used,
rename on confirmation with history and statistics moving along, user choices skipped, undo."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from homeassistant import loader
from homeassistant.components import recorder
from homeassistant.components.recorder.tasks import SynchronizeTask
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.setup import async_setup_component

from custom_components.open_thermostat import entity_id_tidy as tidy
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32
from test_v1_native import entry

LEFTOVER = "E32-regelaar — ketel en diagnose"
LONG = "sensor.woonkamer_e32_regelaar_ketel_en_diagnose_boiler_measured_flow_temperature"


async def install(hass, e):
    """The owner's shape: a hub in area Woonkamer and a room device "Badkamer" in area Badkamer."""
    from homeassistant.helpers import floor_registry as fr, label_registry as lr
    for registry in (fr, lr, ar):  # the conftest loads devices and entities only
        try:
            await registry.async_load(hass, load_empty=True)
        except AssertionError:
            pass  # already loaded
    areas, devices, entities = ar.async_get(hass), dr.async_get(hass), er.async_get(hass)
    woonkamer, badkamer = areas.async_create("Woonkamer"), areas.async_create("Badkamer")
    hub = devices.async_get_or_create(config_entry_id=e.entry_id, identifiers={("open_thermostat", "fixture")},
                                      name="OpenThermostat E32")
    devices.async_update_device(hub.id, area_id=woonkamer.id)
    room = devices.async_get_or_create(config_entry_id=e.entry_id, identifiers={("open_thermostat", "fixture_room_badkamer")},
                                       name="Badkamer")
    devices.async_update_device(room.id, area_id=badkamer.id)
    flow = entities.async_get_or_create("sensor", "open_thermostat", "fixture_flow", config_entry=e, device_id=hub.id,
                                        object_id_base="Flow temperature", has_entity_name=True,
                                        original_name="Flow temperature")
    demand = entities.async_get_or_create("binary_sensor", "open_thermostat", "fixture_badkamer_demand", config_entry=e,
                                          device_id=room.id, has_entity_name=True, original_name="Heat demand",
                                          object_id_base="Heat demand")
    # The IDs these entities got on the owner's installation from the test setup's long device name.
    flow = entities.async_update_entity(flow.entity_id, new_entity_id=LONG)
    demand = entities.async_update_entity(
        demand.entity_id, new_entity_id="binary_sensor.woonkamer_e32_regelaar_ketel_en_diagnose_badkamer_heat_demand")
    return hub, room, flow, demand


@pytest.mark.asyncio
async def test_the_plan_uses_home_assistants_own_ids_said_once_and_skips_what_the_user_chose(hass, monkeypatch):
    loader.async_setup(hass)
    e = entry(hass)
    hub, room, flow, demand = await install(hass, e)
    entities = er.async_get(hass)
    named = entities.async_get_or_create("sensor", "open_thermostat", "fixture_named", config_entry=e, device_id=hub.id,
                                         suggested_object_id="woonkamer_openthermostat_e32_return_temperature",
                                         original_name="Return temperature", has_entity_name=True)
    entities.async_update_entity(named.entity_id, name="Mijn retour")  # the user named it
    custom = entities.async_get_or_create("sensor", "open_thermostat", "fixture_custom", config_entry=e, device_id=hub.id,
                                          suggested_object_id="ketel_druk", original_name="Pressure", has_entity_name=True)
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([]))
    monkeypatch.setattr(tidy, "async_energy_text", _async(""))
    plan = await tidy.async_plan(hass, e)
    pairs = {r.old: r.new for r in plan.renames}
    assert pairs[flow.entity_id] == "sensor.woonkamer_openthermostat_e32_flow_temperature"
    assert pairs[demand.entity_id] == "binary_sensor.badkamer_heat_demand"  # not badkamer_badkamer_…
    assert plan.skipped[named.entity_id] == "user_named" and plan.skipped[custom.entity_id] == "user_entity_id"
    assert named.entity_id not in pairs and custom.entity_id not in pairs


@pytest.mark.asyncio
async def test_a_taken_target_is_skipped_and_never_suffixed(hass, monkeypatch):
    loader.async_setup(hass)
    e = entry(hass)
    _, _, flow, _ = await install(hass, e)
    hass.states.async_set("sensor.woonkamer_openthermostat_e32_flow_temperature", "1")  # another entity holds it
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([]))
    monkeypatch.setattr(tidy, "async_energy_text", _async(""))
    plan = await tidy.async_plan(hass, e)
    assert plan.skipped[flow.entity_id] == "target_taken"
    assert flow.entity_id not in {r.old for r in plan.renames}


@pytest.mark.asyncio
async def test_the_preview_names_every_place_an_entity_is_used(hass, monkeypatch):
    loader.async_setup(hass)
    e = entry(hass)
    _, _, flow, demand = await install(hass, e)
    from homeassistant.components import automation, script
    monkeypatch.setattr(automation, "automations_with_entity", lambda h, eid: ["automation.cv_melding"] if eid == flow.entity_id else [])
    monkeypatch.setattr(script, "scripts_with_entity", lambda h, eid: [])
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([("Woning", '{"cards":[{"entity":"%s"}]}' % demand.entity_id),
                                                               ("Leeg", '{"cards":[]}')]))
    monkeypatch.setattr(tidy, "async_energy_text", _async('{"energy_sources":[{"stat_energy_from":"%s"}]}' % flow.entity_id))
    plan = await tidy.async_plan(hass, e)
    used = {r.old: r.used_in for r in plan.renames}
    assert used[flow.entity_id] == ["automation.cv_melding", "energy"]
    assert used[demand.entity_id] == ["dashboard: Woning"]
    text = tidy.preview_text(plan, False)
    assert f"{flow.entity_id} → sensor.woonkamer_openthermostat_e32_flow_temperature" in text and "energy" in text
    assert plan.unused == []  # both used somewhere: "only unused" renames nothing
    # The words around the list follow the form's language.
    assert "(used in: automation.cv_melding, energy)" in text
    assert "(gebruikt in: dashboard: Woning)" in tidy.preview_text(plan, False, "nl")
    assert "(używane w: dashboard: Woning)" in tidy.preview_text(plan, False, "pl")
    assert "(used in: " in tidy.preview_text(plan, False, "de") and "gebruikt" not in text


@pytest.mark.asyncio
async def test_a_scene_that_uses_an_entity_is_listed(hass, monkeypatch):
    """Scenes (YAML and the scene editor) live in Home Assistant's own scene platform."""
    from types import SimpleNamespace
    from homeassistant.components.homeassistant.scene import DATA_PLATFORM
    loader.async_setup(hass)
    e = entry(hass)
    _, _, _, demand = await install(hass, e)
    scene = SimpleNamespace(entity_id="scene.avond", scene_config=SimpleNamespace(states={demand.entity_id: None}))
    hass.data[DATA_PLATFORM] = SimpleNamespace(entities={"scene.avond": scene})
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([]))
    monkeypatch.setattr(tidy, "async_energy_text", _async(""))
    plan = await tidy.async_plan(hass, e)
    assert {r.old: r.used_in for r in plan.renames}[demand.entity_id] == ["scene.avond"]
    assert demand.entity_id not in {r.old for r in plan.unused}


async def barrier(hass):
    await hass.async_block_till_done()
    instance = recorder.get_instance(hass)
    done = hass.loop.create_future()
    instance.queue_task(SynchronizeTask(done))
    await done
    return instance


@pytest.mark.asyncio
async def test_a_rename_keeps_the_history_and_statistics_and_can_be_undone(hass, monkeypatch):
    loader.async_setup(hass)
    async_initialize_recorder(hass)
    path = Path(hass.config.path("tidy.db"))
    assert await async_setup_component(hass, "recorder", {"recorder": {
        "db_url": "sqlite:///" + str(path), "auto_purge": False, "auto_repack": False, "commit_interval": 0}})
    await hass.async_start()
    e = entry(hass)
    _, _, flow, _ = await install(hass, e)
    start = datetime.now(timezone.utc) - timedelta(seconds=1)
    attrs = {"unit_of_measurement": "°C", "device_class": "temperature", "state_class": "measurement"}
    for value in ("41", "42", "43"):
        hass.states.async_set(flow.entity_id, value, attrs)
    instance = await barrier(hass)
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([]))
    monkeypatch.setattr(tidy, "async_energy_text", _async(""))
    plan = await tidy.async_plan(hass, e)
    new = "sensor.woonkamer_openthermostat_e32_flow_temperature"
    done = await tidy.async_apply(hass, e, plan.renames)
    assert done[new] == flow.entity_id
    await barrier(hass)
    history = await instance.async_add_executor_job(
        lambda: get_significant_states(hass, start, None, [new], significant_changes_only=False))
    assert [s.state for s in history[new]][:3] == ["41", "42", "43"]  # the old ID's history, under the new ID
    # Undo within 30 days puts the old ID back, with its history. (A real entity moves its state with the
    # rename; this fixture wrote states by hand, so the old ID's last state is removed here.)
    hass.states.async_remove(flow.entity_id)
    assert (await tidy.async_undo_available(hass, e))[new] == flow.entity_id
    undone = await tidy.async_undo(hass, e)
    assert undone[flow.entity_id] == new and er.async_get(hass).async_get(flow.entity_id) is not None
    await barrier(hass)
    back = await instance.async_add_executor_job(
        lambda: get_significant_states(hass, start, None, [flow.entity_id], significant_changes_only=False))
    assert [s.state for s in back[flow.entity_id]][:3] == ["41", "42", "43"]
    assert await tidy.async_undo_available(hass, e) == {}


@pytest.mark.asyncio
async def test_undo_leaves_an_entity_whose_old_id_is_taken_and_expires_after_30_days(hass, monkeypatch):
    loader.async_setup(hass)
    e = entry(hass)
    _, _, flow, _ = await install(hass, e)
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([]))
    monkeypatch.setattr(tidy, "async_energy_text", _async(""))
    old = flow.entity_id
    await tidy.async_apply(hass, e, (await tidy.async_plan(hass, e)).renames)
    hass.states.async_set(old, "x")  # something else took the old ID meanwhile
    undone = await tidy.async_undo(hass, e)
    assert old not in undone and er.async_get(hass).async_get(old) is None  # left as it is
    assert "binary_sensor.woonkamer_e32_regelaar_ketel_en_diagnose_badkamer_heat_demand" in undone  # the free one went back
    # A new tidy, then 31 days later: undo is no longer offered.
    await tidy.async_apply(hass, e, (await tidy.async_plan(hass, e)).renames)
    store = tidy._store(hass, e.entry_id)
    saved = await store.async_load()
    if saved:
        saved["at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        await store.async_save(saved)
    assert await tidy.async_undo_available(hass, e) == {}


@pytest.mark.asyncio
async def test_advanced_offers_the_tidy_and_it_renames_only_after_confirmation(hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())
    _, _, flow_entity, _ = await install(hass, parent)
    monkeypatch.setattr(tidy, "async_dashboard_texts", _async([]))
    monkeypatch.setattr(tidy, "async_energy_text", _async(""))
    flow = await manager.async_init(parent.entry_id)
    advanced = await manager.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    assert "entity_ids" in advanced["menu_options"] and "entity_ids_undo" not in advanced["menu_options"]
    form = await manager.async_configure(flow["flow_id"], {"next_step_id": "entity_ids"})
    assert form["type"] == FlowResultType.FORM and flow_entity.entity_id in form["description_placeholders"]["preview"]
    refused = await manager.async_configure(form["flow_id"], {"scope": "all", "confirm": False})
    assert refused["errors"] == {"base": "entity_ids_confirm"}
    assert er.async_get(hass).async_get(flow_entity.entity_id) is not None  # nothing renamed yet
    result = await manager.async_configure(form["flow_id"], {"scope": "all", "confirm": True})
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "entity_ids_done"
    assert er.async_get(hass).async_get("sensor.woonkamer_openthermostat_e32_flow_temperature") is not None


def _async(value):
    async def fn(*_args, **_kwargs):
        return value
    return fn


def test_the_shadow_route_also_drops_the_test_setup_device_name():
    """The owner's installation runs in shadow mode; before 1.0 only the legacy route dropped the hub's
    leftover test-setup name, so the long name (and the long proposed IDs) stayed."""
    import inspect
    import custom_components.open_thermostat as component
    source = inspect.getsource(component.async_setup_entry)  # the effective (shadow-aware) setup
    assert "if mode == MODE_LEGACY:" in source
    assert source.index("_drop_test_setup_name(hass, entry)") > source.index("if mode != MODE_SHADOW:")
