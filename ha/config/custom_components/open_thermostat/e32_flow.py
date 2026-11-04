"""The E32's flow temperature options and what they do (E32 beta.19, ``src/control/FlowPolicy.h``).

Controls on the product device (configuration), read and written over the
stored controller connection (``GET/POST /config/heating/flow``, one field per
change), the same login and lock as the room plan:

- switch "Follow outdoor temperature (heating curve)" (``weather_curve``; on by
  default since E32 rc.3): the flow follows the outdoor temperature, the room
  correction on top; a standard curve until the E32 learned the house's own,
  the room control alone without a fresh outdoor temperature;
- switch "Smart warm-up" (``apply_learned``; on by default since E32 rc.3: a
  time in the week program means "warm at that time"): it starts early enough
  for the next program step, with the lowest flow that is still in time; off,
  heating starts at the program time and the E32 only advises. The entity keeps
  its unique ID (and entity ID) of "Use learned flow and optimum start": the
  meaning is the same, only the name and the default changed;
- number "Flow at −10 °C" (``curve_design_flow_c``): 0 is automatic (floor
  heating 40 °C, radiators 55 °C), else 25–80 °C.

The options are static: they are read when the E32 is (back) online, every
five minutes while it is, and come back with every write. The controls appear
once the E32 answered (firmware without the options never shows them).

Sensors from the E32 summary (``fw/telemetry/summary`` with ``flow`` and
``night_gas`` from ``fw/telemetry/flow``, assembled by the HeatingHub), each
only once the E32 reports its part:

- "Flow source": what sets the flow now (room control, heating curve, learned
  flow, optimum start), with yesterday's comparison in the attributes;
- "Heating curve flow" and "Learned flow" (diagnostic): what each would ask
  for now, in use or as advice; "Room control flow" and "Heating curve slope"
  (diagnostic, disabled by default);
- "Gas calibration" (diagnostic): no meter / calibrating / calibrated (with its
  confidence) / meter not reporting, and "Boiler power at full burner"
  (diagnostic, disabled by default);
- "Last night's heating gas" (diagnostic): the measured heating gas of the
  last night next to the model's prediction; only once a night was measured
  with a gas meter (without one there is nothing to show).

The boiler request itself (the flow in use) stays the existing "Boiler
request (E32)" sensor.

"Water temperature by weather compensation" also carries what the heating-curve
card (frontend/heating-curve-card.js, E32 rc.5) draws: the standard slope from
the water temperature in hard frost (WeatherCurve::slopeFor), the room
temperature the curve starts from, the outdoor temperature the E32 uses now
and the plan's water temperature limits, next to the curve's slope and where
it comes from (standard, learned, or worked out from the house).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature, UnitOfVolume
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .heating_link import HubEntity, add_options, heating_hub, number, track_entities

_LOGGER = logging.getLogger(__name__)

KEY = "e32_flow"
REFRESH = timedelta(minutes=5)
OPTIONS = ("weather_curve", "apply_learned")
DESIGN_FLOW_KEY = "curve_design_flow_c"
DESIGN_FLOW_AUTOMATIC = "automatic"  # the select option for the stored 0
DESIGN_FLOW_LIMITS = (25, 80)  # the E32's own bound (WeatherCurve::min/maxDesignFlowC); 0 is automatic
SOURCES = ["rule", "curve", "learned", "optimum_start"]
GAS_STATUSES = ["no_meter", "collecting", "calibrated", "meter_stale"]
# The Learning view's cards (E32 rc.5), the sixth card module (week_planner.card_modules), versioned with the
# manifest like the other card URLs: "Water temperature by outdoor temperature" and what the E32 knows (a ring).
CURVE_CARD_URL = "/open_thermostat/heating-curve-card-1.0.0rc5.js"
CURVE_CARD_TYPE = "custom:openthermostat-heating-curve"
KNOWLEDGE_CARD_TYPE = "custom:openthermostat-knowledge"
# WeatherCurve (src/control/WeatherCurve.h): the standard slope follows the water temperature in hard frost
# (−10 °C outside) for a 20 °C room; automatic is floor heating 40 °C, radiators 55 °C; the slope's limits.
DESIGN_ROOM_C, DESIGN_OUTDOOR_C = 20, -10
DESIGN_FLOW_BY_EMITTER = {"floor": 40, "radiator": 55}
SLOPE_LIMITS = (0.2, 2.5)
# What only the card reads; it changes with the weather: shown, not kept in the history.
CURVE_CHART_KEYS = ("design_flow_c", "standard_slope", "room_c", "outdoor_c", "minimum_flow_c", "maximum_flow_c")


def decode_settings(value):
    """The options as the E32 stored them, or None when the answer is not well-formed.

    Since 1.0 the answer also has the "Comfort and boiler care" knobs ("tuning", the values
    in effect) and since rc.2 which automatic knobs the owner set ("tuning_manual"); both
    are kept only when well-formed (e32_care.decode_tuning). The options above never
    depend on them.
    """
    if type(value) is not dict:
        return None
    design = value.get(DESIGN_FLOW_KEY)
    if (any(type(value.get(key)) is not bool for key in OPTIONS) or type(design) is not int
            or design != 0 and not DESIGN_FLOW_LIMITS[0] <= design <= DESIGN_FLOW_LIMITS[1]):
        return None
    from .e32_care import decode_tuning
    return {**{key: value[key] for key in OPTIONS}, DESIGN_FLOW_KEY: design, **decode_tuning(value)}


def flow_error(err):
    """A clear Home Assistant error for a refused or failed write."""
    from .controller_link import ControllerLoginRejected, HeatingPlanRejected
    if isinstance(err, ControllerLoginRejected):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_password")
    if str(err) == "controller_no_free_session":
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="e32_no_free_session")
    if isinstance(err, HeatingPlanRejected):
        if err.error == "save_unconfirmed":
            return HomeAssistantError(translation_domain=DOMAIN, translation_key="flow_settings_unconfirmed")
        return ServiceValidationError(translation_domain=DOMAIN, translation_key="flow_settings_rejected",
                                      translation_placeholders={"error": err.error})
    return HomeAssistantError(translation_domain=DOMAIN, translation_key="flow_settings_unreachable",
                              translation_placeholders={"error": str(err)})


class FlowSettingsLink:
    """The E32's flow options as last read or written; listeners hear every change.

    Has ``add_listener`` and ``_trackers`` like the HeatingHub, so
    ``track_entities`` adds the controls once the options are known.
    """

    def __init__(self, hass, hub, plan):
        self.hass, self.hub, self.plan = hass, hub, plan
        self.settings = None
        self.unsupported = False  # firmware without the options: not asked again until the E32 is back
        self._task = None
        self._was_fresh = False
        self._listeners = []
        self._trackers = []

    @property
    def available(self):
        return self.hub.fresh and self.settings is not None

    @callback
    def add_listener(self, listener):
        self._listeners.append(listener)

        @callback
        def remove():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return remove

    @callback
    def notify(self):
        for listener in list(self._listeners):
            listener()

    @callback
    def poll(self, _now=None):
        """Read again (every five minutes) while the E32 is online; never with a refused password."""
        if (not self.hub.fresh or self.unsupported or self.plan.login_rejected
                or (self._task is not None and not self._task.done())):
            return
        self._task = self.hass.async_create_task(self.async_refresh(), "OpenThermostat E32 flow options read")

    @callback
    def hub_changed(self):
        """The E32 is (back) online, perhaps after a firmware update: read at once."""
        fresh = self.hub.fresh
        if fresh and not self._was_fresh:
            self.unsupported = False
            self.poll()
        self._was_fresh = fresh

    async def _call(self, change=None):
        # A change waits for a free E32 web session; a read does not.
        return await self.plan.async_call(lambda client: client.async_flow_settings(change), write=change is not None)

    async def async_read_now(self):
        """Read the options for a Configure form: what the E32 stored, or a clear HomeAssistantError."""
        from .controller_link import ControllerLinkError
        try:
            value = decode_settings(await self._call())
        except ControllerLinkError as err:
            raise flow_error(err) from None
        if value is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="flow_settings_unconfirmed")
        self._set(value)
        return value

    async def async_refresh(self):
        from .controller_link import ControllerLinkError
        try:
            value = decode_settings(await self._call())
        except ControllerLinkError as err:
            self.unsupported = str(err) == "controller_update_required"
            _LOGGER.debug("E32 flow options read failed: %s", err)
            return
        if value is not None:
            self._set(value)

    async def async_change(self, change):
        """POST one change; the E32 answers with what it stored (that is the read-back)."""
        from .controller_link import ControllerLinkError
        if self.settings is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="flow_settings_unreachable",
                                     translation_placeholders={"error": "not_read"})
        try:
            answer = await self._call(change)
        except ControllerLinkError as err:
            raise flow_error(err) from None
        value = decode_settings(answer)
        if value is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="flow_settings_unconfirmed")
        self._set(value)
        return value

    @callback
    def _set(self, value):
        if value != self.settings:
            self.settings = value
            self.notify()

    @callback
    def stop(self):
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._listeners.clear()


def flow_link(hass, entry):
    """The entry's one link, started by whichever platform asks first; None without a stored connection."""
    state = hass.data[DOMAIN][entry.entry_id]
    link = state.get(KEY)
    if link is None:
        hub = heating_hub(hass, entry)
        if hub.plan is None:
            return None  # no stored controller connection: nothing can be read or written
        link = state[KEY] = FlowSettingsLink(hass, hub, hub.plan)
        entry.async_on_unload(link.stop)
        entry.async_on_unload(hub.add_listener(link.hub_changed))
        entry.async_on_unload(async_track_time_interval(hass, link.poll, REFRESH))
        link.hub_changed()
    return link


