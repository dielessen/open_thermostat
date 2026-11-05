// Home page (E32 rc.5) with simulated HTTP: "What the thermostat has learned" opens with what the E32 knows (a ring with
// the percentage, what it still learns in words: three, the rest under "More"), the boiler's response in one sentence and
// yesterday compared with usual; a room's free heat in words; weather compensation worked out from the house; the flow
// detail names the most the E32 asks of the boiler while that holds the request. /status/heating as the firmware builds it
// (the boiler at the top, the rest in one "insight" object); firmware without them shows none. English on a desktop in
// light, Dutch on a phone in dark.
// Screenshots go to the evidence directory for the visual check. Waits on element state only.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),assets=path.join(root,'data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_HOUSE_INSIGHT_EVIDENCE||path.join(root,'out/house-insight-20261104'));
const plan={schema:1,revision:4,mode:'active',minimum_flow_c:28,maximum_flow_c:60,rooms:[
 {id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'floor',sources:[{type:'ha',id:'climate.woonkamer'}],fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500},
 {id:'slaapkamer',name:'Slaapkamer',state:'active',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'sensor.slaapkamer'}],fallback_centi_c:1800,minimum_centi_c:500,maximum_centi_c:2500}]};
// The insight (Knowledge.h addInsightJson) and free heat (FreeHeat::addJson: rates null below five windows) as
// /status/heating carries them (HeatingController: "boiler" at the top, then "insight" with the boiler again).
const INSIGHT={knowledge:{pct:70,missing:['warmup:slaapkamer','arrival:slaapkamer','boiler_response','curve','house','something_new'],more:1},
 house:{ua_kw_per_k:0.21,kw_per_flow_k:0.43,slope:0.71,state:'learned'},
 boiler:{held:3,rest_s:540,ceiling_c:48,absorbed_kw:7.4,kw_per_k:0.36,state:'learned',return:true},
 insights:[{kind:'gas_per_dd_up',pct:34},{kind:'warmup_slower',pct:40,room:'slaapkamer'}]};
const copy=v=>JSON.parse(JSON.stringify(v));
const fixture=()=>({schema:1,revision:4,mode:'active',request:{heat:true,flow_c:48,reason:'heating'},
 rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',status:'ok',temperature:20.5,setpoint:21,demand:true},
  {id:'slaapkamer',name:'Slaapkamer',state:'active',status:'ok',temperature:18,setpoint:18,demand:false}],
 ble_sensors:[],away:{on:false,source:'none',target_c:15,until:null,presence:'home',mode:'auto'},
 flow:{source:'curve',rule_flow_c:44,settings:{weather_curve:true,apply_learned:true,curve_design_flow_c:0},applied_flow_c:48,cap_c:60,ceiling_c:48,
  curve:{state:'applied',flow_c:46,slope:0.71,slope_source:'house',design_flow_c:55,windows:2,last:'collecting'},
  learned:{state:'held',flow_c:52,room:'woonkamer'},optimum_start:{state:'none',room:null,start_utc:null}},
 learned:{schema:1,applied:true,status:'learning',outdoor_c:5,rooms:[
  {id:'woonkamer',emitter:'floor',readiness:'learning',segments:2,periods:1,loss_per_h:null,advice:[]},
  {id:'slaapkamer',emitter:'radiator',readiness:'learning',segments:3,periods:2,loss_per_h:null,advice:[],
   free_heat:{rate:[0,null,0.2,0.4,null,null],n:[9,0,6,7,3,0],applied_min:12}}]},
 tuning:{state:'active',values:{min_on_s:300,min_off_s:300,heat_start_c:0.2,heat_stop_c:0.2,flow_per_degree_c:10,curve_correction_pct:50,
  floor_lead_min_per_c:120,radiator_lead_min_per_c:45,learned_accept_pct:100,night_saving_min_pct:2},manual:[],yesterday:null,today:null,would:[],log:[]},
 boiler:copy(INSIGHT.boiler),insight:copy(INSIGHT)});
