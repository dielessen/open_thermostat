"""Real HA sensor metadata, finite values and firmware metric schema boundary."""
import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from custom_components.open_thermostat.sensor import HubMetric


@pytest.mark.parametrize("key", ["energy", "energy_warm_water", "energy_heating"])
def test_estimated_energy_is_boot_counter_with_explicit_not_meter_label(key):
    sensor = HubMetric("thermostat", "ems_metrics", key)
    assert sensor.state_class == SensorStateClass.TOTAL_INCREASING
    assert sensor.device_class == SensorDeviceClass.ENERGY
    assert sensor.extra_state_attributes["not_a_gas_meter"] is True
    assert sensor.extra_state_attributes["counter_scope"] == "boot"
    assert sensor.translation_key == f"hub_{key}_v2"  # named "Estimated ..." in strings.json
    # Versioned statistic definition; old registry identities are retained separately, never reused.
    assert sensor.unique_id == f"thermostat_hub_{key}_v2"


@pytest.mark.parametrize("schema", [None, 1, True, 2.0, 3])
def test_old_delta_or_unknown_metrics_schema_is_not_new_cumulative_energy(schema):
    sensor = HubMetric("thermostat", "ems_metrics", "energy")
    sensor.update_payload({"metricsSchema": schema, "totalEnergyUsedKwhV2": .01}, True)
    assert sensor.native_value is None
    sensor.update_payload({"metricsSchema": 2, "counterDefinition": "observation-total-v2", "totalEnergyUsedKwhV2": .25}, True)
    assert sensor.native_value == .25
    sensor.update_payload({"metricsSchema": 2, "counterDefinition": "observation-total-v2", "totalEnergyUsedKwhV2": 0}, True)
    assert sensor.native_value == 0  # valid boot reset; HA total_increasing handles it


def test_volume_counter_average_flow_and_unknown_semantics_are_not_mixed():
    volume = HubMetric("thermostat", "ems_metrics", "warm_water_usage")
    assert volume.device_class == SensorDeviceClass.WATER
    assert volume.state_class == SensorStateClass.TOTAL_INCREASING
    volume.update_payload({"metricsSchema": 2, "counterDefinition": "observation-total-v2", "warmWaterUsageV2": 1.2}, True)
    assert volume.native_value == 1.2 and volume.native_unit_of_measurement == "L"
    rate = HubMetric("thermostat", "ems_metrics", "warm_water_avg_flow")
    assert rate.state_class == SensorStateClass.MEASUREMENT
    rate.update_payload({"metricsSchema": 2, "counterDefinition": "observation-total-v2", "warmWaterAvgFlowV2": 1.2}, True)
    assert rate.native_value == 1.2 and rate.native_unit_of_measurement == "L/min"
    rate.update_payload({"warmWaterAvgFlowV2": 0}, True)
    assert rate.native_value is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True])
def test_non_finite_numeric_metrics_never_reach_recorder(bad):
    sensor = HubMetric("thermostat", "ems_metrics", "energy")
    sensor.update_payload({"metricsSchema": 2, "counterDefinition": "observation-total-v2", "totalEnergyUsedKwhV2": bad}, True)
    assert sensor.native_value is None


def test_existing_boiler_units_and_text_codes_are_preserved():
    temp = HubMetric("thermostat", "ems_status", "boiler_current_flow_temperature")
    temp.update_payload({"currentFlowTemperature": 456}, True)
    assert temp.native_value == 45.6
    code = HubMetric("thermostat", "ems_status", "boiler_display_code")
    code.update_payload({"displayCode": "0H"}, True)
    assert code.native_value == "0H"
