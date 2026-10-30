"""End-to-end upgrade path of the owner's installation (HA 0.4.0b12 hotfix, problems of 30 Oct 2026).

What happened on 30 Oct 2026: the owner's entry (HA 0.4.0b11) still had the older
"Badkamer" Home Assistant room next to the E32 rooms Woonkamer and Badkamer. The
E32 still ran beta.18, which publishes none of the retained room-plan topics
(fw/state/heating, fw/config/plan). Repairs "Remove the old Home Assistant room"
removed the room, switched the link off, waited in vain for the E32's heating
report and left shadow_enabled False: no heating-link entities, no forwarding of
the Home Assistant inputs, a dead integration. After the E32 update to beta.19
(hello with storage_fault: the stale firmware store) the boiler values stayed
hidden because they waited for a session; Connect E32 answered a full E32 (429
session_capacity) with a meaningless error; after a reload the week-program card
could be missing.

These tests run the real integration code against one simulated E32: the HTTP
API through the real ControllerClient (only aiohttp's session is replaced) and
the MQTT broker with retained topics (only Home Assistant's mqtt helpers are
replaced). Platforms are real EntityPlatforms, so entities end up in the state
machine. The real E32, HA instance and network are never contacted.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from datetime import timedelta
import importlib
import json
import logging
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import pytest
from paho.mqtt.client import topic_matches_sub
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigSubentry
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.helpers.entity_platform import EntityPlatform, current_platform

import custom_components.open_thermostat as integration
from custom_components.open_thermostat import controller_connection, controller_link as link
from custom_components.open_thermostat import controller_setup_flow as setup
from custom_components.open_thermostat import e32_link, legacy_room_migration
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.controller_link import ControllerProvisioningError
from custom_components.open_thermostat.native_provisioning import (
    SOURCE_OPTION, local_device_descriptor, propose_local_shadow_source, source_selection)
from custom_components.open_thermostat.product import INSTALLATION, configuration_snapshot
from custom_components.open_thermostat.v1_wire import GRANT_SECONDS, LEASE_SECONDS
from e32_telemetry import split_status
from test_v1_native import room

_LOGGER = logging.getLogger(__name__)

PREFIX = "ib-therm"
BASE = PREFIX + "/v1/"
CONTROLLER = "e32_54b602e9bfb4"
ADDRESS = "http://192.168.1.206"
PASSWORD = "owner-e32-password"
ADAPTER = "5f0c7d1e9a2b4c6d8e0f1a2b3c4d5e6f"
CSRF = "c" * 64
TAG = '"' + "d" * 64 + '"'
TADO = "climate.woonkamer"  # the tado (RC10) thermostat in the living room
GAS, PRICE, OUTDOOR = "sensor.gas_meter", "sensor.gas_price", "sensor.outdoor_temperature"
# The owner's Classic boiler: flow and return reported; no digital pressure or storage sensors;
# no outdoor sensor on the boiler (the boiler profile E32 beta.19 learns and publishes).
BOILER_SUPPORTED = ("measured_flow_temperature", "measured_return_temperature")
BOILER_NOT_FITTED = ("pressure", "storage_temperature_1", "storage_temperature_2")
BOILER_NOT_REPORTED = ("outdoor_temperature",)


# --- The E32 ---------------------------------------------------------------------

def owner_plan(legacy_climate):
    """The owner's E32 room plan: Woonkamer on the tado thermostat, Badkamer on the older HA room."""
    room_doc = {"id": "woonkamer", "name": "Woonkamer", "state": "active", "inactive_until": 0, "emitter": "floor",
                "sources": [{"type": "ha", "id": TADO}], "setpoint_entity": TADO, "fallback_centi_c": 2000,
                "minimum_centi_c": 1000, "maximum_centi_c": 2400}
    return {"schema": 1, "revision": 4, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60,
            "rooms": [room_doc, {**room_doc, "id": "badkamer", "name": "Badkamer", "emitter": "radiator",
                                 "sources": [{"type": "ha", "id": legacy_climate}],
                                 "setpoint_entity": None}]}


def heating_status(plan, revision=None):
    """The beta.19 heating status of a plan, as the E32 publishes it (split into retained parts)."""
    rooms = [{"id": r["id"], "name": r["name"], "state": "active", "inactive_until": 0, "status": "ok",
              "source": r["sources"][0]["id"], "temperature": 20.4, "setpoint": 21.0, "demand": True}
             for r in plan["rooms"]]
    entities = sorted({s["id"] for r in plan["rooms"] for s in r["sources"] if s["type"] == "ha"}
                      | {r["setpoint_entity"] for r in plan["rooms"] if r.get("setpoint_entity")})
    return {"schema": 1, "revision": plan["revision"] if revision is None else revision, "mode": "shadow",
            "request": {"heat": True, "flow_c": 38, "reason": "heating"}, "ha_entities": entities, "rooms": rooms}


def boiler_group(group, values):
    return json.dumps({"schema": 1, "group": group, "values": values})


class Response:
    def __init__(self, status=200, value=None, headers=None):
        self.status = status
        self.headers = dict(headers or {})
        body = b"" if value is None else json.dumps(value).encode()
        self._body = body
        self.content = SimpleNamespace(iter_chunked=self._chunks, read=self._read)

    async def _chunks(self, size):
        for start in range(0, len(self._body), size):
            yield self._body[start:start + size]

    async def _read(self, size=-1):
        return self._body if size < 0 else self._body[:size]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


