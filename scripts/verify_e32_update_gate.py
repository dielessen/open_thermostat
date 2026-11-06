"""Validate update acceptance and any scoped prerelease publication decision.

This validates evidence correspondence; it never performs an update or claims
that synthetic/CI tests prove a physical installation. A hash-bound owner
exception can permit one beta or release-candidate publication while preserving
the evidence gap; a stable release never uses an exception.

Two physical update routes can be accepted, each with its own evidence:
``native_github`` (the E32 downloads from GitHub itself) and
``home_assistant`` (the official route since beta.19: the Home Assistant update
entity downloads firmware.bin, verifies GitHub's digest, size and version
marker, and uploads it to the E32 over the local network). A stable release
(``vX.Y.Z-e32v2``) is only published on an accepted ``home_assistant`` update.
See docs/modern-thermostat/HA-UPDATE-ACCEPTANCE.en.md.

A stable release also needs the 1.0 readiness report of the release it follows
(tools/switchover/release_ready.py --stage final): every criterion PASS over at
least 14 days, bound by digest under ``readiness_report`` in the policy. The
window is tied to that release: it starts after the accepted install of it
ended and the update entity showed that release, and no other, throughout. A
release candidate (``-rc.N``) may be published before that.

The owner may declare a release stable instead (``stable_declaration`` in the policy, a digest-bound
record: docs/modern-thermostat/STABLE-RELEASE-TAGS.en.md, "Owner-declared stable release"). The owner decides; the
gate records it. The declaration quotes the owner's own words (a placeholder or an empty statement is refused),
names the readiness criteria and receipt checks it declares instead of measuring, and binds the receipt, the
readiness report and the evidence files by SHA-256. With it, and only for the stable tag it names, the readiness
report may be shorter than 14 days and carry ``DECLARED`` criteria (never over a measured FAIL; ``updates`` is
always measured), and the predecessor's receipt may come from the saved Home Assistant history (``evidence:
ha_history``, re-derived here from the bound exports) with its unprovable checks marked ``declared``. A receipt is
still required and the install facts the history shows must hold. The result then says ``publication_basis:
owner_declared_stable`` and lists the statement and everything declared.

A candidate check compares the candidate plan's ``previous_published_tag`` with
the releases that really exist: it must be the highest published (not draft)
firmware release below the candidate. The list comes from the GitHub releases
API (token from GITHUB_TOKEN or GH_TOKEN when set) or from a saved release
catalog (--published-file); when it cannot be read the check fails, unless
--offline says explicitly that it is skipped.
"""
from pathlib import Path
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import sys
import urllib.request

POLICY = 'docs/modern-thermostat/E32-UPDATE-GATE.json'
REQUIRED = ('public_package_exact', 'fresh_preflight_passed', 'backup_verified',
    'single_native_install_command', 'original_admission_recorded',
    'download_checksum_image_readback_passed', 'new_boot_observed',
    'installed_version_source_elf_web_exact', 'boot_confirmed',
    'stable_uptime_observed', 'settings_programs_bindings_preserved',
    'outputs_remained_disabled', 'independent_postcheck_passed')
# The Home Assistant route. The E32 may own the boiler by then (active mode),
# so its control state after the restart must be the documented safe one
# instead of "outputs remained disabled".
HA_REQUIRED = ('public_release_exact', 'fresh_preflight_passed', 'backup_verified',
    'single_ha_install_action', 'ha_download_digest_size_marker_verified',
    'local_upload_accepted', 'new_boot_observed', 'installed_version_source_elf_web_exact',
    'boot_confirmed', 'stable_uptime_observed', 'settings_programs_bindings_preserved',
    'control_state_safe_after_restart', 'ha_entity_reports_new_version',
    'independent_postcheck_passed')
HA_MIN_IMAGE, HA_MAX_IMAGE = 1000000, 0x3C0000  # firmware_update.py's limits
STABLE_UPTIME_SECONDS = 600  # beyond the E32's 10-minute boot-confirmation window
UTC = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z'
READINESS_CRITERIA = ('stability', 'active_control', 'trv_control', 'failure_tests', 'updates', 'install_guide',
                      'release_window')
READINESS_DAYS = 14
# The observations after an install must come from the boot that install produced (R5-08): the boot instant (the
# time of the reading minus its uptime) is the same in all of them, give or take BOOT_JITTER_S, and lies between
# BOOT_BEFORE_S before the install started and BOOT_AFTER_S after it ended.
BOOT_JITTER_S, BOOT_BEFORE_S, BOOT_AFTER_S = 5, 60, 300
DEFAULT_REPOSITORY = 'dielessen/open_thermostat'
# The owner's stable declaration. The placeholder marks where his own words go; a declaration that still has it (or
# an empty statement) is refused. `updates` (an accepted Home Assistant update) is never declared, and a receipt from
# the Home Assistant history must show the install itself (HA_HISTORY_MEASURED) from the bound exports.
DECLARATION_PLACEHOLDER = '<OWNER STATEMENT>'
DECLARABLE_CRITERIA = tuple(name for name in READINESS_CRITERIA if name != 'updates')
HA_HISTORY_MEASURED = ('single_ha_install_action', 'ha_download_digest_size_marker_verified', 'local_upload_accepted',
                       'new_boot_observed', 'installed_version_source_elf_web_exact', 'stable_uptime_observed',
                       'ha_entity_reports_new_version')
