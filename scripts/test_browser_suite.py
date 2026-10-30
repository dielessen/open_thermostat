"""test/browser-tests.txt lists every browser regression exactly once, in a fixed shard."""
import re
import unittest
from pathlib import Path

import ci_reuse

ROOT = Path(__file__).resolve().parents[1]


def entries():
    rows = []
    for line in (ROOT / 'test/browser-tests.txt').read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            shard, path = line.split()[:2]
            rows.append((int(shard), path))
    return rows


class BrowserSuite(unittest.TestCase):
    def test_every_browser_test_file_is_listed_once(self):
        listed = [path for _, path in entries()]
        on_disk = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / 'test').rglob('*.cjs')
                         if re.search(r'(^|-)browser\.cjs$', p.name) and 'node_modules' not in p.parts)
        self.assertEqual(len(listed), len(set(listed)), 'a test is listed twice')
        self.assertEqual(sorted(listed), on_disk, 'a browser test is missing from test/browser-tests.txt (or gone)')

    def test_shards_are_the_ci_matrix_and_none_is_empty(self):
        shards = {shard for shard, _ in entries()}
        self.assertEqual(shards, set(range(1, ci_reuse.BROWSER_SHARDS + 1)))

    def test_ci_runs_the_list_through_the_shared_runner(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        self.assertIn('bash test/run-browser-tests.sh --shard "${{ matrix.shard }}/%d"' % ci_reuse.BROWSER_SHARDS, workflow)
        self.assertNotRegex(workflow, r'\n\s+browser test/[^\n]+\.cjs\n', 'a browser test is still listed in the workflow')


if __name__ == '__main__':
    unittest.main()