def smart_warm_up(hass, entry_id):
    """Smart warm-up (``apply_learned``) as last read from the E32, or None while unknown."""
    data = getattr(hass, "data", None)
    link = data.get(DOMAIN, {}).get(entry_id, {}).get(KEY) if isinstance(data, dict) else None
    value = (link.settings or {}).get("apply_learned") if link is not None else None
    return value if type(value) is bool else None


# -- the controls ----------------------------------------------------------------------


class FlowOptionEntity(HubEntity):
    """One option on the product device; available while the E32 is online and its options are known."""

    _attr_entity_category = EntityCategory.CONFIG

    def _attach_link(self, link, key):
        self.link, self.key = link, key
        self._attach(link.hub, f"flow_{key}")
        self._attr_translation_key = f"flow_{key}"

    @property
    def available(self):
        return self.link.available

    @property
    def stored(self):
        return (self.link.settings or {}).get(self.key)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.link.add_listener(self._hub_changed))

    async def _change(self, value):
        await self.link.async_change({self.key: value})
        self.async_write_ha_state()


class FlowOptionSwitch(FlowOptionEntity, SwitchEntity):
    def __init__(self, link, key):
        self._attach_link(link, key)

    @property
    def is_on(self):
        return self.stored if type(self.stored) is bool else None

    async def async_turn_on(self, **kwargs):
        await self._change(True)

    async def async_turn_off(self, **kwargs):
        await self._change(False)


