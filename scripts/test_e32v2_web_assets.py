import gzip
import json
from pathlib import Path
import re
import runpy
import tempfile
import unittest
from unittest.mock import patch

from verify_e32v2_web_assets import verify

SCRIPT = Path(__file__).with_name("e32v2_web_assets.py")


class WebAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "build"
        self.source = self.root / "data/html"
        self.source.mkdir(parents=True)
        (self.root / "release.json").write_text('{"version":"v-test"}')
        (self.source / "index.html").write_bytes(b"<p>compressed text</p>" * 400)
        (self.source / "small.js").write_bytes(b"window.small=true;")
        (self.source / "library.js.gz").write_bytes(gzip.compress(b"precompressed" * 300, mtime=0))

    def generate(self):
        root, build, source = self.root, self.build, self.source

        class Env:
            def subst(self, value):
                return str({"$PROJECT_DIR": root, "$BUILD_DIR": build}[value])

            def GetProjectOption(self, *_):
                names = [str(p.relative_to(root)) for p in sorted(source.iterdir())]
                return "\n".join(names + ["certs/github-ca-bundle.bin"])

            def Append(self, **_):
                pass

        with patch("subprocess.check_output", return_value="1" * 40):
            runpy.run_path(str(SCRIPT), init_globals={"env": Env(), "Import": lambda _: None})
        header = (build / "EmbeddedWebAssets.h").read_text()
        packed = []
        for value in re.findall(r"inline const uint8_t gzip\d+\[\] = \{([^}]+)\};", header):
            packed.append(bytes(int(n, 16) for n in re.findall(r"0x([0-9a-f]{2})", value)))
        self.image = b"app" + b"".join(p.read_bytes() for p in sorted(source.iterdir())) + b"".join(packed)
        (build / "firmware.bin").write_bytes(self.image)
        return json.loads((build / "embedded-web.json").read_text())

    def test_repeat_builds_are_stable_without_recompressing_gzip_or_small_files(self):
        meta = self.generate()
        before = (self.build / "EmbeddedWebAssets.h").read_bytes()
        mtime = (self.build / "EmbeddedWebAssets.h").stat().st_mtime_ns
        self.assertEqual(set(meta["gzip"]), {"index.html"})
        self.generate()
        self.assertEqual((self.build / "EmbeddedWebAssets.h").read_bytes(), before)
        self.assertEqual((self.build / "EmbeddedWebAssets.h").stat().st_mtime_ns, mtime)
        self.assertEqual(verify(self.root, self.build)["gzip_representations"], 1)

    def test_source_edits_replace_both_identity_and_compressed_representation(self):
        before = self.generate()
        (self.source / "index.html").write_bytes(b"<p>new page</p>" * 400)
        after = self.generate()
        self.assertNotEqual(before["web_sha256"], after["web_sha256"])
        self.assertNotEqual(before["gzip"], after["gzip"])
        self.assertEqual(verify(self.root, self.build)["status"], "PASS")

    def test_stale_source_is_rejected(self):
        self.generate()
        (self.source / "small.js").write_bytes(b"changed")
        with self.assertRaisesRegex(AssertionError, "stale asset"):
            verify(self.root, self.build)

    def test_missing_original_or_compressed_image_bytes_are_rejected(self):
        self.generate()
        (self.build / "firmware.bin").write_bytes(self.image[:-1])
        with self.assertRaisesRegex(AssertionError, "gzip representation missing"):
            verify(self.root, self.build)
        (self.build / "firmware.bin").write_bytes(self.image.replace(b"window.small=true;", b"gone"))
        with self.assertRaisesRegex(AssertionError, "original source asset missing"):
            verify(self.root, self.build)


if __name__ == "__main__":
    unittest.main()
