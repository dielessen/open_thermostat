// The Overview's house card (E32 rc.5, frontend/house-card.js) with the integration's real translations, a fixture hass
// and Home Assistant's history and statistics answered by the test itself; no HA, no device and no network (every
// request is answered here, any other fails the test). The card as the owner's sketch: a band in the full colour of what
// the boiler does (heating, hot water, resting, a problem that leads to Repairs, waiting for the E32) with white words
// at 4.5:1 and the house mode chip on it; the figures two by two on a phone and in one row on a wide card, large, between
// 1 px lines (the one room switched on with its target, hot water, gas today with its last 7 days beside it and the
// average day under it, burner starts; heating only while the band shows a problem); the day since midnight with its
// tooltips, spoken sentence, hours and "now"; a card with one entity and a card without data. Then the reads: Home
// Assistant only, the history again only after a change and 5 minutes, the statistics every 10, nothing after the card
// left the page. The same module's Yesterday figures (the Learning view): four sensors two by two, 22 px bold, a tap
// shows a figure's history. HA 1.0.0rc7, the rest of the desktop sketch: the band's burner power and display code
// ("burner 37 % · code -H", on its right before the chip on a wide card, under the words on a phone, white at 4.5:1),
// the hot water's temperature and the starts in the last hour under their figures; nothing for an entity that is missing
// or has no value. English, Dutch and Polish; light and dark; desktop, phone and a narrow phone (no sideways scroll).
// R3 review: the room line names a target once; the trial run says what the E32 would ask (grey band); a holiday or a
// temporary end beyond today says "tomorrow" or its date; the gas estimate is named and the sensors' own figures stand
// in for failing statistics; the hot water words of the glossary, "running now" only for a tap; an imperial flow in °F;
// Yesterday says "no warm-up yesterday" and an hour or more in hours.
// Screenshots go to the evidence directory for the visual check.
const {chromium}=require('playwright-core');
const shot=require('./helpers/screenshot.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),component=path.join(root,'ha/config/custom_components/open_thermostat');
const source=fs.readFileSync(path.join(component,'frontend/house-card.js'));
const out=path.resolve(process.env.OPENTHERMOSTAT_HOUSE_CARD_EVIDENCE||path.join(root,'out/ha-house-card-20261104'));
const translations=lang=>JSON.parse(fs.readFileSync(path.join(component,'translations',lang+'.json')));
// What Home Assistant's frontend loads for the "entity" category: flattened component.<domain>.entity... keys.
function resources(lang){
 const flat={},walk=(value,prefix)=>{for(const [k,v] of Object.entries(value))typeof v==='object'?walk(v,prefix+k+'.'):flat[prefix+k]=v;};
 walk(translations(lang).entity,'component.open_thermostat.entity.');
 return flat;
}
const NB=String.fromCharCode(160);  // between a figure and its unit
// The card keeps a figure and its unit together (a no-break space before °C, m³, kWh and %).
const fill=(text,values={})=>text.replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all).replace(/ (°C|m³|kWh|%)/g,NB+'$1');
// Wednesday 4 November 2026, 14:30 in Amsterdam (UTC+1, no clock change in the last 8 days).
const NOW=Date.parse('2026-11-04T13:30:00Z'),MIDNIGHT=Date.parse('2026-11-03T23:00:00Z'),DAY=86400000,MIN=60000;
const at=(h,m=0)=>MIDNIGHT+(h*60+m)*MIN;
// Saturday 14 November 14:30 (ten days on) and tomorrow 7:00, in Amsterdam.
const HOLIDAY_END=at(14,30)+10*DAY,TOMORROW_7=at(7)+DAY;
// The boiler until 12:40: heating twice in the morning with a tap in between, keeping warm, a tap, heating at noon.
const DAYLOG=[['idle',0,0],['heating',5,40],['tapping',6,55],['heating',6,58],['idle',7,30],['keep_warm',8,10],['idle',8,25],
 ['tapping',11,0],['idle',11,2],['heating',12,0],['idle',12,40]];
const history=(...more)=>[...DAYLOG.map(([s,h,m])=>({s,lu:at(h,m)/1000})),...more.map(([s,t])=>({s,lu:t/1000}))];
// Gas (m³) and burner starts per day: the 7 whole days before today and today so far (the hourly statistics lag;
// "today" is the 5-minute one). The line shows the last 7 (six whole days and today), the average the 7 whole days.
const WEEK={'sensor.gas_heating':[2.3,2.1,2.6,1.9,2.4,3.0,2.2,1.2],'sensor.gas_hot_water':[0.4,0.5,0.4,0.6,0.5,0.4,0.5,0.3],
 'sensor.burner_starts':[17,18,22,15,20,25,19,11]};
const TODAY={'sensor.gas_heating':1.6,'sensor.gas_hot_water':0.4,'sensor.burner_starts':14};
// Total-increasing sensors for which Home Assistant answers "today" with the running total (no sum before midnight, as
// the demo once did just after a restart: 28.6 m³ and 173 starts); the 7-day read has the true daily rows.
WEEK['sensor.gas_total']=[2.3,2.1,2.6,1.9,2.4,3.0,2.2,2.0];WEEK['sensor.starts_total']=[17,18,22,15,20,25,19,14];
TODAY['sensor.gas_total']=28.6;TODAY['sensor.starts_total']=173;
const SPARK=[2.6,3.0,2.5,2.9,3.4,2.7,2.0],AVERAGE=(2.7+2.6+3.0+2.5+2.9+3.4+2.7)/7;
const ROOMS=[{id:'woonkamer',name:'Woonkamer',temperature:20.4,setpoint:21},{id:'badkamer',name:'Badkamer',temperature:18.9,setpoint:15}];
const rooms=(...wanting)=>ROOMS.map(r=>({...r,demand:wanting.includes(r.id)}));
const REASONS=['The E32 waits for your confirmation on the E32 Rooms page before it controls the boiler.',
 'Badkamer has had no measurement for 40 minutes.'];
const ent=(entity_id,state,attributes={},changed=NOW-3*3600000)=>({entity_id,state:String(state),attributes,
 last_changed:new Date(changed).toISOString(),last_updated:new Date(changed).toISOString()});
