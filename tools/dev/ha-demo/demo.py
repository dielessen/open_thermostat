"""The OpenThermostat demo Home Assistant: real Core, the integration, a fake E32, screenshots.

Started by run.sh inside a private network namespace (unshare: only a loopback interface, plus the fake
E32's private address on it, and no route anywhere else), as the namespace's root: nothing here can reach
the home network. See README.md.
"""
import argparse
import asyncio
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

from hass_api import Hass, HassError  # noqa: E402
from procs import Processes, wait_port  # noqa: E402

E32_IP = "10.77.0.2"   # private (the integration refuses loopback E32 addresses); exists only in the namespace
E32_PORT = 80
HA_PORT = 18930
MQTT_PORT = 18931
PREFIX = "openthermostat"
E32_PASSWORD = "demo-e32-password"  # the fake E32's own throwaway password (fake_e32.py default)
LOG = []


def say(text):
    line = time.strftime("%H:%M:%S ") + text
    LOG.append(line)
    print(line, flush=True)


def isolated_network():
    """Bring up the namespace's loopback with the fake E32's address; refuse to run with any other route."""
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    have = subprocess.run(["ip", "-4", "-o", "addr", "show", "dev", "lo"], capture_output=True, text=True).stdout
    if E32_IP not in have:
        subprocess.run(["ip", "addr", "add", E32_IP + "/32", "dev", "lo"], check=True)
    links = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True, check=True).stdout
    names = [line.split(":")[1].strip().split("@")[0] for line in links.splitlines() if line.strip()]
    routes = subprocess.run(["ip", "-4", "route", "show"], capture_output=True, text=True, check=True).stdout.strip()
    if names != ["lo"] or routes:
        raise SystemExit(f"not an isolated network namespace (links {names}, routes {routes!r}): run via run.sh")
    say(f"network: only lo (127.0.0.1, {E32_IP}), no routes")


def write_mosquitto(work):
    conf = work / "mosquitto.conf"
    conf.write_text(f"listener {MQTT_PORT} 127.0.0.1\nallow_anonymous true\npersistence false\n"
                    "log_type error\nlog_type warning\nuser root\n", encoding="utf-8")
    return conf


def write_ha_config(config, language):
    config.mkdir(parents=True, exist_ok=True)
    (config / "configuration.yaml").write_text(f"""# OpenThermostat demo (tools/dev/ha-demo): written by demo.py, thrown away afterwards.
homeassistant:
  name: Demo house
  latitude: 52.09
  longitude: 5.12
  elevation: 5
  unit_system: metric
  currency: EUR
  country: NL
  time_zone: Europe/Amsterdam
  language: {language}
  internal_url: http://127.0.0.1:{HA_PORT}
http:
  server_host: 127.0.0.1
  server_port: {HA_PORT}
frontend:
config:
history:
logbook:
recorder:
  commit_interval: 1
  purge_keep_days: 30
logger:
  default: warning
  logs:
    custom_components.open_thermostat: info
""", encoding="utf-8")
    target = config / "custom_components" / "open_thermostat"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(REPO / "ha/config/custom_components/open_thermostat", target,
                    ignore=shutil.ignore_patterns("__pycache__"))


