"""Configure → Home → Comfort and boiler care: the E32's control knobs (E32 rc.2, ``src/control/ControlTuning.h``).

The same settings as the E32 Home page section of that name, over the stored controller
connection (``GET/POST /config/heating/flow``, the flow link of e32_flow.py: its lock, one
sign-in that waits for a free E32 web session, and a logout afterwards):

- seven knobs the thermostat sets itself (AutoTuner): each one "automatic" or "set by you"
  with your value (``tuning`` plus the exact list ``tuning_manual``);
- three fixed knobs with a standard value (``tuning`` only);
- "Back to automatic for all" (``{"tuning_manual": []}``) and "Back to start values"
  (``{"tuning": null}``: the built-in values, every knob automatic, learning starts again).

Only for firmware that reports both ``tuning`` and ``tuning_manual`` (rc.2 and later);
older firmware shows the knobs read-only on the E32 (and in the learned overview sensor).
Burner times are stored in seconds and shown in minutes, as on the E32 page; the °C knobs
are temperature differences and stay in °C.
"""
from __future__ import annotations

import math

from homeassistant.exceptions import HomeAssistantError

# key: (set by the thermostat itself, built-in value, shown min, max, step, unit, stored per shown unit,
#       decimals of the stored value). Ranges are the E32's own (ControlTuning::knobs).
KNOBS = {
    "min_off_s": (True, 300, 2, 30, 0.5, "min", 60, 0),
    "min_on_s": (True, 300, 2, 30, 0.5, "min", 60, 0),
    "heat_start_c": (True, 0.2, 0.05, 1, 0.05, "°C", 1, 2),
    "heat_stop_c": (True, 0.2, 0, 1, 0.05, "°C", 1, 2),
    "flow_per_degree_c": (True, 10, 2, 30, 1, "°C", 1, 0),
    "floor_lead_min_per_c": (True, 120, 30, 360, 5, "min", 1, 0),
    "radiator_lead_min_per_c": (True, 45, 10, 180, 5, "min", 1, 0),
    "curve_correction_pct": (False, 50, 0, 100, 1, "%", 1, 0),
    "learned_accept_pct": (False, 100, 50, 200, 1, "%", 1, 0),
    "night_saving_min_pct": (False, 2, 0, 20, 1, "%", 1, 0),
}
AUTOMATIC = tuple(key for key, knob in KNOBS.items() if knob[0])


def _stored_ok(key, value):
    _auto, _default, low, high, _step, _unit, scale, decimals = KNOBS[key]
    if type(value) not in (int, float) or not math.isfinite(value):
        return False
    if not low * scale - 1e-9 <= value <= high * scale + 1e-9:
        return False
    return abs(round(value, decimals) - value) < 1e-9


def decode_tuning(value):
    """{"tuning": {...}, "tuning_manual": [...]} of a /config/heating/flow answer, each only when well-formed.

    "tuning" needs every knob with a value the E32 can hold; "tuning_manual" a list of
    automatic knobs (firmware before rc.2 has none: then the knobs cannot be changed here).
    """
    out = {}
    tuning = value.get("tuning") if type(value) is dict else None
    if type(tuning) is dict and all(_stored_ok(key, tuning.get(key)) for key in KNOBS):
        out["tuning"] = {key: tuning[key] for key in KNOBS}
        manual = value.get("tuning_manual")
        if type(manual) is list and all(type(k) is str and k in AUTOMATIC for k in manual):
            out["tuning_manual"] = sorted(set(manual), key=AUTOMATIC.index)
    return out


def shown_value(key, stored):
    """The stored value in the unit the form shows (minutes for burner times)."""
    scale = KNOBS[key][6]
    value = stored / scale
    return round(value, 2) if scale != 1 or KNOBS[key][7] else int(round(value))


