
"""Minimal non-secret diagnostics; never exports native MQTT broker credentials."""
from .const import DOMAIN
from .v1_model import integration_mode


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("v1_runtime")
    from homeassistant.helpers import issue_registry as ir
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"legacy_metrics_history_{entry.entry_id}")
    migration = ir.async_get(hass).async_get_issue(DOMAIN, f"metrics_definition_v2_{entry.entry_id}")
    result = {"integration_mode": integration_mode(entry), "entry_version": entry.version,
              "metrics_history": {"review_required": issue is not None or migration is not None,
                  "version2_definition": "isolated_new_entities_and_wire_fields",
                  "legacy_entity_references_retained": True,
                  "automatic_statistics_migration": False, "historic_definition_verified": False,
                  "definition": "schema2 boot-local estimated/integrated counters; old history not certified"}}
    if runtime is None:
        return result
    client = runtime._transport
    result["read_only_metrics"] = {
        "supported": bool(getattr(client,"metrics_supported",False)),
        "available": getattr(client,"metrics_payload",None) is not None,
        "control_qualified": False,
        "scope": "snapshot_not_source_or_actuator_admission",
    }
    result.update(
        enabled=runtime.enabled, transport_ready=runtime.transport_ready,
        diagnostics=dict(runtime.diagnostics),
        rooms=[{"room_id": room_id, "quality": observation.quality,
                "actuator_profile": "C_unverified",
                "actuation_enabled": False}
               for room_id, observation in runtime.observations.items()])
    if client and isinstance(getattr(client, "journal", None), dict):
        result["mapping"] = {
            key: {"revision": record["config"]["revision"], "digest": record["config_digest"]}
            if record else None for key, record in client.journal.items()}
    elif client and hasattr(client, "graph_status"):
        # Status/revisions only, never tokens/pins/mapping/entities/raw config.
        result["graph"] = client.graph_status
    return result
