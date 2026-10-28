"""Update platform: E32 firmware through Home Assistant (firmware_update.py)."""
from .firmware_update import async_setup_firmware_update


async def async_setup_entry(hass, entry, async_add_entities):
    from .product import is_product
    options = {}
    if is_product(entry):
        from .installation_group import ensure_installation_group
        options["config_subentry_id"] = ensure_installation_group(hass, entry)
    await async_setup_firmware_update(hass, entry, async_add_entities, **options)
