#!/usr/bin/env bash
# Build the real-data replay against this tree's src/ and run it (tools/replay/README.md).
#
#   tools/replay/run.sh <data.csv> [more.csv ...] [replay options]   build if needed, run, print the summary
#   tools/replay/run.sh --build-only                                 only build
#
# Environment: REPLAY_BUILD (/tmp/openthermostat-replay) for the binary, REPLAY_OUT
# (<REPLAY_BUILD>/out) for <name>.json and <name>.txt, REPLAY_REV (a commit: build against
# `git archive <rev> src` instead of the working tree, e.g. the release candidate before a
# change), REPLAY_LIBDEPS (the PlatformIO native libraries with cJSON and esp32_utilities;
# default .pio/libdeps/native of this tree), CXX (g++).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
B="${REPLAY_BUILD:-/tmp/openthermostat-replay}"
O="${REPLAY_OUT:-$B/out}"
CXX="${CXX:-g++}"
L="${REPLAY_LIBDEPS:-$ROOT/.pio/libdeps/native}"
CJSON="$L/cJSON"
[ -f "$CJSON/cJSON.c" ] && [ -d "$L/esp32_utilities/src" ] \
    || { echo "run.sh: no cJSON/esp32_utilities in $L (run 'pio pkg install -e native' once, or set REPLAY_LIBDEPS)" >&2; exit 2; }
mkdir -p "$B" "$O"

SRC="$ROOT/src"
BIN="$B/replay"
if [ -n "${REPLAY_REV:-}" ]; then
    rev=$(git -C "$ROOT" rev-parse --short=12 "$REPLAY_REV")
    SRC="$B/src-$rev/src"
    BIN="$B/replay-$rev"
    [ -d "$SRC" ] || { mkdir -p "$B/src-$rev"; git -C "$ROOT" archive "$rev" src | tar -x -C "$B/src-$rev"; }
fi

# Rebuild when the driver, cJSON or any header under the source tree is newer than the binary.
if [ ! -x "$BIN" ] || [ "$ROOT/tools/replay/replay.cpp" -nt "$BIN" ] || [ -n "$(find "$SRC" -name '*.h' -newer "$BIN" -print -quit)" ]; then
    t0=$SECONDS
    "$CXX" -std=gnu++2a -O1 -g1 -Wall -Wextra -fsanitize=address,undefined -fno-omit-frame-pointer \
        -I"$SRC" -I"$ROOT/test/test_native/include" -I"$L/esp32_utilities/src" -I"$CJSON" \
        "$ROOT/tools/replay/replay.cpp" "$CJSON/cJSON.c" -o "$BIN.new"
    mv "$BIN.new" "$BIN"
    echo "run.sh: built $BIN ($((SECONDS - t0)) s)" >&2
fi
[ "${1:-}" = "--build-only" ] && exit 0
[ $# -gt 0 ] || { echo "usage: $0 <data.csv> [more.csv ...] [replay options] | --build-only" >&2; exit 2; }

# The first CSV names the outputs.
name=""
for a in "$@"; do case "$a" in *.csv) name=$(basename "$a" .csv); break ;; esac; done
name=${name:-replay}${REPLAY_REV:+-$rev}
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
    "$BIN" --json "$O/$name.json" --text "$O/$name.txt" "$@"
cat "$O/$name.txt"
echo
echo "run.sh: $O/$name.json"
