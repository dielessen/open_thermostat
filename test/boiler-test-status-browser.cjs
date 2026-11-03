// Real shipped Boiler page with simulated HTTP (rc.3, owner 3 Nov 2026): one boiler test instead of two.
// The Boiler page shows the kept result of the boiler test (control/TakeoverTest.h, run on the Rooms page)
// as "Boiler test: passed on … · Open" and links to it; the attended heating test is retired, so its heat
// controls never show, even when a status claims they could prepare. What stays is the installer check
// without heat (readings, zero-only check). EN at 1280 and NL at phone width; no device is contacted.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const limits={minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,operator_lease_ms:5000,heat_request_interval_ms:60000};
// What rc.3 firmware answers: the heat path closed (pathReady), the zero-only check available.
const retired=()=>({schema:1,boot_id:'000000000000002a',revision:0,state_sequence:1,observed_at_ms:100,clock:'boot_monotonic_ms',
 available:false,blocked_reason:'proving_conditions_missing',phase:'idle',reason:'not_prepared',owned:false,can_prepare:false,can_prepare_zero:true,
 zero_test_available:true,site_confirmation_required:true,pressure_check_required:true,pressure_reading_required:true,
 pressure_reading_limits:{minimum_decibar:11,maximum_decibar:25},operator_lease_ms:5000,can_start:false,can_stop:false,
 reported_stop_confirmed:false,positive_frames:0,zero_frames:0,heat_remaining_ms:0,requested_flow_c:null,limits});
const steps=(o={})=>({disconnect:'not_run',confirm:'not_run',start:'not_run',hot_water:'not_run',stop:'not_run',...o});
const test=o=>({state:'idle',at:null,steps:steps(),reason:null,summary:'never',flow_c:null,marked:false,marked_at:null,...o});
const active={state:'active',awaiting_confirmation:false,reconfirm_required:false,command:{send:true,flow_c:45,why:'heating'},last_sent:null,
 foreign_controller:null,confirmation:{age_s:900,restored:false},warnings:[],enabled:true,taken_over_before:true,thermostat_seen:false,boiler_limit:{flow_c:60,age_s:30,reads:1}};
const plan={schema:1,revision:2,mode:'active',minimum_flow_c:30,maximum_flow_c:60,rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,emitter:'radiator',
 sources:[{type:'ha',id:'climate.woonkamer'}],setpoint_entity:'climate.woonkamer',fallback_centi_c:2000,minimum_centi_c:500,maximum_centi_c:2500}]};
