// Real shipped Rooms page with simulated HTTP: the "Ready to take over?" checklist (TakeoverReadiness::json()).
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
// The owner's shadow period (1 Nov 2026): waiting, nothing failed.
const owner={state:'waiting',comparison:true,stable:{result:'wait',s:182160,restart:'planned'},
  periods:{result:'wait',thermostat:9,night_setbacks:2,morning_warmups:0,no_demand:3},
  timing:{result:'wait',events:18,matched:18,within_5min:16,within_15min:18},
  flow:{result:'pass',max_c:54,limit_c:60,over:0,request_s:41000},cycling:{result:'wait',e32:9,thermostat:9},
  sources:{result:'pass',rooms:1,working:1,backup:1,fallback_seen:true}};
const status={schema:1,revision:4,mode:'shadow',request:{heat:false,flow_c:0,reason:'idle'},
  rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint_source:'ha',temperature:20.4,setpoint:21,demand:false}],
  ble_sensors:[],shadow:{today:{day:'2026-11-01',s:0,tado_unknown_s:0}},
  active:{state:'shadow',command:{send:false,flow_c:0,why:'shadow'},last_sent:null,foreign_controller:null,confirmation:null,warnings:[],enabled:false},
  readiness:owner};
const plan={schema:1,revision:4,mode:'shadow',minimum_flow_c:30,maximum_flow_c:60,rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',
  sources:[{type:'ha',id:'climate.woonkamer'},{type:'ble',id:'a4c138a3e8db'}],setpoint_entity:'climate.woonkamer',fallback_c:20,minimum_c:5,maximum_c:25,schedule:[]}]};