class Held(Response):
    """A request the E32 never answers (until the caller gives up or is cancelled)."""

    def __init__(self, reached):
        super().__init__(200, {})
        self.reached = reached

    async def __aenter__(self):
        self.reached.set()
        await asyncio.Event().wait()


class Session:
    """One ControllerClient's aiohttp session to the simulated E32 (cookie = signed in)."""

    def __init__(self, e32):
        self.e32, self.closed, self.signed_in = e32, False, False
        self.cookie_jar = SimpleNamespace(clear=lambda: None)

    def request(self, method, url, *, data=None, headers=None, allow_redirects=True):
        assert url.startswith(ADDRESS), url  # only the owner's E32, never anything else
        return self.e32.answer(self, method, url[len(ADDRESS):], data, headers or {})

    async def close(self):
        self.closed = True


class E32:
    """The owner's E32 V2 (e32_54b602e9bfb4) over HTTP and MQTT.

    firmware "beta.18": no retained room-plan topics (fw/state/heating, fw/config/plan,
    fw/state/boiler_fields), only the older telemetry (availability, heartbeat).
    firmware "beta.19": the retained room-plan, heating and boiler topics.
    """

    MAX_SESSIONS = 4

    def __init__(self, broker, plan, firmware="beta.18"):
        self.broker, self.plan, self.firmware = broker, deepcopy(plan), firmware
        self.calls, self.saved_settings, self.plan_posts = [], [], []
        self.reboots = 0
        self.silent = False         # its MQTT does not reach this Home Assistant (yet)
        self.blocked = {}           # (method, path) -> [n-th request to hold, Event]
        self.sessions = 0           # web sessions in use (the E32 has 4)
        self.foreign_sessions = 0   # held by browsers / other tools
        self.settings = {"mqtt": {"enabled": True, "brokerAddress": "192.168.1.10", "brokerPort": 1883,
                                  "username": "e32", "password": "", "base": PREFIX, "clientId": "ib-therm-e32",
                                  "modern_shadow": True, "adapter_id": ADAPTER},
                         "interface_mode": "wifi"}

    # -- HTTP ----------------------------------------------------------------------
    @property
    def version(self):
        return f"v0.1.0-e32v2-{self.firmware}"

    def http_writes(self):
        """Every request that changes the E32 (sign-in and sign-out are not changes)."""
        return [c for c in self.calls if c[0] == "POST" and c[1] not in ("/auth/login", "/auth/logout")]

    def block(self, method, path, nth=1):
        """Hold the n-th such request open (the E32 busy, HA stopping meanwhile); returns its 'reached' event."""
        reached = asyncio.Event()
        self.blocked[(method, path)] = [nth, reached]
        return reached

    def answer(self, session, method, path, data, headers):
        self.calls.append((method, path))
        if (rule := self.blocked.get((method, path))) is not None:
            rule[0] -= 1
            if rule[0] == 0:
                return Held(rule[1])
        if path == "/auth/login" and method == "POST":
            if self.sessions + self.foreign_sessions >= self.MAX_SESSIONS:
                return Response(429, {"error": "session_capacity"}, {"Retry-After": "30"})
            form = data if isinstance(data, dict) else {k: v[0] for k, v in parse_qs(data or "").items()}
            if form.get("password") != PASSWORD:
                return Response(401, {"error": "invalid_credentials"})
            session.signed_in = True
            self.sessions += 1
            return Response(200, {"authenticated": True})
        if not session.signed_in:
            return Response(401, {"error": "authentication_required"})
        if method == "POST" and headers.get("X-OpenThermostat-CSRF") != CSRF:
            return Response(403, {"error": "csrf_required"})
        if path == "/auth/session":
            return Response(200, {"authenticated": True, "csrf": CSRF, "expires_in": 60, "default_password": False})
        if path == "/auth/logout":
            session.signed_in = False
            self.sessions -= 1
            return Response(200, {"authenticated": False})
        if method == "GET" and path == "/status/version":
            return Response(200, {"version": self.version, "source": "a" * 40, "sha256": "b" * 64,
                                  "web_sha256": "e" * 64})
        if method == "GET" and path == "/status":
            return Response(200, {"controlMode": "shadow"})
        if method == "GET" and path == "/updates/status":
            return Response(200, {"busy": False, "boot_pending": False, "reboot_required": False,
                                  "reboot_scheduled": False})
        if path == "/config/device":
            if method == "GET":
                value = deepcopy(self.settings)
                value["mqtt"].update(native_source_device_id=CONTROLLER, native_source_live_apply=False)
                return Response(200, value, {"ETag": TAG})
            if headers.get("If-Match") != TAG:
                return Response(412, {"error": "device_settings_changed"})
            self.settings = json.loads(data)
            self.saved_settings.append(deepcopy(self.settings))
            return Response(200, {"saved": True})
        if method == "POST" and path == "/updates/reboot":
            self.reboots += 1
            return Response(202, {"rebooting": True})
        if method == "GET" and path == "/config/rooms":
            return Response(200, [])
        if path == link.HEATING_PLAN:
            if method == "GET":
                return Response(200, self.plan)
            document = json.loads(data)
            self.plan_posts.append(deepcopy(document))
            if document.get("revision") != self.plan["revision"]:
                return Response(409, {"error": "plan_changed"})
            self.plan = {**document, "revision": document["revision"] + 1}
            if self.firmware != "beta.18":
                self.publish_room_plan()
            return Response(200, self.plan)
        if path == link.HEATING_FLOW and self.firmware == "beta.18":
            return Response(404, {"error": "not_found"})
        return Response(404, {"error": "not_found"})

    # -- MQTT ----------------------------------------------------------------------
    def mqtt(self, suffix, payload, retain=False):
        if not self.silent:
            self.broker.e32(suffix, payload, retain)

    def online(self):
        """What every firmware publishes: its availability (retained) and a live heartbeat."""
        self.mqtt("fw/availability", "online", retain=True)
        self.heartbeat()

    def heartbeat(self, uptime=120):
        self.mqtt("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": uptime}))

    def publish_room_plan(self):
        """beta.19: the retained heating, room, entity and plan topics of the current plan."""
        for suffix, document in split_status(heating_status(self.plan)):
            self.mqtt(suffix, json.dumps(document), retain=True)

    def hello(self, *, storage_fault):
        self.mqtt("fw/hello", json.dumps({
            "api": 1, "mode": "shadow", "controller_id": CONTROLLER, "boot_id": "boot19", "challenge_id": "c1",
            "epoch": 1, "config_revision": 0, "config_digest": "", "lease_ms": LEASE_SECONDS * 1000,
            "grant_ms": GRANT_SECONDS * 1000, "storage_fault": storage_fault}))

    def boiler(self):
        """beta.19: the retained boiler values and the learned boiler profile (the owner's Classic boiler)."""
        from custom_components.open_thermostat.boiler_fields import INDEX_BY_NAME
        from test_boiler_fields import values
        at = INDEX_BY_NAME.__getitem__
        supported, not_fitted, not_reported = BOILER_SUPPORTED, BOILER_NOT_FITTED, BOILER_NOT_REPORTED
        missing = {at(n) for n in not_fitted + not_reported}
        for group in range(7):
            document = values(group)
            for row in document["fields"]:
                if row[0] in missing:
                    row[1] = None  # the boiler has no such sensor / never sends the telegram
            self.mqtt(f"fw/state/boiler_fields/{group}", boiler_group(group, document), retain=True)
        self.mqtt("fw/config/boiler_profile", json.dumps({
            "schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
            "supported": sorted(at(n) for n in supported), "not_fitted": sorted(at(n) for n in not_fitted),
            "not_reported": sorted(at(n) for n in not_reported), "settled": True}), retain=True)

    def update_to_beta19(self, *, storage_fault=True):
        """The firmware update: a restart, then the beta.19 retained topics and its hello."""
        self.firmware = "beta.19"
        self.online()
        self.publish_room_plan()
        self.boiler()
        self.hello(storage_fault=storage_fault)
        self.heartbeat(5)


