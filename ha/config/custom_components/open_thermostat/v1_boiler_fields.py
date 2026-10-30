"""Read-only boiler value entities: the runtime link's cache, or the retained E32 state without it."""
import json
import logging
from pathlib import Path

from datetime import timedelta

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_time_interval
from .boiler_fields import (BoilerFieldCache, CATALOG_BASE, CATALOG_COUNTERS, INDEX_BY_NAME, INDEXES, concept,
                            quality, spec)
from .const import DOMAIN, CONF_TOPIC_PREFIX

_LOGGER = logging.getLogger(__name__)

# Registry option (under our domain) set once a field delivered a real value.
REPORTED = "reported"
# Registry option of a record made, disabled, for a value this boiler's profile
# lists as not reported (yet): kept by the setup cleanup, removed once not fitted.
# Releases before 0.4.0b12 made these; apply_boiler_profile now removes them.
PLACEHOLDER = "not_reported_placeholder"
# Registry option: disabled and hidden by apply_boiler_profile (this boiler lacks
# the value); the record comes back by itself once the profile says supported.
PROFILE_HIDDEN = "hidden_by_boiler_profile"
_INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
_HIDDEN = er.RegistryEntryHider.INTEGRATION


def boiler_cache(hass, entry_id):
    """The boiler-field cache of a config entry, or None."""
    state = hass.data.get(DOMAIN, {}).get(entry_id, {})
    if not isinstance(state, dict):
        return None
    client = getattr(state.get("v1_connection"), "client", None) or state.get(SOURCE_KEY)
    return getattr(client, "boiler_fields", None)


# hass.data[DOMAIN][entry_id] key of the RetainedBoilerSource (no runtime link).
SOURCE_KEY = "boiler_source"
STALE_CHECK = timedelta(seconds=15)


def boiler_values_live(client):
    """Whether this client's boiler readings may be shown at all.

    E32 beta.19 keeps the boiler values retained (fw/state/boiler_fields/<g>,
    fw/state/boiler): they need no shadow session, only a live E32 (heartbeat
    and availability), which BoilerFieldCache.reading() checks per value. The
    older session telemetry (fw/telemetry/boiler_fields) keeps its rule: a
    ready session that announced boiler.fields.
    """
    cache = getattr(client, "boiler_fields", None)
    if cache is None:
        return False
    if cache.state_mode:
        return True
    return bool(getattr(client, "ready", False) and getattr(client, "boiler_fields_supported", False))


class RetainedBoilerSource:
    """The retained boiler values of an E32 (beta.19) while the entry runs no shadow link.

    The same cache and entities as the link's ShadowClient, fed from the same
    retained topics (v1_wire.apply_boiler_state), so a stopped or never started
    link (shadow off, an unfinished Connect E32) never hides the boiler values.
    Read-only: it never sends anything and has no session.
    """
    ready = False
    boiler_fields_v2 = False

    def __init__(self, clock):
        self.clock = clock
        self.boiler_fields = BoilerFieldCache()
        self._listeners = []

    @property
    def boiler_fields_supported(self):
        return self.boiler_fields.state_mode

    def add_listener(self, listener):
        self._listeners.append(listener)

        def remove():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return remove

    def receive(self, topic, raw, retained=False):
        """One message, topic after the prefix (fw/...)."""
        from .v1_wire import apply_boiler_state
        if topic == "fw/availability":
            if raw not in ("online", "offline"):
                return
            self.boiler_fields.availability(raw == "online", self.clock())
            changed = True
        else:
            changed, _ = apply_boiler_state(self.boiler_fields, topic, raw, retained, self.clock())
        if changed:
            for listener in list(self._listeners):
                try:
                    listener()
                except Exception:  # noqa: BLE001 - one failing listener never stops the others
                    _LOGGER.exception("OpenThermostat: a boiler value listener failed")


