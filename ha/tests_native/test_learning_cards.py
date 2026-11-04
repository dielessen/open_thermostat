"""The Learning view's new cards (E32 rc.5): what the E32 knows, and water temperature by outdoor temperature.

The knowledge section comes first on the Learning view: the knowledge card (a ring, frontend/heating-curve-card.js),
the boiler's response in one sentence and yesterday compared with usual; hidden until the E32 reports them. The
heating-curve card sits with weather compensation's own controls and reads what "Water temperature by weather
compensation" carries: the slope and where it comes from, the standard slope from the water temperature in hard
frost (WeatherCurve::slopeFor), the room temperature, the outdoor temperature now and the plan's limits.
"""
import json
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template

from custom_components.open_thermostat import e32_flow
from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.heating_link import HeatingHub
from test_dashboard_heating import installation, walk

HUB_KEYS = ("knowledge", "boiler_response", "learned_overview")
FLOW = {"curve": "sensor", "weather_curve": "switch", "curve_design_flow_c": "select", "apply_learned": "switch",
        "source": "sensor"}


def learning_installation(hass, language="en", hub_keys=HUB_KEYS, flow=FLOW):
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    for key in hub_keys:
        hub[key] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id
    controls = {key: entities.async_get_or_create(domain, "open_thermostat", f"fixture_flow_{key}", config_entry=e,
                                                  device_id=product.id, suggested_object_id=f"flow_{key}").entity_id
                for key, domain in flow.items()}
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    learning = next(view for view in config["views"] if view["path"] == "learned")
    return learning, hub, controls


def render(hass, card):
    return Template(card["content"], hass).async_render(parse_result=False)


@pytest.mark.asyncio
async def test_what_the_e32_knows_comes_first_on_the_learning_view(hass):
    learning, hub, _ = learning_installation(hass)
    section = learning["sections"][0]
    heading, knowledge, boiler, insights, note = section["cards"]
    assert heading == {"type": "heading", "heading": "What the E32 knows", "heading_style": "title", "icon": "mdi:home-analytics"}
    # The knowledge card: a ring with the percentage and what it still learns (the sixth card module).
    assert knowledge == {"type": "custom:openthermostat-knowledge", "entity": hub["knowledge"], "grid_options": {"columns": 12},
                         "visibility": [{"condition": "state", "entity": hub["knowledge"], "state_not": ["unavailable", "unknown"]}]}
    # Hidden as a whole until the E32 reports what it knows or how the boiler responds (rc.5).
    assert section["visibility"] == [{"condition": "or", "conditions": [
        {"condition": "state", "entity": hub[key], "state_not": ["unavailable", "unknown"]} for key in ("knowledge", "boiler_response")]}]
    assert note["content"].startswith("The E32 learns all this by itself while the heating runs.\n\n<details>")
    # The boiler's response in one sentence, and yesterday compared with usual; each empty (hidden) without text.
    for card in (boiler, insights):
        assert card["type"] == "markdown" and card["show_empty"] is False
    hass.states.async_set(hub["boiler_response"], "learned", {"sentence": "Your boiler holds about 50 °C and rests 9 minutes; "
                                                               "near the target the E32 asks at most 48 °C."})
    assert render(hass, boiler) == ("<ha-icon icon=\"mdi:water-boiler\"></ha-icon> Your boiler holds about 50 °C and rests 9 "
                                    "minutes; near the target the E32 asks at most 48 °C.")
    hass.states.async_set(hub["learned_overview"], "x", {"insights": [
        {"text": "Yesterday used 34 % more gas per degree of cold than usual.",
         "meaning": "A window or door left open, or a room set warmer, can cause this."}]})
    assert render(hass, insights) == ("**Yesterday compared with usual**\n- Yesterday used 34 % more gas per degree of cold than "
                                      "usual.<br>*A window or door left open, or a room set warmer, can cause this.*")
    hass.states.async_set(hub["learned_overview"], "x", {"insights": []})
    hass.states.async_set(hub["boiler_response"], "unknown", {})
    assert render(hass, insights) == "" and render(hass, boiler) == ""
    # The rest of the Learning view follows unchanged.
    assert [s["cards"][0]["heading"] for s in learning["sections"][1:4]] == [
        "What the thermostat has learned", "House and boiler", "What it changed by itself"]


