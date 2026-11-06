"""Build the acceptance receipt (checklist section 7) from evidence only; optionally write it and the gate.

Each of the fourteen gate checks (verify_e32_update_gate.HA_REQUIRED) is true only when the captured evidence
shows it; otherwise it stays false, the status stays INCOMPLETE and the gap is listed under limits. The kit adds
three checks of its own that a PASS also needs (under "extra_checks"):
  ha_upgraded_with_one_entry          the Home Assistant integration went from ha_previous_version to ha_version
                                      and kept the one loaded config entry
  no_new_duplicate_or_stale_entities  no _2-style IDs, no new "restored" (stale) entities, no new duplicate groups
  takeover_reconfirmed                the E32 controlled the boiler before: it does again after the owner's
                                      re-confirmation (else: it stayed in shadow)
and records, without gating, the password state (factory password replaced?) and whether what the E32 had
learned survived the update. The observations must come from the boot that the install produced (the boot
instant, observation time minus uptime, is the same in all of them and lies in the install window: R5-08).
A PASS receipt is also run through scripts/verify_e32_update_gate.py's home_assistant_acceptance() before it is
written (imported read-only from --repo: the source is compiled in memory, no __pycache__ is written there).

--post-only builds a receipt from post observations made with capture_post.py --post-only (an install that had no
pre-install capture). The three checks that need evidence from before the install (backup_verified,
settings_programs_bindings_preserved, control_state_safe_after_restart) stay false unless the observations name
substitute evidence (a pre-install export, the recorder history, whether the E32 controlled the boiler); every
substitute is listed under limits. The two Home Assistant upgrade checks cannot be proven that way and are listed
as gaps. Expect INCOMPLETE.

Usage:
  python -I write_receipt.py --preinstall <pre> --obs <post1> --obs <post2> [...] --independent <indep>
         [--repo <worktree with scripts/verify_e32_update_gate.py>] [--ci-json <file>] [--local-check-log <file>]
         [--installed-by owner|assistant]                          # print only
     ... --receipt-out <file>     # write the receipt to that file (outside any repository; tests, review)
     ... --write                  # write <repo>/docs/modern-thermostat/update-acceptance/e32-<stage><n>-<YYYYMMDD>.json
     ... --write --apply-gate     # and, only for PASS: accepted <- this receipt, pending_tag null, exception
                                  # removed, then run verify_e32_update_gate.py and verify_beta_release_inventory.py
     ... --dry-run                # print what would be read, requested and written; nothing else
  python -I write_receipt.py --post-only --obs <post> [...] --independent <indep> ...
  python -I write_receipt.py --evidence ha-history --history <saved export> [--history <another>]
         --declaration <the owner's stable declaration, a path in --repo> [--github-release <saved release or catalog>]
         [--ci-json <file>] [--uptime-entity <sensor>] [--integration-entity <update entity>] [--repo <worktree>]
         [--receipt-out <file>] [--write] [--dry-run]
Repository files only change with --write / --apply-gate; nothing is committed or pushed.

--evidence ha-history builds the receipt of an install that was made through the Home Assistant update entity
WITHOUT the capture, from saved Home Assistant recorder history only (the answers of /api/history/period, full
rows for the update entities): the E32 Firmware update entity (offer, last_install, installed_version), the
device-uptime sensor (the restart and the stable boot after it) and the integration's own update entity (its
version at the install). Nothing is requested: no Home Assistant, no E32, no GitHub. The facts are derived with the
gate's own ha_history_facts(), so the gate re-derives and compares them. The checks the history shows are measured
(true or false); the ones it cannot show (HISTORY_DECLARED) are recorded as "declared" with the reason, quoting the
owner's stable declaration (--declaration), never as true. A declaration whose statement is still the placeholder
"<OWNER STATEMENT>" keeps the receipt INCOMPLETE. --write copies the exports into
docs/modern-thermostat/update-acceptance/ha-history/ (byte for byte; from a saved release catalog only the one
release object), then writes the receipt; the gate is changed only by stable_declaration.py seal --apply-gate,
together with the owner's declaration that binds this receipt.
"""
import argparse
import json
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; this module is ours
import acceptance as acc  # noqa: E402

GATE_CHECKS = ('public_release_exact', 'fresh_preflight_passed', 'backup_verified', 'single_ha_install_action',
               'ha_download_digest_size_marker_verified', 'local_upload_accepted', 'new_boot_observed',
               'installed_version_source_elf_web_exact', 'boot_confirmed', 'stable_uptime_observed',
               'settings_programs_bindings_preserved', 'control_state_safe_after_restart',
               'ha_entity_reports_new_version', 'independent_postcheck_passed')
# What a post-only receipt cannot prove, however good the other evidence is.
POST_ONLY_GAPS = ('ha_upgraded_with_one_entry', 'no_new_duplicate_or_stale_entities')


def load_verifier(repo):
    """scripts/verify_e32_update_gate.py of `repo`, compiled in memory (read-only: no bytecode cache written)."""
    path = Path(repo) / 'scripts' / 'verify_e32_update_gate.py'
    module = types.ModuleType('verify_e32_update_gate')
    module.__file__ = str(path)
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return module


