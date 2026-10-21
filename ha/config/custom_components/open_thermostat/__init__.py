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
    from .v1_model import integration_mode, MODE_SHADOW
    # Withdraw current SOURCE control before ANY native config/subentry reload
    # await. A changed draft cannot keep a ready owner while reload is queued.
    state=hass.data.get(DOMAIN,{}).get(entry.entry_id,{})
    runtime=state.get("v1_runtime");connection=state.get("v1_connection")
    if (getattr(runtime,"native_plan_source",None) is not None
            and connection is not None and not connection.closed and connection.client is not None):
        connection.client.require_native_plan_review()
    if (getattr(runtime,"graph_controller_source",None) is not None
            and connection is not None and not connection.closed and connection.client is not None):
        connection.client.require_graph_source_review()
    if integration_mode(entry) == MODE_SHADOW:
        from .v1_heating_graph import reconcile_removed_rooms
        if reconcile_removed_rooms(hass, entry):
            # Native update schedules one follow-up callback; avoid duplicate reload.
            return
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

# SOURCE-owned selection only. No entry option, registry, service or incoming
# manifest can set this. Default remains None/api1; real installation pins require
# independent review. Selecting this branch creates DATA-only, never control.
_GRAPH_DATA_SOURCE_PROFILE = None

def _selected_graph_data_profile(entry):
    from .v1_model import has_graph_rooms,integration_mode,MODE_SHADOW
    if not has_graph_rooms(entry) or integration_mode(entry)!=MODE_SHADOW or _GRAPH_DATA_SOURCE_PROFILE is None:
        return None
    from homeassistant.exceptions import ConfigEntryError
    from .graph_wire import GraphSourceProfile
    profile=_GRAPH_DATA_SOURCE_PROFILE
    try:
        if not isinstance(profile,GraphSourceProfile) or profile.draft_source is None or profile.entry_unique_id is None:
            raise ValueError("complete source bundle and native entry pin required")
        if profile.entry_unique_id!=entry.unique_id:
            return None # Source selection cannot capture another hub/entry.
        profile.validate()
    except (ValueError,TypeError):
        raise ConfigEntryError("graph_profile_unsupported") from None
    return profile

# Trusted reviewed logical context profiles, never options or discovery data.
# Empty preserves existing conservative API1 behavior; no physical qualification.
_COMFORT_CONTEXT_SOURCE_PROFILES = ()
_CONTROLLER_POLICY_SOURCE_PROFILES = ()

_GRAPH_CONTROLLER_ENTRY_SOURCES = ()

def _selected_graph_controller_source(entry):
    from homeassistant.exceptions import ConfigEntryError
    from .v1_model import integration_mode,MODE_SHADOW
    if integration_mode(entry)!=MODE_SHADOW or _GRAPH_CONTROLLER_ENTRY_SOURCES==():return None
    from .graph_control_source import GraphControllerEntrySource
    from .topology_control_source import TopologyControllerEntrySource
    try:
        sources=_GRAPH_CONTROLLER_ENTRY_SOURCES
        if type(sources) is not tuple or len(sources)>8:raise ValueError("source_invalid")
        selected=[]
        for source in sources:
            if not isinstance(source,(GraphControllerEntrySource,TopologyControllerEntrySource)):raise ValueError("source_invalid")
            source.validate()
            if source.controller.entry_unique_id==entry.unique_id:selected.append(source)
        if len(selected)>1:raise ValueError("source_multiple_owners")
        return selected[0] if selected else None
    except (ValueError,TypeError,KeyError):
        raise ConfigEntryError("graph_control_source_invalid") from None


# Explicit independent installation-SHADOW contract; never an entry option.
# Empty means unsupported, not inferred source/physical qualification.
_NATIVE_PLAN_SOURCE_PROFILES = ()

