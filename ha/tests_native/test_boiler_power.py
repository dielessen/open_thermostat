"""The suggested boiler power: gas meter calibration, the boiler, a known type, else the default; the user's value wins."""
import voluptuous as vol

from custom_components.open_thermostat import heating_advice as advice
from custom_components.open_thermostat.boiler_power import DEFAULT_KW, basis, product_kw, suggestion
from custom_components.open_thermostat.energy_input import CONF_BOILER_KW, energy_schema

CALIBRATED = {"status": "calibrated", "confidence": "high", "factor": 1.1, "kw_at_full_modulation": 24.27, "kw_source": "meter"}


def test_the_users_value_always_wins():
    assert suggestion({CONF_BOILER_KW: 28}, CALIBRATED, 30, "Nefit EcomLine HRC 22") == (28.0, "set")


def test_order_gas_meter_then_boiler_then_known_type_then_default():
    assert suggestion({}, CALIBRATED, 30, "Nefit EcomLine HRC 22") == (24.3, "gas_meter")
    collecting = {**CALIBRATED, "status": "collecting", "kw_source": "boiler_kw"}
    assert suggestion({}, collecting, 30, "Nefit EcomLine HRC 22") == (30.0, "boiler")
    assert suggestion({}, collecting, None, "Nefit EcomLine HRC 22") == (22.0, "product")
    assert suggestion({}, None, None, "EasyControl Adapter") == (DEFAULT_KW, "default")
    assert suggestion(None) == (DEFAULT_KW, "default")
    # Out-of-range or broken values are ignored, never suggested.
    assert suggestion({}, {**CALIBRATED, "kw_at_full_modulation": 500}, 0, None) == (DEFAULT_KW, "default")


def test_only_types_whose_power_is_in_the_name():
    assert product_kw("Nefit EcomLine HRC 30") == 30.0 and product_kw("EcomLine HR 22") == 22.0
    assert product_kw("Logamax Plus GB192") is None and product_kw(None) is None


def test_the_form_prefills_the_suggestion_only_while_nothing_is_set():
    def suggested(options, kw):
        for key in energy_schema(vol, options, "EUR", kw).schema:
            if str(key) == "boiler_kw":
                return (key.description or {}).get("suggested_value")
    assert suggested({}, 22.0) == 22.0
    assert suggested({CONF_BOILER_KW: 28}, 22.0) == 28  # the user's own value, as before
    assert suggested({}, None) is None


def test_basis_phrase_in_the_forms_language():
    assert basis("gas_meter", "nl") == "gemeten met je gasmeter"
    assert basis("default", "pl").startswith("wartość domyślna")
    assert basis("product", "de") == "known for this boiler type"  # unknown language: English


def test_advice_card_says_which_power_the_estimates_use():
    ctx = {"boiler_kw": None, "learning": True}
    item = advice.rule_boiler_power([], ctx)[0]
    assert item["id"] == "boiler_power_missing" and item["parts"] == ("default",)
    en = advice.render(item, "en")
    assert en["title"] == "Estimates use 22 kW boiler power"
    assert "default of 22 kW" in en["observed"]
    item = advice.rule_boiler_power([], {**ctx, "gas": CALIBRATED})[0]
    nl = advice.render(item, "nl")
    assert nl["title"].startswith("Schattingen gebruiken 24,3 kW") and "gemeten met je gasmeter" in nl["observed"]
    assert advice.rule_boiler_power([], {**ctx, "boiler_kw": 22}) == []  # set: no card


import pytest  # noqa: E402
from test_heating_advice import set_inputs  # noqa: E402
from test_product_flow import managers, option, product  # noqa: E402,F401


@pytest.mark.asyncio
async def test_house_energy_form_shows_and_prefills_the_suggestion(hass, managers):
    set_inputs(hass)
    _, m = managers
    p = product(hass)
    f = await option(m, p, "energy")
    assert f["description_placeholders"] == {"boiler_kw_suggested": "22", "boiler_kw_basis": "a default value: check the type plate"}
    boiler = next(key for key in f["data_schema"].schema if str(key) == "boiler_kw")
    assert boiler.description == {"suggested_value": 22.0}
