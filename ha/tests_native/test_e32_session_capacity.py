"""Writes from Home Assistant wait for a free E32 web session (owner report, 1 Nov 2026).

The E32 keeps 4 web sessions. While they are all in active use (browser tabs,
pollers), POST /auth/login answers 429 {"error":"session_capacity"}; a full
table gives its least recently used session away only once that one was idle
2 minutes (WebAuthSession::evictIdleMs). A target set in Home Assistant then
used to fail at once. Now every write signs in again after 5, 10, 20, 30, 30,
30 and 30 s (past those 2 minutes), the newest target of a room wins, the
thermostat shows the new target meanwhile, and a write that still finds no
session raises a clear message and a Repairs item. Reads never wait.
"""
import asyncio
import json
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import controller_link as link
from custom_components.open_thermostat.const import DOMAIN
from test_controller_link import BASE, Response, login_responses, setup
from test_e32_comfort import FakeE32, climate, room_state, status
from test_e32_sign_in_errors import Refusal

FAST = (0.02,) * 7  # the same seven attempts, in milliseconds instead of 155 s


class FullE32(FakeE32):
    """FakeE32 whose sign-in answers session_capacity while `full` other sessions are active."""

    def __init__(self, full=0):
        super().__init__()
        self.full, self.logins = full, 0

    def client(self):
        inner, e32 = super().client(), self

        class Client(type(inner)):
            async def async_login(self, password):
                e32.logins += 1
                if e32.full is True or (e32.full and e32.logins <= e32.full):
                    raise link.ControllerLinkError("controller_session_capacity")
                assert password == "secret"
        return Client()


class Attempts:
    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0

    async def async_login(self, password):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)


def capacity(count):
    return [link.ControllerLinkError("controller_session_capacity")] * count


@pytest.mark.asyncio
async def test_the_waits_pass_the_two_minute_idle_eviction():
    assert link.SESSION_WAITS == (5, 10, 20, 30, 30, 30, 30)
    assert 120 < sum(link.SESSION_WAITS) <= 160
    waited = []

    async def pause(seconds):
        waited.append(seconds)
    client = Attempts(*capacity(3))
    await link.async_login_waiting(client, "pw", pause=pause)
    assert waited == [5, 10, 20] and client.calls == 4  # signed in on the fourth attempt

    waited.clear()
    client = Attempts(*capacity(8))
    with pytest.raises(link.ControllerLinkError) as caught:
        await link.async_login_waiting(client, "pw", pause=pause)
    assert str(caught.value) == "controller_no_free_session"
    assert waited == list(link.SESSION_WAITS) and client.calls == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [link.ControllerLinkError("controller_try_again_later"),
                                   link.ControllerLoginRejected(), link.ControllerLinkError("controller_unreachable")])
async def test_other_sign_in_refusals_never_wait(error):
    """A wrong password or the E32's login limit: once, never a loop of sign-ins."""
    waited = []

    async def pause(seconds):
        waited.append(seconds)
    client = Attempts(error)
    with pytest.raises(type(error)) as caught:
        await link.async_login_waiting(client, "pw", pause=pause)
    assert caught.value is error and waited == [] and client.calls == 1


@pytest.mark.asyncio
async def test_one_client_signs_in_again_after_a_429_and_still_logs_out(monkeypatch):
    session, _ = setup(monkeypatch, Refusal("session_capacity"), Refusal("session_capacity"), *login_responses(),
                       Response({"authenticated": False}))
    waited = []

    async def pause(seconds):
        waited.append(seconds)
    async with link.ControllerClient(BASE) as client:
        await link.async_login_waiting(client, "password", pause=pause)
    paths = [(call[0], call[1].removeprefix(BASE)) for call in session.calls]
    assert paths == [("POST", "/auth/login")] * 3 + [("GET", "/auth/session"), ("POST", "/auth/logout")]
    assert waited == [5, 10] and client.logout_confirmed


@pytest.mark.asyncio
async def test_a_new_target_waits_for_a_free_session_without_blocking_home_assistant(hass):
    e32 = FullE32()
    entity, hub, plan = await climate(hass, e32, room_state("living"))
    plan.session_waits = (0.05,) * 7
    e32.full, e32.logins = True, 0
    write = asyncio.ensure_future(entity.async_set_temperature(temperature=22))
    ticks = 0
    while e32.logins < 3:
        await asyncio.sleep(0.005)  # the event loop keeps running other work meanwhile
        ticks += 1
    assert not write.done() and ticks > 3
    assert entity.target_temperature == 22  # the new target shows, not the E32's 20.5
    e32.full = 0  # a session became free (another one was idle 2 minutes)
    await write
    assert e32.commands == [{"room": "living", "override": "next", "temperature": 22.0}]
    assert entity.target_temperature == 22  # until the telemetry reports it
    hub.update(status(room_state("living", setpoint=22.0)))
    assert entity.target_temperature == 22 and entity._pending is None
    plan.stop()


