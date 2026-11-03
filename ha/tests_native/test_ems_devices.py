"""The devices on the E32's EMS bus as Home Assistant devices, and the E32's own firmware version (beta.23)."""
import json
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import device_registry as dr

from custom_components.open_thermostat import ems_devices
from custom_components.open_thermostat.firmware_update import E32FirmwareUpdate

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"


def payload(*devices):
    return json.dumps({"schema": 1, "devices": [dict(zip(("address", "product_id", "version", "brand_id"), d))
                                                 for d in devices]})


def test_the_product_table_matches_the_e32_pages_reference():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/generate_ems_products.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_payloads_are_ignored():
    assert ems_devices.parse("{") is None
    assert ems_devices.parse(json.dumps({"schema": 2, "devices": []})) is None
    assert ems_devices.parse(payload((0, None, None, None))) is None  # address 0
    assert ems_devices.parse(payload((8, None, None, None), (8, None, None, None))) is None  # duplicate
    assert ems_devices.parse(payload((8, 300, None, None))) is None
    assert ems_devices.parse(payload((8, None, None, None))) == [
        {"address": 8, "product_id": None, "version": None, "brand_id": None}]


# The owner's boiler as the E32 reads it (live HA, rc.2): a Nefit EcomLine Classic HRC 22 behind a
# Bosch EasyControl Adapter answers at 0x08 as product 206, version 2.1, brand 4 (Nefit).
OWNER = {"address": 8, "product_id": 206, "version": "2.1", "brand_id": 4}
HRC22H = "nefit-ecomline-classic-hrc-22h"


def profile(model=None, **extra):
    """A retained fw/config/boiler_profile as the E32 writes it (BoilerProfileReport.h)."""
    value = {"schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": 206, "version": "2.1"},
             **({"display_model": model} if model else {}), "supported": [], "not_fitted": [], "not_reported": [],
             "settled": False, **extra}
    return json.dumps(value)


def cached_translations(monkeypatch, language="en"):
    """The device names of this integration as Home Assistant caches them (translations/<language>.json)."""
    from homeassistant.helpers import translation
    names = json.loads((COMPONENT / f"translations/{language}.json").read_text(encoding="utf-8"))["device"]
    cached = {f"component.open_thermostat.device.{key}.name": value["name"] for key, value in names.items()}
    monkeypatch.setattr(translation, "async_get_cached_translations",
                        lambda hass, lang, category, domain=None: cached if category == "device" else {})


def test_names_follow_the_e32_page():
    # Thermostats keep the reference name when it is unambiguous for their role.
    assert ems_devices.describe({"address": 23, "product_id": 65, "version": "1.0", "brand_id": 4}) == {
        "name": "Nefit RC10 (0x17)", "manufacturer": "Nefit", "model": "RC10"}
    assert ems_devices.describe({"address": 8, "product_id": None, "version": None, "brand_id": None}) is None
    unknown = ems_devices.describe({"address": 23, "product_id": 2, "version": "2.0", "brand_id": 4})
    assert "name" not in unknown and unknown["translation_key"] == "ems_thermostat"
    assert unknown["translation_placeholders"] == {"address": "0x17", "product": "2"}


def test_the_boiler_is_named_after_the_chosen_model():
    assert ems_devices.describe(OWNER, HRC22H) == {
        "name": "Nefit Ecomline Classic HRC 22H (0x08)", "manufacturer": "Nefit", "model": "Ecomline Classic HRC 22H"}
    # Any catalog model, also an older one hidden from new selections; the brand is the chosen model's.
    assert ems_devices.describe(OWNER, "worcester-bosch-greenstar-4000")["name"] == "Worcester Bosch Greenstar 4000 (0x08)"
    assert ems_devices.describe(OWNER, "emsesp-product-206")["model"] == "Ecomline Excellent"  # the owner's own choice
    # Not a boiler: the choice never names a thermostat.
    assert ems_devices.describe({"address": 23, "product_id": 65, "version": "1.0", "brand_id": 4}, HRC22H)["name"] == \
        "Nefit RC10 (0x17)"


def test_without_a_choice_a_product_number_never_names_the_boiler():
    """Several boiler models share one product number; 206 is the owner's EcomLine Classic, not an Excellent."""
    for model in (None, "none", "a-model-this-ha-does-not-know", 7):
        described = ems_devices.describe(OWNER, model)
        assert described == {"manufacturer": "Nefit", "model": "EMS product 206", "translation_key": "ems_boiler_brand",
                             "translation_placeholders": {"address": "0x08", "product": "206", "brand": "Nefit"}}
        assert "Excellent" not in json.dumps(described)
    # Every boiler product number, also those with a single reference name (211: EasyControl Adapter).
    for product in map(int, ems_devices.products()["devices"]):
        described = ems_devices.describe({"address": 8, "product_id": product, "version": "1.0", "brand_id": 1})
        assert "name" not in described and described["model"] == f"EMS product {product}", product
    assert ems_devices.describe({"address": 8, "product_id": 206, "version": None, "brand_id": None}) == {
        "manufacturer": "EMS", "model": "EMS product 206", "translation_key": "ems_boiler",
        "translation_placeholders": {"address": "0x08", "product": "206"}}


