"""HA room configuration/admission bounds: native flows, Store and registries."""
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntries, UnknownSubEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.v1_model import RoomBinding
from custom_components.open_thermostat.v1_config_flow import ZoneSubentryFlow, validate_room
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from test_v1_native import room, entry, LocalTransport


def bounded(binding):
    return replace(binding, minimum_target_centi_c=1600, maximum_target_centi_c=2300)


def inputs(binding, **updates):
    return {"room_id": binding.room_id, "name": "Bounded room",
            "temperature_entity": binding.temperature.entity_id,
            "actuator_entities": [binding.actuators[0].entity_id],
            "base_temperature": 21, "minimum_target_temperature": 16,
            "maximum_target_temperature": 23, "maximum_age_ms": 120000, **updates}


def flow(hass, parent, old=None):
    item = ZoneSubentryFlow()
    item.hass, item.handler = hass, (parent.entry_id, "zone")
    item.context = {"source": "reconfigure", "subentry_id": old.subentry_id} if old else {"source": "user"}
    return item


@pytest.mark.asyncio
async def test_old_room_defaults_roundtrip_without_migration(hass):
    data = room(hass).as_dict()
    data.pop("minimum_target_centi_c", None)
    data.pop("maximum_target_centi_c", None)
    restored = RoomBinding.from_dict(data)
    assert (restored.minimum_target_centi_c, restored.maximum_target_centi_c) == (500, 3500)
    assert RoomBinding.from_dict(restored.as_dict()) == restored


@pytest.mark.asyncio
async def test_native_create_and_reconfigure_persist_limits_and_new_bindings(hass):
    original = room(hass)
    parent = entry(hass)
    create = flow(hass, parent)
    form = await create.async_step_user()
    submitted = form["data_schema"](inputs(original))
    result = await create.async_step_user(submitted)
    assert result["type"] == "create_entry"
    assert result["data"]["minimum_target_centi_c"] == 1600
    assert result["data"]["maximum_target_centi_c"] == 2300
    # Flow-manager/core owns persistence; create the core subentry from flow result.
    from homeassistant.config_entries import ConfigSubentry
    old = ConfigSubentry(data=MappingProxyType(result["data"]), subentry_type="zone",
                         title=result["title"], unique_id=result["unique_id"])
    hass.config_entries.async_add_subentry(parent, old)
    changed = room(hass, room_id="b1b2b3b4", suffix="replacement")
    reconfigure = flow(hass, parent, old)
    result = await reconfigure.async_step_reconfigure(inputs(changed, room_id="ffffffff",
                                      minimum_target_temperature=17, maximum_target_temperature=24))
    assert result["type"] == "abort"
    assert old.unique_id == original.room_id
    assert old.data["room_id"] == original.room_id
    assert old.data["temperature"]["entity_id"] == changed.temperature.entity_id
    assert old.data["actuators"][0]["entity_id"] == changed.actuators[0].entity_id
    assert (old.data["minimum_target_centi_c"], old.data["maximum_target_centi_c"]) == (1700, 2400)
    # Flush official Store on normal HA stop, then initialize a second ConfigEntries.
    await hass.async_stop(force=True)
    restored_hass = HomeAssistant(hass.config.config_dir)
    restored_hass.config_entries = ConfigEntries(restored_hass, {})
    try:
        await restored_hass.config_entries.async_initialize()
        restored = restored_hass.config_entries.async_get_entry(parent.entry_id)
        saved = next(iter(restored.subentries.values()))
        assert saved.subentry_id == old.subentry_id
        assert dict(saved.data) == dict(old.data)
    finally:
        await restored_hass.async_stop(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("low,high,base", [(24, 20, 21), (16, 16, 16), (4, 23, 21),
                                         (16, 36, 21), (16, 23, 25), (True, 23, 21),
                                         (16, float("nan"), 21)])
async def test_invalid_bound_or_base_does_not_modify_existing_room(hass, low, high, base):
    binding = room(hass)
    parent = entry(hass, room=binding)
    old = next(iter(parent.subentries.values()))
    before = dict(old.data)
    result = await flow(hass, parent, old).async_step_reconfigure(inputs(binding,
        minimum_target_temperature=low, maximum_target_temperature=high, base_temperature=base))
    assert result["type"] == "form"
    assert result["errors"]
    assert dict(old.data) == before


@pytest.mark.asyncio
async def test_unavailable_source_can_be_configured_but_not_qualified(hass):
    binding = room(hass)
    hass.states.async_set(binding.temperature.entity_id, "unavailable")
    configured = validate_room(hass, entry(hass), inputs(binding))
    assert configured.minimum_target_centi_c == 1600
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [configured])
    runtime.attach_transport(LocalTransport())
    await runtime.async_start()
    try:
        assert runtime.observations[binding.room_id].quality != "qualified"
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_manual_target_outside_room_limits_never_enters_transport(hass):
    binding = bounded(room(hass))
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    transport = LocalTransport()
    runtime.attach_transport(transport)
    await runtime.async_start()
    try:
        for target in (15.9, 23.1, float("nan"), True):
            with pytest.raises(HomeAssistantError):
                await runtime.async_set_temperature(binding.room_id, target)
        assert transport.targets == []
        await runtime.async_set_temperature(binding.room_id, 16)
        await runtime.async_set_temperature(binding.room_id, 23)
        assert transport.targets == [(binding.room_id, 1600), (binding.room_id, 2300)]
        assert ShadowRoom("fixture", binding, runtime).min_temp == 16
        assert ShadowRoom("fixture", binding, runtime).max_temp == 23
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_schedule_outside_room_limits_fails_before_wire_build(hass, monkeypatch):
    from custom_components.open_thermostat import v1_mqtt
    from test_v1_native import reference
    binding = bounded(room(hass))
    registered = er.async_get(hass).async_get_or_create("schedule", "schedule", "weekly")
    binding = replace(binding, schedule=reference(hass, registered.entity_id))
    runtime = ShadowRuntime(hass, entry(hass), [binding])
    compile_schedule = AsyncMock(return_value={"transitions": [[1792368000, 2400]]})
    monkeypatch.setattr(v1_mqtt, "async_compile_schedule", compile_schedule)
    with pytest.raises(ValueError, match="room target limits"):
        await async_build_configuration(runtime)
    compile_schedule.return_value = {"transitions": [[1792368000, 1600], [1792368100, 2300]]}
    zones, mapping = await async_build_configuration(runtime)
    assert zones[0]["schedule"] == compile_schedule.return_value
    assert "minimum_target_centi_c" not in zones[0]  # no unnegotiated firmware keys
    assert mapping["rooms"][0]["minimum_target_centi_c"] == 1600


