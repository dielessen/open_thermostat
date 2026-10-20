"""Real HA native APIs, not replacement HA modules or fake event buses."""
from datetime import timedelta
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from homeassistant.data_entry_flow import AbortFlow

import custom_components.open_thermostat as integration
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.v1_config_flow import (
    ShadowOptionsFlow, ZoneSubentryFlow, validate_room, reference,
)
from custom_components.open_thermostat.v1_model import (
    RoomBinding, QualifiedReport, RoomDecision, CONF_ENABLED,
    CONF_MODE, MODE_SHADOW, MODE_LEGACY, integration_mode,
)
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_profile_c import ProfileCActuator


def entry(hass, *, enabled=False, mode=MODE_SHADOW, version=2, room=None):
    subentries = []
    if room:
        subentries.append({"subentry_type": "zone", "title": room.name,
                           "unique_id": room.room_id, "data": room.as_dict()})
    item = ConfigEntry(domain="open_thermostat", title="test", version=version,
                       minor_version=1, data={"topic_prefix": "fixture", CONF_MODE: mode, "adapter_id": "ha1"},
                       options={CONF_ENABLED: enabled, CONF_MODE: mode}, source="user",
                       unique_id="fixture", discovery_keys=MappingProxyType({}),
                       subentries_data=subentries)
    # Test bootstrap only; avoid async_add's real integration/dependency setup.
    hass.config_entries._entries[item.entry_id] = item
    return item


def room(hass, room_id="a1b2c3d4", suffix="room", age=120000):
    registry = er.async_get(hass)
    source = registry.async_get_or_create(
        "sensor", "fixture_driver", f"{suffix}_sensor", suggested_object_id=f"{suffix}_temp")
    actuator = registry.async_get_or_create(
        "climate", "fixture_driver", f"{suffix}_trv", suggested_object_id=f"{suffix}_trv")
    hass.states.async_set(source.entity_id, "19.5",
                          {"device_class": "temperature", "unit_of_measurement": "°C"})
    hass.states.async_set(actuator.entity_id, "heat", {
        "temperature": 18, "current_temperature": 19.5, "supported_features": 1,
        "min_temp": 5, "max_temp": 30, "target_temp_step": 0.5})
    return RoomBinding(room_id, suffix, reference(hass, source.entity_id),
                       (reference(hass, actuator.entity_id),), maximum_age_ms=age)


class LocalTransport:
    """Local seam only, not a proposed wire implementation or firmware emulator."""
    ready = True
    def __init__(self):
        self.observations = []
        self.targets = []
        self.closed = False
    async def async_observation(self, room_id, observation):
        self.observations.append((room_id, observation))
    async def async_setpoint(self, room_id, centi_c):
        self.targets.append((room_id, centi_c))
    async def async_close(self):
        self.closed = True


def source_profile(state, event_kind):
    if "physical_sample_key" not in state.attributes:
        return None
    return QualifiedReport(state.attributes["physical_sample_key"],
                           state.attributes["physical_sample_at"])


def physical_state(hass, binding, key="new-1", value="20", age=0):
    hass.states.async_set(binding.temperature.entity_id, value, {
        "device_class": "temperature", "unit_of_measurement": "°C",
        "physical_sample_key": key,
        "physical_sample_at": dt_util.utcnow() - timedelta(milliseconds=age),
    })


@pytest.mark.asyncio
async def test_real_gui_selects_explicit_mode_and_defaults_disabled(hass):
    flow = OpenThermostatConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    flow.handler = "open_thermostat"
    menu = await flow.async_step_user()
    assert menu["menu_options"] == ["legacy", "shadow"]
    form = await flow.async_step_shadow()
    assert "topic_prefix" in {str(x) for x in form["data_schema"].schema}
    result = await flow.async_step_shadow({"topic_prefix": "fixture"})
    assert result["data"][CONF_MODE] == MODE_SHADOW
    assert result["options"][CONF_ENABLED] is False
    assert OpenThermostatConfigFlow.VERSION == 2


@pytest.mark.asyncio
async def test_prefix_identity_prevents_duplicate_legacy_and_v1(hass):
    entry(hass, mode=MODE_LEGACY)
    flow = OpenThermostatConfigFlow()
    flow.hass = hass
    flow.handler = "open_thermostat"
    flow.context = {"source": "user"}
    with pytest.raises(AbortFlow):
        await flow.async_step_shadow({"topic_prefix": "fixture"})


