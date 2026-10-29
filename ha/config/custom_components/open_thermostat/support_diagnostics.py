"""What the diagnostics download adds for an E32 (product entry), and the redaction of everything in it.

For help with problems: the E32 version and the last update result (from the
update entity), a summary of the room plan, the last telemetry (heating
status, summary, learned rooms, plans), the energy inputs and what reached
the E32, the gas counting, the advice and the number of entities per kind.

Never in the file: passwords, tokens, keys (Bluetooth bind keys, AES keys),
addresses (the E32's address, IP and MAC addresses, URLs), Wi-Fi names
(SSID/BSSID) and Bluetooth sensor addresses. Known secret keys are removed
with Home Assistant's ``async_redact_data``; then every remaining text is
checked for IP/MAC addresses, URLs and hexadecimal keys, and Bluetooth sensor
ids are replaced by ``ble_1``, ``ble_2`` ... (also where they are keys).
"""
import re
import time

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN

REDACTED = "**REDACTED**"
# Keys whose value never leaves Home Assistant (matched exactly, at any depth).
TO_REDACT = frozenset({
    "password", "controller_password", "admin_password", "mqtt_password", "broker_password", "wifi_password",
    "passphrase", "psk", "token", "access_token", "refresh_token", "api_key", "apikey", "secret", "client_secret",
    "session", "session_id", "session_token", "adapter_session_id", "nonce", "grant", "cookie", "authorization",
    "username", "mqtt_user", "mqtt_username", "credentials",
    "key", "bind_key", "bindkey", "bind_keys", "aes_key", "encryption_key", "ble_key",
    "address", "controller_address", "host", "hostname", "ip", "ip_address", "ipv4", "ipv6", "gateway",
    "dns", "netmask", "subnet", "mac", "mac_address", "bssid", "ssid", "wifi_ssid", "ap_ssid", "broker",
    "broker_host", "mqtt_host", "url", "uri", "latitude", "longitude",
})
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# Eight groups, or a shortened form with "::" (a clock time such as 12:30:45 is neither).
IPV6 = re.compile(r"(?<![\w:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
                  r"|(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4})*)?)"
                  r"(?![\w:])")
MAC = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")
URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"']+", re.IGNORECASE)
# A bare 12-hex Bluetooth address or a 32-hex (AES-128) key; SHA-256 digests (64) stay.
HEX_SECRET = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{12}|[0-9A-Fa-f]{32})(?![0-9A-Fa-f])")
# Where releases come from: public and needed to tell versions apart.
PUBLIC_URL = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+(?:/[\w./-]*)?")


def _scrub_text(text, aliases):
    for secret, alias in aliases.items():
        text = text.replace(secret, alias).replace(secret.upper(), alias)
    text = URL.sub(lambda m: m.group(0) if PUBLIC_URL.fullmatch(m.group(0)) else REDACTED, text)
    for pattern in (MAC, IPV4, IPV6, HEX_SECRET):
        text = pattern.sub(REDACTED, text)
    return text


def scrub(value, aliases=None):
    """async_redact_data for the known keys, then addresses, URLs and keys inside every text (also dict keys)."""
    aliases = aliases or {}

    def walk(item):
        if isinstance(item, dict):
            return {(_scrub_text(k, aliases) if isinstance(k, str) else k): walk(v) for k, v in item.items()}
        if isinstance(item, (list, tuple, set, frozenset)):
            return [walk(v) for v in item]
        if isinstance(item, str):
            return _scrub_text(item, aliases)
        return item
    return walk(async_redact_data(value, TO_REDACT))


def ble_aliases(hub):
    """{Bluetooth sensor id: "ble_n"} for the sensors the E32 reports."""
    ids = sorted(getattr(hub, "ble", {}) or {}) if hub is not None else []
    return {sensor_id: f"ble_{index}" for index, sensor_id in enumerate(ids, 1)}


def _small(value):
    return type(value) in (bool, int, float) or value is None or (type(value) is str and len(value) <= 64)


def plan_summary(hub):
    """The room plan without schedules or sources: scalars, counts, and per room its scalars and counts."""
    link = getattr(hub, "plan", None) if hub is not None else None
    if link is None:
        return {"connected": False}
    plan = getattr(link, "plan", None)
    result = {"connected": True, "read": plan is not None, "login_rejected": bool(getattr(link, "login_rejected", 0))}
    if type(plan) is not dict:
        return result
    for key, value in plan.items():
        if key == "rooms":
            continue
        result[key] = value if _small(value) else {"count": len(value)} if isinstance(value, (list, dict)) else None
    rooms = []
    for room in plan.get("rooms") or []:
        rooms.append({key: value if _small(value) else len(value) if isinstance(value, (list, dict)) else None
                      for key, value in room.items()})
    result["rooms"] = rooms
    return result


def telemetry(hub, clock=time.monotonic):
    """The last telemetry the E32 sent and how old it is (seconds)."""
    if hub is None:
        return {"hub": False}
    now = clock()

    def age(at):
        return round(now - at, 1) if at is not None else None
    return {"fresh": hub.fresh, "status_age_s": age(hub.last_seen), "status": hub.status,
            "summary_age_s": age(hub.summary_received), "summary": hub.summary,
            "learned": hub.learned, "plans": hub.warmup,
            "learned_messages_age_s": {room: age(at) for room, (at, _, _) in hub.learned_messages.items()}}