def stored_value(key, shown):
    """The value entered in the form as the E32 stores it; ValueError when the E32 would refuse it."""
    _auto, _default, low, high, _step, _unit, scale, decimals = KNOBS[key]
    if type(shown) not in (int, float) or isinstance(shown, bool) or not math.isfinite(shown):
        raise ValueError("care_value_invalid")
    if not low - 1e-9 <= shown <= high + 1e-9:
        raise ValueError("care_value_invalid")
    if scale != 1:
        return int(round(shown * scale))
    value = round(shown, decimals)
    if abs(value - shown) > 1e-6:
        raise ValueError("care_value_invalid")
    return int(value) if decimals == 0 else value


def change_for(key, automatic, stored, settings):
    """The partial POST for one knob, or None when nothing would change.

    automatic: an automatic knob goes back to the thermostat (its value is ignored);
    otherwise the value is the owner's. A fixed knob only takes a value.
    """
    tuning, manual = settings["tuning"], list(settings.get("tuning_manual") or [])
    if KNOBS[key][0]:
        if automatic:
            return {"tuning_manual": [k for k in manual if k != key]} if key in manual else None
        if key in manual and tuning[key] == stored:
            return None
        return {"tuning": {key: stored}, "tuning_manual": [k for k in AUTOMATIC if k in manual or k == key]}
    return None if tuning[key] == stored else {"tuning": {key: stored}}


def range_text(key, lang):
    from .learned_overview import number
    _auto, _default, low, high, _step, unit, _scale, decimals = KNOBS[key]
    digits = 2 if decimals else (1 if KNOBS[key][4] < 1 else 0)
    return f"{number(low, lang, digits)}–{number(high, lang, digits)} {unit}"


def care_offered(hass, entry):
    """False once the flow options were read from firmware without changeable knobs (before rc.2)."""
    from .const import DOMAIN
    from .e32_flow import KEY
    link = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get(KEY)
    if link is None:
        return True  # not read yet: the step reads them and explains an older firmware
    return not link.unsupported and (link.settings is None or "tuning_manual" in link.settings)


# Form errors and abort reasons of a refused or failed E32 request (HomeAssistantError translation keys of e32_flow).
FAILURES = {"flow_settings_rejected": "care_rejected", "flow_settings_unconfirmed": "care_unconfirmed",
            "room_plan_password": "e32_password_changed", "e32_no_free_session": "care_no_free_session"}


def _failure(err):
    key = FAILURES.get(getattr(err, "translation_key", None), "care_unreachable")
    placeholders = dict(getattr(err, "translation_placeholders", None) or {})
    placeholders.setdefault("error", getattr(err, "translation_key", None) or "unknown")
    return key, placeholders


