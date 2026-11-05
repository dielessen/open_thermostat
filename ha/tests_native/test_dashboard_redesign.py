"""The beta.21 dashboard redesign: grouped boiler values, a Diagnostics view without duplicates or empty
"Unknown" rows, short names, whole numbers where the boiler sends whole numbers, and a week card that does not
sign in on the E32 for every page view. Entity IDs never change.
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat import _drop_test_setup_name
from custom_components.open_thermostat.boiler_fields import CATALOG_BASE, CATALOG_FIELDS, FIELDS
from custom_components.open_thermostat.dashboard import TEXT, RoomDashboard, boiler_group, view_cards
from custom_components.open_thermostat.e32_week import read_week
from custom_components.open_thermostat.v1_boiler_fields import BoilerFieldEntity
from test_dashboard_heating import installation, walk
from test_e32_room_flow import product
from test_room_plan import FakeE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
# The boiler fields of the owner's installation (30 Oct 2026) that have an entity.
LIVE_FIELDS = (
    "reported_selected_flow_temperature", "measured_flow_temperature", "measured_return_temperature",
    "reported_burner_modulation", "reported_requested_power_limit", "raw_boiler_state", "heating_active",
    "dhw_active", "selected_dhw_temperature", "measured_dhw_temperature", "heating_enabled", "dhw_enabled",
    "display_code", "service_number", "configured_heating_temperature", "reported_dhw_target",
    "ionisation_current", "hydraulic_switch_temperature", "reported_heating_pump_modulation", "dhw_hysteresis_on",
    "dhw_charge_optimisation_enabled", "dhw_flow_temperature_offset", "dhw_circulation_enabled",
    "configured_dhw_circulation_mode", "dhw_disinfection_temperature", "configured_dhw_charge_type",
    "configured_dhw_comfort_mode", "reported_dhw_type", "thermostat_requested_flow_temperature",
    "thermostat_requested_burner_power", "thermostat_requested_pump_modulation", "maintenance_message",
    "thermostat_setpoint", "thermostat_room_temperature", "thermostat_requested_dhw_temperature")


def known(entity_id):
    return {"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}


UNKNOWN = ("unavailable", "unknown")


def target(condition):
    """What a condition reads: the entity's state, or (entity, attribute) for one of its attributes."""
    return (condition["entity"], condition["attribute"]) if "attribute" in condition else condition["entity"]


def shown(conditions, states):
    """Whether Home Assistant shows a card or section with these visibility ``conditions`` in ``states`` (as its
    frontend checks them; an entity without a state is unavailable). The condition kinds this dashboard uses.

    ``states`` also holds an attribute as the frontend reads it, under (entity, attribute): as text (an empty list
    is ""), "unknown" while the attribute or its entity is missing (rc.5: Noticed and Free heat)."""
    for condition in conditions:
        kind = condition.get("condition", "state")
        if kind == "and":
            ok = shown(condition["conditions"], states)
        elif kind == "or":
            ok = any(shown([item], states) for item in condition["conditions"])
        elif kind == "state":
            state = states.get(target(condition), "unknown" if "attribute" in condition else "unavailable")
            listed = condition["state"] if "state" in condition else condition["state_not"]
            ok = (state in listed if isinstance(listed, list) else state == listed) == ("state" in condition)
        elif kind == "numeric_state":
            try:
                value = float(states.get(target(condition), "unavailable"))
            except ValueError:
                ok = False
            else:
                ok = (("above" not in condition or value > condition["above"])
                      and ("below" not in condition or value < condition["below"]))
        else:
            raise AssertionError(f"visibility condition {kind} is not evaluated here")
        if not ok:
            return False
    return True


def references(card, ids):
    """The entities a card shows (in its config or its template), its own visibility aside."""
    text = json.dumps({key: value for key, value in card.items() if key != "visibility"})
    return {entity_id for entity_id in re.findall(r"[a-z_]+\.[a-z0-9_]+", text) if entity_id in ids}


def view(config, path):
    return next(v for v in config["views"] if v["path"] == path)


def headed(view_config):
    """{section heading: its cards}."""
    return {s["cards"][0]["heading"]: s["cards"] for s in view_config["sections"]}


