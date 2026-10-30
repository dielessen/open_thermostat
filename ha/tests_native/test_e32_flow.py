"""HA controls and sensors for the E32 flow options (beta.19): weather curve, learned flow, gas calibration, last night."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.open_thermostat import controller_link as link_module
from custom_components.open_thermostat import e32_flow as module
from custom_components.open_thermostat.controller_link import ControllerLinkError, HeatingPlanRejected
from custom_components.open_thermostat.heating_link import HeatingHub, track_entities
from custom_components.open_thermostat.room_plan import RoomPlanLink

SETTINGS = {"weather_curve": False, "apply_learned": False, "curve_design_flow_c": 0}
STATUS = {"schema": 1, "revision": 4, "mode": "shadow", "request": {"heat": True, "flow_c": 36, "reason": "heating"},
          "ha_entities": [], "rooms": []}
# fw/telemetry/summary (learned header with its gas calibration) and fw/telemetry/flow, merged by the hub.
FLOW = {"source": "curve", "rule_flow_c": 38, "applied_flow_c": 41,
        "curve": {"state": "applied", "flow_c": 41, "slope": 0.67, "slope_source": "design"},
        "learned": {"state": "not_ready", "flow_c": None}, "optimum_start": "advice",
        "yesterday": {"rule_mean_c": 38.4, "applied_mean_c": 40.9, "curve_mean_c": 41.2, "learned_mean_c": None}}
GAS = {"status": "calibrated", "confidence": "medium", "factor": 0.93, "kw_at_full_modulation": 22.3, "kw_source": "meter"}
NIGHT = {"nights": 3, "model_ratio": 1.08, "last": {"switch_utc": 1793248200, "status": "measured", "heating_m3": 1.734,
                                                     "hot_water_m3": 0.178, "predicted_program_m3": 1.6, "recommended": "program"}}


def summary(flow=FLOW, night=NIGHT, gas=GAS):
    value = {"schema": 1, "learned": {"schema": 1, "applied": False, "status": "learning", "heating_periods": 3, "inputs": {}},
             "dhw": {"method": "flow", "clock_known": True, "today": {}}}
    if gas is not None:
        value["learned"]["gas"] = deepcopy(gas)
    if flow is not None:
        value["flow"] = deepcopy(flow)
    if night is not None:
        value["night_gas"] = deepcopy(night)
    return value


class FakeE32:
    """The E32 /config/heating/flow contract: partial changes, refusals by name, 404 on older firmware."""

    def __init__(self, settings=SETTINGS):
        self.settings = deepcopy(settings)
        self.calls, self.logins = [], 0
        self.fail = None
        self.missing = False

    def client(self, address):
        e32 = self

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def async_login(self, password):
                assert address == "http://192.168.1.206" and password == "secret"
                e32.logins += 1

            async def async_read_heating_plan(self):  # the room plan link reads its plan on the same status
                return {"schema": 1, "revision": 4, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60, "rooms": []}

            async def async_flow_settings(self, change=None):
                e32.calls.append(deepcopy(change))
                if e32.missing:
                    raise ControllerLinkError("controller_update_required")
                if change is not None and e32.fail:
                    raise e32.fail
                if change is not None:
                    e32.settings.update(change)
                return deepcopy(e32.settings)
        return Client()


def flow_link(hass, e32):
    hub = HeatingHub("fixture")
    plan = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    plan._client = lambda: e32.client("http://192.168.1.206")
    hub.plan = plan
    return hub, module.FlowSettingsLink(hass, hub, plan)


def test_settings_are_checked_before_they_are_shown():
    assert module.decode_settings(SETTINGS) == SETTINGS
    assert module.decode_settings({**SETTINGS, "curve_design_flow_c": 45, "extra": 1}) == {**SETTINGS, "curve_design_flow_c": 45}
    for bad in (None, [], {**SETTINGS, "weather_curve": 1}, {**SETTINGS, "apply_learned": None},
                {**SETTINGS, "curve_design_flow_c": 24}, {**SETTINGS, "curve_design_flow_c": 81},
                {**SETTINGS, "curve_design_flow_c": 45.0}, {**SETTINGS, "curve_design_flow_c": True},
                {k: v for k, v in SETTINGS.items() if k != "apply_learned"}):
        assert module.decode_settings(bad) is None


@pytest.mark.asyncio
async def test_controls_appear_once_read_and_write_one_field_through_the_stored_connection(hass):
    e32 = FakeE32()
    hub, link = flow_link(hass, e32)
    added = []
    remove = [track_entities(link, added.extend, {}, module._wanted_switches),
              track_entities(link, added.extend, {}, module._wanted_selects)]
    link.hub_changed()
    await hass.async_block_till_done()
    assert e32.calls == [] and added == []  # the E32 is not online yet: nothing is asked
    hub.update(STATUS)
    link.hub_changed()
    await hass.async_block_till_done()
    assert e32.calls == [None]
    curve, learned, design = added
    assert [e.unique_id for e in added] == ["fixture_flow_weather_curve", "fixture_flow_apply_learned",
                                            "fixture_flow_curve_design_flow_c"]
    assert [e.translation_key for e in added] == ["flow_weather_curve", "flow_apply_learned", "flow_curve_design_flow_c"]
    assert all(e.entity_category is EntityCategory.CONFIG and e.available for e in added)
    assert all(e.device_info["identifiers"] == {("open_thermostat", "fixture")} for e in added)  # the product device
    # The stored 0 is "automatic": a choice, never shown as 0 °C (nor converted to °F).
    assert (curve.is_on, learned.is_on, design.current_option) == (False, False, "automatic")
    assert design.options == ["automatic", *(str(c) for c in range(25, 81))]
    assert design.device_class is None
    # Each write is one partial change; the E32's answer is the read-back.
    curve.async_write_ha_state = learned.async_write_ha_state = design.async_write_ha_state = Mock()
    await curve.async_turn_on()
    await design.async_select_option("45")
    await learned.async_turn_on()
    await learned.async_turn_off()
    assert e32.calls[1:] == [{"weather_curve": True}, {"curve_design_flow_c": 45}, {"apply_learned": True},
                             {"apply_learned": False}]
    assert (curve.is_on, learned.is_on, design.current_option) == (True, False, "45")
    await design.async_select_option("automatic")
    assert design.current_option == "automatic" and e32.calls[-1] == {"curve_design_flow_c": 0}
    # Values the E32 would refuse never leave Home Assistant.
    for value in ("0", "10", "24", "45.5", "81"):
        with pytest.raises(ServiceValidationError) as error:
            await design.async_select_option(value)
        assert error.value.translation_key == "flow_design_invalid"
        assert error.value.translation_placeholders == {"minimum": "25", "maximum": "80"}
    assert len(e32.calls) == 6
    # The slow poll: once per call while online, never while offline; a second read changes nothing.
    link.poll()
    await hass.async_block_till_done()
    assert len(e32.calls) == 7 and len(added) == 3
    hub.update(None)
    link.hub_changed()
    assert not any(e.available for e in added)
    link.poll()
    await hass.async_block_till_done()
    assert len(e32.calls) == 7
    # Changed on the E32 page while Home Assistant was away: read again when it is back.
    e32.settings["weather_curve"] = False
    hub.update(STATUS)
    link.hub_changed()
    await hass.async_block_till_done()
    assert len(e32.calls) == 8 and curve.is_on is False and all(e.available for e in added)
    for callback in remove:
        callback()
    link.stop()
    hub.plan.stop()


@pytest.mark.parametrize("failure,error_type,key,placeholders", [
    (HeatingPlanRejected(400, "invalid_value"), ServiceValidationError, "flow_settings_rejected", {"error": "invalid_value"}),
    (HeatingPlanRejected(400, "invalid_key"), ServiceValidationError, "flow_settings_rejected", {"error": "invalid_key"}),
    (HeatingPlanRejected(503, "save_unconfirmed"), HomeAssistantError, "flow_settings_unconfirmed", None),
    (link_module.ControllerLoginRejected(), HomeAssistantError, "room_plan_password", None),
    (ControllerLinkError("controller_unreachable"), HomeAssistantError, "flow_settings_unreachable",
     {"error": "controller_unreachable"}),
])
@pytest.mark.asyncio
async def test_refusals_become_clear_errors_and_keep_the_stored_value(hass, failure, error_type, key, placeholders):
    e32 = FakeE32()
    hub, link = flow_link(hass, e32)
    hub.update(STATUS)
    await link.async_refresh()
    e32.fail = failure
    switch = module.FlowOptionSwitch(link, "weather_curve")
    with pytest.raises(error_type) as error:
        await switch.async_turn_on()
    assert error.value.translation_key == key and error.value.translation_placeholders == placeholders
    assert switch.is_on is False and link.settings == SETTINGS
    hub.plan.stop()


@pytest.mark.asyncio
async def test_firmware_without_the_options_shows_no_controls_and_is_not_asked_again_until_it_is_back(hass):
    e32 = FakeE32()
    e32.missing = True
    hub, link = flow_link(hass, e32)
    added = []
    remove = track_entities(link, added.extend, {}, module._wanted_switches)
    hub.update(STATUS)
    link.hub_changed()
    await hass.async_block_till_done()
    assert link.unsupported and added == [] and len(e32.calls) == 1
    link.poll()
    await hass.async_block_till_done()
    assert len(e32.calls) == 1
    # Updated firmware: the E32 restarts (offline, online) and the controls appear.
    e32.missing = False
    hub.update(None)
    link.hub_changed()
    hub.update(STATUS)
    link.hub_changed()
    await hass.async_block_till_done()
    assert len(e32.calls) == 2 and len(added) == 2
    with pytest.raises(HomeAssistantError):
        await module.FlowSettingsLink(hass, hub, hub.plan).async_change({"weather_curve": True})  # never read: no write
    remove()
    hub.plan.stop()


@pytest.mark.asyncio
async def test_a_refused_password_is_never_tried_again_by_the_poll(hass):
    e32 = FakeE32()
    hub, link = flow_link(hass, e32)
    hub.plan.login_rejected = True
    hub.update(STATUS)
    link.hub_changed()
    link.poll()
    await hass.async_block_till_done()
    assert e32.calls == [] and e32.logins == 0
    hub.plan.stop()


def test_sensors_follow_the_summary_and_stay_few():
    hub = HeatingHub("fixture")
    hub.update(STATUS)
    assert list(module.wanted_sensors(hub)) == []  # firmware before beta.19: nothing
    hub.update_summary(summary(night={"nights": 0, "model_ratio": None, "last": None}))
    sensors = {key: factory() for key, factory in module.wanted_sensors(hub)}
    assert list(sensors) == [("flow", "source"), ("flow", "flow_curve"), ("flow", "flow_learned"), ("flow", "flow_rule"),
                             ("flow", "slope"), ("gas", "calibration"), ("gas", "full_power")]
    # Sensible defaults: the source and what curve and learned flow ask for; the rest diagnostic, rare ones off.
    enabled = {key for key, s in sensors.items() if s.entity_registry_enabled_default}
    assert enabled == {("flow", "source"), ("flow", "flow_curve"), ("flow", "flow_learned"), ("gas", "calibration")}
    assert [k for k, s in sensors.items() if s.entity_category is not EntityCategory.DIAGNOSTIC] == [("flow", "source")]
    assert len({s.unique_id for s in sensors.values()}) == len(sensors)
    assert all(s.unique_id.startswith("fixture_") and s.available for s in sensors.values())
    source = sensors[("flow", "source")]
    assert source.native_value == "curve" and source.options == ["rule", "curve", "learned", "optimum_start"]
    assert source.extra_state_attributes == {
        "applied_flow_c": 41, "rule_flow_c": 38, "curve_state": "applied", "learned_state": "not_ready",
        "optimum_start": "advice", "yesterday_rule_mean_c": 38.4, "yesterday_applied_mean_c": 40.9,
        "yesterday_curve_mean_c": 41.2, "yesterday_learned_mean_c": None}
    curve, learned, rule = (sensors[("flow", k)] for k in ("flow_curve", "flow_learned", "flow_rule"))
    assert (curve.native_value, learned.native_value, rule.native_value) == (41, None, 38)
    assert curve.extra_state_attributes == {"state": "applied", "slope": 0.67, "slope_source": "design"}
    assert learned.extra_state_attributes == {"state": "not_ready"} and rule.extra_state_attributes is None
    assert sensors[("flow", "slope")].native_value == 0.67
    gas = sensors[("gas", "calibration")]
    assert gas.native_value == "calibrated"
    assert gas.extra_state_attributes == {"confidence": "medium", "factor": 0.93, "kw_source": "meter"}
    assert sensors[("gas", "full_power")].native_value == 22.3
    # Last night's gas only once a night was measured with a gas meter.
    hub.update_summary(summary())
    night = dict(module.wanted_sensors(hub))[("night_gas",)]()
    assert night.native_value == 1.734 and night.translation_key == "night_heating_gas"
    assert night.extra_state_attributes == {"status": "measured", "hot_water_m3": 0.178, "predicted_m3": 1.6,
                                            "recommended": "program", "morning": "2026-10-29T04:30:00+00:00",
                                            "model_ratio": 1.08, "nights": 3}
    hub.update_summary(summary(night={**NIGHT, "last": {**NIGHT["last"], "status": "no_meter", "heating_m3": None}}))
    assert night.native_value is None and night.extra_state_attributes["status"] == "no_meter"
    assert ("night_gas",) not in dict(module.wanted_sensors(hub))
    # Malformed or unknown values are not shown as facts.
    hub.update_summary(summary(flow={**FLOW, "source": "boiler", "rule_flow_c": 900, "curve": "x"},
                               gas={**GAS, "status": "maybe", "confidence": "total"}))
    assert source.native_value is None and source.extra_state_attributes["rule_flow_c"] is None
    assert curve.native_value is None and gas.native_value is None
    assert gas.extra_state_attributes["confidence"] is None
    # Offline: unavailable, nothing invented.
    hub.update(None)
    assert not any(s.available for s in (*sensors.values(), night))


@pytest.mark.asyncio
async def test_platforms_add_flow_entities_only_for_a_product_with_a_stored_connection(hass, monkeypatch):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat import product
    from custom_components.open_thermostat import room_plan
    from custom_components.open_thermostat.const import DOMAIN
    from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
    from homeassistant.const import Platform
    assert Platform.SWITCH in integration._shadow_platforms(True)
    assert Platform.SWITCH not in integration._shadow_platforms(False)
    e32 = FakeE32()
    monkeypatch.setattr(room_plan, "ControllerClient", e32.client)
    monkeypatch.setattr(module, "add_options", lambda hass, entry, options=None: {})
    credentials = {CONTROLLER_ADDRESS: "http://192.168.1.206", CONTROLLER_PASSWORD: "secret"}
    for product_entry, data, expected in ((True, {}, 0), (False, credentials, 0), (True, credentials, 3)):
        monkeypatch.setattr(product, "is_product", lambda entry, value=product_entry: value)
        hass.data[DOMAIN] = {"e": {}}
        unload, added = [], []
        entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture", **data}, async_on_unload=unload.append)
        await module.async_setup_switches(hass, entry, added.extend)
        await module.async_setup_selects(hass, entry, added.extend)
        hub = hass.data[DOMAIN]["e"].get("heating_hub")
        if hub is not None:
            hub.update(STATUS)
        await hass.async_block_till_done()
        assert len(added) == expected
        if expected:
            assert e32.calls == [None]  # one read for both platforms
        for callback in unload:
            callback()


@pytest.mark.asyncio
@pytest.mark.parametrize("language,names", [
    ("en", {"switch.weather_curve": "OpenThermostat Weather-compensated heating curve",
            "switch.apply_learned": "OpenThermostat Use learned flow and optimum start",
            "select": "OpenThermostat Flow at −10 °C", "sensor.source": "OpenThermostat Flow source",
            "sensor.gas": "OpenThermostat Gas calibration", "sensor.night": "OpenThermostat Last night's heating gas"},
     ),
    ("nl", {"switch.weather_curve": "OpenThermostat Weersafhankelijke stooklijn",
            "switch.apply_learned": "OpenThermostat Geleerde aanvoer en optimale start gebruiken",
            "select": "OpenThermostat Aanvoer bij −10 °C", "sensor.source": "OpenThermostat Bron aanvoertemperatuur",
            "sensor.gas": "OpenThermostat Gasijking", "sensor.night": "OpenThermostat Gas voor verwarmen afgelopen nacht"}),
])
async def test_entities_on_real_platforms_have_translated_names_and_valid_states(hass, monkeypatch, language, names):
    """Real HA entity platforms and translation resources accept every new entity, on the product device."""
    import logging
    from datetime import timedelta
    from pathlib import Path
    from homeassistant import loader
    from homeassistant.helpers import area_registry as ar, device_registry as dr, translation
    from homeassistant.helpers.entity_platform import EntityPlatform
    from unittest.mock import AsyncMock
    from test_room_plan import json_manifest
    from test_v1_native import entry
    component = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    loader.async_setup(hass)
    await ar.async_load(hass, load_empty=True)
    config_entry = entry(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("open_thermostat", "fixture")}, name="OpenThermostat")
    integration = loader.Integration(hass, "custom_components.open_thermostat", component,
                                     json_manifest(component), top_level_files={p.name for p in component.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    hass.config.language = language
    e32 = FakeE32()
    hub, link = flow_link(hass, e32)
    hub.update(STATUS)
    hub.update_summary(summary())
    await link.async_refresh()
    entities = {"switch.weather_curve": module.FlowOptionSwitch(link, "weather_curve"),
                "switch.apply_learned": module.FlowOptionSwitch(link, "apply_learned"),
                "select": module.FlowDesignSelect(link), "sensor.source": module.FlowSourceSensor(hub),
                "sensor.gas": module.GasCalibrationSensor(hub), "sensor.night": module.NightGasSensor(hub)}
    platforms = {}
    try:
        for key, entity in entities.items():
            domain = key.split(".")[0]
            if domain not in platforms:
                platform = platforms[domain] = EntityPlatform(
                    hass=hass, logger=logging.getLogger(__name__), domain=domain, platform_name="open_thermostat",
                    platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
                platform.config_entry = config_entry
                await platform.platform_data.async_load_translations()
            await platforms[domain].async_add_entities([entity])
        await hass.async_block_till_done()
        for key, entity in entities.items():
            state = hass.states.get(entity.entity_id)
            assert state.attributes["friendly_name"] == names[key], key
            assert state.state not in ("unavailable", "unknown"), key
            assert entity.device_entry.id == device.id, key
        assert hass.states.get(entities["switch.weather_curve"].entity_id).state == "off"
        assert hass.states.get(entities["sensor.source"].entity_id).state == "curve"
        await entities["switch.weather_curve"].async_turn_on()
        await hass.async_block_till_done()
        assert hass.states.get(entities["switch.weather_curve"].entity_id).state == "on"
        assert e32.calls[-1] == {"weather_curve": True}
        hub.update(None)
        await hass.async_block_till_done()
        assert all(hass.states.get(e.entity_id).state == "unavailable" for e in entities.values())
    finally:
        await asyncio.gather(*(p.async_reset() for p in platforms.values()))
        hub.plan.stop()


# -- the HTTP contract -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_controller_client_speaks_the_flow_options_contract():
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    seen, state = [], {"settings": dict(SETTINGS), "missing": False}

    async def login(request):
        return web.json_response({"ok": True})

    async def session(request):
        return web.json_response({"authenticated": True, "csrf": "c" * 64})

    async def logout(request):
        return web.json_response({})

    async def flow(request):
        if state["missing"]:
            return web.Response(status=404, text="Not found")
        if request.method == "GET":
            return web.json_response(state["settings"])
        seen.append((request.headers.get("X-OpenThermostat-CSRF"), request.headers.get("Content-Type"), await request.json()))
        body = await request.json()
        if body.get("curve_design_flow_c") == 99:
            return web.json_response({"error": "invalid_value"}, status=400)
        if body.get("apply_learned") is True and state.get("flash_fails"):
            return web.json_response({"error": "save_unconfirmed"}, status=503)
        state["settings"].update(body)
        return web.json_response(state["settings"])

    app = web.Application()
    app.router.add_post("/auth/login", login)
    app.router.add_get("/auth/session", session)
    app.router.add_post("/auth/logout", logout)
    app.router.add_route("*", "/config/heating/flow", flow)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        client = link_module.ControllerClient("http://192.168.1.206")  # loopback is refused by design
        async with client:
            client.address = f"http://127.0.0.1:{server.port}"
            await client.async_login("secret")
            assert await client.async_flow_settings() == SETTINGS
            assert await client.async_flow_settings({"weather_curve": True}) == {**SETTINGS, "weather_curve": True}
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_flow_settings({"curve_design_flow_c": 99})
            assert (error.value.status, error.value.error) == (400, "invalid_value")
            state["flash_fails"] = True
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_flow_settings({"apply_learned": True})
            assert (error.value.status, error.value.error) == (503, "save_unconfirmed")
            for bad in ({}, [], "x"):
                with pytest.raises(ControllerLinkError, match="^controller_request_invalid$"):
                    await client.async_flow_settings(bad)
            state["missing"] = True  # firmware before beta.19
            with pytest.raises(ControllerLinkError, match="^controller_update_required$"):
                await client.async_flow_settings()
    finally:
        await server.close()
    assert seen[0] == ("c" * 64, "application/json", {"weather_curve": True}) and len(seen) == 3
