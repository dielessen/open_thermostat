/* The Overview's house card (OpenThermostat, E32 rc.5): the house at a glance, from Home Assistant alone.

   One wide card on top of the Overview (dashboard.py, room_overview.HOUSE_CARD_TYPE). A strip in the colour of
   what the boiler does now ("Heating · water 41 °C", hot water, "Boiler resting"; "Attention: …" while there is a
   problem, a tap leads to Repairs and "All reasons" lists them) with the house mode as a chip; the figures of
   today: the one room that is switched on (when the house has exactly one), heating, hot water, gas today with
   its last 7 days and burner starts today; then the day so far, a strip from midnight to now (heating, hot
   water, keeping warm).

   Only Home Assistant is read: the states of the entities in the card's config, the boiler activity since
   midnight (history/history_during_period: again when the activity changes, at most every 5 minutes; the
   changes in between come from the state itself) and the statistics of gas and burner starts (the last 7 days
   by recorder/statistics_during_period, today by recorder/statistic_during_period as Home Assistant's own
   statistic card asks it; at most every 10 minutes and when the day changes). Nothing talks to the E32. "Today"
   is the house's day (Home Assistant's time zone), the day of the E32's own counters and of the statistics.

   The words are the integration's translations (strings.json entity.sensor.heat_request.state_attributes.card,
   and the room's sentence entity.sensor.room_reason as on the room status card), so every viewer reads them in
   their own Home Assistant language; English is only the last resort. Status colours are Home Assistant's state
   colours (as room-status-card.js); the sparkline wears the E32 chart colour (heating-curve-card.js), per mode. */
const PREFIX = 'component.open_thermostat.entity.sensor.';
const CARD = 'heat_request.state_attributes.card.state.';
const TEXT = {title: 'Your house', heating: 'Heating', status_heating: 'Heating · water {flow} °C', status_heating_plain: 'Heating',
 heating_on: 'on · water {flow} °C', heating_on_plain: 'on', heating_off: 'off', request: 'Boiler request {flow} °C',
 no_request: 'No boiler request', wants: '{n} rooms want heat', wants_one: '1 room wants heat', hot_water: 'Hot water',
 taps: '{n} taps today', taps_one: '1 tap today', taps_none: 'no taps yet today', running: 'running now', gas_today: 'Gas today',
 week: 'Last 7 days: {values}', starts_today: 'Burner starts today', idle: 'Boiler resting', attention: 'Attention: {reason}',
 all_reasons: 'All reasons', mode: 'House mode: {mode}', today: 'Today', legend_heating: 'Heating', legend_hot_water: 'Hot water',
 legend_keep_warm: 'Keeping warm', waiting: 'The E32 has not reported yet.'};
const DASH = '—';  // a figure not known yet: the same in every language
const NBSP = '\u00a0';
// What the boiler does (boiler_activity, heating_link.BOILER_ACTIVITIES): the kind in the strip and the status tone.
const KIND = {heating: 'heat', tapping: 'water', hot_water: 'water', keep_warm: 'keep', charging: 'keep', idle: 'rest'};
const RUNNING = new Set(['tapping', 'charging', 'hot_water']);
const ICON = {heat: 'mdi:fire', water: 'mdi:faucet', keep: 'mdi:water-thermometer', rest: 'mdi:water-boiler',
 error: 'mdi:alert-circle-outline', wait: 'mdi:timer-sand'};
const LEGEND = [['heat', 'legend_heating'], ['water', 'legend_hot_water'], ['keep', 'legend_keep_warm']];
const ACTIVITY_EN = {idle: 'Idle', heating: 'Heating', tapping: 'Tapping', keep_warm: 'Keeping warm', charging: 'Heating the hot water tank',
 hot_water: 'Hot water'};
// The room, as the room status card shows it (room-status-card.js): the tone and icon of each reason.
const ROOM_TONE = {warm_up: 'heat', heating: 'heat', wants_heat: 'heat', boost: 'heat', away_return: 'heat', window_open: 'warn',
 window_pending: 'warn', no_measurement: 'error', hot_water: 'info', boiler_pause: 'info', temporary: 'info', holiday: 'away', away: 'away',
 room_away: 'away', house_away: 'away', warm_enough: 'ok', off: 'off'};
const ROOM_ICON = {warm_up: 'mdi:clock-fast', heating: 'mdi:fire', wants_heat: 'mdi:fire', boost: 'mdi:rocket-launch-outline',
 away_return: 'mdi:home-import-outline', window_open: 'mdi:window-open-variant', window_pending: 'mdi:window-open-variant',
 no_measurement: 'mdi:thermometer-off', hot_water: 'mdi:water-boiler', boiler_pause: 'mdi:timer-sand', temporary: 'mdi:clock-outline',
 holiday: 'mdi:palm-tree', away: 'mdi:home-export-outline', room_away: 'mdi:account-off-outline', house_away: 'mdi:home-export-outline',
 warm_enough: 'mdi:check-circle-outline', off: 'mdi:snowflake'};
// Sentences that only repeat the figure above them ("Heating: 20.4 → 21 °C"): the reason's short word instead.
const RESTATED = new Set(['heating', 'wants_heat', 'warm_enough']);
const PRESENCE = {room_home: 'mdi:account-check', room_away: 'mdi:account-off-outline', house_home: 'mdi:home-account',
 house_away: 'mdi:home-export-outline'};
const HISTORY_MS = 5 * 60000, STATS_MS = 10 * 60000, TICK_MS = 60000, DAY_MS = 86400000, PENDING_MS = 2 * 60000;

