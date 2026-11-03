"""Configure → Home → Heating and boiler → Boiler model (rc.3): the model the E32 shows and names.

The same choice as the E32 Boiler page ("My boiler", ``GET/POST /config/boiler-display``
``{"model": <catalog id>}``): the list is the E32's boiler catalog (``boiler_models`` of
ems_products.json, generated from public/boilers/catalog-v1.json), only the models a new choice
may pick plus the one chosen now, and "No boiler selected yet". The E32 answers with what it
stored, which must be the choice. Afterwards the boiler device in Home Assistant is named after
it at once (ems_devices), as it is after the E32's next boiler profile.

Presentation only: the model never changes how the E32 controls the boiler.
"""
from __future__ import annotations

from .const import DOMAIN

NONE = "none"
NONE_LABEL = {"en": "No boiler selected yet", "nl": "Nog geen ketel gekozen", "pl": "Nie wybrano jeszcze kotła"}


def models():
    """{catalog id: {"brand", "name", "selectable"}} of the boiler catalog Home Assistant ships."""
    from .ems_devices import products
    found = products().get("boiler_models")
    return found if type(found) is dict else {}


def options(current, language):
    """The choice list: no boiler, then the selectable models by name, plus the current one."""
    catalog = models()
    lang = language if language in NONE_LABEL else "en"
    shown = [(model_id, item["name"]) for model_id, item in catalog.items()
             if type(item) is dict and type(item.get("name")) is str
             and (item.get("selectable", True) is not False or model_id == current)]
    shown.sort(key=lambda pair: pair[1].casefold())
    return [{"value": NONE, "label": NONE_LABEL[lang]}] + [{"value": v, "label": n} for v, n in shown]


def model_name(model_id, language):
    if model_id == NONE or model_id is None:
        return NONE_LABEL.get(language, NONE_LABEL["en"])
    item = models().get(model_id)
    return item["name"] if type(item) is dict and type(item.get("name")) is str else model_id


class BoilerModelSteps:
    """Mixin for the product options flow: Heating and boiler → Boiler model."""

    def _boiler_language(self):
        from .learned_overview import language
        return language(self.hass)

    async def async_step_boiler_model(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        from .controller_link import ControllerLinkError
        from .e32_system import ABORTS, async_e32_call, failure, link_for
        link = link_for(self.hass, self.config_entry)
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        from .ems_devices import products
        await self.hass.async_add_executor_job(products)  # read once, never in the event loop
        if not models():
            return self.async_abort(reason="e32_settings_update_required")
        lang = self._boiler_language()
        current = getattr(self, "_boiler_model", None)
        if current is None or user_input is None:
            try:
                answer = await async_e32_call(link, lambda c: c.async_boiler_display(), write=False)
            except ControllerLinkError as err:
                return self._system_abort(err)
            current = answer.get("model") if type(answer) is dict else None
            if type(current) is not str:
                return self.async_abort(reason="e32_settings_unreachable",
                                        description_placeholders={"error": "controller_response_invalid"})
            self._boiler_model = current
        choices = options(current, lang)
        errors, placeholders = {}, {"error": "", "current": model_name(current, lang)}
        if user_input is not None:
            chosen = user_input.get("model")
            if chosen not in {c["value"] for c in choices}:
                errors["model"] = "boiler_model_invalid"
            elif chosen == current:
                return self.async_abort(reason="e32_settings_unchanged")
            else:
                try:
                    stored = await async_e32_call(link, lambda c: c.async_boiler_display(chosen), write=True)
                except ControllerLinkError as err:
                    key, values = failure(err)
                    if key in ABORTS:
                        return self.async_abort(reason=key, description_placeholders=values)
                    errors["base"], placeholders = key, {**placeholders, **values}
                else:
                    self._boiler_model = None
                    if type(stored) is not dict or stored.get("model") != chosen:
                        return self.async_abort(reason="e32_settings_unconfirmed")
                    from .ems_devices import MODEL_CHOSEN
                    rename = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {}).get(MODEL_CHOSEN)
                    if rename is not None:
                        rename(chosen)
                    return self.async_abort(reason="boiler_model_saved",
                                            description_placeholders={"model": model_name(chosen, lang)})
        return self.async_show_form(step_id="boiler_model", errors=errors, description_placeholders=placeholders,
                                    data_schema=vol.Schema({vol.Required("model", default=(user_input or {}).get("model", current)):
                                        selector.SelectSelector(selector.SelectSelectorConfig(
                                            options=choices, mode=selector.SelectSelectorMode.DROPDOWN))}))
