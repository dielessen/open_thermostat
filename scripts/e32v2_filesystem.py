"""Stage upstream web assets with inert E32 V2 defaults; never edit user data."""
import json
import shutil
from pathlib import Path

Import("env")
source = Path(env.subst("$PROJECT_DIR")) / "data"
staging = Path(env.subst("$BUILD_DIR")) / "data_e32v2"
shutil.copytree(source, staging, dirs_exist_ok=True)
(staging / "cfg/cfgpins.json").write_text(json.dumps({
    "ems": [4, 5], "boiler_pin": None, "valve_pins": [],
    "gpio_extenders": []
}, indent=2) + "\n")
network_path = staging / "cfg/cfgnetwork.json"
network = json.loads(network_path.read_text())
network.update(emsEnabled=False, emsForwarderEnabled=False, rtcEnabled=False)
network["mqtt"]["enabled"] = False
network_path.write_text(json.dumps(network, indent=2) + "\n")
# Do not ship upstream example rooms as an installed heating system.
(staging / "cfg/rooms.json").write_text("[]\n")
# Empty both sides of the room/program relation. An upstream example program
# with missing IDs blocks even the first catalog save through the REST guard.
for program in (staging / "programs").glob("*.json"):
    program.write_text("[]\n")
env.Replace(PROJECT_DATA_DIR=str(staging))
