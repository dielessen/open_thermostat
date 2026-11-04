"""The boiler's display code in words on the dashboard's "Now" (release 1.0): see at a glance what it does.

rc.5 (the owner's sketch): the Now card (frontend/boiler-now-card.js) says it under the word in its band, "Code -H:
heating"; a code that is not normal operation with its cause number and what to do; a fault of the boiler turns the
band red with what it is, "Fault · code 6A 227" and what to do. The words are the display code sensor's attributes
(display_codes.py), in the Home Assistant language; the card draws them (test/ha-boiler-now-browser.cjs, with the
attributes display_codes.describe() gives). Here: the card gets the code sensor, and it reads the attributes the
sensor really has, with the same fault severities.
"""
import re
from pathlib import Path

import pytest

from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.display_codes import FAULTS, attributes, describe
from custom_components.open_thermostat.room_overview import BOILER_NOW_CARD_TYPE
from test_dashboard_heating import installation

OWNER = "nefit-ecomline-classic-hrc-22h"
CARD = (Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat/frontend/boiler-now-card.js").read_text(
    encoding="utf-8")


def card(hass, e):
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    now = next(v for v in config["views"] if v["path"] == "boiler")["sections"][0]
    assert now["cards"][0]["heading"] in ("Now", "Nu")  # first on the Boiler view
    return next(c for c in now["cards"] if c["type"] == BOILER_NOW_CARD_TYPE)


@pytest.mark.asyncio
async def test_the_now_card_says_the_display_code_in_words(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    assert card(hass, e)["code"] == fields["display_code"]
    hass.config.language = "nl"
    assert card(hass, e)["code"] == fields["display_code"]


def test_the_card_reads_the_words_the_code_sensor_has():
    """The attributes the card reads are the ones display_codes gives the code sensor, for a normal code, a waiting
    code with advice, a fault and an unknown code, also with the owner's boiler table and in Dutch and Polish."""
    for code, cause, model, language in (("-H", 200, None, "en"), ("0A", 202, None, "nl"), ("6A", 227, None, "pl"),
                                         ("0C", None, OWNER, "nl"), ("2E", 207, OWNER, "en")):
        words = attributes(describe(code, cause, model, language))
        assert {"meaning", "severity", "severity_text", "advice", "cause"} <= set(words), (code, language)
        assert words["meaning"] and words["severity_text"], (code, language)
    assert attributes(describe("6A", 227))["severity"] in FAULTS and attributes(describe("-H", 200))["severity"] == "normal"
    for name in ("meaning", "severity_text", "advice"):
        assert f"text('{name}')" in CARD, name
    assert "a.severity" in CARD and "a.cause" in CARD
    # A fault turns the band red: the same severities as the code sensor's own "fault".
    assert set(re.search(r"const FAULTS = new Set\(\[(.*?)\]\)", CARD)[1].replace("'", "").split(", ")) == set(FAULTS)
    # The owner's EcomLine Classic, by its own manual: the words come from its table.
    assert attributes(describe("0C", None, OWNER))["meaning"] == "Waiting for the 3-way valve to switch"
