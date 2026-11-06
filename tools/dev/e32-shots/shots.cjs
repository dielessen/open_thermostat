// Screenshots of the E32's own web pages (data/html) and of the Home Assistant week planner card, from ONE
// fictitious demonstration house. Serves the shipped files with simulated HTTP (playwright-core routes), as the
// browser tests in test/ do. No device, no broker, no Home Assistant, no real installation is contacted.
// Usage: node tools/dev/e32-shots/shots.cjs --suffix rc5 [--version "E32 1.0.0-rc.5 (release-1.0 004dadc1)"]
//          [--out docs/img/screenshots] [--only e32-rooms,ha-week-card] [--raw DIR] [--no-register]
// Environment: CHROMIUM_PATH (headless Chromium), NODE_PATH (playwright-core). See README.md.
'use strict';
const {chromium} = require('playwright-core');
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib'), cp = require('node:child_process'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '../../..'), assets = path.join(root, 'data/html');
const frontend = path.join(root, 'ha/config/custom_components/open_thermostat/frontend');

const args = (() => { const a = process.argv.slice(2), o = {}; for (let i = 0; i < a.length; i++) if (a[i].startsWith('--')) { const k = a[i].slice(2); o[k] = a[i + 1] && !a[i + 1].startsWith('--') ? a[++i] : true; } return o; })();
if (!args.suffix) { console.error('usage: node shots.cjs --suffix rc5 [--version TEXT] [--out DIR] [--only a,b] [--raw DIR] [--no-register]'); process.exit(2); }
const SUFFIX = String(args.suffix), VERSION = args.version || 'E32 (unspecified)';
const OUT = path.resolve(root, args.out || 'docs/img/screenshots'), RAW = path.resolve(root, args.raw || path.join(require('node:os').tmpdir(), 'e32-shots-raw'));
const NAMES = ['e32-overview', 'e32-rooms', 'e32-boiler', 'e32-home-learned', 'e32-overview-phone-dark', 'ha-week-card'];
const only = args.only ? String(args.only).split(',') : NAMES;

// ---------------------------------------------------------------------------------------------------------------
// The demo house. Thursday 5 November 2026, 18:20 in Amsterdam (17:20 UTC): living room (floor heating, a tado-style
// thermostat in Home Assistant plus a Bluetooth thermometer) heating towards 21 °C; bathroom and bedroom (radiators)
// switched off; a Nefit EcomLine-type boiler on the EMS bus; E32 rc.5 telemetry (knowledge 78 %, a learned curve).
// The figures follow tools/dev/ha-demo/scenario.py. Fictitious; nothing here comes from a real installation.
// ---------------------------------------------------------------------------------------------------------------
const NOW = Date.parse('2026-11-05T17:20:00Z'), HOST = 'http://opth.test';
const TADO = 'climate.tado_woonkamer', BLE = 'a4c1380d5e21', OUTDOOR_C = 5.6, SLOPE = 0.85, DESIGN = 50;
const COMFORT = 2100, ECO = 1950, NIGHT = 1850;
// Monday first. Weekdays: up 06:30, eco 08:30, comfort 17:00, night 22:30; weekend: 08:00 .. 23:00.
const WEEKDAY = [[390, COMFORT], [510, ECO], [1020, COMFORT], [1350, NIGHT]], WEEKEND = [[480, COMFORT], [1380, NIGHT]];
const WEEK = [...Array(5)].map(() => WEEKDAY.map(p => [...p])).concat([WEEKEND, WEEKEND].map(d => d.map(p => [...p])));
const BATH = [...Array(7)].map(() => [[375, 2150], [465, 1700], [1170, 2050], [1290, 1700]]);
const SLEEP = [...Array(7)].map(() => [[0, 1600], [1290, 1750], [1410, 1600]]);
const copy = v => JSON.parse(JSON.stringify(v));
const levelsText = week => week.map(day => day.map(([, t]) => ({[COMFORT]: 1, [ECO]: 2, [NIGHT]: 3}[t] || 0)).join('')).join('.');

