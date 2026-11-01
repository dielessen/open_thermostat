"""Old pre-v1 MQTT discovery entities of this E32 are retired by MQTT discovery itself (beta.23).

The owner's HA (1 Nov 2026) still had 38 "unavailable" MQTT entities such as
sensor.ib_therm_opth_warm_water_usage, created by the MQTT integration from
retained discovery configs the E32 firmware wrote before the v1 link.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import legacy_discovery
from custom_components.open_thermostat.legacy_discovery import legacy_config, user_changed

# The live configs, as read from the owner's broker.
UPTIME = ("homeassistant/sensor/fixture/opth_uptime/config", json.dumps({
    "name": "OpenThermostat device uptime", "uniq_id": "fixture_opth_uptime", "obj_id": "fixture_opth_uptime",
    "default_entity_id": "sensor.fixture_opth_uptime", "stat_t": "fixture/device_status",
    "dev": {"ids": ["fixture"]}}))
USAGE = ("homeassistant/sensor/fixture/opth_warm_water_usage/config", json.dumps({
    "name": "Warm water usage", "uniq_id": "fixture_opth_warm_water_usage",
    "default_entity_id": "sensor.fixture_opth_warm_water_usage", "stat_t": "fixture/ems_metrics",
    "dev": {"ids": ["fixture"]}}))
STATUS = ("homeassistant/binary_sensor/fixture/status/config", json.dumps({
    "name": "OpenThermostat", "uniq_id": "fixture", "default_entity_id": "binary_sensor.fixture_status",
    "state_topic": "fixture/status", "dev": {"name": "OpenThermostat", "mf": "intuibase", "ids": ["fixture"]}}))
RENAMED = ("homeassistant/sensor/fixture/opth_energy/config", json.dumps({
    "name": "Total energy consumption", "uniq_id": "fixture_opth_energy", "default_entity_id": "sensor.fixture_opth_energy",
    "stat_t": "fixture/ems_metrics", "dev": {"ids": ["fixture"]}}))
# Not ours: another device on the same node ID, another prefix, and a v1 topic.
FOREIGN = ("homeassistant/sensor/fixture/other/config", json.dumps({
    "uniq_id": "fixture_other", "stat_t": "fixture/x", "dev": {"ids": ["somebody-else"]}}))
OTHER_PREFIX = ("homeassistant/sensor/other-e32/opth_uptime/config", json.dumps({
    "uniq_id": "other-e32_opth_uptime", "stat_t": "other-e32/device_status", "dev": {"ids": ["other-e32"]}}))
V1 = ("homeassistant/sensor/fixture/v1thing/config", json.dumps({
    "uniq_id": "fixture_v1thing", "stat_t": "fixture/v1/fw/state/heating", "dev": {"ids": ["fixture"]}}))


def test_only_this_e32s_old_firmware_configs_qualify():
    assert legacy_config(*UPTIME, "homeassistant", "fixture") == ("sensor", "fixture_opth_uptime",
                                                                  "sensor.fixture_opth_uptime")
    assert legacy_config(*STATUS, "homeassistant", "fixture")[1] == "fixture"
    for message in (FOREIGN, OTHER_PREFIX, V1):
        assert legacy_config(*message, "homeassistant", "fixture") is None
    assert legacy_config(UPTIME[0], "{broken", "homeassistant", "fixture") is None
    assert legacy_config(UPTIME[0].replace("homeassistant", "custom"), UPTIME[1], "homeassistant", "fixture") is None


@pytest.mark.asyncio
async def test_untouched_old_entities_are_retired_and_the_users_own_stay(hass, monkeypatch):
    from test_product_flow import product
    entry = product(hass)
    registry = er.async_get(hass)
    # The MQTT integration's records (platform mqtt): one per config; the user renamed the energy one.
    for component, unique_id, object_id in (("sensor", "fixture_opth_uptime", "fixture_opth_uptime"),
                                            ("sensor", "fixture_opth_warm_water_usage", "fixture_opth_warm_water_usage"),
                                            ("binary_sensor", "fixture", "fixture_status"),
                                            ("sensor", "fixture_opth_energy", "fixture_opth_energy")):
        registry.async_get_or_create(component, "mqtt", unique_id, suggested_object_id=object_id)
    renamed = registry.async_get_entity_id("sensor", "mqtt", "fixture_opth_energy")
    registry.async_update_entity(renamed, name="Mijn energie")
    callbacks, published = {}, []

    async def subscribe(_hass, topic, callback, *args, **kwargs):
        callbacks[topic] = callback
        return lambda: None

    async def publish(_hass, topic, payload, qos=0, retain=False):
        published.append((topic, payload, qos, retain))
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_publish", publish)
    retire = await legacy_discovery.async_setup_legacy_discovery_retirement(hass, entry, delay=3600)
    receive = callbacks["homeassistant/+/fixture/+/config"]
    for topic, payload in (UPTIME, USAGE, STATUS, RENAMED, FOREIGN, OTHER_PREFIX, V1):
        receive(SimpleNamespace(topic=topic, payload=payload, retain=True))
    receive(SimpleNamespace(topic="homeassistant/sensor/fixture/live/config", payload=USAGE[1], retain=False))
    assert published == []  # nothing before the delay
    await retire()
    assert sorted(published) == sorted([(UPTIME[0], "", 0, True), (USAGE[0], "", 0, True), (STATUS[0], "", 0, True)])
    # The MQTT integration's registry is never edited here; the renamed one stays as the user left it.
    assert registry.async_get(renamed).name == "Mijn energie"
    assert hass.data["open_thermostat"][entry.entry_id]["legacy_discovery_retired"] == {"cleared": 3, "kept": 1}
    await hass.async_block_till_done()


def test_user_changes_keep_an_entity():
    base = SimpleNamespace(name=None, icon=None, area_id=None, labels=set(), disabled_by=None, hidden_by=None,
                           entity_id="sensor.fixture_opth_uptime")
    assert user_changed(base, "sensor.fixture_opth_uptime") is False
    for change in ({"name": "x"}, {"icon": "mdi:x"}, {"area_id": "kitchen"}, {"labels": {"a"}},
                   {"disabled_by": er.RegistryEntryDisabler.USER}, {"hidden_by": er.RegistryEntryHider.USER},
                   {"entity_id": "sensor.my_uptime"}):
        assert user_changed(SimpleNamespace(**{**vars(base), **change}), "sensor.fixture_opth_uptime") is True
    # Disabled by the integration (not the user) is no user choice.
    assert user_changed(SimpleNamespace(**{**vars(base), "disabled_by": er.RegistryEntryDisabler.INTEGRATION}),
                        "sensor.fixture_opth_uptime") is False
