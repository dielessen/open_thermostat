"""Optional, integration-managed Lovelace dashboard for thermostat rooms.

The views, built from the entity registry (renamed entity IDs are followed,
disabled and absent entities are left out) with built-in cards, the week
planner and, per room, the room status card (frontend/room-status-card.js):

* Overview (first): the House section headed by the house card
  (custom:openthermostat-house: what the boiler does now in a band of its
  colour, today's hot water, gas and burner starts as large figures, a problem
  with its reason that leads to Repairs, and the one room that is on; the day so
  far; without a heat request and boiler activity there is no card,
  and the rooms that want heat with the boiler request and the problem tile
  stand there instead), the house mode and the next holiday; then one status
  card per other room: temperature against target and, in one line, why it
  heats or not. Nothing else;
* Rooms: per room its thermostat, 24-hour graph, sensors, windows and people,
  and what it learned for that room; then the sensors that feed no single room;
* Week program (with an E32 room plan): the visual week planner card;
* Boiler, in this order: Now (what the boiler does in words and as one coloured
  tile: heating, hot water or resting; the water to the heating and back; the
  burner power and its starts per hour), the heating advice, Today and this week
  (today's gas and burner as figures, the one chart of the gas per day and the
  burner hours per day), Hot water (its temperature and target, today's taps and
  keeping warm, what the boiler did in the last 24 hours), the last 24 hours,
  What the boiler reports (its values in groups) and the boiler settings. The
  thermostat on the bus and the raw boiler data are on Diagnostics;
* Learning and settings, in the order of the owner's sketch (rc.5): what the
  E32 knows (the knowledge ring and what it still learns), your boiler (its
  response in one sentence), water temperature by outdoor temperature (the
  curve), yesterday in figures (the four headline figures large on their own
  card, custom:openthermostat-yesterday, then the rest of the scoreboard and the
  daily summary, once), what stood out yesterday compared with usual, the free
  heat per room, and Smart warm-up and Weather compensation as rows; then what
  the thermostat learned (house and boiler, its own changes, how it learns) and
  who controls the boiler (short cycling as information, the takeover check).
  On a wide screen the sketch's two columns: the curve with what stood out and
  the free heat under it beside your boiler, yesterday and the settings;
* Diagnostics (last): the E32 itself, the thermostat on the boiler bus, the
  energy and hot water counters, the raw boiler data and the hot water capability;
* Comparison (subview, trial run with a thermostat on the bus only).

Layout: every view is sections; a section hides as a whole while nothing in it
has a value, so a heading never stands over nothing; a card is as wide as its
section, or one of a tidy pair of half-width cards (tiles, figures, a gauge) that
appear together on one condition (never one half card alone); a note is one
sentence with the rest behind "More"; a card whose text can change is one card
instead of cards that come and go; one icon per concept (ICONS).

Rows, tiles and graphs without a value stay hidden until they have one, so a
boiler that never reports a value shows no "Unknown" for it.

A stored Lovelace config has no per-viewer language, so the few fixed
headings follow the Home Assistant language (English, Dutch or Polish) and the
dashboard is rebuilt when that changes. Entity names come from Home
Assistant's own translations.
"""

import asyncio
import json
import logging
import re

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceStorage
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import slugify

from .const import DOMAIN
from .e32_flow import CURVE_CARD_TYPE, KNOWLEDGE_CARD_TYPE
from .product import is_product
from .week_planner import ROOM_CARD_TYPE

E32_WEEK_CARD_TYPE = "custom:openthermostat-e32-week"
# Per room (1.1): temperature against target and why it heats or not, from the room's Reason sensor.
ROOM_STATUS_CARD_TYPE = "custom:openthermostat-room-status"

_LOGGER = logging.getLogger(__name__)
# Registry and language changes come in bursts (a start creates every entity one by one): one rebuild
# once they settled this long after the first (R4-11).
REGISTRY_SETTLE_SECONDS = 2

DEVICE_DIAGNOSTIC_METRICS = (
    "connected",
    "memory_free",
    "memory_min_free",
    "memory_max_alloc",
    "rtc_temperature",
    "cpu_temperature",
    "uptime",
)

# The groups of boiler fields (boiler_group) under "What the boiler reports" on the Boiler view, one titled card
# each, in this order. The settings are a section of their own (last on that view); the thermostat on the bus and
# the raw group (unreliable raw values) are on Diagnostics (dashboard-spec §5.6, §5.7, §8).
REPORTED_GROUPS = ("heating", "dhw", "status", "counters")
STATUS_FIELDS = frozenset({"display_code", "service_number", "maintenance_message", "ionisation_current",
                           "plus_flame_current"})
SETTINGS_FIELDS = frozenset({"maximum_burner_power", "pump_run_on", "minimum_burner_period", "pump_modulation_maximum",
                             "pump_modulation_minimum", "pump_start_temperature", "dhw_charge_optimisation_enabled",
                             "dhw_flow_temperature_offset", "dhw_circulation_enabled", "dhw_disinfection_temperature",
                             "reported_dhw_type", "plus_heating_temperature", "plus_maximum_burner_power"})
# The energy and hot water counters (definition v2; only boilers that report them fill these in).
COUNTER_KEYS = ("energy", "energy_heating", "energy_warm_water", "energy_unattributed", "warm_water_usage",
                "warm_water_avg_flow", "burner_observed_time")


def boiler_group(name):
    """The Boiler view group of boiler field ``name``; "raw" for the unreliable raw values (Diagnostics)."""
    from .boiler_fields import INDEX_BY_NAME, quality
    index = INDEX_BY_NAME.get(name)
    if (index is not None and quality(index) == 1) or name.startswith("raw_"):
        return "raw"
    if name.startswith("thermostat_"):
        return "thermostat"
    if name in STATUS_FIELDS or name.startswith("last_"):
        return "status"
    if name.endswith(("_starts", "_runtime")) or name == "boiler_uptime":
        return "counters"
    if name.startswith("configured_") or "hysteresis" in name or name in SETTINGS_FIELDS:
        return "settings"
    if "dhw" in name or name.startswith(("storage_", "solar_")):
        return "dhw"
    return "heating"

# E32 room entities: unique ID f"{prefix}_e32_room_{room id}_{key}" (longest key first).
ROOM_KEYS = ("valve_position", "valve_battery", "valve_problem", "valve_control", "fallback_setpoint", "inactive_until", "heating_start", "flow_advice", "temperature", "thermostat",
             "learning", "reason", "warm_on_time", "overshoot",
             "setpoint", "status", "demand", "state")
# Yesterday's scoreboard of the house (scoreboard.py, E32 rc.4): unique ID f"{prefix}_hub_{key}".
SCOREBOARD_HOUSE = ("burner_starts_per_heating_hour", "short_cycling_hours", "heating_gas_yesterday", "gas_per_degree_day")
# Today's hot water from the E32 (unique ID f"{prefix}_hub_{key}").
DHW_TODAY = ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today")
BLE_KEYS = ("temperature", "humidity", "battery")

# Boiler essentials: (key, boiler field, older hub metric).
ESSENTIALS = (
    ("flow", "measured_flow_temperature", "boiler_current_flow_temperature"),
    ("return", "measured_return_temperature", None),
    ("max_ch", "configured_heating_temperature", None),
    ("modulation", "reported_burner_modulation", "boiler_burner_power"),
    ("pressure", "pressure", "boiler_pressure"),
    ("dhw", "measured_dhw_temperature", "boiler_current_hot_water_temperature"),
    ("code", "display_code", "boiler_display_code"),
)

# Weather compensation and learning on the product device (e32_flow.py): unique ID f"{prefix}_flow_{key}";
# "curve" is what weather compensation asks now, which the heating-curve card draws (E32 rc.5).
FLOW_KEYS = ("source", "weather_curve", "curve_design_flow_c", "apply_learned", "curve")
COMPARISON_PATH = "comparison"
# One icon per concept, the same in every view (dashboard-spec §1): the boiler's values, what the boiler does
# (heating flame, hot water tap, resting boiler), the gas and the burner, and the sections that carry them.
ICONS = {"flow": "mdi:thermometer-chevron-up", "return": "mdi:thermometer-chevron-down",
         "max_ch": "mdi:thermometer-high", "modulation": "mdi:fire", "pressure": "mdi:gauge",
         "dhw": "mdi:water-thermometer", "dhw_target": "mdi:thermometer-water", "code": "mdi:information-outline",
         "heating": "mdi:fire", "hot_water": "mdi:faucet", "gas": "mdi:meter-gas", "burner_starts": "mdi:counter",
         "burner_time": "mdi:timer-outline", "house": "mdi:home-thermometer", "learning": "mdi:school-outline",
         "boiler": "mdi:water-boiler", "now": "mdi:water-boiler", "week": "mdi:chart-bar",
         "history": "mdi:chart-line", "settings": "mdi:cog-outline", "yesterday": "mdi:scoreboard-outline",
         "thermostat": "mdi:thermostat", "knowledge": "mdi:home-analytics", "curve": "mdi:chart-bell-curve-cumulative",
         "insight": "mdi:information-outline", "free_heat": "mdi:weather-sunny"}
# The sketch's coloured icons in a markdown line (_icon), in the colours of Home Assistant's default theme: heating
# (--state-climate-heat-color, deep orange), information (--info-color) and the sun (--amber-color).
ICON_COLOURS = {"heating": "#ff6f22", "insight": "#039be5", "free_heat": "#ffc107"}
# What the boiler does now (hub boiler_activity, heating_link.BOILER_ACTIVITIES) as one tile of three: its icon
# (ICONS), its theme colour and the activities it stands for; exactly one shows at a time.
ACTIVITY_TILES = (("heating", "deep-orange", ["heating"]),
                  ("hot_water", "blue", ["tapping", "keep_warm", "charging", "hot_water"]),
                  ("boiler", "grey", ["idle"]))

