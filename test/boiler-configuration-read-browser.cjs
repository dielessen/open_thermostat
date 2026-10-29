// The shipped three-step workflow, simulated HTTP only. Never contacts hardware.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),out=path.resolve(__dirname,'../out/boiler-configuration-browser');
const limits={minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,operator_lease_ms:5000};
const sample=value=>({value,unit:'degC',state:'valid',quality:'reported',age_ms:100,source_type:24,source_address:8});
function initial(){return {schema:1,boot_id:'000000000000002a',revision:0,state_sequence:1,observed_at_ms:100,
 available:false,blocked_reason:'proving_conditions_missing',phase:'idle',reason:'not_prepared',owned:false,
 can_prepare:false,can_start:false,can_stop:false,reported_stop_confirmed:false,positive_frames:0,zero_frames:0,
 operator_remaining_ms:0,heat_remaining_ms:0,requested_flow_c:null,limits,site_confirmation_required:true,
 pressure_check_required:true,pressure_reading_required:true,pressure_reading_limits:{minimum_decibar:11,maximum_decibar:25},physical_validation:false};}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];fs.mkdirSync(out,{recursive:true});
 try{for(const lang of ['en','nl'])for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:950}}),posts=[],requests=[],errors=[];page.setDefaultTimeout(10000);
  await page.clock.install();let state=initial(),uncertain=false,identified=false;
  let read={schema:1,boot_id:state.boot_id,revision:0,observed_at_ms:100,available:true,identity_supported:true,identity_available:true,kind:'configuration',active:false,phase:'idle',reason:'not_requested',physical_validation:false};
  let heatReason='heating_setting_unavailable';
  const heat=()=>({profile_id:'ecomline-classic-separate-pressure-v1',mode:'supervised_commissioning',
   installation_reviewed:false,digital_pressure_required:false,separate_pressure_method_reviewed:true,operator_gauge_reading_required:true,
   telemetry_ready:heatReason==='telemetry_ready',reason:heatReason,physical_validation:false,
   limits:{minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,minimum_pressure_decibar:11,maximum_pressure_decibar:25,minimum_measured_flow_centi:500,maximum_measured_flow_centi:6000}});
  const reply=(route,data,status=200)=>route.fulfill({status,json:data});
  const snapshot=()=>({reception:{state:'classic_reports_received'},transport:{enabled:true},fields:{measured_flow_temperature:sample(25)},
   inventory:{schema:1,capacity:16,untracked_frames:0,devices:[{address:8,frames:3,age_ms:100,product_id:identified?211:null,version:identified?'2.3':null,brand_id:identified?1:null,untracked_types:0,telegram_types:identified?[2,24]:[24]},
    {address:23,frames:4,age_ms:100,product_id:null,version:null,brand_id:null,untracked_types:0,telegram_types:[53,51]}]},settings_policy:{transmit_compiled:false,installation_reviewed:false},test:state,configuration_read:read,heat_trial:heat()});
  page.on('pageerror',e=>errors.push(e.message));await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://trial.test'}]);
  await page.route('http://trial.test/**',route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push(p);
   if(p==='/auth/session')return reply(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return reply(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(p==='/status/ems/telemetry')return reply(route,snapshot());
   if(req.method()==='POST'){
    assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));const body=req.postDataJSON();posts.push({p,body});
    if(p.endsWith('/read_configuration')||p.endsWith('/read_identity')){
     const {target_address,...fixed}=body;
     assert.deepEqual(fixed,{schema:1,boot_id:state.boot_id,revision:read.revision+1,exclusive_owner_confirmed:true,independent_stop_confirmed:true});
     if(target_address!==undefined)assert.equal(p.endsWith('/read_identity')&&target_address,23,'Only an observed non-boiler device is targeted');
     if(uncertain)return reply(route,{accepted:false},503);
     read={...read,kind:p.endsWith('/read_identity')?'identity':'configuration',target_address:target_address??8,revision:body.revision,observed_at_ms:read.observed_at_ms+1,active:true,available:false,identity_available:false,phase:'queued',reason:'awaiting_poll'};
     return reply(route,{accepted:true,configuration_read:read},202);
    }
    if(p.endsWith('/prepare')){
     assert.equal(body.flow_c,50);assert.equal(body.duration_s,600);assert.equal(body.pressure_decibar,20);
     for(const key of ['exclusive_owner_confirmed','independent_stop_confirmed','heat_path_confirmed','pressure_check_confirmed'])assert.equal(body[key],true);
     state={...state,revision:body.revision,state_sequence:state.state_sequence+1,observed_at_ms:state.observed_at_ms+1,available:true,phase:'ready',owned:true,can_prepare:false,can_start:true,can_stop:true,reported_stop_confirmed:true};
    }else if(p.endsWith('/start'))state={...state,state_sequence:state.state_sequence+1,observed_at_ms:state.observed_at_ms+1,phase:'heating',can_start:false,reported_stop_confirmed:false,heat_remaining_ms:600000};
    else if(p.endsWith('/stop'))state={...state,state_sequence:state.state_sequence+1,observed_at_ms:state.observed_at_ms+1,phase:'stopping',can_start:false,reported_stop_confirmed:false};
    return reply(route,{accepted:true,test:state});
   }
   const f=path.join(assets,p==='/'?'index.html':p);if(!f.startsWith(assets+'/')||!fs.existsSync(f))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(f);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'text/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://trial.test/');await page.evaluate(()=>loadNativePage('boiler_trial'));
  const confirm=page.locator('[data-site-confirm]'),button=page.locator('[data-read-configuration]');
  await button.waitFor();assert.equal(await page.locator('#boiler-test-controls input[type=checkbox]').count(),1);
  const identify=page.getByRole('button',{name:lang==='nl'?'Apparaatidentiteit ophalen':'Read device identity',exact:true});
  await identify.waitFor();assert.equal(await identify.isDisabled(),true);assert.equal(posts.length,0,'No automatic identity request');
  assert.equal(await page.locator('#ems-device-list > details').count(),1,'Unknown raw sender does not duplicate the boiler card');
  await page.locator('#ems-unidentified').waitFor();assert.match(await page.locator('[data-unidentified-traffic]').textContent(),/0x17/);
  assert.equal(await button.isDisabled(),true);assert.equal(await page.locator('[data-test-prepare]').isHidden(),true);
  assert.equal(await page.locator('[data-test-flow]').inputValue(),'50');assert.equal(await page.locator('[data-test-duration]').inputValue(),'600');
  await page.locator('[data-site-pressure-value]').fill('2');await confirm.check();assert.equal(await button.isEnabled(),true);
  await identify.dblclick();assert.equal(posts.length,1);assert.equal(posts[0].p,'/boiler/test/read_identity');
  assert.equal(await confirm.isChecked(),true);assert.equal(await button.isDisabled(),true);
  identified=true;read={...read,active:false,available:true,phase:'completed',reason:'identity_received',observed_at_ms:read.observed_at_ms+1};
  await page.evaluate(()=>BoilerData.refresh());await page.waitForFunction(()=>document.querySelector('[data-read-configuration]').disabled===false);
  assert.equal(await identify.isHidden(),true);assert.match(await page.locator('#ems-device-list summary').textContent(),/EasyControl/);
  assert.equal(await confirm.isChecked(),true,'Identity read retains the same bounded setup declaration');
  // Another observed device gets its own explicit identity read, addressed to it.
  read={...read,identity_available:true,observed_at_ms:read.observed_at_ms+1};await page.evaluate(()=>BoilerData.refresh());
  await page.waitForFunction(()=>{const b=document.querySelector('[data-identify-address="23"]');return b&&!b.disabled;});
  await page.locator('#ems-unidentified > summary').click();
  const before0x17=posts.length;await page.locator('[data-identify-address="23"]').click();
  assert.equal(posts.length,before0x17+1);assert.equal(posts.at(-1).p,'/boiler/test/read_identity');assert.equal(posts.at(-1).body.target_address,23);
  read={...read,active:false,available:true,identity_available:false,phase:'completed',reason:'identity_received',observed_at_ms:read.observed_at_ms+1};
  await page.evaluate(()=>BoilerData.refresh());await page.waitForFunction(()=>document.querySelector('[data-read-configuration]').disabled===false);
  posts.length=0;
  await button.click();assert.equal(posts.length,1);assert.equal(await confirm.isChecked(),true,'Read must not consume the preparation confirmation');
  read={...read,active:false,available:true,phase:'completed',reason:'settings_report_received',observed_at_ms:read.observed_at_ms+1};
  state={...state,available:true,can_prepare:true,state_sequence:state.state_sequence+1,observed_at_ms:state.observed_at_ms+1};heatReason='telemetry_ready';
  await page.evaluate(()=>BoilerData.refresh());
  const prepare=page.locator('[data-test-prepare]'),start=page.locator('[data-test-start]'),stop=page.locator('[data-test-stop]');
  await prepare.waitFor();assert.equal(await prepare.isEnabled(),true);assert.equal(await button.isHidden(),true);assert.equal(await confirm.isChecked(),true);
  await page.screenshot({path:path.join(out,`READY-TO-PREPARE-${lang}-${width}.png`),fullPage:true});
  await prepare.click();await start.waitFor();assert.equal(await confirm.isChecked(),false);assert.equal(await prepare.isHidden(),true);
  assert.equal(posts.filter(r=>r.p.endsWith('/start')).length,0,'Preparation never starts heating');
  page.once('dialog',d=>d.dismiss());await start.click();assert.equal(posts.length,2);
  page.once('dialog',d=>d.accept());await start.click();assert.equal(posts.filter(r=>r.p.endsWith('/start')).length,1);
  await page.waitForFunction(()=>document.querySelector('[data-test-start]').hidden);
  await stop.waitFor();assert.equal(await stop.isEnabled(),true);assert.equal(await start.isHidden(),true);
  await page.screenshot({path:path.join(out,`HEATING-${lang}-${width}.png`),fullPage:true});
  await stop.click();assert.equal(posts.filter(r=>r.p.endsWith('/stop')).length,1);
  // A new page never inherits the old operator declaration or starts heating.
  state=initial();heatReason='heating_setting_unavailable';read={...read,active:false,available:true,phase:'idle'};
  await page.evaluate(()=>loadNativePage('boiler_trial'));await button.waitFor();assert.equal(await confirm.isChecked(),false);
  await page.locator('[data-site-pressure-value]').fill('2');await confirm.check();await page.clock.fastForward(120001);
  assert.equal(await confirm.isChecked(),false);assert.equal(await button.isDisabled(),true,'Polling never renews the declaration');
  await page.locator('[data-site-pressure-value]').fill('2');await confirm.check();uncertain=true;const before=posts.length;
  await button.click();await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'niet bevestigd':'not confirmed'}).waitFor();
  await page.clock.fastForward(5001);assert.equal(posts.length,before+1,'A failed read is not replayed by polling');
  state={...initial(),revision:1,state_sequence:state.state_sequence+1,phase:'closed',reason:'test_transport_unavailable',restart_required:true,reported_stop_confirmed:true,blocked_reason:'restart_required'};
  await page.evaluate(()=>BoilerData.refresh());const restart=page.locator('[data-test-restart]');await restart.waitFor();
  assert.equal(await button.isHidden(),true);assert.equal(await page.locator('[data-test-start]').isHidden(),true);
  page.once('dialog',d=>d.dismiss());const count=posts.length;await restart.click();
  assert.equal(posts.length,count,'Cancelled restart sends no request');assert(!requests.includes('/updates/status'));
  assert(!requests.some(p=>['/status/ems/devices','/status/boiler/settings'].includes(p)));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',explicitIdentityRead:true,canonicalDeviceIdentity:true,closedRestartCancellation:true,readPrepareStartStop:true,oneBoundedDeclaration:true,noAutoHeat:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
