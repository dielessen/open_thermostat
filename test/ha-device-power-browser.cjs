// Actual room editor; native battery snapshots are read-only model projections.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.join(root,'out/device-power-20261027/browser');
const choice=value=>({value,label:value,status:'available',identity:{platform:'fixture',unique_id:'pin_'+value}});
const report=(kind,value)=>({status:'reported',value,entity_id:kind==='battery'?'sensor.room_battery':'binary_sensor.room_battery_low',reported_at:'2026-10-27T05:00:00+00:00',age_ms:300000});
const power={schema:1,scope:'native_ha_cached_state_only',physical_control_qualified:false,unresolved_sources:[],devices:[{label:'Shared sensor and valve',selected_entities:['sensor.room','climate.valve'],battery:report('battery',12.5),battery_low:report('battery_low',false)}]};
const model={entry_id:'fixture',room_id:'a1b2c3d4',supported:true,editable:true,program_only:false,apply_pending:false,token:'0'.repeat(64),
 rooms:[{room_id:'a1b2c3d4',name:'Room'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,device_power:power,
 choices:{sensor:[choice('sensor.room'),choice('sensor.other')],climate:[choice('climate.valve')],schedule:[],binary_sensor:[],input_number:[],person:[]},
 settings:{name:'Room',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],base_centi_c:2100,minimum_centi_c:500,maximum_centi_c:3000,
 maximum_age_ms:120000,program_source:'local',schedule_entity:'',contact_entities:[],contact_policy:{maximum_age_ms:3600000,open_delay_ms:0,close_delay_ms:30000},
 setpoint_entity:'',setpoint_duration_ms:600000,comfort:null,presence_entity:'',
 week:Object.fromEntries(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(day=>[day,[]]))}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<style>body{margin:0;font:14px Arial}</style><main></main>');
  await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async encoded=>{await import('data:text/javascript;base64,'+encoded);},source.toString('base64'));
  await page.evaluate(({model,lang})=>{
   window.model=structuredClone(model);window.originalPower=structuredClone(model.device_power);window.calls=[];
   const card=window.card=document.createElement('openthermostat-room-editor-v42');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   window.hass={language:lang,user:{is_admin:true},states:{},callWS:async request=>{
    calls.push(structuredClone(request));if(request.type!=='open_thermostat/room/get')throw Error('Unexpected write or device request');return structuredClone(window.model);
   }};card.hass=hass;
  },{model,lang});
  const card=page.locator('openthermostat-room-editor-v42');await card.locator('.device-power').waitFor({state:'attached'});
  await card.locator('details.advanced > summary').click();
  const text=()=>card.locator('.device-power').innerText();
  assert.match(await text(),lang==='nl'?/12,5%/:/12\.5%/);assert.match(await text(),lang==='nl'?/Uit gemeld/:/Reported off/);
  assert.equal(await card.locator('.device-power article').count(),1);
  // HA state updates cannot substitute a newer/reused source into a frozen
  // model snapshot, nor repeatedly rebuild the unchanged battery DOM.
  await page.evaluate(async()=>{
   window.powerMutations=[];const observer=new MutationObserver(records=>powerMutations.push(...records));
   observer.observe(card.shadowRoot.querySelector('.device-power'),{subtree:true,childList:true,characterData:true});
   for(let i=0;i<20;++i){hass={...hass,states:{'sensor.room_battery':{state:String(i),attributes:{}}}};card.hass=hass;}
   await Promise.resolve();observer.disconnect();
  });
  assert.equal(await page.evaluate(()=>powerMutations.length),0);assert.equal(await page.evaluate(()=>calls.length),1);
  await card.locator('#temperature_entity').selectOption('sensor.other');
  assert.match(await text(),lang==='nl'?/apparaatkoppelingen/:/device bindings/);assert.doesNotMatch(await text(),/12[.,]5%/);
  await page.evaluate(()=>card._cancel.click());assert.match(await text(),/12[.,]5%/);
  await page.evaluate(async()=>{model.device_power.devices[0].battery.value=0;await card.load();});
  assert.match(await text(),/0%/);assert.equal(await page.evaluate(()=>calls.length),2);
  for(const fault of ['missing','scope','authority','foreign','duplicate','boolean_percentage','false_fresh','bad_time','prototype_status']){
   await page.evaluate(async fault=>{
    const data=structuredClone(originalPower);
    if(fault==='scope')data.scope='physical_source';
    if(fault==='authority')data.physical_control_qualified=true;
    if(fault==='foreign')data.devices[0].selected_entities=['sensor.foreign'];
    if(fault==='duplicate')data.devices.push(structuredClone(data.devices[0]));
    if(fault==='boolean_percentage')data.devices[0].battery.value=false;
    if(fault==='false_fresh')data.devices[0].battery.age_ms=86400000;
    if(fault==='bad_time')data.devices[0].battery.reported_at='2026-02-31T05:00:00+00:00';
    if(fault==='prototype_status')data.devices[0].battery.status='constructor';
    model.device_power=fault==='missing'?undefined:data;await card.load();
   },fault);
   assert.match(await text(),lang==='nl'?/geen bijpassende batterijmomentopname/:/No matching battery snapshot/);
   assert.doesNotMatch(await text(),/12[.,]5%|0%/);
  }
  await page.evaluate(async()=>{
   model.device_power=structuredClone(originalPower);const device=model.device_power.devices[0];
   device.label='<img src=x onerror=alert(1)> Shared device';device.battery.status='stale';device.battery.age_ms=172800000;
   device.battery_low.value=true;await card.load();
  });
  assert.match(await text(),lang==='nl'?/minstens 24 uur oud/:/at least 24 hours old/);
  assert.match(await text(),lang==='nl'?/Aan gemeld/:/Reported on/);assert.equal(await card.locator('.device-power img').count(),0);
  assert.equal(await page.evaluate(()=>calls.every(x=>x.type==='open_thermostat/room/get')),true);
  assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(out,`BATTERY-${lang}-${width}.png`),fullPage:true});
  results.push({lang,width,result:'PASS',readOnlySnapshot:true,unknownAndZeroDistinct:true,sourceScopeChecked:true,noRefreshOnHassUpdates:true,noUnchangedDomRebuild:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2)+'\n');console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
