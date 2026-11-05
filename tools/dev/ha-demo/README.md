# Demo Home Assistant: real screenshots of the dashboard

Shows the generated OpenThermostat dashboard as it really looks, before anyone installs it: a real Home
Assistant Core with this tree's integration, a fake E32 on a local MQTT broker, a day of history, and
Playwright screenshots of every view. Nothing touches a real E32, broker or Home Assistant.

```sh
bash tools/dev/ha-demo/run.sh --out <dir>
```

From Windows (Git Bash), on a copy of the worktree on the WSL disk:

```sh
export MSYS_NO_PATHCONV=1
wsl -e bash -lc 'bash /tmp/copytree.sh /mnt/c/Users/m.dielessen/Downloads/<worktree> ~/.cache/openthermostat-final-check/tree-<name> \
  && cd ~/.cache/openthermostat-final-check/tree-<name> \
  && NODE_PATH=/mnt/c/Users/m.dielessen/Downloads/open_thermostat-vscode-20261021/node_modules bash tools/dev/ha-demo/run.sh --out /tmp/ha-demo-shots'
```

Options: `--languages en,nl` (default both), `--widths 390,1280`, `--themes light,dark`, `--work <dir>` (default a
new temporary directory), `--keep-work` (keep it: the demo's Home Assistant config, database and logs).
About five minutes for the full set (72 pictures, measured 5 min 6 s); the first run also installs about 340 MB of
packages into the cache once.

## What it does

1. **An isolated network.** `run.sh` starts everything in a private user, network, mount and PID namespace
   (`unshare`): its only interface is loopback, with `127.0.0.1` and the fake E32's private address
   `10.77.0.2`, and there is no route anywhere else, so `192.168.1.x` is unreachable by construction. When the
   orchestrator ends, the kernel ends every process of the namespace; `run.sh` checks with `pgrep` afterwards.
2. **The parts.** mosquitto on `127.0.0.1:18931` (anonymous, no persistence); the fake E32 (`fake_e32.py`) with
   its web API on `http://10.77.0.2` (the integration refuses loopback E32 addresses, so the address is a private
   one that exists only in the namespace) and its retained telemetry under `openthermostat/v1/`; Home Assistant
   Core from `~/venvs/ha` (the tests' venv) with a temporary config directory, `--skip-pip`, on
   `127.0.0.1:18930`, the integration copied in as a custom component.
3. **Set-up through Home Assistant's own APIs.** Onboarding (owner user, core config, analytics, integration
   step; the user `demo` gets a throwaway password written only in the work directory), the HTTP settings
   confirmed (Core 2026.10 moves YAML `http:` into a trial it reverts after 5 minutes), the MQTT entry, the
   OpenThermostat installation (config flow), Configure → E32 connection against the fake E32 (login, CSRF,
   device settings with ETag, restart, room plan; the same contract the firmware has), and Configure → Energy and
   outdoor temperature (an outdoor sensor, 22 kW). A tado-style thermostat, the bathroom thermostat and the
   outdoor temperature are plain states, as another integration would provide them.
4. **The past.** Home Assistant is stopped and `history.py` writes 30 hours of states and 8 days of statistics
   into its recorder database, the way the recorder does, plus the integration's own day stores (gas per post,
   burner starts and time), so the 24-hour graphs, the house card's day strip, "gas today", the week's bars and
   the day statistics show something. Everything comes from one timeline in `scenario.py`, the same one the fake
   E32 reports from.
5. **Screenshots.** Home Assistant starts again in each language; `shoot.cjs` (playwright-core, Chromium, logged in
   with the owner's tokens) takes every view full length, at each width and theme, and close-ups of the house
   card, the Boiler view's "Now" section and the heating-curve card. Notices caused by the demo itself (the
   http YAML deprecation, setup errors of integrations whose packages are left out) are dismissed; the
   integration's own repairs and notifications stay.

Output, in `<dir>`: `<language>-<width>-<theme>-<n>-<view>.png` (overview, rooms, week-program, boiler, learning,
diagnostics), `<language>-<width>-<theme>-closeup-{house-card,boiler-now,heating-curve}.png`,
`shots-<language>.json` (what was taken, browser console errors) and `logs/` (Home Assistant, the fake E32, the
broker, the orchestrator).

## The demo house (`scenario.py`)

Like the owner's (E32 in control, "active"): the living room (floor heating, a tado-style HA thermostat and a
Bluetooth thermometer) at 20.4 °C aiming at 21 °C after a window was open, two radiator rooms switched off; a
Nefit EcomLine-type boiler on the EMS bus with the owner's field set (no pressure, no outdoor sensor, no
counters, no DHW flow), heating at 41 °C to the floor and 33 °C back on a cold November evening; 14 burner
starts and 2.0 m³ gas today; yesterday's scoreboard, what the E32 knows (88 %), a learned weather compensation
line and the rc.5 telemetry (insight, free heat, boiler response). The documents follow the firmware's own
shapes: `ha/tests_native/e32_telemetry.py` splits the status into topics (the test helper is loaded by path,
`e32_split.py`) and the boiler fields use the integration's catalog (`boiler_fields.py`). Change the house there.

## What is needed

WSL Ubuntu (or Linux) with: the HA test venv (`HA_VENV`, default `~/venvs/ha`, with `uv`), `/usr/sbin/mosquitto`,
`unshare` and `ip`, node (`NODE`, default `~/node/bin/node`) with playwright-core in `NODE_PATH` and Chromium
(`CHROME`, default Playwright's chromium-1243). The venv is never changed: `deps.py` installs what the demo
needs beyond the tests (the frontend, and the packages of the integrations Core always loads) at this Core's own
pins, without dependencies, into `~/.cache/openthermostat-ha-demo/deps-<core>` (`OPENTHERMOSTAT_DEMO_CACHE`), and
two voice packages that have no wheel for this Python get an import-only stand-in.

## What the pictures do not show

- A real E32: the fake answers what "Connect E32" and the integration read, and its telemetry is a fixed moment
  of a scenario, renewed every minute; nothing reacts to a change made in the dashboard (a saved week program
  is stored, an override is not acted on).
- No gas meter, gas price or water meter: the gas figures are the estimate from burner power (the owner has a
  meter, so his texts say so).
- The v1 session (`fw/hello`, `fw/session`) is not answered, so whatever depends on a live session is absent; the
  E32's own web pages, Bluetooth pairing, firmware updates and backups are not exercised.
- History comes from the scenario, not a recording; the graphs are plausible, not the owner's house.
- The first set-up is a new installation, not an upgrade of the owner's: first-connect notices may differ.
