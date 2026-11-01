"""The devices on the E32's EMS bus as Home Assistant devices (beta.23).

The E32 publishes who is on the bus as the retained ``fw/config/ems_devices``
(address, product, version, brand). Once a device's identity has been read (on
the E32's EMS devices page: "Read device identity") it appears in Home Assistant
as a device "via" the E32, named the way the E32's own page names it
(ems_products.json, generated from data/html/ems-metadata.js), with the product
number as model ID and the device's version as software version. A device whose
identity is unknown is not created; the diagnostics list it. Devices are never
removed here, and names the user gave stay (name_by_user).
"""
import json
import logging
from pathlib import Path

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr

from .const import CONF_TOPIC_PREFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)
TOPIC = "fw/config/ems_devices"
MAX_DEVICES = 16
ROLES = {8: "boiler", 16: "thermostat", 23: "thermostat"}
BRANDS = {1: "Bosch", 2: "Junkers", 3: "Buderus", 4: "Nefit", 5: "Sieger", 11: "Worcester", 13: "IVT"}
_PRODUCTS = None


def products():
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

    @callback
    def received(message):
        devices = parse(message.payload)
        if devices is None:
            return
        state["ems_devices"] = devices
        sync_devices(hass, entry, devices, subentry)

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, f"{prefix}/v1/{TOPIC}", received))


def diagnostics(hass, entry):
    """The bus identities for the diagnostics download (no addresses beyond the EMS bus)."""
    return hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("ems_devices")
