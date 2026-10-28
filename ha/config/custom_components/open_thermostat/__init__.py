"""OpenThermostat room entities and optional dashboard."""

import logging
from contextlib import AsyncExitStack

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import CONF_CREATE_DASHBOARD, CONF_TOPIC_PREFIX, DOMAIN, PLATFORMS
from .dashboard import RoomDashboard
from .heating import HeatingTracker

_LOGGER = logging.getLogger(__name__)
_RELOAD_DASHBOARDS = DOMAIN + "_reload_dashboards"


def _drop_setup_state(hass, entry_id, state):
    """A failed old setup may only remove its own published state."""
    entries = hass.data.get(DOMAIN, {})
    if entries.get(entry_id) is state:
        entries.pop(entry_id, None)


async def _cleanup_setup_bench(hass, entry_id, owner):
    from .v1_bench_actions import KEY, async_unregister_entry
    if hass.data.get(KEY, {}).get(entry_id) is owner:
        await async_unregister_entry(hass, entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the thermostat hub and its room entities."""
    prefix = entry.data[CONF_TOPIC_PREFIX]
    state = hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"duration_minutes": {}}
    # Register each inverse before startup: failures and CancelledError both
    # unwind partial subscriptions, platforms and presentation in reverse order.
    async with AsyncExitStack() as cleanup:
        cleanup.callback(_drop_setup_state, hass, entry.entry_id, state)
        tracker = HeatingTracker(hass, entry)
        state["heating_tracker"] = tracker
        cleanup.push_async_callback(tracker.async_stop)
        await tracker.async_start()
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, prefix)},
            name="OpenThermostat", manufacturer="intuibase", model="OpenThermostat")
        if entry.options.get(CONF_CREATE_DASHBOARD, False):
            dashboard = RoomDashboard(hass, prefix, entry.entry_id)
            state["dashboard"] = dashboard
            cleanup.push_async_callback(dashboard.async_stop)
            await dashboard.async_start()
        cleanup.push_async_callback(hass.config_entries.async_unload_platforms, entry, PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        cleanup.pop_all()
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
    # Keep the same presentation during our native config reload. Removing the
    # panel discards an open editor's draft and even its successful save receipt.
    # Runtime/transport still unload normally; this object owns only HA cards.
    from .product import is_product
    dashboard = state.get("dashboard")
    preserve = (dashboard is not None and is_product(entry)
                and integration_mode(entry) == MODE_SHADOW
                and entry.options.get(CONF_CREATE_DASHBOARD, False))
    retained = hass.data.setdefault(_RELOAD_DASHBOARDS, {})
    if preserve:
        state.pop("dashboard")
        retained[entry.entry_id] = dashboard
    try:
        await hass.config_entries.async_reload(entry.entry_id)
    finally:
        if preserve and retained.get(entry.entry_id) is dashboard:
            retained.pop(entry.entry_id)
            await dashboard.async_stop()

async def async_migrate_entry(hass, entry):
    if entry.version > 3:
        return False
    if entry.version < 3:
        from .product import PRODUCT_CONFIG, PRODUCT_VERSION, SUPPORTED_HA_VERSIONS, HA_VERSION, INSTALLATION
        from .v1_model import MODE_SHADOW, integration_mode
        data = {**entry.data, "integration_mode": entry.data.get("integration_mode", "legacy")}
        managed = integration_mode(entry) == MODE_SHADOW
        if managed and HA_VERSION not in SUPPORTED_HA_VERSIONS:
            return False
        if managed:
            data[PRODUCT_CONFIG] = PRODUCT_VERSION
        subs = dict(entry.subentries)
        if managed:
            central = [s for s in subs.values() if s.subentry_type == "heating"]
            if len(central) > 1 or (central and INSTALLATION in data):
                return False
            if central:
                data[INSTALLATION] = dict(central[0].data)
                subs.pop(central[0].subentry_id)
        # Migration changes presentation/routes, never runtime or actuator authority.
        changes = dict(version=3, data=data,
            title="OpenThermostat" if managed and entry.title.startswith("OpenThermostat shadow (") else entry.title,
        )
        if managed:
            # Same pinned transaction; listeners see complete product metadata.
            hass.config_entries._async_update_entry(entry, subentries=subs, **changes)
            object.__setattr__(entry, "_supported_subentry_types", None)
        else:
            hass.config_entries.async_update_entry(entry, **changes)
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

# Reviewed installation-owned diagnostic pins only. Empty until separately
# reviewed; options, discovery and first reports never populate this tuple.
_ORIGINAL_TV02_DIAGNOSTIC_SOURCES = ()

def _selected_original_tv02_sources(entry):
    from .original_tv02 import Tv02DiagnosticSource
    from .v1_model import MODE_SHADOW, integration_mode
    if integration_mode(entry) != MODE_SHADOW:
        return ()
    sources = _ORIGINAL_TV02_DIAGNOSTIC_SOURCES
    if (type(sources) is not tuple or len(sources) > 64
            or any(type(source) is not Tv02DiagnosticSource
                or type(source.entry_unique_id) is not str or not source.entry_unique_id
                for source in sources)):
        _LOGGER.warning("Original TV02 diagnostics disabled: invalid source selection")
        return ()
    return tuple(source for source in sources if source.entry_unique_id == entry.unique_id)

async def _async_selected_original_tv02_sources(hass, entry):
    from .v1_model import MODE_SHADOW, integration_mode
    if integration_mode(entry) != MODE_SHADOW:
        return ()
    # Explicit compiled installation pins take precedence, including a malformed
    # selection: never substitute another source after its review failed.
    if _ORIGINAL_TV02_DIAGNOSTIC_SOURCES != ():
        return _selected_original_tv02_sources(entry)
    from .diagnostic_source_manifest import async_selected_sources
    return await async_selected_sources(hass, entry)

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


# Independent installation-SHADOW contract; compiled fixtures or separately
# reviewed local logical selection, never DATA/readiness/physical authority.
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
        from .native_provisioning import source_from_selection
        local=source_from_selection(entry)
        if local is not None:selected.append(local)
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
    from .product import is_product
    product = is_product(entry)
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
    state = {"v1_runtime": runtime}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = state
    async with AsyncExitStack() as cleanup:
        cleanup.callback(_drop_setup_state, hass, entry.entry_id, state)
        cleanup.push_async_callback(runtime.async_stop)
        group_kwargs = {}
        if product:
            from .installation_group import ensure_installation_group
            group_kwargs["config_subentry_id"] = ensure_installation_group(hass, entry)
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_TOPIC_PREFIX])},
            name="OpenThermostat", manufacturer="intuibase", model="OpenThermostat", **group_kwargs)
        if product:
            tracker = HeatingTracker(hass, entry)
            state["heating_tracker"] = tracker
            cleanup.push_async_callback(tracker.async_stop)
            await tracker.async_start()
        await runtime.async_start()
        if runtime.enabled:
            from .v1_mqtt import NativeShadowConnection
            diagnostic_sources = await _async_selected_original_tv02_sources(hass, entry)
            diagnostic_kwargs = {"tv02_sources": diagnostic_sources} if diagnostic_sources else {}
            connection = (NativeShadowConnection(runtime, graph_profile, **diagnostic_kwargs)
                          if graph_profile is not None else NativeShadowConnection(runtime, **diagnostic_kwargs))
            state["v1_connection"] = connection
            cleanup.push_async_callback(connection.async_close)
            await connection.async_start()
        from .v1_bench_actions import KEY as BENCH_KEY, async_register_entry
        async_register_entry(hass, entry)
        cleanup.push_async_callback(_cleanup_setup_bench, hass, entry.entry_id,
                                    hass.data.get(BENCH_KEY, {}).get(entry.entry_id))
        platforms = [Platform.CLIMATE, Platform.SENSOR]
        if product:
            platforms += [Platform.BINARY_SENSOR, Platform.UPDATE]
        cleanup.push_async_callback(hass.config_entries.async_unload_platforms, entry, platforms)
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
        if entry.options.get(CONF_CREATE_DASHBOARD,False):
            dashboard=hass.data.get(_RELOAD_DASHBOARDS, {}).pop(entry.entry_id, None)
            existing_dashboard = dashboard is not None
            if dashboard is None:
                dashboard=RoomDashboard(hass,entry.data[CONF_TOPIC_PREFIX],entry.entry_id)
            state["dashboard"]=dashboard
            cleanup.push_async_callback(dashboard.async_stop)
            if not existing_dashboard:
                await dashboard.async_start()
            dashboard.set_rooms(set(runtime.rooms))
        from .metrics_reports import async_register_entry, async_unregister_entry
        cleanup.callback(async_unregister_entry, hass, entry.entry_id)
        async_register_entry(hass, entry)
        entry.async_on_unload(lambda: async_unregister_entry(hass, entry.entry_id))
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))
        cleanup.pop_all()
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
    from .product import is_product
    platforms = [Platform.CLIMATE, Platform.SENSOR]
    if is_product(entry):
        platforms.append(Platform.BINARY_SENSOR)
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        if tracker := state.get("heating_tracker"):
            await tracker.async_stop()
        if dashboard:=state.get("dashboard"):
            await dashboard.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
