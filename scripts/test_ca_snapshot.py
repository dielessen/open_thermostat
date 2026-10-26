"""Offline source/notice/trust and generated-binary failure checks."""
from pathlib import Path
import gzip
import json
import re
import shutil
import tempfile
import unittest

import verify_ca_snapshot as ca

ROOT = Path(__file__).resolve().parents[1]


class Snapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = json.loads((ROOT/'docs/third-party/ca-provenance.json').read_text())
        files = [self.manifest[key]['path'] for key in ('snapshot', 'binary', 'generator', 'converter')]
        files += [n['path'] for n in self.manifest['notices']]
        files += [self.manifest['source']['compressed_path']]
        for name in files:
            target = self.root/name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT/name, target)
        self.save()

    def save(self):
        path = self.root/'docs/third-party/ca-provenance.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest))

    def test_real_snapshot_source_and_binary(self):
        report = ca.verify(self.root)
        self.assertEqual(report['certificates'], 121)
        self.assertEqual(report['server_auth_source_matches'], 121)
        self.assertEqual(report['status'], 'PASS')
        self.assertFalse(report['whole_release_approval'])

    def test_notice_tampering_rejected(self):
        (self.root/self.manifest['notices'][0]['path']).write_bytes(b'replacement notice')
        with self.assertRaisesRegex(ca.CAError, 'ca_file_identity_conflict'):
            ca.verify(self.root)

    def test_external_source_path_rejected(self):
        self.manifest['source']['compressed_path'] = '../elsewhere.gz'; self.save()
        with self.assertRaisesRegex(ca.CAError, 'unsafe_ca_path'):
            ca.verify(self.root)

    def test_binary_with_updated_hash_still_must_reproduce(self):
        data = b'zero or incomplete certificate bundle'
        (self.root/self.manifest['binary']['path']).write_bytes(data)
        self.manifest['binary']['sha256'] = ca.sha(data); self.save()
        with self.assertRaisesRegex(ca.CAError, 'ca_generated_binary_conflict'):
            ca.verify(self.root)

    def test_source_header_with_updated_pem_hash_still_must_match(self):
        record = self.manifest['snapshot']; path = self.root/record['path']
        data = path.read_bytes().replace(self.manifest['source']['sha256'].encode(), b'0'*64)
        path.write_bytes(data); record['sha256'] = ca.sha(data); self.save()
        with self.assertRaisesRegex(ca.CAError, 'ca_snapshot_source_header_conflict'):
            ca.verify(self.root)

    def test_matching_cert_bytes_with_untrusted_server_auth_rejected(self):
        original = self.manifest['source']; path = self.root/original['compressed_path']
        source = gzip.decompress(path.read_bytes())
        # Replace the server-auth trust of an actual certificate included in the
        # PEM. Rebind all ordinary fixture hashes so semantic verification is
        # exercised, rather than merely an earlier digest mismatch.
        pem_path = self.root/self.manifest['snapshot']['path']; pem = pem_path.read_bytes()
        first = re.search(rb'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----', pem, re.S)
        import base64
        der = base64.b64decode(first[1]); label = ca.source_certificates(source)[der]['label']
        objects = re.split(rb'(?m)^CKA_CLASS CK_OBJECT_CLASS ', source)
        for i, obj in enumerate(objects):
            if obj.startswith(b'CKO_NSS_TRUST\n') and ('CKA_LABEL UTF8 "'+label+'"').encode() in obj:
                objects[i] = obj.replace(b'CKA_TRUST_SERVER_AUTH CK_TRUST CKT_NSS_TRUSTED_DELEGATOR',
                                         b'CKA_TRUST_SERVER_AUTH CK_TRUST CKT_NSS_NOT_TRUSTED', 1)
                break
        else:
            self.fail('actual certificate trust fixture missing')
        source = b'CKA_CLASS CK_OBJECT_CLASS '.join(objects)
        pem = pem.replace(original['sha256'].encode(), ca.sha(source).encode())
        pem_path.write_bytes(pem); self.manifest['snapshot']['sha256'] = ca.sha(pem)
        original.update(sha256=ca.sha(source), git_blob=ca.blob(source))
        compressed = gzip.compress(source, mtime=0); path.write_bytes(compressed)
        original['compressed_sha256'] = ca.sha(compressed); self.save()
        with self.assertRaisesRegex(ca.CAError, 'ca_certificate_not_in_original_server_auth_source'):
            ca.verify(self.root)


if __name__ == '__main__':
    unittest.main()