function plan() {
  const room = (id, name, state, emitter, sources, entity, schedule, levels) => ({id, name, state, inactive_until: 0, emitter, sources, setpoint_entity: entity,
    fallback_centi_c: 2000, minimum_centi_c: 500, maximum_centi_c: 2500, schedule, ...(levels ? {levels, schedule_levels: levelsText(schedule)} : {})});
  return {schema: 1, revision: 3, mode: 'active', minimum_flow_c: 28, maximum_flow_c: 50, features: ['plan.levels.v1'], rooms: [
    room('woonkamer', 'Woonkamer', 'active', 'floor', [{type: 'ha', id: TADO}, {type: 'ble', id: BLE}], TADO, WEEK, {comfort: COMFORT, eco: ECO, night: NIGHT}),
    room('badkamer', 'Badkamer', 'inactive', 'radiator', [{type: 'ha', id: 'climate.thermostaat_badkamer'}], '', BATH, null),
    room('slaapkamer', 'Slaapkamer', 'inactive', 'radiator', [{type: 'ble', id: 'a4c1380d7b90'}], '', SLEEP, null)]};
}

// The last 24 h in 5-minute steps (GET /status/history): the living room follows its program with a window open
// shortly before now; the boiler heats the floor, keeps its 25 l store warm now and then, and serves taps.
function history() {
  const n = 288, period = 300, local = i => new Date(NOW - 86400000 + i * period * 1000 + 3600000), wobble = i => Math.sin(i * 1.7) * 0.5 + Math.sin(i * 0.37) * 0.5;
  const taps = [[7, 5, 10], [7, 30, 5], [12, 40, 5], [13, 15, 5], [18, 10, 15], [19, 45, 5]], keep = [[1, 20], [3, 50], [5, 55], [10, 35], [15, 20], [17, 5]];
  const dow = d => (d.getUTCDay() + 6) % 7;
  const target = i => { const l = local(i), m = l.getUTCHours() * 60 + l.getUTCMinutes(); let t = NIGHT; for (const [at, v] of WEEK[dow(l)]) if (m >= at) t = v; if (t === NIGHT && m < WEEK[dow(l)][0][0]) t = NIGHT; return t; };
  const room = [], req = [], flow = [], ret = [], burner = [], tap = [], warm = [], tgt = [];
  let t = 20.9, heating = false;
  for (let i = 0; i < n; i++) {
    const l = local(i), m = l.getUTCHours() * 60 + l.getUTCMinutes(), tg = target(i) / 100;
    const isTap = taps.some(([h, mm, len]) => m - (h * 60 + mm) >= 0 && m - (h * 60 + mm) < len), isKeep = keep.some(([h, mm]) => m - (h * 60 + mm) >= 0 && m - (h * 60 + mm) < 5);
    const dhw = (isTap || isKeep) && i < n - 9;
    // Smart warm-up: start heating early before a comfort switch (floor: about two hours).
    const upcoming = WEEK[dow(l)].find(([at, v]) => at > m && v > tg * 100), early = upcoming && upcoming[0] - m <= 120 && t < upcoming[1] / 100 - 0.1;
    if (early || t < tg - 0.2) heating = true; else if (t > tg + 0.1) heating = false;
    const dip = i >= n - 15 && i < n - 8;
    t += ((heating && !dip ? 0.75 : -0.24) * (dhw ? 0.4 : 1)) / 12 + wobble(i) * 0.004;
    if (dip) t -= 0.03;
    room.push(Math.round(t * 10)); tgt.push(Math.round(tg * 10));
    const out = OUTDOOR_C + 2.5 * Math.sin((m / 60 - 9) / 24 * 6.283);
    const want = Math.min(60, Math.max(30, 21 + SLOPE * (21 - out))) + 3;
    if (dhw) { flow.push(Math.round((66 + wobble(i) * 3) * 10)); ret.push(Math.round((45 + wobble(i)) * 10)); burner.push(Math.round(76 + wobble(i) * 6)); req.push(null); }
    else if (heating) { flow.push(Math.round((want + wobble(i) * 0.8) * 10)); ret.push(Math.round((want - 8 + wobble(i) * 0.5) * 10)); burner.push(Math.round(32 + 2 * (8 - out) + wobble(i) * 3)); req.push(Math.round(want * 10)); }
    else { flow.push(Math.round((t + 6) * 10)); ret.push(Math.round((t + 3) * 10)); burner.push(0); req.push(null); }
    tap.push(isTap && dhw ? 100 : 0); warm.push(isKeep && dhw ? 100 : 0);
  }
  room[n - 1] = 204; tgt[n - 1] = 210; flow[n - 1] = 410; ret[n - 1] = 330; burner[n - 1] = 38; req[n - 1] = 380; tap[n - 1] = warm[n - 1] = 0;
  return {schema: 1, available: true, period_s: period, points: n, oldest_start_ago_s: 86400, uptime_s: 91000, flow, return: ret, request: req,
    thermostat_request: new Array(n).fill(null), burner_pct: burner, dhw_tap_pct: tap, dhw_reheat_pct: warm, rooms: [{id: 'woonkamer', temperature: room, target: tgt}]};
}

