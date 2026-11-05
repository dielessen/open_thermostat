/* Dashboard card: one E32 room at a glance (OpenThermostat 1.1; rc.5 in the form of the owner's sketch).
   Reads the room's Reason sensor (room_overview.py): a round disc in the colour of what the room does, the room's
   name with why it heats or not in one muted line, the temperature now large on the right, and under it chips:
   what the room does in one word (in the disc's colour), "Smart warm-up on" while the E32's Smart warm-up switch
   is on, the house (at home, away or on holiday: the house mode, else who is home) and the radiator valves. A tap
   opens the Reason sensor's history. The words are the integration's translations (strings.json
   entity.sensor.room_reason), so every viewer reads them in their own Home Assistant language; the card itself
   holds no text but English last resorts. Optional config: smart (the Smart warm-up switch) and mode (the house
   mode select); the OpenThermostat dashboard adds both when they exist.
   HA 1.0.0rc7 (the owner's sketch): after the sentence, the week program's step from the Reason sensor's
   ``program`` attribute (room_overview.program_step): "Comfort until 22:30, then Night 18.0 °C"; nothing while the
   attribute is absent or has no next step (the program does not set the room's target, or nothing changes). */
const KEY = 'component.open_thermostat.entity.sensor.room_reason.state_attributes.';
// The tone of each reason: the colour of the disc and of the word chip.
const TONE = {warm_up: 'heat', heating: 'heat', wants_heat: 'heat', boost: 'heat', away_return: 'heat', window_open: 'warn', window_pending: 'warn',
 no_measurement: 'error', hot_water: 'info', boiler_pause: 'info', temporary: 'info', holiday: 'away', away: 'away', room_away: 'away',
 house_away: 'away', warm_enough: 'ok', off: 'off'};
// The reason in one word (state_attributes.chip): the English last resort, key for key as strings.json.
const CHIP = {off: 'Off', window_open: 'Paused', window_pending: 'Pausing soon', no_measurement: 'No measurement', hot_water: 'Waiting',
 boiler_pause: 'Waiting', warm_up: 'Warming up', away_return: 'Warming up', holiday: 'Holiday', away: 'Away', room_away: 'Away',
 house_away: 'Away', boost: 'Boost', temporary: 'Temporary', heating: 'Heating', wants_heat: 'Wants heat', warm_enough: 'At temperature'};
// The card's other words (state_attributes.card): the same, for the chips beside the reason's word.
const WORDS = {smart_on: 'Smart warm-up on', home: 'At home', away: 'Away', holiday: 'Holiday'};
// The week program's step (state_attributes.program): the English last resort, key for key as strings.json.
const PROGRAM = {comfort: 'Comfort', eco: 'Eco', night: 'Night', holiday: 'Holiday', step: '{level} until {time}, then {next}'};
// Who is home for this room (room_overview.room_presence): the house chip's word while the house mode is automatic.
const PRESENCE = {room_home: 'home', room_away: 'away', house_home: 'home', house_away: 'away'};
const MODES = new Set(['home', 'away', 'holiday']);  // the house mode select's options that name the house itself
const FALLBACK = {temperature: 'Now', setpoint: 'Target', valve_position: 'Radiator valves open'};
const STYLE = `:host{display:block}ha-card{display:block;padding:14px 16px;color:var(--primary-text-color);cursor:pointer;
--heat:var(--state-climate-heat-color,#ff8100);--warn:var(--warning-color,#ffa600);--error:var(--error-color,#db4437);--ok:var(--success-color,#43a047);
--info:var(--info-color,#039be5);--away:var(--state-climate-cool-color,#2b9af9);--off:var(--disabled-text-color,#9e9e9e);
--neutral:var(--secondary-text-color,#727272);--surface:var(--ha-card-background,var(--card-background-color,#fff))}
ha-card:focus-visible{outline:3px solid var(--primary-color);outline-offset:2px}
p{margin:0}
.head{display:flex;align-items:center;gap:12px}
.disc{flex:none;display:flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:50%;
background:var(--secondary-background-color);background:color-mix(in srgb,var(--tone) 16%,var(--surface));color:var(--tone);--mdc-icon-size:22px}
.disc ha-icon{display:flex}
.text{flex:1 1 auto;min-width:0}
.name{font-size:16px;font-weight:500;line-height:1.3;overflow-wrap:anywhere}
.why,.missing{margin-top:2px;font-size:13px;line-height:1.35;color:var(--secondary-text-color);overflow-wrap:anywhere}
.now{flex:none;font-size:26px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums;white-space:nowrap}
.now small{font-size:14px;font-weight:400;color:var(--secondary-text-color);margin-left:1px}
.now.none{color:var(--secondary-text-color);font-weight:400}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.chip{display:inline-flex;align-items:center;gap:4px;border-radius:16px;padding:4px 10px;font-size:12px;font-weight:500;line-height:16px;
--tone:var(--neutral);background:var(--secondary-background-color);background:color-mix(in srgb,var(--tone) 14%,var(--surface));
color:var(--primary-text-color);color:color-mix(in srgb,var(--tone) 45%,var(--primary-text-color));--mdc-icon-size:16px}
.chip ha-icon{display:flex}
.chip.smart{--tone:var(--info)}.chip.problem{--tone:var(--warn)}
${Object.keys({heat: 0, warn: 0, error: 0, info: 0, away: 0, ok: 0, off: 0}).map(t => `.tone-${t} .disc,.tone-${t} .chip.state{--tone:var(--${t})}`).join('')}
@media(max-width:380px){ha-card{padding:12px}.now{font-size:24px}}`;

