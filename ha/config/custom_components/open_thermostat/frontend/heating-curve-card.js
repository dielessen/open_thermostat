/* The Learning view's two cards (OpenThermostat, E32 rc.5): one module, one versioned URL.

   openthermostat-heating-curve — water temperature by outdoor temperature. Reads the attributes of the "Water
   temperature by weather compensation" sensor (e32_flow.py), all in °C (its state is converted on an imperial
   system, so the card never draws from it): the slope in use and where it comes from (standard, learned, or
   estimated from the house), the standard slope from the water temperature in hard frost, the room temperature
   the curve starts from, the outdoor temperature now, the water temperature limits, the line's own value now
   (base_c) and what weather compensation asks (flow_c). It draws what the E32 Home page draws
   (data/html/house.html):
     water = room + slope × max(0, room − outdoor), within the lowest and highest water temperature,
   the standard line dashed, the learned one solid with the gain between them as a soft band, "Now" on the line
   (with what the E32 asks when the room correction adds to it) and the hard-frost point (−10 °C). A crosshair
   reads any outdoor temperature (pointer, touch or arrow keys); the values are also a table. Plain inline SVG;
   marks 2 px, markers with a ring in the card colour.

   openthermostat-knowledge — what the E32 knows: a ring with the percentage and, below it, what it still
   learns in words (the Knowledge sensor, insight.py).

   The words are the integration's translations (strings.json entity.sensor.flow_curve.state_attributes.chart
   and entity.sensor.knowledge.state_attributes.card), so every viewer reads them in their own Home Assistant
   language; English is only the last resort. Colours: the validated chart steps of the E32 pages
   (history-chart.js), selected per mode, never an inverted light theme. */
const PREFIX = 'component.open_thermostat.entity.sensor.';
const CURVE_TEXT = {title: 'Water temperature by outdoor temperature', standard: 'Standard', learned: 'Learned for your house',
 house: 'Estimated from your house', now: 'Now', frost: 'At −10 °C with {room} °C inside: {flow} °C',
 now_point: '{outdoor} °C outside → {flow} °C', asks: 'E32 asks {flow} °C', at: 'At {outdoor} °C outside',
 lower: '{n} °C cooler than standard', higher: '{n} °C warmer than standard', outdoor: 'Outdoor temperature (°C)',
 water: 'Water to heating (°C)', caption: 'The colder it is outside, the warmer the water. The E32 learns the line for your house and keeps it as low as it can.',
 values: 'Show the values', outside: 'Outside', off: 'Weather compensation is off; the lines show what it would ask.',
 waiting: 'The E32 has not reported its weather compensation yet.'};
const KNOWLEDGE_TEXT = {title: 'The E32 knows your house', ring: 'The E32 knows your house: {pct} %', hint: 'It learns by itself while the heating runs.',
 missing: 'Still to learn', more: 'And {n} more.', done: 'It has learned everything it needs; it keeps checking as the seasons change.',
 waiting: 'The E32 has not reported what it knows yet.'};
