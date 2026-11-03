#!/usr/bin/env python3
"""Generate the Home Assistant copy of the EMS product names (ems_products.json).

Sources: data/html/ems-metadata.js, the metadata-only EMS reference the E32's own
EMS devices page uses (devices), and public/boilers/catalog-v1.json, the boiler
models the owner can choose on the E32 Boiler page (boiler_models: id -> brand and
name, the ids the E32 sends as "display_model"). Home Assistant names the devices
on the bus with these (ems_devices.py). Run with --check in CI and tests: exit 1
when the committed copy differs.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/html/ems-metadata.js"
CATALOG = ROOT / "public/boilers/catalog-v1.json"
TARGET = ROOT / "ha/config/custom_components/open_thermostat/ems_products.json"


def generate():
    text = SOURCE.read_text(encoding="utf-8")
    reference = json.loads(text[text.index("{"):text.rindex("}") + 1])
    devices = {}
    for device in reference["devices"]:
        devices.setdefault(str(device["product_id"]), []).append({"type": device["type"], "name": device["name"]})
    # Every model, also the ones hidden from new selections: a saved older choice stays named.
    models = {model["id"]: {"brand": model["brand"], "name": model["name"]}
              for model in json.loads(CATALOG.read_text(encoding="utf-8"))["models"] if model["kind"] != "none"}
    products = {"source": "data/html/ems-metadata.js", "devices": dict(sorted(devices.items(), key=lambda i: int(i[0]))),
                "models_source": "public/boilers/catalog-v1.json", "boiler_models": models}
    return json.dumps(products, indent=1, ensure_ascii=False, sort_keys=False) + "\n"


def main(argv):
    output = generate()
    if "--check" in argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != output:
            print(f"{TARGET.relative_to(ROOT)} is out of date: run scripts/generate_ems_products.py")
            return 1
        print("PASS ems_products.json matches data/html/ems-metadata.js and public/boilers/catalog-v1.json")
        return 0
    TARGET.write_bytes(output.encode("utf-8"))
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
