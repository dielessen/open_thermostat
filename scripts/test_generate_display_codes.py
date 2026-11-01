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
# Each family table (boiler profile), its manual in the registry and the boiler-model selections it covers.
FAMILIES = {
    OWNER: ('nefit-ecomline-classic-705428a', ['nefit-ecomline-classic', OWNER]),
    'nefit-ecomline-excellent': ('nefit-ecomline-excellent-705427a', ['nefit-ecomline-excellent']),
    'nefit-proline-hrc': ('nefit-proline-6720646227', ['nefit-proline']),
    'nefit-trendline-ii': ('nefit-trendline-ii-6720882261', ['nefit-trendline-ii']),
    'nefit-topline-aquapower': ('nefit-topline-6720615811', ['nefit-topline']),
    'nefit-smartline-basic': ('nefit-smartline-basic-71652200', ['nefit-smartline']),
    'buderus-logamax-plus-gb172': ('buderus-gb172-6720619596', ['buderus-logamax-plus-gb172']),
    'buderus-logamax-plus-gb162': ('buderus-gb162-6720614965', ['buderus-gb162']),
    'bosch-condens-7000i-w': ('bosch-gc7000iw-6720882461', ['bosch-condens-7000i-w']),
    'bosch-cerapur-zsb-5c': ('bosch-cerapur-6720889855', ['bosch-cerapur-zsb-zwb-5c', 'junkers-cerapur']),
    'worcester-bosch-greenstar-4000': ('worcester-greenstar-4000-6720891161', ['worcester-bosch-greenstar-4000']),
}


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
        self.assertEqual(data['models'], {model: name for name, (_, models) in FAMILIES.items() for model in models})
        self.assertEqual(set(data['tables']), {'ems-generic', *FAMILIES})
        catalog = {m['id']: m for m in json.loads(gen.CATALOG.read_text())['models']}
        for name, (source, models) in FAMILIES.items():
            profile = json.loads((gen.PROFILES / f'{name}.json').read_text(encoding='utf-8'))
            self.assertEqual(profile['display_codes']['source'], source, name)
            self.assertIsNone(data['fallback'][name], name)  # authoritative: never the generic table
            self.assertGreaterEqual(len(data['tables'][name]), 40, name)
            self.assertTrue(all(catalog[m]['selectable'] for m in models), name)
            # Every row of a family table names its page in that family's manual.
            self.assertTrue(all(row['pages'] for row in profile['display_codes']['codes']), name)
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
                                (lambda r: r.update(cause=12345), 'cause number'),
                                (lambda r: r.update(cause=99), 'cause number'),
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

    def family(self, name):
        return gen.PROFILES / f'{name}.json', json.loads((gen.PROFILES / f'{name}.json').read_text(encoding='utf-8'))

    def test_a_cause_number_without_a_display_code_only_in_a_family_table(self):
        # The generic table always needs the display code.
        generic = copy.deepcopy(self.generic)
        del next(row for row in generic['codes'] if 'cause' in row)['code']
        self.rejects('keys', generic=generic)
        # A family table may list a manual's number without a code (Bosch "-" operating messages,
        # the number-only Greenstar 4000), never a row with neither.
        self.write()
        data = gen.load()
        self.assertEqual(data['tables']['bosch-condens-7000i-w'][(None, 203)][2][0], 'Standby: no heat demand')
        self.assertEqual(data['tables']['bosch-condens-7000i-w'][('EA', 227)][0], 'fault')
        self.assertEqual(data['tables']['worcester-bosch-greenstar-4000'][(None, 2927)][0], 'blocking')
        path, profile = self.family('bosch-condens-7000i-w')
        del next(row for row in profile['display_codes']['codes'] if 'code' not in row)['cause']
        path.write_text(json.dumps(profile), encoding='utf-8')
        self.rejects('keys')

    def test_a_classic_type_family_has_no_cause_numbers(self):
        path, profile = self.family('nefit-ecomline-excellent')
        profile['display_codes']['codes'].append(
            {'cause': 203, 'severity': 'normal', 'text': {'en': 'x', 'nl': 'x', 'pl': 'x'}, 'pages': '4-2'})
        path.write_text(json.dumps(profile), encoding='utf-8')
        self.rejects('no cause numbers')

    def test_a_selection_belongs_to_one_family_table(self):
        path, profile = self.family('nefit-ecomline-excellent')
        profile['display_codes']['catalog_ids'].append('nefit-proline')
        path.write_text(json.dumps(profile), encoding='utf-8')
        self.rejects('in two display-code profiles')

    def test_a_selection_catalogued_for_a_manual_uses_that_manuals_table(self):
        catalog = json.loads(gen.CATALOG.read_text())
        entry = next(m for m in catalog['models'] if m['id'] == 'bosch-condens-7000i-w')
        self.assertEqual(entry['source'], 'manufacturer-document')
        entry['source_document'] = 'bosch-cerapur-6720889855'
        saved = gen.CATALOG
        gen.CATALOG = self.tmp / 'catalog-v1.json'
        self.addCleanup(setattr, gen, 'CATALOG', saved)
        gen.CATALOG.write_text(json.dumps(catalog))
        self.rejects('not covered by its table')

    def test_no_generic_code_only_row_contradicts_a_family(self):
        # On the Bosch letter-code families EA is a flame fault and 0Y an overheat: no code-only meaning.
        generic = gen.load()['tables']['ems-generic']
        self.assertNotIn(('EA', None), generic)
        self.assertNotIn(('0Y', None), generic)

    def test_every_advice_text_is_used(self):
        generic = copy.deepcopy(self.generic)
        generic['advice']['spare'] = {'en': 'x', 'nl': 'x', 'pl': 'x'}
        self.rejects('unused advice', generic=generic)


if __name__ == '__main__':
    unittest.main()
