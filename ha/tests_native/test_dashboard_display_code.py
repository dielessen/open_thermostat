"""The boiler's display code in words on the dashboard's "Now" (release 1.0): see at a glance what it does.

The meaning large with the raw code small next to it; a fault as a warning and a lockout as an error,
with what to do; an unknown code as the raw code with a pointer to the manual. Rendered here with Home
Assistant's own template engine against the attributes the code sensor really has (display_codes.py).
"""
import pytest
from homeassistant.helpers.template import Template

from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.display_codes import attributes, describe
from test_dashboard_heating import installation

OWNER = "nefit-ecomline-classic-hrc-22h"


def card(hass, e):
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    now = next(v for v in config["views"] if v["path"] == "boiler")["sections"][0]
    assert now["cards"][0]["heading"] in ("Boiler", "Ketel")
    return next(c for c in now["cards"] if c["type"] == "markdown" and "'meaning'" in c["content"])


def render(hass, content, entity_id, code, cause=None, model=None, language="en"):
    hass.states.async_set(entity_id, code, attributes(describe(code, cause, model, language)))
    return Template(content, hass).async_render(parse_result=False).strip()


@pytest.mark.asyncio
async def test_normal_operation_reads_as_words_with_the_code_small_next_to_it(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    code = fields["display_code"]
    content = card(hass, e)["content"]
    assert render(hass, content, code, "0H", 203) == (
        '<ha-icon icon="mdi:water-boiler"></ha-icon> Boiler: **Standby: no heat demand** <small>0H 203</small>')
    assert render(hass, content, code, "=H") == '<ha-icon icon="mdi:water-boiler"></ha-icon> Boiler: **Hot water** <small>=H</small>'
    # Waiting: its own icon and the advice on a second line.
    waiting = render(hass, content, code, "0A", 202)
    assert waiting.startswith('<ha-icon icon="mdi:timer-sand"></ha-icon> Boiler: **Waiting: anti-cycle time')
    assert waiting.endswith("<small>No action needed; the boiler continues by itself.</small>")
    # The owner's EcomLine Classic, by its own manual.
    assert "**Waiting for the 3-way valve to switch** <small>0C</small>" in render(hass, content, code, "0C", None, OWNER)


@pytest.mark.asyncio
async def test_a_fault_is_a_warning_and_a_lockout_an_error_with_what_to_do(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    code = fields["display_code"]
    content = card(hass, e)["content"]
    fault = render(hass, content, code, "6A", 227)
    assert fault.startswith('<ha-alert alert-type="warning" title="No flame detected after ignition">Fault. ')
    assert "Check that the gas tap is open" in fault and fault.endswith("<small>Display code 6A 227</small></ha-alert>")
    lockout = render(hass, content, code, "3L", 214)
    assert lockout.startswith('<ha-alert alert-type="error" title="Fan not running during start-up">Lockout: ')
    blocking = render(hass, content, code, "2E", 207)
    assert blocking.startswith('<ha-alert alert-type="warning" title="Water pressure too low">Blocking fault')


@pytest.mark.asyncio
async def test_an_unknown_code_shows_the_raw_code_and_the_manual_never_a_guess(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    code = fields["display_code"]
    content = card(hass, e)["content"]
    assert render(hass, content, code, "2E", 207, OWNER) == (
        '<ha-icon icon="mdi:help-circle-outline"></ha-icon> **Display code 2E 207** · '
        'Unknown code, see your boiler manual.')
    # A sensor without the words (an older integration's entity): the bare code, still readable.
    hass.states.async_set(code, "0H", {})
    assert Template(content, hass).async_render(parse_result=False).strip() == (
        '<ha-icon icon="mdi:water-boiler"></ha-icon> Display code **0H**')


@pytest.mark.asyncio
async def test_a_dutch_home_assistant_gets_dutch_words_and_labels(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    hass.config.language = "nl"
    content = card(hass, e)["content"]
    fault = render(hass, content, fields["display_code"], "6A", None, OWNER, "nl")
    assert fault.startswith('<ha-alert alert-type="warning" title="Geen vlam na het ontsteken">Storing. ')
    assert fault.endswith("<small>Displaycode 6A</small></ha-alert>")