// The boiler's object in both places, as the firmware sends it.
const boilerIs=(status,boiler)=>{status.boiler=copy(boiler);status.insight.boiler=copy(boiler);};
const WORDS={
 en:{ring:'The E32 knows your house: 70 %',title:'The E32 knows your house',missingTitle:'Still to learn',
  missing:['It still has to see how fast Slaapkamer warms up.','It still has to check whether Slaapkamer is warm on time.',
   'It is still listening to how your boiler holds its temperature.','It is still learning how much warmer the water must be when it gets colder outside.',
   'It is still working out how fast your house loses heat.','And 2 more.'],more:'More',
  boiler:'Your boiler holds about 50 °C and rests 9 minutes; near the target the E32 asks at most 48 °C.',
  insightsTitle:'Yesterday compared with usual',
  insights:['Yesterday used 34 % more gas per degree of cold than usual. A window or door left open, or a room set warmer, can cause this.',
   'Yesterday Slaapkamer warmed up 40 % more slowly than usual. A window left open, a closed radiator valve or furniture in front of the radiator can slow a room down.'],
  free:'In the afternoon this room warms up by itself, about 0.4 °C per hour (sun, cooking or people). Its next warm-up starts 12 min later, so Smart warm-up does not heat what comes for free.',
  boilerOff:'Your boiler holds about 50 °C and rests 9 minutes. With Smart warm-up on, the E32 would ask at most 48 °C near the target.',
  boilerOutput:'Your boiler has not held a water temperature by itself yet; every degree the water is warmer than the rooms gives your house about 0.25 kW. The E32 keeps listening.',
  house:'Weather compensation, estimated from your house: the water gets about 0.71 °C warmer for every degree colder outside.',
  curveState:'Weather compensation: estimated from your house for now, learning more (2 of 6 steady periods).',
  ceiling:['Asks at most (learned from your boiler)','48 °C'],learnedRow:['Learned water temperature','Limited by your boiler · 52 °C'],
  done:'It has learned everything it needs; it keeps checking as the seasons change.',
  noReturn:'Your boiler does not report the water coming back, so the E32 cannot see how much heat your house takes; it still learns how your boiler holds its temperature.'},
 nl:{ring:'De E32 kent je huis: 70 %',title:'De E32 kent je huis',missingTitle:'Nog te leren',
  missing:['Hij moet nog zien hoe snel Slaapkamer opwarmt.','Hij moet nog nagaan of Slaapkamer op tijd warm is.',
   'Hij luistert nog hoe je ketel zijn temperatuur vasthoudt.','Hij leert nog hoeveel warmer het water moet zijn als het buiten kouder wordt.',
   'Hij rekent nog uit hoe snel je huis warmte verliest.','En nog 2.'],more:'Meer',
  boiler:'Je ketel houdt ongeveer 50 °C vast en rust 9 minuten; dicht bij de doeltemperatuur vraagt de E32 hoogstens 48 °C.',
  insightsTitle:'Gisteren vergeleken met normaal',
  insights:['Gisteren ging er 34 % meer gas per graad kou door dan normaal. Een raam of deur die openstond, of een ruimte die warmer is ingesteld, kan dit veroorzaken.',
   'Gisteren warmde Slaapkamer 40 % langzamer op dan normaal. Een open raam, een dichte radiatorkraan of meubels voor de radiator kunnen een ruimte vertragen.'],
  free:'\'s Middags warmt deze ruimte vanzelf op, ongeveer 0,4 °C per uur (zon, koken of mensen). De volgende opwarming begint daardoor 12 min later, zodat Slim opwarmen niet verwarmt wat gratis komt.',
  boilerOff:'Je ketel houdt ongeveer 50 °C vast en rust 9 minuten. Met Slim opwarmen aan zou de E32 dicht bij de doeltemperatuur hoogstens 48 °C vragen.',
  boilerOutput:'Je ketel heeft nog niet zelf een watertemperatuur vastgehouden; elke graad dat het water warmer is dan de ruimtes, geeft je huis ongeveer 0,25 kW. De E32 blijft luisteren.',
  house:'Weerafhankelijke regeling, geschat uit je huis: het water wordt ongeveer 0,71 °C warmer voor elke graad kouder buiten.',
  curveState:'Weerafhankelijke regeling: voorlopig geschat uit je huis, hij leert nog bij (2 van 6 rustige periodes).',
  ceiling:['Vraagt hoogstens (geleerd van je ketel)','48 °C'],learnedRow:['Geleerde watertemperatuur','Begrensd door je ketel · 52 °C'],
  done:'Hij heeft alles geleerd wat hij nodig heeft; hij blijft het controleren als de seizoenen wisselen.',
  noReturn:'Je ketel meldt het terugkomende water niet, dus de E32 kan niet zien hoeveel warmte je huis opneemt; hij leert wel hoe je ketel zijn temperatuur vasthoudt.'}};
