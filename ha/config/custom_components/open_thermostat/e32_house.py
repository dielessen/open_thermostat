"""The house mode of an E32 (beta.23, ``src/control/RoomOverrides.h``): automatic, at home, away, holiday.

One select on the product device (the house, not one room) chooses the mode:

- automatic: the people of the house decide (Configure → Home → Presence; the
  E32 hears "someone home" or "everyone away", e32_comfort.ComfortForwarder);
- at home: the week programs always, also when everyone is away;
- away: every room at most the away temperature until switched back;
- holiday: away until a date ("Holiday until"), warm again in time.

"Holiday until" (datetime) starts a holiday until that time; "Temperature when
nobody is home" (number) is the away temperature for all rooms. Configure →
Home → Presence sets the same away temperature with the same command
(HouseState.async_command, e32_comfort.async_step_house_presence). Frost
protection is never affected (the E32 heats any room below 8 °C).

Capability ``house.mode.v1``: the E32 announces it as the ``mode`` field of the
house's away status (``fw/state/heating`` "away"). E32 beta.21 has no ``mode``:
then "at home" is not offered and the other modes use its older commands
(``{"away": true|false, "until": ..}``), so HA 0.4.0b15 works with it.

Commands go over the stored controller connection (``POST
/config/heating/comfort``, the same login and lock as the room plan). The
E32's answer carries the stored away state; that read-back is shown until the
next status from the E32 arrives.

Holidays (E32 rc.4, capability ``house.holidays.v1``, announced as the list
``away.holidays``): up to 8 periods planned ahead with their own "Temperature
on holiday" (number). The status lists the next two; Configure → House → House
mode and holiday reads and changes the whole list (``GET``/``POST
/config/heating/comfort`` ``{"holidays": [{"from", "until"}]}`` in one E32 web
session, async_change_holidays). The house is in mode holiday inside a period
and returns to the mode it had afterwards. Older firmware: none of this.
"""
from __future__ import annotations

from datetime import timedelta
import time
import weakref

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .e32_comfort import AWAY_LIMITS, MAX_AWAY_DAYS, async_comfort_command, away_command, comfort_error
from .heating_link import HubEntity, add_options, heating_hub, number, track_entities

HOUSE_MODE_CAPABILITY = "house.mode.v1"  # announced as away.mode in the E32's heating status
HOLIDAYS_CAPABILITY = "house.holidays.v1"  # announced as the list away.holidays (the next two holidays)
MAX_HOLIDAYS = 8  # RoomOverrides::maxHolidays
MODES = ["auto", "home", "away", "holiday"]
READBACK_S = 60  # how long the E32's answer to a command is shown before its next status
KEY = "house_state"


def house_away(hub):
    """The house's away status (``fw/state/heating`` "away"), or None."""
    status = hub.status if type(hub.status) is dict else {}
    away = status.get("away")
    return away if type(away) is dict and type(away.get("on")) is bool else None


def supports_house_mode(away):
    """E32 beta.23 and newer: the status names the mode (house.mode.v1)."""
    return type(away) is dict and away.get("mode") in MODES


def supports_holidays(away):
    """E32 rc.4 and newer plan holidays ahead (house.holidays.v1): the status lists the next ones."""
    return type(away) is dict and type(away.get("holidays")) is list


def holiday_periods(items):
    """[(from, until)] (unix seconds) of a list of {"from", "until"}, the well-formed ones in order."""
    out = []
    for item in items if type(items) is list else []:
        if type(item) is dict and type(item.get("from")) is int and type(item.get("until")) is int and 0 <= item["from"] < item["until"]:
            out.append((item["from"], item["until"]))
    return sorted(out)


def merge_periods(periods):
    """The periods in order, those that overlap or touch as one (as the E32 merges them)."""
    out = []
    for start, end in sorted(periods):
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


HOLIDAY_SELECT_AHEAD_S = 24 * 3600  # Holiday from the list means "now": a planned one counts only when it starts within a day


