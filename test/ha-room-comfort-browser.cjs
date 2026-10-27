// Shipped HA editor and isolated WebSocket/state fixtures, no device IO.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.join(root,'out/room-comfort-20261027/browser');
const choice=(value,label,platform='fixture')=>({value,label,status:'available',identity:{platform,unique_id:'pin_'+value}});
const model={entry_id:'fixture',room_id:'a1b2c3d4',supported:true,editable:true,program_only:false,apply_pending:false,
 token:'0'.repeat(64),rooms:[{room_id:'a1b2c3d4',name:'Living room'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,
 contact_status_entity:'climate.fixture_room',choices:{sensor:[choice('sensor.room','Room sensor')],climate:[choice('climate.valve','Room valve')],schedule:[],
 binary_sensor:[],input_number:[],person:[choice('person.room','Room person','person')]},
 settings:{name:'Living room',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],base_centi_c:2100,
 minimum_centi_c:500,maximum_centi_c:3000,maximum_age_ms:120000,program_source:'local',schedule_entity:'',
 contact_entities:[],contact_policy:{maximum_age_ms:3600000,open_delay_ms:0,close_delay_ms:30000},
 setpoint_entity:'',setpoint_duration_ms:3600000,comfort:null,presence_entity:'',
 week:Object.fromEntries(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(day=>[day,[]]))}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<style>body{margin:0;font:14px Arial}</style><main></main>');
  await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({model,lang})=>{
   window.model=structuredClone(model);window.calls=[];window.saveMode='ok';
   const card=window.card=document.createElement('openthermostat-room-editor-v42');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   window.hass={language:lang,user:{is_admin:true},states:{},callWS:async request=>{
    calls.push(structuredClone(request));if(request.type.endsWith('/get'))return structuredClone(window.model);
    if(request.type!=='open_thermostat/room/save')throw Error('Unexpected command');
    if(saveMode==='frost')throw {code:'native_comfort_frost_profile'};
    if(saveMode==='uncertain')throw {code:'save_uncertain'};
    window.model={...window.model,settings:structuredClone(request.settings),token:'1'.repeat(64)};return structuredClone(window.model);
   }};card.hass=hass;
  },{model,lang});
  const card=page.locator('openthermostat-room-editor-v42'),save=card.locator('footer .primary'),status=card.locator('.comfort-status');
  await card.locator('.room-comfort').waitFor();assert.equal(await save.isDisabled(),true);
  await card.locator('.room-comfort > summary').click();await card.locator('#comfort_enabled').check();
  await card.locator('#presence_entity').selectOption('person.room');await card.locator('#comfort_away_centi_c').fill('17.5');await card.locator('#comfort_temporary_ms').fill('10');
  assert.match(await status.innerText(),lang==='nl'?/Sla op/:/Save to apply/);await save.click();
  await page.waitForFunction(()=>calls.filter(x=>x.type.endsWith('/save')).length===1);
  const saved=await page.evaluate(()=>calls.at(-1));assert.deepEqual(saved.settings.comfort,{away_centi_c:1750,frost_centi_c:500,temporary_ms:600000});
  assert.equal(saved.settings.presence_entity,'person.room');assert.equal(saved.binding_identities['person.room'].platform,'person');assert.equal(Object.keys(saved.binding_identities).length,3);
  await page.evaluate(()=>{hass={...hass,states:{'climate.fixture_room':{state:'heat',attributes:{comfort_mode:'auto',firmware_reason:'presence_away'}}}};card.hass=hass;});
  assert.match(await status.innerText(),lang==='nl'?/Afwezigheidsdoel/:/Away target/);
  await page.evaluate(()=>{hass.states['climate.fixture_room'].attributes.firmware_reason='presence_state_unknown';card.hass={...hass};});
  assert.match(await status.innerText(),lang==='nl'?/onbekend of verlopen/:/unknown or stale/);
  await page.evaluate(()=>{hass.states['climate.fixture_room'].state='unavailable';card.hass={...hass};});
  assert.match(await status.innerText(),lang==='nl'?/niet beschikbaar/:/unavailable/);assert.equal(await page.evaluate(()=>calls.length),2);
  await card.locator('#comfort_frost_centi_c').fill('4');await save.click();assert.equal(await page.evaluate(()=>calls.length),2);
  await card.locator('#comfort_frost_centi_c').fill('6');await page.evaluate(()=>{saveMode='frost'});await save.click();
  await page.waitForFunction(()=>!card._saving);assert.match(await card.locator('footer .status').innerText(),/5 °C/);
  await page.evaluate(()=>{saveMode='ok'});await card.locator('#comfort_enabled').uncheck();await save.click();
  await page.waitForFunction(()=>model.settings.comfort===null&&calls.filter(x=>x.type.endsWith('/save')).length===3);
  const cleared=await page.evaluate(()=>calls.at(-1));assert.equal(cleared.settings.comfort,null);assert.equal(cleared.settings.presence_entity,'');
  await card.locator('#comfort_enabled').check();await card.locator('#presence_entity').selectOption('person.room');
  await page.evaluate(()=>{saveMode='uncertain'});await save.click();await page.waitForFunction(()=>card._uncertain===true);
  assert.equal(await card.locator('#comfort_enabled').isChecked(),true);assert.equal(await card.locator('#presence_entity').inputValue(),'person.room');
  const count=await page.evaluate(()=>calls.length);await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>calls.length),count);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(out,`COMFORT-${lang}-${width}.png`),fullPage:true});
  results.push({lang,width,result:'PASS',nativePresenceIdentity:true,oneAtomicSave:true,liveStatusWithoutReads:true,explicitRemoval:true,uncertainDraftRetained:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
