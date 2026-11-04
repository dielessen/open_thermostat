"""Configure steps for what the house mode, Smart warm-up and Weather compensation entities also set.

Everything the E32 device offers as a control is also here, in Configure
(options_navigation.py gives each step its Back item):

- House -> House mode and holiday: the house mode (Automatic, At home, Away,
  Holiday) and the holiday end, with the very command of the select and the
  datetime entity (e32_house.HouseState.async_command); "Stop holiday". On an
  E32 that plans holidays (rc.4, house.holidays.v1) it is a menu: the house
  mode, plan a holiday, change or remove one, and the temperature on holiday
  (the number entity's command); the whole list is read and written in one E32
  web session (e32_house.async_change_holidays);
- Heating and boiler -> Smart warm-up and -> Weather compensation (with the water
  temperature in hard frost under Advanced): the same E32 link as the switches
  and the select (e32_flow.FlowSettingsLink.async_change).
"""
from datetime import timedelta

import probatio as vol
from homeassistant.data_entry_flow import section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .e32_comfort import AWAY_LIMITS, MAX_AWAY_DAYS
from .e32_flow import DESIGN_FLOW_AUTOMATIC, DESIGN_FLOW_KEY, DESIGN_FLOW_LIMITS, flow_link
from .e32_house import (MODES, async_comfort_state, holiday_periods, holiday_temperature, holiday_until,
                        house_mode, supports_holidays, supports_house_mode)
from .heating_link import number

DESIGN_CHOICES = [DESIGN_FLOW_AUTOMATIC, *(str(c) for c in range(DESIGN_FLOW_LIMITS[0], DESIGN_FLOW_LIMITS[1] + 1))]
# The E32's refusals of a holiday list (RoomOverrides::command) and of a change made elsewhere -> the form's error.
HOLIDAY_ERRORS = {"holiday_in_past": "house_holiday_past", "holiday_too_far": "house_holiday_too_far",
                  "too_many_holidays": "house_holiday_too_many", "house_holiday_too_many": "house_holiday_too_many",
                  "invalid_holidays": "house_holiday_order", "comfort_no_clock": "house_holiday_no_clock",
                  "house_holiday_changed": "house_holiday_changed"}


class HolidayInputError(Exception):
    def __init__(self, field, code):
        super().__init__(code)
        self.field, self.code = field, code


def holiday_input(start, end, now=None):
    """(from, until) in unix seconds of the form's two moments (local time when without a zone).

    The end lies in the future and at most a year ahead and after the start; the start may lie in the
    past (a holiday that runs already). Raises HolidayInputError(field, error key).
    """
    now = now or dt_util.utcnow()
    moments = []
    for field, value in (("holiday_from", start), ("holiday_to", end)):
        moment = dt_util.parse_datetime(str(value or ""))
        if moment is None:
            raise HolidayInputError(field, "house_holiday_dates_needed")
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=dt_util.get_default_time_zone())
        moments.append(moment)
    if moments[1] <= moments[0]:
        raise HolidayInputError("holiday_to", "house_holiday_order")
    if moments[1] <= now:
        raise HolidayInputError("holiday_to", "house_holiday_past")
    if moments[1] > now + timedelta(days=MAX_AWAY_DAYS):
        raise HolidayInputError("holiday_to", "house_holiday_too_far")
    return max(0, int(moments[0].timestamp())), int(moments[1].timestamp())


def holiday_line(period, language="en"):
    """One holiday in plain words, local time: "19 Dec 2030 10:00 – 3 Jan 2031 18:00" (numeric dates in Dutch and Polish)."""
    def moment(utc):
        local = dt_util.as_local(dt_util.utc_from_timestamp(utc))
        if language == "en":
            return f"{local.day} {local.strftime('%b %Y %H:%M')}"
        return local.strftime("%d-%m-%Y %H:%M")
    return f"{moment(period[0])} – {moment(period[1])}"


def _without(periods, period):
    """The list without one holiday; it must still be there (else it was changed elsewhere)."""
    if period not in periods:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="house_holiday_changed")
    return [p for p in periods if p != period]


