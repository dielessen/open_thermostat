"""Remove registry identities a modern-mode E32 product entry no longer provides.

One route, one set of entities: the boiler-fields sensors are the boiler
entities. The legacy hub boiler/status identities are never fed by native
firmware. Boiler fields used to be created all at once and then disabled as
never (or only unreliably) reported; they now appear on their first real value,
so those disabled records only clutter the registry.

Only records of THIS config entry and platform are considered, and only while
untouched by the user (no name, icon, area, label, hidden or user-disabled
state). A customised legacy record is kept, disabled. Removing a registry
record never deletes Recorder history, and Home Assistant restores the same
entity_id if the integration provides that unique_id again.

E32 rooms: a room that is no longer in the E32 room plan (removed in the HA
room editor or on the E32's own page) loses its room device and that device's
entities, but only once a plan has actually been read from the E32 (never on
a missing or unreadable plan) and only this entry's own devices.
"""
import logging
import re

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_INTEGRATION = er.RegistryEntryDisabler.INTEGRATION


def legacy_unique_ids(prefix):
    from .binary_sensor import BOILER_STATES
    from .sensor import HUB_METRICS
    ids = {f"{prefix}_hub_connected", f"{prefix}_hub_dhw_capabilities",
           f"{prefix}_hub_rtc_temperature"}  # E32 has no RTC temperature sensor.
    ids.update(f"{prefix}_hub_{metric}" for metric in HUB_METRICS["ems_status"])
    ids.update(f"{prefix}_hub_{state}" for state in BOILER_STATES)
    return ids


def untouched(record):
    """No user choice is attached to this registry record."""
    return (record.name is None and record.icon is None and record.area_id is None
            and not record.labels and record.hidden_by is None
            and record.disabled_by in (None, _INTEGRATION))


def _reporting_fields(hass, entry):
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    client = getattr(state.get("v1_connection"), "client", None)
    cache = getattr(client, "boiler_fields", None)
    if cache is None:
        return frozenset()
    from .v1_boiler_fields import plausible
    return frozenset(index for index in cache.records if plausible(cache, index))


def stale_reason(record, prefix, legacy, reporting_ids, zones):
    """Why this record is no longer provided, or None when it still is (or may be)."""
    uid = record.unique_id
    if uid in legacy:
        return "legacy_hub"
    if uid.startswith(f"{prefix}_boiler_fields_v1_"):
        # "Never reported": disabled by us (as unreported, or by default as
        # unreliable), never marked as having delivered a real value since
        # 0.4.0b10, and no real value now. A disabled record records no state.
        from .v1_boiler_fields import REPORTED
        if (record.disabled_by is _INTEGRATION and uid not in reporting_ids
                and not record.options.get(DOMAIN, {}).get(REPORTED)):
            return "boiler_field_never_reported"
        return None
    match = re.fullmatch(re.escape(prefix) + r"_room_(.+)_climate", uid)
    if record.domain == "climate" and match and match.group(1) not in zones:
        return "room_without_zone"
    return None


def cleanup_stale_entities(hass, entry, prefix):
    """Remove untouched stale records; keep customised legacy ones disabled."""
    from .v1_boiler_fields import field_unique_id
    registry = er.async_get(hass)
    legacy = legacy_unique_ids(prefix)
    reporting_ids = {field_unique_id(prefix, index) for index in _reporting_fields(hass, entry)}
    zones = {subentry.data.get("room_id") for subentry in entry.subentries.values()
             if subentry.subentry_type == "zone"}
    removed = []
    for record in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if record.platform != DOMAIN:
            continue
        reason = stale_reason(record, prefix, legacy, reporting_ids, zones)
        if reason is None:
            continue
        if untouched(record):
            registry.async_remove(record.entity_id)
            removed.append(f"{record.entity_id} ({reason})")
        elif reason == "legacy_hub" and record.disabled_by is None:
            registry.async_update_entity(record.entity_id, disabled_by=_INTEGRATION)
    if removed:
        _LOGGER.info("Removed %d OpenThermostat entities this installation no longer provides: %s",
                     len(removed), ", ".join(sorted(removed)))
    return removed


# hass.data key: room ids whose device was removed during this setup.
REMOVED_ROOMS = "e32_removed_rooms"


def room_device_ids(hass, entry, prefix):
    """The ids of the E32 rooms that have a device of this entry."""
    from .heating_link import ROOM_ID
    head = f"{prefix}_e32_room_"
    ids = set()
    for device in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier.startswith(head) and ROOM_ID.fullmatch(identifier.removeprefix(head)):
                ids.add(identifier.removeprefix(head))
    return ids


def remove_room_devices(hass, entry, prefix, room_ids):
    """Remove this entry's device of each E32 room and this entry's entities on it.

    Only the device this config entry owns (a device belongs to one config
    entry); devices and entities of other entries and integrations, even with
    the same identifier, are never touched. Returns the room ids whose device
    was removed.
    """
    from .heating_link import room_device_identifier
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    removed = []
    for room_id in room_ids:
        device = devices.async_get_device_by_identifier(room_device_identifier(prefix, room_id), entry.entry_id)
        if device is None or device.config_entry_id != entry.entry_id:
            continue
        for record in er.async_entries_for_device(entities, device.id, include_disabled_entities=True):
            if record.config_entry_id == entry.entry_id and record.platform == DOMAIN:
                entities.async_remove(record.entity_id)
        devices.async_remove_device(device.id)
        removed.append(room_id)
    if state is not None:
        state.setdefault(REMOVED_ROOMS, set()).update(removed)
    if removed:
        _LOGGER.info("Removed the devices of %d E32 rooms that are no longer in the room plan: %s",
                     len(removed), ", ".join(sorted(removed)))
    return removed


def cleanup_removed_rooms(hass, entry, prefix, plan):
    """Remove the room devices of rooms a plan read from the E32 no longer has.

    plan is a decoded E32 room plan; None (not read yet, unreadable) removes
    nothing. A room removed during this setup that is back in the plan (the
    same name added again) reloads the entry, so its entities are created again.
    """
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None or type(plan) is not dict or type(plan.get("rooms")) is not list:
        return []
    planned = {room.get("id") for room in plan["rooms"] if type(room) is dict}
    removed = remove_room_devices(hass, entry, prefix, sorted(room_device_ids(hass, entry, prefix) - planned))
    returned = state.get(REMOVED_ROOMS, set()) & planned
    if returned and hass.config_entries.async_get_entry(entry.entry_id) is entry:
        state[REMOVED_ROOMS] -= returned
        _LOGGER.info("E32 rooms %s are back in the room plan; reloading to add their entities again",
                     ", ".join(sorted(returned)))
        hass.config_entries.async_schedule_reload(entry.entry_id)
    return removed
