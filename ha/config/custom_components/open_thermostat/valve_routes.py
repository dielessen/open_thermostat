"""Which way a radiator valve is driven: by the E32 itself over Zigbee2MQTT, or through Home Assistant.

The room form only asks for the valves' climate entities. For each one Home
Assistant's own registries decide the route:

- a Zigbee2MQTT valve (an ``mqtt`` climate entity on a device with the
  identifier ``zigbee2mqtt_0x…``) of a model the E32 drives itself
  (``src/control/TrvConfig.h`` trvModels: Bosch BTH-RA, Sonoff TRVZB, Sonoff TRV
  Gen2 / TRV-ZBT, Tuya TV02) on the E32's Zigbee2MQTT base topic: the E32 gets
  its Zigbee2MQTT friendly name and model and drives it over MQTT, also while
  Home Assistant is down ("works without Home Assistant");
- every other valve (ZHA, Z-Wave, Shelly, a cloud integration, a Zigbee2MQTT
  valve of another model or another Zigbee2MQTT instance): model
  ``ha_climate`` with its entity ID, driven by Home Assistant on the E32's
  rules (ha_valves.py, "through Home Assistant").

The friendly name comes from the device's MQTT topics (``<base>/<friendly
name>``, from the MQTT integration's debug info of its entities), not from the
Home Assistant device name: a device renamed in Home Assistant keeps its
Zigbee2MQTT name. Without known topics the device name Zigbee2MQTT gave it
(``name``, never ``name_by_user``) is used.

A valve stored before (the E32 valve record) keeps its route and model: a
Zigbee2MQTT valve maps back to its entity by its friendly name; one Home
Assistant no longer knows stays as stored and is listed as kept.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .e32_valves import HA_MODEL, ZIGBEE_MODELS, guess_model, valid_entity, valid_name

Z2M_PREFIX = "zigbee2mqtt_"
Z2M_BRIDGE_PREFIX = "zigbee2mqtt_bridge_"
# Topics of a Zigbee2MQTT device that are not its state topic <base>/<friendly name>.
OTHER_TOPIC_ENDS = ("/availability", "/set", "/get")
# The models the E32 drives itself; "generic" (setpoint only) is chosen by hand only.
AUTOMATIC_MODELS = tuple(m for m in ZIGBEE_MODELS if m != "generic")

ROUTE_TEXT = {
    "en": {"direct": "works without Home Assistant", "ha": "through Home Assistant",
           "kept": "not found in Home Assistant, kept as it was", "none": "No radiator valves yet.",
           "unknown": "model not recognised"},
    "nl": {"direct": "werkt zonder Home Assistant", "ha": "via Home Assistant",
           "kept": "niet gevonden in Home Assistant, blijft zoals hij was", "none": "Nog geen radiatorkranen.",
           "unknown": "model niet herkend"},
    "pl": {"direct": "działa bez Home Assistant", "ha": "przez Home Assistant",
           "kept": "nie znaleziono w Home Assistant, pozostaje bez zmian", "none": "Brak zaworów grzejnikowych.",
           "unknown": "model nierozpoznany"},
}
ROUTE_HEADING = {"en": "Radiator valves:", "nl": "Radiatorkranen:", "pl": "Zawory grzejnikowe:"}
MODEL_NAMES = {"bosch_bth_ra": "Bosch BTH-RA", "sonoff_trvzb": "Sonoff TRVZB", "sonoff_trv_zbt": "Sonoff TRV Gen2",
               "tuya_tv02": "Tuya TV02", "generic": "Zigbee2MQTT"}


@dataclass(frozen=True)
class ValveRoute:
    """One valve as the E32 stores it ({name, model}) and what Home Assistant knows about it."""

    name: str                    # the record's name: the friendly name (direct) or the entity ID
    model: str                   # one of ZIGBEE_MODELS (direct) or HA_MODEL
    entity_id: str | None = None  # None: a stored valve Home Assistant does not know (kept)
    friendly: str | None = None  # its Zigbee2MQTT friendly name on the E32's base topic, if it has one
    detected: str | None = None  # the model recognised from Home Assistant's device registry

    @property
    def direct(self):
        return self.model != HA_MODEL

    def record(self):
        return {"name": self.name, "model": self.model}


def is_z2m_device(device):
    """A device Zigbee2MQTT announced over MQTT discovery (not its bridge)."""
    return device is not None and any(
        domain == "mqtt" and str(ident).startswith(Z2M_PREFIX) and not str(ident).startswith(Z2M_BRIDGE_PREFIX)
        for domain, ident in device.identifiers)


def detect_model(device):
    """Our model id from the device's manufacturer, model and model id, or None (not recognised)."""
    text = " ".join(str(v or "") for v in (device.manufacturer, device.model, getattr(device, "model_id", None)))
    model = guess_model(text)
    return model if model in AUTOMATIC_MODELS else None


def friendly_from_topics(topics, base_topic):
    """The friendly name in <base>/<friendly name> that the topics agree on, or None.

    Availability, command and bridge topics are left out; two different names
    (a device that moved between names while its entities were set up) give None.
    """
    prefix = str(base_topic or "").rstrip("/") + "/"
    counts = Counter()
    for topic in topics:
        if type(topic) is not str or not topic.startswith(prefix) or "+" in topic or "#" in topic:
            continue
        rest = topic[len(prefix):]
        if not rest or rest == "bridge" or rest.startswith("bridge/") or rest.endswith(OTHER_TOPIC_ENDS):
            continue
        counts[rest] += 1
    ranked = counts.most_common(2)
    if not ranked or len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0] if valid_name(ranked[0][0]) else None


