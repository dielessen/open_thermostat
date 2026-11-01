"""The display-code tables in the boiler profiles are validated before anything is generated."""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_display_codes as gen  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OWNER = 'nefit-ecomline-classic-hrc-22h'


class Profiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / 'profiles').mkdir()
        for path in (ROOT / 'docs/modern-thermostat/boiler-profiles').glob('*.json'):
            shutil.copy(path, self.tmp / 'profiles' / path.name)
        self.saved = (gen.PROFILES, gen.GENERIC)
        gen.PROFILES, gen.GENERIC = self.tmp / 'profiles', self.tmp / 'profiles/ems-display-codes.json'
        self.addCleanup(self.restore)
        self.generic = json.loads(gen.GENERIC.read_text(encoding='utf-8'))
        self.owner = json.loads((gen.PROFILES / f'{OWNER}.json').read_text(encoding='utf-8'))

    def restore(self):
        gen.PROFILES, gen.GENERIC = self.saved

    def write(self, generic=None, owner=None):
        gen.GENERIC.write_text(json.dumps(generic or self.generic), encoding='utf-8')
        (gen.PROFILES / f'{OWNER}.json').write_text(json.dumps(owner or self.owner), encoding='utf-8')

    def rejects(self, message, generic=None, owner=None):
        self.write(generic, owner)
        with self.assertRaises(ValueError) as caught:
            gen.load()
        self.assertIn(message, str(caught.exception))

    def test_the_shipped_profiles_load(self):
        data = gen.load()
        self.assertEqual(data['models'], {'nefit-ecomline-classic': OWNER, OWNER: OWNER})
        self.assertEqual(data['tables']['ems-generic'][('0H', 203)][0], 'normal')
        self.assertEqual(data['tables'][OWNER][('0C', None)][2][0], 'Waiting for the 3-way valve to switch')
        # Every reviewed document is named with its number, edition and the hash of the PDF read.
        for source in data['sources'].values():
            self.assertTrue(source['document'] and source['edition'] and len(source['sha256']) == 64)

    def test_each_row_needs_three_languages_a_severity_and_known_advice(self):
        for change, message in ((lambda r: r['text'].pop('pl'), 'needs exactly'),
                                (lambda r: r.update(severity='bad'), 'severity'),
                                (lambda r: r.update(severity='unknown'), 'severity'),
                                (lambda r: r.update(advice='call_mum'), 'advice'),
                                (lambda r: r['text'].update(en=''), 'one plain line'),
                                (lambda r: r['text'].update(nl='two\nlines'), 'one plain line'),
                                (lambda r: r.update(code='0HH'), 'display code'),
                                (lambda r: r.update(cause=1234), 'cause number'),
                                (lambda r: r.update(extra=1), 'keys')):
            generic = copy.deepcopy(self.generic)
            change(generic['codes'][0])
            self.rejects(message, generic=generic)

    def test_generic_rows_cite_a_reviewed_document_or_hold_for_all(self):
        generic = copy.deepcopy(self.generic)
        generic['codes'][0]['sources'] = [{'source': 'ems-esp-wiki', 'pages': [1]}]
        self.rejects('source', generic=generic)
        generic = copy.deepcopy(self.generic)
        only = next(row for row in generic['codes'] if 'cause' not in row)
        only['sources'] = [{'source': 'nefit-proline-6720646227', 'pages': [31]}]
        self.rejects('all reviewed documents', generic=generic)
        generic = copy.deepcopy(self.generic)
        generic['sources']['nefit-proline-6720646227']['sha256'] = ''
        self.rejects('sha256', generic=generic)

    def test_no_duplicate_codes_and_no_cause_numbers_in_a_classic_family(self):
        generic = copy.deepcopy(self.generic)
        generic['codes'].append(copy.deepcopy(generic['codes'][0]))
        self.rejects('duplicate', generic=generic)
        owner = copy.deepcopy(self.owner)
        owner['display_codes']['codes'][0]['cause'] = 203
        self.rejects('no cause numbers', owner=owner)
        owner = copy.deepcopy(self.owner)
        del owner['display_codes']['codes'][0]['pages']
        self.rejects('pages', owner=owner)

    def test_a_profile_covers_real_model_selections_only_once(self):
        owner = copy.deepcopy(self.owner)
        owner['display_codes']['catalog_ids'].append('nefit-hrc-99')
        self.rejects('not a boiler-model selection', owner=owner)
        owner = copy.deepcopy(self.owner)
        owner['display_codes']['fallback'] = 'nefit-proline'
        self.rejects('fallback', owner=owner)
        owner = copy.deepcopy(self.owner)
        owner['display_codes']['source'] = 'forum-post'
        self.rejects('source', owner=owner)

    def test_every_advice_text_is_used(self):
        generic = copy.deepcopy(self.generic)
        generic['advice']['spare'] = {'en': 'x', 'nl': 'x', 'pl': 'x'}
        self.rejects('unused advice', generic=generic)


if __name__ == '__main__':
    unittest.main()