class Broker:
    """Home Assistant's MQTT seen from the integration: subscriptions, retained topics, publishes."""

    def __init__(self, hass):
        self.hass, self.subscriptions, self.retained, self.published = hass, [], {}, []

    async def subscribe(self, hass, topic, callback, qos=0, encoding="utf-8", **_):
        item = (topic, callback)
        self.subscriptions.append(item)
        for retained_topic, payload in list(self.retained.items()):
            if topic_matches_sub(topic, retained_topic):  # a real broker sends the retained state at once
                hass.loop.call_soon(callback, SimpleNamespace(topic=retained_topic, payload=payload, retain=True,
                                                              qos=0))

        def unsubscribe():
            if item in self.subscriptions:
                self.subscriptions.remove(item)
        return unsubscribe

    async def publish(self, hass, topic, payload, qos=0, retain=False, *args, **kwargs):
        self.published.append((topic, payload, retain))

    def e32(self, suffix, payload, retain=False):
        topic = BASE + suffix
        if retain:
            if payload == "":
                self.retained.pop(topic, None)
            else:
                self.retained[topic] = payload
        for pattern, callback in list(self.subscriptions):
            if topic_matches_sub(pattern, topic):
                callback(SimpleNamespace(topic=topic, payload=payload, retain=retain, qos=0))

    def subscribed(self, suffix):
        return any(topic_matches_sub(pattern, BASE + suffix) for pattern, _ in self.subscriptions)

    def inputs(self):
        """What Home Assistant forwarded to the E32 on ha/heating_input."""
        return [json.loads(p) for t, p, _ in self.published if t == BASE + "ha/heating_input"]


# --- Home Assistant around the integration -------------------------------------

SKIPPED_PLATFORMS = {"update"}  # the firmware update entity asks GitHub; never in an offline test


class Platforms:
    """async_forward_entry_setups/async_unload_platforms with real EntityPlatforms (entities in hass.states)."""

    def __init__(self, hass):
        self.hass, self.loaded, self.calls = hass, {}, []

    async def forward(self, entry, platforms):
        hass = self.hass
        for item in platforms:
            domain = str(getattr(item, "value", item))
            self.calls.append(("setup", domain))
            if domain in SKIPPED_PLATFORMS:
                continue
            module = importlib.import_module(f"custom_components.open_thermostat.{domain}")
            platform = EntityPlatform(hass=hass, logger=_LOGGER, domain=domain, platform_name=DOMAIN,
                                      platform=None, scan_interval=timedelta(seconds=30), entity_namespace=None)
            platform.config_entry = entry
            self.loaded[domain] = platform
            tasks = []

            def add(entities, update_before_add=False, *, config_subentry_id=None, platform=platform, tasks=tasks):
                tasks.append(hass.async_create_task(platform.async_add_entities(
                    list(entities), config_subentry_id=config_subentry_id)))
            token = current_platform.set(platform)
            try:
                await module.async_setup_entry(hass, entry, add)
            finally:
                current_platform.reset(token)
            if tasks:
                await asyncio.gather(*tasks)

    async def unload(self, entry, platforms):
        for domain in [str(getattr(p, "value", p)) for p in platforms]:
            self.calls.append(("unload", domain))
            if (platform := self.loaded.pop(domain, None)) is not None:
                await platform.async_reset()
        return True

    def unique_ids(self):
        return {entity.unique_id: entity for platform in self.loaded.values()
                for entity in platform.entities.values()}


