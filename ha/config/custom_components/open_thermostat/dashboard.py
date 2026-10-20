"""Optional, integration-managed Lovelace dashboard for thermostat rooms."""

import asyncio
import logging

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.util import slugify

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_DIAGNOSTIC_METRICS = (
    "connected",
    "memory_free",
    "memory_min_free",
    "memory_max_alloc",
    "rtc_temperature",
    "cpu_temperature",
    "uptime",
)

EMS_METRICS = (
    "energy",
    "energy_warm_water",
    "energy_heating",
    "warm_water_usage",
    "warm_water_avg_flow",
    "outdoor_temperature",
    "boiler_heating_enabled",
    "boiler_hot_water_enabled",
    "boiler_burner_active",
    "boiler_pump_active",
    "boiler_heating_active",
    "boiler_hot_water_active",
    "boiler_siphon_filling",
    "boiler_fan_active",
    "boiler_pump_venting",
    "boiler_selected_hot_water_temperature",
    "boiler_selected_flow_temperature",
    "boiler_current_flow_temperature",
    "boiler_pressure",
    "boiler_burner_power",
    "boiler_hot_water_flow",
    "boiler_current_hot_water_temperature",
    "boiler_display_code",
    "boiler_service_code",
    "boiler_protocol_version",
)


class RoomDashboard:
    """Manage a separate dashboard containing the discovered climate entities."""

    def __init__(self, hass: HomeAssistant, prefix: str, entry_id: str) -> None:
        self.hass = hass
        self.prefix = prefix
        self.entry_id = entry_id
        self.path = f"open-thermostat-{slugify(prefix, separator='-')}-{entry_id[:8].lower()}"
        self._rooms: set[str] = set()
        self._store: LovelaceStorage | None = None
        self._unsubscribe = None
        self._refresh_task: asyncio.Task | None = None
        self._dirty = False

    async def async_start(self) -> None:
        """Register a Lovelace panel without changing the user's dashboards."""
        dashboards = self.hass.data[LOVELACE_DATA].dashboards
        if self.path in dashboards or frontend.async_panel_exists(self.hass, self.path):
            _LOGGER.warning("Cannot create OpenThermostat dashboard: %s is already used", self.path)
            return

        config = {
            "id": self.path,
            "url_path": self.path,
            "title": "OpenThermostat",
            "icon": "mdi:thermostat",
            "show_in_sidebar": True,
            "require_admin": False,
        }
        store = LovelaceStorage(self.hass, config)
        await store.async_save(self._dashboard_config())
        dashboards[self.path] = store
        try:
            frontend.async_register_built_in_panel(
                self.hass,
                "lovelace",
                frontend_url_path=self.path,
                sidebar_title=config["title"],
                sidebar_icon=config["icon"],
                show_in_sidebar=True,
                require_admin=False,
                config={"mode": "storage"},
            )
        except ValueError:
            dashboards.pop(self.path, None)
            _LOGGER.warning("Cannot register OpenThermostat dashboard at %s", self.path)
            return
        self._store = store
        self._unsubscribe = self.hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._entity_registry_updated
        )

    async def async_stop(self) -> None:
        """Remove the panel when the integration is unloaded or disabled."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._refresh_task is not None:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
        if self._store is not None:
            frontend.async_remove_panel(self.hass, self.path)
            self.hass.data[LOVELACE_DATA].dashboards.pop(self.path, None)
            self._store = None

    @callback
    def set_rooms(self, keys: set[str]) -> None:
        """Keep only rooms present in the latest MQTT status."""
        if keys != self._rooms:
            self._rooms = keys.copy()
            self._schedule_refresh()

    @callback
    def _entity_registry_updated(self, event) -> None:
        """Follow integration entity creation and entity ID changes."""
        self._schedule_refresh()

    @callback
    def _schedule_refresh(self) -> None:
        if self._store is None:
            return
        self._dirty = True
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = self.hass.async_create_task(
                self._refresh(), f"Refresh OpenThermostat dashboard {self.path}"
            )

    async def _refresh(self) -> None:
        while self._dirty:
            self._dirty = False
            await asyncio.sleep(0)
            config = self._dashboard_config()
            if config != await self._store.async_load(False):
                await self._store.async_save(config)

    @callback
    def _dashboard_config(self) -> dict:
        registry = er.async_get(self.hass)
        devices = dr.async_get(self.hass)
        room_cards = []
        heating_cards = []
        for key in sorted(self._rooms):
            unique_id = f"{self.prefix}_room_{key}_climate"
            entity_id = registry.async_get_entity_id("climate", DOMAIN, unique_id)
            if entity_id is not None:
                room_cards.append({
                    "type": "thermostat",
                    "entity": entity_id,
                    "show_current_as_primary": False,
                })
            heating_entities = []
            for platform, suffix in (
                ("binary_sensor", "radiator_heating"),
                ("sensor", "radiator_heating_time"),
                ("sensor", "radiator_estimated_power"),
                ("sensor", "radiator_estimated_energy"),
                ("number", "radiator_power"),
            ):
                entity_id = registry.async_get_entity_id(
                    platform, DOMAIN, f"{self.prefix}_room_{key}_{suffix}"
                )
                if entity_id is not None:
                    heating_entities.append(entity_id)
            if heating_entities:
                device = devices.async_get_device_by_identifier(
                    (DOMAIN, f"{self.prefix}_room_{key}"), self.entry_id
                )
                heating_cards.append({
                    "type": "entities",
                    "title": device.name if device is not None else key,
                    "entities": heating_entities,
                })
        hub_entities = {
            entry.unique_id.removeprefix(f"{self.prefix}_hub_"): entry.entity_id
            for entry in er.async_entries_for_config_entry(registry, self.entry_id)
            if entry.unique_id.startswith(f"{self.prefix}_hub_") and entry.disabled_by is None
        }
        diagnostic_entities = [
            hub_entities[metric]
            for metric in DEVICE_DIAGNOSTIC_METRICS
            if metric in hub_entities
        ]
        ems_entities = [
            hub_entities[metric]
            for metric in EMS_METRICS
            if metric in hub_entities
        ]
        ems_entities += [hub_entities[key] for key in hub_entities
                         if key.endswith("_v2") and key[:-3] in EMS_METRICS]
        polish = self.hass.config.language.lower().startswith("pl")
        rooms_title = "Pomieszczenia" if polish else "Rooms"
        diagnostics_title = "Diagnostyka" if polish else "Diagnostics"
        heating_title = "Ogrzewanie" if polish else "Heating"
        device_title = "Urządzenie" if polish else "Device diagnostics"
        ems_title = "Informacje EMS" if polish else "EMS information"
        diagnostics_cards = []
        if diagnostic_entities:
            diagnostics_cards.append({
                "type": "entities",
                "title": device_title,
                "entities": diagnostic_entities,
            })
        if ems_entities:
            diagnostics_cards.append({
                "type": "entities",
                "title": ems_title,
                "entities": ems_entities,
            })
        # Native cards only. Reported selected flow is NOT a controller request,
        # and burner modulation percentage is NOT measured kW or power factor.
        def graph(title, keys, hours=24):
            entities = [{"entity": hub_entities[key], "name": name}
                        for key, name in keys if key in hub_entities]
            return ({"type": "history-graph", "title": title,
                     "hours_to_show": hours, "entities": entities} if entities else None)
        boiler_cards = [{
            "type": "markdown",
            "content": ("EMS observations only: selected flow is the boiler-reported "
                        "selection, not a proven E32 command. Unknown/stale data is "
                        "not zero. Raw legacy status may lack per-field freshness; "
                        "Classic flame/flow and physical operation require separate "
                        "qualification. No inferred flame or pump state is added."),
        }]
        for card in (
            graph("Reported flow selection and measured flow", (
                ("boiler_selected_flow_temperature", "Reported selected flow"),
                ("boiler_current_flow_temperature", "Reported current flow"))),
            graph("Reported burner modulation (%) — not kW", (
                ("boiler_burner_power", "Reported modulation (%)"),)),
            graph("Reported CV / DHW / flame / pump", (
                ("boiler_heating_active", "Reported CV"),
                ("boiler_hot_water_active", "Reported DHW"),
                ("boiler_burner_active", "Reported flame bit"),
                ("boiler_pump_active", "Reported pump bit"))),
        ):
            if card:
                boiler_cards.append(card)
        analysis_cards = [{
            "type": "markdown",
            "content": ("Energy values below are boot-local nominal-modulation "
                        "ESTIMATES, not gas/heat meters. Water volume integrates "
                        "reported flow over observed intervals. Unknown intervals "
                        "are not extrapolated. Historical legacy counters may use "
                        "old definitions: no automatic statistics deletion, repair "
                        "or mixing is performed. Legacy counter aggregate charts remain "
                        "disabled; only isolated definition-v2 IDs are plotted, without backfill. Native History "
                        "detail depends on Recorder retention; hourly statistics "
                        "cannot reconstruct every burner transition."),
        }]
        counter_keys = ("energy", "energy_heating", "energy_warm_water", "energy_unattributed",
                        "warm_water_usage", "burner_observed_time")
        counters = [hub_entities[key + "_v2"] for key in counter_keys if key + "_v2" in hub_entities]
        if counters:
            analysis_cards.append({"type": "entities", "title": "Current reported / estimated counters",
                                   "entities": counters})
        # No unversioned ID can enter a new counter aggregate chart.
        for title, keys in (
            ("Definition-v2 estimated energy (not a meter)", ("energy", "energy_heating", "energy_warm_water", "energy_unattributed")),
            ("Definition-v2 integrated reported water volume", ("warm_water_usage",)),
            ("Definition-v2 observed reported-flame time", ("burner_observed_time",)),
        ):
            entities = [hub_entities[key + "_v2"] for key in keys if key + "_v2" in hub_entities]
            if entities:
                analysis_cards.append({"type": "statistics-graph", "title": title, "entities": entities,
                                       "days_to_show": 7, "period": "day", "chart_type": "bar",
                                       "stat_types": ["change"]})
        # Room targets and observations stay separate, using registered IDs after rename.
        for key in sorted(self._rooms):
            entities = []
            for metric, name in (("temperature", "Room observed"), ("temperature_set", "Room target")):
                entity_id = registry.async_get_entity_id(
                    "sensor", DOMAIN, f"{self.prefix}_room_{key}_{metric}")
                if entity_id:
                    entities.append({"entity": entity_id, "name": name})
            if entities:
                heating_cards.append({"type": "history-graph", "title": f"Room {key}: target / observed",
                                      "hours_to_show": 24, "entities": entities})
        return {
            "views": [
                {
                    "title": rooms_title,
                    "path": "rooms",
                    "icon": "mdi:thermostat",
                    "cards": room_cards,
                },
                {
                    "title": heating_title,
                    "path": "heating",
                    "icon": "mdi:radiator",
                    "cards": heating_cards,
                },
                {
                    "title": "Boiler observations",
                    "path": "boiler",
                    "icon": "mdi:water-boiler",
                    "cards": boiler_cards,
                },
                {
                    "title": "Analysis",
                    "path": "analysis",
                    "icon": "mdi:chart-line",
                    "cards": analysis_cards,
                },
                {
                    "title": diagnostics_title,
                    "path": "diagnostics",
                    "icon": "mdi:information-outline",
                    "cards": diagnostics_cards,
                },
            ]
        }
