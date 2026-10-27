// Shipped navigation/auth/settings assets, isolated HTTP only. No device actions.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html');
const config={hostname:'Fixture',interface_mode:'ethernet',listenPort:80,emsEnabled:false,emsForwarderEnabled:false,rtcEnabled:false,
 ntpEnabled:true,ntpHost:'pool.ntp.org',ntpUtcOffset:0,ntpDaylightUtcOffset:0,timeZone:'UTC',loggerEnabled:false,loggerHost:'',loggerPort:0,loggerTimeoutMs:1000,
 bt:{scanTime:10,scanInterval:30},mqtt:{enabled:false,modern_shadow:true,adapter_id:'fixture',brokerAddress:'127.0.0.1',brokerPort:1883,
  username:'',password:'',clientId:'fixture',base:'fixture',keepAlive:30,interval:10}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],requests=[],failed=[];let dialogs=0;
  let data=JSON.parse('{"App":true,"EMS":false,"__proto__":true,"<img src=x onerror=alert(1)>":false,"DeviceHostname":true}');
  let reads=0,writes=0,holdRead=false,holdWrite=false,replyCode=200;const readGates=[],writeGates=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>{++dialogs;d.dismiss();});
  page.on('requestfailed',r=>failed.push({path:new URL(r.url()).pathname,method:r.method()}));
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),p=url.pathname;requests.push({path:p,method:req.method()});
   if(url.origin!=='http://opth.test')return route.abort();
   const json=async (value,status=200)=>{try{await route.fulfill({json:value,status});}catch(error){if(!req.failure())throw error;}};
   if(p==='/auth/session')return json({authenticated:true,csrf:'a'.repeat(64)});
   if(p==='/status')return json({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}});
   if(p==='/config/boiler-display')return json({model:'none'});
   if(p==='/setup/status')return json({setup_active:false});
   if(p==='/config/device')return json(config);
   if(p==='/config/debug'){
    if(req.method()==='POST'){
     ++writes;assert.equal(req.headers()['x-openthermostat-csrf'],'a'.repeat(64));const payload=req.postDataJSON();
     assert(Object.values(payload).every(v=>typeof v==='boolean'));assert.equal(Object.hasOwn(payload,'__proto__'),true);
     if(holdWrite){holdWrite=false;await new Promise(resolve=>writeGates.push(resolve));}
     data=payload;return json({},201);
    }
    ++reads;const value=structuredClone(data),code=replyCode;
    if(holdRead){holdRead=false;await new Promise(resolve=>readGates.push(resolve));}return json(value,code);
   }
   let file=path.join(assets,p==='/'?'index.html':p);
   if(p==='/network.html'&&process.env.OPENTHERMOSTAT_NETWORK_FIXTURE)file=path.resolve(process.env.OPENTHERMOSTAT_NETWORK_FIXTURE);
   if(!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({body,contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':/\.css(?:\.gz)?$/.test(p)?'text/css':'text/html'});
  });
  const until=async condition=>{for(let i=0;i<200&&!condition();++i)await page.waitForTimeout(10);assert(condition(),'finite debug HTTP gate did not arrive');};
  const loadNetwork=async()=>{
   await page.evaluate(()=>loadNativePage('network'));
   await page.waitForFunction(()=>document.getElementById('DeviceHostname')?.value==='Fixture');
  };
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);await page.clock.install();
  await page.goto('http://opth.test/');await page.locator('.product-dashboard').waitFor();await loadNetwork();
  assert.equal(reads,0,'collapsed debug panel must not fetch settings');assert.equal(writes,0);
  const panel=page.locator('#DebugSettings'),summary=panel.locator(':scope > summary'),save=page.locator('#SaveDebugSettings'),reload=page.locator('#ReloadDebugSettings');
  assert.equal(await panel.evaluate(e=>e.open),false);assert.equal(await save.isDisabled(),true);assert.equal(await reload.isVisible(),false);
  await summary.click();await save.waitFor({state:'visible'});await page.waitForFunction(()=>document.getElementById('SaveDebugSettings')?.disabled===false);
  assert.equal(reads,1);assert.equal(await panel.locator('input[type=checkbox]').count(),5);
  assert.equal(await panel.locator('img').count(),0);assert.match(await panel.innerText(),/<img/);
  assert.equal(await page.locator('#DeviceHostname').count(),1);assert.equal(await page.locator('#DeviceHostname').inputValue(),'Fixture');
  const app=panel.locator('[data-feature="App"]'),ems=panel.locator('[data-feature="EMS"]');
  await app.uncheck();await summary.click();await summary.click();assert.equal(reads,1);assert.equal(await app.isChecked(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  // Closing retires a pending reload; reopening reads once and the old body
  // cannot replace the newer map or release that request's controls.
  holdRead=true;await reload.click();await until(()=>readGates.length===1);const closedReads=reads;
  await summary.click();await until(()=>failed.some(x=>x.path==='/config/debug'&&x.method==='GET'));
  data.EMS=true;await summary.click();await page.waitForFunction(()=>document.querySelector('[data-feature="EMS"]')?.checked===true);
  assert.equal(reads,closedReads+1);readGates.shift()();await page.waitForTimeout(50);
  assert.equal(await ems.isChecked(),true);assert.equal(await save.isEnabled(),true);
  // True deadlines are visible and do not silently start an automatic retry.
  holdRead=true;await reload.click();await until(()=>readGates.length===1);await page.clock.runFor(5000);
  await page.waitForFunction(()=>/unavailable|niet beschikbaar/.test(document.getElementById('DebugSettingsStatus')?.textContent));
  const deadlineReads=reads;readGates.shift()();await page.clock.runFor(10000);
  assert.equal(reads,deadlineReads);assert.equal(await save.isDisabled(),true);
  replyCode=503;await reload.click();await page.waitForFunction(()=>document.getElementById('ReloadDebugSettings')?.disabled===false);
  assert.equal(await save.isDisabled(),true);assert.equal(writes,0);replyCode=200;
  // Malformed flags cannot turn into unchecked defaults or enable Save.
  const known=data;data={App:'true'};await reload.click();await page.waitForFunction(()=>document.getElementById('ReloadDebugSettings')?.disabled===false);
  assert.equal(await save.isDisabled(),true);await page.evaluate(()=>saveDebugSettings());assert.equal(writes,0);data=known;
  await reload.click();await page.waitForFunction(()=>document.getElementById('SaveDebugSettings')?.disabled===false);
  await app.uncheck();await save.click();await page.waitForFunction(()=>/updated|bijgewerkt/.test(document.getElementById('DebugSettingsStatus')?.textContent));
  assert.equal(writes,1);assert.equal(data.App,false);assert.equal(dialogs,0);
  // An already submitted save survives navigation. The retired owner neither
  // changes About nor performs follow-up reads/restarts/replays.
  holdWrite=true;await app.check();await save.click();await until(()=>writeGates.length===1);const beforeLeaving=reads;
  await page.evaluate(()=>loadNativePage('about'));await page.locator('#about-heading').waitFor();writeGates.shift()();await until(()=>data.App===true);
  await page.clock.runFor(10000);assert.equal(reads,beforeLeaving);assert.equal(writes,2);
  assert(!failed.some(x=>x.path==='/config/debug'&&x.method==='POST'));assert.equal(await page.locator('#about-heading').count(),1);
  await loadNetwork();assert.equal(reads,beforeLeaving);await summary.click();await page.waitForFunction(()=>document.getElementById('SaveDebugSettings')?.disabled===false);
  // Late server commit after deadline remains unconfirmed until explicit reload.
  holdWrite=true;await app.uncheck();await save.click();await until(()=>writeGates.length===1);await page.clock.runFor(5000);
  await page.waitForFunction(()=>/not confirmed|niet bevestigd/.test(document.getElementById('DebugSettingsStatus')?.textContent));
  const uncertainReads=reads;writeGates.shift()();await until(()=>data.App===false);await page.clock.runFor(10000);
  assert.equal(reads,uncertainReads);assert.equal(writes,3);assert.equal(await save.isDisabled(),true);
  await reload.click();await page.waitForFunction(()=>document.getElementById('SaveDebugSettings')?.disabled===false);
  assert.equal(await app.isChecked(),false);assert.equal(dialogs,0);
  holdRead=true;await reload.click();await until(()=>readGates.length===1);
  const failuresBeforeDetach=failed.length;
  await page.evaluate(()=>document.getElementById('DebugSettings').remove());
  await until(()=>failed.slice(failuresBeforeDetach).some(x=>x.path==='/config/debug'&&x.method==='GET'));
  assert.equal(await page.evaluate(()=>window.DebugSettingsPage),null);readGates.shift()();
  assert(!requests.some(r=>r.method==='POST'&&r.path!=='/config/debug'));assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',closedPanelGets:0,lazyGet:true,foldKeepsDraft:true,readCancellationAndDeadline:true,
   malformedFlagsNotWritable:true,scopedSafeLabels:true,submittedPostSurvivesNavigation:true,unconfirmedWriteNoReplay:true,restarts:0});await page.close();
 }}finally{await browser.close();}
 const out=path.resolve(process.env.OPENTHERMOSTAT_DEBUG_SETTINGS_EVIDENCE||path.join(__dirname,'../out/debug-settings-lazy-20261027'));
 fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({scope:'Isolated HTTP; no device actions',results},null,2)+'\n');console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
