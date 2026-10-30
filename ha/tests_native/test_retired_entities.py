"""Registry records a release no longer provides are removed; records still provided later are kept.

Live list after HA 0.4.0b11 (unavailable/restored on the owner's installation), checked one by one:
- hub outdoor temperature: created only on a real EMS+ outdoor value since 0.4.0b10; a record
  that never had one is retired (RETIRED) - removed while untouched, statistics kept;
- the definition v2 counters (energy, warm water volume/flow, flame time): still provided by
  v1_metrics once the E32 session offers metrics - kept (they carry energy statistics);
- the shadow comparison (heating time / burner starts today, agreement with thermostat) and the
  per-room predicted heating start: still provided once their data arrives - kept.
"""
import logging
from types import SimpleNamespace

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.native_entity_cleanup import (
    REPORTED, RETIRED, cleanup_stale_entities, mark_reported)
from custom_components.open_thermostat.v1_metrics import async_setup_shadow_metrics
from custom_components.open_thermostat.v1_wire import canonical
from test_modern_metrics import packet, system
from test_product_flow import product
from test_v1_native import entry, room

OUTDOOR = "fixture_hub_outdoor_temperature"
STILL_PROVIDED = (
    # v1_metrics (definition v2): energy statistics live on these.
    "fixture_hub_energy_v2", "fixture_hub_energy_heating_v2", "fixture_hub_energy_warm_water_v2",
    "fixture_hub_energy_unattributed_v2", "fixture_hub_warm_water_usage_v2", "fixture_hub_warm_water_avg_flow_v2",
    "fixture_hub_burner_observed_time_v2",
    # heating_link: today's shadow comparison and the predicted heating start per room.
    "fixture_hub_shadow_e32_heating_time_today", "fixture_hub_shadow_tado_heating_time_today",
    "fixture_hub_shadow_e32_starts_today", "fixture_hub_shadow_tado_starts_today", "fixture_hub_shadow_agreement_today",
    "fixture_e32_room_woonkamer_heating_start",
)


def records(hass, owner):
    registry = er.async_get(hass)

    def record(uid, *, platform="open_thermostat", config_entry=owner, **changes):
        entity_id = registry.async_get_or_create("sensor", platform, uid, config_entry=config_entry).entity_id
        if changes:
            registry.async_update_entity(entity_id, **changes)
        return entity_id
    return registry, record


def test_every_retired_identity_names_the_version_and_a_reason():
    assert RETIRED == {"hub_outdoor_temperature": ("0.4.0b10", "outdoor_temperature_without_value")}


@pytest.mark.asyncio
async def test_a_never_reported_outdoor_record_is_removed_and_the_still_provided_ones_stay(hass, caplog):
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    outdoor = record(OUTDOOR)
    kept = [record(uid) for uid in STILL_PROVIDED]
    foreign = [record(OUTDOOR, platform="other_integration"), record("fixture_hub_outdoor_temperature_x"),
               record(OUTDOOR, config_entry=entry(hass), platform="open_thermostat_other")]
    with caplog.at_level(logging.INFO):
        removed = cleanup_stale_entities(hass, p, "fixture")
    assert removed == [f"{outdoor} (outdoor_temperature_without_value)"]
    assert registry.async_get(outdoor) is None
    assert all(registry.async_get(entity_id) is not None for entity_id in kept + foreign)
    assert "history and long-term statistics are kept" in caplog.text and outdoor in caplog.text
    assert cleanup_stale_entities(hass, p, "fixture") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [{"name": "Buiten"}, {"icon": "mdi:sun"}, {"area_id": "tuin"},
                                    {"disabled_by": er.RegistryEntryDisabler.USER},
                                    {"hidden_by": er.RegistryEntryHider.USER}])
async def test_a_customised_outdoor_record_is_never_removed(hass, choice):
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    outdoor = record(OUTDOOR, **choice)
    assert cleanup_stale_entities(hass, p, "fixture") == [] and registry.async_get(outdoor) is not None


@pytest.mark.asyncio
async def test_an_outdoor_record_with_a_value_now_or_ever_is_kept(hass):
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    outdoor = record(OUTDOOR)
    hass.data["open_thermostat"][p.entry_id] = {
        "v1_connection": SimpleNamespace(client=SimpleNamespace(metrics_payload={"outdoorTemperature": -5.7}))}
    assert cleanup_stale_entities(hass, p, "fixture") == []
    hass.data["open_thermostat"][p.entry_id] = {
        "v1_connection": SimpleNamespace(client=SimpleNamespace(metrics_payload={"outdoorTemperature": None}))}
    assert mark_reported(hass, OUTDOOR) is True
    assert registry.async_get(outdoor).options["open_thermostat"] == {REPORTED: True}
    assert cleanup_stale_entities(hass, p, "fixture") == [] and registry.async_get(outdoor) is not None
    assert mark_reported(hass, "fixture_hub_no_such_record") is False


@pytest.mark.asyncio
async def test_the_outdoor_entity_marks_its_record_on_its_first_real_value(hass):
    e, runtime, client, now = await system(hass)
    added = []
    await async_setup_shadow_metrics(hass, e, lambda entities, **kw: added.extend(entities))
    await client.receive("fw/telemetry/ems_metrics", canonical(packet(client)))
    outdoor = next(sensor for sensor in added if sensor.unique_id == OUTDOOR)
    # The platform registers the entity asynchronously; the next snapshot marks the record.
    registry = er.async_get(hass)
    entity_id = registry.async_get_or_create("sensor", "open_thermostat", outdoor.unique_id, config_entry=e).entity_id
    assert not registry.async_get(entity_id).options.get("open_thermostat")
    now[0] = 102
    await client.receive("fw/telemetry/ems_metrics", canonical(packet(client, 2)))
    assert registry.async_get(entity_id).options["open_thermostat"] == {REPORTED: True}
    await runtime.async_stop()
