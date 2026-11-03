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
marked as having delivered a value (REPORTED), and never at setup: only once
the E32's metrics have arrived for RETIRED_GRACE_S without a value for it
(note_metrics). A record from before the REPORTED mark existed whose value
still comes is thus marked and kept, never removed. Entities that are still
provided but appear only once their data arrives (the predicted heating start,
the definition v2 counters) are never removed here.

The shadow comparison (heating_link.SHADOW_SENSORS) compares the E32 with a
thermostat on the boiler bus, which only means something in the trial run
(shadow mode) while such a thermostat is heard. Once the E32 controls the
boiler (mode active) and reports no thermostat to compare with, its records
go, like the RETIRED ones: only this entry's, only while untouched, and never
at setup, only once that status has lasted RETIRED_GRACE_S
(note_heating_status). A customised record is kept. Back in the trial run
with a thermostat on the bus, heating_link.wanted_sensors creates them again.

Removing a record keeps the Recorder history and the long-term statistics of
its entity_id; the entity comes back under the same entity_id (and continues
those statistics) when the integration provides it again.

E32 rooms: a room that is no longer in the E32 room plan (removed in the HA
room editor or on the E32's own page) loses its room device and that device's
entities, but only once a plan has actually been read from the E32 (never on
a missing or unreadable plan) and only this entry's own devices. A plan
without rooms never removes anything (the E32 serves one when its stored plan
is unreadable, R4-01), and a room goes only once two successful plan reads at
least ABSENT_CONFIRM_SECONDS apart both miss it (cleanup_removed_rooms).
"""
import logging
import re
import time

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
_INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
# Registry option (under DOMAIN): this record's entity delivered a real value once.
REPORTED = "reported"

# How long the metrics must have arrived without a value before a RETIRED record goes.
RETIRED_GRACE_S = 600
_clock = time.monotonic
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


# 0.4.0b13 made the E32 memory kB and its uptime hours. For existing records Home
# Assistant pinned the old display unit in "sensor.private" (to keep showing B and
# s), so the change never showed. Released once: only this exact old pin, never a
# unit the user chose ("sensor" options); Home Assistant then derives the display
# unit again from the entity (kB, h). Statistics stay valid: same unit class, the
# recorder converts to the unit they were compiled in.
PINNED_UNITS = {"hub_memory_free": "B", "hub_memory_min_free": "B", "hub_memory_max_alloc": "B",
                "hub_uptime": "s"}


def release_pinned_units(hass, entry, prefix):
    """Release this entry's old B/s display-unit pins (PINNED_UNITS); returns the entity IDs."""
    registry = er.async_get(hass)
    released = []
    for record in er.async_entries_for_config_entry(registry, entry.entry_id):
        if record.domain != "sensor" or record.platform != DOMAIN or not record.unique_id.startswith(f"{prefix}_"):
            continue
        old = PINNED_UNITS.get(record.unique_id.removeprefix(f"{prefix}_"))
        if old is None or (record.options.get("sensor") or {}).get("unit_of_measurement"):
            continue  # not ours, or the user's own unit
        if record.options.get("sensor.private") != {"suggested_unit_of_measurement": old}:
            continue
        registry.async_update_entity_options(record.entity_id, "sensor.private",
                                             {"refresh_initial_entity_options": True})
        released.append(record.entity_id)
    if released:
        _LOGGER.info("Memory in kB and uptime in hours for %s (the old B/s display unit was pinned)",
                     ", ".join(sorted(released)))
    return released


# Values only some boilers, or only an attended trial, ever have (beta.23): the
# definition v2 counters (EMS+; a Classic boiler never fills them) and the boiler
# test's last requested flow. Instead of an "unknown" row for good: a new record
# starts disabled until its first value; an untouched existing record that never
# had a value is disabled and hidden once its source has been heard for
# VALUE_GRACE_S (NEVER_REPORTED); the first real value marks it REPORTED and undoes
# exactly what this integration did. A user's own disable, hide or name is kept.
# Universal: what a boiler does not send decides, never a list of models.
NEVER_REPORTED = "hidden_never_reported"
VALUE_GRACE_S = RETIRED_GRACE_S
_HIDDEN = er.RegistryEntryHider.INTEGRATION


def value_gated_enabled_default(hass, unique_id, has_value, domain="sensor"):
    """Enabled by default for a new value-gated entity: with a value now, or when its record exists."""
    return bool(has_value) or er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id) is not None


