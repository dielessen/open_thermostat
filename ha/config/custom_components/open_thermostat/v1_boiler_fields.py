"""Read-only entities over the existing runtime listener, with no new MQTT IO."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.const import EntityCategory
from .boiler_fields import FIELDS, QUALITIES
from .const import DOMAIN, CONF_TOPIC_PREFIX


async def async_setup_boiler_fields(hass, entry, async_add_entities):
    state = hass.data[DOMAIN][entry.entry_id]
    runtime = state["v1_runtime"]
    connection = state.get("v1_connection")
    if not runtime.enabled or connection is None or connection.client is None:
        return
    client = connection.client
    entities = []
    last_key = None
    def refresh():
        nonlocal last_key
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
        self._attr_unique_id = f"{prefix}_boiler_fields_v1_{name}"
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
        return {"data_role":"read_only_boiler_field", "control_qualified":False,
                "age_basis":"firmware_snapshot_plus_local_elapsed; network transit unmeasured",
                "quality":({0:"reported",1:"unreliable",2:"inferred"}.get(value["quality"]) if value else "unknown"),
                "source_type":value["source_type"] if value else None,
                "source_observed_at_ms":value["observed_at_ms"] if value else None,
                "protocol_profile":self.client.boiler_fields.profile}