class FlowDesignSelect(FlowOptionEntity, SelectEntity):
    """The heating curve's flow at −10 °C outside: "automatic" (by heating type) or 25–80 °C.

    The E32 stores 0 for automatic (/config/heating/flow curve_design_flow_c); a choice list
    never shows that 0 as a temperature, and it is never converted to °F.
    """

    _attr_options = [DESIGN_FLOW_AUTOMATIC, *(str(c) for c in range(DESIGN_FLOW_LIMITS[0], DESIGN_FLOW_LIMITS[1] + 1))]

    def __init__(self, link):
        self._attach_link(link, DESIGN_FLOW_KEY)  # unique id <prefix>_flow_curve_design_flow_c (select)

    @property
    def current_option(self):
        if type(self.stored) is not int:
            return None
        return DESIGN_FLOW_AUTOMATIC if self.stored == 0 else str(self.stored)

    async def async_select_option(self, option):
        if option not in self._attr_options:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="flow_design_invalid",
                translation_placeholders={"minimum": str(DESIGN_FLOW_LIMITS[0]), "maximum": str(DESIGN_FLOW_LIMITS[1])})
        await self._change(0 if option == DESIGN_FLOW_AUTOMATIC else int(option))


def _wanted_switches(link):
    if link.settings is not None:
        for key in OPTIONS:
            yield key, lambda key=key: FlowOptionSwitch(link, key)


