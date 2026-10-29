"""Read-only entities over the existing runtime listener, with no new MQTT IO."""
import json
from pathlib import Path

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from .boiler_fields import CATALOG_BASE, CATALOG_COUNTERS, INDEXES, quality, spec
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


def confirm_reported(hass, prefix, indexes):
    """Mark the registry records of fields that delivered a real value.

    The mark tells the setup cleanup this field reported once, so a record that
    is disabled (by default, or by an older release) is never removed for it.
    A record we disabled earlier comes back, except unreliable fields: those
    stay disabled by default. Returns the indexes whose record does not exist
    yet (the platform registers new entities asynchronously); retried later.
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
        if quality(index) != 1 and record.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
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
        known = {entity.index for entity in entities}
        cache = client.boiler_fields
        new = ([BoilerFieldEntity(prefix, client, index, translated) for index in INDEXES
                if index not in known and plausible(cache, index)]
               if client.boiler_fields_supported else [])
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
            unconfirmed = confirm_reported(hass, prefix, unconfirmed)
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
        self.client, self.index = client, index
        name, unit, _, _ = spec(index)
        self._attr_unique_id = field_unique_id(prefix, index)
        # Named in English and Dutch by translation key; the unique ID (and so the
        # entity ID) is unchanged. A field newer than the translations it ships
        # with keeps an English name made from its id.
        self._attr_translation_key = translation_key(name)
        if translated is not None and name not in translated:
            self._attr_name = ("Boiler " + name.replace("_", " ") if index < CATALOG_BASE
                               else name.replace("_", " ").capitalize())
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
    def reading(self):
        return self.client.boiler_fields.reading(self.index,self.client.clock())

    @property
    def available(self):
        value = self.reading
        return bool(self.client.ready and self.client.boiler_fields_supported
                    and value and value["usable"])

    @property
    def native_value(self):
        if not self.available:
            return None
        raw = self.reading["raw"]
        name, unit, divisor, _ = spec(self.index)
        if unit == "text":
            return chr(raw >> 8) + chr(raw & 255)
        return raw / divisor

    @property
    def extra_state_attributes(self):
        value = self.reading
        name, _, divisor, ttl = spec(self.index)
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
                "protocol_profile":self.client.boiler_fields.profile}
