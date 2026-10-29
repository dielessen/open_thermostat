#!/usr/bin/env bash
# libFuzzer + ASan/UBSan harnesses for the E32 parsers of external input.
# Host-only: no device, radio, UART, broker or network contact.
#
#   test/fuzz/run.sh build                      build every harness
#   test/fuzz/run.sh smoke [seconds]            CI: build, then every harness N s in parallel (default 60)
#   test/fuzz/run.sh fuzz <target> <seconds> [workers]
#   test/fuzz/run.sh all <seconds> [workers]    every harness in parallel
#   test/fuzz/run.sh repro <target> <file...>   rerun crash/hang inputs
#   test/fuzz/run.sh cov <target>               line coverage of the corpus (llvm-cov)
#
# Env: OUT (default /tmp/fz-build), WORK (default /tmp/fz-work) for the
# growing corpora, crash files and logs. The checked-in seed corpus under
# test/fuzz/corpus/<target> is read-only input; new inputs go to $WORK.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${OUT:-/tmp/fz-build}"
WORK="${WORK:-/tmp/fz-work}"
CXX="${CXX:-clang++}"
CC="${CC:-clang}"
L="$ROOT/.pio/libdeps/native"
TARGETS=(ems_frame ble_advert ble_observer ble_settings room_plan control_json shadow boiler_services config_backup)

# Upper input sizes per harness (the product rejects larger inputs earlier).
max_len() {
  case "$1" in
    ems_frame) echo 2048 ;;          # up to 64 UART records of <=63 bytes
    ble_advert) echo 1700 ;;         # 7 header bytes + legacy (255) or extended (1650) advertisement
    ble_observer) echo 4096 ;;
    ble_settings) echo 6000 ;;
    room_plan) echo 4200 ;;          # /config/heating accepts 4096 bytes
    control_json) echo 8300 ;;       # parseControlJson accepts 8192 bytes
    shadow) echo 24000 ;;
    boiler_services) echo 4096 ;;
    config_backup) echo 25100 ;;     # POST /config/backup accepts 24576 + 512 bytes
  esac
}

need_tools() {
  command -v "$CXX" >/dev/null || { echo "clang++ missing: sudo apt-get install -y clang" >&2; exit 2; }
  [ -f /usr/include/mbedtls/ccm.h ] || { echo "Mbed TLS headers missing: sudo apt-get install -y libmbedtls-dev" >&2; exit 2; }
  [ -f "$L/cJSON/cJSON.c" ] || { echo "Missing $L/cJSON: run 'pio pkg install -e native' first" >&2; exit 2; }
}

SAN="-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer"
CXXFLAGS="-std=c++17 -include cstdint -O1 -g $SAN -DOPENTHERMOSTAT_E32V2 -I$ROOT/src -I$ROOT/test/test_native/include -I$ROOT/test/fuzz -I$L/esp32_utilities/src -I$L/cJSON"