async def _async_retained_source(hass, entry, state):
    """A RetainedBoilerSource subscribed to the entry's E32 topics (product entries only)."""
    from homeassistant.components import mqtt
    from .heating_link import topic_base
    base = topic_base(hass, entry)
    source = state[SOURCE_KEY] = RetainedBoilerSource(hass.loop.time)

    @callback
    def received(message):
        topic = getattr(message, "topic", "")
        if type(topic) is str and topic.startswith(base):
            source.receive(topic[len(base):], message.payload, retained=getattr(message, "retain", False))

    await mqtt.async_wait_for_mqtt_client(hass)
    for suffix in ("fw/state/boiler_fields/+", "fw/state/boiler", "fw/config/boiler_profile", "fw/heartbeat",
                   "fw/availability"):
        entry.async_on_unload(await mqtt.async_subscribe(hass, base + suffix, received))
    entry.async_on_unload(lambda: state.pop(SOURCE_KEY, None))
    return source


def boiler_field_shown(hass, entry_id, name):
    """Dashboards: whether a tile for boiler field ``name`` (a field id) belongs on them.

    True without a boiler profile (older firmware, or before the retained profile
    arrived: every tile as before); with one only when this boiler has the value
    (supported, an EMS+ field and its Classic twin together). Regenerate when
    ``boiler_cache(...).profile_sequence`` changes.
    """
    index = INDEX_BY_NAME.get(name)
    cache = boiler_cache(hass, entry_id)
    if index is None or cache is None:
        return True
    state = cache.concept_state(concept(index))
    return state is None or state == "supported"


def field_unique_id(prefix, index):
    return f"{prefix}_boiler_fields_v1_{spec(index)[0]}"


def translation_key(name):
    """Every boiler field (Classic or catalog) is named by translation key field_<field id>."""
    return "field_" + name


def translated_fields():
    """The field ids strings.json names (read once per setup, in the executor)."""
    try:
        sensor = json.loads(Path(__file__).with_name("strings.json").read_text(encoding="utf-8"))["entity"]["sensor"]
    except (OSError, ValueError, KeyError):
        return frozenset()
    return frozenset(key.removeprefix("field_") for key in sensor if key.startswith("field_"))


def plausible(cache, index):
    """A real value: acquired and valid. An unreliable field's zero is no evidence:
    adapters such as EasyControl fill unsupported counter/bit bytes with 00."""
    record = cache.records.get(index)
    if record is None:
        return False
    _, raw, observed, field_quality, _ = record[0]
    return observed is not None and raw is not None and (field_quality != 1 or raw != 0)


def concept_name(index):
    """The field id that names the entity of index (F28: one name per physical value).

    An EMS+ field with a reported Classic twin carries the Classic name, so the
    one entity reads "Flow temperature", not "Flow temperature (EMS+)". A pair
    with a Classic raw bit is named by its own field.
    """
    classic = next((m for m in concept(index) if m < CATALOG_BASE), None)
    if classic is None or classic == index or spec(classic)[0].startswith("raw_"):
        return spec(index)[0]
    return spec(classic)[0]


def _rank(record, index, members, reporting):
    """Which registry record of one physical value keeps it: lowest first.

    The record the user sees (enabled), then one that delivered a value
    before, then one that reports now, then the concept's preference order.
    """
    options = record.options.get(DOMAIN, {})
    return (record.disabled_by is not None, not options.get(REPORTED), index not in reporting,
            members.index(index))


def holder(registry, prefix, members, reporting):
    """The field index whose unique ID the one entity of members uses.

    An existing registry record keeps its entity ID and history; without one,
    the first reporting member in preference order.
    """
    records = {}
    for index in members:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, field_unique_id(prefix, index))
        if entity_id is not None:
            records[index] = registry.async_get(entity_id)
    if records:
        return min(records, key=lambda index: _rank(records[index], index, members, reporting))
    return next((index for index in members if index in reporting), members[0])


def duplicate_unique_ids(records, prefix, reporting_ids=frozenset()):
    """Unique IDs of boiler field records that another record of the same physical value replaces.

    records: this entry's registry records (other domains and platforms are
    ignored); reporting_ids: unique IDs of fields with a real value now. Of
    each EMS+ / Classic pair with two records, the one holder() keeps is not
    listed, so the entity the user already has stays.
    """
    head = f"{prefix}_boiler_fields_v1_"
    found = {}
    for record in records:
        if record.domain == "sensor" and record.platform == DOMAIN and record.unique_id.startswith(head):
            index = INDEX_BY_NAME.get(record.unique_id.removeprefix(head))
            if index is not None:
                found[index] = record
    reporting = {index for index in found if field_unique_id(prefix, index) in reporting_ids}
    duplicates = set()
    for index in found:
        members = concept(index)
        present = [member for member in members if member in found]
        if len(present) > 1:
            keep = min(present, key=lambda member: _rank(found[member], member, members, reporting))
            duplicates.update(field_unique_id(prefix, member) for member in present if member != keep)
    return frozenset(duplicates)


