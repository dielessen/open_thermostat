"""A new install names each room once in its entity IDs, also when the room's device gets the area of its name.

Found in the demo Home Assistant (rc.5, P21): a Dutch onboarding creates the areas Woonkamer, Keuken and Slaapkamer;
room_groups gives a new room device the existing area named like the room, and Home Assistant 2026.10 puts the
device's area in front of a new entity ID, so the rooms with an area of their name got sensor.woonkamer_woonkamer_reden
and climate.slaapkamer_slaapkamer while Badkamer (no such area) got sensor.badkamer_temperatuur.
"""
import logging
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant import loader
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, translation
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.open_thermostat import heating_link, room_groups
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.e32_comfort import _wanted as wanted_climates
from custom_components.open_thermostat.installation_group import ensure_installation_group
from custom_components.open_thermostat.product import PRODUCT_CONFIG
from test_room_plan import json_manifest
from test_v1_native import entry as make_entry

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
ROOMS = (("woonkamer", "Woonkamer"), ("slaapkamer", "Slaapkamer"), ("badkamer", "Badkamer"),
         ("studeerkamer", "Studeerkamer"))
# Each room's entities on three platforms, by the end of their unique ID: the names of a Dutch Home Assistant.
NAMES = {("sensor", "temperature"): "temperatuur", ("sensor", "setpoint"): "gewenste_temperatuur",
         ("sensor", "status"): "regelstatus", ("sensor", "reason"): "reden",
         ("binary_sensor", "demand"): "warmtevraag", ("climate", "thermostat"): None}


def room(room_id, name):
    return {"id": room_id, "name": name, "status": "ok", "source": "ha", "temperature": 20.5, "setpoint": 21.0,
            "demand": False}


async def dutch_install(hass, monkeypatch):
    loader.async_setup(hass)
    await ar.async_load(hass, load_empty=True)
    hass.config.language = "nl"
    integration = loader.Integration(hass, "custom_components.open_thermostat", COMPONENT, json_manifest(COMPONENT),
                                     top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={DOMAIN: integration}))
    parent = make_entry(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1})
    dr.async_get(hass).async_get_or_create(config_entry_id=parent.entry_id, identifiers={(DOMAIN, "fixture")},
                                           name="OpenThermostat")
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    return parent, ensure_installation_group(hass, parent)


async def add_rooms(hass, parent, install):
    """The room entities as a new install adds them: a sensor, binary sensor and climate platform."""
    groups = room_groups.async_setup_room_groups(hass, parent, install)
    hub = heating_link.HeatingHub("fixture")
    plan = {"schema": 1, "revision": 3, "rooms": [
        {"id": room_id, "name": name, "sources": [{"type": "ha", "id": f"sensor.{room_id}"}]} for room_id, name in ROOMS]}
    hub.plan = SimpleNamespace(plan=plan, room=lambda room_id: next(r for r in plan["rooms"] if r["id"] == room_id))
    groups.attach(hub)
    platforms, stops = [], []
    climates = SimpleNamespace(entry_id=parent.entry_id, options={})
    for domain, wanted in (("sensor", heating_link.wanted_sensors), ("binary_sensor", heating_link.wanted_demand),
                           ("climate", lambda hub: wanted_climates(hub, climates))):
        platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
                                  platform_name=DOMAIN, platform=None, scan_interval=timedelta(seconds=30),
                                  entity_namespace=None)
        platform.config_entry = parent
        await platform.platform_data.async_load_translations()
        platforms.append(platform)

        def add(new, platform=platform, **options):
            hass.async_create_task(platform.async_add_entities(new, **options))
        stops.append(heating_link.track_entities(hub, add, {"config_subentry_id": install}, wanted))
    hub.update({"schema": 1, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
                "ha_entities": [], "rooms": [room(room_id, name) for room_id, name in ROOMS]})
    await hass.async_block_till_done()

    async def stop():
        for item in stops:
            item()
        for platform in platforms:
            await platform.async_reset()
        groups.stop()
    return stop


def room_device(hass, parent, room_id):
    return dr.async_get(hass).async_get_device_by_identifier(
        heating_link.room_device_identifier("fixture", room_id), parent.entry_id)


def room_entity_ids(hass):
    entities = er.async_get(hass)
    return {(domain, room_id, key): entities.async_get_entity_id(domain, DOMAIN, f"fixture_e32_room_{room_id}_{key}")
            for room_id, _ in ROOMS for domain, key in NAMES}