def setup(hass, language="en"):
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities = er.async_get(hass)
    product_device = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)

    def add(unique_id):
        return entities.async_get_or_create("sensor", "open_thermostat", unique_id, config_entry=e,
                                            device_id=product_device.id, suggested_object_id=unique_id).entity_id
    for name in LIVE_FIELDS:
        fields[name] = add(f"fixture_boiler_fields_v1_{name}")
    for key in ("memory_free", "memory_min_free", "memory_max_alloc", "cpu_temperature", "uptime",
                "dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today", "energy_v2", "energy_heating_v2",
                "energy_warm_water_v2", "energy_unattributed_v2", "warm_water_usage_v2", "warm_water_avg_flow_v2",
                "burner_observed_time_v2", "outdoor_temperature", "boiler_heating_enabled", "boiler_display_code",
                "boiler_activity", "heating_gas", "hot_water_gas", "daily_burner_starts", "daily_burner_time"):
        hub[key] = add(f"fixture_hub_{key}")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    return config, hub, fields


def test_every_boiler_field_has_one_group():
    names = [field[0] for field in FIELDS] + [field[0] for field in CATALOG_FIELDS]
    groups = {name: boiler_group(name) for name in names}
    assert set(groups.values()) <= {"heating", "dhw", "status", "counters", "settings", "thermostat", "raw"}
    assert groups["measured_flow_temperature"] == "heating" and groups["measured_dhw_temperature"] == "dhw"
    assert groups["display_code"] == groups["last_locking_error_code"] == "status"
    assert groups["configured_dhw_comfort_mode"] == groups["dhw_hysteresis_on"] == "settings"
    assert groups["thermostat_setpoint"] == "thermostat" and groups["boiler_uptime"] == "counters"
    # The raw state bits and the unreliable OEM values are raw data (Diagnostics), never a boiler group.
    assert groups["raw_boiler_state"] == groups["raw_burner_bit"] == groups["reported_burner_starts"] == "raw"


def shown_row(entity_id, fields):
    """A row's condition: only while a value; the maintenance message also not while there is none."""
    return {**known(entity_id), "state_not": ["unavailable", "unknown", *(
        ["none"] if entity_id == fields["maintenance_message"] else [])]}


def sections_visibility(view_config, heading):
    return next(s.get("visibility") for s in view_config["sections"] if s["cards"][0]["heading"] == heading)


