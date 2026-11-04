/* The Boiler view's "Now" card (OpenThermostat, E32 rc.5): the boiler at a glance, from Home Assistant alone.

   One wide card, first on the Boiler view (dashboard.py _boiler_now, room_overview.BOILER_NOW_CARD_TYPE), drawn as
   the owner's sketch and in the family of the Overview's house card (house-card.js): a band in the full colour of
   what the boiler does now, its words in white (heating in deep orange, hot water in blue, resting in grey, a
   fault of the boiler in red), with the display code in words under it ("Display code -H: heating", in Dutch
   "Code -H: verwarmen", what to do for a code that is not normal operation) and on the right the connection with
   the boiler and whether it serves hot water;
   under it four figures, large, two by two on a phone and in one row on a wide card: the water to the heating (what
   is asked of the boiler and the most the E32 asks near the target), the water back (the difference), the burner
   power with a small arc (low, half or full fire) and the burner starts in the last hour (calm or switching on and
   off too often, and today's starts).

   Only Home Assistant is read: the states of the entities in the card's config and, for today's burner starts, the
   statistic of the starts sensor (recorder/statistic_during_period, calendar day, as Home Assistant's own statistic
   card asks it; at most every 5 minutes and when the day changes, never after the card left the page). Nothing
   talks to the E32. A figure without its entity is left out; one that is not known shows "—".

   The words are the integration's translations (strings.json entity.sensor.boiler_activity.state_attributes.card,
   the boiler activity's own states and the display code sensor's words), so every viewer reads them in their own
   Home Assistant language; English is only the last resort. The band wears Home Assistant's theme colours darkened
   until white words on it read at 4.5:1 at least, in the light and the dark theme (the house card's rule). */
const PREFIX = 'component.open_thermostat.entity.sensor.';
const CARD = 'boiler_activity.state_attributes.card.state.';
const TEXT = {title: 'The boiler now', no_data: 'No data from the boiler', boiler: 'Boiler', code: 'Display code {code}: {meaning}',
 code_bare: 'Display code {code}', code_fault: '{severity} · display code {code}', link: 'connection with the boiler: {state}', link_good: 'good',
 link_none: 'none', dhw: 'hot water: {state}', yes: 'yes', no: 'no', flow: 'Water to heating', asked: 'asked {flow} °C',
 would_ask: 'E32 would ask {flow} °C', no_request: 'no request', ceiling: 'at most {flow} °C', back: 'Water back',
 difference: 'difference {n} °C', power: 'Burner power', power_off: 'burner off', power_low: 'low fire, calm', power_mid: 'medium fire',
 power_full: 'full fire', starts: 'Starts in the last hour', calm: 'calm', often: 'switching on and off too often', today: 'today {n}'};
const DASH = '—';  // a figure not known yet: the same in every language
const NBSP = ' ';  // a no-break space between a figure and its unit
// What the boiler does (boiler_activity, heating_link.BOILER_ACTIVITIES): the band's tone and icon, as on the house card.
const KIND = {heating: 'heat', tapping: 'water', hot_water: 'water', keep_warm: 'keep', charging: 'keep', idle: 'rest'};
const ICON = {heat: 'mdi:fire', water: 'mdi:faucet', keep: 'mdi:water-thermometer', rest: 'mdi:water-boiler',
 error: 'mdi:alert-circle-outline', none: 'mdi:water-boiler-off'};
const ACTIVITY_EN = {idle: 'Idle', heating: 'Heating', tapping: 'Tapping', keep_warm: 'Keeping warm', charging: 'Heating the hot water tank',
 hot_water: 'Hot water'};
// A display code that is a fault of the boiler (display_codes.FAULTS): the band turns red and says what to do.
const FAULTS = new Set(['blocking', 'locking', 'fault']);
const STATS_MS = 5 * 60000, TICK_MS = 60000, PENDING_MS = 2 * 60000;

