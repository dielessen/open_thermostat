/* The Overview's house card (OpenThermostat, E32 rc.5): the house at a glance, from Home Assistant alone.

   One wide card on top of the Overview (dashboard.py, room_overview.HOUSE_CARD_TYPE). A band in the full colour of
   what the boiler does now, its words in white ("Heating · water 41 °C" in orange, hot water in blue, "Boiler
   resting" in grey; "Attention: …" in red while there is a problem, a tap leads to Repairs and "All reasons" lists
   them) with the house mode as a chip on it; under it today's figures, large, between thin lines, two by two on a
   phone and in one row on a wide card: the one room that is switched on (when the house has exactly one) with its
   target, hot water, gas today with its last 7 days beside it and the average day under it, and burner starts
   today (heating too while the band shows a problem, which then cannot say it); then the day so far, a strip from
   midnight to now (heating, hot water, keeping warm) with the hours and "now" under it. The layout, sizes and
   spacing are the owner's sketch (rc.5 design, Main/Overzicht-donker/Overzicht-desktop).
   HA 1.0.0rc7 completes the desktop sketch: the band also says the burner power and the boiler's display code
   ("burner 37 % · code -H"; on a wide card on its right before the house mode chip, on a phone under the words), the
   hot water figure its temperature ("water 65 °C") and the burner starts how many came in the last hour; each only
   while its entity is in the card's config (modulation, code, dhw, starts_hour) and has a value.

   Only Home Assistant is read: the states of the entities in the card's config, the boiler activity since
   midnight (history/history_during_period: again when the activity changes, at most every 5 minutes; the
   changes in between come from the state itself) and the statistics of gas and burner starts (the 7 whole days
   before today by recorder/statistics_during_period, today by recorder/statistic_during_period as Home Assistant's own
   statistic card asks it; at most every 10 minutes and when the day changes). Nothing talks to the E32. "Today"
   is the house's day (Home Assistant's time zone), the day of the E32's own counters and of the statistics.

   The same module draws the Learning view's "Yesterday in figures" (custom:openthermostat-yesterday,
   room_overview.YESTERDAY_CARD_TYPE): the scoreboard's four headline figures, two by two and large as the sketch
   (Leren), each from its own sensor (scoreboard.py): the lead room warm on time, burner starts per heating hour, gas
   for heating and the degree-days. It reads states only.

   The words are the integration's translations (strings.json entity.sensor.heat_request.state_attributes.card,
   the Yesterday figures' own short labels there too, and the room's sentence entity.sensor.room_reason as on the room status card), so every
   viewer reads them in their own Home Assistant language; English is only the last resort. The band wears Home
   Assistant's theme colours (deep orange, blue, grey, the error colour) darkened until white words on it read at
   4.5:1 at least, in the light and the dark theme; the day strip and the gas line wear the same hues, a little
   darker on a light card so they stand out from it (3:1). */
const PREFIX = 'component.open_thermostat.entity.sensor.';
const CARD = 'heat_request.state_attributes.card.state.';
const TEXT = {title: 'Your house', heating: 'Heating', status_heating: 'Heating · water {flow} °C', status_heating_plain: 'Heating',
 heating_on: 'on · water {flow} °C', heating_on_plain: 'on', heating_off: 'off', request: 'Boiler request {flow} °C',
 no_request: 'No boiler request', wants: '{n} rooms want heat', wants_one: '1 room wants heat', hot_water: 'Hot water',
 taps: '{n} taps today', taps_one: '1 tap today', taps_none: 'no taps yet today', running: 'running now', gas_today: 'Gas today',
 week: 'Last 7 days: {values}', starts_today: 'Burner starts today', idle: 'Boiler resting', attention: 'Attention: {reason}',
 all_reasons: 'All reasons', mode: 'House mode: {mode}', today: 'Today', legend_heating: 'Heating', legend_hot_water: 'Hot water',
 legend_keep_warm: 'Keeping warm', waiting: 'The E32 is not reporting.', now: 'now', warm: '{room} was warm', early: '{m} min early',
 late: '{m} min late', on_time: 'on time', degree_days: 'Degree-days', target: 'target {t} °C', per_day: 'On average {value} a day (last {n} days)',
 today_since: 'Today since midnight', burner: 'burner {n} %', code: 'code {code}', water: 'water {t} °C',
 last_hour: '{n} in the last hour', would_ask: 'E32 would ask {flow} °C', no_wish: 'The E32 would not ask for heat',
 tap_open: 'Hot water: tap open', keeping_warm: 'Keeping hot water warm', gas_estimate: 'Gas today (estimate)',
 no_warmup: 'no warm-up yesterday', late_hours: '{h} h {m} min late', early_hours: '{h} h {m} min early',
 not_warm: 'not warm within 3 h', yesterday_starts: 'Burner starts per heating hour',
 yesterday_heating: 'Heating energy (estimate)'};
// The warm-on-time sensor's value for a room that did not get warm within 3 hours (the firmware's ArrivalLearner cap).
const NOT_WARM_MIN = 180;
const DASH = '—';  // a figure not known yet: the same in every language
const NBSP = '\u00a0';
// What the boiler does (boiler_activity, heating_link.BOILER_ACTIVITIES): the kind in the strip and the status tone.
const KIND = {heating: 'heat', tapping: 'water', hot_water: 'water', keep_warm: 'keep', charging: 'keep', idle: 'rest'};
const RUNNING = new Set(['tapping', 'hot_water']);  // a tap runs (not "charging": the tank is heated)
const ICON = {heat: 'mdi:fire', water: 'mdi:faucet', keep: 'mdi:water-thermometer', rest: 'mdi:water-boiler',
 error: 'mdi:alert-circle-outline', wait: 'mdi:timer-sand'};
const LEGEND = [['heat', 'legend_heating'], ['water', 'legend_hot_water'], ['keep', 'legend_keep_warm']];
const ACTIVITY_EN = {idle: 'Idle', heating: 'Heating', tapping: 'Tapping', keep_warm: 'Keeping warm', charging: 'Heating the hot water tank',
 hot_water: 'Hot water'};
