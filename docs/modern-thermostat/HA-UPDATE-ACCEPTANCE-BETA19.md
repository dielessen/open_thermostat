# Beta.19 update acceptance on the Home Assistant route: checklist

The update from E32 `v0.1.0-e32v2-beta.18` to `v0.1.0-e32v2-beta.19` is
planned as the **first complete acceptance on the Home Assistant route**
(`method: home_assistant`). The beta.18 install has no complete receipt
(`update-acceptance/e32-beta18-20261029.json` is `INCOMPLETE`: no
pre-install capture, no backup, no `last_install` record and no
independent check). The update gate therefore still accepts beta.4 as the
basis, and beta.19 is published under the one-time owner exception
`BETA19-PUBLICATION-EXCEPTION-20261030.json`.

This page lists the steps in order. The fields and rules come from
[HA-UPDATE-ACCEPTANCE.en.md](HA-UPDATE-ACCEPTANCE.en.md) and
`scripts/verify_e32_update_gate.py` (`HA_REQUIRED`,
`home_assistant_acceptance`). Every check in the receipt must be `true`.
All times are UTC (`2026-10-30T09:00:00Z`).

## 0. Before you start

- [ ] Both releases are published: `v0.1.0-e32v2-beta.19` (pre-release) and
      `ha-v0.4.0b11`. Neither is a draft.
- [ ] The release preflight passed for exactly this tag: the final local
      check round and the tag's CI run are green. Write down the CI run URL.
      This is `fresh_preflight_passed`.
- [ ] HA 0.4.0b11 is installed first (integration package, Home Assistant
      restarted). Only 0.4.0b11 writes the `last_install` record. Note that
      0.4.0b11 shows no E32 values while the E32 still runs beta.18 (the
      MQTT topics changed). The Firmware entity still works, because it reads
      `/status/version` over HTTP.
- [ ] Nobody uses the E32 web pages or the OpenThermostat options while the
      update runs. No boiler trial or settings session is open.

## 1. Pre-install capture (installer's capture, read-only)

Run the read-only capture script on the home network. It only sends GET
requests, plus at most one `/auth/login` when there is no session.

```powershell
python -I capture_beta19_preinstall.py --out preinstall-<UTC>
```

It saves:

- [ ] The GitHub release as the API returns it: `tag_name`, `draft`,
      `prerelease`, `published_at` and the `firmware.bin` asset (`name`,
      `size`, `digest`). This is `github_release` and `public_release_exact`.
- [ ] The E32 identity before the update: `/status/version`,
      `/updates/status` and `/status` (uptime, `boot_pending`).
- [ ] The settings backup (section 2).
- [ ] The Home Assistant update entity, when `HA_URL` and `HA_TOKEN` are
      set: `installed_version` must be `v0.1.0-e32v2-beta.18` and
      `latest_version` must be exactly `v0.1.0-e32v2-beta.19`. Also the
      integration version (`0.4.0b11`) and the Core version. The entity checks
      GitHub every 6 hours. If it does not offer beta.19 yet, run the
      `homeassistant.update_entity` action for it once, then capture again.
- [ ] `CAPTURE-MANIFEST.json` with the SHA-256 of every captured file.
      Its own SHA-256 becomes `installer_receipt_sha256`.

## 2. Settings backup

- [ ] **On beta.18** the new backup endpoint does not exist yet. The backup
      is the read-only API export of the settings documents. The capture
      script reads `/config/rooms`, `/config/wifi`, `/config/boiler`,
      `/config/boiler-display`, `/config/hardware`, `/config/debug`,
      `/config/logging`, `/config/program/current`, `/status/programs` and
      every program, `/config/bluetooth` and `/config/heating`.
      The device redacts secrets in these documents. The SHA-256 of
      `backup/BACKUP-MANIFEST.json` becomes `backup_manifest_sha256`.
- [ ] **After the update (beta.19)** also save an export from the new
      backup endpoint: System → Network → Backup and restore → export,
      **without a passphrase**. Without a passphrase the file contains no
      keys, and Wi-Fi and web passwords are never exported. This is
      `POST /config/backup {"action":"export"}`. It is read-only, but it is
      a POST behind the CSRF gate, so the GET-only capture script does not
      send it. Keep the file next to the post-check. From beta.20 on, this
      export is the pre-install backup.