TEXT = {
    "en": {
        "heating": "Heating", "boiler_view": "Boiler", "diagnostics": "Diagnostics",
        "room_settings": "Room settings", "now": "Now", "rooms": "Rooms", "set_up_rooms": "Set up rooms", "week_program": "Week program",
        "settings": "{room} settings",
        "boiler_request": "Boiler request", "flow": "Water to heating (flow)", "return": "Water back (return)",
        "modulation": "Burner power", "pressure": "Pressure", "dhw": "Hot water", "code": "Display code",
        "max_ch": "Boiler maximum", "status": "Status", "problem": "Heating",
        "starts_hour": "Starts per hour", "short_cycling": "Switching on and off too often",
        "agreement": "Agreement with thermostat", "measured": "Measured by E32", "target": "Target temperature",
        "valve_position": "Valves open",
        "mode": "Mode", "off_until": "Off until", "without_ha": "Temperature without Home Assistant",
        "compare": "E32 and thermostat", "e32_request": "Boiler request E32",
        "thermostat_request": "Thermostat request", "heating_time_e32": "Heating time E32",
        "heating_time_thermostat": "Heating time thermostat", "starts_e32": "Starts E32",
        "starts_thermostat": "Starts thermostat", "heating_per_day": "Heating time per day",
        "boiler": "Boiler", "bluetooth": "Bluetooth sensors", "temperature": "Temperature",
        "humidity": "Humidity", "battery": "Battery",
        "shadow": "Trial run: the E32 calculates along but does not control the boiler yet; your current "
                  "thermostat or the boiler's own control stays in charge.",
        "active": "The E32 controls the boiler.",
        "next": "Next step: run the boiler test and confirm the takeover on the E32 Rooms page. Until then the E32 "
                "sends nothing to the boiler.",
        "how": "The E32 keeps your rooms running, also without Home Assistant.",
        "overview": "Overview",
        "room_nothing": "Nothing learned yet.",
        "house": "House",
        "learning_view": "Learning and settings",
        "more": "More",
        "sensors_presence": "Sensors, windows and people",
        "smart_heating": "Smart warm-up and weather compensation",
        "cycling_ok": "The burner runs calmly.",
        "cycling_info": "The E32 lengthens the burner rest step by step.",
        "burner": "Burner",
        "problem_more": "All reasons",
        "legacy_rooms": "Rooms (older setup)",
        "group_heating": "Heating", "group_dhw": "Hot water", "group_status": "Status and faults",
        "group_counters": "Counters", "group_settings": "Boiler settings",
        "group_thermostat": "Thermostat on the bus", "history_24h": "Last 24 hours",
        "boiler_note": "Values as the boiler reports them; a value the boiler does not send is left out. "
                       "Burner power is a percentage of the boiler's maximum, not kW; \"active\" is what the boiler "
                       "reports, not a separate check.",
        "settings_note": "Settings the boiler reports only when asked are read at start-up and every six hours; the "
                         "time of the last reading is on the sensor.",
        "raw": "Raw boiler data",
        "raw_note": "For troubleshooting: values exactly as the boiler sends them, not checked by the E32.",
        "e32_device": "E32",
        "estimates": "Energy and hot water counters",
        "estimates_empty": "This boiler reports no energy or hot water counters yet; boilers that do (EMS+) fill "
                           "them in here. The Boiler tab and the E32's Home page estimate the gas per day from "
                           "the burner power and the boiler's power.",
        "older_rooms": "Rooms (older setup)",
        "legacy_boiler_note": "What the boiler reports over its bus (EMS), not proof of an E32 command. Unknown or old values are not zero.",
        "flow_graph": "Water temperatures: target, to heating and back", "flow_selection": "Target (boiler)",
        "measured_flow": "To heating (flow)", "measured_return": "Back (return)",
        "current_flow": "To heating, as the boiler reports it",
        "modulation_graph": "Burner power (%) — not kW", "modulation_series": "Burner power (%)",
        "dhw_graph": "Hot water temperatures", "dhw_selected": "Reported selected hot water",
        "dhw_measured": "Measured hot water", "dhw_target": "Reported hot water target",
        "states_graph": "Reported heating / hot water / flame / pump", "state_heating": "Reported heating",
        "state_dhw": "Reported hot water", "state_flame": "Reported flame bit", "state_pump": "Reported pump bit",
        "dhw_card": "Hot water capability and quality",
        "dhw_note": "Hot water, view only: the last values the boiler reported (their age is not checked); "
                    "nothing is sent to the boiler.",
        "dhw_profile": "Profile", "dhw_status": "status", "unknown": "Unknown",
        "estimates_note": "Energy and volume are estimates from reported values, not gas or heat meters.",
        "energy_chart": "Estimated energy per day (not a meter)", "volume_chart": "Hot water volume per day",
        "flame_chart": "Observed flame time per day",
        "models_note": "Room heat models are estimates, not measured heat; unknown or stale inputs leave gaps.",
        "room_history": "{room}: target and measured", "room_measured": "Measured", "room_target": "Target",
        "learning": "Learning", "flow_advice": "Recommended water temperature", "heating_start": "Heating starts",
        "learning_note": "The E32 also learns how fast each room warms up and works out the coolest water "
                         "that still warms the room 1 °C in time (the recommended water temperature).",
        "advice_only": "For now this is advice only; the E32 keeps using its room control.",
        "dhw_taps": "Taps today", "dhw_today": "Hot water today",
        "advice": "Advice", "advice_where": "Where", "advice_confidence": "Confidence",
        "advice_note": "Advice only: nothing is changed automatically.",
        "learned": "What the thermostat has learned", "learned_house": "House and boiler",
        "learned_changes": "What it changed by itself",
        "learned_note": "The thermostat adjusts these settings itself; to change one: Configure → Heating and boiler → Comfort and boiler care "
                        "(or the E32 page, Home).",
        "confidence_low": "low", "confidence_medium": "medium", "confidence_high": "high",
        "gas_heating": "Heating", "gas_hot_water": "Hot water", "gas_keep_warm": "Of which keeping hot water warm",
        "gas_tapping": "Tapping", "gas_keeping_warm": "Keeping warm",
        "activity_timeline": "What the boiler does (24 hours)", "activity": "Boiler",
        "dhw_use_note": "Tapping is hot water used at a tap; keeping warm is the boiler reheating its store or "
                        "exchanger without a tap, nothing more; a cylinder shows as charging. The E32 tells them apart "
                        "with the most direct signal your boiler reports.",
        "gas_per_day": "Gas per day",
        "gas_measured": "Measured with your gas meter, split by what the boiler did.",
        "gas_estimate": "Estimated from the burner power and the boiler's heating power (no gas meter).",
        "gas_note": "Add heating and hot water to the Energy dashboard under Gas consumption; keeping warm is a part of hot water, so leave it out there.",
        "yesterday": "Yesterday", "burner_per_day": "Burner hours per day",
        "missed_per_day": "Missed comfort per day (minutes)",
        "day_burner": "Burner {h} h, {n} starts ({short} shorter than 10 minutes).",
        "day_gas": "Gas: heating {heating}, hot water {hot_water}.",
        "day_room": "{room}: asked for heat {h} h; warm after {ttt} min on average; missed comfort {missed} min.",
        "day_room_no_step": "{room}: asked for heat {h} h; missed comfort {missed} min.",
        "day_outdoor": "Outdoor {low} to {high} °C.",
        "day_partial": "Partial day: the E32 was not heard all day, so the figures are incomplete.",
        "scoreboard_on_time": "warm on time",
        "scoreboard_late": "warm {m} min late",
        "scoreboard_early": "warm {m} min early",
        "scoreboard_overshoot": "{c} °C too warm",
        "scoreboard_hours": "Heating time: {h} h",
        "scoreboard_burner": "Burner starts per heating hour: {n}",
        "scoreboard_short": "Short burner runs: {h} h",
        "scoreboard_gas": "Gas for heating (estimate): {kwh} kWh",
        "scoreboard_degree_days": "Degree-days: {d}",
        "scoreboard_degree_day": "{v} kWh per degree-day",
        "scoreboard_note": "Every day the thermostat checks whether each room was warm on time without getting too warm, how often the burner started and how much gas went to heating. It learns from this; every figure keeps its history on its own sensor.",
        "day_none": "The first full day appears here tomorrow.",
        "outdoor": "Outdoor",
        "flow_settings": "Weather compensation and learning",
        "flow_source": "Water temperature set by",
        "weather_curve": "Weather compensation",
        "design_flow": "Water temperature in hard frost (−10 °C)",
        "apply_learned": "Smart warm-up",
        "house_mode": "House mode", "boiler_now": "Boiler",
        # rc.4: the next holiday under House (house.holidays.v1).
        "holiday_next": "Holiday from {from} to {until}", "holiday_now": "On holiday until {until}",
        "months": "Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
        "learned_latest": "Latest change",
        "compare_link": "E32 compared with your thermostat",
        "no_request": "No boiler request",
        "wanting_one": "1 room wants heat", "wanting_many": "{n} rooms want heat", "wanting_none": "No room wants heat",
        "decimal": ".",
        "flow_short": "Water to heating", "return_short": "Water back",
        "e32": "E32", "thermostat": "Thermostat",
        "comparison_view": "Comparison",
        "room_off": "This room is off and never asks for heat.",
        "room_no_source": "{room} is off and has no working temperature source. Choose a source to "
            "use it again, or remove the room if you no longer need it.",
        "choose_source": "Choose a source",
        "remove_room": "Remove room",
        "readiness": "Ready to take over?",
        "ready_ready": "Ready: follow the switch-over steps.",
        "ready_waiting": "Not yet: the E32 is still collecting data in the trial run.",
        "ready_not_ready": "Not ready: fix the red items first.",
        "ready_no_comparison": "No thermostat on the boiler bus to compare with, so only the E32 and the boiler "
            "are checked.",
        "ready_stable": "Stable: {stable_hours} of {stable_hours_needed} h without a hang or unexpected restart",
        "ready_periods": "Heating periods compared: {periods_compared} of {periods_needed}, with a night setback, "
            "a morning warm-up and a period without demand",
        "ready_timing": "Heat at the same moments: {timing_events} of {timing_events_needed} starts and stops",
        "ready_flow_limit": "Water temperature request never above the limit: highest {flow_max_c} °C, limit {flow_limit_c} °C",
        "ready_cycling": "Not more heating periods than the thermostat: E32 {heating_periods_e32}, "
            "thermostat {heating_periods_thermostat}",
        "ready_sources": "Room sources work, and a backup sensor has taken over",
        "ready_boiler": "Boiler heard on the bus",
        "ready_boiler_limit": "Boiler maximum known: {boiler_limit_c} °C",
        "fix_timing": "The E32 heats at other moments than your thermostat: check the room targets and week program.",
        "fix_flow_limit": "A request went above the hard limit: check the water temperature limits.",
        "fix_cycling": "The E32 would start the burner more often: check the water temperature limits.",
        "fix_sources": "Check the room sensors (battery, range) and give a room a second source.",
        "fix_boiler": "The E32 hears nothing from the boiler: check the bus cable.",
        "fix_boiler_limit": "The boiler has not reported its maximum: check the bus connection.",
        # rc.5 dashboard (dashboard-spec §1): the Boiler view's sections and today's figures, Yesterday once on the
        # Learning view and who controls the boiler.
        "today_week": "Today and this week", "gas_heating_today": "Heating gas",
        "gas_hot_water_today": "Hot water gas", "starts_today": "Burner starts",
        "burner_today": "Burner time", "boiler_values": "What the boiler reports",
        "who_controls": "Who controls the boiler", "yesterday_figures": "Yesterday in figures",
        "dhw_target_short": "Hot water target",
        # E32 rc.5, the Learning view as the owner's sketch: what the E32 knows, your boiler (its response in one
        # sentence), water temperature by outdoor temperature, what stood out yesterday (insight.py), the free heat.
        "knowledge": "What the E32 knows", "your_boiler": "Your boiler",
        "curve_title": "Water temperature by outdoor temperature", "noticed": "Noticed",
        "noticed_note": "Yesterday is compared with your house's own usual days; that is information and changes nothing.",
        "free_heat": "Free heat",
        # rc.5 (P11): the Overview's rooms beside the one room the house card shows.
        "other_rooms": "Other rooms",
    },
    "nl": {
        "heating": "Verwarming", "boiler_view": "Ketel", "diagnostics": "Diagnose",
        "room_settings": "Ruimte-instellingen", "now": "Nu", "rooms": "Ruimtes", "set_up_rooms": "Ruimtes instellen", "week_program": "Weekprogramma",
        "settings": "Instellingen {room}",
        "boiler_request": "Ketelvraag", "flow": "Water naar verwarming (aanvoer)", "return": "Water terug (retour)",
        "modulation": "Brandervermogen", "pressure": "Waterdruk", "dhw": "Warm water", "code": "Displaycode",
        "max_ch": "Ketelmaximum", "status": "Status", "problem": "Verwarming",
        "starts_hour": "Starts per uur", "short_cycling": "Te vaak aan en uit",
        "agreement": "Overeenstemming met thermostaat", "measured": "Gemeten door E32",
        "valve_position": "Kranen open",
        "target": "Gewenste temperatuur", "mode": "Stand", "off_until": "Uit tot",
        "without_ha": "Temperatuur zonder Home Assistant",
        "compare": "E32 en thermostaat vergeleken", "e32_request": "Ketelvraag E32",
        "thermostat_request": "Vraag thermostaat", "heating_time_e32": "Stooktijd E32",
        "heating_time_thermostat": "Stooktijd thermostaat", "starts_e32": "Starts E32",
        "starts_thermostat": "Starts thermostaat", "heating_per_day": "Stooktijd per dag",
        "boiler": "Ketel", "bluetooth": "Bluetooth-sensoren", "temperature": "Temperatuur",
        "humidity": "Luchtvochtigheid", "battery": "Batterij",
        "shadow": "Proefperiode: de E32 rekent mee maar stuurt de ketel nog niet; je huidige thermostaat of de "
                  "eigen regeling van de ketel blijft de baas.",
        "active": "De E32 regelt de ketel.",
        "next": "Volgende stap: doe de keteltest en bevestig de overname op de E32-pagina Ruimtes. Tot dan stuurt "
                "de E32 niets naar de ketel.",
        "how": "De E32 houdt je ruimtes op temperatuur, ook zonder Home Assistant.",
        "overview": "Overzicht",
        "room_nothing": "Nog niets geleerd.",
        "house": "Huis",
        "learning_view": "Leren en instellingen",
        "more": "Meer",
        "sensors_presence": "Sensoren, ramen en personen",
        "smart_heating": "Slim opwarmen en weerafhankelijke regeling",
        "cycling_ok": "De brander loopt rustig.",
        "cycling_info": "De E32 verlengt de rusttijd van de brander stap voor stap.",
        "burner": "Brander",
        "problem_more": "Alle redenen",
        "legacy_rooms": "Ruimtes (oudere opzet)",
        "group_heating": "Verwarming", "group_dhw": "Warm water", "group_status": "Status en storingen",
        "group_counters": "Tellers", "group_settings": "Ketelinstellingen",
        "group_thermostat": "Thermostaat op de bus", "history_24h": "Afgelopen 24 uur",
        "boiler_note": "Waarden zoals de ketel ze meldt; een waarde die de ketel niet stuurt, staat er niet. "
                       "Brandervermogen is een percentage van het maximum van de ketel, geen kW; \"actief\" is wat de ketel "
                       "meldt, geen aparte controle.",
        "settings_note": "Instellingen die de ketel alleen op verzoek meldt, leest de E32 bij het opstarten en daarna "
                         "elke zes uur; wanneer ze voor het laatst zijn gelezen staat op de sensor.",
        "raw": "Ruwe keteldata",
        "raw_note": "Voor het zoeken naar fouten: waarden precies zoals de ketel ze stuurt, niet gecontroleerd "
                    "door de E32.",
        "e32_device": "E32",
        "estimates": "Tellers voor energie en warm water",
        "estimates_empty": "Deze ketel meldt nog geen tellers voor energie of warm water; ketels die dat wel doen "
                           "(EMS+) vullen ze hier in. Het tabblad Ketel en de pagina Huis van de E32 schatten het "
                           "gas per dag uit het brandervermogen en het vermogen van de ketel.",
        "older_rooms": "Ruimtes (oudere opzet)",
        "legacy_boiler_note": "Wat de ketel via zijn bus (EMS) meldt, geen bewijs van een E32-opdracht. Onbekende of "
                              "oude waarden zijn geen nul.",
        "flow_graph": "Watertemperaturen: doel, naar verwarming en terug", "flow_selection": "Doel (ketel)",
        "measured_flow": "Naar verwarming (aanvoer)", "measured_return": "Terug (retour)",
        "current_flow": "Naar verwarming, zoals de ketel meldt",
        "modulation_graph": "Brandervermogen (%) — geen kW", "modulation_series": "Brandervermogen (%)",
        "dhw_graph": "Warmwatertemperaturen", "dhw_selected": "Gemeld gekozen warm water",
        "dhw_measured": "Gemeten warm water", "dhw_target": "Gemeld warmwaterdoel",
        "states_graph": "Gemeld verwarmen / warm water / vlam / pomp", "state_heating": "Gemeld verwarmen",
        "state_dhw": "Gemeld warm water", "state_flame": "Gemelde vlambit", "state_pump": "Gemelde pompbit",
        "dhw_card": "Warmwatermogelijkheden en kwaliteit",
        "dhw_note": "Warm water, alleen bekijken: de laatste waarden die de ketel meldde (hun leeftijd wordt niet gecontroleerd); "
                    "er gaat niets naar de ketel.",
        "dhw_profile": "Profiel", "dhw_status": "status", "unknown": "Onbekend",
        "estimates_note": "Energie en volume zijn schattingen uit gemelde waarden, geen gas- of warmtemeter.",
        "energy_chart": "Geschatte energie per dag (geen meter)", "volume_chart": "Warmwatervolume per dag",
        "flame_chart": "Waargenomen vlamtijd per dag",
        "models_note": "Warmtemodellen per ruimte zijn schattingen, geen gemeten warmte; onbekende of verouderde "
                       "invoer laat gaten.",
        "room_history": "{room}: gewenst en gemeten", "room_measured": "Gemeten", "room_target": "Gewenst",
        "learning": "Leren", "flow_advice": "Geadviseerde watertemperatuur", "heating_start": "Start verwarmen",
        "learning_note": "De E32 leert ook hoe snel elke ruimte opwarmt en berekent de laagste "
                         "watertemperatuur die de ruimte nog op tijd 1 °C opwarmt (de geadviseerde watertemperatuur).",
        "advice_only": "Voorlopig is dat alleen advies; de E32 blijft zijn ruimteregeling gebruiken.",
        "dhw_taps": "Tappen vandaag", "dhw_today": "Warm water vandaag",
        "advice": "Advies", "advice_where": "Waar", "advice_confidence": "Zekerheid",
        "advice_note": "Alleen advies: er wordt niets automatisch veranderd.",
        "learned": "Wat de thermostaat heeft geleerd", "learned_house": "Huis en ketel",
        "learned_changes": "Wat hij zelf heeft aangepast",
        "learned_note": "De thermostaat past deze instellingen zelf aan; wijzigen kan onder Configureren → Verwarming en ketel → Comfort en "
                        "zorg voor de ketel (of op de E32-pagina, Huis).",
        "confidence_low": "laag", "confidence_medium": "middel", "confidence_high": "hoog",
        "gas_heating": "Verwarmen", "gas_hot_water": "Warm water", "gas_keep_warm": "Waarvan warm water warmhouden",
        "gas_tapping": "Tappen", "gas_keeping_warm": "Warmhouden",
        "activity_timeline": "Wat de ketel doet (24 uur)", "activity": "Ketel",
        "dhw_use_note": "Tappen is warm water uit een kraan; warmhouden is de ketel die zijn voorraad of "
                        "warmtewisselaar opwarmt zonder dat er getapt wordt, meer niet; een boiler toont als laden. De E32 "
                        "houdt ze uit elkaar met het meest directe signaal dat je ketel geeft.",
        "gas_per_day": "Gas per dag",
        "gas_measured": "Gemeten met je gasmeter, verdeeld naar wat de ketel deed.",
        "gas_estimate": "Geschat uit het brandervermogen en het vermogen van de ketel (geen gasmeter).",
        "gas_note": "Voeg verwarmen en warm water toe aan het energiedashboard onder Gasverbruik; warmhouden is een deel van warm water, laat dat daar weg.",
        "yesterday": "Gisteren", "burner_per_day": "Branderuren per dag",
        "missed_per_day": "Gemiste comfort per dag (minuten)",
        "day_burner": "Brander {h} uur, {n} starts ({short} korter dan 10 minuten).",
        "day_gas": "Gas: verwarmen {heating}, warm water {hot_water}.",
        "day_room": "{room}: vroeg {h} uur warmte; gemiddeld na {ttt} min op temperatuur; gemiste comfort {missed} min.",
        "day_room_no_step": "{room}: vroeg {h} uur warmte; gemiste comfort {missed} min.",
        "day_outdoor": "Buiten {low} tot {high} °C.",
        "day_partial": "Gedeeltelijke dag: de E32 was niet de hele dag te horen, dus de cijfers zijn onvolledig.",
        "scoreboard_on_time": "op tijd warm",
        "scoreboard_late": "{m} min te laat warm",
        "scoreboard_early": "{m} min te vroeg warm",
        "scoreboard_overshoot": "{c} °C te warm",
        "scoreboard_hours": "Stooktijd: {h} u",
        "scoreboard_burner": "Branderstarts per stookuur: {n}",
        "scoreboard_short": "Korte brandtijden: {h} u",
        "scoreboard_gas": "Gas voor verwarming (schatting): {kwh} kWh",
        "scoreboard_degree_days": "Graaddagen: {d}",
        "scoreboard_degree_day": "{v} kWh per graaddag",
        "scoreboard_note": "Elke dag kijkt de thermostaat of elke ruimte op tijd warm was zonder te warm te worden, hoe vaak de brander startte en hoeveel gas naar verwarmen ging. Hij leert daarvan; elk getal houdt zijn geschiedenis bij op zijn eigen sensor.",
        "day_none": "Morgen staat hier de eerste volledige dag.",
        "outdoor": "Buiten",
        "flow_settings": "Weerafhankelijke regeling en leren",
        "flow_source": "Watertemperatuur bepaald door",
        "weather_curve": "Weerafhankelijke regeling",
        "design_flow": "Watertemperatuur bij strenge vorst (−10 °C)",
        "apply_learned": "Slim opwarmen",
        "house_mode": "Huismodus", "boiler_now": "Ketel",
        "holiday_next": "Vakantie vanaf {from} t/m {until}", "holiday_now": "Op vakantie t/m {until}",
        "months": "jan,feb,mrt,apr,mei,jun,jul,aug,sep,okt,nov,dec",
        "learned_latest": "Laatste aanpassing",
        "compare_link": "E32 vergeleken met je thermostaat",
        "no_request": "Geen ketelvraag",
        "wanting_one": "1 ruimte vraagt warmte", "wanting_many": "{n} ruimtes vragen warmte",
        "wanting_none": "Geen ruimte vraagt warmte", "decimal": ",",
        "flow_short": "Aanvoerwater", "return_short": "Retourwater",
        "e32": "E32", "thermostat": "Thermostaat",
        "comparison_view": "Vergelijking",
        "room_off": "Deze ruimte staat uit en vraagt nooit warmte.",
        "room_no_source": "{room} staat uit en heeft geen werkende temperatuurbron. Kies een bron "
            "om de ruimte weer te gebruiken, of verwijder hem als je hem niet meer nodig hebt.",
        "choose_source": "Kies een bron",
        "remove_room": "Ruimte verwijderen",
        "readiness": "Klaar om over te nemen?",
        "ready_ready": "Klaar: volg de stappen voor de overschakeling.",
        "ready_waiting": "Nog niet: de E32 verzamelt nog gegevens in de proefperiode.",
        "ready_not_ready": "Niet klaar: los eerst de rode punten op.",
        "ready_no_comparison": "Geen thermostaat op de ketelbus om mee te vergelijken, dus alleen de E32 en de "
            "ketel worden gecontroleerd.",
        "ready_stable": "Stabiel: {stable_hours} van {stable_hours_needed} uur zonder vastloper of onverwachte herstart",
        "ready_periods": "Verwarmingsperiodes vergeleken: {periods_compared} van {periods_needed}, met een "
            "nachtverlaging, een ochtendopwarming en een periode zonder vraag",
        "ready_timing": "Warmte op dezelfde momenten: {timing_events} van {timing_events_needed} starts en stops",
        "ready_flow_limit": "Gevraagde watertemperatuur nooit boven de grens: hoogste {flow_max_c} °C, grens {flow_limit_c} °C",
        "ready_cycling": "Niet meer verwarmingsperiodes dan de thermostaat: E32 {heating_periods_e32}, "
            "thermostaat {heating_periods_thermostat}",
        "ready_sources": "Ruimtebronnen werken, en een reservesensor heeft het overgenomen",
        "ready_boiler": "Ketel gehoord op de bus",
        "ready_boiler_limit": "Ketelmaximum bekend: {boiler_limit_c} °C",
        "fix_timing": "De E32 stookt op andere momenten dan je thermostaat: controleer de doeltemperaturen en "
            "het weekprogramma.",
        "fix_flow_limit": "Een vraag kwam boven de harde grens: controleer de grenzen van de watertemperatuur.",
        "fix_cycling": "De E32 zou de brander vaker starten: controleer de grenzen van de watertemperatuur.",
        "fix_sources": "Controleer de ruimtesensoren (batterij, bereik) en geef een ruimte een tweede bron.",
        "fix_boiler": "De E32 hoort niets van de ketel: controleer de buskabel.",
        "fix_boiler_limit": "De ketel heeft zijn maximum niet gemeld: controleer de busverbinding.",
        "today_week": "Vandaag en deze week", "gas_heating_today": "Gas verwarmen",
        "gas_hot_water_today": "Gas warm water", "starts_today": "Branderstarts",
        "burner_today": "Brandertijd", "boiler_values": "Wat de ketel meldt",
        "who_controls": "Wie regelt de ketel", "yesterday_figures": "Gisteren in cijfers",
        "dhw_target_short": "Doel warm water",
        "knowledge": "Wat de E32 weet", "your_boiler": "Je ketel",
        "curve_title": "Watertemperatuur bij buitentemperatuur", "noticed": "Opgevallen",
        "noticed_note": "Gisteren wordt vergeleken met de gewone dagen van je eigen huis; dat is informatie en verandert "
                        "niets.",
        "free_heat": "Gratis warmte",
        "other_rooms": "Overige ruimtes",
    },
    # Polish: the terms of translations/pl.json and docs/UX-GLOSSARY.md; E32 page names stay English.
    "pl": {
        "heating": "Ogrzewanie", "boiler_view": "Kocioł", "diagnostics": "Diagnostyka",
        "room_settings": "Ustawienia pomieszczeń", "now": "Teraz", "rooms": "Pomieszczenia",
        "set_up_rooms": "Skonfiguruj pomieszczenia", "week_program": "Program tygodniowy",
        "settings": "Ustawienia: {room}",
        "boiler_request": "Żądanie do kotła", "flow": "Woda do ogrzewania (zasilanie)", "return": "Woda powrotna (powrót)",
        "modulation": "Moc palnika", "pressure": "Ciśnienie", "dhw": "Ciepła woda", "code": "Kod wyświetlacza",
        "max_ch": "Maksimum kotła", "status": "Stan", "problem": "Ogrzewanie",
        "starts_hour": "Starty na godzinę", "short_cycling": "Palnik zbyt często się włącza",
        "agreement": "Zgodność z termostatem", "measured": "Zmierzona przez E32", "target": "Temperatura docelowa",
        "valve_position": "Otwarcie zaworów",
        "mode": "Tryb", "off_until": "Wyłączone do", "without_ha": "Temperatura bez Home Assistant",
        "compare": "E32 i termostat", "e32_request": "Żądanie do kotła E32",
        "thermostat_request": "Żądanie termostatu", "heating_time_e32": "Czas grzania E32",
        "heating_time_thermostat": "Czas grzania termostatu", "starts_e32": "Starty E32",
        "starts_thermostat": "Starty termostatu", "heating_per_day": "Czas grzania na dzień",
        "boiler": "Kocioł", "bluetooth": "Czujniki Bluetooth", "temperature": "Temperatura",
        "humidity": "Wilgotność", "battery": "Bateria",
        "shadow": "Okres próbny: E32 liczy równolegle, ale jeszcze nie steruje kotłem; decyduje nadal Twój "
                  "obecny termostat lub własna regulacja kotła.",
        "active": "E32 steruje kotłem.",
        "next": "Następny krok: wykonaj test kotła i potwierdź przejęcie na stronie pomieszczeń E32. Do tego czasu E32 "
                "niczego nie wysyła do kotła.",
        "how": "E32 utrzymuje temperaturę w pomieszczeniach, także bez Home Assistant.",
        "overview": "Przegląd",
        "room_nothing": "Jeszcze niczego się nie nauczył.",
        "house": "Dom",
        "learning_view": "Uczenie i ustawienia",
        "more": "Więcej",
        "sensors_presence": "Czujniki, okna i osoby",
        "smart_heating": "Inteligentne nagrzewanie i sterowanie pogodowe",
        "cycling_ok": "Palnik pracuje spokojnie.",
        "cycling_info": "E32 stopniowo wydłuża przerwę palnika.",
        "burner": "Palnik",
        "problem_more": "Wszystkie powody",
        "legacy_rooms": "Pomieszczenia (starsza konfiguracja)",
        "group_heating": "Ogrzewanie", "group_dhw": "Ciepła woda", "group_status": "Stan i usterki",
        "group_counters": "Liczniki", "group_settings": "Ustawienia kotła",
        "group_thermostat": "Termostat na magistrali", "history_24h": "Ostatnie 24 godziny",
        "boiler_note": "Wartości tak, jak zgłasza je kocioł; wartości, której kocioł nie wysyła, tu nie ma. "
                       "Moc palnika to procent maksimum kotła, a nie kW; \"aktywny\" to to, co zgłasza kocioł, "
                       "a nie osobne sprawdzenie.",
        "settings_note": "Ustawienia, które kocioł zgłasza tylko na żądanie, E32 odczytuje przy uruchomieniu, a potem "
                         "co sześć godzin; czas ostatniego odczytu jest podany na czujniku.",
        "raw": "Surowe dane kotła",
        "raw_note": "Do szukania usterek: wartości dokładnie tak, jak wysyła je kocioł, niesprawdzane przez E32.",
        "e32_device": "E32",
        "estimates": "Liczniki energii i ciepłej wody",
        "estimates_empty": "Ten kocioł nie zgłasza jeszcze liczników energii ani ciepłej wody; kotły, które to "
                           "robią (EMS+), pokazują je tutaj. Karta Kocioł i strona Dom w E32 szacują gaz na dzień "
                           "z mocy palnika i mocy kotła.",
        "older_rooms": "Pomieszczenia (starsza konfiguracja)",
        "legacy_boiler_note": "To, co kocioł zgłasza przez swoją magistralę (EMS), a nie dowód polecenia E32. "
                              "Nieznane lub stare wartości to nie zero.",
        "flow_graph": "Temperatury wody: docelowa, do ogrzewania i powrotna", "flow_selection": "Docelowa (kocioł)",
        "measured_flow": "Do ogrzewania (zasilanie)", "measured_return": "Powrotna (powrót)",
        "current_flow": "Do ogrzewania, według kotła",
        "modulation_graph": "Moc palnika (%) — nie kW", "modulation_series": "Moc palnika (%)",
        "dhw_graph": "Temperatury ciepłej wody", "dhw_selected": "Zgłoszona wybrana ciepła woda",
        "dhw_measured": "Zmierzona ciepła woda", "dhw_target": "Zgłoszona docelowa ciepła woda",
        "states_graph": "Zgłoszone ogrzewanie / ciepła woda / płomień / pompa", "state_heating": "Zgłoszone ogrzewanie",
        "state_dhw": "Zgłoszona ciepła woda", "state_flame": "Zgłoszony bit płomienia", "state_pump": "Zgłoszony bit pompy",
        "dhw_card": "Możliwości i jakość ciepłej wody",
        "dhw_note": "Ciepła woda, tylko podgląd: ostatnie wartości zgłoszone przez kocioł (ich wiek nie jest "
                    "sprawdzany); nic nie jest wysyłane do kotła.",
        "dhw_profile": "Profil", "dhw_status": "stan", "unknown": "Nieznane",
        "estimates_note": "Energia i objętość to szacunki ze zgłoszonych wartości, a nie liczniki gazu lub ciepła.",
        "energy_chart": "Szacowana energia na dzień (nie licznik)", "volume_chart": "Objętość ciepłej wody na dzień",
        "flame_chart": "Obserwowany czas płomienia na dzień",
        "models_note": "Modele cieplne pomieszczeń to szacunki, a nie zmierzone ciepło; nieznane lub nieaktualne "
                       "dane zostawiają luki.",
        "room_history": "{room}: docelowa i zmierzona", "room_measured": "Zmierzona", "room_target": "Docelowa",
        "learning": "Nauka", "flow_advice": "Zalecana temperatura wody", "heating_start": "Start grzania",
        "learning_note": "E32 uczy się też, jak szybko nagrzewa się każde pomieszczenie, i wylicza najchłodniejszą "
                         "wodę, która wciąż nagrzeje je o 1 °C na czas (zalecana temperatura wody).",
        "advice_only": "Na razie to tylko porada; E32 nadal używa regulacji pokojowej.",
        "dhw_taps": "Pobory dziś", "dhw_today": "Ciepła woda dziś",
        "advice": "Porady", "advice_where": "Gdzie", "advice_confidence": "Pewność",
        "advice_note": "Tylko porada: nic nie jest zmieniane automatycznie.",
        "learned": "Czego nauczył się termostat", "learned_house": "Dom i kocioł",
        "learned_changes": "Co zmienił sam",
        "learned_note": "Termostat sam dostosowuje te ustawienia; aby zmienić jedno z nich: Konfiguruj → Ogrzewanie i kocioł → Komfort i "
                        "dbałość o kocioł (lub strona E32, Dom).",
        "confidence_low": "niska", "confidence_medium": "średnia", "confidence_high": "wysoka",
        "gas_heating": "Ogrzewanie", "gas_hot_water": "Ciepła woda", "gas_keep_warm": "W tym podtrzymanie ciepłej wody",
        "gas_tapping": "Pobór", "gas_keeping_warm": "Podtrzymanie",
        "activity_timeline": "Co robi kocioł (24 godziny)", "activity": "Kocioł",
        "dhw_use_note": "Pobór to ciepła woda z kranu; podtrzymanie to kocioł, który dogrzewa swój zasobnik lub "
                        "wymiennik bez otwartego kranu, nic więcej; zasobnik c.w.u. jest pokazywany jako ładowanie. "
                        "E32 rozróżnia je po najbardziej bezpośrednim sygnale, jaki zgłasza Twój kocioł.",
        "gas_per_day": "Gaz na dzień",
        "gas_measured": "Zmierzony licznikiem gazu, podzielony według tego, co robił kocioł.",
        "gas_estimate": "Oszacowany z mocy palnika i mocy grzewczej kotła (bez licznika gazu).",
        "gas_note": "Dodaj ogrzewanie i ciepłą wodę do panelu Energia w sekcji Zużycie gazu; podtrzymanie jest "
                    "częścią ciepłej wody, więc tam je pomiń.",
        "yesterday": "Wczoraj", "burner_per_day": "Godziny pracy palnika na dzień",
        "missed_per_day": "Utracony komfort na dzień (minuty)",
        "day_burner": "Palnik: {h} godz., starty: {n} (krótsze niż 10 minut: {short}).",
        "day_gas": "Gaz: ogrzewanie {heating}, ciepła woda {hot_water}.",
        "day_room": "{room}: żądanie ciepła przez {h} godz.; ciepło średnio po {ttt} min; utracony komfort {missed} min.",
        "day_room_no_step": "{room}: żądanie ciepła przez {h} godz.; utracony komfort {missed} min.",
        "day_outdoor": "Na zewnątrz od {low} do {high} °C.",
        "day_partial": "Niepełny dzień: E32 nie był słyszalny przez cały dzień, więc dane są niekompletne.",
        "scoreboard_on_time": "ciepło na czas",
        "scoreboard_late": "ciepło {m} min za późno",
        "scoreboard_early": "ciepło {m} min za wcześnie",
        "scoreboard_overshoot": "{c} °C za ciepło",
        "scoreboard_hours": "Czas grzania: {h} godz.",
        "scoreboard_burner": "Starty palnika na godzinę grzania: {n}",
        "scoreboard_short": "Krótkie cykle palnika: {h} godz.",
        "scoreboard_gas": "Gaz na ogrzewanie (szacunek): {kwh} kWh",
        "scoreboard_degree_days": "Stopniodni: {d}",
        "scoreboard_degree_day": "{v} kWh na stopniodzień",
        "scoreboard_note": "Każdego dnia termostat sprawdza, czy każde pomieszczenie było ciepłe na czas i nie za ciepłe, jak często startował palnik i ile gazu poszło na ogrzewanie. Uczy się z tego; każda liczba ma swoją historię na własnym czujniku.",
        "day_none": "Pierwszy pełny dzień pojawi się tu jutro.",
        "outdoor": "Na zewnątrz",
        "flow_settings": "Kompensacja pogodowa i nauka",
        "flow_source": "Temperatura wody ustalana przez",
        "weather_curve": "Kompensacja pogodowa",
        "design_flow": "Temperatura wody przy silnym mrozie (−10 °C)",
        "apply_learned": "Inteligentne nagrzewanie",
        "house_mode": "Tryb domu", "boiler_now": "Kocioł",
        "holiday_next": "Urlop od {from} do {until}", "holiday_now": "Urlop do {until}",
        "months": "sty,lut,mar,kwi,maj,cze,lip,sie,wrz,paź,lis,gru",
        "learned_latest": "Ostatnia zmiana",
        "compare_link": "E32 w porównaniu z Twoim termostatem",
        "no_request": "Brak żądania do kotła",
        "wanting_one": "1 pomieszczenie potrzebuje ciepła", "wanting_many": "Pomieszczenia potrzebujące ciepła: {n}",
        "wanting_none": "Żadne pomieszczenie nie potrzebuje ciepła", "decimal": ",",
        "flow_short": "Woda do ogrzewania", "return_short": "Woda powrotna",
        "e32": "E32", "thermostat": "Termostat",
        "comparison_view": "Porównanie",
        "room_off": "To pomieszczenie jest wyłączone i nigdy nie żąda ciepła.",
        "room_no_source": "Pomieszczenie {room} jest wyłączone i nie ma działającego źródła temperatury. Wybierz "
            "źródło, aby znów z niego korzystać, albo usuń pomieszczenie, jeśli nie jest już potrzebne.",
        "choose_source": "Wybierz źródło",
        "remove_room": "Usuń pomieszczenie",
        "readiness": "Gotowość do przejęcia?",
        "ready_ready": "Gotowe: wykonaj kroki przełączenia.",
        "ready_waiting": "Jeszcze nie: E32 nadal zbiera dane w okresie próbnym.",
        "ready_not_ready": "Niegotowe: najpierw usuń problemy oznaczone na czerwono.",
        "ready_no_comparison": "Na magistrali kotła nie ma termostatu do porównania, więc sprawdzane są tylko E32 "
            "i kocioł.",
        "ready_stable": "Stabilność: {stable_hours} z {stable_hours_needed} godz. bez zawieszenia i nieoczekiwanego "
            "restartu",
        "ready_periods": "Porównane okresy grzania: {periods_compared} z {periods_needed}, w tym nocne obniżenie, "
            "poranne nagrzewanie i okres bez zapotrzebowania",
        "ready_timing": "Ciepło w tych samych momentach: {timing_events} z {timing_events_needed} startów i zatrzymań",
        "ready_flow_limit": "Żądana temperatura wody nigdy powyżej limitu: najwyżej {flow_max_c} °C, limit {flow_limit_c} °C",
        "ready_cycling": "Nie więcej okresów grzania niż termostat: E32 {heating_periods_e32}, "
            "termostat {heating_periods_thermostat}",
        "ready_sources": "Źródła temperatury w pomieszczeniach działają, a czujnik zapasowy przejął pomiar",
        "ready_boiler": "Kocioł słyszalny na magistrali",
        "ready_boiler_limit": "Maksimum kotła znane: {boiler_limit_c} °C",
        "fix_timing": "E32 grzeje w innych momentach niż Twój termostat: sprawdź temperatury docelowe pomieszczeń "
            "i program tygodniowy.",
        "fix_flow_limit": "Żądanie przekroczyło twardy limit: sprawdź limity temperatury wody.",
        "fix_cycling": "E32 uruchamiałby palnik częściej: sprawdź limity temperatury wody.",
        "fix_sources": "Sprawdź czujniki w pomieszczeniach (bateria, zasięg) i dodaj pomieszczeniu drugie źródło.",
        "fix_boiler": "E32 nic nie słyszy z kotła: sprawdź kabel magistrali.",
        "fix_boiler_limit": "Kocioł nie zgłosił swojego maksimum: sprawdź połączenie z magistralą.",
        "today_week": "Dziś i w tym tygodniu", "gas_heating_today": "Gaz: ogrzewanie",
        "gas_hot_water_today": "Gaz: ciepła woda", "starts_today": "Starty palnika",
        "burner_today": "Praca palnika", "boiler_values": "Co zgłasza Twój kocioł",
        "who_controls": "Kto steruje kotłem", "yesterday_figures": "Wczoraj w liczbach",
        "dhw_target_short": "Cel ciepłej wody",
        "knowledge": "Co wie E32", "your_boiler": "Twój kocioł",
        "curve_title": "Temperatura wody a temperatura zewnętrzna", "noticed": "Spostrzeżenia",
        "noticed_note": "Wczoraj jest porównywane ze zwykłymi dniami Twojego domu; to tylko informacja i niczego nie "
                        "zmienia.",
        "free_heat": "Darmowe ciepło",
        "other_rooms": "Pozostałe pomieszczenia",
    },
}