// The axes (°C): outdoor −15..20 (wider when it is colder or warmer now), water 20..80. FROST: the design point.
const X0 = -15, X1 = 20, Y0 = 20, Y1 = 80, FROST = -10;
const COLORS = `--hc-learned:#00876f;--hc-now:#b5600c;--hc-learned-soft:rgba(0,135,111,.13);--hc-now-soft:rgba(181,96,12,.18)`;
const DARK = `--hc-learned:#239c8a;--hc-now:#c97a2c;--hc-learned-soft:rgba(35,156,138,.2);--hc-now-soft:rgba(201,122,44,.24)`;
const BASE = `:host{display:block}ha-card{display:block;padding:16px;color:var(--primary-text-color);${COLORS};
--hc-surface:var(--ha-card-background,var(--card-background-color,#fff));--hc-muted:var(--secondary-text-color,#6b6b6b);--hc-grid:var(--divider-color,rgba(127,127,127,.22))}
ha-card.dark{${DARK}}h2{margin:0 0 4px;font-size:1.05rem;font-weight:600;line-height:1.35;overflow-wrap:anywhere}
p{margin:0;line-height:1.45}.muted{color:var(--hc-muted);font-size:.9rem}@media(max-width:480px){ha-card{padding:12px}}`;
const CURVE_STYLE = `${BASE}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;margin:2px 0 6px;padding:0;list-style:none;font-size:.875rem;color:var(--hc-muted)}
.legend li{display:inline-flex;align-items:center;gap:6px;max-width:100%}
.key{display:inline-block;flex:none;width:18px;border-top:2px solid var(--hc-learned)}.key.standard{border-top:2px dashed var(--hc-muted)}
.key.now{width:10px;height:10px;border:0;border-radius:50%;background:var(--hc-now);box-shadow:0 0 0 3px var(--hc-now-soft)}
.plot{position:relative;touch-action:pan-y}svg{display:block;max-width:100%;height:auto;overflow:visible;-webkit-tap-highlight-color:transparent}
svg:focus{outline:none}svg:focus-visible{outline:2px solid var(--primary-color);outline-offset:4px;border-radius:4px}
.grid{stroke:var(--hc-grid);stroke-width:1;shape-rendering:crispEdges}.tick{font-size:12px;fill:var(--hc-muted);font-variant-numeric:tabular-nums}
.axis-title{font-size:12px;fill:var(--hc-muted)}.band{fill:var(--hc-learned-soft);stroke:none}
.line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}.line.learned{stroke:var(--hc-learned)}
.line.standard{stroke:var(--hc-muted);stroke-dasharray:6 5}.point{stroke:var(--hc-surface);stroke-width:2}
.point.learned{fill:var(--hc-learned)}.point.standard{fill:var(--hc-muted)}.point.now{fill:var(--hc-now)}.halo{fill:var(--hc-now-soft)}
.label{font-size:12.5px;font-weight:600;fill:var(--primary-text-color);paint-order:stroke;stroke:var(--hc-surface);stroke-width:4px;stroke-linejoin:round}
.label .sub{font-weight:400;fill:var(--hc-muted)}.leader{stroke:var(--hc-muted);stroke-width:1}
.cross{stroke:var(--primary-text-color);stroke-opacity:.35;stroke-width:1;shape-rendering:crispEdges}.hit{fill:transparent;cursor:crosshair}
.tip{position:absolute;top:0;left:0;z-index:1;min-width:132px;padding:6px 10px;border-radius:8px;pointer-events:none;font-size:.875rem;line-height:1.35;
background:var(--hc-surface);color:var(--primary-text-color);border:1px solid var(--hc-grid);box-shadow:0 2px 10px rgba(0,0,0,.18)}.tip[hidden]{display:none}
.tip-head{color:var(--hc-muted);margin-bottom:2px;white-space:nowrap}.tip-row{display:flex;align-items:center;gap:8px;white-space:nowrap}
.tip-row b{font-weight:600;font-variant-numeric:tabular-nums}.tip-row span{color:var(--hc-muted)}
.caption{margin:8px 0 0;color:var(--hc-muted);font-size:.9rem}.note{margin:6px 0 0;font-size:.9rem}
details{margin:8px 0 0}summary{cursor:pointer;color:var(--primary-color);font-size:.9rem;padding:6px 0;min-height:24px}
table{border-collapse:collapse;color:inherit;font-size:.875rem;font-variant-numeric:tabular-nums;margin-top:4px}th,td{padding:4px 12px 4px 0;text-align:right;vertical-align:bottom;overflow-wrap:normal}td{white-space:nowrap}
th{font-weight:500;color:var(--hc-muted)}th:first-child,td:first-child{text-align:left}tr+tr td{border-top:1px solid var(--hc-grid)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}`;
const KNOWLEDGE_STYLE = `${BASE}
.head{display:flex;align-items:center;gap:14px}.ring{flex:none;width:72px;height:72px}.ring .track{stroke:var(--hc-learned-soft)}
.ring .fill{stroke:var(--hc-learned)}.ring text{font-size:16px;font-weight:600;fill:var(--primary-text-color)}
h3{margin:14px 0 6px;font-size:.95rem;font-weight:600}ul{margin:0;padding:0;list-style:none}
li{position:relative;margin:0 0 6px;padding-left:16px;line-height:1.45;overflow-wrap:anywhere}
li::before{content:"";position:absolute;left:2px;top:.6em;width:6px;height:6px;border-radius:50%;background:var(--hc-learned)}
li.more{color:var(--hc-muted)}li.more::before{background:var(--hc-muted)}.done{margin-top:12px}`;

