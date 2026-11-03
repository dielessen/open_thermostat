#!/bin/bash
# Run the browser regression tests listed in test/browser-tests.txt (one list
# for CI and scripts/final_check.sh). Each line is "<shard> <test file>"; the
# shard numbers are fixed in that file, so a test always runs in the same CI job.
#
#   test/run-browser-tests.sh                 every test, one after another
#   test/run-browser-tests.sh --shard 2/4     only shard 2 of 4 (CI job "browser (2/4)")
#   test/run-browser-tests.sh --jobs 4        every test, at most 4 tests at a time
#   test/run-browser-tests.sh --stress 3      every test 3 rounds, 4 copies at once pinned to
#                                             one CPU core: timing races show up here, not in CI
#   STRESS_CPU=0-5 test/run-browser-tests.sh --stress 3
#                                             the same load per test, six tests at a time, each
#                                             on its own core (its rounds stay one after another)
#   test/run-browser-tests.sh --list [--shard K/N]
#
# Needs node and playwright-core (NODE_PATH) with Chromium. A failing test and
# its last output lines also go into a GitHub annotation, because the job log
# itself needs a login. All tests of the selection run; the exit code is 1 when
# any failed. BROWSER_TEST_DURATIONS names an optional file of "<seconds> <test>"
# lines (scripts/final_check.sh keeps one): parallel runs then start the longest
# tests first. It only changes the order, never the selection.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2
LIST=test/browser-tests.txt
SHARD=""; STRESS=0; ONLY_LIST=0; JOBS=${BROWSER_TEST_JOBS:-1}
COPIES=${STRESS_COPIES:-4}; CPU=${STRESS_CPU:-0}; TIMEOUT=${BROWSER_TEST_TIMEOUT:-300}
LOGS=${BROWSER_TEST_LOGS:-${RUNNER_TEMP:-/tmp}/browser-tests}
DURATIONS=${BROWSER_TEST_DURATIONS:-}
while [ $# -gt 0 ]; do
  case "$1" in
    --shard) SHARD=$2; shift ;;
    --stress) STRESS=$2; shift ;;
    --jobs) JOBS=$2; shift ;;
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
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "--jobs needs a positive number" >&2; exit 2; }
mkdir -p "$LOGS"

annotate(){ # annotate <title> <log>
  [ -n "${GITHUB_ACTIONS:-}" ] || return 0
  echo "::error title=$1 on ${ImageOS:-unknown} ${ImageVersion:-}::$(tail -c 3000 "$2" | awk '{gsub(/%/,"%25");gsub(/\r/,"");printf "%s%%0A",$0}')"
}
logname(){ echo "$LOGS/$(echo "$1" | tr '/' '_')${2:+.$2}.log"; }
cpulist(){ # "0-2,5" -> "0 1 2 5"
  local part parts out=()
  IFS=, read -ra parts <<< "$1"
  for part in "${parts[@]}"; do
    if [[ "$part" =~ ^([0-9]+)-([0-9]+)$ ]]; then mapfile -t -O "${#out[@]}" out < <(seq "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}")
    elif [[ "$part" =~ ^[0-9]+$ ]]; then out+=("$part")
    else echo "bad CPU list $1" >&2; return 2; fi
  done
  echo "${out[@]}"
}

# Longest known tests first (unknown ones, e.g. new tests, before all known ones).
if [ -n "$DURATIONS" ] && [ -f "$DURATIONS" ] && { [ "$JOBS" -gt 1 ] || [ "$STRESS" -gt 0 ]; }; then
  mapfile -t tests < <(printf '%s\n' "${tests[@]}" | awk 'NR==FNR{if(NF==2)d[$2]=$1;next}{print ($0 in d?d[$0]:999999), FNR, $0}' "$DURATIONS" - \
                       | sort -k1,1nr -k2,2n | awk '{print $3}')
fi

