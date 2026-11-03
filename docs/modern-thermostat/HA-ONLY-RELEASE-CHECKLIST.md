# HA-only release checklist (HA 1.0.0rc4 on E32 1.0.0-e32v2-rc.3)

Precedent: `075359b6` (HA 0.4.0b15 on E32 beta.22). Nothing is bumped yet.

## Version name: `1.0.0rc4`, tag `ha-v1.0.0rc4`

- `scripts/organize_releases.py` accepts HA tags `ha-vX.Y.Z[.dev|a|b|rc]N` only.
  A `.post1` suffix is rejected by `classify`, so `ha-v1.0.0rc3.post1` could
  never be packaged or published. `publish_hacs_repo.py` accepts `(a|b|rc)N` too.
- `rc4` sorts after `rc3` for HA/HACS (PEP 440), is a pre-release, and keeps
  the rule "HA and E32 have separate version numbers" (STABLE-RELEASE-TAGS).
  The E32 stays `v1.0.0-e32v2-rc.3`; the HA notes say so in their first line.
- Users see "1.0.0rc4" in HACS next to firmware "rc.3". That is the accepted
  pattern (b15 next to beta.22).

## Files to change in the version commit

1. `ha/config/custom_components/open_thermostat/manifest.json`: `"version": "1.0.0rc4"`.
2. Versioned frontend URLs `-1.0.0rc3.js` to `-1.0.0rc4.js` (cache busting):
   `e32_week.py` (CARD_URL, EDITOR_URL), `week_planner.py` (URL),
   `frontend/e32-week-card.js` (EDITOR), `test/week-editor-browser.cjs` (route).
   Do this after the three integration branches have merged, to avoid conflicts.
3. `docs/modern-thermostat/HA-RELEASE-NOTES.md`: prepend the finished
   `HA-RC4-NOTES-DRAFT.en.md` (all `<!-- pending -->` markers resolved). The
   first line must be `# HA 1.0.0rc4` (`verify_publication_notes` compares it
   to the manifest, so the notes and the manifest must change in the same
   commit; that is why the draft is kept in its own file for now).
4. `docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json`: refresh the `sha256`
   of every changed file (it lists `ha/...` files, `scripts/publish_hacs_repo.py`
   and others; `scripts/verify_beta_release_inventory.py` names the first drifted path).
   No refresh tool exists; recompute the hashes of the changed paths after review.
5. `docs/third-party/shipped-policy.json`: the same for changed HA source files
   it lists (checked by `release_shipped` / packaging).

## Must NOT change

- `release.json` (stays `v1.0.0-e32v2-rc.3`), `src/`, `data/html/`, firmware assets.
- `docs/modern-thermostat/E32-UPDATE-GATE.json` (pending tag stays rc.3), the RC3 candidate and
  exception files, `RELEASE-NOTES.md` (E32 notes).
- No `v...-e32v2-...` tag.

## Gates and commands

```sh
python3 scripts/verify_beta_release_inventory.py     # runs verify_publication_notes + update gate
python3 scripts/verify_e32_update_gate.py
python3 scripts/organize_releases.py --repository dielessen/open_thermostat \
    --output out/notes-check.json --publication-notes-for ha-v1.0.0rc4   # needs New/Fixed/Updating/Limitations, < 6000 bytes
scripts/final_check.sh --stress 3                    # WSL; branch pushed only after OVERALL PASS
```

CI (`build.yml`) on a `ha-v*` tag: firmware jobs are skipped; `gates`,
`home-assistant-native` ("Verify and package exact HA-only candidate" via
`scripts/package_ha_release.py`) and the HA publish job run. The publish job asserts
`tag == 'ha-v' + manifest version`, source commit, notes equal
`HA-RELEASE-NOTES.md`, and pre-release status. The `v*` accepted-predecessor
gate step does not run for `ha-v*`.

Order: version commit, local check, push branch, wait for green, tag the same
commit `ha-v1.0.0rc4`, push the tag (reuses the branch run), check the release
and its assets. Then HACS: `python3 scripts/publish_hacs_repo.py 1.0.0rc4 <clone> [--push]`
(downloads the release ZIP, verifies SHA-256, writes the HACS repo; also writes
`hacs.json` with `hide_default_branch`). If only the front page changes, use `--readme-only`.
After publishing: install on the HA route and record acceptance
(`HA-UPDATE-ACCEPTANCE.en.md`), merge to `main`, cleanup per AGENTS.md.

## Open points to confirm before tagging

- A local-only unittest run on Windows has many environment failures (symlinks, ELF
  fixtures); run the scripts suite in WSL (`final_check.sh` step `unittests`).
- The HACS repo must be re-published (or `--readme-only`) for `hide_default_branch` to reach users.

## Docs to update after the other branches land (not edited yet)

Configure paths, dashboard view names, "heating curve" / "Follow outdoor temperature":

- `docs/INSTALL.md`: lines ~495-504 (Configure after setup), 540, 581 (Configure → Rooms),
  593 and 680 (dashboard), 650-672 (Configure → Home → Heating and boiler / Presence /
  Defaults / Energy), 1092, 1117 (Configure → E32 connection), 1191 (Advanced and diagnostics).
- `docs/USER-GUIDE.md`: the feature table lines 30-53 (all Configure paths; line 43 names
  "Follow outdoor temperature (heating curve)"), 118 and 584 (Heating view), 205-225, 242
  ("Week program" view), 313-356 (Windows and doors, presence, house mode, defaults),
  427-428, 514-529 ("heating curve" / "Follow outdoor temperature" paragraph; learned overview texts
  "Heating curve: standard for now..."), 536, 721 and 770 ("Now" section), 840 (Boiler view),
  882-932 (E32 connection, restore, Advanced and diagnostics), 1059 (Tidy entity IDs).
- `docs/INSTALL-CHECK.md`: rows at lines 43-52 (Configure paths, "OpenThermostat → Week program"
  dashboard view, check row with dashboard and Repairs).
- `docs/FIELD-TESTER.md`: lines 97-106 (Configure → E32 connection / Rooms), 216 (Learned page).
- `README.md`: only E32 page screenshots (lines 17, 121-125); no HA menu path. Check that the
  feature list does not name "heating curve" (grep again after the merge).
- `scripts/publish_hacs_repo.py` README template: line ~86 ("A ready-made dashboard") and the
  screenshots (E32 pages only); no Configure path now, but re-read after the dashboard branch.
- Also `docs/modern-thermostat/HA-PARITY-RC3.md` if parity tables are kept current.
