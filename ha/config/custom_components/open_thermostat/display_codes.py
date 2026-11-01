"""The boiler's display code in words: what it means, how serious it is and what to do.

The tables come from the boiler profiles (docs/modern-thermostat/boiler-profiles, compiled
into display_code_table.py by scripts/generate_display_codes.py) and follow the boiler model
chosen on the E32 (``display_model`` in fw/config/boiler_profile). A model without its own
table, or firmware that does not say, uses the generic EMS table (display code + cause
number). A model table can also list a cause number without a display code (the manual
shows the number only); it matches that number with any display code. A code the table
does not list stays the raw code with "unknown code, see your boiler manual": never a
guess from another boiler family.

Presentation only: the code sensor's state stays the raw code (history and automations keep
their meaning); the words are its attributes, in the Home Assistant language.
"""
import re

from .display_code_table import ADVICE, FALLBACK, GENERIC, LANGUAGES, MODELS, SEVERITIES, TABLES, UNKNOWN

FAULTS = frozenset({"blocking", "locking", "fault"})
CODE = re.compile(r"[-=0-9A-Za-z]{1,2}")
# A text code field and the number field that goes with it (boiler_fields.py names).
CODE_FIELDS = {"display_code": "service_number",
               "last_locking_error_code": "last_locking_error_number",
               "last_blocking_error_code": "last_blocking_error_number"}


def language_index(language):
    """English, Dutch or Polish; English for any other Home Assistant language."""
    base = str(language or "en").lower().replace("_", "-").split("-")[0]
    return LANGUAGES.index(base) if base in LANGUAGES else 0


def normalise(code):
    """"0H", "-H", "=H": the display's dots and padding are not part of the code; "--" is no code."""
    if type(code) is not str:
        return None
    raw = "".join(ch for ch in code if not ch.isspace() and ch != ".")
    return raw if CODE.fullmatch(raw) and raw != "--" else None


def describe(code, cause=None, model=None, language="en"):
    """{code, cause, known, table, severity, fault, meaning, advice, severity_text}; None without a code."""
    raw = normalise(code)
    if raw is None:
        return None
    number = cause if type(cause) is int and 0 < cause < 10000 else None
    i = language_index(language)
    table = MODELS.get(model, GENERIC) if type(model) is str else GENERIC
    while table is not None:
        rows = TABLES[table]
        hit = ((rows.get((raw, number)) or rows.get((None, number))) if number is not None else None)             or rows.get((raw, None))
        if hit:
            severity, advice, text = hit
            return {"code": raw, "cause": number, "known": True, "table": table, "severity": severity,
                    "fault": severity in FAULTS, "meaning": text[i], "advice": ADVICE[advice][i] if advice else None,
                    "severity_text": SEVERITIES[severity][i]}
        table = FALLBACK.get(table)
    return {"code": raw, "cause": number, "known": False, "table": None, "severity": "unknown", "fault": False,
            "meaning": UNKNOWN[i], "advice": None, "severity_text": SEVERITIES["unknown"][i]}


def attributes(description):
    """The entity attributes of a description (empty without a code)."""
    if description is None:
        return {}
    return {"meaning": description["meaning"], "severity": description["severity"],
            "severity_text": description["severity_text"], "advice": description["advice"],
            "cause": description["cause"], "code_table": description["table"]}
