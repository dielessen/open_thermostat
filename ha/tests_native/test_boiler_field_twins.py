"""F28: one Home Assistant entity per physical boiler value, Classic or EMS+.

An EMS+ catalog field and its Classic twin (the same quantity in another
telegram family) share one entity. The entity the user already has keeps its
unique ID, entity ID and history; the value follows what the bus reports and
the source family is an attribute.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.boiler_fields import (
    CATALOG_BASE, CATALOG_FIELDS, FIELDS, INDEX_BY_NAME, LIMITS, PER_GROUP, PLUS_CLASSIC_TWINS, QUALITIES,
    BoilerFieldCache, concept, quality, spec)
from custom_components.open_thermostat.v1_boiler_fields import (
    REPORTED, BoilerFieldEntity, async_setup_boiler_fields, concept_name, duplicate_unique_ids, field_unique_id,
    translated_fields)
from custom_components.open_thermostat.v1_wire import canonical
from test_boiler_fields import packet
from test_modern_metrics import system

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
USER = er.RegistryEntryDisabler.USER
PLUS = sorted(index for index in INDEX_BY_NAME.values() if spec(index)[0].startswith("plus_"))


def at(name):
    return INDEX_BY_NAME[name]


def one_per_value(entities):
    """No two entities share a field, and every pair is covered by at most one entity."""
    covered = [member for entity in entities for member in entity.members]
    return len(covered) == len(set(covered))


def test_every_ems_plus_field_has_exactly_one_classic_twin_with_the_same_unit():
    assert len(PLUS) == len(PLUS_CLASSIC_TWINS) == 23
    assert set(PLUS_CLASSIC_TWINS) == {spec(index)[0] for index in PLUS}
    assert len(set(PLUS_CLASSIC_TWINS.values())) == len(PLUS_CLASSIC_TWINS)  # one to one
    classic = {field[0] for field in FIELDS}
    for plus, twin in PLUS_CLASSIC_TWINS.items():
        assert twin in classic, plus
        assert spec(at(plus))[1] == spec(at(twin))[1], plus  # same unit; the divisor may differ
        assert set(concept(at(plus))) == set(concept(at(twin))) == {at(plus), at(twin)}
    # Reported fields lead; Classic before EMS+, but an unreliable Classic bit or counter follows.
    assert concept(at("plus_flow_temperature")) == (at("measured_flow_temperature"), at("plus_flow_temperature"))
    assert concept(at("raw_burner_bit")) == (at("plus_burner_on"), at("raw_burner_bit"))
    assert concept(at("reported_burner_starts")) == (at("plus_burner_starts"), at("reported_burner_starts"))
    # The thermostat rows, records and uptime have no twin: what another controller
    # asks of the boiler is not what the boiler reports.
    for name in ("thermostat_requested_flow_temperature", "thermostat_requested_dhw_temperature",
                 "boiler_uptime", "last_locking_error_code"):
        assert concept(at(name)) == (at(name),)
    assert concept(at("selected_dhw_temperature")) == (at("selected_dhw_temperature"), at("plus_dhw_selected_temperature"))


def test_the_one_entity_carries_the_plain_name_and_ems_plus_stays_an_attribute():
    assert concept_name(at("plus_flow_temperature")) == "measured_flow_temperature"
    assert concept_name(at("plus_heating_temperature")) == "configured_heating_temperature"
    assert concept_name(at("measured_flow_temperature")) == "measured_flow_temperature"
    assert concept_name(at("plus_burner_on")) == "plus_burner_on"  # never "Burner bit (raw)"
    assert concept_name(at("raw_burner_bit")) == "raw_burner_bit"
    assert concept_name(at("thermostat_setpoint")) == "thermostat_setpoint"
    en = json.loads((ROOT / "ha/config/custom_components/open_thermostat/translations/en.json")
                    .read_text(encoding="utf-8"))["entity"]["sensor"]
    shown = [en["field_" + concept_name(index)]["name"] for index in PLUS]
    # Only the three EMS+ bits whose Classic twin is an unreliable raw bit keep "(EMS+)".
    assert sorted(name for name in shown if "(EMS+)" in name) == [
        "Burner on (EMS+)", "Heating pump (EMS+)", "Hot water valve (EMS+)"]
    client = SimpleNamespace(ready=True, boiler_fields_supported=True, boiler_fields=BoilerFieldCache(),
                             clock=lambda: 10.0)
    entity = BoilerFieldEntity("fixture", client, at("plus_flow_temperature"), translated_fields())
    assert entity.unique_id == "fixture_boiler_fields_v1_plus_flow_temperature"  # history stays
    assert entity.translation_key == "field_measured_flow_temperature"
    untranslated = BoilerFieldEntity("fixture", client, at("plus_flow_temperature"), frozenset())
    assert untranslated.name == "Boiler measured flow temperature"


def group(index_range, sampled, raw, profile):
    """A firmware-shaped group: raw maps a field index to its raw value (None: invalid); others unobserved."""
    fields = []
    for index in index_range:
        if index in raw:
            source = FIELDS[index][4] if index < CATALOG_BASE else CATALOG_FIELDS[index - CATALOG_BASE][4][0]
            fields.append([index, raw[index], sampled - 100, QUALITIES[index] if index < CATALOG_BASE else 0, source])
        else:
            fields.append([index, None, None, 0, 0])
    return {"schema": 1, "sampled_at_ms": sampled, "profile": profile, "fields": fields}


async def send(client, sequence, number, raw, sampled=10000, profile="classic_observed"):
    begin = number * PER_GROUP
    end = min(begin + PER_GROUP, len(FIELDS) if number < 7 else CATALOG_BASE + len(CATALOG_FIELDS))
    p = packet(client, sequence, group=number)
    p["values"] = group(range(begin, end), sampled, raw, profile)
    await client.receive("fw/telemetry/boiler_fields", canonical(p))


def test_the_value_follows_the_bus_from_either_family():
    cache = BoilerFieldCache()
    client = SimpleNamespace(ready=True, boiler_fields_supported=True, boiler_fields=cache, clock=lambda: 10.0)
    flow = BoilerFieldEntity("fixture", client, at("measured_flow_temperature"))
    cache.accept(group(range(0, 10), 10000, {1: 4520}, "classic_observed"), 0, 1, 10.0)
    assert flow.native_value == 45.2 and flow.extra_state_attributes["source_protocol"] == "ems_classic"
    # The bus now also carries EMS+ (a mixed adapter): Classic is no longer qualified, EMS+ is.
    cache.accept(group(range(70, 80), 11000, {at("plus_flow_temperature"): 463}, "conflicting_families"), 7, 2, 10.0)
    attributes = flow.extra_state_attributes
    assert flow.native_value == 46.3 and attributes["source_protocol"] == "ems_plus"
    assert attributes["field_name"] == "plus_flow_temperature" and attributes["raw_divisor"] == 10
    assert attributes["source_fields"] == ["measured_flow_temperature", "plus_flow_temperature"]
    # Unpaired fields keep their attributes as before.
    setpoint = BoilerFieldEntity("fixture", client, at("thermostat_setpoint"))
    assert "source_protocol" not in setpoint.extra_state_attributes


# The owner's installation (docs/modern-thermostat/boiler-profiles/nefit-ecomline-classic-hrc-22h.json):
# a Nefit EcomLine Classic HRC 22H behind a Bosch EasyControl Adapter that answers as the boiler at
# 0x08, and a tado (RC10 type) at 0x17. Classic telegrams only; the adapter fills unsupported
# counters and bits with zero; pressure and exhaust have no sensor (invalid).
OWNER_VALID = ["reported_selected_flow_temperature", "measured_flow_temperature", "measured_return_temperature",
               "reported_burner_modulation", "reported_requested_power_limit", "raw_boiler_state",
               "selected_dhw_temperature", "measured_dhw_temperature", "dhw_enabled", "display_code",
               "service_number", "configured_heating_temperature", "reported_dhw_target", "ionisation_current",
               "hydraulic_switch_temperature", "reported_heating_pump_modulation", "dhw_hysteresis_on",
               "dhw_charge_optimisation_enabled", "dhw_flow_temperature_offset", "dhw_circulation_enabled",
               "configured_dhw_circulation_mode", "dhw_disinfection_temperature", "configured_dhw_charge_type",
               "configured_dhw_comfort_mode", "reported_dhw_type", "heating_active", "dhw_active"]
OWNER_INVALID = ["outdoor_temperature", "pressure", "storage_temperature_1", "storage_temperature_2",
                 "boiler_temperature", "exhaust_temperature", "secondary_dhw_temperature"]
OWNER_ZERO_FILLER = ["raw_burner_bit", "raw_pump_bit", "raw_fan_bit", "dhw_flow", "reported_burner_starts",
                     "reported_burner_runtime", "reported_heating_runtime", "reported_heating_starts",
                     "reported_dhw_runtime", "reported_dhw_starts", "raw_dhw_valve_bit"]
# The tado's verified frames: 0x1A heat request, 0xB1 RC10 monitor, 0x33 hot water request.
TADO = {"thermostat_requested_flow_temperature": 38, "thermostat_requested_burner_power": 100,
        "thermostat_requested_pump_modulation": 100, "thermostat_setpoint": 42, "thermostat_room_temperature": 209}


def owner_raw():
    raw = {}
    for name in OWNER_VALID:
        index = at(name)
        unit, (low, high) = spec(index)[1], LIMITS[index]
        value = {"degC": 4500, "%": 40, "text": (ord("-") << 8) | ord("H"), "bool": 1}.get(unit, 1)
        raw[index] = min(max(value, low), high)
    raw.update({at(name): None for name in OWNER_INVALID})
    raw.update({at(name): 0 for name in OWNER_ZERO_FILLER})
    return raw


@pytest.mark.asyncio
async def test_owner_easycontrol_adapter_with_tado_keeps_one_entity_per_value_and_its_entity_ids(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = c.boiler_fields_v2 = True
    reg = er.async_get(hass)

    def record(name, reported=True, **kw):
        entity_id = reg.async_get_or_create("sensor", "open_thermostat", field_unique_id("fixture", at(name)),
                                            config_entry=e, suggested_object_id=f"owner_{name}", **kw).entity_id
        if reported:
            reg.async_update_entity_options(entity_id, "open_thermostat", {REPORTED: True})
        return entity_id

    # What the owner's registry holds since HA0.4.0b10: the Classic entities with history,
    # the tado rows, and one EMS+ record an earlier release left behind for the same flow.
    owned = {name: record(name) for name in ("measured_flow_temperature", "measured_return_temperature",
                                             "reported_burner_modulation", "thermostat_room_temperature")}
    leftover = record("plus_flow_temperature", reported=False, disabled_by=INTEGRATION)
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    raw = owner_raw()
    sequence = 0
    for number in range(7):
        sequence += 1
        await send(c, sequence, number, {i: v for i, v in raw.items() if number * 10 <= i < number * 10 + 10})
    sequence += 1
    await send(c, sequence, 7, {at(name): value for name, value in TADO.items()})
    sequence += 1
    await send(c, sequence, at("thermostat_requested_dhw_temperature") // PER_GROUP,
               {at("thermostat_requested_dhw_temperature"): 55})
    r._notify()
    entities = {spec(entity.index)[0]: entity for entity in added}
    # Exactly the reported Classic fields and the tado rows; no EMS+ entity, nothing twice.
    expected = set(OWNER_VALID) | set(TADO) | {"thermostat_requested_dhw_temperature"}
    assert set(entities) == expected and len(added) == len(expected) and one_per_value(added)
    assert not any(entity.index in PLUS for entity in added)
    for name, entity_id in owned.items():
        assert entities[name].unique_id == reg.async_get(entity_id).unique_id  # same entity ID and history
    assert entities["measured_flow_temperature"].native_value == 45
    assert entities["thermostat_room_temperature"].native_value == 20.9
    assert entities["thermostat_requested_flow_temperature"].native_value == 38
    assert entities["measured_flow_temperature"].translation_key == "field_measured_flow_temperature"
    # The setup cleanup can see the leftover EMS+ record as the duplicate it is.
    records = er.async_entries_for_config_entry(reg, e.entry_id)
    assert duplicate_unique_ids(records, "fixture") == {reg.async_get(leftover).unique_id}

    # Should the adapter ever send EMS+ monitor frames too (firmware: conflicting families),
    # the existing Classic entity shows that value; no "Flow temperature (EMS+)" appears.
    sequence += 1
    await send(c, sequence, 7, {at("plus_flow_temperature"): 471, **{at(name): value for name, value in TADO.items()}},
               sampled=12000, profile="conflicting_families")
    sequence += 1
    await send(c, sequence, at("plus_pressure") // PER_GROUP, {at("plus_pressure"): 15},
               sampled=12000, profile="conflicting_families")
    r._notify()
    r._notify()
    flow = entities["measured_flow_temperature"]
    assert flow.native_value == 47.1 and flow.extra_state_attributes["source_protocol"] == "ems_plus"
    names = [spec(entity.index)[0] for entity in added]
    assert "plus_flow_temperature" not in names and one_per_value(added)
    # The owner had no pressure entity (no sensor); its first real value gets one, with the
    # identity of the family that reports it and the plain name.
    pressure = [entity for entity in added if at("pressure") in entity.members]
    assert len(pressure) == 1 and pressure[0].native_value == 1.5
    assert pressure[0].index == at("plus_pressure") and pressure[0].translation_key == "field_pressure"
    assert reg.async_get(leftover).disabled_by is INTEGRATION  # not adopted, not re-enabled
    await r.async_stop()


@pytest.mark.asyncio
async def test_an_ems_plus_boiler_keeps_its_existing_ems_plus_entity(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = c.boiler_fields_v2 = True
    reg = er.async_get(hass)
    mine = reg.async_get_or_create("sensor", "open_thermostat", "fixture_boiler_fields_v1_plus_pressure",
                                   config_entry=e, suggested_object_id="my_ems_plus_pressure").entity_id
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await send(c, 1, at("plus_pressure") // PER_GROUP, {at("plus_pressure"): 17}, profile="plus_observed")
    await send(c, 2, at("plus_flow_temperature") // PER_GROUP, {at("plus_flow_temperature"): 520},
               profile="plus_observed")
    r._notify()
    by_name = {spec(entity.index)[0]: entity for entity in added}
    # The existing EMS+ record keeps its identity; a new value gets the identity of its own family.
    assert set(by_name) == {"plus_pressure", "plus_flow_temperature"} and one_per_value(added)
    assert by_name["plus_pressure"].unique_id == reg.async_get(mine).unique_id
    assert by_name["plus_pressure"].native_value == 1.7
    assert by_name["plus_flow_temperature"].native_value == 52
    assert by_name["plus_flow_temperature"].translation_key == "field_measured_flow_temperature"
    r._notify()
    assert len(added) == 2
    await r.async_stop()


@pytest.mark.asyncio
async def test_the_record_the_user_sees_wins_and_the_other_is_the_duplicate(hass):
    e, r, c, now = await system(hass)
    reg = er.async_get(hass)
    make = lambda name, **kw: reg.async_get_or_create(
        "sensor", "open_thermostat", f"fixture_boiler_fields_v1_{name}", config_entry=e, **kw)
    classic_hidden = make("measured_return_temperature", disabled_by=INTEGRATION)
    plus_shown = make("plus_return_temperature")
    both_classic, both_plus = make("measured_flow_temperature"), make("plus_flow_temperature")
    unreliable, reliable = make("raw_burner_bit"), make("plus_burner_on")
    lone = make("plus_pressure")
    other = reg.async_get_or_create("sensor", "other_integration", "fixture_boiler_fields_v1_pressure")
    duplicates = duplicate_unique_ids(list(er.async_entries_for_config_entry(reg, e.entry_id)) + [other], "fixture")
    assert duplicates == {classic_hidden.unique_id, both_plus.unique_id, unreliable.unique_id}
    # A record marked as having reported beats an enabled one that never did.
    reg.async_update_entity_options(both_plus.entity_id, "open_thermostat", {REPORTED: True})
    records = er.async_entries_for_config_entry(reg, e.entry_id)
    assert both_classic.unique_id in duplicate_unique_ids(records, "fixture")
    # A record without a twin is never a duplicate; with both equal, the one that reports now stays.
    assert lone.unique_id not in duplicate_unique_ids(records, "fixture")
    unmarked = [make("measured_dhw_temperature"), make("plus_dhw_temperature")]
    assert duplicate_unique_ids(unmarked, "fixture", {unmarked[1].unique_id}) == {unmarked[0].unique_id}
    await r.async_stop()


@pytest.mark.asyncio
async def test_real_firmware_classic_groups_never_create_an_ems_plus_twin(hass):
    from test_boiler_fields_interop import system as firmware
    async with firmware(hass) as (e, r, c, bus, entities):
        r._notify()
        assert entities and one_per_value(entities)
        assert not any(entity.index in PLUS for entity in entities)
        assert all(entity.index < CATALOG_BASE for entity in entities)
