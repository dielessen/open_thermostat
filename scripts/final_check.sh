#!/bin/bash
# The whole local pre-tag check, with a PASS/FAIL summary (docs/RELEASING.md).
# Run it on the exact commit that will be tagged, in WSL or Linux.
#
#   scripts/final_check.sh                         every step (about 45-75 min)
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
# Environment (defaults in brackets): NODE_MODULES [<repo>/node_modules] with
# playwright-core; HA_VENV [~/venvs/ha] with ha/requirements-test-native.txt;
# PIO_VENV [~/venvs/pio] with platformio 6.2.0; LOGDIR [/tmp/final-check];
# PIO_LOCK [/tmp/openthermostat-pio.lock], shared by worktrees that build at the
# same time; MQTT_PORT [18839] for a local mosquitto (/usr/sbin/mosquitto).
set -u
R=$(cd "$(dirname "$0")/.." && pwd)
NODE_MODULES=${NODE_MODULES:-$R/node_modules}
HA_VENV=${HA_VENV:-$HOME/venvs/ha}
PIO_VENV=${PIO_VENV:-$HOME/venvs/pio}
L=${LOGDIR:-/tmp/final-check}
LOCK=${PIO_LOCK:-/tmp/openthermostat-pio.lock}
MQTT_PORT=${MQTT_PORT:-18839}
WF=$R/.github/workflows/build.yml
STEPS="static verifiers harnesses native ha ha_min browser browser_stress soak fuzz builds literal_reach link_review unittests"

DRY=0; ONLY=""; SKIP=""; STRESS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry) DRY=1 ;;
    --only) ONLY=",$2,"; shift ;;
    --skip) SKIP=",$2,"; shift ;;
    --stress) STRESS=$2; shift ;;
    *) echo "unknown option $1"; exit 2 ;;
  esac; shift
done
[ "${FUZZ:-0}" = 1 ] || SKIP="$SKIP,fuzz,"
[ "$STRESS" -gt 0 ] || SKIP="$SKIP,browser_stress,"

export PATH="$HOME/node/bin:$PIO_VENV/bin:$HA_VENV/bin:$PATH"
export NODE_PATH=$NODE_MODULES ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1
rm -rf "$L"; mkdir -p "$L"
cd "$R" || exit 2
FW=$(python3 -c "import json;print(json.load(open('release.json'))['version'])")
HA=$(python3 -c "import json;print(json.load(open('ha/config/custom_components/open_thermostat/manifest.json'))['version'])")
declare -a RESULTS=()
FAILED=0

want(){ case "$ONLY" in "") ;; *",$1,"*) ;; *) return 1 ;; esac; case "$SKIP" in *",$1,"*) return 1 ;; esac; return 0; }
step(){ # step <name> <function>: run, log, record
  local name=$1 fn=$2 start rc secs
  if ! want "$name"; then RESULTS+=("SKIP  $name"); return; fi
  start=$(date +%s); echo "== $name"
  ( set -o pipefail; "$fn" ) > "$L/$name.log" 2>&1; rc=$?
  secs=$(( $(date +%s) - start ))
  if [ $rc = 0 ]; then RESULTS+=("PASS  $name (${secs}s)"); else RESULTS+=("FAIL  $name (${secs}s, rc=$rc, log $L/$name.log)"); FAILED=1; tail -15 "$L/$name.log"; fi
}
ci(){ python3 scripts/ci_step.py "$WF" "$@"; }
pio_locked(){ flock "$LOCK" pio "$@"; }
accepted_tag(){ python3 -c "import json;print(json.load(open('docs/modern-thermostat/E32-UPDATE-GATE.json'))['accepted']['tag'])"; }

