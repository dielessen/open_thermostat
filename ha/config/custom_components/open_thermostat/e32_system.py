"""E32 system settings from Home Assistant (rc.3): the system log, the time zone and a restart.

Each one goes over the stored controller connection, through the room-plan link's lock: one
sign-in (a change waits for a free E32 web session, as every Home Assistant write does) and a
logout afterwards, so no E32 web session is left open.

- Configure → Advanced and diagnostics → "E32 system log": syslog forwarding (server, port,
  level, which messages) and the level the E32 keeps for its own log page
  (``GET/POST /config/logging``, all fields in one POST, the answer is the read-back).
- Configure → Advanced and diagnostics → "E32 time zone": the zone the E32 week programs run
  in, from the same list as the E32 Settings page, Home Assistant's own zone first. Saved in
  the E32 device settings (``GET/POST /config/device`` with the read's ETag, so a change made
  on the E32 meanwhile is never overwritten; everything else travels back unchanged, the
  secrets stay on the E32) and used after one restart (``POST /updates/reboot``), in the
  same sign-in.
- Repairs "The E32 uses another time zone" (checked from the daily settings backup, the time
  zone step and every change of Home Assistant's own zone); its fix sets Home Assistant's zone
  with the same write, and the issue clears itself once both match.
- the button "Restart E32" (configuration) on the product device: the E32's controlled
  restart; refused while it updates or checks new firmware.

Wi-Fi, MQTT and the E32's own password stay on the E32 (or the existing repair flow): a
wrong value there would cut the very connection Home Assistant uses to put it right.
"""
from __future__ import annotations

import re

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.components.repairs import RepairsFlow
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_TOPIC_PREFIX, DOMAIN

# The E32 Settings page's list (data/html/network.html): POSIX rules -> the zones that use them.
TIME_ZONES = {
    "CET-1CEST,M3.5.0,M10.5.0/3": (
        "Europe/Amsterdam", "Europe/Berlin", "Europe/Brussels", "Europe/Copenhagen", "Europe/Luxembourg",
        "Europe/Madrid", "Europe/Oslo", "Europe/Paris", "Europe/Prague", "Europe/Rome", "Europe/Stockholm",
        "Europe/Vienna", "Europe/Warsaw", "Europe/Zurich", "Europe/Budapest"),
    "GMT0BST,M3.5.0/1,M10.5.0": ("Europe/London",),
    "IST-1GMT0,M10.5.0,M3.5.0/1": ("Europe/Dublin",),
    "WET0WEST,M3.5.0/1,M10.5.0": ("Europe/Lisbon", "Atlantic/Canary"),
    "EET-2EEST,M3.5.0/3,M10.5.0/4": (
        "Europe/Helsinki", "Europe/Athens", "Europe/Bucharest", "Europe/Kyiv", "Europe/Riga", "Europe/Tallinn",
        "Europe/Vilnius", "Europe/Sofia"),
    "<+03>-3": ("Europe/Istanbul",), "MSK-3": ("Europe/Moscow",), "UTC0": ("UTC",),
    "EST5EDT,M3.2.0,M11.1.0": ("America/New_York", "America/Toronto"),
    "CST6CDT,M3.2.0,M11.1.0": ("America/Chicago",), "MST7MDT,M3.2.0,M11.1.0": ("America/Denver",),
    "MST7": ("America/Phoenix",), "PST8PDT,M3.2.0,M11.1.0": ("America/Los_Angeles", "America/Vancouver"),
    "AKST9AKDT,M3.2.0,M11.1.0": ("America/Anchorage",),
    "AEST-10AEDT,M10.1.0,M4.1.0/3": ("Australia/Sydney", "Australia/Melbourne"), "AEST-10": ("Australia/Brisbane",),
    "AWST-8": ("Australia/Perth",), "NZST-12NZDT,M9.5.0,M4.1.0/3": ("Pacific/Auckland",), "JST-9": ("Asia/Tokyo",),
    "CST-8": ("Asia/Shanghai",), "<+08>-8": ("Asia/Singapore",), "IST-5:30": ("Asia/Kolkata",),
    "<+04>-4": ("Asia/Dubai",), "SAST-2": ("Africa/Johannesburg",),
}
ZONE_POSIX = {zone: posix for posix, zones in TIME_ZONES.items() for zone in zones}
# Other names Home Assistant may use for a zone of the list.
ZONE_ALIASES = {"Europe/Kiev": "Europe/Kyiv", "Etc/UTC": "UTC", "Asia/Calcutta": "Asia/Kolkata"}
# Older strings the E32 may hold for the same rules (the beta.17 default).
POSIX_ALIASES = {"CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00": "CET-1CEST,M3.5.0,M10.5.0/3"}

