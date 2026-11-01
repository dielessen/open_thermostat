// Home page (beta.23; the Rooms page before) with simulated HTTP: the flow temperature section (E32 beta.19); the Rooms page:
// the switch-over status of active control.
// Flow: weather curve, learned flow and optimum start, design flow, status lines, gas calibration and last night.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const room={id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'floor',sources:[{type:'ha',id:'climate.woonkamer'}],
  setpoint_entity:'climate.woonkamer',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500};
const plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[room]};
const day=(rule,curve,learned)=>({heat_s:7200,rule_mean_c:rule,applied_mean_c:rule,curve_s:7200,curve_mean_c:curve,curve_rule_mean_c:rule,
  learned_s:curve===null?0:3600,learned_mean_c:learned,learned_rule_mean_c:rule,optimum_start_s:0});
// FlowPolicy::addStatus (full form), learnedJson's "gas" and NightLedger::json (full form), as /status/heating carries them.
const fixture=()=>({schema:1,revision:4,mode:'shadow',request:{heat:true,flow_c:36,reason:'heating'},
  rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint_source:'ha',temperature:20.4,setpoint:21,demand:true}],
  ble_sensors:[],shadow:{today:{s:0},days:[]},away:{on:false,source:'none',target_c:15,until:null,presence:'home',mode:'auto'},
  active:{state:'shadow',command:{send:false,flow_c:0,why:'shadow'},last_sent:null,foreign_controller:null,confirmation:null,warnings:[],enabled:false},
  flow:{source:'rule',rule_flow_c:36,settings:{weather_curve:false,apply_learned:false,curve_design_flow_c:0},applied_flow_c:36,cap_c:60,
   curve:{state:'advice',flow_c:41,base_c:38.2,slope:0.67,slope_source:'design',design_flow_c:40,windows:3,last:'too_short'},
   learned:{state:'not_ready',flow_c:null,room:'woonkamer'},
   optimum_start:{state:'advice',room:'woonkamer',start_utc:1793248800,flow_c:38,confidence:'learned',heating:false},
   today:day(36,41,null),yesterday:day(38.4,41.25,null)},
  learned:{schema:1,applied:false,status:'learning',gas:{status:'calibrated',confidence:'medium',factor:0.93,kw_at_full_modulation:22.3,kw_source:'meter',
   intervals:7,rejected:1,last:'interval_compared',spread:0.21}},
  night_gas:{nights:3,model_ratio:1.08,state:'waiting',model_nights:3,last:{start_utc:1793215800,switch_utc:1793248200,status:'measured',measured_m3:1.912,
   heating_m3:1.734,hot_water_m3:0.178,predicted_program_m3:1.6,predicted_thermostat_like_m3:1.9,predicted_recommended_m3:1.6,recommended:'program'}}});
