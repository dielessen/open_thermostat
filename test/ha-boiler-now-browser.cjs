// The Boiler view's Now card (E32 rc.5, frontend/boiler-now-card.js) with the integration's real translations, a fixture
// hass and Home Assistant's statistic answered by the test itself; no HA, no device and no network (every request is
// answered here, any other fails the test). Per card: the band in the full colour of what the boiler does (heating,
// hot water, resting, a fault of the boiler with what to do, no data), white words readable on it (4.5:1), the display
// code in words, the connection with the boiler and hot water on the right; the four figures (water to the heating with
// what is asked and the ceiling, water back with the difference, burner power with its arc, starts in the last hour
// with calm or not and today's starts) two by two on a phone and in one row on a wide card; "—" for what is not known;
// a tap opens the figure's history. Then the reads: Home Assistant's statistic only (never the E32), at most every
// 5 minutes and when the day changes, nothing after the card left the page. English, Dutch and Polish; light and dark;
// desktop, a tablet (the narrowest four-column card), phone and a narrow phone (no sideways scroll, nothing cut). Screenshots go to the evidence directory for the visual check.
const {chromium}=require('playwright-core');
const shot=require('./helpers/screenshot.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),component=path.join(root,'ha/config/custom_components/open_thermostat');
const source=fs.readFileSync(path.join(component,'frontend/boiler-now-card.js'));
const out=path.resolve(process.env.OPENTHERMOSTAT_BOILER_NOW_EVIDENCE||path.join(root,'out/ha-boiler-now-20261104'));
const translations=lang=>JSON.parse(fs.readFileSync(path.join(component,'translations',lang+'.json')));
// What Home Assistant's frontend loads for the "entity" category: flattened component.<domain>.entity... keys.
function resources(lang){
 const flat={},walk=(value,prefix)=>{for(const [k,v] of Object.entries(value))typeof v==='object'?walk(v,prefix+k+'.'):flat[prefix+k]=v;};
 walk(translations(lang).entity,'component.open_thermostat.entity.');
 return flat;
}
const NB=String.fromCharCode(160);  // between a figure and its unit
const fill=(text,values={})=>text.replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all).replace(/ (°C|%)/g,NB+'$1');
// The line under a figure: its parts after one another, a number kept with the word before it, the dot at a line's end.
const SEP=NB+'· ',note=(...parts)=>parts.map(text=>text.replace(/ (?=[−-]?\d)/g,NB)).join(SEP);
// Wednesday 4 November 2026, 14:30 in Amsterdam (UTC+1); the next midnight there.
const NOW=Date.parse('2026-11-04T13:30:00Z'),NEXT_MIDNIGHT=Date.parse('2026-11-04T23:00:00Z'),MIN=60000;
// The display code sensor's words, as display_codes.describe() gives them in the Home Assistant language (generic table).
const CODES={
 en:{heating:{meaning:'Heating',severity:'normal',severity_text:'Normal operation',advice:null,cause:200},
  water:{meaning:'Hot water',severity:'normal',severity_text:'Normal operation',advice:null,cause:201},
  waiting:{meaning:'Waiting: anti-cycle time, the burner may not restart yet',severity:'waiting',severity_text:'Waiting',
   advice:'No action needed; the boiler continues by itself.',cause:202},
  fault:{meaning:'No flame detected after ignition',severity:'fault',severity_text:'Fault',
   advice:'Check that the gas tap is open, then reset the boiler. Call your installer if the code comes back.',cause:227}},
 nl:{heating:{meaning:'Verwarmen',severity:'normal',severity_text:'Normaal bedrijf',advice:null,cause:200},
  water:{meaning:'Warm water',severity:'normal',severity_text:'Normaal bedrijf',advice:null,cause:201},
  waiting:{meaning:'Wacht: antipendeltijd, de brander mag nog niet herstarten',severity:'waiting',severity_text:'Wacht',
   advice:'Geen actie nodig; de ketel gaat vanzelf verder.',cause:202},
  fault:{meaning:'Geen vlam na het ontsteken',severity:'fault',severity_text:'Storing',
   advice:'Controleer of de gaskraan open staat en reset dan de ketel. Bel je installateur als de code terugkomt.',cause:227}},
 pl:{heating:{meaning:'Ogrzewanie',severity:'normal',severity_text:'Normalna praca',advice:null,cause:200},
  water:{meaning:'Ciepła woda',severity:'normal',severity_text:'Normalna praca',advice:null,cause:201},
  waiting:{meaning:'Oczekiwanie: blokada taktowania, palnik nie może jeszcze wystartować',severity:'waiting',severity_text:'Oczekiwanie',
   advice:'Nie trzeba nic robić; kocioł wznowi pracę samoczynnie.',cause:202},
  fault:{meaning:'Nie wykryto płomienia po zapłonie',severity:'fault',severity_text:'Usterka',
   advice:'Sprawdź, czy zawór gazu jest otwarty, a następnie zresetuj kocioł. Jeśli kod powróci, wezwij instalatora.',cause:227}}};
