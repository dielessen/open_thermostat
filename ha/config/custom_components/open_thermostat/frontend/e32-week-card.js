/* Dashboard card: the visual week planner for the rooms of the E32 room plan.
   HA authenticates (admin websocket open_thermostat/e32_week/*); the E32 stores and runs the program.
   The planner itself is week-editor.js, the same file the E32 rooms page uses. */
const EDITOR = '/open_thermostat/week-editor-0.4.0b13.js';
const TEXT = {
 en: {title: 'Week program', loading: 'Loading…', reading: 'Reading the week programs from the E32…', intro: 'The E32 follows this program on its own, also when Home Assistant is offline.',
  follows: 'This room follows {entity} while Home Assistant gives a target temperature; the week program applies when it gives none.',
  save: 'Save to E32', saving: 'Saving…', discard: 'Discard changes', remove: 'Remove week program', reload: 'Reload', unsaved: 'Unsaved changes',
  waiting: 'Waiting for the E32…', retrying: 'Trying again…',
  outdated: 'OpenThermostat was updated. Reload the page (Ctrl+F5) to use the new version of this card.',
  saved: 'Saved on the E32.', removedNote: 'Without a week program the room keeps its fixed temperature of {value}.', rooms: 'Rooms',
  none: 'No rooms yet. Add one under Settings → Devices & services → OpenThermostat → Configure → E32 rooms.',
  errors: {plan_changed: 'The room plan was changed elsewhere. Reload to see the current program; your changes were not saved.',
   week_changed: 'This week program was changed elsewhere. Reload to see the current program; your changes were not saved.',
   plan_too_large: 'The plan is too large for the E32: use fewer switch times or rooms.', storage_full: 'The E32 storage is full. Remove switch times or a room, then save again.',
   save_unconfirmed: 'The E32 could not confirm the save. Reload and check the program.', room_missing: 'This room no longer exists on the E32. Reload.',
   password_changed: 'The E32 password changed. Reconnect the E32 in the integration settings.', unreachable: 'The E32 cannot be reached. Check the connection and try again.',
   invalid_schedule: 'At most 6 switch times per day, each at a different time.', invalid_schedule_limits: 'Every temperature must lie within the room minimum and maximum.',
   unavailable: 'The E32 room plan is not available for this installation.', unauthorized: 'Only Home Assistant administrators can change week programs.',
   rejected: 'The E32 refused the program. Reload and try again.', editor: 'The week planner could not be loaded. Reload the page (Ctrl+F5) after updating OpenThermostat.',
   not_ready: 'OpenThermostat is still starting or the E32 is not connected yet. This card tries again by itself.',
   disabled: 'This OpenThermostat installation is turned off. Turn it on under Settings → Devices & services → OpenThermostat.',
   unknown_command: 'This page does not match the installed OpenThermostat. Reload the page (Ctrl+F5) after updating OpenThermostat; if that does not help, restart Home Assistant.',
   session_capacity: 'The E32 has too many open sign-ins (for example its own web page in other browsers). This card tries again shortly.',
   try_again_later: 'Too many sign-in attempts on the E32. This card tries again shortly.',
   setup_error: 'OpenThermostat could not start. Open Settings → Devices & services → OpenThermostat to see why, then reload this page.',
   gave_up: 'The E32 has not answered for several minutes. Check that it is on and connected, then press Reload.'}},
 nl: {title: 'Weekprogramma', loading: 'Laden…', reading: 'Weekprogramma’s lezen van de E32…', intro: 'De E32 volgt dit programma zelf, ook als Home Assistant offline is.',
  follows: 'Deze ruimte volgt {entity} zolang Home Assistant een gewenste temperatuur geeft; het weekprogramma geldt als die er niet is.',
  save: 'Opslaan op E32', saving: 'Opslaan…', discard: 'Wijzigingen weggooien', remove: 'Weekprogramma verwijderen', reload: 'Opnieuw laden', unsaved: 'Niet opgeslagen wijzigingen',
  waiting: 'Wachten op de E32…', retrying: 'Opnieuw proberen…',
  outdated: 'OpenThermostat is bijgewerkt. Laad de pagina opnieuw (Ctrl+F5) om de nieuwe versie van deze kaart te gebruiken.',
  saved: 'Opgeslagen op de E32.', removedNote: 'Zonder weekprogramma houdt de ruimte de vaste temperatuur van {value} aan.', rooms: 'Ruimtes',
  none: 'Nog geen ruimtes. Voeg er een toe via Instellingen → Apparaten en diensten → OpenThermostat → Configureren → E32-ruimtes.',
  errors: {plan_changed: 'Het ruimteplan is elders gewijzigd. Laad opnieuw om het huidige programma te zien; je wijzigingen zijn niet opgeslagen.',
   week_changed: 'Dit weekprogramma is elders gewijzigd. Laad opnieuw om het huidige programma te zien; je wijzigingen zijn niet opgeslagen.',
   plan_too_large: 'Het plan is te groot voor de E32: gebruik minder schakeltijden of ruimtes.', storage_full: 'De opslag van de E32 is vol. Verwijder schakeltijden of een ruimte en sla opnieuw op.',
   save_unconfirmed: 'De E32 kon het opslaan niet bevestigen. Laad opnieuw en controleer het programma.', room_missing: 'Deze ruimte bestaat niet meer op de E32. Laad opnieuw.',
   password_changed: 'Het wachtwoord van de E32 is gewijzigd. Verbind de E32 opnieuw in de integratie-instellingen.', unreachable: 'De E32 is niet bereikbaar. Controleer de verbinding en probeer het opnieuw.',
   invalid_schedule: 'Maximaal 6 schakeltijden per dag, elk op een andere tijd.', invalid_schedule_limits: 'Elke temperatuur moet binnen het minimum en maximum van de ruimte liggen.',
   unavailable: 'Het ruimteplan van de E32 is niet beschikbaar voor deze installatie.', unauthorized: 'Alleen beheerders van Home Assistant kunnen weekprogramma’s wijzigen.',
   rejected: 'De E32 weigerde het programma. Laad opnieuw en probeer het nog eens.', editor: 'De weekplanner kon niet worden geladen. Laad de pagina opnieuw (Ctrl+F5) na het bijwerken van OpenThermostat.',
   not_ready: 'OpenThermostat start nog of de E32 is nog niet verbonden. Deze kaart probeert het vanzelf opnieuw.',
   disabled: 'Deze OpenThermostat-installatie staat uit. Zet hem aan via Instellingen → Apparaten en diensten → OpenThermostat.',
   unknown_command: 'Deze pagina past niet bij de geïnstalleerde OpenThermostat. Laad de pagina opnieuw (Ctrl+F5) na het bijwerken van OpenThermostat; helpt dat niet, herstart dan Home Assistant.',
   session_capacity: 'De E32 heeft te veel open aanmeldingen (bijvoorbeeld zijn eigen webpagina in andere browsers). Deze kaart probeert het zo opnieuw.',
   try_again_later: 'Te veel aanmeldpogingen op de E32. Deze kaart probeert het zo opnieuw.',
   setup_error: 'OpenThermostat kon niet starten. Open Instellingen → Apparaten en diensten → OpenThermostat om te zien waarom en laad daarna deze pagina opnieuw.',
   gave_up: 'De E32 antwoordt al enkele minuten niet. Controleer of hij aan staat en verbonden is en kies dan Opnieuw laden.'}}};
