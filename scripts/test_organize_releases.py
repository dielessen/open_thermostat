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
        self.assertNotIn('## This version', change['body'])
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
        self.assertLess(result['body'].index('## New'), result['body'].index('## Which download'))
        self.assertIn('## Fixed',result['body']);self.assertIn('## Limitations',result['body'])
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

    def test_english_publication_and_catalog_preserve_reader_notes(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        notes = ('# E32 V2 beta4\n' + release.ENGLISH_USER_NOTES +
                 '\n## New\nSession recovery.\n## Fixed\nIdle expiry.\n'
                 '## Updating\nE32 only.\n## Limitations\nOutputs disabled.\n')
        rendered = release.publication_notes(notes, 'owner/project', 'v0.1.0-e32v2-beta.4', True)
        self.assertIn('Full release notes and history', rendered)
        self.assertNotIn('Volledige', rendered)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'docs/modern-thermostat/RELEASE-NOTES.md'
            path.parent.mkdir(parents=True)
            path.write_text(notes)
            summary = release.user_summary('v0.1.0-e32v2-beta.4', 'owner/project', tmp)
            self.assertIn('Session recovery.', summary)
            self.assertIn('Outputs disabled.', summary)
        for heading in ('## New', '## Fixed', '## Updating', '## Limitations'):
            with self.assertRaisesRegex(ValueError, 'need_user'):
                release.publication_notes(notes.replace(heading, '### Missing'),
                                          'owner/project', 'v0.1.0-e32v2-beta.4', True)

    def test_catalog_surrounding_text_is_english_without_rewriting_originals(self):
        row = self.row('Oorspronkelijke historische notities.')
        change = release.plan([row], 'owner/project')[0]
        self.assertEqual(change['name'], 'E32 firmware · alpha.23 · Current')
        self.assertIn('## Which download do you need?', change['body'])
        self.assertIn('Full original release notes and evidence', change['body'])
        self.assertEqual(release.original_notes(change['body']), row['body'])

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
        self.assertIn('Archive',changes[0]['name'])
        self.assertIn('Current',changes[1]['name'])
        self.assertIn('OpenThermostat-HA-0.4.0b1.zip',changes[1]['body'])
        self.assertIn('| Component | Current test version | File |',changes[1]['body'])  # unchanged before 1.0
        self.assertEqual(release.original_notes(changes[0]['body']),'Original 0.4.0.dev48')
        updated=[{**row,**{k:change[k] for k in ('name','body')}} for row,change in zip(rows,changes)]
        self.assertEqual(release.plan(updated,'owner/project'),[])

    def test_beta_publication_uses_same_required_reader_sections(self):
        notes='# E32 V2 beta1\n'+release.USER_NOTES+'\n## Nieuw\nFeatures\n## Opgelost\nFixes\n## Bijwerken en gebruik\nUsage\n## English\nSummary'
        self.assertIn('Features',release.publication_notes(notes,'owner/project',
                      'v0.1.0-e32v2-beta.1',require_user_notes=True))
        with self.assertRaisesRegex(ValueError,'version_mismatch'):
            release.publication_notes(notes,'owner/project','v0.1.0-e32v2-alpha.1',True)


class StableReleaseTests(unittest.TestCase):
    def rows(self,*tags,prerelease=None):
        rows=[]
        for index,tag in enumerate(tags,1):
            channel,version=release.classify(tag)
            name='firmware.bin' if channel=='firmware' else 'OpenThermostat-HA-'+release.ha_version(version)+'.zip'
            row=dict(id=index,tag_name=tag,draft=False,name='old',body='Original '+tag,
                     assets=[dict(name=name,browser_download_url='https://example.test/'+tag+'/'+name)])
            if prerelease is not None:row['prerelease']=prerelease(tag)
            rows.append(row)
        return rows

    def test_version_one_tags_order_after_every_pre_release(self):
        tags=['v0.1.0-e32v2-beta.19','v1.0.0-e32v2-alpha.1','v1.0.0-e32v2-beta.1','v1.0.0-e32v2-rc.1',
              'v1.0.0-e32v2','v1.0.1-e32v2-beta.1','v1.0.1-e32v2']
        versions=[release.classify(tag)[1] for tag in tags]
        self.assertEqual(sorted(reversed(versions)),versions)
        self.assertEqual(release.label('firmware',release.classify('v1.0.0-e32v2')[1]),('E32 firmware','1.0.0'))
        self.assertEqual(release.firmware_heading(release.classify('v1.0.0-e32v2')[1]),'# E32 V2 1.0.0')
        ha=['ha-v0.4.0b11','ha-v1.0.0rc1','ha-v1.0.0','ha-v1.0.1b1']
        self.assertEqual(sorted(reversed([release.classify(t)[1] for t in ha])),[release.classify(t)[1] for t in ha])
        self.assertTrue(release.is_stable(*release.classify('ha-v1.0.0')))
        self.assertTrue(release.is_stable(*release.classify('v1.0.0-e32v2')))
        for tag in ['v1.0.0-e32v2-rc.1','ha-v1.0.0rc1','sources-e32v2-20261029.1']:
            self.assertFalse(release.is_stable(*release.classify(tag)),tag)
        self.assertFalse(release.is_stable(*release.classify('v1.0.0-e32v2'),{'prerelease':True}))
        for tag in ['v1.0.0','v1.0.0-e32v2-','ha-v1.0','ha-v1.0.0.0']:
            self.assertIsNone(release.classify(tag)[0],tag)
        notes='# E32 V2 1.0.0\n'+release.ENGLISH_USER_NOTES+'\n## New\nA\n## Fixed\nB\n## Updating\nC\n## Limitations\nD'
        self.assertIn('/blob/v1.0.0-e32v2/',release.publication_notes(notes,'owner/project','v1.0.0-e32v2',True))

    def test_stable_release_is_current_and_a_newer_test_version_is_labelled_pre_release(self):
        rows=self.rows('v0.1.0-e32v2-beta.19','v1.0.0-e32v2','v1.1.0-e32v2-beta.1','ha-v0.4.0b11','ha-v1.0.0',
                       prerelease=lambda tag:not release.is_stable(*release.classify(tag)))
        changes={change['tag']:change for change in release.plan(rows,'owner/project')}
        self.assertEqual(changes['v1.0.0-e32v2']['name'],'E32 firmware · 1.0.0 · Current')
        self.assertEqual(changes['v1.1.0-e32v2-beta.1']['name'],'E32 firmware · beta.1 · Pre-release')
        self.assertEqual(changes['v0.1.0-e32v2-beta.19']['name'],'Archive · E32 firmware · beta.19')
        self.assertEqual(changes['ha-v1.0.0']['name'],'Home Assistant · 1.0.0 · Current')
        self.assertEqual(changes['ha-v0.4.0b11']['name'],'Archive · Home Assistant · 0.4.0b11')
        body=changes['v1.0.0-e32v2']['body']
        self.assertIn('**Current stable release of E32 firmware.**',body)
        self.assertIn('| Component | Version | Channel | File |',body)
        self.assertIn('| E32 firmware | [1.0.0](https://github.com/owner/project/releases/tag/v1.0.0-e32v2) | Stable | '
                      '[firmware.bin](https://example.test/v1.0.0-e32v2/firmware.bin) |\n'
                      '| E32 firmware | [beta.1](https://github.com/owner/project/releases/tag/v1.1.0-e32v2-beta.1) | Pre-release | '
                      '[firmware.bin](https://example.test/v1.1.0-e32v2-beta.1/firmware.bin) |\n'
                      '| Home Assistant | [1.0.0](https://github.com/owner/project/releases/tag/ha-v1.0.0) | Stable |',body)
        self.assertIn('Use the stable release',body)
        self.assertNotIn('These are test releases',body)
        self.assertIn('**Pre-release — a test version of E32 firmware',changes['v1.1.0-e32v2-beta.1']['body'])
        updated=[{**row,'name':changes[row['tag_name']]['name'],'body':changes[row['tag_name']]['body']} for row in rows]
        self.assertEqual(release.plan(updated,'owner/project'),[])

    def test_a_component_without_a_stable_release_keeps_its_test_version_and_github_pre_release_is_not_stable(self):
        rows=self.rows('v1.0.0-e32v2','ha-v0.4.0b11','ha-v1.0.0',
                       prerelease=lambda tag:tag!='v1.0.0-e32v2')  # ha-v1.0.0 still published as a pre-release
        changes={change['tag']:change for change in release.plan(rows,'owner/project')}
        self.assertEqual(changes['ha-v1.0.0']['name'],'Home Assistant · 1.0.0 · Current')
        self.assertIn('**Current test version for Home Assistant.**',changes['ha-v1.0.0']['body'])
        self.assertIn('| Home Assistant | [1.0.0](https://github.com/owner/project/releases/tag/ha-v1.0.0) | Pre-release |',
                      changes['v1.0.0-e32v2']['body'])


class HistoricalNotesTests(unittest.TestCase):
    def test_all_curated_records_have_sections_and_bound_original(self):
        from pathlib import Path
        records=json.loads((Path(release.__file__).resolve().parents[1]/
            'docs/modern-thermostat/USER-RELEASE-NOTES.json').read_text())['releases']
        self.assertEqual(len(records),63)
        for tag,entry in records.items():
            self.assertIsNotNone(release.classify(tag)[0])
            self.assertEqual(len(entry['original_notes_sha256']),64)
            for header in (release.ENGLISH_USER_NOTES,'## New','## Fixed','## Updating','## Limitations'):
                self.assertIn(header,entry['summary'])
            with self.assertRaisesRegex(ValueError,'original_notes_changed'):
                release.archive_summary(tag,'changed original')

    def test_known_defects_and_source_package_remain_explicit(self):
        from pathlib import Path
        records=json.loads((Path(release.__file__).resolve().parents[1]/
            'docs/modern-thermostat/USER-RELEASE-NOTES.json').read_text())['releases']
        self.assertIn('Known issue',records['ha-v0.4.0.dev18']['summary'])
        self.assertIn('not in this original download',records['v0.1.0-e32v2-alpha.1']['summary'])
        self.assertIn('not a firmware file',records['sources-e32v2-20261023.1']['summary'])


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