const ent=(entity_id,state,attributes={},changed=NOW-20*MIN)=>({entity_id,state:String(state),attributes,
 last_changed:new Date(changed).toISOString(),last_updated:new Date(changed).toISOString()});
const C={unit_of_measurement:'°C'},PCT={unit_of_measurement:'%'};
const gone=(...ids)=>ids.map(id=>ent(id,'unavailable'));
// The cards on the page: their config and their states.
const cardsFor=lang=>{const code=CODES[lang];return {
 heating:{config:{activity:'sensor.activity_heating',heating:'sensor.ch_heating',hot_water:'sensor.dhw_heating',code:'sensor.code_heating',
   flow:'sensor.flow_heating',return:'sensor.return_heating',modulation:'sensor.power_heating',starts:'sensor.starts_heating',
   starts_today:'sensor.daily_burner_starts',cycling:'binary_sensor.cycling_heating',request:'sensor.req_heating',ceiling:'sensor.flow_source'},
  states:[ent('sensor.activity_heating','heating'),ent('sensor.ch_heating','on'),ent('sensor.dhw_heating','off'),
   ent('sensor.code_heating','-H',code.heating),ent('sensor.flow_heating','40.4',C),ent('sensor.return_heating','33.2',C),
   ent('sensor.power_heating','37',PCT),ent('sensor.starts_heating','1'),ent('sensor.daily_burner_starts','2088'),
   ent('binary_sensor.cycling_heating','off'),ent('sensor.req_heating','30',{mode:'active',control:'active',rooms:[]}),
   ent('sensor.flow_source','curve',{applied_flow_c:30,ceiling_c:40})]},
 water:{config:{activity:'sensor.activity_water',hot_water:'sensor.dhw_water',code:'sensor.code_water',flow:'sensor.flow_water',
   return:'sensor.return_water',modulation:'sensor.power_water',starts:'sensor.starts_water',starts_today:'sensor.daily_burner_starts_water',
   cycling:'binary_sensor.cycling_water',request:'sensor.req_water',ceiling:'sensor.flow_source_off'},
  states:[ent('sensor.activity_water','tapping'),ent('sensor.dhw_water','on'),ent('sensor.code_water','=H',code.water),
   ent('sensor.flow_water','55.2',C),ent('sensor.return_water','45.0',C),ent('sensor.power_water','100',PCT),ent('sensor.starts_water','7'),
   ent('sensor.daily_burner_starts_water','16'),ent('binary_sensor.cycling_water','on'),ent('sensor.req_water','0',{mode:'active'}),
   ent('sensor.flow_source_off','curve',{applied_flow_c:30,ceiling_c:null})]},
 idle:{config:{activity:'sensor.activity_idle',heating:'sensor.ch_idle',hot_water:'sensor.dhw_idle',code:'sensor.code_idle',flow:'sensor.flow_idle',
   return:'sensor.return_idle',modulation:'sensor.power_idle',starts:'sensor.starts_idle',request:'sensor.req_idle'},
  states:[ent('sensor.activity_idle','idle'),ent('sensor.ch_idle','off'),ent('sensor.dhw_idle','off'),ent('sensor.code_idle','0A',code.waiting),
   ent('sensor.flow_idle','31.0',C),ent('sensor.return_idle','29.4',C),ent('sensor.power_idle','0',PCT),ent('sensor.starts_idle','0'),
   ent('sensor.req_idle','38',{mode:'shadow'})]},
 fault:{config:{activity:'sensor.activity_fault',code:'sensor.code_fault',flow:'sensor.flow_fault',modulation:'sensor.power_fault',
   starts:'sensor.starts_fault'},
  states:[ent('sensor.activity_fault','idle'),ent('sensor.code_fault','6A',code.fault),ent('sensor.flow_fault','24.0',C),
   ent('sensor.power_fault','0',PCT),ent('sensor.starts_fault','3')]},
 // The E32 is heard (its request), the boiler is not: the connection says "none".
 silent:{config:{activity:'sensor.activity_silent',code:'sensor.code_silent',flow:'sensor.flow_silent',modulation:'sensor.power_silent',
   request:'sensor.req_silent'},
  states:[ent('sensor.activity_silent','unknown'),ent('sensor.code_silent','unknown'),ent('sensor.flow_silent','unknown',C),
   ent('sensor.power_silent','unknown',PCT),ent('sensor.req_silent','45',{mode:'active'})]},
 // Nothing heard at all (the E32 offline): no data, every figure "—", the connection and hot water "—".
 unknown:{config:{activity:'sensor.activity_unknown',heating:'sensor.ch_unknown',hot_water:'sensor.dhw_unknown',code:'sensor.code_unknown',
   flow:'sensor.flow_unknown',return:'sensor.return_unknown',modulation:'sensor.power_unknown',starts:'sensor.starts_unknown',
   request:'sensor.req_unknown'},
  states:gone('sensor.activity_unknown','sensor.ch_unknown','sensor.dhw_unknown','sensor.code_unknown','sensor.flow_unknown',
   'sensor.return_unknown','sensor.power_unknown','sensor.starts_unknown','sensor.req_unknown')},
 // An older integration: no boiler activity, the hub's heating and hot water bits.
 bits:{config:{heating:'binary_sensor.boiler_heating_active',hot_water:'binary_sensor.boiler_hot_water_active',flow:'sensor.boiler_flow',
   modulation:'sensor.boiler_burner_power'},
  states:[ent('binary_sensor.boiler_heating_active','on'),ent('binary_sensor.boiler_hot_water_active','off'),ent('sensor.boiler_flow','45',C),
   ent('sensor.boiler_burner_power','50',PCT)]},
 // A code without its words (an older entity) and one figure that is not known yet.
 partial:{config:{code:'sensor.code_bare',flow:'sensor.flow_partial'},states:[ent('sensor.code_bare','-H'),ent('sensor.flow_partial','unknown',C)]},
};};
// Home Assistant's default theme (its deep orange, blue and grey are the band's colours before they are darkened).
const THEMES={light:'--primary-text-color:#212121;--secondary-text-color:#727272;--card-background-color:#fff;--divider-color:rgba(0,0,0,.12);'+
  '--primary-color:#03a9f4;--deep-orange-color:#ff6f22;--blue-color:#2196f3;--grey-color:#9e9e9e;--error-color:#db4437;background:#fafafa',
 dark:'--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--card-background-color:#1c1c1c;--divider-color:rgba(225,225,225,.12);'+
  '--primary-color:#03a9f4;--deep-orange-color:#ff6f22;--blue-color:#2196f3;--grey-color:#9e9e9e;--error-color:#db4437;background:#111'};