def test_the_chosen_model_is_read_from_the_boiler_profile():
    assert ems_devices.profile_model(profile(HRC22H)) == HRC22H
    assert ems_devices.profile_model(profile()) is None                      # no model chosen: left out
    assert ems_devices.profile_model("") is None                            # profile cleared
    assert ems_devices.profile_model(profile("Not A Slug")) is None
    assert ems_devices.profile_model("{") is False                          # invalid: ignored
    assert ems_devices.profile_model(json.dumps({"schema": 2, "display_model": HRC22H})) is False
    assert ems_devices.profile_model(profile(HRC22H, padding="x" * 2000)) is False


def test_generic_names_are_translated_in_english_dutch_and_polish():
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        device = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["device"]
        for key in ("ems_boiler", "ems_boiler_brand", "ems_thermostat", "ems_device"):
            assert "{address}" in device[key]["name"] and "{product}" in device[key]["name"], (name, key)
        assert "{brand}" in device["ems_boiler_brand"]["name"], name
    english = {name: json.loads((COMPONENT / name).read_text(encoding="utf-8")) for name in ("strings.json", "translations/en.json")}
    assert english["strings.json"] == english["translations/en.json"]
    placeholders = {"address": "0x08", "product": "206", "brand": "Nefit"}
    assert {language: json.loads((COMPONENT / f"translations/{language}.json").read_text(encoding="utf-8"))["device"]
            ["ems_boiler_brand"]["name"].format(**placeholders) for language in ("en", "nl", "pl")} == {
        "en": "Nefit boiler (product 206) (0x08)", "nl": "Nefit-ketel (product 206) (0x08)",
        "pl": "Kocioł Nefit (produkt 206) (0x08)"}


async def ems_and_profile_setup(hass, monkeypatch, entry):
    callbacks = {}

    async def subscribe(_hass, topic, callback, *args, **kwargs):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    await ems_devices.async_setup_ems_devices(hass, entry)
    devices, boiler = callbacks["fixture/v1/fw/config/ems_devices"], callbacks["fixture/v1/fw/config/boiler_profile"]
    return (lambda *d: devices(SimpleNamespace(payload=payload(*d)))), (lambda p: boiler(SimpleNamespace(payload=p)))


def boilers(hass, entry):
    """This entry's devices with the boiler's identifier: never more than one."""
    found = [d for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
             if ("open_thermostat", "fixture_ems_08") in d.identifiers]
    assert len(found) <= 1
    return found[0] if found else None


@pytest.mark.asyncio
async def test_the_device_list_first_then_the_chosen_model(hass, monkeypatch):
    from test_product_flow import product
    cached_translations(monkeypatch)
    entry = product(hass)
    devices, boiler_profile = await ems_and_profile_setup(hass, monkeypatch, entry)
    devices(tuple(OWNER.values()))
    neutral = boilers(hass, entry)
    assert (neutral.name, neutral.manufacturer, neutral.model, neutral.model_id, neutral.sw_version) == (
        "Nefit boiler (product 206) (0x08)", "Nefit", "EMS product 206", "206", "2.1")
    boiler_profile(profile(HRC22H))
    chosen = boilers(hass, entry)
    assert chosen.id == neutral.id
    assert (chosen.name, chosen.manufacturer, chosen.model, chosen.model_id, chosen.sw_version) == (
        "Nefit Ecomline Classic HRC 22H (0x08)", "Nefit", "Ecomline Classic HRC 22H", "206", "2.1")
    # The profile is republished as fields are learned, and an invalid one is ignored: the name stays.
    boiler_profile(profile(HRC22H, settled=True))
    boiler_profile("{")
    assert boilers(hass, entry).name == "Nefit Ecomline Classic HRC 22H (0x08)"
    # The owner chooses another model, then none: the same device follows.
    boiler_profile(profile("nefit-ecomline-classic"))
    assert (boilers(hass, entry).id, boilers(hass, entry).name) == (neutral.id, "Nefit Ecomline Classic (0x08)")
    boiler_profile(profile())
    assert (boilers(hass, entry).id, boilers(hass, entry).name, boilers(hass, entry).model) == (
        neutral.id, "Nefit boiler (product 206) (0x08)", "EMS product 206")