// The house card's band and figures (house-card.js): the band in the theme colour darkened for white words; the figures
// a small muted label over a large number, its unit small and muted, a muted line under it, 1 px lines between them
// (shadows the grid's edge cuts off). The figures of one row share their label, number and line rows (a subgrid), so
// the numbers stand on one line also when a label takes two lines on a narrow phone. The burner power's arc and its
// number fit side by side at every width ("100 %" on a 320 px phone, four figures on a 720 px tablet): a smaller arc
// where a figure is narrow, and the number under the arc rather than cut off if a font is wider still.
const STYLE = `:host{display:block}
ha-card{display:block;overflow:hidden;color:var(--primary-text-color);
--oth-surface:var(--ha-card-background,var(--card-background-color,#fff));--oth-muted:var(--secondary-text-color,#6b6b6b);
--oth-line:var(--divider-color,rgba(127,127,127,.22));
--heat:var(--deep-orange-color,#ff6f22);--water:var(--blue-color,#2196f3);--grey:var(--grey-color,#9e9e9e);--error:var(--error-color,#db4437);
--oth-track:color-mix(in srgb,var(--primary-text-color,#212121) 9%,var(--oth-surface));
--band-heat:color-mix(in srgb,var(--heat) 75%,#000);--band-water:color-mix(in srgb,var(--water) 78%,#000);
--band-rest:color-mix(in srgb,var(--grey) 72%,#000);--band-error:color-mix(in srgb,var(--error) 88%,#000);--fire:var(--band-heat)}
ha-card.dark{--fire:var(--heat)}
p{margin:0}
.wrap{container:now/inline-size}
.tone-heat{--band:var(--band-heat)}.tone-water,.tone-keep{--band:var(--band-water)}.tone-rest,.tone-none{--band:var(--band-rest)}
.tone-error{--band:var(--band-error)}
.status{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:12px 16px;background:var(--band);color:#fff}
.main{display:flex;align-items:center;gap:10px;flex:1 1 0;min-width:min(100%,200px)}
.main>ha-icon{--mdc-icon-size:22px;color:#fff;display:flex;flex:none}.words{flex:1 1 auto;min-width:0}
.line{font-size:16px;font-weight:500;line-height:1.3;overflow-wrap:anywhere}
.sub{margin-top:2px;font-size:13px;line-height:1.35;overflow-wrap:anywhere}
.advice{margin-top:4px;font-size:13px;line-height:1.4;overflow-wrap:anywhere;text-wrap:pretty}
.meta{flex:1 1 100%;margin-left:32px;font-size:12px;line-height:1.35;overflow-wrap:anywhere}
.figures{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:hidden}
.figure{display:grid;grid-row:span 3;grid-template-rows:subgrid;min-width:0;padding:14px 16px 12px;
box-shadow:1px 0 0 var(--oth-line),0 1px 0 var(--oth-line);cursor:pointer}
.p2{grid-column:span 2}
.label{font-size:12px;line-height:16px;color:var(--oth-muted);overflow-wrap:anywhere}
.value{margin-top:4px;font-size:18px;line-height:1.25;overflow-wrap:anywhere}
.value .num{font-size:30px;font-weight:700;line-height:1.1;letter-spacing:-.01em}
.value .unit{font-weight:400;color:var(--oth-muted)}
.value.unknown{font-size:30px;line-height:1.1;color:var(--oth-muted)}
.note{margin-top:4px;font-size:12px;line-height:16px;color:var(--oth-muted);overflow-wrap:anywhere}
.dial{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;margin-top:4px}.dial .value{margin-top:0}
.arc{display:block;flex:none;width:56px;height:34px;overflow:visible}
.arc path{fill:none;stroke-width:7;stroke-linecap:round}.arc .track{stroke:var(--oth-track)}.arc .level{stroke:var(--fire)}
[data-focus]:focus{outline:none}[data-focus]:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:-3px}
@container now (max-width:360px){.status{padding:12px}.figure{padding:12px 12px 10px}.arc{width:44px;height:27px}.dial{column-gap:8px}}
@container now (min-width:720px){.status{padding:14px 22px}.line{font-size:18px}.main>ha-icon{--mdc-icon-size:24px}
.meta{flex:0 1 auto;margin-left:auto;font-size:13px;text-align:right}
.figures{grid-template-columns:repeat(var(--n,4),minmax(0,1fr))}.p2{grid-column:auto}
.figure{padding:18px 22px 16px}.label{font-size:13px}.value .num,.value.unknown{font-size:34px}.note{margin-top:6px;font-size:13px;line-height:18px}
.arc{width:64px;height:38px}}
@container now (min-width:720px) and (max-width:899px){.figure{padding:16px 16px 14px}.arc{width:48px;height:29px}.dial{column-gap:8px}}`;