def next_holiday_end(away, now=None, within=HOLIDAY_SELECT_AHEAD_S):
    """E32 rc.4+: the end (unix seconds) of the planned holiday that runs now or starts within ``within`` seconds, or
    None (choosing Holiday from the list starts it now, so one weeks away would start weeks early)."""
    if not supports_holidays(away):
        return None
    now = dt_util.utcnow().timestamp() if now is None else now
    return next((until for start, until in holiday_periods(away["holidays"]) if until > now and start <= now + within),
                None)


def holiday_temperature(away):
    """The temperature on holiday (°C): the owner's own, else the away temperature; None on older firmware."""
    return number(away.get("holiday_temperature_c"), *AWAY_LIMITS) if supports_holidays(away) else None


def house_mode(away):
    """auto, home, away or holiday; derived from the away state on firmware without house modes."""
    if supports_house_mode(away):
        return away["mode"]
    if type(away) is dict and away.get("on") is True and away.get("source") == "manual":
        return "holiday" if type(away.get("until")) is int and away["until"] > 0 else "away"
    return "auto"


def holiday_until(value, now=None):
    """The unix time of a holiday end: in the future and at most a year ahead."""
    now = now or dt_util.utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_util.get_default_time_zone())
    if not now < value <= now + timedelta(days=MAX_AWAY_DAYS):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_away_until")
    return int(value.timestamp())


def mode_command(away, mode, temperature=None, until=None):
    """The command for a mode, in the E32's own format (house_mode, or the older away command)."""
    if mode not in MODES:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="house_mode_invalid")
    if mode == "holiday" and until is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="house_holiday_date_needed")
    if temperature is not None and number(temperature, *AWAY_LIMITS) is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_away_temperature")
    if supports_house_mode(away):
        command = {"house_mode": mode}
        if temperature is not None:
            command["temperature"] = round(float(temperature), 2)
        if mode == "holiday":
            command["until"] = until
        return command
    if mode == "home":
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="house_mode_update_required")
    if mode == "auto":
        if temperature is not None:  # beta.21 sets the away temperature only together with away
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="house_mode_update_required")
        return {"away": False}
    command = away_command(True, temperature)
    if mode == "holiday":
        command["until"] = until
    return command


async def async_comfort_state(link):
    """GET the E32's comfort state (every planned holiday) over the link's stored connection (one sign-in,
    RoomPlanLink.async_call: the one path that honours the refused-password latch and never waits)."""
    from .controller_link import ControllerLinkError
    try:
        state = await link.async_call(lambda client: client.async_comfort_state())
    except ControllerLinkError as err:
        raise comfort_error(err) from None
    if type(state) is not dict or type(state.get("holidays")) is not list:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="house_mode_update_required")
    return state


async def async_change_holidays(link, change):
    """Read, change and write the E32's planned holidays in one E32 web session (RoomPlanLink.async_call).

    change(periods) gets the list as the E32 holds it now ([(from, until)]) and returns the new one (it may raise
    a HomeAssistantError, e.g. house_holiday_changed); the E32 merges overlapping periods and refuses one that is
    over (merged here already, so eight places hold a holiday that joins another). With every E32 web session in
    use it waits for one without holding up reads or other writes (R4-02); a newer change supersedes one that
    still waits: None, nothing sent. Returns the E32's answer, its comfort state.
    """
    from .controller_link import ControllerLinkError
    from .room_plan import WriteSuperseded

    async def save(client):
        state = await client.async_comfort_state()
        if type(state) is not dict or type(state.get("holidays")) is not list:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="house_mode_update_required")
        periods = merge_periods(change(holiday_periods(state["holidays"])))
        if len(periods) > MAX_HOLIDAYS:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="house_holiday_too_many")
        return await client.async_comfort_command({"holidays": [{"from": int(f), "until": int(u)} for f, u in periods]})
    try:
        answer = await link.async_call(save, write=True, key=("holidays",))
    except WriteSuperseded:
        return None
    except ControllerLinkError as err:
        raise comfort_error(err) from None
    if type(answer) is not dict or answer.get("schema") != 1:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unconfirmed")
    return answer


# The house changes on their way to the E32, per room-plan link: field -> (value, the command carrying it).
_WAITING = weakref.WeakKeyDictionary()