@pytest.mark.asyncio
async def test_the_chosen_model_first_then_the_device_list(hass, monkeypatch):
    from test_product_flow import product
    cached_translations(monkeypatch, "nl")
    entry = product(hass)
    devices, boiler_profile = await ems_and_profile_setup(hass, monkeypatch, entry)
    boiler_profile(profile(HRC22H))
    assert boilers(hass, entry) is None                     # no identity read yet: no device
    devices((8, None, None, None))
    assert boilers(hass, entry) is None
    devices(tuple(OWNER.values()))
    assert (boilers(hass, entry).name, boilers(hass, entry).model) == (
        "Nefit Ecomline Classic HRC 22H (0x08)", "Ecomline Classic HRC 22H")
    boiler_profile("")                                      # profile cleared: the Dutch neutral name
    assert boilers(hass, entry).name == "Nefit-ketel (product 206) (0x08)"


@pytest.mark.asyncio
async def test_a_name_the_user_gave_the_boiler_stays(hass, monkeypatch):
    from test_product_flow import product
    cached_translations(monkeypatch)
    entry = product(hass)
    registry = dr.async_get(hass)
    devices, boiler_profile = await ems_and_profile_setup(hass, monkeypatch, entry)
    devices(tuple(OWNER.values()))
    registry.async_update_device(boilers(hass, entry).id, name_by_user="Ketel zolder")
    boiler_profile(profile(HRC22H))
    devices((8, 206, "2.2", 4))
    boiler = boilers(hass, entry)
    assert (boiler.name_by_user, boiler.name, boiler.sw_version) == (
        "Ketel zolder", "Nefit Ecomline Classic HRC 22H (0x08)", "2.2")
    boiler_profile(profile())
    assert boilers(hass, entry).name_by_user == "Ketel zolder"


@pytest.mark.asyncio
async def test_an_existing_boiler_device_is_renamed_in_place(hass, monkeypatch):
    """A device an older release named after the product table keeps its identifier and gets the new name."""
    from test_product_flow import product
    cached_translations(monkeypatch)
    entry = product(hass)
    registry = dr.async_get(hass)
    devices, boiler_profile = await ems_and_profile_setup(hass, monkeypatch, entry)
    devices((8, 206, "2.0", 4))
    old = registry.async_update_device(boilers(hass, entry).id, name="Nefit Ecomline Excellent (0x08)",
                                       model="Ecomline Excellent")  # as rc.2 left it
    devices(tuple(OWNER.values()))
    assert (boilers(hass, entry).id, boilers(hass, entry).name) == (old.id, "Nefit boiler (product 206) (0x08)")
    boiler_profile(profile(HRC22H))
    assert (boilers(hass, entry).id, boilers(hass, entry).model) == (old.id, "Ecomline Classic HRC 22H")


@pytest.mark.asyncio
async def test_known_identities_become_devices_via_the_e32_and_unknown_ones_wait(hass, monkeypatch):
    from test_product_flow import product
    cached_translations(monkeypatch)
    entry = product(hass)
    registry = dr.async_get(hass)
    hub = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("open_thermostat", "fixture")},
                                       name="OpenThermostat E32")
    callbacks = {}

    async def subscribe(_hass, topic, callback, *args, **kwargs):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    await ems_devices.async_setup_ems_devices(hass, entry)
    receive = callbacks["fixture/v1/fw/config/ems_devices"]
    receive(SimpleNamespace(payload=payload((8, None, None, None), (23, None, None, None))))
    assert registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id) is None
    assert ems_devices.diagnostics(hass, entry)[0]["address"] == 8
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1), (23, None, None, None))))
    adapter = registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id)
    assert (adapter.name, adapter.manufacturer, adapter.model, adapter.model_id, adapter.sw_version) == (
        "Bosch boiler (product 211) (0x08)", "Bosch", "EMS product 211", "211", "1.3")
    assert adapter.via_device_id == hub.id
    # A name the user gives stays; a newer version updates the device.
    registry.async_update_device(adapter.id, name_by_user="Ketel")
    receive(SimpleNamespace(payload=payload((8, 211, "1.4", 1))))
    adapter = registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id)
    assert (adapter.name_by_user, adapter.sw_version) == ("Ketel", "1.4")
    receive(SimpleNamespace(payload="{not json"))
    assert registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id) is not None


