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
    assert product_kw("Nefit Ecomline Classic HRC 22H") == 22.0  # the catalog name of the chosen model
    assert product_kw("Logamax Plus GB192") is None and product_kw(None) is None


def test_the_form_prefills_only_a_power_the_user_stored():
    def suggested(options):
        for key in energy_schema(vol, options, "EUR").schema:
            if str(key) == "boiler_kw":
                return (key.description or {}).get("suggested_value")
    assert suggested({}) is None                         # a suggestion is never saved by an unrelated change
    assert suggested({CONF_BOILER_KW: 28}) == 28         # the user's own value, as before


def test_basis_phrase_in_the_forms_language():
    assert basis("gas_meter", "nl") == "gemeten met je gasmeter"
    assert basis("default", "pl").startswith("wartość domyślna")
    assert basis("product", "de") == "known for this boiler type"  # unknown language: English
    assert basis("product", "nl", "Nefit EcomLine HRC 22") == "bekend voor dit keteltype: Nefit EcomLine HRC 22"
    assert basis("default", "en", "EasyControl Adapter") == "a default value: check the type plate"


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
from nav_helpers import is_again  # noqa: E402
from test_product_flow import managers, option, product  # noqa: E402,F401


@pytest.mark.asyncio
async def test_house_energy_form_names_the_suggestion_and_saves_it_only_when_typed(hass, managers):
    from homeassistant.helpers import device_registry as dr
    set_inputs(hass)
    _, m = managers
    p = product(hass)
    f = await option(m, p, "energy")
    assert f["description_placeholders"] == {"boiler_kw_suggested": "22", "boiler_kw_basis": "a default value: check the type plate"}
    boiler = next(key for key in f["data_schema"].schema if str(key) == "boiler_kw")
    assert boiler.description is None                    # not prefilled: saving the form leaves it unset
    result = await m.async_configure(f["flow_id"], {})
    assert is_again(result) and CONF_BOILER_KW not in p.options
    # The boiler type from the E32's EMS bus list (ems_devices), named in the description.
    dr.async_get(hass).async_get_or_create(config_entry_id=p.entry_id, identifiers={("open_thermostat", "fixture_ems_08")},
                                           name="Nefit EcomLine HRC 30 (0x08)", model="EcomLine")
    f = await option(m, p, "energy")
    assert f["description_placeholders"] == {"boiler_kw_suggested": "30",
                                              "boiler_kw_basis": "known for this boiler type: Nefit EcomLine HRC 30"}
    result = await m.async_configure(f["flow_id"], {"boiler_kw": 24})
    assert p.options[CONF_BOILER_KW] == 24
    boiler = next(key for key in (await option(m, p, "energy"))["data_schema"].schema if str(key) == "boiler_kw")
    assert boiler.description == {"suggested_value": 24}  # a stored value stays prefilled