const GAS=['sensor.gas_heating','sensor.gas_hot_water'],M3={unit_of_measurement:'m³'};
// The cards on the page: their config, their states and the activity's history today.
const CARDS={
 heating:{config:{request:'sensor.req_heating',activity:'sensor.activity_heating',heating:'sensor.ch_heating',flow:'sensor.flow',
   hot_water:'sensor.dhw_heating',taps:'sensor.taps_heating',gas:GAS,starts:'sensor.burner_starts',mode:'select.house_mode',
   problem:'binary_sensor.problem_heating',rooms:[{entity:'sensor.woonkamer_reason',name:'Woonkamer'}],
   modulation:'sensor.modulation',code:'sensor.display_code',dhw:'sensor.dhw_temperature',starts_hour:'sensor.starts_last_hour'},
  states:[ent('sensor.req_heating',45,{rooms:rooms('woonkamer'),mode:'shadow'}),ent('sensor.activity_heating','heating',{},at(14,5)),
   ent('sensor.ch_heating','on'),ent('sensor.flow','41.3',{unit_of_measurement:'°C'}),ent('sensor.dhw_heating','off'),ent('sensor.taps_heating','3'),
   ent('sensor.gas_heating','1234.56',M3),ent('sensor.gas_hot_water','321.04',{...M3,estimate:true}),ent('sensor.burner_starts','2088'),ent('select.house_mode','auto'),
   ent('binary_sensor.problem_heating','off'),ent('sensor.modulation','37.4',{unit_of_measurement:'%'}),
   ent('sensor.display_code','-H',{meaning:'Heating',severity:'normal',cause:200}),ent('sensor.dhw_temperature','64.6',{unit_of_measurement:'°C'}),
   ent('sensor.starts_last_hour','1'),ent('sensor.woonkamer_reason','warm_up',{room_id:'woonkamer',line:'warm_up',
    values:{time:new Date(at(17)).toISOString(),target:21},temperature:20.4,setpoint:21,presence:'room_home',window:null})],
  history:history(['heating',at(14,5)])},
 water:{config:{request:'sensor.req_water',activity:'sensor.activity_water',heating:'sensor.ch_water',flow:'sensor.flow',hot_water:'sensor.dhw_water',
   taps:'sensor.taps_water',gas:GAS,starts:'sensor.burner_starts',mode:'select.house_mode_home',problem:'binary_sensor.problem_water'},
  states:[ent('sensor.req_water',0,{rooms:rooms()}),ent('sensor.activity_water','tapping',{},at(14,25)),ent('sensor.ch_water','off'),
   ent('sensor.dhw_water','on'),ent('sensor.taps_water','4'),ent('select.house_mode_home','home'),ent('binary_sensor.problem_water','off')],
  history:history(['tapping',at(14,25)])},
 idle:{config:{request:'sensor.req_idle',activity:'sensor.activity_idle',taps:'sensor.taps_idle',gas:GAS,starts:'sensor.burner_starts',
   mode:'select.house_mode',code:'sensor.code_idle',starts_hour:'sensor.starts_hour_idle'},
  states:[ent('sensor.req_idle',38,{rooms:rooms('woonkamer','badkamer'),mode:'shadow'}),ent('sensor.activity_idle','idle',{},at(12,40)),ent('sensor.taps_idle','0'),
   ent('sensor.code_idle','--',{meaning:'No code'}),ent('sensor.starts_hour_idle','0')],
  history:history()},
 problem:{config:{request:'sensor.req_problem',activity:'sensor.activity_problem',flow:'sensor.flow',taps:'sensor.taps_heating',gas:GAS,
   starts:'sensor.burner_starts',mode:'select.house_mode_away',problem:'binary_sensor.problem',modulation:'sensor.modulation_problem',
   code:'sensor.code_problem'},
  states:[ent('sensor.req_problem',45,{rooms:rooms('woonkamer')}),ent('sensor.activity_problem','heating',{},at(14,5)),
   ent('sensor.modulation_problem','0'),ent('sensor.code_problem','3L',{meaning:'Ignition failed',severity:'lockout',cause:214}),
   ent('select.house_mode_away','away'),ent('binary_sensor.problem','on',{reason:'Waiting for your confirmation (+1)',reasons:REASONS,problems:['a','b']})],
  history:history(['heating',at(14,5)])},
 partial:{config:{request:'sensor.req_partial'},states:[ent('sensor.req_partial',45,{rooms:rooms('badkamer')})],history:[]},
 unknown:{config:{request:'sensor.req_unknown',activity:'sensor.activity_unknown',heating:'sensor.ch_unknown',taps:'sensor.taps_unknown',
   gas:['sensor.gas_unknown'],starts:'sensor.starts_unknown',mode:'select.house_mode',modulation:'sensor.mod_unknown',code:'sensor.code_unknown',
   dhw:'sensor.dhw_unknown',starts_hour:'sensor.hour_unknown'},
  states:[ent('sensor.req_unknown','unavailable'),ent('sensor.activity_unknown','unknown'),ent('sensor.ch_unknown','unavailable'),
   ent('sensor.taps_unknown','unknown'),ent('sensor.gas_unknown','unknown',M3),ent('sensor.starts_unknown','unknown'),
   ent('sensor.mod_unknown','unavailable'),ent('sensor.code_unknown','unknown'),ent('sensor.dhw_unknown','unavailable'),
   ent('sensor.hour_unknown','unknown')],history:[]},
 first:{config:{request:'sensor.req_first',activity:'sensor.activity_first',heating:'sensor.ch_first',taps:'sensor.taps_first',
   gas:['sensor.gas_new'],starts:'sensor.starts_new'},
  states:[ent('sensor.req_first',0,{rooms:rooms()}),ent('sensor.activity_first','idle',{},at(9,12)),ent('sensor.ch_first','off'),
   ent('sensor.taps_first','1'),ent('sensor.gas_new','0.0',M3),ent('sensor.starts_new','0')],history:[{s:'idle',lu:at(9,12)/1000}]},
 // The trial run with the request alone (no boiler activity or bits): grey, what the E32 would ask.
 shadow_only:{config:{request:'sensor.req_shadow'},states:[ent('sensor.req_shadow',40,{rooms:rooms(),mode:'shadow'})],history:[]},
 // The hot water tank heated: hot water's colour, the activity's own words, no "running now" (no tap is open).
 charging:{config:{request:'sensor.req_first',activity:'sensor.activity_charging',taps:'sensor.taps_first'},
  states:[ent('sensor.activity_charging','charging',{},at(14,0))],history:history(['charging',at(14,0)])},
 // An imperial Home Assistant: the water in °F, as the flow sensor says.
 imperial:{config:{request:'sensor.req_first',activity:'sensor.activity_imperial',flow:'sensor.flow_f'},
  states:[ent('sensor.activity_imperial','heating',{},at(14,5)),ent('sensor.flow_f','106',{unit_of_measurement:'°F'})],
  history:history(['heating',at(14,5)])},
 // Statistics that fail (a recorder without these sensors): the gas sensor's own today and last 7 days, an estimate.
 nostats:{config:{request:'sensor.req_first',gas:['sensor.gas_attr']},
  states:[ent('sensor.gas_attr','512.3',{...M3,estimate:true,today:1.4,last_7_days:13.4})],history:[]},
 // Today answered with the running total: the day's change from the 7-day read instead (2.0 m³, 14 starts).
 cumulative:{config:{request:'sensor.req_first',gas:['sensor.gas_total'],starts:'sensor.starts_total'},
  states:[ent('sensor.gas_total','1234.5',M3),ent('sensor.starts_total','2088')],history:[]},
 // A room on holiday for 10 more days, and one held until tomorrow morning: the date, and "tomorrow".
 holiday:{config:{request:'sensor.req_first',rooms:[{entity:'sensor.hal_reason',name:'Hal'}]},
  states:[ent('sensor.hal_reason','holiday',{room_id:'hal',line:'holiday',values:{until:new Date(HOLIDAY_END).toISOString(),target:15},
   temperature:15.3,setpoint:15,presence:null,window:null})],history:[]},
 temporary:{config:{request:'sensor.req_first',rooms:[{entity:'sensor.zolder_reason',name:'Zolder'}]},
  states:[ent('sensor.zolder_reason','temporary',{room_id:'zolder',line:'temporary_until',values:{until:new Date(TOMORROW_7).toISOString(),
   target:22},temperature:20.1,setpoint:22,presence:null,window:null})],history:[]},
};
// The Learning view's Yesterday figures: the four sensors; a room late with one figure not known; a room on time alone.
const YESTERDAY={
 full:{config:{room:{entity:'sensor.woonkamer_warm_on_time',name:'Woonkamer'},starts:'sensor.burner_starts_per_heating_hour',
   gas:'sensor.heating_gas_yesterday',degree_days:'sensor.gas_per_degree_day'},
  states:[ent('sensor.woonkamer_warm_on_time','-4',{unit_of_measurement:'min'}),ent('sensor.burner_starts_per_heating_hour','1.3',{heating_hours:6.2}),
   ent('sensor.heating_gas_yesterday','18.2',{unit_of_measurement:'kWh'}),
   ent('sensor.gas_per_degree_day','1.98',{unit_of_measurement:'kWh',degree_days:9.2,heating_kwh:18.2})]},
 late:{config:{room:{entity:'sensor.badkamer_warm_on_time',name:'Badkamer'},starts:'sensor.starts_per_hour_unknown',gas:'sensor.heating_gas_yesterday'},
  states:[ent('sensor.badkamer_warm_on_time','12.4',{unit_of_measurement:'min'}),ent('sensor.starts_per_hour_unknown','unknown')]},
 on_time:{config:{room:{entity:'sensor.slaapkamer_warm_on_time',name:'Slaapkamer'}},
  states:[ent('sensor.slaapkamer_warm_on_time','0.3',{unit_of_measurement:'min'})]},
 // No warm-up yesterday (the sensor unknown: the room off, away or on holiday), and a warm-up 72 minutes late.
 none:{config:{room:{entity:'sensor.zolder_warm_on_time',name:'Zolder'}},states:[ent('sensor.zolder_warm_on_time','unknown')]},
 long:{config:{room:{entity:'sensor.hal_warm_on_time',name:'Hal'}},states:[ent('sensor.hal_warm_on_time','72.4',{unit_of_measurement:'min'})]},
 // Not warm within 3 hours: the firmware records 180 min (ArrivalLearner's cap); just under it is still minutes late.
 never:{config:{room:{entity:'sensor.kelder_warm_on_time',name:'Kelder'}},states:[ent('sensor.kelder_warm_on_time','180',{unit_of_measurement:'min'})]},
 almost:{config:{room:{entity:'sensor.zolder2_warm_on_time',name:'Zolder'}},states:[ent('sensor.zolder2_warm_on_time','179',{unit_of_measurement:'min'})]},
};
// Home Assistant's own colours (the same in its light and dark theme), its light and dark text and surfaces.
const COLOURS='--state-climate-heat-color:#ff8100;--info-color:#039be5;--error-color:#db4437;--warning-color:#ffa600;--success-color:#43a047;'+
 '--deep-orange-color:#ff6f22;--blue-color:#2196f3;--grey-color:#9e9e9e;--primary-color:#03a9f4;';
