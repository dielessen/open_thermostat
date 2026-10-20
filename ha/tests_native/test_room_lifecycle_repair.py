"""Actual HA APIs + integration callbacks; MQTT boundary only, no live network."""
from collections import defaultdict
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.config_entries import ConfigSubentry, UnknownSubEntry
from custom_components.open_thermostat import climate, sensor, number, binary_sensor
from custom_components.open_thermostat.heating import HeatingTracker
from custom_components.open_thermostat.v1_config_flow import ZoneSubentryFlow
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_v1_native import entry, room, MODE_LEGACY, LocalTransport

ROOM = {"id": "a1b2c3d4", "name": "Original", "currentTemp": 1950,
        "tempSet": 2100, "currentHumidity": 50, "batteryLevel": 80,
        "enabledState": "on", "isBeingHeatedState": "on", "currentProgram": "default"}

@pytest_asyncio.fixture
async def legacy(hass, monkeypatch):
    parent = entry(hass, mode=MODE_LEGACY)
    callbacks = defaultdict(list)
    added = []
    async def subscribe(hass, topic, callback, **kwargs):
        callbacks[topic].append(callback)
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    publish = AsyncMock()
    monkeypatch.setattr(mqtt, "async_publish", publish)
    tracker = HeatingTracker(hass, parent)
    hass.data.setdefault("open_thermostat", {})[parent.entry_id] = {
        "duration_minutes": {}, "heating_tracker": tracker}
    await tracker.async_start()
    for module in (climate, sensor, number, binary_sensor):
        await module.async_setup_entry(hass, parent, lambda entities, **kwargs: added.extend(entities))
    def emit(topic, payload):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        for callback in tuple(callbacks["fixture/"+topic]):
            callback(SimpleNamespace(topic="fixture/"+topic, payload=raw, retain=False))
    yield emit, added, tracker, publish
    await tracker.async_stop()

@pytest.mark.asyncio
async def test_removed_legacy_climate_never_resurrects_on_hub_online(legacy):
    emit, added, tracker, publish = legacy
    emit("status", "on")
    emit("room_data", {"rooms": [ROOM]})
    entity = next(x for x in added if isinstance(x, climate.OpenThermostatRoom))
    assert entity.available
    emit("room_data", {"rooms": []})
    assert not entity.available
    emit("status", "off"); emit("status", "on")
    assert not entity.available
    with pytest.raises(HomeAssistantError):
        await entity.async_set_temperature(temperature=21)
    publish.assert_not_awaited()

@pytest.mark.asyncio
async def test_all_removed_legacy_room_entities_remain_unavailable_keep_history(legacy):
    emit, added, tracker, publish = legacy
    emit("status", "on"); emit("room_data", {"rooms": [ROOM]})
    tracker.rooms[ROOM["id"]].heating_seconds = 123
    tracker.rooms[ROOM["id"]].estimated_energy_kwh = 4.5
    tracker.rooms[ROOM["id"]].rated_power = 900
    room_entities = [e for e in added if "_room_a1b2c3d4_" in (e.unique_id or "")]
    assert room_entities and all(e.available for e in room_entities)
    emit("room_data", {"rooms": []})
    assert all(not e.available for e in room_entities), [
        e.unique_id for e in room_entities if e.available]
    emit("status", "off"); emit("status", "on")
    assert all(not e.available for e in room_entities)
    assert tracker.rooms[ROOM["id"]].heating_seconds == 123
    assert tracker.rooms[ROOM["id"]].estimated_energy_kwh == 4.5
    # Readd same stable ID: same entities and preserved counters, no duplicate IDs.
    count = len(added)
    emit("room_data", {"rooms": [{**ROOM, "name": "Renamed"}]})
    assert len(added) == count
    assert all(e.available for e in room_entities)
    assert tracker.rooms[ROOM["id"]].rated_power == 900