const STYLE = `:host{display:block}
ha-card{display:block;padding:16px;color:var(--primary-text-color);
--heat:var(--state-climate-heat-color,#ff8100);--info:var(--info-color,#039be5);--error:var(--error-color,#db4437);
--warn:var(--warning-color,#ffa600);--ok:var(--success-color,#43a047);--away:var(--state-climate-cool-color,#2b9af9);
--off:var(--disabled-text-color,#9e9e9e);--oth-1:#00876f;
--oth-surface:var(--ha-card-background,var(--card-background-color,#fff));--oth-muted:var(--secondary-text-color,#6b6b6b);
--oth-line:var(--divider-color,rgba(127,127,127,.22));--oth-rest:color-mix(in srgb,var(--primary-text-color,#212121) 11%,var(--oth-surface));
--keep:color-mix(in srgb,var(--info) 55%,var(--oth-surface))}
ha-card.dark{--oth-1:#239c8a}
.wrap{container:house/inline-size}
p{margin:0}
.tone-heat{--tone:var(--heat)}.tone-water,.tone-keep,.tone-info{--tone:var(--info)}.tone-rest,.tone-off,.tone-wait{--tone:var(--off)}
.tone-error{--tone:var(--error)}.tone-warn{--tone:var(--warn)}.tone-ok{--tone:var(--ok)}.tone-away{--tone:var(--away)}
.status{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:10px 12px;border-radius:12px;
border-left:6px solid var(--tone);background:var(--secondary-background-color);background:color-mix(in srgb,var(--tone) 10%,var(--oth-surface))}
.main{display:flex;align-items:center;gap:12px;flex:1 1 0;min-width:min(100%,220px);border-radius:8px}
.main>ha-icon{color:var(--tone);--mdc-icon-size:24px;display:flex;flex:none}.words{min-width:0}
.line{font-size:1rem;font-weight:600;line-height:1.35;overflow-wrap:anywhere}
.sub{margin-top:2px;font-size:.875rem;line-height:1.35;color:var(--oth-muted);overflow-wrap:anywhere}
.main[role=link]{cursor:pointer}
.chip{display:inline-flex;align-items:center;gap:6px;min-height:32px;padding:0 12px;border-radius:16px;border:1px solid var(--oth-line);
background:var(--oth-surface);color:var(--primary-text-color);font:inherit;font-size:.875rem;font-weight:500;cursor:pointer;white-space:nowrap;
--mdc-icon-size:18px}
.chip ha-icon{color:var(--oth-muted);display:flex}
[data-focus]:focus{outline:none}[data-focus]:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}
.reasons{margin:8px 0 0}.reasons summary{cursor:pointer;color:var(--primary-color,#03a9f4);font-size:.875rem;padding:4px 0;min-height:24px}
.reasons ul{margin:4px 0 0;padding-left:20px}.reasons li{margin:0 0 4px;line-height:1.45;overflow-wrap:anywhere}
.figures{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:16px}
.figure{display:flex;flex-direction:column;gap:2px;min-width:0}
.label{display:flex;align-items:center;gap:6px;font-size:.8125rem;font-weight:500;line-height:1.3;color:var(--oth-muted);overflow-wrap:anywhere}
.value{font-size:1.25rem;font-weight:600;line-height:1.25;overflow-wrap:anywhere;text-wrap:balance}
.value small{font-size:.62em;font-weight:500;color:var(--oth-muted)}
.value.unknown{color:var(--oth-muted);font-weight:500}
.room{cursor:pointer;border-radius:8px}.room .value{font-size:2.25rem;line-height:1.1}
.room .arrow{font-size:.55em;font-weight:500;color:var(--oth-muted);margin:0 .2em}.room .target{font-size:.6em;font-weight:600;color:var(--oth-muted)}
.room .label ha-icon{--mdc-icon-size:16px;display:flex}.room .label .on{color:var(--ok)}.room .label .warn{color:var(--warn)}
.why{display:flex;align-items:flex-start;gap:6px;margin-top:6px;font-size:.9rem;line-height:1.4;overflow-wrap:anywhere;text-wrap:pretty}
.why ha-icon{color:var(--tone);--mdc-icon-size:18px;flex:none;display:flex;margin-top:1px}
.running{display:inline-flex;align-items:center;gap:6px;font-size:.875rem;color:var(--oth-muted)}
.running::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--info)}
.trend{display:flex;flex-wrap:wrap;align-items:flex-end;gap:4px 12px}
.spark{display:block;flex:none;overflow:visible}.spark path{fill:none;stroke:var(--oth-1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.spark path.partial{stroke-opacity:.45}
.spark circle{fill:var(--oth-1);stroke:var(--oth-surface);stroke-width:2}
.p2{grid-column:span 2}
.today{margin-top:20px}
.today-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 16px;margin-bottom:8px}
.today-title{font-size:.8125rem;font-weight:500;color:var(--oth-muted)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;margin:0;padding:0;list-style:none;font-size:.8125rem;color:var(--oth-muted)}
.legend li{display:inline-flex;align-items:center;gap:6px;white-space:nowrap}.legend i{width:10px;height:10px;border-radius:3px;flex:none}
.strip{position:relative;height:14px}
.strip::before{content:"";position:absolute;left:0;right:0;top:6px;height:2px;border-radius:1px;background:var(--oth-line)}
.seg{position:absolute;top:0;bottom:0;min-width:2px}.seg.first{border-radius:4px 0 0 4px}.seg.last{border-radius:0 4px 4px 0}
.seg.first.last{border-radius:4px}.seg.gap{box-shadow:-2px 0 0 var(--oth-surface)}
.rest{background:var(--oth-rest)}.heat{background:var(--heat)}.water{background:var(--info)}.keep{background:var(--keep)}
.ticks{position:relative;height:16px;margin-top:6px;font-size:12px;line-height:16px;color:var(--oth-muted);font-variant-numeric:tabular-nums}
.ticks span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}.ticks span:first-child{transform:none}
@media(max-width:480px){ha-card{padding:12px}}
@container house (max-width:400px){.main{flex-basis:100%}.chip{margin-left:36px}
.value{font-size:1.125rem}.room .value{font-size:2.25rem}}
@container house (min-width:720px){.figures{grid-template-columns:repeat(var(--wc,4),minmax(0,1fr));gap:16px 24px}
.p2{grid-column:auto}.w2{grid-column:span 2}.room{grid-row:span var(--rr,1)}}`;