const OVERVIEW_ROOMS = () => [
  {id: 'woonkamer', name: 'Woonkamer', state: 'active', inactive_until: 0, fallback_centi_c: 2000, minimum_centi_c: 500, maximum_centi_c: 2500, status: 'ok',
    source: TADO, temperature: 20.4, setpoint: 21, setpoint_source: 'schedule', demand: true,
    comfort: {mode: 'program', target_c: 21, until: Math.round(Date.parse('2026-11-05T21:30:00Z') / 1000), override: 'none'}},
  ...['badkamer:Badkamer', 'slaapkamer:Slaapkamer'].map(s => ({id: s.split(':')[0], name: s.split(':')[1], state: 'inactive', inactive_until: 0, fallback_centi_c: 2000,
    minimum_centi_c: 500, maximum_centi_c: 2500, status: 'inactive', source: null, temperature: null, setpoint: null, setpoint_source: 'fallback', demand: false}))];

const INSIGHT = {knowledge: {pct: 78, missing: ['arrival:woonkamer', 'boiler_minimum', 'something_new'], more: 1},
  house: {ua_kw_per_k: 0.21, kw_per_flow_k: 0.42, slope: SLOPE, state: 'learned'},
  boiler: {held: 0, rest_s: 600, ceiling_c: null, absorbed_kw: 6.8, kw_per_k: 0.42, state: 'learned', return: true},
  insights: [{kind: 'gas_per_dd_down', pct: 8}]};