const pairs=dl=>dl.evaluate(e=>[...e.querySelectorAll('dt')].map(dt=>[dt.textContent,dt.nextElementSibling.textContent]));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,scheme] of [[1280,'light'],[360,'dark']]){
  const page=await browser.newPage({viewport:{width,height:900},colorScheme:scheme}),errors=[],posts=[];
  let status=fixture(),settings={...status.flow.settings},route='flow',reject=null;
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
    if(route!=='flow')return r.fulfill({status:404,contentType:'text/plain',body:'Not found'});
    if(request.method()==='POST'){
     assert.equal(request.headers()['x-openthermostat-csrf'],'b'.repeat(64));
     assert.equal(request.headers()['content-type'],'application/json');
     const body=request.postDataJSON();posts.push(body);
     if(reject){const x=reject;reject=null;return json({error:x.error},x.code);}
     settings={...settings,...body};status.flow.settings={...settings};
    }
    return json(settings);
   }
   if(p==='/week-editor.js')return r.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return r.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return r.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>{sessionStorage.removeItem('ot-rooms-edit');loadNativePage('house');});
  const root=page.locator('#house-settings'),box=root.locator('[data-heating-flow-options]');
  await box.getByRole('heading',{name:'Aanvoertemperatuur'}).waitFor();
  const curve=box.getByLabel('Weersafhankelijke stooklijn'),learned=box.getByLabel('Geleerde aanvoer en optimale start gebruiken');
  const design=box.getByLabel('Aanvoer bij −10 °C'),message=box.locator('[data-flow-message]');
  // Status lines from /status/heating: source, curve, slope, learned, optimum start, gas calibration and boiler power,
  // collapsed under "Status en leren" below the two settings.
  const more=box.locator('details.hp-more');
  assert.equal(await more.evaluate(d=>d.open),false,'the status lines start collapsed');
  await more.locator('summary').click();
  await box.locator('[data-flow-status] dt').first().waitFor();
  const time=await page.evaluate(()=>new Date(1793248800000).toLocaleTimeString('nl-NL',{hour:'2-digit',minute:'2-digit'}));
  assert.deepEqual(await pairs(box.locator('[data-flow-status]')),[['Aanvoer nu','Ruimteregeling · 36 °C'],['Stooklijn','Alleen advies · 41 °C'],
   ['Helling stooklijn','0,67 · Uit de ontwerpaanvoer'],['Geleerde aanvoer','Nog aan het leren'],['Optimale start','Alleen advies · geplande start '+time],
   ['Gasijking','Geijkt met de gasmeter (middel)'],['Ketelvermogen','22,3 kW bij volle brander']]);
  assert.equal(await box.locator('[data-flow-compare]').innerText(),'Gisteren tijdens verwarmen: ruimteregeling 38,4 °C, stooklijn 41,3 °C, geleerd — °C');
  assert.equal(await box.locator('[data-flow-night]').innerText(),'Afgelopen nacht: 1,73 m³ gas voor verwarmen (0,18 m³ warm water); model voorspelde 1,60 m³');
  // Help texts and the design flow choice: automatic by emitter, or 25–80 °C.
  assert.match(await box.innerText(),/Bepaalt de aanvoertemperatuur uit de buitentemperatuur, met de ruimtecorrectie erbovenop\./);
  assert.match(await box.innerText(),/Uit: de E32 geeft alleen advies\. Aan: bij opwarmen gebruikt hij de laagste aanvoer/);
  const choices=await design.locator('option').allInnerTexts();
  assert.equal(choices[0],'Automatisch (vloer 40 °C, radiatoren 55 °C)');assert.equal(choices[1],'25 °C');assert.equal(choices.at(-1),'80 °C');assert.equal(choices.length,57);
  assert.equal(await design.inputValue(),'0');assert.equal(await curve.isChecked(),false);assert.equal(await learned.isChecked(),false);
  // Managed in Home Assistant (unreachable here) and not unlocked: read-only, like the flow limits.
  assert.equal(await curve.isDisabled(),true);assert.equal(await design.isDisabled(),true);assert.equal(await learned.isDisabled(),true);
  await root.locator('[data-house-unlock]').click();
  await page.waitForFunction(()=>!document.querySelector('#heating-flow-curve').disabled);
  assert.equal(await design.isDisabled(),false);
  // 44 px targets for the switches and the choice; no horizontal scroll at phone width.
  for(const target of [curve.locator('xpath=..'),learned.locator('xpath=..'),design]){const b=await target.boundingBox();assert(b.height>=44,'44 px target');}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // Light and dark: the panel follows the theme tokens.
  const bg=await root.locator('[data-house-heating]').evaluate(e=>getComputedStyle(e).backgroundColor);
  assert.equal(bg,scheme==='dark'?'rgb(22, 33, 36)':'rgb(255, 255, 255)');
  // Each change is one partial POST with the CSRF proof; the answer is shown at once.
  await curve.check();
  await message.getByText('Opgeslagen.').waitFor();
  assert.deepEqual(posts.at(-1),{weather_curve:true});assert.equal(await curve.isChecked(),true);
  await design.selectOption('45');
  await page.waitForFunction(n=>document.querySelector('[data-flow-message]').textContent==='Opgeslagen.'&&!document.querySelector('#heating-flow-design').disabled,null);
  assert.deepEqual(posts.at(-1),{curve_design_flow_c:45});assert.equal(posts.length,2);
  // Refusals in plain words; the control shows the stored value again.
  reject={code:400,error:'invalid_value'};
  await learned.click();
  await message.getByText('Ongeldige waarde').waitFor();
  assert.deepEqual(posts.at(-1),{apply_learned:true});assert.equal(await learned.isChecked(),false);
  reject={code:503,error:'save_unconfirmed'};
  await learned.click();
  await message.getByText('Opslaan niet bevestigd, probeer opnieuw').waitFor();
  assert.equal(await learned.isChecked(),false);
  reject={code:400,error:'invalid_key'};
  await learned.click();
  await message.getByText('De E32 weigerde de wijziging. (invalid_key)').waitFor();
  await learned.check();
  await message.getByText('Opgeslagen.').waitFor();
  assert.deepEqual(posts.at(-1),{apply_learned:true});assert.equal(await learned.isChecked(),true);
  // Now in use: the next status shows the learned flow and optimum start as applied.
  Object.assign(status.flow,{source:'learned',applied_flow_c:34,learned:{state:'applied',flow_c:34,room:'woonkamer'},
   optimum_start:{state:'none',room:null,start_utc:null,flow_c:null,confidence:'none',heating:false},
   curve:{...status.flow.curve,state:'applied',slope:0.71,slope_source:'learned'}});
  status.learned.gas={status:'no_meter',confidence:'none',factor:1,kw_at_full_modulation:24,kw_source:'boiler_kw',intervals:0,rejected:0,last:'no_interval',spread:null};
  status.night_gas.last={...status.night_gas.last,status:'no_meter',measured_m3:null,heating_m3:null,hot_water_m3:null};
  await box.locator('[data-flow-status]').getByText('Geleerde aanvoer · 34 °C').waitFor({timeout:15000});
  assert.deepEqual(await pairs(box.locator('[data-flow-status]')),[['Aanvoer nu','Geleerde aanvoer · 34 °C'],['Stooklijn','In gebruik · 41 °C'],
   ['Helling stooklijn','0,71 · Geleerd van dit huis'],['Geleerde aanvoer','In gebruik · 34 °C'],['Optimale start','Geen start gepland'],
   ['Gasijking','Geen gasmeter: schatting uit het ketelvermogen (ruw)'],['Ketelvermogen','24,0 kW bij volle brander']]);
  assert.equal(await box.locator('[data-flow-night]').innerText(),'Afgelopen nacht: geen gasmeterstand');
  // Changed elsewhere (Home Assistant): the stored options come with the status.
  settings={weather_curve:false,apply_learned:true,curve_design_flow_c:0};status.flow.settings={...settings};
  await page.waitForFunction(()=>!document.querySelector('#heating-flow-curve').checked,null,{timeout:15000});
  assert.equal(await design.inputValue(),'0');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // Active control after a restart with a stored confirmation: the boiler's own maximum, the listening
  // period before taking over again, and the warning while the boiler limit is unknown.
  // Active control stays on the Rooms page (part of the room plan's mode).
  await page.evaluate(()=>loadNativePage('heating'));
  const rooms=page.locator('#heating-plan');await rooms.locator('[data-heating-active]').waitFor();
  const control=rooms.locator('[data-heating-active]'),activeFacts=control.locator('[data-heating-active-facts]');
  const activeNotes=control.locator('[data-heating-active-notes]');
  assert.equal(await activeFacts.isVisible(),false,'firmware without boiler_limit: no line');
  status.active={state:'arming',awaiting_confirmation:false,command:{send:false,flow_c:0,why:'arming'},last_sent:null,foreign_controller:null,
   confirmation:{age_s:40,restored:true,listened_s:45},warnings:['boiler_limit_unknown'],enabled:true,confirmation_stored:true,
   boiler_limit:{flow_c:null,age_s:null,reads:2}};
  await activeFacts.waitFor({timeout:15000});
  assert.deepEqual(await pairs(activeFacts),[['Maximale aanvoer (gemeld door de ketel)','nog niet bekend']]);
  assert.deepEqual(await activeNotes.locator('p').allInnerTexts(),[
   'Herstart: de E32 luistert eerst 2 minuten of er een andere thermostaat is voordat hij weer overneemt. (45 van 120 s)',
   'Je bevestiging blijft bewaard na een herstart.']);
  assert.deepEqual(await control.locator('[data-heating-active-warnings] li').allInnerTexts(),
   ['De ketel heeft zijn maximale aanvoertemperatuur nog niet gemeld; de E32 vraagt geen warmte en vraagt het elke 5 minuten opnieuw.']);
  // Listening done and the limit read: the maximum with its age, only the stored confirmation remains.
  Object.assign(status.active,{state:'active',confirmation:{age_s:200,restored:false},warnings:[],boiler_limit:{flow_c:75,age_s:30,reads:3}});
  await activeFacts.getByText('75 °C · 30 s geleden').waitFor({timeout:15000});
  assert.deepEqual(await activeNotes.locator('p').allInnerTexts(),['Je bevestiging blijft bewaard na een herstart.']);
  assert.equal(await control.locator('[data-heating-active-warnings]').isVisible(),false);
  status.active.confirmation_stored=false;
  await activeNotes.waitFor({state:'hidden',timeout:15000});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // Firmware without the flow options: no section at all.
  route='none';status=fixture();delete status.flow;delete status.night_gas;
  await page.evaluate(()=>loadNativePage('house'));
  await root.locator('[data-house-now]').getByText(/Automatisch/).waitFor();
  await page.waitForTimeout(300);
  assert.equal(await root.locator('[data-heating-flow-options]').isVisible(),false);
  assert.equal(await page.locator('#heating-plan [data-heating-flow-options]').count(),0,'no flow options on the Rooms page');
  assert.deepEqual(errors,[]);
  results.push({width,scheme,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
