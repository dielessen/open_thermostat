"""Remove registry identities a modern-mode E32 product entry no longer provides.

One route, one set of entities: the boiler-fields sensors are the boiler
entities. The legacy hub boiler/status identities are never fed by native
firmware. Boiler fields used to be created all at once and then disabled as
never (or only unreliably) reported; they now appear on their first real value,
so those disabled records only clutter the registry. An EMS+ field and its
Classic twin carry one physical value and share one entity (F28); a second
registry record of such a pair is removed as a duplicate, keeping the one the
user has (v1_boiler_fields.duplicate_unique_ids).

Only records of THIS config entry and platform are considered, and only while
untouched by the user (no name, icon, area, label, hidden or user-disabled
state). A customised legacy record is kept, disabled. Removing a registry
record never deletes Recorder history, and Home Assistant restores the same
entity_id if the integration provides that unique_id again.

Retired identities (RETIRED): records an older release created that this
version only provides on a condition the record itself shows, listed with the
version that changed them. Each is removed only while untouched and never
marked as having delivered a value (REPORTED). Entities that are still
provided but appear only once their data arrives (the shadow comparison, the
predicted heating start, the definition v2 counters) are never removed here.

Removing a record keeps the Recorder history and the long-term statistics of
its entity_id; the entity comes back under the same entity_id (and continues
those statistics) when the integration provides it again.

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
# Registry option (under DOMAIN): this record's entity delivered a real value once.
REPORTED = "reported"

# unique ID after f"{prefix}_" -> (version that retired it, reason in the log).
RETIRED = {
    # 0.4.0b10 (E32 beta.18): the hub outdoor temperature is the EMS+ outdoor
    # telegram (0xD1) and is created only on its first real value
    # (v1_metrics.VALUE_GATED). Older releases created it always; on a Classic
    # boiler it never reported and the boiler field "outdoor temperature" is the
    # one outdoor entity. A record that ever had a value stays.
    "hub_outdoor_temperature": ("0.4.0b10", "outdoor_temperature_without_value"),
    # 0.4.0b12: the "Legacy history: ..." counters. Since 0.4.0b2 the boiler
    # counters are the definition v2 sensors (<prefix>_hub_<metric>_v2); the old
    # identity was only re-added, always unavailable and without a state class,
    # to keep its history in view, and it kept a Repairs item open. Firmware
    # that still sends old-format values keeps it (a value now).
    **{f"hub_{metric}": ("0.4.0b12", "legacy_metric_history") for metric in (
        "energy", "energy_warm_water", "energy_heating", "energy_unattributed",
        "burner_observed_time", "warm_water_usage", "warm_water_avg_flow")},
}


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


def mark_reported(hass, unique_id, domain="sensor"):
    """Mark this entry's record as having delivered a real value (kept by RETIRED).
    False while the record does not exist yet (entities register asynchronously)."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return False
    options = registry.async_get(entity_id).options.get(DOMAIN, {})
    if not options.get(REPORTED):
        registry.async_update_entity_options(entity_id, DOMAIN, {**options, REPORTED: True})
    return True