const THEMES={light:COLOURS+'--primary-text-color:#212121;--secondary-text-color:#6b6b6b;--card-background-color:#fff;--secondary-background-color:#e5e5e5;'+
  '--divider-color:rgba(0,0,0,.12);--disabled-text-color:#bdbdbd;background:#fafafa',
 dark:COLOURS+'--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--card-background-color:#1c1c1c;--secondary-background-color:#282828;'+
  '--divider-color:rgba(225,225,225,.12);--disabled-text-color:#6f6f6f;background:#111'};
const RGB={light:{text:'rgb(33, 33, 33)',muted:'rgb(107, 107, 107)',surface:'rgb(255, 255, 255)'},
 dark:{text:'rgb(225, 225, 225)',muted:'rgb(155, 155, 155)',surface:'rgb(28, 28, 28)'}};
const WHITE='rgb(255, 255, 255)';
const UNAVAILABLE={en:'Unavailable',nl:'Niet beschikbaar',pl:'Niedostępny'},UNKNOWN={en:'Unknown',nl:'Onbekend',pl:'Nieznany'};
// WCAG contrast of two "rgb(…)"/"color(srgb …)" colours (the second opaque).
const channels=c=>{const m=c.match(/rgba?\(([^)]+)\)/);if(m)return m[1].split(',').map(Number);
 const s=c.match(/color\(srgb ([^)]+)\)/);if(s)return s[1].split(/\s+/).map((v,i)=>i<3?Number(v)*255:Number(v));throw new Error('colour '+c);};
const luminance=([r,g,b])=>{const f=v=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4;};return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);};
const contrast=(fg,bg)=>{const [a,b]=[luminance(channels(fg)),luminance(channels(bg))].sort((x,y)=>y-x);return (a+0.05)/(b+0.05);};
// A translucent colour over an opaque one, as "rgb(…)".
const over=(top,under)=>{const t=channels(top),u=channels(under),a=t.length>3?t[3]:1;return `rgb(${[0,1,2].map(i=>t[i]*a+u[i]*(1-a)).join(', ')})`;};