def inputs(hass, entry, hub):
    """The energy options, the state of each input entity and what reached the E32."""
    from .energy_input import CONF_GAS_METER, CONF_GAS_PRICE_ENTITY, CONF_OUTDOOR, energy_options
    from .heating_link import learned_inputs
    options = energy_options(entry)
    entities = {}
    for key in (CONF_GAS_METER, CONF_GAS_PRICE_ENTITY, CONF_OUTDOOR):
        if key in options:
            state = hass.states.get(options[key])
            entities[key] = None if state is None else {
                "state": state.state, **{name: state.attributes.get(name) for name in
                                         ("unit_of_measurement", "device_class", "state_class")}}
    header = hub.learned_header if hub is not None and hub.fresh else None
    return {"options": options, "entities": entities, "on_e32": learned_inputs(header),
            "forwarded_room_entities": list((hub.status or {}).get("ha_entities") or []) if hub is not None else []}


def entity_counts(hass, entry):
    """Entities of the entry per platform, disabled and unavailable ones (no stale or duplicate ones hidden)."""
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    per_domain, disabled, unavailable, seen = {}, [], [], {}
    for item in entries:
        per_domain[item.domain] = per_domain.get(item.domain, 0) + 1
        if item.disabled_by is not None:
            disabled.append(item.entity_id)
            continue
        state = hass.states.get(item.entity_id)
        if state is None or state.state == "unavailable":
            unavailable.append(item.entity_id)
        seen.setdefault((item.domain, item.translation_key or item.original_name, item.device_id), []).append(
            item.entity_id)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return {"total": len(entries), "per_domain": dict(sorted(per_domain.items())), "devices": len(devices),
            "disabled": sorted(disabled), "unavailable": sorted(unavailable),
            "possible_duplicates": sorted(ids for ids in seen.values() if len(ids) > 1)}


def _update_entity(hass, entity_id):
    """The live update entity object (its ``last_install`` property), or None."""
    from homeassistant.helpers.entity_component import DATA_INSTANCES
    component = hass.data.get(DATA_INSTANCES, {}).get("update")
    return component.get_entity(entity_id) if component is not None else None


def firmware(hass, entry):
    """The E32 version and the last update result as the update entity and the device registry know them.

    ``last_install`` is the update entity's record of its last install through
    Home Assistant (tag, previous version, SHA-256, size, start/end, duration,
    result, uploads and the identity the E32 reported after its restart):
    the live entity's property, else its state attribute.
    """
    from .firmware_update import valid_install_record
    registry = er.async_get(hass)
    result = {"installed_version": None, "latest_version": None, "last_install": None,
              "last_install_valid": None}
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.domain != "update":
            continue
        state = hass.states.get(item.entity_id)
        if state is not None:
            result.update(installed_version=state.attributes.get("installed_version"),
                          latest_version=state.attributes.get("latest_version"),
                          in_progress=state.attributes.get("in_progress"),
                          last_install=state.attributes.get("last_install"))
        record = getattr(_update_entity(hass, item.entity_id), "last_install", None)
        if isinstance(record, dict):
            result["last_install"] = record
        if isinstance(result["last_install"], dict):
            record = {key: dict(value) if isinstance(value, dict) else value
                      for key, value in result["last_install"].items()}
            result["last_install"], result["last_install_valid"] = record, valid_install_record(record)
        break
    from .const import CONF_TOPIC_PREFIX
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.data.get(CONF_TOPIC_PREFIX)),
                                                               entry.entry_id)
    if device is not None:
        result.update(device_model=device.model, device_sw_version=device.sw_version,
                      device_hw_version=device.hw_version)
    return result


def advice(hass, entry):
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    sensor = state.get("heating_advice")
    if sensor is None:
        return None
    return {"items": [{"id": item["id"], "severity": item["severity"], "confidence": item["confidence"],
                       "values": item["values"]} for item in sensor.items],
            "not_evaluated": {name: missing.reason for name, missing in sensor.missing},
            "observed_days": len(sensor.history.days), "samples": len(sensor.history.samples)}


async def async_product_diagnostics(hass, entry):
    """The E32 part of the diagnostics (not yet redacted: the caller scrubs the whole document)."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    hub = state.get("heating_hub")
    use = state.get("energy_use")
    return {"firmware": firmware(hass, entry), "plan": plan_summary(hub), "telemetry": telemetry(hub),
            "inputs": inputs(hass, entry, hub), "energy": use.diagnostics() if use is not None else None,
            "advice": advice(hass, entry), "entities": entity_counts(hass, entry)}


def device_summary(entry, device):
    """Which device the download is for: its kind and names, never its identifiers' addresses."""
    from .const import CONF_TOPIC_PREFIX
    prefix = entry.data.get(CONF_TOPIC_PREFIX)
    kind = "other"
    for domain, identifier in device.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == prefix:
            kind = "e32"
        elif identifier.startswith(f"{prefix}_e32_room_"):
            kind = "room"
        elif identifier.startswith(f"{prefix}_e32_ble_"):
            kind = "bluetooth_sensor"
    return {"kind": kind, "name": device.name, "name_by_user": device.name_by_user, "model": device.model,
            "manufacturer": device.manufacturer, "sw_version": device.sw_version,
            "identifiers": sorted(identifier for _, identifier in device.identifiers)}
