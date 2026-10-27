"""Read-only entities over the existing runtime listener, with no new MQTT IO."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er
from .boiler_fields import FIELDS, QUALITIES
from .const import DOMAIN, CONF_TOPIC_PREFIX

# Longer than the slowest 600 s field TTL, so every polled field had its chance.
UNOBSERVED_RETIRE_SECONDS = 900


def field_unique_id(prefix, index):
    return f"{prefix}_boiler_fields_v1_{FIELDS[index][0]}"


def reconcile_unobserved(hass, prefix, observed, qualified):
    """Hide fields this boiler never reports; never touch user or unreliable choices.

    Disabled (not deleted) records keep Recorder history. A field the firmware
    observes later is enabled again; Home Assistant then reloads the entry.
    """
    registry = er.async_get(hass)
    for index in range(len(FIELDS)):
        if QUALITIES[index] == 1:
            continue  # Unreliable fields stay disabled by default.
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, field_unique_id(prefix, index))
        record = registry.async_get(entity_id) if entity_id else None
        if record is None:
            continue
        if index in observed and record.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(entity_id, disabled_by=None)
        elif qualified and index not in observed and record.disabled_by is None:
            registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)


async def async_setup_boiler_fields(hass, entry, async_add_entities):
    state = hass.data[DOMAIN][entry.entry_id]
    runtime = state["v1_runtime"]
    connection = state.get("v1_connection")
    if not runtime.enabled or connection is None or connection.client is None:
        return
    client = connection.client
    entities = []
    last_key = None
    stream_since = None
    last_presence = None
    def refresh():
        nonlocal last_key, stream_since, last_presence
        cache = client.boiler_fields
        if (client.ready and client.boiler_fields_supported and not cache.invalid
                and cache.profile == "classic_observed"):
            now = client.clock()
            stream_since = now if stream_since is None or now < stream_since else stream_since
            observed = frozenset(i for i, (field, _) in cache.records.items() if field[2] is not None)
            presence = (observed, now - stream_since >= UNOBSERVED_RETIRE_SECONDS)
            if presence != last_presence:
                last_presence = presence
                reconcile_unobserved(hass, entry.data[CONF_TOPIC_PREFIX], *presence)
        else:
            stream_since = None
        if client.boiler_fields_supported and not entities:
            entities.extend(BoilerFieldEntity(entry.data[CONF_TOPIC_PREFIX], client, index)
                            for index in range(len(FIELDS)))
            from .product import is_product
            if is_product(entry):
                from .installation_group import ensure_installation_group
                async_add_entities(entities, config_subentry_id=ensure_installation_group(hass,entry))
            else:
                async_add_entities(entities)
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

    def __init__(self, prefix, client, index):
        self.client, self.index = client, index
        name, unit, _, _, _ = FIELDS[index]
        self._attr_unique_id = field_unique_id(prefix, index)
        self._attr_name = "Boiler " + name.replace("_", " ")
        if QUALITIES[index] == 1:
            self._attr_entity_registry_enabled_default = False
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN,prefix)})
        self._attr_native_unit_of_measurement = {"degC":"°C", "uA":"µA"}.get(unit,unit)
        if unit in ("bool", "bits", "text", "code", "starts"):
            self._attr_native_unit_of_measurement = None
        if unit == "degC":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        # No statistics on unqualified OEM counters or settings. No new energy identity.

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
        name, unit, divisor, _, _ = FIELDS[self.index]
        if unit == "text":
            return chr(raw >> 8) + chr(raw & 255)
        return raw / divisor

    @property
    def extra_state_attributes(self):
        value = self.reading
        name, _, divisor, ttl, _ = FIELDS[self.index]
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