const finite = value => typeof value === 'number' && Number.isFinite(value);
const numeric = value => { const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value; return finite(n) ? n : null; };
const locale = hass => hass?.locale?.language || hass?.language || 'en';
const SVG = 'http://www.w3.org/2000/svg';
const make = (tag, attrs = {}, text) => {
 const e = tag.startsWith('svg:') ? document.createElementNS(SVG, tag.slice(4)) : document.createElement(tag);
 for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) e.setAttribute(k, v);
 if (text !== undefined) e.textContent = text;
 return e;
};
// WeatherCurve::baseCentiC as the E32 computes it, within the water temperature limits where they are known.
const water = (slope, room, low, high) => outdoor =>
 Math.min(high ?? Infinity, Math.max(low ?? -Infinity, room + slope * Math.max(0, room - outdoor)));

/* The chart, drawn into `host` (a .plot element) at its own width; `t(key, values)` gives a text and `n(value,
   digits)` a number in the viewer's language. `keep` ({at, focus}) carries the crosshair and the keyboard focus
   over a redraw (a new state, a new width), so a tooltip being read stays. Returns what the table reads. */
function drawCurve(host, data, t, n, keep = {at: null, focus: false}) {
 const width = Math.max(260, Math.round(host.clientWidth || 320)), M = {left: 34, right: 12, top: 24, bottom: 42};
 const plotH = Math.round(Math.min(240, Math.max(168, width * 0.5))), height = M.top + plotH + M.bottom;
 const x0 = data.outdoor !== null && data.outdoor < X0 ? Math.floor((data.outdoor - 1) / 5) * 5 : X0;
 const x1 = data.outdoor !== null && data.outdoor > X1 ? Math.ceil((data.outdoor + 1) / 5) * 5 : X1;
 const px = v => M.left + (v - x0) / (x1 - x0) * (width - M.left - M.right);
 const py = v => M.top + (Y1 - Math.min(Y1, Math.max(Y0, v))) / (Y1 - Y0) * plotH;
 const svg = make('svg:svg', {width, height, viewBox: `0 0 ${width} ${height}`, tabindex: '0', role: 'img'});
 const tip = make('div', {class: 'tip', hidden: ''}), live = make('span', {class: 'sr', 'aria-live': 'polite'});
 const was = keep.at, refocus = keep.focus; // before the old chart goes (a browser may blur it on the way out)
 host.replaceChildren(svg, tip, live); // in the document first, so the labels can be measured
 const layer = cls => svg.appendChild(make('svg:g', {class: cls}));
 const grid = layer('axes'), marks = layer('marks'), labels = layer('labels'), cross = layer('crosshair');
 for (let v = Y0; v <= Y1; v += 10) {
  grid.append(make('svg:line', {class: 'grid', x1: M.left, x2: width - M.right, y1: py(v), y2: py(v)}),
   make('svg:text', {class: 'tick', x: M.left - 8, y: py(v) + 4, 'text-anchor': 'end'}, n(v)));
 }
 for (let v = Math.ceil(x0 / 5) * 5; v <= x1; v += 5)
  grid.append(make('svg:text', {class: 'tick', x: px(v), y: M.top + plotH + 18, 'text-anchor': 'middle'}, n(v)));
 grid.append(make('svg:text', {class: 'axis-title', x: (M.left + width - M.right) / 2, y: height - 4, 'text-anchor': 'middle'}, t('outdoor')),
  make('svg:text', {class: 'axis-title', x: M.left - 30, y: 12}, t('water')));
 const standard = data.standardSlope !== null ? water(data.standardSlope, data.room, data.low, data.high) : null;
 const own = data.learned ? water(data.slope, data.room, data.low, data.high) : null;
 const sample = f => { const out = []; for (let v = x0; v <= x1 + 1e-9; v += 0.25) out.push([px(v), py(f(v))]); return out; };
 const path = points => 'M' + points.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join('L');
 const lines = [];
 if (standard && own) marks.append(make('svg:path', {class: 'band', d: path([...sample(own), ...sample(standard).reverse()]) + 'Z'}));
 if (standard) { const s = sample(standard); lines.push(s); marks.append(make('svg:path', {class: 'line standard', 'data-line': 'standard', d: path(s)})); }
 if (own) { const s = sample(own); lines.push(s); marks.append(make('svg:path', {class: 'line learned', 'data-line': 'learned', d: path(s)})); }
 // The hard-frost point of the line in use (the learned one once there is one), and the gain over the standard.
 const used = own || standard, frost = Math.round(used(FROST)), gain = own && standard ? Math.round(standard(FROST) - own(FROST)) : 0;
 const solid = data.house ? 'house' : 'learned'; // the solid line's words: learned, or estimated from the house
 marks.append(make('svg:circle', {class: 'point ' + (own ? 'learned' : 'standard'), 'data-point': 'frost', cx: px(FROST), cy: py(used(FROST)), r: 4.5}));
 // "Now" sits on the line: the E32's own value of it (base_c), else the line here at the outdoor temperature now;
 // what weather compensation asks with the room correction (flow_c) is told beside it when it differs.
 const base = data.outdoor === null ? null
  : data.base !== null ? Math.min(data.high ?? Infinity, Math.max(data.low ?? -Infinity, data.base)) : used(data.outdoor);
 const showNow = base !== null;
 const nowRows = showNow ? [t('now_point', {outdoor: n(data.outdoor, 1), flow: n(Math.round(base))})] : [];
 if (showNow && data.now !== null && Math.round(data.now) !== Math.round(base)) nowRows.push(t('asks', {flow: n(data.now)}));
 if (showNow) {
  marks.append(make('svg:circle', {class: 'halo', cx: px(data.outdoor), cy: py(base), r: 12}),
   make('svg:circle', {class: 'point now', 'data-point': 'now', cx: px(data.outdoor), cy: py(base), r: 5}));
 }
 // Labels, most important first; each takes the first of its places that overlaps no line, mark or earlier label
 // and stays inside the plot. An optional one that finds none is left out (the legend, tooltip and table still
 // carry it). A required one ("Now", the hard-frost point) then takes the free place of the plot nearest to its
 // point, with a thin leader; in a plot without one it crosses a line (its halo keeps it legible) rather than
 // cover another label or point.
 const taken = [], plot = {l: M.left, r: width - M.right, t: M.top - 4, b: M.top + plotH};
 const crosses = box => lines.some(line => line.some(([x, y]) => x >= box.l - 2 && x <= box.r + 2 && y >= box.t - 2 && y <= box.b + 2));
 const covers = box => taken.some(o => box.l < o.r && box.r > o.l && box.t < o.b && box.b > o.t);
 const place = (attrs, rows, spots, required, near) => {
  const text = make('svg:text', {class: 'label', ...attrs});
  rows.forEach((row, i) => text.append(make('svg:tspan', {class: i ? 'sub' : null, x: 0, dy: i ? 15 : 0}, row)));
  labels.append(text);
  const at = ([x, y, anchor]) => {
   text.setAttribute('text-anchor', anchor);
   text.querySelectorAll('tspan').forEach(s => s.setAttribute('x', x));
   text.setAttribute('y', y);
   let b; try { b = text.getBBox(); } catch (e) { b = null; }
   const w = b && b.width ? b.width : Math.max(...rows.map(r => r.length)) * 7, h = 15 * rows.length;
   const l = anchor === 'end' ? x - w : anchor === 'middle' ? x - w / 2 : x;
   return {l, r: l + w, t: y - 12, b: y - 12 + h};
  };
  // How far a box sticks out of the plot (0: inside); covering a label or point weighs far more than a line.
  const outside = box => Math.max(0, plot.l - box.l) + Math.max(0, box.r - plot.r) + Math.max(0, plot.t - box.t) + Math.max(0, box.b - plot.b);
  const score = box => outside(box) * 10 + (covers(box) ? 100 : 0) + (crosses(box) ? 1 : 0);
  let best = null, size = null;
  for (const spot of spots) {
   const box = at(spot), s = score(box);
   if (s === 0) { taken.push(box); return box; }
   if (!best || s < best[0]) best = [s, 0, spot];
   size = box;
  }
  if (!required || !best) { text.remove(); return null; }
  // Every place of the plot on an 8 px grid: the lowest score, then the nearest to the point.
  const w = size.r - size.l, h = size.b - size.t;
  for (let y = plot.t + 12; y - 12 + h <= plot.b; y += 8) for (let x = plot.l + 4; x + w <= plot.r; x += 8) {
   const box = {l: x, r: x + w, t: y - 12, b: y - 12 + h}, s = score(box);
   const d = Math.hypot(Math.max(box.l - near[0], 0, near[0] - box.r), Math.max(box.t - near[1], 0, near[1] - box.b));
   if (s < best[0] || (s === best[0] && d < best[1])) best = [s, d, [x, y, 'start']];
  }
  const box = at(best[2]); taken.push(box); return box;
 };
 // A label placed away from its point gets a thin leader to it.
 const leader = (x, y, r, box) => {
  const nx = Math.min(box.r, Math.max(box.l, x)), ny = Math.min(box.b, Math.max(box.t, y)), d = Math.hypot(nx - x, ny - y);
  if (d > r + 10) marks.append(make('svg:line', {class: 'leader', x1: x + (nx - x) / d * (r + 2), y1: y + (ny - y) / d * (r + 2), x2: nx, y2: ny}));
 };
 const dot = (x, y, r) => taken.push({l: x - r, r: x + r, t: y - r, b: y + r});
 dot(px(FROST), py(used(FROST)), 6);
 if (showNow) dot(px(data.outdoor), py(base), 12);
 const around = (x, y, gapX, gapY) => [[x + gapX, y - gapY, 'start'], [x + gapX, y + gapY + 12, 'start'], [x - gapX, y - gapY, 'end'],
  [x - gapX, y + gapY + 12, 'end'], [x, y - gapY - 6, 'middle'], [x, y + gapY + 18, 'middle']];
 if (showNow) {
  const x = px(data.outdoor), y = py(base);
  const box = place({'data-label': 'now'}, nowRows, [...around(x, y, 14, 12), ...around(x, y, 14, 28)], true, [x, y]);
  if (box) leader(x, y, 6, box);
 }
 // The hard-frost point is the line at −10 °C for the room temperature the curve starts from (WeatherCurve), so it
 // names that room temperature: the setting "water temperature in hard frost" is for a 20 °C room.
 const frostAt = flow => t('frost', {room: n(data.room, 1), flow: n(flow)});
 const frostRows = [frostAt(frost)];
 if (Math.abs(gain) >= 1) frostRows.push(t(gain > 0 ? 'lower' : 'higher', {n: n(Math.abs(gain))}));
 const fx = px(FROST), fy = py(used(FROST)), upper = Math.min(fy, standard ? py(standard(FROST)) : fy, own ? py(own(FROST)) : fy);
 const frostBox = place({'data-label': 'frost'}, frostRows,
  [[fx + 10, upper - 14 - 15 * (frostRows.length - 1), 'start'], ...around(fx, fy, 10, 10), ...around(fx, fy, 10, 30)], true, [fx, fy]);
 if (frostBox) leader(fx, fy, 5, frostBox);
 // Direct labels at the cold end, where the lines are furthest apart.
 for (const [f, key] of [[own, 'learned'], [standard, 'standard']]) {
  if (!f) continue;
  const x = px(x0) + 6, y = py(f(x0 + 0.5));
  place({'data-label': key}, [t(key === 'learned' ? solid : key)], [[x, y - 9, 'start'], [x, y + 19, 'start']]);
 }
 // The crosshair: the nearest half degree under the pointer, or the arrow keys.
 const hair = make('svg:line', {class: 'cross', y1: M.top, y2: M.top + plotH, visibility: 'hidden'});
 const marksAt = [own && ['learned', own], standard && ['standard', standard]].filter(Boolean);
 const dots = marksAt.map(([key]) => make('svg:circle', {class: 'point ' + key, r: 4, visibility: 'hidden'}));
 cross.append(hair, ...dots, make('svg:rect', {class: 'hit', x: M.left, y: M.top, width: width - M.left - M.right, height: plotH}));
 let at = null;
 const show = (outdoor, announce) => {
  at = keep.at = Math.min(x1, Math.max(x0, Math.round(outdoor * 2) / 2));
  const x = px(at);
  hair.setAttribute('x1', x); hair.setAttribute('x2', x); hair.setAttribute('visibility', 'visible');
  const rows = marksAt.map(([key, f], i) => {
   dots[i].setAttribute('cx', x); dots[i].setAttribute('cy', py(f(at))); dots[i].setAttribute('visibility', 'visible');
   return [key, Math.round(f(at))];
  });
  const head = make('div', {class: 'tip-head'}, t('at', {outdoor: n(at, 1)}));
  const words = key => t(key === 'learned' ? solid : key);
  tip.replaceChildren(head, ...rows.map(([key, value]) => {
   const row = make('div', {class: 'tip-row'});
   row.append(make('i', {class: 'key ' + key}), make('b', {}, n(value) + ' °C'), make('span', {}, words(key)));
   return row;
  }));
  tip.hidden = false;
  const left = Math.min(width - tip.offsetWidth - 2, Math.max(2, x + (x > width / 2 ? -tip.offsetWidth - 12 : 12)));
  tip.style.transform = `translate(${left}px, ${M.top}px)`;
  if (announce) live.textContent = [head.textContent, ...rows.map(([key, value]) => words(key) + ' ' + n(value) + ' °C')].join(', ');
 };
 const hide = () => { at = keep.at = null; tip.hidden = true; hair.setAttribute('visibility', 'hidden'); dots.forEach(d => d.setAttribute('visibility', 'hidden')); };
 const outdoorAt = event => { const box = svg.getBoundingClientRect(); return x0 + ((event.clientX - box.left) / box.width * width - M.left) / (width - M.left - M.right) * (x1 - x0); };
 svg.addEventListener('pointermove', e => show(outdoorAt(e)));
 svg.addEventListener('pointerdown', e => show(outdoorAt(e)));
 svg.addEventListener('pointerleave', e => { if (e.pointerType !== 'touch') hide(); });
 svg.addEventListener('focus', () => { keep.focus = true; show(at ?? data.outdoor ?? 0, true); });
 // Leaving the chart hides the crosshair; a redraw that replaces this chart does not.
 svg.addEventListener('blur', () => { if (svg.isConnected) { keep.focus = false; hide(); } });
 svg.addEventListener('keydown', e => {
  const step = {ArrowLeft: -1, ArrowRight: 1, ArrowDown: -1, ArrowUp: 1}[e.key];
  if (step) { e.preventDefault(); show((at ?? data.outdoor ?? 0) + step * (e.shiftKey ? 5 : 1), true); }
  else if (e.key === 'Home' || e.key === 'End') { e.preventDefault(); show(e.key === 'Home' ? x0 : x1, true); }
  else if (e.key === 'Escape') hide();
 });
 // The chart's accessible name: what it shows, in one sentence per line.
 const name = [t('title')];
 if (standard) name.push(t('standard') + ': ' + frostAt(Math.round(standard(FROST))));
 if (own) name.push(t(solid) + ': ' + frostAt(Math.round(own(FROST))));
 if (showNow) name.push(t('now') + ': ' + nowRows.join(', '));
 svg.setAttribute('aria-label', name.join('. '));
 // A redraw keeps what the viewer had: the crosshair where it was, the keyboard focus on the chart.
 if (refocus) svg.focus({preventScroll: true});
 if (was !== null) show(was);
 return {standard, own, frost, gain, x0, x1, solid};
}