@pytest.mark.asyncio
async def test_the_boiler_view_groups_the_values_and_shows_only_rows_with_a_value(hass):
    config, hub, fields = setup(hass)
    boiler = view(config, "boiler")
    assert (boiler["type"], boiler["max_columns"], boiler["dense_section_placement"]) == ("sections", 2, True)
    sections = headed(boiler)
    # rc.5 (dashboard-spec §5): seven sections at most, in this order (no advice in this installation).
    assert list(sections) == ["Now", "Today and this week", "Hot water", "Last 24 hours", "What the boiler reports",
                              "Boiler settings"]
    assert [s["cards"][0]["icon"] for s in boiler["sections"]] == [
        "mdi:water-boiler", "mdi:chart-bar", "mdi:faucet", "mdi:chart-line", "mdi:water-boiler", "mdi:cog-outline"]
    # Every section hides as a whole while nothing in it has a value: no heading over nothing.
    assert all(section["visibility"][0]["condition"] == "or" for section in boiler["sections"])

    def rows(card):
        # Only while a value; the card while one of its rows shows.
        assert card["visibility"] == [{"condition": "or", "conditions": [
            shown_row(row["row"]["entity"], fields) for row in card["entities"]]}]
        assert all(row["type"] == "conditional" and row["conditions"] == [shown_row(row["row"]["entity"], fields)]
                   for row in card["entities"])
        return [row["row"]["entity"] for row in card["entities"]]
    # What the boiler reports: one card per group with its own title, under one heading.
    reported = sections["What the boiler reports"]
    assert [c["type"] for c in reported] == ["heading", "entities", "markdown", "entities", "entities"]
    cards = {c["title"]: c for c in reported if c["type"] == "entities"}
    assert list(cards) == ["Heating", "Hot water", "Status and faults"]
    assert rows(cards["Heating"]) == [fields[n] for n in (
        "reported_selected_flow_temperature", "measured_flow_temperature", "measured_return_temperature",
        "reported_burner_modulation", "reported_requested_power_limit", "pressure", "heating_enabled",
        "hydraulic_switch_temperature", "reported_heating_pump_modulation",
        "heating_active")]  # table order, the inferred activity last
    assert rows(cards["Hot water"])[-1] == fields["dhw_active"]
    assert fields["measured_dhw_temperature"] in rows(cards["Hot water"])
    assert rows(cards["Status and faults"]) == [fields[n] for n in (
        "display_code", "service_number", "ionisation_current", "maintenance_message")]
    every = [row["row"]["entity"] for card in cards.values() for row in card["entities"]]
    assert sections_visibility(boiler, "What the boiler reports") == [{"condition": "or", "conditions": [
        shown_row(entity_id, fields) for entity_id in every]}]
    # One note, under the first card and shown with it; the raw state bits are not on this view.
    note = reported[2]
    assert "not a separate check" in note["content"] and note["visibility"] == cards["Heating"]["visibility"]
    assert fields["raw_boiler_state"] not in json.dumps(boiler)
    # The settings, last and untitled (their heading names them); the thermostat on the bus is on Diagnostics.
    settings = sections["Boiler settings"][1]
    assert "title" not in settings and fields["configured_dhw_comfort_mode"] in rows(settings)
    assert fields["thermostat_requested_flow_temperature"] not in json.dumps(boiler)
    # The graphs: no heading repeated as a graph title, each shown once one of its series has a value.
    graphs = [c for c in sections["Last 24 hours"] if c["type"] == "history-graph"]
    assert graphs and all(g["title"] != "Last 24 hours" for g in graphs)
    for graph in graphs:
        assert graph["visibility"] == [{"condition": "or", "conditions": [
            known(item["entity"]) for item in graph["entities"]]}]
    assert sections_visibility(boiler, "Last 24 hours") == [{"condition": "or", "conditions": [
        known(item["entity"]) for graph in graphs for item in graph["entities"]]}]
    # Today's hot water and what the boiler does: under "Hot water", with the temperature next to its target.
    hot_water = sections["Hot water"]
    measured, target = hot_water[1:3]
    assert (measured["entity"], measured["name"], target["entity"], target["name"], target["icon"]) == (
        fields["measured_dhw_temperature"], "Hot water", fields["reported_dhw_target"], "Hot water target",
        "mdi:thermometer-water")
    assert measured["visibility"] == target["visibility"] == [known(fields["measured_dhw_temperature"])]
    assert [c["type"] for c in hot_water[3:]] == ["entities", "history-graph", "markdown"]
    assert hot_water[4]["visibility"] == hot_water[5]["visibility"] == [known(hub["boiler_activity"])]


# Roboto Medium at 16 px, the statistic card's name (--ha-font-size-l, weight 500): advance widths in CSS px, measured
# in Chromium with the frontend's own Roboto-Medium.woff2 (P21); kerning moves these names by less than 0.3 px.
ROBOTO_MEDIUM_16 = {
    "a": 8.7, "b": 9, "c": 8.4, "d": 9, "e": 8.6, "f": 5.7, "g": 9.1, "h": 8.9, "i": 4.1, "j": 4, "k": 8.4,
    "l": 4.1, "m": 13.9, "n": 8.9, "o": 9.1, "p": 9, "q": 9.1, "r": 5.6, "s": 8.3, "t": 5.3, "u": 8.9, "v": 7.9,
    "w": 11.9, "x": 8, "y": 7.8, "z": 8, "A": 10.7, "B": 10.1, "C": 10.5, "D": 10.5, "E": 9, "F": 8.8, "G": 10.9,
    "H": 11.4, "I": 4.5, "J": 8.9, "K": 10.1, "L": 8.7, "M": 14, "N": 11.4, "O": 11, "P": 10.2, "Q": 11, "R": 10,
    "S": 9.7, "T": 9.7, "U": 10.4, "V": 10.4, "W": 14.1, "X": 10.1, "Y": 9.8, "Z": 9.6, "ą": 8.7, "ć": 8.4,
    "ę": 8.6, "ł": 4.6, "ń": 8.9, "ó": 9.1, "ś": 8.3, "ź": 8, "ż": 8, "Ą": 10.7, "Ć": 10.5, "Ę": 9, "Ł": 8.8,
    "Ń": 11.4, "Ó": 11, "Ś": 9.7, "Ź": 9.6, "Ż": 9.6, "ë": 8.6, "é": 8.6, "è": 8.6, "ü": 8.9, "ö": 9.1, "ä": 8.7,
    "0": 9.1, "1": 9.1, "2": 9.1, "3": 9.1, "4": 9.1, "5": 9.1, "6": 9.1, "7": 9.1, "8": 9.1, "9": 9.1, " ": 4,
    ":": 4.3, ",": 3.5, ".": 4.5, "(": 5.6, ")": 5.6, "–": 10.3, "-": 5.3, "…": 11.3, "/": 6.3}