const items=list=>list.evaluate(ul=>[...ul.children].map(li=>[li.className.replace('hp-check hp-check--',''),
  li.querySelector('strong').textContent,li.querySelector('.hp-check-word').textContent,li.querySelector('.hp-check-line').textContent]));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,language] of [[1280,'en'],[320,'nl']]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let current=status;
  await page.route('http://opth.test/**',async route=>{
   const p=new URL(route.request().url()).pathname;
   const json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/status/heating')return json(current);
   if(p==='/config/heating')return json(plan);
   if(p==='/week-editor.js')return route.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  if(language==='nl')await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  // A fresh mount per status: the old page is removed first, so nothing stale is read.
  const show=async next=>{current=next;await page.evaluate(()=>{document.getElementById('heating-plan')?.remove();loadNativePage('heating');});
   await page.locator('#heating-plan [data-heating-request]').getByText(/off|uit/).waitFor();};
  await show(status);
  const box=page.locator('#heating-plan [data-heating-readiness]'),list=box.locator('[data-heating-readiness-list]');
  const verdict=box.locator('[data-heating-readiness-verdict]');
  await box.waitFor();
  // Right before "Comparison with your thermostat", in shadow mode.
  assert.equal(await box.evaluate(b=>b.nextElementSibling.matches('[data-heating-shadow]')),true);
  if(language==='en'){
   assert.equal(await box.locator('h2').innerText(),'Ready for the E32 to control the boiler?');
   assert.equal(await verdict.innerText(),'Not yet: the trial run needs at least 3 days of data.');
   assert.equal(await box.locator('[data-heating-readiness-alone]').isVisible(),false);
   assert.deepEqual(await items(list),[
    ['wait','Stable for 72 hours','Waiting','50.6 of 72 h without a hang or unexpected restart.'],
    ['wait','Heating periods compared','Waiting','9 of 10 periods. Still needed: a morning warm-up.'],
    ['wait','Heat at the same moments','Waiting','18 of 20 starts and stops.'],
    ['pass','Water temperature stays below the safe maximum','Passed','Highest 54 °C, limit 60 °C.'],
    ['wait','Not more burner starts than the thermostat','Waiting','9 of 10 thermostat periods.'],
    ['pass','Room sensors work','Passed','Every active room is measured, and a backup sensor has stepped in at least once.']]);
   // Colour and icon per result: green pass, orange wait, red fail.
   const colours=await list.evaluate(ul=>[...ul.children].map(li=>getComputedStyle(li.querySelector('.hp-mark')).color));
   assert.notEqual(colours[0],colours[3]);
   // Everything passed: the switch-over steps.
   const pass=Object.fromEntries(Object.entries(owner).map(([k,v])=>[k,v&&typeof v==='object'?{...v,result:'pass'}:v]));
   await show({...status,readiness:{...pass,state:'ready',stable:{result:'pass',s:300000,restart:'planned'},
    periods:{...pass.periods,thermostat:14,morning_warmups:2},timing:{result:'pass',events:28,matched:27,within_5min:22,within_15min:26},
    cycling:{result:'pass',e32:12,thermostat:14}}});
   assert.equal(await verdict.innerText(),'Ready: follow the steps to switch over.');
   assert.equal(await verdict.evaluate(v=>v.className),'hp-verdict hp-verdict--ready');
   assert.deepEqual((await items(list)).map(i=>i[0]),['pass','pass','pass','pass','pass','pass']);
   assert.equal((await items(list))[2][3],'22 of 28 starts and stops within 5 minutes, 27 within 30 minutes.');
   // A failure says what to do.
   await show({...status,readiness:{...owner,state:'not_ready',flow:{result:'fail',max_c:62,limit_c:60,over:2,request_s:41000},
    stable:{result:'wait',s:7200,restart:'unexpected'},sources:{result:'fail',rooms:1,working:1,backup:0,fallback_seen:false}}});
   assert.equal(await verdict.innerText(),'Not ready: fix the items marked in red first.');
   const failed=await items(list);
   assert.deepEqual(failed[0],['wait','Stable for 72 hours','Waiting','2 of 72 h without a hang or unexpected restart. The E32 restarted unexpectedly; counting started again.']);
   assert.deepEqual(failed[3],['fail','Water temperature stays below the safe maximum','Action needed','2 times above the limit of 60 °C. Do not switch over: check the water temperature limits and report this.']);
   assert.deepEqual(failed[5],['fail','Room sensors work','Action needed','No room has a backup sensor yet. Add one, for example a Bluetooth sensor.']);
  }else{
   assert.equal(await box.locator('h2').innerText(),'Klaar om de E32 de ketel te laten regelen?');
   assert.equal(await verdict.innerText(),'Nog niet: de proefperiode heeft minstens 3 dagen gegevens nodig.');
   assert.deepEqual((await items(list)).map(i=>[i[2],i[3]]),[
    ['Wacht','50,6 van 72 uur zonder vastloper of onverwachte herstart.'],
    ['Wacht','9 van 10 periodes. Nog nodig: een ochtendopwarming.'],
    ['Wacht','18 van 20 starts en stops.'],
    ['Geslaagd','Hoogste 54 °C, grens 60 °C.'],
    ['Wacht','9 van 10 thermostaatperiodes.'],
    ['Geslaagd','Elke actieve ruimte wordt gemeten, en een reservesensor heeft het al eens overgenomen.']]);
   // A home without a thermostat on the bus: the E32 and the boiler only, and it says so.
   await show({...status,readiness:{state:'not_ready',comparison:false,stable:{result:'wait',s:36000,restart:'first'},
    sources:{result:'wait',rooms:1,working:1,backup:1,fallback_seen:false},boiler:{result:'pass',age_s:12},boiler_limit:{result:'fail',limit_c:null}}});
   assert.equal(await box.locator('[data-heating-readiness-alone]').innerText(),
    'Er is geen thermostaat op de ketelbus om mee te vergelijken, dus alleen de E32 zelf en de ketel worden gecontroleerd.');
   assert.deepEqual((await items(list)).map(i=>i[1]),['72 uur stabiel','Ruimtesensoren werken','De E32 hoort de ketel','Ketelmaximum bekend']);
   assert.equal((await items(list))[0][3],'10 van 72 uur zonder vastloper of onverwachte herstart. Het tellen begon toen deze firmware voor het eerst draaide.');
   assert.equal((await items(list))[2][3],'Laatste melding 12 s geleden.');
   assert.equal((await items(list))[3][3],'De ketel heeft zijn hoogste watertemperatuur niet gemeld. Controleer de kabel naar de ketel.');
  }
  // Taken over: no checklist (the firmware says not_applicable; active mode hides it too).
  await show({...status,mode:'active',readiness:{state:'not_applicable'}});
  assert.equal(await box.isVisible(),false);
  await show({...status,mode:'active'});
  assert.equal(await box.isVisible(),false);
  // Firmware without the check: nothing either.
  const {readiness,...older}=status;
  await show(older);
  assert.equal(await box.isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  assert.deepEqual(errors,[]);
  results.push({width,language,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
