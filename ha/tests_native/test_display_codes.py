"""The boiler's display code in words (release 1.0): meaning, severity and advice per boiler profile.

The tables live in the boiler profiles (docs/modern-thermostat/boiler-profiles) and are compiled by
scripts/generate_display_codes.py. The code sensor keeps the raw code as its state; the words are
attributes in the Home Assistant language. A code no table lists is never guessed.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from custom_components.open_thermostat.boiler_fields import FIELDS, QUALITIES, BoilerFieldCache
from custom_components.open_thermostat.display_code_table import FALLBACK, GENERIC, MODELS, TABLES
from custom_components.open_thermostat.display_codes import attributes, describe, language_index, normalise
from custom_components.open_thermostat.v1_boiler_fields import async_setup_boiler_fields
from test_boiler_fields import by_index
from test_modern_metrics import system

ROOT = Path(__file__).resolve().parents[2]
OWNER = "nefit-ecomline-classic-hrc-22h"
DISPLAY_CODE, SERVICE_NUMBER = 24, 25
# Boiler-model selection (E32 Boiler page): its family table (docs/modern-thermostat/boiler-profiles).
FAMILY_MODELS = {
    "nefit-ecomline-classic": OWNER, OWNER: OWNER,
    "nefit-ecomline-excellent": "nefit-ecomline-excellent",
    "nefit-proline": "nefit-proline-hrc",
    "nefit-trendline-ii": "nefit-trendline-ii",
    "nefit-topline": "nefit-topline-aquapower",
    "nefit-smartline": "nefit-smartline-basic",
    "buderus-logamax-plus-gb172": "buderus-logamax-plus-gb172",
    "buderus-gb162": "buderus-logamax-plus-gb162",
    "bosch-condens-7000i-w": "bosch-condens-7000i-w",
    "bosch-cerapur-zsb-zwb-5c": "bosch-cerapur-zsb-5c", "junkers-cerapur": "bosch-cerapur-zsb-5c",
    "worcester-bosch-greenstar-4000": "worcester-bosch-greenstar-4000",
}


def wire(code):
    return ord(code[0]) << 8 | ord(code[1])


def test_the_generated_table_matches_the_boiler_profiles():
    subprocess.run([sys.executable, "scripts/generate_display_codes.py", "--check"], cwd=ROOT, check=True)
    assert GENERIC == "ems-generic" and FALLBACK[OWNER] is None
    # Each family with a reviewed manual has its own table for exactly its selections.
    assert MODELS == FAMILY_MODELS
    assert set(TABLES) == {GENERIC, *FAMILY_MODELS.values()}
    assert all(FALLBACK[table] is None for table in FAMILY_MODELS.values())  # never borrowed


def test_a_known_code_with_its_cause_number_in_three_languages():
    standby = describe("0H", 203)
    assert standby["meaning"] == "Standby: no heat demand" and standby["severity"] == "normal"
    assert standby["table"] == "ems-generic" and standby["cause"] == 203 and standby["known"] and not standby["fault"]
    assert describe("0H", 203, language="nl")["meaning"] == "Stand-by: geen warmtevraag"
    assert describe("0H", 203, language="pl")["meaning"] == "Czuwanie: brak zapotrzebowania na ciepło"
    assert describe("0H", 203, language="de-DE")["meaning"] == "Standby: no heat demand"  # English otherwise
    assert describe("=H", 201)["meaning"] == "Hot water" and describe("-H", 200)["meaning"] == "Heating"
    flame = describe("6A", 227)
    assert flame["fault"] and flame["meaning"] == "No flame detected after ignition"
    assert flame["advice"].startswith("Check that the gas tap is open")
    lockout = describe("3L", 214, language="nl")
    assert lockout["severity"] == "locking" and lockout["severity_text"].startswith("Vergrendelende storing")
    assert describe("2E", 207)["advice"].startswith("Check the water pressure")
    assert describe("0A", 202)["severity"] == "waiting"


def test_the_cause_number_tells_codes_apart():
    assert describe("0Y", 204)["severity"] == "waiting"
    assert describe("0Y", 276)["severity"] == "blocking" and "95 °C" in describe("0Y", 276)["meaning"]
    assert describe("6C", 228)["meaning"] != describe("6C", 306)["meaning"]


def test_a_missing_or_unlisted_cause_uses_the_code_only_meaning_or_none():
    # No cause number (Classic), zero or a number this table does not list: the code-only row,
    # which exists only where every reviewed document agrees.
    for cause in (None, 0, True, 999, -1, "203"):
        assert describe("0H", cause)["meaning"] == "Standby: no heat demand", cause
        assert describe("0H", cause)["cause"] is None or cause == 999
    assert describe("6A")["fault"] and describe("6A")["meaning"] == "No flame detected after ignition"
    # 0C and 2F mean different things on Classic and newer boilers, EA and 0Y on the Bosch
    # letter-code families: no code-only guess.
    for code in ("0C", "2F", "3C", "7H", "EA", "0Y"):
        assert not describe(code)["known"], code
    assert describe("0C", 283)["meaning"] == "Preparing to start the burner"


def test_the_boiler_model_selects_its_own_table_and_never_borrows_from_another_family():
    # The owner's EcomLine Classic: letter service codes, its own meanings.
    valve = describe("0C", 283, OWNER)
    assert valve["table"] == OWNER and valve["meaning"] == "Waiting for the 3-way valve to switch"
    assert describe("2F", None, OWNER)["meaning"].startswith("Adapting to a small water volume")
    assert describe("0H", None, OWNER)["meaning"] == "Standby: no heat demand"
    assert describe("0U", None, "nefit-ecomline-classic")["meaning"] == "Fan purge before or after burning (15 s)"
    assert describe("P", None, OWNER)["meaning"].startswith("Control unit starting up")
    assert describe("EP", None, OWNER, "nl")["meaning"] == "Besturing en codeerstekker (KIM) niet compatibel"
    # 2E (low water pressure on newer boilers) is not in the Classic manual: unknown, not borrowed.
    unknown = describe("2E", 207, OWNER)
    assert not unknown["known"] and unknown["table"] is None
    # A model without a table of its own (or none chosen) uses the generic table.
    for model in (None, "none", "emsesp-product-122", 7):
        assert describe("2E", 207, model)["meaning"] == "Water pressure too low", model


def test_an_unknown_code_reads_as_the_raw_code_with_a_pointer_to_the_manual():
    for language, text in (("en", "Unknown code, see your boiler manual."),
                           ("nl", "Onbekende code, zie de handleiding van je ketel."),
                           ("pl", "Nieznany kod, sprawdź instrukcję kotła.")):
        unknown = describe("7X", 512, language=language)
        assert unknown["code"] == "7X" and unknown["cause"] == 512 and unknown["meaning"] == text
        assert unknown["severity"] == "unknown" and not unknown["known"] and unknown["advice"] is None


def test_codes_are_normalised_and_no_code_is_no_description():
    assert normalise(" P") == "P" and normalise("-.H") == "-H" and normalise("0H") == "0H"
    for none in (None, "", "  ", "--", "0H0", "\x01\x02", 12360):
        assert normalise(none) is None and describe(none) is None, none
    assert attributes(None) == {}
    assert language_index("nl_NL") == 1 and language_index("pl") == 2 and language_index(None) == 0


def test_every_table_row_has_three_languages_and_a_known_severity():
    for name, rows in TABLES.items():
        model = next((m for m, t in MODELS.items() if t == name), None)
        for (code, cause), (severity, advice, text) in rows.items():
            assert len(text) == 3 and all(text), (name, code, cause)
            if code is None:  # a cause number without a display code: any code with that number
                assert name != GENERIC and cause is not None
                found = describe("XX", cause, model)
                assert found["table"] == name and found["meaning"] == text[0], (name, cause)
                continue
            assert normalise(code) == code, (name, code, cause)
            assert describe(code, cause, model)["table"] == name


def test_the_family_tables_follow_their_own_manuals():
    # ProLine and TrendLine II: code + cause number, the type column for the severity.
    assert describe("2E", 207, "nefit-proline")["severity"] == "blocking"
    assert describe("8C", 373, "nefit-proline")["meaning"].startswith("Burner thermostat tripped too often")
    assert describe("5Y", None, "nefit-proline")["severity"] == "service"
    assert describe("EE", 554, "nefit-trendline-ii")["meaning"] == "Internal fault in the control unit"
    assert describe("4A", 332, "nefit-topline")["meaning"] == "Flow temperature above 110 °C"
    # GB172: 4C 224 is in both the blocking and the locking table, so "fault".
    assert describe("4C", 224, "buderus-logamax-plus-gb172")["severity"] == "fault"
    assert describe("2P", 342, "buderus-logamax-plus-gb172")["severity"] == "waiting"
    assert describe("C0", 288, "nefit-smartline", "nl")["meaning"] == "Druksensor onderbroken of kortgesloten"
    assert describe("5L", None, "buderus-gb162")["meaning"] == "A blocking or locking fault has occurred"
    # The EcomLine Excellent shares the Classic codes, except that its wiring-link fault is 8Y.
    assert describe("8Y", None, "nefit-ecomline-excellent")["meaning"] == describe("8L", None, OWNER)["meaning"]
    assert not describe("8L", None, "nefit-ecomline-excellent")["known"]
    assert describe("0C", None, "nefit-ecomline-excellent")["meaning"] == "Waiting for the 3-way valve to switch"


def test_bosch_letter_codes_and_number_only_messages():
    # Condens 7000i W / Cerapur: letter codes with a subcode; operating messages are number only.
    for model in ("bosch-condens-7000i-w", "bosch-cerapur-zsb-zwb-5c", "junkers-cerapur"):
        flame = describe("EA", 227, model)
        assert flame["meaning"] == "No flame detected after ignition" and flame["severity"] == "fault", model
        assert describe("C6", 215, model)["severity"] == "locking"
        assert describe("-H", 203, model)["meaning"] == "Standby: no heat demand"  # any code with 203
        assert describe("0H", 200, model, "pl")["meaning"] == "Ogrzewanie"
        # The code with its number wins over the number alone: D4 341 blocks, "-" 341 only limits.
        assert describe("D4", 341, model)["severity"] == "blocking"
        assert describe("-H", 341, model)["severity"] == "waiting"
        # A Nefit code is not borrowed from another family.
        assert not describe("2E", 207, model)["known"]
    assert describe("EH", 258, "bosch-condens-7000i-w")["known"] and not describe("EH", 258, "junkers-cerapur")["known"]
    # Greenstar 4000: the display shows a three- or four-digit number only.
    model = "worcester-bosch-greenstar-4000"
    lost = describe("EA", 2927, model)
    assert lost["meaning"] == "Flame lost while burning" and lost["severity"] == "blocking" and lost["cause"] == 2927
    assert describe("XX", 2980, model)["severity"] == "locking"
    assert not describe("XX", 1013, model)["known"]  # a maintenance message (class W) is left out
    # Four-digit numbers stay numbers, also where no table knows them.
    assert describe("7X", 9999)["cause"] == 9999 and describe("7X", 10000)["cause"] is None


def test_the_profile_topic_carries_the_boiler_model_choice():
    cache = BoilerFieldCache()
    base = {"schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
            "supported": [], "not_fitted": [], "not_reported": [], "settled": False}
    assert cache.accept_profile(json.dumps(base)) and cache.display_model is None  # older firmware
    sequence = cache.profile_sequence
    assert cache.accept_profile(json.dumps(base | {"display_model": OWNER})) and cache.display_model == OWNER
    assert cache.profile_sequence == sequence  # words only: no entity pass, no profile change
    for bad in ("Nefit HRC", "", 5, None, "x" * 64):
        assert cache.accept_profile(json.dumps(base | {"display_model": bad})) and cache.display_model is None
    assert cache.accept_profile(json.dumps(base | {"display_model": OWNER})) and cache.accept_profile("")
    assert cache.display_model is None


def group_two(code, cause):
    fields = []
    for i in range(20, 30):
        raw = wire(code) if i == DISPLAY_CODE else cause if i == SERVICE_NUMBER else 0
        fields.append([i, raw, 9000, QUALITIES[i], FIELDS[i][4]])
    return json.dumps({"schema": 1, "group": 2, "values": {"schema": 1, "sampled_at_ms": 10000,
                                                           "profile": "classic_observed", "fields": fields}})


def profile_doc(model):
    return json.dumps({"schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
                       "supported": [DISPLAY_CODE, SERVICE_NUMBER], "not_fitted": [], "not_reported": [],
                       "settled": False, **({"display_model": model} if model else {})})


@pytest.mark.asyncio
async def test_the_display_code_sensor_keeps_its_raw_state_and_gets_the_words(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = False
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/config/boiler_profile", profile_doc(None), retained=True)
    await c.receive("fw/state/boiler_fields/2", group_two("0C", 283), retained=True)
    r._notify()
    code = by_index(added)[DISPLAY_CODE]
    assert code.native_value == "0C"  # history and automations keep the raw code
    attrs = code.extra_state_attributes
    assert {k: attrs[k] for k in ("meaning", "severity", "cause", "code_table")} == {
        "meaning": "Preparing to start the burner", "severity": "normal", "cause": 283, "code_table": "ems-generic"}
    before = code.signature()
    # The owner chooses the EcomLine Classic on the E32: the same code reads as its own manual says.
    await c.receive("fw/config/boiler_profile", profile_doc(OWNER), retained=True)
    r._notify()
    assert code.native_value == "0C" and code.signature() != before
    assert code.extra_state_attributes["meaning"] == "Waiting for the 3-way valve to switch"
    assert code.extra_state_attributes["severity"] == "waiting"
    assert code.extra_state_attributes["code_table"] == OWNER
    # A fault: severity and advice; the service number itself is not a code with words.
    await c.receive("fw/state/boiler_fields/2", group_two("6A", 0), retained=True)
    r._notify()
    attrs = code.extra_state_attributes
    assert attrs["severity"] == "fault" and attrs["cause"] is None and attrs["advice"].startswith("Check that the gas tap")
    assert "meaning" not in by_index(added)[SERVICE_NUMBER].extra_state_attributes
    # Dutch Home Assistant: Dutch words (the entity is not added to a platform here).
    code.hass = hass
    hass.config.language = "nl"
    assert code.extra_state_attributes["meaning"] == "Geen vlam na het ontsteken"
    await r.async_stop()
