"""Our own name (plan item 27) and the default-password warning: real HA registries, no device."""
import asyncio
from datetime import timedelta
import json
import logging
from pathlib import Path
import shutil

import pytest
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers.service_info.mqtt import MqttServiceInfo

from custom_components.open_thermostat import controller_link as link
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.const import DEFAULT_TOPIC_PREFIX, MANUFACTURER
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
from custom_components.open_thermostat.e32_access import (DEFAULT_PASSWORD_ISSUE, password_page_url,
                                                            report_password)
from custom_components.open_thermostat.v1_climate import async_setup_entry as setup_climate
from custom_components.open_thermostat.v1_runtime import ShadowRuntime

from test_controller_link import authenticated_readbacks
from test_room_editor import configured  # noqa: F401  (fixture)
from test_v1_native import LocalTransport, entry, room

ROOT = Path(__file__).resolve().parents[2]
INTEGRATION = ROOT / "ha/config/custom_components/open_thermostat"


def test_the_integration_names_openthermostat_as_manufacturer_everywhere():
    assert MANUFACTURER == "OpenThermostat"
    for path in sorted(INTEGRATION.rglob("*")):
        if path.suffix in {".py", ".json", ".yaml"}:
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if "intuibase" in line.lower()]
            # Only the name older releases stored, so setup can rename those devices.
            assert lines == (['OLD_MANUFACTURER = "intuibase"'] if path.name == "const.py" else []), path.name


@pytest.mark.asyncio
async def test_setup_renames_every_device_an_older_release_stored(hass, monkeypatch):
    """Hub, E32 rooms (Badkamer, Woonkamer) and a Bluetooth sensor: before any entity is added again."""
    import custom_components.open_thermostat as integration
    from homeassistant.components import mqtt
    from unittest.mock import AsyncMock
    from custom_components.open_thermostat.heating_link import ble_device_identifier, room_device_identifier
    parent = entry(hass)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    identifiers = [("open_thermostat", "fixture"), room_device_identifier("fixture", "badkamer"),
                   room_device_identifier("fixture", "woonkamer"), ble_device_identifier("fixture", "a4c138a3e8db")]
    old = [devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={i}, name=i[1],
                                       manufacturer="intuibase") for i in identifiers]
    room_entity = entities.async_get_or_create("sensor", "open_thermostat", "fixture_e32_room_badkamer_temperature",
                                               config_entry=parent, device_id=old[1].id)
    other = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={("zha", "x")},
                                        manufacturer="_TZE200_other")
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock(return_value=True))
    monkeypatch.setattr(mqtt, "async_subscribe", AsyncMock(return_value=lambda: None))
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None))
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    try:
        assert await integration.async_setup_entry(hass, parent)
        after = dr.async_entries_for_config_entry(devices, parent.entry_id)
        assert {d.id for d in after} == {d.id for d in old} | {other.id}
        for device in old:
            current = devices.async_get(device.id)
            assert current.manufacturer == "OpenThermostat" and current.identifiers == device.identifiers
        assert devices.async_get(other.id).manufacturer == "_TZE200_other"  # not ours: untouched
        assert entities.async_get(room_entity.entity_id).device_id == old[1].id
    finally:
        await integration.async_unload_entry(hass, parent)
        state = hass.data.get("open_thermostat", {}).pop(parent.entry_id, {})
        for key in ("heating_tracker", "v1_runtime"):
            if state.get(key) is not None:
                await state[key].async_stop()


