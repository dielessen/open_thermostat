"""Test helper: an E32 heating status as the beta.19 firmware publishes it.

Mirrors src/control/HeatingStateTopics.h (splitHeatingStatus) and the
TelemetryPublisher's clearing of rooms that left the plan, so the HA tests can
keep describing the E32 by its /status/heating shape.
"""
import json
import re
from types import SimpleNamespace

ROOM_ID = re.compile(r"[a-z0-9_]{1,32}")
ENTITY_PART_BYTES = 800


def split_status(status):
    """[(topic suffix, document)] of one status: heating, rooms, sensors, entities, plan, shadow."""
    if type(status) is not dict:
        return [("fw/state/heating", status)]
    heating = {k: v for k, v in status.items() if k not in ("rooms", "ble_sensors", "ha_entities", "shadow", "learned", "dhw")}
    messages, room_ids, ble_ids = [], [], []
    # What older firmware carried inside the status: summary and learned/<id> (firmware never does).
    learned, dhw = status.get("learned"), status.get("dhw")
    if type(learned) is dict or type(dhw) is dict:
        summary = {"schema": 1}
        if type(learned) is dict:
            summary["learned"] = {k: v for k, v in learned.items() if k not in ("rooms", "plans")}
            plans = {p.get("id"): p for p in (learned.get("plans") or {}).get("rooms", []) if type(p) is dict}
            for room in (learned.get("rooms") or []) if learned.get("schema") == 1 else []:
                if type(room) is dict and type(room.get("id")) is str and ROOM_ID.fullmatch(room["id"]):
                    messages.append(("fw/telemetry/learned/" + room["id"],
                                     {"schema": 1, "id": room["id"], "learned": room, "plan": plans.get(room["id"])}))
        if type(dhw) is dict:
            summary["dhw"] = dhw
        messages.append(("fw/telemetry/summary", summary))
    for key, prefix, ids in (("rooms", "fw/state/room/", room_ids), ("ble_sensors", "fw/state/ble/", ble_ids)):
        for item in status.get(key) or []:
            if type(item) is dict and type(item.get("id")) is str and ROOM_ID.fullmatch(item["id"]):
                ids.append(item["id"])
                messages.append((prefix + item["id"], {"schema": 1, **item}))
    entities = status.get("ha_entities") if type(status.get("ha_entities")) is list else []
    parts, size = [], 0
    for e in entities:
        n = (len(e) if type(e) is str else 0) + 3
        if not parts or size + n > ENTITY_PART_BYTES:
            parts.append([])
            size = 0
        parts[-1].append(e)
        size += n
    parts = parts or [[]]
    for k, part in enumerate(parts):
        messages.append(("fw/config/entities" + (f"/{k}" if k else ""),
                         {"entities": part, "schema": 1, "revision": status.get("revision", 0), "part": k, "parts": len(parts)}))
    messages.append(("fw/config/plan", {"rooms": room_ids, "ble": ble_ids, "schema": 1, "revision": status.get("revision", 0),
                                        "mode": status.get("mode"), "entity_parts": len(parts)}))
    if type(status.get("shadow")) is dict:
        messages.append(("fw/telemetry/shadow", {**status["shadow"], "schema": 1}))
    messages.append(("fw/state/heating", heating))
    return messages


class FakeE32:
    """Sends statuses to the subscribed callbacks like the E32 (prefix "fixture/v1/")."""

    def __init__(self, callbacks, prefix="fixture/v1/"):
        self.callbacks, self.prefix, self.sent = callbacks, prefix, set()

    def message(self, suffix, payload, retain=False):
        topic = self.prefix + suffix
        for pattern, callback in self.callbacks.items():
            if pattern == topic or (pattern.endswith("/+") and topic.startswith(pattern[:-1]) and "/" not in topic[len(pattern) - 1:]):
                callback(SimpleNamespace(topic=topic, payload=payload, retain=retain))
                return True
        return False

    def heartbeat(self, uptime=100):
        self.message("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": uptime}))

    def status(self, status, retain=False, heartbeat=True):
        if heartbeat:
            self.heartbeat()
        messages = split_status(status)
        now = {suffix for suffix, _ in messages}
        for suffix in sorted(self.sent - now):  # rooms, sensors and parts that left the plan
            if suffix.startswith(("fw/state/room/", "fw/state/ble/", "fw/config/entities/", "fw/telemetry/shadow")):
                self.message(suffix, "", retain)
        self.sent = now
        for suffix, document in messages:
            self.message(suffix, json.dumps(document), retain)

    def learned(self, room_id, value, retain=False):
        self.message("fw/telemetry/learned/" + room_id, value if type(value) is str else json.dumps(value), retain)

    def summary(self, value, retain=False):
        self.message("fw/telemetry/summary", value if type(value) is str else json.dumps(value), retain)
