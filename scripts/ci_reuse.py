"""Decide whether a tag run may reuse the green branch run of the exact same commit.

A tag points at a commit that was already pushed to a branch, and that branch
run executed every test job of this workflow. Running them again on the tag
only adds a second chance for a timing flake and about 20 minutes. When such a
run exists, the tag run keeps every gate that publication relies on (update
gate, source reproduction, E32 build, packaging and verification) and skips the
test jobs.

A branch run counts only when it is a push run of this workflow file, for this
repository and this exact commit, on a branch (not a tag), concluded success,
and every required job of its latest attempt concluded success. Anything else,
including an API error, means a full run.

Prints GitHub step outputs (key=value lines):
  reuse=true|false, reuse_run_id, reuse_run_url, reason, build_matrix (JSON)
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
BUILD_ENVIRONMENTS = ['e32v2', 'esp32dev', 'esp32s3', 'native']
# Only the packaged firmware is built again when tests are reused.
RELEASE_BUILD = ['e32v2']
BROWSER_SHARDS = 4
HA_COMPAT_CORES = ['2026.10.0', '2026.10.2', '2026.10.3']
# Every job a branch run must have passed. test_ci_reuse.py keeps this list in
# step with the job ids of .github/workflows/build.yml.
REQUIRED_JOBS = (
    ['gates', 'harnesses', 'source-reproduction', 'manual-route-compile',
     'settings-route-compile', 'home-assistant-native', 'fuzz-smoke', 'soak-smoke']
    + [f'build ({env})' for env in BUILD_ENVIRONMENTS]
    + [f'browser ({shard}/{BROWSER_SHARDS})' for shard in range(1, BROWSER_SHARDS + 1)]
    + [f'home-assistant-compat ({core})' for core in HA_COMPAT_CORES]
)


def get(path, token):
    request = urllib.request.Request(API + path, headers={
        'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + token,
        'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def is_tag(repository, name, token):
    try:
        get(f'/repos/{repository}/git/ref/tags/{urllib.parse.quote(name, safe="")}', token)
        return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def failed_jobs(jobs):
    """Required jobs that are missing or did not succeed in a run's latest attempt."""
    conclusions = {job['name']: job.get('conclusion') for job in jobs}
    return [name for name in REQUIRED_JOBS if conclusions.get(name) != 'success']


def find_reusable(repository, sha, run_id, workflow_path, token, fetch=get, tag_check=is_tag):
    """(run, reason): a qualifying branch run for this commit, or (None, why not)."""
    query = urllib.parse.urlencode({'head_sha': sha, 'event': 'push', 'status': 'success', 'per_page': 100})
    runs = fetch(f'/repos/{repository}/actions/runs?{query}', token).get('workflow_runs', [])
    reasons = []
    for run in sorted(runs, key=lambda r: r.get('id', 0), reverse=True):
        label = f"run {run.get('id')} ({run.get('head_branch')})"
        if run.get('id') == run_id:
            continue
        if (run.get('head_sha') != sha or run.get('event') != 'push' or run.get('conclusion') != 'success'
                or run.get('path') != workflow_path
                or (run.get('head_repository') or {}).get('full_name') != repository):
            reasons.append(label + ': not a successful push run of this workflow and commit')
            continue
        if tag_check(repository, run.get('head_branch') or '', token):
            reasons.append(label + ': a tag run, not a branch run')
            continue
        jobs = fetch(f"/repos/{repository}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100", token)
        missing = failed_jobs(jobs.get('jobs', []))
        if missing:
            reasons.append(label + ': required jobs not successful: ' + ', '.join(missing))
            continue
        return run, 'all required jobs passed in ' + label
    return None, '; '.join(reasons) or 'no successful branch run of this commit'


def decide(args, token, fetch=get, tag_check=is_tag):
    full = {'reuse': 'false', 'reuse_run_id': '', 'reuse_run_url': '', 'build_matrix': json.dumps(BUILD_ENVIRONMENTS)}
    if args.event != 'push' or not args.ref.startswith('refs/tags/'):
        return dict(full, reason='not a tag push: full run')
    if not token:
        return dict(full, reason='no token: full run')
    try:
        run, reason = find_reusable(args.repository, args.sha, args.run_id, args.workflow_path, token, fetch, tag_check)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        return dict(full, reason=f'lookup failed ({error}): full run')
    if run is None:
        return dict(full, reason=reason + ': full run')
    return {'reuse': 'true', 'reuse_run_id': str(run['id']), 'reuse_run_url': run.get('html_url', ''),
            'build_matrix': json.dumps(RELEASE_BUILD), 'reason': reason}


def main(argv=None):
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--event', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--workflow-path', default='.github/workflows/build.yml')
    args = parser.parse_args(argv)
    result = decide(args, os.environ.get('GH_TOKEN', ''))
    lines = [f'{key}={result[key]}' for key in ('reuse', 'reuse_run_id', 'reuse_run_url', 'build_matrix', 'reason')]
    print('\n'.join(lines))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('\n'.join(lines) + '\n')
    if os.environ.get('GITHUB_ACTIONS') and args.ref.startswith('refs/tags/'):
        # Public annotation: the reader of a release sees where its tests ran.
        title = 'Tests reused' if result['reuse'] == 'true' else 'All tests run on the tag'
        detail = result['reuse_run_url'] or result['reason']
        print(f"::notice title={title}::{result['reason']} {detail}".replace('\n', ' '))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write(f"Test reuse: **{result['reuse']}** - {result['reason']} {result['reuse_run_url']}\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
