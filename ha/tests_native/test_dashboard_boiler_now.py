"""The Boiler view's Now card (E32 rc.5, frontend/boiler-now-card.js, the owner's sketch): where it sits, what it
reads, how it is served and its words.

The card is a band in the colour of what the boiler does with its display code in words, the connection with the boiler
and whether it serves hot water, and four large figures: the water to the heating (what is asked, the most the E32 asks
near the target), the water back (the difference), the burner power and its starts in the last hour (calm or not,
today's starts). What it draws from these entities is checked in a browser by test/ha-boiler-now-browser.cjs.
"""
import json
import re
import string
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import dashboard, week_planner
from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.heating_link import BOILER_ACTIVITIES
from custom_components.open_thermostat.room_overview import BOILER_NOW_CARD_TYPE, BOILER_NOW_CARD_URL
from test_dashboard_heating import installation
from test_dashboard_redesign import headed, view
from test_dashboard_tidy import live

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"
CARD = (COMPONENT / "frontend/boiler-now-card.js").read_text(encoding="utf-8")


def known(entity_id):
    return {"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}


def now_section(config):
    section = view(config, "boiler")["sections"][0]
    assert section["cards"][0]["heading"] in ("Now", "Nu", "Teraz")
    return section


@pytest.mark.asyncio
async def test_the_owners_now_is_one_card_with_what_it_needs(hass):
    """The owner's installation (test_dashboard_tidy.live: his boiler's fields, the E32's hub sensors, the flow
    sensors): the heading and one card across both columns. It reads what the boiler does (the E32's activity, the
    boiler's own heating and hot water bits), its display code, the water to the heating and back, the burner power,
    the starts in the last hour with the E32's short-cycling judgement and today's starts, the E32's request and the
    ceiling in effect (on the "Water temperature set by" sensor). The display-code markdown, the activity tiles and the
    pairs (water, gauge and starts) are gone; the rest of the Boiler view is as it was."""
    config, rooms, sensors, hub, fields, flow = live(hass)
    section = now_section(config)
    assert section["column_span"] == 2  # the four figures in one row on a wide screen, as the sketch
    heading, card = section["cards"]
    assert (heading["heading"], heading["icon"]) == ("Now", "mdi:water-boiler")
    assert card == {"type": BOILER_NOW_CARD_TYPE, "grid_options": {"columns": 12}, "activity": hub["boiler_activity"],
                    "heating": fields["heating_active"], "hot_water": fields["dhw_active"], "code": fields["display_code"],
                    "flow": fields["measured_flow_temperature"], "return": fields["measured_return_temperature"],
                    "modulation": fields["reported_burner_modulation"], "starts": hub["burner_starts_last_hour"],
                    "starts_today": hub["daily_burner_starts"], "cycling": hub["burner_short_cycling"],
                    "request": hub["heat_request"], "ceiling": flow["source"]}
    # The section's visibility as before: the code, what the boiler does, the water and the burner. The card has none
    # of its own: whenever its heading shows, the card does (it says "—" for what is not known).
    assert section["visibility"] == [{"condition": "or", "conditions": [known(entity) for entity in (
        fields["display_code"], hub["boiler_activity"], fields["measured_flow_temperature"],
        fields["reported_burner_modulation"])]}]
    assert "visibility" not in card
    boiler = view(config, "boiler")
    assert not any(c["type"] == "gauge" or (c["type"] == "markdown" and "'meaning'" in c["content"])
                   or (c["type"] == "tile" and c["entity"] in (hub["boiler_activity"], fields["heating_active"],
                                                                hub["burner_starts_last_hour"]))
                   for c in view_cards(boiler))
    assert list(headed(boiler)) == ["Now", "Advice", "Today and this week", "Hot water", "Last 24 hours",
                                    "What the boiler reports", "Boiler settings"]
    # Once, on the Boiler view only; its words are the card's own (strings.json), so the config is the same in every
    # language: entity ids only.
    assert sum(json.dumps(v).count(BOILER_NOW_CARD_TYPE) for v in config["views"]) == 1
    assert all("." in value for key, value in card.items() if key not in ("type", "grid_options"))


@pytest.mark.asyncio
@pytest.mark.parametrize("language, heading", [("nl", "Nu"), ("pl", "Teraz")])
async def test_dutch_and_polish_have_the_same_card_under_their_heading(hass, language, heading):
    config, rooms, sensors, hub, fields, flow = live(hass, language)
    section = now_section(config)
    assert section["cards"][0]["heading"] == heading
    assert section["cards"][1]["type"] == BOILER_NOW_CARD_TYPE and section["cards"][1]["ceiling"] == flow["source"]


@pytest.mark.asyncio
async def test_now_is_there_with_what_the_boiler_reports_and_gone_without(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    registry = er.async_get(hass)

    def now():
        config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
        sections = [s for s in view(config, "boiler")["sections"] if s["cards"][0]["heading"] == "Now"]
        return sections[0] if sections else None
    # No boiler fields (an E32 that hears no boiler values yet): the card with the E32's starts count, its judgement
    # and request; the section shows while the starts have a value.
    for entity_id in fields.values():
        registry.async_remove(entity_id)
    section = now()
    assert section["cards"][1] == {"type": BOILER_NOW_CARD_TYPE, "grid_options": {"columns": 12},
                                   "starts": hub["burner_starts_last_hour"], "cycling": hub["burner_short_cycling"],
                                   "request": hub["heat_request"]}
    assert section["visibility"] == [{"condition": "or", "conditions": [known(hub["burner_starts_last_hour"])]}]
    # Nothing the card could show: no section, no heading over nothing.
    registry.async_remove(hub["burner_starts_last_hour"])
    assert now() is None


def test_the_card_module_is_served_with_the_others_and_carries_the_version():
    version = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert BOILER_NOW_CARD_URL == f"/open_thermostat/boiler-now-card-{version}.js"
    assert BOILER_NOW_CARD_TYPE == "custom:openthermostat-boiler-now"
    assert BOILER_NOW_CARD_URL in week_planner.card_modules()
    assert '(BOILER_NOW_CARD_URL, "boiler-now-card.js")' in (COMPONENT / "week_planner.py").read_text(encoding="utf-8")
    # The static step of scripts/final_check.sh checks it with the other seven versioned URLs (tools/dev/prepare_rc5.py
    # finds it by itself: every /open_thermostat/<file>-<version>.js of the integration moves with the next release).
    script = (ROOT / "scripts/final_check.sh").read_text(encoding="utf-8")
    assert """'room_overview.py|BOILER_NOW_CARD_URL = "/open_thermostat/boiler-now-card-'""" in script
    assert "versioned frontend URLs: all eight carry" in script
    assert "ensureDefined('openthermostat-boiler-now', OpenThermostatBoilerNow);" in CARD
    assert "getGridOptions() { return {columns: 12, min_columns: 12}; }" in CARD and "getCardSize() { return 4; }" in CARD
    assert "custom:openthermostat-boiler-now" in dashboard.__doc__


def test_the_card_asks_home_assistant_only_and_sparingly():
    """Never the E32 (session hygiene): only today's starts, from Home Assistant's statistics, at most every 5 minutes
    and on a new day; nothing after the card left the page (test/ha-boiler-now-browser.cjs counts the reads)."""
    assert re.findall(r"callWS\(\{type: '([\w/]+)'", CARD) == ["recorder/statistic_during_period"]
    assert CARD.count("callWS(") == 1 and "subscribe" not in CARD  # no stream that keeps running
    assert re.findall(r"https?://[^'\"\s]+", CARD) == ["http://www.w3.org/2000/svg"]
    for word in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "192.168.", "/api/"):
        assert word not in CARD, word
    assert "STATS_MS = 5 * 60000" in CARD
    assert "disconnectedCallback() {\n  clearInterval(this._timer)" in CARD and "this._gen++;" in CARD


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def card_texts(name):
    sensor = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]["sensor"]
    return sensor["boiler_activity"]["state_attributes"]["card"]["state"]


