"""A fake E32 for the demo: its web API (what "Connect E32" and the integration read and write) and its
retained MQTT telemetry, from scenario.py.

HTTP on a private address of the demo's own network namespace (the integration refuses loopback E32
addresses), the same cookie/CSRF/ETag contract as the firmware (the HA tests' fakes check it the same way):
POST /auth/login (form), GET /auth/session (csrf), POST /auth/logout; GET /status/version, /status,
/updates/status, /config/rooms, /config/heating(/comfort|/flow), /config/logging, /config/boiler-display,
/config/bluetooth; GET+POST /config/device (If-Match ETag), POST /updates/reboot (202), POST of the heating
documents. MQTT: the scenario's documents under <prefix>/v1/, retained, refreshed every minute, a heartbeat
every 30 s, online/offline with a last will. Nothing is persisted outside the demo's work directory.
"""
import argparse
import asyncio
import hashlib
import json
import secrets
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenario  # noqa: E402

BOOT = time.monotonic()
SESSION_COOKIE = "OTSESSION"
MAX_SESSIONS = 4


def uptime():
    return int(time.monotonic() - BOOT) + 86000  # "up since yesterday"


def etag(document):
    return '"' + hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest() + '"'


class E32:
    def __init__(self, args):
        self.args = args
        self.password = args.password
        self.sessions = {}  # cookie -> csrf
        host, port = args.mqtt.split(":")
        self.settings = {
            "hostname": "openthermostat", "interface_mode": "wifi", "listenPort": 80, "emsEnabled": True,
            "emsForwarderEnabled": False, "ntpEnabled": True, "ntpHost": "pool.ntp.org",
            "timeZone": "CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00",
            "mqtt": {"enabled": True, "modern_shadow": False, "adapter_id": "", "publishHomeAssistantDiscovery": False,
                     "brokerAddress": host, "brokerPort": int(port), "username": "e32", "password": "",
                     "clientId": args.prefix, "base": args.prefix, "keepAlive": 60, "interval": 30,
                     "native_shadow_source": None, "native_source_device_id": scenario.CONTROLLER_ID,
                     "native_source_live_apply": True}}
        self.control_mode = "legacy"  # the MQTT protocol: "shadow" once linked to Home Assistant
        self.plan = scenario.plan_document(mode=args.mode)
        self.flow = {"weather_curve": True, "apply_learned": True, "curve_design_flow_c": 40,
                     "tuning": {"min_on_s": 900, "min_off_s": 900, "heat_start_c": 0.2, "heat_stop_c": 0.1,
                                "flow_per_degree_c": 6, "curve_correction_pct": 96, "floor_lead_min_per_c": 140,
                                "radiator_lead_min_per_c": 60, "learned_accept_pct": 100, "night_saving_min_pct": 20},
                     "tuning_manual": []}
        self.logging = {"syslog_enabled": False, "server": "", "port": 514, "syslog_level": 3, "web_level": 3,
                        "mark_interval_s": 0, "syslog_esp": True, "syslog_ems": False}
        self.boiler_display = {"model": "nefit-ecomline-classic-hrc-22h"}
        self.holidays = []
        self.timeline = None
        self.client = None
        self.calls = []

    def save_state(self):
        Path(self.args.state).write_text(json.dumps({
            "control_mode": self.control_mode, "settings": self.settings, "plan_revision": self.plan["revision"],
            "calls": self.calls[-200:]}, indent=1), encoding="utf-8")

    # -- HTTP --------------------------------------------------------------------------------------------
    def session(self, request):
        cookie = request.cookies.get(SESSION_COOKIE)
        return cookie if cookie in self.sessions else None

    async def handle(self, request):
        path, method = request.path, request.method
        self.calls.append([round(time.monotonic() - BOOT, 1), method, path])
        if path == "/auth/login" and method == "POST":
            form = await request.post()
            if form.get("username") != "admin" or form.get("password") != self.password:
                return web.json_response({"error": "invalid_credentials"}, status=401)
            while len(self.sessions) >= MAX_SESSIONS:  # the oldest web session goes, as on the E32
                self.sessions.pop(next(iter(self.sessions)))
            cookie = secrets.token_hex(32)
            self.sessions[cookie] = secrets.token_hex(32)
            response = web.json_response({"authenticated": True})
            response.set_cookie(SESSION_COOKIE, cookie, httponly=True, samesite="Strict", path="/")
            return response
        cookie = self.session(request)
        if cookie is None:
            return web.json_response({"error": "authentication_required"}, status=401)
        if method == "POST" and request.headers.get("X-OpenThermostat-CSRF") != self.sessions[cookie]:
            return web.json_response({"error": "csrf_required"}, status=403)
        if path == "/auth/session":
            return web.json_response({"authenticated": True, "csrf": self.sessions[cookie], "expires_in": 900,
                                      "default_password": False})
        if path == "/auth/logout":
            self.sessions.pop(cookie, None)
            return web.json_response({"authenticated": False})
        handler = (self.reads if method == "GET" else self.writes).get(path)
        if handler is None:
            return web.json_response({"error": "not_found"}, status=404)
        response = await handler(request)
        self.save_state()
        return response

    @property
    def reads(self):
        return {"/status/version": self.version, "/status": self.status, "/updates/status": self.updates,
                "/config/device": self.device, "/config/rooms": self.rooms, "/config/heating": self.heating,
                "/config/heating/comfort": self.comfort, "/config/heating/flow": self.flow_settings,
                "/config/logging": self.logging_settings, "/config/boiler-display": self.display,
                "/config/bluetooth": self.bluetooth, "/status/heating": self.status_heating}

    @property
    def writes(self):
        return {"/config/device": self.save_device, "/updates/reboot": self.reboot, "/config/heating": self.save_plan,
                "/config/heating/comfort": self.comfort_command, "/config/heating/flow": self.save_flow,
                "/config/logging": self.save_logging, "/config/boiler-display": self.save_display,
                "/config/bluetooth": self.save_bluetooth}

    async def version(self, _request):
        return web.json_response({"project": "openthermostat", "version": scenario.FIRMWARE, "source": scenario.SOURCE,
                                  "web_sha256": scenario.WEB_SHA256, "date": "Nov  4 2026", "time": "18:00:00",
                                  "idf": "v4.4.7", "sha256": scenario.SHA256})

    async def status(self, _request):
        now = datetime.now(scenario.ZONE)
        return web.json_response({"rooms": [], "controlMode": self.control_mode,
                                  "firmware_update": {"known": True, "available": False, "version": "",
                                                      "interval_seconds": 43200, "checked_age_seconds": 1200},
                                  "time": now.strftime("%H:%M:%S"), "date": now.strftime("%Y-%m-%d"),
                                  "weekDay": now.isoweekday() % 7, "uptime": uptime()})

    async def updates(self, _request):
        return web.json_response({"installed": scenario.FIRMWARE, "source_commit": scenario.SOURCE,
                                  "web_sha256": scenario.WEB_SHA256, "phase": "idle", "error": "", "operation": "none",
                                  "busy": False, "can_check": True, "boot_pending": False, "reboot_required": False,
                                  "rollback_available": True, "reboot_scheduled": False, "received": 0, "total": 0,
                                  "releases": []})

    async def device(self, _request):
        return web.json_response(self.settings, headers={"ETag": etag(self.settings)})

    async def save_device(self, request):
        if request.headers.get("If-Match") != etag(self.settings):
            return web.json_response({"error": "device_settings_changed"}, status=412)
        document = await request.json()
        mqtt_part = document.get("mqtt") if isinstance(document, dict) else None
        if not isinstance(mqtt_part, dict) or not mqtt_part.get("username"):
            return web.json_response({"error": "invalid_settings"}, status=400)
        keep = {k: self.settings["mqtt"][k] for k in ("native_source_device_id", "native_source_live_apply")}
        self.settings = {**document, "mqtt": {**mqtt_part, **keep, "password": ""}}
        return web.Response(text="saved", status=201)

    async def reboot(self, _request):
        # The MQTT protocol follows the saved settings at the next start; the restart itself is instant here.
        self.control_mode = "shadow" if self.settings["mqtt"].get("modern_shadow") else "legacy"
        self.sessions.clear()
        if self.client is not None:
            asyncio.get_running_loop().call_later(1, self.publish_all)
        return web.json_response({"rebooting": True}, status=202)

    async def rooms(self, _request):
        return web.json_response([])

    async def heating(self, _request):
        return web.json_response(self.plan)

    async def save_plan(self, request):
        plan = await request.json()
        if plan.get("revision") != self.plan["revision"]:
            return web.json_response({"error": "plan_changed"}, status=409)
        self.plan = {**plan, "revision": plan["revision"] + 1}
        return web.json_response(self.plan)

    def comfort_state(self):
        return {"schema": 1, "rooms": [], "away": {"on": False, "source": "none", "target_c": 15, "until": None,
                                                    "presence": "unknown", "mode": "auto"},
                "holidays": [dict(h) for h in self.holidays], "holiday_temperature_c": 15}

    async def comfort(self, _request):
        return web.json_response(self.comfort_state())

    async def comfort_command(self, request):
        command = await request.json()
        if isinstance(command.get("holidays"), list):
            self.holidays = command["holidays"]
        return web.json_response(self.comfort_state())

    async def flow_settings(self, _request):
        return web.json_response(self.flow)

    async def save_flow(self, request):
        change = await request.json()
        self.flow.update({k: v for k, v in change.items() if k in ("weather_curve", "apply_learned", "curve_design_flow_c")})
        return web.json_response(self.flow)

    async def logging_settings(self, _request):
        return web.json_response(self.logging)

    async def save_logging(self, request):
        self.logging.update(await request.json())
        return web.json_response(self.logging)

    async def display(self, _request):
        return web.json_response(self.boiler_display)

    async def save_display(self, request):
        self.boiler_display = {"model": (await request.json()).get("model")}
        return web.json_response(self.boiler_display)

    def bluetooth_document(self):
        def device(address, name, temperature, humidity, battery):
            return {"address": address, "profile": "pvvx_thermometer", "encryption": "none", "name": name,
                    "key_stored": False, "control_qualified": False, "status": "received", "message_integrity": False,
                    "measurement_qualified": True, "frames_received": 412, "frames_ignored": 3,
                    "temperature": temperature, "humidity": humidity, "battery": battery, "rssi": -71,
                    "temperature_age_ms": 21000, "humidity_age_ms": 21000, "battery_age_ms": 21000,
                    "last_accepted_age_ms": 21000}
        return {"schema": 1, "pending_restart": False, "restart_scheduled": False, "config_error": "none",
                "queue_drops": 0, "scan_pending": False,
                "devices": [device(scenario.BLE_LIVING, "Thermometer woonkamer", 2046, 5280, 100),
                            device("a4c1380d7b90", "Thermometer slaapkamer", 1762, 5840, 83)],
                "discovery_full": False, "discovery_capacity": 32, "nearby": [], "nearby_devices": []}

    async def bluetooth(self, _request):
        document = self.bluetooth_document()
        return web.json_response(document, headers={"ETag": etag(document)})

    async def save_bluetooth(self, request):
        return web.json_response(self.bluetooth_document())

    async def status_heating(self, _request):
        return web.json_response(scenario.heating_status(self.timeline or scenario.Timeline(), self.args.mode))

    # -- MQTT --------------------------------------------------------------------------------------------
    def base(self):
        return self.settings["mqtt"]["base"] + "/v1/"

    def start_mqtt(self):
        host, port = self.args.mqtt.split(":")
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.args.prefix + "-fake-e32")
        client.will_set(self.base() + "fw/availability", "offline", qos=1, retain=True)
        client.on_connect = lambda c, *_: c.subscribe(self.base() + "ha/#")
        client.on_message = lambda c, u, m: self.calls.append([round(time.monotonic() - BOOT, 1), "MQTT", m.topic])
        client.connect(host, int(port), 30)
        client.loop_start()
        self.client = client

    def publish_all(self):
        """Every retained document of now (the scenario's timeline, renewed each time)."""
        self.timeline = scenario.Timeline()
        base = self.base()
        self.client.publish(base + "fw/availability", "online", qos=1, retain=True)
        for suffix, payload in scenario.telemetry(self.timeline, self.args.mode, uptime()):
            self.client.publish(base + suffix, payload, qos=1, retain=True)
        self.heartbeat()

    def heartbeat(self):
        self.client.publish(self.base() + "fw/heartbeat", scenario.heartbeat(uptime()), qos=0, retain=False)

    async def mqtt_loop(self):
        self.start_mqtt()
        self.publish_all()
        beat = 0
        while True:
            await asyncio.sleep(30)
            beat += 1
            self.heartbeat()
            if beat % 2 == 0:
                self.publish_all()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--mqtt", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--password", default="demo-e32-password")
    parser.add_argument("--mode", default="active", choices=("active", "shadow"))
    args = parser.parse_args()
    e32 = E32(args)
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", e32.handle)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, args.bind, args.port).start()
    print(f"fake E32 on http://{args.bind}:{args.port}, MQTT {args.mqtt} base {args.prefix}/v1/", flush=True)
    e32.save_state()
    await e32.mqtt_loop()


if __name__ == "__main__":
    asyncio.run(main())
