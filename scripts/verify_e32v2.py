"""Post-build checks independent of the C++ safety policy (no hardware access)."""
import csv
import json
import os
from pathlib import Path
import subprocess
import struct
from verify_e32v2_web_assets import verify as verify_web_assets

root = Path(__file__).resolve().parents[1]
build = root / ".pio/build/e32v2"
rows = []
for row in csv.reader((root / "partitions_e32v2.csv").read_text().splitlines()):
    if not row or row[0].lstrip().startswith("#"):
        continue
    name, kind, subtype, offset, size = [field.strip() for field in row[:5]]
    rows.append((name, kind, subtype, int(offset, 0), int(size, 0)))
compiled_rows = []
partition_binary = (build / "partitions.bin").read_bytes()
for offset in range(0, len(partition_binary), 32):
    magic, kind, subtype, start, size, label, flags = struct.unpack(
        "<HBBII16sI", partition_binary[offset:offset + 32])
    if magic != 0x50AA:
        break  # MD5/end marker
    compiled_rows.append((label.rstrip(b"\0").decode(), start, size))
assert compiled_rows == [(r[0], r[3], r[4]) for r in rows], "compiled partition table differs"
image = (build / "firmware.bin").read_bytes()
print(json.dumps(verify_web_assets(root, build)))
assert image[0] == 0xE9 and image[2] == 2, "not an ESP DIO image"
assert image[3] >> 4 == 4, "image flash header is not 16MB"
end = 0x9000
for name, kind, subtype, offset, size in rows:
    assert offset >= end, f"overlap at {name}"
    assert offset % (0x10000 if kind == "app" else 0x1000) == 0, name
    assert size > 0 and size % 0x1000 == 0, name
    end = offset + size
assert end <= 0x1000000, "layout exceeds 16MB"
slots = [r for r in rows if r[1] == "app"]
assert {r[2] for r in slots} == {"ota_0", "ota_1"}
firmware_size = (build / "firmware.bin").stat().st_size
assert all(firmware_size <= r[4] for r in slots)
filesystems = [r for r in rows if r[2] == "spiffs"]
assert {r[0] for r in filesystems} == {"spiffs0", "spiffs1"}
assert filesystems[0][4] == filesystems[1][4]
assert (build / "spiffs.bin").stat().st_size <= filesystems[0][4]
assert any(r[2] == "nvs" for r in rows) and any(r[2] == "ota" for r in rows)
staged = build / "data_e32v2/cfg"
assert json.loads((staged / "rooms.json").read_text()) == [], "factory room catalog must be empty"
programs = staged.parent / "programs"
assert (programs / "default.json").is_file(), "factory default program missing"
for program in programs.glob("*.json"):
    assert json.loads(program.read_text()) == [], f"factory program contains example/unknown rooms: {program.name}"
pins = json.loads((staged / "cfgpins.json").read_text())
assert pins["ems"] == [4, 5]
assert not pins["boiler_pin"] and not pins["valve_pins"] and not pins["gpio_extenders"]
assert "i2c" not in pins and "ems_forwarder" not in pins
network = json.loads((staged / "cfgnetwork.json").read_text())
assert not any(network[k] for k in ("emsEnabled", "emsForwarderEnabled", "rtcEnabled"))
patched = (build / "e32v2_mqtt.cpp").read_text()
assert "WiFi.status()" not in patched
assert "heating::networkConnected()" in patched
board = json.loads((root / "boards/bbqkees_e32v2.json").read_text())
assert board["build"]["mcu"] == "esp32"
assert board["upload"]["flash_size"] == "16MB"
assert "BOARD_HAS_PSRAM" in board["build"]["extra_flags"]
# Check the shipped policy and compiler output. Only the finite, attended
# commissioning path may own UART writes; legacy and persistent writers stay off.
policy = (root / "src/Board.h").read_text().split("#ifdef OPENTHERMOSTAT_E32V2", 1)[1].split("#else", 1)[0]
assert "constexpr bool emsTransmitAllowed = false;" in policy
assert "constexpr bool emsManualTestTransmitAllowed = true;" in policy
assert "constexpr bool auxiliaryGpioAllowed = false;" in policy
assert "constexpr bool emsSettingsTransmitAllowed = false;" in (root / "src/Board.h").read_text()
core = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
nm = core / "packages/toolchain-xtensa-esp32/bin/xtensa-esp32-elf-nm"
objects = list((build / "src").rglob("*.o"))
assert objects
owners = []
for obj in sorted(objects):
    symbols = {line.split()[-1] for line in subprocess.check_output([str(nm), "-u", str(obj)], text=True).splitlines() if line.split()}
    assert not symbols.intersection({"uart_send_break", "uart_tx_chars", "uart_write_bytes_with_break"}), obj
    if "uart_write_bytes" in symbols:
        owners.append(obj.relative_to(build).as_posix())
assert owners == ["src/EmsController.cpp.o"], owners
print(f"PASS: partition bounds/alignment, dual OTA ({firmware_size}/{slots[0][4]} bytes), "
      "dual SPIFFS, inert defaults, PSRAM flags, network gate, controller-only attended UART route")