def _wanted_selects(link):
    if link.settings is not None:
        yield DESIGN_FLOW_KEY, lambda: FlowDesignSelect(link)


async def _async_setup_controls(hass, entry, async_add_entities, wanted):
    from .product import is_product
    if not is_product(entry):
        return
    link = flow_link(hass, entry)
    if link is None:
        return
    entry.async_on_unload(track_entities(link, async_add_entities, add_options(hass, entry), wanted))


async def async_setup_switches(hass, entry, async_add_entities):
    await _async_setup_controls(hass, entry, async_add_entities, _wanted_switches)


async def async_setup_selects(hass, entry, async_add_entities):
    await _async_setup_controls(hass, entry, async_add_entities, _wanted_selects)


# -- the sensors -----------------------------------------------------------------------


def summary_part(hub, key):
    """``flow`` or ``night_gas`` of the E32 summary (the hub merges fw/telemetry/flow into it), or None."""
    summary = getattr(hub, "summary", None)
    part = summary.get(key) if type(summary) is dict else None
    return part if type(part) is dict else None


def gas_calibration(hub):
    """The learner's gas calibration (``learned.gas`` of the summary), or None on firmware without it."""
    header = hub.learned_header
    gas = header.get("gas") if type(header) is dict else None
    return gas if type(gas) is dict else None


def _text(item, key):
    value = item.get(key) if type(item) is dict else None
    return value if type(value) is str and len(value) <= 40 else None


def _flow(value):
    return number(value, 0, 90)


def standard_slope(design_flow_c):
    """WeatherCurve::slopeFor: K of water above the room per K the outdoor is below it, or None."""
    if type(design_flow_c) is not int or not DESIGN_FLOW_LIMITS[0] <= design_flow_c <= DESIGN_FLOW_LIMITS[1]:
        return None
    slope = (design_flow_c - DESIGN_ROOM_C) / (DESIGN_ROOM_C - DESIGN_OUTDOOR_C)
    return round(min(SLOPE_LIMITS[1], max(SLOPE_LIMITS[0], slope)), 3)


def design_flow(settings, plan, learned=None):
    """The water temperature in hard frost the E32 uses: the stored one, else 55 °C with any radiator room and
    40 °C for floor heating only (as FlowPolicy decides), or None while neither is known."""
    stored = settings.get(DESIGN_FLOW_KEY) if type(settings) is dict else None
    if type(stored) is int and stored > 0:
        return stored
    rooms = plan.get("rooms") if type(plan) is dict and type(plan.get("rooms")) is list else None
    emitters = [room.get("emitter") for room in (rooms if rooms else (learned or {}).values()) if type(room) is dict]
    for emitter in ("radiator", "floor"):
        if emitter in emitters:
            return DESIGN_FLOW_BY_EMITTER[emitter]
    return None


def curve_room_c(rooms):
    """The room temperature the curve is drawn for: the highest target of the rooms the E32 heats now
    (FlowPolicy takes the highest base over its usable rooms), else 20 °C."""
    targets = [number(room.get("setpoint"), 5, 30) for room in (rooms or {}).values()
               if type(room) is dict and room.get("status") in ("ok", "fallback")]
    targets = [value for value in targets if value is not None]
    return max(targets) if targets else DESIGN_ROOM_C


def _limit(value):
    return value if type(value) is int and 20 <= value <= 90 else None


def curve_chart(settings, plan, learned, rooms, outdoor_c):
    """What the heating-curve card draws besides the curve's slope: {design_flow_c, standard_slope, room_c,
    outdoor_c, minimum_flow_c, maximum_flow_c}; None for what is not known."""
    design = design_flow(settings, plan, learned)
    plan = plan if type(plan) is dict else {}
    outdoor = number(outdoor_c, -50, 60)
    return {"design_flow_c": design, "standard_slope": standard_slope(design), "room_c": curve_room_c(rooms),
            "outdoor_c": round(outdoor, 1) if outdoor is not None else None,
            "minimum_flow_c": _limit(plan.get("minimum_flow_c")), "maximum_flow_c": _limit(plan.get("maximum_flow_c"))}


