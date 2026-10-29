/* Dashboard card: the visual week planner for the rooms of the E32 room plan.
   HA authenticates (admin websocket open_thermostat/e32_week/*); the E32 stores and runs the program.
   The planner itself is week-editor.js, the same file the E32 rooms page uses. */
const EDITOR = '/open_thermostat/week-editor-0.4.0b11.js';
const TEXT = {
 en: {title: 'Week program', loading: 'Loading…', intro: 'The E32 follows this program on its own, also when Home Assistant is offline.',
  follows: 'This room follows {entity} while Home Assistant gives a target temperature; the week program applies when it gives none.',
  save: 'Save to E32', saving: 'Saving…', discard: 'Discard changes', remove: 'Remove week program', reload: 'Reload', unsaved: 'Unsaved changes',
  saved: 'Saved on the E32.', removedNote: 'Without a week program the room keeps its fixed temperature of {value}.', rooms: 'Rooms',
  none: 'No rooms yet. Add one under Settings → Devices & services → OpenThermostat → Configure → E32 rooms.',
  errors: {plan_changed: 'The room plan was changed elsewhere. Reload to see the current program; your changes were not saved.',
   week_changed: 'This week program was changed elsewhere. Reload to see the current program; your changes were not saved.',
   plan_too_large: 'The plan is too large for the E32: use fewer switch times or rooms.', storage_full: 'The E32 storage is full. Remove switch times or a room, then save again.',
   save_unconfirmed: 'The E32 could not confirm the save. Reload and check the program.', room_missing: 'This room no longer exists on the E32. Reload.',
   password_changed: 'The E32 password changed. Reconnect the E32 in the integration settings.', unreachable: 'The E32 cannot be reached. Check the connection and try again.',
   invalid_schedule: 'At most 6 switch times per day, each at a different time.', invalid_schedule_limits: 'Every temperature must lie within the room minimum and maximum.',
   unavailable: 'The E32 room plan is not available for this installation.', unauthorized: 'Only Home Assistant administrators can change week programs.',
   rejected: 'The E32 refused the program. Reload and try again.', editor: 'The week planner could not be loaded. Reload the page.'}},
 nl: {title: 'Weekprogramma', loading: 'Laden…', intro: 'De E32 volgt dit programma zelf, ook als Home Assistant offline is.',
  follows: 'Deze ruimte volgt {entity} zolang Home Assistant een gewenste temperatuur geeft; het weekprogramma geldt als die er niet is.',
  save: 'Opslaan op E32', saving: 'Opslaan…', discard: 'Wijzigingen weggooien', remove: 'Weekprogramma verwijderen', reload: 'Opnieuw laden', unsaved: 'Niet opgeslagen wijzigingen',
  saved: 'Opgeslagen op de E32.', removedNote: 'Zonder weekprogramma houdt de ruimte de vaste temperatuur van {value} aan.', rooms: 'Ruimtes',
  none: 'Nog geen ruimtes. Voeg er een toe via Instellingen → Apparaten en diensten → OpenThermostat → Configureren → E32-ruimtes.',
  errors: {plan_changed: 'Het ruimteplan is elders gewijzigd. Laad opnieuw om het huidige programma te zien; je wijzigingen zijn niet opgeslagen.',
   week_changed: 'Dit weekprogramma is elders gewijzigd. Laad opnieuw om het huidige programma te zien; je wijzigingen zijn niet opgeslagen.',
   plan_too_large: 'Het plan is te groot voor de E32: gebruik minder schakeltijden of ruimtes.', storage_full: 'De opslag van de E32 is vol. Verwijder schakeltijden of een ruimte en sla opnieuw op.',
   save_unconfirmed: 'De E32 kon het opslaan niet bevestigen. Laad opnieuw en controleer het programma.', room_missing: 'Deze ruimte bestaat niet meer op de E32. Laad opnieuw.',
   password_changed: 'Het wachtwoord van de E32 is gewijzigd. Verbind de E32 opnieuw in de integratie-instellingen.', unreachable: 'De E32 is niet bereikbaar. Controleer de verbinding en probeer het opnieuw.',
   invalid_schedule: 'Maximaal 6 schakeltijden per dag, elk op een andere tijd.', invalid_schedule_limits: 'Elke temperatuur moet binnen het minimum en maximum van de ruimte liggen.',
   unavailable: 'Het ruimteplan van de E32 is niet beschikbaar voor deze installatie.', unauthorized: 'Alleen beheerders van Home Assistant kunnen weekprogramma’s wijzigen.',
   rejected: 'De E32 weigerde het programma. Laad opnieuw en probeer het nog eens.', editor: 'De weekplanner kon niet worden geladen. Laad de pagina opnieuw.'}}};
