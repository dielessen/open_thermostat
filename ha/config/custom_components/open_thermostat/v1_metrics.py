"""Native Sensor platform over the EXISTING shadow connection/runtime listener."""
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN,CONF_TOPIC_PREFIX
from .metric_snapshot import finite

# EMS+ outdoor telegram (0xD1): on a Classic boiler it never reports and the
# boiler field "outdoor temperature" is the one entity, so it waits for a value.
VALUE_GATED="outdoor_temperature"

async def async_setup_shadow_metrics(hass,entry,async_add_entities):
    from .sensor import HubMetric,HUB_METRICS,VERSIONED_METRICS
    state=hass.data[DOMAIN][entry.entry_id];runtime=state["v1_runtime"]
    if not runtime.enabled:
        return # Disabled editor provisions no metrics entities/listeners/IO.
    connection=state.get("v1_connection")
    if connection is None or connection.client is None:
        return
    from .product import is_product
    from .installation_group import ensure_installation_group
    add_options = ({"config_subentry_id": ensure_installation_group(hass, entry)}
                   if is_product(entry) else {})
    client=connection.client;entities=[];last_key=None;gated=None;marked=False
    def refresh():
        nonlocal last_key,gated,marked
        if client.metrics_supported and not entities:
            for metric in HUB_METRICS["ems_metrics"]:
                if metric==VALUE_GATED:
                    continue
                entities.append(HubMetric(entry.data[CONF_TOPIC_PREFIX],"ems_metrics",metric,entry.entry_id))
                if metric in VERSIONED_METRICS:
                    old_id=er.async_get(hass).async_get_entity_id(
                        "sensor",DOMAIN,f'{entry.data[CONF_TOPIC_PREFIX]}_hub_{metric}')
                    old=er.async_get(hass).async_get(old_id) if old_id else None
                    if old is not None and old.config_entry_id==entry.entry_id:
                        entities.append(HubMetric(entry.data[CONF_TOPIC_PREFIX],"ems_metrics",metric,
                                                  entry.entry_id,definition_version=1))
            async_add_entities(entities, **add_options)
            last_key=None
        key=client.metrics_key
        if key==last_key:
            return # Existing2s control poll must not rewrite every metric state.
        last_key=key;payload=client.metrics_payload
        field=HUB_METRICS["ems_metrics"][VALUE_GATED][0]
        if gated is None and entities and payload is not None and finite(payload.get(field)):
            gated=HubMetric(entry.data[CONF_TOPIC_PREFIX],"ems_metrics",VALUE_GATED,entry.entry_id)
            entities.append(gated)
            async_add_entities([gated], **add_options)
        if gated is not None and not marked and payload is not None and finite(payload.get(field)):
            # A real value: the stale-entity cleanup keeps this record (native_entity_cleanup.RETIRED).
            from .native_entity_cleanup import mark_reported
            marked=mark_reported(hass,gated.unique_id)
        for entity in entities:
            entity._attr_extra_state_attributes={**(entity.extra_state_attributes or {}),
                "data_role":"read_only_snapshot","control_qualified":False}
            entity.update_payload(payload or {},payload is not None)
    entry.async_on_unload(runtime.add_listener(refresh))
    refresh()
