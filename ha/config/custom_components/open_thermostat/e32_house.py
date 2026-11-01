"""The house mode of an E32 (beta.23, ``src/control/RoomOverrides.h``): automatic, at home, away, holiday.

One select on the product device (the house, not one room) chooses the mode:

- automatic: the people of the house decide (Configure → Home → Presence; the
  E32 hears "someone home" or "everyone away", e32_comfort.ComfortForwarder);
- at home: the week programs always, also when everyone is away;
- away: every room at most the away temperature until switched back;
- holiday: away until a date ("Holiday until"), warm again in time.

"Holiday until" (datetime) starts a holiday until that time; "Temperature when
nobody is home" (number) is the away temperature for all rooms. Frost
protection is never affected (the E32 heats any room below 8 °C).

Capability ``house.mode.v1``: the E32 announces it as the ``mode`` field of the
house's away status (``fw/state/heating`` "away"). E32 beta.21 has no ``mode``:
then "at home" is not offered and the other modes use its older commands
(``{"away": true|false, "until": ..}``), so HA 0.4.0b15 works with it.

Commands go over the stored controller connection (``POST
/config/heating/comfort``, the same login and lock as the room plan). The
E32's answer carries the stored away state; that read-back is shown until the
next status from the E32 arrives.
"""
from __future__ import annotations

from datetime import timedelta
import time

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .e32_comfort import AWAY_LIMITS, MAX_AWAY_DAYS, async_comfort_command, away_command
from .heating_link import HubEntity, add_options, heating_hub, number, track_entities

HOUSE_MODE_CAPABILITY = "house.mode.v1"  # announced as away.mode in the E32's heating status
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

    async def async_command(self, command):
        answer = await async_comfort_command(self.hub.plan, command)
        away = answer.get("away")
        if type(away) is dict and type(away.get("on")) is bool:
            self.answer, self.answer_at = away, time.monotonic()
        self.hub.notify()

    @callback
    def hub_changed(self):
        """The E32's status replaces the command's answer once it shows the same mode and temperature."""
        status = house_away(self.hub)
        if (self.answer is not None and status is not None and house_mode(status) == house_mode(self.answer)
                and status.get("target_c") == self.answer.get("target_c") and status.get("until") == self.answer.get("until")):
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
        return {"presence": away.get("presence"), "away_now": away.get("on") is True,
                "away_temperature": number(away.get("target_c"), 5, 25),
                "until": dt_util.utc_from_timestamp(until).isoformat() if type(until) is int and until > 0 else None}

    async def async_select_option(self, option):
        away = self.house.away
        until = None
        if option == "holiday":
            current = away.get("until") if house_mode(away) == "holiday" else None
            until = self.house.pending_until or current
        await self.house.async_command(mode_command(away, option, until=until))


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
        await self.house.async_command(mode_command(self.house.away, "holiday", until=until))


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
        away = self.house.away
        mode = house_mode(away)
        until = away.get("until") if mode == "holiday" else None
        await self.house.async_command(mode_command(away, mode, temperature=value, until=until))


def _wanted(factory, house):
    def wanted(hub):
        if house_away(hub) is not None:
            yield factory.__name__, lambda: factory(house)
    return wanted


async def _async_setup(hass, entry, async_add_entities, factory):
    from .product import is_product
    if not is_product(entry):
        return
    hub = heating_hub(hass, entry)
    if hub.plan is None:
        return  # no stored controller connection: nothing can be written
    house = house_state(hass, entry, hub)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), _wanted(factory, house)))


async def async_setup_selects(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, HouseModeSelect)


async def async_setup_datetimes(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, HolidayUntil)


async def async_setup_numbers(hass, entry, async_add_entities):
    await _async_setup(hass, entry, async_add_entities, AwayTemperature)