function heatingStatus() {
  const switchUtc = Math.round(Date.parse('2026-11-06T05:30:00Z') / 1000);
  return {schema: 1, revision: 3, mode: 'active',
    request: {heat: true, flow_c: 38, reason: 'heating', capped_by: null}, ha_entities: [TADO, 'climate.thermostaat_badkamer'],
    rooms: OVERVIEW_ROOMS(),
    away: {on: false, source: 'none', target_c: 15, until: null, presence: 'home', mode: 'auto', holidays: [], holiday_temperature_c: 15},
    ble_sensors: [{id: BLE, name: 'Thermometer woonkamer', profile: 'pvvx_thermometer', temperature: 20.46, humidity: 52.8, battery: 100, age_s: 21},
      {id: 'a4c1380d7b90', name: 'Thermometer slaapkamer', profile: 'pvvx_thermometer', temperature: 17.62, humidity: 58.4, battery: 83, age_s: 47}],
    burner: {starts_last_hour: 2, heating_starts_last_hour: 1, short_cycling: false, activity: 'heating'},
    ha: {input_age_s: 18, broker_connected: true},
    active: {state: 'active', awaiting_confirmation: false, command: {send: true, flow_c: 38, why: 'heating'}, last_sent: {flow_c: 38, age_s: 24}, foreign_controller: null,
      confirmation: {age_s: 900, restored: false}, warnings: [], enabled: true, confirmation_stored: true, thermostat_seen: false, taken_over_before: true, reconfirm_required: false,
      boiler_limit: {flow_c: 75, age_s: 300, reads: 12}},
    flow: {source: 'learned', rule_flow_c: 40, settings: {weather_curve: true, apply_learned: true, curve_design_flow_c: 0}, applied_flow_c: 38, cap_c: 60, ceiling_c: null,
      curve: {state: 'applied', flow_c: 38, base_c: Math.round((21 + SLOPE * (21 - OUTDOOR_C)) * 10) / 10 - 0.4, slope: SLOPE, slope_source: 'learned', design_flow_c: DESIGN, windows: 23, last: 'window_learned'},
      learned: {state: 'applied', flow_c: 38, room: 'woonkamer'},
      optimum_start: {state: 'applied', room: 'woonkamer', start_utc: switchUtc - 165 * 60}},
    learned: {schema: 1, applied: true, status: 'ready', outdoor_c: OUTDOOR_C, heating_periods: 38,
      inputs: {gas_meter: false, gas_price: false, outdoor: 'ha', boiler_kw: 22, boiler_kw_source: 'ha', gas_kwh_per_m3: 9.77, gas_kwh_per_m3_source: 'default'},
      rooms: [{id: 'woonkamer', emitter: 'floor', readiness: 'ready', readiness_timing: 'ready', segments: 41, periods: 38, loss_per_h: 0.0176, capacity_kwh_per_k: 26.4,
        advice: [{shortfall_c: 1, required_c_per_h: 0.5, flow_c: 42, warmup_h: 1.9, reason: 'learned', rule_flow_c: 40, rule_warmup_h: 2.2, rule: 'lower_too_slow'}],
        now: {shortfall_c: 0.6, required_c_per_h: 0.3, flow_c: 41, warmup_h: 1.3, reason: 'learned', rule_flow_c: 38, rule_warmup_h: 1.6, rule: 'agrees'},
        free_heat: {rate: [0.3, 0.2, 0.1, 0.5, 0.8, 0.4], n: [14, 12, 9, 16, 18, 11], applied_min: 12},
        plan: {optimum_start: {reason: 'planned', next_switch: {utc: switchUtc, target_c: 21}, predicted_start_utc: switchUtc - 165 * 60, lead_minutes: 165, flow_c: 44,
          confidence: 'learned', reachable: true, start_now: false, applies: true, estimate: false},
          night: {reason: 'estimated', recommended: 'program', recommended_night_c: 18.5, saving_m3: 0.4, saving_eur: 0.52},
          arrival: {factor: 1.05, events: 9, last_error_min: 6, last_at_utc: Math.round(NOW / 1000) - 14 * 3600}}}]},
    tuning: {state: 'applied', values: {min_on_s: 900, min_off_s: 900, heat_start_c: 0.2, heat_stop_c: 0.1, flow_per_degree_c: 6, curve_correction_pct: 96, floor_lead_min_per_c: 140,
      radiator_lead_min_per_c: 60, learned_accept_pct: 100, night_saving_min_pct: 20}, manual: [], yesterday: {starts: 21, heating_h: 7.4}, today: {starts: 14, heating_h: 5.3}, would: [], log: []},
    scoreboard: {yesterday: {day: '2026-11-04', heating_h: 7.4, heating_starts_per_h: 2.8, short_cycle_h: 0, heating_kwh: 27.4, degree_days: 14.2,
      rooms: [{id: 'woonkamer', on_time_min: 4, overshoot_c: 0.2}]}, today: {day: '2026-11-05', heating_h: 5.3, heating_starts_per_h: 2.5, short_cycle_h: 0, heating_kwh: 15.8, degree_days: 13.6}},
    boiler: copy(INSIGHT.boiler), insight: copy(INSIGHT),
    shadow: {today: {day: '2026-11-05', s: 0, tado_unknown_s: 0}}, readiness: {state: 'not_applicable', takeover_test: {state: 'passed', at: Math.round(NOW / 1000) - 86400 * 4, steps: {}, reason: null, summary: 'passed', flow_c: 45, marked: true, marked_at: null}},
    new_plan: {stored: true, mode: 'active', reason: 'no_thermostat'}};
}

