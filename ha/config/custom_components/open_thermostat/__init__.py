"""OpenThermostat room entities and optional dashboard."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_CREATE_DASHBOARD, CONF_TOPIC_PREFIX, DOMAIN, PLATFORMS
from .dashboard import RoomDashboard
from .heating import HeatingTracker


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the thermostat hub and its room entities."""
    prefix = entry.data[CONF_TOPIC_PREFIX]
    state = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"duration_minutes": {}}
    tracker = HeatingTracker(hass, entry)
    state["heating_tracker"] = tracker
    await tracker.async_start()
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, prefix)},
        name="OpenThermostat",
        manufacturer="intuibase",
        model="OpenThermostat",
    )
    if entry.options.get(CONF_CREATE_DASHBOARD, False):
        dashboard = RoomDashboard(hass, prefix, entry.entry_id)
        await dashboard.async_start()
        state["dashboard"] = dashboard
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        if dashboard := state.get("dashboard"):
            await dashboard.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await tracker.async_stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the room climate platform and its MQTT subscriptions."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await hass.data[DOMAIN][entry.entry_id]["heating_tracker"].async_stop()
        if dashboard := hass.data[DOMAIN][entry.entry_id].get("dashboard"):
            await dashboard.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded

# Explicit mode dispatcher. Existing entries default to legacy; IDs stay intact.
_legacy_setup_entry = async_setup_entry
_legacy_unload_entry = async_unload_entry

async def _async_options_updated(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_migrate_entry(hass, entry):
    if entry.version > 2:
        return False
    if entry.version < 2:
        hass.config_entries.async_update_entry(
            entry, version=2,
            data={**entry.data, "integration_mode": entry.data.get("integration_mode", "legacy")},
        )
    return True

async def async_setup_entry(hass, entry):
    from .v1_model import integration_mode, MODE_LEGACY, MODE_SHADOW, RoomBinding
    mode = integration_mode(entry)
    if mode == MODE_LEGACY:
        result = await _legacy_setup_entry(hass, entry)
        if result:
            entry.async_on_unload(entry.add_update_listener(_async_options_updated))
        return result
    if mode != MODE_SHADOW:
        return False
    from homeassistant.const import Platform
    from .v1_runtime import ShadowRuntime
    rooms = [RoomBinding.from_dict(dict(s.data)) for s in entry.subentries.values()
             if s.subentry_type == "zone"]
    runtime = ShadowRuntime(hass, entry, rooms)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"v1_runtime": runtime}
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_TOPIC_PREFIX])},
        name="OpenThermostat", manufacturer="intuibase", model="OpenThermostat")
    try:
        await runtime.async_start()
        if runtime.enabled:
            from .v1_mqtt import NativeShadowConnection
            connection = NativeShadowConnection(runtime)
            hass.data[DOMAIN][entry.entry_id]["v1_connection"] = connection
            await connection.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.CLIMATE])
    except Exception:
        await runtime.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True

async def async_unload_entry(hass, entry):
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if "v1_runtime" not in state:
        return await _legacy_unload_entry(hass, entry)
    from homeassistant.const import Platform
    # Withdraw listener/task/transport ownership before any mode transfer.
    await state["v1_runtime"].async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.CLIMATE])
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
