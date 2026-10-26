// Actual shipped root/auth/fragment with fixture telemetry, never real EMS.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const out=path.resolve(process.env.OPENTHERMOSTAT_CONFIGURATION_EVIDENCE||'out/boiler-configuration-browser');
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390]){
  const page=await browser.newPage({viewport:{width,height:950}});const errors=[],posts=[];let uncertain=false,statusReads=0;
  page.on('pageerror',e=>errors.push(e.message));
  const test={schema:1,boot_id:'000000000000002a',revision:0,state_sequence:0,observed_at_ms:100,
   available:false,blocked_reason:'transmit_blocked',phase:'idle',reason:'not_prepared',owned:false,can_prepare:false,
   can_start:false,can_stop:false,site_confirmation_required:true,reported_stop_confirmed:false,positive_frames:0,zero_frames:0,
   operator_remaining_ms:0,heat_remaining_ms:0,requested_flow_c:null,limits:null,physical_validation:false};
  let read={schema:1,boot_id:test.boot_id,revision:0,observed_at_ms:100,available:false,active:false,phase:'idle',reason:'not_requested',physical_validation:false};
  const reply=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
  await page.route('http://configuration.test/**',async route=>{
   const req=route.request(),name=new URL(req.url()).pathname;
   if(name==='/auth/session')return reply(route,{authenticated:true,csrf:'a'.repeat(64)});
   if(name==='/status')return reply(route,{controlMode:'shadow',ems:{},control:{fresh:false,reason:'missing'}});
   if(name==='/status/ems/telemetry'){
    ++statusReads;return reply(route,{reception:{state:'classic_reports_received',report_count:3,last_report_age_ms:100},
     transport:{enabled:true,transmit_compiled:false,transmitted_frames:0},fields:{},test,configuration_read:read});
   }
   if(req.method()==='POST'){
    assert.equal(name,'/boiler/test/read_configuration');assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));
    const body=req.postDataJSON();posts.push(body);
    assert.deepEqual(body,{schema:1,boot_id:test.boot_id,revision:read.revision+1,exclusive_owner_confirmed:true,independent_stop_confirmed:true});
    if(uncertain)return reply(route,{accepted:false},503);
    read={...read,revision:body.revision,observed_at_ms:read.observed_at_ms+1,available:false,active:true,
     phase:'queued',reason:'awaiting_poll',withdrawn:false};
    return reply(route,{accepted:true,configuration_read:read},202);
   }
   const file=path.join(assets,name==='/'?'index.html':name);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(name.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:name.endsWith('.js')||name.endsWith('.js.gz')?'application/javascript':name.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://configuration.test'}]);
  await page.goto('http://configuration.test/');await page.waitForFunction(()=>typeof loadNativePage==='function');
  await page.evaluate(()=>loadNativePage('boiler_test'));const button=page.locator('[data-read-configuration]');
  await button.waitFor();await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'nog niet opgevraagd':'not been requested'}).waitFor();
  assert.equal(await button.isDisabled(),true);assert.equal(posts.length,0);
  assert.equal(await page.locator('[data-site-pressure-label]').isHidden(),true);
  assert.match(await button.innerText(),lang==='nl'?/CV-instellingen/:/Read heating/);
  read={...read,available:true,observed_at_ms:102};await page.locator('[data-site-owner]').check();
  assert.equal(await button.isDisabled(),true);await page.locator('[data-site-stop]').check();await button.waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('[data-read-configuration]').disabled);
  // Cancel and visibility lost DURING confirmation cannot send.
  page.once('dialog',dialog=>dialog.dismiss());await button.click();assert.equal(posts.length,0);
  await page.evaluate(()=>{
   const original=window.confirm;window.confirm=()=>{
    Object.defineProperty(document,'visibilityState',{configurable:true,value:'hidden'});
    document.dispatchEvent(new Event('visibilitychange'));return true;
   };
   document.querySelector('[data-read-configuration]').click();window.confirm=original;
  });assert.equal(posts.length,0);
  await page.evaluate(()=>Object.defineProperty(document,'visibilityState',{configurable:true,value:'visible'}));
  await page.locator('[data-site-owner]').check();await page.locator('[data-site-stop]').check();
  uncertain=width===390;page.once('dialog',dialog=>dialog.accept());await button.click();
  await page.locator('[data-read-status]').filter({hasText:uncertain?(lang==='nl'?'niet bevestigd':'not confirmed'):(lang==='nl'?'toestemming':'allow the read')}).waitFor();
  assert.equal(posts.length,1);assert.equal(await page.locator('[data-site-owner]').isChecked(),false);
  assert.equal(await page.locator('[data-site-stop]').isChecked(),false);assert.equal(await button.isDisabled(),true);
  await page.waitForTimeout(5500);assert.equal(posts.length,1); // No retry/heat/lease renewal.
  if(!uncertain){
   read={...read,active:false,phase:'completed',observed_at_ms:103,reason:'configuration_received'};
   await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'CV-instellingen ontvangen':'Heating settings received'}).waitFor();
   assert.equal(await page.locator('[data-test-start]').isDisabled(),true);
  }
  // Confirmations prepared before a different read scope must not survive its
  // withdrawal. No extra read is emitted while the original reply is pending.
  read={...read,available:true,observed_at_ms:read.observed_at_ms+1};
  await page.locator('[data-site-owner]').check();await page.locator('[data-site-stop]').check();
  await page.waitForFunction(()=>!document.querySelector('[data-read-configuration]').disabled);
  read={...read,revision:read.revision+1,observed_at_ms:read.observed_at_ms+1,available:false,
   active:true,phase:'waiting',withdrawn:true,reason:'operator_session_expired'};
  await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'Wachten tot het huidige':'Waiting for the current'}).waitFor();
  assert.equal(await button.isDisabled(),true);
  for(const field of ['owner','stop']){
   assert.equal(await page.locator('[data-site-'+field+']').isDisabled(),true);
   assert.equal(await page.locator('[data-site-'+field+']').isChecked(),false);
  }
  const withdrawn={...read};
  // Even a later snapshot cannot retract a known withdrawal for this revision.
  const before=statusReads;
  read={...read,withdrawn:false,active:false,phase:'completed',available:true,
   observed_at_ms:read.observed_at_ms+1,reason:'configuration_received'};
  const deadline=Date.now()+8000;
  while(statusReads===before&&Date.now()<deadline)await page.waitForTimeout(100);
  assert(statusReads>before);await page.waitForTimeout(150);
  assert.match(await page.locator('[data-read-status]').innerText(),lang==='nl'?/Wachten tot het huidige/:/Waiting for the current/);
  assert.equal(await button.isDisabled(),true);assert.equal(posts.length,1);
  read={...withdrawn,active:false,phase:'failed',available:true,observed_at_ms:read.observed_at_ms+1};
  await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'bedienersessie is beëindigd':'operator session ended'}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`WITHDRAWN-${lang}-${width}.png`),fullPage:true});
  for(const malformed of [{withdrawn:'true',phase:'waiting',active:true,available:false},
                          {withdrawn:true,phase:'completed',active:false,available:true}]){
   const saved={...read};read={...read,...malformed,observed_at_ms:read.observed_at_ms+1};
   await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'niet beschikbaar':'unavailable'}).waitFor();
   assert.equal(await button.isDisabled(),true);assert.equal(posts.length,1);
   const seen=statusReads;
   read={...saved,withdrawn:false,phase:'completed',active:false,available:true,observed_at_ms:read.observed_at_ms+1};
   const until=Date.now()+8000;
   while(statusReads===seen&&Date.now()<until)await page.waitForTimeout(100);
   assert(statusReads>seen);await page.waitForTimeout(150);
   assert.match(await page.locator('[data-read-status]').innerText(),lang==='nl'?/niet beschikbaar/:/unavailable/);
   assert.equal(await button.isDisabled(),true);
   read={...saved,observed_at_ms:read.observed_at_ms+1};
   await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'bedienersessie is beëindigd':'operator session ended'}).waitFor();
  }
  await page.evaluate(()=>loadNativePage('boiler_test'));
  await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'bedienersessie is beëindigd':'operator session ended'}).waitFor();
  assert.equal(await button.isDisabled(),true);assert.equal(posts.length,1);
  await page.locator('[data-site-owner]').check();await page.locator('[data-site-stop]').check();
  await page.waitForFunction(()=>!document.querySelector('[data-read-configuration]').disabled);
  uncertain=false;page.once('dialog',dialog=>dialog.accept());await button.click();
  await page.locator('[data-read-status]').filter({hasText:lang==='nl'?'toestemming':'allow the read'}).waitFor();
  assert.equal(posts.length,2);assert.equal(await button.isDisabled(),true);
  assert.deepEqual(errors,[]);await page.screenshot({path:path.join(out,`${lang}-${width}.png`),fullPage:true});
  results.push({lang,width,posts:posts.length,withdrawalVisible:true,lateCompletionIgnored:true,
   malformedWithdrawalRejected:true,freshConfirmationRequired:true,passed:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:true,cases:results},null,2));console.log(JSON.stringify({passed:true,cases:results.length}));
})().catch(e=>{console.error(e);process.exitCode=1;});
