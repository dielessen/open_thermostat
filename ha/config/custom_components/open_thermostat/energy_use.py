"""Gas for heating and for hot water, as long-term statistics for the Home Assistant Energy dashboard.

Two sensors on the product device, "Gas for heating" and "Gas for hot water"
(state class ``total_increasing``), so Home Assistant keeps long-term
statistics and shows them per day, week and month in the Energy dashboard
(add them under "Gas consumption"). They appear once the E32 reports the
boiler's burner modulation and hot-water state (boiler fields); without that
there is nothing to split and no entity is created.

How the gas is counted (attribute ``method``):

* ``gas_meter``: with a gas meter in the energy options, the meter's real
  increase is shared out between heating and hot water by what the boiler did
  meanwhile (burner modulation, split by the boiler's hot-water state). Gas
  used while the burner was off the whole time (a gas stove) goes to neither.
  A meter that stays still for six hours while the boiler burns counts as
  broken: that stretch is estimated instead and the meter starts afresh.
* ``estimate``: without a meter, burner modulation x the boiler's power
  (energy options; else the E32's default of 22 kW) x time. Rough, and the
  attributes say so.

The unit follows the meter: kWh for a meter in Wh/kWh/MWh, m³ otherwise (and
without a meter). Per day the counts are kept for 15 days (heating, hot water,
other gas, burner time, hot-water taps and the night-setback saving the E32
estimates), in a small Home Assistant store; the weekly summary reads them.
Nothing here writes a setting.
"""
import math
import time
from datetime import date, datetime, timedelta, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .energy_input import (CONF_BOILER_KW, CONF_GAS_METER, ENERGY_UNITS, VOLUME_UNITS, BOILER_KW_LIMITS,
                           energy_options, kwh_per_m3)

SAMPLE_SECONDS = 10
# Two samples further apart than this are not one observation: nothing is counted in between.
MAX_STEP_SECONDS = 60
# A meter that does not move while the boiler burns this long is taken as broken.
METER_STALE_SECONDS = 6 * 3600
# A meter jump above max(2 m³, 10 m³ per hour since its last change) is a replaced or reset meter.
METER_JUMP_M3 = 2.0
METER_JUMP_M3_PER_HOUR = 10.0
DEFAULT_BOILER_KW = 22.0  # the E32's own default (FlowLearner::Params::nominalKw)
DAYS_KEPT = 15
SAVE_DELAY_SECONDS = 300
WRITE_SECONDS = 60
KINDS = ("heating", "hot_water")
METHODS = ("gas_meter", "estimate")
UNIT_M3, UNIT_KWH = UnitOfVolume.CUBIC_METERS, UnitOfEnergy.KILO_WATT_HOUR
STORE_VERSION = 1


def _float(value):
    if type(value) is bool:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _round(value, digits):
    value = round(value, digits)
    return int(value) if value == int(value) else value


def meter_reading(state, options):
    """(m³, kWh, unit family "m3"/"kwh") of a gas meter state, or None."""
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    value = _float(state.state)
    unit = state.attributes.get("unit_of_measurement")
    if value is None or value < 0:
        return None
    calorific = kwh_per_m3(options)
    if unit in VOLUME_UNITS:
        return value, value * calorific, "m3"
    if unit in ENERGY_UNITS:
        kwh = value * ENERGY_UNITS[unit]
        return kwh / calorific, kwh, "kwh"
    return None


def boiler_power(options, header=None):
    """(kW, known): the boiler power from the energy options, else what the E32 uses, else its default."""
    value = _float(options.get(CONF_BOILER_KW))
    if value is not None and BOILER_KW_LIMITS[0] <= value <= BOILER_KW_LIMITS[1]:
        return value, True
    from .heating_link import learned_inputs
    inputs = learned_inputs(header)
    value = _float(inputs.get("boiler_kw"))
    if value is not None and BOILER_KW_LIMITS[0] <= value <= BOILER_KW_LIMITS[1]:
        return value, inputs.get("boiler_kw_source") == "ha"
    return DEFAULT_BOILER_KW, False