def confirm_reported(hass, prefix, indexes, cache=None):
    """Mark the registry records of fields that delivered a real value.

    The mark tells the setup cleanup this field reported once, so a record that
    is disabled (by default, or by an older release) is never removed for it.
    A record we disabled earlier comes back, except unreliable fields: those
    stay disabled by default. The record of an EMS+ / Classic pair comes back
    when a reliable member reports now (cache). Returns the indexes whose record
    does not exist yet (the platform registers new entities asynchronously);
    retried later.
    """
    registry = er.async_get(hass)
    pending = set()
    for index in indexes:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, field_unique_id(prefix, index))
        if entity_id is None:
            pending.add(index)
            continue
        record = registry.async_get(entity_id)
        options = record.options.get(DOMAIN, {})
        if not options.get(REPORTED) or options.get(PLACEHOLDER):
            registry.async_update_entity_options(
                entity_id, DOMAIN, {**{k: v for k, v in options.items() if k != PLACEHOLDER}, REPORTED: True})
        reporting = [m for m in concept(index) if cache is not None and plausible(cache, m)]
        reliable = any(quality(m) != 1 for m in reporting) if reporting else quality(index) != 1
        if reliable and record.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(entity_id, disabled_by=None)
    return pending


def ours(record):
    """No user choice on this registry record: only this integration disabled or hid it."""
    return (record.name is None and record.icon is None and record.area_id is None and not record.labels
            and record.disabled_by in (None, _INTEGRATION) and record.hidden_by in (None, _HIDDEN))


def profile_hides(cache, members):
    """True when the boiler profile says this boiler lacks the value of members (F28 concept).

    Not fitted (a sentinel instead of a value), or not reported once the profile
    settled. The E32's "Show anyway" makes a not-fitted value supported. A value
    that is real now (plausible) is never hidden.
    """
    state = cache.concept_state(members)
    return ((state == "not_fitted" or state == "not_reported" and cache.profile_settled)
            and not any(plausible(cache, member) for member in members))


def apply_boiler_profile(hass, entry, prefix, cache):
    """This entry's boiler-field records follow the boiler profile (fw/config/boiler_profile).

    Universal for every EMS boiler: only what the profile says, never a list of
    this house. A value the boiler lacks (profile_hides) leaves no "unavailable"
    row behind: its record goes when it never delivered a value, else it is
    disabled and hidden (PROFILE_HIDDEN, keeping its history). A value that is
    supported again comes back: a record this integration disabled (hidden by
    the profile, an older placeholder, or any reliable value) is enabled and
    shown again. Records the user renamed, hid, disabled or placed are never
    changed. Without a profile (older firmware) nothing happens. Returns the
    unique IDs that are removed or hidden.
    """
    if cache is None or cache.field_profile is None:
        return frozenset()
    registry = er.async_get(hass)
    head = f"{prefix}_boiler_fields_v1_"
    gone, removed, hidden, shown = set(), [], [], []
    for record in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if record.domain != "sensor" or record.platform != DOMAIN or not record.unique_id.startswith(head):
            continue
        index = INDEX_BY_NAME.get(record.unique_id.removeprefix(head))
        if index is None or not ours(record):
            continue
        members = concept(index)
        options = record.options.get(DOMAIN, {})
        if cache.concept_state(members) == "supported":
            if options.get(PROFILE_HIDDEN) or options.get(PLACEHOLDER) or (
                    record.disabled_by is _INTEGRATION and quality(index) != 1):
                if record.disabled_by is not None or record.hidden_by is not None:
                    registry.async_update_entity(record.entity_id, disabled_by=None, hidden_by=None)
                    shown.append(record.entity_id)
                registry.async_update_entity_options(record.entity_id, DOMAIN, {
                    k: v for k, v in options.items() if k not in (PROFILE_HIDDEN, PLACEHOLDER)})
            continue
        if not profile_hides(cache, members):
            continue
        gone.add(record.unique_id)
        if not options.get(REPORTED):
            registry.async_remove(record.entity_id)
            removed.append(record.entity_id)
        elif record.disabled_by is None or record.hidden_by is None or not options.get(PROFILE_HIDDEN):
            registry.async_update_entity(record.entity_id, disabled_by=_INTEGRATION, hidden_by=_HIDDEN)
            registry.async_update_entity_options(record.entity_id, DOMAIN, {**options, PROFILE_HIDDEN: True})
            hidden.append(record.entity_id)
    if removed or hidden:
        _LOGGER.info("Boiler profile: removed %d and hid %d OpenThermostat boiler entities this boiler has "
                     "no sensor for or never reports: %s", len(removed), len(hidden),
                     ", ".join(sorted(removed + hidden)))
    if shown:
        _LOGGER.info("Boiler profile: %d OpenThermostat boiler entities are reported again and shown: %s",
                     len(shown), ", ".join(sorted(shown)))
    return frozenset(gone)


