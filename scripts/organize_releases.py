"""Organize release titles/notes; never mutate tags, assets or release status."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

START = '<!-- openthermostat-original-notes:start -->'
END = '<!-- openthermostat-original-notes:end -->'
USER_NOTES = '<!-- user-release-notes:v1 -->'
ENGLISH_USER_NOTES = '<!-- user-release-notes:v2:en -->'
PATTERNS = {
    'firmware': r'v(\d+)\.(\d+)\.(\d+)-e32v2(?:-(alpha|beta|rc)\.(\d+))?',
    'ha': r'ha-v(\d+)\.(\d+)\.(\d+)(?:(\.dev|a|b|rc)(\d+))?',
    'source': r'sources-e32v2-(\d{8})\.(\d+)',
}


def classify(tag):
    for channel, pattern in PATTERNS.items():
        if match := re.fullmatch(pattern, tag):
            if channel == 'firmware':
                major, minor, patch, stage, sequence = match.groups()
                numbers = (major, minor, patch) + ((sequence,) if sequence is not None else ())
                if any((len(n)>1 and n.startswith('0')) or int(n)>2**32-1 for n in numbers):
                    return None, ()
                return channel, (int(major), int(minor), int(patch),
                                 {'alpha':0, 'beta':1, 'rc':2, None:3}[stage], int(sequence or 0))
            if channel == 'ha':
                major, minor, patch, stage, sequence = match.groups()
                numbers = (major, minor, patch) + ((sequence,) if sequence is not None else ())
                if any((len(n)>1 and n.startswith('0')) or int(n)>2**32-1 for n in numbers):
                    return None, ()
                return channel, (int(major), int(minor), int(patch),
                                 {'.dev':0, 'a':1, 'b':2, 'rc':3, None:4}[stage], int(sequence or 0))
            return channel, tuple(map(int, match.groups()))
    return None, ()

def is_stable(channel, version, release=None):
    """A stable firmware/HA release: no pre-release suffix, and not published as a GitHub pre-release."""
    stage = {'firmware': 3, 'ha': 4}.get(channel)
    return (stage is not None and bool(version) and version[3] == stage
            and (release is None or release.get('prerelease') is not True))



def ha_version(version):
    base = f'{version[0]}.{version[1]}.{version[2]}'
    return base if version[3] == 4 else base + ('.dev', 'a', 'b', 'rc')[version[3]] + str(version[4])


def firmware_heading(version):
    if version[3] == 3:
        return f'# E32 V2 {version[0]}.{version[1]}.{version[2]}'
    return f'# E32 V2 {("alpha", "beta", "rc")[version[3]]}{version[4]}'


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


def publication_notes(notes, repository, tag, require_user_notes=False):
    """Bound future release API responses; full history stays at the immutable tag."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository):
        raise ValueError('invalid_repository')
    channel, version = classify(tag)
    if channel not in ('firmware', 'ha'):
        raise ValueError('invalid_publication_tag')
    lines = notes.strip().splitlines()
    expected = (firmware_heading(version) if channel == 'firmware' else
                '# HA ' + ha_version(version))
    if not lines or not (lines[0] == expected or lines[0].startswith(expected+' ')):
        raise ValueError('publication_notes_version_mismatch')
    for index, line in enumerate(lines[1:], 1):
        if line.startswith('# '):
            lines = lines[:index]
            break
    document = 'RELEASE-NOTES.md' if channel == 'firmware' else 'HA-RELEASE-NOTES.md'
    current = '\n'.join(lines).rstrip()
    if require_user_notes:
        if ENGLISH_USER_NOTES in current:
            sections = ('## New', '## Fixed', '## Updating', '## Limitations')
        elif USER_NOTES in current:
            # Preserve already published bilingual history. New notes use v2:en.
            sections = ('## Nieuw', '## Opgelost', '## Bijwerken en gebruik', '## English')
        else:
            raise ValueError('publication_notes_need_user_features_fixes_update_and_limitations')
        headings = set(current.splitlines())
        if any(section not in headings for section in sections):
            raise ValueError('publication_notes_need_user_features_fixes_update_and_limitations')
    url = f'https://github.com/{repository}/blob/{tag}/docs/modern-thermostat/{document}'
    result = current+'\n\n[Full release notes and history]('+url+')\n'
    if len(result.encode()) > 6000:
        raise ValueError('publication_notes_too_large; shorten current summary, retain full history in source')
    return result



