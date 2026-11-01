"""The devices on the E32's EMS bus as Home Assistant devices (beta.23).

The E32 publishes who is on the bus as the retained ``fw/config/ems_devices``
(address, product, version, brand). Once a device's identity has been read (on
the E32's EMS devices page: "Read device identity") it appears in Home Assistant
as a device "via" the E32, named the way the E32's own page names it
(ems_products.json, generated from data/html/ems-metadata.js), with the product
number as model ID and the device's version as software version. A device whose
identity is unknown is not created; the diagnostics list it. Names the user gave
stay (name_by_user).

A device taken off the bus (2026-11-01: the owner's tado at 0x17) stays in the
E32's list until the E32 restarts; one missing from complete lists (StaleDevices)
for STALE_AFTER_S is removed, and the user may delete it at once.
"""
from datetime import timedelta
import json
import logging
from pathlib import Path
import time

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_TOPIC_PREFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)
TOPIC = "fw/config/ems_devices"
MAX_DEVICES = 16
# The E32 lists the devices heard during this boot and starts empty: after this
# uptime every device on the bus has reported (they send at least every minute).
FULL_LIST_UPTIME_S = 15 * 60
STALE_AFTER_S = 24 * 3600
CHECK_INTERVAL = timedelta(minutes=10)
ROLES = {8: "boiler", 16: "thermostat", 23: "thermostat"}
BRANDS = {1: "Bosch", 2: "Junkers", 3: "Buderus", 4: "Nefit", 5: "Sieger", 11: "Worcester", 13: "IVT"}
_PRODUCTS = None


def products():
    """The product reference; read once in the executor by async_setup_ems_devices."""
    global _PRODUCTS
    if _PRODUCTS is None:
        _PRODUCTS = json.loads((Path(__file__).parent / "ems_products.json").read_text(encoding="utf-8"))
    return _PRODUCTS


def parse(payload):
    """The validated device list of a retained payload, or None (invalid: ignored)."""
    try:
        value = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if type(value) is not dict or value.get("schema") != 1 or type(value.get("devices")) is not list:
        return None
    devices, seen = [], set()
    for item in value["devices"][:MAX_DEVICES]:
        if type(item) is not dict:
            return None
        address, product, version, brand = (item.get(k) for k in ("address", "product_id", "version", "brand_id"))
        if type(address) is not int or not 1 <= address <= 127 or address in seen:
            return None
        if product is not None and (type(product) is not int or not 0 <= product <= 254):
            return None
        if version is not None and (type(version) is not str or len(version) > 7):
            return None
        if brand is not None and (type(brand) is not int or not 0 <= brand <= 254):
            return None
        seen.add(address)
        devices.append({"address": address, "product_id": product, "version": version, "brand_id": brand})
    return devices


def describe(device):
    """name, manufacturer and model of a device with a known product (the E32 page's deviceTitle)."""
    product = device["product_id"]
    if product is None:
        return None
    reference = products()
    candidates = reference["devices"].get(str(product), [])
    expected = ROLES.get(device["address"])
    matched = [c for c in candidates if c["type"] == expected] if expected else candidates
    known = matched[0] if len(matched) == 1 else None  # product IDs are reused between categories
    brand = BRANDS.get(device["brand_id"]) if device["brand_id"] is not None else None
    names = (reference["boiler_names"].get(str(product), {}).get(brand)
             if known is not None and known["type"] == "boiler" and brand else None)
    address = f"0x{device['address']:02X}"
    described = {"manufacturer": brand or "EMS", "model": known["name"] if known else f"EMS {product}"}
    if names:
        return {**described, "name": f"{' / '.join(names)} ({address})"}
    if known is not None:
        return {**described, "name": f"{brand + ' ' if brand else ''}{known['name']} ({address})"}
    # Not in the reference (or ambiguous): a translated generic name (strings.json "device").
    return {**described, "translation_key": f"ems_{ROLES.get(device['address'], 'device')}",
            "translation_placeholders": {"address": address, "product": str(product)}}


