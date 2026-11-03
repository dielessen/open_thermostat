"""Test helper: a saved (or unchanged) step now shows the menu it was opened from, with a short line on top."""
from custom_components.open_thermostat.options_navigation import UNCHANGED


def is_again(result, kind="saved"):
    """True when ``result`` is the menu shown again after a save ("saved") or a no-op ("unchanged")."""
    if result.get("type") != "menu":
        return False
    note = result["description_placeholders"].get("saved", "").strip("*\n")
    if kind == "unchanged":
        return note in UNCHANGED.values()
    return bool(note) and note not in UNCHANGED.values()  # "Saved.", or the step's own text with its details
