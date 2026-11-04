# Developer helpers (not shipped)

Moved from a session scratchpad on 3 November 2026 so a release can be prepared without it.

| Script | Use |
| --- | --- |
| `refresh_beta19_inventory.py . --apply` | Refresh `docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json` and `docs/third-party/shipped-policy.json` after any change to a listed file; then `python scripts/verify_beta_release_inventory.py` must print PASS |
| `json_merge3.py <repo> <conflicted json>...` | Three-way merge of conflicted JSON files by key (translations, strings.json) during a `git merge`; reports clashes |
| `ci_wait.py <sha>` | Anonymous GitHub API: wait for the workflow runs of a commit |
| `tag_wait.py <tag>...` | Anonymous GitHub API: wait for the tag runs and the GitHub releases |
| `prepare_rc4.py <worktree> --date YYYYMMDD --changes-file F` | The content of the rc.4 version commit: both versions, the five card URLs, the notes drafts prepended (validated first), `RC4-KANDIDAAT.json`, `RC4-OWNER-INSTRUCTION-<date>.json`, `RC3-UPDATE-GAP-<date>.json`, `RC4-PUBLICATION-EXCEPTION-<date>.json` (a draft without the owner's approval unless `--statement-file` gives his words) and the gate file; all or nothing, LF bytes. `--rebind` redoes the hash chain after the owner's statement was filled in by hand. Tested on throwaway trees (`test_prepare_rc4.py`); run it once, in the release worktree |
| `prepare_rc3.py <worktree>` | How the rc.3 version commit was made (history; `prepare_rc4.py` replaces it as the template) |
| `final_check_runner.sh [--copy] [--only steps]` | Runs `scripts/final_check.sh --stress 2` in WSL with the node path; `WORKTREE=/mnt/c/...` selects the worktree; `--copy` runs on a copy on the WSL disk (much faster than /mnt/c) |
