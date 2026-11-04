"""Build the rc.2 acceptance receipt (checklist section 7) from evidence only; optionally write it and the gate.

Each of the fourteen gate checks (verify_e32_update_gate.HA_REQUIRED) is true only when the captured evidence
shows it; otherwise it stays false, the status stays INCOMPLETE and the gap is listed under limits. rc.2 adds
three checks of its own that a PASS also needs (under "rc2_checks"):
  ha_migrated_with_one_entry          HA 0.4.0b15 (manual) -> 1.0.0rc2 (HACS) kept the one loaded config entry
  no_new_duplicate_or_stale_entities  no _2-style IDs, no new "restored" (stale) entities, no new duplicate groups
  takeover_reconfirmed                the E32 controlled the boiler before: it does again after the owner's
                                      re-confirmation (else: it stayed in shadow)
and records, without gating, the password state (factory password replaced?) and whether what was learned
started fresh (rc.2 is the first firmware that keeps it). A PASS receipt is also run through
scripts/verify_e32_update_gate.py's home_assistant_acceptance() before it is written (imported read-only: the
source is compiled in memory, no __pycache__ is written into that worktree).

Usage:
  python -I write_rc2_receipt.py --preinstall <pre> --obs <post1> --obs <post2> [...] --independent <indep>
         [--repo <worktree with scripts/verify_e32_update_gate.py>] [--ci-json <file>] [--local-check-log <file>]
         [--installed-by owner|assistant]                          # print only
     ... --receipt-out <file>     # write the receipt to that file (outside any repository; tests, review)
     ... --write                  # write <repo>/docs/modern-thermostat/update-acceptance/e32-rc2-<YYYYMMDD>.json
     ... --write --apply-gate     # and, only for PASS: accepted <- this receipt, pending_tag null, exception
                                  # removed, then run verify_e32_update_gate.py and verify_beta_release_inventory.py
     ... --dry-run                # print what would be read, requested and written; nothing else
Repository files only change with --write / --apply-gate; nothing is committed or pushed.
"""
import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; this module is ours
import rc2_acc as acc  # noqa: E402


def load_verifier(repo):
    """scripts/verify_e32_update_gate.py of `repo`, compiled in memory (read-only: no bytecode cache written)."""
    path = Path(repo) / 'scripts' / 'verify_e32_update_gate.py'
    module = types.ModuleType('verify_e32_update_gate')
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return module


def ci_answers(tag):
    """The exact tag's commit (annotated tags dereferenced) and its GitHub Actions runs (anonymous API)."""
    ref = json.loads(acc.github(f'https://api.github.com/repos/{acc.REPOSITORY}/git/ref/tags/{tag}'))
    target = ref['object']
    if target['type'] == 'tag':
        target = json.loads(acc.github(target['url']))['object']
    commit = target['sha'] if target['type'] == 'commit' else None
    runs = json.loads(acc.github(f'https://api.github.com/repos/{acc.REPOSITORY}/actions/runs?head_sha={commit}&per_page=20'))
    return {'commit': commit, 'runs': [{k: r.get(k) for k in ('id', 'name', 'head_branch', 'event', 'status', 'conclusion',
                                                              'html_url', 'created_at')} for r in runs.get('workflow_runs', [])]}


