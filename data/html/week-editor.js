/* OpenThermostat week planner: one dependency-free editor shared by the E32 rooms page and Home Assistant
   (identical copy: ha/.../frontend/week-editor.js). A week is 7 days, Monday first, of [minute, centi °C]
   switch points exactly as the E32 room plan stores it: a point holds until the next one, also across
   midnight and empty days. Named levels are only a way to edit; the program keeps plain temperatures. */
(() => {
'use strict';
if (window.OTWeekEditor) return;
const MAX = 6, STEP = 15, LEVELS = ['comfort', 'night', 'away'];
const T = {
 en: {days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], short: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  text: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'], names: {comfort: 'Comfort', night: 'Night', away: 'Away'}, levels: 'Temperature levels',
  warmer: '{level} warmer', cooler: '{level} cooler', custom: 'Own temperature', template: 'Start from a template', choose: 'Choose…',
  templates: {work: 'Workdays and weekend', home: 'Working from home', daily: 'Same every day'}, undo: 'Undo',
  applied: '{name} applied. Undo brings back the previous program.', hint: 'Tap a block to change it, drag a dividing line to change a time, tap a day to copy it.',
  empty: 'No program yet: choose a template to start.', copyDay: 'Copy {day}', copyTo: 'Copy {day} to', workdays: 'Workdays', weekend: 'Weekend', all: 'All days',
  copy: 'Copy', cancel: 'Cancel', pickDay: 'Choose at least one day.', copied: '{day} copied.', block: '{day} {from}–{to}', inherited: 'continues from the day before',
  level: 'Level', starts: 'Starts at', earlier: '15 minutes earlier', later: '15 minutes later', split: 'Split block', remove: 'Remove switch time',
  prev: 'Previous block', next: 'Next block', close: 'Done', full: 'At most 6 switch times per day.', short15: 'This block is too short to split.',
  differ: 'Each level needs its own temperature.', limits: 'Keep temperatures between {min} and {max}.', preview: 'Week preview',
  advanced: 'Advanced: edit as text', textHelp: 'One line per group of days, for example: mon-fri: 06:30 20.5; 22:30 18', apply: 'Apply text',
  bad: 'Line {line} cannot be read: {text}', outside: 'Line {line}: temperatures must lie between {min} and {max}.', many: 'Line {line}: at most 6 switch times per day.',
  textApplied: 'Text applied.', inF: 'Temperatures in °F.'},
 nl: {days: ['Maandag', 'Dinsdag', 'Woensdag', 'Donderdag', 'Vrijdag', 'Zaterdag', 'Zondag'], short: ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo'],
  text: ['ma', 'di', 'wo', 'do', 'vr', 'za', 'zo'], names: {comfort: 'Comfort', night: 'Nacht', away: 'Afwezig'}, levels: 'Temperatuurniveaus',
  warmer: '{level} warmer', cooler: '{level} kouder', custom: 'Eigen temperatuur', template: 'Begin met een sjabloon', choose: 'Kies…',
  templates: {work: 'Werkdagen en weekend', home: 'Thuiswerken', daily: 'Elke dag hetzelfde'}, undo: 'Ongedaan maken',
  applied: '{name} toegepast. Ongedaan maken zet het vorige programma terug.', hint: 'Tik op een blok om het te wijzigen, sleep een scheidingslijn om een tijd te verschuiven, tik op een dag om hem te kopiëren.',
  empty: 'Nog geen programma: kies een sjabloon om te beginnen.', copyDay: '{day} kopiëren', copyTo: '{day} kopiëren naar', workdays: 'Werkdagen', weekend: 'Weekend', all: 'Alle dagen',
  copy: 'Kopiëren', cancel: 'Annuleren', pickDay: 'Kies minstens één dag.', copied: '{day} gekopieerd.', block: '{day} {from}–{to}', inherited: 'loopt door van de dag ervoor',
  level: 'Niveau', starts: 'Begint om', earlier: '15 minuten eerder', later: '15 minuten later', split: 'Blok splitsen', remove: 'Schakeltijd verwijderen',
  prev: 'Vorig blok', next: 'Volgend blok', close: 'Klaar', full: 'Maximaal 6 schakeltijden per dag.', short15: 'Dit blok is te kort om te splitsen.',
  differ: 'Elk niveau heeft een eigen temperatuur nodig.', limits: 'Houd temperaturen tussen {min} en {max}.', preview: 'Voorbeeld van de week',
  advanced: 'Geavanceerd: als tekst bewerken', textHelp: 'Eén regel per groep dagen, bijvoorbeeld: ma-vr: 06:30 20,5; 22:30 18', apply: 'Tekst toepassen',
  bad: 'Regel {line} is niet te lezen: {text}', outside: 'Regel {line}: temperaturen moeten tussen {min} en {max} liggen.', many: 'Regel {line}: maximaal 6 schakeltijden per dag.',
  textApplied: 'Tekst toegepast.', inF: 'Temperaturen in °F.'}};
// Templates in level names; the owner's level temperatures fill them in.
const WORK = [[390, 'comfort'], [510, 'away'], [1020, 'comfort'], [1350, 'night']], HOME = [[420, 'comfort'], [1350, 'night']], FREE = [[480, 'comfort'], [1380, 'night']];
const TEMPLATES = {work: [WORK, WORK, WORK, WORK, WORK, FREE, FREE], home: [HOME, HOME, HOME, HOME, HOME, FREE, FREE], daily: Array(7).fill(HOME)};
const DAY_NAMES = {};
[T.en.text, T.nl.text, T.en.days.map(d => d.toLowerCase()), T.nl.days.map(d => d.toLowerCase())].forEach(n => n.forEach((d, i) => { DAY_NAMES[d] = i; }));
const clone = w => w.map(d => d.map(p => [p[0], p[1]]));
const fill = (s, v) => s.replace(/\{(\w+)\}/g, (a, k) => k in v ? v[k] : a);
const clock = m => String(m / 60 | 0).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
// °F only at the edge (Home Assistant in imperial units): shown with one decimal like the options flow
// (e32_room_flow.shown), read back to 0.01 °C so a whole °F shows again as typed; the program stays in centi °C.
const shown = (c, f) => f ? Math.round(c * 9 / 50 + 320) / 10 : c / 100;
const centi = (v, f) => f ? Math.round((v - 32) * 500 / 9) : Math.round(v * 100);
const deg = (c, lang, f) => { const s = String(shown(c, f)); return lang === 'nl' ? s.replace('.', ',') : s; };
const valid = w => Array.isArray(w) && w.length === 7 && w.every(d => Array.isArray(d) && d.length <= MAX && d.every((p, i) => Array.isArray(p)
 && Number.isInteger(p[0]) && Number.isInteger(p[1]) && p[0] >= 0 && p[0] < 1440 && (!i || p[0] > d[i - 1][0])));
const tr = lang => T[lang === 'nl' ? 'nl' : 'en'];

// The existing program text ("mon-fri: 06:30 20.5; 22:30 18"), as the Home Assistant options flow reads and writes it.
function format(week, lang, f) {
 const t = tr(lang), groups = new Map();
 week.forEach((points, d) => { if (points.length) { const key = points.map(([m, c]) => clock(m) + ' ' + deg(c, lang, f)).join('; '); groups.set(key, [...(groups.get(key) || []), d]); } });
 return [...groups].map(([key, days]) => {
  if (days.length === 7) return key;
  const runs = [];
  for (const d of days) { const r = runs[runs.length - 1]; if (r && r[1] === d - 1) r[1] = d; else runs.push([d, d]); }
  return runs.map(([a, b]) => a === b ? t.text[a] : t.text[a] + '-' + t.text[b]).join(',') + ': ' + key;
 }).join('\n');
}
function parse(text, min, max, f) {
 const week = Array(7).fill(null);
 (text || '').split(/\r?\n/).forEach((original, n) => {
  const fail = key => { throw {key, line: n + 1, text: original.trim().slice(0, 60)}; };
  const line = original.toLowerCase().replace(/–/g, '-').trim();
  if (!line) return;
  const prefix = line.match(/^([a-z][a-z ,-]*?)\s*:\s*(.*)$/);
  let days = [0, 1, 2, 3, 4, 5, 6];
  if (prefix) {
   days = [];
   for (const token of prefix[1].split(',').map(s => s.trim())) {
    const ends = token.split('-').map(s => s.trim());
    if (ends.length > 2 || ends.some(e => !(e in DAY_NAMES))) fail('bad');
    const a = DAY_NAMES[ends[0]], b = DAY_NAMES[ends[ends.length - 1]];
    for (let s = 0; s <= (b - a + 7) % 7; s++) days.push((a + s) % 7);
   }
  }
  const body = prefix ? prefix[2] : line, points = new Map(), junk = s => s.replace(/[ ,;\t]/g, '') !== '';
  let at = 0;
  for (const m of body.matchAll(/(\d{1,2})[:.](\d{2})\s+(\d{1,2}(?:[.,]\d{1,2})?)/g)) {
   if (junk(body.slice(at, m.index))) fail('bad');
   at = m.index + m[0].length;
   const minute = +m[1] * 60 + +m[2], c = centi(parseFloat(m[3].replace(',', '.')), f);
   if (+m[1] > 23 || +m[2] > 59 || points.has(minute)) fail('bad');
   if (c < min || c > max) fail('outside');
   points.set(minute, c);
  }
  if (!points.size || junk(body.slice(at))) fail('bad');
  if (points.size > MAX) fail('many');
  for (const d of days) { if (week[d]) fail('bad'); week[d] = [...points].sort((a, b) => a[0] - b[0]); }
 });
 return week.map(d => d || []);
}
// Levels follow the program: warmest = comfort, coolest = night, the most used in between = away.
function infer(week, min, max) {
 const count = new Map();
 week.flat().forEach(([, c]) => count.set(c, (count.get(c) || 0) + 1));
 const values = [...count.keys()].sort((a, b) => b - a), clamp = v => Math.max(min, Math.min(max, v));
 const levels = {comfort: values[0] ?? clamp(2000), night: values.length > 1 ? values[values.length - 1] : clamp(1600)};
 const middle = values.slice(1, -1).sort((a, b) => count.get(b) - count.get(a))[0];
 levels.away = middle ?? clamp(Math.round((levels.comfort + levels.night) / 100) * 50);
 if (levels.night === levels.comfort) levels.night = clamp(levels.comfort - 300);
 if (new Set(Object.values(levels)).size < 3) levels.away = [levels.comfort - 100, levels.night + 100, levels.comfort + 100].map(clamp).find(v => v !== levels.comfort && v !== levels.night) ?? levels.away;
 return levels;
}
const CSS = `.wpe{--wt:var(--primary-text-color,var(--ot-text,#173b40));--wm:var(--secondary-text-color,var(--ot-muted,#4f666b));--ws:var(--card-background-color,var(--ot-surface,#fff));--w2:var(--secondary-background-color,var(--ot-surface-2,#f1f5f5));--wl:var(--divider-color,var(--ot-border,#c9d6d8));--wf:var(--ot-focus,var(--primary-color,#b06313));--comfort:#eb6834;--night:#6250d6;--away:#1baf7a;--ink-night:#fff;color:var(--wt);display:grid;gap:14px;min-width:0}
@media(prefers-color-scheme:dark){.wpe:not([data-theme=light]){--wt:var(--primary-text-color,var(--ot-text,#e3eeef));--wm:var(--secondary-text-color,var(--ot-muted,#a3b7bb));--ws:var(--card-background-color,var(--ot-surface,#162124));--w2:var(--secondary-background-color,var(--ot-surface-2,#1d2b2f));--wl:var(--divider-color,var(--ot-border,#2f4247));--comfort:#d95926;--night:#9085e9;--away:#199e70;--ink-night:#1a1a19}}.wpe[data-theme=dark]{--wt:var(--primary-text-color,var(--ot-text,#e3eeef));--wm:var(--secondary-text-color,var(--ot-muted,#a3b7bb));--ws:var(--card-background-color,var(--ot-surface,#162124));--w2:var(--secondary-background-color,var(--ot-surface-2,#1d2b2f));--wl:var(--divider-color,var(--ot-border,#2f4247));--comfort:#d95926;--night:#9085e9;--away:#199e70;--ink-night:#1a1a19}
.wpe *{box-sizing:border-box}.wpe button,.wpe select,.wpe input,.wpe textarea{font:inherit;color:inherit;background:var(--ws);border:1px solid var(--wl);border-radius:10px;min-height:44px;min-width:44px;padding:6px 10px}.wpe button{cursor:pointer;font-weight:600}.wpe button:disabled{opacity:.45;cursor:default}
.wpe :focus-visible{outline:3px solid var(--wf);outline-offset:2px}.wpe h4{margin:0;font-size:.95rem}.wpe small,.wpe .wpe-note{color:var(--wm);font-size:.82rem;line-height:1.45}.wpe p{margin:0}
.wpe-levels,.wpe-tools,.wpe-row2{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.wpe-lv{display:flex;align-items:center;gap:6px;border:1px solid var(--wl);border-radius:12px;padding:4px 4px 4px 10px;background:var(--ws)}
.wpe-lv b{min-width:9ch}.wpe-dot{width:14px;height:14px;border-radius:4px;flex:none}.wpe-tools label{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.wpe-grid{display:grid;gap:6px}.wpe-day{display:grid;grid-template-columns:52px minmax(0,1fr);gap:6px;align-items:center}.wpe-day>button{padding:4px;font-size:.85rem}
.wpe-axis{position:relative;height:16px;font-size:.72rem;color:var(--wm)}.wpe-axis span{position:absolute;transform:translateX(-50%)}.wpe-axis span:first-child{transform:none}.wpe-axis span:last-child{transform:translateX(-100%)}
.wpe-bar{position:relative;height:48px;border-radius:8px;background:var(--w2);touch-action:pan-y}.wpe-seg{position:absolute;top:0;bottom:0;border:0!important;border-radius:0!important;border-right:2px solid var(--ws)!important;min-width:0!important;min-height:0!important;padding:0 4px 0 9px!important;font-size:.78rem;text-align:left;white-space:nowrap;overflow:hidden;color:#1a1a19}
.wpe-seg:first-child{border-radius:8px 0 0 8px!important}.wpe-seg:last-of-type{border-right:0!important;border-radius:0 8px 8px 0!important}.wpe-seg:only-of-type{border-radius:8px!important}
.wpe .lv-comfort{background:var(--comfort)}.wpe .lv-night{background:var(--night);color:var(--ink-night)}.wpe .lv-away{background:var(--away)}.wpe .lv-custom{background:repeating-linear-gradient(45deg,var(--w2) 0 6px,var(--wl) 6px 9px);color:var(--wt)}.wpe .lv-none{background:var(--w2);color:var(--wm)}
.wpe-seg.wpe-on{box-shadow:inset 0 0 0 3px var(--wt),inset 0 0 0 5px var(--ws);z-index:1}.wpe-h{position:absolute;top:-4px;bottom:-4px;width:44px;margin-left:-22px;cursor:ew-resize;touch-action:none;z-index:2}
.wpe-h::after{content:"";position:absolute;left:19px;top:22%;height:56%;width:6px;border-radius:3px;background:var(--ws);border:2px solid var(--wt)}.wpe-h span{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);background:var(--wt);color:var(--ws);border-radius:6px;padding:2px 6px;font-size:.75rem;white-space:nowrap}
.wpe-panel{border:1px solid var(--wl);border-radius:12px;padding:12px;display:grid;gap:10px;background:var(--ws)}.wpe-panel [aria-pressed=true]{box-shadow:inset 0 0 0 2px var(--wt)}.wpe-panel input[type=number]{width:7em}.wpe-panel input[type=time]{width:8em}
.wpe-check{display:flex;align-items:center;gap:8px;min-height:44px;border:1px solid var(--wl);border-radius:10px;padding:0 10px}.wpe-check input{min-height:0;min-width:0;width:22px;height:22px}
.wpe-msg:empty{display:none}.wpe-msg{border-left:4px solid var(--wf);padding:6px 10px;background:var(--w2);border-radius:6px}
.wpe-chart{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 6px;font-size:.72rem;color:var(--wm)}.wpe-chart svg{width:100%;height:110px;display:block;background:var(--w2);border-radius:8px}.wpe-y{display:flex;flex-direction:column;justify-content:space-between}.wpe-x{grid-column:2;display:grid;grid-template-columns:repeat(7,1fr);text-align:center}
.wpe details{border:1px solid var(--wl);border-radius:12px;padding:4px 12px}.wpe summary{cursor:pointer;min-height:44px;display:flex;align-items:center;font-weight:600}.wpe textarea{width:100%;min-height:7em;font-family:ui-monospace,monospace;margin:8px 0}`;

function mount(host, options) {
 const o = Object.assign({min: 500, max: 3000, lang: 'en'}, options), t = tr(o.lang);
 let week = valid(o.week) ? clone(o.week) : Array.from({length: 7}, () => []), levels = Object.assign(infer(week, o.min, o.max), o.levels || {});
 let sel = null, copyFrom = null, copyTo = new Set(), undo = null, msg = '', textError = '', textDraft = null, textOpen = false;
 const root = document.createElement('div');
 root.className = 'wpe';
 if (o.theme) root.dataset.theme = o.theme;
 host.replaceChildren(Object.assign(document.createElement('style'), {textContent: CSS}), root);
 const el = (tag, text, attrs = {}, on) => {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) e.setAttribute(k, v === true ? '' : v);
  if (on) e.addEventListener(tag === 'select' || tag === 'input' ? 'change' : 'click', on);
  return e;
 };
 const say = s => { msg = s; };
 const name = c => { const k = LEVELS.find(l => levels[l] === c); return k ? t.names[k] : c == null ? '' : t.custom; };
 const cls = c => c == null ? 'lv-none' : 'lv-' + (LEVELS.find(l => levels[l] === c) || 'custom');
 const F = !!o.fahrenheit, degText = c => deg(c, o.lang, F) + (F ? ' °F' : ' °C');
 // One step of a level: 0.5 °C, or 1 °F.
 const step = (c, by) => F ? centi(shown(c, true) + by, true) : c + 50 * by;
 const changed = () => { textDraft = null; textError = ''; if (o.onChange) o.onChange(clone(week)); };
 const carry = d => { for (let b = 1; b <= 7; b++) { const p = week[(d + 7 - b) % 7]; if (p.length) return p[p.length - 1][1]; } return null; };
 const segs = d => {
  const out = [];
  let s = 0, c = carry(d), p = -1;
  week[d].forEach(([m, v], i) => { if (m > s) out.push({s, e: m, c, p}); s = m; c = v; p = i; });
  out.push({s, e: 1440, c, p});
  return out;
 };
 const tidy = d => { for (let i = week[d].length - 1; i > 0; i--) if (week[d][i][1] === week[d][i - 1][1]) week[d].splice(i, 1); };
 const pick = (d, minute) => { sel = {d, i: Math.max(0, segs(d).findIndex(g => g.s <= minute && minute < g.e))}; };
 const snapshot = () => { undo = {week: clone(week), levels: {...levels}}; };
 function setLevel(d, i, c) {
  const g = segs(d)[i];
  if (g.p >= 0) week[d][g.p][1] = c; else week[d].unshift([0, c]);
  tidy(d); pick(d, g.s); changed();
 }
 function split(d, i) {
  const list = segs(d), g = list[i], at = Math.round((g.s + g.e) / 2 / STEP) * STEP, after = list[i + 1] ? list[i + 1].c : null;
  if (week[d].length >= MAX) return say(t.full);
  if (at <= g.s || at >= g.e) return say(t.short15);
  // The new second half gets another level than both neighbours: a comfort block is split for "away", others for comfort.
  const order = g.c === levels.comfort ? ['away', 'night', 'comfort'] : ['comfort', 'away', 'night'];
  week[d].push([at, levels[order.find(l => levels[l] !== g.c && levels[l] !== after) || order[0]]]);
  week[d].sort((a, b) => a[0] - b[0]); pick(d, at); changed();
 }
 function removePoint(d, i) {
  const g = segs(d)[i];
  if (g.p < 0) return;
  week[d].splice(g.p, 1); pick(d, Math.max(0, g.s - 1)); changed();
 }
 const bounds = (d, p) => [p ? week[d][p - 1][0] + 1 : 0, p < week[d].length - 1 ? week[d][p + 1][0] - 1 : 1439];
 function moveTo(d, p, minute) {
  const [lo, hi] = bounds(d, p);
  week[d][p][0] = Math.max(lo, Math.min(hi, minute)); pick(d, week[d][p][0]); changed();
 }
 function setLevelValue(key, c) {
  if (c < o.min || c > o.max) return say(fill(t.limits, {min: degText(o.min), max: degText(o.max)}));
  if (LEVELS.some(l => l !== key && levels[l] === c)) return say(t.differ);
  const old = levels[key];
  levels[key] = c;
  week.forEach(day => day.forEach(p => { if (p[1] === old) p[1] = c; }));
  if (o.onLevels) o.onLevels({...levels});
  if (week.some(day => day.length)) changed();
 }
 function applyTemplate(key) {
  snapshot();
  week = TEMPLATES[key].map(day => day.map(([m, l]) => [m, levels[l]]));
  sel = copyFrom = null; say(fill(t.applied, {name: t.templates[key]})); changed();
 }

 function renderLevels() {
  const box = el('div', null, {class: 'wpe-levels', role: 'group', 'aria-label': t.levels});
  for (const key of LEVELS) {
   const chip = el('div', null, {class: 'wpe-lv'}), n = t.names[key], c = levels[key];
   chip.append(el('span', null, {class: 'wpe-dot lv-' + key, 'aria-hidden': 'true'}), el('b', n + ' ' + degText(c)),
    el('button', '−', {type: 'button', 'aria-label': fill(t.cooler, {level: n}), 'data-k': 'lv-' + key + '-'}, () => setLevelValue(key, step(c, -1))),
    el('button', '+', {type: 'button', 'aria-label': fill(t.warmer, {level: n}), 'data-k': 'lv-' + key + '+'}, () => setLevelValue(key, step(c, 1))));
   box.append(chip);
  }
  return box;
 }
 function renderTools() {
  const box = el('div', null, {class: 'wpe-tools'}), label = el('label', t.template);
  const choice = el('select', null, {'data-k': 'template'}, () => { if (choice.value) applyTemplate(choice.value); render(); });
  choice.append(el('option', t.choose, {value: ''}), ...Object.keys(TEMPLATES).map(k => el('option', t.templates[k], {value: k})));
  label.append(choice); box.append(label);
  if (undo) box.append(el('button', t.undo, {type: 'button', 'data-k': 'undo'}, () => { ({week, levels} = undo); undo = null; sel = copyFrom = null; say(''); changed(); }));
  return box;
 }
 function renderDay(d) {
  const row = el('div', null, {class: 'wpe-day'}), bar = el('div', null, {class: 'wpe-bar', role: 'group', 'aria-label': t.days[d]});
  row.append(el('button', t.short[d], {type: 'button', title: fill(t.copyDay, {day: t.days[d]}), 'aria-label': fill(t.copyDay, {day: t.days[d]}), 'data-k': 'day' + d,
   'aria-expanded': String(copyFrom === d)}, () => { copyFrom = copyFrom === d ? null : d; copyTo = new Set(); sel = null; say(''); }), bar);
  const list = segs(d), nodes = [];
  list.forEach((g, i) => {
   const label = fill(t.block, {day: t.days[d], from: clock(g.s), to: g.e === 1440 ? '24:00' : clock(g.e)}) + (g.c == null ? '' : ', ' + name(g.c) + ' ' + degText(g.c)) + (g.p < 0 && g.c != null ? ', ' + t.inherited : '');
   const b = el('button', g.c == null ? '' : deg(g.c, o.lang, F) + '°', {type: 'button', class: 'wpe-seg ' + cls(g.c) + (sel && sel.d === d && sel.i === i ? ' wpe-on' : ''),
    style: 'left:' + g.s / 14.4 + '%;width:' + (g.e - g.s) / 14.4 + '%', 'aria-label': label, title: label, 'data-k': 'seg' + d + '-' + g.s,
    'aria-pressed': String(!!(sel && sel.d === d && sel.i === i))}, () => { sel = {d, i}; copyFrom = null; say(''); });
   nodes.push(b); bar.append(b);
  });
  // A dividing line per switch time: drag it (snaps to 15 minutes); the panel has the exact time.
  list.forEach((g, i) => {
   if (!i || g.p < 0) return;
   const h = el('span', null, {class: 'wpe-h', style: 'left:' + g.s / 14.4 + '%', 'aria-hidden': 'true'});
   h.addEventListener('pointerdown', e => {
    if (e.button) return;
    e.preventDefault();
    const rect = bar.getBoundingClientRect(), [lo, hi] = bounds(d, g.p), tip = el('span', clock(g.s)), x0 = e.clientX;
    let minute = g.s;
    h.append(tip); h.setPointerCapture(e.pointerId);
    const move = ev => {
     // A tap is not a move; a drag snaps the time to 15 minutes within its neighbours.
     const raw = Math.abs(ev.clientX - x0) < 4 ? g.s : Math.round((g.s + (ev.clientX - x0) / rect.width * 1440) / STEP) * STEP;
     minute = raw === g.s ? g.s : Math.max(Math.ceil(lo / STEP) * STEP, Math.min(Math.floor(hi / STEP) * STEP, raw));
     if (minute < lo || minute > hi) minute = g.s;
     h.style.left = minute / 14.4 + '%'; tip.textContent = clock(minute);
     nodes[i - 1].style.width = (minute - list[i - 1].s) / 14.4 + '%';
     nodes[i].style.left = minute / 14.4 + '%'; nodes[i].style.width = (g.e - minute) / 14.4 + '%';
    };
    const end = ev => {
     h.removeEventListener('pointermove', move); h.removeEventListener('pointerup', end); h.removeEventListener('pointercancel', end);
     // A tap on the line's touch area selects the block on the tapped side (narrow blocks on a phone).
     if (ev.type === 'pointerup' && minute !== g.s) moveTo(d, g.p, minute);
     else if (ev.type === 'pointerup') { sel = {d, i: ev.clientX < rect.left + g.s / 1440 * rect.width ? i - 1 : i}; copyFrom = null; say(''); }
     render();
    };
    h.addEventListener('pointermove', move); h.addEventListener('pointerup', end); h.addEventListener('pointercancel', end);
   });
   bar.append(h);
  });
  return row;
 }
 function renderCopy() {
  const d = copyFrom, box = el('div', null, {class: 'wpe-panel', role: 'group', 'aria-label': fill(t.copyTo, {day: t.days[d]})});
  box.append(el('h4', fill(t.copyTo, {day: t.days[d]})));
  const days = el('div', null, {class: 'wpe-row2'}), quick = el('div', null, {class: 'wpe-row2'});
  t.days.forEach((n, i) => {
   if (i === d) return;
   const label = el('label', null, {class: 'wpe-check'}), c = el('input', null, {type: 'checkbox', value: i, 'data-k': 'copy' + i}, () => { if (c.checked) copyTo.add(i); else copyTo.delete(i); });
   c.checked = copyTo.has(i); label.append(c, document.createTextNode(n)); days.append(label);
  });
  for (const [k, set] of [['workdays', [0, 1, 2, 3, 4]], ['weekend', [5, 6]], ['all', [0, 1, 2, 3, 4, 5, 6]]])
   quick.append(el('button', t[k], {type: 'button', 'data-k': 'quick-' + k}, () => { copyTo = new Set(set.filter(x => x !== d)); }));
  const actions = el('div', null, {class: 'wpe-row2'});
  actions.append(el('button', t.copy, {type: 'button', 'data-k': 'copy-apply'}, () => {
   const targets = [...copyTo].sort();
   if (!targets.length) { say(t.pickDay); return render(); }
   snapshot();
   for (const x of targets) week[x] = week[d].map(p => [p[0], p[1]]);
   copyFrom = null; say(fill(t.copied, {day: t.days[d]})); changed(); render();
  }), el('button', t.cancel, {type: 'button', 'data-k': 'copy-cancel'}, () => { copyFrom = null; render(); }));
  box.append(quick, days, actions);
  return box;
 }
 function renderPanel() {
  const {d, i} = sel, list = segs(d), g = list[i];
  if (!g) { sel = null; return el('span'); }
  const box = el('div', null, {class: 'wpe-panel', role: 'group', 'aria-label': t.days[d]});
  box.append(el('h4', fill(t.block, {day: t.days[d], from: clock(g.s), to: g.e === 1440 ? '24:00' : clock(g.e)}) + (g.p < 0 && g.c != null ? ' · ' + t.inherited : '')));
  const lv = el('div', null, {class: 'wpe-row2', role: 'group', 'aria-label': t.level});
  for (const key of LEVELS) lv.append(el('button', t.names[key] + ' ' + degText(levels[key]), {type: 'button', class: 'lv-' + key, 'aria-pressed': String(g.c === levels[key]),
   'data-k': 'set-' + key}, () => setLevel(d, i, levels[key])));
  const own = el('input', null, {type: 'number', step: F ? '1' : '0.5', min: shown(o.min, F), max: shown(o.max, F), 'aria-label': t.custom, 'data-k': 'own'}, () => {
   const c = centi(parseFloat(String(own.value).replace(',', '.')), F);
   if (!(c >= o.min && c <= o.max)) say(fill(t.limits, {min: degText(o.min), max: degText(o.max)})); else setLevel(d, i, c);
   render();
  });
  if (g.c != null) own.value = shown(g.c, F);
  const ownLabel = el('label', t.custom, {class: 'wpe-check'});
  ownLabel.append(own); lv.append(ownLabel); box.append(lv);
  if (g.p >= 0 && g.s > 0) {
   const time = el('div', null, {class: 'wpe-row2'}), [lo, hi] = bounds(d, g.p);
   const at = el('input', null, {type: 'time', step: '60', value: clock(g.s), 'aria-label': t.starts, 'data-k': 'time'}, () => {
    const m = /^(\d\d):(\d\d)/.exec(at.value);
    if (m) moveTo(d, g.p, +m[1] * 60 + +m[2]);
    render();
   });
   const label = el('label', t.starts, {class: 'wpe-check'});
   label.append(at);
   time.append(el('button', '−15', {type: 'button', 'aria-label': t.earlier, 'data-k': 'earlier', disabled: g.s - STEP < lo}, () => moveTo(d, g.p, g.s - STEP)), label,
    el('button', '+15', {type: 'button', 'aria-label': t.later, 'data-k': 'later', disabled: g.s + STEP > hi}, () => moveTo(d, g.p, g.s + STEP)));
   box.append(time);
  }
  const actions = el('div', null, {class: 'wpe-row2'});
  actions.append(el('button', '‹', {type: 'button', 'aria-label': t.prev, title: t.prev, 'data-k': 'prev', disabled: !i && !d}, () => { if (i) sel = {d, i: i - 1}; else sel = {d: d - 1, i: segs(d - 1).length - 1}; }),
   el('button', '›', {type: 'button', 'aria-label': t.next, title: t.next, 'data-k': 'next', disabled: i === list.length - 1 && d === 6}, () => { sel = i < list.length - 1 ? {d, i: i + 1} : {d: d + 1, i: 0}; }),
   el('button', t.split, {type: 'button', 'data-k': 'split'}, () => split(d, i)),
   el('button', t.remove, {type: 'button', 'data-k': 'remove', disabled: g.p < 0}, () => removePoint(d, i)),
   el('button', t.close, {type: 'button', 'data-k': 'close'}, () => { sel = null; }));
  box.append(actions);
  return box;
 }
 function renderChart() {
  const values = [...week.flat().map(p => p[1]), levels.comfort, levels.night], top = Math.max(...values) + 50, bottom = Math.min(...values) - 50;
  const y = c => ((top - c) / (top - bottom) * 100).toFixed(1), ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg'), add = (tag, a, title) => {
   const e = document.createElementNS(ns, tag);
   for (const [k, v] of Object.entries(a)) e.setAttribute(k, v);
   if (title) { const x = document.createElementNS(ns, 'title'); x.textContent = title; e.append(x); }
   svg.append(e); return e;
  };
  svg.setAttribute('viewBox', '0 0 1008 100'); svg.setAttribute('preserveAspectRatio', 'none'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', t.preview);
  for (let d = 1; d < 7; d++) add('line', {x1: d * 144, x2: d * 144, y1: 0, y2: 100, stroke: 'var(--wl)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'});
  let last = null;
  week.forEach((day, d) => segs(d).forEach(g => {
   if (g.c == null) return;
   const x1 = d * 144 + g.s / 10, x2 = d * 144 + g.e / 10, yy = y(g.c), color = 'var(--' + (LEVELS.find(l => levels[l] === g.c) || 'wt') + ')';
   if (last != null && last !== yy) add('line', {x1, x2: x1, y1: last, y2: yy, stroke: 'var(--wm)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'});
   add('line', {x1, x2, y1: yy, y2: yy, stroke: color, 'stroke-width': 3, 'vector-effect': 'non-scaling-stroke'});
   add('rect', {x: x1, width: x2 - x1, y: 0, height: 100, fill: 'transparent'}, fill(t.block, {day: t.days[d], from: clock(g.s), to: g.e === 1440 ? '24:00' : clock(g.e)}) + ' · ' + name(g.c) + ' ' + degText(g.c));
   last = yy;
  }));
  const box = el('div', null, {class: 'wpe-chart'}), axis = el('div', null, {class: 'wpe-y', 'aria-hidden': 'true'}), x = el('div', null, {class: 'wpe-x', 'aria-hidden': 'true'});
  axis.append(el('span', degText(top - 50)), el('span', degText(bottom + 50)));
  t.short.forEach(s => x.append(el('span', s)));
  box.append(axis, svg, x);
  return box;
 }
 function renderText() {
  const box = el('details', null, {'data-k': 'text', open: textOpen || textDraft != null || !!textError}), area = el('textarea', null, {'aria-label': t.advanced, spellcheck: 'false', 'data-k': 'textarea'});
  area.value = textDraft ?? format(week, o.lang, F);
  area.addEventListener('input', () => { textDraft = area.value; });
  box.addEventListener('toggle', () => { textOpen = box.open; });
  box.append(el('summary', t.advanced), el('small', t.textHelp + (F ? ' ' + t.inF : '')), area, el('p', textError, {class: 'wpe-msg', role: 'alert'}),
   el('button', t.apply, {type: 'button', 'data-k': 'text-apply'}, () => {
    try {
     const next = parse(area.value, o.min, o.max, F);
     snapshot(); week = next; levels = infer(week, o.min, o.max); sel = copyFrom = null; say(t.textApplied); changed();
    } catch (err) {
     if (!err || !err.key) throw err;
     textDraft = area.value;
     textError = fill(t[err.key], {line: err.line, text: err.text, min: degText(o.min), max: degText(o.max)});
    }
    render();
   }));
  return box;
 }
 function render() {
  const active = host.getRootNode().activeElement || document.activeElement, focus = active && root.contains(active) ? active.getAttribute('data-k') : null;
  const grid = el('div', null, {class: 'wpe-grid'}), axis = el('div', null, {class: 'wpe-day', 'aria-hidden': 'true'}), hours = el('div', null, {class: 'wpe-axis'});
  for (const h of [0, 6, 12, 18, 24]) hours.append(el('span', String(h).padStart(2, '0'), {style: 'left:' + h / 0.24 + '%'}));
  axis.append(el('span'), hours); grid.append(axis);
  for (let d = 0; d < 7; d++) grid.append(renderDay(d));
  const empty = !week.some(day => day.length);
  root.replaceChildren(renderLevels(), renderTools(), el('p', empty ? t.empty : t.hint, {class: 'wpe-note'}), grid,
   ...(copyFrom != null ? [renderCopy()] : sel ? [renderPanel()] : []), el('p', msg, {class: 'wpe-msg', role: 'status', 'aria-live': 'polite'}),
   ...(empty ? [] : [el('h4', t.preview), renderChart()]), renderText());
  const again = focus && root.querySelector('[data-k="' + focus + '"]');
  if (again && !again.disabled) again.focus();
 }
 root.addEventListener('click', e => { if (e.target.closest('button') && !e.defaultPrevented) queueMicrotask(render); });
 render();
 return {
  get: () => clone(week),
  set(next) { if (!valid(next)) return false; week = clone(next); levels = infer(week, o.min, o.max); sel = copyFrom = null; textDraft = null; textError = ''; render(); return true; },
  limits(min, max) { o.min = min; o.max = max; render(); },
  levels: () => ({...levels}),
  // A template with the current levels (the E32 page starts a new program with "Workdays and weekend").
  template(key) { if (TEMPLATES[key]) { applyTemplate(key); render(); } },
  render
 };
}
window.OTWeekEditor = Object.freeze({mount, format, parse, infer, valid, TEMPLATES});
})();
