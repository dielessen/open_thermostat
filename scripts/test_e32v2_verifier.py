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
        for name in ("scripts/verify_e32v2.py", "boards/bbqkees_e32v2.json", "partitions_e32v2.csv"):
            destination = cls.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project / name, destination)
        cls.build = cls.root / ".pio/build/e32v2"
        original = project / ".pio/build/e32v2"
        cls.build.mkdir(parents=True)
        for name in ("firmware.bin", "partitions.bin", "spiffs.bin", "e32v2_mqtt.cpp"):
            shutil.copy2(original / name, cls.build / name)
        for name in ("src", "data_e32v2"):
            shutil.copytree(original / name, cls.build / name)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