const locale = hass => hass?.locale?.language || hass?.language || 'en';
// The viewer's 12/24-hour choice in Home Assistant (profile → time format); else the language's.
const hour12 = hass => {
 const chosen = ({'12': true, '24': false})[hass?.locale?.time_format];
 if (chosen !== undefined) return chosen;
 try { return /h1[12]/.test(new Intl.DateTimeFormat(locale(hass), {hour: 'numeric'}).resolvedOptions().hourCycle); } catch (e) { return false; }
};
const finite = value => typeof value === 'number' && Number.isFinite(value);
const numeric = value => { const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value; return finite(n) ? n : null; };
// A figure and its unit stay on one line ("41 °C" is never cut into "41" and "°C" on a phone).
const together = text => typeof text === 'string' ? text.replace(/ (°C|m³|kWh)/g, NBSP + '$1') : text;
const known = st => !!st && typeof st.state === 'string' && !['unknown', 'unavailable', ''].includes(st.state);
const SVG = 'http://www.w3.org/2000/svg';
const make = (tag, attrs = {}, text) => {
 const e = tag.startsWith('svg:') ? document.createElementNS(SVG, tag.slice(4)) : document.createElement(tag);
 for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v);
 if (text !== undefined) e.textContent = text;
 return e;
};
const icon = (name, attrs = {}) => make('ha-icon', {icon: name, ...attrs});