def build(pre, obs_folders, ind, ci, local_logs=(), installed_by='owner'):
    """The receipt record and the gating rc.2 checks, from verified capture folders only."""
    limits = []
    pre = Path(pre).resolve()
    ind = Path(ind).resolve()
    acc.verify_manifest(pre, 'CAPTURE-MANIFEST.json')
    backup_files = acc.verify_manifest(pre / 'backup', 'BACKUP-MANIFEST.json')
    pre_summary = json.loads((pre / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    assert pre_summary.get('kind') == 'installer_preinstall_capture' and pre_summary['tag'] == acc.TAG, 'not an rc.2 pre-install capture'
    base_dir = Path(pre_summary['baseline']['folder'])
    acc.verify_manifest(base_dir, 'CAPTURE-MANIFEST.json')
    baseline_sha = acc.file_digest(base_dir / 'CAPTURE-MANIFEST.json')
    if baseline_sha != pre_summary['baseline']['manifest_sha256']:
        raise SystemExit('The ha-baseline capture changed after the pre-install capture referenced it')
    baseline = json.loads((base_dir / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    observations_raw = []
    for folder in obs_folders:
        folder = Path(folder).resolve()
        acc.verify_manifest(folder, 'OBS-MANIFEST.json')
        observation = json.loads((folder / 'OBSERVATION.json').read_text(encoding='utf-8'))
        assert observation.get('tag') == acc.TAG and Path(observation['preinstall']).resolve() == pre, \
            f'{folder} belongs to another pre-install capture'
        observations_raw.append(observation)
    assert observations_raw, 'no post observation'
    observations_raw.sort(key=lambda o: o['observation']['at_utc'])
    first, final = observations_raw[0], observations_raw[-1]
    acc.verify_manifest(ind, 'INDEPENDENT-MANIFEST.json')
    ind_summary = json.loads((ind / 'INDEPENDENT-SUMMARY.json').read_text(encoding='utf-8'))
    assert ind_summary.get('tag') == acc.TAG, 'the independent check belongs to another release'
    installer_sha = acc.file_digest(pre / 'CAPTURE-MANIFEST.json')
    independent_sha = acc.file_digest(ind / 'INDEPENDENT-MANIFEST.json')
    backup_sha = acc.file_digest(pre / 'backup' / 'BACKUP-MANIFEST.json')
    ind_checks = ind_summary.get('checks') or {}

    def ok(observation, name):
        rows = [f for f in observation['findings'] if f['check'] == name]
        return bool(rows) and all(f['ok'] for f in rows)

    def every(name):
        return all(ok(o, name) for o in observations_raw)

    tag_runs = [r for r in ci['runs'] if r['head_branch'] == acc.TAG]
    preflight = bool(ci.get('commit')) and bool(tag_runs) and all(r['status'] == 'completed' and r['conclusion'] == 'success'
                                                                  for r in tag_runs)
    if not preflight:
        limits.append('No successful CI run found for the exact tag commit.')

    last_install = final['ha_entity']['last_install'] or {}
    release = first['github_release']
    uptimes = [o['observation']['uptime_seconds'] for o in observations_raw]
    counters = [o['observation'].get('mqtt_counters') or {} for o in observations_raw]
    counters_steady = all(counters[0].get(k) == counters[-1].get(k)
                          for k in ('mqtt_stalled_disconnects', 'mqtt_socket_error_disconnects'))
    owned = pre_summary['e32_before']['owned_boiler'] is True
    phases = [o['observation'].get('control_phase') for o in observations_raw]
    started = last_install.get('started_at') or '9999'
    history_waits = [row for o in observations_raw for sensor in (o.get('info') or {}).get('ha_control_history') or []
                     for row in sensor.get('sequence') or []
                     if row.get('control') == 'awaiting_confirmation' and str(row.get('at') or '') >= started]
    wait_seen = 'awaiting_reconfirm' in phases or bool(history_waits)
    export_compared = any((o.get('export') or {}).get('compared') for o in observations_raw)
    migration = pre_summary.get('ha_migration') or {}

    checks = {
        'public_release_exact': (release == pre_summary['github_release'] and release['draft'] is False
                                 and release['prerelease'] is True and every('github.release_is_the_capture_one')
                                 and every('github.firmware_digest_and_size')),
        'fresh_preflight_passed': preflight,
        'backup_verified': backup_files > 0 and any(e['file'] == 'config-backup-export.json' for e in json.loads(
            (pre / 'backup' / 'BACKUP-MANIFEST.json').read_text(encoding='utf-8'))['files']),
        'single_ha_install_action': final['install_actions'] == 1 and last_install.get('uploads') == 1
                                    and every('ha.install_actions==1'),
        'ha_download_digest_size_marker_verified': ok(final, 'ha.last_install') and every('github.descriptor'),
        'local_upload_accepted': last_install.get('result') == 'installed' and last_install.get('uploads') == 1,
        'new_boot_observed': ok(first, 'e32.new_boot_after_install'),
        'installed_version_source_elf_web_exact': every('e32.version_source_elf_web_exact'),
        'boot_confirmed': every('e32.boot_confirmed'),
        'stable_uptime_observed': (len(observations_raw) >= 2 and all(b > a for a, b in zip(uptimes, uptimes[1:]))
                                   and isinstance(uptimes[-1], int) and uptimes[-1] >= 600
                                   and all(o['observation']['version'] == acc.TAG for o in observations_raw)),
        'settings_programs_bindings_preserved': (every('e32.settings_programs_bindings_preserved') and export_compared
                                                 and ind_checks.get('settings_same_as_preinstall_backup') is True),
        'control_state_safe_after_restart': (every('e32.control_state_safe') and ind_checks.get('control_state_safe') is True
                                             and (wait_seen or not owned)
                                             and every('mqtt.availability_online') and every('mqtt.heartbeat_every_60s')
                                             and every('mqtt.heartbeat_counters_steady') and counters_steady),
        'ha_entity_reports_new_version': every('ha.entity_reports_new_version'),
        'independent_postcheck_passed': ind_summary.get('passed') is True and independent_sha != installer_sha,
    }
    rc2_checks = {
        'ha_migrated_with_one_entry': (baseline['ha'].get('ha_integration_version') == acc.HA_PREV_VERSION
                                       and migration.get('integration_version') == acc.HA_VERSION
                                       and migration.get('single_entry_kept') is True
                                       and every('ha.single_config_entry') and every('ha.integration_version')
                                       and all(o.get('ha_integration_version') == acc.HA_VERSION for o in observations_raw)
                                       and ind_checks.get('ha_one_config_entry') is True
                                       and ind_checks.get('ha_integration_version') is True),
        'no_new_duplicate_or_stale_entities': ((migration.get('entities') or {}).get('ok') is True
                                               and every('ha.no_new_duplicate_or_stale_entities')),
        'takeover_reconfirmed': ((phases[-1] == 'reconfirmed') if owned else (phases[-1] == 'shadow'))
                                and ind_checks.get('takeover_reconfirmed') is True,
    }
    passwords = [o['observation'].get('default_password') for o in observations_raw]
    password = {'before_update': pre_summary['e32_before']['password'].get('default_password'),
                'observations': passwords, 'independent': (ind_summary.get('e32') or {}).get('default_password'),
                'own_password_at_end': passwords[-1] is False and (ind_summary.get('e32') or {}).get('default_password') is False,
                'ha_issues': [(o.get('info') or {}).get('ha_issues') for o in observations_raw]}
    learned = {'before_update': pre_summary['e32_before'].get('learned'),
               'first_observation': ((first.get('info') or {}).get('learned') or {}).get('summary'),
               'started_fresh': ((first.get('info') or {}).get('learned') or {}).get('fresh') is True}

    for name, value in {**checks, **rc2_checks}.items():
        if value is not True:
            limits.append(f'{name}: no evidence (see the observation findings).')
    if not counters_steady:
        limits.append(f'MQTT disconnect counters rose during the observation: {counters[0]} -> {counters[-1]}')
    if 'settings_same_as_preinstall_backup' not in ind_checks:
        limits.append('The independent check ran without --preinstall-backup.')
    if not export_compared:
        limits.append('No post observation compared the passphrase-less export (the E32 refused it while it had '
                      'the factory password); run a post capture after the password change.')
    if owned and not wait_seen:
        limits.append('No evidence of the documented wait after the restart (awaiting re-confirmation, frost only): '
                      'neither a post capture nor HA\'s heat-request history shows it.')
    if not password['own_password_at_end']:
        limits.append('The E32 still reports the factory password at the end (Repairs: "E32 still uses the default '
                      'password"); rc.2 refuses every change but the hand-back until a new one is chosen.')
    if not learned['started_fresh']:
        limits.append('The first post capture does not show the self-tuning and learner starting fresh '
                      '(see rc2.learned.first_observation).')

    status = 'PASS' if all(v is True for v in {**checks, **rc2_checks}.values()) else 'INCOMPLETE'
    record = {
        'schema': 1, 'status': status, 'tag': acc.TAG, 'method': 'home_assistant',
        'acceptance_decision': 'ACCEPTED' if status == 'PASS' else 'NOT_ACCEPTED_PENDING_EVIDENCE',
        'checks': checks, 'github_release': release,
        'firmware_sha256': final['firmware_sha256'], 'firmware_bytes': final['firmware_bytes'],
        'source_commit': last_install.get('reported', {}).get('source_commit'),
        'web_sha256': last_install.get('reported', {}).get('web_sha256'),
        'elf_sha256': last_install.get('reported', {}).get('elf_sha256'),
        'ha_entity_id': final['ha_entity']['entity_id'],
        'ha_installed_version_before': pre_summary['ha_before']['ha_installed_version_before'],
        'ha_latest_version_before': pre_summary['ha_before']['ha_latest_version_before'],
        'ha_installed_version_after': final['ha_entity']['installed_version'],
        'install_actions': final['install_actions'],
        'ha_integration_version': final['ha_integration_version'], 'ha_core_version': final['ha_core_version'],
        'ha_install_record': last_install,
        'observations': [{k: o['observation'][k] for k in ('at_utc', 'version', 'boot_pending', 'uptime_seconds')}
                         for o in observations_raw],
        'installer_receipt_sha256': installer_sha, 'independent_receipt_sha256': independent_sha,
        'backup_manifest_sha256': backup_sha,
        'preflight': {'ci_commit': ci.get('commit'), 'tag_runs': tag_runs, 'local_check_logs': list(local_logs)},
        'mqtt_counters': {'first': counters[0], 'last': counters[-1]},
        'rc2_checks': rc2_checks,
        'rc2': {
            'ha_migration': {'route': f'HACS custom repository {acc.HACS_REPOSITORY}, version {acc.HACS_TAG}',
                             'baseline_manifest_sha256': baseline_sha,
                             'baseline_integration_version': baseline['ha'].get('ha_integration_version'),
                             'config_entries_before': baseline['ha'].get('config_entries'),
                             'config_entries_after': final.get('ha_config_entries'),
                             'entities_after_migration': migration.get('entities')},
            'takeover': {'owned_before_update': owned, 'phases': phases, 'ha_control_waits_seen': len(history_waits),
                         'independent_phase': (ind_summary.get('e32') or {}).get('control_phase'),
                         'final_control': final.get('control')},
            'password': password, 'learned': learned,
        },
        'limits': limits + [
            'The independent post-check is a separately written tool (capture_rc2_independent.py, own HTTP code, own '
            'folder and manifest), run by the same assistant session, not by a second person.',
            ('The single Install press on the Firmware entity was made by the owner, attended.' if installed_by == 'owner'
             else 'The single install action was sent by the assistant through the Home Assistant update.install '
                  'service with the owner\'s approval; last_install records one upload.'),
            'Physical boiler behaviour is not part of this acceptance beyond the E32\'s reported control state: after '
            'the restart the E32 waits for the owner\'s re-confirmation with frost protection only; after it, active '
            'control resumes on the stored plan.'],
    }
    return record, limits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', default=str(acc.RELEASE_WORKTREE))
    parser.add_argument('--preinstall', required=True)
    parser.add_argument('--obs', action='append', required=True)
    parser.add_argument('--independent', required=True)
    parser.add_argument('--local-check-log', action='append', default=[])
    parser.add_argument('--ci-json', help='Saved GitHub API answers instead of asking the API (offline runs)')
    parser.add_argument('--installed-by', choices=('owner', 'assistant'), default='owner')
    parser.add_argument('--receipt-out')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--apply-gate', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if args.dry_run:
        print('DRY RUN write_rc2_receipt.py: nothing is requested or written.')
        for line in [f'verify the manifests of {args.preinstall} (and its ha-baseline), ' + ', '.join(args.obs)
                     + f' and {args.independent}',
                     (f'read the CI answers from {args.ci_json}' if args.ci_json else
                      f'GitHub GET api.github.com/repos/{acc.REPOSITORY}/git/ref/tags/{acc.TAG} (+ the tag object if '
                      'annotated) and /actions/runs?head_sha=<commit>'),
                     f'compile {repo / "scripts" / "verify_e32_update_gate.py"} in memory for a PASS receipt',
                     ('write ' + args.receipt_out) if args.receipt_out else 'write no receipt file',
                     (f'write {repo}/docs/modern-thermostat/update-acceptance/e32-rc2-<day>.json' if args.write else
                      'leave the repository unchanged'),
                     ('update E32-UPDATE-GATE.json and run the two verifiers' if args.apply_gate else 'leave the gate')]:
            print('  would ' + line)
        return 0
    ci = json.loads(Path(args.ci_json).read_text(encoding='utf-8')) if args.ci_json else ci_answers(acc.TAG)
    local_logs = []
    for path in args.local_check_log:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
        local_logs.append({'file': Path(path).name, 'sha256': acc.file_digest(path), 'overall_pass': 'OVERALL PASS' in text})
    record, limits = build(args.preinstall, args.obs, args.independent, ci, local_logs, args.installed_by)
    status = record['status']
    if status == 'PASS':
        load_verifier(repo).home_assistant_acceptance(record)  # raises on any rule the gate would refuse
    print(json.dumps({'status': status, 'checks': record['checks'], 'rc2_checks': record['rc2_checks'],
                      'limits': limits, 'observations': record['observations'],
                      'install_actions': record['install_actions']}, indent=1))
    text = (json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode()
    if args.receipt_out:
        Path(args.receipt_out).write_bytes(text)
        print('wrote', args.receipt_out, acc.digest(text))
    if not args.write:
        return 0 if status == 'PASS' else 2
    day = record['observations'][-1]['at_utc'][:10].replace('-', '')
    receipt = repo / 'docs' / 'modern-thermostat' / 'update-acceptance' / f'e32-rc2-{day}.json'
    receipt.write_bytes(text)
    receipt_sha = acc.file_digest(receipt)
    print('wrote', receipt, receipt_sha)
    if args.apply_gate:
        if status != 'PASS':
            raise SystemExit('Gate unchanged: the receipt is not PASS')
        gate_path = repo / 'docs' / 'modern-thermostat' / 'E32-UPDATE-GATE.json'
        gate = json.loads(gate_path.read_text(encoding='utf-8'))
        gate['accepted'] = {'tag': acc.TAG, 'receipt': receipt.relative_to(repo).as_posix(), 'sha256': receipt_sha}
        gate['pending_tag'] = None
        gate.pop('publication_exception', None)
        gate_path.write_bytes((json.dumps(gate, indent=2) + '\n').encode())
        for script in ('verify_e32_update_gate.py', 'verify_beta_release_inventory.py'):
            # Repository scripts import their siblings, so they run without -I (trusted, our own source).
            result = subprocess.run([sys.executable, str(repo / 'scripts' / script)], cwd=repo,
                                    capture_output=True, text=True)
            print(script, result.returncode, (result.stdout or result.stderr).strip()[-600:])
        print('Next: refresh the release inventory (the gate and the new receipt changed), then commit both.')
    return 0 if status == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
