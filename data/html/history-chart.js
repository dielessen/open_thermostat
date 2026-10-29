/* 24-hour charts from GET /status/history: 5-minute averages the E32 keeps in RAM
   since its last restart. Plain inline SVG, no chart library. Read-only. */
'use strict';
(() => {
    const DAY = 86400000, HOUR = 3600000;
    const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
    const locale = () => typeof OpenThermostatLanguage === 'undefined' ? 'en-GB' : OpenThermostatLanguage.locale;
    const fixed = (v, d) => v.toLocaleString(locale(), {minimumFractionDigits:d, maximumFractionDigits:d, useGrouping:false});
    const clock = t => new Date(t).toLocaleTimeString(locale(), {hour:'2-digit', minute:'2-digit'});
    const charts = Object.create(null); // hover data per drawn chart, replaced on every render

    // Validated model with absolute times (ms), values in degC or percent; null when unusable.
    function series(list, n, min, max, scale) {
        if (list === null || list === undefined) return null;
        if (!Array.isArray(list) || list.length !== n) return undefined;
        const out = new Array(n);
        for (let i = 0; i < n; i++) {
            const v = list[i];
            if (v === null) { out[i] = null; continue; }
            if (!Number.isInteger(v) || v < min || v > max) return undefined;
            out[i] = v / scale;
        }
        return out;
    }
    function parse(doc, receivedAt) {
        if (!doc || typeof doc !== 'object' || doc.schema !== 1 || doc.available !== true) return null;
        const n = doc.points, period = doc.period_s * 1000, ago = doc.oldest_start_ago_s;
        if (!Number.isSafeInteger(n) || n < 2 || n > 400 || !(doc.period_s >= 60 && doc.period_s <= 3600) ||
            !Number.isSafeInteger(ago) || ago < 0 || !Number.isSafeInteger(doc.uptime_s) || !Array.isArray(doc.rooms)) return null;
        const temp = list => series(list, n, -600, 1500, 10);
        const model = {n, period, start: receivedAt - ago * 1000, boot: receivedAt - doc.uptime_s * 1000, rooms: Object.create(null),
            flow: temp(doc.flow), ret: temp(doc.return), request: temp(doc.request), thermostat: temp(doc.thermostat_request),
            burner: series(doc.burner_pct, n, 0, 100, 1)};
        if ([model.flow, model.ret, model.request, model.thermostat, model.burner].includes(undefined)) return null;
        for (const room of doc.rooms.slice(0, 8)) {
            if (!room || typeof room.id !== 'string' || !room.id || room.id.length > 32) return null;
            const t = temp(room.temperature), s = temp(room.target);
            if (t === undefined || s === undefined) return null;
            model.rooms[room.id] = {temperature: t, target: s};
        }
        return model;
    }

    // Times of the points: the middle of each 5-minute slot, never in the future.
    // The window starts at the oldest point: within 24 h of a restart, the restart.
    function window_(model, now) {
        const from = Math.max(now - DAY, model.start), to = Math.max(now, from + HOUR);
        const at = p => Math.min(model.start + p * model.period + model.period / 2, now);
        return {from, to, at, full: now - model.start >= DAY - model.period};
    }
    function range(values) {
        let lo = Infinity, hi = -Infinity;
        for (const list of values) if (list) for (const v of list) if (v !== null) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
        return lo <= hi ? [lo, hi] : null;
    }
    function scale(lo, hi, minSpan) {
        if (hi - lo < minSpan) { const mid = (lo + hi) / 2; lo = mid - minSpan / 2; hi = mid + minSpan / 2; }
        const step = [0.5, 1, 2, 5, 10, 20, 50].find(s => (hi - lo) / s <= 4) || 50;
        lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
        const ticks = []; for (let v = lo; v <= hi + 1e-9; v += step) ticks.push(v);
        return {lo, hi, ticks, digits: step < 1 ? 1 : 0};
    }
    // Visible values within the window only (a full ring reaches 5 min past 24 h).
    function visible(model, w, list) {
        return list && list.map((v, p) => w.at(p) >= w.from ? v : null);
    }

    // Each chart has its own viewBox width, so its text keeps a readable size where it is shown.
    const L = 30, R = 8, T = 16;
    function frame(id, w, W, h, y, label, body, unit) {
        const B = h - 18, x = t => L + (t - w.from) / (w.to - w.from) * (W - L - R);
        let grid = '';
        for (const v of y.ticks) {
            const py = (B - (v - y.lo) / (y.hi - y.lo) * (B - T)).toFixed(1);
            grid += '<line class="oth-grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + py + '" y2="' + py + '"/><text class="oth-axis" x="' + (L - 4) + '" y="' + py + '" dy="3.5" text-anchor="end">' + esc(fixed(v, y.digits)) + '</text>';
        }
        const span = w.to - w.from, step = [HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR].find(s => span / s <= 5) || 6 * HOUR;
        const offset = new Date(w.to).getTimezoneOffset() * 60000; // local clock hours
        for (let t = Math.ceil((w.from - offset) / step) * step + offset; t <= w.to; t += step) {
            const px = x(t); if (px < L + 12 || px > W - R - 12) continue;
            grid += '<text class="oth-axis" x="' + px.toFixed(1) + '" y="' + (h - 4) + '" text-anchor="middle">' + esc(clock(t)) + '</text>';
        }
        return '<figure class="oth-figure"><svg class="oth-chart" data-oth="' + esc(id) + '" viewBox="0 0 ' + W + ' ' + h + '" role="img" aria-label="' + esc(label) + '">' +
            '<text class="oth-axis" x="2" y="10">' + esc(unit) + '</text>' + grid + body(x, v => B - (v - y.lo) / (y.hi - y.lo) * (B - T), B) +
            '<line class="oth-cross" x1="0" x2="0" y1="' + T + '" y2="' + B + '" visibility="hidden"/></svg><div class="oth-tip" hidden></div></figure>';
    }
    function path(model, w, list, x, y, skipZero) {
        let d = '', pen = false;
        if (list) list.forEach((v, p) => {
            if (v === null || (skipZero && v === 0) || w.at(p) < w.from) { pen = false; return; }
            d += (pen ? 'L' : 'M') + x(w.at(p)).toFixed(1) + ',' + y(v).toFixed(1);
            pen = true;
        });
        return d;
    }
    function legend(items) {
        return '<p class="pd-help oth-legend">' + items.map(i => '<span data-oth-line="' + i[0] + '">' + esc(i[1]) + '</span>').join('') + '</p>';
    }
    function spanText(model, now, w) {
        if (w.full) return uiText("Last 24 hours");
        const minutes = Math.max(1, Math.round((now - Math.max(model.boot, model.start)) / 60000));
        const duration = minutes < 60 ? minutes + ' min' : Math.floor(minutes / 60) + ' h' + (minutes % 60 ? ' ' + minutes % 60 + ' min' : '');
        return uiText("Since the restart {duration} ago").replace('{duration}', duration);
    }
    const between = r => r[0] === r[1] ? fixed(r[0], 1) : fixed(r[0], 1) + '–' + fixed(r[1], 1);
    function mean(list, from, to) {
        let sum = 0, n = 0;
        for (let p = from; p < to; p++) if (list && list[p] !== null && list[p] !== undefined) { sum += list[p]; n++; }
        return n ? sum / n : null;
    }
    // Hourly averages, newest first: the accessible reading of the same data.
    function table(model, w, columns) {
        const offset = new Date(w.to).getTimezoneOffset() * 60000, hours = [];
        for (let p = 0; p < model.n; p++) {
            if (w.at(p) < w.from) continue;
            const hour = Math.floor((w.at(p) - offset) / HOUR) * HOUR + offset;
            if (!hours.length || hours[hours.length - 1].hour !== hour) hours.push({hour, from: p, to: p + 1}); else hours[hours.length - 1].to = p + 1;
        }
        const head = '<tr><th scope="col">' + esc(uiText("Time")) + '</th>' + columns.map(c => '<th scope="col">' + esc(c[0]) + '</th>').join('') + '</tr>';
        const rows = hours.reverse().map(h => '<tr><th scope="row">' + esc(clock(h.hour)) + '</th>' + columns.map(c => {
            // Requests: the average while heat was requested; "off" when none was.
            const v = mean(c[2] === 'request' ? c[1].map(x => x === 0 ? null : x) : c[1], h.from, h.to);
            const off = v === null && c[2] === 'request' && c[1].slice(h.from, h.to).includes(0);
            return '<td>' + (off ? esc(uiText("off")) : v === null ? '–' : esc(c[2] === 'pct' ? Math.round(v) + ' %' : fixed(v, 1) + ' °C')) + '</td>';
        }).join('') + '</tr>').join('');
        return '<details class="ot-advanced oth-table"><summary>' + esc(uiText("Show as table (hourly averages)")) + '</summary>' +
            '<div class="oth-scroll"><table class="table table-sm"><thead>' + head + '</thead><tbody>' + rows + '</tbody></table></div></details>';
    }
    function register(id, model, w, W, rows) { charts[id] = {model, w, W, rows}; }

    // A room card's chart: measured temperature and the effective target.
    function room(model, id, name, now) {
        const r = model && model.rooms[id];
        now = now || Date.now();
        if (!r) return '';
        const w = window_(model, now);
        const t = visible(model, w, r.temperature), s = visible(model, w, r.target);
        const tr = range([t]), all = range([t, s]);
        if (!all || t.filter(v => v !== null).length + s.filter(v => v !== null).length < 2) return '';
        const sr = range([s]), y = scale(all[0], all[1], 2);
        let summary = spanText(model, now, w) + ': ' + (tr ? uiText("measured {range} °C").replace('{range}', between(tr)) : uiText("no measurement"));
        if (sr) summary += ', ' + uiText("target {range} °C").replace('{range}', between(sr));
        summary += '.';
        const key = 'room:' + id;
        register(key, model, w, 220, p => [[uiText("Measured"), t[p], '°C'], [uiText("Target"), s[p], '°C']]);
        return '<div class="oth" data-oth-chart="room">' + frame(key, w, 220, 120, y, (name ? name + ': ' : '') + summary, (x, py) =>
            '<path class="oth-line oth-target" d="' + path(model, w, s, x, py) + '"/><path class="oth-line oth-measured" d="' + path(model, w, t, x, py) + '"/>', '°C') +
            legend([['measured', uiText("Measured")], ['target', uiText("Target")]]) +
            '<p class="pd-help oth-summary">' + esc(summary) + ' ' + esc(uiText("Kept in the E32's memory since the last restart.")) + '</p>' +
            table(model, w, [[uiText("Measured"), t], [uiText("Target"), s]]) + '</div>';
    }

    // The boiler panel: flow, return and both requests on one °C axis; the burner on its own strip.
    function boiler(model, now) {
        now = now || Date.now();
        if (!model) return '';
        const w = window_(model, now);
        // Panel width at render time (each poll): about 1:1 on a phone, at most 600 wide.
        const BW = typeof innerWidth === 'number' && innerWidth > 0 ? Math.round(Math.max(260, Math.min(600, innerWidth - 60))) : 600;
        const flow = visible(model, w, model.flow), ret = visible(model, w, model.ret), burner = visible(model, w, model.burner);
        const request = visible(model, w, model.request), thermostat = visible(model, w, model.thermostat);
        const positive = list => list && list.map(v => v === 0 ? null : v);
        const all = range([flow, ret, positive(request), positive(thermostat)]);
        const fr = range([flow]), br = range([burner]);
        if (!all && !br) return '';
        let summary = spanText(model, now, w) + ': ' + (fr ? uiText("flow {range} °C").replace('{range}', between(fr)) : uiText("no flow temperature"));
        const on = mean(burner, 0, model.n);
        if (on !== null) summary += ', ' + uiText("burner on {pct} % of the time").replace('{pct}', Math.round(on));
        summary += '.';
        const items = [['flow', uiText("Flow"), flow], ['return', uiText("Return"), ret], ['request', uiText("E32 request"), request], ['thermostat', uiText("Thermostat request"), thermostat]]
            .filter(i => range([i[0] === 'request' || i[0] === 'thermostat' ? positive(i[2]) : i[2]]));
        register('boiler', model, w, BW, p => items.map(i => [i[1], i[2][p] === 0 && (i[0] === 'request' || i[0] === 'thermostat') ? uiText("off") : i[2][p], '°C'])
            .concat(burner ? [[uiText("Burner on"), burner[p], '%']] : []));
        let html = '<div class="oth" data-oth-chart="boiler"><h3 class="oth-title">' + esc(uiText("Boiler history")) + '</h3>';
        if (all) html += frame('boiler', w, BW, 170, scale(all[0], all[1], 10), summary, (x, py) => items.map(i =>
            '<path class="oth-line oth-' + i[0] + '" d="' + path(model, w, i[2], x, py, i[0] === 'request' || i[0] === 'thermostat') + '"/>').join(''), '°C') +
            legend(items.map(i => [i[0], i[1]]));
        if (br) {
            // One path of bars: the share of each 5 minutes with the burner on.
            const strip = {lo: 0, hi: 100, ticks: [0, 100], digits: 0};
            html += frame('burner', w, BW, 64, strip, uiText("Burner on") + ': ' + Math.round(on) + ' %', (x, py, base) => {
                let d = ''; const width = Math.max(0.6, (x(w.from + model.period) - x(w.from)) - 0.4);
                burner.forEach((v, p) => { if (v) d += 'M' + (x(w.at(p)) - width / 2).toFixed(1) + ',' + base + 'V' + py(v).toFixed(1) + 'h' + width.toFixed(1) + 'V' + base + 'z'; });
                return '<path class="oth-bars" d="' + d + '"/>';
            }, '%') + '<p class="pd-help oth-legend"><span data-oth-line="burner">' + esc(uiText("Burner on (share of each 5 minutes)")) + '</span></p>';
            register('burner', model, w, BW, p => [[uiText("Burner on"), burner[p], '%']]);
        }
        return html + '<p class="pd-help oth-summary">' + esc(summary) + ' ' + esc(uiText("Kept in the E32's memory since the last restart.")) + '</p>' +
            table(model, w, items.map(i => [i[1], i[2], i[0] === 'request' || i[0] === 'thermostat' ? 'request' : '']).concat(burner ? [[uiText("Burner on"), burner, 'pct']] : [])) + '</div>';
    }

    // Crosshair and tooltip: one delegated listener for every chart on the page.
    function hover(event) {
        const leaving = event.type === 'pointerleave';
        if (leaving && !(event.target && event.target.matches && event.target.matches('svg[data-oth]'))) return;
        const svg = leaving ? null : event.target && event.target.closest ? event.target.closest('svg[data-oth]') : null;
        document.querySelectorAll('.oth-tip:not([hidden])').forEach(tip => { if (!svg || tip.previousElementSibling !== svg) { tip.hidden = true; tip.previousElementSibling.querySelector('.oth-cross').setAttribute('visibility', 'hidden'); } });
        const chart = svg && charts[svg.getAttribute('data-oth')];
        if (!chart) return;
        const box = svg.getBoundingClientRect(), vx = (event.clientX - box.left) / box.width * chart.W;
        const t = chart.w.from + (vx - L) / (chart.W - L - R) * (chart.w.to - chart.w.from);
        let best = -1;
        for (let p = 0; p < chart.model.n; p++) if (chart.w.at(p) >= chart.w.from && (best < 0 || Math.abs(chart.w.at(p) - t) < Math.abs(chart.w.at(best) - t))) best = p;
        if (best < 0) return;
        const at = chart.w.at(best), px = L + (at - chart.w.from) / (chart.w.to - chart.w.from) * (chart.W - L - R);
        const cross = svg.querySelector('.oth-cross'), tip = svg.nextElementSibling;
        cross.setAttribute('x1', px.toFixed(1)); cross.setAttribute('x2', px.toFixed(1)); cross.setAttribute('visibility', 'visible');
        tip.textContent = '';
        const head = document.createElement('strong'); head.textContent = clock(at); tip.append(head);
        for (const [label, value, unit] of chart.rows(best)) {
            const line = document.createElement('span');
            line.textContent = label + ': ' + (value === null || value === undefined ? '–' : typeof value === 'string' ? value : unit === '%' ? Math.round(value) + ' %' : fixed(value, 1) + ' °C');
            tip.append(line);
        }
        tip.hidden = false;
        tip.style.left = Math.min(Math.max(px / chart.W * 100, 18), 82) + '%';
    }
    if (typeof document !== 'undefined') {
        document.addEventListener('pointermove', hover);
        document.addEventListener('pointerdown', hover);
        document.addEventListener('pointerleave', hover, true);
    }
    window.OpenThermostatHistory = Object.freeze({parse, room, boiler});
})();