@pytest.mark.asyncio
async def test_a_room_in_the_area_of_its_name_says_its_name_once(hass, monkeypatch):
    parent, install = await dutch_install(hass, monkeypatch)
    devices, areas = dr.async_get(hass), ar.async_get(hass)
    # The areas of a Dutch onboarding.
    woonkamer, keuken, slaapkamer = (areas.async_create(name) for name in ("Woonkamer", "Keuken", "Slaapkamer"))
    # A room the user already put in an area of another name (its device exists before its entities).
    study = devices.async_get_or_create(config_entry_id=parent.entry_id, config_subentry_id=install,
                                        identifiers={heating_link.room_device_identifier("fixture", "studeerkamer")},
                                        name="Studeerkamer")
    devices.async_update_device(study.id, area_id=keuken.id)
    stop = await add_rooms(hass, parent, install)
    try:
        # The area suggestion still works: a new room device lands in the existing area of its name.
        assert room_device(hass, parent, "woonkamer").area_id == woonkamer.id
        assert room_device(hass, parent, "slaapkamer").area_id == slaapkamer.id
        assert room_device(hass, parent, "badkamer").area_id is None
        assert room_device(hass, parent, "studeerkamer").area_id == keuken.id
        expected = {}
        for room_id, _ in ROOMS:
            # The user's own area of another name: Home Assistant's own ID, that area in front.
            start = "keuken_studeerkamer" if room_id == "studeerkamer" else room_id
            for (domain, key), name in NAMES.items():
                expected[(domain, room_id, key)] = f"{domain}.{start}_{name}" if name else f"{domain}.{start}"
        assert room_entity_ids(hass) == expected
        # What Home Assistant shows: the room once, then the entity's own name.
        assert hass.states.get("sensor.woonkamer_reden").attributes["friendly_name"] == "Woonkamer Reden"
        assert hass.states.get("climate.slaapkamer").attributes["friendly_name"] == "Slaapkamer"
    finally:
        await stop()


@pytest.mark.asyncio
async def test_an_existing_install_keeps_its_entity_ids(hass, monkeypatch):
    """Registered entities keep their IDs, the doubled ones of an rc.5 install included; only new ones get the room
    once. The user's own entity ID format (Settings -> Entities) is Home Assistant's to apply."""
    parent, install = await dutch_install(hass, monkeypatch)
    entities, areas = er.async_get(hass), ar.async_get(hass)
    areas.async_create("Woonkamer")
    areas.async_create("Slaapkamer")
    earlier = {
        ("sensor", "woonkamer", "status"): "sensor.woonkamer_woonkamer_regelstatus",  # an rc.5 install
        ("climate", "slaapkamer", "thermostat"): "climate.slaapkamer_slaapkamer",
        ("sensor", "woonkamer", "temperature"): "sensor.woonkamer_e32_regelaar_temperatuur",  # an early one
    }
    for (domain, room_id, key), entity_id in earlier.items():
        entities.async_get_or_create(domain, DOMAIN, f"fixture_e32_room_{room_id}_{key}", config_entry=parent,
                                     suggested_object_id=entity_id.split(".", 1)[1])
    stop = await add_rooms(hass, parent, install)
    try:
        found = room_entity_ids(hass)
        assert {key: found[key] for key in earlier} == earlier
        assert found[("sensor", "woonkamer", "reason")] == "sensor.woonkamer_reden"
        assert found[("climate", "woonkamer", "thermostat")] == "climate.woonkamer"
    finally:
        await stop()


@pytest.mark.asyncio
async def test_the_users_own_entity_id_format_is_left_to_home_assistant(hass, monkeypatch):
    parent, install = await dutch_install(hass, monkeypatch)
    ar.async_get(hass).async_create("Woonkamer")
    registry = er.async_get(hass)
    settings = getattr(registry, "settings", None)
    if settings is None or not hasattr(settings, "entity_id_parts"):
        pytest.skip("this Core has no entity ID format setting")
    monkeypatch.setattr(registry, "settings", type(settings)(entity_id_parts=(
        er.EntityNamePart.AREA, er.EntityNamePart.DEVICE, er.EntityNamePart.ENTITY)))
    stop = await add_rooms(hass, parent, install)
    try:
        assert room_entity_ids(hass)[("sensor", "woonkamer", "reason")] == "sensor.woonkamer_woonkamer_reden"
        assert room_entity_ids(hass)[("sensor", "badkamer", "reason")] == "sensor.badkamer_reden"
    finally:
        await stop()
