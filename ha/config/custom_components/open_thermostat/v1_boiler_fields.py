"""Read-only entities over the existing runtime listener, with no new MQTT IO."""
import json
from pathlib import Path

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from .boiler_fields import CATALOG_BASE, CATALOG_COUNTERS, INDEX_BY_NAME, INDEXES, concept, quality, spec
from .const import DOMAIN, CONF_TOPIC_PREFIX

# Registry option (under our domain) set once a field delivered a real value.
REPORTED = "reported"


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
        if not options.get(REPORTED):
            registry.async_update_entity_options(entity_id, DOMAIN, {**options, REPORTED: True})
        reporting = [m for m in concept(index) if cache is not None and plausible(cache, m)]
        reliable = any(quality(m) != 1 for m in reporting) if reporting else quality(index) != 1
        if reliable and record.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(entity_id, disabled_by=None)
    return pending


async def async_setup_boiler_fields(hass, entry, async_add_entities):
    state = hass.data[DOMAIN][entry.entry_id]
    runtime = state["v1_runtime"]
    connection = state.get("v1_connection")
    if not runtime.enabled or connection is None or connection.client is None:
        return
    client = connection.client
    prefix = entry.data[CONF_TOPIC_PREFIX]
    translated = await hass.async_add_executor_job(translated_fields)
    entities = []
    last_key = None
    unconfirmed = set()
    def refresh():
        nonlocal last_key, unconfirmed
        # A field (Classic or catalog) gets its entity only after its first real
        # value, like the BLE sensors: a boiler never shows rows it does not report.
        # Once created, an entity stays for this run even if a new session resets the cache.
        # One entity per physical value (F28): an EMS+ field and its Classic twin
        # share it, under the unique ID the registry already has.
        known = {member for entity in entities for member in entity.members}
        cache = client.boiler_fields
        new = []
        registry = None
        for index in INDEXES if client.boiler_fields_supported else ():
            if index in known:
                continue
            members = concept(index)
            known.update(members)
            reporting = {member for member in members if plausible(cache, member)}
            if reporting:
                registry = registry or er.async_get(hass)
                new.append(BoilerFieldEntity(prefix, client, holder(registry, prefix, members, reporting),
                                             translated))
        if new:
            entities.extend(new)
            unconfirmed |= {entity.index for entity in new}
            from .product import is_product
            if is_product(entry):
                from .installation_group import ensure_installation_group
                async_add_entities(new, config_subentry_id=ensure_installation_group(hass,entry))
            else:
                async_add_entities(new)
        elif unconfirmed:
            unconfirmed = confirm_reported(hass, prefix, unconfirmed, cache)
        key = (client.boiler_fields.sequence, client.boiler_fields.invalid, client.ready,
               tuple(entity.available for entity in entities))
        if key == last_key:
            return
        last_key = key
        for entity in entities:
            if entity.hass is not None:
                entity.async_write_ha_state()
    entry.async_on_unload(runtime.add_listener(refresh))
    refresh()


class BoilerFieldEntity(SensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, prefix, client, index, translated=None):
        # index: the field whose unique ID (so entity ID and history) this entity
        # keeps; members: every field that carries the same physical value.
        self.client, self.index = client, index
        self.members = concept(index)
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

    @property
    def source(self):
        """(field index, reading) the value comes from: the freshest usable member,
        else this entity's own field, whose reading explains why there is no value."""
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
        value = self.reading
        return bool(self.client.ready and self.client.boiler_fields_supported
                    and value and value["usable"])

    @property
    def native_value(self):
        if not self.available:
            return None
        index, value = self.source
        raw = value["raw"]
        name, unit, divisor, _ = spec(index)
        if unit == "text":
            return chr(raw >> 8) + chr(raw & 255)
        return raw / divisor

    @property
    def extra_state_attributes(self):
        index, value = self.source
        name, _, divisor, ttl = spec(index)
        reason = ("session_unavailable" if not self.client.ready else
                  "capability_unavailable" if not self.client.boiler_fields_supported else
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
                **({"source_protocol":"ems_classic" if index < CATALOG_BASE else "ems_plus",
                    "source_fields":[spec(member)[0] for member in self.members]}
                   if len(self.members) > 1 else {})}
