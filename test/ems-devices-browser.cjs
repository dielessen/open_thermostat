// Shipped root and entity panel: one coherent fixture snapshot, no device writes.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(__dirname,'../out/ems-devices-browser');
const sample=(value,unit='degC',extra={})=>({value,unit,state:'valid',quality:'reported',source_type:24,source_address:8,age_ms:100,...extra});
function snapshot(){return {reception:{state:'classic_reports_received'},transport:{enabled:true},
 manual_bus_identity:{source_address:23,matches_reviewed_address:true,source_conflict:false},
 inventory:{schema:1,capacity:16,untracked_frames:0,devices:[{address:8,frames:20,age_ms:100,product_id:211,version:'2.3',brand_id:1,untracked_types:0,telegram_types:[2,24]},
 {address:23,frames:2,age_ms:200,product_id:null,version:null,brand_id:null,untracked_types:0,telegram_types:[32]}]},
 fields:{measured_flow_temperature:sample(47.2),pressure:sample(2,'bar',{quality:'unreliable'}),
 measured_return_temperature:sample(null,'degC',{state:'stale',age_ms:45000}),
 heating_enabled:sample(1,'bool',{source_type:22}),configured_heating_temperature:sample(60,'degC',{source_type:22}),
 minimum_burner_period:sample(5,'min',{source_type:22}),pump_run_on:sample(3,'min',{source_type:22}),
 unknown_reading:sample(null,'degC',{state:'unknown',source_type:0,age_ms:null})}};}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[],requests=[];let data=snapshot(),failed=false,missingMetadata=false;
  page.on('pageerror',e=>errors.push(e.message));await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.route('http://opth.test/**',route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/auth/session')return route.fulfill({json:{authenticated:true,csrf:'a'.repeat(64)}});
   if(p==='/status')return route.fulfill({json:{controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}}});
   if(p==='/config/boiler-display')return route.fulfill({json:{model:'none'}});
   if(p==='/status/ems/telemetry')return route.fulfill(failed?{status:503,body:'unavailable'}:{json:data});
   if(p==='/ems-metadata.js'&&missingMetadata)return route.fulfill({status:503,body:''});
   const file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'text/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.evaluate(()=>loadNativePage('boiler_test'));
  const boiler=page.locator('details[data-address="8"]'),rows=boiler.locator('tbody tr');await rows.first().waitFor();
  assert.match(await boiler.locator('summary').first().innerText(),/Bosch EasyControl Adapter/);
  assert.equal(await rows.count(),7);assert.equal(await page.locator('[data-fields],#ems-all-entities,#ems-settings-table,.ems-reference').count(),0);
  assert.equal(await page.locator('[data-address="23"]').count(),0,'Our own reviewed bus identity is not an external thermostat');
  assert.equal(requests.filter(r=>r.path==='/status/ems/telemetry').length,1,'Both consumers share the initial read');
  assert.match(await boiler.innerText(),lang==='nl'?/47,2 °C/:/47.2 °C/);
  assert.match(await boiler.innerText(),lang==='nl'?/Onbetrouwbaar/:/Unreliable/);
  assert.match(await boiler.innerText(),lang==='nl'?/Verlopen/:/Expired/);
  assert.equal(await boiler.locator('[data-field="heating_enabled"]').count(),1);
  assert.equal(await boiler.locator('[data-field="heating_enabled"] button').isDisabled(),true);
  await page.locator('#ems-access').selectOption('write');assert.equal(await rows.count(),4);
  await page.locator('#ems-access').selectOption('all');await page.locator('#ems-search').fill('curflowtemp');assert.equal(await rows.count(),1);
  await page.evaluate(()=>window.savedFlow=document.querySelector('[data-field="measured_flow_temperature"]'));
  async function refresh(){await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);}
  data.fields.measured_flow_temperature.value=48.1;await refresh();
  assert.equal(await page.evaluate(()=>savedFlow===document.querySelector('[data-field="measured_flow_temperature"]')),true);
  assert.match(await boiler.innerText(),lang==='nl'?/48,1 °C/:/48.1 °C/);
  assert.equal(await page.locator('#ems-search').inputValue(),'curflowtemp');
  failed=true;await refresh();assert.equal(await page.locator('#ems-devices').getAttribute('data-failed'),'true');
  assert(!/48[.,]1/.test(await boiler.innerText()),'A failed read must suppress the previous numerical value');
  failed=false;data.inventory.devices[1].address=8;await refresh();
  assert.equal(await page.locator('#ems-devices').getAttribute('data-failed'),'true');
  data=snapshot();data.fields.safe_text=sample('<img src=x onerror=alert(1)>','text');await page.locator('#ems-search').fill('');await refresh();
  assert.equal(await page.locator('#ems-device-list img').count(),0);assert.match(await boiler.innerText(),/<img/);
  data.inventory.devices[0].product_id=null;await refresh();assert(!/EasyControl/.test(await boiler.locator('summary').first().innerText()));
  // A room thermostat with table-driven entities gets its own read-only card.
  data=snapshot();data.inventory.devices.push({address:16,frames:3,age_ms:300,product_id:null,version:null,brand_id:null,untracked_types:0,telegram_types:[177]});
  data.ems_entities={schema:1,reference:'emsesp_offsets',verified_on_hardware:false,devices:[{address:16,entities:[
   {id:'thermostat_room_temperature',value:20.5,unit:'degC',source_type:177,age_ms:300},{id:'thermostat_setpoint',value:null,unit:'degC',source_type:177,age_ms:300}]}],dropped:0};
  await refresh();
  const thermostat=page.locator('#ems-device-list > details[data-address="16"]');await thermostat.waitFor();
  await thermostat.locator('summary').click();
  assert.match(await thermostat.innerText(),lang==='nl'?/20,5 °C/:/20.5 °C/);
  assert.equal(await thermostat.locator('button').count(),0,'table entities are read only');
  data.ems_entities.devices[0].entities[0].value='bad';await refresh();
  assert.equal(await page.locator('#ems-device-list > details[data-address="16"]').count(),0,'invalid entity data is ignored, the boiler card remains');
  assert.equal(await page.locator('#ems-device-list > details[data-address="8"]').count(),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  fs.mkdirSync(output,{recursive:true});await page.screenshot({path:path.join(output,`${lang}-${width}.png`),fullPage:true});
  missingMetadata=true;data=snapshot();await page.reload();await page.evaluate(()=>loadNativePage('boiler_test'));
  await page.locator('[data-field="measured_flow_temperature"]').waitFor();
  assert.match(await page.locator('[data-field="measured_flow_temperature"]').innerText(),lang==='nl'?/47,2/:/47.2/);
  assert(!requests.some(r=>['/status/ems/devices','/status/boiler/settings','/ems-reference.js.gz'].includes(r.path)));
  assert(!requests.some(r=>r.method!=='GET'));assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',oneEntityTable:true,sharedSnapshot:true,noGuessedIdentity:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
