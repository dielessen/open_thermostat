"""Optional, integration-managed Lovelace dashboard for thermostat rooms.

Three views, built from the entity registry (renamed entity IDs are followed,
disabled and absent entities are left out) with built-in cards only:

* Heating: now (boiler request, flow, agreement), the heating advice (only
  while there is any), one section per E32 room
  (with a small "Learning" area once the E32 reports it), the E32 next to the
  current thermostat (only in a home with one), the boiler essentials (with today's hot-water taps) and the
  Bluetooth sensors;
* Boiler: the reported boiler fields and their history;
* Diagnostics: device and EMS details, hot water, estimates, each with a
  one-line note.

A stored Lovelace config has no per-viewer language, so the few fixed
headings follow the Home Assistant language (English or Dutch) and the
dashboard is rebuilt when that changes. Entity names come from Home
Assistant's own translations.
"""

import asyncio
import json
import logging

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import DOMAIN
from .product import is_product
from .week_planner import ROOM_CARD_TYPE

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

# E32 room entities: unique ID f"{prefix}_e32_room_{room id}_{key}" (longest key first).
ROOM_KEYS = ("fallback_setpoint", "inactive_until", "heating_start", "flow_advice", "temperature", "learning",
             "setpoint", "status", "demand", "state")
# Today's hot water from the E32 (unique ID f"{prefix}_hub_{key}").
DHW_TODAY = ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today")
BLE_KEYS = ("temperature", "humidity", "battery")

# Boiler essentials: (key, boiler field, older hub metric).
ESSENTIALS = (
    ("flow", "measured_flow_temperature", "boiler_current_flow_temperature"),
    ("return", "measured_return_temperature", None),
    ("modulation", "reported_burner_modulation", "boiler_burner_power"),
    ("pressure", "pressure", "boiler_pressure"),
    ("dhw", "measured_dhw_temperature", "boiler_current_hot_water_temperature"),
    ("code", "display_code", "boiler_display_code"),
)

# The shadow comparison entities: created only once the E32 saw a thermostat to compare with.
COMPARISON_KEYS = ("shadow_agreement_today", "shadow_tado_heating_time_today", "shadow_tado_starts_today")

