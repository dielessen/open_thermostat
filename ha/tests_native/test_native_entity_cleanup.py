"""One route, one set of entities: stale registry cleanup and boiler fields that appear on a value."""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.boiler_fields import (
    CATALOG_BASE, CATALOG_FIELDS, PER_GROUP, BoilerFieldCache)
from custom_components.open_thermostat.native_entity_cleanup import cleanup_stale_entities
from custom_components.open_thermostat.v1_boiler_fields import (
    REPORTED, async_setup_boiler_fields, field_unique_id)
from custom_components.open_thermostat.v1_wire import canonical
from test_boiler_fields import packet
from test_modern_metrics import system
from test_product_flow import product
from test_v1_native import entry, room

INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
USER = er.RegistryEntryDisabler.USER
NAMES = [field[0] for field in CATALOG_FIELDS]


def catalog(name):
    return CATALOG_BASE + NAMES.index(name)


def catalog_values(group, sampled, raw, profile="classic_observed"):
    """Firmware-shaped catalog group; raw maps a field name to its raw value (None: invalid)."""
    fields = []
    for index in range(group * PER_GROUP, min(group * PER_GROUP + PER_GROUP, CATALOG_BASE + len(CATALOG_FIELDS))):
        name, _, _, _, types, _, _ = CATALOG_FIELDS[index - CATALOG_BASE]
        fields.append([index, raw[name], sampled - 100, 0, types[0]] if name in raw
                      else [index, None, None, 0, 0])
    return {"schema": 1, "sampled_at_ms": sampled, "profile": profile, "fields": fields}


