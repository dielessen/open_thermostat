
"""Minimal non-secret diagnostics; never exports native MQTT broker credentials."""
from .const import DOMAIN
from .v1_model import integration_mode


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("v1_runtime")
    from homeassistant.helpers import issue_registry as ir
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"legacy_metrics_history_{entry.entry_id}")
    migration = ir.async_get(hass).async_get_issue(DOMAIN, f"metrics_definition_v2_{entry.entry_id}")
    room_migration = ir.async_get(hass).async_get_issue(DOMAIN, f"room_model_v2_{entry.entry_id}")
    result = {"integration_mode": integration_mode(entry), "entry_version": entry.version,
              "metrics_history": {"review_required": issue is not None or migration is not None or room_migration is not None,
                  "room_model_review_required": room_migration is not None,
                  "version2_definition": "isolated_new_entities_and_wire_fields",
                  "legacy_entity_references_retained": True,
                  "automatic_statistics_migration": False, "historic_definition_verified": False,
                  "definition": "schema2 boot-local estimated/integrated counters; old history not certified"}}
    from .dhw import entry_snapshot
    result["dhw"] = entry_snapshot(hass, entry)
    if runtime is None:
        return result
    connection = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("v1_connection")
    from .v1_mqtt import NativeShadowConnection
    result["read_only_original_ingress"] = {"available": False, "snapshot": None,
        "control_qualified": False}
    if isinstance(connection, NativeShadowConnection) and connection.runtime is runtime:
        result["read_only_original_ingress"] = {"available": True,
            "snapshot": connection.original_ingress_status(), "control_qualified": False}
    client = runtime._transport
    result["read_only_last_rejection"] = getattr(client, "last_rejection_payload", None)
    supervisor = getattr(client, "supervisor_payload", None)
    result["read_only_supervisor"] = {
        "available": supervisor is not None,
        "snapshot": supervisor,
        "control_qualified": False,
        "scope": "reported_shadow_intent_only",
    }
    result["read_only_metrics"] = {
        "supported": bool(getattr(client,"metrics_supported",False)),
        "available": getattr(client,"metrics_payload",None) is not None,
        "control_qualified": False,
        "scope": "snapshot_not_source_or_actuator_admission",
    }
    result.update(
        enabled=runtime.enabled, transport_ready=runtime.transport_ready,
        diagnostics=dict(runtime.diagnostics),
        comfort_context_sources={room_id:runtime.context_source_status(room_id) for room_id in runtime.rooms},
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
