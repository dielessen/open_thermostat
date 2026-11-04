// The Overview's house card (E32 rc.5, frontend/house-card.js) with the integration's real translations, a fixture hass
// and Home Assistant's history and statistics answered by the test itself; no HA, no device and no network (every
// request is answered here, any other fails the test). Per card: the strip in the colour of what the boiler does
// (heating, hot water, resting, a problem that leads to Repairs, waiting for the E32), the figures (the one room switched
// on, heating, hot water, gas today with its last 7 days, burner starts), the day so far from midnight with its
// tooltips and spoken sentence, a card with one entity and a card without data. Then the reads: Home Assistant only,
// the history again only after a change and 5 minutes, the statistics every 10, nothing after the card left the page.
// English, Dutch and Polish; light and dark; desktop, phone and a narrow phone (no sideways scroll). Screenshots go to
// the evidence directory for the visual check.
const {chromium}=require('playwright-core');
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
// The card keeps a figure and its unit together (a no-break space before °C, m³ and kWh).
const fill=(text,values={})=>text.replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all).replace(/ (°C|m³|kWh)/g,NB+'$1');
// Wednesday 4 November 2026, 14:30 in Amsterdam (UTC+1, no clock change in the last 7 days).
const NOW=Date.parse('2026-11-04T13:30:00Z'),MIDNIGHT=Date.parse('2026-11-03T23:00:00Z'),DAY=86400000,MIN=60000;
const at=(h,m=0)=>MIDNIGHT+(h*60+m)*MIN;
// The boiler until 12:40: heating twice in the morning with a tap in between, keeping warm, a tap, heating at noon.
const DAYLOG=[['idle',0,0],['heating',5,40],['tapping',6,55],['heating',6,58],['idle',7,30],['keep_warm',8,10],['idle',8,25],
 ['tapping',11,0],['idle',11,2],['heating',12,0],['idle',12,40]];
const history=(...more)=>[...DAYLOG.map(([s,h,m])=>({s,lu:at(h,m)/1000})),...more.map(([s,t])=>({s,lu:t/1000}))];
// Gas (m³) and burner starts per day: six days and today so far (the hourly statistics lag; "today" is the 5-minute one).
const WEEK={'sensor.gas_heating':[2.1,2.6,1.9,2.4,3.0,2.2,1.2],'sensor.gas_hot_water':[0.5,0.4,0.6,0.5,0.4,0.5,0.3],
 'sensor.burner_starts':[18,22,15,20,25,19,11]};
