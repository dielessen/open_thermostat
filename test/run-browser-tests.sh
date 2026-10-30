#!/bin/bash
# Run the browser regression tests listed in test/browser-tests.txt (one list
# for CI and scripts/final_check.sh). Each line is "<shard> <test file>"; the
# shard numbers are fixed in that file, so a test always runs in the same CI job.
#
#   test/run-browser-tests.sh                 every test, one after another
#   test/run-browser-tests.sh --shard 2/4     only shard 2 of 4 (CI job "browser (2/4)")
#   test/run-browser-tests.sh --stress 3      every test 3 rounds, 4 copies at once pinned to
#                                             one CPU core: timing races show up here, not in CI
#   test/run-browser-tests.sh --list [--shard K/N]
#
# Needs node and playwright-core (NODE_PATH) with Chromium. A failing test and
# its last output lines also go into a GitHub annotation, because the job log
# itself needs a login. All tests of the selection run; the exit code is 1 when
# any failed.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
LIST=test/browser-tests.txt
SHARD=""; STRESS=0; ONLY_LIST=0
COPIES=${STRESS_COPIES:-4}; CPU=${STRESS_CPU:-0}; TIMEOUT=${BROWSER_TEST_TIMEOUT:-300}
LOGS=${BROWSER_TEST_LOGS:-${RUNNER_TEMP:-/tmp}/browser-tests}
while [ $# -gt 0 ]; do
  case "$1" in
    --shard) SHARD=$2; shift ;;
    --stress) STRESS=$2; shift ;;
    --list) ONLY_LIST=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac; shift
done

shards=$(awk '!/^[[:space:]]*(#|$)/{print $1}' "$LIST" | sort -n | tail -1)
if [ -n "$SHARD" ]; then
  k=${SHARD%/*}; n=${SHARD#*/}
  [ "$n" = "$shards" ] || { echo "$LIST has $shards shards, not $n" >&2; exit 2; }
  [ "$k" -ge 1 ] && [ "$k" -le "$n" ] || { echo "no shard $SHARD" >&2; exit 2; }
fi
mapfile -t tests < <(awk -v k="${k:-}" '!/^[[:space:]]*(#|$)/ && (k=="" || $1==k) {print $2}' "$LIST")
[ ${#tests[@]} -gt 0 ] || { echo "no tests selected" >&2; exit 2; }
if [ $ONLY_LIST = 1 ]; then printf '%s\n' "${tests[@]}"; exit 0; fi
mkdir -p "$LOGS"

annotate(){ # annotate <title> <log>
  [ -n "${GITHUB_ACTIONS:-}" ] || return 0
  echo "::error title=$1 on ${ImageOS:-unknown} ${ImageVersion:-}::$(tail -c 3000 "$2" | awk '{gsub(/%/,"%25");gsub(/\r/,"");printf "%s%%0A",$0}')"
}
logname(){ echo "$LOGS/$(echo "$1" | tr '/' '_')${2:+.$2}.log"; }

failed=()
if [ "$STRESS" -gt 0 ]; then
  command -v taskset >/dev/null || { echo "stress mode needs taskset" >&2; exit 2; }
  for t in "${tests[@]}"; do
    bad=0
    for round in $(seq 1 "$STRESS"); do
      pids=()
      for copy in $(seq 1 "$COPIES"); do
        taskset -c "$CPU" timeout "$((TIMEOUT * 2))" node "$t" > "$(logname "$t" "r$round-c$copy")" 2>&1 & pids+=($!)
      done
      copy=0
      for pid in "${pids[@]}"; do
        copy=$((copy + 1))
        wait "$pid" || { bad=$((bad + 1)); echo "  FAIL $t round $round copy $copy: $(logname "$t" "r$round-c$copy")"; }
      done
    done
    total=$((STRESS * COPIES))
    if [ $bad = 0 ]; then echo "PASS $t ($total/$total under load)"; else echo "FAIL $t ($((total - bad))/$total under load)"; failed+=("$t"); fi
  done
else
  for t in "${tests[@]}"; do
    log=$(logname "$t"); start=$(date +%s)
    if timeout "$TIMEOUT" node "$t" > "$log" 2>&1; then
      echo "PASS $t ($(( $(date +%s) - start ))s)"
    else
      echo "FAIL $t ($(( $(date +%s) - start ))s)"; tail -40 "$log"
      annotate "Browser regression failed: $t" "$log"; failed+=("$t")
    fi
  done
fi
if [ ${#failed[@]} -gt 0 ]; then echo "FAILED ${#failed[@]} of ${#tests[@]}: ${failed[*]}"; exit 1; fi
summary="PASS all ${#tests[@]} browser tests"
[ -n "$SHARD" ] && summary+=" of shard $SHARD"
[ "$STRESS" -gt 0 ] && summary+=" ($STRESS rounds x $COPIES copies on CPU $CPU)"
echo "$summary"
