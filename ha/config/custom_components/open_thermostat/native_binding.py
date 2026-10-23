"""Private in-memory native identity; never exported or physical qualification."""
from homeassistant.helpers import device_registry as dr, entity_registry as er


def native_binding_identity(hass, entity_id):
    """Pin native registry identity, never a display name or cached state object.

    A removed/recreated row, disabled entity, device reassignment or changed
    model invalidates the captured binding. Labels and entity renames are not identity.
    This guard supplies no physical qualification of its own.
    """
    entity = er.async_get(hass).async_get(entity_id)
    if entity is None or entity.disabled_by is not None:
        return None
    device = dr.async_get(hass).async_get(entity.device_id) if entity.device_id else None
    if entity.device_id and device is None:
        return None
    if device is not None and device.disabled_by is not None:
        return None
    return (entity.id, entity.unique_id, entity.platform, entity.config_entry_id,
            entity.device_id,
            (device.id, device.model, device.model_id, device.manufacturer,
             frozenset(device.identifiers), frozenset(device.connections)) if device else None)