DECLARABLE_CHECKS = tuple(name for name in HA_REQUIRED if name not in HA_HISTORY_MEASURED)
# The receipt fields that are re-derived from the bound Home Assistant history exports and must match exactly.
HA_HISTORY_FACTS = ('ha_entity_id', 'ha_installed_version_before', 'ha_latest_version_before',
                    'ha_installed_version_after', 'install_actions', 'ha_install_record', 'ha_integration_version',
                    'firmware_sha256', 'firmware_bytes', 'source_commit', 'web_sha256', 'elf_sha256', 'observations')
UPTIME_UNITS = {'s': 1, 'min': 60, 'h': 3600, 'd': 86400}
EVIDENCE_LIMIT = 4 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def version(value):
    if not isinstance(value, str):
        return None
    number = r'(0|[1-9]\d*)'
    match = re.fullmatch('v'+number+r'\.'+number+r'\.'+number+
        r'-e32v2(?:-(alpha|beta|rc)\.'+number+r')?', value)
    if not match:
        return None
    major, minor, patch, stage, sequence = match.groups()
    return (int(major), int(minor), int(patch),
            {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage], int(sequence or 0))


def valid_tag(value):
    return version(value) is not None


def stable(value):
    """A stable release (vX.Y.Z-e32v2, no alpha/beta/rc suffix)."""
    return valid_tag(value) and version(value)[3] == 3


def hexadecimal(value, length):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{'+str(length)+'}', value) is not None


def integer(value):
    return type(value) is int


def utc_time(value, label):
    require(isinstance(value, str) and re.fullmatch(UTC, value) is not None, 'Missing UTC time: '+label)
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        raise ValueError('Missing UTC time: '+label) from None


def native_acceptance(record):
    """The E32 downloaded and installed the release itself (evidence rules unchanged)."""
    checks = record.get('checks', {})
    require(all(checks.get(key) is True for key in REQUIRED), 'Incomplete physical update acceptance')
    require(record.get('catalog_check_commands') in (0, 1)
            and type(record.get('catalog_check_commands')) is int, 'Unexpected catalog retries')
    require(type(record.get('install_commands')) is int and record['install_commands'] == 1,
            'Install was missing/repeated')
    require(record.get('install_http_status') == 202, 'Original worker admission missing')
    for key, length in (('source_commit', 40), ('elf_sha256', 64), ('web_sha256', 64),
                        ('firmware_sha256', 64), ('installer_receipt_sha256', 64),
                        ('independent_receipt_sha256', 64), ('backup_manifest_sha256', 64)):
        require(isinstance(record.get(key), str)
                and re.fullmatch('[0-9a-f]{'+str(length)+'}', record[key]), 'Missing identity: '+key)


def home_assistant_acceptance(record):
    """Home Assistant's update entity installed exactly the published firmware.bin."""
    tag = record['tag']
    checks = record.get('checks')
    require(isinstance(checks, dict) and all(checks.get(key) is True for key in HA_REQUIRED),
            'Incomplete physical update acceptance')
    for key, length in (('source_commit', 40), ('elf_sha256', 64), ('web_sha256', 64),
                        ('firmware_sha256', 64), ('installer_receipt_sha256', 64),
                        ('independent_receipt_sha256', 64), ('backup_manifest_sha256', 64)):
        require(hexadecimal(record.get(key), length), 'Missing identity: '+key)
    require(record['installer_receipt_sha256'] != record['independent_receipt_sha256'],
            'Independent check must be a separate receipt')
    # The published GitHub release, as Home Assistant read it.
    release = record.get('github_release')
    require(isinstance(release, dict) and release.get('tag_name') == tag and release.get('draft') is False,
            'Release is not the published one')
    require(release.get('prerelease') is (not stable(tag)), 'Release channel does not match the tag')
    published = utc_time(release.get('published_at'), 'release publication')
    asset = release.get('asset')
    require(isinstance(asset, dict) and asset.get('name') == 'firmware.bin', 'Missing firmware.bin asset')
    require(isinstance(asset.get('digest'), str) and asset['digest'] == 'sha256:'+record['firmware_sha256'],
            'firmware.bin SHA-256 differs from the GitHub digest')
    require(integer(asset.get('size')) and HA_MIN_IMAGE <= asset['size'] <= HA_MAX_IMAGE
            and integer(record.get('firmware_bytes')) and record['firmware_bytes'] == asset['size'],
            'firmware.bin size differs from the GitHub asset')
    # The update entity: offered exactly this release, one install action, new version after.
    require(isinstance(record.get('ha_entity_id'), str)
            and re.fullmatch(r'update\.[a-z0-9_]{1,200}', record['ha_entity_id']) is not None,
            'Missing HA update entity')
    before = record.get('ha_installed_version_before')
    require(valid_tag(before) and version(before) < version(tag), 'HA installed version before is not older')
    require(record.get('ha_latest_version_before') == tag, 'HA did not offer this release')
    require(record.get('ha_installed_version_after') == tag, 'HA does not report the new version')
    require(integer(record.get('install_actions')) and record['install_actions'] == 1,
            'Install was missing/repeated')
    require(isinstance(record.get('ha_integration_version'), str)
            and re.fullmatch(r'\d+\.\d+\.\d+(?:(?:\.dev|a|b|rc)\d+)?', record['ha_integration_version']) is not None,
            'Missing HA integration version')
    require(isinstance(record.get('ha_core_version'), str)
            and re.fullmatch(r'\d{4}\.\d{1,2}\.\d+', record['ha_core_version']) is not None,
            'Missing HA Core version')
    # firmware_update.py's own record of the install (its last_install attribute).
    last = record.get('ha_install_record')
    require(isinstance(last, dict) and last.get('result') == 'installed', 'HA install record missing/failed')
    require(last.get('tag') == tag and last.get('from_version') == before
            and last.get('sha256') == record['firmware_sha256'] and last.get('size') == record['firmware_bytes']
            and integer(last.get('uploads')) and last['uploads'] == 1, 'HA install record belongs to another install')
    started = utc_time(last.get('started_at'), 'install start')
    finished = utc_time(last.get('finished_at'), 'install end')
    duration = last.get('duration_s')
    require(type(duration) in (int, float) and 0 < duration <= 900 and started <= finished
            and published <= started, 'Implausible install timing')
    reported = last.get('reported')
    require(isinstance(reported, dict) and reported.get('version') == tag
            and reported.get('source_commit') == record['source_commit']
            and reported.get('web_sha256') == record['web_sha256']
            and reported.get('elf_sha256') == record['elf_sha256'],
            'E32-reported identity after restart differs')
    # The E32 after its restart: the new version, a confirmed boot, stable uptime.
    observations = record.get('observations')
    require(isinstance(observations, list) and len(observations) >= 2, 'Missing boot observations')
    uptime = -1
    boots = []
    for item in observations:
        require(isinstance(item, dict) and item.get('version') == tag and item.get('boot_pending') is False
                and integer(item.get('uptime_seconds')) and item['uptime_seconds'] > uptime,
                'Boot not confirmed or restarted during observation')
        at = utc_time(item.get('at_utc'), 'observation')
        require(at >= finished, 'Observation before the install ended')
        boots.append(at - timedelta(seconds=item['uptime_seconds']))
        uptime = item['uptime_seconds']
    require(uptime >= STABLE_UPTIME_SECONDS, 'Uptime after the update too short')
    # R5-08: rising uptimes alone do not say that the reads belong to this install: a later restart, or reads taken
    # days afterwards, would pass. All reads share one boot, and it is the boot the install produced.
    require(all(abs((boot - boots[0]).total_seconds()) <= BOOT_JITTER_S for boot in boots),
            'Observations come from different boots')
    require(started - timedelta(seconds=BOOT_BEFORE_S) <= boots[0] <= finished + timedelta(seconds=BOOT_AFTER_S),
            'Observations are not of the boot the install produced')