@pytest.mark.asyncio
async def test_native_remove_clears_owned_entity_not_source_and_rejects_unknown_id(hass):
    binding = room(hass)
    parent = entry(hass, room=binding)
    subentry = next(iter(parent.subentries.values()))
    registry = er.async_get(hass)
    own = registry.async_get_or_create("climate", "open_thermostat", "owned",
                       config_entry=parent, config_subentry_id=subentry.subentry_id)
    source_id = registry.async_get(binding.temperature.entity_id).id
    assert hass.config_entries.async_remove_subentry(parent, subentry.subentry_id)
    await hass.async_block_till_done()
    assert registry.async_get(own.entity_id) is None
    assert registry.async_get(binding.temperature.entity_id).id == source_id
    with pytest.raises(UnknownSubEntry):
        hass.config_entries.async_remove_subentry(parent, subentry.subentry_id)


@pytest.mark.asyncio
async def test_optional_setpoint_schedule_and_maxage_reconfigure_then_remove(hass):
    from test_v1_native import reference
    binding = room(hass)
    parent = entry(hass, room=binding)
    old = next(iter(parent.subentries.values()))
    registry = er.async_get(hass)
    wall = registry.async_get_or_create("number", "fixture_driver", "wall_target")
    schedule = registry.async_get_or_create("schedule", "schedule", "week_program")
    old_id = old.subentry_id
    first = await flow(hass, parent, old).async_step_reconfigure(inputs(binding,
        setpoint_entity=wall.entity_id, schedule_entity=schedule.entity_id,
        maximum_age_ms=90000, base_temperature=20.5))
    assert first["type"] == "abort"
    configured = RoomBinding.from_dict(dict(old.data))
    assert configured.setpoint == reference(hass, wall.entity_id)
    assert configured.schedule == reference(hass, schedule.entity_id)
    assert configured.maximum_age_ms == 90000
    assert configured.base_centi_c == 2050
    assert configured.minimum_target_centi_c == 1600
    second = await flow(hass, parent, old).async_step_reconfigure(inputs(binding))
    assert second["type"] == "abort"
    assert old.subentry_id == old_id and old.unique_id == binding.room_id
    assert old.data["setpoint"] is None and old.data["schedule"] is None


@pytest.mark.asyncio
async def test_invalid_wire_config_cannot_bypass_persisted_bounds(hass):
    data = room(hass).as_dict()
    for minimum, maximum in [(True, 2300), (1600, 2300.0), (2400, 2300), (1600, 2000)]:
        with pytest.raises(ValueError, match="invalid_target_range"):
            RoomBinding.from_dict({**data, "minimum_target_centi_c": minimum,
                                   "maximum_target_centi_c": maximum})
