"""Native HA presentation group for the shared controller, never a config owner.

The central document remains in entry.data. This empty subentry only provides a
normal named section in HA's existing integration page; it is not an add choice.
"""
from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_TOPIC_PREFIX, DOMAIN
from .product import HA_VERSION, SUPPORTED_HA_VERSIONS, is_product

GROUP_TYPE = "installation"
GROUP_UNIQUE_ID = "controller_overview"
GROUP_TITLE = "Installatie en ketel"


def ensure_installation_group(hass, entry):
    """Group existing IDs synchronously, before platforms/listeners are started.

    Registry device-move events remove entities still assigned to the old
    subentry. Move the entity associations first, without yielding, so the
    queued event observes the complete new association and preserves IDs.
    """
    if not is_product(entry) or HA_VERSION not in SUPPORTED_HA_VERSIONS:
        raise ValueError("setup_platform_unsupported")
    groups = [s for s in entry.subentries.values() if s.subentry_type == GROUP_TYPE]
    if len(groups) > 1 or any(s.unique_id != GROUP_UNIQUE_ID or dict(s.data) for s in groups):
        raise ValueError("installation_group_conflict")
    group = groups[0] if groups else ConfigSubentry(
        data=MappingProxyType({}), subentry_type=GROUP_TYPE,
        title=GROUP_TITLE, unique_id=GROUP_UNIQUE_ID)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    hub = devices.async_get_device_by_identifier((DOMAIN, entry.data[CONF_TOPIC_PREFIX]), entry.entry_id)
    members = [] if hub is None else [
        e for e in er.async_entries_for_device(entities, hub.id, include_disabled_entities=True)
        if e.config_entry_id == entry.entry_id and e.platform == DOMAIN]
    if (hub and hub.config_subentry_id not in (None, group.subentry_id)) or any(
            e.config_subentry_id not in (None, group.subentry_id) for e in members):
        raise ValueError("installation_group_conflict")
    created = not groups
    if created:
        hass.config_entries.async_add_subentry(entry, group)
    previous = {e.entity_id: e.config_subentry_id for e in members}
    try:
        for member in members:
            if member.config_subentry_id != group.subentry_id:
                entities.async_update_entity(member.entity_id, config_subentry_id=group.subentry_id)
        if hub and hub.config_subentry_id != group.subentry_id:
            devices.async_update_device(hub.id, new_config_subentry_id=group.subentry_id)
    except Exception:
        # No await: even queued device events must see the restored association.
        for entity_id, subentry_id in previous.items():
            entities.async_update_entity(entity_id, config_subentry_id=subentry_id)
        if hub and (current := devices.async_get(hub.id)) and current.config_subentry_id != hub.config_subentry_id:
            devices.async_update_device(hub.id, new_config_subentry_id=hub.config_subentry_id)
        if created:
            hass.config_entries.async_remove_subentry(entry, group.subentry_id)
        raise
    return group.subentry_id
