// Home page (E32 rc.2) with simulated HTTP: "What the thermostat has learned" (per room: learning progress, how fast it
// warms and cools, the lowest water temperature, the planned start and the night advice; weather compensation, the burner
// and the self-tuning's changes) and "Comfort and boiler care" (the knobs of /config/heating/flow: automatic or set by
// the owner, back to automatic, back to start values). English on a desktop in light, Dutch on a phone in dark.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const plan={schema:1,revision:4,mode:'active',minimum_flow_c:30,maximum_flow_c:55,rooms:[
  {id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'floor',sources:[{type:'ha',id:'climate.woonkamer'}],fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500},
  {id:'slaapkamer',name:'Slaapkamer',state:'active',inactive_until:0,emitter:'radiator',sources:[{type:'ha',id:'sensor.slaapkamer'}],fallback_centi_c:1800,minimum_centi_c:500,maximum_centi_c:2500},
  {id:'zolder',name:'Zolder',state:'inactive',inactive_until:0,emitter:'radiator',sources:[],fallback_centi_c:1500,minimum_centi_c:500,maximum_centi_c:2500}]};
const start=1793257800,rise=1793262600; // Thu 29 Oct 2026 07:30 and 08:50 local
const advice=(flow,warm,ruleFlow,ruleWarm,reason)=>[{shortfall_c:0,flow_c:null,warmup_h:null,reason:'not_ready',rule_flow_c:30,rule_warmup_h:null,rule:'unknown'},
  {shortfall_c:1,required_c_per_h:0.5,flow_c:flow,warmup_h:warm,reason,rule_flow_c:ruleFlow,rule_warmup_h:ruleWarm,rule:'higher_wasteful'}];
const defaults={min_on_s:300,min_off_s:300,heat_start_c:0.2,heat_stop_c:0.2,flow_per_degree_c:10,curve_correction_pct:50,
  floor_lead_min_per_c:120,radiator_lead_min_per_c:45,learned_accept_pct:100,night_saving_min_pct:2};
const fixture=()=>({schema:1,revision:4,mode:'active',request:{heat:true,flow_c:36,reason:'heating'},
  rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',status:'ok',temperature:20.5,setpoint:21,demand:true},
    {id:'slaapkamer',name:'Slaapkamer',state:'active',status:'ok',temperature:18,setpoint:18,demand:false},
    {id:'zolder',name:'Zolder',state:'inactive',status:'inactive',temperature:null,setpoint:null,demand:false}],
  ble_sensors:[],shadow:{today:{s:0},days:[]},away:{on:false,source:'none',target_c:15,until:null,presence:'home',mode:'auto'},
  flow:{source:'rule',settings:{weather_curve:true,apply_learned:true,curve_design_flow_c:0},curve:{state:'applied',flow_c:38,slope:0.62,slope_source:'learned'}},
  learned:{schema:1,applied:true,status:'learning',outdoor_c:5,rooms:[
    {id:'woonkamer',emitter:'floor',readiness:'ready',segments:9,periods:4,loss_per_h:0.02,advice:advice(34,1.5,40,1.25,'learned')},
    {id:'slaapkamer',emitter:'radiator',readiness:'learning',segments:3,periods:2,loss_per_h:null,advice:advice(null,null,40,null,'not_ready')}],
   plans:{rooms:[{id:'woonkamer',optimum_start:{reason:'planned',next_switch:{utc:rise,target_c:21},predicted_start_utc:start,lead_minutes:80,flow_c:34,confidence:'learned',reachable:true,start_now:false},
     night:{reason:'estimated',confidence:'calibrated',recommended:'hold_0_5',recommended_night_c:19,saving_m3:0.12,saving_eur:0.15}},
    {id:'slaapkamer',optimum_start:{reason:'planned',next_switch:{utc:rise,target_c:18},predicted_start_utc:start+3000,lead_minutes:30,flow_c:40,confidence:'default',reachable:true,start_now:false},
     night:{reason:'estimated',confidence:'low',recommended:'program',recommended_night_c:16,saving_m3:0,saving_eur:null}}]}},
  tuning:{state:'active',values:{...defaults,min_off_s:600,heat_stop_c:0.15},manual:['min_off_s'],
   yesterday:{starts:59,heating_h:14,burns:58,burn_s:420},today:{starts:12,heating_h:5},would:[],
   log:[[1793232000,'heat_stop_c',0.2,0.15,'overshoot',0.6,'woonkamer'],[1793145600,'min_off_s',450,600,'many_starts',59,''],
    [1793059200,'floor_lead_min_per_c',120,90,'learned_warmup',90,'woonkamer']]}});
