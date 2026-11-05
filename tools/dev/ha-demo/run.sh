#!/bin/bash
# OpenThermostat demo Home Assistant: real Core with the integration, a fake E32 and screenshots of the
# generated dashboard. Everything runs in a private network namespace (only loopback, no route out), so
# nothing can reach a real E32, broker or Home Assistant. README.md has the details.
#
#   bash tools/dev/ha-demo/run.sh --out <dir> [--languages en,nl] [--work <dir>] [--keep-work]
#
# Environment (defaults): HA_VENV (~/venvs/ha), NODE ($HOME/node/bin/node), NODE_PATH (the repository's
# node_modules with playwright-core), CHROME (Playwright's Chromium 1243), MOSQUITTO (/usr/sbin/mosquitto),
# OPENTHERMOSTAT_DEMO_CACHE (~/.cache/openthermostat-ha-demo: the frontend package, downloaded once).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
HA_VENV=${HA_VENV:-$HOME/venvs/ha}
CACHE=${OPENTHERMOSTAT_DEMO_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/openthermostat-ha-demo}
MOSQUITTO=${MOSQUITTO:-/usr/sbin/mosquitto}

OUT=""; WORK=""; KEEP=0; PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT=$2; shift ;;
    --work) WORK=$2; shift ;;
    --keep-work) KEEP=1 ;;
    *) PASS+=("$1") ;;
  esac; shift
done
[ -n "$OUT" ] || { echo "usage: $0 --out <dir> [--languages en,nl] [--work <dir>] [--keep-work]"; exit 2; }
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)

NODE=${NODE:-$HOME/node/bin/node}
CHROME=${CHROME:-$HOME/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome}
export NODE_PATH=${NODE_PATH:-$REPO/node_modules}
PY=$HA_VENV/bin/python
[ -x "$PY" ] && [ -x "$HA_VENV/bin/hass" ] || { echo "no Home Assistant venv at $HA_VENV (HA_VENV=...)"; exit 2; }
[ -x "$MOSQUITTO" ] || { echo "no mosquitto at $MOSQUITTO (MOSQUITTO=...)"; exit 2; }
[ -x "$NODE" ] && [ -x "$CHROME" ] || { echo "needs node ($NODE) and Chromium ($CHROME): NODE=..., CHROME=..."; exit 2; }
[ -d "$NODE_PATH/playwright-core" ] || { echo "no playwright-core in NODE_PATH ($NODE_PATH)"; exit 2; }
command -v unshare >/dev/null && command -v ip >/dev/null || { echo "needs unshare (util-linux) and ip (iproute2)"; exit 2; }

# What the venv of the tests lacks (the frontend, the packages of the integrations Core always loads): downloaded
# once from PyPI at this Core's own pins into the cache, outside the venv (deps.py). Home Assistant runs with
# --skip-pip and that directory on PYTHONPATH, so it installs nothing and the venv stays as it is.
CORE=$("$PY" -c 'import homeassistant.const as c; print(c.__version__)')
mkdir -p "$CACHE"
DEPS=$("$PY" "$HERE/deps.py" "$CACHE/deps-$CORE") || { echo "could not prepare the demo's packages"; exit 2; }
echo "Home Assistant Core $CORE, demo packages in $DEPS"

if [ -z "$WORK" ]; then WORK=$(mktemp -d "${TMPDIR:-/tmp}/openthermostat-ha-demo.XXXXXX"); else mkdir -p "$WORK"; fi
WORK=$(cd "$WORK" && pwd)
echo "work directory $WORK (the demo Home Assistant's config, logs and the throwaway demo login)"

T0=$(date +%s)
rc=0
# A user, network, mount and PID namespace: the demo's processes see only loopback, and all of them end
# with demo.py (PID 1 of the namespace) whatever happens.
unshare --user --map-root-user --net --pid --fork --mount-proc -- \
  "$PY" -u "$HERE/demo.py" --out "$OUT" --work "$WORK" --hass "$HA_VENV/bin/hass" --mosquitto "$MOSQUITTO" \
  --frontend-deps "$DEPS" --node "$NODE" --chrome "$CHROME" "${PASS[@]}" || rc=$?

# Nothing outlives the namespace (the kernel ends every process of a PID namespace with its first one); checked
# anyway: Home Assistant, the broker, the fake E32 and the orchestrator each name the work directory on their
# command line in their own way.
left=$(pgrep -f -- "(-c $WORK/ha( |\$)|-c $WORK/mosquitto\.conf|--state $WORK/e32-state\.json|demo\.py --out .* --work $WORK( |\$))" || true)
if [ -n "$left" ]; then echo "FAIL processes left behind: $left"; rc=1; else echo "no demo process left behind"; fi
echo "took $(( $(date +%s) - T0 )) s; screenshots in $OUT"
if [ $KEEP = 0 ] && [ $rc = 0 ]; then
  mkdir -p "$OUT/logs"; cp "$WORK"/logs/*.log "$WORK/demo.log" "$OUT/logs/" 2>/dev/null || true
  cp "$WORK/ha/home-assistant.log" "$OUT/logs/" 2>/dev/null || true
  rm -rf "$WORK"
else
  echo "work directory kept: $WORK"
fi
exit $rc
