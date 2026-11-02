// Real shipped Rooms page with simulated HTTP: the guided "Boiler test and takeover" (rc.2, TakeoverTest::json()),
// a new installation in active mode waiting for the takeover, the optional trial run, EN at 1280 and NL at phone width.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const steps=(o={})=>({disconnect:'not_run',confirm:'not_run',start:'not_run',hot_water:'not_run',stop:'not_run',...o});
const idle={state:'idle',at:null,steps:steps(),reason:null};
const waiting={state:'awaiting_confirmation',awaiting_confirmation:true,reconfirm_required:false,command:{send:false,flow_c:0,why:'awaiting_confirmation'},
  last_sent:null,foreign_controller:null,confirmation:null,warnings:[],enabled:true,taken_over_before:false,boiler_limit:{flow_c:60,age_s:30,reads:1}};
const status={schema:1,revision:2,mode:'active',request:{heat:false,flow_c:0,reason:'idle'},
  rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint_source:'ha',temperature:20.4,setpoint:21,demand:false}],
  ble_sensors:[],shadow:{today:{day:'2026-11-02',s:0,tado_unknown_s:0}},active:waiting,readiness:{state:'not_applicable',takeover_test:idle},
  new_plan:{stored:true,mode:'active',reason:'no_thermostat'}};
const plan={schema:1,revision:2,mode:'active',minimum_flow_c:30,maximum_flow_c:60,rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'radiator',
  sources:[{type:'ha',id:'climate.woonkamer'}],setpoint_entity:'climate.woonkamer',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500}]};
const running=(step,phase,extra={})=>({state:'running',at:1762077600,steps:steps({...Object.fromEntries(['disconnect','confirm','start','hot_water','stop']
  .slice(0,['disconnect','confirm','start','hot_water','stop'].indexOf(step)).map(k=>[k,'pass'])),[step]:'wait'}),reason:null,step,phase,step_s:40,room:'woonkamer',target_c:null,...extra});
