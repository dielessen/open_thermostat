"""The beta.21 dashboard redesign: grouped boiler values, a Diagnostics view without duplicates or empty
"Unknown" rows, short names, whole numbers where the boiler sends whole numbers, and a week card that does not
sign in on the E32 for every page view. Entity IDs never change.
"""
import json
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
                "burner_observed_time_v2", "outdoor_temperature", "boiler_heating_enabled", "boiler_display_code"):
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


@pytest.mark.asyncio
async def test_the_boiler_view_groups_the_values_and_shows_only_rows_with_a_value(hass):
    config, hub, fields = setup(hass)
    boiler = view(config, "boiler")
    assert (boiler["type"], boiler["max_columns"], boiler["dense_section_placement"]) == ("sections", 3, True)
    sections = headed(boiler)
    assert list(sections) == ["Heating", "Hot water", "Status and faults", "Boiler settings",
                              "Thermostat on the bus", "Last 24 hours"]

    def rows(heading):
        card = next(c for c in sections[heading] if c["type"] == "entities")
        # No title: the section heading names the card, so nothing is said twice.
        assert "title" not in card and card["visibility"] == [{"condition": "or", "conditions": [
            known(row["row"]["entity"]) for row in card["entities"]]}]
        # Only while a value; the maintenance message also not while there is none.
        assert all(row["type"] == "conditional" and row["conditions"] == [
            {**known(row["row"]["entity"]), "state_not": ["unavailable", "unknown", *(
                ["none"] if row["row"]["entity"] == fields["maintenance_message"] else [])]}]
            for row in card["entities"])
        return [row["row"]["entity"] for row in card["entities"]]
    assert rows("Heating") == [fields[n] for n in (
        "reported_selected_flow_temperature", "measured_flow_temperature", "measured_return_temperature",
        "reported_burner_modulation", "reported_requested_power_limit", "pressure", "heating_enabled",
        "hydraulic_switch_temperature", "reported_heating_pump_modulation",
        "heating_active")]  # table order, the inferred activity last
    assert rows("Hot water")[-1] == fields["dhw_active"] and fields["measured_dhw_temperature"] in rows("Hot water")
    assert rows("Status and faults") == [fields[n] for n in ("display_code", "service_number", "ionisation_current",
                                                             "maintenance_message")]
    assert fields["configured_dhw_comfort_mode"] in rows("Boiler settings")
    assert rows("Thermostat on the bus")[0] == fields["thermostat_requested_flow_temperature"]
    # One note, in the first section; the raw state bits are not on this view.
    assert [c["type"] for c in sections["Heating"]] == ["heading", "entities", "markdown"]
    assert "not a verified operation" in sections["Heating"][2]["content"]
    assert fields["raw_boiler_state"] not in json.dumps(boiler)
    # The graphs: no heading repeated as a graph title, shown while every series has a value.
    graphs = [c for c in sections["Last 24 hours"] if c["type"] == "history-graph"]
    assert graphs and all(g["title"] != "Last 24 hours" for g in graphs)
    for graph in graphs:
        assert graph["visibility"] == [known(item["entity"]) for item in graph["entities"]]


@pytest.mark.asyncio
async def test_diagnostics_shows_each_value_once_and_hides_counters_until_they_have_data(hass):
    config, hub, fields = setup(hass)
    diagnostics = view(config, "diagnostics")
    assert (diagnostics["type"], diagnostics["max_columns"]) == ("sections", 3)
    sections = headed(diagnostics)
    assert list(sections) == ["E32", "Hot water today", "Energy and hot water counters", "Raw boiler data"]
    text = json.dumps(diagnostics)
    # Every value shown once (the counters were listed twice), and no legacy hub rows any more.
    shown = [row["row"]["entity"] if row.get("type") == "conditional" else row["entity"]
             for c in view_cards(diagnostics) if c["type"] == "entities" for row in c["entities"]]
    assert not [c for c in view_cards(diagnostics) if c["type"] == "tile"]  # rows: whole names on a phone
    assert len(shown) == len(set(shown))
    assert {hub[k] for k in ("energy_v2", "memory_free", "dhw_taps_today", "warm_water_usage_v2")} <= set(shown)
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
    assert "EMS+" in empty["content"] and "gas per day" in empty["content"]
    charts = [c for c in cards if c["type"] == "statistics-graph"]
    assert charts and all(c["visibility"] == [{"condition": "or", "conditions": [known(e) for e in c["entities"]]}]
                          for c in charts)
    raw = next(c for c in sections["Raw boiler data"] if c["type"] == "entities")
    assert [r["row"]["entity"] for r in raw["entities"]] == [fields["raw_boiler_state"]]


@pytest.mark.asyncio
async def test_dutch_headings_for_the_new_groups(hass):
    config, hub, fields = setup(hass, "nl")
    assert list(headed(view(config, "boiler"))) == ["Verwarming", "Warm water", "Status en storingen",
                                                    "Ketelinstellingen", "Thermostaat op de bus", "Afgelopen 24 uur"]
    assert list(headed(view(config, "diagnostics"))) == ["E32", "Warm water vandaag",
                                                         "Tellers voor energie en warm water", "Ruwe keteldata"]
    assert set(TEXT["en"]) == set(TEXT["nl"])


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
