"""Native HA registry/state/service tests; no device qualification or hardware IO."""
import asyncio
from dataclasses import replace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_thermostat.v1_profile_c import (
    ProfileCActuator, reported_operating_mode, review_room_targets,
)
from test_v1_native import entry, room
from test_product_flow import managers, product, new_room, option


def bind_model(hass, binding, parent, model="TV02-Zigbee"):
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=parent.entry_id, identifiers={("fixture", "tv02")}, model_id=model)
    er.async_get(hass).async_update_entity(binding.actuators[0].entity_id, device_id=device.id)


def mode(hass, binding, preset="manual", state="heat"):
    entity = binding.actuators[0].entity_id
    attrs = dict(hass.states.get(entity).attributes)
    attrs["preset_mode"] = preset
    hass.states.async_set(entity, state, attrs)


def setup(hass, preset="manual", state="heat"):
    binding = replace(room(hass), maximum_target_centi_c=3000)
    parent = entry(hass, room=binding)
    bind_model(hass, binding, parent)
    mode(hass, binding, preset, state)
    return binding, parent


@pytest.mark.asyncio
@pytest.mark.parametrize("preset,state,reason", [
    ("auto", "heat", "local_schedule_active"),
    ("holiday", "heat", "holiday_mode_active"),
    ("manual", "off", "heating_disabled"),
    (None, "heat", "operating_mode_unknown"),
    ("unsupported", "heat", "operating_mode_unknown"),
    (["manual"], "heat", "operating_mode_unknown"),
    ("manual", "unknown", "operating_mode_unknown"),
    ("manual", "unavailable", "operating_mode_unknown"),
])
async def test_conflict_is_read_only_and_does_not_qualify_target_or_valve(hass, preset, state, reason):
    binding, _ = setup(hass, preset, state)
    before = hass.states.get(binding.actuators[0].entity_id)
    view = reported_operating_mode(hass, binding.actuators[0].entity_id)
    assert reason in view["issues"]
    assert not view["authorizes_actuation"]
    assert view["scope"] == "reported_ha_operating_mode"
    result = review_room_targets(hass, binding, [binding.actuators[0].entity_id])
    assert result["status"] != "compatible"
    assert not result["authorizes_actuation"]
    assert hass.states.get(binding.actuators[0].entity_id) is before


@pytest.mark.asyncio
async def test_manual_heat_is_only_a_compatible_declaration_default_adapter_stays_disabled(hass):
    binding, _ = setup(hass)
    result = review_room_targets(hass, binding, [binding.actuators[0].entity_id])
    assert result["status"] == "compatible"
    assert result["actuators"][0]["operating_mode"]["issues"] == []
    assert not result["authorizes_actuation"]
    calls = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    with pytest.raises(HomeAssistantError, match="disabled"):
        await ProfileCActuator(hass, binding.actuators[0].entity_id).async_set_room_target(21)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("preset,state", [("auto","heat"),("holiday","heat"),("manual","off"),(None,"heat")])
async def test_even_deliberate_synthetic_authorization_cannot_override_known_mode_conflict(hass, preset, state):
    binding, _ = setup(hass, preset, state)
    calls = []
    for service in ["set_temperature", "set_preset_mode", "set_hvac_mode"]:
        hass.services.async_register("climate", service, lambda call: calls.append(call))
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=lambda: True)
    with pytest.raises(HomeAssistantError, match="operating mode"):
        await actuator.async_set_room_target(21)
    assert calls == []  # no setpoint, mode repair, preset change or retry


@pytest.mark.asyncio
async def test_mode_rechecked_after_waiting_for_adapter_owner(hass):
    binding, _ = setup(hass)
    calls = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=lambda: True)
    await actuator._lock.acquire()
    task = asyncio.create_task(actuator.async_set_room_target(21))
    await asyncio.sleep(0)
    mode(hass, binding, "auto")
    actuator._lock.release()
    with pytest.raises(HomeAssistantError, match="operating mode"):
        await task
    assert calls == []