LOG_LEVELS = ("0", "1", "2", "3", "4", "5")  # off, error, warning, info, debug, trace (diagnostics/SystemLog.h)
MARK_LIMITS = (0, 86400)
IPV4 = re.compile(r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}")


def ha_zone(hass):
    zone = getattr(getattr(hass, "config", None), "time_zone", None)
    zone = ZONE_ALIASES.get(zone, zone)
    return zone if zone in ZONE_POSIX else None


def zone_of(posix, prefer=None):
    """The zone shown for the E32's POSIX text: prefer (Home Assistant's) when it has those rules, else the first."""
    posix = POSIX_ALIASES.get(posix, posix)
    if prefer is not None and ZONE_POSIX.get(prefer) == posix:
        return prefer
    zones = TIME_ZONES.get(posix)
    return zones[0] if zones else None


def valid_server(text):
    """The E32's rule (diagnostics/SystemLog.h ipv4): four parts, no leading zeros, first part 1–223."""
    if type(text) is not str or len(text) > 15 or IPV4.fullmatch(text) is None:
        return False
    first = int(text.split(".")[0])
    return 0 < first < 224


def logging_document(user_input, with_sources):
    """The POST body (all fields) from the form; ValueError(<field>, <error>) when the E32 would refuse it."""
    server = (user_input.get("server") or "").strip()
    enabled = bool(user_input.get("syslog_enabled"))
    if server and not valid_server(server) or enabled and not server:
        raise ValueError("server", "e32_log_server_invalid")
    numbers = {}
    for field, (low, high) in (("port", (1, 65535)), ("mark_interval_s", MARK_LIMITS)):
        value = user_input.get(field)
        if type(value) not in (int, float) or isinstance(value, bool) or value != int(value) or not low <= value <= high:
            raise ValueError(field, "e32_log_number_invalid")
        numbers[field] = int(value)
    levels = {}
    for field in ("syslog_level", "web_level"):
        if str(user_input.get(field)) not in LOG_LEVELS:
            raise ValueError(field, "e32_log_number_invalid")
        levels[field] = int(user_input[field])
    document = {"syslog_enabled": enabled, "server": server, "port": numbers["port"],
                "syslog_level": levels["syslog_level"], "web_level": levels["web_level"],
                "mark_interval_s": numbers["mark_interval_s"]}
    if with_sources:
        document.update(syslog_esp=bool(user_input.get("syslog_esp")), syslog_ems=bool(user_input.get("syslog_ems")))
    return document


def decode_logging(value):
    """The E32's logging settings, or None when the answer is not well-formed."""
    if type(value) is not dict:
        return None
    ints = {"port": (1, 65535), "syslog_level": (0, 5), "web_level": (0, 5), "mark_interval_s": MARK_LIMITS}
    if (type(value.get("syslog_enabled")) is not bool or type(value.get("server")) is not str
            or any(type(value.get(k)) is not int or not lo <= value[k] <= hi for k, (lo, hi) in ints.items())):
        return None
    out = {k: value[k] for k in ("syslog_enabled", "server", *ints)}
    if type(value.get("syslog_esp")) is bool and type(value.get("syslog_ems")) is bool:
        out.update(syslog_esp=value["syslog_esp"], syslog_ems=value["syslog_ems"])
    return out


def link_for(hass, entry):
    """The room-plan link of the stored E32 connection (its lock and sign-in), or None without one.

    Only the hub the platforms already set up: building a menu never creates one as a side effect.
    """
    from .room_plan import has_room_plan
    if not has_room_plan(entry):
        return None
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub")
    return getattr(hub, "plan", None)


async def async_e32_call(link, call, *, write):
    """call(client) in one sign-in (RoomPlanLink.async_call); a write waits for a free E32 web session."""
    return await link.async_call(call, write=write)


