// Real Settings page and DOM, isolated HTTP snapshots; no broker/device traffic.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(__dirname,'../out/ems-devices-browser');
const ids=[...fs.readFileSync(path.resolve(__dirname,'../src/EMS/ClassicBoilerMonitor.h'),'utf8').matchAll(/\{"([a-z][a-z0-9_]+)", "/g)].map(m=>m[1]);assert.equal(ids.length,69);
function snapshot(){
 const fields=Object.fromEntries(ids.map(id=>[id,{value:null,unit:'degC',state:'unknown',quality:'reported',source_type:0,source_address:8,age_ms:null}]));
 fields.measured_flow_temperature={value:47.2,unit:'degC',state:'valid',quality:'reported',source_type:24,source_address:8,age_ms:500};
 fields.pressure={value:1.8,unit:'bar',state:'valid',quality:'unreliable',source_type:24,source_address:8,age_ms:500};
 fields.measured_return_temperature={value:null,unit:'degC',state:'stale',quality:'reported',source_type:24,source_address:8,age_ms:45000};
 return {enabled:true,inventory:{schema:1,capacity:16,untracked_frames:0,devices:[{address:8,frames:20,age_ms:500,product_id:123,version:'1.2',brand_id:null,untracked_types:0,telegram_types:[2,24]},{address:16,frames:3,age_ms:60000,product_id:null,version:null,brand_id:null,untracked_types:0,telegram_types:[32]}]},boiler:{fields}};
}
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],requests=[];let data=snapshot(),fail=false,hold=false,pending=null;
  page.on('pageerror',e=>errors.push(e.message));
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}})});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(p==='/status/ems/devices'){
    if(hold){pending=route;return;}
    if(fail)return route.fulfill({status:503,body:'unavailable'});
    return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   }
   const file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor();if(await page.locator('.navbar-toggler').isVisible())await page.locator('.navbar-toggler').click();await page.locator('#navbarDropdownMenuLink').click();await page.locator('a[data-page="ems_devices"]').click();
  const status=page.locator('#ems-devices-status');await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.equal(await page.locator('#ems-device-list details').count(),2);
  const boiler=page.locator('details[data-address="8"]'),other=page.locator('details[data-address="16"]');await boiler.locator('summary').click();
  assert.equal(await boiler.locator('tbody tr').count(),3);assert.match(await boiler.innerText(),/47.2 °C/);assert.match(await boiler.innerText(),lang==='nl'?/Onbetrouwbaar/:/Unreliable/);assert.match(await boiler.innerText(),lang==='nl'?/Verlopen/:/Expired/);
  assert(!((await boiler.innerText()).includes('Nefit')),'No selected model presented as received identification');
  await other.locator('summary').click();assert.match(await other.innerText(),lang==='nl'?/nog niet worden gedecodeerd/:/not available yet/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,`${lang}-${width}.png`),fullPage:true});
  await page.locator('#ems-search').fill('measured_flow');assert.equal(await boiler.locator('tbody tr').count(),1);
  data.boiler.fields.measured_flow_temperature.value=48.1;await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.equal(await boiler.getAttribute('open'),'');assert.equal(await other.getAttribute('open'),'');assert.equal(await page.locator('#ems-search').inputValue(),'measured_flow');assert.match(await boiler.innerText(),/48.1 °C/);
  await page.locator('#ems-search').fill('');await page.locator('#ems-show-unknown').check();assert.equal(await boiler.locator('tbody tr').count(),69);
  fail=true;await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Vernieuwen mislukt':'Refresh failed'}).waitFor();assert.equal(await boiler.getAttribute('open'),'');assert.equal(await page.locator('#ems-devices').getAttribute('data-failed'),'true');assert.match(await boiler.innerText(),/48.1 °C/);
  fail=false;data.boiler.fields.bad={value:'<img src=x onerror=alert(1)>',unit:'text',state:'valid',quality:'reported',source_type:24,source_address:8,age_ms:0};data.inventory.devices[0].address=16; // Duplicate identity invalidates entire snapshot.
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Vernieuwen mislukt':'Refresh failed'}).waitFor();assert.equal(await page.locator('#ems-device-list img').count(),0);assert.equal(await page.locator('#ems-device-list details').count(),2);
  data=snapshot();data.inventory.devices=[];await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();assert.equal(await page.locator('#ems-device-list details').count(),0);assert.match(await page.locator('#ems-device-list').innerText(),lang==='nl'?/Nog geen/:/No EMS/);
  // Navigating away cancels a bounded in-flight read; no late repaint/new polling.
  hold=true;await page.locator('#ems-refresh').click();await page.waitForFunction(()=>document.querySelector('#ems-refresh').disabled);await page.evaluate(()=>loadNativePage('about'));await page.locator('#ems-devices').waitFor({state:'detached'});if(pending)await pending.fulfill({contentType:'application/json',body:JSON.stringify(snapshot())}).catch(()=>{});
  assert(!requests.some(r=>r.method!=='GET'));assert(!requests.some(r=>/scan|test\/start|updates\/install/.test(r.path)));assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',snapshot_only:true,no_device_commands:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