class Dashboard:
    """The Lovelace panel itself is not under test here (create_dashboard stays on)."""

    def __init__(self, hass, prefix, entry_id):
        self.rooms = set()

    async def async_start(self):
        return None

    async def async_stop(self):
        return None

    def set_rooms(self, rooms):
        self.rooms = set(rooms)


async def yield_loop(rounds=5):
    for _ in range(rounds):
        await asyncio.sleep(0)


async def settle(hass, rounds=3):
    for _ in range(rounds):
        await asyncio.sleep(0)
        await hass.async_block_till_done()


class Installation:
    """The owner's Home Assistant: one OpenThermostat entry, set up, reloaded and restarted for real."""

    def __init__(self, hass, monkeypatch):
        self.hass = hass
        self.broker = Broker(hass)
        self.platforms = Platforms(hass)
        self.setups, self.errors, self.log = 0, [], []
        self._reload_lock = asyncio.Lock()  # HA reloads one entry at a time (its setup lock)
        monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock(return_value=True))
        monkeypatch.setattr(mqtt, "async_subscribe", self.broker.subscribe)
        monkeypatch.setattr(mqtt, "async_publish", self.broker.publish)
        monkeypatch.setattr(mqtt, "async_subscribe_connection_status", lambda hass, callback: lambda: None)
        monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", self.platforms.forward)
        monkeypatch.setattr(hass.config_entries, "async_unload_platforms", self.platforms.unload)
        monkeypatch.setattr(hass.config_entries, "async_reload", self.reload)
        monkeypatch.setattr(integration, "RoomDashboard", Dashboard)
        # The HTTP side: the real ControllerClient, a simulated E32 behind aiohttp's session.
        monkeypatch.setattr(link.aiohttp, "ClientSession", lambda **kwargs: Session(self.e32))
        monkeypatch.setattr(link.aiohttp, "TCPConnector", lambda **kwargs: None)
        # Real waits, shortened (seconds in production).
        monkeypatch.setattr(controller_connection, "CONNECTION_TIMEOUT", 2.0)
        monkeypatch.setattr(controller_connection, "TELEMETRY_POLL", 0.01)
        monkeypatch.setattr(link, "LINK_POLL_INTERVAL", 0.01)
        monkeypatch.setattr(link, "LINK_BOOT_TIMEOUT", 2.0)
        monkeypatch.setattr(legacy_room_migration, "HANDOVER_WAIT", 0.2)
        self.entry = None
        self.e32 = None

    # -- the entry exactly like the owner's -------------------------------------
    async def create_owner_entry(self, *, native_profile=True):
        """The owner's entry before Repairs.

        native_profile: the native room profile Connect E32 (HA 0.4.0b10) saved for the
        older room (options native_shadow_source; on the E32 its descriptor). The handoff
        of 30 Oct records that the failed link cleared it on the E32, so the owner had it.
        """
        hass = self.hass
        from homeassistant import config_entries
        from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
        from test_product_flow import new_room
        hass.states.async_set(TADO, "heat", {"current_temperature": 20.4, "temperature": 21.0})
        hass.states.async_set(GAS, "12345.678", {"unit_of_measurement": "m³", "device_class": "gas",
                                                 "state_class": "total_increasing"})
        hass.states.async_set(PRICE, "1.45", {"unit_of_measurement": "EUR/m³"})
        hass.states.async_set(OUTDOOR, "9.5", {"unit_of_measurement": "°C", "device_class": "temperature"})
        entry = ConfigEntry(domain=DOMAIN, title="OpenThermostat", version=3, minor_version=1,
                            data={"topic_prefix": PREFIX, "integration_mode": "v1_shadow", "adapter_id": ADAPTER,
                                  "product_configuration": 1},
                            options={"integration_mode": "v1_shadow", "shadow_enabled": False}, source="user",
                            unique_id=PREFIX, discovery_keys=MappingProxyType({}), subentries_data=[])
        hass.config_entries._entries[entry.entry_id] = entry
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
        # The older "Badkamer" room, made with the real "Add room" flow of HA 0.4.0b10.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(config_entries, "_async_get_flow_handler", AsyncMock(return_value=OpenThermostatConfigFlow))
            binding = replace(room(hass, suffix="badkamer"), name="Badkamer")
            manager = hass.config_entries.subentries
            flow = await new_room(manager, entry, binding)
            flow = await manager.async_configure(flow["flow_id"], {"base_temperature": 21, "program_action": "save"})
            await manager.async_configure(flow["flow_id"], {})
        hass.data[DOMAIN].pop(entry.entry_id, None)
        zone = next(s for s in entry.subentries.values() if s.subentry_type == "zone")
        devices, entities = dr.async_get(hass), er.async_get(hass)
        legacy = devices.async_get_or_create(config_entry_id=entry.entry_id, config_subentry_id=zone.subentry_id,
                                             identifiers={(DOMAIN, f"{PREFIX}_room_{zone.data['room_id']}")},
                                             name="Badkamer — thermostaat")
        climate = entities.async_get_or_create("climate", DOMAIN, f"{PREFIX}_room_{zone.data['room_id']}_climate",
                                               config_entry=entry, config_subentry_id=zone.subentry_id,
                                               device_id=legacy.id, suggested_object_id="badkamer_thermostaat")
        # Connect E32 (beta.18 HA) and the owner's settings.
        hass.config_entries.async_update_entry(entry, data={
            **entry.data, setup.CONTROLLER_ADDRESS: ADDRESS, setup.CONTROLLER_ID: CONTROLLER,
            setup.CONTROLLER_PASSWORD: PASSWORD}, options={
            "create_dashboard": True, "energy_gas_meter": GAS, "energy_gas_price_entity": PRICE,
            "energy_outdoor_entity": OUTDOOR, "integration_mode": "v1_shadow", "shadow_enabled": True})
        if native_profile:
            source = propose_local_shadow_source(hass, entry, CONTROLLER, week_reviewed=True)
            hass.config_entries.async_update_entry(entry, options={**entry.options,
                                                                   SOURCE_OPTION: source_selection(source)})
            self.native_descriptor = local_device_descriptor(source)
        else:
            self.native_descriptor = None
        for room_id, title in (("woonkamer", "Woonkamer"), ("badkamer", "Badkamer")):
            hass.config_entries.async_add_subentry(entry, ConfigSubentry(
                data=MappingProxyType({}), subentry_type="e32_room", title=title, unique_id=f"e32_room_{room_id}"))
        self.entry, self.binding, self.legacy_climate = entry, binding, climate.entity_id
        return entry

    def owner_e32(self, firmware="beta.18"):
        self.e32 = E32(self.broker, owner_plan(self.legacy_climate), firmware)
        if self.native_descriptor is not None:
            self.e32.settings["mqtt"]["native_shadow_source"] = deepcopy(self.native_descriptor)
        return self.e32

    # -- setup, unload, reload (the parts of ConfigEntries the integration uses) --
    def _state(self, state):
        with suppress(Exception):
            self.entry._async_set_state(self.hass, state, None)

    async def start(self):
        """What Home Assistant does at a start: the entry's async_setup_entry (under the entry's setup lock)."""
        async with self._reload_lock:
            return await self._start()

    async def stop(self):
        async with self._reload_lock:
            await self._stop()

    async def _start(self):
        self.setups += 1
        self.log.append(("start", dict(self.entry.options).get("shadow_enabled")))
        self._state(ConfigEntryState.SETUP_IN_PROGRESS)
        try:
            ok = await integration.async_setup_entry(self.hass, self.entry)
        except Exception as err:  # what HA logs as "Error setting up entry"
            self.errors.append(f"{type(err).__name__}: {err}")
            self._state(ConfigEntryState.SETUP_ERROR)
            await self.entry._async_process_on_unload(self.hass)
            return False
        self._state(ConfigEntryState.LOADED if ok else ConfigEntryState.SETUP_ERROR)
        await yield_loop()  # never async_block_till_done here: a running link task waits for this reload
        return ok

    async def _stop(self):
        self.log.append(("stop",))
        if self.entry.state is ConfigEntryState.LOADED or self.entry.entry_id in self.hass.data.get(DOMAIN, {}):
            await integration.async_unload_entry(self.hass, self.entry)
        await self.entry._async_process_on_unload(self.hass)
        self._state(ConfigEntryState.NOT_LOADED)
        await yield_loop()  # never async_block_till_done here: a running link task waits for this reload

    async def reload(self, entry_id):
        assert entry_id == self.entry.entry_id
        self.log.append(("reload",))
        async with self._reload_lock:
            try:
                await self._stop()
            except Exception as err:
                self.errors.append(f"unload {type(err).__name__}: {err}")
                raise
            return await self._start()

    async def restart(self):
        """An HA restart: everything in memory is gone, the saved entry and the broker's retained topics stay."""
        await self.stop()
        self.platforms.loaded.clear()
        return await self.start()

    # -- what the owner sees ---------------------------------------------------
    def state(self):
        return self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {})

    def entity(self, unique_id):
        return self.platforms.unique_ids().get(unique_id)

    def available(self, unique_id):
        entity = self.entity(unique_id)
        if entity is None:
            return False
        state = self.hass.states.get(entity.entity_id)
        return state is not None and state.state not in ("unavailable", "unknown")

    def heating_link_alive(self):
        """The heating-link entities exist and the E32 telemetry is subscribed (the integration is not dead)."""
        return (self.entity(f"{PREFIX}_hub_heat_request") is not None and self.broker.subscribed("fw/state/heating")
                and self.broker.subscribed("fw/config/plan"))