const lines=list=>list.evaluate(ol=>[...ol.children].map(li=>[li.className.replace('hp-check hp-check--','').replace(' hp-check--now',''),
  li.querySelector('strong').textContent,li.querySelector('.hp-check-word').textContent,li.querySelector('.hp-check-line').textContent]));
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,language] of [[1280,'en'],[320,'nl']]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',d=>d.accept());
  let current=status,currentPlan=plan;
  await page.route('http://opth.test/**',async route=>{
   const request=route.request(),p=new URL(request.url()).pathname;
   const json=body=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(request.method()==='POST'){
    const body=JSON.parse(request.postData()||'{}');posts.push([p,body]);
    if(p==='/config/heating'){currentPlan={...body,revision:body.revision+1};current={...current,mode:body.mode};return json(currentPlan);}
    if(p==='/config/heating/takeover-test')return json(body.action==='start'?running('disconnect','listening',{quiet_s:0}):current.readiness.takeover_test);
    if(p==='/config/heating/handover')return json({...waiting,state:'arming',awaiting_confirmation:false,confirmation:{age_s:0,restored:false}});
   }
   if(p==='/status/heating')return json(current);
   if(p==='/config/heating')return json(currentPlan);
   if(p==='/week-editor.js')return route.fulfill({status:404,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:p.endsWith('.js')||p.endsWith('.js.gz')?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  if(language==='nl')await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://opth.test'}]);
  await page.goto('http://opth.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  const show=async(next,nextPlan=plan)=>{current=next;currentPlan=nextPlan;await page.evaluate(()=>{document.getElementById('heating-plan')?.remove();loadNativePage('heating');});
   await page.locator('#heating-plan [data-heating-request]').getByText(/off|uit/).waitFor();};
  const withTest=(test,extra={})=>({...status,...extra,readiness:{state:'not_applicable',takeover_test:test}});
  const box=page.locator('#heating-plan [data-heating-test]'),list=box.locator('[data-heating-test-list]'),verdict=box.locator('[data-heating-test-verdict]');
  const button=name=>box.locator('[data-heating-test-'+name+']');
  const en=language==='en';
  // A new installation: active plan, not taken over. A clear next step, no alarm.
  await show(status);
  await box.waitFor();
  assert.equal(await box.locator('h2').innerText(),en?'Boiler test and takeover':'Keteltest en overname');
  assert.equal(await verdict.innerText(),en?'Not run yet.':'Nog niet uitgevoerd.');
  assert.equal(await page.locator('#heating-plan [data-heating-mode-text]').innerText(),en
   ?'Next step: the boiler test and takeover below. Until you confirm the takeover, the E32 sends nothing to the boiler.'
   :'Volgende stap: de keteltest en overname hieronder. Tot je de overname bevestigt, stuurt de E32 niets naar de ketel.');
  assert.match(await page.locator('#heating-plan [data-heating-active-state]').innerText(),en?/^Not controlling the boiler yet/:/^Regelt de ketel nog niet/);
  assert.equal(await page.locator('#heating-plan [data-heating-readiness]').isVisible(),false);
  const fresh=await lines(list);
  assert.deepEqual(fresh.map(l=>l[0]),['idle','idle','idle','idle','idle','idle']);
  assert.deepEqual(fresh.map(l=>l[1]),en?['Disconnect your old thermostat','Confirm the takeover','Start heating','Hot water while heating','Stop heating','Done']
   :['Koppel je oude thermostaat los','Overname bevestigen','Verwarmen starten','Warm water tijdens verwarmen','Verwarmen stoppen','Klaar']);
  assert.equal(fresh[0][3],en?'Switch the boiler off, disconnect your old thermostat from the boiler, then switch the boiler back on.'
   :'Zet de ketel uit, koppel je oude thermostaat los van de ketel en zet de ketel daarna weer aan.');
  assert.equal(fresh[3][3],en?'Open a hot tap for 3 minutes. Hot water goes first, then heating resumes.':'Open een warme kraan 3 minuten. Warm water gaat voor, daarna gaat het verwarmen verder.');
  assert.equal(await button('start').isVisible(),true);
  assert.equal(await button('stop').isVisible(),false);
  assert.equal(await box.locator('[data-heating-test-choices]').isVisible(),true);
  assert.equal(await button('skip').innerText(),en?'Skip the test and confirm the takeover now':'Test overslaan en de overname nu bevestigen');
  assert.equal(await page.locator('#heating-plan [data-heating-trial]').innerText(),en?'Trial run first (compare with your thermostat)':'Eerst een proefperiode (vergelijken met je thermostaat)');
  assert.match(await box.locator('[data-heating-test-choices]').innerText(),en?/A trial run is for a home that still has its old thermostat/:/Een proefperiode is voor een huis/);
  // Why this route: no other thermostat on the boiler bus.
  const why=box.locator('[data-heating-test-why]');
  assert.equal(await why.innerText(),en?'No other thermostat was found on the boiler bus, so you can go straight to the boiler test.'
   :'Er is geen andere thermostaat op de ketelbus gevonden, dus je kunt meteen naar de keteltest.');
  // Start: one POST, then the first step listens.
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/takeover-test')),button('start').click()]);
  assert.deepEqual(posts.filter(([p])=>p.endsWith('takeover-test')).map(([,b])=>b),[{action:'start'}]);
  await show(withTest(running('disconnect','listening',{quiet_s:45})));
  let now=await lines(list);
  assert.deepEqual(now[0],['wait',en?'Disconnect your old thermostat':'Koppel je oude thermostaat los',en?'Waiting':'Wacht',
   en?'Listening: no other thermostat heard for 45 of 120 s.':'Luisteren: al 45 van 120 s geen andere thermostaat gehoord.']);
  assert.equal(await verdict.innerText(),en?'Test running: step 1 of 5.':'Test loopt: stap 1 van 5.');
  assert.equal(await box.locator('[data-heating-test-choices]').isVisible(),false);
  assert.equal(await button('stop').isVisible(),true);
  await show(withTest(running('disconnect','thermostat_heard',{quiet_s:0})));
  assert.equal((await lines(list))[0][3],en?'Your old thermostat is still heard on the boiler bus. Disconnect it from the boiler.'
   :'Je oude thermostaat is nog te horen op de ketelbus. Koppel hem los van de ketel.');
  // Confirm: the existing confirmation and dialog.
  await show(withTest(running('confirm','waiting_confirmation')));
  now=await lines(list);
  assert.equal(now[0][0],'pass');
  assert.equal(now[1][3],en?'Press “Confirm the takeover” below.':'Druk hieronder op “Overname bevestigen”.');
  posts.length=0;
  await button('confirm').click();
  await page.waitForFunction(()=>/E32/.test(document.querySelector('#heating-plan [data-heating-active-message]').textContent));
  assert.deepEqual(posts,[['/config/heating/handover',{thermostat_disconnected:true}]]);
  // Start heating: the room and its test temperature.
  await show(withTest(running('start','waiting_burner',{target_c:21.4}),{active:{...waiting,state:'active',awaiting_confirmation:false,confirmation:{age_s:90,restored:false}}}));
  assert.equal((await lines(list))[2][3],en?'Woonkamer is set to 21.4 °C for this test. Waiting for the burner (up to 10 minutes).'
   :'Woonkamer staat voor deze test op 21,4 °C. Wachten op de brander (tot 10 minuten).');
  await show(withTest(running('start','waiting_flow_rise',{target_c:21.4,rise_c:1.5})));
  assert.equal((await lines(list))[2][3],en?'Burner on. The water to heating rose 1.5 of 3 °C.':'Brander aan. Het water naar verwarming steeg 1,5 van 3 °C.');
  // Hot water: the tap, and the skip for a boiler without hot water.
  await show(withTest(running('hot_water','waiting_tap',{target_c:21.4})));
  assert.equal((await lines(list))[3][3],en?'Open a hot tap now and leave it open for 3 minutes.':'Open nu een warme kraan en laat hem 3 minuten open.');
  assert.equal(await button('skip-step').isVisible(),true);
  posts.length=0;
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/takeover-test')),button('skip-step').click()]);
  assert.deepEqual(posts,[['/config/heating/takeover-test',{action:'skip'}]]);
  await show(withTest(running('stop','watching_restart',{target_c:19.9,steps:steps({disconnect:'pass',confirm:'pass',start:'pass',hot_water:'skipped',stop:'wait'})})));
  now=await lines(list);
  assert.deepEqual(now[3].slice(0,3),['idle',en?'Hot water while heating':'Warm water tijdens verwarmen',en?'Skipped':'Overgeslagen']);
  assert.equal(now[4][3],en?'Burner off. Checking that it stays off for 5 minutes.':'Brander uit. Controleren dat hij 5 minuten uit blijft.');
  assert.equal(await button('skip-step').isVisible(),false);
  // Passed: the result is kept and shown, with its time.
  await show(withTest({state:'passed',at:1762077600,steps:steps({disconnect:'pass',confirm:'pass',start:'pass',hot_water:'pass',stop:'pass'}),reason:null},
   {active:{...waiting,state:'active',awaiting_confirmation:false,confirmation:{age_s:900,restored:false},taken_over_before:true}}));
  assert.match(await verdict.innerText(),en?/^Passed\. The E32 now controls your boiler\. \(.+\)$/:/^Geslaagd\. De E32 regelt nu je ketel\. \(.+\)$/);
  now=await lines(list);
  assert.deepEqual(now.map(l=>l[0]),['pass','pass','pass','pass','pass','pass']);
  assert.equal(now[5][3],en?'The E32 now controls your boiler. The test temperature has ended; the week program continues.'
   :'De E32 regelt nu je ketel. De testtemperatuur is afgelopen; het weekprogramma gaat verder.');
  assert.equal(await button('start').innerText(),en?'Start the boiler test again':'Keteltest opnieuw starten');
  assert.equal(await box.locator('[data-heating-test-choices]').isVisible(),false); // already taken over
  // A failed step says what to do; an abort rule says stop and give control back, with the steps.
  await show(withTest({state:'failed',at:1762077600,steps:steps({disconnect:'pass',confirm:'pass',start:'fail'}),reason:'no_burner'}));
  now=await lines(list);
  assert.deepEqual(now[2].slice(0,3),['fail',en?'Start heating':'Verwarmen starten',en?'Failed':'Mislukt']);
  assert.equal(now[2][3],en?"The burner did not start within 10 minutes. Check that the boiler's heating switch is on and that it shows no fault."
   :'De brander ging niet binnen 10 minuten aan. Controleer of de verwarmingsschakelaar van de ketel aan staat en of hij geen storing toont.');
  assert.equal(await box.locator('[data-heating-test-abort-steps]').isVisible(),false);
  await show(withTest({state:'stopped',at:1762077600,steps:steps({disconnect:'pass',confirm:'pass',start:'pass',hot_water:'fail'}),reason:'foreign_controller'}));
  assert.equal(await verdict.evaluate(v=>v.className),'hp-verdict hp-verdict--stopped');
  assert.equal((await lines(list))[3][3],en?'Another thermostat asked the boiler for heat. Disconnect it from the boiler.':'Een andere thermostaat vroeg de ketel om warmte. Koppel hem los van de ketel.');
  const abort=box.locator('[data-heating-test-abort-steps]');
  assert.equal(await abort.isVisible(),true);
  assert.match(await abort.innerText(),en?/Stop and give control back to your thermostat:[\s\S]*Give control back to my thermostat[\s\S]*reconnect your old thermostat/
   :/Stop en geef de regeling terug aan je thermostaat:[\s\S]*Regeling teruggeven aan mijn thermostaat[\s\S]*sluit je oude thermostaat weer/);
  assert.equal(await page.locator('#heating-plan [data-heating-handback]').isVisible(),true);
  // The trial run first is an explicit choice: the plan goes to shadow mode, nothing else.
  await show(status);
  posts.length=0;
  await page.locator('#heating-plan [data-heating-trial]').click();
  await page.waitForFunction(()=>/(optional|optioneel)/.test(document.querySelector('#heating-plan [data-heating-test-message]').textContent));
  assert.equal(posts.length,1);
  assert.equal(posts[0][0],'/config/heating');assert.equal(posts[0][1].mode,'shadow');
  assert.equal(await box.locator('[data-heating-test-message]').innerText(),en?'Trial run started. It is optional: start the boiler test whenever you are ready.'
   :'Proefperiode gestart. Die is optioneel: start de keteltest zodra je klaar bent.');
  // In the trial run the test can still be started: the plan goes active first, then the test.
  await show(withTest(idle,{mode:'shadow',active:{...waiting,state:'shadow',awaiting_confirmation:false,command:{send:false,flow_c:0,why:'shadow'}}}),{...plan,mode:'shadow'});
  assert.match(await page.locator('#heating-plan [data-heating-mode-text]').innerText(),en?/^Trial run \(optional\)/:/^Proefperiode \(optioneel\)/);
  assert.equal(await why.innerText(),en?'No other thermostat is heard on the boiler bus: you can go straight to the boiler test.'
   :'Er is geen andere thermostaat op de ketelbus te horen: je kunt meteen naar de keteltest.'); // a trial run without a thermostat
  assert.equal(await button('start').innerText(),en?'Go straight to the boiler test':'Meteen naar de keteltest');
  assert.equal(await box.locator('[data-heating-test-choices]').isVisible(),false);
  posts.length=0;
  await Promise.all([page.waitForResponse(r=>r.url().endsWith('/takeover-test')),button('start').click()]);
  assert.deepEqual(posts.map(([p,b])=>[p,b.mode||b.action]),[['/config/heating','active'],['/config/heating/takeover-test','start']]);
  // A new E32 that hears a thermostat on the bus starts with the trial run and says why; the checklist's last step points here.
  const heard={...withTest(idle,{mode:'shadow',active:{...waiting,state:'shadow',awaiting_confirmation:false,command:{send:false,flow_c:0,why:'shadow'}}}),
   new_plan:{stored:false,mode:'shadow',reason:'thermostat_heard'}};
  heard.readiness={state:'waiting',comparison:true,stable:{result:'wait',s:3600,restart:'first'},sources:{result:'pass',rooms:1,working:1,backup:1,fallback_seen:true},takeover_test:idle};
  await show(heard,{...plan,mode:'shadow',rooms:[]});
  assert.equal(await why.innerText(),en?'Your boiler still gets requests from another thermostat, so the E32 first runs alongside it (trial run).'
   :'Je ketel krijgt nog vragen van een andere thermostaat, dus de E32 draait eerst mee (proefperiode).');
  assert.match(await page.locator('#heating-plan [data-heating-readiness]').innerText(),en?/Last step: when everything has passed, start the boiler test and takeover above\./
   :/Laatste stap: als alles is geslaagd, start je hierboven de keteltest en overname\./);
  assert.equal(await button('start').innerText(),en?'Go straight to the boiler test':'Meteen naar de keteltest');
  // Still listening: it says so, and the first save waits until the bus decided, in the mode it decided.
  await page.evaluate(()=>sessionStorage.setItem('ot-rooms-edit','1')); // editing here, not in Home Assistant
  await show({...status,mode:'shadow',active:{...waiting,state:'shadow'},new_plan:{stored:false,mode:'shadow',reason:'checking'}},{...plan,mode:'shadow'});
  assert.equal(await why.innerText(),en?'Checking the boiler bus…':'De ketelbus wordt gecontroleerd…');
  posts.length=0;
  await page.locator('#heating-plan [data-heating-save]').click();
  await page.locator('#heating-plan [data-heating-message]').getByText(en?'Checking the boiler bus…':'De ketelbus wordt gecontroleerd…').waitFor();
  assert.equal(posts.length,0);
  current={...current,new_plan:{stored:false,mode:'active',reason:'no_thermostat'}};
  await page.waitForResponse(r=>r.url().endsWith('/config/heating')&&r.request().method()==='POST',{timeout:15000});
  assert.equal(posts[0][0],'/config/heating');assert.equal(posts[0][1].mode,'active');
  // Firmware without the test, or without the active gate: no card.
  await show({...status,readiness:{state:'not_applicable'}});
  assert.equal(await box.isVisible(),false);
  await show({...status,active:{...waiting,enabled:false}});
  assert.equal(await box.isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  assert.deepEqual(errors,[]);
  results.push({width,language,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
