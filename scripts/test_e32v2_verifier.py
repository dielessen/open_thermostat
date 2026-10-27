"""Fault injection against the real post-build verifier; never accesses hardware."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class VerifierFaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sandbox = tempfile.TemporaryDirectory(prefix="e32v2-verifier-")
        cls.root = Path(cls.sandbox.name)
        project = Path(__file__).resolve().parents[1]
        for name in ("scripts/verify_e32v2.py", "scripts/verify_e32v2_web_assets.py",
                     "boards/bbqkees_e32v2.json", "partitions_e32v2.csv", "src/Board.h"):
            destination = cls.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project / name, destination)
        cls.build = cls.root / ".pio/build/e32v2"
        original = project / ".pio/build/e32v2"
        cls.build.mkdir(parents=True)
        for name in ("firmware.bin", "partitions.bin", "spiffs.bin", "e32v2_mqtt.cpp",
                     "embedded-web.json", "EmbeddedWebAssets.h"):
            shutil.copy2(original / name, cls.build / name)
        for name in ("src", "data_e32v2"):
            shutil.copytree(original / name, cls.build / name)
        shutil.copytree(project / "data/html", cls.root / "data/html")

    @classmethod
    def tearDownClass(cls):
        cls.sandbox.cleanup()

    def verify(self, succeeds):
        result = subprocess.run([sys.executable, str(self.root / "scripts/verify_e32v2.py")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, succeeds, result.stdout + result.stderr)
        if not succeeds:
            self.assertIn("AssertionError", result.stderr)

    def test_valid_build(self):
        self.verify(True)

    def test_stale_web_source(self):
        path = self.root / "data/html/index.html"
        saved = path.read_bytes()
        try:
            path.write_bytes(saved + b"<!-- stale -->")
            self.verify(False)
        finally:
            path.write_bytes(saved)

    def test_corrupt_gzip_digest(self):
        path = self.build / "embedded-web.json"
        saved = path.read_bytes()
        try:
            metadata = json.loads(saved)
            first = next(iter(metadata["gzip"].values()))
            first["sha256"] = "0" * 64
            path.write_text(json.dumps(metadata))
            self.verify(False)
        finally:
            path.write_bytes(saved)

    def corrupt_byte(self, name, index, value):
        path = self.build / name
        saved = path.read_bytes()
        changed = bytearray(saved)
        changed[index] = value
        try:
            path.write_bytes(changed)
            self.verify(False)
        finally:
            path.write_bytes(saved)

    def test_wrong_flash_size_header(self):
        self.corrupt_byte("firmware.bin", 3, 0x2F)  # 4MB rather than 16MB

    def test_wrong_compiled_partition_offset(self):
        self.corrupt_byte("partitions.bin", 5, 0xA0)  # NVS 0xA000 versus 0x9000

    def test_unsafe_filesystem_gpio(self):
        path = self.build / "data_e32v2/cfg/cfgpins.json"
        saved = path.read_text()
        try:
            config = json.loads(saved)
            config["boiler_pin"] = 5
            path.write_text(json.dumps(config))
            self.verify(False)
        finally:
            path.write_text(saved)

    def test_compiled_uart_transmit_regression(self):
        core = Path(os.environ.get("PLATFORMIO_CORE_DIR", Path.home() / ".platformio"))
        compiler = core / "packages/toolchain-xtensa-esp32/bin/xtensa-esp32-elf-gcc"
        obj = self.build / "src/unsafe-fixture.o"
        try:
            subprocess.run([str(compiler), "-x", "c", "-c", "-o", str(obj), "-"],
                           input="extern void uart_write_bytes(void); void unsafe(void) { uart_write_bytes(); }",
                           text=True, check=True, capture_output=True)
            self.verify(False)
        finally:
            obj.unlink(missing_ok=True)

    def test_missing_attended_uart_owner(self):
        obj = self.build / "src/EmsController.cpp.o"
        saved = obj.read_bytes()
        try:
            obj.unlink()
            self.verify(False)
        finally:
            obj.write_bytes(saved)

    def test_general_and_settings_source_permissions_stay_closed(self):
        path = self.root / "src/Board.h"
        saved = path.read_text()
        try:
            for flag in ("emsTransmitAllowed", "emsSettingsTransmitAllowed", "auxiliaryGpioAllowed"):
                path.write_text(saved.replace(f"constexpr bool {flag} = false;", f"constexpr bool {flag} = true;", 1))
                self.verify(False)
        finally:
            path.write_text(saved)

    def test_orphan_factory_program(self):
        path = self.build / "data_e32v2/programs/default.json"
        saved = path.read_bytes()
        try:
            path.write_text('[{"room_id":"409afa7c"}]')
            self.verify(False)
        finally:
            path.write_bytes(saved)

    def test_example_factory_rooms(self):
        path = self.build / "data_e32v2/cfg/rooms.json"
        saved = path.read_bytes()
        try:
            path.write_text('[{"id":"409afa7c","name":"Example"}]')
            self.verify(False)
        finally:
            path.write_bytes(saved)


if __name__ == "__main__":
    unittest.main(verbosity=2)