def failure(err):
    """(form error or abort key, placeholders) of a failed E32 request."""
    from .controller_link import ControllerLoginRejected, ControllerPasswordChangeRequired
    if isinstance(err, ControllerLoginRejected):
        return "e32_password_changed", {}
    if isinstance(err, ControllerPasswordChangeRequired):
        return "e32_settings_password_default", {}
    code = str(err)
    key = {"controller_no_free_session": "e32_settings_no_free_session",
           "controller_session_capacity": "e32_settings_no_free_session",
           "controller_settings_invalid": "e32_settings_invalid",
           "controller_settings_unconfirmed": "e32_settings_unconfirmed",
           "controller_settings_changed": "e32_settings_changed",
           "controller_busy_or_conflict": "e32_settings_busy",
           "controller_update_required": "e32_settings_update_required"}.get(code, "e32_settings_unreachable")
    return key, {"error": code}


# Abort (not a form error) for these: nothing in the form would help.
ABORTS = {"e32_password_changed", "e32_settings_password_default", "e32_settings_update_required"}


class SystemOptionsSteps:
    """Mixin for the product options flow: Configure → Advanced and diagnostics → E32 system log / E32 time zone."""

    def _system_abort(self, err):
        key, placeholders = failure(err)
        if key not in ABORTS:
            key = "e32_settings_unreachable"
        return self.async_abort(reason=key, description_placeholders=placeholders)

    # -- the system log --------------------------------------------------------------

    async def async_step_e32_logging(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        from .controller_link import ControllerLinkError
        link = link_for(self.hass, self.config_entry)
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        errors, placeholders = {}, {"error": ""}
        current = getattr(self, "_e32_logging", None)
        if current is None or user_input is None:
            try:
                current = decode_logging(await async_e32_call(link, lambda c: c.async_logging(), write=False))
            except ControllerLinkError as err:
                return self._system_abort(err)
            if current is None:
                return self.async_abort(reason="e32_settings_unreachable",
                                        description_placeholders={"error": "controller_response_invalid"})
            self._e32_logging = current
        sources = "syslog_esp" in current
        if user_input is not None:
            try:
                document = logging_document(user_input, sources)
            except ValueError as err:
                errors[err.args[0]] = err.args[1]
            else:
                if document == {k: current[k] for k in document}:
                    return self.async_abort(reason="e32_settings_unchanged")
                try:
                    stored = decode_logging(await async_e32_call(
                        link, lambda c: c.async_logging(document), write=True))
                except ControllerLinkError as err:
                    key, values = failure(err)
                    if key in ABORTS:
                        return self.async_abort(reason=key, description_placeholders=values)
                    errors["base"], placeholders = key, {**placeholders, **values}
                else:
                    self._e32_logging = None
                    if stored is None or any(stored.get(k) != v for k, v in document.items()):
                        return self.async_abort(reason="e32_settings_unconfirmed")
                    return self.async_abort(reason="e32_logging_saved")
        shown = {**current, **{k: v for k, v in (user_input or {}).items()}}
        level = selector.SelectSelector(selector.SelectSelectorConfig(
            options=list(LOG_LEVELS), translation_key="e32_log_level", mode=selector.SelectSelectorMode.DROPDOWN))
        fields = {
            vol.Required("syslog_enabled", default=bool(shown["syslog_enabled"])): selector.BooleanSelector(),
            vol.Optional("server", description={"suggested_value": shown["server"] or None}): selector.TextSelector(),
            vol.Required("port", default=shown["port"]): selector.NumberSelector(selector.NumberSelectorConfig(
                min=1, max=65535, step=1, mode=selector.NumberSelectorMode.BOX)),
            vol.Required("syslog_level", default=str(shown["syslog_level"])): level,
        }
        if sources:
            fields[vol.Required("syslog_esp", default=bool(shown["syslog_esp"]))] = selector.BooleanSelector()
            fields[vol.Required("syslog_ems", default=bool(shown["syslog_ems"]))] = selector.BooleanSelector()
        fields[vol.Required("web_level", default=str(shown["web_level"]))] = level
        fields[vol.Required("mark_interval_s", default=shown["mark_interval_s"])] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=MARK_LIMITS[0], max=MARK_LIMITS[1], step=1, unit_of_measurement="s",
                                          mode=selector.NumberSelectorMode.BOX))
        return self.async_show_form(step_id="e32_logging", data_schema=vol.Schema(fields), errors=errors,
                                    description_placeholders=placeholders)

    # -- the time zone ---------------------------------------------------------------

    async def async_step_e32_time_zone(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        from .controller_link import ControllerLinkError
        link = link_for(self.hass, self.config_entry)
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        if getattr(self, "_e32_zone", None) is None or user_input is None:
            try:
                settings, _tag = await async_e32_call(link, lambda c: c.async_read("/config/device"), write=False)
            except ControllerLinkError as err:
                return self._system_abort(err)
            if type(settings) is not dict or type(settings.get("timeZone")) is not str:
                return self.async_abort(reason="e32_settings_update_required")
            self._e32_zone = settings["timeZone"]
            check_time_zone(self.hass, self.config_entry, self._e32_zone)
        posix, home = self._e32_zone, ha_zone(self.hass)
        current = zone_of(posix, home)
        errors, placeholders = {}, {"error": "", "e32": current or posix or "-",
                                    "home": getattr(self.hass.config, "time_zone", None) or "-"}
        if user_input is not None:
            chosen = user_input.get("time_zone")
            if chosen not in ZONE_POSIX:
                errors["time_zone"] = "e32_time_zone_invalid"
            elif ZONE_POSIX[chosen] == POSIX_ALIASES.get(posix, posix):
                return self.async_abort(reason="e32_settings_unchanged")
            else:
                try:
                    await async_e32_call(link, lambda c: async_write_zone(c, ZONE_POSIX[chosen], posix), write=True)
                except ControllerLinkError as err:
                    key, values = failure(err)
                    if key in ABORTS:
                        return self.async_abort(reason=key, description_placeholders=values)
                    errors["base"], placeholders = key, {**placeholders, **values}
                    self._e32_zone = None  # read again: the E32 may have changed meanwhile
                else:
                    self._e32_zone = None
                    check_time_zone(self.hass, self.config_entry, ZONE_POSIX[chosen])
                    return self.async_abort(reason="e32_time_zone_saved", description_placeholders={"zone": chosen})
        zones = sorted(ZONE_POSIX)
        default = home or current or zones[0]
        return self.async_show_form(step_id="e32_time_zone", errors=errors, description_placeholders=placeholders,
                                    data_schema=vol.Schema({vol.Required("time_zone", default=default): selector.SelectSelector(
                                        selector.SelectSelectorConfig(options=zones, mode=selector.SelectSelectorMode.DROPDOWN))}))



async def async_write_zone(client, posix, expected=None):
    """In one sign-in: read the device settings (fresh ETag), change only the time zone, save, read back, restart.

    expected: the zone the form showed; another one on the E32 now is controller_settings_changed.
    """
    from .controller_link import ControllerLinkError
    settings, tag = await client.async_read("/config/device")
    if type(settings) is not dict or type(settings.get("timeZone")) is not str:
        raise ControllerLinkError("controller_update_required")
    if expected is not None and settings.get("timeZone") != expected:
        raise ControllerLinkError("controller_settings_changed")
    document = {**settings, "timeZone": posix}
    if type(document.get("mqtt")) is dict:
        # Shown by the E32 on a read, never stored (REST.h configDevice).
        document["mqtt"] = {k: v for k, v in document["mqtt"].items()
                            if k not in ("native_source_device_id", "native_source_live_apply")}
    await client.async_save_settings(document, tag)
    saved, _ = await client.async_read("/config/device")
    if type(saved) is not dict or saved.get("timeZone") != posix:
        raise ControllerLinkError("controller_settings_unconfirmed")
    await client.async_reboot()


# -- Repairs: the E32's time zone differs from Home Assistant's --------------------------

TIME_ZONE_ISSUE = "e32_time_zone"
TIME_ZONE_STATE = "e32_time_zone_posix"  # hass.data state key: the E32's zone as last seen


def time_zone_issue_id(entry):
    return f"{TIME_ZONE_ISSUE}_{entry.entry_id}"


@callback
def check_time_zone(hass, entry, posix=None):
    """Show or clear "The E32 uses another time zone" for the E32's POSIX text (None: the last one seen).

    Only for a Home Assistant zone the E32 knows (its Settings list); unknown on either side
    shows nothing. Sources: the daily settings backup, the E32 time zone step, and a change of
    Home Assistant's own time zone.
    """
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is None:
        return
    if type(posix) is str:
        state[TIME_ZONE_STATE] = posix
    posix = state.get(TIME_ZONE_STATE)
    home = ha_zone(hass)
    issue = time_zone_issue_id(entry)
    if type(posix) is not str or home is None or ZONE_POSIX[home] == POSIX_ALIASES.get(posix, posix):
        ir.async_delete_issue(hass, DOMAIN, issue)
        return
    ir.async_create_issue(hass, DOMAIN, issue, is_fixable=True, is_persistent=False,
                          severity=ir.IssueSeverity.WARNING, translation_key=TIME_ZONE_ISSUE,
                          translation_placeholders={"name": entry.title, "e32": zone_of(posix) or posix,
                                                    "home": home},
                          data={"entry_id": entry.entry_id})


def _backup_zone(manager):
    """The time zone in the newest settings backup (its cleartext network section), or None."""
    records = manager.records() if manager is not None else []
    network = records[0].get("document", {}).get("network") if records else None
    zone = network.get("timeZone") if type(network) is dict else None
    return zone if type(zone) is str else None


@callback
def setup_time_zone_check(hass, entry, backups):
    """Check at start, after every backup and when Home Assistant's time zone changes; returns the undo."""
    from homeassistant.const import EVENT_CORE_CONFIG_UPDATE
    removers = []

    @callback
    def from_backup():
        zone = _backup_zone(backups)
        if zone is not None:
            check_time_zone(hass, entry, zone)

    if backups is not None:
        removers.append(backups.add_listener(from_backup))
        from_backup()
    @callback
    def home_changed(_event):  # in the event loop: the issue registry is not thread-safe
        check_time_zone(hass, entry)

    removers.append(hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, home_changed))

    @callback
    def remove():
        for undo in removers:
            undo()
        ir.async_delete_issue(hass, DOMAIN, time_zone_issue_id(entry))
    return remove