@pytest.mark.asyncio
async def test_native_zone_flow_selectors_create_optional_wall_binding(hass):
    binding = room(hass)
    parent = entry(hass)
    flow = ZoneSubentryFlow()
    flow.hass = hass
    flow.handler = (parent.entry_id, "zone")
    flow.context = {"source": "user"}
    form = await flow.async_step_user()
    schema = form["data_schema"]
    selection = schema({
        "room_id": binding.room_id, "name": "My room",
        "temperature_entity": binding.temperature.entity_id,
        "actuator_entities": [binding.actuators[0].entity_id],
        "maximum_age_ms": 120000,
    })
    result = await flow.async_step_user(selection)
    assert result["type"] == "create_entry"
    assert result["unique_id"] == binding.room_id
    assert result["data"]["setpoint"] is None
    assert result["data"]["actuator_profile"] == "C_unverified"


@pytest.mark.asyncio
async def test_registry_uuid_selected_and_reconfigure_preserves_room_identity(hass):
    binding = room(hass)
    parent = entry(hass, room=binding)
    subentry = next(iter(parent.subentries.values()))
    registry = er.async_get(hass)
    flow = ZoneSubentryFlow()
    flow.hass = hass
    flow.handler = (parent.entry_id, "zone")
    flow.context = {"source": "reconfigure", "subentry_id": subentry.subentry_id}
    result = await flow.async_step_reconfigure({
        "name": "Renamed", "temperature_entity": registry.async_get(binding.temperature.entity_id).id,
        "actuator_entities": [registry.async_get(binding.actuators[0].entity_id).id],
        "maximum_age_ms": 120000, "room_id": "ffffffff",
    })
    assert result["type"] == "abort"
    assert subentry.data["room_id"] == binding.room_id
    assert subentry.title == "Renamed"


@pytest.mark.asyncio
async def test_own_outputs_and_duplicate_actuators_rejected(hass):
    binding = room(hass)
    parent = entry(hass, room=binding)
    args = {"room_id": "aabbccdd", "name": "other",
            "temperature_entity": binding.temperature.entity_id,
            "actuator_entities": [binding.actuators[0].entity_id]}
    with pytest.raises(ValueError, match="duplicate_actuator"):
        validate_room(hass, parent, args)
    own = er.async_get(hass).async_get_or_create(
        "sensor", "open_thermostat", "own_output", suggested_object_id="own_output")
    args["temperature_entity"] = own.entity_id
    with pytest.raises(ValueError, match="loop_binding"):
        validate_room(hass, parent, args)


@pytest.mark.asyncio
async def test_mode_migration_preserves_legacy_identity_without_setup(hass):
    parent = entry(hass, mode=MODE_LEGACY, version=1)
    before = parent.unique_id
    assert await integration.async_migrate_entry(hass, parent)
    assert parent.unique_id == before == "fixture"
    assert parent.version == 2
    assert integration_mode(parent) == MODE_LEGACY
    assert not OpenThermostatConfigFlow.async_get_supported_subentry_types(parent)


@pytest.mark.asyncio
async def test_default_disabled_has_no_source_listener_or_transport_request(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=False), [binding])
    transport = LocalTransport()
    runtime.attach_transport(transport)
    await runtime.async_start()
    physical_state(hass, binding)
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].quality == "disabled"
    assert not transport.observations
    assert not runtime._subscriptions
    with pytest.raises(HomeAssistantError):
        await runtime.async_set_temperature(binding.room_id, 21)
    await runtime.async_stop()


@pytest.mark.asyncio
async def test_real_state_events_cache_and_last_reported_are_not_physical(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    transport = LocalTransport()
    runtime.attach_transport(transport)
    await runtime.async_start()
    physical_state(hass, binding)
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].quality == "unverified"
    assert all(x[1].quality != "qualified" for x in transport.observations)
    hass.states.async_set(binding.temperature.entity_id, "20",
                          hass.states.get(binding.temperature.entity_id).attributes)
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].quality == "unverified"
    await runtime.async_stop()


