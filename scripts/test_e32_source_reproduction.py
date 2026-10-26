"""Use actual GNU ar output to exercise independent object identity parsing."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from e32_relink import RelinkError
from e32_verify_reproduction import ar_members, declared_sdk_source


class ReproductionChecks(unittest.TestCase):
    def archive(self, directory, members):
        directory = Path(directory)
        files = []
        for name, data in members:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files.append(str(path))
        output = directory / 'objects.a'
        subprocess.run(['ar', 'qc', str(output), *files], check=True, capture_output=True)
        return output

    def test_duplicate_member_names_keep_both_actual_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = b'\x7fELFfirst object', b'\x7fELFsecond object'
            archive = self.archive(directory, [('one/same.o', first), ('two/same.o', second)])
            self.assertEqual(ar_members(archive)['same.o'], [first, second])

    def test_original_gnu_long_name_table_is_resolved(self):
        with tempfile.TemporaryDirectory() as directory:
            name = 'this_is_an_original_long_component_name.c.obj'
            data = b'\x7fELForiginal object'
            archive = self.archive(directory, [(name, data)])
            self.assertEqual(ar_members(archive), {name: [data]})

    def test_truncated_original_archive_is_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, [('input.o', b'\x7fELForiginal object bytes')])
            archive.write_bytes(archive.read_bytes()[:-4])
            with self.assertRaisesRegex(RelinkError, 'truncated_original_ar_member'):
                ar_members(archive)

    def test_nonobject_archive_member_and_invalid_header_are_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, [('input.o', b'not an ELF object')])
            with self.assertRaisesRegex(RelinkError, 'non_elf_original_ar_member'):
                ar_members(archive)
            archive.write_bytes(b'changed header')
            with self.assertRaisesRegex(RelinkError, 'invalid_original_ar_header'):
                ar_members(archive)

    def test_sdk_source_bindings_follow_original_submodule_identity(self):
        submodules = [dict(path='components/lwip/lwip', repository='espressif/esp-lwip')]
        self.assertEqual(declared_sdk_source('/builder/esp-idf/components/lwip/lwip/src/core/tcp.c',
                                             submodules, Path('.')),
                         'sources/esp-lwip/src/core/tcp.c')
        self.assertEqual(declared_sdk_source('/builder/esp-idf/components/heap/heap_caps.c', [], Path('.')),
                         'sources/esp-idf/components/heap/heap_caps.c')

    def test_unknown_builder_source_is_not_assumed_to_be_idf(self):
        self.assertIsNone(declared_sdk_source('/unknown/component.c', [], Path('.')))


if __name__ == '__main__':
    unittest.main()