// The room, as the room status card shows it (room-status-card.js): the tone and icon of each reason.
const ROOM_TONE = {warm_up: 'heat', heating: 'heat', wants_heat: 'heat', boost: 'heat', away_return: 'heat', window_open: 'warn',
 window_pending: 'warn', no_measurement: 'error', hot_water: 'info', boiler_pause: 'info', temporary: 'info', holiday: 'away', away: 'away',
 room_away: 'away', house_away: 'away', warm_enough: 'ok', off: 'off'};
// Sentences that only repeat the figure above them ("Heating: 20.4 → 21 °C"): the reason's short word instead.
const RESTATED = new Set(['heating', 'wants_heat', 'warm_enough']);
// Sentences with a target of their own (room_overview.LINES with "target"): no "target X °C" in front of them, which
// would say a figure twice, or two different ones during a warm-up.
const OWN_TARGET = new Set(['warm_up', 'holiday', 'away', 'room_away', 'house_away', 'temporary', 'temporary_until']);
const PRESENCE = {room_home: 'mdi:account-check', room_away: 'mdi:account-off-outline', house_home: 'mdi:home-account',
 house_away: 'mdi:home-export-outline'};
const HISTORY_MS = 5 * 60000, STATS_MS = 10 * 60000, TICK_MS = 60000, DAY_MS = 86400000, PENDING_MS = 2 * 60000;

