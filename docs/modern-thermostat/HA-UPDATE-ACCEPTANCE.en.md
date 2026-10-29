# Accepting an E32 update installed through Home Assistant

Since beta.19 the official way to update the E32 is the **Firmware** update
entity of the Home Assistant integration (`firmware_update.py`), the same way
ESPHome devices are updated. Home Assistant reads the GitHub release list,
downloads `firmware.bin`, checks that its SHA-256 equals GitHub's asset digest,
that its size matches and that the image carries the version marker of that
release, and only then uploads it to the E32 over the local network (`/ota`).
The E32 itself does not connect to GitHub.

A successor release (and every stable release, such as `v1.0.0-e32v2`) is only
published after one real update of the previous release was accepted. This page
describes how one update on the Home Assistant route is accepted, so that
`scripts/verify_e32_update_gate.py` accepts it as physical evidence
(`method: home_assistant`). The older route where the E32 downloads the release
itself (`method: native_github`) is still accepted with its own evidence.

The verifier only checks that the evidence is complete and consistent. It
never installs anything and does not replace the observations below.

## Version tags

| Kind | Firmware tag | Home Assistant tag | GitHub |
| --- | --- | --- | --- |
| Pre-release | `v0.1.0-e32v2-beta.19`, `v1.0.0-e32v2-rc.1` | `ha-v0.4.0b11`, `ha-v1.0.0rc1` | Pre-release |
| Stable | `v1.0.0-e32v2` | `ha-v1.0.0` | Release |

Order from old to new: alpha < beta < rc < stable within one version number,
then the version number: `v0.1.0-e32v2-beta.19` < `v1.0.0-e32v2-rc.1` <
`v1.0.0-e32v2` < `v1.0.1-e32v2-beta.1`. Home Assistant (like the E32's own
catalog) never offers an installation a less mature channel than the one it
runs: an E32 on 1.0.0 is offered 1.0.1, not 1.1.0-beta.1.

## One accepted update, step by step

1. **Before the update**
   - The release is published on GitHub (not a draft); a stable tag is not
     marked as a pre-release. Save the release as the API returns it
     (`tag_name`, `draft`, `prerelease`, `published_at` and the `firmware.bin`
     asset with `name`, `size`, `digest`).
   - The release preflight passed for exactly this tag.
   - Make a settings backup of the E32 (network, rooms, programs, Bluetooth
     sensors) and keep its manifest; it is compared after the update.
   - Note the update entity's state: `installed_version` (the old release) and
     `latest_version` (must be exactly the new tag), and the versions of the
     integration and Home Assistant Core.
2. **Install once.** Press **Install** on the E32's Firmware entity once. Do
   not retry: a second install means a new acceptance.
3. **During the install** Home Assistant downloads, verifies and uploads the
   image, waits for the E32 to restart and checks that it reports the new
   version. A mismatching digest, size or marker is never uploaded.
4. **After the install**
   - The update entity shows the new version as installed.
   - Copy the entity's `last_install` attribute (Developer tools → States;
     it is kept over a Home Assistant restart). It holds the tag, the old
     version, the SHA-256 and size, start and end time (UTC), duration, the result
     (`installed`), the number of uploads (1) and the identity the E32 reported
     after its restart (version, source commit, web hash, ELF hash). It holds no
     address or password.
   - Read `/status/version`, `/updates/status` and the uptime on the E32 at least twice,
     the last time at least 10 minutes after the restart: the same version,
     `boot_pending: false`, uptime increasing (no restart in between).
   - Compare the settings, programs and Bluetooth bindings with the backup.
   - Check that the heating is in the documented state after a restart: in
     shadow mode unchanged; in active mode the E32 asks for the "thermostat
     disconnected" confirmation again (it is cleared by a firmware change) and
     keeps frost protection.
5. **Independent check.** A second, separate capture (another person or tool,
   reading the E32 and Home Assistant directly) confirms version, identity and
   settings. Its receipt is a different file from the installer's capture.
6. **Record and bind.** Write the receipt (below) to
   `docs/modern-thermostat/update-acceptance/e32-<release>-<date>.json`, put
   its SHA-256 in `docs/modern-thermostat/E32-UPDATE-GATE.json` under
   `accepted` and run `python3 scripts/verify_e32_update_gate.py`.

## Receipt (`method: home_assistant`)

All checks must be `true` and all identities lowercase hex. Times are UTC in
the form `2026-10-30T09:00:00Z`.

| Field | Meaning |
| --- | --- |
| `schema`, `status`, `tag`, `method` | `1`, `PASS`, the installed tag, `home_assistant` |
| `checks` | `public_release_exact`, `fresh_preflight_passed`, `backup_verified`, `single_ha_install_action`, `ha_download_digest_size_marker_verified`, `local_upload_accepted`, `new_boot_observed`, `installed_version_source_elf_web_exact`, `boot_confirmed`, `stable_uptime_observed`, `settings_programs_bindings_preserved`, `control_state_safe_after_restart`, `ha_entity_reports_new_version`, `independent_postcheck_passed` |
| `github_release` | The release as read from GitHub: `tag_name` = `tag`, `draft: false`, `prerelease` false only for a stable tag, `published_at`, `asset` {`name: firmware.bin`, `size`, `digest: sha256:<firmware_sha256>`} |
| `firmware_sha256`, `firmware_bytes` | SHA-256 and size of the installed `firmware.bin` (equal to the GitHub asset) |
| `source_commit`, `web_sha256`, `elf_sha256` | Identity the E32 reports after the restart |
| `ha_entity_id` | The update entity, e.g. `update.open_thermostat_firmware` |
| `ha_installed_version_before`, `ha_latest_version_before` | Older installed release; the offered release (= `tag`) |
| `ha_installed_version_after` | `tag` |
| `install_actions` | `1` |
| `ha_integration_version`, `ha_core_version` | e.g. `0.4.0b11`, `2026.10.4` |
| `ha_install_record` | The `last_install` attribute, unchanged: `result: installed`, `uploads: 1`, same tag, old version, SHA-256, size and reported identity; started after publication, duration at most 15 minutes |
| `observations` | At least two E32 reads after the install: `at_utc`, `uptime_seconds` (strictly increasing, last ≥ 600), `boot_pending: false`, `version` = `tag` |
| `installer_receipt_sha256`, `independent_receipt_sha256`, `backup_manifest_sha256` | Hashes of the installer's capture, the separate independent capture and the backup manifest |

Further fields (limits, notes, the Home Assistant capture itself) may be added;
they do not weaken the checks above.

## What the gate then allows

- The next pre-release once the accepted release is the previously published
  one (or with a hash-bound owner exception for one beta).
- A **stable** release only when the accepted predecessor was installed on this
  Home Assistant route and is exactly the previously published release; an
  exception cannot be used for a stable release.
