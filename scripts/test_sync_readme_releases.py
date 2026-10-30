"""Published releases refresh without changing reviewed feature/acceptance prose."""
import base64
import hashlib
import json
import subprocess
import unittest
from unittest.mock import patch

import sync_readme_releases as page


def row(tag, **extra):
    return {'tag_name': tag, 'draft': False, 'prerelease': True,
            'published_at': '2026-10-26T09:00:00Z', **extra}


class ReadmeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.text = '# Reviewed project\n' + page.START + '\nold links\n' + page.END + '\nPhysical outputs disabled.\n'
        self.rows = [row('ha-v0.4.0b3'), row('v0.1.0-e32v2-beta.3')]

    def test_semantic_latest_public_versions_not_order_or_drafts(self):
        rows = self.rows + [row('v0.1.0-e32v2-beta.11'),
                           row('v0.1.0-e32v2-beta.12', draft=True),
                           row('v0.1.0-e32v2-beta.13', published_at=None),
                           row('v0.1.0-e32v2-alpha.99'),
                           row('ha-v0.4.0.dev99'), row('sources-e32v2-20261026.1')]
        output = page.render(self.text, rows, 'owner/project')
        self.assertIn('/tag/v0.1.0-e32v2-beta.11', output)
        self.assertIn('git clone --branch v0.1.0-e32v2-beta.11', output)
        self.assertIn('[0.4.0b3]', output)
        for hidden in ('beta.12', 'beta.13', 'alpha.99', 'dev99', 'sources-e32'):
            self.assertNotIn(hidden, output)

    def test_reviewed_prose_preserved_and_second_pass_is_noop(self):
        output = page.render(self.text, self.rows, 'owner/project')
        self.assertEqual(output.split(page.START)[0], self.text.split(page.START)[0])
        self.assertEqual(output.split(page.END)[1], self.text.split(page.END)[1])
        self.assertEqual(page.render(output, self.rows, 'owner/project'), output)
        self.assertEqual(self.text.count('old links'), 1)

    def test_stable_release_displaces_prerelease(self):
        output = page.render(self.text, self.rows + [row('v0.1.0-e32v2', prerelease=False)], 'owner/project')
        self.assertIn('[v0.1.0-e32v2](https://github.com/owner/project/releases/tag/v0.1.0-e32v2) | Stable |', output)
        self.assertNotIn('beta.3', output)  # an older pre-release is not shown next to the stable release

    def test_version_one_and_a_newer_pre_release_are_both_shown_with_their_channel(self):
        rows = self.rows + [row('v0.1.0-e32v2-beta.19'), row('v1.0.0-e32v2-rc.1'),
                            row('v1.0.0-e32v2', prerelease=False), row('v1.1.0-e32v2-beta.1'),
                            row('ha-v1.0.0', prerelease=False), row('ha-v0.4.0b11')]
        output = page.render(self.text, rows, 'owner/project')
        table = output.split(page.START)[1].split(page.END)[0]
        self.assertIn('| E32 V2 firmware | [v1.0.0-e32v2](https://github.com/owner/project/releases/tag/v1.0.0-e32v2) | Stable |\n'
                      '| E32 V2 firmware | [v1.1.0-e32v2-beta.1](https://github.com/owner/project/releases/tag/v1.1.0-e32v2-beta.1)'
                      ' | Pre-release |\n'
                      '| Home Assistant integration | [1.0.0](https://github.com/owner/project/releases/tag/ha-v1.0.0) | Stable |\n',
                      table)
        for hidden in ('rc.1', 'beta.19', '0.4.0b11', 'beta.3'):
            self.assertNotIn(hidden, table)
        self.assertIn('git clone --branch v1.0.0-e32v2 ', table)  # build the stable release
        self.assertEqual(page.render(output, rows, 'owner/project'), output)

    def test_a_suffix_or_github_pre_release_is_never_labelled_stable(self):
        rows = [row('ha-v1.0.0', prerelease=True), row('v0.1.0-e32v2-beta.18', prerelease=False),
                row('v1.0.0-e32v2'), {**row('v0.1.0-e32v2-beta.17'), 'prerelease': None}]
        table = page.render(self.text, rows, 'owner/project').split(page.START)[1]
        self.assertNotIn('Stable', table)
        self.assertIn('[v1.0.0-e32v2](https://github.com/owner/project/releases/tag/v1.0.0-e32v2) | Pre-release |', table)
        self.assertIn('[1.0.0](https://github.com/owner/project/releases/tag/ha-v1.0.0) | Pre-release |', table)

    def test_incomplete_catalog_or_ambiguous_markers_fail_closed(self):
        for text in (self.text.replace(page.START, ''), self.text + page.END,
                     page.END + page.START):
            with self.assertRaises(ValueError):
                page.render(text, self.rows, 'owner/project')
        with self.assertRaisesRegex(ValueError, 'published_firmware_and_ha_required'):
            page.render(self.text, self.rows[:1], 'owner/project')
        with self.assertRaisesRegex(ValueError, 'invalid_repository'):
            page.render(self.text, self.rows, 'owner/project/evil')

    def test_atomic_commit_conflict_preserves_human_edit_and_inventory(self):
        current = self.text
        head = 'old-head'
        commits = 0
        trees = []
        recorded = {'items': [{'files': [{'path': 'README.md', 'sha256': 'old'},
                                        {'path': 'src/Board.h', 'sha256': 'unchanged'}]}],
                    'release_state': 'NOT_READY'}

        def api(path, payload=None, method='POST'):
            nonlocal current, head, commits
            if path == 'repos/owner/project':
                return {'default_branch': 'main'}
            if '/branches/' in path:
                return {'commit': {'sha': head, 'commit': {'tree': {'sha': 'base-tree'}}}}
            if '/contents/' in path:
                content = json.dumps(recorded) if page.INVENTORY in path else current
                return {'content': base64.b64encode(content.encode()).decode()}
            if path.endswith('/git/trees'):
                self.assertEqual(payload['base_tree'], 'base-tree')
                self.assertEqual({entry['path'] for entry in payload['tree']}, {'README.md', page.INVENTORY})
                trees.append(payload['tree'])
                return {'sha': 'new-tree'}
            if path.endswith('/git/commits'):
                self.assertEqual(payload['parents'], [head])
                commits += 1
                return {'sha': 'docs-commit-' + str(commits)}
            self.assertTrue(path.endswith('/git/refs/heads/main'))
            self.assertEqual(method, 'PATCH')
            self.assertFalse(payload['force'])
            if commits == 1:
                current += 'Human edit during publication.\n'
                head = 'human-edit-head'
                raise subprocess.CalledProcessError(1, ['gh', 'api'])
            current = next(entry['content'] for entry in trees[-1] if entry['path'] == 'README.md')
            return {}

        with patch.object(page, 'api', side_effect=api), patch.object(page, 'fetch', return_value=self.rows):
            result = page.sync('owner/project')
        self.assertEqual(result['commit'], 'docs-commit-2')
        self.assertIn('Human edit during publication.', current)
        self.assertIn('Physical outputs disabled.', current)
        inventory = json.loads(next(entry['content'] for entry in trees[-1] if entry['path'] == page.INVENTORY))
        self.assertEqual(inventory['items'][0]['files'][0]['sha256'], hashlib.sha256(current.encode()).hexdigest())
        self.assertEqual(inventory['items'][0]['files'][1], recorded['items'][0]['files'][1])
        self.assertEqual(inventory['release_state'], 'NOT_READY')

    def test_already_current_page_has_no_write(self):
        current = page.render(self.text, self.rows, 'owner/project')

        def api(path, payload=None, method='POST'):
            self.assertIsNone(payload)
            if path == 'repos/owner/project':
                return {'default_branch': 'main'}
            if '/branches/' in path:
                return {'commit': {'sha': 'unchanged'}}
            return {'content': base64.b64encode(current.encode()).decode()}

        with patch.object(page, 'api', side_effect=api), patch.object(page, 'fetch', return_value=self.rows):
            self.assertFalse(page.sync('owner/project')['updated'])

    def test_missing_inventory_entry_blocks_publication_of_page(self):
        with self.assertRaisesRegex(ValueError, 'entry missing'):
            page.update_inventory('{"items": []}', self.text)


if __name__ == '__main__':
    unittest.main()
