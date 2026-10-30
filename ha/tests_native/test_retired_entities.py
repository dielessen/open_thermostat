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
    assert RETIRED["hub_outdoor_temperature"] == ("0.4.0b10", "outdoor_temperature_without_value")
    assert {reason for _, reason in RETIRED.values()} == {"outdoor_temperature_without_value", "legacy_metric_history"}
    assert all(version.startswith("0.4.0b") for version, _ in RETIRED.values())


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


def test_the_legacy_history_counters_are_retired_by_name_and_version():
    from custom_components.open_thermostat.sensor import VERSIONED_METRICS
    legacy = {key.removeprefix("hub_") for key, (version, reason) in RETIRED.items() if reason == "legacy_metric_history"}
    assert legacy == set(VERSIONED_METRICS) and all(RETIRED[f"hub_{m}"][0] == "0.4.0b12" for m in legacy)


@pytest.mark.asyncio
async def test_legacy_history_records_go_and_their_repairs_items_close(hass, caplog):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.open_thermostat.metrics_reports import (
        note_legacy_metrics, note_metric_definition_migration, note_room_definition_migration)
    p = product(hass, room(hass))
    registry, record = records(hass, p)
    old = [record(f"fixture_hub_{metric}") for metric in ("energy", "warm_water_usage", "burner_observed_time")]
    kept = record("fixture_hub_energy_heating", name="Old heating energy")  # customised: stays
    v2 = record("fixture_hub_energy_v2")
    for note in (note_legacy_metrics, note_metric_definition_migration, note_room_definition_migration):
        note(hass, p.entry_id)
    issues = ir.async_get(hass)
    with caplog.at_level(logging.INFO):
        removed = cleanup_stale_entities(hass, p, "fixture")
    assert sorted(item.split(" ")[0] for item in removed) == sorted(old)
    assert registry.async_get(kept) is not None and registry.async_get(v2) is not None
    # The customised old record keeps the counters item open; the other two close.
    assert issues.async_get_issue("open_thermostat", f"metrics_definition_v2_{p.entry_id}") is not None
    assert issues.async_get_issue("open_thermostat", f"room_model_v2_{p.entry_id}") is None
    assert issues.async_get_issue("open_thermostat", f"legacy_metrics_history_{p.entry_id}") is None
    registry.async_remove(kept)  # the user deletes it
    cleanup_stale_entities(hass, p, "fixture")
    assert issues.async_get_issue("open_thermostat", f"metrics_definition_v2_{p.entry_id}") is None
    # Firmware that still sends old-format values keeps the old record (a value now).
    again = record("fixture_hub_energy")
    hass.data["open_thermostat"][p.entry_id] = {
        "v1_connection": SimpleNamespace(client=SimpleNamespace(metrics_payload={"totalEnergyUsedKwh": 12.5}))}
    assert cleanup_stale_entities(hass, p, "fixture") == [] and registry.async_get(again) is not None


@pytest.mark.asyncio
async def test_removing_an_installation_closes_every_repairs_item_of_it(hass):
    from homeassistant.helpers import issue_registry as ir
    import custom_components.open_thermostat as integration
    p = product(hass, room(hass))
    other = entry(hass)
    ids = [f"e32_room_choose_source_{p.entry_id}_woonkamer", f"device_own_schedule_{p.entry_id}_woonkamer",
           f"metrics_definition_v2_{p.entry_id}", f"room_group_restored_{p.entry_id}_woonkamer"]
    for issue in ids + [f"metrics_definition_v2_{other.entry_id}"]:
        ir.async_create_issue(hass, "open_thermostat", issue, is_fixable=False, severity=ir.IssueSeverity.WARNING,
                              translation_key="metrics_definition_v2")
    ir.async_create_issue(hass, "other_domain", f"x_{p.entry_id}", is_fixable=False,
                          severity=ir.IssueSeverity.WARNING, translation_key="x")
    await integration.async_remove_entry(hass, p)
    registry = ir.async_get(hass)
    assert all(registry.async_get_issue("open_thermostat", issue) is None for issue in ids)
    assert registry.async_get_issue("open_thermostat", f"metrics_definition_v2_{other.entry_id}") is not None
    assert registry.async_get_issue("other_domain", f"x_{p.entry_id}") is not None