@pytest.fixture
def owner(hass, monkeypatch):
    return Installation(hass, monkeypatch)


async def started_owner(owner, firmware="beta.18", *, native_profile=True):
    entry = await owner.create_owner_entry(native_profile=native_profile)
    e32 = owner.owner_e32(firmware)
    e32.online()
    if firmware != "beta.18":
        e32.publish_room_plan()
    assert await owner.start(), owner.errors
    await settle(owner.hass)
    return entry, e32


def snapshot(entry):
    return (dict(entry.data), dict(entry.options), {k: s.as_dict() for k, s in entry.subentries.items()})


async def teardown(owner):
    with suppress(Exception):
        await owner.stop()


# --- 1. The owner's real path on a beta.18 E32 ----------------------------------------

@pytest.mark.asyncio
async def test_the_owner_entry_is_exactly_the_owners_and_starts_alive_on_beta18(owner):
    entry, e32 = await started_owner(owner)
    try:
        assert entry.data[INSTALLATION]["status"] == "draft_not_applied"
        assert {k: entry.data[k] for k in ("adapter_id", "controller_address", "controller_id", "integration_mode",
                                           "product_configuration", "topic_prefix")} == {
            "adapter_id": ADAPTER, "controller_address": ADDRESS, "controller_id": CONTROLLER,
            "integration_mode": "v1_shadow", "product_configuration": 1, "topic_prefix": PREFIX}
        options = {k: v for k, v in entry.options.items() if k != SOURCE_OPTION}
        assert options == {"create_dashboard": True, "energy_gas_meter": GAS,
                           "energy_gas_price_entity": PRICE, "energy_outdoor_entity": OUTDOOR,
                           "integration_mode": "v1_shadow", "shadow_enabled": True}
        assert SOURCE_OPTION in entry.options  # the native room profile of the older room
        kinds = sorted((s.subentry_type, s.title) for s in entry.subentries.values() if s.subentry_type != "installation")
        assert kinds == [("e32_room", "Badkamer"), ("e32_room", "Woonkamer"), ("zone", "Badkamer")]
        assert e32_link.legacy_rooms_pending(entry)
        issue = ir.async_get(owner.hass).async_get_issue(DOMAIN, e32_link.issue_id(entry))
        assert issue is not None and issue.translation_key == "legacy_rooms" and issue.is_fixable
        # Alive: the shadow link runs and the heating-link entities exist, even though beta.18 sends no heating report.
        assert owner.state()["v1_runtime"].enabled and "v1_connection" in owner.state()
        assert owner.heating_link_alive()
    finally:
        await teardown(owner)