def name_width(text):
    return round(sum(ROBOTO_MEDIUM_16[c] for c in text), 1)


def test_todays_figures_have_names_a_phone_shows_in_full():
    """The demo Home Assistant at 390 px (P16) cut every name of the four figures ("Gas verwarmen…", "Branderstarts
    v…"): a half-width statistic card there showed "Gas verwarmen…" (122.8 px) in full and cut "Gas warm water…"
    (125.9 px). The names fit that, in every language; "today" is said once, by the section's heading."""
    from custom_components.open_thermostat.dashboard import _energy_section
    budget = name_width("Gas verwarmen…")
    assert 122.5 <= budget < name_width("Gas warm water…")
    hub = {key: "sensor." + key for key in ("heating_gas", "hot_water_gas", "daily_burner_starts", "daily_burner_time")}
    for language, t in TEXT.items():
        figures = [card for card in _energy_section(t, hub)["cards"] if card["type"] == "statistic"]
        assert len(figures) == 4, language
        for card in figures:
            assert name_width(card["name"]) <= budget, (language, card["name"], name_width(card["name"]))
    assert [TEXT[language]["today_week"] for language in ("en", "nl", "pl")] == [
        "Today and this week", "Vandaag en deze week", "Dziś i w tym tygodniu"]


@pytest.mark.asyncio
@pytest.mark.parametrize("language,lines,names", [
    ("en", ["Heating time today", "Burner starts today"], ["E32", "Thermostat"]),
    ("nl", ["Stooktijd vandaag", "Branderstarts vandaag"], ["E32", "Thermostaat"]),
    ("pl", ["Czas grzania dziś", "Starty palnika dziś"], ["E32", "Termostat"])])
async def test_the_comparison_tiles_have_names_a_phone_shows_in_full(hass, language, lines, names):
    """The trial run's Comparison subview (P21): its half-width tiles cut "Heating time thermostat", "Stooktijd
    thermostaat" and "Czas grzania termostatu" (136-154 px) at 390 px, where a half tile shows about 116 px of name
    ("Starts thermostaat", 118 px, was cut). Each pair now stands under a line that says what it counts (the whole
    width), so the tiles need only say whose figure it is. Tile names are Roboto Medium at 14 px."""
    config, hub, fields = setup(hass, language)
    cards = view(config, "comparison")["sections"][0]["cards"]
    pairs = [(c["heading"], c["heading_style"]) for c in cards[2:] if c["type"] == "heading"]
    assert pairs == [(line, "subtitle") for line in lines]
    tiles = [c for c in cards[2:] if c["type"] == "tile"]
    assert [(c["entity"], c["name"]) for c in tiles] == [
        (hub["shadow_e32_heating_time_today"], names[0]), (hub["shadow_tado_heating_time_today"], names[1]),
        (hub["shadow_e32_starts_today"], names[0]), (hub["shadow_tado_starts_today"], names[1])]
    assert all("grid_options" not in c for c in tiles)  # side by side in pairs
    budget = 116
    width = lambda text: name_width(text) * 14 / 16
    assert width("Starts thermostaat") > budget >= width("Thermostaat")
    assert all(width(c["name"]) <= budget for c in tiles), [(c["name"], width(c["name"])) for c in tiles]
    # Every card shows only while a thermostat is heard to compare with, the lines with their tiles.
    agreement = [{"condition": "state", "entity": hub["shadow_agreement_today"], "state_not": ["unavailable", "unknown"]}]
    assert all(c["visibility"] == agreement for c in cards[1:])


