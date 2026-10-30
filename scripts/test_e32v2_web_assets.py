import gzip
import json
from pathlib import Path
import re
import runpy
import tempfile
import unittest
from unittest.mock import patch

from verify_e32v2_web_assets import image_sources, source_in_image, verify

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
        self.embedded = None

    def generate(self):
        root, build, source, test = self.root, self.build, self.source, self

        class Env:
            def subst(self, value):
                return str({"$PROJECT_DIR": root, "$BUILD_DIR": build}[value])

            def GetProjectOption(self, *_):
                if test.embedded is not None:
                    return "\n".join(test.embedded)
                names = [str(p.relative_to(root)) for p in sorted(source.iterdir()) if p.suffix == ".gz"]
                return "\n".join(names + ["certs/github-ca-bundle.bin"])

            def Append(self, **_):
                pass

        with patch("subprocess.check_output", return_value="1" * 40):
            runpy.run_path(str(SCRIPT), init_globals={"env": Env(), "Import": lambda _: None})
        header = (build / "EmbeddedWebAssets.h").read_text()
        packed = []
        for value in re.findall(r"inline const uint8_t asset\d+\[\] = \{([^}]+)\};", header):
            packed.append(bytes(int(n, 16) for n in re.findall(r"0x([0-9a-f]{2})", value)))
        # The linker image: embedded .gz files and the generated arrays, no other source bytes.
        self.image = (b"app" + b"".join(p.read_bytes() for p in sorted(source.iterdir()) if p.suffix == ".gz")
                      + b"".join(packed))
        (build / "firmware.bin").write_bytes(self.image)
        return json.loads((build / "embedded-web.json").read_text())

    def test_every_text_asset_is_gzip_only_and_repeat_builds_are_stable(self):
        meta = self.generate()
        before = (self.build / "EmbeddedWebAssets.h").read_bytes()
        mtime = (self.build / "EmbeddedWebAssets.h").stat().st_mtime_ns
        self.assertEqual(meta["representation"], "gzip-only")
        self.assertEqual(set(meta["gzip"]), {"index.html", "small.js"})  # also the small file
        self.assertNotIn("library.js.gz", meta["gzip"])                    # served as stored
        self.assertIn('struct Asset { const char *path; const uint8_t *bytes; size_t size; const char *etag; };',
                      before.decode())
        self.generate()
        self.assertEqual((self.build / "EmbeddedWebAssets.h").read_bytes(), before)
        self.assertEqual((self.build / "EmbeddedWebAssets.h").stat().st_mtime_ns, mtime)
        result = verify(self.root, self.build)
        self.assertEqual((result["gzip_representations"], result["assets"]), (2, 3))

    def test_source_edits_replace_the_compressed_representation(self):
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

    def test_missing_or_duplicate_image_bytes_are_rejected(self):
        self.generate()
        (self.build / "firmware.bin").write_bytes(self.image[:-1])
        with self.assertRaisesRegex(AssertionError, "gzip representation missing"):
            verify(self.root, self.build)
        stored = (self.source / "library.js.gz").read_bytes()
        (self.build / "firmware.bin").write_bytes(self.image.replace(stored, b"gone"))
        with self.assertRaisesRegex(AssertionError, "precompressed source asset missing"):
            verify(self.root, self.build)
        (self.build / "firmware.bin").write_bytes(self.image + (self.source / "index.html").read_bytes())
        with self.assertRaisesRegex(AssertionError, "uncompressed duplicate"):
            verify(self.root, self.build)

    def test_embed_list_must_hold_only_precompressed_assets(self):
        self.embedded = ["data/html/index.html", "data/html/library.js.gz", "certs/github-ca-bundle.bin"]
        with self.assertRaisesRegex(RuntimeError, "precompressed"):
            self.generate()

    def test_unknown_asset_types_are_refused(self):
        (self.source / "logo.png").write_bytes(b"\x89PNG")
        with self.assertRaisesRegex(RuntimeError, "logo.png"):
            self.generate()

    def test_release_checks_find_sources_from_the_image_alone(self):
        self.generate()
        streams = image_sources(self.image)
        for path in sorted(self.source.iterdir()):
            self.assertTrue(source_in_image(path.name, path.read_bytes(), self.image, streams), path.name)
        self.assertFalse(source_in_image("index.html", b"<p>other</p>", self.image, streams))
        self.assertFalse(source_in_image("library.js.gz", gzip.compress(b"other", mtime=0), self.image, streams))


if __name__ == "__main__":
    unittest.main()
