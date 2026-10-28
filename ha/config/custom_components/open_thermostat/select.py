"""Select platform: E32 room state (active / inactive) through the room plan (room_plan.py)."""
from .room_plan import async_setup_selects


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_selects(hass, entry, async_add_entities)