def verify_publication_notes(root, repository="dielessen/open_thermostat"):
    """Fail release preparation before builds/tags when current notes are stale."""
    root = Path(root)
    firmware = json.loads((root / "release.json").read_text())["version"]
    ha_version = json.loads((root / "ha/config/custom_components/open_thermostat/manifest.json").read_text())["version"]
    tags = {"firmware": firmware, "ha": "ha-v" + ha_version}
    for channel, filename in (("firmware", "RELEASE-NOTES.md"), ("ha", "HA-RELEASE-NOTES.md")):
        if classify(tags[channel])[0] != channel:
            raise ValueError("invalid_publication_tag")
        publication_notes((root / "docs/modern-thermostat" / filename).read_text(),
                          repository, tags[channel], require_user_notes=True)
    return tags


def user_summary(tag, repository, root=None):
    """Use deliberately edited reader notes, never guess features from code."""
    channel, version = classify(tag)
    if channel not in ('firmware', 'ha'):
        return ''
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    filename = 'RELEASE-NOTES.md' if channel == 'firmware' else 'HA-RELEASE-NOTES.md'
    path = root / 'docs/modern-thermostat' / filename
    if not path.is_file():
        return ''
    expected = (firmware_heading(version) if channel == 'firmware' else
                '# HA ' + ha_version(version))
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        if line == expected or line.startswith(expected+' '):
            section_lines = lines[index:]
            for end, following in enumerate(section_lines[1:], 1):
                if following.startswith('# '):
                    section_lines = section_lines[:end]
                    break
            section = '\n'.join(section_lines)
            if USER_NOTES not in section and ENGLISH_USER_NOTES not in section:
                return ''
            rendered = publication_notes(section, repository, tag, require_user_notes=True)
            return '\n'.join(rendered.splitlines()[1:]).strip()
    return ''


def label(channel, version):
    if channel == 'firmware':
        return 'E32 firmware', (f'{version[0]}.{version[1]}.{version[2]}' if version[3] == 3
                                else f'{("alpha", "beta", "rc")[version[3]]}.{version[4]}')
    if channel == 'ha':
        return 'Home Assistant', ha_version(version)
    return 'E32 SDK source package', f'{version[0]}.{version[1]}'