// The house card, as the sketch: on a phone 12 px labels, 30 px bold numbers with 18 px muted units, 12 px muted lines
// under them; from 720 px of card 13 px and 34 px with more room. 1 px lines between the figures are shadows that the
// grid's edge cuts off, so they never double at the card's border. Colours: the theme's (deep orange, blue, grey, the
// error colour); the band darker until white reads at 4.5:1, the strip and the gas line a little darker on a light
// card (3:1 against it), the theme's own on a dark one.
const STYLE = `:host{display:block}
ha-card{display:block;overflow:hidden;color:var(--primary-text-color);
--oth-surface:var(--ha-card-background,var(--card-background-color,#fff));--oth-muted:var(--secondary-text-color,#6b6b6b);
--oth-line:var(--divider-color,rgba(127,127,127,.22));--oth-track:color-mix(in srgb,var(--primary-text-color,#212121) 8%,var(--oth-surface));
--heat:var(--deep-orange-color,#ff6f22);--water:var(--blue-color,#2196f3);--grey:var(--grey-color,#9e9e9e);
--error:var(--error-color,#db4437);--info:var(--info-color,#039be5);--warn:var(--warning-color,#ffa600);--ok:var(--success-color,#43a047);
--away:var(--state-climate-cool-color,#2b9af9);--off:var(--disabled-text-color,#9e9e9e);
--band-heat:color-mix(in srgb,var(--heat) 75%,#000);--band-water:color-mix(in srgb,var(--water) 78%,#000);
--band-rest:color-mix(in srgb,var(--grey) 72%,#000);--band-error:color-mix(in srgb,var(--error) 88%,#000);
--mark-heat:color-mix(in srgb,var(--heat) 85%,#000);--mark-water:color-mix(in srgb,var(--water) 85%,#000);
--mark-keep:color-mix(in srgb,var(--mark-water) 50%,var(--oth-surface))}
ha-card.dark{--mark-heat:var(--heat);--mark-water:var(--water);--mark-keep:color-mix(in srgb,var(--water) 45%,#fff)}
.wrap{container:house/inline-size}
p{margin:0}
.tone-heat{--tone:var(--heat);--band:var(--band-heat)}.tone-water,.tone-keep{--tone:var(--water);--band:var(--band-water)}
.tone-rest,.tone-wait{--tone:var(--grey);--band:var(--band-rest)}.tone-error{--tone:var(--error);--band:var(--band-error)}
[data-focus]:focus{outline:none}[data-focus]:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:-3px}
.status{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;padding:12px 16px;background:var(--band);color:#fff}
.main{display:flex;align-items:center;gap:10px;flex:1 1 0;min-width:min(100%,200px);border-radius:6px}
.main>ha-icon{--mdc-icon-size:22px;color:#fff;display:flex;flex:none}.words{flex:1 1 auto;min-width:0}
.line{font-size:16px;font-weight:500;line-height:1.3;overflow-wrap:anywhere}
.sub{margin-top:1px;font-size:12px;line-height:1.35;overflow-wrap:anywhere}
.main[role=link]{cursor:pointer}.main[role=link]:hover .line{text-decoration:underline}
.go{--mdc-icon-size:20px;display:flex;flex:none;color:#fff}
.chip{display:inline-flex;align-items:center;gap:6px;min-height:28px;margin-left:auto;padding:0 10px;border-radius:16px;box-sizing:border-box;
border:1px solid rgba(255,255,255,.6);background:rgba(0,0,0,.2);color:#fff;font:inherit;font-size:12px;font-weight:500;cursor:pointer;
white-space:nowrap;--mdc-icon-size:16px}
.chip ha-icon{color:#fff;display:flex}
.boiler{order:1;flex:1 1 100%;margin:-4px 0 0 32px;font-size:12px;line-height:1.35;color:#fff;overflow-wrap:anywhere}
.status [data-focus]:focus-visible{outline:2px solid #fff;outline-offset:2px}
.reasons{padding:8px 16px 10px;border-bottom:1px solid var(--oth-line)}
.reasons summary{cursor:pointer;font-size:14px;font-weight:500;padding:4px 0;min-height:24px}
.reasons ul{margin:4px 0 0;padding-left:20px}.reasons li{margin:0 0 4px;font-size:14px;line-height:1.45;overflow-wrap:anywhere}
.reasons [data-focus]:focus-visible{outline-offset:2px}
.figures{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));overflow:hidden}
.figure{display:flex;flex-direction:column;min-width:0;padding:14px 16px 12px;box-shadow:1px 0 0 var(--oth-line),0 1px 0 var(--oth-line)}
.figure.top{padding-top:16px}.p2{grid-column:span 2}
.label{display:flex;align-items:center;gap:6px;font-size:12px;line-height:1.3;color:var(--oth-muted);overflow-wrap:anywhere}
.value{font-size:18px;line-height:1.05;overflow-wrap:anywhere}
.value .num{font-size:30px;font-weight:700}.value .unit{font-weight:400;color:var(--oth-muted)}
.value.words{margin-top:4px;font-weight:600;line-height:1.3;text-wrap:balance}
.value.unknown{font-size:30px;color:var(--oth-muted)}
.note{margin-top:4px;font-size:12px;line-height:1.35;color:var(--oth-muted);overflow-wrap:anywhere;text-wrap:pretty}
.room{cursor:pointer}.room .label ha-icon{--mdc-icon-size:16px;display:flex}.room .label .on{color:var(--ok)}.room .label .warn{color:var(--warn)}
.running{display:flex;align-items:center;gap:6px}.running::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--mark-water);flex:none}
.trend{display:flex;flex-wrap:wrap;align-items:flex-end;gap:4px 10px}.trend .value{flex:none}
.spark{display:block;flex:1 1 56px;min-width:56px;max-width:84px;height:auto;overflow:visible;margin-bottom:2px}
.spark path{fill:none;stroke:var(--mark-heat);stroke-width:2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.spark path.partial{stroke-opacity:.45}.spark circle{fill:var(--mark-heat)}
.today{display:grid;grid-template-columns:minmax(0,1fr);grid-template-areas:"title" "strip" "ticks" "legend";padding:10px 16px 14px;
border-top:1px solid var(--oth-line)}
.today-title{grid-area:title;margin-bottom:6px;font-size:12px;color:var(--oth-muted)}
.legend{grid-area:legend;display:flex;flex-wrap:wrap;gap:2px 12px;margin:6px 0 0;padding:0;list-style:none;font-size:12px;color:var(--oth-muted)}
.legend li{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}.legend i{width:8px;height:8px;border-radius:50%;flex:none}
.legend .heat{background:var(--mark-heat)}.legend .water{background:var(--mark-water)}.legend .keep{background:var(--mark-keep)}
.strip{grid-area:strip;position:relative;height:10px;margin:4px 0}
.strip::before{content:"";position:absolute;inset:0;border-radius:5px;background:var(--oth-track);opacity:.55}
.seg{position:absolute;top:0;bottom:0;min-width:2px;background:var(--oth-track)}
.seg.first{border-radius:5px 0 0 5px}.seg.last{border-radius:0 5px 5px 0}.seg.first.last{border-radius:5px}
.seg.heat,.seg.water,.seg.keep{z-index:1;min-width:6px}
.seg.heat::after,.seg.water::after,.seg.keep::after{content:"";position:absolute;inset:0;border-radius:5px;background:var(--fill)}
.seg.heat{--fill:var(--mark-heat)}.seg.water{--fill:var(--mark-water)}.seg.keep{--fill:var(--mark-keep)}.seg.gap::after{left:2px}
.ticks{grid-area:ticks;position:relative;height:16px;margin-top:2px;font-size:12px;line-height:16px;color:var(--oth-muted);font-variant-numeric:tabular-nums}
.ticks span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}.ticks span:first-child,.ticks .now.start{transform:none}
.ticks .now.end{transform:translateX(-100%)}
@container house (max-width:340px){.main{flex-basis:100%}.chip{margin-left:32px}.status{padding:12px}.figure,.figure.top{padding-left:12px;padding-right:12px}.today{padding:10px 12px 12px}
.reasons{padding:8px 12px 10px}}
@container house (min-width:720px){.status{gap:8px 12px;padding:14px 22px}.main{gap:12px}.main>ha-icon{--mdc-icon-size:24px}
.line{font-size:18px}.sub,.chip,.boiler{font-size:13px}
.boiler{order:0;flex:0 1 auto;margin:0 0 0 auto;text-align:right}.boiler+.chip{margin-left:0}
.figures{grid-template-columns:repeat(var(--n,4),minmax(0,1fr))}.p2{grid-column:auto}.figure,.figure.top{padding:20px 22px}
.label,.note,.today-title,.legend,.ticks{font-size:13px}.note{margin-top:6px}.value .num,.value.unknown{font-size:34px}
.trend{gap:4px 12px}.spark{flex:1 1 64px;min-width:64px;max-width:110px}.reasons{padding:8px 22px 10px}
.today{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"title legend" "strip strip" "ticks ticks";padding:10px 22px 16px}
.legend{margin:0 0 6px;justify-content:flex-end}}`;

// Yesterday in figures, as the sketch (Leren): two by two, a 12 px muted label over a 22 px bold value, the values of a
// row on one line (a label of two lines stands higher); 13 px and more room from 420 px of card.
const YESTERDAY_STYLE = `:host{display:block}
ha-card{display:block;color:var(--primary-text-color);--oth-muted:var(--secondary-text-color,#6b6b6b)}
.wrap{container:yesterday/inline-size}
p{margin:0}
.figures{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;padding:14px 16px}
.figure{display:flex;flex-direction:column;justify-content:flex-end;min-width:0;border-radius:6px}.p2{grid-column:span 2}
.label{font-size:12px;line-height:1.3;color:var(--oth-muted);overflow-wrap:anywhere}
.value{font-size:22px;font-weight:700;line-height:1.15;overflow-wrap:anywhere}.value.unknown{font-weight:400;color:var(--oth-muted)}
[role=button]{cursor:pointer}[data-focus]:focus{outline:none}
[data-focus]:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}
@container yesterday (min-width:420px){.figures{gap:14px 20px;padding:16px 18px}.label{font-size:13px}}`;