const TODAY={'sensor.gas_heating':1.6,'sensor.gas_hot_water':0.4,'sensor.burner_starts':14};
const SPARK=[2.6,3.0,2.5,2.9,3.4,2.7,2.0];
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
   problem:'binary_sensor.problem_heating',rooms:[{entity:'sensor.woonkamer_reason',name:'Woonkamer'}]},
  states:[ent('sensor.req_heating',45,{rooms:rooms('woonkamer'),mode:'shadow'}),ent('sensor.activity_heating','heating',{},at(14,5)),
   ent('sensor.ch_heating','on'),ent('sensor.flow','41.3',{unit_of_measurement:'°C'}),ent('sensor.dhw_heating','off'),ent('sensor.taps_heating','3'),
   ent('sensor.gas_heating','1234.56',M3),ent('sensor.gas_hot_water','321.04',M3),ent('sensor.burner_starts','2088'),ent('select.house_mode','auto'),
   ent('binary_sensor.problem_heating','off'),ent('sensor.woonkamer_reason','warm_up',{room_id:'woonkamer',line:'warm_up',
    values:{time:new Date(at(17)).toISOString(),target:21},temperature:20.4,setpoint:21,presence:'room_home',window:null})],
  history:history(['heating',at(14,5)])},
 water:{config:{request:'sensor.req_water',activity:'sensor.activity_water',heating:'sensor.ch_water',flow:'sensor.flow',hot_water:'sensor.dhw_water',
   taps:'sensor.taps_water',gas:GAS,starts:'sensor.burner_starts',mode:'select.house_mode_home',problem:'binary_sensor.problem_water'},
  states:[ent('sensor.req_water',0,{rooms:rooms()}),ent('sensor.activity_water','tapping',{},at(14,25)),ent('sensor.ch_water','off'),
   ent('sensor.dhw_water','on'),ent('sensor.taps_water','4'),ent('select.house_mode_home','home'),ent('binary_sensor.problem_water','off')],
  history:history(['tapping',at(14,25)])},
 idle:{config:{request:'sensor.req_idle',activity:'sensor.activity_idle',taps:'sensor.taps_idle',gas:GAS,starts:'sensor.burner_starts',
   mode:'select.house_mode'},
  states:[ent('sensor.req_idle',38,{rooms:rooms('woonkamer','badkamer')}),ent('sensor.activity_idle','idle',{},at(12,40)),ent('sensor.taps_idle','0')],
  history:history()},
 problem:{config:{request:'sensor.req_problem',activity:'sensor.activity_problem',flow:'sensor.flow',taps:'sensor.taps_heating',gas:GAS,
   starts:'sensor.burner_starts',mode:'select.house_mode_away',problem:'binary_sensor.problem'},
  states:[ent('sensor.req_problem',45,{rooms:rooms('woonkamer')}),ent('sensor.activity_problem','heating',{},at(14,5)),
   ent('select.house_mode_away','away'),ent('binary_sensor.problem','on',{reason:'Waiting for your confirmation (+1)',reasons:REASONS,problems:['a','b']})],
  history:history(['heating',at(14,5)])},
 partial:{config:{request:'sensor.req_partial'},states:[ent('sensor.req_partial',45,{rooms:rooms('badkamer')})],history:[]},
 unknown:{config:{request:'sensor.req_unknown',activity:'sensor.activity_unknown',heating:'sensor.ch_unknown',taps:'sensor.taps_unknown',
   gas:['sensor.gas_unknown'],starts:'sensor.starts_unknown',mode:'select.house_mode'},
  states:[ent('sensor.req_unknown','unavailable'),ent('sensor.activity_unknown','unknown'),ent('sensor.ch_unknown','unavailable'),
   ent('sensor.taps_unknown','unknown'),ent('sensor.gas_unknown','unknown',M3),ent('sensor.starts_unknown','unknown')],history:[]},
 first:{config:{request:'sensor.req_first',activity:'sensor.activity_first',heating:'sensor.ch_first',taps:'sensor.taps_first',
   gas:['sensor.gas_new'],starts:'sensor.starts_new'},
  states:[ent('sensor.req_first',0,{rooms:rooms()}),ent('sensor.activity_first','idle',{},at(9,12)),ent('sensor.ch_first','off'),
   ent('sensor.taps_first','1'),ent('sensor.gas_new','0.0',M3),ent('sensor.starts_new','0')],history:[{s:'idle',lu:at(9,12)/1000}]},
};
const THEMES={light:'--primary-text-color:#212121;--secondary-text-color:#6b6b6b;--card-background-color:#fff;--secondary-background-color:#e5e5e5;'+
  '--divider-color:rgba(0,0,0,.12);--primary-color:#03a9f4;--state-climate-heat-color:#ff8100;--info-color:#039be5;--error-color:#db4437;'+
  '--warning-color:#ffa600;--success-color:#43a047;--disabled-text-color:#bdbdbd;background:#fafafa',
 dark:'--primary-text-color:#e1e1e1;--secondary-text-color:#9b9b9b;--card-background-color:#1c1c1c;--secondary-background-color:#282828;'+
  '--divider-color:rgba(225,225,225,.12);--primary-color:#03a9f4;--state-climate-heat-color:#ff8100;--info-color:#039be5;--error-color:#db4437;'+
  '--warning-color:#ffa600;--success-color:#43a047;--disabled-text-color:#6f6f6f;background:#111'};
