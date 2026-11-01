"""Values only some boilers, or only a boiler trial, ever have: no "unknown" row for good (beta.23).

The owner's EMS Classic boiler never fills the definition v2 counters (EMS+), and
"Boiler test: requested flow temperature" only has a value during an attended
trial; both showed "unknown" permanently (31 Oct 2026). Universal rule: what a
boiler does not send decides, never a list of models.
"""
from copy import deepcopy

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import native_entity_cleanup as cleanup
from custom_components.open_thermostat.native_entity_cleanup import (NEVER_REPORTED, REPORTED, hide_never_reported,
                                                                     note_value, value_gate_due,
                                                                     value_gated_enabled_default)
from custom_components.open_thermostat.metric_snapshot import VERSIONED
from custom_components.open_thermostat.v1_metrics import async_setup_shadow_metrics
from custom_components.open_thermostat.v1_wire import canonical
from test_modern_metrics import packet, system

INTEGRATION, USER = er.RegistryEntryDisabler.INTEGRATION, er.RegistryEntryDisabler.USER
HIDDEN = er.RegistryEntryHider.INTEGRATION
V2 = ("energy", "energy_warm_water", "energy_heating", "energy_unattributed", "burner_observed_time",
      "warm_water_usage", "warm_water_avg_flow")


def record(registry, e, unique_id, **changes):
    entity_id = registry.async_get_or_create("sensor", "open_thermostat", unique_id, config_entry=e).entity_id
    if changes:
        registry.async_update_entity(entity_id, **changes)
    return entity_id


@pytest.mark.asyncio
async def test_untouched_records_without_a_value_are_hidden_and_a_value_brings_them_back(hass):
    e, runtime, client, now = await system(hass)
    registry = er.async_get(hass)
    silent = record(registry, e, "fixture_hub_energy_v2")
    named = record(registry, e, "fixture_hub_energy_heating_v2", name="My counter")
    user_off = record(registry, e, "fixture_hub_warm_water_usage_v2", disabled_by=USER)
    reported = record(registry, e, "fixture_hub_burner_observed_time_v2")
    registry.async_update_entity_options(reported, "open_thermostat", {REPORTED: True})
    try:
        ids = ["fixture_hub_energy_v2", "fixture_hub_energy_heating_v2", "fixture_hub_warm_water_usage_v2",
               "fixture_hub_burner_observed_time_v2"]
        assert hide_never_reported(hass, e, ids) == [silent]
        entry = registry.async_get(silent)
        assert (entry.disabled_by, entry.hidden_by) == (INTEGRATION, HIDDEN)
        assert entry.options["open_thermostat"][NEVER_REPORTED] is True
        assert registry.async_get(named).disabled_by is None and registry.async_get(named).name == "My counter"
        assert registry.async_get(user_off).disabled_by is USER
        assert registry.async_get(reported).disabled_by is None
        assert hide_never_reported(hass, e, ids) == []  # once
        # A first real value (an EMS+ boiler, or a later firmware) undoes exactly what was done.
        assert note_value(hass, "fixture_hub_energy_v2") is True
        entry = registry.async_get(silent)
        assert (entry.disabled_by, entry.hidden_by) == (None, None)
        assert entry.options["open_thermostat"] == {REPORTED: True}
        # The user's own disable stays.
        assert note_value(hass, "fixture_hub_warm_water_usage_v2") is True
        assert registry.async_get(user_off).disabled_by is USER
        assert note_value(hass, "fixture_hub_unknown_v2") is False  # no record: nothing
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_a_new_record_starts_disabled_until_its_first_value(hass):
    e, runtime, client, now = await system(hass)
    registry = er.async_get(hass)
    try:
        assert value_gated_enabled_default(hass, "fixture_hub_energy_v2", False) is False
        assert value_gated_enabled_default(hass, "fixture_hub_energy_v2", True) is True
        record(registry, e, "fixture_hub_energy_v2")  # an existing record keeps its own state
        assert value_gated_enabled_default(hass, "fixture_hub_energy_v2", False) is True
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_the_grace_starts_when_the_source_is_heard_and_runs_once(hass, monkeypatch):
    e, runtime, client, now = await system(hass)
    clock = [1000.0]
    monkeypatch.setattr(cleanup, "_clock", lambda: clock[0])
    try:
        assert value_gate_due(hass, e, "definition_v2") is False
        clock[0] += cleanup.VALUE_GRACE_S - 1
        assert value_gate_due(hass, e, "definition_v2") is False
        clock[0] += 1
        assert value_gate_due(hass, e, "definition_v2") is True
        assert value_gate_due(hass, e, "definition_v2") is False
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_a_classic_boiler_hides_the_ems_plus_counters_and_an_ems_plus_boiler_keeps_them(hass, monkeypatch):
    e, runtime, client, now = await system(hass)
    clock = [1000.0]
    monkeypatch.setattr(cleanup, "_clock", lambda: clock[0])
    registry = er.async_get(hass)
    existing = {metric: record(registry, e, f"fixture_hub_{metric}_v2") for metric in V2}
    added = []
    await async_setup_shadow_metrics(hass, e, lambda entities: added.extend(entities))
    try:
        runtime._notify()
        # Classic: the E32 sends the v2 counters as null.
        classic = packet(client)
        classic["metrics"] = {**classic["metrics"], **{key: None for key in VERSIONED}}
        await client.receive("fw/telemetry/ems_metrics", canonical(classic))
        assert all(registry.async_get(entity_id).disabled_by is None for entity_id in existing.values())
        clock[0] += cleanup.VALUE_GRACE_S
        now[0] += 1
        later = deepcopy(classic)
        later["sequence"] = 2
        await client.receive("fw/telemetry/ems_metrics", canonical(later))
        for entity_id in existing.values():
            entry = registry.async_get(entity_id)
            assert (entry.disabled_by, entry.hidden_by) == (INTEGRATION, HIDDEN), entity_id
        # Entity IDs are kept (disabled and hidden, not removed): history stays.
        assert set(existing.values()) <= {r.entity_id for r in er.async_entries_for_config_entry(registry, e.entry_id)}
        # The same counters from an EMS+ boiler: back, and REPORTED.
        plus = packet(client, sequence=3)
        now[0] += 1
        await client.receive("fw/telemetry/ems_metrics", canonical(plus))
        assert client.metrics_payload["totalEnergyUsedKwhV2"] == 0, client.metrics_payload
        for entity_id in existing.values():
            entry = registry.async_get(entity_id)
            assert (entry.disabled_by, entry.hidden_by) == (None, None), entity_id
            assert entry.options["open_thermostat"].get(REPORTED) is True
    finally:
        await e._async_process_on_unload(hass)
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_new_ems_plus_counters_without_a_value_are_created_disabled(hass):
    e, runtime, client, now = await system(hass)
    added = []
    classic = packet(client)
    classic["metrics"] = {**classic["metrics"], **{key: None for key in VERSIONED}}
    await client.receive("fw/telemetry/ems_metrics", canonical(classic))
    await async_setup_shadow_metrics(hass, e, lambda entities: added.extend(entities))
    try:
        runtime._notify()
        v2 = [sensor for sensor in added if sensor.unique_id.endswith("_v2")]
        assert len(v2) == 7 and all(sensor.entity_registry_enabled_default is False for sensor in v2)
    finally:
        await e._async_process_on_unload(hass)
        await runtime.async_stop()
