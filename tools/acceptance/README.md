# Acceptance kit

The kit that records an attended update of an E32 on the Home Assistant route: what was
installed, that it is the published release, that nothing the owner had set was lost, and that
the boiler control came back in the documented safe way. It ends in the acceptance receipt that
`scripts/verify_e32_update_gate.py` demands before the next release (`HA-UPDATE-ACCEPTANCE-BETA19.md`
lists the fourteen checks; this kit is how they are filled in with evidence).

It reads, it does not change. The E32 and Home Assistant are only read (two extra POSTs on the E32,
see the rules below), nothing is installed by these scripts, and nothing is committed or pushed.
The owner presses Install once, in Home Assistant.

## Files

| File | Use |
| --- | --- |
| `install-config.json` | The release and the installation: tags, integration versions, update entity, LAN addresses, MQTT prefix. Change this file for the next release, or give the same names as arguments (`--tag` and so on). |
| `acceptance.py` | Shared helpers and the pure evaluators. No release is written in the code. |
| `e32client.py` | The bounded E32 client: GETs, one `POST /auth/login` per session. |
| `capture_preinstall.py` | Before the install, two stages: `--stage ha-baseline` and `--stage e32`. |
| `capture_post.py` | After the install, run twice (and `--post-only` when there was no pre-install capture). |
| `capture_independent.py` | A second, separate check with its own code. It does not import the other modules. |
| `write_receipt.py` | Builds the receipt from the verified folders; optionally writes it and the gate. |
| `mqtt_listen.py` | The read-only MQTT listener the post capture starts. |
| `INSTALL-STEPS.nl.md` | The steps for the owner on the day, in Dutch. |
| `test_receipt.py`, `test_capture_smoke.py` | Offline tests (no device, no network). They run in CI `gates`. |

Git-ignored and never committed: `ha-token.txt` and every capture folder (put them under `out/`).

## Rules

- **E32:** one web session at a time (the E32 has 4 and Home Assistant needs one for the update). The
  scripts always sign out, also after an error. Only a LAN address is accepted. The only POSTs are
  `/auth/login`, the passphrase-less `/config/backup` export and `/auth/logout`.
- **Passwords:** the E32 password comes from `OT_E32_PASSWORD` or a prompt, `--factory-password` stands for the
  public factory default. The MQTT login comes from `OT_MQTT_USER` / `OT_MQTT_PASSWORD` or a prompt and travels to
  the listener on its stdin. Neither is ever put on a command line, in a file, or (after the login) in the
  environment. They are never read from Home Assistant's storage. No file of the kit may contain a secret.
- **Home Assistant:** GET only, only the configured LAN address, with the long-lived access token in
  `tools/acceptance/ha-token.txt` (Profile > Security > Long-lived access tokens). Nothing is posted to it.
- **GitHub:** anonymous.
- `--dry-run` on every script prints what it would request and touches nothing.
- Exit code 2 means a check failed. From the pre-install capture that means: **do not press Install.**
- A check in the receipt is true only when captured evidence shows it. Otherwise it stays false, the status
  is `INCOMPLETE` and the gap is listed under `limits`. Never edit a receipt by hand.

## Install day (Checklist B)

Run everything from the repository root (PowerShell on the laptop in the home network). `<UTC>` is a time stamp
such as `20261108T0905Z`. `OUT=out/install-rc4` is only an example: use one folder per install.

