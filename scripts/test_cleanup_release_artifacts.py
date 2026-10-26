"""Local cleanup must preserve source, backups, relink inputs and exact archive bytes."""
import hashlib
import os
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

import cleanup_release_artifacts as cleanup


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);(self.root/'out').mkdir()

    def write(self,name,data=b'generated'):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        return path

    def test_preview_keeps_files_unchanged_and_only_selects_generated_directories(self):
        cache=self.write('out/run/node_modules/package/index.js')
        source=self.write('out/source-copy/src/main.cpp')
        log=self.write('out/run/native.log')
        report=cleanup.plan(self.root)
        self.assertEqual(report['generated_caches'],[{'path':'out/run/node_modules'}])
        self.assertTrue(cache.exists());self.assertTrue(source.exists());self.assertTrue(log.exists())
        cleanup.apply(report)
        self.assertFalse(cache.exists());self.assertTrue(source.exists());self.assertTrue(log.exists())

    def test_relink_kits_backups_and_nested_git_repositories_are_preserved(self):
        for marker in ('RELINK-MANIFEST.json','SHA256SUMS.txt','backup-manifest.json'):
            base='out/'+marker.replace('.','_')
            self.write(base+'/'+marker)
            self.write(base+'/node_modules/retained.js')
        self.write('out/user/node_modules/custom/.git/HEAD')
        self.write('out/user/node_modules/custom/source.cpp')
        self.assertEqual(cleanup.plan(self.root)['generated_caches'],[])

    def test_identical_archives_share_read_only_storage_and_different_bytes_remain(self):
        first=self.write('out/one/archive.zip',b'A'*1_000_000)
        second=self.write('out/two/archive.zip',b'A'*1_000_000)
        other=self.write('out/three/archive.zip',b'B'*1_000_000)
        original=cleanup.filehash(first)
        result=cleanup.apply(cleanup.plan(self.root))
        self.assertEqual(result['duplicate_archives_linked'],1)
        self.assertEqual(first.stat().st_ino,second.stat().st_ino)
        self.assertNotEqual(first.stat().st_ino,other.stat().st_ino)
        self.assertEqual(cleanup.filehash(first),original)
        self.assertEqual(first.stat().st_mode&0o222,0)
        self.assertEqual(cleanup.plan(self.root)['identical_archive_groups'],[])
        fresh=self.write('out/new-release/archive.zip',b'A'*1_000_000)
        again=cleanup.apply(cleanup.plan(self.root))
        self.assertEqual(again['duplicate_archives_linked'],1)
        self.assertEqual(first.stat().st_ino,fresh.stat().st_ino)

    def test_old_published_archive_needs_exact_digest_and_latest_versions_survive(self):
        releases=[];paths=[]
        for sequence in range(1,6):
            name=f'open-thermostat-e32v2-v0.1.0-e32v2-beta.{sequence}.zip'
            data=bytes([sequence])*1_000_000
            paths.append(self.write('out/downloads/'+name,data))
            releases.append({'tag_name':f'v0.1.0-e32v2-beta.{sequence}','draft':False,'assets':[
                {'name':name,'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest(),
                 'browser_download_url':'https://github.com/owner/project/releases/download/'+name}]})
        # A different local file is never discarded just because its name matches.
        paths[1].write_bytes(b'unknown bytes'*100_000)
        report=cleanup.plan(self.root,releases,keep=3)
        self.assertEqual(len(report['published_archive_removals']),1)
        cleanup.apply(report)
        self.assertFalse(paths[0].exists())
        self.assertTrue(all(path.exists() for path in paths[1:]))

    def test_archive_modified_after_preview_aborts_before_deletion(self):
        first=self.write('out/one/archive.zip',b'A'*1_000_000)
        self.write('out/two/archive.zip',b'A'*1_000_000)
        report=cleanup.plan(self.root)
        first.write_bytes(b'C'*1_000_000)
        with self.assertRaisesRegex(RuntimeError,'changed_since_preview'):cleanup.apply(report)
        self.assertEqual(first.stat().st_nlink,1)

    def test_git_tracked_cache_named_directory_is_source_and_never_removed(self):
        source=self.write('out/tracked/node_modules/local.js')
        subprocess.run(['git','init','-q',str(self.root)],check=True)
        subprocess.run(['git','-C',str(self.root),'add',str(source.relative_to(self.root))],check=True)
        self.assertEqual(cleanup.plan(self.root)['generated_caches'],[])

    def test_accepted_and_pending_release_tags_are_retained_beyond_latest_limit(self):
        path=self.write('docs/modern-thermostat/E32-UPDATE-GATE.json',json.dumps({
            'accepted':{'tag':'v0.1.0-e32v2-beta.1'},'pending_tag':'v0.1.0-e32v2-beta.2'}).encode())
        rows=[{'tag_name':f'v0.1.0-e32v2-beta.{n}','draft':False,'assets':[]} for n in range(1,6)]
        report=cleanup.plan(self.root,rows,keep=1)
        self.assertEqual(report['retained_release_tags'],['v0.1.0-e32v2-beta.1','v0.1.0-e32v2-beta.2','v0.1.0-e32v2-beta.5'])
        self.assertTrue(path.exists())

    def test_symlink_escape_is_never_followed_or_removed(self):
        outside=self.root/'outside';outside.mkdir()
        file=outside/'private.txt';file.write_text('preserve')
        (self.root/'out'/'node_modules').symlink_to(outside,target_is_directory=True)
        report=cleanup.plan(self.root)
        self.assertEqual(report['generated_caches'],[])
        with self.assertRaisesRegex(ValueError,'outside_out'):
            cleanup.apply({'root':str(self.root),'generated_caches':[{'path':'outside'}],
                           'published_archive_removals':[],'identical_archive_groups':[]})
        self.assertEqual(file.read_text(),'preserve')

    def test_report_cannot_overwrite_source_backups_or_unrelated_evidence(self):
        source=self.write('README.md',b'Source documentation')
        backup=self.write('out/backups/backup-manifest.json',b'{"important":true}')
        for path in (source,backup):
            with self.assertRaises(ValueError):cleanup.report_destination(self.root,path)
        proof=self.write('out/evidence.json',b'{"status":"PASS"}')
        with self.assertRaisesRegex(ValueError,'unrelated_report'):cleanup.report_destination(self.root,proof)
        self.assertEqual(source.read_bytes(),b'Source documentation')


if __name__=='__main__':unittest.main()