def _metric_values(hass, entry):
    """The metrics payload the connection holds now (empty without one)."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    payload = getattr(getattr(state.get("v1_connection"), "client", None), "metrics_payload", None)
    return payload if type(payload) is dict else {}


def _has_value(payload, unique_id, prefix):
    from .metric_snapshot import finite
    from .sensor import HUB_METRICS
    metric = unique_id.removeprefix(f"{prefix}_hub_")
    field = HUB_METRICS["ems_metrics"].get(metric, (None,))[0]
    return field is not None and finite(payload.get(field))


def _reporting_fields(hass, entry):
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    client = getattr(state.get("v1_connection"), "client", None)
    cache = getattr(client, "boiler_fields", None)
    if cache is None:
        return frozenset()
    from .v1_boiler_fields import plausible
    return frozenset(index for index in cache.records if plausible(cache, index))


def stale_reason(record, prefix, legacy, reporting_ids, zones, metrics=None):
    """Why this record is no longer provided, or None when it still is (or may be)."""
    uid = record.unique_id
    if uid in legacy:
        return "legacy_hub"
    retired = RETIRED.get(uid.removeprefix(f"{prefix}_")) if uid.startswith(f"{prefix}_") else None
    if retired is not None:
        if record.options.get(DOMAIN, {}).get(REPORTED) or _has_value(metrics or {}, uid, prefix):
            return None
        return retired[1]
    if uid.startswith(f"{prefix}_boiler_fields_v1_"):
        # "Never reported": disabled by us (as unreported, or by default as
        # unreliable), never marked as having delivered a real value since
        # 0.4.0b10, and no real value now. A disabled record records no state.
        from .v1_boiler_fields import PLACEHOLDER, REPORTED as FIELD_REPORTED
        options = record.options.get(DOMAIN, {})
        # A disabled record of a value the boiler profile lists as not reported
        # (PLACEHOLDER, older releases) belongs to the boiler profile: apply_boiler_profile shows or removes it.
        if (record.disabled_by is _INTEGRATION and uid not in reporting_ids
                and not options.get(FIELD_REPORTED) and not options.get(PLACEHOLDER)):
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
    records = [record for record in er.async_entries_for_config_entry(registry, entry.entry_id)
               if record.platform == DOMAIN]
    metrics = _metric_values(hass, entry)
    reasons = {record.entity_id: stale_reason(record, prefix, legacy, reporting_ids, zones, metrics)
               for record in records}
    # F28: of an EMS+ / Classic pair that carries one physical value, only the
    # record that stays (the one the user has) is kept; the other is a duplicate.
    from .v1_boiler_fields import duplicate_unique_ids
    remaining = [record for record in records if reasons[record.entity_id] is None or not untouched(record)]
    duplicates = duplicate_unique_ids(remaining, prefix, reporting_ids)
    removed = []
    for record in records:
        reason = reasons[record.entity_id] or (
            "boiler_field_duplicate" if record.unique_id in duplicates else None)
        if reason is None:
            continue
        if untouched(record):
            registry.async_remove(record.entity_id)
            removed.append(f"{record.entity_id} ({reason})")
        elif reason == "legacy_hub" and record.disabled_by is None:
            registry.async_update_entity(record.entity_id, disabled_by=_INTEGRATION)
    if removed:
        _LOGGER.info("Removed %d OpenThermostat entities this installation no longer provides: %s. "
                     "Their history and long-term statistics are kept",
                     len(removed), ", ".join(sorted(removed)))
    # Repairs items about records that are gone now close as well.
    from .metrics_reports import reconcile_migration_issues
    reconcile_migration_issues(hass, entry, prefix)
    return removed


def cleanup_not_fitted(hass, entry, prefix, cache):
    """Remove untouched records of boiler values this boiler has no sensor for.

    The boiler profile (fw/config/boiler_profile) says which fields are not
    fitted; an EMS+ field and its Classic twin count as one value (F28), not
    fitted only when neither is supported. Only this entry's boiler-field
    sensors, and only while untouched (see untouched) and never marked as having
    delivered a real value (REPORTED); a kept record reads unavailable with
    availability_reason "not_fitted". Returns the removed unique IDs.
    """
    from .boiler_fields import INDEX_BY_NAME, concept
    from .v1_boiler_fields import REPORTED
    if cache is None or cache.field_profile is None:
        return frozenset()
    registry = er.async_get(hass)
    head = f"{prefix}_boiler_fields_v1_"
    removed = {}
    for record in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if record.domain != "sensor" or record.platform != DOMAIN or not record.unique_id.startswith(head):
            continue
        index = INDEX_BY_NAME.get(record.unique_id.removeprefix(head))
        if index is None or cache.concept_state(concept(index)) != "not_fitted":
            continue
        if untouched(record) and not record.options.get(DOMAIN, {}).get(REPORTED):
            registry.async_remove(record.entity_id)
            removed[record.unique_id] = record.entity_id
    if removed:
        _LOGGER.info("Removed %d OpenThermostat boiler entities this boiler has no sensor for: %s",
                     len(removed), ", ".join(sorted(removed.values())))
    return frozenset(removed)


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
    same name added again) gets its entities again from the heating hub's
    trackers (heating_link.track_entities), without reloading the entry.
    """
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None or type(plan) is not dict or type(plan.get("rooms")) is not list:
        return []
    planned = {room.get("id") for room in plan["rooms"] if type(room) is dict}
    removed = remove_room_devices(hass, entry, prefix, sorted(room_device_ids(hass, entry, prefix) - planned))
    returned = state.get(REMOVED_ROOMS, set()) & planned
    if returned:
        state[REMOVED_ROOMS] -= returned
        hub = state.get("heating_hub")
        if hub is not None:
            _LOGGER.info("E32 rooms %s are back in the room plan; adding their entities again",
                         ", ".join(sorted(returned)))
            hub.forget_removed_rooms(returned)
    return removed
