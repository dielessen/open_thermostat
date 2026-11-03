"""Configure navigation: "← Back" in every submenu, and a menu again after a save.

Home Assistant option flows have no back button and close after a save. This
mixin keeps the trail of menus the user walked through:

- every menu below the first one gets a "back" item (to the menu before it);
- the first menu gets a "done" item that closes the dialog with the options
  unchanged;
- a step that ends with a plain "saved" (or "nothing changed") abort shows
  the menu it was opened from instead, with a short line on top and a "done"
  item, so a user can go on setting things up and close when finished.

Aborts that carry information (errors, "restart the E32", "these IDs changed")
still close the dialog as before.
"""
from functools import wraps

from homeassistant.config_entries import OptionsFlow

SAVED = {"en": "Saved.", "nl": "Opgeslagen.", "pl": "Zapisano."}
UNCHANGED = {"en": "Nothing changed.", "nl": "Niets gewijzigd.", "pl": "Nic się nie zmieniło."}

# Abort reasons that only say "saved" (a menu with SAVED) or "nothing changed" (a menu with UNCHANGED).
SAVED_REASONS = frozenset({
    "comfort_saved", "presence_saved", "installation_saved", "energy_saved", "e32_flow_options_saved",
    "e32_flow_limits_saved", "care_saved", "e32_logging_saved", "e32_time_zone_saved", "boiler_model_saved",
    "house_mode_saved", "room_saved", "e32_room_saved"})
UNCHANGED_REASONS = frozenset({"e32_room_unchanged", "care_unchanged", "e32_settings_unchanged"})

# The room list after a save or removal is the Rooms menu with its own text.
ALIASES = {"e32_rooms_saved": "e32_rooms", "e32_rooms_removed": "e32_rooms"}


class _MenuAgain(dict):
    """An abort result that the step wrapper replaces by the menu the step was opened from."""

    note = ""


def _language(hass):
    language = str(getattr(getattr(hass, "config", None), "language", "en") or "en").split("-")[0]
    return language if language in SAVED else "en"


def _wrap(step):
    @wraps(step)
    async def wrapper(self, *args, **kwargs):
        result = await step(self, *args, **kwargs)
        if isinstance(result, _MenuAgain):
            return await self._menu_again(result.note)
        return result
    return wrapper


class MenuNavigation:
    """Put first in the options flow's bases; call ``wrap_steps`` on the finished class."""

    _menu_trail = None
    _menu_note = ""

    @classmethod
    def wrap_steps(cls):
        for name in dir(cls):
            if name.startswith("async_step_") and name not in ("async_step_back", "async_step_done"):
                step = getattr(cls, name)
                if not getattr(step, "_menu_wrapped", False):
                    wrapped = _wrap(step)
                    wrapped._menu_wrapped = True
                    setattr(cls, name, wrapped)
        return cls

    def _trail(self):
        if self._menu_trail is None:
            self._menu_trail = []
        return self._menu_trail

    def async_show_menu(self, *, step_id=None, menu_options, description_placeholders=None):
        trail = self._trail()
        base = ALIASES.get(step_id, step_id)
        if base in trail:
            del trail[trail.index(base) + 1:]
        else:
            trail.append(base)
        options = list(menu_options)
        note, self._menu_note = self._menu_note, ""
        if len(trail) > 1:
            options.append("back")
        if len(trail) == 1 or note:
            options.append("done")
        placeholders = {**(description_placeholders or {}), "saved": f"**{note}**\n\n" if note else ""}
        return super().async_show_menu(step_id=step_id, menu_options=options, description_placeholders=placeholders)

    def async_abort(self, *, reason, description_placeholders=None):
        result = super().async_abort(reason=reason, description_placeholders=description_placeholders)
        if self._trail() and (reason in SAVED_REASONS or reason in UNCHANGED_REASONS):
            again = _MenuAgain(result)
            again.note = (SAVED if reason in SAVED_REASONS else UNCHANGED)[_language(self.hass)]
            return again
        return result

    async def _menu_again(self, note):
        """The menu this step was opened from, rebuilt (its texts show what was just saved)."""
        self._menu_note = note
        result = await getattr(self, f"async_step_{self._trail()[-1]}")()
        self._menu_note = ""
        return result

    async def async_step_back(self, user_input=None):
        trail = self._trail()
        if len(trail) > 1:
            trail.pop()
        return await getattr(self, f"async_step_{trail[-1] if trail else 'init'}")()

    async def async_step_done(self, user_input=None):
        # The room-flow base classes also define async_create_entry (for subentries): use the options flow's own.
        return OptionsFlow.async_create_entry(self, title="", data=dict(self.config_entry.options))