async def repairs_flow(owner):
    """The owner opens Repairs → "Remove the old Home Assistant room"."""
    from custom_components.open_thermostat import repairs
    issue = ir.async_get(owner.hass).async_get_issue(DOMAIN, e32_link.issue_id(owner.entry))
    assert issue is not None and issue.is_fixable
    flow = await repairs.async_create_fix_flow(owner.hass, issue.issue_id, issue.data)
    flow.hass, flow.handler, flow.flow_id = owner.hass, DOMAIN, "fix"
    return flow


async def confirm_removal(flow, form, timeout=15):
    """The owner presses Submit on the form shown, waits for the progress and sees the result."""
    await getattr(flow, "async_step_" + form["step_id"])({})
    task = getattr(flow, "_legacy_task", None)
    if task is not None:
        await asyncio.wait([task], timeout=timeout)
        assert task.done(), "the removal must end (a refusal or a result), never hang"
    done = await flow.async_step_legacy_rooms_removing()
    assert done["type"] == "progress_done", done
    flow.failure = getattr(flow, "_legacy_failure", None)  # the error the next form shows
    with suppress(Exception):
        flow.failure_cause = task.exception()
    return await getattr(flow, "async_step_" + done["step_id"])()


def assert_not_dead(owner):
    """The 30 Oct failure must never come back: link on, runtime and heating link running."""
    entry = owner.entry
    context = (entry.state, owner.setups, owner.errors, owner.log, dict(entry.options))
    assert entry.options["shadow_enabled"] is True, ("shadow_enabled stuck False (30 Oct)", context)
    assert owner.state().get("v1_runtime") is not None, ("the entry is not set up", context)
    assert owner.heating_link_alive(), "no heating-link entities or E32 subscriptions: a dead integration"


async def e32_reaches_home_assistant(owner):
    """The E32 (beta.19) publishes its retained topics; HA must forward its inputs and show the rooms."""
    owner.e32.silent = False
    owner.e32.update_to_beta19()
    await settle(owner.hass, 5)
    owner.hass.states.async_set(TADO, "heat", {"current_temperature": 20.6, "temperature": 21.5})
    await settle(owner.hass)
    inputs = owner.broker.inputs()
    assert {"entity": TADO, "temperature": 20.6, "target": 21.5} in inputs, inputs
    assert owner.available(f"{PREFIX}_hub_heat_request")
    for room_id in ("woonkamer", "badkamer"):
        assert owner.available(f"{PREFIX}_e32_room_{room_id}_temperature"), room_id


# --- 1. The owner's real path: Repairs on a beta.18 E32 ---------------------------------

@pytest.mark.asyncio
async def test_repairs_on_a_beta18_e32_says_update_first_and_changes_nothing(owner):
    entry, e32 = await started_owner(owner)
    try:
        before = snapshot(entry)
        flow = await repairs_flow(owner)
        form = await flow.async_step_init()
        # Said before the owner confirms: the E32 needs beta.19 first.
        assert form["type"] == "form" and form["errors"] == {"base": "e32_update_required"}, form
        result = await confirm_removal(flow, form)
        if result["type"] == "create_entry":  # success is allowed too, but then completely
            assert not e32_link.legacy_rooms_pending(entry)
        else:
            assert result["type"] == "form" and result["errors"] == {"base": "e32_update_required"}, result
            assert snapshot(entry) == before, "a refusal changes nothing in Home Assistant"
            assert e32.http_writes() == [], "a refusal changes nothing on the E32 (no plan, settings or restart)"
            assert e32_link.legacy_rooms_pending(entry)  # Repairs offers it again after the update
        assert e32.sessions == 0, "every E32 sign-in ends with a sign-out"
        assert_not_dead(owner)
        # Then the E32 updates to beta.19: its topics arrive and the inputs are forwarded.
        await e32_reaches_home_assistant(owner)
    finally:
        await teardown(owner)


