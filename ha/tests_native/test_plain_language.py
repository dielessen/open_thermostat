"""Every form explains itself: a step description and a field description, in English and Dutch."""
import json
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


def steps(node, path=""):
    for key, value in node.items():
        if key == "step" and isinstance(value, dict):
            for step_id, step in value.items():
                yield f"{path}.step.{step_id}", step
        elif isinstance(value, dict):
            yield from steps(value, f"{path}.{key}")


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json", "translations/nl.json"])
def test_every_step_and_field_has_a_description(filename):
    document = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))
    missing = []
    for path, step in steps({k: document[k] for k in ("config", "options", "config_subentries")}):
        if not step.get("description", "").strip():
            missing.append(path)
        holders = [("", step)] + [("/" + name, section) for name, section in step.get("sections", {}).items()]
        for prefix, holder in holders:
            descriptions = holder.get("data_description", {})
            missing += [f"{path}{prefix}.{field}" for field in holder.get("data", {})
                        if not descriptions.get(field, "").strip()]
    assert missing == []


def test_the_room_editor_says_who_does_what_in_plain_words():
    en = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))["options"]["step"]
    nl = json.loads((COMPONENT / "translations/nl.json").read_text(encoding="utf-8"))["options"]["step"]
    room = en["e32_room"]["data_description"]
    assert room["fallback_temperature"] == ("The temperature the E32 keeps when Home Assistant gives no target "
                                            "and the room has no week program, or its clock is not set yet.")
    assert nl["e32_room"]["data_description"]["fallback_temperature"] == (
        "De temperatuur die de E32 aanhoudt als Home Assistant geen doel doorgeeft en de ruimte geen weekprogramma "
        "heeft, of zijn klok nog niet is gezet.")
    assert room["ble_sources"] == "Sensors paired on the E32 itself; they keep working without Home Assistant."
    assert "without Home Assistant" in en["e32_room"]["description"]
    assert "zonder Home Assistant" in nl["e32_room"]["description"]
    assert "{revision}" in en["e32_rooms"]["description"] and "{rooms}" in nl["e32_rooms"]["description"]
    # Explanations live in descriptions; field labels and entity names stay short.
    for document in (en, nl):
        assert all(len(label) <= 60 for label in document["e32_room"]["data"].values())
    for filename in ("strings.json", "translations/nl.json"):
        entity = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))["entity"]
        assert all(len(item["name"]) <= 45 for platform in entity.values() for item in platform.values()), filename


def test_english_and_dutch_have_the_same_texts():
    def keys(node, path=""):
        for key, value in node.items():
            if isinstance(value, dict):
                yield from keys(value, f"{path}.{key}")
            else:
                yield f"{path}.{key}"
    en = set(keys(json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))))
    nl = set(keys(json.loads((COMPONENT / "translations/nl.json").read_text(encoding="utf-8"))))
    assert sorted(en - nl) == [] and sorted(nl - en) == []


def test_the_fixed_gas_price_is_per_cubic_metre_in_your_own_currency():
    from custom_components.open_thermostat.energy_input import PRICE_LIMITS
    assert PRICE_LIMITS == (0.0001, 1000.0)  # the E32 accepts the same range
    for filename, currency in (("strings.json", "currency"), ("translations/nl.json", "valuta")):
        options = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))["options"]
        price = options["step"]["energy"]["data_description"]["gas_price"]
        assert "per m³" in price and currency in price, filename
        invalid = options["error"]["gas_price_invalid"]
        assert "1000" in invalid and "per m³" in invalid and currency in invalid, filename