def sync_devices(hass, entry, devices, subentry_id=None):
    """Create or update the devices with a known identity; returns their identifiers."""
    prefix = entry.data[CONF_TOPIC_PREFIX]
    registry = dr.async_get(hass)
    hub = registry.async_get_device_by_identifier((DOMAIN, prefix), entry.entry_id)
    done = []
    for device in devices:
        described = describe(device)
        if described is None:
            continue
        identifier = (DOMAIN, f"{prefix}_ems_{device['address']:02x}")
        options = {"config_subentry_id": subentry_id} if subentry_id else {}
        if hub is not None:
            options["via_device_id"] = hub.id
        if "name" in described:
            options["name"] = described["name"]
        else:
            options["translation_key"] = described["translation_key"]
            options["translation_placeholders"] = described["translation_placeholders"]
        registry.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={identifier}, manufacturer=described["manufacturer"],
            model=described["model"], model_id=str(device["product_id"]), sw_version=device["version"], **options)
        done.append(identifier)
    return done


def device_address(prefix, device):
    """The bus address of one of this E32's EMS devices (``<prefix>_ems_xx``), or None."""
    head = f"{prefix}_ems_"
    for domain, identifier in device.identifiers:
        rest = identifier.removeprefix(head)
        if domain == DOMAIN and rest != identifier and len(rest) == 2:
            try:
                return int(rest, 16)
            except ValueError:
                return None
    return None


def listed(hass, entry, complete=False):
    """The addresses in the E32's current bus list, or None while unknown (E32 offline, nothing received).

    complete: only a list of this E32 boot after FULL_LIST_UPTIME_S, never a
    partial or empty list while the E32 is starting.
    """
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    devices, hub = state.get("ems_devices"), state.get("heating_hub")
    if devices is None or hub is None or not hub.fresh:
        return None
    if complete:
        uptime = (hub.heartbeat or {}).get("uptime_s")
        if type(uptime) is not int or uptime < FULL_LIST_UPTIME_S or state.get("ems_devices_boot") != hub.boots:
            return None
    return {device["address"] for device in devices}


class StaleDevices:
    """Removes an EMS device of this entry that complete lists have lacked for STALE_AFTER_S.

    Only this entry's devices with this E32's ``<prefix>_ems_xx`` identifier;
    other devices and other integrations' devices are never touched. Kept in
    memory: after a Home Assistant restart the grace period starts again.
    """

    def __init__(self, hass, entry, clock=time.time):
        self.hass, self.entry, self.clock = hass, entry, clock
        self.missing = {}  # address -> since when complete lists lack it

    @callback
    def check(self, _now=None):
        present = listed(self.hass, self.entry, complete=True)
        if present is None:
            return
        prefix, now = self.entry.data[CONF_TOPIC_PREFIX], self.clock()
        registry = dr.async_get(self.hass)
        gone = {}
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            address = device_address(prefix, device)
            if address is not None and address not in present:
                gone[address] = device
        self.missing = {address: self.missing.get(address, now) for address in gone}
        for address, since in list(self.missing.items()):
            if now - since >= STALE_AFTER_S:
                _LOGGER.info("EMS device 0x%02X is no longer on the bus: removed", address)
                registry.async_remove_device(gone[address].id)
                del self.missing[address]


async def async_setup_ems_devices(hass, entry):
    """Follow the retained fw/config/ems_devices of this E32 (product entries)."""
    from .product import is_product
    if not is_product(entry):
        return
    prefix = entry.data[CONF_TOPIC_PREFIX]
    state = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})
    subentry = None
    try:
        from .installation_group import ensure_installation_group
        subentry = ensure_installation_group(hass, entry)
    except Exception:  # noqa: BLE001 - grouping is cosmetic; the devices still appear
        subentry = None

    await hass.async_add_executor_job(products)  # not in the MQTT callback: that runs in the event loop
    stale = state["ems_stale"] = StaleDevices(hass, entry)

    @callback
    def received(message):
        devices = parse(message.payload)
        if devices is None:
            return
        state["ems_devices"] = devices
        state["ems_devices_boot"] = getattr(state.get("heating_hub"), "boots", None)
        sync_devices(hass, entry, devices, subentry)
        stale.check()

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, f"{prefix}/v1/{TOPIC}", received))
    entry.async_on_unload(async_track_time_interval(hass, stale.check, CHECK_INTERVAL))


def diagnostics(hass, entry):
    """The bus identities for the diagnostics download (no addresses beyond the EMS bus)."""
    return hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("ems_devices")