def test_the_card_texts_are_in_every_language_with_the_same_placeholders():
    english = card_texts("strings.json")
    # The card's own English last resort is the same text, key for key.
    fallback = dict(re.findall(r"(\w+): '([^']*)'", re.search(r"const TEXT = \{(.*?)\};", CARD, re.S)[1]))
    assert fallback == english
    assert card_texts("translations/en.json") == english
    for language in ("nl", "pl"):
        words = card_texts(f"translations/{language}.json")
        assert list(words) == list(english), language
        for key, text in words.items():
            assert text.strip() and placeholders(text) == placeholders(english[key]), (language, key)
    nl, pl = card_texts("translations/nl.json"), card_texts("translations/pl.json")
    # The words of the sketch (Ketel.dc.html) and docs/UX-GLOSSARY.md.
    assert (nl["flow"], nl["back"], nl["power"], nl["starts"]) == (
        "Water naar de verwarming", "Water terug", "Brandervermogen", "Starts afgelopen uur")
    assert (nl["asked"], nl["ceiling"], nl["difference"], nl["power_low"], nl["calm"], nl["today"]) == (
        "gevraagd {flow} °C", "hoogstens {flow} °C", "verschil {n} °C", "laag vuur, rustig", "rustig", "vandaag {n}")
    assert (nl["link"], nl["link_good"], nl["dhw"], nl["no"]) == (
        "verbinding met de ketel: {state}", "goed", "warm water: {state}", "nee")
    assert (pl["flow"], pl["power"]) == (dashboard.TEXT["pl"]["flow_short"], dashboard.TEXT["pl"]["modulation"])
    for words in (english, nl, pl):
        assert not any(term in text.lower() for text in words.values()
                       for term in ("shadow", "digest", "schema", "setpoint", "modulation")), words
    # The band's word is the boiler activity's own state, in the sketch's words ("Verwarmen", "Warm water", "In rust").
    states = json.loads((COMPONENT / "translations/nl.json").read_text(encoding="utf-8"))["entity"]["sensor"]["boiler_activity"]
    assert (states["state"]["heating"], states["state"]["hot_water"], states["state"]["idle"]) == (
        "Verwarmen", "Warm water", "In rust")
    assert "'boiler_activity.state.'" in CARD
    kinds = dict(re.findall(r"(\w+): '(\w+)'", re.search(r"const KIND = \{(.*?)\};", CARD, re.S)[1]))
    assert set(kinds) == set(BOILER_ACTIVITIES) and set(kinds.values()) == {"heat", "water", "keep", "rest"}
