"""How boiler and E32 values read (review of 30 Oct 2026): on/off instead of 1.0/0.0, codes by their meaning,
memory in kB, the uptime as a duration and the raw state bits as a whole number with its hex.

The constraints: entity IDs never change, no entity changes platform, recorded history and long-term
statistics stay valid. So words are used only for fields that never had statistics (no state class, no
unit); memory and uptime keep their state class and change to a unit of the same unit class, which the
recorder converts to the unit of the statistics it compiled before.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass, _numeric_state_expected
from homeassistant.components.sensor.recorder import _normalize_states
from homeassistant.core import State
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util.unit_conversion import InformationConverter, DurationConverter

from custom_components.open_thermostat.boiler_fields import (CATALOG_BASE, CATALOG_COUNTERS, CATALOG_FIELDS,
                                                             FIELDS, INDEXES, spec)
from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.sensor import HubMetric
from custom_components.open_thermostat.v1_boiler_fields import (CODE_STATES, MAINTENANCE, ON_OFF, BoilerFieldEntity,
                                                                presentation, shown_value)

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
AT = {field[0]: index for index, field in enumerate(FIELDS)} | {
    field[0]: CATALOG_BASE + index for index, field in enumerate(CATALOG_FIELDS)}


class Shown(BoilerFieldEntity):
    """A field entity with one usable reading, without a transport."""

    def __init__(self, name, raw):
        super().__init__("fixture", SimpleNamespace(
            ready=True, boiler_fields=SimpleNamespace(concept_state=lambda members: None, profile="classic")), AT[name])
        self._reading = (AT[name], {"raw": raw, "usable": True, "measurement_state": "fresh", "quality": 0,
                                    "source_type": "retained", "observed_at_ms": 1, "availability_reason": "fresh"})

    available = True
    source = property(lambda self: self._reading)

    def _live(self):
        return True


def test_on_off_fields_read_on_or_off():
    for name in ("dhw_enabled", "heating_enabled", "heating_active", "dhw_active", "dhw_circulation_enabled",
                 "dhw_charge_optimisation_enabled", "raw_burner_bit"):
        assert presentation(AT[name]) == ON_OFF, name
        assert (Shown(name, 1).native_value, Shown(name, 0).native_value) == ("on", "off"), name
        assert Shown(name, 1).extra_state_attributes["raw_value"] == 1


def test_codes_read_their_meaning_and_unknown_codes_read_code_n():
    cases = {"configured_dhw_comfort_mode": {0x00: "hot", 0xD8: "eco", 0xEC: "intelligent", 7: "Code 7"},
             "configured_dhw_charge_type": {0: "charge_pump", 1: "three_way_valve"},
             "configured_dhw_circulation_mode": {0: "off", 2: "2x3min", 7: "continuous", 9: "Code 9"},
             "reported_dhw_type": {1: "flow", 4: "layered_buffer", 5: "Code 5"},
             "configured_pump_mode": {0: "proportional", 3: "delta_p_3"}}
    for name, values in cases.items():
        for raw, state in values.items():
            assert Shown(name, raw).native_value == state, (name, raw)
    # The live installation of 30 Oct 2026: "2.0", "1.0", "0.0", "1.0" became words.
    assert [Shown(n, r).native_value for n, r in (("configured_dhw_circulation_mode", 2), (
        "configured_dhw_charge_type", 1), ("configured_dhw_comfort_mode", 0), ("reported_dhw_type", 1))] == [
        "2x3min", "three_way_valve", "hot", "flow"]


def test_the_maintenance_message_reads_none_or_its_h_code_and_its_row_hides_while_there_is_none(hass):
    assert presentation(AT["maintenance_message"]) == MAINTENANCE
    assert (Shown("maintenance_message", 0).native_value, Shown("maintenance_message", 8).native_value) == (
        "none", "H08")
    from test_dashboard_heating import installation
    e, rooms, sensors, hub, fields = installation(hass)
    message = er.async_get(hass).async_get_or_create("sensor", "open_thermostat",
                                                     "fixture_boiler_fields_v1_maintenance_message",
                                                     config_entry=e).entity_id
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    boiler = next(v for v in config["views"] if v["path"] == "boiler")
    row = next(r for c in view_cards(boiler) if c["type"] == "entities" for r in c["entities"]
               if r["row"]["entity"] == message)
    assert row["conditions"] == [{"condition": "state", "entity": message,
                                  "state_not": ["unavailable", "unknown", "none"]}]


def test_service_number_and_state_bits_are_whole_numbers_and_the_bits_also_hex():
    assert presentation(AT["service_number"]) is None and Shown("service_number", 0).native_value == 0
    bits = Shown("raw_boiler_state", 9)
    assert bits.native_value == 9 and bits.suggested_display_precision == 0
    assert bits.extra_state_attributes["hex"] == "0x09" and "raw_value" not in bits.extra_state_attributes


def test_words_only_where_there_never_were_statistics():
    """Only fields without a state class and unit become words: no statistics stop, no repair, no unit change."""
    worded = [index for index in INDEXES if presentation(index) is not None]
    assert {spec(index)[0] for index in worded} >= {"dhw_enabled", "configured_dhw_comfort_mode", "maintenance_message"}
    for index in worded:
        name, unit, divisor, _ = spec(index)
        assert name not in CATALOG_COUNTERS and unit in ("bool", "code") and divisor == 1, name
        entity = BoilerFieldEntity("fixture", SimpleNamespace(), index)
        assert entity.state_class is None and entity.native_unit_of_measurement is None, name
        assert entity.device_class is None and entity.suggested_display_precision is None, name
        # Home Assistant accepts a text state for exactly these (no numeric state expected).
        assert not _numeric_state_expected(entity.device_class, entity.state_class,
                                           entity.native_unit_of_measurement, entity.suggested_display_precision)
    # Fields with statistics (the EMS counters) stay numbers.
    for name in CATALOG_COUNTERS:
        entity = BoilerFieldEntity("fixture", SimpleNamespace(), AT[name])
        assert presentation(AT[name]) is None or entity._presentation is None
        assert entity.state_class == SensorStateClass.TOTAL_INCREASING


def test_every_word_is_translated_in_english_dutch_and_polish():
    states = {name: set(table.values()) for name, table in CODE_STATES.items()}
    states["maintenance_message"] = {"none"}
    states |= {spec(index)[0]: {"on", "off"} for index in INDEXES if presentation(index) == ON_OFF}
    for filename in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        sensors = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))["entity"]["sensor"]
        for name, keys in states.items():
            assert set(sensors["field_" + name].get("state", {})) == keys, (filename, name)
    nl = json.loads((COMPONENT / "translations/nl.json").read_text(encoding="utf-8"))["entity"]["sensor"]
    assert nl["field_dhw_enabled"]["state"] == {"on": "Aan", "off": "Uit"}
    assert nl["field_configured_dhw_comfort_mode"]["state"]["eco"] == "Eco (zuinig)"


def test_memory_reads_whole_kilobytes_and_the_uptime_hours_for_a_duration():
    memory = HubMetric("fixture", "device_status", "memory_free")
    memory.update_payload({"mem_free": 56628}, False)
    assert (memory.native_value, memory.native_unit_of_measurement, memory.suggested_display_precision) == (
        56.628, "kB", 0)
    assert (memory.device_class, memory.state_class) == (SensorDeviceClass.DATA_SIZE, SensorStateClass.MEASUREMENT)
    uptime = HubMetric("fixture", "device_status", "uptime")
    uptime.update_payload({"uptime": 4569}, False)
    # 1.27 h: the frontend formats a duration in h (not in s) as "1h 16m".
    assert (round(uptime.native_value, 4), uptime.native_unit_of_measurement, uptime.suggested_display_precision) == (
        1.2692, "h", 2)
    assert (uptime.device_class, uptime.state_class) == (SensorDeviceClass.DURATION, SensorStateClass.TOTAL_INCREASING)


@pytest.mark.parametrize("old_unit,new_unit,value,unit_class,expected", [
    ("B", "kB", 56.628, InformationConverter.UNIT_CLASS, 56628),
    ("s", "h", 1.2692, DurationConverter.UNIT_CLASS, 4569.12)])
def test_the_recorder_keeps_compiling_the_old_statistics_in_their_own_unit(hass, old_unit, new_unit, value,
                                                                           unit_class, expected):
    """Home Assistant's own normalisation: new kB / h states convert to the B / s of the existing statistics."""
    device_class = "data_size" if old_unit == "B" else "duration"
    metadata = {"sensor.memory": (1, {"unit_of_measurement": old_unit, "unit_class": unit_class,
                                      "statistic_id": "sensor.memory"})}
    state = State("sensor.memory", str(value), {"unit_of_measurement": new_unit, "device_class": device_class})
    result_class, statistics_unit, states = _normalize_states(hass, metadata, [(value, state)], "sensor.memory", None)
    assert (result_class, statistics_unit) == (unit_class, old_unit)
    assert len(states) == 1 and states[0][0] == pytest.approx(expected)


