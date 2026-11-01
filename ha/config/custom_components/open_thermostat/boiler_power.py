"""A suggested boiler power, so the heat and gas estimates work before anyone types one in.

The power the user entered (House → Energy) always wins and is not a suggestion. Without it, in this order:

* ``gas_meter``: the E32's own calibration against the gas meter (``learned.gas``,
  ``kw_at_full_modulation`` with ``kw_source`` "meter"): measured in this house;
* ``boiler``: the nominal power the boiler itself reports, where its EMS profile has one;
* ``product``: a known boiler type (a small table, only types whose power is certain);
* ``default``: the E32's default of 22 kW, a guess (``FlowLearner::Params::nominalKw``).

Nothing here writes a setting: the form names the suggestion and its basis in the field's description; only a
power the user types in is stored.
"""
from __future__ import annotations

import re

from .energy_input import BOILER_KW_LIMITS, CONF_BOILER_KW

DEFAULT_KW = 22.0
SOURCES = ("set", "gas_meter", "boiler", "product", "default")
# Only types whose nominal heating power is in the name and certain; the E32 may only know a product group.
KNOWN_PRODUCTS = (
    (re.compile(r"\bEcomLine\b.*\bHRC?\s*22\b", re.I), 22.0),
    (re.compile(r"\bEcomLine\b.*\bHRC?\s*30\b", re.I), 30.0),
    (re.compile(r"\bEcomLine\b.*\bHRC?\s*43\b", re.I), 43.0),
)
# The word after the number in the House → Energy form, per language (the rest of the sentence is translated).
BASIS = {
    "en": {"gas_meter": "measured with your gas meter", "boiler": "reported by the boiler",
           "product": "known for this boiler type", "default": "a default value: check the type plate"},
    "nl": {"gas_meter": "gemeten met je gasmeter", "boiler": "gemeld door de ketel",
           "product": "bekend voor dit keteltype", "default": "een standaardwaarde: controleer het typeplaatje"},
    "pl": {"gas_meter": "zmierzona licznikiem gazu", "boiler": "zgłoszona przez kocioł",
           "product": "znana dla tego typu kotła", "default": "wartość domyślna: sprawdź tabliczkę znamionową"},
}


def _kw(value):
    try:
        kw = float(value)
    except (TypeError, ValueError):
        return None
    return kw if BOILER_KW_LIMITS[0] <= kw <= BOILER_KW_LIMITS[1] else None


def product_kw(model):
    """The nominal power of a known boiler type from its model name, or None."""
    if type(model) is not str:
        return None
    return next((kw for pattern, kw in KNOWN_PRODUCTS if pattern.search(model)), None)


def suggestion(options, gas=None, nominal_kw=None, model=None):
    """(kW, source) with source one of SOURCES.

    options: the entry options; gas: the learner's gas calibration (``learned.gas``); nominal_kw: the boiler's
    own reported power; model: the boiler's model name, when the E32 knows it.
    """
    own = _kw((options or {}).get(CONF_BOILER_KW))
    if own is not None:
        return own, "set"
    if type(gas) is dict and gas.get("kw_source") == "meter" and gas.get("status") == "calibrated":
        measured = _kw(gas.get("kw_at_full_modulation"))
        if measured is not None:
            return round(measured, 1), "gas_meter"
    reported = _kw(nominal_kw)
    if reported is not None:
        return reported, "boiler"
    known = product_kw(model)
    if known is not None:
        return known, "product"
    return DEFAULT_KW, "default"


def basis(source, language, model=None):
    """The short phrase that says where a suggestion comes from, in the form's language.

    model: the detected boiler type, named after "known for this boiler type".
    """
    words = BASIS.get((language or "en").split("-")[0], BASIS["en"])
    phrase = words.get(source, words["default"])
    return f"{phrase}: {model}" if source == "product" and model else phrase


def detected_model(hass, entry):
    """The boiler type as the E32's EMS bus list names it (its device at 0x08), or None."""
    from homeassistant.helpers import device_registry as dr
    from .const import CONF_TOPIC_PREFIX, DOMAIN
    prefix = entry.data.get(CONF_TOPIC_PREFIX)
    device = (dr.async_get(hass).async_get_device_by_identifier((DOMAIN, f"{prefix}_ems_08"), entry.entry_id)
              if prefix else None)
    if device is None:
        return None
    if device.name:
        return re.sub(r"\s*\(0x08\)$", "", device.name)
    return device.model
