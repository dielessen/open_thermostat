"""Publication metadata stays compatible with the installed bounded updater."""
import copy
import json
import unittest
import organize_releases as release


class ReleaseNotesTests(unittest.TestCase):
    def row(self, notes):
        return dict(id=1, tag_name='v0.1.0-e32v2-alpha.23', draft=False,
                    name='old', body=notes, assets=[dict(name='firmware.bin', browser_download_url='https://example.test/firmware.bin')])

    def test_large_cumulative_notes_preserved_without_duplicate_summary(self):
        notes='# Current\n\n'+'current feature '*160+'\n\n# History\n\n'+'historical detail '*970
        row=self.row(notes)
        change=release.plan([row], 'owner/project')[0]
        self.assertLessEqual(len(change['body'].encode()), 21000)
        self.assertEqual(release.original_notes(change['body']), notes)
        self.assertNotIn('## Deze versie', change['body'])
        updated={**row,'name':change['name'],'body':change['body']}
        self.assertEqual(release.plan([updated], 'owner/project'), [])
        self.assertEqual(set(change), {'id','tag','name','body'})

    def test_unrepresentable_original_notes_fail_without_discarding_history(self):
        row=self.row('# Current\n\n'+'history '*4000)
        before=copy.deepcopy(row)
        with self.assertRaisesRegex(ValueError,'release_notes_exceed'):
            release.plan([row], 'owner/project')
        self.assertEqual(row,before)

    def test_future_publication_keeps_current_section_and_immutable_history_link(self):
        notes='# E32 V2 alpha23 — changes\n\nCurrent fixes.\n\n# Older version\n\n'+'old '*10000
        rendered=release.publication_notes(notes,'owner/project','v0.1.0-e32v2-alpha.23')
        self.assertIn('Current fixes.',rendered)
        self.assertNotIn('old old',rendered)
        self.assertIn('/blob/v0.1.0-e32v2-alpha.23/docs/modern-thermostat/RELEASE-NOTES.md',rendered)
        self.assertLessEqual(len(rendered.encode()),6000)

    def test_future_notes_then_catalog_fit_full_json_response(self):
        notes='# E32 V2 alpha23 — changes\n\n'+'feature '*300+'\n\n# History\n\n'+'old '*10000
        published=release.publication_notes(notes,'owner/project','v0.1.0-e32v2-alpha.23')
        change=release.plan([self.row(published)],'owner/project')[0]
        envelope=dict(body=change['body'],assets=[dict(metadata='x'*11000)])
        self.assertLess(len(json.dumps(envelope,ensure_ascii=False,indent=2).encode()),32768)
        self.assertEqual(release.original_notes(change['body']),published)

    def test_ha_notes_require_correct_version_and_document(self):
        notes='# HA 0.4.0.dev29 — changes\n\nOntvangst; no commands.\n'
        self.assertIn('/blob/ha-v0.4.0.dev29/docs/modern-thermostat/HA-RELEASE-NOTES.md',
                      release.publication_notes(notes,'owner/project','ha-v0.4.0.dev29'))
        with self.assertRaisesRegex(ValueError,'version'):
            release.publication_notes(notes.replace('dev29','dev27'),'owner/project','ha-v0.4.0.dev29')

    def test_publication_utf8_byte_bound_and_invalid_identity(self):
        for repo,tag in [('owner/project','bad'),('../project','ha-v0.4.0.dev29')]:
            with self.assertRaises(ValueError):
                release.publication_notes('# HA 0.4.0.dev29\n\nFix',repo,tag)
        with self.assertRaisesRegex(ValueError,'too_large'):
            release.publication_notes('# HA 0.4.0.dev29\n\n'+'温'*2500,'owner/project','ha-v0.4.0.dev29')




class PublicationPreflightTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'ha/config/custom_components/open_thermostat').mkdir(parents=True)
        (self.root / 'docs/modern-thermostat').mkdir(parents=True)
        (self.root / 'release.json').write_text(json.dumps({'version': 'v0.1.0-e32v2-alpha.29'}))
        self.ha = self.root / 'ha/config/custom_components/open_thermostat/manifest.json'
        self.ha.write_text(json.dumps({'version': '0.4.0.dev38'}))
        (self.root / 'docs/modern-thermostat/RELEASE-NOTES.md').write_text('# E32 V2 alpha29\n\nCurrent.\n\n# E32 V2 alpha28\n\nHistory.')
        (self.root / 'docs/modern-thermostat/HA-RELEASE-NOTES.md').write_text('# HA 0.4.0.dev38\n\nCurrent.\n\n# HA 0.4.0.dev37\n\nHistory.')

    def test_current_publication_preflight_preserves_history_and_checks_both_versions(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(release.verify_publication_notes(self.root),
                         {'firmware': 'v0.1.0-e32v2-alpha.29', 'ha': 'ha-v0.4.0.dev38'})
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_firmware_version_bump_without_notes_is_rejected_before_build(self):
        (self.root / 'release.json').write_text(json.dumps({'version': 'v0.1.0-e32v2-alpha.30'}))
        with self.assertRaisesRegex(ValueError, 'publication_notes_version_mismatch'):
            release.verify_publication_notes(self.root)

    def test_ha_version_bump_without_notes_is_rejected_before_build(self):
        self.ha.write_text(json.dumps({'version': '0.4.0.dev39'}))
        with self.assertRaisesRegex(ValueError, 'publication_notes_version_mismatch'):
            release.verify_publication_notes(self.root)


if __name__=='__main__':unittest.main()
