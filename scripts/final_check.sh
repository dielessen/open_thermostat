#!/bin/bash
# The whole local pre-tag check, with a PASS/FAIL summary (docs/RELEASING.md).
# Run it on the exact commit that will be tagged, in WSL or Linux.
#
#   scripts/final_check.sh                         every step, one after another, in this worktree
#   scripts/final_check.sh --lanes                 EXPERIMENTAL: independent steps at the same time (below)
#   scripts/final_check.sh --copy                  EXPERIMENTAL: run in a copy on the WSL disk (below)
#   scripts/final_check.sh --stress 3              also every browser test 3 rounds x 4 copies on one CPU core
#   scripts/final_check.sh --only harnesses,native / --skip builds    a subset (names: STEPS below)
#   scripts/final_check.sh --dry                   prerequisites, CI step extraction and the fast steps
#   FUZZ=1 scripts/final_check.sh                  also the 60 s fuzz smoke of CI
#   ALLOW_DIRTY=1 scripts/final_check.sh           do not fail on uncommitted changes
#
# The native harnesses, HA interop runners and browser list come from the same
# scripts CI uses (test/native_harnesses.sh, test/interop/prepare_runners.sh,
# test/run-browser-tests.sh); the remaining CI commands are read from
# .github/workflows/build.yml at run time (scripts/ci_step.py).
#
# Lanes (--lanes; not yet proven equivalent to the serial run; fewer than 12 CPUs: serial). After `static`,
# independent groups run at the same time, each pinned to its own CPUs:
#   pio      harnesses, then native and builds together, then literal_reach, link_review, unittests
#   ha       ha and ha_min together (own MQTT broker port each)
#   host     verifiers, soak, replay
#   browser  browser (a few tests at a time), then fuzz on the same CPUs
#   stress   browser_stress: the same 4 copies on one core per test, one test per stress core
# Every step keeps its own log and PASS/FAIL line; the summary adds the wall time per lane.
#
# A worktree on a Windows drive under WSL (/mnt/c, 9p) makes every file access of the
# builds, scans and tests slow. With --copy the check runs in a copy on the Linux disk
# (CHECK_TREE [~/.cache/openthermostat-final-check/tree-<worktree name>]): a git clone
# sharing this repository's objects, at this worktree's HEAD, plus its uncommitted and
# untracked (not ignored) files, so `static` sees the same state. The copy keeps its
# .pio and out/ between runs (incremental builds); firmware and evidence land there.
#
# Environment (defaults in brackets): NODE_MODULES [<repo>/node_modules] with
# playwright-core; HA_VENV [~/venvs/ha] with ha/requirements-test-native.txt;
# PIO_VENV [~/venvs/pio] with platformio 6.2.0; LOGDIR [/tmp/final-check-<worktree
# name>], one per worktree so two checks never delete each other's logs; PIO_LOCK
# [/tmp/openthermostat-pio.lock], shared by worktrees that build at the same time;
# MQTT_PORT [an even port from 18800 to 18898 chosen by the worktree's path] for a
# local mosquitto (/usr/sbin/mosquitto; ha_min uses MQTT_PORT+1 in lanes). All build
# and evidence directories of a run are under LOGDIR. CPU sets of the lanes: STRESS_CPUS,
# BROWSER_CPUS, WORK_CPUS (pio, ha, host), e.g. 0-5, 6-14, 15-27 on 28 CPUs.
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
SRC=$R
NODE_MODULES=${NODE_MODULES:-$R/node_modules}
HA_VENV=${HA_VENV:-$HOME/venvs/ha}
PIO_VENV=${PIO_VENV:-$HOME/venvs/pio}
# Per worktree (R5-23): the log directory is wiped at the start, and the broker port must not be shared.
L=${LOGDIR:-/tmp/final-check-$(basename "$SRC")}
LOCK=${PIO_LOCK:-/tmp/openthermostat-pio.lock}
MQTT_PORT=${MQTT_PORT:-$(( 18800 + 2 * ($(printf '%s' "$SRC" | cksum | cut -d' ' -f1) % 50) ))}
STEPS="static verifiers harnesses native ha ha_min browser browser_stress soak replay fuzz builds literal_reach link_review unittests"
# Durations of the last browser run on this machine: lanes start the longest tests first.
DURATIONS=${BROWSER_TEST_DURATIONS:-${XDG_CACHE_HOME:-$HOME/.cache}/openthermostat-final-check/browser-durations.txt}