def curve_outdoor(hass, entry, hub):
    """The outdoor temperature the E32 uses now (learned.inputs.outdoor) as Home Assistant sees it: the boiler's
    own sensor, or the one set under Energy and outdoor temperature; None without one."""
    from .energy_input import CONF_OUTDOOR, energy_options, outdoor_celsius
    from .heating_link import celsius, learned_inputs
    source = learned_inputs(hub.learned_header).get("outdoor")
    if source == "ha":
        entity_id = energy_options(entry).get(CONF_OUTDOOR)
        return outdoor_celsius(hass.states.get(entity_id)) if type(entity_id) is str else None
    if source == "boiler":
        from homeassistant.helpers import entity_registry as er
        entity_id = er.async_get(hass).async_get_entity_id(
            "sensor", DOMAIN, f"{hub.prefix}_boiler_fields_v1_outdoor_temperature")
        state = hass.states.get(entity_id) if entity_id else None
        return celsius(state.state, state.attributes.get("unit_of_measurement"), -50, 60) if state else None
    return None


def _utc(value):
    if type(value) is not int or value <= 0:
        return None
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


class FlowSummarySensor(HubEntity, SensorEntity):
    """One value of the summary on the product device."""

    part = "flow"

    def __init__(self, hub, key):
        self._attach(hub, key)
        self._attr_translation_key = key

    @property
    def data(self):
        if not self.hub.fresh:
            return None
        return gas_calibration(self.hub) if self.part == "gas" else summary_part(self.hub, self.part)

    @property
    def available(self):
        return self.data is not None


class FlowSourceSensor(FlowSummarySensor):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = SOURCES

    def __init__(self, hub):
        super().__init__(hub, "flow_source")

    @property
    def native_value(self):
        source = _text(self.data, "source")
        return source if source in SOURCES else None

    @property
    def extra_state_attributes(self):
        flow = self.data
        if flow is None:
            return None
        curve, learned = flow.get("curve"), flow.get("learned")
        start = flow.get("optimum_start")
        attributes = {"applied_flow_c": _flow(flow.get("applied_flow_c")), "rule_flow_c": _flow(flow.get("rule_flow_c")),
                      "curve_state": _text(curve, "state"), "learned_state": _text(learned, "state"),
                      "optimum_start": start if type(start) is str else _text(start, "state")}
        yesterday = flow.get("yesterday") if type(flow.get("yesterday")) is dict else {}
        for key in ("rule", "applied", "curve", "learned"):
            attributes[f"yesterday_{key}_mean_c"] = _flow(yesterday.get(f"{key}_mean_c"))
        return attributes


