"""What the demo's Home Assistant needs beyond the test venv, into a cache directory outside the venv.

The venv of the HA tests (~/venvs/ha) has Core and the integration's dependencies, not the frontend nor the
packages of the integrations Core always loads (its bootstrap set) or imports for the frontend's service list
(homeassistant/helpers/service.py _base_components: ai_task, assist_satellite, camera, ...). Each package is
installed once, at the exact version this Core pins (its manifests or package_constraints.txt), without
dependencies, into <target>; Home Assistant runs with --skip-pip and that directory on PYTHONPATH, so the venv
is never changed. Two voice packages have no wheel for this Python and would need a compiler: they get a
stand-in module that only satisfies the import (the demo never runs a voice pipeline).

    python deps.py <target>      (with the venv's python; prints the target when it is complete)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import homeassistant
from homeassistant.const import __version__ as CORE

HA = Path(homeassistant.__file__).parent
# (component whose manifest pins it, or None for package_constraints.txt, PyPI name)
WANTED = [("frontend", "home-assistant-frontend"), ("hassio", "aiohasupervisor"), ("conversation", "hassil"),
          ("conversation", "home-assistant-intents"), ("conversation", "gazetteer-matcher"),
          ("camera", "PyTurboJPEG"), (None, "numpy"), ("tts", "mutagen"), ("ffmpeg", "ha-ffmpeg"),
          ("infrared", "infrared-protocols"), ("radio_frequency", "rf-protocols")]
# Dependencies of the packages above that Core does not pin itself.
EXTRA = ["unicode-rbnf==2.4.1"]
STUBS = {
    "pymicro_vad": "class MicroVad:\n    def __init__(self, *a, **k):\n        pass\n\n"
                   "    def Process10ms(self, *a, **k):\n        return -1\n",
    "pyspeex_noise": "class AudioProcessor:\n    def __init__(self, *a, **k):\n        pass\n\n"
                     "    def Process10ms(self, *a, **k):\n        return None\n",
}
CHECK = ("import hass_frontend, aiohasupervisor; import homeassistant.components.mqtt.config_flow; "
         "from homeassistant.components import ai_task, alarm_control_panel, assist_satellite, calendar, camera, "
         "climate, cover, fan, humidifier, light, lock, media_player, notify, remote, siren, todo, update, vacuum, "
         "water_heater, conversation, infrared, radio_frequency, ffmpeg, tts")


def pins():
    constraints = (HA / "package_constraints.txt").read_text(encoding="utf-8").splitlines()
    out = []
    for component, name in WANTED:
        lines = (json.loads((HA / "components" / component / "manifest.json").read_text(encoding="utf-8"))
                 .get("requirements", []) if component else constraints)
        match = [r.strip() for r in lines if re.match(re.escape(name) + r"==", r.strip(), re.IGNORECASE)]
        if not match:
            raise SystemExit(f"Core {CORE} pins no {name} (in {component or 'package_constraints.txt'})")
        out.append(match[0])
    return out + EXTRA


def check(target):
    env = {**os.environ, "PYTHONPATH": str(target)}
    result = subprocess.run([sys.executable, "-c", CHECK], env=env, capture_output=True, text=True)
    return result.returncode == 0, (result.stderr.strip().splitlines() or [""])[-1]


def main():
    target = Path(sys.argv[1])
    wanted = pins()
    stamp = target / ".complete"
    if stamp.exists() and stamp.read_text(encoding="utf-8").split() == wanted and check(target)[0]:
        print(target)
        return
    tmp = target.with_name(target.name + ".tmp")
    subprocess.run(["rm", "-rf", str(tmp)], check=True)
    print(f"Core {CORE}: installing {' '.join(wanted)} into {target} (once)", file=sys.stderr)
    uv = Path(sys.executable).with_name("uv")
    subprocess.run([str(uv), "pip", "install", "--quiet", "--no-deps", "--python", sys.executable, "--target", str(tmp),
                    *wanted], check=True)
    for module, text in STUBS.items():
        (tmp / (module + ".py")).write_text('"""Stand-in for the demo (tools/dev/ha-demo/deps.py): import only."""\n'
                                             + text, encoding="utf-8")
    ok, error = check(tmp)
    if not ok:
        raise SystemExit(f"the demo's packages do not import: {error}")
    (tmp / ".complete").write_text("\n".join(wanted) + "\n", encoding="utf-8")
    subprocess.run(["rm", "-rf", str(target)], check=True)
    tmp.rename(target)
    print(target)


if __name__ == "__main__":
    main()
