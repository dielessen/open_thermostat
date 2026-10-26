// Real Settings page and DOM, isolated HTTP snapshots; no broker/device traffic.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const assets=path.resolve(__dirname,'../data/html'),output=path.resolve(__dirname,'../out/ems-devices-browser');
const reference=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(assets,'ems-reference.js.gz'))).toString().replace(/^window\.OT_EMS_REFERENCE = /,'').replace(/;\s*$/,''));
const allBoilerDefinitions=new Set(Object.entries(reference.groups).filter(([key])=>key.startsWith('boiler:')).flatMap(([,group])=>group.fields));
const ids=[...fs.readFileSync(path.resolve(__dirname,'../src/EMS/ClassicBoilerMonitor.h'),'utf8').matchAll(/\{"([a-z][a-z0-9_]+)", "/g)].map(m=>m[1]);assert.equal(ids.length,69);
function snapshot(){
 const fields=Object.fromEntries(ids.map(id=>[id,{value:null,unit:'degC',state:'unknown',quality:'reported',source_type:0,source_address:8,age_ms:null}]));
 fields.measured_flow_temperature={value:47.2,unit:'degC',state:'valid',quality:'reported',source_type:24,source_address:8,age_ms:500};
 fields.pressure={value:1.8,unit:'bar',state:'valid',quality:'unreliable',source_type:24,source_address:8,age_ms:500};
 fields.measured_return_temperature={value:null,unit:'degC',state:'stale',quality:'reported',source_type:24,source_address:8,age_ms:45000};
 return {enabled:true,inventory:{schema:1,capacity:16,untracked_frames:0,devices:[{address:8,frames:20,age_ms:500,product_id:123,version:'1.2',brand_id:null,untracked_types:0,telegram_types:[2,24]},{address:23,frames:3,age_ms:60000,product_id:null,version:null,brand_id:null,untracked_types:0,telegram_types:[32]}]},boiler:{fields}};
}
function settingsSnapshot(){return {schema:1,boot_id:'000000000000002a',revision:0,available:false,active:false,
 write_attempted:false,physical_validation:false,reason:'settings_transport_unqualified',settings:[
 ['heatingactivated','bool',1,0],['heatingtemp','degC',90,1],['burnminperiod','min',120,6],['pumpdelay','min',60,8]
 ].map(([entity,unit,maximum,offset])=>({entity,unit,minimum:0,maximum,offset,telegram_type:22}))};}
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[],requests=[];let data=snapshot(),fail=false,hold=false,pending=null,missingReference=false,settingsFail=false,settingsData=settingsSnapshot();
  page.on('pageerror',e=>errors.push(e.message));
  await page.context().addCookies([{name:'ot_ui_lang',value:lang,url:'http://opth.test'}]);
  await page.route('http://opth.test/**',async route=>{
   const req=route.request(),p=new URL(req.url()).pathname;requests.push({path:p,method:req.method()});
   if(p==='/ems-reference.js.gz'&&missingReference)return route.fulfill({status:503,body:''});
   if(p==='/auth/session')return route.fulfill({contentType:'application/json',body:JSON.stringify({authenticated:true,csrf:'a'.repeat(64)})});
   if(p==='/status')return route.fulfill({contentType:'application/json',body:JSON.stringify({controlMode:'shadow',ems:{},control:{fresh:false,reason:'waiting'}})});
   if(p==='/config/boiler-display')return route.fulfill({contentType:'application/json',body:'{"model":"none"}'});
   if(p==='/status/boiler/settings')return route.fulfill({status:settingsFail?503:200,contentType:'application/json',body:JSON.stringify(settingsData)});
   if(p==='/status/ems/devices'){
    if(hold){pending=route;return;}
    if(fail)return route.fulfill({status:503,body:'unavailable'});
    return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   }
   const file=path.join(assets,p==='/'?'index.html':p);if(!file.startsWith(assets+'/')||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   let body=fs.readFileSync(file);if(p.endsWith('.gz'))body=zlib.gunzipSync(body);
   return route.fulfill({contentType:/\.js(?:\.gz)?$/.test(p)?'application/javascript':p.endsWith('.css.gz')?'text/css':'text/html',body});
  });
  await page.goto('http://opth.test/');await page.locator('#auth-sign-out').waitFor();if(await page.locator('.navbar-toggler').isVisible())await page.locator('.navbar-toggler').click();await page.locator('#navbarDropdownMenuLink').click();await page.locator('a[data-page="boiler_test"]').click();
  const status=page.locator('#ems-devices-status');await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.equal(await page.locator('a[data-page="ems_devices"]').count(),0);
  assert.equal(await page.locator('#boiler-test').count(),1);
  // Every pinned boiler definition is reachable without an exact product ID;
  // catalogue capabilities never become an invented local command.
  const catalogue=page.locator('#ems-all-entities');
  while(await page.locator('#ems-catalog-more').isVisible())await page.locator('#ems-catalog-more').click();
  assert.equal(await page.locator('#ems-catalog-rows tr').count(),allBoilerDefinitions.size);
  await page.locator('#ems-catalog-access').selectOption('write');
  assert.equal(await page.locator('#ems-catalog-rows tr[data-access="read"],#ems-catalog-rows tr[data-access="command"]').count(),0);
  await page.locator('#ems-catalog-search').fill('heatingtemp');
  assert.match(await catalogue.innerText(),lang==='nl'?/Instelbaar in EMS-ESP/:/Configurable in EMS-ESP/);
  assert.match(await catalogue.innerText(),lang==='nl'?/wijzigen geblokkeerd/:/changes blocked/);
  assert.equal(await catalogue.locator('input[type="number"]').count(),0);
  assert.match(await catalogue.innerText(),/0 … 90.*°C/);
  const modelReferences=page.locator('#ems-catalog-rows .ems-models').first();
  await modelReferences.locator('summary').click();assert.match(await modelReferences.innerText(),/123/);
  await modelReferences.locator('summary').click();
  if(width===390)await catalogue.screenshot({path:path.join(output,`catalogue-${lang}-${width}.png`)});
  await page.locator('#ems-catalog-search').fill('heatingactivated');
  assert.match(await catalogue.innerText(),lang==='nl'?/Uit \/ Aan/:/Off \/ On/);
  await page.locator('#ems-catalog-search').fill('');await page.locator('#ems-catalog-access').selectOption('command');
  assert.equal(await page.locator('#ems-catalog-rows tr:not([data-access="command"])').count(),0);
  assert.match(await catalogue.innerText(),/reset/);
  await page.locator('#ems-catalog-access').selectOption('read');
  assert.equal(await page.locator('#ems-catalog-rows tr:not([data-access="read"])').count(),0);
  await page.locator('#ems-catalog-access').selectOption('all');await page.locator('#ems-catalog-model').selectOption('boiler:123');
  const exactDefinitions=new Set(reference.groups['boiler:123'].fields);
  while(await page.locator('#ems-catalog-more').isVisible())await page.locator('#ems-catalog-more').click();
  assert.equal(await page.locator('#ems-catalog-rows tr').count(),exactDefinitions.size);
  await page.locator('#ems-catalog-model').selectOption('all');
  const originalProduct=data.inventory.devices[0].product_id;
  data.inventory.devices[0].product_id=null;await page.locator('#ems-refresh').click();
  await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.match(await page.locator('#ems-catalog-status').innerText(),new RegExp(String(allBoilerDefinitions.size)));
  data.inventory.devices[0].product_id=originalProduct;await page.locator('#ems-refresh').click();
  await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.equal(await page.locator('#ems-device-list > details').count(),2);
  const settings=page.locator('#ems-boiler-settings');
  assert.equal(await settings.locator('tbody tr').count(),4);
  assert.match(await settings.innerText(),lang==='nl'?/wijzigen is nog niet beschikbaar/:/Changing settings is unavailable/);
  assert.equal(await settings.locator('input,select,button').count(),0);
  // Independent metadata failure must preserve the ordinary measurement list.
  settingsFail=true;await page.locator('#ems-refresh').click();
  await page.locator('#ems-settings-status').filter({hasText:lang==='nl'?'niet beschikbaar':'unavailable'}).waitFor();
  await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.equal(await page.locator('#ems-settings-table').isVisible(),false);
  assert.equal(await page.locator('#ems-devices').getAttribute('data-failed'),'false');
  settingsFail=false;
  data.boiler.fields.configured_heating_temperature={value:45,unit:'degC',state:'valid',quality:'reported',source_type:22,source_address:8,age_ms:500};
  data.boiler.fields.heating_enabled={value:1,unit:'bool',state:'valid',quality:'reported',source_type:22,source_address:8,age_ms:500};
  data.boiler.fields.pump_run_on={value:null,unit:'min',state:'stale',quality:'reported',source_type:22,source_address:8,age_ms:600001};
  await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.match(await settings.locator('[data-setting="heatingtemp"]').innerText(),/45 °C/);
  assert.match(await settings.locator('[data-setting="heatingactivated"]').innerText(),lang==='nl'?/Aan/:/On/);
  assert.match(await settings.locator('[data-setting="pumpdelay"]').innerText(),lang==='nl'?/Verlopen/:/Expired/);
  assert.match(await settings.locator('[data-setting="burnminperiod"]').innerText(),lang==='nl'?/Niet ontvangen/:/Not received/);
  if(width<=600)assert.equal(await settings.evaluate(node=>node.scrollWidth<=node.clientWidth),true);
  await settings.screenshot({path:path.join(output,`settings-${lang}-${width}.png`)});
  data.boiler.fields.configured_heating_temperature.source_type=24;
  await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.match(await settings.locator('[data-setting="heatingtemp"]').innerText(),lang==='nl'?/Niet-geverifieerde/:/Unverified/);
  assert(!(await settings.locator('[data-setting="heatingtemp"]').innerText()).includes('45 °C'));
  settingsData.settings[0]={entity:'__proto__',telegram_type:22};
  await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.equal(await page.locator('#ems-settings-table').isVisible(),false);
  settingsData=settingsSnapshot();
  // Unsafe/foreign definition sets are rejected without hiding measurements.
  settingsData.settings[0].entity='<img src=x onerror=alert(1)>';
  await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);
  assert.equal(await settings.locator('img').count(),0);
  assert.equal(await page.locator('#ems-settings-table').isVisible(),false);
  settingsData=settingsSnapshot();data=snapshot();
  await page.locator('#ems-refresh').click();await page.waitForFunction(()=>!document.querySelector('#ems-refresh').disabled);

  assert.match(await page.locator('#ems-device-list > details').first().locator(':scope > summary').innerText(),/GB\*72.*Trendline/i);
  await page.locator('[data-address="8"] > summary').click();
  assert.match(await page.locator('[data-address="23"] > summary').innerText(),/Thermostaat|Thermostat/);
  const ref=page.locator('[data-address="8"] .ems-reference');
  await ref.locator(':scope > summary').click();
  await ref.getByRole('combobox').selectOption('write');
  assert.match(await ref.innerText(),/selflowtemp/);
  assert(!(await ref.innerText()).includes('(burnstarts)'));
  await ref.locator('input').fill('selflowtemp');
  assert.match(await ref.innerText(),/selected flow temperature/);
  await ref.locator(':scope > summary').click();
  const library=page.locator('[data-address="8"] .ems-library');
  await library.locator(':scope > summary').click();
  await library.locator('details > summary').filter({hasText:'UBAMonitorFast'}).click();
  await library.getByText(/Offset 0 ·/).first().waitFor();
  assert.match(await library.innerText(),/Offset 0/);
  await library.locator(':scope > summary').click();
  await page.locator('[data-address="8"] > summary').click();
  const boiler=page.locator('details[data-address="8"]'),other=page.locator('details[data-address="23"]');await boiler.locator(':scope > summary').click();
  assert.equal(await boiler.locator('tbody tr').count(),3);assert.match(await boiler.innerText(),(lang==='nl'?/47,2 °C/:/47.2 °C/));assert.match(await boiler.innerText(),lang==='nl'?/Onbetrouwbaar/:/Unreliable/);assert.match(await boiler.innerText(),lang==='nl'?/Verlopen/:/Expired/);
  assert(!((await boiler.innerText()).includes('Nefit')),'No selected model presented as received identification');
  await other.locator(':scope > summary').click();assert.match(await other.innerText(),lang==='nl'?/nog niet worden gedecodeerd/:/not available yet/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,`${lang}-${width}.png`),fullPage:true});
  // A normal boiler has more than eight handlers; retain the complete bounded list.
  data.inventory.devices[0].telegram_types=Array.from({length:64},(_,i)=>i+1);
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.match(await boiler.locator('.ems-device-meta').last().innerText(),/0x40/);
  data.inventory.devices[0].telegram_types.push(65);
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Vernieuwen mislukt':'Refresh failed'}).waitFor();
  data.inventory.devices[0].telegram_types=[2,24];
  data.inventory.devices[0].brand_id=4;
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.match(await boiler.locator(':scope > summary').innerText(),/Nefit TrendLine/);
  await page.locator('#ems-search').fill('measured_flow');assert.equal(await boiler.locator('tbody tr').count(),1);
  await page.evaluate(()=>{window.keptFlowRow=[...document.querySelectorAll('tbody tr')].find(r=>r.textContent.includes('measured_flow_temperature'));});
  data.boiler.fields.measured_flow_temperature.value=48.1;await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.equal(await page.evaluate(()=>keptFlowRow===[...document.querySelectorAll('tbody tr')].find(r=>r.textContent.includes('measured_flow_temperature'))),true,'Existing entity row must be updated in place');
  assert.equal(await boiler.getAttribute('open'),'');assert.equal(await other.getAttribute('open'),'');assert.equal(await page.locator('#ems-search').inputValue(),'measured_flow');assert.match(await boiler.innerText(),(lang==='nl'?/48,1 °C/:/48.1 °C/));
  await page.locator('#ems-search').fill('');await page.locator('#ems-show-unknown').check();assert.equal(await boiler.locator('tbody tr').count(),69);
  await page.locator('#ems-access').selectOption('write');
  assert.equal(await boiler.locator('tbody tr').count(),4);
  assert.match(await boiler.innerText(),lang==='nl'?/wijzigen geblokkeerd/:/changes blocked/);
  await page.locator('#ems-access').selectOption('all');assert.equal(await boiler.locator('tbody tr').count(),69);
  data.boiler.fields.pressure.unit='bool';data.boiler.fields.pressure.value='off';
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Vernieuwen mislukt':'Refresh failed'}).waitFor({timeout:6000});
  assert.equal(await page.locator('#ems-devices').getAttribute('data-failed'),'true');
  assert.match(await settings.innerText(),lang==='nl'?/Geen nieuwe momentopname/:/No fresh snapshot/);
  data=snapshot();data.boiler.fields.measured_flow_temperature.value=48.1;
  fail=true;await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Vernieuwen mislukt':'Refresh failed'}).waitFor();assert.equal(await boiler.getAttribute('open'),'');assert.equal(await page.locator('#ems-devices').getAttribute('data-failed'),'true');assert.match(await boiler.innerText(),(lang==='nl'?/48,1 °C/:/48.1 °C/));
  fail=false;data.boiler.fields.bad={value:'<img src=x onerror=alert(1)>',unit:'text',state:'valid',quality:'reported',source_type:24,source_address:8,age_ms:0};data.inventory.devices[0].address=23; // Duplicate identity invalidates entire snapshot.
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Vernieuwen mislukt':'Refresh failed'}).waitFor();assert.equal(await page.locator('#ems-device-list img').count(),0);assert.equal(await page.locator('#ems-device-list > details').count(),2);
  data=snapshot();data.inventory.devices=[data.inventory.devices[1]];
  await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  data=snapshot();await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();
  assert.deepEqual(await page.locator('#ems-device-list > details').evaluateAll(nodes=>nodes.map(n=>n.dataset.address)),['8','23']);
  data=snapshot();data.inventory.devices=[];await page.locator('#ems-refresh').click();await status.filter({hasText:lang==='nl'?'Momentopname bijgewerkt':'Snapshot updated'}).waitFor();assert.equal(await page.locator('#ems-device-list > details').count(),0);assert.match(await page.locator('#ems-device-list').innerText(),lang==='nl'?/Nog geen/:/No EMS/);
  // Navigating away cancels a bounded in-flight read; no late repaint/new polling.
  hold=true;await page.locator('#ems-refresh').click();await page.waitForFunction(()=>document.querySelector('#ems-refresh').disabled);await page.evaluate(()=>loadNativePage('about'));await page.locator('#ems-devices').waitFor({state:'detached'});if(pending)await pending.fulfill({contentType:'application/json',body:JSON.stringify(snapshot())}).catch(()=>{});
  // Reference asset failure must not suppress already decoded local measurements.
  hold=false;missingReference=true;data=snapshot();await page.reload();
  await page.evaluate(()=>loadNativePage('ems_devices'));
  await page.locator('#ems-devices-status').filter({hasText:lang==='nl'?'EMS-referentie niet beschikbaar':'EMS reference unavailable'}).waitFor();
  const fallback=page.locator('[data-address="8"]');await fallback.locator(':scope > summary').click();
  assert.match(await fallback.locator(':scope > summary').innerText(),/Ketel|Boiler/);
  assert.equal(await fallback.locator('tbody tr').count(),3);
  assert.match(await fallback.innerText(),lang==='nl'?/47,2 °C/:/47.2 °C/);
  assert(!requests.some(r=>r.method!=='GET'));assert(!requests.some(r=>/scan|test\/start|updates\/install/.test(r.path)));assert.deepEqual(errors,[]);
  results.push({lang,width,result:'PASS',snapshot_only:true,no_device_commands:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(output,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(e=>{console.error(e);process.exitCode=1;});
