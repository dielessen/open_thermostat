"""Refresh only the README release block from published GitHub releases.

--apply updates README.md and its source-inventory checksum on the default branch
in one commit, with a fast-forward-only branch update.
It never changes firmware source, tags, release assets or acceptance records.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote

from organize_releases import classify, fetch, ha_version, is_stable

START = '<!-- openthermostat-readme-releases:start -->'
END = '<!-- openthermostat-readme-releases:end -->'
INVENTORY = 'docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json'


def render(readme, releases, repository):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository):
        raise ValueError('invalid_repository')
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError('README needs exactly one release block')
    start, end = readme.index(START), readme.index(END)
    if end < start:
        raise ValueError('reversed_readme_release_markers')
    latest, stable = {}, {}
    for row in releases:
        channel, version = classify(row['tag_name'])
        if channel not in ('firmware', 'ha') or row['draft'] or not row.get('published_at'):
            continue
        if channel not in latest or version > classify(latest[channel]['tag_name'])[1]:
            latest[channel] = row
        # Stable: a tag without a pre-release suffix that GitHub does not list as a pre-release.
        if is_stable(channel, version, row) and row.get('prerelease') is False and (
                channel not in stable or version > classify(stable[channel]['tag_name'])[1]):
            stable[channel] = row
    if set(latest) != {'firmware', 'ha'}:
        raise ValueError('published_firmware_and_ha_required')
    lines = ['## Latest published releases', '',
             '| Component | Version | Channel |', '| --- | --- | --- |']
    for channel, name in (('firmware', 'E32 V2 firmware'), ('ha', 'Home Assistant integration')):
        # The stable release first; a newer pre-release (a test version) below it.
        shown = [(stable[channel], 'Stable')] if channel in stable else []
        if latest[channel] is not stable.get(channel):
            shown.append((latest[channel], 'Pre-release'))
        for row, kind in shown:
            version = row['tag_name'] if channel == 'firmware' else ha_version(classify(row['tag_name'])[1])
            url = f'https://github.com/{repository}/releases/tag/{row["tag_name"]}'
            lines.append(f'| {name} | [{version}]({url}) | {kind} |')
    build = stable.get('firmware', latest['firmware'])['tag_name']
    lines += ['', 'Firmware and the HA integration are separate downloads. Read each release’s',
              'changes, compatibility notes and installation instructions before updating.', '',
              'To build the published E32 firmware, start from its exact tag:', '', '```sh',
              f'git clone --branch {build} https://github.com/{repository}.git',
              '```']
    return readme[:start+len(START)] + '\n\n' + '\n'.join(lines) + '\n\n' + readme[end:]


def api(path, payload=None, method='POST'):
    command = ['gh', 'api', path]
    if payload is None:
        return json.loads(subprocess.check_output(command, text=True))
    with tempfile.TemporaryDirectory(prefix='ot-readme-') as work:
        path = Path(work) / 'request.json'
        path.write_text(json.dumps(payload))
        return json.loads(subprocess.check_output(command + ['--method', method, '--input', str(path)], text=True))


def update_inventory(text, readme):
    inventory = json.loads(text)
    found = False
    for item in inventory['items']:
        for source in item['files']:
            if source['path'] == 'README.md':
                source['sha256'] = hashlib.sha256(readme.encode('utf-8')).hexdigest()
                found = True
    if not found:
        raise ValueError('README source-inventory entry missing')
    return json.dumps(inventory, indent=2, ensure_ascii=False) + '\n'


def sync(repository):
    # Commit the page and its inventory checksum atomically. A concurrent branch
    # change rejects the ref update, so retry from its new head without losing it.
    for attempt in range(3):
        branch = api(f'repos/{repository}')['default_branch']
        base = f'repos/{repository}'
        head = api(base + '/branches/' + quote(branch, safe=''))['commit']
        ref = '?ref=' + head['sha']
        current = api(base + '/contents/README.md' + ref)
        before = base64.b64decode(current['content']).decode('utf-8')
        after = render(before, fetch(repository), repository)
        if after == before:
            return {'updated': False, 'branch': branch}
        recorded = api(base + '/contents/' + INVENTORY + ref)
        inventory = update_inventory(base64.b64decode(recorded['content']).decode('utf-8'), after)
        tree = api(base + '/git/trees', {'base_tree': head['commit']['tree']['sha'], 'tree': [
            {'path': path, 'mode': '100644', 'type': 'blob', 'content': content}
            for path, content in (('README.md', after), (INVENTORY, inventory))]})
        commit = api(base + '/git/commits', {
            'message': 'docs: refresh published release links on the project page',
            'tree': tree['sha'], 'parents': [head['sha']]})
        try:
            api(base + '/git/refs/heads/' + quote(branch, safe=''),
                {'sha': commit['sha'], 'force': False}, method='PATCH')
        except subprocess.CalledProcessError:
            if attempt == 2:
                raise
            continue
        # A second pass catches a publication completed while the commit ran.
        latest = api(base + '/contents/README.md?ref=' + quote(branch, safe=''))
        text = base64.b64decode(latest['content']).decode('utf-8')
        if render(text, fetch(repository), repository) == text:
            return {'updated': True, 'branch': branch, 'commit': commit['sha']}
    raise RuntimeError('README or release catalog kept changing; rerun the refresh')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='dielessen/open_thermostat')
    parser.add_argument('--readme', type=Path, default=Path('README.md'))
    parser.add_argument('--input', type=Path, help='Offline GitHub release inventory')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--write', action='store_true', help='Refresh the local README')
    mode.add_argument('--check', action='store_true', help='Reject stale local release links')
    mode.add_argument('--apply', action='store_true', help='Refresh the default branch README on GitHub')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', args.repository):
        parser.error('invalid_repository')
    if args.apply:
        if args.input:
            parser.error('--apply always reads the live release catalog')
        print(json.dumps(sync(args.repository)))
        return
    releases = json.loads(args.input.read_text()) if args.input else fetch(args.repository)
    before = args.readme.read_text()
    after = render(before, releases, args.repository)
    if args.check and before != after:
        parser.exit(1, 'README release links are stale; run with --write\n')
    if args.write:
        args.readme.write_text(after)
    print(json.dumps({'updated': args.write and before != after}))


if __name__ == '__main__':
    main()