@pytest.mark.asyncio
async def test_a_link_the_e32_never_confirms_does_not_leave_a_dead_integration(owner):
    """Fix B: the old-room removal ran but no heating report came (the 30 Oct chain past the precheck)."""
    entry, e32 = await started_owner(owner)
    e32.firmware = "beta.19"  # its web server already says beta.19 ...
    e32.silent = True         # ... but its heating report does not reach Home Assistant (yet)
    try:
        flow = await repairs_flow(owner)
        form = await flow.async_step_init()
        assert form["errors"] == {}, form
        result = await confirm_removal(flow, form)
        assert result["type"] in ("form", "abort", "create_entry"), result
        assert e32.sessions == 0
        assert_not_dead(owner)
        await e32_reaches_home_assistant(owner)
    finally:
        await teardown(owner)


@pytest.mark.asyncio
async def test_repairs_on_a_beta19_e32_removes_the_old_room_and_everything_keeps_running(owner):
    entry, e32 = await started_owner(owner, "beta.19")
    try:
        kept = {k: v for k, v in entry.options.items() if k not in (SOURCE_OPTION, "shadow_enabled")}
        flow = await repairs_flow(owner)
        form = await flow.async_step_init()
        assert form["step_id"] == "legacy_rooms" and form["errors"] == {}, form
        result = await confirm_removal(flow, form)
        assert result["type"] == "create_entry", (result, flow.failure, getattr(flow, "failure_cause", None))
        assert not e32_link.legacy_zones(entry) and SOURCE_OPTION not in entry.options
        assert {k: v for k, v in entry.options.items() if k != "shadow_enabled"} == kept
        assert ir.async_get(owner.hass).async_get_issue(DOMAIN, e32_link.issue_id(entry)) is None
        # The E32 lost only its old native room profile; Badkamer now reads the room's own sensor.
        assert e32.saved_settings and e32.saved_settings[-1]["mqtt"]["native_shadow_source"] is None
        badkamer = next(r for r in e32.plan["rooms"] if r["id"] == "badkamer")
        assert badkamer["sources"] == [{"type": "ha", "id": owner.binding.temperature.entity_id}]
        assert e32.sessions == 0
        assert_not_dead(owner)
        await e32_reaches_home_assistant(owner)
    finally:
        await teardown(owner)


@pytest.mark.asyncio
async def test_the_owner_entry_as_described_without_its_native_profile_still_starts(owner):
    """The entry exactly as listed for 30 Oct: the older room, shadow on, but no native room profile saved.

    However the entry got there, Home Assistant must start it (heating link, entities,
    forwarding) and offer the removal in Repairs, never fail its setup.
    """
    entry, e32 = await started_owner(owner, native_profile=False)
    try:
        assert SOURCE_OPTION not in entry.options and e32_link.legacy_zones(entry)
        assert_not_dead(owner)
        assert ir.async_get(owner.hass).async_get_issue(DOMAIN, e32_link.issue_id(entry)) is not None
        await e32_reaches_home_assistant(owner)
    finally:
        await teardown(owner)


# --- 2. The E32 updates to beta.19 (hello storage_fault: the stale firmware store) -------

@pytest.mark.asyncio
@pytest.mark.parametrize("link", ["running", "switched_off"])
async def test_after_the_update_rooms_heat_request_and_boiler_values_show_without_a_session(owner, link):
    from custom_components.open_thermostat.boiler_fields import INDEX_BY_NAME
    from custom_components.open_thermostat.v1_boiler_fields import field_unique_id
    entry, e32 = await started_owner(owner)
    hass = owner.hass
    try:
        if link == "switched_off":  # what 30 Oct left behind
            hass.config_entries.async_update_entry(entry, options={**entry.options, "shadow_enabled": False})
            await settle(hass, 5)
            assert owner.setups == 2, "the options change reloads the entry"
        e32.update_to_beta19(storage_fault=True)
        await settle(hass, 5)
        client = getattr(owner.state().get("v1_connection"), "client", None)
        assert client is None or not client.ready, "no session: the E32 reports storage_fault"
        if client is not None:
            assert client.error == "firmware_storage_fault"
        assert owner.available(f"{PREFIX}_hub_heat_request")
        for room_id in ("woonkamer", "badkamer"):
            assert owner.available(f"{PREFIX}_e32_room_{room_id}_temperature"), room_id
        registry = er.async_get(hass)
        for name in BOILER_SUPPORTED:
            unique_id = field_unique_id(PREFIX, INDEX_BY_NAME[name])
            assert owner.available(unique_id), f"boiler value {name} needs no session (fix A)"
        flow_temperature = owner.entity(field_unique_id(PREFIX, INDEX_BY_NAME["measured_flow_temperature"]))
        assert float(hass.states.get(flow_temperature.entity_id).state) == 45.0
        for name in BOILER_NOT_FITTED + BOILER_NOT_REPORTED:
            unique_id = field_unique_id(PREFIX, INDEX_BY_NAME[name])
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            shown = entity_id is not None and registry.async_get(entity_id).disabled_by is None
            assert not shown and (entity_id is None or hass.states.get(entity_id) is None), name
        # The forwarding of the Home Assistant inputs runs in both cases.
        hass.states.async_set(TADO, "heat", {"current_temperature": 20.7, "temperature": 21.0})
        await settle(hass)
        assert {"entity": TADO, "temperature": 20.7, "target": 21.0} in owner.broker.inputs()
    finally:
        await teardown(owner)


# --- 3. Connect E32 while every E32 web session is in use (429 session_capacity) ---------

def after_removal(owner):
    """The owner's entry once the older room is gone (the room-plan route of Connect E32)."""
    entry = owner.entry
    changes, removed = e32_link.without_legacy_rooms(entry)
    owner.hass.config_entries._async_update_entry(entry, **changes)
    owner.hass.config_entries.async_update_entry(
        entry, options={k: v for k, v in entry.options.items() if k != SOURCE_OPTION})
    e32_link.remove_legacy_room_devices(owner.hass, entry, removed)
    owner.e32.settings["mqtt"].pop("native_shadow_source", None)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["with_old_room", "room_plan"])