TEXT = {
    "en": {
        "heating": "Heating", "boiler_view": "Boiler", "diagnostics": "Diagnostics",
        "room_settings": "Room settings", "now": "Now", "rooms": "Rooms", "set_up_rooms": "Set up rooms",
        "settings": "{room} settings",
        "boiler_request": "Boiler request (E32)", "flow": "Flow temperature", "return": "Return temperature",
        "modulation": "Modulation", "pressure": "Pressure", "dhw": "Hot water", "code": "Display code",
        "starts_hour": "Burner starts last hour", "short_cycling": "Short cycling",
        "agreement": "Agreement with thermostat", "measured": "Measured by E32", "target": "Target temperature",
        "mode": "Mode", "off_until": "Off until", "without_ha": "Temperature without Home Assistant",
        "compare": "E32 and thermostat", "e32_request": "Boiler request E32",
        "thermostat_request": "Thermostat request", "heating_time_e32": "Heating time today (E32)",
        "heating_time_thermostat": "Heating time today (thermostat)", "starts_e32": "Burner starts today (E32)",
        "starts_thermostat": "Burner starts today (thermostat)", "heating_per_day": "Heating time per day",
        "boiler": "Boiler", "bluetooth": "Bluetooth sensors", "temperature": "Temperature",
        "humidity": "Humidity", "battery": "Battery",
        "shadow": "Shadow mode: the E32 calculates along but does not control the boiler yet; your current "
                  "thermostat or the boiler's own control stays in charge.",
        "active": "The E32 controls the boiler.",
        "how_title": "How it works",
        "how": "You set the rooms, their sensors, target temperatures and week program here in Home Assistant. "
               "The E32 stores this plan and runs it, also without Home Assistant, with its own Bluetooth sensors "
               "and week program.",
        "boiler_fields": "Reported boiler fields", "inferred": "Inferred activity — not verified operation",
        "unreliable": "Unreliable raw boiler diagnostics",
        "boiler_note": "Values as the boiler reports them. Unknown or stale is not zero; modulation is a percentage, "
                       "not kW.",
        "legacy_boiler_note": "Reported by the boiler over EMS, not a proven E32 command. Unknown or stale is not zero.",
        "flow_graph": "Flow selection, flow and return", "flow_selection": "Reported selected flow",
        "measured_flow": "Measured flow", "measured_return": "Measured return",
        "current_flow": "Reported current flow",
        "modulation_graph": "Burner modulation (%) — not kW", "modulation_series": "Reported modulation (%)",
        "dhw_graph": "Hot water temperatures", "dhw_selected": "Reported selected hot water",
        "dhw_measured": "Measured hot water", "dhw_target": "Reported hot water target",
        "states_graph": "Reported heating / hot water / flame / pump", "state_heating": "Reported heating",
        "state_dhw": "Reported hot water", "state_flame": "Reported flame bit", "state_pump": "Reported pump bit",
        "device": "Device diagnostics", "ems": "EMS information",
        "dhw_card": "Hot water capability and quality",
        "dhw_note": "Domestic hot water, read-only: last reported values with unverified source age; "
                    "nothing is written to the boiler.",
        "dhw_none": "No hot water fields on this connection; unknown is not zero or off.",
        "dhw_profile": "Profile", "dhw_status": "status", "unknown": "Unknown",
        "estimates_note": "Energy and volume are estimates from reported values, not gas or heat meters.",
        "counters": "Reported and estimated counters",
        "energy_chart": "Estimated energy per day (not a meter)", "volume_chart": "Hot water volume per day",
        "flame_chart": "Observed flame time per day",
        "models_note": "Room heat models are estimates, not measured heat; unknown or stale inputs leave gaps.",
        "room_history": "{room}: target and measured", "room_measured": "Measured", "room_target": "Target",
        "learning": "Learning", "flow_advice": "Recommended flow", "heating_start": "Heating starts",
        "learning_note": "The E32 also learns how fast each room warms up and works out the lowest flow "
                         "temperature that still makes up a 1 °C shortfall in time (the recommended flow).",
        "advice_only": "For now this is advice only; the E32 keeps its own rule.",
        "dhw_taps": "Hot water taps today", "dhw_today": "Hot water today",
        "advice": "Advice", "advice_where": "Where", "advice_confidence": "Confidence",
        "advice_note": "Advice only: nothing is changed automatically.",
        "confidence_low": "low", "confidence_medium": "medium", "confidence_high": "high",
    },
    "nl": {
        "heating": "Verwarming", "boiler_view": "Ketel", "diagnostics": "Diagnose",
        "room_settings": "Ruimte-instellingen", "now": "Nu", "rooms": "Ruimtes", "set_up_rooms": "Ruimtes instellen",
        "settings": "Instellingen {room}",
        "boiler_request": "Ketelvraag (E32)", "flow": "Aanvoertemperatuur", "return": "Retourtemperatuur",
        "modulation": "Modulatie", "pressure": "Waterdruk", "dhw": "Warm water", "code": "Displaycode",
        "starts_hour": "Branderstarts afgelopen uur", "short_cycling": "Pendelen",
        "agreement": "Overeenstemming met thermostaat", "measured": "Gemeten door E32",
        "target": "Gewenste temperatuur", "mode": "Stand", "off_until": "Uit tot",
        "without_ha": "Temperatuur zonder Home Assistant",
        "compare": "E32 en thermostaat vergeleken", "e32_request": "Ketelvraag E32",
        "thermostat_request": "Vraag thermostaat", "heating_time_e32": "Stooktijd vandaag (E32)",
        "heating_time_thermostat": "Stooktijd vandaag (thermostaat)", "starts_e32": "Branderstarts vandaag (E32)",
        "starts_thermostat": "Branderstarts vandaag (thermostaat)", "heating_per_day": "Stooktijd per dag",
        "boiler": "Ketel", "bluetooth": "Bluetooth-sensoren", "temperature": "Temperatuur",
        "humidity": "Luchtvochtigheid", "battery": "Batterij",
        "shadow": "Schaduwmodus: de E32 rekent mee maar stuurt de ketel nog niet; je huidige thermostaat of de "
                  "eigen regeling van de ketel blijft de baas.",
        "active": "De E32 regelt de ketel.",
        "how_title": "Zo werkt het",
        "how": "Je stelt de ruimtes, hun sensoren, gewenste temperaturen en het weekprogramma hier in Home Assistant "
               "in. De E32 bewaart dit plan en voert het uit, ook zonder Home Assistant, met zijn eigen "
               "Bluetooth-sensoren en weekprogramma.",
        "boiler_fields": "Gemelde ketelwaarden", "inferred": "Afgeleide activiteit — niet geverifieerd",
        "unreliable": "Onbetrouwbare ruwe keteldiagnose",
        "boiler_note": "Waarden zoals de ketel ze meldt. Onbekend of verouderd is geen nul; modulatie is een "
                       "percentage, geen kW.",
        "legacy_boiler_note": "Gemeld door de ketel via EMS, geen bewezen E32-opdracht. Onbekend of verouderd is "
                              "geen nul.",
        "flow_graph": "Aanvoerkeuze, aanvoer en retour", "flow_selection": "Gemelde gekozen aanvoer",
        "measured_flow": "Gemeten aanvoer", "measured_return": "Gemeten retour",
        "current_flow": "Gemelde huidige aanvoer",
        "modulation_graph": "Brandermodulatie (%) — geen kW", "modulation_series": "Gemelde modulatie (%)",
        "dhw_graph": "Warmwatertemperaturen", "dhw_selected": "Gemeld gekozen warm water",
        "dhw_measured": "Gemeten warm water", "dhw_target": "Gemeld warmwaterdoel",
        "states_graph": "Gemeld verwarmen / warm water / vlam / pomp", "state_heating": "Gemeld verwarmen",
        "state_dhw": "Gemeld warm water", "state_flame": "Gemelde vlambit", "state_pump": "Gemelde pompbit",
        "device": "Apparaatdiagnose", "ems": "EMS-informatie",
        "dhw_card": "Warmwatermogelijkheden en kwaliteit",
        "dhw_note": "Warm tapwater, alleen lezen: laatst gemelde waarden met onbevestigde bronleeftijd; "
                    "er wordt niets naar de ketel geschreven.",
        "dhw_none": "Geen warmwaterwaarden op deze verbinding; onbekend is geen nul of uit.",
        "dhw_profile": "Profiel", "dhw_status": "status", "unknown": "Onbekend",
        "estimates_note": "Energie en volume zijn schattingen uit gemelde waarden, geen gas- of warmtemeter.",
        "counters": "Gemelde en geschatte tellers",
        "energy_chart": "Geschatte energie per dag (geen meter)", "volume_chart": "Warmwatervolume per dag",
        "flame_chart": "Waargenomen vlamtijd per dag",
        "models_note": "Warmtemodellen per ruimte zijn schattingen, geen gemeten warmte; onbekende of verouderde "
                       "invoer laat gaten.",
        "room_history": "{room}: gewenst en gemeten", "room_measured": "Gemeten", "room_target": "Gewenst",
        "learning": "Leren", "flow_advice": "Geadviseerde aanvoer", "heating_start": "Start verwarmen",
        "learning_note": "De E32 leert ook hoe snel elke ruimte opwarmt en berekent de laagste "
                         "aanvoertemperatuur die een tekort van 1 °C nog op tijd inhaalt (de geadviseerde aanvoer).",
        "advice_only": "Voorlopig is dat alleen advies; de E32 houdt zijn eigen regel aan.",
        "dhw_taps": "Warmwatertappen vandaag", "dhw_today": "Warm water vandaag",
        "advice": "Advies", "advice_where": "Waar", "advice_confidence": "Zekerheid",
        "advice_note": "Alleen advies: er wordt niets automatisch veranderd.",
        "confidence_low": "laag", "confidence_medium": "middel", "confidence_high": "hoog",
    },
}