def mark_placeholders(hass, prefix, indexes):
    """Mark the new disabled records of not-reported values (PLACEHOLDER); the
    indexes whose record does not exist yet are returned, retried later."""
    registry = er.async_get(hass)
    pending = set()
    for index in indexes:
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, field_unique_id(prefix, index))
        if entity_id is None:
            pending.add(index)
            continue
        options = registry.async_get(entity_id).options.get(DOMAIN, {})
        if not options.get(REPORTED) and not options.get(PLACEHOLDER):
            registry.async_update_entity_options(entity_id, DOMAIN, {**options, PLACEHOLDER: True})
    return pending


async def async_setup_boiler_fields(hass, entry, async_add_entities):
    state = hass.data[DOMAIN][entry.entry_id]
    runtime = state["v1_runtime"]
    connection = state.get("v1_connection")
    if runtime.enabled and connection is not None and connection.client is not None:
        client, add_listener = connection.client, runtime.add_listener
    else:
        # No running link (shadow off, Connect E32 not finished): the retained
        # boiler values of E32 beta.19 still show (product entries with a connected E32).
        from .room_plan import has_room_plan
        if not has_room_plan(entry):
            return
        client = await _async_retained_source(hass, entry, state)
        add_listener = client.add_listener
    prefix = entry.data[CONF_TOPIC_PREFIX]
    translated = await hass.async_add_executor_job(translated_fields)
    entities = []
    last_profile = None
    unconfirmed = set()
    placeholders = set()
    # One evaluation per pass, shared by every entity of it (client.ready costs ~1 ms).
    shared = {"valid": False, "live": False}

    def refresh():
        nonlocal unconfirmed, placeholders, last_profile
        # A field (Classic or catalog) gets its entity only after its first real
        # value, like the BLE sensors: a boiler never shows rows it does not report.
        # Once created, an entity stays for this run even if a new session resets the cache.
        # One entity per physical value (F28): an EMS+ field and its Classic twin
        # share it, under the unique ID the registry already has.
        # The boiler profile (fw/config/boiler_profile) refines this: a value the
        # boiler has (supported) gets its entity at once and is shown again; one it
        # has no sensor for (not fitted) or never reports (not reported, once the
        # profile settled) never gets one, and its record goes or is hidden
        # (apply_boiler_profile). Unknown values wait for the profile or a real
        # value. Without a profile (older firmware) nothing changes.
        cache = client.boiler_fields
        if cache.field_profile is not None and cache.profile_sequence != last_profile:
            last_profile = cache.profile_sequence
            removed = apply_boiler_profile(hass, entry, prefix, cache)
            if removed:
                entities[:] = [entity for entity in entities if entity.unique_id not in removed]
        known = {member for entity in entities for member in entity.members}
        new = []
        registry = None
        for index in INDEXES if client.boiler_fields_supported else ():
            if index in known:
                continue
            members = concept(index)
            known.update(members)
            reporting = {member for member in members if plausible(cache, member)}
            state = cache.concept_state(members)
            placeholder = False
            if not reporting and state in ("not_fitted", "not_reported"):
                # Never a new entity; only a record the user customised stays and says why it has no value.
                registry = registry or er.async_get(hass)
                records = [registry.async_get(entity_id) for entity_id in (
                    registry.async_get_entity_id("sensor", DOMAIN, field_unique_id(prefix, member))
                    for member in members) if entity_id is not None]
                if not any(record is not None and not ours(record) for record in records):
                    continue
            elif not reporting and state != "supported":
                continue
            registry = registry or er.async_get(hass)
            preferred = reporting or {member for member in members if cache.field_state(member) == "supported"}
            entity = BoilerFieldEntity(prefix, client, holder(registry, prefix, members, preferred), translated,
                                       placeholder=placeholder, shared=shared)
            entity.confirmed = bool(reporting) or state == "supported"
            new.append(entity)
        for entity in entities:
            # A placeholder (or a kept not-fitted record) whose value arrived after all.
            if not entity.confirmed and any(plausible(cache, member) for member in entity.members):
                entity.confirmed = True
                unconfirmed.add(entity.index)
        if new:
            entities.extend(new)
            unconfirmed |= {entity.index for entity in new if entity.confirmed}
            placeholders |= {entity.index for entity in new if entity.placeholder}
            from .product import is_product
            if is_product(entry):
                from .installation_group import ensure_installation_group
                async_add_entities(new, config_subentry_id=ensure_installation_group(hass,entry))
            else:
                async_add_entities(new)
        else:
            if unconfirmed:
                unconfirmed = confirm_reported(hass, prefix, unconfirmed, cache)
            if placeholders:
                placeholders = mark_placeholders(hass, prefix, placeholders)
        # Only entities that are in Home Assistant now (never a disabled or removed
        # one) and whose state really changed are written: (available, value, reason).
        shared.update(valid=True, live=boiler_values_live(client))
        try:
            for entity in entities:
                entity.evaluate()
                if not entity.added:
                    continue
                signature = entity.signature()
                if signature != entity.written:
                    entity.written = signature
                    entity.async_write_ha_state()
        finally:
            shared["valid"] = False
            for entity in entities:
                entity.evaluate()

    @callback
    def check_stale(_now=None):
        # Retained values stay usable while the E32 is alive: three missed
        # heartbeats (or offline) make them unavailable without a new message.
        refresh()
    entry.async_on_unload(add_listener(refresh))
    entry.async_on_unload(async_track_time_interval(hass, check_stale, STALE_CHECK))
    refresh()