stress_one(){ # stress_one <test> <cpu>: all rounds on one core, prints one result line
  local t=$1 cpu=$2 bad=0 round copy pid start total pids
  start=$(date +%s)
  for round in $(seq 1 "$STRESS"); do
    pids=()
    for copy in $(seq 1 "$COPIES"); do
      taskset -c "$cpu" timeout "$((TIMEOUT * 2))" node "$t" > "$(logname "$t" "r$round-c$copy")" 2>&1 & pids+=($!)
    done
    copy=0
    for pid in "${pids[@]}"; do
      copy=$((copy + 1))
      wait "$pid" || { bad=$((bad + 1)); echo "  FAIL $t round $round copy $copy: $(logname "$t" "r$round-c$copy")"; }
    done
  done
  total=$((STRESS * COPIES))
  if [ $bad = 0 ]; then echo "PASS $t ($total/$total under load, CPU $cpu, $(( $(date +%s) - start ))s)"
  else echo "FAIL $t ($((total - bad))/$total under load, CPU $cpu, $(( $(date +%s) - start ))s)"; return 1; fi
}
plain_one(){ # plain_one <test>: one run, prints one result line (and the log tail on failure)
  local t=$1 log start
  log=$(logname "$t"); start=$(date +%s)
  if timeout "$TIMEOUT" node "$t" > "$log" 2>&1; then
    echo "PASS $t ($(( $(date +%s) - start ))s)"
  else
    echo "FAIL $t ($(( $(date +%s) - start ))s)"; tail -40 "$log"
    annotate "Browser regression failed: $t" "$log"; return 1
  fi
}

failed=()
slots=()
if [ "$STRESS" -gt 0 ]; then
  command -v taskset >/dev/null || { echo "stress mode needs taskset" >&2; exit 2; }
  cpus=$(cpulist "$CPU") || exit 2
  read -ra slots <<< "$cpus"
elif [ "$JOBS" -gt 1 ]; then
  mapfile -t slots < <(seq 1 "$JOBS")
fi
if [ ${#slots[@]} -gt 0 ]; then
  # A pool with one test per slot (per CPU core under --stress); a result prints when its test ends.
  res=$(mktemp -d "$LOGS/.results.XXXXXX")
  declare -A slot_of=() test_of=()
  free=("${slots[@]}")
  collect(){ # wait for one running test to end and print its result
    local pid rc
    wait -n -p pid; rc=$?
    cat "$res/${test_of[$pid]//\//_}"
    [ $rc = 0 ] || failed+=("${test_of[$pid]}")
    free+=("${slot_of[$pid]}"); unset "slot_of[$pid]" "test_of[$pid]"
  }
  for t in "${tests[@]}"; do
    [ ${#free[@]} -gt 0 ] || collect
    slot=${free[0]}; free=("${free[@]:1}")
    if [ "$STRESS" -gt 0 ]; then stress_one "$t" "$slot" > "$res/${t//\//_}" 2>&1 &
    else plain_one "$t" > "$res/${t//\//_}" 2>&1 & fi
    slot_of[$!]=$slot; test_of[$!]=$t
  done
  while [ ${#test_of[@]} -gt 0 ]; do collect; done
  rm -rf "$res"
else
  for t in "${tests[@]}"; do plain_one "$t" || failed+=("$t"); done
fi
if [ ${#failed[@]} -gt 0 ]; then echo "FAILED ${#failed[@]} of ${#tests[@]}: ${failed[*]}"; exit 1; fi
summary="PASS all ${#tests[@]} browser tests"
[ -n "$SHARD" ] && summary+=" of shard $SHARD"
[ "$JOBS" -gt 1 ] && [ "$STRESS" = 0 ] && summary+=" ($JOBS at a time)"
[ "$STRESS" -gt 0 ] && summary+=" ($STRESS rounds x $COPIES copies on CPU $CPU, one test per core)"
echo "$summary"
