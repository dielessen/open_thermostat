// Shipped editor with an isolated native WebSocket contract. No device IO.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.join(root,'out/manual-target-20261027/browser');
const choice=(value,label,platform='fixture')=>({value,label,status:'available',identity:{platform,unique_id:'pin_'+value}});
const model={entry_id:'fixture',room_id:'a1b2c3d4',supported:true,editable:true,program_only:false,apply_pending:false,
 token:'0'.repeat(64),rooms:[{room_id:'a1b2c3d4',name:'Living room'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,
 contact_status_entity:'climate.fixture_room',choices:{sensor:[choice('sensor.room','Room sensor')],climate:[choice('climate.valve','Room valve')],schedule:[],
 binary_sensor:[],input_number:[choice('input_number.manual_target','Room temperature helper','input_number')]},
 settings:{name:'Living room',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],base_centi_c:2100,
 minimum_centi_c:500,maximum_centi_c:3000,maximum_age_ms:120000,program_source:'local',schedule_entity:'',
 contact_entities:[],contact_policy:{maximum_age_ms:3600000,open_delay_ms:0,close_delay_ms:30000},
 setpoint_entity:'',setpoint_duration_ms:3600000,
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
    if(saveMode==='uncertain')throw {code:'save_uncertain'};
    window.model={...window.model,settings:structuredClone(request.settings),token:'1'.repeat(64)};return structuredClone(window.model);
   }};card.hass=hass;
  },{model,lang});
  const card=page.locator('openthermostat-room-editor-v42'),save=card.locator('footer .primary');
  const selection=card.locator('#setpoint_entity'),duration=card.locator('#setpoint_duration_ms'),status=card.locator('.manual-target-status');
  await selection.waitFor();assert.equal(await save.isDisabled(),true);assert.equal(await duration.isDisabled(),true);
  await selection.selectOption('input_number.manual_target');await duration.fill('10');
  assert.match(await status.innerText(),lang==='nl'?/Sla op/:/Save to apply/);
  await save.click();await page.waitForFunction(()=>calls.filter(x=>x.type.endsWith('/save')).length===1);
  const request=await page.evaluate(()=>calls.at(-1));assert.equal(request.settings.setpoint_entity,'input_number.manual_target');assert.equal(request.settings.setpoint_duration_ms,600000);
  assert.equal(request.binding_identities['input_number.manual_target'].platform,'input_number');assert.equal(Object.keys(request.binding_identities).length,3);
  await page.evaluate(()=>{hass={...hass,states:{'climate.fixture_room':{state:'heat',attributes:{manual_target_source:{status:'request_accepted'},target_source:'temporary',override_remaining_minutes:9}}}};card.hass=hass;});
  assert.match(await status.innerText(),/9/);
  await page.evaluate(()=>{hass.states['climate.fixture_room'].state='unavailable';card.hass={...hass};});
  assert.match(await status.innerText(),lang==='nl'?/niet beschikbaar/:/unavailable/);assert.doesNotMatch(await status.innerText(),/9/);assert.equal(await page.evaluate(()=>calls.length),2);
  await duration.fill('0');await save.click();assert.equal(await page.evaluate(()=>calls.length),2);
  await duration.fill('15');await page.evaluate(()=>{saveMode='uncertain'});await save.click();await page.waitForFunction(()=>card._uncertain===true);
  assert.equal(await selection.inputValue(),'input_number.manual_target');assert.equal(await duration.inputValue(),'15');
  const count=await page.evaluate(()=>calls.length);await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>calls.length),count);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(out,`MANUAL-${lang}-${width}.png`),fullPage:true});
  results.push({lang,width,result:'PASS',identityPinned:true,oneSave:true,noStatusPolling:true,uncertainDraftRetained:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
