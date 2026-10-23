"""Organize release titles/notes; never mutate tags, assets or release status."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

START = '<!-- openthermostat-original-notes:start -->'
END = '<!-- openthermostat-original-notes:end -->'
PATTERNS = {
    'firmware': r'v(\d+)\.(\d+)\.(\d+)-e32v2-alpha\.(\d+)',
    'ha': r'ha-v(\d+)\.(\d+)\.(\d+)\.dev(\d+)',
    'source': r'sources-e32v2-(\d{8})\.(\d+)',
}


def classify(tag):
    for channel, pattern in PATTERNS.items():
        if match := re.fullmatch(pattern, tag):
            return channel, tuple(map(int, match.groups()))
    return None, ()


def original_notes(body):
    body = body or ''
    if START in body or END in body:
        if body.count(START) != 1 or body.count(END) != 1:
            raise ValueError('ambiguous_original_notes_markers')
        start = body.index(START) + len(START)
        end = body.index(END)
        if end < start:
            raise ValueError('reversed_original_notes_markers')
        return body[start:end].removeprefix('\n').removesuffix('\n')
    return body


def first_section(notes):
    """Show this version's section, without repeating the cumulative history."""
    lines = notes.strip().splitlines()
    if lines and lines[0].startswith('# '):
        lines = lines[1:]
    for index, line in enumerate(lines):
        if line.startswith('# '):
            lines = lines[:index]
            break
    summary = '\n'.join(lines).strip()
    # Unstructured historical notes remain available in full in the disclosure.
    return summary if len(summary) <= 2800 else ''


def label(channel, version):
    if channel == 'firmware':
        return 'E32-firmware', f'alpha.{version[3]}'
    if channel == 'ha':
        return 'Home Assistant', f'{version[0]}.{version[1]}.{version[2]}.dev{version[3]}'
    return 'Bronpakket E32 SDK', f'{version[0]}.{version[1]}'


def plan(releases, repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid_repository')
    latest = {}
    for release in releases:
        channel, version = classify(release['tag_name'])
        if channel and not release['draft'] and (
            channel not in latest or version > classify(latest[channel]['tag_name'])[1]
        ):
            latest[channel] = release
    base = 'https://github.com/'+repository+'/releases'
    table = ['## Welke download heb je nodig?', '',
             '| Onderdeel | Actuele testversie | Bestand |',
             '| --- | --- | --- |']
    for channel in ('firmware', 'ha'):
        if channel not in latest:
            continue
        release = latest[channel]
        title, version = label(channel, classify(release['tag_name'])[1])
        filename = 'firmware.bin' if channel == 'firmware' else f'OpenThermostat-HA-{version}.zip'
        asset = next((a for a in release.get('assets', []) if a['name'] == filename), None)
        if asset is None:
            raise ValueError('missing_current_download:'+release['tag_name'])
        table.append(f'| {title} | [{version}]({base}/tag/{release["tag_name"]}) | '
                     f'[{filename}]({asset["browser_download_url"]}) |')
    if 'source' in latest:
        table += ['', f'[Bron- en licentiemateriaal]({base}/tag/{latest["source"]["tag_name"]}) '
                  'staat apart; dit is geen installatiebestand.']
    table += ['', 'Dit zijn testreleases. Firmware en de HA-integratie hebben elk hun eigen versienummer.']
    overview = '\n'.join(table)
    changes = []
    for release in releases:
        channel, version = classify(release['tag_name'])
        if channel is None:
            continue
        title, short = label(channel, version)
        current = latest.get(channel, {}).get('id') == release['id']
        if release['draft']:
            name = f'Concept · {title} · {short}'
            status = '**Concept — nog niet gepubliceerd.**'
        elif channel == 'source':
            name = f'{title} · {short}'
            status = '**Bron- en licentiemateriaal voor reproduceerbaarheid.**'
        elif current:
            name = f'{title} · {short} · Actueel'
            status = f'**Actuele testversie voor {title}.**'
        else:
            name = f'Archief · {title} · {short}'
            status = '**Archief — voor de actuele testversies gebruik je het overzicht hieronder.**'
        notes = original_notes(release.get('body'))
        sections = [status, overview]
        if current or channel == 'source':
            if summary := first_section(notes):
                sections += ['## Deze versie\n\n'+summary]
        sections += ['<details>\n<summary>Volledige oorspronkelijke releasenotities en bewijs</summary>\n\n'
                     +START+'\n'+notes+'\n'+END+'\n\n</details>']
        body = '\n\n'.join(sections)+'\n'
        if release['name'] != name or (release.get('body') or '') != body:
            changes.append({'id': release['id'], 'tag': release['tag_name'], 'name': name, 'body': body})
    return changes


def fetch(repository):
    pages = json.loads(subprocess.check_output([
        'gh', 'api', '--paginate', '--slurp', f'repos/{repository}/releases?per_page=100'
    ], text=True))
    return [release for page in pages for release in page]


def apply(repository, changes):
    # Separate JSON files preserve newlines and avoid shell interpolation of notes.
    with tempfile.TemporaryDirectory(prefix='openthermostat-release-metadata-') as work:
        for change in changes:
            path = Path(work)/'update.json'
            # GitHub can replace a draft's tag with an untagged placeholder
            # when PATCH omits tag_name. Explicitly retain its existing tag.
            path.write_text(json.dumps({'name':change['name'], 'body':change['body'],
                                        'tag_name':change['tag']}))
            subprocess.run(['gh','api','--method','PATCH',
                            f'repos/{repository}/releases/{change["id"]}',
                            '--input',str(path)], check=True, stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default='dielessen/open_thermostat')
    parser.add_argument('--input', type=Path, help='Saved release API inventory instead of a fresh read')
    parser.add_argument('--output', type=Path, required=True, help='Reviewable metadata change plan')
    parser.add_argument('--apply', action='store_true', help='Apply only the planned title/body edits')
    args = parser.parse_args()
    releases = json.loads(args.input.read_text()) if args.input else fetch(args.repository)
    changes = plan(releases, args.repository)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(changes, indent=2)+'\n')
    applied = 0
    if args.apply:
        history = list(changes)
        for _ in range(3):
            apply(args.repository, changes)
            applied += len(changes)
            if args.input:
                break
            # Concurrent firmware/HA publications can finish during this pass.
            # Re-read and converge on the latest complete public catalog.
            changes = plan(fetch(args.repository), args.repository)
            if not changes:
                break
            history.extend(changes)
            args.output.write_text(json.dumps(history, indent=2)+'\n')
        else:
            raise RuntimeError('release_catalog_kept_changing; inspect saved plan')
    print(json.dumps({'changes':applied if args.apply else len(changes), 'applied':args.apply}))


if __name__ == '__main__':
    main()