const RGB={light:{text:'rgb(33, 33, 33)',muted:'rgb(107, 107, 107)',surface:'rgb(255, 255, 255)',line:'rgb(0, 135, 111)'},
 dark:{text:'rgb(225, 225, 225)',muted:'rgb(155, 155, 155)',surface:'rgb(28, 28, 28)',line:'rgb(35, 156, 138)'}};
const UNAVAILABLE={en:'Unavailable',nl:'Niet beschikbaar',pl:'Niedostępny'},UNKNOWN={en:'Unknown',nl:'Onbekend',pl:'Nieznany'};
// WCAG contrast of two "rgb(…)"/"color(srgb …)" colours (the second opaque).
const channels=c=>{const m=c.match(/rgba?\(([^)]+)\)/);if(m)return m[1].split(',').map(Number);
 const s=c.match(/color\(srgb ([^)]+)\)/);if(s)return s[1].split(/\s+/).map((v,i)=>i<3?Number(v)*255:Number(v));throw new Error('colour '+c);};
const luminance=([r,g,b])=>{const f=v=>{v/=255;return v<=0.03928?v/12.92:((v+0.055)/1.055)**2.4;};return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b);};
const contrast=(fg,bg)=>{const [a,b]=[luminance(channels(fg)),luminance(channels(bg))].sort((x,y)=>y-x);return (a+0.05)/(b+0.05);};