@pytest.mark.asyncio
async def test_deliberately_authorized_manual_fixture_sends_only_the_target_not_a_mode_repair(hass):
    binding, _ = setup(hass)
    calls = []
    for service in ["set_temperature", "set_preset_mode", "set_hvac_mode"]:
        hass.services.async_register("climate", service, lambda call: calls.append(call))
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=lambda: True)
    assert await actuator.async_set_room_target(20.1) == 20
    assert len(calls) == 1 and calls[0].service == "set_temperature"
    assert calls[0].data["temperature"] == 20
    assert not reported_operating_mode(hass, binding.actuators[0].entity_id)["authorizes_actuation"]


@pytest.mark.asyncio
async def test_final_authorization_callback_cannot_leave_a_stale_manual_snapshot(hass):
    binding, _ = setup(hass)
    calls = []; checks = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    def authorize():
        checks.append(True)
        if len(checks) == 2:
            mode(hass, binding, "auto")
        return True
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=authorize)
    with pytest.raises(HomeAssistantError, match="operating mode"):
        await actuator.async_set_room_target(21)
    assert len(checks) == 2 and calls == []


@pytest.mark.asyncio
async def test_other_models_do_not_inherit_tv02_semantics_from_a_preset_label(hass):
    binding, parent = setup(hass, "auto")
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get(binding.actuators[0].entity_id).device_id)
    dr.async_get(hass).async_update_device(device.id, model_id="other-model")
    assert reported_operating_mode(hass, binding.actuators[0].entity_id) is None
    result = review_room_targets(hass, binding, [binding.actuators[0].entity_id])
    assert result["status"] == "compatible" and not result["authorizes_actuation"]
    assert "operating_mode" not in result["actuators"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("original,replacement", [("TV02-Zigbee","other-model"),("other-model","TV02-Zigbee")])
async def test_model_classification_cannot_change_during_final_authorization(hass, original, replacement):
    binding, _ = setup(hass)
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get(binding.actuators[0].entity_id).device_id)
    dr.async_get(hass).async_update_device(device.id, model_id=original)
    calls = []; checks = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    def authorize():
        checks.append(True)
        if len(checks) == 2:
            dr.async_get(hass).async_update_device(device.id, model_id=replacement)
        return True
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=authorize)
    with pytest.raises(HomeAssistantError, match="model changed"):
        await actuator.async_set_room_target(21)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("language,phrase", [("nl","eigen weekprogramma"),("en","automatic scheduling")])
async def test_native_room_and_configuration_status_explain_mode_without_a_save_or_service(hass, managers, language, phrase):
    from custom_components.open_thermostat.room_editor import read_room
    from custom_components.open_thermostat.product import configuration_snapshot
    hass.config.language = language
    sub, opts = managers; parent = product(hass)
    binding = replace(room(hass), maximum_target_centi_c=3000)
    bind_model(hass, binding, parent);mode(hass, binding, "auto")
    result = await new_room(sub, parent, binding)
    result = await sub.async_configure(result["flow_id"], {"base_temperature":21,"program_action":"save",
        "advanced":{"minimum_target_temperature":5,"maximum_target_temperature":30,"maximum_age_seconds":120}})
    await sub.async_configure(result["flow_id"], {})
    zone = next(s for s in parent.subentries.values() if s.subentry_type == "zone")
    before = configuration_snapshot(parent)
    calls = []
    hass.services.async_register("climate", "set_temperature", lambda call: calls.append(call))
    model = read_room(hass, parent.entry_id, zone.data["room_id"])
    assert "local_schedule_active" in model["actuator_target_review"]["actuators"][0]["issues"]
    form = await option(opts, parent, "configuration_status")
    text = form["description_placeholders"]["actuator_checks"]
    assert phrase in text
    assert "kamergrenzen" not in text and "Review room limits" not in text
    assert configuration_snapshot(parent) == before and calls == []
