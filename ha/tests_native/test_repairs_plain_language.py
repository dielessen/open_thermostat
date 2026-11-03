"""Repairs and the options/first-run texts speak plain language; information is a one-time notification."""
import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
FILES = ["strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"]
INFO = ("legacy_metrics_history", "metrics_definition_v2", "room_model_v2")
# Words a normal user never sees outside a "Technical details" part.
JARGON = re.compile(r"shadow|controller|readback|\bACK\b|digest|fingerprint|schema|quarantine|descriptor", re.I)
CLEANED = [("options", "step", "graph_review"), ("options", "step", "graph_status"),
           ("options", "step", "graph_source_status"), ("options", "step", "installation_source"),
           ("options", "step", "installation_source_review"), ("config", "step", "user"),
           ("config", "step", "shadow")]


def load(name):
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def walk(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, str):
        yield node


@pytest.mark.parametrize("filename", FILES)
def test_every_repair_says_what_to_do(filename):
    issues = load(filename)["issues"]
    for key, issue in issues.items():
        assert issue["title"].strip(), key
        assert issue.get("description", "").strip(), f"{key} has no description"
        if "fix_flow" in issue:
            assert re.search(r"Fix|Oplossen|Napraw|Configure|Configureren|Konfiguruj", issue["description"]), key


@pytest.mark.parametrize("filename", FILES)
def test_the_important_repairs_have_the_planned_words(filename):
    issues = load(filename)["issues"]
    password, zone = issues["e32_default_password"]["description"], issues["e32_time_zone"]["description"]
    assert "{name}" in password and "{e32}" in zone and "{home}" in zone
    assert zone.count("{home}") == 2  # the Fix sets the E32 to the Home Assistant zone
    assert issues["valve_single_source"]["description"].strip()
    for key in ("reconfirm_takeover", "reconfirm_takeover_thermostat"):
        assert "{" not in issues[key]["description"]  # raised without placeholders


@pytest.mark.parametrize("filename", FILES)
def test_user_visible_texts_of_the_cleaned_steps_have_no_developer_words_outside_technical_details(filename):
    document = load(filename)
    for section, kind, step_id in CLEANED:
        step = document[section][kind][step_id]
        for text in walk({k: v for k, v in step.items()}):
            visible = re.split(r"Technical details|Technische details|Szczegóły techniczne", text)[0]
            assert not JARGON.search(re.sub(r"\{[^}]*\}", "", visible)), (step_id, visible)


@pytest.mark.parametrize("filename", FILES)
def test_menu_labels_and_first_run_texts(filename):
    document = load(filename)
    menu = document["options"]["step"]["init"]["menu_options"]
    words = {"strings.json": ("Repair room plan", "Is everything connected?"),
             "translations/en.json": ("Repair room plan", "Is everything connected?"),
             "translations/nl.json": ("Ruimteplan herstellen", "Is alles verbonden?"),
             "translations/pl.json": ("Napraw plan pomieszczeń", "Czy wszystko jest połączone?")}[filename]
    assert (menu["graph_prepare"], menu["configuration_status"]) == words
    config = document["config"]
    assert "ib-therm" not in config["step"]["user"]["menu_options"]["legacy"]
    assert "(" in config["step"]["user"]["menu_options"]["legacy"]
    if filename in ("strings.json", "translations/en.json"):
        assert config["error"]["invalid_topic"] == "Use 1 to 32 letters, digits, - or _."
        assert config["step"]["user"]["description"].startswith("Connect your E32. It shows you what to do next.")
    reauth = config["error"]["reauth_session_capacity"]
    assert "1." in reauth and "2." in reauth and len(reauth) < 160


def test_strings_json_equals_the_english_translation():
    assert load("strings.json") == load("translations/en.json")


@pytest.mark.parametrize("filename", FILES)
def test_the_information_items_are_friendly_and_say_the_history_is_kept(filename):
    issues = load(filename)["issues"]
    for key in INFO:
        assert issues[key]["title"].strip() and issues[key]["description"].strip()
        assert not JARGON.search(issues[key]["description"])


def test_no_information_item_is_raised_as_a_repair():
    for path in COMPONENT.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for key in INFO:
            assert not re.search(rf"async_create_issue\([^)]*{key}", text, re.S), (path.name, key)


@pytest.mark.parametrize("language", ["en", "nl", "pl"])
def test_the_heating_problems_tell_what_to_do(language):
    from custom_components.open_thermostat.heating_problem import TEXT
    for key in ("short_cycling", "active_foreign_controller", "active_measurement_lost",
                "active_boiler_no_response", "active_transmit_failed"):
        assert len(TEXT[language][key].split(".")) >= 3, key  # what is wrong, then what to do