const locale = hass => hass?.locale?.language || hass?.language || 'en';
// The viewer's 12/24-hour choice in Home Assistant (profile → time format); else the language's.
const hour12 = hass => {
 const chosen = ({'12': true, '24': false})[hass?.locale?.time_format];
 if (chosen !== undefined) return chosen;
 try { return /h1[12]/.test(new Intl.DateTimeFormat(locale(hass), {hour: 'numeric'}).resolvedOptions().hourCycle); } catch (e) { return false; }
};
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
const finite = value => typeof value === 'number' && Number.isFinite(value);
const numeric = value => { const n = typeof value === 'string' && value.trim() !== '' ? Number(value) : value; return finite(n) ? n : null; };
// A figure and its unit stay on one line ("41 °C" is never cut into "41" and "°C" on a phone).
const together = text => typeof text === 'string' ? text.replace(/ (°C|m³|kWh|%)/g, NBSP + '$1') : text;
const known = st => !!st && typeof st.state === 'string' && !['unknown', 'unavailable', ''].includes(st.state);
const entityId = value => typeof value === 'string' && value.includes('.') ? value : undefined;
const SVG = 'http://www.w3.org/2000/svg';
const make = (tag, attrs = {}, text) => {
 const e = tag.startsWith('svg:') ? document.createElementNS(SVG, tag.slice(4)) : document.createElement(tag);
 for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined && v !== false) e.setAttribute(k, v);
 if (text !== undefined) e.textContent = text;
 return e;
};
const icon = (name, attrs = {}) => make('ha-icon', {icon: name, ...attrs});
// A figure's value: its number large, the words and the unit around it small and muted ("3 taps today", "Pobory dziś: 3",
// "2.0 m³"); words without the number ("off", "no taps yet today") a size smaller; "—" while it is not known.
const valueOf = (text, num) => {
 const value = make('p', {class: 'value'});
 if (text === null) { value.classList.add('unknown'); value.textContent = DASH; return value; }
 const at = typeof num === 'string' && num ? text.indexOf(num) : -1;
 if (at < 0) { value.classList.add('words'); value.textContent = text; return value; }
 if (at > 0) value.append(make('span', {class: 'unit'}, text.slice(0, at)));
 value.append(make('span', {class: 'num'}, num));
 if (at + num.length < text.length) value.append(make('span', {class: 'unit'}, text.slice(at + num.length)));
 return value;
};

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