def boiler_sample(client):
    """(modulation %, hot water) from the boiler fields, or None while either is unknown."""
    from .heating_advice import _either
    modulation = _either(client, ("reported_burner_modulation", "plus_burner_modulation"), 0, 100)
    hot_water = _either(client, ("dhw_active", "plus_dhw_valve"), 0, 1)
    if modulation is None or hot_water is None:
        return None
    return modulation, bool(hot_water)


def night_savings(hub):
    """{room id: (m³, money or None)} of tonight's night-setback estimate per room (0 when the program is best)."""
    from .heating_link import number
    result = {}
    for room_id, plan in (hub.warmup.items() if hub is not None and hub.fresh else ()):
        night = plan.get("night") if type(plan.get("night")) is dict else {}
        if night.get("reason") != "estimated":
            continue
        m3 = number(night.get("saving_m3"), 0, 100)
        if m3 is None:
            continue
        if night.get("recommended") in (None, "program"):
            m3 = 0.0
        money = number(night.get("saving_eur"), 0, 1000) if m3 else None
        result[room_id] = (m3, money)
    return result


def hot_water_taps(hub):
    """Today's hot-water taps as the E32 counts them, or None."""
    from .heating_link import _count, _dict
    dhw = hub.dhw if hub is not None and hub.fresh else None
    return _count(_dict(dhw["today"], "tapping").get("count")) if dhw is not None else None


def empty_day():
    return {"heating_m3": 0.0, "heating_kwh": 0.0, "hot_water_m3": 0.0, "hot_water_kwh": 0.0,
            "other_m3": 0.0, "heating_s": 0, "hot_water_s": 0, "observed_s": 0, "meter": False, "estimate": False}


def empty_data():
    return {"schema": 1, "created": False, "unit": UNIT_M3, "totals": {kind: 0.0 for kind in KINDS},
            "days": {}, "meter": None, "pending": {kind: 0.0 for kind in KINDS}, "pending_since": None}


def valid_data(value):
    """The stored data when it is a usable schema 1 document, else None."""
    if type(value) is not dict or value.get("schema") != 1 or value.get("unit") not in (UNIT_M3, UNIT_KWH):
        return None
    totals, days, pending = value.get("totals"), value.get("days"), value.get("pending")
    if type(totals) is not dict or type(days) is not dict or type(pending) is not dict:
        return None
    totals = {kind: _float(totals.get(kind)) for kind in KINDS}
    pending = {kind: _float(pending.get(kind)) for kind in KINDS}
    if any(item is None or item < 0 for item in (*totals.values(), *pending.values())):
        return None
    result = empty_data()
    result.update(created=value.get("created") is True, unit=value["unit"], totals=totals, pending=pending,
                  pending_since=_float(value.get("pending_since")))
    meter = value.get("meter")
    if (type(meter) is dict and type(meter.get("entity")) is str and meter.get("family") in ("m3", "kwh")
            and _float(meter.get("value")) is not None and _float(meter.get("at")) is not None):
        result["meter"] = {"entity": meter["entity"], "family": meter["family"], "value": float(meter["value"]),
                           "at": float(meter["at"])}
    for key, day in days.items():
        try:
            date.fromisoformat(key)
        except (TypeError, ValueError):
            continue
        if type(day) is not dict:
            continue
        clean = empty_day()
        for field, default in clean.items():
            item = day.get(field)
            if type(default) is bool:
                clean[field] = item is True
            elif (number := _float(item)) is not None and number >= 0:
                clean[field] = type(default)(number)
        taps = day.get("taps")
        if type(taps) is int and taps >= 0:
            clean["taps"] = taps
        nights = day.get("nights")
        if type(nights) is dict:
            clean["nights"] = {room: [_float(v[0]), _float(v[1])] for room, v in nights.items()
                               if type(room) is str and type(v) is list and len(v) == 2
                               and _float(v[0]) is not None and _float(v[0]) >= 0}
        result["days"][key] = clean
    for key in sorted(result["days"])[:-DAYS_KEPT]:
        del result["days"][key]
    return result


