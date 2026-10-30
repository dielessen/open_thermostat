import json
import re
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import ci_reuse

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/build.yml'
REPO, SHA = 'dielessen/open_thermostat', 'a' * 40


def args(ref='refs/tags/v0.1.0-e32v2-beta.21', event='push', run_id=99):
    return SimpleNamespace(repository=REPO, sha=SHA, ref=ref, event=event, run_id=run_id,
                           workflow_path='.github/workflows/build.yml')


def run(run_id=7, branch='beta21', **changes):
    value = dict(id=run_id, head_sha=SHA, event='push', conclusion='success', head_branch=branch,
                 path='.github/workflows/build.yml', head_repository={'full_name': REPO},
                 html_url=f'https://github.com/{REPO}/actions/runs/{run_id}')
    value.update(changes)
    return value


def jobs(**conclusions):
    rows = {name: 'success' for name in ci_reuse.REQUIRED_JOBS}
    rows.update(conclusions)
    return {'jobs': [{'name': name, 'conclusion': c} for name, c in rows.items() if c is not None]}


class Api:
    def __init__(self, runs, job_rows=None, tags=('v0.1.0-e32v2-beta.21',)):
        self.runs, self.job_rows, self.tags, self.calls = runs, job_rows or {}, set(tags), []

    def fetch(self, path, token):
        self.calls.append(path)
        if '/jobs?' in path:
            return self.job_rows.get(int(path.split('/runs/')[1].split('/')[0]), jobs())
        return {'workflow_runs': self.runs}

    def tag(self, repository, name, token):
        return name in self.tags


class Decide(unittest.TestCase):
    def decide(self, api, **kw):
        return ci_reuse.decide(args(**kw), 'token', api.fetch, api.tag)

    def test_a_branch_push_runs_everything_without_asking_the_api(self):
        api = Api([run()])
        result = self.decide(api, ref='refs/heads/beta21')
        self.assertEqual(result['reuse'], 'false')
        self.assertEqual(json.loads(result['build_matrix']), ci_reuse.BUILD_ENVIRONMENTS)
        self.assertEqual(api.calls, [])

    def test_a_pull_request_runs_everything(self):
        self.assertEqual(self.decide(Api([run()]), event='pull_request')['reuse'], 'false')

    def test_a_tag_reuses_the_green_branch_run_of_the_same_commit(self):
        result = self.decide(Api([run(7)]))
        self.assertEqual((result['reuse'], result['reuse_run_id']), ('true', '7'))
        self.assertEqual(json.loads(result['build_matrix']), ['e32v2'])
        self.assertTrue(result['reuse_run_url'].endswith('/runs/7'))

    def test_the_tag_run_itself_and_other_tag_runs_never_count(self):
        api = Api([run(99, branch='v0.1.0-e32v2-beta.21'), run(98, branch='ha-v0.4.0b13')],
                  tags=('v0.1.0-e32v2-beta.21', 'ha-v0.4.0b13'))
        result = self.decide(api)
        self.assertEqual(result['reuse'], 'false')
        self.assertIn('a tag run', result['reason'])

    def test_a_run_with_a_failed_skipped_or_missing_required_job_does_not_count(self):
        for conclusion in ('failure', 'skipped', 'cancelled', None):
            api = Api([run(7)], {7: jobs(**{'browser (2/4)': conclusion})})
            result = self.decide(api)
            self.assertEqual(result['reuse'], 'false', conclusion)
            self.assertIn('browser (2/4)', result['reason'])

    def test_another_commit_workflow_event_or_repository_does_not_count(self):
        for change in ({'head_sha': 'b' * 40}, {'path': '.github/workflows/readme.yml'},
                       {'event': 'workflow_dispatch'}, {'conclusion': 'failure'},
                       {'head_repository': {'full_name': 'someone/fork'}}):
            self.assertEqual(self.decide(Api([run(7, **change)]))['reuse'], 'false', change)

    def test_the_newest_qualifying_run_is_chosen(self):
        api = Api([run(5), run(8), run(6)], {8: jobs(**{'soak-smoke': 'failure'})})
        self.assertEqual(self.decide(api)['reuse_run_id'], '6')

    def test_an_api_error_means_a_full_run(self):
        def broken(path, token):
            raise urllib.error.URLError('down')
        result = ci_reuse.decide(args(), 'token', broken, Api([]).tag)
        self.assertEqual(result['reuse'], 'false')
        self.assertIn('lookup failed', result['reason'])

    def test_without_a_token_the_run_is_full(self):
        self.assertEqual(ci_reuse.decide(args(), '', Api([run()]).fetch, Api([]).tag)['reuse'], 'false')


class WorkflowAgreement(unittest.TestCase):
    """The required job list must follow the workflow, or reuse would accept too little."""

    def setUp(self):
        self.text = WORKFLOW.read_text()
        body = self.text.split('\njobs:\n', 1)[1]
        self.job_ids = re.findall(r'^  ([a-z0-9-]+):$', body, re.M)

    def test_every_test_job_of_the_workflow_is_required(self):
        bases = {name.split(' (')[0] for name in ci_reuse.REQUIRED_JOBS}
        test_jobs = {job for job in self.job_ids if job != 'reuse' and not job.startswith('publish-')}
        self.assertEqual(bases, test_jobs)

    def test_matrix_names_and_values_match(self):
        self.assertIn('name: browser (${{ matrix.shard }}/%d)' % ci_reuse.BROWSER_SHARDS, self.text)
        self.assertIn('shard: [%s]' % ', '.join(str(i) for i in range(1, ci_reuse.BROWSER_SHARDS + 1)), self.text)
        self.assertIn("core: ['%s']" % "', '".join(ci_reuse.HA_COMPAT_CORES), self.text)
        self.assertIn('name: home-assistant-compat (${{ matrix.core }})', self.text)
        self.assertIn('environment: ${{ fromJSON(needs.reuse.outputs.build_matrix) }}', self.text)

    def test_publication_keeps_the_gates_that_reuse_cannot_replace(self):
        publish = self.text.split('\n  publish-test-release:\n', 1)[1].split('\n  publish-home-assistant-test-release:\n')[0]
        for gate in ("needs.gates.result == 'success'", "needs.source-reproduction.result == 'success'",
                     "needs.build.result == 'success'", "needs.home-assistant-native.result == 'success'"):
            self.assertIn(gate, publish)
        ha = self.text.split('\n  publish-home-assistant-test-release:\n', 1)[1]
        for gate in ("needs.gates.result == 'success'", "needs.home-assistant-native.result == 'success'"):
            self.assertIn(gate, ha)


if __name__ == '__main__':
    unittest.main()