def set_language(config, language):
    path = config / "configuration.yaml"
    text = path.read_text(encoding="utf-8")
    lines = [f"  language: {language}" if line.startswith("  language: ") else line for line in text.splitlines()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Demo:
    def __init__(self, args):
        self.args = args
        self.work = Path(args.work).resolve()
        self.out = Path(args.out).resolve()
        self.config = self.work / "ha"
        self.logs = self.work / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self.procs = Processes(str(self.logs))
        self.base = f"http://127.0.0.1:{HA_PORT}"
        # A throwaway password, kept only in this run's temporary directory.
        secret = self.work / "demo-user.json"
        if not secret.exists():
            secret.write_text(json.dumps({"username": "demo", "password": secrets.token_urlsafe(18)}), encoding="utf-8")
            os.chmod(secret, 0o600)
        self.user = json.loads(secret.read_text(encoding="utf-8"))
        self.entry_id = None

    # -- processes -----------------------------------------------------------------------------------
    def start_broker(self):
        conf = write_mosquitto(self.work)
        self.procs.start("mosquitto", [self.args.mosquitto, "-c", str(conf)])
        if not wait_port("127.0.0.1", MQTT_PORT, 15):
            raise SystemExit("the MQTT broker did not start (logs/mosquitto.log)")
        say(f"broker: mosquitto on 127.0.0.1:{MQTT_PORT}")

    def start_e32(self):
        env = dict(os.environ)
        self.procs.start("fake-e32", [sys.executable, "-u", str(HERE / "fake_e32.py"), "--bind", E32_IP,
                                      "--port", str(E32_PORT), "--mqtt", f"127.0.0.1:{MQTT_PORT}",
                                      "--prefix", PREFIX, "--state", str(self.work / "e32-state.json")], env=env)
        if not wait_port(E32_IP, E32_PORT, 20):
            raise SystemExit("the fake E32 did not start (logs/fake-e32.log)")
        say(f"fake E32: http://{E32_IP} (+ its MQTT telemetry under {PREFIX}/v1/)")

    def start_ha(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (self.args.frontend_deps, env.get("PYTHONPATH")) if p)
        argv = [self.args.hass, "-c", str(self.config), "--skip-pip", "--log-no-color"]
        self.procs.start("hass", argv, env=env)
        say(f"Home Assistant: starting ({self.base}, config {self.config})")

    def stop_ha(self):
        self.procs.stop("hass", timeout=90)
        say("Home Assistant: stopped")

    async def ha_ready(self, hass):
        t0 = time.monotonic()
        await hass.wait_up(self.args.ha_timeout)
        say(f"Home Assistant: HTTP up after {time.monotonic() - t0:.0f} s")

    # -- set-up ----------------------------------------------------------------------------------------
    async def onboard(self, hass):
        await hass.onboard("Demo", self.user["username"], self.user["password"], self.args.languages[0])
        say("onboarding: owner user, core config, analytics, integration step done")

    async def mqtt_entry(self, hass):
        entries = await hass.get("/api/config/config_entries/entry?domain=mqtt")
        if entries:
            return
        flow = await hass.flow_start("mqtt")
        while flow["type"] == "menu":
            flow = await hass.flow_step(flow["flow_id"], {"next_step_id": "broker"})
        if flow["type"] == "form":
            flow = await hass.flow_step(flow["flow_id"], hass.form_defaults(
                flow["data_schema"], broker="127.0.0.1", port=MQTT_PORT,
                other_settings={"set_client_cert": False, "set_ca_cert": "off"}))
        if flow["type"] != "create_entry":
            raise HassError(f"MQTT flow: {flow}")
        say("MQTT: config entry for the local broker created")

    async def ot_entry(self, hass):
        entries = await hass.get("/api/config/config_entries/entry?domain=open_thermostat")
        if entries:
            self.entry_id = entries[0]["entry_id"]
            return
        flow = await hass.flow_start("open_thermostat")
        if flow["type"] != "form" or flow["step_id"] != "installation":
            raise HassError(f"OpenThermostat flow: {flow}")
        flow = await hass.flow_step(flow["flow_id"], {"name": "OpenThermostat", "create_dashboard": True,
                                                      "advanced": {"topic_prefix": PREFIX}})
        if flow["type"] != "create_entry":
            raise HassError(f"OpenThermostat flow: {flow}")
        self.entry_id = flow["result"]["entry_id"]
        say(f"OpenThermostat: installation entry {self.entry_id} created")

    async def house_states(self, hass):
        """The house's own Home Assistant entities the E32 plan reads (a tado-style thermostat, the bathroom
        thermostat) and the outdoor temperature: plain states, as another integration would provide them."""
        import scenario
        tl = scenario.Timeline()
        for entity_id, state, attributes in (
                (scenario.TADO, "heat", {"friendly_name": "tado Woonkamer", "current_temperature": 20.4,
                                         "temperature": 21.0, "hvac_modes": ["off", "heat", "auto"],
                                         "min_temp": 5, "max_temp": 25, "target_temp_step": 0.1,
                                         "supported_features": 1}),
                (scenario.BATHROOM_THERMOSTAT, "heat", {"friendly_name": "Thermostaat badkamer",
                                                        "current_temperature": 18.6, "temperature": 15.0,
                                                        "hvac_modes": ["off", "heat"], "min_temp": 5, "max_temp": 30,
                                                        "supported_features": 1}),
                (scenario.OUTDOOR, str(tl.outdoor[-1]), {"friendly_name": "Buitentemperatuur",
                                                         "unit_of_measurement": "°C", "device_class": "temperature",
                                                         "state_class": "measurement"})):
            await hass.post("/api/states/" + entity_id, {"state": state, "attributes": attributes})
        say("house entities: tado-style thermostat, bathroom thermostat, outdoor temperature")

    async def options_menu(self, hass, *path):
        """An options flow of the installation, walked through its menus to the last step id of path."""
        flow = await hass.flow_start(self.entry_id, kind="options")
        for step in path:
            if flow["type"] != "menu":
                raise HassError(f"options flow: expected a menu before {step}: {flow}")
            flow = await hass.flow_step(flow["flow_id"], {"next_step_id": step}, kind="options")
        return flow

    async def connect_e32(self, hass):
        """Configure -> E32 connection, as a user does it: the fake E32's address and password."""
        entries = await hass.get("/api/config/config_entries/entry?domain=open_thermostat")
        flow = await self.options_menu(hass, "controller_connection")
        if flow["type"] != "form" or flow["step_id"] != "controller_connection":
            raise HassError(f"Connect E32: {flow}")
        flow = await hass.flow_step(flow["flow_id"], {"address": f"http://{E32_IP}", "password": E32_PASSWORD},
                                    kind="options")
        loop = asyncio.get_running_loop()
        end = loop.time() + 150
        while flow["type"] == "progress" and loop.time() < end:
            await asyncio.sleep(1)
            flow = await hass.flow_get(flow["flow_id"], kind="options")
        if flow["type"] == "progress_done":
            flow = await hass.flow_get(flow["flow_id"], kind="options")
        if flow["type"] == "form" and flow["step_id"].startswith("controller_connected"):
            flow = await hass.flow_step(flow["flow_id"], {}, kind="options")
        if flow["type"] != "abort" or flow.get("reason") != "controller_connection_complete":
            raise HassError(f"Connect E32 did not complete: {flow}")
        say(f"Connect E32: linked to http://{E32_IP} ({len(entries)} installation)")

    async def run(self):
        isolated_network()
        write_ha_config(self.config, self.args.languages[0])
        self.start_broker()
        self.start_e32()
        self.start_ha()
        async with Hass(self.base) as hass:
            await self.ha_ready(hass)
            await self.onboard(hass)
            await self.mqtt_entry(hass)
            await self.ot_entry(hass)
            await self.house_states(hass)
            await self.connect_e32(hass)
            await asyncio.sleep(10)
            states = await hass.get("/api/states")
            ours = [s for s in states if "woonkamer" in s["entity_id"] or "boiler" in s["entity_id"]]
            say(f"{len(states)} states, e.g. " + ", ".join(f"{s['entity_id']}={s['state']}" for s in ours[:30]))
            panels = await hass.ws("get_panels")
            say("panels: " + ", ".join(sorted(panels)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--languages", default="en,nl")
    parser.add_argument("--hass", required=True)
    parser.add_argument("--mosquitto", default="/usr/sbin/mosquitto")
    parser.add_argument("--frontend-deps", required=True)
    parser.add_argument("--ha-timeout", type=int, default=240)
    args = parser.parse_args()
    args.languages = [x for x in args.languages.split(",") if x]
    demo = Demo(args)
    t0 = time.monotonic()
    try:
        asyncio.run(demo.run())
    finally:
        demo.procs.stop_all()
        say(f"done in {time.monotonic() - t0:.0f} s; every process stopped")
        (demo.work / "demo.log").write_text("\n".join(LOG) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
