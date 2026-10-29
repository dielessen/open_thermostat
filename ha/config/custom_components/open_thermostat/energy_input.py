"""Optional energy inputs: gas meter, gas price, calorific value, outdoor temperature and boiler power.

Nothing here is required. A house without a gas meter, price sensor or
outdoor sensor works as before; the E32 then uses its own defaults, its
estimates are rough, and the heating advice says what is missing.

The configured values go to the E32 over the existing room route
``<base>ha/heating_input`` as typed payloads, on every change and every five
minutes (with the room inputs' refresh)::

    {"kind": "gas_m3", "entity": "sensor.gas", "value": 1234.567}
    {"kind": "gas_price", "value": 1.32}                      (+ "entity" for a sensor)
    {"kind": "gas_kwh_per_m3", "value": 9.77}
    {"kind": "outdoor_c", "entity": "sensor.outside", "value": 7.4}
    {"kind": "boiler_kw", "value": 22}

A gas meter in kWh (Wh, MWh) is converted to m³ with the calorific value
before it is sent (always ``gas_m3``); a price per kWh likewise becomes a
price per m³. The price is in Home Assistant's own currency. The room payloads
({"entity","temperature","target"}) have no ``kind`` and are unchanged.
Options are stored in the entry options; saving only these keys does not
reload the integration (see ``__init__._async_options_updated``).
"""
import json
import math

from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

CONF_GAS_METER = "energy_gas_meter"
CONF_GAS_PRICE_ENTITY = "energy_gas_price_entity"
CONF_GAS_PRICE = "energy_gas_price"
CONF_GAS_KWH_PER_M3 = "energy_gas_kwh_per_m3"
CONF_OUTDOOR = "energy_outdoor_entity"
CONF_BOILER_KW = "energy_boiler_kw"
ENERGY_KEYS = (CONF_GAS_METER, CONF_GAS_PRICE_ENTITY, CONF_GAS_PRICE, CONF_GAS_KWH_PER_M3, CONF_OUTDOOR,
               CONF_BOILER_KW)
# Form field -> option key (short field names read better in the translations).
FIELDS = {"gas_meter": CONF_GAS_METER, "gas_price_entity": CONF_GAS_PRICE_ENTITY, "gas_price": CONF_GAS_PRICE,
          "gas_kwh_per_m3": CONF_GAS_KWH_PER_M3, "outdoor_entity": CONF_OUTDOOR, "boiler_kw": CONF_BOILER_KW}

# Meter units: m³ as such, energy units converted with the calorific value.
VOLUME_UNITS = ("m³", "m3")
ENERGY_UNITS = {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}
GAS_STATE_CLASSES = ("total", "total_increasing")
# The E32's default (NL gas, upper value); natural gas is roughly 8–12 kWh/m³.
DEFAULT_GAS_KWH_PER_M3 = 9.77
GAS_KWH_PER_M3_LIMITS = (5.0, 15.0)
PRICE_LIMITS = (0.0001, 1000.0)   # per m³ or per kWh, in any currency
BOILER_KW_LIMITS = (3.0, 60.0)
OUTDOOR_LIMITS = (-50.0, 60.0)    # °C
# The flag the options flow sets just before saving only these keys.
ENERGY_ONLY_UPDATE = "energy_only_options"


class EnergyError(ValueError):
    """One invalid form field: ``field`` and the translated error ``code``."""

    def __init__(self, field, code):
        super().__init__(code)
        self.field, self.code = field, code


def _float(value):
    if type(value) is bool:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _rounded(value, digits):
    value = round(value, digits)
    return int(value) if value == int(value) else value


def _unit(state):
    return state.attributes.get("unit_of_measurement") if state is not None else None


def price_basis(unit):
    """'m3' or 'kwh' for a currency per m³ / per kWh unit (EUR/m³, £/kWh ...), else None."""
    if type(unit) is not str:
        return None
    unit = unit.replace(" ", "").lower()
    return "m3" if unit.endswith(("/m³", "/m3")) else "kwh" if unit.endswith("/kwh") else None


def outdoor_celsius(state):
    """The outdoor temperature in °C of a temperature sensor or a weather entity, or None."""
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    if state.domain == "weather":
        value, unit = _float(state.attributes.get("temperature")), state.attributes.get("temperature_unit", "°C")
    else:
        value, unit = _float(state.state), _unit(state)
    if value is None:
        return None
    if unit == "°F":
        value = (value - 32) * 5 / 9
    elif unit != "°C":
        return None
    return value if OUTDOOR_LIMITS[0] <= value <= OUTDOOR_LIMITS[1] else None


# -- validation (the options flow) ---------------------------------------------