async def async_house_change(link, away, mode=None, until=None, temperature=None):
    """Send one house change (a mode with its holiday end, or the away temperature); the E32's answer.

    The E32 takes the house as one command: house_mode always, the away
    temperature and holiday end with it. A newer house command supersedes one
    that still waits for an E32 web session (async_comfort_command, None: not
    sent), so every command carries the newest value of each field still on
    its way: a newer mode keeps an away temperature set just before it, and a
    newer away temperature keeps a mode chosen just before it (never the mode
    it read from the E32).
    """
    waiting = _WAITING.setdefault(link, {})
    change = {}
    if mode is not None:
        change["mode"] = (mode, until)
    if temperature is not None:
        change["temperature"] = temperature
    fields = {**{name: value for name, (value, _) in waiting.items()}, **change}
    if "mode" in fields:
        mode, until = fields["mode"]
    else:
        mode = house_mode(away)
        until = away.get("until") if mode == "holiday" and type(away) is dict else None
    temperature = fields.get("temperature")
    if mode == "auto" and "temperature" not in change and not supports_house_mode(away):
        temperature = None  # beta.21 takes the away temperature only together with away
    command = mode_command(away, mode, temperature=temperature, until=until)  # refused: nothing recorded
    mine = object()
    waiting.update({name: (value, mine) for name, value in fields.items()})
    try:
        return await async_comfort_command(link, command)
    finally:
        # Sent or failed: done. Superseded: the newer command took these fields over.
        for name, (_, owner) in list(waiting.items()):
            if owner is mine:
                del waiting[name]


class HouseState:
    """The house's away status for the three controls: the E32's read-back of a command, else its status."""

    def __init__(self, hub):
        self.hub = hub
        self.answer, self.answer_at = None, 0.0
        self.pending_until = None  # "Holiday until" chosen before the select picks holiday

    @property
    def away(self):
        if self.answer is not None and time.monotonic() - self.answer_at < READBACK_S:
            return self.answer
        return house_away(self.hub)

    async def async_command(self, mode=None, until=None, temperature=None):
        answer = await async_house_change(self.hub.plan, self.away, mode, until, temperature)
        if answer is None:
            return  # a newer house mode came in while this one waited for an E32 web session
        self._show(answer)

    async def async_holidays(self, change):
        """Change the planned holidays (async_change_holidays); the E32's answer is shown at once."""
        answer = await async_change_holidays(self.hub.plan, change)
        if answer is not None:
            self._show(answer)
        return answer

    async def async_holiday_temperature(self, value):
        """The temperature on holiday (5–25 °C) on its own; the E32's answer is shown at once."""
        if number(value, *AWAY_LIMITS) is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="holiday_temperature_invalid")
        answer = await async_comfort_command(self.hub.plan, {"holiday_temperature": round(float(value), 2)})
        if answer is not None:
            self._show(answer)
        return answer

    def _show(self, answer):
        away = answer.get("away") if type(answer) is dict else None
        if type(away) is dict and type(away.get("on")) is bool:
            self.answer, self.answer_at = away, time.monotonic()
        self.hub.notify()

    @callback
    def hub_changed(self):
        """The E32's status replaces the command's answer once it shows the same mode and temperature."""
        status = house_away(self.hub)
        if (self.answer is not None and status is not None and house_mode(status) == house_mode(self.answer)
                and status.get("target_c") == self.answer.get("target_c") and status.get("until") == self.answer.get("until")
                and status.get("holiday_temperature_c") == self.answer.get("holiday_temperature_c")
                and status.get("holidays") == self.answer.get("holidays")):
            self.answer = None


def house_state(hass, entry, hub):
    state = hass.data[DOMAIN][entry.entry_id]
    if KEY not in state:
        state[KEY] = HouseState(hub)
        entry.async_on_unload(hub.add_listener(state[KEY].hub_changed))
    return state[KEY]


class HouseEntity(HubEntity):
    """On the product device; available while the E32 is online and reports the house's away status."""

    def __init__(self, house, suffix):
        self.house = house
        self._attach(house.hub, suffix)
        self._attr_translation_key = suffix

    @property
    def available(self):
        return self.hub.fresh and self.house.away is not None and self.hub.plan is not None


