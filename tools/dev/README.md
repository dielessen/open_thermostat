# Developer helpers (not shipped)

Moved from a session scratchpad on 3 November 2026 so a release can be prepared without it.

| Script | Use |
| --- | --- |
| `refresh_beta19_inventory.py . --apply` | Refresh `docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json` and `docs/third-party/shipped-policy.json` after any change to a listed file; then `python scripts/verify_beta_release_inventory.py` must print PASS |
| `json_merge3.py <repo> <conflicted json>...` | Three-way merge of conflicted JSON files by key (translations, strings.json) during a `git merge`; reports clashes |
| `ci_wait.py <sha>` | Anonymous GitHub API: wait for the workflow runs of a commit |
| `tag_wait.py <tag>...` | Anonymous GitHub API: wait for the tag runs and the GitHub releases |
| `prepare_rc5.py <worktree> --date YYYYMMDD --changes-file F` | The content of the rc.5 version commit (E32 `v1.0.0-e32v2-rc.5`, HA `1.0.0rc6`): both versions, every `/open_thermostat/<file>-1.0.0rc5.js` URL (found, not listed: all the cards of the frontend folder, the week editor, the planner and the browser test that routes one; a card without a versioned URL stops it), the notes drafts prepended (validated first; a draft that still has `<!-- pending` or `TODO` lines is refused), `RC5-KANDIDAAT.json` (a field the script does not know stops it), `RC5-OWNER-INSTRUCTION-<date>.json`, `RC4-UPDATE-GAP-<date>.json`, `RC5-PUBLICATION-EXCEPTION-<date>.json` (a draft without the owner's approval unless `--statement-file` gives his words), the gate file, `tools/acceptance/install-config.json` and the "nu ..." lines of `INSTALL-STEPS.nl.md`; no string of the rc.4 records may stay in the rc.5 records; all or nothing, LF bytes. `--rebind` redoes the hash chain after the owner's statement was filled in by hand. `--allow-placeholders` is for a `--dry-run` or a rehearsal on a throwaway copy only. Tested on throwaway trees with five and with six cards, and on copies of the real files (`test_prepare_rc5.py`); never run it on a tree you want to keep as it is: `--dry-run` on a copy first, then once in the release worktree |
| `prepare_rc4.py` | How the rc.4 version commit was made (history; `prepare_rc5.py` replaces it as the template; `test_prepare_rc4.py` keeps testing it) |
| `prepare_rc3.py <worktree>` | How the rc.3 version commit was made (history) |
| `manual/make_pdf.py <output.pdf>` | The Dutch installation manual as a PDF (reportlab in WSL `~/venvs/pdf`). Versions at the top; menu names go through `ui()` and `named()` and `test_manual_labels.py` checks them against the Dutch texts of the integration. Write the PDF to `out/`, never commit it; see `manual/README.md` |
| `final_check_runner.sh [--copy] [--only steps]` | Runs `scripts/final_check.sh --stress 2` in WSL with the node path; `WORKTREE=/mnt/c/...` selects the worktree; `--copy` runs on a copy on the WSL disk (much faster than /mnt/c) |
