# E32 screenshots

`shots.cjs` takes the pictures of the E32's own web pages (`data/html`) and of the Home Assistant week
planner card for the project page and the HACS front page. It serves the shipped files with simulated HTTP
(playwright-core routes, as the browser tests in `test/` do) from ONE fictitious demonstration house; no E32,
broker or Home Assistant instance is contacted, and the pages themselves are never changed.

The house (Thursday 5 November 2026, 18:20 in Amsterdam): the living room with floor heating, a tado-style
thermostat in Home Assistant plus a Bluetooth thermometer, heating towards 21 °C with a week program;
bathroom and bedroom (radiators) switched off; a Nefit EcomLine-type boiler on the EMS bus; rc.5 telemetry
(knowledge 78 %, a learned curve, "yesterday compared with usual", free heat); a 24-hour history. The figures
follow `tools/dev/ha-demo/scenario.py`.

```
export NODE_PATH=<dir with node_modules/playwright-core> CHROMIUM_PATH=<headless chromium> PYTHON=<python with Pillow>
node tools/dev/e32-shots/shots.cjs --suffix rc5 --version "E32 1.0.0-rc.5 (release-1.0 004dadc1)"
```

Options: `--out DIR` (default `docs/img/screenshots`), `--only name,name`, `--raw DIR` (the unquantised
captures, default the system temp directory), `--no-register` (do not touch `screenshots.json`).

It writes the six names `scripts/publish_hacs_repo.py` reads (`e32-overview`, `e32-rooms`, `e32-boiler`,
`e32-home-learned`, `e32-overview-phone-dark`, `ha-week-card`) as `<name>-<suffix>.png`, 256-colour PNGs
(Pillow, Floyd-Steinberg), and adds or replaces their entries (file, version, date, width, height, bytes,
sha256, scope) in `screenshots.json`. Re-run it after a UI change, with a new suffix for a new set. Edit the
`DEMO` data at the top of the script to change the house; if the pages ask for a file the script does not
serve, it lists it at the end (a 404 for `/config/heating/trv` or `/config/heating/comfort` is expected).
Check every picture by eye afterwards: empty panels or placeholder text mean the demo data is incomplete.

In the captures the sticky "Save" bars are put back in the flow (otherwise they float mid-picture), and
the Home picture leaves out house mode, holidays, presence and the limits to keep to learning.
