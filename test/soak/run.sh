#!/usr/bin/env bash
# Long-run host soak of the E32 control modules (test/soak/README.md).
#   run.sh [full|smoke|build|repro]      works from any directory
# Environment: CXX (g++), SOAK_BUILD (/tmp/soak-build), SOAK_OUT (/tmp/soak-out),
# SOAK_SEED (added to every scenario's seed), SOAK_JOBS (parallel scenarios),
# SOAK_ALLOW (comma-separated invariant ids that are reported but do not fail
# the run, e.g. known defects while their fix is pending).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MODE="${1:-full}"
L="$ROOT/.pio/libdeps/native"
B="${SOAK_BUILD:-/tmp/soak-build}"
O="${SOAK_OUT:-/tmp/soak-out}/$MODE"
CXX="${CXX:-g++}"
SEED="${SOAK_SEED:-0}"
JOBS="${SOAK_JOBS:-$(nproc)}"
ALLOW=",${SOAK_ALLOW:-},"
SAN=(-fsanitize=address,undefined -fno-omit-frame-pointer)
DBG=(-g1) # line tables: sanitizer reports keep file:line; builds ~40 % faster than -g
INC=(-I"$ROOT/src" -I"$ROOT/test/test_native/include" -I"$ROOT/test/test_native" -I"$L/esp32_utilities/src" -I"$L/cJSON")
mkdir -p "$B" "$O"

build() {
    local t0=$SECONDS
    [ -f "$L/cJSON/cJSON.c" ] || { echo "missing $L/cJSON (run the native PlatformIO env once)"; exit 2; }
    [ "$B/cjson.o" -nt "$L/cJSON/cJSON.c" ] || gcc -std=c11 -O1 "${DBG[@]}" "${SAN[@]}" -I"$L/cJSON" -c "$L/cJSON/cJSON.c" -o "$B/cjson.o"
    [ "$B/ems.o" -nt "$ROOT/src/EMS/EmsTelegram.cpp" ] || "$CXX" -std=gnu++2a -O1 "${DBG[@]}" "${SAN[@]}" "${INC[@]}" -c "$ROOT/src/EMS/EmsTelegram.cpp" -o "$B/ems.o"
    # Rebuild when the soak or any header under src/ changed.
    if [ ! -x "$B/soak" ] || [ "$ROOT/test/soak/soak.cpp" -nt "$B/soak" ] || [ -n "$(find "$ROOT/src" -name '*.h' -newer "$B/soak" -print -quit)" ]; then
        "$CXX" -std=gnu++2a -O1 "${DBG[@]}" -Wall -Wextra "${SAN[@]}" "${INC[@]}" -DSOAK_WRAP_LOCALTIME "$ROOT/test/soak/soak.cpp" \
            "$B/ems.o" "$B/cjson.o" -Wl,--wrap=localtime_r -o "$B/soak.new"
        mv "$B/soak.new" "$B/soak"
    fi
    echo "build: $B/soak ($((SECONDS - t0)) s)"
}

# name|arguments (no spaces inside an argument; seeds are offset by SOAK_SEED)
full_scenarios() {
    cat <<'LIST'
chain-ams|--scenario=chain --tz=CET-1CEST,M3.5.0,M10.5.0/3 --start=2026-09-20T12:34:50Z --days=60 --seed=1
chain-nyc-wrap|--scenario=chain --tz=EST5EDT,M3.2.0,M11.1.0 --start=2027-02-01T05:00:07Z --days=60 --seed=2 --uptime0=4293167296 --live-dhw-flow --boiler-outdoor --no-oom
chain-lordhowe|--scenario=chain --tz=<+1030>-10:30<+11>-11,M10.1.0,M4.1.0 --start=2027-03-20T00:00:00Z --days=30 --seed=3 --no-oom
chain-santiago|--scenario=chain --tz=<-04>4<-03>,M9.1.6/24,M4.1.6/24 --start=2027-03-25T03:00:00Z --days=21 --seed=4 --no-oom
chain-sydney-churn|--scenario=chain --tz=AEST-10AEDT,M10.1.0,M4.1.0/3 --start=2026-09-25T00:00:00Z --days=20 --seed=5 --edit-h=0.25 --no-oom
chain-kathmandu-30s|--scenario=chain --tz=<+0545>-5:45 --start=2026-12-01T00:00:00Z --days=60 --seed=6 --step-ms=30000 --no-oom
guard|--scenario=guard --days=60 --seed=7
active|--scenario=active --days=200 --seed=10
flow|--scenario=flow --days=60 --seed=9
supervisor|--scenario=supervisor --days=60 --seed=8
sizes|--scenario=sizes
repro|--scenario=repro
LIST
}
smoke_scenarios() {
    cat <<'LIST'
chain-ams|--scenario=chain --tz=CET-1CEST,M3.5.0,M10.5.0/3 --start=2026-10-24T20:00:00Z --days=1.5 --seed=1 --mqtt-s=60 --learned-s=60 --full-s=1800 --no-oom
chain-nyc-wrap|--scenario=chain --tz=EST5EDT,M3.2.0,M11.1.0 --start=2027-03-13T12:00:00Z --days=1.5 --seed=2 --uptime0=4293167296 --live-dhw-flow --boiler-outdoor --edit-h=0.5 --no-oom
guard|--scenario=guard --days=10 --seed=7
active|--scenario=active --days=3 --seed=10
flow|--scenario=flow --days=10 --seed=9
supervisor|--scenario=supervisor --days=30 --seed=8
sizes|--scenario=sizes
repro|--scenario=repro
LIST
}

