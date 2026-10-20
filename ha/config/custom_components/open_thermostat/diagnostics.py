
"""Minimal non-secret diagnostics; never exports native MQTT broker credentials."""
from .const import DOMAIN
from .v1_model import integration_mode


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("v1_runtime")
    result = {"integration_mode": integration_mode(entry), "entry_version": entry.version}
    if runtime is None:
        return result
    client = runtime._transport
    result.update(
        enabled=runtime.enabled, transport_ready=runtime.transport_ready,
        diagnostics=dict(runtime.diagnostics),
        rooms=[{"room_id": room_id, "quality": observation.quality,
                "actuator_profile": "C_unverified",
                "actuation_enabled": False}
               for room_id, observation in runtime.observations.items()])
    if client and hasattr(client, "journal"):
        result["mapping"] = {
            key: {"revision": record["config"]["revision"], "digest": record["config_digest"]}
            if record else None for key, record in client.journal.items()}
    return result