@pytest.mark.asyncio
async def test_worded_and_rescaled_entities_keep_their_entity_ids(hass, monkeypatch):
    from homeassistant import loader
    from homeassistant.helpers import translation
    from custom_components.open_thermostat.v1_boiler_fields import translated_fields
    from test_modern_metrics import system
    from test_room_sensor_restore import platform
    e, runtime, client, now = await system(hass)
    client.boiler_fields_supported = True
    actual = await platform(hass, e)
    integration = loader.Integration(hass, "custom_components.open_thermostat", COMPONENT,
                                     json.loads((COMPONENT / "manifest.json").read_text()),
                                     top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    device = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, name="E32",
                                                    identifiers={("open_thermostat", "fixture")})
    registry = er.async_get(hass)
    owners = {unique_id: registry.async_get_or_create("sensor", "open_thermostat", unique_id, config_entry=e,
                                                      device_id=device.id, suggested_object_id=object_id).entity_id
              for unique_id, object_id in (
                  ("fixture_boiler_fields_v1_dhw_enabled", "woonkamer_e32_regelaar_ketel_en_diagnose_hot_water_enabled"),
                  ("fixture_boiler_fields_v1_configured_dhw_comfort_mode",
                   "woonkamer_e32_regelaar_ketel_en_diagnose_hot_water_comfort_mode"),
                  ("fixture_hub_memory_free", "woonkamer_openthermostat_free_memory"),
                  ("fixture_hub_uptime", "woonkamer_openthermostat_device_uptime"))}
    await actual.platform_data.async_load_translations()
    fields = [BoilerFieldEntity("fixture", client, AT[name], translated_fields())
              for name in ("dhw_enabled", "configured_dhw_comfort_mode")]
    hub = [HubMetric("fixture", "device_status", metric, e.entry_id) for metric in ("memory_free", "uptime")]
    try:
        await actual.async_add_entities(fields + hub)
        await hass.async_block_till_done()
        assert [entity.entity_id for entity in fields + hub] == list(owners.values())
        assert all(registry.async_get(entity_id).platform == "open_thermostat" for entity_id in owners.values())
        assert all(entity_id.startswith("sensor.") for entity_id in owners.values())
    finally:
        await actual.async_reset()
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_retained_boiler_values_arrive_as_words_end_to_end(hass):
    """The E32's retained groups (beta.19 and later) through the real cache: words where the value is a code."""
    from custom_components.open_thermostat.v1_boiler_fields import async_setup_boiler_fields
    from test_boiler_fields import by_index
    from test_boiler_state import group_doc
    from test_modern_metrics import system
    e, runtime, client, now = await system(hass)
    client.boiler_fields_supported = False
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities: added.extend(entities))
    for group in range(7):
        await client.receive(f"fw/state/boiler_fields/{group}", group_doc(group), retained=True)
    runtime._notify()
    entities = by_index(added)
    assert entities[AT["dhw_enabled"]].native_value == "off"                       # raw 0
    assert entities[AT["configured_dhw_comfort_mode"]].native_value == "hot"       # raw 0x00
    assert entities[AT["configured_dhw_circulation_mode"]].native_value == "off"   # raw 0
    assert entities[AT["measured_flow_temperature"]].native_value == 45            # numbers stay numbers
    await runtime.async_stop()
