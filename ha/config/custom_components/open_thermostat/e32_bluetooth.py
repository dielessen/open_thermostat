"""Configure → Advanced and diagnostics → Bluetooth sensors (rc.3): rename or forget paired sensors.

The same list as the E32's Bluetooth sensors page (``GET/POST /config/bluetooth``). Changes are
collected first and saved together, because every save restarts the E32 about 30 seconds later
(it reloads its Bluetooth listener): several renames and removals are one save, one restart.

The save reads the list again in the same sign-in (its ETag), checks that it still holds the
sensors this form showed, and posts the whole remaining list with that ETag; a change made on the
E32 page meanwhile is refused (412) and nothing is written. Each row says ``"key_action": "keep"``:
bindkeys never travel through Home Assistant. Pairing a new sensor (scan, profile, bindkey) stays on
the E32, next to the sensor. Which room a sensor measures is set per room (Configure → Rooms).
"""
from __future__ import annotations

import re

ADDRESS = re.compile(r"[0-9a-f]{12}")
PROFILES = ("shelly_ht_display", "xiaomi_monitor_3", "shelly_blu_trv", "pvvx_thermometer")
ENCRYPTIONS = ("none", "bthome_v2", "mibeacon_v4_v5")
NAME_BYTES = 40  # ManagedBleBinding name (BleDeviceConfig.h validManagedBleName)
# The E32's refusals that have their own message; the rest name the E32's code.
REFUSALS = {"invalid_device_name": "ble_name_invalid", "bluetooth_storage_full": "ble_storage_full",
            "bluetooth_resources_unavailable": "e32_settings_busy"}


def decode_sensors(value):
    """The paired sensors [{address, profile, encryption, name}] of a GET answer, or None."""
    rows = value.get("devices") if type(value) is dict and value.get("schema") == 1 else None
    if type(rows) is not list:
        return None
    sensors = []
    for row in rows:
        if (type(row) is not dict or type(row.get("address")) is not str or ADDRESS.fullmatch(row["address"]) is None
                or row.get("profile") not in PROFILES or row.get("encryption") not in ENCRYPTIONS
                or type(row.get("name")) is not str):
            return None
        sensors.append({key: row[key] for key in ("address", "profile", "encryption", "name")})
    return sensors


def valid_name(name):
    """The E32's rule: 1–40 UTF-8 bytes, no control characters, something visible."""
    return (type(name) is str and name.strip() != "" and len(name.encode()) <= NAME_BYTES
            and not any(ord(c) < 32 or ord(c) == 127 for c in name))


def save_document(sensors, names, forget):
    """The POST body: every remaining sensor with its (new) name, its key kept on the E32."""
    return {"devices": [{"address": s["address"], "profile": s["profile"], "encryption": s["encryption"],
                         "name": names.get(s["address"], s["name"]), "key_action": "keep"}
                        for s in sensors if s["address"] not in forget]}


def same_sensors(old, new):
    key = lambda rows: sorted((s["address"], s["profile"], s["encryption"], s["name"]) for s in rows)  # noqa: E731
    return new is not None and key(old) == key(new)