@pytest.mark.asyncio
@pytest.mark.parametrize("language,heading,note", [
    ("en", "Boiler settings", "Settings the boiler reports only when asked are read at start-up and every six hours; "
                              "the time of the last reading is on the sensor."),
    ("nl", "Ketelinstellingen", "Instellingen die de ketel alleen op verzoek meldt, leest de E32 bij het opstarten en "
                                "daarna elke zes uur; wanneer ze voor het laatst zijn gelezen staat op de sensor."),
    ("pl", "Ustawienia kotła", "Ustawienia, które kocioł zgłasza tylko na żądanie, E32 odczytuje przy uruchomieniu, "
                               "a potem co sześć godzin; czas ostatniego odczytu jest podany na czujniku.")])
async def test_the_boiler_settings_say_when_the_boiler_reports_them(hass, language, heading, note):
    """The owner (4 Nov 2026): settings the boiler reports only once or at start-up are shown, with a remark. Under
    the settings one sentence says when they are read and where the time of the last reading is."""
    config, hub, fields = setup(hass, language)
    cards = headed(view(config, "boiler"))[heading]
    assert [card["type"] for card in cards] == ["heading", "entities", "markdown"]
    assert cards[2]["content"] == note and cards[2]["visibility"] == cards[1]["visibility"]


@pytest.mark.asyncio
async def test_today_and_this_week_has_todays_figures_and_the_one_gas_chart(hass):
    """rc.5 (dashboard-spec §5.3): gas and burner of today as pairs of figures, one gas-per-day chart, the burner
    hours per day and one note on how the gas is counted; on the Boiler view only."""
    config, hub, fields = setup(hass)
    boiler = view(config, "boiler")
    cards = headed(boiler)["Today and this week"]
    figures = [c for c in cards if c["type"] == "statistic"]
    assert [(c["entity"], c["name"], c["icon"]) for c in figures] == [
        (hub["heating_gas"], "Heating gas", "mdi:meter-gas"),
        (hub["hot_water_gas"], "Hot water gas", "mdi:meter-gas"),
        (hub["daily_burner_starts"], "Burner starts", "mdi:counter"),
        (hub["daily_burner_time"], "Burner time", "mdi:timer-outline")]
    assert all(c["period"] == {"calendar": {"period": "day"}} and c["stat_type"] == "change"
               and c["grid_options"] == {"columns": 6, "rows": 2} for c in figures)
    # Pairs that appear together: the gas while the gas has a value, the burner while its starts have one.
    assert [c["visibility"] for c in figures] == (
        [[known(hub["heating_gas"])]] * 2 + [[known(hub["daily_burner_starts"])]] * 2)
    gas, burner = [c for c in cards if c["type"] == "statistics-graph"]
    assert (gas["title"], gas["chart_type"], gas["period"], gas["days_to_show"], gas["stat_types"]) == (
        "Gas per day", "bar", "day", 7, ["change"])
    assert gas["entities"] == [{"entity": hub["heating_gas"], "name": "Heating"},
                               {"entity": hub["hot_water_gas"], "name": "Hot water"}]
    assert gas["visibility"] == [known(hub["heating_gas"])]
    assert burner["title"] == "Burner hours per day" and burner["visibility"] == [known(hub["daily_burner_time"])]
    note = cards[-1]
    assert note["type"] == "markdown" and "'estimate'" in note["content"]
    assert note["visibility"] == [known(hub["heating_gas"])]
    assert sections_visibility(boiler, "Today and this week") == [{"condition": "or", "conditions": [
        known(hub[k]) for k in ("heating_gas", "daily_burner_starts", "daily_burner_time")]}]
    # The one gas chart of the whole dashboard.
    assert sum(json.dumps(v).count('"title": "Gas per day"') for v in config["views"]) == 1