METHODS = {'native_github': native_acceptance, 'home_assistant': home_assistant_acceptance}


# ---- the owner's stable declaration and a receipt from the saved Home Assistant history --------------------------

def placeholder(text):
    """True for a statement that is not the owner's own words yet: empty, or still the marked placeholder."""
    return not isinstance(text, str) or not text.strip() or DECLARATION_PLACEHOLDER in text


def bound_file(root, name, expected_sha, label):
    """The bytes of a repository file bound by SHA-256 (evidence may be larger than a policy document)."""
    require(isinstance(name, str) and bool(name), 'Missing '+label)
    path = (root / name).resolve()
    require(path.is_relative_to(root) and path.is_file(), 'Missing/outside '+label)
    raw = path.read_bytes()
    require(0 < len(raw) <= EVIDENCE_LIMIT, 'Oversized '+label)
    require(hexadecimal(expected_sha, 64), 'Missing digest for '+label)
    require(hashlib.sha256(raw).hexdigest() == expected_sha, label+' changed')
    return raw


def owner_statements(owner):
    """The owner's own words, in the order he gave them; refused while one is a placeholder."""
    require(isinstance(owner, dict) and owner.get('actor') == 'repository_owner'
            and owner.get('method') == 'explicit_user_instruction', "Stable declaration is not the owner's")
    statements = owner.get('statements')
    require(isinstance(statements, list) and bool(statements), 'Stable declaration has no owner statement')
    for item in statements:
        require(isinstance(item, dict) and not placeholder(item.get('text')) and len(item['text']) <= 2000,
                'Stable declaration: the owner statement is a placeholder or missing; his own words are required')
        utc_time(item.get('at_utc'), 'owner statement')
    return [item['text'] for item in statements]


def declaration_record(root, record, name):
    """A stable declaration as the owner gave it: his words, what it declares, and every file it covers by digest."""
    require(isinstance(record, dict) and record.get('schema') == 1 and record.get('kind') == 'owner_declared_stable',
            'Invalid stable declaration')
    tag, follows = record.get('tag'), record.get('follows')
    require(stable(tag) and valid_tag(follows) and version(follows) < version(tag),
            'Stable declaration: tag must be a stable release after the release it follows')
    statements = owner_statements(record.get('owner'))
    criteria = record.get('declared_criteria')
    require(isinstance(criteria, dict) and all(key in DECLARABLE_CRITERIA and isinstance(text, str) and text.strip()
                                               for key, text in criteria.items()),
            'Stable declaration: declared criteria must be readiness criteria with a reason (updates is always measured)')
    checks = record.get('declared_receipt_checks')
    require(isinstance(checks, dict) and all(key in DECLARABLE_CHECKS and isinstance(text, str) and text.strip()
                                             for key, text in checks.items()),
            'Stable declaration: declared receipt checks must be checks the history cannot show, with a reason')
    for key in ('receipt', 'readiness_report'):
        reference = record.get(key)
        require(isinstance(reference, dict) and set(reference) == {'path', 'sha256'},
                'Stable declaration: '+key+' is not bound by digest')
        bound_file(root, reference['path'], reference['sha256'], 'declared '+key)
    evidence = record.get('evidence')
    require(isinstance(evidence, list) and all(isinstance(item, dict) and {'path', 'sha256'} <= set(item)
                                               for item in evidence), 'Stable declaration: invalid evidence list')
    for item in evidence:
        bound_file(root, item['path'], item['sha256'], 'declared evidence '+str(item['path']))
    return {**record, 'file': name, 'statement_texts': statements}