def dashboard_language(hass):
    """English, Dutch or Polish by the Home Assistant language (English otherwise)."""
    language = (hass.config.language or "en").lower().replace("_", "-").split("-")[0]
    return language if language in TEXT else "en"


def view_cards(view):
    """Every card of a view, also inside its sections."""
    cards = list(view.get("cards", []))
    for section in view.get("sections", []):
        cards.extend(section.get("cards", []))
    return cards


def _section(*cards):
    return {"type": "grid", "cards": [card for card in cards if card]}


def _section_known(entities, *cards, hidden=None):
    """A section that hides as a whole while none of ``entities`` has a value (dashboard-spec §1).

    ``entities`` are the ones its cards show with: every card in it is visible whenever one of them has a value,
    so its heading never stands over nothing. ``hidden``: {entity id: more states that count as no value}.
    """
    section = _section(*cards)
    entities = [entity for entity in dict.fromkeys(entities) if entity]
    if entities:
        section["visibility"] = _any_known(entities, hidden)
    return section


def _filled(section):
    """The section, or None when it would be its heading alone."""
    return section if section is not None and len(section["cards"]) > 1 else None


# Ready to take over? (takeover_readiness.py): the result attribute of each criterion, in order.
READINESS_ITEMS = ("stable", "periods", "timing", "flow_limit", "cycling", "sources", "boiler", "boiler_limit")