const locale = hass => hass?.locale?.language || hass?.language || 'en';
// A figure and its unit stay together on a narrow card ("21,2 °C" never breaks before the unit).
const together = text => text.replace(/ (°C|%)/g, ' $1');
// Now with one decimal (20.0); a target as set (21, 22.5).
const degrees = (hass, value, fixed) => typeof value === 'number' && Number.isFinite(value)
 ? value.toLocaleString(locale(hass), {minimumFractionDigits: fixed ? 1 : 0, maximumFractionDigits: 1}) : null;
/* clock: begin. One clock for the OpenThermostat cards (the same text in house-card.js and room-status-card.js, checked
   by test_room_overview.py): Home Assistant's time zone (the house's, where the E32 and its program live), the viewer's
   12/24-hour choice (a 12-hour clock without a leading zero: "5:00 PM"); a moment today as its time, the day before or
   after as "yesterday 14:05" / "tomorrow 14:30" in the viewer's language, further away with its date ("Sat 14 Nov,
   14:30"): a weekday alone is ambiguous after six days, and a holiday can end months ahead. */
const clockLocale = hass => hass?.locale?.language || hass?.language || 'en';
const clockZone = hass => {
 const zone = hass?.config?.time_zone;
 if (typeof zone !== 'string' || !zone) return undefined;
 try { new Intl.DateTimeFormat('en', {timeZone: zone}); return zone; } catch (e) { return undefined; }
};
const clockHour12 = hass => {
 const chosen = ({'12': true, '24': false})[hass?.locale?.time_format];
 if (chosen !== undefined) return chosen;
 try { return /h1[12]/.test(new Intl.DateTimeFormat(clockLocale(hass), {hour: 'numeric'}).resolvedOptions().hourCycle); } catch (e) { return false; }
};
const clockOptions = hass => {
 const hour12 = clockHour12(hass);
 return {hour: hour12 ? 'numeric' : '2-digit', minute: '2-digit', hour12, timeZone: clockZone(hass)};
};
// The time of day of ms ("14:30", "2:30 PM").
const clockTime = (hass, ms) => {
 try { return new Date(ms).toLocaleTimeString(clockLocale(hass), clockOptions(hass)); } catch (e) { return new Date(ms).toISOString().slice(11, 16); }
};
// The day number of ms in the house's zone (days since 1970), to compare calendar days.
const clockDay = (hass, ms) => {
 try {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', {timeZone: clockZone(hass), year: 'numeric', month: 'numeric', day: 'numeric'})
   .formatToParts(new Date(ms)).map(({type, value}) => [type, Number(value)]));
  return Math.round(Date.UTC(p.year, p.month - 1, p.day) / 86400000);
 } catch (e) { return Math.floor(ms / 86400000); }
};
// A moment (an ISO text or ms) for a sentence: "14:30", "tomorrow 14:30", "Sat 14 Nov, 14:30"; '' when not a time.
const clockMoment = (hass, value, now = Date.now()) => {
 const ms = typeof value === 'number' ? value : typeof value === 'string' ? Date.parse(value) : NaN;
 if (!Number.isFinite(ms)) return '';
 const days = clockDay(hass, ms) - clockDay(hass, now), time = clockTime(hass, ms);
 if (days === 0) return time;
 if (Math.abs(days) === 1) {
  try { return new Intl.RelativeTimeFormat(clockLocale(hass), {numeric: 'auto'}).format(days, 'day') + ' ' + time; } catch (e) { /* older browser */ }
 }
 try { return new Date(ms).toLocaleString(clockLocale(hass), {weekday: 'short', day: 'numeric', month: 'short', ...clockOptions(hass)}); }
 catch (e) { return new Date(ms).toISOString().slice(0, 16).replace('T', ' '); }
};
/* clock: end */
// A moment in a sentence (Back door open since 14:05; Holiday until Sat 14 Nov, 14:30): the shared clock.
const moment = (hass, iso) => clockMoment(hass, iso);