const STYLE = `:host{display:block}ha-card{display:block;padding:16px;max-width:1100px;margin:auto;color:var(--primary-text-color)}h2{margin:0 0 4px;font-size:1.3rem}
p{margin:0 0 12px;line-height:1.45}.muted{color:var(--secondary-text-color);font-size:.9rem}.tabs,.actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
button{font:inherit;font-weight:600;color:inherit;background:transparent;border:1px solid var(--divider-color,#ccd);border-radius:10px;min-height:44px;min-width:44px;padding:6px 14px;cursor:pointer}
button[aria-selected=true]{box-shadow:inset 0 0 0 2px var(--primary-text-color)}button.primary{background:var(--primary-color,#03a9f4);border-color:var(--primary-color,#03a9f4);color:var(--text-primary-color,#fff)}
button:disabled{opacity:.45;cursor:default}button:focus-visible{outline:3px solid var(--primary-color);outline-offset:2px}
.msg:empty{display:none}.msg{border-left:4px solid var(--primary-color);padding:8px 12px;background:var(--secondary-background-color);border-radius:6px}.msg.error{border-color:var(--error-color,#db4437)}
.dirty{color:var(--warning-color,#b26b00);font-weight:600}@media(max-width:480px){ha-card{padding:12px}}`;
const language = hass => /^nl\b/i.test(hass?.locale?.language || hass?.language || '') ? 'nl' : 'en';
const fill = (s, v) => s.replace(/\{(\w+)\}/g, (a, k) => k in v ? v[k] : a);
const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
const program = week => week && week.some(d => d.length) ? week : null;
// Home Assistant in imperial units: the planner shows and edits °F; the E32 program stays in °C.
const fahrenheit = hass => hass?.config?.unit_system?.temperature === '°F';
const degrees = (hass, centi) => (fahrenheit(hass) ? Math.round(centi * 9 / 50 + 320) / 10 : centi / 100)
 .toLocaleString(hass?.locale?.language || 'en') + (fahrenheit(hass) ? ' °F' : ' °C');
let editorReady = null;

class OpenThermostatE32Week extends HTMLElement {
 constructor() {
  super();
  this.attachShadow({mode: 'open'});
  this._rooms = null; this._room = null; this._drafts = {}; this._message = ''; this._error = false; this._busy = false;
 }
 setConfig(config) {
  if (!config || typeof config.entry_id !== 'string') throw new Error('entry_id is required');
  this._config = config;
 }
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
  const code = err?.code || err?.message || 'rejected';
  this._message = this.t.errors[code] || this.t.errors.rejected; this._error = true;
 }
 async load() {
  this._busy = true; this._message = ''; this.render();
  try {
   editorReady = editorReady || import(EDITOR).then(() => { if (!window.OTWeekEditor) throw {code: 'editor'}; }).catch(e => { editorReady = null; throw e?.code ? e : {code: 'editor'}; });
   const [result] = await Promise.all([this._hass.callWS({type: 'open_thermostat/e32_week/get', entry_id: this._config.entry_id}), editorReady]);
   this._rooms = result.rooms; this._drafts = {};
   if (!this._rooms.some(r => r.id === this._room)) this._room = this._rooms[0]?.id ?? null;
  } catch (err) { this._fail(err); }
  this._busy = false; this.render();
 }
 get room() { return this._rooms?.find(r => r.id === this._room); }
 get dirty() { const r = this.room; return !!r && this._room in this._drafts && !same(program(this._drafts[this._room]), r.schedule); }
 async save() {
  const r = this.room;
  if (!r || this._busy) return;
  this._busy = true; this._message = ''; this.refresh();
  try {
   const result = await this._hass.callWS({type: 'open_thermostat/e32_week/save', entry_id: this._config.entry_id, room_id: r.id,
    schedule: program(this._drafts[r.id]), expected: r.schedule});
   this._rooms = result.rooms; delete this._drafts[r.id];
   this._message = this.t.saved; this._error = false;
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
  const msg = el('p', null, {class: 'msg', role: 'status', 'aria-live': 'polite'});
  if (!this._rooms) {
   card.append(el('p', this._busy ? t.loading : '', {class: 'muted'}), msg);
   if (!this._busy) { const again = el('button', t.reload, {type: 'button'}); again.onclick = () => this.load(); card.append(again); }
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
  const week = this._room in this._drafts ? this._drafts[this._room] : r.schedule;
  this._planner = window.OTWeekEditor.mount(host, {week: week || Array.from({length: 7}, () => []), min: r.minimum_centi_c, max: r.maximum_centi_c,
   lang: language(this._hass), fahrenheit: fahrenheit(this._hass), theme: this._hass?.themes?.darkMode ? 'dark' : 'light',
   onChange: w => { this._drafts[r.id] = w; this._message = ''; this.refresh(); }});
  const actions = el('div', null, {class: 'actions'}), save = el('button', t.save, {type: 'button', class: 'primary', 'data-save': ''});
  const discard = el('button', t.discard, {type: 'button', 'data-discard': ''}), remove = el('button', t.remove, {type: 'button', 'data-remove': ''});
  const reload = el('button', t.reload, {type: 'button'});
  save.onclick = () => this.save();
  discard.onclick = () => { delete this._drafts[r.id]; this._message = ''; this.render(); };
  remove.onclick = () => { this._drafts[r.id] = Array.from({length: 7}, () => []); this._message = ''; this.render(); };
  reload.onclick = () => this.load();
  actions.append(save, discard, remove, reload, el('span', null, {class: 'dirty', role: 'status'}));
  card.append(actions, msg);
  this.refresh();
 }
}
if (!customElements.get('openthermostat-e32-week')) customElements.define('openthermostat-e32-week', OpenThermostatE32Week);