class BoilerFieldEntity(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    # Diagnostics that change with every sample: shown, not recorded with each state.
    _unrecorded_attributes = frozenset({"source_observed_at_ms", "age_basis", "raw_divisor", "source_ttl_ms",
                                        "protocol_profile", "source_fields"})

    def __init__(self, prefix, client, index, translated=None, placeholder=False, shared=None):
        # shared: the setup's per-pass evaluation (whether the values may show at all).
        self._shared = shared
        self._source = None  # this pass's source, while shared["valid"]
        # In Home Assistant now (added, not yet removed or disabled), and the last written state.
        self.added = False
        self.written = None
        # index: the field whose unique ID (so entity ID and history) this entity
        # keeps; members: every field that carries the same physical value.
        self.client, self.index = client, index
        self.members = concept(index)
        # placeholder: made, disabled, for a value the boiler profile lists as not
        # reported; confirmed: its REPORTED mark is (being) set.
        self.placeholder, self.confirmed = placeholder, not placeholder
        name, unit, _, _ = spec(index)
        self._attr_unique_id = field_unique_id(prefix, index)
        # Named in English and Dutch by translation key; the unique ID (and so the
        # entity ID) is unchanged. A field newer than the translations it ships
        # with keeps an English name made from its id.
        shown = concept_name(index)
        self._attr_translation_key = translation_key(shown)
        if translated is not None and shown not in translated:
            self._attr_name = ("Boiler " + shown.replace("_", " ") if INDEX_BY_NAME[shown] < CATALOG_BASE
                               else shown.replace("_", " ").capitalize())
        if quality(index) == 1:
            self._attr_entity_registry_enabled_default = False
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if placeholder:
            self._attr_entity_registry_enabled_default = False
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN,prefix)})
        self._attr_native_unit_of_measurement = {"degC":"°C", "uA":"µA"}.get(unit,unit)
        if unit in ("bool", "bits", "text", "code", "starts"):
            self._attr_native_unit_of_measurement = None
        if unit == "degC":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        # Table counters (EMS u24) keep statistics; the unqualified v1 OEM
        # counters and settings do not. No new energy identity.
        if name in CATALOG_COUNTERS:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            if unit == "min":
                self._attr_device_class = SensorDeviceClass.DURATION

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.added, self.written = True, None

    async def async_will_remove_from_hass(self):
        # Also when the user or the boiler profile disables it: no writes from now on.
        self.added = False
        await super().async_will_remove_from_hass()

    def evaluate(self):
        """Forget this pass's cached source (the setup's refresh calls it per pass)."""
        self._source = None

    def _live(self):
        shared = self._shared
        return shared["live"] if shared is not None and shared["valid"] else boiler_values_live(self.client)

    def signature(self):
        """What a state write would change: availability, value and why there is none."""
        available = self.available
        value = self.native_value if available else None
        _, reading = self.source
        return available, value, reading["availability_reason"] if reading else None

    @property
    def source(self):
        """(field index, reading) the value comes from: the freshest usable member,
        else this entity's own field, whose reading explains why there is no value."""
        shared = self._shared
        if self._source is not None and shared is not None and shared["valid"]:
            return self._source
        self._source = self._find_source()
        return self._source

    def _find_source(self):
        cache, now = self.client.boiler_fields, self.client.clock()
        readings = [(index, cache.reading(index, now)) for index in self.members]
        usable = [(index, value) for index, value in readings if value and value["usable"]]
        if usable:
            return max(usable, key=lambda item: item[1]["observed_at_ms"])  # ties: preference order
        own = dict(readings).get(self.index)
        if own is not None:
            return self.index, own
        return next(((index, value) for index, value in readings if value), (self.index, None))

    @property
    def reading(self):
        return self.source[1]

    @property
    def available(self):
        cache = self.client.boiler_fields
        if cache.state_mode:
            # Retained state (E32 beta.19): unavailable only while the E32 itself is
            # offline or silent; a value it has none of now reads unknown.
            return cache.alive(self.client.clock())
        value = self.reading
        return bool(self._live() and value and value["usable"])

    @property
    def native_value(self):
        if not self.available:
            return None
        index, value = self.source
        if not value or not value["usable"]:
            return None
        raw = value["raw"]
        name, unit, divisor, _ = spec(index)
        if unit == "text":
            return chr(raw >> 8) + chr(raw & 255)
        return raw / divisor

    @property
    def extra_state_attributes(self):
        index, value = self.source
        name, _, divisor, ttl = spec(index)
        profile = self.client.boiler_fields.concept_state(self.members)
        live = self._live()
        reason = ("session_unavailable" if not live and not self.client.ready else
                  "capability_unavailable" if not live else
                  "not_fitted" if profile == "not_fitted" and not (value and value["usable"]) else
                  value["availability_reason"] if value else "not_received")
        return {"data_role":"read_only_boiler_field", "control_qualified":False,
                "field_name":name, "raw_divisor":divisor, "source_ttl_ms":ttl,
                "measurement_state":value["measurement_state"] if value else "unknown",
                "availability_reason":reason,
                "age_basis":"firmware_snapshot_plus_local_elapsed; network transit unmeasured",
                "quality":({0:"reported",1:"unreliable",2:"inferred"}.get(value["quality"]) if value else "unknown"),
                "source_type":value["source_type"] if value else None,
                "source_observed_at_ms":value["observed_at_ms"] if value else None,
                "protocol_profile":self.client.boiler_fields.profile,
                **({"boiler_profile":profile} if profile is not None else {}),
                **({"source_protocol":"ems_classic" if index < CATALOG_BASE else "ems_plus",
                    "source_fields":[spec(member)[0] for member in self.members]}
                   if len(self.members) > 1 else {})}
