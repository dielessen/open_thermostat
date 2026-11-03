cd "${WORKTREE:-/mnt/c/Users/m.dielessen/Downloads/open_thermostat-10-release}"
export MQTT_PORT=18911 PATH="$HOME/node/bin:$PATH" NODE_MODULES=/mnt/c/Users/m.dielessen/Downloads/open_thermostat-vscode-20261021/node_modules LOGDIR=/tmp/final-$(git rev-parse --short HEAD)
echo "logdir $LOGDIR head $(git rev-parse --short HEAD) start $(date +%H:%M)"
bash scripts/final_check.sh --stress 2 "$@" 2>&1 | tail -40