def stable_declaration(root, reference):
    """The policy's stable_declaration: {"declaration": <path>, "sha256": <digest>}, or None."""
    if reference is None:
        return None
    require(isinstance(reference, dict) and set(reference) == {'declaration', 'sha256'},
            'Invalid stable declaration reference')
    return declaration_record(root, document(root, reference['declaration'], 'stable declaration', reference['sha256']),
                              reference['declaration'])


def history_time(row):
    """The time of a recorder row (last_changed, else last_updated) as a naive UTC datetime."""
    text = (row.get('last_changed') or row.get('last_updated')) if isinstance(row, dict) else None
    require(isinstance(text, str), 'A history row has no time')
    try:
        value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('A history row has no time') from None
    require(value.tzinfo is not None, 'A history row has no time zone')
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def ha_history_series(exports):
    """{entity_id: rows in time order} from saved /api/history/period answers (each a list of series). A minimal row
    (no entity_id) belongs to the series it is in; a row in two exports counts once."""
    series = {}
    for export in exports:
        require(isinstance(export, list), 'A Home Assistant history export is a list of series')
        for rows in export:
            require(isinstance(rows, list) and bool(rows) and isinstance(rows[0], dict)
                    and isinstance(rows[0].get('entity_id'), str), 'Invalid Home Assistant history series')
            entity = rows[0]['entity_id']
            require(all(isinstance(row, dict) and row.get('entity_id', entity) == entity for row in rows),
                    'A history series mixes entities')
            known = series.setdefault(entity, [])
            for row in rows:
                if row not in known:
                    known.append(row)
    for rows in series.values():
        rows.sort(key=history_time)
    return series


def ha_history_facts(series, entity_id, tag, uptime_entity, integration_entity):
    """What the recorder history of the update entity, the device-uptime sensor and the integration's own update
    entity shows about the install of `tag`, in the receipt's fields. Raises when the history does not show it."""
    def attributes(row):
        value = row.get('attributes')
        return value if isinstance(value, dict) else {}
    rows = series.get(entity_id) if isinstance(entity_id, str) else None
    require(bool(rows), 'The history has no rows of the update entity')
    require(all('installed_version' in attributes(row) for row in rows),
            'The update entity history must be a full export (with attributes)')
    shown = [row for row in rows if attributes(row).get('installed_version') == tag]
    require(bool(shown), 'The history never shows '+str(tag)+' installed')
    first = history_time(shown[0])
    offered = [row for row in rows if history_time(row) < first and attributes(row).get('latest_version') == tag]
    records = []
    for row in rows:
        last = attributes(row).get('last_install')
        if isinstance(last, dict) and last.get('tag') == tag and last not in records:
            records.append(last)
    require(bool(records), 'The history has no install record of '+str(tag))
    last = records[-1]
    finished = utc_time(last.get('finished_at'), 'install end')
    started = utc_time(last.get('started_at'), 'install start')
    reported = last.get('reported') if isinstance(last.get('reported'), dict) else {}

    def installed_at(moment):
        before = [row for row in rows if history_time(row) <= moment]
        return attributes(before[-1]).get('installed_version') if before else None
    uptime = series.get(uptime_entity) if isinstance(uptime_entity, str) else None
    require(bool(uptime), 'The history has no rows of the device-uptime sensor')
    unit = next((attributes(row)['unit_of_measurement'] for row in uptime
                 if attributes(row).get('unit_of_measurement')), None)
    require(unit in UPTIME_UNITS, 'Unknown unit of the device-uptime sensor: '+str(unit))
    samples = []
    for row in uptime:
        moment = history_time(row)
        try:
            value = float(row.get('state'))
        except (TypeError, ValueError):
            continue  # unavailable or unknown
        if moment < finished or value != value:
            continue
        seconds = int(round(value * UPTIME_UNITS[unit]))
        if samples and seconds < samples[-1][1]:
            break  # a later restart ends the boot the install produced
        samples.append((moment, seconds))
    picks = []
    for sample in samples[:1] + [item for item in samples if item[1] >= STABLE_UPTIME_SECONDS][:1] + samples[-1:]:
        if sample not in picks:
            picks.append(sample)
    observations = [{'at_utc': moment.strftime('%Y-%m-%dT%H:%M:%SZ'), 'version': installed_at(moment),
                     'uptime_seconds': seconds, 'source': uptime_entity} for moment, seconds in picks]
    integration = None
    if isinstance(integration_entity, str) and series.get(integration_entity):
        before = [row for row in series[integration_entity] if history_time(row) <= started]
        integration = attributes(before[-1]).get('installed_version') if before else None
    return {'ha_entity_id': entity_id,
            'ha_installed_version_before': installed_at(first - timedelta(microseconds=1)),
            'ha_latest_version_before': tag if offered else None,
            'ha_installed_version_after': attributes(rows[-1]).get('installed_version'),
            'install_actions': len(records), 'ha_install_record': last, 'ha_integration_version': integration,
            'firmware_sha256': last.get('sha256'), 'firmware_bytes': last.get('size'),
            'source_commit': reported.get('source_commit'), 'web_sha256': reported.get('web_sha256'),
            'elf_sha256': reported.get('elf_sha256'), 'observations': observations}


def release_summary(releases, tag):
    """The published GitHub release of `tag` from a saved release object or catalog, as receipts record it."""
    rows = releases if isinstance(releases, list) else [releases]
    found = [row for row in rows if isinstance(row, dict) and row.get('tag_name') == tag]
    require(len(found) == 1, 'The saved GitHub release evidence has no single release '+str(tag))
    row = found[0]
    assets = [asset for asset in row.get('assets') or [] if isinstance(asset, dict) and asset.get('name') == 'firmware.bin']
    require(len(assets) == 1, 'The saved GitHub release has no firmware.bin')
    return {'tag_name': row.get('tag_name'), 'draft': row.get('draft'), 'prerelease': row.get('prerelease'),
            'published_at': row.get('published_at'),
            'asset': {'name': 'firmware.bin', 'size': assets[0].get('size'), 'digest': assets[0].get('digest')}}