function emsStatus() {
  return {controlMode: 'shadow', ems: {heatingActive: true, warmWaterActive: false, heatingEnabled: true, warmWaterEnabled: true, currentFlowTemperature: 410, currentReturnTemperature: 330,
    currentBurnerPower: 38, currentWarmWaterTemperature: 579, selectedFlowTemperature: 38, displayCode: '-H', serviceCode: 201},
    control: {fresh: false, reason: 'waiting'}, ha: {}, firmware: 'v1.0.0-e32v2-rc.5'};
}
function boilerTelemetry() {
  const s = (value, unit = 'degC', extra = {}) => ({value, unit, state: 'valid', quality: 'reported', source_type: 24, source_address: 8, age_ms: 900, ...extra});
  return {reception: {state: 'classic_reports_received'}, transport: {enabled: true, frames: 482113}, fields: {
    measured_flow_temperature: s(41.0), measured_return_temperature: s(33.0), measured_dhw_temperature: s(57.9), reported_burner_modulation: s(38, 'percent'),
    heating_active: s(1, 'bool'), dhw_active: s(0, 'bool'), display_code: s('-H', 'text'), service_number: s(201, 'number'),
    configured_heating_temperature: s(75, 'degC', {source_type: 22, request_only: true, age_ms: 1200000, observed_at_ms: 840000}),
    reported_burner_runtime: s(31260, 'min')},
    burner_cycles: {known: true, starts_last_hour: 2, median_heating_run_s: 1260, short_cycling: false},
    dhw_episodes: {today: {tapping: {count: 6, s: 2340}, keep_warm: {count: 4, s: 960}, burner_s: 3300, peak_flow_l_min: null},
      last_7_days: {tapping: {count: 41, s: 15100}, keep_warm: {count: 33, s: 7100}}, method: 'dhw_temperature_fall'}};
}
function boilerProfile() {
  return {schema: 1, boiler: {address: 8, family: 'classic', product_id: null, version: null}, supported: [0, 1, 2, 4, 10, 11, 12, 13, 14, 24, 25, 28, 29, 32, 40, 41],
    not_fitted: [3, 6, 15], not_reported: [], settled: true, display_model: 'nefit-ecomline-classic-hrc-22h'};
}

// ---------------------------------------------------------------------------------------------------------------
async function serve(context, missing) {
  const json = (r, body, code = 200) => r.fulfill({status: code, contentType: 'application/json', body: JSON.stringify(body)});
  await context.route(HOST + '/**', async r => {
    const req = r.request(), p = decodeURIComponent(new URL(req.url()).pathname), post = req.method() !== 'GET';
    if (p === '/auth/session') return json(r, {authenticated: true, csrf: 'c'.repeat(64), default_password: false});
    if (p === '/status') return json(r, emsStatus());
    if (p === '/status/heating') return json(r, heatingStatus());
    if (p === '/status/history') return json(r, history());
    if (p === '/status/ems/telemetry') return json(r, boilerTelemetry());
    if (p === '/status/boiler/profile') return json(r, boilerProfile());
    if (p === '/config/heating' && !post) return json(r, plan());
    if (p === '/config/heating/flow') return json(r, {weather_curve: true, apply_learned: true, curve_design_flow_c: 0, tuning: heatingStatus().tuning.values, tuning_manual: []});
    if (p === '/config/boiler-display') return json(r, {model: 'nefit-ecomline-classic-hrc-22h'});
    if (p === '/updates/status') return json(r, {installed: 'v1.0.0-e32v2-rc.5', phase: 'idle', error: '', busy: false, can_check: true, releases: []});
    if (p === '/week-editor.js' || p === '/deps/chart.umd.js.gz' && false) { /* served from data/html below */ }
    const file = path.join(assets, p === '/' ? 'index.html' : p);
    if (!file.startsWith(assets + path.sep) || !fs.existsSync(file)) { missing.add(req.method() + ' ' + p); return r.fulfill({status: 404, body: ''}); }
    let body = fs.readFileSync(file); if (p.endsWith('.gz')) body = zlib.gunzipSync(body);
    const type = p.endsWith('.css.gz') ? 'text/css' : p.endsWith('.js') || p.endsWith('.js.gz') ? 'application/javascript' : p.endsWith('.svg') ? 'image/svg+xml' : 'text/html';
    return r.fulfill({contentType: type, body});
  });
}
async function open(browser, {width, height = 1000, scheme = 'light', scale = 1, lang = 'en', edit = false}, missing, errors) {
  const context = await browser.newContext({viewport: {width, height}, deviceScaleFactor: scale, colorScheme: scheme, locale: lang === 'nl' ? 'nl-NL' : 'en-GB', timezoneId: 'Europe/Amsterdam'});
  await context.addCookies([{name: 'ot_ui_lang', value: lang, url: HOST}]);
  await context.addInitScript(([edit]) => { try { if (edit) sessionStorage.setItem('ot-rooms-edit', '1'); else sessionStorage.removeItem('ot-rooms-edit'); } catch (_) {} }, [edit]);
  await serve(context, missing);
  const page = await context.newPage(); await page.clock.setFixedTime(new Date(NOW));
  page.on('pageerror', e => errors.push(e.message));
  return page;
}
const settle = page => page.waitForTimeout(1500);
async function goto(page, name) {
  await page.goto(HOST + '/'); await page.waitForFunction(() => typeof loadNativePage === 'function');
  if (name) await page.evaluate(n => loadNativePage(n), name);
}
// Crop from the top of the page to just above an element (its top edge minus a gap), or to a fixed height.
async function clipAbove(page, selector, gap = 12) {
  return page.evaluate(([sel, gap]) => { const e = document.querySelector(sel); return e ? Math.floor(e.getBoundingClientRect().top + scrollY - gap) : null; }, [selector, gap]);
}

