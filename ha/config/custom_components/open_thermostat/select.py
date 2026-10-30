"""Select platform: E32 room state (active / inactive) through the room plan (room_plan.py),
and the heating curve's flow at −10 °C (e32_flow.py)."""
from .const import DOMAIN
from .room_plan import async_setup_selects


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_selects(hass, entry, async_add_entities)
    if "v1_runtime" in hass.data.get(DOMAIN, {}).get(entry.entry_id, {}):
        from .e32_flow import async_setup_selects as async_setup_flow_selects
        await async_setup_flow_selects(hass, entry, async_add_entities)
