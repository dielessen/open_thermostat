"""Native Sensor platform over the EXISTING shadow connection/runtime listener."""
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN,CONF_TOPIC_PREFIX

async def async_setup_shadow_metrics(hass,entry,async_add_entities):
    from .sensor import HubMetric,HUB_METRICS,VERSIONED_METRICS
    state=hass.data[DOMAIN][entry.entry_id];runtime=state["v1_runtime"]
    if not runtime.enabled:
        return # Disabled editor provisions no metrics entities/listeners/IO.
    connection=state.get("v1_connection")
    if connection is None or connection.client is None:
        return
    client=connection.client;entities=[];last_key=None
    def refresh():
        nonlocal last_key
        if client.metrics_supported and not entities:
            for metric in HUB_METRICS["ems_metrics"]:
                entities.append(HubMetric(entry.data[CONF_TOPIC_PREFIX],"ems_metrics",metric,entry.entry_id))
                if metric in VERSIONED_METRICS:
                    old_id=er.async_get(hass).async_get_entity_id(
                        "sensor",DOMAIN,f'{entry.data[CONF_TOPIC_PREFIX]}_hub_{metric}')
                    old=er.async_get(hass).async_get(old_id) if old_id else None
                    if old is not None and old.config_entry_id==entry.entry_id:
                        entities.append(HubMetric(entry.data[CONF_TOPIC_PREFIX],"ems_metrics",metric,
                                                  entry.entry_id,definition_version=1))
            async_add_entities(entities)
            last_key=None
        key=client.metrics_key
        if key==last_key:
            return # Existing2s control poll must not rewrite every metric state.
        last_key=key;payload=client.metrics_payload
        for entity in entities:
            entity._attr_extra_state_attributes={**(entity.extra_state_attributes or {}),
                "data_role":"read_only_snapshot","control_qualified":False}
            entity.update_payload(payload or {},payload is not None)
    entry.async_on_unload(runtime.add_listener(refresh))
    refresh()