const locale = hass => hass?.locale?.language || hass?.language || 'en';
const finite = value => typeof value === 'number' && Number.isFinite(value);
const numeric = value => { const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value; return finite(n) ? n : null; };
// A figure and its unit stay on one line ("41 °C" is never cut into "41" and "°C" on a phone).
const together = text => typeof text === 'string' ? text.replace(/ (°C|%)/g, NBSP + '$1') : text;
// In a line under a figure a number stays with the word before it ("today 14", "at most 40 °C"), and the dot between
// two parts stays at the end of a line: a phone breaks between the parts, never inside one.
const bind = text => text.replace(/ (?=[−-]?\d)/g, NBSP);
const SEP = NBSP + '· ';
const known = st => !!st && typeof st.state === 'string' && !['unknown', 'unavailable', ''].includes(st.state);
const entityId = value => typeof value === 'string' && value.includes('.') ? value : undefined;
// "Heating" after "Display code -H:" reads "heating"; a word in capitals ("EMS") keeps them.
const lower = text => /^\p{Lu}\p{Ll}/u.test(text) ? text[0].toLocaleLowerCase() + text.slice(1) : text;
const SVG = 'http://www.w3.org/2000/svg';
const make = (tag, attrs = {}, text) => {
 const e = tag.startsWith('svg:') ? document.createElementNS(SVG, tag.slice(4)) : document.createElement(tag);
 for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v);
 if (text !== undefined) e.textContent = text;
 return e;
};
const icon = name => make('ha-icon', {icon: name});
// The house's day (Home Assistant's time zone): the calendar day of the statistic, and when it changes.
const dayOf = (ms, timeZone) => {
 try { return new Intl.DateTimeFormat('en-CA', {timeZone, year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date(ms)); }
 catch (e) { return new Date(ms).toISOString().slice(0, 10); }
};
// The burner power as a half circle, filled from the left (decorative: the number beside it says it).
function arc(pct) {
 const svg = make('svg:svg', {class: 'arc', viewBox: '0 0 56 34', 'aria-hidden': 'true'});
 svg.append(make('svg:path', {class: 'track', d: 'M6 30 A22 22 0 0 1 50 30'}));
 if (pct > 0) {
  const angle = Math.PI * (1 - Math.min(pct, 100) / 100);
  const x = (28 + 22 * Math.cos(angle)).toFixed(2), y = (30 - 22 * Math.sin(angle)).toFixed(2);
  svg.append(make('svg:path', {class: 'level', d: `M6 30 A22 22 0 0 1 ${x} ${y}`, 'data-pct': Math.round(pct)}));
 }
 return svg;
}

class OpenThermostatBoilerNow extends HTMLElement {
 constructor() {
  super(); this.attachShadow({mode: 'open'});
  this._key = null; this._gen = 0; this._timer = null;
  this._today = null; this._fetched = {day: null, at: 0}; this._pending = 0;
 }
 setConfig(config) {
  const id = entityId;
  const c = {activity: id(config?.activity), heating: id(config?.heating), hot_water: id(config?.hot_water), code: id(config?.code),
   flow: id(config?.flow), return: id(config?.return), modulation: id(config?.modulation), starts: id(config?.starts),
   starts_today: id(config?.starts_today), cycling: id(config?.cycling), request: id(config?.request), ceiling: id(config?.ceiling)};
  if (!['activity', 'heating', 'hot_water', 'code', 'flow', 'return', 'modulation', 'starts'].some(key => c[key]))
   throw new Error('This card needs a boiler sensor of OpenThermostat (activity, heating, hot_water, code, flow, return, modulation or starts: sensor.…); the OpenThermostat dashboard adds it for you.');
  // A new config (the card editor sets it again while the card is on the page): an answer still on its way for the
  // old one is dropped, and the timer follows whether there are today's starts to read.
  this._config = c; this._key = null; this._today = null; this._fetched = {day: null, at: 0}; this._gen++; this._pending = 0;
  this.arm();
  if (this._hass) { this.refresh(); this.render(); }
 }
 set hass(hass) {
  this._hass = hass;
  if (!this._config) return;
  this.refresh();
  // Only a new state of its own entities, the language or the theme redraws; Home Assistant sets hass on every change.
  const key = [...this.entities().map(id => hass?.states?.[id]), locale(hass), hass?.themes?.darkMode];
  if (this._key && key.length === this._key.length && key.every((v, i) => v === this._key[i])) return;
  this._key = key; this.render();
 }
 connectedCallback() {
  this.arm();
  if (this._hass && this._config) this.refresh();
 }
 disconnectedCallback() {
  clearInterval(this._timer); this._timer = null;
  this._gen++;  // what is still on its way is dropped when it comes
  this._pending = 0;
 }
 // Once a minute, while on the page and with today's starts to show: they are asked again when due (Home Assistant only).
 arm() {
  const wanted = this.isConnected && !!this._config?.starts_today;
  if (wanted && !this._timer) this._timer = setInterval(() => this.refresh(), TICK_MS);
  else if (!wanted && this._timer) { clearInterval(this._timer); this._timer = null; }
 }
 getCardSize() { return 4; }
 getGridOptions() { return {columns: 'full'}; }  // the whole section, also one across two columns
 entities() { return Object.values(this._config).filter(Boolean); }
 st(id) { return id ? this._hass?.states?.[id] || null : null; }
 // A text of the card (strings.json …boiler_activity.state_attributes.card), its {placeholders} filled; English as the last resort.
 t(key, values = {}) {
  let text = '';
  try { text = this._hass?.localize?.(PREFIX + CARD + key, values) || ''; } catch (e) { text = ''; }
  return together(typeof text === 'string' && text ? text : TEXT[key].replace(/\{(\w+)\}/g, (all, k) => k in values ? values[k] : all));
 }
 // What the boiler does in Home Assistant's own words (the boiler activity's states), for the band.
 activityWord(state) {
  const st = this.st(this._config.activity);
  if (st) try { const text = this._hass?.formatEntityState?.(st, state); if (typeof text === 'string' && text && text !== state) return text; } catch (e) { /* older frontend */ }
  let text = '';
  try { text = this._hass?.localize?.(PREFIX + 'boiler_activity.state.' + state) || ''; } catch (e) { text = ''; }
  return typeof text === 'string' && text ? text : ACTIVITY_EN[state];
 }
 number(value) {
  return value.toLocaleString(locale(this._hass), {maximumFractionDigits: 0}).replace('-', '−');
 }
 value(id) { const st = this.st(id); return known(st) ? numeric(st.state) : null; }
 moreInfo(entityId) { this.dispatchEvent(new CustomEvent('hass-more-info', {bubbles: true, composed: true, detail: {entityId}})); }

 // -- today's burner starts: the statistic of the starts sensor, throttled; never the E32 -------------------------
 refresh() {
  const hass = this._hass, id = this._config?.starts_today;
  if (!hass || !id || !this.st(id) || !this.isConnected || typeof hass.callWS !== 'function') return;
  const now = Date.now(), day = dayOf(now, hass.config?.time_zone || undefined);
  if (now - this._pending < PENDING_MS) return;  // a read that never answers stops nothing for long
  if (this._fetched.day === day && now - this._fetched.at < STATS_MS) return;
  this.readToday(id, day);
 }
 async readToday(id, day) {
  const gen = this._gen;
  this._pending = Date.now();
  try {
   const result = await this._hass.callWS({type: 'recorder/statistic_during_period', statistic_id: id, calendar: {period: 'day'},
    types: ['change']});
   if (gen !== this._gen) return;
   this._today = {day, value: numeric(result?.change)};
  } catch (e) {
   if (gen !== this._gen) return;
   if (this._today?.day !== day) this._today = null;
  }
  this._fetched = {day, at: Date.now()}; this._pending = 0;
  this.render();
 }
 today() {
  const hass = this._hass, day = dayOf(Date.now(), hass?.config?.time_zone || undefined);
  return this._today?.day === day && this._today.value !== null ? Math.round(this._today.value) : null;
 }

 // -- what the card says -------------------------------------------------------------------------------------------
 // The display code: {code (with its cause number unless normal), meaning, severity, severity text, advice}, or null.
 code() {
  const st = this.st(this._config.code);
  if (!known(st)) return null;
  const code = st.state.replace(/[\s.]/g, '');
  if (!code || code === '--') return null;
  const a = st.attributes || {}, severity = typeof a.severity === 'string' ? a.severity : null;
  const cause = Number.isInteger(a.cause) && severity && severity !== 'normal' ? ' ' + a.cause : '';
  const text = key => typeof a[key] === 'string' && a[key].trim() ? a[key].trim() : null;
  return {code: code + cause, meaning: text('meaning'), severity, severity_text: text('severity_text'), advice: text('advice')};
 }
 // The band: a fault of the boiler first, then what the boiler does (the activity, else the boiler's own bits).
 status(code) {
  const c = this._config;
  if (code && FAULTS.has(code.severity) && code.meaning) return {tone: 'error', icon: ICON.error, line: code.meaning, fault: true};
  const activity = this.st(c.activity);
  if (known(activity) && KIND[activity.state]) {
   const kind = KIND[activity.state];
   return {tone: kind, icon: ICON[kind], line: this.activityWord(activity.state)};
  }
  const heating = this.st(c.heating), water = this.st(c.hot_water);
  if (heating?.state === 'on') return {tone: 'heat', icon: ICON.heat, line: this.activityWord('heating')};
  if (water?.state === 'on') return {tone: 'water', icon: ICON.water, line: this.activityWord('hot_water')};
  if (heating?.state === 'off' && (!water || water.state === 'off')) return {tone: 'rest', icon: ICON.rest, line: this.activityWord('idle')};
  // Not known what it does: "Boiler" while its figures come in (an older boiler without the bits), else no data at all.
  const anything = [c.code, c.flow, c.return, c.modulation, c.starts].some(id => known(this.st(id)));
  return anything ? {tone: 'none', icon: ICON.rest, line: this.t('boiler')} : {tone: 'none', icon: ICON.none, line: this.t('no_data')};
 }
 // On the right of the band: the connection with the boiler (its own values come in; the E32 is heard but they do
 // not; nothing heard) and whether it serves hot water.
 meta() {
  const c = this._config, parts = [];
  const own = [c.flow, c.return, c.modulation, c.code, c.heating, c.hot_water].filter(Boolean);
  if (own.length) {
   const link = own.some(id => known(this.st(id))) ? 'good'
    : [c.activity, c.request, c.starts].some(id => this.st(id) && this.st(id).state !== 'unavailable') ? 'none' : null;
   parts.push(['link', link, this.t('link', {state: link ? this.t('link_' + link) : DASH})]);
  }
  const water = this.st(c.hot_water), activity = this.st(c.activity);
  let serving;
  if (c.hot_water) serving = known(water) ? water.state === 'on' : null;
  else if (c.activity) serving = known(activity) && KIND[activity.state] ? ['water', 'keep'].includes(KIND[activity.state]) : null;
  if (serving !== undefined) parts.push(['dhw', serving === null ? null : serving ? 'on' : 'off',
   this.t('dhw', {state: serving === null ? DASH : this.t(serving ? 'yes' : 'no')})]);
  if (!parts.length) return null;
  const meta = make('p', {class: 'meta'});
  parts.forEach(([key, state, text], i) => {
   if (i) meta.append(SEP);
   // "…: good" never alone on a line.
   meta.append(make('span', {['data-' + key]: state || 'unknown'}, text.replace(/ (?=\S+$)/, NBSP)));
  });
  return meta;
 }

 render() {
  const hass = this._hass, config = this._config;
  if (!hass || !config) return;
  const root = this.shadowRoot, focused = root.activeElement?.dataset?.focus;
  const card = make('ha-card', hass.themes?.darkMode ? {class: 'dark'} : {});
  const wrap = make('div', {class: 'wrap', role: 'group', 'aria-label': this.t('title')});
  card.append(wrap);
  wrap.append(this.band());
  const figures = this.figures();
  if (figures) wrap.append(figures);
  root.replaceChildren(make('style', {}, STYLE), card);
  if (focused) root.querySelector(`[data-focus="${focused}"]`)?.focus({preventScroll: true});
 }
 band() {
  const code = this.code(), status = this.status(code);
  const box = make('div', {class: 'status tone-' + status.tone, 'data-status': status.tone});
  const main = make('div', {class: 'main'}), words = make('div', {class: 'words'});
  words.append(make('p', {class: 'line'}, status.line));
  if (code) {
   // "Display code -H: heating"; a fault (the band says what it is) "Lockout: the boiler needs a reset · display code 3L 214".
   const sub = status.fault ? this.t('code_fault', {severity: code.severity_text || code.severity, code: code.code})
    : code.meaning ? this.t('code', {code: code.code, meaning: lower(code.meaning)}) : this.t('code_bare', {code: code.code});
   words.append(make('p', {class: 'sub', 'data-code': code.severity || ''}, sub));
   if (code.advice && code.severity && code.severity !== 'normal') words.append(make('p', {class: 'advice'}, code.advice));
  }
  main.append(icon(status.icon), words);
  box.append(main);
  const meta = this.meta();
  if (meta) box.append(meta);
  return box;
 }
 // One figure: a small muted label, the number large with its unit small and muted (or "—"), a muted line under it.
 figure(key, entity, label, num, unit, notes, extra) {
  const box = make('div', {class: 'figure', 'data-figure': key, 'data-focus': key, role: 'button', tabindex: '0'});
  box.append(make('p', {class: 'label'}, label));
  const value = make('p', {class: 'value'});
  if (num === null) { value.classList.add('unknown'); value.textContent = DASH; }
  else {
   value.append(make('span', {class: 'num'}, num));
   if (unit) value.append(make('span', {class: 'unit'}, NBSP + unit));
  }
  if (extra) { const dial = make('div', {class: 'dial'}); dial.append(extra, value); box.append(dial); }
  else box.append(value);
  const said = notes.filter(Boolean);
  if (said.length) box.append(make('p', {class: 'note'}, said.map(bind).join(SEP)));
  box.addEventListener('click', () => this.moreInfo(entity));
  box.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.moreInfo(entity); } });
  return box;
 }
 figures() {
  const c = this._config, list = [];
  const flow = this.value(c.flow), back = this.value(c.return);
  const flowWhole = flow === null ? null : Math.round(flow), backWhole = back === null ? null : Math.round(back);
  if (c.flow) list.push(this.figure('flow', c.flow, this.t('flow'), flowWhole === null ? null : this.number(flowWhole), '°C',
   [this.asked(), this.ceiling()]));
  if (c.return) {
   // The difference of the two numbers as they are shown (41 and 34: 7), never one the eye cannot check.
   const difference = flowWhole !== null && backWhole !== null ? this.t('difference', {n: this.number(flowWhole - backWhole)}) : null;
   list.push(this.figure('return', c.return, this.t('back'), backWhole === null ? null : this.number(backWhole), '°C', [difference]));
  }
  if (c.modulation) {
   const power = this.value(c.modulation), pct = power === null ? null : Math.max(0, Math.min(100, Math.round(power)));
   const band = pct === null ? null : pct === 0 ? 'power_off' : pct < 40 ? 'power_low' : pct < 80 ? 'power_mid' : 'power_full';
   list.push(this.figure('power', c.modulation, this.t('power'), pct === null ? null : this.number(pct), '%',
    [band && this.t(band)], arc(pct || 0)));
  }
  if (c.starts) {
   const starts = this.value(c.starts), cycling = this.st(c.cycling), today = c.starts_today ? this.today() : null;
   const word = known(cycling) ? (cycling.state === 'on' ? this.t('often') : cycling.state === 'off' ? this.t('calm') : null) : null;
   list.push(this.figure('starts', c.starts, this.t('starts'), starts === null ? null : this.number(Math.round(starts)), '',
    [word, today === null ? null : this.t('today', {n: this.number(today)})]));
  }
  if (!list.length) return null;
  // Wide (≥ 720 px): one row, as many columns as figures. Phone: two by two, an odd last one across both columns.
  const grid = make('div', {class: 'figures'});
  grid.style.setProperty('--n', list.length);
  if (list.length % 2) list[list.length - 1].classList.add('p2');
  grid.append(...list);
  return grid;
 }
 // What is asked of the boiler: the E32's request while it drives the boiler; in the trial run (or before the
 // takeover is confirmed) what it would ask; nothing said without a request sensor.
 asked() {
  const st = this.st(this._config.request), flow = known(st) ? numeric(st.state) : null;
  if (flow === null) return null;
  const a = st.attributes || {}, driving = a.mode !== 'shadow' && a.control !== 'awaiting_confirmation';
  if (flow <= 0) return driving ? this.t('no_request') : null;
  return this.t(driving ? 'asked' : 'would_ask', {flow: this.number(Math.round(flow))});
 }
 // The most the E32 asks near the target now (the flow document's ceiling_c in effect: Smart warm-up on, the E32
 // driving the boiler); only while it is known.
 ceiling() {
  const st = this.st(this._config.ceiling), ceiling = st && st.state !== 'unavailable' ? numeric(st.attributes?.ceiling_c) : null;
  return ceiling === null ? null : this.t('ceiling', {flow: this.number(Math.round(ceiling))});
 }
}
// Other dashboard cards (HACS resources) may later replace window.customElements with a scoped-registry
// polyfill whose get() does not see elements defined before it; Home Assistant then reports "Custom element
// doesn't exist". So: define now, and again (a fresh subclass) whenever the registry in use lacks the element.
// Never throws. (The same guard as e32-week-card.js, room-status-card.js, heating-curve-card.js and house-card.js.)
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
ensureDefined('openthermostat-boiler-now', OpenThermostatBoilerNow);
window.customCards = window.customCards || [];
if (!window.customCards.some(c => c.type === 'openthermostat-boiler-now'))
 window.customCards.push({type: 'openthermostat-boiler-now', name: 'OpenThermostat boiler now',
  description: 'What the boiler does now, its display code in words, the water to the heating and back, the burner power and its starts.'});
