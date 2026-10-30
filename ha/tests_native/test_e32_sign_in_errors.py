"""E32 sign-in refusals (429) get their own clear message, and every sign-in ends with a logout.

The E32 keeps at most 4 web sessions: POST /auth/login answers 429
{"error":"session_capacity"} while they are all in use, and 429
{"error":"try_again_later"} (Retry-After 30) after failed sign-ins
(src/REST.h login()). Home Assistant must name both, and must never leave its
own sessions behind (each one blocks a sign-in for days).
"""
import json

import pytest

from custom_components.open_thermostat import controller_link as link
from custom_components.open_thermostat.room_plan import plan_error
from test_controller_link import BASE, CSRF, Response, login_responses, setup


class Body:
    def __init__(self, raw):
        self.raw = raw

    async def read(self, size):
        return self.raw[:size]

    async def iter_chunked(self, size):
        yield self.raw


class Refusal(Response):
    def __init__(self, error, status=429):
        super().__init__({"error": error}, status=status)
        self.content = Body(json.dumps({"error": error}).encode())


@pytest.mark.asyncio
@pytest.mark.parametrize("error,code", [("session_capacity", "controller_session_capacity"),
                                        ("try_again_later", "controller_try_again_later"),
                                        ("something_new", "controller_try_again_later")])
async def test_a_full_or_rate_limited_e32_names_the_reason(monkeypatch, error, code):
    session, _ = setup(monkeypatch, Refusal(error))
    async with link.ControllerClient(BASE) as client:
        with pytest.raises(link.ControllerLinkError) as caught:
            await client.async_login("password")
    assert str(caught.value) == code
    assert not isinstance(caught.value, link.ControllerLoginRejected)  # never a re-authentication
    # Refused before a session existed: nothing to log out.
    assert [call[1] for call in session.calls] == [BASE + "/auth/login"] and session.closed


@pytest.mark.asyncio
async def test_a_sign_in_whose_csrf_read_failed_still_logs_out(monkeypatch):
    session, _ = setup(monkeypatch, Response({"authenticated": True}), Response({"authenticated": False}),
                       Response({"authenticated": True, "csrf": CSRF}), Response({"authenticated": False}))
    async with link.ControllerClient(BASE) as client:
        with pytest.raises(link.ControllerLinkError, match="controller_auth_failed"):
            await client.async_login("password")
    paths = [(call[0], call[1].removeprefix(BASE)) for call in session.calls]
    assert paths == [("POST", "/auth/login"), ("GET", "/auth/session"), ("GET", "/auth/session"),
                     ("POST", "/auth/logout")]
    assert session.calls[-1][2]["headers"]["X-OpenThermostat-CSRF"] == CSRF
    assert client.logout_confirmed and session.closed


@pytest.mark.asyncio
async def test_every_normal_sign_in_logs_out_also_after_an_error(monkeypatch):
    session, _ = setup(monkeypatch, *login_responses(), Refusal("busy", status=500), Response({"authenticated": False}))
    with pytest.raises(link.ControllerLinkError, match="controller_response_invalid"):
        async with link.ControllerClient(BASE) as client:
            await client.async_login("password")
            await client.async_read("/status")
    assert session.calls[-1][1] == BASE + "/auth/logout" and client.logout_confirmed


def test_the_room_plan_and_reauthentication_explain_the_refusal():
    for code, key in (("controller_session_capacity", "e32_session_capacity"),
                      ("controller_try_again_later", "e32_try_again_later")):
        assert plan_error(link.ControllerLinkError(code)).translation_key == key


def test_every_new_code_has_an_english_dutch_and_polish_text():
    from test_polish_translation import COMPONENT
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        strings = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        options = strings["options"]["error"]
        for key in ("controller_session_capacity", "controller_try_again_later",
                    "controller_room_plan_update_required"):
            assert options[key].strip(), (name, key)
        for issue in ("legacy_rooms", "legacy_rooms_finish"):
            errors = strings["issues"][issue]["fix_flow"]["error"]
            assert {"e32_update_required", "e32_session_capacity", "e32_try_again_later"} <= set(errors)
        assert {"reauth_session_capacity", "reauth_try_again_later"} <= set(strings["config"]["error"])
        assert {"e32_session_capacity", "e32_try_again_later"} <= set(strings["exceptions"])
    dutch = json.loads((COMPONENT / "translations/nl.json").read_text(encoding="utf-8"))
    assert "beta.19" in dutch["options"]["error"]["controller_room_plan_update_required"]
    assert "30 seconden" in dutch["options"]["error"]["controller_try_again_later"]


@pytest.mark.asyncio
async def test_reauthentication_shows_the_sign_in_refusal(hass, monkeypatch):
    from custom_components.open_thermostat import config_flow
    flow_class = config_flow.OpenThermostatConfigFlow

    class Full:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def async_login(self, password):
            raise link.ControllerLinkError("controller_session_capacity")
    monkeypatch.setattr(flow_class, "_reauth_client", staticmethod(lambda address: Full()))
    from test_e32_room_plan_link import product
    from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS
    parent = product(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, CONTROLLER_ADDRESS: BASE})
    flow = flow_class()
    flow.hass = hass
    flow.context = {"source": "reauth", "entry_id": parent.entry_id}
    flow._get_reauth_entry = lambda: parent
    result = await flow.async_step_reauth_confirm({"password": "new-password"})
    assert result["errors"] == {"base": "reauth_session_capacity"}