class TimeZoneRepairFlow(RepairsFlow):
    """One confirmation: the E32 takes Home Assistant's time zone (and restarts once)."""

    def __init__(self, issue_id, data):
        self._issue_id, self._data = issue_id, data if isinstance(data, dict) else {}

    async def async_step_init(self, user_input=None):
        return await self.async_step_confirm_time_zone(user_input)

    async def async_step_confirm_time_zone(self, user_input=None):
        from .controller_link import ControllerLinkError
        entry = self.hass.config_entries.async_get_entry(self._data.get("entry_id"))
        link = link_for(self.hass, entry) if entry is not None else None
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        home = ha_zone(self.hass)
        if home is None:
            ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
            return self.async_abort(reason="e32_time_zone_unknown")
        state = self.hass.data[DOMAIN][entry.entry_id]
        placeholders = {"name": entry.title, "home": home, "error": "",
                        "e32": zone_of(state.get(TIME_ZONE_STATE) or "") or state.get(TIME_ZONE_STATE) or "-"}
        if user_input is None:
            return self.async_show_form(step_id="confirm_time_zone", description_placeholders=placeholders)
        posix = ZONE_POSIX[home]
        try:
            await async_e32_call(link, lambda c: async_write_zone(c, posix), write=True)
        except ControllerLinkError as err:
            key, values = failure(err)
            if key in ABORTS:
                return self.async_abort(reason=key, description_placeholders=values)
            return self.async_show_form(step_id="confirm_time_zone", errors={"base": key},
                                        description_placeholders={**placeholders, **values})
        check_time_zone(self.hass, entry, posix)
        return self.async_create_entry(data={})