@pytest.mark.asyncio
async def test_the_e32_device_shows_its_firmware_version(hass):
    from test_product_flow import product
    entry = product(hass)
    registry = dr.async_get(hass)
    hub = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("open_thermostat", "fixture")},
                                       name="OpenThermostat E32")
    assert hub.sw_version is None
    fake = SimpleNamespace(hass=hass, registry_entry=SimpleNamespace(device_id=hub.id),
                           _attr_installed_version="v0.1.0-e32v2-beta.22")
    E32FirmwareUpdate._sync_device_version(fake)
    assert registry.async_get(hub.id).sw_version == "v0.1.0-e32v2-beta.22"
    fake._attr_installed_version = None  # unknown: nothing is overwritten
    E32FirmwareUpdate._sync_device_version(fake)
    assert registry.async_get(hub.id).sw_version == "v0.1.0-e32v2-beta.22"


async def ems_setup(hass, monkeypatch, entry):
    callbacks = {}

    async def subscribe(_hass, topic, callback, *args, **kwargs):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    await ems_devices.async_setup_ems_devices(hass, entry)
    return callbacks["fixture/v1/fw/config/ems_devices"]


@pytest.mark.asyncio
async def test_the_product_table_is_read_outside_the_event_loop(hass, monkeypatch):
    """The MQTT callback runs in the event loop; the table is read once in the executor at setup."""
    import asyncio
    from test_product_flow import product
    reads, original = [], Path.read_text

    def read_text(self, *args, **kwargs):
        try:
            asyncio.get_running_loop()
            reads.append((self.name, "loop"))
        except RuntimeError:
            reads.append((self.name, "executor"))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(ems_devices, "_PRODUCTS", None)
    receive = await ems_setup(hass, monkeypatch, product(hass))
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1))))
    assert [r for r in reads if r[0] == "ems_products.json"] == [("ems_products.json", "executor")]


@pytest.mark.asyncio
async def test_a_device_gone_from_the_bus_goes_after_a_day_of_complete_lists(hass, monkeypatch):
    """The owner's tado (0x17) was taken off the bus on 2026-11-01; the boiler adapter (0x08) stays."""
    from homeassistant.config_entries import ConfigEntry
    from custom_components.open_thermostat.heating_link import removable_device
    from test_product_flow import product
    entry = product(hass)
    registry = dr.async_get(hass)
    registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("open_thermostat", "fixture")},
                                 name="OpenThermostat E32")
    other = ConfigEntry(domain="tado", title="tado", version=1, minor_version=1, data={}, options={}, source="user",
                        unique_id="tado", discovery_keys=MappingProxyType({}), subentries_data=[])
    hass.config_entries._entries[other.entry_id] = other
    foreign = registry.async_get_or_create(config_entry_id=other.entry_id, identifiers={("tado", "fixture_ems_17")})
    hub = SimpleNamespace(fresh=True, heartbeat={"uptime_s": 30}, boots=0, prefix="fixture", rooms={}, ble={})
    hass.data["open_thermostat"][entry.entry_id]["heating_hub"] = hub
    receive = await ems_setup(hass, monkeypatch, entry)
    clock = [1_800_000_000.0]
    stale = hass.data["open_thermostat"][entry.entry_id]["ems_stale"]
    stale.clock = lambda: clock[0]
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1), (23, 2, "2.0", 4))))

    def device(address):
        return registry.async_get_device_by_identifier(("open_thermostat", f"fixture_ems_{address:02x}"), entry.entry_id)
    tado = device(0x17)
    # The E32 restarts without the tado: an empty, then a partial list while it starts.
    hub.boots, hub.heartbeat = 1, {"uptime_s": 5}
    receive(SimpleNamespace(payload=payload()))
    clock[0] += 2 * ems_devices.STALE_AFTER_S
    stale.check()
    assert device(0x08) is not None and device(0x17) is not None   # never on a list of a starting E32
    assert not removable_device(hass, entry, device(0x08))
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1))))
    assert not removable_device(hass, entry, registry.async_get(tado.id))
    hub.heartbeat = {"uptime_s": ems_devices.FULL_LIST_UPTIME_S}  # the list is complete now
    assert removable_device(hass, entry, registry.async_get(tado.id))   # the user may delete it at once
    assert not removable_device(hass, entry, device(0x08))
    stale.check()
    clock[0] += ems_devices.STALE_AFTER_S - 60
    hub.fresh = False                                                # an outage: nothing is decided
    stale.check()
    assert not removable_device(hass, entry, registry.async_get(tado.id))
    hub.fresh = True
    stale.check()
    assert registry.async_get(tado.id) is not None                  # not a day yet
    clock[0] += 60
    stale.check()
    assert registry.async_get(tado.id) is None
    assert device(0x08) is not None and registry.async_get(foreign.id) is not None   # another integration's stays
    # A device that comes back within the day is kept.
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1), (16, 2, "2.0", 4))))
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1))))
    clock[0] += ems_devices.STALE_AFTER_S / 2
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1), (16, 2, "2.0", 4))))
    clock[0] += ems_devices.STALE_AFTER_S
    stale.check()
    assert device(0x10) is not None
