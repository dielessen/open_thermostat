"""UX review of HA 0.4.0b10: one "Add room", a changed or default E32 password, °F, flow limits up to 80 °C.

The night-time "is my heating OK?" sensor has its own tests (test_heating_problem.py).
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import heating_advice
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.controller_link import (
    ControllerLinkError, ControllerLoginRejected, HeatingPlanRejected)
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_PASSWORD
from custom_components.open_thermostat.e32_access import DEFAULT_PASSWORD_ISSUE
from custom_components.open_thermostat.e32_room_flow import (
    flow_celsius, flow_shown, format_program, parse_program, shown as shown_c, FlowError)
from custom_components.open_thermostat.room_plan import RoomPlanLink, has_room_plan
from test_e32_room_flow import (  # noqa: F401  (the manager fixture)
    CREDENTIALS, NEW_ROOM, manager, product, room_form, rooms_menu, shown)
from test_room_plan import PLAN, FakeE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


def documents():
    return {name: json.loads((COMPONENT / name).read_text(encoding="utf-8"))
            for name in ("strings.json", "translations/en.json", "translations/nl.json")}


# -- F09: one "Add room" -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_entry_with_an_e32_room_plan_offers_no_second_add_room(hass, manager):
    """The older HA room record ("zone") is not offered once the E32 plan is the room editor."""
    with_plan, _ = product(hass, FakeE32())
    assert has_room_plan(with_plan)
    assert OpenThermostatConfigFlow.async_get_supported_subentry_types(with_plan) == {}
    # Before the E32 is connected the guided room flow stays: Connect E32 needs one room first.
    hass.config_entries.async_update_entry(with_plan, data={
        k: v for k, v in with_plan.data.items() if k not in CREDENTIALS})
    assert list(OpenThermostatConfigFlow.async_get_supported_subentry_types(with_plan)) == ["zone"]
    # A cached button (HA keeps the type map until a restart) explains where the rooms are now.
    hass.config_entries.async_update_entry(with_plan, data={**with_plan.data, **CREDENTIALS})
    from custom_components.open_thermostat.product_flow import ProductRoomFlow
    flow = ProductRoomFlow()
    flow.hass, flow.handler = hass, (with_plan.entry_id, "zone")
    flow.context = {"source": "user"}
    result = await flow.async_step_user()
    assert result["type"] == "abort" and result["reason"] == "e32_rooms_elsewhere"
    texts = {name: d["config_subentries"]["zone"]["abort"]["e32_rooms_elsewhere"] for name, d in documents().items()}
    assert "Configure → Rooms" in texts["strings.json"] and "Configureren → Ruimtes" in texts["translations/nl.json"]


def test_connecting_the_e32_drops_the_cached_add_room_button():
    source = (COMPONENT / "controller_setup_flow.py").read_text(encoding="utf-8")
    assert 'object.__setattr__(entry, "_supported_subentry_types", None)' in source


# -- F03: a changed password (reauth) and the default password (Repairs) -----------------------


class LoginFake(FakeE32):
    """FakeE32 whose login follows a password and reports default_password like /auth/session."""

    def __init__(self, password="secret", default=None):
        super().__init__()
        self.password, self.default = password, default

    def client(self, address):
        inner = super().client(address)
        e32 = self

        async def login(password):
            e32.logins += 1
            if password != e32.password:
                raise ControllerLoginRejected()
            inner.default_password = e32.default
        inner.async_login = login
        inner.default_password = None
        return inner


@pytest.mark.asyncio
async def test_a_refused_password_starts_reauth_once_and_is_never_tried_again(hass, manager):
    e32 = LoginFake(password="changed-on-the-e32")
    parent, hub = product(hass, e32)
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub, entry=parent)
    link._client = lambda: e32.client("http://192.168.1.206")
    hub.plan = link
    from homeassistant.exceptions import HomeAssistantError
    with pytest.raises(HomeAssistantError) as error:
        await link.async_read()
    assert error.value.translation_key == "room_plan_password"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler("open_thermostat")
    assert [f["context"]["source"] for f in flows] == ["reauth"]
    assert flows[0]["step_id"] == "reauth_confirm"
    # The E32 limits failed logins: Home Assistant does not try the old password again.
    logins = e32.logins
    await link.async_refresh()
    with pytest.raises(HomeAssistantError):
        await link.async_change_room("woonkamer", lambda room: None)
    hub.notify()
    await hass.async_block_till_done()
    assert e32.logins == logins and link.login_rejected


@pytest.mark.asyncio
async def test_the_rooms_editor_explains_a_changed_password(hass, manager):
    e32 = LoginFake(password="changed-on-the-e32")
    parent, _ = product(hass, e32)
    flow = await manager.async_init(parent.entry_id)
    result = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_rooms"})
    assert result["type"] == "abort" and result["reason"] == "e32_password_changed"


@pytest.mark.asyncio
async def test_reauth_checks_the_new_password_and_saves_it(hass, manager, monkeypatch):
    from unittest.mock import Mock
    e32 = LoginFake(password="new-password", default=False)
    parent, _ = product(hass, e32)
    monkeypatch.setattr(OpenThermostatConfigFlow, "_reauth_client",
                        staticmethod(lambda address: e32.client(address)))
    reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reload)
    issues = ir.async_get(hass)
    issue_id = f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}"
    ir.async_create_issue(hass, "open_thermostat", issue_id, is_fixable=False,
                          severity=ir.IssueSeverity.WARNING, translation_key=DEFAULT_PASSWORD_ISSUE)
    flow = await hass.config_entries.flow.async_init(
        "open_thermostat", context={"source": "reauth", "entry_id": parent.entry_id}, data=dict(parent.data))
    assert flow["step_id"] == "reauth_confirm"
    assert flow["description_placeholders"]["address"] == "http://192.168.1.206"
    assert "secret" not in str(flow)  # the old password is never shown or suggested
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "wrong"})
    assert flow["type"] == "form" and flow["errors"] == {"password": "reauth_password_wrong"}
    assert parent.data[CONTROLLER_PASSWORD] == "secret"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "new-password"})
    assert result["type"] == "abort" and result["reason"] == "reauth_successful", result
    assert parent.data[CONTROLLER_PASSWORD] == "new-password"
    reload.assert_called_once_with(parent.entry_id)
    assert issues.async_get_issue("open_thermostat", issue_id) is None  # the E32 said: no default password


@pytest.mark.asyncio
async def test_a_new_password_is_used_in_place_without_a_reload_or_plan_review(hass, manager, monkeypatch):
    from unittest.mock import AsyncMock
    from homeassistant.config_entries import ConfigEntryState
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.e32_access import save_password
    e32 = LoginFake(password="new-password")
    parent, hub = product(hass, e32)
    parent._async_set_state(hass, ConfigEntryState.LOADED, None)
    link = hub.plan
    link.login_rejected = True  # the old password was refused
    reload = AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    save_password(hass, parent, "new-password")
    await integration._async_options_updated(hass, parent)
    await hass.async_block_till_done()
    assert parent.data[CONTROLLER_PASSWORD] == "new-password"
    assert reload.await_count == 0 and not link.login_rejected
    assert link._password == "new-password" and link.plan == e32.plan  # read again with the new password
    # Any other data change still reloads as before.
    hass.config_entries.async_update_entry(parent, data={**parent.data, "controller_id": "other"})
    await integration._async_options_updated(hass, parent)
    assert reload.await_count == 1


@pytest.mark.asyncio
async def test_an_unreachable_e32_during_reauth_keeps_the_form(hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())

    class Unreachable:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def async_login(self, password):
            raise ControllerLinkError("controller_unreachable")
    monkeypatch.setattr(OpenThermostatConfigFlow, "_reauth_client", staticmethod(lambda address: Unreachable()))
    flow = await hass.config_entries.flow.async_init(
        "open_thermostat", context={"source": "reauth", "entry_id": parent.entry_id}, data=dict(parent.data))
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"password": "x"})
    assert flow["errors"] == {"base": "reauth_unreachable"} and parent.data[CONTROLLER_PASSWORD] == "secret"


@pytest.mark.asyncio
async def test_the_default_password_is_a_repairs_issue_until_it_is_changed(hass, manager):
    e32 = LoginFake(default=True)
    parent, hub = product(hass, e32)
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub, entry=parent)
    link._client = lambda: e32.client("http://192.168.1.206")
    issue_id = f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}"
    await link.async_read()
    issue = ir.async_get(hass).async_get_issue("open_thermostat", issue_id)
    assert issue is not None and issue.translation_key == DEFAULT_PASSWORD_ISSUE
    assert issue.severity == ir.IssueSeverity.WARNING and not issue.is_fixable
    # Firmware that does not report the field leaves the issue alone; false removes it.
    e32.default = None
    await link.async_read()
    assert ir.async_get(hass).async_get_issue("open_thermostat", issue_id) is not None
    e32.default = False
    await link.async_read()
    assert ir.async_get(hass).async_get_issue("open_thermostat", issue_id) is None


@pytest.mark.asyncio
async def test_the_client_reads_default_password_and_tells_a_refused_login_apart():
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from custom_components.open_thermostat.controller_link import ControllerClient
    answer = {"default_password": True}

    async def login(request):
        form = await request.post()
        if form["password"] != "admin":
            return web.json_response({"error": "invalid_credentials"}, status=401)
        return web.json_response({"ok": True})

    async def session(request):
        return web.json_response({"authenticated": True, "csrf": "c" * 64, **answer})

    async def logout(request):
        return web.json_response({})
    app = web.Application()
    app.router.add_post("/auth/login", login)
    app.router.add_get("/auth/session", session)
    app.router.add_post("/auth/logout", logout)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        for value, expected in ((True, True), (False, False), ("yes", None)):
            answer["default_password"] = value
            client = ControllerClient("http://192.168.1.206")
            async with client:
                client.address = f"http://127.0.0.1:{server.port}"
                await client.async_login("admin")
                assert client.default_password is expected
        answer.clear()
        client = ControllerClient("http://192.168.1.206")
        async with client:
            client.address = f"http://127.0.0.1:{server.port}"
            await client.async_login("admin")
            assert client.default_password is None  # older firmware: unknown
        client = ControllerClient("http://192.168.1.206")
        async with client:
            client.address = f"http://127.0.0.1:{server.port}"
            with pytest.raises(ControllerLoginRejected) as error:
                await client.async_login("old")
            assert str(error.value) == "controller_auth_failed"  # the same public code as before
    finally:
        await server.close()


def test_password_texts_are_plain_and_in_both_languages():
    for name, document in documents().items():
        config = document["config"]
        assert {"password"} == set(config["step"]["reauth_confirm"]["data"]), name
        assert "{address}" in config["step"]["reauth_confirm"]["description"]
        for key in ("reauth_password_invalid", "reauth_password_wrong", "reauth_unreachable"):
            assert config["error"][key], (name, key)
        assert config["abort"]["reauth_successful"] and config["abort"]["reauth_no_e32"]
        issue = document["issues"][DEFAULT_PASSWORD_ISSUE]
        assert "admin/admin" in issue["description"] and "{name}" in issue["description"]
        assert document["exceptions"]["room_plan_password"]["message"]
        assert document["options"]["abort"]["e32_password_changed"]
        # The connect form no longer refers to a password "you set on the E32 web page".
        assert "you set" not in document["options"]["step"]["controller_connection"]["data_description"]["password"]
    nl = documents()["translations/nl.json"]
    assert "Systeem" in nl["issues"][DEFAULT_PASSWORD_ISSUE]["description"]
    assert "System" in documents()["strings.json"]["issues"][DEFAULT_PASSWORD_ISSUE]["description"]


# -- F11: the room editor in a °F Home Assistant ---------------------------------------------------


def test_temperatures_convert_between_fahrenheit_and_the_plans_celsius():
    assert shown_c(2000, "°F") == 68.0 and shown_c(2050, "°F") == 68.9 and shown_c(500, "°F") == 41.0
    assert shown_c(3000, "°F") == 86.0 and shown_c(2050) == 20.5
    from custom_components.open_thermostat.e32_room_flow import centi
    assert centi(68, "°F") == 2000 and centi("68,9", "°F") == 2050 and centi(41, "°F") == 500
    # Every value shown in °F reads back to the same tenth of a °C.
    for tenth in range(50, 301):
        assert centi(shown_c(tenth * 10, "°F"), "°F") == tenth * 10
    assert (flow_shown(45, "°F"), flow_shown(80, "°F"), flow_shown(21, "°F")) == (113, 176, 70)
    assert all(flow_celsius(flow_shown(c, "°F"), "°F") == c for c in range(20, 81))
    assert flow_celsius(45.5) is None and flow_celsius(45.0) == 45


def test_the_week_program_reads_and_writes_fahrenheit():
    week = [[[390, 2050], [1350, 1800]]] * 5 + [[[480, 2050], [1380, 1800]]] * 2
    text = format_program(week, "en", "°F")
    assert text == "mon-fri: 06:30 68.9; 22:30 64.4\nsat-sun: 08:00 68.9; 23:00 64.4"
    assert parse_program(text, 500, 3000, "°F") == week
    with pytest.raises(FlowError) as error:
        parse_program("07:00 90", 500, 3000, "°F")
    assert error.value.key == "e32_program_outside_limits"


@pytest.mark.asyncio
async def test_a_room_edited_in_fahrenheit_keeps_its_exact_celsius_values(hass, manager):
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
    plan = deepcopy(PLAN)
    plan["rooms"][0].update(fallback_centi_c=2055, schedule=[[[420, 2055]]] * 7)
    e32 = FakeE32(plan)
    parent, _ = product(hass, e32)
    hass.config.units = US_CUSTOMARY_SYSTEM
    form = await room_form(manager, parent, "woonkamer")
    values = shown(form)
    assert values["fallback_temperature"] == 69.0 and values["program"] == "07:00 69"
    assert values["limits"] == {"minimum_temperature": 50.0, "maximum_temperature": 75.2}
    posts = len(e32.posts)
    result = await manager.async_configure(form["flow_id"], values)
    assert result["reason"] == "e32_room_unchanged" and len(e32.posts) == posts
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "name": "Huiskamer"})
    assert result["step_id"] == "e32_rooms_saved", result
    room = e32.plan["rooms"][0]
    assert room["name"] == "Huiskamer"
    # Only the name changed: no °F rounding of the stored values.
    assert (room["fallback_centi_c"], room["schedule"], room["maximum_centi_c"]) == (2055, [[[420, 2055]]] * 7, 2400)
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "fallback_temperature": 70})
    assert e32.plan["rooms"][0]["fallback_centi_c"] == 2110  # 70 °F = 21.1 °C


# -- F20: the program error names the line ------------------------------------------------------


@pytest.mark.asyncio
async def test_a_program_error_names_the_line_that_could_not_be_read(hass, manager):
    parent, _ = product(hass, FakeE32())
    form = await room_form(manager, parent)
    result = await manager.async_configure(form["flow_id"], {
        **NEW_ROOM, "program": "mon-fri: 06:30 20.5; 22:30 18\nsat: 8 uur 20"})
    assert result["errors"] == {"program": "e32_program_invalid"}
    assert result["description_placeholders"]["line"] == "2"
    assert result["description_placeholders"]["text"] == "sat: 8 uur 20"
    for document in documents().values():
        errors = document["options"]["error"]
        assert "{line}" in errors["e32_program_invalid"] and "{text}" in errors["e32_program_invalid"]
        assert "{line}" in errors["e32_program_too_many"] and "{line}" in errors["e32_program_outside_limits"]
    # Without an error the placeholders are still there (no raw {line} in other messages).
    form = await room_form(manager, parent)
    assert form["description_placeholders"]["line"] == "" and form["description_placeholders"]["range"]


# -- F05 + boiler maximum: flow limits -------------------------------------------------------------


async def flow_form(manager, parent):
    flow = await rooms_menu(manager, parent)
    return await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_flow_limits"})


@pytest.mark.asyncio
async def test_a_radiator_home_can_ask_up_to_80_degrees(hass, manager):
    plan = deepcopy(PLAN)
    for room in plan["rooms"]:
        room["emitter"] = "radiator"
    e32 = FakeE32(plan)
    parent, _ = product(hass, e32)
    form = await flow_form(manager, parent)
    maximum = next(v for k, v in form["data_schema"].schema.items() if str(k) == "maximum_flow_temperature")
    assert (maximum.config["min"], maximum.config["max"]) == (21, 80)
    assert form["description_placeholders"]["maximum_range"] == "21–80 °C"
    assert form["description_placeholders"]["boiler"] == ""  # the boiler reports no maximum
    result = await manager.async_configure(form["flow_id"], {"minimum_flow_temperature": 30,
                                                             "maximum_flow_temperature": 75})
    assert result["reason"] == "e32_flow_limits_saved", result
    assert e32.plan["maximum_flow_c"] == 75


@pytest.mark.asyncio
async def test_floor_heating_above_50_warns_once_and_then_saves(hass, manager):
    e32 = FakeE32()  # woonkamer is floor heating
    parent, _ = product(hass, e32)
    form = await flow_form(manager, parent)
    posts = len(e32.posts)
    values = {"minimum_flow_temperature": 30, "maximum_flow_temperature": 65}
    form = await manager.async_configure(form["flow_id"], values)
    assert form["type"] == "form" and form["errors"] == {
        "maximum_flow_temperature": "e32_flow_limits_floor_warning"}
    assert form["description_placeholders"]["floor_maximum"] == "50 °C" and len(e32.posts) == posts
    result = await manager.async_configure(form["flow_id"], values)  # saved on the second press
    assert result["reason"] == "e32_flow_limits_saved" and e32.plan["maximum_flow_c"] == 65


@pytest.mark.asyncio
async def test_the_boiler_maximum_is_shown_and_a_higher_limit_warns(hass, manager, monkeypatch):
    plan = deepcopy(PLAN)
    for room in plan["rooms"]:
        room["emitter"] = "radiator"
    e32 = FakeE32(plan)
    parent, _ = product(hass, e32)
    hass.data["open_thermostat"][parent.entry_id]["v1_connection"] = SimpleNamespace(client=object())
    monkeypatch.setattr(heating_advice, "boiler_maximum", lambda client: 70)
    form = await flow_form(manager, parent)
    assert form["description_placeholders"]["boiler"] == (
        "Your boiler allows at most 70 °C; the E32 never asks for more. A lower limit here is useful for floor "
        "heating.")
    values = {"minimum_flow_temperature": 30, "maximum_flow_temperature": 75}
    form = await manager.async_configure(form["flow_id"], values)
    assert form["errors"] == {"base": "e32_flow_limits_above_boiler"}
    result = await manager.async_configure(form["flow_id"], values)
    assert result["reason"] == "e32_flow_limits_saved" and e32.plan["maximum_flow_c"] == 75
    hass.config.language = "nl"
    form = await flow_form(manager, parent)
    assert form["description_placeholders"]["boiler"].startswith("Je ketel staat hoogstens 70 °C toe")


@pytest.mark.asyncio
async def test_older_firmware_refusing_more_than_60_gets_a_clear_message(hass, manager):
    plan = deepcopy(PLAN)
    for room in plan["rooms"]:
        room["emitter"] = "radiator"
    e32 = FakeE32(plan)
    parent, _ = product(hass, e32)
    form = await flow_form(manager, parent)
    e32.fail = HeatingPlanRejected(400, "invalid_flow_limits")
    form = await manager.async_configure(form["flow_id"], {"minimum_flow_temperature": 30,
                                                           "maximum_flow_temperature": 70})
    assert form["type"] == "form" and form["errors"] == {"base": "e32_rejected_flow_limits"}


@pytest.mark.asyncio
async def test_flow_limits_in_fahrenheit(hass, manager):
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
    plan = deepcopy(PLAN)
    for room in plan["rooms"]:
        room["emitter"] = "radiator"
    e32 = FakeE32(plan)
    parent, _ = product(hass, e32)
    hass.config.units = US_CUSTOMARY_SYSTEM
    form = await flow_form(manager, parent)
    assert shown(form) == {"minimum_flow_temperature": 86, "maximum_flow_temperature": 140}
    assert form["description_placeholders"]["maximum_range"] == "70–176 °F"
    posts = len(e32.posts)
    result = await manager.async_configure(form["flow_id"], shown(form))
    assert result["reason"] == "e32_room_unchanged" and len(e32.posts) == posts
    form = await flow_form(manager, parent)
    result = await manager.async_configure(form["flow_id"], {"minimum_flow_temperature": 77,
                                                             "maximum_flow_temperature": 158})
    assert result["reason"] == "e32_flow_limits_saved"
    assert (e32.plan["minimum_flow_c"], e32.plan["maximum_flow_c"]) == (25, 70)
    assert result["description_placeholders"] == {"minimum": "77", "maximum": "158", "unit": "°F"}


# -- F06 (HA side): the E32's refusals as plain messages ------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("error,key", [("invalid_sources", "e32_rejected_sources"),
                                       ("duplicate_room", "e32_rejected_duplicate_room"),
                                       ("duplicate_source", "e32_rejected_duplicate_source"),
                                       ("invalid_setpoint_entity", "e32_rejected_setpoint"),
                                       ("invalid_schedule", "e32_rejected_schedule")])
async def test_e32_refusals_are_plain_messages(hass, manager, error, key):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    e32.fail = HeatingPlanRejected(400, error)
    result = await manager.async_configure(form["flow_id"], NEW_ROOM)
    assert result["errors"] == {"base": key}
    for document in documents().values():
        assert "{" not in document["options"]["error"][key]


# -- F29: the main menu ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_main_menu_starts_with_the_rooms_and_keeps_status_under_advanced(hass, manager):
    parent, _ = product(hass, FakeE32())
    flow = await manager.async_init(parent.entry_id)
    assert flow["menu_options"] == ["e32_rooms", "controller_connection", "energy", "installation",
                                    "advanced_settings"]
    advanced = await manager.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    assert advanced["menu_options"][0] == "configuration_status"


# -- Language: EN and NL say the same things --------------------------------------------------


def _leaves(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaves(value, path + (key,))
    else:
        yield path, node


def test_dutch_has_every_english_text_with_the_same_placeholders():
    docs = documents()
    en, nl = docs["strings.json"], docs["translations/nl.json"]
    assert docs["translations/en.json"] == en
    nl_leaves = dict(_leaves(nl))
    problems = []
    for path, text in _leaves(en):
        if path not in nl_leaves:
            problems.append(("missing", path))
        elif isinstance(text, str) and set(re.findall(r"{(\w+)}", text)) != set(
                re.findall(r"{(\w+)}", nl_leaves[path])):
            problems.append(("placeholders", path))
    assert problems == []


def test_no_formal_or_english_leftovers_in_dutch():
    text = (COMPONENT / "translations/nl.json").read_text(encoding="utf-8")
    assert "voordat u " not in text and "(alleen shadow)" not in text
