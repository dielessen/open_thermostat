"""Memory in kB and uptime in hours also for existing installations (beta.23).

0.4.0b13 made these sensors kB and h, but Home Assistant had pinned the old
display unit of existing records in "sensor.private" (B and s), so the owner's
HA kept showing "56440.0 B" and "1216.0 s" (31 Oct 2026). The integration
releases exactly that old pin once; a unit the user chose stays.
"""
import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.native_entity_cleanup import PINNED_UNITS, release_pinned_units
from custom_components.open_thermostat.sensor import HubMetric


def pinned(registry, e, device, unique_id, object_id, old, user_unit=None):
    entity_id = registry.async_get_or_create("sensor", "open_thermostat", unique_id, config_entry=e,
                                             device_id=device.id, suggested_object_id=object_id,
                                             unit_of_measurement=old).entity_id
    # What the owner's registry holds (read from the live .storage on 1 Nov 2026).
    registry.async_update_entity_options(entity_id, "sensor.private", {"suggested_unit_of_measurement": old})
    if user_unit:
        registry.async_update_entity_options(entity_id, "sensor", {"unit_of_measurement": user_unit})
    return entity_id


@pytest.mark.asyncio
async def test_the_old_pin_is_released_once_and_the_users_own_unit_stays(hass):
    from test_modern_metrics import system
    from test_room_sensor_restore import platform
    e, runtime, client, now = await system(hass)
    actual = await platform(hass, e)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, name="E32",
                                                    identifiers={("open_thermostat", "fixture")})
    registry = er.async_get(hass)
    free = pinned(registry, e, device, "fixture_hub_memory_free", "woonkamer_openthermostat_free_memory", "B")
    uptime = pinned(registry, e, device, "fixture_hub_uptime", "woonkamer_openthermostat_device_uptime", "s")
    # The user picked MB for this one: never touched.
    chosen = pinned(registry, e, device, "fixture_hub_memory_min_free",
                    "woonkamer_openthermostat_minimum_free_memory", "B", user_unit="MB")
    try:
        assert sorted(release_pinned_units(hass, e, "fixture")) == sorted([free, uptime])
        assert release_pinned_units(hass, e, "fixture") == []  # once
        hub = [HubMetric("fixture", "device_status", m, e.entry_id) for m in ("memory_free", "uptime", "memory_min_free")]
        await actual.async_add_entities(hub)
        await hass.async_block_till_done()
        for entity in hub:
            entity.update_payload({"mem_free": 56440, "uptime": 4569, "mem_min_free": 17636}, True)
            entity.async_write_ha_state()
        await hass.async_block_till_done()
        assert [entity.entity_id for entity in hub] == [free, uptime, chosen]  # IDs unchanged
        units = {entity_id: hass.states.get(entity_id).attributes.get("unit_of_measurement")
                 for entity_id in (free, uptime, chosen)}
        assert units == {free: "kB", uptime: "h", chosen: "MB"}
        assert float(hass.states.get(free).state) == pytest.approx(56.44, abs=0.5)
        assert float(hass.states.get(uptime).state) == pytest.approx(4569 / 3600, abs=0.01)
        # After a reload Home Assistant does not pin B or s again.
        await actual.async_reset()
        hub = [HubMetric("fixture", "device_status", m, e.entry_id) for m in ("memory_free", "uptime")]
        await actual.async_add_entities(hub)
        await hass.async_block_till_done()
        for entity in hub:
            entity.update_payload({"mem_free": 56440, "uptime": 4569}, True)
            entity.async_write_ha_state()
        await hass.async_block_till_done()
        assert hass.states.get(free).attributes["unit_of_measurement"] == "kB"
        assert hass.states.get(uptime).attributes["unit_of_measurement"] == "h"
        assert (registry.async_get(free).options.get("sensor.private") or {}).get("suggested_unit_of_measurement") != "B"
        assert registry.async_get(chosen).options["sensor"]["unit_of_measurement"] == "MB"
    finally:
        await actual.async_reset()
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_without_the_release_home_assistant_keeps_showing_bytes_and_seconds(hass):
    """The cause as seen live: the pinned old unit wins over the entity's kB and h."""
    from test_modern_metrics import system
    from test_room_sensor_restore import platform
    e, runtime, client, now = await system(hass)
    actual = await platform(hass, e)
    device = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, name="E32",
                                                    identifiers={("open_thermostat", "fixture")})
    registry = er.async_get(hass)
    free = pinned(registry, e, device, "fixture_hub_memory_free", "woonkamer_openthermostat_free_memory", "B")
    try:
        hub = [HubMetric("fixture", "device_status", "memory_free", e.entry_id)]
        await actual.async_add_entities(hub)
        await hass.async_block_till_done()
        hub[0].update_payload({"mem_free": 56440}, True)
        hub[0].async_write_ha_state()
        await hass.async_block_till_done()
        assert hass.states.get(free).attributes["unit_of_measurement"] == "B"
        assert float(hass.states.get(free).state) == pytest.approx(56440, abs=500)
    finally:
        await actual.async_reset()
        await runtime.async_stop()


def test_only_the_exact_old_pins_are_listed():
    assert PINNED_UNITS == {"hub_memory_free": "B", "hub_memory_min_free": "B", "hub_memory_max_alloc": "B",
                            "hub_uptime": "s"}