const STYLE = `:host{display:block}ha-card{display:block;padding:16px;max-width:1100px;margin:auto;color:var(--primary-text-color)}h2{margin:0 0 4px;font-size:1.3rem}
p{margin:0 0 12px;line-height:1.45}.muted{color:var(--secondary-text-color);font-size:.9rem}.tabs,.actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.actions{position:sticky;bottom:0;z-index:3;align-items:center;padding:8px 0;background:var(--card-background-color,var(--ha-card-background,#fff))}
button{font:inherit;font-weight:600;color:inherit;background:transparent;border:1px solid var(--divider-color,#ccd);border-radius:10px;min-height:44px;min-width:44px;padding:6px 14px;cursor:pointer}
button[aria-selected=true]{box-shadow:inset 0 0 0 2px var(--primary-text-color)}button.primary{background:var(--primary-color,#03a9f4);border-color:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}
button:disabled{opacity:.45;cursor:default}button:focus-visible{outline:3px solid var(--primary-color);outline-offset:2px}
.msg:empty{display:none}.msg{border-left:4px solid var(--primary-color);padding:8px 12px;background:var(--secondary-background-color);border-radius:6px}.msg.error{border-color:var(--error-color,#db4437)}
.dirty{color:var(--warning-color,#b26b00);font-weight:600}.waiting{font-weight:600;margin:4px 0 8px}.notice{border-left:4px solid var(--warning-color,#b26b00);padding:8px 12px;background:var(--secondary-background-color);border-radius:6px;margin:0 0 12px}@media(max-width:480px){ha-card{padding:12px}}`;
const language = hass => /^nl\b/i.test(hass?.locale?.language || hass?.language || '') ? 'nl' : 'en';
const fill = (s, v) => s.replace(/\{(\w+)\}/g, (a, k) => k in v ? v[k] : a);
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const program = week => week && week.some(d => d.length) ? week : null;
// Home Assistant in imperial units: the planner shows and edits °F; the E32 program stays in °C.
const fahrenheit = hass => hass?.config?.unit_system?.temperature === '°F';
const degrees = (hass, centi) => (fahrenheit(hass) ? Math.round(centi * 9 / 50 + 320) / 10 : centi / 100)
 .toLocaleString(hass?.locale?.language || 'en') + (fahrenheit(hass) ? ' °F' : ' °C');