DRY=0; ONLY=""; SKIP=""; STRESS=0; SERIAL=1; IN_PLACE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --dry) DRY=1 ;;
    --serial) SERIAL=1 ;;
    --lanes) SERIAL=0 ;;
    --in-place) IN_PLACE=1 ;;
    --copy) IN_PLACE=0 ;;
    --only) ONLY=",$2,"; shift ;;
    --skip) SKIP=",$2,"; shift ;;
    --stress) STRESS=$2; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac; shift
done
[ "${FUZZ:-0}" = 1 ] || SKIP="$SKIP,fuzz,"
[ "$STRESS" -gt 0 ] || SKIP="$SKIP,browser_stress,"

NCPU=$(nproc)
if [ $SERIAL = 0 ] && [ "$NCPU" -lt 12 ]; then echo "only $NCPU CPUs: the steps run one after another (--serial)"; SERIAL=1; fi
if [ $SERIAL = 0 ]; then
  # Stress cores first, then the browser/fuzz cores (9 = one per fuzz harness), the rest for the work lanes.
  ns=$(( NCPU >= 24 ? 6 : NCPU / 4 )); nb=$(( NCPU >= 24 ? 9 : NCPU / 4 ))
  STRESS_CPUS=${STRESS_CPUS:-0-$((ns - 1))}
  BROWSER_CPUS=${BROWSER_CPUS:-$ns-$((ns + nb - 1))}
  WORK_CPUS=${WORK_CPUS:-$((ns + nb))-$((NCPU - 1))}
fi

cpu_count(){ # cpu_count "6-14,16" -> 10: how many CPUs a list names
  local n=0 part parts; IFS=, read -ra parts <<< "$1"
  for part in "${parts[@]}"; do
    if [[ $part =~ ^([0-9]+)-([0-9]+)$ ]]; then n=$(( n + BASH_REMATCH[2] - BASH_REMATCH[1] + 1 )); else n=$(( n + 1 )); fi
  done; echo "$n"
}

export PATH="$HOME/node/bin:$PIO_VENV/bin:$HA_VENV/bin:$PATH"
export NODE_PATH=$NODE_MODULES ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1
rm -rf "$L"; mkdir -p "$L/.results" "$L/.lanes"
T0=$(date +%s)