def dashboard_language(hass):
    """Dutch for a Dutch Home Assistant, English otherwise."""
    language = (hass.config.language or "en").lower().replace("_", "-")
    return "nl" if language.split("-")[0] == "nl" else "en"


def view_cards(view):
    """Every card of a view, also inside its sections."""
    cards = list(view.get("cards", []))
    for section in view.get("sections", []):
        cards.extend(section.get("cards", []))
    return cards


def _section(*cards):
    return {"type": "grid", "cards": [card for card in cards if card]}


def _heading(text, icon=None, badges=None, style="title", visibility=None):
    card = {"type": "heading", "heading": text, "heading_style": style}
    if icon:
        card["icon"] = icon
    if badges:
        card["badges"] = badges
    if visibility:
        card["visibility"] = visibility
    return card


def _known(entity_id):
    """Card visibility: only while the entity has a value."""
    return [{"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}]


def _learning_cards(t, room):
    """A compact "Learning" area under a room: status badge, recommended flow, predicted start.

    Nothing without the learned entities (older firmware); hidden while the E32 reports none.
    """
    learning, advice, start = room.get("learning"), room.get("flow_advice"), room.get("heating_start")
    if not learning:
        return []
    badge = {"type": "entity", "entity": learning, "show_state": True, "show_icon": True, "color": "teal"}
    return [
        _heading(t["learning"], "mdi:school-outline", [badge], "subtitle", _known(learning)),
        # The advice only means something once the room is learned.
        _tile(advice, t["flow_advice"],
              visibility=[{"condition": "state", "entity": learning, "state": "ready"}, *_known(advice)]),
        _tile(start, t["heating_start"], visibility=_known(start)),
    ]


ADVICE_ICONS = {"warning": "mdi:alert-outline", "suggestion": "mdi:lightbulb-on-outline",
                "info": "mdi:information-outline"}


def _advice_section(t, advice):
    """The current heating advice (title, action, where); hidden while there is none."""
    if not advice:
        return None
    quoted = json.dumps(advice)
    confidence = json.dumps({key: t["confidence_" + key] for key in ("low", "medium", "high")})
    icons = json.dumps(ADVICE_ICONS)
    content = ("{% set icons = " + icons + " %}{% set confidence = " + confidence + " %}"
               "{% for item in state_attr(" + quoted + ", 'items') or [] %}"
               "<ha-icon icon=\"{{ icons.get(item.severity, 'mdi:information-outline') }}\"></ha-icon> "
               "**{{ item.title }}**\n\n{{ item.action }}\n\n"
               "*" + t["advice_where"] + ": {{ item.where }} · " + t["advice_confidence"]
               + ": {{ confidence.get(item.confidence, item.confidence) }}*\n\n"
               "{% endfor %}" + t["advice_note"])
    shown = [{"condition": "numeric_state", "entity": advice, "above": 0}]
    section = _section(_heading(t["advice"], "mdi:lightbulb-on-outline", style="title", visibility=shown),
                       {"type": "markdown", "content": content, "visibility": shown})
    section["visibility"] = shown
    return section


def _tile(entity_id, name=None, icon=None, features=None, visibility=None):
    if entity_id is None:
        return None
    card = {"type": "tile", "entity": entity_id}
    if name:
        card["name"] = name
    if icon:
        card["icon"] = icon
    if features:
        card["features"] = features
    if visibility:
        card["visibility"] = visibility
    return card


class RoomDashboard:
    """Manage a separate dashboard containing the discovered climate entities."""

    def __init__(self, hass: HomeAssistant, prefix: str, entry_id: str) -> None:
        self.hass = hass
        self.prefix = prefix
        self.entry_id = entry_id
        self.path = f"open-thermostat-{slugify(prefix, separator='-')}-{entry_id[:8].lower()}"
        self._rooms: set[str] = set()
        self._store: LovelaceStorage | None = None
        self._unsubscribe = []
        self._refresh_task: asyncio.Task | None = None
        self._dirty = False
        self._hub = None
        self._hub_unsubscribe = None
        self._hub_signature = None

    async def async_start(self) -> None:
        """Register a Lovelace panel without changing the user's dashboards."""
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry and is_product(entry):
            from .week_planner import async_setup_planner
            await async_setup_planner(self.hass)
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
        self._unsubscribe = [
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_updated),
            self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._registry_updated),
            self.hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, self._registry_updated),
        ]
        self._watch_hub()

    async def async_stop(self) -> None:
        """Remove the panel when the integration is unloaded or disabled."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        self._unwatch_hub()
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
    def _registry_updated(self, event) -> None:
        """Follow entity creation, entity ID and device name changes, and the HA language."""
        self._watch_hub()
        self._schedule_refresh()

    def _heating_hub(self):
        return self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("heating_hub")

    @callback
    def _watch_hub(self) -> None:
        """Rebuild when the E32 reports other rooms, room names or thermostats (not on every reading)."""
        hub = self._heating_hub()
        if hub is self._hub or self._store is None:
            return
        self._unwatch_hub()
        if hub is not None:
            self._hub = hub
            self._hub_unsubscribe = hub.add_listener(self._hub_changed)

    @callback
    def _unwatch_hub(self) -> None:
        if self._hub is not None:
            self._hub_unsubscribe()
        self._hub = None

    @callback
    def _hub_changed(self) -> None:
        signature = self._signature(self._hub)
        if signature != self._hub_signature:
            self._hub_signature = signature
            self._schedule_refresh()

    @staticmethod
    def _signature(hub):
        if hub is None or not hub.fresh:
            return None
        plan = hub.plan.plan if hub.plan is not None else None
        return (hub.status.get("mode"),
                tuple((key, room.get("name"), room.get("source")) for key, room in hub.rooms.items()),
                tuple((key, sensor.get("name")) for key, sensor in hub.ble.items()),
                json.dumps(plan, sort_keys=True, default=str) if plan else None)

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

    # -- registry lookups -------------------------------------------------

    def _entries(self):
        registry = er.async_get(self.hass)
        return [item for item in er.async_entries_for_config_entry(registry, self.entry_id)
                if item.platform == DOMAIN and item.disabled_by is None]

    def _device_name(self, identifier, fallback):
        device = dr.async_get(self.hass).async_get_device_by_identifier(identifier, self.entry_id)
        if device is None:
            return fallback
        return device.name_by_user or device.name or fallback

    def _e32_rooms(self, entries):
        """{room id: {key: entity id}} in the order the E32 reports its rooms.

        While the telemetry is fresh, a room the E32 no longer reports is left
        out (its entities stay, unavailable, until the user deletes its device).
        """
        head = f"{self.prefix}_e32_room_"
        rooms: dict[str, dict[str, str]] = {}
        for item in entries:
            if not item.unique_id.startswith(head):
                continue
            rest = item.unique_id.removeprefix(head)
            for key in ROOM_KEYS:
                if rest.endswith("_" + key):
                    rooms.setdefault(rest[:-len(key) - 1], {})[key] = item.entity_id
                    break
        hub = self._heating_hub()
        order = list(hub.rooms) if hub is not None else []
        if hub is not None and hub.fresh:
            rooms = {room_id: room for room_id, room in rooms.items() if room_id in hub.rooms}
        return dict(sorted(rooms.items(), key=lambda pair: (
            order.index(pair[0]) if pair[0] in order else len(order), pair[0])))

    def _e32_ble(self, entries):
        head = f"{self.prefix}_e32_ble_"
        sensors: dict[str, dict[str, str]] = {}
        for item in entries:
            if item.unique_id.startswith(head):
                sensor_id, _, metric = item.unique_id.removeprefix(head).rpartition("_")
                if sensor_id and metric in BLE_KEYS:
                    sensors.setdefault(sensor_id, {})[metric] = item.entity_id
        hub = self._heating_hub()
        if hub is not None and hub.fresh:
            sensors = {sensor_id: metrics for sensor_id, metrics in sensors.items() if sensor_id in hub.ble}
        return sensors

    def _room_thermostat(self, room_id):
        """The Home Assistant thermostat whose target the E32 room follows, if it exists."""
        hub = self._heating_hub()
        if hub is None:
            return None
        candidates = []
        plan_room = hub.plan.room(room_id) if hub.plan is not None else None
        if plan_room:
            candidates.append(plan_room.get("setpoint_entity"))
            candidates.extend(source.get("id") for source in plan_room.get("sources", [])
                              if type(source) is dict and source.get("type") == "ha")
        status_room = hub.rooms.get(room_id)
        if status_room:
            candidates.append(status_room.get("source"))
        registry = er.async_get(self.hass)
        for entity_id in candidates:
            if (type(entity_id) is str and entity_id.startswith("climate.")
                    and (self.hass.states.get(entity_id) is not None or registry.async_get(entity_id))):
                return entity_id
        return None

    # -- the dashboard ------------------------------------------------------

    @callback
    def _dashboard_config(self) -> dict:
        t = TEXT[dashboard_language(self.hass)]
        registry = er.async_get(self.hass)
        entries = self._entries()
        hub_entities = {
            item.unique_id.removeprefix(f"{self.prefix}_hub_"): item.entity_id
            for item in entries if item.unique_id.startswith(f"{self.prefix}_hub_")
        }
        # Registry identities follow user renames; model choice never filters fields.
        native_fields = {
            item.unique_id.removeprefix(f"{self.prefix}_boiler_fields_v1_"): item.entity_id
            for item in entries
            if item.domain == "sensor" and item.unique_id.startswith(f"{self.prefix}_boiler_fields_v1_")
        }
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        product = entry is not None and is_product(entry)
        from .room_plan import has_room_plan
        e32_rooms = product and has_room_plan(entry)
        # Older HA room records (zone subentries). With an E32 room plan the
        # rooms are set up in the options flow: no settings view or buttons;
        # only each record's own subview stays, for the link in its
        # reconfigure dialog.
        legacy = [sub for sub in entry.subentries.values() if sub.subentry_type == "zone"] if product else []

        def graph(title, keys, lookup, hours=24):
            entities = [{"entity": lookup[key], "name": name} for key, name in keys if key in lookup]
            return ({"type": "history-graph", "title": title, "hours_to_show": hours, "entities": entities}
                    if entities else None)

        def essential(key):
            _, field, metric = next(item for item in ESSENTIALS if item[0] == key)
            return native_fields.get(field) or (hub_entities.get(metric) if metric else None)

        heating = self._heating_sections(t, entries, hub_entities, native_fields, essential,
                                         registry, e32_rooms, legacy)
        boiler, unreliable = self._boiler_sections(t, hub_entities, native_fields, graph)
        diagnostics = self._diagnostics_cards(t, registry, hub_entities, unreliable)
        return {
            "views": [
                {"title": t["heating"], "path": "heating", "icon": "mdi:home-thermometer",
                 "type": "sections", "max_columns": 3, "sections": heating},
                *([{
                    "title": t["room_settings"],
                    "panel": True,
                    "path": "week", "icon": "mdi:calendar-week",
                    "cards": [{"type": ROOM_CARD_TYPE,
                               "entry_id": self.entry_id, "room_id": sub.data["room_id"]}
                              for sub in legacy[:1]],
                }] if product and not e32_rooms else []),
                *[{"title": sub.title, "path": "room-" + sub.data["room_id"],
                   "subview": True, "panel": True, "icon": "mdi:cog",
                   "cards": [{"type": ROOM_CARD_TYPE, "entry_id": self.entry_id,
                              "room_id": sub.data["room_id"]}]}
                  for sub in legacy],
                {"title": t["boiler_view"], "path": "boiler", "icon": "mdi:water-boiler",
                 "type": "sections", "max_columns": 2, "sections": boiler},
                {"title": t["diagnostics"], "path": "diagnostics", "icon": "mdi:information-outline",
                 "cards": diagnostics},
            ]
        }

    def _heating_sections(self, t, entries, hub, fields, essential, registry, e32_rooms, legacy):
        request = hub.get("heat_request")
        e32_room_entities = self._e32_rooms(entries)
        # One small card says who does what; the mode line follows the E32's own status.
        explain = None
        if request or e32_room_entities:
            content = "**" + t["how_title"] + "**\n\n" + t["how"]
            if request:
                quoted = json.dumps(request)
                content += ("{% set mode = state_attr(" + quoted + ", 'mode') %}"
                            "{% if mode == 'active' %}\n\n" + t["active"]
                            + "{% elif mode == 'shadow' %}\n\n" + t["shadow"] + "{% endif %}")
            # One line for the learning, once, while the E32 reports it.
            learning = next((room["learning"] for room in e32_room_entities.values() if room.get("learning")), None)
            if learning:
                quoted = json.dumps(learning)
                content += ("{% if states(" + quoted + ") not in ['unavailable', 'unknown'] %}\n\n"
                            + t["learning_note"] + "{% if not state_attr(" + quoted + ", 'applied') %} "
                            + t["advice_only"] + "{% endif %}{% endif %}")
            explain = {"type": "markdown", "content": content}
        now = _section(
            _heading(t["now"], "mdi:home-thermometer"),
            _tile(request, t["boiler_request"], "mdi:water-thermometer"),
            _tile(essential("flow"), t["flow"]),
            _tile(hub.get("shadow_agreement_today"), t["agreement"]),
            explain,
            {"type": "button", "name": t["set_up_rooms"], "icon": "mdi:home-edit-outline",
             "tap_action": {"action": "navigate",
                            "navigation_path": "/config/integrations/integration/" + DOMAIN}}
            if e32_rooms else None,
        )
        sections = [now] if len(now["cards"]) > 1 else []
        advice = _advice_section(t, hub.get("heating_advice"))
        if advice:
            sections.append(advice)

        from .heating_link import label
        heating_hub = self._heating_hub()
        for room_id, room in e32_room_entities.items():
            reported = heating_hub.rooms.get(room_id) if heating_hub is not None else None
            name = self._device_name((DOMAIN, f"{self.prefix}_e32_room_{room_id}"),
                                     label(reported) if reported else room_id)
            badges = []
            if room.get("demand"):
                badges.append({"type": "entity", "entity": room["demand"], "show_state": True,
                               "show_icon": True, "color": "deep-orange"})
            if room.get("status"):
                badges.append({"type": "entity", "entity": room["status"], "show_state": True,
                               "show_icon": True, "color": "amber",
                               "visibility": [{"condition": "state", "entity": room["status"],
                                               "state_not": "ok"}]})
            thermostat = self._room_thermostat(room_id)
            state = room.get("state")
            sections.append(_section(
                _heading(name, "mdi:home-thermometer-outline", badges),
                {"type": "thermostat", "entity": thermostat} if thermostat else None,
                _tile(room.get("temperature"), t["measured"]),
                _tile(room.get("setpoint"), t["target"]),
                _tile(state, t["mode"], features=[{"type": "select-options"}]),
                _tile(room.get("inactive_until"), t["off_until"],
                      visibility=[{"condition": "state", "entity": state, "state": "inactive"}] if state else None),
                _tile(room.get("fallback_setpoint"), t["without_ha"],
                      features=[{"type": "numeric-input", "style": "buttons"}]),
            *_learning_cards(t, room),
            ))

        # Older HA rooms (one climate per MQTT room) and their settings.
        legacy_cards = []
        for key in sorted(self._rooms):
            entity_id = registry.async_get_entity_id("climate", DOMAIN, f"{self.prefix}_room_{key}_climate")
            if entity_id is not None:
                legacy_cards.append({"type": "thermostat", "entity": entity_id, "show_current_as_primary": False})
        if not e32_rooms:
            legacy_cards.extend({"type": "button", "name": t["settings"].format(room=sub.title), "icon": "mdi:cog",
                                 "tap_action": {"action": "navigate",
                                                "navigation_path": "/" + self.path + "/room-" + sub.data["room_id"]}}
                                for sub in legacy)
        if legacy_cards:
            sections.append(_section(_heading(t["rooms"], "mdi:thermostat"), *legacy_cards))

        # The E32's decision next to the thermostat's (shadow comparison), only in a home
        # with a thermostat on the bus: the comparison entities exist only once the E32 saw one.
        thermostat = any(key in hub for key in COMPARISON_KEYS)
        compare_entities = [] if not thermostat else [{"entity": entity_id, "name": name} for entity_id, name in (
            (request, t["e32_request"]),
            (fields.get("thermostat_requested_flow_temperature"), t["thermostat_request"]),
            (essential("flow"), t["flow"])) if entity_id]
        history = ({"type": "history-graph", "hours_to_show": 24, "entities": compare_entities}
                   if compare_entities else None)
        heating_time = [hub[key] for key in ("shadow_e32_heating_time_today", "shadow_tado_heating_time_today")
                        if key in hub]
        compare = _section(
            _heading(t["compare"], "mdi:compare-horizontal"),
            history,
            _tile(hub.get("shadow_e32_heating_time_today"), t["heating_time_e32"]),
            _tile(hub.get("shadow_tado_heating_time_today"), t["heating_time_thermostat"]),
            _tile(hub.get("shadow_e32_starts_today"), t["starts_e32"]),
            _tile(hub.get("shadow_tado_starts_today"), t["starts_thermostat"]),
            {"type": "statistics-graph", "title": t["heating_per_day"], "entities": heating_time,
             "stat_types": ["max"], "period": "day", "days_to_show": 7, "chart_type": "bar"}
            if heating_time else None,
        )
        if thermostat and len(compare["cards"]) > 1:
            sections.append(compare)

        # Today's hot-water taps (E32 firmware that sorts them) sit next to the hot water temperature.
        taps = hub.get("dhw_taps_today")
        taps = _tile(taps, t["dhw_taps"], visibility=_known(taps)) if taps else None
        boiler = _section(
            _heading(t["boiler"], "mdi:water-boiler"),
            *(card for key, _, _ in ESSENTIALS
              for card in (_tile(essential(key), t[key]), taps if key == "dhw" else None)),
            _tile(hub.get("burner_starts_last_hour"), t["starts_hour"]),
            _tile(hub.get("burner_short_cycling"), t["short_cycling"]),
        )
        if len(boiler["cards"]) > 1:
            sections.append(boiler)

        ble_cards = []
        for sensor_id, metrics in sorted(self._e32_ble(entries).items()):
            ble_cards.append({
                "type": "glance", "columns": 3, "state_color": False,
                "title": self._device_name((DOMAIN, f"{self.prefix}_e32_ble_{sensor_id}"), sensor_id),
                "entities": [{"entity": metrics[key], "name": t[key]} for key in BLE_KEYS if key in metrics]})
        if ble_cards:
            sections.append(_section(_heading(t["bluetooth"], "mdi:bluetooth"), *ble_cards))
        return sections

    def _boiler_sections(self, t, hub, fields, graph):
        """The boiler view, and the unreliable raw fields (for Diagnostics)."""
        from .boiler_fields import FIELDS, QUALITIES
        field_quality = {field[0]: quality for field, quality in zip(FIELDS, QUALITIES)}
        unreliable = None
        if fields:
            # Native cards only. Reported selected flow is NOT a controller request,
            # and burner modulation percentage is NOT measured kW or power factor.
            rows = {quality: [entity_id for name, entity_id in fields.items()
                              if field_quality.get(name, 1) == quality] for quality in (0, 1, 2)}
            entity_cards = {quality: ({"type": "entities", "title": title, "show_header_toggle": False,
                                       "entities": rows[quality]} if rows[quality] else None)
                            for quality, title in ((0, t["boiler_fields"]), (1, t["unreliable"]),
                                                   (2, t["inferred"]))}
            unreliable = entity_cards[1]
            sections = [
                _section(_heading(t["boiler_fields"], "mdi:water-boiler"),
                         {"type": "markdown", "content": t["boiler_note"]}, entity_cards[0], entity_cards[2]),
                _section(
                    _heading(t["flow_graph"], "mdi:chart-line"),
                    graph(t["flow_graph"], (
                        ("reported_selected_flow_temperature", t["flow_selection"]),
                        ("measured_flow_temperature", t["measured_flow"]),
                        ("measured_return_temperature", t["measured_return"])), fields),
                    graph(t["modulation_graph"], (
                        ("reported_burner_modulation", t["modulation_series"]),), fields),
                    graph(t["dhw_graph"], (
                        ("selected_dhw_temperature", t["dhw_selected"]),
                        ("measured_dhw_temperature", t["dhw_measured"]),
                        ("reported_dhw_target", t["dhw_target"])), fields)),
            ]
        else:
            sections = [_section(
                _heading(t["boiler"], "mdi:water-boiler"),
                {"type": "markdown", "content": t["legacy_boiler_note"]},
                graph(t["flow_graph"], (
                    ("boiler_selected_flow_temperature", t["flow_selection"]),
                    ("boiler_current_flow_temperature", t["current_flow"])), hub),
                graph(t["modulation_graph"], (("boiler_burner_power", t["modulation_series"]),), hub),
                graph(t["states_graph"], (
                    ("boiler_heating_active", t["state_heating"]),
                    ("boiler_hot_water_active", t["state_dhw"]),
                    ("boiler_burner_active", t["state_flame"]),
                    ("boiler_pump_active", t["state_pump"])), hub))]
        # A heading and a note alone are no section.
        return [section for section in sections
                if any(card["type"] not in ("heading", "markdown") for card in section["cards"])], unreliable

    def _diagnostics_cards(self, t, registry, hub, unreliable):
        cards = []
        diagnostic_entities = [hub[metric] for metric in DEVICE_DIAGNOSTIC_METRICS if metric in hub]
        if diagnostic_entities:
            cards.append({"type": "entities", "title": t["device"], "entities": diagnostic_entities})
        ems_entities = [hub[metric] for metric in EMS_METRICS if metric in hub and metric not in {
            "boiler_selected_hot_water_temperature", "boiler_current_hot_water_temperature",
            "boiler_hot_water_flow", "boiler_hot_water_enabled"}]
        ems_entities += [hub[key] for key in hub if key.endswith("_v2") and key[:-3] in EMS_METRICS]
        if ems_entities:
            cards.append({"type": "entities", "title": t["ems"], "entities": ems_entities})
        if unreliable:
            cards.append(unreliable)
        # Native read-only DHW card, driven only by the integration-owned status.
        dhw_id = hub.get("dhw_capabilities")
        note = t["dhw_note"]
        if dhw_id:
            quoted = json.dumps(dhw_id)
            note += ("\n\n" + t["dhw_profile"] + ": {{ state_attr(" + quoted + ", 'profile') or '"
                     + t["unknown"] + "' }}; " + t["dhw_status"] + ": {{ states(" + quoted + ") }}.\n"
                     "{% set fields = state_attr(" + quoted + ", 'fields') or {} %}"
                     "{% for key, field in fields.items() %}{% if field.supported_read %}"
                     "\n- {{ key | replace('_', ' ') }}: {{ field.value if field.value is not none else '"
                     + t["unknown"] + "' }} {{ field.unit or '' }} ({{ field.quality }}){% endif %}{% endfor %}")
            cards.append({"type": "entities", "title": t["dhw_card"], "entities": [dhw_id]})
        else:
            note += " " + t["dhw_none"]
        cards.append({"type": "markdown", "content": note})
        # Today's taps, keeping warm and burner time, as the E32 sorts them on the bus.
        dhw_today = [hub[key] for key in DHW_TODAY if key in hub]
        if dhw_today:
            cards.append({"type": "entities", "title": t["dhw_today"], "entities": dhw_today})
        # Estimates: only isolated definition-v2 IDs, no legacy counter aggregates or backfill.
        counter_keys = ("energy", "energy_heating", "energy_warm_water", "energy_unattributed",
                        "warm_water_usage", "burner_observed_time")
        counters = [hub[key + "_v2"] for key in counter_keys if key + "_v2" in hub]
        charts = []
        for title, keys in (
            (t["energy_chart"], ("energy", "energy_heating", "energy_warm_water", "energy_unattributed")),
            (t["volume_chart"], ("warm_water_usage",)),
            (t["flame_chart"], ("burner_observed_time",)),
        ):
            entities = [hub[key + "_v2"] for key in keys if key + "_v2" in hub]
            if entities:
                charts.append({"type": "statistics-graph", "title": title, "entities": entities,
                               "days_to_show": 7, "period": "day", "chart_type": "bar",
                               "stat_types": ["change"]})
        if counters:
            cards.append({"type": "markdown", "content": t["estimates_note"]})
            cards.append({"type": "entities", "title": t["counters"], "entities": counters})
        cards.extend(charts)
        # Older HA rooms: heat model estimates and target / measured history, by room name.
        devices = dr.async_get(self.hass)
        model_cards = []
        for key in sorted(self._rooms):
            device = devices.async_get_device_by_identifier((DOMAIN, f"{self.prefix}_room_{key}"), self.entry_id)
            name = (device.name_by_user or device.name) if device is not None else key
            heating_entities = []
            for platform, suffix in (
                ("binary_sensor", "radiator_heating"),
                ("sensor", "radiator_heating_time"),
                ("sensor", "radiator_estimated_power"),
                ("sensor", "radiator_estimated_energy"),
                ("number", "radiator_power"),
            ):
                definition_suffix = "" if platform == "number" else "_v2"
                entity_id = registry.async_get_entity_id(
                    platform, DOMAIN, f"{self.prefix}_room_{key}_{suffix}{definition_suffix}")
                if entity_id is not None:
                    heating_entities.append(entity_id)
            if heating_entities:
                model_cards.append({"type": "entities", "title": name, "entities": heating_entities})
            history = []
            for metric, label in (("temperature", t["room_measured"]), ("temperature_set", t["room_target"])):
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{self.prefix}_room_{key}_{metric}")
                if entity_id:
                    history.append({"entity": entity_id, "name": label})
            if history:
                model_cards.append({"type": "history-graph", "title": t["room_history"].format(room=name),
                                    "hours_to_show": 24, "entities": history})
        if model_cards:
            cards.append({"type": "markdown", "content": t["models_note"]})
            cards.extend(model_cards)
        return cards
