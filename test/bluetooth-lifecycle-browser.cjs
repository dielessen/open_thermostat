// Shipped root/Bluetooth/auth assets with finite isolated HTTP gates; no radio/device actions.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const values=['temperature','humidity','battery','battery_low','light','light_level','button','target_temperature','external_temperature','state_revision'];
function snapshot(){
 const d={...Object.fromEntries([...values,'temperature_age_ms','humidity_age_ms','battery_age_ms','last_accepted_age_ms','counter','rssi','declared_device_type','firmware_32','firmware_24','target_temperature_age_ms','external_temperature_age_ms','state_revision_age_ms'].map(k=>[k,null])),
  address:'aabbccddeeff',profile:'shelly_ht_display',name:'Saved sensor',encryption:'bthome_v2',key_stored:true,
  control_qualified:false,measurement_qualified:false,message_integrity:true,status:'received',old_counter_drops:0,
  temperature:2300,temperature_age_ms:100,counter:1,rssi:-60};
 return {schema:1,pending_restart:false,scan_pending:false,discovery_full:false,config_error:'none',queue_drops:0,nearby:[],devices:[d]};
}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl']){
  const page=await browser.newPage({viewport:{width:390,height:900}}),errors=[],failed=[];
  let data=snapshot(),statusReads=0,statusInFlight=0,configReads=0,writes=0,scans=0,holdStatus=false,holdConfig=false,holdWrite=false,holdScan=false;
  const statusGates=[],configGates=[],writeGates=[],scanGates=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('requestfailed',r=>failed.push({path:new URL(r.url()).pathname,method:r.method()}));
  await page.addInitScript(()=>{window.__bleVisibility='visible';Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__bleVisibility});});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;
   if(url.origin!=='http://opth.test')return route.abort();
   const json=async (body,headers={})=>{try{await route.fulfill({json:body,headers});}catch(e){if(!req.failure())throw e;}};
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/config/boiler-display')return json({model:'none'});
   if(p==='/bluetooth/status'){
    ++statusReads;++statusInFlight;const answer=structuredClone(data);
    try{if(holdStatus){holdStatus=false;await new Promise(resolve=>statusGates.push(resolve));}return await json(answer);}finally{--statusInFlight;}
   }
   if(p==='/config/bluetooth'&&req.method()==='GET'){
    ++configReads;const answer=structuredClone(data);if(holdConfig){holdConfig=false;await new Promise(resolve=>configGates.push(resolve));}return json(answer,{ETag:'"'+'b'.repeat(64)+'"'});
   }
   if(p==='/config/bluetooth'&&req.method()==='POST'){
    ++writes;assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));assert.equal(req.headers()['if-match'],'"'+'b'.repeat(64)+'"');
    const payload=req.postDataJSON();if(holdWrite){holdWrite=false;await new Promise(resolve=>writeGates.push(resolve));}
    data.devices[0].name=payload.devices[0].name;data.pending_restart=true;data.devices[0].status='pending_restart';for(const key of values)data.devices[0][key]=null;
    return json({changed:true,pending_restart:true});
   }
   if(p==='/config/bluetooth/scan'){
    ++scans;assert.equal(req.method(),'POST');if(holdScan){holdScan=false;await new Promise(resolve=>scanGates.push(resolve));}return json({scan_started:true});
   }
   const file=path.join(assets,p==='/'?'index.html':p);
   if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':/\.css(?:\.gz)?$/.test(p)?'text/css':'text/html'});
  });
  const until=async condition=>{for(let i=0;i<200&&!condition();++i)await page.waitForTimeout(10);assert(condition(),'finite HTTP fixture condition did not arrive');};
  const visibility=(value,events=1)=>page.evaluate(([v,n])=>{window.__bleVisibility=v;for(let i=0;i<n;++i)document.dispatchEvent(new Event('visibilitychange'));},[value,events]);
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);await page.clock.install();
  await page.goto('http://opth.test/');await page.evaluate(()=>loadNativePage('bluetooth'));await page.locator('#ble-save:enabled').waitFor();
  // Pause page time (it flows naturally after clock.install): from here only runFor moves it, so a
  // naturally elapsing poll tick cannot add a request between an action and its count assertion.
  const pause=async()=>{for(;;){const at=await page.evaluate(()=>Date.now())+500;
   try{await page.clock.pauseAt(at);return;}catch(e){if(!/past/.test(e.message))throw e;}}};
  await pause();await until(()=>statusInFlight===0);
  const name=page.locator('[data-ble-field=name]'),key=page.locator('#ble-rows input[type=password]');
  await name.fill('Kept draft');await page.locator('[data-ble-field=key_action]').selectOption('set');await key.fill('1'.repeat(32));
  await page.locator('#ble-rows details summary').click();await key.focus();
  holdStatus=true;await page.clock.runFor(5000);await until(()=>statusGates.length===1);
  await visibility('hidden');await until(()=>failed.some(x=>x.path==='/bluetooth/status'));
  const hiddenReads=statusReads;await page.clock.runFor(20000);assert.equal(statusReads,hiddenReads);
  data.devices[0].temperature=2400;data.nearby=['0123456789ab'];
  // Two visible events in one task: the second must not start a second read. As two separate calls the
  // first read could already have finished, and then a second read is correct.
  await visibility('visible',2);
  await page.locator('[data-ble-address="0123456789ab"]').waitFor();
  assert.equal(statusReads,hiddenReads+1);statusGates.shift()();await page.waitForTimeout(50);
  assert.equal(await name.inputValue(),'Kept draft');assert.equal(await key.inputValue(),'1'.repeat(32));
  assert.equal(await key.evaluate(e=>e===document.activeElement),true);assert.equal(await page.locator('#ble-rows details').getAttribute('open'),'');
  assert.match(await page.locator('[data-readings]').textContent(),/Save and restart|Sla op en herstart/);
  assert.equal(await page.locator('[data-ble-address="0123456789ab"]').count(),1);
  // Real status deadline remains visible and keeps the normal five-second retry.
  holdStatus=true;await page.clock.runFor(5000);await until(()=>statusGates.length===1);await page.clock.runFor(10000);
  await page.waitForFunction(()=>/unavailable|niet beschikbaar/.test(document.querySelector('[data-readings]')?.textContent));
  const timeoutReads=statusReads;statusGates.shift()();await page.waitForTimeout(50);assert.equal(statusReads,timeoutReads);
  await page.clock.runFor(5000);await page.waitForFunction(()=>/Save and restart|Sla op en herstart/.test(document.querySelector('[data-readings]')?.textContent));
  assert.equal(statusReads,timeoutReads+1);assert.equal(await key.inputValue(),'1'.repeat(32));
  assert.match(await page.locator('#ble-status').textContent(),/Bluetooth status updated|Bluetoothstatus bijgewerkt/);
  // An explicitly confirmed config reload owns its readback; automatic status
  // reads stay paused through visibility changes until that load completes.
  holdConfig=true;page.once('dialog',dialog=>dialog.accept());await page.locator('#ble-reload').click();await until(()=>configGates.length===1);
  const loadingReads=statusReads,loadingConfigReads=configReads;
  await visibility('hidden');await visibility('visible');await page.clock.runFor(5000);
  assert.equal(statusReads,loadingReads);assert.equal(configReads,loadingConfigReads);
  configGates.shift()();await page.locator('#ble-save:enabled').waitFor();
  assert.equal(await name.inputValue(),'Saved sensor');assert.equal(await key.inputValue(),'');
  await name.fill('Kept draft');await page.locator('[data-ble-field=key_action]').selectOption('set');await key.fill('1'.repeat(32));
  // Submitted save survives hide/navigation; retired pages clear passwords and
  // never read back, replay or mutate the newly selected page.
  holdWrite=true;await page.locator('#ble-save').click();await until(()=>writeGates.length===1);
  const readsBeforeSave=statusReads;await page.clock.runFor(6000);assert.equal(statusReads,readsBeforeSave);
  await page.evaluate(()=>window.retiredBle=document.getElementById('bluetooth-page'));
  // Loading another page needs its timers: let page time flow again.
  await page.clock.resume();
  await visibility('hidden');await page.evaluate(()=>loadNativePage('about'));await page.locator('#about-heading').waitFor();
  assert.equal(await page.evaluate(()=>retiredBle.querySelector('input[type=password]').value),'');
  const retiredConfigReads=configReads;writeGates.shift()();await until(()=>data.devices[0].name==='Kept draft');await page.waitForTimeout(50);
  assert.equal(configReads,retiredConfigReads);assert.equal(writes,1);
  assert(!failed.some(x=>x.path==='/config/bluetooth'&&x.method==='POST'));
  await visibility('visible');await page.clock.runFor(10000);assert.equal(statusReads,readsBeforeSave);
  assert.equal(await page.locator('#about-heading').count(),1);
  // Mount hidden: one configuration read, no automatic status loop.
  await visibility('hidden');await page.evaluate(()=>loadNativePage('bluetooth'));await page.locator('#ble-save:enabled').waitFor();
  await page.clock.runFor(10000);assert.equal(statusReads,readsBeforeSave);await visibility('visible');await until(()=>statusReads>readsBeforeSave);
  assert.equal(await name.inputValue(),'Kept draft');assert.equal(writes,1);
  // Explicit scan also retains its own deadline through navigation.
  holdScan=true;await page.locator('#ble-scan').click();await until(()=>scanGates.length===1);
  await page.evaluate(()=>loadNativePage('about'));scanGates.shift()();await page.waitForTimeout(50);
  assert.equal(scans,1);assert(!failed.some(x=>x.path==='/config/bluetooth/scan'));assert.equal(await page.locator('#about-heading').count(),1);
  // A timed-out save is unconfirmed even if its server-side write arrives late.
  await page.evaluate(()=>loadNativePage('bluetooth'));await page.locator('#ble-save:enabled').waitFor();await name.fill('Late write');
  holdWrite=true;await page.locator('#ble-save').click();await until(()=>writeGates.length===1);await page.clock.runFor(10000);
  await page.waitForFunction(()=>/not.*confirmed|niet.*bevestigd/.test(document.querySelector('#ble-status')?.textContent));
  assert.equal(await page.locator('#ble-save').isDisabled(),true);assert.equal(writes,2);
  writeGates.shift()();await until(()=>data.devices[0].name==='Late write');await page.clock.runFor(15000);
  assert.equal(writes,2);assert.equal(await page.locator('#ble-save').isDisabled(),true);assert.equal(await name.inputValue(),'Late write');
  assert.match(await page.locator('#ble-status').textContent(),/not.*confirmed|niet.*bevestigd/);
  assert.deepEqual(errors,[]);results.push({lang,status:'PASS',hiddenStopsAndAbortsPoll:true,resumeOneRead:true,draftFocusKeyAndDetailsPreserved:true,
   genuineReadDeadlineBackoff:true,submittedSaveAndScanSurviveNavigation:true,retiredReadback:0,passwordClearedOnUnmount:true,unconfirmedWriteNotReplayed:true});
  await page.close();
 }}finally{await browser.close();}
 console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
