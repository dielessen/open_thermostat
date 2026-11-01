"""Switches of an E32 product entry: the flow options (weather curve, learned flow and optimum start)
and the valve control of each room with radiator valves (e32_valves.py)."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if "v1_runtime" not in hass.data.get(DOMAIN, {}).get(entry.entry_id, {}):
        return
    from .e32_flow import async_setup_switches
    await async_setup_switches(hass, entry, async_add_entities)
    from .e32_valves import async_setup_switches as async_setup_valve_switches
    await async_setup_valve_switches(hass, entry, async_add_entities)
