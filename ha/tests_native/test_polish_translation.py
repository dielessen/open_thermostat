"""Polish is shipped complete: every English key, the same placeholders, no English leftovers.

Home Assistant falls back to English per missing key, so a partial pl.json
shows Polish users a mix of languages; this keeps it in step with strings.json.
"""
import json
import re
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[2] / "ha/config/custom_components/open_thermostat"
PLACEHOLDER = re.compile(r"\{[^{}]*\}")
# Names that stay the same in every language, and the temperatures of a choice list ("45 °C").
SAME_IN_POLISH = {"OK", "OpenThermostat", *(f"{c} °C" for c in range(25, 81))}


def flat(node, path=""):
    out = {}
    for key, value in node.items():
        if isinstance(value, dict):
            out.update(flat(value, f"{path}{key}."))
        else:
            out[path + key] = value
    return out


def load(name):
    return flat(json.loads((COMPONENT / name).read_text(encoding="utf-8")))


def test_polish_has_exactly_the_english_keys_and_placeholders():
    english, polish = load("strings.json"), load("translations/pl.json")
    assert sorted(set(english) - set(polish)) == [], "translate the new keys in translations/pl.json"
    assert sorted(set(polish) - set(english)) == []
    for key, text in english.items():
        assert sorted(PLACEHOLDER.findall(polish[key])) == sorted(PLACEHOLDER.findall(text)), key
        assert polish[key].strip(), key


def test_polish_is_translated_not_copied():
    english, polish = load("strings.json"), load("translations/pl.json")
    copied = sorted(key for key, text in polish.items() if text == english[key] and text not in SAME_IN_POLISH)
    assert copied == []
    # Boiler field names stay short and distinct, as in English and Dutch (one device carries them all).
    names = [text for key, text in polish.items() if key.startswith("entity.sensor.field_") and key.endswith(".name")]
    assert len(names) == len(set(names)) and max(map(len, names)) <= 45
    # The week-program syntax the parser reads (English or Dutch day names) stays literal.
    assert "mon-fri: 06:30 20.5" in polish["options.step.e32_room.data_description.program"]
