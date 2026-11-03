"""The generated dashboard is tidy: no half-empty rows, headed sections, short notes, and the browser fixture is current.

Home Assistant's sections view lays the cards of a section out on a 12-column grid. A tile is 6 columns
wide, almost everything else 12, and `grid_options.columns` overrides it. A card hidden by its `visibility`
leaves the grid, so a half-width tile whose neighbour is hidden would stand alone with an empty slot next to it.
The same rule is drawn in a browser by test/dashboard-views-browser.cjs, from test/fixtures/ha-dashboard-views.json
(rewritten by running this test with OPENTHERMOSTAT_WRITE_DASHBOARD_FIXTURE=1).
"""
import json
import os
import re
from pathlib import Path

import pytest

from custom_components.open_thermostat.dashboard import RoomDashboard
from test_dashboard_heating import installation, walk
from test_dashboard_tidy import live

FIXTURE = Path(__file__).resolve().parents[2] / "test/fixtures/ha-dashboard-views.json"
HALF = {"tile", "button"}


def columns(card):
    options = card.get("grid_options") or {}
    return options.get("columns", 6 if card["type"] in HALF else 12)


def rows(cards, hidden):
    """The grid rows of a section: [[cards]], with the conditional cards left out when ``hidden``."""
    result, row, used = [], [], 0
    for card in cards:
        if hidden and card.get("visibility"):
            continue
        if used + columns(card) > 12:
            result.append(row)
            row, used = [], 0
        row.append(card)
        used += columns(card)
    if row:
        result.append(row)
    return result


def gaps(config):
    """Every row that does not fill the 12 columns: (view, section heading, scenario, the cards' types)."""
    found = []
    for view in config["views"]:
        for section in view.get("sections", []):
            for hidden in (False, True):
                for row in rows(section["cards"], hidden):
                    if sum(columns(card) for card in row) != 12:
                        found.append((view["path"], section["cards"][0].get("heading"),
                                      "conditional cards hidden" if hidden else "all shown",
                                      [card.get("entity") or card["type"] for card in row]))
    return found


def dashboards(hass):
    config, *_ = live(hass)
    return config


@pytest.mark.asyncio
async def test_no_row_of_a_section_is_half_empty_in_any_state(hass):
    config = dashboards(hass)
    assert gaps(config) == []
    assert None not in list(walk(config))
    # The bare installation too (no thermostats, no learning): only the rooms' own tiles.
    e, *_ = installation(hass, "nl")
    assert gaps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()) == []


@pytest.mark.asyncio
async def test_every_section_starts_with_its_heading_and_every_view_is_sections(hass):
    config = dashboards(hass)
    for view in config["views"]:
        if view.get("panel"):
            continue
        assert view["type"] == "sections" and view["max_columns"] <= 2, view["path"]
        for section in view["sections"]:
            assert section["cards"][0]["type"] == "heading", (view["path"], section["cards"][0])
    # The order the owner asked for: overview, rooms, week program, boiler, learning, diagnostics.
    assert [v["path"] for v in config["views"]] == ["heating", "rooms", "boiler", "learned", "diagnostics", "comparison"]


@pytest.mark.asyncio
async def test_notes_are_one_sentence_with_the_rest_behind_more(hass):
    """A long grey note is cut off on a phone: the first sentence shows, the rest sits behind "More"."""
    for language in ("en", "nl", "pl"):
        config, *_ = live(hass, language)
        for view in config["views"]:
            for card in (c for s in view.get("sections", []) for c in s["cards"] if c["type"] == "markdown"):
                shown = card["content"].split("<details>")[0]
                if "{%" in shown or "{{" in shown:  # templates: their text is checked where they are built
                    continue
                sentences = re.split(r"(?<=[.!?])\s+(?=\S)", shown.strip())
                assert len(sentences) <= 1, (language, view["path"], shown)


@pytest.mark.asyncio
async def test_the_browser_fixture_is_the_current_dashboard(hass):
    config = {}
    for language in ("en", "nl"):
        config[language], *_ = live(hass, language)
    # The dashboard URL path has a random part: not part of the structure.
    text = re.sub(r"open-thermostat-fixture-[a-z0-9]+", "open-thermostat-fixture-x",
                  json.dumps(config, indent=1, ensure_ascii=False, sort_keys=True)) + chr(10)
    if os.environ.get("OPENTHERMOSTAT_WRITE_DASHBOARD_FIXTURE") == "1":
        FIXTURE.parent.mkdir(exist_ok=True)
        FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    # Entity ids and the dashboard's path come from the registry, so the fixture is the structure and the words.
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == json.loads(text), (
        "run this test with OPENTHERMOSTAT_WRITE_DASHBOARD_FIXTURE=1 to rewrite test/fixtures/ha-dashboard-views.json")
