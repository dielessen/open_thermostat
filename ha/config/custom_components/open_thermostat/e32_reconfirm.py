"""Repairs: "Confirm the takeover again" after an E32 firmware update (beta.23, review S3).

The E32 controlled the boiler before the update; the new firmware does not take
over again until the owner confirms once more that the old thermostat is still
disconnected from the boiler (``active.reconfirm_required`` in the heating
status). Until then it keeps only frost protection. This issue offers that one
confirmation (``POST /config/heating/handover``); the E32 checks it again (its
firmware gate, the plan active) and answers with its active-control status.
Handing back stays on the E32 Rooms page (Active control).
"""
from __future__ import annotations

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

RECONFIRM_ISSUE = "reconfirm_takeover"
# The E32's refusals -> this flow's errors (plan_not_active ends it); anything else: not reachable.
REFUSALS = {"active_mode_not_released": "reconfirm_not_released"}


def issue_id(entry):
    return f"{RECONFIRM_ISSUE}_{entry.entry_id}"


def reconfirm_required(hub):
    """Whether the E32 waits for the owner to confirm the takeover again after an update."""
    active = getattr(hub, "active", None)
    if type(active) is not dict:
        status = getattr(hub, "status", None) or {}
        active = status.get("active") if type(status) is dict else None
    return type(active) is dict and active.get("reconfirm_required") is True


@callback
def update_reconfirm_issue(hass, entry, hub):
    """Raise the issue while the E32 asks for it, remove it once answered (kept during an outage)."""
    if not hub.fresh:
        return
    registry, key = ir.async_get(hass), issue_id(entry)
    if not reconfirm_required(hub):
        if registry.async_get_issue(DOMAIN, key) is not None:
            ir.async_delete_issue(hass, DOMAIN, key)
        return
    if registry.async_get_issue(DOMAIN, key) is None:
        ir.async_create_issue(hass, DOMAIN, key, is_fixable=True, is_persistent=False,
                              severity=ir.IssueSeverity.WARNING, translation_key=RECONFIRM_ISSUE,
                              data={"entry_id": entry.entry_id})


async def async_handover(link, disconnected):
    """POST the handover over the room-plan link's stored connection (one login, its lock)."""
    async with link._lock:
        async with link._client() as client:
            await link._login(client)
            return await client.async_handover(disconnected)


class ReconfirmTakeoverRepairFlow(RepairsFlow):
    """One confirmation: the old thermostat is still disconnected, the E32 may control the boiler again."""

    def __init__(self, issue, data):
        self._issue, self._data = issue, data

    async def async_step_init(self, user_input=None):
        return await self.async_step_reconfirm_takeover(user_input)

    async def async_step_reconfirm_takeover(self, user_input=None):
        from .controller_link import ControllerLinkError, HeatingPlanRejected
        entry = self.hass.config_entries.async_get_entry(self._data.get("entry_id"))
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub") if entry else None
        if hub is None or hub.plan is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        if hub.fresh and not reconfirm_required(hub):
            ir.async_delete_issue(self.hass, DOMAIN, self._issue)
            return self.async_abort(reason="reconfirm_done")
        if user_input is None:
            return self.async_show_form(step_id="reconfirm_takeover")
        try:
            answer = await async_handover(hub.plan, True)
        except HeatingPlanRejected as err:
            if err.error == "plan_not_active":
                ir.async_delete_issue(self.hass, DOMAIN, self._issue)
                return self.async_abort(reason="reconfirm_plan_not_active")
            return self.async_show_form(step_id="reconfirm_takeover",
                                        errors={"base": REFUSALS.get(err.error, "e32_unreachable")})
        except ControllerLinkError:
            return self.async_show_form(step_id="reconfirm_takeover", errors={"base": "e32_unreachable"})
        if type(answer) is not dict or type(answer.get("confirmation")) is not dict or answer.get("reconfirm_required"):
            return self.async_show_form(step_id="reconfirm_takeover", errors={"base": "reconfirm_unconfirmed"})
        ir.async_delete_issue(self.hass, DOMAIN, self._issue)
        return self.async_create_entry(data={})