# -- the restart button ----------------------------------------------------------------

RESTART_ERRORS = {"e32_password_changed": "room_plan_password", "e32_settings_no_free_session": "e32_no_free_session",
                  "e32_settings_busy": "e32_restart_busy", "e32_settings_password_default": "e32_password_change_required"}


class E32RestartButton(ButtonEntity):
    """"Restart E32": the E32's controlled restart (POST /updates/reboot); the heating continues after it."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "e32_restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, entry):
        prefix = entry.data[CONF_TOPIC_PREFIX]
        self._entry = entry
        self._attr_unique_id = f"{prefix}_e32_restart"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})

    async def async_press(self):
        from .controller_link import ControllerLinkError
        link = link_for(self.hass, self._entry)
        if link is None:
            from .room_plan import link_error
            raise link_error("no_controller_connection")
        try:
            await async_e32_call(link, lambda client: client.async_reboot(), write=True)
        except ControllerLinkError as err:
            key, placeholders = failure(err)
            raise HomeAssistantError(translation_domain=DOMAIN,
                                     translation_key=RESTART_ERRORS.get(key, "e32_restart_failed"),
                                     translation_placeholders=placeholders if key not in RESTART_ERRORS else None
                                     ) from None


async def async_setup_buttons(hass, entry, async_add_entities):
    """The restart button of a product entry with a stored E32 connection."""
    from .product import is_product
    if not is_product(entry) or link_for(hass, entry) is None:
        return
    from .installation_group import ensure_installation_group
    async_add_entities([E32RestartButton(hass, entry)], config_subentry_id=ensure_installation_group(hass, entry))