@pytest.mark.asyncio
async def test_the_new_manufacturer_updates_existing_devices_without_new_devices_or_entities(hass):
    binding = room(hass)
    parent = entry(hass, enabled=True, room=binding)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    # As stored by an older release: the same identifiers, the old manufacturer.
    hub = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={("open_thermostat", "fixture")},
                                      name="OpenThermostat", manufacturer="intuibase", model="OpenThermostat")
    old_room = devices.async_get_or_create(
        config_entry_id=parent.entry_id, config_subentry_id=next(iter(parent.subentries)), identifiers={("open_thermostat", f"fixture_room_{binding.room_id}")},
        name=f"OpenThermostat — {binding.name}", manufacturer="intuibase", model="OpenThermostat room")
    existing = entities.async_get_or_create("climate", "open_thermostat", f"fixture_room_{binding.room_id}_climate",
                                            config_entry=parent, device_id=old_room.id,
                                            suggested_object_id="living_room_thermostat")
    before_devices = {d.id for d in dr.async_entries_for_config_entry(devices, parent.entry_id)}
    before_entities = {e.entity_id for e in er.async_entries_for_config_entry(entities, parent.entry_id)}
    runtime = ShadowRuntime(hass, parent, [binding])
    runtime.attach_transport(LocalTransport())
    hass.data["open_thermostat"] = {parent.entry_id: {"v1_runtime": runtime}}
    await runtime.async_start()
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="climate",
                              platform_name="open_thermostat", platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = parent
    try:
        tasks = []

        def add(new, *, config_subentry_id=None):
            tasks.append(hass.async_create_task(platform.async_add_entities(new, config_subentry_id=config_subentry_id)))
        await setup_climate(hass, parent, add)
        await asyncio.gather(*tasks)
        assert {d.id for d in dr.async_entries_for_config_entry(devices, parent.entry_id)} == before_devices
        assert {e.entity_id for e in er.async_entries_for_config_entry(entities, parent.entry_id)} == before_entities
        updated = devices.async_get(old_room.id)
        assert updated.manufacturer == "OpenThermostat"
        assert updated.identifiers == {("open_thermostat", f"fixture_room_{binding.room_id}")}
        assert entities.async_get(existing.entity_id).device_id == old_room.id
        assert existing.entity_id == "climate.living_room_thermostat"
        # The hub device is matched by its identifiers too: metadata changes, the device stays.
        again = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={("open_thermostat", "fixture")},
                                            name="OpenThermostat", manufacturer=MANUFACTURER, model="OpenThermostat")
        assert again.id == hub.id and again.manufacturer == "OpenThermostat"
    finally:
        await platform.async_reset()
        await runtime.async_stop()


def _flow(hass, source="user"):
    flow = OpenThermostatConfigFlow()
    flow.hass, flow.handler, flow.context = hass, "open_thermostat", {"source": source}
    return flow


def _default(form, key="topic_prefix"):
    for field, value in form["data_schema"].schema.items():
        if str(field) == "advanced":
            return _default({"data_schema": value.schema}, key)
        if str(field) == key:
            return field.default()
    raise AssertionError(key)


@pytest.mark.asyncio
async def test_a_new_installation_defaults_to_the_openthermostat_prefix(hass):
    assert DEFAULT_TOPIC_PREFIX == "openthermostat"
    form = await _flow(hass).async_step_user()
    assert form["step_id"] == "installation" and _default(form) == "openthermostat"
    form = await _flow(hass).async_step_shadow()
    assert _default(form) == "openthermostat"
    # The older-firmware path keeps the prefix that firmware always used.
    assert _default(await _flow(hass).async_step_legacy()) == "ib-therm"


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["openthermostat", "ib-therm"])
async def test_discovery_accepts_the_new_and_the_older_prefix(hass, prefix):
    flow = _flow(hass, "mqtt")
    form = await flow.async_step_mqtt(MqttServiceInfo(topic=f"{prefix}/room_data", payload=json.dumps({"rooms": []}),
                                                      qos=0, retain=True, subscribed_topic="+/room_data", timestamp=0))
    assert form["step_id"] == "installation" and _default(form) == prefix
    assert flow.unique_id == prefix


@pytest.mark.asyncio
async def test_an_existing_ib_therm_installation_is_not_offered_again(hass):
    existing = entry(hass)
    hass.config_entries.async_update_entry(existing, unique_id="ib-therm", data={**existing.data, "topic_prefix": "ib-therm"})
    flow = _flow(hass, "mqtt")
    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_mqtt(MqttServiceInfo(topic="ib-therm/room_data", payload=json.dumps({"rooms": []}),
                                                   qos=0, retain=True, subscribed_topic="+/room_data", timestamp=0))
    assert existing.data["topic_prefix"] == "ib-therm"


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["ib-therm", "openthermostat"])
async def test_connect_e32_keeps_the_stored_base_of_either_name(hass, configured, prefix):
    parent, _, _ = configured
    hass.config_entries.async_update_entry(parent, data={**parent.data, "topic_prefix": prefix})
    reads = authenticated_readbacks()
    reads["settings"]["mqtt"]["base"] = prefix
    plan = link.initial_controller_link(hass, parent, **reads)
    assert plan.observed_settings["mqtt"]["base"] == prefix and plan.settings["mqtt"]["base"] == prefix


def _stage_e32_filesystem(tmp_path):
    """Run scripts/e32v2_filesystem.py as the build does, on a copy of the shipped data."""
    project = tmp_path / "project"
    project.mkdir()
    shutil.copytree(ROOT / "data", project / "data", ignore=shutil.ignore_patterns("deps", "*.gz"))

    class Env:
        def subst(self, value):
            return str({"$PROJECT_DIR": project, "$BUILD_DIR": tmp_path / "build"}[value])

        def Replace(self, **kwargs):
            self.replaced = kwargs
    env = Env()
    code = (ROOT / "scripts/e32v2_filesystem.py").read_text(encoding="utf-8")
    exec(compile(code, "e32v2_filesystem.py", "exec"), {"Import": lambda name: None, "env": env, "__name__": "scons"})
    return Path(env.replaced["PROJECT_DATA_DIR"])