def ci_answers(cfg, tag):
    """The exact tag's commit (annotated tags dereferenced) and its GitHub Actions runs (anonymous API)."""
    ref = json.loads(acc.github(f'https://api.github.com/repos/{cfg.repository}/git/ref/tags/{tag}'))
    target = ref['object']
    if target['type'] == 'tag':
        target = json.loads(acc.github(target['url']))['object']
    commit = target['sha'] if target['type'] == 'commit' else None
    runs = json.loads(acc.github(f'https://api.github.com/repos/{cfg.repository}/actions/runs?head_sha={commit}&per_page=20'))
    return {'commit': commit, 'runs': [{k: r.get(k) for k in ('id', 'name', 'head_branch', 'event', 'status', 'conclusion',
                                                              'html_url', 'created_at')} for r in runs.get('workflow_runs', [])]}


def build(cfg, pre, obs_folders, ind, ci, local_logs=(), installed_by='owner', post_only=False):
    """The receipt record and its limits, from verified capture folders only."""
    limits = []
    ind = Path(ind).resolve()
    pre_summary = baseline = base_dir = None
    backup_files = 0
    observations_raw = []
    for folder in obs_folders:
        folder = Path(folder).resolve()
        acc.verify_manifest(folder, 'OBS-MANIFEST.json')
        observation = json.loads((folder / 'OBSERVATION.json').read_text(encoding='utf-8'))
        assert observation.get('tag') == cfg.tag, f'{folder} belongs to another release'
        assert observation.get('mode') == ('post_only' if post_only else 'full'), \
            f'{folder} was made {"with" if post_only else "without"} --post-only'
        observation['_folder'] = folder
        observations_raw.append(observation)
    assert observations_raw, 'no post observation'
    if not post_only:
        pre = Path(pre).resolve()
        acc.verify_manifest(pre, 'CAPTURE-MANIFEST.json')
        backup_files = acc.verify_manifest(pre / 'backup', 'BACKUP-MANIFEST.json')
        pre_summary = json.loads((pre / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
        assert pre_summary.get('kind') == 'installer_preinstall_capture' and pre_summary['tag'] == cfg.tag, \
            f'not a pre-install capture for {cfg.tag}'
        base_dir = Path(pre_summary['baseline']['folder'])
        acc.verify_manifest(base_dir, 'CAPTURE-MANIFEST.json')
        baseline_sha = acc.file_digest(base_dir / 'CAPTURE-MANIFEST.json')
        if baseline_sha != pre_summary['baseline']['manifest_sha256']:
            raise SystemExit('The ha-baseline capture changed after the pre-install capture referenced it')
        baseline = json.loads((base_dir / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    if not post_only:
        for observation in observations_raw:
            assert Path(observation['preinstall']).resolve() == pre, \
                f'{observation["_folder"]} belongs to another pre-install capture'
    observations_raw.sort(key=lambda o: o['observation']['at_utc'])
    first, final = observations_raw[0], observations_raw[-1]
    acc.verify_manifest(ind, 'INDEPENDENT-MANIFEST.json')
    ind_summary = json.loads((ind / 'INDEPENDENT-SUMMARY.json').read_text(encoding='utf-8'))
    assert ind_summary.get('tag') == cfg.tag, 'the independent check belongs to another release'
    installer_sha = (acc.file_digest(pre / 'CAPTURE-MANIFEST.json') if pre_summary
                     else acc.file_digest(first['_folder'] / 'OBS-MANIFEST.json'))
    independent_sha = acc.file_digest(ind / 'INDEPENDENT-MANIFEST.json')
    ind_checks = ind_summary.get('checks') or {}
    substitutes = {}
    for o in observations_raw:
        substitutes.update(o.get('substitutes') or {})

    def ok(observation, name):
        rows = [f for f in observation['findings'] if f['check'] == name]
        return bool(rows) and all(f['ok'] for f in rows)

    def every(name):
        return all(ok(o, name) for o in observations_raw)

    tag_runs = [r for r in ci['runs'] if r['head_branch'] == cfg.tag]
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
    owned = pre_summary['e32_before']['owned_boiler'] is True if pre_summary else final.get('owned_before')
    phases = [o['observation'].get('control_phase') for o in observations_raw]
    started = last_install.get('started_at') or '9999'
    history_waits = [row for o in observations_raw for sensor in (o.get('info') or {}).get('ha_control_history') or []
                     for row in sensor.get('sequence') or []
                     if row.get('control') == 'awaiting_confirmation' and str(row.get('at') or '') >= started]
    wait_seen = 'awaiting_reconfirm' in phases or bool(history_waits)
    export_compared = any((o.get('export') or {}).get('compared') for o in observations_raw)
    upgrade = (pre_summary or {}).get('ha_upgrade') or {}
    boot_ok, boot_detail = acc.boot_continuity([o['observation'] for o in observations_raw],
                                               last_install.get('started_at'), last_install.get('finished_at'))
    if not boot_ok:
        limits.append('The observations do not all belong to the boot of this install: ' + json.dumps(boot_detail))

    # The three checks that need evidence from before the install: from the capture, or named substitutes.
    if pre_summary:
        backup_verified = backup_files > 0 and any(e['file'] == 'config-backup-export.json' for e in json.loads(
            (pre / 'backup' / 'BACKUP-MANIFEST.json').read_text(encoding='utf-8'))['files'])
        settings_preserved = (every('e32.settings_programs_bindings_preserved') and export_compared
                              and ind_checks.get('settings_same_as_preinstall_backup') is True)
        before_version, latest_before = pre_summary['ha_before']['ha_installed_version_before'], \
            pre_summary['ha_before']['ha_latest_version_before']
        backup_sha = acc.file_digest(pre / 'backup' / 'BACKUP-MANIFEST.json')
    else:
        backup_at = substitutes.get('pre_backup_at')
        try:
            before_install = backup_at is not None and acc.stamp(backup_at) < acc.stamp(started)
        except ValueError:
            before_install = False
        backup_verified = bool(substitutes.get('pre_backup_sha256')) and before_install
        settings_preserved = (backup_verified and every('e32.settings_programs_bindings_preserved') and export_compared)
        before_version = last_install.get('from_version')
        latest_before = cfg.tag if every('ha.offered_before_install') else None
        backup_sha = substitutes.get('pre_backup_sha256')
        if not backup_verified:
            limits.append('backup_verified: no settings backup from before the install was named (--pre-backup) or '
                          'it is not older than the install start.')
        for name, text in (('history_since', 'the Home Assistant recorder history was read from {}'),
                           ('pre_backup', 'the settings were compared with the export {} (not with every route)'),
                           ('owned_before', 'whether the E32 controlled the boiler before the update is the '
                                            'installer\'s statement: {}')):
            if substitutes.get(name):
                limits.append('Substitute evidence: ' + text.format(substitutes[name]))
        limits.append('Post-only receipt: there is no pre-install capture. The installer receipt hash is the first '
                      'post observation; the backup hash is the named export.')

    mqtt_ok = (every('mqtt.availability_online') and every('mqtt.heartbeat_every_60s')
               and every('mqtt.heartbeat_counters_steady') and counters_steady)
    checks = {
        'public_release_exact': (release == first['github_release'] and release['draft'] is False
                                 and release['prerelease'] is cfg.expect_prerelease
                                 and all(o['github_release'] == release for o in observations_raw)
                                 and (release == pre_summary['github_release'] if pre_summary else True)
                                 and every('github.release_is_the_capture_one' if pre_summary else 'github.release_is_published')
                                 and every('github.firmware_digest_and_size')),
        'fresh_preflight_passed': preflight,
        'backup_verified': backup_verified,
        'single_ha_install_action': final['install_actions'] == 1 and last_install.get('uploads') == 1
                                    and every('ha.install_actions==1'),
        'ha_download_digest_size_marker_verified': ok(final, 'ha.last_install') and every('github.descriptor'),
        'local_upload_accepted': last_install.get('result') == 'installed' and last_install.get('uploads') == 1,
        'new_boot_observed': ok(first, 'e32.new_boot_after_install') and boot_ok,
        'installed_version_source_elf_web_exact': every('e32.version_source_elf_web_exact'),
        'boot_confirmed': every('e32.boot_confirmed'),
        'stable_uptime_observed': (len(observations_raw) >= 2 and all(b > a for a, b in zip(uptimes, uptimes[1:]))
                                   and isinstance(uptimes[-1], int) and uptimes[-1] >= 600 and boot_ok
                                   and every('mqtt.heartbeat_uptime_rising')
                                   and all(o['observation']['version'] == cfg.tag for o in observations_raw)),
        'settings_programs_bindings_preserved': settings_preserved,
        'control_state_safe_after_restart': (every('e32.control_state_safe') and ind_checks.get('control_state_safe') is True
                                             and owned is not None and (wait_seen or not owned) and mqtt_ok),
        'ha_entity_reports_new_version': every('ha.entity_reports_new_version'),
        'independent_postcheck_passed': ind_summary.get('passed') is True and independent_sha != installer_sha,
    }
    assert tuple(checks) == GATE_CHECKS, 'the receipt checks and verify_e32_update_gate.HA_REQUIRED diverged'
    takeover = ((phases[-1] == 'reconfirmed') if owned else (phases[-1] == 'shadow')) \
        and ind_checks.get('takeover_reconfirmed') is True
    if pre_summary:
        extra_checks = {
            'ha_upgraded_with_one_entry': (baseline['ha'].get('ha_integration_version') == cfg.ha_previous_version
                                           and upgrade.get('integration_version') == cfg.ha_version
                                           and upgrade.get('single_entry_kept') is True
                                           and every('ha.single_config_entry') and every('ha.integration_version')
                                           and all(o.get('ha_integration_version') == cfg.ha_version for o in observations_raw)
                                           and ind_checks.get('ha_one_config_entry') is True
                                           and ind_checks.get('ha_integration_version') is True),
            'no_new_duplicate_or_stale_entities': ((upgrade.get('entities') or {}).get('ok') is True
                                                   and every('ha.no_new_duplicate_or_stale_entities')),
            'takeover_reconfirmed': takeover,
        }
        gating_extras = dict(extra_checks)
    else:
        extra_checks = {name: None for name in POST_ONLY_GAPS}
        extra_checks['takeover_reconfirmed'] = takeover
        gating_extras = {'takeover_reconfirmed': takeover}
        for name in POST_ONLY_GAPS:
            limits.append(f'{name}: cannot be proven without a Home Assistant baseline and a pre-install capture.')
    passwords = [o['observation'].get('default_password') for o in observations_raw]
    password = {'before_update': pre_summary['e32_before']['password'].get('default_password') if pre_summary else None,
                'observations': passwords, 'independent': (ind_summary.get('e32') or {}).get('default_password'),
                'own_password_at_end': passwords[-1] is False and (ind_summary.get('e32') or {}).get('default_password') is False,
                'ha_issues': [(o.get('info') or {}).get('ha_issues') for o in observations_raw]}
    learned_first = ((first.get('info') or {}).get('learned') or {})
    learned = {'before_update': pre_summary['e32_before'].get('learned') if pre_summary else None,
               'first_observation': learned_first.get('summary'),
               'kept_over_update': learned_first.get('kept_over_update'),
               'started_fresh': learned_first.get('fresh') is True}

    for name, value in {**checks, **gating_extras}.items():
        if value is not True:
            limits.append(f'{name}: no evidence (see the observation findings).')
    if not counters_steady:
        limits.append(f'MQTT disconnect counters rose during the observation: {counters[0]} -> {counters[-1]}')
    if pre_summary and 'settings_same_as_preinstall_backup' not in ind_checks:
        limits.append('The independent check ran without --preinstall-backup.')
    if not export_compared:
        limits.append('No post observation compared the passphrase-less export (the E32 refused it while it had '
                      'the factory password); run a post capture after the password change.')
    if owned and not wait_seen:
        limits.append('No evidence of the documented wait after the restart (awaiting re-confirmation, frost only): '
                      'neither a post capture nor HA\'s heat-request history shows it.')
    if not password['own_password_at_end']:
        limits.append('The E32 still reports the factory password at the end (Repairs: "E32 still uses the default '
                      'password"); the E32 refuses every change but the hand-back until a new one is chosen.')
    if learned['kept_over_update'] is False:
        limits.append('What the E32 had learned did not all survive the update (a counter went down): '
                      'see learned.before_update and learned.first_observation.')

    status = 'PASS' if all(v is True for v in {**checks, **gating_extras}.values()) else 'INCOMPLETE'
    record = {
        'schema': 1, 'status': status, 'tag': cfg.tag, 'method': 'home_assistant',
        'acceptance_decision': 'ACCEPTED' if status == 'PASS' else 'NOT_ACCEPTED_PENDING_EVIDENCE',
        'checks': checks, 'github_release': release,
        'firmware_sha256': final['firmware_sha256'], 'firmware_bytes': final['firmware_bytes'],
        'source_commit': last_install.get('reported', {}).get('source_commit'),
        'web_sha256': last_install.get('reported', {}).get('web_sha256'),
        'elf_sha256': last_install.get('reported', {}).get('elf_sha256'),
        'ha_entity_id': final['ha_entity']['entity_id'],
        'ha_installed_version_before': before_version,
        'ha_latest_version_before': latest_before,
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
        'extra_checks': extra_checks,
        'details': {
            'mode': 'post_only' if post_only else 'full',
            'config': cfg.as_dict(),
            'boot': boot_detail,
            'ha_upgrade': ({'route': f'{cfg.hacs_repository}, version {cfg.hacs_tag}',
                            'baseline_manifest_sha256': baseline_sha,
                            'baseline_integration_version': baseline['ha'].get('ha_integration_version'),
                            'config_entries_before': baseline['ha'].get('config_entries'),
                            'config_entries_after': final.get('ha_config_entries'),
                            'entities_after_upgrade': upgrade.get('entities')} if pre_summary else None),
            'takeover': {'owned_before_update': owned, 'phases': phases, 'ha_control_waits_seen': len(history_waits),
                         'independent_phase': (ind_summary.get('e32') or {}).get('control_phase'),
                         'final_control': final.get('control')},
            'password': password, 'learned': learned, 'substitutes': substitutes,
            'gaps': sorted({gap for o in observations_raw for gap in o.get('gaps') or []}),
        },
        'limits': limits + [
            'The independent post-check is a separately written tool (capture_independent.py, own HTTP code, own '
            'folder and manifest), run by the same assistant session, not by a second person.',
            ('The single Install press on the Firmware entity was made by the owner, attended.' if installed_by == 'owner'
             else 'The single install action was sent by the assistant through the Home Assistant update.install '
                  'service with the owner\'s approval; last_install records one upload.'),
            'Physical boiler behaviour is not part of this acceptance beyond the E32\'s reported control state: after '
            'the restart the E32 waits for the owner\'s re-confirmation with frost protection only; after it, active '
            'control resumes on the stored plan.'],
    }
    return record, limits


# ------------------------------------------------------------------ evidence: the saved Home Assistant history

# Why each check that the recorder history cannot show is declared by the owner instead of measured (never "true").
HISTORY_DECLARED = {
    'public_release_exact': 'no saved GitHub release record was given (--github-release), so the published release '
                            'and its firmware.bin digest are not compared here',
    'fresh_preflight_passed': 'no saved CI answer for the exact tag was given (--ci-json)',
    'backup_verified': 'the install was made without the acceptance capture: no settings backup was taken before it, '
                       'and the history cannot show one',
    'boot_confirmed': 'the history has no boot_pending flag of the E32',
    'settings_programs_bindings_preserved': 'the history has no settings export from before and after the install',
    'control_state_safe_after_restart': 'the history export has no control-state entity of the E32',
    'independent_postcheck_passed': 'no independent post-check was run after the install',
}


def history_entity(series, wanted, suffix, label, test=None):
    """The entity to read: the given one, or the single one in the exports that ends in `suffix` (and passes test)."""
    if wanted:
        if wanted not in series:
            raise SystemExit(f'{label} {wanted} is not in the history exports')
        return wanted
    found = sorted(entity for entity, rows in series.items() if entity.endswith(suffix) and (test is None or test(rows)))
    if len(found) != 1:
        raise SystemExit(f'expected one {label} in the history exports, found {found or "none"}: name it explicitly')
    return found[0]


def repo_path(repo, path):
    """A path relative to the repository (with /) when the file is inside it, else the absolute path."""
    path = Path(path).resolve()
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def tag_commit(repo, tag):
    """The commit of a tag in the repository (annotated tags dereferenced), or None when git cannot tell."""
    try:
        result = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--verify', '--quiet', f'refs/tags/{tag}^{{commit}}'],
                                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def build_from_history(cfg, gate, repo, histories, declaration_name, github=None, ci=None, uptime_entity=None,
                       integration_entity=None):
    """The receipt of an install made through the Home Assistant update entity without the capture, from the saved
    recorder history only. Every fact is derived with the gate's own ha_history_facts(); the checks the history
    shows are measured, the rest are 'declared' (by the owner's stable declaration, quoted here), never true.
    The gate's own rule is applied when every evidence file is inside the repository (as --write puts them)."""
    limits = []
    exports = [json.loads(Path(path).read_text(encoding='utf-8')) for path in histories]
    series = gate.ha_history_series(exports)
    entity = history_entity(series, cfg.entity_id, '_firmware', 'update entity')
    uptime = history_entity(series, uptime_entity, '_device_uptime', 'device-uptime sensor')
    integration = history_entity(
        series, integration_entity, '', 'integration update entity',
        lambda rows: rows[0]['entity_id'].startswith('update.') and any(
            cfg.hacs_repository in str((row.get('attributes') or {}).get('release_url') or '') for row in rows))
    facts = gate.ha_history_facts(series, entity, cfg.tag, uptime, integration)
    last = facts['ha_install_record']
    reported = last.get('reported') if isinstance(last.get('reported'), dict) else {}
    observations = facts['observations']
    boot_ok, boot_detail = acc.boot_continuity(observations, last.get('started_at'), last.get('finished_at'))
    uptimes = [item['uptime_seconds'] for item in observations]

    # The owner's declaration: his words, quoted; a placeholder keeps the receipt INCOMPLETE.
    declaration_path = (repo / declaration_name).resolve()
    if not declaration_path.is_relative_to(repo) or not declaration_path.is_file():
        raise SystemExit(f'{declaration_name}: the stable declaration must be a file in {repo}')
    declaration = json.loads(declaration_path.read_text(encoding='utf-8'))
    statements = [item.get('text') for item in ((declaration.get('owner') or {}).get('statements') or [])
                  if isinstance(item, dict)]
    real_statement = bool(statements) and not any(gate.placeholder(text) for text in statements)
    if not real_statement:
        limits.append('The owner statement in the declaration is still a placeholder: nothing is declared yet.')
    if declaration.get('follows') != cfg.tag:
        raise SystemExit(f'{declaration_name} follows {declaration.get("follows")}, not {cfg.tag}')

    release = None
    if github is not None:
        release = gate.release_summary(json.loads(Path(github).read_text(encoding='utf-8')), cfg.tag)
    commit = tag_commit(repo, cfg.tag)
    if commit is None:
        limits.append(f'git cannot resolve the tag {cfg.tag} here: the reported source commit is not compared with it.')
    tag_runs = [run for run in (ci or {}).get('runs', []) if run.get('head_branch') == cfg.tag]
    measured = {
        # None: no evidence given (declared); False: the evidence shows something else (never declared).
        'public_release_exact': None if release is None else (
            release['draft'] is False and release['prerelease'] is cfg.expect_prerelease
            and release['asset']['digest'] == 'sha256:' + str(last.get('sha256')) and release['asset']['size'] == last.get('size')),
        'fresh_preflight_passed': None if ci is None else (bool(ci.get('commit')) and bool(tag_runs) and all(
            run.get('status') == 'completed' and run.get('conclusion') == 'success' for run in tag_runs)),
        'single_ha_install_action': facts['install_actions'] == 1 and last.get('uploads') == 1,
        # firmware_update.py records "installed" only after verify_image() passed (GitHub digest, size, marker).
        'ha_download_digest_size_marker_verified': last.get('result') == 'installed' and bool(last.get('sha256')),
        'local_upload_accepted': last.get('result') == 'installed' and last.get('uploads') == 1,
        'new_boot_observed': boot_ok,
        'installed_version_source_elf_web_exact': (reported.get('version') == cfg.tag
                                                   and bool(reported.get('source_commit'))
                                                   and (commit is None or reported['source_commit'] == commit)
                                                   and bool(reported.get('web_sha256')) and bool(reported.get('elf_sha256'))),
        'stable_uptime_observed': (len(observations) >= 2 and all(b > a for a, b in zip(uptimes, uptimes[1:]))
                                   and uptimes[-1] >= 600 and boot_ok
                                   and all(item['version'] == cfg.tag for item in observations)),
        'ha_entity_reports_new_version': facts['ha_installed_version_after'] == cfg.tag,
    }
    checks, basis = {}, {}
    for name in GATE_CHECKS:
        value = measured.get(name)
        if name in gate.HA_HISTORY_MEASURED or value is not None:
            checks[name] = value is True
            basis[name] = 'measured from the saved history' if value is True else 'not shown by the saved history'
        else:
            checks[name] = 'declared'
            basis[name] = 'declared by the owner: ' + HISTORY_DECLARED[name]
    hours = round((uptimes[-1] if uptimes else 0) / 3600, 2)
    basis['boot_confirmed'] = basis['boot_confirmed'] + (
        f'; supporting, not proof: the uptime sensor rose without a restart for {hours} h after the install and the '
        'update entity kept reporting the release') if checks['boot_confirmed'] == 'declared' else basis['boot_confirmed']
    for name, value in checks.items():
        if value is False:
            limits.append(f'{name}: not shown by the saved history.')
    declared = sorted(name for name, value in checks.items() if value == 'declared')
    complete = all(value is not False for value in checks.values())
    status = 'PASS' if complete and real_statement else 'INCOMPLETE'
    decision = ('ACCEPTED_ON_OWNER_DECLARATION' if status == 'PASS' else
                'NOT_ACCEPTED_PENDING_EVIDENCE' if not complete else 'NOT_ACCEPTED_PENDING_OWNER_STATEMENT')
    files = [{'path': repo_path(repo, path), 'sha256': acc.file_digest(path), 'kind': 'ha_history',
              'entities': sorted(rows[0]['entity_id'] for rows in export)} for path, export in zip(histories, exports)]
    if github is not None:
        files.append({'path': repo_path(repo, github), 'sha256': acc.file_digest(github), 'kind': 'github_release'})
    inside = all(not Path(item['path']).is_absolute() for item in files)
    if not inside:
        limits.append('Evidence files outside the repository: the gate cannot bind them (use --write).')
    offered = [row for row in series[entity] if (row.get('attributes') or {}).get('latest_version') == cfg.tag]
    shown = [row for row in series[entity] if (row.get('attributes') or {}).get('installed_version') == cfg.tag]
    record = {
        'schema': 1, 'status': status, 'tag': cfg.tag, 'method': 'home_assistant', 'evidence': 'ha_history',
        'acceptance_decision': decision, 'checks': checks, 'check_basis': basis, 'declared_checks': declared,
        'owner_declaration': {'declaration': declaration_name, 'statements': statements},
        'evidence_files': files, 'github_release': release,
        'firmware_sha256': facts['firmware_sha256'], 'firmware_bytes': facts['firmware_bytes'],
        'source_commit': facts['source_commit'], 'web_sha256': facts['web_sha256'], 'elf_sha256': facts['elf_sha256'],
        'ha_entity_id': entity, 'uptime_entity_id': uptime, 'ha_integration_entity_id': integration,
        'ha_installed_version_before': facts['ha_installed_version_before'],
        'ha_latest_version_before': facts['ha_latest_version_before'],
        'ha_installed_version_after': facts['ha_installed_version_after'],
        'install_actions': facts['install_actions'], 'ha_integration_version': facts['ha_integration_version'],
        'ha_core_version': None, 'ha_install_record': last, 'observations': observations,
        'preflight': {'ci_commit': (ci or {}).get('commit'), 'tag_runs': tag_runs} if ci else None,
        'details': {
            'mode': 'ha_history',
            'offered_at': offered[0].get('last_changed') if offered else None,
            'first_reported_installed_at': shown[0].get('last_changed') if shown else None,
            'tag_commit': commit, 'boot': boot_detail,
            'uptime_hours_after_install': hours,
        },
        'limits': limits + [
            'Receipt from the saved Home Assistant recorder history only: there was no pre-install capture, no '
            'post-install observation of the E32 and no independent check. Every fact here is re-derived by the gate '
            'from the exports listed under evidence_files.',
            'The checks marked "declared" are not measured: the owner declared the release stable '
            f'({declaration_name}); check_basis says why each one cannot be shown.',
            'ha_core_version is not in the exports (null).',
            'The integration version is the installed_version of the integration\'s own update entity when the install '
            'started; the exports do not show the Home Assistant restart that loaded it.'],
    }
    if status == 'PASS' and inside:
        # The gate's rule, with this receipt's own declaration (its digests are bound later, when it is sealed).
        provisional = {'file': declaration_name, 'follows': declaration.get('follows'), 'statement_texts': statements,
                       'declared_receipt_checks': dict.fromkeys(declared, 'provisional'),
                       'evidence': [{'path': item['path'], 'sha256': item['sha256']} for item in files]}
        gate.ha_history_acceptance(repo, record, provisional)
    return record, limits


def history_main(parser, args):
    """--evidence ha-history: the receipt from the saved recorder history (offline; nothing is requested)."""
    if args.preinstall or args.post_only or args.obs or args.independent or args.local_check_log:
        parser.error('--evidence ha-history reads saved files only: no --preinstall, --post-only, --obs, --independent '
                     'or --local-check-log')
    if not args.history or not args.declaration:
        parser.error('--evidence ha-history needs --history <saved export> (one or more) and --declaration <the owner\'s '
                     'stable declaration, a path in --repo>')
    if args.apply_gate:
        parser.error('--apply-gate: a receipt from the history is accepted only together with the sealed owner '
                     'declaration; run tools/acceptance/stable_declaration.py seal ... --apply-gate after the readiness '
                     'report')
    cfg = acc.load_config(args, needs=('tag', 'previous_tag', 'entity_id'))
    repo = Path(args.repo).resolve()
    stem = acc.receipt_stem(cfg.tag)
    folder = repo / 'docs' / 'modern-thermostat' / 'update-acceptance' / 'ha-history'
    if args.dry_run:
        print('DRY RUN write_receipt.py --evidence ha-history: nothing is requested or written.')
        for line in [f'read the saved history {", ".join(args.history)}, the declaration {args.declaration}'
                     + (f', the GitHub release in {args.github_release}' if args.github_release else '')
                     + (f' and the CI answers in {args.ci_json}' if args.ci_json else ''),
                     'contact nothing (no Home Assistant, no E32, no GitHub)',
                     f'compile {repo / "scripts" / "verify_e32_update_gate.py"} in memory',
                     ('write ' + args.receipt_out) if args.receipt_out else 'write no receipt file',
                     (f'copy the evidence into {folder} and write {repo}/docs/modern-thermostat/update-acceptance/'
                      f'{stem}-<day>.json' if args.write else 'leave the repository unchanged'),
                     'leave the gate (stable_declaration.py seal --apply-gate binds the receipt)']:
            print('  would ' + line)
        return 0
    gate = load_verifier(repo)
    ci = json.loads(Path(args.ci_json).read_text(encoding='utf-8')) if args.ci_json else None
    histories = [Path(path).resolve() for path in args.history]
    github = Path(args.github_release).resolve() if args.github_release else None
    if args.write:
        # The evidence goes into the repository first (byte for byte; the GitHub release as the one release object),
        # so that the receipt names the files the gate reads and binds.
        folder.mkdir(parents=True, exist_ok=True)
        copies = []
        for path in histories:
            target = path if path.is_relative_to(repo) else folder / f'{stem}-{path.name}'
            if target != path:
                if target.exists() and target.read_bytes() != path.read_bytes():
                    raise SystemExit(f'{target} exists with other content; never overwritten')
                target.write_bytes(path.read_bytes())
            copies.append(target)
        histories = copies
        if github is not None and not github.is_relative_to(repo):
            raw = json.loads(github.read_text(encoding='utf-8'))
            rows = [row for row in (raw if isinstance(raw, list) else [raw])
                    if isinstance(row, dict) and row.get('tag_name') == cfg.tag]
            if len(rows) != 1:
                raise SystemExit(f'{github} has no single release {cfg.tag}')
            target = folder / f'{stem}-github-release.json'
            data = (json.dumps(rows[0], indent=2, ensure_ascii=False) + '\n').encode()
            if target.exists() and target.read_bytes() != data:
                raise SystemExit(f'{target} exists with other content; never overwritten')
            target.write_bytes(data)
            print('extracted', cfg.tag, 'from', github.name, acc.file_digest(github), 'to', target)
            github = target
    record, limits = build_from_history(cfg, gate, repo, histories, args.declaration, github, ci,
                                       args.uptime_entity, args.integration_entity)
    status = record['status']
    print(json.dumps({'status': status, 'acceptance_decision': record['acceptance_decision'], 'checks': record['checks'],
                      'declared_checks': record['declared_checks'], 'limits': limits,
                      'observations': record['observations'], 'install_actions': record['install_actions']}, indent=1,
                     ensure_ascii=False))
    text = (json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode()
    if args.receipt_out:
        Path(args.receipt_out).write_bytes(text)
        print('wrote', args.receipt_out, acc.digest(text))
    if args.write:
        day = record['observations'][-1]['at_utc'][:10].replace('-', '')
        receipt = repo / 'docs' / 'modern-thermostat' / 'update-acceptance' / f'{stem}-{day}.json'
        receipt.write_bytes(text)
        print('wrote', receipt, acc.file_digest(receipt))
        print('Next: the readiness report (tools/switchover/release_ready.py --stage final --history-file ... '
              '--declaration ...), then tools/acceptance/stable_declaration.py seal ... --apply-gate.')
    return 0 if status == 'PASS' else 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    acc.add_config_arguments(parser)
    parser.add_argument('--repo', default=str(acc.REPO), help='worktree with scripts/verify_e32_update_gate.py '
                                                              '(default: the worktree of this kit)')
    parser.add_argument('--preinstall', help='the pre-install capture folder (not with --post-only)')
    parser.add_argument('--post-only', action='store_true', help='the observations were made with capture_post.py --post-only')
    parser.add_argument('--obs', action='append')
    parser.add_argument('--independent')
    parser.add_argument('--evidence', choices=('capture', 'ha-history'), default='capture',
                        help='capture (the captures of this kit, the default) or ha-history (the saved recorder history only)')
    parser.add_argument('--history', action='append', default=[], help='a saved Home Assistant history export (ha-history)')
    parser.add_argument('--declaration', help="the owner's stable declaration, a path in --repo (ha-history)")
    parser.add_argument('--github-release', help='a saved GitHub release object or release catalog (ha-history)')
    parser.add_argument('--uptime-entity', help='the device-uptime sensor in the export (default: the one ending _device_uptime)')
    parser.add_argument('--integration-entity', help="the integration's own update entity in the export (default: found)")
    parser.add_argument('--local-check-log', action='append', default=[])
    parser.add_argument('--ci-json', help='Saved GitHub API answers instead of asking the API (offline runs)')
    parser.add_argument('--installed-by', choices=('owner', 'assistant'), default='owner')
    parser.add_argument('--receipt-out')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--apply-gate', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.evidence == 'ha-history':
        return history_main(parser, args)
    if args.history or args.declaration or args.github_release or args.uptime_entity or args.integration_entity:
        parser.error('--history, --declaration, --github-release, --uptime-entity and --integration-entity belong to '
                     '--evidence ha-history')
    if not args.obs or not args.independent:
        parser.error('the following arguments are required: --obs, --independent')
    if args.post_only == bool(args.preinstall):
        parser.error('give --preinstall <pre folder>, or --post-only for an install without one')
    cfg = acc.load_config(args, needs=('tag', 'previous_tag', 'ha_version', 'ha_previous_version'))
    repo = Path(args.repo).resolve()
    stem = acc.receipt_stem(cfg.tag)
    if args.dry_run:
        print('DRY RUN write_receipt.py: nothing is requested or written.')
        for line in [f'verify the manifests of {args.preinstall or "(no pre-install capture: --post-only)"}'
                     + (' (and its ha-baseline), ' if args.preinstall else ', ') + ', '.join(args.obs)
                     + f' and {args.independent}',
                     (f'read the CI answers from {args.ci_json}' if args.ci_json else
                      f'GitHub GET api.github.com/repos/{cfg.repository}/git/ref/tags/{cfg.tag} (+ the tag object if '
                      'annotated) and /actions/runs?head_sha=<commit>'),
                     f'compile {repo / "scripts" / "verify_e32_update_gate.py"} in memory for a PASS receipt',
                     ('write ' + args.receipt_out) if args.receipt_out else 'write no receipt file',
                     (f'write {repo}/docs/modern-thermostat/update-acceptance/{stem}-<day>.json' if args.write else
                      'leave the repository unchanged'),
                     ('update E32-UPDATE-GATE.json and run the two verifiers' if args.apply_gate else 'leave the gate')]:
            print('  would ' + line)
        return 0
    ci = json.loads(Path(args.ci_json).read_text(encoding='utf-8')) if args.ci_json else ci_answers(cfg, cfg.tag)
    local_logs = []
    for path in args.local_check_log:
        text = Path(path).read_text(encoding='utf-8', errors='replace')
        local_logs.append({'file': Path(path).name, 'sha256': acc.file_digest(path), 'overall_pass': 'OVERALL PASS' in text})
    record, limits = build(cfg, args.preinstall, args.obs, args.independent, ci, local_logs, args.installed_by,
                           post_only=args.post_only)
    status = record['status']
    if status == 'PASS':
        load_verifier(repo).home_assistant_acceptance(record)  # raises on any rule the gate would refuse
    print(json.dumps({'status': status, 'checks': record['checks'], 'extra_checks': record['extra_checks'],
                      'limits': limits, 'observations': record['observations'],
                      'install_actions': record['install_actions']}, indent=1))
    text = (json.dumps(record, indent=2, ensure_ascii=False) + '\n').encode()
    if args.receipt_out:
        Path(args.receipt_out).write_bytes(text)
        print('wrote', args.receipt_out, acc.digest(text))
    if not args.write:
        return 0 if status == 'PASS' else 2
    day = record['observations'][-1]['at_utc'][:10].replace('-', '')
    receipt = repo / 'docs' / 'modern-thermostat' / 'update-acceptance' / f'{stem}-{day}.json'
    receipt.write_bytes(text)
    receipt_sha = acc.file_digest(receipt)
    print('wrote', receipt, receipt_sha)
    if args.apply_gate:
        if status != 'PASS':
            raise SystemExit('Gate unchanged: the receipt is not PASS')
        gate_path = repo / 'docs' / 'modern-thermostat' / 'E32-UPDATE-GATE.json'
        gate = json.loads(gate_path.read_text(encoding='utf-8'))
        gate['accepted'] = {'tag': cfg.tag, 'receipt': receipt.relative_to(repo).as_posix(), 'sha256': receipt_sha}
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