const SHOTS = {
  async 'e32-overview'(browser, ctx) {
    const page = await open(browser, {width: 1280}, ctx.missing, ctx.errors); await goto(page);
    await page.locator('.pd-room').first().waitFor(); await page.locator('.pd-history .oth-chart').first().waitFor(); await settle(page);
    const stop = await clipAbove(page, '[data-dashboard-key="shadow-mode-help"]', 0);
    const top = await page.evaluate(() => { const h = [...document.querySelectorAll('.pd-panel h2')].find(e => /How this works|Hoe dit werkt/.test(e.textContent)); return h ? Math.floor(h.closest('.pd-panel').getBoundingClientRect().top + scrollY - 12) : null; });
    return {page, height: top || stop};
  },
  async 'e32-rooms'(browser, ctx) {
    const page = await open(browser, {width: 1280}, ctx.missing, ctx.errors); await goto(page, 'heating');
    // Editing unlocked as the owner does it: "Edit here anyway", then the living room's card with its week program.
    page.on('dialog', d => d.accept());
    await page.locator('[data-heating-unlock]').click();
    const card = page.locator('[data-heating-rooms] details').first();
    await card.evaluate(e => { e.open = true; for (const d of e.querySelectorAll('[data-heating-section]')) d.open = true; });
    await page.locator('[data-heating-planner] .wpe-seg').first().waitFor({timeout: 15000}); await settle(page);
    // The save bar sticks to the viewport; in a long capture it would float mid-page, so let it sit in the flow.
    await page.addStyleTag({content: '.ot-sticky{position:static!important}'});
    // Cropped after the planner and the week preview (before "Advanced: edit as text").
    return {page, height: await page.evaluate(() => { const s = [...document.querySelectorAll('summary')].find(e => /Advanced: edit as text/.test(e.textContent)); return s ? Math.floor(s.closest('details').getBoundingClientRect().top + scrollY - 8) : null; })};
  },
  async 'e32-boiler'(browser, ctx) {
    const page = await open(browser, {width: 1280}, ctx.missing, ctx.errors); await goto(page, 'boiler_test');
    await page.locator('[data-essentials] dt').first().waitFor(); await page.locator('[data-dhw-list] dt').first().waitFor(); await settle(page);
    return {page, height: await page.evaluate(() => { const e = document.querySelector('#bt-now').closest('section'); return Math.ceil(e.getBoundingClientRect().bottom + scrollY + 16); })};
  },
  async 'e32-home-learned'(browser, ctx) {
    const page = await open(browser, {width: 1280}, ctx.missing, ctx.errors); await goto(page, 'house');
    await page.locator('[data-learned-knows] [data-knowledge-ring]').waitFor(); await page.locator('[data-curve-chart] svg').first().waitFor(); await settle(page);
    // The picture is about learning: leave out house mode, holidays, presence and the limits (page content is untouched, only hidden in this capture),
    // keep the water temperature chart and the learned panel, with each room's and the house's "More" opened.
    await page.addStyleTag({content: '#house-settings>.pd-panel:not([data-house-heating]):not([data-house-learned]),[data-boiler-limits],[data-house-heating]>.pd-help,[data-house-lock]{display:none!important}'});
    await page.evaluate(() => { for (const d of document.querySelectorAll('[data-house-learned] details')) d.open = true; });
    await page.waitForTimeout(300);
    return {page, height: await page.evaluate(() => Math.ceil(document.querySelector('[data-house-learned]').getBoundingClientRect().bottom + scrollY + 8))};
  },
  async 'e32-overview-phone-dark'(browser, ctx) {
    const page = await open(browser, {width: 390, height: 844, scheme: 'dark', scale: 2, lang: 'en'}, ctx.missing, ctx.errors); await goto(page);
    await page.locator('.pd-room').first().waitFor(); await settle(page);
    return {page, height: await page.evaluate(() => { const r = document.querySelectorAll('.pd-room'); return Math.ceil(r[0].getBoundingClientRect().bottom + scrollY + 16); })};
  },
  async 'ha-week-card'(browser, ctx) {
    const context = await browser.newContext({viewport: {width: 1000, height: 1000}, deviceScaleFactor: 1, colorScheme: 'light', locale: 'en-GB', timezoneId: 'Europe/Amsterdam'});
    const page = await context.newPage(); page.on('pageerror', e => ctx.errors.push(e.message));
    await page.route('http://ha.test/**', r => {
      const p = new URL(r.request().url()).pathname;
      if (p === '/') return r.fulfill({contentType: 'text/html', body: '<meta name="viewport" content="width=device-width, initial-scale=1"><body style="margin:0;padding:16px;background:#fafafa;font:14px Roboto,system-ui,sans-serif;color:#212121"><main style="max-width:968px"></main></body>'});
      if (p === '/open_thermostat/week-editor-1.0.0.js') return r.fulfill({contentType: 'application/javascript', body: fs.readFileSync(path.join(frontend, 'week-editor.js'))});
      if (p === '/card.js') return r.fulfill({contentType: 'application/javascript', body: fs.readFileSync(path.join(frontend, 'e32-week-card.js'))});
      return r.fulfill({status: 404, body: ''});
    });
    await page.goto('http://ha.test/'); await page.addScriptTag({url: '/card.js', type: 'module'});
    await page.evaluate(({rooms}) => {
      // Only Home Assistant's default light card style stands in for ha-card.
      const style = document.createElement('style'); style.textContent = 'openthermostat-e32-week{display:block;background:#fff;border-radius:12px;box-shadow:0 2px 2px rgba(0,0,0,.14),0 3px 1px -2px rgba(0,0,0,.12),0 1px 5px rgba(0,0,0,.2);padding:16px;--primary-text-color:#212121;--secondary-text-color:#727272;--primary-color:#03a9f4;--divider-color:#e0e0e0;--card-background-color:#fff}';
      document.head.append(style);
      const card = document.createElement('openthermostat-e32-week'); card.setConfig({entry_id: 'entry'}); document.querySelector('main').append(card);
      card.hass = {language: 'en', config: {unit_system: {temperature: '°C'}}, locale: {language: 'en'}, themes: {darkMode: false},
        states: {'climate.tado_woonkamer': {attributes: {friendly_name: 'tado Woonkamer'}}},
        callWS: async r => { if (r.type === 'open_thermostat/e32_week/get') return {revision: 3, levels_supported: true, rooms}; throw {code: 'unexpected'}; }};
    }, {rooms: plan().rooms});
    await page.locator('openthermostat-e32-week .wpe-seg').first().waitFor({timeout: 15000}); await page.waitForTimeout(800);
    // The save bar sticks to the card's bottom edge; in a long capture it would float mid-card, so let it sit in the flow.
    await page.evaluate(() => { const c = document.querySelector('openthermostat-e32-week'), st = document.createElement('style'); st.textContent = '.actions{position:static!important}'; (c.shadowRoot || c).append(st); });
    return {page, height: null, element: 'openthermostat-e32-week', pad: 16};
  },
};