def note_value(hass, unique_id, domain="sensor"):
    """A real value for this value-gated record: REPORTED, and undo this integration's disable/hide."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    if entity_id is None:
        return False
    record = registry.async_get(entity_id)
    options = record.options.get(DOMAIN, {})
    changes = {}
    if record.disabled_by is _INTEGRATION:
        changes["disabled_by"] = None  # Home Assistant reloads the entry to add it
    if record.hidden_by is _HIDDEN and options.get(NEVER_REPORTED):
        changes["hidden_by"] = None
    if changes:
        registry.async_update_entity(entity_id, **changes)
        _LOGGER.info("%s reports a value: shown again", entity_id)
    new = {k: v for k, v in options.items() if k != NEVER_REPORTED}
    new[REPORTED] = True
    if new != options:
        registry.async_update_entity_options(entity_id, DOMAIN, new)
    return True


def hide_never_reported(hass, entry, unique_ids, domain="sensor"):
    """Disable and hide this entry's untouched records of these IDs that never had a value."""
    registry = er.async_get(hass)
    hidden = []
    for unique_id in unique_ids:
        entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
        record = registry.async_get(entity_id) if entity_id else None
        if record is None or record.config_entry_id != entry.entry_id or not untouched(record):
            continue
        options = record.options.get(DOMAIN, {})
        if options.get(REPORTED) or options.get(NEVER_REPORTED):
            continue
        registry.async_update_entity(entity_id, disabled_by=_INTEGRATION, hidden_by=_HIDDEN)
        registry.async_update_entity_options(entity_id, DOMAIN, {**options, NEVER_REPORTED: True})
        hidden.append(entity_id)
    if hidden:
        _LOGGER.info("Disabled and hid %d OpenThermostat entities that never had a value on this "
                     "installation (they come back by themselves on a first value): %s",
                     len(hidden), ", ".join(sorted(hidden)))
    return hidden


def value_gate_due(hass, entry, key):
    """True once per setup, VALUE_GRACE_S after the first call for this key (its source heard)."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None:
        return False
    watch = state.setdefault("value_gate_watch", {}).setdefault(key, {"since": _clock(), "done": False})
    if watch["done"] or _clock() - watch["since"] < VALUE_GRACE_S:
        return False
    watch["done"] = True
    return True


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


def _has_value(payload, unique_id, prefix):
    from .metric_snapshot import finite
    from .sensor import HUB_METRICS
    metric = unique_id.removeprefix(f"{prefix}_hub_")
    field = HUB_METRICS["ems_metrics"].get(metric, (None,))[0]
    return field is not None and finite(payload.get(field))


def retired_reason(record, prefix, metrics=None):
    """The RETIRED reason of this record, or None when it is not retired or still has a value.

    metrics None: only whether the identity is retired at all."""
    uid = record.unique_id
    retired = RETIRED.get(uid.removeprefix(f"{prefix}_")) if uid.startswith(f"{prefix}_") else None
    if retired is None:
        return None
    if metrics is not None and (record.options.get(DOMAIN, {}).get(REPORTED) or _has_value(metrics, uid, prefix)):
        return None
    return retired[1]


def note_metrics(hass, entry, prefix, payload):
    """Every new metrics snapshot (v1_metrics): once they have arrived for RETIRED_GRACE_S,
    remove the untouched RETIRED records that still have no value (once per setup)."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None or type(payload) is not dict:
        return
    watch = state.setdefault("retired_watch", {"since": _clock(), "done": False})
    if watch["done"] or _clock() - watch["since"] < RETIRED_GRACE_S:
        return
    watch["done"] = True
    cleanup_retired(hass, entry, prefix, payload)


def cleanup_retired(hass, entry, prefix, payload):
    """Remove this entry's untouched RETIRED records without a value now or ever (REPORTED)."""
    registry = er.async_get(hass)
    removed = []
    for record in er.async_entries_for_config_entry(registry, entry.entry_id):
        if record.platform != DOMAIN or not untouched(record):
            continue
        if (reason := retired_reason(record, prefix, payload)) is not None:
            registry.async_remove(record.entity_id)
            removed.append(f"{record.entity_id} ({reason})")
    if removed:
        _LOGGER.info("Removed %d OpenThermostat entities this version no longer provides: %s. "
                     "Their history and long-term statistics are kept", len(removed), ", ".join(sorted(removed)))
    from .metrics_reports import reconcile_migration_issues
    reconcile_migration_issues(hass, entry, prefix)
    return removed


def comparison_unique_ids(prefix):
    """The unique IDs of the shadow comparison sensors (heating_link.ShadowSensor)."""
    from .heating_link import SHADOW_SENSORS
    return {f"{prefix}_hub_shadow_{key}" for key in SHADOW_SENSORS}


def comparison_over(status):
    """The E32 controls the boiler (mode active) and reports no thermostat to compare with."""
    from .heating_link import shadow_has_thermostat
    return type(status) is dict and status.get("mode") == "active" and not shadow_has_thermostat(status)