async def test_connect_e32_on_a_full_e32_names_the_cause_and_changes_nothing(owner, route):
    from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
    entry = await owner.create_owner_entry()
    e32 = owner.owner_e32("beta.19")
    if route == "room_plan":
        after_removal(owner)
    e32.online()
    e32.publish_room_plan()
    assert await owner.start(), owner.errors
    hass = owner.hass
    try:
        e32.foreign_sessions = E32.MAX_SESSIONS  # four browser sessions open on the E32
        before = snapshot(entry)
        flow = OpenThermostatConfigFlow.async_get_options_flow(entry)
        flow.hass, flow.handler, flow.flow_id = hass, entry.entry_id, "connect"
        flow.context = {"source": "user"}
        await flow.async_step_controller_connection({"address": ADDRESS, "password": PASSWORD})
        await asyncio.wait([flow._controller_task], timeout=10)
        done = await flow.async_step_controller_connecting()
        assert done["type"] == "progress_done" and done["step_id"] == "controller_connection", done
        form = await flow.async_step_controller_connection()
        error = form["errors"].get("base")
        assert error != "controller_response_invalid", "429 must not read as an invalid E32 answer"
        assert error == "controller_session_capacity", form
        strings = json.loads((Path(integration.__file__).parent / "strings.json").read_text(encoding="utf-8"))
        assert error in strings["options"]["error"]
        assert snapshot(entry) == before and entry.options["shadow_enabled"] is True
        assert e32.http_writes() == [] and e32.sessions == 0
        assert_not_dead(owner)
    finally:
        await teardown(owner)


# --- 4. An HA restart in the middle of a link ------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["graceful", "power_loss"])
@pytest.mark.parametrize("moment", ["link_paused", "old_room_removed", "waiting_for_the_e32"])
async def test_an_ha_restart_in_the_middle_of_a_link_keeps_forwarding_and_entities(owner, moment, stop):
    """Whatever options were saved when HA stopped, the restarted entry forwards inputs and shows entities."""
    entry = await owner.create_owner_entry()
    e32 = owner.owner_e32("beta.19")
    e32.silent = True  # restarting after its own update: no heating report yet
    assert await owner.start(), owner.errors
    hass = owner.hass
    try:
        reached = None
        if moment == "link_paused":
            reached = e32.block("GET", "/config/rooms", 1)  # the first E32 check after the link was paused
        elif moment == "old_room_removed":
            reached = e32.block("GET", "/config/rooms", 2)  # the check after the old room was removed
        flow = await repairs_flow(owner)
        form = await flow.async_step_init()
        await getattr(flow, "async_step_" + form["step_id"])({})
        task = flow._legacy_task
        if reached is not None:
            await asyncio.wait_for(reached.wait(), 10)
        else:
            async with asyncio.timeout(10):
                while SOURCE_OPTION in entry.options or entry.options.get("shadow_enabled") is not True:
                    await asyncio.sleep(0.01)
        for _ in range(5):  # (async_block_till_done would wait for the held link task itself)
            await asyncio.sleep(0)
        assert not task.done(), task
        if moment != "link_paused":
            assert not e32_link.legacy_zones(entry)
        saved = (dict(entry.data), dict(entry.options), dict(entry.subentries))
        # HA stops: the running flow is cancelled.
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await owner.stop()
        if stop == "power_loss":  # nothing after that moment reached the disk
            hass.config_entries._async_update_entry(entry, data=saved[0], options=saved[1], subentries=saved[2])
        owner.platforms.loaded.clear()
        e32.blocked.clear()
        assert await owner.start(), owner.errors  # HA starts again with whatever was saved
        assert owner.state().get("v1_runtime") is not None
        assert owner.heating_link_alive(), "after the restart the heating link must run"
        await e32_reaches_home_assistant(owner)
    finally:
        await teardown(owner)


# --- 5. The week-program card after a reload ---------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["running", "link_off", "setup_failed"])
async def test_after_a_reload_the_week_card_module_is_registered_whatever_the_runtime(owner, monkeypatch, runtime):
    from homeassistant.components import frontend
    from homeassistant.components.frontend import UrlManager
    from custom_components.open_thermostat.e32_week import CARD_URL
    hass = owner.hass
    hass.data[frontend.DATA_EXTRA_MODULE_URL] = UrlManager(lambda change, url: None, [])
    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock())
    assert await integration.async_setup(hass, {})  # HA start: the domain is set up once
    entry = await owner.create_owner_entry()
    e32 = owner.owner_e32()
    e32.online()
    if runtime == "link_off":
        hass.config_entries.async_update_entry(entry, options={**entry.options, "shadow_enabled": False})
    if runtime == "setup_failed":
        def broken(entry):
            raise ConfigEntryError("context_profile_invalid")
        monkeypatch.setattr(integration, "_selected_context_source_profiles", broken)
    try:
        assert await owner.start() is (runtime != "setup_failed"), owner.errors
        failures = []
        for _ in range(2):
            try:
                await owner.reload(entry.entry_id)
            except Exception as err:  # HA logs a failed reload; the card must not depend on it
                failures.append(f"{type(err).__name__}: {err}")
        assert CARD_URL in hass.data[frontend.DATA_EXTRA_MODULE_URL].urls
        assert "open_thermostat/e32_week/get" in hass.data["websocket_api"]
        assert failures == [], "the reload itself must work in this state too"
    finally:
        await teardown(owner)
