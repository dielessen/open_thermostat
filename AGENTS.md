# Release housekeeping

- Keep user-facing GitHub pages, commit messages and release descriptions in English.
  Existing `.nl.md` engineering plans may stay Dutch.
- After each release and large local preflight, clean generated output with
  `python3 scripts/cleanup_release_artifacts.py --fetch-published --apply --report out/cleanup-latest.json`.
  Use the command without `--apply` to inspect its scope first when needed.
- Preserve source, Git worktrees, installation backups, receipts, logs and delivered
  relink inputs. `out/` contains nested source worktrees; never delete it wholesale.
- The cleanup retains the latest three published E32 releases plus the accepted
  and pending releases. Old public downloads require an exact GitHub digest before
  removal. Identical retained ZIPs share read-only storage; write new archives to
  fresh paths. Keep the local cleanup report with restore URLs and file hashes.

# Before a tag

- Follow `docs/RELEASING.md`: run `scripts/final_check.sh --stress 3` on the exact
  commit, push the branch only when it passes, tag only after its CI run is green
  (the tag run then reuses those tests). Never fix a timing race with a retry.
