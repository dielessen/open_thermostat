"""rc.2: while the E32 has its factory password it refuses every change; Repairs chooses a new one.

The E32 answers 403 {"error":"password_change_required"} to every state-changing
request (reads keep working). Home Assistant turns that into a clear error and a
fixable Repairs issue, "Choose a new E32 password", that changes it through
POST /auth/password and stores it in the entry, in one step.
"""
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import controller_link
from custom_components.open_thermostat.controller_link import (
    ControllerClient, ControllerLinkError, ControllerLoginRejected, ControllerPasswordChangeRequired,
    PasswordChangeRejected)
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_PASSWORD
from custom_components.open_thermostat.e32_access import DEFAULT_PASSWORD_ISSUE, ChooseE32PasswordRepairFlow
from custom_components.open_thermostat.repairs import async_create_fix_flow
from custom_components.open_thermostat.room_plan import RoomPlanLink
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32

FACTORY = {"error": "password_change_required"}


class FactoryE32(FakeE32):
    """An E32 on rc.2 that still has its factory password (stored in HA as "secret" here)."""

    def __init__(self):
        super().__init__()
        self.password, self.factory, self.changes = "secret", True, []

    def client(self, address):
        inner, e32 = super().client(address), self

        async def login(password):
            e32.logins += 1
            if password != e32.password:
                raise ControllerLoginRejected()
            inner.default_password = e32.factory

        async def save(plan):
            if e32.factory:
                raise ControllerPasswordChangeRequired()
            return await type(inner).async_save_heating_plan(inner, plan)

        async def change(current, new):
            e32.changes.append((current, new))
            if current != e32.password:
                raise PasswordChangeRejected(403, "password_wrong")
            if len(new) < 8:
                raise PasswordChangeRejected(400, "password_too_short")
            e32.password, e32.factory = new, False

        inner.async_login, inner.async_save_heating_plan, inner.async_change_password = login, save, change
        inner.default_password = None
        return inner


@pytest.mark.asyncio
async def test_the_client_tells_password_change_required_apart_and_changes_the_password():
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    seen = []

    async def login(request):
        return web.json_response({"authenticated": True, "default_password": True})

    async def session(request):
        return web.json_response({"authenticated": True, "csrf": "c" * 64, "default_password": True})

    async def logout(request):
        return web.json_response({})

    async def heating(request):
        return web.json_response(FACTORY, status=403)

    async def flow(request):
        return web.json_response({"error": "csrf_required"}, status=403)

    async def password(request):
        body = await request.json()
        seen.append((request.headers.get("X-OpenThermostat-CSRF"), body))
        if len(body["new"]) < 8:
            return web.json_response({"error": "password_too_short"}, status=400)
        if body["current"] != "admin":
            return web.json_response({"error": "password_wrong"}, status=403)
        return web.Response(status=204)
    app = web.Application()
    app.router.add_post("/auth/login", login)
    app.router.add_get("/auth/session", session)
    app.router.add_post("/auth/logout", logout)
    app.router.add_post("/config/heating", heating)
    app.router.add_post("/config/heating/flow", flow)
    app.router.add_post("/auth/password", password)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        client = ControllerClient("http://192.168.1.206")
        async with client:
            client.address = f"http://127.0.0.1:{server.port}"
            await client.async_login("admin")
            assert client.default_password is True
            with pytest.raises(ControllerPasswordChangeRequired) as refused:
                await client.async_save_heating_plan({"schema": 1})
            assert str(refused.value) == "controller_password_change_required"
            # Another 403 (a missing CSRF proof) stays the sign-in error it was.
            with pytest.raises(ControllerLinkError) as other:
                await client.async_flow_settings({"curve": True})
            assert str(other.value) == "controller_auth_failed"
            with pytest.raises(PasswordChangeRejected) as short:
                await client.async_change_password("admin", "Qz7!")
            assert short.value.error == "password_too_short" and "Qz7!" not in repr(short.value)
            with pytest.raises(PasswordChangeRejected) as wrong:
                await client.async_change_password("nope", "correct horse 42")
            assert wrong.value.error == "password_wrong"
            await client.async_change_password("admin", "correct horse 42")
        assert seen[-1] == ("c" * 64, {"current": "admin", "new": "correct horse 42"})
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_a_refused_write_is_a_clear_error_and_a_fixable_repairs_issue(hass, manager):
    e32 = FactoryE32()
    parent, hub = product(hass, e32)
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub, entry=parent)
    link._client = lambda: e32.client("http://192.168.1.206")
    hub.plan = link
    # Reading keeps working with the factory password (the heating runs on the stored plan).
    plan = await link.async_read()
    assert plan["revision"] == e32.plan["revision"]
    with pytest.raises(HomeAssistantError) as error:
        await link.async_change_room("woonkamer", lambda room: room.update(name="Zitkamer"))
    assert error.value.translation_key == "e32_password_change_required"
    assert e32.plan["rooms"][0].get("name") != "Zitkamer" and not link.login_rejected
    issue = ir.async_get(hass).async_get_issue("open_thermostat", f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}")
    assert issue is not None and issue.is_fixable and issue.data == {"entry_id": parent.entry_id}