build_one() {
  local t="$1"
  local extra=() sources=("$ROOT/test/fuzz/fuzz_$t.cpp")
  case "$t" in
    ems_frame) sources+=("$ROOT"/src/EMS/*.cpp) ;;
    ble_advert|ble_observer|config_backup) extra+=(-Wl,-Bstatic -lmbedcrypto -Wl,-Bdynamic) ;;
    boiler_services) sources+=("$ROOT/src/EMS/EmsTelegram.cpp") ;;
  esac
  "$CXX" $CXXFLAGS ${COVERAGE:+-fprofile-instr-generate -fcoverage-mapping} -fsanitize=fuzzer \
    "${sources[@]}" "$OUT/cjson.o" "${extra[@]}" -lpthread -o "$OUT/fuzz_$t"
}

build_cjson() {
  need_tools; mkdir -p "$OUT"
  [ -f "$OUT/cjson.o" ] || "$CC" -std=c11 -O1 -g $SAN -fsanitize=fuzzer-no-link \
    ${COVERAGE:+-fprofile-instr-generate -fcoverage-mapping} -I"$L/cJSON" -c "$L/cJSON/cJSON.c" -o "$OUT/cjson.o"
}

build() {
  build_cjson
  local pids=() t
  for t in "${TARGETS[@]}"; do build_one "$t" & pids+=($!); done
  local failed=0; for p in "${pids[@]}"; do wait "$p" || failed=1; done
  [ "$failed" = 0 ] || { echo "build failed" >&2; exit 1; }
  echo "built ${#TARGETS[@]} harnesses in $OUT"
}

export ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=1:abort_on_error=1:allocator_may_return_null=1}"
export UBSAN_OPTIONS="${UBSAN_OPTIONS:-halt_on_error=1:print_stacktrace=1}"

fuzz() {
  local t="$1" seconds="$2" workers="${3:-1}"
  local corpus="$WORK/corpus/$t" art="$WORK/artifacts/$t/"
  mkdir -p "$corpus" "$art" "$WORK/logs"
  local args=(-max_len="$(max_len "$t")" -timeout=2 -rss_limit_mb=2048 -max_total_time="$seconds"
              -artifact_prefix="$art" -print_final_stats=1 -report_slow_units=1
              -dict="$ROOT/test/fuzz/dict/$t.dict")
  [ -f "$ROOT/test/fuzz/dict/$t.dict" ] || unset 'args[${#args[@]}-1]'
  if [ "$workers" -gt 1 ]; then
    # -fork keeps fuzzing after a crash and merges all workers into one corpus.
    args+=(-fork="$workers" -ignore_crashes=1 -ignore_timeouts=1 -ignore_ooms=1)
  fi
  (cd "$WORK/logs" && "$OUT/fuzz_$t" "${args[@]}" "$corpus" "$ROOT/test/fuzz/corpus/$t") \
    >"$WORK/logs/$t.log" 2>&1 || true
  # slow-unit-* files (-report_slow_units=1) are reports, not failures: a busy
  # CI runner can take >1 s for one input. Hangs fail as timeout-* (>2 s).
  local n; n=$(find "$art" -type f ! -name 'slow-unit-*' | wc -l)
  echo "$t: $(grep -E 'stat::number_of_executed_units|#[0-9]+.*DONE|cov:' "$WORK/logs/$t.log" | tail -1) artifacts=$n"
  [ "$n" = 0 ]
}

case "${1:-}" in
  build) build ;;
  build-one) build_cjson; build_one "$2" ;;
  fuzz) [ -x "$OUT/fuzz_$2" ] || { build_cjson; build_one "$2"; }; fuzz "$2" "${3:-600}" "${4:-1}" ;;
  all)
    [ -x "$OUT/fuzz_${TARGETS[0]}" ] || build
    pids=(); for t in "${TARGETS[@]}"; do fuzz "$t" "${2:-600}" "${3:-1}" & pids+=($!); done
    status=0; for p in "${pids[@]}"; do wait "$p" || status=1; done; exit $status ;;
  smoke)
    # CI: every harness for N seconds side by side; fails on any crash/hang/leak file.
    build
    per="${2:-60}"
    pids=(); for t in "${TARGETS[@]}"; do fuzz "$t" "$per" 1 & pids+=($!); done
    status=0; for p in "${pids[@]}"; do wait "$p" || status=1; done; exit $status ;;
  repro)
    t="$2"; shift 2; [ -x "$OUT/fuzz_$t" ] || { build_cjson; build_one "$t"; }
    "$OUT/fuzz_$t" -timeout=2 -runs=1 "$@" ;;
  cov)
    t="$2"; OUT="$OUT-cov"; export COVERAGE=1; build_cjson; build_one "$t"
    OUT="${OUT%-cov}"
    rm -f "$WORK/$t.profraw"
    LLVM_PROFILE_FILE="$WORK/$t.profraw" "$OUT-cov/fuzz_$t" -runs=0 -timeout=10 "$WORK/corpus/$t" "$ROOT/test/fuzz/corpus/$t" >/dev/null 2>&1 || true
    llvm-profdata merge -sparse "$WORK/$t.profraw" -o "$WORK/$t.profdata"
    llvm-cov report "$OUT-cov/fuzz_$t" -instr-profile="$WORK/$t.profdata" "$ROOT/src" ;;
  *) sed -n '2,15p' "$0"; exit 2 ;;
esac