def ha_history_acceptance(root, record, declaration):
    """A receipt built from the saved Home Assistant history (no capture): every fact is re-derived from the bound
    exports, the install itself must be shown (HA_HISTORY_MEASURED), and only checks the history cannot show may be
    'declared', exactly those the owner's declaration covers. Returns the declared checks."""
    tag = record['tag']
    require(declaration is not None, "A receipt from the Home Assistant history needs the owner's stable declaration")
    require(declaration['follows'] == tag, 'The stable declaration follows another release')
    require(record.get('method') == 'home_assistant', 'Wrong update route')
    checks = record.get('checks')
    require(isinstance(checks, dict) and set(checks) == set(HA_REQUIRED)
            and all(value is True or value == 'declared' for value in checks.values())
            and all(checks[key] is True for key in HA_HISTORY_MEASURED), 'Incomplete physical update acceptance')
    declared = sorted(key for key, value in checks.items() if value == 'declared')
    require(record.get('declared_checks') == declared and set(declared) == set(declaration['declared_receipt_checks']),
            "The receipt's declared checks differ from the owner's declaration")
    require(record.get('acceptance_decision') == 'ACCEPTED_ON_OWNER_DECLARATION', 'Update not accepted')
    quoted = record.get('owner_declaration')
    require(isinstance(quoted, dict) and quoted.get('declaration') == declaration['file']
            and quoted.get('statements') == declaration['statement_texts'],
            "The receipt does not quote the owner's declaration")
    files = record.get('evidence_files')
    require(isinstance(files, list) and bool(files), 'Missing Home Assistant history evidence')
    bound = [{'path': item.get('path'), 'sha256': item.get('sha256')} for item in declaration['evidence']]
    exports, releases = [], []
    for item in files:
        require(isinstance(item, dict) and item.get('kind') in ('ha_history', 'github_release'),
                'Invalid evidence file entry')
        require({'path': item.get('path'), 'sha256': item.get('sha256')} in bound,
                "Evidence file not covered by the owner's declaration: "+str(item.get('path')))
        value = json.loads(bound_file(root, item.get('path'), item.get('sha256'), 'evidence '+str(item.get('path'))))
        (exports if item['kind'] == 'ha_history' else releases).append(value)
    require(bool(exports), 'Missing Home Assistant history evidence')
    facts = ha_history_facts(ha_history_series(exports), record.get('ha_entity_id'), tag,
                             record.get('uptime_entity_id'), record.get('ha_integration_entity_id'))
    for key in HA_HISTORY_FACTS:
        require(record.get(key) == facts[key], 'The receipt differs from the Home Assistant history: '+key)
    for key, length in (('source_commit', 40), ('elf_sha256', 64), ('web_sha256', 64), ('firmware_sha256', 64)):
        require(hexadecimal(record.get(key), length), 'Missing identity: '+key)
    require(isinstance(record.get('ha_entity_id'), str)
            and re.fullmatch(r'update\.[a-z0-9_]{1,200}', record['ha_entity_id']) is not None, 'Missing HA update entity')
    before = record.get('ha_installed_version_before')
    require(valid_tag(before) and version(before) < version(tag), 'HA installed version before is not older')
    require(record.get('ha_latest_version_before') == tag, 'HA did not offer this release')
    require(record.get('ha_installed_version_after') == tag, 'HA does not report the new version')
    require(integer(record.get('install_actions')) and record['install_actions'] == 1, 'Install was missing/repeated')
    require(isinstance(record.get('ha_integration_version'), str)
            and re.fullmatch(r'\d+\.\d+\.\d+(?:(?:\.dev|a|b|rc)\d+)?', record['ha_integration_version']) is not None,
            'Missing HA integration version')
    last = record['ha_install_record']
    require(isinstance(last, dict) and last.get('result') == 'installed', 'HA install record missing/failed')
    require(last.get('from_version') == before and integer(last.get('size'))
            and HA_MIN_IMAGE <= last['size'] <= HA_MAX_IMAGE and integer(last.get('uploads')) and last['uploads'] == 1,
            'HA install record belongs to another install')
    started = utc_time(last.get('started_at'), 'install start')
    finished = utc_time(last.get('finished_at'), 'install end')
    duration = last.get('duration_s')
    require(type(duration) in (int, float) and 0 < duration <= 900 and started <= finished, 'Implausible install timing')
    reported = last.get('reported')
    require(isinstance(reported, dict) and reported.get('version') == tag, 'E32-reported identity after restart differs')
    if checks['public_release_exact'] is True:
        require(bool(releases), 'public_release_exact needs the saved GitHub release')
        release = release_summary(releases[0], tag)
        require(record.get('github_release') == release, 'The receipt differs from the saved GitHub release')
        require(release['draft'] is False and release['prerelease'] is (not stable(tag)),
                'Release is not the published one')
        require(release['asset']['digest'] == 'sha256:'+record['firmware_sha256']
                and release['asset']['size'] == record['firmware_bytes'], 'firmware.bin differs from the GitHub asset')
        require(utc_time(release.get('published_at'), 'release publication') <= started, 'Implausible install timing')
    # The E32 after its restart, from the uptime sensor: one boot (the install's), stable for 10 minutes or more.
    observations = record['observations']
    require(isinstance(observations, list) and len(observations) >= 2, 'Missing boot observations')
    uptime, boots = -1, []
    for item in observations:
        require(item.get('version') == tag and integer(item.get('uptime_seconds')) and item['uptime_seconds'] > uptime,
                'Boot not confirmed or restarted during observation')
        at = utc_time(item.get('at_utc'), 'observation')
        require(at >= finished, 'Observation before the install ended')
        boots.append(at - timedelta(seconds=item['uptime_seconds']))
        uptime = item['uptime_seconds']
    require(uptime >= STABLE_UPTIME_SECONDS, 'Uptime after the update too short')
    require(all(abs((boot - boots[0]).total_seconds()) <= BOOT_JITTER_S for boot in boots),
            'Observations come from different boots')
    require(started - timedelta(seconds=BOOT_BEFORE_S) <= boots[0] <= finished + timedelta(seconds=BOOT_AFTER_S),
            'Observations are not of the boot the install produced')
    return declared