function quantize(src, dest) {
  const py = process.env.PYTHON || 'python3';
  const code = 'import sys\nfrom PIL import Image\nim=Image.open(sys.argv[1]).convert("RGB")\nim.quantize(256,dither=Image.FLOYDSTEINBERG).save(sys.argv[2],optimize=True)\n';
  cp.execFileSync(py, ['-c', code, src, dest], {stdio: 'inherit'});
}
function pngSize(file) { const b = fs.readFileSync(file); return {width: b.readUInt32BE(16), height: b.readUInt32BE(20), bytes: b.length, sha256: crypto.createHash('sha256').update(b).digest('hex')}; }

(async () => {
  fs.mkdirSync(RAW, {recursive: true}); fs.mkdirSync(OUT, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH || undefined});
  const ctx = {missing: new Set(), errors: []}, made = [];
  try {
    for (const name of NAMES) {
      if (!only.includes(name)) continue;
      const shot = await SHOTS[name](browser, ctx), raw = path.join(RAW, `${name}-${SUFFIX}.png`), file = path.join(OUT, `${name}-${SUFFIX}.png`);
      if (shot.element) {
        const box = await shot.page.locator(shot.element).first().boundingBox(), pad = shot.pad || 0, vp = shot.page.viewportSize();
        await shot.page.screenshot({path: raw, fullPage: true, clip: {x: Math.max(0, box.x - pad), y: box.y - pad, width: Math.min(vp.width, box.width + 2 * pad), height: box.height + 2 * pad}});
      } else {
        const full = await shot.page.evaluate(() => document.documentElement.scrollHeight), vp = shot.page.viewportSize();
        await shot.page.screenshot({path: raw, fullPage: true, clip: {x: 0, y: 0, width: vp.width, height: Math.min(full, shot.height || full)}});
      }
      quantize(raw, file); made.push({name, file, ...pngSize(file)}); await shot.page.context().close();
      console.log(`${name}-${SUFFIX}.png ${made.at(-1).width}x${made.at(-1).height} ${made.at(-1).bytes} B`);
    }
  } finally { await browser.close(); }
  if (ctx.missing.size) console.warn('files requested but not served (404):\n  ' + [...ctx.missing].join('\n  '));
  if (ctx.errors.length) { console.error('page errors:\n  ' + ctx.errors.join('\n  ')); process.exitCode = 1; }
  if (args['no-register']) return;
  const jsonFile = path.join(OUT, 'screenshots.json'), doc = JSON.parse(fs.readFileSync(jsonFile, 'utf8')), date = '2026-11-05';
  for (const m of made) {
    const file = path.basename(m.file), what = {
      'e32-overview': 'cropped above How this works', 'e32-rooms': 'editing unlocked, whole page', 'e32-boiler': 'cropped to the Now panel',
      'e32-home-learned': 'cropped to the What the E32 knows and learned panel', 'e32-overview-phone-dark': '390 px phone width at 2x, dark theme, cropped after the first room',
      'ha-week-card': 'Home Assistant week planner card (e32-week-card.js and week-editor.js) with a synthetic hass object; ha-card stand-in with the default light card style; no Home Assistant instance'}[m.name];
    const scope = m.name === 'ha-week-card' ? `${what}; rendered in headless Chromium with fictitious demonstration data; not a live capture`
      : `E32 web interface (data/html) rendered locally in headless Chromium by tools/dev/e32-shots with fictitious demonstration data (mocked HTTP responses); not a live device; ${what}`;
    const entry = {file, version: VERSION, date, width: m.width, height: m.height, bytes: m.bytes, sha256: m.sha256, scope};
    const at = doc.images.findIndex(i => i.file === file); if (at >= 0) doc.images[at] = entry; else doc.images.push(entry);
  }
  fs.writeFileSync(jsonFile, JSON.stringify(doc, null, 2) + '\n');
})().catch(e => { console.error(e); process.exit(1); });
