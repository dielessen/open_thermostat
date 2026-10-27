// Actual root/auth/fragment. Finite local HTTP fixtures only; no hardware calls.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(process.env.OPENTHERMOSTAT_TRIAL_GUIDANCE_EVIDENCE||'out/boiler-trial-guidance-browser');
const limits={minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,operator_lease_ms:5000,heat_request_interval_ms:60000};
const progress=()=>({schema:1,requested_temperature_reported:false,heating_operation_reported:false,duration_completed:false,requested_duration_s:600,end_reason:''});
const initial=()=>({schema:1,boot_id:'000000000000002a',revision:0,state_sequence:1,observed_at_ms:100,clock:'boot_monotonic_ms',
 available:true,blocked_reason:'',phase:'idle',reason:'not_prepared',owned:false,can_prepare:true,can_prepare_zero:true,
 zero_test_available:true,site_confirmation_required:true,pressure_check_required:true,pressure_reading_required:true,
 pressure_reading_limits:{minimum_decibar:11,maximum_decibar:25},operator_lease_ms:5000,can_start:false,can_stop:false,
 reported_stop_confirmed:false,positive_frames:0,zero_frames:0,heat_remaining_ms:0,requested_flow_c:null,limits,progress:progress()});
(async()=>{
 fs.mkdirSync(out,{recursive:true});const results=[];
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 try{for(const width of [1280,320])for(const language of ['en','nl']){
  const page=await browser.newPage({viewport:{width,height:950}});let state=initial(),posts=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const reply=(route,body)=>route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  const update=patch=>{Object.assign(state,patch);state.state_sequence++;state.observed_at_ms+=100;};
  await page.route('http://guidance.test/**',async route=>{
   const req=route.request(),name=new URL(req.url()).pathname;
   if(name==='/auth/session')return reply(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(name==='/status')return reply(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(name==='/status/ems/telemetry')return reply(route,{reception:{state:'classic_reports_received'},transport:{enabled:true},fields:{},test:state});
   if(name.startsWith('/boiler/test/')){
    assert.equal(req.method(),'POST');assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));posts.push(name);
    const body=req.postDataJSON();assert.equal(body.boot_id,state.boot_id);
    if(name.endsWith('/prepare')){
     assert.equal(body.flow_c,50);assert.equal(body.duration_s,600);assert.equal(body.pressure_decibar,20);
     for(const key of ['exclusive_owner_confirmed','independent_stop_confirmed','heat_path_confirmed','pressure_check_confirmed'])assert.equal(body[key],true);
     update({revision:body.revision,phase:'ready',owned:true,can_prepare:false,can_prepare_zero:false,can_start:true,can_stop:true,reported_stop_confirmed:true,zero_frames:1,requested_flow_c:50});
    } else if(name.endsWith('/start'))update({phase:'heating',can_start:false,reported_stop_confirmed:false,positive_frames:1,heat_remaining_ms:600000});
    else if(name.endsWith('/stop'))update({phase:'stopping',can_start:false,reported_stop_confirmed:false,heat_remaining_ms:0,progress:{...state.progress,end_reason:'explicit_stop'}});
    else assert.equal(name,'/boiler/test/keepalive');
    return reply(route,{accepted:true,test:state});
   }
   const file=path.join(assets,name==='/'?'index.html':name);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(name.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:name.includes('.js')?'application/javascript':name.includes('.css')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:language,url:'http://guidance.test'}]);
  await page.goto('http://guidance.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  const open=async()=>{await page.evaluate(()=>loadNativePage('boiler_test'));await page.locator('[data-workflow-help]').waitFor();await page.evaluate(()=>BoilerData.refresh());};
  const refresh=async()=>{await page.evaluate(()=>BoilerData.refresh());};
  const outcome=async expected=>{await page.waitForFunction(value=>document.querySelector('[data-trial-result]')?.dataset.outcome===value,expected);};
  const step=async expected=>assert.equal(await page.locator('[data-trial-step][aria-current="step"]').getAttribute('data-trial-step'),String(expected));
  await open();await step(1);
  assert.equal(posts.length,0);assert.equal(await page.locator('#boiler-test-reception').getAttribute('open'),null);
  assert.equal(await page.locator('[data-test-site] input[type=checkbox]').count(),1);
  assert.equal(await page.locator('[data-test-flow]').inputValue(),'50');assert.equal(await page.locator('[data-test-duration]').inputValue(),'600');
  assert.match(await page.locator('[data-trial-selection]').innerText(),/50 °C.*10/);
  assert.match(await page.locator('[data-trial-cadence]').innerText(),language==='nl'?/60 seconden.*Stop wordt direct/:/60 seconds.*Stop is sent immediately/);
  assert.equal(await page.locator('[data-site-pressure-value]').evaluate(e=>e.required&&e.validity.valueMissing),true);
  await page.screenshot({path:path.join(out,`SETUP-${language}-${width}.png`),fullPage:true});
  await page.locator('[data-site-pressure-value]').fill('2');await page.locator('[data-site-confirm]').check();await step(2);
  await page.locator('[data-test-prepare]').click();await page.waitForFunction(()=>!document.querySelector('[data-test-start]').disabled);await step(3);
  assert.match(await page.locator('[data-workflow-help]').innerText(),language==='nl'?/Druk op 3\. Verwarming starten/:/Press 3\. Start heating/);
  page.once('dialog',d=>d.accept());await page.locator('[data-test-start]').click();await outcome('running');
  assert.match(await page.locator('[data-trial-remaining]').innerText(),/10:00/);
  assert.doesNotMatch(await page.locator('[data-trial-result-title]').innerText(),/geslaagd|passed/);
  state.progress.requested_temperature_reported=true;state.progress.heating_operation_reported=true;update({heat_remaining_ms:540000});await refresh();
  await page.screenshot({path:path.join(out,`HEATING-${language}-${width}.png`),fullPage:true});
  const mutations=()=>posts.filter(p=>!p.endsWith('/keepalive'));
  assert.deepEqual(mutations(),['/boiler/test/prepare','/boiler/test/start']);
  update({phase:'stopping',reason:'heat_deadline',heat_remaining_ms:0,progress:{...state.progress,duration_completed:true,end_reason:'heat_deadline'}});await refresh();await outcome('running');
  update({phase:'completed',can_stop:false,can_prepare:true,reported_stop_confirmed:true,zero_frames:2});await refresh();await outcome('passed');await step(4);
  assert.equal(await page.locator('[data-trial-checks] li').count(),5);
  assert.equal(await page.locator('[data-site-pressure-value]').evaluate(e=>e.value===''&&!e.classList.contains('is-valid')),true,'consumed gauge value cannot retain a green check');
  for(const text of await page.locator('[data-trial-checks] li').allTextContents())assert.match(text,/^✓/);
  assert.equal(await page.locator('[data-trial-result]').evaluate(el=>el.nextElementSibling.matches('[data-test-form]')),true,'final result precedes repeat form');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`PASSED-${language}-${width}.png`),fullPage:true});
  // Result survives reopening, without renewing or starting an old session.
  const before=posts.length;await open();await outcome('passed');assert.equal(posts.length,before);
  update({progress:{...state.progress,duration_completed:false,end_reason:'explicit_stop'}});await refresh();await outcome('partial');
  update({progress:{...state.progress,heating_operation_reported:false}});await refresh();await outcome('unconfirmed');
  delete state.progress;update({});await refresh();await outcome('unconfirmed');
  update({positive_frames:0});await refresh();await outcome('not_heated');
  update({zero_only:true});await refresh();await outcome('zero_passed');
  update({phase:'fault',can_prepare:false,can_stop:true,reported_stop_confirmed:false,zero_only:false,progress:{...progress(),end_reason:'explicit_stop'}});await refresh();await outcome('failed');
  assert.match(await page.locator('[data-trial-result-title]').innerText(),language==='nl'?/Handmatig gestopt/:/Stopped manually/);
  assert.match(await page.locator('[data-workflow-help]').innerText(),language==='nl'?/Controleer nu de ketel/:/Check the boiler now/);
  update({phase:'ready',can_start:true,owned:true,reported_stop_confirmed:true});await open();
  assert.equal(await page.locator('[data-test-start]').isVisible(),false);
  assert.equal(await page.locator('[data-test-stop]').isEnabled(),true);
  assert.match(await page.locator('[data-workflow-help]').innerText(),language==='nl'?/eerdere proef niet/:/not supervising the previous test/);
  const stoppedBefore=posts.filter(p=>p.endsWith('/stop')).length;
  await page.locator('[data-test-stop]').click();assert.equal(posts.filter(p=>p.endsWith('/stop')).length,stoppedBefore+1);
  update({phase:'completed',can_start:false,can_stop:false,can_prepare:true,reported_stop_confirmed:true,zero_frames:3});await refresh();
  assert.doesNotMatch(await page.locator('[data-test-action]').innerText(),/Wait for a reported stop|Wacht op een gemelde stop/);
  assert.deepEqual(errors,[]);results.push({width,language,result:'PASS',guidedActions:true,honestOutcomes:true,reopenPreservesResult:true,physicalProof:false});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',physicalProof:false,cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',cases:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
