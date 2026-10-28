"""Datetime platform: E32 room "inactive until" through the room plan (room_plan.py)."""
from .room_plan import async_setup_datetimes


async def async_setup_entry(hass, entry, async_add_entities):
    await async_setup_datetimes(hass, entry, async_add_entities)