class HouseModeSelect(HouseEntity, SelectEntity):
    """Automatic, at home, away or holiday."""

    def __init__(self, house):
        super().__init__(house, "house_mode")

    @property
    def options(self):
        away = self.house.away
        return list(MODES) if away is None or supports_house_mode(away) else ["auto", "away", "holiday"]

    @property
    def current_option(self):
        away = self.house.away
        return house_mode(away) if away is not None else None

    @property
    def extra_state_attributes(self):
        away = self.house.away
        if away is None:
            return None
        until = away.get("until")
        attributes = {"presence": away.get("presence"), "away_now": away.get("on") is True,
                      "away_temperature": number(away.get("target_c"), 5, 25),
                      "until": dt_util.utc_from_timestamp(until).isoformat() if type(until) is int and until > 0 else None}
        if supports_holidays(away):  # rc.4: the next holidays (the dashboard shows the first) and their temperature
            attributes["holidays"] = [{"from": dt_util.utc_from_timestamp(f).isoformat(), "until": dt_util.utc_from_timestamp(u).isoformat()}
                                      for f, u in holiday_periods(away["holidays"])]
            attributes["holiday_temperature"] = holiday_temperature(away)
        return attributes

    async def async_select_option(self, option):
        """Holiday from the list: until "Holiday until", the running holiday's end, or (rc.4+) the end of a planned
        holiday that starts within a day, which then starts now; without any of them the error says how to start one."""
        away = self.house.away
        until = None
        if option == "holiday":
            current = away.get("until") if house_mode(away) == "holiday" else None
            until = self.house.pending_until or current or next_holiday_end(away)
        await self.house.async_command(option, until)


class HolidayUntil(HouseEntity, DateTimeEntity):
    """When a holiday ends; setting it starts the holiday until then (warm again in time)."""

    def __init__(self, house):
        super().__init__(house, "holiday_until")

    @property
    def native_value(self):
        away = self.house.away
        until = away.get("until") if away is not None and house_mode(away) == "holiday" else self.house.pending_until
        return dt_util.utc_from_timestamp(until) if type(until) is int and until > 0 else None

    async def async_set_value(self, value):
        until = holiday_until(value)
        self.house.pending_until = until
        await self.house.async_command("holiday", until)


class AwayTemperature(HouseEntity, NumberEntity):
    """Temperature when nobody is home: every room at most this while away, on holiday or everyone away."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value, _attr_native_max_value = AWAY_LIMITS
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, house):
        super().__init__(house, "away_temperature")

    @property
    def native_value(self):
        away = self.house.away
        return number(away.get("target_c"), *AWAY_LIMITS) if away is not None else None

    async def async_set_native_value(self, value):
        await self.house.async_command(temperature=value)  # in the mode it has (or is about to get)


class HolidayTemperature(HouseEntity, NumberEntity):
    """Temperature on holiday (E32 rc.4, house.holidays.v1): every room at most this during a holiday.

    The away temperature until the owner sets one; only on an E32 that plans holidays.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value, _attr_native_max_value = AWAY_LIMITS
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, house):
        super().__init__(house, "holiday_temperature")

    @property
    def available(self):
        return super().available and supports_holidays(self.house.away)

    @property
    def native_value(self):
        away = self.house.away
        return holiday_temperature(away) if away is not None else None

    async def async_set_native_value(self, value):
        await self.house.async_holiday_temperature(value)


def _wanted(factory, house, condition=None):
    def wanted(hub):
        away = house_away(hub)
        if away is not None and (condition is None or condition(away)):
            yield factory.__name__, lambda: factory(house)
    return wanted


async def _async_setup(hass, entry, async_add_entities, factory, condition=None):
    from .product import is_product
    if not is_product(entry):
        return
    hub = heating_hub(hass, entry)
    if hub.plan is None:
        return  # no stored controller connection: nothing can be written
    house = house_state(hass, entry, hub)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), _wanted(factory, house, condition)))


async def async_setup_selects(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, HouseModeSelect)


async def async_setup_datetimes(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, HolidayUntil)


async def async_setup_numbers(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, AwayTemperature)
    await _async_setup(hass, entry, async_add_entities, HolidayTemperature, supports_holidays)
