"""Hub entity names come from translation keys (EN/NL/PL), and existing entity IDs never change (audit 9)."""
import json
import logging
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant import loader
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, translation
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.open_thermostat.binary_sensor import HubConnection
from custom_components.open_thermostat.sensor import HUB_METRICS, VERSIONED_METRICS, HubMetric
from test_room_plan import json_manifest
from test_v1_native import entry

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


# The boiler counters got short, plain names (entity names stay <= 45 characters); the rest keep theirs.
COUNTERS = {"energy": "Estimated energy", "energy_warm_water": "Estimated hot water energy",
            "energy_heating": "Estimated heating energy", "energy_unattributed": "Estimated unattributed energy",
            "burner_observed_time": "Observed flame time", "warm_water_usage": "Hot water volume",
            "warm_water_avg_flow": "Average hot water flow"}


def expected_english():
    """The English names by translation key: the old hard-coded ones, the counters shortened."""
    names = {}
    for topic, metrics in HUB_METRICS.items():
        for metric, (*_, name) in metrics.items():
            if topic == "ems_metrics" and metric in VERSIONED_METRICS:
                names[f"hub_{metric}_v2"] = COUNTERS[metric]
                names[f"hub_{metric}_legacy"] = "Old: " + COUNTERS[metric]
            else:
                names[f"hub_{metric}"] = name
    return names


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"])
def test_every_hub_name_is_translated_and_english_is_unchanged(filename):
    entity = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))["entity"]
    names = {key: entity["sensor"][key]["name"] for key in expected_english()}
    assert entity["binary_sensor"]["hub_connected"]["name"] and entity["update"]["e32_firmware"]["name"]
    if filename.endswith(("strings.json", "en.json")):
        assert names == expected_english()
        assert (entity["binary_sensor"]["hub_connected"]["name"], entity["update"]["e32_firmware"]["name"]) == (
            "Connected", "Firmware")
    elif filename.endswith("nl.json"):
        assert names["hub_memory_free"] == "Vrij geheugen" and names["hub_uptime"] == "Bedrijfstijd apparaat"
        assert names["hub_energy_v2"] == "Geschatte energie" and entity["binary_sensor"]["hub_connected"]["name"] == "Verbonden"
    assert all(names.values()) and all(len(name) <= 45 for name in names.values())


def test_no_hard_coded_english_name_is_left_on_these_entities():
    source = (COMPONENT / "sensor.py").read_text(encoding="utf-8")
    assert '"Legacy history: " + name' not in source and "self._attr_name = name\n" not in source
    assert '_attr_name = "Firmware"' not in (COMPONENT / "firmware_update.py").read_text(encoding="utf-8")
    assert '_attr_name = "Connected"' not in (COMPONENT / "binary_sensor.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_names_follow_the_language_and_existing_entity_ids_stay(hass, monkeypatch):
    loader.async_setup(hass)
    await ar.async_load(hass, load_empty=True)
    config_entry = entry(hass)
    dr.async_get(hass).async_get_or_create(config_entry_id=config_entry.entry_id,
                                           identifiers={("open_thermostat", "fixture")}, name="OpenThermostat")
    integration = loader.Integration(hass, "custom_components.open_thermostat", COMPONENT, json_manifest(COMPONENT),
                                     top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    registry = er.async_get(hass)
    # Entities of an earlier release, registered under their English entity IDs.
    old = {uid: registry.async_get_or_create(domain, "open_thermostat", uid, config_entry=config_entry,
                                             suggested_object_id=object_id).entity_id
           for domain, uid, object_id in (("sensor", "fixture_hub_memory_free", "openthermostat_free_memory"),
                                          ("sensor", "fixture_hub_energy_v2",
                                           "openthermostat_estimated_nominal_modulation_energy_definition_v2"),
                                          ("binary_sensor", "fixture_hub_connected", "openthermostat_connected"))}
    hass.config.language = "nl"
    entities = {"sensor": [HubMetric("fixture", "device_status", "memory_free", config_entry.entry_id),
                           HubMetric("fixture", "ems_metrics", "energy", config_entry.entry_id),
                           HubMetric("fixture", "device_status", "uptime", config_entry.entry_id)],
                "binary_sensor": [HubConnection("fixture")]}
    platforms = []
    try:
        for domain, items in entities.items():
            platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
                                      platform_name="open_thermostat", platform=None,
                                      scan_interval=timedelta(seconds=30), entity_namespace=None)
            platform.config_entry = config_entry
            await platform.platform_data.async_load_translations()
            platforms.append(platform)
            await platform.async_add_entities(items)
        await hass.async_block_till_done()
        memory, energy, uptime = entities["sensor"]
        connected = entities["binary_sensor"][0]
        # The registry keeps the existing IDs; the names are Dutch now.
        assert (memory.entity_id, energy.entity_id, connected.entity_id) == tuple(old.values())
        assert memory.entity_id == "sensor.openthermostat_free_memory"
        assert hass.states.get(memory.entity_id).attributes["friendly_name"] == "OpenThermostat Vrij geheugen"
        assert hass.states.get(energy.entity_id).attributes["friendly_name"] == (
            "OpenThermostat Geschatte energie")
        assert hass.states.get(connected.entity_id).attributes["friendly_name"] == "OpenThermostat Verbonden"
        assert hass.states.get(uptime.entity_id).attributes["friendly_name"] == "OpenThermostat Bedrijfstijd apparaat"
    finally:
        for platform in platforms:
            await platform.async_reset()