class OpenThermostatRoomStatus extends HTMLElement {
 constructor() { super(); this.attachShadow({mode: 'open'}); this._key = null; }
 setConfig(config) {
  if (!config || typeof config.entity !== 'string' || !config.entity.startsWith('sensor.'))
   throw new Error('This card needs the Reason sensor of an OpenThermostat room (entity: sensor.…); the OpenThermostat dashboard adds it for you.');
  this._config = config; this._key = null;
  if (this._hass) this.render();
 }
 set hass(hass) {
  this._hass = hass;
  // Only a new state of its own entities, language or theme redraws; Home Assistant sets hass on every change in the house.
  const config = this._config || {}, states = hass?.states || {};
  const key = [states[config.entity], states[config.smart], states[config.mode], locale(hass), hass?.themes?.darkMode,
   hass?.locale?.time_format];
  if (this._key && key.every((v, i) => v === this._key[i])) return;
  this._key = key; this.render();
 }
 getCardSize() { return 3; }
 getGridOptions() { return {columns: 12, min_columns: 6}; }
 _text(key, values) {
  try { const text = this._hass?.localize?.(KEY + key, values); return typeof text === 'string' ? text : ''; } catch (e) { return ''; }
 }
 // The sentence, with its values formatted for this viewer; else the state's own translation.
 sentence(st) {
  const a = st.attributes || {}, v = a.values && typeof a.values === 'object' ? a.values : {}, hass = this._hass;
  const values = {contact: typeof v.contact === 'string' ? v.contact : '', since: moment(hass, v.since), time: moment(hass, v.time), until: moment(hass, v.until),
   temperature: degrees(hass, v.temperature, true) ?? '–', target: degrees(hass, v.target) ?? '–'};
  const line = typeof a.line === 'string' ? this._text('line.state.' + a.line, values) : '';
  if (line) return together(line);
  try { return this._hass?.formatEntityState?.(st) || st.state; } catch (e) { return st.state; }
 }
 // The week program's step: "Comfort until 22:30, then Night 18.0 °C" (a level with its own temperature: "21.5 °C
 // until …"); '' without a next step. The time as the sentence's times (today plain, another day with its weekday).
 step(st) {
  const p = st.attributes?.program, hass = this._hass;
  if (!p || typeof p !== 'object' || typeof p.next_at !== 'string') return '';
  // The time kept on one line ("Sun 4:12 PM" never breaks before PM).
  const time = moment(hass, p.next_at).replace(/\s/g, ' '), now = degrees(hass, p.target, true), next = degrees(hass, p.next_target, true);
  if (!time || now === null || next === null) return '';
  const word = (key, values = {}) => {
   const text = this._text('program.state.' + key, values);
   return text || PROGRAM[key].replace(/\{(\w+)\}/g, (all, k) => k in values ? values[k] : all);
  };
  const level = key => ['comfort', 'eco', 'night', 'holiday'].includes(key) ? word(key) : '';
  const nowLevel = level(p.level), nextLevel = level(p.next_level);
  // A level by its name ("Comfort"), its next one with the temperature ("Night 18.0 °C"); a point without a level by its
  // temperature alone. The program's temperatures are the E32's, in °C.
  const deg = value => value + ' °C';
  return together(word('step', {level: nowLevel || deg(now), time, next: nextLevel ? nextLevel + ' ' + deg(next) : deg(next)}));
 }
 // The house in one word: the house mode when it names the house (at home, away, holiday), else who is home.
 house(st) {
  const mode = this._hass?.states?.[this._config.mode]?.state, presence = PRESENCE[st.attributes?.presence];
  const which = MODES.has(mode) ? mode : presence;
  return which ? (this._text('card.state.' + which) || WORDS[which]) : '';
 }
 render() {
  const hass = this._hass, config = this._config, root = this.shadowRoot;
  if (!hass || !config) return;
  const el = (tag, text, attrs = {}) => {
   const e = document.createElement(tag);
   if (text != null) e.textContent = text;
   for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
   return e;
  };
  const icon = (name, attrs = {}) => el('ha-icon', null, {icon: name, ...attrs});
  const card = el('ha-card', null, {tabindex: '0', role: 'button'}), st = hass.states?.[config.entity];
  const head = el('div', null, {class: 'head'}), disc = el('span', null, {class: 'disc', 'aria-hidden': 'true'}), text = el('div', null, {class: 'text'});
  disc.append(icon('mdi:home-outline'));
  if (config.name) text.append(el('p', config.name, {class: 'name'}));
  head.append(disc, text);
  root.replaceChildren(el('style', STYLE), card);
  card.append(head);
  if (!st) {
   card.classList.add('tone-off');
   const words = hass.localize?.('ui.panel.lovelace.warning.entity_not_found', {entity: config.entity}) || 'Entity not available: ' + config.entity;
   text.append(el('p', words, {class: 'missing'}));
   return;
  }
  card.onclick = () => this.dispatchEvent(new CustomEvent('hass-more-info', {bubbles: true, composed: true, detail: {entityId: config.entity}}));
  card.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.onclick(); } };
  const a = st.attributes || {}, known = TONE[st.state];
  card.classList.add('tone-' + (known || 'off'));
  if (!known) {  // unavailable or unknown: Home Assistant's own word for it
   text.append(el('p', (() => { try { return hass.formatEntityState?.(st) || st.state; } catch (e) { return st.state; } })(), {class: 'missing'}));
   return;
  }
  const label = key => this._text(key + '.name') || FALLBACK[key];
  // The sentence, then the week program's step after a middle dot (the sketch: "At temperature · Comfort until 22:30, …").
  const why = el('p', this.sentence(st), {class: 'why', 'data-reason': st.state}), step = this.step(st);
  if (step) why.append(el('span', ' · '), el('span', step, {class: 'step', 'data-step': ''}));
  text.append(why);
  // Now, large; for a screen reader with its label and the target ("Now 20.6 °C, Target 22.5 °C").
  const now = degrees(hass, a.temperature, true), target = st.state === 'off' ? null : degrees(hass, a.setpoint);
  const spoken = [now && `${label('temperature')} ${now} °C`, target && `${label('setpoint')} ${target} °C`].filter(Boolean).join(', ');
  const big = el('p', now ?? '–', {class: 'now' + (now ? '' : ' none'), 'data-now': '', ...(spoken ? {role: 'img', 'aria-label': spoken} : {})});
  if (now) big.append(el('small', '°'));
  head.append(big);
  // The chips: the reason in a word (an open window or door named in its tooltip), Smart warm-up, the house, the valves.
  const chips = el('div', null, {class: 'chips'}), word = this._text('chip.state.' + st.state) || CHIP[st.state];
  const chip = (kind, words, attrs = {}) => {
   const c = el('span', null, {class: 'chip ' + kind, 'data-chip': kind.split(' ')[0], ...attrs});
   c.append(el('span', words));
   chips.append(c);
   return c;
  };
  const opened = a.window === 'open' || a.window === 'pending'
   ? (typeof a.values?.contact === 'string' && a.values.contact ? a.values.contact + ': ' : '') + (this._text('window.state.' + a.window) || a.window) : '';
  chip('state', word, opened ? {title: opened, 'data-window': a.window} : {});
  if (st.state !== 'off' && config.smart && hass.states?.[config.smart]?.state === 'on') chip('smart', this._text('card.state.smart_on') || WORDS.smart_on);
  const house = this.house(st);
  if (house && house !== word) {  // never "Away" twice: an away room says it in its own word already
   const presence = PRESENCE[a.presence] ? this._text('presence.state.' + a.presence) || a.presence : '';
   chip('house', house, presence ? {title: presence, 'data-presence': a.presence} : {});
  }
  if (typeof a.valve_position === 'number' && Number.isFinite(a.valve_position)) {
   const valves = chip('valves' + (a.valve_problem ? ' problem' : ''), together(label('valve_position') + ': ' + Math.round(a.valve_position) + ' %'), {'data-valves': ''});
   valves.prepend(icon(a.valve_problem ? 'mdi:valve-closed' : 'mdi:valve'));
  }
  card.append(chips);
 }
}
// Other dashboard cards (HACS resources) may later replace window.customElements with a scoped-registry
// polyfill whose get() does not see elements defined before it; Home Assistant then reports "Custom element
// doesn't exist". So: define now, and again (a fresh subclass) whenever the registry in use lacks the element.
// Never throws. (The same guard as e32-week-card.js.)
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
ensureDefined('openthermostat-room-status', OpenThermostatRoomStatus);
window.customCards = window.customCards || [];
if (!window.customCards.some(c => c.type === 'openthermostat-room-status'))
 window.customCards.push({type: 'openthermostat-room-status', name: 'OpenThermostat room status', description: 'One E32 room: now, why it heats or not, and what it does in a word.'});
