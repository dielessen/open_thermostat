"""Anonymous GET: wait for the workflow runs of the given tags to complete and their GitHub releases to exist."""
import json, sys, time, urllib.request, urllib.error
API = 'https://api.github.com/repos/dielessen/open_thermostat'
def get(path):
    with urllib.request.urlopen(urllib.request.Request(API + path, headers={'Accept': 'application/vnd.github+json'}), timeout=30) as r:
        return json.loads(r.read())
tags = sys.argv[1:]
deadline = time.time() + 3 * 3600
time.sleep(60)
while True:
    done = True; lines = []
    for t in tags:
        try:
            runs = get(f'/actions/runs?branch={t}&per_page=10')['workflow_runs']
        except Exception as e:
            lines.append(f'{t}: poll error {e}'); done = False; continue
        if not runs or any(r['status'] != 'completed' for r in runs):
            done = False; lines.append(f'{t}: ' + str([(r['name'], r['status']) for r in runs])); continue
        lines.append(f'{t}: ' + str([(r['name'], r['conclusion'], r['html_url']) for r in runs]))
        try:
            rel = get(f'/releases/tags/{t}')
            lines.append(f'  release: prerelease={rel["prerelease"]} assets={[a["name"] for a in rel["assets"]]}')
        except urllib.error.HTTPError as e:
            lines.append(f'  release: HTTP {e.code}')
            if any(r['conclusion'] == 'success' for r in runs): done = False
    if done or time.time() > deadline:
        print('\n'.join(lines)); break
    time.sleep(180)