const heating=(t,a=active)=>({schema:1,revision:2,mode:'active',request:{heat:false,flow_c:0,reason:'idle'},
 rooms:[{id:'woonkamer',name:'Woonkamer',state:'active',inactive_until:0,status:'ok',source:'climate.woonkamer',setpoint_source:'ha',temperature:20.4,setpoint:21,demand:false}],
 ble_sensors:[],shadow:{today:{day:'2026-11-03',s:0,tado_unknown_s:0}},active:a,readiness:{state:'not_applicable',takeover_test:t},
 new_plan:{stored:true,mode:'active',reason:'no_thermostat'}});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const [width,language] of [[1280,'en'],[320,'nl']]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  let state=retired(),status=heating(test()),statusCode=200;
  const reply=(route,body,code=200)=>route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(body)});
  await page.route('http://status.test/**',async route=>{
   const req=route.request(),name=new URL(req.url()).pathname;
   if(req.method()==='POST')posts.push(name);
   if(name==='/auth/session')return reply(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(name==='/status')return reply(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(name==='/status/ems/telemetry')return reply(route,{reception:{state:'classic_reports_received'},transport:{enabled:true},fields:{},test:state});
   if(name==='/status/heating')return statusCode===200?reply(route,status):route.fulfill({status:statusCode,body:''});
   if(name==='/config/heating')return reply(route,plan);
   if(name==='/week-editor.js')return route.fulfill({status:404,body:''});
   const file=path.join(assets,name==='/'?'index.html':name);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(name.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:name.includes('.js')?'application/javascript':name.includes('.css')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:language,url:'http://status.test'}]);
  await page.goto('http://status.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  const en=language==='en',box=page.locator('#boiler-test [data-boiler-test-status]'),line=box.locator('[data-boiler-test-line]');
  const open=async(next,section='boiler_test')=>{status=next;await page.evaluate(s=>{document.getElementById('boiler-test')?.remove();return loadNativePage(s);},section);
   await page.locator('#boiler-test [data-workflow-help]').waitFor({state:'attached'});};
  // The line as read (whitespace folded): an exact text or a pattern.
  const shown=()=>page.evaluate(()=>{const b=document.querySelector('#boiler-test [data-boiler-test-status]');return b&&!b.hidden?b.textContent.replace(/\s+/g,' ').trim():null;});
  const shows=async text=>{
   try{await page.waitForFunction(([exact,source])=>{const b=document.querySelector('#boiler-test [data-boiler-test-status]');const t=b&&!b.hidden?b.textContent.replace(/\s+/g,' ').trim():null;
    return t!==null&&(exact?t===source:new RegExp(source).test(t));},[typeof text==='string',typeof text==='string'?text:text.source],{timeout:10000});}
   catch(error){throw new Error('status line '+JSON.stringify(await shown())+' is not '+text);}
  };
  // Never run: a short line and the way to the test.
  await open(heating(test()));
  await shows(en?'Boiler test: not run yet · Open':'Keteltest: nog niet uitgevoerd · Openen');
  assert.equal(await box.locator('a').getAttribute('href'),'#boiler-test');
  // Passed, kept across restarts and updates: with its date and time.
  await open(heating(test({state:'passed',at:1762029120,summary:'passed',flow_c:52,steps:steps({disconnect:'pass',confirm:'pass',start:'pass',hot_water:'pass',stop:'pass'})})));
  await shows(en?/^Boiler test: passed on .+\d.+ · Open$/:/^Keteltest: geslaagd op .+\d.+ · Openen$/);
  // Marked by the owner: a mark with its date, never a pass.
  await open(heating(test({summary:'marked',marked:true,marked_at:1762180000})));
  await shows(en?/^Boiler test: marked as done by you on .+ · Open$/:/^Keteltest: door jou gemarkeerd als gedaan op .+ · Openen$/);
  assert.doesNotMatch(await line.innerText(),en?/passed/:/geslaagd/);
  // An installation the E32 controlled before: not needed.
  await open(heating(test({summary:'not_needed'})));
  await shows(en?'Boiler test: not needed: the E32 has controlled this boiler before · Open':'Keteltest: niet nodig: de E32 heeft deze ketel al eerder geregeld · Openen');
  // Running now, a test ended by a restart, a failure.
  await open(heating(test({state:'running',at:1762029120,summary:'running',step:'start',phase:'waiting_burner'})));
  await shows(en?'Boiler test: running now (step 3 of 5) · Open':'Keteltest: loopt nu (stap 3 van 5) · Openen');
  await open(heating(test({state:'stopped',at:1762029120,summary:'stopped',reason:'e32_restarted',steps:steps({disconnect:'pass',confirm:'fail'})})));
  await shows(en?/^Boiler test: ended on .+ because the E32 restarted · Open$/:/^Keteltest: beëindigd op .+ omdat de E32 herstartte · Openen$/);
  await open(heating(test({state:'failed',at:1762029120,summary:'failed',reason:'no_burner',steps:steps({disconnect:'pass',confirm:'pass',start:'fail'})})));
  await shows(en?/^Boiler test: not passed on .+ · Open$/:/^Keteltest: niet geslaagd op .+ · Openen$/);
  // Firmware without the test or without active control, or no status: no line.
  await open(heating(undefined));await page.waitForTimeout(150);assert.equal(await box.isVisible(),false);
  await open(heating(test(),{...active,enabled:false}));await page.waitForTimeout(150);assert.equal(await box.isVisible(),false);
  statusCode=404;await open(heating(test()));await page.waitForTimeout(150);assert.equal(await box.isVisible(),false);statusCode=200;
  // The installer check: no heat control, whatever the status claims (an older or stale answer).
  for(const claimed of [retired(),{...retired(),available:true,blocked_reason:'',can_prepare:true}]){
   state=claimed;await open(heating(test()),'boiler_trial');await page.evaluate(()=>BoilerData.refresh());
   const trial=page.locator('#boiler-test-trial');
   assert.equal(await trial.evaluate(d=>d.open),true);
   assert.equal(await trial.locator(':scope > summary').innerText(),en?'Installer check (no heat)':'Controle voor de installateur (zonder warmte)');
   assert.match(await trial.locator(':scope > p.pd-help').first().innerText(),en?/Nothing here asks the boiler for heat\. To test heating, use the boiler test on the Rooms page\./
    :/Niets hier vraagt de ketel om warmte\. Om het verwarmen te testen gebruik je de keteltest op de pagina Ruimtes\./);
   for(const hidden of ['[data-test-flow]','[data-test-duration]','[data-test-prepare]','[data-test-start]','[data-site-pressure-value]','.bt-steps','[data-trial-selection]','[data-trial-live]'])
    assert.equal(await page.locator('#boiler-test '+hidden).isVisible(),false,hidden+' stays hidden');
   await page.waitForFunction(()=>document.querySelector('#boiler-test [data-workflow-title]').textContent.length>0);
   assert.equal(await page.locator('#boiler-test [data-workflow-title]').innerText(),en?'Installer check without heat':'Controle zonder warmte');
   assert.match(await page.locator('#boiler-test [data-workflow-help]').innerText(),en?/^Confirm the setup once to read the heating settings or the device identity, or to run the zero-only test under Diagnostics\./
    :/^Bevestig de opstelling één keer om de verwarmingsinstellingen of de apparaatidentiteit te lezen/);
   // The zero-only check and its setup declaration stay.
   assert.equal(await page.locator('#boiler-test [data-site-confirm]').isVisible(),true);
   await page.locator('#boiler-test-reception > summary').click();
   assert.equal(await page.locator('#boiler-test [data-test-zero]').isVisible(),true);
   assert.equal(await page.locator('#boiler-test [data-heat-limits]').isVisible(),false);
  }
  assert.deepEqual(posts,[],'nothing is sent by opening or reading');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'no horizontal scroll');
  // Open: the boiler test on the Rooms page, in view.
  state=retired();await open(heating(test({summary:'not_needed'})));await shows(/·/);
  await box.locator('a').click();
  await page.waitForFunction(()=>location.hash==='#boiler-test');
  await page.locator('#heating-plan [data-heating-test]').waitFor();
  assert.equal(await page.locator('#heating-plan [data-heating-test] [data-heating-test-verdict]').innerText(),
   en?'Not needed: the E32 has controlled this boiler before.':'Niet nodig: de E32 heeft deze ketel al eerder geregeld.');
  assert.equal(await page.locator('#heating-plan [data-heating-test] [data-heating-test-steps]').evaluate(d=>d.open),true,'opened from the Boiler page: the steps show');
  assert.equal(await page.locator('[data-nav="heating"]').getAttribute('aria-current'),'page');
  assert.deepEqual(errors,[]);
  results.push({width,language,result:'PASS'});await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