def published_tags(releases):
    """The firmware tags that are published (not drafts) in a list of GitHub release objects, or of plain tags."""
    tags = set()
    for row in releases:
        tag, draft = (row, False) if isinstance(row, str) else (row.get('tag_name'), row.get('draft') is True)
        if not draft and valid_tag(tag):
            tags.add(tag)
    return tags


def fetch_published(repository, token=None, urlopen=urllib.request.urlopen, max_pages=12):
    """The releases of a repository from the GitHub API (anonymous, or with a token); any failure raises."""
    rows = []
    for page in range(1, max_pages + 1):
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'openthermostat-update-gate',
                   'X-GitHub-Api-Version': '2022-11-28'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(f'https://api.github.com/repos/{repository}/releases?per_page=100&page={page}',
                                         headers=headers)
        with urlopen(request, timeout=30) as response:
            batch = json.load(response)
        require(isinstance(batch, list), 'Unexpected answer from the GitHub releases API')
        rows += batch
        if len(batch) < 100:
            return rows
    raise ValueError('More release pages than the gate reads: cannot tell the latest published release')


def check_previous_published(previous, candidate, published):
    """R5-07: the plan's previous_published_tag is the highest published firmware release below the candidate.
    A plan that names an older release (or one that was never published) would hide unaccepted releases."""
    below = sorted((version(tag), tag) for tag in published_tags(published) if version(tag) < version(candidate))
    require(below, 'No published firmware release below the candidate')
    latest = below[-1][1]
    require(latest == previous, f'previous_published_tag is {previous}, but the latest published release below '
                                f'{candidate} is {latest}')


def document(root, name, label, expected_sha=None):
    require(isinstance(name, str) and bool(name), 'Missing '+label)
    path = (root / name).resolve()
    require(path.is_relative_to(root) and path.is_file(), 'Missing/outside '+label)
    raw = path.read_bytes()
    require(0 < len(raw) <= 65536, 'Oversized '+label)
    if expected_sha is not None:
        require(isinstance(expected_sha, str) and re.fullmatch('[0-9a-f]{64}', expected_sha),
                'Missing digest for '+label)
        require(hashlib.sha256(raw).hexdigest() == expected_sha, label+' changed')
    value = json.loads(raw)
    require(isinstance(value, dict), 'Invalid '+label)
    return value


def report_declaration(root, report, reference, measured):
    """The owner's stable declaration a readiness report names: valid, about the measured release, binding this
    report by digest, and quoted word for word in it."""
    quoted = report.get('declaration')
    require(isinstance(quoted, dict), 'Invalid owner declaration in the readiness report')
    name = quoted.get('file')
    declaration = declaration_record(root, document(root, name, 'stable declaration'), name)
    require(declaration['follows'] == measured, 'The stable declaration follows another release')
    require(declaration['readiness_report'] == {'path': reference.get('report'), 'sha256': reference.get('sha256')},
            'The stable declaration does not bind this readiness report')
    require(quoted.get('statements') == declaration['statement_texts'],
            "The readiness report does not quote the owner's declaration")
    return declaration


def readiness_report(root, reference, measured, installed_at=None):
    """The 1.0 readiness report a stable release needs: final, every criterion PASS, at
    least READINESS_DAYS long, about the release the stable one follows. The window is tied to
    that release (R5-09): it starts after the accepted install of it ended, and the update entity
    showed that release, and no other, for the whole window.

    A report that names the owner's stable declaration may instead carry DECLARED criteria (exactly those the
    declaration names, each with its measured result attached, never over a FAIL) and, when release_window is
    declared, a window shorter than 14 days; its overall result is then PASS_DECLARED. The report returned then
    carries the declaration under "_declaration" and the declared criteria under "_declared"."""
    require(isinstance(reference, dict), 'A stable release needs a PASS readiness report')
    report = document(root, reference.get('report'), 'readiness report', reference.get('sha256'))
    require(report.get('schema') == 1 and report.get('kind') == 'release_readiness', 'Invalid readiness report')
    require(report.get('stage') == 'final', 'Readiness report is not final')
    require(report.get('release') == measured, 'Readiness report measured another release')
    criteria = report.get('criteria')
    declaration, declared = None, []
    if report.get('declaration') is None:
        require(isinstance(criteria, dict) and report.get('overall') == 'PASS'
                and all(isinstance(criteria.get(name), dict) and criteria[name].get('result') == 'PASS'
                        for name in READINESS_CRITERIA), 'Readiness report is not PASS on every criterion')
    else:
        declaration = report_declaration(root, report, reference, measured)
        named = declaration['declared_criteria']
        require(isinstance(criteria, dict) and all(isinstance(criteria.get(name), dict) for name in READINESS_CRITERIA),
                'Readiness report is not PASS on every criterion')
        declared = sorted(name for name in READINESS_CRITERIA if criteria[name].get('result') == 'DECLARED')
        require(all(criteria[name].get('result') == 'PASS' or (
                    name in declared and name in named and criteria[name].get('declared') == named[name]
                    and isinstance(criteria[name].get('measured'), dict)
                    and criteria[name]['measured'].get('result') in ('PASS', 'WAIT'))
                    for name in READINESS_CRITERIA)
                and report.get('overall') == ('PASS_DECLARED' if declared else 'PASS'),
                'Readiness report is not PASS on every criterion (or declared by the owner over a measured FAIL)')
        require(set(declared) == set(named), "The readiness report's declared criteria differ from the owner's declaration")
    start = utc_time(report.get('from'), 'readiness start')
    end = utc_time(report.get('to'), 'readiness end')
    require(end > start, 'Readiness window is empty')
    if 'release_window' not in declared:
        require((end - start).total_seconds() >= READINESS_DAYS * 86400, 'Readiness window is shorter than 14 days')
    require(report.get('installed_versions') == [measured], 'Readiness window is not the measured release only')
    require(installed_at is not None and start >= utc_time(installed_at, 'accepted install end'),
            'Readiness window starts before the accepted install ended')
    if declaration is not None:
        report = {**report, '_declaration': declaration, '_declared': declared}
    return report


