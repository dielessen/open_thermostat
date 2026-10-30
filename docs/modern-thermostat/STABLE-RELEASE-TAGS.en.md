# Stable release tags (1.0 and later)

Decision, 30 October 2026. Status: the release tooling accepts these tags; no
stable tag or release exists yet.

## Decision

| Component | Pre-release | Stable | GitHub release |
| --- | --- | --- | --- |
| E32 V2 firmware | `v0.1.0-e32v2-beta.20`, `v1.0.0-e32v2-rc.1`, `v1.1.0-e32v2-beta.1` | `v1.0.0-e32v2`, `v1.0.1-e32v2`, `v1.1.0-e32v2` | Pre-release / normal release |
| Home Assistant integration | `ha-v0.4.0b12`, `ha-v1.0.0rc1`, `ha-v1.1.0b1` | `ha-v1.0.0`, `ha-v1.0.1`, `ha-v1.1.0` | Pre-release / normal release |

- **E32 stable tags keep the board suffix:** `v1.0.0-e32v2`, not `v1.0.0`.
  A bare `v1.0.0` is rejected by every parser, so it can never become a
  firmware release by accident.
- **HA stable tags:** `ha-v` plus the `manifest.json` version, which follows
  PEP 440 (`1.0.0`, `1.0.0rc1`, `1.1.0b1`).
- **The two components keep separate version numbers.** HA 1.0.0 together
  with E32 1.0.0 is a choice for that release, not a rule.
- **The path to 1.0:** beta.21 (`v0.1.0-e32v2-beta.21`), with the attended
  switch-over to active control, is the candidate. After 14 days of active
  control without problems, the same source becomes `v1.0.0-e32v2`. An optional `v1.0.0-e32v2-rc.N` may come
  first. EMS+ arrives in 1.1 (`v1.1.0-e32v2-beta.N`).

## Why this form

- The `-e32v2` suffix is already part of every published firmware tag. The
  E32's own catalog (`src/update/IndexedReleaseCatalog.h`), the Home
  Assistant update entity (`firmware_update.py`) and every release script
  use it to tell firmware tags apart from `ha-v…` and `sources-e32v2-…` tags
  in the same repository. It also leaves room for another board later.
- The tag is built into the image (`OT_E32V2_OTA_V1:<tag>:…`) and reported in
  `/status/version`. Home Assistant uploads an image only when this marker
  matches the release tag.
- The build workflow already starts on `v*` and `ha-v*` tags.
  `organize_releases.py` and `sync_readme_releases.py` already show a stable
  channel next to a newer pre-release on the release pages and in the README
  table.

## Order

Within one version number: alpha < beta < rc < stable. Then the version number:

`v0.1.0-e32v2-beta.19` < `v0.1.0-e32v2-beta.20` < `v1.0.0-e32v2-rc.1` <
`v1.0.0-e32v2` < `v1.0.1-e32v2-beta.1` < `v1.0.1-e32v2` < `v1.1.0-e32v2-beta.1`

An installation is never offered a less mature channel than the one it runs.
For example, an E32 on beta.20 or beta.21 is offered `v1.0.0-e32v2-rc.N` and
then `v1.0.0-e32v2`. An E32 on 1.0.0 is offered 1.0.1, but not
1.1.0-beta.1. The same rule applies in Home Assistant and on the E32's own
update page.

## Where it is enforced

| Place | Stable handling |
| --- | --- |
| `ha/.../firmware_update.py` | `TAG` regex, `parse_tag` (stable rank 3), `select_release` channel floor, `verify_image` marker |
| `src/update/IndexedReleaseCatalog.h` | `firmwareVersion` (stable rank 3), `newerFirmwareRelease` channel floor |
| `scripts/organize_releases.py` | `classify`, `is_stable` (tag and GitHub flag), titles `E32 firmware · 1.0.0 · Current`, notes heading `# E32 V2 1.0.0` |
| `scripts/sync_readme_releases.py` | README table: a Stable row, plus a Pre-release row when a newer one exists; `git clone --branch` uses the stable tag |
| `scripts/verify_e32_update_gate.py` | `version`, `stable`; a stable candidate needs an accepted **Home Assistant** update of its predecessor; the one-time exception is limited to betas |
| `scripts/package_ha_release.py` | `ha-release.json` `prerelease` follows the tag |
| `scripts/verify_alpha36_beta_path.py`, `verify_accepted_update_path.py` | retained updaters are proved against a stable tag published as a normal release |
| `scripts/cleanup_release_artifacts.py` | keeps the newest three firmware releases by version (stable included) |
| `.github/workflows/build.yml` | `gh release create` without `--prerelease` for a stable tag; the HA publication check binds `prerelease` to the tag |

## Notes headings and titles

The 0.1.0 test releases keep their published short form (`beta.19`,
`# E32 V2 beta19`). From 1.0 on, release titles and `RELEASE-NOTES.md`
headings name the full version: `1.0.0`, `1.0.0-rc.1`, `1.1.0-beta.1`
(`# E32 V2 1.1.0-beta.1`). This way, a 1.1.0 beta.1 is never confused with
the published 0.1.0 beta.1.

## Still needed before `v1.0.0-e32v2` is tagged

1. **Physical acceptance on the Home Assistant route.** The published
   predecessor (beta.20 or beta.21) must be installed through the HA update
   entity. Its receipt must be recorded as `accepted` in `E32-UPDATE-GATE.json`
   (`method: home_assistant`). Today, `accepted` is beta.4 (native) and
   `pending` is beta.19.
2. **A frozen candidate.** Set `pending_tag` to `v1.0.0-e32v2`, write a
   candidate plan with `previous_published_tag` equal to the accepted tag,
   and add no publication exception.
3. **A version-only commit.** Set `release.json` to `v1.0.0-e32v2` and, if HA
   becomes 1.0.0, set `manifest.json` to `1.0.0` and update the versioned
   frontend card URLs. Add `# E32 V2 1.0.0` and `# HA 1.0.0` sections with
   the English reader notes. Refresh the reviewed release inventory. The
   version string is built into the image, so 1.0.0 is a new build of the
   same source and not a retag of the beta binary. Keep that commit limited
   to version and release files.
4. **The 14 days of active control.** This criterion is the owner's decision
   and is not checked by the tooling. Record it in the candidate plan.

## Known limits (after 1.0)

- The E32's own catalog keeps the two newest verified releases by version.
  Suppose 1.0.1 is published while two newer 1.1 betas exist. Then an E32 on
  1.0.0 does not see 1.0.1 on its own update page, but Home Assistant (the
  official route) does offer it. The tag index is also limited to 80 `v*`
  tags (55 today); above that, the E32 uses the slower general release scan.
- Home Assistant reads the 20 newest GitHub releases of all components. A
  stable release that is older than 20 newer releases is not offered.
- Once `ha-v1.0.0` is published, GitHub's "Latest release" badge goes to
  whichever stable release was published last. Nothing in the update paths
  uses `releases/latest`.
