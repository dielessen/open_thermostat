"""Select platform: E32 room state (active / inactive) through the room plan (room_plan.py),
the heating curve's flow at −10 °C (e32_flow.py) and the house mode (e32_house.py)."""
from .const import DOMAIN
from .room_plan import async_setup_selects


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_selects(hass, entry, async_add_entities)
    from .e32_house import async_setup_selects as async_setup_house_selects
    await async_setup_house_selects(hass, entry, async_add_entities)
    if "v1_runtime" in hass.data.get(DOMAIN, {}).get(entry.entry_id, {}):
        from .e32_flow import async_setup_selects as async_setup_flow_selects
        await async_setup_flow_selects(hass, entry, async_add_entities)
