"""Denial checks for the target-specific source/input correspondence boundary."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from e32_relink import RelinkError, relink
from e32_source_closure import retained_inventory, source_inventory


class SourceClosure(unittest.TestCase):
    def test_original_source_bytes_and_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/original.c').write_bytes(b'original source')
            expected = {'src/original.c': hashlib.sha256(b'original source').hexdigest()}
            self.assertEqual(source_inventory(root, expected, ['src']), 1)
            (root / 'src/original.c').write_bytes(b'changed source')
            with self.assertRaisesRegex(RelinkError, 'bytes_changed'):
                source_inventory(root, expected, ['src'])

    def test_extra_compiled_source_cannot_hide_beside_unchanged_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/added.c').write_bytes(b'unreviewed source')
            with self.assertRaisesRegex(RelinkError, 'inventory_missing_or_unreviewed'):
                source_inventory(root, {}, ['src'])

    def test_directory_symlink_cannot_hide_extra_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'hidden').mkdir()
            (root / 'hidden/added.c').write_bytes(b'extra')
            (root / 'src/link').symlink_to(root / 'hidden', target_is_directory=True)
            with self.assertRaisesRegex(RelinkError, 'directory_link'):
                source_inventory(root, {}, ['src'])

    def test_source_file_link_cannot_escape_reviewed_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'outside.c').write_bytes(b'original source')
            (base / 'root/src').mkdir(parents=True)
            (base / 'root/src/linked.c').symlink_to(base / 'outside.c')
            with self.assertRaisesRegex(RelinkError, 'external_relink_path'):
                source_inventory(base / 'root', {'src/linked.c': hashlib.sha256(b'original source').hexdigest()}, ['src'])

    def review(self):
        return dict(retained_vendor_inputs=[dict(path='packages/framework-arduinoespressif32/tools/sdk/esp32/lib/libc.a', member='known.o')],
                    build_archives=['libFrameworkArduino.a'])

    def row(self, path=None, member='known.o', archive='libc.a'):
        return dict(path=path or self.review()['retained_vendor_inputs'][0]['path'], member=member, archive=archive)

    def test_reviewed_vendor_member_is_bound_to_exact_archive_path(self):
        self.assertEqual(len(retained_inventory([self.row()], self.review())), 1)
        with self.assertRaisesRegex(RelinkError, 'unreviewed_retained_vendor_input'):
            retained_inventory([self.row(member='new.o')], self.review())
        with self.assertRaisesRegex(RelinkError, 'unqualified_retained_input'):
            retained_inventory([self.row(path='packages/framework-arduinoespressif32/tools/sdk/esp32s3/lib/libc.a')], self.review())

    def test_host_only_or_unknown_library_is_never_admitted(self):
        for library in ['libUnity.a', 'libUnknown.a']:
            with self.subTest(library=library), self.assertRaisesRegex(RelinkError, 'unreviewed_linked_library'):
                retained_inventory([self.row(), self.row(path='.pio/build/e32v2/lib123/' + library,
                                                       archive=library)], self.review())

    def test_no_vendor_inputs_or_unqualified_paths_are_denied(self):
        with self.assertRaisesRegex(RelinkError, 'missing_retained_vendor_inputs'):
            retained_inventory([], self.review())
        with self.assertRaisesRegex(RelinkError, 'unqualified_retained_input'):
            retained_inventory([self.row(path='unqualified-origin/libc.a')], self.review())

    def test_relink_tampered_object_is_denied_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'application.o').write_bytes(b'changed')
            manifest = dict(schema=1, object_files=[dict(path='application.o', sha256=hashlib.sha256(b'original').hexdigest())], core_files=[])
            (root / 'RELINK-MANIFEST.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(RelinkError, 'relink_input_changed'):
                relink(root, root, root / 'output.elf')

    def test_relink_external_object_path_is_denied_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = dict(schema=1, object_files=[dict(path='../outside.o', sha256='0' * 64)], core_files=[])
            (root / 'RELINK-MANIFEST.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(RelinkError, 'unsafe_relink_path'):
                relink(root, root, root / 'output.elf')

    def test_relink_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'RELINK-MANIFEST.json').write_text(json.dumps(dict(schema=1, object_files=[], core_files=[])))
            (root / 'existing.elf').write_bytes(b'preserve')
            with self.assertRaisesRegex(RelinkError, 'output_already_exists'):
                relink(root, root, root / 'existing.elf')
            self.assertEqual((root / 'existing.elf').read_bytes(), b'preserve')


if __name__ == '__main__':
    unittest.main()
