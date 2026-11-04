"""The Learning view's new cards (E32 rc.5): what the E32 knows, and water temperature by outdoor temperature.

The knowledge section comes first on the Learning view: the knowledge card (a ring, frontend/heating-curve-card.js);
then your boiler (the boiler's response in one sentence) and the heating-curve card under its own heading, as the
owner's sketch (the order of all seven: test_dashboard_learning_sketch.py); each hidden until the E32 reports it. The
heating-curve card reads what "Water temperature by weather compensation" carries, all in °C: the slope and where it
comes from, the standard slope from the water temperature in hard frost the E32 publishes (WeatherCurve::slopeFor),
the room temperature, the outdoor temperature now, the limits (the highest also within the boiler's own maximum), the
line's value now and what weather compensation asks.
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


def known(entity_id):
    return {"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}


@pytest.mark.asyncio
async def test_what_the_e32_knows_comes_first_on_the_learning_view(hass):
    learning, hub, _ = learning_installation(hass)
    section, boiler = learning["sections"][:2]
    heading, knowledge = section["cards"]
    assert heading == {"type": "heading", "heading": "What the E32 knows", "heading_style": "title", "icon": "mdi:home-analytics"}
    # The knowledge card: a ring beside "The E32 knows your house: 70 %" and what it still learns (the sixth card
    # module); the card says it learns by itself, so no note repeats it under the card (the owner's sketch, rc.5).
    assert knowledge == {"type": "custom:openthermostat-knowledge", "entity": hub["knowledge"], "grid_options": {"columns": 12},
                         "visibility": [known(hub["knowledge"])]}
    # Hidden as a whole until the E32 reports what it knows (rc.5).
    assert section["visibility"] == [{"condition": "or", "conditions": [known(hub["knowledge"])]}]
    # Your boiler: the boiler's response in one sentence behind a flame in the heating colour; hidden as a whole while
    # the response is unknown (every known state has its sentence).
    heading, sentence = boiler["cards"]
    assert (heading["heading"], heading["icon"]) == ("Your boiler", "mdi:water-boiler")
    assert boiler["visibility"] == [{"condition": "or", "conditions": [known(hub["boiler_response"])]}]
    assert sentence["type"] == "markdown" and "show_empty" not in sentence and "visibility" not in sentence
    hass.states.async_set(hub["boiler_response"], "learned", {"sentence": "Your boiler holds about 50 °C and rests 9 minutes; "
                                                               "near the target the E32 asks at most 48 °C."})
    assert render(hass, sentence) == ('<font color="#ff6f22"><ha-icon icon="mdi:fire"></ha-icon></font> Your boiler holds '
                                      "about 50 °C and rests 9 minutes; near the target the E32 asks at most 48 °C.")
    hass.states.async_set(hub["boiler_response"], "unknown", {})
    assert render(hass, sentence) == ""


@pytest.mark.asyncio
async def test_no_knowledge_section_without_its_sensors(hass):
    learning, _, _ = learning_installation(hass, hub_keys=("learned_overview",))
    assert learning["sections"][0]["cards"][0]["heading"] == "Water temperature by outdoor temperature"
    assert "openthermostat-knowledge" not in json.dumps(learning)
    assert not {"What the E32 knows", "Your boiler"} & {s["cards"][0]["heading"] for s in learning["sections"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("language, headings", [
    ("nl", ["Wat de E32 weet", "Je ketel", "Watertemperatuur bij buitentemperatuur"]),
    ("pl", ["Co wie E32", "Twój kocioł", "Temperatura wody a temperatura zewnętrzna"])])
async def test_the_knowledge_section_in_dutch_and_polish(hass, language, headings):
    learning, hub, _ = learning_installation(hass, language)
    assert [s["cards"][0]["heading"] for s in learning["sections"][:3]] == headings


@pytest.mark.asyncio
async def test_the_heating_curve_has_a_section_of_its_own(hass):
    """The owner's sketch (rc.5): the curve under its own heading (the card leaves out its own title, which would say
    the same), the switches of Smart warm-up and weather compensation as rows in a section of their own."""
    learning, _, controls = learning_installation(hass)
    headed = {s["cards"][0].get("heading"): s for s in learning["sections"]}
    section = headed["Water temperature by outdoor temperature"]
    heading, curve = section["cards"]
    assert heading["icon"] == "mdi:chart-bell-curve-cumulative"
    assert curve == {"type": "custom:openthermostat-heating-curve", "entity": controls["curve"], "show_name": False,
                     "grid_options": {"columns": 12}, "visibility": [known(controls["curve"])]}
    assert section["visibility"] == [{"condition": "or", "conditions": [known(controls["curve"])]}]
    assert e32_flow.CURVE_CARD_TYPE == curve["type"]
    settings = headed["Smart warm-up and weather compensation"]["cards"]
    assert "openthermostat-heating-curve" not in json.dumps(settings)
    rows = settings[1]["entities"]
    assert [row["entity"] for row in rows] == [controls[key] for key in ("apply_learned", "weather_curve",
                                                                         "curve_design_flow_c")]
    # What sets the water temperature now is no setting: it stays on the E32 device (the sketch has three rows).
    assert controls["source"] not in json.dumps(learning)


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
    rooms = {"a": {"status": "ok", "setpoint": 21}}
    # Firmware before rc.5: the design flow worked out as FlowPolicy does, no line value.
    assert e32_flow.curve_chart({"curve_design_flow_c": 0}, plan, {}, rooms, 6.46) == {
        "design_flow_c": 40, "standard_slope": 0.667, "room_c": 21, "outdoor_c": 6.5, "minimum_flow_c": 28, "maximum_flow_c": 55,
        "base_c": None, "flow_c": None}
    assert e32_flow.curve_chart(None, None, None, None, None) == {
        "design_flow_c": None, "standard_slope": None, "room_c": 20, "outdoor_c": None, "minimum_flow_c": None,
        "maximum_flow_c": None, "base_c": None, "flow_c": None}
    # rc.5: the E32's own design flow (a custom one, too: no options link needed), its line value and what it asks, in
    # °C; the highest water temperature also within the boiler's own maximum (FlowPolicy's cap).
    curve = {"state": "applied", "flow_c": 47, "base_c": 41.7, "slope": 0.67, "slope_source": "design", "design_flow_c": 48}
    assert e32_flow.curve_chart(None, plan, {}, rooms, -10, curve, 52) == {
        "design_flow_c": 48, "standard_slope": 0.933, "room_c": 21, "outdoor_c": -10, "minimum_flow_c": 28, "maximum_flow_c": 52,
        "base_c": 41.7, "flow_c": 47}
    assert e32_flow.curve_chart(None, {**plan, "maximum_flow_c": 80}, {}, rooms, -10, curve, None)["maximum_flow_c"] == 80
    assert e32_flow.curve_chart(None, {**plan, "maximum_flow_c": 90}, {}, rooms, -10, curve, 95)["maximum_flow_c"] == 80
    assert e32_flow.curve_chart(None, None, {}, rooms, -10, curve, 65)["maximum_flow_c"] == 65  # the boiler's alone
    for odd in (0, 24, 81, 55.0, "55", None):
        assert e32_flow.curve_chart(None, plan, {}, rooms, -10, {**curve, "design_flow_c": odd})["design_flow_c"] == 40, odd


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


def test_the_curve_sensor_carries_what_the_card_draws(monkeypatch):
    hub = HeatingHub("fixture")
    hub.update({"schema": 1, "revision": 1, "mode": "active", "request": {"heat": True, "flow_c": 46, "reason": "heating"},
                "ha_entities": [], "rooms": [{"id": "a", "name": "A", "status": "ok", "setpoint": 21.5}]})
    # The flow document as the rc.5 firmware sends it (FlowPolicy::addSummary).
    hub.update_summary({"schema": 1, "flow": {"curve": {"state": "applied", "flow_c": 46, "base_c": 44.6, "slope": 0.71,
                                                        "slope_source": "house", "design_flow_c": 55, "windows": 2}}})
    hub.plan = SimpleNamespace(plan={"minimum_flow_c": 30, "maximum_flow_c": 60, "rooms": [{"emitter": "radiator"}]})
    sensor = e32_flow.FlowTemperatureSensor(hub, "flow_curve")
    assert sensor.unique_id == "fixture_flow_curve" and sensor.native_value == 46
    assert sensor.extra_state_attributes == {"state": "applied", "slope": 0.71, "slope_source": "house", "windows": 2,
                                             "design_flow_c": 55,
                                             "standard_slope": 1.167, "room_c": 21.5, "outdoor_c": None,
                                             "minimum_flow_c": 30, "maximum_flow_c": 60, "base_c": 44.6, "flow_c": 46}
    assert set(e32_flow.CURVE_CHART_KEYS) <= sensor._unrecorded_attributes
    # The boiler's own maximum (its 0x16 telegram, read from the E32's boiler fields) caps the lines as FlowPolicy does.
    from custom_components.open_thermostat import heating_advice
    monkeypatch.setattr(heating_advice, "boiler_maximum", lambda client: 52)
    sensor.hass = SimpleNamespace(data={"open_thermostat": {"e": {"v1_connection": SimpleNamespace(client=object())}}})
    sensor.platform = SimpleNamespace(config_entry=SimpleNamespace(entry_id="e", options={}))
    assert sensor.extra_state_attributes["maximum_flow_c"] == 52
    learned = e32_flow.FlowTemperatureSensor(hub, "flow_learned")  # the other flow sensors stay as they were
    assert "standard_slope" not in (learned.extra_state_attributes or {})