class HouseHeatingSteps:
    """Mixin of the product options flow."""

    # -- house mode and holiday -------------------------------------------------------

    async def async_step_house_mode(self, user_input=None):
        house = self._presence_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        if user_input is None and supports_holidays(house.away):
            return await self.async_step_house_holidays()
        return await self._house_mode_form("house_mode", house, user_input)

    async def async_step_house_mode_set(self, user_input=None):
        """The house mode itself, inside the holidays menu (the same form as before rc.4)."""
        house = self._presence_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        return await self._house_mode_form("house_mode_set", house, user_input)

    async def _house_mode_form(self, step_id, house, user_input):
        away = house.away
        current = house_mode(away)
        modes = [mode for mode in MODES if mode != "home" or supports_house_mode(away)]
        errors, placeholders = {}, {"error": ""}
        if user_input is not None:
            mode = user_input.get("house_mode")
            until = None
            if mode not in modes:
                errors["house_mode"] = "house_mode_invalid"
            elif mode == "holiday":
                value = dt_util.parse_datetime(str(user_input.get("holiday_until") or ""))
                if value is None:
                    errors["holiday_until"] = "house_holiday_date_needed"
                else:
                    try:
                        until = holiday_until(value)
                    except HomeAssistantError:
                        errors["holiday_until"] = "house_holiday_date_invalid"
            if not errors:
                if mode == current and (mode != "holiday" or until == away.get("until")):
                    return self.async_abort(reason="e32_room_unchanged")
                try:
                    if until is not None:
                        house.pending_until = until
                    await house.async_command(mode, until)
                except HomeAssistantError as err:
                    key = getattr(err, "translation_key", None)
                    errors["base"] = ("house_mode_update_required" if key == "house_mode_update_required"
                                      else "house_mode_not_saved")
                    placeholders["error"] = (getattr(err, "translation_placeholders", None) or {}).get("error") or \
                        key or "unknown"
                else:
                    return self.async_abort(reason="house_mode_saved")
        until = away.get("until") if current == "holiday" else None
        marker = vol.Optional("holiday_until")
        if type(until) is int and until > 0:
            marker = vol.Optional("holiday_until", description={"suggested_value": dt_util.as_local(
                dt_util.utc_from_timestamp(until)).strftime("%Y-%m-%d %H:%M:%S")})
        schema = vol.Schema({
            vol.Required("house_mode", default=current): selector.SelectSelector({
                "options": modes, "translation_key": "house_mode_choice", "mode": "list"}),
            marker: selector.DateTimeSelector(),
        })
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id=step_id, data_schema=schema, errors=errors,
                                    description_placeholders=placeholders)

    async def async_step_house_holiday_stop(self, user_input=None):
        house = self._presence_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        try:
            if supports_holidays(house.away):
                # rc.4: the running holiday ends now; the house returns to the mode it had before it.
                now = int(dt_util.utcnow().timestamp())
                await house.async_holidays(lambda periods: [p for p in periods if not p[0] <= now < p[1]])
            else:
                await house.async_command("auto", None)
        except HomeAssistantError:
            return self.async_abort(reason="house_mode_unavailable")
        return self.async_abort(reason="house_mode_saved")

    # -- planned holidays (E32 rc.4, house.holidays.v1) -------------------------------

    def _holiday_house(self):
        house = self._presence_house()
        return house if house is not None and supports_holidays(house.away) else None

    def _holiday_language(self):
        language = str(getattr(self.hass.config, "language", "en") or "en").split("-")[0]
        return language if language in ("en", "nl", "pl") else "en"

    async def _holiday_periods(self, house):
        """Every planned holiday as the E32 holds it now (the status names only the next two)."""
        return holiday_periods((await async_comfort_state(house.hub.plan))["holidays"])

    async def _holidays_change(self, house, change, errors, placeholders):
        """Sends one change of the list; the menu again ("Saved.") or None with the form's error set."""
        try:
            await house.async_holidays(change)
        except HomeAssistantError as err:
            key = getattr(err, "translation_key", None)
            code = (getattr(err, "translation_placeholders", None) or {}).get("error") or key or "unknown"
            errors["base"] = HOLIDAY_ERRORS.get(code, "house_holiday_not_saved")
            placeholders["error"] = code
            return None
        return self.async_abort(reason="house_mode_saved")

    async def async_step_house_holidays(self, user_input=None):
        """House mode and holiday: the house mode, plan a holiday, change or remove one, the temperature on holiday."""
        house = self._holiday_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        try:
            periods = await self._holiday_periods(house)
        except HomeAssistantError:
            return self.async_abort(reason="house_mode_unavailable")
        language = self._holiday_language()
        none = {"en": "No holidays planned.", "nl": "Geen vakanties gepland.", "pl": "Brak zaplanowanych urlopów."}[language]
        lines = "\n".join(f"- {holiday_line(p, language)}" for p in periods) or none
        options = ["house_mode_set", "house_holiday_add", *(["house_holiday_change"] if periods else []), "house_holiday_temperature"]
        return self.async_show_menu(step_id="house_holidays", menu_options=options, description_placeholders={"holidays": lines})

    async def async_step_house_holiday_add(self, user_input=None):
        house = self._holiday_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        errors, placeholders = {}, {"error": ""}
        if user_input is not None:
            try:
                period = holiday_input(user_input.get("holiday_from"), user_input.get("holiday_to"))
            except HolidayInputError as err:
                errors[err.field] = err.code
            else:
                if (result := await self._holidays_change(house, lambda periods: [*periods, period], errors,
                                                          placeholders)) is not None:
                    return result
        schema = vol.Schema({vol.Required("holiday_from"): selector.DateTimeSelector(),
                             vol.Required("holiday_to"): selector.DateTimeSelector()})
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="house_holiday_add", data_schema=schema, errors=errors,
                                    description_placeholders=placeholders)

    async def async_step_house_holiday_change(self, user_input=None):
        """Which holiday to change or remove (then house_holiday_edit)."""
        house = self._holiday_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        try:
            periods = await self._holiday_periods(house)
        except HomeAssistantError:
            return self.async_abort(reason="house_mode_unavailable")
        if not periods:
            return self.async_abort(reason="house_holidays_none")
        language, errors = self._holiday_language(), {}
        choices = {f"{f}-{u}": (f, u) for f, u in periods}
        if user_input is not None:
            if user_input.get("holiday") in choices:
                self._holiday = choices[user_input["holiday"]]
                return await self.async_step_house_holiday_edit()
            errors["holiday"] = "house_holiday_changed"
        options = [{"value": key, "label": holiday_line(p, language)} for key, p in choices.items()]
        schema = vol.Schema({vol.Required("holiday", default=options[0]["value"]): selector.SelectSelector(
            {"options": options, "mode": "list"})})
        return self.async_show_form(step_id="house_holiday_change", data_schema=schema, errors=errors)

    async def async_step_house_holiday_edit(self, user_input=None):
        house = self._holiday_house()
        original = getattr(self, "_holiday", None)
        if house is None or original is None:
            return self.async_abort(reason="house_mode_unavailable")
        errors = {}
        placeholders = {"error": "", "holiday": holiday_line(original, self._holiday_language())}
        if user_input is not None:
            change = None
            if user_input.get("remove") is True:
                def change(periods):
                    return _without(periods, original)
            else:
                try:
                    period = holiday_input(user_input.get("holiday_from"), user_input.get("holiday_to"))
                except HolidayInputError as err:
                    errors[err.field] = err.code
                else:
                    if period == original:
                        return self.async_abort(reason="e32_room_unchanged")

                    def change(periods):
                        return [*_without(periods, original), period]
            if change is not None and (result := await self._holidays_change(house, change, errors, placeholders)) is not None:
                return result

        def local(utc):
            return dt_util.as_local(dt_util.utc_from_timestamp(utc)).strftime("%Y-%m-%d %H:%M:%S")
        schema = vol.Schema({
            vol.Required("holiday_from", default=local(original[0])): selector.DateTimeSelector(),
            vol.Required("holiday_to", default=local(original[1])): selector.DateTimeSelector(),
            vol.Optional("remove", default=False): selector.BooleanSelector(),
        })
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="house_holiday_edit", data_schema=schema, errors=errors,
                                    description_placeholders=placeholders)

    async def async_step_house_holiday_temperature(self, user_input=None):
        """The temperature on holiday, with the very command of its number entity."""
        house = self._holiday_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        current = holiday_temperature(house.away)
        errors, placeholders = {}, {"error": ""}
        if user_input is not None:
            value = number(user_input.get("holiday_temperature"), *AWAY_LIMITS)
            if value is None:
                errors["holiday_temperature"] = "house_holiday_temperature_invalid"
            elif current is not None and float(value) == float(current):
                return self.async_abort(reason="e32_room_unchanged")
            else:
                try:
                    await house.async_holiday_temperature(value)
                except HomeAssistantError as err:
                    errors["base"] = "house_holiday_not_saved"
                    placeholders["error"] = (getattr(err, "translation_placeholders", None) or {}).get("error") or \
                        getattr(err, "translation_key", None) or "unknown"
                else:
                    return self.async_abort(reason="house_mode_saved")
        schema = vol.Schema({vol.Required("holiday_temperature", default=current if current is not None else 15.0):
                             selector.NumberSelector({"min": AWAY_LIMITS[0], "max": AWAY_LIMITS[1], "step": 0.5, "mode": "box",
                                                      "unit_of_measurement": "°C"})})
        return self.async_show_form(step_id="house_holiday_temperature", data_schema=schema, errors=errors,
                                    description_placeholders=placeholders)

    # -- Smart warm-up and Weather compensation ---------------------------------------

    async def _heating_options(self):
        """(link, the options the E32 stored); (None, an abort result) when they cannot be read."""
        link = flow_link(self.hass, self.config_entry)
        if link is None:
            return None, self.async_abort(reason="e32_rooms_unavailable")
        try:
            return link, await link.async_read_now()
        except HomeAssistantError as err:
            return None, self._e32_abort_failure(err)

    async def _heating_save(self, link, changes):
        """None when the E32 stored every change (one field at a time), else the form's error key."""
        for key, value in changes.items():
            if (error := await self._e32_save_flow_options(link, {key: value})) is not None:
                return error
        return None

    async def async_step_heating_warm_up(self, user_input=None):
        link, stored = await self._heating_options()
        if link is None:
            return stored
        errors = {}
        if user_input is not None:
            value = user_input.get("smart_warm_up")
            if type(value) is not bool:
                errors["base"] = "e32_flow_options_failed"
            elif value == stored["apply_learned"]:
                return self.async_abort(reason="e32_room_unchanged")
            elif (error := await self._heating_save(link, {"apply_learned": value})) is None:
                return self.async_abort(reason="e32_flow_options_saved")
            else:
                errors["base"] = error
        schema = vol.Schema({vol.Required("smart_warm_up", default=stored["apply_learned"]): selector.BooleanSelector()})
        return self.async_show_form(step_id="heating_warm_up", data_schema=schema, errors=errors)

    async def async_step_heating_weather(self, user_input=None):
        link, stored = await self._heating_options()
        if link is None:
            return stored
        design = stored[DESIGN_FLOW_KEY]
        shown = DESIGN_FLOW_AUTOMATIC if design == 0 else str(design)
        errors = {}
        if user_input is not None:
            changes = {}
            on = user_input.get("weather_compensation")
            choice = (user_input.get("advanced") or {}).get("hard_frost_water_temperature", shown)
            if type(on) is not bool or choice not in DESIGN_CHOICES:
                errors["base"] = "e32_flow_options_failed"
            else:
                if on != stored["weather_curve"]:
                    changes["weather_curve"] = on
                wanted = 0 if choice == DESIGN_FLOW_AUTOMATIC else int(choice)
                if wanted != design:
                    changes[DESIGN_FLOW_KEY] = wanted
                if not changes:
                    return self.async_abort(reason="e32_room_unchanged")
                if (error := await self._heating_save(link, changes)) is None:
                    return self.async_abort(reason="e32_flow_options_saved")
                errors["base"] = error
        schema = vol.Schema({
            vol.Required("weather_compensation", default=stored["weather_curve"]): selector.BooleanSelector(),
            vol.Optional("advanced"): section(vol.Schema({
                vol.Required("hard_frost_water_temperature", default=shown): selector.SelectSelector({
                    "options": DESIGN_CHOICES, "translation_key": "flow_design_choice", "mode": "dropdown"}),
            }), {"collapsed": True}),
        })
        return self.async_show_form(step_id="heating_weather", data_schema=schema, errors=errors)