async def send_catalog(client, sequence, name, raw, sampled=10000, also=None, profile="classic_observed"):
    group = catalog(name) // PER_GROUP
    values = {name: raw, **(also or {})}
    assert all(catalog(other) // PER_GROUP == group for other in values)
    p = packet(client, sequence, group=group)
    p["values"] = catalog_values(group, sampled, values, profile)
    await client.receive("fw/telemetry/boiler_fields", canonical(p))


@pytest.mark.asyncio
async def test_registry_cleanup_removes_exactly_the_stale_patterns(hass, caplog):
    binding = room(hass)  # zone room_id a1b2c3d4 still exists and feeds ShadowRuntime.
    p = product(hass, binding)
    reg = er.async_get(hass)

    def record(domain, uid, *, owner=p, platform="open_thermostat", name=None, reported=False, **kw):
        entity_id = reg.async_get_or_create(domain, platform, uid, config_entry=owner, **kw).entity_id
        if name:
            reg.async_update_entity(entity_id, name=name)
        if reported:
            reg.async_update_entity_options(entity_id, "open_thermostat", {REPORTED: True})
        return entity_id

    field = lambda name: f"fixture_boiler_fields_v1_{name}"
    gone = [
        record("sensor", "fixture_hub_boiler_pressure", disabled_by=INTEGRATION),
        record("binary_sensor", "fixture_hub_boiler_burner_active", disabled_by=INTEGRATION),
        record("binary_sensor", "fixture_hub_connected"),  # Never fed natively, even if enabled.
        record("sensor", "fixture_hub_rtc_temperature", disabled_by=INTEGRATION),
        record("sensor", field("plus_pressure"), disabled_by=INTEGRATION),
        record("sensor", field("plus_burner_starts"), disabled_by=INTEGRATION),
        record("sensor", field("no_longer_in_the_table"), disabled_by=INTEGRATION),
        # Classic fields we disabled (unreported, or unreliable by default) without a real value.
        record("sensor", field("raw_burner_bit"), disabled_by=INTEGRATION),
        record("sensor", field("raw_pump_bit"), disabled_by=INTEGRATION),  # Only zero filler now.
        record("sensor", field("reported_burner_starts"), disabled_by=INTEGRATION),
        record("climate", "fixture_room_deadbeef_climate"),  # Its zone no longer exists.
    ]
    kept = [
        # Unique diagnostics and estimates, the E32 heat request and new E32 rooms.
        record("sensor", "fixture_hub_memory_free"), record("sensor", "fixture_hub_uptime"),
        record("sensor", "fixture_hub_cpu_temperature"), record("sensor", "fixture_hub_energy_v2"),
        record("sensor", "fixture_hub_outdoor_temperature"),  # RETIRED: decided later, never at setup
        record("sensor", "fixture_hub_heat_request"),
        record("sensor", "fixture_e32_room_badkamer_state"),
        # Classic fields that reported: enabled, or disabled but marked as having had a value.
        record("sensor", field("measured_flow_temperature")),
        record("sensor", field("configured_pump_mode"), disabled_by=INTEGRATION, reported=True),
        record("sensor", field("raw_fan_bit"), disabled_by=INTEGRATION),  # Real non-zero bit now.
        # Catalog fields that reported (enabled), that report right now, or carry user choices.
        record("sensor", field("thermostat_room_temperature")),
        record("sensor", field("no_longer_in_the_table_but_enabled")),
        record("sensor", field("plus_return_temperature"), disabled_by=INTEGRATION),
        record("sensor", field("plus_flow_temperature"), disabled_by=INTEGRATION, name="My flow"),
        record("sensor", field("plus_dhw_flow"), disabled_by=USER),
        # The live zone's climate (old room editor identity) is still created by v1_climate.
        record("climate", f"fixture_room_{binding.room_id}_climate"),
    ]
    user_legacy = record("sensor", "fixture_hub_boiler_service_code", disabled_by=USER)
    renamed_legacy = record("sensor", "fixture_hub_boiler_display_code", name="Code")
    foreign = [
        record("sensor", "fixture_hub_boiler_current_flow_temperature", platform="other_integration"),
        record("binary_sensor", "fixture_hub_boiler_fan_active", owner=entry(hass)),
        record("sensor", "fixture_hub_boiler_hot_water_flow", owner=None),
    ]
    cache = BoilerFieldCache()
    index = catalog("plus_return_temperature")
    cache.records[index] = ((index, 450, 9000, 0, CATALOG_FIELDS[index - CATALOG_BASE][4][0]), 200.0)
    cache.records[8] = ((8, 0, 9000, 1, 24), 200.0)  # raw_pump_bit: adapter zero, no evidence.
    cache.records[9] = ((9, 1, 9000, 1, 24), 200.0)  # raw_fan_bit: a real non-zero bit.
    hass.data["open_thermostat"][p.entry_id] = {
        "v1_connection": SimpleNamespace(client=SimpleNamespace(boiler_fields=cache))}

    with caplog.at_level(logging.INFO):
        removed = cleanup_stale_entities(hass, p, "fixture")
    assert sorted(item.split(" ")[0] for item in removed) == sorted(gone)
    assert all(reg.async_get(entity_id) is None for entity_id in gone)
    assert all(reg.async_get(entity_id) is not None for entity_id in kept + foreign)
    assert reg.async_get(user_legacy).disabled_by is USER
    assert reg.async_get(renamed_legacy).disabled_by is INTEGRATION and reg.async_get(renamed_legacy).name == "Code"
    assert all(reg.async_get(x).disabled_by is None for x in foreign)
    assert "Removed 11 OpenThermostat entities" in caplog.text
    assert "boiler_field_never_reported" in caplog.text and "room_without_zone" in caplog.text
    # Idempotent: a second setup finds nothing left to remove.
    assert cleanup_stale_entities(hass, p, "fixture") == []


@pytest.mark.asyncio
async def test_catalog_entity_appears_only_after_its_first_value(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = c.boiler_fields_v2 = True
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    assert not added  # Negotiating v2 alone creates no entity.
    room_temperature, setpoint = catalog("thermostat_room_temperature"), catalog("thermostat_setpoint")
    # An acquired slot without a valid value is not a value either.
    await send_catalog(c, 1, "thermostat_setpoint", None)
    r._notify()
    assert not added
    await send_catalog(c, 2, "thermostat_room_temperature", 215, also={"thermostat_setpoint": None})
    r._notify()
    assert len(added) == 1
    entity = added[-1]
    assert entity.index == room_temperature and entity.native_value == 21.5
    assert entity.unique_id == field_unique_id("fixture", room_temperature)
    assert entity.unique_id == "fixture_boiler_fields_v1_thermostat_room_temperature"  # History stays.
    r._notify()
    assert len(added) == 1  # Never twice.
    # A new session empties the cache; the existing entity stays and others still appear.
    c.boiler_fields.reset()
    await send_catalog(c, 3, "thermostat_setpoint", 42, sampled=20000)
    r._notify()
    assert [x.index for x in added] == [room_temperature, setpoint]
    await r.async_stop()


@pytest.mark.asyncio
async def test_first_value_reenables_and_marks_our_retired_catalog_record(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = c.boiler_fields_v2 = True
    reg = er.async_get(hass)
    create = lambda name, **kw: reg.async_get_or_create(
        "sensor", "open_thermostat", f"fixture_boiler_fields_v1_{name}", config_entry=e, **kw).entity_id
    marked = lambda entity_id: reg.async_get(entity_id).options.get("open_thermostat", {}).get(REPORTED)
    retired = create("thermostat_room_temperature", disabled_by=INTEGRATION)
    mine = create("thermostat_requested_flow_temperature", disabled_by=USER)
    silent = create("thermostat_setpoint")
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await send_catalog(c, 1, "thermostat_room_temperature", 215, profile="plus_observed",
                       also={"thermostat_requested_flow_temperature": 40})
    r._notify()
    r._notify()  # The platform registers new entities asynchronously; retried on the next tick.
    assert reg.async_get(retired).disabled_by is None and marked(retired)
    assert reg.async_get(mine).disabled_by is USER and marked(mine)
    # No time-based retirement any more: a silent field is simply never created.
    now[0] += 3600
    r._notify()
    assert reg.async_get(silent).disabled_by is None and not marked(silent)
    await r.async_stop()


@pytest.mark.asyncio
async def test_product_sensor_platform_cleans_before_adding_and_creates_no_legacy_hub_entities(hass, monkeypatch):
    from custom_components.open_thermostat import (
        heating_link, native_entity_cleanup, product_telemetry, sensor, v1_boiler_fields, v1_metrics)
    p = product(hass)
    hass.data["open_thermostat"][p.entry_id] = {"v1_runtime": object()}
    calls = []
    monkeypatch.setattr(native_entity_cleanup, "cleanup_stale_entities",
                        lambda hass, entry, prefix: calls.append(("cleanup", prefix)))
    for module, name in ((v1_boiler_fields, "async_setup_boiler_fields"),
                         (heating_link, "async_setup_heating_link"),
                         (v1_metrics, "async_setup_shadow_metrics")):
        monkeypatch.setattr(module, name, AsyncMock(side_effect=lambda *a, n=name, **k: calls.append(n)))
    telemetry = AsyncMock(side_effect=lambda *a, **k: calls.append(("telemetry", k)))
    monkeypatch.setattr(product_telemetry, "async_setup_sensors", telemetry)
    await sensor.async_setup_entry(hass, p, lambda entities, **kw: None)
    # The E32 rooms first (sensor.py: every later step is optional).
    assert calls == [("cleanup", "fixture"), "async_setup_heating_link", "async_setup_boiler_fields",
                     ("telemetry", {"native_metrics": True}), "async_setup_shadow_metrics"]
