"""Anonymous GET: wait until every workflow run for a commit has completed, then print their conclusions."""
import json, sys, time, urllib.request
sha = sys.argv[1]
url = f'https://api.github.com/repos/dielessen/open_thermostat/actions/runs?head_sha={sha}&per_page=20'
deadline = time.time() + 3 * 3600
while True:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json'}), timeout=30) as r:
            runs = json.loads(r.read())['workflow_runs']
    except Exception as e:
        print('poll error', e, flush=True); runs = None
    if runs:
        states = [(x['name'], x['status'], x['conclusion']) for x in runs]
        if all(s == 'completed' for _, s, _ in states):
            for n, s, c in states: print(n, s, c)
            for x in runs: print(x['html_url'])
            break
    if time.time() > deadline: print('timeout', runs and [(x['name'], x['status']) for x in runs]); break
    time.sleep(180)