class BluetoothOptionsSteps:
    """Mixin for the product options flow: the Bluetooth sensors, renamed and forgotten in one save."""

    def _ble_label(self, sensor):
        return f"{sensor['name'] or sensor['address']} ({sensor['address']})"

    def _ble_rooms(self, address):
        """The rooms that measure with this sensor (from the room plan HA last read)."""
        from .e32_system import link_for
        link = link_for(self.hass, self.config_entry)
        plan = getattr(link, "plan", None) if link is not None else None
        rooms = plan.get("rooms", []) if type(plan) is dict else []
        return [room.get("name") or room.get("id") for room in rooms if type(room) is dict and any(
            type(s) is dict and s.get("type") == "ble" and s.get("id") == address for s in room.get("sources", []))]

    def _ble_summary(self):
        from .learned_overview import language
        lang = language(self.hass)
        words = {"en": ("new name", "will be forgotten", "no changes yet"),
                 "nl": ("nieuwe naam", "wordt vergeten", "nog geen wijzigingen"),
                 "pl": ("nowa nazwa", "zostanie usunięty", "na razie bez zmian")}[lang]
        state = self._ble
        lines = []
        for sensor in state["sensors"]:
            line = f"- {self._ble_label(sensor)}"
            if sensor["address"] in state["forget"]:
                line += f": {words[1]}"
            elif sensor["address"] in state["names"]:
                line += f" → {words[0]}: {state['names'][sensor['address']]}"
            lines.append(line)
        pending = bool(state["forget"] or state["names"])
        return "\n".join(lines), pending, ("" if pending else words[2])

    async def async_step_ble_sensors(self, user_input=None):
        from .controller_link import ControllerLinkError
        from .e32_system import async_e32_call, link_for
        link = link_for(self.hass, self.config_entry)
        if link is None:
            return self.async_abort(reason="e32_rooms_unavailable")
        if getattr(self, "_ble", None) is None:
            try:
                value, _tag = await async_e32_call(link, lambda c: c.async_bluetooth(), write=False)
            except ControllerLinkError as err:
                return self._system_abort(err)
            sensors = decode_sensors(value)
            if sensors is None:
                return self.async_abort(reason="e32_settings_unreachable",
                                        description_placeholders={"error": "controller_response_invalid"})
            if not sensors:
                return self.async_abort(reason="ble_none")
            self._ble = {"sensors": sensors, "names": {}, "forget": set()}
        sensors, pending, note = self._ble_summary()
        left = [s for s in self._ble["sensors"] if s["address"] not in self._ble["forget"]]
        options = (["ble_rename", "ble_forget"] if left else []) + (["ble_save"] if pending else [])
        return self.async_show_menu(step_id="ble_sensors", menu_options=options,
                                    description_placeholders={"sensors": sensors, "pending": note})

    def _ble_choices(self):
        return [{"value": s["address"], "label": self._ble_label(s)} for s in self._ble["sensors"]
                if s["address"] not in self._ble["forget"]]

    async def async_step_ble_rename(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        if getattr(self, "_ble", None) is None:
            return await self.async_step_ble_sensors()
        choices = self._ble_choices()
        errors = {}
        if user_input is not None:
            address, name = user_input.get("sensor"), (user_input.get("name") or "").strip()
            if address not in {c["value"] for c in choices}:
                errors["sensor"] = "ble_sensor_invalid"
            elif not valid_name(name):
                errors["name"] = "ble_name_invalid"
            else:
                current = next(s["name"] for s in self._ble["sensors"] if s["address"] == address)
                if name == current:
                    self._ble["names"].pop(address, None)
                else:
                    self._ble["names"][address] = name
                return await self.async_step_ble_sensors()
        return self.async_show_form(step_id="ble_rename", errors=errors, data_schema=vol.Schema({
            vol.Required("sensor", default=(user_input or {}).get("sensor", choices[0]["value"])): selector.SelectSelector(
                selector.SelectSelectorConfig(options=choices, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required("name", default=(user_input or {}).get("name", "")): selector.TextSelector(),
        }))

    async def async_step_ble_forget(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        if getattr(self, "_ble", None) is None:
            return await self.async_step_ble_sensors()
        choices = self._ble_choices()
        errors = {}
        if user_input is not None:
            chosen = list(user_input.get("sensors") or [])
            if not chosen or any(a not in {c["value"] for c in choices} for a in chosen):
                errors["sensors"] = "ble_sensor_invalid"
            else:
                for address in chosen:
                    self._ble["forget"].add(address)
                    self._ble["names"].pop(address, None)
                return await self.async_step_ble_sensors()
        used = [f"- {self._ble_label(s)}: {', '.join(self._ble_rooms(s['address']))}"
                for s in self._ble["sensors"] if s["address"] not in self._ble["forget"] and self._ble_rooms(s["address"])]
        return self.async_show_form(step_id="ble_forget", errors=errors,
                                    description_placeholders={"used": "\n".join(used) or "-"},
                                    data_schema=vol.Schema({vol.Required("sensors"): selector.SelectSelector(
                                        selector.SelectSelectorConfig(options=choices, multiple=True,
                                                                      mode=selector.SelectSelectorMode.LIST))}))

    async def async_step_ble_save(self, user_input=None):
        from homeassistant.helpers import selector
        import probatio as vol
        from .controller_link import BluetoothRejected, ControllerLinkError
        from .e32_system import ABORTS, async_e32_call, failure, link_for
        if getattr(self, "_ble", None) is None:
            return await self.async_step_ble_sensors()
        sensors, pending, _note = self._ble_summary()
        if not pending:
            return await self.async_step_ble_sensors()
        errors, placeholders = {}, {"sensors": sensors, "error": ""}
        if user_input is not None:
            if not user_input.get("confirm"):
                errors["base"] = "care_confirm"
            else:
                link = link_for(self.hass, self.config_entry)
                if link is None:
                    return self.async_abort(reason="e32_rooms_unavailable")
                state = self._ble
                document = save_document(state["sensors"], state["names"], state["forget"])

                async def save(client):
                    value, tag = await client.async_bluetooth()
                    if not same_sensors(state["sensors"], decode_sensors(value)):
                        raise ControllerLinkError("controller_settings_changed")
                    return await client.async_bluetooth(document, tag)
                try:
                    answer = await async_e32_call(link, save, write=True)
                except BluetoothRejected as err:
                    errors["base"] = REFUSALS.get(err.error, "ble_rejected")
                    placeholders["error"] = err.error
                except ControllerLinkError as err:
                    key, values = failure(err)
                    if key in ABORTS:
                        return self.async_abort(reason=key, description_placeholders=values)
                    if key == "e32_settings_changed":
                        self._ble = None  # read the list again before the next try
                        return self.async_abort(reason="ble_changed")
                    errors["base"], placeholders = key, {**placeholders, **values}
                else:
                    self._ble = None
                    if type(answer) is not dict:
                        return self.async_abort(reason="e32_settings_unconfirmed")
                    if answer.get("changed") is False:
                        return self.async_abort(reason="e32_settings_unchanged")
                    return self.async_abort(reason="ble_saved" if answer.get("restart_scheduled") is not False
                                            else "ble_saved_restart_later")
        return self.async_show_form(step_id="ble_save", errors=errors, description_placeholders=placeholders,
                                    data_schema=vol.Schema({vol.Required("confirm", default=False): selector.BooleanSelector()}))