// textContent: the figures under a closed "More" are read too (rc.4).
const texts=list=>list.evaluateAll(l=>l.map(e=>e.textContent.replace(/\s+/g,' ').trim()));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,scheme,lang] of [[1280,'light','en'],[360,'dark','nl']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme,locale:lang==='nl'?'nl-NL':'en-GB',timezoneId:'Europe/Amsterdam'}),errors=[],posts=[];
  let status=fixture(),record={weather_curve:true,apply_learned:true,curve_design_flow_c:0,tuning:{...status.tuning.values},tuning_manual:['min_off_s']},reject=null,route=true;
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  await page.route('http://opth.test/**',async r=>{
   const request=r.request(),p=new URL(request.url()).pathname;
   const json=(body,code=200)=>r.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'b'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(status);
   if(p==='/config/heating')return json(plan);
   if(p==='/config/heating/flow'){
    if(!route)return json({weather_curve:true,apply_learned:true,curve_design_flow_c:0}); // firmware before the knobs
    if(request.method()==='POST'){
     assert.equal(request.headers()['x-openthermostat-csrf'],'b'.repeat(64));
     const body=request.postDataJSON();posts.push(body);
     if(reject){const x=reject;reject=null;return json({error:x},400);}
     // The E32's semantics (control/FlowPolicy.h): "tuning" sets values, "tuning_manual" the owner's knobs exactly, null resets.
     if(body.tuning===null){record.tuning={...defaults};record.tuning_manual=[];}
     else if(body.tuning)record.tuning={...record.tuning,...body.tuning};
     // A knob back to automatic: the automatic value (here the built-in one).
     if(body.tuning_manual){for(const k of record.tuning_manual)if(!body.tuning_manual.includes(k))record.tuning[k]=defaults[k];record.tuning_manual=body.tuning_manual;}
     status.tuning.values={...record.tuning};status.tuning.manual=[...record.tuning_manual];
    }
    return json(record);
   }
   if(p==='/week-editor.js')return r.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  const t=(en,nl)=>lang==='nl'?nl:en;
  const at=utc=>page.evaluate(([u,l])=>new Date(u*1000).toLocaleTimeString(l,{hour:'2-digit',minute:'2-digit'}),[utc,lang==='nl'?'nl-NL':'en-GB']);
  // rc.3 Smart warm-up on the Overview: per active room one line on what the next program step means
  // (a learned room starts early; one still learning starts at the program time; the room that is off has none).
  const overview=page.locator('.pd-room .pd-warmup');
  await overview.nth(1).waitFor();
  assert.deepEqual(await texts(overview),t([`Smart warm-up: starts at ${await at(start)} so it is 21 °C at ${await at(rise)}.`,
   `Smart warm-up is still learning: for now heating starts at ${await at(rise)} (estimate: from ${await at(start+3000)} it would be 18 °C on time).`],
   [`Slim opwarmen: begint om ${await at(start)}, zodat het om ${await at(rise)} 21 °C is.`,
   `Slim opwarmen leert nog: voorlopig begint verwarmen om ${await at(rise)} (schatting: vanaf ${await at(start+3000)} zou het op tijd 18 °C zijn).`]));
  // rc.4 learning on the Home page: the living room's arrival feedback (warm 12 min late yesterday at 09:00, the
  // warm-up 10 % longer since), the bedroom's warm-up time learned before its coolest water and a start on an
  // estimate (rc.4: "applies" and "estimate"), and the scoreboard's yesterday.
  const yesterdayNine=await page.evaluate(()=>{const d=new Date();d.setDate(d.getDate()-1);d.setHours(9,0,0,0);return Math.floor(d/1000);});
  status.learned.plans.rooms[0].arrival={factor:1.1,events:3,last_error_min:12,last_at_utc:yesterdayNine};
  status.learned.rooms[1].readiness_timing='ready';
  Object.assign(status.learned.plans.rooms[1].optimum_start,{applies:true,estimate:true});
  status.scoreboard={yesterday:{day:'2026-11-03',heating_h:9,heating_starts_per_h:2.1,short_cycle_h:0.5,heating_kwh:18.2,degree_days:9.4,
   rooms:[{id:'woonkamer',on_time_min:12,overshoot_c:0.3},{id:'slaapkamer',on_time_min:null,overshoot_c:null}]},today:null};
  await page.evaluate(()=>{sessionStorage.removeItem('ot-rooms-edit');loadNativePage('house');});
  const root=page.locator('#house-settings'),learned=root.locator('[data-house-learned]'),care=root.locator('[data-house-care]');
  await learned.getByRole('heading',{name:t('What the thermostat has learned','Wat de thermostaat heeft geleerd')}).waitFor();
  const clock=utc=>page.evaluate(([u,l])=>new Date(u*1000).toLocaleTimeString(l,{hour:'2-digit',minute:'2-digit'}),[utc,lang==='nl'?'nl-NL':'en-GB']);
  // Per room: progress and the Smart warm-up line with how the last morning went; each other figure with what it
  // means under "More" (rc.4: two lines per room); an inactive room is left out.
  const cards=learned.locator('.hl-room');
  assert.equal(await cards.count(),2);
  assert.equal(await cards.nth(0).locator('.hl-progress').innerText(),t('Learned','Geleerd'));
  const living=await texts(cards.nth(0).locator('li'));
  assert.deepEqual(living,lang==='en'?[
   `Smart warm-up: starts at ${await clock(start)} so it is 21 °C at ${await clock(rise)}. Yesterday warm at ${await clock(yesterdayNine+720)} (12 min late); tomorrow 10 % earlier.`,
   'Warms about 1 °C in 1 h 15 min with water of 40 °C. The thermostat plans the start of every warm-up with this.',
   'The lowest water temperature that still warms it in time: 34 °C. Cooler water lets the boiler condense better, so it uses less gas.',
   'Loses about 0.31 °C per hour at 5 °C outside. This is how fast it cools when the heating is off, for example at night.',
   'Keeping it at 19 °C at night is cheaper than letting it cool down: about 0.12 m³ gas (€ 0.15) a night. This is advice: your week program stays as it is.']:[
   `Slim opwarmen: begint om ${await clock(start)}, zodat het om ${await clock(rise)} 21 °C is. Gisteren warm om ${await clock(yesterdayNine+720)} (12 min te laat); morgen 10 % eerder.`,
   'Warmt ongeveer 1 °C op in 1 u 15 min met water van 40 °C. Hiermee plant de thermostaat de start van elke keer opwarmen.',
   'De laagste watertemperatuur die nog op tijd opwarmt: 34 °C. Met koeler water condenseert de ketel beter, dus verbruikt hij minder gas.',
   'Verliest ongeveer 0,31 °C per uur bij 5 °C buiten. Zo snel koelt de ruimte af als de verwarming uit is, bijvoorbeeld \'s nachts.',
   '\'s Nachts op 19 °C houden is goedkoper dan laten afkoelen: ongeveer 0,12 m³ gas (€ 0,15) per nacht. Dit is een advies: je weekprogramma blijft zoals het is.']);
  // Two lines per room: the first figure visible, the others under a closed "More".
  const firstLine=cards.nth(0).locator('li').nth(0),more=cards.nth(0).locator('details.hl-more');
  assert.equal(await firstLine.isVisible(),true);assert.equal(await cards.nth(0).locator('li').nth(1).isVisible(),false);
  assert.equal(await more.locator('summary').innerText(),t('More','Meer'));
  // Opened, it stays open over the page's refresh.
  await more.locator('summary').click();assert.equal(await cards.nth(0).locator('li').nth(1).isVisible(),true);
  await page.evaluate(async()=>{const s=await (await fetch('/status/heating')).json();document.getElementById('house-settings').dispatchEvent(new CustomEvent('heating-status',{detail:s}));});
  assert.equal(await learned.locator('.hl-room').nth(0).locator('details.hl-more').evaluate(d=>d.open),true);
  assert.equal(await cards.nth(1).locator('.hl-progress').innerText(),t('Learning: 3 of 6 warm-ups seen','Aan het leren: 3 van 6 keer opwarmen gezien'));
  const bedroom=await texts(cards.nth(1).locator('li'));
  // rc.4 (L3): a start on an estimate says so; it is used, and it learns from every morning.
  assert.equal(bedroom[0],t(`Smart warm-up: starts at ${await clock(start+3000)} so it is 18 °C at ${await clock(rise)} (estimate; it learns from every morning). So the room is warm on time, without heating longer than needed.`,
   `Slim opwarmen: begint om ${await clock(start+3000)}, zodat het om ${await clock(rise)} 18 °C is (schatting; hij leert van elke ochtend). Zo is de ruimte op tijd warm, zonder langer te verwarmen dan nodig.`));
  // rc.4 (L4): the warm-up time is learned before the coolest water.
  assert.equal(bedroom[1],t('The warm-up time is learned; the coolest water is still being learned.','De opwarmtijd is geleerd; het koelste water leert hij nog.'));
  assert.equal(bedroom[2],t('Letting it cool down at night, as your program does, is the cheapest. This is advice: your week program stays as it is.',
   '\'s Nachts laten afkoelen, zoals je programma doet, is het goedkoopst. Dit is een advies: je weekprogramma blijft zoals het is.'));
  // The scoreboard's yesterday: the figures the E32 measured; a room without any is left out.
  const score=await learned.locator('[data-learned-score]').evaluate(dl=>[...dl.querySelectorAll('dt')].map(dt=>[dt.textContent,dt.nextElementSibling.textContent]));
  assert.deepEqual(score,lang==='en'?[['Heating time','9 h'],['Burner starts per heating hour','2.1'],['Short burner runs','0.5 h'],['Gas for heating (estimate)','18.2 kWh'],
   ['Degree days (how cold it was)','9.4'],['Woonkamer','warm 12 min late · 0.3 °C too warm']]:[['Stooktijd','9 u'],['Branderstarts per stookuur','2,1'],
   ['Korte branderrondes','0,5 u'],['Gas voor verwarmen (schatting)','18,2 kWh'],['Graaddagen (hoe koud het was)','9,4'],['Woonkamer','12 min te laat warm · 0,3 °C te warm']]);
  assert.equal(await learned.locator('[data-learned-yesterday] h3').innerText(),t('Yesterday','Gisteren'));
  // House and boiler: the first item, the rest under "More"; the self-tuning's state and its changes in words, the newest first.
  assert.equal(await learned.locator('[data-learned-house] li').nth(1).isVisible(),false);
  assert.deepEqual(await texts(learned.locator('[data-learned-house] li')),lang==='en'?[
   'Weather compensation, learned from your house: the water gets about 0.62 °C warmer for every degree colder outside. Weather compensation sets the water temperature, so the boiler runs as cool as the weather allows.',
   // rc.4 F5: often, and the self-tuning lengthened the rest once (the "many_starts" change in its log).
   'Yesterday the burner started 59 times for heating; a burn lasted 7 min on average. The burner starts often; the E32 lengthens the burner rest step by step (step 1).']:[
   'Weerafhankelijke regeling, geleerd van je huis: het water wordt ongeveer 0,62 °C warmer voor elke graad kouder buiten. De weerafhankelijke regeling bepaalt de watertemperatuur, zodat de ketel zo koel draait als het weer toelaat.',
   'Gisteren startte de brander 59 keer voor verwarmen; hij brandde gemiddeld 7 min. De brander gaat vaak kort aan; de E32 verlengt de rusttijd stap voor stap (stap 1).']);
  assert.equal(await learned.locator('[data-learned-state]').innerText(),t('The thermostat adjusts its settings itself, at most one small step a day.',
   'De thermostaat past zijn instellingen zelf aan, hooguit één kleine stap per dag.'));
  const log=await texts(learned.locator('[data-learned-log] li'));
  assert.equal(log.length,3);
  assert.match(log[0],t(/^\d+ \w+\.? Woonkamer got 0\.6 °C warmer than its target; the thermostat now stops heating a little earlier\.$/,
   /^\d+ \w+\.? Woonkamer werd 0,6 °C warmer dan gewenst; de thermostaat stopt nu iets eerder met verwarmen\.$/));
  assert.match(log[1],t(/The burner now rests at least 10 min before it starts again, because it started 59 times yesterday\. Fewer starts are gentler on the boiler\.$/,
   /De brander rust nu minstens 10 min voordat hij weer start, omdat hij gisteren 59 keer startte\. Minder starts zijn beter voor de ketel\.$/));
  assert.match(log[2],t(/Woonkamer warms about 1 °C in 1 h 30 min; mornings are planned with that\.$/,/Woonkamer warmt ongeveer 1 °C op in 1 u 30 min; de ochtenden worden daarmee gepland\.$/));
  // Comfort and boiler care: each knob with its value, automatic or set by you, and what it does.
  await care.getByRole('heading',{name:t('Comfort and boiler care','Comfort en zorg voor de ketel')}).waitFor();
  const knob=key=>care.locator(`[data-knob="${key}"]`);
  const head=key=>knob(key).locator('div').first().innerText();
  assert.equal(await head('min_off_s'),t('Burner rest between starts: 10 min (set by you)','Rust van de brander tussen starts: 10 min (door jou ingesteld)'));
  assert.equal(await head('min_on_s'),t('Burner run time: at least 5 min (automatic)','Brandtijd: minstens 5 min (automatisch)'));
  assert.equal(await head('heat_start_c'),t('Start heating when the room is this much below its target: 0.2 °C (automatic)',
   'Begin met verwarmen als de ruimte zoveel onder de gewenste temperatuur is: 0,2 °C (automatisch)'));
  assert.equal(await head('heat_stop_c'),t('Stop heating when the room is this much above its target: 0.15 °C (automatic)',
   'Stop met verwarmen als de ruimte zoveel boven de gewenste temperatuur is: 0,15 °C (automatisch)'));
  assert.equal(await head('floor_lead_min_per_c'),t('Warm-up time for floor heating: 2 h per °C (automatic)','Opwarmtijd voor vloerverwarming: 2 u per °C (automatisch)'));
  assert.match(await knob('min_off_s').innerText(),t(/so the boiler switches on and off less often\./,/zodat de ketel minder vaak aan en uit gaat\./));
  assert.equal(await care.locator('details.hc-more').evaluate(d=>d.open),false,'the fixed knobs start collapsed');
  assert.equal(await knob('curve_correction_pct').locator('div').first().evaluate(e=>e.textContent.replace(/\s+/g,' ')),t('Room correction on weather compensation: 50 % (standard value)','Ruimtecorrectie op de weerafhankelijke regeling: 50 % (standaardwaarde)'));
  // Read-only while Home Assistant manages the settings; editable once unlocked.
  const own=knob('min_on_s').getByRole('button',{name:t('Set it myself','Zelf instellen')});
  assert.equal(await own.isDisabled(),true);
  await root.locator('[data-house-unlock]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-knob="min_on_s"] button').disabled);
  // Set it myself: minutes on the page, seconds to the E32, and the knob becomes the owner's.
  await own.click();
  const input=knob('min_on_s').getByLabel(t('New value (min)','Nieuwe waarde (min)'));
  assert.equal(await input.inputValue(),'5');
  await input.fill('40');
  await knob('min_on_s').getByRole('button',{name:t('Save','Opslaan')}).click();
  await care.locator('[data-care-message]').getByText(t('Use a value from 2 to 30.','Gebruik een waarde van 2 tot 30.')).waitFor();
  assert.equal(posts.length,0);
  await input.fill('7');
  await knob('min_on_s').getByRole('button',{name:t('Save','Opslaan')}).click();
  await care.locator('[data-care-message]').getByText(t('Saved.','Opgeslagen.')).waitFor();
  assert.deepEqual(posts.at(-1),{tuning:{min_on_s:420},tuning_manual:['min_off_s','min_on_s']});
  assert.equal(await head('min_on_s'),t('Burner run time: at least 7 min (set by you)','Brandtijd: minstens 7 min (door jou ingesteld)'));
  assert.equal(await input.isVisible(),false);
  // A refused value: in plain words, nothing changes.
  reject='invalid_value';
  await knob('heat_stop_c').getByRole('button',{name:t('Set it myself','Zelf instellen')}).click();
  await knob('heat_stop_c').locator('input').fill('0.05');
  await knob('heat_stop_c').getByRole('button',{name:t('Save','Opslaan')}).click();
  await care.locator('[data-care-message]').getByText(t('This value is not possible. Choose one within the range shown.','Deze waarde kan niet. Kies er een binnen het aangegeven bereik.')).waitFor();
  assert.equal(await head('heat_stop_c'),t('Stop heating when the room is this much above its target: 0.15 °C (automatic)',
   'Stop met verwarmen als de ruimte zoveel boven de gewenste temperatuur is: 0,15 °C (automatisch)'));
  await knob('heat_stop_c').getByRole('button',{name:t('Cancel','Annuleren')}).click();
  // Back to automatic for one knob, then for all; then back to start values (confirmed).
  await knob('min_off_s').getByRole('button',{name:t('Back to automatic','Weer automatisch')}).click();
  await page.waitForFunction(()=>document.querySelector('[data-knob="min_off_s"] .hc-mode').textContent.includes('(a'));
  assert.deepEqual(posts.at(-1),{tuning_manual:['min_on_s']});
  assert.equal(await knob('min_off_s').getByRole('button',{name:t('Back to automatic','Weer automatisch')}).isVisible(),false);
  await care.getByRole('button',{name:t('Back to automatic for all','Alles weer automatisch')}).click();
  await page.waitForFunction(()=>document.querySelector('[data-care-all-auto]').hidden);
  assert.deepEqual(posts.at(-1),{tuning_manual:[]});
  await care.getByRole('button',{name:t('Back to start values','Terug naar de beginwaarden')}).click();
  await page.waitForFunction(()=>document.querySelector('[data-knob="min_off_s"] .hc-value').textContent==='5 min');
  assert.deepEqual(posts.at(-1),{tuning:null});
  // 44 px targets, no horizontal scroll at phone width, the panels follow the theme.
  for(const target of [knob('min_on_s').getByRole('button').first(),care.getByRole('button',{name:t('Back to start values','Terug naar de beginwaarden')})]){
   const b=await target.boundingBox();assert(b.height>=44,'44 px target');}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  for(const p of [learned,care])assert.equal(await p.evaluate(e=>getComputedStyle(e).backgroundColor),scheme==='dark'?'rgb(22, 33, 36)':'rgb(255, 255, 255)');
  // Shadow mode: what it would change, nothing applied; a quiet house has nothing to show yet.
  Object.assign(status.tuning,{state:'shadow',would:[['min_off_s',300,450,'many_starts',72,'']],log:[]});
  status.flow.curve=null;status.tuning.yesterday=null;
  await learned.locator('[data-learned-log] li').filter({hasText:t('Would change:','Zou aanpassen:')}).waitFor({timeout:15000});
  assert.deepEqual(await texts(learned.locator('[data-learned-log] li')),[t(
   'Would change: The burner now rests at least 7.5 min before it starts again, because it started 72 times yesterday. Fewer starts are gentler on the boiler.',
   'Zou aanpassen: De brander rust nu minstens 7,5 min voordat hij weer start, omdat hij gisteren 72 keer startte. Minder starts zijn beter voor de ketel.')]);
  assert.equal(await learned.locator('[data-learned-state]').innerText(),t('Your own thermostat still controls the boiler, so the E32 only shows what it would change.',
   'Je eigen thermostaat regelt de ketel nog, dus de E32 laat alleen zien wat hij zou aanpassen.'));
  assert.deepEqual(await texts(learned.locator('[data-learned-house] li')),[t('Nothing yet: this appears after the first heating days.','Nog niets: dit verschijnt na de eerste dagen met verwarming.')]);
  // Firmware without the scoreboard: no "Yesterday" block.
  assert.equal(await learned.locator('[data-learned-yesterday]').isVisible(),true);delete status.scoreboard;
  await learned.locator('[data-learned-yesterday]').waitFor({state:'hidden',timeout:15000});
  // Firmware before rc.2: neither panel.
  route=false;status=fixture();delete status.tuning;delete status.learned;
  await page.evaluate(()=>loadNativePage('house'));
  await root.locator('[data-house-now]').getByText(t(/Automatic/,/Automatisch/)).waitFor();
  await page.waitForTimeout(300);
  assert.equal(await learned.isVisible(),false);assert.equal(await care.isVisible(),false);
  assert.deepEqual(errors,[]);
  results.push({width,scheme,lang,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