const texts=list=>list.evaluateAll(l=>l.map(e=>e.textContent.replace(/\s+/g,' ').trim()));
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,scheme,lang] of [[1280,'light','en'],[390,'dark','nl']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme,locale:lang==='nl'?'nl-NL':'en-GB',timezoneId:'Europe/Amsterdam'}),errors=[];
  let status=fixture();
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://opth.test/**',async r=>{
   const p=new URL(r.request().url()).pathname;
   const json=(body,code=200)=>r.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'b'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(status);
   if(p==='/config/heating')return json(plan);
   if(p==='/config/heating/flow')return json({weather_curve:true,apply_learned:true,curve_design_flow_c:0,tuning:status.tuning.values,tuning_manual:[]});
   if(p==='/week-editor.js')return r.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>{sessionStorage.removeItem('ot-rooms-edit');loadNativePage('house');});
  const words=WORDS[lang],learned=page.locator('[data-house-learned]'),knows=learned.locator('[data-learned-knows]');
  const push=()=>page.evaluate(async()=>{const s=await (await fetch('/status/heating')).json();document.getElementById('house-settings').dispatchEvent(new CustomEvent('heating-status',{detail:s}));});
  await knows.locator('[data-knowledge-ring]').waitFor();
  // The ring: 70 % filled, the percentage inside, its name for a screen reader.
  const ring=knows.locator('[data-knowledge-ring]');
  assert.equal(await ring.getAttribute('aria-label'),words.ring);
  assert.equal(await ring.locator('[data-knowledge-pct]').textContent(),'70 %');
  const arc=(await ring.locator('[data-knowledge-arc]').getAttribute('stroke-dasharray')).split(' ').map(Number);
  assert(Math.abs(arc[0]/arc[1]-0.7)<0.001,'the ring is filled 70 %');
  assert.equal(await knows.locator('.hl-knows-title').innerText(),words.title);
  // What it still learns: the first three, the rest (and a key this page does not know, counted) under "More".
  assert.equal(await knows.locator('[data-knowledge-missing] h4').innerText(),words.missingTitle);
  assert.deepEqual(await texts(knows.locator('[data-knowledge-missing] li')),words.missing);
  assert.equal(await knows.locator('[data-knowledge-missing] li').nth(2).isVisible(),true);
  assert.equal(await knows.locator('[data-knowledge-missing] li').nth(3).isVisible(),false);
  assert.equal(await knows.locator('[data-knowledge-missing] summary').innerText(),words.more);
  // The boiler's response and yesterday compared with usual.
  assert.equal(await knows.locator('[data-boiler-line]').innerText(),words.boiler);
  assert.equal(await knows.locator('[data-learned-insights] h3').innerText(),words.insightsTitle);
  assert.deepEqual(await texts(knows.locator('[data-insight-list] li')),words.insights);
  // A room's free heat (under the room's "More"), and weather compensation worked out from the house.
  const bedroom=learned.locator('.hl-room[data-room=slaapkamer]');
  assert((await texts(bedroom.locator('li'))).includes(words.free),'the bedroom says its free heat');
  assert.equal((await texts(learned.locator('.hl-room[data-room=woonkamer] li'))).some(t=>/°C (per hour|per uur)/.test(t)),false);
  assert((await texts(learned.locator('[data-learned-house] li'))).some(t=>t.startsWith(words.house)),'the house list says where the curve comes from');
  // Heating settings: what weather compensation uses now, and the most the E32 asks while the boiler's own response holds it.
  const flow=page.locator('[data-heating-flow-options]');
  await flow.locator('[data-curve-state]').filter({hasText:words.curveState}).waitFor();
  const facts=await flow.locator('[data-flow-status]').evaluate(dl=>[...dl.querySelectorAll('dt')].map(dt=>[dt.textContent,dt.nextElementSibling.textContent]));
  assert(facts.some(([k,v])=>k===words.ceiling[0]&&v===words.ceiling[1]),JSON.stringify(facts));
  assert(facts.some(([k,v])=>k===words.learnedRow[0]&&v===words.learnedRow[1]),JSON.stringify(facts));
  // Phone width first: nothing scrolls sideways; the panel follows the theme.
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  await learned.screenshot({path:path.join(out,`${lang}-${width}-${scheme}-learning.png`)});
  // The boiler only inside "insight" says the same.
  status=fixture();delete status.boiler;await push();
  assert.equal(await knows.isVisible(),true);assert.equal(await knows.locator('[data-boiler-line]').innerText(),words.boiler);
  // "Asks at most" only with the ceiling in effect (flow.ceiling_c); with Smart warm-up off the learned one waits for it.
  status=fixture();status.flow.ceiling_c=null;status.flow.settings.apply_learned=false;await push();
  await page.waitForFunction(([text])=>document.querySelector('[data-boiler-line]').textContent===text,[words.boilerOff]);
  // Still collecting, but the emitters' output per K is known (what the E32 knows counts the boiler as learned then).
  status=fixture();boilerIs(status,{held:0,rest_s:null,ceiling_c:null,absorbed_kw:6.1,kw_per_k:0.25,state:'collecting',return:true});await push();
  await page.waitForFunction(([text])=>document.querySelector('[data-boiler-line]').textContent===text,[words.boilerOutput]);
  // Everything learned; another boiler state; nothing stood out yesterday.
  status=fixture();status.insight.knowledge={pct:100,missing:[],more:0};boilerIs(status,{state:'no_return',return:false});status.insight.insights=[];
  await push();
  await knows.locator('.hl-done').waitFor();
  assert.equal(await knows.locator('.hl-done').innerText(),words.done);
  assert.equal(await knows.locator('[data-boiler-line]').innerText(),words.noReturn);
  assert.equal(await knows.locator('[data-learned-insights]').isVisible(),false);
  // The ceiling row only while it holds the request.
  status.flow.learned.state='not_ready';status.flow.applied_flow_c=44;await push();
  await page.waitForFunction(([label])=>![...document.querySelectorAll('[data-flow-status] dt')].some(dt=>dt.textContent===label),[words.ceiling[0]]);
  // Firmware before rc.5: no knowledge, boiler or insights, no free heat: the block and the line are gone.
  status=fixture();delete status.boiler;delete status.insight;delete status.flow.ceiling_c;delete status.learned.rooms[1].free_heat;await push();
  await knows.waitFor({state:'hidden'});
  assert.equal((await texts(bedroom.locator('li'))).includes(words.free),false);
  assert.deepEqual(errors,[]);
  results.push({width,scheme,lang,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify({results,screenshots:out}));
})().catch(error=>{console.error(error);process.exitCode=1;});