def archive_summary(tag, notes, root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    path = root / 'docs/modern-thermostat/USER-RELEASE-NOTES.json'
    records = json.loads(path.read_text())
    if records['schema'] != 1:
        raise ValueError('unsupported_archive_notes_schema')
    entry = records['releases'].get(tag)
    if entry is None:
        return ''
    if hashlib.sha256(notes.encode()).hexdigest() != entry['original_notes_sha256']:
        raise ValueError('archive_original_notes_changed:'+tag)
    summary = entry['summary']
    # English archive summaries (v2:en) use the same four sections as current notes.
    sections = ((ENGLISH_USER_NOTES, '## New', '## Fixed', '## Updating', '## Limitations')
                if ENGLISH_USER_NOTES in summary else
                (USER_NOTES, '## Nieuw', '## Opgelost', '## Bijwerken en gebruik', '## English'))
    if any(section not in summary for section in sections):
        raise ValueError('incomplete_archive_summary:'+tag)
    return summary


def plan(releases, repository, include_archive=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*', repository):
        raise ValueError('invalid_repository')
    latest, stable = {}, {}
    for release in releases:
        channel, version = classify(release['tag_name'])
        if channel and not release['draft'] and (
            channel not in latest or version > classify(latest[channel]['tag_name'])[1]
        ):
            latest[channel] = release
        if channel and not release['draft'] and is_stable(channel, version, release) and (
            channel not in stable or version > classify(stable[channel]['tag_name'])[1]
        ):
            stable[channel] = release
    # A newer pre-release than the stable release of its component, if any.
    preview = {channel: row for channel, row in latest.items()
               if channel in stable and row['id'] != stable[channel]['id']}
    base = 'https://github.com/'+repository+'/releases'

    def download(release, channel):
        title, version = label(channel, classify(release['tag_name'])[1])
        filename = 'firmware.bin' if channel == 'firmware' else f'OpenThermostat-HA-{version}.zip'
        asset = next((a for a in release.get('assets', []) if a['name'] == filename), None)
        if asset is None:
            raise ValueError('missing_current_download:'+release['tag_name'])
        return title, f'[{version}]({base}/tag/{release["tag_name"]})', f'[{filename}]({asset["browser_download_url"]})'
    if not stable:
        # Only test releases so far: the overview stays exactly as published before 1.0.
        table = ['## Which download do you need?', '',
                 '| Component | Current test version | File |',
                 '| --- | --- | --- |']
        for channel in ('firmware', 'ha'):
            if channel in latest:
                table.append('| %s | %s | %s |' % download(latest[channel], channel))
    else:
        table = ['## Which download do you need?', '',
                 '| Component | Version | Channel | File |',
                 '| --- | --- | --- | --- |']
        for channel in ('firmware', 'ha'):
            for row, kind in ((stable.get(channel), 'Stable'), (preview.get(channel), 'Pre-release'),
                              (latest.get(channel) if channel not in stable else None, 'Pre-release')):
                if row is not None:
                    title, version, file = download(row, channel)
                    table.append(f'| {title} | {version} | {kind} | {file} |')
    if 'source' in latest:
        table += ['', f'[Source and licence material]({base}/tag/{latest["source"]["tag_name"]}) '
                  'is supplied separately; it is not an installation file.']
    table += ['', 'These are test releases. Firmware and the HA integration have separate version numbers.'
              if not stable else 'Use the stable release; a pre-release is a test version. '
              'Firmware and the HA integration have separate version numbers.']
    overview = '\n'.join(table)
    changes = []
    for release in releases:
        channel, version = classify(release['tag_name'])
        if channel is None:
            continue
        title, short = label(channel, version)
        newest = latest.get(channel, {}).get('id') == release['id']
        released = stable.get(channel, {}).get('id') == release['id']
        current = newest or released
        if release['draft']:
            name = f'Draft · {title} · {short}'
            status = '**Draft — not published yet.**'
        elif channel == 'source':
            name = f'{title} · {short}'
            status = '**Source and licence material for reproducibility.**'
        elif released:
            name = f'{title} · {short} · Current'
            status = f'**Current stable release of {title}.**'
        elif newest and channel in stable:
            name = f'{title} · {short} · Pre-release'
            status = f'**Pre-release — a test version of {title}; the stable release is in the overview below.**'
        elif current:
            name = f'{title} · {short} · Current'
            status = f'**Current test version for {title}.**'
        else:
            name = f'Archive · {title} · {short}'
            status = ('**Archive — use the overview below for current test versions.**' if not stable
                      else '**Archive — use the overview below for the current versions.**')
        notes = original_notes(release.get('body'))
        reader_notes = user_summary(release['tag_name'], repository)
        if not reader_notes and include_archive:
            reader_notes = archive_summary(release['tag_name'], notes)
        release_overview = overview
        if include_archive and reader_notes and not current:
            release_overview = '## Which download do you need?\n\n[Use the current firmware and Home Assistant versions]('+base+'). Firmware and HA are separate downloads.'
        sections = [status, reader_notes, release_overview] if reader_notes else [status, release_overview]
        original = '<details>\n<summary>Full original release notes and evidence</summary>\n\n'+START+'\n'+notes+'\n'+END+'\n\n</details>'
        summary = first_section(notes) if not reader_notes and (current or channel == 'source') else ''
        if summary:
            sections.append('## This version\n\n'+summary)
        body = '\n\n'.join(sections+[original])+'\n'
        # Older installed firmware bounds each complete GitHub API response at
        # 32 KiB. Preserve originals verbatim; drop only the optional duplicate.
        if len(body.encode()) > 21000 and summary:
            body = '\n\n'.join([status, overview, original])+'\n'
        if len(body.encode()) > 21000:
            raise ValueError('release_notes_exceed_updater_budget:'+release['tag_name'])
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
    parser.add_argument('--publication-notes-for', help='Write bounded notes before publishing this canonical firmware/HA tag')
    args = parser.parse_args()
    if args.publication_notes_for:
        if args.input or args.apply:
            parser.error('publication notes cannot edit releases or consume a release inventory')
        channel, _ = classify(args.publication_notes_for)
        if channel not in ('firmware','ha'):
            parser.error('expected canonical firmware or HA tag')
        document = 'RELEASE-NOTES.md' if channel == 'firmware' else 'HA-RELEASE-NOTES.md'
        notes = (Path(__file__).resolve().parents[1]/'docs/modern-thermostat'/document).read_text()
        rendered = publication_notes(notes,args.repository,args.publication_notes_for,require_user_notes=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(rendered)
        print(json.dumps({'tag':args.publication_notes_for,'bytes':len(rendered.encode()),'full_history_in_tagged_source':True}))
        return
    releases = json.loads(args.input.read_text()) if args.input else fetch(args.repository)
    changes = plan(releases, args.repository, include_archive=True)
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
            changes = plan(fetch(args.repository), args.repository, include_archive=True)
            if not changes:
                break
            history.extend(changes)
            args.output.write_text(json.dumps(history, indent=2)+'\n')
        else:
            raise RuntimeError('release_catalog_kept_changing; inspect saved plan')
    print(json.dumps({'changes':applied if args.apply else len(changes), 'applied':args.apply}))


if __name__ == '__main__':
    main()