(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[],ratios={};
 try{for(const [lang,width,theme,reads] of [['en',1280,'light',true],['en',390,'dark',false],['nl',390,'light',false],['nl',1280,'dark',false],
  ['pl',390,'dark',false],['pl',320,'light',false]]){
  const context=await browser.newContext({viewport:{width,height:900},timezoneId:'Europe/Amsterdam',locale:lang});
  const page=await context.newPage(),errors=[],foreign=[];page.on('pageerror',e=>errors.push(e.message));
  // No network: the page itself is answered here; anything else is a failure.
  await context.route('**/*',route=>{const url=route.request().url();
   if(url.startsWith('http://ha.test/'))return route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><style>
    body{margin:0;padding:${width<500?8:16}px;font:14px Roboto,Arial,sans-serif;${THEMES[theme]}}main{display:grid;gap:12px;max-width:1040px}
    h6{margin:6px 2px 0;font:500 11px Roboto,Arial;color:var(--secondary-text-color)}</style><main></main>`});
   foreign.push(url);return route.abort();});
  await page.clock.install({time:NOW-MIN});await page.clock.pauseAt(NOW);
  await page.goto('http://ha.test/lovelace/0');
  // Home Assistant's own elements: ha-card (the card surface) and ha-icon (a visible marker per glyph in the screenshots).
  await page.evaluate(()=>{customElements.define('ha-card',class extends HTMLElement{constructor(){super();this.attachShadow({mode:'open'}).innerHTML=
    '<style>:host{display:block;background:var(--card-background-color);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.2)}</style><slot></slot>';}});
   customElements.define('ha-icon',class extends HTMLElement{connectedCallback(){const name=(this.getAttribute('icon')||'').replace('mdi:','');
    this.textContent=name.split('-').map(w=>w[0]).join('').slice(0,2).toUpperCase();
    this.style.cssText+=';display:inline-flex;align-items:center;justify-content:center;width:var(--mdc-icon-size,24px);height:var(--mdc-icon-size,24px);'+
     'box-sizing:border-box;font:700 9px Arial;border:1.5px solid currentColor;border-radius:50%';}});});
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text);},source.toString('base64'));
  const words=resources(lang),W=translations(lang).entity.sensor.heat_request.state_attributes.card.state;
  await page.evaluate(({cards,yesterday,lang,dict,dark,week,today,midnight,unavailable,unknown})=>{
   const localize=(key,values={})=>(dict[key]||'').replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all);
   const states={};for(const card of [...Object.values(cards),...Object.values(yesterday)])for(const st of card.states)states[st.entity_id]=st;
   window.histories=Object.fromEntries(Object.values(cards).filter(c=>c.config.activity).map(c=>[c.config.activity,c.history]));
   window.calls=[];window.events=[];window.moreInfo=[];
   window.addEventListener('location-changed',()=>events.push(location.pathname));
   const formatEntityState=(st,state=st.state)=>{
    if(state==='unavailable')return unavailable;if(state==='unknown')return unknown;
    const kind=st.entity_id.startsWith('select.')?'select.house_mode':st.entity_id.endsWith('_reason')?'sensor.room_reason':
     st.entity_id.includes('activity')?'sensor.boiler_activity':null;
    return (kind&&dict['component.open_thermostat.entity.'+kind+'.state.'+state])||state;};
   // Home Assistant's websocket: history and statistics as the recorder answers them (each call recorded).
   const callWS=async msg=>{calls.push(JSON.parse(JSON.stringify(msg)));
    if(msg.type==='history/history_during_period')return {[msg.entity_ids[0]]:histories[msg.entity_ids[0]]||[]};
    if(JSON.stringify(msg).includes('sensor.gas_attr'))throw new Error('no statistics for this sensor');
    if(msg.type==='recorder/statistics_during_period')return Object.fromEntries(msg.statistic_ids.filter(id=>week[id])
     .map(id=>[id,week[id].map((change,i)=>({start:midnight-(7-i)*86400000,end:midnight-(6-i)*86400000,change}))]));
    if(msg.type==='recorder/statistic_during_period')return msg.statistic_id in today?{change:today[msg.statistic_id]}:{};
    throw new Error('not answered: '+msg.type);};
   window.hass={language:lang,locale:{language:lang,time_format:'24',time_zone:'server'},config:{time_zone:'Europe/Amsterdam'},
    themes:{darkMode:dark},states,localize,formatEntityState,callWS};
   const add=(tag,name,config)=>{const el=document.createElement(tag);el.dataset.card=name;el.setConfig(config);
    el.addEventListener('hass-more-info',e=>moreInfo.push(e.detail.entityId));
    const label=document.createElement('h6');label.textContent=name;document.querySelector('main').append(label,el);el.hass=hass;};
   for(const [name,card] of Object.entries(cards))add('openthermostat-house',name,card.config);
   for(const [name,card] of Object.entries(yesterday))add('openthermostat-yesterday',name,card.config);
  },{cards:CARDS,yesterday:YESTERDAY,lang,dict:words,dark:theme==='dark',week:WEEK,today:TODAY,midnight:MIDNIGHT,unavailable:UNAVAILABLE[lang],
   unknown:UNKNOWN[lang]});
  const card=name=>page.locator(`openthermostat-house[data-card="${name}"]`);
  const n=(v,d=0)=>v.toLocaleString(lang,{minimumFractionDigits:d,maximumFractionDigits:d});
  // Everything read: the gas figure and the day strip carry Home Assistant's answers.
  await card('heating').locator('.spark').waitFor();await card('heating').locator('.seg.keep').waitFor();
  const activityWord=state=>words['component.open_thermostat.entity.sensor.boiler_activity.state.'+state];
  const modeWord=state=>words['component.open_thermostat.entity.select.house_mode.state.'+state];

  // 1. Heating, with the one room switched on inside: the band, the figures and the day so far.
  const heating=card('heating');
  assert.equal(await heating.locator('.wrap').getAttribute('aria-label'),W.title);
  assert.equal(await heating.locator('.status').getAttribute('data-status'),'heat');
  assert.equal(await heating.locator('.status .line').textContent(),fill(W.status_heating,{flow:'41'}));
  // The living room is in the card: the request without "1 room wants heat" (the room says it itself).
  assert.equal(await heating.locator('.status .sub').textContent(),fill(W.would_ask,{flow:'45'}));  // the trial run
  assert.equal(await heating.locator('.chip span').textContent(),modeWord('auto'));
  assert.equal(await heating.locator('.chip').getAttribute('aria-label'),fill(W.mode,{mode:modeWord('auto')}));
  // The band says the boiler heats: no Heating figure under it (as the sketch).
  assert.deepEqual(await heating.locator('.figure').evaluateAll(f=>f.map(x=>x.dataset.figure)),['room','hot_water','gas','starts']);
  const room=heating.locator('.figure.room');
  assert.equal(await room.locator('.label > span').textContent(),'Woonkamer');
  // As the sketch: the temperature large with its unit small, its target and why under it.
  assert.equal(await room.locator('.value').textContent(),n(20.4,1)+NB+'°C');
  assert.deepEqual(await room.locator('.value > span').evaluateAll(s=>s.map(x=>[x.className,x.textContent])),[['num',n(20.4,1)],['unit',NB+'°C']]);
  // The warm-up's sentence carries its own target: no "target 21 °C" in front of it (a figure said once).
  assert.equal(await room.locator('.why').textContent(),
   fill(words['component.open_thermostat.entity.sensor.room_reason.state_attributes.line.state.warm_up'],{time:'17:00',target:'21'}));
  assert.equal(await room.locator('[data-presence]').getAttribute('aria-label'),
   words['component.open_thermostat.entity.sensor.room_reason.state_attributes.presence.state.room_home']);
  const value=name=>heating.locator(`[data-figure="${name}"] .value`).textContent();
  assert.equal(await value('hot_water'),fill(W.taps,{n:'3'}));
  assert.equal(await heating.locator('[data-figure="hot_water"] .value .num').textContent(),'3');
  assert.equal(await heating.locator('[data-running]').count(),0);
  assert.equal(await value('gas'),n(2,1)+NB+'m³');
  assert.equal(await heating.locator('[data-average]').textContent(),fill(W.per_day,{n:'7',value:n(AVERAGE,1)+' m³'}));
  assert.equal(await value('starts'),'14');
  // HA 1.0.0rc7, the desktop sketch: "burner 37 % · code -H" on the band (the code's meaning in its tooltip), "water 65 °C"
  // under the taps and "1 in the last hour" under today's starts.
  const boiler=heating.locator('[data-boiler]');
  assert.equal(await boiler.textContent(),fill(W.burner,{n:'37'})+' · '+fill(W.code,{code:'-H'}));
  assert.deepEqual([await boiler.locator('[data-power]').textContent(),await boiler.locator('[data-code]').textContent()],
   [fill(W.burner,{n:'37'}),fill(W.code,{code:'-H'})]);
  assert.equal(await boiler.getAttribute('title'),'Heating');
  assert.equal(await heating.locator('[data-figure="hot_water"] [data-dhw]').textContent(),fill(W.water,{t:'65'}));
  assert.equal(await heating.locator('[data-figure="starts"] [data-last-hour]').textContent(),fill(W.last_hour,{n:'1'}));
  // Where the words stand: on a wide card on the band's right, before the house mode chip, in one row with the words; on a
  // phone under the words (indented as they are), the chip still beside them.
  const place=await heating.evaluate(el=>{const r=el.shadowRoot,b=q=>r.querySelector(q).getBoundingClientRect();
   return {main:b('.status .main'),words:b('.status .words'),boiler:b('.status .boiler'),chip:b('.status .chip'),band:b('.status'),
    size:getComputedStyle(r.querySelector('.status .boiler')).fontSize};});
  if(width>=1000){
   assert(place.boiler.left>=place.main.right&&place.boiler.right<=place.chip.left,'burner and code between the words and the chip');
   assert(place.boiler.top<place.main.bottom&&place.boiler.bottom>place.main.top&&place.chip.top<place.main.bottom,'one row');
   assert.equal(place.size,'13px');
  }else{
   assert(place.boiler.top>=place.main.bottom-1,'under the words on a phone');
   assert(Math.abs(place.boiler.left-place.words.left)<1,'indented as the words');
   if(width>=380)assert(place.chip.left>=place.main.right&&place.chip.top<place.main.bottom,'the chip beside the words, as in rc.5');
   assert.equal(place.size,'12px');
  }
  assert(place.boiler.right<=place.band.right+0.5&&place.boiler.bottom<=place.band.bottom+0.5,'inside the band');
  assert.deepEqual(await heating.locator('.figure .label').evaluateAll(l=>l.map(x=>(x.querySelector('span')||x).textContent)),
   ['Woonkamer',W.hot_water,W.gas_estimate,W.starts_today]);  // without a gas meter: an estimate, named
  // The sparkline beside the gas: 7 days, a 2 px line in the heating hue scaled to its own range; today (a day still
  // running) joins it lighter and is the end dot (r 3); no grid.
  const spark=heating.locator('svg.spark');
  assert.equal(await spark.getAttribute('aria-label'),fill(W.week,{values:SPARK.map(v=>n(v,1)).join('; ')+NB+'m³'}));
  const marks=await spark.evaluate(s=>{const [p,q]=s.querySelectorAll('path'),c=s.querySelector('circle'),g=(e,k)=>getComputedStyle(e)[k];
   const ys=p.getAttribute('d').split(/[ML]/).filter(Boolean).map(xy=>Number(xy.split(',')[1]));
   const v=s.closest('.figure').querySelector('.value').getBoundingClientRect(),b=s.getBoundingClientRect();
   return {d:p.getAttribute('d'),stroke:g(p,'stroke'),width:g(p,'strokeWidth'),fill:g(p,'fill'),opacity:g(p,'strokeOpacity'),
    partial:q.getAttribute('class'),partialOpacity:g(q,'strokeOpacity'),partialEnd:q.getAttribute('d').split('L')[1],r:c.getAttribute('r'),dot:g(c,'fill'),
    cx:c.getAttribute('cx'),cy:c.getAttribute('cy'),h:Number(s.getAttribute('height')),w:Number(s.getAttribute('width')),top:Math.min(...ys),
    grid:s.querySelectorAll('line,rect').length,beside:b.left>=v.right&&b.top<v.bottom&&b.bottom>v.top,shown:b.width};});
  assert.equal((marks.d.match(/[ML]/g)||[]).join(''),'MLLLLL','six whole days as the line');
  assert.deepEqual([marks.width,marks.fill,marks.opacity,marks.r,marks.grid,marks.w,marks.h],['2px','none','1','3',0,84,30]);
  assert.equal(marks.dot,marks.stroke,'the end dot in the line colour');
  assert(contrast(marks.stroke,RGB[theme].surface)>=3,`the gas line stands out: ${contrast(marks.stroke,RGB[theme].surface).toFixed(2)}`);
  assert.deepEqual([marks.partial,marks.partialOpacity,marks.partialEnd],['partial','0.45',marks.cx+','+marks.cy]);
  assert(Number(marks.cx)>marks.w-10,'the dot is today, at the right end');
  assert(marks.top<=5.01&&Number(marks.cy)>=marks.h-5.01,'its own range: the highest day at the top, today (the lowest) at the bottom');
  if(width>=390)assert(marks.beside,'the line beside the number');
  // Home Assistant's sidebar leaves a card of about 960 px at 1280: a figure of 240 px still has the line beside.
  if(width>=1000){const narrow=await heating.evaluate(el=>{el.style.width='960px';const s=el.shadowRoot.querySelector('svg.spark'),
    v=s.closest('.figure').querySelector('.value').getBoundingClientRect(),b=s.getBoundingClientRect();el.style.width='';
    return b.left>=v.right&&b.top<v.bottom&&b.width>=64;});assert(narrow,'beside the number on a 960 px card too');}
  assert(marks.shown>=56&&marks.shown<=(width>=1000?110.5:84.5),`its width ${marks.shown}`);
  // The day so far: midnight to now in the house's time zone, by what the boiler did; touching colours 2 px apart.
  const segments=await heating.locator('.seg').evaluateAll(s=>s.map(x=>({kind:x.dataset.kind,title:x.title,cls:x.className,
   left:parseFloat(x.style.left),width:parseFloat(x.style.width)})));
  assert.deepEqual(segments.map(s=>s.kind),['rest','heat','water','heat','rest','keep','rest','water','rest','heat','rest','heat']);
  assert.deepEqual(segments.filter(s=>s.cls.includes('gap')).map(s=>s.title),
   [W.legend_hot_water+' 06:55–06:58',W.legend_heating+' 06:58–07:30']);
  assert.equal(segments[1].title,W.legend_heating+' 05:40–06:55');
  assert.equal(segments[5].title,W.legend_keep_warm+' 08:10–08:25');
  assert.equal(segments[0].title,W.idle+' 00:00–05:40');
  assert(Math.abs(segments[1].left-340/1440*100)<0.01,'heating from 05:40');
  const last=segments[segments.length-1];
  assert(Math.abs(last.left+last.width-870/1440*100)<0.01,'the strip reaches now (14:30), the rest of the day paler');
  assert(segments[0].cls.includes('first')&&last.cls.includes('last'));
  assert.equal(await heating.locator('.strip').getAttribute('role'),'img');
  assert.equal(await heating.locator('.strip').getAttribute('aria-label'),W.today+': '+[
   W.legend_heating+' 05:40–06:55, 06:58–07:30, 12:00–12:40, 14:05–14:30',W.legend_hot_water+' 06:55–06:58, 11:00–11:02',
   W.legend_keep_warm+' 08:10–08:25'].join('; ')+'.');
  // The hours and "now" under it; an hour that "now" would cover steps aside; nothing overlaps.
  assert.deepEqual(await heating.locator('.ticks [data-hour]').allTextContents(),['00','06','12','18']);
  assert.deepEqual(await heating.locator('.ticks [data-hour]').evaluateAll(s=>s.map(x=>parseFloat(x.style.left))),[0,25,50,75]);
  assert.equal(await heating.locator('.ticks .now').textContent(),W.now);
  assert(Math.abs(await heating.locator('.ticks .now').evaluate(x=>parseFloat(x.style.left))-870/1440*100)<0.01,'"now" at 14:30');
  const overlaps=await page.locator('openthermostat-house').evaluateAll(cards=>cards.flatMap(c=>{
   const shown=[...c.shadowRoot.querySelectorAll('.ticks span')].filter(x=>getComputedStyle(x).visibility!=='hidden').map(x=>x.getBoundingClientRect());
   return shown.flatMap((a,i)=>shown.slice(i+1).filter(b=>a.right>b.left&&b.right>a.left).map(()=>c.dataset.card));}));
  assert.deepEqual(overlaps,[],'hour marks and "now" never overlap');
  assert.equal(await heating.locator('.today-title').textContent(),W.today_since);
  assert.deepEqual(await heating.locator('.legend li').allTextContents(),[W.legend_heating,W.legend_hot_water,W.legend_keep_warm]);
  // Colours. The band: the theme's colour of what the boiler does, white words on it at 4.5:1 or better (also the line under
  // them, the chip's words on its own shade); never text in a status colour elsewhere: labels, units and lines under the
  // figures muted, the figures in the text colour. The strip's marks stand out from its track (3:1).
  const look=await heating.evaluate(el=>{const r=el.shadowRoot,g=(q,k,pseudo)=>getComputedStyle(r.querySelector(q),pseudo)[k];
   return {band:g('.status','backgroundColor'),line:g('.status .line','color'),sub:g('.status .sub','color'),icon:g('.status .main > ha-icon','color'),
    chip:g('.chip','color'),chipBg:g('.chip','backgroundColor'),label:g('.figure .label','color'),value:g('.figure .value','color'),
    num:g('.figure .value .num','fontSize'),numWeight:g('.figure .value .num','fontWeight'),unit:g('.figure .value .unit','color'),
    unitSize:g('.figure .value .unit','fontSize'),labelSize:g('.figure .label','fontSize'),why:g('.figure .why','color'),
    divider:g('.figure','boxShadow'),track:g('.seg.rest','backgroundColor'),heat:g('.seg.heat','backgroundColor','::after'),
    water:g('.seg.water','backgroundColor','::after'),keep:g('.seg.keep','backgroundColor','::after'),legend:g('.legend li','color'),
    tick:g('.ticks span','color'),title:g('.today-title','color'),dark:r.querySelector('ha-card').classList.contains('dark')};});
  assert.equal(look.dark,theme==='dark');
  assert.deepEqual([look.line,look.sub,look.icon,look.chip],[WHITE,WHITE,WHITE,WHITE]);
  assert.deepEqual([look.value,look.label,look.unit,look.why,look.legend,look.tick,look.title],
   [RGB[theme].text,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted]);
  assert.deepEqual([look.num,look.numWeight,look.unitSize,look.labelSize],width>=1000?['34px','700','18px','13px']:['30px','700','18px','12px']);
  assert.match(look.divider,/1px 0px 0px 0px/,'1 px lines between the figures');
  assert(contrast(look.line,look.band)>=4.5&&contrast(look.chip,over(look.chipBg,look.band))>=4.5,'white on the band');
  for(const [fg,bg] of [[look.label,RGB[theme].surface],[look.value,RGB[theme].surface],[look.legend,RGB[theme].surface]])
   assert(contrast(fg,bg)>=4.5,`contrast ${fg} on ${bg}: ${contrast(fg,bg).toFixed(2)}`);
  for(const mark of [look.heat,look.water])assert(contrast(mark,look.track)>=3,`a mark on the track: ${contrast(mark,look.track).toFixed(2)}`);
  assert.notEqual(look.keep,look.water,'keeping warm is the lighter hot-water colour');
  // Every band, in every tone: the theme's colour, its words white and readable; the ratios go into the evidence.
  const bands=await page.locator('openthermostat-house').evaluateAll(cards=>cards.map(c=>{const s=c.shadowRoot.querySelector('.status'),chip=s.querySelector('.chip');
   return {name:c.dataset.card,tone:s.dataset.status,bg:getComputedStyle(s).backgroundColor,words:[...s.querySelectorAll('.line,.sub,.boiler')].map(t=>getComputedStyle(t).color),
    chip:chip?[getComputedStyle(chip).color,getComputedStyle(chip).backgroundColor]:null};}));
  assert.equal(new Set(bands.map(b=>b.name)).size,Object.keys(CARDS).length);
  assert.deepEqual(bands.map(b=>b.tone),['heat','water','rest','error','heat','wait','rest','rest','keep','heat','rest','rest','rest','rest']);
  for(const b of bands){
   for(const fg of b.words)assert(fg===WHITE&&contrast(fg,b.bg)>=4.5,`${b.name}: contrast ${fg} on ${b.bg}: ${contrast(fg,b.bg).toFixed(2)}`);
   if(b.chip)assert(contrast(b.chip[0],over(b.chip[1],b.bg))>=4.5,`${b.name}: the chip`);
   const key=`${theme} ${b.tone}`;
   ratios[key]={band:b.bg,white:Number(contrast(WHITE,b.bg).toFixed(2)),
    chip:b.chip?Number(contrast(b.chip[0],over(b.chip[1],b.bg)).toFixed(2)):ratios[key]?.chip??null};
  }
  // As the sketch: two by two on a phone, one row of four on a wide card; the room, the hot water and the starts as wide as the gas.
  const boxes=await heating.locator('.figure').evaluateAll(f=>f.map(x=>{const b=x.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width};}));
  const grid=await heating.locator('.figures').evaluate(g=>g.getBoundingClientRect().width);
  if(width>=1000){
   assert(boxes.every(b=>b.y===boxes[0].y&&Math.abs(b.w-grid/4)<1),'one row of four');
  }else{
   assert(boxes[0].y===boxes[1].y&&boxes[2].y===boxes[3].y&&boxes[2].y>boxes[0].y&&boxes[0].x===boxes[2].x,'two by two');
   assert(boxes.every(b=>Math.abs(b.w-grid/2)<1),'two columns');
  }

  // 2. Hot water now: a blue band with the activity's own word, "running now"; no heating figure; the strip ends in hot water.
  const water=card('water');
  assert.equal(await water.locator('.status').getAttribute('data-status'),'water');
  assert.equal(await water.locator('.status .line').textContent(),W.tap_open);  // the glossary's words
  assert.equal(await water.locator('.status .sub').count(),0);
  assert.equal(await water.locator('.chip span').textContent(),modeWord('home'));
  assert.equal(await water.locator('[data-figure="hot_water"] .value').textContent(),fill(W.taps,{n:'4'}));
  assert.equal(await water.locator('[data-running]').textContent(),W.running);
  assert.equal(await water.locator('[data-boiler],[data-dhw],[data-last-hour]').count(),0,'not in the config: not shown');
  assert.deepEqual(await water.locator('.figure').evaluateAll(f=>f.map(x=>[x.dataset.figure,x.classList.contains('p2')])),
   [['hot_water',false],['gas',false],['starts',true]]);
  assert.deepEqual(await water.locator('.seg').evaluateAll(s=>s.slice(-2).map(x=>[x.dataset.kind,x.title])),
   [['rest',W.idle+' 12:40–14:25'],['water',W.legend_hot_water+' 14:25–14:30']]);
  // 3. Resting while two rooms want heat (trial run): a grey band, the line under it says so, with the request.
  const idle=card('idle');
  assert.equal(await idle.locator('.status').getAttribute('data-status'),'rest');
  assert.equal(await idle.locator('.status .line').textContent(),W.idle);
  assert.equal(await idle.locator('.status .sub').textContent(),fill(W.wants,{n:'2'})+' · '+fill(W.would_ask,{flow:'38'}));
  assert.equal(await idle.locator('[data-figure="hot_water"] .value').textContent(),W.taps_none);
  assert.deepEqual(await idle.locator('.figure').evaluateAll(f=>f.map(x=>x.dataset.figure)),['hot_water','gas','starts']);
  assert.equal(await idle.locator('[data-boiler]').count(),0,'no display code ("--") and no burner power: no words');
  assert.equal(await idle.locator('[data-last-hour]').textContent(),fill(W.last_hour,{n:'0'}));
  // 4. A problem wins: a red band, its reason, all reasons inside; a tap (or Enter) opens Repairs; the chip its own dialog.
  // The band cannot say what the boiler does now, so the Heating figure does.
  const problem=card('problem'),strip=problem.locator('.status'),link=strip.locator('.main');
  assert.equal(await strip.getAttribute('data-status'),'error');
  assert.equal(await strip.locator('.line').textContent(),fill(W.attention,{reason:'Waiting for your confirmation (+1)'}));
  assert.deepEqual([await link.getAttribute('role'),await link.getAttribute('tabindex')],['link','0']);
  assert.equal(await link.locator('button,[tabindex],[role=link],[role=button]').count(),0,'no control inside the link');
  assert.equal(await link.locator('ha-icon.go').getAttribute('icon'),'mdi:chevron-right','a chevron says it leads somewhere');
  assert.equal(await heating.locator('.status [role=link]').count(),0,'a link only while there is a problem');
  assert.deepEqual(await problem.locator('.figure').evaluateAll(f=>f.map(x=>x.dataset.figure)),['heating','hot_water','gas','starts']);
  assert.equal(await problem.locator('[data-figure="heating"] .value').textContent(),fill(W.heating_on,{flow:'41'}));
  assert.equal(await problem.locator('[data-boiler]').textContent(),fill(W.burner,{n:'0'})+' · '+fill(W.code,{code:'3L 214'}));
  assert.equal(await problem.locator('[data-boiler]').getAttribute('title'),'Ignition failed');
  assert.equal(await problem.locator('.main [data-boiler]').count(),0,'not part of the link to Repairs');
  assert.equal(await problem.locator('.reasons summary').textContent(),W.all_reasons);
  assert.equal(await problem.locator('.reasons').evaluate(d=>d.open),false);
  assert.deepEqual(await problem.locator('.reasons li').allTextContents(),REASONS);
  await strip.locator('.line').click();
  assert.deepEqual(await page.evaluate(()=>[events.slice(),location.pathname]),[['/config/repairs'],'/config/repairs']);
  await link.focus();await page.keyboard.press('Enter');
  assert.equal(await page.evaluate(()=>events.length),2);
  await problem.locator('.chip').click();
  assert.deepEqual(await page.evaluate(()=>[events.length,moreInfo.slice()]),[2,['select.house_mode_away']]);
  // A redraw keeps what the viewer had: "All reasons" open, the keyboard focus on the chip.
  await problem.locator('.reasons summary').click();await problem.locator('.chip').focus();
  await page.evaluate(()=>{const next={...hass,states:{...hass.states,'sensor.activity_problem':{...hass.states['sensor.activity_problem']}}};
   document.querySelector('[data-card=problem]').hass=next;});
  assert.equal(await problem.locator('.reasons').evaluate(d=>d.open),true);
  assert.equal(await problem.evaluate(c=>c.shadowRoot.activeElement?.dataset.focus),'mode');
  // The room figure opens the room's history, as its own status card did.
  await room.click();
  assert.deepEqual(await page.evaluate(()=>moreInfo.slice(-1)),['sensor.woonkamer_reason']);
  // 5. One entity only (the request): the band from it, no figures, no strip and no chip.
  const partial=card('partial');
  assert.deepEqual([await partial.locator('.status').getAttribute('data-status'),await partial.locator('.status .line').textContent(),
   await partial.locator('.status .sub').textContent()],['heat',fill(W.request,{flow:'45'}),W.wants_one]);
  assert.equal(await partial.locator('.figure').count(),0);
  assert.equal(await partial.locator('.today').count(),0);assert.equal(await partial.locator('.chip').count(),0);
  // 6. Nothing reported yet: it says so in a grey band; every figure "—", no sparkline, no strip.
  const unknown=card('unknown');
  assert.deepEqual([await unknown.locator('.status').getAttribute('data-status'),await unknown.locator('.status .line').textContent()],['wait',W.waiting]);
  assert.deepEqual(await unknown.locator('.figure .value').allTextContents(),['—','—','—']);
  assert.equal(await unknown.locator('[data-boiler],[data-dhw],[data-last-hour]').count(),0,'without a value: nothing');
  assert.equal(await unknown.locator('.spark').count(),0);assert.equal(await unknown.locator('.today').count(),0);
  assert.equal(await unknown.locator('[data-average]').count(),0);
  // 7. The first day: no statistics yet, so "—", no sparkline and no average day; the strip starts where the history does.
  const first=card('first');
  assert.deepEqual(await first.locator('[data-figure="gas"] .value, [data-figure="starts"] .value').allTextContents(),['—','—']);
  assert.equal(await first.locator('.spark').count(),0);assert.equal(await first.locator('[data-average]').count(),0);
  assert.deepEqual(await first.locator('.seg').evaluateAll(s=>s.map(x=>[x.dataset.kind,x.title])),[['rest',W.idle+' 09:12–14:30']]);
  assert.equal(await first.locator('[data-figure="hot_water"] .value').textContent(),W.taps_one);

  // R3 review. The trial run with the request alone: grey, what the E32 would ask, never "Boiler request".
  const shadow=card('shadow_only');
  assert.deepEqual([await shadow.locator('.status').getAttribute('data-status'),await shadow.locator('.status .line').textContent(),
   await shadow.locator('.status .sub').count()],['rest',fill(W.would_ask,{flow:'40'}),0]);
  // The tank heated: the activity's own words, no "running now".
  const charging=card('charging');
  assert.equal(await charging.locator('.status .line').textContent(),activityWord('charging'));
  assert.equal(await charging.locator('[data-running]').count(),0);
  // Imperial: the water in the flow sensor's °F.
  assert.equal(await card('imperial').locator('.status .line').textContent(),fill(W.status_heating,{flow:'106'}).replace('°C','°F'));
  // Failing statistics: the gas sensor's own today and the 6 whole days before it, named an estimate.
  const nostats=card('nostats');
  await nostats.locator('[data-average]').waitFor();
  assert.deepEqual([await nostats.locator('[data-figure="gas"] .label').textContent(),await nostats.locator('[data-figure="gas"] .value').textContent(),
   await nostats.locator('[data-average]').textContent(),await nostats.locator('.spark').count()],
   [W.gas_estimate,n(1.4,1)+NB+'m³',fill(W.per_day,{n:'6',value:n(2,1)+' m³'}),0]);
  // Today answered with the running total of a total-increasing sensor: never shown as today's figure; the day's own
  // row, and the line of daily values (no cumulative rise at its end).
  const cumulative=card('cumulative');
  await cumulative.locator('.spark').waitFor();
  assert.deepEqual(await cumulative.locator('[data-figure="gas"] .value, [data-figure="starts"] .value').allTextContents(),
   [n(2,1)+NB+'m³','14']);
  assert.equal(await cumulative.locator('svg.spark').getAttribute('aria-label'),
   fill(W.week,{values:[2.1,2.6,1.9,2.4,3.0,2.2,2.0].map(v=>n(v,1)).join('; ')+NB+'m³'}));
  // A holiday ten days on ends on a date; a temporary target tomorrow morning says "tomorrow"; neither repeats its target.
  const line=key=>words['component.open_thermostat.entity.sensor.room_reason.state_attributes.line.state.'+key];
  const [far,tomorrow]=await page.evaluate(([end,next,lang])=>[
   new Date(end).toLocaleString(lang,{weekday:'short',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Europe/Amsterdam'}),
   new Intl.RelativeTimeFormat(lang,{numeric:'auto'}).format(1,'day')+' '+
    new Date(next).toLocaleTimeString(lang,{hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Europe/Amsterdam'})],[HOLIDAY_END,TOMORROW_7,lang]);
  assert.match(far,/14/,'the date');
  assert.equal(await card('holiday').locator('.why').textContent(),fill(line('holiday'),{until:far,target:'15'}));
  assert.equal(await card('temporary').locator('.why').textContent(),fill(line('temporary_until'),{until:tomorrow,target:'22'}));

  // 8. Yesterday in figures (the Learning view), as the sketch: two by two, the label small and muted, the value 22 px bold.
  const yesterday=name=>page.locator(`openthermostat-yesterday[data-card="${name}"]`);
  const sensorName=key=>words[`component.open_thermostat.entity.sensor.${key}.name`];
  const figures=async name=>yesterday(name).locator('.figure').evaluateAll(f=>f.map(x=>[x.dataset.figure,x.querySelector('.label').textContent,
   x.querySelector('.value').textContent,x.classList.contains('p2')]));
  assert.deepEqual(await figures('full'),[['room',fill(W.warm,{room:'Woonkamer'}),fill(W.early,{m:'4'}),false],
   ['starts',sensorName('burner_starts_per_heating_hour'),n(1.3,1),false],['gas',sensorName('heating_gas_yesterday'),n(18.2,1)+NB+'kWh',false],
   ['degree_days',W.degree_days,n(9.2,1),false]]);
  assert.deepEqual(await figures('late'),[['room',fill(W.warm,{room:'Badkamer'}),fill(W.late,{m:'12'}),false],
   ['starts',sensorName('burner_starts_per_heating_hour'),'—',false],['gas',sensorName('heating_gas_yesterday'),n(18.2,1)+NB+'kWh',true]]);
  assert.deepEqual(await figures('on_time'),[['room',fill(W.warm,{room:'Slaapkamer'}),W.on_time,true]]);
  // No warm-up yesterday in words, muted (not "—" under "was warm"); 72 minutes as an hour and 12 minutes.
  assert.deepEqual(await figures('none'),[['room',fill(W.warm,{room:'Zolder'}),W.no_warmup,true]]);
  assert.equal(await yesterday('none').locator('.value').evaluate(v=>v.classList.contains('unknown')),true);
  assert.deepEqual(await figures('long'),[['room',fill(W.warm,{room:'Hal'}),fill(W.late_hours,{h:'1',m:'12'}),true]]);
  // 180 min is the firmware's "not warm within 3 hours": said in words, muted; 179 min is still a lateness.
  assert.deepEqual(await figures('never'),[['room',fill(W.warm,{room:'Kelder'}),W.not_warm,true]]);
  assert.equal(await yesterday('never').locator('.value').evaluate(v=>v.classList.contains('unknown')),true);
  assert.deepEqual(await figures('almost'),[['room',fill(W.warm,{room:'Zolder'}),fill(W.late_hours,{h:'2',m:'59'}),true]]);
  assert.equal(await yesterday('almost').locator('.value').evaluate(v=>v.classList.contains('unknown')),false);
  if(lang==='nl')assert.equal(W.not_warm,'niet warm binnen 3 uur');
  if(lang==='pl')assert.equal(W.not_warm,'nie ciepło w ciągu 3 godz.');
  const ylook=await yesterday('full').evaluate(el=>{const r=el.shadowRoot,g=(q,k)=>getComputedStyle(r.querySelector(q))[k];
   return {size:g('.value','fontSize'),weight:g('.value','fontWeight'),value:g('.value','color'),label:g('.label','color'),
    boxes:[...r.querySelectorAll('.figure')].map(f=>{const b=f.getBoundingClientRect();return [b.x,b.y];}),
    bottoms:[...r.querySelectorAll('.value')].map(v=>Math.round(v.getBoundingClientRect().bottom))};});
  assert.deepEqual([ylook.size,ylook.weight,ylook.value,ylook.label],['22px','700',RGB[theme].text,RGB[theme].muted]);
  const yb=ylook.boxes;
  assert(yb[0][1]===yb[1][1]&&yb[2][1]===yb[3][1]&&yb[2][1]>yb[0][1]&&yb[0][0]===yb[2][0],'a pair of pairs');
  assert(ylook.bottoms[0]===ylook.bottoms[1]&&ylook.bottoms[2]===ylook.bottoms[3],'the values of a row on one line');
  // A tap (or Enter) shows that figure's history.
  await yesterday('full').locator('[data-figure="gas"]').click();
  await yesterday('full').locator('[data-figure="room"]').focus();await page.keyboard.press('Enter');
  assert.deepEqual(await page.evaluate(()=>moreInfo.slice(-2)),['sensor.heating_gas_yesterday','sensor.woonkamer_warm_on_time']);
  // A redraw keeps the keyboard focus.
  await page.evaluate(()=>{const next={...hass,states:{...hass.states,'sensor.woonkamer_warm_on_time':{...hass.states['sensor.woonkamer_warm_on_time'],state:'-6'}}};
   document.querySelector('openthermostat-yesterday[data-card=full]').hass=next;});
  assert.equal(await yesterday('full').locator('[data-figure="room"] .value').textContent(),fill(W.early,{m:'6'}));
  assert.equal(await yesterday('full').evaluate(c=>c.shadowRoot.activeElement?.dataset.figure),'room');

  // Phone width first: nothing scrolls sideways, no figure or line is cut off.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  const cut=await page.locator('openthermostat-house,openthermostat-yesterday').evaluateAll(cards=>cards.flatMap(c=>[...c.shadowRoot.querySelectorAll(
   '.figure,.status,.strip,.today,.words,.value,.trend,.boiler')].filter(x=>x.scrollWidth>x.clientWidth+1).map(x=>c.dataset.card+' '+x.className)));
  assert.deepEqual(cut,[]);
  await page.mouse.click(2,2);  // the screenshots without a keyboard focus ring
  await shot(page,{path:path.join(out,`${lang}-${width}-${theme}.png`),fullPage:true});
  for(const name of ['heating','water','idle','problem'])await shot(card(name),{path:path.join(out,`${lang}-${width}-${theme}-${name}.png`)});
  await shot(yesterday('full'),{path:path.join(out,`${lang}-${width}-${theme}-yesterday.png`)});

  if(reads){
   // The reads: Home Assistant only (never the E32), each card once, with the house's midnight; the Yesterday figures ask nothing.
   const calls=await page.evaluate(()=>calls.slice());
   const history=calls.filter(c=>c.type==='history/history_during_period'),week=calls.filter(c=>c.type==='recorder/statistics_during_period');
   assert.deepEqual(history.map(c=>c.entity_ids[0]).sort(),Object.values(CARDS).filter(c=>c.config.activity).map(c=>c.config.activity).sort());
   assert.deepEqual(history[0],{type:'history/history_during_period',start_time:new Date(MIDNIGHT).toISOString(),entity_ids:[history[0].entity_ids[0]],
    minimal_response:true,no_attributes:true});
   // The 7 whole days before today (the average day) and today: from the midnight 7 days ago.
   assert.deepEqual(week.find(c=>c.statistic_ids.includes('sensor.gas_heating')),{type:'recorder/statistics_during_period',
    start_time:new Date(MIDNIGHT-7*DAY).toISOString(),period:'day',statistic_ids:[...GAS,'sensor.burner_starts'],types:['change']});
   assert.deepEqual(calls.find(c=>c.type==='recorder/statistic_during_period'),{type:'recorder/statistic_during_period',statistic_id:'sensor.gas_heating',
    calendar:{period:'day'},types:['change']});
   assert.equal(new Set(calls.map(c=>c.type)).size,3);
   assert(!JSON.stringify(calls).includes('yesterday')&&!JSON.stringify(calls).includes('warm_on_time'),'the Yesterday figures ask nothing');
   const count=()=>page.evaluate(()=>calls.length),asked=async(type,id)=>(await page.evaluate(()=>calls.slice())).filter(c=>c.type===type
    &&(c.entity_ids||c.statistic_ids||[c.statistic_id]).includes(id)).length;
   const before=await count();
   // Home Assistant sets hass on every change in the house: nothing is asked again.
   await page.evaluate(()=>{const next={...hass,states:{...hass.states,'light.kitchen':{entity_id:'light.kitchen',state:'on',attributes:{}}}};
    document.querySelectorAll('openthermostat-house,openthermostat-yesterday').forEach(c=>c.hass=next);});
   await page.clock.runFor(MIN);
   assert.equal(await count(),before,'a minute later, and after a change elsewhere: nothing asked');
   // The boiler stops heating: shown at once from the state itself, the history asked only 5 minutes after the last read.
   await page.evaluate(now=>{const st={entity_id:'sensor.activity_heating',state:'idle',attributes:{},last_changed:new Date(now).toISOString(),
     last_updated:new Date(now).toISOString()};histories['sensor.activity_heating'].push({s:'idle',lu:now/1000});
    window.hass={...hass,states:{...hass.states,'sensor.activity_heating':st}};document.querySelectorAll('openthermostat-house').forEach(c=>c.hass=hass);},NOW+MIN);
   assert.equal(await count(),before);
   assert.equal(await heating.locator('.status').getAttribute('data-status'),'rest');
   await page.clock.runFor(2*MIN);
   assert.deepEqual(await heating.locator('.seg').evaluateAll(s=>s.slice(-2).map(x=>[x.dataset.kind,x.title])),
    [['heat',W.legend_heating+' 14:05–14:31'],['rest',W.idle+' 14:31–14:33']]);
   assert.equal(await count(),before,'no read within 5 minutes');
   await page.clock.runFor(2*MIN);
   assert.equal(await asked('history/history_during_period','sensor.activity_heating'),2,'read again 5 minutes after the last read');
   assert.equal(await count(),before+1,'only the card whose activity changed');
   // The statistics every 10 minutes, for every card that has them.
   const stats=await asked('recorder/statistics_during_period','sensor.gas_heating');
   await page.clock.runFor(5*MIN);
   assert.equal(await asked('recorder/statistics_during_period','sensor.gas_heating'),stats+4,'10 minutes on: the four cards with gas');
   // A card that left the page asks nothing any more (no poller left running).
   await page.evaluate(()=>document.querySelector('[data-card=first]').remove());
   const gone=await asked('recorder/statistics_during_period','sensor.gas_new');
   await page.clock.runFor(30*MIN);
   assert.equal(await asked('recorder/statistics_during_period','sensor.gas_new'),gone,'removed: nothing asked');
   assert(await asked('recorder/statistics_during_period','sensor.gas_heating')>stats+4,'the cards still on the page go on');
  }
  assert.deepEqual(foreign,[],'no network');
  assert.deepEqual(errors,[]);
  results.push({lang,width,theme,result:'PASS'});await context.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'shipped_card_fixture_hass_no_ha',results,band_contrast:ratios},null,2)+'\n');
 console.log(JSON.stringify({results,band_contrast:ratios,screenshots:out}));
})().catch(error=>{console.error(error);process.exitCode=1;});
