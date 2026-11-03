# Developer helpers (not shipped)

Moved from a session scratchpad on 3 November 2026 so a release can be prepared without it.

| Script | Use |
| --- | --- |
| `refresh_beta19_inventory.py . --apply` | Refresh `docs/modern-thermostat/BETA1-RELEASE-INVENTARIS.json` and `docs/third-party/shipped-policy.json` after any change to a listed file; then `python scripts/verify_beta_release_inventory.py` must print PASS |
| `json_merge3.py <repo> <conflicted json>...` | Three-way merge of conflicted JSON files by key (translations, strings.json) during a `git merge`; reports clashes |
| `ci_wait.py <sha>` | Anonymous GitHub API: wait for the workflow runs of a commit |
| `tag_wait.py <tag>...` | Anonymous GitHub API: wait for the tag runs and the GitHub releases |
| `prepare_rc3.py <worktree>` | Template for the version commit of a release (notes, versions, card URLs, gate files); copy to `prepare_rc4.py` and adjust |
| `final_check_runner.sh [--copy] [--only steps]` | Runs `scripts/final_check.sh --stress 2` in WSL with the node path; `WORKTREE=/mnt/c/...` selects the worktree; `--copy` runs on a copy on the WSL disk (much faster than /mnt/c) |