@pytest.mark.asyncio
async def test_repairs_changes_the_factory_password_in_one_step_and_writes_work_again(hass, manager, monkeypatch):
    e32 = FactoryE32()
    parent, hub = product(hass, e32)
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub, entry=parent)
    link._client = lambda: e32.client("http://192.168.1.206")
    hub.plan = link
    hass.data["open_thermostat"][parent.entry_id]["heating_hub"] = hub
    monkeypatch.setattr(controller_link, "ControllerClient", e32.client)
    reloads = []  # this test entry is not set up: save_password reloads it
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", reloads.append)
    await link.async_read()  # the login reports the factory password: the issue appears
    issue_id = f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}"
    assert ir.async_get(hass).async_get_issue("open_thermostat", issue_id).is_fixable
    flow = await async_create_fix_flow(hass, issue_id, {"entry_id": parent.entry_id})
    assert isinstance(flow, ChooseE32PasswordRepairFlow)
    flow.hass = hass
    form = await flow.async_step_init()
    assert form["type"] == "form" and form["step_id"] == "choose_password"
    assert form["description_placeholders"] == {"name": parent.title}
    # Checked here first, before anything goes to the E32.
    for new, again, field, code in (("short", "short", "new_password", "password_too_short"),
                                    ("x" * 65, "x" * 65, "new_password", "password_too_long"),
                                    ("correct horse 42", "correct horse 43", "repeat_password", "password_mismatch")):
        form = await flow.async_step_choose_password({"new_password": new, "repeat_password": again})
        assert form["errors"] == {field: code}
    assert e32.changes == []
    done = await flow.async_step_choose_password({"new_password": "correct horse 42", "repeat_password": "correct horse 42"})
    assert done["type"] == "create_entry"
    assert e32.changes == [("secret", "correct horse 42")] and e32.password == "correct horse 42"
    await hass.async_block_till_done()
    assert parent.data[CONTROLLER_PASSWORD] == "correct horse 42"
    assert ir.async_get(hass).async_get_issue("open_thermostat", issue_id) is None
    # The next write signs in with the new password and goes through; no re-authentication.
    await link.async_change_room("woonkamer", lambda room: room.update(name="Zitkamer"))
    assert e32.plan["rooms"][0]["name"] == "Zitkamer" and not link.login_rejected
    assert [f for f in hass.config_entries.flow.async_progress_by_handler("open_thermostat")
            if f["context"]["source"] == "reauth"] == []


@pytest.mark.asyncio
async def test_the_repairs_flow_explains_a_stored_password_the_e32_no_longer_takes(hass, manager, monkeypatch):
    e32 = FactoryE32()
    e32.password = "changed-on-the-e32"
    parent, hub = product(hass, e32)
    monkeypatch.setattr(controller_link, "ControllerClient", e32.client)
    flow = await async_create_fix_flow(hass, f"{DEFAULT_PASSWORD_ISSUE}_{parent.entry_id}", {"entry_id": parent.entry_id})
    flow.hass = hass
    form = await flow.async_step_choose_password({"new_password": "correct horse 42", "repeat_password": "correct horse 42"})
    assert form["errors"] == {"base": "e32_password_stored_wrong"} and e32.changes == []
    await hass.async_block_till_done()
    assert [f["context"]["source"] for f in hass.config_entries.flow.async_progress_by_handler("open_thermostat")] == ["reauth"]
    # Already changed on the E32 (and Home Assistant has it): nothing to do.
    e32.password, e32.factory = "secret", False
    gone = await flow.async_step_choose_password({"new_password": "correct horse 42", "repeat_password": "correct horse 42"})
    assert gone["type"] == "abort" and gone["reason"] == "e32_password_already_changed" and e32.changes == []


def test_the_new_password_texts_exist_in_every_language():
    import json
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        doc = json.loads((base / name).read_text(encoding="utf-8"))
        flow = doc["issues"][DEFAULT_PASSWORD_ISSUE]["fix_flow"]
        assert "{name}" in flow["step"]["choose_password"]["description"], name
        assert set(flow["error"]) >= {"password_mismatch", "password_too_short", "password_too_long",
                                      "e32_password_stored_wrong", "e32_unreachable"}, name
        assert doc["exceptions"]["e32_password_change_required"]["message"], name
        assert doc["issues"]["reconfirm_takeover"]["fix_flow"]["error"]["e32_password_change_required"], name
