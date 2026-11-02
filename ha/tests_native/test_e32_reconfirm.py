"""Repairs "Confirm the takeover again" after an E32 firmware update (review S3b); no live device."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import controller_link as link
from custom_components.open_thermostat import e32_reconfirm as module
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.heating_problem import HeatingProblemSensor
from custom_components.open_thermostat.repairs import async_create_fix_flow
from custom_components.open_thermostat.room_plan import RoomPlanLink
from test_controller_link import BASE, CSRF, Response, login_responses, setup as session_setup
from test_e32_comfort import FakeE32

ISSUE = "reconfirm_takeover_e1"
# ActiveHeatGuard::json() after an update: the E32 owned the boiler and waits for the owner.
WAITING = {"state": "awaiting_confirmation", "awaiting_confirmation": True, "reconfirm_required": True,
           "command": {"send": False, "flow_c": 0, "why": "awaiting_confirmation"}, "confirmation": None,
           "warnings": [], "enabled": True, "confirmation_stored": False, "reconfirm_stored": True}
CONFIRMED = {**WAITING, "state": "arming", "awaiting_confirmation": False, "reconfirm_required": False,
             "confirmation": {"age_s": 0}, "confirmation_stored": True, "reconfirm_stored": False}


def status(active):
    return {"schema": 1, "revision": 3, "mode": "active", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
            "ha_entities": [], "rooms": [], "active": deepcopy(active)}


class E32(FakeE32):
    """FakeE32 plus POST /config/heating/handover as REST::heatingHandover answers it."""

    def __init__(self):
        super().__init__()
        self.handovers, self.refusal, self.answer = [], None, CONFIRMED

    def client(self):
        client, e32 = super().client(), self

        async def async_handover(disconnected):
            e32.handovers.append(disconnected)
            if e32.refusal:
                raise e32.refusal
            return deepcopy(e32.answer)
        client.async_handover = async_handover
        return client


async def rig(hass, active=WAITING):
    e32, hub = E32(), HeatingHub("fixture")
    plan_link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    plan_link._client = e32.client
    hub.plan = plan_link
    hub.update(status(active))
    hass.config_entries.async_get_entry = lambda entry_id: SimpleNamespace(entry_id=entry_id)
    hass.data.setdefault("open_thermostat", {})["e1"] = {"heating_hub": hub}
    return e32, hub


def issue(hass):
    return ir.async_get(hass).async_get_issue("open_thermostat", ISSUE)


@pytest.mark.asyncio
async def test_the_issue_follows_the_e32_and_survives_an_outage(hass):
    e32, hub = await rig(hass)
    entry = SimpleNamespace(entry_id="e1", data={})
    sensor = HeatingProblemSensor(entry, hub)  # evaluates on every hub change and every minute
    sensor.hass = hass
    sensor.evaluate()
    raised = issue(hass)
    assert raised is not None and raised.is_fixable and raised.translation_key == "reconfirm_takeover"
    assert raised.severity == ir.IssueSeverity.WARNING and raised.data == {"entry_id": "e1"}
    sensor.evaluate()
    assert issue(hass) is raised  # not raised again each minute
    hub.status = None  # the E32 is silent: keep the issue as it was
    sensor.evaluate()
    assert issue(hass) is not None
    hub.update(status(CONFIRMED))  # answered on the E32 page, or handed back there
    sensor.evaluate()
    assert issue(hass) is None
    for active in ({**WAITING, "reconfirm_required": False}, {}, None):  # older firmware: no such field
        hub.update(status(active) if active is not None else {**status({}), "active": None})
        sensor.evaluate()
        assert issue(hass) is None
    assert e32.handovers == []  # raising the issue never writes to the E32


@pytest.mark.asyncio
async def test_one_repairs_issue_while_the_e32_waits_for_the_takeover_again(hass):
    """After an update the E32 reports awaiting_confirmation and reconfirm_required: only the fixable issue."""
    from custom_components.open_thermostat.heating_problem import AWAITING_CONFIRMATION_SECONDS
    _e32, hub = await rig(hass)
    now = [1000.0]
    hub.clock = lambda: now[0]
    hub.update(status(WAITING))
    sensor = HeatingProblemSensor(SimpleNamespace(entry_id="e1", data={}), hub)
    sensor.hass, sensor.entity_id, sensor.async_write_ha_state = hass, "binary_sensor.heating_problem", lambda: None
    sensor.evaluate()
    now[0] += AWAITING_CONFIRMATION_SECONDS + 60
    hub.update(status(WAITING))
    sensor.evaluate()
    registry = ir.async_get(hass)
    assert sensor.extra_state_attributes["problems"] == ["awaiting_confirmation"]   # the sensor still says so
    assert issue(hass) is not None
    assert registry.async_get_issue("open_thermostat", "heating_problem_awaiting_confirmation_e1") is None
    # A first takeover (no reconfirm): the general issue is the one that asks.
    hub.update(status({**WAITING, "reconfirm_required": False}))
    sensor.evaluate()
    assert issue(hass) is None
    assert registry.async_get_issue("open_thermostat", "heating_problem_awaiting_confirmation_e1") is not None


@pytest.mark.asyncio
async def test_the_fix_confirms_once_and_never_hands_back_or_edits_the_plan(hass):
    e32, hub = await rig(hass)
    module.update_reconfirm_issue(hass, SimpleNamespace(entry_id="e1"), hub)
    flow = await async_create_fix_flow(hass, ISSUE, {"entry_id": "e1"})
    assert isinstance(flow, module.ReconfirmTakeoverRepairFlow)
    flow.hass = hass
    form = await flow.async_step_init()
    assert form["type"] == "form" and form["step_id"] == "reconfirm_takeover"
    assert e32.handovers == []  # nothing is sent before the owner confirms
    done = await flow.async_step_reconfirm_takeover({})
    assert done["type"] == "create_entry"
    assert e32.handovers == [True] and e32.plan_posts == [] and e32.commands == []
    assert issue(hass) is None


@pytest.mark.asyncio
async def test_refusals_keep_the_issue_with_a_clear_reason(hass):
    e32, hub = await rig(hass)
    module.update_reconfirm_issue(hass, SimpleNamespace(entry_id="e1"), hub)
    flow = module.ReconfirmTakeoverRepairFlow(ISSUE, {"entry_id": "e1"})
    flow.hass = hass
    for refusal, error in ((link.HeatingPlanRejected(409, "active_mode_not_released"), "reconfirm_not_released"),
                           (link.ControllerLinkError("controller_unreachable"), "e32_unreachable"),
                           (link.HeatingPlanRejected(400, "invalid_request"), "e32_unreachable"),
                           (None, "reconfirm_unconfirmed")):
        e32.refusal, e32.answer = refusal, WAITING  # an answer that still waits is no confirmation
        form = await flow.async_step_reconfirm_takeover({})
        assert form["type"] == "form" and form["errors"] == {"base": error}
        assert issue(hass) is not None
    # The plan went back to shadow meanwhile: nothing to confirm, the issue goes.
    e32.refusal = link.HeatingPlanRejected(409, "plan_not_active")
    aborted = await flow.async_step_reconfirm_takeover({})
    assert aborted["type"] == "abort" and aborted["reason"] == "reconfirm_plan_not_active"
    assert issue(hass) is None
    assert set(e32.handovers) == {True}


@pytest.mark.asyncio
async def test_an_answered_or_unknown_issue_aborts_without_sending(hass):
    e32, hub = await rig(hass, CONFIRMED)
    ir.async_create_issue(hass, "open_thermostat", ISSUE, is_fixable=True, is_persistent=False,
                          severity=ir.IssueSeverity.WARNING, translation_key="reconfirm_takeover",
                          data={"entry_id": "e1"})
    flow = module.ReconfirmTakeoverRepairFlow(ISSUE, {"entry_id": "e1"})
    flow.hass = hass
    done = await flow.async_step_init()
    assert done["type"] == "abort" and done["reason"] == "reconfirm_done" and issue(hass) is None
    hass.data["open_thermostat"]["e1"] = {}
    gone = await flow.async_step_init()
    assert gone["type"] == "abort" and gone["reason"] == "e32_rooms_unavailable"
    assert e32.handovers == []


def refusal_response(error, code):
    """An E32 refusal; the client reads at most 512 bytes of its {"error": ...}."""
    response = Response(status=code)

    async def read(size):
        return json.dumps({"error": error}).encode()[:size]
    response.content.read = read
    return response


@pytest.mark.asyncio
async def test_the_client_posts_the_exact_handover_with_csrf(monkeypatch):
    session, _ = session_setup(monkeypatch, *login_responses(), Response(CONFIRMED),
                               refusal_response("plan_not_active", 409), Response({"authenticated": False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        assert await client.async_handover(True) == CONFIRMED
        with pytest.raises(link.HeatingPlanRejected) as refused:
            await client.async_handover(True)
        assert refused.value.status == 409 and refused.value.error == "plan_not_active"
        for value in (1, "true", None):
            with pytest.raises(link.ControllerLinkError, match="^controller_request_invalid$"):
                await client.async_handover(value)
    method, url, kwargs = session.calls[2]
    assert (method, url.removeprefix(BASE)) == ("POST", "/config/heating/handover")
    assert kwargs["data"] == '{"thermostat_disconnected":true}'
    assert kwargs["headers"]["X-OpenThermostat-CSRF"] == CSRF and kwargs["headers"]["Content-Type"] == "application/json"
    assert len(session.calls) == 5 and session.closed


def test_the_issue_texts_exist_in_every_language():
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    titles = {}
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        texts = json.loads((base / name).read_text(encoding="utf-8"))["issues"]["reconfirm_takeover"]
        flow = texts["fix_flow"]
        assert set(flow["step"]) == {"reconfirm_takeover"}
        assert set(flow["error"]) == {"reconfirm_not_released", "reconfirm_unconfirmed", "e32_unreachable",
                                      "e32_password_change_required"}
        assert set(flow["abort"]) == {"reconfirm_done", "reconfirm_plan_not_active", "e32_rooms_unavailable"}
        titles[name] = texts["title"]
    assert titles["translations/nl.json"] == "Bevestig opnieuw dat de E32 de ketel mag regelen"
    assert titles["strings.json"] == titles["translations/en.json"] == "Confirm again that the E32 may control the boiler"
