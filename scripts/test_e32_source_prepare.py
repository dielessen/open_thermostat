"""Exercise actual safe extraction and failure before writing outside its output."""
from pathlib import Path
import hashlib
import io
import json
import tarfile
import unittest

import test_e32_source_inputs as fixtures
from e32_prepare_source_tree import prepare
from e32_relink import RelinkError
from e32_source_inputs import SourceInputError


class PrepareSources(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.SourceInputs()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        row = self.fixture.policy['archives'][0]
        row.update(component='esp-idf', repository='espressif/esp-idf', commit='fixture')
        self.root = self.fixture.archive.parent / 'checkout'
        self.recipes = self.root / 'docs/third-party/e32v2-reproduction'
        self.recipes.mkdir(parents=True)
        (self.recipes / 'README.md').write_bytes(b'Original recipe instructions')
        (self.recipes / 'MANIFEST.json').write_text(json.dumps(dict(schema=1, files={
            'README.md': hashlib.sha256(b'Original recipe instructions').hexdigest()})))
        self.output = self.fixture.archive.parent / 'prepared'
        self.write_inputs()

    def write_inputs(self):
        self.fixture.write()
        base = self.root / 'docs/third-party'
        (base / 'e32v2-source-inputs.json').write_text(json.dumps(self.fixture.policy))
        (base / 'e32v2-source-distribution.json').write_text(json.dumps(dict(
            bytes=self.fixture.archive.stat().st_size,
            sha256=hashlib.sha256(self.fixture.archive.read_bytes()).hexdigest())))

    def with_extra_member(self, name, *, link=None):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=io.BytesIO(self.fixture.files['sources/vendor.tar.gz']), mode='r:gz') as original:
            with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
                for member in original:
                    tar.addfile(member, original.extractfile(member))
                member = tarfile.TarInfo(name)
                if link:
                    member.type, member.linkname = tarfile.SYMTYPE, link
                    tar.addfile(member)
                else:
                    member.size = 4
                    tar.addfile(member, io.BytesIO(b'evil'))
        self.fixture.files['sources/vendor.tar.gz'] = buffer.getvalue()
        self.fixture.policy['payloads']['sources/vendor.tar.gz'] = hashlib.sha256(buffer.getvalue()).hexdigest()
        self.write_inputs()

    def test_original_source_and_recipe_bytes_are_prepared(self):
        result = prepare(self.root, self.fixture.archive, self.output)
        self.assertEqual(result['source_components'], 1)
        self.assertFalse(result['firmware_installed'])
        self.assertEqual((self.output / 'sources/esp-idf/source.c').read_bytes(),
                         b'/* original copyright */\nint source(void) {return 1;}\n')
        self.assertEqual((self.output / 'README.md').read_bytes(), b'Original recipe instructions')

    def test_original_internal_source_symlink_is_preserved(self):
        self.with_extra_member('vendor/alias.c', link='source.c')
        prepare(self.root, self.fixture.archive, self.output)
        link = self.output / 'sources/esp-idf/alias.c'
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.read_bytes(), (link.parent / 'source.c').read_bytes())

    def test_archive_path_escape_is_denied_before_output_creation(self):
        self.with_extra_member('../outside.c')
        with self.assertRaisesRegex(SourceInputError, 'unsafe_source_path'):
            prepare(self.root, self.fixture.archive, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse((self.output.parent / 'outside.c').exists())

    def test_unused_escaping_link_is_still_denied_by_extraction_filter(self):
        self.with_extra_member('vendor/leak.c', link='../../../../outside.c')
        with self.assertRaises(tarfile.FilterError):
            prepare(self.root, self.fixture.archive, self.output)
        self.assertFalse((self.output.parent / 'outside.c').exists())

    def test_existing_user_directory_is_preserved(self):
        self.output.mkdir()
        (self.output / 'keep.txt').write_bytes(b'preserve')
        with self.assertRaisesRegex(RelinkError, 'output_already_exists'):
            prepare(self.root, self.fixture.archive, self.output)
        self.assertEqual((self.output / 'keep.txt').read_bytes(), b'preserve')

    def test_changed_archive_is_denied_before_output_creation(self):
        with self.fixture.archive.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(RelinkError, 'digest_conflict'):
            prepare(self.root, self.fixture.archive, self.output)
        self.assertFalse(self.output.exists())

    def test_changed_or_extra_recipe_is_denied_before_output_creation(self):
        (self.recipes / 'README.md').write_bytes(b'changed')
        with self.assertRaisesRegex(RelinkError, 'recipe_hash_conflict'):
            prepare(self.root, self.fixture.archive, self.output)
        self.assertFalse(self.output.exists())
        (self.recipes / 'unlisted.py').write_bytes(b'extra code')
        with self.assertRaisesRegex(RelinkError, 'recipe_inventory_conflict'):
            prepare(self.root, self.fixture.archive, self.output)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