/* The house's day in its own time zone (Intl only; no library). zone: an IANA name, or undefined for the browser's. */
const formats = new Map();
const parts = (ms, timeZone) => {
 const key = timeZone || '';
 if (!formats.has(key)) formats.set(key, new Intl.DateTimeFormat('en-US', {timeZone, hourCycle: 'h23', year: 'numeric', month: 'numeric',
  day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric'}));
 const out = {};
 for (const {type, value} of formats.get(key).formatToParts(new Date(ms))) out[type] = Number(value);
 return out;
};
// Minutes the zone is ahead of UTC at instant ms.
const offset = (ms, timeZone) => {
 const p = parts(ms, timeZone);
 return (Date.UTC(p.year, p.month - 1, p.day, p.hour % 24, p.minute, p.second) - Math.floor(ms / 1000) * 1000) / 60000;
};
// The instant of the wall-clock time y-m-d h:00 in the zone (again with the offset found: a clock change between).
const wallTime = (y, m, d, h, timeZone) => {
 const guess = Date.UTC(y, m, d, h);
 return guess - offset(guess - offset(guess, timeZone) * 60000, timeZone) * 60000;
};
// The local midnight of the day of instant ms, `days` later (−6: six days before, 1: the next midnight).
const midnight = (ms, timeZone, days = 0) => {
 const p = parts(ms, timeZone);
 return wallTime(p.year, p.month - 1, p.day + days, 0, timeZone);
};
const houseZone = hass => {
 const zone = hass?.config?.time_zone;
 if (typeof zone !== 'string' || !zone) return undefined;
 try { parts(0, zone); return zone; } catch (e) { return undefined; }
};

// Home Assistant's history of one entity, as [{s: state, t: ms}] by time ("lc"/"lu" in seconds, or ISO texts).
const changes = rows => (Array.isArray(rows) ? rows : []).map(row => {
 const seconds = numeric(row?.lc) ?? numeric(row?.lu);
 const t = seconds !== null ? seconds * 1000 : Date.parse(row?.last_changed ?? row?.last_updated);
 return {s: row?.s ?? row?.state, t};
}).filter(c => typeof c.s === 'string' && Number.isFinite(c.t)).sort((a, b) => a.t - b.t);

// The day so far as runs of one kind: [{kind, start, end}], same kinds merged; '' for a time without a known state.
function runs(list, start, now) {
 const out = [];
 list.forEach((c, i) => {
  const from = Math.max(start, c.t), to = Math.min(now, i + 1 < list.length ? list[i + 1].t : now);
  if (to <= from) return;
  const kind = KIND[c.s] || '', last = out[out.length - 1];
  if (last && last.kind === kind && last.end >= from) last.end = to;
  else out.push({kind, start: from, end: to});
 });
 return out;
}

// The last 7 days as a line: points [{i: 0..6, v}] (6: today), scaled to their own range (the shape is the point).
// Today is a day still running: the step to it is drawn lighter, its dot solid. Marks 2 px, the dot ringed in the card colour.
function sparkline(points, label) {
 const W = 84, H = 30, P = 5, values = points.map(p => p.v), low = Math.min(...values), high = Math.max(...values);
 const x = i => P + i * (W - 2 * P) / 6, y = v => high > low ? H - P - (v - low) / (high - low) * (H - 2 * P) : H / 2;
 const svg = make('svg:svg', {class: 'spark', width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': label});
 svg.append(make('svg:title', {}, label));
 const at = p => x(p.i).toFixed(1) + ',' + y(p.v).toFixed(1), last = points[points.length - 1];
 const done = points.filter(p => p.i < 6);
 let d = '';
 done.forEach((p, k) => { d += (k && p.i === done[k - 1].i + 1 ? 'L' : 'M') + at(p); });
 if (d) svg.append(make('svg:path', {d, 'data-days': done.length}));
 const before = done[done.length - 1];
 if (last.i === 6 && before?.i === 5) svg.append(make('svg:path', {class: 'partial', d: 'M' + at(before) + 'L' + at(last)}));
 svg.append(make('svg:circle', {cx: x(last.i).toFixed(1), cy: y(last.v).toFixed(1), r: 4}));
 return svg;
}

class OpenThermostatHouse extends HTMLElement {
 constructor() {
  super(); this.attachShadow({mode: 'open'});
  this._key = null; this._gen = 0; this._timer = null; this._open = false;
  this.reset();
 }
 reset() {
  this._history = null; this._live = []; this._stats = null; this._changed = false; this._seen = undefined; this._seenAt = undefined;
  this._fetched = {history: 0, day: null, stats: 0, statsDay: null}; this._pending = {history: 0, stats: 0};
 }
 setConfig(config) {
  const id = value => typeof value === 'string' && value.includes('.') ? value : undefined;
  if (!config || !(id(config.request) || id(config.activity)))
   throw new Error('This card needs the "Boiler request (E32)" or "Boiler activity" sensor of OpenThermostat (request: sensor.…, activity: sensor.…); the OpenThermostat dashboard adds it for you.');
  const gas = (Array.isArray(config.gas) ? config.gas : [config.gas]).filter(id);
  const rooms = (Array.isArray(config.rooms) ? config.rooms : []).filter(room => room && id(room.entity)).slice(0, 1);
  this._config = {request: id(config.request), activity: id(config.activity), heating: id(config.heating), flow: id(config.flow),
   hot_water: id(config.hot_water), taps: id(config.taps), gas, starts: id(config.starts), mode: id(config.mode),
   problem: id(config.problem), rooms};
  this._key = null; this.reset();
  if (this._hass) { this.track(); this.refresh(); this.render(); }
 }
 set hass(hass) {
  this._hass = hass;
  if (!this._config) return;
  this.track(); this.refresh();
  // Only a new state of its own entities, language, theme or clock choice redraws; Home Assistant sets hass on every change.
  const key = [...this.entities().map(id => hass?.states?.[id]), locale(hass), hass?.themes?.darkMode, hass?.locale?.time_format,
   hass?.config?.time_zone];
  if (this._key && key.length === this._key.length && key.every((v, i) => v === this._key[i])) return;
  this._key = key; this.render();
 }
 connectedCallback() {
  // Once a minute: the day strip reaches now, and data that is due is asked again (Home Assistant only).
  if (!this._timer) this._timer = setInterval(() => { if (this._hass && this._config) { this.refresh(); this.render(); } }, TICK_MS);
  this._changed = true;  // back on the page: what happened meanwhile is read again (at most every 5 minutes)
  if (this._hass && this._config) this.refresh();
 }
 disconnectedCallback() {
  clearInterval(this._timer); this._timer = null;
  this._gen++;  // what is still on its way is dropped when it comes
  this._pending = {history: 0, stats: 0};
 }
 getCardSize() { return 5; }
 getGridOptions() { return {columns: 12, min_columns: 12}; }
 entities() {
  const c = this._config;
  return [c.request, c.activity, c.heating, c.flow, c.hot_water, c.taps, ...c.gas, c.starts, c.mode, c.problem, c.rooms[0]?.entity].filter(Boolean);
 }
 st(id) { return id ? this._hass?.states?.[id] || null : null; }
 // A text of the card (strings.json …heat_request.state_attributes.card), its {placeholders} filled; English as the last resort.
 t(key, values = {}) {
  let text = '';
  try { text = this._hass?.localize?.(PREFIX + CARD + key, values) || ''; } catch (e) { text = ''; }
  return together(typeof text === 'string' && text ? text : TEXT[key].replace(/\{(\w+)\}/g, (all, k) => k in values ? values[k] : all));
 }
 word(key, values) {
  try { const text = this._hass?.localize?.(PREFIX + key, values); return typeof text === 'string' ? text : ''; } catch (e) { return ''; }
 }
 // A state in Home Assistant's own words (a select's option, the boiler activity, a reason).
 stateText(st, state = st?.state) {
  try { const text = this._hass?.formatEntityState?.(st, state); if (typeof text === 'string' && text) return text; } catch (e) { /* older frontend */ }
  return state;
 }
 number(value, digits = 0) {
  return value.toLocaleString(locale(this._hass), {minimumFractionDigits: digits, maximumFractionDigits: digits}).replace('-', '−');
 }
 degrees(value) { return this.number(Math.round(value)); }
 time(ms) {
  try {
   return new Date(ms).toLocaleTimeString(locale(this._hass), {hour: '2-digit', minute: '2-digit', hour12: hour12(this._hass),
    timeZone: houseZone(this._hass)});
  } catch (e) { return new Date(ms).toISOString().slice(11, 16); }
 }

 // -- data: Home Assistant's history and statistics, throttled; never the E32 --------------------------------------
 // The boiler activity as it changes, kept between two history reads (and before the first).
 track() {
  const st = this.st(this._config.activity);
  if (!st) return;
  const t = Date.parse(st.last_changed), last = this._live[this._live.length - 1];
  if (Number.isFinite(t) && (!last || t > last.t || (t === last.t && st.state !== last.s))) this._live.push({s: st.state, t});
  if (this._live.length > 400) this._live.splice(0, this._live.length - 400);
  // A new state, or the same one again since a later moment (a change came and went unseen): read the history again.
  if (this._seen !== undefined && (this._seen !== st.state || this._seenAt !== st.last_changed)) this._changed = true;
  this._seen = st.state; this._seenAt = st.last_changed;
 }
 statIds() { return [...this._config.gas, this._config.starts].filter(id => id && this.st(id)); }
 refresh() {
  const hass = this._hass;
  if (!hass || !this.isConnected || typeof hass.callWS !== 'function') return;
  const now = Date.now(), zone = houseZone(hass), day = midnight(now, zone);
  const busy = key => now - this._pending[key] < PENDING_MS;  // a read that never answers stops nothing for long
  if (this.st(this._config.activity) && !busy('history')
      && (this._fetched.day !== day || (this._changed && now - this._fetched.history >= HISTORY_MS))) this.readHistory(day);
  const ids = this.statIds();
  if (ids.length && !busy('stats') && (this._fetched.statsDay !== day || now - this._fetched.stats >= STATS_MS)) this.readStats(ids, day, zone);
 }
 async readHistory(day) {
  const gen = this._gen, id = this._config.activity;
  this._pending.history = Date.now(); this._changed = false;
  try {
   const result = await this._hass.callWS({type: 'history/history_during_period', start_time: new Date(day).toISOString(),
    entity_ids: [id], minimal_response: true, no_attributes: true});
   if (gen !== this._gen) return;
   const list = changes(result?.[id]);
   this._history = {day, list};
   const newest = list.length ? list[list.length - 1].t : day;
   this._live = this._live.filter(c => c.t > newest);
  } catch (e) {
   if (gen !== this._gen) return;
   this._changed = true;  // tried again with the next change, 5 minutes on
  }
  this._fetched.day = day; this._fetched.history = Date.now(); this._pending.history = 0;
  this.render();
 }
 async readStats(ids, day, zone) {
  const gen = this._gen, hass = this._hass;
  this._pending.stats = Date.now();
  const days = Array.from({length: 7}, (_, i) => midnight(day, zone, i - 6));
  try {
   const [week, ...today] = await Promise.all([
    hass.callWS({type: 'recorder/statistics_during_period', start_time: new Date(days[0]).toISOString(), period: 'day',
     statistic_ids: ids, types: ['change']}),
    ...ids.map(id => hass.callWS({type: 'recorder/statistic_during_period', statistic_id: id, calendar: {period: 'day'},
     types: ['change']}).catch(() => null))]);
   if (gen !== this._gen) return;
   const per = {};
   for (const id of ids) {
    const values = Array(7).fill(null);
    for (const row of Array.isArray(week?.[id]) ? week[id] : []) {
     const start = typeof row?.start === 'number' ? row.start : Date.parse(row?.start), change = numeric(row?.change);
     const i = days.findIndex(d => Math.abs(d - start) < DAY_MS / 2);
     if (i >= 0 && change !== null) values[i] = change;
    }
    const now = numeric(today[ids.indexOf(id)]?.change);
    if (now !== null) values[6] = now;  // today to the last 5 minutes, as the statistic cards on the Boiler tab
    per[id] = values;
   }
   this._stats = {day, per};
  } catch (e) {
   if (gen !== this._gen) return;
   if (this._stats?.day !== day) this._stats = null;
  }
  this._fetched.statsDay = day; this._fetched.stats = Date.now(); this._pending.stats = 0;
  this.render();
 }
 // Today's change of the entities (a sum), or null while no statistics exist.
 today(ids) {
  const per = this._stats?.day === midnight(Date.now(), houseZone(this._hass)) ? this._stats.per : null;
  const values = ids.map(id => per?.[id]?.[6]).filter(v => v !== null && v !== undefined);
  return values.length ? values.reduce((a, b) => a + b, 0) : null;
 }

 // -- what the card says ---------------------------------------------------------------------------------------------
 // Heating now: the boiler activity, else the boiler's own heating bit, else the E32's request (null: not known).
 heatingOn() {
  const c = this._config, activity = this.st(c.activity), heating = this.st(c.heating), request = this.st(c.request);
  if (known(activity)) return activity.state === 'heating';
  if (known(heating)) return heating.state === 'on';
  return known(request) && numeric(request.state) !== null ? numeric(request.state) > 0 : null;
 }
 flow() { const st = this.st(this._config.flow); return known(st) ? numeric(st.state) : null; }
 // The strip's tone, icon and line: a problem wins; then what the boiler does; without it the boiler's bits or the request.
 status() {
  const c = this._config, problem = this.st(c.problem), activity = this.st(c.activity), flow = this.flow();
  const heating = () => flow !== null ? this.t('status_heating', {flow: this.degrees(flow)}) : this.t('status_heating_plain');
  if (problem?.state === 'on') {
   const reasons = Array.isArray(problem.attributes?.reasons) ? problem.attributes.reasons.filter(r => typeof r === 'string' && r) : [];
   const reason = typeof problem.attributes?.reason === 'string' && problem.attributes.reason ? problem.attributes.reason
    : reasons[0] || this.stateText(problem);
   return {tone: 'error', icon: ICON.error, line: this.t('attention', {reason}), problem: true, reasons};
  }
  if (known(activity) && KIND[activity.state]) {
   const kind = KIND[activity.state];
   if (kind === 'heat') return {tone: 'heat', icon: ICON.heat, line: heating()};
   if (kind === 'rest') return {tone: 'rest', icon: ICON.rest, line: this.t('idle')};
   return {tone: kind, icon: ICON[kind], line: this.stateText(activity) || ACTIVITY_EN[activity.state]};
  }
  const bit = this.st(c.heating), water = this.st(c.hot_water);
  if (bit?.state === 'on') return {tone: 'heat', icon: ICON.heat, line: heating()};
  if (water?.state === 'on') return {tone: 'water', icon: ICON.water, line: this.t('hot_water')};
  if (bit?.state === 'off' && (!water || water.state === 'off')) return {tone: 'rest', icon: ICON.rest, line: this.t('idle')};
  const request = this.st(c.request), value = known(request) ? numeric(request.state) : null;
  if (value !== null && value > 0) return {tone: 'heat', icon: ICON.heat, line: this.t('request', {flow: this.degrees(value)}), fromRequest: true};
  if (value !== null) return {tone: 'rest', icon: ICON.rest, line: this.t('no_request'), fromRequest: true};
  return {tone: 'wait', icon: ICON.wait, line: this.t('waiting')};
 }
 // The line under it: the rooms that want heat (not the room shown in the card) and the boiler request.
 wanting(status, inlined) {
  const request = this.st(this._config.request);
  if (!known(request)) return '';
  const rooms = (Array.isArray(request.attributes?.rooms) ? request.attributes.rooms : [])
   .filter(room => room && room.demand === true && (inlined === undefined || room.id !== inlined));
  const value = numeric(request.state), out = [];
  if (rooms.length) out.push(rooms.length === 1 ? this.t('wants_one') : this.t('wants', {n: this.number(rooms.length)}));
  if (value !== null && value > 0 && !status.fromRequest) out.push(this.t('request', {flow: this.degrees(value)}));
  return out.join(' · ');
 }

 render() {
  const hass = this._hass, config = this._config;
  if (!hass || !config) return;
  const root = this.shadowRoot, focused = root.activeElement?.dataset?.focus;
  const card = make('ha-card', hass.themes?.darkMode ? {class: 'dark'} : {}), wrap = make('div', {class: 'wrap', role: 'group', 'aria-label': this.t('title')});
  card.append(wrap);
  const room = config.rooms[0] && this.st(config.rooms[0].entity) ? config.rooms[0] : null;
  const roomState = room ? this.st(room.entity) : null, status = this.status();
  wrap.append(this.statusStrip(status, room ? roomState.attributes?.room_id : undefined));
  if (status.reasons?.length) {
   // Every reason, behind "All reasons" (kept open over a redraw).
   const details = make('details', {class: 'reasons'}), list = make('ul'), summary = make('summary', {'data-focus': 'reasons'}, this.t('all_reasons'));
   for (const reason of status.reasons) list.append(make('li', {}, reason));
   details.append(summary, list);
   details.open = this._open;
   // The click comes before the toggle (which is a later task): a redraw in between keeps it.
   summary.addEventListener('click', () => { this._open = !details.open; });
   details.addEventListener('toggle', () => { if (details.isConnected) this._open = details.open; });
   wrap.append(details);
  }
  const figures = this.figures(room, roomState);
  if (figures) wrap.append(figures);
  const strip = this.dayStrip();
  if (strip) wrap.append(strip);
  root.replaceChildren(make('style', {}, STYLE), card);
  if (focused) root.querySelector(`[data-focus="${focused}"]`)?.focus({preventScroll: true});
 }
 statusStrip(status, inlined) {
  const config = this._config;
  const box = make('div', {class: 'status tone-' + status.tone, 'data-status': status.tone});
  const main = make('div', {class: 'main'}), words = make('div', {class: 'words'});
  words.append(make('p', {class: 'line'}, status.line));
  const sub = this.wanting(status, inlined);
  if (sub) words.append(make('p', {class: 'sub'}, sub));
  main.append(icon(status.icon), words);
  box.append(main);
  if (status.problem) {
   // A tap leads to the fix: Repairs (Home Assistant's own navigation: the new path and location-changed). The link
   // is the icon and the words; the house mode chip beside it is a control of its own.
   Object.assign(main.dataset, {focus: 'problem'});
   main.setAttribute('role', 'link'); main.setAttribute('tabindex', '0');
   const go = () => {
    try { history.pushState(null, '', '/config/repairs'); } catch (e) { /* not on a Home Assistant page */ }
    window.dispatchEvent(new CustomEvent('location-changed', {detail: {replace: false}}));
   };
   main.addEventListener('click', go);
   main.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  }
  const mode = this.st(config.mode);
  if (mode) {
   const label = this.stateText(mode);
   const chip = make('button', {class: 'chip', type: 'button', 'data-focus': 'mode', 'aria-label': this.t('mode', {mode: label}),
    title: this.t('mode', {mode: label})});
   chip.append(icon('mdi:home-account'), make('span', {}, label));
   chip.addEventListener('click', () => this.moreInfo(config.mode));
   box.append(chip);
  }
  return box;
 }
 moreInfo(entityId) { this.dispatchEvent(new CustomEvent('hass-more-info', {bubbles: true, composed: true, detail: {entityId}})); }
 figure(key, label, value, extra) {
  const box = make('div', {class: 'figure', 'data-figure': key});
  box.append(make('p', {class: 'label'}, label));
  const shown = value === null ? DASH : value;
  box.append(make('p', {class: 'value' + (value === null ? ' unknown' : '')}, shown));
  if (extra) box.append(extra);
  return box;
 }
 figures(room, roomState) {
  const config = this._config, list = [];
  if (room) list.push(this.roomFigure(room, roomState));
  if ([config.activity, config.heating, config.request].some(id => this.st(id))) {
   const on = this.heatingOn(), flow = this.flow();
   list.push(this.figure('heating', this.t('heating'), on === null ? null
    : on ? (flow !== null ? this.t('heating_on', {flow: this.degrees(flow)}) : this.t('heating_on_plain')) : this.t('heating_off')));
  }
  const taps = this.st(config.taps);
  if (taps) {
   const n = known(taps) ? numeric(taps.state) : null, activity = this.st(config.activity), water = this.st(config.hot_water);
   const running = known(activity) ? RUNNING.has(activity.state) : water?.state === 'on';
   const count = n === null ? null : Math.round(n);
   list.push(this.figure('hot_water', this.t('hot_water'), count === null ? null
    : count === 0 ? this.t('taps_none') : count === 1 ? this.t('taps_one') : this.t('taps', {n: this.number(count)}),
    running ? make('p', {class: 'running', 'data-running': ''}, this.t('running')) : null));
  }
  const gas = config.gas.filter(id => this.st(id));
  if (gas.length) list.push(this.gasFigure(gas));
  if (this.st(config.starts)) {
   const starts = this.today([config.starts]);
   list.push(this.figure('starts', this.t('starts_today'), starts === null ? null : this.number(Math.round(starts))));
  }
  if (!list.length) return null;
  // Phone: two columns, the room across both, an odd last figure across both. Wide (≥ 720 px): the room
  // takes the left half (as many rows as the other figures need), the others two by two beside it; without a
  // room the figures share one row.
  const grid = make('div', {class: 'figures'}), small = list.filter(f => f.dataset.figure !== 'room'), n = small.length;
  if (room) {
   list[0].classList.add('p2');
   if (n) { list[0].classList.add('w2'); list[0].style.setProperty('--rr', Math.ceil(n / 2)); grid.style.setProperty('--wc', 4); }
   else grid.style.setProperty('--wc', 1);
   if (n % 2) small[n - 1].classList.add('p2', 'w2');
  } else {
   grid.style.setProperty('--wc', Math.max(1, n));
   if (n % 2) small[n - 1].classList.add('p2');
  }
  grid.append(...list);
  return grid;
 }
 roomFigure(room, st) {
  const hass = this._hass, a = st.attributes || {}, tone = ROOM_TONE[st.state];
  const box = make('div', {class: 'figure room', 'data-figure': 'room', role: 'button', tabindex: '0', 'data-focus': 'room'});
  const label = make('p', {class: 'label'});
  label.append(make('span', {}, room.name || a.friendly_name || room.entity));
  if (PRESENCE[a.presence]) {
   const text = this.word('room_reason.state_attributes.presence.state.' + a.presence) || a.presence;
   label.append(icon(PRESENCE[a.presence], {role: 'img', 'aria-label': text, title: text, class: a.presence.endsWith('_home') ? 'on' : null,
    'data-presence': a.presence}));
  }
  if (a.window === 'open' || a.window === 'pending') {
   const contact = typeof a.values?.contact === 'string' && a.values.contact ? a.values.contact + ': ' : '';
   const text = contact + (this.word('room_reason.state_attributes.window.state.' + a.window) || a.window);
   label.append(icon('mdi:window-open-variant', {role: 'img', 'aria-label': text, title: text, class: 'warn', 'data-window': a.window}));
  }
  box.append(label);
  const value = make('p', {class: 'value'}), now = numeric(a.temperature), target = numeric(a.setpoint);
  if (tone && now !== null) {
   value.append(now.toLocaleString(locale(hass), {minimumFractionDigits: 1, maximumFractionDigits: 1}));
   if (st.state !== 'off' && target !== null) {
    value.append(make('span', {class: 'arrow', 'aria-hidden': 'true'}, '→'),
     make('span', {class: 'target'}, target.toLocaleString(locale(hass), {maximumFractionDigits: 1})));
   }
   value.append(make('small', {}, NBSP + '°C'));
  } else { value.textContent = DASH; value.classList.add('unknown'); }
  box.append(value);
  const why = make('p', {class: 'why tone-' + (tone || 'off'), 'data-reason': st.state});
  why.append(icon(ROOM_ICON[st.state] || 'mdi:information-outline'), make('span', {}, this.roomSentence(st)));
  box.append(why);
  box.addEventListener('click', () => this.moreInfo(room.entity));
  box.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.moreInfo(room.entity); } });
  return box;
 }
 // The room status card's sentence (strings.json room_reason line), its values formatted for this viewer.
 roomSentence(st) {
  const a = st.attributes || {}, v = a.values && typeof a.values === 'object' ? a.values : {}, hass = this._hass;
  if (RESTATED.has(st.state) || !ROOM_TONE[st.state]) return this.stateText(st);
  const at = iso => {
   const ms = typeof iso === 'string' ? Date.parse(iso) : NaN;
   if (!Number.isFinite(ms)) return '';
   const zone = houseZone(hass), same = midnight(ms, zone) === midnight(Date.now(), zone);
   try {
    return new Date(ms).toLocaleString(locale(hass), {hour: '2-digit', minute: '2-digit', hour12: hour12(hass), timeZone: zone,
     ...(same ? {} : {weekday: 'short'})});
   } catch (e) { return this.time(ms); }
  };
  const deg = (value, fixed) => finite(value) ? value.toLocaleString(locale(hass), {minimumFractionDigits: fixed ? 1 : 0, maximumFractionDigits: 1}) : '–';
  const values = {contact: typeof v.contact === 'string' ? v.contact : '', since: at(v.since), time: at(v.time), until: at(v.until),
   temperature: deg(v.temperature, true), target: deg(v.target)};
  const line = typeof a.line === 'string' ? this.word('room_reason.state_attributes.line.state.' + a.line, values) : '';
  return together(line || this.stateText(st));
 }
 gasFigure(ids) {
  const total = this.today(ids), unit = this.st(ids[0])?.attributes?.unit_of_measurement;
  const value = total === null ? null : this.number(total, 1) + (typeof unit === 'string' && unit ? NBSP + unit : '');
  const box = this.figure('gas', this.t('gas_today'), value);
  // The last 7 days: the gas of every day that has statistics; no line before there are two days.
  const per = this._stats?.day === midnight(Date.now(), houseZone(this._hass)) ? this._stats.per : null;
  const points = [];
  for (let i = 0; i < 7; i++) {
   const values = ids.map(id => per?.[id]?.[i]).filter(v => v !== null && v !== undefined);
   if (values.length) points.push({i, v: values.reduce((a, b) => a + b, 0)});
  }
  if (points.length >= 2) {
   const row = make('div', {class: 'trend'});
   // "; " between the values: a comma is the decimal separator in Dutch and Polish.
   const label = this.t('week', {values: points.map(p => this.number(p.v, 1)).join('; ') + (unit ? NBSP + unit : '')});
   row.append(box.querySelector('.value'), sparkline(points, label));
   box.append(row);
  }
  return box;
 }
 // The day so far: midnight to now in the house's time zone; the rest of the day a hairline.
 dayStrip() {
  const config = this._config, activity = this.st(config.activity);
  if (!known(activity)) return null;
  const zone = houseZone(this._hass), now = Date.now(), start = midnight(now, zone), end = midnight(now, zone, 1);
  const history = this._history?.day === start ? this._history.list : [];
  const newest = history.length ? history[history.length - 1].t : -Infinity;
  const list = [...history, ...this._live.filter(c => c.t > newest)];
  const current = {s: activity.state, t: Date.parse(activity.last_changed)};
  if (Number.isFinite(current.t) && (!list.length || current.t > list[list.length - 1].t)) list.push(current);
  const pct = ms => (ms - start) / (end - start) * 100;
  const box = make('div', {class: 'today'}), head = make('div', {class: 'today-head'}), legend = make('ul', {class: 'legend'});
  for (const [kind, key] of LEGEND) {
   const li = make('li', {'data-key': kind});
   li.append(make('i', {class: kind}), this.t(key));
   legend.append(li);
  }
  head.append(make('span', {class: 'today-title'}, this.t('today')), legend);
  const strip = make('div', {class: 'strip', 'data-strip': ''}), spoken = {heat: [], water: [], keep: []};
  const drawn = runs(list, start, now).filter(r => r.kind);
  drawn.forEach((r, i) => {
   const prev = drawn[i - 1], colored = r.kind !== 'rest', span = this.time(r.start) + '–' + this.time(r.end);
   const word = colored ? this.t(LEGEND.find(l => l[0] === r.kind)[1]) : this.t('idle');
   const seg = make('div', {class: ['seg', r.kind, i === 0 ? 'first' : '', i === drawn.length - 1 ? 'last' : '',
    colored && prev && prev.kind !== 'rest' && prev.end >= r.start ? 'gap' : ''].filter(Boolean).join(' '),
   style: `left:${pct(r.start).toFixed(3)}%;width:${(pct(r.end) - pct(r.start)).toFixed(3)}%`, title: word + ' ' + span, 'data-kind': r.kind});
   strip.append(seg);
   if (colored) spoken[r.kind].push(span);
  });
  const said = LEGEND.filter(([kind]) => spoken[kind].length).map(([kind, key]) => this.t(key) + ' ' + spoken[kind].join(', '));
  strip.setAttribute('role', 'img');
  strip.setAttribute('aria-label', this.t('today') + ': ' + (said.length ? said.join('; ') : this.t('idle')) + '.');
  const ticks = make('div', {class: 'ticks', 'aria-hidden': 'true'}), p = parts(now, zone), twelve = hour12(this._hass);
  for (const hour of [0, 6, 12, 18]) {
   const at = wallTime(p.year, p.month - 1, p.day, hour, zone);
   let text = String(hour).padStart(2, '0');
   if (twelve) try { text = new Date(at).toLocaleTimeString(locale(this._hass), {hour: 'numeric', hour12: true, timeZone: zone}); } catch (e) { /* 24 h */ }
   ticks.append(make('span', {style: `left:${pct(at).toFixed(3)}%`}, text));
  }
  box.append(head, strip, ticks);
  return box;
 }
}
// Other dashboard cards (HACS resources) may later replace window.customElements with a scoped-registry
// polyfill whose get() does not see elements defined before it; Home Assistant then reports "Custom element
// doesn't exist". So: define now, and again (a fresh subclass) whenever the registry in use lacks the element.
// Never throws. (The same guard as e32-week-card.js, room-status-card.js and heating-curve-card.js.)
const ensureDefined = (name, cls) => {
 let own = cls;
 const check = () => {
  try { if (!customElements.get(name)) { customElements.define(name, own); own = class extends cls {}; } }
  catch (e) { own = class extends cls {}; }
 };
 check();
 if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', check, {once: true});
 if (document.readyState !== 'complete') window.addEventListener('load', check, {once: true});
 for (const ms of [0, 250, 1000, 3000, 10000]) setTimeout(check, ms);
 window.addEventListener('location-changed', check);
 setInterval(check, 500);
 return check;
};
ensureDefined('openthermostat-house', OpenThermostatHouse);
window.customCards = window.customCards || [];
if (!window.customCards.some(c => c.type === 'openthermostat-house'))
 window.customCards.push({type: 'openthermostat-house', name: 'OpenThermostat house',
  description: 'The house at a glance: what the boiler does now, today in figures and the day so far.'});
