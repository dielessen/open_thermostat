"""Button platform: back up the E32 settings now (e32_backup.py) and restart the E32 (e32_system.py)."""
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
    from .e32_backup_entities import async_setup_buttons
    await async_setup_buttons(hass, entry, async_add_entities)
    from .e32_system import async_setup_buttons as async_setup_restart_button
    await async_setup_restart_button(hass, entry, async_add_entities)