def note_heating_status(hass, entry, prefix, status):
    """Every heating status (heating_link): once comparison_over has held for RETIRED_GRACE_S,
    remove the untouched comparison records (once per such stretch; a new stretch starts over)."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None:
        return
    if not comparison_over(status):
        state.pop("comparison_watch", None)
        return
    watch = state.setdefault("comparison_watch", {"since": _clock(), "done": False})
    if watch["done"] or _clock() - watch["since"] < RETIRED_GRACE_S:
        return
    watch["done"] = True
    cleanup_comparison(hass, entry, prefix)


def cleanup_comparison(hass, entry, prefix):
    """Remove this entry's untouched shadow comparison records; returns their entity IDs."""
    registry = er.async_get(hass)
    ids = comparison_unique_ids(prefix)
    removed = []
    for record in er.async_entries_for_config_entry(registry, entry.entry_id):
        if record.platform == DOMAIN and record.unique_id in ids and untouched(record):
            registry.async_remove(record.entity_id)
            removed.append(record.entity_id)
    if removed:
        _LOGGER.info("Removed %d OpenThermostat comparison entities (the E32 controls the boiler and hears no "
                     "thermostat to compare with): %s. Their history and long-term statistics are kept; they "
                     "come back in a trial run with a thermostat on the bus", len(removed), ", ".join(sorted(removed)))
    return removed


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
    if retired_reason(record, prefix) is not None:
        return None  # decided later, once the metrics have been seen (note_metrics)
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
    reasons = {record.entity_id: stale_reason(record, prefix, legacy, reporting_ids, zones)
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


# hass.data key: {room id: clock time of the plan read that first missed it} for rooms that still
# have a device of this entry while the latest successful plan reads did not list them.
ABSENT_ROOMS = "e32_absent_rooms"
# A room leaves Home Assistant only once two successful plan reads at least this far apart miss it.
ABSENT_CONFIRM_SECONDS = 60


def absent_rooms(hass, entry):
    """{room id: clock time first missed} of the rooms that wait for a confirming plan read."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id) if entry is not None else None
    return dict(state.get(ABSENT_ROOMS) or {}) if isinstance(state, dict) else {}


def cleanup_removed_rooms(hass, entry, prefix, plan, now=None):
    """Remove the room devices of rooms the E32 room plan no longer has; returns their room ids.

    plan is a decoded E32 room plan, just read from (or confirmed by) the E32;
    None (not read yet, unreadable) removes nothing. A plan without rooms never
    removes anything either: the E32 serves exactly that when its stored plan
    cannot be read (and after a factory reset), so it proves nothing. Removing
    a room in Configure (e32_room_flow) removes its device at once, also the
    last room's.

    Otherwise a room goes only when two consecutive successful plan reads at
    least ABSENT_CONFIRM_SECONDS apart both miss it (now: the clock time of this
    read, monotonic seconds); a read that lists it again keeps it. absent_rooms()
    says which rooms wait for that second read.

    A room removed during this setup that is back in the plan (the same name
    added again) gets its entities again from the heating hub's trackers
    (heating_link.track_entities), without reloading the entry.
    """
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None or type(plan) is not dict or type(plan.get("rooms")) is not list:
        return []
    now = _clock() if now is None else now
    planned = {room.get("id") for room in plan["rooms"] if type(room) is dict}
    absent = state.setdefault(ABSENT_ROOMS, {})
    if not planned:
        absent.clear()  # no proof either way: the next plan with rooms starts counting again
        kept = room_device_ids(hass, entry, prefix)
        if kept:
            _LOGGER.info("The E32 room plan (revision %s) lists no rooms; the devices of %s stay "
                         "(a plan without rooms never removes any)", plan.get("revision"), ", ".join(sorted(kept)))
        return []
    missing = room_device_ids(hass, entry, prefix) - planned
    for room_id in [r for r in absent if r not in missing]:
        del absent[room_id]  # listed again, or its device is gone already
    due = sorted(r for r in missing if r in absent and now - absent[r] >= ABSENT_CONFIRM_SECONDS)
    first = sorted(r for r in missing if r not in absent)
    for room_id in first:
        absent[room_id] = now
    if first:
        _LOGGER.info("The E32 room plan no longer lists %s; their devices stay until a plan read at least "
                     "%d s later confirms it", ", ".join(first), ABSENT_CONFIRM_SECONDS)
    removed = remove_room_devices(hass, entry, prefix, due)
    for room_id in due:
        absent.pop(room_id, None)
    returned = state.get(REMOVED_ROOMS, set()) & planned
    if returned:
        state[REMOVED_ROOMS] -= returned
        hub = state.get("heating_hub")
        if hub is not None:
            _LOGGER.info("E32 rooms %s are back in the room plan; adding their entities again",
                         ", ".join(sorted(returned)))
            hub.forget_removed_rooms(returned)
    return removed
