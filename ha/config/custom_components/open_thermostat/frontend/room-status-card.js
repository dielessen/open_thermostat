/* Dashboard card: one E32 room at a glance (OpenThermostat 1.1).
   Reads the room's Reason sensor (room_overview.py): now against target, why the room heats or not
   in one sentence, who is home, an open window or door and the radiator valves. The words are the
   integration's translations (strings.json entity.sensor.room_reason), so every viewer reads them in
   their own Home Assistant language; the card itself holds no text but English last resorts. */
const KEY = 'component.open_thermostat.entity.sensor.room_reason.state_attributes.';
// The tone of each reason: the colour of the sentence's bar and icon.
const TONE = {warm_up: 'heat', heating: 'heat', wants_heat: 'heat', boost: 'heat', away_return: 'heat', window_open: 'warn', window_pending: 'warn',
 no_measurement: 'error', hot_water: 'info', boiler_pause: 'info', temporary: 'info', holiday: 'away', away: 'away', room_away: 'away',
 house_away: 'away', warm_enough: 'ok', off: 'off'};
const ICON = {warm_up: 'mdi:clock-fast', heating: 'mdi:fire', wants_heat: 'mdi:fire', boost: 'mdi:rocket-launch-outline', away_return: 'mdi:home-import-outline',
 window_open: 'mdi:window-open-variant', window_pending: 'mdi:window-open-variant', no_measurement: 'mdi:thermometer-off',
 hot_water: 'mdi:water-boiler', boiler_pause: 'mdi:timer-sand', temporary: 'mdi:clock-outline', holiday: 'mdi:palm-tree',
 away: 'mdi:home-export-outline', room_away: 'mdi:account-off-outline', house_away: 'mdi:home-export-outline',
 warm_enough: 'mdi:check-circle-outline', off: 'mdi:snowflake'};
const PRESENCE = {room_home: 'mdi:account-check', room_away: 'mdi:account-off-outline', house_home: 'mdi:home-account', house_away: 'mdi:home-export-outline'};
const FALLBACK = {temperature: 'Now', setpoint: 'Target', valve_position: 'Radiator valves open'};
const STYLE = `:host{display:block}ha-card{display:block;padding:14px 16px;color:var(--primary-text-color);cursor:pointer;
--heat:var(--state-climate-heat-color,#ff8100);--warn:var(--warning-color,#ffa600);--error:var(--error-color,#db4437);--ok:var(--success-color,#43a047);
--info:var(--info-color,#039be5);--away:var(--state-climate-cool-color,#2b9af9);--off:var(--disabled-text-color,#9e9e9e)}
ha-card:focus-visible{outline:3px solid var(--primary-color);outline-offset:2px}
.name{margin:0 0 8px;font-size:1.05rem;font-weight:600;overflow-wrap:anywhere}
.top{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;flex-wrap:wrap}
.temps{display:flex;align-items:flex-end;gap:10px;min-width:0;font-variant-numeric:tabular-nums}
.temp{display:flex;flex-direction:column}.label{font-size:.78rem;color:var(--secondary-text-color);font-weight:500}
.value{font-size:1.9rem;font-weight:600;line-height:1.15}.value small{font-size:.5em;font-weight:500;margin-left:2px;color:var(--secondary-text-color)}
.target .value{font-size:1.35rem;color:var(--secondary-text-color)}.arrow{font-size:1.2rem;color:var(--secondary-text-color);padding-bottom:4px}
.icons{display:flex;gap:6px}.icon{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;
background:var(--secondary-background-color);color:var(--secondary-text-color);--mdc-icon-size:20px}
.icon.on{color:var(--ok);background:color-mix(in srgb,var(--ok) 16%,transparent)}.icon.warn{color:var(--warn);background:color-mix(in srgb,var(--warn) 18%,transparent)}
.why{display:flex;align-items:center;gap:8px;margin:12px 0 0;padding:8px 12px;border-radius:10px;border-left:4px solid var(--tone);font-weight:600;line-height:1.35;
background:var(--secondary-background-color);background:color-mix(in srgb,var(--tone) 13%,transparent);overflow-wrap:anywhere}
.why ha-icon{color:var(--tone);--mdc-icon-size:20px;flex:none}
.valves{display:flex;align-items:center;gap:6px;margin:8px 0 0;font-size:.9rem;color:var(--secondary-text-color);--mdc-icon-size:18px}
.missing{color:var(--secondary-text-color);margin:0}
${Object.keys({heat: 0, warn: 0, error: 0, info: 0, away: 0, ok: 0, off: 0}).map(t => `.tone-${t}{--tone:var(--${t})}`).join('')}
@media(max-width:380px){ha-card{padding:12px}.value{font-size:1.6rem}.target .value{font-size:1.2rem}}`;