class EnergyUse:
    """Counts the boiler's gas for heating and for hot water; owns the two sensors and their store."""

    def __init__(self, hass, entry, hub, connection, clock=time.time, local_date=None, store=None):
        self.hass, self.entry, self.hub, self.connection, self.clock = hass, entry, hub, connection, clock
        self._local_date = local_date
        self.store = store if store is not None else Store(hass, STORE_VERSION,
                                                           f"{DOMAIN}.energy_use.{entry.entry_id}")
        self.data = empty_data()
        self.sensors = []
        self._add = None
        self._previous = None  # (time, modulation %, hot water, kW) of the last usable sample
        self._written = None
        self._dirty = False

    # -- time ------------------------------------------------------------------

    def today(self, now=None):
        now = self.clock() if now is None else now
        if self._local_date is not None:
            return self._local_date(now)
        from homeassistant.util import dt as dt_util
        return dt_util.as_local(datetime.fromtimestamp(now, timezone.utc)).date()

    def day(self, now=None):
        days = self.data["days"]
        key = self.today(now).isoformat()
        if key not in days:
            days[key] = empty_day()
            for old in sorted(days)[:-DAYS_KEPT]:
                del days[old]
        return days[key]

    # -- what is configured ---------------------------------------------------

    @property
    def options(self):
        return energy_options(self.entry)

    @property
    def unit(self):
        return self.data["unit"]

    @property
    def method(self):
        return "gas_meter" if self.options.get(CONF_GAS_METER) else "estimate"

    def power(self):
        header = self.hub.learned_header if self.hub is not None and self.hub.fresh else None
        return boiler_power(self.options, header)

    # -- counting ----------------------------------------------------------------

    def _add_gas(self, kind, m3, kwh, method, now):
        if m3 <= 0 and kwh <= 0:
            return
        self.data["totals"][kind] += kwh if self.unit == UNIT_KWH else m3
        day = self.day(now)
        day[f"{kind}_m3"] += m3
        day[f"{kind}_kwh"] += kwh
        day["meter" if method == "gas_meter" else "estimate"] = True
        self._dirty = True

    def _set_unit(self, unit):
        """The meter's unit family changed: convert the totals once (Home Assistant then asks to fix the statistics)."""
        if unit == self.unit:
            return
        calorific = kwh_per_m3(self.options)
        factor = calorific if unit == UNIT_KWH else 1 / calorific
        self.data["totals"] = {kind: value * factor for kind, value in self.data["totals"].items()}
        self.data["unit"] = unit
        self._dirty = True

    def _flush_pending(self, now):
        """Count what waits for the meter as an estimate (a broken meter, or no meter any more)."""
        calorific = kwh_per_m3(self.options)
        for kind in KINDS:
            kwh = self.data["pending"][kind]
            self._add_gas(kind, kwh / calorific, kwh, "estimate", now)
        self.data["pending"] = {kind: 0.0 for kind in KINDS}
        self.data["pending_since"] = None

    def _integrate(self, now, sample):
        """Count the previous sample's burner power over the time since then."""
        previous = self._previous
        if sample is not None:
            kw, _ = self.power()
            self._previous = (now, sample[0], sample[1], kw)
        else:
            self._previous = None
        if previous is None:
            return
        at, modulation, hot_water, kw = previous
        seconds = now - at
        if not 0 < seconds <= MAX_STEP_SECONDS:
            return
        kind = "hot_water" if hot_water else "heating"
        day = self.day(now)
        day["observed_s"] += round(seconds)
        if modulation <= 0:
            self._dirty = True
            return
        day[f"{kind}_s"] += round(seconds)
        kwh = modulation / 100 * kw * seconds / 3600
        if self.method == "gas_meter":
            if self.data["pending_since"] is None:
                self.data["pending_since"] = at
            self.data["pending"][kind] += kwh
            self._dirty = True
        else:
            self._add_gas(kind, kwh / kwh_per_m3(self.options), kwh, "estimate", now)

    def _follow_meter(self, now):
        """Share each real meter increase out between heating and hot water."""
        options = self.options
        entity = options.get(CONF_GAS_METER)
        if not entity:
            if self.data["meter"] is not None or any(self.data["pending"].values()):
                self._flush_pending(now)
                self.data["meter"] = None
                self._dirty = True
            return
        reading = meter_reading(self.hass.states.get(entity), options)
        pending = self.data["pending"]
        since = self.data["pending_since"]
        if since is not None and now - since > METER_STALE_SECONDS:
            self._flush_pending(now)
            self.data["meter"] = None  # start afresh: the stretch just estimated is not counted twice
        if reading is None:
            return
        m3, kwh, family = reading
        self._set_unit(UNIT_KWH if family == "kwh" else UNIT_M3)
        value = kwh if family == "kwh" else m3
        meter = self.data["meter"]
        if meter is None or meter["entity"] != entity or meter["family"] != family or value < meter["value"]:
            if meter is not None and meter["entity"] != entity:
                self._flush_pending(now)
            self.data["meter"] = {"entity": entity, "family": family, "value": value, "at": now}
            self._dirty = True
            return
        if value == meter["value"]:
            return
        calorific = kwh_per_m3(options)
        delta = value - meter["value"]
        delta_m3, delta_kwh = (delta / calorific, delta) if family == "kwh" else (delta, delta * calorific)
        hours = max(0.0, now - meter["at"]) / 3600
        self.data["meter"] = {"entity": entity, "family": family, "value": value, "at": now}
        self._dirty = True
        if delta_m3 > max(METER_JUMP_M3, hours * METER_JUMP_M3_PER_HOUR):
            return  # a replaced or reset meter: no gas counted for the jump
        total = sum(pending.values())
        if total <= 0:
            self.day(now)["other_m3"] += delta_m3  # the burner was off: another appliance
        else:
            for kind in KINDS:
                share = pending[kind] / total
                self._add_gas(kind, delta_m3 * share, delta_kwh * share, "gas_meter", now)
        self.data["pending"] = {kind: 0.0 for kind in KINDS}
        self.data["pending_since"] = None

    def _note_day(self, now):
        day = self.day(now)
        taps = hot_water_taps(self.hub)
        if taps is not None and taps > day.get("taps", -1):
            day["taps"] = taps
            self._dirty = True
        nights = night_savings(self.hub)
        if nights:
            stored = day.setdefault("nights", {})
            for room_id, (m3, money) in nights.items():
                if stored.get(room_id) != [m3, money]:
                    stored[room_id] = [m3, money]
                    self._dirty = True

    @callback
    def tick(self, _now=None):
        now = self.clock()
        sample = boiler_sample(getattr(self.connection, "client", None))
        self._integrate(now, sample)
        self._follow_meter(now)
        self._note_day(now)
        if sample is not None and not self.data["created"]:
            self.data["created"] = True
            self._dirty = True
            self._create_sensors()
        if self._dirty:
            self._dirty = False
            self.store.async_delay_save(lambda: self.data, SAVE_DELAY_SECONDS)
            if self._written is None or now - self._written >= WRITE_SECONDS:
                self._write(now)

    def _write(self, now):
        self._written = now
        for sensor in self.sensors:
            if sensor.added:  # never a removed or disabled sensor (it keeps its hass)
                sensor.async_write_ha_state()

    @callback
    def _create_sensors(self):
        if self._add is None or self.sensors:
            return
        self.sensors = [GasUseSensor(self, kind) for kind in KINDS]
        self._add(self.sensors)

    # -- reading back ---------------------------------------------------------------

    def window(self, end, days):
        """The day records of ``days`` calendar days ending with ``end`` (missing days left out)."""
        keys = {date.fromordinal(end.toordinal() - i).isoformat() for i in range(days)}
        return [day for key, day in self.data["days"].items() if key in keys]

    def attributes(self, kind):
        today = self.today()
        days = self.window(today, 7)
        current = self.data["days"].get(today.isoformat(), empty_day())
        boiler = sum(day["heating_m3"] + day["hot_water_m3"] for day in days)
        mine = sum(day[f"{kind}_m3"] for day in days)
        in_kwh = self.unit == UNIT_KWH
        key = f"{kind}_kwh" if in_kwh else f"{kind}_m3"
        _, known = self.power()
        method = self.method
        return {"method": method, "estimate": method == "estimate",
                "rough": method == "estimate" and not known,
                "today": _round(current[key], 3), "last_7_days": _round(sum(day[key] for day in days), 3),
                "today_kwh": _round(current[f"{kind}_kwh"], 2),
                "last_7_days_kwh": _round(sum(day[f"{kind}_kwh"] for day in days), 2),
                "share_last_7_days": _round(100 * mine / boiler, 0) if boiler > 0 else None,
                "burner_hours_last_7_days": _round(sum(day[f"{kind}_s"] for day in days) / 3600, 1)}

    def diagnostics(self):
        days = {key: {field: (_round(value, 3) if type(value) is float else value)
                      for field, value in day.items() if field != "nights"}
                for key, day in sorted(self.data["days"].items())}
        kw, known = self.power()
        return {"created": self.data["created"], "method": self.method, "unit": self.unit,
                "totals": {kind: _round(value, 3) for kind, value in self.data["totals"].items()},
                "pending_kwh": {kind: _round(value, 3) for kind, value in self.data["pending"].items()},
                "meter_seen": self.data["meter"] is not None, "boiler_kw": kw, "boiler_kw_known": known,
                "boiler_sample": boiler_sample(getattr(self.connection, "client", None)) is not None,
                "days": days}

    # -- life cycle -----------------------------------------------------------

    async def async_start(self, add_entities):
        self._add = add_entities
        stored = valid_data(await self.store.async_load())
        if stored is not None:
            self.data = stored
        if self.data["created"]:
            self._create_sensors()
        self.entry.async_on_unload(async_track_time_interval(self.hass, self.tick,
                                                             timedelta(seconds=SAMPLE_SECONDS)))
        self.entry.async_on_unload(self.stop)

    def stop(self):
        """Save now; Home Assistant awaits the returned save before the entry is set up again (a reload)."""
        return self.store.async_save(self.data)