- [ ] `backup_verified`: every file in the backup manifest is re-read and
      its hash matches.

## 3. Install once

- [ ] Press **Install** on the E32's Firmware entity in Home Assistant
      **once**, and note the time. Do not retry. A second press means a new
      acceptance. This gives `single_ha_install_action` and
      `install_actions: 1`.
- [ ] Wait until the entity shows `v0.1.0-e32v2-beta.19` as installed
      (`ha_entity_reports_new_version`). Home Assistant downloads, verifies
      (GitHub SHA-256, size, version marker), uploads once to `/ota` and
      waits for the restart. A mismatch is never uploaded.

## 4. `last_install`

- [ ] Copy the entity's `last_install` attribute unchanged (Developer
      tools → States), or let the post-check capture read it through the
      HA API. It is `ha_install_record` and must have:
      `result: installed`, `uploads: 1`, `tag` = beta.19,
      `from_version` = beta.18, `sha256` = `firmware_sha256`, `size` =
      `firmware_bytes`, `started_at` after `published_at`, `finished_at`,
      `duration_s` ≤ 900. Its `reported` block must hold the version, source
      commit, web SHA-256 and ELF SHA-256 that the E32 reports after the
      restart.
- [ ] `ha_download_digest_size_marker_verified` and
      `local_upload_accepted` follow from `result: installed` with
      `uploads: 1`.

## 5. Post-check after at least 600 s

- [ ] Read `/status/version`, `/updates/status` and `/status` at least
      twice after the install. Each read must show version beta.19 and
      `boot_pending: false`. Uptime must rise between the reads (no restart
      in between). The last read must be at least 600 s after the restart
      (`observations`, `new_boot_observed`, `boot_confirmed`,
      `stable_uptime_observed`).
- [ ] Version, source commit, web SHA-256 and ELF SHA-256 must equal the
      public `e32v2-update.json` of the release, and the ELF hash must match
      the app descriptor in `firmware.bin`
      (`installed_version_source_elf_web_exact`).
- [ ] Read the same settings routes again and compare them with the backup.
      Only schema additions are allowed; Bluetooth runtime fields such as
      the last-seen time are volatile
      (`settings_programs_bindings_preserved`).
- [ ] Heating is still in shadow mode: the active route is not ready,
      `board::emsActiveHeatAllowed` is still false and the E32 sends no boiler
      request (`control_state_safe_after_restart`).
- [ ] MQTT: `fw/availability` is `online`, `fw/heartbeat` arrives every
      60 s, HA 0.4.0b11 entities have values, and
      `mqtt_stalled_disconnects` / `mqtt_socket_error_disconnects` do not
      rise during the observation.

## 6. Independent capture

- [ ] A second, separate capture by another person or tool confirms the
      version, the identity and the settings. It reads the E32 and Home
      Assistant directly and does not reuse the installer's files. It is
      written to its own folder with its own manifest. That manifest's
      SHA-256 is `independent_receipt_sha256` and must differ from
      `installer_receipt_sha256` (`independent_postcheck_passed`).

## 7. Receipt and gate

- [ ] Write `update-acceptance/e32-beta19-<YYYYMMDD>.json` with `schema: 1`,
      `status: PASS`, `tag`, `method: home_assistant`, all fourteen
      `checks`, `github_release`, `firmware_sha256`, `firmware_bytes`,
      `source_commit`, `web_sha256`, `elf_sha256`, `ha_entity_id`,
      `ha_installed_version_before`, `ha_latest_version_before`,
      `ha_installed_version_after`, `install_actions`,
      `ha_integration_version`, `ha_core_version`, `ha_install_record`,
      `observations`, and the three receipt hashes. Limits and notes may be
      added.
- [ ] Put the receipt and its SHA-256 under `accepted` in
      `E32-UPDATE-GATE.json`, set `pending_tag` to `null` (or to the next
      candidate), and remove the publication exception.
- [ ] Run `python3 scripts/verify_e32_update_gate.py` and
      `python3 scripts/verify_beta_release_inventory.py`.
- [ ] If any check is not `true`, keep `status: INCOMPLETE` and list the gap
      under `limits`. Never mark a check `true` without evidence.