def _check_gas_meter(state):
    if state is None:
        raise EnergyError("gas_meter", "entity_not_found")
    unit = _unit(state)
    if state.domain != "sensor" or not (unit in VOLUME_UNITS or (
            unit in ENERGY_UNITS and state.attributes.get("device_class") in ("gas", "energy"))):
        raise EnergyError("gas_meter", "gas_meter_unit")
    if state.attributes.get("state_class") not in GAS_STATE_CLASSES:
        raise EnergyError("gas_meter", "gas_meter_not_total")


def _check_price_entity(state):
    if state is None:
        raise EnergyError("gas_price_entity", "entity_not_found")
    if state.domain not in ("sensor", "input_number") or price_basis(_unit(state)) is None:
        raise EnergyError("gas_price_entity", "gas_price_unit")
    value = _float(state.state)
    if state.state not in ("unavailable", "unknown") and (
            value is None or not PRICE_LIMITS[0] <= value <= PRICE_LIMITS[1]):
        raise EnergyError("gas_price_entity", "gas_price_invalid")


def _check_outdoor(state):
    if state is None:
        raise EnergyError("outdoor_entity", "entity_not_found")
    if state.domain == "weather":
        if _float(state.attributes.get("temperature")) is None or state.attributes.get(
                "temperature_unit", "°C") not in ("°C", "°F"):
            raise EnergyError("outdoor_entity", "outdoor_unit")
    elif state.domain != "sensor" or _unit(state) not in ("°C", "°F"):
        raise EnergyError("outdoor_entity", "outdoor_unit")


def _number(values, key, field, limits, code, digits):
    if key in values:
        value = _float(values[key])
        if value is None or not limits[0] <= value <= limits[1]:
            raise EnergyError(field, code)
        values[key] = _rounded(value, digits)


def validate_energy(hass, user_input):
    """The energy options from a submitted form: {option key: value}, only what was filled in.

    Raises EnergyError for the first invalid field.
    """
    values = {key: user_input.get(field) for field, key in FIELDS.items()}
    values = {key: value for key, value in values.items() if value not in (None, "")}
    if CONF_GAS_METER in values:
        _check_gas_meter(hass.states.get(values[CONF_GAS_METER]))
    if CONF_GAS_PRICE_ENTITY in values and CONF_GAS_PRICE in values:
        raise EnergyError("gas_price", "gas_price_twice")
    if CONF_GAS_PRICE_ENTITY in values:
        _check_price_entity(hass.states.get(values[CONF_GAS_PRICE_ENTITY]))
    _number(values, CONF_GAS_PRICE, "gas_price", PRICE_LIMITS, "gas_price_invalid", 4)
    _number(values, CONF_GAS_KWH_PER_M3, "gas_kwh_per_m3", GAS_KWH_PER_M3_LIMITS, "gas_kwh_per_m3_invalid", 3)
    if CONF_OUTDOOR in values:
        _check_outdoor(hass.states.get(values[CONF_OUTDOOR]))
    _number(values, CONF_BOILER_KW, "boiler_kw", BOILER_KW_LIMITS, "boiler_kw_invalid", 1)
    return values


def currency(hass):
    value = getattr(hass.config, "currency", None)
    return value if type(value) is str and value else "EUR"


def energy_schema(vol, options, currency_code="EUR"):
    """The form: every field optional, prefilled (as a suggestion, so it can be cleared)."""
    def optional(field):
        current = options.get(FIELDS[field])
        return vol.Optional(field, description={"suggested_value": current}) if current is not None else vol.Optional(field)

    def number(low, high, step, unit):
        return selector.NumberSelector({"min": low, "max": high, "step": step, "mode": "box",
                                        "unit_of_measurement": unit})
    return vol.Schema({
        optional("gas_meter"): selector.EntitySelector({"filter": [{"domain": "sensor"}]}),
        optional("gas_price_entity"): selector.EntitySelector({"filter": [{"domain": "sensor"},
                                                                           {"domain": "input_number"}]}),
        optional("gas_price"): number(0, PRICE_LIMITS[1], "any", f"{currency_code}/m³"),
        optional("gas_kwh_per_m3"): number(GAS_KWH_PER_M3_LIMITS[0], GAS_KWH_PER_M3_LIMITS[1], 0.01, "kWh/m³"),
        optional("outdoor_entity"): selector.EntitySelector({"filter": [
            {"domain": "sensor", "device_class": "temperature"}, {"domain": "weather"}]}),
        optional("boiler_kw"): number(BOILER_KW_LIMITS[0], BOILER_KW_LIMITS[1], 0.1, "kW"),
    })


@callback
def save_energy(hass, entry, values):
    """Replace the energy keys of the entry options; the other options stay as they are."""
    options = {key: value for key, value in entry.options.items() if key not in ENERGY_KEYS}
    options.update(values)
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if options == dict(entry.options):
        return False
    if state is not None:
        # Only energy keys changed: the update listener refreshes instead of reloading.
        state[ENERGY_ONLY_UPDATE] = dict(options)
    hass.config_entries.async_update_entry(entry, options=options)
    return True