class GasUseSensor(RestoreEntity, SensorEntity):
    """The boiler's gas for heating or for hot water since counting began (total_increasing)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    # The day and week figures change with every count; the history keeps the total.
    _unrecorded_attributes = frozenset({"today", "last_7_days", "today_kwh", "last_7_days_kwh",
                                        "share_last_7_days", "burner_hours_last_7_days"})

    def __init__(self, use, kind):
        self.use, self.kind = use, kind
        self.added = False  # in Home Assistant now (added, not removed or disabled)
        prefix = use.hub.prefix
        self._attr_unique_id = f"{prefix}_hub_{kind}_gas"
        self._attr_translation_key = f"{kind}_gas"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})

    @property
    def native_unit_of_measurement(self):
        return self.use.unit

    @property
    def device_class(self):
        return SensorDeviceClass.ENERGY if self.use.unit == UNIT_KWH else SensorDeviceClass.GAS

    @property
    def suggested_display_precision(self):
        return 1 if self.use.unit == UNIT_KWH else 2

    @property
    def native_value(self):
        return _round(self.use.data["totals"][self.kind], 3)

    @property
    def extra_state_attributes(self):
        return self.use.attributes(self.kind)

    async def async_added_to_hass(self):
        """A total never goes down (Home Assistant would count a decrease as a new meter): at least the last state."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        value = _float(last.state) if last is not None else None
        if (value is not None and last.attributes.get("unit_of_measurement") == self.use.unit
                and value > self.use.data["totals"][self.kind]):
            self.use.data["totals"][self.kind] = value
        self.added = True

    async def async_will_remove_from_hass(self):
        self.added = False
        await super().async_will_remove_from_hass()


async def async_setup_energy_use(hass, entry, async_add_entities, options, hub, connection):
    """Product entries: count the gas; the two sensors appear once the boiler reports its modulation."""
    use = EnergyUse(hass, entry, hub, connection)
    hass.data[DOMAIN][entry.entry_id]["energy_use"] = use
    await use.async_start(lambda entities: async_add_entities(entities, **options))
    return use