@pytest.mark.asyncio
async def test_invalid_ids_do_not_create_rooms_or_remove_valid_snapshot_on_bad_envelope(legacy):
    emit, added, tracker, publish = legacy
    emit("status", "on")
    emit("room_data", {"rooms": [{**ROOM, "id": "../absent"}, {**ROOM, "id": "not-a-room"}]})
    assert not tracker.rooms
    assert not [e for e in added if "_room_" in (e.unique_id or "")]
    emit("room_data", {"rooms": [ROOM]})
    entity = next(x for x in added if isinstance(x, climate.OpenThermostatRoom))
    emit("room_data", "not JSON")
    emit("room_data", {"rooms": None})
    assert entity.available
    assert ROOM["id"] in tracker.rooms

@pytest.mark.asyncio
async def test_native_zone_create_edit_remove_reload_and_registry_cleanup(hass):
    binding = room(hass)
    parent = entry(hass)
    reload = AsyncMock()
    parent.add_update_listener(lambda hass, updated: reload(updated.entry_id))
    sub = ConfigSubentry(data=binding.as_dict(), subentry_type="zone",
                         title=binding.name, unique_id=binding.room_id)
    assert hass.config_entries.async_add_subentry(parent, sub)
    await hass.async_block_till_done()
    reload.assert_awaited_once_with(parent.entry_id)
    reload.reset_mock()
    flow = ZoneSubentryFlow(); flow.hass = hass
    flow.handler = (parent.entry_id, "zone")
    flow.context = {"source": "reconfigure", "subentry_id": sub.subentry_id}
    result = await flow.async_step_reconfigure({
        "name": "Renamed", "temperature_entity": binding.temperature.entity_id,
        "actuator_entities": [binding.actuators[0].entity_id], "maximum_age_ms": 120000,
        "room_id": "ffffffff"})
    assert result["type"] == "abort"
    assert sub.unique_id == binding.room_id and sub.data["room_id"] == binding.room_id
    await hass.async_block_till_done()
    reload.assert_awaited_once()
    reload.reset_mock()
    entity = er.async_get(hass).async_get_or_create(
        "climate", "open_thermostat", "fixture_room_"+binding.room_id+"_climate",
        config_entry=parent, config_subentry_id=sub.subentry_id)
    assert entity.config_subentry_id == sub.subentry_id
    assert hass.config_entries.async_remove_subentry(parent, sub.subentry_id)
    await hass.async_block_till_done()
    reload.assert_awaited_once()
    assert not parent.subentries
    assert er.async_get(hass).async_get(entity.entity_id) is None
    with pytest.raises(UnknownSubEntry):
        hass.config_entries.async_remove_subentry(parent, sub.subentry_id)
    assert not parent.subentries

@pytest.mark.asyncio
async def test_unknown_shadow_room_setpoint_is_rejected_without_transport_write(hass):
    binding = room(hass); parent = entry(hass, enabled=True, room=binding)
    runtime = ShadowRuntime(hass, parent, [binding])
    transport = LocalTransport(); runtime.attach_transport(transport)
    await runtime.async_start()
    with pytest.raises(HomeAssistantError):
        await runtime.async_set_temperature("deadbeef", 21)
    assert not transport.targets
    await runtime.async_stop()

@pytest.mark.asyncio
async def test_removing_one_room_preserves_other_room_and_hub(legacy):
    emit, added, tracker, publish = legacy
    other = {**ROOM, "id": "b1c2d3e4", "name": "Other"}
    emit("status", "on")
    emit("room_data", {"rooms": [ROOM, other]})
    emit("room_data", {"rooms": [other]})
    emit("status", "off"); emit("status", "on")
    removed = [e for e in added if "_room_a1b2c3d4_" in (e.unique_id or "")]
    retained = [e for e in added if "_room_b1c2d3e4_" in (e.unique_id or "")]
    assert removed and retained
    assert all(not e.available for e in removed)
    assert all(e.available for e in retained)
    assert tracker.online and not tracker.is_heating(ROOM["id"])
