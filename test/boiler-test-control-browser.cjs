// Shipped root/auth/fragment, fixture HTTP only; native service/policy tested separately.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_BOILER_CONTROL_EVIDENCE||'out/boiler-control-browser');
function initial(){return {schema:1,boot_id:'000000000000002a',revision:0,state_sequence:0,observed_at_ms:100,
 available:false,blocked_reason:'transmit_blocked',phase:'idle',reason:'not_prepared',owned:false,can_prepare:false,
 can_start:false,can_stop:false,reported_stop_confirmed:false,positive_frames:0,zero_frames:0,
 operator_remaining_ms:0,heat_remaining_ms:0,requested_flow_c:null,limits:null,physical_validation:false};}
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:950}});let state=initial(),requests=[],errors=[],delayedStart=null,failStop=width===320,failClose=width===320,forcedOld=null,delayPreparation=false,delayedPreparation=null;
  page.on('pageerror',e=>errors.push(e.message));
  function update(patch){Object.assign(state,patch);state.state_sequence++;state.observed_at_ms+=100;}
  const gaugeTrial=width===390;
  const limits={minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,operator_lease_ms:5000};
  let feedback={},controllerRequest=null;
  let heatTrial={profile_id:'ecomline-classic-manual-v1',installation_reviewed:false,telemetry_ready:false,
   reason:'pressure_unavailable',physical_validation:false,limits:{minimum_flow_c:40,maximum_flow_c:50,maximum_duration_s:600,
    minimum_pressure_decibar:10,maximum_pressure_decibar:25,minimum_measured_flow_centi:500,maximum_measured_flow_centi:9000}};
  const response=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  const until=async condition=>{for(let i=0;i<200&&!condition();++i)await page.waitForTimeout(25);assert(condition(),'fixture condition did not arrive');};
  await page.route('http://boiler.test/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;
   requests.push({path:pathname,method:req.method(),body:req.postData()});
   if(pathname==='/auth/session')return response(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(pathname==='/status')return response(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(pathname==='/status/ems/telemetry')return response(route,{reception:{state:'classic_reports_received',report_count:3,last_report_age_ms:100},
    transport:{enabled:true,transmit_compiled:false,transmitted_frames:0,receive_queue_dropped:0,invalid_telegrams:0,uart_errors:0,uart_resets:0},fields:feedback,heat_trial:heatTrial,controller_request:controllerRequest,test:forcedOld||state});
   if(pathname.startsWith('/boiler/test/')){
    assert.equal(req.method(),'POST');assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    const body=req.postDataJSON();assert.equal(body.schema,1);assert.equal(body.boot_id,state.boot_id);
    const action=pathname.split('/').pop();
    if(action==='prepare_zero'){
     assert.equal(body.revision,state.revision+1);assert.deepEqual(Object.keys(body).sort(),['boot_id','exclusive_owner_confirmed','independent_stop_confirmed','revision','schema']);
     assert.equal(body.exclusive_owner_confirmed,true);assert.equal(body.independent_stop_confirmed,true);
     update({revision:body.revision,phase:'baseline',owned:true,zero_only:true,can_prepare_zero:false,can_prepare:false,can_start:false,can_stop:true,reported_stop_confirmed:false});
    }else if(action==='prepare'){
     assert.equal(body.revision,state.revision+1);assert.equal(body.flow_c,50);assert.equal(body.duration_s,600);
     assert.equal(body.exclusive_owner_confirmed,true);assert.equal(body.independent_stop_confirmed,true);assert.equal(body.heat_path_confirmed,true);
     assert.equal(body.pressure_check_confirmed,true);
     if(gaugeTrial)assert.equal(body.pressure_decibar,15);
     else assert.equal(Object.hasOwn(body,'pressure_decibar'),false);
     update({revision:body.revision,phase:'baseline',owned:true,zero_only:false,can_prepare_zero:false,can_prepare:false,can_start:false,can_stop:true,
      reported_stop_confirmed:false,operator_remaining_ms:5000,requested_flow_c:50});
    }else if(action==='close_fault'){
     assert.equal(body.revision,state.revision);assert.equal(body.local_stop_confirmed,true);
     assert.deepEqual(Object.keys(body).sort(),['boot_id','local_stop_confirmed','revision','schema']);
     assert.equal(state.phase,'fault');assert.equal(state.reported_stop_confirmed,true);
     update({phase:'closed',owned:false,available:false,zero_test_available:false,blocked_reason:'restart_required',
      can_prepare:false,can_prepare_zero:false,can_start:false,can_stop:false,can_close_fault:false,restart_required:true});
     if(failClose){failClose=false;return response(route,{accepted:false,error:'uncertain'},503);}
    }else{
     assert.equal(body.revision,state.revision);
     if(action==='keepalive'&&state.zero_only)update({phase:'completed',can_stop:false,can_prepare_zero:true,reported_stop_confirmed:true,zero_frames:1});
     else if(action==='keepalive')update(state.phase==='baseline'?{phase:'ready',can_start:true,reported_stop_confirmed:true,zero_frames:1}:{});
     if(action==='start'){
      update({phase:'heating',can_start:false,reported_stop_confirmed:false,heat_remaining_ms:1000});
      if(width===390){delayedStart={route,body:{accepted:true,duplicate:false,error:'',test:structuredClone(state)}};return;}
     }
     if(action==='stop'){
      update({phase:'stopping',can_start:false,reported_stop_confirmed:false,heat_remaining_ms:0});
      if(failStop){failStop=false;return response(route,{accepted:false,error:'uncertain'},503);}
     }
    }
    if(delayPreparation && ['prepare','prepare_zero'].includes(action)){delayedPreparation={route,body:{accepted:true,test:structuredClone(state)}};return;}
    return response(route,{accepted:true,duplicate:false,error:'',test:state},202);
   }
   const file=path.join(assets,pathname==='/'?'index.html':pathname);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(pathname.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:pathname.endsWith('.css.gz')?'text/css':pathname.endsWith('.js')||pathname.endsWith('.js.gz')?'application/javascript':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://boiler.test'}]);
  await page.goto('http://boiler.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
  await page.locator('[data-test-state]').filter({hasText:'geblokkeerd'}).waitFor({state:'attached'});
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
  assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
  assert.equal(requests.some(r=>r.method!=='GET'),false);
  await page.locator('[data-heat-status]').filter({hasText:'verse meting van de keteldruk'}).waitFor({state:'attached'});
  assert.match(await page.locator('[data-heat-limits]').innerText(),/40–50 °C/);
  assert.match(await page.locator('[data-heat-limits]').innerText(),/1–2,5 bar/);
  assert.match(await page.locator('[data-heat-limits]').innerText(),/Niet beoordeeld/);
  // A live hot-water cycle must explain the blocked zero and heat buttons,
  // without a hidden read/heat request or any change to backend permission.
  feedback={measured_flow_temperature:{value:95,unit:'degC',state:'valid',quality:'reported'},
    dhw_active:{value:1,unit:'bool',state:'valid',quality:'inferred'}};
  heatTrial={...heatTrial,reason:'flow_outside_trial_limits'};
  await page.locator('[data-heat-status]').filter({hasText:'95 °C'}).waitFor({state:'attached'});
  assert.match(await page.locator('[data-heat-status]').innerText(),/5–<90 °C/);
  assert.match(await page.locator('[data-zero-help]').innerText(),/tapwaterbedrijf/);
  assert.equal(await page.locator('[data-test-zero]').isDisabled(),true);
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
  assert.equal(requests.some(r=>r.method!=='GET'),false);
  feedback={};

  controllerRequest={schema:1,profile_id:'ecomline-classic-separate-pressure-v1',source:'controller_uart_transmit',
    boot_id:'000000000000002a',observed_at_ms:1000,known:false,boiler_readback:false,value_c:null,emitted_at_ms:null,sequence:0};
  await page.locator('[data-controller-request-value]').filter({hasText:'Nog geen bevestigde'}).waitFor();
  controllerRequest={...controllerRequest,observed_at_ms:1100,known:true,value_c:50,emitted_at_ms:1050,sequence:1};
  await page.locator('[data-controller-request-value]').filter({hasText:'50 °C'}).waitFor();
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
  controllerRequest={...controllerRequest,observed_at_ms:1200,value_c:0,emitted_at_ms:1150,sequence:2};
  await page.locator('[data-controller-request-value]').filter({hasText:'0 °C'}).waitFor();
  // Healthy numbers cannot change the separately blocked test controls.
  heatTrial={...heatTrial,telemetry_ready:true,reason:'telemetry_ready'};
  await page.locator('[data-heat-status]').filter({hasText:'metingen vallen binnen'}).waitFor({state:'attached'});
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
  assert.equal(await page.locator('[data-test-start]').isDisabled(),true);

  heatTrial={...heatTrial,profile_id:'ecomline-classic-separate-pressure-v1',digital_pressure_required:false,
    separate_pressure_method_reviewed:false,telemetry_ready:false,reason:'pressure_check_method_unreviewed'};
  await page.locator('[data-heat-status]').filter({hasText:'geen digitale druksensor'}).waitFor({state:'attached'});
  assert.match(await page.locator('[data-heat-limits]').innerText(),/Grenzen afzonderlijke drukcontrole/);
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);

  // No test code can grant real hardware permission. This is an explicit IO fixture.
  heatTrial={...heatTrial,installation_reviewed:true,separate_pressure_method_reviewed:true,telemetry_ready:true,reason:'telemetry_ready'};
  if(gaugeTrial)heatTrial={...heatTrial,mode:'supervised_commissioning',installation_reviewed:false,separate_pressure_method_reviewed:false,operator_gauge_reading_required:true,limits:{...heatTrial.limits,minimum_pressure_decibar:11}};
  const gaugeFields=gaugeTrial?{pressure_reading_required:true,pressure_reading_limits:{minimum_decibar:11,maximum_decibar:25}}:{};
  update({available:true,blocked_reason:'',can_prepare:true,limits,site_confirmation_required:true,pressure_check_required:true,...gaugeFields});
  await page.locator('[data-test-site]').waitFor({state:'visible'});
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
  assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
  await page.locator('[data-site-confirm]').check();
  assert.equal(requests.some(r=>r.path.endsWith('/prepare')),false);
  if(gaugeTrial){
   assert.equal(await page.locator('[data-site-pressure-value]').evaluate(e=>e.required&&e.validity.valueMissing),true,
    'An empty required gauge reading must not appear valid');
   assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
   for(const invalid of ['1','2.6','1.55']){
    await page.locator('[data-site-pressure-value]').fill(invalid);
    assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
   }
   await page.locator('[data-site-pressure-value]').fill('1.5');
   assert.match(await page.locator('[data-heat-limits]').innerText(),/fysieke acceptatie staat nog open/);
  }
  feedback={measured_flow_temperature:{value:66,unit:'degC',state:'valid',quality:'reported'}};
  await page.locator('[data-heat-status]').filter({hasText:'Het water is al op of boven'}).waitFor({state:'attached'});
  await page.waitForFunction(()=>!document.querySelector('[data-test-prepare]').disabled);
  await page.locator('[data-test-flow]').fill('61');await page.locator('[data-test-duration]').fill('600');
  await page.locator('[data-test-prepare]').click();assert.equal(requests.some(r=>r.path.endsWith('/prepare')),false);
  await page.locator('[data-test-flow]').fill('50');await page.locator('[data-test-prepare]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-test-start]').disabled);
  assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
  assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
  assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
  assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
  if(gaugeTrial)assert.equal(await page.locator('[data-site-pressure-value]').inputValue(),'');
  const readySnapshot=structuredClone(state);
  assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,0); // ready never auto-starts
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('[data-test-start]').click();
  assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,0);
  page.once('dialog',dialog=>dialog.accept());await page.locator('[data-test-start]').click();
  if(width===390){
   await until(()=>delayedStart);
   assert.equal(await page.locator('[data-test-stop]').isDisabled(),false); // stop works while start response is pending
  }else await page.locator('[data-test-action]').filter({hasText:'Startverzoek aangenomen'}).waitFor();
  await page.locator('[data-test-stop]').click();
  if(width===320){
   await page.locator('[data-test-action]').filter({hasText:'niet bevestigd'}).waitFor();
   await page.waitForTimeout(200);assert.equal(requests.filter(r=>r.path.endsWith('/stop')).length,1);
   await page.locator('[data-test-stop]').click(); // explicit retry, never automatic
  }
  await page.locator('[data-test-action]').filter({hasText:'Stopverzoek aangenomen'}).waitFor();
  if(delayedStart){await response(delayedStart.route,delayedStart.body,202);await page.waitForTimeout(100);}
  assert.match(await page.locator('[data-test-state]').innerText(),/Stop aangevraagd/);
  assert.doesNotMatch(await page.locator('[data-test-action]').innerText(),/Startverzoek aangenomen/);
  assert.match(await page.locator('[data-test-facts]').innerText(),/Nog niet bevestigd/);
  const keepalives=requests.filter(r=>r.path.endsWith('/keepalive')).length;
  await page.waitForTimeout(1300);assert.equal(requests.filter(r=>r.path.endsWith('/keepalive')).length,keepalives);
  if(width===1280){
   forcedOld=readySnapshot;
   const before=requests.filter(r=>r.path==='/status/ems/telemetry').length;
   const deadline=Date.now()+8000;
   while(requests.filter(r=>r.path==='/status/ems/telemetry').length===before&&Date.now()<deadline)await page.waitForTimeout(100);
   assert(requests.filter(r=>r.path==='/status/ems/telemetry').length>before);
   await page.waitForTimeout(100);
   assert.match(await page.locator('[data-test-state]').innerText(),/Stop aangevraagd/);
   assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
   forcedOld=null;
  }
  update({phase:'completed',can_prepare:true,can_stop:false,reported_stop_confirmed:true,zero_frames:2});
  await page.locator('[data-test-state]').filter({hasText:'afgerond'}).waitFor({state:'attached'});
  assert.match(await page.locator('[data-test-action]').innerText(),/Stop na de opdracht gemeld; proef afgerond/,
   'Confirmed stop must replace the earlier waiting-for-stop notice');
  assert.equal(await page.locator('[data-test-stop]').isDisabled(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`CONTROL-${width}.png`),fullPage:true});
  // Reopening a ready owned session does not renew or start it automatically.
  update({phase:'ready',can_prepare:false,can_stop:true,can_start:true,owned:true,reported_stop_confirmed:true});
  await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
  await page.locator('[data-test-state]').filter({hasText:'Stopbasis gemeld'}).waitFor({state:'attached'});
  const before=requests.filter(r=>r.method==='POST').length;await page.waitForTimeout(1300);
  assert.equal(requests.filter(r=>r.method==='POST').length,before);
  assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
  await page.evaluate(()=>mainScreen());await page.waitForTimeout(1300);
  assert.equal(requests.filter(r=>r.method==='POST').length,before);
  assert.equal(requests.some(r=>r.method==='POST'&&!r.path.startsWith('/boiler/test/')),false);
  // The same reported stop is translated after reopening in English.
  await page.context().addCookies([{name:'ot_ui_lang',value:'en',url:'http://boiler.test'}]);
  await page.reload();await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
  await page.locator('[data-test-facts] dd').filter({hasText:/^Yes$/}).waitFor();
  assert.equal(await page.locator('[data-test-facts] dd').filter({hasText:/^Ja$/}).count(),0);
  assert.match(await page.locator('[data-heat-limits]').innerText(),gaugeTrial?/1.1–2.5 bar/:/1–2.5 bar/);
  assert.match(await page.locator('[data-heat-limits]').innerText(),gaugeTrial?/physical acceptance remains open/:/Reviewed/);
  assert.match(await page.locator('[data-heat-limits]').innerText(),/Separate pressure check window/);

  await page.waitForTimeout(1300);assert.equal(requests.filter(r=>r.method==='POST').length,before);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  for(const language of ['nl','en']) {
   update({phase:'idle',owned:false,available:false,blocked_reason:'profile_missing',limits:null,
    can_prepare:false,can_start:false,can_stop:false,can_prepare_zero:true,zero_test_available:true,
    zero_only:false,operator_lease_ms:5000,reported_stop_confirmed:false});
   await page.context().addCookies([{name:'ot_ui_lang',value:language,url:'http://boiler.test'}]);
   await page.reload();await page.waitForFunction(()=>typeof loadNativePage==='function');
   await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   await page.locator('[data-test-site]').waitFor({state:'visible'});
   assert.equal(await page.locator('[data-test-zero]').isDisabled(),true);
   await page.locator('[data-site-confirm]').check();
   await page.waitForFunction(()=>!document.querySelector('[data-test-zero]').disabled);
   assert.match(await page.locator('[data-test-state]').innerText(),language==='nl'?/Alleen een nulvraagproef/:/Only a zero-demand test/);
   assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
   assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
   const zeroBefore=requests.filter(r=>r.method==='POST').length;
   await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   page.once('dialog',dialog=>dialog.dismiss());await page.locator('[data-test-zero]').click();
   assert.equal(requests.filter(r=>r.method==='POST').length,zeroBefore);
   await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   page.once('dialog',dialog=>dialog.accept());await page.locator('[data-test-zero]').click();
   await page.waitForFunction(()=>document.querySelector('[data-test-state]').textContent.includes(document.cookie.includes('ot_ui_lang=nl')?'afgerond':'completed'));
   assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
   assert.equal(state.zero_only,true);assert.equal(state.positive_frames,0);
   const zeroRequests=requests.filter(r=>r.method==='POST').slice(zeroBefore);
   assert.equal(zeroRequests.filter(r=>r.path.endsWith('/prepare_zero')).length,1);
   assert.equal(zeroRequests.some(r=>r.path.endsWith('/start')||r.path.endsWith('/prepare')),false);
   assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
   assert.equal(await page.locator('[data-site-confirm]').isChecked(),false);
   assert.equal(await page.locator('[data-test-zero]').isDisabled(),true);
   const finished=requests.filter(r=>r.method==='POST').length;await page.waitForTimeout(1200);
   assert.equal(requests.filter(r=>r.method==='POST').length,finished);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   assert.deepEqual(errors,[]);
  }
  // Fault closure is an explicit local acknowledgment after reported stop,
  // never a general reset or an automatically replayed recovery command.
  for(const language of ['nl','en']) {
   update({phase:'fault',owned:false,available:false,zero_test_available:true,blocked_reason:'profile_missing',
    can_prepare:false,can_prepare_zero:false,can_start:false,can_stop:true,can_close_fault:false,
    restart_required:false,reported_stop_confirmed:false});
   await page.context().addCookies([{name:'ot_ui_lang',value:language,url:'http://boiler.test'}]);
   await page.reload();await page.waitForFunction(()=>typeof loadNativePage==='function');
   await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   await page.locator('[data-test-close-fault]').waitFor({state:'visible'});
   assert.equal(await page.locator('[data-test-close-fault]').isDisabled(),true);
   if(width===1280) {
    update({can_close_fault:true}); // malformed permission without reported stop
    await page.locator('[data-test-state]').filter({hasText:language==='nl'?'Proefstatus niet beschikbaar':'Test status unavailable'}).waitFor({state:'attached'});
    assert.equal(await page.locator('[data-test-close-fault]').isVisible(),false);
   }
   update({can_close_fault:true,reported_stop_confirmed:true});
   await page.waitForFunction(()=>!document.querySelector('[data-test-close-fault]').disabled);
   const beforeClose=requests.filter(r=>r.method==='POST').length;
   page.once('dialog',dialog=>dialog.dismiss());await page.locator('[data-test-close-fault]').click();
   assert.equal(requests.filter(r=>r.method==='POST').length,beforeClose);
   page.once('dialog',dialog=>dialog.accept());await page.locator('[data-test-close-fault]').click();
   await page.locator('[data-test-state]').filter({hasText:language==='nl'?'afgesloten na gemelde stop':'closed after reported stop'}).waitFor({state:'attached'});
   assert.equal(await page.locator('[data-test-close-fault]').isVisible(),false);
   for(const selector of ['[data-test-zero]','[data-test-prepare]','[data-test-start]','[data-test-stop]'])
    assert.equal(await page.locator(selector).isDisabled(),true);
   await page.waitForTimeout(1200);
   const closeRequests=requests.filter(r=>r.method==='POST').slice(beforeClose);
   assert.equal(closeRequests.length,1);assert(closeRequests[0].path.endsWith('/close_fault'));
   await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   await page.locator('[data-test-state]').filter({hasText:language==='nl'?'afgesloten na gemelde stop':'closed after reported stop'}).waitFor({state:'attached'});
   await page.waitForTimeout(1200);assert.equal(requests.filter(r=>r.method==='POST').length,beforeClose+1);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
   assert.deepEqual(errors,[]);
  }
  // Brief visibility loss between renewal ticks must retire authority forever,
  // including preparation replies which arrive after the page becomes visible.
  for(const mode of ['prepare','prepare_zero','ready','pagehide']) {
   state={...initial(),revision:state.revision,state_sequence:state.state_sequence+1,observed_at_ms:state.observed_at_ms+100,
    available:true,blocked_reason:'',can_prepare:true,can_prepare_zero:true,zero_test_available:true,
    site_confirmation_required:true,pressure_check_required:true,operator_lease_ms:5000,limits,...gaugeFields};
   await page.evaluate(()=>loadNativePage('boiler_trial'));await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   await page.waitForFunction(()=>!document.querySelector('[data-site-confirm]').disabled);
   await page.locator('[data-site-confirm]').check();await page.locator('[data-site-confirm]').check();
   await page.locator('[data-site-confirm]').check();await page.locator('[data-site-confirm]').check();
   if(gaugeTrial)await page.locator('[data-site-pressure-value]').fill('1.5');
   await page.locator('[data-test-flow]').fill('50');await page.locator('[data-test-duration]').fill('600');
   delayPreparation=true;delayedPreparation=null;
   if(mode==='prepare_zero')page.once('dialog',dialog=>dialog.accept());
   await page.locator('#boiler-test-reception').evaluate(node=>node.open=true);
   await page.locator(mode==='prepare_zero'?'[data-test-zero]':'[data-test-prepare]').click();
   await until(()=>delayedPreparation);
   if(['ready','pagehide'].includes(mode)) {
    await response(delayedPreparation.route,delayedPreparation.body,202);delayPreparation=false;
    await page.waitForFunction(()=>!document.querySelector('[data-test-start]').disabled);
   }
   await page.evaluate(eventType=>{
    if(eventType==='pagehide'){window.dispatchEvent(new Event('pagehide'));return;}
    Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});
    document.dispatchEvent(new Event('visibilitychange'));
    Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});
    document.dispatchEvent(new Event('visibilitychange'));
   },mode);
   if(['ready','pagehide'].includes(mode))assert.equal(await page.locator('[data-test-start]').isDisabled(),true,'authority must end immediately');
   const posts=requests.filter(r=>r.method==='POST').length;
   if(delayPreparation){await response(delayedPreparation.route,delayedPreparation.body,202);delayPreparation=false;}
   update({phase:'ready',zero_only:mode==='prepare_zero',can_start:mode!=='prepare_zero',reported_stop_confirmed:true});
   await page.waitForTimeout(1500);
   assert.equal(requests.filter(r=>r.method==='POST').length,posts,'late preparation must not renew after brief hide');
   assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
   assert.equal(await page.locator('[data-test-stop]').isDisabled(),false);
  }
  results.push({width,result:'PASS',fixtureOnly:true,noAutoStartOrResume:true,csrfPresent:true,stopWhilePending:true,
   uncertainStopNotReplayed:true,lateStartIgnored:true,staleReadbackIgnored:width===1280,navigationStopsRenewal:true,englishStopConfirmation:true,zeroOnlyNlEn:true,perTestDeclarations:true,zeroNeedsNoHeatPath:true,faultClosureNlEn:true,uncertainClosureNotReplayed:true,closedDoesNotResume:true,heatEnvelopeNlEn:true,gaugeTrial,healthyTelemetryCannotUnlock:true,briefHideRetiresSupervision:true,latePreparationCannotRearm:true,pagehideRetiresSupervision:true,physicalProof:false});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
