// Actual shipped room editor; synthetic admin WS, no live HA or device claims.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'ha/config/custom_components/open_thermostat/frontend/week-planner.js'));
const out=path.resolve(process.env.OPENTHERMOSTAT_PROGRAM_EVIDENCE||path.join(root,'out/ha-room-program-browser'));
const days=['monday','tuesday','wednesday','thursday','friday','saturday','sunday'];
const initial={measurement:{status:'profile_missing',report_profile_configured:false,sample_age_ms:null,usable:false},entry_id:'fixture',room_id:'room',supported:true,editable:true,program_only:true,apply_pending:false,
 token:'0'.repeat(64),rooms:[{room_id:'room',name:'Bathroom'}],time_zone:'Europe/Amsterdam',maximum_blocks:28,
 choices:{sensor:[{value:'sensor.room',label:'Room sensor',status:'available'}],
 climate:[{value:'climate.valve',label:'Room valve',status:'available'}],schedule:[]},
 settings:{name:'Bathroom',emitter:'radiator',temperature_entity:'sensor.room',radiator_entities:['climate.valve'],
 base_centi_c:2100,minimum_centi_c:500,maximum_centi_c:3000,maximum_age_ms:120000,program_source:'local',schedule_entity:'',
 week:Object.fromEntries(days.map(day=>[day,[]]))}};