@pytest.mark.asyncio
async def test_the_newest_target_wins_and_only_one_write_goes_out(hass):
    e32 = FullE32()
    entity, hub, plan = await climate(hass, e32, room_state("living"))
    plan.session_waits = (0.05,) * 7
    e32.full, e32.logins = True, 0
    first = asyncio.ensure_future(entity.async_set_temperature(temperature=21))
    while e32.logins < 2:
        await asyncio.sleep(0.005)
    second = asyncio.ensure_future(entity.async_set_temperature(temperature=22.5))
    third = asyncio.ensure_future(entity.async_set_temperature(temperature=23))
    await asyncio.sleep(0.01)
    assert first.done() and first.exception() is None  # superseded: nothing sent, no error
    assert entity.target_temperature == 23
    e32.full = 0
    await asyncio.gather(second, third)
    assert e32.commands == [{"room": "living", "override": "next", "temperature": 23.0}]
    plan.stop()


@pytest.mark.asyncio
async def test_a_room_with_only_a_fixed_target_coalesces_its_plan_writes_too(hass):
    e32 = FullE32()
    entity, hub, plan = await climate(hass, e32, room_state("study"))
    plan.session_waits = (0.05,) * 7
    e32.full, e32.logins = True, 0
    first = asyncio.ensure_future(entity.async_set_temperature(temperature=18))
    while e32.logins < 2:
        await asyncio.sleep(0.005)
    second = asyncio.ensure_future(entity.async_set_temperature(temperature=19))
    e32.full = 0
    await asyncio.gather(first, second)
    assert len(e32.plan_posts) == 1 and e32.plan["rooms"][1]["fallback_centi_c"] == 1900
    plan.stop()


@pytest.mark.asyncio
async def test_still_full_after_the_waits_a_clear_message_and_a_repairs_item(hass):
    e32 = FullE32()
    entity, hub, plan = await climate(hass, e32, room_state("living"))
    plan.session_waits = FAST
    plan.entry = SimpleNamespace(entry_id="e1", title="Home")
    e32.full, e32.logins = True, 0
    with pytest.raises(HomeAssistantError) as caught:
        await entity.async_set_temperature(temperature=22)
    assert caught.value.translation_key == "e32_no_free_session"
    assert e32.logins == 8 and e32.commands == []
    assert entity.target_temperature == 20.5  # the E32's own target again: nothing silently "applied"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "e32_no_free_session_e1")
    assert issue is not None and issue.translation_key == "e32_no_free_session"
    assert issue.translation_placeholders == {"name": "Home"}
    # The next change that reaches the E32 removes the item.
    e32.full = 0
    await entity.async_set_temperature(temperature=22)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "e32_no_free_session_e1") is None
    plan.stop()


@pytest.mark.asyncio
async def test_reads_never_wait_for_a_session(hass):
    """A read holds the lock the user's writes need: it fails at once (the telemetry reads again later)."""
    e32 = FullE32()
    entity, hub, plan = await climate(hass, e32, room_state("living"))
    plan.session_waits = (5,) * 7
    e32.full, e32.logins = True, 0
    with pytest.raises(HomeAssistantError) as caught:
        await asyncio.wait_for(plan.async_read(), 1)
    assert caught.value.translation_key == "e32_session_capacity" and e32.logins == 1
    plan.stop()


@pytest.mark.asyncio
async def test_other_writes_wait_too(hass):
    """The house mode, flow options, valves and the handover use the same waiting sign-in."""
    from custom_components.open_thermostat.e32_flow import FlowSettingsLink
    from custom_components.open_thermostat.e32_reconfirm import async_handover
    seen = []

    class Plan:
        _lock = asyncio.Lock()

        def claim(self, key=None):
            return lambda: True

        def _client(self):
            return Client()

        async def _login(self, client, wanted=None):
            seen.append(wanted is not None)

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def async_flow_settings(self, change):
            return {}

        async def async_handover(self, disconnected):
            return {}
    flow = FlowSettingsLink(hass, SimpleNamespace(), Plan())
    await flow._call()
    await flow._call({"weather_curve": True})
    await async_handover(Plan(), True)
    assert seen == [False, True, True]


def test_the_message_is_translated():
    from test_polish_translation import COMPONENT
    texts = {}
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        strings = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        message = strings["exceptions"]["e32_no_free_session"]["message"]
        issue = strings["issues"]["e32_no_free_session"]
        assert message.strip() and issue["title"].strip() and "{name}" in issue["description"]
        texts[name] = message
    assert texts["strings.json"] == texts["translations/en.json"] == (
        "The E32 has no free web session: close E32 pages you do not use, or wait two minutes.")
    assert "twee minuten" in texts["translations/nl.json"] and "dwie minuty" in texts["translations/pl.json"]