run_list() {
    local list="$1" pids=() name args seed
    while IFS='|' read -r name args; do
        [ -n "$name" ] || continue
        seed=$(sed -n 's/.*--seed=\([0-9]*\).*/\1/p' <<<"$args")
        [ -z "$seed" ] || args="${args/--seed=$seed/--seed=$((seed + SEED))}"
        # shellcheck disable=SC2086 # the arguments are split on purpose
        ( rc=0; ASAN_OPTIONS=detect_leaks=1:abort_on_error=0 UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=0 \
            "$B/soak" --name="$name" --out="$O" $args >"$O/$name.log" 2>"$O/$name.err" || rc=$?; echo "$rc" >"$O/$name.rc" ) &
        pids+=($!)
        while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 1; done
    done <<<"$list"
    wait "${pids[@]}" 2>/dev/null || true
}

summary() {
    local status=0 name rc wall result san line id failing
    echo
    echo "==== soak $MODE: logs in $O"
    for f in "$O"/*.log; do
        [ -f "$f" ] || continue
        name=$(basename "$f" .log)
        [ -f "$O/$name.rc" ] || continue
        rc=$(cat "$O/$name.rc")
        wall=$(sed -n "s/^---- $name: \(.*\) wall$/\1/p" "$f")
        result=$(grep '^RESULT' "$f" || echo "RESULT $name CRASHED (exit $rc)")
        san=$(grep -c -E 'runtime error:|ERROR: AddressSanitizer|ERROR: LeakSanitizer' "$O/$name.err" || true)
        printf '%-24s %-44s %8s  sanitizer reports: %s\n' "$name" "${result#RESULT $name }" "$wall" "$san"
        failing=0
        while IFS= read -r line; do
            id=$(sed -n 's/^FAIL  [^:]*:\([^ ]*\).*/\1/p' <<<"$line")
            if [[ "$ALLOW" == *",$id,"* ]]; then echo "    (allowed) ${line:0:290}"; else echo "    ${line:0:300}"; failing=1; fi
        done < <(grep '^FAIL ' "$f" || true)
        # Exit 0: pass, 1: invariants failed (only allowed ones count as a pass), other: crash.
        if { [ "$rc" != 0 ] && [ "$rc" != 1 ]; } || [ "$failing" = 1 ] || [ "$san" != 0 ] || ! grep -q '^RESULT' "$f"; then status=1; fi
        if [ "$san" != 0 ]; then grep -E -m5 -A3 'runtime error:|ERROR: AddressSanitizer|ERROR: LeakSanitizer' "$O/$name.err" | sed 's/^/    /' || true; fi
    done
    if [ "$status" = 0 ]; then echo "SOAK $MODE: PASS"; else echo "SOAK $MODE: FAIL"; fi
    return $status
}

cd "$ROOT"
case "$MODE" in
    build) build ;;
    full|smoke)
        build
        t0=$SECONDS
        rm -f "$O"/*.log "$O"/*.err "$O"/*.rc
        if [ "$MODE" = full ]; then run_list "$(full_scenarios)"; else run_list "$(smoke_scenarios)"; fi
        echo "wall: $((SECONDS - t0)) s"
        summary ;;
    repro) build; rm -f "$O"/*.log "$O"/*.err "$O"/*.rc; run_list "repro|--scenario=repro"; summary ;;
    *) echo "usage: $0 [full|smoke|build|repro]"; exit 2 ;;
esac