def test_a_new_install_ships_the_openthermostat_names(tmp_path):
    network = json.loads((ROOT / "data/cfg/cfgnetwork.json").read_text(encoding="utf-8"))
    assert network["mqtt"]["base"] == "openthermostat"
    assert 'id="DeviceMQTTBase" data-hint="The start of all MQTT topics of the E32." value="openthermostat"' in (
        ROOT / "data/html/network.html").read_text(encoding="utf-8")
    staged = json.loads((_stage_e32_filesystem(tmp_path) / "cfg/cfgnetwork.json").read_text(encoding="utf-8"))
    assert staged["mqtt"]["base"] == "openthermostat" and staged["mqtt"]["enabled"] is False
    # esp32dev/esp32s3: empty, so the firmware derives OpenThermostat-xxxxxx and the documented password.
    ap = json.loads((ROOT / "data/cfg/cfgap.json").read_text(encoding="utf-8"))
    assert ap["ssid"] == "" and ap["password"] == ""
    config = (ROOT / "src/config.h").read_text(encoding="utf-8") + (ROOT / "src/config.cpp").read_text(encoding="utf-8")
    assert "IntuiBase" not in config


def test_a_stored_base_is_read_as_it_is():
    """The firmware load only reads: the stored base is never replaced by the shipped default."""
    source = (ROOT / "src/config.cpp").read_text(encoding="utf-8")
    mqtt = source[source.index("MqttConfig getMqttConfig()"):source.index("OpenWeatherConfig getOpenWeatherConfig()")]
    assert 'config.base = json::getString(mqtt, "base");' in mqtt
    assert "saveDeviceNetworkSettings" not in mqtt and "openthermostat" not in mqtt
    settings = (ROOT / "src/DeviceNetworkSettings.h").read_text(encoding="utf-8")
    read = settings[settings.index("inline String readDeviceNetworkSettings()"):settings.index("inline bool saveDeviceNetworkSettings")]
    assert "NVS_READONLY" in read and "nvs_set" not in read


def test_the_about_page_keeps_the_credit_without_the_old_contact_address():
    about = (ROOT / "data/html/about.html").read_text(encoding="utf-8")
    assert "info@intuibase.pl" not in about and "mailto:" not in about
    assert "Copyright 2023 Paweł Filipczak" in about and "MIT license" in about
    assert "https://github.com/intuibase/open_thermostat" in about


@pytest.mark.asyncio
async def test_the_default_password_issue_links_to_the_e32_page_and_never_carries_the_password(hass):
    parent = entry(hass)
    hass.config_entries.async_update_entry(parent, title="Home", data={
        **parent.data, CONTROLLER_ADDRESS: "http://192.168.1.206", CONTROLLER_PASSWORD: "admin-secret-value"})
    report_password(hass, parent, True)
    issue = ir.async_get(hass).async_get_issue("open_thermostat", f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}")
    assert issue.learn_more_url == "http://192.168.1.206/#about"
    assert issue.translation_placeholders == {"name": "Home"}
    assert "admin-secret-value" not in repr(issue.to_json()) and "admin-secret-value" not in repr(issue)
    report_password(hass, parent, False)
    assert ir.async_get(hass).async_get_issue("open_thermostat", f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}") is None
    # No (valid) address stored: the issue still appears, without a link.
    for address in (None, "ftp://192.168.1.206", "http://8.8.8.8"):
        data = {k: v for k, v in parent.data.items() if k != CONTROLLER_ADDRESS}
        if address is not None:
            data[CONTROLLER_ADDRESS] = address
        hass.config_entries.async_update_entry(parent, data=data)
        assert password_page_url(parent) is None
        report_password(hass, parent, True)
        issue = ir.async_get(hass).async_get_issue("open_thermostat", f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}")
        assert issue is not None and issue.learn_more_url is None


@pytest.mark.parametrize("language,title", [("en", "E32 still uses the default password"),
                                            ("nl", "E32 gebruikt nog het standaardwachtwoord")])
def test_the_default_password_issue_is_worded_in_english_and_dutch(language, title):
    strings = json.loads((INTEGRATION / f"translations/{language}.json").read_text(encoding="utf-8"))
    issue = strings["issues"][DEFAULT_PASSWORD_ISSUE]
    assert issue["title"] == title and "{name}" in issue["description"]