@pytest.mark.asyncio
async def test_no_knowledge_section_without_its_sensors(hass):
    learning, _, _ = learning_installation(hass, hub_keys=("learned_overview",))
    assert learning["sections"][0]["cards"][0]["heading"] == "What the thermostat has learned"
    assert "openthermostat-knowledge" not in json.dumps(learning)


@pytest.mark.asyncio
@pytest.mark.parametrize("language, heading, insights", [("nl", "Wat de E32 weet", "Gisteren vergeleken met normaal"),
                                                          ("pl", "Co wie E32", "Wczoraj w porównaniu ze zwykłymi dniami")])
async def test_the_knowledge_section_in_dutch_and_polish(hass, language, heading, insights):
    learning, hub, _ = learning_installation(hass, language)
    cards = learning["sections"][0]["cards"]
    assert cards[0]["heading"] == heading and f"**{insights}**" in cards[3]["content"]


@pytest.mark.asyncio
async def test_the_heating_curve_sits_with_weather_compensation(hass):
    learning, _, controls = learning_installation(hass)
    settings = next(s["cards"] for s in learning["sections"] if s["cards"][0].get("heading") == "Smart warm-up and weather compensation")
    entities = [card.get("entity") for card in settings[1:5]]
    assert entities == [controls[key] for key in ("apply_learned", "weather_curve", "curve_design_flow_c", "curve")]
    curve = settings[4]
    assert curve == {"type": "custom:openthermostat-heating-curve", "entity": controls["curve"], "grid_options": {"columns": 12},
                     "visibility": [{"condition": "state", "entity": controls["curve"], "state_not": ["unavailable", "unknown"]}]}
    assert e32_flow.CURVE_CARD_TYPE == curve["type"]


@pytest.mark.asyncio
async def test_no_heating_curve_without_its_sensor(hass):
    """Firmware before beta.19 (no flow document), or the sensor disabled: no card."""
    without = {key: domain for key, domain in FLOW.items() if key != "curve"}
    learning, _, _ = learning_installation(hass, hub_keys=(), flow=without)
    assert "openthermostat-heating-curve" not in json.dumps(learning)


# -- what the card draws ------------------------------------------------------------------------------------------


def test_the_standard_slope_follows_the_water_temperature_in_hard_frost():
    """WeatherCurve::slopeFor: (design − 20) / 30, within 0.2..2.5; floor heating 40 °C, radiators 55 °C."""
    assert e32_flow.standard_slope(40) == 0.667 and e32_flow.standard_slope(55) == 1.167
    assert e32_flow.standard_slope(25) == 0.2 and e32_flow.standard_slope(80) == 2.0
    for odd in (0, 24, 81, None, 40.0, "55"):
        assert e32_flow.standard_slope(odd) is None, odd


def test_the_design_flow_the_e32_uses():
    plan = {"rooms": [{"id": "a", "emitter": "floor"}, {"id": "b", "emitter": "radiator"}]}
    assert e32_flow.design_flow({"curve_design_flow_c": 0}, plan) == 55  # one radiator room makes it a radiator circuit
    assert e32_flow.design_flow(None, {"rooms": [{"emitter": "floor"}]}) == 40
    assert e32_flow.design_flow({"curve_design_flow_c": 48}, plan) == 48  # the owner's own choice
    assert e32_flow.design_flow(None, None, {"a": {"emitter": "radiator"}}) == 55  # the learned rooms without a plan
    assert e32_flow.design_flow(None, None) is None