const RGB={light:{text:'rgb(33, 33, 33)',muted:'rgb(114, 114, 114)',surface:'rgb(255, 255, 255)'},
 dark:{text:'rgb(225, 225, 225)',muted:'rgb(155, 155, 155)',surface:'rgb(28, 28, 28)'}};
const UNAVAILABLE={en:'Unavailable',nl:'Niet beschikbaar',pl:'Niedostępny'},UNKNOWN={en:'Unknown',nl:'Onbekend',pl:'Nieznany'};
// WCAG contrast of two "rgb(…)"/"color(srgb …)" colours (the second opaque).
const channels=c=>{const m=c.match(/rgba?\(([^)]+)\)/);if(m)return m[1].split(',').map(Number);
 const s=c.match(/color\(srgb ([^)]+)\)/);if(s)return s[1].split(/\s+/).map((v,i)=>i<3?Number(v)*255:Number(v));throw new Error('colour '+c);};
const luminance=([r,g,b])=>{const f=v=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4;};return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);};
const contrast=(fg,bg)=>{const [a,b]=[luminance(channels(fg)),luminance(channels(bg))].sort((x,y)=>y-x);return (a+0.05)/(b+0.05);};

(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[],ratios={};
 try{for(const [lang,width,theme,reads] of [['en',1280,'light',true],['en',390,'dark',false],['nl',390,'light',false],['nl',1280,'dark',false],
  ['pl',390,'dark',false],['pl',320,'light',false],['en',768,'light',false]]){
  const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Europe/Amsterdam',locale:lang});
  const page=await context.newPage(),errors=[],foreign=[];page.on('pageerror',e=>errors.push(e.message));
  // No network: the page itself is answered here; anything else is a failure.
  await context.route('**/*',route=>{const url=route.request().url();
   if(url.startsWith('http://ha.test/'))return route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><style>
    body{margin:0;padding:${width<500?8:16}px;font:14px Roboto,Arial,sans-serif;${THEMES[theme]}}main{display:grid;gap:12px;max-width:1040px}
    h6{margin:6px 2px 0;font:500 11px Roboto,Arial;color:var(--secondary-text-color)}</style><main></main>`});
   foreign.push(url);return route.abort();});
  await page.clock.install({time:NOW-MIN});await page.clock.pauseAt(NOW);
  await page.goto('http://ha.test/lovelace/boiler');
  // Home Assistant's own elements: ha-card (the card surface) and ha-icon (a visible marker per glyph in the screenshots).
  await page.evaluate(()=>{customElements.define('ha-card',class extends HTMLElement{constructor(){super();this.attachShadow({mode:'open'}).innerHTML=
    '<style>:host{display:block;background:var(--card-background-color);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.2)}</style><slot></slot>';}});
   customElements.define('ha-icon',class extends HTMLElement{connectedCallback(){const name=(this.getAttribute('icon')||'').replace('mdi:','');
    this.textContent=name.split('-').map(w=>w[0]).join('').slice(0,2).toUpperCase();
    this.style.cssText+=';display:inline-flex;align-items:center;justify-content:center;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);'+
     'box-sizing:border-box;font:700 9px Arial;border:1.5px solid currentColor;border-radius:50%';}});});
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text);},source.toString('base64'));
  const CARDS=cardsFor(lang),words=resources(lang),W=translations(lang).entity.sensor.boiler_activity.state_attributes.card.state;
  const activityWord=state=>words['component.open_thermostat.entity.sensor.boiler_activity.state.'+state];
  await page.evaluate(({cards,lang,dict,dark,unavailable,unknown,midnight})=>{
   const localize=(key,values={})=>(dict[key]||'').replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all);
   const states={};for(const card of Object.values(cards))for(const st of card.states)states[st.entity_id]=st;
   window.calls=[];window.moreInfo=[];
   const formatEntityState=(st,state=st.state)=>{
    if(state==='unavailable')return unavailable;if(state==='unknown')return unknown;
    return (st.entity_id.includes('activity')&&dict['component.open_thermostat.entity.sensor.boiler_activity.state.'+state])||state;};
   // Home Assistant's websocket: the starts' statistic of today as the recorder answers it (each call recorded); a
   // new day starts at zero.
   const callWS=async msg=>{calls.push(JSON.parse(JSON.stringify(msg)));
    if(msg.type==='recorder/statistic_during_period'){
     const today={'sensor.daily_burner_starts':14,'sensor.daily_burner_starts_water':16}[msg.statistic_id];
     return today===undefined?{}:{change:Date.now()>=midnight?0:today};}
    throw new Error('not answered: '+msg.type);};
   window.hass={language:lang,locale:{language:lang,time_format:'24',time_zone:'server'},config:{time_zone:'Europe/Amsterdam'},
    themes:{darkMode:dark},states,localize,formatEntityState,callWS};
   for(const [name,card] of Object.entries(cards)){
    const el=document.createElement('openthermostat-boiler-now');el.dataset.card=name;el.setConfig(card.config);
    el.addEventListener('hass-more-info',e=>moreInfo.push(e.detail.entityId));
    const label=document.createElement('h6');label.textContent=name;document.querySelector('main').append(label,el);el.hass=hass;
   }
  },{cards:CARDS,lang,dict:words,dark:theme==='dark',unavailable:UNAVAILABLE[lang],unknown:UNKNOWN[lang],midnight:NEXT_MIDNIGHT});
  const card=name=>page.locator(`openthermostat-boiler-now[data-card="${name}"]`);
  // Today's starts read: the statistic's answers are in the cards.
  await page.waitForFunction(([a,b])=>['heating','water'].map(name=>document.querySelector(`[data-card="${name}"]`).shadowRoot
   .querySelector('[data-figure="starts"] .note')?.textContent).join('|')===a+'|'+b,
   [note(W.calm,fill(W.today,{n:'14'})),note(W.often,fill(W.today,{n:'16'}))]);
  const figure=(name,key)=>card(name).locator(`[data-figure="${key}"]`);
  const figures=async name=>card(name).locator('.figure').evaluateAll(f=>f.map(x=>[x.dataset.figure,x.querySelector('.value').textContent,
   x.querySelector('.note')?.textContent??null]));
  const band=async name=>{const s=card(name).locator('.status');return [await s.getAttribute('data-status'),await s.locator('.line').textContent(),
   await s.locator('.sub').count()?await s.locator('.sub').textContent():null,await s.locator('.advice').count()?await s.locator('.advice').textContent():null,
   await s.locator('.meta').count()?await s.locator('.meta').textContent():null,await s.locator('.main > ha-icon').getAttribute('icon')];};
  const meta=(link,dhw)=>[link===undefined?null:fill(W.link,{state:link}),dhw===undefined?null:fill(W.dhw,{state:dhw})].filter(Boolean)
   .map(text=>text.replace(/ (?=\S+$)/,NB)).join(SEP);
  const lower=text=>text[0].toLocaleLowerCase(lang)+text.slice(1);

  // 1. Heating: the band in deep orange with the activity's own word, the code in words, the connection and hot water.
  const heating=card('heating');
  assert.equal(await heating.locator('.wrap').getAttribute('aria-label'),W.title);
  assert.deepEqual(await band('heating'),['heat',activityWord('heating'),fill(W.code,{code:'-H',meaning:lower(CODES[lang].heating.meaning)}),null,
   meta(W.link_good,W.no),'mdi:fire']);
  assert.deepEqual(await heating.locator('.meta span').evaluateAll(s=>s.map(x=>[x.dataset.link??null,x.dataset.dhw??null])),
   [['good',null],[null,'off']]);
  // The four figures, as the sketch: the numbers whole, their units small, a line under each.
  assert.deepEqual(await figures('heating'),[
   ['flow','40'+NB+'°C',note(fill(W.asked,{flow:'30'}),fill(W.ceiling,{flow:'40'}))],
   ['return','33'+NB+'°C',note(fill(W.difference,{n:'7'}))],
   ['power','37'+NB+'%',note(W.power_low)],
   ['starts','1',note(W.calm,fill(W.today,{n:'14'}))]]);
  assert.deepEqual(await heating.locator('.figure .label').allTextContents(),[W.flow,W.back,W.power,W.starts]);
  assert.deepEqual(await heating.locator('.figure .unit').allTextContents(),[NB+'°C',NB+'°C',NB+'%']);
  // The burner power's arc: a half circle, filled to 37 % from the left, hidden from screen readers (the number says it).
  const arc=await figure('heating','power').locator('svg.arc').evaluate(s=>({hidden:s.getAttribute('aria-hidden'),
   level:s.querySelector('.level')?.getAttribute('data-pct'),d:s.querySelector('.level')?.getAttribute('d'),track:s.querySelector('.track').getAttribute('d'),
   stroke:getComputedStyle(s.querySelector('.level')).stroke,width:getComputedStyle(s.querySelector('.level')).strokeWidth}));
  assert.deepEqual([arc.hidden,arc.level,arc.track,arc.width],['true','37','M6 30 A22 22 0 0 1 50 30','7px']);
  const [ex,ey]=arc.d.split(' ').slice(-2).map(Number),angle=Math.PI*(1-0.37);
  assert(Math.abs(ex-(28+22*Math.cos(angle)))<0.01&&Math.abs(ey-(30-22*Math.sin(angle)))<0.01,'the arc ends at 37 % of the half circle');
  // 2. Hot water now (tapping): blue, the activity's own word, "hot water: yes"; full fire; switching on and off too often.
  assert.deepEqual(await band('water'),['water',activityWord('tapping'),fill(W.code,{code:'=H',meaning:lower(CODES[lang].water.meaning)}),null,
   meta(W.link_good,W.yes),'mdi:faucet']);
  assert.deepEqual(await figures('water'),[['flow','55'+NB+'°C',note(W.no_request)],['return','45'+NB+'°C',note(fill(W.difference,{n:'10'}))],
   ['power','100'+NB+'%',note(W.power_full)],['starts','7',note(W.often,fill(W.today,{n:'16'}))]]);
  // 3. Resting in the trial run: grey; a waiting code with its cause number and what to do; what the E32 would ask.
  assert.deepEqual(await band('idle'),['rest',activityWord('idle'),fill(W.code,{code:'0A 202',meaning:lower(CODES[lang].waiting.meaning)}),
   CODES[lang].waiting.advice,meta(W.link_good,W.no),'mdi:water-boiler']);
  assert.deepEqual(await figures('idle'),[['flow','31'+NB+'°C',note(fill(W.would_ask,{flow:'38'}))],
   ['return','29'+NB+'°C',note(fill(W.difference,{n:'2'}))],['power','0'+NB+'%',note(W.power_off)],['starts','0',null]]);
  assert.equal(await figure('idle','power').locator('svg.arc .level').count(),0,'burner off: the arc is its track only');
  // 4. A fault of the boiler: red, what it is, how serious with its code, and what to do.
  assert.deepEqual(await band('fault'),['error',CODES[lang].fault.meaning,
   fill(W.code_fault,{severity:CODES[lang].fault.severity_text,code:'6A 227'}),CODES[lang].fault.advice,meta(W.link_good,W.no),'mdi:alert-circle-outline']);
  assert.deepEqual((await figures('fault')).map(f=>f[0]),['flow','power','starts']);
  // 5. The E32 heard, the boiler not: no data from the boiler, connection none; what is asked still said.
  assert.deepEqual(await band('silent'),['none',W.no_data,null,null,meta(W.link_none,'—'),'mdi:water-boiler-off']);
  assert.deepEqual(await figures('silent'),[['flow','—',note(fill(W.asked,{flow:'45'}))],['power','—',null]]);
  // 6. Nothing heard: no data, every figure "—" and nothing under it, the connection and hot water "—".
  assert.deepEqual(await band('unknown'),['none',W.no_data,null,null,meta('—','—'),'mdi:water-boiler-off']);
  assert.deepEqual(await figures('unknown'),[['flow','—',null],['return','—',null],['power','—',null],['starts','—',null]]);
  assert.equal(await card('unknown').locator('.figure .unit, .figure .num').count(),0);
  // 7. An older integration (the hub's heating and hot water bits, no activity): the activity's words still.
  assert.deepEqual(await band('bits'),['heat',activityWord('heating'),null,null,meta(W.link_good,W.no),'mdi:fire']);
  assert.deepEqual(await figures('bits'),[['flow','45'+NB+'°C',null],['power','50'+NB+'%',note(W.power_mid)]]);
  // 8. A code without its words and one figure: "Boiler" in grey, the bare code, the figure across the card.
  assert.deepEqual(await band('partial'),['none',W.boiler,fill(W.code_bare,{code:'-H'}),null,meta(W.link_good),'mdi:water-boiler']);
  assert.deepEqual(await card('partial').locator('.figure').evaluateAll(f=>f.map(x=>[x.dataset.figure,x.classList.contains('p2')])),[['flow',true]]);

  // Colours: the band in the full colour of its tone, darkened so white words read at 4.5:1 at least; the figures in the
  // text colours on the card (labels and lines muted, readable too); the arc in the heating colour.
  const tones=await page.locator('openthermostat-boiler-now').evaluateAll(cards=>cards.map(c=>{const s=c.shadowRoot.querySelector('.status');
   return {card:c.dataset.card,tone:s.dataset.status,bg:getComputedStyle(s).backgroundColor,
    words:[...s.querySelectorAll('.line,.sub,.advice,.meta')].map(t=>getComputedStyle(t).color)};}));
  assert.equal(tones.length,Object.keys(CARDS).length);
  for(const {card:name,tone,bg,words:colours} of tones)for(const fg of colours){
   assert.equal(fg,'rgb(255, 255, 255)',name);const ratio=contrast(fg,bg);
   assert(ratio>=4.5,`${name}: white on ${bg}: ${ratio.toFixed(2)}`);ratios[tone]=ratio.toFixed(2);}
  const bg=tone=>tones.find(t=>t.tone===tone).bg;
  assert.equal(new Set(['heat','water','rest','error'].map(bg)).size,4,'four tones, four colours');
  assert.equal(bg('none'),bg('rest'),'not known: the resting grey');
  const look=await heating.evaluate(el=>{const r=el.shadowRoot,g=(q,k)=>getComputedStyle(r.querySelector(q))[k];
   return {label:g('.figure .label','color'),num:g('.figure .num','color'),unit:g('.figure .unit','color'),note:g('.figure .note','color'),
    numSize:g('.figure .num','fontSize'),numWeight:g('.figure .num','fontWeight'),line:g('.figure','boxShadow'),dark:r.querySelector('ha-card').classList.contains('dark')};});
  assert.equal(look.dark,theme==='dark');
  assert.deepEqual([look.num,look.label,look.unit,look.note,look.numWeight],[RGB[theme].text,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted,'700']);
  const wide=await heating.evaluate(c=>c.getBoundingClientRect().width>=720);
  assert.equal(wide,width>=768,'four figures in a row from a 720 px card');
  assert.equal(look.numSize,wide?'34px':'30px');
  assert(/1px 0px 0px/.test(look.line)&&/0px 1px 0px/.test(look.line),'1 px lines between the figures: '+look.line);
  for(const fg of [look.label,look.note,look.num])assert(contrast(fg,RGB[theme].surface)>=4.5,`${fg} on the card`);
  assert.equal(arc.stroke,theme==='dark'?'rgb(255, 111, 34)':bg('heat'),'the arc: the heating colour (darkened as the band on light)');
  // Phone: two by two; wide: the four in one row.
  const boxes=await heating.locator('.figure').evaluateAll(f=>f.map(x=>{const b=x.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width};}));
  const grid=await heating.locator('.figures').evaluate(g=>g.getBoundingClientRect().width);
  if(wide){
   assert(boxes.every(b=>b.y===boxes[0].y),'one row of four');
   assert(boxes.every(b=>Math.abs(b.w-grid/4)<1),'four equal columns');
   assert.equal(await heating.locator('.meta').evaluate(m=>getComputedStyle(m).textAlign),'right');
  }else{
   assert(boxes[0].y===boxes[1].y&&boxes[2].y===boxes[3].y&&boxes[2].y>boxes[0].y,'two by two');
   assert(boxes.every(b=>Math.abs(b.w-grid/2)<1),'two equal columns');
   // The connection and hot water under the words, where they start.
   const [words,line]=await heating.evaluate(el=>[el.shadowRoot.querySelector('.words'),el.shadowRoot.querySelector('.meta')].map(x=>x.getBoundingClientRect()));
   assert(line.top>=words.bottom&&Math.abs(line.left-words.left)<1,'the line under the words');
  }
  // In every card, the figures of one row share their rows: the numbers stand on one line, also where a label takes two
  // lines (a narrow phone, a long Polish label), and so do the lines under them.
  const rows=await page.locator('openthermostat-boiler-now').evaluateAll(cards=>cards.flatMap(c=>{const byRow=new Map();
   for(const f of c.shadowRoot.querySelectorAll('.figure')){const top=Math.round(f.getBoundingClientRect().top),value=f.querySelector('.value,.dial');
    const label=f.querySelector('.label').getBoundingClientRect();
    byRow.set(top,[...(byRow.get(top)||[]),{value:value.getBoundingClientRect().top,lines:Math.round(label.height/16)}]);}
   return [...byRow.values()].map(row=>({card:c.dataset.card,values:row.map(r=>Math.round(r.value)),lines:row.map(r=>r.lines)}));}));
  for(const row of rows)assert(row.values.every(v=>v===row.values[0]),`${row.card}: numbers on one line ${row.values} (label lines ${row.lines})`);
  // Phone width first: nothing scrolls sideways, no figure or line is cut off.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  const cut=await page.locator('openthermostat-boiler-now').evaluateAll(cards=>cards.flatMap(c=>[...c.shadowRoot.querySelectorAll('.figure,.status,.words,.meta,.note,.value,.dial,.label')]
   .filter(x=>x.scrollWidth>x.clientWidth+1).map(x=>c.dataset.card+' '+x.className)));
  assert.deepEqual(cut,[]);
  // The burner power's arc and its number side by side inside the figure, also "100 %" on the narrowest phone and in
  // the narrowest four-column card.
  for(const name of ['heating','water']){
   const [box,arcBox,value]=await figure(name,'power').evaluate(f=>[f,f.querySelector('svg.arc'),f.querySelector('.value')].map(x=>x.getBoundingClientRect()));
   assert(value.left>=arcBox.right&&value.top<arcBox.bottom&&value.bottom>arcBox.top,`${name}: the number beside the arc`);
   assert(arcBox.left>=box.left&&value.right<=box.right,`${name}: arc and number inside the figure`);
  }
  await shot(page,{path:path.join(out,`${lang}-${width}-${theme}.png`),fullPage:true});
  for(const name of ['heating','water','idle','fault'])await shot(card(name),{path:path.join(out,`${lang}-${width}-${theme}-${name}.png`)});
  // A tap (or Enter) on a figure opens its entity's history; the focus stays over a redraw.
  await figure('heating','return').click();
  await figure('heating','flow').focus();await page.keyboard.press('Enter');
  assert.deepEqual(await page.evaluate(()=>moreInfo.slice()),['sensor.return_heating','sensor.flow_heating']);
  await page.evaluate(()=>{const next={...hass,states:{...hass.states,'sensor.flow_heating':{...hass.states['sensor.flow_heating'],state:'41.6'}}};
   window.hass=next;document.querySelectorAll('openthermostat-boiler-now').forEach(c=>c.hass=next);});
  assert.equal(await figure('heating','flow').locator('.value').textContent(),'42'+NB+'°C');
  assert.equal(await figure('heating','return').locator('.note').textContent(),note(fill(W.difference,{n:'9'})),'the difference of the numbers shown');
  assert.equal(await heating.evaluate(c=>c.shadowRoot.activeElement?.dataset.figure),'flow');

  if(reads){
   // The reads: Home Assistant's statistic only (never the E32), once per card that shows today's starts.
   const calls=()=>page.evaluate(()=>calls.slice()),asked=async id=>(await calls()).filter(c=>c.statistic_id===id).length;
   assert.deepEqual(await calls(),[
    {type:'recorder/statistic_during_period',statistic_id:'sensor.daily_burner_starts',calendar:{period:'day'},types:['change']},
    {type:'recorder/statistic_during_period',statistic_id:'sensor.daily_burner_starts_water',calendar:{period:'day'},types:['change']}]);
   // Home Assistant sets hass on every change in the house, and a minute passes: nothing is asked again.
   await page.evaluate(()=>{const next={...hass,states:{...hass.states,'light.kitchen':{entity_id:'light.kitchen',state:'on',attributes:{}}}};
    document.querySelectorAll('openthermostat-boiler-now').forEach(c=>c.hass=next);});
   await page.clock.runFor(4*MIN);
   assert.equal((await calls()).length,2,'within 5 minutes: nothing asked');
   await page.clock.runFor(MIN);
   assert.deepEqual([await asked('sensor.daily_burner_starts'),await asked('sensor.daily_burner_starts_water')],[2,2],'5 minutes on: once more each');
   // A card that left the page asks nothing any more (no poller left running).
   await page.evaluate(()=>document.querySelector('[data-card=water]').remove());
   await page.clock.runFor(20*MIN);
   assert.equal(await asked('sensor.daily_burner_starts_water'),2,'removed: nothing asked');
   assert.equal(await asked('sensor.daily_burner_starts'),6,'the card still on the page: every 5 minutes');
   // A new day: asked at once, today's starts from zero.
   await page.clock.pauseAt(NEXT_MIDNIGHT+30*1000);await page.clock.runFor(MIN);
   assert.equal(await figure('heating','starts').locator('.note').textContent(),note(W.calm,fill(W.today,{n:'0'})));
   assert.equal(new Set((await calls()).map(c=>c.type)).size,1);
  }
  assert.deepEqual(foreign,[],'no network');
  assert.deepEqual(errors,[]);
  results.push({lang,width,theme,result:'PASS'});await context.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'shipped_card_fixture_hass_no_ha',results,contrast:ratios},null,2)+'\n');
 console.log(JSON.stringify({results,contrast:ratios,screenshots:out}));
})().catch(error=>{console.error(error);process.exitCode=1;});