const locale = hass => hass?.locale?.language || hass?.language || 'en';
const zone = hass => hass?.locale?.time_zone === 'server' ? hass?.config?.time_zone : undefined;
// The viewer's 12/24-hour choice in Home Assistant (profile → time format); else the language's.
const hour12 = hass => ({'12': true, '24': false})[hass?.locale?.time_format];
// Now with one decimal (20.0); a target as set (21, 22.5).
const degrees = (hass, value, fixed) => typeof value === 'number' && Number.isFinite(value)
 ? value.toLocaleString(locale(hass), {minimumFractionDigits: fixed ? 1 : 0, maximumFractionDigits: 1}) : null;
// A moment as the clock time today, else with the weekday (Back door open since Tue 14:05).
const moment = (hass, iso) => {
 const at = typeof iso === 'string' ? new Date(iso) : null;
 if (!at || !Number.isFinite(at.getTime())) return '';
 const timeZone = zone(hass), day = d => d.toLocaleDateString('en-CA', {timeZone});
 const options = {hour: '2-digit', minute: '2-digit', timeZone, hour12: hour12(hass), ...(day(at) === day(new Date()) ? {} : {weekday: 'short'})};
 try { return at.toLocaleString(locale(hass), options); } catch (e) { return at.toISOString().slice(11, 16); }
};

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
  // Only a new state, language or theme redraws; Home Assistant sets hass on every change in the house.
  const st = hass?.states?.[this._config?.entity], key = [st, locale(hass), hass?.themes?.darkMode];
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
  if (line) return line;
  try { return this._hass?.formatEntityState?.(st) || st.state; } catch (e) { return st.state; }
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
  root.replaceChildren(el('style', STYLE), card);
  if (config.name) card.append(el('p', config.name, {class: 'name'}));
  if (!st) {
   const text = hass.localize?.('ui.panel.lovelace.warning.entity_not_found', {entity: config.entity}) || 'Entity not available: ' + config.entity;
   card.append(el('p', text, {class: 'missing'}));
   return;
  }
  card.onclick = () => this.dispatchEvent(new CustomEvent('hass-more-info', {bubbles: true, composed: true, detail: {entityId: config.entity}}));
  card.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); card.onclick(); } };
  const a = st.attributes || {}, known = TONE[st.state];
  card.classList.add('tone-' + (known || 'off'));
  if (!known) {  // unavailable or unknown: Home Assistant's own word for it
   card.append(el('p', (() => { try { return hass.formatEntityState?.(st) || st.state; } catch (e) { return st.state; } })(), {class: 'missing'}));
   return;
  }
  const label = key => this._text(key + '.name') || FALLBACK[key];
  const temperature = (cls, key, value, fixed) => {
   const box = el('span', null, {class: 'temp ' + cls}), text = degrees(hass, value, fixed);
   const out = el('span', text ?? '–', {class: 'value'});
   if (text) out.append(el('small', '°C'));
   box.append(el('span', label(key), {class: 'label'}), out);
   return box;
  };
  const top = el('div', null, {class: 'top'}), temps = el('div', null, {class: 'temps'}), icons = el('div', null, {class: 'icons'});
  temps.append(temperature('now', 'temperature', a.temperature, true));
  if (st.state !== 'off') temps.append(el('span', '→', {class: 'arrow', 'aria-hidden': 'true'}), temperature('target', 'setpoint', a.setpoint));
  if (PRESENCE[a.presence]) {
   const text = this._text('presence.state.' + a.presence) || a.presence, home = a.presence.endsWith('_home');
   icons.append(el('span', null, {class: 'icon presence' + (home ? ' on' : ''), role: 'img', 'aria-label': text, title: text, 'data-presence': a.presence}));
   icons.lastChild.append(icon(PRESENCE[a.presence]));
  }
  if (a.window === 'open' || a.window === 'pending') {
   const contact = typeof a.values?.contact === 'string' && a.values.contact ? a.values.contact + ': ' : '';
   const text = contact + (this._text('window.state.' + a.window) || a.window);
   icons.append(el('span', null, {class: 'icon window warn', role: 'img', 'aria-label': text, title: text, 'data-window': a.window}));
   icons.lastChild.append(icon('mdi:window-open-variant'));
  }
  top.append(temps, icons);
  const why = el('p', null, {class: 'why', 'data-reason': st.state});
  why.append(icon(ICON[st.state]), el('span', this.sentence(st)));
  card.append(top, why);
  if (typeof a.valve_position === 'number' && Number.isFinite(a.valve_position)) {
   const valves = el('p', null, {class: 'valves', 'data-valves': ''});
   valves.append(icon(a.valve_problem ? 'mdi:valve-closed' : 'mdi:valve'), el('span', label('valve_position') + ': ' + Math.round(a.valve_position) + ' %'));
   card.append(valves);
  }
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
 window.customCards.push({type: 'openthermostat-room-status', name: 'OpenThermostat room status', description: 'One E32 room: now against target and why it heats or not.'});
