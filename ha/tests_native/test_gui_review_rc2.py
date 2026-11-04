"""GUI review rc.2: the Heating view as a phone shows it, clean device pages and fewer surprises in Configure.

- The learned overview (a page of text) moved to its own subview; the Heating view keeps a short summary
  after the rooms, so the rooms come right after "Now" and the advice.
- "Now": the house mode tile has a name (it showed the device name, cut short), the problem's reasons sit
  right under it, the boiler's state words say "Boiler:", long states get the whole width.
- "Ready to take over?" never shows "None °C" for a figure the E32 does not know yet.
- Device pages: the boiler's settings, counters, the thermostat on the bus and service details are
  Diagnostic, the room's "Temperature without Home Assistant" is a setting; unique IDs stay.
- Configure: a new installation gets the dashboard, the room form says which room, sources by name,
  the house default for windows in minutes like each room's own.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.const import EntityCategory
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template

from custom_components.open_thermostat import dashboard
from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.v1_boiler_fields import secondary_field
from test_dashboard_heating import installation, walk
from nav_helpers import is_again  # noqa: E402
from test_e32_room_flow import manager, product, rooms_menu  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


def with_learned(hass, language="en"):
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product_device = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    room = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    rooms["woonkamer"]["learning"] = entities.async_get_or_create(
        "sensor", "open_thermostat", "fixture_e32_room_woonkamer_learning", config_entry=e, device_id=room.id,
        suggested_object_id="woonkamer_learning").entity_id
    for domain, key in (("sensor", "learned_overview"), ("select", "house_mode"), ("sensor", "takeover_readiness")):
        unique_id = "fixture_house_mode" if key == "house_mode" else f"fixture_hub_{key}"
        hub[key] = entities.async_get_or_create(domain, "open_thermostat", unique_id, config_entry=e,
                                                device_id=product_device.id, suggested_object_id=key).entity_id
    board = RoomDashboard(hass, "fixture", e.entry_id)
    config = board._dashboard_config()
    assert None not in list(walk(config))
    return board, config, rooms, hub


def view(config, path):
    return next((v for v in config["views"] if v["path"] == path), None)


@pytest.mark.asyncio
async def test_the_overview_is_short_and_what_it_learned_is_its_own_view(hass):
    board, config, rooms, hub = with_learned(hass)
    heating = view(config, "heating")
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == ["House", "Rooms"]
    # What it learned is not on the Overview any more; the view "Learning and settings" has it.
    assert "learned_overview" not in json.dumps(heating) and hub["learned_overview"] not in json.dumps(heating)
    learned = view(config, "learned")
    assert (learned["title"], learned["type"], "subview" in learned) == ("Learning and settings", "sections", False)
    # rc.5 (the owner's sketch): what stood out yesterday and the free heat come from the same sensor, each hidden
    # while it has nothing to say.
    assert [s["cards"][0]["heading"] for s in learned["sections"]] == [
        "Noticed", "Free heat", "What the thermostat has learned", "House and boiler", "What it changed by itself",
        "Who controls the boiler"]
    # How it learns is the note of what it learned (rc.5), not a section of its own.
    first = next(s["cards"] for s in learned["sections"] if s["cards"][0]["heading"] == "What the thermostat has learned")
    assert first[-1]["type"] == "markdown" and "learns how fast each room warms up" in first[-1]["content"]
    # What it learned per room is in that room's section, not in the learning view.
    living = next(s["cards"] for s in view(config, "rooms")["sections"] if s["cards"][0]["heading"] == "Woonkamer")
    lines = next(c for c in living if c["type"] == "markdown" and "mine[0].lines" in c["content"])
    assert '"Woonkamer"' in lines["content"] and hub["learned_overview"] in lines["content"]
    # How the learning works is with what it learned, not on the Comparison page.
    assert "learns how fast each room warms up" not in json.dumps(view(config, "comparison"))
    # Dutch.
    hass.config.language = "nl"
    dutch = RoomDashboard(hass, "fixture", board.entry_id)._dashboard_config()
    assert view(dutch, "learned")["title"] == "Leren en instellingen"
    assert "Wat de thermostaat heeft geleerd" in json.dumps(view(dutch, "learned"), ensure_ascii=False)


@pytest.mark.asyncio
async def test_the_overview_names_the_house_mode_and_long_states_get_the_whole_width(hass):
    board, config, rooms, hub = with_learned(hass)
    house = view(config, "heating")["sections"][0]["cards"]
    mode = next(c for c in house if c.get("entity") == hub["house_mode"])
    # The whole width, also where the Overview's section spans both view columns on a wide screen (rc.5: "full").
    assert mode["name"] == "House mode" and mode["grid_options"] == {"columns": "full"}
    assert mode["features"] == [{"type": "select-options"}]
    control = next(s["cards"] for s in view(config, "learned")["sections"]
                   if s["cards"][0]["heading"] == "Who controls the boiler")
    ready = next(c for c in control if c.get("entity") == hub["takeover_readiness"])
    assert ready["grid_options"] == {"columns": 12}
    # The boiler's state in words: since rc.5 the Now card's band says what it does and its display code in words
    # ("Heating", "Code -H: heating"; frontend/boiler-now-card.js, checked in test/ha-boiler-now-browser.cjs).
    code = er.async_get(hass).async_get_entity_id("sensor", "open_thermostat", "fixture_boiler_fields_v1_display_code")
    now = next(c for c in view_cards(view(config, "boiler")) if c["type"] == "custom:openthermostat-boiler-now")
    assert code and now["code"] == code


@pytest.mark.asyncio
async def test_a_figure_the_e32_does_not_know_yet_is_left_out_not_shown_as_none(hass):
    board, config, rooms, hub = with_learned(hass)
    check = next(c for s in view(config, "comparison")["sections"] for c in s["cards"]
                 if c["type"] == "markdown" and "Ready" in c["content"])
    readiness = hub["takeover_readiness"]
    hass.states.async_set(readiness, "not_ready", {"comparison": True, "boiler_limit": "fail", "boiler_limit_c": None,
                                                  "flow_limit": "pass", "flow_max_c": 54, "flow_limit_c": 60})
    text = Template(check["content"], hass).async_render(parse_result=False)
    assert "None" not in text
    assert "- ❌ Boiler maximum known. The boiler has not reported its maximum" in text
    assert "- ✅ Water temperature request never above the limit: highest 54 °C, limit 60 °C" in text
    hass.states.async_set(readiness, "not_ready", {"comparison": True, "boiler_limit": "pass", "boiler_limit_c": 75})
    assert "Boiler maximum known: 75 °C" in Template(check["content"], hass).async_render(parse_result=False)


def test_settings_counters_and_service_details_are_diagnostic_the_everyday_values_are_not():
    for name in ("configured_heating_temperature", "dhw_hysteresis_on", "minimum_burner_period",
                 "thermostat_requested_flow_temperature", "thermostat_setpoint", "boiler_uptime", "service_number", "ionisation_current", "last_locking_error_code"):
        assert secondary_field(name), name
    for name in ("measured_flow_temperature", "measured_return_temperature", "outdoor_temperature",
                 "reported_burner_modulation", "pressure", "measured_dhw_temperature", "display_code",
                 "heating_active", "dhw_active", "maintenance_message", "reported_selected_flow_temperature"):
        assert not secondary_field(name), name


def test_the_boiler_field_entity_takes_the_category_and_keeps_its_unique_id():
    from custom_components.open_thermostat.boiler_fields import INDEX_BY_NAME
    from custom_components.open_thermostat.v1_boiler_fields import BoilerFieldEntity, field_unique_id
    client = SimpleNamespace()
    for name, category in (("configured_heating_temperature", EntityCategory.DIAGNOSTIC),
                           ("measured_flow_temperature", None)):
        entity = BoilerFieldEntity("fixture", client, INDEX_BY_NAME[name])
        assert entity.entity_category == category, name
        assert entity.unique_id == field_unique_id("fixture", INDEX_BY_NAME[name])
        assert entity.entity_registry_enabled_default is True


def test_the_temperature_without_home_assistant_is_a_room_setting():
    from custom_components.open_thermostat.room_plan import RoomFallbackSetpoint, RoomInactiveUntil, RoomStateSelect
    def category(cls):
        return cls.__new__(cls).entity_category
    assert category(RoomFallbackSetpoint) == EntityCategory.CONFIG
    # The room's on/off and its "off until" stay controls on the device page.
    assert category(RoomStateSelect) is None and category(RoomInactiveUntil) is None


def test_every_icon_belongs_to_a_translated_entity():
    icons = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))["entity"]
    names = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))["entity"]
    for domain, items in icons.items():
        for key, icon in items.items():
            assert key in names.get(domain, {}), (domain, key)
            assert all(value.startswith("mdi:") for value in (icon.get("default"), *icon.get("state", {}).values()))
    for domain, key in (("select", "house_mode"), ("sensor", "boiler_activity"), ("sensor", "field_pressure"),
                        ("sensor", "field_display_code"), ("sensor", "daily_summary")):
        assert icons[domain][key]["default"], key


@pytest.mark.asyncio
async def test_a_new_installation_shows_the_dashboard_unless_unticked(hass):
    from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
    flow = OpenThermostatConfigFlow()
    flow.hass, flow.context, flow.handler = hass, {"source": "user"}, "open_thermostat"
    form = await flow.async_step_user()
    dashboard_key = next(k for k in form["data_schema"].schema if str(k) == "create_dashboard")
    assert dashboard_key.default() is True
    done = await flow.async_step_user({"name": "Thuis"})
    assert done["options"]["create_dashboard"] is False  # unticked (left out of the submitted form) stays off


@pytest.mark.asyncio
async def test_the_room_list_names_sources_and_the_form_says_which_room(hass, manager):
    parent, _ = product(hass, FakeE32())
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.1, "temperature": 20.5,
                                                        "friendly_name": "Woonkamer tado"})
    menu = await rooms_menu(manager, parent)
    assert "- Woonkamer: Woonkamer tado, Bluetooth Slaapkamer (a4c138a3e8db)" in menu["description_placeholders"]["rooms"]
    add = await manager.async_configure(menu["flow_id"], {"next_step_id": "e32_room_add"})
    assert add["description_placeholders"]["room_name"] == "new room"
    menu = await rooms_menu(manager, parent)
    pick = await manager.async_configure(menu["flow_id"], {"next_step_id": "e32_room_pick"})
    edit = await manager.async_configure(pick["flow_id"], {"room": "woonkamer", "action": "edit"})
    assert edit["step_id"] == "e32_room" and edit["description_placeholders"]["room_name"] == "Woonkamer"
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        document = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        steps = document["options"]["step"]
        assert "{room_name}" in steps["e32_room"]["title"], name
        # rc.3: edit (radiator valves included, a section of the room form) or remove; both named.
        assert set(document["selector"]["e32_room_action"]["options"]) == {"edit", "remove"}, name
        assert "(" in steps["e32_room_pick"]["data_description"]["action"], name  # "... (radiator valves included)"


@pytest.mark.asyncio
async def test_the_house_window_delay_is_in_minutes_like_each_rooms_own(hass, manager):
    parent, _ = product(hass, FakeE32())
    await hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "house"})
    form = await manager.async_configure(house["flow_id"], {"next_step_id": "comfort_settings"})
    key = next(k for k in form["data_schema"].schema if str(k) == "contact_delay")
    selector = form["data_schema"].schema[key].config
    assert (key.default(), selector["unit_of_measurement"], selector["max"]) == (2, "min", 30)
    done = await manager.async_configure(form["flow_id"], {"comfort_temperature": 20, "eco_temperature": 16,
                                                           "contact_delay": 1.5, "override_minutes": 120})
    assert is_again(done)
    assert parent.options["comfort_settings"]["contact_delay_s"] == 90  # stored in seconds, as before
    for name in ("strings.json", "translations/nl.json", "translations/pl.json"):
        help_text = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["options"]["step"][
            "comfort_settings"]["data_description"]["contact_delay"]
        assert help_text.split()[0] in ("Minutes", "Minuten", "Liczba"), name


def test_the_week_card_names_the_setting_device_and_the_current_menu():
    card = (COMPONENT / "frontend/e32-week-card.js").read_text(encoding="utf-8")
    assert "attributes?.friendly_name || r.setpoint_entity" in card
    assert "Configure → Rooms." in card and "Configureren → Ruimtes." in card and "E32 rooms." not in card


def test_dashboard_texts_follow_the_glossary():
    for language, words in (("en", ("Water to heating", "Water back", "Water temperature set by")),
                            ("nl", ("Aanvoerwater", "Retourwater", "Watertemperatuur bepaald door"))):
        t = dashboard.TEXT[language]
        assert (t["flow_short"], t["return_short"], t["flow_source"]) == words
        assert "shadow" not in t["ready_waiting"] and "schaduw" not in t["ready_waiting"]
        assert "flow limits" not in t["fix_flow_limit"] and "aanvoergrenzen" not in t["fix_flow_limit"]
