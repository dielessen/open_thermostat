"""HA operates the E32 room plan: one field per write, the read revision, one re-read on 409."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.open_thermostat import room_plan as module
from custom_components.open_thermostat.controller_link import HeatingPlanRejected
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.room_plan import (
    RoomFallbackSetpoint, RoomInactiveUntil, RoomPlanLink, RoomStateSelect, decode_plan, set_fallback, set_state)

ROOM = {"id": "woonkamer", "name": "Woonkamer", "state": "active", "inactive_until": 0, "emitter": "floor",
        "sources": [{"type": "ha", "id": "climate.woonkamer"}, {"type": "ble", "id": "a4c138a3e8db"}],
        "setpoint_entity": "climate.woonkamer", "fallback_centi_c": 2000,
        "minimum_centi_c": 1000, "maximum_centi_c": 2400}
PLAN = {"schema": 1, "revision": 4, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60,
        "rooms": [ROOM, {**ROOM, "id": "badkamer", "name": "Badkamer", "emitter": "radiator"}]}
STATUS = {"schema": 1, "revision": 4, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
          "ha_entities": ["climate.woonkamer"],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "inactive_until": 0, "status": "ok",
                     "source": "climate.woonkamer", "temperature": 20.1, "setpoint": 20.0, "demand": False}]}


class FakeE32:
    """The E32 /config/heating contract: a revision per save, 409 for a stale revision."""

    def __init__(self, plan=PLAN):
        self.plan = deepcopy(plan)
        self.posts, self.reads, self.logins = [], 0, 0
        self.before_save = []  # callables run before a POST is judged (another writer)
        self.fail = None

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

            async def async_read_heating_plan(self):
                e32.reads += 1
                return deepcopy(e32.plan)

            async def async_save_heating_plan(self, plan):
                e32.posts.append(deepcopy(plan))
                if e32.before_save:
                    e32.before_save.pop(0)(e32.plan)
                if e32.fail:
                    raise e32.fail
                if plan["revision"] != e32.plan["revision"]:
                    raise HeatingPlanRejected(409, "plan_changed")
                e32.plan = {**deepcopy(plan), "revision": plan["revision"] + 1}
                return deepcopy(e32.plan)
        return Client()


def other_side(field, value, room="badkamer"):
    """The E32 web page saves a change between our read and our write."""
    def save(plan):
        next(r for r in plan["rooms"] if r["id"] == room)[field] = value
        plan["revision"] += 1
    return save


def link(hass, e32):
    hub = HeatingHub("fixture")
    plan = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    plan._client = lambda: e32.client("http://192.168.1.206")
    hub.plan = plan
    return hub, plan


def test_plan_document_is_checked_before_any_change():
    assert decode_plan(PLAN) is PLAN
    for bad in ({**PLAN, "schema": 2}, {**PLAN, "revision": "4"}, {**PLAN, "revision": -1},
                {**PLAN, "rooms": {}}, {**PLAN, "rooms": [{"id": "Bad Id"}]}, {**PLAN, "rooms": [ROOM, ROOM]},
                {key: value for key, value in PLAN.items() if key != "revision"}):
        assert decode_plan(bad) is None


@pytest.mark.asyncio
async def test_a_change_posts_the_whole_plan_with_the_read_revision_and_one_field_changed(hass):
    e32 = FakeE32()
    hub, plan = link(hass, e32)
    stored = await plan.async_change_room("woonkamer", set_state("inactive"))
    expected = deepcopy(PLAN)
    expected["rooms"][0]["state"] = "inactive"
    assert e32.posts == [expected]  # unknown and unrelated fields travel back unchanged
    assert stored["revision"] == 5 and plan.plan == stored and e32.logins == 1


@pytest.mark.asyncio
async def test_a_stale_revision_is_read_again_once_and_the_same_change_reapplied(hass):
    e32 = FakeE32()
    e32.before_save.append(other_side("fallback_centi_c", 1800))
    hub, plan = link(hass, e32)
    stored = await plan.async_change_room("woonkamer", set_fallback(2150))
    assert len(e32.posts) == 2 and e32.reads == 2
    assert [p["revision"] for p in e32.posts] == [4, 5]
    # The other side's change survives; ours is applied on top of the new revision.
    assert stored["revision"] == 6
    assert {r["id"]: r["fallback_centi_c"] for r in stored["rooms"]} == {"woonkamer": 2150, "badkamer": 1800}


@pytest.mark.asyncio
async def test_a_second_conflict_raises_a_clear_error_and_saves_nothing(hass):
    e32 = FakeE32()
    e32.before_save += [other_side("state", "inactive"), other_side("state", "active")]
    hub, plan = link(hass, e32)
    with pytest.raises(HomeAssistantError) as error:
        await plan.async_change_room("woonkamer", set_state("inactive"))
    assert error.value.translation_key == "room_plan_changed"
    assert len(e32.posts) == 2 and e32.plan["rooms"][0]["state"] == "active" and plan.plan is None


@pytest.mark.parametrize("failure,key,placeholders", [
    (HeatingPlanRejected(400, "invalid_room_limits"), "room_plan_rejected", {"error": "invalid_room_limits"}),
    (HeatingPlanRejected(400, "active_mode_not_released"), "room_plan_rejected", {"error": "active_mode_not_released"}),
    (HeatingPlanRejected(503, "save_unconfirmed"), "room_plan_unconfirmed", None),
    (module.ControllerLinkError("controller_unreachable"), "room_plan_unreachable", {"error": "controller_unreachable"}),
])
@pytest.mark.asyncio
async def test_refusals_become_clear_errors_without_a_retry(hass, failure, key, placeholders):
    e32 = FakeE32()
    e32.fail = failure
    hub, plan = link(hass, e32)
    with pytest.raises(HomeAssistantError) as error:
        await plan.async_change_room("woonkamer", set_state("inactive"))
    assert error.value.translation_key == key and error.value.translation_placeholders == placeholders
    assert len(e32.posts) == 1


@pytest.mark.asyncio
async def test_a_room_missing_from_the_plan_or_limits_are_never_written(hass):
    e32 = FakeE32()
    hub, plan = link(hass, e32)
    with pytest.raises(HomeAssistantError) as error:
        await plan.async_change_room("zolder", set_state("inactive"))
    assert error.value.translation_key == "room_plan_room_missing"
    with pytest.raises(ServiceValidationError):
        await plan.async_change_room("woonkamer", set_fallback(2500))  # above this room's 24 °C
    e32.plan = {**PLAN, "revision": "x"}
    with pytest.raises(HomeAssistantError) as error:
        await plan.async_change_room("woonkamer", set_state("inactive"))
    assert error.value.translation_key == "room_plan_invalid" and e32.posts == []


@pytest.mark.asyncio
async def test_the_plan_is_read_when_the_telemetry_reports_a_new_revision(hass):
    e32 = FakeE32()
    hub, plan = link(hass, e32)
    hub.update(STATUS)
    await hass.async_block_till_done()
    assert e32.reads == 1 and plan.revision == 4
    hub.update(STATUS)  # same revision: no new read
    await hass.async_block_till_done()
    assert e32.reads == 1
    e32.plan["revision"] = 5
    hub.update({**STATUS, "revision": 5})
    await hass.async_block_till_done()
    assert e32.reads == 2 and plan.revision == 5
    # Our own write already holds the new revision: its telemetry causes no extra read.
    await plan.async_change_room("woonkamer", set_state("inactive"))
    hub.update({**STATUS, "revision": 6})
    await hass.async_block_till_done()
    assert e32.reads == 3  # only the write's own GET
    plan.stop()


@pytest.mark.asyncio
async def test_a_failed_read_is_retried_after_a_pause(hass):
    hub, plan = link(hass, FakeE32())
    now, attempts = [100.0], []
    plan.clock = lambda: now[0]
    plan._client = lambda: _Failing(attempts)
    hub.update(STATUS)
    await hass.async_block_till_done()
    hub.update(STATUS)
    await hass.async_block_till_done()
    assert attempts == [1] and plan.plan is None
    now[0] += module.RETRY_SECONDS
    hub.update(STATUS)
    await hass.async_block_till_done()
    assert attempts == [1, 1]
    plan.stop()


class _Failing:
    def __init__(self, reads):
        self.reads = reads

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def async_login(self, password):
        self.reads.append(1)
        raise module.ControllerLinkError("controller_unreachable")


@pytest.mark.asyncio
async def test_room_entities_show_the_live_state_and_write_through_the_plan(hass, monkeypatch):
    e32 = FakeE32()
    hub, plan = link(hass, e32)
    hub.update(STATUS)
    await hass.async_block_till_done()
    room = STATUS["rooms"][0]
    select, until, setpoint = RoomStateSelect(hub, room), RoomInactiveUntil(hub, room), RoomFallbackSetpoint(hub, room)
    assert [e.unique_id for e in (select, until, setpoint)] == [
        "fixture_e32_room_woonkamer_state", "fixture_e32_room_woonkamer_inactive_until",
        "fixture_e32_room_woonkamer_fallback_setpoint"]
    assert select.options == ["active", "inactive"] and select.current_option == "active"
    assert until.native_value is None
    assert (setpoint.native_value, setpoint.native_min_value, setpoint.native_max_value, setpoint.native_step) == (20.0, 10.0, 24.0, 0.5)
    assert setpoint.extra_state_attributes["setpoint_entity"] == "climate.woonkamer"

    await select.async_select_option("inactive")
    # Our write (revision 5) is newer than the telemetry (4): show it right away.
    assert select.current_option == "inactive" and e32.plan["rooms"][0]["inactive_until"] == 0

    moment = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
    await until.async_set_value(moment)
    assert e32.plan["rooms"][0]["state"] == "inactive"
    assert e32.plan["rooms"][0]["inactive_until"] == int(moment.timestamp())
    assert until.native_value == moment
    with pytest.raises(ServiceValidationError):
        await until.async_set_value(datetime.now(timezone.utc) - timedelta(minutes=1))

    await setpoint.async_set_native_value(21.3)  # rounded to the 0.5 °C step
    assert e32.plan["rooms"][0]["fallback_centi_c"] == 2150 and setpoint.native_value == 21.5
    with pytest.raises(ServiceValidationError):
        await setpoint.async_set_native_value(29)

    await select.async_select_option("active")
    assert e32.plan["rooms"][0]["state"] == "active" and e32.plan["rooms"][0]["inactive_until"] == 0
    # Each write changed only its own field of its own room.
    assert e32.plan["rooms"][1] == PLAN["rooms"][1]
    # Once the telemetry catches up, the E32's live view is shown again.
    hub.update({**STATUS, "revision": e32.plan["revision"],
                "rooms": [{**room, "state": "inactive", "inactive_until": 0}]})
    assert select.current_option == "inactive"
    hub.update(None)
    assert not select.available and not setpoint.available and not until.available
    plan.stop()


@pytest.mark.asyncio
async def test_platforms_create_room_operation_only_with_a_stored_controller_connection(hass, monkeypatch):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat import product
    from custom_components.open_thermostat.const import DOMAIN
    from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
    from homeassistant.const import Platform
    assert {Platform.BINARY_SENSOR, Platform.UPDATE, Platform.SELECT, Platform.NUMBER,
            Platform.DATETIME} <= set(integration._shadow_platforms(True))
    assert integration._shadow_platforms(False) == [Platform.CLIMATE, Platform.SENSOR]
    e32 = FakeE32()
    monkeypatch.setattr(module, "ControllerClient", e32.client)
    monkeypatch.setattr(module, "add_options", lambda hass, entry, options=None: {})
    credentials = {CONTROLLER_ADDRESS: "http://192.168.1.206", CONTROLLER_PASSWORD: "secret"}
    for product_entry, data, expected in ((True, {}, 0), (False, credentials, 0), (True, credentials, 3)):
        monkeypatch.setattr(product, "is_product", lambda entry, value=product_entry: value)
        hass.data[DOMAIN] = {"e": {}}
        unload, added = [], []
        entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture", **data}, async_on_unload=unload.append)
        for setup in (module.async_setup_selects, module.async_setup_datetimes, module.async_setup_numbers):
            await setup(hass, entry, added.extend)
        hub = hass.data[DOMAIN]["e"].get("heating_hub") or HeatingHub("fixture")
        hub.update(STATUS)
        await hass.async_block_till_done()
        assert len(added) == expected
        if expected:
            assert {type(e) for e in added} == {RoomStateSelect, RoomInactiveUntil, RoomFallbackSetpoint}
            assert e32.reads == 1 and all(e.available for e in added)
        for callback in unload:
            callback()


@pytest.mark.asyncio
async def test_controller_client_speaks_the_heating_plan_contract():
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from custom_components.open_thermostat.controller_link import ControllerClient
    seen, state = [], {"plan": deepcopy(PLAN)}

    async def login(request):
        return web.json_response({"ok": True})

    async def session(request):
        return web.json_response({"authenticated": True, "csrf": "c" * 64})

    async def logout(request):
        return web.json_response({})

    async def heating(request):
        if request.method == "GET":
            return web.json_response(state["plan"])
        seen.append((request.headers.get("X-OpenThermostat-CSRF"), request.headers.get("Origin"),
                     request.headers.get("Content-Type")))
        body = await request.json()
        if body["revision"] != state["plan"]["revision"]:
            return web.json_response({"error": "plan_changed"}, status=409)
        if body.get("mode") == "active":
            return web.json_response({"error": "active_mode_not_released"}, status=400)
        if body.get("mode") == "flash":
            return web.json_response({"error": "save_unconfirmed"}, status=503)
        state["plan"] = {**body, "revision": body["revision"] + 1}
        return web.json_response(state["plan"])

    app = web.Application()
    app.router.add_post("/auth/login", login)
    app.router.add_get("/auth/session", session)
    app.router.add_post("/auth/logout", logout)
    app.router.add_route("*", "/config/heating", heating)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    origin = f"http://127.0.0.1:{server.port}"
    try:
        client = ControllerClient("http://192.168.1.206")  # loopback is refused by design
        async with client:
            client.address = origin
            await client.async_login("secret")
            plan = await client.async_read_heating_plan()
            assert plan == PLAN
            stored = await client.async_save_heating_plan(plan)
            assert stored["revision"] == 5
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_save_heating_plan(plan)  # still revision 4
            assert (error.value.status, error.value.error) == (409, "plan_changed")
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_save_heating_plan({**stored, "mode": "active"})
            assert (error.value.status, error.value.error) == (400, "active_mode_not_released")
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_save_heating_plan({**stored, "mode": "flash"})
            assert error.value.error == "save_unconfirmed"
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_save_heating_plan({**stored, "padding": "x" * 4096})
            assert error.value.error == "plan_too_large"
    finally:
        await server.close()
    assert seen[0] == ("c" * 64, origin, "application/json")
    assert len(seen) == 4  # the oversized plan never left Home Assistant


@pytest.mark.asyncio
@pytest.mark.parametrize("language,names", [
    ("en", {"sensor": "Woonkamer temperature", "select": "Woonkamer room state", "number": "Woonkamer fallback setpoint",
            "datetime": "Woonkamer inactive until", "binary_sensor": "Woonkamer heat demand"}),
    ("nl", {"sensor": "Temperatuur Woonkamer", "select": "Ruimtestand Woonkamer", "number": "Terugvaltemperatuur Woonkamer",
            "datetime": "Woonkamer inactief tot", "binary_sensor": "Warmtevraag Woonkamer"}),
])
async def test_entities_on_real_platforms_have_translated_names_and_valid_states(hass, monkeypatch, language, names):
    """Real HA entity platforms and translation resources accept every new entity."""
    import asyncio
    import logging
    from pathlib import Path
    from homeassistant import loader
    from homeassistant.helpers import translation
    from homeassistant.helpers.entity_platform import EntityPlatform
    from unittest.mock import AsyncMock
    from custom_components.open_thermostat.heating_link import RoomDemandBinarySensor, RoomTemperatureSensor
    component = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    loader.async_setup(hass)
    integration = loader.Integration(hass, "custom_components.open_thermostat", component,
                                     json_manifest(component), top_level_files={p.name for p in component.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    hass.config.language = language
    e32 = FakeE32()
    hub, plan = link(hass, e32)
    hub.update(STATUS)
    await hass.async_block_till_done()
    room = STATUS["rooms"][0]
    entities = {"sensor": RoomTemperatureSensor(hub, room), "select": RoomStateSelect(hub, room),
                "number": RoomFallbackSetpoint(hub, room), "datetime": RoomInactiveUntil(hub, room),
                "binary_sensor": RoomDemandBinarySensor(hub, room)}
    platforms = []
    try:
        for domain, entity in entities.items():
            platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain=domain,
                                      platform_name="open_thermostat", platform=None,
                                      scan_interval=timedelta(seconds=30), entity_namespace=None)
            await platform.platform_data.async_load_translations()
            platforms.append(platform)
            await platform.async_add_entities([entity])
        await hass.async_block_till_done()
        for domain, entity in entities.items():
            state = hass.states.get(entity.entity_id)
            assert state.attributes["friendly_name"] == names[domain], domain
            assert state.state not in ("unavailable",), domain
        assert hass.states.get(entities["select"].entity_id).state == "active"
        assert hass.states.get(entities["number"].entity_id).attributes["max"] == 24.0
        await entities["select"].async_select_option("inactive")
        await hass.async_block_till_done()
        assert hass.states.get(entities["select"].entity_id).state == "inactive"
        hub.update(None)
        await hass.async_block_till_done()
        assert all(hass.states.get(e.entity_id).state == "unavailable" for e in entities.values())
    finally:
        await asyncio.gather(*(p.async_reset() for p in platforms))
        plan.stop()


def json_manifest(component):
    import json
    return json.loads((component / "manifest.json").read_text())