class CareOptionsSteps:
    """Mixin for the product options flow: Configure → Home → Comfort and boiler care."""

    def _care_link(self):
        """The flow-options link of the stored E32 connection (e32_flow), or None without one."""
        from .e32_flow import flow_link
        if self._e32_link() is None:
            return None
        return flow_link(self.hass, self.config_entry)

    def _care_language(self):
        from .learned_overview import language
        return language(self.hass)

    async def async_step_comfort_care(self, user_input=None):
        """What each knob is now, then: change one, back to automatic for all, back to start values."""
        link = self._care_link()
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        try:
            settings = await link.async_read_now()
        except HomeAssistantError as err:
            key, placeholders = _failure(err)
            return self.async_abort(reason="care_unreachable" if key == "care_no_free_session" else key,
                                    description_placeholders=placeholders)
        if "tuning_manual" not in settings:
            return self.async_abort(reason="care_update_required")
        self._care_settings = settings
        from .learned_overview import settings as knob_lines
        lines = knob_lines(settings["tuning"], settings["tuning_manual"], self._care_language())
        options = ["comfort_care_knob"] + (["comfort_care_auto_all"] if settings["tuning_manual"] else []) + [
            "comfort_care_reset"]
        return self.async_show_menu(step_id="comfort_care", menu_options=options, description_placeholders={
            "settings": "\n".join(f"- {name}: {value}" for name, value in lines.items())})

    async def async_step_comfort_care_knob(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        if getattr(self, "_care_settings", None) is None:
            return await self.async_step_comfort_care()
        errors = {}
        if user_input is not None:
            if user_input.get("knob") in KNOBS:
                self._care_knob = user_input["knob"]
                return await self.async_step_comfort_care_value()
            errors["knob"] = "care_knob_invalid"
        return self.async_show_form(step_id="comfort_care_knob", errors=errors, data_schema=vol.Schema({
            vol.Required("knob"): selector.SelectSelector(selector.SelectSelectorConfig(
                options=list(KNOBS), translation_key="comfort_care_knob", mode=selector.SelectSelectorMode.LIST)),
        }))

    async def async_step_comfort_care_value(self, user_input=None):
        """One knob: automatic or your own value (the automatic ones), or its value (the fixed ones)."""
        from homeassistant.helpers import selector
        import probatio as vol
        from .learned_overview import TEXT, knob_value
        settings, key = getattr(self, "_care_settings", None), getattr(self, "_care_knob", None)
        if settings is None or key not in KNOBS:
            return await self.async_step_comfort_care()
        auto, default, low, high, step, unit, _scale, _decimals = KNOBS[key]
        lang = self._care_language()
        current, manual = settings["tuning"][key], settings["tuning_manual"]
        mine = key in manual if auto else current != default
        placeholders = {"name": TEXT[lang]["knob." + key], "current": knob_value(key, current, lang),
                        "mode": TEXT[lang]["yours" if mine else "automatic" if auto else "standard"],
                        "standard": knob_value(key, default, lang), "range": range_text(key, lang), "error": ""}
        errors = {}
        if user_input is not None:
            automatic = bool(user_input.get("automatic")) if auto else False
            try:
                stored = stored_value(key, user_input.get("value")) if not automatic else current
            except ValueError as err:
                errors["value"] = str(err)
            else:
                change = change_for(key, automatic, stored, settings)
                if change is None:
                    return self.async_abort(reason="care_unchanged")
                result = await self._care_send(change, errors, placeholders)
                if result is not None:
                    return result
        fields = {}
        if auto:
            fields[vol.Required("automatic", default=(user_input or {}).get("automatic", not mine))] = \
                selector.BooleanSelector()
        fields[vol.Required("value", default=(user_input or {}).get("value", shown_value(key, current)))] = \
            selector.NumberSelector(selector.NumberSelectorConfig(
                min=low, max=high, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX))
        return self.async_show_form(step_id="comfort_care_auto_value" if auto else "comfort_care_fixed_value",
                                    data_schema=vol.Schema(fields), errors=errors,
                                    description_placeholders=placeholders)

    # The value form has its own text for an automatic and a fixed knob; both submit here.
    async def async_step_comfort_care_auto_value(self, user_input=None):
        return await self.async_step_comfort_care_value(user_input)

    async def async_step_comfort_care_fixed_value(self, user_input=None):
        return await self.async_step_comfort_care_value(user_input)

    async def async_step_comfort_care_auto_all(self, user_input=None):
        return await self._care_confirm("comfort_care_auto_all", {"tuning_manual": []}, user_input)

    async def async_step_comfort_care_reset(self, user_input=None):
        return await self._care_confirm("comfort_care_reset", {"tuning": None}, user_input)

    async def _care_confirm(self, step_id, change, user_input):
        from homeassistant.helpers import selector
        import probatio as vol
        if getattr(self, "_care_settings", None) is None:
            return await self.async_step_comfort_care()
        errors, placeholders = {}, {"error": ""}
        if user_input is not None:
            if not user_input.get("confirm"):
                errors["base"] = "care_confirm"
            else:
                result = await self._care_send(change, errors, placeholders)
                if result is not None:
                    return result
        return self.async_show_form(step_id=step_id, errors=errors, description_placeholders=placeholders,
                                    data_schema=vol.Schema({vol.Required("confirm", default=False): selector.BooleanSelector()}))

    async def _care_send(self, change, errors, placeholders):
        """POST one change; the finished flow on success, else None with the form error set."""
        link = self._care_link()
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        try:
            await link.async_change(change)
        except HomeAssistantError as err:
            key, values = _failure(err)
            if key == "e32_password_changed":
                return self.async_abort(reason=key)
            errors["base"] = key
            placeholders.update(values)
            return None
        self._care_settings = None
        return self.async_abort(reason="care_saved")