@pytest.mark.asyncio
async def test_qualified_profile_roundtrip_confirmed_fw_state_no_device_action(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    transport = LocalTransport()
    runtime.attach_transport(transport)
    runtime.set_report_profile(binding.room_id, source_profile)
    calls = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    await runtime.async_start()
    assert runtime.observations[binding.room_id].quality == "unverified"
    physical_state(hass, binding)
    await hass.async_block_till_done()
    assert transport.observations[-1][1].quality == "qualified"
    climate = ShadowRoom("fixture", binding, runtime)
    assert climate.unique_id == "fixture_room_a1b2c3d4_climate"
    await runtime.async_set_temperature(binding.room_id, 21)
    assert climate.target_temperature is None
    assert transport.targets == [(binding.room_id, 2100)]
    runtime.apply_confirmed_state(binding.room_id, RoomDecision(2100, 2000, True, "fixture_fw_reply"))
    assert climate.target_temperature == 21
    assert climate.current_temperature == 20
    assert climate.extra_state_attributes["actuation_enabled"] is False
    assert calls == []
    await runtime.async_stop()


@pytest.mark.asyncio
async def test_report_event_duplicate_does_not_renew_sample_deadline(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    runtime.set_report_profile(binding.room_id, source_profile)
    await runtime.async_start()
    physical_state(hass, binding)
    await hass.async_block_till_done()
    original = runtime._expiries[binding.room_id]
    previous = hass.states.get(binding.temperature.entity_id)
    hass.states.async_set(binding.temperature.entity_id, previous.state, previous.attributes)
    await hass.async_block_till_done()
    assert runtime._expiries[binding.room_id] is original
    await runtime.async_stop()


@pytest.mark.asyncio
async def test_invalid_old_profile_and_unavailable_fail_closed(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    runtime.set_report_profile(binding.room_id, source_profile)
    await runtime.async_start()
    physical_state(hass, binding, age=120001)
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].quality == "stale"
    runtime.set_report_profile(binding.room_id, lambda *_: 1/0)
    physical_state(hass, binding, key="new-2")
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].quality == "profile_error"
    hass.states.async_set(binding.temperature.entity_id, "unavailable")
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].quality == "unavailable"
    await runtime.async_stop()


@pytest.mark.asyncio
async def test_registry_rename_rebind_and_unload_remove_native_listeners(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    await runtime.async_start()
    registry = er.async_get(hass)
    registry.async_update_entity(binding.temperature.entity_id, new_entity_id="sensor.renamed_room")
    await hass.async_block_till_done()
    assert runtime.resolved(binding.temperature) == "sensor.renamed_room"
    hass.states.async_set("sensor.renamed_room", "21", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert runtime.observations[binding.room_id].temperature_c == 21
    await runtime.async_stop()
    before = dict(runtime.observations)
    hass.states.async_set("sensor.renamed_room", "22", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert runtime.observations == before
    assert runtime._subscriptions == []
    assert runtime._expiries == {}


@pytest.mark.asyncio
async def test_profile_c_default_gate_calls_no_native_service(hass):
    binding = room(hass)
    calls = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id)
    with pytest.raises(HomeAssistantError, match="disabled"):
        await actuator.async_set_room_target(21)
    assert calls == []


@pytest.mark.asyncio
async def test_profile_c_deliberate_in_memory_bench_uses_real_service_registry(hass):
    binding = room(hass)
    calls = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call.data))
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=lambda: True)
    actual = await actuator.async_set_room_target(20.1)
    assert actual == 20.0
    assert len(calls) == 1
    assert calls[0]["entity_id"] == binding.actuators[0].entity_id
    assert calls[0]["temperature"] == 20.0


@pytest.mark.asyncio
async def test_profile_c_service_timeout_is_unknown_not_readiness_or_retry(hass, monkeypatch):
    import asyncio
    binding = room(hass)
    calls = []
    async def stalled(call):
        calls.append(call.data)
        await asyncio.Event().wait()
    hass.services.async_register("climate", "set_temperature", stalled)
    monkeypatch.setattr("custom_components.open_thermostat.v1_profile_c.ACTION_TIMEOUT_SECONDS", 0.01)
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                               qualified_profile=True, authorize=lambda: True)
    with pytest.raises(HomeAssistantError, match="physical outcome unknown"):
        await actuator.async_set_room_target(21)
    assert len(calls) == 1