class FlowTemperatureSensor(FlowSummarySensor):
    """A flow in °C: the heating curve's, the learned one or the room control's (what each asks for now)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    PATHS = {"flow_curve": ("curve", "flow_c"), "flow_learned": ("learned", "flow_c"), "flow_rule": (None, "rule_flow_c")}
    _unrecorded_attributes = frozenset(CURVE_CHART_KEYS)

    def __init__(self, hub, key):
        super().__init__(hub, key)
        self.block, self.field = self.PATHS[key]
        self._attr_entity_registry_enabled_default = key != "flow_rule"

    def _chart(self):
        """The heating-curve card's figures (curve_chart) from the E32's options, plan, rooms and outdoor."""
        hass = getattr(self, "hass", None)
        entry = getattr(getattr(self, "platform", None), "config_entry", None)
        state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}) if hass is not None and entry is not None else {}
        outdoor = curve_outdoor(hass, entry, self.hub) if state else None
        plan = getattr(self.hub.plan, "plan", None)
        return curve_chart(getattr(state.get(KEY), "settings", None), plan, self.hub.learned, self.hub.rooms, outdoor)

    def _block(self):
        flow = self.data
        block = flow if self.block is None or flow is None else flow.get(self.block)
        return block if type(block) is dict else None

    @property
    def native_value(self):
        return _flow((self._block() or {}).get(self.field))

    @property
    def extra_state_attributes(self):
        block = self._block()
        if block is None or self.block is None:
            return None
        attributes = {"state": _text(block, "state")}
        if self.block == "curve":
            attributes.update(slope=number(block.get("slope"), 0, 10), slope_source=_text(block, "slope_source"))
            attributes.update(self._chart())  # E32 rc.5: the heating-curve card
        return attributes


class CurveSlopeSensor(FlowSummarySensor):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, hub):
        super().__init__(hub, "flow_curve_slope")

    @property
    def native_value(self):
        curve = (self.data or {}).get("curve")
        return number(curve.get("slope"), 0, 10) if type(curve) is dict else None

    @property
    def extra_state_attributes(self):
        curve = (self.data or {}).get("curve")
        return {"slope_source": _text(curve, "slope_source")} if type(curve) is dict else None


class GasCalibrationSensor(FlowSummarySensor):
    part = "gas"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = GAS_STATUSES

    def __init__(self, hub):
        super().__init__(hub, "gas_calibration")

    @property
    def native_value(self):
        status = _text(self.data, "status")
        return status if status in GAS_STATUSES else None

    @property
    def extra_state_attributes(self):
        gas = self.data
        if gas is None:
            return None
        confidence = _text(gas, "confidence")
        return {"confidence": confidence if confidence in ("none", "low", "medium", "high") else None,
                "factor": number(gas.get("factor"), 0, 10), "kw_source": _text(gas, "kw_source")}


class BoilerFullPowerSensor(FlowSummarySensor):
    part = "gas"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_suggested_display_precision = 1

    def __init__(self, hub):
        super().__init__(hub, "boiler_full_power")

    @property
    def native_value(self):
        return number((self.data or {}).get("kw_at_full_modulation"), 0, 200)

    @property
    def extra_state_attributes(self):
        gas = self.data
        return {"kw_source": _text(gas, "kw_source"), "confidence": _text(gas, "confidence")} if gas else None


class NightGasSensor(FlowSummarySensor):
    """The last night's measured heating gas (hot water taken off) next to the model's prediction."""

    part = "night_gas"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.GAS
    _attr_native_unit_of_measurement = UnitOfVolume.CUBIC_METERS
    _attr_suggested_display_precision = 2

    def __init__(self, hub):
        super().__init__(hub, "night_heating_gas")

    @property
    def last(self):
        last = (self.data or {}).get("last")
        return last if type(last) is dict else None

    @property
    def native_value(self):
        last = self.last
        return number(last.get("heating_m3"), 0, 1000) if last and last.get("status") == "measured" else None

    @property
    def extra_state_attributes(self):
        night, last = self.data, self.last
        if night is None:
            return None
        last = last or {}
        return {"status": _text(last, "status"), "hot_water_m3": number(last.get("hot_water_m3"), 0, 1000),
                "predicted_m3": number(last.get("predicted_program_m3"), 0, 1000),
                "recommended": _text(last, "recommended"), "morning": _utc(last.get("switch_utc")),
                "model_ratio": number(night.get("model_ratio"), 0, 100), "nights": night.get("nights")
                if type(night.get("nights")) is int else None}


def wanted_sensors(hub):
    if summary_part(hub, "flow") is not None:  # firmware with the flow options (E32 beta.19)
        yield ("flow", "source"), lambda: FlowSourceSensor(hub)
        for key in FlowTemperatureSensor.PATHS:
            yield ("flow", key), lambda key=key: FlowTemperatureSensor(hub, key)
        yield ("flow", "slope"), lambda: CurveSlopeSensor(hub)
    if gas_calibration(hub) is not None:
        yield ("gas", "calibration"), lambda: GasCalibrationSensor(hub)
        yield ("gas", "full_power"), lambda: BoilerFullPowerSensor(hub)
    last = (summary_part(hub, "night_gas") or {}).get("last")
    if type(last) is dict and last.get("status") == "measured":  # only with a gas meter
        yield ("night_gas",), lambda: NightGasSensor(hub)


async def async_setup_sensors(hass, entry, async_add_entities):
    from .product import is_product
    if not is_product(entry):
        return
    hub = heating_hub(hass, entry)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), wanted_sensors))