function table(model, t, n) {
 const box = make('details', {class: 'values'}), body = make('table');
 box.append(make('summary', {}, t('values')), body);
 const head = make('tr');
 head.append(make('th', {scope: 'col'}, t('outside')));
 for (const key of ['standard', 'learned']) if (model[key === 'learned' ? 'own' : 'standard']) head.append(make('th', {scope: 'col'}, t(key === 'learned' ? model.solid : key)));
 body.append(head);
 for (let v = Math.ceil(model.x0 / 5) * 5; v <= model.x1; v += 5) {
  const row = make('tr');
  row.append(make('td', {}, n(v) + ' °C'));
  for (const f of [model.standard, model.own]) if (f) row.append(make('td', {}, n(Math.round(f(v))) + ' °C'));
  body.append(row);
 }
 return box;
}

class OpenThermostatCard extends HTMLElement {
 constructor() { super(); this.attachShadow({mode: 'open'}); this._key = null; }
 setConfig(config) {
  if (!config || typeof config.entity !== 'string' || !config.entity.startsWith('sensor.')) throw new Error(this.constructor.configError);
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
 getGridOptions() { return {columns: 12, min_columns: 6}; }
 // A text of the integration's translations, its {placeholders} filled; English when Home Assistant has none.
 text(base, fallback, key, values = {}) {
  let text = '';
  try { text = this._hass?.localize?.(PREFIX + base + key, values) || ''; } catch (e) { text = ''; }
  return typeof text === 'string' && text ? text : fallback[key].replace(/\{(\w+)\}/g, (all, k) => k in values ? values[k] : all);
 }
 // A number in the viewer's language, with a real minus sign.
 number(value, digits = 0) {
  return value.toLocaleString(locale(this._hass), {maximumFractionDigits: digits, minimumFractionDigits: 0, useGrouping: false}).replace('-', '−');
 }
 frame(style) {
  const card = make('ha-card', this._hass?.themes?.darkMode ? {class: 'dark'} : {});
  this.shadowRoot.replaceChildren(make('style', {}, style), card);
  return card;
 }
 missing(card, config, st) {
  if (st) return false;
  const text = this._hass.localize?.('ui.panel.lovelace.warning.entity_not_found', {entity: config.entity}) || 'Entity not available: ' + config.entity;
  card.append(make('p', {class: 'muted'}, text));
  return true;
 }
}

class OpenThermostatHeatingCurve extends OpenThermostatCard {
 static configError = 'This card needs the "Water temperature by weather compensation" sensor of OpenThermostat (entity: sensor.…); the OpenThermostat dashboard adds it for you.';
 constructor() { super(); this._resize = null; this._width = 0; this._keep = {at: null, focus: false}; }
 getCardSize() { return 6; }
 disconnectedCallback() { this._resize?.disconnect(); this._resize = null; }
 render() {
  const hass = this._hass, config = this._config;
  if (!hass || !config) return;
  const t = (key, values) => this.text('flow_curve.state_attributes.chart.state.', CURVE_TEXT, key, values), n = (v, d) => this.number(v, d);
  const card = this.frame(CURVE_STYLE), st = hass.states?.[config.entity];
  card.append(make('h2', {}, config.name || t('title')));
  if (this.missing(card, config, st)) return;
  // Everything in °C from the attributes, never from the state (Home Assistant converts that on an imperial system).
  const a = st.attributes || {}, slope = numeric(a.slope), usable = slope !== null && slope > 0;
  const data = {standardSlope: numeric(a.standard_slope) ?? (a.slope_source === 'design' && usable ? slope : null), slope,
   room: numeric(a.room_c) ?? 20, low: numeric(a.minimum_flow_c), high: numeric(a.maximum_flow_c), outdoor: numeric(a.outdoor_c),
   base: numeric(a.base_c), now: numeric(a.flow_c), house: a.slope_source === 'house',
   learned: (a.slope_source === 'learned' || a.slope_source === 'house') && usable};
  if (data.standardSlope === null && !data.learned) { card.append(make('p', {class: 'muted'}, t('waiting'))); return; }
  const legend = make('ul', {class: 'legend'});
  const key = (cls, label) => { const li = make('li', {'data-key': cls}); li.append(make('i', {class: 'key ' + cls}), label); legend.append(li); };
  if (data.standardSlope !== null) key('standard', t('standard'));
  if (data.learned) key('learned', t(data.house ? 'house' : 'learned'));
  if (data.outdoor !== null) key('now', t('now'));
  const plot = make('div', {class: 'plot'});
  card.append(legend, plot, make('p', {class: 'caption'}, t('caption')));
  if (a.state === 'advice') card.append(make('p', {class: 'note'}, t('off')));
  const draw = () => {
   this._width = plot.clientWidth;
   const model = drawCurve(plot, data, t, n, this._keep), old = card.querySelector('details.values'), values = table(model, t, n);
   values.open = !!old?.open; // an open table stays open over a new width
   old?.remove();
   card.append(values);
  };
  draw();
  // Drawn at the card's own width, so the text stays 12 px on a phone; again when the width changes.
  this._resize?.disconnect();
  if (typeof ResizeObserver === 'function') {
   this._resize = new ResizeObserver(() => { if (plot.isConnected && Math.abs(plot.clientWidth - this._width) > 2) draw(); });
   this._resize.observe(plot);
  }
 }
}

class OpenThermostatKnowledge extends OpenThermostatCard {
 static configError = 'This card needs the Knowledge sensor of OpenThermostat (entity: sensor.…); the OpenThermostat dashboard adds it for you.';
 getCardSize() { return 4; }
 render() {
  const hass = this._hass, config = this._config;
  if (!hass || !config) return;
  const t = (key, values) => this.text('knowledge.state_attributes.card.state.', KNOWLEDGE_TEXT, key, values);
  const card = this.frame(KNOWLEDGE_STYLE), st = hass.states?.[config.entity];
  if (this.missing(card, config, st)) return;
  const pct = numeric(st.state), a = st.attributes || {};
  const head = make('div', {class: 'head'}), words = make('div');
  words.append(make('h2', {}, config.name || t('title')), make('p', {class: 'muted'}, pct === null ? t('waiting') : t('hint')));
  if (pct !== null) {
   const share = Math.min(100, Math.max(0, pct)), r = 30, length = 2 * Math.PI * r;
   const ring = make('svg:svg', {class: 'ring', viewBox: '0 0 72 72', role: 'img', 'aria-label': t('ring', {pct: this.number(share)})});
   ring.append(make('svg:circle', {class: 'track', cx: 36, cy: 36, r, fill: 'none', 'stroke-width': 7}));
   if (share > 0) ring.append(make('svg:circle', {class: 'fill', cx: 36, cy: 36, r, fill: 'none', 'stroke-width': 7, 'stroke-linecap': 'round',
    'stroke-dasharray': `${(share / 100 * length).toFixed(2)} ${length.toFixed(2)}`, transform: 'rotate(-90 36 36)'}));
   ring.append(make('svg:text', {x: 36, y: 41.5, 'text-anchor': 'middle'}, this.number(share) + ' %'));
   head.append(ring);
  }
  head.append(words);
  card.append(head);
  if (pct === null) return;
  const missing = Array.isArray(a.missing) ? a.missing.filter(s => typeof s === 'string' && s) : [];
  const more = Number.isInteger(a.more) && a.more > 0 ? a.more : 0;
  if (!missing.length && !more) { card.append(make('p', {class: 'done'}, t('done'))); return; }
  const list = make('ul');
  for (const sentence of missing) list.append(make('li', {}, sentence));
  if (more) list.append(make('li', {class: 'more'}, t('more', {n: this.number(more)})));
  card.append(make('h3', {}, t('missing')), list);
 }
}
// Other dashboard cards (HACS resources) may later replace window.customElements with a scoped-registry
// polyfill whose get() does not see elements defined before it; Home Assistant then reports "Custom element
// doesn't exist". So: define now, and again (a fresh subclass) whenever the registry in use lacks the element.
// Never throws. (The same guard as e32-week-card.js and room-status-card.js.)
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
ensureDefined('openthermostat-heating-curve', OpenThermostatHeatingCurve);
ensureDefined('openthermostat-knowledge', OpenThermostatKnowledge);
window.customCards = window.customCards || [];
for (const [type, name, description] of [
 ['openthermostat-heating-curve', 'OpenThermostat heating curve', 'Water temperature by outdoor temperature: the standard line, the one learned for your house and now.'],
 ['openthermostat-knowledge', 'OpenThermostat knowledge', 'How much the E32 knows about your house, and what it still learns.']])
 if (!window.customCards.some(c => c.type === type)) window.customCards.push({type, name, description});