sync_tree(){ # sync_tree <worktree> <copy>: the copy gets the worktree's HEAD and working-tree state
  local src=$1 m=$2 d
  set -e
  if [ ! -d "$m/.git" ]; then mkdir -p "$(dirname "$m")"; git clone --quiet --no-checkout --shared "$src" "$m"; fi
  git -C "$m" fetch --quiet --force "$src" "+HEAD:refs/check/head" "+refs/tags/*:refs/tags/*"
  git -C "$m" checkout --quiet --force --detach refs/check/head
  git -C "$m" clean -fdq -- . ':!out' ':!node_modules' ':!.vscode'
  # Uncommitted, untracked and deleted files: the same set `static` looks at.
  (cd "$src" && git ls-files -z -m -o --exclude-standard -- . ':!out' ':!node_modules' ':!.vscode') > "$L/tree-changed.lst"
  (cd "$src" && git ls-files -z -d -- . ':!out' ':!node_modules' ':!.vscode') > "$L/tree-deleted.lst"
  (cd "$m" && xargs -0 -r rm -f -- < "$L/tree-deleted.lst")
  rsync -a --from0 --ignore-missing-args --files-from="$L/tree-changed.lst" "$src/" "$m/"
  # The first time: the PlatformIO libraries the worktree already has (no registry download).
  for d in "$src"/.pio/libdeps/*/; do
    [ -d "$d" ] && [ ! -e "$m/.pio/libdeps/$(basename "$d")" ] && { mkdir -p "$m/.pio/libdeps"; cp -a "$d" "$m/.pio/libdeps/"; }
  done
  echo "tree $m: $(git -C "$m" rev-parse HEAD), $(tr -cd '\0' < "$L/tree-changed.lst" | wc -c) changed/untracked and $(tr -cd '\0' < "$L/tree-deleted.lst" | wc -c) deleted files from $src"
}
if [ $IN_PLACE = 0 ] && [ "$(stat -f -c %T "$SRC")" = v9fs ]; then
  M=${CHECK_TREE:-$HOME/.cache/openthermostat-final-check/tree-$(basename "$SRC")}
  ( sync_tree "$SRC" "$M" ) > "$L/tree.log" 2>&1 || { cat "$L/tree.log"; echo "could not copy $SRC to $M (--in-place runs here)"; exit 2; }
  cat "$L/tree.log"; R=$M
fi
WF=$R/.github/workflows/build.yml
cd "$R" || exit 2
FW=$(python3 -c "import json;print(json.load(open('release.json'))['version'])")
HA=$(python3 -c "import json;print(json.load(open('ha/config/custom_components/open_thermostat/manifest.json'))['version'])")

want(){ case "$ONLY" in "") ;; *",$1,"*) ;; *) return 1 ;; esac; case "$SKIP" in *",$1,"*) return 1 ;; esac; return 0; }
record(){ printf '%s\n' "$2" > "$L/.results/$1"; } # record <name> <summary line>
passed(){ grep -q '^PASS' "$L/.results/$1" 2>/dev/null; }
step(){ # step <name> <function>: run, log, record
  local name=$1 fn=$2 start rc secs
  if ! want "$name"; then record "$name" "SKIP  $name"; return 0; fi
  start=$(date +%s); echo "== $name${LANE:+ [$LANE]} $(date +%H:%M:%S)"
  ( set -o pipefail; "$fn" ) > "$L/$name.log" 2>&1; rc=$?
  secs=$(( $(date +%s) - start ))
  if [ $rc = 0 ]; then record "$name" "PASS  $name (${secs}s)"; echo "   $name PASS (${secs}s)"
  else record "$name" "FAIL  $name (${secs}s, rc=$rc, log $L/$name.log)"; echo "   $name FAIL (${secs}s)"; tail -15 "$L/$name.log"; fi
}
ci(){ python3 scripts/ci_step.py "$WF" "$@"; }
# The PIO lock: a lane that holds it for a group of steps sets PIO_LOCK_HELD=1, so the
# steps inside do not wait for themselves; otherwise every pio call takes it.
locked(){
  if [ "${PIO_LOCK_HELD:-0}" = 1 ]; then "$@"; return; fi
  flock -n "$LOCK" true || echo "waiting for the PIO lock (another worktree builds) since $(date +%H:%M:%S)" >&2
  flock "$LOCK" "$@"
}
pio_locked(){ locked pio "$@"; }
accepted_tag(){ python3 -c "import json;print(json.load(open('docs/modern-thermostat/E32-UPDATE-GATE.json'))['accepted']['tag'])"; }
# Lanes: the pio lane installs the native dependencies and builds the HA interop runners
# once, holding the PIO lock; the lanes that need them wait for that.
native_deps(){ pio_locked pkg install -e native && bash test/interop/prepare_runners.sh && touch "$L/.deps-ok"; touch "$L/.deps-done"; }
wait_native_deps(){
  [ $SERIAL = 1 ] && return 0
  while [ ! -f "$L/.deps-done" ]; do sleep 2; done
  [ -f "$L/.deps-ok" ] || { echo "native dependencies or HA interop runners failed: $L/deps.log"; return 1; }
}
# Before pio processes of one project run at the same time: let PlatformIO bring
# .pio/build/project.checksum up to date now (a stale checksum makes every pio run
# delete the whole .pio/build, including the other environments being built).
pio_build_dir_ready(){
  "$(dirname "$(readlink -f "$(command -v pio)")")/python" -c 'from platformio.project.config import ProjectConfig
from platformio.run.helpers import clean_build_dir
c = ProjectConfig.get_instance(); clean_build_dir(c.get("platformio", "build_dir"), c)'
}

# --- steps --------------------------------------------------------------------
s_static(){
  echo "release.json $FW, manifest.json $HA"
  # Cache busting (R5-12): the five versioned frontend URLs of the integration, and the test that routes one of
  # them, carry the integration version. (week_planner.py keeps older URLs on purpose, in LEGACY_URLS.)
  local ha_dir=ha/config/custom_components/open_thermostat missing="" entry
  for entry in 'e32_week.py|CARD_URL = "/open_thermostat/e32-week-card-' 'e32_week.py|EDITOR_URL = "/open_thermostat/week-editor-' \
               'frontend/e32-week-card.js|const EDITOR = '"'"'/open_thermostat/week-editor-' \
               'room_overview.py|CARD_URL = "/open_thermostat/room-status-card-' 'week_planner.py|URL = "/open_thermostat/week-planner-'; do
    grep -qF "${entry#*|}$HA.js" "$ha_dir/${entry%%|*}" || missing+=" ${entry%%|*}:${entry#*|}$HA.js"
  done
  grep -qF "p==='/open_thermostat/week-editor-$HA.js'" test/week-editor-browser.cjs || missing+=" test/week-editor-browser.cjs"
  [ -z "$missing" ] || { echo "FAIL versioned frontend URLs do not carry $HA:$missing"; return 1; }
  echo "versioned frontend URLs: all five carry $HA"
  # Since beta.22 only the E32 V2 build may send an active heat request (after the
  # owner's plan + handover); every other board keeps the gate closed.
  python3 - <<'PY' || { echo "FAIL active heat gate: only the E32 V2 branch of src/Board.h may be open"; return 1; }
import re
s = open('src/Board.h').read()
e32, other = s.split('#ifdef OPENTHERMOSTAT_E32V2', 1)[1].split('#else', 1)
other = other.split('#endif', 1)[0]
gate = r'constexpr bool emsActiveHeatAllowed = (\w+);'
assert re.findall(gate, e32) == ['true'] and re.findall(gate, other) == ['false']
assert s.count('emsActiveHeatAllowed =') == 2
PY
  echo "active heat gate: open in the E32 V2 build only (nothing is sent before the owner's handover)"
  if grep -rn 'TODO-FINAL' docs/modern-thermostat/RELEASE-NOTES.md docs/modern-thermostat/HA-RELEASE-NOTES.md README.md docs/INSTALL.md docs/USER-GUIDE.md; then
    echo "FAIL TODO-FINAL markers left"; return 1; fi
  if [ "${ALLOW_DIRTY:-0}" != 1 ] && [ -n "$(git status --porcelain --untracked-files=normal -- . ':!out' ':!node_modules' ':!.vscode')" ]; then
    git status --short | head -20; echo "FAIL uncommitted changes (ALLOW_DIRTY=1 to override)"; return 1; fi
  # Windows editors silently turn LF into CRLF: no new file, and no file that was LF at
  # the accepted release, may have CRLF now (files that were CRLF already keep it).
  local base; base=$(accepted_tag)
  if git rev-parse -q --verify "refs/tags/$base" >/dev/null; then
    local crlf="" name
    while IFS= read -r name; do
      if ! git cat-file -e "$base:$name" 2>/dev/null || ! git show "$base:$name" | grep -q $'\r'; then crlf+="$name"$'\n'; fi
    done < <(git diff -z --name-only --diff-filter=AM "$base" HEAD | xargs -0 -r git ls-files --eol -- | awk '$1=="i/crlf"{print $NF}')
    [ -z "$crlf" ] || { printf '%s' "$crlf"; echo "FAIL files turned to CRLF line endings since $base"; return 1; }
    echo "no file turned to CRLF since $base"
  else echo "tag $base not fetched: CRLF check skipped"; fi
  echo "HEAD $(git rev-parse HEAD)"
}
s_verifiers(){
  set -e
  python3 scripts/verify_e32_update_gate.py
  # The candidate check also compares the plan's previous_published_tag with the published releases (GitHub, R5-07)
  # and fails when it cannot read them; FINAL_CHECK_OFFLINE=1 skips that comparison on purpose (it says so).
  local gate_offline=(); [ "${FINAL_CHECK_OFFLINE:-0}" = 1 ] && gate_offline=(--offline)
  if [ "$FW" = "$(accepted_tag)" ]; then echo "release.json $FW is the accepted basis: no candidate check (development tree)"
  else python3 scripts/verify_e32_update_gate.py --candidate "$FW" ${gate_offline[@]+"${gate_offline[@]}"}; fi
  python3 scripts/verify_beta_release_inventory.py
  python3 scripts/inventory_boiler_writes.py --check
  python3 scripts/organize_releases.py --publication-notes-for "$FW" --output "$L/notes-fw.md"
  python3 scripts/organize_releases.py --publication-notes-for "ha-v$HA" --output "$L/notes-ha.md"
  python3 test/static_assets/run.py
  python3 scripts/generate_ems_fields.py --check
  python3 scripts/generate_ems_reference.py --check
  python3 scripts/generate_boiler_catalog.py --check
  python3 scripts/generate_display_codes.py --check
}
# The harnesses are built once, in parallel, into $L/harnesses and run from those binaries, as the CI job
# "harnesses" does (R5-19: `native` no longer compiles them a second time).
export HARNESS_OUT=$L/harnesses
s_harnesses(){
  set -e
  if [ $SERIAL = 1 ]; then pio_locked pkg install -e native; else wait_native_deps; cat "$L/deps.log"; fi
  ci "Build and run every native harness" > "$L/ci-harnesses.sh"
  locked bash -e "$L/ci-harnesses.sh"
  [ $SERIAL = 0 ] || locked bash test/interop/prepare_runners.sh
}
s_native(){
  set -e; ci "Run native tests" > "$L/ci-native.sh"
  locked bash -e "$L/ci-native.sh"
}
start_broker(){ # start_broker <port> <dir>
  D=$2; rm -rf "$D"; mkdir -p "$D"
  cp test/interop/mqtt-fixture/{acl,passwords} "$D/"; chmod 0700 "$D/passwords" "$D/acl"
  sed -e "s#/mosquitto/config#$D#g" -e "s#^listener 1883#listener $1 127.0.0.1#" test/interop/mqtt-fixture/mosquitto.conf > "$D/mosquitto.conf"
  /usr/sbin/mosquitto -c "$D/mosquitto.conf" & BROKER=$!; sleep 1
  kill -0 $BROKER || { echo "broker did not start"; return 1; }
  export OPENTHERMOSTAT_TEST_MQTT_PORT=$1
}
s_ha(){
  set -e
  if [ $SERIAL = 1 ]; then pio_locked pkg install -e native; bash test/interop/prepare_runners.sh; else wait_native_deps; fi
  # shellcheck disable=SC1091
  source "$HA_VENV/bin/activate"
  start_broker "$MQTT_PORT" "$L/mqtt-fixture"; trap 'kill $BROKER 2>/dev/null' EXIT
  ROOM_METRICS_EVIDENCE_DIR=out python -m pytest ha/tests ha/tests_native -q -o faulthandler_timeout=120 -p no:warnings --junitxml="$L/ha-acceptance.xml"
  python -B -m unittest discover -s scripts -p test_package_ha_release.py
  python -B -m unittest discover -s scripts -p test_prepare_original_report_pins.py
}
s_ha_min(){ # the minimum accepted Core, its package overlaid on the shared venv (venv untouched)
  set -e
  wait_native_deps
  # shellcheck disable=SC1091
  source "$HA_VENV/bin/activate"
  local core=2026.10.0
  local dl=/tmp/final-check-ha-dl ov=/tmp/final-check-ha-$core
  [ -f "$dl/homeassistant-$core-py3-none-any.whl" ] || { mkdir -p "$dl" && python -I -c "import hashlib,json,sys,urllib.request as u;d=json.load(u.urlopen('https://pypi.org/pypi/homeassistant/'+sys.argv[2]+'/json'));w=[f for f in d['urls'] if f['filename'].endswith('-py3-none-any.whl')][0];u.urlretrieve(w['url'],sys.argv[1]+'/'+w['filename']);assert hashlib.sha256(open(sys.argv[1]+'/'+w['filename'],'rb').read()).hexdigest()==w['digests']['sha256']" "$dl" "$core"; }
  [ -d "$ov/homeassistant" ] || python -I -c "import zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);[z.extract(n,sys.argv[2]) for n in z.namelist() if n.startswith('homeassistant/')]" "$dl/homeassistant-$core-py3-none-any.whl" "$ov"
  PYTHONPATH=$ov python -c "import homeassistant.const as c,sys;assert c.__version__==sys.argv[1],c.__version__;print('core',c.__version__)" "$core"
  # In lanes ha runs at the same time: own broker port and directory, own evidence directory
  # (out/ keeps the evidence of the accepted Core from step ha, as in CI).
  local port=$MQTT_PORT evidence=out
  [ $SERIAL = 1 ] || { port=$((MQTT_PORT + 1)); evidence=$L/ha_min-evidence; }
  start_broker "$port" "$L/mqtt-fixture-ha_min"; trap 'kill $BROKER 2>/dev/null' EXIT
  # As CI: the two provenance tests pin the tested 2026.10.2-.4 sources and are left out for this run only.
  PYTHONPATH=$ov ROOM_METRICS_EVIDENCE_DIR=$evidence python -m pytest ha/tests ha/tests_native -q -o faulthandler_timeout=120 -p no:warnings -p no:cacheprovider \
    --ignore=ha/tests_native/test_native_provider.py --ignore=ha/tests_native/test_native_schema_contract.py
}
s_browser(){
  local fail=0 jobs=1 cpus
  # In lanes a few tests at a time on the browser CPUs (no other lane runs there), never more than half the CPUs of
  # that set: more Chromiums than cores is a load CI never has, and only turns timing margins into flakes (R5-04).
  if [ $SERIAL = 0 ]; then
    cpus=$(cpu_count "$BROWSER_CPUS"); jobs=$(( cpus / 2 > 1 ? cpus / 2 : 1 ))
    echo "browser lane: $jobs tests at a time on $cpus CPUs ($BROWSER_CPUS)"
  fi
  BROWSER_TEST_LOGS=$L/browser BROWSER_TEST_DURATIONS=$DURATIONS bash test/run-browser-tests.sh --jobs "$jobs" | tee "$L/browser-results.txt" || fail=1
  # Remember how long each test took on this machine (the order of the next parallel run).
  mkdir -p "$(dirname "$DURATIONS")"
  { sed -nE 's/^(PASS|FAIL) ([^ ]+) \(([0-9]+)s\)$/\3 \2/p' "$L/browser-results.txt"; cat "$DURATIONS" 2>/dev/null; } \
    | awk 'NF==2 && !seen[$2]++' > "$DURATIONS.new" && mv "$DURATIONS.new" "$DURATIONS"
  ci "Test original Zigbee report producers (isolated APIs)" > "$L/ci-zigbee.sh"; bash -e "$L/ci-zigbee.sh" || fail=1
  ci "Test page modules without a browser" > "$L/ci-units.sh"; bash -e "$L/ci-units.sh" || fail=1
  return $fail
}
s_browser_stress(){
  if [ $SERIAL = 1 ]; then BROWSER_TEST_LOGS=$L/browser-stress bash test/run-browser-tests.sh --stress "$STRESS"
  else BROWSER_TEST_LOGS=$L/browser-stress BROWSER_TEST_DURATIONS=$DURATIONS STRESS_CPU=$STRESS_CPUS bash test/run-browser-tests.sh --stress "$STRESS"; fi
}
s_soak(){ wait_native_deps || return 1; SOAK_BUILD=$L/soak-build SOAK_OUT=$L/soak-out bash test/soak/run.sh smoke; }
# The learning and self-tuning on the anonymised real-data fixture (tools/replay/README.md), about 25 s with the build.
REPLAY_FIXTURE=test/fixtures/replay/house-shadow.csv
s_replay(){ wait_native_deps || return 1; REPLAY_BUILD=$L/replay-build REPLAY_OUT=$L/replay-out REPLAY_VERBOSE=1 python3 tools/replay/test_replay.py -v; }
s_fuzz(){ wait_native_deps || return 1; OUT=$L/fz-build WORK=$L/fz-work bash test/fuzz/run.sh smoke 60; }
build_env(){ # build_env <env>: build, sizes into $L/sizes-<env>.txt, OTA slot check
  local env=$1
  echo "== build $env"; pio_locked run -e "$env" > "$L/build-$env.log" 2>&1 || { tail -30 "$L/build-$env.log"; return 1; }
  { grep -E "^(RAM|Flash):" "$L/build-$env.log" | sed "s/^/$env /"
    echo "$env firmware.bin $(stat -c %s ".pio/build/$env/firmware.bin") bytes"; } > "$L/sizes-$env.txt"
  cat "$L/sizes-$env.txt"
  BUILD_ENVIRONMENT=$env bash -e "$L/ci-slots.sh"
}
build_e32v2_fs(){
  echo "== buildfs + E32 verifier"
  pio_locked run -e e32v2 -t buildfs > "$L/buildfs.log" 2>&1 || { tail -30 "$L/buildfs.log"; return 1; }
  python3 scripts/verify_e32v2.py
  python3 scripts/test_e32v2_verifier.py
}
s_builds(){
  set -e
  local env
  ci "Verify actual firmware image fits every OTA app slot" > "$L/ci-slots.sh"
  if [ $SERIAL = 1 ]; then
    for env in e32v2 esp32dev esp32s3; do build_env "$env"; done
    build_e32v2_fs
  else
    # The three environments at the same time (own build and library directories each);
    # buildfs needs the finished e32v2 build.
    local rc=0 pids=()
    ( set -e; build_env e32v2; build_e32v2_fs ) > "$L/builds-e32v2.log" 2>&1 & pids+=($!)
    ( set -e; build_env esp32dev ) > "$L/builds-esp32dev.log" 2>&1 & pids+=($!)
    ( set -e; build_env esp32s3 ) > "$L/builds-esp32s3.log" 2>&1 & pids+=($!)
    for env in "${pids[@]}"; do wait "$env" || rc=1; done
    cat "$L/builds-e32v2.log" "$L/builds-esp32dev.log" "$L/builds-esp32s3.log"
    [ $rc = 0 ] || return 1
  fi
  for env in e32v2 esp32dev esp32s3; do cat "$L/sizes-$env.txt"; done > "$L/SIZES.txt"
  python3 scripts/test_esp32_size_link.py
}
s_literal_reach(){ set -e; python3 scripts/e32v2_literal_reach.py .pio/build/e32v2; python3 scripts/test_e32v2_literal_reach.py; }
s_link_review(){ # no unreviewed vendor (path, member) pairs or new library archives in the e32v2 link
  python3 - <<'PY' | tee "$L/unreviewed.txt"
import json,sys
from pathlib import Path
sys.path.insert(0,'scripts')
from release_shipped import elf_allocations, map_inputs
review=json.loads(Path('docs/third-party/e32v2-link-review.json').read_text())
approved={(r['path'],r['member']) for r in review['retained_vendor_inputs']}
b=Path('.pio/build/e32v2')
for r in map_inputs((b/'firmware.map').read_text(),elf_allocations((b/'firmware.elf').read_bytes())):
    p=r['path']
    if p.startswith(('packages/framework-arduinoespressif32/tools/sdk/esp32/','packages/toolchain-xtensa-esp32/')) and (p,r['member']) not in approved:
        print('NEW',p,r['member'])
    if p.startswith('.pio/build/e32v2/') and r['archive'] and r['archive'] not in review['build_archives']:
        print('NEWLIB',r['archive'])
print('approved',len(approved))
PY
  ! grep -qE '^NEW' "$L/unreviewed.txt"
}
s_unittests(){
  "$HA_VENV/bin/python" -m unittest discover -s scripts -p 'test_*.py' > "$L/unittests-full.log" 2>&1; local rc=$?
  grep -E "^(ERROR|FAIL):|^Ran |^OK|^FAILED" "$L/unittests-full.log"
  # The suites of tools/ that the CI job "gates" runs (no device): the switch-over tools, the install acceptance kit
  # and the release preparation script.
  local dir
  for dir in tools/switchover tools/acceptance tools/dev; do
    if "$HA_VENV/bin/python" -I -B -m unittest discover -s "$dir" -p 'test_*.py' > "$L/unittests-${dir//\//-}.log" 2>&1; then
      echo "$dir: $(grep -E '^(Ran|OK)' "$L/unittests-${dir//\//-}.log" | tr '\n' ' ')"
    else rc=1; echo "FAIL $dir"; tail -15 "$L/unittests-${dir//\//-}.log"; fi
  done
  return $rc
}
s_replay_or_skip(){ if [ -f "$REPLAY_FIXTURE" ]; then step replay s_replay; else record replay "SKIP  replay (no $REPLAY_FIXTURE)"; fi; }

# --- dry run ------------------------------------------------------------------
if [ $DRY = 1 ]; then
  ok=0
  for t in pio node npx flock taskset clang g++ /usr/sbin/mosquitto python3 "$HA_VENV/bin/python"; do
    command -v "$t" >/dev/null 2>&1 && echo "have $t" || { echo "MISSING $t"; ok=1; }; done
  [ -d "$NODE_MODULES/playwright-core" ] && echo "have playwright-core ($NODE_MODULES)" || { echo "MISSING playwright-core in $NODE_MODULES"; ok=1; }
  for name in "Build and run every native harness" "Run native tests" "Test original Zigbee report producers (isolated APIs)" \
              "Test page modules without a browser" "Verify actual firmware image fits every OTA app slot"; do
    f="$L/dry-$(echo "$name" | tr -c 'a-zA-Z0-9' '_').sh"
    if ci "$name" > "$f" && bash -n "$f"; then echo "CI step ok: $name ($(wc -l < "$f") lines)"; else echo "CI step BROKEN: $name"; ok=1; fi
  done
  echo "browser tests: $(bash test/run-browser-tests.sh --list | wc -l)"
  for f in "$0" test/native_harnesses.sh test/run-browser-tests.sh test/interop/prepare_runners.sh tools/replay/run.sh; do bash -n "$f" && echo "bash -n $f ok" || ok=1; done
  echo "steps: $STEPS (fuzz only with FUZZ=1, browser_stress only with --stress N)"
  if [ $SERIAL = 1 ]; then echo "mode: serial"
  else echo "mode: lanes on $NCPU CPUs: stress $STRESS_CPUS, browser+fuzz $BROWSER_CPUS, pio/ha/host $WORK_CPUS"; fi
  ONLY=",static,verifiers,"; SKIP=""
  ALLOW_DIRTY=1 step static s_static
  step verifiers s_verifiers
  cat "$L/.results/static" "$L/.results/verifiers"
  exit $ok
fi

# --- full run -----------------------------------------------------------------
lane(){ # lane <name> <cpus> <function>: a group of steps in the background, pinned to <cpus>
  local name=$1 cpus=$2 fn=$3
  (
    LANE=$name; start=$(date +%s)
    taskset -cp "$cpus" "$BASHPID" > /dev/null || { echo "taskset $cpus failed"; exit 2; }
    "$fn"
    echo "$name $(( $(date +%s) - start ))s on CPUs $cpus" > "$L/.lanes/$name"
  ) &
}
lane_pio(){
  local name needed=0 waited
  for name in harnesses native builds ha ha_min soak replay fuzz; do want "$name" && needed=1; done
  if [ $needed = 1 ]; then
    # One hold of the shared PIO lock for the native dependencies, harnesses, native and builds.
    waited=$(date +%s); exec 8>> "$LOCK"; flock 8; PIO_LOCK_HELD=1
    echo "   PIO lock [pio] after $(( $(date +%s) - waited ))s of waiting for other worktrees" | tee "$L/pio-lock-wait.txt"
    native_deps > "$L/deps.log" 2>&1
  fi
  step harnesses s_harnesses
  if want native || want builds; then
    # native and builds at the same time (pio checks .pio/build/project.checksum first, once).
    if pio_build_dir_ready; then step native s_native & step builds s_builds & wait
    else echo "   could not prepare .pio/build: native and builds one after another"; step native s_native; step builds s_builds; fi
  fi
  if [ $needed = 1 ]; then flock -u 8; exec 8>&-; PIO_LOCK_HELD=0; fi
  step literal_reach s_literal_reach
  step link_review s_link_review
  step unittests s_unittests
}
lane_ha(){ step ha s_ha & step ha_min s_ha_min & wait; }
lane_host(){ step verifiers s_verifiers; step soak s_soak; s_replay_or_skip; }
lane_browser(){ step browser s_browser; step fuzz s_fuzz; }
lane_stress(){ step browser_stress s_browser_stress; }

step static s_static
if [ $SERIAL = 1 ]; then
  step verifiers s_verifiers
  step harnesses s_harnesses
  step native s_native
  step ha s_ha
  step ha_min s_ha_min
  step browser s_browser
  step browser_stress s_browser_stress
  step soak s_soak
  s_replay_or_skip
  step fuzz s_fuzz
  step builds s_builds
  step literal_reach s_literal_reach
  step link_review s_link_review
  step unittests s_unittests
else
  echo "lanes on $NCPU CPUs: stress $STRESS_CPUS, browser+fuzz $BROWSER_CPUS, pio/ha/host $WORK_CPUS"
  lane stress "$STRESS_CPUS" lane_stress
  lane browser "$BROWSER_CPUS" lane_browser
  lane pio "$WORK_CPUS" lane_pio
  lane ha "$WORK_CPUS" lane_ha
  lane host "$WORK_CPUS" lane_host
  wait
fi

FAILED=0
{
  echo "Final check $FW / HA $HA, $(date -u +%Y-%m-%dT%H:%M:%SZ), HEAD $(git rev-parse HEAD)"
  [ "$R" = "$SRC" ] || echo "checked in $R (copy of $SRC)"
  for name in $STEPS; do
    if [ -f "$L/.results/$name" ]; then cat "$L/.results/$name"; else echo "FAIL  $name (no result: its lane stopped early)"; fi
  done
  if [ $SERIAL = 0 ]; then echo "-- lanes (wall time)"; cat "$L"/.lanes/* 2>/dev/null; fi
  echo "-- total $(( $(date +%s) - T0 ))s ($([ $SERIAL = 1 ] && echo serial || echo lanes))"
  [ -f "$L/SIZES.txt" ] && { echo "-- sizes"; cat "$L/SIZES.txt"; }
} > "$L/SUMMARY.txt"
grep -q '^FAIL' "$L/SUMMARY.txt" && FAILED=1
{ [ $FAILED = 0 ] && echo "OVERALL PASS" || echo "OVERALL FAIL"; } >> "$L/SUMMARY.txt"
cat "$L/SUMMARY.txt"
exit $FAILED