@pytest.mark.asyncio
async def test_diagnostics_shows_each_value_once_and_hides_counters_until_they_have_data(hass):
    config, hub, fields = setup(hass)
    diagnostics = view(config, "diagnostics")
    assert (diagnostics["type"], diagnostics["max_columns"]) == ("sections", 2)
    sections = headed(diagnostics)
    # rc.7: first, in plain words, whether the E32 and Home Assistant reach each other (test_dashboard_e32_link.py).
    assert list(sections) == ["Connection with the E32", "E32", "Thermostat on the bus", "Energy and hot water counters",
                              "Raw boiler data"]
    # The thermostat on the bus (a trial run's old thermostat): its rows, here and nowhere else.
    thermostat = sections["Thermostat on the bus"][1]
    assert [row["row"]["entity"] for row in thermostat["entities"]][0] == fields["thermostat_requested_flow_temperature"]
    assert sections_visibility(diagnostics, "Thermostat on the bus") == thermostat["visibility"]
    # The raw data's note shows with its rows.
    raw_note = sections["Raw boiler data"][1]
    assert raw_note["type"] == "markdown" and raw_note["visibility"] == sections["Raw boiler data"][2]["visibility"]
    text = json.dumps(diagnostics)
    # Every value shown once (the counters were listed twice), and no legacy hub rows any more.
    shown = [row["row"]["entity"] if row.get("type") == "conditional" else row["entity"]
             for c in view_cards(diagnostics) if c["type"] == "entities" for row in c["entities"]]
    assert not [c for c in view_cards(diagnostics) if c["type"] == "tile"]  # rows: whole names on a phone
    assert len(shown) == len(set(shown))
    assert {hub[k] for k in ("energy_v2", "memory_free", "warm_water_usage_v2")} <= set(shown)
    for key in ("outdoor_temperature", "boiler_heating_enabled", "boiler_display_code"):
        assert hub[key] not in text, key
    assert "Unreliable" not in text and "EMS information" not in text
    # The E32's rows show while they have a value, named by the entity alone.
    e32 = sections["E32"][1]["entities"]
    assert [row["row"] for row in e32] == [{"entity": hub[k], "name": {"type": "entity"}}
                                           for k in ("memory_free", "memory_min_free", "memory_max_alloc",
                                                     "cpu_temperature", "uptime")]
    assert all(row["conditions"] == [known(row["row"]["entity"])] for row in e32)
    counters = [hub[k + "_v2"] for k in ("energy", "energy_heating", "energy_warm_water", "energy_unattributed",
                                         "warm_water_usage", "warm_water_avg_flow", "burner_observed_time")]
    cards = sections["Energy and hot water counters"]
    assert [row["row"]["entity"] for row in cards[1]["entities"]] == counters
    note, empty = [c for c in cards if c["type"] == "markdown"]
    any_known = [{"condition": "or", "conditions": [known(e) for e in counters]}]
    assert note["visibility"] == any_known and "estimates" in note["content"]
    # While none has a value (a boiler without EMS+ counters): one line why, instead of rows of "Unknown".
    assert empty["visibility"] == [{"condition": "state", "entity": e, "state": ["unavailable", "unknown"]}
                                   for e in counters]
    assert "EMS+" in empty["content"] and "gas per day" in empty["content"] and "The Boiler tab" in empty["content"]
    assert "Heating page" not in json.dumps(diagnostics)
    charts = [c for c in cards if c["type"] == "statistics-graph"]
    assert charts and all(c["visibility"] == [{"condition": "or", "conditions": [known(e) for e in c["entities"]]}]
                          for c in charts)
    raw = next(c for c in sections["Raw boiler data"] if c["type"] == "entities")
    assert sections_visibility(diagnostics, "Raw boiler data") == raw["visibility"]
    assert [r["row"]["entity"] for r in raw["entities"]] == [fields["raw_boiler_state"]]