```text
 1  [assistant]  Anonymous preflight: the E32 release and the HA release are published (not drafts), the tag CI runs are green.
 2  [owner]      Home Assistant backup: Settings > System > Backups > Create backup now.
 3  [assistant]  python -I tools/acceptance/capture_preinstall.py --stage ha-baseline --out OUT/ha-baseline-<UTC>
                 (HA still runs the old integration; no E32 contact. Exit 2: stop.)
 4  [owner]      HACS: download the new integration version, restart Home Assistant. Exactly one OpenThermostat entry.
 5  [assistant]  python -I tools/acceptance/capture_preinstall.py --stage e32 --baseline OUT/ha-baseline-<UTC> --out OUT/preinstall-<UTC>
                 (the owner types the E32 password in the capture window; exit 2 = do not press Install)
 6  [owner]      Firmware entity: check that it offers the new tag, press Install ONCE, say the time.
 7  [assistant]  python -I tools/acceptance/capture_post.py --preinstall OUT/preinstall-<UTC> --out OUT/post1-<UTC> --mqtt-user <user>
 8  [owner]      Repairs: choose a new E32 password if asked, then confirm the takeover again.
 9  [assistant]  python -I tools/acceptance/capture_post.py --preinstall OUT/preinstall-<UTC> --out OUT/post2-<UTC> --mqtt-user <user>
                 (at least 600 s after the restart)
10  [assistant]  python -I tools/acceptance/capture_independent.py --out OUT/independent-<UTC> --preinstall-backup OUT/preinstall-<UTC>/backup
11  [assistant]  python -I tools/acceptance/write_receipt.py --preinstall OUT/preinstall-<UTC> --obs OUT/post1-<UTC> --obs OUT/post2-<UTC> \
                     --independent OUT/independent-<UTC> --receipt-out OUT/receipt.json
12  [assistant]  After PASS: the same with --write --apply-gate, then python3 -B scripts/verify_e32_update_gate.py,
                 python tools/dev/refresh_beta19_inventory.py . --apply, python scripts/verify_beta_release_inventory.py, commit.
                 No push without the owner.
```

What each step records:

- **Pre-install, stage `ha-baseline`** (before the integration is upgraded): the GitHub releases, the update entity,
  the one config entry, the integration version, the entity counts and states (to prove "no new duplicate or stale
  entities"). No E32 contact.
- **Pre-install, stage `e32`** (new integration installed, before Install): the same again, the upgrade against the
  baseline, `firmware.bin` and `e32v2-update.json` against each other and against GitHub's digest and size and the
  app descriptor, then one E32 session: identity, health, heating state, the password state, what was learned, every
  settings route and program, the passphrase-less export, `backup/BACKUP-MANIFEST.json` and `CAPTURE-MANIFEST.json`.
- **Post** (twice): the update entity with `last_install` and its history since the pre-install capture (one
  `in_progress` episode), the diagnostics, the states against the baseline, the heat-request sensor's `control`
  history, the E32 identity and health, the settings against the pre-install backup (schema additions and volatile
  Bluetooth readings ignored), and the MQTT listener for at least 130 s (availability, heartbeat every 60 s, uptime
  rising, disconnect counters steady). Post 1 comes right after Home Assistant shows the new version, post 2 at least
  600 s after the restart.
- **Independent:** the E32, Home Assistant and GitHub once more, with separate code and its own manifest; the settings
  against the pre-install backup files.
- **Receipt:** the fourteen gate checks, plus `ha_upgraded_with_one_entry`, `no_new_duplicate_or_stale_entities` and
  `takeover_reconfirmed`. The observations must come from the boot the install produced: the boot instant (time of the
  reading minus uptime) is the same in all of them and lies between a minute before the install started and five minutes
  after it ended. A PASS receipt is run through `home_assistant_acceptance()` of the repository before it is written.

## An install without a pre-install capture

`capture_post.py --post-only` and `write_receipt.py --post-only` record what can still be read and say what cannot.
Substitute evidence counts only when it is named, and every one is listed under `limits`:

- `--history-since <UTC>`: the Home Assistant recorder history to read (install actions, the offer before the install,
  the heat-request sensor's control phases). The recorder keeps about 10 days by default.
- `--pre-backup <file>` (and `--pre-backup-at <UTC>` if its `created` field has no time): an E32 settings export from
  before the install.
- `--owned-before yes|no`: whether the E32 controlled the boiler before the update.

Without them `backup_verified`, `settings_programs_bindings_preserved` and `control_state_safe_after_restart` stay
false. The two Home Assistant upgrade checks cannot be proven after the fact at all. Expect `INCOMPLETE`.

## MQTT listener

`mqtt_listen.py` needs `paho-mqtt`. With `paho` importable the post capture runs it with the same Python. On Windows
without it, the capture runs it inside WSL with `wsl_python` (default `~/venvs/ha/bin/python`, set it in the
configuration or with `--wsl-python`). `--no-mqtt` skips it; the MQTT checks then stay false.

## Tests

```text
python -I -m unittest discover -s tools/acceptance -p "test_*.py"
```

They build capture folders the way the scripts write them, run the receipt writer, and check that a PASS receipt passes
the repository's gate (`home_assistant_acceptance`, `verify()` on a throwaway root, `verify_accepted_update_path.accepted_source`)
and that every missing piece of evidence leaves the receipt `INCOMPLETE`. `OT_ACCEPTANCE_REPO` points them at another worktree.