// The last 7 days as a line beside today's gas, as the sketch (84 × 30 on a phone, drawn larger on a wide card):
// points [{i: 0..6, v}] (6: today), scaled to their own range (the shape is the point). Today is a day still running:
// the step to it is drawn lighter, its dot solid. A 2 px line, the end dot r = 3.
function sparkline(points, label) {
 const W = 84, H = 30, PX = 4, PY = 5, values = points.map(p => p.v), low = Math.min(...values), high = Math.max(...values);
 const x = i => PX + i * (W - 2 * PX) / 6, y = v => high > low ? H - PY - (v - low) / (high - low) * (H - 2 * PY) : H / 2;
 const svg = make('svg:svg', {class: 'spark', width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': label});
 svg.append(make('svg:title', {}, label));
 const at = p => x(p.i).toFixed(1) + ',' + y(p.v).toFixed(1), last = points[points.length - 1];
 const done = points.filter(p => p.i < 6);
 let d = '';
 done.forEach((p, k) => { d += (k && p.i === done[k - 1].i + 1 ? 'L' : 'M') + at(p); });
 if (d) svg.append(make('svg:path', {d, 'data-days': done.length}));
 const before = done[done.length - 1];
 if (last.i === 6 && before?.i === 5) svg.append(make('svg:path', {class: 'partial', d: 'M' + at(before) + 'L' + at(last)}));
 svg.append(make('svg:circle', {cx: x(last.i).toFixed(1), cy: y(last.v).toFixed(1), r: 3}));
 return svg;
}

// What both cards share: Home Assistant's states, the integration's words and the viewer's number format.
class OpenThermostatCard extends HTMLElement {
 st(id) { return id ? this._hass?.states?.[id] || null : null; }
 // A text of the cards (strings.json …heat_request.state_attributes.card), its {placeholders} filled; English as the last resort.
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
 moreInfo(entityId) { this.dispatchEvent(new CustomEvent('hass-more-info', {bubbles: true, composed: true, detail: {entityId}})); }
 // One figure: its label, its value (number large) and what follows under it.
 figure(key, label, text, num, extra) {
  const box = make('div', {class: 'figure', 'data-figure': key});
  box.append(make('p', {class: 'label'}, label), valueOf(text, num));
  if (extra) box.append(extra);
  return box;
 }
}

class OpenThermostatHouse extends OpenThermostatCard {
 constructor() {
  super(); this.attachShadow({mode: 'open'});
  this._key = null; this._gen = 0; this._timer = null; this._open = false; this._resize = null;
  this.reset();
 }
 reset() {
  this._history = null; this._live = []; this._stats = null; this._changed = false; this._seen = undefined; this._seenAt = undefined;
  this._fetched = {history: 0, day: null, stats: 0, statsDay: null}; this._pending = {history: 0, stats: 0};
 }
 setConfig(config) {
  const id = entityId;
  if (!config || !(id(config.request) || id(config.activity)))
   throw new Error('This card needs the "Boiler request (E32)" or "Boiler activity" sensor of OpenThermostat (request: sensor.…, activity: sensor.…); the OpenThermostat dashboard adds it for you.');
  const gas = (Array.isArray(config.gas) ? config.gas : [config.gas]).filter(id);
  const rooms = (Array.isArray(config.rooms) ? config.rooms : []).filter(room => room && id(room.entity)).slice(0, 1);
  this._config = {request: id(config.request), activity: id(config.activity), heating: id(config.heating), flow: id(config.flow),
   hot_water: id(config.hot_water), taps: id(config.taps), gas, starts: id(config.starts), mode: id(config.mode),
   problem: id(config.problem), rooms, modulation: id(config.modulation), code: id(config.code), dhw: id(config.dhw),
   starts_hour: id(config.starts_hour)};
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
  // A new width (a phone turned, another column) places the hour marks around "now" again; nothing is asked.
  if (!this._resize && typeof ResizeObserver === 'function') this._resize = new ResizeObserver(() => this.fitTicks());
  this._resize?.observe(this);
 }
 disconnectedCallback() {
  clearInterval(this._timer); this._timer = null;
  this._gen++;  // what is still on its way is dropped when it comes
  this._pending = {history: 0, stats: 0};
  this._resize?.disconnect();
 }
 getCardSize() { return 5; }
 getGridOptions() { return {columns: 12, min_columns: 12}; }
 entities() {
  const c = this._config;
  return [c.request, c.activity, c.heating, c.flow, c.hot_water, c.taps, ...c.gas, c.starts, c.mode, c.problem, c.rooms[0]?.entity,
   c.modulation, c.code, c.dhw, c.starts_hour].filter(Boolean);
 }
 degrees(value) { return this.number(Math.round(value)); }
 time(ms) { return clockTime(this._hass, ms); }
 // 10: a temperature line in the entity's own unit (Home Assistant converts a °C sensor for an imperial house).
 inUnit(text, id) {
  const unit = this.st(id)?.attributes?.unit_of_measurement;
  return typeof unit === 'string' && unit && unit !== '°C' && typeof text === 'string' ? text.replace('°C', unit) : text;
 }
 // Whether the E32 drives the boiler: not in the trial run, nor before the takeover is confirmed (as the Now card).
 driving() {
  const a = this.st(this._config.request)?.attributes || {};
  return a.mode !== 'shadow' && a.control !== 'awaiting_confirmation';
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
  // The 7 whole days before today (the average day under the gas) and today; the line shows the last 7 of them.
  const days = Array.from({length: 8}, (_, i) => midnight(day, zone, i - 7));
  try {
   // Each read on its own: a failing 7-day read keeps today's answers, and the other way round.
   const [week, ...today] = await Promise.all([
    hass.callWS({type: 'recorder/statistics_during_period', start_time: new Date(days[0]).toISOString(), period: 'day',
     statistic_ids: ids, types: ['change']}).catch(() => null),
    ...ids.map(id => hass.callWS({type: 'recorder/statistic_during_period', statistic_id: id, calendar: {period: 'day'},
     types: ['change']}).catch(() => null))]);
   if (gen !== this._gen) return;
   if (week === null && today.every(answer => answer === null)) throw new Error('no statistics');
   const per = {};
   for (const id of ids) {
    const values = Array(8).fill(null);
    for (const row of Array.isArray(week?.[id]) ? week[id] : []) {
     const start = typeof row?.start === 'number' ? row.start : Date.parse(row?.start), change = numeric(row?.change);
     const i = days.findIndex(d => Math.abs(d - start) < DAY_MS / 2);
     if (i >= 0 && change !== null) values[i] = change;
    }
    // Today to the last 5 minutes, as the statistic cards on the Boiler tab. Home Assistant can answer the day's change
    // with the running total of a total-increasing sensor (no sum found before midnight, e.g. just after a restart while
    // the recorder catches up: the demo once showed 28.6 m³ and 173 starts "today"). More than the 7 days before and
    // today together is no day's change: today's own row of the 7-day read stands instead (the hourly statistics).
    const now = numeric(today[ids.indexOf(id)]?.change);
    const before = values.slice(0, 7).filter(v => v !== null), all = values.filter(v => v !== null).reduce((a, b) => a + b, 0);
    if (now !== null && !(before.length && now > all + 1e-6)) values[7] = now;
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
  const values = ids.map(id => per?.[id]?.[7]).filter(v => v !== null && v !== undefined);
  return values.length ? values.reduce((a, b) => a + b, 0) : null;
 }

 // -- what the card says ---------------------------------------------------------------------------------------------
 // Heating now: the boiler activity, else the boiler's own heating bit, else the E32's request (null: not known).
 heatingOn() {
  const c = this._config, activity = this.st(c.activity), heating = this.st(c.heating), request = this.st(c.request);
  if (known(activity)) return activity.state === 'heating';
  if (known(heating)) return heating.state === 'on';
  return known(request) && numeric(request.state) !== null && this.driving() ? numeric(request.state) > 0 : null;
 }
 flow() { const st = this.st(this._config.flow); return known(st) ? numeric(st.state) : null; }
 // The band's tone, icon and line: a problem wins; then what the boiler does; without it the boiler's bits or the request.
 status() {
  const c = this._config, problem = this.st(c.problem), activity = this.st(c.activity), flow = this.flow();
  const heating = () => flow !== null ? this.inUnit(this.t('status_heating', {flow: this.degrees(flow)}), c.flow) : this.t('status_heating_plain');
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
   // The glossary's words for hot water: a tap open, keeping hot water warm; heating the tank in the activity's own.
   const words = {tapping: 'tap_open', hot_water: 'hot_water', keep_warm: 'keeping_warm'}[activity.state];
   return {tone: kind, icon: ICON[kind], line: words ? this.t(words) : this.stateText(activity) || ACTIVITY_EN[activity.state]};
  }
  const bit = this.st(c.heating), water = this.st(c.hot_water);
  if (bit?.state === 'on') return {tone: 'heat', icon: ICON.heat, line: heating()};
  if (water?.state === 'on') return {tone: 'water', icon: ICON.water, line: this.t('hot_water')};
  if (bit?.state === 'off' && (!water || water.state === 'off')) return {tone: 'rest', icon: ICON.rest, line: this.t('idle')};
  // Nothing from the boiler itself: the E32's request. In the trial run the old thermostat runs the boiler, so the band
  // stays grey and says what the E32 would ask.
  const request = this.st(c.request), value = known(request) ? numeric(request.state) : null, driving = this.driving();
  const asked = key => this.inUnit(this.t(key, {flow: this.degrees(value)}), c.request);
  if (value !== null && value > 0) return driving ? {tone: 'heat', icon: ICON.heat, line: asked('request'), fromRequest: true}
   : {tone: 'rest', icon: ICON.rest, line: asked('would_ask'), fromRequest: true};
  if (value !== null) return {tone: 'rest', icon: ICON.rest, line: this.t(driving ? 'no_request' : 'no_wish'), fromRequest: true};
  return {tone: 'wait', icon: ICON.wait, line: this.t('waiting')};
 }
 // A value of an entity in the config, or null (missing, unknown, not a number).
 value(id) { const st = this.st(id); return known(st) ? numeric(st.state) : null; }
 // The boiler in a few words, as the sketch: its burner power and its display code ("burner 37 % · code -H"); the
 // code's meaning in the tooltip. Each part only while it has a value; null without either.
 boilerWords() {
  const c = this._config, parts = [], power = this.value(c.modulation), code = this.st(c.code);
  let title = '';
  if (power !== null) parts.push(['power', this.t('burner', {n: this.number(Math.max(0, Math.min(100, Math.round(power))))})]);
  const text = known(code) ? code.state.replace(/[\s.]/g, '') : '';
  if (text && text !== '--') {
   // A fault's cause number with it, as the Boiler tab's Now card ("3L 214"); normal operation the code alone.
   const a = code.attributes || {}, severity = typeof a.severity === 'string' ? a.severity : null;
   const cause = Number.isInteger(a.cause) && severity && severity !== 'normal' ? ' ' + a.cause : '';
   parts.push(['code', this.t('code', {code: text + cause})]);
   title = typeof a.meaning === 'string' ? a.meaning.trim() : '';
  }
  if (!parts.length) return null;
  const box = make('p', {class: 'boiler', 'data-boiler': '', title: title || null});
  parts.forEach(([key, words], i) => box.append(...(i ? [' · '] : []), make('span', {['data-' + key]: ''}, words)));
  return box;
 }
 // The line under it: the rooms that want heat (not the room shown in the card) and the boiler request.
 wanting(status, inlined) {
  const request = this.st(this._config.request);
  if (!known(request)) return '';
  const rooms = (Array.isArray(request.attributes?.rooms) ? request.attributes.rooms : [])
   .filter(room => room && room.demand === true && (inlined === undefined || room.id !== inlined));
  const value = numeric(request.state), out = [];
  if (rooms.length) out.push(rooms.length === 1 ? this.t('wants_one') : this.t('wants', {n: this.number(rooms.length)}));
  if (value !== null && value > 0 && !status.fromRequest)
   out.push(this.inUnit(this.t(this.driving() ? 'request' : 'would_ask', {flow: this.degrees(value)}), this._config.request));
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
  const figures = this.figures(room, roomState, status);
  if (figures) wrap.append(figures);
  const strip = this.dayStrip();
  if (strip) wrap.append(strip);
  root.replaceChildren(make('style', {}, STYLE), card);
  if (focused) root.querySelector(`[data-focus="${focused}"]`)?.focus({preventScroll: true});
  this.fitTicks();
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
  const boiler = this.boilerWords();
  if (boiler) box.append(boiler);
  if (status.problem) {
   // A tap leads to the fix: Repairs (Home Assistant's own navigation: the new path and location-changed). The link
   // is the icon and the words, with a chevron that says so; the house mode chip beside it is a control of its own.
   Object.assign(main.dataset, {focus: 'problem'});
   main.setAttribute('role', 'link'); main.setAttribute('tabindex', '0');
   main.append(icon('mdi:chevron-right', {class: 'go'}));
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
 figures(room, roomState, status) {
  const config = this._config, list = [];
  if (room) list.push(this.roomFigure(room, roomState));
  // The band says what the boiler does, heating or not; only a problem takes its place, and then this figure says it.
  if (status.problem && [config.activity, config.heating, config.request].some(id => this.st(id))) {
   const on = this.heatingOn(), flow = this.flow();
   list.push(this.figure('heating', this.t('heating'), on === null ? null
    : on ? (flow !== null ? this.t('heating_on', {flow: this.degrees(flow)}) : this.t('heating_on_plain')) : this.t('heating_off')));
  }
  const taps = this.st(config.taps);
  if (taps) {
   const n = known(taps) ? numeric(taps.state) : null, activity = this.st(config.activity), water = this.st(config.hot_water);
   const running = known(activity) ? RUNNING.has(activity.state) : water?.state === 'on';
   const count = n === null ? null : Math.round(n), num = count === null ? null : this.number(count);
   const box = this.figure('hot_water', this.t('hot_water'), count === null ? null
    : count === 0 ? this.t('taps_none') : count === 1 ? this.t('taps_one') : this.t('taps', {n: num}), num,
    running ? make('p', {class: 'note running', 'data-running': ''}, this.t('running')) : null);
   // As the sketch ("vandaag · boiler 65 °C"): the hot water's temperature under the taps.
   const hot = this.value(config.dhw);
   if (hot !== null) box.append(make('p', {class: 'note', 'data-dhw': ''}, this.inUnit(this.t('water', {t: this.degrees(hot)}), config.dhw)));
   list.push(box);
  }
  const gas = config.gas.filter(id => this.st(id));
  if (gas.length) list.push(this.gasFigure(gas));
  if (this.st(config.starts)) {
   const starts = this.today([config.starts]), num = starts === null ? null : this.number(Math.round(starts));
   // As the sketch ("vandaag · 1 in het laatste uur"): the starts in the last hour under today's.
   const hour = this.value(config.starts_hour);
   list.push(this.figure('starts', this.t('starts_today'), num, num, hour === null ? null
    : make('p', {class: 'note', 'data-last-hour': ''}, this.t('last_hour', {n: this.number(Math.round(hour))}))));
  }
  if (!list.length) return null;
  // As the sketch: two by two on a phone (an odd last one across both), one row on a wide card (≥ 720 px), as many
  // columns as figures.
  const grid = make('div', {class: 'figures'});
  grid.style.setProperty('--n', list.length);
  if (list.length % 2) list[list.length - 1].classList.add('p2');
  for (const f of list.slice(0, 2)) f.classList.add('top');
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
  // As the sketch: the temperature large, under it its target and why it heats or not, in the room card's words.
  const now = numeric(a.temperature), target = numeric(a.setpoint);
  const num = tone && now !== null ? now.toLocaleString(locale(hass), {minimumFractionDigits: 1, maximumFractionDigits: 1}) : null;
  box.append(valueOf(num === null ? null : num + NBSP + '°C', num));
  const why = [this.roomSentence(st)];
  if (tone && st.state !== 'off' && target !== null && !OWN_TARGET.has(a.line)) why.unshift(this.t('target', {t: target.toLocaleString(locale(hass), {maximumFractionDigits: 1})}));
  box.append(make('p', {class: 'note why', 'data-reason': st.state}, why.join(' · ')));
  box.addEventListener('click', () => this.moreInfo(room.entity));
  box.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.moreInfo(room.entity); } });
  return box;
 }
 // The room status card's sentence (strings.json room_reason line), its values formatted for this viewer.
 roomSentence(st) {
  const a = st.attributes || {}, v = a.values && typeof a.values === 'object' ? a.values : {}, hass = this._hass;
  if (RESTATED.has(st.state) || !ROOM_TONE[st.state]) return this.stateText(st);
  const at = iso => clockMoment(hass, iso);
  const deg = (value, fixed) => finite(value) ? value.toLocaleString(locale(hass), {minimumFractionDigits: fixed ? 1 : 0, maximumFractionDigits: 1}) : '–';
  const values = {contact: typeof v.contact === 'string' ? v.contact : '', since: at(v.since), time: at(v.time), until: at(v.until),
   temperature: deg(v.temperature, true), target: deg(v.target)};
  const line = typeof a.line === 'string' ? this.word('room_reason.state_attributes.line.state.' + a.line, values) : '';
  return together(line || this.stateText(st));
 }
 gasFigure(ids) {
  const unit = this.st(ids[0])?.attributes?.unit_of_measurement;
  // Without statistics (a recorder that keeps none of these sensors, or a failing read) the sensors' own figures:
  // their attributes today and last_7_days (energy_use.py; today included in the 7 days).
  const attribute = key => { const values = ids.map(id => numeric(this.st(id)?.attributes?.[key]));
   return values.every(v => v !== null) ? values.reduce((a, b) => a + b, 0) : null; };
  const stats = this.today(ids), total = stats !== null ? stats : attribute('today');
  const num = total === null ? null : this.number(total, 1);
  // Without a gas meter the sensors estimate the gas from the burner (estimate: true): the label says so (glossary).
  const estimate = ids.some(id => this.st(id)?.attributes?.estimate === true);
  const box = this.figure('gas', this.t(estimate ? 'gas_estimate' : 'gas_today'), num === null ? null
   : num + (typeof unit === 'string' && unit ? NBSP + unit : ''), num);
  // The last 7 days: the gas of every day that has statistics; no line before there are two days. Under it the
  // average whole day of the week before today, once there are two.
  const per = this._stats?.day === midnight(Date.now(), houseZone(this._hass)) ? this._stats.per : null;
  const day = i => { const values = ids.map(id => per?.[id]?.[i]).filter(v => v !== null && v !== undefined);
   return values.length ? values.reduce((a, b) => a + b, 0) : null; };
  const points = [], whole = [];
  for (let i = 0; i < 7; i++) { const v = day(i + 1); if (v !== null) points.push({i, v}); }
  for (let i = 0; i < 7; i++) { const v = day(i); if (v !== null) whole.push(v); }
  const unitText = typeof unit === 'string' && unit ? NBSP + unit : '';
  if (points.length >= 2) {
   const row = make('div', {class: 'trend'});
   // "; " between the values: a comma is the decimal separator in Dutch and Polish.
   const label = this.t('week', {values: points.map(p => this.number(p.v, 1)).join('; ') + unitText});
   row.append(box.querySelector('.value'), sparkline(points, label));
   box.append(row);
  }
  let average = null, days = 0;
  if (whole.length >= 2) { average = whole.reduce((a, b) => a + b, 0) / whole.length; days = whole.length; }
  else if (!per || ids.every(id => (per[id] || []).every(v => v === null))) {
   // No statistics at all: the 6 whole days before today from the sensors' last 7 days, once they hold some gas.
   const week = attribute('last_7_days'), now = attribute('today');
   if (week !== null && now !== null && week - now > 0) { average = (week - now) / 6; days = 6; }
  }
  if (average !== null)
   box.append(make('p', {class: 'note', 'data-average': ''}, this.t('per_day', {n: this.number(days), value: this.number(average, 1) + unitText})));
  return box;
 }
 // The day so far, as the sketch: a 10 px rounded track from midnight to midnight, what the boiler did on it up to now
 // (the rest of the day paler), the hours and "now" under it.
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
  const box = make('div', {class: 'today'}), legend = make('ul', {class: 'legend'});
  for (const [kind, key] of LEGEND) {
   const li = make('li', {'data-key': kind});
   li.append(make('i', {class: kind}), this.t(key));
   legend.append(li);
  }
  const title = make('span', {class: 'today-title'}, this.t('today_since'));
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
   ticks.append(make('span', {style: `left:${pct(at).toFixed(3)}%`, 'data-hour': hour}, text));
  }
  // "now" where the strip ends; at the very start or end of the day it keeps inside the card.
  const here = pct(now);
  ticks.append(make('span', {class: 'now' + (here > 94 ? ' end' : here < 3 ? ' start' : ''), style: `left:${here.toFixed(3)}%`}, this.t('now')));
  box.append(title, legend, strip, ticks);
  return box;
 }
 // An hour mark that "now" would cover steps aside (its place is plain from the others); measured, so in any language.
 fitTicks() {
  const ticks = this.shadowRoot?.querySelector('.ticks'), now = ticks?.querySelector('.now');
  if (!now) return;
  const hours = [...ticks.querySelectorAll('[data-hour]')];
  for (const span of hours) span.style.visibility = '';
  const a = now.getBoundingClientRect();
  if (!a.width) return;  // not laid out yet (a hidden tab): the next redraw or a new width places them
  for (const span of hours) {
   const b = span.getBoundingClientRect();
   if (b.right + 6 > a.left && b.left - 6 < a.right) span.style.visibility = 'hidden';
  }
 }
}