@pytest.mark.asyncio
async def test_the_owners_boiler_shows_no_card_that_can_only_say_unknown(hass):
    """rc.5 (dashboard-spec §14): the owner's Bosch EasyControl Adapter in front of a Nefit EcomLine HRC 22 sends
    no pressure, no selected water temperature (it stays 0, so its boiler profile hides it) and no EMS+ counters.
    With every other value reported, each card on the screen shows at least one value: none can only say
    "Unknown", and no section is left with its heading alone."""
    config, hub, fields = setup(hass)
    registry = er.async_get(hass)
    entry_id = registry.async_get(hub["heat_request"]).config_entry_id
    for name in ("reported_selected_flow_temperature", "pressure"):  # not on this boiler: its profile hides them
        registry.async_remove(fields.pop(name))
    config = RoomDashboard(hass, "fixture", entry_id)._dashboard_config()
    ids = {item.entity_id for item in er.async_entries_for_config_entry(registry, entry_id)} | {"climate.tado_woonkamer"}
    silent = {hub[key] for key in hub if key.endswith("_v2")}  # no EMS+ energy or hot water counters
    special = {hub["boiler_activity"]: "heating", fields["heating_active"]: "on", fields["dhw_active"]: "off",
               fields["maintenance_message"]: "none"}
    states = {entity_id: "unknown" if entity_id in silent else special.get(entity_id, "1") for entity_id in ids}
    on_screen = 0
    for view_config in config["views"]:
        for section in view_config.get("sections", []):
            if not shown(section.get("visibility", []), states):
                continue
            # (The house card stands alone on top of the Overview, without a heading.)
            titled = section["cards"][0]["type"] == "heading"
            cards = [card for card in section["cards"][1 if titled else 0:] if shown(card.get("visibility", []), states)]
            assert cards, (view_config["path"], section["cards"][0].get("heading"))
            for card in cards:
                refs = references(card, ids)
                assert not refs or any(states[entity_id] not in UNKNOWN for entity_id in refs), (
                    view_config["path"], section["cards"][0].get("heading"), card)
                on_screen += 1
    assert on_screen > 40
    # The silent values are nowhere on the Boiler view, and the counters say in one line why they are empty.
    boiler = json.dumps(view(config, "boiler"))
    assert not any(entity_id in boiler for entity_id in silent)
    counters = headed(view(config, "diagnostics"))["Energy and hot water counters"]
    assert [shown(card.get("visibility", []), states) for card in counters[1:4]] == [False, False, True]


@pytest.mark.asyncio
async def test_dutch_headings_for_the_new_groups(hass):
    config, hub, fields = setup(hass, "nl")
    assert list(headed(view(config, "boiler"))) == ["Nu", "Vandaag en deze week", "Warm water", "Afgelopen 24 uur",
                                                    "Wat de ketel meldt", "Ketelinstellingen"]
    reported = headed(view(config, "boiler"))["Wat de ketel meldt"]
    assert [c["title"] for c in reported if c["type"] == "entities"] == ["Verwarming", "Warm water",
                                                                          "Status en storingen"]
    assert list(headed(view(config, "diagnostics"))) == ["Verbinding met de E32", "E32", "Thermostaat op de bus",
                                                         "Tellers voor energie en warm water", "Ruwe keteldata"]
    assert set(TEXT["en"]) == set(TEXT["nl"]) == set(TEXT["pl"])


@pytest.mark.asyncio
async def test_the_week_card_reads_the_plan_ha_holds_and_signs_in_only_for_reload_or_a_stale_plan(hass):
    e32 = FakeE32()
    parent, hub = product(hass, e32)
    await hass.async_block_till_done()  # the hub reads the plan once after its first status
    logins, reads = e32.logins, e32.reads
    assert hub.plan.plan is not None and hub.plan.revision == hub.revision
    week = await read_week(hass, parent.entry_id)
    assert [room["id"] for room in week["rooms"]] == [room["id"] for room in hub.plan.plan["rooms"]]
    assert (e32.logins, e32.reads) == (logins, reads)  # no sign-in for opening the card
    await read_week(hass, parent.entry_id, fresh=True)  # Reload: from the E32 itself
    assert (e32.logins, e32.reads) == (logins + 1, reads + 1)
    # The E32 reports a newer revision than HA read: read again, never show an old program.
    hub.status = {**hub.status, "revision": hub.revision + 1}
    before = e32.reads
    await read_week(hass, parent.entry_id)
    assert e32.reads > before
    # An E32 that is not heard: read from the E32 (which then says it cannot be reached).
    await hass.async_block_till_done()
    hub.status = {**hub.status, "revision": hub.plan.revision}
    hub.online = False
    before = e32.reads
    await read_week(hass, parent.entry_id)
    assert e32.reads > before


def test_the_card_asks_for_a_fresh_read_only_on_reload():
    card = (COMPONENT / "frontend/e32-week-card.js").read_text(encoding="utf-8")
    assert "...(fresh ? {fresh: true} : {})" in card
    assert card.count("this.load(true)") == 2 and "setTimeout(() => this.load(fresh), RETRY_MS)" in card
    assert "Reading the week programs from the E32…" in card and "Weekprogramma’s lezen van de E32…" in card