def test_the_room_temperature_the_curve_starts_from():
    rooms = {"a": {"status": "ok", "setpoint": 21.0}, "b": {"status": "fallback", "setpoint": 19.5},
             "c": {"status": "stale", "setpoint": 23.0}, "d": {"status": "inactive", "setpoint": 22.0}}
    assert e32_flow.curve_room_c(rooms) == 21.0  # the highest target of the rooms the E32 heats now
    assert e32_flow.curve_room_c({"c": rooms["c"]}) == 20 and e32_flow.curve_room_c({}) == 20


def test_the_chart_figures():
    plan = {"minimum_flow_c": 28, "maximum_flow_c": 55, "rooms": [{"emitter": "floor"}]}
    assert e32_flow.curve_chart({"curve_design_flow_c": 0}, plan, {}, {"a": {"status": "ok", "setpoint": 21}}, 6.46) == {
        "design_flow_c": 40, "standard_slope": 0.667, "room_c": 21, "outdoor_c": 6.5, "minimum_flow_c": 28, "maximum_flow_c": 55}
    assert e32_flow.curve_chart(None, None, None, None, None) == {
        "design_flow_c": None, "standard_slope": None, "room_c": 20, "outdoor_c": None, "minimum_flow_c": None,
        "maximum_flow_c": None}


@pytest.mark.asyncio
async def test_the_outdoor_temperature_is_the_one_the_e32_uses(hass):
    from homeassistant.const import UnitOfTemperature
    hub = HeatingHub("fixture")
    entry = SimpleNamespace(entry_id="e", options={"energy_outdoor_entity": "sensor.outside"})
    boiler = er.async_get(hass).async_get_or_create("sensor", "open_thermostat", "fixture_boiler_fields_v1_outdoor_temperature",
                                                    suggested_object_id="boiler_outdoor").entity_id
    hass.states.async_set(boiler, "6.5", {"unit_of_measurement": UnitOfTemperature.CELSIUS})
    hass.states.async_set("sensor.outside", "41.9", {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT})
    for source, expected in (("boiler", 6.5), ("ha", 5.5), (None, None)):
        hub.summary = {"schema": 1, "learned": {"schema": 1, "inputs": {"outdoor": source}}}
        value = e32_flow.curve_outdoor(hass, entry, hub)
        assert (value if value is None else round(value, 1)) == expected, source
    hass.states.async_set(boiler, "unavailable", {})
    hub.summary = {"schema": 1, "learned": {"schema": 1, "inputs": {"outdoor": "boiler"}}}
    assert e32_flow.curve_outdoor(hass, entry, hub) is None


def test_the_curve_sensor_carries_what_the_card_draws():
    hub = HeatingHub("fixture")
    hub.update({"schema": 1, "revision": 1, "mode": "active", "request": {"heat": True, "flow_c": 46, "reason": "heating"},
                "ha_entities": [], "rooms": [{"id": "a", "name": "A", "status": "ok", "setpoint": 21.5}]})
    hub.update_summary({"schema": 1, "flow": {"curve": {"state": "applied", "flow_c": 46, "slope": 0.71, "slope_source": "house"}}})
    hub.plan = SimpleNamespace(plan={"minimum_flow_c": 30, "maximum_flow_c": 60, "rooms": [{"emitter": "radiator"}]})
    sensor = e32_flow.FlowTemperatureSensor(hub, "flow_curve")
    assert sensor.unique_id == "fixture_flow_curve" and sensor.native_value == 46
    assert sensor.extra_state_attributes == {"state": "applied", "slope": 0.71, "slope_source": "house", "design_flow_c": 55,
                                             "standard_slope": 1.167, "room_c": 21.5, "outdoor_c": None,
                                             "minimum_flow_c": 30, "maximum_flow_c": 60}
    assert set(e32_flow.CURVE_CHART_KEYS) <= sensor._unrecorded_attributes
    learned = e32_flow.FlowTemperatureSensor(hub, "flow_learned")  # the other flow sensors stay as they were
    assert "standard_slope" not in (learned.extra_state_attributes or {})