// Yesterday in figures (the Learning view): the scoreboard's headline figures, each from its own sensor, large as on
// the house card; a tap shows that sensor's history (more-info). States only: nothing is asked.
class OpenThermostatYesterday extends OpenThermostatCard {
 constructor() { super(); this.attachShadow({mode: 'open'}); this._key = null; }
 setConfig(config) {
  const id = entityId, room = config?.room && id(config.room.entity)
   ? {entity: config.room.entity, name: typeof config.room.name === 'string' ? config.room.name : ''} : null;
  const c = {room, starts: id(config?.starts), gas: id(config?.gas), degree_days: id(config?.degree_days)};
  if (!room && !c.starts && !c.gas && !c.degree_days)
   throw new Error('This card needs a "Yesterday" sensor of OpenThermostat (room: {entity: sensor.…, name: …}, starts, gas or degree_days: sensor.…); the OpenThermostat dashboard adds it for you.');
  this._config = c; this._key = null;
  if (this._hass) this.render();
 }
 set hass(hass) {
  this._hass = hass;
  if (!this._config) return;
  const c = this._config, key = [c.room?.entity, c.starts, c.gas, c.degree_days].map(id => id && hass?.states?.[id])
   .concat([locale(hass), hass?.themes?.darkMode]);
  if (this._key && key.every((v, i) => v === this._key[i])) return;
  this._key = key; this.render();
 }
 getCardSize() { return 3; }
 getGridOptions() { return {columns: 12, min_columns: 6}; }
 render() {
  const hass = this._hass, c = this._config;
  if (!hass || !c) return;
  const root = this.shadowRoot, focused = root.activeElement?.dataset?.focus, list = [];
  const value = (st, attribute) => known(st) ? numeric(attribute ? st.attributes?.[attribute] : st.state) : null;
  // As the sketch: the label small and muted, the value (its unit and words too) 22 px bold; "—" while not known.
  const add = (key, entity, label, text, muted) => {
   const box = make('div', {class: 'figure', 'data-figure': key, 'data-focus': key, role: 'button', tabindex: '0'});
   box.append(make('p', {class: 'label'}, label), make('p', {class: 'value' + (text === null || muted ? ' unknown' : '')}, text === null ? DASH : text));
   box.addEventListener('click', () => this.moreInfo(entity));
   box.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.moreInfo(entity); } });
   list.push(box);
  };
  const room = c.room && this.st(c.room.entity);
  if (room) {
   // Minutes after the program's switch time that the room was warm (scoreboard.py): late, early or on time.
   // An hour or more as hours and minutes ("1 h 12 min late"); no warm-up yesterday (the sensor unknown: the room off,
   // away or on holiday) in words, muted, instead of "—" under a label that says it was warm.
   const minutes = value(room), m = minutes === null ? null : Math.round(minutes), num = m === null ? null : this.number(Math.abs(m));
   const long = m !== null && Math.abs(m) >= 60 ? {h: this.number(Math.floor(Math.abs(m) / 60)), m: this.number(Math.abs(m) % 60)} : null;
   const none = m === null && room.state === 'unknown';
   // The firmware records a room that did not get warm within 3 hours after the switch as 180 min late (ArrivalLearner):
   // that is no lateness to count, so it says so, muted as "no warm-up yesterday".
   const never = minutes !== null && minutes >= NOT_WARM_MIN;
   add('room', c.room.entity, this.t('warm', {room: c.room.name || room.attributes?.friendly_name || c.room.entity}),
    none ? this.t('no_warmup') : never ? this.t('not_warm') : m === null ? null : m > 0 ? (long ? this.t('late_hours', long) : this.t('late', {m: num}))
     : m < 0 ? (long ? this.t('early_hours', long) : this.t('early', {m: num})) : this.t('on_time'), none || never);
  }
  const plain = (key, entity, label, v, unit) => {
   const num = v === null ? null : this.number(v, 1);
   add(key, entity, label, num === null ? null : num + (unit ? NBSP + unit : ''));
  };
  const starts = this.st(c.starts), gas = this.st(c.gas), degrees = this.st(c.degree_days);
  if (starts) plain('starts', c.starts, this.t('yesterday_starts'), value(starts));
  if (gas) {
   const unit = gas.attributes?.unit_of_measurement;
   plain('gas', c.gas, this.t('yesterday_heating'), value(gas), typeof unit === 'string' ? unit : '');
  }
  if (degrees) plain('degree_days', c.degree_days, this.t('degree_days'), numeric(degrees.attributes?.degree_days));
  const card = make('ha-card', hass.themes?.darkMode ? {class: 'dark'} : {}), wrap = make('div', {class: 'wrap'});
  if (list.length) {
   // Two by two (a pair of pairs), as the sketch; an odd last one across both columns.
   const grid = make('div', {class: 'figures'});
   if (list.length % 2) list[list.length - 1].classList.add('p2');
   grid.append(...list);
   wrap.append(grid);
  }
  card.append(wrap);
  root.replaceChildren(make('style', {}, YESTERDAY_STYLE), card);
  if (focused) root.querySelector(`[data-focus="${focused}"]`)?.focus({preventScroll: true});
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
ensureDefined('openthermostat-yesterday', OpenThermostatYesterday);
window.customCards = window.customCards || [];
for (const [type, name, description] of [
 ['openthermostat-house', 'OpenThermostat house', 'The house at a glance: what the boiler does now, today in figures and the day so far.'],
 ['openthermostat-yesterday', 'OpenThermostat yesterday in figures', 'Yesterday\u2019s headline figures: a room warm on time, burner starts per heating hour, gas for heating and degree-days.']])
 if (!window.customCards.some(c => c.type === type)) window.customCards.push({type, name, description});