@pytest.mark.asyncio
async def test_the_test_setup_hub_name_goes_a_user_name_stays_and_entity_ids_never_change(hass):
    from homeassistant import loader
    from test_v1_native import entry
    loader.async_setup(hass)
    e = entry(hass)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    hub = devices.async_get_or_create(config_entry_id=e.entry_id, identifiers={("open_thermostat", "fixture")},
                                      name="OpenThermostat E32")
    devices.async_update_device(hub.id, name_by_user="E32-regelaar — ketel en diagnose")
    owner_id = "sensor.woonkamer_e32_regelaar_ketel_en_diagnose_boiler_measured_flow_temperature"
    entities.async_get_or_create("sensor", "open_thermostat", "fixture_boiler_fields_v1_measured_flow_temperature",
                                 config_entry=e, device_id=hub.id, suggested_object_id=owner_id.split(".")[1])
    _drop_test_setup_name(hass, e)
    assert devices.async_get(hub.id).name_by_user is None and devices.async_get(hub.id).name == "OpenThermostat E32"
    assert entities.async_get(owner_id) is not None  # the entity ID (and so its history) is unchanged
    # Any other name the user gives stays, also on the next start.
    devices.async_update_device(hub.id, name_by_user="Ketel")
    _drop_test_setup_name(hass, e)
    assert devices.async_get(hub.id).name_by_user == "Ketel"


def test_whole_numbers_show_without_decimals_and_measured_temperatures_keep_theirs():
    client = SimpleNamespace()
    at = {field[0]: index for index, field in enumerate(FIELDS)}
    at.update({field[0]: CATALOG_BASE + index for index, field in enumerate(CATALOG_FIELDS)})
    precision = lambda name: getattr(BoilerFieldEntity("fixture", client, at[name]),
                                     "_attr_suggested_display_precision", None)
    for name in ("reported_burner_modulation", "service_number", "dhw_hysteresis_on", "raw_boiler_state",
                 "thermostat_requested_flow_temperature", "reported_burner_starts"):
        assert precision(name) == 0, name
    # Words (on/off, codes) have no precision, so Home Assistant accepts their text state.
    for name in ("measured_flow_temperature", "selected_dhw_temperature", "pressure", "ionisation_current",
                 "display_code", "thermostat_setpoint", "dhw_enabled", "configured_dhw_comfort_mode",
                 "maintenance_message"):
        assert precision(name) is None, name


@pytest.mark.asyncio
async def test_a_whole_number_field_keeps_its_entity_id(hass, monkeypatch):
    from homeassistant import loader
    from homeassistant.helpers import translation
    from custom_components.open_thermostat.v1_boiler_fields import translated_fields
    from test_modern_metrics import system
    from test_room_sensor_restore import platform
    e, runtime, client, now = await system(hass)
    client.boiler_fields_supported = True
    actual = await platform(hass, e)
    integration = loader.Integration(hass, "custom_components.open_thermostat", COMPONENT,
                                     json.loads((COMPONENT / "manifest.json").read_text()),
                                     top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    device = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, name="E32",
                                                    identifiers={("open_thermostat", "fixture")})
    owner_id = "sensor.woonkamer_e32_regelaar_ketel_en_diagnose_boiler_reported_burner_modulation"
    er.async_get(hass).async_get_or_create("sensor", "open_thermostat",
                                           "fixture_boiler_fields_v1_reported_burner_modulation",
                                           config_entry=e, device_id=device.id,
                                           suggested_object_id=owner_id.split(".")[1])
    await actual.platform_data.async_load_translations()
    index = next(i for i, field in enumerate(FIELDS) if field[0] == "reported_burner_modulation")
    enabled = BoilerFieldEntity("fixture", client, index, translated_fields())
    try:
        await actual.async_add_entities([enabled])
        await hass.async_block_till_done()
        assert enabled.entity_id == owner_id
        assert er.async_get(hass).async_get(owner_id).options["sensor"]["suggested_display_precision"] == 0
    finally:
        await actual.async_reset()
        await runtime.async_stop()
