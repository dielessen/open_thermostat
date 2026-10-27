// Shipped HA editor, isolated WebSocket fixture. No HA/E32/device connection.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.join(root,'out/room-contacts-20261027/browser');
const choice=(value,label)=>({value,label,status:'available',identity:{platform:'contact_fixture',unique_id:'pin_'+value}});
const initial={entry_id:'fixture',room_id:'a1b2c3d4',supported:true,editable:true,program_only:false,apply_pending:false,
 token:'0'.repeat(64),rooms:[{room_id:'a1b2c3d4',name:'Living room'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,
 contact_status_entity:'climate.fixture_room',choices:{sensor:[choice('sensor.room','Room sensor')],climate:[choice('climate.valve','Room valve')],schedule:[],
 binary_sensor:Array.from({length:9},(_,i)=>choice('binary_sensor.contact_'+i,i?'Door '+i:'Living room window'))},
 settings:{name:'Living room',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],base_centi_c:2100,
 minimum_centi_c:500,maximum_centi_c:3000,maximum_age_ms:120000,program_source:'local',schedule_entity:'',
 contact_entities:[],contact_policy:{maximum_age_ms:3600000,open_delay_ms:0,close_delay_ms:30000},
 week:Object.fromEntries(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(day=>[day,[]]))}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH}),results=[];
 try{for(const lang of ['en','nl'])for(const width of [1280,390,320]){
  const page=await browser.newPage({viewport:{width,height:950}}),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.setContent('<style>body{margin:0;font:14px Arial}</style><main></main>');
  await page.evaluate(()=>{customElements.define('home-assistant',class extends HTMLElement{});customElements.define('openthermostat-room-editor-v41',class extends HTMLElement{});});
  await page.evaluate(async text=>{await import('data:text/javascript;base64,'+text)},source.toString('base64'));
  await page.evaluate(({model,lang})=>{
   window.model=structuredClone(model);window.calls=[];window.saveMode='ok';
   const card=window.card=document.createElement('openthermostat-room-editor-v42');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   window.hass={language:lang,user:{is_admin:true},states:{},callWS:async request=>{
    calls.push(structuredClone(request));
    if(request.type==='open_thermostat/room/get')return structuredClone(window.model);
    if(request.type!=='open_thermostat/room/save')throw Error('Unexpected command');
    if(saveMode==='hold')return new Promise(()=>{});
    if(saveMode==='uncertain')throw {code:'save_uncertain'};
    window.model={...window.model,settings:structuredClone(request.settings),token:'1'.repeat(64)};return structuredClone(window.model);
   }};card.hass=hass;
  },{model:initial,lang});
  const card=page.locator('openthermostat-room-editor-v42'),save=card.locator('footer .primary');
  await card.locator('.room-contacts').waitFor();assert.equal(await save.isDisabled(),true);
  await card.locator('.contacts > summary').click();const boxes=card.locator('[data-contact-choice]');
  await boxes.nth(0).check();await boxes.nth(1).check();
  assert.match(await card.locator('.contact-status').innerText(),lang==='nl'?/Sla op/:/Save to apply/);
  await card.locator('.contact-options > summary').click();await card.locator('#contact_open_delay_ms').fill('5');
  await card.locator('#contact_close_delay_ms').fill('60');await card.locator('#contact_maximum_age_ms').fill('7200');
  await save.click();await page.waitForFunction(()=>calls.filter(x=>x.type.endsWith('/save')).length===1);
  const saved=await page.evaluate(()=>calls.at(-1));
  assert.deepEqual(saved.settings.contact_entities,['binary_sensor.contact_0','binary_sensor.contact_1']);
  assert.deepEqual(saved.settings.contact_policy,{open_delay_ms:5000,close_delay_ms:60000,maximum_age_ms:7200000});
  assert.equal(Object.keys(saved.binding_identities).length,4);assert.equal(saved.binding_identities['binary_sensor.contact_0'].unique_id,'pin_binary_sensor.contact_0');
  await page.evaluate(()=>{hass={...hass,states:{'climate.fixture_room':{state:'heat',attributes:{comfort_context_sources:{contacts:{count:2,reason:'contact_open',pending_ms:0}}}}}};card.hass=hass;});
  assert.match(await card.locator('.contact-status').innerText(),lang==='nl'?/gepauzeerd/:/paused/);
  await page.evaluate(()=>{hass.states['climate.fixture_room'].attributes.comfort_context_sources.contacts={count:2,reason:'contact_close_delay',pending_ms:29000};card.hass={...hass};});
  assert.match(await card.locator('.contact-status').innerText(),/29/);
  await page.evaluate(()=>{hass.states['climate.fixture_room'].state='unavailable';card.hass={...hass};});
  assert.match(await card.locator('.contact-status').innerText(),lang==='nl'?/niet beschikbaar/:/not available/);
  assert.equal(await page.evaluate(()=>calls.length),2,'State updates never add a read or write');
  // Invalid policies and too many contacts must stay local drafts.
  await card.locator('.contact-options > summary').click();await card.locator('#contact_maximum_age_ms').fill('30');await save.click();
  assert.match(await card.locator('footer .status').innerText(),lang==='nl'?/Controleer de gekozen contacten/:/Check contact selections/);
  assert.equal(await page.evaluate(()=>calls.length),2);await card.locator('#contact_maximum_age_ms').fill('7200');
  await card.locator('.contacts > summary').click();for(let i=2;i<9;i++)await boxes.nth(i).check();await save.click();
  assert.equal(await page.evaluate(()=>calls.length),2);for(let i=2;i<9;i++)await boxes.nth(i).uncheck();
  await page.evaluate(()=>{saveMode='uncertain'});await boxes.nth(1).uncheck();await save.click();
  await page.waitForFunction(()=>card._uncertain===true);assert.equal(await boxes.nth(0).isChecked(),true);
  const count=await page.evaluate(()=>calls.length);await page.waitForTimeout(150);assert.equal(await page.evaluate(()=>calls.length),count,'Uncertain save is never replayed');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
  await page.screenshot({path:path.join(out,`CONTACTS-${lang}-${width}.png`),fullPage:true});
  results.push({lang,width,result:'PASS',nativeSelections:true,oneSave:true,identityPins:true,liveStatusWithoutReads:true,uncertainDraftPreserved:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'RESULT.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
})().catch(error=>{console.error(error);process.exitCode=1;});