def device_topics(hass, device_id):
    """The MQTT topics of a device's entities (subscriptions and discovery), from the MQTT debug info."""
    try:
        from homeassistant.components.mqtt.debug_info import info_for_device
        info = info_for_device(hass, device_id)
    except Exception:  # noqa: BLE001 - MQTT not set up (yet): no topics, the device name is used
        return []
    topics = []
    for entity in info.get("entities", []):
        topics += [s.get("topic") for s in entity.get("subscriptions", []) if type(s) is dict]
        payload = (entity.get("discovery_data") or {}).get("payload")
        if isinstance(payload, dict):
            topics += [v for k, v in payload.items() if str(k).endswith("_topic") and type(v) is str
                       and not str(k).endswith("command_topic")]
    return [t for t in topics if type(t) is str]


def friendly_name(hass, device, base_topic):
    """The device's Zigbee2MQTT friendly name on the E32's base topic, or None.

    From its topics when Home Assistant knows them (a device on another base
    topic is not reachable for the E32: None); otherwise the name Zigbee2MQTT
    gave the device (never the name the user gave it in Home Assistant).
    """
    topics = device_topics(hass, device.id)
    if topics:
        return friendly_from_topics(topics, base_topic)
    return device.name if valid_name(device.name) and not str(device.name).startswith("Zigbee2MQTT") else None


class RouteFinder:
    """Routes for climate entities and the entities of stored valves, for one form."""

    def __init__(self, hass, base_topic):
        self.hass, self.base_topic = hass, base_topic or "zigbee2mqtt"
        self.entities, self.devices = er.async_get(hass), dr.async_get(hass)
        self._index = None

    def _z2m(self, entity_id):
        """(device, friendly name) of a Zigbee2MQTT climate entity, else (None, None)."""
        entry = self.entities.async_get(entity_id)
        if entry is None or entry.platform != "mqtt" or not entry.device_id:
            return None, None
        device = self.devices.async_get(entry.device_id)
        if not is_z2m_device(device):
            return None, None
        return device, friendly_name(self.hass, device, self.base_topic)

    def route(self, entity_id, model=None):
        """The route of a newly chosen climate entity; model: the installer's choice (Advanced), if any."""
        device, friendly = self._z2m(entity_id)
        detected = detect_model(device) if device is not None else None
        chosen = detected if model is None else model
        if friendly and chosen in ZIGBEE_MODELS:
            return ValveRoute(friendly, chosen, entity_id, friendly, detected)
        return ValveRoute(entity_id, HA_MODEL, entity_id, friendly, detected)

    def z2m_details(self, entity_id):
        """(friendly name, detected model, device model text) for the Advanced step; None when not Zigbee2MQTT."""
        device, friendly = self._z2m(entity_id)
        if device is None or not friendly:
            return None
        text = " ".join(str(v) for v in (device.manufacturer, device.model, getattr(device, "model_id", None)) if v)
        return friendly, detect_model(device), text

    def index(self):
        """{friendly name: climate entity} of the Zigbee2MQTT climate entities on the E32's base topic."""
        if self._index is None:
            found = {}
            for entry in list(self.entities.entities.values()):
                if entry.domain != "climate" or entry.platform != "mqtt":
                    continue
                _device, friendly = self._z2m(entry.entity_id)
                if friendly:
                    found.setdefault(friendly, entry.entity_id)
            self._index = found
        return self._index

    def stored(self, valves):
        """The stored valves of a room as routes, each with its entity (None: Home Assistant does not know it)."""
        routes = []
        for valve in valves:
            name, model = valve["name"], valve["model"]
            if model == HA_MODEL:
                entity = name if valid_entity(name) else None
                routes.append(ValveRoute(name, model, entity, *self._friendly_detected(entity)))
            else:
                entity = self.index().get(name)
                routes.append(ValveRoute(name, model, entity, name, *self._friendly_detected(entity)[1:]))
        return routes

    def _friendly_detected(self, entity_id):
        if entity_id is None:
            return None, None
        device, friendly = self._z2m(entity_id)
        return friendly, detect_model(device) if device is not None else None


def language_of(flow):
    language = ((getattr(flow, "context", None) or {}).get("language") or flow.hass.config.language or "en")[:2]
    return language if language in ROUTE_TEXT else "en"


def model_choice_text(hass, entity_id, friendly, device_text):
    """The Advanced step's line for one valve: its name, its Zigbee2MQTT name and what its device says it is."""
    state = hass.states.get(entity_id)
    shown = state.attributes.get("friendly_name") if state is not None else None
    shown = shown if type(shown) is str and shown.strip() else entity_id
    parts = [shown] + ([f"Zigbee2MQTT: {friendly}"] if friendly != shown else []) + ([device_text] if device_text else [])
    return " · ".join(parts)


def route_lines(hass, routes, language="en"):
    """Per valve one plain line: its name and its route ("works without Home Assistant")."""
    text = ROUTE_TEXT.get(language, ROUTE_TEXT["en"])
    lines = []
    for route in routes:
        state = hass.states.get(route.entity_id) if route.entity_id else None
        shown = state.attributes.get("friendly_name") if state is not None else None
        shown = shown if type(shown) is str and shown.strip() else route.name
        if route.entity_id is None:
            lines.append(f"- {shown}: {text['direct'] if route.direct else text['ha']} ({text['kept']})")
        elif route.direct:
            lines.append(f"- {shown}: {text['direct']} ({MODEL_NAMES.get(route.model, route.model)})")
        elif route.friendly and route.detected is None:
            lines.append(f"- {shown}: {text['ha']} ({text['unknown']})")
        else:
            lines.append(f"- {shown}: {text['ha']}")
    return "\n".join(lines) or text["none"]
