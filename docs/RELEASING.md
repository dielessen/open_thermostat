# Releasing

This page describes how a commit becomes a published E32 or Home Assistant
release, and what to check before a tag. A red CI run costs about 45 minutes
and a failed tag run blocks the release, because tags are never moved. So every
check that can fail runs locally first, and CI runs each test once per commit.

## How CI runs

The workflow `.github/workflows/build.yml` runs on every push and pull request.

| Job | What it does | Time |
| --- | --- | --- |
| `reuse` | Decides whether a tag run may reuse the tests of a branch run (below) | < 1 min |
| `gates` | Update gate, release inventory, release metadata and policy checks | about 1 min |
| `harnesses` | Compiles every hand-written native harness and HA interop runner, without running them, so a stale test stub fails within minutes | about 3 min |
| `browser (1/4)` … `browser (4/4)` | The browser regressions of `test/browser-tests.txt`, in four fixed shards | about 5–8 min each |
| `build (…)` | Firmware builds; `build (native)` runs the native test suites and harnesses; `build (e32v2)` packages the E32 release | 2–9 min |
| `home-assistant-native` | Native HA suite on the reviewed Core, then the HA package | about 8 min |
| `home-assistant-compat (…)` | The same suite on the other accepted Cores, in parallel | about 7 min each |
| `source-reproduction`, `manual-route-compile`, `settings-route-compile`, `fuzz-smoke`, `soak-smoke` | Reproduction, compile-only policy probes, fuzzing and soak | 1–3 min each |
| `publish-…` | Publication, only on a tag push | about 1 min |

### Reusing the branch run on a tag

A tag points at a commit that was already pushed to a branch, and that branch
run executed every test job. When the tag is pushed, `scripts/ci_reuse.py` looks
up that run with the workflow's own token. A run counts only when it:

- is a push run of this workflow file, for this repository and this exact commit;
- ran on a branch, not on a tag;
- concluded `success`, and every required job of its latest attempt concluded
  `success` (the list in `ci_reuse.py`, which `scripts/test_ci_reuse.py` keeps
  in step with the workflow's job ids).

When it finds one, the tag run skips the test jobs. It still runs the gates,
the source reproduction, the E32 build, packaging, verification and
publication. The HA package is built from the tagged checkout with the branch
run's acceptance report; `scripts/package_ha_release.py` checks that report's
recorded commit and source hash against the checkout.

The tag run's annotations and summary name the reused run, or say why
everything ran again. Without such a branch run, for example when the tag is
pushed before the branch run finished, or after an API error, the tag run runs
every job as before.

## Before the tag

1. **Code freeze.** The release commit is on its branch, with versions, release
   notes, gate files and a refreshed release inventory. `git status` is clean.
2. **Local check, with stress.** Run the whole local check on that exact commit,
   in WSL or Linux:

   ```sh
   scripts/final_check.sh --stress 3
   ```

   Every step must say `PASS` and the summary `OVERALL PASS`. `--stress 3` runs
   every browser test 3 rounds of 4 parallel copies pinned to one CPU core. A
   timing race in a test shows up there, not on a loaded CI runner. Fix a race at
   its cause, never with a retry, a longer timeout or a skip.
3. **Push the branch only now**, and wait until its CI run is completely green.
   Do not push half-checked work to a release branch: every push starts CI.
4. **Tag the same commit**: `v…-e32v2-…` and/or `ha-v…`. Push the tags. The tag
   runs reuse the green branch run, so they take minutes, not another full run.
5. **Check the tag runs and the published releases**: the release exists, is
   not a draft, and its assets and digests match the run.

## Between an acceptance and the next version bump

Right after a release is accepted (`docs/modern-thermostat/E32-UPDATE-GATE.json`),
`release.json` on `main` and on feature branches still names that release.
Branch and pull-request builds then package it with `--allow-accepted-version`:
the image is reproduced and verified, and `accepted-predecessor-compatibility.json`
says `ALREADY_ACCEPTED` instead of proving an update path (the accepted updater
rightly never offers its own version). A tag build never gets this allowance:
`scripts/package_e32v2_release.py` refuses it when `GITHUB_REF` is a tag, and the
`gates` job requires the tag to be newer than the accepted release.

## After the release

- Install and accept on the Home Assistant route (`docs/modern-thermostat/HA-UPDATE-ACCEPTANCE.en.md`).
- Merge into `main` from a separate worktree. The release-links bot pushes
  README updates to `main` after every publication. So fetch first, check that
  `origin/main` is an ancestor, and push the merge at once.
- Clean generated output as `AGENTS.md` describes.

## Rules for test code

- Change a test stub in the same commit as the product code it follows. The
  `harnesses` job and `scripts/final_check.sh` compile them all within minutes.
- A new browser test goes into `test/browser-tests.txt` with a shard number;
  `scripts/test_browser_suite.py` fails when one is missing.
- Keep LF line endings. Python on Windows writes CRLF with `open(path, 'w')`;
  use `write_bytes` or `newline='\n'`. The local check fails when a new file, or
  a file that was LF at the accepted release, now has CRLF.
