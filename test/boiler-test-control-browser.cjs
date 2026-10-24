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
  const page=await browser.newPage({viewport:{width,height:950}});let state=initial(),requests=[],errors=[],delayedStart=null,failStop=width===320,forcedOld=null;
  page.on('pageerror',e=>errors.push(e.message));
  function update(patch){Object.assign(state,patch);state.state_sequence++;state.observed_at_ms+=100;}
  const limits={minimum_flow_c:20,maximum_flow_c:60,maximum_duration_s:10,operator_lease_ms:5000};
  const response=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  await page.route('http://boiler.test/**',async route=>{
   const req=route.request(),pathname=new URL(req.url()).pathname;
   requests.push({path:pathname,method:req.method(),body:req.postData()});
   if(pathname==='/auth/session')return response(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(pathname==='/status')return response(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(pathname==='/status/ems/telemetry')return response(route,{reception:{state:'classic_reports_received',report_count:3,last_report_age_ms:100},
    transport:{enabled:true,transmit_compiled:false,transmitted_frames:0,receive_queue_dropped:0,invalid_telegrams:0,uart_errors:0,uart_resets:0},fields:{},test:forcedOld||state});
   if(pathname.startsWith('/boiler/test/')){
    assert.equal(req.method(),'POST');assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    const body=req.postDataJSON();assert.equal(body.schema,1);assert.equal(body.boot_id,state.boot_id);
    const action=pathname.split('/').pop();
    if(action==='prepare'){
     assert.equal(body.revision,state.revision+1);assert.equal(body.flow_c,40);assert.equal(body.duration_s,1);
     update({revision:body.revision,phase:'baseline',owned:true,can_prepare:false,can_start:false,can_stop:true,
      reported_stop_confirmed:false,operator_remaining_ms:5000,requested_flow_c:40});
    }else{
     assert.equal(body.revision,state.revision);
     if(action==='keepalive')update(state.phase==='baseline'?{phase:'ready',can_start:true,reported_stop_confirmed:true,zero_frames:1}:{});
     if(action==='start'){
      update({phase:'heating',can_start:false,reported_stop_confirmed:false,heat_remaining_ms:1000});
      if(width===390){delayedStart={route,body:{accepted:true,duplicate:false,error:'',test:structuredClone(state)}};return;}
     }
     if(action==='stop'){
      update({phase:'stopping',can_start:false,reported_stop_confirmed:false,heat_remaining_ms:0});
      if(failStop){failStop=false;return response(route,{accepted:false,error:'uncertain'},503);}
     }
    }
    return response(route,{accepted:true,duplicate:false,error:'',test:state},202);
   }
   const file=path.join(assets,pathname==='/'?'index.html':pathname);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(pathname.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:pathname.endsWith('.css.gz')?'text/css':pathname.endsWith('.js')||pathname.endsWith('.js.gz')?'application/javascript':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:'nl',url:'http://boiler.test'}]);
  await page.goto('http://boiler.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('boiler_test'));
  await page.locator('[data-test-state]').filter({hasText:'geblokkeerd'}).waitFor();
  assert.equal(await page.locator('[data-test-prepare]').isDisabled(),true);
  assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
  assert.equal(requests.some(r=>r.method!=='GET'),false);
  // No test code can grant real hardware permission. This is an explicit IO fixture.
  update({available:true,blocked_reason:'',can_prepare:true,limits});
  await page.waitForFunction(()=>!document.querySelector('[data-test-prepare]').disabled);
  await page.locator('[data-test-flow]').fill('61');await page.locator('[data-test-duration]').fill('1');
  await page.locator('[data-test-prepare]').click();assert.equal(requests.some(r=>r.path.endsWith('/prepare')),false);
  await page.locator('[data-test-flow]').fill('40');await page.locator('[data-test-prepare]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-test-start]').disabled);
  const readySnapshot=structuredClone(state);
  assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,0); // ready never auto-starts
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('[data-test-start]').click();
  assert.equal(requests.filter(r=>r.path.endsWith('/start')).length,0);
  page.once('dialog',dialog=>dialog.accept());await page.locator('[data-test-start]').click();
  if(width===390){
   await page.waitForTimeout(150);assert(delayedStart);
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
  await page.locator('[data-test-state]').filter({hasText:'afgerond'}).waitFor();
  assert.equal(await page.locator('[data-test-stop]').isDisabled(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`CONTROL-${width}.png`),fullPage:true});
  // Reopening a ready owned session does not renew or start it automatically.
  update({phase:'ready',can_prepare:false,can_stop:true,can_start:true,owned:true,reported_stop_confirmed:true});
  await page.evaluate(()=>loadNativePage('boiler_test'));
  await page.locator('[data-test-state]').filter({hasText:'Stopbasis gemeld'}).waitFor();
  const before=requests.filter(r=>r.method==='POST').length;await page.waitForTimeout(1300);
  assert.equal(requests.filter(r=>r.method==='POST').length,before);
  assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
  await page.evaluate(()=>mainScreen());await page.waitForTimeout(1300);
  assert.equal(requests.filter(r=>r.method==='POST').length,before);
  assert.equal(requests.some(r=>r.method==='POST'&&!r.path.startsWith('/boiler/test/')),false);
  // The same reported stop is translated after reopening in English.
  await page.context().addCookies([{name:'ot_ui_lang',value:'en',url:'http://boiler.test'}]);
  await page.reload();await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('boiler_test'));
  await page.locator('[data-test-facts] dd').filter({hasText:/^Yes$/}).waitFor();
  assert.equal(await page.locator('[data-test-facts] dd').filter({hasText:/^Ja$/}).count(),0);
  await page.waitForTimeout(1300);assert.equal(requests.filter(r=>r.method==='POST').length,before);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  assert.deepEqual(errors,[]);
  results.push({width,result:'PASS',fixtureOnly:true,noAutoStartOrResume:true,csrfPresent:true,stopWhilePending:true,
   uncertainStopNotReplayed:true,lateStartIgnored:true,staleReadbackIgnored:width===1280,navigationStopsRenewal:true,englishStopConfirmation:true,physicalProof:false});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',viewports:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
