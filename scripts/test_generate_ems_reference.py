"""Ensure lookup generation never drops upstream fields or aliases."""
import collections
import csv
import io
import json
import re
import unittest
from generate_ems_reference import ROOT,generate

class ReferenceTests(unittest.TestCase):
    def test_every_exported_entity_and_access_bit_survives(self):
        # The full reference as JSON (string keys), as ems-reference.js.gz held it before rc.4 (no longer shipped, R3-10).
        ref=json.loads(json.dumps(generate(check=True)))
        actual=[]
        for key,group in ref['groups'].items():
            for index in group['fields']:actual.append((key,*ref['entities'][index]))
        expected=[]
        for row in csv.DictReader(io.StringIO((ROOT/'public/ems/entities.csv').read_text())):
            expected.append((row['device type']+':'+str(int(row['product id'])),*[row[k].strip() for k in ('shortname','fullname','type [options...] \\| (min/max)','uom')],row['writeable']=='true'))
        self.assertEqual(collections.Counter(actual),collections.Counter(expected))
        self.assertEqual(len(actual),6042)
        self.assertEqual(len(ref['libraryFields']),1853)
        # A multi-circuit range must retain the exact same definition for each ID.
        for type_id in range(0x165,0x16d):
            self.assertEqual(ref['library'][str(type_id)],ref['library'][str(0x165)])
        self.assertEqual(ref['telegrams']['24'],'UBAMonitorFast')
        self.assertIn('2',ref['telegrams'])
        compact=json.loads((ROOT/'data/html/ems-metadata.js').read_text().removeprefix('window.OT_EMS_METADATA = ').rstrip(';\n'))
        self.assertEqual(compact['devices'],ref['devices'])
        aliases=compact['aliases']
        self.assertEqual(len(aliases),68)
        self.assertEqual(len(set(aliases.values())),68)
        for key,group in compact['groups'].items():
            self.assertTrue(key.startswith('boiler:'))
            expected=[ref['entities'][i] for i in ref['groups'][key]['fields'] if ref['entities'][i][0] in aliases.values()]
            self.assertEqual([compact['entities'][i] for i in group['fields']],expected)
        self.assertLess((ROOT/'data/html/ems-metadata.js').stat().st_size,30000)

    def test_setting_help_explains_every_writable_boiler_field_in_both_languages(self):
        generate(check=True)
        compact=json.loads((ROOT/'data/html/ems-metadata.js').read_text().removeprefix('window.OT_EMS_METADATA = ').rstrip(';\n'))
        writable={spec[0] for spec in compact['entities'] if spec[4]}
        source=(ROOT/'data/html/ems-setting-help.js').read_text(encoding='utf-8')
        help=json.loads(re.search(r'window.OT_EMS_SETTING_HELP = (.*);\n',source).group(1))
        dutch=json.loads(re.search(r'Object.entries\((\{.*\})\)\) if',source).group(1))
        self.assertEqual(set(help),writable)
        self.assertEqual(len(help),27)
        for entity,row in help.items():
            self.assertIn(row['level'],('user','installer'))
            for key in ('what','expect','risk','e32'):
                self.assertNotEqual(dutch[row[key]],row[key],(entity,key))
        # The E32's own heat request and the second burner stage are explained, never offered.
        for entity in ('selflowtemp','selburnpow','boil2hyston','boil2hystoff'):self.assertEqual(help[entity]['offer'],'never')
        self.assertLess(len(source.encode()),40000)

if __name__=='__main__':unittest.main()