def _readiness_card(t, entity_id):
    """The verdict and one line per criterion the E32 reports (✅ pass, ⏳ wait, ❌ fail with what to do)."""
    quoted = json.dumps(entity_id)

    def attribute(match):
        return "{{ state_attr(" + quoted + ", '" + match.group(1) + "') }}"
    content = ("{% set s = states(" + quoted + ") %}{% set mark = {'pass': '✅', 'wait': '⏳', 'fail': '❌'} %}"
               "**{% if s == 'ready' %}" + t["ready_ready"] + "{% elif s == 'not_ready' %}" + t["ready_not_ready"]
               + "{% else %}" + t["ready_waiting"] + "{% endif %}**\n\n"
               "{% if state_attr(" + quoted + ", 'comparison') == false %}" + t["ready_no_comparison"] + "\n\n{% endif %}")
    for item in READINESS_ITEMS:
        text = t["ready_" + item]
        line = re.sub(r"\{(\w+)\}", attribute, text)
        names = re.findall(r"\{(\w+)\}", text)
        if names:
            # A figure the E32 does not know yet (null) shows the criterion alone, never "None °C".
            known = " and ".join("state_attr(" + quoted + ", '" + name + "') is not none" for name in names)
            line = "{% if " + known + " %}" + line + "{% else %}" + text.split(":")[0] + "{% endif %}"
        fix = t.get("fix_" + item)
        content += ("{% set r = state_attr(" + quoted + ", '" + item + "') %}{% if r in mark %}- {{ mark[r] }} " + line
                    + ("{% if r == 'fail' %}. " + fix + "{% endif %}" if fix else "") + "\n{% endif %}")
    return {"type": "markdown", "content": content, "visibility": _known(entity_id, ("not_applicable",))}


def _heading(text, icon=None, badges=None, style="title", visibility=None):
    card = {"type": "heading", "heading": text, "heading_style": style}
    if icon:
        card["icon"] = icon
    if badges:
        card["badges"] = badges
    if visibility:
        card["visibility"] = visibility
    return card


def _link(text, icon, path, visibility=None):
    """A one-line link row (a heading with a chevron) to another page."""
    card = _heading(text, icon, style="subtitle", visibility=visibility)
    card["tap_action"] = {"action": "navigate", "navigation_path": path}
    return card


def _known(entity_id, also=()):
    """Card visibility: only while the entity has a value (and none of the states ``also``)."""
    return [{"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown", *also]}]


# Rows hidden in this state too: the maintenance message while there is none.
HIDDEN_STATES = {"maintenance_message": ("none",)}


def _rows(entity_ids):
    """Entities-card rows named by the entity alone: the card title already says whose they are,
    and the device name in front of every row cut the names short."""
    return [{"entity": entity_id, "name": {"type": "entity"}} for entity_id in entity_ids]


def _known_rows(entity_ids, hidden=None):
    """Rows shown only while their entity has a value (no "Unknown" rows for what a boiler never sends);
    ``hidden``: {entity id: more states that hide the row}."""
    hidden = hidden or {}
    return [{"type": "conditional", "conditions": _known(row["entity"], hidden.get(row["entity"], ())), "row": row}
            for row in _rows(entity_ids)]


def _any_known(entity_ids, hidden=None):
    """Card visibility: while at least one of the entities has a value; ``hidden``: {entity id: more states that
    count as none}, as for its row (_known_rows)."""
    hidden = hidden or {}
    return [{"condition": "or", "conditions": [condition for entity_id in entity_ids
                                               for condition in _known(entity_id, hidden.get(entity_id, ()))]}]


def _none_known(entity_ids):
    """Card visibility: while none of the entities has a value."""
    return [{"condition": "state", "entity": entity_id, "state": ["unavailable", "unknown"]} for entity_id in entity_ids]


def _known_entities_card(entity_ids, hidden=None, title=None):
    """An entities card of rows with a value, hidden while no row shows; no title where its section heading names
    it, ``title`` where one section holds several such cards."""
    card = {"type": "entities", "entities": _known_rows(entity_ids, hidden), "visibility": _any_known(entity_ids, hidden)}
    if title:
        card["title"] = title
    return card


def _room_lines_card(t, learned, names, on):
    """What the thermostat learned for this room (its lines of the learned overview), or a short "nothing yet"."""
    quoted = json.dumps(learned)
    content = ("{% set names = " + json.dumps(list(names), ensure_ascii=False) + " %}"
               "{% set mine = (state_attr(" + quoted + ", 'rooms') or []) | selectattr('name', 'in', names) | list %}"
               "{% if mine and mine[0].lines %}{% for line in mine[0].lines %}- {{ line.text }}"
               "{% if line.meaning %}<br>*{{ line.meaning }}*{% endif %}\n{% endfor %}"
               "{% else %}" + t["room_nothing"] + "{% endif %}")
    return {"type": "markdown", "content": content,
            "visibility": [*on, {"condition": "state", "entity": learned, "state_not": "unavailable"}]}


