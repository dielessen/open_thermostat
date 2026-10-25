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

    def test_user_features_and_fixes_precede_downloads_and_originals_survive(self):
        row=self.row('Original technical record.')
        row['tag_name']='v0.1.0-e32v2-alpha.36'
        result=release.plan([row],'owner/project')[0]
        self.assertLess(result['body'].index('## Nieuw'), result['body'].index('## Welke download'))
        self.assertIn('## Opgelost',result['body']);self.assertIn('## English',result['body'])
        self.assertEqual(release.original_notes(result['body']),row['body'])
        self.assertEqual(release.plan([{**row,**{k:result[k] for k in ('name','body')}}], 'owner/project'),[])

    def test_valid_reader_notes_are_not_silently_dropped_by_legacy_teaser_limit(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            root=Path(tmp);doc=root/'docs/modern-thermostat/RELEASE-NOTES.md'
            doc.parent.mkdir(parents=True)
            doc.write_text('# E32 V2 alpha36\n'+release.USER_NOTES+'\n## Nieuw\n'+
                'Visible '*420+'\n## Opgelost\nFix\n## Bijwerken en gebruik\nUpdate\n## English\nNew.\n')
            rendered=release.user_summary('v0.1.0-e32v2-alpha.36','owner/project',root)
            self.assertIn('Visible '*420,rendered)
            self.assertIn('## English',rendered)

    def test_production_publication_requires_reader_sections(self):
        notes='# E32 V2 alpha36\n\nOnly technical details.'
        with self.assertRaisesRegex(ValueError,'need_user'):
            release.publication_notes(notes,'owner/project','v0.1.0-e32v2-alpha.36',require_user_notes=True)
        self.assertEqual(release.user_summary('v0.1.0-e32v2-alpha.999','owner/project'),'')

    def test_publication_utf8_byte_bound_and_invalid_identity(self):
        for repo,tag in [('owner/project','bad'),('../project','ha-v0.4.0.dev29')]:
            with self.assertRaises(ValueError):
                release.publication_notes('# HA 0.4.0.dev29\n\nFix',repo,tag)
        with self.assertRaisesRegex(ValueError,'too_large'):
            release.publication_notes('# HA 0.4.0.dev29\n\n'+'温'*2500,'owner/project','ha-v0.4.0.dev29')




class BetaReleaseNotesTests(unittest.TestCase):
    def test_alpha_beta_rc_stable_sort_and_labels(self):
        tags=['v0.1.0-e32v2-alpha.99','v0.1.0-e32v2-beta.1',
              'v0.1.0-e32v2-rc.1','v0.1.0-e32v2']
        versions=[release.classify(tag)[1] for tag in tags]
        self.assertEqual(sorted(versions),versions)
        self.assertEqual(release.label('firmware',versions[1])[1],'beta.1')
        self.assertEqual(release.firmware_heading(versions[1]),'# E32 V2 beta1')
        self.assertEqual(release.firmware_heading(versions[3]),'# E32 V2 0.1.0')
        for tag in ['v0.1.0-e32v2-beta.01','v0.1.0-e32v2-beta.4294967296']:
            self.assertIsNone(release.classify(tag)[0])

    def test_ha_pep440_stages_sort_and_preserve_download_identity(self):
        tags=['ha-v0.4.0.dev48','ha-v0.4.0a1','ha-v0.4.0b1',
              'ha-v0.4.0rc1','ha-v0.4.0']
        versions=[release.classify(tag)[1] for tag in tags]
        self.assertEqual(sorted(versions),versions)
        for tag,version in zip(tags,versions):
            expected=tag.removeprefix('ha-v')
            self.assertEqual(release.label('ha',version),('Home Assistant',expected))
            notes='# HA '+expected+'\n'+release.USER_NOTES+'\n## Nieuw\nFeatures\n## Opgelost\nFixes\n## Bijwerken en gebruik\nUsage\n## English\nSummary'
            rendered=release.publication_notes(notes,'owner/project',tag,True)
            self.assertIn('/blob/'+tag+'/',rendered)
        for tag in ['ha-v0.4.0b01','ha-v00.4.0b1','ha-v0.4.0b4294967296',
                    'ha-v0.4.0.beta1','ha-v0.4.0b','ha-v0.4.0.dev1rc1']:
            self.assertIsNone(release.classify(tag)[0],tag)

    def test_ha_beta_overview_uses_beta_asset_and_archives_dev(self):
        rows=[]
        for index,version in enumerate(('0.4.0.dev48','0.4.0b1'),1):
            rows.append(dict(id=index,tag_name='ha-v'+version,draft=False,
                name='old',body='Original '+version,assets=[dict(
                    name='OpenThermostat-HA-'+version+'.zip',
                    browser_download_url='https://example.test/'+version+'.zip')]))
        changes=release.plan(rows,'owner/project')
        self.assertIn('Archief',changes[0]['name'])
        self.assertIn('Actueel',changes[1]['name'])
        self.assertIn('OpenThermostat-HA-0.4.0b1.zip',changes[1]['body'])
        self.assertEqual(release.original_notes(changes[0]['body']),'Original 0.4.0.dev48')
        updated=[{**row,**{k:change[k] for k in ('name','body')}} for row,change in zip(rows,changes)]
        self.assertEqual(release.plan(updated,'owner/project'),[])

    def test_beta_publication_uses_same_required_reader_sections(self):
        notes='# E32 V2 beta1\n'+release.USER_NOTES+'\n## Nieuw\nFeatures\n## Opgelost\nFixes\n## Bijwerken en gebruik\nUsage\n## English\nSummary'
        self.assertIn('Features',release.publication_notes(notes,'owner/project',
                      'v0.1.0-e32v2-beta.1',require_user_notes=True))
        with self.assertRaisesRegex(ValueError,'version_mismatch'):
            release.publication_notes(notes,'owner/project','v0.1.0-e32v2-alpha.1',True)


class HistoricalNotesTests(unittest.TestCase):
    def test_all_curated_records_have_sections_and_bound_original(self):
        from pathlib import Path
        records=json.loads((Path(release.__file__).resolve().parents[1]/
            'docs/modern-thermostat/USER-RELEASE-NOTES.json').read_text())['releases']
        self.assertEqual(len(records),63)
        for tag,entry in records.items():
            self.assertIsNotNone(release.classify(tag)[0])
            self.assertEqual(len(entry['original_notes_sha256']),64)
            for header in ('## Nieuw','## Opgelost','## Bijwerken en gebruik','## English'):
                self.assertIn(header,entry['summary'])
            with self.assertRaisesRegex(ValueError,'original_notes_changed'):
                release.archive_summary(tag,'changed original')

    def test_known_defects_and_source_package_remain_explicit(self):
        from pathlib import Path
        records=json.loads((Path(release.__file__).resolve().parents[1]/
            'docs/modern-thermostat/USER-RELEASE-NOTES.json').read_text())['releases']
        self.assertIn('Bekend probleem',records['ha-v0.4.0.dev18']['summary'])
        self.assertIn('niet in deze oorspronkelijke download',records['v0.1.0-e32v2-alpha.1']['summary'])
        self.assertIn('geen firmwarebestand',records['sources-e32v2-20261023.1']['summary'])


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
        (self.root / 'docs/modern-thermostat/RELEASE-NOTES.md').write_text('# E32 V2 alpha29\n<!-- user-release-notes:v1 -->\n## Nieuw\nCurrent.\n## Opgelost\nFix.\n## Bijwerken en gebruik\nKeep settings.\n## English\nFixes.\n# E32 V2 alpha28\nHistory.')
        (self.root / 'docs/modern-thermostat/HA-RELEASE-NOTES.md').write_text('# HA 0.4.0.dev38\n<!-- user-release-notes:v1 -->\n## Nieuw\nCurrent.\n## Opgelost\nFix.\n## Bijwerken en gebruik\nKeep settings.\n## English\nFixes.\n# HA 0.4.0.dev37\nHistory.')

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
