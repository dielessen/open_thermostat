"""Malformed legacy readings must not become valid HA measurements or commands."""
from unittest.mock import AsyncMock
import pytest
from homeassistant.exceptions import HomeAssistantError
from custom_components.open_thermostat.climate import OpenThermostatRoom
from custom_components.open_thermostat.sensor import RoomMetric


@pytest.mark.parametrize('bad', [True, False, float('nan'), float('inf'), -float('inf'), 10**500, '20'])
def test_climate_rejects_non_numeric_or_unrepresentable_room_readings(bad):
    room = OpenThermostatRoom('fixture', 0, 'a1b2c3d4', None, {}, AsyncMock())
    room.update_room({'currentTemp': bad, 'currentHumidity': bad,
                      'tempSet': bad, 'batteryLevel': bad}, True, None, False)
    assert room.current_temperature is None
    assert room.current_humidity is None
    assert room.target_temperature is None
    assert 'battery_level' not in room.extra_state_attributes
    assert 'temperature_set' not in room.extra_state_attributes


@pytest.mark.parametrize('metric,bad', [('humidity', -32768), ('humidity', 10001),
    ('battery', -1), ('battery', 101), ('temperature', float('inf')),
    ('temperature_set', 10**500)])
def test_sensor_rejects_invalid_readings_instead_of_emitting_numeric_statistics(metric, bad):
    sensor = RoomMetric('fixture', 0, 'a1b2c3d4', 'Room', metric)
    sensor.update_value(bad, True)
    assert sensor.native_value is None


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [True, float('nan'), float('inf'), 10**500, 9.9, 40.1, '21'])
async def test_legacy_target_rejects_invalid_input_before_dispatch(bad):
    send = AsyncMock(return_value=True)
    room = OpenThermostatRoom('fixture', 0, 'a1b2c3d4', None, {}, send)
    room.update_room({'name': 'Room'}, True, None, False)
    with pytest.raises(HomeAssistantError):
        await room.async_set_temperature(temperature=bad)
    send.assert_not_awaited()


@pytest.mark.parametrize('metric,raw,wanted', [('humidity', 0, 0), ('humidity', 10000, 100),
    ('battery', 0, 0), ('battery', 100, 100), ('temperature', -125, -1.25),
    ('temperature_set', 2100, 21)])
def test_valid_boundaries_and_centi_units_are_preserved(metric, raw, wanted):
    sensor = RoomMetric('fixture', 0, 'a1b2c3d4', 'Room', metric)
    sensor.update_value(raw, True)
    assert sensor.native_value == wanted


def test_huge_native_target_is_a_validation_error_not_float_conversion_crash():
    from custom_components.open_thermostat.v1_model import target_centi
    with pytest.raises(ValueError):
        target_centi(10**500)


def test_huge_reported_heat_number_is_unknown_not_callback_crash():
    from custom_components.open_thermostat.heating import finite
    assert not finite(10**500, 0, 100)


@pytest.mark.parametrize('legacy', [False, True])
def test_huge_hub_metrics_cannot_interrupt_status_processing(legacy):
    from custom_components.open_thermostat.sensor import HubMetric
    sensor = HubMetric('fixture', 'ems_metrics', 'energy')
    payload = {'metricsSchema': 2, 'counterDefinition': 'observation-total-v2',
               'totalEnergyUsedKwhV2': 10**500 if not legacy else 1,
               'totalEnergyUsedKwh': 10**500 if legacy else None}
    sensor.update_payload(payload, True)
    assert sensor.native_value == (1 if legacy else None)


def test_huge_converter_number_does_not_appear_as_device_capability():
    from custom_components.open_thermostat.device_metadata import project_definition
    result = project_definition({'definition': {'exposes': [{'property': 'occupied_heating_setpoint',
        'access': 7, 'value_min': 10**500, 'value_max': 30, 'value_step': 0.5}]}})
    feature = result['declared_features'][0]
    assert 'value_min' not in feature
    assert feature['value_max'] == 30 and feature['value_step'] == 0.5


@pytest.mark.parametrize('bad', [-32768, 32767, -6001, 13001, -10**20, 10**20])
def test_impossible_room_temperatures_are_unknown_in_climate_and_statistics(bad):
    room = OpenThermostatRoom('fixture', 0, 'a1b2c3d4', None, {}, AsyncMock())
    room.update_room({'currentTemp': bad, 'tempSet': bad}, True, None, False)
    assert room.current_temperature is None
    assert room.target_temperature is None
    assert 'temperature_set' not in room.extra_state_attributes
    for metric in ('temperature', 'temperature_set'):
        sensor = RoomMetric('fixture', 0, 'a1b2c3d4', 'Room', metric)
        sensor.update_value(bad, True)
        assert sensor.native_value is None


@pytest.mark.parametrize('raw,wanted', [(-6000, -60), (0, 0), (13000, 130)])
def test_room_temperature_wire_boundaries_still_preserve_real_zero_and_units(raw, wanted):
    room = OpenThermostatRoom('fixture', 0, 'a1b2c3d4', None, {}, AsyncMock())
    room.update_room({'currentTemp': raw, 'tempSet': raw}, True, None, False)
    assert room.current_temperature == wanted
    assert room.target_temperature == wanted
    for metric in ('temperature', 'temperature_set'):
        sensor = RoomMetric('fixture', 0, 'a1b2c3d4', 'Room', metric)
        sensor.update_value(raw, True)
        assert sensor.native_value == wanted