(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
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
  await page.evaluate(({cards,lang,dict,dark,week,today,midnight,unavailable,unknown})=>{
   const localize=(key,values={})=>(dict[key]||'').replace(/\{(\w+)\}/g,(all,k)=>k in values?values[k]:all);
   const states={};for(const card of Object.values(cards))for(const st of card.states)states[st.entity_id]=st;
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
    if(msg.type==='recorder/statistics_during_period')return Object.fromEntries(msg.statistic_ids.filter(id=>week[id])
     .map(id=>[id,week[id].map((change,i)=>({start:midnight-(6-i)*86400000,end:midnight-(5-i)*86400000,change}))]));
    if(msg.type==='recorder/statistic_during_period')return msg.statistic_id in today?{change:today[msg.statistic_id]}:{};
    throw new Error('not answered: '+msg.type);};
   window.hass={language:lang,locale:{language:lang,time_format:'24',time_zone:'server'},config:{time_zone:'Europe/Amsterdam'},
    themes:{darkMode:dark},states,localize,formatEntityState,callWS};
   for(const [name,card] of Object.entries(cards)){
    const el=document.createElement('openthermostat-house');el.dataset.card=name;el.setConfig(card.config);
    el.addEventListener('hass-more-info',e=>moreInfo.push(e.detail.entityId));
    const label=document.createElement('h6');label.textContent=name;document.querySelector('main').append(label,el);el.hass=hass;
   }
  },{cards:CARDS,lang,dict:words,dark:theme==='dark',week:WEEK,today:TODAY,midnight:MIDNIGHT,unavailable:UNAVAILABLE[lang],unknown:UNKNOWN[lang]});
  const card=name=>page.locator(`openthermostat-house[data-card="${name}"]`);
  const n=(v,d=0)=>v.toLocaleString(lang,{minimumFractionDigits:d,maximumFractionDigits:d});
  // Everything read: the gas figure and the day strip carry Home Assistant's answers.
  await card('heating').locator('.spark').waitFor();await card('heating').locator('.seg.keep').waitFor();
  const activityWord=state=>words['component.open_thermostat.entity.sensor.boiler_activity.state.'+state];
  const modeWord=state=>words['component.open_thermostat.entity.select.house_mode.state.'+state];

  // 1. Heating, with the one room switched on inside: the strip, the figures and the day so far.
  const heating=card('heating');
  assert.equal(await heating.locator('.wrap').getAttribute('aria-label'),W.title);
  assert.equal(await heating.locator('.status').getAttribute('data-status'),'heat');
  assert.equal(await heating.locator('.status .line').textContent(),fill(W.status_heating,{flow:'41'}));
  // The living room is in the card: the request without "1 room wants heat" (the room says it itself).
  assert.equal(await heating.locator('.status .sub').textContent(),fill(W.request,{flow:'45'}));
  assert.equal(await heating.locator('.chip span').textContent(),modeWord('auto'));
  assert.equal(await heating.locator('.chip').getAttribute('aria-label'),fill(W.mode,{mode:modeWord('auto')}));
  assert.deepEqual(await heating.locator('.figure').evaluateAll(f=>f.map(x=>x.dataset.figure)),['room','heating','hot_water','gas','starts']);
  const room=heating.locator('.figure.room');
  assert.equal(await room.locator('.label > span').textContent(),'Woonkamer');
  assert.equal(await room.locator('.value').textContent(),n(20.4,1)+'→21'+NB+'°C');
  assert.equal(await room.locator('.why span').textContent(),
   fill(words['component.open_thermostat.entity.sensor.room_reason.state_attributes.line.state.warm_up'],{time:'17:00',target:'21'}));
  assert.equal(await room.locator('[data-presence]').getAttribute('aria-label'),
   words['component.open_thermostat.entity.sensor.room_reason.state_attributes.presence.state.room_home']);
  const value=name=>heating.locator(`[data-figure="${name}"] .value`).textContent();
  assert.equal(await value('heating'),fill(W.heating_on,{flow:'41'}));
  assert.equal(await value('hot_water'),fill(W.taps,{n:'3'}));
  assert.equal(await heating.locator('[data-running]').count(),0);
  assert.equal(await value('gas'),n(2,1)+NB+'m³');
  assert.equal(await value('starts'),'14');
  assert.deepEqual(await heating.locator('.figure .label').evaluateAll(l=>l.map(x=>(x.querySelector('span')||x).textContent)),
   ['Woonkamer',W.heating,W.hot_water,W.gas_today,W.starts_today]);
  // The sparkline: 7 days, a 2 px line in the E32 colour scaled to its own range; today (a day still running) joins it
  // lighter and is the dot of 8 px with a 2 px ring in the card colour; no grid.
  const spark=heating.locator('svg.spark');
  assert.equal(await spark.getAttribute('aria-label'),fill(W.week,{values:SPARK.map(v=>n(v,1)).join('; ')+NB+'m³'}));
  const marks=await spark.evaluate(s=>{const [p,q]=s.querySelectorAll('path'),c=s.querySelector('circle'),g=(e,k)=>getComputedStyle(e)[k];
   const ys=p.getAttribute('d').split(/[ML]/).filter(Boolean).map(xy=>Number(xy.split(',')[1]));
   return {d:p.getAttribute('d'),stroke:g(p,'stroke'),width:g(p,'strokeWidth'),fill:g(p,'fill'),opacity:g(p,'strokeOpacity'),
    partial:q.getAttribute('class'),partialOpacity:g(q,'strokeOpacity'),partialEnd:q.getAttribute('d').split('L')[1],r:c.getAttribute('r'),dot:g(c,'fill'),
    ring:g(c,'stroke'),ringWidth:g(c,'strokeWidth'),cx:c.getAttribute('cx'),cy:c.getAttribute('cy'),h:Number(s.getAttribute('height')),
    w:Number(s.getAttribute('width')),top:Math.min(...ys),grid:s.querySelectorAll('line,rect').length};});
  assert.equal((marks.d.match(/[ML]/g)||[]).join(''),'MLLLLL','six whole days as the line');
  assert.deepEqual([marks.stroke,marks.width,marks.fill,marks.opacity,marks.dot,marks.r,marks.ring,marks.ringWidth,marks.grid],
   [RGB[theme].line,'2px','none','1',RGB[theme].line,'4',RGB[theme].surface,'2px',0]);
  assert.deepEqual([marks.partial,marks.partialOpacity,marks.partialEnd],['partial','0.45',marks.cx+','+marks.cy]);
  assert(Number(marks.cx)>marks.w-10,'the dot is today, at the right end');
  assert(marks.top<=5.01&&Number(marks.cy)>=marks.h-5.01,'its own range: the highest day at the top, today (the lowest) at the bottom');
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
  assert(Math.abs(last.left+last.width-870/1440*100)<0.01,'the strip reaches now (14:30), the rest of the day is a hairline');
  assert(segments[0].cls.includes('first')&&last.cls.includes('last'));
  assert.equal(await heating.locator('.strip').getAttribute('role'),'img');
  assert.equal(await heating.locator('.strip').getAttribute('aria-label'),W.today+': '+[
   W.legend_heating+' 05:40–06:55, 06:58–07:30, 12:00–12:40, 14:05–14:30',W.legend_hot_water+' 06:55–06:58, 11:00–11:02',
   W.legend_keep_warm+' 08:10–08:25'].join('; ')+'.');
  assert.deepEqual(await heating.locator('.ticks span').allTextContents(),['00','06','12','18']);
  assert.deepEqual(await heating.locator('.ticks span').evaluateAll(s=>s.map(x=>parseFloat(x.style.left))),[0,25,50,75]);
  assert.equal(await heating.locator('.today-title').textContent(),W.today);
  assert.deepEqual(await heating.locator('.legend li').allTextContents(),[W.legend_heating,W.legend_hot_water,W.legend_keep_warm]);
  // Colours: Home Assistant's state colours for status, never on text; text in the text colours, readable (≥ 4.5:1).
  const look=await heating.evaluate(el=>{const r=el.shadowRoot,g=(q,k)=>getComputedStyle(r.querySelector(q))[k];
   return {bar:g('.status','borderLeftColor'),barWidth:g('.status','borderLeftWidth'),icon:g('.status .main > ha-icon','color'),line:g('.status .line','color'),
    statusBg:g('.status','backgroundColor'),sub:g('.status .sub','color'),label:g('.figure .label','color'),value:g('.figure .value','color'),
    legend:g('.legend li','color'),tick:g('.ticks span','color'),heat:g('.seg.heat','backgroundColor'),water:g('.seg.water','backgroundColor'),
    keep:g('.seg.keep','backgroundColor'),rest:g('.seg.rest','backgroundColor'),dark:r.querySelector('ha-card').classList.contains('dark')};});
  assert.equal(look.dark,theme==='dark');
  assert.deepEqual([look.bar,look.barWidth,look.icon,look.heat,look.water],['rgb(255, 129, 0)','6px','rgb(255, 129, 0)','rgb(255, 129, 0)','rgb(3, 155, 229)']);
  assert.notEqual(look.keep,look.water,'keeping warm is the lighter hot-water colour');
  assert.deepEqual([look.line,look.value,look.sub,look.label,look.legend,look.tick],
   [RGB[theme].text,RGB[theme].text,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted,RGB[theme].muted]);
  for(const [fg,bg] of [[look.line,look.statusBg],[look.sub,look.statusBg],[look.label,RGB[theme].surface],[look.value,RGB[theme].surface],
   [look.legend,RGB[theme].surface]])assert(contrast(fg,bg)>=4.5,`contrast ${fg} on ${bg}: ${contrast(fg,bg).toFixed(2)}`);
  // Every strip, in every tone: its words readable on its tint.
  const strips=await page.locator('openthermostat-house').evaluateAll(cards=>cards.map(c=>{const s=c.shadowRoot.querySelector('.status');
   return [...s.querySelectorAll('.line,.sub')].map(t=>[c.dataset.card,getComputedStyle(t).color,getComputedStyle(s).backgroundColor]);}).flat());
  assert.equal(new Set(strips.map(([name])=>name)).size,Object.keys(CARDS).length);
  for(const [name,fg,bg] of strips)assert(contrast(fg,bg)>=4.5,`${name}: contrast ${fg} on ${bg}: ${contrast(fg,bg).toFixed(2)}`);
  // Phone: two columns, the room across both; wide: the room the left half, the others two by two beside it.
  const boxes=await heating.locator('.figure').evaluateAll(f=>f.map(x=>{const b=x.getBoundingClientRect();return {x:b.x,y:b.y,w:b.width};}));
  const grid=await heating.locator('.figures').evaluate(g=>g.getBoundingClientRect().width);
  if(width>=1000){
   assert(boxes[0].w>1.9*boxes[1].w&&boxes[0].w<2.3*boxes[1].w,'the room takes two of four columns');
   assert(boxes[1].y===boxes[2].y&&boxes[3].y===boxes[4].y&&boxes[3].y>boxes[1].y&&boxes[1].x===boxes[3].x,'the others two by two');
  }else{
   assert(Math.abs(boxes[0].w-grid)<1,'the room across the card');
   assert(boxes[1].y===boxes[2].y&&boxes[3].y===boxes[4].y&&Math.abs(boxes[1].w-(grid-16)/2)<1,'two columns');
  }

  // 2. Hot water now: the activity's own word, "running now", heating off; the strip ends in hot water.
  const water=card('water');
  assert.equal(await water.locator('.status').getAttribute('data-status'),'water');
  assert.equal(await water.locator('.status .line').textContent(),activityWord('tapping'));
  assert.equal(await water.locator('.status .sub').count(),0);
  assert.equal(await water.locator('.chip span').textContent(),modeWord('home'));
  assert.equal(await water.locator('[data-figure="hot_water"] .value').textContent(),fill(W.taps,{n:'4'}));
  assert.equal(await water.locator('[data-running]').textContent(),W.running);
  assert.equal(await water.locator('[data-figure="heating"] .value').textContent(),W.heating_off);
  assert.deepEqual(await water.locator('.seg').evaluateAll(s=>s.slice(-2).map(x=>[x.dataset.kind,x.title])),
   [['rest',W.idle+' 12:40–14:25'],['water',W.legend_hot_water+' 14:25–14:30']]);
  // 3. Resting while two rooms want heat (trial run): the line under it says so, with the request.
  const idle=card('idle');
  assert.equal(await idle.locator('.status').getAttribute('data-status'),'rest');
  assert.equal(await idle.locator('.status .line').textContent(),W.idle);
  assert.equal(await idle.locator('.status .sub').textContent(),fill(W.wants,{n:'2'})+' · '+fill(W.request,{flow:'38'}));
  assert.equal(await idle.locator('[data-figure="hot_water"] .value').textContent(),W.taps_none);
  assert.deepEqual(await idle.locator('.figure').evaluateAll(f=>f.map(x=>x.dataset.figure)),['heating','hot_water','gas','starts']);
  // 4. A problem wins: red, its reason, all reasons inside; a tap (or Enter) opens Repairs; the chip its own dialog.
  const problem=card('problem'),strip=problem.locator('.status'),link=strip.locator('.main');
  assert.equal(await strip.getAttribute('data-status'),'error');
  assert.equal(await strip.locator('.line').textContent(),fill(W.attention,{reason:'Waiting for your confirmation (+1)'}));
  assert.deepEqual([await link.getAttribute('role'),await link.getAttribute('tabindex')],['link','0']);
  assert.equal(await link.locator('button,[tabindex],[role=link],[role=button]').count(),0,'no control inside the link');
  assert.equal(await heating.locator('.status [role=link]').count(),0,'a link only while there is a problem');
  assert.equal(await problem.locator('.status').evaluate(s=>getComputedStyle(s).borderLeftColor),'rgb(219, 68, 55)');
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
  // 5. One entity only (the request): the status from it, one figure across the card, no strip and no chip.
  const partial=card('partial');
  assert.deepEqual([await partial.locator('.status').getAttribute('data-status'),await partial.locator('.status .line').textContent(),
   await partial.locator('.status .sub').textContent()],['heat',fill(W.request,{flow:'45'}),W.wants_one]);
  assert.deepEqual(await partial.locator('.figure').evaluateAll(f=>f.map(x=>[x.dataset.figure,x.querySelector('.value').textContent,x.classList.contains('p2')])),
   [['heating',W.heating_on_plain,true]]);
  assert.equal(await partial.locator('.today').count(),0);assert.equal(await partial.locator('.chip').count(),0);
  // 6. Nothing reported yet: it says so; every figure "—", no sparkline, no strip.
  const unknown=card('unknown');
  assert.deepEqual([await unknown.locator('.status').getAttribute('data-status'),await unknown.locator('.status .line').textContent()],['wait',W.waiting]);
  assert.deepEqual(await unknown.locator('.figure .value').allTextContents(),['—','—','—','—']);
  assert.equal(await unknown.locator('.spark').count(),0);assert.equal(await unknown.locator('.today').count(),0);
  // 7. The first day: no statistics yet, so "—" and no sparkline; the strip starts where the history does.
  const first=card('first');
  assert.deepEqual(await first.locator('[data-figure="gas"] .value, [data-figure="starts"] .value').allTextContents(),['—','—']);
  assert.equal(await first.locator('.spark').count(),0);
  assert.deepEqual(await first.locator('.seg').evaluateAll(s=>s.map(x=>[x.dataset.kind,x.title])),[['rest',W.idle+' 09:12–14:30']]);
  assert.equal(await first.locator('[data-figure="hot_water"] .value').textContent(),W.taps_one);
  // Phone width first: nothing scrolls sideways, no figure or line is cut off.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  const cut=await page.locator('openthermostat-house').evaluateAll(cards=>cards.flatMap(c=>[...c.shadowRoot.querySelectorAll('.figure,.status,.strip,.today-head,.words')]
   .filter(x=>x.scrollWidth>x.clientWidth+1).map(x=>c.dataset.card+' '+x.className)));
  assert.deepEqual(cut,[]);
  await page.screenshot({path:path.join(out,`${lang}-${width}-${theme}.png`),fullPage:true});
  await heating.screenshot({path:path.join(out,`${lang}-${width}-${theme}-heating.png`)});

  if(reads){
   // The reads: Home Assistant only (never the E32), each card once, with the house's midnight.
   const calls=await page.evaluate(()=>calls.slice());
   const history=calls.filter(c=>c.type==='history/history_during_period'),week=calls.filter(c=>c.type==='recorder/statistics_during_period');
   assert.deepEqual(history.map(c=>c.entity_ids[0]).sort(),Object.values(CARDS).filter(c=>c.config.activity).map(c=>c.config.activity).sort());
   assert.deepEqual(history[0],{type:'history/history_during_period',start_time:new Date(MIDNIGHT).toISOString(),entity_ids:[history[0].entity_ids[0]],
    minimal_response:true,no_attributes:true});
   assert.deepEqual(week.find(c=>c.statistic_ids.includes('sensor.gas_heating')),{type:'recorder/statistics_during_period',
    start_time:new Date(MIDNIGHT-6*DAY).toISOString(),period:'day',statistic_ids:[...GAS,'sensor.burner_starts'],types:['change']});
   assert.deepEqual(calls.find(c=>c.type==='recorder/statistic_during_period'),{type:'recorder/statistic_during_period',statistic_id:'sensor.gas_heating',
    calendar:{period:'day'},types:['change']});
   assert.equal(new Set(calls.map(c=>c.type)).size,3);
   const count=()=>page.evaluate(()=>calls.length),asked=async(type,id)=>(await page.evaluate(()=>calls.slice())).filter(c=>c.type===type
    &&(c.entity_ids||c.statistic_ids||[c.statistic_id]).includes(id)).length;
   const before=await count();
   // Home Assistant sets hass on every change in the house: nothing is asked again.
   await page.evaluate(()=>{const next={...hass,states:{...hass.states,'light.kitchen':{entity_id:'light.kitchen',state:'on',attributes:{}}}};
    document.querySelectorAll('openthermostat-house').forEach(c=>c.hass=next);});
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
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({scope:'shipped_card_fixture_hass_no_ha',results},null,2)+'\n');
 console.log(JSON.stringify({results,screenshots:out}));
})().catch(error=>{console.error(error);process.exitCode=1;});