def publication_exception(root, reference):
    if reference is None:
        return None
    require(isinstance(reference, dict) and set(reference) == {'receipt', 'sha256'},
            'Invalid publication exception reference')
    require(isinstance(reference['sha256'], str) and re.fullmatch('[0-9a-f]{64}', reference['sha256']),
            'Missing publication exception digest')
    record = document(root, reference['receipt'], 'publication exception', reference['sha256'])
    require(type(record.get('schema')) is int and record['schema'] == 1 and record.get('status') == 'APPROVED',
            'Publication exception has no explicit approval')
    require(record.get('scope') == 'one_prerelease_publication', 'Wrong exception scope')
    tags = [record.get(key) for key in ('accepted_basis_tag', 'unaccepted_predecessor', 'candidate_tag')]
    require(all(valid_tag(tag) for tag in tags), 'Invalid exception release identity')
    require(version(tags[0]) < version(tags[1]) < version(tags[2]), 'Invalid exception release order')
    require(version(tags[2])[3] in (1, 2), 'Exception is limited to a beta or rc prerelease')
    require(record.get('predecessor_acceptance_status') == 'INCOMPLETE',
            'Exception must retain incomplete predecessor acceptance')
    require(record.get('device_installation_authorized') is False
            and record.get('boiler_trial_authorized') is False, 'Exception grants publication only')
    require(isinstance(record.get('accepted_basis_receipt_sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', record['accepted_basis_receipt_sha256']),
            'Missing accepted basis receipt identity')
    reason = record.get('reason')
    require(isinstance(reason, str) and 1 <= len(reason.strip()) <= 2000, 'Missing exception reason')
    gap_sha = record.get('gap_report_sha256')
    require(isinstance(gap_sha, str) and re.fullmatch('[0-9a-f]{64}', gap_sha), 'Missing evidence-gap digest')
    gap = document(root, record.get('gap_report'), 'predecessor evidence-gap report', gap_sha)
    require(gap.get('status') == 'INCOMPLETE', 'Missing incomplete predecessor evidence')
    approval = record.get('approval')
    require(isinstance(approval, dict) and approval.get('actor') == 'repository_owner'
            and approval.get('method') == 'explicit_user_instruction'
            and approval.get('decision') == 'approve_one_prerelease_publication',
            'Missing explicit operator decision')
    statement = approval.get('statement')
    require(isinstance(statement, str) and 1 <= len(statement.strip()) <= 2000,
            'Missing original approval statement')
    at = approval.get('at_utc')
    require(isinstance(at, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', at),
            'Missing UTC approval time')
    datetime.strptime(at, '%Y-%m-%dT%H:%M:%SZ')
    return record


def verify(root, policy, candidate=None, published=None):
    root = Path(root).resolve()
    require(policy.get('schema') == 1, 'Unknown E32 update-gate schema')
    require(policy.get('required_for_successor_release') is True, 'Mandatory update gate disabled')
    pending = policy.get('pending_tag')
    require(pending is None or valid_tag(pending), 'Invalid pending release')
    declaration = stable_declaration(root, policy.get('stable_declaration'))
    accepted = policy.get('accepted')
    record, declared_checks, owner_declared = None, None, None
    if accepted is not None:
        require(valid_tag(accepted.get('tag')), 'Invalid accepted release')
        require(isinstance(accepted.get('receipt'), str), 'Missing acceptance receipt')
        path = (root / accepted['receipt']).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'Missing/outside acceptance receipt')
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == accepted.get('sha256'), 'Acceptance receipt changed')
        record = json.loads(raw)
        require(isinstance(record, dict) and record.get('schema') == 1 and record.get('status') == 'PASS',
                'Update not accepted')
        require(record.get('tag') == accepted['tag'], 'Acceptance belongs to another release')
        method = record.get('method')
        require(isinstance(method, str) and method in METHODS, 'Wrong update route')
        if record.get('evidence') == 'ha_history':
            # No capture: accepted only on the owner's stable declaration that binds this very receipt.
            require(declaration is not None and declaration['receipt'] == {'path': accepted['receipt'],
                                                                           'sha256': accepted['sha256']},
                    "A receipt from the Home Assistant history is accepted only on the owner's stable declaration "
                    'that binds it')
            declared_checks = ha_history_acceptance(root, record, declaration)
        else:
            METHODS[method](record)
    exception = publication_exception(root, policy.get('publication_exception'))
    plan = None
    if policy.get('candidate_plan') is not None:
        plan = document(root, policy['candidate_plan'], 'candidate plan')
        require(valid_tag(plan.get('planned_tag')) and valid_tag(plan.get('previous_published_tag'))
                and version(plan['previous_published_tag']) < version(plan['planned_tag']),
                'Invalid candidate plan release order')
    basis = None
    if candidate is not None:
        require(valid_tag(candidate), 'Unsupported release candidate')
        require(accepted is not None, 'No physically accepted E32 predecessor; successor publication blocked')
        require(pending == candidate, 'Another release is pending or candidate freeze is missing')
        require(version(candidate) > version(accepted['tag']),
                'Candidate must be newer than accepted predecessor')
        require(plan is not None, 'Missing candidate plan')
        previous = plan.get('previous_published_tag')
        require(plan.get('planned_tag') == candidate and valid_tag(previous)
                and version(previous) < version(candidate), 'Candidate plan identity/order mismatch')
        if published is not None:
            check_previous_published(previous, candidate, published)
        if stable(candidate):
            # Version 1.0 and later: one update on the official route succeeded.
            require(record['method'] == 'home_assistant',
                    'A stable release needs an accepted Home Assistant update')
        basis = 'accepted_previous_release'
        if accepted['tag'] != previous:
            require(exception is not None, 'Previous published release is not accepted; explicit exception required')
            require(exception['candidate_tag'] == candidate and exception['unaccepted_predecessor'] == previous,
                    'Exception belongs to another candidate/predecessor')
            require(exception['accepted_basis_tag'] == accepted['tag']
                    and exception['accepted_basis_receipt_sha256'] == accepted['sha256'],
                    'Exception belongs to another accepted basis')
            basis = 'operator_approved_one_time_exception'
        if stable(candidate):
            # ...and the 1.0 criteria were met with the release it follows (14 days), or the owner declared them.
            report = readiness_report(root, policy.get('readiness_report'), previous,
                                      (record.get('ha_install_record') or {}).get('finished_at'))
            if '_declaration' in report or declared_checks is not None:
                require(declaration is not None, 'An owner-declared stable release needs stable_declaration in the policy')
                require(declaration['tag'] == candidate and declaration['follows'] == previous,
                        'The stable declaration belongs to another release (one declaration per stable tag)')
                require(declaration['readiness_report'] == {'path': policy['readiness_report'].get('report'),
                                                            'sha256': policy['readiness_report'].get('sha256')}
                        and report.get('_declaration', declaration)['file'] == declaration['file'],
                        'The stable declaration binds another readiness report')
                require(basis == 'accepted_previous_release', 'A stable release never uses an exception')
                basis = 'owner_declared_stable'
                window = utc_time(report['to'], 'readiness end') - utc_time(report['from'], 'readiness start')
                owner_declared = {'declaration': declaration['file'], 'tag': declaration['tag'],
                                  'follows': declaration['follows'], 'statements': declaration['statement_texts'],
                                  'declared_criteria': report.get('_declared', []),
                                  'declared_receipt_checks': declared_checks or [],
                                  'readiness_window_days': round(window.total_seconds() / 86400, 2)}
    ready = accepted is not None and pending is None
    if plan is not None:
        ready = ready and accepted['tag'] in {plan.get('previous_published_tag'), plan.get('planned_tag')}
    result = {'result': 'PASS', 'accepted': accepted['tag'] if accepted else None,
              'pending': pending, 'successor_ready': ready,
              'physical_test_performed_by_verifier': False}
    if basis is not None:
        result['publication_basis'] = basis
    if owner_declared is not None:
        result['owner_declaration'] = owner_declared
    if declared_checks is not None:
        result['accepted_evidence'] = 'ha_history'
        result['accepted_declared_checks'] = declared_checks
    if declaration is not None:
        result['stable_declaration'] = {'declaration': declaration['file'], 'tag': declaration['tag']}
    if candidate is not None:
        result['previous_published_checked'] = published is not None
    return result


