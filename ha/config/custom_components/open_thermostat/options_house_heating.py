"""Configure steps for what the house mode, Smart warm-up and Weather compensation entities also set.

Everything the E32 device offers as a control is also here, in Configure
(options_navigation.py gives each step its Back item):

- House -> House mode and holiday: the house mode (Automatic, At home, Away,
  Holiday) and the holiday end, with the very command of the select and the
  datetime entity (e32_house.HouseState.async_command); "Stop holiday";
- Heating and boiler -> Smart warm-up and -> Weather compensation (with the water
  temperature in hard frost under Advanced): the same E32 link as the switches
  and the select (e32_flow.FlowSettingsLink.async_change).
"""
import probatio as vol
from homeassistant.data_entry_flow import section
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .e32_flow import DESIGN_FLOW_AUTOMATIC, DESIGN_FLOW_KEY, DESIGN_FLOW_LIMITS, flow_link
from .e32_house import MODES, holiday_until, house_mode, supports_house_mode

DESIGN_CHOICES = [DESIGN_FLOW_AUTOMATIC, *(str(c) for c in range(DESIGN_FLOW_LIMITS[0], DESIGN_FLOW_LIMITS[1] + 1))]


class HouseHeatingSteps:
    """Mixin of the product options flow."""

    # -- house mode and holiday -------------------------------------------------------

    async def async_step_house_mode(self, user_input=None):
        house = self._presence_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
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
        return self.async_show_form(step_id="house_mode", data_schema=schema, errors=errors,
                                    description_placeholders=placeholders)

    async def async_step_house_holiday_stop(self, user_input=None):
        house = self._presence_house()
        if house is None:
            return self.async_abort(reason="house_mode_unavailable")
        try:
            await house.async_command("auto", None)
        except HomeAssistantError:
            return self.async_abort(reason="house_mode_unavailable")
        return self.async_abort(reason="house_mode_saved")

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
