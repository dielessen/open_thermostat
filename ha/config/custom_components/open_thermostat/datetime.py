"""Datetime platform: E32 room "inactive until" through the room plan (room_plan.py) and the
house's "Holiday until" (e32_house.py)."""
from .e32_house import async_setup_datetimes as async_setup_house_datetimes
from .room_plan import async_setup_datetimes


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_datetimes(hass, entry, async_add_entities)
    await async_setup_house_datetimes(hass, entry, async_add_entities)