def _selected_native_plan_source(entry):
    from .native_plan import NativePlanSource
    from .v1_model import integration_mode,MODE_SHADOW
    from homeassistant.exceptions import ConfigEntryError
    if integration_mode(entry)!=MODE_SHADOW:return None
    try:
        profiles=_NATIVE_PLAN_SOURCE_PROFILES
        if type(profiles) is not tuple or len(profiles)>8:raise ValueError("native_profile_limit")
        selected=[]
        for source in profiles:
            if type(source) is not NativePlanSource:raise ValueError("native_profile_type")
            source.validate()
            if source.policy.entry_unique_id==entry.unique_id:selected.append(source)
        if len(selected)>1:raise ValueError("native_multiple_owners")
        return selected[0] if selected else None
    except (ValueError,TypeError,KeyError):
        raise ConfigEntryError("native_plan_profile_unsupported") from None

def _selected_controller_policy_source_profile(entry):
    from homeassistant.exceptions import ConfigEntryError
    from .comfort_sources import ControllerPolicySourceProfile
    from .v1_model import MODE_SHADOW,integration_mode
    if integration_mode(entry)!=MODE_SHADOW:return None
    try:
        profiles=_CONTROLLER_POLICY_SOURCE_PROFILES
        if type(profiles) is not tuple or len(profiles)>8:
            raise ValueError("controller_policy_profile_invalid")
        selected=[]
        for profile in profiles:
            if not isinstance(profile,ControllerPolicySourceProfile):
                raise ValueError("controller_policy_profile_invalid")
            profile.validate()
            if profile.entry_unique_id==entry.unique_id:selected.append(profile)
        if len(selected)>1:raise ValueError("controller_policy_multiple_owners")
        return selected[0] if selected else None
    except (ValueError,TypeError):
        raise ConfigEntryError("controller_policy_profile_invalid") from None

def _selected_context_source_profiles(entry):
    from homeassistant.exceptions import ConfigEntryError
    from .comfort_sources import ContextSourceProfile
    from .v1_model import MODE_SHADOW,integration_mode
    if integration_mode(entry)!=MODE_SHADOW:
        return ()
    try:
        profiles=_COMFORT_CONTEXT_SOURCE_PROFILES
        if type(profiles) is not tuple or len(profiles)>16:
            raise ValueError("context_profile_invalid")
        for profile in profiles:
            if not isinstance(profile,ContextSourceProfile):
                raise ValueError("context_profile_invalid")
            profile.validate()
        return tuple(p for p in profiles if p.entry_unique_id==entry.unique_id)
    except (ValueError,TypeError):
        raise ConfigEntryError("context_profile_invalid") from None

