"""Polish on the dashboard: every text table the integration builds itself has a complete Polish entry.

translations/pl.json covers flows, entities and Repairs (test_polish_translation.py); the dashboard
markdown, the advice, the problem reasons, the weekly summary and the learned overview are texts of
their own, chosen by the Home Assistant language. Each Polish table has exactly the English keys and
placeholders, so a Polish Home Assistant never shows English or a broken "{placeholder}".
The cards' JavaScript tables are checked the same way in test/week-editor.test.cjs.
"""
import json
import re
import string
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import (boiler_power, dashboard, display_code_table, e32_room_flow,
                                               entity_id_tidy, heating_advice, heating_problem,
                                               installation_group, learned_overview, weekly_summary)
from custom_components.open_thermostat.dashboard import RoomDashboard, TEXT

# The same in every language: names, units and figures.
SAME = {"E32", "OpenThermostat", "{m} min"}


def flat(node, path=""):
    out = {}
    for key, value in node.items():
        if isinstance(value, dict):
            out.update(flat(value, f"{path}{key}."))
        else:
            out[path + key] = value
    return out


def placeholders(text):
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name is not None)


TABLES = {
    "dashboard.TEXT": dashboard.TEXT,
    "heating_advice.TEXT": heating_advice.TEXT,
    "heating_problem.TEXT": heating_problem.TEXT,
    "weekly_summary.TEXT": weekly_summary.TEXT,
    "learned_overview.TEXT": learned_overview.TEXT,
    "boiler_power.BASIS": boiler_power.BASIS,
    "entity_id_tidy.USED_IN": entity_id_tidy.USED_IN,
    "installation_group.GROUP_TITLES": installation_group.GROUP_TITLES,
    "e32_room_flow.BOILER_MAXIMUM_TEXT": e32_room_flow.BOILER_MAXIMUM_TEXT,
    "e32_room_flow.NEW_ROOM_TITLE": e32_room_flow.NEW_ROOM_TITLE,
}


@pytest.mark.parametrize("name", sorted(TABLES))
def test_polish_has_exactly_the_english_keys_and_placeholders(name):
    table = TABLES[name]
    english, polish = flat({"t": table["en"]}), flat({"t": table["pl"]})
    assert sorted(set(english) - set(polish)) == [], f"translate the new keys of {name} into Polish"
    assert sorted(set(polish) - set(english)) == []
    for key, text in english.items():
        assert polish[key].strip(), key
        assert placeholders(polish[key]) == placeholders(text), key
        # Translated, not copied (a text that is only placeholders and names may stay).
        assert polish[key] != text or text in SAME or not re.sub(r"\{\w+\}|[^A-Za-z]", "", text), key


def test_display_codes_have_polish_words():
    assert display_code_table.LANGUAGES == ("en", "nl", "pl")
    for table in (display_code_table.SEVERITIES, display_code_table.ADVICE):
        for key, texts in table.items():
            assert len(texts) == 3 and texts[2].strip() and texts[2] != texts[0], key


@pytest.mark.parametrize(("configured", "expected"), [("pl", "pl"), ("pl-PL", "pl"), ("PL", "pl"),
                                                       ("nl-NL", "nl"), ("de", "en"), (None, "en")])
def test_the_home_assistant_language_picks_polish(configured, expected):
    hass = SimpleNamespace(config=SimpleNamespace(language=configured))
    assert dashboard.dashboard_language(hass) == expected
    assert heating_advice.language(hass) == expected
    assert learned_overview.language(hass) == expected
    assert installation_group.group_title(hass) == installation_group.GROUP_TITLES[expected]


def test_polish_figures_use_a_decimal_comma():
    assert heating_advice.fmt(1.5, "pl") == "1,5" and heating_advice.fmt(2, "pl") == "2"
    assert heating_problem.render([("pressure_low", {"pressure": 0.8})], "pl") == [
        "Ciśnienie wody jest niskie (0,8 bar). Uzupełnij wodę w instalacji grzewczej."]


def test_polish_dashboard_texts_fit_the_markdown_templates():
    polish = TEXT["pl"]
    for key, text in polish.items():
        assert "{%" not in text and "{{" not in text and "\n" not in text, key
    # A readiness line without its figures shows the part before the colon ("Stabilność").
    for item in dashboard.READINESS_ITEMS:
        text = polish["ready_" + item]
        if "{" in text:
            assert 0 < text.find(":") < text.find("{"), item
    card = dashboard._readiness_card(polish, "sensor.gotowosc")
    assert "{% else %}Stabilność{% endif %}" in card["content"]
    assert "Kocioł słyszalny na magistrali" in card["content"]


def test_polish_weekly_summary_message():
    records = {f"2026-11-0{d}": {"observed_s": 86400, "heating_m3": 1.25, "hot_water_m3": 0.5, "heating_kwh": 12.5,
                                 "hot_water_kwh": 5.0, "heating_s": 7200, "hot_water_s": 1800, "meter": True}
               for d in range(1, 8)}
    from datetime import date
    result = weekly_summary.weekly_summary(records, date(2026, 11, 7), ["Niskie ciśnienie wody"], "pl")
    assert result["title"] == "OpenThermostat: Twój tydzień"
    assert "Ogrzewanie: 8,75 m³ gazu (87,5 kWh), palnik 14 godz." in result["message"]
    assert "- Niskie ciśnienie wody" in result["message"]


@pytest.mark.asyncio
async def test_a_polish_home_assistant_gets_a_polish_dashboard(hass):
    from test_dashboard_heating import installation
    e, *_ = installation(hass, "pl")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    text = json.dumps(config, ensure_ascii=False)
    assert [view["title"] for view in config["views"]][:5] == [
        "Przegląd", "Pomieszczenia", "Kocioł", "Uczenie i ustawienia", "Diagnostyka"]
    for words in ("Dom", "Żądanie do kotła", "Okres próbny", "Czujniki Bluetooth",
                  "Czujniki Bluetooth"):
        assert words in text, words
    # No English dashboard text is left (the names in it come from the registry).
    english = {value for key, value in TEXT["en"].items()
               if value != TEXT["pl"][key] and len(value) > 3 and value.lower() != value}  # not entity IDs
    assert sorted(value for value in english if value in text) == []