def _learning_cards(t, room, active=None, learned=None, names=()):
    """A compact "Learning" area under a room: status badge, what it learned, recommended flow, predicted start.

    Nothing without the learned entities (older firmware); hidden while the E32 reports none
    and while the room is off (``active``: the room's "on" condition).
    """
    learning, advice, start = room.get("learning"), room.get("flow_advice"), room.get("heating_start")
    on = list(active or [])
    if not learning:
        return ([_heading(t["learning"], "mdi:school-outline", style="subtitle", visibility=on),
                 _room_lines_card(t, learned, names, on)] if learned else [])
    badge = {"type": "entity", "entity": learning, "show_state": True, "show_icon": True, "color": "teal"}
    return [
        _heading(t["learning"], "mdi:school-outline", [badge], "subtitle", on + _known(learning)),
        _room_lines_card(t, learned, names, on + _known(learning)) if learned else None,
        # The advice only means something once the room is learned.
        # The whole width: "Recommended water temperature" was cut short in half a section.
        _wide(_tile(advice, t["flow_advice"],
                    visibility=[*on, {"condition": "state", "entity": learning, "state": "ready"}, *_known(advice)])),
        _wide(_tile(start, t["heating_start"], visibility=on + _known(start))),
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


LEARNED_PATH = "learned"


def _learned_sections(t, learned, how=None):
    """What the thermostat learned (learned_overview.py), in the learning view: how far each room is, the house
    and boiler, and what it changed by itself. What it learned per room sits in that room's section.

    Three sections, so a wide screen shows them side by side; a phone reads them one after another. ``how``: the
    note on how it learns (a card with its own visibility), the last card of the first section; without the
    learned overview (an older integration) it stands alone under that section's heading.
    """
    if not learned:
        if not how:
            return []
        section = _section(_heading(t["learned"], ICONS["learning"], style="title"), how)
        section["visibility"] = how["visibility"]
        return [section]
    quoted = json.dumps(learned)
    lines = ("{% for line in items %}- {{ line.text }}{% if line.meaning %}<br>*{{ line.meaning }}*{% endif %}\n"
             "{% endfor %}")
    # One sentence of the explanation; the rest behind "More".
    summary = ("{% set e = state_attr(" + quoted + ", 'explanation') or '' %}{% set p = e.split('. ', 1) %}"
               "{{ p[0] }}{% if p | length > 1 %}.\n\n<details><summary>" + t["more"] + "</summary>\n\n{{ p[1] }}\n\n</details>"
               "{% endif %}\n\n"
               "{% for room in state_attr(" + quoted + ", 'rooms') or [] %}- **{{ room.name }}** · {{ room.progress }}\n"
               "{% endfor %}{% for change in (state_attr(" + quoted + ", 'changes') or [])[:1] %}\n"
               "*" + t["learned_latest"] + ":* {{ change.text }}{% endfor %}")
    house = "{% set items = state_attr(" + quoted + ", 'house') or [] %}" + lines
    changes = ("{% for change in state_attr(" + quoted + ", 'changes') or [] %}- {% if change.time %}"
               "{{ as_timestamp(change.time) | timestamp_custom('%d-%m') }}: {% endif %}{{ change.text }}\n{% endfor %}")
    shown = [{"condition": "state", "entity": learned, "state_not": "unavailable"}]
    sections = []
    for heading, icon, content, note in ((t["learned"], ICONS["learning"], summary, how),
                                         (t["learned_house"], "mdi:home-thermometer-outline", house, None),
                                         (t["learned_changes"], "mdi:history", changes, _note(t, t["learned_note"], shown))):
        section = _section(_heading(heading, icon, style="title", visibility=shown),
                           {"type": "markdown", "content": content, "visibility": shown}, note)
        section["visibility"] = shown
        sections.append(section)
    return sections


# The Learning view as the owner's sketch (rc.5, Leren.dc.html): what the E32 knows, your boiler, water temperature by
# outdoor temperature, yesterday in figures (_yesterday_figures), what stood out, the free heat and Smart warm-up and
# weather compensation, each a section of its own that hides as a whole while it has nothing to show.


def _icon(concept):
    """The icon of a concept (ICONS) in its colour, at the start of a markdown line, as the sketch draws it. A markdown
    card cannot read the theme's CSS variables (its sanitiser keeps <font color> only), so the colours are those of
    Home Assistant's default theme (ICON_COLOURS)."""
    return '<font color="' + ICON_COLOURS[concept] + '"><ha-icon icon="' + ICONS[concept] + '"></ha-icon></font>'


def _listed(entity_id, attribute):
    """Visibility: while the entity's list ``attribute`` has an item (Home Assistant 2026.10 reads an attribute in a
    state condition as text: an empty list is "", a missing attribute or entity "unknown")."""
    return [{"condition": "state", "entity": entity_id, "attribute": attribute,
             "state_not": ["unavailable", "unknown", ""]}]


def _knowledge_section(t, knowledge):
    """What the E32 knows (insight.py, E32 rc.5), first on the Learning view: the knowledge card, a ring beside "The
    E32 knows your house: 70 %" and what it still learns in words (frontend/heating-curve-card.js). It follows its
    sensor without a rebuild and hides until the E32 reports it (firmware before rc.5 leaves it unknown)."""
    if not knowledge:
        return None
    return _section_known([knowledge], _heading(t["knowledge"], ICONS["knowledge"]),
                          _wide({"type": KNOWLEDGE_CARD_TYPE, "entity": knowledge, "visibility": _known(knowledge)}))


def _boiler_section(t, boiler):
    """Your boiler: what the E32 learned from the boiler itself, in one sentence behind a flame (the Boiler response
    sensor's ``sentence``, insight.py); every known state has one. Hidden while the response is unknown."""
    if not boiler:
        return None
    quoted = json.dumps(boiler)
    return _section_known([boiler], _heading(t["your_boiler"], ICONS["boiler"]), {"type": "markdown", "content": (
        "{% set s = state_attr(" + quoted + ", 'sentence') %}{% if s %}" + _icon("heating") + " {{ s }}{% endif %}")})


def _curve_section(t, curve):
    """Water temperature by outdoor temperature (E32 rc.5): the heating-curve card (frontend/heating-curve-card.js)
    under a heading of its own, so the card leaves its own title out; shown while the curve has a value."""
    if not curve:
        return None
    return _section_known([curve], _heading(t["curve_title"], ICONS["curve"]), _wide(
        {"type": CURVE_CARD_TYPE, "entity": curve, "show_name": False, "visibility": _known(curve)}))


def _noticed_section(t, learned):
    """Noticed: what stood out yesterday against the house's own usual days (the learned overview's ``insights``,
    insight.py), each line behind an information icon with what can cause it, in one card with one line on what the
    comparison is; hidden while nothing stood out."""
    if not learned:
        return None
    quoted = json.dumps(learned)
    section = _section(_heading(t["noticed"], ICONS["insight"]), {"type": "markdown", "content": (
        "{% for line in state_attr(" + quoted + ", 'insights') or [] %}" + _icon("insight") + " {{ line.text }}"
        "{% if line.meaning %} {{ line.meaning }}{% endif %}\n\n{% endfor %}*" + t["noticed_note"] + "*")})
    section["visibility"] = _listed(learned, "insights")
    return section


def _free_heat_section(t, learned):
    """Free heat: per room the heat it gets for free from sun, cooking and people (E32 rc.5, the learned overview's
    ``free_heat``), each room on a line behind a sun with what Smart warm-up does with it; hidden while there is none."""
    if not learned:
        return None
    quoted = json.dumps(learned)
    section = _section(_heading(t["free_heat"], ICONS["free_heat"]), {"type": "markdown", "content": (
        "{% for line in state_attr(" + quoted + ", 'free_heat') or [] %}" + _icon("free_heat") + " **{{ line.name }}** · "
        "{{ line.text }}{% if line.meaning %} {{ line.meaning }}{% endif %}\n\n{% endfor %}")})
    section["visibility"] = _listed(learned, "free_heat")
    return section


def _settings_section(t, flow, rooms=None, week=None):
    """Smart warm-up and weather compensation: the two switches and the water temperature in hard frost as rows
    (stored on the E32, e32_flow.py; always there to change), and the links to the rooms editor (``rooms``) and the
    week program (``week``); None without any of them. What sets the water temperature now (the sensor "Water
    temperature set by") is not a setting and stays on the E32 device: as a row its long state cut its name short on
    a phone, and the sketch has the three rows only."""
    rows = [{"entity": flow[key], "name": t[name], "icon": icon} for key, name, icon in (
        ("apply_learned", "apply_learned", "mdi:school-outline"), ("weather_curve", "weather_curve", "mdi:sun-thermometer"),
        ("curve_design_flow_c", "design_flow", "mdi:thermometer-lines")) if flow.get(key)]
    return _filled(_section(
        _heading(t["smart_heating"], ICONS["settings"]), {"type": "entities", "entities": rows} if rows else None,
        _link(t["set_up_rooms"], "mdi:home-edit-outline", rooms) if rooms else None,
        _link(t["week_program"], "mdi:calendar-week", week) if week else None))


def _per_day(title, entities, entity_id):
    """A bar per day for the last 7 days (the day's change of a running total), shown while ``entity_id`` has a value."""
    return {"type": "statistics-graph", "title": title, "chart_type": "bar", "period": "day", "days_to_show": 7,
            "stat_types": ["change"], "entities": entities, "visibility": _known(entity_id)}


def _energy_section(t, hub):
    """Today and this week (dashboard-spec §5.3): today's gas for heating and for hot water and today's burner
    starts and time as figures, then the one chart of the gas per day (heating, tapping and keeping warm once the
    E32 tells them apart; heating and hot water before), the burner hours per day and one note on how the gas is
    counted.

    hub: {key: entity id} of the hub sensors. Every card shows only with a value, the section hides as a whole
    without one, and there is none without the gas and the daily-summary sensors.
    """
    heating, hot_water = hub.get("heating_gas"), hub.get("hot_water_gas")
    starts, burner = hub.get("daily_burner_starts"), hub.get("daily_burner_time")
    gas = heating or hot_water
    posts = [(hub.get(key), t[name]) for key, name in (("heating_gas", "gas_heating"), ("tapping_gas", "gas_tapping"),
                                                       ("keep_warm_gas", "gas_keeping_warm"))]
    if not all(entity_id for entity_id, _ in posts):
        posts = [(entity_id, t[name]) for entity_id, name in ((heating, "gas_heating"), (hot_water, "gas_hot_water"))
                 if entity_id]
    note = None
    if gas:
        quoted = json.dumps(gas)
        note = {"type": "markdown", "visibility": _known(gas), "content": (
            "{% if state_attr(" + quoted + ", 'estimate') %}" + t["gas_estimate"] + "{% else %}" + t["gas_measured"]
            + "{% endif %}" + _details(t, t["gas_note"]))}
    return _filled(_section_known(
        [gas, starts, burner],
        _heading(t["today_week"], ICONS["week"]),
        *_pair(_statistic(heating, t["gas_heating_today"], ICONS["gas"]),
               _statistic(hot_water, t["gas_hot_water_today"], ICONS["gas"]), rows=2),
        *_pair(_statistic(starts, t["starts_today"], ICONS["burner_starts"]),
               _statistic(burner, t["burner_today"], ICONS["burner_time"]), rows=2),
        # The one gas chart of the dashboard; the Overview has today's figure, Learning yesterday's line.
        _per_day(t["gas_per_day"], [{"entity": entity_id, "name": name} for entity_id, name in posts], gas)
        if gas else None,
        _per_day(t["burner_per_day"], [{"entity": burner}], burner) if burner else None,
        note))


def _summary_lines(t, summary, gas_unit, scoreboard_gas=None):
    """Yesterday's daily summary (daily_summary.py) as list lines of "Yesterday in figures": the burner, the gas
    (unless ``scoreboard_gas`` has a value: then the scoreboard's line says it, once) and the outdoor range, then
    per room its heat demand, how fast it got warm and its missed comfort; a partial day says so. Before the first
    full day: "tomorrow", unless the scoreboard has a line already (``shown.lines``, _yesterday_figures).
    """
    q = json.dumps(summary)

    def fill(text, **names):
        for name, expr in names.items():
            text = text.replace("{" + name + "}", "{{ " + expr + " }}")
        return text

    def number(expr):
        """The summary's number as it is, in the language's decimal sign ("7,4 uur", as elsewhere on the dashboard)."""
        if t["decimal"] == ".":
            return expr
        return "(((" + expr + ") ~ '') | replace('.', " + json.dumps(t["decimal"]) + "))"
    unit = " " + gas_unit if gas_unit else ""
    gas = "d.gas and d.gas.heating is not none and d.gas.hot_water is not none"
    if scoreboard_gas:
        gas += " and not is_number(states(" + json.dumps(scoreboard_gas) + "))"
    return (
        "{% set d = state_attr(" + q + ", 'last_day') %}{% if d %}- "
        + fill(t["day_burner"], h=number("d.burner_hours"), n="d.burner_starts", short="d.short_runs")
        + "{% if " + gas + " %} "
        + fill(t["day_gas"], heating=number("d.gas.heating") + " ~ '" + unit + "'",
               hot_water=number("d.gas.hot_water") + " ~ '" + unit + "'")
        + "{% endif %}{% if d.outdoor %} "
        + fill(t["day_outdoor"], low=number("d.outdoor.min"), high=number("d.outdoor.max"))
        + "{% endif %}\n{% for r in d.rooms %}- {% if r.time_to_target_minutes is not none %}"
        # Whole minutes ("25 min", not "25.0 min": the summary keeps the median as a float).
        + fill(t["day_room"], room="r.name", h=number("r.heat_hours"), ttt="r.time_to_target_minutes | round | int",
               missed="r.missed_minutes")
        + "{% else %}" + fill(t["day_room_no_step"], room="r.name", h=number("r.heat_hours"), missed="r.missed_minutes")
        + "{% endif %}\n{% endfor %}{% if not d.complete %}\n_" + t["day_partial"] + "_{% endif %}"
        + "{% elif not shown.lines %}" + t["day_none"] + "{% endif %}")


def _figure(t, digits):
    """A Jinja expression: the number in v with digits decimals and the language's decimal sign."""
    return "(('%." + str(digits) + "f' % (v | float)) | replace('.', " + json.dumps(t["decimal"]) + "))"


def _jinja_text(text, **values):
    """A translated text with {name} placeholders as one Jinja string expression: "warm " ~ (m) ~ " min late"."""
    pieces = []
    for k, piece in enumerate(re.split(r"\{(\w+)\}", text)):
        if k % 2:
            pieces.append("(" + values[piece] + ")")
        elif piece:
            pieces.append(json.dumps(piece, ensure_ascii=False))
    return " ~ ".join(pieces) or '""'


# The headline figures of "Yesterday in figures", large on their own card above the lines (frontend/house-card.js,
# custom:openthermostat-yesterday), each from its own scoreboard sensor: (card key, sensor, its attribute or None for
# the state). The first figure is the lead room's warm on time (_yesterday_figures).
YESTERDAY_FIGURES = (("starts", "burner_starts_per_heating_hour", None), ("gas", "heating_gas_yesterday", None),
                     ("degree_days", "gas_per_degree_day", "degree_days"))


def _scoreboard_lines(t, rooms, names, house, large=()):
    """Yesterday's scoreboard (scoreboard.py, E32 rc.4) in plain words, as list lines of "Yesterday in figures":
    each room warm on time and how far it got above its target; the heating time, the burner's starts per heating
    hour and its short runs; the gas for heating, the degree-days and the gas per degree-day.

    rooms: {room id: {"warm_on_time": entity, "overshoot": entity}}; house: {key: entity}. The text follows the
    sensors' states (the heating time and the degree-days their attributes), so a new day needs no rebuild; a
    figure without a value is left out. Every line it writes counts in ``shown.lines`` (_yesterday_figures).
    large: the figures the card above shows large, (house key, attribute) as in YESTERDAY_FIGURES and
    ("warm_on_time", room id); they are not said again here.
    """
    def part(entity, expression, attribute=None):
        """One figure from the entity's state, or from one of its attributes (the heating hours, the degree-days)."""
        value = ("state_attr(" + json.dumps(entity) + ", " + json.dumps(attribute) + ")" if attribute
                 else "states(" + json.dumps(entity) + ")")
        return "{% set v = " + value + " %}{% if is_number(v) %}{% set parts = parts + [" + expression + "] %}{% endif %}"

    def line(prefix):
        return ("{% if parts %}{% set shown.lines = shown.lines + 1 %}- " + prefix + "{{ parts | join(' · ') }}\n"
                "{% endif %}")
    content = ""
    for room_id, keys in rooms.items():
        content += "{% set parts = [] %}"
        if keys.get("warm_on_time") and ("warm_on_time", room_id) not in large:  # minutes after the switch time
            content += ("{% set v = states(" + json.dumps(keys["warm_on_time"]) + ") %}{% if is_number(v) %}"
                        "{% set m = v | float | round(0) | int %}{% set parts = parts + [("
                        + _jinja_text(t["scoreboard_late"], m="m") + ") if m > 0 else ("
                        + _jinja_text(t["scoreboard_early"], m="-m") + ") if m < 0 else "
                        + json.dumps(t["scoreboard_on_time"], ensure_ascii=False) + "] %}{% endif %}")
        if keys.get("overshoot"):
            content += part(keys["overshoot"], _jinja_text(t["scoreboard_overshoot"], c=_figure(t, 1)))
        content += line("**{{ " + json.dumps(names.get(room_id, room_id), ensure_ascii=False) + " }}**: ")
    # (sensor, its attribute or None for the state, text, placeholder, decimals): the heating hours and the
    # degree-days ride as attributes on the burner-starts and gas-per-degree-day sensors (scoreboard.py).
    for figures in ((("burner_starts_per_heating_hour", "heating_hours", "scoreboard_hours", "h", 1),
                     ("burner_starts_per_heating_hour", None, "scoreboard_burner", "n", 1),
                     ("short_cycling_hours", None, "scoreboard_short", "h", 1)),
                    (("heating_gas_yesterday", None, "scoreboard_gas", "kwh", 1),
                     ("gas_per_degree_day", "degree_days", "scoreboard_degree_days", "d", 1),
                     ("gas_per_degree_day", None, "scoreboard_degree_day", "v", 2))):
        said = [(key, attribute) for key, attribute, *_ in figures if house.get(key) and (key, attribute) not in large]
        if said:
            content += "{% set parts = [] %}"
            for key, attribute, text, name, digits in figures:
                if (key, attribute) in said:
                    content += part(house[key], _jinja_text(t[text], **{name: _figure(t, digits)}), attribute)
            content += line("")
    return content


def _yesterday_figures(t, rooms, names, house, summary=None, missed=None, gas_unit=None, lead=None):
    """Yesterday in figures (dashboard-spec §6), once, on the Learning view: the four headline figures large, two
    by two (frontend/house-card.js, custom:openthermostat-yesterday: the lead room warm on time, burner starts per
    heating hour, gas for heating and the degree-days, each from its own scoreboard sensor), under them the rest of
    the scoreboard (scoreboard.py, E32 rc.4) and the daily summary (daily_summary.py) in lines, then the missed
    comfort per day and one note.

    rooms, house: the scoreboard's sensors (_scoreboard_lines); summary, missed: the daily summary's; lead: the room
    whose warm on time is a headline figure. A figure without its sensor is left out. The cards follow the states,
    so a new day needs no rebuild; the section hides as a whole until one figure has a value, the figures card
    until one of its own has, and the lines while they have nothing to add (one gas figure: the summary's gas line
    only while the scoreboard has none).
    """
    scoreboard = [entity for keys in rooms.values() for entity in keys.values()] + list(house.values())
    if not scoreboard and not summary:
        return None
    from .room_overview import YESTERDAY_CARD_TYPE
    room = rooms.get(lead, {}).get("warm_on_time")
    figures = {"room": {"entity": room, "name": names.get(lead, lead)} if room else None,
               **{key: house.get(sensor) for key, sensor, _ in YESTERDAY_FIGURES}}
    figures = {key: value for key, value in figures.items() if value}
    large = {(sensor, attribute) for key, sensor, attribute in YESTERDAY_FIGURES if key in figures}
    large |= {("warm_on_time", lead)} if room else set()
    entities = [entity for entity in [room, *(house.get(sensor) for _, sensor, _ in YESTERDAY_FIGURES)] if entity]
    # A figure on the card counts as a line: "tomorrow" only while nothing has a value yet.
    counted = ("{% if " + " or ".join("is_number(states(" + json.dumps(entity) + "))" for entity in entities)
               + " %}{% set shown.lines = shown.lines + 1 %}{% endif %}") if entities else ""
    content = ("{% set shown = namespace(lines=0) %}" + counted + _scoreboard_lines(t, rooms, names, house, large)
               + (_summary_lines(t, summary, gas_unit, house.get("heating_gas_yesterday")) if summary else ""))
    return _section_known(
        [*scoreboard, summary, missed],
        _heading(t["yesterday_figures"], ICONS["yesterday"]),
        {"type": YESTERDAY_CARD_TYPE, "grid_options": {"columns": 12}, **figures, "visibility": _any_known(entities)}
        if figures else None,
        {"type": "markdown", "show_empty": False, "content": content},
        _per_day(t["missed_per_day"], [{"entity": missed}], missed) if missed else None,
        _note(t, t["scoreboard_note"]))


# The boiler's display code in words (display_codes.py: its attributes), for a look at a glance:
# the meaning large with the raw code small next to it; a fault or lockout as a warning with
# what to do. Severity names: display_code_table.SEVERITIES.
FAULT_SEVERITIES = ("blocking", "locking", "fault")


def _boiler_status_card(t, entity_id):
    """The boiler's state in words under "Now"; only while the display code has a value."""
    if entity_id is None:
        return None
    quoted = json.dumps(entity_id)
    content = (
        "{% set e = " + quoted + " %}{% set code = states(e) %}{% set meaning = state_attr(e, 'meaning') %}"
        "{% set severity = state_attr(e, 'severity') %}{% set advice = state_attr(e, 'advice') %}"
        "{% set cause = state_attr(e, 'cause') %}{% set raw = code ~ (' ' ~ cause if cause else '') %}"
        "{% if severity in " + json.dumps(list(FAULT_SEVERITIES)) + " %}"
        "<ha-alert alert-type=\"{{ 'error' if severity == 'locking' else 'warning' }}\" "
        "title=\"{{ meaning }}\">{{ state_attr(e, 'severity_text') }}.{% if advice %} {{ advice }}{% endif %} "
        "<small>" + t["code"] + " {{ raw }}</small></ha-alert>"
        "{% elif severity == 'unknown' %}<ha-icon icon=\"mdi:help-circle-outline\"></ha-icon> "
        "**" + t["code"] + " {{ raw }}** · {{ meaning }}"
        "{% elif meaning %}<ha-icon icon=\"{{ " + json.dumps(STATUS_ICONS) + ".get(severity, 'mdi:water-boiler') }}\">"
        "</ha-icon> " + t["boiler_now"] + ": **{{ meaning }}** <small>{{ raw }}</small>"
        "{% if advice and severity != 'normal' %}\n\n<small>{{ advice }}</small>{% endif %}"
        "{% else %}<ha-icon icon=\"mdi:water-boiler\"></ha-icon> " + t["code"] + " **{{ code }}**{% endif %}")
    return {"type": "markdown", "content": content, "visibility": _known(entity_id)}


STATUS_ICONS = {"normal": "mdi:water-boiler", "waiting": "mdi:timer-sand", "service": "mdi:wrench-outline"}


def _hot_water_use_cards(t, hub, heating_active=None):
    """When hot water is tapped and when it is kept warm, for the Boiler view's hot-water section: the last 24 hours
    of what the boiler does (next to its own "heating" bit) and one note on tapping and keeping warm, both while the
    activity has a value. The gas per day is the one chart under "Today and this week". No cards without the
    activity (firmware before it)."""
    activity = hub.get("boiler_activity")
    if not activity:
        return []
    rows = [(activity, t["activity"]), (heating_active, t["state_heating"])]
    return [{"type": "history-graph", "title": t["activity_timeline"], "hours_to_show": 24,
             "entities": [{"entity": entity_id, "name": name} for entity_id, name in rows if entity_id],
             "visibility": _known(activity)},
            _note(t, t["dhw_use_note"], _known(activity))]


def _boiler_now(t, hub, fields, essential):
    """Now (dashboard-spec §5.1), first on the Boiler view: the boiler in words, one coloured tile for what it does
    (heating, hot water or resting; on an older integration the boiler's own "heating" bit), the water to the
    heating next to the water back, and the burner power as a gauge next to its starts in the last hour (or the
    pressure). Every card shows with its value; the section hides as a whole without any."""
    code, flow, back, modulation = (essential(key) for key in ("code", "flow", "return", "modulation"))
    activity = hub.get("boiler_activity")
    doing = activity or fields.get("heating_active")
    if activity:
        tiles = [(t["boiler_now"], icon, color, states) for icon, color, states in ACTIVITY_TILES]
    else:  # on and off of the boiler's own "heating" bit
        tiles = [(t["state_heating"], "heating", "deep-orange", ["on"]), (t["state_heating"], "boiler", "grey", ["off"])]
    starts = hub.get("burner_starts_last_hour")
    beside = (_tile(starts, t["starts_hour"], ICONS["burner_starts"]) if starts
              else _tile(essential("pressure"), t["pressure"], ICONS["pressure"]))
    gauge = ({"type": "gauge", "entity": modulation, "name": t["modulation"], "min": 0, "max": 100, "needle": False}
             if modulation else None)
    return _filled(_section_known(
        [code, doing, flow or back, modulation or (beside or {}).get("entity")],
        _heading(t["now"], ICONS["now"]),
        _boiler_status_card(t, code),
        *(_wide(_tile(doing, name, ICONS[icon], color=color,
                      visibility=[{"condition": "state", "entity": doing, "state": states}]))
          for name, icon, color, states in (tiles if doing else ())),
        *_pair(_tile(flow, t["flow_short"], ICONS["flow"]), _tile(back, t["return_short"], ICONS["return"])),
        # The gauge needs two grid rows; the tile beside it takes the same, so the pair is one even row.
        *_pair(gauge, beside, rows=2 if gauge else None)))


def _hot_water_section(t, hub, fields, essential):
    """Hot water (dashboard-spec §5.4): its temperature next to its target, today's taps, keeping warm and burner
    time, and what the boiler did in the last 24 hours with one note on tapping and keeping warm."""
    measured = essential("dhw")
    target = fields.get("reported_dhw_target") or fields.get("selected_dhw_temperature")
    today = [hub[key] for key in DHW_TODAY if key in hub]
    return _filled(_section_known(
        [measured, *today, hub.get("boiler_activity")],
        _heading(t["group_dhw"], ICONS["hot_water"]),
        *_pair(_tile(measured, t["dhw"], ICONS["dhw"]), _tile(target, t["dhw_target_short"], ICONS["dhw_target"])),
        _known_entities_card(today) if today else None,
        *_hot_water_use_cards(t, hub, fields.get("heating_active"))))


def _value_tile(entity_id, name, icon, color=None):
    """A boiler value, shown only while it has one. Without the E32 the "Heating" tile says why,
    instead of a row of "Unavailable" tiles."""
    return _tile(entity_id, name, icon, color=color, visibility=_known(entity_id)) if entity_id else None


def _wanting_card(t, request):
    """Which rooms want heat and the boiler request, as the E32's dashboard shows it (rc.3, owner's wish).

    "1 room wants heat", then each such room with its temperature and target, then the request.
    From the heat request's ``rooms`` attribute, so it follows the E32 without regenerating.
    """
    if not request:
        return None
    quoted = json.dumps(request)

    def number(value):
        return "{{ ('%.1f' % (" + value + " | float)) | replace('.', " + json.dumps(t["decimal"]) + ") }}"

    return {"type": "markdown", "content": (
        "{% set wanting = (state_attr(" + quoted + ", 'rooms') or []) | selectattr('demand', 'eq', true) | list %}"
        "### {% if wanting | length == 1 %}" + t["wanting_one"]
        + "{% elif wanting %}" + t["wanting_many"].replace("{n}", "{{ wanting | length }}")
        + "{% else %}" + t["wanting_none"] + "{% endif %}\n"
        "{% for room in wanting %}- **{{ room.name }}**"
        "{% if room.temperature is number and room.setpoint is number %}: "
        + number("room.temperature") + " → " + number("room.setpoint") + " °C{% endif %}\n{% endfor %}"
        "{% if states(" + quoted + ") | float(0) > 0 %}\n" + t["boiler_request"] + ": "
        + number("states(" + quoted + ")") + " °C{% endif %}")}


def _holiday_card(t, select):
    """The next holiday (E32 rc.4, house.holidays.v1): "Holiday from 20 Dec to 3 Jan", or "On holiday until 3 Jan"
    while it runs. From the house mode select's ``holidays`` attribute, so it follows the E32 without regenerating;
    empty (and hidden) without a planned holiday or on firmware without them. The first holiday only once there is
    one: Home Assistant's markdown card renders strictly, where "first" of an empty list is an error that left an
    empty card standing (and an error in the log every 30 s).
    """
    if not select:
        return None

    def day(name):
        return "{{ " + name + ".day }} {{ months[" + name + ".month - 1] }}"

    return {"type": "markdown", "show_empty": False, "content": (
        "{% set holidays = state_attr(" + json.dumps(select) + ", 'holidays') or [] %}"
        "{% if holidays %}{% set h = holidays[0] %}{% set months = " + json.dumps(t["months"], ensure_ascii=False)
        + ".split(',') %}"
        "{% set f = as_local(as_datetime(h['from'])) %}{% set u = as_local(as_datetime(h['until'])) %}"
        "{% if f <= now() %}" + t["holiday_now"].replace("{until}", day("u"))
        + "{% else %}" + t["holiday_next"].replace("{from}", day("f")).replace("{until}", day("u"))
        + "{% endif %}{% endif %}")}


def _split(text):
    """(first sentence, the rest) of a note; the rest is "" for a note of one sentence."""
    parts = re.split(r"(?<=[.!?])\s+(?=\S)", text.strip(), maxsplit=1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _details(t, rest):
    """The longer part of a note behind "More", so a phone shows one short sentence."""
    return "\n\n<details><summary>" + t["more"] + "</summary>\n\n" + rest + "\n\n</details>" if rest else ""


def _note(t, text, visibility=None):
    """A note of one sentence; whatever follows it sits behind "More"."""
    first, rest = _split(text)
    card = {"type": "markdown", "content": first + _details(t, rest)}
    if visibility:
        card["visibility"] = visibility
    return card


def _tiles(*cards):
    """Tiles that appear together: pairs of half tiles, and an odd one out across the whole width."""
    cards = [card for card in cards if card]
    if len(cards) % 2:
        _wide(cards[-1])
    return cards


def _wide(card):
    """A card across the whole section (12 of 12 grid columns), so its state is not cut short."""
    if card is not None:
        card["grid_options"] = {"columns": 12}
    return card


def _full(card):
    """A card across the whole section also where the section spans both columns of a wide view (the Overview's:
    Home Assistant gives it 24 grid columns there, so 12 would be half the width); on a phone the same as _wide."""
    if card is not None:
        card["grid_options"] = {"columns": "full"}
    return card


def _pair(first, second, rows=None):
    """Two half-width cards that appear together on one condition, while the first has a value, side by side in one
    row; one alone takes the whole width (dashboard-spec §1). ``rows``: their height in grid rows, set on both so the
    row is even (a figure or a gauge needs two, and so does a tile beside one)."""
    cards = [card for card in (first, second) if card]
    for card in cards:
        card["visibility"] = _known(cards[0]["entity"])
        if len(cards) == 1:
            card["grid_options"] = {"columns": 12, **({"rows": rows} if rows else {})}
        elif rows:
            card["grid_options"] = {"columns": 6, "rows": rows}
    return cards


def _statistic(entity_id, name, icon):
    """Today's figure of a running total (its change since local midnight): today's gas or burner."""
    if not entity_id:
        return None
    return {"type": "statistic", "entity": entity_id, "name": name, "icon": icon,
            "period": {"calendar": {"period": "day"}}, "stat_type": "change"}


def _tile(entity_id, name=None, icon=None, features=None, visibility=None, color=None, tap_action=None,
          state_content=None):
    if entity_id is None:
        return None
    card = {"type": "tile", "entity": entity_id}
    if name:
        card["name"] = name
    if icon:
        card["icon"] = icon
    if color:
        card["color"] = color
    if tap_action:
        card["tap_action"] = tap_action
    if state_content:
        card["state_content"] = state_content
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
        self._mode = None  # the E32's last reported mode (shadow / active), kept while it is silent
        self._candidate: LovelaceStorage | None = None  # registered, panel not yet (async_start)
        # This entry's entities and devices at the last build: registry events about others never rebuild.
        self._entity_ids: set[str] = set()
        self._device_ids: set[str] = set()
        self._registry_timer = None  # the debounced rebuild after registry or language changes

    async def async_start(self) -> None:
        """Register a Lovelace panel without changing the user's dashboards.

        Optional: a failure is logged and undone, never failing the installation's setup.
        """
        try:
            await self._async_start()
        except Exception:  # noqa: BLE001 - the dashboard is optional
            _LOGGER.exception("The OpenThermostat dashboard could not be started; "
                              "the installation works without it and tries again on its next start")
            candidate, self._candidate = self._candidate, None
            if self._store is not None:
                await self.async_stop()
            elif candidate is not None and self.hass.data[LOVELACE_DATA].dashboards.get(self.path) is candidate:
                self.hass.data[LOVELACE_DATA].dashboards.pop(self.path, None)
        self._candidate = None

    async def _async_start(self) -> None:
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry and is_product(entry):
            # Normally done once in async_setup; again here (idempotent) so the cards'
            # modules come back after the last installation was removed and a new one added.
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
        dashboards[self.path] = self._candidate = store
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
        self._listen()
        self._watch_hub()

    @callback
    def _listen(self) -> None:
        """Rebuild after registry changes of this entry's own entities and devices and after a change of
        language or units; the registry events of every other integration pass by (R4-11)."""
        self._unsubscribe = [
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_updated,
                                       event_filter=self._own_entity_event),
            self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._registry_updated,
                                       event_filter=self._own_device_event),
            self.hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, self._registry_updated,
                                       event_filter=self._language_or_units),
        ]

    @callback
    def _own_entity_event(self, data) -> bool:
        """An entity of this entry was created, renamed, enabled or removed."""
        entity_id = data.get("entity_id")
        if entity_id in self._entity_ids or data.get("old_entity_id") in self._entity_ids:
            return True
        item = er.async_get(self.hass).async_get(entity_id) if type(entity_id) is str else None
        return item is not None and item.config_entry_id == self.entry_id

    @callback
    def _own_device_event(self, data) -> bool:
        """A device of this entry was created, renamed or removed."""
        device_id = data.get("device_id")
        if device_id in self._device_ids:
            return True
        device = dr.async_get(self.hass).async_get(device_id) if type(device_id) is str else None
        return device is not None and self.entry_id in device.config_entries

    @staticmethod
    @callback
    def _language_or_units(data) -> bool:
        """The language or the unit system changed (an update without data: Home Assistant starts)."""
        return not data or "language" in data or "unit_system" in data

    async def async_stop(self) -> None:
        """Remove the panel when the integration is unloaded or disabled."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        if self._registry_timer is not None:
            self._registry_timer()
            self._registry_timer = None
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
        """Follow entity creation, entity ID and device name changes, and the HA language.

        Once per burst: the rebuild follows REGISTRY_SETTLE_SECONDS after the first event (a start
        creates this entry's entities one by one, R4-11).
        """
        self._watch_hub()
        if self._registry_timer is None and self._store is not None:
            self._registry_timer = async_call_later(self.hass, REGISTRY_SETTLE_SECONDS, self._registry_settled)

    @callback
    def _registry_settled(self, _now=None) -> None:
        self._registry_timer = None
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
        # The boiler profile (which fields this boiler has) decides the boiler tiles: rebuild when it
        # changes; the hub reports often enough to notice it within seconds.
        from .v1_boiler_fields import boiler_cache
        cache = boiler_cache(self.hass, self.entry_id)
        signature = (self._signature(self._hub), getattr(cache, "profile_sequence", None))
        if signature != self._hub_signature:
            self._hub_signature = signature
            self._schedule_refresh()

    @staticmethod
    def _signature(hub):
        if hub is None or not hub.fresh:
            return None
        plan = hub.plan.plan if hub.plan is not None else None
        # The E32 counts every plan save in its revision: no need to compare the whole plan (R4-11).
        # A room's state too: switched on or off, it moves into or out of the Overview's house card (rc.5).
        return (hub.status.get("mode"),
                tuple((key, room.get("name"), room.get("source"), room.get("state"))
                      for key, room in hub.rooms.items()),
                tuple((key, sensor.get("name")) for key, sensor in hub.ble.items()),
                plan.get("revision") if plan else None)

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
        self._entity_ids = {item.entity_id for item in entries}
        self._device_ids = {device.id for device in dr.async_entries_for_config_entry(dr.async_get(self.hass),
                                                                                       self.entry_id)}
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
        # No tiles for values this boiler does not have (its boiler profile).
        from .v1_boiler_fields import boiler_field_shown
        native_fields = {name: entity_id for name, entity_id in native_fields.items()
                         if boiler_field_shown(self.hass, self.entry_id, name)}
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
            if not boiler_field_shown(self.hass, self.entry_id, field):
                return None  # not on this boiler: no older hub tile either
            return native_fields.get(field) or (hub_entities.get(metric) if metric else None)

        parts = self._heating_sections(t, entries, hub_entities, native_fields, essential, registry, e32_rooms, legacy)
        boiler, raw, thermostat = self._boiler_sections(t, hub_entities, native_fields, graph, essential)
        diagnostics = self._diagnostics_sections(t, registry, hub_entities, raw, thermostat)

        def view(title, path, sections, columns=2, **more):
            # Sections side by side, a short one filling the gap under itself (never half-empty rows inside).
            # No view icon: Home Assistant then shows the view's title in the tab bar ("Overzicht · Ruimtes · ..."),
            # as in the approved sketches; with an icon a tab is only that icon.
            return {"title": title, "path": path, "type": "sections", "max_columns": columns,
                    "dense_section_placement": True, "sections": sections, **more}
        back = "/" + self.path + "/heating"
        comparison = parts["comparison"]
        return {
            "views": [
                # 1. Overview: the house, the problem (only while there is one) and one card per room.
                # Its sections span both columns and stack: a short House section never sits beside the
                # long Rooms section with empty space under it.
                *([view(t["overview"], "heating",
                        [{**section, "column_span": 2} for section in parts["overview"]])] if parts["overview"] else []),
                # 2. Rooms: thermostat, the day, sensors, windows, people and what it learned, per room.
                *([view(t["rooms"], "rooms", parts["rooms"])] if parts["rooms"] else []),
                *([{
                    "title": t["room_settings"],
                    "panel": True,
                    "path": "week",
                    "cards": [{"type": ROOM_CARD_TYPE,
                               "entry_id": self.entry_id, "room_id": sub.data["room_id"]}
                              for sub in legacy[:1]],
                }] if product and not e32_rooms else []),
                *[{"title": sub.title, "path": "room-" + sub.data["room_id"],
                   "subview": True, "panel": True,
                   "cards": [{"type": ROOM_CARD_TYPE, "entry_id": self.entry_id,
                              "room_id": sub.data["room_id"]}]}
                  for sub in legacy],
                # 3. The E32 rooms' visual week planner (e32_week.py), one card for all rooms.
                *([{"title": t["week_program"], "path": "week-program", "panel": True,
                    "cards": [{"type": E32_WEEK_CARD_TYPE, "entry_id": self.entry_id}]}] if e32_rooms else []),
                # 4. Boiler: everything about the boiler in one place.
                view(t["boiler_view"], "boiler", boiler),
                # 5. What it learned, Smart warm-up, weather compensation, short cycling and the takeover check.
                *([view(t["learning_view"], LEARNED_PATH, parts["learning"])] if parts["learning"] else []),
                # 6. Diagnostics last.
                view(t["diagnostics"], "diagnostics", diagnostics),
                # Trial run only: reached from the "E32 compared with your thermostat" link and the
                # "Ready to take over?" tile in the learning view.
                *([view(t["comparison_view"], COMPARISON_PATH, comparison, subview=True,
                        back_path=back)] if comparison else []),
            ]
        }

    def _trial_run(self):
        """Whether the E32 runs the trial run (shadow mode), from its live status, never the registry.

        The last reported mode counts while the E32 is silent, so an outage does not drop the
        Comparison subview; nothing reported yet is no trial run. A change of mode rebuilds the
        dashboard (_signature), so this follows the E32 by itself.
        """
        heating_hub = self._heating_hub()
        if heating_hub is not None and heating_hub.fresh:
            self._mode = heating_hub.status.get("mode")
        return self._mode == "shadow"

    def _heating_sections(self, t, entries, hub, fields, essential, registry, e32_rooms, legacy):
        """The sections of the views that come from the E32's heating: {overview, rooms, learning, comparison}.

        Overview: the house (mode, rooms that want heat and the boiler request, the problem with its reason, only
        while there is one) and one status card per room. Rooms: one section per room (thermostat, its day, sensors,
        windows and people, what it learned), then the sensors that feed no single room. Learning, as the owner's
        sketch: what the E32 knows, your boiler, water temperature by outdoor temperature, yesterday in figures, what
        stood out, the free heat, Smart warm-up and Weather compensation; then what it learned (and how) and who
        controls the boiler (the burner as information and the takeover check). The Boiler view is _boiler_sections.

        The comparison with the thermostat on the boiler bus means something only in the trial run
        and only while such a thermostat is heard: the Comparison subview exists only in the trial
        run (the E32's live mode, _trial_run), and its link and comparison cards show only while the
        agreement has a value (it has none without a thermostat). Once the E32 controls the boiler,
        the comparison sensors are removed (native_entity_cleanup.note_heating_status).
        """
        request = hub.get("heat_request")
        # The house mode (beta.23, e32_house.py): automatic, at home, away, holiday, switched right here.
        house_mode = registry.async_get_entity_id("select", DOMAIN, f"{self.prefix}_house_mode")
        e32_room_entities = self._e32_rooms(entries)
        flow = self._flow_entities(entries)
        problem = hub.get("heating_problem")
        trial = self._trial_run()
        sub_path = "/" + self.path + "/" + COMPARISON_PATH
        from .heating_link import label
        heating_hub = self._heating_hub()

        # -- Overview ------------------------------------------------------------------------------
        on = [{"condition": "state", "entity": problem, "state": "on"}] if problem else None
        # rc.5 (P11): the house card (frontend/house-card.js) heads the House section: what the boiler does now (a
        # problem first, with its reason, a tap to Repairs and all reasons inside), today in figures and the day so
        # far, read from Home Assistant alone. It replaces the rooms-that-want-heat card and the problem tile with its
        # reasons, which stay as before only without a heat request and boiler activity (then there is no card). A
        # house with exactly one room switched on shows that room in the card (its Reason sensor), the others under
        # "Other rooms"; _signature follows the rooms' state, so switching a room on or off rebuilds the dashboard.
        from .room_overview import HOUSE_CARD_TYPE
        activity = hub.get("boiler_activity")
        reported = heating_hub.rooms if heating_hub is not None else {}
        switched_on = [room_id for room_id in e32_room_entities
                       if (reported.get(room_id) or {}).get("state") != "inactive"]
        inline = (switched_on[0] if (request or activity) and len(switched_on) == 1
                  and e32_room_entities[switched_on[0]].get("reason") else None)
        reads = {"request": request, "activity": activity, "heating": fields.get("heating_active"),
                 "flow": essential("flow"), "hot_water": fields.get("dhw_active"), "taps": hub.get("dhw_taps_today"),
                 "gas": [hub[key] for key in ("heating_gas", "hot_water_gas") if key in hub],
                 "starts": hub.get("daily_burner_starts"), "mode": house_mode, "problem": problem,
                 "rooms": [{"entity": e32_room_entities[inline]["reason"],
                            "name": self._room_name(inline, heating_hub, label)}] if inline else None}
        # Across the whole view on a wide screen too, as the sketch (the section spans both columns).
        house_card = (_full({"type": HOUSE_CARD_TYPE, **{key: value for key, value in reads.items() if value}})
                      if request or activity else None)
        before = () if house_card else (
            # Which rooms want heat and the boiler request: one card whose text follows the E32.
            _wanting_card(t, request),
            # A problem names itself ("Waiting for your confirmation"), and a tap leads to the fix in Repairs.
            _wide(_tile(problem, t["problem"], visibility=on, state_content=["reason"],
                        tap_action={"action": "navigate", "navigation_path": "/config/repairs"})),
            {"type": "markdown", "visibility": on, "content": (
                "<details><summary>" + t["problem_more"] + "</summary>\n\n{% for reason in state_attr("
                + json.dumps(problem) + ", 'reasons') or [] %}- {{ reason }}\n{% endfor %}\n\n</details>")}
            if problem else None)
        house = _section(
            _heading(t["house"], ICONS["house"]),  # one icon per concept (dashboard-spec §1)
            house_card,
            # Named: without a name the tile showed the device name, cut short on a phone. Under the card, across the
            # view as the card is (half of it would stand alone in its row on a wide screen).
            _full(_tile(house_mode, t["house_mode"], "mdi:home-account", features=[{"type": "select-options"}],
                        color="teal")),
            # rc.4: the next holiday, only while one is planned.
            _full(_holiday_card(t, house_mode)),
            *before)
        from .e32_comfort import room_contacts, room_persons
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        ble = self._e32_ble(entries)
        in_room = {}  # Bluetooth sensor -> the one room it feeds (None: several rooms)
        for room_id in e32_room_entities:
            plan_room = self._plan_room(heating_hub, room_id)
            for source in (plan_room or {}).get("sources", []):
                if type(source) is dict and source.get("type") == "ble" and source.get("id") in ble:
                    in_room[source["id"]] = None if source["id"] in in_room else room_id
        names = {room_id: self._room_name(room_id, heating_hub, label) for room_id in e32_room_entities}
        room_cards = []
        for room_id, room in e32_room_entities.items():
            if room_id == inline:  # rc.5 (P11): inside the house card
                continue
            if room.get("reason"):
                room_cards.append({"type": ROOM_STATUS_CARD_TYPE, "entity": room["reason"], "name": names[room_id]})
            else:  # a registry without the Reason sensor (older integration): the temperature at least
                room_cards.append(_wide(_tile(room.get("temperature") or room.get("setpoint"), names[room_id],
                                              "mdi:home-thermometer-outline")))
        overview = [section for section in (
            house if len(house["cards"]) > 1 else None,
            _section(_heading(t["other_rooms"] if inline else t["rooms"], "mdi:thermostat"), *room_cards)
            if any(room_cards) else None) if section]

        # -- Rooms ---------------------------------------------------------------------------------
        learned_overview = hub.get("learned_overview")
        rooms = [self._room_section(t, room_id, room, heating_hub, names[room_id], ble, in_room, entry, learned_overview,
                                    (room_contacts, room_persons))
                 for room_id, room in e32_room_entities.items()]
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
            rooms.append(_section(_heading(t["legacy_rooms"], "mdi:thermostat"), *legacy_cards))
        loose = [{"type": "glance", "columns": 3, "state_color": False,
                  "title": self._device_name((DOMAIN, f"{self.prefix}_e32_ble_{sensor_id}"), sensor_id),
                  "entities": [{"entity": metrics[key], "name": t[key]} for key in BLE_KEYS if key in metrics]}
                 for sensor_id, metrics in sorted(ble.items()) if not in_room.get(sensor_id)]
        if loose:
            rooms.append(_section(_heading(t["bluetooth"], "mdi:bluetooth"), *loose))

        # -- Learning and settings -----------------------------------------------------------------
        # In the order of the owner's sketch (rc.5): what the E32 knows, your boiler in one sentence and water
        # temperature by outdoor temperature, then yesterday in figures, what stood out yesterday, the free heat and
        # Smart warm-up and weather compensation as rows; after them what it learned and who controls the boiler.
        learning = [section for section in (_knowledge_section(t, hub.get("knowledge")),
                                            _boiler_section(t, hub.get("boiler_response")),
                                            _curve_section(t, flow.get("curve"))) if section]
        # Yesterday in figures, once (dashboard-spec §6): the scoreboard (E32 rc.4) and the daily summary, with the
        # gas in the gas sensor's unit. Is it getting better? Only once one figure has a value. The headline figures
        # large (rc.5, as the owner's sketch): the warm on time of the lead room, the first room switched on that
        # has one (in the owner's house the room inside the house card).
        heating_gas = hub.get("heating_gas")
        gas_state = self.hass.states.get(heating_gas) if heating_gas and self.hass is not None else None
        lead = next((room_id for room_id in [*switched_on, *e32_room_entities]
                     if e32_room_entities[room_id].get("warm_on_time")), None)
        yesterday = _yesterday_figures(
            t, {room_id: {key: room[key] for key in ("warm_on_time", "overshoot") if room.get(key)}
                for room_id, room in e32_room_entities.items() if room.get("warm_on_time") or room.get("overshoot")},
            names, {key: hub[key] for key in SCOREBOARD_HOUSE if key in hub}, hub.get("daily_summary"),
            hub.get("daily_missed_comfort"), gas_state.attributes.get("unit_of_measurement") if gas_state else None,
            lead)
        if yesterday:
            learning.append(yesterday)
        learning += [section for section in (
            _noticed_section(t, learned_overview), _free_heat_section(t, learned_overview),
            _settings_section(t, flow, "/config/integrations/integration/" + DOMAIN if e32_rooms else None,
                              "/" + self.path + "/week-program" if e32_rooms else None)) if section]
        # The sketch's two columns on a wide screen, within the sections view's own placement (in this order, dense,
        # a row as tall as its tallest section): yesterday spans two rows, so the curve and what stood out under it
        # fill the column beside it, your boiler above it and the settings under it. A phone stacks them in order.
        if yesterday:
            yesterday["row_span"] = 2
        # What it learned, with how it learns as the note of its first section, only while the E32 reports it.
        learning_entity = next((room["learning"] for room in e32_room_entities.values() if room.get("learning")), None)
        how = None
        if learning_entity:
            quoted = json.dumps(learning_entity)
            how = {"type": "markdown", "visibility": _known(learning_entity), "content": (
                t["learning_note"] + "{% if not state_attr(" + quoted + ", 'applied') %}"
                + _details(t, t["advice_only"]) + "{% endif %}")}
        learning += _learned_sections(t, learned_overview, how)
        # The comparison entities exist only once the E32 saw a thermostat to compare with; outside
        # the trial run a record left behind leads nowhere.
        agreement = hub.get("shadow_agreement_today") if trial else None
        readiness = hub.get("takeover_readiness")  # E32 1.0: ready to take over? (shadow mode only)
        # The Comparison subview: the readiness check and the comparison, in the trial run only.
        subview = trial and bool(readiness or agreement)
        control = _section(
            _heading(t["who_controls"], ICONS["boiler"]),
            self._explain_card(t, request) if request or e32_room_entities else None,
            # Short cycling is information, not a fault: the E32 deals with it by itself.
            self._cycling_card(t, hub.get("burner_short_cycling")),
            # Ready to take over? Leads to the Comparison subview, which opens with the check.
            # The whole width: its state ("Waiting for more data") was cut short on a phone.
            _wide(_tile(readiness, t["readiness"], "mdi:clipboard-check-outline",
                        visibility=_known(readiness, ("not_applicable",)),
                        tap_action={"action": "navigate", "navigation_path": sub_path} if subview else None)),
            # A bare percentage meant nothing here: a link to the comparison, which explains it; only
            # while a thermostat is heard to compare with (the agreement has a value).
            _link(t["compare_link"], "mdi:compare-horizontal", sub_path, _known(agreement)) if agreement else None)
        if len(control["cards"]) > 1:
            if all(card.get("visibility") for card in control["cards"][1:]):
                # No sentence on who controls it (no heat request and no rooms): shown while one of its cards is.
                control["visibility"] = [{"condition": "or", "conditions": [
                    {"condition": "and", "conditions": card["visibility"]} for card in control["cards"][1:]]}]
            learning.append(control)

        # -- Comparison subview (trial run only): the readiness check and the E32 next to the thermostat --
        comparison = []
        if readiness and subview:
            hidden = _known(readiness, ("not_applicable",))
            comparison.append(_section(_heading(t["readiness"], "mdi:clipboard-check-outline", visibility=hidden),
                                       _readiness_card(t, readiness)))
        if agreement:
            compared = []
            compare_entities = [{"entity": entity_id, "name": name} for entity_id, name in (
                (request, t["e32_request"]),
                (fields.get("thermostat_requested_flow_temperature"), t["thermostat_request"]),
                (essential("flow"), t["flow"])) if entity_id]
            heating_time = [hub[key] for key in ("shadow_e32_heating_time_today", "shadow_tado_heating_time_today")
                            if key in hub]
            compare = _section(
                _heading(t["compare"], "mdi:compare-horizontal"),
                # The whole width, so the E32 and thermostat tiles below stand side by side in pairs.
                _wide(_tile(agreement, t["agreement"], "mdi:compare-horizontal", color="teal")),
                _tile(hub.get("shadow_e32_heating_time_today"), t["heating_time_e32"], "mdi:timer-outline"),
                _tile(hub.get("shadow_tado_heating_time_today"), t["heating_time_thermostat"], "mdi:timer-outline"),
                _tile(hub.get("shadow_e32_starts_today"), t["starts_e32"], "mdi:counter"),
                _tile(hub.get("shadow_tado_starts_today"), t["starts_thermostat"], "mdi:counter"),
                {"type": "history-graph", "hours_to_show": 24, "entities": compare_entities}
                if compare_entities else None,
            )
            if len(compare["cards"]) > 1:
                compared.append(compare)
            names = {"shadow_e32_heating_time_today": t["e32"], "shadow_tado_heating_time_today": t["thermostat"]}
            if heating_time:
                compared.append(_section(
                    _heading(t["heating_per_day"], "mdi:chart-bar"),
                    {"type": "statistics-graph", "entities": [
                        {"entity": hub[key], "name": name} for key, name in names.items() if key in hub],
                     "stat_types": ["max"], "period": "day", "days_to_show": 7, "chart_type": "bar"}))
            # Only while a thermostat is heard to compare with: no "Unavailable" tiles without one.
            for card in (card for section in compared for card in section["cards"]):
                card.setdefault("visibility", _known(agreement))
            comparison.extend(compared)
        return {"overview": overview, "rooms": rooms, "learning": learning, "comparison": comparison if subview else []}

    @staticmethod
    def _explain_card(t, request):
        """One sentence on who controls the boiler (the rest behind "More"), from the heat request's mode."""
        if not request:
            return _note(t, t["how"])
        quoted = json.dumps(request)
        branches = (("{% if mode == 'active' and state_attr(" + quoted + ", 'control') == 'awaiting_confirmation' %}",
                     t["next"]),
                    ("{% elif mode == 'active' %}", t["active"]), ("{% elif mode == 'shadow' %}", t["shadow"]))
        head = ("".join(condition + _split(text)[0] for condition, text in branches)
                + "{% else %}" + t["how"] + "{% endif %}")
        rest = "".join(condition + _split(text)[1] for condition, text in branches) + "{% endif %}"
        return {"type": "markdown", "content": (
            "{% set mode = state_attr(" + quoted + ", 'mode') %}" + head
            + "\n\n<details><summary>" + t["more"] + "</summary>\n\n" + rest + " " + t["how"] + "\n\n</details>")}

    @staticmethod
    def _cycling_card(t, entity_id):
        """Short cycling as information (the E32 lengthens the burner's rest step by step), never as a fault."""
        if not entity_id:
            return None
        quoted = json.dumps(entity_id)
        return {"type": "markdown", "visibility": _known(entity_id), "content": (
            "{% if is_state(" + quoted + ", 'on') %}<ha-icon icon=\"mdi:sync\"></ha-icon> **" + t["short_cycling"]
            + "**\n\n" + t["cycling_info"] + "{% else %}<ha-icon icon=\"mdi:check-circle-outline\"></ha-icon> "
            + t["cycling_ok"] + "{% endif %}")}

    @staticmethod
    def _plan_room(heating_hub, room_id):
        plan = getattr(heating_hub, "plan", None) if heating_hub is not None else None
        return plan.room(room_id) if plan is not None else None

    def _room_name(self, room_id, heating_hub, label):
        reported = heating_hub.rooms.get(room_id) if heating_hub is not None else None
        return self._device_name((DOMAIN, f"{self.prefix}_e32_room_{room_id}"),
                                 label(reported) if reported else room_id)

    def _room_section(self, t, room_id, room, heating_hub, name, ble, in_room, entry, learned, comfort):
        """One E32 room: its thermostat, the last 24 hours, its sensors, windows and people, and what it learned.

        Every card is as wide as the section, or a tidy pair of tiles that appear together. An inactive room
        stays compact; without any working source, a hint with "Choose a source" first and "Remove room" second
        (both in Home Assistant's own pages).
        """
        room_contacts, room_persons = comfort
        state = room.get("state")
        active = [{"condition": "state", "entity": state, "state_not": "inactive"}] if state else None
        inactive = [{"condition": "state", "entity": state, "state": "inactive"}] if state else None
        sensor = next((metrics for sensor_id, metrics in sorted(ble.items()) if in_room.get(sensor_id) == room_id), {})
        badges = []
        if room.get("demand"):
            badges.append({"type": "entity", "entity": room["demand"], "show_state": True, "show_icon": True,
                           "color": "deep-orange", **({"visibility": active} if active else {})})
        if room.get("status"):
            badges.append({"type": "entity", "entity": room["status"], "show_state": True, "show_icon": True,
                           "color": "amber", "visibility": [{"condition": "state", "entity": room["status"],
                                                             "state_not": ["ok", "inactive"]}]})
        if state:
            badges.append({"type": "entity", "entity": state, "show_state": True, "show_icon": True,
                           "icon": "mdi:power-off", "visibility": inactive})
        if room.get("valve_problem"):  # a radiator valve with a low battery or not reporting
            badges.append({"type": "entity", "entity": room["valve_problem"], "show_state": False, "show_icon": True,
                           "color": "red", "visibility": [{"condition": "state", "entity": room["valve_problem"],
                                                           "state": "on"}]})
        if sensor.get("battery"):  # only when it needs attention
            badges.append({"type": "entity", "entity": sensor["battery"], "show_state": True, "show_icon": True,
                           "color": "red", "visibility": [{"condition": "numeric_state", "entity": sensor["battery"],
                                                           "below": 20}]})
        own = room.get("thermostat")
        thermostat = own or self._room_thermostat(room_id)
        # The E32's own measurement only where the dial does not show it (dashboard-spec §3): never next to the
        # room's own climate, and next to another thermostat only while the E32 measures (also) elsewhere; a room
        # whose only source is the thermostat it follows shows its temperature once, on the dial.
        measured = thermostat is None or (not own and self._measured_elsewhere(room_id, heating_hub, thermostat))
        working = self._room_has_working_source(room_id, heating_hub)
        history = [{"entity": room[key], "name": t[label]} for key, label in (("temperature", "room_measured"),
                                                                              ("setpoint", "room_target"))
                   if room.get(key)]
        when_active = {"visibility": active} if active else {}
        # Sensors, windows and people: the Bluetooth sensor of this room, its window and door contacts, its
        # persons and the other Home Assistant sources of its temperature, as rows with their own names.
        rows = [{"entity": sensor[key], "name": t[key]} for key in BLE_KEYS if sensor.get(key)]
        plan_room = self._plan_room(heating_hub, room_id) or {}
        extra = [*(room_contacts(entry, room_id) if entry is not None else []),
                 *(room_persons(entry, room_id) if entry is not None else []),
                 *(source["id"] for source in plan_room.get("sources", [])
                   if type(source) is dict and source.get("type") == "ha" and type(source.get("id")) is str
                   and not source["id"].startswith("climate."))]
        seen = {row["entity"] for row in rows}
        rows += [{"entity": entity_id} for entity_id in dict.fromkeys(extra) if entity_id not in seen]
        cards = [
            _heading(name, "mdi:home-thermometer-outline", badges),
            # An inactive room stays compact: its heading says "Off"; no dial, so no way to switch it on here.
            {"type": "thermostat", "entity": thermostat, **when_active} if thermostat else None,
            # The E32's own measurement where the dial does not show it, the target without a dial and how far its
            # radiator valves are open: pairs, an odd one across.
            *_tiles(_tile(room.get("temperature"), t["measured"], visibility=active) if measured else None,
                    None if thermostat else _tile(room.get("setpoint"), t["target"], visibility=active),
                    _tile(room["valve_position"], t["valve_position"], "mdi:valve", visibility=active)
                    if room.get("valve_position") else None),
            {"type": "history-graph", "hours_to_show": 24, "entities": history, **when_active}
            if history else None,
            # The whole width: a date and time do not fit half a section on a phone.
            _wide(_tile(room.get("inactive_until"), t["off_until"],
                        visibility=inactive + _known(room["inactive_until"])))
            if inactive and room.get("inactive_until") else None,
            _heading(t["sensors_presence"], "mdi:window-open-variant", style="subtitle") if rows else None,
            {"type": "entities", "entities": rows} if rows else None,
            *_learning_cards(t, room, active, learned, [name]),
        ]
        if inactive and working:
            cards += [{"type": "markdown", "content": t["room_off"], "visibility": inactive},
                      _link(t["settings"].format(room=name), "mdi:cog",
                            "/config/integrations/integration/" + DOMAIN, inactive)]
        elif inactive:
            from homeassistant.helpers import issue_registry as ir
            integration = "/config/integrations/integration/" + DOMAIN
            repair = ir.async_get(self.hass).async_get_issue(DOMAIN, f"e32_room_choose_source_{self.entry_id}_{room_id}")
            cards += [
                _note(t, t["room_no_source"].format(room=name), inactive),
                _link(t["choose_source"], "mdi:thermometer-plus", "/config/repairs" if repair else integration, inactive),
                _link(t["remove_room"], "mdi:delete-outline", integration, inactive),
            ]
        return _section(*cards)

    def _measured_elsewhere(self, room_id, heating_hub, thermostat):
        """Whether the E32 measures the room (also) from another source than ``thermostat``, the climate its dial
        shows: a Bluetooth sensor or another Home Assistant entity in its plan; before the plan is read, the source
        it reports using now."""
        plan_room = self._plan_room(heating_hub, room_id)
        if plan_room:
            return any(not (source.get("type") == "ha" and source.get("id") == thermostat)
                       for source in plan_room.get("sources", []) if type(source) is dict)
        reported = (heating_hub.rooms.get(room_id) or {}).get("source") if heating_hub is not None else None
        return reported is not None and reported != thermostat

    def _room_has_working_source(self, room_id, heating_hub):
        """Any source of the room that measures now: a Bluetooth sensor with a reading, or an HA entity with a state."""
        plan_room = self._plan_room(heating_hub, room_id)
        if not plan_room:
            return True  # plan not read yet: no hint
        for source in plan_room.get("sources", []):
            if type(source) is not dict:
                continue
            if source.get("type") == "ble":
                sensor = heating_hub.ble.get(source.get("id")) or {}
                if isinstance(sensor.get("temperature"), (int, float)):
                    return True
            elif type(source.get("id")) is str:
                state = self.hass.states.get(source["id"])
                if state is not None and state.state not in ("unavailable", "unknown"):
                    return True
        return False

    def _flow_entities(self, entries):
        """The heating curve and learning entities on the product device: {key: entity id}."""
        head = f"{self.prefix}_flow_"
        return {item.unique_id.removeprefix(head): item.entity_id for item in entries
                if item.unique_id.startswith(head) and item.unique_id.removeprefix(head) in FLOW_KEYS
                and item.domain != "number"}  # the design flow is a select (never a 0 °C number)

    def _boiler_sections(self, t, hub, fields, graph, essential):
        """The Boiler view (dashboard-spec §5) and what of the boiler belongs on Diagnostics: (sections, the raw
        boiler fields, the thermostat on the bus).

        In this order: Now (the boiler in words and at a glance), the advice, Today and this week (the gas and the
        burner), Hot water, the last 24 hours, What the boiler reports (its values, one titled card per group) and
        the boiler settings. Every section hides as a whole while nothing in it has a value, so a boiler that never
        reports a value shows neither an "Unknown" nor a heading over nothing. Raw values the E32 does not check
        and the thermostat on the bus go to Diagnostics.
        """
        from .boiler_fields import INDEX_BY_NAME, quality
        sections = [_boiler_now(t, hub, fields, essential), _advice_section(t, hub.get("heating_advice")),
                    _energy_section(t, hub), _hot_water_section(t, hub, fields, essential)]
        raw = thermostat = None
        if fields:
            # Native cards only. Reported selected flow is NOT a controller request,
            # and burner modulation percentage is NOT measured kW or power factor.
            def order(name):
                # Table order; activity inferred from the state bits (quality 2) last in its group.
                index = INDEX_BY_NAME.get(name)
                return (index is not None and quality(index) == 2, index if index is not None else len(INDEX_BY_NAME),
                        name)
            groups = {}
            for name in sorted(fields, key=order):
                groups.setdefault(boiler_group(name), []).append(fields[name])
            raw, thermostat = groups.pop("raw", None), groups.pop("thermostat", None)
            hidden = {fields[name]: states for name, states in HIDDEN_STATES.items() if name in fields}
            # The last 24 hours: each graph once one of its series has a value, so a series the boiler does not
            # send never hides the others (an empty series draws no line).
            graphs = [card for card in (
                graph(t["flow_graph"], (("reported_selected_flow_temperature", t["flow_selection"]),
                                        ("measured_flow_temperature", t["measured_flow"]),
                                        ("measured_return_temperature", t["measured_return"])), fields),
                graph(t["modulation_graph"], (("reported_burner_modulation", t["modulation_series"]),), fields),
                graph(t["dhw_graph"], (("selected_dhw_temperature", t["dhw_selected"]),
                                       ("measured_dhw_temperature", t["dhw_measured"]),
                                       ("reported_dhw_target", t["dhw_target"])), fields)) if card]
            for card in graphs:
                card["visibility"] = _any_known([item["entity"] for item in card["entities"]])
            sections.append(_filled(_section_known([item["entity"] for card in graphs for item in card["entities"]],
                                                   _heading(t["history_24h"], ICONS["history"]), *graphs)))
            # What the boiler reports: one titled card per group (rows with a value), the first with the one note
            # on what these values are (dashboard-spec §5.6).
            reported = [key for key in REPORTED_GROUPS if groups.get(key)]
            cards = [_known_entities_card(groups[key], hidden, t["group_" + key]) for key in reported]
            if cards:
                cards.insert(1, _note(t, t["boiler_note"], _any_known(groups[reported[0]], hidden)))
            sections.append(_filled(_section_known(
                [entity for key in reported for entity in groups[key]],
                _heading(t["boiler_values"], ICONS["boiler"]), *cards, hidden=hidden)))
            # The boiler's own settings, read only, last, with when the boiler reports them (only when asked).
            settings = groups.get("settings")
            if settings:
                sections.append(_section_known(settings, _heading(t["group_settings"], ICONS["settings"]),
                                               _known_entities_card(settings, hidden),
                                               _note(t, t["settings_note"], _any_known(settings, hidden)), hidden=hidden))
        else:
            # An older integration without the boiler fields: what the hub reports, as graphs.
            legacy = _section(
                _heading(t["boiler"], ICONS["boiler"]),
                _note(t, t["legacy_boiler_note"]),
                graph(t["flow_graph"], (
                    ("boiler_selected_flow_temperature", t["flow_selection"]),
                    ("boiler_current_flow_temperature", t["current_flow"])), hub),
                graph(t["modulation_graph"], (("boiler_burner_power", t["modulation_series"]),), hub),
                graph(t["states_graph"], (
                    ("boiler_heating_active", t["state_heating"]),
                    ("boiler_hot_water_active", t["state_dhw"]),
                    ("boiler_burner_active", t["state_flame"]),
                    ("boiler_pump_active", t["state_pump"])), hub))
            # A heading and a note alone are no section.
            if any(card["type"] not in ("heading", "markdown") for card in legacy["cards"]):
                sections.append(legacy)
        return [section for section in sections if section], raw, thermostat

    def _diagnostics_sections(self, t, registry, hub, raw, thermostat):
        """The Diagnostics view (dashboard-spec §8): the E32, the thermostat on the boiler bus, the energy and hot
        water counters, the raw boiler data, the hot water capability and the older rooms."""
        sections = []
        device = [hub[metric] for metric in DEVICE_DIAGNOSTIC_METRICS if metric in hub]
        # Rows (not tiles) under each heading: whole names, also on a phone.
        if device:
            sections.append(_section_known(device, _heading(t["e32_device"], "mdi:chip"), _known_entities_card(device)))
        # The thermostat still on the boiler bus (the trial run): what it asks of the boiler, as the boiler hears it.
        if thermostat:
            sections.append(_section_known(thermostat, _heading(t["group_thermostat"], ICONS["thermostat"]),
                                           _known_entities_card(thermostat)))
        # The energy and hot water counters: only isolated definition-v2 IDs, no legacy counter aggregates or
        # backfill. Each shows once it has a value; until then one line says why there is none.
        counters = [hub[key + "_v2"] for key in COUNTER_KEYS if key + "_v2" in hub]
        if counters:
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
                                   "stat_types": ["change"], "visibility": _any_known(entities)})
            sections.append(_section(
                _heading(t["estimates"], "mdi:chart-bar"),
                _known_entities_card(counters),
                _note(t, t["estimates_note"], _any_known(counters)),
                _note(t, t["estimates_empty"], _none_known(counters)),
                *charts))
        if raw:
            sections.append(_section_known(raw, _heading(t["raw"], "mdi:wrench-outline"),
                                           _note(t, t["raw_note"], _any_known(raw)), _known_entities_card(raw)))
        # The read-only hot water capability, on a connection that reports one (today's taps and keeping warm are
        # on the Boiler view).
        dhw_id = hub.get("dhw_capabilities")
        if dhw_id:
            quoted = json.dumps(dhw_id)
            note = (t["dhw_note"] + "\n\n" + t["dhw_profile"] + ": {{ state_attr(" + quoted + ", 'profile') or '"
                    + t["unknown"] + "' }}; " + t["dhw_status"] + ": {{ states(" + quoted + ") }}.\n"
                    "{% set fields = state_attr(" + quoted + ", 'fields') or {} %}"
                    "{% for key, field in fields.items() %}{% if field.supported_read %}"
                    "\n- {{ key | replace('_', ' ') }}: {{ field.value if field.value is not none else '"
                    + t["unknown"] + "' }} {{ field.unit or '' }} ({{ field.quality }}){% endif %}{% endfor %}")
            # Its name once, as the heading: the Boiler view has the everyday "Hot water".
            sections.append(_section(_heading(t["dhw_card"], ICONS["hot_water"]),
                                     {"type": "entities", "entities": _rows([dhw_id])},
                                     {"type": "markdown", "content": note}))
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
                model_cards.append({"type": "entities", "title": name, "entities": _rows(heating_entities)})
            history = []
            for metric, label in (("temperature", t["room_measured"]), ("temperature_set", t["room_target"])):
                entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{self.prefix}_room_{key}_{metric}")
                if entity_id:
                    history.append({"entity": entity_id, "name": label})
            if history:
                model_cards.append({"type": "history-graph", "title": t["room_history"].format(room=name),
                                    "hours_to_show": 24, "entities": history})
        if model_cards:
            sections.append(_section(_heading(t["older_rooms"], "mdi:home-thermometer-outline"),
                                     _note(t, t["models_note"]), *model_cards))
        return sections
