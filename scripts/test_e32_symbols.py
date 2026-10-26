"""Artifact binding fixtures only; not real MCU or ELF execution acceptance."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from e32_symbols import export,verify


class E32Symbols(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.build=self.root/'build';self.package=self.root/'package'
        self.build.mkdir();self.package.mkdir()
        self.elf=b'\x7fELF\x01\x01'+b'fake debug ELF binding fixture'*20
        (self.build/'firmware.elf').write_bytes(self.elf)
        (self.build/'firmware.map').write_bytes(b'Linker script and memory map\nfixture symbols\n')
        self.manifest=dict(version='v0.1.0-e32v2-beta.1',source_commit='a'*40,web_sha256='b'*64)
        (self.build/'embedded-web.json').write_text(json.dumps(dict(version=self.manifest['version'],source='a'*40,web_sha256='b'*64)))
        image=bytearray(1024);image[0]=0xe9;image[0xb0:0xd0]=hashlib.sha256(self.elf).digest()
        marker=f"OT_E32V2_OTA_V1:{self.manifest['version']}:{'a'*40}:{'b'*64}:END".encode();image[512:512+len(marker)]=marker
        self.image=bytes(image)
        for target in (self.build,self.package):(target/'firmware.bin').write_bytes(self.image)
        self.manifest.update(size=len(self.image),sha256=hashlib.sha256(self.image).hexdigest())
        (self.package/'e32v2-update.json').write_text(json.dumps(self.manifest))

    def test_exact_symbols_metadata_and_readback_are_bound_to_image(self):
        report=export(self.build,self.package)
        self.assertEqual(verify(self.package),report)
        self.assertFalse(report['physical_acceptance']);self.assertFalse(report['executable_for_installation'])
        self.assertEqual((self.package/'symbols/firmware.elf').read_bytes(),self.elf)
        self.assertEqual(report['elf_sha256'],hashlib.sha256(self.elf).hexdigest())

    def test_mismatched_elf_refused_before_output(self):
        (self.build/'firmware.elf').write_bytes(self.elf+b'changed')
        with self.assertRaisesRegex(ValueError,'descriptor_conflict'):export(self.build,self.package)
        self.assertFalse((self.package/'symbols').exists())

    def test_stale_web_identity_or_image_copy_refused(self):
        meta=(self.build/'embedded-web.json').read_bytes()
        for change in ('version','source','web_sha256'):
            data=json.loads(meta);data[change]='stale'
            (self.build/'embedded-web.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'web_identity_conflict'):export(self.build,self.package)
            self.assertFalse((self.package/'symbols').exists())
        (self.build/'embedded-web.json').write_bytes(meta)
        (self.build/'firmware.bin').write_bytes(self.image+b'changed')
        with self.assertRaisesRegex(ValueError,'build_image_conflict'):export(self.build,self.package)

    def test_corrupt_map_report_or_unexpected_research_image_is_rejected(self):
        export(self.build,self.package);folder=self.package/'symbols'
        source=(folder/'firmware.map').read_bytes();(folder/'firmware.map').write_bytes(source+b'changed')
        with self.assertRaisesRegex(ValueError,'report_conflict'):verify(self.package)
        (folder/'firmware.map').write_bytes(source)
        (folder/'MODIFIED-NOT-FOR-INSTALL.elf').write_bytes(self.elf)
        with self.assertRaisesRegex(ValueError,'inventory_conflict'):verify(self.package)

    def test_export_never_replaces_existing_symbol_directory(self):
        report=export(self.build,self.package)
        with self.assertRaisesRegex(ValueError,'already_exists'):export(self.build,self.package)
        self.assertEqual(verify(self.package),report)

    def test_symlink_input_and_missing_or_invalid_map_fail_before_output(self):
        (self.build/'firmware.elf').unlink();(self.root/'outside.elf').write_bytes(self.elf)
        (self.build/'firmware.elf').symlink_to(self.root/'outside.elf')
        with self.assertRaises(OSError):export(self.build,self.package)
        self.assertFalse((self.package/'symbols').exists())
        (self.build/'firmware.elf').unlink();(self.build/'firmware.elf').write_bytes(self.elf)
        (self.build/'firmware.map').write_bytes(b'not a linker map')
        with self.assertRaisesRegex(ValueError,'link_map_invalid'):export(self.build,self.package)
