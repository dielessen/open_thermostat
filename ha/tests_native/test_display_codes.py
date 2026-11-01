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


def wire(code):
    return ord(code[0]) << 8 | ord(code[1])


def test_the_generated_table_matches_the_boiler_profiles():
    subprocess.run([sys.executable, "scripts/generate_display_codes.py", "--check"], cwd=ROOT, check=True)
    assert GENERIC == "ems-generic" and FALLBACK[OWNER] is None
    # Both selections of the owner's family use its own table; no other model claims one.
    assert MODELS == {"nefit-ecomline-classic": OWNER, OWNER: OWNER}


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
    # 0C and 2F mean different things on Classic and newer boilers: no code-only guess.
    for code in ("0C", "2F", "3C", "7H"):
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
        for (code, cause), (severity, advice, text) in rows.items():
            assert normalise(code) == code and len(text) == 3 and all(text), (name, code, cause)
            assert describe(code, cause, next((m for m, t in MODELS.items() if t == name), None))["table"] == name


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