async def async_setup_entry(hass, entry):
    from .v1_model import integration_mode, MODE_LEGACY, MODE_SHADOW, RoomBinding
    mode = integration_mode(entry)
    from .v1_model import has_graph_rooms, CONF_ENABLED
    graph_profile=_selected_graph_data_profile(entry)
    graph_control_source=_selected_graph_controller_source(entry)
    native_plan_source=_selected_native_plan_source(entry)
    if native_plan_source is not None and (graph_profile is not None or graph_control_source is not None):
        from homeassistant.exceptions import ConfigEntryError
        raise ConfigEntryError("native_plan_owner_role_conflict")
    if graph_control_source is not None or native_plan_source is not None:
        prior=hass.data.get(DOMAIN,{}).get(entry.entry_id,{})
        if (connection:=prior.get("v1_connection")) is not None and not connection.closed:
            from homeassistant.exceptions import ConfigEntryError
            raise ConfigEntryError("graph_control_existing_owner_active")
    if graph_profile is not None and graph_control_source is not None:
        from homeassistant.exceptions import ConfigEntryError
        raise ConfigEntryError("graph_control_data_owner_conflict")
    if has_graph_rooms(entry) and (mode != MODE_SHADOW or (entry.options.get(CONF_ENABLED, False) and graph_profile is None and graph_control_source is None and native_plan_source is None)):
        from homeassistant.exceptions import ConfigEntryError
        raise ConfigEntryError("graph_room_contract_unavailable")
    if mode == MODE_LEGACY:
        result = await _legacy_setup_entry(hass, entry)
        if result:
            from .metrics_reports import async_register_entry, async_unregister_entry
            async_register_entry(hass, entry)
            entry.async_on_unload(lambda: async_unregister_entry(hass, entry.entry_id))
            entry.async_on_unload(entry.add_update_listener(_async_options_updated))
        return result
    if mode != MODE_SHADOW:
        return False
    from .v1_heating_graph import reconcile_removed_rooms
    reconcile_removed_rooms(hass, entry)
    from homeassistant.const import Platform
    from .v1_runtime import ShadowRuntime
    rooms = [RoomBinding.from_dict(dict(s.data)) for s in entry.subentries.values()
             if s.subentry_type == "zone"]
    context_profiles=_selected_context_source_profiles(entry)
    controller_policy=_selected_controller_policy_source_profile(entry)
    if graph_control_source is not None:
        if controller_policy not in (None,graph_control_source.controller):
            from homeassistant.exceptions import ConfigEntryError
            raise ConfigEntryError("graph_control_source_owner_conflict")
        controller_policy=graph_control_source.controller
    if native_plan_source is not None:
        if controller_policy is not None:
            from homeassistant.exceptions import ConfigEntryError
            raise ConfigEntryError("native_plan_policy_role_conflict")
        controller_policy=native_plan_source.policy
    runtime_kwargs={}
    if native_plan_source is not None:
        runtime_kwargs["native_plan_source"]=native_plan_source
    if graph_control_source is not None:
        runtime_kwargs["graph_controller_source"]=graph_control_source
    if graph_profile is not None:
        runtime_kwargs["graph_data_profile"]=graph_profile
    if context_profiles:
        runtime_kwargs["context_source_profiles"]=context_profiles
    if controller_policy is not None:
        runtime_kwargs["controller_policy_source_profile"]=controller_policy
    try:
        runtime=ShadowRuntime(hass,entry,rooms,**runtime_kwargs)
    except ValueError:
        if controller_policy is not None:
            from homeassistant.exceptions import ConfigEntryError
            raise ConfigEntryError("controller_policy_profile_binding") from None
        if context_profiles:
            from homeassistant.exceptions import ConfigEntryError
            raise ConfigEntryError("context_profile_binding") from None
        raise
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"v1_runtime": runtime}
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_TOPIC_PREFIX])},
        name="OpenThermostat", manufacturer="intuibase", model="OpenThermostat")
    try:
        await runtime.async_start()
        if runtime.enabled:
            from .v1_mqtt import NativeShadowConnection
            connection = NativeShadowConnection(runtime,graph_profile) if graph_profile is not None else NativeShadowConnection(runtime)
            hass.data[DOMAIN][entry.entry_id]["v1_connection"] = connection
            await connection.async_start()
        from .v1_bench_actions import async_register_entry
        async_register_entry(hass, entry)
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.CLIMATE, Platform.SENSOR])
        if entry.options.get(CONF_CREATE_DASHBOARD,False):
            dashboard=RoomDashboard(hass,entry.data[CONF_TOPIC_PREFIX],entry.entry_id)
            hass.data[DOMAIN][entry.entry_id]["dashboard"]=dashboard
            await dashboard.async_start()
            dashboard.set_rooms(set(runtime.rooms))
    except Exception:
        try:
            if dashboard:=hass.data[DOMAIN][entry.entry_id].get("dashboard"):
                await dashboard.async_stop()
        finally:
            from .v1_bench_actions import async_unregister_entry
            try:
                await async_unregister_entry(hass, entry.entry_id)
            finally:
                await runtime.async_stop()
                hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    from .metrics_reports import async_register_entry, async_unregister_entry
    async_register_entry(hass, entry)
    entry.async_on_unload(lambda: async_unregister_entry(hass, entry.entry_id))
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True

async def async_unload_entry(hass, entry):
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if "v1_runtime" not in state:
        return await _legacy_unload_entry(hass, entry)
    from homeassistant.const import Platform
    from .v1_bench_actions import async_unregister_entry
    await async_unregister_entry(hass, entry.entry_id)
    # Withdraw listener/task/transport ownership before any mode transfer.
    await state["v1_runtime"].async_stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.CLIMATE, Platform.SENSOR])
    if unloaded:
        if dashboard:=state.get("dashboard"):
            await dashboard.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