def main(argv=None, fetch=fetch_published):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--candidate')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--published-file', help='saved GitHub release list (or a JSON list of tags) instead of the API')
    source.add_argument('--offline', action='store_true',
                        help='skip the comparison of previous_published_tag with the published releases (explicit)')
    parser.add_argument('--repository', default=os.environ.get('GITHUB_REPOSITORY') or DEFAULT_REPOSITORY)
    args = parser.parse_args(argv)
    if args.candidate is None and (args.published_file or args.offline):
        parser.error('--published-file and --offline belong to --candidate')
    root = Path(__file__).resolve().parents[1]
    published = None
    if args.candidate is not None and not args.offline:
        try:
            if args.published_file:
                published = json.loads(Path(args.published_file).read_text(encoding='utf-8'))
                require(isinstance(published, list), 'The release catalog is not a list')
            else:
                published = fetch(args.repository, os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN'))
        except (OSError, ValueError) as error:  # URLError, HTTPError, timeouts, bad JSON: fail closed
            print(f'FAIL cannot read the published releases of {args.repository} ({type(error).__name__}: {error}); '
                  'the previous release cannot be checked. Use --offline only when you mean to skip that check.',
                  file=sys.stderr)
            return 1
    elif args.offline:
        print('WARNING --offline: previous_published_tag is not compared with the published releases', file=sys.stderr)
    print(json.dumps(verify(root, json.loads((root / POLICY).read_text()), args.candidate, published)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
