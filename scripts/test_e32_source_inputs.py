"""Source/notice loss, payload substitution, ZIP ambiguity and path denial."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import warnings
import zipfile

from e32_source_inputs import SourceInputError, verify


class SourceInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.archive = Path(self.tmp.name) / 'inputs.zip'
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
            data = b'/* original copyright */\nint source(void) {return 1;}\n'
            member = tarfile.TarInfo('vendor/source.c'); member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
        self.source_sha = hashlib.sha256(data).hexdigest()
        self.files = {'sources/vendor.tar.gz': buffer.getvalue(), 'notices/LICENSE': b'Original notice\n'}
        self.policy = dict(schema=1, environment='e32v2',
            payloads={n: hashlib.sha256(b).hexdigest() for n,b in self.files.items()},
            archives=[dict(path='sources/vendor.tar.gz', required_sources={'vendor/source.c': self.source_sha})])

    def write(self, *, omit=None, extra=None, duplicate=False):
        with zipfile.ZipFile(self.archive, 'w') as out:
            for name, content in self.files.items():
                if name != omit: out.writestr(name, content)
            out.writestr('CORRESPONDENCE.json', json.dumps(self.policy))
            if extra: out.writestr(*extra)
            if duplicate:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', UserWarning)
                    out.writestr('notices/LICENSE', b'Original notice\n')

    def test_complete_original_source_and_notice(self):
        self.write(); result = verify(self.policy, self.archive)
        self.assertEqual(result['required_source_files'], 1)
        self.assertFalse(result['firmware_release_approved'])

    def test_missing_original_notice_is_denied(self):
        self.write(omit='notices/LICENSE')
        with self.assertRaisesRegex(SourceInputError, 'unexpected_or_missing'): verify(self.policy,self.archive)

    def test_unlisted_live_storage_is_denied(self):
        self.write(extra=('.storage/auth', b'private'))
        with self.assertRaisesRegex(SourceInputError, 'unexpected_or_missing'): verify(self.policy,self.archive)

    def test_traversal_and_duplicate_entries_are_denied(self):
        self.write(extra=('../escape', b'bad'))
        with self.assertRaisesRegex(SourceInputError, 'unsafe_source_path'): verify(self.policy,self.archive)
        self.write(duplicate=True)
        with self.assertRaisesRegex(SourceInputError, 'duplicate_source_payload'): verify(self.policy,self.archive)

    def test_replaced_payload_is_denied(self):
        self.files['notices/LICENSE'] = b'changed'
        self.write()
        with self.assertRaisesRegex(SourceInputError, 'source_payload_hash_conflict'): verify(self.policy,self.archive)

    def test_matching_tar_hash_cannot_hide_wrong_corresponding_source(self):
        self.policy['archives'][0]['required_sources']['vendor/source.c'] = '0' * 64
        self.write()
        with self.assertRaisesRegex(SourceInputError, 'corresponding_source_hash_conflict'): verify(self.policy,self.archive)

    def test_missing_corresponding_source_and_other_board_are_denied(self):
        self.policy['archives'][0]['required_sources'] = {'vendor/absent.c':self.source_sha}
        self.write()
        with self.assertRaisesRegex(SourceInputError, 'required_corresponding_source_missing'): verify(self.policy,self.archive)
        self.policy['environment'] = 'esp32s3'
        with self.assertRaisesRegex(SourceInputError, 'unsupported_source_input_scope'): verify(self.policy,self.archive)

    def linked_source(self, target, *, hardlink=False):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
            data = b'/* original copyright */\nint source(void) {return 1;}\n'
            member = tarfile.TarInfo('vendor/source.c'); member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
            link = tarfile.TarInfo('vendor/alias.c'); link.type = tarfile.LNKTYPE if hardlink else tarfile.SYMTYPE
            link.linkname = target; tar.addfile(link)
        self.files['sources/vendor.tar.gz'] = buffer.getvalue()
        self.policy['payloads']['sources/vendor.tar.gz'] = hashlib.sha256(buffer.getvalue()).hexdigest()
        self.policy['archives'][0]['required_sources'] = {'vendor/alias.c': self.source_sha}
        self.write()

    def test_original_internal_source_symlink_and_hardlink_are_hashed_without_extraction(self):
        self.linked_source('source.c'); self.assertEqual(verify(self.policy,self.archive)['required_source_files'],1)
        self.linked_source('vendor/source.c',hardlink=True)
        self.assertEqual(verify(self.policy,self.archive)['required_source_files'],1)

    def test_escaping_and_cyclic_required_source_links_are_denied(self):
        for target in ('../../outside', '/etc/passwd'):
            self.linked_source(target)
            with self.assertRaisesRegex(SourceInputError,'unsafe_source'): verify(self.policy,self.archive)
        self.linked_source('alias.c')
        with self.assertRaisesRegex(SourceInputError,'cyclic_or_deep_source_link'): verify(self.policy,self.archive)


if __name__ == '__main__':
    unittest.main()