# --- steps --------------------------------------------------------------------
s_static(){
  echo "release.json $FW, manifest.json $HA"
  grep -q "e32-week-card-$HA.js" ha/config/custom_components/open_thermostat/e32_week.py \
    && grep -q "week-editor-$HA.js" ha/config/custom_components/open_thermostat/frontend/e32-week-card.js \
    || { echo "FAIL frontend asset URLs do not carry $HA"; return 1; }
  [ "$(grep -c 'constexpr bool emsActiveHeatAllowed = false;' src/Board.h)" -ge 2 ] \
    && ! grep -q 'emsActiveHeatAllowed = true' src/Board.h || { echo "FAIL active heat gate is not locked"; return 1; }
  echo "active heat gate locked (board::emsActiveHeatAllowed = false)"
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
  if [ "$FW" = "$(accepted_tag)" ]; then echo "release.json $FW is the accepted basis: no candidate check (development tree)"
  else python3 scripts/verify_e32_update_gate.py --candidate "$FW"; fi
  python3 scripts/verify_beta_release_inventory.py
  python3 scripts/inventory_boiler_writes.py --check
  python3 scripts/organize_releases.py --publication-notes-for "$FW" --output "$L/notes-fw.md"
  python3 scripts/organize_releases.py --publication-notes-for "ha-v$HA" --output "$L/notes-ha.md"
  python3 test/static_assets/run.py
  python3 scripts/generate_ems_fields.py --check
  python3 scripts/generate_ems_reference.py --check
  python3 scripts/generate_boiler_catalog.py --check
}
s_harnesses(){ set -e; pio_locked pkg install -e native; flock "$LOCK" bash test/native_harnesses.sh build; flock "$LOCK" bash test/interop/prepare_runners.sh; }
s_native(){ set -e; ci "Run native tests" > "$L/ci-native.sh"; flock "$LOCK" bash -e "$L/ci-native.sh"; }
start_broker(){
  D=$L/mqtt-fixture; rm -rf "$D"; mkdir -p "$D"
  cp test/interop/mqtt-fixture/{acl,passwords} "$D/"; chmod 0700 "$D/passwords" "$D/acl"
  sed -e "s#/mosquitto/config#$D#g" -e "s#^listener 1883#listener $MQTT_PORT 127.0.0.1#" test/interop/mqtt-fixture/mosquitto.conf > "$D/mosquitto.conf"
  /usr/sbin/mosquitto -c "$D/mosquitto.conf" & BROKER=$!; sleep 1
  kill -0 $BROKER || { echo "broker did not start"; return 1; }
  export OPENTHERMOSTAT_TEST_MQTT_PORT=$MQTT_PORT
}
s_ha(){
  set -e
  pio_locked pkg install -e native
  bash test/interop/prepare_runners.sh
  # shellcheck disable=SC1091
  source "$HA_VENV/bin/activate"
  start_broker; trap 'kill $BROKER 2>/dev/null' EXIT
  ROOM_METRICS_EVIDENCE_DIR=out python -m pytest ha/tests ha/tests_native -q -o faulthandler_timeout=120 -p no:warnings --junitxml="$L/ha-acceptance.xml"
  python -B -m unittest discover -s scripts -p test_package_ha_release.py
  python -B -m unittest discover -s scripts -p test_prepare_original_report_pins.py
}
s_ha_min(){ # the minimum accepted Core, its package overlaid on the shared venv (venv untouched)
  set -e
  # shellcheck disable=SC1091
  source "$HA_VENV/bin/activate"
  local core=2026.10.0
  local dl=/tmp/final-check-ha-dl ov=/tmp/final-check-ha-$core
  [ -f "$dl/homeassistant-$core-py3-none-any.whl" ] || { mkdir -p "$dl" && python -I -c "import hashlib,json,sys,urllib.request as u;d=json.load(u.urlopen('https://pypi.org/pypi/homeassistant/'+sys.argv[2]+'/json'));w=[f for f in d['urls'] if f['filename'].endswith('-py3-none-any.whl')][0];u.urlretrieve(w['url'],sys.argv[1]+'/'+w['filename']);assert hashlib.sha256(open(sys.argv[1]+'/'+w['filename'],'rb').read()).hexdigest()==w['digests']['sha256']" "$dl" "$core"; }
  [ -d "$ov/homeassistant" ] || python -I -c "import zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);[z.extract(n,sys.argv[2]) for n in z.namelist() if n.startswith('homeassistant/')]" "$dl/homeassistant-$core-py3-none-any.whl" "$ov"
  PYTHONPATH=$ov python -c "import homeassistant.const as c,sys;assert c.__version__==sys.argv[1],c.__version__;print('core',c.__version__)" "$core"
  start_broker; trap 'kill $BROKER 2>/dev/null' EXIT
  # As CI: the two provenance tests pin the tested 2026.10.2-.4 sources and are left out for this run only.
  PYTHONPATH=$ov ROOM_METRICS_EVIDENCE_DIR=out python -m pytest ha/tests ha/tests_native -q -o faulthandler_timeout=120 -p no:warnings -p no:cacheprovider \
    --ignore=ha/tests_native/test_native_provider.py --ignore=ha/tests_native/test_native_schema_contract.py
}
s_browser(){
  local fail=0
  BROWSER_TEST_LOGS=$L/browser bash test/run-browser-tests.sh || fail=1
  ci "Test original Zigbee report producers (isolated APIs)" > "$L/ci-zigbee.sh"; bash -e "$L/ci-zigbee.sh" || fail=1
  ci "Test page modules without a browser" > "$L/ci-units.sh"; bash -e "$L/ci-units.sh" || fail=1
  return $fail
}
s_browser_stress(){ BROWSER_TEST_LOGS=$L/browser-stress bash test/run-browser-tests.sh --stress "$STRESS"; }
s_soak(){ SOAK_BUILD=$L/soak-build SOAK_OUT=$L/soak-out bash test/soak/run.sh smoke; }
s_fuzz(){ OUT=$L/fz-build WORK=$L/fz-work bash test/fuzz/run.sh smoke 60; }
s_builds(){
  set -e
  local env
  ci "Verify actual firmware image fits every OTA app slot" > "$L/ci-slots.sh"
  for env in e32v2 esp32dev esp32s3; do
    echo "== build $env"; pio_locked run -e "$env" > "$L/build-$env.log" 2>&1 || { tail -30 "$L/build-$env.log"; return 1; }
    grep -E "^(RAM|Flash):" "$L/build-$env.log" | sed "s/^/$env /" | tee -a "$L/SIZES.txt"
    echo "$env firmware.bin $(stat -c %s ".pio/build/$env/firmware.bin") bytes" | tee -a "$L/SIZES.txt"
    BUILD_ENVIRONMENT=$env bash -e "$L/ci-slots.sh"
  done
  echo "== buildfs + E32 verifier"
  pio_locked run -e e32v2 -t buildfs > "$L/buildfs.log" 2>&1 || { tail -30 "$L/buildfs.log"; return 1; }
  python3 scripts/verify_e32v2.py
  python3 scripts/test_e32v2_verifier.py
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
s_unittests(){ "$HA_VENV/bin/python" -m unittest discover -s scripts -p 'test_*.py' > "$L/unittests-full.log" 2>&1; local rc=$?; grep -E "^(ERROR|FAIL):|^Ran |^OK|^FAILED" "$L/unittests-full.log"; return $rc; }

# --- dry run ------------------------------------------------------------------
if [ $DRY = 1 ]; then
  ok=0
  for t in pio node npx flock taskset clang g++ /usr/sbin/mosquitto python3 "$HA_VENV/bin/python"; do
    command -v "$t" >/dev/null 2>&1 && echo "have $t" || { echo "MISSING $t"; ok=1; }; done
  [ -d "$NODE_MODULES/playwright-core" ] && echo "have playwright-core ($NODE_MODULES)" || { echo "MISSING playwright-core in $NODE_MODULES"; ok=1; }
  for name in "Run native tests" "Test original Zigbee report producers (isolated APIs)" "Test page modules without a browser" \
              "Verify actual firmware image fits every OTA app slot"; do
    f="$L/dry-$(echo "$name" | tr -c 'a-zA-Z0-9' '_').sh"
    if ci "$name" > "$f" && bash -n "$f"; then echo "CI step ok: $name ($(wc -l < "$f") lines)"; else echo "CI step BROKEN: $name"; ok=1; fi
  done
  echo "browser tests: $(bash test/run-browser-tests.sh --list | wc -l)"
  for f in "$0" test/native_harnesses.sh test/run-browser-tests.sh test/interop/prepare_runners.sh; do bash -n "$f" && echo "bash -n $f ok" || ok=1; done
  echo "steps: $STEPS (fuzz only with FUZZ=1, browser_stress only with --stress N)"
  ONLY=",static,verifiers,"; SKIP=""
  ALLOW_DIRTY=1 step static s_static
  step verifiers s_verifiers
  printf '%s\n' "${RESULTS[@]}"
  exit $ok
fi

# --- full run -----------------------------------------------------------------
step static s_static
step verifiers s_verifiers
step harnesses s_harnesses
step native s_native
step ha s_ha
step ha_min s_ha_min
step browser s_browser
step browser_stress s_browser_stress
step soak s_soak
step fuzz s_fuzz
step builds s_builds
step literal_reach s_literal_reach
step link_review s_link_review
step unittests s_unittests

{
  echo "Final check $FW / HA $HA, $(date -u +%Y-%m-%dT%H:%M:%SZ), HEAD $(git rev-parse HEAD)"
  printf '%s\n' "${RESULTS[@]}"
  [ -f "$L/SIZES.txt" ] && { echo "-- sizes"; cat "$L/SIZES.txt"; }
  [ $FAILED = 0 ] && echo "OVERALL PASS" || echo "OVERALL FAIL"
} | tee "$L/SUMMARY.txt"
exit $FAILED