let editorReady = null;
// Codes after which the card tries again by itself (HA still starting, E32 not reachable yet).
const RETRY = new Set(['not_ready', 'unreachable', 'session_capacity', 'try_again_later']), RETRY_MS = 15000;
// After this long without an answer the card stops trying by itself and says so (Reload tries again).
const GIVE_UP_MS = 5 * 60000;
// This module's own path: compared with the module the backend serves (a page left open over an update).
const SELF = (() => { try { return new URL(import.meta.url).pathname; } catch (e) { return ''; } })();

class OpenThermostatE32Week extends HTMLElement {
 constructor() {
  super();
  this.attachShadow({mode: 'open'});
  // _drafts: per room the edited program; _levels: per room the planner's state (levels and marks).
  this._rooms = null; this._room = null; this._drafts = {}; this._levels = {}; this._base = {}; this._message = ''; this._error = false; this._busy = false;
  this._waiting = false; this._outdated = false; this._retry = null; this._waitSince = null;
 }
 setConfig(config) {
  if (!config || typeof config.entry_id !== 'string' || !config.entry_id)
   throw new Error('This card needs the entry_id of an OpenThermostat installation; the OpenThermostat dashboard adds it for you.');
  const changed = !!this._config && this._config.entry_id !== config.entry_id;
  this._config = config;
  if (changed && this._hass) { this._rooms = null; this._drafts = {}; this.load(); }
 }
 connectedCallback() { if (this._hass && this._waiting && !this._retry && !this._busy) this.load(); }
 disconnectedCallback() { clearTimeout(this._retry); this._retry = null; }
 getCardSize() { return 12; }
 set hass(hass) {
  const first = !this._hass;
  this._hass = hass;
  if (first) this.load();
  else if (this._planner) this._theme();
 }
 get t() { return TEXT[language(this._hass)]; }
 _theme() { const box = this.shadowRoot.querySelector('.wpe'); if (box) box.dataset.theme = this._hass?.themes?.darkMode ? 'dark' : 'light'; }
 _fail(err) {
  const code = typeof err?.code === 'string' && err.code ? err.code : 'rejected';
  this._message = this.t.errors[code] || this.t.errors.rejected; this._error = true;
  return code;
 }
 // fresh: read from the E32 itself (Reload); otherwise Home Assistant answers from the plan it already
 // holds while that plan is current, so opening the page costs the E32 no sign-in.
 async load(fresh = false) {
  clearTimeout(this._retry); this._retry = null;
  if (!this._hass || !this._config) return;
  this._busy = true; this._fresh = fresh; this._message = ''; this.render();
  try {
   editorReady = editorReady || import(EDITOR).then(() => { if (!window.OTWeekEditor) throw {code: 'editor'}; }).catch(e => { editorReady = null; throw e?.code ? e : {code: 'editor'}; });
   const request = {type: 'open_thermostat/e32_week/get', entry_id: this._config.entry_id, ...(fresh ? {fresh: true} : {})};
   const [result] = await Promise.all([this._hass.callWS(request), editorReady]);
   if (!result || !Array.isArray(result.rooms)) throw {code: 'unknown_command'};
   this._rooms = result.rooms; this._drafts = {}; this._levels = {}; this._base = {}; this._waiting = false; this._waitSince = null;
   this._levelsSupported = result.levels_supported === true;
   this._outdated = typeof result.card_url === 'string' && !!SELF && result.card_url !== SELF;
   if (!this._rooms.some(r => r.id === this._room)) this._room = this._rooms[0]?.id ?? null;
  } catch (err) {
   // Still starting or not reachable: say so and try again by itself (never a dead end).
   const code = this._fail(err);
   this._waiting = RETRY.has(code) && !this._rooms;
   if (RETRY.has(code)) {
    this._waitSince = this._waitSince ?? Date.now();
    if (Date.now() - this._waitSince >= GIVE_UP_MS) { this._waiting = false; this._message = this.t.errors.gave_up; }
    else if (this.isConnected) this._retry = setTimeout(() => this.load(fresh), RETRY_MS);
   } else this._waitSince = null;
  }
  this._busy = false; this.render();
 }
 get room() { return this._rooms?.find(r => r.id === this._room); }
 // Changed: another program, or (E32 with stored levels) other levels or marks, also without a program change.
 get dirty() {
  const r = this.room, st = r && this._levels[r.id];
  if (!r) return false;
  if (this._room in this._drafts && !same(program(this._drafts[this._room]), r.schedule)) return true;
  const base = this._base[r.id];
  return !!st && !!base && this._levelsSupported && (!same(st.levels, base.levels) || st.schedule_levels !== base.schedule_levels);
 }
 async save() {
  const r = this.room;
  if (!r || this._busy) return;
  this._busy = true; this._message = ''; this.refresh();
  try {
   const st = this._levels[r.id], schedule = program(r.id in this._drafts ? this._drafts[r.id] : r.schedule);
   const result = await this._hass.callWS({type: 'open_thermostat/e32_week/save', entry_id: this._config.entry_id, room_id: r.id,
    schedule, expected: r.schedule, ...(this._levelsSupported && st ? {levels: st.levels, schedule_levels: st.schedule_levels} : {})});
   this._rooms = result.rooms; delete this._drafts[r.id]; delete this._levels[r.id]; delete this._base[r.id];
   this._message = this.t.saved + ' ✓ ' + new Date().toLocaleTimeString(this._hass?.locale?.language || 'en', {hour: '2-digit', minute: '2-digit'}); this._error = false;
   if (!program(this.room?.schedule)) this._message += ' ' + fill(this.t.removedNote, {value: degrees(this._hass, r.fallback_centi_c)});
   this._busy = false; this.render();
  } catch (err) { this._fail(err); this._busy = false; this.refresh(); }
 }
 // Buttons and messages only, so the planner keeps its focus and selection while editing.
 refresh() {
  const root = this.shadowRoot, t = this.t, dirty = this.dirty, r = this.room;
  const msg = root.querySelector('.msg');
  if (msg) { msg.textContent = this._message; msg.className = 'msg' + (this._error ? ' error' : ''); }
  const state = root.querySelector('.dirty');
  if (state) state.textContent = dirty ? t.unsaved : '';
  const save = root.querySelector('[data-save]');
  if (save) { save.disabled = !dirty || this._busy; save.textContent = this._busy ? t.saving : t.save; }
  const discard = root.querySelector('[data-discard]');
  if (discard) discard.disabled = !dirty || this._busy;
  const remove = root.querySelector('[data-remove]');
  if (remove && r) remove.disabled = this._busy || !program(this._room in this._drafts ? this._drafts[this._room] : r.schedule);
 }
 render() {
  const t = this.t, root = this.shadowRoot, card = document.createElement('ha-card'), el = (tag, text, attrs = {}) => {
   const e = document.createElement(tag);
   if (text != null) e.textContent = text;
   for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
   return e;
  };
  root.replaceChildren(el('style', STYLE), card);
  card.append(el('h2', t.title));
  if (this._outdated) card.append(el('p', t.outdated, {class: 'notice', role: 'status'}));
  const msg = el('p', null, {class: 'msg', role: 'status', 'aria-live': 'polite'});
  if (!this._rooms) {
   const status = this._waiting ? (this._busy ? t.retrying : t.waiting) : this._busy ? (this._fresh ? t.reading : t.loading) : '';
   card.append(el('p', status, {class: this._waiting ? 'waiting' : 'muted'}), msg);
   if (!this._busy) { const again = el('button', t.reload, {type: 'button'}); again.onclick = () => { this._waitSince = null; this.load(true); }; card.append(again); }
   return this.refresh();
  }
  if (!this._rooms.length) { card.append(el('p', t.none, {class: 'muted'})); return; }
  card.append(el('p', t.intro, {class: 'muted'}));
  if (this._rooms.length > 1) {
   const tabs = el('div', null, {class: 'tabs', role: 'tablist', 'aria-label': t.rooms});
   for (const r of this._rooms) {
    const tab = el('button', r.name, {type: 'button', role: 'tab', 'aria-selected': String(r.id === this._room)});
    tab.onclick = () => { this._room = r.id; this._message = ''; this.render(); };
    tabs.append(tab);
   }
   card.append(tabs);
  }
  const r = this.room;
  if (r.setpoint_entity) card.append(el('p', fill(t.follows, {entity: r.setpoint_entity}), {class: 'muted'}));
  const host = el('div');
  card.append(host);
  const week = this._room in this._drafts ? this._drafts[this._room] : r.schedule, st = this._levels[r.id];
  // The room's stored levels (or, before its first program, the former house settings); none: inferred.
  this._planner = window.OTWeekEditor.mount(host, {week: week || Array.from({length: 7}, () => []), min: r.minimum_centi_c, max: r.maximum_centi_c,
   lang: language(this._hass), fahrenheit: fahrenheit(this._hass), theme: this._hass?.themes?.darkMode ? 'dark' : 'light',
   levels: st ? st.levels : r.levels, scheduleLevels: st ? st.schedule_levels : r.schedule_levels,
   onChange: (w, state) => { this._drafts[r.id] = w; if (state) this._levels[r.id] = state; this._message = ''; this.refresh(); },
   onLevels: () => { this._levels[r.id] = this._planner.state(); this._message = ''; this.refresh(); }});
  // What the planner showed at load: levels and marks are compared with this, not with the stored fields.
  if (!(r.id in this._base)) this._base[r.id] = this._planner.state();
  const actions = el('div', null, {class: 'actions'}), save = el('button', t.save, {type: 'button', class: 'primary', 'data-save': ''});
  const discard = el('button', t.discard, {type: 'button', 'data-discard': ''}), remove = el('button', t.remove, {type: 'button', 'data-remove': ''});
  const reload = el('button', t.reload, {type: 'button'});
  save.onclick = () => this.save();
  discard.onclick = () => { delete this._drafts[r.id]; delete this._levels[r.id]; delete this._base[r.id]; this._message = ''; this.render(); };
  remove.onclick = () => { this._drafts[r.id] = Array.from({length: 7}, () => []); this._message = ''; this.render(); };
  reload.onclick = () => { this._waitSince = null; this.load(true); };
  actions.append(save, discard, remove, reload, el('span', null, {class: 'dirty', role: 'status'}));
  card.append(actions, msg);
  this.refresh();
 }
}
// Other dashboard cards (HACS resources) may later replace window.customElements with a scoped-registry
// polyfill whose get() does not see elements defined before it; Home Assistant then reports "Custom element
// doesn't exist". So: define now, and again (a fresh subclass) whenever the registry in use lacks the element.
// Never throws.
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
 return check;
};
ensureDefined('openthermostat-e32-week', OpenThermostatE32Week);