def energy_only_update(state, entry):
    """True (once) when the last options change was a save of the energy step alone."""
    pending = state.pop(ENERGY_ONLY_UPDATE, None) if state is not None else None
    return pending is not None and pending == dict(entry.options)


# -- configuration as the advice reads it -------------------------------------


def energy_options(entry):
    options = getattr(entry, "options", None) or {}
    return {key: options[key] for key in ENERGY_KEYS if options.get(key) not in (None, "")}


def kwh_per_m3(options):
    value = _float(options.get(CONF_GAS_KWH_PER_M3))
    return value if value is not None and GAS_KWH_PER_M3_LIMITS[0] <= value <= GAS_KWH_PER_M3_LIMITS[1] \
        else DEFAULT_GAS_KWH_PER_M3


def gas_price(hass, options):
    """The configured gas price per m³ (sensor per m³ or per kWh, or fixed), or None."""
    if CONF_GAS_PRICE_ENTITY in options:
        state = hass.states.get(options[CONF_GAS_PRICE_ENTITY])
        value = _float(state.state) if state is not None else None
        basis = price_basis(_unit(state))
        if value is None or basis is None or not PRICE_LIMITS[0] <= value <= PRICE_LIMITS[1]:
            return None
        return value * kwh_per_m3(options) if basis == "kwh" else value
    value = _float(options.get(CONF_GAS_PRICE))
    return value if value is not None and PRICE_LIMITS[0] <= value <= PRICE_LIMITS[1] else None


def gas_m3(state, options):
    """A gas meter reading in m³ (an energy meter converted with the calorific value), or None."""
    value = _float(state.state) if state is not None else None
    if value is None or value < 0:
        return None
    unit = _unit(state)
    if unit in VOLUME_UNITS:
        return value
    if unit in ENERGY_UNITS:
        return value * ENERGY_UNITS[unit] / kwh_per_m3(options)
    return None


# -- forwarding to the E32 -----------------------------------------------------


def energy_payloads(hass, options, only=None):
    """The typed heating_input payloads (dicts) for the configured values that have a valid reading.

    ``only``: limit to the payloads of this one entity (a state change).
    """
    payloads = []
    meter = options.get(CONF_GAS_METER)
    if meter and only in (None, meter):
        value = gas_m3(hass.states.get(meter), options)
        if value is not None:
            payloads.append({"kind": "gas_m3", "entity": meter, "value": _rounded(value, 3)})
    price_entity = options.get(CONF_GAS_PRICE_ENTITY)
    if price_entity and only in (None, price_entity):
        value = gas_price(hass, options)
        if value is not None:
            payloads.append({"kind": "gas_price", "entity": price_entity, "value": _rounded(value, 4)})
    elif CONF_GAS_PRICE in options and only is None and (value := gas_price(hass, options)) is not None:
        payloads.append({"kind": "gas_price", "value": _rounded(value, 4)})
    if CONF_GAS_KWH_PER_M3 in options and only is None:
        payloads.append({"kind": "gas_kwh_per_m3", "value": _rounded(kwh_per_m3(options), 3)})
    outdoor = options.get(CONF_OUTDOOR)
    if outdoor and only in (None, outdoor):
        value = outdoor_celsius(hass.states.get(outdoor))
        if value is not None:
            payloads.append({"kind": "outdoor_c", "entity": outdoor, "value": _rounded(value, 1)})
    power = _float(options.get(CONF_BOILER_KW))
    if power is not None and only is None and BOILER_KW_LIMITS[0] <= power <= BOILER_KW_LIMITS[1]:
        payloads.append({"kind": "boiler_kw", "value": _rounded(power, 1)})
    return payloads


class EnergyForwarder:
    """Sends the configured energy values to the E32: on each change and with the room inputs' refresh.

    ``track_state`` is Home Assistant's state-change tracker (passed in by the
    heating route, which also calls ``publish`` every five minutes).
    """

    def __init__(self, hass, entry, send, track_state=async_track_state_change_event):
        self.hass, self.entry, self.send, self.track_state = hass, entry, send, track_state
        self._unsubscribe = None

    @property
    def options(self):
        return energy_options(self.entry)

    def entities(self):
        options = self.options
        return [options[key] for key in (CONF_GAS_METER, CONF_GAS_PRICE_ENTITY, CONF_OUTDOOR) if key in options]

    @callback
    def publish(self, only=None):
        for payload in energy_payloads(self.hass, self.options, only):
            self.send(json.dumps(payload))

    @callback
    def _changed(self, event):
        self.publish(event.data["entity_id"])

    @callback
    def reconfigure(self):
        """Follow new options (also without a reload) and send them at once."""
        self.stop()
        entities = self.entities()
        if entities:
            self._unsubscribe = self.track_state(self.hass, entities, self._changed)
        self.publish()

    @callback
    def stop(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