(async()=>{
 fs.mkdirSync(out,{recursive:true});const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});const results=[];
 try{
 const boot=await browser.newPage();
 await boot.setContent('<home-assistant></home-assistant>');
 await boot.evaluate(text=>{window.editorImport=import('data:text/javascript;base64,'+text);},source.toString('base64'));
 await boot.waitForTimeout(100);
 assert.equal(await boot.evaluate(()=>!!customElements.get('openthermostat-room-editor-v38')),false);
 await boot.evaluate(async()=>{customElements.define('home-assistant',class extends HTMLElement{});await editorImport;});
 assert.equal(await boot.evaluate(()=>!!customElements.get('openthermostat-room-editor-v38')),true);
 assert.equal(await boot.evaluate(()=>!!customElements.get('ha-card')),false);
 // Existing saved v35 cards must render with ONLY the new module loaded.
 await boot.evaluate(initial=>{
  window.upgradeCalls=[];
  for(const tag of ['openthermostat-room-editor-v35','openthermostat-room-editor-v38','openthermostat-room-editor-v41']){
   const card=document.createElement(tag);document.body.append(card);
   card.setConfig({entry_id:initial.entry_id,room_id:initial.room_id});
   card.hass={language:'en',user:{is_admin:true},callWS:async request=>{
    upgradeCalls.push(request.type);
    if(request.type!=='open_thermostat/room/get')throw Error('Upgrade probe must not write');
    return structuredClone(initial);
   }};
  }
 },initial);
 for(const tag of ['openthermostat-room-editor-v35','openthermostat-room-editor-v38','openthermostat-room-editor-v41']){
  await boot.locator(tag+' #name').waitFor();
  assert.equal(await boot.locator(tag+' #name').inputValue(),initial.settings.name);
 }
 assert.deepEqual(await boot.evaluate(()=>upgradeCalls),['open_thermostat/room/get','open_thermostat/room/get','open_thermostat/room/get']);
 await boot.close();
 for(const [size,viewport]of [['desktop',{width:1440,height:1100}],['mobile',{width:390,height:844}]])for(const language of ['nl','en'])for(const shell of ['cold','preloaded']){
  const page=await browser.newPage({viewport});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<style>body{margin:0;font:14px Arial,sans-serif}</style><main></main>');
  await page.evaluate(shell=>{if(shell==='preloaded')customElements.define('ha-card',class extends HTMLElement{});customElements.define('openthermostat-room-editor-v15',class extends HTMLElement{});customElements.define('openthermostat-room-editor-v25',class extends HTMLElement{});customElements.define('openthermostat-room-editor-v28',class extends HTMLElement{});},shell);
 await page.evaluate(()=>customElements.define('home-assistant',class extends HTMLElement{}));
  await page.evaluate(async text=>{await Promise.race([import('data:text/javascript;base64,'+text),new Promise((_,reject)=>setTimeout(()=>reject(Error('Room editor registration blocked waiting for ha-card')),5000))])},source.toString('base64'));
  await page.evaluate(({initial,language})=>{
   window.model=structuredClone(initial);window.calls=[];window.saveMode='hold';
   const card=window.card=document.createElement('openthermostat-room-editor-v38');document.querySelector('main').append(card);
   card.setConfig({entry_id:model.entry_id,room_id:model.room_id});
   card.hass={language,user:{is_admin:true},callWS:async request=>{
    calls.push(structuredClone(request));
    if(request.type==='open_thermostat/room/get')return structuredClone(model);
    if(request.type==='open_thermostat/room/save'){
     const next={...structuredClone(model),settings:structuredClone(request.settings),token:'1'.repeat(64)};
     if(saveMode==='readback_lost')throw {code:'controller_readback_unconfirmed'};
     if(saveMode==='uncertain'){model={...next,apply_pending:true};throw {code:'save_uncertain'};}
     if(saveMode==='hold')return new Promise(resolve=>window.finishSave=()=>{model={...next,apply_pending:false};resolve(structuredClone(model));});
     model={...next,apply_pending:false};return structuredClone(model);
    }
    throw Error('Unexpected command');
   }};
  },{initial,language});
  const nl=language==='nl',card=page.locator('openthermostat-room-editor-v38');await card.locator('#name').waitFor();
  assert.match(await card.locator('.measurement-state').innerText(),nl?/getoetst meetprofiel ontbreekt/:/reviewed measurement profile is still missing/);
  const callsBeforeSourceReview=await page.evaluate(()=>calls.length);
  await page.evaluate(()=>{card._model.temperature_source_review={reason:'internal_device_temperature',authorizes_control:false};card.refreshStatus();});
  assert.match(await card.locator('.temperature-source-review').innerText(),nl?/interne apparaattemperatuur/:/internal device temperature/);
  await page.evaluate(()=>{card._model.choices.sensor.push({value:'sensor.other_diagnostic',label:'Other',status:'available',temperature_role:'diagnostic'});card._settings.temperature_entity='sensor.other_diagnostic';card.refreshStatus();});
  assert.match(await card.locator('.temperature-source-review').innerText(),nl?/diagnostiek/:/diagnostic/);
  assert.doesNotMatch(await card.locator('.temperature-source-review').innerText(),nl?/interne apparaattemperatuur/:/internal device temperature/);
  await page.evaluate(()=>{card._settings.temperature_entity='sensor.new_room_air';card.refreshStatus();});
  assert.equal(await card.locator('.temperature-source-review').innerText(),'');
  await page.evaluate(()=>{card._settings.temperature_entity=card._model.settings.temperature_entity;delete card._model.temperature_source_review;card.refreshStatus();});
  assert.equal(await page.evaluate(()=>calls.length),callsBeforeSourceReview);

  for(const status of ['qualified','stale','unverified','inactive']){
   await page.evaluate(status=>{card._model.measurement.status=status;card.refreshStatus();},status);
   assert((await card.locator('.measurement-state').innerText()).length>20);
  }
  await page.evaluate(()=>{card._model.measurement.status='unknown-future-status';card.refreshStatus();});
  assert.equal(await card.locator('.measurement-state').innerText(),'');
  await page.evaluate(()=>{card._model.measurement.status='profile_missing';card.refreshStatus();});
  if(shell==='cold'){
   assert.equal(await page.evaluate(()=>!!customElements.get('ha-card')),false);
   await card.locator('#name').fill('Retain draft across HA shell loading');
   await page.evaluate(()=>customElements.define('ha-card',class extends HTMLElement{}));
   assert.equal(await card.locator('#name').inputValue(),'Retain draft across HA shell loading');
   await card.locator('#name').fill(initial.settings.name);
  }
  const save=()=>card.locator('footer .primary');
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),0);
  assert(await card.locator('#name').isEnabled());assert(await card.locator('#base_centi_c').isEnabled());
  assert(await card.locator('#temperature_entity').isDisabled());assert(await card.locator('#emitter').isDisabled());
  await card.locator('.valves summary').click();assert(await card.locator('.valves input').isDisabled());
  await card.locator('.advanced summary').first().click();
  assert(await card.locator('#minimum_centi_c').isDisabled());assert(await card.locator('#maximum_centi_c').isDisabled());
  assert(await save().isDisabled());
  await card.locator('#name').fill('New bathroom');await card.locator('#base_centi_c').fill('20.5');
  await card.getByRole('button',{name:nl?'Blok toevoegen':'Add block',exact:true}).click();
  await card.locator('#block-temperature').fill('22');
  await save().click();await card.locator('#name:disabled').waitFor();
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),1);
  const first=await page.evaluate(()=>calls.find(c=>c.type.endsWith('/save')));
  assert.equal(first.settings.base_centi_c,2050);assert.equal(first.settings.week.monday[0].target_centi_c,2200);
  assert.equal(first.settings.temperature_entity,'sensor.room');assert.deepEqual(first.settings.radiator_entities,['climate.valve']);
  await page.evaluate(()=>finishSave());await card.locator('#name:enabled').waitFor();assert(await save().isDisabled());
  await card.getByText(nl?'De ruimte is opgeslagen en het programma is bevestigd':'The room is saved and its program is confirmed',{exact:false}).waitFor();
  await page.screenshot({path:path.join(out,`${size}-${language}-${shell}.png`),fullPage:true});
  await page.evaluate(()=>window.saveMode='uncertain');await card.locator('#name').fill('Retain my intent');await save().click();
  await card.getByText(nl?'De toepassing is nog niet bevestigd.':'Application has not been confirmed.',{exact:false}).waitFor();
  assert.equal(await card.locator('#name').inputValue(),'Retain my intent');assert(await save().isDisabled());
  page.once('dialog',dialog=>{assert.match(dialog.message(),nl?/opgeslagen/:/currently saved/);dialog.accept();});
  await card.getByRole('button',{name:nl?'Opnieuw laden':'Reload',exact:true}).click();
  await card.getByText(nl?'De ruimte is opgeslagen, maar':'The room is saved, but',{exact:false}).waitFor();
  const reapply=card.getByRole('button',{name:nl?'Programma opnieuw toepassen':'Apply program again',exact:true});
  assert(await reapply.isEnabled());assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),2);
  await page.evaluate(()=>window.saveMode='ok');await reapply.click();await card.locator('#name:enabled').waitFor();
  assert(await save().isDisabled());assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),3);
  await page.evaluate(()=>window.saveMode='readback_lost');await card.locator('#name').fill('Unsaved idle edit');await save().click();
  await card.getByText(nl?'Er is niets opgeslagen;':'Nothing was saved;',{exact:false}).waitFor();
  assert.equal(await card.locator('#name').inputValue(),'Unsaved idle edit');assert(await save().isEnabled());
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),4);
  assert.notEqual(await page.evaluate(()=>model.settings.name),'Unsaved idle edit');
  await page.evaluate(()=>window.saveMode='ok');await save().click();await card.locator('#name:enabled').waitFor();
  assert(await save().isDisabled());assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),5);
  assert.equal(await page.evaluate(()=>calls.every(c=>['open_thermostat/room/get','open_thermostat/room/save'].includes(c.type))),true);
  await page.evaluate(async()=>{model.profile_editable=true;await card.load();});
  assert(await card.locator('#temperature_entity').isEnabled());
  assert(await card.locator('#emitter').isDisabled());
  await card.locator('.valves summary').click();assert(await card.locator('.valves input').isEnabled());
  await page.evaluate(async()=>{Object.assign(model,{editable:false,program_only:false,profile_apply_pending:true,apply_pending:true});await card.load();});
  assert(await card.locator('#name').isDisabled());assert(await card.locator('#temperature_entity').isDisabled());
  const retryProfile=card.getByRole('button',{name:nl?'Opgeslagen instellingen toepassen':'Apply saved settings',exact:true});
  assert(await retryProfile.isEnabled());
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),5);
  await page.evaluate(()=>{Object.assign(model,{editable:true,program_only:true,profile_apply_pending:false,apply_pending:false});});
  await retryProfile.click();await card.locator('#name:enabled').waitFor();
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.type.endsWith('/save')).length),6);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);assert.deepEqual(errors,[]);
  results.push({size,language,shell,result:'PASS',hardware_locked:true,graphical_temperature_block:true,wait_for_save:true,uncertain_draft_preserved:true,reapply_explicit:true,no_device_actions:true});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync(path.join(out,'BROWSER.json'),JSON.stringify({result:'PASS',scope:'Real shipped JS; simulated admin WS, no physical qualification',cases:results},null,2)+'\n');
 console.log(JSON.stringify({result:'PASS',cases:results.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
