"""Ensure compression/lookup generation never drops upstream fields or aliases."""
import collections
import csv
import gzip
import io
import json
import re
import unittest
from generate_ems_reference import ROOT,generate

class ReferenceTests(unittest.TestCase):
    def test_every_exported_entity_and_access_bit_survives(self):
        generate(check=True)
        source=gzip.decompress((ROOT/'data/html/ems-reference.js.gz').read_bytes()).decode()
        ref=json.loads(re.search(r'window.OT_EMS_REFERENCE = (.*);\n',source).group(1))
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

if __name__=='__main__':unittest.main()
